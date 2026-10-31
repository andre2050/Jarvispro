"""I.S.A. por voz (NEXUS Ultra 2026 1.3).

"Nexus, relatório da I.S.A." / "o que você fez agora há pouco?" /
"como está o seu núcleo?" — o NEXUS lê o próprio fluxo de decisões
(core/isa.py) e conta o que entendeu, o que decidiu e o que executou.
"""
from __future__ import annotations
from core.protecao import engolida as _engolida


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
        _engolida("actions/isa_core.py:21")
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
        _engolida("actions/isa_core.py:33")
    n = isa.em_andamento()
    if n:
        partes.append(f"{n} ação(ões) rodando agora")
    return "; ".join(partes) + "." if partes else ""


def _avancado(acao: str, parameters: dict) -> str | None:
    """3.4 — previsão, desempenho, auto-regeneração e rede colaborativa. None = não é uma destas ações."""
    from core import isa_preditiva as IP

    if acao in ("predict", "previsao"):
        prev = IP.prever()
        if not prev:
            n = len(IP.serie())
            return ("Nenhum problema à vista: disco, memória, tempo de resposta e funções estão estáveis."
                    if n >= 4 else "Ainda estou juntando medidas (uma a cada 5 min) para prever tendências.")
        return "Previsões da I.S.A.: " + " | ".join(f"{p['texto']} Sugestão: {p['sugestao']}" for p in prev[:4])

    if acao in ("optimize", "otimizar"):
        feitos = IP.otimizar()
        from core import autoregeneracao as AR
        feitos += AR.verificar(previsoes=IP.prever())
        return "Otimizei: " + "; ".join(feitos) + "." if feitos else "Nada para otimizar agora."

    if acao in ("performance", "desempenho"):
        alvo = str(parameters.get("mode") or "").strip().lower()
        if alvo in ("auto", "automatico", "automático"):
            IP.automatico()
            return f"Desempenho automático ligado (agora: {IP.modo()}). Eu ajusto conforme o uso do PC."
        if alvo in IP.MODOS:
            IP.definir_modo(alvo, "pedido do usuário", manual=True)
            return f"Modo {alvo} fixado. Diga 'desempenho automático' para eu voltar a escolher."
        return (f"Modo de desempenho: {IP.modo()}" + (" (fixado por você)" if IP.modo_manual() else " (automático)")
                + ". Modos: economia, equilibrado, desempenho ou automático.")

    if acao in ("health", "saude", "repair", "reparar"):
        from core import autoregeneracao as AR
        if acao in ("repair", "reparar"):
            from core import confirm
            feitos = AR.verificar(previsoes=IP.prever(),
                                  confirmar=lambda t, d, f: confirm.request("instalar_pacote", t, d, f))
            return ("Rodada de auto-regeneração: " + "; ".join(feitos) + ".") if feitos else \
                "Rodada de auto-regeneração: não achei nada quebrado."
        return AR.resumo_texto()

    if acao in ("network", "rede"):
        from core import rede_colaborativa as RCo
        ligar = str(parameters.get("enable") or "").strip().lower()
        if ligar in ("true", "sim", "1", "on", "ligar"):
            return RCo.configurar(True, str(parameters.get("code") or ""))
        if ligar in ("false", "nao", "não", "0", "off", "desligar"):
            return RCo.configurar(False)
        st = RCo.status()
        if not st["ligada"]:
            return "A rede colaborativa está desligada. Para ligar, diga um código de grupo (8+ caracteres)."
        if str(parameters.get("share") or "").lower() in ("true", "1", "sim"):
            RCo.anunciar()
        return (f"Rede colaborativa ligada: {st['pares']} outro(s) NEXUS ouvido(s), {st['recebidos']} pacote(s) "
                f"aceito(s), {st['rejeitados']} recusado(s).")
    return None


def isa_core(parameters: dict, player=None) -> str:
    from core import isa
    acao = str(parameters.get("action") or "report").strip().lower()
    avancado = _avancado(acao, parameters)
    if avancado is not None:
        return avancado

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
    try:                                                  # 3.4 — o modo de desempenho e o que se regenerou
        from core import isa_preditiva as IP
        from core import autoregeneracao as AR
        estado += f" Desempenho: {IP.modo()}. " + AR.resumo_texto()
    except Exception:
        _engolida("actions/isa_core.py:121")
    return f"{texto} Módulos: {estado}" if estado else texto


TOOL = {
    "name": "isa_core",
    "description": ("The I.S.A. core (Intelligent Systems Architecture): NEXUS's own decision log "
                    "and module status. Use when the user asks what you did or decided recently, "
                    "why something happened, how your core/brain is doing, or says 'relatório da "
                    "I.S.A.' / 'status do núcleo'. action=report (numbers + last steps), "
                    "status (modules: Gemini, local neural net, automation, permissions), "
                    "last (the last 3 decisions/results). 3.4 ADVANCED CORE: predict ('vai dar algum problema?', "
                    "'previsão do sistema' — disk, memory leaks, slowness, failing functions, BEFORE they happen), "
                    "optimize ('otimiza o sistema' — safe fixes now), performance with mode economia | equilibrado | "
                    "desempenho | auto ('modo economia', 'desempenho automático'), health (self-healing report), "
                    "repair ('se conserta', 'roda a auto-regeneração'), network (collaborative learning with the "
                    "user's other NEXUS on the LAN: enable=true + code to turn on, enable=false to turn off, "
                    "share=true to send now). Answer in Portuguese, briefly."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING",
                       "description": "report | status | last | predict | optimize | performance | health | repair | network"},
            "mode": {"type": "STRING", "description": "performance: economia | equilibrado | desempenho | auto"},
            "enable": {"type": "STRING", "description": "network: true to turn on, false to turn off"},
            "code": {"type": "STRING", "description": "network: group code (8+ characters), same on every PC"},
            "share": {"type": "STRING", "description": "network: true to share what was learned now"},
        },
        "required": [],
    },
    "handler": isa_core,
}
