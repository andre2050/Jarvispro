from datetime import date

import pytest

from core import competicao as C
from core import historico_longo as H

HOJE = date(2026, 10, 28)
DOCS = [
    {"fonte": "conversas", "texto": "O usuário desinstalou o Visual Studio para resolver problemas de desempenho no computador.", "quando": "2026-10-28"},
    {"fonte": "conversas", "texto": "Conversa sobre o plano de saúde: decidiu manter o plano atual e pesquisar reajuste.", "quando": "2025-11-03"},
    {"fonte": "diario", "texto": "Troquei o óleo do carro e revisei os freios na oficina.", "quando": "2026-09-15"},
    {"fonte": "notas", "texto": "Meu cartão é 4111 1111 1111 1111 validade 12/30", "quando": "2026-10-01"},
]


@pytest.fixture(autouse=True)
def limpa():
    C._variantes.clear()
    yield
    C._variantes.clear()


def test_ingere_sem_duplicar_e_nunca_guarda_segredo(tmp_path):
    arq = tmp_path / "h.jsonl"
    r = H.ingerir(DOCS, arq, HOJE)
    assert r == {"novos": 3, "total": 3, "ignorados_segredo": 1}
    assert H.ingerir(DOCS, arq, HOJE)["novos"] == 0
    assert "4111" not in arq.read_text()


def test_lembra_conversa_de_um_ano_atras_por_palavras(tmp_path):
    arq = tmp_path / "h.jsonl"
    H.ingerir(DOCS, arq, HOJE)
    t = H.lembrar("plano de saúde", arq=arq, hoje=HOJE, competir=False)
    assert "03/11/2025" in t and "manter o plano" in t
    assert "Não achei" in H.lembrar("viagem para a lua", arq=arq, hoje=HOJE, competir=False)


def test_periodo_falado_filtra_resultados(tmp_path):
    arq = tmp_path / "h.jsonl"
    H.ingerir(DOCS, arq, HOJE)
    assert "óleo" in H.lembrar("carro mês passado", arq=arq, hoje=HOJE, competir=False)
    assert "Não achei" in H.lembrar("plano de saúde ontem", arq=arq, hoje=HOJE, competir=False)


def test_compacta_o_antigo_e_mantem_palavras_chave(tmp_path):
    arq = tmp_path / "h.jsonl"
    longo = "Reunião sobre reforma da cozinha. " + "detalhe " * 100
    H.ingerir([{"fonte": "diario", "texto": longo, "quando": "2025-01-10"}], arq, HOJE)
    e = H._ler(arq)[0]
    assert e["compacto"] and len(e["texto"]) <= H.TAM_COMPACTO + 1 and "cozinha" in e["tags"]
    assert H.buscar_palavras("reforma cozinha", arq=arq, hoje=HOJE)


def test_busca_competitiva_funciona_mesmo_sem_indice_semantico(tmp_path, monkeypatch):
    arq = tmp_path / "h.jsonl"
    H.ingerir(DOCS, arq, HOJE)
    monkeypatch.setattr(H, "buscar_semantica", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sem índice")))
    monkeypatch.setattr("core.competicao.ARQUIVO", tmp_path / "comp.json")
    for _ in range(5):
        assert "plano atual" in H.lembrar("plano saúde", arq=arq, hoje=HOJE)
    assert "palavras" in C.relatorio(tmp_path / "comp.json")


def test_esquecer_por_tema_e_tudo(tmp_path):
    arq = tmp_path / "h.jsonl"
    H.ingerir(DOCS, arq, HOJE)
    assert H.esquecer("plano saúde", arq) == 1
    assert "Não achei" in H.lembrar("plano saúde", arq=arq, hoje=HOJE, competir=False)
    assert H.esquecer("", arq) == 0 and H.esquecer_tudo(arq) == 2 and "vazio" in H.resumo(arq)


def test_limite_maximo_de_entradas(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "MAX_ENTRADAS", 5)
    arq = tmp_path / "h.jsonl"
    H.ingerir([{"fonte": "n", "texto": f"anotação {i} sobre coisa{i}", "quando": f"2026-10-{i + 1:02d}"} for i in range(12)], arq, HOJE)
    assert len(H._ler(arq)) == 5 and H._ler(arq)[-1]["data"] == "2026-10-12"
