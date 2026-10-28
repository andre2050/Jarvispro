"""Motor da rede neural do NEXUS em Keras (TensorFlow) — mesma API do core/neural_engine.py.

O motor NumPy (core/neural_engine.py) continua no projeto como reserva: quando o
TensorFlow não está instalado, é ele que roda (veja core/neural_backend.py). Os
dois leem e gravam o MESMO formato de modelo (JSON com W/b por camada), então um
modelo treinado em um motor abre no outro.

O que foi reescrito em Keras (a rede e o treino):

  Rede        MLP vira um keras.Model (Dense + Activation + Dropout), com as 7
              ativações, dropout, ruído nas entradas e L2 ajustáveis em cada treino
  Treino      keras.optimizers (SGD, momentum, Nesterov, RMSprop, Adam, AdamW),
              recorte global de gradiente (5.0), tf.data com embaralhamento
              reproduzível, e UM callback que cuida da agenda de taxa de
              aprendizado, validação, parada antecipada, restauração do melhor
              ponto, máscara de poda e detecção de divergência
  Busca       grid / random e AutoML, sobre o treino acima
  Modelo      ensemble, poda, destilação, ajuste fino com camadas congeladas
              (layer.trainable) e exportação para .keras

O que NÃO é rede neural e continua em NumPy, importado do motor antigo: o pipeline
de dados (Prep, split estratificado, SMOTE, pesos de classe), as métricas, a
importância por permutação e o monitor de drift.
"""
from __future__ import annotations

import itertools
import math
import os
import time

os.environ.setdefault("KERAS_BACKEND", "tensorflow")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")          # sem o falatório do TensorFlow no console
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")         # resultados iguais entre computadores

import numpy as np

import keras
import tensorflow as tf
from keras import layers, ops

if int(keras.__version__.split(".")[0]) < 3:                 # o neural_backend cai para o NumPy
    raise ImportError(f"Keras 3 ou mais novo é necessário (achei {keras.__version__})")

from core import neural_engine as _np
from core.neural_engine import (                              # pipeline de dados e métricas (NumPy)
    DEFAULT_CFG, DEFAULT_LR, GRID, OPTIMIZERS, SCHEDULES, SIZE_PRESETS, SPACE,
    Prep, class_weights, clean_rows, drift_report, loss_and_delta, lr_at, metrics, parse_hidden,
    permutation_importance, softmax, split_idx, synth_rows, synthesize,
    _is_missing, _num, _onehot, _prepare_target, _score,
)

BACKEND = "keras"
ACTIVATIONS = tuple(_np.ACTIVATIONS)

# Cada treino em Keras paga ~0,5 s para compilar o grafo (o NumPy não paga nada). Com o orçamento
# antigo de 25 s a busca/AutoML perderia tentativas; 60 s mantém o mesmo número de tentativas.
DEFAULT_OPTS = {**_np.DEFAULT_OPTS, "budget_s": 60.0}


# ══ 2. Rede ═══════════════════════════════════════════════════════════════════

def _camada_ativacao(nome: str):
    if nome == "leaky_relu":
        return layers.LeakyReLU(negative_slope=0.01)
    if nome == "gelu":                                       # mesma aproximação por tanh do motor NumPy
        return layers.Activation(lambda x: keras.activations.gelu(x, approximate=True))
    return layers.Activation(nome)                          # relu, tanh, sigmoid, elu, swish


class _RuidoNaEntrada(layers.Layer):
    """Ruído gaussiano nas entradas, só no treino. O desvio é uma variável: muda a cada fit()
    sem reconstruir a rede."""

    def __init__(self, seed: int = 0, **kw):
        super().__init__(**kw)
        self.std = keras.Variable(0.0, trainable=False, dtype="float32", name="std")
        self._gerador = keras.random.SeedGenerator(seed)

    def call(self, x, training=False):
        if not training:
            return x
        ruido = keras.random.normal(ops.shape(x), seed=self._gerador, dtype=x.dtype)
        return x + ops.cast(self.std, x.dtype) * ruido

    def compute_output_shape(self, input_shape):
        return input_shape


class _L2Ajustavel(keras.regularizers.Regularizer):
    """Penalidade L2 com coeficiente variável (muda a cada fit()). coef = l2/2 reproduz o gradiente
    `l2 * W` do motor NumPy."""

    def __init__(self):
        self.coef = keras.Variable(0.0, trainable=False, dtype="float32", name="l2")

    def __call__(self, x):
        return ops.cast(self.coef, x.dtype) * ops.sum(ops.square(x))


