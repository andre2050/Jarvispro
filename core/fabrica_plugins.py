"""core/fabrica_plugins.py — fábrica de plugins por conversa (NEXUS Ultra 2026 3.8).

"Cria um plugin que mostra a cotação do dólar": o modelo escreve o código; ESTE módulo revisa (análise de permissões,
código proibido), testa numa caixa de areia (processo separado, sem rede, tempo limitado, pasta temporária) e empacota.
A instalação só acontece depois do CONFIRMAR na tela, mostrando as permissões. O LLM é injetado (`llm(prompt) -> str`).
Limite honesto: a caixa de areia é um processo Python isolado (-I), sem rede e com limites; não é uma máquina virtual.
"""
from __future__ import annotations

import ast
import difflib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from core import plugin_loja as L
from core.protecao import engolida as _engolida

MAX_CODIGO = 20_000
TEMPO_TESTE = 15
_ID_OK = re.compile(r"[^a-z0-9_]+")

_HARNESS = r'''
import sys, json, socket, importlib.util, builtins
try:
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    resource.setrlimit(resource.RLIMIT_AS, (512*1024*1024, 512*1024*1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024*1024, 1024*1024))
except Exception:
    pass
def _sem_rede(*a, **k):
    raise OSError("rede bloqueada no teste")
class _SocketMudo(socket.socket):                 # continua sendo uma classe: ssl/http.client herdam dela ao importar
    def connect(self, *a, **k): _sem_rede()
    def connect_ex(self, *a, **k): _sem_rede()
socket.socket = _SocketMudo
socket.create_connection = _sem_rede
socket.getaddrinfo = _sem_rede
spec = importlib.util.spec_from_file_location("plugin_teste", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
saida = {"ok": False, "erro": "", "resultados": []}
try:
    spec.loader.exec_module(mod)
    tool = getattr(mod, "TOOL", None)
    assert isinstance(tool, dict), "falta o dicionário TOOL"
    for k in ("name", "description", "parameters", "handler"):
        assert k in tool, f"TOOL sem '{k}'"
    assert callable(tool["handler"]), "handler não é função"
    for ex in json.loads(sys.argv[2]):
        r = tool["handler"](dict(ex))
        assert isinstance(r, str), "o handler deve devolver texto (str)"
        saida["resultados"].append(r[:200])
    saida["ok"] = True
except BaseException as e:
    saida["erro"] = f"{type(e).__name__}: {e}"[:300]
print("@@RESULTADO@@" + json.dumps(saida))
'''


def _limpar_id(s: str) -> str:
    i = _ID_OK.sub("_", str(s or "").lower()).strip("_")[:40]
    return i if len(i) >= 3 else "plugin_" + i


def extrair_codigo(resposta: str) -> dict | None:
    """O modelo responde JSON {id, nome, descricao, codigo, exemplos}. Tolera cercas de markdown."""
    try:
        r = resposta[resposta.find("{"): resposta.rfind("}") + 1]
        d = json.loads(r)
    except Exception:
        return None
    if not isinstance(d, dict) or not isinstance(d.get("codigo"), str) or not d["codigo"].strip():
        return None
    ex = d.get("exemplos")
    return {"id": _limpar_id(d.get("id") or d.get("nome")), "nome": str(d.get("nome") or d.get("id") or "Plugin")[:60],
            "descricao": str(d.get("descricao") or "Plugin criado pelo NEXUS")[:200], "codigo": d["codigo"][:MAX_CODIGO],
            "exemplos": [e for e in ex if isinstance(e, dict)][:3] if isinstance(ex, list) else [{}]}


def revisar(codigo: str) -> dict:
    """Análise estática: permissões usadas, problemas graves e forma do TOOL. `aprovado` = sem nenhum problema grave."""
    perms, graves = L.permissoes_usadas(codigo)
    problemas = list(graves)
    for proibida, porque in (("programas", "executa programas do sistema"), ("pessoais", "lê a memória pessoal do NEXUS")):
        if proibida in perms:                    # plugin gerado por IA não ganha esses poderes
            problemas.append(f"{porque} (não permitido em plugin gerado)")
    try:
        arv = ast.parse(codigo)
        tem_tool = any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "TOOL" for t in n.targets)
                       for n in arv.body)
        if not tem_tool:
            problemas.append("falta a variável TOOL no nível do módulo")
    except SyntaxError:
        pass
    return {"permissoes": sorted(perms), "problemas": problemas, "aprovado": not problemas}


