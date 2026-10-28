"""Imunidade a falhas conhecidas. Ver core/imunidade.py."""
from core import imunidade as I


def imunidade(parameters: dict, **_kw) -> str:
    acao = str(parameters.get("action") or "report").strip().lower()
    if acao in ("forget", "esquecer"):
        I.esquecer()
        return "[done] Esqueci todas as falhas e vacinas."
    return I.relatorio()


TOOL = {
    "name": "immunity",
    "description": "Known-failure immunity of the NEXUS core: report of recurring failures, working vaccines and bugs with no remedy (file:line). action=report (default) | forget. It never edits code.",
    "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING", "enum": ["report", "forget"]}}},
    "handler": imunidade,
}
