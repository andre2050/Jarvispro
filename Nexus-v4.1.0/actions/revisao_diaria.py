"""Revisão diária por voz (NEXUS Ultra 2026 3.3)."""
from __future__ import annotations


def revisao_diaria(parameters: dict, player=None) -> str:
    from core import revisao_diaria as R
    return R.montar()


TOOL = {
    "name": "revisao_diaria",
    "description": ("Daily voice review: what the user finished today, what is still pending or overdue, the "
                    "reminders still to ring today, and what is left for tomorrow. Use for 'como foi meu dia?', "
                    "'revisão do dia', 'o que falta fazer?', 'o que fica para amanhã?'. Read-only. Read the "
                    "result aloud in Portuguese, briefly, without adding items."),
    "parameters": {"type": "OBJECT", "properties": {}, "required": []},
    "handler": revisao_diaria,
}
