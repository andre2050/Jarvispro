"""Histórico longo: lembrar conversas antigas. Ver core/historico_longo.py."""
from core import historico_longo as H


def historico_longo(parameters: dict, **_kw) -> str:
    acao = str(parameters.get("action") or "remember").strip().lower()
    q = str(parameters.get("query") or "").strip()
    try:
        if acao in ("forget", "esquecer"):
            if not q:
                return "Diga qual assunto esquecer."
            return f"[done] Apaguei {H.esquecer(q)} lembrança(s) sobre “{q}”."
        if acao in ("forget_all", "esquecer_tudo"):
            return f"[done] Apaguei {H.esquecer_tudo()} lembrança(s) do histórico longo."
        if acao in ("export", "exportar"):
            return H.exportar()[:6000]
        if acao in ("summary", "resumo"):
            return H.resumo()
        H.ingerir()
        return H.lembrar(q) if q else H.resumo()
    except Exception as e:
        return f"[failed] {str(e)[:120]}"


TOOL = {
    "name": "long_history",
    "description": ("Permanent local archive of past conversations, diary and notes, searchable years later. action=remember (query, may include a period like 'mês passado') | "
                    "summary | forget (query) | forget_all | export. Entries with secrets (cards, CPF, API keys) are never stored."),
    "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING", "enum": ["remember", "summary", "forget", "forget_all", "export"]}, "query": {"type": "STRING"}}},
    "handler": historico_longo,
}
