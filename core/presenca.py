"""Voz acordando por presença (3.7) — opt-in, tudo local.

Dois sensores, você escolhe (ou os dois):
  • CELULAR por perto: o PC testa se o IP do seu celular responde na rede da casa (ping). Nenhuma imagem, nenhum dado.
  • CÂMERA: a cada alguns segundos olha UM quadro e só pergunta "tem rosto?" (detector do OpenCV). O quadro fica na
    memória por um instante e é descartado — nunca é gravado, enviado nem mostrado.

Quando você CHEGA (de ausente para presente, confirmado por vários testes seguidos) o NEXUS acorda e dá um oi curto,
no máximo uma vez a cada 30 minutos. Desligado por padrão: "liga a presença" / "desliga a presença".
"""
from __future__ import annotations

import ipaddress
import json
import platform
import re
import subprocess
import time
from pathlib import Path
from core.protecao import engolida as _engolida

_BASE = Path(__file__).resolve().parent.parent
ARQ = _BASE / "memory" / "presenca.json"
CONFIRMAR = 2            # testes seguidos para valer
AUSENTE_APOS = 600       # segundos sem sinal para considerar que você saiu
PAUSA_OI = 1800          # no máximo um oi a cada 30 min
INTERVALO = 20           # segundos entre testes


def carregar(arq: Path | None = None) -> dict:
    try:
        d = json.loads(Path(arq or ARQ).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def salvar(novo: dict, arq: Path | None = None) -> dict:
    arq = Path(arq or ARQ)
    d = carregar(arq)
    d.update(novo)
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(d), encoding="utf-8")
    return d


def ip_valido(txt: str) -> str:
    """Só IP de rede local (privado): nunca testa endereços da internet."""
    try:
        ip = ipaddress.ip_address(str(txt).strip())
    except ValueError:
        return ""
    return str(ip) if ip.is_private and not ip.is_loopback else ""


def celular_responde(ip: str, executar=None) -> bool:
    ip = ip_valido(ip)
    if not ip:
        return False
    win = platform.system() == "Windows"
    cmd = ["ping", "-n", "1", "-w", "1500", ip] if win else ["ping", "-c", "1", "-W", "2", ip]
    try:
        r = (executar or subprocess.run)(cmd, capture_output=True, timeout=6,
                                         **({"creationflags": 0x08000000} if win else {}))
        return getattr(r, "returncode", 1) == 0
    except Exception:
        return False


def rosto_na_camera(indice: int = 0, abrir=None) -> bool:
    """Um quadro, um 'tem rosto?', e o quadro é descartado."""
    try:
        import cv2
    except ImportError:
        return False
    cap = (abrir or cv2.VideoCapture)(indice)
    try:
        if not cap.isOpened():
            return False
        ok, quadro = cap.read()
        if not ok or quadro is None:
            return False
        cinza = cv2.cvtColor(quadro, cv2.COLOR_BGR2GRAY)
        det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        achou = len(det.detectMultiScale(cinza, 1.2, 5, minSize=(60, 60))) > 0
        del quadro, cinza
        return achou
    except Exception:
        return False
    finally:
        try:
            cap.release()
        except Exception:
            _engolida("core/presenca.py:93")


def sensor_atual(cfg: dict | None = None):
    """Função sem argumentos → bool, montada com o que está ligado. None se nada está ligado."""
    cfg = cfg if cfg is not None else carregar()
    if not cfg.get("ativo"):
        return None
    fontes = []
    if cfg.get("celular_ip"):
        fontes.append(lambda ip=cfg["celular_ip"]: celular_responde(ip))
    if cfg.get("camera"):
        fontes.append(lambda: rosto_na_camera(int(cfg.get("camera_indice", 0))))
    if not fontes:
        return None
    return lambda: any(f() for f in fontes)


class Presenca:
    """Máquina de estados: ausente → presente só depois de CONFIRMAR testes seguidos; ausente depois de AUSENTE_APOS."""

    def __init__(self, confirmar: int = CONFIRMAR, ausente_apos: float = AUSENTE_APOS, pausa_oi: float = PAUSA_OI):
        self.confirmar, self.ausente_apos, self.pausa_oi = confirmar, ausente_apos, pausa_oi
        self.presente = False
        self._seguidos = 0
        self._ultimo_sinal = 0.0
        self._ultimo_oi = -1e12

    def passo(self, viu: bool, agora: float | None = None) -> str:
        """Devolve 'chegou' quando é hora de acordar/dar oi; 'saiu'; ou ''."""
        agora = time.monotonic() if agora is None else agora
        if viu:
            self._ultimo_sinal = agora
            self._seguidos += 1
            if not self.presente and self._seguidos >= self.confirmar:
                self.presente = True
                if agora - self._ultimo_oi >= self.pausa_oi:
                    self._ultimo_oi = agora
                    return "chegou"
            return ""
        self._seguidos = 0
        if self.presente and agora - self._ultimo_sinal >= self.ausente_apos:
            self.presente = False
            return "saiu"
        return ""


def texto_estado(cfg: dict | None = None) -> str:
    cfg = cfg if cfg is not None else carregar()
    if not cfg.get("ativo"):
        return "Presença desligada."
    fontes = []
    if cfg.get("celular_ip"):
        fontes.append(f"celular em {cfg['celular_ip']}")
    if cfg.get("camera"):
        fontes.append("câmera (só detecta rosto, não grava)")
    return "Presença ligada" + (": " + " e ".join(fontes) if fontes else " (sem sensor escolhido).")
