"""core/voz_emocao.py — voz em tempo real mais natural (NEXUS Ultra 2026 3.8).

Três coisas, todas locais e desligadas por padrão (config: voz_emocao, voz_interrupcao):
1. Emoção na SUA voz: mede energia, tom (f0), variação do tom e pausas de cada fala, compara com a sua média e, quando
   a voz foge muito dela (agitado, cansado, hesitante), manda ao modelo uma dica de como responder. Nada é gravado.
2. Correção e hesitação no TEXTO ("não, espera", "quer dizer…", "é… tipo…"): vira dica "a pessoa se corrigiu, vale o final".
3. Interrupção: decisão de cortar a resposta quando a sua voz passa por cima do eco (usa o EchoGuard existente).
Limites honestos: é prosódia simples (não é um modelo de emoção treinado) e erra; por isso só age com desvio forte e
com cooldown. A voz do NEXUS vem do modelo ao vivo: o tom dela só muda por instrução no texto, não por controle direto.
"""
from __future__ import annotations

import json
import re
import threading
import time
from collections import deque
from pathlib import Path

import numpy as np

from core import audio_feat as AF

ARQ_CALIB = Path(__file__).resolve().parent.parent / "config" / "voz_calibracao.json"
ESTADOS_CALIB = ("neutro", "cansado", "agitado")
MIN_CALIB = 6                  # falas por estado na calibração guiada
_CAMPOS = ("energia", "f0", "var_f0")
MIN_AMOSTRAS = 12              # falas para formar a sua linha de base
COOLDOWN_S = 150.0
_CORRECAO = re.compile(r"\b(n[aã]o,? (espera|pera|calma)|espera,? n[aã]o|quer dizer|ou melhor|na verdade,? n[aã]o|"
                       r"desconsidera|esquece (isso|o que eu disse)|corrigindo|perd[aã]o,? (eu )?quis dizer|errei)\b", re.I)
_HESITACAO = re.compile(r"(\b(hum+|[eé]h+|ahn+|tipo|sei l[aá]|n[aã]o sei|como que fala)\b[ ,.…]*){2,}|\.{3,}|…", re.I)

DICAS = {
    "agitado": "A voz do usuário está mais alta/rápida que o normal: responda calmo, curto e direto, sem enrolar.",
    "cansado": "A voz do usuário está mais baixa e lenta que o normal: seja gentil e breve; não empilhe perguntas.",
    "hesitante": "O usuário está hesitando (muitas pausas): ajude a organizar, ofereça 2 opções simples em vez de pergunta aberta.",
}


def prosodia(x: np.ndarray, taxa: int = AF.TAXA) -> dict | None:
    """x float32 mono. -> {energia, f0, var_f0, vozeado} ou None se curto demais/sem tom."""
    if x is None or len(x) < 0.3 * taxa:
        return None
    q = AF._quadros(x)
    rms = np.sqrt(np.mean(q * q, axis=1))
    limiar = max(0.01, min(float(np.percentile(rms, 20)) * 2.0, 0.5 * float(rms.max())))
    vozeados = rms > limiar
    if vozeados.sum() < 5:
        return None
    f0 = AF.f0_por_quadro(x, taxa)
    if f0.size < 5:
        return None
    return {"energia": float(np.mean(rms[vozeados])), "f0": float(np.median(f0)),
            "var_f0": float(np.std(f0) / max(np.mean(f0), 1.0)), "vozeado": float(vozeados.mean())}


