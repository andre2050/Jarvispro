"""
core/reconexoes.py — o diário das quedas de conexão com o Gemini (NEXUS Ultra 2026 2.3).

"Ele fala normal, desconecta e conecta sozinho": para achar a causa de verdade é preciso saber
QUANDO caiu, depois de QUANTO TEMPO conectado, POR QUÊ e se a conversa foi mantida. Cada queda
e cada renovação ganha uma linha em memory/reconexoes.log (JSON por linha, só no seu PC, chaves
removidas). A ação `diagnostico` lê este arquivo e mostra o padrão.
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent.parent / "memory" / "reconexoes.log"
_MAX_LINHAS = 400
_TRAVA = threading.Lock()
_SEGREDO = re.compile(r"AIza[0-9A-Za-z_\-]{20,}|sk-[A-Za-z0-9_\-]{20,}|key=[^&\s'\"]+", re.IGNORECASE)


def folhas(exc: BaseException) -> list[BaseException]:
    """Os erros de verdade dentro de um ExceptionGroup (TaskGroup embrulha tudo em grupo)."""
    sub = getattr(exc, "exceptions", None)
    if sub:
        out: list[BaseException] = []
        for e in sub:
            out.extend(folhas(e))
        return out
    return [exc]


def descrever(exc: BaseException) -> tuple[str, str]:
    """(tipo, mensagem curta e sem segredos) do erro mais relevante."""
    fs = folhas(exc)
    # CancelledError é só consequência de outra tarefa ter falhado: prefira o erro que causou
    reais = [e for e in fs if type(e).__name__ != "CancelledError"] or fs
    e = reais[0]
    msg = _SEGREDO.sub("[chave]", " ".join(str(e).split()))[:220]
    return type(e).__name__, msg


def classificar(tipo: str, msg: str) -> str:
    """Um rótulo curto para a causa provável."""
    t = f"{tipo} {msg}".lower()
    if "_reconnectsignal" in t or "reconnectsignal" in t:
        return "pedido do app"
    if "goaway" in t or "go_away" in t:
        return "servidor avisou (GoAway)"
    if any(k in t for k in ("api key", "api_key")):
        return "chave"
    if any(k in t for k in ("1011", "internal error", "deadline", "unavailable", "503", "500 ")):
        return "erro do servidor"
    if any(k in t for k in ("keepalive", "ping timeout", "1006", "connectionclosed", "no close frame")):
        return "conexão perdida (rede)"
    if any(k in t for k in ("timeout", "timed out", "getaddrinfo", "connect call failed")):
        return "rede / sem internet"
    if any(k in t for k in ("429", "quota", "resource_exhausted")):
        return "cota"
    if "1007" in t or "invalid_argument" in t:
        return "pedido recusado (1007)"
    return "outro"


def registrar(evento: str, tipo: str = "", msg: str = "", conectado_s: float | None = None,
              manteve_conversa: bool | None = None, acordado: bool | None = None) -> None:
    linha = {"quando": time.strftime("%Y-%m-%d %H:%M:%S"), "evento": evento, "tipo": tipo,
             "causa": classificar(tipo, msg), "msg": msg,
             "conectado_s": None if conectado_s is None else round(conectado_s, 1),
             "manteve_conversa": manteve_conversa, "acordado": acordado}
    try:
        with _TRAVA:
            ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
            linhas = []
            if ARQUIVO.exists():
                linhas = ARQUIVO.read_text(encoding="utf-8").splitlines()[-(_MAX_LINHAS - 1):]
            linhas.append(json.dumps(linha, ensure_ascii=False))
            ARQUIVO.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    except Exception:
        pass


def ler(ultimas: int = 50) -> list[dict]:
    try:
        itens = []
        for l in ARQUIVO.read_text(encoding="utf-8").splitlines()[-ultimas:]:
            try:
                itens.append(json.loads(l))
            except Exception:
                continue
        return itens
    except Exception:
        return []


def resumo(ultimas: int = 50) -> str:
    itens = [i for i in ler(ultimas) if i.get("evento") != "conectou"]
    if not itens:
        return "Nenhuma queda ou renovação registrada ainda."
    por_causa: dict[str, int] = {}
    perdeu = 0
    for i in itens:
        por_causa[i["causa"]] = por_causa.get(i["causa"], 0) + 1
        if i.get("manteve_conversa") is False:
            perdeu += 1
    duracoes = [i["conectado_s"] for i in itens if i.get("conectado_s")]
    med = f", conexão dura em média {sum(duracoes) / len(duracoes) / 60:.1f} min" if duracoes else ""
    causas = ", ".join(f"{c} ×{n}" for c, n in sorted(por_causa.items(), key=lambda x: -x[1]))
    ultimo = itens[-1]
    return (f"{len(itens)} reconexão(ões) recentes: {causas}{med}. "
            f"Em {perdeu} a conversa NÃO foi mantida. Última: {ultimo['quando']} — {ultimo['causa']}"
            f"{' (' + ultimo['msg'][:80] + ')' if ultimo.get('msg') else ''}.")


# ── decisões puras (sem rede nem Qt: testáveis) ──────────────────────────────
RENOVAR_APOS_S = 8.5 * 60          # a partir daqui renova assim que ficar calmo
RENOVAR_FORCADA_S = 9.3 * 60       # a partir daqui renova mesmo sem calma (o servidor derruba ~10 min)
ESPERA_FORCADA_S = 10.0
CONVERSA_VIVA_S = 10 * 60


def deve_renovar(idade_s: float, tem_handle: bool, calmo: bool,
                 goaway_definido: bool, goaway_estourou: bool) -> bool:
    """Hora de trocar a conexão por uma nova (mantendo a conversa)?"""
    if not goaway_definido and (idade_s < RENOVAR_APOS_S or not tem_handle):
        return False
    if goaway_estourou:
        return True
    if tem_handle and idade_s >= RENOVAR_FORCADA_S + ESPERA_FORCADA_S:
        return True
    return calmo


def seguir_acordado(estava_acordado: bool, conectou_antes: bool, segundos_desde_a_fala: float) -> bool:
    """Depois de reconectar no meio de uma conversa, o NEXUS continua acordado."""
    return bool(estava_acordado and conectou_antes and segundos_desde_a_fala < CONVERSA_VIVA_S)


def conversa_acabou(saindo: bool, segundos_desde_a_fala: float) -> bool:
    """Só resume a conversa quando ela terminou de verdade (não a cada queda)."""
    return bool(saindo or segundos_desde_a_fala > CONVERSA_VIVA_S)
