"""Testes das finanças simples: valores em português, períodos, orçamento e arquivo à prova de queda."""
import json
import types
from datetime import datetime

import pytest

from actions import simple_finance as sf
from core.pt_time import BRASILIA

HOJE = datetime(2026, 10, 22, 15, 0)                       # quinta-feira, horário de Brasília
HOJE_TS = HOJE.replace(tzinfo=BRASILIA).timestamp()


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    """Arquivos numa pasta temporária e relógio parado em 22/10/2026 15:00."""
    monkeypatch.setattr(sf, "_FILE", tmp_path / "finance_entries.json")
    monkeypatch.setattr(sf, "_BUDGETS", tmp_path / "finance_budgets.json")
    monkeypatch.setattr(sf, "agora", lambda: HOJE)
    monkeypatch.setattr(sf, "time", types.SimpleNamespace(time=lambda: HOJE_TS))
    return tmp_path


def run(**kw):
    return sf.simple_finance(kw)


# ── números e dinheiro ───────────────────────────────────────────────────────

@pytest.mark.parametrize("entrada, esperado", [
    (35, 35.0), (35.5, 35.5), ("35", 35.0), ("35,50", 35.5), ("35.50", 35.5),
    ("R$ 1.234,56", 1234.56), ("1,234.56", 1234.56), ("1.234", 1234.0), ("1234,5", 1234.5),
    ("  R$12 ", 12.0),
])
def test_valor_entende_formatos_brasileiros(entrada, esperado):
    assert sf._valor(entrada) == esperado


@pytest.mark.parametrize("entrada", [None, "", "abc", True, "-", float("nan"), float("inf")])
def test_valor_rejeita_lixo(entrada):
    assert sf._valor(entrada) is None


def test_real_formata_em_reais():
    assert sf.real(1234.5) == "R$ 1.234,50"
    assert sf.real(0) == "R$ 0,00"
    assert sf.real(-10) == "-R$ 10,00"


# ── datas e períodos ─────────────────────────────────────────────────────────

def test_data_aceita_hoje_ontem_e_formatos():
    assert sf._data("hoje") == HOJE
    assert sf._data("ontem").day == 21
    assert sf._data("anteontem").day == 20
    assert (sf._data("05/10").month, sf._data("05/10").day, sf._data("05/10").year) == (10, 5, 2026)
    assert sf._data("2026-09-30").month == 9
    assert sf._data("05/10/26").year == 2026
    assert sf._data("31/02") is None
    assert sf._data("qualquer coisa") is None
    assert sf._data("") is None


def test_periodos():
    ini, fim, nome = sf._periodo("mes")
    assert (ini, fim, nome) == (datetime(2026, 10, 1), datetime(2026, 11, 1), "neste mês")
    ini, fim, nome = sf._periodo("mês passado")
    assert (ini, fim, nome) == (datetime(2026, 9, 1), datetime(2026, 10, 1), "no mês passado")
    ini, fim, _ = sf._periodo("semana")
    assert ini == datetime(2026, 10, 19) and fim == datetime(2026, 10, 26)      # segunda a segunda
    ini, fim, _ = sf._periodo("semana passada")
    assert ini == datetime(2026, 10, 12) and fim == datetime(2026, 10, 19)
    ini, fim, _ = sf._periodo("hoje")
    assert ini == datetime(2026, 10, 22) and fim == datetime(2026, 10, 23)
    assert sf._periodo("ano")[:2] == (datetime(2026, 1, 1), datetime(2027, 1, 1))
    assert sf._periodo("tudo")[:2] == (None, None)
    assert sf._periodo(None)[2] == "neste mês"


def test_periodo_de_dezembro_vira_o_ano(monkeypatch):
    monkeypatch.setattr(sf, "agora", lambda: datetime(2026, 12, 15, 10, 0))
    assert sf._periodo("mes")[:2] == (datetime(2026, 12, 1), datetime(2027, 1, 1))
    monkeypatch.setattr(sf, "agora", lambda: datetime(2027, 1, 5, 10, 0))
    assert sf._periodo("mês passado")[:2] == (datetime(2026, 12, 1), datetime(2027, 1, 1))


# ── lançar ───────────────────────────────────────────────────────────────────

def test_despesa_e_receita_sao_gravadas():
    r = run(action="add_expense", amount=35.5, category="mercado", description="feira")
    assert r.startswith("[done]") and "R$ 35,50" in r and "Mercado" in r
    r = run(action="add_income", amount="3.000,00", category="Salário")
    assert r.startswith("[done]") and "R$ 3.000,00" in r
    dados = json.loads(sf._FILE.read_text(encoding="utf-8"))
    assert [(e["type"], e["amount"], e["category"]) for e in dados] == [
        ("expense", 35.5, "Mercado"), ("income", 3000.0, "Salário")]
    assert dados[0]["timestamp"] == HOJE_TS


