"""core/estatisticas_pc.py — estatísticas completas do PC e sugestões de otimização (NEXUS Ultra 2026 3.9).

CPU por núcleo, memória/swap, discos, rede, processos que mais pesam (somados por nome), tempo ligado, bateria e temperatura quando o
sistema informa. As sugestões são regras simples e explicáveis; nada é fechado ou apagado por aqui — só diz o que vê.
`coletar(psu=…)` aceita um módulo de sensores injetado (testes).
"""
from __future__ import annotations

import time
from core.protecao import engolida as _engolida


def _gb(b) -> float:
    return round(b / 1024 ** 3, 1)


def coletar(psu=None, agora: float | None = None, top: int = 5) -> dict:
    if psu is None:
        import psutil as psu
    d: dict = {}
    d["cpu_total"] = psu.cpu_percent(interval=0.3)
    d["cpu_nucleos"] = list(psu.cpu_percent(interval=None, percpu=True))
    m, s = psu.virtual_memory(), psu.swap_memory()
    d["mem"] = {"usada_gb": _gb(m.used), "total_gb": _gb(m.total), "pct": m.percent}
    d["swap"] = {"usada_gb": _gb(s.used), "total_gb": _gb(s.total), "pct": s.percent}
    discos = []
    try:
        for p in psu.disk_partitions(all=False):
            try:
                u = psu.disk_usage(p.mountpoint)
                discos.append({"ponto": p.mountpoint, "livre_gb": _gb(u.free), "total_gb": _gb(u.total), "pct": u.percent})
            except Exception:
                _engolida("core/estatisticas_pc.py:32")
    except Exception:
        _engolida("core/estatisticas_pc.py:34")
    d["discos"] = discos[:8]
    try:
        n = psu.net_io_counters()
        d["rede_mb"] = {"enviado": round(n.bytes_sent / 1e6), "recebido": round(n.bytes_recv / 1e6)}
    except Exception:
        d["rede_mb"] = None
    try:
        d["ligado_h"] = round(((time.time() if agora is None else agora) - psu.boot_time()) / 3600, 1)
    except Exception:
        d["ligado_h"] = None
    try:
        b = psu.sensors_battery()
        d["bateria"] = {"pct": round(b.percent), "carregando": bool(b.power_plugged)} if b else None
    except Exception:
        d["bateria"] = None
    try:
        t = psu.sensors_temperatures()
        v = [x.current for lst in t.values() for x in lst if getattr(x, "current", None)]
        d["temp_max"] = round(max(v)) if v else None
    except Exception:
        d["temp_max"] = None
    por_nome: dict[str, dict] = {}
    try:
        for p in psu.process_iter(["name", "memory_info", "cpu_percent"]):
            i = p.info
            nome = (i.get("name") or "?")[:40]
            mi = i.get("memory_info")
            e = por_nome.setdefault(nome, {"nome": nome, "mem_mb": 0, "cpu": 0.0, "n": 0})
            e["mem_mb"] += round((mi.rss if mi else 0) / 1e6)
            e["cpu"] += float(i.get("cpu_percent") or 0)
            e["n"] += 1
    except Exception:
        _engolida("core/estatisticas_pc.py:67")
    d["top_mem"] = sorted(por_nome.values(), key=lambda x: -x["mem_mb"])[:top]
    return d


def sugestoes(d: dict) -> list[str]:
    s = []
    if d["mem"]["pct"] >= 85:
        t = d["top_mem"][0] if d.get("top_mem") else None
        s.append(f"Memória em {d['mem']['pct']:.0f}%." + (f" O que mais pesa é {t['nome']} ({t['mem_mb']} MB, {t['n']} processo(s)); fechar ajuda." if t else ""))
    if d["swap"]["total_gb"] and d["swap"]["pct"] >= 50:
        s.append(f"Está usando bastante a memória de disco ({d['swap']['pct']:.0f}%): o PC fica lento; feche programas ou considere mais RAM.")
    if d["cpu_total"] >= 85:
        s.append(f"Processador em {d['cpu_total']:.0f}%: veja se algo travou ou está rodando sem precisar.")
    for x in d.get("discos", []):
        if x["pct"] >= 90 or x["livre_gb"] < 5:
            s.append(f"O disco {x['ponto']} está quase cheio (livre {x['livre_gb']} GB): posso listar o que ocupa espaço ou limpar temporários.")
    if d.get("ligado_h") and d["ligado_h"] >= 24 * 7:
        s.append(f"O PC está ligado há {d['ligado_h'] / 24:.0f} dias; reiniciar costuma ajudar a liberar memória e aplicar atualizações.")
    b = d.get("bateria")
    if b and not b["carregando"] and b["pct"] <= 20:
        s.append(f"Bateria em {b['pct']}% e fora da tomada.")
    if d.get("temp_max") and d["temp_max"] >= 85:
        s.append(f"Temperatura alta ({d['temp_max']} °C): confira a ventilação.")
    return s


def texto(d: dict) -> str:
    nuc = d["cpu_nucleos"]
    l = [f"CPU {d['cpu_total']:.0f}% ({len(nuc)} núcleos, o mais ocupado a {max(nuc) if nuc else 0:.0f}%).",
         f"Memória {d['mem']['usada_gb']}/{d['mem']['total_gb']} GB ({d['mem']['pct']:.0f}%)."]
    if d["swap"]["total_gb"]:
        l.append(f"Swap {d['swap']['usada_gb']}/{d['swap']['total_gb']} GB.")
    for x in d.get("discos", [])[:3]:
        l.append(f"Disco {x['ponto']}: {x['livre_gb']} GB livres de {x['total_gb']}.")
    if d.get("top_mem"):
        l.append("Mais pesados: " + ", ".join(f"{p['nome']} {p['mem_mb']} MB" for p in d["top_mem"][:3]) + ".")
    if d.get("ligado_h") is not None:
        l.append(f"Ligado há {d['ligado_h']} h.")
    if d.get("bateria"):
        l.append(f"Bateria {d['bateria']['pct']}%{' (carregando)' if d['bateria']['carregando'] else ''}.")
    if d.get("temp_max"):
        l.append(f"Temperatura máx. {d['temp_max']} °C.")
    sug = sugestoes(d)
    l.append("Sugestões: " + " ".join(sug) if sug else "Está tudo tranquilo, sem nada a otimizar.")
    return " ".join(l)


def saude() -> tuple[bool, str]:
    try:
        import psutil  # noqa: F401
        return True, "ok"
    except Exception:
        return False, "psutil ausente"
