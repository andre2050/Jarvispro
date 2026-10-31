"""
core/wake_nexus.py — palavra de ativação "NEXUS" (offline, NEXUS Ultra 2026 1.5).

O modelo pronto do openWakeWord só conhece "Hey Jarvis". Este detector entende
"Nexus", "Hey Nexus", "Ei Nexus", "Oi Nexus", "Ok Nexus"… usando o Whisper
(faster-whisper, o mesmo pacote do motor próprio), 100% no seu PC.

Como não pesa
  • Um corte de fala por energia (barato, em numpy) separa os trechos curtos.
    SÓ trechos de até ~3 s são enviados ao Whisper; conversa longa, TV e música
    nunca chegam nele. Silêncio custa quase nada.
  • O Whisper "tiny" (≈75 MB, baixado uma vez) roda em segundo plano, numa
    thread própria; o microfone só faz um push numa fila (feed), como antes.
  • Nada sai do computador. A única rede é o download único do modelo.

Mesma interface do WakeWordDetector (core/wake_word.py): start(), stop(),
feed(), ready, on_detect — o resto do NEXUS nem percebe a troca.

Limite honesto: reconhecer uma palavra solta é mais difícil que uma frase.
Em sala barulhenta pode errar; ajuste em Configurações › Sensibilidade, ou use
"Segurar para falar" (Ctrl+Espaço).
"""
from __future__ import annotations

import collections
import difflib
import queue
import re
import subprocess
import sys
import threading
import time
import unicodedata
from typing import Callable
from core.protecao import engolida as _engolida

SAMPLE_RATE = 16000
PALAVRA = "nexus"
MODELO = "tiny"

# trechos de fala aceitos como "possível chamada"
_MIN_S = 0.25
_MAX_S = 3.0
_SILENCIO_FIM_S = 0.45
_PRE_ROLL_S = 0.35
_COOLDOWN_S = 1.8
_PISO_ENERGIA = 250.0        # rms (int16) mínimo para contar como voz
_FATOR_RUIDO = 3.5

# palavras que podem vir antes de "Nexus" ("hey nexus", "ei nexus", "ok nexus")
_ANTES = {"hey", "hei", "ei", "ey", "oi", "ola", "ok", "okay", "e", "ai", "a", "o", "opa",
          "hi", "hello"}


# ── instalação / disponibilidade ────────────────────────────────────────────
def is_installed() -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec("faster_whisper") is not None
    except Exception:
        return False


def is_ready() -> bool:
    """Pacote instalado. O modelo tiny baixa sozinho na primeira ativação."""
    return is_installed()


def install_and_download(logger: Callable[[str], None] = print,
                         notify: Callable[[str], None] | None = None) -> tuple[bool, str]:
    """Instala o faster-whisper (se faltar) e baixa o modelo tiny. Nunca levanta."""
    _tell = notify or (lambda _m: None)
    try:
        if not is_installed():
            logger("Palavra Nexus: instalando faster-whisper (uma vez)…")
            _tell("Palavra Nexus: instalando faster-whisper (uma vez)…")
            r = subprocess.run([sys.executable, "-m", "pip", "install", "faster-whisper"],
                               capture_output=True, text=True)
            if r.returncode != 0:
                tail = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or [""]
                return False, f"pip install falhou: {tail[0][:160]}"
        logger("Palavra Nexus: baixando o modelo de voz (uma vez, ~75 MB)…")
        _tell("Palavra Nexus: baixando o modelo de voz (uma vez, ~75 MB)…")
        from faster_whisper import WhisperModel
        WhisperModel(MODELO, device="cpu", compute_type="int8")
        return True, "Palavra de ativação 'Nexus' pronta."
    except Exception as e:
        return False, f"não foi possível preparar a palavra Nexus: {e}"


# ── texto: "isso foi uma chamada?" ───────────────────────────────────────────
def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", t).strip()


