"""core/isa_autonomia.py — auto-regeneração com mais autonomia (NEXUS Ultra 2026 3.9).

O que a 3.4 já fazia (restaurar arquivo, disjuntor, limpar disco) continua. Aqui entram dois remédios novos que resolvem sozinhos:

1. TAREFAS DE FUNDO QUE MORREM. Antes: depois de 4 falhas seguidas a tarefa (lembretes, e-mail, presença…) desistia até reiniciar o NEXUS.
   Agora ela dorme (30 min, depois 2 h) e tenta de novo, no máximo 3 "ciclos de descanso" por hora do dia; tudo registrado.
2. MISSÕES TRAVADAS. Uma missão "executando" sem nenhuma atividade há 20+ minutos (e fora de uma espera marcada) é religada.

Nível de autonomia (config `isa_autonomia`): "avisar" (só conta o que viu) ou "seguros" (padrão: aplica estes remédios, que são
reversíveis e não tocam nos seus dados). Nada aqui apaga, envia, instala ou gasta. Toda ação vai para a auditoria.
"""
from __future__ import annotations

import time
from pathlib import Path
from core.protecao import engolida as _engolida

NIVEIS = ("avisar", "seguros")
DESCANSOS_S = (1800, 7200)           # 1º e 2º descanso de uma tarefa que desistiu
MAX_CICLOS = 3
LIMITE_PARADA_S = 20 * 60

_tarefas: dict[str, dict] = {}


def nivel() -> str:
    try:
        from memory.config_manager import load_api_keys
        v = str(load_api_keys().get("isa_autonomia", "seguros")).lower()
        return v if v in NIVEIS else "seguros"
    except Exception:
        return "seguros"


def definir_nivel(v: str) -> str:
    v = str(v).strip().lower()
    if v not in NIVEIS:
        raise ValueError("Nível inválido. Use: " + ", ".join(NIVEIS))
    from memory.config_manager import _save_flag
    _save_flag("isa_autonomia", v)
    return v


# ── tarefas de fundo ─────────────────────────────────────────────────────────
def tarefa_caiu(nome: str, tentativa: int, agora: float | None = None) -> float | None:
    """Chamado quando a tarefa `nome` falhou na `tentativa`-ésima vez seguida. Devolve quantos segundos esperar antes de
    recomeçar, ou None se deve desistir de vez (nível 'avisar', ou os 3 ciclos de descanso já foram usados)."""
    agora = time.time() if agora is None else agora
    t = _tarefas.setdefault(nome, {"ciclos": 0, "falhas": 0, "ultima": 0})
    t["falhas"] += 1
    t["ultima"] = agora
    if tentativa <= 4:
        return 5.0 * tentativa                                   # o comportamento de sempre
    if nivel() != "seguros" or t["ciclos"] >= MAX_CICLOS:
        _aud(f"tarefa '{nome}' desistiu depois de {t['falhas']} falhas", "autonomia desligada ou ciclos esgotados")
        return None
    espera = DESCANSOS_S[min(t["ciclos"], len(DESCANSOS_S) - 1)]
    t["ciclos"] += 1
    _aud(f"tarefa '{nome}' descansa {int(espera / 60)} min e tenta de novo (ciclo {t['ciclos']}/{MAX_CICLOS})", "auto-regeneração")
    return float(espera)


def tarefa_ok(nome: str) -> None:
    if nome in _tarefas:
        _tarefas[nome]["falhas"] = 0


def estado_tarefas() -> dict[str, dict]:
    return {k: dict(v) for k, v in _tarefas.items()}


# ── missões travadas ─────────────────────────────────────────────────────────
def missoes_travadas(pasta: Path | None = None, agora: float | None = None, limite_s: int = LIMITE_PARADA_S) -> list[str]:
    from core import missoes as M
    agora = time.time() if agora is None else agora
    out = []
    for m in M.todas(pasta):
        if m["estado"] != "executando":
            continue
        if any(p["estado"] in ("esperando", "aguardando_decisao") for p in m["plano"]):
            continue                                              # espera marcada ou decisão sua: não é travamento
        ultima = max([m["criada"]] + [e.get("t", 0) for e in m.get("log", [])])
        if agora - ultima > limite_s:
            out.append(m["id"])
    return out


def religar_missoes(iniciar, pasta: Path | None = None, agora: float | None = None) -> list[str]:
    """`iniciar(mid)` religa a thread da missão. Respeita o nível. Devolve frases do que fez."""
    feitos = []
    for mid in missoes_travadas(pasta, agora):
        if nivel() != "seguros":
            feitos.append(f"a missão {mid} parece travada (nível 'avisar': não mexi)")
            continue
        try:
            iniciar(mid)
            feitos.append(f"religuei a missão {mid}, que estava parada")
            _aud(f"religou a missão {mid}", "sem atividade há mais de 20 minutos")
        except Exception as e:
            feitos.append(f"não consegui religar a missão {mid}: {str(e)[:60]}")
    return feitos


def _aud(o_que: str, motivo: str) -> None:
    try:
        from core import auditoria
        auditoria.registrar("sistema", "isa_autonomia", o_que, motivo=motivo)
    except Exception:
        _engolida("core/isa_autonomia.py:108")


def saude() -> tuple[bool, str]:
    t = estado_tarefas()
    return True, f"nível {nivel()}; {sum(v['ciclos'] for v in t.values())} descanso(s) usado(s)"
