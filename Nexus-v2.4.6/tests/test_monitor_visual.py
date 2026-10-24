"""Monitor de sistema e paleta do visual novo: partes que não dependem de tela."""
import pytest

pytest.importorskip("PyQt6")

from ui._base import C, accent2, mix, _metrics  # noqa: E402
from ui.modern import format_uptime  # noqa: E402


def test_uptime_em_dias_horas_minutos():
    # 115h18 (o valor que aparecia como "115h18") agora é lido como dias
    assert format_uptime(115 * 3600 + 18 * 60)[0] == "4d 19h 18m"
    assert format_uptime(3 * 3600 + 5 * 60)[0] == "3h 05m"
    assert format_uptime(7 * 60)[0] == "7 min"
    assert format_uptime(-5)[0] == "0 min"


def test_cores_dos_degrades_sao_hex_validos():
    import re
    assert re.fullmatch(r"#[0-9a-f]{6}", accent2())
    assert re.fullmatch(r"#[0-9a-f]{6}", accent2("#ff0000"))
    assert accent2("#ff0000") != "#ff0000"
    assert accent2("lixo") == "#8b6bff"          # entrada inválida não quebra
    assert mix("#000000", "#ffffff", 0.5) in ("#808080", "#7f7f7f")
    assert mix("#102030", "#102030", 0.7) == "#102030"
    assert mix("#000000", "#ffffff", 9) == "#ffffff"   # t é limitado a 0..1


def test_snapshot_tem_tudo_que_a_tela_usa():
    snap = _metrics.snapshot()
    for chave in ("cpu", "mem", "net", "net_down", "net_up", "gpu", "tmp", "tmp_src",
                  "gpu_mem_pct", "gpu_name", "mem_used_gb", "mem_total_gb", "cpu_ghz",
                  "cores", "procs", "proc_count", "hist"):
        assert chave in snap, chave
    for k in ("cpu", "mem", "net", "gpu", "tmp"):
        assert k in snap["hist"]


def test_coletor_de_processos_agrupa_e_ignora_ocioso():
    lista, total, threads = _metrics._get_procs()
    assert total > 0
    nomes = [n.lower() for n, _, _ in lista]
    assert "system idle process" not in nomes
    assert len(nomes) == len(set(nomes))           # um item por nome
    assert all(cpu >= 0 and ram >= 0 for _, cpu, ram in lista)


def test_lista_de_processos_ordena_por_cpu_e_por_ram():
    from PyQt6.QtWidgets import QApplication
    from ui.modern import ProcessList
    _app = QApplication.instance() or QApplication([])
    w = ProcessList()
    w.set_data([("a", 1.0, 900), ("b", 20.0, 100), ("c", 5.0, 5000)], 3)
    assert [r[0] for r in w._sorted()][0] == "b"
    w._mode = "mem"
    assert [r[0] for r in w._sorted()][0] == "c"


def test_setup_tem_uma_so_configuracao_do_usuario():
    from ui.overlays.settings import SettingsPanelOverlay as S
    menu = [rotulo for _, rotulo in S.MENU_LABELS]
    assert sum("USUÁRIO" in r for r in menu) == 1
    chaves_menu = [k for k, _ in S.MENU_LABELS]
    assert "skin" not in chaves_menu and "notif" not in chaves_menu
    assert "usuario" not in [k for k, _ in S._TABS]   # o menu abre a janela direto


def test_hub_tem_seis_visuais_e_todos_desenham():
    from PyQt6.QtWidgets import QApplication
    from memory.config_manager import HUD_STYLES
    from ui.hud import HUD_STYLE_INFO, HudCanvas
    _app = QApplication.instance() or QApplication([])
    assert set(HUD_STYLES) == set(HUD_STYLE_INFO)
    assert {"aurora", "liquid", "holo", "globe"} <= set(HUD_STYLES)
    for estilo in HUD_STYLES:
        h = HudCanvas("", "NEXUS")
        h.resize(480, 420)
        h.hud_style = estilo
        for estado in ("SPEAKING", "LISTENING", "THINKING"):
            h.state, h.speaking = estado, estado == "SPEAKING"
            h._amp = 0.6
            for v in (0.1, 0.9, 0.4, 0.0):
                h._hist.append(v)
            img = h.grab().toImage()
            assert not img.isNull() and img.width() == 480, (estilo, estado)
        h._tmr.stop()
        h.muted = True                      # mudo também desenha sem erro
        assert not h.grab().toImage().isNull()


