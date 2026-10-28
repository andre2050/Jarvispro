import numpy as np
from core import voz_emocao as V

TX = 16000


def _tom(f, seg=1.0, amp=0.3, vib=0.0):
    t = np.arange(int(TX * seg)) / TX
    return (amp * np.sin(2 * np.pi * (f + vib * np.sin(2 * np.pi * 4 * t)) * t)).astype(np.float32)


def test_prosodia_mede_tom_e_energia():
    p = V.prosodia(_tom(150))
    assert p and 130 < p["f0"] < 170 and p["energia"] > 0.1
    assert V.prosodia(np.zeros(TX, np.float32)) is None and V.prosodia(_tom(150, 0.1)) is None


def test_estado_a_partir_da_linha_de_base():
    e = V.Emocao()
    rng = np.random.default_rng(0)
    for _ in range(30):
        e.hist.append({"energia": 0.10 + rng.normal(0, .01), "f0": 130 + rng.normal(0, 4),
                       "var_f0": .10 + rng.normal(0, .01), "vozeado": .7 + rng.normal(0, .03)})
    assert e.classificar({"energia": .10, "f0": 130, "var_f0": .10, "vozeado": .7}) == "neutro"
    assert e.classificar({"energia": .20, "f0": 160, "var_f0": .2, "vozeado": .7}) == "agitado"
    assert e.classificar({"energia": .05, "f0": 110, "var_f0": .1, "vozeado": .7}) == "cansado"
    assert e.classificar({"energia": .10, "f0": 130, "var_f0": .1, "vozeado": .3}) == "hesitante"


def test_sem_linha_de_base_fica_neutro():
    assert V.Emocao().classificar({"energia": 9, "f0": 500, "var_f0": 1, "vozeado": 0.1}) == "neutro"


def test_dica_so_com_mudanca_e_cooldown():
    t = [0.0]
    e = V.Emocao(relogio=lambda: t[0])
    for _ in range(30):
        e.hist.append({"energia": .1, "f0": 130, "var_f0": .1, "vozeado": .7})
    e.hist[0] = {"energia": .11, "f0": 131, "var_f0": .11, "vozeado": .71}
    forte = _tom(300, 1.0, 0.8)
    e._fila.append(forte)
    d1 = e.processar()
    e._fila.append(forte)
    assert e.processar() is None            # mesmo estado: não repete
    assert d1 is None or "calmo" in d1


def test_correcao_e_hesitacao_no_texto():
    assert "se corrigiu" in V.dica_do_texto("abre o Chrome, não, espera, abre o Firefox")
    assert "hesitando" in V.dica_do_texto("hum... é... tipo... não sei")
    assert V.dica_do_texto("abre o Chrome") == ""


def test_interrupcao_exige_blocos_seguidos():
    seq = iter([True, True, False, True, True, True, True])
    i = V.Interrupcao(lambda b: next(seq), 4)
    r = [i.bloco(None) for _ in range(7)]
    assert r == [False] * 6 + [True]
    assert not V.Interrupcao(lambda b: 1 / 0).bloco(None)
