"""Modelo local/híbrido: ver o estado, trocar o modo (auto, privado, rapido, economico, offline) e testar a rota."""
from core import hibrido as H


def modelo_hibrido(parameters: dict, **_kw) -> str:
    acao = str(parameters.get("action") or "status").strip().lower()
    try:
        if acao in ("set", "definir"):
            return f"[done] Modo do modelo: {H.definir_modo(str(parameters.get('mode') or ''))}."
        if acao in ("test", "testar"):
            t = str(parameters.get("text") or "")
            r = H.rotear(t, True, H.local_disponivel(), H.modo())
            return f"Esse pedido iria para: {r['destino']} ({r['motivo']})."
        loc = H.local_disponivel()
        return (f"Modo: {H.modo()}. Modelo local: {'rodando' if loc else 'não encontrado (instale o Ollama e baixe um modelo, ex.: qwen2.5)'}. "
                "A voz ao vivo continua na nuvem; planejamento e textos usam a rota.")
    except Exception as e:
        return f"[failed] {e}"


TOOL = {
    "name": "hybrid_model",
    "description": ("Local/cloud model router. action=status; set (mode: auto|privado|rapido|economico|offline); "
                    "test (text): where a request would go. Sensitive content stays local in auto mode."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["status", "set", "test"]},
        "mode": {"type": "STRING"}, "text": {"type": "STRING"}}, "required": ["action"]},
    "handler": modelo_hibrido,
}
