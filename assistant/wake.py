"""Wake word, sleep/wake and push-to-talk.

Mixin of NexusLive (assistant/core.py); methods moved verbatim from main.py."""
from __future__ import annotations

from .common import _MOTIVOS, WakeWordDetector, _P, asyncio, save_wake_word_enabled, time, wake_criar_detector, wake_criar_reserva, wake_frase, wake_install, wake_is_ready  # noqa: F401
from core.protecao import engolida as _engolida


class WakeMixin:
    # ── Wake word: state machine ─────────────────────────────────────────────

    def _wake_state(self) -> dict:
        # A loaded, running detector is definitively ready; otherwise fall back
        # to the cheap on-disk model-file check (no Model construction).
        ready = bool(self._wake_detector and self._wake_detector.ready) or wake_is_ready()
        return {"enabled": self._wake_enabled, "awake": self._awake, "ready": ready}

    def _ensure_wake_detector(self) -> bool:
        """Load the detector once (model loads on first start). Idempotent."""
        if self._wake_detector is None:
            try:
                _thr = min(0.9, max(0.2, float(_P.get("wake_sensitivity") or 0.5)))
            except (TypeError, ValueError):
                _thr = 0.5
            self._wake_detector = wake_criar_detector(
                on_detect=self._on_wake_detected,
                threshold=_thr,
                logger=lambda m: print(f"[Wake] {m}"),
                notify=lambda m: self.ui.write_log(f"SYS: {m}"),
            )
        if not self._wake_detector.ready:
            if self._wake_detector.start():
                return True
            # 1.5: o motor "Nexus" não subiu (ex.: sem rede para baixar o modelo
            # na primeira vez). Se o "Hey Jarvis" está pronto, usa ele.
            try:
                reserva = wake_criar_reserva(
                    self._on_wake_detected, 0.5,
                    lambda m: print(f"[Wake] {m}"),
                    lambda m: self.ui.write_log(f"SYS: {m}"))
                if reserva is not None and reserva.start():
                    self._wake_detector = reserva
                    self.ui.write_log("SYS: Usando o \"Hey Jarvis\" no lugar da palavra Nexus.")
                    return True
            except Exception as e:
                print(f"[Wake] reserva indisponível: {e}")
            return False
        return True

    def _on_wake_detected(self) -> None:
        """Called from the detector thread when the wake word is heard."""
        self.wake(reason="wake word")

    def wake(self, reason: str = "wake word") -> None:
        if self._awake:
            return
        self._awake = True
        self._last_user_speech = time.monotonic()   # start the auto-sleep clock now
        if not self.ui.muted:
            self.ui.set_state("LISTENING")
        self.ui.write_log(f"SYS: Acordado — {_MOTIVOS.get(reason, reason)}.")

    def sleep(self, reason: str = "timeout") -> None:
        if not self._awake:
            return
        self._awake = False
        self.set_speaking(False)
        self.ui.set_state("SLEEPING")
        self.ui.write_log(f"SYS: Dormindo — {_MOTIVOS.get(reason, reason)}. Diga {wake_frase()} para me acordar.")

    async def _run_sleep_watch(self) -> None:
        """Auto-sleep after the configured silence window (wake-word mode only)."""
        while True:
            await asyncio.sleep(5)
            if not self._wake_enabled or not self._awake:
                continue
            with self._speaking_lock:
                speaking = self._is_speaking
            if speaking:
                continue
            if (time.monotonic() - self._last_user_speech) > self._wake_sleep_timeout:
                self.sleep(reason="no speech for 2 minutes")

    # ── Wake word: UI callbacks (called from the Qt thread) ──────────────────

    def _ui_wake_toggle(self, enable: bool) -> str:
        """Enable/disable wake word from the settings UI. Returns a status token:
        'enabled' | 'disabled' | 'need_download'."""
        if enable:
            if not wake_is_ready():
                return "need_download"
            self._wake_enabled = True
            save_wake_word_enabled(True)
            self._ensure_wake_detector()
            self.sleep(reason="wake word enabled")
            return "enabled"
        else:
            self._wake_enabled = False
            save_wake_word_enabled(False)
            self.wake(reason="wake word disabled")
            return "disabled"

    def _ui_wake_manual(self) -> None:
        """Manual sleep/wake button in the UI."""
        if not self._wake_enabled:
            return
        if self._awake:
            self.sleep(reason="you tapped sleep")
        else:
            self.wake(reason="you tapped wake")

    def _ui_wake_install(self) -> tuple[bool, str]:
        """Download openwakeword + the model (runs in a UI worker thread)."""
        # Triggered by the user pressing the button, so its progress is exactly
        # what they are waiting to see.
        return wake_install(logger=lambda m: print(f"[Wake] {m}"),
                            notify=lambda m: self.ui.write_log(f"SYS: {m}"))

    def set_push_to_talk(self, enabled: bool) -> str:
        """Turn hold-to-talk on or off. Returns the scope actually achieved."""
        from core.hotkey import PushToTalk

        self._ptt_enabled = bool(enabled)
        self._ptt_held = False
        if not enabled:
            if self._ptt is not None:
                self._ptt.stop()
                self._ptt = None
            return "off"

        if self._ptt is None:
            self._ptt = PushToTalk(self._on_ptt)
        scope = self._ptt.start()
        # A window-scoped chord is a real limitation, not a detail — say it once
        # in the log so nobody wonders why it does nothing while another app is
        # focused. Reporting it must never be able to undo the thing it reports.
        try:
            self.ui.write_log(
                f"SYS: Falar segurando ligado — segure {self._ptt.label}"
                + ("." if scope == "global"
                   else " (funciona com esta janela em primeiro plano)."))
        except Exception:
            _engolida("assistant/wake.py:143")
        return scope

    def _on_ptt(self, held: bool) -> None:
        """Chord pressed or released — may arrive on the hotkey thread."""
        self._ptt_held = held
        if held:
            # Holding the key is also a way to wake it, so push-to-talk works
            # without having to say the wake word first.
            if self._wake_enabled and not self._awake:
                self._awake = True
                self._last_user_speech = time.monotonic()
        try:
            self.ui.set_state("LISTENING" if held else "SLEEPING")
        except Exception:
            _engolida("assistant/wake.py:158")
