"""NEXUS Pro 2.3 — embeddings, memória semântica e verificador do roteador."""
import json

import numpy as np

from core import embeddings as E
from core import indice_semantico as IS
from core import roteador as R


def test_embedder_hash_aproxima_sentidos_e_afasta_o_resto():
    emb = E.EmbedderHash()
    textos = ["comprei passagem para Recife", "Corri 5 km no parque", "reunião com o cliente amanhã"]
    emb.ajustar(textos)
    M = emb.embed(textos)
    assert M.shape == (3, emb.dim)
    assert np.allclose(np.linalg.norm(M, axis=1), 1.0, atol=1e-4)
    q = emb.embed(["viagem"])[0]
    assert int(np.argmax(M @ q)) == 0
    q2 = emb.embed(["exercício físico"])[0]
    assert int(np.argmax(M @ q2)) == 1


def test_cosseno_top_ordena():
    M = np.eye(4, dtype=np.float32)
    top = E.cosseno_top(M[2], M, k=2)
    assert top[0][0] == 2 and top[0][1] > 0.99


def test_indice_busca_por_sentido_e_persiste(tmp_path):
    (tmp_path / "memory").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "quick_notes.json").write_text(json.dumps(
        [{"text": "comprar passagem para Recife", "at": 1}, {"text": "trocar o filtro da geladeira", "at": 2}]))
    (tmp_path / "memory" / "diario.json").write_text(json.dumps(
        [{"quando": "2026-10-01T10:00:00", "texto": "Corri 5 km no parque hoje", "humor": 4}]))
    idx = IS.Indice(tmp_path / "idx.npz", base=tmp_path)
    r = idx.atualizar(preferir="hash", forcar=True)
    assert r
    achados = idx.buscar("viagem", k=3)
    assert achados and "Recife" in achados[0][1]["texto"]
    achados = idx.buscar("exercício físico", k=3)
    assert achados and "Corri" in achados[0][1]["texto"]
    outro = IS.Indice(tmp_path / "idx.npz", base=tmp_path)          # recarrega do disco
    assert outro.buscar("viagem", k=1)


def test_indice_nao_acha_assunto_que_nao_existe(tmp_path):
    (tmp_path / "memory").mkdir(); (tmp_path / "config").mkdir()
    (tmp_path / "config" / "quick_notes.json").write_text(json.dumps([{"text": "comprar leite", "at": 1}]))
    idx = IS.Indice(tmp_path / "i.npz", base=tmp_path)
    idx.atualizar(preferir="hash", forcar=True)
    assert idx.buscar("zzzz qqqq", k=3) == []


def test_verificador_veta_frase_de_outra_funcao():
    v = R.Verificador()
    textos = ["abre o spotify", "abre o chrome", "abre o whatsapp", "anota comprar leite", "anota ligar pro joão",
              "salva a nota pagar a luz", "gastei 30 no mercado", "gastei 50 de uber", "quanto gastei esse mês",
              "registra um gasto de 20"]
    rot = ["open_app"] * 3 + ["note_add"] * 3 + ["none"] * 4
    v.construir(textos, rot)
    ok, _ = v.concorda("abre o discord", "open_app")
    assert ok
    ok, motivo = v.concorda("gastei 40 no mercado", "note_add")
    assert not ok and motivo
