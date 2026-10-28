"""
I.S.A. HUD (estilo "isa") — o núcleo do NEXUS Ultra 2026 desenhado: 🧠 + ⚙.

Metade esquerda, COGNIÇÃO: um hemisfério cerebral com neurônios ligados por
sinapses. Pulsos de luz correm pelas sinapses — devagar em repouso, rápido
quando o NEXUS pensa, no ritmo da voz quando ele fala.

Metade direita, AUTOMAÇÃO: três engrenagens encaixadas. Giram devagar em
repouso e aceleram quando uma função está de fato rodando no computador
(lido do núcleo core/isa.py), além de quando ele pensa.

No meio, o BARRAMENTO: a costura que junta as duas metades, com pacotes de
dados subindo e descendo, e o NÚCLEO, que pulsa com a voz e solta anéis.

Mesmo contrato dos outros HUDs: step() a cada quadro, paint() com o painter;
só desenho (QPainter, sem GPU), nunca levanta exceção para a interface.
"""
from __future__ import annotations

import math
import random

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QColor, QFont, QPainter, QPainterPath, QPen,
                         QRadialGradient)

TAU = 2.0 * math.pi
_OURO = QColor(255, 196, 107)

# Engrenagens em unidades do raio: (x, y, raio, dentes, fase)
_ENGRENAGENS = [
    (0.37, -0.12, 0.29, 12, 0.0),
    (0.37 + 0.44 * math.cos(math.radians(58)), -0.12 + 0.44 * math.sin(math.radians(58)), 0.165, 7, 0.21),
    (0.37 + 0.39 * math.cos(math.radians(124)), -0.12 + 0.39 * math.sin(math.radians(124)), 0.115, 5, 0.33),
]
# Trilhas de circuito (barramento -> engrenagens), em unidades do raio
_TRILHAS = [
    [(0.0, -0.46), (0.10, -0.46), (0.18, -0.38)],
    [(0.0, 0.14), (0.08, 0.14), (0.12, 0.20)],
    [(0.0, 0.44), (0.30, 0.44), (0.42, 0.33)],
    [(0.0, -0.20), (0.07, -0.20)],
]


def _rate(dt: float, tau: float) -> float:
    return 1.0 - math.exp(-dt / max(tau, 1e-4))


def _c(col: QColor, a: float) -> QColor:
    q = QColor(col)
    q.setAlphaF(max(0.0, min(1.0, a)))
    return q


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(int(a.red() + (b.red() - a.red()) * t),
                  int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t))


def _contorno_cerebro(escala: float = 1.0, onda: float = 1.0, semente: float = 0.0):
    """Pontos do hemisfério esquerdo visto de frente: topo arredondado, lobo
    temporal saliente embaixo, a fissura lateral e a base achatada."""
    pts = []
    n = 96
    for i in range(n + 1):
        phi = 1.5 * math.pi - math.pi * i / n          # topo -> esquerda -> base
        rx, ry = 0.70, 0.58
        x = math.cos(phi) * rx
        y = math.sin(phi) * ry
        # lobo temporal (embaixo à esquerda) e a fissura logo acima dele
        bojo = 0.07 * math.exp(-((phi - 0.80 * math.pi) / 0.12) ** 2)
        fissura = -0.05 * math.exp(-((phi - 0.93 * math.pi) / 0.05) ** 2)
        ondinha = 0.016 * onda * math.sin(13 * phi + semente) + 0.010 * onda * math.sin(7 * phi + 2 * semente)
        k = 1.0 + bojo + fissura + ondinha
        x, y = x * k, y * k
        if y > 0.36:                                    # base achatada
            y = 0.36 + (y - 0.36) * 0.4
        cxm, cym = -0.33, -0.02                         # centro do hemisfério
        x = cxm + (x - cxm) * escala if escala != 1.0 else x
        y = cym + (y - cym) * escala if escala != 1.0 else y
        pts.append((min(x, -0.015), y))
    return pts


def _cerebro_unitario() -> QPainterPath:
    path = QPainterPath()
    pts = _contorno_cerebro()
    path.moveTo(-0.015, pts[0][1])
    for x, y in pts:
        path.lineTo(x, y)
    path.lineTo(-0.015, pts[-1][1])
    path.closeSubpath()
    return path


