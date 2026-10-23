"""Vision, system intel, clipboard history, command list, notes.

Part of the ui package (split from the old single ui.py)."""
from __future__ import annotations

import os
from pathlib import Path

from .._qt import *  # noqa: F401,F403
from .._base import _base_dir  # noqa: F401
from .._base import C, FONT_MAIN  # noqa: F401
from ..overlays.base import _HudOverlay  # noqa: F401

class VisionOverlay(_HudOverlay):
    """Painel 👁 VISÃO (1.4.2) — tudo roda no próprio PC, sem internet.

    OpenCV (actions/computer_vision.py): QR na tela e na câmera, contar rostos,
    analisar a tela e a vigia de movimento. Visão local (core/visao_local.py):
    ler o texto e descrever a tela.

    Na 1.4.2 cada botão roda numa thread (a janela não trava mais enquanto a
    câmera abre), o NEXUS sai da frente por um instante para fotografar a tela
    (antes ele fotografava a si mesmo), e o resultado aparece aqui: a imagem
    que foi analisada, com as marcações, e o texto para copiar."""

    _OW = 420
    _pronto_sig = pyqtSignal(object)      # resultado de uma ação (dict)
    _sit_sig = pyqtSignal(str)

    _BTN_CSS = """
        QPushButton {{ background: {p2}; color: {t};
                      border: 1px solid {b}; border-radius: 5px; padding: 2px 6px; }}
        QPushButton:hover {{ border-color: {pd}; }}
        QPushButton:disabled {{ color: {td}; }}
    """

    def __init__(self, parent=None, log=None):
        super().__init__(parent)
        self._log_fn = log            # callable(msg) → conversa
        self._ocupado = False
        self._res_texto = ""
        self._res_link = ""
        self._pronto_sig.connect(self._pronto)
        self._sit_sig.connect(lambda t: self._local_line.setText(t))
        self.setObjectName("VisionOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            QWidget#VisionOverlay {{
                background: rgba(8, 10, 28, 248);
                border: 1px solid {C.BORDER_B};
                border-radius: 8px;
            }}
            QLabel {{ background: transparent; }}
            QTextEdit#visaoOut {{ background: {C.PANEL}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 4px; }}
            QComboBox#visaoSens {{ background: {C.PANEL2}; color: {C.TEXT};
                border: 1px solid {C.BORDER_B}; border-radius: 4px; padding: 1px 6px; }}
        """)
        self.setFixedWidth(self._OW)
        css = self._BTN_CSS.format(p2=C.PANEL2, t=C.TEXT, b=C.BORDER_B, pd=C.PRI_DIM, td=C.TEXT_DIM)

        def _lbl(txt, fs=9, bold=False, color=C.PRI, align=Qt.AlignmentFlag.AlignLeft):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setWordWrap(True)
            w.setFont(QFont(FONT_MAIN, fs, QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color};")
            return w

        def _btn(txt, fn, tip="", altura=30):
            b = QPushButton(txt)
            b.setFixedHeight(altura)
            b.setFont(QFont(FONT_MAIN, 8))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(css)
            if tip:
                b.setToolTip(tip)
            b.clicked.connect(fn)
            return b

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(7)

        head = QHBoxLayout()
        head.addWidget(_lbl("👁  VISÃO", 12, True))
        head.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setFont(QFont(FONT_MAIN, 9))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"QPushButton {{ background: transparent; color: {C.TEXT_DIM}; border: none; }}"
                                f"QPushButton:hover {{ color: {C.TEXT}; }}")
        close_btn.clicked.connect(self._close_panel)
        head.addWidget(close_btn)
        lay.addLayout(head)
        lay.addWidget(_lbl("Tudo aqui roda no seu PC, sem internet. Para olhar a tela, o NEXUS "
                           "sai da frente por um instante.", 8, color=C.TEXT_DIM))

        self._btns: list[QPushButton] = []
        grid = QGridLayout()
        grid.setSpacing(5)
        specs = [
            ("📱  QR NA TELA", {"action": "qr", "angle": "screen"},
             "Lê os QR codes que estão na tela (em todos os monitores)"),
            ("📷  QR NA CÂMERA", {"action": "qr", "angle": "camera"},
             "Mostre o QR para a câmera, a uns 20 cm, com boa luz"),
            ("👤  CONTAR ROSTOS", {"action": "faces", "angle": "camera"},
             "Conta os rostos que a câmera está vendo"),
            ("📊  ANALISAR A TELA", {"action": "analyze", "angle": "screen"},
             "Brilho, nitidez e as cores principais da tela"),
        ]
        for i, (txt, params, tip) in enumerate(specs):
            b = _btn(txt, lambda _=False, p=params: self._run(p), tip)
            self._btns.append(b)
            grid.addWidget(b, i // 2, i % 2)
        lay.addLayout(grid)

        # vigia de movimento
        lay.addWidget(_lbl("🚨  VIGIA DE MOVIMENTO", 9, True))
        self._motion_line = _lbl("", 8, color=C.TEXT_MED)
        lay.addWidget(self._motion_line)
        vrow = QHBoxLayout()
        vrow.setSpacing(5)
        vrow.addWidget(_lbl("Sensibilidade", 8, color=C.TEXT_DIM))
        self._sens = QComboBox()
        self._sens.setObjectName("visaoSens")
        for n in range(1, 11):
            self._sens.addItem(str(n), n)
        self._sens.setCurrentIndex(4)
        self._sens.setFixedHeight(28)
        self._sens.setToolTip("1 = só movimentos grandes · 10 = qualquer coisinha")
        vrow.addWidget(self._sens)
        self._mot_on = _btn("🚨  VIGIAR", self._vigiar,
                            "Olha a câmera e avisa quando algo se mexer (com som e foto)")
        self._mot_off = _btn("⏹  PARAR DE VIGIAR", lambda: self._run({"action": "motion", "op": "stop"}))
        self._fotos = _btn("📁", self._abrir_fotos, "Abrir as fotos da vigia (Imagens\\NEXUS Vigia)")
        self._fotos.setFixedWidth(36)
        vrow.addWidget(self._mot_on, 1)
        vrow.addWidget(self._mot_off, 1)
        vrow.addWidget(self._fotos)
        lay.addLayout(vrow)

        # visão local (OCR / descrever)
        lay.addWidget(_lbl("🔒  LER E DESCREVER", 9, True))
        self._local_line = _lbl("Verificando o que está instalado…", 8, color=C.TEXT_DIM)
        lay.addWidget(self._local_line)
        g2 = QHBoxLayout()
        g2.setSpacing(5)
        tip = "O NEXUS sai da frente por um instante e olha a janela que estava atrás dele"
        b1 = _btn("🔤  LER O TEXTO", lambda: self._run_local("read_text"), tip)
        b2 = _btn("🖼  DESCREVER", lambda: self._run_local("describe"), tip)
        self._btns += [b1, b2]
        g2.addWidget(b1)
        g2.addWidget(b2)
        lay.addLayout(g2)

        # resultado
        self._status = _lbl("Escolha um botão acima — ou peça por voz: “lê o QR code da minha "
                            "tela”, “vigia a câmera e me avisa se mexer”.", 8, color=C.TEXT_MED)
        self._status.setMinimumHeight(30)
        self._status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self._status)
        self._previa = QLabel()
        self._previa.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._previa.setStyleSheet(f"background: #000; border: 1px solid {C.BORDER}; border-radius: 4px;")
        self._previa.hide()
        lay.addWidget(self._previa)
        self._out = QTextEdit()
        self._out.setObjectName("visaoOut")
        self._out.setReadOnly(True)
        self._out.setFixedHeight(92)
        self._out.setFont(QFont(FONT_MAIN, 8))
        self._out.hide()
        lay.addWidget(self._out)
        acoes = QHBoxLayout()
        acoes.setSpacing(5)
        self._b_copiar = _btn("📋  COPIAR", self._copiar, altura=26)
        self._b_link = _btn("🌐  ABRIR LINK", self._abrir_link, altura=26)
        self._b_bloco = _btn("📝  BLOCO DE NOTAS", self._para_bloco, altura=26)
        for b in (self._b_copiar, self._b_link, self._b_bloco):
            b.hide()
            acoes.addWidget(b)
        acoes.addStretch(1)
        lay.addLayout(acoes)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_motion)
        self._timer.start(1000)
        self._refresh_motion()
        threading.Thread(target=self._ver_situacao, daemon=True).start()

    # ── geral ───────────────────────────────────────────────────────────────

    def _close_panel(self):
        self._timer.stop()
        self.hide()
        self.deleteLater()

    def _ocultar_fn(self):
        """Tira a janela do NEXUS da frente (pela fila do Qt — dá para chamar de thread)."""
        win = self.window()
        sig = getattr(win, "_ocultar_sig", None)
        return (lambda v: sig.emit(bool(v))) if sig is not None else None

    def _emitir(self, dados: dict) -> None:
        try:
            self._pronto_sig.emit(dados)
        except RuntimeError:
            pass                    # o painel foi fechado enquanto trabalhava

    def _comecar(self, texto: str) -> bool:
        if self._ocupado:
            return False
        self._ocupado = True
        for b in self._btns + [self._mot_on, self._mot_off]:
            b.setEnabled(False)
        self._status.setText(texto)
        return True

    @staticmethod
    def _jpeg(imagem) -> bytes:
        if imagem is None:
            return b""
        try:
            import cv2
            h, w = imagem.shape[:2]
            if w > 900:
                imagem = cv2.resize(imagem, (900, int(h * 900 / w)))
            ok, buf = cv2.imencode(".jpg", imagem, [cv2.IMWRITE_JPEG_QUALITY, 85])
            return buf.tobytes() if ok else b""
        except Exception:
            return b""

    def _pronto(self, d: dict) -> None:
        self._ocupado = False
        for b in self._btns:
            b.setEnabled(True)
        self._refresh_motion()
        msg = str(d.get("msg") or "")
        self._status.setText(msg)
        jpg = d.get("jpeg") or b""
        if jpg:
            pix = QPixmap()
            if pix.loadFromData(jpg):
                pix = pix.scaled(self._OW - 44, 230, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
                self._previa.setPixmap(pix)
                self._previa.setFixedHeight(pix.height() + 4)
                self._previa.show()
        else:
            self._previa.hide()
        self._res_texto = str(d.get("texto") or "")
        self._res_link = str(d.get("link") or "")
        tem_texto = bool(self._res_texto.strip())
        self._out.setVisible(tem_texto)
        if tem_texto:
            self._out.setPlainText(self._res_texto)
        self._b_copiar.setVisible(tem_texto)
        self._b_bloco.setVisible(tem_texto and bool(d.get("bloco", True)))
        self._b_link.setVisible(bool(self._res_link))
        if self._log_fn and msg:
            try:
                self._log_fn(f"SYS: 👁 {msg}")
            except Exception:
                pass
        self._ajustar()

    def _ajustar(self) -> None:
        lay = self.layout()
        lay.activate()
        h = lay.heightForWidth(self.width()) if lay.hasHeightForWidth() else -1
        if h <= 0:
            h = lay.sizeHint().height()
        p = self.parentWidget()
        if p is not None:
            h = min(h, p.height() - 8)
        centro = self.geometry().center().y()
        self.resize(self.width(), h)
        if p is not None and self.isVisible():
            self.move(self.x(), max(4, min(centro - h // 2, p.height() - h - 4)))

    # ── OpenCV ──────────────────────────────────────────────────────────────

    def _run(self, params: dict) -> None:
        tela = params.get("angle") == "screen"
        if params.get("action") == "motion":
            aviso = "Desligando a vigia…" if params.get("op") == "stop" else "Abrindo a câmera…"
        else:
            aviso = "Olhando a tela…" if tela else "Abrindo a câmera (um segundinho para a luz ajustar)…"
        if not self._comecar(aviso):
            return
        ocultar = self._ocultar_fn() if tela else None
        avisar = self._log_fn

        def _trabalho():
            try:
                from actions.computer_vision import executar
                r = executar(dict(params), ocultar=ocultar, forcar_ocultar=bool(ocultar), avisar=avisar)
            except Exception as e:
                r = {"msg": f"A visão falhou: {e}", "imagem": None, "texto": "", "link": ""}
            self._emitir({"msg": r.get("msg"), "jpeg": self._jpeg(r.get("imagem")),
                          "texto": r.get("texto"), "link": r.get("link"),
                          "bloco": params.get("action") == "qr"})

        threading.Thread(target=_trabalho, daemon=True, name="painel-visao").start()

    def _vigiar(self) -> None:
        self._run({"action": "motion", "op": "start", "sensitivity": int(self._sens.currentData()),
                   "cooldown_seconds": 30})

    def _refresh_motion(self) -> None:
        try:
            from actions.computer_vision import _vigia
            ligada = _vigia.ativo
            if ligada:
                txt = f"🔴  {_vigia.status().capitalize()}"
                if _vigia.ultima_foto:
                    txt += f" — foto: {_vigia.ultima_foto.name}"
                cor = C.MUTED_C
            else:
                txt, cor = "Desligada. Escolha a sensibilidade e clique em VIGIAR.", C.TEXT_MED
            self._motion_line.setText(txt)
            self._motion_line.setStyleSheet(f"color: {cor};")
            if not self._ocupado:
                self._mot_on.setEnabled(not ligada)
                self._mot_off.setEnabled(ligada)
                self._sens.setEnabled(not ligada)
        except Exception as e:
            self._motion_line.setText(f"A vigia não está disponível: {e}")

    def _abrir_fotos(self) -> None:
        try:
            from actions.computer_vision import _pasta_fotos
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(_pasta_fotos())))
        except Exception as e:
            self._status.setText(f"Não consegui abrir a pasta das fotos: {e}")

    # ── ler e descrever (visão local) ───────────────────────────────────────

    def _ver_situacao(self) -> None:
        try:
            from core import visao_local as V
            s = V.situacao()
            nomes = {"windows": "OCR do Windows", "rapidocr": "RapidOCR"}
            ocr = " + ".join(nomes[m] for m in s["ocr"]) or "não instalado"
            desc = s["modelo"] or "não instalado"
            texto = f"Ler texto: {ocr}   ·   Descrever: {desc}"
            if not s["modelo"] and s.get("aviso"):
                texto += f"\n{s['aviso']}"
        except Exception as e:
            texto = f"Ler e descrever indisponível: {e}"
        try:
            self._sit_sig.emit(texto)
        except RuntimeError:
            pass

    def _run_local(self, acao: str) -> None:
        if not self._comecar("Saindo da frente para olhar a janela que está atrás…"):
            return
        ocultar = self._ocultar_fn()

        def _trabalho():
            import time as _t
            from core import visao_local as V
            d = {"msg": "", "jpeg": b"", "texto": "", "link": "", "bloco": True}
            try:
                if ocultar:
                    ocultar(True)
                    _t.sleep(0.65)
                try:
                    img, nome = V.capturar("janela")
                finally:
                    if ocultar:
                        ocultar(False)
                nome = "janela" if nome == "janela da frente" else nome
                if acao == "read_text":
                    r = V.ocr(img)
                    d["texto"] = r["texto"].strip()
                    d["msg"] = ((f"Li {len(r['linhas'])} linha(s) na {nome} · {r['motor']} · "
                                 f"{r['ms'] / 1000:.1f} s").replace(".", ",", 1)
                                if d["texto"] else f"Não achei texto legível na {nome}.")
                else:
                    r = V.descrever(img)
                    d["texto"] = r["texto"]
                    d["msg"] = f"Descrição da {nome} · {r['modelo']} · {r['ms'] / 1000:.1f} s"
                try:
                    import numpy as np
                    d["jpeg"] = self._jpeg(np.asarray(img.convert("RGB"))[:, :, ::-1].copy())
                except Exception:
                    pass
            except Exception as e:
                d["msg"] = f"Não consegui: {e}"
            self._emitir(d)

        threading.Thread(target=_trabalho, daemon=True, name="painel-visao-local").start()

    # ── botões do resultado ─────────────────────────────────────────────────

    def _copiar(self) -> None:
        if self._res_texto:
            QApplication.clipboard().setText(self._res_texto)
            self._status.setText("Copiado para a área de transferência.")

    def _abrir_link(self) -> None:
        if self._res_link:
            QDesktopServices.openUrl(QUrl(self._res_link))

    def _para_bloco(self) -> None:
        if not self._res_texto:
            return
        try:
            from actions.notepad import notepad
            self._status.setText(notepad({"action": "write", "text": self._res_texto + "\n",
                                          "title": "texto da visão"}))
        except Exception as e:
            self._status.setText(f"Não consegui abrir no Bloco de Notas: {e}")


class IntelOverlay(_HudOverlay):
    """Live system intel — CPU, RAM, disk, battery, uptime, top processes.

    Everything here comes from psutil and runs locally. If psutil is not
    installed the panel says so instead of dying."""

    _OW = 380

    def __init__(self, parent=None, log=None):
        super().__init__(parent)
        self._log_fn = log
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            IntelOverlay {{
                background: rgba(8, 10, 28, 246);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._OW)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)

        def _lbl(txt, fs=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt); w.setAlignment(align)
            w.setFont(QFont(FONT_MAIN, fs,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        head = QHBoxLayout()
        head.addWidget(_lbl("📊  SISTEMA", 12, True))
        head.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setFont(QFont(FONT_MAIN, 9))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                          border: none; }}
            QPushButton:hover {{ color: {C.TEXT}; }}
        """)
        close_btn.clicked.connect(self._close_panel)
        head.addWidget(close_btn)
        lay.addLayout(head)

        self._body = QLabel("…")
        self._body.setFont(QFont(FONT_MAIN, 8))
        self._body.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._body.setWordWrap(True)
        self._body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self._body)

        refresh_btn = QPushButton("🔄  ATUALIZAR")
        refresh_btn.setFixedHeight(30)
        refresh_btn.setFont(QFont(FONT_MAIN, 8))
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setStyleSheet(f"""
            QPushButton {{ background: {C.PANEL2}; color: {C.TEXT};
                          border: 1px solid {C.BORDER_B};
                          border-radius: 4px; padding: 2px 6px; }}
            QPushButton:hover {{ border-color: {C.PRI_DIM}; }}
        """)
        refresh_btn.clicked.connect(self._refresh)
        lay.addWidget(refresh_btn)
        lay.addStretch()
        self._refresh()

    def _close_panel(self):
        self.hide()
        self.deleteLater()

    def _refresh(self):
        try:
            import psutil
        except ImportError:
            self._body.setText("O psutil não está instalado — rode "
                                "pip install psutil.")
            return
        cpu = psutil.cpu_percent(interval=0.4)
        vm = psutil.virtual_memory()
        try:
            disk = psutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\" if os.name == "nt" else "/")
        except Exception:
            disk = psutil.disk_usage(str(Path.home()))
        try:
            batt = psutil.sensors_battery()
        except Exception:
            batt = None
        import datetime as _dt
        up = _dt.datetime.now() - _dt.datetime.fromtimestamp(psutil.boot_time())
        lines = [
            f"CPU  —  {cpu:.0f}%  ({psutil.cpu_count(logical=False)} núcleos / "
            f"{psutil.cpu_count()} threads)",
            f"MEMÓRIA  —  {vm.used / (1 << 30):.1f} / {vm.total / (1 << 30):.1f} GB "
            f"({vm.percent:.0f}%)",
            f"DISCO  —  {disk.used / (1 << 30):.0f} / {disk.total / (1 << 30):.0f} GB "
            f"({disk.percent:.0f}%)",
            f"BATERIA — " + (f"{batt.percent:.0f}% "
                             f"({'carregando' if batt.power_plugged else 'na bateria'})"
                             if batt else "tomada (sem bateria)"),
            f"TEMPO LIGADO — {up.days}d {up.seconds // 3600}h {(up.seconds // 60) % 60}m",
            "",
            "PRINCIPAIS PROCESSOS (MEMÓRIA):",
        ]
        procs = []
        for p in psutil.process_iter(["name", "memory_info"]):
            try:
                mi = p.info["memory_info"]
                if mi and p.info["name"]:
                    procs.append((mi.rss, p.info["name"]))
            except Exception:
                continue
        for rss, name in sorted(procs, reverse=True)[:5]:
            lines.append(f"  • {name[:28]}  {rss / (1 << 20):.0f} MB")
        self._body.setText("\n".join(lines))
        if self._log_fn:
            try:
                self._log_fn("SYS: system intel refreshed")
            except Exception:
                pass


