"""NEXUS Ultra 2026 · 3.6 — vinte visuais novos para o hub (HUD).

Assinatura dos visuais:  f(cv, p, W, H, cx, cy, R, main, acc, amp).
Só QPainter, sem arquivos de imagem, sem estado fora do canvas (`cv._ux`), leves.
A voz faz o visual crescer, brilhar ou acelerar; mudo deixa tudo quase parado.
Para criar o seu: escreva a função, ponha em NOVOS_STYLES e a chave em HUD_STYLES.
"""
from __future__ import annotations

import math
import random

from PyQt6.QtGui import QLinearGradient, QPolygonF

from ._qt import *  # noqa: F401,F403
from ._base import C, qcol  # noqa: F401
from .hud_util import _calmo, _est, _glow, _nucleo, _rgba

_BRANCO = "#ffffff"
TAU = math.tau


def _linha(p, a, b, c, d, cor, larg=1.4):
    p.setPen(QPen(cor, larg))
    p.drawLine(QPointF(a, b), QPointF(c, d))


def _poli(p, pts, cor_borda, cor_fill=None, larg=1.5):
    p.setPen(QPen(cor_borda, larg))
    p.setBrush(cor_fill if cor_fill is not None else Qt.BrushStyle.NoBrush)
    p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))


def _pt(p, x, y, r, cor):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(cor)
    p.drawEllipse(QPointF(x, y), r, r)


def _arco(p, cx, cy, r, ini, fim, cor, larg):
    p.setPen(QPen(cor, larg, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), int(ini * 16), int((fim - ini) * 16))


