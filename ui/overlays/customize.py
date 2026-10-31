"""Assistant name, voice, colour, address, language, quiet hours.

Part of the ui package (split from the old single ui.py)."""
from __future__ import annotations

from .._qt import *  # noqa: F401,F403
from .._base import C, DEFAULT_UI_COLOR, FONT_MAIN, accent2  # noqa: F401
from ..widgets import HueWheel  # noqa: F401
from core.protecao import engolida as _engolida

# Temas prontos: um clique troca a cor da interface (e, se quiser, o visual do hub).
TEMAS = (
    ("Ultra 2026", "#8a9bff", "prism"),
    ("Aurora",      "#3ee0ff", "galaxy"),
    ("Pôr do sol",  "#ff7a45", "synthwave"),
    ("Matrix",      "#2dff7a", "city"),
    ("Rosa neon",   "#ff4fd8", "rose"),
    ("Violeta",     "#9b7bff", "kaleido"),
    ("Oceano",      "#3b82ff", "drops"),
    ("Ouro",        "#ffc233", "gears"),
    ("Esmeralda",   "#34e0a1", "lotus"),
    ("Mono",        "#b4bccd", "origami"),
)


class ThemeChip(QPushButton):
    """Amostra pintada do tema: degradê cor→cor2 e o nome por baixo."""

    def __init__(self, nome: str, cor: str, parent=None):
        super().__init__(parent)
        self.nome, self.cor = nome, cor
        self._on = False
        self.setCheckable(True)
        self.setFixedHeight(46)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"{nome}  ({cor})")

    def set_on(self, on: bool):
        self._on = bool(on)
        self.setChecked(self._on)
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        c1, c2 = QColor(self.cor), QColor(accent2(self.cor))
        c1.setAlpha(210 if self._on else 120); c2.setAlpha(210 if self._on else 120)
        g.setColorAt(0, c1); g.setColorAt(1, c2)
        p.setBrush(QBrush(g))
        pen = QPen(QColor(self.cor) if self._on else QColor(255, 255, 255, 40),
                   2 if self._on else 1)
        p.setPen(pen)
        p.drawRoundedRect(r, 9, 9)
        p.setPen(QColor("#ffffff"))
        f = QFont(FONT_MAIN, 8, QFont.Weight.Bold)
        p.setFont(f)
        p.drawText(self.rect().adjusted(4, 0, -4, 0),
                   Qt.AlignmentFlag.AlignCenter, self.nome.upper())
        if self._on:
            p.setBrush(QColor("#ffffff")); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(r.right() - 9, r.top() + 9), 3, 3)
        p.end()


