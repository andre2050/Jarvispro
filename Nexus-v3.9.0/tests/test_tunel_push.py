"""Túnel (cloudflared falso) e Web Push: endereços permitidos, assinaturas, envio, painel e IP real atrás do túnel."""
import base64
import os
import stat
import sys
import time
from pathlib import Path

import pytest

from core import push_web as P
from core import tunel as T

FALSO = str(Path(__file__).parent / "cloudflared_falso.py")


def _b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _sub(endpoint="https://fcm.googleapis.com/fcm/send/abc123"):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    pub = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return {"endpoint": endpoint, "keys": {"p256dh": _b64u(pub), "auth": _b64u(os.urandom(16))}}


# ── Web Push ─────────────────────────────────────────────────────────────────
def test_chave_vapid_valida_e_estavel(tmp_path):
    arq = tmp_path / "vapid.pem"
    k1 = P.chave_publica(arq)
    raw = base64.urlsafe_b64decode(k1 + "=" * (-len(k1) % 4))
    assert len(raw) == 65 and raw[0] == 4                       # ponto não comprimido P-256
    assert P.chave_publica(arq) == k1 and arq.exists()          # a mesma nas próximas vezes


@pytest.mark.parametrize("url,ok", [
    ("https://fcm.googleapis.com/fcm/send/x", True),
    ("https://updates.push.services.mozilla.com/wpush/v2/x", True),
    ("https://web.push.apple.com/x", True),
    ("https://wns2-par02p.notify.windows.com/w/?token=x", True),
    ("http://fcm.googleapis.com/x", False),                      # sem https
    ("https://127.0.0.1/x", False), ("https://localhost/x", False), ("https://192.168.0.1/admin", False),
    ("https://169.254.169.254/latest/meta-data", False),         # metadados de nuvem
    ("https://fcm.googleapis.com.evil.com/x", False),            # sufixo falso
    ("https://fcm.googleapis.com@evil.com/x", False),            # truque do usuário@
    ("https://fcm.googleapis.com:8443/x", False),                # porta estranha
    ("ftp://fcm.googleapis.com/x", False), ("", False), ("lixo", False)])
def test_endpoint_permitido(url, ok):
    assert P.endpoint_permitido(url) is ok


def test_assinar_cancelar_dedupe_e_limite(tmp_path):
    arq = tmp_path / "subs.json"
    s = _sub()
    assert P.assinar(s, arq) == 1 and P.assinar(s, arq) == 1       # o mesmo celular não duplica
    for i in range(12):
        P.assinar(_sub(f"https://fcm.googleapis.com/fcm/send/c{i}"), arq)
    assert P.quantas(arq) == P.MAX_ASSINATURAS
    assert P.cancelar("https://fcm.googleapis.com/fcm/send/c11", arq) == P.MAX_ASSINATURAS - 1
    for ruim in (None, "x", {}, {"endpoint": "https://evil.com/x", "keys": _sub()["keys"]},
                 {"endpoint": s["endpoint"], "keys": {"p256dh": "curta", "auth": "x"}}):
        with pytest.raises(ValueError):
            P.assinar(ruim, arq)


def test_enviar_remove_morto_mantem_falha_temporaria_e_corta_texto(tmp_path, monkeypatch):
    arq, chave = tmp_path / "subs.json", tmp_path / "v.pem"
    ok, morto, temp = (_sub(f"https://fcm.googleapis.com/fcm/send/{n}") for n in ("ok", "morto", "temp"))
    for x in (ok, morto, temp):
        P.assinar(x, arq)
    enviados = []

    class Resp:
        def __init__(self, c): self.status_code = c

    class Erro(Exception):
        def __init__(self, c): self.response = Resp(c)

    def fn(sub, dados, arq_chave):
        if sub["endpoint"].endswith("morto"):
            raise Erro(410)
        if sub["endpoint"].endswith("temp"):
            raise Erro(503)
        enviados.append(dados)

    monkeypatch.setattr(P, "_ultimo_envio", 0.0)
    r = P.enviar("NEXUS", "palavra " * 100, arq, chave, fn, ignorar_intervalo=True)
    assert (r["enviados"], r["removidos"], r["falhas"]) == (1, 1, 1)
    assert P.quantas(arq) == 2                                       # só o morto saiu
    import json
    corpo = json.loads(enviados[0])
    assert len(corpo["body"]) <= P.MAX_CORPO and corpo["title"] == "NEXUS"
    assert chave.exists()                                            # o par VAPID foi criado


def test_enviar_respeita_intervalo_sem_assinaturas_e_sem_pacote(tmp_path, monkeypatch):
    arq = tmp_path / "subs.json"
    assert P.enviar("a", "b", arq, tmp_path / "v.pem", lambda *a: None)["motivo"] == "nenhum celular assinado"
    P.assinar(_sub(), arq)
    monkeypatch.setattr(P, "_ultimo_envio", 0.0)
    n = []
    P.enviar("a", "b", arq, tmp_path / "v.pem", lambda *a: n.append(1), agora=1000.0)
    r = P.enviar("a", "b", arq, tmp_path / "v.pem", lambda *a: n.append(1), agora=1005.0)     # 5 s depois
    assert r["motivo"] == "aviso recente demais" and len(n) == 1
    assert P.enviar("a", "b", arq, tmp_path / "v.pem", lambda *a: n.append(1), agora=1030.0)["enviados"] == 1
    monkeypatch.setattr(P, "disponivel", lambda: False)
    monkeypatch.setattr(P, "_ultimo_envio", 0.0)
    assert "pywebpush" in P.enviar("a", "b", arq, tmp_path / "v.pem")["motivo"]


