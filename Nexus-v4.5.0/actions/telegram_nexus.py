"""Telegram (3.5): o NEXUS manda e lê mensagens do SEU chat com o SEU bot. Só esse chat; nada de terceiros.

Por voz:  "configura o Telegram" (passe o token do BotFather)   "reconhece meu Telegram"
          "manda no meu Telegram: comprar pão"    "tem mensagem no meu Telegram?"
Detalhes e segurança: core/integracoes.py."""
from __future__ import annotations

from core import integracoes as I


def telegram_nexus(parameters: dict, player=None) -> str:
    acao = str(parameters.get("action") or "send").strip().lower()
    try:
        if acao in ("setup", "configurar"):
            return "[done] " + I.telegram_configurar(str(parameters.get("token") or ""))
        if acao in ("pair", "reconhecer"):
            return "[done] " + I.telegram_reconhecer()
        if acao in ("send", "enviar"):
            return "[done] " + I.telegram_enviar(str(parameters.get("text") or ""))
        if acao in ("read", "ler"):
            return I.telegram_ler(int(parameters.get("limit") or 5))
    except I.ErroIntegracao as e:
        return f"[failed] {e}"
    except Exception as e:
        return f"[failed] Telegram: {e}"
    return "Ação desconhecida. Use setup, pair, send ou read."


TOOL = {
    "name": "telegram_nexus",
    "description": (
        "TELEGRAM to the user's OWN chat with their own bot (never to other people — use send_message for that). "
        "action=send with text ('manda no meu Telegram…'), action=read (messages the user wrote to the bot), "
        "action=setup with token (BotFather token), action=pair (recognise the user's chat after they messaged the bot)."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "send | read | setup | pair"},
            "text": {"type": "STRING", "description": "For send: the message"},
            "token": {"type": "STRING", "description": "For setup: the BotFather token"},
            "limit": {"type": "INTEGER", "description": "For read: how many messages (default 5)"},
        },
        "required": ["action"],
    },
    "handler": telegram_nexus,
}
