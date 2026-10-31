"""3.3 — rotinas criadas por conversa (core/rotinas_conversa.py)."""
from datetime import datetime

import pytest

from actions import smart_routines as SR
from core import rotinas_conversa as RC


@pytest.fixture(autouse=True)
def _tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(SR, "_FILE", tmp_path / "routines.json")
    RC._pendente = None
    yield
    RC._pendente = None


def _ts(dia, hora, minuto=0):                                   # 2026-10-26 é segunda-feira
    return datetime(2026, 10, dia, hora, minuto).timestamp()


def test_dias_e_horas_em_portugues():
    assert RC.parse_dias(["segunda"]) == [0]
    assert RC.parse_dias("segunda e quarta") == [0, 2]
    assert RC.parse_dias("dias úteis") == [0, 1, 2, 3, 4]
    assert RC.parse_dias("todo dia") == list(range(7))
    assert RC.parse_dias("fim de semana") == [5, 6]
    assert RC.parse_dias("terça-feira") == [1] and RC.parse_dias("sábado") == [5]
    assert RC.parse_dias(None) == [] and RC.parse_dias("blablabla") is None
    assert RC.parse_hora("8") == "08:00" and RC.parse_hora("8h30") == "08:30"
    assert RC.parse_hora("18:45") == "18:45" and RC.parse_hora("de manhã") == "08:00"
    assert RC.parse_hora("à noite") == "20:00" and RC.parse_hora("25h") is None and RC.parse_hora("") is None


def test_propor_mostra_a_previa_e_nao_salva():
    txt = RC.propor("segunda de manhã", apps=["Spotify"],
                    steps=[{"tool": "weather_report", "params": {}}], dias="segunda", hora="de manhã")
    assert "PRÉVIA" in txt and "Spotify" in txt and "toda segunda, às 08:00" in txt and "NÃO salvou" in txt
    assert SR._load().get("segunda de manhã") is None                 # nada salvo ainda
    assert RC.pendente() is not None


def test_confirmar_salva_com_agenda():
    RC.propor("manhã de segunda", apps=["Spotify"], steps=[{"tool": "weather_report", "params": {}}],
              dias="segunda", hora="8h")
    msg = RC.confirmar()
    assert "Salvei" in msg and "toda segunda" in msg
    r = SR._load()["manhã de segunda"]
    assert r["agenda"] == {"dias": [0], "hora": "08:00"}
    assert [s["tool"] for s in r["steps"]] == ["open_app", "weather_report"]
    assert RC.pendente() is None
    assert "Não há rotina" in RC.confirmar() or "[failed]" in RC.confirmar()


def test_sem_agenda_a_rotina_so_roda_pelo_nome():
    RC.propor("modo leitura", apps=["Kindle"])
    assert "diga o nome" in RC.confirmar()
    assert "agenda" not in SR._load()["modo leitura"]


def test_cancelar_e_expirar():
    RC.propor("x", apps=["A"])
    assert "Descartei" in RC.cancelar() and RC.pendente() is None
    assert "Não havia" in RC.cancelar()
    RC.propor("y", apps=["A"], agora=100.0)
    assert RC.pendente(agora=100.0 + RC.VALIDADE_S + 1) is None
    assert "[failed]" in RC.confirmar(agora=100.0 + RC.VALIDADE_S + 1)


def test_so_ferramentas_seguras_e_entradas_ruins():
    assert "[failed]" in RC.propor("perigo", steps=[{"tool": "send_message", "params": {}}])
    assert "[failed]" in RC.propor("perigo", steps=[{"tool": "file_controller", "params": {"action": "delete"}}])
    assert "[failed]" in RC.propor("", apps=["A"])
    assert "[failed]" in RC.propor("vazia")
    assert "[failed]" in RC.propor("a", apps=["A"], dias="dia errado", hora="8h")
    assert "[failed]" in RC.propor("a", apps=["A"], dias="segunda")               # falta a hora
    assert "[failed]" in RC.propor("a", apps=["A"], hora="8h")                    # falta o dia
    assert RC.pendente() is None


def test_devidas_so_na_hora_e_uma_vez_por_dia():
    RC.propor("manhã", apps=["A"], dias="segunda", hora="08:00")
    RC.confirmar()
    assert RC.devidas(_ts(26, 7, 59)) == []                       # cedo
    assert RC.devidas(_ts(26, 8, 0)) == ["manhã"]
    assert RC.devidas(_ts(26, 8, 9)) == ["manhã"]                 # dentro da janela
    assert RC.devidas(_ts(26, 8, 11)) == []                       # passou da janela
    assert RC.devidas(_ts(27, 8, 0)) == []                        # terça
    RC.marcar_executada("manhã", _ts(26, 8, 0))
    assert RC.devidas(_ts(26, 8, 5)) == []                        # já rodou hoje
    assert RC.devidas(datetime(2026, 11, 2, 8, 0).timestamp()) == ["manhã"]   # segunda seguinte


def test_agendadas_e_ferramenta_de_voz():
    RC.propor("t", apps=["A"], dias="dias úteis", hora="9h")
    RC.confirmar()
    from actions.rotina_conversa import TOOL, criar_rotina
    assert TOOL["name"] == "criar_rotina"
    assert "nos dias úteis, às 09:00" in criar_rotina({"action": "list"})
    assert "PRÉVIA" in criar_rotina({"action": "propose", "name": "z", "apps": ["B"], "days": "sábado", "time": "10h"})
    assert "Salvei" in criar_rotina({"action": "confirm"})
