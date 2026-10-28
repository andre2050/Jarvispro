"""Testes do painel pelo celular (dashboard/server.py): login, sessões, limites e uploads."""
import io
import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from starlette.testclient import TestClient

from dashboard import server as S


@pytest.fixture
def painel(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "UPLOADS_DIR", tmp_path / "up")
    (tmp_path / "up").mkdir()
    monkeypatch.setattr(S.DashboardServer, "_ssl_enabled", staticmethod(lambda: False))
    srv = S.DashboardServer()
    srv._uploads_dir = tmp_path / "up"
    srv._acordou = []
    srv.set_wake_callback(lambda: srv._acordou.append(1))
    return srv


@pytest.fixture
def cli(painel):
    with TestClient(painel.app) as c:
        yield c


def _entrar(painel, cli):
    pin = painel.new_key()
    r = cli.post("/login", json={"pin": pin})
    assert r.status_code == 200 and r.json()["ok"]
    return r.json()["token"], pin


def test_login_certo_e_chave_de_uso_unico(painel, cli):
    token, pin = _entrar(painel, cli)
    assert len(token) > 30
    again = cli.post("/login", json={"pin": pin})
    assert again.status_code == 401                       # a chave só vale uma vez


def test_login_com_json_quebrado_nao_derruba_o_servidor(cli):
    r = cli.post("/login", content=b"isso nao e json", headers={"content-type": "application/json"})
    assert r.status_code == 400


def test_tentativas_erradas_bloqueiam_o_aparelho(painel, cli):
    for _ in range(S.LOGIN_MAX_FALHAS):
        assert cli.post("/login", json={"pin": "ERRADO"}).status_code == 401
    r = cli.post("/login", json={"pin": "ERRADO"})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
    # durante o bloqueio nem a chave certa entra
    pin = painel.new_key()
    assert cli.post("/login", json={"pin": pin}).status_code == 429
    # passada a janela, volta a funcionar
    painel._falhas["testclient"] = [time.time() - S.LOGIN_JANELA_S - 1] * S.LOGIN_MAX_FALHAS
    assert cli.post("/login", json={"pin": pin}).status_code == 200


def test_qr_expirado_tambem_conta_como_tentativa(painel, cli):
    for _ in range(S.LOGIN_MAX_FALHAS):
        cli.get("/auto-login", params={"key": "XXXXXX"})
    assert cli.get("/auto-login", params={"key": "XXXXXX"}).status_code == 429


def test_qr_valido_cria_sessao_e_aparelho_pareado(painel, cli):
    pin = painel.new_key()
    r = cli.get("/auto-login", params={"key": pin})
    assert r.status_code == 200 and "jarvis_token" in r.text and "jarvis_device_token" in r.text
    assert len(painel._device_sessions) == 1 and len(painel._tokens) == 1


def test_aparelho_pareado_reconecta_e_expira_em_30_dias(painel, cli):
    pin = painel.new_key()
    cli.get("/auto-login", params={"key": pin})
    dev = next(iter(painel._device_sessions))
    ok = cli.post("/api/device-login", json={"device_token": dev})
    assert ok.status_code == 200 and ok.json()["token"]
    painel._device_sessions[dev]["at"] = time.time() - S.DEVICE_VALIDADE_S - 5
    assert cli.post("/api/device-login", json={"device_token": dev}).status_code == 401
    assert dev not in painel._device_sessions
    assert cli.post("/api/device-login", json={"device_token": "inventado"}).status_code == 401


def test_sessao_parada_expira(painel, cli):
    token, _ = _entrar(painel, cli)
    h = {"Authorization": f"Bearer {token}"}
    assert cli.post("/api/wake", headers=h).status_code == 200 and painel._acordou
    painel._token_seen[token] = time.time() - S.TOKEN_OCIOSO_S - 10
    assert cli.post("/api/wake", headers=h).status_code == 401
    assert token not in painel._tokens and token not in painel._token_keys


