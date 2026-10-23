"""
core/voz_propria.py — ouvido e voz do MOTOR PRÓPRIO (NEXUS Pro 1.5).

OUVIDO
    Whisper (faster-whisper) no seu processador: ouve, transcreve e diz em que
    IDIOMA você falou. Offline depois do primeiro download do modelo.

VOZ (escolhida na Configuração do usuário › MOTOR DE VOZ)
    piper       neural, 100 % offline, ~50 idiomas (rhasspy/piper)
    elevenlabs  uma voz que fala todas as línguas, transmitida ao vivo
    edge        vozes neurais grátis da Microsoft (precisa de internet)
    sistema     a voz do Windows (SAPI), sempre disponível

A VOZ TE SEGUE
    Cada fala é sintetizada com a voz do idioma da resposta — fale em espanhol
    e o NEXUS responde com uma voz espanhola, no meio da conversa.

TOCADOR
    Toca no alto-falante escolhido para o NEXUS, mede o volume para a onda do
    HUD e para na hora quando você interrompe.
"""
from __future__ import annotations

import io
import json
import re
import threading
import time
import wave
from pathlib import Path
from typing import Callable, Iterator

import numpy as np

_BASE = Path(__file__).resolve().parent.parent
PASTA_PIPER = _BASE / "memory" / "piper_voices"
TAXA_SAIDA = 24000            # tudo é tocado a 24 kHz, como a voz do Gemini Live

# ── Mapas de voz por idioma ───────────────────────────────────────────────────
PIPER_VOZES = {
    "pt": "pt_BR-faber-medium", "en": "en_US-lessac-medium", "es": "es_ES-davefx-medium",
    "fr": "fr_FR-siwis-medium", "de": "de_DE-thorsten-medium", "it": "it_IT-riccardo-x_low",
    "ru": "ru_RU-irina-medium", "tr": "tr_TR-dfki-medium", "pl": "pl_PL-darkman-medium",
    "uk": "uk_UA-ukrainian_tts-medium", "zh": "zh_CN-huayan-medium", "nl": "nl_BE-nathalie-medium",
    "ar": "ar_JO-kareem-medium", "cs": "cs_CZ-jirka-medium", "el": "el_GR-rapunzelina-low",
    "fi": "fi_FI-harri-medium", "hu": "hu_HU-anna-medium", "ro": "ro_RO-mihai-medium",
    "sv": "sv_SE-nst-medium", "vi": "vi_VN-vais1000-medium", "ca": "ca_ES-upc_ona-medium",
    "da": "da_DK-talesyntese-medium", "no": "no_NO-talesyntese-medium", "ka": "ka_GE-natia-medium",
    "kk": "kk_KZ-issai-high", "sw": "sw_CD-lanfrica-medium", "fa": "fa_IR-amir-medium",
    "ne": "ne_NP-google-medium", "sr": "sr_RS-serbski_institut-medium", "sk": "sk_SK-lili-medium",
    "sl": "sl_SI-artur-medium", "is": "is_IS-bui-medium", "lb": "lb_LU-marylux-medium",
    "cy": "cy_GB-gwryw_gogleddol-medium",
}
EDGE_VOZES = {
    "pt": "pt-BR-AntonioNeural", "en": "en-US-GuyNeural", "es": "es-ES-AlvaroNeural",
    "fr": "fr-FR-HenriNeural", "de": "de-DE-ConradNeural", "it": "it-IT-DiegoNeural",
    "ja": "ja-JP-KeitaNeural", "zh": "zh-CN-YunxiNeural", "ru": "ru-RU-DmitryNeural",
    "tr": "tr-TR-AhmetNeural", "ko": "ko-KR-InJoonNeural", "ar": "ar-SA-HamedNeural",
    "hi": "hi-IN-MadhurNeural", "nl": "nl-NL-MaartenNeural", "pl": "pl-PL-MarekNeural",
    "uk": "uk-UA-OstapNeural", "sv": "sv-SE-MattiasNeural",
}
NOMES_IDIOMA = {
    "pt": "português", "en": "inglês", "es": "espanhol", "fr": "francês", "de": "alemão",
    "it": "italiano", "ja": "japonês", "zh": "chinês", "ru": "russo", "tr": "turco",
    "ko": "coreano", "ar": "árabe", "hi": "hindi", "nl": "holandês", "pl": "polonês",
    "uk": "ucraniano", "sv": "sueco",
}


