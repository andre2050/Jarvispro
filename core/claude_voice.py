"""
Claude voice loop (Phase 1).

Replaces the Gemini Live session with:
    microphone -> energy-based utterance capture
               -> faster-whisper transcription   (core/stt.py, offline)
               -> Claude Messages API with tool use
               -> pyttsx3 speech                 (offline)

Phase 1 scope — deliberately narrower than main.py:
    * half-duplex: the mic is ignored while NEXUS speaks (no barge-in yet)
    * no wake word, push-to-talk, proactive mode, vision or avatar
    * tools: the inline tools below + every actions/*.py TOOL and plugin

The existing main.py (Gemini Live) is untouched and still the default app.
"""
from __future__ import annotations
from core.pt_time import agora, data_hora

import json
import queue
import re
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.action_loader import discover_actions          # noqa: E402
from core.plugin_loader import discover_plugins          # noqa: E402
from core import undo as undo_stack                      # noqa: E402
from memory.memory_manager import (                      # noqa: E402
    load_memory, update_memory, search_memory, format_memory_for_prompt,
)
from memory.config_manager import load_api_keys, get_assistant_name  # noqa: E402
from core import preferences as _P  # noqa: E402
from core.protecao import engolida as _engolida

SAMPLE_RATE = 16000
BLOCK = 512                       # 32 ms frames
SILENCE_END_S = 0.8               # silence that closes an utterance
MAX_UTTERANCE_S = 20.0
MIN_UTTERANCE_S = 0.4
PRE_ROLL_S = 0.3
HISTORY_MESSAGES = 30             # sliding window sent to Claude
MAX_TOOL_ROUNDS = 8
TOOL_RESULT_CHARS = 4000

DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_WHISPER = "small"
DEFAULT_LANGUAGE = "pt"

PROMPT_PATH = BASE_DIR / "core" / "prompt.txt"

_REPEAT_WORDS = {"repete", "repita", "repete isso", "repita isso", "repeat", "repeat that"}

_TONE = {
    "formal": "Use a formal, courteous tone. No slang.",
    "casual": "Use a casual, friendly tone.",
    "direto": "Be very direct: answer first, no pleasantries, no filler.",
}


# ── Inline tools ──────────────────────────────────────────────────────────────
# Same behaviour as the inline tools in main.py, declared in the Claude schema
# shape (lowercase JSON-schema types). Vision, camera and shutdown are left out
# in Phase 1 because they depend on the Live session's state.
INLINE_TOOLS = [
    {
        "name": "system_status",
        "description": ("Returns real-time system metrics: CPU usage, RAM, GPU load, CPU "
                        "temperature, uptime, and process count. Use when the user asks about "
                        "computer performance, temperature, memory, or resource usage."),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "save_memory",
        "description": ("Save an important personal fact about the user to long-term memory. "
                        "Call silently when the user reveals something worth remembering. "
                        "Values must be in English."),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description":
                    "identity | preferences | projects | relationships | wishes | notes"},
                "key": {"type": "string", "description": "Short snake_case key"},
                "value": {"type": "string", "description": "Concise value in English"},
            },
            "required": ["category", "key", "value"],
        },
    },
    {
        "name": "recall_memory",
        "description": "Search long-term memory about the user. Use before answering personal questions.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "What to look for"}},
            "required": ["query"],
        },
    },
    {
        "name": "undo",
        "description": "Undo the last change NEXUS made, or list what can be undone.",
        "input_schema": {
            "type": "object",
            "properties": {"action": {"type": "string", "description": "'undo' or 'list'"}},
            "required": ["action"],
        },
    },
    {
        "name": "manage_monitor",
        "description": "Add, remove or list topics NEXUS watches in the background for news.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "add | remove | list"},
                "topic": {"type": "string", "description": "Topic (not needed for list)"},
            },
            "required": ["action"],
        },
    },
]
INLINE_NAMES = {t["name"] for t in INLINE_TOOLS}


def _to_claude_schema(node):
    """Gemini declarations use uppercase types ("OBJECT", "STRING"). Claude wants
    JSON-schema lowercase. Property *names* are left alone, even if one is 'type'."""
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == "properties" and isinstance(v, dict):
                out[k] = {pk: _to_claude_schema(pv) for pk, pv in v.items()}
            elif k == "type" and isinstance(v, str):
                out[k] = v.lower()
            else:
                out[k] = _to_claude_schema(v)
        return out
    if isinstance(node, list):
        return [_to_claude_schema(x) for x in node]
    return node


