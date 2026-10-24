"""Streaming (2.4.6): core/llm_providers.py (conversar_stream) + core/voz_propria.py (FalaEmFluxo)
+ o laço do motor próprio. O servidor é de verdade (HTTP local, SSE em chunked), então o teste
enxerga se o texto chega ENQUANTO o servidor ainda escreve."""
import asyncio
import importlib.util
import json
import sys
import threading
import time
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pytest

from core import llm_providers as L
from core import voz_propria as V


# ── servidor SSE de mentira ──────────────────────────────────────────────────
class _Servidor:
    """roteiro: lista de eventos (dict → 'data: json', str → linha crua, float → pausa em s)."""

    def __init__(self):
        self.roteiro, self.status_stream, self.corte = [], 200, False
        self.chamadas = []
        outer = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def do_POST(self):
                corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.chamadas.append(corpo)
                if corpo.get("stream") and outer.status_stream != 200:
                    d = b'{"error":"sem streaming"}'
                    self.send_response(outer.status_stream)
                    self.send_header("Content-Length", str(len(d)))
                    self.end_headers()
                    self.wfile.write(d)
                    return
                if not corpo.get("stream"):
                    d = json.dumps({"choices": [{"message": {"content": "resposta sem stream"}}]}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(d)))
                    self.end_headers()
                    self.wfile.write(d)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()

                def chunk(b):
                    self.wfile.write(f"{len(b):x}\r\n".encode() + b + b"\r\n")
                    self.wfile.flush()
                for ev in outer.roteiro:
                    if isinstance(ev, float):
                        time.sleep(ev)
                    elif isinstance(ev, dict):
                        chunk(b"data: " + json.dumps(ev).encode() + b"\n\n")
                    else:
                        chunk(ev.encode())
                if outer.corte:
                    self.connection.close()
                    return
                chunk(b"data: [DONE]\n\n")
                self.wfile.write(b"0\r\n\r\n")

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/v1"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def parar(self):
        self.srv.shutdown()


def _delta(texto=None, **kw):
    d = {}
    if texto is not None:
        d["content"] = texto
    d.update(kw)
    return {"choices": [{"delta": d}]}


@pytest.fixture
def srv():
    s = _Servidor()
    yield s
    s.parar()


def _cerebro(srv):
    return L.CerebroLLM("llamacpp", "modelo-x", srv.url, "", timeout=10)


# ── conversar_stream ─────────────────────────────────────────────────────────
def test_texto_chega_enquanto_o_servidor_ainda_escreve(srv):
    srv.roteiro = [_delta("Olá, "), _delta("tudo bem? "), 0.6, _delta("Posso ajudar."), 0.1]
    marcas = []
    t0 = time.monotonic()
    r = _cerebro(srv).conversar_stream("s", [{"role": "user", "content": "oi"}], [],
                                       lambda p: marcas.append((time.monotonic() - t0, p)))
    total = time.monotonic() - t0
    assert r.texto == "Olá, tudo bem? Posso ajudar."
    assert "".join(p for _, p in marcas) == "Olá, tudo bem? Posso ajudar."
    assert marcas[0][0] < 0.4 < total          # o 1º pedaço veio ANTES do servidor terminar (≥0,7 s)
    assert srv.chamadas[0]["stream"] is True


def test_chamada_de_ferramenta_montada_dos_pedacos(srv):
    srv.roteiro = [
        _delta("Vou abrir."),
        _delta(tool_calls=[{"index": 0, "id": "c1", "function": {"name": "open_app", "arguments": ""}}]),
        _delta(tool_calls=[{"index": 0, "function": {"arguments": '{"app_na'}}]),
        _delta(tool_calls=[{"index": 0, "function": {"arguments": 'me": "chrome"}'}}]),
        _delta(tool_calls=[{"index": 1, "id": "c2", "function": {"name": "timer_action",
                                                                  "arguments": '{"action":"status"}'}}]),
    ]
    r = _cerebro(srv).conversar_stream("s", [{"role": "user", "content": "x"}], [{"name": "open_app"}],
                                       lambda p: None)
    assert r.texto == "Vou abrir."
    assert [(c["id"], c["name"], c["args"]) for c in r.chamadas] == [
        ("c1", "open_app", {"app_name": "chrome"}), ("c2", "timer_action", {"action": "status"})]


def test_raciocinio_interno_nao_e_falado(srv):
    srv.roteiro = [_delta("<thi"), _delta("nk>planejando "), _delta("muito</think>"),
                   _delta("Oi"), _delta("! Tudo "), _delta("bem.")]
    falado = []
    r = _cerebro(srv).conversar_stream("s", [{"role": "user", "content": "x"}], [], falado.append)
    assert "".join(falado) == "Oi! Tudo bem." and r.texto == "Oi! Tudo bem."


def test_sem_streaming_no_servidor_cai_para_a_chamada_normal(srv):
    srv.status_stream = 400
    falado = []
    r = _cerebro(srv).conversar_stream("s", [{"role": "user", "content": "x"}], [], falado.append)
    assert r.texto == "resposta sem stream" and falado == []