# ── Ouvido (Whisper) ──────────────────────────────────────────────────────────
class OuvidoWhisper:
    """faster-whisper no processador. transcrever() → (texto, idioma)."""

    def __init__(self, modelo: str = "small", idioma: str = "auto", vocabulario: str = ""):
        from faster_whisper import WhisperModel
        try:
            import torch
            disp = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            disp = "cpu"
        tipo = "float16" if disp == "cuda" else "int8"
        self._modelo = WhisperModel(modelo or "small", device=disp, compute_type=tipo)
        self._idioma = None if not idioma or idioma == "auto" else idioma
        self._vocab = vocabulario or None
        self.descricao = f"Whisper {modelo} ({disp})"

    def transcrever(self, audio: np.ndarray) -> tuple[str, str]:
        segs, info = self._modelo.transcribe(
            audio.astype(np.float32), language=self._idioma, initial_prompt=self._vocab,
            beam_size=1, best_of=1, condition_on_previous_text=False,
            vad_filter=True, vad_parameters={"min_silence_duration_ms": 300})
        texto = " ".join(s.text for s in segs).strip()
        idioma = (getattr(info, "language", None) or self._idioma or "pt").lower()
        return texto, idioma


# ── Utilidades de áudio ───────────────────────────────────────────────────────
def para_24k(pcm: np.ndarray, taxa: int) -> np.ndarray:
    """int16 mono em qualquer taxa → int16 a 24 kHz (interpolação linear)."""
    if taxa == TAXA_SAIDA or pcm.size == 0:
        return pcm.astype(np.int16, copy=False)
    n = int(round(pcm.size * TAXA_SAIDA / float(taxa)))
    x = np.linspace(0, pcm.size - 1, num=max(1, n))
    return np.interp(x, np.arange(pcm.size), pcm.astype(np.float32)).astype(np.int16)


def _wav_para_pcm(dados: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(dados), "rb") as w:
        taxa, canais, larg = w.getframerate(), w.getnchannels(), w.getsampwidth()
        bruto = w.readframes(w.getnframes())
    pcm = np.frombuffer(bruto, dtype=np.int16 if larg == 2 else np.uint8)
    if larg != 2:
        pcm = ((pcm.astype(np.int16) - 128) << 8).astype(np.int16)
    if canais > 1:
        pcm = pcm.reshape(-1, canais).mean(axis=1).astype(np.int16)
    return pcm, taxa


def frases(texto: str) -> list[str]:
    """Quebra a resposta em frases para começar a falar antes de sintetizar tudo."""
    partes = re.split(r"(?<=[.!?…;:])\s+|\n+", str(texto or "").strip())
    out, buf = [], ""
    for p in partes:
        p = p.strip()
        if not p:
            continue
        buf = f"{buf} {p}".strip() if buf else p
        if len(buf) >= 25:
            out.append(buf); buf = ""
    if buf:
        out.append(buf)
    return out


def falavel(texto: str) -> str:
    """Tira markdown e símbolos que a voz leria como ruído."""
    t = re.sub(r"```.*?```", " ", str(texto or ""), flags=re.S)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"[*_#>|~]+", "", t)
    t = re.sub(r"^\s*[-•]\s+", "", t, flags=re.M)
    return re.sub(r"\s+", " ", t).strip()


# ── Vozes ─────────────────────────────────────────────────────────────────────
class VozPiper:
    """Piper (rhasspy) — neural e offline. Baixa a voz de cada idioma na 1ª vez."""
    nome = "Piper (offline)"

    def __init__(self, voz_padrao: str = "", log: Callable[[str], None] = print):
        import piper  # noqa: F401  — falha cedo se o pacote não estiver instalado
        self._vozes: dict[str, object] = {}
        self._padrao = voz_padrao or PIPER_VOZES["pt"]
        self._log = log
        self._lock = threading.Lock()

    @staticmethod
    def _url(voz: str) -> str:
        locale, nome, qual = voz.split("-", 2)
        familia = locale.split("_")[0]
        return (f"https://huggingface.co/rhasspy/piper-voices/resolve/main/"
                f"{familia}/{locale}/{nome}/{qual}/{voz}.onnx")

    def _baixar(self, voz: str) -> Path:
        import requests
        PASTA_PIPER.mkdir(parents=True, exist_ok=True)
        modelo = PASTA_PIPER / f"{voz}.onnx"
        config = PASTA_PIPER / f"{voz}.onnx.json"
        if modelo.exists() and config.exists():
            return modelo
        self._log(f"Baixando a voz {voz} (só na primeira vez, ~20-60 MB)…")
        for url, dest in ((self._url(voz) + ".json", config), (self._url(voz), modelo)):
            tmp = dest.with_suffix(dest.suffix + ".part")
            with requests.get(url, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for bloco in r.iter_content(1 << 16):
                        f.write(bloco)
            tmp.replace(dest)
        return modelo

    def _carregar(self, voz: str):
        with self._lock:
            if voz in self._vozes:
                return self._vozes[voz]
            caminho = self._baixar(voz)
            try:
                from piper import PiperVoice
            except ImportError:
                from piper.voice import PiperVoice
            v = PiperVoice.load(str(caminho))
            self._vozes[voz] = v
            return v

    def sintetizar(self, texto: str, idioma: str = "pt") -> Iterator[np.ndarray]:
        voz_id = PIPER_VOZES.get((idioma or "")[:2], None) or self._padrao
        try:
            voz = self._carregar(voz_id)
        except Exception as e:
            if voz_id == self._padrao:
                raise
            self._log(f"Voz {voz_id} indisponível ({e}) — usando {self._padrao}.")
            voz = self._carregar(self._padrao)
        if hasattr(voz, "synthesize") and not hasattr(voz, "synthesize_stream_raw"):
            for chunk in voz.synthesize(texto):               # piper-tts ≥ 1.3
                pcm = np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16)
                yield para_24k(pcm, int(chunk.sample_rate))
        else:                                                  # piper-tts 1.2
            taxa = int(voz.config.sample_rate)
            for bruto in voz.synthesize_stream_raw(texto):
                yield para_24k(np.frombuffer(bruto, dtype=np.int16), taxa)


