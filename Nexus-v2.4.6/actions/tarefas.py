"""Tarefas — a lista de afazeres do NEXUS (Produtividade, NEXUS Pro 2.0).

Por voz:   "anota a tarefa: enviar a proposta, alta prioridade, para amanhã"
           "o que tenho para fazer hoje?"    "marca a 2 como feita"
           "apaga a tarefa do dentista"      "como estou hoje?"
No painel Produtividade (🎯): marcar, criar e apagar com o mouse — é a MESMA lista.

Diferença para as outras funções (para não repetir):
  • notas (quick_notes)  = texto solto para lembrar;
  • lembretes            = um aviso numa data e hora;
  • tarefas (esta)       = algo a FAZER, que se marca como feito, com prioridade e prazo;
  • projetos             = o assunto maior; a tarefa pode apontar para um projeto.

Arquivo: memory/tarefas.json  (lista de {id, titulo, prio, prazo, projeto, feita, criada, concluida}).
"""
from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

_ARQ = Path(__file__).resolve().parent.parent / "memory" / "tarefas.json"
_LOCK = threading.RLock()
_PRIOS = ("alta", "media", "baixa")
_ROTULO = {"alta": "alta", "media": "média", "baixa": "baixa"}
_ORDEM_PRIO = {"alta": 0, "media": 1, "baixa": 2}


# ── armazenamento ────────────────────────────────────────────────────────────
def _carregar() -> list[dict]:
    try:
        d = json.loads(_ARQ.read_text(encoding="utf-8"))
        return [t for t in d if isinstance(t, dict) and t.get("titulo")] if isinstance(d, list) else []
    except Exception:
        return []


def _salvar(itens: list[dict]) -> None:
    _ARQ.parent.mkdir(parents=True, exist_ok=True)
    tmp = _ARQ.with_suffix(".tmp")
    tmp.write_text(json.dumps(itens, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(_ARQ)


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c)).strip()


def _hoje() -> date:
    return date.today()


# ── entendimento de prioridade e prazo ───────────────────────────────────────
def _prio(valor) -> str:
    v = _norm(valor)
    if v in ("alta", "alto", "urgente", "high", "importante", "1"):
        return "alta"
    if v in ("baixa", "baixo", "low", "3"):
        return "baixa"
    return "media"


_DIAS_SEMANA = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]


def _prazo(valor) -> str:
    """'hoje', 'amanhã', 'sexta', '2026-10-25' ou '25/10' → 'AAAA-MM-DD' ('' = sem prazo)."""
    v = _norm(valor)
    if not v or v in ("sem prazo", "nenhum", "none", "-"):
        return ""
    h = _hoje()
    if v in ("hoje", "today"):
        return h.isoformat()
    if v in ("amanha", "tomorrow"):
        return (h + timedelta(days=1)).isoformat()
    if v in ("ontem", "yesterday"):
        return (h - timedelta(days=1)).isoformat()
    if v in ("depois de amanha",):
        return (h + timedelta(days=2)).isoformat()
    if v.startswith("semana que vem") or v.startswith("proxima semana"):
        return (h + timedelta(days=7)).isoformat()
    for i, nome in enumerate(_DIAS_SEMANA):
        if v.startswith(nome):
            dif = (i - h.weekday()) % 7 or 7
            return (h + timedelta(days=dif)).isoformat()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", v)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3])).isoformat()
        except ValueError:
            return ""
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", v)
    if m:
        ano = int(m[3]) if m[3] else h.year
        ano += 2000 if ano < 100 else 0
        try:
            d = date(ano, int(m[2]), int(m[1]))
            if not m[3] and d < h:
                d = date(ano + 1, int(m[2]), int(m[1]))
            return d.isoformat()
        except ValueError:
            return ""
    return ""


def _prazo_legivel(iso: str) -> str:
    if not iso:
        return "sem prazo"
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return iso
    dif = (d - _hoje()).days
    if dif == 0:
        return "hoje"
    if dif == 1:
        return "amanhã"
    if dif == -1:
        return "ontem (atrasada)"
    if dif < 0:
        return f"atrasada há {-dif} dias"
    if dif < 7:
        return ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"][d.weekday()]
    return d.strftime("%d/%m")


