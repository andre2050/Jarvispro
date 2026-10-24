"""Diário e humor — o NEXUS Pro 2.2 guarda o seu dia (só no seu PC).

Por voz:  "escreve no diário: hoje terminei a prova e me senti aliviado"       "humor 4"
          "o que escrevi ontem?"     "procura no diário: viagem"      "como tem sido meu humor?"

O humor é uma nota de 1 (péssimo) a 5 (ótimo). O NEXUS só anota e mostra o que VOCÊ disse;
não interpreta nem diagnostica nada a partir do que está escrito.

Arquivo: memory/diario.json  (lista de {id, quando, texto, humor}). Fica fora do GitHub.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from core import armazem

_ARQ = armazem.PASTA_MEMORIA / "diario.json"
_ROTULO_HUMOR = {1: "péssimo", 2: "ruim", 3: "mais ou menos", 4: "bom", 5: "ótimo"}


def _agora() -> datetime:
    return datetime.now().replace(microsecond=0)


def _ler() -> list[dict]:
    itens = [e for e in armazem.carregar(_ARQ, []) if isinstance(e, dict) and e.get("quando")]
    return sorted(itens, key=lambda e: e["quando"])


def _humor(valor) -> int | None:
    if valor in (None, ""):
        return None
    try:
        n = int(float(str(valor).replace(",", ".")))
    except ValueError:
        return None
    return n if 1 <= n <= 5 else None


def _dia(e: dict) -> date:
    return datetime.fromisoformat(e["quando"]).date()


def _quando_txt(e: dict) -> str:
    d = datetime.fromisoformat(e["quando"])
    return f"{d:%d/%m} {d:%H:%M}"


def _linha(e: dict) -> str:
    h = f" [humor {e['humor']}]" if e.get("humor") else ""
    return f"{_quando_txt(e)}{h}: {e['texto']}" if e.get("texto") else f"{_quando_txt(e)}{h}"


def _data_pedida(v) -> date | None:
    n = armazem.norm(v)
    hoje = _agora().date()
    if n in ("hoje", "today", ""):
        return hoje
    if n in ("ontem", "yesterday"):
        return hoje - timedelta(days=1)
    if n in ("anteontem",):
        return hoje - timedelta(days=2)
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?", n)
    if m:
        ano = int(m[3]) if m[3] else hoje.year
        ano += 2000 if ano < 100 else 0
        try:
            return date(ano, int(m[2]), int(m[1]))
        except ValueError:
            return None
    try:
        return date.fromisoformat(n)
    except ValueError:
        return None


def diario(parameters: dict, player=None) -> str:
    acao = str(parameters.get("action") or "read").strip().lower()
    itens = _ler()

    if acao in ("write", "escrever", "add"):
        texto = str(parameters.get("text") or "").strip()[:4000]
        humor = _humor(parameters.get("mood"))
        if parameters.get("mood") not in (None, "") and humor is None:
            return "O humor é uma nota de 1 a 5. Diga de novo."
        if not texto and humor is None:
            return "O que devo escrever no diário?"
        e = {"id": armazem.novo_id(itens), "quando": _agora().isoformat(), "texto": texto, "humor": humor}
        itens.append(e)
        armazem.salvar(_ARQ, itens)
        h = f" Humor {humor} ({_ROTULO_HUMOR[humor]})." if humor else ""
        return "Anotado no diário." + h

    if acao in ("read", "ler", "list"):
        d = _data_pedida(parameters.get("date"))
        if d is None:
            return "Não entendi a data. Diga hoje, ontem ou 22/10."
        do_dia = [e for e in itens if _dia(e) == d]
        if not do_dia:
            return f"Não há anotações em {d:%d/%m/%Y}."
        return f"{d:%d/%m/%Y}: " + " | ".join(_linha(e).split(" ", 1)[1] for e in do_dia[-8:])

    if acao in ("recent", "recentes"):
        if not itens:
            return "O diário está vazio."
        return " | ".join(_linha(e) for e in itens[-5:])

    if acao in ("search", "buscar", "procurar"):
        q = armazem.norm(parameters.get("query") or parameters.get("text"))
        if not q:
            return "O que devo procurar no diário?"
        achados = [e for e in itens if q in armazem.norm(e.get("texto"))]
        if not achados:
            return f"Não achei “{q}” no diário."
        return f"{len(achados)} anotação(ões): " + " | ".join(_linha(e) for e in achados[-5:])

    if acao in ("mood", "humor", "stats"):
        try:
            dias = max(1, min(365, int(parameters.get("days") or 7)))
        except (TypeError, ValueError):
            dias = 7
        corte = _agora().date() - timedelta(days=dias - 1)
        notas = [e["humor"] for e in itens if e.get("humor") and _dia(e) >= corte]
        if not notas:
            return f"Você não registrou humor nos últimos {dias} dia(s)."
        media = sum(notas) / len(notas)
        metade = len(notas) // 2
        tendencia = ""
        if metade >= 2:
            ant, rec = sum(notas[:metade]) / metade, sum(notas[metade:]) / (len(notas) - metade)
            tendencia = (" Subindo." if rec - ant >= 0.5 else " Caindo." if ant - rec >= 0.5 else " Estável.")
        return (f"Humor médio dos últimos {dias} dia(s): {media:.1f} de 5 ({len(notas)} registro(s)); "
                f"melhor {max(notas)}, pior {min(notas)}.{tendencia}")

    if acao in ("remove_last", "apagar_ultima"):
        if not itens:
            return "O diário está vazio."
        ultimo = itens[-1]
        armazem.salvar(_ARQ, itens[:-1])
        return f"Apaguei a última anotação ({_quando_txt(ultimo)})."

    return "Ação desconhecida. Use write, read, recent, search, mood ou remove_last."


TOOL = {
    "name": "diario",
    "description": (
        "PRIVATE JOURNAL with a 1-5 mood score, stored only on this PC. action=write with text and/or "
        "mood (1=terrible … 5=great) — 'escreve no diário…', 'meu humor hoje é 4'; action=read with date "
        "(hoje|ontem|DD/MM, default hoje); action=recent (last 5 entries); action=search with query; "
        "action=mood with days (default 7) for the average and trend; action=remove_last. Record and "
        "report only what the user wrote; never interpret or diagnose."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "write | read | recent | search | mood | remove_last"},
            "text": {"type": "STRING", "description": "For write: what to record"},
            "mood": {"type": "INTEGER", "description": "For write: mood 1 (terrible) to 5 (great)"},
            "date": {"type": "STRING", "description": "For read: hoje, ontem, DD/MM or YYYY-MM-DD"},
            "query": {"type": "STRING", "description": "For search: words to look for"},
            "days": {"type": "INTEGER", "description": "For mood: how many days back (default 7)"},
        },
        "required": ["action"],
    },
    "handler": diario,
}
