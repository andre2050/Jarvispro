"""Testes do Nexus Forge (core/forge_engine.py + actions/forge_app.py) com uma "IA" de mentira: o fluxo inteiro
roda de verdade (arquivos, comandos, git, zip); só as respostas do Claude são roteirizadas."""
import json
import shutil
import sys
import time
import zipfile
from types import SimpleNamespace

import pytest

from actions import forge_app as FA
from core import action_loader
from core import forge_engine as FE


# ── "Claude" de mentira ──────────────────────────────────────────────────────

def resp(blocos, stop="tool_use"):
    uso = SimpleNamespace(input_tokens=1000, output_tokens=500)
    return SimpleNamespace(content=blocos, stop_reason=stop, usage=uso)


def tu(i, nome, **entrada):
    return SimpleNamespace(type="tool_use", id=i, name=nome, input=entrada)


def tx(texto):
    return SimpleNamespace(type="text", text=texto)


class ClienteFalso:
    def __init__(self, fila):
        self.fila = fila
        self.chamadas = []
        self.messages = self

    def create(self, **kw):
        self.chamadas.append(kw)
        return self.fila.pop(0)


PLANO = json.dumps({
    "titulo": "Lista de Tarefas", "resumo": "Um app simples de tarefas.", "stack": "Python + Tkinter",
    "arquivos": ["main.py", "README.md"], "entrada": "main.py",
    "comando_teste": "python -m py_compile main.py", "como_executar": "python main.py", "riscos": [],
})


def fila_de_construcao(extra_revisor=None):
    """Arquiteto + construtor (escreve, concluí) + revisor sem problemas graves."""
    return [
        resp([tx(PLANO)], "end_turn"),
        resp([tu("a", "escrever_arquivo", caminho="main.py", conteudo="print('tarefas')\n")]),
        resp([tu("b", "concluir", resumo="App de tarefas criado.", como_executar="python main.py")]),
        resp([tu("c", "reportar_revisao", nota=9, problemas=extra_revisor or [])]),
    ]


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr(FA, "PROJECTS_DIR", tmp_path / "NexusForge")
    monkeypatch.setattr(FA, "_cache", {})
    monkeypatch.setattr(FE, "CONFIG_DIR", tmp_path / "cfg")
    monkeypatch.setattr(FE.NexusForge, "_venv_python", lambda self: sys.executable)   # sem criar venv a cada teste
    FA._msgs.clear()
    FA._ativo.clear()
    yield
    FA._msgs.clear()


def motor(tmp_path, ouvir=lambda: "", falas=None):
    falas = [] if falas is None else falas
    return FE.NexusForge(falar=falas.append, ouvir=ouvir, pasta_projetos=tmp_path / "raiz",
                         progresso_voz=False, segundo_plano=False)


def com_projeto(tmp_path):
    m = motor(tmp_path)
    m.pasta = m._pasta_nova("proj")
    m.plano = {"titulo": "proj", "comando_teste": "python -m py_compile main.py", "entrada": "main.py"}
    m._iniciar_projeto(m.plano, "x")
    return m


def espera_fim(falas, limite=30):
    fim = time.time() + limite
    while not falas and time.time() < fim:
        time.sleep(0.05)
    return " ".join(falas)


# ── ação: encaixe no Nexus ───────────────────────────────────────────────────

def test_a_acao_passa_pelo_carregador_do_nexus():
    rec = action_loader._validate(FA, "forge_app.py")
    assert rec.valid, rec.error
    assert rec.name == "forge_app" and callable(rec.handler)


def test_o_forge_nao_disputa_o_pedido_comum_com_o_dev_agent():
    d = FA.TOOL["description"]
    assert FA.TOOL["name"] != "dev_agent"
    assert "ONLY when the user explicitly asks for the Forge" in d and "use dev_agent instead" in d


def test_sem_projeto_aberto_alterar_e_recusado():
    r = FA.forge_app({"action": "modify", "description": "adiciona login"})
    assert r.startswith("[failed]") and "no Forge project" in r


def test_acao_desconhecida_e_pedido_vazio():
    assert FA.forge_app({"action": "plan"}).startswith("[failed]")
    assert FA.forge_app({"action": "build"}).startswith("[failed]")      # sem plano aprovado
    assert "Unknown action" in FA.forge_app({"action": "voar"}) or FA.forge_app({"action": "voar"}).startswith("[failed]")


