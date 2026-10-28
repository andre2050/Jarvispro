"""Voz mais natural: liga/desliga a leitura de emoção na sua voz e a interrupção por voz. Tudo local, desligado por padrão."""
from memory import config_manager as CM

_CHAVES = {"emotion": "voz_emocao", "emocao": "voz_emocao", "interrupt": "voz_interrupcao", "interrupcao": "voz_interrupcao"}


def voz_natural(parameters: dict, **_kw) -> str:
    acao = str(parameters.get("action") or "status").strip().lower()
    rec = str(parameters.get("feature") or "").strip().lower()
    k = CM.load_api_keys()
    if acao in ("calibrate", "calibrar"):
        from core import voz_emocao as VE
        try:
            return "[done] " + VE.tracker.iniciar_calibracao(rec or "neutro") + " Quando terminar, peça para concluir a calibração."
        except ValueError as e:
            return f"[failed] {e}"
    if acao in ("finish_calibration", "concluir"):
        from core import voz_emocao as VE
        return VE.tracker.concluir_calibracao()
    if acao in ("reset_calibration", "limpar"):
        from core import voz_emocao as VE
        VE.tracker.limpar_calibracao()
        return "[done] Calibração apagada; volto a usar a sua média."
    if acao in ("on", "off", "ligar", "desligar"):
        chave = _CHAVES.get(rec)
        if not chave:
            return "[failed] Diga qual: emotion (emoção na voz) ou interrupt (interromper falando)."
        CM._save_flag(chave, acao in ("on", "ligar"))
        try:
            from core import voz_emocao
            voz_emocao._cache_cfg["t"] = -1e9
        except Exception:
            pass
        extra = " Teste num ambiente com fone; com caixa de som o eco pode atrapalhar." if chave == "voz_interrupcao" and acao in ("on", "ligar") else ""
        return f"[done] {rec}: {'ligado' if acao in ('on', 'ligar') else 'desligado'}.{extra}"
    return (f"Emoção na voz: {'ligada' if k.get('voz_emocao') else 'desligada'}. "
            f"Interromper falando: {'ligado' if k.get('voz_interrupcao') else 'desligado'}.")


TOOL = {
    "name": "natural_voice",
    "description": ("Settings of the natural-voice features (local, off by default): feature=emotion reads stress/tiredness/hesitation "
                    "in the user's voice to adapt answers; feature=interrupt lets the user cut NEXUS off by talking. "
                    "action=status|on|off. Guided calibration: calibrate (feature=neutro|cansado|agitado: the user speaks ~8 short phrases in that state), finish_calibration, reset_calibration; 2 minutes make the emotion reading use the user's OWN limits."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["status", "on", "off", "calibrate", "finish_calibration", "reset_calibration"]},
        "feature": {"type": "STRING", "enum": ["emotion", "interrupt", "neutro", "cansado", "agitado"]}},
        "required": ["action"]},
    "handler": voz_natural,
}