class MLP:
    """Rede feed-forward em Keras: sizes = [entrada, h1, ..., saída].

    Mesma interface do MLP do motor NumPy: `.W` / `.b` (listas de arrays), `.predict`,
    `.get` / `.set`, `MLP.from_arrays`. A saída são os logits (aplique `softmax` para classificar).
    """

    def __init__(self, sizes, activation="relu", seed=42, dropout=0.0):
        if activation not in _np.ACTIVATIONS:
            raise ValueError(f"unknown activation '{activation}' "
                             f"(use: {', '.join(_np.ACTIVATIONS)})")
        self.sizes = [int(s) for s in sizes]
        self.activation = activation
        self.dropout = float(dropout)
        self.seed = int(seed)
        self.mask = None                                     # poda: lista de máscaras 0/1 por kernel
        self._reg = _L2Ajustavel()
        self.model, self._dense, self._ruido = self._montar(com_treino=True)

    def _montar(self, com_treino: bool):
        entrada = keras.Input(shape=(self.sizes[0],), name="entrada")
        x, ruido = entrada, None
        if com_treino:
            ruido = _RuidoNaEntrada(seed=self.seed, name="ruido")
            x = ruido(x)
        ganho = 1.0 if self.activation in ("tanh", "sigmoid") else 2.0
        ultima_oculta = len(self.sizes) - 2
        denses = []
        for i in range(len(self.sizes) - 1):
            g = ganho if i < ultima_oculta else 1.0
            d = layers.Dense(
                self.sizes[i + 1], activation=None, name=f"dense_{i}",
                kernel_initializer=keras.initializers.VarianceScaling(
                    scale=g, mode="fan_in", distribution="untruncated_normal", seed=self.seed + i),
                bias_initializer="zeros",
                kernel_regularizer=self._reg if com_treino else None)
            x = d(x)
            if i < ultima_oculta:
                x = _camada_ativacao(self.activation)(x)
                if com_treino and self.dropout > 0:
                    x = layers.Dropout(self.dropout, seed=self.seed + 100 + i)(x)
            denses.append(d)
        return keras.Model(entrada, x, name="nexus_mlp"), denses, ruido

    # ── pesos ──────────────────────────────────────────────────────────────
    @property
    def W(self):
        return [d.get_weights()[0] for d in self._dense]

    @property
    def b(self):
        return [d.get_weights()[1] for d in self._dense]

    def get(self):
        return [w.copy() for w in self.W], [b.copy() for b in self.b]

    def set(self, state):
        W, b = state
        if len(W) != len(self._dense) or len(b) != len(self._dense):
            raise ValueError(f"expected {len(self._dense)} layers of weights, got {len(W)}")
        for d, w, bias in zip(self._dense, W, b):
            d.set_weights([np.asarray(w, dtype=np.float32), np.asarray(bias, dtype=np.float32)])

    @classmethod
    def from_arrays(cls, sizes, activation, W, b):
        net = cls(sizes, activation)
        net.set((W, b))
        return net

    # ── uso ────────────────────────────────────────────────────────────────
    _COMPILAR_APOS = 5      # chamadas "soltas" antes de compilar: traçar o grafo custa ~20–70 ms

    def _inferir(self, X: np.ndarray) -> np.ndarray:
        """Redes de vida curta rodam direto (eager); a que é usada várias vezes (a palavra de
        ativação, a voz) ganha um grafo compilado, ~4× mais rápido por chamada."""
        self._chamadas = getattr(self, "_chamadas", 0) + 1
        fn = getattr(self, "_fn", None)
        if fn is None and self._chamadas > self._COMPILAR_APOS:
            fn = self._fn = tf.function(
                lambda a: self.model(a, training=False), autograph=False,
                input_signature=[tf.TensorSpec([None, self.sizes[0]], tf.float32)])
        if fn is not None:
            return fn(X).numpy()
        return np.asarray(self.model(X, training=False))

    def predict(self, X):
        X = np.atleast_2d(np.asarray(X, dtype=np.float32))
        if len(X) <= 16384:
            return self._inferir(X)
        return np.concatenate([self._inferir(X[i:i + 16384]) for i in range(0, len(X), 16384)])

    def para_keras(self) -> "keras.Model":
        """Modelo Keras só de inferência (sem ruído, dropout ou regularização), pronto para .save()."""
        modelo, denses, _ = self._montar(com_treino=False)
        for d, w, bias in zip(denses, self.W, self.b):
            d.set_weights([w, bias])
        return modelo


# ══ 3. Treino ═════════════════════════════════════════════════════════════════