# 1 ─ Prisma
def prisma(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Triângulo de vidro que abre um leque de cores com a voz."""
    f = cv._fase * _calmo(cv)
    r = R * (0.5 + 0.08 * amp)
    tri = [(cx + math.cos(a) * r, cy + 0.15 * r + math.sin(a) * r) for a in (-1.5708, 0.5236, 2.618)]
    _linha(p, cx - R * 1.1, cy - r * 0.1, cx - r * 0.25, cy, _rgba(QColor(_BRANCO), 200), 2)
    for k in range(7):
        t = k / 6
        ang = -0.35 + t * 0.7 + 0.05 * math.sin(f + k)
        cor = QColor.fromHsvF((t * 0.8 + f * 0.02) % 1.0, 0.7, 1.0)
        L = R * (0.8 + 0.5 * amp)
        _linha(p, cx + r * 0.2, cy, cx + r * 0.2 + math.cos(ang) * L, cy + math.sin(ang) * L,
               _rgba(cor, 170 + 60 * amp), 2.2)
    _poli(p, tri, _rgba(acc, 230), _rgba(main, 40 + 50 * amp), 2.2)


# 2 ─ Origami
def origami(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Polígonos concêntricos dobrando um sobre o outro."""
    f = cv._fase * _calmo(cv)
    for k in range(7):
        n = 3 + k % 4
        r = R * (0.95 - 0.12 * k) * (1 + 0.08 * amp)
        rot = f * (0.3 + 0.08 * k) * (1 if k % 2 else -1)
        pts = [(cx + math.cos(rot + i * TAU / n) * r, cy + math.sin(rot + i * TAU / n) * r) for i in range(n)]
        cor = acc if k % 2 else main
        _poli(p, pts, _rgba(cor, 110 + 120 * amp), _rgba(cor, 14 + 20 * amp), 1.6)
    _nucleo(p, cx, cy, R * 0.12, main, acc, amp)


# 3 ─ Gotas
def gotas(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Gotas que pingam no centro e abrem ondulações."""
    f = cv._fase * _calmo(cv)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for k in range(5):
        t = (f * 0.35 + k / 5) % 1.0
        r = R * (0.1 + 0.95 * t) * (1 + 0.1 * amp)
        for j, esc in enumerate((1.0, 0.72)):
            p.setPen(QPen(_rgba(acc if j else main, (1 - t) * (170 + 80 * amp)), 2.0 - j * 0.6))
            p.drawEllipse(QPointF(cx, cy), r * esc, r * esc * 0.62)
    _pt(p, cx, cy - R * (0.9 - 0.8 * ((f * 0.35) % 1.0)), 4 + 3 * amp, _rgba(main, 230))
    _glow(p, cx, cy, R * 0.25, acc, 100 + 100 * amp)


# 4 ─ Saturno
def saturno(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Planeta com anéis inclinados e luas em órbita."""
    f = cv._fase * _calmo(cv)
    r = R * (0.36 + 0.05 * amp)
    _glow(p, cx, cy, r * 2.2, main, 70 + 80 * amp)
    p.save()
    p.translate(cx, cy)
    p.rotate(-22)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for k, (m, a) in enumerate(((1.7, 130), (1.95, 100), (2.2, 70))):
        p.setPen(QPen(_rgba(acc if k != 1 else main, a + 90 * amp), 3.2 - k * 0.7))
        p.drawEllipse(QPointF(0, 0), r * m * 1.15, r * m * 0.3)
    p.restore()
    g = QRadialGradient(cx - r * 0.35, cy - r * 0.35, r * 1.5)
    g.setColorAt(0, _rgba(main, 255)); g.setColorAt(1, _rgba(C.BG if isinstance(C.BG, QColor) else QColor(C.BG), 255))
    p.setPen(QPen(_rgba(acc, 200), 1.6)); p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(cx, cy), r, r)
    for k in range(2):
        a = f * (0.9 + 0.5 * k) + k * 2.4
        _pt(p, cx + math.cos(a) * R * (0.8 + 0.12 * k), cy + math.sin(a) * R * (0.3 + 0.08 * k), 4 - k, _rgba(QColor(_BRANCO), 220))


# 5 ─ Vaga-lumes
def vagalumes(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Pontos de luz à deriva que piscam no ritmo da voz."""
    pts = _est(cv, "vl", lambda: [(r.uniform(0, TAU), r.uniform(0.15, 1.0), r.uniform(0, TAU), r.uniform(0.3, 1.2))
                                  for r in (random.Random(5),) for _ in range(46)])
    f = cv._fase * _calmo(cv)
    for i, (a0, d, ph, v) in enumerate(pts):
        a = a0 + f * 0.25 * v
        x = cx + math.cos(a + math.sin(f * 0.7 + ph) * 0.4) * R * d * 1.25
        y = cy + math.sin(a * 1.3 + ph) * R * d * 0.9
        br = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(f * 2 * v + ph)) * (0.6 + 0.8 * amp)
        _glow(p, x, y, 7 + 9 * br, acc if i % 3 else main, 70 + 150 * br)
        _pt(p, x, y, 1.6, _rgba(QColor(_BRANCO), 120 + 120 * br))
    _nucleo(p, cx, cy, R * 0.1, main, acc, amp)


# 6 ─ Cometas
def cometas(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Cometas cruzando em órbitas elípticas com cauda."""
    f = cv._fase * _calmo(cv)
    _nucleo(p, cx, cy, R * 0.13, main, acc, amp)
    for k in range(5):
        rot = k * 0.63 + 0.2
        a, b = R * (0.85 + 0.12 * k % 0.3), R * (0.3 + 0.1 * k)
        for s in range(14):
            t = f * (0.9 - 0.1 * k) - s * 0.07
            x, y = math.cos(t) * a, math.sin(t) * b
            X = cx + x * math.cos(rot) - y * math.sin(rot)
            Y = cy + x * math.sin(rot) + y * math.cos(rot)
            _pt(p, X, Y, (3.4 + 2 * amp) * (1 - s / 14), _rgba(acc if k % 2 else main, 230 * (1 - s / 14)))


# 7 ─ Arcos
def arcos(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Anéis de arco que giram em velocidades diferentes (estilo painel)."""
    f = cv._fase * _calmo(cv)
    for k in range(6):
        r = R * (0.95 - 0.13 * k)
        ini = math.degrees(f * (0.7 + 0.25 * k)) * (1 if k % 2 else -1) + k * 40
        cor = acc if k % 2 else main
        _arco(p, cx, cy, r, ini, ini + 70 + 150 * ((k * 37) % 5) / 5 + 40 * amp, _rgba(cor, 190), 4 - k * 0.4 + amp * 2)
        _arco(p, cx, cy, r, ini + 200, ini + 215, _rgba(QColor(_BRANCO), 150), 2)
    _nucleo(p, cx, cy, R * 0.1, main, acc, amp)


# 8 ─ Fogos
def fogos(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Explosões de faíscas que se abrem e apagam."""
    f = cv._fase * _calmo(cv)
    for k in range(3):
        t = (f * 0.28 + k / 3) % 1.0
        ox = cx + math.cos(k * 2.4 + 1) * R * 0.5
        oy = cy + math.sin(k * 3.1) * R * 0.35
        raio = R * (0.15 + 0.7 * t) * (1 + 0.3 * amp)
        for i in range(22):
            a = i * TAU / 22 + k
            x, y = ox + math.cos(a) * raio, oy + math.sin(a) * raio + R * 0.25 * t * t
            _pt(p, x, y, 2.6 * (1 - t) + 0.6, _rgba(QColor.fromHsvF((k * 0.3 + i / 60) % 1, 0.6, 1.0), 255 * (1 - t)))
        _glow(p, ox, oy, raio * 0.5, main if k % 2 else acc, 80 * (1 - t))
    _nucleo(p, cx, cy, R * 0.08, main, acc, amp)


# 9 ─ Rosa
def rosa(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Curva rosa (pétalas) que desabrocha com a voz."""
    f = cv._fase * _calmo(cv)
    for camada, (n, esc) in enumerate(((5, 1.0), (7, 0.7), (3, 0.45))):
        pts = []
        for i in range(181):
            t = i * TAU / 180
            r = R * esc * (0.55 + 0.4 * amp) * math.cos(n * t / 2 + f * 0.4 * (camada + 1))
            pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
        cor = (main, acc, main)[camada]
        p.setPen(QPen(_rgba(cor, 190), 1.8)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in pts]))
    _nucleo(p, cx, cy, R * 0.08, main, acc, amp)


# 10 ─ Synthwave
def synthwave(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Sol retrô sobre grade em perspectiva que corre para você."""
    f = cv._fase * _calmo(cv)
    hor = cy + R * 0.1
    _glow(p, cx, hor - R * 0.35, R * (0.8 + 0.2 * amp), acc, 110)
    p.setPen(Qt.PenStyle.NoPen)
    r = R * (0.5 + 0.06 * amp)
    for i in range(8):
        y0 = hor - r + i * r * 0.25
        p.setBrush(_rgba(main if i % 2 else acc, 210))
        p.drawRect(QRectF(cx - r * math.sqrt(max(0, 1 - ((y0 + 2 - (hor - r)) / r - 1) ** 2)),
                          y0, 2 * r * math.sqrt(max(0, 1 - ((y0 + 2 - (hor - r)) / r - 1) ** 2)), r * 0.1))
    _linha(p, cx - R * 1.4, hor, cx + R * 1.4, hor, _rgba(acc, 220), 2)
    for i in range(-8, 9):
        _linha(p, cx + i * R * 0.12, hor, cx + i * R * 0.5, hor + R * 0.9, _rgba(main, 120), 1.2)
    for i in range(7):
        t = ((i + f * 0.6) % 7) / 7
        y = hor + (R * 0.9) * t * t
        _linha(p, cx - R * 1.4 * t - R * 0.3, y, cx + R * 1.4 * t + R * 0.3, y, _rgba(acc, 80 + 120 * t), 1.2)


# 11 ─ Galáxia
def galaxia(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Braços espirais de estrelas girando em torno do núcleo."""
    f = cv._fase * _calmo(cv)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    for braco in range(3):
        for i in range(48):
            t = i / 47
            a = braco * TAU / 3 + t * 5.0 + f * 0.35
            r = R * t * 1.05 * (1 + 0.1 * amp)
            _pt(p, cx + math.cos(a) * r, cy + math.sin(a) * r * 0.6, 1.2 + 2.2 * (1 - t),
                _rgba(acc if i % 2 else main, 90 + 160 * (1 - t)))
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    _nucleo(p, cx, cy, R * (0.14 + 0.08 * amp), main, acc, amp)


# 12 ─ Cidade
def cidade(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Skyline com prédios que acendem janelas e sobem com a voz."""
    pred = _est(cv, "cid", lambda: [(r.uniform(0.25, 0.95), r.randint(2, 5), r.random())
                                    for r in (random.Random(9),) for _ in range(15)])
    f = cv._fase * _calmo(cv)
    base = cy + R * 0.7
    larg = R * 2.3 / len(pred)
    for i, (alt, jan, ph) in enumerate(pred):
        h = R * alt * (0.8 + 0.5 * cv._hv(i / len(pred)) + 0.2 * amp)
        x = cx - R * 1.15 + i * larg
        p.setPen(QPen(_rgba(main, 170), 1.2)); p.setBrush(_rgba(main, 28))
        p.drawRect(QRectF(x, base - h, larg * 0.82, h))
        for j in range(int(h / 16)):
            if math.sin(f * 0.8 + j * 3.1 + ph * 9) > 0.1:
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(_rgba(acc, 200))
                p.drawRect(QRectF(x + 4, base - h + 6 + j * 16, larg * 0.82 - 8, 5))
    _linha(p, cx - R * 1.2, base, cx + R * 1.2, base, _rgba(acc, 200), 2)


# 13 ─ Engrenagens
def engrenagens(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Três engrenagens encaixadas, girando em sentidos opostos."""
    f = cv._fase * _calmo(cv)

    def roda(x, y, r, dentes, rot, cor):
        pts = []
        for i in range(dentes * 2):
            a = rot + i * math.pi / dentes
            rr = r * (1.0 if i % 2 == 0 else 0.8)
            pts += [(x + math.cos(a - 0.02) * rr, y + math.sin(a - 0.02) * rr),
                    (x + math.cos(a + math.pi / dentes - 0.02) * rr, y + math.sin(a + math.pi / dentes - 0.02) * rr)]
        _poli(p, pts, _rgba(cor, 200), _rgba(cor, 22 + 25 * amp), 1.6)
        p.setPen(QPen(_rgba(cor, 160), 1.4)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(x, y), r * 0.25, r * 0.25)

    roda(cx, cy, R * 0.5, 12, f * 0.6, main)
    roda(cx + R * 0.82, cy - R * 0.05, R * 0.34, 8, -f * 0.9 + 0.2, acc)
    roda(cx - R * 0.74, cy + R * 0.2, R * 0.27, 6, -f * 1.15 + 0.5, acc)


# 14 ─ Cordas
def cordas(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Cordas de violão que vibram com a voz."""
    f = cv._fase * _calmo(cv)
    for k in range(7):
        y0 = cy + (k - 3) * R * 0.2
        pts = []
        for i in range(61):
            u = i / 60
            env = math.sin(u * math.pi)
            v = cv._hv(abs(u - 0.5) * 2) * 0.8 + amp * 0.5
            pts.append((cx - R * 1.15 + u * R * 2.3,
                        y0 + math.sin(u * 9 + f * (2 + k * 0.4)) * env * R * (0.03 + 0.2 * v)))
        p.setPen(QPen(_rgba(acc if k % 2 else main, 150 + 90 * amp), 1.6 + 0.2 * (3 - abs(k - 3))))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in pts]))


# 15 ─ Árvore
def arvore(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Árvore fractal que balança e brilha com a voz."""
    f = cv._fase * _calmo(cv)

    def galho(x, y, ang, comp, nivel):
        if nivel == 0 or comp < 3:
            _glow(p, x, y, 8 + 8 * amp, acc, 140)
            return
        x2, y2 = x + math.cos(ang) * comp, y + math.sin(ang) * comp
        _linha(p, x, y, x2, y2, _rgba(main if nivel % 2 else acc, 80 + nivel * 22), 0.8 + nivel * 0.5)
        bal = math.sin(f * 0.9 + nivel) * 0.07 + 0.38 + 0.18 * amp
        galho(x2, y2, ang - bal, comp * 0.74, nivel - 1)
        galho(x2, y2, ang + bal, comp * 0.74, nivel - 1)

    galho(cx, cy + R * 0.95, -1.5708, R * 0.42, 7)


# 16 ─ Caleidoscópio
def caleidoscopio(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Simetria de 8 lados com formas que giram e mudam de cor."""
    f = cv._fase * _calmo(cv)
    for lado in range(8):
        p.save(); p.translate(cx, cy); p.rotate(lado * 45)
        for k in range(4):
            d = R * (0.2 + 0.18 * k) * (1 + 0.25 * amp)
            a = f * (0.5 + 0.2 * k)
            cor = QColor.fromHsvF((lado / 8 + k * 0.1 + f * 0.03) % 1, 0.55, 1.0)
            _poli(p, [(d, 0), (d + R * 0.15 * math.cos(a), R * 0.15 * math.sin(a) + R * 0.1),
                      (d + R * 0.28, R * 0.02)], _rgba(cor, 220), _rgba(cor, 40 + 50 * amp), 1.4)
        p.restore()
    _nucleo(p, cx, cy, R * 0.09, main, acc, amp)


# 17 ─ Buraco negro
def buraco_negro(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Disco de acreção em espiral engolindo luz."""
    f = cv._fase * _calmo(cv)
    for k in range(36):
        t = k / 36
        for lado in (0, 3.14159):
            a = f * (1.2 - t) + t * 6.5 + lado
            r = R * (0.25 + 0.8 * t) * (1 + 0.1 * amp)
            _pt(p, cx + math.cos(a) * r, cy + math.sin(a) * r * 0.42, 2.8 * (1 - t) + 0.8,
                _rgba(QColor.fromHsvF(0.08 + 0.1 * t, 0.7, 1.0) if k % 2 else acc, 255 * (1 - t * 0.7)))
    _glow(p, cx, cy, R * 0.5, main, 90 + 90 * amp)
    p.setPen(QPen(_rgba(QColor(_BRANCO), 200), 2)); p.setBrush(QColor("#000000"))
    p.drawEllipse(QPointF(cx, cy), R * 0.22, R * 0.22)


# 18 ─ Escudo
def escudo(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Escudo de energia: favo que acende em ondas ao falar."""
    f = cv._fase * _calmo(cv)
    r = R * (0.9 + 0.05 * amp)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(_rgba(acc, 200), 2.4)); p.drawEllipse(QPointF(cx, cy), r, r)
    for q in range(-4, 5):
        for s in range(-4, 5):
            x = cx + (s + 0.5 * (q % 2)) * R * 0.27
            y = cy + q * R * 0.234
            d = math.hypot(x - cx, y - cy)
            if d > r * 0.93:
                continue
            onda = 0.5 + 0.5 * math.sin(d * 0.045 - f * 2.4)
            pts = [(x + math.cos(i * TAU / 6 + 0.5236) * R * 0.14, y + math.sin(i * TAU / 6 + 0.5236) * R * 0.14)
                   for i in range(6)]
            _poli(p, pts, _rgba(main, 70 + 120 * onda), _rgba(acc, 10 + (50 + 90 * amp) * onda), 1.1)


# 19 ─ Lótus
def lotus(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Pétalas em camadas que abrem e fecham respirando."""
    f = cv._fase * _calmo(cv)
    abre = 0.55 + 0.25 * math.sin(f * 0.6) + 0.3 * amp
    for camada in range(3):
        n = 8 + camada * 2
        for i in range(n):
            a = i * TAU / n + camada * 0.2
            comp = R * (0.95 - 0.25 * camada) * abre
            larg = R * (0.2 - 0.03 * camada)
            ux, uy = math.cos(a), math.sin(a)
            vx, vy = -uy, ux
            pts = [(cx + ux * R * 0.12, cy + uy * R * 0.12),
                   (cx + ux * comp * 0.5 + vx * larg, cy + uy * comp * 0.5 + vy * larg),
                   (cx + ux * comp, cy + uy * comp),
                   (cx + ux * comp * 0.5 - vx * larg, cy + uy * comp * 0.5 - vy * larg)]
            cor = main if camada % 2 == 0 else acc
            _poli(p, pts, _rgba(cor, 200), _rgba(cor, 20 + 25 * amp), 1.4)
    _nucleo(p, cx, cy, R * 0.1, main, acc, amp)


# 20 ─ Tempestade
def tempestade(cv, p, W, H, cx, cy, R, main, acc, amp):
    """Nuvem de energia com relâmpagos que disparam com a voz."""
    f = cv._fase * _calmo(cv)
    for k in range(6):
        a = f * 0.3 + k * 1.05
        _glow(p, cx + math.cos(a) * R * 0.45, cy - R * 0.25 + math.sin(a * 1.3) * R * 0.15, R * 0.6, main, 60 + 60 * amp)
    rnd = random.Random(int(cv._tick // 4) * 7919 + 13)
    for _ in range(2 + int(amp * 3)):
        x, y = cx + rnd.uniform(-R * 0.6, R * 0.6), cy - R * 0.45
        pts = [(x, y)]
        for _ in range(7):
            x += rnd.uniform(-R * 0.12, R * 0.12); y += R * 0.17
            pts.append((x, y))
        p.setPen(QPen(_rgba(QColor(_BRANCO), 120 + 130 * amp), 2.0 + amp * 1.5)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolyline(QPolygonF([QPointF(a, b) for a, b in pts]))
        _glow(p, pts[-1][0], pts[-1][1], R * 0.18, acc, 120 * (0.4 + amp))
    for i in range(24):
        x = cx + ((i * 53 + f * 120) % (R * 2.2)) - R * 1.1
        y = cy + R * 0.2 + ((i * 37 + f * 260) % (R * 0.9))
        _linha(p, x, y, x - 4, y + 12, _rgba(acc, 90), 1.0)


# ── registro ─────────────────────────────────────────────────────────────────
# chave: (ícone, nome, descrição curta, função de desenho)
NOVOS_STYLES: dict = {
    "prism":     ("◭", "Prisma", "Triângulo de vidro que abre um leque de cores", prisma),
    "origami":   ("❖", "Origami", "Polígonos concêntricos dobrando uns sobre os outros", origami),
    "drops":     ("💧", "Gotas", "Gotas que pingam e abrem ondulações", gotas),
    "saturn":    ("🪐", "Saturno", "Planeta com anéis inclinados e luas", saturno),
    "fireflies": ("✺", "Vaga-lumes", "Luzes à deriva que piscam com a voz", vagalumes),
    "comets":    ("☄", "Cometas", "Cometas com cauda em órbitas elípticas", cometas),
    "arcs":      ("◠", "Arcos", "Anéis de arco girando em velocidades diferentes", arcos),
    "fireworks": ("🎆", "Fogos", "Explosões de faíscas coloridas", fogos),
    "rose":      ("✿", "Rosa", "Curva rosa que desabrocha com a voz", rosa),
    "synthwave": ("🌇", "Synthwave", "Sol retrô sobre grade em perspectiva", synthwave),
    "galaxy":    ("🌌", "Galáxia", "Braços espirais de estrelas", galaxia),
    "city":      ("🏙", "Cidade", "Skyline que acende janelas com a voz", cidade),
    "gears":     ("⚙", "Engrenagens", "Três engrenagens encaixadas girando", engrenagens),
    "strings":   ("🎸", "Cordas", "Cordas que vibram com a voz", cordas),
    "tree":      ("🌳", "Árvore", "Árvore fractal que balança e brilha", arvore),
    "kaleido":   ("❂", "Caleidoscópio", "Simetria de 8 lados em cores que mudam", caleidoscopio),
    "blackhole": ("●", "Buraco negro", "Disco de acreção engolindo luz", buraco_negro),
    "shield":    ("⛨", "Escudo", "Escudo de energia em favo com ondas", escudo),
    "lotus":     ("❀", "Lótus", "Pétalas em camadas que respiram", lotus),
    "storm":     ("⛈", "Tempestade", "Nuvem de energia com relâmpagos", tempestade),
}

# 4.1 — cinco rostos (ui/hud_rostos.py) entram no mesmo registro
from .hud_rostos import ROSTOS_INFO, ROSTOS_STYLES  # noqa: E402

NOVOS_ORIGINAIS = tuple(NOVOS_STYLES)                    # os vinte da 3.6
NOVOS_STYLES.update(ROSTOS_STYLES)
NOVOS_INFO = {k: v[:3] for k, v in NOVOS_STYLES.items()}
