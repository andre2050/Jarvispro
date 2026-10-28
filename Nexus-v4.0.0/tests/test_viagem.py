from datetime import datetime

from core import viagem as V

AG = [{"titulo": "Voo para Lisboa", "inicio": "2026-11-02T09:30:00-03:00", "local": "GRU", "dia_inteiro": False},
      {"titulo": "Check-in hotel", "inicio": "2026-11-03T15:00:00-03:00", "local": "", "dia_inteiro": False},
      {"titulo": "Aniversário", "inicio": "2026-11-03T00:00:00-03:00", "local": "", "dia_inteiro": True}]


def _fontes(**ex):
    f = {"agenda": lambda dias: AG, "tarefas": lambda: [{"titulo": "malas"}], "contatos": lambda: [{"nome": "Ana"}],
         "documentos": lambda: ["C:/Viagem"], "modelo_local": lambda: True}
    f.update(ex)
    return f


def test_preparar_guarda_pacote_e_avisa_o_que_falta(tmp_path):
    arq = tmp_path / "p.json"
    r = V.preparar(_fontes(), 14, arq, agora=1000)
    assert r["itens"] == {"agenda": 3, "tarefas": 1, "contatos": 1, "documentos": 1} and r["faltando"] == []
    r = V.preparar(_fontes(agenda=lambda d: 1 / 0, modelo_local=lambda: False, documentos=None), 14, arq, agora=2000)
    assert any(x.startswith("agenda:") for x in r["faltando"]) and any("modelo local" in x for x in r["faltando"])
    assert any("documentos: sem fonte" in x for x in r["faltando"])
    assert "Nenhum" in V.status(tmp_path / "nao.json") and "Modelo local: NÃO" in V.status(arq, agora=3000)


def test_agenda_offline_por_periodo(tmp_path):
    arq = tmp_path / "p.json"
    V.preparar(_fontes(), 14, arq, agora=1000)
    hoje = datetime(2026, 11, 2, 8, 0)
    assert "09:30 Voo para Lisboa (GRU)" in V.agenda_offline("hoje", hoje, arq)
    t = V.agenda_offline("amanha", hoje, arq)
    assert "15:00 Check-in hotel" in t and "dia todo Aniversário" in t and "Voo" not in t
    assert "semana" in V.agenda_offline("semana", hoje, arq) and "Nada" in V.agenda_offline("hoje", datetime(2026, 12, 1), arq)
    assert "Prepare antes" in V.agenda_offline("hoje", hoje, tmp_path / "vazio.json")


def test_ligar_e_desligar_restaura_o_modo_anterior(tmp_path):
    arq = tmp_path / "p.json"
    modo = {"v": "economico"}
    setar = lambda m: modo.update(v=m)
    assert "ligado" in V.ativar(setar, lambda: modo["v"], arq) and modo["v"] == "offline" and V.viajando(arq)
    assert "já está" in V.ativar(setar, lambda: modo["v"], arq) and modo["v"] == "offline"   # não sobrescreve o modo guardado
    assert "economico" in V.desativar(setar, arq) and modo["v"] == "economico" and not V.viajando(arq)
    assert "não estava" in V.desativar(setar, arq)
