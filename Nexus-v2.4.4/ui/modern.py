"""Peças visuais da versão 1.2 (visual novo).

- ChatLog ........ a CONVERSA em balões (substitui o antigo log de texto corrido)
- RingGauge ...... medidor em arco com degradê (CPU, memória)
- SparkMetric .... linha com gráfico de área (rede, GPU, temperatura)
- UptimeCard ..... tempo ligado (dias/horas/minutos) e barra de 7 dias
- ProcessList .... processos que mais pesam (por CPU ou por RAM)
- StatusCard ..... cartão de estado (núcleo, segurança, versão)
- QuickBar ....... barra de acesso rápido personalizável

Todas usam as cores da classe C em folhas de estilo, então a troca de cor ao
vivo (retheme_all_widgets) continua pintando tudo na hora.

Parte do pacote ui do NEXUS Pro.
"""
from __future__ import annotations

from ._qt import *  # noqa: F401,F403
from ._base import C, FONT_MAIN, _persist_activity, accent2, mix, qcol, agora  # noqa: F401


def _font(size: float, weight=QFont.Weight.Normal, spacing: float = 0.0) -> QFont:
    f = QFont(FONT_MAIN)
    f.setPointSizeF(size)
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return f


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
            ss = f"QFrame#bub_you {{ background: {C.PRI_GHO}; border: 1px solid {C.BORDER_B}; border-radius: 12px; }}"
        elif tag == "ai":
            ss = (f"QFrame#bub_ai {{ background: {C.PANEL2}; border: 1px solid {C.BORDER};"
                  f" border-left: 3px solid {C.PRI}; border-radius: 12px; }}")
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


# ══════════════════════════════════════════════════════════════════════════
#  MONITOR DE SISTEMA  (visual 2.2)
# ══════════════════════════════════════════════════════════════════════════

def _level_colour(value: float, base: str) -> QColor:
    """Passou de 65% fica âmbar, passou de 85% fica vermelho; senão, a cor própria."""
    if value > 85:
        return qcol(C.RED)
    if value > 65:
        return qcol(C.ACC)
    return qcol(base)


def _grad_ends(value: float, base: str) -> tuple[QColor, QColor]:
    """Início e fim do degradê de um medidor: acento → violeta; alerta muda tudo."""
    if value > 85:
        return qcol("#ff9a5c"), qcol(C.RED)
    if value > 65:
        return qcol(C.ACC2), qcol(C.ACC)
    return qcol(base), qcol(accent2(base))