def test_plano_depois_construcao_em_segundo_plano_e_aviso_no_fim():
    m = FA._motor()
    m._cliente_cache = ClienteFalso(fila_de_construcao())
    r = FA.forge_app({"action": "plan", "description": "app de tarefas para o PC"})
    assert r.startswith("[plan]") and "Lista de Tarefas" in r and "Do NOT call action=build" in r
    assert m.plano_pendente["titulo"] == "Lista de Tarefas"

    avisos = []
    r = FA.forge_app({"action": "build"}, speak=avisos.append)
    assert r.startswith("[done]")
    texto = espera_fim(avisos)
    assert "[FORGE_DONE]" in texto and "Pronto!" in texto and "Os testes passaram" in texto
    assert (m.pasta / "main.py").read_text() == "print('tarefas')\n"
    assert m.plano_pendente is None
    assert m.tokens_missao == 1500 * 4          # o arquiteto também conta no gasto


def test_alterar_e_desfazer_um_projeto_do_forge():
    m = FA._motor()
    m._cliente_cache = ClienteFalso(fila_de_construcao())
    FA.forge_app({"action": "plan", "description": "app de tarefas"})
    avisos = []
    FA.forge_app({"action": "build"}, speak=avisos.append)
    espera_fim(avisos)

    m._cliente_cache = ClienteFalso([
        resp([tu("h", "escrever_arquivo", caminho="main.py", conteudo="print('com login')\n")]),
        resp([tu("i", "concluir", resumo="Login adicionado.")]),
    ])
    avisos.clear()
    FA.forge_app({"action": "modify", "description": "adiciona uma tela de login"}, speak=avisos.append)
    assert "Login adicionado" in espera_fim(avisos)
    assert (m.pasta / "main.py").read_text() == "print('com login')\n"

    r = FA.forge_app({"action": "undo"})
    assert r.startswith("[done]") and "Desfeito" in r
    assert (m.pasta / "main.py").read_text() == "print('tarefas')\n"


def test_empacotar_gera_zip_sem_lixo():
    m = FA._motor()
    m.pasta = m._pasta_nova("zipado")
    m._iniciar_projeto({"titulo": "zipado"}, "x")
    (m.pasta / "main.py").write_text("print(1)\n", encoding="utf-8")
    (m.pasta / ".venv").mkdir()
    (m.pasta / ".venv" / "lixo.txt").write_text("x", encoding="utf-8")
    r = FA.forge_app({"action": "package"})
    assert r.startswith("[done]")
    zips = list((m.raiz / "_entregas").glob("zipado-*.zip"))
    assert len(zips) == 1
    nomes = zipfile.ZipFile(zips[0]).namelist()
    assert "main.py" in nomes and not any(n.startswith((".venv/", ".git/", ".forge/")) for n in nomes)


# ── publicar: só com a confirmação da tela ───────────────────────────────────

def test_publicar_pede_confirmacao_na_tela_e_nao_publica_antes(monkeypatch):
    m = FA._motor()
    m.pasta = m._pasta_nova("meuapp")
    m._iniciar_projeto({"titulo": "meuapp"}, "x")
    publicou = []
    monkeypatch.setattr(m, "publicar_agora", lambda: publicou.append(1) or "publicado")
    pedido = {}

    def falso_request(key, title, detail, run):
        pedido.update(key=key, title=title, detail=detail, run=run)
        return "[CONFIRMATION_PENDING] ..."

    monkeypatch.setattr(FA._confirm, "request", falso_request)
    monkeypatch.setattr(FA._confirm, "pending_title", lambda: None)
    r = FA.forge_app({"action": "publish"})
    assert r.startswith("[CONFIRMATION_PENDING]")
    assert "PUBLICAR MEUAPP" in pedido["title"] and "privado" in pedido["detail"]
    assert publicou == []                                   # nada saiu antes do CONFIRMAR
    assert pedido["run"]() == "[done] publicado" and publicou == [1]


