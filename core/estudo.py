"""Estudo (4.5.0): cartões com repetição espaçada (método SM-2) e quiz de múltipla escolha.

    "cria um cartão: capital da França :: Paris"          "o que devo revisar hoje?"
    "faz um quiz de 5 perguntas"                          "como estou indo nos estudos?"

Repetição espaçada: acertou, o cartão volta daqui a 1 dia, depois 6, depois cada vez mais longe; errou,
volta amanhã. Arquivo: memory/estudo.json. O quiz sorteia as erradas de outros cartões do mesmo baralho.
"""
from __future__ import annotations

import random
import re
from datetime import date, timedelta
from pathlib import Path

from core import armazem

_ARQ = armazem.PASTA_MEMORIA / "estudo.json"
BARALHO_PADRAO = "geral"
MAX_CARTOES = 3000
_SEPARADOR = re.compile(r"\s*(?:::|\||=>|;;)\s*")


def _vazio() -> dict:
    return {"cartoes": [], "historico": []}


def carregar(arquivo: Path | None = None) -> dict:
    d = armazem.carregar(Path(arquivo or _ARQ), _vazio())
    if not isinstance(d, dict):
        return _vazio()
    d["cartoes"] = [c for c in d.get("cartoes", []) if isinstance(c, dict) and c.get("p") and c.get("r")]
    d["historico"] = d.get("historico", []) if isinstance(d.get("historico"), list) else []
    return d


def salvar(dado: dict, arquivo: Path | None = None) -> None:
    dado["historico"] = dado.get("historico", [])[-200:]
    armazem.salvar(Path(arquivo or _ARQ), dado)


def _nome_baralho(v) -> str:
    v = str(v or "").strip().lower()
    return v[:40] if v else BARALHO_PADRAO


def adicionar(dado: dict, pergunta: str, resposta: str, baralho: str = "", hoje: date | None = None) -> dict:
    pergunta, resposta = str(pergunta or "").strip()[:300], str(resposta or "").strip()[:500]
    if not pergunta or not resposta:
        raise ValueError("Preciso da pergunta e da resposta.")
    if len(dado["cartoes"]) >= MAX_CARTOES:
        raise ValueError("Limite de cartões atingido.")
    b = _nome_baralho(baralho)
    for c in dado["cartoes"]:
        if c["baralho"] == b and armazem.norm(c["p"]) == armazem.norm(pergunta):
            c["r"] = resposta
            return c
    hoje = hoje or date.today()
    c = {"id": armazem.novo_id(dado["cartoes"]), "p": pergunta, "r": resposta, "baralho": b, "facilidade": 2.5,
         "intervalo": 0, "repeticoes": 0, "proxima": hoje.isoformat(), "acertos": 0, "erros": 0}
    dado["cartoes"].append(c)
    return c


def importar(dado: dict, texto: str, baralho: str = "", hoje: date | None = None) -> int:
    """Uma linha por cartão: 'pergunta :: resposta' (também aceita | ou =>). Devolve quantos entraram."""
    n = 0
    for linha in str(texto or "").splitlines():
        partes = _SEPARADOR.split(linha.strip(), maxsplit=1)
        if len(partes) == 2 and partes[0] and partes[1]:
            try:
                adicionar(dado, partes[0], partes[1], baralho, hoje)
                n += 1
            except ValueError:
                break
    return n


def avaliar(c: dict, nota: int, hoje: date | None = None) -> dict:
    """SM-2. nota: 0 = não lembrei nada … 5 = lembrei fácil. Menos de 3 conta como erro."""
    nota = max(0, min(5, int(nota)))
    hoje = hoje or date.today()
    if nota < 3:
        c["repeticoes"], c["intervalo"] = 0, 1
        c["erros"] = c.get("erros", 0) + 1
    else:
        c["repeticoes"] += 1
        c["intervalo"] = 1 if c["repeticoes"] == 1 else 6 if c["repeticoes"] == 2 else max(1, round(c["intervalo"] * c["facilidade"]))
        c["acertos"] = c.get("acertos", 0) + 1
    c["facilidade"] = round(max(1.3, c["facilidade"] + 0.1 - (5 - nota) * (0.08 + (5 - nota) * 0.02)), 3)
    c["proxima"] = (hoje + timedelta(days=c["intervalo"])).isoformat()
    return c


