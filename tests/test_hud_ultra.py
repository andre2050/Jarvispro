"""Os vinte visuais do hub (ui/hud_novos.py): registro, desenho em todos os estados e migração de escolhas antigas."""
import pytest


def _novos():
    from ui.hud_novos import NOVOS_STYLES
    return list(NOVOS_STYLES)


def test_vinte_visuais_novos_3_6_registrados_e_no_menu():
    from memory.config_manager import HUD_STYLES
    from ui.hud import HUD_STYLE_INFO
    from ui.hud_novos import NOVOS_INFO, NOVOS_STYLES
    assert len(NOVOS_STYLES) == 21 and set(NOVOS_STYLES) == set(NOVOS_INFO)      # 20 da 3.6 + Rosto · Real (4.1)
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


def test_so_existem_os_vinte_visuais_mais_o_orbe_de_reserva():
    from memory.config_manager import HUD_STYLES
    from ui.hud import HUD_STYLE_INFO
    assert len(HUD_STYLES) == 22 and "orb" in HUD_STYLES      # orbe + 20 da 3.6 + Rosto · Real (4.1)
    assert set(HUD_STYLES) == set(HUD_STYLE_INFO)
    assert not {"aurora", "liquid", "holo", "globe", "hub", "matrix", "waves", "minimal", "nebula"} & set(HUD_STYLES)


def test_escolha_antiga_migra_para_o_padrao(monkeypatch):
    import memory.config_manager as CM
    for antigo in ("matrix", "orb", "nebula", "lixo", ""):
        monkeypatch.setattr(CM, "load_api_keys", lambda a=antigo: {"hud_style": a})
        assert CM.get_hud_style() == CM.HUD_PADRAO
    monkeypatch.setattr(CM, "load_api_keys", lambda: {"hud_style": "saturn"})
    assert CM.get_hud_style() == "saturn"


def test_visual_com_defeito_volta_ao_orbe(monkeypatch):
    from PyQt6.QtWidgets import QApplication
    from ui import hud, hud_novos
    _app = QApplication.instance() or QApplication([])
    def quebrado(*a, **k):
        raise RuntimeError("defeito de mentira")
    monkeypatch.setitem(hud_novos.NOVOS_STYLES, "saturn", ("x", "Saturno", "d", quebrado))
    h = hud.HudCanvas("", "NEXUS")
    h._tmr.stop()
    h.resize(400, 400)
    h.hud_style = "saturn"
    assert not h.grab().toImage().isNull()
    assert h.hud_style == "orb"
