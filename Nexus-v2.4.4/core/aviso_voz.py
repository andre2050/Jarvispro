"""core/aviso_voz.py — avisos falados que não dependem do Gemini (NEXUS Pro 2.2).

Quando a chave do Gemini é recusada, a conversa por voz nem chega a abrir, então o NEXUS
não tem como falar pelo Gemini. Este módulo fala pela voz do próprio sistema (pyttsx3,
offline, voz masculina quando houver) e reconhece os vários jeitos que o Google tem de
dizer "chave inválida".
"""
from __future__ import annotations

import threading
import time

MENSAGEM_CHAVE_INVALIDA = ("A chave da API do Gemini é inválida. "
                           "Digite uma chave nova na tela de configuração.")

_SINAIS_CHAVE = (
    "api key not valid", "api_key_invalid", "api key expired", "api_key_expired",
    "api key was reported as leaked", "reported as leaked", "api key not found",
    "api_key_service_blocked", "api_key_http_referrer_blocked", "api_key_ip_address_blocked",
    "please pass a valid api key", "invalid api key",
)

_COOLDOWN = 60.0
_ultimo = 0.0
_trava = threading.Lock()


def chave_invalida(erro) -> bool:
    """True se o erro do Gemini significa que a chave não serve (inválida, vencida, vazada, bloqueada)."""
    t = str(erro or "").lower()
    if any(s in t for s in _SINAIS_CHAVE):
        return True
    # "1007" sozinho é qualquer pedido recusado; só vale junto de "api key"
    return "1007" in t and "api key" in t


def falar(texto: str, rapido: bool = False) -> bool:
    """Fala ``texto`` pela voz do sistema, em segundo plano. No máximo uma vez por minuto
    (o laço de reconexão não pode ficar repetindo). Devolve False se não falou."""
    global _ultimo
    with _trava:
        agora = time.monotonic()
        if agora - _ultimo < _COOLDOWN:
            return False
        _ultimo = agora
    threading.Thread(target=_falar_agora, args=(texto,), daemon=True, name="aviso-voz").start()
    return True


def _falar_agora(texto: str) -> None:
    try:
        import pyttsx3
        eng = pyttsx3.init()
        eng.setProperty("rate", 175)
        try:
            from core.vozes import escolher_voz
            voz = escolher_voz(eng.getProperty("voices"), ("portug", "pt-br", "pt_br", "brazil"))
            if voz:
                eng.setProperty("voice", voz)
        except Exception:
            pass
        eng.say(texto)
        eng.runAndWait()
    except Exception as e:                      # sem voz do sistema: a mensagem escrita continua valendo
        print(f"[aviso_voz] não consegui falar: {e}")
