"""I.S.A. preditiva (NEXUS Ultra 2026 3.4): antecipar problemas e ajustar o ritmo do NEXUS sozinha.

PREVER — a cada 5 minutos o núcleo anota algumas medidas (memory/isa_series.json, só números):
  disco livre, memória do PC, memória e threads do próprio NEXUS, CPU, tempo de resposta e erros das
  funções. Com a tendência (reta dos mínimos quadrados) ela avisa ANTES de virar problema:
    • "o disco enche em ~6 dias nesse ritmo"
    • "o NEXUS está crescendo 45 MB por hora — reiniciar à noite resolve" (vazamento de memória)
    • "a memória do PC chega a 95% em ~40 min"
    • "as respostas estão ficando mais lentas" / "a função X falhou 4 vezes na última hora"
  e diz o que fazer (sugestões concretas, que você pode pedir para ela aplicar).

AJUSTAR — o modo de desempenho muda conforme o que você está fazendo (preferência ``desempenho_auto``):
    economia     PC muito ocupado (jogo, render, CPU > 80%) ou bateria baixa: o NEXUS baixa a PRÓPRIA
                 prioridade, olha as coisas em segundo plano 3× menos e guarda clima/notícias por mais tempo
    equilibrado  o normal
    desempenho   você está conversando muito com ele: prioridade normal e laços no ritmo cheio
  Só o próprio processo do NEXUS é ajustado — nunca outros programas.
"""
from __future__ import annotations

import threading
import time

from core import armazem
from core.protecao import engolida as _engolida

ARQ = armazem.PASTA_MEMORIA / "isa_series.json"
AMOSTRA_S = 300
MAX_PONTOS = 2016                      # 7 dias de 5 em 5 minutos
MODOS = ("economia", "equilibrado", "desempenho")
_FATOR = {"economia": 3.0, "equilibrado": 1.0, "desempenho": 1.0}
_ESPERA_PREVISAO_S = 6 * 3600

_trava = threading.RLock()
_estado = {"modo": "equilibrado", "manual": "", "desde": time.time(), "ultima_amostra": 0.0,
           "avisadas": {}, "uso_recente": []}


# ── medir ────────────────────────────────────────────────────────────────────
def medir() -> dict:
    """Uma medida agora. Campos que não der para ler ficam de fora."""
    m: dict = {"t": time.time()}
    try:
        import psutil
        m["cpu"] = psutil.cpu_percent(interval=None)
        m["mem_pct"] = psutil.virtual_memory().percent
        try:
            m["disco_livre_gb"] = round(psutil.disk_usage(str(armazem.PASTA_MEMORIA.anchor or "/")).free / 1e9, 2)
        except Exception:
            _engolida("core/isa_preditiva.py:49")
        eu = psutil.Process()
        m["nexus_mb"] = round(eu.memory_info().rss / 1e6, 1)
        m["threads"] = eu.num_threads()
        bat = getattr(psutil, "sensors_battery", lambda: None)()
        if bat is not None and not bat.power_plugged:
            m["bateria"] = bat.percent
    except Exception:
        _engolida("core/isa_preditiva.py:57")
    try:
        from core import latencia
        r = latencia.relatorio(10)
        if r.get("fala_mediana_ms"):
            m["resposta_ms"] = r["fala_mediana_ms"]
    except Exception:
        _engolida("core/isa_preditiva.py:64")
    try:
        from core import isa
        m["erros"] = isa.estatisticas()["acoes_erro"]
    except Exception:
        _engolida("core/isa_preditiva.py:69")
    return m


def serie() -> list[dict]:
    return [p for p in armazem.carregar(ARQ, []) if isinstance(p, dict) and p.get("t")]


def anotar(m: dict) -> None:
    pontos = serie() + [m]
    armazem.salvar(ARQ, pontos[-MAX_PONTOS:])


# ── tendência ────────────────────────────────────────────────────────────────
def tendencia(pontos: list[dict], campo: str, janela_s: float) -> tuple[float, float] | None:
    """(inclinação por hora, último valor) nos pontos da janela; None com menos de 4 pontos."""
    if not pontos:
        return None
    fim = pontos[-1]["t"]
    xs, ys = [], []
    for p in pontos:
        if p["t"] >= fim - janela_s and p.get(campo) is not None:
            xs.append((p["t"] - fim) / 3600.0)
            ys.append(float(p[campo]))
    if len(xs) < 4 or max(xs) - min(xs) < 0.25:
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den, ys[-1]


