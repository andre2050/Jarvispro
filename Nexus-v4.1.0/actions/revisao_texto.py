"""Revisão de texto antes de enviar. Ver core/revisao_texto.py."""
from core import revisao_texto as R


def revisar_texto(parameters: dict, llm=None, **_kw) -> str:
    texto, tom = str(parameters.get("text") or ""), str(parameters.get("tone") or "").strip().lower()
    if tom and llm is None:
        try:
            from core import hibrido
            llm = lambda p: hibrido.completar(p, nuvem=lambda t: "", local=lambda t: "", auditar=False)[0]
        except Exception:
            llm = None
    return R.revisar(texto, tom, llm)


TOOL = {
    "name": "review_text",
    "description": "Review a Portuguese text before sending: rule-based issues (repeated words, gerundismo, long sentences, common mistakes) and, if tone is given (formal|amigavel|direto|neutro), a rewrite suggestion. Does not send anything.",
    "parameters": {"type": "OBJECT", "properties": {"text": {"type": "STRING"}, "tone": {"type": "STRING", "enum": ["formal", "amigavel", "direto", "neutro"]}}, "required": ["text"]},
    "handler": revisar_texto,
}
