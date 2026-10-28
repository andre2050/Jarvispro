"""NEXUS Ultra 2026 · 4.1 — rosto realista para o hub (HUD).

Mesma assinatura dos outros visuais:  f(cv, p, W, H, cx, cy, R, main, acc, amp).
"Rosto · Real": um rosto humano de frente, desenhado por código (QPainter, sem foto de ninguém), com pele sombreada, olhos azuis com íris
detalhada, sobrancelhas, nariz, lábios e uma GRADE DIGITAL sobre a pele, com colunas de dados caindo nas laterais.
  • a voz (`amp`) abre os lábios e acende os olhos; os olhos piscam sozinhos e acompanham um olhar que passeia; mudo = olhos semicerrados.
  • REALISMO DE VERDADE = foto. Salve uma imagem SUA (ou com licença) em  config/rosto_hub.png  — ela cobre o hub e o NEXUS põe por cima só a vida:
    varredura, olhos que acendem com a voz e dados caindo. Se os olhos da foto ficarem fora do lugar, ajuste config/rosto_hub.json
    ({"olhos": [[0.33, 0.38], [0.67, 0.38]]}, frações do quadrado central). Nada sai do PC. Sem foto, usa o rosto desenhado por código (mais simples).
"""
from __future__ import annotations

import math
import random
from pathlib import Path

from ._qt import *  # noqa: F401,F403
from ._base import C, qcol  # noqa: F401
from .hud_util import _calmo, _est, _glow, _rgba

FOTO = Path(__file__).resolve().parent.parent / "config" / "rosto_hub.png"


def _piscada(cv) -> float:
    """1.0 olho aberto … 0.0 fechado. Pisca a cada ~4,3 s; mudo mantém semicerrado (0.35)."""
    if getattr(cv, "muted", False):
        return 0.35
    t = (cv._fase * 0.9) % 4.3
    return max(0.0, abs(t - 4.15) / 0.15) if 4.0 < t < 4.3 else 1.0


def _olhar(cv, R: float) -> tuple[float, float]:
    f = cv._fase * 0.35 * _calmo(cv)
    return math.sin(f * 1.3) * R * 0.03, math.sin(f * 0.8 + 1.0) * R * 0.015


def _boca_aberta(amp: float) -> float:
    return max(0.0, min(1.0, amp * 1.6))


def _suave(pts, fechar=True) -> QPainterPath:
    """Curva suave (Catmull-Rom → Bézier) passando por todos os pontos."""
    n = len(pts)
    path = QPainterPath(QPointF(*pts[0]))
    for i in range(n if fechar else n - 1):
        p0, p1, p2, p3 = pts[(i - 1) % n], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        if not fechar:
            p0 = pts[max(i - 1, 0)]
            p3 = pts[min(i + 2, n - 1)]
        path.cubicTo(QPointF(p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6),
                     QPointF(p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6), QPointF(*p2))
    return path


# contorno do rosto (x em -1..1 da metade da largura, y em -1..1 da metade da altura)
_ROSTO = [(0.0, -1.0), (0.46, -0.95), (0.74, -0.66), (0.80, -0.20), (0.76, 0.18), (0.62, 0.55), (0.34, 0.86), (0.0, 0.96),
          (-0.34, 0.86), (-0.62, 0.55), (-0.76, 0.18), (-0.80, -0.20), (-0.74, -0.66), (-0.46, -0.95)]


