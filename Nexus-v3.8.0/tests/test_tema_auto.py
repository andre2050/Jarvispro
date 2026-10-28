"""Tema automático: faixas do dia, humor do diário, modos, ação por voz e aplicação ao vivo na interface."""
import json
from datetime import datetime, timedelta

import pytest

from core import tema_auto as T

AGORA = datetime(2026, 10, 28, 12, 30)


def test_faixas_do_dia():
    assert T.faixa_do_horario(0)[0] == "madrugada" and T.faixa_do_horario(5)[0] == "madrugada"
    assert T.faixa_do_horario(6)[0] == "manhã" and T.faixa_do_horario(11)[0] == "manhã"
    assert T.faixa_do_horario(12)[0] == "tarde" and T.faixa_do_horario(17)[0] == "tarde"
    assert T.faixa_do_horario(18)[0] == "noite" and T.faixa_do_horario(23)[0] == "noite"
    assert len({T.faixa_do_horario(h)[1] for h in (3, 9, 15, 21)}) == 4          # quatro cores diferentes


def _diario(tmp_path, itens):
    arq = tmp_path / "diario.json"
    arq.write_text(json.dumps(itens), encoding="utf-8")
    return arq


def test_humor_recente_so_conta_a_janela_e_notas_validas(tmp_path):
    q = lambda d: (AGORA - timedelta(days=d)).isoformat()
    arq = _diario(tmp_path, [
        {"quando": q(0), "humor": 5}, {"quando": q(1), "humor": 3}, {"quando": q(1), "texto": "sem humor"},
        {"quando": q(10), "humor": 1},                                           # velho demais
        {"quando": q(1), "humor": 9}, {"quando": "lixo", "humor": 2}, "estranho"])    # inválidos
    assert T.humor_recente(AGORA, arq) == 4.0
    assert T.humor_recente(AGORA, tmp_path / "nao_existe.json") is None
    assert T.humor_recente(AGORA, _diario(tmp_path, [])) is None


def test_cor_do_humor_vai_do_calmo_ao_quente_passando_pelo_neutro():
    assert T.cor_do_humor(1) == T.COR_HUMOR_BAIXO
    assert T.cor_do_humor(3) == T.FAIXAS[2][2]
    assert T.cor_do_humor(5) == T.COR_HUMOR_ALTO
    assert T.cor_do_humor(0) == T.COR_HUMOR_BAIXO and T.cor_do_humor(9) == T.COR_HUMOR_ALTO   # limites
    assert T.cor_do_humor(2) not in (T.COR_HUMOR_BAIXO, T.FAIXAS[2][2])


def test_modos():
    assert T.cor_do_momento("desligado", AGORA, 5) is None
    assert T.cor_do_momento("horario", AGORA) == T.faixa_do_horario(12)[1]
    assert T.cor_do_momento("humor", AGORA, None) is None                 # sem humor anotado, não muda nada
    assert T.cor_do_momento("humor", AGORA, 5) == T.COR_HUMOR_ALTO
    assert T.cor_do_momento("ambos", AGORA, None) == T.faixa_do_horario(12)[1]
    mistura = T.cor_do_momento("ambos", datetime(2026, 1, 1, 3), 5)
    assert mistura not in (T.faixa_do_horario(3)[1], T.COR_HUMOR_ALTO)
    assert T.cor_do_momento("qualquer coisa", AGORA, 3) is None


@pytest.fixture
def cfg(monkeypatch):
    guardado = {}
    import memory.config_manager as M
    monkeypatch.setattr(M, "get_plugin_setting", lambda ns, k, d=None: guardado.get(ns, {}).get(k, d))
    monkeypatch.setattr(M, "save_plugin_config", lambda ns, v: guardado.setdefault(ns, {}).update(v))
    return guardado


def test_configuracao_e_acao_por_voz(cfg, monkeypatch, tmp_path):
    from actions import tema_auto as A
    monkeypatch.setattr(T, "ARQ_DIARIO", tmp_path / "sem_diario.json")
    assert T.modo_atual() == "desligado" and T.cor_agora() is None
    assert "desligado" in A.tema_auto({"action": "status"})
    r = A.tema_auto({"action": "set", "mode": "horário"})
    assert r.startswith("[done]") and T.modo_atual() == "horario" and T.cor_agora() is not None
    r = A.tema_auto({"action": "set", "mode": "humor"})
    assert "humor 4" in r                                                  # avisa que ainda não há humor no diário
    assert "Escolha" in A.tema_auto({"action": "set", "mode": "roxo"})
    cfg["tema_auto"]["modo"] = "lixo"
    assert T.modo_atual() == "desligado"                                    # valor inválido na config é ignorado
    A.tema_auto({"action": "set", "mode": "off"})
    assert T.modo_atual() == "desligado"


def test_aplica_ao_vivo_e_devolve_a_cor_escolhida_ao_desligar(monkeypatch):
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication, QLabel
    from ui import _base as B
    app = QApplication.instance() or QApplication([])
    escolhida = "#ff0000"
    monkeypatch.setattr(B, "_read_full_config", lambda: {"ui_color": escolhida})
    pal0 = B.current_palette()
    w = QLabel("x")
    w.setStyleSheet(f"color: {B.C.PRI}; background: {B.C.PANEL};")
    try:
        c1 = B.aplicar_tema_automatico(None, "#4fb8ff")
        assert c1 == "#4fb8ff" and B.C.PRI != pal0["PRI"]
        assert pal0["PRI"] not in w.styleSheet() and B.C.PRI in w.styleSheet()    # estilos dos painéis trocaram na hora
        assert B.aplicar_tema_automatico(c1, "#4fb8ff") == c1                       # mesma cor: nada a fazer
        pri_azul = B.C.PRI
        c2 = B.aplicar_tema_automatico(c1, None)                                    # modo desligado: volta à cor da pessoa
        assert c2 is None and B.C.PRI != pri_azul
        antes = B.current_palette()
        assert B.aplicar_tema_automatico(None, None) is None and B.current_palette() == antes   # já desligado: não mexe
        assert B.aplicar_tema_automatico("x", "não é cor") == "x"                   # cor inválida: ignora
    finally:
        B.apply_ui_accent(pal0["PRI"])
