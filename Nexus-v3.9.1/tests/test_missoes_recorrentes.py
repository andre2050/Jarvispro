from datetime import datetime

import pytest

from core import missoes_recorrentes as R

SEXTA_17H = datetime(2026, 10, 30, 17, 5)       # 30/10/2026 é sexta


def test_agenda_valida_entradas(tmp_path):
    arq = tmp_path / "r.json"
    it = R.adicionar("monte o resumo da semana", "sexta", "17:00", {"chamadas": 30}, arq=arq)
    assert it["dias"] == [4] and it["hora"] == "17:00" and it["orcamento"] == {"chamadas": 30}
    for ruim in (("curto", "sexta", "17:00"), ("monte o resumo da semana", "quando der", "17:00"),
                 ("monte o resumo da semana", "sexta", "25:99"), ("monte o resumo da semana", "", "17:00")):
        with pytest.raises(R.ErroAgenda):
            R.adicionar(*ruim, arq=arq)
    assert "sex 17:00" in R.texto(R.listar(arq))


def test_dispara_uma_vez_por_dia_e_respeita_a_janela(tmp_path):
    arq = tmp_path / "r.json"
    R.adicionar("monte o resumo da semana", "sexta", "17:00", arq=arq)
    feitos = []
    criar = lambda meta, orc, ens: (feitos.append(meta) or {"estado": "executando"})
    assert R.devidas(datetime(2026, 10, 30, 16, 59), arq) == []                  # ainda não é a hora
    assert R.disparar(criar, SEXTA_17H, arq)[0][1] == "executando"
    assert R.disparar(criar, datetime(2026, 10, 30, 17, 30), arq) == [] and len(feitos) == 1   # já rodou hoje
    assert R.devidas(datetime(2026, 10, 31, 17, 5), arq) == []                   # sábado não
    R.adicionar("organize a semana que vem", "sexta", "08:00", arq=arq)
    assert R.devidas(datetime(2026, 10, 30, 20, 0), arq) == []                   # 12h depois: pulou o dia
    assert len(R.devidas(datetime(2026, 10, 30, 11, 0), arq)) == 1               # 3h depois: ainda dispara


def test_falha_ao_criar_nao_repete_e_pausa_remove(tmp_path):
    arq = tmp_path / "r.json"
    it = R.adicionar("monte o resumo da semana", "sexta", "17:00", arq=arq)
    def quebra(*a):
        raise RuntimeError("sem plano")
    assert R.disparar(quebra, SEXTA_17H, arq)[0][1].startswith("erro")
    assert R.disparar(quebra, SEXTA_17H, arq) == []                              # não tenta de novo no mesmo dia
    assert R.pausar(it["id"], False, arq) and R.devidas(datetime(2026, 11, 6, 17, 5), arq) == []
    assert R.remover(it["id"], arq) and not R.remover(it["id"], arq)


def test_limite_de_agendas(tmp_path):
    arq = tmp_path / "r.json"
    for i in range(R.MAX_AGENDAS):
        R.adicionar(f"missão número {i} bem descrita", "todo dia", "09:00", arq=arq)
    with pytest.raises(R.ErroAgenda):
        R.adicionar("mais uma missão bem descrita", "todo dia", "09:00", arq=arq)
