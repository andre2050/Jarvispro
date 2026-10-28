"""Editor de visuais do hub: cor e velocidade por visual, salvas e aplicadas no desenho."""
import pytest

from core import hub_ajustes as HA


@pytest.fixture
def cfg(monkeypatch):
    estado = {}
    import memory.config_manager as CM
    monkeypatch.setattr(CM, "load_api_keys", lambda: dict(estado))
    monkeypatch.setattr(CM, "_save_flag", lambda k, v: estado.__setitem__(k, v))
    return estado


def test_normaliza_e_limita():
    assert HA.normalizar({"matiz": 400, "velocidade": 9}) == {"matiz": 40, "velocidade": 2.5}
    assert HA.normalizar({"velocidade": 0.01}) == {"velocidade": 0.3}
    assert HA.normalizar({"matiz": "x", "velocidade": "y"}) == {}
    assert HA.normalizar(None) == {} and HA.normalizar({"velocidade": 1.0}) == {}


def test_salva_por_visual_e_restaura(cfg):
    HA.salvar("nebula", 200, 1.5)
    HA.salvar("saturn", None, 0.5)
    assert HA.obter("nebula") == {"matiz": 200, "velocidade": 1.5} and HA.obter("saturn") == {"velocidade": 0.5}
    HA.restaurar("nebula")
    assert HA.obter("nebula") == {} and "nebula" not in cfg["hud_ajustes"] and "saturn" in cfg["hud_ajustes"]


def test_cores_trocam_o_matiz_e_mantem_brilho():
    (r, g, b), (r2, g2, b2) = HA.cores_com_matiz(120, (123, 140, 255))
    assert g > r and g > b                       # verde
    assert max(r, g, b) == 255 or max(r, g, b) > 240
    assert (r, g, b) != (r2, g2, b2)


def test_hud_usa_a_cor_e_a_velocidade(cfg):
    from PyQt6.QtWidgets import QApplication
    from ui.hud import HudCanvas
    _app = QApplication.instance() or QApplication([])
    h = HudCanvas("", "NEXUS")
    h._tmr.stop()
    h.hud_style = "galaxy"
    h.state, h.speaking, h.muted = "IDLE", False, False
    sem = h._cores()[0].name()
    HA.salvar("galaxy", 0, 2.0)                   # vermelho, 2x
    h.recarregar_ajustes()
    main, _ = h._cores()
    assert main.red() > main.green() and main.name() != sem
    assert h._ajustes["velocidade"] == 2.0
    h.resize(400, 400)
    assert not h.grab().toImage().isNull()
    h.muted = True
    assert h._cores()[0].name() != main.name()    # mudo continua mostrando o vermelho de mudo