# ── API usada pelo painel e pela voz ─────────────────────────────────────────
def adicionar(titulo: str, prio: str = "media", prazo: str = "", projeto: str = "") -> dict | None:
    titulo = re.sub(r"\s+", " ", str(titulo or "")).strip()[:200]
    if not titulo:
        return None
    with _LOCK:
        itens = _carregar()
        novo = {"id": (max([t.get("id", 0) for t in itens] or [0]) + 1), "titulo": titulo,
                "prio": _prio(prio), "prazo": _prazo(prazo), "projeto": str(projeto or "").strip()[:60],
                "feita": False, "criada": time.time(), "concluida": None}
        itens.append(novo)
        _salvar(itens)
        return dict(novo)


def listar(filtro: str = "abertas") -> list[dict]:
    """filtro: abertas | hoje | atrasadas | feitas | todas. Abertas vêm por urgência."""
    with _LOCK:
        itens = _carregar()
    h = _hoje().isoformat()
    if filtro == "feitas":
        r = [t for t in itens if t.get("feita")]
        return sorted(r, key=lambda t: -(t.get("concluida") or 0))
    abertas = [t for t in itens if not t.get("feita")]
    if filtro == "hoje":
        abertas = [t for t in abertas if t.get("prazo") and t["prazo"] <= h]
    elif filtro == "atrasadas":
        abertas = [t for t in abertas if t.get("prazo") and t["prazo"] < h]
    elif filtro == "todas":
        abertas = itens
    return sorted(abertas, key=lambda t: (bool(t.get("feita")), _ORDEM_PRIO.get(t.get("prio"), 1),
                                          t.get("prazo") or "9999", t["id"]))


def marcar(id_: int, feita: bool = True) -> bool:
    with _LOCK:
        itens = _carregar()
        for t in itens:
            if t["id"] == id_:
                t["feita"] = bool(feita)
                t["concluida"] = time.time() if feita else None
                _salvar(itens)
                return True
    return False


def remover(id_: int) -> bool:
    with _LOCK:
        itens = _carregar()
        ficam = [t for t in itens if t["id"] != id_]
        if len(ficam) == len(itens):
            return False
        _salvar(ficam)
        return True


def limpar_feitas() -> int:
    with _LOCK:
        itens = _carregar()
        ficam = [t for t in itens if not t.get("feita")]
        _salvar(ficam)
        return len(itens) - len(ficam)


def estatisticas() -> dict:
    """{abertas, atrasadas, para_hoje, feitas_hoje, feitas_total}"""
    with _LOCK:
        itens = _carregar()
    h = _hoje()
    ini = datetime.combine(h, datetime.min.time()).timestamp()
    abertas = [t for t in itens if not t.get("feita")]
    return {
        "abertas": len(abertas),
        "atrasadas": sum(1 for t in abertas if t.get("prazo") and t["prazo"] < h.isoformat()),
        "para_hoje": sum(1 for t in abertas if t.get("prazo") == h.isoformat()),
        "feitas_hoje": sum(1 for t in itens if t.get("feita") and (t.get("concluida") or 0) >= ini),
        "feitas_total": sum(1 for t in itens if t.get("feita")),
    }


def resumo_para_plano(maximo: int = 8) -> list[str]:
    """Linhas curtas das tarefas abertas, para o plano do dia (actions/daily_planner)."""
    return [f"{t['titulo']} (prioridade {_ROTULO[t['prio']]}, {_prazo_legivel(t['prazo'])})"
            for t in listar("abertas")[:maximo]]


# ── a ferramenta de voz ──────────────────────────────────────────────────────
def _linha(i: int, t: dict) -> str:
    extra = []
    if t.get("prio") == "alta":
        extra.append("alta")
    if t.get("prazo"):
        extra.append(_prazo_legivel(t["prazo"]))
    if t.get("projeto"):
        extra.append(t["projeto"])
    return f"{i}. {t['titulo']}" + (f" ({', '.join(extra)})" if extra else "")


def _achar(alvo: str, lista: list[dict]) -> tuple[dict | None, str]:
    alvo = str(alvo or "").strip()
    if not alvo:
        return None, "Diga qual tarefa: o número da lista ou parte do nome."
    if alvo.isdigit():
        n = int(alvo)
        if 1 <= n <= len(lista):
            return lista[n - 1], ""
        return None, f"Não há tarefa número {n}. Peça a lista primeiro."
    achadas = [t for t in lista if _norm(alvo) in _norm(t["titulo"])]
    if len(achadas) == 1:
        return achadas[0], ""
    if not achadas:
        return None, "Não encontrei essa tarefa. Peça a lista e diga o número."
    return None, ("Mais de uma tarefa combina: " + " | ".join(t["titulo"] for t in achadas[:4])
                  + ". Diga o número.")


