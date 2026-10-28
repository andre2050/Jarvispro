"""Plugins, confirmation banner, audio devices, memory.

Part of the ui package (split from the old single ui.py)."""
from __future__ import annotations

from .._qt import *  # noqa: F401,F403
from .._base import C, FONT_MAIN  # noqa: F401
from ..overlays.base import _HudOverlay  # noqa: F401

class PluginManagerOverlay(QWidget):
    """Floating overlay — lists discovered plugins with per-plugin ON/OFF toggles."""

    _OW = 420

    def __init__(self, plugins: list[dict], parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            PluginManagerOverlay {{
                background: rgba(8, 10, 28, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._OW)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(6)

        hdr = QLabel("🧩  PLUGINS")
        hdr.setFont(QFont(FONT_MAIN, 12, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        lay.addWidget(hdr)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        if not plugins:
            empty = QLabel("Nenhum plugin na pasta plugins/.")
            empty.setFont(QFont(FONT_MAIN, 8))
            empty.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            lay.addWidget(empty)

        for p in plugins:
            lay.addLayout(self._build_row(p))

        lay.addSpacing(4)
        close_btn = QPushButton("FECHAR")
        close_btn.setFixedHeight(30)
        close_btn.setFont(QFont(FONT_MAIN, 9))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        close_btn.clicked.connect(self.hide)
        lay.addWidget(close_btn)
        self.adjustSize()

    def _build_row(self, p: dict) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(6)

        label_text = p["name"] if p["valid"] else f"{p['name']}  (⚠ {p['file']})"
        lbl = QLabel(label_text)
        lbl.setFont(QFont(FONT_MAIN, 8))
        lbl.setStyleSheet(f"color: {C.TEXT if p['valid'] else C.TEXT_DIM}; background: transparent;")
        lbl.setToolTip(p["description"] if p["valid"] else p["error"])
        lbl.setWordWrap(False)
        row.addWidget(lbl, stretch=1)

        btn = QPushButton()
        btn.setFixedSize(72, 24)
        btn.setFont(QFont(FONT_MAIN, 7, QFont.Weight.Bold))
        if not p["valid"]:
            btn.setText("COM ERRO")
            btn.setEnabled(False)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 3px;
                }}
            """)
        else:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._style_toggle(btn, p["enabled"])
            btn.clicked.connect(lambda _, name=p["name"], b=btn: self._toggle(name, b))
        row.addWidget(btn)
        return row

    def _style_toggle(self, btn: QPushButton, enabled: bool):
        if enabled:
            btn.setText("LIGADO")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: #001a08; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 3px;
                }}
                QPushButton:hover {{ background: #002010; }}
            """)
        else:
            btn.setText("DESLIGADO")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 3px;
                }}
                QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
            """)

    def _toggle(self, name: str, btn: QPushButton):
        from memory.config_manager import get_plugin_enabled, save_plugin_enabled
        new_val = not get_plugin_enabled(name)
        save_plugin_enabled(name, new_val)
        self._style_toggle(btn, new_val)


class ConfirmBanner(_HudOverlay):
    """The gate in front of an action that cannot be taken back.

    The old confirmation was a tool parameter the model filled in itself, which
    means it confirmed its own shutdown requests. This is the interface asking,
    and the answer travels from a human finger to core/confirm.py without the
    model in the loop. Nothing blocks while it is up: the assistant keeps
    talking, so this costs no latency — unlike the old gate, which spent two
    tool round trips on every power command."""

    answered = pyqtSignal(bool)
    _OW = 430

    def __init__(self, title: str, detail: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ConfirmBanner {{
                background: rgba(14, 3, 0, 250);
                border: 1px solid {C.ACC};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._OW)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)

        hdr = QLabel("⚠  CONFIRMAR")
        hdr.setFont(QFont(FONT_MAIN, 11, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.ACC}; background: transparent;")
        lay.addWidget(hdr)

        ttl = QLabel(title)
        ttl.setWordWrap(True)
        ttl.setFont(QFont(FONT_MAIN, 10, QFont.Weight.Bold))
        ttl.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
        lay.addWidget(ttl)

        if detail:
            dtl = QLabel(detail)
            dtl.setWordWrap(True)
            dtl.setFont(QFont(FONT_MAIN, 8))
            dtl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            lay.addWidget(dtl)

        row = QHBoxLayout(); row.setSpacing(8)

        yes = QPushButton("▸  CONFIRMAR")
        yes.setFixedHeight(32)
        yes.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        yes.setCursor(Qt.CursorShape.PointingHandCursor)
        yes.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.ACC};
                border: 1px solid {C.ACC}; border-radius: 3px; }}
            QPushButton:hover {{ background: rgba(255,107,0,40); }}
        """)
        yes.clicked.connect(lambda: self.answered.emit(True))
        row.addWidget(yes)

        no = QPushButton("CANCELAR")
        no.setFixedHeight(32)
        no.setFont(QFont(FONT_MAIN, 9))
        no.setCursor(Qt.CursorShape.PointingHandCursor)
        no.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        no.clicked.connect(lambda: self.answered.emit(False))
        row.addWidget(no)
        lay.addLayout(row)

        # Default focus on CANCEL: if someone hits Enter without reading, the
        # safe answer wins.
        no.setDefault(True)
        no.setFocus()


