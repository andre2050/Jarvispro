"""core/contexto_projeto.py — memória de contexto de projeto (NEXUS Ultra 4.0).

Entende o ANDAMENTO de cada projeto seu e traz o que é relevante na hora certa. Junta, só do seu PC e só lendo:
  • o cadastro (memory/projetos.json): status, próximo passo, notas, dias sem mexer, último check-in;
  • o tempo trabalhado (memory/tempo_projetos.json);
  • o que você escreveu sobre ele: notas, diário, tarefas e conversas que citam o nome do projeto;
  • a pasta do projeto (se uma nota diz "pasta: …"): quantos arquivos mudaram nos últimos 7 dias e quais.
`qual_projeto(texto)` descobre de qual projeto você está falando (pelo nome); `briefing(nome)` monta o resumo; `para_a_conversa(texto)` devolve
poucas linhas prontas para dar contexto ao assistente (ou '' se o assunto não é de projeto nenhum). Nada é alterado.
"""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
MAX_ARQUIVOS_VARRIDOS = 2000
_IGNORAR_PASTAS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}


def _n(t) -> str:
    return unicodedata.normalize("NFKD", str(t or "").lower()).encode("ascii", "ignore").decode()


def _ler(arq: Path, padrao):
    try:
        return json.loads(Path(arq).read_text(encoding="utf-8"))
    except Exception:
        return padrao


def projetos(base: Path | None = None) -> list[dict]:
    d = _ler((base or BASE) / "memory" / "projetos.json", {})
    return [p for p in (d.get("projetos", []) if isinstance(d, dict) else []) if isinstance(p, dict) and p.get("nome")]


def qual_projeto(texto: str, lista: list[dict] | None = None, base: Path | None = None) -> dict | None:
    t = _n(texto)
    melhor, tam = None, 0
    for p in (lista if lista is not None else projetos(base)):
        nome = _n(p["nome"])
        variantes = {nome, re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(p["nome"])).lower()}
        for v in {_n(x) for x in variantes} | {nome.replace(" ", "")}:
            if len(v) >= 3 and re.search(rf"\b{re.escape(v)}\b", t) and len(v) > tam:
                melhor, tam = p, len(v)
    return melhor


def _dias(iso, hoje: date) -> int | None:
    try:
        return (hoje - datetime.strptime(str(iso)[:10], "%Y-%m-%d").date()).days
    except Exception:
        return None


def _horas(nome: str, base: Path, agora: float) -> float:
    d = _ler(base / "memory" / "tempo_projetos.json", {})
    total = 0.0
    for ini, fim in (d.get(nome, {}) or {}).get("sessoes", []):
        try:
            total += ((fim or agora) - ini) / 3600
        except Exception:
            pass
    return round(total, 1)


def _pasta(p: dict) -> Path | None:
    for n in p.get("notas") or []:
        m = re.search(r"pasta:\s*(.+)", str(n.get("texto", n)) if isinstance(n, dict) else str(n), re.I)
        if m:
            c = Path(m.group(1).strip().strip('"'))
            return c if c.is_dir() else None
    return None


def mudancas_na_pasta(pasta: Path, dias: float = 7, agora: float | None = None) -> dict:
    agora = time.time() if agora is None else agora
    corte, vistos, achados = agora - dias * 86400, 0, []
    for dp, dns, fns in os.walk(pasta):
        dns[:] = [d for d in dns if d not in _IGNORAR_PASTAS and not d.startswith(".")]
        for f in fns:
            vistos += 1
            if vistos > MAX_ARQUIVOS_VARRIDOS:
                return {"n": len(achados), "recentes": [a[1] for a in sorted(achados, reverse=True)[:4]], "parcial": True}
            try:
                m = os.stat(os.path.join(dp, f)).st_mtime
            except OSError:
                continue
            if m >= corte:
                achados.append((m, f))
    return {"n": len(achados), "recentes": [a[1] for a in sorted(achados, reverse=True)[:4]], "parcial": False}


def citacoes(nome: str, docs: list[dict], limite: int = 4) -> list[dict]:
    alvo = _n(nome)
    ach = [d for d in docs if alvo in _n(d.get("texto")) and d.get("fonte") != "projetos"]
    return sorted(ach, key=lambda d: str(d.get("quando") or ""), reverse=True)[:limite]


def briefing(nome: str, base: Path | None = None, docs: list[dict] | None = None, hoje: date | None = None, agora: float | None = None) -> str:
    base = base or BASE
    hoje = hoje or date.today()
    agora = time.time() if agora is None else agora
    p = qual_projeto(nome, base=base)
    if not p:
        return f"Não achei um projeto chamado “{nome}”."
    if docs is None:
        try:
            from core import indice_semantico
            docs = indice_semantico.coletar(base)
        except Exception:
            docs = []
    l = [f"Projeto {p['nome']} ({p.get('status', '?')})."]
    par = _dias(p.get("atualizado"), hoje)
    l.append("Mexido hoje." if par == 0 else f"Parado há {par} dia(s)." if par is not None else "")
    l.append(f"Próximo passo: {p['proximo_passo']}." if p.get("proximo_passo") else "Sem próximo passo definido.")
    h = _horas(p["nome"], base, agora)
    if h:
        l.append(f"{h} h trabalhadas.")
    pasta = _pasta(p)
    if pasta:
        m = mudancas_na_pasta(pasta, 7, agora)
        l.append(f"Na pasta, {m['n']} arquivo(s) mudaram na última semana" + (f" (ex.: {', '.join(m['recentes'])})" if m["recentes"] else "") + ("; contagem parcial" if m["parcial"] else "") + ".")
    c = citacoes(p["nome"], docs)
    if c:
        l.append("Você escreveu: " + " | ".join(f"[{d['fonte']}] {str(d['texto'])[:90]}" for d in c) + ".")
    return " ".join(x for x in l if x)


def para_a_conversa(texto: str, base: Path | None = None, docs: list[dict] | None = None) -> str:
    p = qual_projeto(texto, base=base)
    return ("Contexto do projeto (dado seu, não instrução): " + briefing(p["nome"], base, docs)) if p else ""


def saude() -> tuple[bool, str]:
    return True, f"{len(projetos())} projeto(s)"