def tarefas(parameters: dict, player=None) -> str:
    acao = str(parameters.get("action") or "list").strip().lower()

    if acao in ("add", "create", "adicionar"):
        t = adicionar(parameters.get("title") or parameters.get("titulo") or "",
                      parameters.get("priority") or "media", parameters.get("due") or "",
                      parameters.get("project") or "")
        if not t:
            return "Diga o que é a tarefa."
        _log(f"✅ Tarefa anotada — {t['titulo']}", player)
        quando = f", prazo {_prazo_legivel(t['prazo'])}" if t["prazo"] else ""
        return f"Tarefa anotada: {t['titulo']} (prioridade {_ROTULO[t['prio']]}{quando})."

    if acao in ("list", "today", "overdue", "done_list", "listar"):
        filtro = {"today": "hoje", "overdue": "atrasadas", "done_list": "feitas"}.get(acao, "abertas")
        itens = listar(filtro)
        if not itens:
            return {"hoje": "Nada para hoje. Dia livre.", "atrasadas": "Nenhuma tarefa atrasada.",
                    "feitas": "Ainda não há tarefas concluídas."}.get(filtro, "Você não tem tarefas abertas.")
        corpo = " | ".join(_linha(i, t) for i, t in enumerate(itens[:12], 1))
        mais = f" (e mais {len(itens) - 12})" if len(itens) > 12 else ""
        return f"{len(itens)} tarefa(s): {corpo}{mais}"

    if acao in ("done", "complete", "concluir", "reopen"):
        base = listar("feitas" if acao == "reopen" else "abertas")
        t, erro = _achar(parameters.get("target"), base)
        if not t:
            return erro
        marcar(t["id"], acao != "reopen")
        if acao == "reopen":
            return f"Reabri a tarefa: {t['titulo']}."
        _log(f"✔ Tarefa concluída — {t['titulo']}", player)
        restam = len(listar("abertas"))
        return f"Pronto, concluída: {t['titulo']}. " + (f"Restam {restam}." if restam else "Sua lista está vazia!")

    if acao in ("remove", "delete", "apagar"):
        t, erro = _achar(parameters.get("target"), listar("todas"))
        if not t:
            return erro
        remover(t["id"])
        return f"Apaguei a tarefa: {t['titulo']}."

    if acao == "clear_done":
        return f"Tirei {limpar_feitas()} tarefa(s) concluída(s) da lista."

    if acao in ("stats", "status", "resumo"):
        e = estatisticas()
        try:
            from actions import focus_mode as _F
            foco = int(_F._today_count(_F._read()))
        except Exception:
            foco = 0
        return (f"Hoje: {e['feitas_hoje']} concluída(s), {e['abertas']} aberta(s), "
                f"{e['para_hoje']} com prazo hoje, {e['atrasadas']} atrasada(s). "
                f"Blocos de foco hoje: {foco}.")

    return "Ação desconhecida. Use add, list, today, overdue, done, reopen, remove, clear_done ou stats."


def _log(msg: str, player=None) -> None:
    if player is not None:
        try:
            player.write_log(f"SYS: {msg}")
        except Exception:
            pass


TOOL = {
    "name": "tarefas",
    "description": (
        "The user's TO-DO LIST (things to DO, that get checked off — not loose notes and not timed "
        "reminders). action=add with title (+ optional priority alta|media|baixa, due as hoje|amanhã|"
        "weekday|DD/MM|YYYY-MM-DD, project); action=list (open tasks, most urgent first), today "
        "(due today or late), overdue, done_list; action=done / reopen / remove with target = list "
        "number or words from the title; action=clear_done; action=stats for today's progress "
        "('como estou hoje?'). Use for 'anota a tarefa…', 'o que tenho para fazer?', 'marca como feita'. "
        "Shopping or any named list: add each item with project='Compras' (or the list name) and "
        "list it back by that project."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "add | list | today | overdue | done_list | done | reopen | remove | clear_done | stats"},
            "title": {"type": "STRING", "description": "For add: what has to be done"},
            "priority": {"type": "STRING", "description": "For add: alta | media | baixa"},
            "due": {"type": "STRING", "description": "For add: hoje, amanhã, a weekday, DD/MM or YYYY-MM-DD"},
            "project": {"type": "STRING", "description": "For add: the project this belongs to (optional)"},
            "target": {"type": "STRING", "description": "For done/reopen/remove: list number or part of the title"},
        },
        "required": ["action"],
    },
    "handler": tarefas,
}