class ClipOverlay(_HudOverlay):
    """Clipboard manager — keeps the last 20 copies and lets you put any of
    them back. History lives in memory only: nothing sensitive is written to
    disk, and clearing the panel clears the history."""

    _OW = 380

    def __init__(self, parent=None, log=None, history=None):
        super().__init__(parent)
        self._log_fn = log
        self._history = history if history is not None else []
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ClipOverlay {{
                background: rgba(8, 10, 28, 246);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._OW)

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(20, 16, 20, 16)
        self._lay.setSpacing(8)

        def _lbl(txt, fs=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt); w.setAlignment(align)
            w.setFont(QFont(FONT_MAIN, fs,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        head = QHBoxLayout()
        head.addWidget(_lbl("📋  ÁREA DE TRANSFERÊNCIA", 12, True))
        head.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setFont(QFont(FONT_MAIN, 9))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                          border: none; }}
            QPushButton:hover {{ color: {C.TEXT}; }}
        """)
        close_btn.clicked.connect(self._close_panel)
        head.addWidget(close_btn)
        self._lay.addLayout(head)

        self._hint = QLabel("Clique em um item para copiar de novo. Os mais novos primeiro; "
                            "o histórico fica só na memória.")
        self._hint.setFont(QFont(FONT_MAIN, 8))
        self._hint.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._hint.setWordWrap(True)
        self._lay.addWidget(self._hint)

        self._list_host = QVBoxLayout()
        self._list_host.setSpacing(4)
        self._lay.addLayout(self._list_host)

        clear_btn = QPushButton("🗑  LIMPAR HISTÓRICO")
        clear_btn.setFixedHeight(30)
        clear_btn.setFont(QFont(FONT_MAIN, 8))
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet(f"""
            QPushButton {{ background: {C.PANEL2}; color: {C.TEXT};
                          border: 1px solid {C.BORDER_B};
                          border-radius: 4px; padding: 2px 6px; }}
            QPushButton:hover {{ border-color: {C.RED}; }}
        """)
        clear_btn.clicked.connect(self._clear)
        self._lay.addWidget(clear_btn)
        self._lay.addStretch()
        self._rebuild()

    def _close_panel(self):
        self.hide()
        self.deleteLater()

    def _clear(self):
        self._history.clear()
        self._rebuild()
        if self._log_fn:
            try:
                self._log_fn("SYS: clipboard history cleared")
            except Exception:
                pass

    def _copy_back(self, text: str):
        from PyQt6.QtWidgets import QApplication as _QApp
        clip = _QApp.clipboard()
        clip.setText(text)
        if self._log_fn:
            try:
                self._log_fn("SYS: clipboard item restored")
            except Exception:
                pass

    def _rebuild(self):
        while self._list_host.count():
            item = self._list_host.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        if not self._history:
            empty = QLabel("Nada copiado ainda — copie algo em qualquer lugar "
                           "e aparece aqui.")
            empty.setFont(QFont(FONT_MAIN, 8))
            empty.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            empty.setWordWrap(True)
            self._list_host.addWidget(empty)
            return
        for idx, text in enumerate(self._history):
            short = text.replace("\n", " ⏎ ")
            if len(short) > 72:
                short = short[:72] + "…"
            b = QPushButton(f"{len(self._history) - idx}.  {short}")
            b.setFixedHeight(26)
            b.setFont(QFont(FONT_MAIN, 8))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{ background: {C.PANEL2}; color: {C.TEXT};
                              border: 1px solid {C.BORDER_B};
                              border-radius: 4px; padding: 2px 8px;
                              text-align: left; }}
                QPushButton:hover {{ border-color: {C.PRI_DIM}; }}
            """)
            b.clicked.connect(lambda _t=text: self._copy_back(_t))
            self._list_host.addWidget(b)


