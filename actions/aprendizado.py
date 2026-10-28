"""Aprendizado contínuo da rotina (opt-in, local). Ver core/aprendizado.py."""
from core import aprendizado as A


def aprendizado(parameters: dict, **_kw) -> str:
    acao = str(parameters.get("action") or "summary").strip().lower()
    if acao in ("on", "ligar"):
        A.ligar(True)
        return "[done] Aprendizado da rotina ligado. Guardo só contagens por horário, neste PC."
    if acao in ("off", "desligar"):
        A.ligar(False)
        return "[done] Desligado. O que já aprendi continua guardado até você mandar esquecer."
    if acao in ("forget", "esquecer"):
        A.esquecer()
        return "[done] Esqueci tudo o que tinha aprendido da sua rotina."
    if acao in ("export", "exportar"):
        return A.exportar()
    if acao in ("now", "agora"):
        l = A.agora_costuma()
        return "Nesta hora você costuma usar: " + ", ".join(l) if l else "Nada recorrente para este horário."
    try:
        from core import habits
        A.atualizar(habits._load())
    except Exception:
        pass
    return A.resumo()


TOOL = {
    "name": "routine_learning",
    "description": ("Opt-in, local-only learning of the user's routine (counts per time slot, 30-day decay, no content). "
                    "action=summary | on | off | now | export | forget. Never turn it on without the user asking."),
    "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING", "enum": ["summary", "on", "off", "now", "export", "forget"]}}},
    "handler": aprendizado,
}
