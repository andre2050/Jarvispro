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


V2 = BOM.replace('"dobro: " + str(int(parameters.get("n", 1)) * 2)', '"triplo: " + str(int(parameters.get("n", 1)) * 3)')


def test_versoes_guardadas_comparadas_e_rollback(tmp_path):
    p1 = F.preparar("cria um plugin que dobra números", _llm(BOM), tmp_path)
    assert p1["ok"] and p1["versao"] == 1
    p2 = F.evoluir(p1["id"], "agora triplica", _llm(V2, id=p1["id"]), tmp_path)
    assert p2["ok"] and p2["versao"] == 2 and p2["teste"]["resultados"] == ["triplo: 12"]
    assert [v["versao"] for v in F.versoes(p1["id"], tmp_path)] == [1, 2]
    c = F.comparar(p1["id"], 1, 2, tmp_path)
    assert c["linhas_novas"] >= 1 and c["linhas_removidas"] >= 1 and c["permissoes_novas"] == []
    volta = F.reempacotar(p1["id"], 1, tmp_path)
    assert volta["ok"] and volta["teste"]["resultados"] == ["dobro: 8"]
    assert not F.reempacotar(p1["id"], 9, tmp_path)["ok"]


def test_diff_destaca_permissao_nova_e_evolucao_reprovada_nao_vira_versao(tmp_path):
    p1 = F.preparar("cria um plugin que dobra números", _llm(BOM), tmp_path)
    com_rede = V2 + "\nimport urllib.request\n"
    p2 = F.evoluir(p1["id"], "usa a internet", _llm(com_rede, id=p1["id"]), tmp_path)
    assert p2["ok"]                                              # rede é permitida (declarada e mostrada), programas não
    assert "rede" in F.comparar(p1["id"], 1, p2["versao"], tmp_path)["permissoes_novas"]
    perigosa = V2 + "\nimport subprocess\nsubprocess.run(['ls'])\n"
    p3 = F.evoluir(p1["id"], "roda comandos", _llm(perigosa, id=p1["id"]), tmp_path)
    assert not p3["ok"] and len(F.versoes(p1["id"], tmp_path)) == 2
    assert not F.evoluir("nao_existe", "x", _llm(V2), tmp_path)["ok"]