def _falhas_por_funcao(janela_s: float = 3600) -> dict[str, int]:
    try:
        from core import isa
        limite = time.time() - janela_s
        cont: dict[str, int] = {}
        for e in isa.eventos(300, {"erro"}):
            if e["t"] >= limite:
                nome = e["titulo"].removesuffix(" falhou")
                cont[nome] = cont.get(nome, 0) + 1
        return cont
    except Exception:
        return {}


def prever(pontos: list[dict] | None = None, falhas: dict[str, int] | None = None) -> list[dict]:
    """[{chave, texto, sugestao, gravidade}] — o que deve dar problema, antes de dar."""
    pontos = serie() if pontos is None else pontos
    falhas = _falhas_por_funcao() if falhas is None else falhas
    out: list[dict] = []

    t = tendencia(pontos, "disco_livre_gb", 3 * 86400)
    if t and t[0] < -0.01 and t[1] > 0:
        horas = t[1] / -t[0]
        if horas < 14 * 24 or t[1] < 5:
            dias = horas / 24
            out.append({"chave": "disco", "gravidade": 3 if dias < 2 else 2,
                        "texto": f"O disco enche em ~{dias:.0f} dia(s) nesse ritmo ({t[1]:.1f} GB livres).",
                        "sugestao": "Limpar temporários e a lixeira (manutenção do PC) e ver o que está crescendo."})
    elif pontos and (pontos[-1].get("disco_livre_gb") or 99) < 3:
        out.append({"chave": "disco", "gravidade": 3, "texto": f"Só {pontos[-1]['disco_livre_gb']} GB livres no disco.",
                    "sugestao": "Limpar temporários e a lixeira (manutenção do PC)."})

    t = tendencia(pontos, "nexus_mb", 6 * 3600)
    if t and t[0] > 25 and t[1] > 500:
        out.append({"chave": "vazamento", "gravidade": 2,
                    "texto": f"O NEXUS está crescendo {t[0]:.0f} MB por hora ({t[1]:.0f} MB agora).",
                    "sugestao": "Liberar memória agora (otimizar) e reiniciar o NEXUS quando der."})

    t = tendencia(pontos, "mem_pct", 3600)
    if t and t[0] > 2 and t[1] < 95:
        minutos = (95 - t[1]) / t[0] * 60
        if minutos < 90:
            out.append({"chave": "memoria", "gravidade": 2,
                        "texto": f"A memória do PC chega a 95% em ~{minutos:.0f} min ({t[1]:.0f}% agora).",
                        "sugestao": "Fechar programas que não está usando; posso mostrar os mais pesados."})
    elif pontos and (pontos[-1].get("mem_pct") or 0) >= 92:
        out.append({"chave": "memoria", "gravidade": 2, "texto": f"Memória do PC em {pontos[-1]['mem_pct']:.0f}%.",
                    "sugestao": "Fechar programas que não está usando; posso mostrar os mais pesados."})

    t = tendencia(pontos, "resposta_ms", 6 * 3600)
    if t and t[0] > 150 and t[1] > 2500:
        out.append({"chave": "lentidao", "gravidade": 1,
                    "texto": f"As respostas estão ficando mais lentas ({t[1] / 1000:.1f} s, subindo).",
                    "sugestao": "Ver o painel ⏱ Latência; no motor próprio, um modelo menor ajuda."})

    for nome, n in sorted(falhas.items(), key=lambda kv: -kv[1]):
        if n >= 3:
            out.append({"chave": f"funcao:{nome}", "gravidade": 2,
                        "texto": f"A função “{nome}” falhou {n} vezes na última hora.",
                        "sugestao": "A auto-regeneração pausa a função por alguns minutos e tenta o remédio conhecido."})
    return sorted(out, key=lambda p: -p["gravidade"])


