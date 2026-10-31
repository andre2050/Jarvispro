"""Memória semanal do NEXUS (Ultra 2026 3.2) — o que ele aprendeu sobre você e o que antecipa.

Toda semana o NEXUS resume, só com contagem (sem modelo, sem rede, sem custo), o que viu você fazer:
  • as ações que mais repetiu e em que horário costumam acontecer;
  • o dia mais movimentado;
  • os pedidos que você refez mais de uma vez (candidatos a rotina).
O resumo fica em memory/resumo_semanal.json (só no PC, até 12 semanas) e serve para:
  • "Nexus, o que você aprendeu sobre mim esta semana?";
  • ANTECIPAR: "agora é terça de manhã e você costuma abrir o Spotify — quer que eu abra?"
    (o NEXUS só SUGERE; abrir ou rodar algo continua dependendo do seu "sim").

Fontes: core/habits.py (ferramentas seguras que você usou) e core/autoavaliacao.py (seus pedidos).
Nunca levanta erro para quem chama.
"""
from __future__ import annotations

import json
import re
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from core.protecao import engolida as _engolida

ARQUIVO = Path(__file__).resolve().parent.parent / "memory" / "resumo_semanal.json"
VERSAO = 1
MAX_SEMANAS = 12
MIN_REPETICOES = 3          # uma ação só entra no resumo se foi vista pelo menos assim
MIN_DIAS_ANTECIPAR = 3      # e só vira sugestão se aconteceu em pelo menos 3 dias diferentes
DIAS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")

_trava = threading.RLock()


# ── nomes legíveis ──────────────────────────────────────────────────────────
_NOMES = {
    "open_app": "abrir", "music_control": "música", "weather_report": "ver o clima",
    "morning_briefing": "o resumo da manhã", "quick_notes": "anotar", "web_search": "pesquisar na internet",
    "timer_action": "timer", "unit_converter": "converter", "everyday_tools": "ferramentas do dia a dia",
    "video_player": "vídeo", "youtube_video": "YouTube", "price_alert": "alerta de preço",
    "computer_settings": "ajuste do computador", "system_update": "atualização", "daily_planner": "planejar o dia",
}


def nome_legivel(sig: str) -> str:
    """'music_control:play' → 'música (play)'; 'open_app:spotify' → 'abrir spotify'."""
    tool, _, qual = str(sig).partition(":")
    base = _NOMES.get(tool, tool.replace("_", " "))
    if not qual:
        return base
    return f"{base} {qual}" if tool == "open_app" else f"{base} ({qual})"


def periodo(hora: int) -> str:
    if 5 <= hora < 12:
        return "de manhã"
    if 12 <= hora < 18:
        return "à tarde"
    if 18 <= hora < 23:
        return "à noite"
    return "de madrugada"


def semana_id(quando: float | None = None) -> str:
    d = datetime.fromtimestamp(quando or time.time())
    ano, sem, _ = d.isocalendar()
    return f"{ano}-S{sem:02d}"


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\wÀ-ÿ ]+", " ", str(t or "").lower())).strip()


# ── fontes ──────────────────────────────────────────────────────────────────
def _eventos() -> list[dict]:
    try:
        from core import habits
        return [e for e in habits._load() if isinstance(e, dict) and e.get("sig") and e.get("t")]
    except Exception:
        return []


def _pedidos() -> list[dict]:
    try:
        from core import autoavaliacao as AV
        return [e for e in AV._carregar()["eventos"] if e.get("texto") and e.get("t")]
    except Exception:
        return []


# ── o resumo ────────────────────────────────────────────────────────────────
def resumir(agora: float | None = None, eventos: list[dict] | None = None,
            pedidos: list[dict] | None = None) -> dict:
    """O resumo dos últimos 7 dias (puro e testável: aceita os dados de fora)."""
    agora = agora or time.time()
    ini = agora - 7 * 86400
    ev = [e for e in (eventos if eventos is not None else _eventos()) if ini <= e["t"] <= agora]
    pe = [p for p in (pedidos if pedidos is not None else _pedidos()) if ini <= p["t"] <= agora]

    por_acao: dict[str, list[float]] = defaultdict(list)
    por_dia: Counter = Counter()
    for e in ev:
        por_acao[e["sig"]].append(e["t"])
        por_dia[datetime.fromtimestamp(e["t"]).weekday()] += 1

    habitos = []
    for sig, ts in sorted(por_acao.items(), key=lambda kv: -len(kv[1])):
        if len(ts) < MIN_REPETICOES:
            continue
        horas = Counter(datetime.fromtimestamp(t).hour for t in ts)
        hora, _ = horas.most_common(1)[0]
        habitos.append({"sig": sig, "nome": nome_legivel(sig), "vezes": len(ts), "hora_tipica": hora})
    habitos = habitos[:5]

    repetidos = Counter(_norm(p["texto"]) for p in pe if p["texto"])
    originais = {_norm(p["texto"]): p["texto"] for p in pe}
    pedidos_rep = [{"texto": originais[k][:80], "vezes": n}
                   for k, n in repetidos.most_common(3) if n >= 2 and k]

    dia_top = por_dia.most_common(1)[0][0] if por_dia else None
    r = {"semana": semana_id(agora), "gerado_em": int(agora), "acoes": len(ev), "pedidos": len(pe),
         "habitos": habitos, "pedidos_repetidos": pedidos_rep,
         "dia_mais_ativo": DIAS[dia_top] if dia_top is not None else None}
    r["texto"] = _frase(r)
    return r


