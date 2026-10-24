"""Texto e ferramentas de programador — tudo offline (NEXUS Pro 2.2).

Por voz:  "conta as palavras desse texto"      "transforma em maiúsculas"       "gera um UUID"
          "faz o hash SHA-256 de 'senha123'"    "codifica em base64: olá"        "formata esse JSON"
          "que dia é o timestamp 1760000000?"   "cria um slug de 'Meu Post Novo'"

Só texto entra e texto sai: não lê arquivos, não roda comandos e não usa eval.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import unicodedata
import urllib.parse
import uuid
from datetime import datetime, timezone

_MAX = 200_000


def _palavras(t: str) -> list[str]:
    """Quebra 'meuNomeAqui', 'meu_nome-aqui' e 'Meu nome aqui' em ['meu', 'nome', 'aqui']."""
    t = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", t)
    return [p.lower() for p in re.split(r"[^\w]+|_", t) if p]


def _sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))


def contar(t: str) -> str:
    palavras = re.findall(r"\w+", t, re.UNICODE)
    frases = [s for s in re.split(r"[.!?]+\s*", t) if s.strip()]
    minutos = len(palavras) / 200
    leitura = "menos de 1 minuto" if minutos < 1 else f"cerca de {minutos:.0f} minuto(s)"
    return (f"{len(palavras)} palavra(s), {len(t)} caractere(s) ({len(t.replace(' ', '').replace(chr(10), ''))} "
            f"sem espaços), {len(t.splitlines()) or 1} linha(s), {len(frases)} frase(s). Leitura: {leitura}.")


def caixa(t: str, modo: str) -> str:
    p = _palavras(t)
    modo = modo.lower()
    if modo in ("upper", "maiusculas", "maiúsculas"):
        return t.upper()
    if modo in ("lower", "minusculas", "minúsculas"):
        return t.lower()
    if modo in ("title", "titulo", "título"):
        return " ".join(w.capitalize() for w in t.split())
    if modo == "snake":
        return "_".join(p)
    if modo == "kebab":
        return "-".join(p)
    if modo == "camel":
        return (p[0] + "".join(w.capitalize() for w in p[1:])) if p else ""
    if modo == "pascal":
        return "".join(w.capitalize() for w in p)
    raise ValueError("Modos de caixa: upper, lower, title, snake, kebab, camel, pascal.")


def slug(t: str) -> str:
    return "-".join(re.findall(r"[a-z0-9]+", _sem_acento(t).lower()))


def hash_texto(t: str, algoritmo: str) -> str:
    alg = (algoritmo or "sha256").lower().replace("-", "")
    if alg not in ("md5", "sha1", "sha256", "sha512"):
        raise ValueError("Algoritmos: md5, sha1, sha256, sha512.")
    return hashlib.new(alg, t.encode("utf-8")).hexdigest()


def b64(t: str, decodificar: bool) -> str:
    if not decodificar:
        return base64.b64encode(t.encode("utf-8")).decode("ascii")
    try:
        t2 = t.strip()
        t2 += "=" * (-len(t2) % 4)
        return base64.b64decode(t2, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise ValueError("Isso não é um base64 de texto válido.")


def json_formatar(t: str, minificar: bool = False) -> str:
    try:
        obj = json.loads(t)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON inválido na linha {e.lineno}, coluna {e.colno}: {e.msg}.")
    if minificar:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False)


def timestamp(t: str) -> str:
    t = t.strip()
    if not t or t.lower() in ("agora", "now"):
        d = datetime.now(timezone.utc)
        return f"Agora: {int(d.timestamp())} (UTC {d:%Y-%m-%d %H:%M:%S})"
    if re.fullmatch(r"-?\d{9,13}(\.\d+)?", t):
        n = float(t)
        if abs(n) > 1e11:                               # milissegundos
            n /= 1000
        d = datetime.fromtimestamp(n, timezone.utc)
        local = d.astimezone()
        return f"{t} = {d:%d/%m/%Y %H:%M:%S} UTC ({local:%d/%m/%Y %H:%M:%S} no horário do PC)"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            d = datetime.strptime(t, fmt).astimezone()          # lido como horário do PC
            return f"{t} (horário do PC) = timestamp {int(d.timestamp())}"
        except ValueError:
            continue
    raise ValueError("Diga um timestamp (1760000000) ou uma data (22/10/2026 15:30).")


def texto_dev(parameters: dict, player=None) -> str:
    op = str(parameters.get("operation") or "").strip().lower()
    t = str(parameters.get("text") if parameters.get("text") is not None else "")
    if len(t) > _MAX:
        return f"[failed] Texto grande demais (limite {_MAX} caracteres)."
    try:
        if op in ("count", "contar"):
            return contar(t) if t.strip() else "Cadê o texto? Cole ou diga o que devo contar."
        if op == "uuid":
            return str(uuid.uuid4())
        if op == "timestamp":
            return timestamp(t)
        if not t.strip():
            return "[failed] Faltou o texto para esta operação."
        if op in ("case", "caixa"):
            return caixa(t, str(parameters.get("mode") or ""))
        if op == "slug":
            return slug(t)
        if op == "hash":
            return hash_texto(t, str(parameters.get("mode") or "sha256"))
        if op == "base64_encode":
            return b64(t, False)
        if op == "base64_decode":
            return b64(t, True)
        if op == "url_encode":
            return urllib.parse.quote(t, safe="")
        if op == "url_decode":
            return urllib.parse.unquote(t)
        if op in ("json_format", "json"):
            return json_formatar(t)
        if op == "json_minify":
            return json_formatar(t, True)
        if op in ("remove_accents", "sem_acento"):
            return _sem_acento(t)
        if op in ("reverse", "inverter"):
            return t[::-1]
        if op in ("sort_lines", "ordenar"):
            return "\n".join(sorted(t.splitlines(), key=lambda s: _sem_acento(s).lower()))
        if op in ("unique_lines", "unicas"):
            vistos, saida = set(), []
            for linha in t.splitlines():
                if linha not in vistos:
                    vistos.add(linha)
                    saida.append(linha)
            return "\n".join(saida)
    except ValueError as e:
        return f"[failed] {e}"
    return ("Operação desconhecida. Use count, case, slug, hash, base64_encode, base64_decode, url_encode, "
            "url_decode, json_format, json_minify, uuid, timestamp, remove_accents, reverse, sort_lines ou unique_lines.")


TOOL = {
    "name": "texto_dev",
    "description": (
        "OFFLINE TEXT & DEVELOPER UTILITIES on text the user gives (no files, no commands). operation: "
        "count (words/characters/lines/reading time), case (mode=upper|lower|title|snake|kebab|camel|pascal), "
        "slug, hash (mode=md5|sha1|sha256|sha512), base64_encode, base64_decode, url_encode, url_decode, "
        "json_format, json_minify, uuid (no text needed), timestamp (text = unix time or a date like "
        "'22/10/2026 15:30'; empty = now), remove_accents, reverse, sort_lines, unique_lines. "
        "Return the result to the user; for long output also offer to put it on the clipboard."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "operation": {"type": "STRING", "description": "count | case | slug | hash | base64_encode | base64_decode | url_encode | url_decode | json_format | json_minify | uuid | timestamp | remove_accents | reverse | sort_lines | unique_lines"},
            "text": {"type": "STRING", "description": "The text to work on"},
            "mode": {"type": "STRING", "description": "For case: upper|lower|title|snake|kebab|camel|pascal. For hash: md5|sha1|sha256|sha512"},
        },
        "required": ["operation"],
    },
    "handler": texto_dev,
}
