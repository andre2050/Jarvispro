"""core/isa_codigo.py — análise de código recente (NEXUS Ultra 2026 3.9).

Guarda a "impressão digital" (hash) de cada arquivo .py do projeto. Na próxima análise, só olha o que MUDOU desde a anterior
(ou nos últimos N dias) e procura problemas de verdade: erro de sintaxe, `eval/exec`, `os.system`/`shell=True`, segredo no
código, `except:` sem tipo, argumento padrão mutável, import sem uso, funções gigantes, TODO/FIXME.
É análise ESTÁTICA (não roda nada): acha candidatos a problema, não prova bug. Não altera nenhum arquivo.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
ARQ_SNAP = BASE / "memory" / "isa_codigo.json"
PASTAS = ("core", "actions", "assistant", "ui", "dashboard", "memory", "plugins")
IGNORAR = ("tests", "backups", "_internal", "__pycache__", "plugins_gerados", ".venv", "Nexus-v")
_SEGREDO = re.compile(r"(AIza[0-9A-Za-z_\-]{30,}|sk-[A-Za-z0-9]{20,}|sk-ant-[A-Za-z0-9_\-]{20,}|(?:password|senha|secret|token)\s*=\s*['\"][^'\"\s]{8,}['\"])", re.I)
LINHAS_FUNCAO = 120
GRAVIDADE = {"alta": 3, "media": 2, "baixa": 1}


def arquivos_py(raiz: Path | None = None) -> list[Path]:
    raiz = Path(raiz or BASE)
    out = []
    for pasta in PASTAS:
        for p in (raiz / pasta).rglob("*.py") if (raiz / pasta).is_dir() else []:
            if not any(x in p.parts or any(part.startswith(x) for part in p.parts) for x in IGNORAR):
                out.append(p)
    return sorted(out)


def _hash(p: Path) -> str:
    return hashlib.sha1(p.read_bytes()).hexdigest()


def impressao(raiz: Path | None = None) -> dict[str, str]:
    raiz = Path(raiz or BASE)
    return {str(p.relative_to(raiz)).replace("\\", "/"): _hash(p) for p in arquivos_py(raiz)}


def mudancas(raiz: Path | None = None, arq: Path | None = None) -> dict:
    """{novos, alterados, removidos} desde a última `marcar()`. Sem marca anterior, tudo é 'novo'."""
    ant = _ler(arq).get("arquivos", {})
    atual = impressao(raiz)
    return {"novos": sorted(set(atual) - set(ant)), "alterados": sorted(k for k in atual if k in ant and atual[k] != ant[k]),
            "removidos": sorted(set(ant) - set(atual))}


def marcar(raiz: Path | None = None, arq: Path | None = None, agora: float | None = None) -> int:
    d = {"quando": time.time() if agora is None else agora, "arquivos": impressao(raiz)}
    arq = Path(arq or ARQ_SNAP)
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(d), encoding="utf-8")
    return len(d["arquivos"])


def _ler(arq: Path | None = None) -> dict:
    try:
        return json.loads(Path(arq or ARQ_SNAP).read_text(encoding="utf-8"))
    except Exception:
        return {}


def recentes(dias: float, raiz: Path | None = None, agora: float | None = None) -> list[str]:
    raiz = Path(raiz or BASE)
    corte = (time.time() if agora is None else agora) - dias * 86400
    return [str(p.relative_to(raiz)).replace("\\", "/") for p in arquivos_py(raiz) if p.stat().st_mtime >= corte]


def analisar_texto(codigo: str, nome: str = "arquivo.py") -> list[dict]:
    """Lista de {arquivo, linha, tipo, gravidade, msg}. Nunca levanta erro."""
    achados: list[dict] = []

    def add(linha, tipo, grav, msg):
        achados.append({"arquivo": nome, "linha": linha, "tipo": tipo, "gravidade": grav, "msg": msg})

    try:
        arv = ast.parse(codigo)
    except SyntaxError as e:
        add(e.lineno or 0, "sintaxe", "alta", f"erro de sintaxe: {e.msg}")
        return achados
    for i, l in enumerate(codigo.splitlines(), 1):
        if _SEGREDO.search(l) and "os.environ" not in l and "getenv" not in l:
            add(i, "segredo", "alta", "parece um segredo escrito no código")
        if re.search(r"#\s*(TODO|FIXME|XXX)\b", l):
            add(i, "pendencia", "baixa", l.strip()[:80])
    usados = {n.id for n in ast.walk(arv) if isinstance(n, ast.Name)} | {n.value.id for n in ast.walk(arv)
                                                                        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}
    for n in ast.walk(arv):
        if isinstance(n, ast.Call):
            f = n.func
            nome_f = f.id if isinstance(f, ast.Name) else (f"{f.value.id}.{f.attr}" if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) else "")
            if nome_f in ("eval", "exec"):
                add(n.lineno, "perigo", "alta", f"uso de {nome_f}()")
            if nome_f in ("os.system", "os.popen"):
                add(n.lineno, "perigo", "alta", f"uso de {nome_f}() (comando de shell)")
            if any(k.arg == "shell" and isinstance(k.value, ast.Constant) and k.value.value is True for k in n.keywords):
                add(n.lineno, "perigo", "alta", "subprocess com shell=True")
        elif isinstance(n, ast.ExceptHandler):
            if n.type is None:
                add(n.lineno, "excecao", "media", "`except:` sem tipo (esconde até Ctrl+C)")
            elif len(n.body) == 1 and isinstance(n.body[0], ast.Pass) and isinstance(n.type, ast.Name) and n.type.id == "Exception":
                add(n.lineno, "excecao", "baixa", "`except Exception: pass` engole o erro sem registrar")
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in n.args.defaults + [x for x in n.args.kw_defaults if x is not None]:
                if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                    add(n.lineno, "padrao_mutavel", "media", f"{n.name}(): argumento padrão mutável (compartilhado entre chamadas)")
            fim = getattr(n, "end_lineno", n.lineno)
            if fim - n.lineno + 1 > LINHAS_FUNCAO:
                add(n.lineno, "funcao_grande", "baixa", f"{n.name}() tem {fim - n.lineno + 1} linhas")
    imports = [n for n in arv.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    linhas_import = {i for n in imports for i in range(n.lineno, getattr(n, "end_lineno", n.lineno) + 1)}
    corpo = "\n".join(l for i, l in enumerate(codigo.splitlines(), 1) if i not in linhas_import)
    for n in imports:                                          # imports de topo sem uso
        if nome.endswith("__init__.py"):
            break
        for a in n.names:
            nm = (a.asname or a.name).split(".")[0]
            if nm != "*" and nm not in usados and not (isinstance(n, ast.ImportFrom) and n.module == "__future__"):
                if not re.search(rf"\b{re.escape(nm)}\b", corpo):
                    add(n.lineno, "import_sem_uso", "baixa", f"import “{nm}” não é usado")
    return sorted(achados, key=lambda a: (-GRAVIDADE[a["gravidade"]], a["linha"]))


def analisar(arquivos: list[str], raiz: Path | None = None) -> dict:
    raiz = Path(raiz or BASE)
    todos, ilegiveis = [], []
    for rel in arquivos:
        try:
            todos += analisar_texto((raiz / rel).read_text(encoding="utf-8"), rel)
        except OSError:
            ilegiveis.append(rel)
    por = {g: sum(1 for a in todos if a["gravidade"] == g) for g in GRAVIDADE}
    return {"arquivos": len(arquivos) - len(ilegiveis), "achados": todos, "por_gravidade": por}


def texto(res: dict, limite: int = 8) -> str:
    p = res["por_gravidade"]
    if not res["achados"]:
        return f"Olhei {res['arquivos']} arquivo(s) alterado(s): nada preocupante."
    top = [a for a in res["achados"] if a["gravidade"] != "baixa"][:limite] or res["achados"][:limite]
    linhas = "\n".join(f"- {a['arquivo']}:{a['linha']} [{a['gravidade']}] {a['msg']}" for a in top)
    return (f"Olhei {res['arquivos']} arquivo(s): {p['alta']} grave(s), {p['media']} média(s), {p['baixa']} leve(s).\n{linhas}\n"
            "(Análise estática: aponta candidatos, não prova bug.)")
