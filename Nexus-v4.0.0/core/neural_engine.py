"""Motor da rede neural do NEXUS — NumPy puro, sem bibliotecas de ML.

Camadas independentes (cada uma pode ser usada ou trocada sem mexer nas outras):

  1. Pipeline de dados   Prep (numéricos + categóricos, faltantes, outliers),
                         split estratificado, SMOTE, pesos de classe, dados sintéticos
  2. Rede                MLP com N camadas, 7 ativações, dropout, máscara de poda
  3. Treino              SGD/Momentum/Nesterov/RMSprop/Adam/AdamW, agendas de taxa
                         de aprendizado, lotes, L2, ruído (aumento de dados),
                         parada antecipada com restauração do melhor ponto
  4. Busca               grid / random search e AutoML (busca + ensemble dos melhores)
  5. Modelo final        Ensemble (bagging), importância por permutação,
                         explicação por oclusão, poda + arredondamento (compressão),
                         destilação, ajuste fino com camadas congeladas

Tudo aqui é puro: não lê nem grava arquivos (isso fica em actions/neural_core.py).
"""
from __future__ import annotations

import itertools
import math
import time

import numpy as np

# ══ 2. Rede ═══════════════════════════════════════════════════════════════════

def _sig(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -60, 60)))


_GC = math.sqrt(2.0 / math.pi)


def _gelu(z):
    return 0.5 * z * (1 + np.tanh(_GC * (z + 0.044715 * z ** 3)))


def _gelu_d(z, a):
    t = np.tanh(_GC * (z + 0.044715 * z ** 3))
    return 0.5 * (1 + t) + 0.5 * z * (1 - t * t) * _GC * (1 + 3 * 0.044715 * z * z)


# nome → (f(z), derivada(z, a)) onde a = f(z)
ACTIVATIONS = {
    "relu":       (lambda z: np.maximum(z, 0.0), lambda z, a: (z > 0).astype(float)),
    "leaky_relu": (lambda z: np.where(z > 0, z, 0.01 * z), lambda z, a: np.where(z > 0, 1.0, 0.01)),
    "tanh":       (np.tanh, lambda z, a: 1.0 - a * a),
    "sigmoid":    (_sig, lambda z, a: a * (1.0 - a)),
    "elu":        (lambda z: np.where(z > 0, z, np.expm1(np.minimum(z, 0.0))),
                   lambda z, a: np.where(z > 0, 1.0, a + 1.0)),
    "gelu":       (_gelu, _gelu_d),
    "swish":      (lambda z: z * _sig(z), lambda z, a: _sig(z) * (1.0 + z * (1.0 - _sig(z)))),
}


