"""core/armazem.py — guardar listas pessoais em JSON sem corromper (NEXUS Pro 2.2).

Usado pelas funções novas (compras, hábitos, contatos, diário). Escreve num arquivo
temporário e troca de uma vez, então uma queda de energia no meio nunca deixa o
arquivo pela metade. Se o arquivo existir mas estiver estragado, ele é guardado
como ``.quebrado`` em vez de ser apagado pela próxima gravação.
"""
from __future__ import annotations

import json
import threading
import unicodedata
from pathlib import Path
from typing import Any

PASTA_MEMORIA = Path(__file__).resolve().parent.parent / "memory"
_TRAVA = threading.RLock()


def norm(texto: Any) -> str:
    """Minúsculas e sem acento: 'Água' → 'agua'."""
    t = unicodedata.normalize("NFKD", str(texto or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c)).strip()


def carregar(arquivo: Path, padrao: Any) -> Any:
    """Lê o JSON; devolve ``padrao`` (uma cópia nova) se faltar ou vier do tipo errado."""
    with _TRAVA:
        try:
            dado = json.loads(Path(arquivo).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return json.loads(json.dumps(padrao))
        except Exception:
            from core import protecao as _prot
            _prot.anotar(f"arquivo estragado: {Path(arquivo).name} (guardado como .quebrado)")
            try:                                    # estragado: guarda para o usuário poder recuperar
                p = Path(arquivo)
                p.replace(p.with_suffix(p.suffix + ".quebrado"))
            except Exception:
                _prot.anotar(f"não consegui guardar {Path(arquivo).name} como .quebrado — "
                             "a próxima gravação pode apagar o conteúdo antigo")
            return json.loads(json.dumps(padrao))
        if isinstance(dado, type(padrao)):
            return dado
        return json.loads(json.dumps(padrao))


def salvar(arquivo: Path, dado: Any) -> None:
    with _TRAVA:
        p = Path(arquivo)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(dado, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(p)


def novo_id(itens: list[dict]) -> int:
    return max((int(i.get("id", 0)) for i in itens if isinstance(i, dict)), default=0) + 1


def achar(alvo: Any, itens: list[dict], campo: str) -> tuple[dict | None, str]:
    """Acha um item pelo número da lista (1, 2…) ou por parte do nome. Devolve (item, erro)."""
    alvo = str(alvo or "").strip()
    if not alvo:
        return None, "Diga qual: o número da lista ou parte do nome."
    if alvo.isdigit():
        n = int(alvo)
        if 1 <= n <= len(itens):
            return itens[n - 1], ""
        return None, f"Não há o número {n}. Peça a lista primeiro."
    exatos = [i for i in itens if norm(i.get(campo)) == norm(alvo)]
    if len(exatos) == 1:
        return exatos[0], ""
    achados = [i for i in itens if norm(alvo) in norm(i.get(campo))]
    if len(achados) == 1:
        return achados[0], ""
    if not achados:
        return None, "Não encontrei. Peça a lista e diga o número."
    return None, "Mais de um combina: " + " | ".join(str(i.get(campo)) for i in achados[:4]) + ". Diga o número."
