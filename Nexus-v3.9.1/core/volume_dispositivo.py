"""
core/volume_dispositivo.py — 🎚️ volume POR DISPOSITIVO (NEXUS Ultra 2026 1.5).

O controle de volume da janela de áudio pertence ao alto-falante que você
escolheu para o NEXUS — não ao que o Windows chama de "padrão" naquele momento.
Usa o pycaw (já nas dependências do Windows). Em outro sistema, não faz nada.
"""
from __future__ import annotations

import platform
import re

_OS = platform.system()


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", str(t or "").strip().lower())


def _volume_de(obj):
    from ctypes import POINTER, cast
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import IAudioEndpointVolume
    ev = getattr(obj, "EndpointVolume", None)      # pycaw novo
    if ev is not None:
        return ev
    dev = getattr(obj, "_dev", obj)
    iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(iface, POINTER(IAudioEndpointVolume))


def _endpoint(nome: str):
    """O controle de volume do alto-falante com esse nome ('' = o padrão)."""
    if _OS != "Windows":
        return None
    try:
        import comtypes
        try:
            comtypes.CoInitialize()
        except Exception:
            pass
        from pycaw.pycaw import AudioUtilities
        alvo = _norm(nome)
        if not alvo or alvo.startswith("padrão") or alvo.startswith("padrao") or alvo == "default":
            return _volume_de(AudioUtilities.GetSpeakers())
        # o nome do sounddevice pode vir cortado (MME: 31 letras) ou com " (sufixo)"
        melhor = None
        for d in AudioUtilities.GetAllDevices():
            try:
                fn = _norm(getattr(d, "FriendlyName", "") or "")
                estado = getattr(d, "state", None)
                if not fn:
                    continue
                if estado is not None and estado != 1 and "active" not in str(estado).lower():
                    continue                      # desconectado / desativado
                if fn == alvo or fn.startswith(alvo) or alvo.startswith(fn[:28]):
                    melhor = d
                    break
            except Exception:
                continue
        if melhor is None:
            return None
        try:
            return _volume_de(melhor)
        except Exception:
            enum = AudioUtilities.GetDeviceEnumerator()
            return _volume_de(enum.GetDevice(melhor.id))
    except Exception as e:
        print(f"[Volume] dispositivo '{nome}': {e}")
        return None


def ler(nome: str) -> int | None:
    vol = _endpoint(nome)
    if vol is None:
        return None
    try:
        return int(round(vol.GetMasterVolumeLevelScalar() * 100))
    except Exception:
        return None


def definir(nome: str, pct: int) -> bool:
    vol = _endpoint(nome)
    if vol is None:
        return False
    try:
        vol.SetMasterVolumeLevelScalar(max(0, min(100, int(pct))) / 100.0, None)
        return True
    except Exception as e:
        print(f"[Volume] não ajustou '{nome}': {e}")
        return False