class CommandsOverlay(_HudOverlay):
    """Every voice command the assistant knows, discovered live from the
    action modules' TOOL declarations — new tools appear here automatically."""

    _OW = 440
    _OH = 560

    def __init__(self, parent=None, adicionar: bool = False):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            CommandsOverlay {{
                background: rgba(8, 10, 28, 246);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self.setFixedSize(self._OW, self._OH)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)

        head = QHBoxLayout()
        ttl = QLabel("📖  TODOS OS COMANDOS")
        ttl.setFont(QFont(FONT_MAIN, 12, QFont.Weight.Bold))
        ttl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        head.addWidget(ttl)
        head.addStretch()
        add_btn = QPushButton("＋  Adicionar comando")
        add_btn.setFixedHeight(24)
        add_btn.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(f"""
            QPushButton {{ background: {C.PANEL2}; color: {C.PRI};
                          border: 1px solid {C.BORDER_B}; border-radius: 4px; padding: 0 8px; }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.PRI}; }}
        """)
        add_btn.clicked.connect(self._toggle_form)
        head.addWidget(add_btn)
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setFont(QFont(FONT_MAIN, 9))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                          border: none; }}
            QPushButton:hover {{ color: {C.TEXT}; }}
        """)
        close_btn.clicked.connect(self._close_panel)
        head.addWidget(close_btn)
        lay.addLayout(head)

        # 2.3 — formulário "Adicionar comando" (escondido até clicar no botão)
        self._form = QFrame()
        self._form.setStyleSheet(f"""
            QFrame {{ background: {C.PANEL}; border: 1px solid {C.BORDER_B}; border-radius: 4px; }}
            QLabel {{ border: none; background: transparent; }}
        """)
        fl = QVBoxLayout(self._form)
        fl.setContentsMargins(10, 8, 10, 8)
        fl.setSpacing(5)
        edit_css = f"""
            QLineEdit {{ background: {C.PANEL2}; color: {C.TEXT};
                        border: 1px solid {C.BORDER_B}; border-radius: 4px; padding: 5px 8px; }}
            QLineEdit:focus {{ border-color: {C.PRI_DIM}; }}
        """
        from core import comandos_usuario as _cu
        self._frase = QLineEdit()
        self._frase.setPlaceholderText("Quando eu disser… (ex.: modo cinema)")
        self._frase.setMaxLength(_cu.MAX_FRASE)
        self._frase.setFont(QFont(FONT_MAIN, 9))
        self._frase.setStyleSheet(edit_css)
        self._pedido = QLineEdit()
        self._pedido.setPlaceholderText("…o NEXUS faz (ex.: abre a Netflix e baixa o volume para 30)")
        self._pedido.setMaxLength(_cu.MAX_PEDIDO)
        self._pedido.setFont(QFont(FONT_MAIN, 9))
        self._pedido.setStyleSheet(edit_css)
        self._pedido.returnPressed.connect(self._salvar_comando)
        self._frase.returnPressed.connect(self._pedido.setFocus)
        fl.addWidget(self._frase)
        fl.addWidget(self._pedido)
        row = QHBoxLayout()
        self._form_msg = QLabel("Vale digitado na hora; por voz, na próxima conexão.")
        self._form_msg.setWordWrap(True)
        self._form_msg.setFont(QFont(FONT_MAIN, 7))
        self._form_msg.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        row.addWidget(self._form_msg, 1)
        save_btn = QPushButton("Salvar")
        save_btn.setFixedHeight(26)
        save_btn.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{ background: {C.PRI_GHO}; color: {C.PRI};
                          border: 1px solid {C.PRI_DIM}; border-radius: 4px; padding: 0 12px; }}
            QPushButton:hover {{ border-color: {C.PRI}; }}
        """)
        save_btn.clicked.connect(self._salvar_comando)
        row.addWidget(save_btn)
        fl.addLayout(row)
        self._form.setVisible(False)
        lay.addWidget(self._form)

        # 2.3 — comandos que o usuário criou, com botão de apagar
        self._meus_box = QVBoxLayout()
        self._meus_box.setSpacing(3)
        lay.addLayout(self._meus_box)

        self._view = QTextEdit()
        self._view.setReadOnly(True)
        self._view.setFont(QFont(FONT_MAIN, 8))
        self._view.setStyleSheet(f"""
            QTextEdit {{ background: {C.PANEL}; color: {C.TEXT_MED};
                        border: 1px solid {C.BORDER_B};
                        border-radius: 4px; padding: 8px; }}
        """)
        lay.addWidget(self._view)
        self._rebuild_meus()
        self._rebuild()
        if adicionar:
            self._toggle_form()

    def _close_panel(self):
        self.hide()
        self.deleteLater()

    def _toggle_form(self):
        aberto = not self._form.isVisible()
        self._form.setVisible(aberto)
        if aberto:
            self._frase.setFocus()

    def _salvar_comando(self):
        from core import comandos_usuario as _cu
        erro = _cu.adicionar(self._frase.text(), self._pedido.text())
        if erro:
            self._form_msg.setText(erro)
            self._form_msg.setStyleSheet(f"color: {C.MUTED_C}; background: transparent; border: none;")
            return
        self._form_msg.setText(f"Salvo: “{self._frase.text().strip()}”.")
        self._form_msg.setStyleSheet(f"color: {C.GREEN}; background: transparent; border: none;")
        self._frase.clear()
        self._pedido.clear()
        self._frase.setFocus()
        self._rebuild_meus()
        self._rebuild()

    def _apagar_comando(self, i: int):
        from core import comandos_usuario as _cu
        _cu.remover(i)
        self._rebuild_meus()
        self._rebuild()

    def _rebuild_meus(self):
        from core import comandos_usuario as _cu
        while self._meus_box.count():
            w = self._meus_box.takeAt(0).widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        cmds = _cu.listar()
        if not cmds:
            return
        sec = QLabel(f"MEUS COMANDOS ({len(cmds)})")
        sec.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        sec.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent;")
        self._meus_box.addWidget(sec)
        # Mostra só os últimos 5 para não esconder a lista toda; o resto rola na lista abaixo.
        for i, c in list(enumerate(cmds))[-5:]:
            fr = QFrame()
            fr.setStyleSheet(f"QFrame {{ background: {C.PANEL2}; border: 1px solid {C.BORDER};"
                             f" border-radius: 4px; }} QLabel {{ border: none; background: transparent; }}")
            h = QHBoxLayout(fr)
            h.setContentsMargins(8, 2, 2, 2)
            t = QLabel(f"⚡ {c['phrase']}  →  {c['command']}")
            t.setFont(QFont(FONT_MAIN, 8))
            t.setStyleSheet(f"color: {C.TEXT};")
            t.setToolTip(c["command"])
            h.addWidget(t, 1)
            d = QPushButton("✕")
            d.setFixedSize(22, 22)
            d.setCursor(Qt.CursorShape.PointingHandCursor)
            d.setToolTip("Apagar este comando")
            d.setStyleSheet(f"QPushButton {{ background: transparent; color: {C.TEXT_DIM}; border: none; }}"
                            f"QPushButton:hover {{ color: {C.MUTED_C}; }}")
            d.clicked.connect(lambda _=False, k=i: self._apagar_comando(k))
            h.addWidget(d)
            self._meus_box.addWidget(fr)

    def _rebuild(self):
        """Lista as funções SEM rodar os arquivos de novo.

        Até a 1.3 cada abertura da lista executava todos os actions/*.py outra
        vez (e qualquer coisa que eles fizessem ao carregar — abrir threads,
        ler arquivos — acontecia de novo; um arquivo que encerrasse ao carregar
        derrubava o NEXUS). Agora o nome e a descrição saem do módulo já
        carregado ou, se não estiver carregado, da leitura do texto (ast)."""
        import ast
        import sys as _sys
        from ..comandos_pt import COMANDOS
        from core import comandos_usuario as _cu
        actions_dir = _base_dir() / "actions"
        blocks = [f"⚡ {c['phrase']} — {c['command']}\n    (meu comando)" for c in _cu.listar()]
        for p in sorted(actions_dir.glob("*.py")):
            if p.stem.startswith("_"):
                continue
            nome = desc = ""
            mod = _sys.modules.get(f"actions.{p.stem}")
            t = getattr(mod, "TOOL", None) if mod is not None else None
            if isinstance(t, dict):
                nome, desc = str(t.get("name") or ""), str(t.get("description") or "")
            else:
                try:
                    arvore = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
                    for n in ast.walk(arvore):
                        if (isinstance(n, ast.Assign) and isinstance(n.value, ast.Dict)
                                and any(getattr(x, "id", "") == "TOOL" for x in n.targets)):
                            for k, v in zip(n.value.keys, n.value.values):
                                if isinstance(k, ast.Constant) and k.value in ("name", "description"):
                                    try:
                                        val = ast.literal_eval(v)
                                    except Exception:
                                        continue
                                    if k.value == "name":
                                        nome = str(val)
                                    else:
                                        desc = str(val)
                except Exception:
                    continue
            if not nome:
                continue
            pt = COMANDOS.get(nome)
            if pt:
                titulo, d, exemplo = pt
                blocks.append(f"▸ {titulo} — {d}\n    ex.: “{exemplo}”")
            else:
                blocks.append(f"▸ {nome} — {desc.strip().split('. ')[0]}")
        self._view.setPlainText("\n\n".join(blocks) if blocks
                                else "Nenhuma função encontrada.")