def _sse(y_true, y_pred):
    """Regressão: soma dos erros ao quadrado por amostra (igual ao motor NumPy)."""
    return ops.sum(ops.square(y_pred - y_true), axis=-1)


def _otimizador(nome: str, lr: float, wd: float = 0.0):
    comum = dict(learning_rate=lr, global_clipnorm=5.0)
    if nome == "sgd":
        return keras.optimizers.SGD(**comum)
    if nome == "momentum":
        return keras.optimizers.SGD(momentum=0.9, **comum)
    if nome == "nesterov":
        return keras.optimizers.SGD(momentum=0.9, nesterov=True, **comum)
    if nome == "rmsprop":
        return keras.optimizers.RMSprop(rho=0.9, epsilon=1e-8, **comum)
    if nome == "adam":
        return keras.optimizers.Adam(beta_1=0.9, beta_2=0.999, epsilon=1e-8, **comum)
    opt = keras.optimizers.AdamW(weight_decay=wd, beta_1=0.9, beta_2=0.999, epsilon=1e-8, **comum)
    opt.exclude_from_weight_decay(var_names=["bias"])        # só os pesos, não os vieses
    return opt


class _Controle(keras.callbacks.Callback):
    """Tudo o que o Keras puro não faz do jeito do NEXUS, num lugar só:
    agenda de taxa de aprendizado (inclui 'plateau'), validação, parada antecipada com
    restauração do melhor ponto, máscara de poda e detecção de divergência."""

    def __init__(self, net, hist, task, base, schedule, epochs, Xv, Yv, patience):
        super().__init__()
        self.net, self.hist, self.task = net, hist, task
        self.base, self.schedule, self.epochs, self.patience = base, schedule, epochs, patience
        self.Xv, self.Yv = Xv, Yv
        self.has_val = Xv is not None and len(Xv) > 0
        self.wv = np.ones(len(Xv)) if self.has_val else None
        self.pl, self.pl_bad = 1.0, 0
        self.best, self.best_val, self.bad = None, float("inf"), 0
        self._lr = base
        if net.mask is not None:
            self._mascaras = [ops.convert_to_tensor(m, dtype="float32") for m in net.mask]
        else:
            self._mascaras = None

    def on_epoch_begin(self, epoch, logs=None):
        self._lr = lr_at(self.schedule, epoch, self.epochs, self.base) * self.pl
        self.model.optimizer.learning_rate = self._lr

    def on_train_batch_end(self, batch, logs=None):
        if self._mascaras is not None:
            for d, m in zip(self.net._dense, self._mascaras):
                d.kernel.assign(ops.multiply(d.kernel, m))
        loss = (logs or {}).get("loss")
        if loss is not None and not math.isfinite(float(loss)):
            self.hist["diverged"] = True
            self.model.stop_training = True

    def on_epoch_end(self, epoch, logs=None):
        if self.hist["diverged"]:
            return
        self.hist["train"].append(float((logs or {}).get("loss", float("nan"))))
        self.hist["lr"].append(float(self._lr))
        self.hist["epochs_run"] = epoch + 1
        if not self.has_val:
            return
        vl = loss_and_delta(self.net.predict(self.Xv), self.Yv, self.wv, self.task)[0]
        self.hist["val"].append(vl)
        if vl < self.best_val - 1e-6:
            self.best_val, self.best, self.bad, self.pl_bad = vl, self.net.get(), 0, 0
            self.hist["best_epoch"] = epoch
        else:
            self.bad += 1
            self.pl_bad += 1
            if self.schedule == "plateau" and self.pl_bad >= 8:
                self.pl, self.pl_bad = max(self.pl * 0.5, 0.01), 0
            if self.patience and self.bad >= self.patience:
                self.hist["stopped_early"] = True
                self.model.stop_training = True

    def on_train_end(self, logs=None):
        if self.best is not None:
            self.net.set(self.best)
            self.hist["best_val"] = self.best_val
        elif self.hist["val"]:
            self.hist["best_val"] = self.hist["val"][-1]


