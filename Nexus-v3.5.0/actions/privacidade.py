"""Painel de privacidade por voz (NEXUS Ultra 2026 3.3): o que guardo, o que sai do PC, apagar com confirmação."""
from __future__ import annotations


import time

_PENDENTE: dict[str, float] = {}      # item → quando o NEXUS pediu a confirmação
_VALE_S = 180


def privacidade(parameters: dict, player=None) -> str:
    from core import privacidade as P
    acao = str(parameters.get("action") or "stored").strip().lower()
    if acao in ("leaves", "sai", "out"):
        return P.sai_texto()
    if acao in ("delete", "apagar", "forget"):
        item = str(parameters.get("item") or "").strip().lower()
        # a confirmação só vale se o pedido SEM confirmação veio antes (o modelo não pode pular a pergunta)
        ok = bool(parameters.get("confirmed")) and time.time() - _PENDENTE.get(item, 0) <= _VALE_S
        if not ok:
            _PENDENTE[item] = time.time()
        else:
            _PENDENTE.pop(item, None)
        return P.apagar(item, confirmar=ok)
    return P.resumo_texto()


TOOL = {
    "name": "privacidade",
    "description": ("Privacy panel. action=stored (default): what NEXUS keeps on the PC; action=leaves: what leaves "
                    "the computer; action=delete + item (conversas, fatos, diario, notas, tarefas, lembretes, "
                    "habitos, autoavaliacao, financas, contatos, casa, registros, perfil, or 'tudo'): delete that "
                    "data. NEVER set confirmed=true on the first call: first call delete without it, read the "
                    "answer, ask the user 'quer mesmo apagar?', and only after a clear 'sim' call again with "
                    "confirmed=true. Answer in Portuguese, briefly."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "stored | leaves | delete"},
            "item": {"type": "STRING", "description": "what to delete"},
            "confirmed": {"type": "BOOLEAN", "description": "true only after the user said yes"},
        },
        "required": [],
    },
    "handler": privacidade,
}