class MLP:
    """Rede feed-forward: sizes = [entrada, h1, ..., saída]."""

    def __init__(self, sizes, activation="relu", seed=42, dropout=0.0):
        if activation not in ACTIVATIONS:
            raise ValueError(f"unknown activation '{activation}' "
                             f"(use: {', '.join(ACTIVATIONS)})")
        self.sizes = [int(s) for s in sizes]
        self.activation = activation
        self.dropout = float(dropout)
        self.mask = None                       # poda: lista de máscaras 0/1 por W
        rng = np.random.default_rng(seed)
        gain = 1.0 if activation in ("tanh", "sigmoid") else 2.0
        self.W, self.b = [], []
        last = len(self.sizes) - 2
        for i in range(len(self.sizes) - 1):
            g = gain if i < last else 1.0
            self.W.append(rng.normal(0.0, math.sqrt(g / self.sizes[i]),
                                     (self.sizes[i], self.sizes[i + 1])))
            self.b.append(np.zeros(self.sizes[i + 1]))

    def forward(self, X, rng=None):
        f = ACTIVATIONS[self.activation][0]
        train = rng is not None and self.dropout > 0
        cache = {"zs": [], "raw": [], "ins": [X], "masks": []}
        a, last = X, len(self.W) - 1
        for i, (W, b) in enumerate(zip(self.W, self.b)):
            z = a @ W + b
            if i == last:
                raw, m, a = z, None, z
            else:
                raw, m = f(z), None
                a = raw
                if train:
                    m = (rng.random(raw.shape) >= self.dropout) / (1.0 - self.dropout)
                    a = raw * m
            cache["zs"].append(z); cache["raw"].append(raw)
            cache["masks"].append(m); cache["ins"].append(a)
        return a, cache

    def backward(self, cache, delta, l2=0.0):
        df = ACTIVATIONS[self.activation][1]
        L = len(self.W)
        gW, gb, d = [None] * L, [None] * L, delta
        for i in range(L - 1, -1, -1):
            gW[i] = cache["ins"][i].T @ d + l2 * self.W[i]
            gb[i] = d.sum(axis=0)
            if i > 0:
                d = d @ self.W[i].T
                m = cache["masks"][i - 1]
                if m is not None:
                    d = d * m
                d = d * df(cache["zs"][i - 1], cache["raw"][i - 1])
        return gW, gb

    def predict(self, X):
        return self.forward(X)[0]

    def get(self):
        return [w.copy() for w in self.W], [b.copy() for b in self.b]

    def set(self, state):
        self.W = [w.copy() for w in state[0]]
        self.b = [b.copy() for b in state[1]]

    @classmethod
    def from_arrays(cls, sizes, activation, W, b):
        net = cls(sizes, activation)
        net.W = [np.array(w, dtype=float) for w in W]
        net.b = [np.array(x, dtype=float) for x in b]
        return net