def fit(net, X, Y, task, *, epochs=300, lr=None, optimizer="adam", schedule="cosine",
        batch=32, l2=0.0, noise=0.0, w=None, Xv=None, Yv=None, patience=0,
        seed=0, frozen_layers=()):
    """Treina `net` no lugar. Y: one-hot/probabilidades (classificação) ou (n,1).
    Devolve o histórico. Com validação + patience faz parada antecipada e
    restaura os pesos da melhor época."""
    if schedule not in SCHEDULES:
        raise ValueError(f"unknown schedule '{schedule}' (use: {', '.join(SCHEDULES)})")
    if optimizer not in OPTIMIZERS:
        raise ValueError(f"unknown optimizer '{optimizer}' (use: {', '.join(OPTIMIZERS)})")
    X = np.asarray(X, dtype=np.float32)
    Y = np.asarray(Y, dtype=np.float32)
    n = len(X)
    w = np.ones(n, np.float32) if w is None else np.asarray(w, dtype=np.float32)
    w = w / (float(w.mean()) or 1.0)                         # peso médio 1: a perda fica na mesma escala
    base = float(lr or DEFAULT_LR[optimizer])
    bs = n if (not batch or batch >= n) else max(1, int(batch))
    if Xv is not None:
        Xv = np.asarray(Xv, dtype=np.float32)
    hist = {"train": [], "val": [], "lr": [], "best_epoch": 0, "epochs_run": 0,
            "best_val": None, "stopped_early": False, "diverged": False}

    frozen = {int(i) for i in frozen_layers}
    for i, d in enumerate(net._dense):                       # congelar = layer.trainable = False
        d.trainable = i not in frozen
    net._ruido.std.assign(float(noise))
    net._reg.coef.assign(0.0 if optimizer == "adamw" else float(l2) / 2.0)

    perda = (keras.losses.CategoricalCrossentropy(from_logits=True)
             if task == "classification" else _sse)
    net.model.compile(optimizer=_otimizador(optimizer, base, wd=l2 if optimizer == "adamw" else 0.0),
                      loss=perda, jit_compile=False)
    dados = (tf.data.Dataset.from_tensor_slices((X, Y, w))
             .shuffle(n, seed=int(seed), reshuffle_each_iteration=True)
             .batch(bs).prefetch(1))
    controle = _Controle(net, hist, task, base, schedule, epochs, Xv, Yv, patience)
    try:
        # shuffle=False: o embaralhamento (reproduzível) já é feito pelo tf.data acima
        net.model.fit(dados, epochs=epochs, callbacks=[controle], verbose=0, shuffle=False)
    finally:
        for d in net._dense:
            d.trainable = True
    return hist


def train_member(in_dim, out_dim, cfg, X, Y, task, w, Xv, Yv, seed, epochs, patience):
    """Cria e treina uma rede. Se divergir, tenta de novo com taxa menor."""
    lr = cfg.get("lr")
    for attempt in range(3):
        net = MLP([in_dim] + list(cfg["hidden"]) + [out_dim], cfg["activation"],
                  seed=seed + 1000 * attempt, dropout=cfg.get("dropout", 0.0))
        h = fit(net, X, Y, task, epochs=epochs, lr=lr, optimizer=cfg["optimizer"],
                schedule=cfg["schedule"], batch=cfg["batch"], l2=cfg["l2"],
                noise=cfg.get("noise", 0.0), w=w, Xv=Xv, Yv=Yv, patience=patience,
                seed=seed)
        if not h["diverged"] and all(np.isfinite(x).all() for x in net.W):
            return net, h
        lr = (lr or DEFAULT_LR[cfg["optimizer"]]) * 0.3
    return net, h


# ══ 5. Modelo final ═══════════════════════════════════════════════════════════

def _listar(a) -> list:
    """Array → lista JSON com 5 casas (via float64, para não gravar 0.12345000356…)."""
    return np.round(np.asarray(a, dtype=np.float64), 5).tolist()


class Predictor(_np.Predictor):
    """Envolve um modelo salvo (v1 ou v2): ensemble de redes Keras + pré-processamento.
    Só o construtor muda; predict_row / explain_row / outputs_enc são os do motor NumPy."""

    def __init__(self, model, nets=None):
        self.m = model
        self.task = model["task"]
        self.classes = model.get("classes")
        self.prep = Prep.from_model(model)
        act = model.get("arch", {}).get("activation", "relu")
        sizes = model.get("arch", {}).get("sizes") or model["sizes"]
        members = model.get("members") or [{"W": model["W"], "b": model["b"]}]
        self.nets = nets if nets is not None else [
            MLP.from_arrays(sizes, act, m["W"], m["b"]) for m in members]
        self.y_mean = model.get("y_mean", 0.0)
        self.y_std = model.get("y_std", 1.0)


def prune(nets, sparsity):
    """Poda por magnitude (global, entre todas as redes do ensemble). Os zeros ficam
    garantidos nos treinos seguintes pelo callback `_Controle`."""
    sparsity = min(max(float(sparsity), 0.0), 0.95)
    if sparsity <= 0:
        return 0.0
    allw = np.concatenate([np.abs(W).ravel() for n in nets for W in n.W])
    thr = np.quantile(allw, sparsity)
    zeros = total = 0
    for n in nets:
        pesos, vieses = n.W, n.b
        n.mask = [(np.abs(W) > thr).astype(np.float32) for W in pesos]
        n.set(([W * m for W, m in zip(pesos, n.mask)], vieses))
        for m in n.mask:
            zeros += int((m == 0).sum())
            total += m.size
    return zeros / max(1, total)