# ── desempenho ───────────────────────────────────────────────────────────────
def marcar_uso() -> None:
    """Chamado a cada pedido do usuário: muito uso recente puxa o modo desempenho."""
    with _trava:
        agora = time.time()
        _estado["uso_recente"] = [t for t in _estado["uso_recente"] if agora - t < 600] + [agora]


def decidir_modo(m: dict, usos_10min: int, ocupado: bool = False) -> str:
    if (m.get("bateria") is not None and m["bateria"] <= 25) or ocupado or (m.get("cpu") or 0) >= 80:
        return "economia"
    if usos_10min >= 4:
        return "desempenho"
    return "equilibrado"


def _aplicar_prioridade(modo: str) -> None:
    try:
        import psutil
        eu = psutil.Process()
        if hasattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS"):          # Windows
            eu.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if modo == "economia" else psutil.NORMAL_PRIORITY_CLASS)
        elif modo == "economia":
            eu.nice(min(19, max(eu.nice(), 5)))                       # Unix: só dá para ficar mais gentil
    except Exception:
        _engolida("core/isa_preditiva.py:190")


def definir_modo(modo: str, motivo: str = "", manual: bool = False) -> str:
    modo = modo if modo in MODOS else "equilibrado"
    with _trava:
        anterior = _estado["modo"]
        _estado["manual"] = modo if manual else _estado["manual"]
        if modo == anterior:
            return modo
        _estado["modo"], _estado["desde"] = modo, time.time()
    _aplicar_prioridade(modo)
    try:
        from core import isa
        isa.definir("desempenho", modo)
        isa.registrar("sistema", f"Desempenho: {modo}", motivo, origem="isa")
    except Exception:
        _engolida("core/isa_preditiva.py:207")
    return modo


def automatico() -> None:
    """Volta a deixar a I.S.A. escolher o modo sozinha."""
    with _trava:
        _estado["manual"] = ""


def modo() -> str:
    with _trava:
        return _estado["modo"]


def modo_manual() -> str:
    with _trava:
        return _estado["manual"]


def fator() -> float:
    """Quanto os laços de segundo plano devem esticar o intervalo (economia = 3×)."""
    return _FATOR.get(modo(), 1.0)


def otimizar() -> list[str]:
    """O que dá para fazer AGORA, com segurança, para o NEXUS ficar mais leve."""
    feitos = []
    try:
        import gc
        n = gc.collect()
        feitos.append(f"memória do NEXUS liberada ({n} objetos)")
    except Exception:
        _engolida("core/isa_preditiva.py:240")
    try:
        from core import cache_respostas
        cache_respostas.limpar()
        feitos.append("cache de respostas limpo")
    except Exception:
        _engolida("core/isa_preditiva.py:246")
    return feitos


# ── o passo do laço ──────────────────────────────────────────────────────────
def passo(agora: float | None = None, ocupado: bool = False, auto: bool = True) -> list[str]:
    """Mede, ajusta o modo e devolve as previsões NOVAS (cada uma no máximo a cada 6 h)."""
    agora = agora or time.time()
    m = medir()
    with _trava:
        usos = len([t for t in _estado["uso_recente"] if agora - t < 600])
        anotar_agora = agora - _estado["ultima_amostra"] >= AMOSTRA_S
        if anotar_agora:
            _estado["ultima_amostra"] = agora
        manual = _estado["manual"]
    if anotar_agora:
        anotar(m)
    if auto and not manual:
        novo = decidir_modo(m, usos, ocupado)
        definir_modo(novo, f"CPU {m.get('cpu', 0):.0f}%, {usos} pedido(s) em 10 min"
                     + (", tela cheia/ocupado" if ocupado else ""))
    if not anotar_agora:
        return []
    avisos = []
    for p in prever():
        with _trava:
            if agora - _estado["avisadas"].get(p["chave"], 0) < _ESPERA_PREVISAO_S:
                continue
            _estado["avisadas"][p["chave"]] = agora
        avisos.append(f"{p['texto']} Sugestão: {p['sugestao']}")
        try:
            from core import isa
            isa.registrar("sistema", "Previsão da I.S.A.", p["texto"], origem="isa")
        except Exception:
            _engolida("core/isa_preditiva.py:280")
    return avisos
