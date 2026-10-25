"""Lista de compras — o NEXUS Ultra 2026 2.2 anota o que falta em casa.

Por voz:  "põe leite, pão e 2 dúzias de ovos na lista de compras"
          "o que falta comprar?"        "comprei o leite"        "tira o pão da lista"
          "limpa o que já comprei"      "lista da farmácia: dipirona"   (outras listas, com nome)

Diferença para as outras funções: tarefas = coisas a FAZER; compras = coisas a COMPRAR, em
listas com nome (mercado, farmácia, feira…), com quantidade, marcadas como "comprado".

Arquivo: memory/compras.json  (lista de {id, item, qtd, lista, comprado, criado}).
"""
from __future__ import annotations

import re
from datetime import datetime

from core import armazem

_ARQ = armazem.PASTA_MEMORIA / "compras.json"
_LISTA_PADRAO = "mercado"
_QTD = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(?:x\s+|un\w*\s+|de\s+)?(.+)$", re.IGNORECASE)


def _ler() -> list[dict]:
    return [i for i in armazem.carregar(_ARQ, []) if isinstance(i, dict) and i.get("item")]


def _separar(texto: str) -> list[str]:
    """'leite, pão e 2 ovos' → ['leite', 'pão', '2 ovos']."""
    partes = re.split(r"\s*(?:,|;|\n|\se\s)\s*", str(texto or ""))
    return [p.strip(" .") for p in partes if p.strip(" .")]


def _nome_lista(valor) -> str:
    v = str(valor or "").strip()
    return v.lower()[:40] if v else _LISTA_PADRAO


def adicionar(texto: str, lista: str = "", qtd: str = "") -> list[dict]:
    """Acrescenta um ou vários itens. Item repetido na mesma lista soma a quantidade."""
    itens = _ler()
    lista = _nome_lista(lista)
    novos = []
    for bruto in _separar(texto)[:30]:
        q = str(qtd or "").strip()
        m = _QTD.match(bruto)
        nome = bruto
        if m and not q:
            q, nome = m.group(1), m.group(2).strip()
        nome = nome[:80]
        if not nome:
            continue
        igual = next((i for i in itens if i["lista"] == lista and not i.get("comprado")
                      and armazem.norm(i["item"]) == armazem.norm(nome)), None)
        if igual:
            if q:
                igual["qtd"] = _somar(igual.get("qtd", ""), q)
            novos.append(igual)
            continue
        it = {"id": armazem.novo_id(itens), "item": nome, "qtd": q, "lista": lista,
              "comprado": False, "criado": datetime.now().isoformat(timespec="seconds")}
        itens.append(it)
        novos.append(it)
    if novos:
        armazem.salvar(_ARQ, itens)
    return novos


def _somar(a: str, b: str) -> str:
    try:
        return f"{float(str(a).replace(',', '.')) + float(str(b).replace(',', '.')):g}"
    except ValueError:
        return str(b) or str(a)


def _fmt(i: dict, n: int | None = None) -> str:
    q = f"{i['qtd']} " if i.get("qtd") else ""
    pref = f"{n}. " if n else ""
    return f"{pref}{q}{i['item']}"


def _abertos(lista: str) -> list[dict]:
    return [i for i in _ler() if not i.get("comprado") and (not lista or i["lista"] == lista)]


def compras(parameters: dict, player=None) -> str:
    acao = str(parameters.get("action") or "list").strip().lower()
    lista = parameters.get("list_name") or ""
    alvo_lista = _nome_lista(lista) if lista else ""

    if acao in ("add", "adicionar"):
        novos = adicionar(parameters.get("items") or parameters.get("item") or "", lista,
                          parameters.get("quantity") or "")
        if not novos:
            return "Diga o que devo anotar na lista de compras."
        nome = novos[0]["lista"]
        return f"Anotei na lista {nome}: " + ", ".join(_fmt(i) for i in novos) + "."

    if acao in ("list", "listar"):
        itens = _abertos(alvo_lista)
        if not itens:
            return "Sua lista de compras está vazia." if not alvo_lista else f"A lista {alvo_lista} está vazia."
        if alvo_lista:
            return f"Lista {alvo_lista} ({len(itens)}): " + " | ".join(_fmt(i, n) for n, i in enumerate(itens, 1))
        grupos: dict[str, list[dict]] = {}
        for i in itens:
            grupos.setdefault(i["lista"], []).append(i)
        return " || ".join(f"{nome} ({len(g)}): " + " | ".join(_fmt(i, n) for n, i in enumerate(g, 1))
                           for nome, g in grupos.items())

    if acao in ("lists", "listas"):
        nomes: dict[str, int] = {}
        for i in _abertos(""):
            nomes[i["lista"]] = nomes.get(i["lista"], 0) + 1
        return ("Listas com itens: " + ", ".join(f"{n} ({q})" for n, q in nomes.items()) + "."
                ) if nomes else "Você não tem nenhuma lista com itens."

    if acao in ("bought", "comprei", "done", "unbought"):
        marcar = acao != "unbought"
        todos = _ler()
        base = [i for i in todos if bool(i.get("comprado")) != marcar and (not alvo_lista or i["lista"] == alvo_lista)]
        it, erro = armazem.achar(parameters.get("target"), base, "item")
        if not it:
            return erro
        it["comprado"] = marcar
        armazem.salvar(_ARQ, todos)
        restam = len(_abertos(it["lista"]))
        if not marcar:
            return f"Voltei {it['item']} para a lista."
        return f"Marquei como comprado: {it['item']}. " + (f"Faltam {restam} na lista {it['lista']}." if restam else
                                                          f"A lista {it['lista']} está completa!")

    if acao in ("remove", "delete", "apagar"):
        todos = _ler()
        base = [i for i in todos if not alvo_lista or i["lista"] == alvo_lista]
        it, erro = armazem.achar(parameters.get("target"), base, "item")
        if not it:
            return erro
        armazem.salvar(_ARQ, [i for i in todos if i is not it])
        return f"Tirei da lista: {it['item']}."

    if acao in ("clear_bought", "limpar_comprados"):
        todos = _ler()
        resto = [i for i in todos if not i.get("comprado") or (alvo_lista and i["lista"] != alvo_lista)]
        armazem.salvar(_ARQ, resto)
        return f"Tirei {len(todos) - len(resto)} item(ns) já comprado(s)."

    return "Ação desconhecida. Use add, list, lists, bought, unbought, remove ou clear_bought."


TOOL = {
    "name": "compras",
    "description": (
        "SHOPPING LISTS (things to BUY — not to-do tasks). action=add with items (several at once, "
        "separated by commas or 'e', quantity may come first: '2 ovos') and optional list_name "
        "(default 'mercado'; others: farmácia, feira…); action=list (optionally for one list_name), "
        "lists (names of lists with items); action=bought / unbought with target = number or part of "
        "the item name; action=remove; action=clear_bought. Use for 'põe leite na lista de compras', "
        "'o que falta comprar?', 'comprei o pão'."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "add | list | lists | bought | unbought | remove | clear_bought"},
            "items": {"type": "STRING", "description": "For add: one or more items, e.g. 'leite, pão e 2 ovos'"},
            "quantity": {"type": "STRING", "description": "For add: quantity when it applies to a single item"},
            "list_name": {"type": "STRING", "description": "Which list (default 'mercado')"},
            "target": {"type": "STRING", "description": "For bought/unbought/remove: list number or part of the item name"},
        },
        "required": ["action"],
    },
    "handler": compras,
}
