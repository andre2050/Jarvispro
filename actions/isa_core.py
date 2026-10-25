"""I.S.A. por voz (NEXUS Ultra 2026 1.3).

"Nexus, relatório da I.S.A." / "o que você fez agora há pouco?" /
"como está o seu núcleo?" — o NEXUS lê o próprio fluxo de decisões
(core/isa.py) e conta o que entendeu, o que decidiu e o que executou.
"""
from __future__ import annotations


def _estado_modulos() -> str:
    from core import isa
    st = isa.status()
    partes = []
    con = st.get("conexao")
    if con:
        partes.append(f"Gemini Live: {con}" + (f" ({st['modelo']})" if st.get("modelo") else ""))
    try:
        from core.intent_net import brain
        partes.append("rede neural local: " + ("pronta" if brain.ready else "treinando ou desligada"))
    except Exception:
        pass
    if st.get("funcoes") is not None:
        partes.append(f"{st['funcoes']} funções de automação")
    if st.get("plugins"):
        partes.append(f"{st['plugins']} plugin(s)")
    try:
        from core.settings_tools import actuator_permissions
        perms = actuator_permissions()
        if perms:
            liberados = sum(1 for v in perms.values() if v)
            partes.append(f"permissões do atuador: {liberados} de {len(perms)} grupos liberados")
    except Exception:
        pass
    n = isa.em_andamento()
    if n:
        partes.append(f"{n} ação(ões) rodando agora")
    return "; ".join(partes) + "." if partes else ""


def isa_core(parameters: dict, player=None) -> str:
    from core import isa
    acao = str(parameters.get("action") or "report").strip().lower()

    if acao == "status":
        return "Núcleo I.S.A. — " + (_estado_modulos() or "sem dados ainda.")

    if acao == "last":
        ultimos = [e for e in isa.eventos(80) if e["tipo"] in ("decisao", "resultado", "erro")][:3]
        if not ultimos:
            return "Ainda não tomei nenhuma decisão nesta sessão."
        return " | ".join(f"{e['hora'][:5]} — {e['titulo']}"
                          + (f" ({e['detalhe'][:80]})" if e["detalhe"] else "") for e in ultimos)

    # report (padrão)
    texto = isa.resumo_texto()
    estado = _estado_modulos()
    return f"{texto} Módulos: {estado}" if estado else texto


TOOL = {
    "name": "isa_core",
    "description": ("The I.S.A. core (Intelligent Systems Architecture): NEXUS's own decision log "
                    "and module status. Use when the user asks what you did or decided recently, "
                    "why something happened, how your core/brain is doing, or says 'relatório da "
                    "I.S.A.' / 'status do núcleo'. action=report (numbers + last steps), "
                    "status (modules: Gemini, local neural net, automation, permissions), "
                    "last (the last 3 decisions/results). Answer in Portuguese, briefly."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "report | status | last"},
        },
        "required": [],
    },
    "handler": isa_core,
}
