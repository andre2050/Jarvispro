"""Projetos — o NEXUS sabe no que você está trabalhando (Proativo 2.0, 1.5).

    "Nexus, registra o projeto Loja Virtual, próximo passo: criar a página do carrinho"
    "atualiza o projeto Loja Virtual: próximo passo, ligar o pagamento"
    "como estão meus projetos?"            -> painel com a lista
    "terminei o projeto Loja Virtual"      -> concluído
    "pausa o projeto Loja Virtual"

Os check-ins espontâneos (actions/proactive.py) usam esta lista: em vez de
perguntar algo genérico, o NEXUS lembra do projeto ativo que está parado há
mais tempo e do próximo passo que você anotou. Para não virar chatice:
  • projeto mexido hoje não entra;
  • o mesmo projeto só é puxado de novo depois de 2 dias;
  • projeto pausado ou concluído nunca é puxado.

Os dados ficam em memory/projetos.json, só no seu computador.
"""
from __future__ import annotations

import json
import re
import threading
import unicodedata
from datetime import date, datetime
from pathlib import Path

_ARQ = Path(__file__).resolve().parent.parent / "memory" / "projetos.json"
_LOCK = threading.RLock()
_DIAS_ENTRE_CHECKINS = 2
_MAX_NOTAS = 8

_STATUS = ("ativo", "pausado", "concluido")
_ROTULO = {"ativo": "ativo", "pausado": "pausado", "concluido": "concluído"}


# ── armazenamento ────────────────────────────────────────────────────────────
def _hoje() -> str:
    return date.today().isoformat()


def _carregar() -> dict:
    try:
        d = json.loads(_ARQ.read_text(encoding="utf-8"))
        if isinstance(d, dict) and isinstance(d.get("projetos"), list):
            return d
    except Exception:
        pass
    return {"proximo_id": 1, "projetos": []}


def _salvar(d: dict) -> None:
    try:
        _ARQ.parent.mkdir(parents=True, exist_ok=True)
        tmp = _ARQ.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_ARQ)
    except Exception as e:
        print(f"[Projetos] não salvou: {e}")


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", t).strip()


def _achar(d: dict, nome: str = "", pid=None) -> dict | None:
    """Por número (#3) ou por parte do nome, sem acento nem maiúscula."""
    try:
        n = int(str(pid or "").lstrip("#"))
    except (TypeError, ValueError):
        n = 0
    if n:
        for p in d["projetos"]:
            if p["id"] == n:
                return p
    alvo = _norm(nome)
    if not alvo:
        return None
    exato = [p for p in d["projetos"] if _norm(p["nome"]) == alvo]
    if exato:
        return exato[0]
    parcial = [p for p in d["projetos"]
               if alvo in _norm(p["nome"]) or _norm(p["nome"]) in alvo]
    return parcial[0] if len(parcial) == 1 else None


def _dias_desde(iso: str | None) -> int | None:
    try:
        return (date.today() - datetime.strptime(str(iso), "%Y-%m-%d").date()).days
    except (TypeError, ValueError):
        return None


# ── consultado pelo resto do app ─────────────────────────────────────────────
def pick_projeto() -> dict | None:
    """Um projeto ativo que vale um check-in agora, ou None. Marca o escolhido."""
    with _LOCK:
        d = _carregar()
        candidatos = []
        for p in d["projetos"]:
            if p.get("status") != "ativo":
                continue
            parado = _dias_desde(p.get("atualizado"))
            if parado is None or parado < 1:          # mexido hoje: não incomoda
                continue
            ult = _dias_desde(p.get("ultimo_checkin"))
            if ult is not None and ult < _DIAS_ENTRE_CHECKINS:
                continue
            candidatos.append((parado, p))
        if not candidatos:
            return None
        candidatos.sort(key=lambda x: -x[0])           # o mais parado primeiro
        parado, escolhido = candidatos[0]
        escolhido["ultimo_checkin"] = _hoje()
        _salvar(d)
        return {"nome": escolhido["nome"], "proximo_passo": escolhido.get("proximo_passo", ""),
                "dias_parado": parado,
                "nota": (escolhido.get("notas") or [""])[-1]}


def ativos() -> list[dict]:
    with _LOCK:
        return [dict(p) for p in _carregar()["projetos"] if p.get("status") == "ativo"]


# ── apresentação ─────────────────────────────────────────────────────────────
def _tabela(projetos: list[dict]) -> str:
    if not projetos:
        return "Nenhum projeto registrado ainda."
    linhas = ["| # | Projeto | Situação | Próximo passo | Mexido |", "|---|---|---|---|---|"]
    ordem = {"ativo": 0, "pausado": 1, "concluido": 2}
    for p in sorted(projetos, key=lambda x: (ordem.get(x.get("status"), 9), x["id"])):
        dias = _dias_desde(p.get("atualizado"))
        quando = "hoje" if dias == 0 else (f"há {dias} d" if dias is not None else "—")
        passo = (p.get("proximo_passo") or "—").replace("|", "/")
        linhas.append(f"| {p['id']} | **{p['nome'].replace('|', '/')}** | "
                      f"{_ROTULO.get(p.get('status'), p.get('status'))} | {passo} | {quando} |")
    return "\n".join(linhas)


