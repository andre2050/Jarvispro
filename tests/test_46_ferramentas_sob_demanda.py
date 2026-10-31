"""4.6.0 — perfil dinâmico: tool_search + tool_call."""
import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from core import action_loader as L
from core import carga_ferramentas as C

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def reais():
    spec = importlib.util.spec_from_file_location("td_real2", RAIZ / "assistant" / "tool_declarations.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    reg = L.discover_actions(RAIZ / "actions", {d["name"] for d in m.TOOL_DECLARATIONS}, lambda s: None, desativadas=set())
    return list(m.TOOL_DECLARATIONS) + reg.get_tool_declarations()


def _d(nome, desc="", **props):
    return {"name": nome, "description": desc, "parameters": {"type": "OBJECT", "properties": props}}


def test_dinamico_mostra_o_basico_e_as_duas_de_busca(reais):
    nomes = [d["name"] for d in C.filtrar(reais, "dinamico", usadas=set(), fixadas=[])]
    assert "tool_search" in nomes and "tool_call" in nomes and "open_app" in nomes
    assert "printer_control" not in nomes and "kanban_board" not in nomes
    assert len(nomes) < len(reais) / 2
    assert nomes.count("tool_search") == 1


def test_dinamico_inclui_as_usadas_e_fixadas(reais):
    nomes = {d["name"] for d in C.filtrar(reais, "dinamico", usadas={"kanban_board"}, fixadas=["study"])}
    assert {"kanban_board", "study"} <= nomes


def test_dinamico_nao_cai_para_tudo_com_pouco_historico():
    d = [_d("open_app"), _d("coisa_rara")]
    nomes = [x["name"] for x in C.filtrar(d, "dinamico", usadas=set(), fixadas=[])]
    assert "coisa_rara" not in nomes and "tool_search" in nomes      # diferente de "recentes", que mostraria tudo


def test_aviso_do_dinamico_manda_procurar_antes_de_desistir():
    a = C.aviso_para_o_modelo("dinamico")
    assert "tool_search" in a and "tool_call" in a


def test_busca_acha_o_que_esta_escondido(reais):
    r = C.buscar(reais, "quero imprimir um arquivo")
    assert "printer_control" in r.splitlines()[1] and "parâmetros" in r
    assert "kanban_board" in C.buscar(reais, "quadro kanban do obsidian")
    assert "study" in C.buscar(reais, "cartões de estudo e quiz")


def test_busca_nao_devolve_as_proprias_ferramentas_de_busca(reais):
    d = reais + C.declaracoes_gateway()
    assert "tool_search:" not in C.buscar(d, "procurar ferramenta tool search") and "tool_call:" not in C.buscar(d, "tool call chamar")


def test_busca_vazia_ou_sem_resultado():
    assert "Diga o que você precisa" in C.buscar([_d("a", "x")], "   ")
    assert C.buscar([_d("a", "abrir programa")], "zzzzzz yyyyyy") == "Não achei nenhuma ferramenta para isso."


def test_busca_mostra_parametros_obrigatorios_e_opcoes():
    d = {"name": "x_tool", "description": "faz x", "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["a", "b"]}, "n": {"type": "INTEGER"}}, "required": ["action"]}}
    r = C.buscar([d], "faz x")
    assert "action* (a|b)" in r and "n (integer)" in r


def test_resolver_chamada():
    ok = {"printer_control", "study"}
    assert C.resolver_chamada({"name": "study", "args": {"action": "stats"}}, ok) == ("study", {"action": "stats"}, "")
    assert C.resolver_chamada({"name": "study", "args": '{"action": "stats"}'}, ok)[1] == {"action": "stats"}
    assert C.resolver_chamada({"name": "study"}, ok) == ("study", {}, "")
    for ruim, trecho in (({}, "nome"), ({"name": "nao_existe"}, "não existe"), ({"name": "tool_call"}, "dentro de tool_call"),
                         ({"name": "tool_search"}, "dentro de tool_call"), ({"name": "study", "args": "lixo"}, "objeto"),
                         ({"name": "study", "args": [1]}, "objeto")):
        r = C.resolver_chamada(ruim, ok)
        assert r[0] == "" and trecho in r[2]


# ── o caminho de execução ─────────────────────────────────────────────────────

class _Registro:
    def __init__(self, *nomes):
        self.nomes = nomes

    def get_tool_declarations(self):
        return [{"name": n} for n in self.nomes]


def _app(monkeypatch, executadas):
    from assistant.tools import ToolsMixin
    from google.genai import types

    class App(ToolsMixin):
        _action_registry = _Registro("study", "kanban_board")
        _plugin_registry = _Registro("meu_plugin")

        async def _executar_ferramenta(self, fc):
            executadas.append((fc.name, dict(fc.args or {}), fc.id))
            return types.FunctionResponse(id=fc.id, name=fc.name, response={"result": f"rodou {fc.name}"})
    monkeypatch.setattr(C, "TODAS", [_d("study", "cartões de estudo"), _d("meu_plugin", "faz algo do plugin")])
    return App(), types


def test_tool_call_roda_a_ferramenta_de_verdade_e_responde_como_tool_call(monkeypatch):
    feitas = []
    app, types = _app(monkeypatch, feitas)
    fc = types.FunctionCall(id="c1", name="tool_call", args={"name": "study", "args": {"action": "stats"}})
    r = asyncio.run(app._execute_tool(fc))
    assert feitas == [("study", {"action": "stats"}, "c1")]
    assert r.name == "tool_call" and r.id == "c1" and r.response["result"] == "rodou study"


def test_tool_call_de_plugin_e_de_nome_falso(monkeypatch):
    feitas = []
    app, types = _app(monkeypatch, feitas)
    r = asyncio.run(app._execute_tool(types.FunctionCall(id="c2", name="tool_call", args={"name": "meu_plugin"})))
    assert feitas[0][0] == "meu_plugin" and r.name == "tool_call"
    r = asyncio.run(app._execute_tool(types.FunctionCall(id="c3", name="tool_call", args={"name": "shutdown_jarvis"})))
    assert len(feitas) == 1 and r.response["result"].startswith("[failed]")       # fixas e desconhecidas não passam pelo gateway
    r = asyncio.run(app._execute_tool(types.FunctionCall(id="c4", name="tool_call", args={"name": "tool_call"})))
    assert len(feitas) == 1 and "[failed]" in r.response["result"]


def test_tool_search_responde_sem_executar_nada(monkeypatch):
    feitas = []
    app, types = _app(monkeypatch, feitas)
    r = asyncio.run(app._execute_tool(types.FunctionCall(id="s1", name="tool_search", args={"query": "estudo cartões"})))
    assert not feitas and r.name == "tool_search" and "study" in r.response["result"]


def test_ferramenta_comum_passa_direto(monkeypatch):
    feitas = []
    app, types = _app(monkeypatch, feitas)
    r = asyncio.run(app._execute_tool(types.FunctionCall(id="x", name="study", args={"action": "stats"})))
    assert feitas == [("study", {"action": "stats"}, "x")] and r.name == "study"


def test_acao_tool_load_aceita_o_novo_perfil(monkeypatch):
    from actions import carga_ferramentas as A
    from core import preferences as P
    guardado = {}
    monkeypatch.setattr(P, "save", lambda v: guardado.update(v))
    assert A.tool_load({"action": "set", "mode": "dinamico"}).startswith("[done]") and guardado["carga_ferramentas"] == "dinamico"
