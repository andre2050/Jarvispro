"""Presença por voz: "liga a presença com a câmera", "o IP do meu celular é 192.168.0.15", "desliga a presença"."""
from __future__ import annotations


def presenca(parameters: dict, player=None) -> str:
    from core import presenca as P
    acao = str(parameters.get("action") or "status").strip().lower()
    if acao in ("on", "ligar"):
        novo = {"ativo": True}
        ip = parameters.get("phone_ip")
        if ip:
            ok = P.ip_valido(str(ip))
            if not ok:
                return "[failed] Esse IP não é de rede local (ex.: 192.168.0.15). Por segurança só testo aparelhos da sua casa."
            novo["celular_ip"] = ok
        if parameters.get("camera") is not None:
            novo["camera"] = str(parameters.get("camera")).lower() in ("1", "true", "yes", "sim")
        cfg = P.salvar(novo)
        if not (cfg.get("camera") or cfg.get("celular_ip")):
            return "[done] Presença ligada, mas falta escolher o sensor: diga o IP do celular ou 'com a câmera'."
        return "[done] " + P.texto_estado(cfg) + " Eu acordo e dou um oi quando você chegar."
    if acao in ("off", "desligar"):
        P.salvar({"ativo": False})
        return "[done] Presença desligada."
    return P.texto_estado()


TOOL = {
    "name": "presenca",
    "description": ("Wake NEXUS when the user arrives (opt-in, local only). action=on with phone_ip (a LAN address of "
                    "the user's phone, pinged on the home network) and/or camera=true (looks at one frame, only asks "
                    "'is there a face?', never saves or sends it); action=off; action=status. Use for 'liga a "
                    "presença', 'acorda quando eu chegar', 'desliga a presença'. Answer in Portuguese."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["on", "off", "status"]},
            "phone_ip": {"type": "STRING", "description": "LAN IP of the phone, e.g. 192.168.0.15"},
            "camera": {"type": "BOOLEAN", "description": "use the webcam face check"},
        },
        "required": [],
    },
    "handler": presenca,
}
