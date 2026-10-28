"""3.5.0 — correções da auditoria de segurança.

1. clean_temp e a exclusão de arquivos ocultos só rodam se a PESSOA apertar CONFIRMAR
   no HUD (core/confirm.py). O `confirm=true` que o modelo escreve não basta.
2. O validador/caixa de areia do desktop.py recusa escrita, desligar/bloquear a tela
   e cópia por cima de arquivos existentes.
"""
import os
import time
from pathlib import Path

import pytest

from actions import desktop as D
from actions import file_controller as FC
from core import confirm


# ── ajudantes ────────────────────────────────────────────────────────────────

def _esperar(condicao, limite=3.0):
    fim = time.monotonic() + limite
    while time.monotonic() < fim:
        if condicao():
            return True
        time.sleep(0.02)
    return condicao()


@pytest.fixture
def hud(monkeypatch):
    """Liga um HUD de mentira ao core.confirm e devolve a lista de avisos mostrados."""
    mostrados = []
    monkeypatch.setattr(confirm, "_pending", None)
    monkeypatch.setattr(confirm, "_show_cb", lambda t, d: mostrados.append((t, d)))
    monkeypatch.setattr(confirm, "_hide_cb", lambda: None)
    monkeypatch.setattr(confirm, "_log_cb", None)
    yield mostrados
    monkeypatch.setattr(confirm, "_pending", None)


@pytest.fixture
def sem_hud(monkeypatch):
    monkeypatch.setattr(confirm, "_pending", None)
    monkeypatch.setattr(confirm, "_show_cb", None)


@pytest.fixture
def temp_velho(tmp_path, monkeypatch):
    """Uma pasta 'temp' com dois arquivos antigos."""
    pasta = tmp_path / "temp"
    pasta.mkdir()
    antigos = []
    for nome in ("a.tmp", "b.tmp"):
        f = pasta / nome
        f.write_text("x" * 100)
        velho = time.time() - 3 * 3600
        os.utime(f, (velho, velho))
        antigos.append(f)
    monkeypatch.setattr(FC, "_get_temp", lambda: pasta)
    return antigos


@pytest.fixture
def pasta_com_ocultos(tmp_path, monkeypatch):
    pasta = tmp_path / "casa"
    pasta.mkdir()
    ocultos = [pasta / ".segredo1", pasta / ".segredo2"]
    for f in ocultos:
        f.write_text("oi")
    (pasta / "normal.txt").write_text("fica")
    monkeypatch.setattr(FC, "_resolve_path", lambda raw: pasta)
    monkeypatch.setattr(FC, "_SAFE_ROOTS", [tmp_path])
    # sem lixeira de verdade nos testes: "mandar para a lixeira" vira um simples apagar
    monkeypatch.setattr(FC, "_safe_trash", lambda p: (Path(p).unlink(), "Moved to Trash")[1])
    return pasta, ocultos


def _fc(**params):
    return FC.file_controller(parameters=params)


# ── 1. clean_temp ────────────────────────────────────────────────────────────

def test_clean_temp_sem_confirm_so_mede(temp_velho, hud):
    r = _fc(action="clean_temp")
    assert "can be removed" in r
    assert all(f.exists() for f in temp_velho)
    assert hud == []                                   # nem pergunta: só mediu


def test_clean_temp_confirm_do_modelo_nao_apaga_sem_hud(temp_velho, sem_hud):
    r = _fc(action="clean_temp", confirm=True)
    assert "have not done it" in r
    assert all(f.exists() for f in temp_velho)


def test_clean_temp_confirm_do_modelo_so_abre_o_aviso(temp_velho, hud):
    r = _fc(action="clean_temp", confirm=True)
    assert "CONFIRMATION_PENDING" in r
    assert len(hud) == 1 and "temporários" in hud[0][0]
    assert all(f.exists() for f in temp_velho)         # nada apagado até a pessoa apertar


def test_clean_temp_pessoa_cancela(temp_velho, hud):
    _fc(action="clean_temp", confirm=True)
    confirm.resolve(False)
    time.sleep(0.2)
    assert all(f.exists() for f in temp_velho)


def test_clean_temp_pessoa_confirma(temp_velho, hud):
    _fc(action="clean_temp", confirm=True)
    assert all(f.exists() for f in temp_velho)
    confirm.resolve(True)
    assert _esperar(lambda: not any(f.exists() for f in temp_velho))


def test_clean_temp_pasta_limpa_nao_pede_confirmacao(tmp_path, monkeypatch, hud):
    vazia = tmp_path / "vazia"
    vazia.mkdir()
    monkeypatch.setattr(FC, "_get_temp", lambda: vazia)
    r = _fc(action="clean_temp", confirm=True)
    assert "already clean" in r
    assert hud == []


def test_dois_pedidos_seguidos_nao_empilham_avisos(temp_velho, hud):
    _fc(action="clean_temp", confirm=True)
    r = _fc(action="clean_temp", confirm=True)
    assert "already a confirmation waiting" in r
    assert len(hud) == 1


