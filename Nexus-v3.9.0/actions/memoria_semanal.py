"""Memória semanal por voz (NEXUS Ultra 2026 3.2).

"Nexus, o que você aprendeu sobre mim esta semana?" / "o que eu costumo fazer agora?" —
o NEXUS conta o resumo da semana (core/memoria_semanal.py) ou diz o hábito firme deste dia e hora.
Ele só SUGERE: fazer a ação continua dependendo do seu "sim".
"""
from __future__ import annotations


def memoria_semanal(parameters: dict, player=None) -> str:
    from core import memoria_semanal as MS
    acao = str(parameters.get("action") or "summary").strip().lower()

    if acao == "anticipate":
        return MS.sugestao_texto() or "Ainda não vejo um hábito firme para este dia e horário."

    if acao == "forget":
        MS.esquecer()
        return "Apaguei os resumos semanais."

    MS.garantir_semana()
    return MS.texto_da_semana()


TOOL = {
    "name": "memoria_semanal",
    "description": ("NEXUS's weekly memory: what it learned about the user's routine this week and what the "
                    "user usually does around this day and time. Use when the user asks 'o que você aprendeu "
                    "sobre mim', 'resumo da semana', 'o que eu costumo fazer agora', 'o que você acha que eu "
                    "vou querer'. action=summary (default), anticipate (a habit that fits right now; only "
                    "suggest it, never do it without the user's yes), forget (delete the weekly summaries). "
                    "Answer in Portuguese, briefly."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "summary | anticipate | forget"},
        },
        "required": [],
    },
    "handler": memoria_semanal,
}
