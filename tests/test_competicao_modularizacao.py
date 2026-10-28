import pytest

from core import competicao as C
from core import isa_modularizacao as M


@pytest.fixture(autouse=True)
def limpo():
    C._variantes.clear()
    yield
    C._variantes.clear()


def _fake_relogio(passos):
    it = iter(passos)
    return lambda: next(it)


def test_variante_nova_e_testada_antes_de_ser_julgada(tmp_path):
    arq = tmp_path / "c.json"
    C.registrar("busca", "a", lambda x: "A")
    C.registrar("busca", "b", lambda x: "B")
    usadas = [C.executar("busca", 1, arq=arq, aleatorio=lambda: 0.99)[1] for _ in range(6)]
    assert set(usadas) == {"a", "b"}                                       # as duas foram experimentadas


def test_fica_com_a_melhor_e_cai_para_a_proxima_quando_falha(tmp_path):
    arq = tmp_path / "c.json"
    C.registrar("busca", "boa", lambda x: "ok", valida=lambda r: r == "ok")
    C.registrar("busca", "ruim", lambda x: 1 / 0)
    for _ in range(8):
        res, nome = C.executar("busca", 1, arq=arq, aleatorio=lambda: 0.99)
        assert (res, nome) == ("ok", "boa")                                # a ruim quebra mas o usuário nunca vê
    assert C.ranking("busca", arq=arq)[0][0] == "boa"


def test_restricao_rapido_prefere_a_mais_veloz(tmp_path):
    arq = tmp_path / "c.json"
    C.registrar("c", "lenta_certa", lambda: 1)
    C.registrar("c", "rapida", lambda: 1)
    d = {"c": {"fixada": "", "v": {"lenta_certa": {"n": 10, "ok": 10, "ms": 10 * 4000.0, "aposentada": False},
                                   "rapida": {"n": 10, "ok": 8, "ms": 10 * 20.0, "aposentada": False}}}}
    C._gravar(d, arq)
    assert C.ranking("c", "rapido", arq)[0][0] == "rapida"
    assert C.ranking("c", "rapido", arq)[0][0] == "rapida"


def test_aposenta_quem_so_erra_mas_nunca_a_ultima(tmp_path):
    arq = tmp_path / "c.json"
    C.registrar("c", "boa", lambda: 1)
    C.registrar("c", "ruim", lambda: None, valida=lambda r: False)
    for _ in range(20):
        C.executar("c", arq=arq, aleatorio=lambda: 0.99)
    assert "aposentada" in C.relatorio(arq)
    assert [n for n, _ in C.ranking("c", arq=arq)] == ["boa"]
    C.reativar("c", "ruim", arq)
    assert {n for n, _ in C.ranking("c", arq=arq)} == {"boa", "ruim"}


def test_fixar_forca_a_escolha_e_todas_falhando_levanta(tmp_path):
    arq = tmp_path / "c.json"
    C.registrar("c", "x", lambda: "X")
    C.registrar("c", "y", lambda: "Y")
    C.fixar("c", "y", arq)
    assert C.executar("c", arq=arq)[1] == "y"
    with pytest.raises(C.SemVariante):
        C.fixar("c", "zzz", arq)
    C._variantes.clear()
    C.registrar("d", "q", lambda: 1 / 0)
    with pytest.raises(C.SemVariante):
        C.executar("d", arq=arq)
    with pytest.raises(C.SemVariante):
        C.executar("inexistente", arq=arq)


def test_exploracao_ocasional_experimenta_a_segunda(tmp_path):
    arq = tmp_path / "c.json"
    C.registrar("c", "a", lambda: "A")
    C.registrar("c", "b", lambda: "B")
    for _ in range(8):
        C.executar("c", arq=arq, aleatorio=lambda: 0.99)
    melhor = C.ranking("c", arq=arq)[0][0]
    ordem = C.escolher("c", arq=arq, aleatorio=iter([0.01, 0.0]).__next__)
    assert ordem[0] != melhor


CODIGO = "\n".join(
    [f"def telegram_{n}():\n" + "    x = 1\n" * 30 for n in "ab"] + [f"def agenda_{n}():\n" + "    y = 2\n" * 30 for n in "ab"] + ["def _util():\n    return 1\n"])


def test_agrupa_por_prefixo():
    g = M.agrupar(CODIGO)
    assert {x["nome"] for x in g} == {"telegram", "agenda"} and all(len(x["funcoes"]) == 2 for x in g)


def test_agrupa_por_quem_chama_quem_sem_prefixo():
    cod = "def a():\n    return b()\n\ndef b():\n    return 1\n\ndef c():\n    return d()\n\ndef d():\n    return 2\n"
    g = M.agrupar(cod)
    assert sorted(sorted(x["funcoes"]) for x in g) == [["a", "b"], ["c", "d"]]
    assert M.agrupar("def so_uma():\n    pass\n") == [] and M.agrupar("def (") == []


def test_planejar_ordena_por_risco_e_nao_mexe_em_nada(tmp_path):
    for sub in ("core",):
        (tmp_path / sub).mkdir()
    (tmp_path / "core" / "grande.py").write_text(CODIGO * 2)
    (tmp_path / "core" / "pequeno.py").write_text("def a_b():\n    pass\n")
    (tmp_path / "core" / "usa.py").write_text("from core import grande\n")
    antes = (tmp_path / "core" / "grande.py").read_text()
    r = M.planejar(tmp_path, limite=100)
    assert [c["arquivo"] for c in r["candidatos"]] == ["core/grande.py"]
    c = r["candidatos"][0]
    assert c["dependentes"] == 1 and c["grupos"][0]["modulo_novo"].startswith("core/grande_") and len(c["testes"]) == 3
    assert (tmp_path / "core" / "grande.py").read_text() == antes
    assert "Só planejei" in M.texto(r)
    assert "em dia" in M.texto({"candidatos": []})
