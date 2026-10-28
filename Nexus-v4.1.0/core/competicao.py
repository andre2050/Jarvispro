"""core/competicao.py — módulos competitivos e seleção dinâmica (NEXUS Ultra 2026 4.0).

Uma "capacidade" (ex.: buscar no histórico) pode ter várias VARIANTES que fazem a mesma coisa de jeitos diferentes. A cada uso o NEXUS
escolhe uma, mede (deu certo? quanto demorou? o resultado passou na validação?) e vai ficando com a que se sai melhor — sem você mexer
no código. Regras:
  • toda variante nova é testada pelo menos {MIN_TESTES} vezes antes de ser julgada;
  • depois, 10% das vezes experimenta outra (para não ficar preso numa que piorou);
  • se a escolhida falhar, a próxima melhor assume na mesma chamada (o usuário não vê a falha);
  • restrição "rapido" pesa o tempo, "preciso" pesa o acerto, "equilibrado" os dois;
  • uma variante que erra todas as {MIN_TESTES} primeiras vezes, ou com acerto < 30% depois de 10 usos, é APOSENTADA (reversível: `reativar`); `fixar` força uma escolha manual.
Placar em memory/competicao.json (local). `aleatorio` e `relogio` são injetáveis nos testes.
"""
from __future__ import annotations

import json
import random
import threading
import time
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent.parent / "memory" / "competicao.json"
MIN_TESTES = 3
EXPLORAR = 0.10
APOSENTA_ACERTO = 0.30
APOSENTA_USOS = 10
_trava = threading.Lock()
_variantes: dict[str, dict[str, dict]] = {}          # capacidade → nome → {"fn", "valida"}


class SemVariante(Exception):
    pass


def registrar(capacidade: str, nome: str, fn, valida=None) -> None:
    _variantes.setdefault(capacidade, {})[nome] = {"fn": fn, "valida": valida}


def _ler(arq=None) -> dict:
    try:
        d = json.loads(Path(arq or ARQUIVO).read_text(encoding="utf-8"))
        if isinstance(d, dict):
            return d
    except Exception:
        pass
    return {}


def _gravar(d: dict, arq=None) -> None:
    arq = Path(arq or ARQUIVO)
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    tmp.replace(arq)


def _p(d: dict, cap: str, nome: str) -> dict:
    return d.setdefault(cap, {"fixada": "", "v": {}})["v"].setdefault(nome, {"n": 0, "ok": 0, "ms": 0.0, "aposentada": False})


def nota(p: dict, restricao: str = "equilibrado") -> float:
    acerto = (p["ok"] + 1) / (p["n"] + 2)                                   # Laplace: variante nova começa em 0,5
    lento = (p["ms"] / p["n"]) if p["n"] else 0.0
    rapidez = 1.0 / (1.0 + lento / 500.0)                                   # 0 ms → 1,0 · 500 ms → 0,5
    pesos = {"rapido": (0.3, 0.7), "preciso": (0.9, 0.1)}.get(restricao, (0.6, 0.4))
    return pesos[0] * acerto + pesos[1] * rapidez


def ranking(cap: str, restricao: str = "equilibrado", arq=None) -> list[tuple[str, float]]:
    d = _ler(arq)
    nomes = list(_variantes.get(cap, {}))
    vivos = [n for n in nomes if not _p(d, cap, n)["aposentada"]]
    return sorted(((n, round(nota(_p(d, cap, n), restricao), 3)) for n in vivos), key=lambda x: -x[1])


def escolher(cap: str, restricao: str = "equilibrado", arq=None, aleatorio=random.random) -> list[str]:
    """Ordem em que as variantes serão tentadas nesta chamada."""
    d = _ler(arq)
    if cap not in _variantes or not _variantes[cap]:
        raise SemVariante(f"Sem variantes para “{cap}”.")
    fix = d.get(cap, {}).get("fixada")
    rank = [n for n, _ in ranking(cap, restricao, arq)] or list(_variantes[cap])
    if fix and fix in _variantes[cap]:
        return [fix] + [n for n in rank if n != fix]
    novas = [n for n in rank if _p(d, cap, n)["n"] < MIN_TESTES]
    if novas:
        return novas[:1] + [n for n in rank if n != novas[0]]
    if len(rank) > 1 and aleatorio() < EXPLORAR:
        outra = rank[1 + int(aleatorio() * (len(rank) - 1)) % (len(rank) - 1)]
        return [outra] + [n for n in rank if n != outra]
    return rank


def executar(cap: str, *args, restricao: str = "equilibrado", arq=None, aleatorio=random.random, relogio=time.perf_counter, **kw):
    """Roda a melhor variante; se falhar (ou não passar na validação) cai para a próxima. Devolve (resultado, nome_da_variante)."""
    erros = []
    for nome in escolher(cap, restricao, arq, aleatorio):
        v = _variantes[cap][nome]
        t0 = relogio()
        ok, res = False, None
        try:
            res = v["fn"](*args, **kw)
            ok = bool(v["valida"](res)) if v["valida"] else res is not None
        except Exception as e:                                              # noqa: BLE001
            erros.append(f"{nome}: {type(e).__name__}")
        ms = (relogio() - t0) * 1000
        with _trava:
            d = _ler(arq)
            p = _p(d, cap, nome)
            p["n"] += 1
            p["ok"] += int(ok)
            p["ms"] += ms
            if ((p["ok"] == 0 and p["n"] >= MIN_TESTES) or (p["n"] >= APOSENTA_USOS and p["ok"] / p["n"] < APOSENTA_ACERTO)) and sum(1 for x in d[cap]["v"].values() if not x["aposentada"]) > 1:
                p["aposentada"] = True
            _gravar(d, arq)
        if ok:
            return res, nome
    raise SemVariante(f"Nenhuma variante de “{cap}” funcionou ({'; '.join(erros) or 'resultado inválido'}).")


def fixar(cap: str, nome: str = "", arq=None) -> str:
    if nome and nome not in _variantes.get(cap, {}):
        raise SemVariante("Variante desconhecida. Existem: " + ", ".join(_variantes.get(cap, {})))
    with _trava:
        d = _ler(arq)
        d.setdefault(cap, {"fixada": "", "v": {}})["fixada"] = nome
        _gravar(d, arq)
    return f"“{cap}” fixada em {nome}" if nome else f"“{cap}” volta à escolha automática"


def reativar(cap: str, nome: str, arq=None) -> None:
    with _trava:
        d = _ler(arq)
        p = _p(d, cap, nome)
        p.update({"aposentada": False, "n": 0, "ok": 0, "ms": 0.0})        # recomeça do zero, com os testes mínimos
        _gravar(d, arq)


def relatorio(arq=None) -> str:
    d = _ler(arq)
    if not _variantes:
        return "Nenhuma capacidade com variantes registrada."
    l = []
    for cap in _variantes:
        partes = []
        for n in _variantes[cap]:
            p = _p(d, cap, n)
            partes.append(f"{n}: " + ("aposentada" if p["aposentada"] else f"{p['ok']}/{p['n']} certos, {p['ms'] / p['n']:.0f} ms" if p["n"] else "sem testes"))
        fix = d.get(cap, {}).get("fixada")
        l.append(f"{cap}" + (f" [fixada em {fix}]" if fix else "") + " → " + "; ".join(partes))
    return " | ".join(l)


def saude() -> tuple[bool, str]:
    return True, f"{len(_variantes)} capacidade(s) com variantes"