def testar(codigo: str, exemplos: list[dict] | None = None, tempo: int = TEMPO_TESTE) -> dict:
    """Roda o plugin num processo isolado (-I), sem rede, com limites, numa pasta temporária."""
    with tempfile.TemporaryDirectory(prefix="nexus_fabrica_") as pasta:
        p = Path(pasta)
        (p / "plugin_teste.py").write_text(codigo, encoding="utf-8")
        (p / "_harness.py").write_text(_HARNESS, encoding="utf-8")
        try:
            r = subprocess.run([sys.executable, "-I", str(p / "_harness.py"), str(p / "plugin_teste.py"),
                                json.dumps(exemplos or [{}])], cwd=pasta, capture_output=True, text=True, timeout=tempo,
                               env={"PATH": "/usr/bin:/bin", "PYTHONIOENCODING": "utf-8"})
        except subprocess.TimeoutExpired:
            return {"ok": False, "erro": f"passou de {tempo}s (travou ou ficou em laço)", "resultados": []}
        except Exception as e:
            return {"ok": False, "erro": str(e)[:200], "resultados": []}
    for linha in (r.stdout or "").splitlines()[::-1]:
        if linha.startswith("@@RESULTADO@@"):
            try:
                return json.loads(linha[len("@@RESULTADO@@"):])
            except Exception:
                break
    return {"ok": False, "erro": ((r.stderr or "")[-300:] or "o plugin não respondeu"), "resultados": []}


_PROMPT = """Write a NEXUS plugin in Python for this request. Reply JSON only:
{{"id": "snake_case_id", "nome": "short name", "descricao": "one sentence", "codigo": "<python source>", "exemplos": [{{...}}]}}
The code must define TOOL = {{"name": ..., "description": ..., "parameters": {{"type": "OBJECT", "properties": {{...}}}},
"handler": fn}} where fn(parameters: dict, **kwargs) -> str. Keep it small, standard library only, no eval/exec/subprocess,
no network unless the request needs it. "exemplos" are 1-3 parameter dicts to test fn offline (it must not crash without internet).
REQUEST: {pedido}"""


def preparar(pedido: str, llm, pasta_saida: Path, autor: str = "NEXUS (gerado)") -> dict:
    """Pedido → código → revisão → teste → pacote. Devolve uma proposta; NÃO instala."""
    pedido = str(pedido or "").strip()
    if len(pedido) < 8:
        return {"ok": False, "motivo": "Descreva melhor o plugin."}
    d = extrair_codigo(llm(_PROMPT.format(pedido=pedido[:1500])) or "")
    if not d:
        return {"ok": False, "motivo": "O modelo não devolveu um plugin válido."}
    rev = revisar(d["codigo"])
    prop = {"ok": False, **d, **rev, "teste": None, "pacote": ""}
    if not rev["aprovado"]:
        prop["motivo"] = "Revisão reprovou: " + "; ".join(rev["problemas"])
        return prop
    teste = testar(d["codigo"], d["exemplos"])
    prop["teste"] = teste
    if not teste["ok"]:
        prop["motivo"] = "Teste na caixa de areia falhou: " + teste["erro"]
        return prop
    pasta_saida = Path(pasta_saida)
    with tempfile.TemporaryDirectory(prefix="nexus_pacote_") as fonte:
        (Path(fonte) / f"{d['id']}.py").write_text(d["codigo"], encoding="utf-8")
        pasta_saida.mkdir(parents=True, exist_ok=True)
        pacote = L.empacotar(fonte, pasta_saida / d["id"], {
            "id": d["id"], "nome": d["nome"], "versao": "1.0", "autor": autor, "descricao": d["descricao"],
            "permissoes": rev["permissoes"]})
    prop.update(ok=True, pacote=str(pacote))
    try:
        prop["versao"] = guardar_versao(d["id"], dict(d, permissoes=rev["permissoes"]), pasta_saida)
    except Exception:
        _engolida("core/fabrica_plugins.py:161")
    return prop


# ── versões (3.9) ────────────────────────────────────────────────────────────
def _pasta_versoes(pasta_saida: Path, pid: str) -> Path:
    return Path(pasta_saida) / "versoes" / _limpar_id(pid)


def guardar_versao(pid: str, d: dict, pasta_saida: Path, agora: float | None = None) -> int:
    """Guarda o código desta versão (v1, v2…) e devolve o número."""
    import time
    pasta = _pasta_versoes(pasta_saida, pid)
    pasta.mkdir(parents=True, exist_ok=True)
    n = max([int(p.stem[1:]) for p in pasta.glob("v*.json") if p.stem[1:].isdigit()] or [0]) + 1
    (pasta / f"v{n}.json").write_text(json.dumps({
        "versao": n, "ts": time.time() if agora is None else agora, "id": d["id"], "nome": d["nome"], "descricao": d["descricao"],
        "codigo": d["codigo"], "exemplos": d.get("exemplos") or [{}], "permissoes": d.get("permissoes") or []},
        ensure_ascii=False), encoding="utf-8")
    return n


def versoes(pid: str, pasta_saida: Path) -> list[dict]:
    out = []
    for p in sorted(_pasta_versoes(pasta_saida, pid).glob("v*.json"), key=lambda x: int(x.stem[1:]) if x.stem[1:].isdigit() else 0):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append({"versao": d["versao"], "ts": d["ts"], "descricao": d["descricao"], "permissoes": d["permissoes"],
                        "linhas": d["codigo"].count("\n") + 1})
        except Exception:
            continue
    return out


def ler_versao(pid: str, n: int, pasta_saida: Path) -> dict | None:
    try:
        return json.loads((_pasta_versoes(pasta_saida, pid) / f"v{int(n)}.json").read_text(encoding="utf-8"))
    except Exception:
        return None