def test_queda_no_meio_devolve_o_que_ja_saiu(srv):
    srv.roteiro = [_delta("Primeira parte. "), 0.05]
    srv.corte = True                           # a conexão cai sem [DONE]
    falado = []
    r = _cerebro(srv).conversar_stream("s", [{"role": "user", "content": "x"}], [], falado.append)
    assert r.texto.startswith("Primeira parte.") and r.chamadas == []
    assert len(srv.chamadas) == 1              # não repetiu a chamada (nem a fala)


def test_claude_stream():
    ev = types.SimpleNamespace
    final = ev(content=[ev(type="text", text="Certo, abrindo."),
                        ev(type="tool_use", id="t1", name="open_app", input={"app_name": "x"})])

    class Fluxo:
        text_stream = iter(["Certo, ", "abrindo."])

        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get_final_message(self): return final

    c = L.CerebroLLM.__new__(L.CerebroLLM)
    c.nativo_claude, c.modelo = True, "m"
    c._claude = ev(messages=ev(stream=lambda **kw: Fluxo()))
    pedacos = []
    r = c.conversar_stream("s", [{"role": "user", "content": "x"}], [], pedacos.append)
    assert "".join(pedacos) == "Certo, abrindo." and r.texto == "Certo, abrindo."
    assert r.chamadas == [{"id": "t1", "name": "open_app", "args": {"app_name": "x"}}]


# ── FalaEmFluxo ──────────────────────────────────────────────────────────────
class _Voz:
    def __init__(self, seg=0.0, falha=False):
        self.seg, self.falha, self.ditas = seg, falha, []

    def sintetizar(self, frase, idioma):
        if self.falha:
            raise RuntimeError("boom")
        time.sleep(self.seg)
        self.ditas.append(frase)
        yield np.zeros(10, np.int16)


class _Toc:
    def __init__(self, seg=0.0):
        self.seg, self.tocadas, self._int = seg, 0, False

    @property
    def interrompido(self): return self._int
    def parar(self): self._int = True
    def novo_turno(self): self._int = False

    def tocar(self, pcm):
        if self._int:
            return False
        time.sleep(self.seg)
        self.tocadas += 1
        return True


def _fala(voz, toc, **kw):
    ev = {"c": 0, "t": 0, "e": []}
    f = V.FalaEmFluxo(voz, toc, "pt", ao_comecar=lambda: ev.__setitem__("c", ev["c"] + 1),
                      ao_terminar=lambda: ev.__setitem__("t", ev["t"] + 1), ao_erro=ev["e"].append, **kw)
    return f, ev


def test_fala_em_ordem_e_junta_frases_curtas():
    voz, toc = _Voz(), _Toc()
    f, ev = _fala(voz, toc)
    for pedaco in ["Oi. Tudo ", "bem com você hoje? ", "Que bom!\nAté ", "logo."]:
        f.alimentar(pedaco)
    f.fechar(); f.esperar(5)
    assert voz.ditas == ["Oi. Tudo bem com você hoje?", "Que bom! Até logo."]
    assert ev["c"] == 1 and ev["t"] == 1 and f.enfileirou


def test_fala_comeca_antes_do_texto_acabar():
    voz, toc = _Voz(), _Toc()
    f, _ = _fala(voz, toc)
    f.alimentar("Essa é a primeira frase completa. Segue")
    t0 = time.monotonic()
    while not voz.ditas and time.monotonic() - t0 < 2:
        time.sleep(0.01)
    assert voz.ditas == ["Essa é a primeira frase completa."]       # falando, sem ter chamado fechar()
    f.fechar(); f.esperar(5)
    assert voz.ditas[-1] == "Segue"


def test_sintese_e_reproducao_em_paralelo():
    voz, toc = _Voz(seg=0.2), _Toc(seg=0.2)
    f, _ = _fala(voz, toc)
    t0 = time.monotonic()
    f.alimentar("Frase número um bem longa aqui. Frase número dois bem longa aqui. "
                "Frase número três bem longa aqui. Frase número quatro bem longa aqui.")
    f.fechar(); f.esperar(10)
    assert voz.ditas.__len__() == 4
    assert time.monotonic() - t0 < 1.35        # em fila seria ≥ 1,6 s


def test_interromper_descarta_o_resto():
    voz, toc = _Voz(seg=0.05), _Toc(seg=0.1)
    f, ev = _fala(voz, toc)
    f.alimentar("Frase número um bem longa aqui. Frase número dois bem longa aqui. "
                "Frase número três bem longa aqui.")
    time.sleep(0.15)
    toc.parar()
    f.alimentar(" mais texto que não deve ser falado.")
    f.fechar(); f.esperar(5)
    assert toc.tocadas < 3 and ev["t"] == ev["c"]


def test_falha_na_voz_nao_trava():
    f, ev = _fala(_Voz(falha=True), _Toc())
    f.alimentar("Uma frase comprida o bastante para ser falada. Outra frase comprida aqui.")
    f.fechar(); f.esperar(5)
    assert ev["e"] and "boom" in ev["e"][0]


