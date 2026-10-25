"""Chave do Gemini inválida: reconhecer os erros e avisar por voz sem repetir."""
import pytest

from core import aviso_voz


@pytest.mark.parametrize("erro", [
    "400 INVALID_ARGUMENT. API key not valid. Please pass a valid API key.",
    "{'error': {'status': 'INVALID_ARGUMENT', 'details': [{'reason': 'API_KEY_INVALID'}]}}",
    "400 API key expired. Please renew the API key.",
    "403 PERMISSION_DENIED: Your API key was reported as leaked.",
    "received 1007 (invalid frame payload data) API key not valid",
])
def test_reconhece_chave_invalida(erro):
    assert aviso_voz.chave_invalida(erro)


@pytest.mark.parametrize("erro", [
    "1007 (invalid frame payload data) Request contains an invalid argument.",
    "TimeoutError", "getaddrinfo failed", "", None,
    "429 RESOURCE_EXHAUSTED quota",
])
def test_nao_confunde_outros_erros(erro):
    assert not aviso_voz.chave_invalida(erro)


def test_fala_uma_vez_por_minuto(monkeypatch):
    ditos = []
    monkeypatch.setattr(aviso_voz, "_falar_agora", lambda t: ditos.append(t))
    monkeypatch.setattr(aviso_voz, "_ultimo", 0.0)
    assert aviso_voz.falar("oi") is True
    assert aviso_voz.falar("oi de novo") is False
    import time
    time.sleep(0.1)
    assert ditos == ["oi"]
