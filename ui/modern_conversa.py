"""A conversa em balões (ChatLog).

Parte de ui/modern.py (dividido na 4.6.0 — sem mudança de comportamento)."""
from __future__ import annotations

from ._qt import *  # noqa: F401,F403
from ._base import C, FONT_MAIN, _persist_activity, accent2, mix, qcol, agora  # noqa: F401
from .modern_base import _font

# ══════════════════════════════════════════════════════════════════════════
#  CONVERSA
# ══════════════════════════════════════════════════════════════════════════

class _Bubble(QFrame):
    """Um balão da conversa: cabeçalho pequeno (quem · hora) + texto."""

    def __init__(self, tag: str, who: str, text: str):
        super().__init__()
        self.tag = tag
        self.full_text = text
        self.setObjectName(f"bub_{tag}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(11, 7, 11, 8)
        lay.setSpacing(2)
        if who:
            self.meta = QLabel(f"{who}  ·  {agora().strftime('%H:%M')}")
            self.meta.setFont(_font(6.8, QFont.Weight.Bold, 1.2))
            self.meta.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
            if tag == "you":
                self.meta.setAlignment(Qt.AlignmentFlag.AlignRight)
            lay.addWidget(self.meta)
        else:
            self.meta = None
        self.body = QLabel("")
        self.body.setWordWrap(True)
        self.body.setTextFormat(Qt.TextFormat.PlainText)
        self.body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.body.setFont(_font(9.4))
        colour = {"you": C.WHITE, "ai": C.TEXT, "err": C.RED, "file": C.GREEN}.get(tag, C.TEXT)
        self.body.setStyleSheet(f"color: {colour}; background: transparent; border: none;")
        lay.addWidget(self.body)

        if tag == "you":
            ss = f"QFrame#bub_you {{ background: {C.PRI_GHO}; border: 1px solid {C.BORDER_B}; border-radius: 16px; }}"
        elif tag == "ai":
            ss = (f"QFrame#bub_ai {{ background: {C.PANEL2}; border: 1px solid {C.BORDER};"
                  f" border-left: 3px solid {C.PRI}; border-radius: 16px; }}")
        elif tag == "err":
            ss = (f"QFrame#bub_err {{ background: {qcol(C.RED, 22).name(QColor.NameFormat.HexArgb)};"
                  f" border: 1px solid {C.RED}; border-radius: 10px; }}")
        else:  # file
            ss = (f"QFrame#bub_file {{ background: {qcol(C.GREEN, 18).name(QColor.NameFormat.HexArgb)};"
                  f" border: 1px solid {C.GREEN_D}; border-radius: 10px; }}")
        self.setStyleSheet(ss)

    def fit(self, max_w: int) -> None:
        """Balão do tamanho do texto, quebrando linha só quando precisa."""
        self.body.ensurePolished()
        fm = self.body.fontMetrics()
        natural = max((fm.horizontalAdvance(l) for l in self.full_text.split("\n")), default=40) + 6
        if self.meta is not None:
            self.meta.ensurePolished()
            natural = max(natural, self.meta.fontMetrics().horizontalAdvance(self.meta.text()) + 6)
        self.body.setFixedWidth(max(40, min(natural, max_w - 24)))


class ChatLog(QScrollArea):
    """A conversa em balões.

    Mesma interface do LogWidget antigo — append_log(texto) e _ai_name_lc —
    então o resto do NEXUS não precisa saber que mudou. Linhas "You: ..." viram
    balões à direita, "NEXUS: ..." balões à esquerda (com efeito de digitação),
    "FILE: ..." um selo verde, "ERR..." um aviso vermelho e o resto (SYS) uma
    linha discreta no meio.
    """

    _sig = pyqtSignal(str)
    MAX_ROWS = 260

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ai_name_lc = "nexus"
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setObjectName("ChatLog")
        self.setStyleSheet(f"""
            QScrollArea#ChatLog {{
                background: {C.PANEL}; border: 1px solid {C.BORDER}; border-radius: 10px;
            }}
            QWidget#ChatHost {{ background: transparent; }}
            QScrollBar:vertical {{ background: transparent; width: 7px; margin: 6px 2px; }}
            QScrollBar::handle:vertical {{ background: {C.BORDER_B}; border-radius: 3px; min-height: 24px; }}
            QScrollBar::handle:vertical:hover {{ background: {C.PRI_DIM}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
        """)
        self._host = QWidget()
        self._host.setObjectName("ChatHost")
        self._lay = QVBoxLayout(self._host)
        self._lay.setContentsMargins(8, 10, 8, 10)
        self._lay.setSpacing(7)
        self._lay.addStretch(1)
        self.setWidget(self._host)

        self._empty = QLabel("A conversa aparece aqui.\nFale com o NEXUS ou digite um comando abaixo.")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setWordWrap(True)
        self._empty.setFont(_font(8.4))
        self._empty.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._lay.addWidget(self._empty)

        self._rows: list[QWidget] = []
        self._bubbles: list[_Bubble] = []
        self._sys_labels: list[QLabel] = []
        self._history: list[tuple[str, str]] = []   # (tag, texto) para copiar
        self._queue: list[str] = []
        self._typing: _Bubble | None = None
        self._busy = False       # uma única fila andando por vez
        self._pos = 0
        self._tmr = QTimer(self)
        self._tmr.setInterval(16)
        self._tmr.timeout.connect(self._step)
        self._sig.connect(self._enqueue)

        self._at_bottom = True
        bar = self.verticalScrollBar()
        bar.valueChanged.connect(lambda v: setattr(self, "_at_bottom", v >= bar.maximum() - 24))
        bar.rangeChanged.connect(lambda _a, mx: bar.setValue(mx) if self._at_bottom else None)
        self.viewport().installEventFilter(self)

    # ── interface pública (igual ao LogWidget) ──────────────────────────────

    def append_log(self, text: str) -> None:
        _persist_activity(text)
        self._sig.emit(str(text))

    def clear_view(self) -> None:
        self._queue.clear()
        self._tmr.stop()
        self._typing = None
        self._busy = False
        for row in self._rows:
            row.hide()
            row.deleteLater()
        self._rows.clear()
        self._bubbles.clear()
        self._sys_labels.clear()
        self._history.clear()
        self._empty.show()

    def plain_text(self) -> str:
        nome = self._ai_name_lc.upper() or "NEXUS"
        quem = {"you": "Você", "ai": nome, "file": "Arquivo", "err": "Erro"}
        return "\n".join(f"{quem.get(t, 'Sistema')}: {x}" for t, x in self._history)

    def message_count(self) -> int:
        return sum(1 for t, _ in self._history if t in ("you", "ai"))

    # ── internos ────────────────────────────────────────────────────────────

    def _classify(self, text: str) -> tuple[str, str]:
        tl = text.lower()
        ai_pfx = f"{self._ai_name_lc}:"
        if tl.startswith(("you:", "você:", "voce:")):
            return "you", text.split(":", 1)[1].strip()
        for pfx in (ai_pfx, "nexus:", "jarvis:"):
            if tl.startswith(pfx):
                return "ai", text[len(pfx):].strip()
        if tl.startswith(("file:", "arquivo:")):
            return "file", text.split(":", 1)[1].strip()
        if tl.startswith(("err:", "erro:")):
            return "err", text.split(":", 1)[1].strip()
        if tl.startswith("sys:"):
            return "sys", text[4:].strip()
        return "sys", text.strip()

    def _enqueue(self, text: str) -> None:
        self._queue.append(text)
        if not self._busy:
            self._busy = True
            QTimer.singleShot(0, self._next)

    def _max_w(self) -> int:
        return max(160, int(self.viewport().width() * 0.88))

    def _add_row(self, widget: QWidget, align: str) -> None:
        self._empty.hide()
        row = QWidget()
        row.setObjectName("crow")
        row.setStyleSheet("QWidget#crow { background: transparent; }")
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        if align in ("right", "center"):
            h.addStretch(1)
        h.addWidget(widget)
        if align in ("left", "center"):
            h.addStretch(1)
        self._lay.addWidget(row)
        self._rows.append(row)
        while len(self._rows) > self.MAX_ROWS:
            velho = self._rows.pop(0)
            for b in [b for b in self._bubbles if b.parent() is velho]:
                self._bubbles.remove(b)
            for l in [l for l in self._sys_labels if l.parent() is velho]:
                self._sys_labels.remove(l)
            velho.hide()
            velho.deleteLater()

    def _next(self) -> None:
        if not self._queue:
            self._typing = None
            self._busy = False
            return
        text = self._queue.pop(0)
        tag, disp = self._classify(text)
        if not disp:
            QTimer.singleShot(0, self._next)
            return
        self._history.append((tag, disp))
        self._history = self._history[-self.MAX_ROWS:]

        if tag == "sys":
            lbl = QLabel(disp)
            lbl.setWordWrap(True)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFont(_font(7.6))
            lbl.setTextFormat(Qt.TextFormat.PlainText)
            lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; padding: 0 6px;")
            lbl.ensurePolished()
            natural = lbl.fontMetrics().horizontalAdvance(disp) + 16
            lbl.setFixedWidth(max(60, min(natural, self._max_w())))
            self._sys_labels.append(lbl)
            self._add_row(lbl, "center")
            QTimer.singleShot(0, self._next)
            return

        who = {"you": "VOCÊ", "ai": (self._ai_name_lc or "nexus").upper()}.get(tag, "")
        if tag == "file":
            disp = f"📎  {disp}"
        elif tag == "err":
            disp = f"⚠  {disp}"
        bub = _Bubble(tag, who, disp)
        self._bubbles.append(bub)
        self._add_row(bub, {"you": "right", "ai": "left"}.get(tag, "center"))
        bub.fit(self._max_w())

        if tag == "ai" and len(self._queue) < 3:
            self._typing = bub
            self._pos = 0
            self._tmr.start()
        else:
            bub.body.setText(disp)
            QTimer.singleShot(0, self._next)

    def _step(self) -> None:
        bub = self._typing
        if bub is None:
            self._tmr.stop()
            return
        texto = bub.full_text
        passo = max(2, len(texto) // 70)
        if self._queue:
            passo *= 4                       # tem fila: acelera
        self._pos = min(len(texto), self._pos + passo)
        bub.body.setText(texto[: self._pos])
        if self._pos >= len(texto):
            self._tmr.stop()
            self._typing = None
            QTimer.singleShot(10, self._next)

    def eventFilter(self, obj, ev):
        if obj is self.viewport() and ev.type() == ev.Type.Resize:
            mw = self._max_w()
            for b in self._bubbles:
                b.fit(mw)
            for l in self._sys_labels:
                natural = l.fontMetrics().horizontalAdvance(l.text()) + 16
                l.setFixedWidth(max(60, min(natural, mw)))
        return super().eventFilter(obj, ev)