def limiar_de_similaridade(sensibilidade: float) -> float:
    """0.35 (acorda fácil) … 0.7 (menos alarme falso) → mínimo de parecença com 'nexus'."""
    try:
        s = float(sensibilidade)
    except (TypeError, ValueError):
        s = 0.5
    s = min(0.9, max(0.2, s))
    # o app guarda "confiança mínima": MAIOR = mais exigente
    return max(0.62, min(0.93, 0.62 + (s - 0.2) * 0.44))


def e_chamada(texto: str, limiar: float = 0.8) -> bool:
    """True se o trecho é a chamada: [saudação] + 'nexus', no máximo 4 palavras."""
    palavras = _norm(texto).split()
    if not palavras or len(palavras) > 4:
        return False

    def parece(p: str) -> bool:
        return p == PALAVRA or difflib.SequenceMatcher(None, p, PALAVRA).ratio() >= limiar

    for i, p in enumerate(palavras):
        so_saudacao = all(a in _ANTES for a in palavras[:i])
        if not so_saudacao:
            return False                      # "eu falei do nexus": Nexus tem de vir no início
        if parece(p):
            return True
        # o reconhecedor às vezes parte a palavra: "o rion", "ori on"
        if i + 1 < len(palavras) and parece(p + palavras[i + 1]):
            return True
    return False


# ── corte da fala (numpy, sem modelo) ────────────────────────────────────────
class Segmentador:
    """Recebe blocos int16 de qualquer tamanho; devolve trechos curtos de fala.

    Só passam trechos entre _MIN_S e _MAX_S segundos. Mais longo que isso é
    conversa, TV ou música — descartado sem custo."""

    def __init__(self, taxa: int = SAMPLE_RATE):
        self.taxa = taxa
        self._ruido = 120.0                 # rms do silêncio (média móvel)
        self._pre: collections.deque = collections.deque()   # [(bloco, n)]
        self._pre_n = 0
        self._fala: list = []
        self._fala_n = 0
        self._sil_n = 0
        self._pre_len = 0                   # amostras de pré-rolagem no início do trecho
        self._em_fala = False
        self._descartar = False             # passou de _MAX_S: ignora até o silêncio

    def _limiar(self) -> float:
        return max(_PISO_ENERGIA, self._ruido * _FATOR_RUIDO)

    def alimentar(self, bloco) -> list:
        import numpy as np
        x = np.asarray(bloco)
        if x.ndim > 1:
            x = x[:, 0]
        x = x.astype(np.int16, copy=False)
        n = int(x.shape[0])
        if n == 0:
            return []
        rms = float(np.sqrt(np.mean(np.square(x.astype(np.float32)))))
        voz = rms >= self._limiar()
        saida = []

        if not self._em_fala:
            if not voz:
                self._ruido = 0.95 * self._ruido + 0.05 * rms      # aprende o ruído do ambiente
                self._pre.append((x, n)); self._pre_n += n
                while self._pre_n > _PRE_ROLL_S * self.taxa and self._pre:
                    _, m = self._pre.popleft(); self._pre_n -= m
                return saida
            # começou a fala: leva o pré-rolagem junto (não corta o "o" de Nexus)
            self._em_fala = True
            self._descartar = False
            self._fala = [b for b, _ in self._pre]
            self._fala_n = self._pre_n
            self._pre_len = self._pre_n
            self._pre.clear(); self._pre_n = 0
            self._sil_n = 0

        # em fala
        if not self._descartar:
            self._fala.append(x); self._fala_n += n
        if voz:
            self._sil_n = 0
        else:
            self._sil_n += n

        dur = self._fala_n / self.taxa
        if not self._descartar and dur > _MAX_S + _SILENCIO_FIM_S:
            self._descartar = True              # longo demais: é conversa, não chamada
            self._fala = []; self._fala_n = 0

        if self._sil_n >= _SILENCIO_FIM_S * self.taxa:
            if not self._descartar:
                voz_s = (self._fala_n - self._pre_len - self._sil_n) / self.taxa   # só a fala, sem pré-rolagem nem silêncio final
                if _MIN_S <= voz_s <= _MAX_S:
                    import numpy as np
                    saida.append(np.concatenate(self._fala).astype(np.float32) / 32768.0)
            self._em_fala = False
            self._fala = []; self._fala_n = 0; self._sil_n = 0; self._descartar = False
        return saida