def softmax(A):
    e = np.exp(A - A.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


def loss_and_delta(out, Y, w, task):
    sw = float(w.sum()) or 1.0
    if task == "classification":
        P = softmax(out)
        loss = -float((w * (Y * np.log(P + 1e-12)).sum(axis=1)).sum()) / sw
        return loss, (P - Y) * w[:, None] / sw
    diff = out - Y
    loss = float((w * (diff ** 2).sum(axis=1)).sum()) / sw
    return loss, 2.0 * diff * w[:, None] / sw


# ══ 3. Treino ═════════════════════════════════════════════════════════════════

OPTIMIZERS = ("sgd", "momentum", "nesterov", "rmsprop", "adam", "adamw")
SCHEDULES = ("constant", "step", "exp", "cosine", "warmup_cosine", "plateau")
DEFAULT_LR = {"sgd": 0.1, "momentum": 0.03, "nesterov": 0.03,
              "rmsprop": 0.003, "adam": 0.01, "adamw": 0.01}


class Optimizer:
    def __init__(self, name, params, wd=0.0):
        if name not in OPTIMIZERS:
            raise ValueError(f"unknown optimizer '{name}' (use: {', '.join(OPTIMIZERS)})")
        self.name, self.wd, self.t = name, wd, 0
        self.m = [np.zeros_like(p) for p in params]
        self.v = [np.zeros_like(p) for p in params]

    def step(self, params, grads, lr, frozen=()):
        self.t += 1
        n = self.name
        for k, (p, g) in enumerate(zip(params, grads)):
            if k in frozen:
                continue
            if n == "sgd":
                p -= lr * g
            elif n in ("momentum", "nesterov"):
                self.m[k] = 0.9 * self.m[k] + g
                p -= lr * ((g + 0.9 * self.m[k]) if n == "nesterov" else self.m[k])
            elif n == "rmsprop":
                self.v[k] = 0.9 * self.v[k] + 0.1 * g * g
                p -= lr * g / (np.sqrt(self.v[k]) + 1e-8)
            else:                                         # adam / adamw
                self.m[k] = 0.9 * self.m[k] + 0.1 * g
                self.v[k] = 0.999 * self.v[k] + 0.001 * g * g
                mh = self.m[k] / (1 - 0.9 ** self.t)
                vh = self.v[k] / (1 - 0.999 ** self.t)
                p -= lr * mh / (np.sqrt(vh) + 1e-8)
                if n == "adamw" and k % 2 == 0:           # só pesos, não vieses
                    p -= lr * self.wd * p


def lr_at(kind, e, total, base):
    total = max(1, total)
    if kind == "step":
        return base * 0.5 ** (e // max(1, total // 4))
    if kind == "exp":
        return base * 0.05 ** (e / total)
    if kind == "cosine":
        return max(0.02 * base, 0.5 * base * (1 + math.cos(math.pi * e / total)))
    if kind == "warmup_cosine":
        w = max(1, int(0.05 * total))
        if e < w:
            return base * (e + 1) / w
        return max(0.02 * base, 0.5 * base * (1 + math.cos(math.pi * (e - w) / max(1, total - w))))
    return base


def fit(net, X, Y, task, *, epochs=300, lr=None, optimizer="adam", schedule="cosine",
        batch=32, l2=0.0, noise=0.0, w=None, Xv=None, Yv=None, patience=0,
        seed=0, frozen_layers=()):
    """Treina `net` no lugar. Y: one-hot/probabilidades (classificação) ou (n,1).
    Devolve o histórico. Com validação + patience faz parada antecipada e
    restaura os pesos da melhor época."""
    if schedule not in SCHEDULES:
        raise ValueError(f"unknown schedule '{schedule}' (use: {', '.join(SCHEDULES)})")
    rng = np.random.default_rng(seed)
    n = len(X)
    w = np.ones(n) if w is None else np.asarray(w, dtype=float)
    base = float(lr or DEFAULT_LR[optimizer])
    params = []
    for W, b in zip(net.W, net.b):
        params += [W, b]
    opt = Optimizer(optimizer, params, wd=l2 if optimizer == "adamw" else 0.0)
    l2g = 0.0 if optimizer == "adamw" else l2
    frozen = {2 * i + j for i in frozen_layers for j in (0, 1)}
    bs = n if (not batch or batch >= n) else max(1, int(batch))
    has_val = Xv is not None and len(Xv) > 0
    wv = np.ones(len(Xv)) if has_val else None
    hist = {"train": [], "val": [], "lr": [], "best_epoch": 0, "epochs_run": 0,
            "best_val": None, "stopped_early": False, "diverged": False}
    best, best_val, bad, pl, pl_bad = None, float("inf"), 0, 1.0, 0

    for e in range(epochs):
        lr_e = lr_at(schedule, e, epochs, base) * pl
        order = rng.permutation(n)
        tot = 0.0
        for s in range(0, n, bs):
            idx = order[s:s + bs]
            xb = X[idx]
            if noise > 0:
                xb = xb + rng.normal(0.0, noise, xb.shape)
            out, cache = net.forward(xb, rng)
            loss, delta = loss_and_delta(out, Y[idx], w[idx], task)
            gW, gb = net.backward(cache, delta, l2g)
            grads = []
            for a, b in zip(gW, gb):
                grads += [a, b]
            norm = math.sqrt(sum(float((g * g).sum()) for g in grads))
            if not math.isfinite(norm):
                hist["diverged"] = True
                break
            if norm > 5.0:
                grads = [g * (5.0 / norm) for g in grads]
            opt.step(params, grads, lr_e, frozen)
            if net.mask is not None:
                for i, m in enumerate(net.mask):
                    net.W[i] *= m
            tot += loss * len(idx)
        if hist["diverged"]:
            break
        hist["train"].append(tot / n); hist["lr"].append(lr_e)
        hist["epochs_run"] = e + 1
        if has_val:
            vl = loss_and_delta(net.predict(Xv), Yv, wv, task)[0]
            hist["val"].append(vl)
            if vl < best_val - 1e-6:
                best_val, best, bad, pl_bad = vl, net.get(), 0, 0
                hist["best_epoch"] = e
            else:
                bad += 1; pl_bad += 1
                if schedule == "plateau" and pl_bad >= 8:
                    pl, pl_bad = max(pl * 0.5, 0.01), 0
                if patience and bad >= patience:
                    hist["stopped_early"] = True
                    break
    if best is not None:
        net.set(best)
        hist["best_val"] = best_val
    elif hist["val"]:
        hist["best_val"] = hist["val"][-1]
    return hist


DEFAULT_CFG = {"hidden": None, "activation": "relu", "optimizer": "adam", "lr": None,
               "schedule": "cosine", "batch": 32, "l2": 1e-4, "dropout": 0.0, "noise": 0.0}


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


# ══ 1. Pipeline de dados ══════════════════════════════════════════════════════

MISSING = {"", "na", "nan", "null", "none", "?", "n/a"}


def _num(s):
    if isinstance(s, (int, float, np.number)):
        return float(s)
    try:
        return float(str(s).strip().replace(",", "."))
    except ValueError:
        return None


def _is_missing(v):
    return str(v).strip().lower() in MISSING


class Prep:
    """Transforma linhas cruas (texto) em matriz numérica.

    Numéricos: faltantes → mediana, outliers cortados em p1..p99 (≥50 linhas),
    padronização. Texto: one-hot das 20 categorias mais comuns (as demais e as
    inéditas viram "outro" = tudo zero; faltante é uma categoria própria)."""

    def __init__(self, names=None, cols=None):
        self.names, self.cols = names or [], cols or []

    def fit(self, rows, names):
        self.names, self.cols = list(names), []
        for j in range(len(names)):
            vals = [r[j] for r in rows]
            nums = [_num(v) for v in vals if not _is_missing(v)]
            if nums and all(x is not None for x in nums):
                a = np.array(nums, dtype=float)
                lo, hi = ((np.percentile(a, 1), np.percentile(a, 99))
                          if len(a) >= 50 else (a.min(), a.max()))
                c = np.clip(a, lo, hi)
                self.cols.append({"kind": "num", "fill": float(np.median(a)),
                                  "lo": float(lo), "hi": float(hi),
                                  "mean": float(c.mean()),
                                  "std": float(c.std()) or 1.0})
            else:
                cnt = {}
                for v in vals:
                    k = "__missing__" if _is_missing(v) else str(v).strip()
                    cnt[k] = cnt.get(k, 0) + 1
                cats = [k for k, _ in sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))][:20]
                self.cols.append({"kind": "cat", "cats": cats})
        return self

    def transform(self, rows, clip=True):
        out = []
        for r in rows:
            if len(r) != len(self.cols):
                raise ValueError(f"expected {len(self.cols)} values, got {len(r)}")
            v = []
            for x, c in zip(r, self.cols):
                if c["kind"] == "num":
                    f = None if _is_missing(x) else _num(x)
                    if f is None:
                        if not _is_missing(x):
                            raise ValueError(f"'{x}' is not a number")
                        f = c["fill"]
                    if clip:
                        f = min(max(f, c["lo"]), c["hi"])
                    v.append((f - c["mean"]) / c["std"])
                else:
                    k = "__missing__" if _is_missing(x) else str(x).strip()
                    v.extend(1.0 if k == cat else 0.0 for cat in c["cats"])
            out.append(v)
        return np.array(out, dtype=float).reshape(len(rows), -1)

    @property
    def col_map(self):
        m = []
        for j, c in enumerate(self.cols):
            m += [j] * (1 if c["kind"] == "num" else len(c["cats"]))
        return m

    @property
    def width(self):
        return len(self.col_map)

    def to_dict(self):
        return {"names": self.names, "cols": self.cols}

    @classmethod
    def from_model(cls, model):
        if "prep" in model:
            return cls(model["prep"]["names"], model["prep"]["cols"])
        mean, std = model["mean"], model["std"]              # modelo v1 (só numérico)
        cols = [{"kind": "num", "fill": m, "lo": -1e18, "hi": 1e18, "mean": m,
                 "std": s or 1.0} for m, s in zip(mean, std)]
        hdr = model.get("header")
        names = hdr[:-1] if hdr else [f"x{i + 1}" for i in range(len(mean))]
        return cls(names, cols)