def _dobras_unitarias() -> list[QPainterPath]:
    """As dobras (giros): contornos menores e mais ondulados dentro do hemisfério."""
    dobras = []
    for k, esc in enumerate((0.80, 0.60, 0.40, 0.22)):
        pts = _contorno_cerebro(esc, onda=2.6 + k, semente=k * 1.3)
        path = QPainterPath()
        path.moveTo(*pts[0])
        for x, y in pts[1:]:
            path.lineTo(x, y)
        dobras.append(path)
    return dobras


def _engrenagem_unitaria(dentes: int) -> QPainterPath:
    path = QPainterPath()
    passo = TAU / dentes
    ri, ro = 0.80, 1.0
    primeiro = True
    for i in range(dentes):
        th = i * passo
        for raio, ang in ((ri, th - passo * 0.50), (ri, th - passo * 0.24), (ro, th - passo * 0.14),
                          (ro, th + passo * 0.14), (ri, th + passo * 0.24)):
            pt = QPointF(math.cos(ang) * raio, math.sin(ang) * raio)
            if primeiro:
                path.moveTo(pt)
                primeiro = False
            else:
                path.lineTo(pt)
    path.closeSubpath()
    furo = QPainterPath()
    furo.addEllipse(QPointF(0, 0), 0.20, 0.20)
    return path.subtracted(furo)


