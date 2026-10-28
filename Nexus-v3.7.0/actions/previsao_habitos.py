"""Previsão de hábitos — NEXUS Ultra 2026 2.3. Veja core/previsao_habitos.py.

Por voz: "treina a previsão dos meus hábitos"   "o que eu costumo fazer agora?"   "como é meu dia típico?"
"""
from __future__ import annotations

from core import previsao_habitos as P

_DIAS = {"segunda": 0, "terca": 1, "terça": 1, "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5, "sábado": 5, "domingo": 6}


def _nome(sig: str) -> str:
    return sig.replace(":", " ").replace("_", " ")


def previsao_habitos(parameters: dict, player=None) -> str:
    p = parameters or {}
    acao = str(p.get("action") or "now").strip().lower()
    if acao in ("train", "treinar"):
        try:
            r = P.treinar(log=lambda *a: None)
        except ValueError as e:
            return f"[failed] {e}"
        ok = "Ela é melhor que uma contagem simples por hora, então vou usá-la." if r["melhor_que_contagem"] else \
             "Ela ainda NÃO é melhor que uma contagem simples por hora; não vou sugerir nada por ela até haver mais dados."
        return (f"[done] Treinada com {r['eventos']} registros. Em dias que ela não viu, acerta a 1ª opção em "
                f"{r['top1']:.0%} (contagem simples: {r['base_contagem_top1']:.0%}) e a 1ª entre as 3 em {r['top3']:.0%}. {ok}")
    if acao in ("status",):
        r = P.relatorio()
        if not r:
            return "A previsão ainda não foi treinada. Diga 'treina a previsão dos meus hábitos'."
        return (f"[done] Treinada em {r['treinado_em']} com {r['eventos']} registros; acerto {r['top1']:.0%} "
                f"(contagem simples {r['base_contagem_top1']:.0%}). {'Em uso.' if r['melhor_que_contagem'] else 'Sem uso: dados insuficientes.'}")
    if not P.relatorio():
        return "A previsão ainda não foi treinada. Diga 'treina a previsão dos meus hábitos'."
    if acao in ("now", "agora"):
        pr = P.prever(topo=3)
        if not pr:
            return "Sem previsão confiável para agora (ainda faltam dados ou a rede não superou a contagem simples)."
        return "[done] Pelo seu histórico, agora você costuma: " + ", ".join(
            f"{_nome(s)} ({c:.0%})" for s, c in pr) + ". É só uma estimativa; nada foi executado."
    if acao in ("day", "dia"):
        d = _DIAS.get(str(p.get("weekday") or "").strip().lower())
        linhas = P.dia_previsto(d)
        if not linhas:
            return "Não achei horas em que um hábito seja bem previsível."
        return "[done] Dia típico: " + "; ".join(f"{h:02d}h {_nome(s)} ({c:.0%})" for h, s, c in linhas)
    return "Ação desconhecida. Use train, status, now ou day."


TOOL = {
    "name": "previsao_habitos",
    "description": (
        "Predicts what the user usually does at this time using a small local neural network trained on "
        "their own usage history (it only suggests; it never runs anything). action=train, status, now "
        "('o que eu costumo fazer agora?'), day (+ weekday segunda..domingo, optional) for the typical day."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "train | status | now | day"},
        "weekday": {"type": "STRING", "description": "For day: segunda..domingo (default today)"}},
        "required": ["action"]},
    "handler": previsao_habitos,
}
