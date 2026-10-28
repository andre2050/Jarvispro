"""Ajudantes de desenho dos visuais do hub (QPainter)."""
from __future__ import annotations

from ._qt import *  # noqa: F401,F403


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
