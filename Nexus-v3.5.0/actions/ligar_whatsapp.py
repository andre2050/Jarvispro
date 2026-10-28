"""Ligar pelo WhatsApp por voz (NEXUS Ultra 2026 3.4) — a lógica fica em core/whatsapp_ligacao.py.

"Liga pro Marcos no WhatsApp"   "chamada de vídeo com a Maria"   "liga no zap pro 11 98888-7777"

Antes de ligar, o NEXUS mostra QUEM e QUAL NÚMERO na tela e espera o seu CONFIRMAR (uma ligação para a
pessoa errada não tem desfazer). Em Configurações você pode liberar a ligação direta para quem está
salvo nos contatos com o nome exato (preferência ``whatsapp_ligar_confirmar`` = falso).
"""
from __future__ import annotations

import threading


def _pref(chave: str, padrao):
    try:
        from core import preferences
        v = preferences.get(chave)
        return padrao if v is None else v
    except Exception:
        return padrao


def _contatos() -> list[dict]:
    try:
        from actions.contatos import _ler
        return _ler()
    except Exception:
        return []


def _executar(nome: str, numero: str, tipo: str, speak=None, player=None) -> str:
    from core import whatsapp_ligacao as WL
    ok, detalhe = WL.ligar(nome, numero, tipo)
    rotulo = "chamada de vídeo" if tipo == "video" else "ligação de voz"
    if ok and not detalhe:
        msg = f"Call started: {rotulo} with {nome} on WhatsApp."
    elif ok:
        msg = f"Call probably started ({rotulo} with {nome} on WhatsApp), but: {detalhe}."
    else:
        msg = f"The WhatsApp call to {nome} was NOT started: {detalhe}."
    if player is not None:
        try:
            player.write_log(f"SYS: 📞 {msg}")
        except Exception:
            pass
    if speak and not (ok and not detalhe):                  # só fala de novo quando algo não saiu perfeito
        try:
            speak(f"[CALL_RESULT] {msg} Tell the user in ONE short sentence, in their language. "
                  "Never say the call started unless this says so. Call no tools.")
        except Exception:
            pass
    return msg


def ligar_whatsapp(parameters: dict, player=None, speak=None) -> str:
    from core import confirm
    from core import whatsapp_ligacao as WL

    alvo = str(parameters.get("contact") or parameters.get("receiver") or "").strip()
    tipo = WL.normalizar_tipo(parameters.get("call_type") or "voz")
    quem = WL.resolver(alvo, _contatos(), str(_pref("whatsapp_ddi", "55")))
    if quem["erro"]:
        return f"[failed] {quem['erro']}"

    nome, numero = quem["nome"], quem["numero"]
    rotulo = "chamada de vídeo" if tipo == "video" else "ligação de voz"
    detalhe = f"{rotulo} · " + (f"+{numero}" if numero else "procurar pelo nome no WhatsApp")

    direto = quem["exato"] and bool(numero) and not bool(_pref("whatsapp_ligar_confirmar", True))
    if direto:
        threading.Thread(target=_executar, args=(nome, numero, tipo, speak, player),
                         daemon=True, name="nexus-whatsapp-call").start()
        return (f"status=calling contact={nome} type={rotulo}. Say ONE short sentence that you are calling "
                f"{nome} on WhatsApp now.")

    if confirm.pending_title():
        return "[failed] There is already a confirmation on screen; ask the user to answer it first."
    return confirm.request(
        "whatsapp_call", f"Ligar para {nome} no WhatsApp", detalhe,
        lambda: _executar(nome, numero, tipo, speak, player))


TOOL = {
    "name": "ligar_whatsapp",
    "description": (
        "Starts a WhatsApp VOICE or VIDEO CALL from the PC (WhatsApp Desktop). Use for 'liga pro Marcos no "
        "WhatsApp', 'faz uma chamada de vídeo com a Maria', 'liga no zap pro 11 98888-7777'. 'contact' is the "
        "person's name as the user said it, or a phone number; call_type is voz (default) or video. The name "
        "is looked up in the user's saved contacts. Usually a CONFIRM banner appears first: tell the user to "
        "confirm it on screen. Never say the call started unless the result says so. For TEXT messages use "
        "send_message instead."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "contact": {"type": "STRING", "description": "Who to call: a contact name or a phone number"},
            "call_type": {"type": "STRING", "description": "voz (default) | video"},
        },
        "required": ["contact"],
    },
    "handler": ligar_whatsapp,
}
