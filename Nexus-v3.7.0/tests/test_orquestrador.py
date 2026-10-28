"""2.5 — roteador de modelos (core/roteador_modelos.py), orquestrador de agentes
(actions/orquestrador.py) e as intenções de brilho da rede local."""
import importlib
import threading
import time
import types
from pathlib import Path

import pytest

from core import roteador_modelos as RM

AT = importlib.import_module("actions.agent_task")
ORQ = importlib.import_module("actions.orquestrador")


# ── roteador de modelos ──────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def rot(tmp_path_factory):
    r = RM.Roteador(arquivo=tmp_path_factory.mktemp("rm") / "ex.json")
    r.treinar()
    return r


# frases que NÃO estão nos modelos de treino: mede se ela generaliza, não se decorou
@pytest.mark.parametrize("texto,esperado", [
    ("liga o timer de dez minutos", "rapido"),
    ("pausa essa música", "rapido"),
    ("bom dia, como vai você", "rapido"),
    ("abre o navegador", "rapido"),
    ("me explica como funciona a bolsa de valores", "forte"),
    ("escreve uma função em javascript que remove duplicados de um array", "forte"),
    ("por que meu programa trava quando eu clico no botão", "forte"),
    ("faz uma análise dos prós e contras de morar sozinho", "forte"),
    ("pesquisa os melhores hotéis em Gramado, compara os preços e salva uma tabela", "delegar"),
    ("procura reviews de cadeiras gamer, resume cada uma e escreve um relatório no meu computador", "delegar"),
    ("research the best running shoes, compare them and write the result to a file", "delegar"),
])
def test_roteador_generaliza(rot, texto, esperado):
    assert rot.decidir(texto).rota == esperado


def test_roteador_regras_de_seguranca(rot):
    assert rot.decidir("[AGENT_DONE] terminou").rota == "rapido"          # mensagem do app
    assert rot.decidir("").rota == "rapido"
    # delegar exige frase com corpo: 3 palavras nunca viram equipe de agentes
    assert rot.decidir("pesquisa e salva").rota != "delegar"
    assert rot.decidir("revisa isso\n```python\nprint(1)\n```\ne acha o bug").rota == "forte"
    assert rot.decidir("x").tier in ("fast", "smart")


def test_roteador_aprende_com_o_uso(tmp_path):
    r = RM.Roteador(arquivo=tmp_path / "ex.json")
    r.treinar()
    frase = "calcula a melhor entrada para um financiamento"
    antes = r.probabilidades(frase)
    for _ in range(RM.RETREINAR_A_CADA):
        r.aprender(frase, "forte")
    t0 = time.time()
    while time.time() - t0 < 10 and r.estatisticas()["ensinados"]["forte"] < 1:
        time.sleep(0.05)
    r.treinar()                                    # o retreino em segundo plano também ocorre; aqui, determinístico
    depois = r.probabilidades(frase)
    assert depois[1] > antes[1] and r.decidir(frase).rota == "forte"
    assert (tmp_path / "ex.json").exists()
    r.esquecer()
    assert r.estatisticas()["aprendidos"] == 0


def test_cerebro_para_claude_e_configurado():
    from core import llm_providers as L
    base = L.CerebroLLM.__new__(L.CerebroLLM)
    base.__dict__.update(provedor="claude", modelo="claude-sonnet-5-5", _variantes=None)
    del base.__dict__["_variantes"]
    assert RM.cerebro_para(base, {}, "forte") is base                      # já é o Sonnet
    assert RM.cerebro_para(base, {}, "delegar") is base
    rap = RM.cerebro_para(base, {}, "rapido")
    assert rap is not base and rap.modelo == "claude-haiku-5-5"
    assert RM.cerebro_para(base, {}, "rapido") is rap                       # reaproveita
    assert base.modelo == "claude-sonnet-5-5"                              # o original não mudou
    outro = L.CerebroLLM.__new__(L.CerebroLLM)
    outro.__dict__.update(provedor="groq", modelo="m-grande")
    assert RM.cerebro_para(outro, {}, "rapido") is outro                   # sem config, outros provedores não mudam
    assert RM.cerebro_para(outro, {"llm_model_rapido": "m-pequeno"}, "rapido").modelo == "m-pequeno"


# ── orquestrador ─────────────────────────────────────────────────────────────
class _Reg:
    def __init__(self):
        self.chamadas, self.trava = [], threading.Lock()
        self.decls = [{"name": n, "description": n, "parameters": {"properties": {"q": {"description": "x"}}}}
                      for n in ("web_search", "file_controller", "file_processor", "orchestrate",
                                "send_message", "code_helper", "weather_report")]

    def get_tool_declarations(self):
        return self.decls

    def has(self, n):
        return any(d["name"] == n for d in self.decls)

    def run(self, n, args, ctx=None):
        time.sleep(0.15)
        with self.trava:
            self.chamadas.append((n, dict(args), time.monotonic()))
        return f"resultado de {n}: {args.get('q', '')}"


