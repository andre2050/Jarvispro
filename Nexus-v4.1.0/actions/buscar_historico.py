"""Busca no que você já fez, por voz (NEXUS Ultra 2026 3.3): relatórios, anotações e diário."""
from __future__ import annotations


def buscar_historico(parameters: dict, player=None) -> str:
    from core import busca_historico as B
    pedido = " ".join(str(parameters.get(k) or "") for k in ("query", "period")).strip()
    return B.responder(pedido)


TOOL = {
    "name": "buscar_historico",
    "description": ("Search what the user already did: agent reports, quick notes and diary entries (all local). "
                    "Use for 'o que eu anotei sobre X semana passada?', 'procura o relatório da pesquisa de Y', "
                    "'o que eu fiz ontem?'. query = the topic words; period = hoje, ontem, esta semana, semana "
                    "passada, este mês, mês passado, 'últimos 3 dias' (may also be inside query). Read-only. "
                    "Answer in Portuguese, briefly."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "words to look for (may be empty for 'o que fiz ontem')"},
            "period": {"type": "STRING", "description": "hoje | ontem | semana passada | mês passado | últimos N dias"},
        },
        "required": [],
    },
    "handler": buscar_historico,
}
