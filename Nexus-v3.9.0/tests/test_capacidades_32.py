"""3.2 — equipe com revisor, auto-avaliação, memória semanal e conferência do modo agente."""
import importlib
import threading
import time
from datetime import datetime
from pathlib import Path

import pytest

from core import autoavaliacao as AV
from core import memoria_semanal as MS

AT = importlib.import_module("actions.agent_task")
ORQ = importlib.import_module("actions.orquestrador")


# ── auto-avaliação ───────────────────────────────────────────────────────────
def test_rapido_que_falha_ensina_forte(tmp_path):
    ensinados = []
    r = AV.registrar("calcula o imposto do meu carro", "rapido", ok=False, ms=900, arquivo=tmp_path / "a.json",
                     ensinar=lambda t, rota: ensinados.append((t, rota)) or True)
    assert r == "forte" and ensinados == [("calcula o imposto do meu carro", "forte")]
    assert AV.relatorio(tmp_path / "a.json")["ajustes_total"] == 1


def test_rapido_com_ferramenta_falha_tambem_ensina_forte(tmp_path):
    ens = []
    AV.registrar("abre o programa x", "rapido", ok=True, ms=500, ferramentas=1, falhas=1,
                 arquivo=tmp_path / "a.json", ensinar=lambda t, r: ens.append(r) or True)
    assert ens == ["forte"]


def test_rapido_que_deu_certo_nao_muda_nada(tmp_path):
    ens = []
    assert AV.registrar("liga o timer", "rapido", True, 300, arquivo=tmp_path / "a.json",
                        ensinar=lambda t, r: ens.append(r) or True) is None
    assert ens == []


def test_forte_lento_em_pedido_simples_so_rebaixa_na_segunda_vez(tmp_path):
    arq, ens = tmp_path / "a.json", []
    f = lambda t, r: ens.append(r) or True
    assert AV.registrar("bom dia", "forte", True, 12000, arquivo=arq, ensinar=f) is None   # 1ª vez: só anota
    assert AV.registrar("Bom dia!", "forte", True, 11000, arquivo=arq, ensinar=f) == "rapido"
    assert ens == ["rapido"]


def test_forte_lento_com_ferramenta_ou_texto_longo_nao_rebaixa(tmp_path):
    arq, ens = tmp_path / "a.json", []
    f = lambda t, r: ens.append(r) or True
    for _ in range(3):
        AV.registrar("pesquisa isso", "forte", True, 15000, ferramentas=1, arquivo=arq, ensinar=f)
        AV.registrar("explica em detalhes como funciona a bolsa de valores e seus riscos", "forte", True, 15000,
                     arquivo=arq, ensinar=f)
    assert ens == []


def test_mensagens_do_app_e_rota_desconhecida_nao_contam(tmp_path):
    arq = tmp_path / "a.json"
    assert AV.registrar("[AGENT_DONE] terminou", "rapido", False, 10, arquivo=arq) is None
    assert AV.registrar("oi", "outra", False, 10, arquivo=arq) is None
    assert AV.relatorio(arq)["total"] == 0


def test_relatorio_e_resumo(tmp_path):
    arq = tmp_path / "a.json"
    for ms in (1000, 2000, 3000, 4000):
        AV.registrar("diz oi", "rapido", True, ms, arquivo=arq, ensinar=lambda *a: True)
    AV.registrar("explica a bolsa", "forte", False, 5000, arquivo=arq, ensinar=lambda *a: True)
    r = AV.relatorio(arq)
    assert r["rotas"]["rapido"]["pedidos"] == 4 and r["rotas"]["rapido"]["mediana_ms"] in (2000, 3000)
    assert r["rotas"]["forte"]["erros"] == 1
    txt = AV.resumo_texto(arq)
    assert "modelo rápido" in txt and "modelo forte" in txt
    AV.esquecer(arq)
    assert AV.relatorio(arq)["total"] == 0 and "Ainda não" in AV.resumo_texto(arq)


def test_turno_fecha_uma_vez_so(tmp_path, monkeypatch):
    monkeypatch.setattr(AV, "ARQUIVO", tmp_path / "t.json")
    monkeypatch.setattr(AV, "_ensinar", lambda *a: True)
    t = AV.Turno("diz oi", "rapido")
    t.ferramenta(falhou=False)
    t.fechar(True)
    t.fechar(False)
    assert AV.relatorio()["total"] == 1
    assert AV.Turno("sem rota", None).fechar(True) is None


