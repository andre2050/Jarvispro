"""Hábitos e metas diárias — o NEXUS Ultra 2026 2.2 acompanha o que você quer manter.

Por voz:  "cria o hábito beber água, meta 8 copos"       "bebi 2 copos de água"
          "fiz exercício hoje"                           "como estão meus hábitos?"
          "quantos dias seguidos de leitura?"            "apaga o hábito de meditar"

Cada hábito tem uma meta por dia (padrão 1). Um dia "bate a meta" quando a soma dos registros
chega nela. A SEQUÊNCIA conta os dias seguidos que bateram a meta; se hoje ainda não bateu, a
sequência de ontem continua valendo (você ainda tem o dia para cumprir).

Diferença para as outras funções: tarefas = algo que se faz UMA vez; hábitos = algo que se repete
todo dia e que se conta.

Arquivo: memory/habitos_diarios.json  ({"habitos": [{nome, meta, unidade, criado, registros: {"AAAA-MM-DD": total}}]}).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from core import armazem

_ARQ = armazem.PASTA_MEMORIA / "habitos_diarios.json"


def _hoje() -> date:
    return datetime.now().date()


def _ler() -> dict:
    d = armazem.carregar(_ARQ, {"habitos": []})
    d["habitos"] = [h for h in d.get("habitos", []) if isinstance(h, dict) and h.get("nome")]
    return d


def _numero(valor, padrao: float = 1.0) -> float:
    try:
        n = float(str(valor).replace(",", ".").strip())
    except (TypeError, ValueError):
        return padrao
    return n if 0 < n < 100000 else padrao


def _fmt(n: float) -> str:
    return f"{n:g}"


def _achar(dados: dict, nome) -> tuple[dict | None, str]:
    return armazem.achar(nome, dados["habitos"], "nome")


def total_do_dia(h: dict, dia: date) -> float:
    return float(h.get("registros", {}).get(dia.isoformat(), 0))


def sequencia(h: dict, hoje: date | None = None) -> int:
    """Dias seguidos batendo a meta. Hoje ainda aberto não quebra a sequência de ontem."""
    hoje = hoje or _hoje()
    meta = float(h.get("meta", 1))
    dia = hoje if total_do_dia(h, hoje) >= meta else hoje - timedelta(days=1)
    n = 0
    while total_do_dia(h, dia) >= meta:
        n += 1
        dia -= timedelta(days=1)
    return n


def melhor_sequencia(h: dict) -> int:
    meta = float(h.get("meta", 1))
    dias = sorted(date.fromisoformat(d) for d, v in h.get("registros", {}).items() if float(v) >= meta)
    melhor = atual = 0
    anterior = None
    for d in dias:
        atual = atual + 1 if anterior and (d - anterior).days == 1 else 1
        melhor = max(melhor, atual)
        anterior = d
    return melhor


def _linha(h: dict, hoje: date) -> str:
    meta = float(h["meta"])
    feito = total_do_dia(h, hoje)
    un = f" {h['unidade']}" if h.get("unidade") else ""
    marca = "✅" if feito >= meta else "⏳"
    seq = sequencia(h, hoje)
    return f"{marca} {h['nome']}: {_fmt(feito)}/{_fmt(meta)}{un}" + (f" (sequência {seq} dia(s))" if seq else "")


def rastreador_habitos(parameters: dict, player=None) -> str:
    acao = str(parameters.get("action") or "status").strip().lower()
    dados = _ler()
    hoje = _hoje()

    if acao in ("create", "criar", "add"):
        nome = str(parameters.get("name") or "").strip()[:60]
        if not nome:
            return "Diga o nome do hábito."
        if any(armazem.norm(h["nome"]) == armazem.norm(nome) for h in dados["habitos"]):
            return f"Você já tem o hábito {nome}."
        if len(dados["habitos"]) >= 40:
            return "Você já tem 40 hábitos. Apague algum antes de criar outro."
        h = {"nome": nome, "meta": _numero(parameters.get("goal"), 1.0),
             "unidade": str(parameters.get("unit") or "").strip()[:20],
             "criado": hoje.isoformat(), "registros": {}}
        dados["habitos"].append(h)
        armazem.salvar(_ARQ, dados)
        un = f" {h['unidade']}" if h["unidade"] else ""
        return f"Criei o hábito {nome}, meta de {_fmt(h['meta'])}{un} por dia."

    if acao in ("log", "registrar", "feito", "done"):
        h, erro = _achar(dados, parameters.get("name"))
        if not h:
            return erro
        qtd = _numero(parameters.get("amount"), 1.0)
        chave = hoje.isoformat()
        h.setdefault("registros", {})
        h["registros"][chave] = round(float(h["registros"].get(chave, 0)) + qtd, 4)
        armazem.salvar(_ARQ, dados)
        feito, meta = h["registros"][chave], float(h["meta"])
        if feito >= meta:
            return (f"Registrado. {h['nome']}: meta de hoje batida ({_fmt(feito)}/{_fmt(meta)})! "
                    f"Sequência: {sequencia(h, hoje)} dia(s).")
        return f"Registrado. {h['nome']}: {_fmt(feito)} de {_fmt(meta)} hoje, faltam {_fmt(meta - feito)}."

    if acao in ("undo", "desfazer"):
        h, erro = _achar(dados, parameters.get("name"))
        if not h:
            return erro
        qtd = _numero(parameters.get("amount"), 1.0)
        chave = hoje.isoformat()
        atual = float(h.get("registros", {}).get(chave, 0))
        if atual <= 0:
            return f"Não há registro de hoje em {h['nome']} para desfazer."
        novo = max(0.0, round(atual - qtd, 4))
        if novo:
            h["registros"][chave] = novo
        else:
            h["registros"].pop(chave, None)
        armazem.salvar(_ARQ, dados)
        return f"Tirei {_fmt(atual - novo)} de hoje em {h['nome']}. Agora: {_fmt(novo)}."

    if acao in ("status", "list", "listar", "hoje"):
        if not dados["habitos"]:
            return "Você ainda não tem hábitos. Diga, por exemplo: cria o hábito beber água, meta 8 copos."
        return " | ".join(_linha(h, hoje) for h in dados["habitos"])

    if acao in ("streak", "stats", "sequencia"):
        h, erro = _achar(dados, parameters.get("name"))
        if not h:
            return erro
        ult7 = sum(1 for i in range(7) if total_do_dia(h, hoje - timedelta(days=i)) >= float(h["meta"]))
        return (f"{h['nome']}: sequência atual {sequencia(h, hoje)} dia(s), melhor {melhor_sequencia(h)}. "
                f"Bateu a meta em {ult7} dos últimos 7 dias.")

    if acao in ("remove", "delete", "apagar"):
        h, erro = _achar(dados, parameters.get("name"))
        if not h:
            return erro
        dados["habitos"].remove(h)
        armazem.salvar(_ARQ, dados)
        return f"Apaguei o hábito {h['nome']} e todo o histórico dele."

    return "Ação desconhecida. Use create, log, undo, status, streak ou remove."


TOOL = {
    "name": "rastreador_habitos",
    "description": (
        "DAILY HABIT / GOAL TRACKER with streaks (drink water, exercise, read, meditate…). "
        "action=create with name (+ goal per day, default 1, and unit like 'copos'); action=log with "
        "name (+ amount, default 1) to count something done today ('bebi 2 copos' → amount=2); "
        "action=undo to take back today's log; action=status for today's progress on every habit "
        "('como estão meus hábitos?'); action=streak with name for current/best streak; action=remove. "
        "Use for repeating daily habits, NOT one-off to-dos (that is 'tarefas')."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "create | log | undo | status | streak | remove"},
            "name": {"type": "STRING", "description": "Habit name or part of it (e.g. 'água')"},
            "goal": {"type": "NUMBER", "description": "For create: the daily goal (default 1)"},
            "unit": {"type": "STRING", "description": "For create: unit, e.g. copos, minutos, páginas"},
            "amount": {"type": "NUMBER", "description": "For log/undo: how much (default 1)"},
        },
        "required": ["action"],
    },
    "handler": rastreador_habitos,
}
