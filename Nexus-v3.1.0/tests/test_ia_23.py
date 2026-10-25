"""Testes da 2.3: reconexão, embeddings/memória semântica, roteador, voz do dono."""
import json
import sys
import threading
from pathlib import Path

import numpy as np
import pytest

from core import reconexoes as rc


# ── reconexão: decisões ──────────────────────────────────────────────────────
def test_nao_renova_cedo_nem_sem_handle():
    assert not rc.deve_renovar(60, True, True, False, False)               # conexão nova: nada a renovar
    assert not rc.deve_renovar(9 * 60, False, True, False, False)          # sem handle perderia a conversa
    assert rc.deve_renovar(8.6 * 60, True, True, False, False)             # calmo depois de 8,5 min
    assert not rc.deve_renovar(8.6 * 60, True, False, False, False)        # falando: espera


def test_renovacao_forcada_na_conversa_continua():
    """Antes: quem conversava sem pausa nunca renovava e a queda vinha NO MEIO da fala."""
    assert not rc.deve_renovar(9.0 * 60, True, False, False, False)
    assert rc.deve_renovar(rc.RENOVAR_FORCADA_S + rc.ESPERA_FORCADA_S + 1, True, False, False, False)
    # sem handle a forçada não vale (renovar perderia a conversa)
    assert not rc.deve_renovar(9.9 * 60, False, False, False, False)


def test_goaway_manda_renovar_no_prazo_mesmo_sem_calma():
    assert not rc.deve_renovar(60, True, False, True, False)               # avisou, ainda dá tempo
    assert rc.deve_renovar(60, True, False, True, True)                    # prazo estourou


def test_continua_acordado_depois_de_reconectar():
    assert rc.seguir_acordado(True, True, 30)
    assert not rc.seguir_acordado(False, True, 30)                         # estava dormindo: continua dormindo
    assert not rc.seguir_acordado(True, False, 0)                          # primeira conexão do app
    assert not rc.seguir_acordado(True, True, rc.CONVERSA_VIVA_S + 1)      # conversa velha


def test_so_resume_quando_a_conversa_acabou():
    assert not rc.conversa_acabou(False, 20)          # queda no meio da conversa: não resume
    assert rc.conversa_acabou(False, rc.CONVERSA_VIVA_S + 5)
    assert rc.conversa_acabou(True, 1)                # app fechando


# ── reconexão: diário ────────────────────────────────────────────────────────
@pytest.fixture
def diario_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(rc, "ARQUIVO", tmp_path / "reconexoes.log")
    return tmp_path


def test_descrever_pega_o_erro_real_dentro_do_grupo_e_esconde_chaves():
    class Cancelado(Exception):
        pass
    Cancelado.__name__ = "CancelledError"
    grupo = type("ExceptionGroup", (Exception,), {})("g")
    chave_falsa = "AIza" + "SyABCDEFGHIJKLMNOPQRSTUVWXYZ0123456"   # em pedaços: o preparar_publicacao não acusa
    grupo.exceptions = [Cancelado(), ConnectionError(f"received 1011 internal error key={chave_falsa}")]
    tipo, msg = rc.descrever(grupo)
    assert tipo == "ConnectionError" and "AIza" not in msg and "[chave]" in msg


@pytest.mark.parametrize("tipo, msg, causa", [
    ("ConnectionClosedError", "received 1011 (internal error) Deadline expired", "erro do servidor"),
    ("ConnectionClosedError", "sent 1011 keepalive ping timeout", "erro do servidor"),
    ("ConnectionClosedError", "no close frame received or sent", "conexão perdida (rede)"),
    ("TimeoutError", "timed out", "rede / sem internet"),
    ("APIError", "400 API key not valid", "chave"),
    ("APIError", "1007 invalid argument", "pedido recusado (1007)"),
    ("_ReconnectSignal", "", "pedido do app"),
])
def test_classificar_causa(tipo, msg, causa):
    assert rc.classificar(tipo, msg) == causa


def test_registrar_e_resumir(diario_tmp):
    rc.registrar("caiu", "ConnectionClosedError", "1011 internal error", 301.2, False, True)
    rc.registrar("renovou", "_ReconnectSignal", "", 515.0, True, True)
    rc.registrar("conectou", conectado_s=0.0, manteve_conversa=True, acordado=True)
    r = rc.resumo()
    assert "2 reconexão(ões)" in r and "NÃO foi mantida" in r and "Em 1 a conversa" in r
    assert len(rc.ler()) == 3


def test_diario_nao_cresce_sem_limite(diario_tmp):
    for i in range(rc._MAX_LINHAS + 50):
        rc.registrar("caiu", "X", str(i))
    assert len(rc.ler(10_000)) == rc._MAX_LINHAS


def test_diagnostico_mostra_reconexoes(diario_tmp):
    from actions import diagnostico as dg
    assert "Nenhuma queda" in dg.diagnostico({"action": "reconnections"})
    rc.registrar("caiu", "X", "1011", 100, True, True)
    assert dg.diagnostico({"action": "reconnections"}).startswith("[done] 1 reconexão")
