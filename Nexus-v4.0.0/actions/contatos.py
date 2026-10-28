"""Contatos e aniversários — o NEXUS Ultra 2026 2.2 lembra de quem importa para você.

Por voz:  "salva o contato Marcos, telefone 11 98888-7777, aniversário 12 de março"
          "qual o telefone da Maria?"          "quem faz aniversário essa semana?"
          "muda o e-mail do Marcos para marcos@exemplo.com"      "apaga o contato do Marcos"

Os contatos ficam só no seu PC. O NEXUS só ANOTA e consulta: quem manda a mensagem ou liga é a
função de mensagens, que continua pedindo a sua confirmação.

Arquivo: memory/contatos.json  (lista de {id, nome, telefone, email, aniversario, notas}).
Aniversário guardado como "MM-DD" (ou "AAAA-MM-DD" quando você diz o ano, para calcular a idade).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from core import armazem

_ARQ = armazem.PASTA_MEMORIA / "contatos.json"
_MESES = ["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto",
          "setembro", "outubro", "novembro", "dezembro"]
_MESES_BONITOS = [m if m != "marco" else "março" for m in _MESES]


def _hoje() -> date:
    return datetime.now().date()


def _ler() -> list[dict]:
    itens = [c for c in armazem.carregar(_ARQ, []) if isinstance(c, dict) and c.get("nome")]
    return sorted(itens, key=lambda c: armazem.norm(c["nome"]))


def interpretar_data(valor) -> str:
    """'12/03', '12 de março', '12 de março de 1990', '1990-03-12' → 'MM-DD' ou 'AAAA-MM-DD' ('' se não entendeu)."""
    v = armazem.norm(valor)
    if not v:
        return ""
    ano = mes = dia = None
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", v)
    if m:
        ano, mes, dia = int(m[1]), int(m[2]), int(m[3])
    else:
        m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?", v)
        if m:
            dia, mes = int(m[1]), int(m[2])
            ano = int(m[3]) if m[3] else None
        else:
            m = re.fullmatch(r"(?:dia\s+)?(\d{1,2})\s*(?:de\s+)?([a-z]+)(?:\s+de\s+(\d{4}))?", v)
            if m and m[2] in _MESES:
                dia, mes = int(m[1]), _MESES.index(m[2]) + 1
                ano = int(m[3]) if m[3] else None
    if not (dia and mes):
        return ""
    if ano is not None and ano < 100:
        ano += 2000 if ano < 30 else 1900
    try:
        date(ano or 2000, mes, dia)                    # 2000 é bissexto: aceita 29/02
    except ValueError:
        return ""
    return f"{ano:04d}-{mes:02d}-{dia:02d}" if ano else f"{mes:02d}-{dia:02d}"


def proximo_aniversario(aniv: str, hoje: date | None = None) -> tuple[date, int | None] | None:
    """Próxima data (de hoje em diante) e a idade que a pessoa fará (None sem o ano)."""
    hoje = hoje or _hoje()
    partes = aniv.split("-")
    try:
        ano_nasc = int(partes[0]) if len(partes) == 3 else None
        mes, dia = int(partes[-2]), int(partes[-1])
    except (ValueError, IndexError):
        return None
    for ano in (hoje.year, hoje.year + 1):
        try:
            d = date(ano, mes, dia)
        except ValueError:                              # 29/02 em ano comum → 28/02
            d = date(ano, 2, 28)
        if d >= hoje:
            return d, (ano - ano_nasc if ano_nasc else None)
    return None


def _legivel(aniv: str) -> str:
    p = aniv.split("-")
    base = f"{int(p[-1])} de {_MESES_BONITOS[int(p[-2]) - 1]}"
    return base + (f" de {p[0]}" if len(p) == 3 else "")


def _resumo(c: dict) -> str:
    partes = [c["nome"]]
    if c.get("telefone"):
        partes.append(f"tel {c['telefone']}")
    if c.get("email"):
        partes.append(c["email"])
    if c.get("aniversario"):
        partes.append(f"aniversário {_legivel(c['aniversario'])}")
    if c.get("notas"):
        partes.append(c["notas"])
    return ", ".join(partes)


def _quando(d: date, hoje: date) -> str:
    n = (d - hoje).days
    return "hoje" if n == 0 else "amanhã" if n == 1 else f"em {n} dias ({d.day:02d}/{d.month:02d})"


def contatos(parameters: dict, player=None) -> str:
    acao = str(parameters.get("action") or "find").strip().lower()
    itens = _ler()
    hoje = _hoje()

    if acao in ("save", "add", "salvar", "update"):
        nome = str(parameters.get("name") or "").strip()[:80]
        if not nome:
            return "Diga o nome do contato."
        c = next((x for x in itens if armazem.norm(x["nome"]) == armazem.norm(nome)), None)
        novo = c is None
        if novo:
            c = {"id": armazem.novo_id(itens), "nome": nome, "telefone": "", "email": "",
                 "aniversario": "", "notas": ""}
            if len(itens) >= 2000:
                return "A agenda está cheia (2000 contatos)."
            itens.append(c)
        if parameters.get("phone"):
            c["telefone"] = str(parameters["phone"]).strip()[:30]
        if parameters.get("email"):
            email = str(parameters["email"]).strip()[:120]
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                return "Esse e-mail não parece válido. Confira e diga de novo."
            c["email"] = email
        if parameters.get("birthday"):
            a = interpretar_data(parameters["birthday"])
            if not a:
                return "Não entendi a data do aniversário. Diga, por exemplo, 12 de março."
            c["aniversario"] = a
        if parameters.get("notes"):
            c["notas"] = str(parameters["notes"]).strip()[:200]
        armazem.salvar(_ARQ, itens)
        return f"{'Salvei' if novo else 'Atualizei'} o contato: {_resumo(c)}."

    if acao in ("find", "buscar", "get"):
        q = parameters.get("name") or parameters.get("query") or ""
        if not str(q).strip():
            return "Diga o nome (ou parte dele) para eu procurar."
        achados = [c for c in itens if armazem.norm(q) in armazem.norm(c["nome"])
                   or armazem.norm(q) in armazem.norm(c.get("notas"))]
        if not achados:
            return f"Não achei ninguém com “{q}” nos seus contatos."
        return " | ".join(_resumo(c) for c in achados[:6]) + (f" (e mais {len(achados) - 6})" if len(achados) > 6 else "")

    if acao in ("list", "listar"):
        if not itens:
            return "Sua agenda de contatos está vazia."
        return f"{len(itens)} contato(s): " + ", ".join(c["nome"] for c in itens[:30]) + ("…" if len(itens) > 30 else "")

    if acao in ("birthdays", "aniversarios", "proximos"):
        try:
            dias = max(1, min(366, int(parameters.get("days") or 30)))
        except (TypeError, ValueError):
            dias = 30
        prox = []
        for c in itens:
            r = proximo_aniversario(c.get("aniversario") or "", hoje) if c.get("aniversario") else None
            if r and (r[0] - hoje).days <= dias:
                prox.append((r[0], r[1], c["nome"]))
        prox.sort()
        if not prox:
            return f"Ninguém faz aniversário nos próximos {dias} dias."
        return "Aniversários: " + " | ".join(
            f"{nome} {_quando(d, hoje)}" + (f" ({idade} anos)" if idade else "") for d, idade, nome in prox[:10])

    if acao in ("remove", "delete", "apagar"):
        c, erro = armazem.achar(parameters.get("name"), itens, "nome")
        if not c:
            return erro
        armazem.salvar(_ARQ, [x for x in itens if x is not c])
        return f"Apaguei o contato {c['nome']}."

    return "Ação desconhecida. Use save, find, list, birthdays ou remove."


def aniversariantes_de_hoje() -> list[str]:
    """Para o briefing da manhã: nomes de quem faz aniversário hoje."""
    hoje = _hoje()
    out = []
    for c in _ler():
        r = proximo_aniversario(c["aniversario"], hoje) if c.get("aniversario") else None
        if r and r[0] == hoje:
            out.append(c["nome"])
    return out


TOOL = {
    "name": "contatos",
    "description": (
        "The user's CONTACT BOOK and BIRTHDAYS (stored only on this PC; it does not call or message "
        "anyone). action=save with name (+ phone, email, birthday like '12 de março' or '12/03' or "
        "'12/03/1990', notes) — saving an existing name updates it; action=find with name (also searches "
        "notes) for 'qual o telefone da Maria?'; action=list; action=birthdays (+ days, default 30) for "
        "'quem faz aniversário essa semana?'; action=remove with name."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "save | find | list | birthdays | remove"},
            "name": {"type": "STRING", "description": "Contact name or part of it"},
            "phone": {"type": "STRING", "description": "For save: phone number"},
            "email": {"type": "STRING", "description": "For save: e-mail address"},
            "birthday": {"type": "STRING", "description": "For save: '12 de março', '12/03' or '12/03/1990'"},
            "notes": {"type": "STRING", "description": "For save: free note (who they are, where they work…)"},
            "days": {"type": "INTEGER", "description": "For birthdays: how many days ahead (default 30)"},
        },
        "required": ["action"],
    },
    "handler": contatos,
}
