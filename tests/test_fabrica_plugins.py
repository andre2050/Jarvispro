import json
from core import fabrica_plugins as F

BOM = '''
def _h(parameters, **kw):
    return "dobro: " + str(int(parameters.get("n", 1)) * 2)
TOOL = {"name": "dobro", "description": "dobra", "parameters": {"type": "OBJECT", "properties": {}}, "handler": _h}
'''


def _llm(codigo, **extra):
    d = {"id": "Dobro Útil", "nome": "Dobro", "descricao": "dobra números", "codigo": codigo, "exemplos": [{"n": 4}]}
    d.update(extra)
    return lambda p: "```json\n" + json.dumps(d) + "\n```"


def test_fluxo_completo_gera_pacote_valido(tmp_path):
    from core import plugin_loja as L
    p = F.preparar("cria um plugin que dobra números", _llm(BOM), tmp_path)
    assert p["ok"] and p["teste"]["resultados"] == ["dobro: 8"]
    pac = L.abrir_pacote(p["pacote"])
    assert pac.id == p["id"] and not pac.assinado


def test_revisao_barra_codigo_perigoso(tmp_path):
    ruim = BOM + "\nimport subprocess\nsubprocess.run(['ls'])\n"
    p = F.preparar("cria um plugin perigoso aqui", _llm(ruim), tmp_path)
    assert not p["ok"] and "Revisão" in p["motivo"]


def test_sem_tool_e_erro_de_sintaxe(tmp_path):
    assert "TOOL" in " ".join(F.revisar("x = 1")["problemas"])
    assert not F.revisar("def (:")["aprovado"]


def test_caixa_de_areia_pega_erro_laco_e_rede():
    assert not F.testar("raise RuntimeError('boom')")["ok"]
    assert not F.testar(BOM.replace('"handler": _h', '"handler": 5'))["ok"]
    assert not F.testar("import time\nwhile True: time.sleep(0.1)", tempo=2)["ok"]
    rede = '''
import socket
def _h(p, **k):
    socket.create_connection(("example.com", 80), timeout=2)
    return "conectou"
TOOL = {"name": "r", "description": "d", "parameters": {}, "handler": _h}
'''
    t = F.testar(rede)
    assert not t["ok"] and "rede" in t["erro"].lower()


def test_resposta_do_modelo_invalida(tmp_path):
    assert not F.preparar("cria um plugin qualquer", lambda p: "desculpe", tmp_path)["ok"]
    assert not F.preparar("curto", _llm(BOM), tmp_path)["ok"]