def split_idx(n, y_idx, fracs, seed):
    """Divide índices em partes (fracs somam 1). Estratificado se y_idx != None."""
    rng = np.random.default_rng(seed)
    parts = [[] for _ in fracs]
    groups = ([np.where(y_idx == c)[0] for c in np.unique(y_idx)]
              if y_idx is not None else [np.arange(n)])
    for g in groups:
        g = rng.permutation(g)
        cuts = np.cumsum([int(round(f * len(g))) for f in fracs[:-1]])
        for p, piece in zip(parts, np.split(g, cuts)):
            p.extend(piece.tolist())
    return [np.array(rng.permutation(p), dtype=int) for p in parts]


def class_weights(y_idx, k):
    cnt = np.bincount(y_idx, minlength=k).astype(float)
    cw = len(y_idx) / (k * np.maximum(cnt, 1.0))
    return cw[y_idx] / cw[y_idx].mean()


def synth_rows(X, y, n_new, task, rng, per_class=None, k=5):
    """SMOTE: cria linhas novas interpolando uma amostra com um vizinho próximo
    (da mesma classe; na regressão a saída é interpolada junto)."""
    if n_new <= 0 or len(X) < 2:
        return X[:0], y[:0]
    xs, ys = [], []

    def make(pool, count):
        if len(pool) < 2:
            if len(pool):
                for _ in range(count):
                    i = pool[0]
                    xs.append(X[i] + rng.normal(0, 0.05, X.shape[1])); ys.append(y[i])
            return
        D = ((X[pool][:, None, :] - X[pool][None, :, :]) ** 2).sum(axis=2)
        np.fill_diagonal(D, np.inf)
        nn = np.argsort(D, axis=1)[:, :min(k, len(pool) - 1)]
        for _ in range(count):
            a = int(rng.integers(len(pool)))
            b = int(nn[a][rng.integers(nn.shape[1])])
            lam = rng.random()
            i, j = pool[a], pool[b]
            xs.append(X[i] + lam * (X[j] - X[i]))
            ys.append(y[i] if task == "classification" else y[i] + lam * (y[j] - y[i]))

    if task == "classification":
        classes = np.unique(y)
        per = per_class or {int(c): int(math.ceil(n_new / len(classes))) for c in classes}
        for c in classes:
            make(np.where(y == c)[0], per.get(int(c), 0))
    else:
        make(np.arange(len(X)), n_new)
    return np.array(xs).reshape(-1, X.shape[1]), np.array(ys)


