"""Auditoria verificável (3.8) — um registro do que o NEXUS fez, por quê, com que dados e qual modelo.

Cada linha de memory/auditoria.jsonl leva o hash SHA-256 da linha anterior: apagar, trocar ou reordenar qualquer linha
quebra a corrente e `verificar()` aponta onde. Dá para perguntar "por que você fez isso?" (`explicar`).

O que NÃO entra: chaves, senhas, tokens e corpo de mensagens/e-mails (só um resumo curto e o tamanho). O arquivo fica só
neste PC (fora do GitHub). Registrar nunca derruba quem chamou: qualquer erro aqui é engolido.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import unicodedata
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent.parent / "memory" / "auditoria.jsonl"
MAX_LINHAS = 20000
_TRAVA = threading.RLock()
_SEGREDO = re.compile(r"(key|token|password|senha|secret|passphrase|frase|authorization|cookie)", re.I)
_VALOR_SEGREDO = re.compile(r"(?:AIza[0-9A-Za-z_\-]{20,}|sk-[A-Za-z0-9_\-]{20,}|ghp_[A-Za-z0-9]{30,}|xox[baprs]-[A-Za-z0-9\-]{10,}|AKIA[0-9A-Z]{16})")
_CORPO = re.compile(r"^(body|text|message|content|corpo|texto|mensagem|html)$", re.I)
GENESE = "0" * 64


def _enxugar(v, nivel: int = 0):
    """Parâmetros prontos para guardar: sem segredos, textos longos viram resumo com tamanho."""
    if nivel > 3:
        return "…"
    if isinstance(v, dict):
        out = {}
        for k, x in list(v.items())[:25]:
            if _SEGREDO.search(str(k)):
                out[str(k)] = "[oculto]"
            elif _CORPO.match(str(k)) and isinstance(x, str):
                out[str(k)] = f"[texto de {len(x)} caracteres: {_VALOR_SEGREDO.sub('[oculto]', x)[:40]!r}…]"
            else:
                out[str(k)] = _enxugar(x, nivel + 1)
        return out
    if isinstance(v, (list, tuple)):
        return [_enxugar(x, nivel + 1) for x in list(v)[:15]]
    if isinstance(v, str):
        v = _VALOR_SEGREDO.sub("[oculto]", v)                                   # chave de API no meio do texto também some
        return v if len(v) <= 160 else v[:160] + f"…(+{len(v) - 160})"
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    return str(v)[:80]


def _hash(prev: str, corpo: dict) -> str:
    return hashlib.sha256((prev + json.dumps(corpo, sort_keys=True, ensure_ascii=False)).encode("utf-8")).hexdigest()


def _ultimo_hash(arq: Path) -> str:
    try:
        with open(arq, "rb") as f:
            f.seek(0, 2)
            tam = f.tell()
            f.seek(max(0, tam - 8192))
            linhas = f.read().splitlines()
        for bruta in reversed(linhas):
            try:
                return json.loads(bruta.decode("utf-8"))["h"]
            except Exception:
                continue
    except OSError:
        pass
    return GENESE


def registrar(tipo: str, ator: str, o_que: str, params=None, motivo: str = "", modelo: str = "",
              resultado: str = "", missao: str = "", arq: Path | None = None, agora: float | None = None) -> str:
    """Grava uma linha. `tipo`: acao | decisao | simulacao | modelo | sistema. Devolve o hash (ou '' se falhou)."""
    arq = Path(arq or ARQUIVO)
    try:
        with _TRAVA:
            corpo = {"t": round(agora if agora is not None else time.time(), 3), "tipo": str(tipo)[:20],
                     "ator": str(ator)[:40], "o_que": str(o_que)[:120], "params": _enxugar(params or {}),
                     "motivo": str(motivo)[:300], "modelo": str(modelo)[:60], "resultado": str(resultado)[:240],
                     "missao": str(missao)[:20]}
            prev = _ultimo_hash(arq)
            h = _hash(prev, dict(corpo, prev=prev))
            arq.parent.mkdir(parents=True, exist_ok=True)
            with open(arq, "a", encoding="utf-8") as f:
                f.write(json.dumps(dict(corpo, prev=prev, h=h), ensure_ascii=False) + "\n")
            return h
    except Exception:
        return ""


def ler(limite: int = 50, arq: Path | None = None) -> list[dict]:
    arq = Path(arq or ARQUIVO)
    try:
        linhas = arq.read_text(encoding="utf-8").splitlines()[-max(1, limite):]
    except OSError:
        return []
    out = []
    for l in linhas:
        try:
            out.append(json.loads(l))
        except ValueError:
            continue
    return out


def verificar(arq: Path | None = None) -> tuple[bool, str]:
    """(íntegro?, mensagem). Confere a corrente inteira do começo ao fim."""
    arq = Path(arq or ARQUIVO)
    if not arq.is_file():
        return True, "Nenhum registro ainda."
    prev, n = GENESE, 0
    with open(arq, "r", encoding="utf-8") as f:
        for i, linha in enumerate(f, 1):
            if not linha.strip():
                continue
            try:
                d = json.loads(linha)
                h = d.pop("h")
            except Exception:
                return False, f"Linha {i} ilegível: o registro foi alterado."
            if d.get("prev") != prev and n > 0:
                return False, f"A corrente quebra na linha {i}: uma linha antes dela foi apagada ou trocada."
            if _hash(d.get("prev", ""), d) != h:
                return False, f"A linha {i} foi adulterada (o hash não confere)."
            prev, n = h, n + 1
    return True, f"Registro íntegro: {n} linha(s) conferidas."


def _sem(t: str) -> str:
    return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()


def descrever(d: dict) -> str:
    quando = time.strftime("%d/%m %H:%M", time.localtime(d.get("t", 0)))
    base = f"{quando} — {d.get('ator')} {d.get('o_que')}"
    if d.get("motivo"):
        base += f" porque {d['motivo']}"
    if d.get("modelo"):
        base += f" (modelo {d['modelo']})"
    if d.get("resultado"):
        base += f" → {d['resultado']}"
    return base


def explicar(consulta: str = "", limite: int = 5, arq: Path | None = None) -> str:
    """'Por que você fez isso?' — as ações mais recentes que combinam com a consulta (ou as últimas)."""
    itens = [d for d in ler(400, arq) if d.get("tipo") in ("acao", "decisao", "simulacao")]
    q = [p for p in re.findall(r"\w{3,}", _sem(consulta)) if p not in ("voce", "isso", "fez", "por", "que", "porque")]
    if q:
        pont = []
        for d in itens:
            alvo = _sem(f"{d.get('o_que')} {d.get('params')} {d.get('motivo')} {d.get('resultado')}")
            s = sum(p in alvo for p in q)
            if s:
                pont.append((s, d["t"], d))
        itens = [d for _, _, d in sorted(pont, key=lambda x: (-x[0], -x[1]))]
    else:
        itens = list(reversed(itens))
    if not itens:
        return "Não encontrei nada no registro sobre isso."
    return "\n".join(descrever(d) for d in itens[:limite])


def aparar(arq: Path | None = None, maximo: int = MAX_LINHAS) -> int:
    """Mantém só as últimas linhas; a corrente recomeça a partir da primeira que sobra (o `prev` dela vale como âncora)."""
    arq = Path(arq or ARQUIVO)
    with _TRAVA:
        try:
            linhas = arq.read_text(encoding="utf-8").splitlines()
        except OSError:
            return 0
        if len(linhas) <= maximo:
            return 0
        sobra = linhas[-maximo:]
        arq.write_text("\n".join(sobra) + "\n", encoding="utf-8")
        return len(linhas) - maximo


def consultar(q: str = "", tipo: str = "", missao: str = "", dias: float = 0, limite: int = 60,
              arq: Path | None = None, agora: float | None = None) -> list[dict]:
    """Linha do tempo filtrada para o painel: texto livre, tipo, missão e janela de dias. Mais novo primeiro."""
    itens = ler(2000, arq)
    corte = ((agora if agora is not None else time.time()) - dias * 86400) if dias else 0
    termos = [p for p in re.findall(r"\w{2,}", _sem(q))]
    out = []
    for d in reversed(itens):
        if tipo and d.get("tipo") != tipo:
            continue
        if missao and d.get("missao") != missao:
            continue
        if corte and d.get("t", 0) < corte:
            continue
        if termos:
            alvo = _sem(f"{d.get('o_que')} {d.get('params')} {d.get('motivo')} {d.get('resultado')} {d.get('ator')}")
            if not all(t in alvo for t in termos):
                continue
        out.append({"t": d.get("t"), "tipo": d.get("tipo"), "ator": d.get("ator"), "missao": d.get("missao", ""),
                    "texto": descrever(d), "h": str(d.get("h", ""))[:8]})
        if len(out) >= max(1, min(limite, 300)):
            break
    return out
