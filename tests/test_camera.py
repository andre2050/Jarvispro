"""Visão da câmera (2.4.2): sem câmera de verdade — um VideoCapture falso."""
import io
import json

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
PIL = pytest.importorskip("PIL.Image")

from actions import computer_vision as CV
from actions import screen_processor as SP


class CameraFalsa:
    """Abre só nos (índice, driver) liberados; o 1º quadro vem preto, depois clareia."""
    liberadas: set = set()
    abertas: list = []

    def __init__(self, idx, be=0):
        self.ok = (idx, be) in self.liberadas
        self.lidos = 0
        CameraFalsa.abertas.append((idx, be))

    def isOpened(self):
        return self.ok

    def set(self, *a):
        return True

    def read(self):
        if not self.ok:
            return False, None
        self.lidos += 1
        brilho = 0 if self.lidos < 3 else 120
        return True, np.full((720, 1280, 3), brilho, np.uint8)

    def release(self):
        pass


@pytest.fixture
def camera(monkeypatch, tmp_path):
    CameraFalsa.abertas = []
    monkeypatch.setattr(CV.cv2, "VideoCapture", CameraFalsa)
    monkeypatch.setattr(CV, "_cam_boa", {})
    monkeypatch.setattr(CV, "_indice_configurado", lambda: None)
    monkeypatch.setattr(CV._vigia, "quadro_recente", lambda: None)
    monkeypatch.setattr(CV, "_no_windows", lambda: True)
    return CameraFalsa


def _jpeg(b):
    return np.asarray(PIL.open(io.BytesIO(b)))


def test_foto_do_gemini_em_hd_e_sem_o_quadro_preto(camera):
    camera.liberadas = {(0, cv2.CAP_DSHOW)}
    b, mime = SP._capture_camera()
    img = _jpeg(b)
    assert mime == "image/jpeg" and img.shape[:2] == (720, 1280)
    assert img.mean() > 100                                  # esperou a exposição


def test_driver_dshow_quebrado_cai_no_msmf(camera):
    camera.liberadas = {(0, cv2.CAP_MSMF)}
    SP._capture_camera()
    assert CV._cam_boa == {"idx": 0, "backend": cv2.CAP_MSMF}


def test_acha_a_camera_em_outro_indice(camera):
    camera.liberadas = {(2, cv2.CAP_DSHOW)}
    SP._capture_camera()
    assert CV._cam_boa["idx"] == 2


def test_sem_camera_explica_em_portugues(camera):
    camera.liberadas = set()
    with pytest.raises(CV.VisaoErro, match="não achei nenhuma câmera"):
        SP._capture_camera()


def test_vigia_ligada_empresta_o_quadro_em_vez_de_falhar(camera, monkeypatch):
    camera.liberadas = set()                                  # a vigia está com a câmera
    monkeypatch.setattr(CV._vigia, "quadro_recente", lambda: np.full((480, 640, 3), 90, np.uint8))
    assert _jpeg(SP._capture_camera()[0]).shape[:2] == (480, 640)
    assert camera.abertas == []


def test_deteccao_que_falha_nao_grava_camera_0(monkeypatch):
    gravados = []
    monkeypatch.setattr(SP, "_probe_camera", lambda *a, **k: False)
    monkeypatch.setattr(SP, "_save_config_key", lambda k, v: gravados.append((k, v)))
    assert SP._detect_camera_index() == 0
    assert gravados == []


def test_gravar_camera_preserva_a_chave_e_nao_estraga_arquivo_ilegivel(monkeypatch, tmp_path):
    arq = tmp_path / "api_keys.json"
    monkeypatch.setattr(SP, "_CONFIG_PATH", arq)
    arq.write_text(json.dumps({"gemini_api_key": "CHAVE"}), encoding="utf-8")
    SP._save_config_key("camera_index", 1)
    assert json.loads(arq.read_text(encoding="utf-8")) == {"gemini_api_key": "CHAVE", "camera_index": 1}
    arq.write_text("{ quebrado", encoding="utf-8")
    SP._save_config_key("camera_index", 2)
    assert arq.read_text(encoding="utf-8") == "{ quebrado"     # não virou um arquivo sem a chave