# ══ 5. Modelo final ═══════════════════════════════════════════════════════════

class Predictor:
    """Envolve um modelo salvo (v1 ou v2): ensemble de redes + pré-processamento."""

    def __init__(self, model):
        self.m = model
        self.task = model["task"]
        self.classes = model.get("classes")
        self.prep = Prep.from_model(model)
        act = model.get("arch", {}).get("activation", "relu")
        sizes = model.get("arch", {}).get("sizes") or model["sizes"]
        members = model.get("members") or [{"W": model["W"], "b": model["b"]}]
        self.nets = [MLP.from_arrays(sizes, act, m["W"], m["b"]) for m in members]
        self.y_mean = model.get("y_mean", 0.0)
        self.y_std = model.get("y_std", 1.0)

    def outputs_enc(self, X):
        """Classificação → probabilidades (n,k). Regressão → valores reais (n,)."""
        if self.task == "classification":
            return np.mean([softmax(n.predict(X)) for n in self.nets], axis=0)
        return np.mean([n.predict(X)[:, 0] for n in self.nets], axis=0) * self.y_std + self.y_mean

    def predict_row(self, row):
        x = self.prep.transform([row])
        raw = self.prep.transform([row], clip=False)       # sem corte: é o que o monitor de drift vê
        if self.task == "classification":
            Ps = np.array([softmax(n.predict(x))[0] for n in self.nets])
            P = Ps.mean(axis=0)
            order = np.argsort(-P)
            top = int(order[0])
            return {"task": "classification", "label": self.classes[top],
                    "confidence": float(P[top]),
                    "runner_up": (self.classes[int(order[1])], float(P[order[1]]))
                    if len(order) > 1 else None,
                    "spread": float(Ps[:, top].std()) if len(Ps) > 1 else 0.0,
                    "members": len(self.nets), "_x": raw[0], "_p": P}
        vals = np.array([n.predict(x)[0, 0] for n in self.nets]) * self.y_std + self.y_mean
        return {"task": "regression", "value": float(vals.mean()),
                "spread": float(vals.std()) if len(vals) > 1 else 0.0,
                "members": len(self.nets), "_x": raw[0]}

    def explain_row(self, row, top=5):
        """Oclusão: zera cada feature (= valor médio) e mede o quanto a saída muda."""
        x = self.prep.transform([row])
        base = self.outputs_enc(x)
        cm = np.array(self.prep.col_map)
        if self.task == "classification":
            k = int(np.argmax(base[0])); b0 = base[0][k]
        else:
            b0 = float(base[0])
        res = []
        for j, name in enumerate(self.prep.names):
            x2 = x.copy(); x2[:, cm == j] = 0.0
            o = self.outputs_enc(x2)
            v = o[0][k] if self.task == "classification" else float(o[0])
            res.append((name, float(b0 - v)))
        res.sort(key=lambda t: -abs(t[1]))
        return res[:top]


