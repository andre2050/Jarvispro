from datetime import datetime

from core import revisao_diaria as R

AGORA = datetime(2026, 10, 21, 18, 0)
INI = datetime(2026, 10, 21, 9, 0).timestamp()


def _t(id_, titulo, prazo="", feita=False, concl=None):
    return {"id": id_, "titulo": titulo, "prazo": prazo, "feita": feita, "concluida": concl}


def test_revisao_completa():
    tarefas = [_t(1, "enviar proposta", feita=True, concl=INI), _t(2, "dentista", "2026-10-20"),
               _t(3, "pagar conta", "2026-10-21"), _t(4, "ligar para o João", "2026-10-22"),
               _t(5, "ontem feita", feita=True, concl=INI - 86400 * 2)]
    lem = [{"quando": "2026-10-21T20:00", "mensagem": "remédio", "pendente": True},
           {"quando": "2026-10-21T08:00", "mensagem": "já tocou", "pendente": False},
           {"quando": "2026-10-22T07:30", "mensagem": "reunião", "pendente": True}]
    t = R.montar(AGORA, tarefas=tarefas, lembretes=lem)
    assert "concluiu 1 tarefa: enviar proposta" in t
    assert "atrasada: dentista" in t and "Pendente para hoje: pagar conta" in t
    assert "remédio às 20:00" in t and "já tocou" not in t
    assert "Para amanhã: ligar para o João e reunião às 07:30" in t
    assert "ontem feita" not in t


def test_dia_vazio():
    t = R.montar(AGORA, tarefas=[], lembretes=[])
    assert "ainda não marcou nenhuma" in t and "Nada marcado para amanhã" in t


def test_lista_longa_resume():
    assert R._lista(["a", "b", "c", "d", "e"]) == "a, b, c e mais 2"
