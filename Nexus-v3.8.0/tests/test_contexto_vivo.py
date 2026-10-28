from datetime import datetime, timedelta, timezone
from core import contexto_vivo as CV

AGORA = datetime(2026, 10, 28, 10, 0, tzinfo=timezone.utc)


def ev(min_, titulo="Reunião com o time", dia=False):
    return {"inicio": AGORA + timedelta(minutes=min_), "fim": AGORA + timedelta(minutes=min_ + 30), "titulo": titulo, "dia_inteiro": dia}


def test_reuniao_em_breve():
    assert "3 min" in CV.reuniao_em_breve([ev(3)], AGORA)
    assert CV.reuniao_em_breve([ev(20)], AGORA) == "" and CV.reuniao_em_breve([ev(-5)], AGORA) == ""
    assert CV.reuniao_em_breve([ev(2, dia=True)], AGORA) == "" and CV.reuniao_em_breve([{"x": 1}], AGORA) == ""


def test_anexo_esquecido():
    assert CV.anexo_esquecido("Novo e-mail - Gmail", "Oi Ana, segue em anexo o relatório")
    assert not CV.anexo_esquecido("Novo e-mail - Gmail", "segue em anexo relatorio.pdf (120 KB)")
    assert not CV.anexo_esquecido("Planilha", "segue em anexo") and not CV.anexo_esquecido("Novo e-mail", "")


def test_erro_na_tela_e_janela():
    assert CV.erro_na_tela("", "Traceback (most recent call last):\n  File x")
    assert CV.erro_na_tela("App (Não está respondendo)", "")
    assert CV.erro_na_tela("Bloco de notas", "bom dia") == ""


def test_observador_cooldown_silencio_e_fonte_quebrada():
    t = [0.0]
    o = CV.Observador(agenda=lambda: [ev(3)], janela=lambda: "Novo e-mail", tela=lambda: "segue em anexo",
                      relogio=lambda: t[0], cooldown=600)
    a = o.passo(AGORA)
    assert len(a) == 2 and o.passo(AGORA) == []         # não repete
    t[0] = 700
    assert len(o.passo(AGORA)) == 2                      # passou o cooldown
    assert CV.Observador(agenda=lambda: [ev(3)], silencio=lambda: "foco").passo(AGORA) == []
    assert CV.Observador(agenda=lambda: 1 / 0, janela=lambda: 1 / 0, tela=lambda: 1 / 0).passo(AGORA) == []