@pytest.fixture
def equipe(monkeypatch, tmp_path):
    reg = _Reg()
    monkeypatch.setattr(AT, "_registry", reg)
    monkeypatch.setattr(ORQ, "_registry", None)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(ORQ, "_aprender", lambda *a: None)
    monkeypatch.setattr(ORQ, "_tier_do_passo", lambda t: "smart")
    return reg


def _roteiro(monkeypatch, plano, passos, sintese="Pronto: a equipe terminou."):
    """passos: {agente: [decisões em ordem]}; o prompt diz qual agente está pedindo."""
    vistos = {}

    def _json(prompt, tier):
        if "split a user's GOAL" in prompt:
            return plano
        for ag in passos:
            if f"You are the {ag.upper()} agent" in prompt:
                chave = (ag, prompt.split("YOUR SUBTASK:")[1].split("\n")[0])
                i = vistos.get(chave, 0)
                vistos[chave] = i + 1
                lista = passos[ag]
                return lista[min(i, len(lista) - 1)]
        return None
    monkeypatch.setattr(ORQ, "_llm_json", _json)
    monkeypatch.setattr(ORQ, "_llm_texto", lambda p, t: sintese)


def test_validar_plano():
    ok = {"subtarefas": [{"id": "a", "agente": "pesquisador", "tarefa": "x", "depende_de": []},
                         {"id": "b", "agente": "escritor", "tarefa": "y", "depende_de": ["a"]}]}
    assert [s["id"] for s in ORQ._validar_plano(ok)] == ["a", "b"]
    assert ORQ._validar_plano(None) is None
    assert ORQ._validar_plano({"subtarefas": []}) is None
    ruim = [
        {"subtarefas": [{"id": "a", "agente": "hacker", "tarefa": "x", "depende_de": []}]},          # agente inexistente
        {"subtarefas": [{"id": "a", "agente": "escritor", "tarefa": "x", "depende_de": ["z"]}]},     # dependência fantasma
        {"subtarefas": [{"id": "a", "agente": "escritor", "tarefa": "x", "depende_de": ["a"]}]},     # depende de si
        {"subtarefas": [{"id": "a", "agente": "escritor", "tarefa": "x", "depende_de": ["b"]},
                        {"id": "b", "agente": "escritor", "tarefa": "y", "depende_de": ["a"]}]},     # ciclo
        {"subtarefas": [{"id": "a", "agente": "escritor", "tarefa": "x", "depende_de": []},
                        {"id": "a", "agente": "escritor", "tarefa": "y", "depende_de": []}]},        # id repetido
    ]
    for p in ruim:
        assert ORQ._validar_plano(p) is None


def test_orquestra_em_paralelo_e_junta(equipe, monkeypatch):
    plano = {"sintese": "junta tudo", "subtarefas": [
        {"id": "s1", "agente": "pesquisador", "tarefa": "pesquisar notebooks", "depende_de": []},
        {"id": "s2", "agente": "pesquisador", "tarefa": "pesquisar monitores", "depende_de": []},
        {"id": "s3", "agente": "escritor", "tarefa": "escrever o relatório", "depende_de": ["s1", "s2"]}]}
    passos = {"pesquisador": [{"tool": "web_search", "args": {"q": "melhores"}, "why": "buscar"},
                              {"done": True, "report": "achei três opções"}],
              "escritor": [{"done": True, "report": "relatório escrito"}]}
    _roteiro(monkeypatch, plano, passos)
    falas = []
    t0 = time.monotonic()
    r = ORQ.orquestrar("pesquisa e escreve", speak=falas.append)
    assert r["final"] == "Pronto: a equipe terminou."
    assert [x["id"] for x in r["resultados"]] == ["s1", "s2", "s3"]
    buscas = [c for c in equipe.chamadas if c[0] == "web_search"]
    assert len(buscas) == 2
    assert abs(buscas[0][2] - buscas[1][2]) < 0.14                  # as duas pesquisas começaram juntas
    assert r["arquivo"] and Path(r["arquivo"]).exists()
    assert "AGENT_DONE" in falas[0] and "Pronto" in falas[0]
    assert time.monotonic() - t0 < 5


