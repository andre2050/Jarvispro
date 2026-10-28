"""core/keras_intent.py — a rede do intent_net em Keras (TensorFlow).

Substitui a classe `IntentMLP` (NumPy puro) de core/intent_net.py quando o
TensorFlow está instalado. A arquitetura é a mesma:

    4096 → 192 → 96 → K intenções
    Dense + LayerNormalization + GELU + Dropout(25 %), AdamW (decaimento só nos pesos),
    agenda de taxa de aprendizado em cosseno, label smoothing 5 %,
    parada antecipada pela acurácia de validação (restaura o melhor ponto),
    e calibração de temperatura na validação (T ≥ 1: nunca deixa a rede mais confiante).

A interface é idêntica à do IntentMLP (fit / logits / proba / calibrate / save / load /
sizes / T), e o arquivo `memory/intent_net.npz` tem o MESMO formato: um modelo treinado
com a rede NumPy abre aqui sem retreinar, e o contrário também.

Mapa dos pesos do .npz para o Keras:   W{i}, b{i} → Dense `W{i}` (kernel, bias)
                                       g{i}, s{i} → LayerNormalization `ln{i}` (gamma, beta)
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

os.environ.setdefault("KERAS_BACKEND", "tensorflow")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import numpy as np

import keras
import tensorflow as tf
from keras import layers

DROPOUT = 0.25
_LN_EPS = 1e-5


def _gelu(x):
    return keras.activations.gelu(x, approximate=True)      # a mesma aproximação por tanh do NumPy


class _Treino(keras.callbacks.Callback):
    """Cosseno por época + validação por acurácia + parada antecipada que restaura o melhor ponto
    (mesmas regras do IntentMLP.fit: paciência 6, só depois da época 12)."""

    def __init__(self, net, lr, epochs, Xv, yv, log):
        super().__init__()
        self.net, self.lr, self.epochs, self.Xv, self.yv, self.log = net, lr, epochs, Xv, yv, log
        self.best, self.best_pesos, self.paciencia = -1.0, None, 0

    def on_epoch_begin(self, epoch, logs=None):
        self.model.optimizer.learning_rate = self.lr * (0.5 * (1 + math.cos(math.pi * epoch / self.epochs)))

    def on_epoch_end(self, epoch, logs=None):
        acc = float((self.net.logits(self.Xv).argmax(1) == self.yv).mean()) if len(self.Xv) else 1.0
        if self.log:
            self.log(f"época {epoch + 1}/{self.epochs} — validação {acc:.1%}")
        if acc > self.best + 1e-4:
            self.best, self.best_pesos, self.paciencia = acc, self.net.p, 0
        else:
            self.paciencia += 1
            if self.paciencia >= 6 and epoch >= 12:
                self.model.stop_training = True

    def on_train_end(self, logs=None):
        if self.best_pesos is not None:
            self.net.p = self.best_pesos


class KerasIntentMLP:
    """4096 → 192 → 96 → K, LayerNorm + GELU, treinada com AdamW (em Keras)."""

    def __init__(self, sizes=None, seed=7):
        if sizes is None:
            from core import intent_net as _in
            sizes = (_in.DIM, 192, 96, len(_in.INTENTS))
        self.sizes = tuple(int(s) for s in sizes)
        self.seed = seed
        self.T = 1.0                                         # temperatura calibrada
        self.model = self._montar()

    def _montar(self) -> "keras.Model":
        L = len(self.sizes) - 1
        entrada = keras.Input(shape=(self.sizes[0],), name="frase")
        x = entrada
        for i in range(L):
            x = layers.Dense(
                self.sizes[i + 1], name=f"W{i}",
                kernel_initializer=keras.initializers.VarianceScaling(
                    scale=2.0, mode="fan_in", distribution="untruncated_normal", seed=self.seed + i),
                bias_initializer="zeros")(x)
            if i < L - 1:
                x = layers.LayerNormalization(epsilon=_LN_EPS, name=f"ln{i}")(x)
                x = layers.Activation(_gelu)(x)
                x = layers.Dropout(DROPOUT, seed=self.seed + 100 + i)(x)
        return keras.Model(entrada, x, name="intent_net")

    # ── pesos no formato do .npz antigo ────────────────────────────────────
    @property
    def p(self) -> dict:
        out: dict[str, np.ndarray] = {}
        for i in range(len(self.sizes) - 1):
            kernel, bias = self.model.get_layer(f"W{i}").get_weights()
            out[f"W{i}"], out[f"b{i}"] = kernel, bias
            if i < len(self.sizes) - 2:
                gamma, beta = self.model.get_layer(f"ln{i}").get_weights()
                out[f"g{i}"], out[f"s{i}"] = gamma, beta
        return out

    @p.setter
    def p(self, pesos: dict) -> None:
        for i in range(len(self.sizes) - 1):
            self.model.get_layer(f"W{i}").set_weights(
                [np.asarray(pesos[f"W{i}"], np.float32), np.asarray(pesos[f"b{i}"], np.float32)])
            if i < len(self.sizes) - 2:
                self.model.get_layer(f"ln{i}").set_weights(
                    [np.asarray(pesos[f"g{i}"], np.float32), np.asarray(pesos[f"s{i}"], np.float32)])

    # ── uso ────────────────────────────────────────────────────────────────
    _COMPILAR_APOS = 5      # chamadas antes de compilar o grafo (traçar custa ~70 ms)

    def _inferir(self, X: np.ndarray) -> np.ndarray:
        """Direto (eager) nas primeiras chamadas; depois um grafo compilado: ~1 ms por frase
        em vez de ~7 ms."""
        self._chamadas = getattr(self, "_chamadas", 0) + 1
        fn = getattr(self, "_fn", None)
        if fn is None and self._chamadas > self._COMPILAR_APOS:
            fn = self._fn = tf.function(
                lambda a: self.model(a, training=False), autograph=False,
                input_signature=[tf.TensorSpec([None, self.sizes[0]], tf.float32)])
        if fn is not None:
            return fn(X).numpy()
        return np.asarray(self.model(X, training=False))

    def logits(self, X) -> np.ndarray:
        X = np.atleast_2d(np.asarray(X, dtype=np.float32))
        if len(X) <= 2048:
            return self._inferir(X)
        return np.concatenate([self._inferir(X[i:i + 2048]) for i in range(0, len(X), 2048)])

    def proba(self, X) -> np.ndarray:
        z = self.logits(X) / self.T
        z = z - z.max(1, keepdims=True)
        e = np.exp(z)
        return e / e.sum(1, keepdims=True)

    # ── treino ─────────────────────────────────────────────────────────────
    def fit(self, X, y, w, Xv, yv, epochs=40, batch=64, lr=2e-3, wd=1e-4,
            smooth=0.05, seed=7, log=None):
        K = self.sizes[-1]
        X = np.asarray(X, np.float32)
        y = np.asarray(y, np.int64)
        w = np.asarray(w, np.float32)
        w = w / (float(w.mean()) or 1.0)
        Xv, yv = np.asarray(Xv, np.float32), np.asarray(yv, np.int64)

        opt = keras.optimizers.AdamW(learning_rate=lr, weight_decay=wd, beta_1=0.9, beta_2=0.999,
                                     epsilon=1e-8)
        opt.exclude_from_weight_decay(var_names=["bias", "gamma", "beta"])   # só os pesos (W) decaem
        self.model.compile(
            optimizer=opt, jit_compile=False,
            loss=keras.losses.CategoricalCrossentropy(from_logits=True, label_smoothing=smooth))
        Y = np.eye(K, dtype=np.float32)[y]
        dados = (tf.data.Dataset.from_tensor_slices((X, Y, w))
                 .shuffle(len(X), seed=int(seed), reshuffle_each_iteration=True)
                 .batch(batch).prefetch(1))
        ctl = _Treino(self, lr, epochs, Xv, yv, log)
        self.model.fit(dados, epochs=epochs, callbacks=[ctl], verbose=0, shuffle=False)
        self.calibrate(Xv, yv)
        return ctl.best

    def calibrate(self, Xv, yv):
        """Temperature scaling: escolhe T que minimiza a perda na validação."""
        if not len(Xv):
            return
        z = self.logits(Xv)
        best_t, best_l = 1.0, 1e9
        # T a partir de 1,0 (1.4.3): a validação é fácil e a perda era mínima em T=0,5, o que
        # deixaria a rede MAIS confiante em frases que ela nunca viu. T ≥ 1 nunca aguça.
        for T in np.linspace(1.0, 3.0, 21):
            zz = z / T
            zz = zz - zz.max(1, keepdims=True)
            lp = zz - np.log(np.exp(zz).sum(1, keepdims=True))
            loss = -lp[np.arange(len(yv)), yv].mean()
            if loss < best_l:
                best_t, best_l = float(T), loss
        self.T = best_t

    # ── disco: o mesmo .npz do IntentMLP ───────────────────────────────────
    def save(self, path: Path, meta: dict):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp.npz")
        np.savez_compressed(tmp, T=np.float32(self.T),
                            sizes=np.array(self.sizes),
                            meta=np.frombuffer(json.dumps(meta).encode(), np.uint8),
                            **self.p)
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path):
        d = np.load(path)
        net = cls(tuple(int(s) for s in d["sizes"]))
        net.p = {k: d[k] for k in d.files if k[0] in "Wbgs" and k[1:].isdigit()}
        net.T = float(d["T"])
        meta = json.loads(bytes(d["meta"]).decode())
        return net, meta

    def export(self, path) -> str:
        """Salva no formato nativo `.keras` (a temperatura T fica de fora: aplique logits / T)."""
        path = str(path)
        if not path.endswith(".keras"):
            path += ".keras"
        self.model.save(path)
        return path