class Emocao:
    def __init__(self, relogio=time.monotonic, arq_calib: Path | None = None):
        self.arq_calib = Path(arq_calib or ARQ_CALIB)
        self.calibrando: str | None = None
        self._amostras: list[dict] = []
        self.calib: dict = self._ler_calib()
        self.hist: deque = deque(maxlen=80)
        self.seg = AF.SegmentadorFala(min_s=0.6, max_s=6.0)
        self.relogio = relogio
        self._ultimo_aviso = -1e9
        self._ultimo_estado = "neutro"
        self._fila: deque = deque(maxlen=4)
        self._trava = threading.Lock()

    def alimentar(self, bloco) -> None:
        """Chamado no callback do microfone: só segmenta (barato); a análise roda em `processar()`."""
        try:
            for fala in self.seg.alimentar(bloco):
                self._fila.append(fala)
        except Exception:
            pass

    def processar(self) -> str | None:
        """Analisa as falas pendentes. Devolve a dica quando o estado muda e passou o cooldown."""
        dica = None
        while self._fila:
            fala = self._fila.popleft()
            p = prosodia(fala)
            if p is None:
                continue
            if self.calibrando:                                  # calibração guiada: só junta amostras, não comenta nada
                self._amostras.append(p)
                continue
            estado = self.classificar(p)
            self.hist.append(p)
            if estado != "neutro" and estado != self._ultimo_estado and self.relogio() - self._ultimo_aviso > COOLDOWN_S:
                self._ultimo_aviso = self.relogio()
                dica = DICAS[estado]
            self._ultimo_estado = estado
        return dica

    # ── calibração guiada (3.9) ──
    def _ler_calib(self) -> dict:
        try:
            d = json.loads(self.arq_calib.read_text(encoding="utf-8"))
            return {k: v for k, v in d.items() if k in ESTADOS_CALIB and isinstance(v, dict) and "media" in v}
        except Exception:
            return {}

    def iniciar_calibracao(self, estado: str) -> str:
        if estado not in ESTADOS_CALIB:
            raise ValueError("Estado inválido. Use: " + ", ".join(ESTADOS_CALIB))
        self.calibrando, self._amostras = estado, []
        self._fila.clear()
        return {"neutro": "Fale normalmente, umas 8 frases curtas.",
                "cansado": "Fale como fala quando está cansado, umas 8 frases curtas.",
                "agitado": "Fale como fala quando está agitado ou com pressa, umas 8 frases curtas."}[estado]

    def amostras_juntadas(self) -> int:
        return len(self._amostras)

    def concluir_calibracao(self) -> str:
        est, am = self.calibrando, list(self._amostras)
        self.calibrando, self._amostras = None, []
        if not est:
            return "Não há calibração em andamento."
        if len(am) < MIN_CALIB:
            return f"Só captei {len(am)} falas (preciso de {MIN_CALIB}). Tente de novo falando um pouco mais alto e em frases curtas."
        media = {k: float(np.mean([a[k] for a in am])) for k in ("energia", "f0", "var_f0", "vozeado")}
        desvio = {k: float(np.std([a[k] for a in am])) + 1e-6 for k in ("energia", "f0", "var_f0", "vozeado")}
        self.calib[est] = {"media": media, "desvio": desvio, "n": len(am)}
        self.arq_calib.parent.mkdir(parents=True, exist_ok=True)
        self.arq_calib.write_text(json.dumps(self.calib), encoding="utf-8")
        faltam = [e for e in ESTADOS_CALIB if e not in self.calib]
        return f"Calibrei “{est}” com {len(am)} falas." + (f" Falta: {', '.join(faltam)}." if faltam else " Calibração completa.")

    def limpar_calibracao(self) -> None:
        self.calib, self.calibrando, self._amostras = {}, None, []
        try:
            self.arq_calib.unlink()
        except OSError:
            pass

    def _classificar_calibrado(self, p: dict) -> str | None:
        """Com o 'neutro' calibrado usa a SUA linha de base; com mais um estado calibrado escolhe o mais próximo."""
        neu = self.calib.get("neutro")
        if not neu:
            return None
        sd = {k: max(neu["desvio"][k], 0.05 * abs(neu["media"][k]) + 1e-6) for k in _CAMPOS}
        def dist(c):
            return float(np.sqrt(sum(((p[k] - c["media"][k]) / sd[k]) ** 2 for k in _CAMPOS)))
        cand = {e: dist(c) for e, c in self.calib.items()}
        if len(cand) >= 2:
            melhor = min(cand, key=cand.get)
            return melhor
        z = {k: (p[k] - neu["media"][k]) / sd[k] for k in _CAMPOS}
        if z["energia"] > 2.0 and (z["f0"] > 1.0 or z["var_f0"] > 1.2):
            return "agitado"
        if z["energia"] < -2.0 and z["f0"] < -1.0:
            return "cansado"
        return "neutro"

    def classificar(self, p: dict) -> str:
        cal = self._classificar_calibrado(p)
        if cal is not None:
            vz = self.calib["neutro"]
            if cal == "neutro" and (p["vozeado"] - vz["media"]["vozeado"]) / max(vz["desvio"]["vozeado"], 0.05) < -2.0:
                return "hesitante"
            return cal
        if len(self.hist) < MIN_AMOSTRAS:
            return "neutro"
        base = {k: float(np.mean([h[k] for h in self.hist])) for k in ("energia", "f0", "var_f0", "vozeado")}
        dev = {k: float(np.std([h[k] for h in self.hist])) + 1e-6 for k in base}
        z = {k: (p[k] - base[k]) / dev[k] for k in base}
        if z["energia"] > 1.6 and (z["f0"] > 1.0 or z["var_f0"] > 1.2):
            return "agitado"
        if z["energia"] < -1.5 and z["f0"] < -0.8:
            return "cansado"
        if z["vozeado"] < -1.6:
            return "hesitante"
        return "neutro"


def dica_do_texto(texto: str) -> str:
    """Correção ou hesitação no que a pessoa disse. '' se nada."""
    t = texto or ""
    if _CORRECAO.search(t):
        return "O usuário se corrigiu no meio da frase: vale o que ele disse DEPOIS da correção; não repita o que ele desfez."
    if _HESITACAO.search(t):
        return DICAS["hesitante"]
    return ""


class Interrupcao:
    """Corta a resposta quando N blocos seguidos são voz do usuário por cima do eco. `eh_voz(bloco) -> bool` é injetada."""

    def __init__(self, eh_voz, blocos_necessarios: int = 4):
        self.eh_voz, self.n, self._seguidos = eh_voz, blocos_necessarios, 0

    def bloco(self, bloco) -> bool:
        try:
            self._seguidos = self._seguidos + 1 if self.eh_voz(bloco) else 0
        except Exception:
            self._seguidos = 0
        if self._seguidos >= self.n:
            self._seguidos = 0
            return True
        return False

    def zerar(self) -> None:
        self._seguidos = 0


tracker = Emocao()


# ── ligar/desligar (config/api_keys.json) com cache curto, para o callback do microfone não ler o disco toda hora ──
_cache_cfg = {"t": -1e9, "emocao": False, "interrupcao": False}


def _flags() -> dict:
    agora = time.monotonic()
    if agora - _cache_cfg["t"] > 5.0:
        try:
            from memory.config_manager import load_api_keys
            k = load_api_keys()
            _cache_cfg.update(emocao=bool(k.get("voz_emocao", False)), interrupcao=bool(k.get("voz_interrupcao", False)))
        except Exception:
            _cache_cfg.update(emocao=False, interrupcao=False)
        _cache_cfg["t"] = agora
    return _cache_cfg


def emocao_ligada() -> bool:
    return _flags()["emocao"] or tracker.calibrando is not None


def interrupcao_ligada() -> bool:
    return _flags()["interrupcao"]