def test_botao_de_controle_le_icone_nome_e_estado():
    from PyQt6.QtWidgets import QApplication
    from ui.modern import ControlButton
    _app = QApplication.instance() or QApplication([])
    b = ControlButton()
    casos = {
        "☀  BRIEFING DA MANHÃ: LIGADO": ("sol", "BRIEFING DA MANHÃ", "LIGADO", "on"),
        "🎙  PALAVRA DE ATIVAÇÃO: DESLIGADA": ("mic", "PALAVRA DE ATIVAÇÃO", "DESLIGADA", "off"),
        "⬇  PALAVRA DE ATIVAÇÃO: BAIXAR": ("baixar", "PALAVRA DE ATIVAÇÃO", "BAIXAR", "alerta"),
        "🎚  FALAR SEGURANDO: F4": ("ptt", "FALAR SEGURANDO", "F4", "info"),
        "⛶  TELA CHEIA  [F11]": ("tela", "TELA CHEIA", "F11", "info"),
        "😴  DORMIR AGORA": ("lua", "DORMIR AGORA", "", "nenhum"),
        "🌐  VISUAL DO HUB: Globo neural": ("globo", "VISUAL DO HUB", "Globo neural", "info"),
    }
    for texto, esperado in casos.items():
        b.setText(texto)
        assert b._partes() == esperado, texto
        b.resize(268, 36)
        assert not b.grab().toImage().isNull()
    b.setEnabled(False)                        # desabilitado também desenha
    assert not b.grab().toImage().isNull()


def test_todos_os_botoes_da_barra_e_do_setup_tem_icone_e_desenham():
    from PyQt6.QtWidgets import QApplication
    from ui.modern import ICONE_FERRAMENTA, ICONE_SETUP, MenuButton, QuickButton
    from ui.quickbar import FERRAMENTAS
    from ui.overlays.settings import SettingsPanelOverlay as S
    _app = QApplication.instance() or QApplication([])
    assert set(FERRAMENTAS) <= set(ICONE_FERRAMENTA)           # nenhuma ferramenta sem ícone
    assert {k for k, _ in S.MENU_LABELS} <= set(ICONE_SETUP)   # nenhum item do SETUP sem ícone
    for chave in set(ICONE_FERRAMENTA.values()) | set(ICONE_SETUP.values()) | {"raio"}:
        b = QuickButton(chave, "Teste", "tool")
        b.resize(b.width(), b.height())
        assert not b.grab().toImage().isNull(), chave
    q = QuickButton("alvo", "Produtividade")
    larga = q.width()
    q.set_compacto(True)
    assert q.width() < larga
    q.set_on(True)
    assert not q.grab().toImage().isNull()
    for tipo in ("normal", "primario", "destaque"):
        mb = MenuButton("pessoa", "CONFIGURAÇÃO DO USUÁRIO", tipo)
        mb.resize(224, 27)
        assert not mb.grab().toImage().isNull(), tipo


def test_temas_prontos_trocam_cor_e_hub():
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])
    from ui.overlays.customize import CustomizeOverlay, TEMAS
    from memory.config_manager import HUD_STYLES
    assert all(h in HUD_STYLES for _, _, h in TEMAS)
    got = []
    ov = CustomizeOverlay(embedded=True)
    ov.on_preview = lambda h: got.append(("c", h))
    ov.on_hud_style = lambda h: got.append(("h", h))
    ov._theme_chips[2].click()
    assert got == [("c", TEMAS[2][1]), ("h", TEMAS[2][2])]
    ov._theme_hud.setChecked(False)
    got.clear(); ov._theme_chips[3].click()
    assert got == [("c", TEMAS[3][1])]
