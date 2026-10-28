"""Núcleo I.S.A. por voz (3.9): módulos e saúde, autonomia da auto-regeneração, análise de código recente e da arquitetura."""
from core import isa_arquitetura as AR
from core import isa_autonomia as AU
from core import isa_codigo as IC
from core import isa_modulos as MO


def isa_nucleo(parameters: dict, **_kw) -> str:
    acao = str(parameters.get("action") or "modules").strip().lower()
    nome = str(parameters.get("module") or "").strip().lower()
    try:
        if acao in ("modules", "modulos"):
            return MO.resumo()
        if acao in ("reload", "recarregar"):
            return MO.recarregar(nome)
        if acao in ("import_cost", "custo"):
            ms = MO.custo_de_importacao(nome)
            return f"{nome}: {ms} ms para carregar a frio." if ms is not None else "Não consegui medir."
        if acao in ("autonomy", "autonomia"):
            if parameters.get("level"):
                return f"[done] Autonomia da auto-regeneração: {AU.definir_nivel(str(parameters['level']))}."
            t = AU.estado_tarefas()
            return f"Autonomia: {AU.nivel()}. Tarefas que já descansaram: " + (", ".join(f"{k} ({v['ciclos']}x)" for k, v in t.items() if v["ciclos"]) or "nenhuma") + "."
        if acao in ("code", "codigo"):
            dias = float(parameters.get("days") or 0)
            if dias:
                arqs = IC.recentes(dias)
            else:
                m = IC.mudancas()
                arqs = m["novos"] + m["alterados"]
            texto = IC.texto(IC.analisar(arqs[:150]))
            if parameters.get("mark"):
                IC.marcar()
                texto += " (Marquei este estado como a base da próxima análise.)"
            return "[done] " + texto + (f" [{len(arqs)} arquivos analisados]" if len(arqs) > 150 else "")
        if acao in ("architecture", "arquitetura"):
            return "[done] " + AR.texto(AR.rodar())
        if acao in ("modularization", "modularizacao", "modularização"):
            from core import isa_modularizacao as MZ
            return "[done] " + MZ.texto(MZ.rodar())
        if acao in ("immunity", "imunidade"):
            from core import imunidade as IM
            return "[done] " + IM.relatorio()
        if acao in ("competition", "competicao", "competição"):
            from core import competicao as CP
            cap, var = str(parameters.get("capability") or ""), str(parameters.get("variant") or "")
            if cap and parameters.get("pin") is not None:
                return "[done] " + CP.fixar(cap, var if parameters.get("pin") else "")
            return "[done] " + CP.relatorio()
        return "[failed] Ação desconhecida."
    except Exception as e:
        return f"[failed] I.S.A.: {e}"


TOOL = {
    "name": "isa_nucleo",
    "description": ("I.S.A. core internals. action=modules (health of each core module) | reload (module) hot-reload with a safety test | "
                    "import_cost (module) | autonomy (optional level avisar|seguros) | code (days or since last mark; mark=true saves the baseline): "
                    "static review of recently changed code | architecture: structure analysis with ranked improvement PROPOSALS (never applies them)."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["modules", "reload", "import_cost", "autonomy", "code", "architecture", "modularization", "immunity", "competition"]},
        "module": {"type": "STRING"}, "capability": {"type": "STRING"}, "variant": {"type": "STRING"}, "pin": {"type": "BOOLEAN"}, "level": {"type": "STRING"}, "days": {"type": "NUMBER"}, "mark": {"type": "BOOLEAN"}},
        "required": ["action"]},
    "handler": isa_nucleo,
}