def comparar(pid: str, a: int, b: int, pasta_saida: Path) -> dict | None:
    """O que mudou entre duas versões: linhas novas/removidas, permissões que apareceram e o diff curto."""
    va, vb = ler_versao(pid, a, pasta_saida), ler_versao(pid, b, pasta_saida)
    if not va or not vb:
        return None
    diff = list(difflib.unified_diff(va["codigo"].splitlines(), vb["codigo"].splitlines(), f"v{a}", f"v{b}", lineterm="", n=1))
    novas = [l for l in diff if l.startswith("+") and not l.startswith("+++")]
    tiradas = [l for l in diff if l.startswith("-") and not l.startswith("---")]
    pa, pb = set(va["permissoes"]), set(vb["permissoes"])
    return {"de": a, "para": b, "linhas_novas": len(novas), "linhas_removidas": len(tiradas),
            "permissoes_novas": sorted(pb - pa), "permissoes_removidas": sorted(pa - pb), "diff": "\n".join(diff[:80])}


def reempacotar(pid: str, n: int, pasta_saida: Path, autor: str = "NEXUS (gerado)") -> dict:
    """Volta para a versão `n`: revisa e testa de novo e gera o pacote. NÃO instala (isso pede CONFIRMAR)."""
    v = ler_versao(pid, n, pasta_saida)
    if not v:
        return {"ok": False, "motivo": f"Não existe a versão {n}."}
    rev = revisar(v["codigo"])
    prop = {"ok": False, **{k: v[k] for k in ("id", "nome", "descricao", "codigo", "exemplos")}, **rev, "teste": None, "pacote": ""}
    if not rev["aprovado"]:
        prop["motivo"] = "Revisão reprovou: " + "; ".join(rev["problemas"])
        return prop
    teste = testar(v["codigo"], v["exemplos"])
    prop["teste"] = teste
    if not teste["ok"]:
        prop["motivo"] = "Teste na caixa de areia falhou: " + teste["erro"]
        return prop
    with tempfile.TemporaryDirectory(prefix="nexus_pacote_") as fonte:
        (Path(fonte) / f"{v['id']}.py").write_text(v["codigo"], encoding="utf-8")
        Path(pasta_saida).mkdir(parents=True, exist_ok=True)
        pacote = L.empacotar(fonte, Path(pasta_saida) / f"{v['id']}_v{n}", {
            "id": v["id"], "nome": v["nome"], "versao": f"1.{n}", "autor": autor, "descricao": v["descricao"],
            "permissoes": rev["permissoes"]})
    prop.update(ok=True, pacote=str(pacote))
    return prop


_PROMPT_EVOLUIR = """Improve this existing NEXUS plugin as asked. Reply JSON only, same shape:
{{"id": "{pid}", "nome": "...", "descricao": "...", "codigo": "<full new python source>", "exemplos": [{{...}}]}}
Keep TOOL = {{name, description, parameters, handler(parameters, **kwargs) -> str}}; standard library only; no eval/exec/subprocess.
CURRENT CODE:
{codigo}
CHANGE REQUEST: {pedido}"""


def evoluir(pid: str, pedido: str, llm, pasta_saida: Path, autor: str = "NEXUS (gerado)") -> dict:
    """Pede ao modelo uma nova versão a partir da última guardada; revisa, testa, guarda como vN+1 e empacota."""
    vs = versoes(pid, pasta_saida)
    if not vs:
        return {"ok": False, "motivo": "Não conheço esse plugin gerado."}
    atual = ler_versao(pid, vs[-1]["versao"], pasta_saida)
    d = extrair_codigo(llm(_PROMPT_EVOLUIR.format(pid=atual["id"], codigo=atual["codigo"][:8000], pedido=str(pedido)[:800])) or "")
    if not d:
        return {"ok": False, "motivo": "O modelo não devolveu uma nova versão válida."}
    d["id"] = atual["id"]
    rev = revisar(d["codigo"])
    prop = {"ok": False, **d, **rev, "teste": None, "pacote": ""}
    if not rev["aprovado"]:
        prop["motivo"] = "Revisão reprovou: " + "; ".join(rev["problemas"])
        return prop
    teste = testar(d["codigo"], d["exemplos"])
    prop["teste"] = teste
    if not teste["ok"]:
        prop["motivo"] = "Teste na caixa de areia falhou: " + teste["erro"]
        return prop
    d["permissoes"] = rev["permissoes"]
    n = guardar_versao(d["id"], d, pasta_saida)
    return dict(reempacotar(d["id"], n, pasta_saida, autor), versao=n)


def resumo(p: dict) -> str:
    perms = ", ".join(p.get("permissoes") or []) or "nenhuma"
    return (f"Plugin “{p.get('nome')}” — {p.get('descricao')}\nPermissões: {perms}\n"
            f"Teste na caixa de areia: {'passou' if (p.get('teste') or {}).get('ok') else 'não rodou'}\n"
            "Gerado por IA e SEM assinatura de autor: instale só se leu o resumo.")
