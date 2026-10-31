"""core/hibrido.py — modelo local/híbrido com roteador (NEXUS Ultra 2026 3.8).

Decide, para cada pedido de TEXTO (planejar missão, resumir, redigir), se vai para o modelo local (Ollama/LM Studio, no
seu PC) ou para a nuvem, por sensibilidade, complexidade, conexão e modo. Dado sensível NUNCA vai para a nuvem no modo
automático. A voz ao vivo continua na nuvem (o modelo de voz em tempo real não roda local). Cada decisão vai à auditoria.
Modos: auto | privado (só local) | rapido | economico (local quando der) | offline (só local).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from core.protecao import engolida as _engolida

ARQUIVO = Path(__file__).resolve().parent.parent / "config" / "hibrido.json"
MODOS = ("auto", "privado", "rapido", "economico", "offline")
_SENSIVEL = re.compile(
    r"\b(senha|password|cpf|rg|cart[aã]o|cvv|token|api[_ -]?key|chave privada|pix|conta banc|saldo|extrato|"
    r"diagn[oó]stico|exame|receita m[eé]dica|rem[eé]dio|laudo|processo judicial|advogado|contrato|"
    r"sal[aá]rio|imposto de renda|segredo)\b", re.I)
_PADRAO_SEGREDO = re.compile(r"(\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b|\b(?:\d[ -]?){13,19}\b|AIza[0-9A-Za-z_-]{20,}|sk-[A-Za-z0-9]{20,})")
_COMPLEXO = re.compile(r"\b(analis|compar|planej|estrat[eé]g|c[oó]digo|programa|refator|pesquis|resum[ae] (o|a|os|as) (documento|artigo|livro|relat)|"
                       r"escreva (um|uma) (artigo|relat|ensaio)|passo a passo|raciocin)", re.I)


def modo(arq: Path | None = None) -> str:
    try:
        m = json.loads(Path(arq or ARQUIVO).read_text(encoding="utf-8")).get("modo", "auto")
        return m if m in MODOS else "auto"
    except Exception:
        return "auto"


def definir_modo(m: str, arq: Path | None = None) -> str:
    m = str(m).strip().lower()
    if m not in MODOS:
        raise ValueError("Modo inválido. Válidos: " + ", ".join(MODOS))
    arq = Path(arq or ARQUIVO)
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps({"modo": m}), encoding="utf-8")
    return m


def sensivel(texto: str) -> bool:
    return bool(_SENSIVEL.search(texto or "") or _PADRAO_SEGREDO.search(texto or ""))


def complexo(texto: str) -> bool:
    t = texto or ""
    return len(t) > 1200 or bool(_COMPLEXO.search(t))


def local_disponivel(timeout: float = 1.5) -> bool:
    """Pergunta ao servidor local (Ollama/LM Studio) se está de pé. Nunca levanta erro."""
    try:
        import requests
        from core import llm_client as L
        url, _ = L.get_llm_settings()
        rota = "/v1/models" if L.get_llm_provider() == "openai" else "/api/tags"
        return requests.get(url.rstrip("/") + rota, timeout=timeout).ok
    except Exception:
        return False


def rotear(texto: str, online: bool, local_ok: bool, modo_atual: str = "auto") -> dict:
    """-> {destino: local|nuvem|nenhum, motivo}. Pura (sem rede), por isso testável."""
    s, c = sensivel(texto), complexo(texto)
    if modo_atual in ("privado", "offline"):
        return {"destino": "local" if local_ok else "nenhum", "motivo": f"modo {modo_atual}"
                + ("" if local_ok else ": o modelo local não está rodando")}
    if not online:
        return {"destino": "local" if local_ok else "nenhum", "motivo": "sem internet"
                + ("" if local_ok else " e sem modelo local")}
    if s:
        return {"destino": "local" if local_ok else "nenhum",
                "motivo": "conteúdo sensível fica no PC" + ("" if local_ok else " (e o modelo local não está rodando)")}
    if modo_atual == "economico" and local_ok and not c:
        return {"destino": "local", "motivo": "modo econômico, pedido simples"}
    if modo_atual == "rapido":
        return {"destino": "nuvem", "motivo": "modo rápido"}
    if local_ok and not c and len(texto or "") < 400:
        return {"destino": "local", "motivo": "pedido simples e rápido no PC"}
    return {"destino": "nuvem", "motivo": "pedido complexo" if c else "padrão"}


def completar(texto: str, nuvem, local, online: bool | None = None, local_ok: bool | None = None,
              modo_atual: str | None = None, auditar: bool = True) -> tuple[str, dict]:
    """Roda `nuvem(texto)` ou `local(texto)` conforme a rota; se um falhar tenta o outro SÓ quando permitido
    (conteúdo sensível nunca cai para a nuvem). Devolve (resposta, rota)."""
    m = modo_atual or modo()
    ok_local = local_disponivel() if local_ok is None else local_ok
    rota = rotear(texto, True if online is None else online, ok_local, m)
    if rota["destino"] == "nenhum":
        return "", rota
    ordem = [rota["destino"]]
    pode_nuvem = rota["destino"] == "local" and m not in ("privado", "offline") and not sensivel(texto) \
        and (True if online is None else online)
    if pode_nuvem:
        ordem.append("nuvem")
    if rota["destino"] == "nuvem" and ok_local:
        ordem.append("local")
    resp = ""
    for d in ordem:
        try:
            resp = (local if d == "local" else nuvem)(texto) or ""
        except Exception:
            resp = ""
        if resp:
            rota = dict(rota, usado=d)
            break
    if auditar:
        try:
            from core import auditoria
            auditoria.registrar("modelo", "hibrido", f"texto de {len(texto or '')} caracteres → {rota.get('usado', 'falhou')}",
                                motivo=rota["motivo"], modelo=rota.get("usado", ""))
        except Exception:
            _engolida("core/hibrido.py:116")
    return resp, rota
