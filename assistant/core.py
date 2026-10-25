"""The assistant itself: NexusLive = every mixin + __init__ (was the class in main.py)."""
from __future__ import annotations

from .common import EchoGuard, NexusUI, Path, ProactiveEngine, SystemMonitor, WakeWordDetector, _P, asyncio, discover_actions, discover_plugins, get_push_to_talk_enabled, get_wake_word_enabled, sys, threading, time, wake_is_ready  # noqa: F401
from .tool_declarations import TOOL_DECLARATIONS  # noqa: F401
from .wake import WakeMixin
from .typed import TypedCommandsMixin
from .audio import AudioMixin
from .session import SessionMixin
from .tools import ToolsMixin
from .background import BackgroundMixin
from .dictation import DictationMixin
from .motor_proprio import MotorProprioMixin


class NexusLive(WakeMixin, TypedCommandsMixin, AudioMixin, SessionMixin, ToolsMixin, BackgroundMixin,
                 DictationMixin, MotorProprioMixin):
    def __init__(self, ui: NexusUI):
        self.ui             = ui

        # ── System update check (local, instant, no network) ───────────────
        # Announces the running version, and if a newer package is sitting
        # in updates/ it says so in the log so the user can just ask to apply.
        try:
            from actions.system_update import current_version, startup_check
            _ver = current_version().get("version", "?")
            ui.write_log(f"SYS: NEXUS Ultra 2026 v{_ver} — desenvolvido por André Luiz Lima Menezes. "
                         f"Verificação de atualizações ligada.")
            _upd = startup_check()
            if _upd:
                ui.write_log(f"SYS: {_upd}")
        except Exception as _e:
            ui.write_log(f"SYS: Verificação de atualizações indisponível — {_e}")
        self._asst_name     = "NEXUS"        # updated each session from config
        self.session              = None
        self.audio_in_queue       = None
        self.out_queue            = None
        self._loop                     = None
        self._is_speaking         = False
        self._speaking_lock       = threading.Lock()
        self._phone_active        = False   # True while phone mic is streaming; pauses PC mic
        self._pending_vision       = None    # (img_bytes, mime_type, question, angle) to inject after tool response
        self._vision_cam_active    = False   # True if camera was opened for vision → auto-close after response
        self._vision_close_pending = False   # True after vision injected; next turn_complete closes camera
        self._vision_last_time     = 0.0     # monotonic time of last screen_process call (cooldown guard)
        self._vision_busy          = False   # True while a vision capture/inject cycle is in flight
        self._interrupted          = False   # True while draining audio after user interrupt
        # Transcript-driven mouth shapes for the avatar. Fed from the receive
        # loop as words arrive, drained by the playback loop against the audio.
        self._last_out_logged      = ""      # de-dupes a re-sent transcript tail
        # Push-to-talk
        self._ptt_enabled          = False
        self._ptt_held             = False
        self._ptt                  = None    # core.hotkey.PushToTalk
        self._out_level            = 0.0     # level of the audio being played right now
        self._echo                 = EchoGuard()
        # `stream.write()` returns when the buffer accepts the audio, not when the
        # speaker has finished with it, so sound is still in the room after the
        # speaking flag drops. Streaming the microphone during that gap is how an
        # assistant ends up answering itself. Measured from the device rather than
        # guessed; see _play_audio.
        self._out_latency          = 0.20    # seconds, replaced with the real value
        self._tail_until           = 0.0     # monotonic time the echo tail expires
        # Wall-clock time at which the audio written next will begin to sound.
        # The mouth is scheduled against this, never against "now": batches are
        # handed to the device far faster than they play, so "now" ran the lips
        # ahead of the words and cut every schedule short. 0 = nothing playing.
        self._play_cursor          = 0.0
        self.ui.on_push_to_talk   = self.set_push_to_talk
        self.ui.ptt_hold          = self._on_ptt
        self.ui.on_text_command   = self._on_text_command
        self.ui.on_remote_clicked = self._make_remote_key
        self.ui.on_interrupt      = self.interrupt
        self.ui.on_voice_change   = self._on_voice_change     # voice picker → rebuild session
        self.ui.on_audio_device_change = self._on_audio_device_change
        try:   # 1.4.3 — mudar a velocidade da resposta vale na hora
            self.ui._win.on_live_settings_change = (
                lambda motivo="speed": self.request_reconnect(keep_context=True, reason=motivo))
        except Exception:
            pass
        self._reconnect_event: asyncio.Event | None = None
        self._reconnect_keep = True   # False → next rebuild drops the resumption handle

        # ── Session resumption ─────────────────────────────────────────
        # The server issues a resumption handle every few seconds and reissues
        # it as the conversation moves on. Before this, session_resumption was
        # switched ON in the config and the update was never read, so the handle
        # was thrown away and EVERY reconnect — a dropped packet, a voice change,
        # switching microphone — started an empty session. "Unlimited sessions"
        # leaked through exactly this hole.
        #
        # Deliberately in RAM only, never written to disk. Persisting it would
        # make a fresh launch continue yesterday's conversation, which sounds
        # appealing but breaks the session-summary flow: _save_session_summary
        # runs at shutdown and the morning briefing pops it the next day. A
        # conversation that never ends never produces a summary, and the
        # "yesterday we talked about…" line silently disappears.
        self._resume_handle: str | None = None
        self._turn_done_event: asyncio.Event | None = None
        self._dashboard     = None
        self._briefing_sent    = False          # morning briefing fires once per process
        self._sys_monitor      = SystemMonitor()  # persistent cooldown state
        self._proactive        = ProactiveEngine()
        self._last_user_speech = time.monotonic()  # updated on every user utterance
        self._session_log: list[str] = []          # conversation turns for end-of-session summary

        self._enhanced_live = True  # proactive audio; auto-disabled if the server rejects it
        self._tuned_live    = True  # turn-taking / media / thinking knobs; same fallback

        _base_dir = Path(__file__).resolve().parents[1]
        _inline_names = {t["name"] for t in TOOL_DECLARATIONS}

        # File-backed tools: every actions/*.py with a TOOL dict, discovered the
        # same way plugins are. Reserved names = the inline tools above, so an
        # action can never shadow one.
        self._action_registry = discover_actions(
            actions_dir=_base_dir / "actions",
            reserved_names=_inline_names,
            logger=lambda msg: print(f"[Actions] {msg}"),
        )

        # Routines run other actions, so they need the registry that was just
        # built. Without this call every "run" answered "routines aren't ready
        # yet" and nothing opened. The loader registered the module under
        # "actions.smart_routines", so this is the same instance it discovered.
        try:
            _routines_mod = sys.modules.get("actions.smart_routines")
            if _routines_mod is not None:
                _routines_mod.bind(self._action_registry)
        except Exception as e:
            print(f"[Routines] ⚠️ could not bind the action registry: {e}")
        try:   # 1.5 — 🧩 o modo agente usa as mesmas ferramentas
            _agente = sys.modules.get("actions.agent_task")
            if _agente is not None:
                _agente.bind(self._action_registry)
        except Exception as e:
            print(f"[Agente] ⚠️ could not bind the action registry: {e}")
        try:   # 2.5 — 🤝 o orquestrador de agentes usa as mesmas ferramentas
            _orq = sys.modules.get("actions.orquestrador")
            if _orq is not None:
                _orq.bind(self._action_registry)
        except Exception as e:
            print(f"[Orquestrador] ⚠️ could not bind the action registry: {e}")

        # Local neural network for typed commands (core/intent_net.py). It
        # loads its saved model, or trains in the background on first run —
        # never blocks the start. Anything it is unsure about goes to Gemini.
        self._last_typed: tuple[str, float] | None = None
        try:
            from core.intent_net import brain as _brain
            _brain._log = lambda m: print(m)
            _brain.start()
        except Exception as e:
            print(f"[IntentNet] ⚠️ unavailable: {e}")

        # Plugins must not collide with either an inline tool or a discovered action.
        _core_names = _inline_names | self._action_registry.names()
        self._plugin_registry = discover_plugins(
            plugins_dir=_base_dir / "plugins",
            core_tool_names=_core_names,
            # Console gets the full boot transcript; the activity log gets only
            # what the user has to know about. Every plugin loading correctly is
            # the expected case and does not belong in their conversation.
            logger=lambda msg: print(f"[Plugins] {msg}"),
            notify=lambda msg: self.ui.write_log(f"SYS: {msg}"),
        )
        self.ui.get_plugins = self._plugin_registry.list_for_ui
        try:   # I.S.A.: o que a metade "automação" tem disponível
            from core import isa as _isa
            _isa.definir("funcoes", len(self._action_registry.names()))
            _isa.definir("plugins", sum(1 for _p in self._plugin_registry.list_for_ui()
                                        if _p.get("valid") and _p.get("enabled")))
            _isa.definir("conexao", "conectando")
            _isa.registrar("sistema", "Núcleo I.S.A. iniciado",
                           f"{len(self._action_registry.names())} funções prontas", origem="sistema")
        except Exception:
            pass
        self.ui.get_plugin_settings = self._plugin_registry.settings_schemas  # ⚙ settings tab
        self.ui.request_say = self.plugin_say   # plugins: mid-task speech channel

        # ── Wake word ────────────────────────────────────────────────────────
        # _awake gates the mic (see _listen_audio) and the background speakers.
        # It is True whenever wake word is OFF, so default behaviour is unchanged.
        self._wake_enabled     = get_wake_word_enabled()
        self._awake            = not self._wake_enabled
        self._wake_detector: WakeWordDetector | None = None
        self._wake_sleep_timeout = float(_P.get("sleep_after_minutes") or 2) * 60

        # Restore the saved push-to-talk preference. Doing it here rather than
        # in __init__ means the hotkey thread only exists once there is a
        # session to talk to.
        if get_push_to_talk_enabled():
            try:
                self.set_push_to_talk(True)
            except Exception as e:
                print(f"[NEXUS] ⚠ Push-to-talk unavailable: {e}")
        # UI control surface for the Wake Word settings section.
        self.ui.wake_is_ready    = wake_is_ready          # () -> bool
        self.ui.wake_get_state   = self._wake_state       # () -> dict
        self.ui.on_wake_toggle   = self._ui_wake_toggle   # (enable: bool) -> str
        self.ui.on_wake_manual   = self._ui_wake_manual   # () -> toggle awake/asleep
        self.ui.on_wake_install  = self._ui_wake_install  # () -> (ok, msg)

        # 1.4 — Bloco de Notas: modo ditado (assistant/dictation.py)
        self._setup_dictation()

