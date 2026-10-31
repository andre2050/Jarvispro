"""Registro de auditoria: cada ação do assistente vira uma linha em memory/audit.log.

2.1 — cada linha ganhou "ms" (quanto a ferramenta demorou) e o arquivo gira quando passa de
2 MB (audit.log → audit.log.1). Antes ele crescia para sempre. O "diagnóstico" lê estas linhas
para dizer o que falhou e o que anda lento."""
from __future__ import annotations
from core.pt_time import agora

import json
from pathlib import Path
from core.protecao import engolida as _engolida

_FILE = Path(__file__).resolve().parent.parent / "memory" / "audit.log"
MAX_BYTES = 2 * 1024 * 1024


def _girar(arquivo: Path) -> None:
    """audit.log grande demais → vira audit.log.1 (o antigo .1 é descartado)."""
    try:
        if arquivo.exists() and arquivo.stat().st_size > MAX_BYTES:
            velho = arquivo.with_name(arquivo.name + ".1")
            velho.unlink(missing_ok=True)
            arquivo.rename(velho)
    except OSError:
        pass


def record(tool: str, args: dict, result, ms: int | None = None) -> None:
    try:
        from core import preferences as P
        if not P.get("audit_enabled"):
            return
        linha = {"ts": agora().strftime("%Y-%m-%d %H:%M:%S"), "tool": tool,
                 "args": args, "result": str(result)[:300]}
        if ms is not None:
            linha["ms"] = int(ms)
        _FILE.parent.mkdir(parents=True, exist_ok=True)
        _girar(_FILE)
        with _FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(linha, ensure_ascii=False) + "\n")
    except Exception:
        _engolida("core/audit.py:41")   # auditing must never break a tool call


def ler(arquivo: Path | None = None, limite: int = 5000) -> list[dict]:
    """As últimas `limite` linhas válidas do registro (a mais antiga primeiro)."""
    arq = Path(arquivo) if arquivo else _FILE
    saida: list[dict] = []
    try:
        with arq.open("r", encoding="utf-8", errors="replace") as f:
            linhas = f.readlines()[-limite:]
    except OSError:
        return saida
    for l in linhas:
        try:
            d = json.loads(l)
            if isinstance(d, dict) and d.get("tool"):
                saida.append(d)
        except ValueError:
            continue
    return saida