def test_uso_renova_a_sessao(painel, cli):
    token, _ = _entrar(painel, cli)
    painel._token_seen[token] = time.time() - S.TOKEN_OCIOSO_S + 60          # quase expirando
    assert cli.post("/api/wake", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert time.time() - painel._token_seen[token] < 5


def test_sem_token_tudo_e_recusado(cli):
    assert cli.post("/api/command", json={"text": "oi"}).status_code == 401
    assert cli.post("/api/wake").status_code == 401
    assert cli.get("/api/files").status_code == 401
    assert cli.get("/uploads/x.txt").status_code == 401
    assert cli.get("/uploads/x.txt", params={"token": "falso"}).status_code == 401
    assert cli.post("/api/revoke-devices").status_code == 401


def test_comando_limitado_e_json_invalido(painel, cli):
    token, _ = _entrar(painel, cli)
    h = {"Authorization": f"Bearer {token}"}
    assert cli.post("/api/command", json={"text": "x" * 20000}, headers=h).status_code == 200
    fila = painel._command_queue
    texto = fila.get_nowait()
    assert len(texto) == S.MAX_COMANDO_CHARS
    assert cli.post("/api/command", content=b"{{", headers={**h, "content-type": "application/json"}).status_code == 400
    assert cli.post("/api/command", json=[1, 2], headers=h).status_code == 400


def test_comando_cifrado_ida_e_volta(painel, cli):
    import base64
    import os

    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    token, pin = _entrar(painel, cli)
    chave = S._derive_key(pin)
    iv = os.urandom(16)
    p = padding.PKCS7(128).padder()
    dados = p.update("abre o chrome".encode()) + p.finalize()
    enc = Cipher(algorithms.AES(chave), modes.CBC(iv)).encryptor()
    pacote = base64.b64encode(iv + enc.update(dados) + enc.finalize()).decode()
    r = cli.post("/api/command", json={"enc": pacote}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and painel._command_queue.get_nowait() == "abre o chrome"
    r = cli.post("/api/command", json={"enc": "lixo=="}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 400


def test_upload_nomes_perigosos(painel, cli):
    token, _ = _entrar(painel, cli)
    h = {"Authorization": f"Bearer {token}"}
    for enviado, esperado in [("../../fora.txt", "fora.txt"), ("CON.txt", "_CON.txt"), ("nul", "_nul"),
                              ("a:b?.txt", "a_b_.txt"), ("normal.txt", "normal.txt")]:
        r = cli.post("/api/upload", files={"file": (enviado, io.BytesIO(b"conteudo"))}, headers=h)
        assert r.status_code == 200, (enviado, r.text)
        assert r.json()["name"] == esperado
        assert (painel._uploads_dir / esperado).read_bytes() == b"conteudo"
    # mesmo nome duas vezes não sobrescreve
    r = cli.post("/api/upload", files={"file": ("normal.txt", io.BytesIO(b"outro"))}, headers=h)
    assert r.json()["name"] == "normal_1.txt"
    assert not (painel._uploads_dir.parent / "fora.txt").exists()


def test_download_exige_token_e_nao_sai_da_pasta(painel, cli, tmp_path):
    token, _ = _entrar(painel, cli)
    (painel._uploads_dir / "a.txt").write_text("segredo da pasta", encoding="utf-8")
    (tmp_path / "fora.txt").write_text("não pode sair", encoding="utf-8")
    assert cli.get("/uploads/a.txt", params={"token": token}).text == "segredo da pasta"
    assert cli.get("/uploads/..%2Ffora.txt", params={"token": token}).status_code in (404, 400)
    assert cli.get("/uploads/%2e%2e", params={"token": token}).status_code in (404, 400)     # ".." sem o cliente normalizar


def test_cabecalhos_de_seguranca(cli):
    r = cli.get("/login")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["x-frame-options"] == "DENY"
    r = cli.post("/login", json={"pin": "x"})
    assert r.headers["cache-control"] == "no-store"


def test_websocket(painel, cli):
    token, _ = _entrar(painel, cli)
    with pytest.raises(Exception):
        with cli.websocket_connect("/ws?token=falso"):
            pass
    with cli.websocket_connect(f"/ws?token={token}") as ws:
        ws.send_text("isto não é JSON")                       # não pode derrubar a conexão
        ws.send_json({"type": "command", "text": "  oi nexus  "})
        ws.send_json([1, 2, 3])
        ws.send_json({"type": "command", "text": "segundo"})
        time.sleep(0.3)
    assert painel._command_queue.get_nowait() == "oi nexus"
    assert painel._command_queue.get_nowait() == "segundo"


def test_tarefas_em_segundo_plano_ficam_presas_ate_acabar(painel, cli):
    token, pin = _entrar(painel, cli)
    time.sleep(0.2)
    assert painel._tarefas == set()                           # terminaram e foram soltas


# ── PWA (3.5): instalar na tela inicial e tela offline ───────────────────────
def test_pwa_manifest_sw_offline_e_icones(cli):
    m = cli.get("/manifest.webmanifest")
    assert m.status_code == 200 and "manifest+json" in m.headers["content-type"]
    d = m.json()
    assert d["display"] == "standalone" and d["start_url"] == "/" and {i["sizes"] for i in d["icons"]} == {"192x192", "512x512"}
    sw = cli.get("/sw.js")
    assert sw.status_code == 200 and "javascript" in sw.headers["content-type"]
    assert sw.headers["service-worker-allowed"] == "/" and sw.headers["cache-control"] == "no-cache"
    assert "/api/" in sw.text and "return;" in sw.text            # o SW não toca em /api, /ws nem /uploads
    assert "NEXUS fora do ar" in cli.get("/offline").text
    for n in ("icon-192.png", "icon-512.png"):
        r = cli.get(f"/icons/{n}")
        assert r.status_code == 200 and r.content[:4] == b"\x89PNG"
    assert cli.get("/icons/../server.py").status_code in (404, 422)
    assert cli.get("/icons/qualquer.png").status_code == 404


def test_pwa_rotas_publicas_nao_expoem_nada_e_paginas_ligam_o_manifest(cli):
    # sem token, as rotas privadas continuam fechadas
    assert cli.get("/api/files").status_code in (401, 403)
    assert cli.post("/api/command", json={"text": "oi"}).status_code in (401, 403, 422)
    for caminho in ("/", "/login"):
        html = cli.get(caminho).text
        assert 'rel="manifest"' in html and "apple-touch-icon" in html
    assert "serviceWorker" in cli.get("/").text and "NEXUS" in cli.get("/").text
