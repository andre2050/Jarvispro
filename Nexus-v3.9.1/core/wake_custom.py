"""
core/wake_custom.py — a palavra "Nexus" treinada na SUA voz (NEXUS Ultra 2026 2.3).

Hoje o NEXUS acorda transcrevendo trechos curtos com o Whisper. Aqui, uma rede neural pequena
aprende o som da SUA chamada e decide sozinha, sem Whisper e sem internet:
mais leve (um MLP minúsculo no lugar de um modelo de 75 MB), mais rápida e menos sujeita a
confundir "nexo", "next", "texas"…

COMO APRENDE
    Positivos   as vezes que você disse "Nexus" no cadastro (≥ 8), aumentadas com velocidade ±10%,
                volume, ruído e deslocamento no tempo.
    Negativos   (1) o que você falou normalmente durante o cadastro; (2) pedaços e distorções da
                própria chamada ("nex", "us", ao contrário, esticada, comprimida) — são os falsos
                alarmes mais prováveis; (3) ruído, zumbido, estalos e silêncio.
    Entrada     MFCC do trecho aparado, redimensionado para 32 quadros × 20 coeficientes + duração.
    Rede        MLP 641 → 64 → 2 (core/neural_backend.py: Keras ou NumPy), parada antecipada.

Mesma interface do detector atual (start/stop/feed/ready), então o resto do app nem percebe.
Se o modelo não existir, o NEXUS continua usando o Whisper como antes.
"""
from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path
from typing import Callable

import numpy as np

from core import audio_feat as A

_BASE = Path(__file__).resolve().parent.parent
ARQ_MODELO = _BASE / "memory" / "wake_nexus.npz"
QUADROS = 32
N_MFCC = 20
MIN_POSITIVOS = 8
LIMIAR_PADRAO = 0.88
_COOLDOWN_S = 1.8
_TRAVA = threading.RLock()
_cache: dict = {}


def vetor(x) -> np.ndarray | None:
    """Característica de um trecho curto (a chamada). None se for curto/silencioso demais."""
    x = A.para_float(x)
    x = A.aparar(x)
    dur = len(x) / A.TAXA
    if dur < 0.2 or dur > 3.0:
        return None
    pico = float(np.max(np.abs(x))) or 1.0
    x = x / pico * 0.5
    m = A.mfcc(x, N_MFCC)
    m = m - m.mean(0, keepdims=True)                       # tira o canal/volume
    t_old, t_new = np.linspace(0, 1, len(m)), np.linspace(0, 1, QUADROS)
    m = np.stack([np.interp(t_new, t_old, m[:, k]) for k in range(N_MFCC)], axis=1)
    return np.concatenate([m.ravel(), [dur]]).astype(np.float32)


# ── dados de treino ──────────────────────────────────────────────────────────
def _aumentar(x: np.ndarray, rng: np.random.Generator, n: int) -> list[np.ndarray]:
    saida = []
    for _ in range(n):
        y = A.reamostrar(x, float(rng.uniform(0.9, 1.1))) * float(rng.uniform(0.4, 1.6))
        if rng.random() < 0.7:
            y = y + rng.normal(0, rng.uniform(0.0, 0.02), y.shape)
        desloc = int(rng.uniform(0.0, 0.25) * A.TAXA)
        y = np.concatenate([np.zeros(desloc, np.float32), y.astype(np.float32),
                            np.zeros(int(rng.uniform(0.0, 0.25) * A.TAXA), np.float32)])
        saida.append(y)
    return saida


def _negativos_da_chamada(x: np.ndarray, rng: np.random.Generator) -> list[np.ndarray]:
    x = A.aparar(x)
    n = len(x)
    if n < 0.25 * A.TAXA:
        return []
    meio = n // 2
    return [x[:meio], x[meio:], x[::-1].copy(), A.reamostrar(x, 1.8),
            np.concatenate([x, x])[:int(2.9 * A.TAXA)]]