# ── o detector ───────────────────────────────────────────────────────────────
class NexusWordDetector:
    """Mesma interface do WakeWordDetector (core/wake_word.py)."""

    def __init__(self, on_detect: Callable[[], None], threshold: float = 0.5,
                 logger: Callable[[str], None] = print,
                 notify: Callable[[str], None] | None = None):
        self._on_detect = on_detect
        self._limiar = limiar_de_similaridade(threshold)
        self._logger = logger
        self._notify = notify or (lambda _m: None)
        self._queue: queue.Queue = queue.Queue(maxsize=200)
        self._thread: threading.Thread | None = None
        self._running = False
        self._ready = False
        self._modelo = None
        self._seg = Segmentador()
        self._ultimo = 0.0

    # -- ciclo de vida --------------------------------------------------------
    def start(self) -> bool:
        if self._running:
            return True
        try:
            from faster_whisper import WhisperModel
            self._modelo = WhisperModel(MODELO, device="cpu", compute_type="int8")
        except Exception as e:
            self._logger(f"Palavra Nexus: não consegui carregar o Whisper — {e}")
            self._notify("Palavra 'Nexus' indisponível — use o botão ACORDAR AGORA "
                         "(ou instale: pip install faster-whisper).")
            self._modelo = None
            return False
        self._running = True
        self._ready = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="WakeNexusThread")
        self._thread.start()
        self._logger("Palavra Nexus: ouvindo 'Nexus' / 'Hey Nexus'.")
        return True

    def stop(self) -> None:
        self._running = False
        try:
            self._queue.put_nowait(None)
        except Exception:
            _engolida("core/wake_nexus.py:248")
        self._modelo = None
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    def feed(self, frame_int16) -> None:
        """Chamado pelo microfone (tempo real): só copia e enfileira."""
        if not self._running:
            return
        try:
            data = frame_int16[:, 0].copy() if getattr(frame_int16, "ndim", 1) > 1 \
                else frame_int16.copy()
            self._queue.put_nowait(data)
        except queue.Full:
            pass
        except Exception:
            _engolida("core/wake_nexus.py:267")

    # -- trabalho em segundo plano -------------------------------------------
    def _transcrever(self, audio) -> str:
        segs, _info = self._modelo.transcribe(
            audio, language="pt", beam_size=1, vad_filter=False,
            condition_on_previous_text=False, without_timestamps=True,
            initial_prompt="Nexus. Hey Nexus. Ei Nexus.")
        return " ".join(s.text for s in segs).strip()

    def _tratar(self, audio) -> bool:
        """Transcreve um trecho curto e dispara se for a chamada. True se disparou."""
        if time.monotonic() - self._ultimo < _COOLDOWN_S:
            return False
        try:
            texto = self._transcrever(audio)
        except Exception as e:
            self._logger(f"Palavra Nexus: erro ao transcrever — {e}")
            return False
        if texto and e_chamada(texto, self._limiar):
            self._ultimo = time.monotonic()
            self._logger(f"Palavra Nexus: ouvi “{texto}”.")
            self._drain()
            try:
                self._on_detect()
            except Exception as e:
                self._logger(f"Palavra Nexus: erro no on_detect — {e}")
            return True
        return False

    def _loop(self) -> None:
        while self._running:
            try:
                bloco = self._queue.get()
                if bloco is None or not self._running:
                    break
                for trecho in self._seg.alimentar(bloco):
                    self._tratar(trecho)
            except Exception as e:
                self._logger(f"Palavra Nexus: erro — {e}")

    def _drain(self) -> None:
        try:
            while True:
                self._queue.get_nowait()
        except Exception:
            _engolida("core/wake_nexus.py:313")
        self._seg = Segmentador()
