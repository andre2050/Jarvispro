"""Push-to-talk, palavra de ativação, ditado, mudo e envio de texto.

Parte da janela principal (dividida de ui/main_window.py na 4.6.0 — sem mudança de comportamento)."""
from __future__ import annotations

from ._qt import *  # noqa: F401,F403
from ._base import C, FONT_MAIN  # noqa: F401
from . import quickbar as QB
from core.protecao import engolida as _engolida


class VozEntradaMixin:
    """Push-to-talk, palavra de ativação, ditado, mudo e envio de texto."""

    def _toggle_ptt(self):
        from memory.config_manager import (get_push_to_talk_enabled,
                                           save_push_to_talk_enabled)
        want = not get_push_to_talk_enabled()
        save_push_to_talk_enabled(want)
        scope = None
        if self.on_push_to_talk:
            try:
                scope = self.on_push_to_talk(want)
            except Exception as e:
                self._log.append_log(f"ERR: Falar segurando falhou — {e}")
                save_push_to_talk_enabled(False)
                want = False
        self._apply_ptt_shortcut(want and scope != "global")
        self._refresh_talk_btns()

    def _apply_ptt_shortcut(self, needed: bool):
        """Bind the chord inside the window when no global hook is available.

        On macOS and Linux there is no dependency-free way to read global key
        state, so the chord is at least live whenever this window has focus.
        Qt gives no key-release for a QShortcut, so a press latches the mic open
        and a short timer closes it; held down, auto-repeat keeps pushing that
        timer out, which behaves like holding a key.
        """
        from PyQt6.QtGui import QKeySequence, QShortcut
        from core.hotkey import qt_sequence

        if not needed:
            sc = getattr(self, "_ptt_sc", None)
            if sc is not None:
                sc.setEnabled(False)
                self._ptt_sc = None
            self._ptt_hold(False)
            return
        if getattr(self, "_ptt_sc", None) is not None:
            return

        self._ptt_release = QTimer(self)
        self._ptt_release.setSingleShot(True)
        self._ptt_release.setInterval(420)
        self._ptt_release.timeout.connect(lambda: self._ptt_hold(False))

        def _press():
            self._ptt_hold(True)
            self._ptt_release.start()

        self._ptt_sc = QShortcut(QKeySequence(qt_sequence()), self)
        self._ptt_sc.setAutoRepeat(True)
        self._ptt_sc.activated.connect(_press)

    def _ptt_hold(self, held: bool):
        """Report a windowed press/release to whoever owns the microphone."""
        cb = getattr(self, "ptt_hold", None)
        if cb:
            try:
                cb(bool(held))
            except Exception:
                _engolida("ui/main_window.py:2656")

    def _toggle_wake_word(self):
        st = self._wake_state()
        if not st["ready"]:
            # First time: download openwakeword + model in a worker thread.
            self._wake_btn.setText("⬇  BAIXANDO… (só uma vez)")
            self._wake_btn.setEnabled(False)
            def _work():
                try:
                    from core.wake_word import install_and_download
                    ok, msg = install_and_download(
                        logger=lambda m: self._log_sig.emit(f"SYS: {m}"))
                except Exception as e:
                    ok, msg = False, str(e)
                if ok and self.on_wake_toggle:
                    try:
                        self.on_wake_toggle(True)   # auto-enable after a successful download
                    except Exception:
                        _engolida("ui/main_window.py:2675")
                self._wake_dl_sig.emit(ok, msg)
            threading.Thread(target=_work, daemon=True).start()
            return
        # Already downloaded → just flip enabled/disabled through NexusLive.
        if self.on_wake_toggle:
            try:
                self.on_wake_toggle(not st["enabled"])
            except Exception:
                _engolida("ui/main_window.py:2684")
        self._refresh_wake_btns()

    def _on_wake_install_done(self, ok: bool, msg: str):
        self._log_sig.emit(f"SYS: {'Wake word ready.' if ok else 'Wake word setup failed: ' + msg}")
        self._refresh_wake_btns()

    def _tap_wake_manual(self):
        if self.on_wake_manual:
            try:
                self.on_wake_manual()
            except Exception:
                _engolida("ui/main_window.py:2696")
        self._refresh_wake_btns()

    def _update_brief_btn(self, enabled: bool):
        if not hasattr(self, '_brief_btn'):
            return
        if enabled:
            self._brief_btn.setText("☀  BRIEFING DA MANHÃ: LIGADO")
            self._brief_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #001a08; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 3px;
                    text-align: left; padding: 0 8px;
                }}
                QPushButton:hover {{ background: #002010; }}
            """)
        else:
            self._brief_btn.setText("☀  BRIEFING DA MANHÃ: DESLIGADO")
            self._brief_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 3px;
                    text-align: left; padding: 0 8px;
                }}
                QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
            """)

    def _do_interrupt(self):
        if self.on_interrupt:
            self.on_interrupt()

    def _toggle_mute(self):
        # A deliberate press settles the question: whatever the video did, or is
        # about to do, the user has now said what they want.
        self._video_auto_muted = False
        self._set_muted(not self._muted)

    def _set_muted(self, muted: bool, note: str = ""):
        muted = bool(muted)
        if muted == self._muted:
            return
        self._muted = muted
        self.hud.muted = muted
        self._style_mute_btn()
        if muted:
            self._apply_state("MUTED")
            self._log.append_log("SYS: Microfone desligado." + (f" {note}" if note else ""))
        else:
            self._apply_state("LISTENING")
            self._log.append_log("SYS: Microfone ligado." + (f" {note}" if note else ""))

    def _style_mute_btn(self):
        tecla = QB.nome_da_tecla(QB.tecla("shortcut_mute"))
        if self._muted:
            self._mute_btn.setText(f"🔇  Mudo  ·  {tecla}")
            self._mute_btn.setToolTip("O microfone está desligado. Clique para ligar.")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.MUTED_C};
                    border: 1px solid {C.MUTED_C}; border-radius: 16px;
                }}
            """)
        else:
            self._mute_btn.setText(f"🎙  Ouvindo  ·  {tecla}")
            self._mute_btn.setToolTip("O microfone está ligado. Clique para silenciar.")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C.PANEL2}; color: {C.GREEN};
                    border: 1px solid {C.BORDER}; border-radius: 16px;
                }}
                QPushButton:hover {{ border: 1px solid {C.GREEN}; }}
            """)

    def _send(self):
        txt = self._input.text().strip()
        if not txt: return
        self._input.clear()
        self._log.append_log(f"You: {txt}")
        try:
            from core import isa as _isa
            _isa.registrar("entrada", txt, "você digitou", origem="texto")
        except Exception:
            _engolida("ui/main_window.py:3389")
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(txt,), daemon=True).start()

    def _toggle_ditado(self) -> None:
        """Botão 🎙 Ditado / Ctrl+D: liga ou desliga o ditado."""
        if self.on_toggle_ditado:
            threading.Thread(target=self.on_toggle_ditado, daemon=True).start()
            return
        # Ainda conectando: o ditado funciona sem o Gemini pela caixa de comando,
        # mas pela voz precisa da sessão.
        self._log.append_log("SYS: 📝 O ditado fica disponível assim que o NEXUS terminar de conectar.")

    def _ditado_pill(self) -> QPushButton:
        pill = getattr(self, "_ditado_btn", None)
        if pill is None:
            pill = QPushButton(self.hud)
            pill.setObjectName("ditadoPill")
            pill.setCursor(Qt.CursorShape.PointingHandCursor)
            pill.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
            pill.setFixedHeight(30)
            pill.clicked.connect(self._toggle_ditado)
            pill.hide()
            self._ditado_btn = pill
            self.hud.installEventFilter(self)
        tecla = QB.nome_da_tecla(QB.tecla("shortcut_ditado"))
        pill.setText(f"●  DITANDO NO BLOCO DE NOTAS   ·   parar ({tecla})")
        pill.setToolTip("Tudo o que você fala vai para o Bloco de Notas.\n"
                        "Diga “parar ditado” ou clique aqui para terminar.\n"
                        "Durante o ditado: “vírgula”, “ponto final”, “nova linha”, "
                        "“novo parágrafo”, “apaga a última frase”.")
        pill.setStyleSheet(f"""
            QPushButton#ditadoPill {{
                background: {C.PANEL}; color: {C.MUTED_C};
                border: 1px solid {C.MUTED_C}; border-radius: 14px;
                padding: 0 18px;
            }}
            QPushButton#ditadoPill:hover {{ background: {C.PRI_GHO}; color: {C.WHITE}; }}
        """)
        pill.adjustSize()
        return pill

    def _place_ditado_pill(self) -> None:
        pill = getattr(self, "_ditado_btn", None)
        if pill is None or not pill.isVisible():
            return
        pill.adjustSize()
        pill.move(max(6, (self.hud.width() - pill.width()) // 2), 12)
        pill.raise_()

    def _on_ditado_mudou(self, ligado: bool) -> None:
        pill = self._ditado_pill()
        pill.setVisible(bool(ligado))
        self._ditando = bool(ligado)
        if ligado:
            self._place_ditado_pill()
        # o botão da barra rápida acompanha
        try:
            self._quickbar.set_active("ditado", bool(ligado))
        except Exception:
            _engolida("ui/main_window.py:3594")