@pytest.mark.parametrize("valor", [None, "", "abc", 0, -5, 10**12])
def test_valor_invalido_nao_grava(valor):
    assert run(action="add_expense", amount=valor, category="x").startswith("[failed]")
    assert not sf._FILE.exists()


def test_data_invalida_nao_grava():
    assert run(action="add_expense", amount=10, date="semana que vem").startswith("[failed]")
    assert not sf._FILE.exists()


def test_data_no_passado_vale_no_periodo_certo():
    run(action="add_expense", amount=50, category="uber", date="ontem")
    run(action="add_expense", amount=70, category="uber", date="15/09")
    assert "despesas R$ 50,00" in run(action="summary", period="mes")
    assert "despesas R$ 70,00" in run(action="summary", period="mês passado")
    assert "despesas R$ 0,00" in run(action="summary", period="hoje")
    # a data aparece na confirmação
    assert "em 21/10" in run(action="add_expense", amount=1, category="x", date="ontem")


def test_data_informada_usa_o_fuso_de_brasilia_e_nao_o_do_computador():
    run(action="add_expense", amount=5, category="x", date="ontem")
    ts = json.loads(sf._FILE.read_text(encoding="utf-8"))[0]["timestamp"]
    assert ts == datetime(2026, 10, 21, 15, 0, tzinfo=BRASILIA).timestamp()


def test_categoria_reaproveita_a_grafia_anterior():
    run(action="add_expense", amount=10, category="Alimentação")
    run(action="add_expense", amount=10, category="alimentacao")
    run(action="add_expense", amount=10, category="ALIMENTAÇÃO")
    cats = {e["category"] for e in json.loads(sf._FILE.read_text(encoding="utf-8"))}
    assert cats == {"Alimentação"}


def test_categoria_vazia_vira_geral():
    run(action="add_expense", amount=10)
    assert json.loads(sf._FILE.read_text(encoding="utf-8"))[0]["category"] == "Geral"


def test_texto_enorme_e_cortado():
    run(action="add_expense", amount=10, category="c" * 500, description="d" * 5000)
    e = json.loads(sf._FILE.read_text(encoding="utf-8"))[0]
    assert len(e["category"]) <= 60 and len(e["description"]) <= 240


def test_limite_de_lancamentos(monkeypatch):
    monkeypatch.setattr(sf, "MAX_LANCAMENTOS", 5)
    for i in range(8):
        run(action="add_expense", amount=i + 1, category="x")
    dados = json.loads(sf._FILE.read_text(encoding="utf-8"))
    assert [e["amount"] for e in dados] == [4.0, 5.0, 6.0, 7.0, 8.0]


# ── resumo, categorias, lista ────────────────────────────────────────────────

def _popular():
    run(action="add_income", amount=3000, category="Salário")
    run(action="add_expense", amount=300, category="Mercado")
    run(action="add_expense", amount=100, category="Uber")
    run(action="add_expense", amount=200, category="Mercado", date="10/09")      # mês passado


def test_resumo_do_mes_com_comparacao():
    _popular()
    r = run(action="summary")
    assert "receitas R$ 3.000,00" in r and "despesas R$ 400,00" in r and "saldo R$ 2.600,00" in r
    assert "Mercado R$ 300,00" in r
    assert "No mês passado foram R$ 200,00 (+100%" in r


def test_resumo_de_uma_categoria():
    _popular()
    assert run(action="summary", category="mercado") == "[done] Gastos com mercado neste mês: R$ 300,00."
    assert "R$ 200,00" in run(action="summary", category="mercado", period="mês passado")


def test_resumo_sem_dados():
    assert run(action="summary") == "[done] Ainda não há lançamentos."


def test_por_categoria_com_percentual():
    _popular()
    r = run(action="by_category")
    assert "total R$ 400,00" in r and "Mercado R$ 300,00 (75%)" in r and "Uber R$ 100,00 (25%)" in r
    assert r.index("Mercado") < r.index("Uber")                                   # maior primeiro


def test_por_categoria_vazio():
    run(action="add_income", amount=10)
    assert "Nenhuma despesa" in run(action="by_category")


def test_lista_mostra_os_mais_recentes_primeiro():
    for v in (1, 2, 3, 4):
        run(action="add_expense", amount=v, category="x")
    r = run(action="list", count=2)
    assert r.index("R$ 4,00") < r.index("R$ 3,00") and "R$ 2,00" not in r


def test_lista_filtra_por_categoria_e_aceita_count_ruim():
    _popular()
    assert "Uber" in run(action="list", category="uber", count="muitos")
    assert "Mercado" not in run(action="list", category="uber")
    assert "nesse filtro" in run(action="list", category="inexistente")


# ── orçamento ────────────────────────────────────────────────────────────────

def test_orcamento_avisa_em_80_e_ao_estourar():
    assert "definido em R$ 500,00" in run(action="set_budget", category="Lazer", amount=500)
    assert "ATENÇÃO" not in run(action="add_expense", amount=100, category="lazer")
    r = run(action="add_expense", amount=320, category="lazer")                    # 420 de 500 = 84%
    assert "Cuidado" in r and "84%" in r
    r = run(action="add_expense", amount=100, category="lazer")                    # 520 de 500
    assert "ATENÇÃO" in r and "estourou" in r and "104%" in r


