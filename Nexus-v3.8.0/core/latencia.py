"""Latência do NEXUS (Ultra 2026 3.3) — onde o tempo de cada pedido vai.

Para cada pedido do motor próprio o NEXUS mede as etapas:

  escutar     transcrever a sua fala (só por voz)
  preparar    montar o prompt (memória, arquivos) e escolher as ferramentas
  rota        a rede decidir rápido / forte / equipe
  modelo      o modelo pensar e escrever (inclui esperar o 1º token)
  ferramenta  as ferramentas rodarem (e quantas vieram do cache)

e o que importa de verdade: quanto tempo passou do FIM DA SUA FALA até ele COMEÇAR A FALAR.
No Gemini Live só existe esse tempo total (fim da fala → 1º áudio).

Tudo em memory/latencia.json (até 200 pedidos, só no PC). O painel da I.S.A. (⏱ Latência) e a voz
("Nexus, por que você está lento?") leem daqui. Nunca levanta erro para quem chama.
"""
from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent.parent / "memory" / "latencia.json"
VERSAO = 1
MAX_PEDIDOS = 200
ETAPAS = ("escutar", "preparar", "rota", "modelo", "ferramenta")
NOMES = {"escutar": "Escutar", "preparar": "Preparar", "rota": "Decidir a rota",
         "modelo": "Modelo pensar", "ferramenta": "Ferramenta rodar"}
DICAS = {
    "escutar": "A transcrição está demorando: use um modelo Whisper menor (tiny/base) ou ligue a GPU.",
    "preparar": "Montar o prompt está pesado: reduza a memória e os arquivos carregados a cada pedido.",
    "rota": "A decisão da rota é rápida em geral; se está alta, o roteador está treinando no 1º pedido.",
    "modelo": "O modelo é o gargalo: use o modelo rápido nos pedidos simples (o roteador já faz isso) "
              "ou um modelo menor/mais perto.",
    "ferramenta": "As ferramentas demoram: o cache já guarda clima e notícias; pesquisas na web dependem da internet.",
}

_trava = threading.RLock()
_atual: "Trace | None" = None


class Trace:
    def __init__(self, origem: str = "motor", texto: str = "", rota: str | None = None,
                 escutar_ms: float | None = None):
        self.origem, self.texto, self.rota = origem, str(texto or "")[:120], rota
        self.t0 = time.monotonic()
        self.escutar_ms = float(escutar_ms) if escutar_ms else 0.0
        self.etapas: dict[str, float] = {}
        if self.escutar_ms:
            self.etapas["escutar"] = self.escutar_ms
        self.primeira_fala_ms: float | None = None
        self.primeiro_token_ms: float | None = None
        self.ferramentas = 0
        self.cache_hits = 0
        self._modelo_t0: float | None = None
        self._fechado = False

    # ── medir ──
    @contextmanager
    def medir(self, etapa: str):
        t = time.monotonic()
        if etapa == "modelo" and self._modelo_t0 is None:
            self._modelo_t0 = t
        try:
            yield
        finally:
            self.etapas[etapa] = self.etapas.get(etapa, 0.0) + (time.monotonic() - t) * 1000

    def somar(self, etapa: str, ms: float) -> None:
        self.etapas[etapa] = self.etapas.get(etapa, 0.0) + max(0.0, float(ms))

    def primeiro_token(self) -> None:
        if self.primeiro_token_ms is None and self._modelo_t0 is not None:
            self.primeiro_token_ms = (time.monotonic() - self._modelo_t0) * 1000

    def primeira_fala(self) -> None:
        """Marca quando o NEXUS começou a falar: conta desde o FIM da sua fala (inclui o escutar)."""
        if self.primeira_fala_ms is None:
            self.primeira_fala_ms = self.escutar_ms + (time.monotonic() - self.t0) * 1000

    def ferramenta(self, ms: float, cache: bool = False) -> None:
        self.ferramentas += 1
        self.cache_hits += 1 if cache else 0
        self.somar("ferramenta", ms)

    # ── fechar ──
    def fechar(self, ok: bool = True) -> dict | None:
        global _atual
        if self._fechado:
            return None
        self._fechado = True
        with _trava:
            if _atual is self:
                _atual = None
        reg = {"t": int(time.time()), "origem": self.origem, "texto": self.texto, "rota": self.rota,
               "ok": bool(ok), "etapas": {k: int(v) for k, v in self.etapas.items()},
               "primeira_fala_ms": int(self.primeira_fala_ms) if self.primeira_fala_ms is not None else None,
               "primeiro_token_ms": int(self.primeiro_token_ms) if self.primeiro_token_ms is not None else None,
               "total_ms": int(self.escutar_ms + (time.monotonic() - self.t0) * 1000),
               "ferramentas": self.ferramentas, "cache": self.cache_hits}
        _gravar(reg)
        return reg