def _lerp(c1: QColor, c2: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(int(c1.red() + (c2.red() - c1.red()) * t),
                  int(c1.green() + (c2.green() - c1.green()) * t),
                  int(c1.blue() + (c2.blue() - c1.blue()) * t),
                  int(c1.alpha() + (c2.alpha() - c1.alpha()) * t))


class RingGauge(QWidget):
    """Medidor em arco aberto (270°) com degradê e brilho.

    set_value(pct, texto, sub="") — `texto` vai no centro, `sub` embaixo do nome
    (ex.: "11,2/15,9 GB"). A agulha anima suave até o valor novo."""

    def __init__(self, label: str, color: str = None, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color            # None = segue o acento do tema
        self._value = 0.0
        self._shown = 0.0
        self._text = "--"
        self._sub = ""
        self.setFixedHeight(102)
        self.setMinimumWidth(70)
        self._anim = QTimer(self)
        self._anim.setInterval(30)
        self._anim.timeout.connect(self._ease)

    def set_value(self, pct: float, text: str, sub: str = "") -> None:
        v = max(0.0, min(100.0, float(pct)))
        if v == self._value and text == self._text and sub == self._sub:
            return
        self._value, self._text, self._sub = v, text, sub
        self._anim.start()
        self.update()

    def _ease(self) -> None:
        self._shown += (self._value - self._shown) * 0.22
        if abs(self._value - self._shown) < 0.3:
            self._shown = self._value
            self._anim.stop()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W = self.width()
        d = min(W - 14, 70)
        rect = QRectF((W - d) / 2, 6, d, d)
        a, b = _grad_ends(self._value, self._color or C.PRI)
        START, SPAN = 225.0, 270.0          # graus (Qt: 0° = 3h, anti-horário)

        # brilho suave atrás do arco
        glow = QRadialGradient(rect.center(), d * 0.62)
        g0 = QColor(b); g0.setAlpha(int(22 + 40 * self._shown / 100))
        g1 = QColor(b); g1.setAlpha(0)
        glow.setColorAt(0.0, g0); glow.setColorAt(1.0, g1)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(rect.adjusted(-8, -8, 8, 8))

        # trilho
        trilho = QPen(qcol(C.BAR_BG), 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(trilho)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(rect, int(START * 16), int(-SPAN * 16))

        # arco do valor, em pedaços para o degradê
        if self._shown > 0.4:
            total = SPAN * self._shown / 100.0
            n = max(2, int(total / 6))
            seg = total / n
            for i in range(n):
                cor = _lerp(a, b, (i + 0.5) / n)
                last = i == n - 1
                pen = QPen(cor, 7, Qt.PenStyle.SolidLine,
                           Qt.PenCapStyle.RoundCap if (i == 0 or last) else Qt.PenCapStyle.FlatCap)
                p.setPen(pen)
                p.drawArc(rect, int((START - i * seg) * 16), int(-(seg + 0.6) * 16))

        # valor no centro
        indisp = self._text in ("--", "N/D", "N/A")
        p.setPen(QPen(qcol(C.TEXT_DIM) if indisp else qcol(C.WHITE), 1))
        p.setFont(_font(11 if len(self._text) <= 4 else 9, QFont.Weight.Bold))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._text)

        # nome (com cor) e legenda
        p.setPen(QPen(a if not indisp else qcol(C.TEXT_DIM), 1))
        p.setFont(_font(7, QFont.Weight.Bold, 1.8))
        p.drawText(QRectF(0, rect.bottom() - 2, W, 14), Qt.AlignmentFlag.AlignCenter, self._label)
        if self._sub:
            p.setPen(QPen(qcol(C.TEXT_DIM), 1))
            p.setFont(_font(6.4))
            p.drawText(QRectF(0, rect.bottom() + 11, W, 12), Qt.AlignmentFlag.AlignCenter, self._sub)
        p.end()


class SparkMetric(QWidget):
    """Linha com nome, valor e um gráfico de área dos últimos ~80 s.

    set_value(pct, texto, sub="") — chamada a cada leitura; guarda o histórico
    sozinha (ou use set_history + push=False). `sub` aparece pequeno no canto do gráfico (ex.: ↓ 1,2  ↑ 0,3)."""

    def __init__(self, label: str, color: str = None, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color            # None = segue o acento do tema
        self._value = 0.0
        self._text = "--"
        self._sub = ""
        self._hist: list[float] = []
        self.setFixedHeight(46)
        self.setMinimumWidth(90)

    def set_history(self, hist) -> None:
        """Usa o histórico que o coletor já guarda (assim o gráfico nasce cheio)."""
        self._hist = [float(x) for x in hist][-40:]

    def set_value(self, pct: float, text: str, sub: str = "", push: bool = True) -> None:
        v = max(0.0, min(100.0, float(pct)))
        self._value, self._text, self._sub = v, text, sub
        if push and (not self._hist or self._hist[-1] != v):
            self._hist.append(v)
            if len(self._hist) > 40:
                self._hist.pop(0)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        a, b = _grad_ends(self._value, self._color or C.PRI)
        indisp = self._text in ("--", "N/A", "N/D")

        # bolinha de cor + nome
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(b if not indisp else qcol(C.TEXT_DIM)))
        p.drawEllipse(QPointF(5, 9), 2.6, 2.6)
        p.setPen(QPen(qcol(C.TEXT_MED), 1))
        p.setFont(_font(7, QFont.Weight.Bold, 1.6))
        p.drawText(QRectF(13, 1, W - 80, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._label)
        p.setPen(QPen(qcol(C.TEXT_DIM) if indisp else a, 1))
        p.setFont(_font(10, QFont.Weight.Bold))
        p.drawText(QRectF(W - 84, 0, 82, 18),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._text)

        # área do gráfico
        gx0, gx1, gy0, gy1 = 2.0, W - 2.0, 19.0, H - 2.0
        gw, gh = gx1 - gx0, gy1 - gy0
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(qcol(C.BAR_BG, 150)))
        p.drawRoundedRect(QRectF(gx0, gy0, gw, gh), 5, 5)

        hist = self._hist
        if len(hist) >= 2 and not indisp:
            step = gw / 39.0
            x0 = gx1 - step * (len(hist) - 1)
            pts = [QPointF(x0 + i * step, gy1 - 2 - (v / 100.0) * (gh - 5)) for i, v in enumerate(hist)]
            line = QPainterPath()
            line.moveTo(pts[0])
            for pt in pts[1:]:
                line.lineTo(pt)
            area = QPainterPath(line)
            area.lineTo(pts[-1].x(), gy1)
            area.lineTo(pts[0].x(), gy1)
            area.closeSubpath()
            p.save()
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(gx0, gy0, gw, gh), 5, 5)
            p.setClipPath(clip)
            fill = QLinearGradient(0, gy0, 0, gy1)
            f0 = QColor(b); f0.setAlpha(110)
            f1 = QColor(a); f1.setAlpha(6)
            fill.setColorAt(0.0, f0); fill.setColorAt(1.0, f1)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(fill))
            p.drawPath(area)
            lg = QLinearGradient(gx0, 0, gx1, 0)
            lg.setColorAt(0.0, a); lg.setColorAt(1.0, b)
            p.setPen(QPen(QBrush(lg), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(line)
            p.restore()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(qcol(C.WHITE)))
            p.drawEllipse(pts[-1], 2.4, 2.4)

        if self._sub:
            p.setPen(QPen(qcol(C.TEXT_MED, 210), 1))
            p.setFont(_font(6.4, QFont.Weight.DemiBold))
            p.drawText(QRectF(gx0 + 6, gy0 + 1, gw - 12, 13),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._sub)
        p.end()


CompactMetric = SparkMetric          # nome antigo, para quem ainda importa


def format_uptime(seconds: float) -> tuple[str, str]:
    """(texto grande, legenda) — '4d 19h 18m' em vez de '115h18'."""
    s = max(0, int(seconds))
    d, rest = divmod(s, 86400)
    h, rest = divmod(rest, 3600)
    m = rest // 60
    if d:
        big = f"{d}d {h:02d}h {m:02d}m"
    elif h:
        big = f"{h}h {m:02d}m"
    else:
        big = f"{m} min"
    return big, ""


class UptimeCard(QFrame):
    """Há quanto tempo o computador está ligado, com a data do último boot e uma
    barra de 7 dias (cheia = hora de reiniciar para o Windows respirar)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("UptimeCard")
        self.setFixedHeight(68)
        self._secs = 0.0
        self._since = ""
        self._pulse = False
        self.setToolTip("Tempo desde que o computador foi ligado.\n"
                        "A barra enche em 7 dias: reiniciar de vez em quando mantém o Windows leve.")

    def set_uptime(self, seconds: float, since_text: str) -> None:
        self._secs, self._since = float(seconds), since_text
        self._pulse = not self._pulse
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        box = QRectF(0.5, 0.5, W - 1, H - 1)
        bg = QLinearGradient(0, 0, W, H)
        c0 = qcol(C.PANEL2); c1 = QColor(qcol(accent2(), 30))
        bg.setColorAt(0.0, c0); bg.setColorAt(1.0, _lerp(c0, c1, 0.55))
        p.setPen(QPen(qcol(C.BORDER), 1))
        p.setBrush(QBrush(bg))
        p.drawRoundedRect(box, 10, 10)

        verde = qcol(C.GREEN)
        pulso = QColor(verde); pulso.setAlpha(255 if self._pulse else 120)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(pulso))
        p.drawEllipse(QPointF(15, 15), 3.2, 3.2)
        p.setPen(QPen(qcol(C.TEXT_MED), 1))
        p.setFont(_font(6.8, QFont.Weight.Bold, 2.0))
        p.drawText(QRectF(24, 6, W - 30, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   "LIGADO HÁ")

        big, _ = format_uptime(self._secs)
        p.setFont(_font(15, QFont.Weight.Bold))
        fm = p.fontMetrics()
        x = 12.0
        # números em branco, unidades (d/h/m) na cor do acento
        for tok in big.split(" "):
            num, unit = tok[:-1], tok[-1]
            if tok.endswith("min"):
                num, unit = tok[:-3], "min"
            p.setPen(QPen(qcol(C.WHITE), 1))
            p.drawText(QPointF(x, 41), num)
            x += fm.horizontalAdvance(num)
            p.setPen(QPen(qcol(C.PRI), 1))
            p.setFont(_font(9, QFont.Weight.DemiBold))
            p.drawText(QPointF(x + 1, 41), unit)
            x += p.fontMetrics().horizontalAdvance(unit) + 7
            p.setFont(_font(15, QFont.Weight.Bold))

        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.setFont(_font(6.6))
        p.drawText(QRectF(12, 44, W - 24, 12), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   self._since)

        frac = min(1.0, self._secs / (7 * 86400.0))
        pct = frac * 100
        a, b = _grad_ends(pct if pct > 65 else 0, C.GREEN)
        trilho = QRectF(12, H - 9, W - 24, 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(qcol(C.BAR_BG)))
        p.drawRoundedRect(trilho, 2, 2)
        if frac > 0:
            cheio = QRectF(trilho.x(), trilho.y(), max(4.0, trilho.width() * frac), 4)
            lg = QLinearGradient(cheio.left(), 0, cheio.right(), 0)
            lg.setColorAt(0.0, a); lg.setColorAt(1.0, b)
            p.setBrush(QBrush(lg))
            p.drawRoundedRect(cheio, 2, 2)
        p.end()


class ProcessList(QWidget):
    """Os processos que mais pesam, com barra proporcional. Clique no
    cabeçalho para alternar entre ordenar por CPU e por memória."""

    ROWS = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[tuple[str, float, float]] = []
        self._mode = "cpu"
        self._count = 0
        self._threads = 0
        self.setFixedHeight(26 + self.ROWS * 21 + 4)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Clique no cabeçalho para ordenar por CPU ou por memória.\n"
                        "Processos com o mesmo nome (Chrome, por exemplo) são somados.")

    def set_data(self, rows, count: int, threads: int = 0) -> None:
        self._rows, self._count, self._threads = list(rows), int(count), int(threads)
        self.update()

    def mode(self) -> str:
        return self._mode

    def _sorted(self):
        if self._mode == "cpu":
            return sorted(self._rows, key=lambda r: (-r[1], -r[2]))[: self.ROWS]
        return sorted(self._rows, key=lambda r: -r[2])[: self.ROWS]

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and e.position().y() < 24:
            self._mode = "mem" if self._mode == "cpu" else "cpu"
            self.update()
        super().mousePressEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W = self.width()

        p.setPen(QPen(qcol(C.TEXT_MED), 1))
        p.setFont(_font(6.8, QFont.Weight.Bold, 2.0))
        p.drawText(QRectF(2, 2, 90, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "PROCESSOS")
        # contador + seletor
        p.setPen(QPen(qcol(C.WHITE), 1))
        p.setFont(_font(9, QFont.Weight.Bold))
        p.drawText(QRectF(W - 112, 2, 50, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   str(self._count) if self._count else "--")
        chip = QRectF(W - 58, 4, 56, 15)
        p.setPen(QPen(qcol(C.BORDER_B), 1))
        p.setBrush(QBrush(qcol(C.PRI_GHO)))
        p.drawRoundedRect(chip, 7.5, 7.5)
        p.setPen(QPen(qcol(C.PRI), 1))
        p.setFont(_font(6.4, QFont.Weight.Bold, 0.8))
        p.drawText(chip, Qt.AlignmentFlag.AlignCenter, "⇅ CPU" if self._mode == "cpu" else "⇅ RAM")

        rows = self._sorted()
        if not rows:
            p.setPen(QPen(qcol(C.TEXT_DIM), 1))
            p.setFont(_font(7.4))
            p.drawText(QRectF(0, 26, W, 40), Qt.AlignmentFlag.AlignCenter, "lendo processos…")
            p.end()
            return
        idx = 1 if self._mode == "cpu" else 2
        top = max(r[idx] for r in rows) or 1.0
        floor = 5.0 if self._mode == "cpu" else 200.0
        top = max(top, floor)
        y = 26.0
        for i, (nome, cpu, ram) in enumerate(rows):
            val = cpu if self._mode == "cpu" else ram
            frac = max(0.03, min(1.0, val / top))
            a, b = _grad_ends(min(100.0, cpu * 2) if self._mode == "cpu" else 0, C.PRI)
            p.setPen(QPen(qcol(C.TEXT if i else C.WHITE), 1))
            p.setFont(_font(7.6, QFont.Weight.DemiBold if i == 0 else QFont.Weight.Normal))
            fm = p.fontMetrics()
            p.drawText(QRectF(2, y, 74, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       fm.elidedText(nome, Qt.TextElideMode.ElideRight, 72))
            bar = QRectF(80, y + 5, W - 80 - 48, 4)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(qcol(C.BAR_BG)))
            p.drawRoundedRect(bar, 2, 2)
            cheio = QRectF(bar.x(), bar.y(), max(3.0, bar.width() * frac), 4)
            lg = QLinearGradient(cheio.left(), 0, cheio.right(), 0)
            lg.setColorAt(0.0, a); lg.setColorAt(1.0, b)
            p.setBrush(QBrush(lg))
            p.drawRoundedRect(cheio, 2, 2)
            if self._mode == "cpu":
                txt = f"{cpu:.0f}%" if cpu >= 1 else f"{cpu:.1f}%".replace(".", ",")
            else:
                txt = f"{ram / 1024:.1f} GB".replace(".", ",") if ram >= 1024 else f"{ram:.0f} MB"
            p.setPen(QPen(qcol(C.TEXT_MED), 1))
            p.setFont(_font(7.2, QFont.Weight.DemiBold))
            p.drawText(QRectF(W - 46, y, 46, 14), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, txt)
            y += 21
        p.end()


class StatusCard(QFrame):
    """Cartão de estado: substitui os três selos de baixo do painel esquerdo."""

    _CORE = {
        "LISTENING": ("Ouvindo", "GREEN"), "SPEAKING": ("Falando", "ACC"),
        "THINKING": ("Pensando", "ACC2"), "PROCESSING": ("Processando", "ACC2"),
        "SLEEPING": ("Dormindo", "TEXT_MED"), "MUTED": ("Mudo", "MUTED_C"),
        "INITIALISING": ("Iniciando", "PRI"),
    }

    def __init__(self, version: str, parent=None):
        super().__init__(parent)
        self.setObjectName("StatusCard")
        self.setStyleSheet(f"""
            QFrame#StatusCard {{ background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 10px; }}
            QLabel {{ background: transparent; border: none; }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 9)
        lay.setSpacing(5)
        head = QLabel("ESTADO")
        head.setFont(_font(6.6, QFont.Weight.Bold, 2.2))
        head.setStyleSheet(f"color: {C.TEXT_MED};")
        lay.addWidget(head)
        self._core = self._row(lay, "I.S.A.", "Iniciando", C.PRI)
        self._on_click = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Abrir o núcleo I.S.A. — o que o NEXUS pensou, decidiu e fez")
        self._safe = self._row(lay, "Segurança", "Protegida", C.GREEN)
        self._ver = self._row(lay, "Versão", version, C.TEXT_MED)

    def _row(self, lay, name: str, value: str, colour: str):
        h = QHBoxLayout()
        h.setSpacing(6)
        dot = QLabel("●")
        dot.setFont(_font(7))
        dot.setStyleSheet(f"color: {colour};")
        n = QLabel(name)
        n.setFont(_font(7.6))
        n.setStyleSheet(f"color: {C.TEXT_DIM};")
        v = QLabel(value)
        v.setFont(_font(7.6, QFont.Weight.DemiBold))
        v.setStyleSheet(f"color: {colour};")
        v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        h.addWidget(dot)
        h.addWidget(n)
        h.addStretch(1)
        h.addWidget(v)
        lay.addLayout(h)
        return dot, v

    def mousePressEvent(self, e):
        if self._on_click and e.button() == Qt.MouseButton.LeftButton:
            self._on_click()
        super().mousePressEvent(e)

    def set_core(self, state: str) -> None:
        texto, chave = self._CORE.get(str(state).upper(), (str(state).title(), "PRI"))
        cor = getattr(C, chave, C.PRI)
        dot, val = self._core
        val.setText(texto)
        for w in (dot, val):
            w.setStyleSheet(f"color: {cor};")

    def set_security(self, ok: bool, text: str = "") -> None:
        dot, val = self._safe
        cor = C.GREEN if ok else C.ACC
        val.setText(text or ("Protegida" if ok else "Atenção"))
        for w in (dot, val):
            w.setStyleSheet(f"color: {cor};")


# ══════════════════════════════════════════════════════════════════════════
#  CABEÇALHO (hub)  (visual 2.2)
# ══════════════════════════════════════════════════════════════════════════

class HeaderBar(QWidget):
    """Faixa do topo: fundo com leve degradê e um fio luminoso embaixo
    (acento → violeta → acento) no lugar da borda reta de antes."""

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        W, H = self.width(), self.height()
        bg = QLinearGradient(0, 0, W, 0)
        base = qcol(C.DARK)
        meio = qcol(mix(C.DARK, C.PANEL2, 0.65))
        bg.setColorAt(0.0, base); bg.setColorAt(0.5, meio); bg.setColorAt(1.0, base)
        p.fillRect(self.rect(), bg)
        fio = QLinearGradient(0, 0, W, 0)
        c_a, c_b = qcol(C.PRI), qcol(accent2())
        for pos, col, alpha in ((0.0, c_a, 0), (0.18, c_a, 190), (0.5, c_b, 235), (0.82, c_a, 190), (1.0, c_a, 0)):
            c = QColor(col); c.setAlpha(alpha)
            fio.setColorAt(pos, c)
        p.fillRect(QRectF(0, H - 2, W, 2), fio)
        glow = QLinearGradient(0, H - 14, 0, H)
        g0 = QColor(c_b); g0.setAlpha(0)
        g1 = QColor(c_b); g1.setAlpha(34)
        glow.setColorAt(0.0, g0); glow.setColorAt(1.0, g1)
        p.fillRect(QRectF(0, H - 14, W, 12), glow)
        p.end()


class GradientLabel(QLabel):
    """Texto com degradê horizontal (branco → acento → violeta). Usa a fonte, o
    alinhamento e o texto do QLabel normalmente."""

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        r = self.contentsRect()
        p.setFont(self.font())
        tw = p.fontMetrics().horizontalAdvance(self.text())
        x0 = r.center().x() - tw / 2.0
        lg = QLinearGradient(x0, 0, x0 + max(1.0, tw), 0)
        lg.setColorAt(0.0, qcol(C.WHITE))
        lg.setColorAt(0.45, qcol(mix(C.WHITE, C.PRI, 0.55)))
        lg.setColorAt(1.0, qcol(accent2()))
        p.setPen(QPen(QBrush(lg), 1))
        p.drawText(r, int(self.alignment()), self.text())
        p.end()


# ══════════════════════════════════════════════════════════════════════════
#  BOTÕES DO PAINEL CONTROLES  (visual 2.2)
# ══════════════════════════════════════════════════════════════════════════

def _icone(p: QPainter, chave: str, cx: float, cy: float, r: float, cor: QColor, fundo: bool) -> None:
    """Desenha um ícone vetorial de ~2r de lado, centrado em (cx, cy). Sem emoji:
    fica nítido em qualquer tamanho e tem a cor do tema."""
    p.save()
    p.translate(cx, cy)
    p.scale(r, r)
    pen = QPen(cor, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    pen.setCosmetic(True)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    cheio = QBrush(cor)
    P = QPointF

    if chave == "tela":                                   # ⛶ colchetes de tela cheia
        for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            p.drawLine(P(sx * 0.85, sy * 0.30), P(sx * 0.85, sy * 0.85))
            p.drawLine(P(sx * 0.85, sy * 0.85), P(sx * 0.30, sy * 0.85))
    elif chave == "sol":                                  # ☀ briefing da manhã
        p.drawEllipse(P(0, 0), 0.36, 0.36)
        for i in range(8):
            a = i * math.pi / 4
            p.drawLine(P(math.cos(a) * 0.64, math.sin(a) * 0.64), P(math.cos(a) * 0.95, math.sin(a) * 0.95))
    elif chave == "mic":                                  # 🎙 palavra de ativação
        cap = QPainterPath()
        cap.addRoundedRect(QRectF(-0.28, -0.92, 0.56, 1.14), 0.28, 0.28)
        p.drawPath(cap)
        p.drawArc(QRectF(-0.62, -0.50, 1.24, 1.24), 180 * 16, 180 * 16)
        p.drawLine(P(0, 0.74), P(0, 0.98))
        p.drawLine(P(-0.28, 0.98), P(0.28, 0.98))
    elif chave == "baixar":                               # ⬇ baixar
        p.drawLine(P(0, -0.85), P(0, 0.30))
        p.drawLine(P(-0.48, -0.15), P(0, 0.38))
        p.drawLine(P(0.48, -0.15), P(0, 0.38))
        p.drawLine(P(-0.78, 0.88), P(0.78, 0.88))
    elif chave == "ptt":                                  # 🎚 falar segurando (controles deslizantes)
        for x, y in ((-0.62, -0.25), (0.0, 0.32), (0.62, -0.45)):
            p.drawLine(P(x, -0.85), P(x, 0.85))
            p.setBrush(cheio)
            p.drawEllipse(P(x, y), 0.19, 0.19)
            p.setBrush(Qt.BrushStyle.NoBrush)
    elif chave == "lua":                                  # 😴 dormir
        a = QPainterPath()
        a.addEllipse(P(0, 0), 0.82, 0.82)
        b = QPainterPath()
        b.addEllipse(P(0.48, -0.30), 0.70, 0.70)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(cheio)
        p.drawPath(a.subtracted(b))
    elif chave == "ouvir":                                # 👂 acordar (barras de som)
        for i, hh in enumerate((0.30, 0.62, 0.95, 0.62, 0.30)):
            x = -0.76 + i * 0.38
            p.drawLine(P(x, -hh), P(x, hh))
    elif chave == "orb":                                  # ◉
        p.drawEllipse(P(0, 0), 0.86, 0.86)
        p.setBrush(cheio)
        p.drawEllipse(P(0, 0), 0.36, 0.36)
    elif chave == "minimo":                               # 〰
        w = QPainterPath()
        w.moveTo(-0.95, 0)
        for i in range(1, 41):
            t = i / 40.0
            w.lineTo(-0.95 + 1.9 * t, math.sin(t * math.pi * 3) * 0.5)
        p.drawPath(w)
    elif chave == "aurora":                               # 🌌
        for off, esc in ((-0.28, 0.5), (0.30, 0.38)):
            w = QPainterPath()
            w.moveTo(-0.95, off)
            for i in range(1, 41):
                t = i / 40.0
                w.lineTo(-0.95 + 1.9 * t, off + math.sin(t * math.pi * 2 + off * 4) * esc)
            p.drawPath(w)
        p.setBrush(cheio)
        p.drawEllipse(P(0.62, -0.72), 0.11, 0.11)
    elif chave == "liquido":                              # 💧
        d = QPainterPath()
        d.moveTo(0, -0.98)
        d.cubicTo(0.95, 0.05, 0.78, 0.92, 0, 0.92)
        d.cubicTo(-0.78, 0.92, -0.95, 0.05, 0, -0.98)
        p.drawPath(d)
        p.drawArc(QRectF(-0.46, 0.0, 0.7, 0.7), 210 * 16, 70 * 16)
    elif chave == "holo":                                 # 🛰 radar
        p.drawEllipse(P(0, 0), 0.88, 0.88)
        p.drawEllipse(P(0, 0), 0.46, 0.46)
        p.drawLine(P(0, 0), P(0.62, -0.62))
        p.setBrush(cheio)
        p.drawEllipse(P(0.30, 0.40), 0.10, 0.10)
    elif chave == "globo":                                # 🌐
        p.drawEllipse(P(0, 0), 0.88, 0.88)
        p.drawEllipse(P(0, 0), 0.40, 0.88)
        p.drawLine(P(-0.88, 0), P(0.88, 0))
        p.drawArc(QRectF(-0.88, -0.62, 1.76, 1.24), 0, 180 * 16)
        p.drawArc(QRectF(-0.88, -0.62, 1.76, 1.24), 180 * 16, 180 * 16)
    elif chave == "note":                                 # agenda / notas
        rr = QPainterPath(); rr.addRoundedRect(QRectF(-0.72, -0.88, 1.44, 1.76), 0.2, 0.2)
        p.drawPath(rr)
        for y in (-0.38, 0.0, 0.38):
            p.drawLine(P(-0.36, y), P(0.36, y))
    elif chave == "alvo":                                 # produtividade
        p.drawEllipse(P(0, 0), 0.88, 0.88)
        p.drawEllipse(P(0, 0), 0.50, 0.50)
        p.setBrush(cheio); p.drawEllipse(P(0, 0), 0.16, 0.16)
    elif chave == "chip":                                 # I.S.A.
        rr = QPainterPath(); rr.addRoundedRect(QRectF(-0.52, -0.52, 1.04, 1.04), 0.16, 0.16)
        p.drawPath(rr)
        for t in (-0.28, 0.0, 0.28):
            p.drawLine(P(t, -0.52), P(t, -0.88)); p.drawLine(P(t, 0.52), P(t, 0.88))
            p.drawLine(P(-0.52, t), P(-0.88, t)); p.drawLine(P(0.52, t), P(0.88, t))
        p.setBrush(cheio); p.drawEllipse(P(0, 0), 0.16, 0.16)
    elif chave == "pasta":                                # organizar
        rr = QPainterPath(); rr.addRoundedRect(QRectF(-0.92, -0.38, 1.84, 1.2), 0.16, 0.16)
        p.drawPath(rr)
        p.drawLine(P(-0.92, -0.38), P(-0.92, -0.70)); p.drawLine(P(-0.92, -0.70), P(-0.22, -0.70))
        p.drawLine(P(-0.22, -0.70), P(0.02, -0.38))
    elif chave == "livro":                                # comandos
        rr = QPainterPath(); rr.addRoundedRect(QRectF(-0.82, -0.78, 1.64, 1.56), 0.14, 0.14)
        p.drawPath(rr)
        p.drawLine(P(0, -0.78), P(0, 0.78))
        for y in (-0.35, 0.0, 0.35):
            p.drawLine(P(-0.60, y), P(-0.22, y)); p.drawLine(P(0.22, y), P(0.60, y))
    elif chave == "prancheta":                            # área de transferência
        rr = QPainterPath(); rr.addRoundedRect(QRectF(-0.70, -0.72, 1.40, 1.66), 0.16, 0.16)
        p.drawPath(rr)
        cl = QPainterPath(); cl.addRoundedRect(QRectF(-0.30, -0.95, 0.60, 0.36), 0.12, 0.12)
        p.setBrush(QBrush(cor)); p.drawPath(cl); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(P(-0.36, 0.0), P(0.36, 0.0)); p.drawLine(P(-0.36, 0.40), P(0.2, 0.40))
    elif chave == "olho":                                 # visão
        e = QPainterPath(); e.moveTo(-0.97, 0); e.quadTo(0, -1.05, 0.97, 0); e.quadTo(0, 1.05, -0.97, 0)
        p.drawPath(e)
        p.setBrush(cheio); p.drawEllipse(P(0, 0), 0.30, 0.30)
    elif chave == "grafico":                              # sistema
        p.setBrush(cheio)
        for x, y0, hh in ((-0.78, 0.10, 0.78), (-0.20, -0.38, 1.26), (0.38, -0.82, 1.70)):
            rr = QPainterPath(); rr.addRoundedRect(QRectF(x, y0, 0.40, hh), 0.10, 0.10)
            p.drawPath(rr)
    elif chave == "memoria":                              # memória (banco de dados)
        p.drawEllipse(P(0, -0.52), 0.72, 0.28)
        p.drawLine(P(-0.72, -0.52), P(-0.72, 0.52)); p.drawLine(P(0.72, -0.52), P(0.72, 0.52))
        p.drawArc(QRectF(-0.72, -0.14, 1.44, 0.56), 180 * 16, 180 * 16)
        p.drawArc(QRectF(-0.72, 0.24, 1.44, 0.56), 180 * 16, 180 * 16)
    elif chave == "cubo":                                 # plugins
        hx = QPainterPath(); hx.moveTo(0, -0.92); hx.lineTo(0.80, -0.46); hx.lineTo(0.80, 0.46)
        hx.lineTo(0, 0.92); hx.lineTo(-0.80, 0.46); hx.lineTo(-0.80, -0.46); hx.closeSubpath()
        p.drawPath(hx)
        p.drawLine(P(0, 0), P(0, 0.92)); p.drawLine(P(0, 0), P(0.80, -0.46)); p.drawLine(P(0, 0), P(-0.80, -0.46))
    elif chave == "fone":                                 # áudio
        p.drawArc(QRectF(-0.80, -0.86, 1.60, 1.60), 0, 180 * 16)
        p.setBrush(cheio)
        for x in (-0.92, 0.56):
            rr = QPainterPath(); rr.addRoundedRect(QRectF(x, -0.02, 0.36, 0.78), 0.14, 0.14)
            p.drawPath(rr)
    elif chave == "celular":
        rr = QPainterPath(); rr.addRoundedRect(QRectF(-0.46, -0.92, 0.92, 1.84), 0.22, 0.22)
        p.drawPath(rr); p.drawLine(P(-0.14, 0.66), P(0.14, 0.66))
    elif chave == "lista":                                # atividades / lista
        for y in (-0.55, 0.0, 0.55):
            p.setBrush(cheio); p.drawEllipse(P(-0.66, y), 0.10, 0.10); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawLine(P(-0.30, y), P(0.82, y))
    elif chave == "engrenagem":                           # configurações
        p.drawEllipse(P(0, 0), 0.30, 0.30)
        p.drawEllipse(P(0, 0), 0.62, 0.62)
        for i in range(8):
            a = i * math.pi / 4
            p.drawLine(P(math.cos(a) * 0.62, math.sin(a) * 0.62), P(math.cos(a) * 0.94, math.sin(a) * 0.94))
    elif chave == "pessoa":                               # usuário
        p.drawEllipse(P(0, -0.42), 0.32, 0.32)
        p.drawArc(QRectF(-0.72, 0.12, 1.44, 1.50), 0, 180 * 16)
    elif chave == "teclado":                              # atalhos
        rr = QPainterPath(); rr.addRoundedRect(QRectF(-0.95, -0.58, 1.90, 1.16), 0.16, 0.16)
        p.drawPath(rr)
        p.setBrush(cheio)
        for x in (-0.58, -0.19, 0.19, 0.58):
            p.drawEllipse(P(x, -0.22), 0.07, 0.07)
        p.setBrush(Qt.BrushStyle.NoBrush); p.drawLine(P(-0.45, 0.22), P(0.45, 0.22))
    elif chave == "brilho":                               # trocar visual
        s = QPainterPath(); s.moveTo(0, -0.92); s.lineTo(0.20, -0.20); s.lineTo(0.92, 0)
        s.lineTo(0.20, 0.20); s.lineTo(0, 0.92); s.lineTo(-0.20, 0.20); s.lineTo(-0.92, 0)
        s.lineTo(-0.20, -0.20); s.closeSubpath()
        p.drawPath(s)
        p.setBrush(cheio); p.drawEllipse(P(0.66, -0.66), 0.10, 0.10)
    elif chave == "raio":                                 # comando rápido
        b = QPainterPath(); b.moveTo(0.22, -0.95); b.lineTo(-0.55, 0.10); b.lineTo(-0.06, 0.10)
        b.lineTo(-0.22, 0.95); b.lineTo(0.55, -0.12); b.lineTo(0.06, -0.12); b.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(cheio); p.drawPath(b)
    elif chave == "pulso":                                # status
        w = QPainterPath(); w.moveTo(-0.95, 0.05); w.lineTo(-0.45, 0.05); w.lineTo(-0.20, -0.72)
        w.lineTo(0.12, 0.72); w.lineTo(0.36, 0.05); w.lineTo(0.95, 0.05)
        p.drawPath(w)
    elif chave == "recarregar":                           # resetar
        p.drawArc(QRectF(-0.74, -0.74, 1.48, 1.48), 40 * 16, 280 * 16)
        p.drawLine(P(0.57, -0.58), P(0.80, -0.78)); p.drawLine(P(0.57, -0.58), P(0.90, -0.36))
    elif chave == "info":                                 # sobre
        p.drawEllipse(P(0, 0), 0.88, 0.88)
        p.setBrush(cheio); p.drawEllipse(P(0, -0.42), 0.10, 0.10); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(P(0, -0.08), P(0, 0.52))
    elif chave == "tomada":                               # pacotes / APIs
        p.drawLine(P(-0.30, -0.92), P(-0.30, -0.36)); p.drawLine(P(0.30, -0.92), P(0.30, -0.36))
        rr = QPainterPath(); rr.addRoundedRect(QRectF(-0.62, -0.36, 1.24, 0.84), 0.26, 0.26)
        p.drawPath(rr); p.drawLine(P(0, 0.48), P(0, 0.92))
    elif chave == "disco":                                # backup
        rr = QPainterPath(); rr.addRoundedRect(QRectF(-0.86, -0.86, 1.72, 1.72), 0.22, 0.22)
        p.drawPath(rr)
        p.drawRect(QRectF(-0.46, -0.86, 0.92, 0.52)); p.drawRect(QRectF(-0.50, 0.08, 1.0, 0.78))
    elif chave == "robo":                                 # atuador
        rr = QPainterPath(); rr.addRoundedRect(QRectF(-0.72, -0.46, 1.44, 1.24), 0.28, 0.28)
        p.drawPath(rr); p.drawLine(P(0, -0.46), P(0, -0.88))
        p.setBrush(cheio)
        p.drawEllipse(P(-0.28, 0.06), 0.12, 0.12); p.drawEllipse(P(0.28, 0.06), 0.12, 0.12)
        p.setBrush(Qt.BrushStyle.NoBrush); p.drawLine(P(-0.26, 0.48), P(0.26, 0.48))
    elif chave == "barras":                               # barra rápida
        for y in (-0.62, -0.14, 0.34):
            rr = QPainterPath(); rr.addRoundedRect(QRectF(-0.92, y, 1.84, 0.36), 0.18, 0.18)
            p.drawPath(rr)
    elif chave == "subir":                                # atualizar
        p.drawLine(P(0, 0.85), P(0, -0.30))
        p.drawLine(P(-0.48, 0.15), P(0, -0.38)); p.drawLine(P(0.48, 0.15), P(0, -0.38))
        p.drawLine(P(-0.78, -0.88), P(0.78, -0.88))
    else:                                                 # desconhecido: um losango
        d = QPainterPath()
        d.moveTo(0, -0.7); d.lineTo(0.7, 0); d.lineTo(0, 0.7); d.lineTo(-0.7, 0); d.closeSubpath()
        p.drawPath(d)
    p.restore()


_ICONE_POR_CARACTERE = {
    "⛶": "tela", "☀": "sol", "🎙": "mic", "⬇": "baixar", "🎚": "ptt", "😴": "lua", "👂": "ouvir",
    "◉": "orb", "〰": "minimo", "🌌": "aurora", "💧": "liquido", "🛰": "holo", "🌐": "globo",
}
_ESTADO_LIGADO = {"LIGADO", "LIGADA"}
_ESTADO_DESLIGADO = {"DESLIGADO", "DESLIGADA"}
_ESTADO_ALERTA = {"BAIXAR"}


class ControlButton(QPushButton):
    """Linha do painel CONTROLES: ícone vetorial num quadradinho de cor, nome e, à
    direita, o estado em forma de pílula (LIGADO / DESLIGADO / tecla / nome).

    Continua sendo um QPushButton: o resto do programa só faz setText("🎙  NOME: LIGADA")
    como antes — o desenho lê o texto (ícone, nome, estado) e ignora o estilo antigo."""

    H = 36

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(self.H)
        self.setMouseTracking(True)

    # ── leitura do texto ─────────────────────────────────────────────────────
    def _partes(self) -> tuple[str, str, str, str]:
        """(chave do ícone, nome, texto da pílula, tipo: on/off/alerta/info/nenhum)."""
        t = self.text().strip()
        ic, sep, resto = t.partition("  ")
        if not sep:
            ic, resto = "", t
        chave = _ICONE_POR_CARACTERE.get(ic.strip(), "")
        if not chave:                       # sem ícone conhecido: o texto inteiro é o nome
            resto, chave = t, ""
        nome, pilula, tipo = resto.strip(), "", "nenhum"
        if ": " in resto:
            nome, pilula = resto.rsplit(": ", 1)
            up = pilula.strip().upper()
            tipo = ("on" if up in _ESTADO_LIGADO else "off" if up in _ESTADO_DESLIGADO
                    else "alerta" if up in _ESTADO_ALERTA else "info")
        elif resto.rstrip().endswith("]") and "[" in resto:
            a = resto.rindex("[")
            nome, pilula, tipo = resto[:a].strip(), resto[a + 1:-1].strip(), "info"
        return chave, nome.strip(), pilula.strip(), tipo

    # ── desenho ──────────────────────────────────────────────────────────────
    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        W, H = self.width(), self.height()
        chave, nome, pilula, tipo = self._partes()
        ativo = self.isEnabled()
        hover = self.underMouse() and ativo
        press = self.isDown()
        a2 = accent2()

        cor_estado = {"on": C.GREEN, "alerta": C.ACC, "off": C.TEXT_DIM}.get(tipo, C.PRI)
        ligado = tipo in ("on", "alerta", "info", "nenhum")

        # cartão
        box = QRectF(0.5, 0.5, W - 1, H - 1)
        bg = QLinearGradient(0, 0, W, 0)
        c0 = qcol(C.PANEL2)
        c1 = qcol(mix(C.PANEL2, cor_estado, 0.16 if ligado else 0.0))
        if press:
            c0, c1 = qcol(C.PRI_GHO), qcol(C.PRI_GHO)
        bg.setColorAt(0.0, c0)
        bg.setColorAt(1.0, c1)
        p.setPen(QPen(qcol(C.PRI if hover else (cor_estado if tipo in ("on", "alerta") else C.BORDER), 200 if hover else 120), 1))
        p.setBrush(QBrush(bg))
        p.drawRoundedRect(box, 10, 10)

        # quadradinho do ícone
        chip = QRectF(6, (H - 24) / 2, 24, 24)
        if ligado and ativo:
            g = QLinearGradient(chip.topLeft(), chip.bottomRight())
            base = qcol(cor_estado)
            g.setColorAt(0.0, base)
            g.setColorAt(1.0, qcol(accent2(cor_estado, 0.10)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(g))
            cor_ic = qcol(C.BG)
        else:
            p.setPen(QPen(qcol(C.BORDER), 1))
            p.setBrush(QBrush(qcol(C.BAR_BG)))
            cor_ic = qcol(C.TEXT_DIM if ativo else C.BORDER_B)
        p.drawRoundedRect(chip, 7, 7)
        if chave:
            _icone(p, chave, chip.center().x(), chip.center().y(), 7.2, cor_ic, ligado)

        # pílula do estado (à direita)
        x_fim = W - 8.0
        if pilula:
            p.setFont(_font(6.6, QFont.Weight.Bold, 0.9))
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(pilula.upper())
            pw = min(tw + 18.0, 96.0)
            pill = QRectF(W - 8 - pw, (H - 17) / 2, pw, 17)
            if tipo == "on":
                pg = QLinearGradient(pill.left(), 0, pill.right(), 0)
                pg.setColorAt(0.0, qcol(C.GREEN)); pg.setColorAt(1.0, qcol(accent2(C.GREEN, 0.10)))
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(pg)); txt = qcol(C.BG)
            elif tipo == "alerta":
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(qcol(C.ACC))); txt = qcol(C.BG)
            elif tipo == "off":
                p.setPen(QPen(qcol(C.BORDER_B), 1)); p.setBrush(QBrush(qcol(C.BAR_BG))); txt = qcol(C.TEXT_DIM)
            else:
                p.setPen(QPen(qcol(C.BORDER_B), 1)); p.setBrush(QBrush(qcol(C.PRI_GHO))); txt = qcol(C.PRI)
            p.drawRoundedRect(pill, 8.5, 8.5)
            p.setPen(QPen(txt, 1))
            p.drawText(pill, Qt.AlignmentFlag.AlignCenter,
                       fm.elidedText(pilula.upper(), Qt.TextElideMode.ElideRight, int(pw - 10)))
            x_fim = pill.left() - 6

        # nome
        p.setPen(QPen(qcol(C.WHITE if ligado else C.TEXT_MED) if ativo else qcol(C.TEXT_DIM), 1))
        p.setFont(_font(7.6, QFont.Weight.DemiBold if ligado else QFont.Weight.Normal, 0.3))
        fm = p.fontMetrics()
        p.drawText(QRectF(38, 0, max(10.0, x_fim - 38), H), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   fm.elidedText(nome, Qt.TextElideMode.ElideRight, int(max(10.0, x_fim - 38))))
        p.end()


# ícone de cada ferramenta da barra rápida (id do catálogo em ui/quickbar.py) e de cada item do SETUP
ICONE_FERRAMENTA = {
    "agenda": "note", "produtiv": "alvo", "ditado": "mic", "isa": "chip", "organizar": "pasta",
    "comandos": "livro", "area": "prancheta", "visao": "olho", "sistema": "grafico",
    "memoria": "memoria", "plugins": "cubo", "audio": "fone", "celular": "celular",
    "atividades": "lista", "config": "engrenagem", "usuario": "pessoa", "telacheia": "tela",
    "hud": "brilho", "atalhos": "teclado",
}
ICONE_SETUP = {
    "usuario": "pessoa", "audio": "fone", "status": "pulso", "resetar": "recarregar",
    "gerenciar": "memoria", "sobre": "info", "apis": "tomada", "comandos": "livro",
    "lista": "lista", "avancado": "ptt", "backup": "disco", "agenda": "note",
    "atuador": "robo", "barra": "barras", "atalhos": "teclado", "isa": "chip", "atualizar": "subir",
}


class QuickButton(QPushButton):
    """Botão em pílula da barra de acesso rápido: ícone vetorial + nome.
    No modo compacto (janela estreita) mostra só o ícone."""

    H = 32

    def __init__(self, icone: str, nome: str, tipo: str = "tool", parent=None):
        super().__init__(parent)
        self._ic, self._nome, self._tipo = icone, nome, tipo
        self._on = False
        self._compacto = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(self.H)
        self.setMouseTracking(True)
        self._ajustar()

    def _ajustar(self) -> None:
        from PyQt6.QtGui import QFontMetrics
        if self._compacto:
            self.setFixedWidth(36)
        else:
            tw = QFontMetrics(_font(7.8, QFont.Weight.DemiBold)).horizontalAdvance(self._nome)
            self.setFixedWidth(int(14 + 16 + 8 + tw + 16))

    def set_compacto(self, v: bool) -> None:
        if v != self._compacto:
            self._compacto = v
            self._ajustar()
            self.update()

    def set_on(self, v: bool) -> None:
        self._on = bool(v)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        W, H = self.width(), self.height()
        hover, press = self.underMouse(), self.isDown()
        if self._on:
            base, borda, fundo = qcol(C.MUTED_C), qcol(C.MUTED_C), qcol(C.MUTED_C, 40)
        elif self._tipo == "command":
            base = qcol(C.ACC)
            borda = qcol(C.ACC if hover else C.BORDER_B, 200 if hover else 255)
            fundo = qcol(C.ACC, 26) if hover else qcol(C.PANEL2)
        else:
            base = qcol(C.PRI)
            borda = qcol(C.PRI if hover else C.BORDER, 230 if hover else 255)
            fundo = qcol(C.PRI_GHO) if hover else qcol(C.PANEL2)
        if press:
            fundo = qcol(C.PRI_GHO)
        rect = QRectF(0.5, 0.5, W - 1, H - 1)
        g = QLinearGradient(0, 0, 0, H)
        g.setColorAt(0.0, _lerp(fundo, qcol(C.WHITE, fundo.alpha()), 0.05))
        g.setColorAt(1.0, fundo)
        p.setPen(QPen(borda, 1))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(rect, H / 2, H / 2)
        cor_ic = qcol(C.WHITE) if hover and not self._on else base
        icx = W / 2 if self._compacto else 14 + 8
        _icone(p, self._ic, icx, H / 2, 7.4, cor_ic, True)
        if not self._compacto:
            p.setPen(QPen(qcol(C.WHITE if (hover or self._on) else C.TEXT_MED), 1))
            p.setFont(_font(7.8, QFont.Weight.DemiBold))
            p.drawText(QRectF(14 + 16 + 8, 0, W - 40, H), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       self._nome)
        p.end()


class MenuButton(QPushButton):
    """Linha do menu SETUP: ícone vetorial, nome e uma setinha. `tipo`:
    'normal', 'primario' (a Configuração do usuário, em destaque) ou 'destaque' (ATUALIZAR)."""

    H = 27

    def __init__(self, icone: str, nome: str, tipo: str = "normal", parent=None):
        super().__init__(parent)
        self._ic, self._nome, self._tipo = icone, nome, tipo
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(self.H)
        self.setMouseTracking(True)

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        W, H = self.width(), self.height()
        hover, press = self.underMouse(), self.isDown()
        rect = QRectF(0.5, 0.5, W - 1, H - 1)
        if self._tipo == "primario":
            g = QLinearGradient(0, 0, W, 0)
            g.setColorAt(0.0, qcol(C.PRI, 230 if hover else 200))
            g.setColorAt(1.0, qcol(accent2(), 230 if hover else 200))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(g))
            txt, ic = qcol(C.BG), qcol(C.BG)
        elif self._tipo == "destaque":
            g = QLinearGradient(0, 0, W, 0)
            g.setColorAt(0.0, qcol(C.PRI_GHO)); g.setColorAt(1.0, qcol(mix(C.PRI_GHO, C.GREEN, 0.25)))
            p.setPen(QPen(qcol(C.GREEN, 200 if hover else 120), 1))
            p.setBrush(QBrush(g))
            txt, ic = qcol(C.WHITE), qcol(C.GREEN)
        else:
            fundo = qcol(C.PRI_GHO) if (hover or press) else qcol(C.PANEL2, 0 if not hover else 255)
            p.setPen(QPen(qcol(C.BORDER_B if hover else C.BORDER, 255 if hover else 130), 1))
            p.setBrush(QBrush(fundo))
            txt, ic = qcol(C.WHITE if hover else C.TEXT_MED), qcol(C.PRI if hover else C.TEXT_DIM)
        p.drawRoundedRect(rect, 8, 8)
        _icone(p, self._ic, 15, H / 2, 6.4, ic, False)
        p.setPen(QPen(txt, 1))
        p.setFont(_font(7.2, QFont.Weight.Bold if self._tipo != "normal" else QFont.Weight.DemiBold, 0.4))
        fm = p.fontMetrics()
        p.drawText(QRectF(30, 0, W - 50, H), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   fm.elidedText(self._nome, Qt.TextElideMode.ElideRight, int(W - 50)))
        if self._tipo != "primario":
            p.setPen(QPen(qcol(C.PRI if hover else C.TEXT_DIM), 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(W - 15, H / 2 - 3.5), QPointF(W - 11.5, H / 2))
            p.drawLine(QPointF(W - 11.5, H / 2), QPointF(W - 15, H / 2 + 3.5))
        else:
            p.setPen(QPen(qcol(C.BG), 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(W - 15, H / 2 - 3.5), QPointF(W - 11.5, H / 2))
            p.drawLine(QPointF(W - 11.5, H / 2), QPointF(W - 15, H / 2 + 3.5))
        p.end()


# ══════════════════════════════════════════════════════════════════════════
#  BARRA DE ACESSO RÁPIDO
# ══════════════════════════════════════════════════════════════════════════

class QuickBar(QWidget):
    """Faixa de botões acima do rodapé. Os itens vêm de ui/quickbar.py."""

    def __init__(self, on_customize, parent=None):
        super().__init__(parent)
        self._on_customize = on_customize
        self.setObjectName("QuickBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(44)
        self.setStyleSheet(f"""
            QWidget#QuickBar {{ background: {C.DARK}; border-top: 1px solid {C.BORDER}; }}
            QPushButton#qb {{
                background: {C.PANEL2}; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 15px; padding: 0 12px;
            }}
            QPushButton#qb:hover {{ color: {C.WHITE}; border-color: {C.PRI_DIM}; background: {C.PRI_GHO}; }}
            QPushButton#qb:pressed {{ background: {C.PRI_DIM}; }}
            QPushButton#qbon {{
                background: {C.PRI_GHO}; color: {C.MUTED_C};
                border: 1px solid {C.MUTED_C}; border-radius: 15px; padding: 0 12px;
            }}
            QPushButton#qbon:hover {{ color: {C.WHITE}; }}
            QPushButton#qbcmd {{
                background: transparent; color: {C.ACC2};
                border: 1px solid {C.BORDER_B}; border-radius: 15px; padding: 0 12px;
            }}
            QPushButton#qbcmd:hover {{ color: {C.WHITE}; border-color: {C.ACC}; }}
            QPushButton#qbedit {{
                background: transparent; color: {C.TEXT_DIM};
                border: 1px dashed {C.BORDER_B}; border-radius: 15px; padding: 0 12px;
            }}
            QPushButton#qbedit:hover {{ color: {C.PRI}; border-color: {C.PRI}; }}
            QLabel {{ background: transparent; }}
        """)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(14, 6, 14, 6)
        self._lay.setSpacing(6)
        self._por_id: dict[str, QPushButton] = {}

    def build(self, items: list[dict]) -> None:
        """items: [{"icon", "label", "tooltip", "callback", "kind"}]"""
        while self._lay.count():
            it = self._lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        self._por_id = {}
        title = QLabel("ACESSO RÁPIDO")
        title.setFont(_font(6.6, QFont.Weight.Bold, 2.0))
        title.setStyleSheet(f"color: {C.TEXT_DIM};")
        self._lay.addWidget(title)
        self._lay.addSpacing(4)

        self._itens = items
        self._botoes: list[tuple[QPushButton, dict]] = []
        compacto = self._cabe_texto() is False
        for item in items:
            tipo = "command" if item.get("kind") == "command" else "tool"
            chave = "raio" if tipo == "command" else ICONE_FERRAMENTA.get(item.get("id", ""), "")
            b = QuickButton(chave, item["label"], tipo)
            b.set_compacto(compacto)
            b.setToolTip(item.get("tooltip") or item["label"])
            b.clicked.connect(lambda _=False, fn=item["callback"]: fn())
            if item.get("id"):
                self._por_id[item["id"]] = b
            self._botoes.append((b, item))
            self._lay.addWidget(b)
        self._compacto = compacto

        self._lay.addStretch(1)
        edit = QPushButton("＋  Personalizar")
        edit.setObjectName("qbedit")
        edit.setFixedHeight(30)
        edit.setFont(_font(8, QFont.Weight.DemiBold))
        edit.setCursor(Qt.CursorShape.PointingHandCursor)
        edit.setToolTip("Escolher os botões desta barra e criar comandos rápidos")
        edit.clicked.connect(self._on_customize)
        self._lay.addWidget(edit)

    def _cabe_texto(self) -> bool:
        """Os textos dos botões cabem na largura atual? (estimativa barata)"""
        itens = getattr(self, "_itens", [])
        precisa = 280 + sum(len(i["label"]) * 6 + 60 for i in itens)
        return self.width() >= precisa or self.width() <= 100     # ainda sem largura: mostra texto

    def resizeEvent(self, e):
        super().resizeEvent(e)
        botoes = getattr(self, "_botoes", [])
        if not botoes:
            return
        compacto = not self._cabe_texto()
        if compacto != getattr(self, "_compacto", False):
            self._compacto = compacto
            for b, item in botoes:
                b.set_compacto(compacto)

    def set_active(self, item_id: str, on: bool) -> None:
        """Destaca um botão que está ligado (ex.: 🎙 Ditado durante o ditado)."""
        b = self._por_id.get(item_id)
        if b is None:
            return
        b.set_on(on)