def test_publicar_sem_interface_recusa_em_vez_de_publicar(monkeypatch):
    m = FA._motor()
    m.pasta = m._pasta_nova("meuapp")
    m._iniciar_projeto({"titulo": "meuapp"}, "x")
    monkeypatch.setattr(m, "publicar_agora", lambda: pytest.fail("publicou sem confirmação"))
    monkeypatch.setattr(FA._confirm, "_show_cb", None, raising=False)
    monkeypatch.setattr(FA._confirm, "pending_title", lambda: None)
    r = FA.forge_app({"action": "publish"})
    assert "has not done it" in r or "not available" in r


def test_publicar_agora_sem_gh_instalado(tmp_path, monkeypatch):
    m = com_projeto(tmp_path)
    monkeypatch.setattr(FE.shutil, "which", lambda nome: None)
    assert "GitHub CLI" in m.publicar_agora()


# ── motor: segurança ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("ruim", ["../fora.txt", ".git/config", ".venv/x", ".forge/trace.jsonl", "/etc/passwd"])
def test_caminhos_fora_do_projeto_sao_bloqueados(tmp_path, ruim):
    m = com_projeto(tmp_path)
    with pytest.raises(ValueError):
        m._caminho_seguro(ruim)
    assert "ERRO" in m._executar_ferramenta("escrever_arquivo", {"caminho": ruim, "conteudo": "x"})


def test_ferramentas_de_arquivo(tmp_path):
    m = com_projeto(tmp_path)
    assert m._executar_ferramenta("escrever_arquivo", {"caminho": "src/a.py", "conteudo": "x=1\n"}).startswith("ok")
    assert m._executar_ferramenta("ler_arquivo", {"caminho": "src/a.py"}) == "x=1\n"
    assert "src/a.py" in m._executar_ferramenta("listar_arquivos", {})
    assert "ERRO" in m._executar_ferramenta("escrever_arquivo", {"caminho": "a.exe", "conteudo": "x"})
    grande = "x" * (FE.ARQUIVO_MAX + 1)
    assert "ERRO" in m._executar_ferramenta("escrever_arquivo", {"caminho": "g.txt", "conteudo": grande})


@pytest.mark.parametrize("cmd", ["rm -rf .", "python -c 'print(1)'", "python ../a.py", "pip install git+https://x/y",
                                 "pip uninstall x", "curl http://x", "python /etc/passwd", "python ~/x.py"])
def test_comandos_perigosos_sao_recusados(tmp_path, cmd):
    codigo, _ = com_projeto(tmp_path)._comando(cmd)
    assert codigo in (126, 127)


