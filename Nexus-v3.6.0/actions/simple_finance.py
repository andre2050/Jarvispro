"""Finanças simples — o NEXUS anota seus gastos e te avisa do orçamento (NEXUS Ultra 2026 2.1).

    "gastei 35 reais no mercado"                     → anota (categoria: mercado)
    "recebi 3000 de salário"                         → receita
    "gastei 50 de uber ontem"                        → com data
    "quanto gastei esse mês?"  /  "e no mês passado?" → resumo (com comparação)
    "onde mais gastei esse mês?"                     → por categoria
    "meu limite de alimentação é 800 por mês"        → orçamento
    "como está meu orçamento?"                       → quanto de cada limite já foi usado
    "apaga o último lançamento"                      → desfaz

Tudo fica só no seu computador (config/finance_entries.json e finance_budgets.json). Não
conecta em banco nenhum e não é conselho financeiro. Os lançamentos antigos (versão 2.0) continuam
valendo: o formato do arquivo não mudou.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

from core.pt_time import BRASILIA, agora, de_timestamp

_CONFIG = Path(__file__).resolve().parent.parent / "config"
_FILE = _CONFIG / "finance_entries.json"
_BUDGETS = _CONFIG / "finance_budgets.json"
_LOCK = threading.RLock()
MAX_LANCAMENTOS = 20000
TOTAL = "total"                      # nome do orçamento geral (soma de todas as categorias)
_MAX_VALOR = 100_000_000


# ── texto e números ──────────────────────────────────────────────────────────

def _norm(t) -> str:
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t).strip()


def _valor(v) -> float | None:
    """Número a partir de 35, 35.5, "35,50", "R$ 1.234,56", "1.234" (mil, duzentos e trinta e quatro)."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v) if v == v and abs(v) != float("inf") else None
    t = re.sub(r"[^\d,.\-]", "", str(v or ""))
    if not t or t in ("-", ",", "."):
        return None
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", t):
        t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        return None


def real(v: float) -> str:
    """R$ 1.234,56"""
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'-' if v < 0 else ''}R$ {s}"


def _data(texto) -> datetime | None:
    """hoje, ontem, anteontem, 2026-10-05, 05/10/2026, 05/10."""
    t = _norm(texto)
    if not t:
        return None
    hoje = agora()
    if t in ("hoje", "today"):
        return hoje
    if t in ("ontem", "yesterday"):
        return hoje - timedelta(days=1)
    if t == "anteontem":
        return hoje - timedelta(days=2)
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    d = m and (int(m[3]), int(m[2]), int(m[1]))
    m2 = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", t)
    if m2:
        ano = int(m2[3]) if m2[3] else hoje.year
        d = (int(m2[1]), int(m2[2]), ano + 2000 if ano < 100 else ano)
    if not d:
        return None
    try:
        return hoje.replace(year=d[2], month=d[1], day=d[0])
    except ValueError:
        return None


# ── períodos ─────────────────────────────────────────────────────────────────

def _periodo(nome) -> tuple[datetime | None, datetime | None, str]:
    """(início, fim exclusivo, rótulo). None = sem limite."""
    t = _norm(nome) or "mes"
    h = agora()
    dia = h.replace(hour=0, minute=0, second=0, microsecond=0)
    if "passad" in t and ("mes" in t):
        fim = dia.replace(day=1)
        return (fim - timedelta(days=1)).replace(day=1), fim, "no mês passado"
    if "passad" in t and "semana" in t:
        ini = dia - timedelta(days=dia.weekday() + 7)
        return ini, ini + timedelta(days=7), "na semana passada"
    if t in ("hoje", "today", "dia"):
        return dia, dia + timedelta(days=1), "hoje"
    if t in ("ontem", "yesterday"):
        return dia - timedelta(days=1), dia, "ontem"
    if "semana" in t or t == "week":
        ini = dia - timedelta(days=dia.weekday())
        return ini, ini + timedelta(days=7), "nesta semana"
    if "ano" in t or t == "year":
        ini = dia.replace(month=1, day=1)
        return ini, ini.replace(year=ini.year + 1), f"em {ini.year}"
    if t in ("tudo", "all", "total", "geral", "sempre"):
        return None, None, "no total"
    ini = dia.replace(day=1)
    prox = (ini + timedelta(days=32)).replace(day=1)
    return ini, prox, "neste mês"


def _no_periodo(e: dict, ini, fim) -> bool:
    try:
        d = de_timestamp(float(e.get("timestamp", 0)))
    except (TypeError, ValueError, OSError, OverflowError):
        return False
    return (ini is None or d >= ini) and (fim is None or d < fim)


