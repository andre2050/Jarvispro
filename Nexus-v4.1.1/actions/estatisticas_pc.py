"""Estatísticas completas do PC e sugestões. Ver core/estatisticas_pc.py."""
from core import estatisticas_pc as E


def estatisticas_pc(parameters: dict, psu=None, **_kw) -> str:
    try:
        return E.texto(E.coletar(psu=psu))
    except Exception as e:
        return f"[failed] Não consegui ler o PC: {str(e)[:100]}"


TOOL = {
    "name": "pc_stats",
    "description": "Detailed PC usage (CPU per core, memory, swap, disks, heaviest processes, uptime, battery, temperature) plus rule-based optimization tips. Read-only.",
    "parameters": {"type": "OBJECT", "properties": {}},
    "handler": estatisticas_pc,
}