# ══ 4. Busca de hiperparâmetros ═══════════════════════════════════════════════

def hyper_search(in_dim, out_dim, X, Y, w, Xv, Yv, task, base_cfg, mode="random",
                 trials=12, budget_s=25.0, epochs=150, seed=0, log=lambda m: None):
    """Devolve lista [(val_loss, cfg)] ordenada (melhor primeiro)."""
    rng = np.random.default_rng(seed)
    cands = [dict(base_cfg)]
    if mode == "grid":
        keys = list(GRID)
        combos = list(itertools.product(*(GRID[k] for k in keys)))
        step = max(1, len(combos) // max(1, trials))
        for c in combos[::step][:trials]:
            cands.append({**base_cfg, **dict(zip(keys, c))})
    else:
        for _ in range(max(0, trials - 1)):
            c = dict(base_cfg)
            for k, opts in SPACE.items():
                c[k] = opts[int(rng.integers(len(opts)))]
            cands.append(c)
    t0, board = time.time(), []
    for i, c in enumerate(cands):
        if i and time.time() - t0 > budget_s:
            log(f"search: time budget reached after {i} trials")
            break
        net, h = train_member(in_dim, out_dim, c, X, Y, task, w, Xv, Yv, seed + i,
                              min(epochs, 150), 15)
        if h["diverged"] or h["best_val"] is None:
            continue
        board.append((float(h["best_val"]), c))
    board.sort(key=lambda t: t[0])
    return board


# ══ Orquestração ══════════════════════════════════════════════════════════════

def _to_model(nets, task, classes, prep, y_mean, y_std, names):
    return {
        "version": 2, "backend": "keras", "task": task, "classes": classes, "prep": prep.to_dict(),
        "y_mean": y_mean, "y_std": y_std,
        "arch": {"sizes": nets[0].sizes, "activation": nets[0].activation},
        "members": [{"W": [_listar(W) for W in n.W], "b": [_listar(b) for b in n.b]} for n in nets],
        "features": len(names), "feature_names": names,
    }


def train_pipeline(header, rows, opts=None, log=lambda m: None):
    """Treina um modelo completo. Devolve (model_dict, report_dict)."""
    o = {**DEFAULT_OPTS, **{k: v for k, v in (opts or {}).items() if v is not None}}
    t_start = time.time()
    seed = int(o["seed"])
    names, feats, raw_y, etl = clean_rows(header, rows)
    if len(feats) < 3:
        raise ValueError("dataset needs at least 3 usable rows")
    task, classes, y = _prepare_target(raw_y, o["task"])
    n = len(feats)
    k = len(classes) if classes else 1

    # split estratificado
    if n >= 30:
        tr, va, te = split_idx(n, y if task == "classification" else None, (0.70, 0.15, 0.15), seed)
    elif n >= 10:
        tr, te = split_idx(n, y if task == "classification" else None, (0.8, 0.2), seed)
        va = np.array([], dtype=int)
    else:
        tr, va, te = np.arange(n), np.array([], dtype=int), np.array([], dtype=int)

    prep = Prep().fit([feats[i] for i in tr], names)
    X = prep.transform(feats)
    in_dim = X.shape[1]
    y_mean = y_std = 0.0
    if task == "regression":
        y_mean, y_std = float(y[tr].mean()), float(y[tr].std()) or 1.0
        yt = (y - y_mean) / y_std
    else:
        yt = y

    Xtr, ytr = X[tr], yt[tr]
    rng = np.random.default_rng(seed)

    auto = bool(o["auto"])
    balance = o["balance"]
    if auto and task == "classification":
        cnt = np.bincount(y[tr], minlength=k)
        if cnt.max() > 1.5 * max(1, cnt[cnt > 0].min()):
            balance = "weights"

    # dados sintéticos / oversampling (só no treino — validação e teste ficam puros)
    added = 0
    if task == "classification" and balance == "oversample":
        cnt = np.bincount(ytr, minlength=k)
        per = {c: int(cnt.max() - cnt[c]) for c in range(k) if 0 < cnt[c] < cnt.max()}
        xs, ys = synth_rows(Xtr, ytr, sum(per.values()), task, rng, per_class=per)
        if len(xs):
            Xtr, ytr, added = np.vstack([Xtr, xs]), np.concatenate([ytr, ys]), added + len(xs)
    if float(o["synthetic"]) > 0:
        xs, ys = synth_rows(Xtr, ytr, int(round(float(o["synthetic"]) * len(Xtr))), task, rng)
        if len(xs):
            Xtr, ytr, added = np.vstack([Xtr, xs]), np.concatenate([ytr, ys]), added + len(xs)

    if task == "classification":
        Ytr = _onehot(ytr.astype(int), k)
        Yva = _onehot(y[va], k) if len(va) else None
        wtr = class_weights(ytr.astype(int), k) if balance == "weights" else None
    else:
        Ytr, Yva, wtr = ytr.reshape(-1, 1), (yt[va].reshape(-1, 1) if len(va) else None), None
    Xva = X[va] if len(va) else None
    out_dim = k if task == "classification" else 1

    cfg = {key: o[key] for key in DEFAULT_CFG}
    cfg["hidden"] = parse_hidden(o["hidden"], in_dim)
    patience = int(o["patience"]) if len(va) else 0
    epochs = int(o["epochs"])

    # busca de hiperparâmetros / AutoML
    board, member_cfgs = [], None
    mode = o["search"] if o["search"] in ("random", "grid") else ("random" if auto else "none")
    if mode != "none":
        sX, sY, sw, sXv, sYv = Xtr, Ytr, wtr, Xva, Yva
        if sXv is None:                                    # sem validação: separa um pedaço
            a, b = split_idx(len(Xtr), None, (0.8, 0.2), seed)
            sX, sY, sXv, sYv = Xtr[a], Ytr[a], Xtr[b], Ytr[b]
            sw = wtr[a] if wtr is not None else None
        log(f"search ({mode}): up to {o['trials']} trials…")
        board = hyper_search(in_dim, out_dim, sX, sY, sw, sXv, sYv, task, cfg, mode,
                             int(o["trials"]), float(o["budget_s"]), epochs, seed, log)
        if board:
            cfg = dict(board[0][1])
            if auto:
                member_cfgs = [dict(c) for _, c in board[:3]]

    n_members = max(int(o["ensemble"]), len(member_cfgs) if member_cfgs else 1, 1)
    if auto:
        n_members = max(n_members, 3 if len(Xtr) >= 20 else 1)
    n_members = min(n_members, 10)
    members, hist0 = [], None
    for m in range(n_members):
        c = (member_cfgs[m % len(member_cfgs)] if member_cfgs else cfg)
        if m > 0 and n_members > 1:                        # bagging: amostra com reposição
            pick = rng.integers(0, len(Xtr), len(Xtr))
            xm, ym = Xtr[pick], Ytr[pick]
            wm = wtr[pick] if wtr is not None else None
        else:
            xm, ym, wm = Xtr, Ytr, wtr
        net, h = train_member(in_dim, out_dim, c, xm, ym, task, wm, Xva, Yva,
                              seed + 17 * m, epochs, patience)
        members.append(net)
        hist0 = hist0 or h
        log(f"member {m + 1}/{n_members}: {h['epochs_run']} epochs"
            f"{' (early stop)' if h['stopped_early'] else ''}")

    def to_model(nets):
        return _to_model(nets, task, classes, prep, y_mean, y_std, names)

    def evaluate(nets, idx):
        p = Predictor(to_model(nets), nets=nets)           # reaproveita as redes já treinadas
        if len(idx) == 0:
            return {}, p
        out = p.outputs_enc(X[idx])
        return metrics(task, out, y[idx], k if task == "classification" else None), p

    m_tr, pred = evaluate(members, tr)
    m_te, _ = evaluate(members, te)
    ev_idx = te if len(te) >= 3 else tr
    imp = permutation_importance(pred, X[ev_idx], y[ev_idx], seed=seed) if len(ev_idx) >= 3 else []

    # compressão (poda + ajuste fino com a máscara)
    sparsity, m_pruned = 0.0, None
    if float(o["compress"]) > 0:
        sparsity = prune(members, float(o["compress"]))
        for i, net in enumerate(members):
            fit(net, Xtr, Ytr, task, epochs=max(20, epochs // 5), lr=(cfg["lr"] or DEFAULT_LR[cfg["optimizer"]]) * 0.3,
                optimizer=cfg["optimizer"], schedule="constant", batch=cfg["batch"],
                l2=cfg["l2"], w=wtr, seed=seed + i)
        m_pruned, pred = evaluate(members, te if len(te) else tr)

    model = to_model(members)
    final_te = m_pruned if m_pruned is not None else m_te
    if task == "classification":
        quality = f"training accuracy {m_tr['accuracy'] * 100:.0f}%"
        held = (f", held-out accuracy {final_te['accuracy'] * 100:.0f}% "
                f"(F1 {final_te['f1'] * 100:.0f}%)") if final_te else \
            " (small dataset — no held-out split)"
    else:
        quality = f"training MSE {m_tr['mse'] * 1.0:.3f}"
        held = (f", held-out MSE {final_te['mse']:.3f} (R² {final_te['r2']:.2f}, "
                f"MAE {final_te['mae']:.3f})") if final_te else \
            " (small dataset — no held-out split)"
    # baseline para o monitoramento de drift
    if task == "classification":
        base_conf = float(pred.outputs_enc(X[ev_idx]).max(axis=1).mean())
    else:
        base_conf = None
    model.update({"quality": quality, "metrics": {"train": m_tr, "test": final_te},
                  "config": cfg, "ensemble": n_members, "sparsity": sparsity,
                  "importance": [[a, round(b, 4)] for a, b in imp],
                  "baseline": {"conf_mean": base_conf, "n": int(len(ev_idx))},
                  "created": time.strftime("%Y-%m-%d %H:%M")})
    report = {
        "task": task, "classes": classes, "samples": n, "features": len(names),
        "encoded_features": in_dim, "quality": quality, "held_out": held,
        "config": cfg, "ensemble": n_members, "synthetic_added": added,
        "balance": balance, "etl": etl, "metrics": model["metrics"],
        "importance": imp, "history": hist0, "sparsity": sparsity,
        "pruned_before": m_te if m_pruned is not None else None,
        "leaderboard": [(round(s, 4), c) for s, c in board[:5]],
        "splits": (len(tr), len(va), len(te)), "seconds": round(time.time() - t_start, 1),
        "auto": auto, "search_mode": mode, "backend": "keras",
    }
    return model, report


# ── ajuste fino / destilação / compressão de um modelo já treinado ────────────

def _dataset_for(model, header, rows):
    pred = Predictor(model)
    names, feats, raw_y, _ = clean_rows(header, rows)
    if len(names) != len(pred.prep.cols):
        raise ValueError(f"model expects {len(pred.prep.cols)} features, data has {len(names)}")
    task, _, y = _prepare_target(raw_y, pred.task, pred.classes)
    X = pred.prep.transform(feats)
    return pred, X, y


def _rebuild(model, pred, nets):
    m = dict(model)
    m["arch"] = {"sizes": nets[0].sizes, "activation": nets[0].activation}
    m["members"] = [{"W": [_listar(W) for W in n.W], "b": [_listar(b) for b in n.b]} for n in nets]
    m.pop("sizes", None); m.pop("W", None); m.pop("b", None)
    m["version"] = 2
    m["backend"] = "keras"
    return m


def finetune(model, header, rows, epochs=80, lr=None, freeze=0, seed=1, log=lambda m: None):
    """Continua o treino de um modelo com dados novos (taxa baixa), congelando as
    primeiras `freeze` camadas (layer.trainable = False) — o "transfer learning"
    possível para dados tabulares."""
    pred, X, y = _dataset_for(model, header, rows)
    n = len(X)
    tr, te = (split_idx(n, y if pred.task == "classification" else None, (0.8, 0.2), seed)
              if n >= 10 else (np.arange(n), np.array([], dtype=int)))
    before = metrics(pred.task, pred.outputs_enc(X[te]), y[te]) if len(te) else {}
    if pred.task == "classification":
        Y = _onehot(y, len(pred.classes))
    else:
        Y = ((y - pred.y_mean) / pred.y_std).reshape(-1, 1)
    nets = pred.nets
    if freeze >= len(nets[0].W):
        raise ValueError("cannot freeze every layer")
    cfg = model.get("config", DEFAULT_CFG)
    opt = cfg.get("optimizer", "adam")
    for i, net in enumerate(nets):
        fit(net, X[tr], Y[tr], pred.task, epochs=epochs,
            lr=lr or DEFAULT_LR[opt] * 0.3, optimizer=opt, schedule="cosine",
            batch=cfg.get("batch", 32), l2=cfg.get("l2", 1e-4), seed=seed + i,
            frozen_layers=range(int(freeze)))
    new = _rebuild(model, pred, nets)
    pred2 = Predictor(new, nets=nets)
    after = metrics(pred.task, pred2.outputs_enc(X[te]), y[te]) if len(te) else {}
    return new, {"before": before, "after": after, "samples": n, "frozen": int(freeze)}


def distill(model, header, rows, hidden=None, epochs=300, alpha=0.7, temperature=2.0,
            seed=3, log=lambda m: None):
    """Treina uma rede pequena (aluna) para imitar o ensemble (professor)."""
    pred, X, y = _dataset_for(model, header, rows)
    n = len(X)
    tr, te = (split_idx(n, y if pred.task == "classification" else None, (0.8, 0.2), seed)
              if n >= 10 else (np.arange(n), np.array([], dtype=int)))
    in_dim = X.shape[1]
    hidden = parse_hidden(hidden or [max(4, in_dim * 2)], in_dim)
    teacher = pred.outputs_enc(X)
    rng = np.random.default_rng(seed)
    Xa = np.vstack([X[tr], X[tr] + rng.normal(0, 0.05, X[tr].shape)])   # ruído amplia os exemplos
    if pred.task == "classification":
        k = len(pred.classes)
        soft = teacher ** (1.0 / temperature)
        soft /= soft.sum(axis=1, keepdims=True)
        Yt = alpha * soft + (1 - alpha) * _onehot(y, k)
        Ya = np.vstack([Yt[tr], Yt[tr]])
        out_dim = k
    else:
        Yt = ((alpha * teacher + (1 - alpha) * y - pred.y_mean) / pred.y_std).reshape(-1, 1)
        Ya = np.vstack([Yt[tr], Yt[tr]])
        out_dim = 1
    cfg = {**DEFAULT_CFG, "hidden": hidden, "activation": pred.nets[0].activation, "l2": 1e-4}
    net, h = train_member(in_dim, out_dim, cfg, Xa, Ya, pred.task, None, None, None, seed, epochs, 0)
    new = _rebuild(model, pred, [net])
    new["config"] = cfg; new["ensemble"] = 1; new["sparsity"] = 0.0
    sp = Predictor(new, nets=[net])
    ev = te if len(te) else tr
    t_out, s_out = pred.outputs_enc(X[ev]), sp.outputs_enc(X[ev])
    info = {"teacher": metrics(pred.task, t_out, y[ev], len(pred.classes or [1])),
            "student": metrics(pred.task, s_out, y[ev], len(pred.classes or [1])),
            "student_params": sum(w.size + b.size for w, b in zip(net.W, net.b)),
            "teacher_params": sum(w.size + b.size for n_ in pred.nets for w, b in zip(n_.W, n_.b)),
            "hidden": hidden}
    if pred.task == "classification":
        info["agreement"] = float((t_out.argmax(1) == s_out.argmax(1)).mean())
    return new, info


def compress(model, header=None, rows=None, sparsity=0.5, seed=5):
    """Poda por magnitude. Com dados, faz ajuste fino com a máscara e compara."""
    pred = Predictor(model)
    info = {"before": {}, "after": {}}
    X = y = Y = None
    if rows:
        pred, X, y = _dataset_for(model, header, rows)
        info["before"] = metrics(pred.task, pred.outputs_enc(X), y,
                                 len(pred.classes or [1]))
    total = sum(w.size for n in pred.nets for w in n.W)
    real = prune(pred.nets, sparsity)
    if X is not None:
        Y = (_onehot(y, len(pred.classes)) if pred.task == "classification"
             else ((y - pred.y_mean) / pred.y_std).reshape(-1, 1))
        cfg = model.get("config", DEFAULT_CFG)
        opt = cfg.get("optimizer", "adam")
        for i, net in enumerate(pred.nets):
            fit(net, X, Y, pred.task, epochs=60, lr=DEFAULT_LR[opt] * 0.3, optimizer=opt,
                schedule="constant", batch=cfg.get("batch", 32), seed=seed + i)
    new = _rebuild(model, pred, pred.nets)
    new["sparsity"] = real
    if X is not None:
        info["after"] = metrics(pred.task, Predictor(new, nets=pred.nets).outputs_enc(X), y,
                                len(pred.classes or [1]))
    info.update({"sparsity": real, "weights": total})
    return new, info


# ── exportar para o formato nativo do Keras ───────────────────────────────────

def to_keras_model(model, member: int = 0) -> "keras.Model":
    """Um membro do ensemble como keras.Model de inferência (sem pré-processamento)."""
    return Predictor(model).nets[member].para_keras()


def export_keras(model, path, member: int = 0) -> str:
    """Salva um membro do modelo no formato nativo `.keras` (abre em qualquer TensorFlow/Keras)."""
    path = str(path)
    if not path.endswith(".keras"):
        path += ".keras"
    to_keras_model(model, member).save(path)
    return path
