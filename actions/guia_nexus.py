"""Guia do NEXUS: 'o que você sabe fazer?'. Ver core/guia_nexus.py."""
from core import guia_nexus as G


def nexus_guide(parameters: dict, **_kw) -> str:
    return "[done] " + G.texto(str(parameters.get("topic") or ""))


TOOL = {
    "name": "nexus_guide",
    "description": ("Explains what NEXUS can do, in plain Portuguese, by topic. Use for 'what can you do?', 'o que você sabe fazer?', "
                    "'o que você faz com e-mail?', 'me ajuda a começar'. topic is optional (computer, internet, agenda, messages, memory, "
                    "create, media, money, nexus); empty = all topics."),
    "parameters": {"type": "OBJECT", "properties": {"topic": {"type": "STRING", "description": "Subject, e.g. e-mail, música, código. Empty = everything."}}},
    "handler": nexus_guide,
}
