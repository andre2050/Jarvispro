"""Rotinas criadas por conversa (NEXUS Ultra 2026 3.3).

"Toda segunda de manhã abre o Spotify e me diz o clima" → o NEXUS monta a rotina, MOSTRA o que vai
fazer e quando, e só SALVA depois do seu "sim". Fluxo em 3 passos:

    propor(...)     valida (só ferramentas seguras), guarda a proposta e devolve a prévia para ele ler
    confirmar()     salva em memory/routines.json (com a agenda, se houver)
    cancelar()      descarta a proposta

A AGENDA (dias da semana + hora) fica dentro da própria rotina. O laço de segundo plano chama
`devidas()` a cada 30 s e roda, no máximo uma vez por dia, o que estiver na hora. Nada roda sem ter
passado pela sua confirmação, e rotina só chama ferramentas seguras (core/habits.SAFE_TOOLS).
"""
from __future__ import annotations

import re
import threading
import time
import unicodedata
from datetime import datetime

VALIDADE_S = 300.0                 # a proposta some se ninguém confirmar em 5 minutos
JANELA_MIN = 10                    # roda até 10 min depois da hora marcada (o PC pode ter acabado de ligar)
DIAS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
_PERIODOS = {"manha": "08:00", "tarde": "14:00", "noite": "20:00", "madrugada": "05:00"}

_trava = threading.RLock()
_pendente: dict | None = None


def _sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(t or "").lower()) if unicodedata.category(c) != "Mn")


# ── agenda ──────────────────────────────────────────────────────────────────
def parse_dias(valor) -> list[int] | None:
    """['segunda','quarta'] / 'dias úteis' / 'todo dia' → [0,2]. None = não entendi; [] = sem agenda."""
    if valor in (None, "", [], ()):
        return []
    itens = valor if isinstance(valor, (list, tuple)) else re.split(r"[,;/]| e ", str(valor))
    dias: set[int] = set()
    for it in itens:
        t = _sem_acento(it).strip()
        if not t:
            continue
        if any(k in t for k in ("todo dia", "todos os dias", "diari", "every day", "daily")):
            dias |= set(range(7))
        elif any(k in t for k in ("util", "uteis", "weekday")):
            dias |= set(range(5))
        elif any(k in t for k in ("fim de semana", "weekend")):
            dias |= {5, 6}
        else:
            achou = False
            for i, d in enumerate(DIAS):
                base = _sem_acento(d)
                if t.startswith(base) or base in t:
                    dias.add(i)
                    achou = True
            if not achou:
                return None
    return sorted(dias)


def parse_hora(valor) -> str | None:
    """'8', '8h30', '08:00', 'de manhã' → '08:00'. None = não entendi."""
    t = _sem_acento(valor).strip()
    if not t:
        return None
    for chave, hhmm in _PERIODOS.items():
        if chave in t:
            return hhmm
    m = re.search(r"(\d{1,2})\s*(?:[:h]\s*(\d{2}))?", t)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if "pm" in t and h < 12:
        h += 12
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        return None
    return f"{h:02d}:{mi:02d}"


def descrever_agenda(ag: dict | None) -> str:
    if not ag:
        return "só quando você chamar pelo nome"
    dias = ag["dias"]
    if len(dias) == 7:
        quando = "todo dia"
    elif dias == [0, 1, 2, 3, 4]:
        quando = "nos dias úteis"
    elif dias == [5, 6]:
        quando = "no fim de semana"
    else:
        quando = "toda " + " e ".join(DIAS[d] for d in dias) if len(dias) <= 2 else "nos dias: " + ", ".join(DIAS[d] for d in dias)
    return f"{quando}, às {ag['hora']}"


