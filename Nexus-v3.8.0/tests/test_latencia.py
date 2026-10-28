"""3.3 — painel de latência (core/latencia.py) e cache de respostas (core/cache_respostas.py)."""
import time

import pytest

from core import cache_respostas as CR
from core import latencia as LAT


@pytest.fixture(autouse=True)
def _limpo(tmp_path, monkeypatch):
    monkeypatch.setattr(LAT, "ARQUIVO", tmp_path / "lat.json")
    CR.limpar()
    yield
    LAT._atual = None


def test_trace_mede_etapas_e_conta_da_fala_ate_a_primeira_fala():
    tr = LAT.iniciar("voz", "que horas são", escutar_ms=700)
    with tr.medir("rota"):
        time.sleep(0.02)
    with tr.medir("preparar"):
        time.sleep(0.03)
    with tr.medir("modelo"):
        time.sleep(0.01)
        tr.primeiro_token()
    LAT.marca_ferramenta(120, cache=True)
    LAT.marca_primeira_fala()
    primeira = tr.primeira_fala_ms
    LAT.marca_primeira_fala()                              # só a primeira vale
    assert tr.primeira_fala_ms == primeira
    reg = tr.fechar(True)
    assert reg["etapas"]["escutar"] == 700 and reg["etapas"]["ferramenta"] == 120
    assert reg["etapas"]["rota"] >= 15 and reg["etapas"]["preparar"] >= 25
    assert reg["primeira_fala_ms"] >= 700 + 50            # inclui o "escutar"
    assert reg["primeiro_token_ms"] is not None and reg["cache"] == 1
    assert LAT.atual() is None and tr.fechar(True) is None   # fecha uma vez só
    assert LAT.pedidos()[-1]["texto"] == "que horas são"


def test_sem_pedido_aberto_as_marcas_sao_ignoradas():
    LAT.marca_primeira_fala()
    LAT.marca_ferramenta(10)
    assert LAT.pedidos() == []


def test_relatorio_acha_o_gargalo_e_as_dicas():
    for i in range(6):
        LAT._gravar({"t": 1, "origem": "voz", "texto": f"p{i}", "rota": "forte", "ok": True,
                     "etapas": {"escutar": 600, "preparar": 150, "rota": 5, "modelo": 3000 + i * 100, "ferramenta": 400},
                     "primeira_fala_ms": 3500 + i * 100, "primeiro_token_ms": 900, "total_ms": 5000,
                     "ferramentas": 2, "cache": 1})
    LAT.registrar_total("gemini", 1800)
    r = LAT.relatorio()
    assert r["gargalo"] == "modelo" and r["pedidos"] == 7 and r["detalhados"] == 6
    assert 3500 <= r["fala_mediana_ms"] <= 4000 and r["cache_acertos"] == 6
    txt = LAT.resumo_texto()
    assert "modelo pensar" in txt and "gargalo" in txt and LAT.DICAS["modelo"] in txt
    LAT.esquecer()
    assert "Ainda não medi" in LAT.resumo_texto()


def test_registrar_total_ignora_valor_absurdo():
    LAT.registrar_total("gemini", -5)
    LAT.registrar_total("gemini", 10_000_000)
    assert LAT.pedidos() == []


def test_limite_de_pedidos_guardados():
    for i in range(LAT.MAX_PEDIDOS + 15):
        LAT.registrar_total("gemini", 100 + i)
    ped = LAT.pedidos(1000)
    assert len(ped) == LAT.MAX_PEDIDOS and ped[-1]["primeira_fala_ms"] == 100 + LAT.MAX_PEDIDOS + 14


# ── cache ────────────────────────────────────────────────────────────────────
def test_cache_guarda_clima_por_cidade_e_expira():
    assert CR.obter("weather_report", {"city": "Recife"}) is None
    assert CR.guardar("weather_report", {"city": "Recife"}, "28 graus, sol", agora=1000.0)
    assert CR.obter("weather_report", {"city": "Recife"}, agora=1100.0) == "28 graus, sol"
    assert CR.obter("weather_report", {"city": "Natal"}, agora=1100.0) is None          # outra cidade
    assert CR.obter("weather_report", {"city": "Recife"}, agora=1000.0 + 601) is None    # venceu
    st = CR.estatisticas()
    assert st["acertos"] == 1 and st["faltas"] == 3


def test_cache_so_para_leitura_e_nunca_guarda_erro():
    assert not CR.guardar("file_controller", {"action": "write"}, "ok")                   # escreve: nunca
    assert not CR.guardar("open_app", {"app": "x"}, "ok")
    assert not CR.guardar("weather_report", {}, "Tool 'weather_report' failed: sem rede")
    assert not CR.guardar("weather_report", {}, "Failed to fetch")
    assert not CR.guardar("weather_report", {}, "   ")
    assert not CR.guardar("weather_report", {}, None)
    assert CR.obter("weather_report", {}) is None


def test_refresh_ignora_o_cache():
    CR.guardar("noticias", {"topic": "tech"}, "manchete", agora=1.0)
    assert CR.obter("noticias", {"topic": "tech"}, agora=2.0) == "manchete"
    assert CR.obter("noticias", {"topic": "tech", "refresh": True}, agora=2.0) is None


def test_cache_tem_limite_de_entradas():
    for i in range(CR.MAX_ENTRADAS + 10):
        CR.guardar("noticias", {"i": i}, f"n{i}", agora=float(i))
    assert CR.estatisticas()["entradas"] == CR.MAX_ENTRADAS
    assert CR.obter("noticias", {"i": 0}, agora=100.0) is None                            # o mais velho saiu
