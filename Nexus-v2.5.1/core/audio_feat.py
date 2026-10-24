"""
core/audio_feat.py — características de áudio em NumPy puro (NEXUS Pro 2.3).

Base da voz do dono (core/voz_id.py) e da palavra "Nexus" treinada na sua voz
(core/wake_custom.py): espectro em escala mel, MFCC, tom da voz (f0) e corte da fala.
Sem librosa, sem scipy, sem modelo para baixar.
"""
from __future__ import annotations

import numpy as np

TAXA = 16000
N_FFT = 512
JANELA = 400          # 25 ms
SALTO = 160           # 10 ms
N_MEL = 40

_cache: dict = {}


def para_float(x) -> np.ndarray:
    """int16 (qualquer formato do microfone) → float32 mono em [-1, 1]."""
    x = np.asarray(x)
    if x.ndim > 1:
        x = x[:, 0]
    if x.dtype.kind in "iu":
        return x.astype(np.float32) / 32768.0
    return x.astype(np.float32)


def reamostrar(x: np.ndarray, fator: float) -> np.ndarray:
    """fator > 1 = mais rápido e mais agudo (tom e formantes sobem juntos), como outra voz."""
    n = max(2, int(round(len(x) / fator)))
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def banco_mel(taxa: int = TAXA, n_fft: int = N_FFT, n_mel: int = N_MEL,
              fmin: float = 60.0, fmax: float = 7600.0) -> np.ndarray:
    chave = ("mel", taxa, n_fft, n_mel)
    if chave in _cache:
        return _cache[chave]
    hz2mel = lambda f: 2595.0 * np.log10(1.0 + f / 700.0)
    mel2hz = lambda m: 700.0 * (10 ** (m / 2595.0) - 1.0)
    pontos = mel2hz(np.linspace(hz2mel(fmin), hz2mel(fmax), n_mel + 2))
    bins = np.floor((n_fft + 1) * pontos / taxa).astype(int)
    B = np.zeros((n_mel, n_fft // 2 + 1), np.float32)
    for m in range(1, n_mel + 1):
        a, c, b = bins[m - 1], bins[m], bins[m + 1]
        for k in range(a, c):
            B[m - 1, k] = (k - a) / max(c - a, 1)
        for k in range(c, b):
            B[m - 1, k] = (b - k) / max(b - c, 1)
    _cache[chave] = B
    return B


def _quadros(x: np.ndarray, janela: int = JANELA, salto: int = SALTO) -> np.ndarray:
    if len(x) < janela:
        x = np.pad(x, (0, janela - len(x)))
    n = 1 + (len(x) - janela) // salto
    idx = np.arange(janela)[None, :] + salto * np.arange(n)[:, None]
    return x[idx]


def log_mel(x: np.ndarray, taxa: int = TAXA) -> np.ndarray:
    """(T, 40) em log. Pré-ênfase + janela de Hann."""
    x = np.append(x[:1], x[1:] - 0.97 * x[:-1]).astype(np.float32)
    q = _quadros(x) * np.hanning(JANELA).astype(np.float32)
    espectro = np.abs(np.fft.rfft(q, N_FFT, axis=1)) ** 2
    return np.log(espectro @ banco_mel(taxa).T + 1e-8).astype(np.float32)


def _dct(n_mfcc: int, n_mel: int = N_MEL) -> np.ndarray:
    chave = ("dct", n_mfcc, n_mel)
    if chave not in _cache:
        n = np.arange(n_mel)
        _cache[chave] = (np.cos(np.pi / n_mel * (n + 0.5)[None, :] * np.arange(n_mfcc)[:, None])
                         * np.sqrt(2.0 / n_mel)).astype(np.float32)
    return _cache[chave]


def mfcc(x: np.ndarray, n: int = 20, taxa: int = TAXA, lm: np.ndarray | None = None) -> np.ndarray:
    lm = log_mel(x, taxa) if lm is None else lm
    return lm @ _dct(n).T


def energia_por_quadro(x: np.ndarray) -> np.ndarray:
    return np.sqrt(np.mean(_quadros(x) ** 2, axis=1) + 1e-12)


def quadros_de_voz(x: np.ndarray, fracao: float = 0.12) -> np.ndarray:
    """Máscara booleana por quadro: onde há fala (energia acima de uma fração do pico, com piso)."""
    e = energia_por_quadro(x)
    if e.size == 0:
        return np.zeros(0, bool)
    pico = float(np.percentile(e, 95))
    return e >= max(fracao * pico, 0.004)


def aparar(x: np.ndarray, margem_s: float = 0.08) -> np.ndarray:
    """Tira o silêncio do começo e do fim."""
    m = quadros_de_voz(x)
    if not m.any():
        return x[:0]
    ini = max(0, int(np.argmax(m)) * SALTO - int(margem_s * TAXA))
    fim = min(len(x), (len(m) - int(np.argmax(m[::-1]))) * SALTO + JANELA + int(margem_s * TAXA))
    return x[ini:fim]


def f0_por_quadro(x: np.ndarray, taxa: int = TAXA, fmin: float = 70.0, fmax: float = 400.0,
                  mascara: np.ndarray | None = None) -> np.ndarray:
    """Tom da voz (Hz) por autocorrelação, só nos quadros vozeados. Vazio se não achar."""
    q = _quadros(x, 640, SALTO * 2)                       # 40 ms, passo de 20 ms
    lag_min, lag_max = int(taxa / fmax), int(taxa / fmin)
    saida = []
    for i, f in enumerate(q):
        f = f - f.mean()
        if np.sqrt(np.mean(f * f)) < 0.01:
            continue
        ac = np.correlate(f, f, "full")[len(f) - 1:]
        if ac[0] <= 0:
            continue
        ac = ac / ac[0]
        seg = ac[lag_min:lag_max]
        if seg.size == 0:
            continue
        k = int(np.argmax(seg))
        if seg[k] > 0.35:                                  # vozeado de verdade
            saida.append(taxa / (lag_min + k))
    return np.array(saida, np.float32)


class SegmentadorFala:
    """Corta a fala de um fluxo de blocos int16, por energia. Devolve trechos float32.

    min_s/max_s: duração aceita da FALA (sem o silêncio final); silencio_s: pausa que fecha o trecho."""

    def __init__(self, min_s: float = 0.25, max_s: float = 3.0, silencio_s: float = 0.45,
                 piso: float = 250.0, fator_ruido: float = 3.5, taxa: int = TAXA):
        self.min_s, self.max_s, self.silencio_s = min_s, max_s, silencio_s
        self.piso, self.fator, self.taxa = piso, fator_ruido, taxa
        self.ruido = 120.0
        self._pre: list = []
        self._pre_n = 0
        self._fala: list = []
        self._fala_n = 0
        self._sil_n = 0
        self._pre_len = 0
        self._em_fala = False
        self._descartar = False

    def alimentar(self, bloco) -> list[np.ndarray]:
        x = np.asarray(bloco)
        if x.ndim > 1:
            x = x[:, 0]
        x = x.astype(np.int16, copy=False)
        n = int(x.shape[0])
        if n == 0:
            return []
        rms = float(np.sqrt(np.mean(x.astype(np.float32) ** 2)))
        voz = rms >= max(self.piso, self.ruido * self.fator)
        saida: list[np.ndarray] = []
        if not self._em_fala:
            if not voz:
                self.ruido = 0.95 * self.ruido + 0.05 * rms
                self._pre.append(x); self._pre_n += n
                while self._pre_n > 0.35 * self.taxa and self._pre:
                    self._pre_n -= len(self._pre.pop(0))
                return saida
            self._em_fala, self._descartar = True, False
            self._fala, self._fala_n, self._pre_len = list(self._pre), self._pre_n, self._pre_n
            self._pre, self._pre_n, self._sil_n = [], 0, 0
        if not self._descartar:
            self._fala.append(x); self._fala_n += n
        self._sil_n = 0 if voz else self._sil_n + n
        if not self._descartar and self._fala_n / self.taxa > self.max_s + self.silencio_s:
            self._descartar, self._fala, self._fala_n = True, [], 0
        if self._sil_n >= self.silencio_s * self.taxa:
            if not self._descartar:
                voz_s = (self._fala_n - self._pre_len - self._sil_n) / self.taxa
                if self.min_s <= voz_s <= self.max_s:
                    saida.append(np.concatenate(self._fala).astype(np.float32) / 32768.0)
            self._em_fala, self._fala, self._fala_n, self._sil_n, self._descartar = False, [], 0, 0, False
        return saida
