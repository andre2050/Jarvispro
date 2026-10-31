"""Medidores e cartões: anéis, linhas de área, tempo ligado, processos, estado, cabeçalho.

Parte de ui/modern.py (dividido na 4.6.0 — sem mudança de comportamento)."""
from __future__ import annotations

from ._qt import *  # noqa: F401,F403
from ._base import C, FONT_MAIN, _persist_activity, accent2, mix, qcol, agora  # noqa: F401
from .modern_base import _font, _grad_ends, _lerp

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