def metrics(task, out, y_true, k=None):
    """out: probabilidades (cls) ou valores reais (reg); y_true: índices ou reais."""
    if len(y_true) == 0:
        return {}
    if task == "classification":
        pred = out.argmax(axis=1)
        k = k or out.shape[1]
        f1s = []
        for c in range(k):
            tp = float(((pred == c) & (y_true == c)).sum())
            fp = float(((pred == c) & (y_true != c)).sum())
            fn = float(((pred != c) & (y_true == c)).sum())
            if tp + fn > 0:
                f1s.append(2 * tp / max(1.0, 2 * tp + fp + fn))
        return {"accuracy": float((pred == y_true).mean()),
                "f1": float(np.mean(f1s)) if f1s else 0.0}
    err = out - y_true
    var = float(((y_true - y_true.mean()) ** 2).sum())
    return {"mae": float(np.abs(err).mean()), "rmse": float(math.sqrt((err ** 2).mean())),
            "mse": float((err ** 2).mean()),
            "r2": 1.0 - float((err ** 2).sum()) / var if var > 0 else 0.0}


def _score(task, m):
    return m["accuracy"] if task == "classification" else m["r2"]


def permutation_importance(pred, X, y_true, repeats=5, seed=0):
    """Quanto o desempenho cai quando uma feature é embaralhada (por feature original)."""
    rng = np.random.default_rng(seed)
    base = _score(pred.task, metrics(pred.task, pred.outputs_enc(X), y_true))
    cm = np.array(pred.prep.col_map)
    res = []
    for j, name in enumerate(pred.prep.names):
        drops = []
        for _ in range(repeats):
            X2 = X.copy()
            perm = rng.permutation(len(X))
            X2[:, cm == j] = X[perm][:, cm == j]
            drops.append(base - _score(pred.task, metrics(pred.task, pred.outputs_enc(X2), y_true)))
        res.append((name, float(np.mean(drops))))
    res.sort(key=lambda t: -t[1])
    return res


