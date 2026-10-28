from core import hibrido as H


def test_sensivel_nunca_vai_para_nuvem_no_auto():
    r = H.rotear("qual meu saldo e a senha do banco?", True, True)
    assert r["destino"] == "local"
    assert H.rotear("minha senha é 123", True, False)["destino"] == "nenhum"
    assert H.sensivel("CPF 123.456.789-09") and not H.sensivel("que horas são")


def test_offline_e_modos():
    assert H.rotear("oi", False, True)["destino"] == "local"
    assert H.rotear("oi", False, False)["destino"] == "nenhum"
    assert H.rotear("planeje minha estratégia de vendas", True, True)["destino"] == "nuvem"
    assert H.rotear("oi", True, True, "rapido")["destino"] == "nuvem"
    assert H.rotear("planeje algo", True, True, "privado")["destino"] == "local"
    assert H.rotear("oi", True, True, "economico")["destino"] == "local"


def test_completar_fallback_respeita_sensibilidade():
    def ruim(_): raise RuntimeError("x")
    ok = lambda t: "nuvem-ok"
    r, rota = H.completar("planeje a estratégia", ok, lambda t: "local", True, True, "auto", auditar=False)
    assert r == "nuvem-ok" and rota["usado"] == "nuvem"
    r, rota = H.completar("planeje a estratégia", ruim, lambda t: "local", True, True, "auto", auditar=False)
    assert r == "local"
    # sensível: local falha → NÃO cai para a nuvem
    r, rota = H.completar("minha senha", ok, ruim, True, True, "auto", auditar=False)
    assert r == ""
    r, rota = H.completar("minha senha", ok, ok, True, False, "auto", auditar=False)
    assert r == "" and rota["destino"] == "nenhum"


def test_modo_persistido(tmp_path):
    arq = tmp_path / "h.json"
    assert H.modo(arq) == "auto"
    H.definir_modo("privado", arq)
    assert H.modo(arq) == "privado"
    try:
        H.definir_modo("xx", arq)
        assert False
    except ValueError:
        pass
