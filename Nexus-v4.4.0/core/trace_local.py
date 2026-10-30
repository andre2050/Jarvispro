"""core/trace_local.py — trace local de ferramentas, missões e agentes (NEXUS Ultra 4.1).

Uma linha do tempo de TUDO que o NEXUS executou: quem pediu (você, missão, agente), qual ferramenta, quanto demorou, se deu certo e o que
mudou — com segredos mascarados e textos longos resumidos (mesma proteção da auditoria). Fica só no PC (memory/trace.jsonl, máx. 5000 linhas)
e nada é enviado para serviço de monitoramento nenhum. Serve para achar "por que essa missão demorou?" e "qual ferramenta falha mais?".
A auditoria (core/auditoria.py) é o registro à prova de adulteração do que foi DECIDIDO; o trace é o registro de DESEMPENHO e fluxo.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from core.auditoria import _VALOR_SEGREDO, _enxugar

ARQUIVO = Path(__file__).resolve().parent.parent / "memory" / "trace.jsonl"
MAX_LINHAS = 5000
_trava = threading.Lock()
_n = 0


def registrar(nome: str, ator: str = "", missao: str = "", dur_ms: float = 0.0, ok: bool = True, args=None, resultado: str = "",
              extra: str = "", arq=None, agora: float | None = None) -> None:
    """Nunca levanta erro: o trace não pode atrapalhar a ferramenta."""
    global _n
    try:
        linha = {"t": round(time.time() if agora is None else agora, 3), "nome": str(nome)[:40], "ator": str(ator or "nexus")[:20], "missao": str(missao)[:12],
                 "ms": round(float(dur_ms), 1), "ok": bool(ok), "args": _enxugar(args or {}), "res": _VALOR_SEGREDO.sub("[oculto]", str(resultado))[:160], "extra": str(extra)[:80]}
        a = Path(arq or ARQUIVO)
        with _trava:
            a.parent.mkdir(parents=True, exist_ok=True)
            with a.open("a", encoding="utf-8") as f:
                f.write(json.dumps(linha, ensure_ascii=False) + "\n")
            _n += 1
            if _n % 200 == 0:
                _aparar(a)
    except Exception:
        pass


def _aparar(a: Path, maximo: int = MAX_LINHAS) -> None:
    try:
        ls = a.read_text(encoding="utf-8").splitlines()
        if len(ls) > maximo:
            a.write_text("\n".join(ls[-maximo:]) + "\n", encoding="utf-8")
    except Exception:
        pass


def ler(arq=None) -> list[dict]:
    out = []
    try:
        for l in Path(arq or ARQUIVO).read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(l))
            except Exception:
                continue
    except OSError:
        pass
    return out


def linha_do_tempo(missao: str = "", minutos: float = 0, limite: int = 40, arq=None, agora: float | None = None) -> list[dict]:
    agora = time.time() if agora is None else agora
    ls = [e for e in ler(arq) if (not missao or e.get("missao") == missao) and (not minutos or agora - e["t"] <= minutos * 60)]
    return ls[-limite:]


def estatisticas(arq=None, minutos: float = 0, agora: float | None = None) -> dict:
    """Por ferramenta: chamadas, falhas, tempo médio e máximo."""
    agora = time.time() if agora is None else agora
    por: dict[str, dict] = {}
    for e in ler(arq):
        if minutos and agora - e["t"] > minutos * 60:
            continue
        s = por.setdefault(e["nome"], {"n": 0, "falhas": 0, "ms_total": 0.0, "ms_max": 0.0})
        s["n"] += 1
        s["falhas"] += 0 if e["ok"] else 1
        s["ms_total"] += e["ms"]
        s["ms_max"] = max(s["ms_max"], e["ms"])
    for s in por.values():
        s["ms_medio"] = round(s["ms_total"] / s["n"], 1)
    return por


def texto(missao: str = "", minutos: float = 60, arq=None, agora: float | None = None) -> str:
    tl = linha_do_tempo(missao, 0 if missao else minutos, 12, arq, agora)
    if not tl:
        return "Nada no trace nesse período."
    l = []
    for e in tl:
        h = time.strftime("%H:%M:%S", time.localtime(e["t"]))
        l.append(f"{h} {e['ator']}{('/' + e['missao']) if e['missao'] else ''} → {e['nome']} ({e['ms']:.0f} ms) {'✔' if e['ok'] else '✘ ' + e['res'][:50]}")
    st = estatisticas(arq, 0 if missao else minutos, agora)
    piores = sorted(((n, s) for n, s in st.items() if s["falhas"]), key=lambda x: -x[1]["falhas"])[:2]
    lentas = sorted(st.items(), key=lambda x: -x[1]["ms_medio"])[:2]
    if piores:
        l.append("Mais falham: " + ", ".join(f"{n} ({s['falhas']}/{s['n']})" for n, s in piores) + ".")
    if lentas:
        l.append("Mais lentas: " + ", ".join(f"{n} (~{s['ms_medio']:.0f} ms)" for n, s in lentas) + ".")
    return "\n".join(l)


def saude() -> tuple[bool, str]:
    return True, f"{len(ler())} registro(s) de trace"
