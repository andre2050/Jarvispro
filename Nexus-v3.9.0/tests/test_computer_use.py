import pytest
from core import computer_use as C

TELA = (1000, 600)


def _uso(passos, titulo="Bloco de notas", perguntar=None, **kw):
    it = iter(passos)
    feitos = []
    u = C.Uso("abrir algo", lambda: (b"img", TELA, titulo), lambda o, h, i: next(it), feitos.append,
              perguntar=perguntar, auditar=False, **kw)
    return u, feitos


def test_fluxo_feliz():
    u, feitos = _uso([{"acao": "click", "x": 10, "y": 20}, {"acao": "type", "texto": "oi"}, {"acao": "done", "motivo": "ok"}])
    assert u.rodar().startswith("Concluído") and u.estado == "feito" and len(feitos) == 2


def test_clique_fora_da_tela_e_tres_erros_seguidos():
    u, feitos = _uso([{"acao": "click", "x": 5000, "y": 1}] * 3)
    assert "errou três vezes" in u.rodar() and not feitos


def test_janela_de_banco_bloqueia():
    u, feitos = _uso([{"acao": "click", "x": 1, "y": 1}], titulo="Meu Banco - Login")
    assert "Parei" in u.rodar() and u.estado == "bloqueado" and not feitos


def test_tecla_perigosa_bloqueada_e_enter_pergunta():
    u, feitos = _uso([{"acao": "key", "tecla": "Alt+F4"}])
    u.rodar()
    assert u.estado == "bloqueado" and not feitos
    u, feitos = _uso([{"acao": "key", "tecla": "enter"}, {"acao": "done"}], perguntar=lambda t: False)
    u.rodar()
    assert u.estado == "recusado" and not feitos
    u, feitos = _uso([{"acao": "key", "tecla": "enter"}, {"acao": "done"}], perguntar=lambda t: True)
    u.rodar()
    assert u.estado == "feito" and len(feitos) == 1


def test_texto_com_segredo_pede_aprovacao_e_sem_canal_nao_faz():
    u, feitos = _uso([{"acao": "type", "texto": "minha senha 123"}])
    u.rodar()
    assert u.estado == "recusado" and not feitos


def test_limites_de_passos_e_tempo_e_parar():
    u, feitos = _uso([{"acao": "scroll", "quanto": 1}] * 10, max_passos=3)
    assert u.rodar().startswith("Cheguei") and len(feitos) == 3
    t = iter(range(0, 1000, 100))
    u, feitos = _uso([{"acao": "scroll"}] * 10, max_segundos=150, relogio=lambda: next(t))
    u.rodar()
    assert u.estado == "tempo"
    u, feitos = _uso([{"acao": "scroll"}] * 10)
    u.parar()
    assert u.rodar().startswith("Parei") and not feitos


def test_validar_rejeita_lixo():
    for ruim in (None, {"acao": "format_c"}, {"acao": "type"}, {"acao": "key"}, {"acao": "click", "x": "a", "y": 1}):
        with pytest.raises(C.ErroUso):
            C.validar(ruim, TELA)
