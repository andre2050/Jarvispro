"""Painel 🤖 VISÃO COMPUTACIONAL (2.4.4)."""
import numpy as np
import pytest

pytest.importorskip("cv2")
pytest.importorskip("PyQt6")

from ui.overlays.tools import VisionOverlay


def test_rotulo_sem_acento_para_o_opencv():
    assert VisionOverlay._rotulo("avião 91%") == "aviao 91%"
    assert VisionOverlay._rotulo("maçã") == "maca"


def test_marcar_desenha_caixa_sem_mexer_na_original():
    img = np.zeros((200, 300, 3), np.uint8)
    out = VisionOverlay._marcar(img, [((50, 60, 80, 70), "pessoa 88%")])
    assert img.sum() == 0                                  # a original não muda
    assert out[60, 50:130].any() and out[130, 50:130].any()  # bordas de cima e de baixo
    assert not out[150:, 200:].any()                       # fora da caixa continua preto


def test_botao_sem_modelo_pede_para_instalar(monkeypatch):
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from core import visao_ia as V
    monkeypatch.setattr(V, "instalado", lambda nome: False)
    ov = VisionOverlay()
    recebido = []
    monkeypatch.setattr(ov, "_emitir", recebido.append)
    import threading
    monkeypatch.setattr(threading, "Thread", lambda target, **k: type("T", (), {"start": lambda s: target()})())
    ov._run_ia("objects", "camera")
    assert "não está instalada" in recebido[0]["msg"] and "INSTALAR" in recebido[0]["msg"]
    ov._timer.stop()
    app.processEvents()


def test_barra_rapida_chama_de_visao_computacional():
    from ui.quickbar import FERRAMENTAS
    icone, nome, metodo, _ = FERRAMENTAS["visao"]
    assert nome == "Visão computacional" and metodo == "_open_vision_panel"
