"""
core/voz_id.py — o NEXUS reconhece a SUA voz (NEXUS Ultra 2026 2.3).

PARA QUE SERVE
    Uma camada extra para ações sensíveis (mandar mensagem/e-mail, destrancar a casa, apagar
    arquivos, limpar o PC, desligar). Se estiver ligada, essas ações só rodam quando a voz que
    acabou de falar parece ser a do dono. Vale POR CIMA da confirmação na tela, nunca no lugar dela.

COMO FUNCIONA (e o limite honesto)
    1. Você grava ~8 frases (``voz_treino``). O áudio NÃO é guardado: só os números.
    2. De cada frase saem 79 características: MFCC (formato do trato vocal), espectro médio e
       tom da voz (f0).
    3. Como não há outras pessoas para comparar, o NEXUS cria "vozes de outras pessoas" a partir
       da sua: acelera e desacelera o áudio (muda tom e formantes juntos, como outro trato vocal),
       muda o brilho e mistura ruído. Uma pequena rede neural aprende a separar a sua voz delas.
    4. Ao verificar, a rede dá uma probabilidade de ser você.

    É bem mais fraco que um sistema profissional (ECAPA, x-vector): uma pessoa com voz muito
    parecida (mesmo sexo, mesma idade, mesmo tom) pode passar, e gripe/ruído forte podem
    derrubar você. Por isso fica DESLIGADO por padrão, o rigor é ajustável e nada sensível
    depende só dele.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import numpy as np

from core import audio_feat as A
from core.protecao import engolida as _engolida

_BASE = Path(__file__).resolve().parent.parent
ARQ_MODELO = _BASE / "memory" / "voz_dono.npz"
ARQ_CONFIG = _BASE / "memory" / "voz_dono.json"

MIN_VOZ_S = 0.8                 # fala mínima (sem silêncio) para dar uma característica confiável
MIN_AMOSTRAS = 5
RIGOR = {"baixo": 0.60, "normal": 0.80, "alto": 0.93}
_TRAVA = threading.RLock()

# ações que, com a trava ligada, exigem a voz do dono
def exige_dono(nome: str, args: dict) -> bool:
    a = {k: str(v).lower() for k, v in (args or {}).items()}
    acao = a.get("action", "")
    if nome in ("send_message",):
        return True
    if nome == "email_reader":
        return acao in ("send", "reply", "enviar", "responder")
    if nome == "casa_inteligente":
        return acao in ("unlock", "open", "run_script", "destrancar", "abrir", "script")
    if nome == "file_controller":
        return acao in ("delete", "remove", "apagar")
    if nome == "computer_settings":
        return acao in ("shutdown", "restart", "sleep", "hibernate", "desligar", "reiniciar")
    if nome == "manutencao_pc":
        return acao in ("temp_clean", "limpar")
    return False


# ── características ──────────────────────────────────────────────────────────
def caracteristicas(x) -> np.ndarray | None:
    """Vetor de 79 números da voz; None se houver pouca fala."""
    x = A.para_float(x)
    if len(x) < int(0.5 * A.TAXA):
        return None
    pico = float(np.max(np.abs(x))) or 1.0
    x = x / pico * 0.5                                     # nível comparável entre gravações
    mask = A.quadros_de_voz(x)
    if mask.sum() * A.SALTO / A.TAXA < MIN_VOZ_S:
        return None
    lm = A.log_mel(x)
    n = min(len(lm), len(mask))
    lm, mask = lm[:n], mask[:n]
    mf = A.mfcc(x, 20, lm=lm)[:n][mask][:, 1:]
    espectro = lm[mask].mean(0)
    f0 = A.f0_por_quadro(x)
    if f0.size >= 5:
        tom = [float(np.log(np.median(f0))), float(np.log(f0).std()), float(len(f0) / max(mask.sum() / 2, 1))]
    else:
        tom = [np.log(150.0), 0.0, 0.0]
    return np.concatenate([mf.mean(0), mf.std(0), espectro, tom]).astype(np.float32)


# ── outras "vozes" sintéticas a partir da sua ───────────────────────────────
def _outras_vozes(x: np.ndarray, rng: np.random.Generator, n: int) -> list[np.ndarray]:
    saida = []
    for _ in range(n):
        fator = float(rng.uniform(0.74, 0.93) if rng.random() < 0.5 else rng.uniform(1.07, 1.35))
        y = A.reamostrar(x, fator)
        if rng.random() < 0.5:                             # brilho diferente
            alfa = float(rng.uniform(-0.35, 0.55))
            y = np.append(y[:1], y[1:] - alfa * y[:-1]).astype(np.float32)
        if rng.random() < 0.5:                             # fala mais "rouca"/"limpa"
            y = (y + rng.normal(0, rng.uniform(0.003, 0.02), y.shape)).astype(np.float32)
        saida.append(y)
    return saida


def _versoes_do_dono(x: np.ndarray, rng: np.random.Generator, n: int) -> list[np.ndarray]:
    saida = [x]
    for _ in range(n):
        y = A.reamostrar(x, float(rng.uniform(0.97, 1.03))) * float(rng.uniform(0.5, 1.5))
        if rng.random() < 0.7:
            y = y + rng.normal(0, rng.uniform(0.0, 0.01), y.shape)
        saida.append(y.astype(np.float32))
    return saida


def treinar(amostras: list, semente: int = 7, log=print) -> dict:
    """Aprende a sua voz com as gravações (lista de áudios int16/float). Devolve o relatório."""
    from core.neural_backend import engine as NE
    rng = np.random.default_rng(semente)
    audios = [A.para_float(a) for a in amostras]
    audios = [a for a in audios if caracteristicas(a) is not None]
    if len(audios) < MIN_AMOSTRAS:
        raise ValueError(f"Preciso de pelo menos {MIN_AMOSTRAS} frases boas (fala clara, ~1 s ou mais); "
                         f"só {len(audios)} serviram.")
    idx = rng.permutation(len(audios))
    n_val = max(1, len(audios) // 4)
    val_ids, tr_ids = set(idx[:n_val].tolist()), set(idx[n_val:].tolist())

    def montar(ids):
        X, y = [], []
        for i in ids:
            for v in _versoes_do_dono(audios[i], rng, 6):
                f = caracteristicas(v)
                if f is not None:
                    f = f.copy(); f[-3] += rng.normal(0, 0.025)      # o tom do dono varia um pouco
                    X.append(f); y.append(1)
            f0 = caracteristicas(audios[i])
            for v in _outras_vozes(audios[i], rng, 10):              # trato vocal e tom diferentes
                f = caracteristicas(v)
                if f is not None:
                    X.append(f); y.append(0)
            for _ in range(8):                                       # só o tom diferente
                f = f0.copy()
                f[-3] += float(rng.choice([-1, 1]) * rng.uniform(0.09, 0.45))
                X.append(f); y.append(0)
            for _ in range(8):                                       # só o trato vocal diferente (mesmo tom)
                fator = float(rng.uniform(1.05, 1.15) if rng.random() < 0.5 else rng.uniform(0.87, 0.95))
                f = caracteristicas(A.reamostrar(audios[i], fator))
                if f is not None:
                    f = f.copy(); f[-3:] = f0[-3:]; f[-3] += rng.normal(0, 0.025)
                    X.append(f); y.append(0)
        return np.array(X, np.float32), np.array(y)

    Xtr, ytr = montar(tr_ids)
    Xva, yva = montar(val_ids)
    media, desvio = Xtr.mean(0), Xtr.std(0) + 1e-3
    z = lambda X: (X - media) / desvio
    Y = lambda y: np.eye(2)[y]
    w = np.where(ytr == 1, 0.5 / max((ytr == 1).mean(), 1e-6), 0.5 / max((ytr == 0).mean(), 1e-6))
    rede = NE.MLP([Xtr.shape[1], 24, 2], "relu", seed=semente, dropout=0.1)
    NE.fit(rede, z(Xtr), Y(ytr), "classification", epochs=250, lr=0.01, optimizer="adam", batch=64,
           l2=1e-3, w=w, Xv=z(Xva), Yv=Y(yva), patience=30, seed=semente, noise=0.05)
    p = NE.softmax(rede.predict(z(Xva)))[:, 1]
    rel = {
        "amostras": len(audios),
        "dono_aceito": float((p[yva == 1] >= RIGOR["normal"]).mean()),
        "outras_recusadas": float((p[yva == 0] < RIGOR["normal"]).mean()),
        "treinado_em": time.strftime("%d/%m/%Y %H:%M"),
    }
    with _TRAVA:
        ARQ_MODELO.parent.mkdir(parents=True, exist_ok=True)
        tmp = ARQ_MODELO.with_suffix(".tmp.npz")
        np.savez(tmp, media=media, desvio=desvio, n_camadas=len(rede.W),
                 **{f"W{i}": w_ for i, w_ in enumerate(rede.W)}, **{f"b{i}": b for i, b in enumerate(rede.b)},
                 relatorio=json.dumps(rel))
        tmp.replace(ARQ_MODELO)
        _cache.clear()
    log(f"[VozID] treinada: dono aceito {rel['dono_aceito']:.0%}, outras recusadas {rel['outras_recusadas']:.0%}")
    return rel


_cache: dict = {}


def _carregar():
    with _TRAVA:
        if "m" in _cache:
            return _cache["m"]
        try:
            from core.neural_backend import engine as NE
            with np.load(ARQ_MODELO, allow_pickle=False) as z:
                n = int(z["n_camadas"])
                W = [z[f"W{i}"] for i in range(n)]
                b = [z[f"b{i}"] for i in range(n)]
                m = (NE.MLP.from_arrays([W[0].shape[0]] + [w_.shape[1] for w_ in W], "relu", W, b),
                     z["media"], z["desvio"], json.loads(str(z["relatorio"])))
        except Exception:
            m = None
        _cache["m"] = m
        return m


def cadastrada() -> bool:
    return _carregar() is not None


def relatorio() -> dict:
    m = _carregar()
    return dict(m[3]) if m else {}


def probabilidade(x) -> float | None:
    """Chance (0–1) de a voz ser a do dono; None se não há cadastro ou fala suficiente."""
    m = _carregar()
    if m is None:
        return None
    f = caracteristicas(x)
    if f is None:
        return None
    from core.neural_backend import engine as NE
    rede, media, desvio, _ = m
    return float(NE.softmax(rede.predict(((f - media) / desvio)[None, :]))[0, 1])


# ── configuração (trava ligada/desligada e rigor) ────────────────────────────
def config() -> dict:
    d = {"trava": False, "rigor": "normal"}
    try:
        d.update({k: v for k, v in json.loads(ARQ_CONFIG.read_text(encoding="utf-8")).items() if k in d})
    except Exception:
        _engolida("core/voz_id.py:226")
    if d["rigor"] not in RIGOR:
        d["rigor"] = "normal"
    return d


def definir_config(**kw) -> dict:
    d = config()
    d.update({k: v for k, v in kw.items() if k in d})
    ARQ_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    ARQ_CONFIG.write_text(json.dumps(d), encoding="utf-8")
    return d


def remover() -> bool:
    with _TRAVA:
        _cache.clear()
        existia = ARQ_MODELO.exists()
        for p in (ARQ_MODELO, ARQ_CONFIG):
            try:
                p.unlink()
            except FileNotFoundError:
                pass
        return existia


# ── áudio recente do microfone ───────────────────────────────────────────────
class Anel:
    """Os últimos segundos do microfone (int16 mono 16 kHz), para conferir quem falou."""

    def __init__(self, segundos: float = 10.0):
        self.cap = int(segundos * A.TAXA)
        self._buf = np.zeros(0, np.int16)
        self._trava = threading.Lock()

    def adicionar(self, bloco) -> None:
        x = np.asarray(bloco)
        x = (x[:, 0] if x.ndim > 1 else x).astype(np.int16, copy=False)
        with self._trava:
            self._buf = np.concatenate([self._buf, x])[-self.cap:]

    def ultima_fala(self, segundos: float = 6.0) -> np.ndarray:
        with self._trava:
            x = self._buf[-int(segundos * A.TAXA):].copy()
        return A.aparar(A.para_float(x))

    def limpar(self) -> None:
        with self._trava:
            self._buf = np.zeros(0, np.int16)


anel = Anel()


def verificar_dono(nome: str, args: dict) -> str | None:
    """None = pode seguir. Texto = motivo da recusa (para devolver ao modelo)."""
    cfg = config()
    if not cfg["trava"] or not exige_dono(nome, args) or not cadastrada():
        return None
    p = probabilidade(anel.ultima_fala())
    if p is None:
        return ("[failed] TRAVA DE VOZ: não ouvi fala suficiente para conferir que é o dono. "
                "Peça para o dono repetir o pedido em voz clara.")
    if p < RIGOR[cfg["rigor"]]:
        return (f"[failed] TRAVA DE VOZ: a voz não parece ser a do dono ({p:.0%} de chance; "
                f"precisa de {RIGOR[cfg['rigor']]:.0%}). Nada foi executado. Avise o usuário.")
    return None


# ── captura guiada (cadastro) ────────────────────────────────────────────────
class Captura:
    """Enquanto ativa, o microfone alimenta esta captura em vez de ir para o Gemini."""

    def __init__(self):
        self.ativa = False
        self.seg = A.SegmentadorFala(min_s=1.0, max_s=8.0, silencio_s=0.6)
        self.trechos: list[np.ndarray] = []
        self._ev = threading.Event()

    def iniciar(self, min_s=1.0, max_s=8.0, silencio_s=0.6) -> None:
        self.seg = A.SegmentadorFala(min_s=min_s, max_s=max_s, silencio_s=silencio_s)
        self.trechos = []
        self._ev.clear()
        self.ativa = True

    def parar(self) -> None:
        self.ativa = False

    def alimentar(self, bloco) -> None:
        if not self.ativa:
            return
        for t in self.seg.alimentar(bloco):
            self.trechos.append(t)
            self._ev.set()

    def esperar_trecho(self, timeout: float) -> np.ndarray | None:
        """Bloqueia até chegar um trecho novo de fala (ou o tempo acabar)."""
        self._ev.clear()
        n = len(self.trechos)
        if self._ev.wait(timeout) or len(self.trechos) > n:
            return self.trechos[-1] if self.trechos else None
        return None


captura = Captura()
