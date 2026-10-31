"""Editor de visuais do hub (3.7): cor (matiz) e velocidade de cada visual, guardadas por visual.

{"nebula": {"matiz": 280, "velocidade": 1.4}, ...} em config/api_keys.json › hud_ajustes.
matiz: 0–359 (None = a cor do tema); velocidade: 0.3–2.5 (1.0 = normal).
"""
from __future__ import annotations

import colorsys

VEL_MIN, VEL_MAX = 0.3, 2.5


def _todos() -> dict:
    try:
        from memory.config_manager import load_api_keys
        d = load_api_keys().get("hud_ajustes", {})
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def normalizar(aj: dict | None) -> dict:
    aj = aj if isinstance(aj, dict) else {}
    out = {}
    try:
        m = aj.get("matiz")
        if m is not None:
            out["matiz"] = int(float(m)) % 360
    except (TypeError, ValueError):
        pass
    try:
        v = float(aj.get("velocidade", 1.0))
        if abs(v - 1.0) > 1e-6:
            out["velocidade"] = round(max(VEL_MIN, min(VEL_MAX, v)), 2)
    except (TypeError, ValueError):
        pass
    return out


def obter(estilo: str) -> dict:
    return normalizar(_todos().get(str(estilo)))


def salvar(estilo: str, matiz=None, velocidade=1.0) -> dict:
    """Grava (ou, sem nada diferente do padrão, apaga) os ajustes de um visual."""
    from memory.config_manager import _save_flag
    todos = {k: v for k, v in _todos().items() if isinstance(v, dict)}
    aj = normalizar({"matiz": matiz, "velocidade": velocidade})
    if aj:
        todos[str(estilo)] = aj
    else:
        todos.pop(str(estilo), None)
    _save_flag("hud_ajustes", todos)
    return aj


def restaurar(estilo: str) -> None:
    salvar(estilo, None, 1.0)


def cores_com_matiz(matiz: int, base_main: tuple[int, int, int]) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """(principal, destaque) RGB: mantém brilho e saturação da cor do tema, troca o matiz; o destaque gira +0,13."""
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in base_main))
    s = max(s, 0.45)                         # tema cinza não pode deixar a cor escolhida lavada
    def rgb(hh):
        return tuple(int(c * 255 + 0.5) for c in colorsys.hsv_to_rgb(hh % 1.0, s, v))
    mm = (matiz % 360) / 360
    return rgb(mm), rgb(mm + 0.13)
