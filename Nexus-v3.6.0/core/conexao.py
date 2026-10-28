"""Modo offline (NEXUS Ultra 2026 3.3) — o que continua funcionando quando a internet cai.

  • `tem_internet()` testa a rede de verdade (conexão TCP rápida), com cache curto para não pesar;
  • quando cai, o NEXUS AVISA uma vez no log e na I.S.A. e passa a responder NA HORA, sem esperar o
    tempo limite, nas ferramentas que dependem de rede ("sem internet: não consigo pesquisar agora");
  • o que é local segue normal: rotinas, notas e lembretes, tarefas, diário, busca pelo sentido,
    rede de intenções, previsão de hábitos, ajustes do computador e o modelo local (Ollama), se houver;
  • clima e notícias já consultados continuam saindo do cache por alguns minutos.

Nunca levanta erro para quem chama.
"""
from __future__ import annotations

import socket
import threading
import time

CACHE_S = 15.0
ALVOS = (("1.1.1.1", 443), ("8.8.8.8", 53), ("8.8.4.4", 443))

# Ferramentas que só funcionam com rede (consultam a internet, e-mail ou sites).
PRECISAM_DE_INTERNET = frozenset({
    "web_search", "weather_report", "noticias", "flight_finder", "youtube_video", "browser_control",
    "mapas", "email_reader", "email_checker", "system_update", "game_updater", "price_alert",
    "compras", "send_message", "dev_agent", "morning_briefing",
    # 3.4
    "ligar_whatsapp", "bom_dia", "pesquisa_profunda",
})
FUNCIONA_OFFLINE = (
    "rotinas e modos (como o modo trabalho)", "notas rápidas, lembretes e tarefas", "diário e hábitos",
    "busca pelo sentido nas suas notas", "a rede de intenções local (comandos simples)",
    "ajustes do computador, abrir aplicativos, música local e timers",
    "o modelo local (Ollama), se estiver instalado",
)
NAO_FUNCIONA_OFFLINE = (
    "pesquisa na web, notícias e previsão do tempo nova", "e-mail e mensagens",
    "voos, mapas e YouTube", "o Gemini e os outros modelos online (sem eles a conversa fica limitada)",
)

_trava = threading.RLock()
_estado = {"online": True, "checado_em": 0.0, "desde": time.time()}


def _testar(timeout: float = 1.5) -> bool:
    for host, porta in ALVOS:
        try:
            with socket.create_connection((host, porta), timeout=timeout):
                return True
        except OSError:
            continue
    return False


def tem_internet(forcar: bool = False, agora: float | None = None, testar=None) -> bool:
    """True se há rede. O resultado vale CACHE_S segundos."""
    try:
        agora = agora if agora is not None else time.monotonic()
        with _trava:
            if not forcar and _estado["checado_em"] and agora - _estado["checado_em"] < CACHE_S:
                return _estado["online"]
        ok = bool((testar or _testar)())
        with _trava:
            if ok != _estado["online"]:
                _estado["desde"] = time.time()
            _estado.update(online=ok, checado_em=agora)
        return ok
    except Exception:
        return True            # na dúvida, não bloqueia nada


def verificar(testar=None) -> tuple[bool, bool]:
    """(mudou, online): testa agora e diz se o estado mudou desde a última vez."""
    antes = _estado["online"]
    online = tem_internet(forcar=True, testar=testar)
    return online != antes, online


def precisa_internet(ferramenta: str) -> bool:
    return ferramenta in PRECISAM_DE_INTERNET


def bloqueio(ferramenta: str, testar=None) -> str | None:
    """A mensagem rápida para a ferramenta que precisa de rede quando NÃO há rede; None = pode rodar."""
    if not precisa_internet(ferramenta):
        return None
    if tem_internet(testar=testar):
        return None
    return (f"[failed] Sem internet agora: '{ferramenta}' precisa de rede. Diga isso ao usuário em uma frase "
            "curta e ofereça o que funciona offline (notas, lembretes, tarefas, rotinas, abrir aplicativos).")


def texto_estado(testar=None) -> str:
    online = tem_internet(forcar=True, testar=testar)
    if online:
        return "Estou com internet e tudo funciona normalmente."
    return ("Estou sem internet. Continua funcionando: " + "; ".join(FUNCIONA_OFFLINE)
            + ". Não funciona sem conexão: " + "; ".join(NAO_FUNCIONA_OFFLINE) + ".")


def texto_offline() -> str:
    """O que funciona e o que não funciona sem internet (a pergunta 'e se a internet cair?')."""
    return ("Sem internet eu continuo com: " + "; ".join(FUNCIONA_OFFLINE)
            + ". Sem conexão eu perco: " + "; ".join(NAO_FUNCIONA_OFFLINE) + ".")
