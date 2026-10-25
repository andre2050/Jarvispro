"""Previsão de hábitos — NEXUS Ultra 2026 2.3.

Uma rede neural pequena (motor de core/neural_backend.py: Keras se houver TensorFlow, senão NumPy) aprende, com o histórico de memory/habits.json,
"o que você costuma pedir a esta hora, neste dia da semana, depois de pedir tal coisa" e estima o que
vem a seguir. Só OBSERVA e sugere — executar algo continua dependendo do seu "sim".

Honestidade: com poucos dias de uso a rede não supera uma contagem simples por hora. O treino mede isso
(em dias que ela nunca viu) e, se não for melhor que a contagem, avisa e não sugere nada.
"""
from __future__ import annotations

import json
import math
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

PASTA = Path(__file__).resolve().parent.parent / "memory"
ARQ = PASTA / "previsao_habitos.json"
MIN_EVENTOS = 40
MAX_CLASSES = 12
JANELA_S = 300
LIMIAR_SUGERIR = 0.35


def _eventos() -> list[dict]:
    from core import habits
    ev = [e for e in habits._load() if isinstance(e, dict) and e.get("sig") and e.get("t")]
    return sorted(ev, key=lambda e: e["t"])


def _tempo(ts: float) -> list[float]:
    d = datetime.fromtimestamp(ts)
    h = d.hour + d.minute / 60
    return [math.sin(2 * math.pi * h / 24), math.cos(2 * math.pi * h / 24),
            math.sin(2 * math.pi * d.weekday() / 7), math.cos(2 * math.pi * d.weekday() / 7),
            1.0 if d.weekday() >= 5 else 0.0]


def _vetor(ts: float, anterior: str | None, classes: list[str]) -> np.ndarray:
    prev = np.zeros(len(classes) + 1, np.float32)
    prev[classes.index(anterior) if anterior in classes else len(classes)] = 1.0
    return np.concatenate([np.array(_tempo(ts), np.float32), prev])


def _montar(ev: list[dict], classes: list[str]):
    X, y, hrs = [], [], []
    for i, e in enumerate(ev):
        ant = ev[i - 1]["sig"] if i and e["t"] - ev[i - 1]["t"] <= JANELA_S else None
        X.append(_vetor(e["t"], ant, classes))
        y.append(classes.index(e["sig"]) if e["sig"] in classes else len(classes))
        hrs.append(datetime.fromtimestamp(e["t"]).hour)
    return np.array(X, np.float32), np.array(y), np.array(hrs)


def treinar(log=print) -> dict:
    from core.neural_backend import engine as NE
    ev = _eventos()
    if len(ev) < MIN_EVENTOS:
        raise ValueError(f"Tenho só {len(ev)} registros de uso; preciso de pelo menos {MIN_EVENTOS} "
                         "(alguns dias usando o NEXUS normalmente).")
    cont = Counter(e["sig"] for e in ev)
    classes = [s for s, _ in cont.most_common(MAX_CLASSES)]
    n_cl = len(classes) + 1                                    # +1 = "outra coisa"
    corte = int(len(ev) * 0.8)                                 # validação = o final do histórico
    X, y, hrs = _montar(ev, classes)
    Xtr, ytr, Xva, yva, hva = X[:corte], y[:corte], X[corte:], y[corte:], hrs[corte:]
    Y = np.eye(n_cl, dtype=np.float32)
    rede = NE.MLP([X.shape[1], 32, n_cl], "relu", seed=4, dropout=0.1)
    NE.fit(rede, Xtr, Y[ytr], "classification", epochs=300, lr=0.01, optimizer="adam", batch=32,
           l2=1e-3, Xv=Xva, Yv=Y[yva], patience=30, seed=4, noise=0.02)
    p = NE.softmax(rede.predict(Xva))
    top1 = float((p.argmax(1) == yva).mean())
    top3 = float(np.mean([yva[i] in np.argsort(-p[i])[:3] for i in range(len(yva))]))
    # contagem simples por hora (o que um não-ML faria) — a rede precisa ganhar disso
    por_hora: dict[int, Counter] = {}
    for h, c in zip(hrs[:corte], ytr):
        por_hora.setdefault(int(h), Counter())[int(c)] += 1
    geral = Counter(ytr.tolist())
    base = np.mean([ (por_hora.get(int(h)) or geral).most_common(1)[0][0] == c for h, c in zip(hva, yva)])
    rel = {"eventos": len(ev), "classes": classes, "top1": round(top1, 3), "top3": round(top3, 3),
           "base_contagem_top1": round(float(base), 3), "melhor_que_contagem": bool(top1 > base + 0.02),
           "treinado_em": time.strftime("%d/%m/%Y %H:%M")}
    PASTA.mkdir(parents=True, exist_ok=True)
    ARQ.write_text(json.dumps({
        "rel": rel, "W": [w.tolist() for w in rede.W], "b": [b.tolist() for b in rede.b]}), encoding="utf-8")
    log(f"[Previsão] top1 {top1:.0%} (contagem {base:.0%}), top3 {top3:.0%}")
    return rel


def _carregar():
    from core.neural_backend import engine as NE
    try:
        d = json.loads(ARQ.read_text(encoding="utf-8"))
        W = [np.array(w, np.float32) for w in d["W"]]
        b = [np.array(x, np.float32) for x in d["b"]]
        rede = NE.MLP.from_arrays([W[0].shape[0]] + [w.shape[1] for w in W], "relu", W, b)
        return rede, d["rel"]
    except Exception:
        return None


def relatorio() -> dict:
    m = _carregar()
    return m[1] if m else {}


def prever(quando: float | None = None, anterior: str | None = None, topo: int = 3) -> list[tuple[str, float]]:
    """[(hábito, chance)] mais prováveis; [] se não há modelo ou ele não é melhor que a contagem."""
    from core.neural_backend import engine as NE
    m = _carregar()
    if not m or not m[1].get("melhor_que_contagem"):
        return []
    rede, rel = m
    classes = rel["classes"]
    p = NE.softmax(rede.predict(_vetor(quando or time.time(), anterior, classes)[None, :]))[0]
    ordem = [i for i in np.argsort(-p) if i < len(classes)][:topo]
    return [(classes[i], float(p[i])) for i in ordem]


def dia_previsto(dia_semana: int | None = None) -> list[tuple[int, str, float]]:
    """Para cada hora do dia, o hábito mais provável com chance ≥ limiar: [(hora, hábito, chance)]."""
    base = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if dia_semana is not None:
        base += timedelta(days=(int(dia_semana) - base.weekday()) % 7)
    out = []
    for h in range(24):
        t = base.replace(hour=h, minute=30, second=0, microsecond=0).timestamp()
        pr = prever(t, None, 1)
        if pr and pr[0][1] >= LIMIAR_SUGERIR:
            out.append((h, pr[0][0], pr[0][1]))
    return out


def sugestao_agora(anterior: str | None = None) -> tuple[str, float] | None:
    pr = prever(None, anterior, 1)
    return pr[0] if pr and pr[0][1] >= LIMIAR_SUGERIR else None
