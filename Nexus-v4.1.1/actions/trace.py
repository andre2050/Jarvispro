"""actions/trace.py — linha do tempo local do que o NEXUS executou (4.1)."""
from __future__ import annotations


def trace(parameters: dict, **_kw) -> str:
    from core import trace_local as T
    mid = str(parameters.get("mission") or "").strip().lower()
    try:
        minutos = float(parameters.get("minutes") or 60)
    except (TypeError, ValueError):
        minutos = 60
    return T.texto(mid, minutos)


TOOL = {
    "name": "trace",
    "description": ("LOCAL TRACE: timeline of what NEXUS executed — who (you, a mission, an agent), which tool, how long it took, where it failed — "
                    "stored only on this PC. Use for 'por que a missão demorou?', 'o que você fez na última hora?', 'qual ferramenta mais falha?'. "
                    "Optional mission id, or minutes (default 60). Answer in Portuguese."),
    "parameters": {"type": "OBJECT", "properties": {"mission": {"type": "STRING"}, "minutes": {"type": "NUMBER"}}},
    "handler": trace,
}