# ── memória semanal ──────────────────────────────────────────────────────────
def _ts(ano, mes, dia, hora, minuto=0):
    return datetime(ano, mes, dia, hora, minuto).timestamp()


# terça-feira, 20/10/2026
TERCAS = [_ts(2026, 10, d, 9, 10) for d in (6, 13, 20)]


def test_resume_a_semana_com_horario_tipico():
    agora = _ts(2026, 10, 25, 12)                              # domingo
    ev = [{"t": _ts(2026, 10, d, 9, 5), "sig": "music_control:play", "tool": "music_control"} for d in (20, 21, 22)]
    ev += [{"t": _ts(2026, 10, 20, 15), "sig": "weather_report", "tool": "weather_report"}]
    ped = [{"t": _ts(2026, 10, 21, 10), "texto": "abre o spotify"}, {"t": _ts(2026, 10, 22, 10), "texto": "Abre o Spotify!"}]
    r = MS.resumir(agora, ev, ped)
    assert r["acoes"] == 4 and r["habitos"][0]["sig"] == "music_control:play"
    assert r["habitos"][0]["vezes"] == 3 and r["habitos"][0]["hora_tipica"] == 9
    assert r["pedidos_repetidos"][0]["vezes"] == 2
    assert "música" in r["texto"] and "rotina" in r["texto"]


def test_semana_sem_dados_e_honesta():
    r = MS.resumir(_ts(2026, 10, 25, 12), [], [])
    assert "ainda não vi o suficiente" in r["texto"]


def test_so_guarda_um_resumo_por_semana(tmp_path):
    arq, agora = tmp_path / "s.json", _ts(2026, 10, 25, 12)
    assert MS.garantir_semana(agora, arq, [], []) is not None
    assert MS.garantir_semana(agora + 3600, arq, [], []) is None
    assert MS.garantir_semana(agora + 8 * 86400, arq, [], []) is not None
    assert len(MS._carregar(arq)["semanas"]) == 2
    MS.esquecer(arq)
    assert MS.ultimo(arq) is None


def test_antecipa_habito_firme_do_mesmo_dia_da_semana():
    ev = [{"t": t, "sig": "open_app:spotify", "tool": "open_app"} for t in TERCAS]
    agora = _ts(2026, 10, 27, 9, 30)                           # a terça seguinte
    c = MS.antecipar(agora, ev)
    assert c and c[0]["sig"] == "open_app:spotify" and c[0]["dias"] == 3
    txt = MS.sugestao_texto(agora, ev)
    assert "terça" in txt and "abrir spotify" in txt and "Quer que eu" in txt


def test_nao_antecipa_em_outro_dia_nem_com_poucos_dias():
    ev = [{"t": t, "sig": "open_app:spotify", "tool": "open_app"} for t in TERCAS]
    assert MS.antecipar(_ts(2026, 10, 28, 9, 30), ev) == []    # quarta
    assert MS.antecipar(_ts(2026, 10, 27, 15, 0), ev) == []    # tarde
    assert MS.antecipar(_ts(2026, 10, 27, 9, 30), ev[:2]) == []   # só 2 dias
    assert MS.sugestao_texto(_ts(2026, 10, 27, 9, 30), []) == ""


def test_ferramentas_de_voz(tmp_path, monkeypatch):
    monkeypatch.setattr(MS, "ARQUIVO", tmp_path / "s.json")
    from actions.memoria_semanal import TOOL, memoria_semanal
    assert TOOL["name"] == "memoria_semanal"
    assert memoria_semanal({"action": "summary"})
    assert "hábito" in memoria_semanal({"action": "anticipate"}) or "Hoje é" in memoria_semanal({"action": "anticipate"})
    assert "Apaguei" in memoria_semanal({"action": "forget"})
    from actions.explicar_ia import explicar_ia
    assert explicar_ia({"action": "self"})


