"""Loja de plugins: assinatura, permissões declaradas x usadas, hashes, instalação e carregamento."""
import json
import zipfile
from pathlib import Path

import pytest

from core import plugin_loja as L
from core.plugin_loader import discover_plugins

CODIGO_OK = '''
PLUGIN = {"name": "ola_loja", "description": "Diz olá.", "parameters": {"type": "OBJECT", "properties": {}}}

def run(parameters, player=None):
    return "olá da loja"
'''
CODIGO_REDE = '''
import requests
PLUGIN = {"name": "clima_loja", "description": "Clima.", "parameters": {"type": "OBJECT", "properties": {}}}

def run(parameters, player=None):
    return requests.get("https://example.com").text
'''
META = {"id": "ola_loja", "nome": "Olá Loja", "versao": "1.0", "autor": "Maria", "descricao": "Diz olá."}


@pytest.fixture
def ambiente(tmp_path):
    fonte = tmp_path / "fonte"
    fonte.mkdir()
    (fonte / "ola_loja.py").write_text(CODIGO_OK, encoding="utf-8")
    priv, pub = L.gerar_par_de_chaves()
    arq_autores = tmp_path / "autores.json"
    L.confiar_no_autor("Maria", pub, arq_autores)
    return {"tmp": tmp_path, "fonte": fonte, "priv": priv, "pub": pub, "autores": L.autores_confiaveis(arq_autores),
            "pasta": tmp_path / "plugins", "reg": tmp_path / "reg.json"}


def _pacote(amb, assinar=True, meta=None, nome="p"):
    return L.empacotar(amb["fonte"], amb["tmp"] / f"{nome}.nexusplugin", meta or META, amb["priv"] if assinar else None)


def test_analise_estatica_detecta_uso_real():
    u, g = L.permissoes_usadas("import requests\nopen('a.txt')\nimport subprocess")
    assert u == {"rede", "arquivos", "programas"} and not g
    u, g = L.permissoes_usadas("x = eval('1+1')\nimport importlib")
    assert len(g) == 2
    u, _ = L.permissoes_usadas("from pathlib import Path\nPath('x').write_text('y')")
    assert "arquivos" in u
    u, _ = L.permissoes_usadas("import os\nos.system('dir')")
    assert "programas" in u
    u, _ = L.permissoes_usadas("def run(p):\n    return 'nada especial'")
    assert u == set()
    assert L.permissoes_usadas("def (")[1]                      # erro de sintaxe vira problema grave


def test_empacota_assina_abre_e_instala(ambiente):
    pct = L.abrir_pacote(_pacote(ambiente), ambiente["autores"])
    assert pct.assinado and pct.autor_confiavel == "Maria" and pct.permissoes == []
    msg = L.instalar(pct, conceder=[], pasta=ambiente["pasta"], arq_registro=ambiente["reg"])
    assert "instalado" in msg and (ambiente["pasta"] / "ola_loja.py").exists()
    assert L.instalados(ambiente["reg"])[0]["assinado_por"] == "Maria"
    assert L.conferir_arquivo("ola_loja.py", ambiente["pasta"], ambiente["reg"]) == (True, "")
    assert L.conferir_arquivo("solto.py", ambiente["pasta"], ambiente["reg"]) == (True, "")   # local: livre
    L.remover("ola_loja", ambiente["pasta"], ambiente["reg"])
    assert not (ambiente["pasta"] / "ola_loja.py").exists() and L.instalados(ambiente["reg"]) == []


def test_sem_assinatura_ou_autor_desconhecido_nao_instala(ambiente):
    pct = L.abrir_pacote(_pacote(ambiente, assinar=False), ambiente["autores"])
    assert not pct.assinado
    with pytest.raises(L.ErroPacote, match="assinatura"):
        L.instalar(pct, pasta=ambiente["pasta"], arq_registro=ambiente["reg"])
    L.instalar(pct, aceitar_nao_assinado=True, pasta=ambiente["pasta"], arq_registro=ambiente["reg"])  # opt-in explícito
    # assinado por outra chave: autor desconhecido
    outra_priv, _ = L.gerar_par_de_chaves()
    p2 = L.empacotar(ambiente["fonte"], ambiente["tmp"] / "x.nexusplugin", META, outra_priv)
    assert not L.abrir_pacote(p2, ambiente["autores"]).assinado


def test_permissao_nao_declarada_recusa_o_pacote(ambiente):
    (ambiente["fonte"] / "ola_loja.py").write_text(CODIGO_REDE, encoding="utf-8")
    with pytest.raises(L.ErroPacote, match="rede"):
        L.empacotar(ambiente["fonte"], ambiente["tmp"] / "a.nexusplugin", {**META, "permissoes": []}, ambiente["priv"]) and \
            L.abrir_pacote(ambiente["tmp"] / "a.nexusplugin", ambiente["autores"])
    # declarando, abre — mas só instala se a pessoa conceder
    p = L.empacotar(ambiente["fonte"], ambiente["tmp"] / "b.nexusplugin", {**META, "permissoes": ["rede"]}, ambiente["priv"])
    pct = L.abrir_pacote(p, ambiente["autores"])
    assert "acessar a internet" in pct.resumo()
    with pytest.raises(L.ErroPacote, match="não concedidas"):
        L.instalar(pct, conceder=[], pasta=ambiente["pasta"], arq_registro=ambiente["reg"])
    L.instalar(pct, conceder=["rede"], pasta=ambiente["pasta"], arq_registro=ambiente["reg"])