def test_a_chave_da_api_nao_vaza_para_o_programa_gerado(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-NAO-DEVE-VAZAR")
    monkeypatch.setenv("GH_TOKEN", "ghp-NAO-DEVE-VAZAR")
    m = com_projeto(tmp_path)
    (m.pasta / "env.py").write_text("import os\nprint(os.environ.get('ANTHROPIC_API_KEY'), os.environ.get('GH_TOKEN'))\n",
                                    encoding="utf-8")
    codigo, saida = m._comando("python env.py")
    assert codigo == 0 and "NAO-DEVE-VAZAR" not in saida and "None None" in saida


def test_comando_que_trava_e_encerrado(tmp_path, monkeypatch):
    monkeypatch.setattr(FE, "TIMEOUT_CMD", 1)
    m = com_projeto(tmp_path)
    (m.pasta / "trava.py").write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    codigo, saida = m._comando("python trava.py")
    assert codigo == 124 and "tempo esgotado" in saida


def test_venv_de_verdade_e_criado_dentro_do_projeto(tmp_path, monkeypatch):
    monkeypatch.undo()          # esta daqui usa o _venv_python real
    m = com_projeto(tmp_path)
    codigo, saida = m._comando("python --version")
    assert codigo == 0 and "Python" in saida
    assert (m.pasta / ".venv").is_dir()


# ── motor: git, orçamento, memória ───────────────────────────────────────────

@pytest.mark.skipif(shutil.which("git") is None, reason="git não instalado")
def test_desfazer_volta_ao_marco_e_guarda_o_estado_anterior(tmp_path):
    m = com_projeto(tmp_path)
    arq = m.pasta / "main.py"
    m._marcar("m1")
    arq.write_text("v2\n", encoding="utf-8")
    m._checkpoint("v2")
    m._marcar("m2")
    arq.write_text("v3 ruim\n", encoding="utf-8")
    m._checkpoint("v3")
    arq.write_text("minha edição manual, sem commit\n", encoding="utf-8")   # a pessoa mexeu à mão
    m.desfazer()
    assert arq.read_text() == "v2\n"
    # o que não estava commitado foi guardado antes do reset e continua recuperável no reflog
    linhas = [l for l in m._git("reflog").stdout.splitlines() if "estado antes de desfazer" in l]
    assert linhas
    assert m._git("show", f"{linhas[0].split()[0]}:main.py").stdout == "minha edição manual, sem commit\n"


def test_desfazer_sem_historico_avisa(tmp_path):
    falas = []
    m = motor(tmp_path, falas=falas)
    m.pasta = m._pasta_nova("novo")
    m._iniciar_projeto({"titulo": "novo"}, "x")
    m.desfazer()
    assert "Não há alteração anterior" in " ".join(falas)


def test_poda_troca_conteudo_antigo_por_marcadores():
    msgs = [{"role": "assistant", "content": [{"type": "tool_use", "id": "1", "name": "escrever_arquivo",
                                               "input": {"caminho": "a", "conteudo": "x" * 2000}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "1", "content": "y" * 2000}]}]
    msgs += [{"role": "user", "content": "z"}] * 10
    FE.NexusForge._podar(msgs)
    assert "omitido" in msgs[0]["content"][0]["input"]["conteudo"]
    assert "omitido" in msgs[1]["content"][0]["content"]


def test_orcamento_por_missao_e_por_dia(tmp_path, monkeypatch):
    m = com_projeto(tmp_path)
    m.tokens_missao = FE.LIMITE_MISSAO + 1
    with pytest.raises(FE.Orcamento):
        m._checar_orcamento()
    m.tokens_missao = 0
    m._gastar(resp([]))
    monkeypatch.setattr(FE, "LIMITE_DIA", 100)
    with pytest.raises(FE.Orcamento):
        m._checar_orcamento()


def test_o_agente_corta_o_que_o_revisor_nao_pode_chamar(tmp_path):
    m = com_projeto(tmp_path)
    m._cliente_cache = ClienteFalso([
        resp([tu("1", "escrever_arquivo", caminho="x.py", conteudo="1")]),      # revisor não tem essa ferramenta
        resp([tu("2", "reportar_revisao", nota=5, problemas=[])]),
    ])
    r = m._agente(FE.SISTEMA_REVISOR, "revise", "m", FE.TOOLS_REVISOR, "reportar_revisao", max_passos=5)
    assert r["nota"] == 5 and not (m.pasta / "x.py").exists()


def test_revisor_acha_problema_grave_e_o_construtor_corrige(tmp_path):
    m = com_projeto(tmp_path)
    (m.pasta / "main.py").write_text("print('v1')\n", encoding="utf-8")
    m._cliente_cache = ClienteFalso([
        resp([tu("1", "reportar_revisao", nota=4, problemas=[
            {"gravidade": "alta", "arquivo": "main.py", "descricao": "falta tratar entrada vazia"}])]),
        resp([tu("2", "escrever_arquivo", caminho="main.py", conteudo="print('v2 corrigido')\n")]),
        resp([tu("3", "concluir", resumo="Corrigido.")]),
    ])
    assert m._revisar_e_corrigir() == 4
    assert (m.pasta / "main.py").read_text() == "print('v2 corrigido')\n"
    assert (m.pasta / ".forge" / "revisao.md").exists()


def test_verificacao_que_falha_manda_corrigir_e_passa(tmp_path):
    m = com_projeto(tmp_path)
    (m.pasta / "main.py").write_text("def x(:\n", encoding="utf-8")       # erro de sintaxe
    m._cliente_cache = ClienteFalso([
        resp([tu("1", "escrever_arquivo", caminho="main.py", conteudo="print('ok')\n")]),
        resp([tu("2", "concluir", resumo="Corrigido.")]),
    ])
    assert m._verificar(m.plano) is True
    assert m._cliente_cache.chamadas, "o construtor deveria ter sido chamado"


def test_retomar_projeto_em_nova_instancia(tmp_path):
    m = com_projeto(tmp_path)
    nome = m.pasta.name
    outra = motor(tmp_path)
    assert outra.pasta is not None and outra.pasta.name == nome
    outra.pasta = None
    assert outra.achar_projeto("proj").name == nome
    assert outra.achar_projeto("inexistente-xyz") is None


# ── motor no console (voz): roteamento e fluxo completo ──────────────────────

def test_roteador_de_voz_do_modo_console(tmp_path):
    falas = []
    m = motor(tmp_path, falas=falas)
    assert m.tratar_comando("Nexus, listar projetos")
    assert m.tratar_comando("Nexus vamos criar um aplicativo do zero")      # sem resposta: cancela
    assert any("cancelei" in f for f in falas)
    for alheio in ("desfazer a última alteração", "publicar no github", "que horas são"):
        assert not m.tratar_comando(alheio)


def test_fluxo_completo_por_voz_no_console(tmp_path):
    respostas = iter(["controlar minhas tarefas", "no PC", "você decide", "você escolhe", "sim, pode começar"])
    falas = []
    m = motor(tmp_path, ouvir=lambda: next(respostas, ""), falas=falas)
    m._cliente_cache = ClienteFalso(fila_de_construcao())
    assert m.tratar_comando("Nexus, vamos criar um aplicativo do zero")
    texto = " | ".join(falas)
    assert "Pronto!" in texto and "nota 9" in texto
    assert m.pasta.name == "lista-de-tarefas" and (m.pasta / "main.py").exists()
    assert not m._cliente_cache.fila


@pytest.mark.parametrize("frase,esperado", [("sim, pode começar", True), ("claro, vai", True),
                                            ("não, cancela", False), ("", False), ("sim mas não", False)])
def test_confirmacao_por_voz(frase, esperado):
    assert FE.NexusForge._sim(frase) is esperado


# ── a chave da Anthropic: onde o Nexus a guarda e o que o Forge diz quando falha ──────────

@pytest.fixture
def config_nexus(tmp_path, monkeypatch):
    """O config/api_keys.json de verdade (memory/config_manager), numa pasta temporária e sem chave no ambiente."""
    from memory import config_manager as CM
    monkeypatch.setattr(CM, "CONFIG_DIR", tmp_path / "cfg_nexus")
    monkeypatch.setattr(CM, "CONFIG_FILE", tmp_path / "cfg_nexus" / "api_keys.json")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return CM


@pytest.fixture
def sdk_falso(monkeypatch):
    monkeypatch.setattr(FE, "anthropic", SimpleNamespace(Anthropic=lambda **kw: SimpleNamespace(**kw)))


def escreve_json(CM, dados):
    CM.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CM.CONFIG_FILE.write_text(json.dumps(dados), encoding="utf-8")


def test_a_chave_colada_nas_configuracoes_do_nexus_e_encontrada(config_nexus, tmp_path):
    # exatamente o que a tela de Configurações grava ao colar a chave no provedor Claude
    config_nexus.save_motor_config({"llm_keys": {"claude": "sk-ant-das-configuracoes"}})
    assert motor(tmp_path)._chave_e_origem() == ("sk-ant-das-configuracoes", "Configurações do NEXUS (provedor Claude)")


def test_a_chave_anthropic_api_key_do_json_tambem_funciona(config_nexus, tmp_path):
    escreve_json(config_nexus, {"gemini_api_key": "g", "anthropic_api_key": "sk-ant-do-json"})
    assert motor(tmp_path)._chave_e_origem() == ("sk-ant-do-json", "anthropic_api_key em config/api_keys.json")


def test_ordem_das_chaves_nexus_depois_json_depois_ambiente(config_nexus, tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-do-ambiente")
    m = motor(tmp_path)
    assert m._chave() == "sk-ant-do-ambiente"                                  # só o ambiente
    escreve_json(config_nexus, {"anthropic_api_key": "sk-ant-do-json"})
    assert m._chave() == "sk-ant-do-json"                                      # o json vence o ambiente
    escreve_json(config_nexus, {"anthropic_api_key": "sk-ant-do-json", "llm_keys": {"claude": "sk-ant-da-tela"}})
    assert m._chave() == "sk-ant-da-tela"                                      # a tela vence tudo


def test_so_a_chave_do_gemini_nao_conta(config_nexus, tmp_path):
    escreve_json(config_nexus, {"gemini_api_key": "AIza-so-gemini", "llm_keys": {"gemini": "AIza-so-gemini"}})
    assert motor(tmp_path)._chave_e_origem() == ("", "")


def test_sem_chave_o_forge_diz_onde_colar(config_nexus, sdk_falso):
    r = FA.forge_app({"action": "plan", "description": "app de tarefas"})
    assert r.startswith("[failed]")
    assert "Chave do provedor" in r and "Gemini não serve" in r and "dev_agent" in r
    assert "Confira a chave da API" not in r          # a frase genérica de antes escondia tudo isso


def test_sem_o_pacote_anthropic_o_forge_diz_o_que_instalar(config_nexus, monkeypatch):
    monkeypatch.setattr(FE, "anthropic", None)
    r = FA.forge_app({"action": "plan", "description": "app de tarefas"})
    assert "pip install anthropic" in r


def erro(nome, texto):
    return type(nome, (Exception,), {})(texto)


@pytest.mark.parametrize("e,trecho", [
    (erro("AuthenticationError", "Error code: 401 - {'message': 'invalid x-api-key'}"), "recusou a chave"),
    (erro("PermissionDeniedError", "Error code: 403"), "recusou a chave"),
    (erro("BadRequestError", "Error code: 400 - Your credit balance is too low to access the Anthropic API."), "sem crédito"),
    (erro("RateLimitError", "Error code: 429"), "limite de uso"),
    (erro("APIConnectionError", "Connection error."), "falar com a Anthropic"),
    (erro("InternalServerError", "Error code: 529 - overloaded_error"), "sobrecarregada"),
    (erro("NotFoundError", "model: claude-x not found"), "modelo"),
])
def test_erros_da_anthropic_viram_frases_que_dizem_o_que_fazer(e, trecho):
    assert trecho in FE.NexusForge._msg_erro(e)


def test_erro_desconhecido_vai_resumido_e_sem_quebra_de_linha():
    r = FE.NexusForge._msg_erro(RuntimeError("linha um\n" + "x" * 500))
    assert len(r) <= 160 and "\n" not in r


def test_acao_check_chave_valida(config_nexus, sdk_falso, monkeypatch):
    config_nexus.save_motor_config({"llm_keys": {"claude": "sk-ant-segredo-123"}})
    visto = {}

    class Resposta:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def falso_urlopen(req, timeout=0):
        visto["chave_enviada"] = req.get_header("X-api-key")
        return Resposta()

    monkeypatch.setattr("urllib.request.urlopen", falso_urlopen)
    r = FA.forge_app({"action": "check"})
    assert r.startswith("[done]") and "Configurações do NEXUS" in r
    assert visto["chave_enviada"] == "sk-ant-segredo-123"
    assert "sk-ant-segredo-123" not in r              # a chave nunca aparece no que o Nexus fala


def test_acao_check_chave_recusada_e_sem_chave(config_nexus, sdk_falso, monkeypatch):
    import urllib.error
    r = FA.forge_app({"action": "check"})                                  # ainda sem chave
    assert r.startswith("[failed]") and "Chave do provedor" in r

    config_nexus.save_motor_config({"llm_keys": {"claude": "sk-ant-velha"}})

    def recusa(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", recusa)
    r = FA.forge_app({"action": "check"})
    assert r.startswith("[failed]") and "recusou a chave" in r and "sk-ant-velha" not in r


def test_acao_check_sem_internet(config_nexus, sdk_falso, monkeypatch):
    config_nexus.save_motor_config({"llm_keys": {"claude": "sk-ant-x"}})

    def cai(req, timeout=0):
        raise OSError("sem rede")

    monkeypatch.setattr("urllib.request.urlopen", cai)
    assert "falar com a Anthropic" in FA.forge_app({"action": "check"})


def test_falha_de_chave_no_meio_da_construcao_vira_frase_falada(config_nexus, sdk_falso, tmp_path):
    """Sem chave, o aviso falado no fim do trabalho em segundo plano diz o que fazer (não um erro cru)."""
    falas = []
    m = motor(tmp_path, falas=falas)
    m._pendente = ({"titulo": "x", "arquivos": [], "comando_teste": ""}, "x")
    m.construir_pendente()
    assert any("Chave do provedor" in f for f in falas)
