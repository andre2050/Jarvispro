"""Cérebro local (Ollama) — NEXUS Ultra 2026 2.3. Veja core/cerebro_local.py.

Por voz: "prepara o cérebro local"   "o cérebro local está funcionando?"   "avalia o cérebro local"
         "o que o cérebro local faria com: abre o spotify"
"""
from __future__ import annotations

from core import cerebro_local as C


def cerebro_local(parameters: dict, player=None) -> str:
    p = parameters or {}
    acao = str(p.get("action") or "status").strip().lower()
    if acao in ("export", "exportar", "prepare", "preparar"):
        base = str(p.get("base") or C.BASE_PADRAO)
        try:
            r = C.exportar(base=base)
        except Exception as e:
            return f"[failed] Não consegui preparar: {e}"
        return (f"[done] Preparei {r['treino']} exemplos de treino e {r['validacao']} de validação em "
                f"{r['pasta']} (Modelfile, treinar_lora.py e LEIA-ME.txt). Passo a passo: instalar o Ollama, "
                f"'ollama pull {r['base']}' e 'ollama create {C.MODELO_PADRAO} -f Modelfile'. "
                "O treino de verdade (LoRA) precisa de GPU e roda no seu PC com o script gerado; eu não treino aqui.")
    if acao in ("status", "check"):
        s = C.status()
        if not s["ollama"]:
            return "O Ollama não está rodando neste PC (ou não está instalado). Instale em ollama.com e abra-o."
        if not s["modelo"]:
            return (f"O Ollama está rodando, mas o modelo '{C.MODELO_PADRAO}' ainda não foi criado. "
                    "Diga 'prepara o cérebro local' e siga o LEIA-ME.")
        return f"[done] Cérebro local pronto: o modelo '{C.MODELO_PADRAO}' está no Ollama."
    if acao in ("evaluate", "avaliar"):
        if not C.status()["modelo"]:
            return "O modelo ainda não está no Ollama. Veja o status."
        try:
            r = C.avaliar(limite=int(p.get("limit") or 60))
        except Exception as e:
            return f"[failed] {e}"
        return (f"[done] Em {r['frases']} frases de validação: acerto {r['acerto']:.0%}; "
                f"{r['erros_perigosos']} vez(es) faria algo errado; encaminhou certo {r['encaminhou_certo']} de "
                f"{r['para_encaminhar']} frases que não eram comando.")
    if acao in ("try", "testar"):
        frase = str(p.get("text") or "").strip()
        if not frase:
            return "Diga a frase para testar."
        try:
            d = C.decidir(frase)
        except Exception as e:
            return f"[failed] O cérebro local não respondeu: {e}"
        return ("[done] Ele encaminharia para o Gemini." if d is None
                else f"[done] Ele chamaria {d[0]} com {d[1]} (nada foi executado).")
    return "Ação desconhecida. Use export, status, evaluate ou try."


TOOL = {
    "name": "cerebro_local",
    "description": (
        "Local LLM 'brain' via Ollama that turns simple commands into function calls offline. "
        "action=export (prepare dataset, Modelfile and LoRA script — it cannot train here), status, "
        "evaluate (accuracy on validation phrases), try with text (shows what it WOULD do, never runs it)."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "export | status | evaluate | try"},
        "text": {"type": "STRING", "description": "For try: the phrase"},
        "base": {"type": "STRING", "description": "For export: Ollama base model (default qwen2.5:1.5b)"},
        "limit": {"type": "INTEGER", "description": "For evaluate: how many phrases"}},
        "required": ["action"]},
    "handler": cerebro_local,
}
