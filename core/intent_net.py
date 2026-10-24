"""
core/intent_net.py — rede neural local que entende comandos sem internet.

O QUE FAZ
    Recebe uma frase digitada ("abre o spotify", "volume no 40", "timer de 5
    minutos") e diz qual é a INTENÇÃO e com que confiança. Se a confiança for
    alta e o comando for simples, o Nexus executa na hora, sem esperar o
    Gemini — e funciona mesmo sem internet. Tudo que ela não reconhece, ou não
    tem certeza, continua indo para o Gemini como sempre.

A REDE (Keras/TensorFlow se estiver instalado — core/keras_intent.py; senão NumPy puro, aqui)
    Os dois motores têm a mesma arquitetura e gravam o mesmo memory/intent_net.npz,
    então dá para trocar de um para o outro sem retreinar.
    Entrada   texto → 4096 features: n-gramas de letras (2–4) dentro de cada
              palavra + palavras + pares de palavras, por "hashing". Por isso
              ela entende erro de digitação e frase sem acento.
    Camadas   4096 → 192 → 96 → K intenções, ativação GELU, LayerNorm.
    Treino    Adam com weight decay (AdamW), dropout 25 %, label smoothing,
              mini-lotes, parada antecipada pela validação.
    Confiança temperatura calibrada na validação (temperature scaling), então
              "92 %" quer dizer de fato ~92 % de acerto.
    Classe    "none" treinada com centenas de frases que NÃO são comando
              (perguntas, conversa, tarefas complexas, quase-comandos como
              "abre o arquivo e resume"), para ela saber dizer "não é comigo".

APRENDE COM VOCÊ
    Quando você digita algo e o Gemini resolve com uma ferramenta que a rede
    conhece, a frase vira exemplo (memory/intent_examples.json). A cada 8
    exemplos novos ela se retreina sozinha em segundo plano, dando peso 3 ao
    que veio de você.

Os slots (qual app, quantos minutos, qual volume) são lidos por regras depois
da classificação: a rede decide O QUE é, as regras pegam OS DETALHES.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import threading
import time
import unicodedata
from pathlib import Path

import numpy as np

_BASE = Path(__file__).resolve().parent.parent
MODEL_FILE    = _BASE / "memory" / "intent_net.npz"
EXAMPLES_FILE = _BASE / "memory" / "intent_examples.json"
SETTINGS_FILE = _BASE / "memory" / "intent_net_settings.json"

DIM = 4096
DATA_VERSION = 7          # mude ao editar os modelos de frase: força retreino (1.4.3)
RETRAIN_EVERY = 8         # exemplos novos do usuário até retreinar

INTENTS = [
    "none", "time_now", "date_today", "open_app",
    "volume_up", "volume_down", "volume_mute", "volume_set",
    "media_play_pause", "media_next", "media_previous",
    "timer_start", "timer_status", "timer_cancel",
    "note_add", "note_list", "email_check", "system_status",
]

DESCRICAO = {
    "time_now": "dizer as horas", "date_today": "dizer a data",
    "open_app": "abrir aplicativo", "volume_up": "aumentar volume",
    "volume_down": "diminuir volume", "volume_mute": "silenciar",
    "volume_set": "ajustar volume", "media_play_pause": "tocar/pausar",
    "media_next": "próxima música", "media_previous": "música anterior",
    "timer_start": "iniciar timer", "timer_status": "tempo do timer",
    "timer_cancel": "cancelar timer", "note_add": "anotar",
    "note_list": "ler notas", "email_check": "verificar email",
    "system_status": "status do sistema", "none": "enviar ao Gemini",
}


# ══════════════════════════════════════════════════════════════════════════════
# Texto → features
# ══════════════════════════════════════════════════════════════════════════════

_WAKE = re.compile(r"^(?:(?:ei|hey|oi|ok|ola|hi|hello)\s+)?(?:nexus|jarvis|j\.a\.r\.v\.i\.s)\b[\s,]*")


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKD", str(text or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^a-z0-9%:\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = _WAKE.sub("", t).strip()
    return t


def _h(s: str) -> int:
    return int.from_bytes(hashlib.blake2b(s.encode(), digest_size=4).digest(), "little")


_feat_cache: dict[str, tuple] = {}


def features(text: str) -> tuple[np.ndarray, np.ndarray]:
    """Índices e pesos esparsos (já normalizados L2) de uma frase."""
    t = normalize(text)
    hit = _feat_cache.get(t)
    if hit is not None:
        return hit
    counts: dict[int, float] = {}

    def add(key: str, w: float) -> None:
        h = _h(key)
        i = h % DIM
        sign = 1.0 if (h >> 31) & 1 else -1.0      # sinal reduz colisões
        counts[i] = counts.get(i, 0.0) + sign * w

    words = t.split()
    for w in words:
        add("w:" + w, 1.0)
        pw = f"<{w}>"
        for n in (2, 3, 4):
            for k in range(len(pw) - n + 1):
                add(f"c{n}:" + pw[k:k + n], 0.35)
    for a, b in zip(words, words[1:]):
        add(f"b:{a}_{b}", 0.8)
    if any(ch.isdigit() for ch in t):
        add("has:digit", 1.0)
    add("len:" + str(min(len(words), 12)), 0.4)

    if not counts:
        res = (np.zeros(0, np.int64), np.zeros(0, np.float32))
    else:
        idx = np.fromiter(counts.keys(), np.int64)
        val = np.fromiter(counts.values(), np.float32)
        val = np.sign(val) * np.log1p(np.abs(val))
        n = float(np.linalg.norm(val)) or 1.0
        res = (idx, val / n)
    if len(_feat_cache) > 4000:
        _feat_cache.clear()
    _feat_cache[t] = res
    return res


def featurize(texts: list[str]) -> np.ndarray:
    X = np.zeros((len(texts), DIM), np.float32)
    for r, t in enumerate(texts):
        idx, val = features(t)
        np.add.at(X[r], idx, val)
    return X


# ══════════════════════════════════════════════════════════════════════════════
# A rede
# ══════════════════════════════════════════════════════════════════════════════

def _gelu(x):
    return 0.5 * x * (1.0 + np.tanh(0.7978845608 * (x + 0.044715 * x ** 3)))


def _gelu_grad(x):
    t = np.tanh(0.7978845608 * (x + 0.044715 * x ** 3))
    dt = (1 - t * t) * 0.7978845608 * (1 + 3 * 0.044715 * x * x)
    return 0.5 * (1 + t) + 0.5 * x * dt


class IntentMLP:
    """4096 → 192 → 96 → K, GELU + LayerNorm, treinada com AdamW."""

    def __init__(self, sizes=(DIM, 192, 96, len(INTENTS)), seed=7):
        rng = np.random.default_rng(seed)
        self.sizes = tuple(sizes)
        self.p: dict[str, np.ndarray] = {}
        for i in range(len(sizes) - 1):
            fan = sizes[i]
            self.p[f"W{i}"] = (rng.standard_normal((sizes[i], sizes[i + 1]))
                               * np.sqrt(2.0 / fan)).astype(np.float32)
            self.p[f"b{i}"] = np.zeros(sizes[i + 1], np.float32)
            if i < len(sizes) - 2:
                self.p[f"g{i}"] = np.ones(sizes[i + 1], np.float32)
                self.p[f"s{i}"] = np.zeros(sizes[i + 1], np.float32)
        self.T = 1.0                     # temperatura calibrada

    # forward com cache para o backward
    def _forward(self, X, train=False, drop=0.25, rng=None):
        cache = []
        a = X
        L = len(self.sizes) - 1
        for i in range(L):
            z = a @ self.p[f"W{i}"] + self.p[f"b{i}"]
            if i == L - 1:
                cache.append(("out", a))
                return z, cache
            mu = z.mean(1, keepdims=True)
            var = z.var(1, keepdims=True)
            inv = 1.0 / np.sqrt(var + 1e-5)
            zh = (z - mu) * inv
            y = zh * self.p[f"g{i}"] + self.p[f"s{i}"]
            h = _gelu(y)
            mask = None
            if train and drop > 0:
                mask = (rng.random(h.shape) >= drop).astype(np.float32) / (1 - drop)
                h = h * mask
            cache.append(("hid", a, zh, inv, y, mask))
            a = h
        return a, cache

    def logits(self, X):
        z, _ = self._forward(X)
        return z

    def proba(self, X):
        z = self.logits(X) / self.T
        z = z - z.max(1, keepdims=True)
        e = np.exp(z)
        return e / e.sum(1, keepdims=True)

    def _backward(self, cache, dz):
        g: dict[str, np.ndarray] = {}
        L = len(self.sizes) - 1
        for i in range(L - 1, -1, -1):
            c = cache[i]
            if c[0] == "out":
                a = c[1]
                g[f"W{i}"] = a.T @ dz
                g[f"b{i}"] = dz.sum(0)
                da = dz @ self.p[f"W{i}"].T
            else:
                _, a, zh, inv, y, mask = c
                dh = da if mask is None else da * mask
                dy = dh * _gelu_grad(y)
                g[f"g{i}"] = (dy * zh).sum(0)
                g[f"s{i}"] = dy.sum(0)
                dzh = dy * self.p[f"g{i}"]
                n = zh.shape[1]
                dzz = inv / n * (n * dzh - dzh.sum(1, keepdims=True)
                                 - zh * (dzh * zh).sum(1, keepdims=True))
                g[f"W{i}"] = a.T @ dzz
                g[f"b{i}"] = dzz.sum(0)
                da = dzz @ self.p[f"W{i}"].T
            dz = da
        return g

    def fit(self, X, y, w, Xv, yv, epochs=40, batch=64, lr=2e-3, wd=1e-4,
            smooth=0.05, seed=7, log=None):
        rng = np.random.default_rng(seed)
        K = self.sizes[-1]
        m = {k: np.zeros_like(v) for k, v in self.p.items()}
        v2 = {k: np.zeros_like(v) for k, v in self.p.items()}
        b1, b2, step = 0.9, 0.999, 0
        best, best_p, patience = -1.0, None, 0
        n = len(X)
        for ep in range(epochs):
            order = rng.permutation(n)
            cur_lr = lr * (0.5 * (1 + np.cos(np.pi * ep / epochs)))  # cosine
            for s in range(0, n, batch):
                ib = order[s:s + batch]
                xb, yb, wb = X[ib], y[ib], w[ib]
                z, cache = self._forward(xb, train=True, rng=rng)
                z = z - z.max(1, keepdims=True)
                pr = np.exp(z); pr /= pr.sum(1, keepdims=True)
                tgt = np.full((len(ib), K), smooth / K, np.float32)
                tgt[np.arange(len(ib)), yb] += 1.0 - smooth
                dz = (pr - tgt) * (wb[:, None] / wb.sum())
                grads = self._backward(cache, dz.astype(np.float32))
                step += 1
                for k, gk in grads.items():
                    m[k] = b1 * m[k] + (1 - b1) * gk
                    v2[k] = b2 * v2[k] + (1 - b2) * gk * gk
                    mh = m[k] / (1 - b1 ** step)
                    vh = v2[k] / (1 - b2 ** step)
                    upd = cur_lr * mh / (np.sqrt(vh) + 1e-8)
                    if k.startswith("W"):
                        upd = upd + cur_lr * wd * self.p[k]
                    self.p[k] -= upd.astype(np.float32)
            acc = float((self.logits(Xv).argmax(1) == yv).mean()) if len(Xv) else 1.0
            if log:
                log(f"época {ep + 1}/{epochs} — validação {acc:.1%}")
            if acc > best + 1e-4:
                best, best_p, patience = acc, {k: v.copy() for k, v in self.p.items()}, 0
            else:
                patience += 1
                if patience >= 6 and ep >= 12:
                    break
        if best_p is not None:
            self.p = best_p
        self.calibrate(Xv, yv)
        return best

    def calibrate(self, Xv, yv):
        """Temperature scaling: escolhe T que minimiza a perda na validação."""
        if not len(Xv):
            return
        z = self.logits(Xv)
        best_t, best_l = 1.0, 1e9
        # 1.4.3 — T a partir de 1,0. A validação é fácil (frases geradas, ~99 %
        # de acerto), então a perda era mínima no limite de baixo (T=0,5), que
        # deixa a rede MAIS confiante: frase que ela nunca viu ("vc está me
        # ouvindo") saía "aumentar volume (99 %)". T ≥ 1 nunca aguça.
        for T in np.linspace(1.0, 3.0, 21):
            zz = z / T
            zz = zz - zz.max(1, keepdims=True)
            lp = zz - np.log(np.exp(zz).sum(1, keepdims=True))
            loss = -lp[np.arange(len(yv)), yv].mean()
            if loss < best_l:
                best_t, best_l = float(T), loss
        self.T = best_t

    def save(self, path: Path, meta: dict):
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
        for k in net.p:
            net.p[k] = d[k].astype(np.float32)
        net.T = float(d["T"])
        meta = json.loads(bytes(d["meta"]).decode())
        return net, meta


def _keras_provavel() -> bool:
    """Barato (não importa o TensorFlow): o Keras vai ser o motor?"""
    try:
        from core import neural_backend as _B
        return _B.keras_provavel()
    except Exception:
        return False


def _net_class():
    """A rede que o IntentBrain usa: a do Keras (se houver TensorFlow) ou o IntentMLP de NumPy daqui.
    As duas gravam o mesmo .npz, então trocar de uma para a outra não perde o treino."""
    try:
        from core import neural_backend as _B
        if _B.usar_keras():
            from core.keras_intent import KerasIntentMLP
            return KerasIntentMLP
    except Exception as e:
        print(f"[IntentNet] Keras indisponível ({e}) — usando NumPy")
    return IntentMLP


# ══════════════════════════════════════════════════════════════════════════════
# Dados de treino (gerados) — PT-BR e EN
# ══════════════════════════════════════════════════════════════════════════════

_APPS = ["spotify", "chrome", "whatsapp", "discord", "steam", "word", "excel",
         "bloco de notas", "notepad", "calculadora", "vscode", "vs code", "telegram",
         "firefox", "edge", "obs", "netflix", "youtube", "photoshop", "explorador de arquivos",
         "configuracoes", "terminal", "outlook", "teams", "zoom", "paint", "epic games",
         "minecraft", "valorant", "capcut", "canva", "gmail", "instagram", "brave"]
_N = ["1", "2", "3", "5", "10", "15", "20", "25", "30", "40", "45", "50", "60", "70",
      "75", "80", "90", "100", "um", "dois", "tres", "cinco", "dez", "quinze", "vinte",
      "trinta", "quarenta", "cinquenta", "sessenta", "noventa"]
_NOTES = ["comprar leite", "ligar pro joao amanha", "pagar a conta de luz",
          "reuniao as 15h", "estudar python", "levar o carro na revisao",
          "a senha do wifi esta na gaveta", "buy milk", "call mom", "renew passport",
          "ideia de video sobre ia", "trocar a lampada da sala", "devolver o livro"]

_PRE = ["", "", "", "", "jarvis ", "por favor ", "ei jarvis ", "voce pode ", "pode ",
        "consegue ", "quero que voce ", "me ", "please ", "hey jarvis ", "can you ",
        "could you ", "i want you to ", "faz o favor de ", "rapido "]
_POS = ["", "", "", "", " por favor", " agora", " pra mim", " ai", " please", " now",
        " for me", " rapidinho", " jarvis"]

T: dict[str, list[str]] = {
    "time_now": ["que horas sao", "que hora e agora", "me diz as horas", "fala a hora",
                 "horas", "qual o horario", "qual e a hora", "sabe que horas sao",
                 "que horas tem", "hora atual", "what time is it", "tell me the time",
                 "current time", "whats the time", "do you know the time", "time please",
                 "ja e que horas", "olha a hora pra mim"],
    "date_today": ["que dia e hoje", "qual a data de hoje", "data de hoje", "hoje e que dia",
                   "em que dia estamos", "qual o dia do mes", "que dia da semana e hoje",
                   "what is the date today", "whats todays date", "what day is it",
                   "today date", "qual e a data", "hoje e dia quanto"],
    "open_app": [
                 "lanca o {app}", "manda abrir o {app}", "quero usar o {app}", "sobe o {app}", "dispara o {app}", "abre pra mim o {app}", "{app} abre", "abre o {app} ai","abre o {app}", "abrir {app}", "abra o {app}", "abre {app}", "inicia o {app}",
                 "executa o {app}", "liga o {app}", "abre o aplicativo {app}", "abre o programa {app}",
                 "abre a {app}", "quero abrir o {app}", "abre meu {app}", "bota o {app}",
                 "open {app}", "launch {app}", "start {app}", "open the {app} app",
                 "run {app}", "abre ai o {app}", "carrega o {app}", "entra no {app}"],
    "volume_up": [
                 "ta baixo aumenta", "ta baixo demais aumenta", "esta muito baixo", "baixo demais", "ta baixinho", "o som ta baixo", "o volume ta baixo sobe", "ta baixo", "muito baixo aumenta ai", "too quiet turn it up",
                 "joga o volume pra cima", "nao to ouvindo nada", "nao to escutando", "mais alto", "aumenta isso", "sobe mais", "poe mais alto", "deixa mais alto", "aumenta o audio", "turn up the sound","aumenta o volume", "aumentar volume", "sobe o volume", "mais volume",
                  "volume mais alto", "aumenta o som", "coloca mais alto", "ta muito baixo",
                  "aumenta um pouco o volume", "volume up", "turn it up", "turn the volume up",
                  "louder", "increase volume", "raise the volume", "aumenta ai o som",
                  "nao to ouvindo aumenta", "sobe o som"],
    "volume_down": [
                 "ta alto abaixa", "ta alto demais diminui", "o som ta alto", "o volume ta alto baixa", "ta altissimo", "too loud turn it down",
                 "ta estourando", "abaixa isso", "mais baixo", "deixa mais baixo", "ta alto demais", "diminui o audio", "baixa esse som","diminui o volume", "abaixa o volume", "baixa o volume", "menos volume",
                    "volume mais baixo", "abaixa o som", "ta muito alto", "diminuir o som",
                    "baixa um pouco", "volume down", "turn it down", "turn the volume down",
                    "quieter", "lower the volume", "decrease volume", "abaixa ai",
                    "reduz o volume", "diminui o som"],
    "volume_mute": [
                 "cala a boca do pc", "fica quieto", "mudo agora", "sem audio", "zera o som", "tira o audio","muta o som", "silencia", "tira o som", "sem som", "mudo", "mutar o volume",
                    "deixa no mudo", "silenciar o computador", "corta o som", "mute",
                    "mute the sound", "mute the volume", "silence", "desliga o som",
                    "coloca no mudo"],
    "volume_set": ["volume em {n}", "coloca o volume em {n}", "volume no {n}", "volume {n}",
                   "deixa o volume em {n} por cento", "ajusta o volume pra {n}",
                   "volume {n}%", "poe o volume no {n}", "muda o volume para {n}",
                   "set volume to {n}", "volume to {n} percent", "set the volume at {n}",
                   "coloca o som em {n}", "volume a {n} por cento"],
    "media_play_pause": [
                 "para essa musica", "para a musica", "pausa isso", "volta a tocar", "toca de novo", "continua tocando", "stop the music","pausa a musica", "pausa", "da play", "toca a musica", "continua a musica",
                         "pause", "play", "resume the music", "pause the music", "para a musica",
                         "despausa", "retoma a musica", "play music", "solta o som",
                         "pausa o video", "da pause"],
    "media_next": [
                 "essa e ruim troca", "muda a musica", "vai pra proxima", "outra musica","proxima musica", "pula a musica", "passa a musica", "avanca a musica",
                   "proxima faixa", "pular", "proxima", "next song", "skip", "skip this song",
                   "next track", "troca de musica", "pula essa"],
    "media_previous": [
                 "poe a de antes", "a de antes", "volta essa", "toca a de antes", "coloca a anterior","musica anterior", "volta a musica", "volta uma musica", "faixa anterior",
                       "voltar musica", "previous song", "go back a song", "previous track",
                       "toca a anterior", "volta pra anterior"],
    "timer_start": ["timer de {n} {unit}", "coloca um timer de {n} {unit}", "cronometro de {n} {unit}",
                    "me avisa em {n} {unit}", "conta {n} {unit}", "liga um timer de {n} {unit}",
                    "marca {n} {unit}", "temporizador de {n} {unit}", "alarme daqui a {n} {unit}",
                    "set a timer for {n} {unit}", "timer {n} {unit}", "start a {n} {unit} timer",
                    "countdown {n} {unit}", "remind me in {n} {unit}", "timer de meia hora",
                    "coloca um timer de uma hora", "inicia um timer de {n} {unit}"],
    "timer_status": [
                 "o timer ta acabando", "o timer ja acabou", "falta muito no timer", "quanto tempo tem no timer","quanto falta no timer", "quanto tempo falta", "como ta o timer",
                     "tempo restante do timer", "quanto falta pro alarme", "timer status",
                     "how much time is left", "how long left on the timer", "time left",
                     "quanto tempo ainda falta no cronometro"],
    "timer_cancel": ["cancela o timer", "para o timer", "desliga o timer", "cancelar cronometro",
                     "tira o timer", "esquece o timer", "cancel the timer", "stop the timer",
                     "cancel all timers", "desativa o alarme do timer", "apaga o timer"],
    "note_add": [
                 "guarda ai {txt}", "registra {txt}", "toma nota {txt}", "nao me deixa esquecer {txt}", "salva ai {txt}","anota {txt}", "anote {txt}", "anotar {txt}", "faz uma nota {txt}", "nota {txt}",
                 "guarda essa nota {txt}", "escreve ai {txt}", "lembra que {txt}",
                 "adiciona uma nota {txt}", "salva a nota {txt}", "take a note {txt}",
                 "note that {txt}", "write down {txt}", "add a note {txt}",
                 "cria uma nota {txt}", "anota ai {txt}"],
    "note_list": ["quais sao minhas notas", "le minhas notas", "mostra as notas", "minhas anotacoes",
                  "o que eu anotei", "lista as notas", "ler notas", "read my notes",
                  "show my notes", "what are my notes", "what did i write down",
                  "quais notas eu tenho", "abre minhas notas"],
    "email_check": [
                 "da uma olhada no meu gmail", "olha meu gmail", "ve meu outlook", "checa o hotmail", "tem algo no email", "chegou alguma coisa no email","verifica meu email", "verificar email", "checa meu email", "tenho email novo",
                    "tem email novo", "olha meu email", "ve meus emails", "chegou email",
                    "le meus emails", "abre minha caixa de entrada", "confere o email",
                    "check my email", "any new emails", "do i have new mail", "check my inbox",
                    "read my emails", "verifica o gmail", "tem mensagem no email"],
    "system_status": ["como ta o computador", "status do sistema", "uso da cpu", "quanto de memoria ta usando",
                      "como esta o pc", "a cpu ta alta", "temperatura do processador", "uso de ram",
                      "system status", "how is my computer", "cpu usage", "memory usage",
                      "o pc ta pesado", "desempenho do computador", "como ta a maquina"],
}

_NONE = [
    # perguntas e conversa
    "qual a capital da franca", "me conta uma piada", "quem descobriu o brasil",
    "o que voce acha de inteligencia artificial", "como voce esta", "bom dia", "boa noite",
    "obrigado", "valeu jarvis", "tudo bem", "quem e voce", "qual e o seu nome",
    "explica o que e uma rede neural", "como funciona a fotossintese", "quanto e 15 vezes 32",
    "traduz bom dia para ingles", "qual o sentido da vida", "me da uma receita de bolo",
    "what is the capital of japan", "tell me a joke", "how are you", "thank you",
    "who won the world cup", "explain quantum computing", "write a poem about the sea",
    # tarefas complexas e quase-comandos (Gemini resolve)
    "abre o arquivo relatorio pdf e resume", "abre a pasta downloads", "abre o site do banco",
    "pesquisa o preco do iphone", "pesquisa o horario do jogo do flamengo",
    "qual o volume de vendas de 2024", "quanto tempo leva de carro ate sao paulo",
    "como fazer um timer em python", "o que e uma nota fiscal", "qual a nota do filme duna",
    "me lembra de ligar pra minha mae amanha as 10", "cria uma pasta chamada projetos",
    "manda mensagem pro joao dizendo que vou atrasar", "toca a musica bohemian rhapsody no youtube",
    "coloca um video de gato no youtube", "qual a temperatura la fora", "vai chover hoje",
    "previsao do tempo para amanha", "quanto ta o dolar", "noticias de hoje",
    "escreve um email para o meu chefe", "resume esse texto", "corrige meu codigo",
    "olha a minha tela", "o que voce ve na camera", "tira um print e me fala o que tem",
    "desliga o computador", "reinicia o pc", "organiza minha area de trabalho",
    "procura o arquivo curriculo", "quanto espaco tem no disco", "instala o python",
    "faz um plano de estudos", "converte 10 dolares em reais", "quantos km tem uma milha",
    "qual o melhor celular de 2026", "compara o iphone com o galaxy", "me ajuda a dormir",
    "fala mais devagar", "fala em ingles", "repete o que voce disse", "esquece isso",
    "o que eu te pedi ontem", "voce lembra do meu nome", "meu nome e andre",
    "abre uma aba nova e pesquisa receitas", "fecha o chrome", "fecha essa janela",
    "aumenta o brilho", "diminui o brilho da tela", "ativa o modo escuro",
    "search for flights to lisbon", "open the downloads folder and find my resume",
    "send a message to maria", "what's the weather like", "remind me to buy bread tomorrow",
    "how many minutes in a day", "what is the volume of a sphere", "play despacito on youtube",
    "turn off the computer", "summarize this file", "what do you see on my screen",
    "how much is bitcoin", "write a python script", "set brightness to 50",
    "quem e o presidente do brasil", "quantos anos tem a terra", "o que significa saudade",
    "me recomenda um filme", "qual musica ta tocando", "quem canta essa musica",
    "o timer de pomodoro funciona como", "o que e um email marketing", "como criar um email no gmail",
    "as notas do enem ja sairam", "anotacoes de aula de historia sobre a revolucao francesa explica",
    "quanto tempo dura um filme", "que horas abre o mercado", "que horas comeca o jogo",
    "que dia e o carnaval", "qual a hora certa de plantar", "melhor hora para treinar",
    "hora de dormir ideal", "quantas horas devo dormir", "qual o horario de verao",
    "que horas sao em toquio", "qual a melhor hora pra postar", "a hora do rush",
    "o dia de hoje foi cansativo", "que dia nasceu einstein", "volume de agua no corpo",
    "aumenta minhas chances de passar", "abaixa o preco disso", "tocar violao como aprender",
    "proxima copa do mundo", "anterior ao seculo 20", "o email do joao e qual",
    "manda um email para a ana", "responde o email do chefe", "abre o jogo comigo",
    "o pc gamer ideal", "status do meu pedido", "timer pomodoro o que e", "quando e o natal", "a que horas o sol nasce amanha",
    "abre o jogo pra mim conta a verdade", "nao abre nada", "nao precisa abrir",
    "o volume do livro dois", "aumenta a fonte do texto", "diminui o zoom",
    "sim", "nao", "ok", "pode ser", "continua", "para", "cancela isso", "deixa pra la",
    "hmm", "e ai", "tchau", "ate mais", "boa tarde", "te amo jarvis", "voce e incrivel",
    # 1.4.3 — conferir se ele está ouvindo NÃO é pedido de volume
    "voce esta me ouvindo", "vc esta me ouvindo", "ta me ouvindo", "tá me ouvindo ai",
    "voce consegue me ouvir", "consegue me escutar", "esta me escutando", "me escuta",
    "voce ta ai", "vc ta ai", "ta ai", "ta me vendo", "voce me ve", "alo", "alo alo",
    "testando", "teste de microfone", "can you hear me", "are you listening",
    "are you there", "hello can you hear me", "ouviu", "entendeu", "escutou o que eu falei",
    # confirmações e respostas curtas que dependem da conversa
    "ta ok", "ta bom", "beleza", "certo", "entendi", "isso", "isso mesmo", "isso ok",
    "voltei", "pronto", "ja foi", "ja foi executado", "feito", "valeu", "obrigado nexus",
    "nao funcionou", "nao abriu", "cade", "tem nada aqui", "e agora", "faz isso",
    "verifica pra mim", "pode fazer", "manda ver", "so isso por enquanto",
    "fala sempre portugues", "fala em portugues", "responde em portugues",
]
# 2.3 — pedidos das funções novas (casa, finanças, tarefas, compras, hábitos, contatos, manutenção,
# texto, diário, memória, projetos…). A rede NÃO pode sequestrar estes: o Gemini escolhe a função certa.
_NONE_FERRAMENTAS = [
    "liga a luz da sala", "apaga todas as luzes", "acende a luz do quarto", "luz da sala em 40 por cento",
    "poe o ar em 22 graus", "abre a cortina", "tranca a porta da frente", "ativa a cena cinema",
    "a porta esta trancada", "liga o ventilador do quarto", "desliga a tomada da cafeteira",
    "gastei 50 reais no mercado", "paguei 120 de luz", "recebi meu salario", "quanto gastei esse mes",
    "onde mais gastei dinheiro", "define um limite de 800 para alimentacao", "apaga o ultimo gasto",
    "marca a tarefa como feita",
    "o que tenho para fazer hoje", "adiciona a tarefa pagar o boleto", "tarefas atrasadas",
    "poe leite na lista de compras", "poe pao e ovos na lista", "adiciona arroz na lista do mercado",
    "o que falta comprar", "comprei o leite", "tira o pao da lista de compras", "lista da farmacia",
    "cria o habito beber agua", "bebi dois copos de agua", "fiz exercicio hoje", "como estao meus habitos",
    "quantos dias seguidos de leitura", "meta de 8 copos de agua",
    "salva o contato do marcos", "qual o telefone da maria", "quem faz aniversario essa semana",
    "o aniversario da ana e dia 12 de marco", "muda o email do carlos",
    "limpa os arquivos temporarios", "faz backup da pasta projetos", "qual o meu ip",
    "testa a conexao com o google", "como esta a bateria", "o que esta ocupando espaco no disco",
    "gera um uuid", "faz o hash sha 256 disso", "codifica em base64", "formata esse json",
    "conta as palavras desse texto", "transforma em maiusculas", "que dia e o timestamp 1760000000",
    "escreve no diario que hoje foi bom", "meu humor hoje e 4", "o que eu escrevi ontem no diario",
    "como tem sido meu humor", "o que eu falei sobre a viagem", "procura nas minhas coisas algo sobre dinheiro",
    "o que anotei sobre o projeto", "registra o projeto loja virtual", "qual o proximo passo do projeto",
    "cria um site de portfolio", "faz um jogo da cobrinha", "altera o projeto portfolio", "desfaz a ultima alteracao",
    "como chego no aeroporto", "restaurantes perto de mim", "quais as noticias de tecnologia",
    "da um foco de 25 minutos", "me avisa se o bitcoin passar de 400 mil", "planeja minha tarde",
    "me da o briefing do dia", "diagnostico do nexus", "o que deu errado hoje", "relatorio da isa",
    "reconhece meu rosto", "quem esta na camera", "conta as pessoas na imagem", "cadastra meu rosto",
    "atualiza o nexus", "treina a rede neural", "mostra como esta a rede neural", "previsao de habitos",
    "tem alguma coisa estranha no meu pc", "exporta o dataset do cerebro local",
    "nota fiscal do mercado", "lista de tarefas",
]
_TOPICS = ["futebol", "historia do brasil", "python", "receitas", "viagem para portugal",
           "meu trabalho", "o mercado financeiro", "filmes de ficcao", "a lua", "musica classica",
           "minha dieta", "carros eletricos", "o universo", "programacao", "economia"]
_NONE_FRAMES = ["me fala sobre {t}", "o que voce sabe sobre {t}", "pesquisa sobre {t}",
                "escreve um texto sobre {t}", "tenho uma duvida sobre {t}", "me explica {t}",
                "tell me about {t}", "what do you know about {t}", "quero aprender {t}",
                "faz um resumo sobre {t}", "cria uma apresentacao sobre {t}"]


def _typo(s: str, rng: random.Random) -> str:
    if len(s) < 5:
        return s
    i = rng.randrange(1, len(s) - 1)
    op = rng.random()
    if op < 0.4:
        return s[:i] + s[i + 1:]                       # apaga letra
    if op < 0.8 and s[i] != " " and s[i + 1] != " ":
        return s[:i] + s[i + 1] + s[i] + s[i + 2:]     # troca vizinhas
    return s[:i] + s[i] + s[i:]                        # dobra letra


def build_dataset(seed: int = 11) -> tuple[list[str], list[int]]:
    rng = random.Random(seed)
    X, Y = [], []

    def put(text, label):
        X.append(text); Y.append(INTENTS.index(label))

    for intent, pats in T.items():
        for _ in range(140):
            pat = rng.choice(pats)
            s = pat.format(app=rng.choice(_APPS), n=rng.choice(_N),
                           unit=rng.choice(["minutos", "minuto", "min", "segundos", "segundo",
                                            "horas", "hora", "minutes", "seconds", "hours"]),
                           txt=rng.choice(_NOTES))
            s = rng.choice(_PRE) + s + rng.choice(_POS)
            if rng.random() < 0.18:
                s = _typo(s, rng)
            put(s, intent)
    for _ in range(4):
        for s in _NONE:
            s2 = rng.choice(_PRE) + s + rng.choice(_POS) if rng.random() < 0.5 else s
            if rng.random() < 0.15:
                s2 = _typo(s2, rng)
            put(s2, "none")
    for _ in range(260):
        put(rng.choice(_NONE_FRAMES).format(t=rng.choice(_TOPICS)), "none")
    for _ in range(2):                               # 2.3 — pedidos das outras funções
        for s in _NONE_FERRAMENTAS:
            s2 = rng.choice(_PRE) + s + rng.choice(_POS) if rng.random() < 0.5 else s
            if rng.random() < 0.15:
                s2 = _typo(s2, rng)
            put(s2, "none")
    return X, Y


# ══════════════════════════════════════════════════════════════════════════════
# Slots — os detalhes que a regra lê depois que a rede decidiu
# ══════════════════════════════════════════════════════════════════════════════

_NUMW = {"zero": 0, "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4,
         "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10, "onze": 11,
         "doze": 12, "treze": 13, "quatorze": 14, "catorze": 14, "quinze": 15,
         "dezesseis": 16, "dezessete": 17, "dezoito": 18, "dezenove": 19, "vinte": 20,
         "trinta": 30, "quarenta": 40, "cinquenta": 50, "sessenta": 60, "setenta": 70,
         "oitenta": 80, "noventa": 90, "cem": 100, "one": 1, "two": 2, "three": 3,
         "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
         "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
         "sixty": 60, "a": 1, "an": 1}


def _numbers(t: str) -> list[tuple[int, int]]:
    """[(posição, valor)] — aceita '25', 'vinte e cinco', 'cinco'."""
    out, words = [], t.split()
    i = 0
    while i < len(words):
        w = words[i].rstrip("%")
        if w.isdigit():
            out.append((i, int(w))); i += 1; continue
        if w in _NUMW and w not in ("a", "an", "um", "uma") or (w in ("um", "uma") and i + 1 < len(words)
                                                              and words[i + 1].startswith(("min", "seg", "hor", "h"))):
            v = _NUMW[w]
            if i + 2 < len(words) and words[i + 1] == "e" and words[i + 2] in _NUMW:
                v += _NUMW[words[i + 2]]; out.append((i, v)); i += 3; continue
            out.append((i, v))
        i += 1
    return out


_OPEN_VERB = re.compile(
    r"^(?:.*?\b)?(?:abre|abrir|abra|abri|inicia|iniciar|inicie|executa|executar|liga|ligar|"
    r"bota|carrega|entra no|entra na|open|launch|start|run)\b\s*(?:ai\s+)?"
    r"(?:(?:o|a|os|as|meu|minha|the|my|aplicativo|app|programa|jogo|do|da)\s+)*")
_APP_TAIL = re.compile(r"\s+(?:por favor|agora|pra mim|ai|please|now|for me|rapidinho|nexus|jarvis|app)$")
_NOTE_LEAD = re.compile(
    r"^(?:.*?\b)?(?:anota ai|anota|anote|anotar|nota|guarda essa nota|escreve ai|lembra que|"
    r"adiciona uma nota|salva a nota|faz uma nota|cria uma nota|take a note|note that|"
    r"write down|add a note)\b[\s:,]*(?:que\s+)?")


def extract_slots(intent: str, text: str) -> dict | None:
    """Parâmetros para executar o comando, ou None se faltou algo essencial."""
    t = normalize(text)
    if intent == "open_app":
        m = _OPEN_VERB.match(t)
        if not m:
            return None
        app = t[m.end():].strip()
        for _ in range(3):
            app = _APP_TAIL.sub("", app).strip()
        if not app or len(app) > 40 or len(app.split()) > 4:
            return None
        if any(b in app.split() for b in ("arquivo", "pasta", "site", "aba", "file", "folder", "e", "and")):
            return None
        return {"app_name": app}
    if intent == "volume_set":
        nums = [v for _, v in _numbers(t) if 0 <= v <= 100]
        return {"value": nums[-1]} if nums else None
    if intent == "timer_start":
        if "meia hora" in t or "half an hour" in t:
            return {"minutes": 30}
        words = t.split()
        mins = secs = 0.0
        found = False
        for pos, v in _numbers(t):
            unit = words[pos + 1] if pos + 1 < len(words) else ""
            if unit == "e" and pos + 2 < len(words):
                unit = words[pos + 2]
            if unit.startswith(("hora", "hour", "h")) and not unit.startswith("ho" + "je"):
                mins += 60 * v; found = True
            elif unit.startswith(("min",)):
                mins += v; found = True
            elif unit.startswith(("seg", "sec", "s")):
                secs += v; found = True
        if not found:
            if re.search(r"\b(uma hora|an hour|one hour)\b", t):
                return {"minutes": 60}
            return None
        out = {}
        if mins: out["minutes"] = mins
        if secs: out["seconds"] = secs
        return out
    if intent == "note_add":
        m = _NOTE_LEAD.match(t)
        txt = t[m.end():].strip() if m else ""
        txt = _APP_TAIL.sub("", txt).strip()
        if len(txt) < 2:
            return None
        # usa o texto original (com acentos) a partir da mesma palavra
        orig_words = str(text).split()
        n_tail = len(txt.split())
        orig = " ".join(orig_words[-n_tail:]) if n_tail <= len(orig_words) else txt
        return {"text": orig.strip(" ,.:;")}
    return {}


# ══════════════════════════════════════════════════════════════════════════════
# Serviço: carregar, prever, aprender
# ══════════════════════════════════════════════════════════════════════════════

# 1.4.3 — "ouvindo/escutando" só vale como volume com negação ("não tô ouvindo
# nada"); "vc está me ouvindo?" é conversa e vai para o Gemini.
_VOL = r"volume|\bsom\b|audio|\balt[oa]\b|altissimo|baix[oa]|baixinho|loud|quiet|sound|turn it|estourando"
_VOL_UP = _VOL + r"|\bnao\b(?:\s+\w+){0,3}\s+(?:ouvindo|escutando|ouco|escuto)\b|can t hear|cant hear"
# 2.3 — "anota a tarefa…", "anota na lista de compras…", "escreve no diário…" são de OUTRAS funções:
# nunca viram nota rápida pela rede local.
_OUTRA_FUNCAO_DE_NOTA = re.compile(
    r"\btarefa|\blista\b|\bcompras?\b|\bdiario\b|\bcontato|\bgasto|\bgastei|\bdespesa|\bhabito|\bprojeto|"
    r"\blembrete|\baniversario|\bhumor\b|\bmeta\b")
_GUARDS = {k: re.compile(v) for k, v in {
    "time_now": r"\bhora|horario|\btime\b",
    "date_today": r"\bdia\b|\bdata\b|\bdate\b|\bday\b",
    "volume_up": _VOL_UP, "volume_down": _VOL, "volume_set": r"volume|\bsom\b|audio|sound",
    "volume_mute": r"mud[oa]|silenc|\bsom\b|audio|mute|quiet|\bcala|quieto|sound|volume",
    "media_play_pause": r"music|musica|\bplay\b|paus|\btoc[ao]|tocar|tocando|video|despausa|retoma|continua|\bpara\b|stop|resume",
    "media_next": r"music|musica|faixa|track|song|skip|\bpul[ao]|proxima|troca|\bnext\b|outra",
    "media_previous": r"music|musica|faixa|track|song|anterior|antes|previous|\bvolt[ao]",
    "timer_start": r"timer|cronometro|temporizador|alarme|avis[ae]|acord[ae]|\bconta\b|countdown|remind|\bmarca",
    "timer_status": r"timer|cronometro|temporizador|alarme|falta|left",
    "timer_cancel": r"timer|cronometro|temporizador|alarme",
    "note_add": r"\bnot[ae]|anot|lembra|guarda|escreve|registra|esquecer|salva|write|note",
    "note_list": r"\bnotas?\b|anota|notes|escrevi|wrote|write",
    "email_check": r"mail|inbox|caixa de entrada|gmail|outlook|hotmail",
    "system_status": r"cpu|\bram\b|memoria|computador|\bpc\b|maquina|sistema|system|computer|processador|desempenho|temperatura|lento|pesado|memory",
}.items()}


def load_settings() -> dict:
    d = {"enabled": True, "threshold": 0.85}
    try:
        d.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    return d


def save_settings(**kw) -> dict:
    d = load_settings(); d.update(kw)
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(d, indent=1), encoding="utf-8")
    except Exception as e:
        print(f"[IntentNet] não salvou config: {e}")
    return d


def exemplo_valido(text: str, intent: str) -> bool:
    """1.4.3 — só vira exemplo de um comando a frase que a própria rede poderia
    executar: com a palavra do assunto (a "trava") e os detalhes legíveis.
    Antes "ok" virava abrir aplicativo, "tá ok" virava anotar e "voltei" virava
    ler notas — o Gemini tinha agido pelo contexto da conversa, não pela frase."""
    t = normalize(text)
    if not t or intent not in INTENTS:
        return False
    if intent == "none":
        return True
    if len(t) > 160 or t.count(" ") > 20:
        return False
    if re.search(r"[a-z]:\\|https?:|www\.|\.(?:exe|lnk|py|txt|bat)\b", str(text).lower()):
        return False                       # caminho, link, arquivo: não é comando simples
    guard = _GUARDS.get(intent)
    if guard is not None and not guard.search(t):
        return False
    if intent in ("note_add", "note_list") and _OUTRA_FUNCAO_DE_NOTA.search(t):
        return False
    return extract_slots(intent, text) is not None


def _load_examples() -> list[dict]:
    try:
        d = json.loads(EXAMPLES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(d, list):
        return []
    # exemplos antigos que não passam na regra nova são ignorados no treino
    return [e for e in d if isinstance(e, dict)
            and exemplo_valido(str(e.get("text") or ""), str(e.get("intent") or ""))]


def _save_examples(ex: list[dict]) -> None:
    try:
        EXAMPLES_FILE.parent.mkdir(parents=True, exist_ok=True)
        EXAMPLES_FILE.write_text(json.dumps(ex[-2000:], ensure_ascii=False, indent=0), encoding="utf-8")
    except Exception as e:
        print(f"[IntentNet] não salvou exemplos: {e}")


class IntentBrain:
    def __init__(self, log=print):
        self._log = log
        self._net: IntentMLP | None = None
        self.meta: dict = {}
        self._lock = threading.Lock()
        self._training = False
        self._new_since_train = 0
        self.status = "não carregada"

    # ── ciclo de vida ──────────────────────────────────────────────────────
    def _fingerprint(self, user_ex: list[dict]) -> str:
        h = hashlib.sha1(f"{DATA_VERSION}|{INTENTS}".encode())
        for e in user_ex:
            h.update(f"{e.get('text')}|{e.get('intent')}".encode())
        return h.hexdigest()[:16]

    def start(self, block: bool = False) -> None:
        """Carrega do disco; se não houver modelo atualizado, treina em segundo plano.

        Com o TensorFlow instalado a rede é a do Keras (core/keras_intent.py). O import dele
        leva alguns segundos, então roda numa thread: a abertura do NEXUS não espera, e
        até a rede ficar pronta tudo vai para o Gemini (igual a quando ela está treinando)."""
        if not block and _keras_provavel():
            self.status = "carregando…"
            threading.Thread(target=self._carregar_ou_treinar, args=(True,), daemon=True,
                             name="intent-load").start()
            return
        self._carregar_ou_treinar(block)

    def _carregar_ou_treinar(self, block: bool) -> None:
        user_ex = _load_examples()
        fp = self._fingerprint(user_ex)
        try:
            if MODEL_FILE.exists():
                net, meta = _net_class().load(MODEL_FILE)
                if meta.get("fingerprint") == fp and net.sizes[-1] == len(INTENTS):
                    with self._lock:
                        self._net, self.meta = net, meta
                    self.status = "pronta"
                    self._log(f"[IntentNet] carregada — validação {meta.get('val_acc', 0):.1%}")
                    return
        except Exception as e:
            self._log(f"[IntentNet] modelo salvo inválido ({e}) — retreinando")
        self.retrain(block=block)

    def retrain(self, block: bool = False, progress=None) -> None:
        if self._training:
            return
        self._training = True
        self.status = "treinando…"

        def run():
            try:
                t0 = time.time()
                X, Y = build_dataset()
                W = [1.0] * len(X)
                user_ex = _load_examples()
                for e in user_ex:
                    if e.get("intent") in INTENTS:
                        X.append(e["text"]); Y.append(INTENTS.index(e["intent"])); W.append(3.0)
                rng = np.random.default_rng(5)
                idx = rng.permutation(len(X))
                cut = int(len(X) * 0.88)
                tr, va = idx[:cut], idx[cut:]
                Xa = featurize(X)
                Ya = np.array(Y, np.int64)
                Wa = np.array(W, np.float32)
                net = _net_class()()
                acc = net.fit(Xa[tr], Ya[tr], Wa[tr], Xa[va], Ya[va], log=progress)
                meta = {"fingerprint": self._fingerprint(user_ex), "val_acc": acc,
                        "samples": len(X), "user_examples": len(user_ex),
                        "trained_at": time.strftime("%d/%m/%Y %H:%M"),
                        "seconds": round(time.time() - t0, 1), "T": net.T}
                net.save(MODEL_FILE, meta)
                with self._lock:
                    self._net, self.meta = net, meta
                self._new_since_train = 0
                self.status = "pronta"
                try:
                    self._preparar_verificador()
                except Exception:
                    pass
                self._log(f"[IntentNet] treinada em {meta['seconds']}s — validação {acc:.1%} "
                          f"({len(X)} frases, {len(user_ex)} suas)")
            except Exception as e:
                self.status = f"erro: {e}"
                self._log(f"[IntentNet] falha no treino: {e}")
            finally:
                self._training = False

        if block:
            run()
        else:
            threading.Thread(target=run, daemon=True, name="intent-train").start()

    @property
    def ready(self) -> bool:
        return self._net is not None

    # ── uso ────────────────────────────────────────────────────────────────
    def predict(self, text: str) -> tuple[str, float, list[tuple[str, float]]]:
        with self._lock:
            net = self._net
        if net is None or not normalize(text):
            return "none", 0.0, []
        p = net.proba(featurize([text]))[0]
        order = np.argsort(-p)[:3]
        top = [(INTENTS[i], float(p[i])) for i in order]
        return top[0][0], top[0][1], top

    def route(self, text: str, threshold: float | None = None):
        """(intent, confiança, slots) se for para executar localmente; senão None."""
        if threshold is None:
            threshold = float(load_settings().get("threshold", 0.85))
        intent, conf, _ = self.predict(text)
        if intent == "none" or conf < threshold:
            return None
        # Trava de segurança: a rede decide, mas só executa localmente se a
        # frase também tiver uma palavra do assunto. "aumenta o tamanho da
        # letra" pode soar como volume para a rede — sem "volume/som/alto…"
        # ela vai para o Gemini, que resolve do jeito certo.
        guard = _GUARDS.get(intent)
        if guard is not None and not guard.search(normalize(text)):
            return None
        if intent in ("note_add", "note_list") and _OUTRA_FUNCAO_DE_NOTA.search(normalize(text)):
            return None
        if load_settings().get("verificar", True):
            # 2.3 — segunda opinião (core/roteador.py): só executa local se os vizinhos não discordarem
            try:
                from core import roteador as _R
                if not _R.verificador.pronto:
                    self._preparar_verificador()
                ok, motivo = _R.verificador.concorda(text, intent)
                if not ok:
                    self._log(f"[IntentNet] verificador vetou '{text[:40]}' → {intent}: {motivo}")
                    return None
            except Exception as e:
                self._log(f"[IntentNet] verificador indisponível ({e})")
        slots = extract_slots(intent, text)
        if slots is None:
            return None
        return intent, conf, slots

    def _preparar_verificador(self) -> None:
        """Índice dos exemplos (treino + os seus) para a segunda opinião."""
        from core import roteador as _R
        X, Y = build_dataset()
        textos, rotulos = list(X), [INTENTS[y] for y in Y]
        for e in _load_examples():
            if e.get("intent") in INTENTS and e.get("text"):
                textos.append(e["text"]); rotulos.append(e["intent"])
        _R.verificador.construir(textos, rotulos)

    def learn(self, text: str, intent: str) -> None:
        """Guarda um exemplo vindo do uso real e retreina a cada RETRAIN_EVERY."""
        text = str(text or "").strip()
        if not text or intent not in INTENTS or len(text) > 200:
            return
        if not exemplo_valido(text, intent):
            self._log(f"[IntentNet] não aprendi '{text[:40]}' → {intent} (não é um comando simples)")
            return
        ex = _load_examples()
        if ex and ex[-1].get("text") == text and ex[-1].get("intent") == intent:
            return
        ex.append({"text": text, "intent": intent, "at": time.time()})
        _save_examples(ex)
        self._new_since_train += 1
        self._log(f"[IntentNet] aprendi: '{text}' → {intent}")
        if self._new_since_train >= RETRAIN_EVERY:
            self.retrain()

    def forget(self) -> None:
        _save_examples([])
        self.retrain()

    def stats(self) -> dict:
        ex = _load_examples()
        return {"status": self.status, "val_acc": self.meta.get("val_acc"),
                "samples": self.meta.get("samples"), "user_examples": len(ex),
                "trained_at": self.meta.get("trained_at"), "seconds": self.meta.get("seconds"),
                "pending": self._new_since_train, "intents": len(INTENTS) - 1,
                "motor": "keras" if _keras_provavel() else "numpy"}


# ══════════════════════════════════════════════════════════════════════════════
# Mapeamento: ferramenta que o Gemini chamou → intenção (para aprender)
# ══════════════════════════════════════════════════════════════════════════════

def intent_from_tool(name: str, args: dict) -> str | None:
    a = {k: str(v).lower() for k, v in (args or {}).items()}
    if name in ("save_memory", "recall_memory", "undo", "close_camera"):
        return None          # ferramentas de bastidor: não dizem nada sobre o pedido
    if name == "open_app":
        return "open_app"
    if name == "email_checker" and a.get("action", "check") == "check":
        return "email_check"
    if name == "system_status":
        return "system_status"
    if name == "computer_settings":
        return {"volume_up": "volume_up", "volume_down": "volume_down",
                "mute": "volume_mute", "volume_set": "volume_set"}.get(a.get("action", ""))
    if name == "music_control":
        return {"play_pause": "media_play_pause", "next": "media_next",
                "previous": "media_previous", "mute": "volume_mute",
                "volume_up": "volume_up", "volume_down": "volume_down"}.get(a.get("command", ""))
    if name == "timer_action":
        return {"start": "timer_start", "status": "timer_status",
                "cancel": "timer_cancel"}.get(a.get("action", ""))
    if name == "quick_notes":
        return {"add": "note_add", "list": "note_list"}.get(a.get("action", ""))
    return "none"            # usou outra ferramenta: a frase não era comando simples


# Instância única usada pelo app
brain = IntentBrain()
