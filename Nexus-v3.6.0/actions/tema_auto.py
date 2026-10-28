"""Tema automático (3.5): a cor da interface acompanha a hora do dia e o seu humor.

Por voz:  "tema automático pelo horário"   "tema pelo humor"   "tema pelo horário e humor"
          "desliga o tema automático"      "como está o tema?"
A interface troca de cor sozinha em até 1 minuto. Detalhes: core/tema_auto.py."""
from __future__ import annotations

from core import tema_auto as T

_ROTULO = {"desligado": "desligado (vale a cor que você escolheu)", "horario": "pelo horário do dia",
           "humor": "pelo seu humor do diário", "ambos": "pelo horário e pelo humor"}
_ALIAS = {"off": "desligado", "desligar": "desligado", "desligado": "desligado", "horario": "horario",
          "horário": "horario", "hora": "horario", "humor": "humor", "ambos": "ambos", "tudo": "ambos"}


def tema_auto(parameters: dict, player=None) -> str:
    acao = str(parameters.get("action") or "status").strip().lower()
    try:
        if acao in ("set", "definir", "ligar"):
            modo = _ALIAS.get(str(parameters.get("mode") or "").strip().lower())
            if modo is None:
                return "Escolha: horario, humor, ambos ou desligado."
            T.definir_modo(modo)
            extra = ""
            if modo in ("humor", "ambos") and T.humor_recente() is None:
                extra = " Ainda não há humor no diário dos últimos dias; diga “humor 4”, por exemplo, para eu acompanhar."
            return f"[done] Tema automático {_ROTULO[modo]}.{extra}"
        modo = T.modo_atual()
        cor = T.cor_agora(modo)
        return f"Tema automático {_ROTULO[modo]}." + (f" Cor agora: {cor}." if cor else "")
    except Exception as e:
        return f"[failed] Tema automático: {e}"


TOOL = {
    "name": "tema_auto",
    "description": (
        "AUTOMATIC THEME: the interface accent colour follows the time of day and/or the user's journal mood. "
        "action=set with mode horario | humor | ambos | desligado ('tema automático pelo horário', 'desliga o tema "
        "automático'); action=status. To pick a fixed colour the user uses Settings, not this tool."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "set | status"},
            "mode": {"type": "STRING", "description": "For set: horario | humor | ambos | desligado"},
        },
        "required": ["action"],
    },
    "handler": tema_auto,
}
