"""Painel remoto (celular): em português do Brasil, com a marca NEXUS e os atalhos rápidos (4.4.0)."""
import re
from pathlib import Path

import pytest

ESTATICO = Path(__file__).resolve().parent.parent / "dashboard" / "static"
PAGINAS = ["app.html", "login.html", "offline.html"]


def _ler(nome):
    return (ESTATICO / nome).read_text(encoding="utf-8")


@pytest.mark.parametrize("nome", PAGINAS)
def test_paginas_declaram_pt_br(nome):
    assert '<html lang="pt-BR">' in _ler(nome)


def test_login_mostra_a_marca_nexus_e_nao_jarvis():
    s = _ler("login.html")
    assert "<em>N</em>EXUS" in s
    assert not re.search(r"jarvis", re.sub(r"jarvis_(key|token|device_token)", "", s, flags=re.I), re.I)


@pytest.mark.parametrize("nome", ["app.html", "login.html"])
@pytest.mark.parametrize("ingles", [
    "Connection error", "Invalid or expired", "Send a command", "Connecting", "Reconnecting", "Remote Access",
    "File sent", "Upload failed", "Voice connection failed", "Microphone denied", "Tap to stop", "Mic error",
    "Remote session active", "Connected to NEXUS", "Sleeping", ">SEND<", ">WAKE<", ">CONNECT<", "Download back",
])
def test_sem_texto_visivel_em_ingles(nome, ingles):
    assert ingles not in _ler(nome)


def test_atalhos_rapidos_enviam_pelo_mesmo_caminho_do_botao_enviar():
    s = _ler("app.html")
    cmds = re.findall(r'data-cmd="([^"]+)"', s)
    assert len(cmds) >= 6 and all(len(c) > 5 for c in cmds)
    assert "inp.value = b.getAttribute('data-cmd'); doSend();" in s


def test_cor_de_destaque_tem_armazenamento_protegido():
    s = _ler("app.html")
    assert "id=\"tema-btn\"" in s
    # localStorage pode lançar exceção (janela privada, dados bloqueados): toda leitura/escrita fica em try/catch
    for m in re.finditer(r"localStorage\.(get|set)Item\('nexus_tema'", s):
        antes = s[max(0, m.start() - 160):m.start()]
        assert "try" in antes


def test_painel_cabe_em_telas_estreitas():
    s = _ler("app.html")
    assert "@media (max-width:430px)" in s and ".enc-badge{white-space:nowrap}" in s