# ── 1b. arquivos ocultos ─────────────────────────────────────────────────────

def test_ocultos_listar_nao_pergunta_nem_apaga(pasta_com_ocultos, hud):
    pasta, ocultos = pasta_com_ocultos
    r = _fc(action="hidden_files", mode="list")
    assert "hidden file(s) found" in r
    assert all(f.exists() for f in ocultos) and hud == []


def test_ocultos_delete_com_confirm_do_modelo_nao_apaga_sem_hud(pasta_com_ocultos, sem_hud):
    pasta, ocultos = pasta_com_ocultos
    _fc(action="hidden_files", mode="delete", confirm=True)
    assert all(f.exists() for f in ocultos)


def test_ocultos_delete_so_apaga_quando_a_pessoa_confirma(pasta_com_ocultos, hud):
    pasta, ocultos = pasta_com_ocultos
    r = _fc(action="hidden_files", mode="delete", confirm=True)
    assert "CONFIRMATION_PENDING" in r
    assert all(f.exists() for f in ocultos)
    confirm.resolve(True)
    assert _esperar(lambda: not any(f.exists() for f in ocultos))
    assert (pasta / "normal.txt").exists()             # só os ocultos


def test_ocultos_delete_cancelado_mantem_tudo(pasta_com_ocultos, hud):
    pasta, ocultos = pasta_com_ocultos
    _fc(action="hidden_files", mode="delete", confirm=True)
    confirm.resolve(False)
    time.sleep(0.2)
    assert all(f.exists() for f in ocultos)


# ── 2. validador do desktop.py ───────────────────────────────────────────────

@pytest.mark.parametrize("codigo", [
    "Path('alvo.txt').write_text('x')",
    "Path('alvo.bin').write_bytes(b'x')",
    "ctypes.windll.user32.ExitWindowsEx(0x12, 0)",
    "ctypes.windll.user32.LockWorkStation()",
    "u = ctypes.windll.user32\nu.ExitWindowsEx(0, 0)",          # via variável
    "ctypes.windll.user32['ExitWindowsEx'](0, 0)",              # via índice
    "ctypes.windll.user32.PostMessageW(0, 0x10, 0, 0)",         # WM_CLOSE em qualquer janela
    # o que já era recusado continua sendo
    "Path('a').unlink()",
    "open('a', 'w')",
    "Path('a').__class__",
])
def test_validador_recusa(codigo):
    assert D._validar_codigo_gerado(codigo) is not None


@pytest.mark.parametrize("codigo", [
    "print(len(list(Path('.').iterdir())))",
    "print(Path('a.txt').read_text())",
    "time.sleep(0.1)",
    "pyautogui.moveTo(10, 10)",
    "ctypes.windll.user32.GetForegroundWindow()",
    "'a b'.replace('a', 'c')",
])
def test_validador_continua_deixando_passar_o_inofensivo(codigo):
    assert D._validar_codigo_gerado(codigo) is None


def test_caixa_de_areia_copy2_nao_sobrescreve(tmp_path):
    origem, destino = tmp_path / "o.txt", tmp_path / "d.txt"
    origem.write_text("novo")
    destino.write_text("original")
    sb = D._build_sandbox()
    with pytest.raises(PermissionError):
        sb["shutil"].copy2(str(origem), str(destino))
    assert destino.read_text() == "original"
    # destino é uma pasta que já tem um arquivo com esse nome: também recusa
    pasta = tmp_path / "pasta"
    pasta.mkdir()
    (pasta / "o.txt").write_text("original2")
    with pytest.raises(PermissionError):
        sb["shutil"].copy2(str(origem), str(pasta))
    assert (pasta / "o.txt").read_text() == "original2"


def test_caixa_de_areia_copy2_copia_para_destino_novo(tmp_path):
    origem, novo = tmp_path / "o.txt", tmp_path / "novo.txt"
    origem.write_text("conteudo")
    D._build_sandbox()["shutil"].copy2(str(origem), str(novo))
    assert novo.read_text() == "conteudo"


def test_caixa_de_areia_copytree_nao_mistura_com_pasta_existente(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    (src / "a.txt").write_text("a")
    dst.mkdir()
    (dst / "velho.txt").write_text("velho")
    sb = D._build_sandbox()
    with pytest.raises(PermissionError):
        sb["shutil"].copytree(str(src), str(dst))
    with pytest.raises(PermissionError):
        sb["shutil"].copytree(str(src), str(dst), dirs_exist_ok=True)
    assert not (dst / "a.txt").exists()
    sb["shutil"].copytree(str(src), str(tmp_path / "novo"))
    assert (tmp_path / "novo" / "a.txt").read_text() == "a"


def test_execucao_de_ponta_a_ponta_recusa_escrita(tmp_path):
    alvo = tmp_path / "importante.txt"
    alvo.write_text("original")
    r = D._execute_generated_code(f"Path(r'{alvo}').write_text('destruido')")
    assert "Não executei" in r
    assert alvo.read_text() == "original"
