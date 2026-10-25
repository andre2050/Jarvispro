"""Explicar a IA por voz (NEXUS Ultra 2026).

"Nexus, o que é machine learning?" / "como você aprende?" / "você enxerga?" —
o NEXUS explica a área em palavras simples e conta o que ele tem de verdade
no seu computador agora (core/ia_status.py). "Abre o painel da IA" abre a tela.
"""
from __future__ import annotations


def explicar_ia(parameters: dict, player=None) -> str:
    from core import ia_status as st

    acao = str(parameters.get("action") or "explain").strip().lower()

    if acao == "learn":
        return st.como_aprendo()

    if acao == "self":
        from core import autoavaliacao
        return autoavaliacao.resumo_texto()

    if acao == "types":
        return st.explicar_tipo(st.resolver_tipo(str(parameters.get("type") or parameters.get("area") or "")))

    if acao == "panel":
        abrir = getattr(player, "abrir_painel_ia", None)
        if callable(abrir):
            try:
                abrir("tipos" if parameters.get("type") else "areas")
                return "Abri o painel de como a minha IA funciona."
            except Exception as e:
                return f"Não consegui abrir o painel: {e}"
        return "Não consegui abrir o painel agora. Ele fica dentro do Núcleo I.S.A. (Ctrl+I)."

    chave = st.resolver_area(str(parameters.get("area") or ""))
    return st.explicar(chave)


TOOL = {
    "name": "explicar_ia",
    "description": ("Explains the four areas of artificial intelligence in simple words AND says what NEXUS "
                    "really has of each on this PC right now: machine learning, deep learning (neural "
                    "networks), natural language processing and computer vision. Use when the user asks "
                    "'o que é machine learning / aprendizado profundo / PLN / visão computacional', "
                    "'como você aprende?', 'que IA você usa?', 'você enxerga?', 'o que é IA estreita / AGI / superinteligência', 'que tipo de IA você é?'. action=explain (default; "
                    "set area to ml | dl | pln | visao, or leave empty for an overview of all four), "
                    "learn (how NEXUS learns, with real numbers), self (how NEXUS is doing: its own response times, "
                    "errors per model and the adjustments it made to itself; for 'como você está se saindo?'), types (kinds of AI: narrow/ANI, general/AGI, "
                    "super/ASI, and reactive, limited-memory, theory-of-mind machines; set type to ani | agi | asi | "
                    "reativa | memoria | mente, or leave empty for the whole classification), "
                    "panel (open the on-screen AI panel). "
                    "Answer in Portuguese, briefly, in your own words from the result."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "explain | learn | self | types | panel"},
            "area": {"type": "STRING", "description": "ml | dl | pln | visao (empty = overview)"},
            "type": {"type": "STRING", "description": "for action=types: ani | agi | asi | reativa | memoria | mente"},
        },
        "required": [],
    },
    "handler": explicar_ia,
}
