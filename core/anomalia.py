"""Detector de anomalias do PC — NEXUS Ultra 2026 2.3.

Um autoencoder (rede neural que aprende a "reconstruir" o seu PC normal) olha CPU, memória, disco, rede
e processos a cada minuto. Se o PC passa a se comportar de um jeito que a rede nunca viu no seu uso
normal, ela estranha (erro de reconstrução alto) e o NEXUS avisa, dizendo QUAL medida destoou.

Só observa: não fecha programas nem mexe em nada. Os números ficam em memory/metricas.csv (só medidas,
nenhum nome de programa além do mais pesado do momento) e o modelo em memory/anomalia.json.
Treina sozinho com o seu uso normal — precisa de ~5 horas de medidas (300 amostras).
"""
from __future__ import annotations

import csv
import json
import time
from pathlib import Path

import numpy as np
from core.protecao import engolida as _engolida

PASTA = Path(__file__).resolve().parent.parent / "memory"
ARQ_CSV = PASTA / "metricas.csv"
ARQ_MODELO = PASTA / "anomalia.json"
MAX_LINHAS = 20000
MIN_AMOSTRAS = 300

FEATS = ["cpu", "memoria", "swap", "disco_uso", "disco_leitura_mb_s", "disco_escrita_mb_s",
         "rede_baixa_kb_s", "rede_sobe_kb_s", "processos", "cpu_do_maior"]
NOMES = {"cpu": "uso de CPU", "memoria": "uso de memória", "swap": "uso de memória virtual",
         "disco_uso": "espaço usado no disco", "disco_leitura_mb_s": "leitura de disco",
         "disco_escrita_mb_s": "escrita em disco", "rede_baixa_kb_s": "download na rede",
         "rede_sobe_kb_s": "upload na rede", "processos": "quantidade de processos",
         "cpu_do_maior": "CPU do programa mais pesado"}
_LOG_FEATS = {"disco_leitura_mb_s", "disco_escrita_mb_s", "rede_baixa_kb_s", "rede_sobe_kb_s"}

_ultimo: dict = {}
_cache: dict = {}


def amostrar() -> dict | None:
    """Uma medida do PC agora (taxas calculadas contra a medida anterior). None na 1ª chamada."""
    try:
        import psutil
    except ImportError:
        return None
    agora = time.monotonic()
    try:
        io = psutil.disk_io_counters()
        net = psutil.net_io_counters()
        try:
            disco = psutil.disk_usage("/").percent
        except Exception:
            disco = 0.0
        procs = list(psutil.process_iter(["cpu_percent", "name"]))
        maior = max((p.info.get("cpu_percent") or 0.0 for p in procs), default=0.0)
        atual = {"t": agora, "lido": getattr(io, "read_bytes", 0), "escrito": getattr(io, "write_bytes", 0),
                 "baixou": net.bytes_recv, "subiu": net.bytes_sent}
        ant = _ultimo.copy()
        _ultimo.clear(); _ultimo.update(atual)
        if not ant:
            return None
        dt = max(agora - ant["t"], 1e-3)
        return {
            "cpu": psutil.cpu_percent(interval=None), "memoria": psutil.virtual_memory().percent,
            "swap": psutil.swap_memory().percent, "disco_uso": disco,
            "disco_leitura_mb_s": max(0, atual["lido"] - ant["lido"]) / dt / 1e6,
            "disco_escrita_mb_s": max(0, atual["escrito"] - ant["escrito"]) / dt / 1e6,
            "rede_baixa_kb_s": max(0, atual["baixou"] - ant["baixou"]) / dt / 1e3,
            "rede_sobe_kb_s": max(0, atual["subiu"] - ant["subiu"]) / dt / 1e3,
            "processos": float(len(procs)), "cpu_do_maior": float(maior)}
    except Exception:
        return None