def test_orcamento_total_soma_todas_as_categorias():
    run(action="set_budget", amount=1000)                                         # sem categoria = total
    run(action="add_expense", amount=500, category="a")
    r = run(action="add_expense", amount=400, category="b")
    assert "orçamento total" in r and "90%" in r


def test_orcamento_so_conta_o_mes_atual():
    run(action="set_budget", category="Lazer", amount=100)
    r = run(action="add_expense", amount=500, category="lazer", date="10/09")      # mês passado
    assert "ATENÇÃO" not in r and "Cuidado" not in r


def test_status_do_orcamento():
    assert "Nenhum limite" in run(action="budget_status")
    run(action="set_budget", category="Lazer", amount=200)
    run(action="set_budget", category="total", amount=1000)
    run(action="add_expense", amount=150, category="Lazer")
    r = run(action="budget_status")
    assert "Total: R$ 150,00 de R$ 1.000,00 (15%)" in r
    assert "Lazer: R$ 150,00 de R$ 200,00 (75%)" in r
    run(action="add_expense", amount=100, category="Lazer")
    assert "ESTOUROU" in run(action="budget_status")


def test_orcamento_zero_remove_e_redefinir_substitui():
    run(action="set_budget", category="Lazer", amount=200)
    run(action="set_budget", category="lazer", amount=300)
    assert json.loads(sf._BUDGETS.read_text(encoding="utf-8")) == {"Lazer": 300.0}
    assert "removido" in run(action="set_budget", category="lazer", amount=0)
    assert json.loads(sf._BUDGETS.read_text(encoding="utf-8")) == {}


@pytest.mark.parametrize("valor", [None, "abc", -1])
def test_orcamento_com_valor_ruim(valor):
    assert run(action="set_budget", category="x", amount=valor).startswith("[failed]")


# ── apagar ───────────────────────────────────────────────────────────────────

def test_apagar_o_ultimo():
    assert run(action="delete_last").startswith("[failed]")
    run(action="add_expense", amount=10, category="a")
    run(action="add_expense", amount=20, category="b")
    r = run(action="delete_last")
    assert "R$ 20,00" in r and "em B." in r
    assert [e["amount"] for e in json.loads(sf._FILE.read_text(encoding="utf-8"))] == [10.0]


# ── robustez ─────────────────────────────────────────────────────────────────

def test_acao_desconhecida_e_padrao():
    assert run(action="hackear").startswith("[failed]")
    assert sf.simple_finance({}).startswith("[done]")                              # padrão: resumo
    assert sf.simple_finance(None).startswith("[done]")


def test_arquivo_corrompido_nao_derruba():
    sf._FILE.write_text("{isso não é json", encoding="utf-8")
    assert run(action="summary") == "[done] Ainda não há lançamentos."
    assert run(action="add_expense", amount=5, category="x").startswith("[done]")
    assert len(json.loads(sf._FILE.read_text(encoding="utf-8"))) == 1


def test_formato_antigo_da_versao_2_0_continua_valendo():
    antigo = [{"type": "expense", "amount": 40.0, "category": "mercado", "description": "",
               "timestamp": HOJE_TS}, {"type": "income", "amount": 100, "category": "x",
                                         "description": "", "timestamp": HOJE_TS},
              "lixo", {"type": "outro", "amount": 1}]
    sf._FILE.write_text(json.dumps(antigo), encoding="utf-8")
    r = run(action="summary")
    assert "receitas R$ 100,00" in r and "despesas R$ 40,00" in r
    run(action="add_expense", amount=10, category="Mercado")
    assert {e["category"] for e in sf._lancamentos() if e["type"] == "expense"} == {"mercado"}


def test_gravacao_nao_deixa_arquivo_temporario(ambiente):
    run(action="add_expense", amount=1, category="x")
    assert [p.name for p in ambiente.iterdir()] == ["finance_entries.json"]


def test_falha_ao_gravar_preserva_o_historico(monkeypatch, ambiente):
    run(action="add_expense", amount=1, category="x")
    antes = sf._FILE.read_text(encoding="utf-8")

    def quebra(*a, **k):
        raise OSError("disco cheio")
    monkeypatch.setattr(sf.json, "dump", quebra)
    assert run(action="add_expense", amount=2, category="y").startswith("[failed]")
    assert sf._FILE.read_text(encoding="utf-8") == antes
    assert [p.name for p in ambiente.iterdir()] == ["finance_entries.json"]       # sem .tmp sobrando


def test_tool_esta_bem_formada():
    t = sf.TOOL
    assert t["name"] == "simple_finance" and callable(t["handler"])
    assert set(t["parameters"]["properties"]["action"]["enum"]) == set(sf._ACOES)
    assert t["parameters"]["required"] == ["action"]
