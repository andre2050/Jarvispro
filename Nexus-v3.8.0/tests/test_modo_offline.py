"""3.3 — modo offline (core/conexao.py)."""
import pytest

from core import conexao as C


@pytest.fixture(autouse=True)
def _reset():
    C._estado.update(online=True, checado_em=0.0)
    yield
    C._estado.update(online=True, checado_em=0.0)


def test_online_nao_bloqueia_nada():
    assert C.bloqueio("web_search", testar=lambda: True) is None
    assert C.bloqueio("open_app", testar=lambda: False) is None          # local: nunca bloqueia


def test_offline_bloqueia_so_o_que_precisa_de_rede():
    off = lambda: False
    msg = C.bloqueio("web_search", testar=off)
    assert msg and msg.startswith("[failed]") and "Sem internet" in msg
    for local in ("tarefas", "quick_notes", "reminder", "routines", "open_app", "diario", "timer_action"):
        assert C.bloqueio(local, testar=off) is None, local


def test_resultado_vale_alguns_segundos_para_nao_pesar():
    chamadas = []

    def t():
        chamadas.append(1)
        return True
    assert C.tem_internet(agora=100.0, testar=t) and C.tem_internet(agora=105.0, testar=t)
    assert len(chamadas) == 1
    assert C.tem_internet(agora=100.0 + C.CACHE_S + 1, testar=t) and len(chamadas) == 2
    assert C.tem_internet(forcar=True, agora=101.0, testar=t) and len(chamadas) == 3


def test_verificar_diz_quando_o_estado_mudou():
    assert C.verificar(testar=lambda: True) == (False, True)
    assert C.verificar(testar=lambda: False) == (True, False)
    assert C.verificar(testar=lambda: False) == (False, False)
    assert C.verificar(testar=lambda: True) == (True, True)


def test_erro_no_teste_nunca_bloqueia():
    def quebra():
        raise RuntimeError("x")
    assert C.tem_internet(forcar=True, testar=quebra) is True


def test_textos_e_ferramenta_de_voz():
    assert "Ollama" in C.texto_offline() and "pesquisa na web" in C.texto_offline()
    assert "Estou sem internet" in C.texto_estado(testar=lambda: False)
    assert C.texto_estado(testar=lambda: True).startswith("Estou com internet")
    from actions.conexao import TOOL, conexao
    assert TOOL["name"] == "conexao"
    assert "internet" in conexao({"action": "offline"}).lower()


def test_a_lista_de_ferramentas_de_rede_so_tem_ferramentas_que_existem():
    from pathlib import Path
    import re
    nomes = set()
    for f in (Path(__file__).resolve().parent.parent / "actions").glob("*.py"):
        m = re.search(r'^    "name": "([a-z_]+)"', f.read_text(encoding="utf-8"), re.M)
        if m:
            nomes.add(m.group(1))
    assert C.PRECISAM_DE_INTERNET <= nomes
