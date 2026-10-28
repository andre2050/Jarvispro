"""Adaptação contínua ao uso (opt-in, local). Ver core/adaptacao.py."""
from core import adaptacao as A


def adaptacao(parameters: dict, **_kw) -> str:
    acao = str(parameters.get("action") or "summary").strip().lower()
    b = str(parameters.get("knob") or "").strip().lower()
    try:
        if acao in ("on", "ligar"):
            A.ligar(True)
            return "[done] Adaptação ligada: vou ajustar o quanto falo e aviso conforme você usa, só com contagens, neste PC."
        if acao in ("off", "desligar"):
            A.ligar(False)
            return "[done] Adaptação desligada. Os ajustes atuais param de valer."
        if acao in ("lock", "travar"):
            return "[done] " + A.travar(b, parameters.get("value"))
        if acao in ("unlock", "destravar"):
            A.destravar(b)
            return "[done] Destravado."
        if acao in ("undo", "reverter"):
            return "[done] " + A.reverter()
        if acao in ("forget", "esquecer"):
            A.esquecer()
            return "[done] Zerei o que aprendi do seu uso."
        for f in A.ajustar():
            pass
        return A.resumo()
    except ValueError as e:
        return f"[failed] {e}"


TOOL = {
    "name": "adaptation",
    "description": "Continuous adaptation to how the user uses NEXUS (opt-in, local, counts only). action=summary | on | off | lock (knob verbosidade|proatividade, optional value 1-5) | unlock | undo | forget. Never turn on without the user asking.",
    "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING", "enum": ["summary", "on", "off", "lock", "unlock", "undo", "forget"]},
                                                    "knob": {"type": "STRING"}, "value": {"type": "INTEGER"}}},
    "handler": adaptacao,
}
