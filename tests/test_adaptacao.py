from datetime import datetime

from core import adaptacao as A

DIA = 86400


def _t(dia, h=10):
    return datetime(2026, 10, dia, h).timestamp()


def _ligada(tmp_path):
    arq = tmp_path / "a.json"
    A.ligar(True, arq)
    return arq


def test_desligada_nao_observa_nem_muda_nada(tmp_path):
    arq = tmp_path / "a.json"
    for _ in range(20):
        A.observar("interrompeu", arq=arq, agora=_t(1))
    assert A.ajustar(_t(2), arq) == [] and A.fator_cooldown(arq) == 1.0 and A.bloco_prompt(arq) == "" and "desligada" in A.resumo(arq)


def test_interrupcoes_frequentes_reduzem_a_verbosidade_um_passo(tmp_path):
    arq = _ligada(tmp_path)
    for _ in range(7):
        A.observar("interrompeu", arq=arq, agora=_t(1))
    assert A.ajustar(_t(1), arq) == []                                       # evidência insuficiente
    for _ in range(2):
        A.observar("interrompeu", arq=arq, agora=_t(1))
    m = A.ajustar(_t(1), arq)
    assert len(m) == 1 and "3 → 2" in m[0] and A.valor("verbosidade", arq) == 2
    assert "curta" in A.bloco_prompt(arq)


def test_um_passo_por_dia_e_tendencia_clara(tmp_path):
    arq = _ligada(tmp_path)
    for _ in range(10):
        A.observar("interrompeu", arq=arq, agora=_t(1))
    A.ajustar(_t(1), arq)
    for _ in range(10):
        A.observar("interrompeu", arq=arq, agora=_t(1, 12))
    assert A.ajustar(_t(1, 13), arq) == []                                   # mesmo dia: espera
    assert A.ajustar(_t(3), arq) != [] and A.valor("verbosidade", arq) == 1
    for _ in range(10):
        A.observar("interrompeu", arq=arq, agora=_t(5))
    A.ajustar(_t(5), arq)
    assert A.valor("verbosidade", arq) == 1                                  # nunca passa de 1
    arq2 = _ligada(tmp_path / "x") if (tmp_path / "x").mkdir() is None else None
    for s in ["interrompeu"] * 5 + ["pediu_detalhes"] * 5:
        A.observar(s, arq=arq2, agora=_t(1))
    assert A.ajustar(_t(2), arq2) == []                                      # 50/50: sem tendência, não mexe


def test_agir_depois_do_aviso_aumenta_proatividade_e_ignorar_diminui(tmp_path):
    arq = _ligada(tmp_path)
    for i in range(9):
        A.observar("aviso", arq=arq, agora=_t(1, 10) + i * 1000)
        A.observar("uso", "web_search", arq=arq, agora=_t(1, 10) + i * 1000 + 30)    # agiu em 30 s
    A.ajustar(_t(2), arq)
    assert A.valor("proatividade", arq) == 4 and A.fator_cooldown(arq) == 0.7
    arq2 = tmp_path / "b.json"
    A.ligar(True, arq2)
    for i in range(9):
        A.observar("aviso", arq=arq2, agora=_t(1, 10) + i * 1000)                      # ninguém reage
        A.ajustar(_t(1, 10) + i * 1000 + 400, arq2)                                    # passou dos 5 min: conta como ignorado
    assert A.valor("proatividade", arq2) == 2 and A.fator_cooldown(arq2) == 1.7


def test_travar_impede_mudanca_e_reverter_desfaz(tmp_path):
    arq = _ligada(tmp_path)
    A.travar("verbosidade", 4, arq)
    for _ in range(12):
        A.observar("interrompeu", arq=arq, agora=_t(1))
    assert A.ajustar(_t(2), arq) == [] and A.valor("verbosidade", arq) == 4
    A.destravar("verbosidade", arq)
    A.ajustar(_t(2), arq)
    assert A.valor("verbosidade", arq) == 3
    assert "voltou para 4" in A.reverter(arq) and A.valor("verbosidade", arq) == 4 and "Não há" in A.reverter(arq)


def test_horas_de_silencio_so_com_dados_suficientes(tmp_path):
    arq = _ligada(tmp_path)
    for i in range(40):
        A.observar("uso", "x", arq=arq, agora=_t(1, 9 + i % 8))
    assert A.horas_de_silencio(arq) == []                                    # poucos dados
    for i in range(40):
        A.observar("uso", "x", arq=arq, agora=_t(2, 9 + i % 8))
    hs = A.horas_de_silencio(arq)
    assert 3 in hs and 9 not in hs and A.calar_agora(3, arq) and not A.calar_agora(10, arq)


def test_esquecer_zera_mas_mantem_ligado_e_favoritas(tmp_path):
    arq = _ligada(tmp_path)
    for t in ["a", "a", "b", "a", "c", "b"]:
        A.observar("uso", t, arq=arq, agora=_t(1))
    assert A.favoritas(2, arq) == ["a", "b"]
    A.esquecer(arq)
    assert A.favoritas(2, arq) == [] and A.ligado(arq)
