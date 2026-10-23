"""Escolha de voz do sistema (pyttsx3): o NEXUS fala com voz MASCULINA por padrão."""
from __future__ import annotations

# Nomes de vozes masculinas comuns no Windows/macOS/Linux (português e outros idiomas)
_MASCULINAS = ("daniel", "antonio", "antônio", "felipe", "ricardo", "fernando", "paulo", "luciano",
               "male", "masculin", "homem", "david", "mark", "george", "guy", "alvaro", "álvaro",
               "jorge", "diego", "thomas", "paul", "henri", "yannick", "hans", "stefan")
_FEMININAS = ("maria", "heloisa", "heloísa", "francisca", "luciana", "female", "feminin", "zira",
              "hazel", "susan", "helena", "paulina", "sabina", "hortense", "julia")


def _texto(v) -> str:
    return f"{getattr(v, 'id', '')} {getattr(v, 'name', '')} {getattr(v, 'languages', '')}".lower()


def escolher_voz(voices, alvos: tuple[str, ...]) -> str | None:
    """Entre as vozes do idioma (`alvos` = pedaços do nome/idioma), prefere uma masculina.

    Ordem: idioma + masculina → idioma que não seja claramente feminina → primeira do idioma."""
    do_idioma = [v for v in voices if any(a in _texto(v) for a in alvos)]
    if not do_idioma:
        return None
    for v in do_idioma:
        if any(m in _texto(v) for m in _MASCULINAS):
            return v.id
    for v in do_idioma:
        if not any(f in _texto(v) for f in _FEMININAS):
            return v.id
    return do_idioma[0].id