def registrar(m: dict) -> None:
    try:
        PASTA.mkdir(parents=True, exist_ok=True)
        novo = not ARQ_CSV.exists()
        with ARQ_CSV.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if novo:
                w.writerow(["t"] + FEATS)
            w.writerow([int(time.time())] + [round(float(m[k]), 3) for k in FEATS])
        if ARQ_CSV.stat().st_size > MAX_LINHAS * 90:               # aparar: guarda a metade mais recente
            linhas = ARQ_CSV.read_text(encoding="utf-8").splitlines()
            ARQ_CSV.write_text("\n".join([linhas[0]] + linhas[-MAX_LINHAS // 2:]) + "\n", encoding="utf-8")
    except Exception:
        _engolida("core/anomalia.py:87")


def ler() -> np.ndarray:
    try:
        with ARQ_CSV.open(encoding="utf-8") as f:
            r = csv.reader(f); next(r, None)
            linhas = [[float(x) for x in row[1:1 + len(FEATS)]] for row in r if len(row) > len(FEATS)]
        return np.array(linhas, np.float32).reshape(-1, len(FEATS))
    except Exception:
        return np.zeros((0, len(FEATS)), np.float32)


def _transformar(X: np.ndarray) -> np.ndarray:
    X = np.array(X, np.float32, copy=True)
    for i, k in enumerate(FEATS):
        if k in _LOG_FEATS:
            X[..., i] = np.log1p(X[..., i])
    return X


def treinar(log=print) -> dict:
    from core.neural_backend import engine as NE
    bruto = ler()
    if len(bruto) < MIN_AMOSTRAS:
        raise ValueError(f"Tenho {len(bruto)} medidas; preciso de {MIN_AMOSTRAS} (cerca de "
                         f"{MIN_AMOSTRAS // 60} horas com o NEXUS aberto).")
    X = _transformar(bruto)
    rng = np.random.default_rng(2)
    idx = rng.permutation(len(X))
    n_val = max(30, len(X) // 5)
    va, tr = X[idx[:n_val]], X[idx[n_val:]]
    med = np.median(tr, 0)
    esc = np.maximum(np.percentile(tr, 90, 0) - np.percentile(tr, 10, 0), 1e-2 * np.maximum(np.abs(med), 1.0))
    z = lambda A: np.clip((A - med) / esc, -8, 8).astype(np.float32)
    n = X.shape[1]
    rede = NE.MLP([n, 8, 3, 8, n], "tanh", seed=6)
    NE.fit(rede, z(tr), z(tr), "regression", epochs=300, lr=0.01, optimizer="adam", batch=32,
           l2=1e-4, Xv=z(va), Yv=z(va), patience=30, seed=6, noise=0.05)
    err_va = ((rede.predict(z(va)) - z(va)) ** 2).mean(1)
    limiar = float(np.percentile(err_va, 99.5) * 1.25 + 1e-4)       # folga: só o realmente estranho passa
    rel = {"amostras": len(X), "limiar": limiar, "erro_tipico": float(np.median(err_va)),
           "treinado_em": time.strftime("%d/%m/%Y %H:%M")}
    ARQ_MODELO.write_text(json.dumps({
        "rel": rel, "med": med.tolist(), "esc": esc.tolist(),
        "W": [w.tolist() for w in rede.W], "b": [b.tolist() for b in rede.b]}), encoding="utf-8")
    _cache.clear()
    log(f"[Anomalia] treinado com {len(X)} medidas; limiar {limiar:.4f}")
    return rel


def _modelo():
    if "m" in _cache:
        return _cache["m"]
    from core.neural_backend import engine as NE
    try:
        d = json.loads(ARQ_MODELO.read_text(encoding="utf-8"))
        W = [np.array(w, np.float32) for w in d["W"]]
        b = [np.array(x, np.float32) for x in d["b"]]
        rede = NE.MLP.from_arrays([W[0].shape[0]] + [w.shape[1] for w in W], "tanh", W, b)
        m = (rede, np.array(d["med"], np.float32), np.array(d["esc"], np.float32), d["rel"])
    except Exception:
        m = None
    _cache["m"] = m
    return m


def treinado() -> bool:
    return _modelo() is not None


def relatorio() -> dict:
    m = _modelo()
    return dict(m[3]) if m else {}


def avaliar(medida: dict) -> dict | None:
    """{'pontuacao': erro/limiar (≥1 = estranho), 'culpados': [(medida, texto)]} ou None sem modelo."""
    m = _modelo()
    if m is None:
        return None
    rede, med, esc, rel = m
    x = _transformar(np.array([[medida[k] for k in FEATS]], np.float32))
    z = np.clip((x - med) / esc, -8, 8).astype(np.float32)
    rec = rede.predict(z)
    por_feat = ((rec - z) ** 2)[0]
    pont = float(por_feat.mean() / rel["limiar"])
    culpados = []
    for i in np.argsort(-por_feat)[:2]:
        k = FEATS[i]
        sentido = "acima" if z[0, i] > rec[0, i] else "abaixo"
        culpados.append((k, f"{NOMES[k]} {sentido} do seu normal ({medida[k]:.0f})"))
    return {"pontuacao": pont, "culpados": culpados}


class Vigia:
    """Decide quando avisar: precisa estar estranho 3 medidas seguidas, e no máximo 1 aviso por 30 min."""

    def __init__(self, seguidas: int = 3, pausa_s: float = 1800.0):
        self.seguidas, self.pausa_s = seguidas, pausa_s
        self._n, self._ultimo_aviso = 0, -1e9

    def passo(self, medida: dict, agora: float | None = None) -> str | None:
        r = avaliar(medida)
        agora = time.monotonic() if agora is None else agora
        if r is None or r["pontuacao"] < 1.0:
            self._n = 0
            return None
        self._n += 1
        if self._n < self.seguidas or agora - self._ultimo_aviso < self.pausa_s:
            return None
        self._ultimo_aviso, self._n = agora, 0
        return "O PC está se comportando diferente do seu normal: " + "; ".join(t for _, t in r["culpados"]) + "."


def passo_coleta() -> dict | None:
    m = amostrar()
    if m:
        registrar(m)
    return m
