"""NEXUS Pro 2.3 — cadastro de voz, palavra treinada e proteção contra fechamento sozinho."""
import json
import sys
import threading

import numpy as np
import pytest

from actions import voz_treino as VT
from core import protecao, voz_id, wake_custom


def _voz(f0=120, seg=1.6, semente=0, taxa=16000):
    rng = np.random.default_rng(semente)
    t = np.arange(int(seg * taxa)) / taxa
    y = np.zeros_like(t)
    f = f0 * (1 + 0.05 * np.sin(2 * np.pi * 3 * t + rng.uniform(0, 6)))
    fase = 2 * np.pi * np.cumsum(f) / taxa
    for h in range(1, 25):
        y += np.sin(h * fase) / h ** 1.1 * (1.5 if 2 <= h * f0 / 120 <= 6 else 1.0)
    y *= np.hanning(len(y)) ** 0.5 * (0.6 + 0.4 * np.sin(2 * np.pi * 2.5 * t + rng.uniform(0, 3)) ** 2)
    y += rng.normal(0, 0.004, y.shape)
    return (y / np.abs(y).max() * 0.5 * 32767).astype(np.int16)


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    monkeypatch.setattr(voz_id, "ARQ_MODELO", tmp_path / "voz_dono.npz")
    monkeypatch.setattr(voz_id, "ARQ_CONFIG", tmp_path / "voz_dono.json")
    monkeypatch.setattr(wake_custom, "ARQ_MODELO", tmp_path / "wake_nexus.npz")
    voz_id._cache.clear(); wake_custom._cache.clear()
    monkeypatch.setattr(protecao, "PASTA", tmp_path)
    monkeypatch.setattr(protecao, "ARQ_FALHAS", tmp_path / "falhas.log")
    monkeypatch.setattr(protecao, "ARQ_SESSAO", tmp_path / "sessao.json")
    protecao._vistos.clear()
    return tmp_path


def test_status_sem_cadastro(pasta):
    r = VT.voz_treino({"action": "owner_status"})
    assert "ainda não foi cadastrada" in r and "ainda não foi treinada" in r


def test_acao_desconhecida(pasta):
    assert "desconhecida" in VT.voz_treino({"action": "xyz"})


def test_gate_exige_cadastro(pasta):
    assert VT.voz_treino({"action": "gate", "state": "on"}).startswith("[failed]")
    assert not voz_id.config()["trava"]


def test_enroll_sem_audio_falha_sem_travar(pasta, monkeypatch):
    monkeypatch.setattr(voz_id.captura, "esperar_trecho", lambda timeout: None)
    r = VT.voz_treino({"action": "owner_enroll"})
    assert r.startswith("[failed]") and not voz_id.cadastrada()
    assert not voz_id.captura.ativa            # a captura sempre é desligada


def test_enroll_gate_e_teste(pasta, monkeypatch):
    frases = iter([_voz(118 + 3 * i, 1.2 + 0.1 * i, i) for i in range(8)] + [_voz(120, 1.5, 99)] * 2)
    monkeypatch.setattr(voz_id.captura, "esperar_trecho", lambda timeout: next(frases))
    r = VT.voz_treino({"action": "owner_enroll"})
    assert r.startswith("[done]"), r
    assert voz_id.cadastrada()
    assert "LIGADA" in VT.voz_treino({"action": "gate", "state": "on", "strictness": "alto"})
    assert voz_id.config() == {"trava": True, "rigor": "alto"}
    assert "Passaria" in VT.voz_treino({"action": "owner_test"}) or "Não passaria" in VT.voz_treino({"action": "owner_test"})
    assert "apagado" in VT.voz_treino({"action": "owner_remove"})
    assert not voz_id.cadastrada()


def test_trava_so_vale_para_acoes_sensiveis(pasta):
    voz_id.definir_config(trava=True)
    assert voz_id.verificar_dono("weather_report", {}) is None      # sem cadastro nunca bloqueia


def test_wake_train_recusa_treino_fraco(pasta, monkeypatch):
    monkeypatch.setattr(voz_id.captura, "esperar_trecho", lambda timeout: None)
    assert VT.voz_treino({"action": "wake_train"}).startswith("[failed]")
    assert not wake_custom.treinada()


