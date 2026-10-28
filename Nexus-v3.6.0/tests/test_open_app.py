"""Abrir programas (2.4.1): cmd, câmera, Python 3.12 e Backup do Windows."""
import subprocess

import pytest

from actions import open_app as OA

ATALHOS = {
    "python 3.12 (64-bit)": r"C:\menu\Python 3.12 (64-bit).lnk",
    "idle (python 3.12 64-bit)": r"C:\menu\IDLE (Python 3.12 64-bit).lnk",
    "command prompt": r"C:\menu\Command Prompt.lnk",
}
STORE = {
    "camera hd": "Player.CameraHD!App",
    "backup do windows": "MicrosoftWindows.Client.CBS!WindowsBackup",
    "prompt de comando": r"{1AC14E77}\cmd.exe",
}


@pytest.fixture(autouse=True)
def indices(monkeypatch):
    monkeypatch.setattr(OA, "_shortcut_index", dict(ATALHOS))
    monkeypatch.setattr(OA, "_store_index", dict(STORE))


@pytest.mark.parametrize("pedido", ["câmera", "Câmera", "camera", "CÂMERA"])
def test_camera_com_ou_sem_acento(pedido):
    assert OA._find_store_app(pedido) == "Player.CameraHD!App"


@pytest.mark.parametrize("pedido", ["Backup do Windows", "backup windows", "Windows Backup", "backup"])
def test_backup_do_windows_em_qualquer_ordem(pedido):
    assert OA._find_store_app(pedido) == "MicrosoftWindows.Client.CBS!WindowsBackup"


def test_python_312_abre_o_python_e_nao_o_idle():
    assert OA._find_shortcut("Python 3.12").endswith("Python 3.12 (64-bit).lnk")


@pytest.mark.parametrize("pedido", ["cmd", "Prompt de Comando", "linha de comando"])
def test_prompt_de_comando_vira_cmd(pedido):
    if OA._SYSTEM == "Windows":
        assert OA._normalize(pedido) == "cmd.exe"


def test_por_palavras_nao_inventa():
    assert OA._por_palavras("spotify", STORE) is None
    assert OA._por_palavras("do", STORE) is None          # só palavra vazia não procura nada


def test_cmd_ganha_console_proprio_e_saida_visivel(monkeypatch):
    chamadas = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, **k: chamadas.append((args, k)))
    OA._iniciar_exe(r"C:\Windows\System32\cmd.exe")
    args, k = chamadas[0]
    assert "stdout" not in k and "stderr" not in k        # antes ia para DEVNULL: janela em branco
    if OA._SYSTEM == "Windows":
        assert k["creationflags"] & subprocess.CREATE_NEW_CONSOLE


def test_confirma_um_cmd_novo_mesmo_com_outro_ja_aberto():
    antes = {"cmd.exe#10", "python.exe#20", "explorer.exe#30"}
    assert OA._subiu(antes, antes | {"cmd.exe#99"}, "cmd", "cmd.exe")
    assert OA._subiu(antes, antes | {"python.exe#98"}, "Python 3.12")
    assert not OA._subiu(antes, antes | {"python.exe#97"}, "cmd", "cmd.exe")   # outro python não confirma o cmd
    assert not OA._subiu(antes, antes, "cmd")


def test_sem_app_de_camera_explica_como_instalar(monkeypatch):
    if OA._SYSTEM != "Windows":
        pytest.skip("só no Windows")
    monkeypatch.setattr(OA, "_store_index", {})
    monkeypatch.setattr(OA, "_launch_windows", lambda nome: False)
    import core.janelas as J
    monkeypatch.setattr(J, "trazer_para_frente", lambda nome: None)
    r = OA.open_app({"app_name": "câmera"})
    assert "Câmera do Windows não está instalado" in r and "ms-windows-store://" in r
