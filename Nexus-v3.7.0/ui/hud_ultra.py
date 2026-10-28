"""NEXUS Ultra 2026 — dez visuais novos para o hub (HUD).

Cada visual é uma função  f(cv, p, W, H, cx, cy, R, main, acc, amp)  que desenha
um quadro. `cv` é o HudCanvas: de lá vêm a fase da animação (`_fase`, que acelera
quando o NEXUS pensa ou fala), o histórico real do áudio (`_hv(u)`), o estado
(`muted`, `speaking`, `state`) e o relógio (`_tick`).

Regras de todos os visuais:
  • só QPainter — nada de bibliotecas novas, nada de arquivo de imagem;
  • sem estado fora do canvas (o que precisa lembrar vai em `cv._ux`);
  • leves: nenhuma conta passa de algumas centenas de operações por quadro;
  • a voz faz o visual crescer, brilhar ou acelerar; mudo deixa tudo quase parado.

Para criar o seu: escreva a função aqui, coloque em ULTRA_STYLES e acrescente a chave
em memory/config_manager.py › HUD_STYLES. Ele aparece sozinho na lista do hub.
"""
from __future__ import annotations

import math
import random

from PyQt6.QtGui import QPolygonF

from ._qt import *  # noqa: F401,F403
from ._base import C, FONT_MONO, accent2, qcol  # noqa: F401


# ── ajudantes ────────────────────────────────────────────────────────────────
def _rgba(c: QColor, a: float) -> QColor:
    out = QColor(c)
    out.setAlpha(max(0, min(255, int(a))))
    return out


def _est(cv, chave: str, criar):
    """Estado do visual, guardado no próprio canvas (criado uma vez)."""
    ux = cv.__dict__.setdefault("_ux", {})
    if chave not in ux:
        ux[chave] = criar()
    return ux[chave]


def _calmo(cv) -> float:
    """1.0 normal; ~0.25 quando mudo (tudo quase parado)."""
    return 0.25 if getattr(cv, "muted", False) else 1.0