def devidos(dado: dict, baralho: str = "", hoje: date | None = None) -> list[dict]:
    hoje = (hoje or date.today()).isoformat()
    b = _nome_baralho(baralho) if baralho else ""
    lista = [c for c in dado["cartoes"] if c["proxima"] <= hoje and (not b or c["baralho"] == b)]
    return sorted(lista, key=lambda c: (c["proxima"], c["id"]))


def achar(dado: dict, alvo) -> dict | None:
    alvo = str(alvo or "").strip()
    if alvo.isdigit():
        return next((c for c in dado["cartoes"] if c["id"] == int(alvo)), None)
    n = armazem.norm(alvo)
    return next((c for c in dado["cartoes"] if n and n in armazem.norm(c["p"])), None)


def remover(dado: dict, alvo) -> bool:
    c = achar(dado, alvo)
    if not c:
        return False
    dado["cartoes"].remove(c)
    return True


def estatisticas(dado: dict, hoje: date | None = None) -> dict:
    cs = dado["cartoes"]
    acertos, erros = sum(c.get("acertos", 0) for c in cs), sum(c.get("erros", 0) for c in cs)
    return {"cartoes": len(cs), "para_hoje": len(devidos(dado, "", hoje)), "dominados": sum(1 for c in cs if c["intervalo"] >= 21),
            "baralhos": sorted({c["baralho"] for c in cs}), "acerto": round(acertos / (acertos + erros), 2) if acertos + erros else None}


# ── quiz ──────────────────────────────────────────────────────────────────────

def montar_quiz(dado: dict, quantas: int = 5, baralho: str = "", rnd: random.Random | None = None, hoje: date | None = None) -> list[dict]:
    """Perguntas de múltipla escolha com os cartões que mais precisam de revisão primeiro."""
    rnd = rnd or random.Random()
    b = _nome_baralho(baralho) if baralho else ""
    pool = [c for c in dado["cartoes"] if not b or c["baralho"] == b]
    if len(pool) < 2:
        raise ValueError("Preciso de pelo menos 2 cartões para montar um quiz.")
    ordem = devidos({"cartoes": pool}, "", hoje) + [c for c in pool if c not in devidos({"cartoes": pool}, "", hoje)]
    escolhidas = ordem[:max(1, min(int(quantas or 5), 20))]
    perguntas = []
    for c in escolhidas:
        erradas = list({o["r"] for o in pool if armazem.norm(o["r"]) != armazem.norm(c["r"])})
        rnd.shuffle(erradas)
        opcoes = [c["r"]] + erradas[:3]
        rnd.shuffle(opcoes)
        perguntas.append({"id": c["id"], "pergunta": c["p"], "opcoes": opcoes, "correta": opcoes.index(c["r"])})
    return perguntas


LETRAS = "ABCD"


def formatar_pergunta(q: dict, numero: int, total: int) -> str:
    ops = "  ".join(f"{LETRAS[i]}) {o}" for i, o in enumerate(q["opcoes"]))
    return f"Pergunta {numero} de {total}: {q['pergunta']} {ops}"


def ler_escolha(resposta, q: dict) -> int | None:
    """Aceita 'B', 'b', '2', 'a segunda' não — só letra, número ou o texto da opção."""
    r = str(resposta or "").strip()
    if not r:
        return None
    if len(r) == 1 and r.upper() in LETRAS[:len(q["opcoes"])]:
        return LETRAS.index(r.upper())
    if r.isdigit() and 1 <= int(r) <= len(q["opcoes"]):
        return int(r) - 1
    n = armazem.norm(r)
    for i, o in enumerate(q["opcoes"]):
        if armazem.norm(o) == n:
            return i
    return None