# ── proposta ────────────────────────────────────────────────────────────────
def propor(nome: str, apps=None, steps=None, dias=None, hora=None, descricao: str = "",
           agora: float | None = None) -> str:
    """Valida e guarda a proposta. Devolve o texto da prévia (ou o erro, começando com '[failed]')."""
    global _pendente
    from actions import smart_routines as SR
    nome = SR._norm(nome)
    if not nome:
        return "[failed] Falta o nome da rotina: pergunte ao usuário como chamar."
    lista_apps = SR._clean_apps(apps)
    extra, erro = SR._parse_steps(steps)
    if erro:
        return f"[failed] Não dá para montar essa rotina: {erro}."
    passos = SR._app_steps(lista_apps) + extra
    if not passos:
        return "[failed] A rotina precisa de pelo menos um aplicativo ou passo: pergunte o que ela deve fazer."
    if len(passos) > SR.MAX_STEPS:
        return f"[failed] Uma rotina pode ter no máximo {SR.MAX_STEPS} passos."

    agenda = None
    d = parse_dias(dias)
    if d is None:
        return "[failed] Não entendi os dias da semana: pergunte de novo (ex.: toda segunda, dias úteis, todo dia)."
    if d:
        h = parse_hora(hora)
        if h is None:
            return "[failed] Falta a hora (ex.: às 8h): pergunte ao usuário a que horas a rotina deve rodar."
        agenda = {"dias": d, "hora": h}
    elif hora:
        return "[failed] Falta dizer em quais dias a rotina roda: pergunte (ex.: toda segunda)."

    with _trava:
        _pendente = {"nome": nome, "steps": passos, "agenda": agenda, "descricao": str(descricao or "")[:200],
                     "criada": agora if agora is not None else time.monotonic()}
    r = {"steps": passos}
    return (f"PRÉVIA da rotina “{nome}”: {SR._describe(nome, r)}. Quando: {descrever_agenda(agenda)}. "
            "Leia isso para o usuário e pergunte se pode salvar. NÃO salvou ainda: só salve com 'confirm' "
            "depois do 'sim' dele.")


def pendente(agora: float | None = None) -> dict | None:
    agora = agora if agora is not None else time.monotonic()
    with _trava:
        if _pendente and agora - _pendente["criada"] <= VALIDADE_S:
            return dict(_pendente)
        return None


def cancelar() -> str:
    global _pendente
    with _trava:
        tinha = _pendente is not None
        _pendente = None
    return "Descartei a rotina que eu tinha montado." if tinha else "Não havia nenhuma rotina esperando confirmação."


def confirmar(agora: float | None = None) -> str:
    global _pendente
    from actions import smart_routines as SR
    p = pendente(agora)
    if p is None:
        return "[failed] Não há rotina esperando confirmação (ela expira em 5 minutos). Monte de novo."
    with SR._LOCK, _trava:
        data = SR._load()
        if p["nome"] not in data and len(data) >= SR.MAX_ROUTINES:
            return "[failed] O limite de rotinas foi atingido; apague uma antes."
        item = {"steps": p["steps"], "description": p["descricao"] or "criada por conversa"}
        if p["agenda"]:
            item["agenda"] = p["agenda"]
        data[p["nome"]] = item
        SR._save(data)
        _pendente = None
    return (f"Salvei a rotina “{p['nome']}”, que roda {descrever_agenda(p['agenda'])}."
            if p["agenda"] else f"Salvei a rotina “{p['nome']}”: diga o nome dela para rodar.")


# ── rodar na hora marcada ───────────────────────────────────────────────────
def devidas(agora: float | None = None, dados: dict | None = None) -> list[str]:
    """Nomes das rotinas agendadas que estão na hora e ainda não rodaram hoje."""
    from actions import smart_routines as SR
    agora = agora if agora is not None else time.time()
    d = datetime.fromtimestamp(agora)
    hoje = d.date().isoformat()
    minutos = d.hour * 60 + d.minute
    saida = []
    for nome, r in (dados if dados is not None else SR._load()).items():
        ag = r.get("agenda") if isinstance(r, dict) else None
        if not ag or d.weekday() not in ag.get("dias", []) or r.get("ultima") == hoje:
            continue
        try:
            h, m = (int(x) for x in ag["hora"].split(":"))
        except Exception:
            continue
        if 0 <= minutos - (h * 60 + m) <= JANELA_MIN:
            saida.append(nome)
    return saida


def marcar_executada(nome: str, agora: float | None = None) -> None:
    from actions import smart_routines as SR
    hoje = datetime.fromtimestamp(agora if agora is not None else time.time()).date().isoformat()
    with SR._LOCK:
        data = SR._load()
        if nome in data:
            data[nome]["ultima"] = hoje
            SR._save(data)


def agendadas() -> list[dict]:
    from actions import smart_routines as SR
    return [{"nome": n, "quando": descrever_agenda(r.get("agenda"))}
            for n, r in SR._load().items() if isinstance(r, dict) and r.get("agenda")]