def _fundo(cv, p, W, H, cx, cy, R, main, acc, amp, solido=True):
    """Fundo escuro com colunas de dados caindo, em perspectiva leve."""
    g = QLinearGradient(0, cy - R, 0, cy + R)
    g.setColorAt(0, QColor(6, 14, 30))
    g.setColorAt(1, QColor(10, 28, 52))
    if solido:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawRect(QRectF(cx - R * 1.15, cy - R * 1.15, R * 2.3, R * 2.3))
    rnd = _est(cv, "face_cols", lambda: [(random.Random(i).random(), random.Random(i + 99).random(), random.Random(i + 7).random()) for i in range(150)])
    calmo = _calmo(cv)
    if solido:
        p.setPen(QPen(QColor(120, 170, 220, 26), max(0.8, R * 0.003)))                      # grade tênue ao fundo
        for k in range(-12, 13):
            p.drawLine(QPointF(cx + k * R * 0.1, cy - R * 1.15), QPointF(cx + k * R * 0.1, cy + R * 1.15))
        for k in range(-12, 13):
            p.drawLine(QPointF(cx - R * 1.15, cy + k * R * 0.1), QPointF(cx + R * 1.15, cy + k * R * 0.1))
    for i, (a, b, c) in enumerate(rnd):
        lado = -1 if i % 2 == 0 else 1
        x = cx + lado * R * (0.78 + 0.45 * a)
        prox = 1.0 - a                                                                      # perto do rosto: mais longo e mais brilhante
        for k in range(8):
            y = cy - R * 1.2 + ((b * 2.4 + k * 0.3 + cv._fase * 0.035 * (0.5 + c) * calmo) % 2.4) * R
            amarelo = (i * 7 + k * 3) % 13 == 0
            cor = QColor(255, 206, 80) if amarelo else QColor(176, 220, 255)
            al = (110 + 120 * ((k % 3) / 2)) * (0.35 + 0.65 * prox)
            p.setPen(QPen(_rgba(cor, al), max(1.0, R * (0.008 + 0.01 * prox))))
            p.drawLine(QPointF(x, y), QPointF(x, y + R * (0.012 + 0.05 * c * (0.4 + prox))))


def _pele(p, cx, cy, R, rost, amp):
    """Pele sombreada: tom frio no centro claro, sombras nas laterais, mais as sombras do relevo."""
    pa = _suave([(cx + x * R * 0.76, cy + y * R * 0.9) for x, y in _ROSTO])
    # cabelo atrás
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(14, 18, 28))
    cab = _suave([(cx + x * R * 0.82, cy + y * R * 0.93 - R * 0.03) for x, y in _ROSTO])
    p.drawPath(cab)
    # pescoço
    pesc = QPainterPath()
    pesc.addRoundedRect(QRectF(cx - R * 0.26, cy + R * 0.62, R * 0.52, R * 0.5), R * 0.06, R * 0.06)
    gp = QLinearGradient(cx - R * 0.26, 0, cx + R * 0.26, 0)
    gp.setColorAt(0, QColor(88, 104, 126))
    gp.setColorAt(0.5, QColor(150, 168, 186))
    gp.setColorAt(1, QColor(78, 94, 116))
    p.setBrush(QBrush(gp))
    p.drawPath(pesc)
    g = QLinearGradient(cx - R * 0.5, 0, cx + R * 0.5, 0)
    g.setColorAt(0.0, QColor(96, 114, 136))
    g.setColorAt(0.18, QColor(150, 168, 186))
    g.setColorAt(0.5, QColor(196, 208, 218))
    g.setColorAt(0.82, QColor(150, 168, 186))
    g.setColorAt(1.0, QColor(92, 108, 130))
    p.setBrush(QBrush(g))
    p.drawPath(pa)
    return pa


def _relevo(p, cx, cy, R):
    """Sombras e luzes que dão volume: órbitas, nariz, maçãs, queixo."""
    for sx in (-1, 1):
        _glow(p, cx + sx * R * 0.3, cy - R * 0.12, R * 0.24, QColor(40, 62, 96), 110)       # órbitas
        _glow(p, cx + sx * R * 0.4, cy + R * 0.2, R * 0.24, QColor(236, 244, 250), 70)     # maçãs claras
        _glow(p, cx + sx * R * 0.52, cy + R * 0.3, R * 0.2, QColor(50, 70, 100), 80)         # sombra da bochecha
        _glow(p, cx + sx * R * 0.095, cy + R * 0.14, R * 0.09, QColor(60, 80, 108), 140)     # lado do nariz
    _glow(p, cx, cy - R * 0.02, R * 0.12, QColor(246, 250, 255), 90)                         # dorso do nariz
    _glow(p, cx, cy + R * 0.84, R * 0.3, QColor(60, 80, 108), 110)                           # sob o queixo


