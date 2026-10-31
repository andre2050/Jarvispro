"""Desativar ações que você não usa ou que vivem falhando. Ver core/acoes_desativadas.py."""
from core import acoes_desativadas as D


def manage_actions(parameters: dict, **_kw) -> str:
    acao = str(parameters.get("action") or "list").strip().lower()
    nome = str(parameters.get("name") or "").strip()
    try:
        if acao in ("disable", "desativar"):
            D.desativar(nome)
            return f"[done] “{nome}” desativada. Vale na próxima vez que o NEXUS abrir. Para voltar: reativar {nome}."
        if acao in ("enable", "reativar"):
            return f"[done] “{nome}” reativada; vale na próxima vez que o NEXUS abrir." if D.reativar(nome) else f"“{nome}” não estava desativada."
        if acao in ("suspects", "suspeitas", "falhas"):
            from core import audit
            s = D.suspeitas(audit.ler())
            if not s:
                return "[done] Nenhuma ação está falhando de forma repetida (nos últimos 14 dias)."
            return "[done] Falham muito: " + "; ".join(f"{x['nome']} ({x['falhas']} de {x['chamadas']})" for x in s[:8]) + ". Posso desativar alguma."
        d = D.carregar()
        return "[done] " + (("Desativadas: " + ", ".join(d) + ".") if d else "Nenhuma ação desativada.")
    except ValueError as e:
        return f"[failed] {e}"


TOOL = {
    "name": "manage_actions",
    "description": ("Turns NEXUS abilities off or on. action=list | disable (name) | enable (name) | suspects (abilities that keep failing). "
                    "Use for 'desativa a ação X', 'o que anda falhando?', 'reativa X'. Safety and settings abilities can't be disabled. "
                    "Takes effect the next time NEXUS starts."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["list", "disable", "enable", "suspects"]}, "name": {"type": "STRING"}}},
    "handler": manage_actions,
}
