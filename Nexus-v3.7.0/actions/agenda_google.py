"""Agenda (3.5): lê o Google Calendar (ou qualquer .ics) pelo endereço secreto iCal — só leitura, sem login.

Por voz:  "configura minha agenda" (passe o endereço iCal)   "o que tenho hoje?"   "e amanhã?"
          "meus compromissos da semana"   "qual meu próximo compromisso?"
Detalhes: core/integracoes.py."""
from __future__ import annotations

from core import integracoes as I


def agenda_google(parameters: dict, player=None) -> str:
    acao = str(parameters.get("action") or "query").strip().lower()
    try:
        if acao in ("setup", "configurar"):
            return "[done] " + I.agenda_configurar(str(parameters.get("url") or ""))
        return I.agenda_consultar(str(parameters.get("period") or "hoje"))
    except I.ErroIntegracao as e:
        return f"[failed] {e}"
    except Exception as e:
        return f"[failed] Agenda: {e}"


TOOL = {
    "name": "agenda_google",
    "description": (
        "CALENDAR (Google Calendar / any .ics link, read-only): action=query with period hoje | amanha | semana | "
        "proximo ('o que tenho hoje?', 'meus compromissos da semana', 'qual meu próximo compromisso?'); "
        "action=setup with url (the secret iCal address). For reminders/alarms use the reminder tool instead."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "query | setup"},
            "period": {"type": "STRING", "description": "For query: hoje | amanha | semana | proximo"},
            "url": {"type": "STRING", "description": "For setup: the https iCal address"},
        },
        "required": ["action"],
    },
    "handler": agenda_google,
}
