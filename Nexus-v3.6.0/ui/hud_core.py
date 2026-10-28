"""NexusCore — quinze visuais novos para o hub (HUD).

Mesmo contrato dos visuais do Ultra 2026 (ui/hud_ultra.py): cada visual é uma função
f(cv, p, W, H, cx, cy, R, main, acc, amp) que desenha um quadro. `cv` é o HudCanvas
(fase da animação `_fase`, histórico real do áudio `_hv(u)`, `muted`, `speaking`,
`state`, relógio `_tick`).

Regras de todos os visuais:
  • só QPainter — nada de bibliotecas novas, nada de arquivo de imagem;
  • o que precisa lembrar de um quadro para o outro fica em `cv._ux` (via `_est`);
  • leves: nenhuma conta passa de algumas centenas de operações por quadro;
  • a voz faz o visual crescer, brilhar ou acelerar; mudo deixa tudo quase parado;
  • os ajudantes (`_glow`, `_nucleo`, `_est`, `_calmo`, `_rgba`) vêm do hud_ultra — não
    são copiados aqui.

Para criar o seu: escreva a função, coloque em CORE_STYLES e acrescente a chave em
memory/config_manager.py › HUD_STYLES. Ele aparece sozinho na lista do hub.
"""
from __future__ import annotations

import math
import random
import time

from PyQt6.QtGui import QPolygonF

from ._qt import *  # noqa: F401,F403
from ._base import C, qcol  # noqa: F401
from .hud_ultra import _calmo, _est, _glow, _nucleo, _rgba


def _misto(a: QColor, b: QColor, t: float) -> QColor:
    """Cor entre a e b (t = 0 → a, t = 1 → b)."""
    t = max(0.0, min(1.0, t))
    return QColor(int(a.red() + (b.red() - a.red()) * t),
                  int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t))


def _gauss(x: float, c: float, w: float) -> float:
    return math.exp(-((x - c) / w) ** 2)