class AudioDeviceOverlay(_HudOverlay):
    """Choose which microphone NEXUS listens to and which speakers it uses.

    Both audio streams used to open with no `device=` at all, so they always
    took the OS default — which on Windows moves by itself the moment a headset
    is plugged in. 'NEXUS can't hear me' is usually 'NEXUS is listening to the
    webcam'.

    1.5 — 🎤 TESTE com medidor ao vivo (a única prova de que ele te ouve) e
    🎚️ volume do alto-falante ESCOLHIDO, não do "padrão" do Windows."""

    picked = pyqtSignal()      # emitted after Apply, when something changed
    _nivel_sig = pyqtSignal(float)
    _teste_fim_sig = pyqtSignal(str)
    _OW = 460

    def __init__(self, parent=None):
        super().__init__(parent)
        from core.audio_devices import list_devices, DEFAULT_LABEL
        from memory.config_manager import get_input_device, get_output_device

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            AudioDeviceOverlay {{
                background: rgba(8, 10, 28, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._OW)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(6)

        hdr = QLabel("🎧  DISPOSITIVOS DE ÁUDIO")
        hdr.setFont(QFont(FONT_MAIN, 12, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        lay.addWidget(hdr)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        _combo_css = (
            f"QComboBox {{ background: {C.BG}; color: {C.TEXT}; "
            f"border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 8px; }}"
            f"QComboBox:hover {{ border-color: {C.BORDER_B}; }}"
            f"QComboBox QAbstractItemView {{ background: {C.BG}; color: {C.TEXT}; "
            f"selection-background-color: {C.PRI_GHO}; border: 1px solid {C.BORDER}; }}"
        )

        def _row(label: str, kind: str, current: str) -> QComboBox:
            cap = QLabel(label)
            cap.setFont(QFont(FONT_MAIN, 8))
            cap.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            lay.addWidget(cap)

            box = QComboBox()
            box.setFont(QFont(FONT_MAIN, 9))
            box.setFixedHeight(30)
            box.setStyleSheet(_combo_css)
            # The list is served from a cache warmed on a background thread at
            # startup, so opening this panel never blocks the Qt thread on the
            # host audio API.
            box.addItem(DEFAULT_LABEL, "")
            for name in list_devices(kind):
                box.addItem(name, name)
            idx = box.findData(current) if current else 0
            box.setCurrentIndex(idx if idx >= 0 else 0)
            if current and idx < 0:
                # Saved device is not plugged in right now. Show it rather than
                # silently resetting the user's choice to default.
                box.addItem(f"{current}  (desconectado)", current)
                box.setCurrentIndex(box.count() - 1)
            lay.addWidget(box)
            return box

        self._in_box  = _row("MICROFONE — por onde o NEXUS te ouve",
                             "input", get_input_device())
        lay.addSpacing(4)
        self._out_box = _row("ALTO-FALANTE — por onde o NEXUS fala",
                             "output", get_output_device())

        # ── 1.5: TESTE com medidor e volume por dispositivo ──
        _btn_css = (f"QPushButton {{ background: transparent; color: {C.PRI}; "
                    f"border: 1px solid {C.PRI_DIM}; border-radius: 3px; padding: 4px 8px; }}"
                    f"QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.PRI}; }}")
        trow = QHBoxLayout(); trow.setSpacing(6)
        self._b_teste_mic = QPushButton("🎤 TESTAR MICROFONE")
        self._b_teste_mic.setStyleSheet(_btn_css)
        self._b_teste_mic.setCursor(Qt.CursorShape.PointingHandCursor)
        self._b_teste_mic.clicked.connect(self._testar_mic)
        self._b_teste_spk = QPushButton("🔊 TESTAR ALTO-FALANTE")
        self._b_teste_spk.setStyleSheet(_btn_css)
        self._b_teste_spk.setCursor(Qt.CursorShape.PointingHandCursor)
        self._b_teste_spk.clicked.connect(self._testar_alto_falante)
        trow.addWidget(self._b_teste_mic); trow.addWidget(self._b_teste_spk)
        lay.addSpacing(4)
        lay.addLayout(trow)
        self._medidor = QProgressBar()
        self._medidor.setRange(0, 100); self._medidor.setValue(0)
        self._medidor.setTextVisible(False); self._medidor.setFixedHeight(10)
        self._medidor.setStyleSheet(
            f"QProgressBar {{ background: {C.BG}; border: 1px solid {C.BORDER}; border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: {C.PRI}; border-radius: 2px; }}")
        lay.addWidget(self._medidor)
        self._teste_msg = QLabel("Fale durante o teste: a barra tem que se mexer com a sua voz.")
        self._teste_msg.setWordWrap(True)
        self._teste_msg.setFont(QFont(FONT_MAIN, 7))
        self._teste_msg.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addWidget(self._teste_msg)
        self._nivel_sig.connect(lambda v: self._medidor.setValue(int(v * 100)))
        self._teste_fim_sig.connect(self._teste_acabou)

        from PyQt6.QtWidgets import QSlider
        vrow = QHBoxLayout(); vrow.setSpacing(6)
        vcap = QLabel("VOLUME deste alto-falante")
        vcap.setFont(QFont(FONT_MAIN, 8))
        vcap.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._vol = QSlider(Qt.Orientation.Horizontal)
        self._vol.setRange(0, 100)
        self._vol_lbl = QLabel("—")
        self._vol_lbl.setFixedWidth(40)
        self._vol_lbl.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
        vrow.addWidget(vcap); vrow.addWidget(self._vol, 1); vrow.addWidget(self._vol_lbl)
        lay.addLayout(vrow)
        self._vol.valueChanged.connect(self._mudar_volume)
        self._out_box.currentIndexChanged.connect(lambda _i: self._ler_volume())
        self._ler_volume()

        note = QLabel("Aplicar reconecta a sessão. A conversa continua.")
        note.setWordWrap(True)
        note.setFont(QFont(FONT_MAIN, 7))
        note.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addSpacing(6)
        lay.addWidget(note)

        row = QHBoxLayout(); row.setSpacing(8)
        ok = QPushButton("▸  APLICAR")
        ok.setFixedHeight(32)
        ok.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px; }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.PRI}; }}
        """)
        ok.clicked.connect(self._apply)
        row.addWidget(ok)

        cancel = QPushButton("FECHAR")
        cancel.setFixedHeight(32)
        cancel.setFont(QFont(FONT_MAIN, 9))
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        cancel.clicked.connect(self.hide)
        row.addWidget(cancel)
        lay.addLayout(row)

    # ── 1.5: teste e volume ──
    def _nome_saida(self) -> str:
        return self._out_box.currentData() or ""

    def _ler_volume(self) -> None:
        try:
            from core.volume_dispositivo import ler
            v = ler(self._nome_saida())
        except Exception:
            v = None
        self._vol.blockSignals(True)
        if v is None:
            self._vol.setEnabled(False)
            self._vol_lbl.setText("—")
        else:
            self._vol.setEnabled(True)
            self._vol.setValue(v)
            self._vol_lbl.setText(f"{v}%")
        self._vol.blockSignals(False)

    def _mudar_volume(self, v: int) -> None:
        self._vol_lbl.setText(f"{v}%")
        try:
            from core.volume_dispositivo import definir
            if not definir(self._nome_saida(), v):
                self._vol_lbl.setText("✖")
        except Exception:
            self._vol_lbl.setText("✖")

    def _testar_mic(self) -> None:
        if getattr(self, "_testando", False):
            return
        self._testando = True
        self._b_teste_mic.setEnabled(False)
        self._teste_msg.setText("Ouvindo por 5 segundos… fale alguma coisa.")
        nome = self._in_box.currentData() or ""

        def _rodar():
            import numpy as _np
            import sounddevice as _sd
            from core.audio_devices import resolve
            pico, falou = 0.0, 0
            try:
                disp = resolve(nome, "input")
                fim = time.monotonic() + 5.0

                def cb(indata, frames, t, status):
                    nonlocal pico, falou
                    x = indata[:, 0].astype(_np.float32)
                    rms = float(_np.sqrt(_np.mean(x * x)))
                    nivel = 0.0 if rms <= 60 else min(1.0, (rms - 60) / 2540.0)
                    pico = max(pico, nivel)
                    if nivel > 0.12:
                        falou += 1
                    self._nivel_sig.emit(nivel)
                with _sd.InputStream(samplerate=16000, channels=1, dtype="int16",
                                     blocksize=512, device=disp, callback=cb):
                    while time.monotonic() < fim:
                        time.sleep(0.05)
                self._nivel_sig.emit(0.0)
                if falou >= 6:
                    msg = f"✔ Ouvi você (pico {int(pico * 100)}%). Este microfone funciona."
                elif pico > 0.02:
                    msg = (f"⚠ Ouvi só um som baixinho (pico {int(pico * 100)}%). Fale mais perto, "
                           "ou aumente o volume do microfone no Windows.")
                else:
                    msg = ("✖ Não ouvi nada. Confira se é o microfone certo, se não está no mudo "
                           "e a permissão do Windows (Privacidade › Microfone).")
            except Exception as e:
                msg = f"✖ O microfone não abriu: {str(e)[:120]}"
            self._teste_fim_sig.emit(msg)
        threading.Thread(target=_rodar, daemon=True).start()

    def _testar_alto_falante(self) -> None:
        nome = self._nome_saida()

        def _rodar():
            import numpy as _np
            import sounddevice as _sd
            from core.audio_devices import resolve
            try:
                taxa = 24000
                t = _np.arange(int(taxa * 0.9)) / taxa
                env = _np.minimum(1.0, _np.minimum(t / 0.05, (t[-1] - t) / 0.15))
                tom = (_np.sin(2 * _np.pi * 523.25 * t) * 0.6 + _np.sin(2 * _np.pi * 659.25 * t) * 0.4)
                pcm = (tom * env * 0.35 * 32767).astype(_np.int16)
                _sd.play(pcm, taxa, device=resolve(nome, "output"))
                _sd.wait()
                self._teste_fim_sig.emit("🔊 Tocou um aviso neste alto-falante — se você ouviu, está certo.")
            except Exception as e:
                self._teste_fim_sig.emit(f"✖ O alto-falante não abriu: {str(e)[:120]}")
        threading.Thread(target=_rodar, daemon=True).start()

    def _teste_acabou(self, msg: str) -> None:
        self._testando = False
        self._b_teste_mic.setEnabled(True)
        self._teste_msg.setText(msg)
        self._medidor.setValue(0)

    def _apply(self):
        from memory.config_manager import (
            get_input_device, get_output_device,
            save_input_device, save_output_device,
        )
        new_in  = self._in_box.currentData()  or ""
        new_out = self._out_box.currentData() or ""
        changed = (new_in != get_input_device()) or (new_out != get_output_device())
        save_input_device(new_in)
        save_output_device(new_out)
        self.hide()
        # Only rebuild the session if something actually moved — a no-op Apply
        # should not cost a reconnect.
        if changed:
            self.picked.emit()


class MemoryOverlay(_HudOverlay):
    """Everything NEXUS has stored about you, and when it learned it.

    Memory used to be a 2200-character store that deleted its oldest entries
    when full and mentioned it only on stdout. The cap is gone; this panel is
    the other half of that change — a memory you cannot inspect is a memory you
    cannot trust, and 'delete' has to be something the person can do."""

    _OW = 520

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            MemoryOverlay {{
                background: rgba(8, 10, 28, 246);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._OW)

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(20, 16, 20, 16)
        self._lay.setSpacing(5)
        self._rebuild()

    def _clear_layout(self):
        """Take every item out of the layout and detach it from the widget tree
        in this call.

        deleteLater() on its own is not enough: it queues destruction for the
        next event-loop pass, and until then the old rows are still children of
        this widget and still paint — which is what drew half of the previous
        panel over the new one. setParent(None) removes them from the tree now;
        deleteLater() then frees them safely."""
        while self._lay.count():
            item = self._lay.takeAt(0)
            w = item.widget()
            if w is not None:
                # hide() stops it painting in this frame; deleteLater() frees it
                # safely afterwards. setParent(None) would also stop the paint,
                # but it turns the widget into a top-level window for the moment
                # between the two calls, which is not something to leave lying
                # around inside a click handler.
                w.hide()
                w.deleteLater()
                continue
            sub = item.layout()
            if sub is not None:
                while sub.count():
                    si = sub.takeAt(0)
                    sw = si.widget()
                    if sw is not None:
                        sw.hide()
                        sw.deleteLater()
                sub.deleteLater()

    def _settle(self, before):
        """Size the panel to its content, re-centre it, and repaint what the old
        size covered.

        The re-size has to happen here rather than at the end of _rebuild
        because Qt has not polished the freshly-created children at that point,
        so the size hint it would read is the empty-layout one. Measured: a
        first adjustSize() returned 32 px for a panel whose content needed 155,
        and a second call — after the same widgets had been through the event
        loop — returned 155. So this runs twice: once now, once on the next
        turn, from _rebuild.

        The re-centre and the repaint are needed because the overlay is placed
        by hand and is in no layout: shrinking it leaves it off-centre and
        leaves its former pixels on screen, since nothing tells the parent that
        region changed. The repaint has to cover the union of the old and new
        rectangles."""
        self._lay.invalidate()
        self._lay.activate()
        self.updateGeometry()
        self.adjustSize()

        p = self.parentWidget()
        if p is None:
            self.update()
            return
        self.move(max(0, (p.width()  - self.width())  // 2),
                  max(0, (p.height() - self.height()) // 2))
        p.update(before.united(self.geometry()))
        self.update()

    def _rebuild(self):
        before = self.geometry()
        self._clear_layout()

        from memory.memory_manager import all_entries_for_ui

        hdr = QLabel("🧠  O QUE O NEXUS LEMBRA")
        hdr.setFont(QFont(FONT_MAIN, 12, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        self._lay.addWidget(hdr)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        self._lay.addWidget(sep)

        rows = all_entries_for_ui()

        cap = QLabel(f"{len(rows)} fato(s) guardado(s) — os mais novos primeiro. "
                     f"Nada daqui é enviado para lugar nenhum: fica em "
                     f"memory/long_term.json, neste computador.")
        cap.setWordWrap(True)
        cap.setFont(QFont(FONT_MAIN, 7))
        cap.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._lay.addWidget(cap)

        if not rows:
            empty = QLabel("Nada guardado ainda.")
            empty.setFont(QFont(FONT_MAIN, 9))
            empty.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            self._lay.addWidget(empty)
        else:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFixedHeight(min(420, 34 * len(rows) + 10))
            scroll.setStyleSheet(
                f"QScrollArea {{ border: 1px solid {C.BORDER}; border-radius: 3px; "
                f"background: transparent; }}"
            )
            inner = QWidget()
            ilay  = QVBoxLayout(inner)
            ilay.setContentsMargins(6, 6, 6, 6)
            ilay.setSpacing(3)

            for r in rows:
                line = QHBoxLayout(); line.setSpacing(6)
                txt = QLabel(f"<b>{r['key'].replace('_', ' ')}</b> "
                             f"<span style='color:{C.TEXT_MED}'>— {r['value']}</span>")
                txt.setWordWrap(True)
                txt.setFont(QFont(FONT_MAIN, 8))
                txt.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
                line.addWidget(txt, 1)

                meta = QLabel(f"{r['category'][:4]} · {r['updated'] or '—'}")
                meta.setFont(QFont(FONT_MAIN, 7))
                meta.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
                line.addWidget(meta)

                rm = QPushButton("✕")
                rm.setFixedSize(20, 20)
                rm.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
                rm.setCursor(Qt.CursorShape.PointingHandCursor)
                rm.setToolTip("Esquecer isto")
                rm.setStyleSheet(f"""
                    QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                        border: 1px solid {C.BORDER}; border-radius: 3px; }}
                    QPushButton:hover {{ color: {C.RED}; border-color: {C.RED}; }}
                """)
                rm.clicked.connect(
                    lambda _=False, c=r["category"], k=r["key"]: self._forget(c, k))
                line.addWidget(rm)

                holder = QWidget()
                holder.setLayout(line)
                ilay.addWidget(holder)

            ilay.addStretch()
            scroll.setWidget(inner)
            self._lay.addWidget(scroll)

        close = QPushButton("FECHAR")
        close.setFixedHeight(30)
        close.setFont(QFont(FONT_MAIN, 9))
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        close.clicked.connect(self.hide)
        self._lay.addWidget(close)

        self._settle(before)
        # …and again once Qt has polished the new children, because the size
        # hint is not final until then. Harmless when the first pass already
        # got it right: _settle is idempotent.
        QTimer.singleShot(0, lambda g=before: self._settle(g))

    def _forget(self, category: str, key: str):
        from memory.memory_manager import forget
        forget(key, category)
        # Rebuild on the NEXT event-loop turn, not inside this click handler.
        # The rebuild destroys the very ✕ button that emitted this signal, and
        # Qt is entitled to touch the sender after a slot returns; tearing it
        # down mid-emission is how a widget ends up half-alive on screen.
        QTimer.singleShot(0, self._rebuild)