def _olho(cv, p, cx, cy, R, sx, amp, gx, gy, piscar):
    ex, ey = cx + sx * R * 0.3, cy - R * 0.12
    w, h = R * 0.215, R * 0.078 * (0.1 + 0.9 * piscar)
    # sombra da pálpebra superior
    _glow(p, ex, ey - R * 0.06, R * 0.2, QColor(30, 44, 70), 110)
    olho = _suave([(ex - w, ey + h * 0.15), (ex - w * 0.5, ey - h * 1.15), (ex + w * 0.1, ey - h * 1.25), (ex + w * 0.7, ey - h * 0.75), (ex + w, ey + h * 0.1),
                   (ex + w * 0.55, ey + h * 0.85), (ex - w * 0.1, ey + h * 1.0), (ex - w * 0.6, ey + h * 0.7)])
    p.save()
    p.setClipPath(olho)
    p.fillRect(QRectF(ex - w * 1.1, ey - h * 2, w * 2.2, h * 4), QColor(232, 238, 244))       # esclera
    ir = R * 0.074
    ix, iy = ex + gx * 0.7, ey + gy * 0.7
    g = QRadialGradient(ix, iy, ir)
    g.setColorAt(0.0, QColor(14, 70, 130))
    g.setColorAt(0.45, QColor(44, 150, 224))
    g.setColorAt(0.85, QColor(80, 196, 255))
    g.setColorAt(1.0, QColor(12, 50, 96))
    p.setBrush(QBrush(g))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QPointF(ix, iy), ir, ir)
    p.setPen(QPen(QColor(210, 244, 255, 110), max(0.6, R * 0.003)))                          # fibras da íris
    for k in range(28):
        a = k * math.tau / 28
        p.drawLine(QPointF(ix + math.cos(a) * ir * 0.38, iy + math.sin(a) * ir * 0.38), QPointF(ix + math.cos(a) * ir * 0.92, iy + math.sin(a) * ir * 0.92))
    pup = ir * (0.38 - 0.06 * amp)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(4, 8, 16))
    p.drawEllipse(QPointF(ix, iy), pup, pup)
    p.setBrush(QColor(255, 255, 255, 235))                                                    # reflexo
    p.drawEllipse(QPointF(ix - ir * 0.34, iy - ir * 0.36), ir * 0.2, ir * 0.2)
    p.setBrush(QColor(255, 255, 255, 110))
    p.drawEllipse(QPointF(ix + ir * 0.3, iy + ir * 0.34), ir * 0.1, ir * 0.1)
    sh = QLinearGradient(0, ey - h * 1.3, 0, ey - h * 0.1)                                    # sombra da pálpebra sobre o olho
    sh.setColorAt(0, QColor(10, 18, 34, 200))
    sh.setColorAt(1, QColor(10, 18, 34, 0))
    p.fillRect(QRectF(ex - w * 1.1, ey - h * 1.4, w * 2.2, h * 1.4), QBrush(sh))
    p.restore()
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(18, 26, 44, 230), max(1.2, R * 0.009), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))   # linha dos cílios
    top = _suave([(ex - w, ey + h * 0.15), (ex - w * 0.5, ey - h * 1.15), (ex + w * 0.1, ey - h * 1.25), (ex + w * 0.7, ey - h * 0.75), (ex + w, ey + h * 0.1)], False)
    p.drawPath(top)
    p.setPen(QPen(QColor(18, 26, 44, 150), max(0.8, R * 0.004)))
    for k in range(9):                                                                          # cílios
        t = k / 8
        px, py = ex - w * 0.9 + t * w * 1.85, ey - h * (0.5 + 0.7 * math.sin(t * math.pi)) + h * 0.1
        p.drawLine(QPointF(px, py), QPointF(px + sx * R * 0.012 + (t - 0.5) * R * 0.015, py - R * 0.02 * (0.5 + piscar * 0.5)))
    p.setPen(QPen(QColor(120, 140, 166, 120), max(0.8, R * 0.004)))                            # prega sob o olho
    p.drawArc(QRectF(ex - w * 0.9, ey + h * 0.5, w * 1.8, h * 1.6), 210 * 16, 120 * 16)
    # sobrancelha
    sob = _suave([(ex - w * 1.05, ey - R * 0.085), (ex - w * 0.2, ey - R * 0.125), (ex + w * 0.7, ey - R * 0.125), (ex + w * 1.15, ey - R * 0.085 + sx * 0)], False)
    p.setPen(QPen(QColor(24, 28, 40, 215), R * 0.017, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawPath(sob)


def _nariz(p, cx, cy, R):
    p.setPen(Qt.PenStyle.NoPen)
    for sx in (-1, 1):
        p.setBrush(QColor(30, 44, 70, 190))
        p.drawEllipse(QPointF(cx + sx * R * 0.062, cy + R * 0.205), R * 0.027, R * 0.015)    # narinas
        _glow(p, cx + sx * R * 0.085, cy + R * 0.185, R * 0.06, QColor(50, 70, 100), 120)    # asas
    p.setPen(QPen(QColor(70, 92, 124, 120), max(1.0, R * 0.006), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawArc(QRectF(cx - R * 0.095, cy + R * 0.15, R * 0.19, R * 0.075), 200 * 16, 140 * 16)
    _glow(p, cx, cy + R * 0.155, R * 0.045, QColor(255, 255, 255), 130)                      # brilho da ponta


def _labios(p, cx, cy, R, amp, acc):
    ab = _boca_aberta(amp) * R * 0.045
    y = cy + R * 0.40
    w = R * 0.19
    sup = _suave([(cx - w, y), (cx - w * 0.45, y - R * 0.028), (cx - w * 0.12, y - R * 0.034), (cx, y - R * 0.022), (cx + w * 0.12, y - R * 0.034), (cx + w * 0.45, y - R * 0.028), (cx + w, y),
                  (cx, y - ab * 0.2)])
    inf = _suave([(cx - w, y), (cx - w * 0.5, y + R * 0.045 + ab), (cx, y + R * 0.058 + ab), (cx + w * 0.5, y + R * 0.045 + ab), (cx + w, y), (cx, y + ab * 0.2)])
    if ab > R * 0.004:                                                                          # interior da boca
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(40, 14, 24))
        p.drawEllipse(QPointF(cx, y + ab * 0.45), w * 0.8, ab * 0.8)
        p.setBrush(QColor(236, 240, 244, 220))
        p.drawRect(QRectF(cx - w * 0.5, y - ab * 0.12, w, ab * 0.35))
    for path, c1, c2 in ((sup, QColor(176, 118, 138), QColor(140, 88, 112)), (inf, QColor(206, 146, 164), QColor(168, 108, 130))):
        g = QLinearGradient(0, y - R * 0.04, 0, y + R * 0.07 + ab)
        g.setColorAt(0, c1)
        g.setColorAt(1, c2)
        p.setPen(QPen(QColor(110, 60, 82, 170), max(0.8, R * 0.004)))
        p.setBrush(QBrush(g))
        p.drawPath(path)
    _glow(p, cx, y + R * 0.032 + ab, R * 0.05, QColor(255, 240, 246), 110)                    # brilho do lábio inferior
    p.setPen(QPen(QColor(70, 30, 48, 210), max(1.0, R * 0.005), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(cx - w, y), QPointF(cx + w, y + ab * 0.1))


def _mosaico(R):
    """Quadradinhos de tamanhos e brilhos irregulares (coordenadas relativas a R), sempre os mesmos."""
    rnd = random.Random(2026)
    cel, y = [], -1.0
    while y < 1.0:
        x = -0.85
        h = rnd.choice((0.034, 0.04, 0.05))
        while x < 0.85:
            w = rnd.choice((0.03, 0.04, 0.06, 0.09))
            cel.append((x, y, w * 0.92, h * 0.9, rnd.random()))
            x += w
        y += h
    return cel


def _grade(cv, p, cx, cy, R, pa, main, amp):
    """Pele em mosaico digital (quadradinhos claros e escuros), grade fina, manchas de cobre e varredura — tudo recortado no rosto."""
    p.save()
    p.setClipPath(pa)
    p.setPen(Qt.PenStyle.NoPen)
    for x, y, w, h, t in _est(cv, "face_mosaico", lambda: _mosaico(1.0)):
        if t < 0.42:
            p.setBrush(QColor(206, 232, 252, int(30 + 60 * t)))
        elif t > 0.86:
            p.setBrush(QColor(18, 40, 76, int(40 + 80 * (t - 0.86) * 5)))
        else:
            continue
        p.drawRect(QRectF(cx + x * R, cy + y * R, w * R, h * R))
    passo = R * 0.045
    p.setPen(QPen(_rgba(QColor(190, 228, 255), 64), max(0.7, R * 0.003)))
    x0, k = cx - R * 0.9, 0
    while x0 + k * passo < cx + R * 0.9:
        p.drawLine(QPointF(x0 + k * passo, cy - R * 1.1), QPointF(x0 + k * passo, cy + R * 1.1))
        k += 1
    k = 0
    while cy - R * 1.1 + k * passo * 0.8 < cy + R * 1.1:
        y = cy - R * 1.1 + k * passo * 0.8
        p.drawLine(QPointF(cx - R * 0.9, y), QPointF(cx + R * 0.9, y))
        k += 1
    manchas = _est(cv, "face_manchas", lambda: [(random.Random(i).uniform(-0.62, 0.62), random.Random(i + 50).uniform(-1.0, 0.9), random.Random(i + 90).uniform(0.04, 0.13)) for i in range(34)])
    for mx, my, mr in manchas:                                                                   # cobre/ferrugem, em pequenos aglomerados irregulares
        r2 = random.Random(int(mx * 1000) + int(my * 777))
        for _ in range(4):
            _glow(p, cx + (mx + r2.uniform(-0.05, 0.05)) * R, cy + (my + r2.uniform(-0.05, 0.05)) * R, mr * R * r2.uniform(0.7, 1.3), QColor(206, 140, 84), 62)
    sy = cy - R + ((cv._fase * 0.22 * _calmo(cv)) % 1.0) * R * 2.0
    g = QLinearGradient(0, sy - R * 0.12, 0, sy + R * 0.02)
    g.setColorAt(0, _rgba(QColor(150, 220, 255), 0))
    g.setColorAt(1, _rgba(QColor(150, 220, 255), 40 + 50 * amp))
    p.fillRect(QRectF(cx - R * 1.2, sy - R * 0.12, R * 2.4, R * 0.14), QBrush(g))
    p.restore()


def _foto(cv):
    """A foto do usuário (config/rosto_hub.png), se existir. Carrega uma vez."""
    def criar():
        try:
            pm = QPixmap(str(FOTO))
            return None if pm.isNull() else pm
        except Exception:
            return None
    return _est(cv, "face_foto", criar)


# posições na foto, em fração do QUADRADO central: olhos, linha da boca (x, y, meia-largura). Ajuste em config/rosto_hub.json:
#   {"olhos": [[0.33, 0.38], [0.67, 0.38]], "boca": [0.5, 0.757, 0.13]}
_OLHOS_FOTO = ((0.33, 0.38), (0.67, 0.38))
_BOCA_FOTO = (0.5, 0.757, 0.13)


def _cfg_foto() -> tuple[tuple, tuple]:
    try:
        import json
        d = json.loads(FOTO.with_suffix(".json").read_text(encoding="utf-8"))
        o = tuple((float(a), float(b)) for a, b in d.get("olhos", _OLHOS_FOTO)[:2])
        b = tuple(float(x) for x in d.get("boca", _BOCA_FOTO)[:3])
        return (o if len(o) == 2 else _OLHOS_FOTO), (b if len(b) == 3 else _BOCA_FOTO)
    except Exception:
        return _OLHOS_FOTO, _BOCA_FOTO


def _olhos_foto():
    return _cfg_foto()[0]


def _pele_perto(cv, foto, fx, fy):
    """Cor da pele da foto no ponto (fração do quadrado central) — usada nas pálpebras que piscam."""
    img = _est(cv, "face_foto_img", foto.toImage)
    lado = min(img.width(), img.height())
    x = int((img.width() - lado) / 2 + fx * lado)
    y = int((img.height() - lado) / 2 + fy * lado)
    return img.pixelColor(max(0, min(img.width() - 1, x)), max(0, min(img.height() - 1, y)))


def _remendo(p, alvo, foto, fonte, mx, my, w, h, dx=0.0, dy=0.0, dentro=0.55):
    """Redesenha um pedaço elíptico da foto deslocado (dx, dy), com a borda esmaecendo — a deformação não deixa emenda."""
    dst = QRectF(mx - w / 2, my - h / 2, w, h)
    tmp = QPixmap(max(2, int(w) + 1), max(2, int(h) + 1))
    tmp.fill(Qt.GlobalColor.transparent)
    tp = QPainter(tmp)
    tp.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    tp.translate(-dst.x() + dx, -dst.y() + dy)
    tp.drawPixmap(alvo, foto, fonte)
    tp.resetTransform()
    tp.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    tp.translate(w / 2, h / 2)
    tp.scale(1.0, max(0.05, h / w))
    g = QRadialGradient(0, 0, w / 2)
    g.setColorAt(0.0, QColor(0, 0, 0, 255))
    g.setColorAt(dentro, QColor(0, 0, 0, 255))
    g.setColorAt(1.0, QColor(0, 0, 0, 0))
    tp.fillRect(QRectF(-w / 2, -w / 2, w, w), QBrush(g))
    tp.end()
    p.drawPixmap(dst.topLeft(), tmp)


def _animar_olhos(cv, p, alvo, foto, fonte, amp):
    """Olhos da foto: a íris desliza dentro do olho (mais e mais rápido quando você fala), as sobrancelhas sobem na ênfase e as pálpebras piscam."""
    W = alvo.width()
    eixo = _est(cv, "face_olhar", lambda: [0.0, 0.0])
    f = cv._fase * _calmo(cv)
    alvo_x = math.sin(f * 0.9) * 0.6 + math.sin(f * (2.3 + 3.0 * amp)) * (0.3 + 0.7 * amp)
    alvo_y = math.sin(f * 0.7 + 1.0) * 0.4 + math.sin(f * (1.9 + 2.5 * amp) + 2.0) * (0.2 + 0.5 * amp)
    eixo[0] += (alvo_x - eixo[0]) * 0.4
    eixo[1] += (alvo_y - eixo[1]) * 0.4
    dx, dy = eixo[0] * W * 0.0115, eixo[1] * W * 0.0075
    piscar = _piscada(cv)
    enfase = max(0.0, amp - 0.25) * (0.6 + 0.4 * math.sin(f * 4.0))                              # sobrancelhas sobem nas sílabas fortes
    for ox, oy in _olhos_foto():
        x, y = alvo.x() + ox * W, alvo.y() + oy * alvo.height()
        if enfase > 0.02:
            _remendo(p, alvo, foto, fonte, x, y - W * 0.062, W * 0.24, W * 0.05, 0, -enfase * W * 0.012, 0.5)
        _remendo(p, alvo, foto, fonte, x, y, W * 0.15, W * 0.046, dx, dy, 0.6)
        if piscar < 0.97:                                                                         # pálpebra: pele da própria foto descendo sobre o olho
            pele = _pele_perto(cv, foto, ox, oy - 0.075)
            alt = W * 0.026 * (1.0 - piscar)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(pele)
            p.drawEllipse(QPointF(x, y - W * 0.0095 + alt * 0.5), W * 0.085, alt * 0.95)
            p.setPen(QPen(pele.darker(190), max(1.0, W * 0.0016)))
            p.drawLine(QPointF(x - W * 0.07, y + alt * 0.45 - W * 0.0095), QPointF(x + W * 0.07, y + alt * 0.45 - W * 0.0095))


def _animar_boca(cv, p, alvo, foto, fonte, amp):
    """Boca da foto: o maxilar desce com a voz, o lábio de cima sobe um pouco, o interior aparece (dentes, língua) e a boca alarga/estreita como nas vogais."""
    bx, by, bw = _cfg_foto()[1]
    W = alvo.width()
    d = _boca_aberta(amp) * W * 0.046
    if d < 0.8:
        return
    f = cv._fase
    vogal = 0.86 + 0.14 * math.sin(f * 5.3) * min(1.0, amp * 2)                                  # "o" estreita, "a/e" alarga
    xm, y0, hw = alvo.x() + bx * W, alvo.y() + by * alvo.height(), bw * W
    w = hw * 0.8 * vogal
    _remendo(p, alvo, foto, fonte, xm, y0 - W * 0.022, hw * 2.2, W * 0.058, 0, -d * 0.3, 0.55)   # lábio de cima sobe
    interior = QPainterPath(QPointF(xm - w, y0 - d * 0.05))
    interior.quadTo(QPointF(xm, y0 - d * 0.25), QPointF(xm + w, y0 - d * 0.05))
    interior.quadTo(QPointF(xm, y0 + d * 1.7), QPointF(xm - w, y0 - d * 0.05))
    p.save()
    p.setClipPath(interior)
    g = QLinearGradient(0, y0, 0, y0 + d * 1.2)
    g.setColorAt(0, QColor(88, 34, 46))
    g.setColorAt(1, QColor(26, 8, 14))
    p.fillRect(QRectF(xm - hw, y0 - 3, hw * 2, d * 1.7 + 6), QBrush(g))
    if d > W * 0.012:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(176, 84, 98, 190))                                                      # língua
        p.drawEllipse(QPointF(xm, y0 + d * 0.95), w * 0.55, d * 0.34)
    p.fillRect(QRectF(xm - w * 0.72, y0 - 2, w * 1.44, max(1.0, d * 0.3)), QColor(226, 230, 234, 185))   # dentes de cima
    sombra = QLinearGradient(xm - w, 0, xm + w, 0)                                               # cantos da boca mais escuros
    sombra.setColorAt(0.0, QColor(0, 0, 0, 150))
    sombra.setColorAt(0.2, QColor(0, 0, 0, 0))
    sombra.setColorAt(0.8, QColor(0, 0, 0, 0))
    sombra.setColorAt(1.0, QColor(0, 0, 0, 150))
    p.fillRect(QRectF(xm - w, y0 - 3, w * 2, d * 1.7 + 6), QBrush(sombra))
    p.restore()
    # maxilar: lábio inferior + queixo descem juntos
    _remendo(p, alvo, foto, fonte, xm, y0 + d + W * 0.052, hw * 2.4, W * 0.12, 0, d, 0.62)


def _foto_pronta(cv, foto, alvo):
    """A foto já recortada (quadrado central) e escalada para o tamanho do hub, guardada: desenhar a cada quadro fica barato."""
    n = max(8, int(alvo.width()))
    cache = _est(cv, "face_foto_esc", lambda: [0, None])
    if cache[0] != n:
        lado = min(foto.width(), foto.height())
        base = foto.copy(int((foto.width() - lado) / 2), int((foto.height() - lado) / 2), lado, lado)
        cache[0], cache[1] = n, base.scaled(n, n, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    return cache[1]


def _rosto_foto(cv, p, W, H, cx, cy, R, amp, foto):
    """Modo foto: a imagem do usuário cobre o hub (recorte quadrado do centro). Por cima, vida: cabeça que balança e acena ao falar, olhos que se mexem,
    piscam e acendem, sobrancelhas, boca que abre (maxilar, lábios, dentes, língua), varredura e dados caindo."""
    alvo = QRectF(cx - R * 1.15, cy - R * 1.15, R * 2.3, R * 2.3)
    foto = _foto_pronta(cv, foto, alvo)
    fonte = QRectF(foto.rect())
    p.setClipRect(alvo)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    f = cv._fase * _calmo(cv)
    p.save()                                                                                     # cabeça: respiração, balanço e aceno com a voz
    p.translate(cx + math.sin(f * 0.6) * R * 0.004 * (1 + amp), cy + (math.sin(f * 0.9) * 0.004 + amp * 0.012 * math.sin(f * 6.0)) * R)
    p.rotate(math.sin(f * 0.5) * 0.35 + amp * math.sin(f * 3.1) * 0.7)
    p.scale(1.01 + 0.006 * math.sin(f * 0.8), 1.01 + 0.006 * math.sin(f * 0.8))
    p.translate(-cx, -cy)
    p.drawPixmap(alvo, foto, fonte)
    _animar_olhos(cv, p, alvo, foto, fonte, amp)
    _animar_boca(cv, p, alvo, foto, fonte, amp)
    for ox, oy in _olhos_foto():
        x, y = alvo.x() + ox * alvo.width(), alvo.y() + oy * alvo.height()
        _glow(p, x, y, R * (0.11 + 0.08 * amp), QColor(110, 205, 255), 22 + 110 * amp)
    p.restore()
    _fundo(cv, p, W, H, cx, cy, R, QColor("#18c8ff"), QColor("#7df9ff"), amp, solido=False)
    sy = alvo.y() + ((cv._fase * 0.18 * _calmo(cv)) % 1.0) * alvo.height()
    g = QLinearGradient(0, sy - R * 0.2, 0, sy + R * 0.02)
    g.setColorAt(0, _rgba(QColor(150, 220, 255), 0))
    g.setColorAt(1, _rgba(QColor(150, 220, 255), 40 + 40 * amp))
    p.fillRect(QRectF(alvo.x(), sy - R * 0.2, alvo.width(), R * 0.22), QBrush(g))
    if getattr(cv, "muted", False):                                                              # mudo: escurece de leve
        p.fillRect(alvo, QColor(0, 0, 0, 90))


def rosto_real(cv, p, W, H, cx, cy, R, main, acc, amp):
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    foto = _foto(cv)
    if foto is not None:
        _rosto_foto(cv, p, W, H, cx, cy, R, amp, foto)
        p.restore()
        return
    _fundo(cv, p, W, H, cx, cy, R, main, acc, amp)
    p.setClipRect(QRectF(cx - R * 1.2, cy - R * 1.2, R * 2.4, R * 2.4))
    S = 1.32                                                                                   # rosto de perto: testa e queixo saem do quadro
    p.translate(cx, cy + R * 0.1)
    p.scale(S, S)
    p.translate(-cx, -cy)
    gx, gy = _olhar(cv, R)
    piscar = _piscada(cv)
    pa = _pele(p, cx, cy, R, None, amp)
    _relevo(p, cx, cy, R)
    for sx in (-1, 1):
        _olho(cv, p, cx, cy, R, sx, amp, gx, gy, piscar)
    _nariz(p, cx, cy, R)
    _labios(p, cx, cy, R, amp, acc)
    _grade(cv, p, cx, cy, R, pa, main, amp)
    _glow(p, cx, cy - R * 0.12, R * 0.5, _rgba(QColor(120, 200, 255), 255), 16 + 40 * amp)       # a voz acende o olhar
    p.restore()


ROSTOS_STYLES: dict = {
    "face_real": ("🧑‍💻", "Rosto · Real", "Sua foto em config/rosto_hub.png com dados e brilho animados (sem foto: rosto desenhado)", rosto_real),
}
ROSTOS_INFO = {k: v[:3] for k, v in ROSTOS_STYLES.items()}