class CustomizeOverlay(QWidget):
    """Assistant name, user name, UI colour, voice, formality, language, quiet hours.

    Since the settings were unified it lives INSIDE the single "Configuração do
    usuário" window (ui/overlays/user_settings.py) with embedded=True: no
    title, no own buttons, and that window's SALVAR calls _save(). The old
    floating mode (embedded=False) still works for anything that wants it."""

    saved = pyqtSignal(str, str, str, str, str, str, dict)
    # assistant_name, user_name, ui_color, voice, formality, language, quiet_hours
    _OW, _OH = 400, 792

    def __init__(self, assistant_name="NEXUS", user_name="",
                 ui_color=DEFAULT_UI_COLOR, voice="", formality="casual",
                 language="auto", quiet_hours=None, parent=None, embedded=False):
        super().__init__(parent)
        self._embedded  = bool(embedded)
        self._formality = formality if formality in ("formal", "casual") else "casual"
        self._language  = language if language in ("auto", "pt", "en") else "auto"
        self._quiet     = quiet_hours or {}      # {"start": "22:00", "end": "07:00"}
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            CustomizeOverlay {{
                background: {"transparent" if embedded else "rgba(8, 10, 28, 245)"};
                border: {"none" if embedded else f"1px solid {C.BORDER_B}"};
                border-radius: 6px;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(*((0, 0, 0, 0) if embedded else (24, 18, 24, 18)))
        lay.setSpacing(8)

        def _lbl(txt, fs=9, bold=False, color=C.PRI, align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt); w.setAlignment(align)
            w.setFont(QFont(FONT_MAIN, fs,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        _fs = (f"QLineEdit {{ background: {C.PANEL2}; color: {C.TEXT}; "
               f"border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 8px; }}"
               f"QLineEdit:focus {{ border: 1px solid {C.PRI}; }}")

        if not embedded:
            lay.addWidget(_lbl("⚙  PERSONALIZAR ASSISTENTE", 12, True))
            sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
            lay.addWidget(sep)

        lay.addWidget(_lbl("NOME DO ASSISTENTE", 8, color=C.TEXT_DIM,
                            align=Qt.AlignmentFlag.AlignLeft))
        self._name_input = QLineEdit(assistant_name)
        self._name_input.setFont(QFont(FONT_MAIN, 10))
        self._name_input.setFixedHeight(32)
        self._name_input.setStyleSheet(_fs)
        lay.addWidget(self._name_input)

        lay.addSpacing(4)
        lay.addWidget(_lbl("SEU NOME  (vazio = ele te chama de senhor)", 8,
                            color=C.TEXT_DIM, align=Qt.AlignmentFlag.AlignLeft))
        self._user_input = QLineEdit(user_name)
        self._user_input.setPlaceholderText("ex.:  André   (vazio = automático)")
        self._user_input.setFont(QFont(FONT_MAIN, 10))
        self._user_input.setFixedHeight(32)
        self._user_input.setStyleSheet(_fs)
        lay.addWidget(self._user_input)

        # ── Assistant voice — Gemini prebuilt voices ─────────────────────────
        # Names are language-neutral proper nouns, so the row reads the same in
        # every locale. Selecting one and applying rebuilds the Live session.
        from memory.config_manager import AVAILABLE_VOICES, DEFAULT_VOICE
        lay.addSpacing(4)
        lay.addWidget(_lbl("VOZ DO ASSISTENTE", 8, color=C.TEXT_DIM,
                            align=Qt.AlignmentFlag.AlignLeft))
        self._sel_voice   = (voice or DEFAULT_VOICE)
        if self._sel_voice not in AVAILABLE_VOICES:
            self._sel_voice = DEFAULT_VOICE
        self._voice_btns: dict[str, QPushButton] = {}
        voice_row = QGridLayout(); voice_row.setSpacing(4)
        for _i, _v in enumerate(AVAILABLE_VOICES):
            b = QPushButton(_v)
            b.setCheckable(True)
            b.setFixedHeight(28)
            b.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, name=_v: self._on_voice_pick(name))
            self._voice_btns[_v] = b
            voice_row.addWidget(b, _i // 4, _i % 4)
        lay.addLayout(voice_row)
        self._refresh_voice_btns()

        # ── Formality — sir/senhor vs. first-name basis ──────────────────────
        lay.addSpacing(4)
        lay.addWidget(_lbl("TRATAMENTO  (formal = senhor · casual = pelo nome)", 8, color=C.TEXT_DIM,
                            align=Qt.AlignmentFlag.AlignLeft))
        self._form_btns: dict[str, QPushButton] = {}
        form_row = QHBoxLayout(); form_row.setSpacing(4)
        for _f, _fl in (("formal", "FORMAL"), ("casual", "CASUAL")):
            b = QPushButton(_fl)
            b.setCheckable(True)
            b.setFixedHeight(28)
            b.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, f=_f: self._on_formality_pick(f))
            self._form_btns[_f] = b
            form_row.addWidget(b)
        lay.addLayout(form_row)
        self._refresh_form_btns()

        # ── Reply language — follow the user, or force PT-BR / English ─────
        lay.addSpacing(4)
        lay.addWidget(_lbl("IDIOMA DAS RESPOSTAS", 8, color=C.TEXT_DIM,
                            align=Qt.AlignmentFlag.AlignLeft))
        self._lang_btns: dict[str, QPushButton] = {}
        lang_row = QHBoxLayout(); lang_row.setSpacing(4)
        for _l, _ll in (("auto", "AUTOMÁTICO"), ("pt", "PORTUGUÊS"), ("en", "ENGLISH")):
            b = QPushButton(_ll)
            b.setCheckable(True)
            b.setFixedHeight(28)
            b.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, l=_l: self._on_lang_pick(l))
            self._lang_btns[_l] = b
            lang_row.addWidget(b)
        lay.addLayout(lang_row)
        self._refresh_lang_btns()

        # ── Quiet hours — no uninvited talk inside the window ────────────────
        lay.addSpacing(4)
        lay.addWidget(_lbl("HORÁRIO DE SILÊNCIO  —  não puxa assunto entre", 8,
                            color=C.TEXT_DIM, align=Qt.AlignmentFlag.AlignLeft))
        qh_row = QHBoxLayout(); qh_row.setSpacing(4)
        self._quiet_btn = QPushButton("DESLIGADO")
        self._quiet_btn.setCheckable(True)
        self._quiet_btn.setFixedHeight(28)
        self._quiet_btn.setMinimumWidth(96)
        self._quiet_btn.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        self._quiet_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._quiet_btn.clicked.connect(self._toggle_quiet)
        qh_row.addWidget(self._quiet_btn)
        self._quiet_start = QLineEdit(self._quiet.get("start", "22:00"))
        self._quiet_start.setFont(QFont(FONT_MAIN, 10))
        self._quiet_start.setFixedHeight(28)
        self._quiet_start.setFixedWidth(64)
        self._quiet_start.setStyleSheet(_fs)
        self._quiet_end = QLineEdit(self._quiet.get("end", "07:00"))
        self._quiet_end.setFont(QFont(FONT_MAIN, 10))
        self._quiet_end.setFixedHeight(28)
        self._quiet_end.setFixedWidth(64)
        self._quiet_end.setStyleSheet(_fs)
        qh_row.addWidget(self._quiet_start)
        qh_row.addWidget(QLabel("→"))
        qh_row.addWidget(self._quiet_end)
        qh_row.addStretch()
        lay.addLayout(qh_row)
        self._quiet_enabled = bool(self._quiet.get("enabled"))
        self._refresh_quiet_btn()

        # ── System update — visible, not only voice ───────────────────────────
        # Embedded in the unified settings it is left out: "Atualizar sistema"
        # already lives in CONFIGURAÇÕES › AVANÇADO, the SETUP menu and voice.
        _upd_box = QWidget(); _upd_box.setStyleSheet("background: transparent;")
        _upd_lay = QVBoxLayout(_upd_box); _upd_lay.setContentsMargins(0, 0, 0, 0)
        _upd_lay.setSpacing(4)
        _upd_lay.addWidget(_lbl("ATUALIZAÇÃO DO SISTEMA", 8, color=C.TEXT_DIM,
                            align=Qt.AlignmentFlag.AlignLeft))
        self._upd_pkg_path = None          # package chosen by CHECK
        try:
            from actions.system_update import current_version
            _running = current_version().get("version", "?")
        except Exception:
            _running = "?"
        self._upd_status = QLabel(f"versão v{_running}")
        self._upd_status.setFont(QFont(FONT_MAIN, 8))
        self._upd_status.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        upd_row = QHBoxLayout(); upd_row.setSpacing(4)
        upd_row.addWidget(self._upd_status)
        self._upd_check = QPushButton("VERIFICAR")
        self._upd_check.setFixedHeight(28)
        self._upd_check.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        self._upd_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self._upd_check.clicked.connect(self._on_check_updates)
        upd_row.addWidget(self._upd_check)
        self._upd_apply = QPushButton("APLICAR")
        self._upd_apply.setFixedHeight(28)
        self._upd_apply.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        self._upd_apply.setCursor(Qt.CursorShape.PointingHandCursor)
        self._upd_apply.clicked.connect(self._on_apply_update)
        self._upd_apply.setVisible(False)
        upd_row.addWidget(self._upd_apply)
        upd_row.addStretch()
        _upd_lay.addLayout(upd_row)
        if not embedded:
            lay.addSpacing(4)
            lay.addWidget(_upd_box)
        else:
            _upd_box.hide()


        # ── Temas prontos ────────────────────────────────────────────────────
        lay.addSpacing(4)
        lay.addWidget(_lbl("TEMAS PRONTOS  —  um clique", 8, color=C.TEXT_DIM,
                           align=Qt.AlignmentFlag.AlignLeft))
        self.on_hud_style = None     # callable(style) — MainWindow wires it
        self._theme_chips: list[ThemeChip] = []
        tgrid = QGridLayout(); tgrid.setSpacing(6)
        for _i, (_n, _c, _h) in enumerate(TEMAS):
            ch = ThemeChip(_n, _c)
            ch.clicked.connect(lambda _=False, n=_n, c=_c, h=_h: self._on_theme(n, c, h))
            self._theme_chips.append(ch)
            tgrid.addWidget(ch, _i // 4, _i % 4)
        lay.addLayout(tgrid)
        self._theme_hud = QCheckBox("Trocar também o visual do hub")
        self._theme_hud.setChecked(True)
        self._theme_hud.setFont(QFont(FONT_MAIN, 8))
        self._theme_hud.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        lay.addWidget(self._theme_hud)

        # ── UI colour — colour wheel ─────────────────────────────────────────
        lay.addSpacing(4)
        clr_hdr = QHBoxLayout()
        clr_hdr.addWidget(_lbl("COR DA INTERFACE  —  arraste o marcador", 8,
                               color=C.TEXT_DIM, align=Qt.AlignmentFlag.AlignLeft))
        clr_hdr.addStretch()
        df_btn = QPushButton("PADRÃO")
        df_btn.setFixedSize(80, 22)
        df_btn.setFont(QFont(FONT_MAIN, 7, QFont.Weight.Bold))
        df_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        df_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        df_btn.clicked.connect(lambda: self._set_color(DEFAULT_UI_COLOR))
        clr_hdr.addWidget(df_btn)
        lay.addLayout(clr_hdr)

        self._initial_color = (ui_color or DEFAULT_UI_COLOR).strip().lower()
        self._sel_color     = self._initial_color
        self.on_preview     = None   # callable(hex) — live preview; MainWindow wires it

        self._wheel = HueWheel(self._sel_color)
        wheel_row = QHBoxLayout()
        wheel_row.addStretch(); wheel_row.addWidget(self._wheel); wheel_row.addStretch()
        lay.addLayout(wheel_row)
        self._wheel.hue_picked.connect(self._on_wheel_pick)
        self._wheel.hue_committed.connect(self._on_wheel_commit)

        self._hex_input = QLineEdit(self._sel_color)
        self._hex_input.setPlaceholderText(f"{DEFAULT_UI_COLOR}   (cor em hex)")
        self._hex_input.setFont(QFont(FONT_MAIN, 10))
        self._hex_input.setFixedHeight(28)
        self._hex_input.setStyleSheet(_fs)
        self._hex_input.textEdited.connect(self._on_hex_edited)
        lay.addWidget(self._hex_input)
        self._sync_chips()

        if embedded:
            return                     # the unified window's SALVAR / FECHAR drive it

        lay.addSpacing(6)
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)

        save_btn = QPushButton("▸  APLICAR")
        save_btn.setFixedHeight(34)
        save_btn.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
        """)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        cancel_btn = QPushButton("CANCELAR")
        cancel_btn.setFixedHeight(34)
        cancel_btn.setFont(QFont(FONT_MAIN, 9))
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        cancel_btn.clicked.connect(self._cancel)
        btn_row.addWidget(cancel_btn)
        lay.addLayout(btn_row)

    # ── voice selection ──────────────────────────────────────────────────────
    def _on_voice_pick(self, name: str):
        self._sel_voice = name
        self._refresh_voice_btns()

    def _on_formality_pick(self, f: str):
        self._formality = f
        self._refresh_form_btns()

    def _on_lang_pick(self, l: str):
        self._language = l
        self._refresh_lang_btns()

    def _refresh_lang_btns(self):
        for l, b in self._lang_btns.items():
            on = self._language == l
            b.setChecked(on)
            b.setStyleSheet(f"""
                QPushButton {{ background: {C.PANEL2 if not on else C.PRI_GHO};
                    color: {C.PRI if on else C.TEXT_DIM};
                    border: 1px solid {C.BORDER_A if not on else C.PRI};
                    border-radius: 3px; text-align: center; }}
                QPushButton:hover {{ color: {C.WHITE}; }}""")

    def _refresh_form_btns(self):
        for f, b in self._form_btns.items():
            on = self._formality == f
            b.setChecked(on)
            b.setStyleSheet(f"""
                QPushButton {{ background: {C.PANEL2 if not on else C.PRI_GHO};
                    color: {C.PRI if on else C.TEXT_DIM};
                    border: 1px solid {C.BORDER_A if not on else C.PRI};
                    border-radius: 3px; text-align: center; }}
                QPushButton:hover {{ color: {C.WHITE}; }}""")

    def _toggle_quiet(self):
        self._quiet_enabled = not self._quiet_enabled
        self._refresh_quiet_btn()

    def _refresh_quiet_btn(self):
        on = self._quiet_enabled
        self._quiet_btn.setChecked(on)
        self._quiet_btn.setText("LIGADO" if on else "DESLIGADO")
        self._quiet_btn.setStyleSheet(f"""
            QPushButton {{ background: {C.PRI_GHO if on else C.PANEL2};
                color: {C.PRI if on else C.TEXT_DIM};
                border: 1px solid {C.PRI if on else C.BORDER_A};
                border-radius: 3px; text-align: center; }}
            QPushButton:hover {{ color: {C.WHITE}; }}""")

    # ── system update ──────────────────────────────────────────────────────────
    def _on_check_updates(self):
        """Scan the updates/ folder and report status on the panel row."""
        try:
            from actions.system_update import current_version, scan_updates, is_newer
            cur = current_version().get("version", "?")
            pkgs = scan_updates()
            newer = [p for p in pkgs
                     if p["version"] != "?" and is_newer(p["version"], cur)]
            if newer:
                self._upd_pkg_path = newer[0]["path"]
                self._upd_status.setText(f"v{newer[0]['version']} pronta em updates/")
                self._upd_apply.setVisible(True)
            else:
                self._upd_pkg_path = None
                self._upd_status.setText(
                    f"atualizado (v{cur})" if pkgs
                    else f"atualizado (v{cur}) — coloque um ZIP em updates/")
                self._upd_apply.setVisible(False)
        except Exception as e:
            self._upd_status.setText(f"a verificação falhou — {e}")

    def _on_apply_update(self):
        """Extract the chosen package; a restart finishes the swap."""
        if not self._upd_pkg_path:
            self._on_check_updates()
        if not self._upd_pkg_path:
            return
        try:
            from actions.system_update import apply_package
            apply_package(self._upd_pkg_path)
            self._upd_status.setText("aplicada — reinicie para terminar")
            self._upd_apply.setVisible(False)
        except Exception as e:
            self._upd_status.setText(f"não deu para aplicar — {e}")

    def _refresh_voice_btns(self):
        """Highlight the selected voice pill; dim the rest."""
        for name, b in self._voice_btns.items():
            on = (name == self._sel_voice)
            b.setChecked(on)
            if on:
                b.setStyleSheet(f"""
                    QPushButton {{ background: {C.PRI_GHO}; color: {C.PRI};
                        border: 1px solid {C.PRI}; border-radius: 3px; }}
                """)
            else:
                b.setStyleSheet(f"""
                    QPushButton {{ background: transparent; color: {C.TEXT_MED};
                        border: 1px solid {C.BORDER}; border-radius: 3px; }}
                    QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
                """)

    def _on_theme(self, nome: str, cor: str, hud: str):
        self._set_color(cor)
        if self._theme_hud.isChecked() and self.on_hud_style:
            try:
                self.on_hud_style(hud)
            except Exception:
                _engolida("ui/overlays/customize.py:469")

    def _sync_chips(self):
        for ch in getattr(self, "_theme_chips", ()):
            ch.set_on(ch.cor.lower() == self._sel_color)

    # ── colour flow ──────────────────────────────────────────────────────────
    def _set_color(self, hx: str, update_wheel: bool = True, preview: bool = True):
        """Updates the selected colour; hex box + wheel stay in sync, theme is live-previewed."""
        self._sel_color = hx.strip().lower()
        self._hex_input.blockSignals(True)
        self._hex_input.setText(self._sel_color)
        self._hex_input.blockSignals(False)
        if update_wheel:
            self._wheel.set_color(self._sel_color)
        self._sync_chips()
        if preview and self.on_preview:
            self.on_preview(self._sel_color)

    def _on_wheel_pick(self, hx: str):
        # While dragging: update the hex box, don't apply the theme yet
        self._sel_color = hx
        self._hex_input.blockSignals(True)
        self._hex_input.setText(hx)
        self._hex_input.blockSignals(False)

    def _on_wheel_commit(self, hx: str):
        # Handle released → live-preview the whole interface
        self._set_color(hx, update_wheel=False)

    def _on_hex_edited(self, text: str):
        t = text.strip().lower()
        if t.startswith("#") and len(t) == 7:
            try:
                int(t[1:], 16)
            except ValueError:
                return
            self._set_color(t, update_wheel=True, preview=True)

    def _cancel(self):
        # If a preview was applied, revert to the colour from launch
        if self.on_preview and self._sel_color != self._initial_color:
            self.on_preview(self._initial_color)
        if not self._embedded:
            self.hide()

    def _save(self):
        name = self._name_input.text().strip() or "NEXUS"
        user = self._user_input.text().strip()
        quiet = {
            "enabled":    bool(self._quiet_enabled),
            "start":     self._quiet_start.text().strip() or "22:00",
            "end":       self._quiet_end.text().strip() or "07:00",
        }
        self.saved.emit(name, user, self._sel_color or DEFAULT_UI_COLOR,
                        self._sel_voice, self._formality, self._language, quiet)
        # Saved colour is the new baseline: closing afterwards must not revert it.
        self._initial_color = self._sel_color or DEFAULT_UI_COLOR
        if not self._embedded:
            self.hide()
