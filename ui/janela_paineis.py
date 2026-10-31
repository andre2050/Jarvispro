"""Abertura dos painéis e sobreposições (ajustes, notas, agenda, IA, plugins…).

Parte da janela principal (dividida de ui/main_window.py na 4.6.0 — sem mudança de comportamento)."""
from __future__ import annotations

from ._qt import *  # noqa: F401,F403
from ._base import API_FILE, APP_VERSION, C, DEFAULT_UI_COLOR, _read_full_config, aplicar_tema_automatico, apply_ui_accent, current_palette, retheme_all_widgets  # noqa: F401
from .overlays.customize import CustomizeOverlay  # noqa: F401
from .overlays.panels import AudioDeviceOverlay, ConfirmBanner, MemoryOverlay, PluginManagerOverlay  # noqa: F401
from .overlays.remote import PluginSettingsOverlay  # noqa: F401
from .overlays.settings import SettingsPanelOverlay  # noqa: F401
from .overlays.tools import ClipOverlay, CommandsOverlay, IntelOverlay, NotesOverlay, VisionOverlay  # noqa: F401
from core.protecao import engolida as _engolida


class PaineisMixin:
    """Abertura dos painéis e sobreposições (ajustes, notas, agenda, IA, plugins…)."""

    def _pick_setup_option(self, tab: str):
        """Escolher uma opção do menu SETUP fecha o menu e abre a seção.
        CONFIGURAÇÃO DO USUÁRIO abre direto a janela do usuário (a única)."""
        self._close_setup()
        if tab == "usuario":
            self._open_preferences()
            return
        if tab == "barra":
            self._open_quickbar_editor()
            return
        if tab == "atalhos":
            self._open_shortcuts_panel()
            return
        self._open_settings_panel(tab)

    def _open_settings_panel(self, tab: str = "status"):
        """Painel de Configurações: status, atuador, backup, reset, sobre etc.
        Os itens que já têm painel próprio abrem o painel existente."""
        if getattr(self, "_settings_overlay", None):
            self._settings_overlay.hide()
        try:
            plugins = self.get_plugins() if self.get_plugins else []
            count = len(plugins)
        except Exception:
            count = None
        cw = self.centralWidget()
        ov = SettingsPanelOverlay(
            actions={
                "customise": self._open_customize,
                "preferences": self._open_preferences,
                "commands": self._open_commands_panel,
                "add_command": lambda: self._open_commands_panel(adicionar=True),
                "plugins": self._open_plugin_manager,
                "plugin_settings": self._open_plugin_settings,
                "vision": self._open_vision_panel,
                "intel": self._open_intel_panel,
                "clip": self._open_clip_panel,
                "memory": self._open_memory_panel,
                "audio": self._open_audio_devices,
                "ptt": self._toggle_ptt,
                "log": self._open_activity_log,
                "remote": self._open_remote,
                "shortcut": self._create_desktop_shortcut,
                "autostart": self._toggle_autostart,
                "autostart_state": self._check_autostart,
                "update": self._update_system,
                "agenda": self._open_agenda,
                "isa": self._open_isa_panel,
                "quickbar_saved": self._rebuild_quickbar,
                "shortcuts_saved": self._reload_shortcuts,
            },
            plugin_count=count,
            parent=cw,
            start=tab,
        )
        ov.setFixedHeight(min(640, cw.height() - 16))
        self._centre_overlay(ov)
        ov.show()
        ov.raise_()
        self._settings_overlay = ov

    def _open_preferences(self):
        from core import preferences as _P
        if _P.password_set():
            from PyQt6.QtWidgets import QInputDialog, QLineEdit
            pw, ok = QInputDialog.getText(self, "Painel protegido", "Senha do painel:",
                                          QLineEdit.EchoMode.Password)
            if not ok or not _P.check_password(pw):
                self._log.append_log("SYS: Senha do painel incorreta.")
                return
        from .overlays.user_settings import PreferencesOverlay
        if getattr(self, "_prefs_overlay", None):
            self._prefs_overlay.hide()
        if self._customize_overlay:
            self._customize_overlay.hide()
        cw = self.centralWidget()
        ov = PreferencesOverlay(parent=cw,
                                assistant_section=self._make_customize(embedded=True))
        self._centre_overlay(ov)
        self._prefs_overlay = ov

    def _open_customize(self):
        """Personalizar e Preferências viraram UMA janela (Configuração do
        usuário). Quem chamava a personalização cai nela também."""
        self._open_preferences()

    def _make_customize(self, embedded: bool = False, parent=None) -> "CustomizeOverlay":
        """The name / voice / colour / formality / language / quiet-hours block,
        filled from config and wired to save — floating or embedded."""
        cfg = _read_full_config()
        try:
            from memory.config_manager import (get_formality, get_language,
                                               get_quiet_hours)
            _formality = get_formality()
            _language  = get_language()
            _quiet     = get_quiet_hours() or {
                "enabled": False, "start": "22:00", "end": "07:00"}
        except Exception:
            _formality = "casual"
            _language  = "auto"
            _quiet     = {"enabled": False, "start": "22:00", "end": "07:00"}
        ov = CustomizeOverlay(
            cfg.get("assistant_name", "NEXUS") or "NEXUS",
            cfg.get("user_name", ""),
            cfg.get("ui_color", "") or DEFAULT_UI_COLOR,
            cfg.get("voice_name", ""),
            formality=_formality,
            language=_language,
            quiet_hours=_quiet,
            parent=parent,
            embedded=embedded,
        )
        ov.on_preview = self._preview_ui_color
        ov.on_hud_style = self._set_hud_style
        ov.saved.connect(self._apply_name_update)
        return ov

    def _open_customize_floating(self):
        """The old standalone window — kept only in case a plugin calls it."""
        if self._customize_overlay:
            self._customize_overlay.hide()
        cw = self.centralWidget()
        ov = self._make_customize(embedded=False, parent=cw)
        ow, oh = CustomizeOverlay._OW, CustomizeOverlay._OH
        oh = min(oh, cw.height() - 16)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.show()
        self._customize_overlay = ov

    def _tick_tema_auto(self):
        """A cada minuto: se o tema automático está ligado, acompanha a hora e o humor (sem gravar nada)."""
        self._tema_auto_cor = aplicar_tema_automatico(getattr(self, "_tema_auto_cor", None))

    def _preview_ui_color(self, hex_color: str):
        """Live preview — paints the whole interface the new colour (does NOT write to config)."""
        old = current_palette()
        if apply_ui_accent(hex_color):
            retheme_all_widgets(old, current_palette())

    def _apply_name_update(self, name: str, user_name: str, ui_color: str = "",
                           voice: str = "", formality: str = "casual",
                           language: str = "auto", quiet_hours: dict = None):
        """Update all name/theme-dependent UI elements and persist to config."""
        self._assistant_name = name.strip() or "NEXUS"
        display = self._assistant_name.upper()
        self.setWindowTitle(f"{display} — {APP_VERSION} — desenvolvido por André Luiz Lima Menezes")
        self._title_lbl.setText(display)
        if hasattr(self, "_pro_lbl"):
            self._pro_lbl.setVisible(display == "NEXUS")
        self._sub_lbl.setText("ASSISTENTE PESSOAL INTELIGENTE" if display == "NEXUS"
                              else "Assistente pessoal")
        self._log._ai_name_lc = self._assistant_name.lower()
        self.hud._assistant_name = display

        color_changed = False
        if ui_color:
            old = current_palette()
            if apply_ui_accent(ui_color):
                # Live-paint the whole interface (panels, buttons, borders, HUD)
                retheme_all_widgets(old, current_palette())
                color_changed = old["PRI"] != C.PRI

        # Voice change → persist and, if it actually changed, rebuild the Live
        # session so the new voice takes effect (it's fixed at connect time).
        voice_changed = False
        if voice:
            from memory.config_manager import get_voice, save_voice
            if voice != get_voice():
                save_voice(voice)
                voice_changed = True

        try:
            data = _read_full_config()
            data["assistant_name"] = self._assistant_name
            data["user_name"] = user_name.strip()
            if ui_color:
                data["ui_color"] = ui_color.strip().lower()
            API_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")
            self._log.append_log(f"SYS: Identidade atualizada — {display}")
            if color_changed:
                self._log.append_log(f"SYS: Cor aplicada — {ui_color}")
            if voice_changed:
                self._log.append_log(f"SYS: Voice set — {voice}")
        except Exception as e:
            self._log.append_log(f"ERR: Não consegui salvar a configuração — {e}")

        # Formality + quiet hours — persist; formality changes the prompt,
        # so it needs a session rebuild exactly like a voice change.
        formality_changed = False
        try:
            from memory.config_manager import (get_formality, get_language,
                                               save_formality, save_language,
                                               save_quiet_hours)
            formality = formality if formality in ("formal", "casual") else "casual"
            if formality != get_formality():
                save_formality(formality)
                formality_changed = True
                self._log.append_log(f"SYS: Tratamento — {formality}")
            language = language if language in ("auto", "pt", "en") else "auto"
            if language != get_language():
                save_language(language)
                formality_changed = True          # same rebuild trigger
                self._log.append_log(f"SYS: Idioma das respostas — {language}")
            qh = quiet_hours or {}
            save_quiet_hours(bool(qh.get("enabled")),
                             str(qh.get("start", "22:00")),
                             str(qh.get("end", "07:00")))
            if qh.get("enabled"):
                self._log.append_log(
                    f"SYS: Horário de silêncio {qh.get('start')} → {qh.get('end')}")
            else:
                self._log.append_log("SYS: Horário de silêncio desligado")
        except Exception as e:
            self._log.append_log(f"ERR: Não consegui salvar o tratamento ou o horário de silêncio — {e}")

        if (voice_changed or formality_changed) and self.on_voice_change:
            self.on_voice_change()

    def _centre_overlay(self, ov) -> None:
        """Place a floating overlay in the middle of the HUD and show it."""
        cw = self.centralWidget()
        ov.adjustSize()
        ov.setGeometry(
            max(0, (cw.width()  - ov.width())  // 2),
            max(0, (cw.height() - ov.height()) // 2),
            ov.width(), ov.height(),
        )
        ov.show()
        ov.raise_()

    def _open_audio_devices(self):
        ov = AudioDeviceOverlay(parent=self.centralWidget())
        ov.picked.connect(self._on_audio_devices_applied)
        self._centre_overlay(ov)
        self._audio_overlay = ov            # keep a reference so it isn't GC'd

    def _on_audio_devices_applied(self):
        self._log.append_log("SYS: Dispositivos de áudio atualizados.")
        if self.on_audio_device_change:
            self.on_audio_device_change()

    def _open_clip_panel(self):
        try:
            # start monitoring on first open (and only once)
            if not getattr(self, "_clip_hooked", False):
                QApplication.clipboard().dataChanged.connect(
                    self._on_clipboard_change)
                self._clip_hooked = True
            ov = ClipOverlay(parent=self.centralWidget(), log=self.write_log,
                             history=self._clip_history)
            ov._copy_back = self._clip_copy_back(ov)
            self._centre_overlay(ov)
            self._clip_overlay = ov
        except Exception as e:
            msg = f"A área de transferência não abriu — {e}"
            print(f"[UI] {msg}")
            try:
                self.write_log(f"SYS: {msg}")
            except Exception:
                _engolida("ui/main_window.py:3172")

    def _clip_copy_back(self, ov):
        """Wrap ClipOverlay._copy_back so our own copies don't re-enter
        the history."""
        orig = ov._copy_back
        def _guarded(text):
            self._clip_self = True
            try:
                orig(text)
            except Exception:
                self._clip_self = False
        return _guarded

    def _open_notes_panel(self):
        # 1.2: o painel antigo de notas virou a central de Notas e Lembretes
        self._open_agenda()

    def _open_notes_panel_antigo(self):
        try:
            ov = NotesOverlay(parent=self.centralWidget(), log=self.write_log)
            self._centre_overlay(ov)
            self._notes_overlay = ov
        except Exception as e:
            msg = f"O painel de notas não abriu — {e}"
            print(f"[UI] {msg}")
            try:
                self.write_log(f"SYS: {msg}")
            except Exception:
                _engolida("ui/main_window.py:3201")

    def _open_intel_panel(self):
        try:
            ov = IntelOverlay(parent=self.centralWidget(), log=self.write_log)
            self._centre_overlay(ov)
            self._intel_overlay = ov
        except Exception as e:
            msg = f"O painel de sistema não abriu — {e}"
            print(f"[UI] {msg}")
            try:
                self.write_log(f"SYS: {msg}")
            except Exception:
                _engolida("ui/main_window.py:3214")

    def _open_commands_panel(self, adicionar: bool = False):
        try:
            ov = CommandsOverlay(parent=self.centralWidget(), adicionar=adicionar)
            self._centre_overlay(ov)
            self._commands_overlay = ov
        except Exception as e:
            msg = f"A lista de comandos não abriu — {e}"
            print(f"[UI] {msg}")
            try:
                self.write_log(f"SYS: {msg}")
            except Exception:
                _engolida("ui/main_window.py:3227")

    def _open_vision_panel(self):
        # PyQt6 encerra o app em exceção não tratada dentro de um slot —
        # qualquer falha aqui precisa virar mensagem no log, não crash.
        try:
            ov = VisionOverlay(parent=self.centralWidget(), log=self.write_log)
            self._centre_overlay(ov)
            self._vision_overlay = ov
        except Exception as e:
            msg = f"O painel de visão não abriu — {e}"
            print(f"[UI] {msg}")
            try:
                self.write_log(f"SYS: {msg}")
            except Exception:
                _engolida("ui/main_window.py:3242")

    def _open_memory_panel(self):
        ov = MemoryOverlay(parent=self.centralWidget())
        self._centre_overlay(ov)
        self._memory_overlay = ov

    def _show_confirm_banner(self, title: str, detail: str):
        self._hide_confirm_banner()
        ov = ConfirmBanner(title, detail, parent=self.centralWidget())
        ov.answered.connect(self._on_confirm_answered)
        self._centre_overlay(ov)
        self._confirm_overlay = ov

    def _hide_confirm_banner(self):
        ov = getattr(self, "_confirm_overlay", None)
        if ov is not None:
            ov.hide()
            ov.deleteLater()
            self._confirm_overlay = None

    def _on_confirm_answered(self, accepted: bool):
        # Tear the banner down first: core.confirm.resolve() may be about to
        # shut the machine down, and a live widget mid-callback is not where you
        # want to be when that happens.
        self._hide_confirm_banner()
        try:
            from core.confirm import resolve
            resolve(bool(accepted))
        except Exception as e:
            self._log.append_log(f"ERR: A confirmação falhou — {e}")

    def _open_plugin_manager(self):
        plugins = self.get_plugins() if self.get_plugins else []
        cw = self.centralWidget()
        ov = PluginManagerOverlay(plugins, parent=cw)
        ov.adjustSize()
        ov.setGeometry(
            (cw.width()  - ov.width())  // 2,
            (cw.height() - ov.height()) // 2,
            ov.width(), ov.height(),
        )
        ov.show()
        ov.raise_()
        self._plugin_manager_overlay = ov   # keep a reference so it isn't GC'd

    def _open_plugin_settings(self):
        sections = self.get_plugin_settings() if self.get_plugin_settings else []
        cw = self.centralWidget()
        ov = PluginSettingsOverlay(sections, parent=cw)
        ow = PluginSettingsOverlay._OW
        oh = min(560, cw.height() - 16)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.show()
        ov.raise_()
        self._plugin_settings_overlay = ov   # keep a reference so it isn't GC'd

    def _open_agenda(self, start: str = "notas") -> None:
        try:
            from .overlays.agenda import AgendaOverlay
            old = getattr(self, "_agenda_overlay", None)
            if old is not None:
                try:
                    old.hide(); old.deleteLater()
                except RuntimeError:
                    pass
            ov = AgendaOverlay(parent=self.centralWidget(), log=self.write_log, start=start)
            self._centre_overlay(ov)
            self._agenda_overlay = ov
        except Exception as e:
            self._log.append_log(f"ERR: A central de notas e lembretes não abriu — {e}")

    def _open_produtividade(self) -> None:
        """Painel Produtividade: tarefas, foco (Pomodoro) e projetos."""
        try:
            from .overlays.produtividade import ProdutividadeOverlay
            old = getattr(self, "_produtiv_overlay", None)
            if old is not None:
                try:
                    old.hide(); old.deleteLater()
                except RuntimeError:
                    pass
            ov = ProdutividadeOverlay(parent=self.centralWidget(), log=self.write_log)
            self._centre_overlay(ov)
            self._produtiv_overlay = ov
        except Exception as e:
            self._log.append_log(f"ERR: O painel de produtividade não abriu — {e}")

    def _open_isa_panel(self) -> None:
        """1.3 — Núcleo I.S.A.: o centro de decisões, ao vivo."""
        try:
            from .overlays.isa import IsaOverlay
            old = getattr(self, "_isa_overlay", None)
            if old is not None:
                try:
                    old._fechar()
                except RuntimeError:
                    pass
            ov = IsaOverlay(parent=self.centralWidget(),
                            estado=lambda: (self.hud.state, self._muted),
                            abrir_atuador=lambda: self._open_settings_panel("atuador"),
                            abrir_ia=lambda: self._open_ia_panel("areas"),
                            abrir_latencia=self._open_latencia_panel,
                            abrir_privacidade=self._open_privacidade_panel)
            self._centre_overlay(ov)
            self._isa_overlay = ov
        except Exception as e:
            self._log.append_log(f"ERR: O núcleo I.S.A. não abriu — {e}")

    def _open_privacidade_panel(self) -> None:
        """3.3 — Privacidade: o que fica no PC, o que sai e apagar com confirmação."""
        try:
            from .overlays.privacidade_painel import PrivacidadeOverlay
            old = getattr(self, "_priv_overlay", None)
            if old is not None:
                try:
                    old._fechar()
                except RuntimeError:
                    pass
            ov = PrivacidadeOverlay(parent=self.centralWidget())
            self._centre_overlay(ov)
            self._priv_overlay = ov
        except Exception as e:
            self._log.append_log(f"ERR: O painel de privacidade não abriu — {e}")

    def _open_latencia_panel(self) -> None:
        """3.3 — Latência: onde o tempo de cada pedido vai."""
        try:
            from .overlays.latencia_painel import LatenciaOverlay
            old = getattr(self, "_lat_overlay", None)
            if old is not None:
                try:
                    old._fechar()
                except RuntimeError:
                    pass
            ov = LatenciaOverlay(parent=self.centralWidget())
            self._centre_overlay(ov)
            self._lat_overlay = ov
        except Exception as e:
            self._log.append_log(f"ERR: O painel de latência não abriu — {e}")

    def _open_ia_panel(self, aba: str = "areas") -> None:
        """Ultra 2026 — "Como a IA do NEXUS funciona": áreas da IA e tipos de IA."""
        try:
            from .overlays.ia_painel import IaPainelOverlay
            old = getattr(self, "_ia_overlay", None)
            if old is not None:
                try:
                    old._fechar()
                except RuntimeError:
                    pass
            ov = IaPainelOverlay(parent=self.centralWidget(), aba=aba or "areas")
            self._centre_overlay(ov)
            self._ia_overlay = ov
        except Exception as e:
            self._log.append_log(f"ERR: O painel da IA não abriu — {e}")
