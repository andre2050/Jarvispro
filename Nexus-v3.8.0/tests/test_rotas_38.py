"""Rotas do painel do 3.8: missões (protegidas por login) e rede de NEXUS (protegida pela chave do par)."""
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from starlette.testclient import TestClient  # noqa: E402

from core import missoes as M  # noqa: E402
from core import rede_nexus as R  # noqa: E402
from dashboard import server as S  # noqa: E402


@pytest.fixture
def painel(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "UPLOADS_DIR", tmp_path / "up")
    (tmp_path / "up").mkdir()
    monkeypatch.setattr(S.DashboardServer, "_ssl_enabled", staticmethod(lambda: False))
    monkeypatch.setattr(M, "PASTA", tmp_path / "missoes")
    from actions import missao as A
    A._motor = A._gerente = None
    srv = S.DashboardServer()
    srv._uploads_dir = tmp_path / "up"
    yield srv
    if A._gerente:
        A._gerente.parar()
    A._motor = A._gerente = None


def test_missoes_exigem_login(painel):
    with TestClient(painel.app) as c:
        assert c.get("/api/missoes").status_code == 401
        assert c.get("/api/missoes/abc").status_code == 401
        assert c.post("/api/missoes/abc/cancelar", json={}).status_code == 401


def test_missoes_lista_vazia_detalhe_404_e_acao_invalida(painel):
    h = {"Authorization": f"Bearer {painel._novo_token('123456')}"}
    with TestClient(painel.app) as c:
        assert c.get("/api/missoes", headers=h).json() == {"missoes": []}
        assert c.get("/api/missoes/nao_existe", headers=h).status_code == 404
        assert c.post("/api/missoes/nao_existe/explodir", json={}, headers=h).status_code == 400
        assert c.post("/api/missoes/nao_existe/cancelar", json={}, headers=h).status_code == 400


def test_rede_recusa_estranho_e_bloqueia_tentativas(painel, tmp_path, monkeypatch):
    from actions import rede_nexus as RA
    monkeypatch.setattr(RA, "_rede", R.Rede(tmp_path / "r.json", tmp_path / "mem", auditar=False))
    with TestClient(painel.app) as c:
        assert c.post("/api/rede", content=b"lixo", headers={"X-Nexus-Peer": "x"}).status_code == 400
        assert c.post("/api/rede", content=b"", headers={"X-Nexus-Peer": "hello:x"}).status_code == 400
        for _ in range(10):
            c.post("/api/rede", content=b"lixo", headers={"X-Nexus-Peer": "x"})
        assert c.post("/api/rede", content=b"lixo", headers={"X-Nexus-Peer": "x"}).status_code == 429


def test_rede_ping_de_um_par_pareado_funciona(painel, tmp_path, monkeypatch):
    from actions import rede_nexus as RA
    casa = R.Rede(tmp_path / "casa.json", tmp_path / "mc", auditar=False)
    cel = R.Rede(tmp_path / "cel.json", tmp_path / "mm", auditar=False)
    cel.eu("celular")
    casa.eu("casa")
    monkeypatch.setattr(RA, "_rede", casa)
    cod = casa.convidar()
    with TestClient(painel.app) as c:
        def enviar(url, rem, blob):
            r = c.post("/api/rede", content=blob, headers={"X-Nexus-Peer": rem})
            assert r.status_code == 200
            return r.content
        cel.enviar = enviar
        pid = cel.entrar(cod, "http://casa")
        assert cel.ping(pid)
