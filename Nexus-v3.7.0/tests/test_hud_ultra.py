"""NEXUS Ultra 2026 — os dez visuais novos do hub (ui/hud_ultra.py)."""
import pytest


def test_dez_visuais_novos_registrados():
    from memory.config_manager import HUD_STYLES
    from ui.hud import HUD_STYLE_INFO
    from ui.hud_ultra import ULTRA_INFO, ULTRA_STYLES
    assert len(ULTRA_STYLES) == 10
    assert set(ULTRA_STYLES) == set(ULTRA_INFO)
    assert set(ULTRA_STYLES) <= set(HUD_STYLES) and set(ULTRA_STYLES) <= set(HUD_STYLE_INFO)
    assert len(HUD_STYLES) == 54          # 9 clássicos + 10 Ultra + 15 do núcleo + 20 novos
    assert set(HUD_STYLES) == set(HUD_STYLE_INFO)   # tudo que o menu mostra pode ser salvo


@pytest.mark.parametrize("estilo", ["nebula", "gyro", "helix", "sonar", "spectrum",
                                    "hive", "atom", "plasma", "stars", "tunnel"])
def test_cada_visual_desenha_em_todos_os_estados_e_tamanhos(estilo):
    from PyQt6.QtWidgets import QApplication
    from ui.hud import HudCanvas
    _app = QApplication.instance() or QApplication([])
    h = HudCanvas("", "NEXUS")
    h._tmr.stop()
    h.hud_style = estilo
    for (w, alt) in ((480, 420), (300, 300), (700, 360)):
        h.resize(w, alt)
        for estado, fala, mudo in (("SPEAKING", True, False), ("LISTENING", False, False),
                                   ("THINKING", False, False), ("SLEEPING", False, True)):
            h.state, h.speaking, h.muted = estado, fala, mudo
            for amp in (0.0, 0.5, 1.0):
                h._amp = amp
                h._hist.append(amp)
                h._fase += 0.7
                h._tick += 1
                img = h.grab().toImage()
                assert not img.isNull() and img.width() == w
            assert h.hud_style == estilo, f"{estilo} caiu para o orbe (erro de desenho)"


def test_visual_com_defeito_volta_ao_orbe(monkeypatch):
    from PyQt6.QtWidgets import QApplication
    from ui import hud, hud_ultra
    _app = QApplication.instance() or QApplication([])
    def quebrado(*a, **k):
        raise RuntimeError("defeito de mentira")
    monkeypatch.setitem(hud_ultra.ULTRA_STYLES, "atom", ("x", "Átomo", "d", quebrado))
    h = hud.HudCanvas("", "NEXUS")
    h._tmr.stop()
    h.resize(400, 400)
    h.hud_style = "atom"
    assert not h.grab().toImage().isNull()
    assert h.hud_style == "orb"


def _novos():
    from ui.hud_novos import NOVOS_STYLES
    return list(NOVOS_STYLES)


def test_vinte_visuais_novos_3_6_registrados_e_no_menu():
    from memory.config_manager import HUD_STYLES
    from ui.hud import HUD_STYLE_INFO
    from ui.hud_novos import NOVOS_INFO, NOVOS_STYLES
    assert len(NOVOS_STYLES) == 20 and set(NOVOS_STYLES) == set(NOVOS_INFO)
    assert set(NOVOS_STYLES) <= set(HUD_STYLES) and set(NOVOS_STYLES) <= set(HUD_STYLE_INFO)


@pytest.mark.parametrize("estilo", _novos())
def test_cada_visual_novo_desenha_em_todos_os_estados_e_tamanhos(estilo):
    from PyQt6.QtWidgets import QApplication
    from ui.hud import HudCanvas
    _app = QApplication.instance() or QApplication([])
    h = HudCanvas("", "NEXUS")
    h._tmr.stop()
    h.hud_style = estilo
    for (w, alt) in ((480, 420), (300, 300), (700, 360)):
        h.resize(w, alt)
        for estado, fala, mudo in (("SPEAKING", True, False), ("LISTENING", False, False),
                                   ("THINKING", False, False), ("SLEEPING", False, True)):
            h.state, h.speaking, h.muted = estado, fala, mudo
            for amp in (0.0, 0.5, 1.0):
                h._amp = amp
                h._hist.append(amp)
                h._fase += 0.7
                h._tick += 1
                assert not h.grab().toImage().isNull()
            assert h.hud_style == estilo, f"{estilo} caiu para o orbe (erro de desenho)"