def test_pywebpush_real_criptografa_e_assina_sem_rede(tmp_path, monkeypatch):
    pw = pytest.importorskip("pywebpush")
    capturado = {}

    class R:
        status_code = 201
        text = ""
        headers = {}
        def raise_for_status(self): pass

    def post(url, data=None, headers=None, **kw):
        capturado.update(url=url, data=data, headers=headers or {})
        return R()

    monkeypatch.setattr(pw.requests, "post", post)
    sub = _sub()
    P.chave_publica(tmp_path / "v.pem")
    P._webpush_real(sub, '{"title":"NEXUS","body":"segredo do aviso"}', tmp_path / "v.pem")
    assert capturado["url"] == sub["endpoint"]
    assert capturado["headers"]["Authorization"].lower().startswith("vapid")
    assert b"segredo do aviso" not in capturado["data"]              # o corpo vai criptografado


# ── Túnel ────────────────────────────────────────────────────────────────────
@pytest.fixture
def cloudflared(tmp_path):
    exe = tmp_path / "cloudflared"
    exe.write_text(f"#!/bin/sh\nexec {sys.executable} {FALSO} \"$@\"\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return str(exe)


@pytest.fixture
def tunel():
    t = T.Tunel()
    yield t
    t.parar()


def test_tunel_abre_pega_url_avisa_e_fecha(tunel, cloudflared):
    eventos = []
    tunel.ao_mudar(eventos.append)
    assert not tunel.ativo()
    url = tunel.iniciar(8000, True, 1.0, binario=cloudflared)
    assert url == "https://exemplo-teste-123.trycloudflare.com" and tunel.ativo()
    assert tunel.iniciar(8000, True, 1.0, binario=cloudflared) == url           # já aberto: devolve o mesmo
    assert 55 <= tunel.restante_min() <= 60 and eventos == [url]
    proc = tunel.proc
    tunel.parar()
    assert proc.poll() is not None and not tunel.ativo() and tunel.restante_min() == 0 and eventos == [url, ""]


@pytest.mark.parametrize("https,esperado,tls", [(True, "https://127.0.0.1:8443", True), (False, "http://127.0.0.1:8443", False)])
def test_tunel_argumentos_https_e_http(cloudflared, https, esperado, tls):
    t = T.Tunel()
    try:
        t.iniciar(8443, https, 0.5, binario=cloudflared)
        fim = time.time() + 3
        while not any(l.startswith("ARGS:") for l in t.ultimas) and time.time() < fim:
            time.sleep(0.05)
        args = next(l for l in t.ultimas if l.startswith("ARGS:"))
        assert f"--url {esperado}" in args and "--no-autoupdate" in args and args.startswith("ARGS:tunnel")
        assert ("--no-tls-verify" in args) is tls                   # o certificado do painel é autoassinado: só no modo https
    finally:
        t.parar()


def test_tunel_sem_binario_e_sem_url_a_tempo(tunel, monkeypatch, cloudflared):
    monkeypatch.setattr(T, "achar_cloudflared", lambda: None)
    with pytest.raises(T.ErroTunel, match="cloudflared"):
        tunel.iniciar(8000, False)
    monkeypatch.setattr(T, "TEMPO_ABRIR", 1.0)
    with pytest.raises(T.ErroTunel, match="não abriu"):
        tunel.iniciar(8000, False, binario=cloudflared, argumentos_extra=["--sem-url"])
    assert not tunel.ativo() and tunel.proc is None


def test_tunel_limita_duracao(tunel, cloudflared):
    tunel.iniciar(8000, False, 999, binario=cloudflared)
    assert tunel.restante_min() <= T.DURACAO_MAX_H * 60


# ── Painel: endpoints, aviso com app fechado e IP real ───────────────────────
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from starlette.testclient import TestClient  # noqa: E402

from dashboard import server as S  # noqa: E402


@pytest.fixture
def painel(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "UPLOADS_DIR", tmp_path / "up")
    (tmp_path / "up").mkdir()
    monkeypatch.setattr(S.DashboardServer, "_ssl_enabled", staticmethod(lambda: False))
    monkeypatch.setattr(P, "ARQ_SUBS", tmp_path / "subs.json")
    monkeypatch.setattr(P, "ARQ_CHAVE", tmp_path / "v.pem")
    srv = S.DashboardServer()
    srv._uploads_dir = tmp_path / "up"
    return srv


def _token(srv):
    return srv._novo_token("123456")


def test_endpoints_de_push_exigem_login_e_validam(painel):
    with TestClient(painel.app) as c:
        for rota, corpo in (("/api/push/assinar", {}), ("/api/push/cancelar", {})):
            assert c.post(rota, json=corpo).status_code == 401
        assert c.get("/api/push/chave").status_code == 401
        h = {"Authorization": f"Bearer {_token(painel)}"}
        d = c.get("/api/push/chave", headers=h).json()
        assert d["ok"] and len(d["key"]) > 80
        r = c.post("/api/push/assinar", json={"subscription": {"endpoint": "https://evil.com/x", "keys": {}}}, headers=h)
        assert r.status_code == 400
        sub = _sub()
        assert c.post("/api/push/assinar", json={"subscription": sub}, headers=h).json() == {"ok": True, "celulares": 1}
        assert c.post("/api/push/cancelar", json={"endpoint": sub["endpoint"]}, headers=h).json()["celulares"] == 0


def test_aviso_so_com_painel_fechado_e_so_para_respostas_do_nexus(painel, monkeypatch):
    chamadas = []
    monkeypatch.setattr(P, "enviar", lambda t, c, **k: chamadas.append((t, c)))
    P.assinar(_sub())
    painel._avisar_celular_fechado({"type": "log", "speaker": "jarvis", "text": "Pronto, abri o app."})
    deadline = time.time() + 2
    while not chamadas and time.time() < deadline:
        time.sleep(0.02)
    assert chamadas == [("NEXUS", "Pronto, abri o app.")]
    chamadas.clear()
    painel._avisar_celular_fechado({"type": "log", "speaker": "user", "text": "oi"})          # fala do usuário: não avisa
    painel._avisar_celular_fechado({"type": "status", "state": "active"})
    painel._clients.add(object())                                                              # painel aberto: o próprio painel avisa
    painel._avisar_celular_fechado({"type": "log", "speaker": "jarvis", "text": "oi"})
    time.sleep(0.2)
    assert chamadas == []


def test_url_publica_do_tunel_e_ip_real(painel):
    local = painel.get_url()
    painel.set_public_base("https://abc.trycloudflare.com/")
    assert painel.get_url() == "https://abc.trycloudflare.com" and painel.get_manual_url() == "abc.trycloudflare.com"
    painel.set_public_base("")
    assert painel.get_url() == local
    # IP real: atrás do túnel (pedido vindo de 127.0.0.1) o bloqueio por tentativas é por visitante, não geral
    painel.set_public_base("https://abc.trycloudflare.com")
    with TestClient(painel.app, client=("127.0.0.1", 5000)) as c:
        def tentar(ip):
            return c.post("/login", json={"key": "000000"}, headers={"cf-connecting-ip": ip}).status_code
        codigos = [tentar("203.0.113.9") for _ in range(12)]
        assert 429 in codigos                                         # o atacante é bloqueado…
        assert tentar("198.51.100.7") != 429                          # …e outra pessoa não
    painel.set_public_base("")
    painel._falhas.clear()
    with TestClient(painel.app, client=("127.0.0.1", 5000)) as c:
        # sem túnel, o cabeçalho é IGNORADO (não dá para forjar IP para escapar do bloqueio)
        codigos = [c.post("/login", json={"key": "000000"}, headers={"cf-connecting-ip": f"203.0.113.{i}"}).status_code
                   for i in range(12)]
        assert 429 in codigos


def test_acao_tunel_painel(monkeypatch, cloudflared):
    from actions import tunel_painel as A
    from core import confirm
    novo = T.Tunel()
    monkeypatch.setattr(T, "_tunel", novo)
    original = T.Tunel.iniciar
    monkeypatch.setattr(T.Tunel, "iniciar", lambda self, porta, https, horas=4.0, binario=None, argumentos_extra=None:
                        original(self, porta, https, horas, binario=cloudflared))        # usa o cloudflared de mentira
    pedidos = []
    monkeypatch.setattr(confirm, "pending_title", lambda: "")
    monkeypatch.setattr(confirm, "request", lambda key, title, detail, run: pedidos.append((title, detail, run)) or "aguardando")
    monkeypatch.setattr(A, "_porta_e_https", lambda: (8000, False))
    try:
        monkeypatch.setattr(T, "achar_cloudflared", lambda: None)
        assert "winget install" in A.tunel_painel({"action": "open"})
        monkeypatch.setattr(T, "achar_cloudflared", lambda: cloudflared)
        assert A.tunel_painel({"action": "open", "hours": 2}) == "aguardando"
        assert "INTERNET" in pedidos[0][0] and "2 h" in pedidos[0][1]
        assert not novo.ativo()                                                          # nada abre antes do CONFIRMAR
        r = pedidos[0][2]()
        assert r.startswith("[done]") and "trycloudflare.com" in r and novo.ativo()
        assert "já está aberto" in A.tunel_painel({"action": "open"})
        st = A.tunel_painel({"action": "status"})
        assert "Túnel aberto" in st and "Avisos com o app fechado" in st
        assert A.tunel_painel({"action": "close"}).startswith("[done]") and not novo.ativo()
        assert "Túnel fechado" in A.tunel_painel({"action": "status"})
    finally:
        novo.parar()
