"""Como a IA do NEXUS funciona: estado das 4 áreas, tipos de IA e a função de voz."""
from core import ia_status as st


def test_quatro_areas_com_conceito_e_estado():
    areas = st.tudo()
    assert [a.chave for a in areas] == ["ml", "dl", "pln", "visao"]
    for a in areas:
        assert a.resumo and a.no_nexus and a.itens
        ok, total = a.prontos
        assert 0 <= ok <= total


def test_resolver_area_aceita_portugues_e_ingles():
    assert st.resolver_area("machine learning") == "ml"
    assert st.resolver_area("o que é visão computacional?") == "visao"
    assert st.resolver_area("redes neurais") == "dl"
    assert st.resolver_area("NLP") == "pln"
    assert st.resolver_area("bom dia") is None


def test_tipos_dizem_a_verdade_sobre_o_que_existe():
    assert st.tipo("ani").existe is True
    assert st.tipo("agi").existe is False and st.tipo("asi").existe is False
    assert st.tipo("memoria").existe is True and st.tipo("mente").existe is False
    assert st.resolver_tipo("o que é superinteligência?") == "asi"
    assert st.resolver_tipo("teoria da mente") == "mente"
    assert st.resolver_tipo("memória limitada") == "memoria"
    # o NEXUS nunca se declara AGI/ASI
    assert "não é uma AGI" in st.explicar_tipo("agi")


def test_explicacoes_nao_repetem_frases():
    for chave in ("ani", "agi", "asi", "reativa", "memoria", "mente"):
        txt = st.explicar_tipo(chave)
        assert txt.count("Ainda não existe") <= 1


def test_funcao_de_voz():
    from actions.explicar_ia import TOOL, explicar_ia
    assert TOOL["name"] == "explicar_ia" and TOOL["handler"] is explicar_ia
    assert "Machine learning" in explicar_ia({"action": "explain", "area": "ml"})
    assert "ANI" in explicar_ia({"action": "types"})
    assert "Superinteligência" in explicar_ia({"action": "types", "type": "asi"})
    assert "dados" in explicar_ia({"action": "learn"})


def test_painel_abre_sem_janela():
    import pytest
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication, QWidget
    from ui.overlays.ia_painel import IaPainelOverlay
    _app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.resize(1000, 700)
    ov = IaPainelOverlay(parent=host, aba="tipos")
    assert ov._chips["tipos"].isChecked()
    ov._fechar()
