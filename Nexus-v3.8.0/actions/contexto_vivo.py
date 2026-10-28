"""Consciência de contexto: o NEXUS avisa de reunião chegando, anexo esquecido e erro na tela. Desligado por padrão; local."""
from memory import config_manager as CM


def contexto_vivo(parameters: dict, **_kw) -> str:
    acao = str(parameters.get("action") or "status").strip().lower()
    rec = str(parameters.get("feature") or "context").strip().lower()
    chave = "contexto_ocr" if rec in ("ocr", "screen_text") else "contexto_vivo"
    if acao in ("on", "off", "ligar", "desligar"):
        ligar = acao in ("on", "ligar")
        if chave == "contexto_ocr" and ligar:
            from core import ocr
            if not ocr.disponivel():
                return "[failed] Para ler o texto da tela falta: " + ocr.faltando()
        CM._save_flag(chave, ligar)
        extra = " Nada da tela sai do PC e nada é guardado." if ligar else ""
        return f"[done] {'Leitura da tela (OCR)' if chave == 'contexto_ocr' else 'Contexto vivo'}: {'ligado' if ligar else 'desligado'}.{extra}"
    k = CM.load_api_keys()
    return (f"Contexto vivo: {'ligado' if k.get('contexto_vivo') else 'desligado'}; "
            f"leitura da tela por OCR: {'ligada' if k.get('contexto_ocr') else 'desligada'}. Respeita o modo foco.")


TOOL = {
    "name": "live_context",
    "description": ("Context awareness (off by default, local): warns about a meeting in 3 minutes, a forgotten attachment, an error on "
                    "screen. action=status|on|off; feature=context (agenda + window titles) or ocr (also reads the screen text locally)."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["status", "on", "off"]}, "feature": {"type": "STRING", "enum": ["context", "ocr"]}},
        "required": ["action"]},
    "handler": contexto_vivo,
}