def prune(nets, sparsity):
    """Poda por magnitude (global, entre todas as redes do ensemble)."""
    sparsity = min(max(float(sparsity), 0.0), 0.95)
    if sparsity <= 0:
        return 0.0
    allw = np.concatenate([np.abs(W).ravel() for n in nets for W in n.W])
    thr = np.quantile(allw, sparsity)
    zeros = total = 0
    for n in nets:
        n.mask = [(np.abs(W) > thr).astype(float) for W in n.W]
        for i, m in enumerate(n.mask):
            n.W[i] *= m
            zeros += int((m == 0).sum()); total += m.size
    return zeros / max(1, total)


# ══ 4. Busca de hiperparâmetros ═══════════════════════════════════════════════

SPACE = {
    "hidden": [[8], [16], [32], [16, 8], [32, 16], [64, 32], [64, 32, 16], [128, 64, 32]],
    "activation": ["relu", "leaky_relu", "tanh", "gelu", "swish", "elu"],
    "optimizer": ["adam", "adamw", "rmsprop", "momentum"],
    "lr": [0.003, 0.01, 0.03],
    "l2": [0.0, 1e-4, 1e-3, 1e-2],
    "dropout": [0.0, 0.1, 0.2],
    "batch": [16, 32, 64, 0],
}
GRID = {"hidden": [[16], [32, 16], [64, 32]], "activation": ["relu", "tanh"],
        "lr": [0.003, 0.01, 0.03], "l2": [1e-4, 1e-2]}


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

SIZE_PRESETS = {"small": [16, 8], "medium": [64, 32], "large": [128, 64, 32],
                "deep": [128, 64, 32, 16]}
DEFAULT_OPTS = {
    "task": "auto", "hidden": None, "activation": "relu", "optimizer": "adam",
    "lr": None, "schedule": "cosine", "epochs": 300, "batch": 32, "l2": 1e-4,
    "dropout": 0.0, "noise": 0.0, "patience": 25, "balance": "none",
    "synthetic": 0.0, "ensemble": 1, "search": "none", "trials": 12,
    "budget_s": 25.0, "auto": False, "compress": 0.0, "seed": 42,
}


def parse_hidden(h, in_dim):
    if h is None or h == "":
        return [min(128, max(16, 4 * in_dim)), min(64, max(8, 2 * in_dim))]
    if isinstance(h, str):
        key = h.strip().lower()
        if key in SIZE_PRESETS:
            return list(SIZE_PRESETS[key])
        h = [p for p in key.replace(";", ",").replace("x", ",").split(",") if p.strip()]
    out = [int(float(v)) for v in h]
    if not out or any(v < 1 or v > 1024 for v in out) or len(out) > 8:
        raise ValueError("hidden layers must be 1–8 layers of 1–1024 neurons")
    return out


def _prepare_target(raw_y, task, classes=None):
    if task == "auto":
        task = "regression" if all(_num(v) is not None for v in raw_y) else "classification"
    if task == "regression":
        vals = [_num(v) for v in raw_y]
        if any(v is None for v in vals):
            raise ValueError("regression needs a numeric target")
        return "regression", None, np.array(vals, dtype=float)
    cl = classes or sorted({str(v).strip() for v in raw_y})
    idx = {c: i for i, c in enumerate(cl)}
    try:
        y = np.array([idx[str(v).strip()] for v in raw_y], dtype=int)
    except KeyError as e:
        raise ValueError(f"label {e} was not in the original model's classes")
    return "classification", cl, y


def _onehot(y, k):
    Y = np.zeros((len(y), k))
    Y[np.arange(len(y)), y] = 1.0
    return Y


