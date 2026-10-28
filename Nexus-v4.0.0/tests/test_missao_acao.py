"""Ferramenta de voz 'missao', permissões dos especialistas e rotas do painel."""
import json
import pytest

from core import missoes as M


class _Reg:
    def __init__(self):
        self.ran = []

    def has(self, n):
        return n in ("web_search", "send_message")

    def get_tool_declarations(self):
        return [{"name": "web_search", "description": "busca", "parameters": {"properties": {"query": {"description": "q"}}}}]

    def run(self, n, p, c=None):
        self.ran.append(n)
        return "[done] ok"


@pytest.fixture
def mod(tmp_path, monkeypatch):
    from actions import missao as A
    monkeypatch.setattr(M, "PASTA", tmp_path / "m")
    A._motor = A._gerente = None
    A.bind(_Reg())
    mot = A.motor()
    mot.pasta = tmp_path / "m"
    mot.planejar = lambda o, c: [{"titulo": "buscar", "tool": "web_search", "args": {"query": "x"}}]
    mot.conferir = lambda o, p: ""
    yield A
    if A._gerente:
        A._gerente.parar()
    A._motor = A._gerente = None


def test_tool_registrada_e_status_vazio(mod):
    assert mod.TOOL["name"] == "missao"
    assert "Nenhuma" in mod.missao({"action": "status"})
    assert "Nenhuma" in mod.missao({"action": "list"})


def test_start_sem_registry_falha_claro():
    from actions import missao as A
    A._registry = None
    assert "[failed]" in A.missao({"action": "start", "goal": "x"})


def test_proibidas_nao_entram_no_catalogo_e_executor_recusa(mod):
    ok, txt = mod._executar("missao", {}, {})[0], mod._executar("missao", {}, {})[1]
    assert ok == "failed" and "não pode" in txt


def test_especialista_desconhecido_falha(mod):
    st, _ = mod._executar("especialista", {"agente": "xyz", "tarefa": "t"}, {})
    assert st == "failed"


def test_permissoes_dos_agentes(tmp_path):
    from actions import orquestrador as O
    arq = tmp_path / "agentes.json"
    r = O.definir_ferramentas("pesquisador", ["web_search", "agent_task"], existentes={"web_search", "agent_task"}, arq=arq)
    saved = O.carregar_permissoes(arq)
    assert "agent_task" not in json.dumps(saved)
    assert "agenda" in O.AGENTES and "financas" in O.AGENTES


def test_start_ponta_a_ponta_roda_em_segundo_plano_e_conclui(mod):
    import time
    mod.gerente().ritmo_s = 0.01
    out = mod.missao({"action": "start", "goal": "pesquisar algo bem simples"})
    assert out.startswith("[done]") and "começou em segundo plano" in out
    mid = out.split()[2]
    t0 = time.time()
    while time.time() - t0 < 10 and M.carregar(mid)["estado"] not in M.ESTADOS_FINAIS:
        time.sleep(0.05)
    assert M.carregar(mid)["estado"] == "concluida"
    assert "web_search" in mod._registry.ran


def test_start_com_passo_sensivel_espera_aprovacao_e_depois_roda(mod):
    import time
    mod.gerente().ritmo_s = 0.01
    mod.motor().planejar = lambda o, c: [{"titulo": "avisar", "tool": "send_message", "args": {"to": "x"}}]
    out = mod.missao({"action": "start", "goal": "avisar o João que atrasei"})
    assert "esperando a aprovação" in out
    mid = out.split()[2]
    assert "send_message" not in mod._registry.ran
    assert mod.missao({"action": "approve", "id": mid}).startswith("[done]")
    t0 = time.time()
    while time.time() - t0 < 10 and M.carregar(mid)["estado"] not in M.ESTADOS_FINAIS:
        if M.carregar(mid)["decisoes"] and any(d["estado"] == "pendente" for d in M.carregar(mid)["decisoes"]):
            mod.missao({"action": "approve", "id": mid})
        time.sleep(0.05)
    assert "send_message" in mod._registry.ran