def _block_to_dict(block) -> dict:
    if isinstance(block, dict):
        return block
    if hasattr(block, "model_dump"):
        return block.model_dump(exclude_none=True)
    return dict(block)


# ── Speech ────────────────────────────────────────────────────────────────────
class Speaker:
    """pyttsx3 wrapper. Blocking, one utterance at a time."""

    def __init__(self, language: str = DEFAULT_LANGUAGE, rate: int = 185):
        self._engine = None
        self._lock = threading.Lock()
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", int(_P.get("voice_rate") or rate))
            vol = max(0, min(100, int(_P.get("voice_volume") or 100)))
            self._engine.setProperty("volume", vol / 100)
            voice_id = self._pick_voice(language)
            if voice_id:
                self._engine.setProperty("voice", voice_id)
        except Exception as e:
            print(f"[TTS] pyttsx3 unavailable ({e}) — replies will be printed only.")
            self._engine = None

    def _pick_voice(self, language: str) -> str | None:
        try:
            from core.vozes import escolher_voz
            if language:
                return escolher_voz(self._engine.getProperty("voices"), (language.lower(),))
        except Exception:
            _engolida("core/claude_voice.py:184")
        return None

    def say(self, text: str) -> None:
        clean = _speakable(text)
        if not clean:
            return
        print(f"NEXUS: {text}")
        if self._engine is None:
            return
        with self._lock:
            try:
                self._engine.say(clean)
                self._engine.runAndWait()
            except Exception as e:
                print(f"[TTS] speak failed: {e}")


def _speakable(text: str) -> str:
    """Strip markdown that a voice would read out as noise."""
    t = re.sub(r"```.*?```", " ", text, flags=re.S)
    t = re.sub(r"[*_`#>]+", "", t)
    t = re.sub(r"^\s*[-•]\s+", "", t, flags=re.M)
    return re.sub(r"\s+", " ", t).strip()


# ── Listening ─────────────────────────────────────────────────────────────────
class Listener:
    """Captures one utterance at a time from the default microphone.

    Threshold is calibrated from the first second of room noise, so it adapts to
    the mic and the room instead of using a fixed number.
    """

    def __init__(self, device=None):
        import sounddevice as sd
        self._q: queue.Queue = queue.Queue(maxsize=400)
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32",
            blocksize=BLOCK, callback=self._on_audio, device=device,
        )
        self._threshold = 0.012

    def _on_audio(self, indata, frames, t, status):
        try:
            self._q.put_nowait(indata[:, 0].copy())
        except queue.Full:
            pass  # dropping audio while busy is better than blocking the device

    def __enter__(self):
        self._stream.start()
        self.calibrate()
        return self

    def __exit__(self, *exc):
        self._stream.stop()
        self._stream.close()

    def drain(self) -> None:
        """Throw away audio captured while NEXUS was speaking (echo guard)."""
        while True:
            try:
                self._q.get_nowait()
            except queue.Empty:
                break

    def calibrate(self, seconds: float = 1.0) -> None:
        self.drain()
        levels = []
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            try:
                frame = self._q.get(timeout=0.2)
                levels.append(float(np.sqrt(np.mean(frame ** 2))))
            except queue.Empty:
                pass
        if levels:
            floor = float(np.percentile(levels, 90))
            try:
                sens = float(_P.get("mic_sensitivity") or 1.0)
            except (TypeError, ValueError):
                sens = 1.0
            self._threshold = max(0.004, floor * 3.0 * sens)
        print(f"[Mic] noise threshold {self._threshold:.4f}")

    def next_utterance(self) -> np.ndarray | None:
        """Block until the user has said something, return it as float32 mono."""
        pre_roll: list[np.ndarray] = []
        pre_max = int(PRE_ROLL_S * SAMPLE_RATE / BLOCK)
        chunks: list[np.ndarray] = []
        recording = False
        silent_for = 0.0
        started = 0.0
        frame_s = BLOCK / SAMPLE_RATE

        while True:
            try:
                frame = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            level = float(np.sqrt(np.mean(frame ** 2)))

            if not recording:
                pre_roll.append(frame)
                pre_roll = pre_roll[-pre_max:]
                if level > self._threshold:
                    recording = True
                    started = time.monotonic()
                    chunks = list(pre_roll)
                    silent_for = 0.0
                continue

            chunks.append(frame)
            if level > self._threshold:
                silent_for = 0.0
            else:
                silent_for += frame_s
            too_long = (time.monotonic() - started) > MAX_UTTERANCE_S
            if silent_for >= SILENCE_END_S or too_long:
                audio = np.concatenate(chunks)
                if len(audio) / SAMPLE_RATE < MIN_UTTERANCE_S:
                    recording, chunks, pre_roll = False, [], []
                    continue
                return audio.astype(np.float32)


