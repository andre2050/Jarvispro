"""Ícones desenhados, botões de controle, botões do menu e a barra de acesso rápido.

Parte de ui/modern.py (dividido na 4.6.0 — sem mudança de comportamento)."""
from __future__ import annotations

from ._qt import *  # noqa: F401,F403
from ._base import C, FONT_MAIN, _persist_activity, accent2, mix, qcol, agora  # noqa: F401
from .modern_base import _font, _lerp

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
