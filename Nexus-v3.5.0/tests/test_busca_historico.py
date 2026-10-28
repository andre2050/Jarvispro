import json
from datetime import date, datetime, timedelta

from core import busca_historico as B

HOJE = date(2026, 10, 21)          # quarta-feira


def test_periodos():
    assert B.periodo("semana passada", HOJE)[:2] == (date(2026, 10, 12), date(2026, 10, 18))
    assert B.periodo("o que fiz ontem", HOJE)[0] == date(2026, 10, 20)
    assert B.periodo("mês passado", HOJE)[:2] == (date(2026, 9, 1), date(2026, 9, 30))
    assert B.periodo("últimos 3 dias", HOJE)[0] == date(2026, 10, 19)
    assert B.periodo("sobre o carro", HOJE) is None


def test_termos_ignoram_ligacao_e_periodo():
    assert B.termos("o que eu anotei sobre o carro semana passada?") == ["carro"]


def test_busca_em_tres_fontes(tmp_path):
    rel = tmp_path / "rel"
    rel.mkdir()
    (rel / "tarefa.md").write_text("# Pesquisa de notebook\n\nComparei preços de notebook gamer.", encoding="utf-8")
    notas = tmp_path / "n.json"
    ts = datetime(2026, 10, 14, 10).timestamp()
    notas.write_text(json.dumps([{"text": "Levar o carro na revisão", "at": ts},
                                 {"text": "Comprar leite", "at": ts}]), encoding="utf-8")
    dia = tmp_path / "d.json"
    dia.write_text(json.dumps([{"id": 1, "quando": "2026-10-15T09:00:00", "texto": "O carro fez barulho", "humor": 3}]),
                   encoding="utf-8")
    kw = dict(relatorios=rel, notas=notas, diario=dia)
    r = B.buscar("carro semana passada", HOJE, **kw)
    assert r["total"] == 2 and {x["fonte"] for x in r["resultados"]} == {"anotação", "diário"}
    assert B.buscar("notebook", date.today(), **kw)["resultados"][0]["fonte"] == "relatório"
    assert "Não achei" in B.responder("carro ontem", HOJE, **kw)
    assert "2 resultado" in B.responder("carro semana passada", HOJE, **kw)


def test_sem_nada_pede_o_que_procurar(tmp_path):
    assert "Diga o que procurar" in B.responder("", HOJE, relatorios=tmp_path, notas=tmp_path / "x", diario=tmp_path / "y")
