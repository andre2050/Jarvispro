"""Finanças com IA — NEXUS Pro 2.3. Veja core/financas_ia.py.

Por voz: "em que categoria cai 'ifood'?"   "quanto vou fechar o mês gastando?"   "o quanto essa previsão costuma errar?"
"""
from __future__ import annotations

from core import financas_ia as F
from core.pt_time import agora


def _lancs() -> list[dict]:
    from actions import simple_finance as S
    return S._lancamentos()


def _r(v: float) -> str:
    from actions.simple_finance import real
    return real(v)


def financas_ia(parameters: dict, player=None) -> str:
    p = parameters or {}
    acao = str(p.get("action") or "forecast").strip().lower()
    lancs = _lancs()
    if acao in ("category", "categoria"):
        d = str(p.get("description") or "").strip()
        if not d:
            return "Diga a descrição do gasto (ex.: ifood)."
        r = F.prever_categoria(d, lancs)
        if not r:
            return f"[done] Não achei nada parecido com “{d}”. Diga a categoria que eu aprendo."
        return f"[done] “{d}” parece ser {r[0]} (confiança {r[1]:.0%})." + \
            ("" if r[1] >= F.LIMIAR_CONFIANCA else " Está baixa: confirme comigo antes de lançar.")
    if acao in ("forecast", "previsao"):
        r = F.prever_mes(lancs, agora())
        if not r:
            return "[done] Ainda tenho poucos lançamentos (preciso de uns 15 gastos) para prever o mês."
        txt = (f"[done] Até agora você gastou {_r(r['gasto_ate_agora'])}. Pelo seu ritmo, deve fechar o mês em cerca de "
               f"{_r(r['previsto'])} (provável entre {_r(r['faixa'][0])} e {_r(r['faixa'][1])}).")
        if r["fixas_a_cair"]:
            txt += " Contas que costumam cair ainda este mês: " + ", ".join(
                f"{n} ~{_r(v)} (dia {d})" for n, v, d in r["fixas_a_cair"][:5]) + "."
        return txt + " É uma estimativa estatística, não conselho financeiro."
    if acao in ("accuracy", "backtest", "erro"):
        b = F.backtest(lancs, agora())
        if not b:
            return "[done] Ainda não há meses anteriores suficientes para medir o erro."
        media = sum(x["erro"] for x in b) / len(b)
        return ("[done] Nos meses anteriores, prevendo no dia 15, o erro médio seria de "
                f"{media:.0%}: " + "; ".join(f"{x['mes']} previu {_r(x['previsto'])}, gastou {_r(x['real'])}" for x in b[:4]) + ".")
    return "Ação desconhecida. Use category, forecast ou accuracy."


TOOL = {
    "name": "financas_ia",
    "description": (
        "Smart helpers on top of the user's local expense log (simple_finance). action=category with "
        "description: which category an expense belongs to ('em que categoria cai ifood?'); action=forecast: "
        "projected total spending for the current month (so far + recurring bills still to come + daily "
        "pace by weekday); action=accuracy: how far off the forecast would have been in past months. "
        "Statistics and embeddings, not financial advice."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "category | forecast | accuracy"},
        "description": {"type": "STRING", "description": "For category: what the expense was"}},
        "required": ["action"]},
    "handler": financas_ia,
}