def clean_rows(header, rows):
    """ETL leve: separa features/alvo, remove duplicatas exatas e alvo ausente."""
    seen, feats, tgt, dup, miss = set(), [], [], 0, 0
    for r in rows:
        if _is_missing(r[-1]):
            miss += 1; continue
        key = tuple(str(c).strip() for c in r)
        if key in seen:
            dup += 1; continue
        seen.add(key)
        feats.append(list(r[:-1])); tgt.append(r[-1])
    names = list(header[:-1]) if header else [f"x{i + 1}" for i in range(len(rows[0]) - 1)]
    return names, feats, tgt, {"duplicates": dup, "missing_target": miss}


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
        return {
            "version": 2, "task": task, "classes": classes, "prep": prep.to_dict(),
            "y_mean": y_mean, "y_std": y_std,
            "arch": {"sizes": nets[0].sizes, "activation": nets[0].activation},
            "members": [{"W": [np.round(W, 5).tolist() for W in n.W],
                         "b": [np.round(b, 5).tolist() for b in n.b]} for n in nets],
            "features": len(names), "feature_names": names,
        }

    def evaluate(nets, idx):
        p = Predictor({**to_model(nets)})
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
        "auto": auto, "search_mode": mode,
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
    m["members"] = [{"W": [np.round(W, 5).tolist() for W in n.W],
                     "b": [np.round(b, 5).tolist() for b in n.b]} for n in nets]
    m.pop("sizes", None); m.pop("W", None); m.pop("b", None)
    m["version"] = 2
    return m


def finetune(model, header, rows, epochs=80, lr=None, freeze=0, seed=1, log=lambda m: None):
    """Continua o treino de um modelo com dados novos (taxa baixa), congelando as
    primeiras `freeze` camadas — o "transfer learning" possível para dados tabulares."""
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
    pred2 = Predictor(new)
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
    sp = Predictor(new)
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
        info["after"] = metrics(pred.task, Predictor(new).outputs_enc(X), y,
                                len(pred.classes or [1]))
    info.update({"sparsity": real, "weights": total})
    return new, info


def synthesize(header, rows, factor=0.5, seed=0):
    """Gera linhas sintéticas (SMOTE) no espaço original: devolve só as novas, como texto."""
    names, feats, raw_y, _ = clean_rows(header, rows)
    prep = Prep().fit(feats, names)
    if any(c["kind"] == "cat" for c in prep.cols):
        raise ValueError("synthetic data currently needs numeric features only")
    task, classes, y = _prepare_target(raw_y, "auto")
    F = np.array([[_num(v) if not _is_missing(v) else c["fill"] for v, c in zip(r, prep.cols)]
                  for r in feats], dtype=float)
    rng = np.random.default_rng(seed)
    xs, ys = synth_rows(F, y, int(round(factor * len(F))), task, rng)
    out = []
    for x, t in zip(xs, ys):
        lab = classes[int(t)] if task == "classification" else f"{t:.4g}"
        out.append([f"{v:.4g}" for v in x] + [lab])
    return out


def drift_report(model, logs):
    """Compara as entradas/confiança recentes com o que o modelo viu no treino."""
    if len(logs) < 5:
        return {"enough": False, "n": len(logs)}
    Xs = np.array([l["x"] for l in logs if "x" in l], dtype=float)
    res = {"enough": True, "n": len(logs), "alerts": []}
    pred = Predictor(model)
    cm = np.array(pred.prep.col_map)
    if Xs.size:
        for j, name in enumerate(pred.prep.names):
            sel = cm == j
            if pred.prep.cols[j]["kind"] == "num":
                z = float(np.abs(Xs[:, sel].mean()))
                if z > 1.5:
                    res["alerts"].append(f"input '{name}' drifted ({z:.1f} std from training mean)")
    confs = [l["conf"] for l in logs if l.get("conf") is not None]
    base = (model.get("baseline") or {}).get("conf_mean")
    if confs and base is not None:
        res["conf_now"], res["conf_base"] = float(np.mean(confs)), base
        if base - np.mean(confs) > 0.15:
            res["alerts"].append(f"confidence fell from {base * 100:.0f}% to {np.mean(confs) * 100:.0f}% "
                                 "— consider retraining")
    return res