def _glow(p: QPainter, x: float, y: float, r: float, cor: QColor, a: float) -> None:
    """Mancha de luz suave (degradê radial que some na borda)."""
    if r <= 0.5:
        return
    g = QRadialGradient(x, y, r)
    g.setColorAt(0.0, _rgba(cor, a))
    g.setColorAt(1.0, _rgba(cor, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(x, y), r, r)


def _nucleo(p: QPainter, cx: float, cy: float, r: float, main: QColor, acc: QColor, amp: float) -> None:
    """Núcleo brilhante comum a vários visuais."""
    _glow(p, cx, cy, r * 2.4, acc, 60 + 120 * min(1.0, amp * 1.4))
    _glow(p, cx, cy, r * 1.3, main, 150 + 90 * min(1.0, amp))
    _glow(p, cx, cy, r * 0.55, QColor("#ffffff"), 210)


# ── 1. Nebulosa ──────────────────────────────────────────────────────────────
def nebulosa(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Nuvens de luz que orbitam e estrelas que piscam; a voz incha as nuvens."""
    estrelas = _est(cv, "neb", lambda: [
        (r.random(), r.random(), r.uniform(0, 6.28), r.uniform(0.6, 2.2))
        for r in (random.Random(11),) for _ in range(80)])
    f = cv._fase * _calmo(cv)
    violeta = qcol(C.VIOLET)
    cores = (main, acc, violeta, main, acc)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    for k, cor in enumerate(cores):
        ang = f * (0.22 + 0.07 * k) + k * 1.26
        x = cx + math.cos(ang) * R * (0.42 + 0.12 * math.sin(f * 0.5 + k))
        y = cy + math.sin(ang * 1.1) * R * 0.38
        raio = R * (0.62 + 0.10 * math.sin(f * 0.8 + k * 2) + 0.38 * amp)
        _glow(p, x, y, raio, cor, 34 + 62 * amp)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    for sx, sy, ph, tam in estrelas:
        br = 0.5 + 0.5 * math.sin(f * 2.0 + ph)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_rgba(QColor("#ffffff"), 50 + 190 * br))
        p.drawEllipse(QPointF(sx * W, sy * H * 0.82), tam * (0.7 + amp), tam * (0.7 + amp))
    _nucleo(p, cx, cy, R * (0.16 + 0.10 * amp), main, acc, amp)


# ── 2. Giroscópio ────────────────────────────────────────────────────────────
def giroscopio(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Três anéis em 3D que giram e se inclinam; um ponto de luz corre em cada um."""
    f = cv._fase * _calmo(cv)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for k in range(3):
        raio = R * (0.92 - 0.14 * k) * (1.0 + 0.06 * amp)
        rot = math.radians(k * 60 + f * (22 + 9 * k) * (1 if k % 2 == 0 else -1))
        sy = max(0.14, abs(math.cos(f * (0.55 + 0.22 * k) + k)))
        cor = acc if k == 1 else main
        p.save()
        p.translate(cx, cy)
        p.rotate(math.degrees(rot))
        p.scale(1.0, sy)
        p.setPen(QPen(_rgba(cor, 120 + 110 * min(1.0, amp * 1.5)), (2.2 if k == 0 else 1.6) / max(0.4, sy ** 0.4)))
        p.drawEllipse(QPointF(0, 0), raio, raio)
        p.restore()
        a = f * (1.6 + 0.5 * k) + k * 2.1
        px, py = math.cos(a) * raio, math.sin(a) * raio * sy
        x = cx + px * math.cos(rot) - py * math.sin(rot)
        y = cy + px * math.sin(rot) + py * math.cos(rot)
        _glow(p, x, y, 9 + 6 * amp, cor, 230)
    _nucleo(p, cx, cy, R * (0.18 + 0.09 * amp), main, acc, amp)


# ── 3. Hélice (DNA) ──────────────────────────────────────────────────────────
def helice(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Dupla hélice que atravessa a tela; a voz abre e agita as fitas."""
    f = cv._fase * _calmo(cv)
    n = 30
    x0, larg = W * 0.07, W * 0.86
    pontos = []
    for i in range(n + 1):
        u = i / n
        env = 0.45 + 0.55 * math.sin(math.pi * u) ** 0.8
        A = R * 0.5 * env * (0.55 + 0.9 * cv._hv(u) + 0.35 * amp)
        ph = u * math.pi * 3.6 + f * 2.2
        pontos.append((x0 + larg * u, cy + A * math.sin(ph), cy - A * math.sin(ph), math.cos(ph)))
    for x, y1, y2, z in pontos:                                  # degraus
        p.setPen(QPen(_rgba(qcol(C.VIOLET), 40 + 70 * (0.5 + 0.5 * z)), 1.2))
        p.drawLine(QPointF(x, y1), QPointF(x, y2))
    for lado, cor in ((1, main), (2, acc)):                      # as duas fitas
        path = QPainterPath()
        for i, pt in enumerate(pontos):
            q = QPointF(pt[0], pt[lado])
            path.moveTo(q) if i == 0 else path.lineTo(q)
        p.setPen(QPen(_rgba(cor, 150 + 90 * amp), 2.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
    for x, y1, y2, z in pontos[::2]:                             # esferas (maiores quando "na frente")
        for y, cor, zz in ((y1, main, z), (y2, acc, -z)):
            r = 2.6 + 2.6 * (0.5 + 0.5 * zz) + 2 * amp
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_rgba(cor, 110 + 140 * (0.5 + 0.5 * zz)))
            p.drawEllipse(QPointF(x, y), r, r)


# ── 4. Sonar ─────────────────────────────────────────────────────────────────
def sonar(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Ondas saem do núcleo quando alguém fala; uma varredura gira por cima."""
    import time
    agora = time.time()
    ondas = _est(cv, "sonar", lambda: {"t": [], "ult": 0.0})
    intervalo = 0.34 if amp > 0.18 else 1.7
    if not cv.muted and agora - ondas["ult"] > intervalo:
        ondas["t"].append(agora)
        ondas["ult"] = agora
    ondas["t"] = [t for t in ondas["t"] if agora - t < 2.4]
    p.setBrush(Qt.BrushStyle.NoBrush)
    for r_ in (0.35, 0.65, 0.95):                                 # grade fixa
        p.setPen(QPen(_rgba(main, 34), 1))
        p.drawEllipse(QPointF(cx, cy), R * r_, R * r_)
    p.setPen(QPen(_rgba(main, 28), 1))
    p.drawLine(QPointF(cx - R, cy), QPointF(cx + R, cy))
    p.drawLine(QPointF(cx, cy - R), QPointF(cx, cy + R))
    for t in ondas["t"]:
        idade = (agora - t) / 2.4
        raio = R * 1.05 * idade ** 0.8
        p.setPen(QPen(_rgba(acc if idade < 0.5 else main, 220 * (1 - idade)), 2.4 - 1.6 * idade))
        p.drawEllipse(QPointF(cx, cy), raio, raio)
    a0 = cv._fase * 1.9 * _calmo(cv)                              # varredura
    for j in range(16):
        a = a0 - j * 0.07
        p.setPen(QPen(_rgba(main, 150 * (1 - j / 16)), 2))
        p.drawLine(QPointF(cx, cy), QPointF(cx + math.cos(a) * R * 0.98, cy + math.sin(a) * R * 0.98))
    _nucleo(p, cx, cy, R * (0.10 + 0.06 * amp), main, acc, amp)


# ── 5. Espectro ──────────────────────────────────────────────────────────────
def espectro(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Equalizador espelhado com picos que caem devagar."""
    n = 41
    picos = _est(cv, "spec", lambda: [0.0] * n)
    larg = W * 0.86
    x0 = (W - larg) / 2
    passo = larg / n
    meio = (n - 1) / 2
    f = cv._fase * _calmo(cv)
    altmax = R * 0.95
    for i in range(n):
        d = abs(i - meio) / meio                                  # 0 no centro, 1 nas pontas
        v = cv._hv(1.0 - d) * (0.55 + 0.45 * (1 - d))
        v += 0.05 + 0.04 * (0.5 + 0.5 * math.sin(f * 2.4 + i * 0.7))
        v = min(1.0, v * 1.15)
        picos[i] = max(v, picos[i] - 0.018)
        h = max(3.0, v * altmax)
        x = x0 + i * passo
        g = QLinearGradient(0, cy - h, 0, cy + h)
        g.setColorAt(0.0, _rgba(acc, 230))
        g.setColorAt(0.5, _rgba(main, 255))
        g.setColorAt(1.0, _rgba(acc, 230))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawRoundedRect(QRectF(x + 1, cy - h, passo - 2.5, h * 2), 2.5, 2.5)
        hp = max(h, picos[i] * altmax) + 5
        p.setBrush(_rgba(QColor("#ffffff"), 190))
        p.drawRect(QRectF(x + 1, cy - hp, passo - 2.5, 2))
        p.drawRect(QRectF(x + 1, cy + hp - 2, passo - 2.5, 2))


# ── 6. Colmeia ───────────────────────────────────────────────────────────────
def colmeia(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Favo de hexágonos; ondas de luz saem do centro e a voz as deixa mais fortes."""
    f = cv._fase * _calmo(cv)
    s = max(9.0, R / 5.2)                                         # lado do hexágono
    dx, dy = s * math.sqrt(3), s * 1.5
    lim = R * 1.08
    cols, lins = int(lim / dx) + 2, int(lim / dy) + 2
    forca = 0.28 + 1.3 * amp
    p.setBrush(Qt.BrushStyle.NoBrush)
    for j in range(-lins, lins + 1):
        for i in range(-cols, cols + 1):
            x = cx + i * dx + (dx / 2 if j % 2 else 0)
            y = cy + j * dy
            d = math.hypot(x - cx, y - cy) / R
            if d > 1.08:
                continue
            onda = 0.5 + 0.5 * math.sin(d * 7.0 - f * 3.0)
            luz = min(1.0, (0.12 + 0.88 * onda ** 3) * forca) * (1.0 - 0.45 * d)
            pts = QPolygonF([QPointF(x + s * 0.93 * math.cos(math.radians(60 * k + 30)),
                                     y + s * 0.93 * math.sin(math.radians(60 * k + 30))) for k in range(6)])
            cor = acc if onda > 0.82 else main
            p.setBrush(_rgba(cor, 190 * luz))
            p.setPen(QPen(_rgba(main, 55 + 120 * luz), 1.1))
            p.drawPolygon(pts)
    _glow(p, cx, cy, R * 0.28, acc, 50 + 150 * amp)


# ── 7. Átomo ─────────────────────────────────────────────────────────────────
def atomo(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Núcleo e três órbitas inclinadas; elétrons deixam rastro e aceleram com a voz."""
    f = cv._fase * _calmo(cv) * (1.0 + amp * 1.6)
    rx, ry = R * 0.95, R * 0.34
    p.setBrush(Qt.BrushStyle.NoBrush)
    for k in range(3):
        rot = math.radians(60 * k + 12 * math.sin(cv._fase * 0.3))
        p.setBrush(Qt.BrushStyle.NoBrush)                          # o pincel do elétron anterior não pode preencher a órbita
        p.save()
        p.translate(cx, cy)
        p.rotate(math.degrees(rot))
        p.setPen(QPen(_rgba(main, 70 + 60 * amp), 1.2))
        p.drawEllipse(QPointF(0, 0), rx, ry)
        p.restore()
        for j in range(9, -1, -1):                                # cabeça (j=0) e rastro
            a = f * (1.7 + 0.35 * k) * (1 if k != 1 else -1) + k * 2.09 - j * 0.14
            ex, ey = math.cos(a) * rx, math.sin(a) * ry
            x = cx + ex * math.cos(rot) - ey * math.sin(rot)
            y = cy + ex * math.sin(rot) + ey * math.cos(rot)
            if j == 0:
                _glow(p, x, y, 13 + 6 * amp, acc, 230)
                p.setBrush(QColor("#ffffff"))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(x, y), 3.2, 3.2)
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(_rgba(acc, 130 * (1 - j / 10)))
                p.drawEllipse(QPointF(x, y), 3.0 - j * 0.2, 3.0 - j * 0.2)
    for k in range(3):                                            # prótons
        a = cv._fase * 0.9 + k * 2.09
        _glow(p, cx + math.cos(a) * R * 0.07, cy + math.sin(a) * R * 0.07, R * 0.13, main, 230)
    _glow(p, cx, cy, R * (0.34 + 0.18 * amp), acc, 70 + 110 * amp)


# ── 8. Plasma ────────────────────────────────────────────────────────────────
def plasma(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Esfera de vidro com raios que saem do centro; quanto mais voz, mais raios."""
    raio = R * 0.8
    g = QRadialGradient(cx - raio * 0.3, cy - raio * 0.35, raio * 1.2)
    g.setColorAt(0.0, _rgba(main, 55))
    g.setColorAt(1.0, _rgba(qcol(C.BG), 235))
    p.setBrush(QBrush(g))
    p.setPen(QPen(_rgba(main, 110), 1.6))
    p.drawEllipse(QPointF(cx, cy), raio, raio)
    _glow(p, cx, cy, raio * 0.9, acc, 40 + 80 * amp)
    n = 3 + int(amp * 7) if not cv.muted else 2
    semente = cv._tick // 3
    p.setBrush(Qt.BrushStyle.NoBrush)
    for i in range(n):
        rng = random.Random(semente * 31 + i * 7)
        alvo = rng.uniform(0, 6.283)
        comp = raio * rng.uniform(0.78, 0.98)
        pts = [QPointF(cx, cy)]
        for s in range(1, 8):
            t = s / 7
            ox = (rng.random() - 0.5) * raio * 0.22 * math.sin(math.pi * t)
            oy = (rng.random() - 0.5) * raio * 0.22 * math.sin(math.pi * t)
            pts.append(QPointF(cx + math.cos(alvo) * comp * t + ox, cy + math.sin(alvo) * comp * t + oy))
        path = QPainterPath(pts[0])
        for q in pts[1:]:
            path.lineTo(q)
        p.setPen(QPen(_rgba(acc, 90 + 80 * amp), 5.0))
        p.drawPath(path)
        p.setPen(QPen(_rgba(QColor("#ffffff"), 230), 1.4))
        p.drawPath(path)
        _glow(p, pts[-1].x(), pts[-1].y(), 9 + 5 * amp, acc, 200)
    _glow(p, cx, cy, raio * 0.25, QColor("#ffffff"), 190)


# ── 9. Constelação ───────────────────────────────────────────────────────────
def constelacao(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Estrelas à deriva se ligam quando chegam perto; a voz aumenta o alcance das linhas."""
    N = 34
    nos = _est(cv, "cst", lambda: [
        (r.uniform(0.25, 0.95), r.uniform(0.2, 0.8), r.uniform(0, 6.28), r.uniform(0, 6.28), r.random() < 0.18)
        for r in (random.Random(5),) for _ in range(N)])
    f = cv._fase * 0.34 * _calmo(cv)
    pos = []
    for i, (a, b, ph, qh, especial) in enumerate(nos):
        x = cx + math.sin(f * a * 1.7 + ph) * W * 0.40
        y = cy + math.sin(f * b * 1.9 + qh) * H * 0.34
        pos.append((x, y, especial))
    alcance = R * (0.62 + 0.55 * amp)
    for i in range(N):
        xi, yi, _ = pos[i]
        for j in range(i + 1, N):
            xj, yj, _ = pos[j]
            d = math.hypot(xi - xj, yi - yj)
            if d < alcance:
                p.setPen(QPen(_rgba(main, 170 * (1 - d / alcance) ** 1.2), 1.1))
                p.drawLine(QPointF(xi, yi), QPointF(xj, yj))
    p.setPen(Qt.PenStyle.NoPen)
    for i, (x, y, especial) in enumerate(pos):
        r = 2.0 + 2.2 * cv._hv((i % 12) / 12) + (1.8 if especial else 0)
        if especial:
            _glow(p, x, y, r * 4.5, acc, 150)
        p.setBrush(_rgba(acc if especial else QColor("#ffffff"), 235))
        p.drawEllipse(QPointF(x, y), r, r)


# ── 10. Túnel ────────────────────────────────────────────────────────────────
def tunel(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Viagem em dobra: quadrados luminosos voam na sua direção; a voz acelera a viagem."""
    f = cv._fase * _calmo(cv)
    n = 13
    avanco = (f * 0.16 * (1.0 + amp * 2.2)) % 1.0
    p.setBrush(Qt.BrushStyle.NoBrush)
    if amp > 0.05 and not cv.muted:                               # riscos de velocidade
        rng = random.Random(cv._tick // 2)
        for _ in range(int(6 + 26 * amp)):
            a = rng.uniform(0, 6.283)
            r0, r1 = R * rng.uniform(0.2, 0.5), R * rng.uniform(0.6, 1.15)
            p.setPen(QPen(_rgba(acc, 40 + 120 * amp), 1.1))
            p.drawLine(QPointF(cx + math.cos(a) * r0, cy + math.sin(a) * r0),
                       QPointF(cx + math.cos(a) * r1, cy + math.sin(a) * r1))
    for k in range(n):
        z = (k / n + avanco) % 1.0
        esc = z ** 2.3
        lado = R * 1.55 * esc + 3
        p.save()
        p.translate(cx, cy)
        p.rotate(k * 7.0 + f * 9.0 * (0.4 + z))
        cor = acc if k % 4 == 0 else main
        p.setPen(QPen(_rgba(cor, 30 + 215 * z), 0.8 + 2.2 * z))
        p.drawRoundedRect(QRectF(-lado / 2, -lado / 2, lado, lado), lado * 0.12, lado * 0.12)
        p.restore()
    _glow(p, cx, cy, R * (0.22 + 0.2 * amp), acc, 90 + 140 * amp)


# ── registro ─────────────────────────────────────────────────────────────────
# chave: (ícone, nome, descrição curta, função de desenho)
ULTRA_STYLES: dict = {
    "nebula":   ("✦", "Nebulosa", "Nuvens de luz e estrelas que crescem com a voz", nebulosa),
    "gyro":     ("◎", "Giroscópio", "Três anéis em 3D que giram e se inclinam", giroscopio),
    "helix":    ("🧬", "Hélice", "Dupla hélice que se abre e agita com a voz", helice),
    "sonar":    ("◌", "Sonar", "Ondas saem do núcleo quando você ou o NEXUS falam", sonar),
    "spectrum": ("▮", "Espectro", "Equalizador espelhado com picos que caem devagar", espectro),
    "hive":     ("⬢", "Colmeia", "Favo de hexágonos com ondas de luz", colmeia),
    "atom":     ("⚛", "Átomo", "Elétrons com rastro em órbitas inclinadas", atomo),
    "plasma":   ("⚡", "Plasma", "Esfera de vidro com raios que crescem com a voz", plasma),
    "stars":    ("✧", "Constelação", "Estrelas à deriva ligadas por linhas de luz", constelacao),
    "tunnel":   ("⌖", "Túnel", "Viagem em dobra: anéis voando na sua direção", tunel),
}

ULTRA_INFO = {k: v[:3] for k, v in ULTRA_STYLES.items()}
