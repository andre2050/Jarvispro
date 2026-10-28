"""Perfis de uso por voz (NEXUS Ultra 2026 3.3): "modo estudo", "vou jogar", "volta pro normal"."""
from __future__ import annotations


def perfil(parameters: dict, player=None) -> str:
    from core import perfis as P
    acao = str(parameters.get("action") or "").strip().lower()
    nome = str(parameters.get("name") or "").strip()
    if acao == "list":
        return "Perfis: " + P.listar()
    if acao == "status" or (not acao and not nome):
        return P.texto_estado()
    return P.definir(nome or acao)


TOOL = {
    "name": "perfil",
    "description": ("Usage profiles that change NEXUS's tone, proactivity and which tools are enabled. Profiles: "
                    "normal, trabalho (work), estudo (study), jogo (game). Use when the user says 'modo trabalho', "
                    "'vou estudar', 'vou jogar', 'volta pro normal', 'qual perfil está ligado?'. action=set with "
                    "name (default when a name is given), status, list. Security rules never change with the "
                    "profile. Answer in Portuguese, briefly."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "set | status | list"},
            "name": {"type": "STRING", "description": "normal | trabalho | estudo | jogo"},
        },
        "required": [],
    },
    "handler": perfil,
}
