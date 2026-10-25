"""Anomalias do PC — NEXUS Ultra 2026 2.3. Veja core/anomalia.py.

Por voz: "o meu PC está estranho?"   "treina o detector de anomalias"   "como está o detector do PC?"
"""
from __future__ import annotations

from core import anomalia as A


def anomalia_pc(parameters: dict, player=None) -> str:
    acao = str((parameters or {}).get("action") or "check").strip().lower()
    if acao in ("train", "treinar"):
        try:
            r = A.treinar(log=lambda *a: None)
        except ValueError as e:
            return f"[failed] {e}"
        return f"[done] Aprendi o normal do seu PC com {r['amostras']} medidas. Vou avisar quando destoar."
    if acao in ("status",):
        n = len(A.ler())
        if A.treinado():
            r = A.relatorio()
            return f"[done] Detector ativo (treinado em {r['treinado_em']} com {r['amostras']} medidas); {n} medidas guardadas."
        return (f"[done] Ainda aprendendo: {n} de {A.MIN_AMOSTRAS} medidas (uma por minuto com o NEXUS aberto).")
    if acao in ("check", "agora"):
        A.amostrar()
        import time
        time.sleep(1.0)
        m = A.amostrar()
        if not m:
            return "[failed] Não consegui medir o PC agora (a biblioteca psutil está instalada?)."
        r = A.avaliar(m)
        if r is None:
            return (f"[done] Ainda não aprendi o seu normal ({len(A.ler())} de {A.MIN_AMOSTRAS} medidas). "
                    f"Agora: CPU {m['cpu']:.0f}%, memória {m['memoria']:.0f}%.")
        if r["pontuacao"] < 1.0:
            return f"[done] O PC está dentro do seu normal (CPU {m['cpu']:.0f}%, memória {m['memoria']:.0f}%)."
        return "[done] Está fora do seu normal: " + "; ".join(t for _, t in r["culpados"]) + "."
    return "Ação desconhecida. Use check, status ou train."


TOOL = {
    "name": "anomalia_pc",
    "description": (
        "Neural-network anomaly detector for this PC (learns the user's normal CPU/memory/disk/network). "
        "action=check ('meu PC está estranho?'), status, train. It only observes; it never closes anything."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "check | status | train"}}, "required": ["action"]},
    "handler": anomalia_pc,
}
