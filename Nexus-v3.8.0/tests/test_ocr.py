"""OCR local: foto de recibo e PDF escaneado entram na memória de documentos (só com o OCR ligado)."""
import pytest

from core import ocr as OCR
from core import rag_documentos as RD

pytestmark = pytest.mark.skipif(not OCR.disponivel(), reason="Tesseract não instalado")


def _imagem(texto, caminho, pdf=False):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (1400, 420), "white")
    d = ImageDraw.Draw(img)
    try:
        fonte = ImageFont.truetype("DejaVuSans.ttf", 54)
    except Exception:
        fonte = ImageFont.load_default(size=54)
    d.text((40, 60), texto, fill="black", font=fonte)
    img.save(caminho, "PDF" if pdf else None)


@pytest.fixture
def cen(tmp_path, monkeypatch):
    monkeypatch.setattr(OCR, "ARQ_CONFIG", tmp_path / "cfg.json")
    docs = tmp_path / "docs"
    docs.mkdir()
    _imagem("RECIBO Mercado Central total 148 reais\nPAGAMENTO EM DINHEIRO NOTA 3321", docs / "recibo.png")
    _imagem("CONTRATO DE ALUGUEL multa de tres meses\nRESCISAO ANTECIPADA CLAUSULA SETIMA", docs / "scan.pdf", pdf=True)
    ind = RD.IndiceDocumentos(arquivo=tmp_path / "rag.npz", arq_pastas=tmp_path / "p.json")
    return docs, ind


def test_desligado_ignora_fotos_e_pdf_escaneado(cen):
    docs, ind = cen
    assert not OCR.ativo()
    ind.atualizar(pastas=[str(docs)])
    assert ind.trechos == []


def test_ligado_le_a_foto_e_o_pdf_escaneado(cen):
    docs, ind = cen
    OCR.definir_ativo(True)
    ind.atualizar(pastas=[str(docs)])
    nomes = {t["nome"] for t in ind.trechos}
    assert nomes == {"recibo.png", "scan.pdf"}
    a = ind.buscar("quanto foi o recibo do mercado", k=2)
    assert a and a[0][1]["nome"] == "recibo.png" and "148" in a[0][1]["texto"]
    b = ind.buscar("multa de rescisão antecipada do contrato", k=2)
    assert b and b[0][1]["nome"] == "scan.pdf" and "OCR" in b[0][1]["loc"]


def test_acao_liga_e_desliga(cen, monkeypatch):
    from actions import memoria_semantica as M
    docs, ind = cen
    monkeypatch.setattr(RD, "ARQ_PASTAS", docs.parent / "p.json")
    monkeypatch.setattr(RD, "_indice", ind)
    assert M.memoria_semantica({"action": "add_folder", "folder": str(docs)}).startswith("[done]")
    r = M.memoria_semantica({"action": "ocr_on"})
    assert r.startswith("[done]") and "2 arquivo(s)" in r
    assert "desligada" in M.memoria_semantica({"action": "ocr_off"})
    assert ind.trechos == []


def test_sem_tesseract_explica_o_que_falta(monkeypatch):
    from actions import memoria_semantica as M
    monkeypatch.setattr(OCR, "faltando", lambda: "instale o Tesseract OCR")
    assert "instale o Tesseract" in M.memoria_semantica({"action": "ocr_on"})
