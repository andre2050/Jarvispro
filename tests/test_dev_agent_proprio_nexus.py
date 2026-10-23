"""2.4.3 — o agente de código e o 'Nexus Pro': resposta na hora, sem círculo."""
import pytest

from actions import dev_agent as DA


@pytest.fixture
def raiz(tmp_path, monkeypatch):
    monkeypatch.setattr(DA, "_projects_root", lambda: tmp_path)
    return tmp_path


@pytest.mark.parametrize("nome", ["Nexus Pro", "o Nexus", "nexus", "Jarvis", "você mesmo", "Nexus-Pro"])
def test_pedido_para_mudar_o_proprio_nexus_e_explicado(raiz, nome):
    r = DA.dev_agent({"action": "modify", "project_name": nome, "description": "adicionar OpenCV"},
                     speak=lambda *_: pytest.fail("não devia ir para o segundo plano"))
    assert r.startswith("[failed]") and "does not change the NEXUS itself" in r and "system_update" in r


def test_projeto_inexistente_responde_na_hora_com_a_lista(raiz):
    (raiz / "site_padaria").mkdir()
    (raiz / "site_padaria" / "index.html").write_text("<h1>oi</h1>", encoding="utf-8")
    r = DA.dev_agent({"action": "modify", "project_name": "loja de roupas", "description": "x"},
                     speak=lambda *_: pytest.fail("não devia ir para o segundo plano"))
    assert r.startswith("[failed]") and "site_padaria" in r and "separate to-do list" in r


def test_projeto_do_agente_chamado_nexus_continua_editavel(raiz):
    (raiz / "nexus_site").mkdir()
    assert DA._conferir_projeto("nexus_site") is None


@pytest.mark.parametrize("nome", ["site da padaria", "assistente de vendas", "jogo da cobrinha"])
def test_nomes_comuns_nao_sao_o_nexus(nome):
    assert not DA._e_o_proprio_nexus(nome)