class IsaHUD:
    """O desenho da I.S.A. Quadrado: SPAN é 2.0 raios."""

    SPAN = 2.0
    aspect = None

    def __init__(self) -> None:
        self._t = 0.0
        self._amp = 0.0
        self._energy = 0.0
        self._think = 0.0
        self._listen = 0.0
        self._auto = 0.0           # 0..1: funções rodando agora (core/isa.py)
        self._giro = 0.0           # ângulo da engrenagem grande
        self._orbita = 0.0
        self._rings: list[float] = []
        self._last_peak = 0.0
        self._prev_amp = 0.0
        self._bus: list[list[float]] = []      # pacotes no barramento: [y, direção, vida]
        self._trilha: list[list[float]] = []   # pacotes nas trilhas: [trilha, pos 0..1]
        self._fonts: dict = {}

        self._cerebro = _cerebro_unitario()
        self._dobras = _dobras_unitarias()
        self._engr = [_engrenagem_unitaria(d) for _x, _y, _r, d, _f in _ENGRENAGENS]

        # neurônios dentro do hemisfério (sempre os mesmos)
        rng = random.Random(2026)
        nos: list[tuple[float, float]] = []
        tent = 0
        while len(nos) < 30 and tent < 4000:
            tent += 1
            x, y = rng.uniform(-0.70, -0.04), rng.uniform(-0.58, 0.42)
            if not self._cerebro.contains(QPointF(x, y)):
                continue
            if all((x - a) ** 2 + (y - b) ** 2 > 0.115 ** 2 for a, b in nos):
                nos.append((x, y))
        self._nos = nos
        arestas = set()
        for i, (x, y) in enumerate(nos):
            vizinhos = sorted(range(len(nos)), key=lambda j: (nos[j][0] - x) ** 2 + (nos[j][1] - y) ** 2)[1:4]
            for j in vizinhos:
                arestas.add((min(i, j), max(i, j)))
        # neurônios mais à direita ligam no barramento (a "fusão")
        for i in sorted(range(len(nos)), key=lambda k: -nos[k][0])[:4]:
            arestas.add((i, -1))
        self._arestas = sorted(arestas)
        self._brilho = [0.0] * len(nos)
        self._pulsos: list[list[float]] = []   # [aresta, pos, velocidade]
        self._acc_pulso = 0.0
        self._acc_bus = 0.0
        self._rng = random.Random(7)

    # ── animação ────────────────────────────────────────────────────────────

    def _automacao_agora(self) -> float:
        try:
            from core import isa
            return 1.0 if isa.em_andamento() > 0 else 0.0
        except Exception:
            return 0.0

    def step(self, dt: float, amp: float, speaking: bool = False,
             thinking: bool = False, muted: bool = False,
             listening: bool = False) -> None:
        try:
            dt = max(0.0, min(dt, 0.1))
            self._t += dt
            if amp != amp:
                amp = 0.0
            amp = 0.0 if muted else max(0.0, min(1.0, amp))
            self._amp += (amp - self._amp) * _rate(dt, 0.05)
            alvo = (0.5 + 0.5 * self._amp) if (speaking and not muted) else (0.3 if thinking else 0.0)
            self._energy += (alvo - self._energy) * _rate(dt, 0.10 if alvo > self._energy else 0.7)
            self._think += ((1.0 if thinking else 0.0) - self._think) * _rate(dt, 0.25)
            self._listen += ((1.0 if listening and not speaking else 0.0) - self._listen) * _rate(dt, 0.3)
            self._auto += (self._automacao_agora() - self._auto) * _rate(dt, 0.35)

            parado = 0.15 if muted else 1.0
            vel = (0.18 + 1.6 * self._think + 2.8 * self._auto + 0.5 * self._energy) * parado
            self._giro += dt * vel
            self._orbita += dt * (0.10 + 0.8 * self._energy + 0.6 * self._auto)

            # sinapses: pulsos de luz
            taxa = (0.8 + 7.0 * self._think + 6.0 * self._amp * (1 if speaking else 0)
                    + 1.5 * self._listen) * parado
            self._acc_pulso += dt * taxa
            while self._acc_pulso >= 1.0 and self._arestas:
                self._acc_pulso -= 1.0
                k = self._rng.randrange(len(self._arestas))
                self._pulsos.append([k, 0.0, self._rng.uniform(0.9, 1.6) * (1.0 + self._think)])
            vivos = []
            for pl in self._pulsos:
                pl[1] += dt * pl[2]
                if pl[1] >= 1.0:
                    i, j = self._arestas[int(pl[0])]
                    alvo_no = j if j >= 0 else i
                    if 0 <= alvo_no < len(self._brilho):
                        self._brilho[alvo_no] = 1.0
                    if j < 0:   # chegou no barramento: vira um pacote de dados
                        self._bus.append([self._nos[i][1], 1.0 if self._rng.random() < 0.5 else -1.0, 1.0])
                else:
                    vivos.append(pl)
            self._pulsos = vivos[-60:]
            self._brilho = [max(0.0, b - dt * 1.8) for b in self._brilho]

            # barramento e trilhas
            self._acc_bus += dt * (0.6 + 4.0 * self._auto + 2.0 * self._think) * parado
            while self._acc_bus >= 1.0:
                self._acc_bus -= 1.0
                self._trilha.append([float(self._rng.randrange(len(_TRILHAS))), 0.0])
            self._trilha = [[k, pos + dt * (0.9 + 1.2 * self._auto)] for k, pos in self._trilha
                            if pos + dt * (0.9 + 1.2 * self._auto) < 1.0][-24:]
            self._bus = [[y + d * dt * 0.7, d, v - dt * 0.6] for y, d, v in self._bus
                         if v - dt * 0.6 > 0 and -0.75 < y + d * dt * 0.7 < 0.75][-30:]

            # anéis de voz saindo do núcleo
            sobe = amp - self._prev_amp
            self._prev_amp = amp
            if speaking and amp > 0.18 and sobe > 0.04 and self._t - self._last_peak > 0.25:
                self._rings.append(0.0)
                self._last_peak = self._t
            self._rings = [a + dt for a in self._rings if a + dt < 1.5][-6:]
        except Exception:
            pass

    # ── desenho ─────────────────────────────────────────────────────────────

    def _font(self, txt: str, R: float) -> QFont:
        key = (txt, int(R))
        f = self._fonts.get(key)
        if f is None:
            from PyQt6.QtGui import QFontMetricsF
            size = max(7, int(R * 0.10))
            while True:
                f = QFont("Segoe UI", size, QFont.Weight.Light)
                f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, max(2.0, R * 0.04))
                if size <= 7 or QFontMetricsF(f).horizontalAdvance(txt) <= R * 1.1:
                    break
                size -= 1
            self._fonts[key] = f
        return f

    def paint(self, p: QPainter, cx: float, cy: float, r: float,
              main: QColor, accent: QColor, bg: QColor, name: str = "I.S.A.") -> None:
        try:
            self._paint(p, cx, cy, r, main, accent, bg, name)
        except Exception as e:                       # nunca derruba o HUD
            print(f"[IsaHUD] paint skipped: {e}")

    def _ponto(self, cx, cy, r, x, y) -> QPointF:
        return QPointF(cx + x * r, cy + y * r)

    def _brilho_em(self, p, pt: QPointF, raio: float, col: QColor, forca: float) -> None:
        g = QRadialGradient(pt, raio)
        g.setColorAt(0.0, _c(col, 0.65 * forca))
        g.setColorAt(1.0, _c(col, 0.0))
        p.setBrush(g)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(pt, raio, raio)

    def _paint(self, p, cx, cy, r, main, accent, bg, name) -> None:
        e, a, t = self._energy, self._amp, self._t
        branco = QColor(245, 243, 255)
        ouro = _mix(_OURO, main, 0.30)
        lw = max(1.0, r * 0.006)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # halo
        halo = QRadialGradient(QPointF(cx, cy), r * 1.05)
        tinta = _mix(main, accent, max(e, self._listen * 0.6, self._auto * 0.5))
        halo.setColorAt(0.0, _c(tinta, 0.12 + 0.10 * e + 0.06 * self._auto))
        halo.setColorAt(0.75, _c(tinta, 0.03))
        halo.setColorAt(1.0, _c(tinta, 0.0))
        p.setBrush(halo)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), r * 1.05, r * 1.05)

        # anel externo com marcações e arcos girando
        R = r * 0.93
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(_c(main, 0.20), lw))
        p.drawEllipse(QPointF(cx, cy), R, R)
        for k in range(72):
            ang = k * TAU / 72 + self._orbita * 0.15
            longo = k % 6 == 0
            r0 = R * (0.955 if longo else 0.972)
            p.setPen(QPen(_c(main, 0.40 if longo else 0.18), lw))
            p.drawLine(QPointF(cx + math.cos(ang) * r0, cy + math.sin(ang) * r0),
                       QPointF(cx + math.cos(ang) * R, cy + math.sin(ang) * R))
        caixa = QRectF(cx - R, cy - R, 2 * R, 2 * R)
        for k, (ini, vao) in enumerate(((0.4, 0.6), (2.6, 0.45), (4.3, 0.8))):
            caneta = QPen(_c(_mix(main, accent, e), 0.55 + 0.35 * e), lw * (2.0 + 1.5 * e))
            caneta.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(caneta)
            a0 = math.degrees(ini + self._orbita * (1.0 if k % 2 == 0 else -0.7))
            p.drawArc(caixa, int(-a0 * 16), int(-math.degrees(vao) * 16))

        # ── COGNIÇÃO: hemisfério ────────────────────────────────────────────
        p.save()
        p.translate(cx, cy)
        p.scale(r, r)
        grad = QRadialGradient(QPointF(-0.35, -0.05), 0.75)
        grad.setColorAt(0.0, _c(_mix(main, accent, e * 0.5), 0.22 + 0.10 * self._think))
        grad.setColorAt(1.0, _c(main, 0.05))
        p.setBrush(grad)
        borda = QPen(_c(_mix(main, accent, e * 0.6), 0.65), lw * 1.4)
        borda.setCosmetic(True)
        p.setPen(borda)
        p.drawPath(self._cerebro)
        # giros (as dobras do cérebro), recortados no hemisfério
        p.setClipPath(self._cerebro)
        dobra = QPen(_c(main, 0.22 + 0.10 * self._think), lw * 1.1)
        dobra.setCosmetic(True)
        p.setPen(dobra)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for dobra_path in self._dobras:
            p.drawPath(dobra_path)
        p.setClipping(False)
        p.restore()

        # sinapses
        nos = [self._ponto(cx, cy, r, x, y) for x, y in self._nos]
        bus_x = cx
        for i, j in self._arestas:
            p0 = nos[i]
            p1 = nos[j] if j >= 0 else QPointF(bus_x, p0.y())
            p.setPen(QPen(_c(main, 0.18 + 0.12 * self._think), lw))
            p.drawLine(p0, p1)
        for k, pos, _v in self._pulsos:
            i, j = self._arestas[int(k)]
            p0 = nos[i]
            p1 = nos[j] if j >= 0 else QPointF(bus_x, p0.y())
            pt = QPointF(p0.x() + (p1.x() - p0.x()) * pos, p0.y() + (p1.y() - p0.y()) * pos)
            self._brilho_em(p, pt, r * 0.035, accent, 0.9)
            p.setBrush(_c(branco, 0.9))
            p.drawEllipse(pt, r * 0.007, r * 0.007)
        for i, pt in enumerate(nos):
            b = self._brilho[i]
            if b > 0.05:
                self._brilho_em(p, pt, r * (0.03 + 0.04 * b), accent, b)
            p.setBrush(_mix(_mix(branco, main, 0.35), accent, b))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(pt, r * (0.011 + 0.006 * b), r * (0.011 + 0.006 * b))

        # ── AUTOMAÇÃO: trilhas e engrenagens ────────────────────────────────
        trilha_pen = QPen(_c(ouro, 0.30 + 0.25 * self._auto), lw * 1.2)
        trilha_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        for linha in _TRILHAS:
            p.setPen(trilha_pen)
            for (x0, y0), (x1, y1) in zip(linha, linha[1:]):
                p.drawLine(self._ponto(cx, cy, r, x0, y0), self._ponto(cx, cy, r, x1, y1))
            fim = self._ponto(cx, cy, r, *linha[-1])
            p.setBrush(_c(ouro, 0.7))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(fim, r * 0.010, r * 0.010)
        for k, pos in self._trilha:
            linha = _TRILHAS[int(k)]
            seg = len(linha) - 1
            s = min(seg - 1e-6, pos * seg)
            i = int(s)
            f = s - i
            (x0, y0), (x1, y1) = linha[i], linha[i + 1]
            pt = self._ponto(cx, cy, r, x0 + (x1 - x0) * f, y0 + (y1 - y0) * f)
            self._brilho_em(p, pt, r * 0.03, ouro, 0.8)

        for idx, ((gx, gy, gr, dentes, fase), path) in enumerate(zip(_ENGRENAGENS, self._engr)):
            razao = _ENGRENAGENS[0][2] / gr
            sentido = 1.0 if idx == 0 else -1.0
            ang = math.degrees(self._giro * razao * sentido) + fase * 360 / dentes
            p.save()
            p.translate(cx + gx * r, cy + gy * r)
            p.rotate(ang)
            p.scale(gr * r, gr * r)
            corpo = QRadialGradient(QPointF(0, 0), 1.0)
            corpo.setColorAt(0.0, _c(ouro, 0.30 + 0.20 * self._auto))
            corpo.setColorAt(1.0, _c(ouro, 0.10 + 0.10 * self._auto))
            p.setBrush(corpo)
            contorno = QPen(_c(_mix(ouro, accent, self._auto * 0.4), 0.80), lw * 1.4)
            contorno.setCosmetic(True)
            p.setPen(contorno)
            p.drawPath(path)
            interno = QPen(_c(ouro, 0.55), lw)
            interno.setCosmetic(True)
            p.setPen(interno)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(0, 0), 0.56, 0.56)
            for s in range(5 if dentes > 6 else 3):
                aa = s * TAU / (5 if dentes > 6 else 3)
                p.drawLine(QPointF(math.cos(aa) * 0.22, math.sin(aa) * 0.22),
                           QPointF(math.cos(aa) * 0.56, math.sin(aa) * 0.56))
            p.restore()

        # ── BARRAMENTO: a costura entre as metades ──────────────────────────
        topo, base = cy - r * 0.74, cy + r * 0.74
        for larg, alfa in ((lw * 6, 0.06 + 0.06 * self._auto), (lw * 2.2, 0.35 + 0.3 * e), (lw, 0.8)):
            p.setPen(QPen(_c(_mix(main, accent, max(e, self._auto * 0.6)), alfa), larg))
            p.drawLine(QPointF(cx, topo), QPointF(cx, base))
        for y, _d, vida in self._bus:
            pt = QPointF(cx, cy + y * r)
            self._brilho_em(p, pt, r * 0.04, accent, 0.9 * vida)

        # anéis de voz e o núcleo
        nucleo = QPointF(cx, cy + r * 0.02)
        for idade in self._rings:
            k = idade / 1.5
            rr = r * (0.07 + 0.80 * k)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(_c(accent, 0.45 * (1.0 - k)), lw * (2.2 - 1.6 * k)))
            p.drawEllipse(nucleo, rr, rr)
        pulso = 1.0 + 0.06 * math.sin(t * 2.4) + 0.5 * a
        self._brilho_em(p, nucleo, r * 0.20 * pulso, accent, 0.55 + 0.35 * e)
        p.setBrush(_c(branco, 0.95))
        p.setPen(QPen(_c(accent, 0.9), lw * 1.5))
        p.drawEllipse(nucleo, r * 0.045 * pulso, r * 0.045 * pulso)

        # nome
        txt = (name or "I.S.A.").upper()
        f = self._font(txt, r)
        p.setFont(f)
        p.setPen(_c(_mix(branco, main, 0.3), 0.75 + 0.2 * e))
        p.drawText(QRectF(cx - r, cy + r * 0.60, 2 * r, r * 0.22),
                   int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), txt)
        p.restore()
