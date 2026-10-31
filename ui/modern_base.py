"""Funções de apoio das peças visuais (fonte e cores em degradê).

Parte de ui/modern.py (dividido na 4.6.0 — sem mudança de comportamento)."""
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
