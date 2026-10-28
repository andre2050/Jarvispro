"""core/isa_arquitetura.py — auto-evolução de arquitetura (NEXUS Ultra 2026 3.9): o NEXUS olha a PRÓPRIA estrutura e propõe melhorias.

Lê o código (sem rodar) e mede: arquivos grandes, funções enormes, dependências circulares entre módulos (só as de topo de arquivo, que
quebram a importação), módulos de que todos dependem (frágeis) e módulos que ninguém importa (candidatos a código morto). Gera PROPOSTAS
ordenadas (impacto × esforço) e compara com a última rodada para mostrar se a arquitetura melhorou ou piorou.
Ele NÃO reescreve nada sozinho: aplicar uma proposta é um trabalho de código que você pede ao agente de código, com revisão e testes.
"""
from __future__ import annotations

import ast
import json
import time
from pathlib import Path

from core import isa_codigo as IC

BASE = IC.BASE
ARQ = BASE / "memory" / "isa_arquitetura.json"
LIMITE_ARQUIVO = 900
LIMITE_FUNCAO = 150
RAIZES = ("core", "actions", "assistant", "ui", "dashboard", "memory")


def _modulo(rel: str) -> str:
    return rel[:-3].replace("/", ".").removesuffix(".__init__")


def _imports(codigo: str, so_topo: bool) -> set[str]:
    try:
        arv = ast.parse(codigo)
    except SyntaxError:
        return set()
    nos = arv.body if so_topo else list(ast.walk(arv))
    out = set()
    for n in nos:
        if isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            out.add(n.module)
            out |= {f"{n.module}.{a.name}" for a in n.names}
    return {m for m in out if m.split(".")[0] in RAIZES}


def grafo(raiz: Path | None = None, so_topo: bool = False) -> dict[str, set[str]]:
    raiz = Path(raiz or BASE)
    arqs = {_modulo(str(p.relative_to(raiz)).replace("\\", "/")): p for p in IC.arquivos_py(raiz)}
    g = {}
    for mod, p in arqs.items():
        try:
            alvo = _imports(p.read_text(encoding="utf-8"), so_topo)
        except OSError:
            alvo = set()
        g[mod] = {m for m in alvo if m in arqs and m != mod and m not in RAIZES}
    return g


def ciclos(g: dict[str, set[str]]) -> list[list[str]]:
    """Componentes fortemente conectados com mais de um módulo (Tarjan, iterativo)."""
    idx, low, pilha, na_pilha, out, c = {}, {}, [], set(), [], [0]
    for raiz in g:
        if raiz in idx:
            continue
        trabalho = [(raiz, iter(sorted(g[raiz])))]
        idx[raiz] = low[raiz] = c[0]; c[0] += 1; pilha.append(raiz); na_pilha.add(raiz)
        while trabalho:
            v, it = trabalho[-1]
            for w in it:
                if w not in idx:
                    idx[w] = low[w] = c[0]; c[0] += 1; pilha.append(w); na_pilha.add(w)
                    trabalho.append((w, iter(sorted(g.get(w, ())))))
                    break
                elif w in na_pilha:
                    low[v] = min(low[v], idx[w])
            else:
                trabalho.pop()
                if trabalho:
                    low[trabalho[-1][0]] = min(low[trabalho[-1][0]], low[v])
                if low[v] == idx[v]:
                    comp = []
                    while True:
                        w = pilha.pop(); na_pilha.discard(w); comp.append(w)
                        if w == v:
                            break
                    if len(comp) > 1:
                        out.append(sorted(comp))
    return sorted(out)


