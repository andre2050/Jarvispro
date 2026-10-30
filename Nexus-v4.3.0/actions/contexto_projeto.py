"""Contexto de projeto (4.0). Ver core/contexto_projeto.py."""
from core import contexto_projeto as CP


def contexto_projeto(parameters: dict, **_kw) -> str:
    nome = str(parameters.get("project") or parameters.get("text") or "").strip()
    if not nome:
        lista = CP.projetos()
        return "Projetos: " + ", ".join(p["nome"] for p in lista) if lista else "Nenhum projeto cadastrado."
    return CP.briefing(nome) if CP.qual_projeto(nome) else (CP.para_a_conversa(nome) or f"Não achei projeto com “{nome}”.")


TOOL = {
    "name": "project_context",
    "description": "Progress and relevant info for one of the user's projects (next step, days idle, hours, changed files, notes that mention it). project = name or a sentence that mentions it; empty = list projects. Read-only.",
    "parameters": {"type": "OBJECT", "properties": {"project": {"type": "STRING"}}},
    "handler": contexto_projeto,
}
