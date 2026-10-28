"""Auditoria por voz: "por que você fez isso?", "o que você fez hoje?", "o registro está íntegro?"."""
from __future__ import annotations


def auditoria(parameters: dict, player=None) -> str:
    from core import auditoria as A
    acao = str(parameters.get("action") or "explain").strip().lower()
    if acao in ("verify", "verificar"):
        ok, msg = A.verificar()
        return ("[done] " if ok else "[failed] ") + msg
    if acao in ("recent", "recentes"):
        itens = A.ler(int(parameters.get("limit") or 8))
        return "\n".join(A.descrever(d) for d in reversed(itens)) or "O registro está vazio."
    return A.explicar(str(parameters.get("query") or ""), int(parameters.get("limit") or 5))


TOOL = {
    "name": "auditoria",
    "description": ("Verifiable audit log of everything NEXUS did (tool calls, decisions the user confirmed or refused, "
                    "missions). action=explain with query answers 'por que você fez isso?' / 'por que você abriu X?' from the "
                    "log (what, why, with which model, result); action=recent lists the latest entries; action=verify checks "
                    "that nobody altered the log (hash chain). Use when the user asks why, what or whether you can be trusted. "
                    "Only report what the log says; if it says nothing, say you have no record. Answer in Portuguese."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["explain", "recent", "verify"]},
            "query": {"type": "STRING", "description": "explain: what the user asks about"},
            "limit": {"type": "INTEGER"},
        },
        "required": [],
    },
    "handler": auditoria,
}
