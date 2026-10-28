import pytest

from core import modo_avancado as M

BOM = "def main(args):\n    return str(int(args.get('a', 0)) * 2)\n"


def test_guardar_aceita_so_calculo_e_texto(tmp_path):
    arq = tmp_path / "s.json"
    assert M.guardar("dobro", BOM, "dobra", arq) == "dobro"
    for ruim in ("import os\ndef main(a):\n    return os.listdir('.')\n", "import requests\ndef main(a):\n    return ''\n",
                 "import subprocess\ndef main(a):\n    return ''\n", "x = 1\n", "", "import importlib\ndef main(a):\n    return ''\n",
                 "def main(a):\n    return open('/etc/passwd').read()\n"):
        with pytest.raises(M.ErroScript):
            M.guardar("ruim", ruim, "", arq)
    assert [s["nome"] for s in M.listar(arq)] == ["dobro"]


def test_executa_isolado_de_verdade_e_exige_aprovacao(tmp_path):
    arq = tmp_path / "s.json"
    M.guardar("dobro", BOM, "", arq)
    assert M.precisa_confirmar("dobro", arq)
    with pytest.raises(M.ErroScript, match="não foi aprovado"):
        M.executar("dobro", {"a": 4}, arq)
    M.aprovar("dobro", arq)
    assert M.executar("dobro", {"a": 4}, arq) == "8"                         # sandbox real (subprocesso -I)


def test_mudar_o_codigo_revoga_a_aprovacao(tmp_path):
    arq = tmp_path / "s.json"
    M.guardar("dobro", BOM, "", arq)
    M.aprovar("dobro", arq)
    M.guardar("dobro", BOM, "só a descrição", arq)                           # mesmo código mantém
    assert not M.precisa_confirmar("dobro", arq)
    M.guardar("dobro", BOM.replace("* 2", "* 3"), "", arq)                   # outro código revoga
    assert M.precisa_confirmar("dobro", arq)


def test_script_que_trava_ou_quebra_vira_erro(tmp_path):
    arq = tmp_path / "s.json"
    M.guardar("laco", "def main(a):\n    while True:\n        pass\n", "", arq)
    M.aprovar("laco", arq)
    with pytest.raises(M.ErroScript, match="falhou"):
        M.executar("laco", {}, arq, tempo=2)
    M.guardar("erro", "def main(a):\n    return 1 / 0\n", "", arq)
    M.aprovar("erro", arq)
    with pytest.raises(M.ErroScript, match="ZeroDivision"):
        M.executar("erro", {}, arq)


def test_adulterar_arquivo_por_fora_e_detectado(tmp_path):
    import json
    arq = tmp_path / "s.json"
    M.guardar("dobro", BOM, "", arq)
    M.aprovar("dobro", arq)
    d = json.loads(arq.read_text())
    d["dobro"]["codigo"] = "import os\ndef main(a):\n    return os.getcwd()\n"
    arq.write_text(json.dumps(d))
    assert M.precisa_confirmar("dobro", arq)                                 # hash atual != aprovado


def test_ia_local_fica_no_pc():
    chamadas = []
    assert M.perguntar_local("oi", lambda t: (chamadas.append(t) or "olá")) == "olá"
    assert "não configurada" in M.perguntar_local("oi", None)


def test_acao_pede_confirmar_na_primeira_vez(tmp_path, monkeypatch):
    from actions import modo_avancado as A
    from core import confirm
    monkeypatch.setattr(M, "ARQUIVO", tmp_path / "s.json")
    pedidos = []
    monkeypatch.setattr(confirm, "pending_title", lambda: None)
    monkeypatch.setattr(confirm, "request", lambda **k: (pedidos.append(k) or "pedi"))
    A.modo_avancado({"action": "save", "name": "dobro", "code": BOM})
    assert A.modo_avancado({"action": "run", "name": "dobro", "args": {"a": 2}}) == "pedi" and pedidos
    assert pedidos[0]["run"]() == "[done] 4"                                  # após CONFIRMAR: aprova e roda
    assert A.modo_avancado({"action": "run", "name": "dobro", "args": {"a": 5}}) == "[done] 10"   # depois não pede de novo
