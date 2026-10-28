"""Presença: máquina de estados, IP só de rede local, câmera descarta o quadro, ações."""
import types

from core import presenca as P


def test_so_chega_depois_de_confirmar_e_respeita_a_pausa():
    s = P.Presenca(confirmar=2, ausente_apos=100, pausa_oi=1000)
    assert s.passo(True, 0) == "" and s.passo(True, 20) == "chegou"
    assert s.passo(True, 40) == ""
    assert s.passo(False, 80) == "" and s.passo(False, 150) == "saiu"
    assert s.passo(True, 160) == "" and s.passo(True, 180) == ""      # voltou cedo: sem novo oi (pausa de 1000s)
    assert s.passo(False, 200) == ""
    assert [s.passo(True, 1300), s.passo(False, 1305), s.passo(False, 1500)] == ["", "", "saiu"]


def test_um_teste_falso_isolado_nao_chega():
    s = P.Presenca(confirmar=2)
    assert s.passo(True, 0) == "" and s.passo(False, 5) == "" and s.passo(True, 10) == ""


def test_ip_so_de_rede_local():
    assert P.ip_valido("192.168.0.15") == "192.168.0.15"
    assert P.ip_valido("8.8.8.8") == "" and P.ip_valido("127.0.0.1") == "" and P.ip_valido("rm -rf") == ""
    assert not P.celular_responde("8.8.8.8", executar=lambda *a, **k: types.SimpleNamespace(returncode=0))
    assert P.celular_responde("192.168.0.15", executar=lambda *a, **k: types.SimpleNamespace(returncode=0))
    assert not P.celular_responde("192.168.0.15", executar=lambda *a, **k: types.SimpleNamespace(returncode=1))


def test_camera_fecha_o_dispositivo_e_nao_grava(monkeypatch):
    import numpy as np
    estado = {"fechou": False}

    class Cap:
        def isOpened(self): return True
        def read(self): return True, np.zeros((240, 320, 3), np.uint8)
        def release(self): estado["fechou"] = True
    assert P.rosto_na_camera(abrir=lambda i: Cap()) is False        # quadro preto: sem rosto
    assert estado["fechou"]
    class CapFechada(Cap):
        def isOpened(self): return False
    assert P.rosto_na_camera(abrir=lambda i: CapFechada()) is False


def test_sensor_e_acao(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "ARQ", tmp_path / "p.json")
    from actions import presenca as A
    assert P.sensor_atual() is None and "desligada" in A.presenca({"action": "status"})
    assert A.presenca({"action": "on", "phone_ip": "8.8.8.8"}).startswith("[failed]")
    assert "falta escolher" in A.presenca({"action": "on"})
    r = A.presenca({"action": "on", "phone_ip": "192.168.1.9", "camera": True})
    assert r.startswith("[done]") and "192.168.1.9" in r and "câmera" in r
    assert P.sensor_atual() is not None
    assert A.presenca({"action": "off"}).startswith("[done]") and P.sensor_atual() is None