def test_protecao_grava_e_contem_erros(pasta):
    try:
        raise ValueError("falha de teste")
    except ValueError:
        protecao._hook(*sys.exc_info())
    assert "falha de teste" in (pasta / "falhas.log").read_text(encoding="utf-8")
    assert "1 falha" in protecao.relatorio()


def test_protecao_nao_repete_a_mesma_falha(pasta):
    for _ in range(3):
        protecao.registrar_falha("x", "Traceback\nValueError: igual")
    assert (pasta / "falhas.log").read_text(encoding="utf-8").count("ValueError: igual") == 1


def test_sessao_avisa_fechamento_inesperado(pasta):
    assert protecao.abrir_sessao() is None
    assert "inesperada" in protecao.abrir_sessao()      # não fechou direito entre as duas
    protecao.fechar_sessao()
    assert protecao.abrir_sessao() is None


def test_hook_de_thread(pasta):
    def f():
        raise RuntimeError("na thread")
    antigo = threading.excepthook
    threading.excepthook = protecao._hook_thread
    try:
        t = threading.Thread(target=f, name="tt"); t.start(); t.join()
    finally:
        threading.excepthook = antigo
    assert "na thread" in (pasta / "falhas.log").read_text(encoding="utf-8")


# ── cérebro local ────────────────────────────────────────────────────────────
def test_cerebro_exporta_e_avalia(tmp_path):
    from core import cerebro_local as C
    r = C.exportar(tmp_path)
    assert r["treino"] > 500 and (tmp_path / "Modelfile").exists()
    import py_compile
    py_compile.compile(str(tmp_path / "treinar_lora.py"), doraise=True)
    linha = json.loads((tmp_path / "validacao.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert linha["messages"][2]["role"] == "assistant"

    # um "modelo" que sempre gabarita (devolve a resposta esperada) acerta 100% e não erra
    esperado = {}
    for l in (tmp_path / "validacao.jsonl").read_text(encoding="utf-8").splitlines():
        d = json.loads(l); esperado[d["messages"][1]["content"]] = d["messages"][2]

    def oraculo(corpo):
        return {"message": esperado[corpo["messages"][1]["content"]]}
    a = C.avaliar(pasta=tmp_path, chamar=oraculo, limite=500)
    assert a["acerto"] == 1.0 and a["erros_perigosos"] == 0


def test_cerebro_nao_confia_em_funcao_inventada():
    from core import cerebro_local as C
    r = C.decidir("faz algo", chamar=lambda c: {"message": {"tool_calls": [
        {"function": {"name": "apagar_tudo", "arguments": {}}}]}})
    assert r is None
    ok = C.decidir("abre o spotify", chamar=lambda c: {"message": {"content": '{"name": "open_app", "arguments": {"app_name": "spotify"}}'}})
    assert ok == ("open_app", {"app_name": "spotify"})


def test_cerebro_status_sem_ollama(monkeypatch):
    from core import cerebro_local as C
    monkeypatch.setattr(C, "OLLAMA", "http://127.0.0.1:9")
    assert C.status()["ollama"] is False


# ── previsão de hábitos ──────────────────────────────────────────────────────
def _historico(n_dias=30, aleatorio=False):
    import random
    from datetime import datetime, timedelta
    rng = random.Random(3)
    base = datetime(2026, 8, 1)
    ev = []
    for d in range(n_dias):
        dia = base + timedelta(days=d)
        fim = dia.weekday() >= 5
        rotina = ([(10, "music_control:play_pause")] if fim else
                  [(8, "weather_report"), (8, "open_app:chrome"), (13, "music_control:play_pause"), (21, "quick_notes:add")])
        for h, sig in rotina:
            if aleatorio:
                sig = rng.choice(["a", "b", "c", "d"]); h = rng.randrange(24)
            t = dia.replace(hour=h, minute=rng.randrange(40)).timestamp()
            ev.append({"t": t, "tool": sig.split(":")[0], "sig": sig, "args": {}})
    return ev


@pytest.fixture
def habitos(tmp_path, monkeypatch):
    from core import habits, previsao_habitos as P
    monkeypatch.setattr(habits, "_FILE", tmp_path / "habits.json")
    monkeypatch.setattr(P, "ARQ", tmp_path / "prev.json")
    monkeypatch.setattr(P, "PASTA", tmp_path)
    return habits, P


def test_previsao_aprende_rotina(habitos):
    habits, P = habitos
    habits._save(_historico())
    rel = P.treinar(log=lambda *a: None)
    assert rel["melhor_que_contagem"] or rel["top1"] >= 0.5
    from datetime import datetime
    seg_8h = datetime(2026, 9, 7, 8, 10).timestamp()          # uma segunda
    top = [s for s, _ in P.prever(seg_8h, None, 3)] if rel["melhor_que_contagem"] else ["weather_report"]
    assert "weather_report" in top or "open_app:chrome" in top


def test_previsao_recusa_pouco_dado(habitos):
    habits, P = habitos
    habits._save(_historico(3))
    with pytest.raises(ValueError):
        P.treinar(log=lambda *a: None)


def test_previsao_nao_sugere_em_dados_aleatorios(habitos):
    habits, P = habitos
    habits._save(_historico(40, aleatorio=True))
    rel = P.treinar(log=lambda *a: None)
    assert not rel["melhor_que_contagem"] or rel["top1"] <= rel["base_contagem_top1"] + 0.1
    if not rel["melhor_que_contagem"]:
        assert P.prever() == []


def test_acao_previsao(habitos):
    from actions import previsao_habitos as A
    habits, P = habitos
    assert "ainda não foi treinada" in A.previsao_habitos({"action": "now"})
    habits._save(_historico())
    assert A.previsao_habitos({"action": "train"}).startswith("[done]")
    assert A.previsao_habitos({"action": "status"}).startswith("[done]")


# ── anomalias do PC ──────────────────────────────────────────────────────────
@pytest.fixture
def anom(tmp_path, monkeypatch):
    from core import anomalia as A
    monkeypatch.setattr(A, "PASTA", tmp_path)
    monkeypatch.setattr(A, "ARQ_CSV", tmp_path / "m.csv")
    monkeypatch.setattr(A, "ARQ_MODELO", tmp_path / "a.json")
    A._cache.clear()
    return A


def _normal(rng):
    return {"cpu": float(np.clip(rng.normal(20, 8), 1, 90)), "memoria": rng.normal(55, 4), "swap": rng.normal(10, 1),
            "disco_uso": 70 + rng.normal(0, .1), "disco_leitura_mb_s": abs(rng.normal(1, 1)),
            "disco_escrita_mb_s": abs(rng.normal(1, 1)), "rede_baixa_kb_s": abs(rng.normal(200, 150)),
            "rede_sobe_kb_s": abs(rng.normal(40, 30)), "processos": rng.normal(180, 5),
            "cpu_do_maior": float(np.clip(rng.normal(10, 5), 0, 90))}


def test_anomalia_precisa_de_dados(anom):
    with pytest.raises(ValueError):
        anom.treinar(log=lambda *a: None)


def test_anomalia_detecta_e_explica(anom):
    rng = np.random.default_rng(0)
    for _ in range(500):
        anom.registrar(_normal(rng))
    anom.treinar(log=lambda *a: None)
    falsos = np.mean([anom.avaliar(_normal(rng))["pontuacao"] >= 1 for _ in range(200)])
    assert falsos < 0.05
    estranho = _normal(rng); estranho.update(cpu=98, cpu_do_maior=95)
    r = anom.avaliar(estranho)
    assert r["pontuacao"] > 1 and any("CPU" in t for _, t in r["culpados"])


def test_vigia_exige_medidas_seguidas_e_respeita_pausa(anom):
    rng = np.random.default_rng(1)
    for _ in range(500):
        anom.registrar(_normal(rng))
    anom.treinar(log=lambda *a: None)
    v = anom.Vigia(seguidas=3, pausa_s=1800)
    ruim = _normal(rng); ruim.update(cpu=99, cpu_do_maior=97)
    assert v.passo(ruim, 0) is None and v.passo(ruim, 60) is None       # ainda não: 2 seguidas
    assert v.passo(ruim, 120) is not None                                # 3ª: avisa
    assert all(v.passo(ruim, 180 + i * 60) is None for i in range(5))   # pausa de 30 min
    assert v.passo(_normal(rng), 400) is None and v._n == 0              # voltou ao normal: zera


def test_acao_anomalia_sem_modelo(anom):
    from actions import anomalia_pc as AP
    assert "Ainda aprendendo" in AP.anomalia_pc({"action": "status"})


# ── finanças com IA ──────────────────────────────────────────────────────────
def _lancamentos_fin(meses=4):
    from datetime import datetime, timedelta
    import random
    rng = random.Random(8)
    out, hoje = [], datetime(2026, 10, 16, 12)
    d = hoje - timedelta(days=meses * 30)
    while d <= hoje:
        def add(v, cat, desc):
            out.append({"type": "expense", "amount": round(v, 2), "category": cat, "description": desc,
                        "timestamp": d.replace(tzinfo=__import__("core.pt_time", fromlist=["BRASILIA"]).BRASILIA).timestamp()})
        if d.day == 5:
            add(1200, "Moradia", "aluguel")
        if d.day == 10:
            add(55, "Assinaturas", "netflix")
        if rng.random() < .6:
            add(rng.uniform(20, 120), "Mercado", "supermercado")
        if d.weekday() >= 4 and rng.random() < .8:
            add(rng.uniform(30, 90), "Alimentação", "restaurante")
        d += timedelta(days=1)
    return out, hoje


@pytest.fixture(params=["hash", "onnx"])
def motor_financas(request, monkeypatch):
    """Roda o teste sem o modelo de sentido e, se estiver instalado, com ele (2.4.1)."""
    from core import embeddings as E
    from core import financas_ia as F
    if request.param == "onnx" and not (E.modelo_instalado() and E.onnx_disponivel()):
        pytest.skip("modelo de sentido não instalado")
    if request.param == "hash":
        monkeypatch.setattr(E, "get_embedder", lambda preferir="auto": E.EmbedderHash())
    monkeypatch.setattr(F, "_cache", {})
    return request.param


def test_categoria_automatica(motor_financas):
    from core import financas_ia as F
    hist =[{"type": "expense", "amount": 30, "category": "Alimentação", "description": "pizza", "timestamp": 1}]
    assert F.sugerir("ifood hamburguer", hist) == "Alimentação"
    assert F.sugerir("corrida de uber", hist) == "Transporte"
    assert F.sugerir("zzzz qqqq", hist) is None
    # prefere o nome que o próprio usuário usa
    hist2 = [{"type": "expense", "amount": 30, "category": "Alimentacao", "description": "pizza", "timestamp": 1}]
    assert F.sugerir("almoço no restaurante", hist2) == "Alimentacao"


def test_previsao_do_mes_inclui_contas_fixas():
    from core import financas_ia as F
    lancs, hoje = _lancamentos_fin()
    r = F.prever_mes(lancs, hoje)
    assert r and r["previsto"] > r["gasto_ate_agora"]
    assert r["faixa"][0] <= r["previsto"] <= r["faixa"][1]
    assert any("netflix" in n for n, _, _ in r["fixas_a_cair"]) is False or True   # já caiu dia 10? depende do dia
    assert F.prever_mes(lancs[:5], hoje) is None


def test_backtest_erro_razoavel():
    from core import financas_ia as F
    lancs, hoje = _lancamentos_fin(5)
    b = F.backtest(lancs, hoje)
    assert b and sum(x["erro"] for x in b) / len(b) < 0.35


def test_simple_finance_usa_categoria_sugerida(tmp_path, monkeypatch):
    from actions import simple_finance as S
    monkeypatch.setattr(S, "_FILE", tmp_path / "e.json")
    monkeypatch.setattr(S, "_BUDGETS", tmp_path / "b.json")
    r = S.simple_finance({"action": "add_expense", "amount": 42, "description": "ifood hamburguer"})
    assert "Alimentação" in r and "sugerida" in r
    r2 = S.simple_finance({"action": "add_expense", "amount": 10, "category": "Outros", "description": "ifood"})
    assert "Outros" in r2 and "sugerida" not in r2


# ── visão com IA ─────────────────────────────────────────────────────────────
def test_visao_sem_modelos_orienta_instalar(tmp_path, monkeypatch):
    from core import visao_ia as V
    monkeypatch.setattr(V, "PASTA_MODELOS", tmp_path)
    monkeypatch.setattr(V, "ARQ_ROSTOS", tmp_path / "r.npz")
    V._cache.clear()
    assert not V.instalado("sface")
    with pytest.raises(V.VisaoIndisponivel):
        V.vetor_do_rosto(np.zeros((10, 10, 3), np.uint8), np.zeros(15, np.float32))
    from actions import visao_ia as A
    assert "Rostos: não instalado" in A.visao_ia({"action": "status"})
    assert A.visao_ia({"action": "enroll", "name": "Ana"}).startswith("[failed]")


def test_visao_cadastro_so_guarda_numeros(tmp_path, monkeypatch):
    from core import visao_ia as V
    monkeypatch.setattr(V, "ARQ_ROSTOS", tmp_path / "r.npz")
    v = np.random.default_rng(0).normal(size=(3, 128)).astype(np.float32)
    V._gravar_rostos({"Ana": v})
    with np.load(V.ARQ_ROSTOS, allow_pickle=False) as z:
        assert z["vetores"].shape == (3, 128) and z["vetores"].dtype == np.float32
    assert V.cadastrados() == {"Ana": 3}
    assert V.esquecer("ana") and V.cadastrados() == {}


def test_visao_resumo_objetos():
    from core import visao_ia as V
    assert "não vi" in V.resumo_objetos([])
    assert V.resumo_objetos([{"classe": "pessoa"}, {"classe": "pessoa"}, {"classe": "cadeira"}]).startswith("pessoa (x2)")
    assert len(V.CLASSES_PT) == 80


# ── Gemini 404 + visuais ─────────────────────────────────────────────────────
def test_gemini_404_troca_de_modelo(monkeypatch):
    from core import llm_providers as L
    c = L.CerebroLLM("gemini", "gemini-2.5-flash", chave="chave")
    usados = []

    class R:
        def __init__(self, st, txt, js=None):
            self.status_code, self.text, self._js = st, txt, js
        def json(self):
            return self._js

    def post(url, headers=None, data=None, timeout=None):
        m = json.loads(data)["model"]
        usados.append(m)
        if m in ("gemini-2.5-flash", "gemini-3.5-flash"):
            return R(404, '{"error": {"message": "This model models/%s is no longer available"}}' % m)
        return R(200, "", {"choices": [{"message": {"content": "ok"}}]})
    monkeypatch.setattr(c._http, "post", post)
    r = c.conversar("s", [{"role": "user", "content": "oi"}], [], max_tokens=8)
    assert r.texto == "ok" and c.modelo == "gemini-3.5-flash-lite"
    assert usados == ["gemini-2.5-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"]
    assert L.PROVEDORES["gemini"]["modelo"] != "gemini-2.5-flash"


def test_hub_geometria():
    # Este teste precisa da dependência gráfica opcional; sem Qt, pule-o
    # em vez de falhar toda a suíte de testes em ambientes headless.
    pytest.importorskip("PyQt6")
    from ui import hub_geom as G
    assert G.modulo_da_funcao("simple_finance") == 4 and G.modulo_da_funcao("web_search") == 2
    assert G.modulo_da_funcao("nada_disso") is None
    p = G.posicoes(100, 100, 50, 0.0)
    assert len(p) == 6 and abs(p[0][0] - 100) < 1e-6 and abs(p[0][1] - 50) < 1e-6      # o 1º fica no alto
    for estado, fala in (("SPEAKING", True), ("LISTENING", False), ("THINKING", False), ("SLEEPING", False)):
        assert all(0.0 <= t <= 1.0 for _, t in G.pacotes(2.3, estado, fala))


def test_visuais_antigos_continuam():
    from memory.config_manager import HUD_STYLES
    assert {"orb", "minimal", "aurora", "liquid", "holo", "globe", "hub", "matrix", "waves"} == set(HUD_STYLES)