def test_pacote_adulterado_e_zip_malicioso(ambiente):
    p = _pacote(ambiente)
    adulterado = ambiente["tmp"] / "adulterado.nexusplugin"
    with zipfile.ZipFile(p) as zin, zipfile.ZipFile(adulterado, "w") as zout:
        for n in zin.namelist():
            d = zin.read(n)
            zout.writestr(n, d + b"\n# virus" if n == "ola_loja.py" else d)
    with pytest.raises(L.ErroPacote, match="hash|adulterado"):
        L.abrir_pacote(adulterado, ambiente["autores"])
    ruim = ambiente["tmp"] / "ruim.nexusplugin"
    with zipfile.ZipFile(ruim, "w") as z:
        z.writestr("plugin.json", json.dumps({"id": "x"}))
        z.writestr("../fora.py", "x=1")
    with pytest.raises(L.ErroPacote):
        L.abrir_pacote(ruim, ambiente["autores"])
    with pytest.raises(L.ErroPacote, match="zip"):
        (ambiente["tmp"] / "q.nexusplugin").write_bytes(b"nao eh zip")
        L.abrir_pacote(ambiente["tmp"] / "q.nexusplugin", ambiente["autores"])


def test_nao_sobrescreve_arquivo_do_usuario_e_detecta_alteracao_depois(ambiente):
    ambiente["pasta"].mkdir()
    (ambiente["pasta"] / "ola_loja.py").write_text("# meu arquivo", encoding="utf-8")
    pct = L.abrir_pacote(_pacote(ambiente), ambiente["autores"])
    with pytest.raises(L.ErroPacote, match="não vou sobrescrever"):
        L.instalar(pct, pasta=ambiente["pasta"], arq_registro=ambiente["reg"])
    (ambiente["pasta"] / "ola_loja.py").unlink()
    L.instalar(pct, pasta=ambiente["pasta"], arq_registro=ambiente["reg"])
    (ambiente["pasta"] / "ola_loja.py").write_text(CODIGO_OK + "\n# alterado depois", encoding="utf-8")
    ok, motivo = L.conferir_arquivo("ola_loja.py", ambiente["pasta"], ambiente["reg"])
    assert not ok and "mudou" in motivo


def test_carregador_de_plugins_respeita_a_loja(ambiente, monkeypatch):
    monkeypatch.setattr(L, "ARQ_REGISTRO", ambiente["reg"])
    pct = L.abrir_pacote(_pacote(ambiente), ambiente["autores"])
    L.instalar(pct, pasta=ambiente["pasta"], arq_registro=ambiente["reg"])
    (ambiente["pasta"] / "solto.py").write_text(CODIGO_OK.replace("ola_loja", "solto_local"), encoding="utf-8")
    reg = discover_plugins(ambiente["pasta"], set(), logger=lambda m: None)
    assert reg.has("ola_loja") and reg.has("solto_local")
    lista = {r["file"]: r for r in reg.list_for_ui()}
    assert lista["ola_loja.py"]["store"]["assinado_por"] == "Maria" and lista["solto.py"]["store"] is None
    (ambiente["pasta"] / "ola_loja.py").write_text(CODIGO_OK + "\n# mexeram", encoding="utf-8")
    reg = discover_plugins(ambiente["pasta"], set(), logger=lambda m: None)
    assert not reg.has("ola_loja") and reg.has("solto_local")          # adulterado: não carrega


def test_acao_loja_plugins(ambiente, monkeypatch):
    from actions import loja_plugins as A
    from core import confirm
    monkeypatch.setattr(L, "ARQ_REGISTRO", ambiente["reg"])
    monkeypatch.setattr(L, "PASTA_PLUGINS", ambiente["pasta"])
    monkeypatch.setattr(L, "autores_confiaveis", lambda arq=None: ambiente["autores"])
    assert "Nenhum plugin" in A.loja_plugins({"action": "list"})
    assert "[failed]" in A.loja_plugins({"action": "install", "path": str(ambiente["tmp"] / "nao_existe.nexusplugin")})
    nao_assinado = _pacote(ambiente, assinar=False, nome="semsig")
    r = A.loja_plugins({"action": "install", "path": str(nao_assinado)})
    assert "Recusei" in r and "NÃO ASSINADO" in r
    pedidos = []
    monkeypatch.setattr(confirm, "pending_title", lambda: "")
    monkeypatch.setattr(confirm, "request", lambda key, title, detail, run: pedidos.append((title, detail, run)) or "aguardando")
    A.loja_plugins({"action": "install", "path": str(_pacote(ambiente))})
    assert pedidos and "OLÁ LOJA" in pedidos[0][0] and "Maria" in pedidos[0][1]
    assert not (ambiente["pasta"] / "ola_loja.py").exists()             # nada instalado antes do CONFIRMAR
    assert pedidos[0][2]().startswith("[done]") and (ambiente["pasta"] / "ola_loja.py").exists()
    assert "Olá Loja" in A.loja_plugins({"action": "list"})
    assert A.loja_plugins({"action": "remove", "name": "ola_loja"}).startswith("[done]")
    assert A.TOOL["name"] == "loja_plugins"
