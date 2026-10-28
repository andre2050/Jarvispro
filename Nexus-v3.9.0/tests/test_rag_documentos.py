"""Memória de documentos (RAG pessoal): pastas opt-in, leitura, trechos, busca com fonte e atualização incremental."""
import os
import time

import pytest

from core import rag_documentos as RD


@pytest.fixture
def cenario(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "contrato.txt").write_text(
        "CONTRATO DE ALUGUEL\n\nCláusula 7. Em caso de rescisão antecipada pelo locatário, será cobrada multa "
        "equivalente a três meses de aluguel, proporcional ao tempo restante do contrato.\n\n"
        "Cláusula 8. O reajuste anual do aluguel seguirá o índice IGP-M.\n", encoding="utf-8")
    (docs / "receita.md").write_text(
        "# Bolo de cenoura\n\nMisture as cenouras com ovos e óleo no liquidificador. Asse por quarenta minutos "
        "em forno médio. A cobertura leva chocolate e leite.\n" * 3, encoding="utf-8")
    (docs / "garantia.txt").write_text(
        "Garantia do notebook: doze meses contra defeito de fabricação, com nota fiscal. "
        "Não cobre queda, líquido derramado ou mau uso.\n" * 2, encoding="utf-8")
    (docs / "imagem.png").write_bytes(b"\x89PNG....")          # extensão fora da lista: ignorada
    (docs / "vazio.txt").write_text("", encoding="utf-8")        # vazio: ignorado
    sub = docs / "node_modules"
    sub.mkdir()
    (sub / "lixo.txt").write_text("isto não deve entrar no índice " * 5, encoding="utf-8")
    ind = RD.IndiceDocumentos(arquivo=tmp_path / "rag.npz", arq_pastas=tmp_path / "pastas.json")
    return docs, ind, tmp_path


def test_cortar_respeita_tamanho_e_localiza_linhas():
    texto = "\n".join(f"Linha {i}: " + "palavra " * 12 for i in range(1, 40))
    partes = RD.cortar(texto, tamanho=300, sobre=50)
    assert len(partes) > 3
    assert all(len(t) <= 320 for _, t in partes)
    assert partes[0][0] == 1 and partes[-1][0] > partes[0][0]
    assert RD.cortar("   \n  ") == []
    assert RD.cortar("curto") == []                  # pedaço minúsculo não vira trecho


def test_pastas_sao_opt_in_e_recusam_lugares_perigosos(tmp_path):
    arq = tmp_path / "pastas.json"
    assert RD.listar_pastas(arq) == []
    ok, _ = RD.adicionar_pasta(str(tmp_path), arq)
    assert ok and RD.listar_pastas(arq) == [str(tmp_path.resolve())]
    ok, msg = RD.adicionar_pasta(str(tmp_path / "nao_existe"), arq)
    assert not ok and "Não achei" in msg
    ok, _ = RD.adicionar_pasta(str(RD.Path.home()), arq)
    assert not ok                                    # pasta pessoal inteira
    ok, _ = RD.adicionar_pasta(os.path.abspath(os.sep), arq)
    assert not ok                                    # raiz do disco
    ok, msg = RD.adicionar_pasta(str(RD._BASE), arq)
    assert not ok and "NEXUS" in msg                 # chaves e memórias do próprio NEXUS
    ok, _ = RD.remover_pasta(tmp_path.name, arq)
    assert ok and RD.listar_pastas(arq) == []


def test_indexa_so_o_que_deve_e_busca_com_fonte(cenario):
    docs, ind, _ = cenario
    r = ind.atualizar(pastas=[str(docs)])
    assert r["arquivos"] == 3 and r["trechos"] >= 3
    nomes = {t["nome"] for t in ind.trechos}
    assert nomes == {"contrato.txt", "receita.md", "garantia.txt"}      # sem png, vazio nem node_modules

    achados = ind.buscar("quanto é a multa se eu sair antes do fim do contrato?", k=3)
    assert achados and achados[0][1]["nome"] == "contrato.txt"
    assert "multa" in achados[0][1]["texto"].lower()
    assert RD.citacao(achados[0][1]).startswith("contrato.txt, ")

    achados = ind.buscar("defeito de fabricação do notebook", k=3)
    assert achados[0][1]["nome"] == "garantia.txt"
    assert ind.buscar("xyzqwerty inexistente", k=3) == []


def test_filtro_por_pasta_e_limite_por_arquivo(cenario):
    docs, ind, _ = cenario
    ind.atualizar(pastas=[str(docs)])
    assert ind.buscar("aluguel", pasta="outra_pasta") == []
    achados = ind.buscar("cenoura ovos óleo chocolate", k=5)
    assert achados and {t["nome"] for _, t in achados} == {"receita.md"}


