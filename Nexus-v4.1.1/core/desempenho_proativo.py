"""core/desempenho_proativo.py — desempenho proativo (NEXUS Ultra 4.0).

Em vez de esperar você perguntar "por que o PC está lento?", o NEXUS amostra os processos de tempos em tempos e AVISA quando algo
pesa de verdade e por tempo suficiente:
  • CPU: um programa usando ≥ 40% do processador (já dividido pelos núcleos) em 4 amostras seguidas;
  • memória: um programa com ≥ 25% da RAM, ou que cresceu ≥ 400 MB sem parar na janela (suspeita de vazamento);
  • RAM do PC ≥ 90% por 4 amostras.
Cada aviso diz o QUE é, quanto pesa e uma sugestão específica; nunca fecha nada sozinho. O mesmo programa só é avisado de novo depois de 2 h;
programas do sistema são ignorados; em modo foco/ocupado fica quieto. `leitor()` devolve {"cpu_pct","mem_pct","nucleos","procs":[{nome,cpu,mem_mb}]}.
"""
from __future__ import annotations

import time
from collections import deque

JANELA = 6
SEGUIDAS = 4
LIMITE_CPU = 40.0
LIMITE_MEM_PCT = 25.0
CRESCEU_MB = 400
LIMITE_RAM_PC = 90.0
NOVO_AVISO_S = 2 * 3600
_IGNORAR = {"system", "system idle process", "registry", "memcompression", "dwm.exe", "csrss.exe", "wininit.exe", "services.exe", "lsass.exe",
            "svchost.exe", "smss.exe", "idle", "kernel_task", "systemd", "kthreadd"}
_DICAS = {
    "chrome": "feche abas e extensões que não usa (o gerenciador de tarefas do Chrome mostra qual pesa)",
    "msedge": "feche abas que não usa ou ative as guias em suspensão",
    "firefox": "feche abas que não usa",
    "code": "feche janelas/extensões do editor que não precisa",
    "teams": "feche o Teams quando não estiver em reunião",
    "discord": "feche o Discord ou desligue a aceleração de hardware",
    "onedrive": "pause a sincronização por um tempo",
    "python": "pode ser um programa seu em Python; veja se não ficou em laço",
}
_amostras: deque = deque(maxlen=JANELA)
_avisados: dict[str, float] = {}


def limpar() -> None:
    _amostras.clear()
    _avisados.clear()


def ler_psutil() -> dict:
    import psutil
    n = psutil.cpu_count() or 1
    procs = []
    for p in psutil.process_iter(["name", "cpu_percent", "memory_info"]):
        i = p.info
        procs.append({"nome": (i.get("name") or "?")[:40], "cpu": float(i.get("cpu_percent") or 0.0), "mem_mb": round((i["memory_info"].rss if i.get("memory_info") else 0) / 1e6)})
    return {"cpu_pct": psutil.cpu_percent(None), "mem_pct": psutil.virtual_memory().percent, "nucleos": n,
            "ram_mb": psutil.virtual_memory().total / 1e6, "procs": procs}


def _por_nome(l: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for p in l.get("procs", []):
        if p["nome"].lower() in _IGNORAR:
            continue
        e = out.setdefault(p["nome"], {"cpu": 0.0, "mem_mb": 0})
        e["cpu"] += p["cpu"] / max(1, l.get("nucleos", 1))
        e["mem_mb"] += p["mem_mb"]
    return out


def amostrar(leitor=None, agora: float | None = None) -> None:
    l = (leitor or ler_psutil)()
    _amostras.append({"t": time.time() if agora is None else agora, "pc_mem": l.get("mem_pct", 0), "ram_mb": l.get("ram_mb") or 0, "p": _por_nome(l)})


def _dica(nome: str) -> str:
    b = nome.lower().removesuffix(".exe")
    for k, v in _DICAS.items():
        if k in b:
            return v
    return "veja se precisa dele aberto; posso listar e, com o seu sim, fechar"


def avisos(agora: float | None = None) -> list[str]:
    agora = time.time() if agora is None else agora
    a = list(_amostras)
    out = []
    if len(a) < SEGUIDAS:
        return out
    ult = a[-SEGUIDAS:]
    try:                                                # 4.0 — proatividade aprendida: poucos avisos úteis → intervalo maior
        from core import adaptacao
        espaco = NOVO_AVISO_S * adaptacao.fator_cooldown()
    except Exception:
        espaco = NOVO_AVISO_S
    nomes = set(ult[-1]["p"])
    candidatos: list[tuple[float, str, str]] = []
    for n in nomes:
        if n in _avisados and agora - _avisados[n] < espaco:
            continue
        cpus = [x["p"].get(n, {}).get("cpu", 0.0) for x in ult]
        if min(cpus) >= LIMITE_CPU:
            candidatos.append((sum(cpus) / len(cpus), n, f"{n} está usando cerca de {sum(cpus) / len(cpus):.0f}% do processador há um tempo; {_dica(n)}."))
            continue
        mems = [x["p"].get(n, {}).get("mem_mb", 0) for x in a if n in x["p"]]
        ram = ult[-1]["ram_mb"]
        if ram and mems[-1] / ram * 100 >= LIMITE_MEM_PCT:
            candidatos.append((mems[-1], n, f"{n} ocupa {mems[-1] / 1000:.1f} GB ({mems[-1] / ram * 100:.0f}% da memória); {_dica(n)}."))
        elif len(mems) >= SEGUIDAS and all(y >= x for x, y in zip(mems, mems[1:])) and mems[-1] - mems[0] >= CRESCEU_MB:
            candidatos.append((mems[-1] - mems[0], n, f"{n} só cresce na memória (+{mems[-1] - mems[0]} MB na janela): pode estar com vazamento; reiniciar esse programa resolve."))
    for _, n, msg in sorted(candidatos, reverse=True)[:2]:
        _avisados[n] = agora
        out.append(msg)
    if not out and all(x["pc_mem"] >= LIMITE_RAM_PC for x in ult) and ("__ram__" not in _avisados or agora - _avisados["__ram__"] >= espaco):
        _avisados["__ram__"] = agora
        top = sorted(ult[-1]["p"].items(), key=lambda kv: -kv[1]["mem_mb"])[:2]
        out.append(f"A memória do PC está em {ult[-1]['pc_mem']:.0f}%. Os que mais pesam: " + ", ".join(f"{n} ({e['mem_mb'] / 1000:.1f} GB)" for n, e in top) + ".")
    return out


def passo(ocupado: bool = False, leitor=None, agora: float | None = None) -> list[str]:
    """Uma rodada: amostra e devolve os avisos novos (vazio se você está ocupado/em foco)."""
    try:
        amostrar(leitor, agora)
        return [] if ocupado else avisos(agora)
    except Exception:
        return []


def saude() -> tuple[bool, str]:
    return True, f"{len(_amostras)} amostra(s), {len(_avisados)} aviso(s) recente(s)"