def _sinteticos(rng: np.random.Generator, n: int) -> list[np.ndarray]:
    out = []
    for _ in range(n):
        dur = float(rng.uniform(0.3, 1.5))
        t = np.arange(int(dur * A.TAXA)) / A.TAXA
        tipo = rng.integers(0, 4)
        if tipo == 0:
            y = rng.normal(0, rng.uniform(0.02, 0.2), t.shape)                       # ruído
        elif tipo == 1:
            f = rng.uniform(80, 400)
            y = sum(np.sin(2 * np.pi * f * h * t) / h for h in range(1, 6)) * 0.2   # zumbido
        elif tipo == 2:
            y = np.zeros_like(t)
            for _ in range(rng.integers(1, 5)):
                i = rng.integers(0, len(t) - 200)
                y[i:i + 200] = rng.normal(0, 0.5, 200) * np.hanning(200)             # estalos
        else:
            f0 = rng.uniform(100, 250)
            y = np.sin(2 * np.pi * (f0 + 60 * np.sin(2 * np.pi * rng.uniform(1, 5) * t)) * t) * 0.3   # vogal cantada
        out.append((y + rng.normal(0, 0.003, t.shape)).astype(np.float32))
    return out


def treinar(positivos: list, negativos: list | None = None, semente: int = 3, log=print) -> dict:
    """positivos = trechos dizendo "Nexus"; negativos = outras falas suas. Salva o modelo."""
    from core.neural_backend import engine as NE
    rng = np.random.default_rng(semente)
    pos = [A.para_float(p) for p in positivos]
    pos = [p for p in pos if vetor(p) is not None]
    if len(pos) < MIN_POSITIVOS:
        raise ValueError(f"Preciso de pelo menos {MIN_POSITIVOS} chamadas boas ('Nexus' curto e claro); "
                         f"só {len(pos)} serviram.")
    neg_reais = [A.para_float(n) for n in (negativos or [])]
    idx = rng.permutation(len(pos))
    n_val = max(2, len(pos) // 5)
    val_i, tr_i = idx[:n_val], idx[n_val:]

    def montar(ids, reais):
        X, y = [], []
        for i in ids:
            for v in [pos[i]] + _aumentar(pos[i], rng, 14):
                f = vetor(v)
                if f is not None:
                    X.append(f); y.append(1)
            for v in _negativos_da_chamada(pos[i], rng):
                for w in [v] + _aumentar(v, rng, 3):
                    f = vetor(w)
                    if f is not None:
                        X.append(f); y.append(0)
        for r in reais:
            for w in [r] + _aumentar(r, rng, 4):
                f = vetor(w)
                if f is not None:
                    X.append(f); y.append(0)
        for s in _sinteticos(rng, 60):
            f = vetor(s)
            if f is not None:
                X.append(f); y.append(0)
        return np.array(X, np.float32), np.array(y)

    corte = max(1, int(len(neg_reais) * 0.8))
    Xtr, ytr = montar(tr_i, neg_reais[:corte])
    Xva, yva = montar(val_i, neg_reais[corte:])
    media, desvio = Xtr.mean(0), Xtr.std(0) + 1e-3
    z = lambda X: (X - media) / desvio
    Y = lambda y: np.eye(2)[y]
    w = np.where(ytr == 1, 0.5 / max((ytr == 1).mean(), 1e-6), 0.5 / max((ytr == 0).mean(), 1e-6))
    rede = NE.MLP([Xtr.shape[1], 128, 2], "relu", seed=semente, dropout=0.1)
    NE.fit(rede, z(Xtr), Y(ytr), "classification", epochs=400, lr=0.005, optimizer="adam", batch=64,
           l2=1e-3, w=w, Xv=z(Xva), Yv=Y(yva), patience=40, seed=semente, noise=0.05)
    p = NE.softmax(rede.predict(z(Xva)))[:, 1]
    # limiar calibrado na validação: o menor que deixa os falsos alarmes em até 2% dos negativos
    # (um falso alarme acorda o NEXUS à toa; perder uma chamada só obriga a repetir)
    neg_p = np.sort(p[yva == 0])
    limiar = float(np.clip(neg_p[int(np.ceil(0.98 * len(neg_p))) - 1] + 1e-3, 0.60, 0.97)) if len(neg_p) else LIMIAR_PADRAO
    rel = {"chamadas": len(pos), "falas_normais": len(neg_reais), "limiar": round(limiar, 3),
           "acerta_chamada": float((p[yva == 1] >= limiar).mean()),
           "evita_falso_alarme": float((p[yva == 0] < limiar).mean()),
           "treinado_em": time.strftime("%d/%m/%Y %H:%M")}
    with _TRAVA:
        ARQ_MODELO.parent.mkdir(parents=True, exist_ok=True)
        tmp = ARQ_MODELO.with_suffix(".tmp.npz")
        np.savez(tmp, media=media, desvio=desvio, W0=rede.W[0], b0=rede.b[0], W1=rede.W[1], b1=rede.b[1],
                 relatorio=json.dumps(rel))
        tmp.replace(ARQ_MODELO)
        _cache.clear()
    log(f"[WakeCustom] treinada: acerta {rel['acerta_chamada']:.0%}, evita falso alarme {rel['evita_falso_alarme']:.0%}")
    return rel


def _carregar():
    with _TRAVA:
        if "m" in _cache:
            return _cache["m"]
        try:
            from core.neural_backend import engine as NE
            with np.load(ARQ_MODELO, allow_pickle=False) as z:
                rede = NE.MLP.from_arrays([z["W0"].shape[0], z["W0"].shape[1], 2], "relu",
                                          [z["W0"], z["W1"]], [z["b0"], z["b1"]])
                m = (rede, z["media"], z["desvio"], json.loads(str(z["relatorio"])))
        except Exception:
            m = None
        _cache["m"] = m
        return m


def treinada() -> bool:
    return _carregar() is not None


def relatorio() -> dict:
    m = _carregar()
    return dict(m[3]) if m else {}


def probabilidade(trecho) -> float:
    """Chance (0–1) de o trecho ser a chamada "Nexus". 0 se não há modelo ou o trecho não serve."""
    m = _carregar()
    if m is None:
        return 0.0
    f = vetor(trecho)
    if f is None:
        return 0.0
    from core.neural_backend import engine as NE
    rede, media, desvio, _ = m
    return float(NE.softmax(rede.predict(((f - media) / desvio)[None, :]))[0, 1])


def remover() -> bool:
    with _TRAVA:
        _cache.clear()
        try:
            ARQ_MODELO.unlink()
            return True
        except FileNotFoundError:
            return False


def limiar_de(limiar_do_app: float) -> float:
    """Limiar de disparo = o calibrado no treino, ajustado pela configuração "Sensibilidade da palavra
    de ativação" do app (valor MENOR = acorda mais fácil: 0,35 alta, 0,5 normal, 0,7 baixa)."""
    t = min(max(float(limiar_do_app), 0.0), 1.0)
    base = float(relatorio().get("limiar", LIMIAR_PADRAO))
    return float(np.clip(base + (t - 0.5) * 0.2, 0.55, 0.98))


# ── detector (mesma interface do WakeWordDetector) ───────────────────────────
class CustomWakeDetector:
    def __init__(self, on_detect: Callable[[], None], threshold: float = 0.5,
                 logger: Callable[[str], None] = print,
                 notify: Callable[[str], None] | None = None):
        self._on_detect = on_detect
        self._limiar = limiar_de(threshold)
        self._logger = logger
        self._notify = notify or (lambda _m: None)
        self._queue: queue.Queue = queue.Queue(maxsize=200)
        self._thread: threading.Thread | None = None
        self._running = False
        self._seg = A.SegmentadorFala(min_s=0.25, max_s=2.5, silencio_s=0.4)
        self._ultimo = 0.0

    def start(self) -> bool:
        if self._running:
            return True
        if not treinada():
            self._notify("Palavra 'Nexus' treinada na sua voz ainda não foi cadastrada.")
            return False
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="WakeCustomThread")
        self._thread.start()
        self._logger("Palavra Nexus (sua voz): ouvindo.")
        return True

    def stop(self) -> None:
        self._running = False
        try:
            self._queue.put_nowait(None)
        except Exception:
            pass

    @property
    def ready(self) -> bool:
        return self._running and treinada()

    def feed(self, frame_int16) -> None:
        if not self._running:
            return
        try:
            data = frame_int16[:, 0].copy() if getattr(frame_int16, "ndim", 1) > 1 else frame_int16.copy()
            self._queue.put_nowait(data)
        except Exception:
            pass

    def _tratar(self, trecho) -> bool:
        if time.monotonic() - self._ultimo < _COOLDOWN_S:
            return False
        p = probabilidade(trecho)
        if p >= self._limiar:
            self._ultimo = time.monotonic()
            self._logger(f"Palavra Nexus (sua voz): reconheci a chamada ({p:.0%}).")
            self._drain()
            try:
                self._on_detect()
            except Exception as e:
                self._logger(f"Palavra Nexus (sua voz): erro no on_detect — {e}")
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
                self._logger(f"Palavra Nexus (sua voz): erro — {e}")

    def _drain(self) -> None:
        try:
            while True:
                self._queue.get_nowait()
        except Exception:
            pass
        self._seg = A.SegmentadorFala(min_s=0.25, max_s=2.5, silencio_s=0.4)