def test_prompt_proativo_usa_a_antecipacao():
    from actions.proactive import ProactiveEngine as ProactiveMode
    p = ProactiveMode.__new__(ProactiveMode)
    p._rotation = 0
    txt = p.build_prompt(memory={}, antecipacao="Hoje é terça de manhã e você costuma abrir o spotify.")
    assert "pattern" in txt and "spotify" in txt and "Do not do it" in txt
    com_followup = p.build_prompt(memory={}, followup="o relatório", antecipacao="x costuma y")
    assert "the middle of" in com_followup


# ── equipe com revisor ───────────────────────────────────────────────────────
class _Reg:
    def __init__(self):
        self.chamadas = []
        self.decls = [{"name": n, "description": n, "parameters": {"properties": {"q": {"description": "x"}}}}
                      for n in ("web_search", "file_controller", "file_processor", "memoria_semantica")]

    def get_tool_declarations(self):
        return self.decls

    def has(self, n):
        return any(d["name"] == n for d in self.decls)

    def run(self, n, args, ctx=None):
        self.chamadas.append((n, dict(args)))
        return f"resultado de {n}"


@pytest.fixture
def equipe(monkeypatch, tmp_path):
    reg = _Reg()
    monkeypatch.setattr(AT, "_registry", reg)
    monkeypatch.setattr(ORQ, "_registry", None)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(ORQ, "_aprender", lambda *a: None)
    monkeypatch.setattr(ORQ, "_tier_do_passo", lambda t: "smart")
    return reg


def _roteiro(monkeypatch, plano, passos, revisoes):
    """`revisoes`: respostas do revisor, em ordem (a última se repete)."""
    vistos, nrev = {}, [0]

    def _json(prompt, tier):
        if "split a user's GOAL" in prompt:
            return plano
        if "independent REVIEWER" in prompt:
            i = min(nrev[0], len(revisoes) - 1)
            nrev[0] += 1
            return revisoes[i]
        for ag in passos:
            if f"You are the {ag.upper()} agent" in prompt:
                chave = (ag, prompt.split("YOUR SUBTASK:")[1].split("\n")[0])
                i = vistos.get(chave, 0)
                vistos[chave] = i + 1
                lista = passos[ag]
                return lista[min(i, len(lista) - 1)]
        return None
    monkeypatch.setattr(ORQ, "_llm_json", _json)
    monkeypatch.setattr(ORQ, "_llm_texto", lambda p, t: "Pronto.")
    return nrev


PLANO = {"sintese": "junta", "subtarefas": [
    {"id": "s1", "agente": "pesquisador", "tarefa": "pesquisar notebooks", "depende_de": []},
    {"id": "s2", "agente": "escritor", "tarefa": "escrever o relatório", "depende_de": ["s1"]}]}


def test_revisor_manda_refazer_e_o_agente_refaz(equipe, monkeypatch):
    passos = {"pesquisador": [{"done": True, "report": "achei um notebook, sem fonte"},
                              {"tool": "web_search", "args": {"q": "fonte"}, "why": "achar a fonte"},
                              {"done": True, "report": "três notebooks, com fontes"}],
              "escritor": [{"done": True, "report": "relatório escrito"}]}
    nrev = _roteiro(monkeypatch, PLANO, passos,
                    [{"aprovado": False, "problemas": [{"id": "s1", "motivo": "sem fontes e só um item"}]}])
    r = ORQ.orquestrar("pesquisa notebooks e escreve")
    s1 = next(x for x in r["resultados"] if x["id"] == "s1")
    assert s1["resultado"] == "três notebooks, com fontes" and s1.get("refeito") is True
    assert r["revisao"] == [{"id": "s1", "motivo": "sem fontes e só um item", "refeito": True}]
    assert nrev[0] == 1                                                    # revisou UMA vez só
    assert equipe.chamadas == [("web_search", {"q": "fonte"})]
    assert "Revisão" in Path(r["arquivo"]).read_text(encoding="utf-8")


def test_revisor_aprova_e_nada_e_refeito(equipe, monkeypatch):
    passos = {"pesquisador": [{"done": True, "report": "ok"}], "escritor": [{"done": True, "report": "ok"}]}
    _roteiro(monkeypatch, PLANO, passos, [{"aprovado": True, "problemas": []}])
    r = ORQ.orquestrar("x")
    assert r["revisao"] == [] and not any(x.get("refeito") for x in r["resultados"])