# ── a ferramenta ─────────────────────────────────────────────────────────────
def projetos(parameters: dict, player=None) -> str:
    acao = str(parameters.get("action") or "list").strip().lower()
    nome = str(parameters.get("name") or "").strip()[:80]
    passo = str(parameters.get("next_step") or "").strip()[:200]
    nota = str(parameters.get("note") or "").strip()[:300]
    pid = parameters.get("project_id")

    with _LOCK:
        d = _carregar()

        if acao == "list":
            ps = d["projetos"]
            if not ps:
                return "There are no registered projects. Say so in one short sentence."
            tabela = _tabela(ps)
            if player is not None and hasattr(player, "show_content"):
                try:
                    player.show_content("PROJETOS", tabela)
                except Exception:
                    pass
            ativos_ = [p for p in ps if p.get("status") == "ativo"]
            resumo = "; ".join(
                f"{p['nome']}" + (f" (next: {p['proximo_passo']})" if p.get("proximo_passo") else "")
                for p in ativos_[:6]) or "none active"
            return (f"{len(ps)} project(s) registered, {len(ativos_)} active. The table is on "
                    f"screen. Active: {resumo}. Summarize in a sentence or two; do not read the table.")

        if acao == "add":
            if not nome:
                return "Ask the user for the project name."
            if _achar(d, nome):
                return (f"A project called '{nome}' already exists. Use action 'update' to "
                        "change it.")
            p = {"id": d["proximo_id"], "nome": nome, "status": "ativo",
                 "proximo_passo": passo, "notas": [nota] if nota else [],
                 "criado": _hoje(), "atualizado": _hoje(), "ultimo_checkin": None}
            d["proximo_id"] += 1
            d["projetos"].append(p)
            _salvar(d)
            _log(f"projeto #{p['id']} registrado: {nome}", player)
            return (f"Project '{nome}' registered (#{p['id']})"
                    + (f", next step: {passo}" if passo else "")
                    + ". Confirm in one short sentence.")

        p = _achar(d, nome, pid)
        if p is None:
            nomes = ", ".join(x["nome"] for x in d["projetos"][:8]) or "none"
            return (f"No unique project matches '{nome or pid}'. Registered: {nomes}. "
                    "Ask which one the user means.")

        if acao == "update":
            mudou = []
            if passo:
                p["proximo_passo"] = passo; mudou.append("next step")
            if nota:
                p.setdefault("notas", []).append(nota)
                p["notas"] = p["notas"][-_MAX_NOTAS:]; mudou.append("note")
            novo_status = str(parameters.get("status") or "").strip().lower()
            if novo_status in _STATUS:
                p["status"] = novo_status; mudou.append(f"status={novo_status}")
            if not mudou:
                return "Nothing to update: ask what changed (next step, note or status)."
            p["atualizado"] = _hoje()
            _salvar(d)
            _log(f"projeto #{p['id']} atualizado ({', '.join(mudou)})", player)
            return f"Project '{p['nome']}' updated ({', '.join(mudou)}). Confirm briefly."

        if acao in ("done", "pause", "resume"):
            p["status"] = {"done": "concluido", "pause": "pausado", "resume": "ativo"}[acao]
            p["atualizado"] = _hoje()
            _salvar(d)
            _log(f"projeto #{p['id']} → {p['status']}", player)
            return (f"Project '{p['nome']}' is now {_ROTULO[p['status']]}. "
                    + ("Congratulate the user in one short sentence." if acao == "done"
                       else "Confirm briefly."))

        if acao == "remove":
            d["projetos"] = [x for x in d["projetos"] if x["id"] != p["id"]]
            _salvar(d)
            _log(f"projeto #{p['id']} removido", player)
            return f"Project '{p['nome']}' removed. Confirm briefly."

        if acao == "show":
            notas = "; ".join(p.get("notas") or []) or "no notes"
            return (f"Project '{p['nome']}': {_ROTULO[p['status']]}, next step: "
                    f"{p.get('proximo_passo') or 'not set'}, last touched "
                    f"{_dias_desde(p.get('atualizado'))} day(s) ago. Notes: {notas}.")

    return "Unknown action. Use add, update, list, show, done, pause, resume or remove."


def _log(msg: str, player=None) -> None:
    print(f"[Projetos] {msg}")
    if player:
        try:
            player.write_log(f"SYS: {msg}")
        except Exception:
            pass


TOOL = {
    "name": "projetos",
    "description": (
        "The user's own projects list, used so your spontaneous check-ins ask about "
        "the right project and its next step. Actions: add ('registra o projeto Loja "
        "Virtual, próximo passo criar o carrinho' — name, next_step), update ('atualiza o "
        "projeto…', 'agora o próximo passo é…' — name + next_step/note/status), list "
        "('como estão meus projetos?' — shows a table on screen), show (one project), done "
        "('terminei o projeto…'), pause, resume, remove. Match projects by part of the name. "
        "It is only a to-do list: registering a project here does NOT let dev_agent find or edit it."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING",
                       "enum": ["add", "update", "list", "show", "done", "pause", "resume", "remove"]},
            "name": {"type": "STRING", "description": "project name (or part of it)"},
            "project_id": {"type": "STRING", "description": "project number, e.g. 3"},
            "next_step": {"type": "STRING", "description": "the next concrete step"},
            "note": {"type": "STRING", "description": "a short progress note"},
            "status": {"type": "STRING", "enum": ["ativo", "pausado", "concluido"]},
        },
        "required": ["action"],
    },
    "handler": projetos,
}
