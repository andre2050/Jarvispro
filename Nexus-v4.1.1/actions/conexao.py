"""Modo offline por voz (NEXUS Ultra 2026 3.3): "estou sem internet?" / "o que funciona sem internet?"."""
from __future__ import annotations


def conexao(parameters: dict, player=None) -> str:
    from core import conexao as C
    acao = str(parameters.get("action") or "status").strip().lower()
    if acao == "offline":
        return C.texto_offline()
    return C.texto_estado()


TOOL = {
    "name": "conexao",
    "description": ("Checks whether this PC has internet right now and says what NEXUS can and cannot do offline. "
                    "Use when the user asks 'estou sem internet?', 'a internet caiu?', 'o que funciona sem "
                    "internet?', 'e se a internet cair?'. action=status (default; tests the network now), "
                    "offline (what works and what does not without internet). Answer in Portuguese, briefly."),
    "parameters": {
        "type": "OBJECT",
        "properties": {"action": {"type": "STRING", "description": "status | offline"}},
        "required": [],
    },
    "handler": conexao,
}