# ── o pedido em andamento (um de cada vez no motor próprio) ─────────────────
def iniciar(origem: str = "motor", texto: str = "", rota: str | None = None,
            escutar_ms: float | None = None) -> Trace:
    global _atual
    tr = Trace(origem, texto, rota, escutar_ms)
    with _trava:
        _atual = tr
    return tr


def atual() -> "Trace | None":
    return _atual


def marca_primeira_fala() -> None:
    tr = _atual
    if tr is not None:
        tr.primeira_fala()


def marca_ferramenta(ms: float, cache: bool = False) -> None:
    tr = _atual
    if tr is not None:
        tr.ferramenta(ms, cache)


def registrar_total(origem: str, ms: float) -> None:
    """Só o tempo total (fim da fala → 1º áudio): o que o Gemini Live deixa medir."""
    try:
        ms = float(ms)
        if 0 < ms < 60_000:
            _gravar({"t": int(time.time()), "origem": origem, "texto": "", "rota": None, "ok": True,
                     "etapas": {}, "primeira_fala_ms": int(ms), "primeiro_token_ms": None,
                     "total_ms": int(ms), "ferramentas": 0, "cache": 0})
    except Exception:
        pass


# ── disco ───────────────────────────────────────────────────────────────────
def _carregar(arquivo: Path | None = None) -> dict:
    try:
        d = json.loads((arquivo or ARQUIVO).read_text(encoding="utf-8"))
        if d.get("versao") == VERSAO and isinstance(d.get("pedidos"), list):
            return d
    except Exception:
        pass
    return {"versao": VERSAO, "pedidos": []}


def _gravar(reg: dict, arquivo: Path | None = None) -> None:
    arq = arquivo or ARQUIVO
    try:
        with _trava:
            d = _carregar(arq)
            d["pedidos"].append(reg)
            d["pedidos"] = d["pedidos"][-MAX_PEDIDOS:]
            arq.parent.mkdir(parents=True, exist_ok=True)
            tmp = arq.with_suffix(".tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            tmp.replace(arq)
    except Exception:
        pass


def pedidos(n: int = 50, arquivo: Path | None = None) -> list[dict]:
    return _carregar(arquivo)["pedidos"][-n:]


def esquecer(arquivo: Path | None = None) -> None:
    with _trava:
        arq = arquivo or ARQUIVO
        try:
            arq.parent.mkdir(parents=True, exist_ok=True)
            arq.write_text(json.dumps({"versao": VERSAO, "pedidos": []}), encoding="utf-8")
        except Exception:
            pass


# ── análise ─────────────────────────────────────────────────────────────────
def _pct(valores: list[float], p: float) -> int | None:
    if not valores:
        return None
    v = sorted(valores)
    return int(v[min(len(v) - 1, int(round(p * (len(v) - 1))))])


def relatorio(n: int = 50, arquivo: Path | None = None) -> dict:
    ped = pedidos(n, arquivo)
    com_fala = [p["primeira_fala_ms"] for p in ped if p.get("primeira_fala_ms") is not None]
    detalhados = [p for p in ped if p.get("etapas")]
    medias: dict[str, int] = {}
    for e in ETAPAS:
        vs = [p["etapas"][e] for p in detalhados if e in p["etapas"]]
        if vs:
            medias[e] = int(sum(vs) / len(vs))
    gargalo = max(medias, key=medias.get) if medias else None
    tokens = [p["primeiro_token_ms"] for p in detalhados if p.get("primeiro_token_ms") is not None]
    ferr = sum(p.get("ferramentas", 0) for p in ped)
    hits = sum(p.get("cache", 0) for p in ped)
    return {"pedidos": len(ped), "detalhados": len(detalhados),
            "fala_mediana_ms": _pct(com_fala, 0.5), "fala_p90_ms": _pct(com_fala, 0.9),
            "medias": medias, "gargalo": gargalo,
            "primeiro_token_mediana_ms": _pct(tokens, 0.5),
            "ferramentas": ferr, "cache_acertos": hits,
            "ultimos": ped[-12:]}


def _s(ms) -> str:
    if ms is None:
        return "sem medida"
    return f"{ms / 1000:.1f} s".replace(".", ",") if ms >= 1000 else f"{int(ms)} ms"


def resumo_texto(arquivo: Path | None = None) -> str:
    r = relatorio(arquivo=arquivo)
    if not r["pedidos"] or r["fala_mediana_ms"] is None:
        return "Ainda não medi pedidos suficientes para dizer onde o tempo está indo."
    txt = (f"Do fim da sua fala até eu começar a falar, o tempo típico é {_s(r['fala_mediana_ms'])} "
           f"(em 90% dos casos até {_s(r['fala_p90_ms'])}), em {r['pedidos']} pedido(s).")
    if r["gargalo"]:
        txt += (f" O maior gargalo é: {NOMES[r['gargalo']].lower()}, em média {_s(r['medias'][r['gargalo']])}. "
                + DICAS[r["gargalo"]])
    if r["cache_acertos"]:
        txt += f" {r['cache_acertos']} de {r['ferramentas']} chamadas de ferramenta vieram do cache."
    return txt