class VozElevenLabs:
    """ElevenLabs — uma voz multilíngue, transmitida enquanto é gerada."""
    nome = "ElevenLabs"

    def __init__(self, chave: str, voz_id: str = "", modelo: str = "eleven_flash_v2_5"):
        if not chave:
            raise RuntimeError("falta a chave da ElevenLabs")
        import requests
        self._http = requests.Session()
        self._chave = chave
        self._voz = voz_id or "pNInz6obpgDQGcFmaJgB"
        self._modelo = modelo or "eleven_flash_v2_5"

    def sintetizar(self, texto: str, idioma: str = "pt") -> Iterator[np.ndarray]:
        url = (f"https://api.elevenlabs.io/v1/text-to-speech/{self._voz}/stream"
               f"?output_format=pcm_24000")
        corpo = {"text": texto, "model_id": self._modelo,
                 "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}
        if idioma and self._modelo.startswith(("eleven_flash_v2_5", "eleven_turbo_v2_5")):
            corpo["language_code"] = idioma[:2]
        with self._http.post(url, json=corpo, stream=True, timeout=30,
                             headers={"xi-api-key": self._chave}) as r:
            if r.status_code >= 400:
                raise RuntimeError(f"ElevenLabs {r.status_code}: {r.text[:200]}")
            resto = b""
            for bloco in r.iter_content(4800):
                if not bloco:
                    continue
                bloco = resto + bloco
                corte = len(bloco) - (len(bloco) % 2)
                resto = bloco[corte:]
                if corte:
                    yield np.frombuffer(bloco[:corte], dtype=np.int16)


class VozEdge:
    """Vozes neurais da Microsoft (edge-tts), grátis, com internet."""
    nome = "Edge (online)"

    def __init__(self, voz_padrao: str = ""):
        import edge_tts  # noqa: F401
        import miniaudio  # noqa: F401
        self._padrao = voz_padrao or EDGE_VOZES["pt"]

    def sintetizar(self, texto: str, idioma: str = "pt") -> Iterator[np.ndarray]:
        import asyncio
        import edge_tts
        import miniaudio
        voz = EDGE_VOZES.get((idioma or "")[:2], self._padrao)

        async def _mp3() -> bytes:
            buf = bytearray()
            async for c in edge_tts.Communicate(texto, voz).stream():
                if c["type"] == "audio":
                    buf.extend(c["data"])
            return bytes(buf)

        mp3 = asyncio.run(_mp3())
        if not mp3:
            return
        dec = miniaudio.decode(mp3, output_format=miniaudio.SampleFormat.SIGNED16,
                               nchannels=1, sample_rate=TAXA_SAIDA)
        yield np.frombuffer(bytes(dec.samples), dtype=np.int16)


class VozSistema:
    """A voz do Windows (SAPI 5) via pyttsx3 — sempre disponível, offline."""
    nome = "Voz do Windows"

    def __init__(self, velocidade: int = 185):
        import pyttsx3
        self._pyttsx3 = pyttsx3
        self._vel = velocidade
        self._lock = threading.Lock()

    def sintetizar(self, texto: str, idioma: str = "pt") -> Iterator[np.ndarray]:
        import os
        import tempfile
        with self._lock:
            eng = self._pyttsx3.init()
            eng.setProperty("rate", self._vel)
            try:
                from core.vozes import escolher_voz
                alvo = {"pt": ("portug", "pt-br", "pt_br", "brazil"), "en": ("english", "en-us"),
                        "es": ("spanish", "espa"), "fr": ("french", "fran")}.get(idioma[:2], (idioma[:2],))
                voz = escolher_voz(eng.getProperty("voices"), alvo)
                if voz:
                    eng.setProperty("voice", voz)
            except Exception:
                pass
            fd, caminho = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            try:
                eng.save_to_file(texto, caminho)
                eng.runAndWait()
                dados = Path(caminho).read_bytes()
            finally:
                try:
                    os.remove(caminho)
                except Exception:
                    pass
        pcm, taxa = _wav_para_pcm(dados)
        yield para_24k(pcm, taxa)


def criar_voz(cfg: dict, log: Callable[[str], None] = print):
    """A voz escolhida; se não der (pacote faltando, sem chave), a do Windows."""
    escolha = str(cfg.get("tts_motor") or "piper").lower()
    try:
        if escolha == "piper":
            return VozPiper(str(cfg.get("piper_voz") or ""), log=log)
        if escolha == "elevenlabs":
            return VozElevenLabs(str(cfg.get("elevenlabs_api_key") or ""),
                                 str(cfg.get("elevenlabs_voice_id") or ""),
                                 str(cfg.get("elevenlabs_modelo") or "eleven_flash_v2_5"))
        if escolha == "edge":
            return VozEdge(str(cfg.get("edge_voz") or ""))
    except ImportError as e:
        pacote = {"piper": "piper-tts", "edge": "edge-tts miniaudio"}.get(escolha, str(e))
        log(f"A voz '{escolha}' precisa de: pip install {pacote} — usando a voz do Windows por enquanto.")
    except Exception as e:
        log(f"A voz '{escolha}' não abriu ({e}) — usando a voz do Windows por enquanto.")
    try:
        return VozSistema(int(cfg.get("voice_rate") or 185))
    except Exception as e:
        log(f"Nenhuma voz disponível ({e}) — as respostas aparecem só na conversa. "
            f"Instale uma: pip install piper-tts")
        return VozMuda()


class VozMuda:
    """Sem voz instalada: a resposta fica só escrita na conversa."""
    nome = "sem voz"

    def sintetizar(self, texto: str, idioma: str = "pt"):
        return iter(())


# ── Tocador ───────────────────────────────────────────────────────────────────
class Tocador:
    """Toca int16 a 24 kHz no alto-falante escolhido, em pedaços de 50 ms:
    mede o volume (onda do HUD) e para na hora em parar()."""

    def __init__(self, dispositivo=None, ao_nivel: Callable[[float], None] | None = None):
        self._disp = dispositivo
        self._ao_nivel = ao_nivel
        self._parar = threading.Event()
        self._stream = None
        self._lock = threading.Lock()

    def _abrir(self):
        import sounddevice as sd
        if self._stream is None:
            try:
                self._stream = sd.RawOutputStream(samplerate=TAXA_SAIDA, channels=1,
                                                  dtype="int16", device=self._disp)
            except Exception:
                self._stream = sd.RawOutputStream(samplerate=TAXA_SAIDA, channels=1, dtype="int16")
            self._stream.start()
        return self._stream

    def parar(self) -> None:
        self._parar.set()

    @property
    def interrompido(self) -> bool:
        return self._parar.is_set()

    def novo_turno(self) -> None:
        self._parar.clear()

    def tocar(self, pcm: np.ndarray) -> bool:
        """Toca um pedaço. False se foi interrompido."""
        if self._parar.is_set():
            return False
        with self._lock:
            st = self._abrir()
            passo = TAXA_SAIDA // 20                      # 50 ms
            for i in range(0, pcm.size, passo):
                if self._parar.is_set():
                    return False
                fatia = pcm[i:i + passo]
                if self._ao_nivel is not None:
                    try:
                        rms = float(np.sqrt(np.mean(fatia.astype(np.float32) ** 2)))
                        self._ao_nivel(0.0 if rms < 60 else min(1.0, (rms - 60) / 2540.0))
                    except Exception:
                        pass
                st.write(fatia.tobytes())
        return True

    def fechar(self) -> None:
        with self._lock:
            if self._stream is not None:
                try:
                    self._stream.stop(); self._stream.close()
                except Exception:
                    pass
                self._stream = None
