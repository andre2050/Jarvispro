"""Desempenho do PC sob demanda (os avisos proativos chegam sozinhos). Ver core/desempenho_proativo.py."""
from core import estatisticas_pc as E


def desempenho(parameters: dict, **_kw) -> str:
    try:
        return E.texto(E.coletar())
    except Exception as e:
        return f"[failed] {str(e)[:100]}"


TOOL = {
    "name": "performance_now",
    "description": "Snapshot of PC usage and optimization tips (CPU, memory, disks, heaviest programs). Proactive warnings arrive on their own; this is the on-demand version.",
    "parameters": {"type": "OBJECT", "properties": {}},
    "handler": desempenho,
}