def test_o_agente_so_usa_as_ferramentas_do_seu_oficio(equipe, monkeypatch):
    plano = {"subtarefas": [{"id": "s1", "agente": "pesquisador", "tarefa": "tentar abusar", "depende_de": []}]}
    passos = {"pesquisador": [
        {"tool": "send_message", "args": {"q": "oi"}, "why": "mandar"},          # fora do ofício e proibida
        {"tool": "file_controller", "args": {"action": "delete"}, "why": "apagar"},  # fora do ofício
        {"tool": "orchestrate", "args": {"goal": "recursão"}, "why": "recursão"},    # nunca
        {"done": True, "report": "não consegui"}]}
    _roteiro(monkeypatch, plano, passos)
    r = ORQ.orquestrar("x")
    assert equipe.chamadas == []                                    # nada foi executado
    assert [h["status"] for h in r["resultados"][0]["passos"]] == ["failed"] * 3


def test_respeita_as_proibicoes_do_agent_task(equipe, monkeypatch):
    plano = {"subtarefas": [{"id": "s1", "agente": "arquivista", "tarefa": "apagar", "depende_de": []}]}
    passos = {"arquivista": [{"tool": "file_controller", "args": {"action": "delete", "q": "x"}, "why": "apagar"},
                             {"tool": "file_controller", "args": {"action": "read", "q": "a.txt"}, "why": "ler"},
                             {"done": True, "report": "li o arquivo"}]}
    _roteiro(monkeypatch, plano, passos)
    r = ORQ.orquestrar("x")
    assert [c[1].get("action") for c in equipe.chamadas] == ["read"]    # delete nunca chegou à ferramenta
    assert r["resultados"][0]["resultado"] == "li o arquivo"


def test_plano_invalido_cai_para_um_agente(equipe, monkeypatch):
    _roteiro(monkeypatch, {"lixo": 1}, {"pesquisador": [{"done": True, "report": "feito sozinho"}]})
    r = ORQ.orquestrar("faz isso")
    assert len(r["resultados"]) == 1 and r["resultados"][0]["resultado"] == "feito sozinho"


def test_rapido_que_falha_sobe_para_o_forte_e_a_rede_aprende(equipe, monkeypatch):
    aprendeu, tiers = [], []
    monkeypatch.setattr(ORQ, "_tier_do_passo", lambda t: "fast")
    monkeypatch.setattr(ORQ, "_aprender", lambda t, r: aprendeu.append((t, r)))
    plano = {"subtarefas": [{"id": "s1", "agente": "pesquisador", "tarefa": "achar algo difícil", "depende_de": []}]}

    def _json(prompt, tier):
        if "split a user's GOAL" in prompt:
            return plano
        tiers.append(tier)
        return None if tier == "fast" else {"done": True, "report": "o forte resolveu"}
    monkeypatch.setattr(ORQ, "_llm_json", _json)
    monkeypatch.setattr(ORQ, "_llm_texto", lambda p, t: "ok")
    r = ORQ.orquestrar("x")
    assert tiers == ["fast", "smart"] and r["resultados"][0]["resultado"] == "o forte resolveu"
    assert aprendeu == [("achar algo difícil", "forte")]


def test_ferramenta_orchestrate(equipe, monkeypatch):
    assert ORQ.orchestrate({}).startswith("[failed]")
    plano = {"subtarefas": [{"id": "s1", "agente": "pesquisador", "tarefa": "algo", "depende_de": []}]}
    _roteiro(monkeypatch, plano, {"pesquisador": [{"done": True, "report": "ok"}]})
    falas, fim = [], threading.Event()
    msg = ORQ.orchestrate({"goal": "faz algo grande"}, speak=lambda m: (falas.append(m), fim.set()))
    assert msg.startswith("[done]")
    assert ORQ.orchestrate({"goal": "outro"}).startswith("[failed]")      # já tem uma equipe trabalhando
    assert fim.wait(10)
    time.sleep(0.2)
    assert not ORQ._ativo.locked()                                         # liberou para a próxima
    assert ORQ.TOOL["name"] == "orchestrate" and "orchestrate" in AT._PROIBIDAS


# ── rede local: brilho ───────────────────────────────────────────────────────
def test_intencoes_de_brilho_na_rede_local():
    from core import intent_net as I
    assert {"brightness_up", "brightness_down"} <= set(I.INTENTS)
    assert I.intent_from_tool("computer_settings", {"action": "brightness_up"}) == "brightness_up"
    assert I.intent_from_tool("computer_settings", {"action": "brightness_down"}) == "brightness_down"
    X, Y = I.build_dataset()
    assert {I.INTENTS[y] for y in Y} >= {"brightness_up", "brightness_down"}
    assert not [x for x, y in zip(X, Y) if I.INTENTS[y] == "none" and "aumenta o brilho" == x]
    # assistant/typed.py não importa aqui (puxa Qt/PortAudio): confere o mapa no texto do arquivo
    fonte = (Path(__file__).resolve().parent.parent / "assistant" / "typed.py").read_text(encoding="utf-8")
    assert '"brightness_up":    ("computer_settings", {"action": "brightness_up"})' in fonte
    assert '"brightness_down":  ("computer_settings", {"action": "brightness_down"})' in fonte