def _frase(r: dict) -> str:
    if not r["acoes"] and not r["pedidos"]:
        return "Esta semana eu ainda não vi o suficiente para aprender algo novo sobre você."
    partes = []
    if r["habitos"]:
        itens = [f"{h['nome']} ({h['vezes']} vezes, quase sempre por volta das {h['hora_tipica']}h)"
                 for h in r["habitos"][:3]]
        partes.append("Nesta semana você repetiu: " + "; ".join(itens) + ".")
    if r["dia_mais_ativo"]:
        partes.append(f"O dia em que mais usou o computador comigo foi {r['dia_mais_ativo']}.")
    if r["pedidos_repetidos"]:
        itens = [f"“{p['texto']}” ({p['vezes']}x)" for p in r["pedidos_repetidos"][:2]]
        partes.append("Você repetiu estes pedidos: " + "; ".join(itens) + ". Posso transformar em rotina.")
    if not partes:
        partes.append(f"Vi {r['acoes']} ação(ões) e {r['pedidos']} pedido(s), mas nada se repetiu o bastante para eu tirar um padrão.")
    return " ".join(partes)


# ── guardar ─────────────────────────────────────────────────────────────────
def _carregar(arquivo: Path | None = None) -> dict:
    try:
        d = json.loads((arquivo or ARQUIVO).read_text(encoding="utf-8"))
        if d.get("versao") == VERSAO and isinstance(d.get("semanas"), list):
            return d
    except Exception:
        _engolida("core/memoria_semanal.py:153")
    return {"versao": VERSAO, "semanas": []}


def _salvar(d: dict, arquivo: Path | None = None) -> None:
    arq = arquivo or ARQUIVO
    try:
        arq.parent.mkdir(parents=True, exist_ok=True)
        d["semanas"] = d["semanas"][-MAX_SEMANAS:]
        tmp = arq.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        tmp.replace(arq)
    except Exception:
        _engolida("core/memoria_semanal.py:166")


def garantir_semana(agora: float | None = None, arquivo: Path | None = None,
                    eventos: list[dict] | None = None, pedidos: list[dict] | None = None) -> dict | None:
    """Gera e guarda o resumo se esta semana ainda não tem um. Devolve o resumo NOVO (ou None se já existia)."""
    try:
        with _trava:
            d = _carregar(arquivo)
            sid = semana_id(agora)
            if any(s.get("semana") == sid for s in d["semanas"]):
                return None
            r = resumir(agora, eventos, pedidos)
            d["semanas"].append(r)
            _salvar(d, arquivo)
            return r
    except Exception:
        return None


def ultimo(arquivo: Path | None = None) -> dict | None:
    s = _carregar(arquivo)["semanas"]
    return s[-1] if s else None


def texto_da_semana(arquivo: Path | None = None) -> str:
    """O que ele aprendeu: o resumo guardado (ou um novo, se ainda não há nenhum)."""
    r = ultimo(arquivo) or resumir()
    return r["texto"]


def esquecer(arquivo: Path | None = None) -> None:
    with _trava:
        _salvar({"versao": VERSAO, "semanas": []}, arquivo)


# ── antecipar ───────────────────────────────────────────────────────────────
def antecipar(agora: float | None = None, eventos: list[dict] | None = None, janela_h: int = 1,
              dias_hist: int = 28) -> list[dict]:
    """Ações que costumam acontecer por volta de AGORA no mesmo dia da semana, vistas em pelo menos
    MIN_DIAS_ANTECIPAR dias diferentes das últimas semanas. [{'sig','nome','dias','hora'}], mais firme primeiro."""
    agora = agora or time.time()
    atual = datetime.fromtimestamp(agora)
    corte = agora - dias_hist * 86400
    dias: dict[str, set] = defaultdict(set)
    for e in (eventos if eventos is not None else _eventos()):
        t = e["t"]
        if not (corte <= t < agora - 3600):            # a última hora não conta: é o que ele acabou de fazer
            continue
        d = datetime.fromtimestamp(t)
        if d.weekday() != atual.weekday():
            continue
        if min((d.hour - atual.hour) % 24, (atual.hour - d.hour) % 24) > janela_h:
            continue
        dias[e["sig"]].add(d.date().isoformat())
    out = [{"sig": s, "nome": nome_legivel(s), "dias": len(ds), "hora": atual.hour}
           for s, ds in dias.items() if len(ds) >= MIN_DIAS_ANTECIPAR]
    return sorted(out, key=lambda x: -x["dias"])


def sugestao_texto(agora: float | None = None, eventos: list[dict] | None = None) -> str:
    """Uma frase de sugestão para AGORA, ou '' se não há padrão firme."""
    cand = antecipar(agora, eventos)
    if not cand:
        return ""
    quando = datetime.fromtimestamp(agora or time.time())
    dia = DIAS[quando.weekday()]
    c = cand[0]
    return (f"Hoje é {dia} {periodo(quando.hour)} e, em {c['dias']} {dia}s por volta dessa hora, "
            f"você fez: {c['nome']}. Quer que eu faça agora?")
