"""Barra rápida, atalhos de teclado, licença e primeira configuração.

Parte da janela principal (dividida de ui/main_window.py na 4.6.0 — sem mudança de comportamento)."""
from __future__ import annotations

from ._qt import *  # noqa: F401,F403
from ._base import API_FILE, CONFIG_DIR, _read_full_config  # noqa: F401
from .overlays.setup import SetupOverlay  # noqa: F401
from .overlays.licenca import LicencaOverlay  # noqa: F401
from . import quickbar as QB
from core.protecao import engolida as _engolida


class LicencaAtalhosMixin:
    """Barra rápida, atalhos de teclado, licença e primeira configuração."""

    def _open_quickbar_editor(self) -> None:
        from .overlays.quickbar_editor import QuickBarOverlay
        old = getattr(self, "_qb_overlay", None)
        if old is not None:
            try:
                old.hide(); old.deleteLater()
            except RuntimeError:
                pass
        ov = QuickBarOverlay(on_saved=self._rebuild_quickbar, parent=self.centralWidget())
        self._centre_overlay(ov)
        self._qb_overlay = ov

    def _open_shortcuts_panel(self) -> None:
        from .overlays.quickbar_editor import ShortcutsOverlay
        old = getattr(self, "_sc_overlay", None)
        if old is not None:
            try:
                old.hide(); old.deleteLater()
            except RuntimeError:
                pass
        ov = ShortcutsOverlay(on_saved=self._reload_shortcuts, parent=self.centralWidget())
        self._centre_overlay(ov)
        self._sc_overlay = ov

    def _quick_items(self) -> list[dict]:
        items = []
        for chave in QB.barra_atual():
            icone, nome, metodo, dica = QB.FERRAMENTAS[chave]
            fn = getattr(self, metodo, None)
            if fn is None:
                continue
            items.append({"icon": icone, "label": nome, "tooltip": dica, "callback": fn, "id": chave})
        for c in QB.comandos_atuais():
            items.append({"icon": "⚡", "label": c["label"], "kind": "command",
                          "tooltip": f"Pede ao NEXUS: “{c['command']}”",
                          "callback": (lambda cmd=c["command"]: self._quick_command(cmd))})
        for i, it in enumerate(items[:9], start=1):
            it["tooltip"] = f"{it['tooltip']}   (Alt+{i})"
        return items

    def _rebuild_quickbar(self) -> None:
        self._quick_list = self._quick_items()
        self._quickbar.build(self._quick_list)
        if getattr(self, "_ditando", False):
            self._quickbar.set_active("ditado", True)

    def _quick_command(self, cmd: str) -> None:
        self._log.append_log(f"You: {cmd}")
        try:
            from core import isa as _isa
            _isa.registrar("entrada", cmd, "comando rápido", origem="barra rápida")
        except Exception:
            _engolida("ui/main_window.py:3648")
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(cmd,), daemon=True).start()

    def _run_quick(self, n: int) -> None:
        items = getattr(self, "_quick_list", [])
        if 0 <= n < len(items):
            items[n]["callback"]()

    def _install_shortcuts(self) -> None:
        for sc in getattr(self, "_shortcuts", []):
            sc.setEnabled(False)
            sc.deleteLater()
        self._shortcuts = []
        for chave, _rotulo, padrao, metodo in QB.ATALHOS:
            fn = getattr(self, metodo, None)
            seq = QKeySequence(QB.tecla(chave) or padrao)
            if fn is None or seq.isEmpty():
                continue
            sc = QShortcut(seq, self)
            sc.activated.connect(fn)
            self._shortcuts.append(sc)
        for i in range(9):
            sc = QShortcut(QKeySequence(f"Alt+{i + 1}"), self)
            sc.activated.connect(lambda n=i: self._run_quick(n))
            self._shortcuts.append(sc)
        self._refresh_shortcut_labels()

    def _reload_shortcuts(self) -> None:
        self._install_shortcuts()
        self._rebuild_quickbar()
        self._log.append_log("SYS: ⌨ Atalhos atualizados.")

    def _refresh_shortcut_labels(self) -> None:
        k = lambda chave: QB.nome_da_tecla(QB.tecla(chave))
        if hasattr(self, "_interrupt_btn"):
            self._interrupt_btn.setText(f"✋  Interromper  ·  {k('shortcut_interrupt')}")
        if hasattr(self, "_mute_btn") and hasattr(self, "_muted"):
            self._style_mute_btn()
        if hasattr(self, "_fs_btn"):
            self._fs_btn.setText(f"⛶  TELA CHEIA  [{k('shortcut_fullscreen')}]")
        if hasattr(self, "_footer_keys"):
            self._footer_keys.setText(
                f"[{k('shortcut_mute')}] Microfone   ·   [{k('shortcut_fullscreen')}] Tela cheia   ·   "
                f"[{k('shortcut_agenda')}] Notas   ·   [{k('shortcut_commands')}] Comandos")
        if hasattr(self, "_input"):
            self._input.setToolTip(f"Digite e aperte Enter. Atalho para vir aqui: {k('shortcut_command')}")

    def _check_config(self) -> bool:
        if not API_FILE.exists(): return False
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8"))
            return bool(d.get("gemini_api_key")) and bool(d.get("os_system"))
        except Exception:
            return False

    @staticmethod
    def _license_check() -> dict:
        """Estado da licença. Se o módulo faltar ou quebrar, NÃO libera: erro vira bloqueio."""
        try:
            from core import licenca
            return licenca.status()
        except Exception as e:
            return {"valida": False, "motivo": f"Não foi possível conferir a licença ({e}).",
                    "nome": "", "ate": "", "dias": None}

    def _show_license(self, motivo: str = ""):
        try:
            self._show_license_overlay(motivo)
        except Exception as e:  # nunca deixar o NEXUS "mudo": sem tela, sem como ativar
            print(f"[Licença] tela de ativação falhou ({e}); usando a caixa simples.")
            self._license_fallback_dialog(motivo)

    def _license_fallback_dialog(self, motivo: str = ""):
        from PyQt6.QtWidgets import QInputDialog
        from core import licenca
        texto = ((motivo + "\n\n") if motivo and "Nenhuma" not in motivo else "") + \
            f"ID deste computador: {licenca.id_da_maquina()}\n\nCole a chave de licença:"
        while True:
            chave, ok = QInputDialog.getMultiLineText(self, "Ativar o NEXUS Ultra 2026", texto)
            if not ok:
                self._quit_unlicensed()
                return
            ativou, msg = licenca.ativar(chave)
            if ativou:
                self._on_license_ok()
                return
            texto = msg + "\n\nID deste computador: " + licenca.id_da_maquina() + "\n\nCole a chave de licença:"

    def _recentrar_licenca(self):
        """Centraliza a tela de ativação (cabe em janela pequena também)."""
        lic = getattr(self, "_license_overlay", None)
        if lic is None:
            return
        cw = self.centralWidget()
        ow = min(520, max(320, cw.width() - 20))
        oh = min(470, max(380, cw.height() - 20))
        lic.setGeometry(max(0, (cw.width() - ow) // 2), max(0, (cw.height() - oh) // 2), ow, oh)

    def _show_license_overlay(self, motivo: str = ""):
        ov = LicencaOverlay(motivo, self.centralWidget())
        ov.ativada.connect(self._on_license_ok)
        ov.sair.connect(self._quit_unlicensed)
        self._license_overlay = ov
        self._recentrar_licenca()
        ov.show()
        ov.raise_()
        # o tamanho real do centro só existe depois que a janela aparece e o
        # layout assenta: recentra logo depois (e de novo, por segurança)
        QTimer.singleShot(0, self._recentrar_licenca)
        QTimer.singleShot(250, self._recentrar_licenca)

    def _quit_unlicensed(self):
        self._really_quit = True
        if self._tray is not None:
            self._tray.hide()
        self.close()
        QApplication.quit()

    def _on_license_ok(self):
        self._licensed = True
        ov = getattr(self, "_license_overlay", None)
        if ov is not None:
            ov.hide()
            ov.deleteLater()
            self._license_overlay = None
        if self._check_config():
            self._ready = True
            self._apply_state("LISTENING")
            self._assistant_name = _read_full_config().get("assistant_name", "NEXUS") or "NEXUS"
            self._log.append_log(f"SYS: Licença ativada. {self._assistant_name} online.")
        else:
            self._show_setup()

    def _show_setup(self):
        ov = SetupOverlay(self.centralWidget())
        cw = self.centralWidget()
        ow, oh = 460, 390
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.done.connect(self._on_setup_done)
        ov.show()
        self._overlay = ov

    def _on_setup_done(self, key: str, os_name: str):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        API_FILE.write_text(
            json.dumps({"gemini_api_key": key, "os_system": os_name}, indent=4),
            encoding="utf-8",
        )
        self._ready = True
        if self._overlay:
            self._overlay.hide()
            self._overlay = None
        self._apply_state("LISTENING")
        self._assistant_name = _read_full_config().get("assistant_name", "NEXUS") or "NEXUS"
        self._log.append_log(f"SYS: Pronto. Sistema: {os_name.upper()}. {self._assistant_name} online.")
