"""E-mails na memória de documentos (3.6) — opt-in, tudo guardado só no seu PC.

Como funciona: ao ligar, o NEXUS baixa os e-mails recentes da caixa de entrada (a mesma conta do leitor de
e-mail), grava cada um como um pequeno arquivo de texto em memory/emails_cache/ e o índice de documentos passa
a lê-los junto com as suas pastas. Resposta sempre com a fonte: “E-mail de Ana · Reunião · 12-10”.

Privacidade: nada sai do PC; só entra o que você liga; "esquecer e-mails" apaga o cache e o que foi indexado.
O texto de e-mail é de terceiros: a busca devolve-o marcado como não confiável (ver actions/memoria_semantica).
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import threading
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
CACHE = _BASE / "memory" / "emails_cache"
_INDICE = "_indice.json"
PREFIXO = "E-mail de "
MAX_EMAILS = 400
_TRAVA = threading.Lock()


def _limpo(t: str, n: int = 60) -> str:
    t = re.sub(r"[\\/:*?\"<>|\r\n\t]+", " ", str(t)).strip(" .")
    return re.sub(r"\s+", " ", t)[:n] or "sem assunto"


def ativo(cache: Path | None = None) -> bool:
    return (cache or CACHE).joinpath(_INDICE).is_file()


def _ler_indice(cache: Path) -> dict:
    try:
        return json.loads((cache / _INDICE).read_text(encoding="utf-8"))
    except Exception:
        return {"validade": 0, "uids": {}}


def _gravar_indice(cache: Path, ind: dict) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    (cache / _INDICE).write_text(json.dumps(ind, ensure_ascii=False), encoding="utf-8")


def ligar(cache: Path | None = None) -> None:
    cache = cache or CACHE
    cache.mkdir(parents=True, exist_ok=True)
    if not ativo(cache):
        _gravar_indice(cache, {"validade": 0, "uids": {}})


def _arquivo_de(m: dict) -> str:
    data = (m.get("date") or "").split(" ")[0].replace("/", "-")
    return f"{PREFIXO}{_limpo(m.get('from_name'), 30)} · {_limpo(m.get('subject'))} · {data or 's-d'} #{m.get('uid')}.txt"


def _texto_de(m: dict) -> str:
    return (f"De: {m.get('from_name')} <{m.get('from_addr')}>\nAssunto: {m.get('subject')}\n"
            f"Data: {m.get('date')}\n\n{m.get('body')}\n")


def sincronizar(dias: int = 90, maximo: int = 200, cache: Path | None = None, conectar=None, buscar=None) -> dict:
    """Baixa os e-mails novos dos últimos `dias` dias. `conectar`/`buscar` existem para os testes."""
    cache = cache or CACHE
    with _TRAVA:
        from actions import email_reader as ER
        conectar = conectar or ER._connect
        buscar = buscar or ER._fetch
        dias = max(1, min(365, int(dias)))
        maximo = max(1, min(MAX_EMAILS, int(maximo)))
        ligar(cache)
        ind = _ler_indice(cache)
        conn = conectar()
        novos = 0
        try:
            conn.select("INBOX", readonly=True)
            validade, _ = ER._status(conn)
            if ind.get("validade") and validade and validade != ind["validade"]:
                for f in cache.glob(PREFIXO + "*.txt"):
                    f.unlink(missing_ok=True)          # os UIDs antigos não valem mais
                ind["uids"] = {}
            ind["validade"] = validade
            desde = (_dt.date.today() - _dt.timedelta(days=dias)).strftime("%d-%b-%Y")
            typ, dados = conn.uid("SEARCH", "SINCE", desde)
            uids = sorted((int(x) for x in (dados[0].split() if typ == "OK" and dados and dados[0] else [])),
                          reverse=True)[:maximo]
            for uid in uids:
                if str(uid) in ind["uids"]:
                    continue
                m = buscar(conn, uid)
                if not m:
                    continue
                nome = _arquivo_de(m)
                (cache / nome).write_text(_texto_de(m), encoding="utf-8")
                ind["uids"][str(uid)] = nome
                novos += 1
        finally:
            try:
                conn.logout()
            except Exception:
                pass
        # respeita o teto: mantém só os mais novos
        if len(ind["uids"]) > MAX_EMAILS:
            for uid in sorted(ind["uids"], key=int)[:len(ind["uids"]) - MAX_EMAILS]:
                (cache / ind["uids"].pop(uid)).unlink(missing_ok=True)
        _gravar_indice(cache, ind)
        return {"novos": novos, "total": len(ind["uids"])}


def esquecer(cache: Path | None = None) -> int:
    """Apaga o cache de e-mails. Devolve quantos arquivos foram apagados."""
    cache = cache or CACHE
    with _TRAVA:
        n = 0
        if cache.is_dir():
            for f in cache.iterdir():
                if f.is_file() and (f.name == _INDICE or f.name.startswith(PREFIXO)):
                    f.unlink(missing_ok=True)
                    n += f.name != _INDICE
            try:
                cache.rmdir()
            except OSError:
                pass
        return n


def eh_email(t: dict) -> bool:
    return str(t.get("nome", "")).startswith(PREFIXO)
