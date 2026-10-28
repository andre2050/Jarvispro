"""LLM Brain — wired-in LLM for heavy text work.

The voice session (Gemini Live) is the conversational brain; this tool is
the *writing desk*. Long generation, summarising and translation go to a
dedicated text LLM instead of being crammed into the voice session:

  1. Local first (llm_provider config: Ollama, LM Studio, etc.) — the
     project already ships core/llm_client.py for this.
  2. Cloud fallback: the Gemini API key already in config.

Outputs are auto-saved whole to memory/llm_outputs/ and the voice reply
carries a short excerpt plus the file path.
"""

import re
import time
from pathlib import Path

_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "memory" / "llm_outputs"
_MAX_VOICE_CHARS = 600
_GEMINI_MODELS = ["gemini-2.0-flash", "gemini-flash-latest", "gemini-1.5-flash"]


# ── providers ────────────────────────────────────────────────────────────────

def local_available() -> bool:
    """True if the configured local LLM server answers."""
    try:
        from core.llm_client import call_llm_text
        out = call_llm_text("ping", timeout=20)
        return isinstance(out, str)
    except Exception:
        return False


def _gemini_key() -> str:
    try:
        from memory.config_manager import load_api_keys
        return str(load_api_keys().get("gemini_api_key", "")).strip()
    except Exception:
        return ""


def _call_gemini(prompt: str, system: str | None = None) -> str:
    """Text completion via the Gemini REST API (cloud fallback)."""
    # json not needed — requests handles the payload
    import requests
    key = _gemini_key()
    if not key:
        raise RuntimeError("no Gemini API key configured")
    last_err = None
    for model in _GEMINI_MODELS:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={key}",
                json={"contents": [{"role": "user",
                                    "parts": [{"text": prompt}]}],
                      **({"systemInstruction":
                          {"parts": [{"text": system}]}}
                         if system else {})},
                timeout=120)
            if r.status_code == 404:
                last_err = f"model {model} not found"
                continue
            r.raise_for_status()
            data = r.json()
            cands = data.get("candidates", [])
            if not cands:
                raise RuntimeError("empty response")
            parts_out = cands[0].get("content", {}).get("parts", [])
            return "".join(p.get("text", "") for p in parts_out)
        except RuntimeError:
            raise
        except Exception as e:
            last_err = str(e)
    raise RuntimeError(last_err or "Gemini call failed")


def complete(prompt: str, system: str | None = None,
             prefer: str = "auto") -> str:
    """One text completion. Local LLM first, Gemini cloud as fallback."""
    if prefer != "cloud" and local_available():
        from core.llm_client import call_llm_text
        return call_llm_text(prompt, system=system)
    return _call_gemini(prompt, system=system)


def status() -> str:
    loc = local_available()
    key = bool(_gemini_key())
    if loc:
        return "local LLM online"
    if key:
        return "no local LLM — will use Gemini cloud"
    return ("no LLM available: install Ollama/LM Studio or set the "
            "Gemini key, sir")


# ── output persistence ─────────────────────────────────────────────────────────

def _save_output(text: str) -> str:
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"llm_{time.strftime('%Y%m%d_%H%M%S')}.txt"
    path = _OUTPUT_DIR / fname
    path.write_text(text, encoding="utf-8")
    return str(path)


def _voice_excerpt(text: str) -> str:
    text = text.strip()
    if len(text) <= _MAX_VOICE_CHARS:
        return f"{text} — full text saved to {_save_output(text)}"
    cut = text[:_MAX_VOICE_CHARS]
    cut = re.sub(r"\s+\S*$", "", cut)         # end on a word boundary
    return (f"{cut}… [truncated] — full text saved to {_save_output(text)}")


# ── handler ───────────────────────────────────────────────────────────────────

def llm_brain_action(parameters: dict, player=None, session_memory=None) -> str:
    action = str(parameters.get("action") or "").strip().lower()
    text   = str(parameters.get("text") or "").strip()
    prompt = str(parameters.get("prompt") or "").strip()
    target = str(parameters.get("target_language") or "").strip()
    path   = str(parameters.get("file_path") or "").strip()

    # file input for summarize
    if path and not text:
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")[:60000]
        except Exception as e:
            msg = f"Sir, I couldn't read that file: {e}"
            _log(msg, player)
            return msg

    if action == "generate":
        if not prompt:
            msg = "Sir, what should I write about?"
            _log(msg, player); return msg
        try:
            out = complete(prompt,
                           system="You are a precise, helpful writing "
                                  "assistant. Deliver exactly what is asked.")
            msg = _voice_excerpt(out)
            _log(f"generated {len(out)} chars", player)
            return msg
        except Exception as e:
            return _unavailable(e, player)

    if action == "summarize":
        if not text:
            msg = "Sir, give me the text or a file path to summarise."
            _log(msg, player); return msg
        try:
            out = complete(
                "Summarise the following text in clear, concise bullet "
                "points, in the same language as the text:\n\n" + text)
            msg = _voice_excerpt(out)
            _log(f"summarised {len(text)} chars", player)
            return msg
        except Exception as e:
            return _unavailable(e, player)

    if action == "translate":
        if not text:
            msg = "Sir, what text should I translate?"
            _log(msg, player); return msg
        lang = target or "English"
        try:
            out = complete(f"Translate the following into {lang}. Output "
                           "ONLY the translation:\n\n" + text)
            msg = _voice_excerpt(out)
            _log(f"translated to {lang}", player)
            return msg
        except Exception as e:
            return _unavailable(e, player)

    if action == "status":
        msg = f"Sir, LLM brain: {status()}."
        _log(msg, player)
        return msg

    msg = ("Sir, the LLM brain can: generate long text, summarise text or "
           "a file, translate, or report status of the local LLM.")
    _log(msg, player)
    return msg


def _unavailable(e: Exception, player=None) -> str:
    msg = (f"Sir, no LLM answered: {e}. Check that Ollama (or LM Studio) "
           f"is running, or the Gemini key in settings.")
    _log(msg, player)
    return msg


def _log(message: str, player=None) -> None:
    print(f"[LlmBrain] {message}")
    if player:
        try:
            player.write_log(f"NEXUS: {message}")
        except Exception:
            pass


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "llm_brain",
    "description": (
        "Dedicated text LLM for heavy writing work, separate from the "
        "voice session. Long-form generation, summarising (text or file), "
        "and translation. Full output is saved to a file automatically and "
        "the spoken reply is a short excerpt. Also reports whether the "
        "local LLM (Ollama/LM Studio) or the Gemini cloud fallback is in "
        "use."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["generate", "summarize", "translate", "status"],
                "description": "generate: long text from a prompt; "
                               "summarize: text or file; translate: text "
                               "to target_language; status: LLM check"
            },
            "prompt": {
                "type": "STRING",
                "description": "For action=generate: what to write"
            },
            "text": {
                "type": "STRING",
                "description": "Text to summarise or translate"
            },
            "file_path": {
                "type": "STRING",
                "description": "Alternative to text: file to summarise"
            },
            "target_language": {
                "type": "STRING",
                "description": "For translate (default: English)"
            },
        },
        "required": ["action"]
    },
    "handler": llm_brain_action,
}
