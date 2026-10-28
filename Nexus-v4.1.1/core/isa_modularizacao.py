"""core/isa_modularizacao.py — planejamento da modularização (NEXUS Ultra 4.0).

Junta o que o núcleo já sabe — tamanho dos arquivos e das funções (isa_arquitetura), quem depende de quem e arquivos mexidos
recentemente (isa_codigo) — e propõe COMO dividir os módulos que mais pedem isso:
  • candidatos: arquivos acima de {LIMITE} linhas; nota = tamanho + dependentes×40 + mexido recentemente (mais risco, mais valor);
  • grupos sugeridos: funções do topo agrupadas por prefixo do nome (telegram_*, agenda_*, notion_* viram 3 módulos) ou, sem prefixo, por quem
    chama quem; nomes de módulos novos sugeridos; o arquivo original continuaria reexportando (nada quebra);
  • ordem: primeiro o que tem MENOS dependentes (menor risco); checklist de testes por candidato.
Só PLANEJA e grava memory/isa_modularizacao.json: nunca move código nem edita arquivos.
"""
from __future__ import annotations

import ast
import json
import re
import time
from collections import defaultdict
from pathlib import Path

from core import isa_arquitetura as IA
from core import isa_codigo as IC

BASE = Path(__file__).resolve().parent.parent
ARQ = BASE / "memory" / "isa_modularizacao.json"
LIMITE = 600
MIN_GRUPO = 2
__doc__ = __doc__.replace("{LIMITE}", str(LIMITE))


def _topo(codigo: str) -> dict[str, dict]:
    """Funções/classes de nível superior: {nome: {"linhas": n, "chama": {outros nomes do topo}}}."""
    arv = ast.parse(codigo)
    nomes = {n.name for n in arv.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    out = {}
    for n in arv.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            usa = {x.id for x in ast.walk(n) if isinstance(x, ast.Name)} | {x.attr for x in ast.walk(n) if isinstance(x, ast.Attribute)}
            out[n.name] = {"linhas": getattr(n, "end_lineno", n.lineno) - n.lineno + 1, "chama": (usa & nomes) - {n.name}}
    return out


def _prefixo(nome: str) -> str:
    n = nome.lstrip("_")
    return n.split("_")[0] if "_" in n else ""


def agrupar(codigo: str) -> list[dict]:
    """Sugere grupos de funções para virar módulos. [{"nome","funcoes","linhas"}]; vazio se não achar divisão boa."""
    try:
        topo = _topo(codigo)
    except SyntaxError:
        return []
    por_pref: dict[str, list[str]] = defaultdict(list)
    for n in topo:
        p = _prefixo(n)
        if p:
            por_pref[p].append(n)
    grupos = [{"nome": p, "funcoes": sorted(f), "linhas": sum(topo[x]["linhas"] for x in f)}
              for p, f in por_pref.items() if len(f) >= MIN_GRUPO]
    if len(grupos) < 2:                                                # sem prefixos úteis: componentes de quem chama quem
        pai = {n: n for n in topo}

        def raiz(x):
            while pai[x] != x:
                pai[x] = pai[pai[x]]
                x = pai[x]
            return x
        for n, info in topo.items():
            for m in info["chama"]:
                pai[raiz(n)] = raiz(m)
        comp: dict[str, list[str]] = defaultdict(list)
        for n in topo:
            comp[raiz(n)].append(n)
        grupos = [{"nome": f"parte_{i}", "funcoes": sorted(f), "linhas": sum(topo[x]["linhas"] for x in f)}
                  for i, f in enumerate(sorted(comp.values(), key=lambda f: -len(f)), 1) if len(f) >= MIN_GRUPO]
        grupos = grupos if len(grupos) >= 2 else []
    return sorted(grupos, key=lambda g: -g["linhas"])


def planejar(raiz: Path | None = None, dias_recentes: float = 14, agora: float | None = None, limite: int = LIMITE) -> dict:
    raiz = Path(raiz or BASE)
    todo = IA.grafo(raiz, False)
    entrada = {m: sum(1 for o in todo if m in todo[o]) for m in todo}
    rec = set(IC.recentes(dias_recentes, raiz, agora))
    itens = []
    for p in IC.arquivos_py(raiz):
        rel = str(p.relative_to(raiz)).replace("\\", "/")
        if rel.startswith("tests/") or "/__" in rel:
            continue
        try:
            cod = p.read_text(encoding="utf-8")
        except OSError:
            continue
        n = cod.count("\n") + 1
        if n < limite:
            continue
        g = agrupar(cod)
        if not g:
            continue
        mod = IA._modulo(rel)
        dep = entrada.get(mod, 0)
        recente = rel in rec
        base = rel[:-3]
        itens.append({
            "arquivo": rel, "linhas": n, "dependentes": dep, "mexido_recentemente": recente,
            "nota": n + dep * 40 + (150 if recente else 0),
            "grupos": [{"modulo_novo": f"{base}_{x['nome']}.py", "funcoes": x["funcoes"][:12], "linhas": x["linhas"]} for x in g[:5]],
            "risco": "alto" if dep >= 15 or recente else "médio" if dep >= 5 else "baixo",
            "testes": [f"rodar os testes que importam {mod}", "conferir que `from " + mod + " import <função>` continua funcionando (o arquivo original reexporta)",
                       "rodar a suíte completa antes de publicar"],
        })
    ordem = sorted(itens, key=lambda x: (x["dependentes"], -x["linhas"]))      # menos dependentes primeiro = menor risco
    for i, it in enumerate(ordem, 1):
        it["ordem"] = i
    return {"t": time.time() if agora is None else agora, "candidatos": ordem[:10], "total_modulos": len(todo)}


def rodar(raiz: Path | None = None, arq: Path | None = None, agora: float | None = None) -> dict:
    r = planejar(raiz, agora=agora)
    try:
        a = Path(arq or ARQ)
        a.parent.mkdir(parents=True, exist_ok=True)
        a.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return r


def texto(r: dict, limite: int = 3) -> str:
    if not r["candidatos"]:
        return "Nenhum módulo grande o bastante com uma divisão clara. A modularização está em dia."
    l = [f"{len(r['candidatos'])} módulo(s) pedem divisão; comece pelos de menor risco:"]
    for c in r["candidatos"][:limite]:
        g = "; ".join(f"{x['modulo_novo'].rsplit('/', 1)[-1]} ({len(x['funcoes'])} funções)" for x in c["grupos"][:3])
        l.append(f"{c['ordem']}) {c['arquivo']} — {c['linhas']} linhas, {c['dependentes']} dependentes, risco {c['risco']}: {g}.")
    l.append("Só planejei; nada foi movido.")
    return " ".join(l)


def saude() -> tuple[bool, str]:
    return True, "planejador pronto"
