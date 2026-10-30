"""Consciência de contexto: o NEXUS avisa de reunião chegando, anexo esquecido e erro na tela. Desligado por padrão; local."""
from memory import config_manager as CM


def _llm(prompt: str) -> str:
    from core import gemini
    return gemini.text(prompt, tier=gemini.SMART, timeout_ms=45_000)


def contexto_vivo(parameters: dict, llm=None, tela=None, **_kw) -> str:
    acao = str(parameters.get("action") or "status").strip().lower()
    if acao in ("fix", "diagnosticar", "corrigir"):
        from core import contexto_vivo as CV
        from core import copiloto
        texto = (tela or CV.tela_ocr)()
        if not texto:
            return "[failed] Não consegui ler a tela (precisa do OCR: Tesseract, mss e Pillow)."
        d = copiloto.diagnosticar(texto, CV.titulo_ativo(), llm or _llm)
        if not d:
            return "Não achei um erro claro na tela."
        copiloto.ofertas.guardar(d)
        return "[done] Diga isto ao usuário e espere a resposta (não faça nada na tela ainda): " + copiloto.fala(d)
    if acao in ("accept_fix", "aceitar"):
        from core import copiloto
        o = copiloto.ofertas.pegar()
        if not o or not o.get("objetivo"):
            return "Não há uma correção oferecida esperando (ou já passou de 10 minutos)."
        copiloto.ofertas.limpar()
        from actions import uso_computador
        return uso_computador.uso_computador({"action": "start", "goal": o["objetivo"]})
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
                    "screen. action=status|on|off; fix: read the screen text (OCR), diagnose the error and OFFER a fix, then wait; accept_fix: ONLY after the user says yes, starts the on-screen fix (computer use still asks its own CONFIRM); feature=context (agenda + window titles) or ocr (also reads the screen text locally)."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["status", "on", "off", "fix", "accept_fix"]}, "feature": {"type": "STRING", "enum": ["context", "ocr"]}},
        "required": ["action"]},
    "handler": contexto_vivo,
}
