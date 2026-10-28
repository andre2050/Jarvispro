"""Abrir pasta, arquivo ou programa pelo nome. Ver core/abrir_tudo.py."""
from core import abrir_tudo as A


def abrir_qualquer(parameters: dict, abridor=None, app=None, **_kw) -> str:
    try:
        return A.abrir(str(parameters.get("target") or ""), abridor, app)
    except Exception as e:
        return f"[failed] Não consegui abrir: {str(e)[:100]}"


TOOL = {
    "name": "open_anything",
    "description": ("Open a folder (Downloads, Documents, Pictures…), a file (by path or by name, searched in the user's main folders) or a program by name. "
                    "Refuses files that run code (.exe .bat .ps1 .lnk .docm …) by path and network paths; programs go through open_app."),
    "parameters": {"type": "OBJECT", "properties": {"target": {"type": "STRING"}}, "required": ["target"]},
    "handler": abrir_qualquer,
}