# ── The brain ─────────────────────────────────────────────────────────────────
class ClaudeVoice:
    def __init__(self):
        keys = load_api_keys()
        self.api_key = str(keys.get("anthropic_api_key") or "").strip()
        if not self.api_key:
            raise RuntimeError("anthropic_api_key is not set in config/api_keys.json")
        self.model = str(keys.get("claude_voice_model") or DEFAULT_MODEL)
        whisper_name = str(keys.get("whisper_model") or DEFAULT_WHISPER)
        language = str(keys.get("voice_language") or DEFAULT_LANGUAGE)

        import anthropic
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=self.api_key, timeout=60.0, max_retries=2)

        self.assistant_name = get_assistant_name()
        self.history: list[dict] = []
        self.speaker = Speaker(language=language)

        from core.stt import WhisperSTT
        self.stt = WhisperSTT(model_name=whisper_name, language=language)

        self._actions = discover_actions(
            actions_dir=BASE_DIR / "actions",
            reserved_names=INLINE_NAMES,
            logger=lambda m: print(f"[Actions] {m}"),
        )
        core_names = INLINE_NAMES | self._actions.names()
        self._plugins = discover_plugins(
            plugins_dir=BASE_DIR / "plugins",
            core_tool_names=core_names,
            logger=lambda m: print(f"[Plugins] {m}"),
        )
        self.tools = [_to_claude_schema({
            "name": d["name"],
            "description": d.get("description", ""),
            "input_schema": _to_claude_schema(d.get("parameters") or {"type": "OBJECT", "properties": {}}),
        }) for d in self._action_and_plugin_decls()] + INLINE_TOOLS

    # ── tool wiring ──
    def _action_and_plugin_decls(self) -> list[dict]:
        decls = list(self._actions.get_tool_declarations())
        for d in self._plugins.get_tool_declarations():
            decls.append(d)
        return decls

    def _run_tool(self, name: str, args: dict) -> str:
        print(f"[Tool] {name} {args}")
        try:
            if name == "system_status":
                from actions.system_monitor import get_system_status
                return str(get_system_status())
            if name == "save_memory":
                cat, key, val = args.get("category", "notes"), args.get("key", ""), args.get("value", "")
                if key and val:
                    update_memory({cat: {key: {"value": val}}})
                return "ok"
            if name == "recall_memory":
                return search_memory(args.get("query", ""), limit=8)
            if name == "undo":
                if str(args.get("action", "")).lower().strip() == "list":
                    items = undo_stack.history()
                    return "\n".join(f"{i+1}. {t}" for i, t in enumerate(items)) or "Nothing to undo."
                return undo_stack.undo_last()
            if name == "manage_monitor":
                from actions.background_monitor import add_monitor, remove_monitor, list_monitors
                action = str(args.get("action", "")).lower().strip()
                topic = str(args.get("topic", "")).strip()
                if action == "add" and topic:
                    return add_monitor(topic)
                if action == "remove" and topic:
                    return remove_monitor(topic)
                if action == "list":
                    topics = list_monitors()
                    return ("Monitoring: " + ", ".join(topics)) if topics else "No topics are monitored."
                return "Specify action (add/remove/list) and a topic."
            if self._actions.has(name):
                ctx = {"player": None, "speak": self.speaker.say,
                       "response": None, "session_memory": None}
                return self._actions.run(name, args, ctx) or "Done."
            if self._plugins.has(name):
                return self._plugins.run(name, args, player=None, session_memory=None) or "Done."
            return f"Unknown tool: {name}"
        except Exception as e:
            traceback.print_exc()
            return f"Tool '{name}' failed: {e}"

    # ── prompt ──
    def _system_prompt(self) -> str:
        try:
            template = PROMPT_PATH.read_text(encoding="utf-8")
        except Exception:
            template = ("You are {assistant_name}, a voice assistant. Be concise. "
                        "Always use the provided tools to act; never pretend a tool ran.")
        values = {
            "assistant_name": self.assistant_name,
            "platform": sys.platform,
            "capabilities": "voice conversation, computer control and tools",
            "limits": "you hear the user only through speech transcription",
            "braces": "{}",
        }
        out = template
        for k, v in values.items():
            out = out.replace("{" + k + "}", v)
        memory_block = format_memory_for_prompt(load_memory())
        now = data_hora(agora())
        return (f"{out}\n\nHora atual (horário de Brasília): {now}.\n"
                f"Your replies are read aloud: keep them short, plain, no markdown, no lists.\n"
                f"{_TONE.get(str(_P.get('reply_tone') or ''), '')}\n\n"
                f"{memory_block}")

    # ── conversation ──
    def _trimmed_history(self) -> list[dict]:
        msgs = self.history[-HISTORY_MESSAGES:]
        # The window must start on a plain user text turn, never on a tool_result,
        # or the API rejects it.
        while msgs and not (msgs[0]["role"] == "user" and isinstance(msgs[0]["content"], str)):
            msgs = msgs[1:]
        return msgs

    def ask(self, user_text: str) -> str:
        self.history.append({"role": "user", "content": user_text})
        for _ in range(MAX_TOOL_ROUNDS):
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=self._system_prompt(),
                tools=self.tools,
                messages=self._trimmed_history(),
            )
            blocks = [_block_to_dict(b) for b in resp.content]
            self.history.append({"role": "assistant", "content": blocks})

            if resp.stop_reason != "tool_use":
                return "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()

            results = []
            for b in blocks:
                if b.get("type") == "tool_use":
                    args = b.get("input") or {}
                    out = self._run_tool(b["name"], args)
                    from core.audit import record as _audit
                    _audit(b["name"], args, out)
                    results.append({"type": "tool_result", "tool_use_id": b["id"],
                                    "content": str(out)[:TOOL_RESULT_CHARS]})
            self.history.append({"role": "user", "content": results})
        return "Sorry, I got stuck in a loop with my tools."

    def turn(self, audio: np.ndarray) -> None:
        try:
            heard = self.stt.transcribe(audio).strip()
        except Exception as e:
            print(f"[STT] failed: {e}")
            return
        if not heard:
            return
        print(f"YOU: {heard}")
        if heard.lower().strip(" .!?") in _REPEAT_WORDS:
            self.speaker.say(getattr(self, "last_reply", "") or "Ainda não tenho nada para repetir.")
            return
        try:
            reply = self.ask(heard)
        except self._anthropic.APIError as e:
            print(f"[Claude] API error: {e}")
            self.history.pop()          # drop the unanswered user turn
            self.speaker.say("Desculpe, não consegui falar com a Claude agora.")
            return
        if reply:
            self.last_reply = reply
            self.speaker.say(reply)


def run() -> None:
    """Console loop: listen, think, speak. Ctrl+C to quit."""
    print("[Claude voice] starting…")
    jarvis = ClaudeVoice()
    jarvis.speaker.say(f"{jarvis.assistant_name} online.")
    try:
        from core import audio_devices
        from memory.config_manager import get_input_device
        mic_dev = audio_devices.resolve(get_input_device(), "input")
    except Exception as e:
        print(f"[Claude voice] microfone escolhido indisponível, usando o padrão: {e}")
        mic_dev = None
    with Listener(device=mic_dev) as mic:
        print("[Claude voice] listening. Ctrl+C to stop.")
        try:
            while True:
                audio = mic.next_utterance()
                if audio is None:
                    continue
                jarvis.turn(audio)
                mic.drain()        # ignore our own voice echo
        except KeyboardInterrupt:
            print("\n[Claude voice] stopped.")