def test_rodadas_nao_se_misturam():
    voz, toc = _Voz(), _Toc(seg=0.1)
    a, _ = _fala(voz, toc)
    a.alimentar("Primeira rodada com texto bastante longo."); a.fechar()
    b, _ = _fala(voz, toc, depois_de=a)
    b.alimentar("Segunda rodada com texto bastante longo."); b.fechar()
    b.esperar(5)
    assert voz.ditas == ["Primeira rodada com texto bastante longo.", "Segunda rodada com texto bastante longo."]


# ── o laço do motor próprio, de ponta a ponta ────────────────────────────────
@pytest.fixture
def motor(monkeypatch):
    """Carrega assistant/motor_proprio.py sem o resto do pacote (que pede PortAudio, Qt…)."""
    falso = types.ModuleType("assistant.common")
    falso.asyncio, falso._pcm_level = asyncio, lambda b: 0.0
    falso.agora, falso.audio_devices, falso.data_hora = (lambda: None), None, (lambda d: "hoje")
    pacote = types.ModuleType("assistant"); pacote.__path__ = []
    monkeypatch.setitem(sys.modules, "assistant", pacote)
    monkeypatch.setitem(sys.modules, "assistant.common", falso)
    spec = importlib.util.spec_from_file_location(
        "assistant.motor_proprio", __file__.replace("tests/test_streaming.py", "assistant/motor_proprio.py"))
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "assistant.motor_proprio", mod)
    spec.loader.exec_module(mod)
    return mod


class _UI:
    muted = False
    def __init__(self): self.log = []
    def write_log(self, m): self.log.append(m)
    def set_state(self, s): pass
    def set_audio_level(self, v): pass


def _app(motor, cerebro, voz, toc, stream=True):
    class App(motor.MotorProprioMixin):
        pass
    a = App()
    a.ui, a._wake_enabled, a._awake = _UI(), False, True
    a._proprio_hist, a._proprio_cerebro, a._proprio_voz, a._proprio_tocador = [], cerebro, voz, toc
    a._proprio_stream, a._session_log, a._asst_name = stream, [], "NEXUS"
    a._ditado = types.SimpleNamespace(ativo=False)
    a._pending_vision = None
    a.falando = []
    a.set_speaking = a.falando.append
    a._proprio_sistema = lambda: "sistema"
    a._proprio_ferramentas = lambda pedido: []
    a._idioma_da_resposta = lambda: "pt"
    return a


def test_turno_com_streaming_fala_e_registra(motor, srv):
    srv.roteiro = [_delta("Claro, posso ajudar com isso. "), 0.2, _delta("Já está pronto.")]
    voz, toc = _Voz(), _Toc()
    app = _app(motor, _cerebro(srv), voz, toc)
    asyncio.run(app._proprio_turno("faz isso", "digitado"))
    assert voz.ditas == ["Claro, posso ajudar com isso.", "Já está pronto."]
    assert any("NEXUS: Claro, posso ajudar com isso. Já está pronto." in m for m in app.ui.log)
    assert app.falando == [True, False]
    assert app._proprio_hist[-1] == {"role": "assistant", "content": "Claro, posso ajudar com isso. Já está pronto.",
                                     "tool_calls": []}


def test_turno_com_ferramenta_fala_enquanto_ela_roda(motor, srv):
    srv.roteiro = [_delta("Vou olhar isso para você agora. "),
                   _delta(tool_calls=[{"index": 0, "id": "c1", "function": {"name": "web_search",
                                                                            "arguments": '{"q":"x"}'}}])]
    voz, toc = _Voz(), _Toc()
    app = _app(motor, _cerebro(srv), voz, toc)
    rodadas = {"n": 0}

    async def _exec(fc):
        rodadas["n"] += 1
        return types.SimpleNamespace(response={"result": "achei", "status": "done"})
    app._execute_tool = _exec

    # 2ª chamada ao modelo (depois da ferramenta): resposta final
    original = srv.roteiro
    chamadas = {"n": 0}
    orig_stream = app._proprio_cerebro.conversar_stream

    def _stream(*a, **k):
        chamadas["n"] += 1
        srv.roteiro = original if chamadas["n"] == 1 else [_delta("Encontrei o resultado que você pediu.")]
        return orig_stream(*a, **k)
    app._proprio_cerebro.conversar_stream = _stream
    asyncio.run(app._proprio_turno("pesquisa", "digitado"))
    assert rodadas["n"] == 1
    assert voz.ditas == ["Vou olhar isso para você agora.", "Encontrei o resultado que você pediu."]


def test_turno_sem_streaming_continua_igual(motor, srv):
    voz, toc = _Voz(), _Toc()
    app = _app(motor, _cerebro(srv), voz, toc, stream=False)
    falou = []

    async def _falar(texto, idioma=None): falou.append(texto)
    app._proprio_falar = _falar
    asyncio.run(app._proprio_turno("oi", "digitado"))
    assert falou == ["resposta sem stream"] and voz.ditas == []
