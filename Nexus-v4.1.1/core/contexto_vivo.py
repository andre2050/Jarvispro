"""core/contexto_vivo.py — consciência de contexto (NEXUS Ultra 2026 3.8).

Olha, de tempos em tempos, o que está acontecendo (próximo compromisso da agenda, título da janela ativa e, se você ligar,
o texto da tela por OCR) e só fala quando há algo útil: "reunião em 3 minutos", "você escreveu 'segue em anexo' mas não vejo
anexo", "apareceu um erro na tela, quer que eu veja?". Desligado por padrão (opt-in), 100% local: nada da tela sai do PC e
nada é guardado. Respeita o modo foco e o silêncio por reunião/tela cheia. Cada aviso tem cooldown e não repete.
As fontes são injetadas (`agenda`, `janela`, `tela`): nos testes são falsas.
Limite honesto: sem OCR só enxerga o título da janela; com OCR o texto da tela é lido por Tesseract e erra.
"""
from __future__ import annotations

import re
import sys
import time
from datetime import datetime, timedelta
from typing import Callable

COOLDOWN_S = 900.0
_ERRO_JANELA = re.compile(r"(n[aã]o est[aá] respondendo|not responding|\berro\b|\berror\b|falha|crash|exception|fatal)", re.I)
_ERRO_TELA = re.compile(r"(Traceback \(most recent call last\)|\b\w+Error:|\bException\b|Falha cr[ií]tica|n[aã]o foi poss[ií]vel|"
                        r"HTTP (4|5)\d\d|\b(404|500|502|503)\b.{0,20}(not found|error|erro)|Access is denied|Acesso negado)", re.I)
_MENCIONA_ANEXO = re.compile(r"(segue em anexo|em anexo|anexei|anexado|estou anexando|segue anexo|attached|attachment|i('| ha)ve attached)", re.I)
_TEM_ARQUIVO = re.compile(r"\.(pdf|docx?|xlsx?|pptx?|png|jpe?g|zip|rar|csv|txt)\b", re.I)
_COMPOSICAO = re.compile(r"(novo e-?mail|nova mensagem|rascunho|compose|new message|draft|responder|reply|escrever)", re.I)


def reuniao_em_breve(eventos: list[dict], agora: datetime, minutos: int = 3) -> str:
    """Compromisso com hora marcada que começa nos próximos `minutos` (e ainda não começou)."""
    for e in eventos or []:
        try:
            if e.get("dia_inteiro"):
                continue
            falta = (e["inicio"] - agora).total_seconds() / 60
            if 0 < falta <= minutos + 0.5:
                return f"“{str(e.get('titulo', 'compromisso'))[:50]}” começa em {max(1, round(falta))} min."
        except Exception:
            continue
    return ""


def anexo_esquecido(titulo_janela: str, texto_tela: str) -> str:
    if not texto_tela or not _COMPOSICAO.search(titulo_janela or ""):
        return ""
    if _MENCIONA_ANEXO.search(texto_tela) and not _TEM_ARQUIVO.search(texto_tela):
        return "Você escreveu que está mandando um anexo, mas não vejo nenhum arquivo anexado nesse e-mail."
    return ""


def erro_na_tela(titulo_janela: str, texto_tela: str) -> str:
    if _ERRO_TELA.search(texto_tela or ""):
        return "Apareceu uma mensagem de erro na tela. Quer que eu leia e explique?"
    if _ERRO_JANELA.search(titulo_janela or ""):
        return f"A janela “{titulo_janela[:40]}” parece ter dado erro ou travado."
    return ""


class Observador:
    def __init__(self, agenda: Callable[[], list[dict]] | None = None, janela: Callable[[], str] | None = None,
                 tela: Callable[[], str] | None = None, silencio: Callable[[], str | None] | None = None,
                 relogio: Callable[[], float] = time.monotonic, cooldown: float = COOLDOWN_S):
        self.agenda, self.janela, self.tela = agenda, janela, tela
        self.silencio = silencio or (lambda: None)
        self.relogio, self.cooldown = relogio, cooldown
        self._vistos: dict[str, float] = {}

    def _novo(self, chave: str) -> bool:
        agora = self.relogio()
        if agora - self._vistos.get(chave, -1e12) < self.cooldown:
            return False
        self._vistos[chave] = agora
        return True

    def passo(self, agora: datetime | None = None) -> list[str]:
        """Devolve os avisos novos (lista vazia quase sempre)."""
        if self.silencio():
            return []
        agora = agora or datetime.now().astimezone()
        out: list[str] = []
        titulo = ""
        try:
            titulo = (self.janela() if self.janela else "") or ""
        except Exception:
            pass
        try:
            if self.agenda:
                msg = reuniao_em_breve(self.agenda(), agora)
                if msg and self._novo("reuniao:" + msg):
                    out.append(msg)
        except Exception:
            pass
        texto = ""
        if self.tela:
            try:
                texto = self.tela() or ""
            except Exception:
                texto = ""
        for fn, nome in ((anexo_esquecido, "anexo"), (erro_na_tela, "erro")):
            try:
                msg = fn(titulo, texto)
                if msg and self._novo(f"{nome}:{titulo[:30]}"):
                    out.append(msg)
            except Exception:
                pass
        return out


# ── fontes reais ─────────────────────────────────────────────────────────────
def titulo_ativo() -> str:
    if not sys.platform.startswith("win"):
        return ""
    try:
        import ctypes
        u = ctypes.windll.user32
        h = u.GetForegroundWindow()
        n = u.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(h, buf, n + 1)
        return buf.value
    except Exception:
        return ""


_cache_agenda = {"t": -1e9, "ev": []}


def agenda_real() -> list[dict]:
    """Eventos de agora a +15 min; baixa o .ics no máximo a cada 5 minutos."""
    from zoneinfo import ZoneInfo
    from core import integracoes as I
    agora = time.monotonic()
    tz = ZoneInfo("America/Sao_Paulo")
    if agora - _cache_agenda["t"] > 300:
        d = datetime.now(tz)
        try:
            _cache_agenda["ev"] = I.interpretar_ics(I._baixar_ics(), d, d + timedelta(hours=6), tz)
        except Exception:
            _cache_agenda["ev"] = []
        _cache_agenda["t"] = agora
    return _cache_agenda["ev"]


def tela_ocr() -> str:
    """Texto da tela por OCR local (precisa de mss, Pillow e Tesseract). '' se faltar algo."""
    try:
        import io
        import mss
        import PIL.Image
        from core import ocr
        if not ocr.disponivel():
            return ""
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0])
            img = PIL.Image.frombytes("RGB", shot.size, shot.rgb)
        return ocr._ocr(img)[:4000]
    except Exception:
        return ""


def flags() -> dict:
    try:
        from memory.config_manager import load_api_keys
        k = load_api_keys()
        return {"ligado": bool(k.get("contexto_vivo", False)), "ocr": bool(k.get("contexto_ocr", False))}
    except Exception:
        return {"ligado": False, "ocr": False}