# ── armazenamento ────────────────────────────────────────────────────────────

def _ler_json(arq: Path, padrao):
    try:
        d = json.loads(arq.read_text(encoding="utf-8"))
        return d if isinstance(d, type(padrao)) else padrao
    except (OSError, ValueError):
        return padrao


def _gravar_json(arq: Path, dados) -> None:
    """Grava inteiro ou não grava: um arquivo temporário e uma troca no fim, para uma queda de luz
    no meio da escrita não apagar o histórico."""
    arq.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=arq.name + ".", suffix=".tmp", dir=str(arq.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        os.replace(tmp, arq)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _lancamentos() -> list[dict]:
    return [e for e in _ler_json(_FILE, []) if isinstance(e, dict) and e.get("type") in ("expense", "income")]


def _orcamentos() -> dict[str, float]:
    return {k: float(v) for k, v in _ler_json(_BUDGETS, {}).items() if _valor(v)}


def _categoria(nome, lancs: list[dict], orc: dict) -> str:
    """Categoria como o usuário já a escreveu antes ("alimentacao" → "Alimentação")."""
    bruto = str(nome or "").strip()[:60]
    if not bruto:
        return "Geral"
    chave = _norm(bruto)
    for c in [e.get("category", "") for e in reversed(lancs)] + list(orc):
        if _norm(c) == chave:
            return c
    return bruto[:1].upper() + bruto[1:]


# ── contas ───────────────────────────────────────────────────────────────────

def _soma(lancs, tipo, ini, fim, categoria=None) -> float:
    chave = _norm(categoria) if categoria else None
    return round(sum(float(e["amount"]) for e in lancs
                     if e["type"] == tipo and _no_periodo(e, ini, fim)
                     and (chave is None or _norm(e.get("category")) == chave)), 2)


def _por_categoria(lancs, ini, fim) -> list[tuple[str, float]]:
    acc: dict[str, float] = {}
    nomes: dict[str, str] = {}
    for e in lancs:
        if e["type"] == "expense" and _no_periodo(e, ini, fim):
            k = _norm(e.get("category") or "Geral")
            nomes.setdefault(k, e.get("category") or "Geral")
            acc[k] = acc.get(k, 0.0) + float(e["amount"])
    return sorted(((nomes[k], round(v, 2)) for k, v in acc.items()), key=lambda x: -x[1])


def _aviso_de_orcamento(lancs, orc, categoria: str) -> str:
    """Depois de um gasto: avisa se a categoria (ou o total) passou de 80% / 100% do limite do mês."""
    ini, fim, _ = _periodo("mes")
    avisos = []
    for nome, usado in ((categoria, _soma(lancs, "expense", ini, fim, categoria)),
                        (TOTAL, _soma(lancs, "expense", ini, fim))):
        limite = next((v for k, v in orc.items() if _norm(k) == _norm(nome)), None)
        if not limite:
            continue
        pct = usado / limite * 100
        rotulo = "o orçamento total" if nome == TOTAL else f"o limite de {nome}"
        if pct >= 100:
            avisos.append(f"ATENÇÃO: {rotulo} estourou — {real(usado)} de {real(limite)} ({pct:.0f}%).")
        elif pct >= 80:
            avisos.append(f"Cuidado: {rotulo} já está em {pct:.0f}% ({real(usado)} de {real(limite)}).")
    return " ".join(avisos)


# ── ações ────────────────────────────────────────────────────────────────────

def _adicionar(p: dict, tipo: str) -> str:
    v = _valor(p.get("amount"))
    if v is None:
        return "[failed] Informe um valor numérico válido."
    if v <= 0 or v > _MAX_VALOR:
        return "[failed] O valor precisa ser maior que zero e razoável."
    quando = _data(p.get("date"))
    if p.get("date") and quando is None:
        return "[failed] Não entendi a data. Diga hoje, ontem ou algo como 05/10."
    quando = quando or agora()
    with _LOCK:
        lancs = _ler_json(_FILE, [])
        validos = [e for e in lancs if isinstance(e, dict) and e.get("type") in ("expense", "income")]
        orc = _orcamentos()
        auto_cat = False
        if (tipo == "expense" and not str(p.get("category") or "").strip()
                and str(p.get("description") or "").strip()):
            try:                                   # 2.3 — categoria automática (core/financas_ia.py)
                from core import financas_ia as _fia
                sug = _fia.sugerir(str(p["description"]), validos)
            except Exception:
                sug = None
            if sug:
                p = {**p, "category": sug}
                auto_cat = True
        cat = _categoria(p.get("category"), validos, orc) if tipo == "expense" else \
            str(p.get("category") or "Receita").strip()[:60] or "Receita"
        lancs.append({"type": tipo, "amount": round(v, 2), "category": cat,
                      "description": str(p.get("description") or "")[:240],
                      "timestamp": quando.replace(tzinfo=BRASILIA).timestamp() if p.get("date") else time.time()})
        if len(lancs) > MAX_LANCAMENTOS:
            lancs = lancs[-MAX_LANCAMENTOS:]
        _gravar_json(_FILE, lancs)
        validos = [e for e in lancs if isinstance(e, dict) and e.get("type") in ("expense", "income")]
    msg = (f"{'Despesa' if tipo == 'expense' else 'Receita'} registrada: {real(v)} em {cat}"
           + (" (categoria sugerida pela descrição)" if auto_cat else "")
           + (f" ({str(p.get('description')).strip()[:60]})" if p.get("description") else "")
           + (f", em {quando.strftime('%d/%m')}" if p.get("date") else "") + ".")
    if tipo == "expense":
        aviso = _aviso_de_orcamento(validos, orc, cat)
        if aviso:
            msg += " " + aviso
    return "[done] " + msg


def _resumo(p: dict) -> str:
    lancs = _lancamentos()
    if not lancs:
        return "[done] Ainda não há lançamentos."
    ini, fim, rotulo = _periodo(p.get("period"))
    cat = str(p.get("category") or "").strip()
    rec = _soma(lancs, "income", ini, fim)
    desp = _soma(lancs, "expense", ini, fim, cat or None)
    if cat:
        return f"[done] Gastos com {cat} {rotulo}: {real(desp)}."
    linhas = [f"Resumo {rotulo}: receitas {real(rec)}; despesas {real(desp)}; saldo {real(rec - desp)}."]
    top = _por_categoria(lancs, ini, fim)[:3]
    if top:
        linhas.append("Onde mais gastou: " + "; ".join(f"{c} {real(v)}" for c, v in top) + ".")
    if rotulo == "neste mês":
        a_ini, a_fim, _ = _periodo("mes passado")
        antes = _soma(lancs, "expense", a_ini, a_fim)
        if antes:
            var = (desp - antes) / antes * 100
            linhas.append(f"No mês passado foram {real(antes)} ({'+' if var >= 0 else ''}{var:.0f}% em relação a ele).")
    linhas.append("Dados só neste computador; não é conexão com banco nem conselho financeiro.")
    return "[done] " + " ".join(linhas)


def _categorias(p: dict) -> str:
    ini, fim, rotulo = _periodo(p.get("period"))
    dados = _por_categoria(_lancamentos(), ini, fim)
    if not dados:
        return f"[done] Nenhuma despesa {rotulo}."
    total = sum(v for _, v in dados)
    return (f"[done] Despesas {rotulo} por categoria (total {real(total)}): "
            + "; ".join(f"{c} {real(v)} ({v / total * 100:.0f}%)" for c, v in dados[:10]) + ".")


def _listar(p: dict) -> str:
    ini, fim, rotulo = _periodo(p.get("period") or "tudo")
    cat = _norm(p.get("category"))
    itens = [e for e in _lancamentos() if _no_periodo(e, ini, fim) and (not cat or _norm(e.get("category")) == cat)]
    if not itens:
        return "[done] Ainda não há lançamentos" + (" nesse filtro." if (cat or p.get("period")) else ".")
    try:
        n = max(1, min(30, int(p.get("count") or 10)))
    except (TypeError, ValueError):
        n = 10
    linhas = []
    for e in itens[-n:][::-1]:
        d = de_timestamp(float(e["timestamp"])).strftime("%d/%m")
        sinal = "+" if e["type"] == "income" else "-"
        linhas.append(f"{d} {sinal}{real(float(e['amount']))} {e.get('category', '')}"
                      + (f" ({e['description']})" if e.get("description") else ""))
    return f"[done] Últimos lançamentos {rotulo}: " + "; ".join(linhas) + "."


def _definir_orcamento(p: dict) -> str:
    cat = str(p.get("category") or "").strip()
    v = _valor(p.get("amount"))
    if v is None or v < 0 or v > _MAX_VALOR:
        return "[failed] Informe o valor do limite mensal."
    with _LOCK:
        orc = _ler_json(_BUDGETS, {})
        lancs = _lancamentos()
        nome = TOTAL if (not cat or _norm(cat) in ("total", "geral", "tudo", "orcamento total")) \
            else _categoria(cat, lancs, orc)
        for k in [k for k in orc if _norm(k) == _norm(nome)]:
            orc.pop(k)
        if v == 0:
            _gravar_json(_BUDGETS, orc)
            return f"[done] Limite de {'orçamento total' if nome == TOTAL else nome} removido."
        orc[nome] = round(v, 2)
        _gravar_json(_BUDGETS, orc)
    return (f"[done] Limite {'total' if nome == TOTAL else 'de ' + nome} definido em {real(v)} por mês. "
            "Eu aviso quando passar de 80% e quando estourar.")


def _status_orcamento(_p: dict) -> str:
    orc = _orcamentos()
    if not orc:
        return "[done] Nenhum limite definido ainda. Diga, por exemplo: meu limite de alimentação é 800 por mês."
    lancs = _lancamentos()
    ini, fim, _ = _periodo("mes")
    linhas = []
    for nome, limite in sorted(orc.items(), key=lambda kv: (kv[0] != TOTAL, _norm(kv[0]))):
        usado = _soma(lancs, "expense", ini, fim, None if nome == TOTAL else nome)
        pct = usado / limite * 100 if limite else 0
        marca = " — ESTOUROU" if pct >= 100 else " — atenção" if pct >= 80 else ""
        linhas.append(f"{'Total' if nome == TOTAL else nome}: {real(usado)} de {real(limite)} ({pct:.0f}%){marca}")
    return "[done] Orçamento deste mês: " + "; ".join(linhas) + "."


def _apagar_ultimo(_p: dict) -> str:
    with _LOCK:
        lancs = _ler_json(_FILE, [])
        for i in range(len(lancs) - 1, -1, -1):
            e = lancs[i]
            if isinstance(e, dict) and e.get("type") in ("expense", "income"):
                lancs.pop(i)
                _gravar_json(_FILE, lancs)
                return (f"[done] Apaguei o último lançamento: {'despesa' if e['type'] == 'expense' else 'receita'} "
                        f"de {real(float(e['amount']))} em {e.get('category', '')}.")
    return "[failed] Não há lançamentos para apagar."


_ACOES = {
    "add_expense": lambda p: _adicionar(p, "expense"),
    "add_income": lambda p: _adicionar(p, "income"),
    "summary": _resumo,
    "by_category": _categorias,
    "list": _listar,
    "set_budget": _definir_orcamento,
    "budget_status": _status_orcamento,
    "delete_last": _apagar_ultimo,
}


def simple_finance(parameters: dict, player=None) -> str:
    p = parameters or {}
    acao = str(p.get("action") or "summary").strip().lower()
    fn = _ACOES.get(acao)
    if fn is None:
        return f"[failed] Ação desconhecida: {acao}. Use: {', '.join(_ACOES)}."
    try:
        return fn(p)
    except OSError as e:
        return f"[failed] Não consegui ler ou gravar os lançamentos: {e}"


TOOL = {
    "name": "simple_finance",
    "description": (
        "Personal money tracker, local only (no bank connection). add_expense / add_income: amount, "
        "category (mercado, uber, aluguel…), description, optional date (hoje, ontem, 05/10). "
        "summary: income, expenses and balance for a period (today, week, month, last month, year, all) "
        "with the top categories and a comparison with last month; with category it gives only that "
        "category. by_category: where the money went. list: recent entries. set_budget: monthly limit "
        "for a category (or the total) — amount 0 removes it; after each expense the user is warned at "
        "80% and when the limit is exceeded. budget_status: how much of each limit is used. "
        "delete_last: undo the last entry. Use for 'gastei 50 no mercado', 'quanto gastei esse mês?', "
        "'meu limite de lazer é 300', 'como está meu orçamento?'. Not financial advice."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": list(_ACOES)},
            "amount": {"type": "NUMBER", "description": "Value in reais (for set_budget: the monthly limit)"},
            "category": {"type": "STRING", "description": "Spending category, or 'total' for the overall budget"},
            "description": {"type": "STRING", "description": "What it was (optional)"},
            "date": {"type": "STRING", "description": "When it happened: hoje, ontem, anteontem, 05/10 or 2026-10-05 (default: now)"},
            "period": {"type": "STRING", "description": "hoje | ontem | semana | semana passada | mês (default) | mês passado | ano | tudo"},
            "count": {"type": "INTEGER", "description": "For list: how many entries (default 10)"},
        },
        "required": ["action"],
    },
    "handler": simple_finance,
}
