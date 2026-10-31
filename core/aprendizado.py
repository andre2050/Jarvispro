"""core/aprendizado.py — aprendizado contínuo da sua rotina, só neste PC (NEXUS Ultra 2026 3.9).

Opt-in (começa DESLIGADO). Ligado, ele lê os eventos que core/habits.py já guarda (só ferramentas seguras, argumentos cortados, sem
mensagens/senhas) e mantém apenas CONTAGENS por (ferramenta, dia útil/fim de semana, faixa de 3 h), com esquecimento gradual
(meia-vida ~30 dias) — nada de conteúdo, nada de rede. Dá para ver tudo (`resumo`), exportar e apagar (`esquecer`).
Daí saem sugestões do tipo "nas manhãs de dia útil você costuma abrir X". Quem age em cima é o usuário (smart_routines).
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime
from pathlib import Path
from core.protecao import engolida as _engolida

ARQUIVO = Path(__file__).resolve().parent.parent / "memory" / "aprendizado.json"
MEIA_VIDA_S = 30 * 86400
MIN_PESO = 3.0
MAX_CHAVES = 300


def _ler(arq=None) -> dict:
    try:
        d = json.loads(Path(arq or ARQUIVO).read_text(encoding="utf-8"))
        if isinstance(d, dict):
            return d
    except Exception:
        _engolida("core/aprendizado.py:28")
    return {"ligado": False, "contagens": {}, "visto_ate": 0.0, "atualizado": 0.0}


def _gravar(d: dict, arq=None) -> None:
    arq = Path(arq or ARQUIVO)
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    tmp.replace(arq)


def ligado(arq=None) -> bool:
    return bool(_ler(arq).get("ligado"))


def ligar(sim: bool, arq=None, agora: float | None = None) -> None:
    d = _ler(arq)
    d["ligado"] = bool(sim)
    if sim and not d.get("visto_ate"):
        d["visto_ate"] = float(agora if agora is not None else time.time())     # só aprende do momento do "ligar" em diante
    _gravar(d, arq)


def faixa(ts: float) -> str:
    dt = datetime.fromtimestamp(ts)
    tipo = "fim de semana" if dt.weekday() >= 5 else "dia útil"
    h = dt.hour // 3 * 3
    return f"{tipo}|{h:02d}-{h + 3:02d}h"


def atualizar(eventos: list[dict], arq=None, agora: float | None = None) -> int:
    """Soma eventos novos (t > visto_ate) às contagens, aplicando o esquecimento. Devolve quantos entraram."""
    d = _ler(arq)
    if not d.get("ligado"):
        return 0
    agora = float(agora if agora is not None else time.time())
    ant = d.get("atualizado") or agora
    fator = 0.5 ** (max(0.0, agora - ant) / MEIA_VIDA_S)
    cont = {k: v * fator for k, v in d.get("contagens", {}).items() if v * fator >= 0.05}
    novos, corte = 0, d.get("visto_ate", 0)
    for e in eventos:
        t, tool = e.get("t"), e.get("tool")
        if not isinstance(t, (int, float)) or not tool or t <= corte or t > agora:
            continue
        k = f"{tool}|{faixa(t)}"
        cont[k] = cont.get(k, 0.0) + 1.0
        d["visto_ate"] = max(d.get("visto_ate", 0), t)
        novos += 1
    if len(cont) > MAX_CHAVES:
        cont = dict(sorted(cont.items(), key=lambda kv: -kv[1])[:MAX_CHAVES])
    d["contagens"], d["atualizado"] = cont, agora
    _gravar(d, arq)
    return novos


def sugestoes(arq=None, agora: float | None = None, minimo: float = MIN_PESO) -> list[dict]:
    d = _ler(arq)
    agora = float(agora if agora is not None else time.time())
    fator = 0.5 ** (max(0.0, agora - (d.get("atualizado") or agora)) / MEIA_VIDA_S)
    out = []
    for k, v in d.get("contagens", {}).items():
        v *= fator
        if v >= minimo:
            tool, tipo, h = k.split("|")
            out.append({"tool": tool, "quando": f"{tipo}, {h}", "peso": round(v, 1)})
    return sorted(out, key=lambda x: -x["peso"])[:8]


def agora_costuma(arq=None, agora: float | None = None) -> list[str]:
    """Ferramentas que você costuma usar nesta faixa de horário (para o assistente se antecipar)."""
    agora = float(agora if agora is not None else time.time())
    f = faixa(agora)
    return [s["tool"] for s in sugestoes(arq, agora) if s["quando"] == f.replace("|", ", ")]


def resumo(arq=None, agora: float | None = None) -> str:
    d = _ler(arq)
    if not d.get("ligado"):
        return "O aprendizado da rotina está desligado. Ele só guarda contagens por horário, neste PC, e você pode apagar quando quiser."
    s = sugestoes(arq, agora)
    if not s:
        return "Aprendizado ligado; ainda não vi nada que se repita o bastante."
    return "Sua rotina até agora: " + "; ".join(f"{x['tool']} ({x['quando']}, peso {x['peso']})" for x in s)


def exportar(arq=None) -> str:
    d = _ler(arq)
    return json.dumps({"ligado": d.get("ligado"), "contagens": {k: round(v, 2) for k, v in d.get("contagens", {}).items()}}, ensure_ascii=False, indent=1)


def esquecer(arq=None) -> None:
    d = _ler(arq)
    _gravar({"ligado": d.get("ligado", False), "contagens": {}, "visto_ate": time.time(), "atualizado": time.time()}, arq)


def saude() -> tuple[bool, str]:
    return True, "ligado" if ligado() else "desligado (opt-in)"