def medir(raiz: Path | None = None) -> dict:
    raiz = Path(raiz or BASE)
    topo, todo = grafo(raiz, True), grafo(raiz, False)
    grandes, funcoes = [], []
    for p in IC.arquivos_py(raiz):
        rel = str(p.relative_to(raiz)).replace("\\", "/")
        try:
            cod = p.read_text(encoding="utf-8")
            n = cod.count("\n") + 1
            if n > LIMITE_ARQUIVO:
                grandes.append((rel, n))
            for f in ast.walk(ast.parse(cod)):
                if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and getattr(f, "end_lineno", f.lineno) - f.lineno + 1 > LIMITE_FUNCAO:
                    funcoes.append((f"{rel}:{f.name}", f.end_lineno - f.lineno + 1))
        except (OSError, SyntaxError):
            continue
    entrada = {m: sum(1 for o in todo if m in todo[o]) for m in todo}
    sem_uso = sorted(m for m in todo if entrada[m] == 0 and m.startswith("core.") and not any(m in outro for outro in todo.values()))
    return {"modulos": len(todo), "ciclos_topo": ciclos(topo), "grandes": sorted(grandes, key=lambda x: -x[1])[:10],
            "funcoes_grandes": sorted(funcoes, key=lambda x: -x[1])[:10],
            "mais_dependidos": sorted(entrada.items(), key=lambda x: -x[1])[:5], "sem_uso": sem_uso[:15]}


def propostas(med: dict) -> list[dict]:
    p = []
    for c in med["ciclos_topo"]:
        p.append({"impacto": 5, "esforco": 2, "titulo": f"Desfazer dependência circular: {' ↔ '.join(c[:4])}",
                  "como": "mover o import de um dos lados para dentro da função que usa, ou extrair a parte comum para um módulo novo"})
    for rel, n in med["grandes"][:3]:
        p.append({"impacto": 3, "esforco": 4, "titulo": f"Dividir {rel} ({n} linhas)",
                  "como": "separar por responsabilidade em módulos menores, mantendo o nome antigo reexportando"})
    for nome, n in med["funcoes_grandes"][:3]:
        p.append({"impacto": 2, "esforco": 3, "titulo": f"Quebrar a função {nome} ({n} linhas)",
                  "como": "extrair blocos com nome próprio e testá-los separados"})
    for m, n in med["mais_dependidos"][:2]:
        if n >= 8:
            p.append({"impacto": 3, "esforco": 3, "titulo": f"{m} é usado por {n} módulos",
                      "como": "cobrir com testes antes de mexer; qualquer mudança nele se espalha"})
    if med["sem_uso"]:
        p.append({"impacto": 1, "esforco": 1, "titulo": f"{len(med['sem_uso'])} módulos de core/ que ninguém importa",
                  "como": "conferir se são ferramentas carregadas por nome; se não, remover: " + ", ".join(med["sem_uso"][:5])})
    return sorted(p, key=lambda x: (-(x["impacto"] / x["esforco"]), -x["impacto"]))


def rodar(raiz: Path | None = None, arq: Path | None = None, agora: float | None = None) -> dict:
    """Mede, propõe, compara com a última rodada e guarda."""
    arq = Path(arq or ARQ)
    med = medir(raiz)
    try:
        ant = json.loads(arq.read_text(encoding="utf-8")).get("resumo", {})
    except Exception:
        ant = {}
    resumo = {"modulos": med["modulos"], "ciclos": len(med["ciclos_topo"]), "grandes": len(med["grandes"]),
              "funcoes_grandes": len(med["funcoes_grandes"]), "sem_uso": len(med["sem_uso"])}
    tendencia = {k: resumo[k] - ant.get(k, resumo[k]) for k in ("ciclos", "grandes", "funcoes_grandes", "sem_uso")} if ant else {}
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps({"quando": time.time() if agora is None else agora, "resumo": resumo}), encoding="utf-8")
    return {"medidas": med, "resumo": resumo, "tendencia": tendencia, "propostas": propostas(med)}


def texto(r: dict, limite: int = 5) -> str:
    s, t = r["resumo"], r["tendencia"]
    linhas = [f"Arquitetura: {s['modulos']} módulos, {s['ciclos']} ciclo(s), {s['grandes']} arquivo(s) grande(s), "
              f"{s['funcoes_grandes']} função(ões) enorme(s), {s['sem_uso']} sem uso."]
    if t:
        mud = [f"{k} {'+' if v > 0 else ''}{v}" for k, v in t.items() if v]
        linhas.append("Desde a última vez: " + (", ".join(mud) if mud else "sem mudança") + ".")
    linhas += [f"{i}. {p['titulo']} — {p['como']}" for i, p in enumerate(r["propostas"][:limite], 1)]
    if not r["propostas"]:
        linhas.append("Nada a propor agora.")
    linhas.append("Eu só proponho; para aplicar, peça ao agente de código (com revisão e testes).")
    return "\n".join(linhas)
