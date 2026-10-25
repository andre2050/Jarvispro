"""Cache de respostas de ferramentas de LEITURA (Ultra 2026 3.3).

Perguntar o clima três vezes em dez minutos não precisa de três consultas à internet: a segunda e a
terceira saem do cache, na hora. Só entram aqui ferramentas que apenas CONSULTAM (clima, notícias),
com um prazo de validade curto; nada que escreva, envie, abra ou mude algo no computador.

  • a chave é a ferramenta + os argumentos (outra cidade = outra resposta);
  • só guarda resposta que deu certo (erro nunca fica no cache);
  • vale por TTL curto (clima 10 min, notícias 15 min) e some quando o NEXUS fecha;
  • "de novo" / "atualiza" com refresh=true ignora o cache.

Nunca levanta erro para quem chama.
"""
from __future__ import annotations

import json
import threading
import time

TTL_S: dict[str, float] = {"weather_report": 600.0, "noticias": 900.0}
MAX_ENTRADAS = 64
_FALHAS = ("Tool '", "Action '", "Failed", "Could not", "No application", "Unsupported", "[failed]",
           "Search failed", "No results", "Error", "Erro")

_trava = threading.RLock()
_dados: dict[str, tuple[float, str]] = {}
_stats = {"acertos": 0, "faltas": 0}


def _chave(ferramenta: str, args: dict) -> str:
    try:
        return ferramenta + "|" + json.dumps(args or {}, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        return ferramenta + "|" + str(args)


def cacheavel(ferramenta: str, args: dict | None = None) -> bool:
    return ferramenta in TTL_S and not bool((args or {}).get("refresh") or (args or {}).get("force"))


def obter(ferramenta: str, args: dict | None = None, agora: float | None = None) -> str | None:
    """A resposta guardada (ainda válida) ou None."""
    try:
        if not cacheavel(ferramenta, args):
            return None
        agora = agora if agora is not None else time.monotonic()
        with _trava:
            item = _dados.get(_chave(ferramenta, args or {}))
            if item and agora - item[0] <= TTL_S[ferramenta]:
                _stats["acertos"] += 1
                return item[1]
            _stats["faltas"] += 1
            return None
    except Exception:
        return None


def guardar(ferramenta: str, args: dict | None, resposta, agora: float | None = None) -> bool:
    try:
        if ferramenta not in TTL_S or not isinstance(resposta, str) or not resposta.strip():
            return False
        if resposta.lstrip().startswith(_FALHAS):
            return False
        agora = agora if agora is not None else time.monotonic()
        with _trava:
            if len(_dados) >= MAX_ENTRADAS:
                vencido = min(_dados, key=lambda k: _dados[k][0])
                _dados.pop(vencido, None)
            _dados[_chave(ferramenta, args or {})] = (agora, resposta)
        return True
    except Exception:
        return False


def estatisticas() -> dict:
    with _trava:
        total = _stats["acertos"] + _stats["faltas"]
        return {"acertos": _stats["acertos"], "faltas": _stats["faltas"], "entradas": len(_dados),
                "taxa": (_stats["acertos"] / total) if total else None}


def limpar() -> None:
    with _trava:
        _dados.clear()
        _stats.update(acertos=0, faltas=0)
