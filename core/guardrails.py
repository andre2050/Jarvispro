"""core/guardrails.py — guardrails de entrada e saída das ferramentas (NEXUS Ultra 4.1).

Uma camada que olha CADA chamada de ferramenta antes de executar (entrada) e o resultado antes de voltar ao modelo (saída):
  • bloquear — a chamada não acontece (ex.: apagar pastas do sistema, mandar uma chave de API para fora);
  • redigir  — o que casa é trocado por [oculto] no resultado, para o modelo e o histórico nunca verem (cartão, CPF, chaves);
  • avisar   — a chamada acontece, mas vai para o trace/auditoria com a marca da regra.
Vem com regras padrão (abaixo) e você acrescenta as suas em config/guardrails.json:
  {"nome": "...", "tool": "send_message|*", "onde": "entrada|saida", "campo": "texto qualquer ou nome do parâmetro", "padrao": "regex", "acao": "bloquear|redigir|avisar", "motivo": "..."}
As suas regras só podem endurecer: não existe ação que desligue as padrão. Regex inválida é ignorada (nunca derruba a ferramenta). Tudo local.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from core.protecao import engolida as _engolida

ARQUIVO = Path(__file__).resolve().parent.parent / "config" / "guardrails.json"
ACOES = ("bloquear", "redigir", "avisar")
MAX_REGRAS_USUARIO = 30

_SEG = r"(?:AIza[0-9A-Za-z_\-]{20,}|sk-[A-Za-z0-9_\-]{20,}|ghp_[A-Za-z0-9]{30,}|xox[baprs]-[A-Za-z0-9\-]{10,}|AKIA[0-9A-Z]{16})"
_CARTAO = r"\b(?:\d[ -]?){13,19}\b"
_CPF = r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"
PADRAO = [
    {"nome": "chave_para_fora", "tool": "send_message|email_reader|notepad|quick_notes|telegram|notion|discord|connectors", "onde": "entrada", "campo": "*",
     "padrao": _SEG, "acao": "bloquear", "motivo": "parece uma chave de API sendo enviada para fora"},
    {"nome": "apagar_sistema", "tool": "file_controller|file_processor|organize_folder", "onde": "entrada", "campo": "*",
     "padrao": r"(?i)(?:\b[a-z]:\\windows\b|\b[a-z]:\\program files|\\system32|(?:^|[\s'\"=:])/(?:etc|bin|boot|usr|sys|proc)(?:/|\b))", "acao": "bloquear", "motivo": "pasta do sistema"},
    {"nome": "comando_destrutivo", "tool": "*", "onde": "entrada", "campo": "*",
     "padrao": r"(?i)(rm\s+-rf\s+/|format\s+[a-z]:|del\s+/[sfq]\s+[a-z]:\\|mkfs\.|:\(\)\s*\{|dd\s+if=.*of=/dev/)", "acao": "bloquear", "motivo": "comando que destrói dados"},
    {"nome": "segredo_na_saida", "tool": "*", "onde": "saida", "campo": "*", "padrao": _SEG, "acao": "redigir", "motivo": "chave de API no resultado"},
    {"nome": "cartao_na_saida", "tool": "*", "onde": "saida", "campo": "*", "padrao": _CARTAO, "acao": "redigir", "motivo": "número de cartão no resultado"},
    {"nome": "cpf_na_saida", "tool": "*", "onde": "saida", "campo": "*", "padrao": _CPF, "acao": "redigir", "motivo": "CPF no resultado"},
]
# resultados que têm de ser entregues como estão (o usuário pediu para ver o próprio dado)
_SAIDA_LIVRE = {"auditoria", "backup_cripto", "meus_dados"}


def _regras_usuario(arq=None) -> list[dict]:
    try:
        d = json.loads(Path(arq or ARQUIVO).read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in (d if isinstance(d, list) else [])[:MAX_REGRAS_USUARIO]:
        if isinstance(r, dict) and r.get("acao") in ACOES and r.get("onde") in ("entrada", "saida") and r.get("padrao"):
            try:
                re.compile(str(r["padrao"]))
            except re.error:
                continue
            out.append({"nome": str(r.get("nome") or "regra_sua")[:40], "tool": str(r.get("tool") or "*")[:200], "onde": r["onde"], "campo": str(r.get("campo") or "*")[:40],
                        "padrao": str(r["padrao"])[:300], "acao": r["acao"], "motivo": str(r.get("motivo") or "regra sua")[:120]})
    return out


def regras(arq=None) -> list[dict]:
    return PADRAO + _regras_usuario(arq)


def _casa_tool(padrao: str, nome: str) -> bool:
    return padrao == "*" or nome in padrao.split("|")


def _textos(args, campo: str) -> list[str]:
    if not isinstance(args, dict):
        return [str(args)]
    if campo in ("*", ""):
        return [json.dumps(args, ensure_ascii=False, default=str)]
    return [str(args.get(campo, ""))]


def checar_entrada(nome: str, args, arq=None) -> tuple[str, str, str]:
    """(acao, regra, motivo): 'ok' | 'bloquear' | 'avisar'. Bloquear ganha de avisar."""
    achado = ("ok", "", "")
    for r in regras(arq):
        if r["onde"] != "entrada" or not _casa_tool(r["tool"], nome):
            continue
        try:
            if any(re.search(r["padrao"], t) for t in _textos(args, r["campo"])):
                if r["acao"] == "bloquear":
                    return "bloquear", r["nome"], r["motivo"]
                if r["acao"] == "avisar" and achado[0] == "ok":
                    achado = ("avisar", r["nome"], r["motivo"])
        except re.error:
            continue
    return achado


def filtrar_saida(nome: str, texto: str, arq=None) -> tuple[str, list[str]]:
    """(texto filtrado, regras que mexeram). 'bloquear' na saída também esconde o resultado inteiro."""
    if nome in _SAIDA_LIVRE or not isinstance(texto, str) or not texto:
        return texto, []
    usadas = []
    for r in regras(arq):
        if r["onde"] != "saida" or not _casa_tool(r["tool"], nome):
            continue
        try:
            if r["acao"] == "redigir":
                novo, n = re.subn(r["padrao"], "[oculto]", texto)
                if n:
                    texto = novo
                    usadas.append(r["nome"])
            elif re.search(r["padrao"], texto):
                if r["acao"] == "bloquear":
                    return f"[failed] Guardrail “{r['nome']}”: {r['motivo']}. O resultado foi retido.", [r["nome"]]
                usadas.append(r["nome"])
        except re.error:
            continue
    return texto, usadas


def adicionar(regra: dict, arq=None) -> str:
    a = Path(arq or ARQUIVO)
    lista = []
    try:
        lista = json.loads(a.read_text(encoding="utf-8"))
    except Exception:
        _engolida("core/guardrails.py:118")
    if len(lista) >= MAX_REGRAS_USUARIO:
        raise ValueError(f"Já há {MAX_REGRAS_USUARIO} regras suas.")
    if regra.get("acao") not in ACOES or regra.get("onde") not in ("entrada", "saida"):
        raise ValueError("Use acao = bloquear|redigir|avisar e onde = entrada|saida.")
    try:
        re.compile(str(regra.get("padrao") or ""))
    except re.error as e:
        raise ValueError(f"Regex inválida: {e}")
    if not regra.get("padrao"):
        raise ValueError("Falta o padrão (regex).")
    lista.append({k: regra.get(k, "") for k in ("nome", "tool", "onde", "campo", "padrao", "acao", "motivo")})
    a.parent.mkdir(parents=True, exist_ok=True)
    a.write_text(json.dumps(lista, ensure_ascii=False, indent=1), encoding="utf-8")
    return str(regra.get("nome") or "regra_sua")


def remover(nome: str, arq=None) -> int:
    a = Path(arq or ARQUIVO)
    try:
        lista = json.loads(a.read_text(encoding="utf-8"))
    except Exception:
        return 0
    ficam = [r for r in lista if r.get("nome") != nome]
    a.write_text(json.dumps(ficam, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(lista) - len(ficam)


def saude() -> tuple[bool, str]:
    return True, f"{len(PADRAO)} padrão + {len(_regras_usuario())} suas"
