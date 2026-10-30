"""actions/guardrails.py — ver e editar as regras de guardrail (4.1). Só o usuário edita; missões e agentes não podem (está em PROIBIDAS)."""
from __future__ import annotations


def guardrails(parameters: dict, **_kw) -> str:
    from core import guardrails as G
    acao = str(parameters.get("action") or "list").strip().lower()
    try:
        if acao in ("add", "adicionar"):
            nome = G.adicionar({"nome": parameters.get("name"), "tool": parameters.get("tool") or "*", "onde": parameters.get("where") or "entrada",
                                "campo": parameters.get("field") or "*", "padrao": parameters.get("pattern"), "acao": parameters.get("effect") or "bloquear",
                                "motivo": parameters.get("reason") or ""})
            return f"[done] Regra “{nome}” criada. Vale já na próxima chamada de ferramenta."
        if acao in ("remove", "remover"):
            n = G.remover(str(parameters.get("name") or ""))
            return "[done] Regra removida." if n else "[failed] Não achei uma regra SUA com esse nome (as padrão não podem ser removidas)."
        rs = G.regras()
        return "Regras: " + " | ".join(f"{r['nome']} ({r['onde']}, {r['acao']}{', sua' if r not in G.PADRAO else ''})" for r in rs)
    except ValueError as e:
        return f"[failed] {e}"


TOOL = {
    "name": "guardrails",
    "description": ("GUARDRAILS: safety rules checked on every tool call (input) and every tool result (output). Defaults already block API keys "
                    "leaving in messages, deleting system folders and destructive commands, and hide cards/CPF/keys in results. "
                    "action=list shows them; add (name, pattern=regex, effect=bloquear|redigir|avisar, where=entrada|saida, optional tool='a|b' or '*', field, reason) "
                    "creates the user's own rule; remove (name) deletes one of the user's rules. Default rules cannot be turned off. Only on the user's explicit request. Answer in Portuguese."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["list", "add", "remove"]}, "name": {"type": "STRING"}, "pattern": {"type": "STRING"},
        "effect": {"type": "STRING", "enum": ["bloquear", "redigir", "avisar"]}, "where": {"type": "STRING", "enum": ["entrada", "saida"]},
        "tool": {"type": "STRING"}, "field": {"type": "STRING"}, "reason": {"type": "STRING"}}, "required": ["action"]},
    "handler": guardrails,
}
