"""Aprovações aprendidas: o NEXUS sugere "faço sem perguntar?" depois de 5 sins seguidos, e só você cria ou revoga a regra."""
from core import aprovacoes as A


def aprovacoes(parameters: dict, **_kw) -> str:
    acao = str(parameters.get("action") or "status").strip().lower()
    sig = str(parameters.get("rule") or "").strip().lower()
    if acao in ("accept", "aceitar"):
        sug = A.sugestoes()
        alvo = sig or (sug[0] if len(sug) == 1 else "")
        if not alvo:
            return "Qual regra? Sugestões: " + (", ".join(sug) or "nenhuma") + "."
        return "[done] Pronto, passo “%s” agora é automático (só escritas simples)." % alvo if A.aceitar(alvo) else "[failed] Essa regra não é permitida."
    if acao in ("decline", "recusar"):
        for s in ([sig] if sig else A.sugestoes()):
            A.recusar(s)
        return "[done] Ok, não pergunto de novo por 30 dias."
    if acao in ("revoke", "revogar"):
        return "[done] Regra removida." if A.revogar(sig) else "Não achei essa regra."
    return f"Regras automáticas: {', '.join(A.regras()) or 'nenhuma'}. Sugestões esperando você: {', '.join(A.sugestoes()) or 'nenhuma'}."


TOOL = {
    "name": "approvals",
    "description": ("Learned approvals for missions: status | accept (rule) | decline | revoke (rule). Only the USER's yes creates an automatic "
                    "rule, and only for simple writes; deleting, sending, moving, spending, controlling the PC never become automatic."),
    "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING", "enum": ["status", "accept", "decline", "revoke"]},
                                                      "rule": {"type": "STRING"}}, "required": ["action"]},
    "handler": aprovacoes,
}