class NotesOverlay(_HudOverlay):
    """Visual notes & reminders manager — the same config/quick_notes.json
    the voice commands use, now with a panel: read, add, delete, clear.

    The file is shared, so a note typed here is spoken back by 'list my
    notes' and vice versa."""

    _OW = 380
    _OH = 470

    def __init__(self, parent=None, log=None):
        super().__init__(parent)
        self._log_fn = log
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            NotesOverlay {{
                background: rgba(8, 10, 28, 246);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self.setFixedSize(self._OW, self._OH)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)

        head = QHBoxLayout()
        ttl = QLabel("📝  NOTAS RÁPIDAS")
        ttl.setFont(QFont(FONT_MAIN, 12, QFont.Weight.Bold))
        ttl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        head.addWidget(ttl)
        head.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setFont(QFont(FONT_MAIN, 9))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                          border: none; }}
            QPushButton:hover {{ color: {C.TEXT}; }}
        """)
        close_btn.clicked.connect(self._close_panel)
        head.addWidget(close_btn)
        lay.addLayout(head)

        # add row
        row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("Escreva uma nota e aperte Enter…")
        self._input.setFont(QFont(FONT_MAIN, 9))
        self._input.setStyleSheet(f"""
            QLineEdit {{ background: {C.PANEL2}; color: {C.TEXT};
                        border: 1px solid {C.BORDER_B};
                        border-radius: 4px; padding: 6px 8px; }}
            QLineEdit:focus {{ border-color: {C.PRI_DIM}; }}
        """)
        self._input.returnPressed.connect(self._add_note)
        row.addWidget(self._input)
        add_btn = QPushButton("＋")
        add_btn.setFixedSize(34, 30)
        add_btn.setFont(QFont(FONT_MAIN, 11))
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(f"""
            QPushButton {{ background: {C.PANEL2}; color: {C.PRI};
                          border: 1px solid {C.BORDER_B};
                          border-radius: 4px; }}
            QPushButton:hover {{ border-color: {C.PRI_DIM}; }}
        """)
        add_btn.clicked.connect(self._add_note)
        row.addWidget(add_btn)
        lay.addLayout(row)

        # scroll list
        from PyQt6.QtWidgets import QScrollArea
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: {C.PANEL}; width: 6px;
                                  border-radius: 3px; }}
            QScrollBar::handle:vertical {{ background: {C.BORDER_B};
                                           border-radius: 3px; min-height: 30px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        self._list_host = QWidget()
        self._list_host.setStyleSheet("background: transparent;")
        self._list_lay = QVBoxLayout(self._list_host)
        self._list_lay.setContentsMargins(0, 4, 0, 4)
        self._list_lay.setSpacing(4)
        self._list_lay.addStretch()
        self._scroll.setWidget(self._list_host)
        lay.addWidget(self._scroll)

        clear_btn = QPushButton("🗑  APAGAR TODAS")
        clear_btn.setFixedHeight(28)
        clear_btn.setFont(QFont(FONT_MAIN, 8))
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet(f"""
            QPushButton {{ background: {C.PANEL2}; color: {C.TEXT};
                          border: 1px solid {C.BORDER_B};
                          border-radius: 4px; }}
            QPushButton:hover {{ border-color: {C.RED}; }}
        """)
        clear_btn.clicked.connect(self._clear_all)
        lay.addWidget(clear_btn)
        self._rebuild()

    # ── same file the voice commands use ────────────────────────────────────

    def _load_notes(self) -> list:
        try:
            from actions.quick_notes import _load
            return _load()
        except Exception:
            try:
                return json.loads(
                    Path("config/quick_notes.json").read_text(encoding="utf-8"))
            except Exception:
                return []

    def _save_notes(self, notes: list) -> None:
        try:
            from actions.quick_notes import _save
            _save(notes)
            return
        except Exception:
            pass
        try:
            Path("config/quick_notes.json").parent.mkdir(parents=True,
                                                        exist_ok=True)
            Path("config/quick_notes.json").write_text(
                json.dumps(notes[-200:], indent=1, ensure_ascii=False),
                encoding="utf-8")
        except Exception:
            pass

    def _when(self, at: float) -> str:
        diff = time.time() - at
        if diff < 60:
            return "agora mesmo"
        if diff < 3600:
            return f"há {int(diff // 60)} min"
        if diff < 86400:
            return f"há {int(diff // 3600)} h"
        d = int(diff // 86400)
        return f"há {d} dias" if d != 1 else "ontem"

    # ── actions ─────────────────────────────────────────────────────────────

    def _close_panel(self):
        self.hide()
        self.deleteLater()

    def _add_note(self):
        text = self._input.text().strip()
        if not text:
            return
        notes = self._load_notes()
        notes.append({"text": text[:500], "at": time.time()})
        self._save_notes(notes)
        self._input.clear()
        if self._log_fn:
            try:
                self._log_fn(f"SYS: 📝 Nota salva — {text[:60]}")
            except Exception:
                pass
        self._rebuild()

    def _delete_note(self, idx_newest_first: int):
        notes = self._load_notes()
        idx = len(notes) - 1 - idx_newest_first      # newest-first → real index
        if 0 <= idx < len(notes):
            notes.pop(idx)
            self._save_notes(notes)
        self._rebuild()

    def _clear_all(self):
        self._save_notes([])
        if self._log_fn:
            try:
                self._log_fn("SYS: 📝 Todas as notas foram apagadas.")
            except Exception:
                pass
        self._rebuild()

    def _rebuild(self):
        while self._list_lay.count() > 1:           # keep the stretch
            item = self._list_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        notes = self._load_notes()
        if not notes:
            empty = QLabel("Nenhuma nota ainda — escreva uma acima ou peça por voz.")
            empty.setFont(QFont(FONT_MAIN, 8))
            empty.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            empty.setWordWrap(True)
            self._list_lay.insertWidget(0, empty)
            return
        for i, n in enumerate(reversed(notes)):      # newest first
            text = str(n.get("text", "")) if isinstance(n, dict) else str(n)
            when = self._when(n.get("at", 0)) if isinstance(n, dict) else ""
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{ background: {C.PANEL2};
                          border: 1px solid {C.BORDER_B};
                          border-radius: 4px; }}
            """)
            cl = QHBoxLayout(card)
            cl.setContentsMargins(8, 6, 4, 6)
            cl.setSpacing(6)
            body = QVBoxLayout()
            body.setSpacing(2)
            t = QLabel(text)
            t.setFont(QFont(FONT_MAIN, 9))
            t.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
            t.setWordWrap(True)
            body.addWidget(t)
            if when:
                sub = QLabel(when)
                sub.setFont(QFont(FONT_MAIN, 7))
                sub.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
                body.addWidget(sub)
            cl.addLayout(body)
            del_btn = QPushButton("✕")
            del_btn.setFixedSize(22, 22)
            del_btn.setFont(QFont(FONT_MAIN, 8))
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setStyleSheet(f"""
                QPushButton {{ background: transparent;
                              color: {C.TEXT_DIM}; border: none; }}
                QPushButton:hover {{ color: {C.RED}; }}
            """)
            del_btn.clicked.connect(lambda _i=i: self._delete_note(_i))
            cl.addWidget(del_btn)
            self._list_lay.insertWidget(i, card)