# ── 1. Pulsar ────────────────────────────────────────────────────────────────
def pulsar(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Dois feixes opostos giram a partir do núcleo; a voz alarga os feixes e solta anéis de pulso."""
    f = cv._fase * _calmo(cv)
    a0 = f * 1.15
    meia = 0.10 + 0.13 * min(1.0, amp * 1.3)
    comp = R * (0.85 + 0.30 * amp)
    p.setPen(Qt.PenStyle.NoPen)
    for lado in (0.0, math.pi):
        for j in range(6):                                        # do largo e fraco ao fino e forte
            m = meia * (1.0 - j * 0.14)
            a = a0 + lado
            tri = QPolygonF([
                QPointF(cx, cy),
                QPointF(cx + math.cos(a - m) * comp, cy + math.sin(a - m) * comp),
                QPointF(cx + math.cos(a + m) * comp, cy + math.sin(a + m) * comp)])
            p.setBrush(_rgba(acc if j >= 4 else main, 22 + 20 * j + 60 * amp))
            p.drawPolygon(tri)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for i in range(3):                                            # anéis de pulso
        t = (f * 0.22 + i / 3) % 1.0
        r = R * (0.15 + 0.85 * t)
        p.setPen(QPen(_rgba(main, 150 * (1 - t) * (0.4 + amp)), 1.8))
        p.drawEllipse(QPointF(cx, cy), r, r)
    _nucleo(p, cx, cy, R * (0.13 + 0.08 * amp), main, acc, amp)


# ── 2. Órbitas ───────────────────────────────────────────────────────────────
# (raio, achatamento, velocidade, tamanho do planeta, inclinação)
_ORBITAS = ((0.30, 0.62, 2.3, 4.5, 0.2), (0.45, 0.78, 1.5, 6.0, 1.1), (0.60, 0.55, 1.05, 5.0, 2.0),
            (0.76, 0.72, 0.72, 8.0, 0.5), (0.94, 0.50, 0.46, 5.5, 1.6))


def orbitas(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Cinco planetas com rastro em órbitas inclinadas ao redor de uma estrela."""
    f = cv._fase * _calmo(cv)
    for k, (ra, ach, vel, tam, inc) in enumerate(_ORBITAS):
        a, b = R * ra, R * ra * ach
        cor = acc if k % 2 else main
        p.save()
        p.translate(cx, cy)
        p.rotate(math.degrees(inc + f * 0.05 * (1 if k % 2 else -1)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(_rgba(cor, 45 + 40 * amp), 1))
        p.drawEllipse(QPointF(0, 0), a, b)
        t = f * vel + k * 1.7
        p.setPen(Qt.PenStyle.NoPen)
        for j in range(1, 9):                                     # rastro
            tt = t - j * 0.08
            p.setBrush(_rgba(cor, 190 * (1 - j / 9)))
            r = max(0.8, tam * 0.5 * (1 - j / 9))
            p.drawEllipse(QPointF(math.cos(tt) * a, math.sin(tt) * b), r, r)
        px, py = math.cos(t) * a, math.sin(t) * b
        _glow(p, px, py, tam * (2.2 + amp), cor, 210)
        p.setBrush(_rgba(QColor("#ffffff"), 235))
        p.drawEllipse(QPointF(px, py), tam * 0.38, tam * 0.38)
        p.restore()
    _nucleo(p, cx, cy, R * (0.14 + 0.07 * amp), main, acc, amp)


# ── 3. Mandala ───────────────────────────────────────────────────────────────
def mandala(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Três camadas de pétalas que giram em sentidos opostos e desabrocham com a voz."""
    f = cv._fase * _calmo(cv)
    camadas = ((5, 1.00, main, 0.20), (7, 0.78, acc, -0.28), (9, 0.55, main, 0.36))
    for k, (petalas, esc, cor, vel) in enumerate(camadas):
        rot = f * vel
        caminho = QPainterPath()
        n = 160
        for i in range(n + 1):
            th = i * 2 * math.pi / n
            r = R * esc * (0.30 + 0.70 * abs(math.cos(petalas * th / 2))) \
                * (0.78 + 0.42 * amp + 0.06 * math.sin(f * 1.6 + k))
            x, y = cx + math.cos(th + rot) * r, cy + math.sin(th + rot) * r
            if i == 0:
                caminho.moveTo(x, y)
            else:
                caminho.lineTo(x, y)
        caminho.closeSubpath()
        p.setPen(QPen(_rgba(cor, 200), 1.4))
        p.setBrush(_rgba(cor, 22 + 34 * amp))
        p.drawPath(caminho)
    _nucleo(p, cx, cy, R * (0.10 + 0.06 * amp), main, acc, amp)


# ── 4. Circuito ──────────────────────────────────────────────────────────────
def _circuito_tracos():
    """18 trilhas (em unidades de R) saindo do centro com uma curva de 45° no meio."""
    rng = random.Random(21)
    tracos = []
    for i in range(18):
        a = i * math.tau / 18
        d1, d2, d3 = rng.uniform(0.40, 0.58), rng.uniform(0.14, 0.28), rng.uniform(0.08, 0.20)
        a2 = a + rng.choice((-1, 1)) * math.pi / 4
        p0 = (math.cos(a) * 0.24, math.sin(a) * 0.24)
        p1 = (math.cos(a) * d1, math.sin(a) * d1)
        p2 = (p1[0] + math.cos(a2) * d2, p1[1] + math.sin(a2) * d2)
        p3 = (p2[0] + math.cos(a) * d3, p2[1] + math.sin(a) * d3)
        pts = (p0, p1, p2, p3)
        comp = [math.dist(pts[j], pts[j + 1]) for j in range(3)]
        tracos.append((pts, comp, sum(comp), rng.uniform(0.12, 0.40), rng.random()))
    return tracos


def _ponto_em(pts, comp, total, t):
    d = t * total
    for j, c in enumerate(comp):
        if d <= c or j == len(comp) - 1:
            u = min(1.0, d / c) if c else 0.0
            return (pts[j][0] + (pts[j + 1][0] - pts[j][0]) * u,
                    pts[j][1] + (pts[j + 1][1] - pts[j][1]) * u)
        d -= c
    return pts[-1]


def circuito(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Placa de circuito: pulsos de luz correm pelas trilhas até os nós; a voz acende tudo."""
    tracos = _est(cv, "circ", _circuito_tracos)
    f = cv._fase * _calmo(cv)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(_rgba(main, 60 + 40 * amp), 1.2))
    p.drawEllipse(QPointF(cx, cy), R * 0.22, R * 0.22)
    for pts, comp, total, vel, fase in tracos:
        poli = QPolygonF([QPointF(cx + x * R, cy + y * R) for x, y in pts])
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(_rgba(main, 55 + 100 * amp), 1.3))
        p.drawPolyline(poli)
        ex, ey = pts[-1]
        p.setPen(QPen(_rgba(acc, 120 + 100 * amp), 1.3))
        p.drawEllipse(QPointF(cx + ex * R, cy + ey * R), 2.8, 2.8)
        t = (f * vel * (1 + amp) + fase) % 1.0
        x, y = _ponto_em(pts, comp, total, t)
        _glow(p, cx + x * R, cy + y * R, 6 + 5 * amp, acc, 230)
    _nucleo(p, cx, cy, R * (0.11 + 0.06 * amp), main, acc, amp)


# ── 5. Cristal ───────────────────────────────────────────────────────────────
def cristal(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Cristal de 16 faces; as faces acendem em sequência e o cristal incha com a voz."""
    f = cv._fase * _calmo(cv)
    n = 8
    re, ri = R * (0.86 + 0.10 * amp), R * (0.40 + 0.06 * amp)
    ge, gi = f * 0.35, -f * 0.55
    ext = [QPointF(cx + math.cos(ge + i * math.tau / n) * re, cy + math.sin(ge + i * math.tau / n) * re)
           for i in range(n)]
    inn = [QPointF(cx + math.cos(gi + (i + 0.5) * math.tau / n) * ri,
                   cy + math.sin(gi + (i + 0.5) * math.tau / n) * ri) for i in range(n)]
    for i in range(n):
        j = (i + 1) % n
        for s, tri in enumerate(((ext[i], ext[j], inn[i]), (inn[i], inn[j], ext[j]))):
            luz = 0.5 + 0.5 * math.sin(f * 1.8 + i * 0.9 + s * 1.7)
            cor = acc if (i + s) % 2 else main
            p.setBrush(_rgba(cor, 18 + 110 * luz * (0.5 + amp)))
            p.setPen(QPen(_rgba(cor, 120 + 100 * luz), 1.1))
            p.drawPolygon(QPolygonF(list(tri)))
    _nucleo(p, cx, cy, R * (0.10 + 0.06 * amp), main, acc, amp)


# ── 6. Lissajous ─────────────────────────────────────────────────────────────
def lissajous(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Duas curvas de osciloscópio entrelaçadas; a voz estica cada trecho conforme o áudio real."""
    f = cv._fase * _calmo(cv)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for k, (a, b, cor, esc) in enumerate(((3, 2, main, 1.0), (5, 4, acc, 0.78))):
        d = f * (0.7 + 0.3 * k) * (1 if k == 0 else -1)
        caminho = QPainterPath()
        n = 200
        for i in range(n + 1):
            u = i / n
            t = u * math.tau
            m = min(1.0, 0.55 + 0.45 * cv._hv(abs(2 * u - 1)) + 0.25 * amp)
            x = cx + math.sin(a * t + d) * R * 0.95 * esc * m
            y = cy + math.sin(b * t) * R * 0.95 * esc * m
            if i == 0:
                caminho.moveTo(x, y)
            else:
                caminho.lineTo(x, y)
        p.setPen(QPen(_rgba(cor, 40 + 30 * amp), 5.5))
        p.drawPath(caminho)
        p.setPen(QPen(_rgba(cor, 235), 1.6))
        p.drawPath(caminho)
    _glow(p, cx, cy, R * 0.25, acc, 60 + 100 * amp)


# ── 7. Vórtice ───────────────────────────────────────────────────────────────
def vortice(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Três braços de partículas em espiral, puxadas para o núcleo; a voz acelera o redemoinho."""
    f = cv._fase * _calmo(cv)
    bracos, por = 3, 44
    p.setPen(Qt.PenStyle.NoPen)
    for b in range(bracos):
        for i in range(por):
            u = (i / por - f * 0.07 * (1 + amp * 1.5)) % 1.0     # 1 = borda, 0 = centro
            r = R * (0.06 + 0.98 * u)
            ang = b * math.tau / bracos + u * 5.2 + f * 0.35
            perto = 1.0 - u
            tam = 1.2 + 3.2 * perto * (0.8 + 0.7 * amp)
            p.setBrush(_rgba(acc if (b + i) % 5 == 0 else main, 40 + 215 * perto ** 0.7))
            p.drawEllipse(QPointF(cx + math.cos(ang) * r, cy + math.sin(ang) * r), tam, tam)
    _glow(p, cx, cy, R * 0.55, acc, 60 + 120 * amp)
    _nucleo(p, cx, cy, R * (0.09 + 0.05 * amp), main, acc, amp)


# ── 8. Faíscas ───────────────────────────────────────────────────────────────
def faiscas(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Fagulhas saem do núcleo quando alguém fala e esfriam no caminho; mudo não solta nenhuma."""
    agora = time.time()
    st = _est(cv, "faisca", lambda: {"p": [], "t": agora, "acum": 0.0})
    dt = max(0.0, min(0.1, agora - st["t"]))
    st["t"] = agora
    if not cv.muted:
        st["acum"] += dt * (3 + 70 * amp)
        for _ in range(min(int(st["acum"]), 12)):
            a = random.uniform(0, math.tau)
            v = R * random.uniform(0.7, 1.9) * (0.6 + 0.8 * amp)
            st["p"].append([0.0, 0.0, math.cos(a) * v, math.sin(a) * v, random.uniform(0.7, 1.5), 0.0])
        st["acum"] -= int(st["acum"])
    freio = 0.12 ** dt
    vivas = []
    p.setBrush(Qt.BrushStyle.NoBrush)
    for s in st["p"]:                                             # [dx, dy, vx, vy, vida, idade]
        s[5] += dt
        if s[5] >= s[4]:
            continue
        s[0] += s[2] * dt
        s[1] += s[3] * dt
        s[2] *= freio
        s[3] *= freio
        v = 1.0 - s[5] / s[4]
        p.setPen(QPen(_rgba(acc if v > 0.5 else main, 230 * v), 1.0 + 1.8 * v))
        p.drawLine(QPointF(cx + s[0], cy + s[1]), QPointF(cx + s[0] - s[2] * 0.04, cy + s[1] - s[3] * 0.04))
        vivas.append(s)
    st["p"] = vivas[-220:]
    _nucleo(p, cx, cy, R * (0.11 + 0.08 * amp), main, acc, amp)


# ── 9. Coroa ─────────────────────────────────────────────────────────────────
def coroa(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Eclipse: disco escuro cercado de raios cujo comprimento segue o nível real da voz."""
    f = cv._fase * _calmo(cv)
    n, r0 = 120, R * 0.36
    _glow(p, cx, cy, r0 * 1.9, acc, 70 + 110 * amp)
    for i in range(n):
        u = i / n
        a = u * math.tau + f * 0.05
        h = cv._hv(abs(2 * u - 1))                                # espelhado: o mesmo nos dois lados
        ruido = 0.5 + 0.5 * math.sin(f * 1.7 + i * 0.83) * math.sin(i * 0.37 + f * 0.6)
        comp = R * (0.10 + 0.50 * h + 0.12 * ruido + 0.20 * amp)
        p.setPen(QPen(_rgba(acc if i % 3 == 0 else main, 70 + 150 * min(1.0, h + amp)),
                      2.4 if i % 4 == 0 else 1.4))
        p.drawLine(QPointF(cx + math.cos(a) * r0 * 1.02, cy + math.sin(a) * r0 * 1.02),
                   QPointF(cx + math.cos(a) * (r0 + comp), cy + math.sin(a) * (r0 + comp)))
    p.setPen(QPen(_rgba(QColor("#ffffff"), 190), 1.6))
    p.setBrush(QColor(4, 6, 12))
    p.drawEllipse(QPointF(cx, cy), r0, r0)


# ── 10. Grade ────────────────────────────────────────────────────────────────
def grade(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Sol listrado sobre um chão em perspectiva que avança; a voz acelera a viagem."""
    f = cv._fase * _calmo(cv)
    yb = H * 0.82
    yh = cy + R * 0.12                                            # horizonte
    raio = R * 0.55 * (1 + 0.07 * amp)
    sy = yh - raio * 0.78
    _glow(p, cx, yh, R * 1.1, acc, 50 + 80 * amp)
    disco = QPainterPath()
    disco.addEllipse(QPointF(cx, sy), raio, raio)
    p.save()
    p.setClipPath(disco)
    p.setPen(Qt.PenStyle.NoPen)
    fatias = 16
    alt = 2 * raio / fatias
    violeta = qcol(C.VIOLET)
    for s in range(fatias):
        corte = 0.0 if s < fatias * 0.45 else min(0.85, (s - fatias * 0.45) / (fatias * 0.55) * 0.95)
        p.setBrush(_rgba(_misto(acc, violeta, s / (fatias - 1)), 235))
        p.drawRect(QRectF(cx - raio, sy - raio + s * alt, 2 * raio, alt * (1 - corte)))
    p.restore()
    p.setPen(QPen(_rgba(main, 200), 1.6))
    p.drawLine(QPointF(0, yh), QPointF(W, yh))
    for i in range(-9, 10):                                       # linhas que fogem para o horizonte
        p.setPen(QPen(_rgba(main, 70 + 90 * amp), 1.1))
        p.drawLine(QPointF(cx + i * W * 0.004, yh), QPointF(cx + i * W * 0.115, yb))
    for k in range(8):                                            # linhas que vêm na sua direção
        z = (k / 8 + f * 0.12 * (1 + 2 * amp)) % 1.0
        p.setPen(QPen(_rgba(acc, 30 + 200 * z), 0.8 + 1.4 * z))
        y = yh + (yb - yh) * z ** 2.2
        p.drawLine(QPointF(0, y), QPointF(W, y))


# ── 11. Pêndulos ─────────────────────────────────────────────────────────────
def pendulos(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Onda de pêndulos: cada um com um ritmo, então eles se alinham e se desalinham em padrões."""
    f = cv._fase * _calmo(cv)
    n = 17
    topo, L = cy - R * 0.88, R * 1.30
    x0, x1 = W * 0.18, W * 0.82                                   # sobra espaço dos lados para o balanço
    A = 0.10 + 0.20 * min(1.0, amp * 1.4)
    p.setPen(QPen(_rgba(main, 110), 2))
    p.drawLine(QPointF(x0 - 10, topo), QPointF(x1 + 10, topo))
    for i in range(n):
        px = x0 + (x1 - x0) * i / (n - 1)
        th = A * math.sin(f * (0.55 + i * 0.040))
        bx, by = px + math.sin(th) * L, topo + math.cos(th) * L
        cor = acc if i % 2 else main
        p.setPen(QPen(_rgba(cor, 70), 1))
        p.drawLine(QPointF(px, topo), QPointF(bx, by))
        _glow(p, bx, by, 10 + 6 * amp, cor, 200)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_rgba(cor, 245))
        p.drawEllipse(QPointF(bx, by), 4 + 2 * amp, 4 + 2 * amp)


# ── 12. Meteoros ─────────────────────────────────────────────────────────────
def meteoros(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Chuva de meteoros em diagonal; em silêncio caem poucos, com a voz o céu enche."""
    meteoros_ = _est(cv, "meteoros", lambda: [
        (r.random(), r.random(), r.uniform(0.6, 1.4), r.uniform(0.07, 0.16), r.random())
        for r in (random.Random(7),) for _ in range(34)])
    f = cv._fase * _calmo(cv)
    limiar = 0.30 + 0.70 * min(1.0, amp * 1.3)
    dx, dy = -0.447, 0.894
    _glow(p, cx, cy + R * 1.1, R * 0.9, main, 40 + 40 * amp)
    p.save()
    p.setClipRect(QRectF(0, 0, W, H * 0.83))
    for fase, faixa, vel, comp, sorte in meteoros_:
        if sorte > limiar:
            continue
        t = (f * 0.09 * vel + fase) % 1.0
        s = t * H * 1.1
        hx, hy = W * (0.25 + 0.9 * faixa) + dx * s, -H * 0.05 + dy * s
        fade = math.sin(math.pi * t) ** 0.5
        tam = comp * H
        for j in range(6):                                        # cauda em 6 trechos
            p.setPen(QPen(_rgba(main, 230 * (1 - j / 6) * fade), 2.2 - 1.4 * j / 6))
            p.drawLine(QPointF(hx - dx * tam * j / 6, hy - dy * tam * j / 6),
                       QPointF(hx - dx * tam * (j + 1) / 6, hy - dy * tam * (j + 1) / 6))
        _glow(p, hx, hy, 7 + 5 * amp, acc, 220 * fade)
    p.restore()


# ── 13. Bolhas ───────────────────────────────────────────────────────────────
def bolhas(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Bolhas de vidro sobem balançando e incham quando há voz."""
    bolhas_ = _est(cv, "bolhas", lambda: [
        (r.random(), r.random(), r.uniform(0.6, 1.4), r.uniform(0.5, 1.4))
        for r in (random.Random(13),) for _ in range(24)])
    f = cv._fase * _calmo(cv)
    _glow(p, cx, H * 0.80, R * 1.0, acc, 50 + 90 * amp)
    for lane, fase, vel, tam in bolhas_:
        t = (f * 0.05 * vel + fase) % 1.0
        x = W * (0.08 + 0.84 * lane) + math.sin(f * 0.9 + fase * 20) * W * 0.02
        y = H * 0.80 - t * H * 0.74
        r = R * 0.12 * tam * (0.7 + 0.6 * t) * (0.85 + 0.5 * amp)
        al = 1.0 - t ** 3
        cor = acc if lane > 0.5 else main
        g = QRadialGradient(x - r * 0.3, y - r * 0.3, r * 1.2)
        g.setColorAt(0.0, _rgba(QColor("#ffffff"), 90 * al))
        g.setColorAt(0.7, _rgba(cor, 25 * al))
        g.setColorAt(1.0, _rgba(cor, 70 * al))
        p.setBrush(QBrush(g))
        p.setPen(QPen(_rgba(cor, 150 * al), 1.2))
        p.drawEllipse(QPointF(x, y), r, r)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_rgba(QColor("#ffffff"), 170 * al))
        p.drawEllipse(QPointF(x - r * 0.35, y - r * 0.38), r * 0.18, r * 0.12)


# ── 14. Rede ─────────────────────────────────────────────────────────────────
_CAMADAS = (4, 6, 6, 3)


def rede(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Rede neural em quatro camadas: impulsos correm pelas ligações e a última camada segue a voz."""
    f = cv._fase * _calmo(cv)
    x0, x1 = W * 0.14, W * 0.86
    esp = R * 1.7 / (max(_CAMADAS) - 1)
    nos = [[(x0 + (x1 - x0) * c / (len(_CAMADAS) - 1), cy + (i - (n - 1) / 2) * esp) for i in range(n)]
           for c, n in enumerate(_CAMADAS)]
    p.setBrush(Qt.BrushStyle.NoBrush)
    for c in range(len(nos) - 1):
        for i, a in enumerate(nos[c]):
            for j, b in enumerate(nos[c + 1]):
                p.setPen(QPen(_rgba(main, 28 + 40 * amp), 1))
                p.drawLine(QPointF(*a), QPointF(*b))
                if (i * 7 + j * 3 + c) % 3 == 0:                  # só uma em cada três leva impulso
                    t = (f * 0.55 + i * 0.31 + j * 0.17 + c * 0.23) % 1.0
                    _glow(p, a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, 5 + 4 * amp, acc,
                          170 * math.sin(math.pi * t) * (0.5 + 0.5 * min(1.0, amp * 1.5 + 0.4)))
    for c, camada in enumerate(nos):
        for i, (x, y) in enumerate(camada):
            ativ = 0.5 + 0.5 * math.sin(f * 1.4 + c * 1.1 + i * 0.9)
            if c == len(nos) - 1:                                 # a saída reage ao áudio de verdade
                ativ = max(ativ * 0.6, cv._hv((i + 0.5) / len(camada)))
            ativ = min(1.0, ativ * (0.7 + 0.6 * amp))
            _glow(p, x, y, 12 + 10 * ativ, acc if c % 2 else main, 70 + 150 * ativ)
            p.setPen(QPen(_rgba(main, 220), 1.4))
            p.setBrush(_rgba(acc if ativ > 0.6 else main, 60 + 160 * ativ))
            p.drawEllipse(QPointF(x, y), 5, 5)


# ── 15. Batimento ────────────────────────────────────────────────────────────
def _ecg(ph: float) -> float:
    """Um batimento: onda P, complexo QRS e onda T (ph de 0 a 1)."""
    return (0.10 * _gauss(ph, 0.16, 0.035) - 0.12 * _gauss(ph, 0.37, 0.012) + 1.0 * _gauss(ph, 0.41, 0.011)
            - 0.28 * _gauss(ph, 0.455, 0.014) + 0.22 * _gauss(ph, 0.68, 0.06))


def batimento(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Monitor cardíaco: o traçado corre pela tela e os picos crescem com a voz."""
    f = cv._fase * _calmo(cv)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(_rgba(main, 26), 1))
    for k in range(-3, 4):                                        # grade do monitor
        p.drawLine(QPointF(W * 0.05, cy + k * R * 0.28), QPointF(W * 0.95, cy + k * R * 0.28))
    for k in range(-5, 6):
        p.drawLine(QPointF(cx + k * W * 0.08, cy - R * 0.84), QPointF(cx + k * W * 0.08, cy + R * 0.84))
    n, x0, x1 = 140, W * 0.06, W * 0.94
    ritmo = 2.6 + 1.2 * amp
    esc = R * 0.66 * (0.6 + 0.4 * min(1.0, amp * 1.5))
    pts = []
    for i in range(n + 1):
        u = i / n
        v = _ecg((u * ritmo - f * 0.30) % 1.0)
        pts.append(QPointF(x0 + (x1 - x0) * u, cy - v * esc * (0.75 + 0.35 * cv._hv(u))))
    poli = QPolygonF(pts)
    p.setPen(QPen(_rgba(acc, 60), 6))
    p.drawPolyline(poli)
    p.setPen(QPen(_rgba(main, 255), 2.2))
    p.drawPolyline(poli)
    _glow(p, pts[-1].x(), pts[-1].y(), 14 + 8 * amp, acc, 230)


# ── registro ─────────────────────────────────────────────────────────────────
# chave: (ícone, nome, descrição curta, função de desenho)
CORE_STYLES: dict = {
    "pulsar":    ("✺", "Pulsar", "Dois feixes de luz giram e se alargam com a voz", pulsar),
    "orbits":    ("🪐", "Órbitas", "Planetas com rastro em órbitas inclinadas", orbitas),
    "mandala":   ("❁", "Mandala", "Pétalas simétricas que desabrocham com a voz", mandala),
    "circuit":   ("⎔", "Circuito", "Pulsos de luz correndo pelas trilhas até os nós", circuito),
    "crystal":   ("◆", "Cristal", "Cristal facetado cujas faces acendem em sequência", cristal),
    "lissajous": ("∞", "Lissajous", "Curvas de osciloscópio que se deformam com a voz", lissajous),
    "vortex":    ("🌀", "Vórtice", "Espiral de partículas puxadas para o núcleo", vortice),
    "sparks":    ("✹", "Faíscas", "Fagulhas saem do núcleo quando alguém fala", faiscas),
    "corona":    ("☀", "Coroa", "Eclipse com raios que seguem o nível da voz", coroa),
    "grid":      ("▤", "Grade", "Sol listrado e chão em perspectiva que aceleram com a voz", grade),
    "pendulum":  ("⚬", "Pêndulos", "Onda de pêndulos que se alinham e se desalinham", pendulos),
    "meteors":   ("☄", "Meteoros", "Chuva de meteoros que fica mais densa com a voz", meteoros),
    "bubbles":   ("◯", "Bolhas", "Bolhas de vidro que sobem e incham com a voz", bolhas),
    "network":   ("⌬", "Rede", "Rede neural com impulsos que seguem a voz", rede),
    "heartbeat": ("♥", "Batimento", "Monitor cardíaco com picos que crescem com a voz", batimento),
}

CORE_INFO = {k: v[:3] for k, v in CORE_STYLES.items()}