def test_atualizacao_incremental_nova_alterada_e_removida(cenario):
    docs, ind, _ = cenario
    ind.atualizar(pastas=[str(docs)])

    r = ind.atualizar(pastas=[str(docs)])
    assert (r["novos_arquivos"], r["alterados"], r["removidos"]) == (0, 0, 0)      # nada mudou

    novo = docs / "viagem.txt"
    novo.write_text("Reserva do hotel em Recife para dezembro, três noites perto da praia de Boa Viagem.", encoding="utf-8")
    r = ind.atualizar(pastas=[str(docs)])
    assert r["novos_arquivos"] == 1
    assert ind.buscar("hotel em Recife", k=2)[0][1]["nome"] == "viagem.txt"

    time.sleep(0.01)
    novo.write_text("Reserva cancelada. Voo remarcado para janeiro com destino a Salvador na Bahia.", encoding="utf-8")
    os.utime(novo, ns=(time.time_ns() + 5_000_000_000, time.time_ns() + 5_000_000_000))
    r = ind.atualizar(pastas=[str(docs)])
    assert r["alterados"] == 1
    assert ind.buscar("voo para Salvador", k=2)[0][1]["nome"] == "viagem.txt"
    assert not any("Recife" in t["texto"] for t in ind.trechos)                    # texto velho saiu

    novo.unlink()
    r = ind.atualizar(pastas=[str(docs)])
    assert r["removidos"] == 1 and "viagem.txt" not in {t["nome"] for t in ind.trechos}


def test_persiste_em_disco_e_recarrega(cenario):
    docs, ind, tmp = cenario
    ind.atualizar(pastas=[str(docs)])
    de_novo = RD.IndiceDocumentos(arquivo=tmp / "rag.npz", arq_pastas=tmp / "pastas.json")
    assert len(de_novo.trechos) == len(ind.trechos)
    assert de_novo.buscar("multa de rescisão", k=1)[0][1]["nome"] == "contrato.txt"


def test_arquivo_ilegivel_nao_derruba_a_indexacao(cenario):
    docs, ind, _ = cenario
    (docs / "quebrado.pdf").write_bytes(b"isto nao e um pdf de verdade")
    (docs / "quebrado.docx").write_bytes(b"nem isto e um docx")
    r = ind.atualizar(pastas=[str(docs)])
    assert r["arquivos"] >= 3                       # os bons continuam entrando
    assert ind.buscar("multa", k=1)


def test_leitores_de_docx_e_pptx(tmp_path):
    docx = pytest.importorskip("docx")
    d = docx.Document()
    d.add_paragraph("Ata da reunião: ficou decidido adiar o lançamento do produto para março.")
    d.save(tmp_path / "ata.docx")
    leitura = RD.ler_arquivo(tmp_path / "ata.docx")
    assert leitura and "adiar o lançamento" in leitura[0][1]

    pptx = pytest.importorskip("pptx")
    p = pptx.Presentation()
    s = p.slides.add_slide(p.slide_layouts[5])
    s.shapes.title.text = "Resultados do trimestre"
    p.save(tmp_path / "apres.pptx")
    leitura = RD.ler_arquivo(tmp_path / "apres.pptx")
    assert leitura[0][0] == "slide 1" and "Resultados" in leitura[0][1]


def test_acao_memoria_semantica_docs_ponta_a_ponta(cenario, monkeypatch):
    from actions import memoria_semantica as M
    docs, ind, tmp = cenario
    monkeypatch.setattr(RD, "ARQ_PASTAS", tmp / "pastas.json")
    monkeypatch.setattr(RD, "_indice", ind)

    assert "Nenhuma pasta" in M.memoria_semantica({"action": "docs_search", "query": "multa"})
    r = M.memoria_semantica({"action": "add_folder", "folder": str(docs)})
    assert r.startswith("[done]")
    r = M.memoria_semantica({"action": "docs_reindex"})
    assert r.startswith("[done]") and "3 arquivo(s)" in r
    r = M.memoria_semantica({"action": "docs_search", "query": "multa por rescisão antecipada"})
    assert "[contrato.txt," in r and "cite a fonte" in r
    assert "Não achei" in M.memoria_semantica({"action": "docs_search", "query": "zzzqqq inexistente"})
    assert str(docs.resolve()) in M.memoria_semantica({"action": "folders"})
    r = M.memoria_semantica({"action": "add_folder", "folder": str(RD._BASE)})
    assert r.startswith("[failed]")
    assert M.TOOL["parameters"]["properties"]["folder"]