def test_revisao_com_resposta_ruim_ou_id_inexistente_nunca_trava(equipe, monkeypatch):
    passos = {"pesquisador": [{"done": True, "report": "ok"}], "escritor": [{"done": True, "report": "ok"}]}
    for resposta in (None, "texto solto", {"aprovado": False, "problemas": [{"id": "zzz", "motivo": "x"}]},
                     {"aprovado": False, "problemas": "quebrado"}):
        _roteiro(monkeypatch, PLANO, passos, [resposta])
        r = ORQ.orquestrar("x")
        assert r["revisao"] == [] and r["final"] == "Pronto."


def test_sem_tempo_pula_a_revisao(equipe, monkeypatch):
    passos = {"pesquisador": [{"done": True, "report": "ok"}], "escritor": [{"done": True, "report": "ok"}]}
    nrev = _roteiro(monkeypatch, PLANO, passos, [{"aprovado": False, "problemas": [{"id": "s1", "motivo": "x"}]}])
    monkeypatch.setattr(ORQ, "MIN_PRAZO_REVISAO_S", 10_000)
    r = ORQ.orquestrar("x")
    assert nrev[0] == 0 and r["revisao"] == []


def test_equipe_maior_e_com_revisor():
    assert ORQ.MAX_SUBTAREFAS == 8 and ORQ.MAX_PARALELO == 4
    assert "revisor" in ORQ.AGENTES
    plano = {"subtarefas": [{"id": "a", "agente": "pesquisador", "tarefa": "x", "depende_de": []},
                            {"id": "b", "agente": "revisor", "tarefa": "y", "depende_de": ["a"]}]}
    assert [s["agente"] for s in ORQ._validar_plano(plano)] == ["pesquisador", "revisor"]


# ── conferência no modo agente ───────────────────────────────────────────────
def _agente(monkeypatch, decisoes, conferencias):
    reg = _Reg()
    monkeypatch.setattr(AT, "_registry", reg)
    it, conf = iter(decisoes), iter(conferencias)
    monkeypatch.setattr(AT, "_proximo_passo", lambda o, h: next(it))
    monkeypatch.setattr(AT, "_conferir", lambda o, h, r: next(conf))
    monkeypatch.setattr(AT, "_relatorio", lambda *a: "")
    falas = []
    AT._trabalhar("salva o resultado", falas.append, None)
    return reg, falas


def test_agente_confere_e_tenta_de_novo(monkeypatch):
    reg, falas = _agente(monkeypatch,
        [{"tool": "web_search", "args": {"q": "a"}}, {"done": True, "report": "salvei"},
         {"tool": "file_controller", "args": {"action": "write"}}, {"done": True, "report": "salvei de verdade"}],
        ["nenhum arquivo foi salvo", ""])
    assert [c[0] for c in reg.chamadas] == ["web_search", "file_controller"]
    assert "salvei de verdade" in falas[0]


def test_agente_so_confere_uma_vez(monkeypatch):
    n = [0]
    reg = _Reg()
    monkeypatch.setattr(AT, "_registry", reg)
    monkeypatch.setattr(AT, "_proximo_passo", lambda o, h: {"tool": "web_search", "args": {"q": "a"}} if not h
                        else {"done": True, "report": f"fim {len(h)}"})
    def conferir(o, h, r):
        n[0] += 1
        return "ainda falta"
    monkeypatch.setattr(AT, "_conferir", conferir)
    monkeypatch.setattr(AT, "_relatorio", lambda *a: "")
    falas = []
    AT._trabalhar("x", falas.append, None)
    assert n[0] == 1 and "fim" in falas[0]


def test_conferir_sem_modelo_da_por_cumprido(monkeypatch):
    from core import gemini
    monkeypatch.setattr(gemini, "as_json", lambda *a, **k: None)
    assert AT._conferir("x", [{"tool": "t", "status": "done", "result": "r"}], "ok") == ""
    monkeypatch.setattr(gemini, "as_json", lambda *a, **k: {"cumprido": False, "falta": "salvar"})
    assert AT._conferir("x", [{"tool": "t", "status": "done", "result": "r"}], "ok") == "salvar"
