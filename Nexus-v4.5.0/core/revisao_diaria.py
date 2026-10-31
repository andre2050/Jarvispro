"""Revisão diária por voz (NEXUS Ultra 2026 3.3): "Nexus, como foi meu dia?".

Monta, só com os seus dados locais (sem modelo, sem rede), um resumo curto para ser FALADO:
  • o que você concluiu hoje (tarefas marcadas como feitas);
  • o que ainda está pendente hoje e o que está atrasado (tarefas);
  • os lembretes que ainda vão tocar hoje;
  • o que fica para amanhã (tarefas com prazo amanhã e lembretes de amanhã).
Só LÊ. Nunca levanta erro para quem chama; uma fonte que falha só some do resumo.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta


def coletar(agora: datetime | None = None, tarefas: list[dict] | None = None,
            lembretes: list[dict] | None = None) -> dict:
    """Os dados do dia (puro e testável: aceita tarefas/lembretes de fora)."""
    agora = agora or datetime.now()
    hoje, amanha = agora.date(), agora.date() + timedelta(days=1)
    if tarefas is None:
        try:
            from actions import tarefas as T
            tarefas = T.listar("todas")
        except Exception:
            tarefas = []
    if lembretes is None:
        try:
            from actions import reminder as R
            lembretes = R.listar()
        except Exception:
            lembretes = []

    ini = datetime.combine(hoje, datetime.min.time()).timestamp()
    feitas = [t for t in tarefas if t.get("feita") and (t.get("concluida") or 0) >= ini]
    abertas = [t for t in tarefas if not t.get("feita")]
    h, a = hoje.isoformat(), amanha.isoformat()
    atrasadas = [t for t in abertas if t.get("prazo") and t["prazo"] < h]
    para_hoje = [t for t in abertas if t.get("prazo") == h]
    para_amanha = [t for t in abertas if t.get("prazo") == a]
    sem_prazo = [t for t in abertas if not t.get("prazo")]

    def _dia(l):
        try:
            return datetime.fromisoformat(l["quando"])
        except Exception:
            return None
    lem_hoje, lem_amanha = [], []
    for l in lembretes:
        d = _dia(l)
        if not d or not l.get("pendente", d > agora):
            continue
        if d.date() == hoje:
            lem_hoje.append((d, l.get("mensagem", "")))
        elif d.date() == amanha:
            lem_amanha.append((d, l.get("mensagem", "")))
    lem_hoje.sort()
    lem_amanha.sort()
    return {"feitas": feitas, "atrasadas": atrasadas, "para_hoje": para_hoje, "para_amanha": para_amanha,
            "sem_prazo": sem_prazo, "lembretes_hoje": lem_hoje, "lembretes_amanha": lem_amanha}


def _lista(titulos: list[str], limite: int = 3) -> str:
    t = [x for x in titulos if x]
    if len(t) <= limite:
        return ", ".join(t[:-1]) + (" e " if len(t) > 1 else "") + t[-1] if t else ""
    return ", ".join(t[:limite]) + f" e mais {len(t) - limite}"


def montar(agora: datetime | None = None, **fontes) -> str:
    try:
        d = coletar(agora, **fontes)
    except Exception as e:
        return f"[failed] Não consegui montar a revisão do dia: {e}"
    partes = []
    if d["feitas"]:
        n = len(d["feitas"])
        partes.append(f"Hoje você concluiu {n} tarefa{'s' if n > 1 else ''}: "
                      + _lista([t["titulo"] for t in d["feitas"]]) + ".")
    else:
        partes.append("Hoje você ainda não marcou nenhuma tarefa como feita.")
    pend = d["para_hoje"] + d["atrasadas"]
    if d["atrasadas"]:
        n = len(d["atrasadas"])
        partes.append(f"{n} tarefa{'s' if n > 1 else ''} atrasada{'s' if n > 1 else ''}: "
                      + _lista([t["titulo"] for t in d["atrasadas"]]) + ".")
    if d["para_hoje"]:
        partes.append("Pendente para hoje: " + _lista([t["titulo"] for t in d["para_hoje"]]) + ".")
    if not pend:
        partes.append("Não há tarefa pendente para hoje.")
    if d["lembretes_hoje"]:
        itens = [f"{m} às {dt:%H:%M}" for dt, m in d["lembretes_hoje"]]
        partes.append("Lembretes que ainda vão tocar hoje: " + _lista(itens) + ".")
    amanha = [t["titulo"] for t in d["para_amanha"]] + [f"{m} às {dt:%H:%M}" for dt, m in d["lembretes_amanha"]]
    if amanha:
        partes.append("Para amanhã: " + _lista(amanha) + ".")
    elif d["sem_prazo"]:
        n = len(d["sem_prazo"])
        partes.append(f"Nada com prazo para amanhã; {n} tarefa{'s' if n > 1 else ''} sem data na lista.")
    else:
        partes.append("Nada marcado para amanhã.")
    return " ".join(partes)
