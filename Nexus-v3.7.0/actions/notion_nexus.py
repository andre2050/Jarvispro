"""Notion (3.5): cria notas no seu banco de dados do Notion e procura nas suas páginas.

Por voz:  "configura o Notion" (token da integração + link do banco)   "anota no Notion: ideia do app"
          "procura no Notion algo sobre viagem"
Detalhes: core/integracoes.py."""
from __future__ import annotations

from core import integracoes as I


def notion_nexus(parameters: dict, player=None) -> str:
    acao = str(parameters.get("action") or "create").strip().lower()
    try:
        if acao in ("setup", "configurar"):
            return "[done] " + I.notion_configurar(str(parameters.get("token") or ""), str(parameters.get("database") or ""))
        if acao in ("create", "criar", "add"):
            return "[done] " + I.notion_criar(str(parameters.get("title") or ""), str(parameters.get("text") or ""))
        if acao in ("search", "buscar"):
            return I.notion_buscar(str(parameters.get("query") or ""))
    except I.ErroIntegracao as e:
        return f"[failed] {e}"
    except Exception as e:
        return f"[failed] Notion: {e}"
    return "Ação desconhecida. Use setup, create ou search."


TOOL = {
    "name": "notion_nexus",
    "description": (
        "NOTION: action=create with title (+ optional text) adds a page to the user's Notion database "
        "('anota no Notion…'); action=search with query; action=setup with token and database (link or id). "
        "For local notes without Notion use quick_notes."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "create | search | setup"},
            "title": {"type": "STRING", "description": "For create: page title"},
            "text": {"type": "STRING", "description": "For create: page body (one paragraph per line)"},
            "query": {"type": "STRING", "description": "For search: what to look for"},
            "token": {"type": "STRING", "description": "For setup: integration token"},
            "database": {"type": "STRING", "description": "For setup: database link or id"},
        },
        "required": ["action"],
    },
    "handler": notion_nexus,
}
