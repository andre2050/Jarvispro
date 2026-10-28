"""Oráculo de bem-estar (NEXUS Ultra 2026 3.4): um plano de dia feito dos SEUS dados, para render sem se gastar.

O NEXUS junta o que já sabe de você — e só aqui no PC, sem mandar nada de saúde para a nuvem:

  SONO E ENERGIA   o que você conta: "dormi 6 horas", "energia 3", "acordei às 7" (memory/bemestar.json)
  HUMOR            as notas de humor do diário (1 a 5)
  HÁBITOS          água e exercício, se você acompanha esses hábitos
  AGENDA           tarefas com prazo hoje, atrasadas e de alta prioridade; lembretes de hoje
  TELA             quanto tempo o PC ficou ligado hoje e há quanto tempo você está sem pausa (medidas do PC)
  AMBIENTE         o clima de hoje (calor pede mais água; chuva tira a caminhada do plano)

e devolve:
  • a energia prevista do dia (1 a 5) e por quê;
  • blocos de horário: foco profundo no seu pico, tarefas leves na queda pós-almoço, pausas, movimento;
  • PREVENÇÃO: sinais que se repetem há dias (pouco sono, humor caindo, sobrecarga de tarefas, muita tela,
    vários dias sem se mexer) — com uma sugestão prática para cada.

Ao longo do dia (se ``bemestar_vigia`` estiver ligado) avisa: pausa depois de ~100 min seguidos de PC,
água atrasada e hora de dormir. Cada aviso tem intervalo mínimo para não virar chatice.

NÃO é conselho médico e não diagnostica nada. Um sintoma que você contar só gera a sugestão de procurar um
profissional de saúde se continuar. As regras são simples e estão todas aqui, para você conferir.
"""
from __future__ import annotations

import csv
import time
from datetime import date, datetime, timedelta

from core import armazem

ARQ = armazem.PASTA_MEMORIA / "bemestar.json"
AVISO_SAUDE = ("Isto é um plano de rotina baseado nos dados que você deu, não conselho médico. "
               "Se algo te preocupa ou continua, fale com um profissional de saúde.")
META_SONO_H = 7.5
META_AGUA = 8
PAUSA_APOS_MIN = 100
_ESPERA_AVISO_S = {"pausa": 3600, "agua": 2 * 3600, "dormir": 6 * 3600}


def _hoje() -> date:
    return datetime.now().date()


def _ler() -> dict:
    d = armazem.carregar(ARQ, {"registros": {}, "avisos": {}})
    d.setdefault("registros", {})
    d.setdefault("avisos", {})
    return d


def _num(v, minimo: float, maximo: float) -> float | None:
    try:
        n = float(str(v).replace(",", ".").replace("h", "").strip())
    except (TypeError, ValueError):
        return None
    return n if minimo <= n <= maximo else None


def _hora(v) -> str:
    if v in (None, ""):
        return ""
    from core.rotinas_conversa import parse_hora
    return parse_hora(v) or ""


# ── o que você conta ─────────────────────────────────────────────────────────
def registrar(dia: date | None = None, **campos) -> str:
    """sono_h, energia (1-5), humor (1-5), agua (copos), exercicio_min, acordou ('7h'), dormiu ('23h'),
    sintomas (texto). Só grava o que veio e é válido."""
    dia = dia or _hoje()
    d = _ler()
    reg = d["registros"].setdefault(dia.isoformat(), {})
    gravados = []
    limites = {"sono_h": (0, 16), "energia": (1, 5), "humor": (1, 5), "agua": (0, 30), "exercicio_min": (0, 600)}
    for chave, (a, b) in limites.items():
        if campos.get(chave) not in (None, ""):
            n = _num(campos[chave], a, b)
            if n is not None:
                reg[chave] = n
                gravados.append(chave)
    for chave in ("acordou", "dormiu"):
        h = _hora(campos.get(chave))
        if h:
            reg[chave] = h
            gravados.append(chave)
    if str(campos.get("sintomas") or "").strip():
        reg["sintomas"] = str(campos["sintomas"]).strip()[:200]
        gravados.append("sintomas")
    if not gravados:
        return "Não entendi o que anotar. Diga, por exemplo: dormi 7 horas, energia 4, bebi 3 copos."
    armazem.salvar(ARQ, d)
    nomes = {"sono_h": "sono", "exercicio_min": "exercício", "agua": "água"}
    return "Anotado: " + ", ".join(nomes.get(g, g) for g in gravados) + "."


# ── juntar os dados ──────────────────────────────────────────────────────────
def _humor_diario(dias: int, hoje: date) -> dict[str, float]:
    try:
        from actions.diario import _ler as ler_diario
        notas: dict[str, list[float]] = {}
        for e in ler_diario():
            if e.get("humor"):
                dia = str(e["quando"])[:10]
                if (hoje - date.fromisoformat(dia)).days < dias:
                    notas.setdefault(dia, []).append(float(e["humor"]))
        return {k: sum(v) / len(v) for k, v in notas.items()}
    except Exception:
        return {}


def _habito(palavras: tuple[str, ...], hoje: date) -> dict | None:
    try:
        from actions.rastreador_habitos import _ler as ler_habitos
        for h in ler_habitos()["habitos"]:
            if any(p in armazem.norm(h["nome"]) for p in palavras):
                regs = h.get("registros") or {}
                ult = [regs.get((hoje - timedelta(days=i)).isoformat(), 0) for i in range(7)]
                return {"nome": h["nome"], "meta": float(h.get("meta") or 1), "hoje": float(ult[0]),
                        "dias_sem": next((i for i, v in enumerate(ult) if v), 7)}
    except Exception:
        pass
    return None


def _tarefas(hoje: date) -> dict:
    try:
        from actions.tarefas import _carregar
        abertas = [t for t in _carregar() if not t.get("feita")]
    except Exception:
        abertas = []
    hoje_s = hoje.isoformat()
    return {"hoje": [t["titulo"] for t in abertas if str(t.get("prazo") or "") == hoje_s],
            "atrasadas": [t["titulo"] for t in abertas if t.get("prazo") and str(t["prazo"]) < hoje_s],
            "alta": [t["titulo"] for t in abertas if t.get("prio") == "alta"], "abertas": len(abertas)}


def _lembretes(hoje: date) -> list[tuple[str, str]]:
    try:
        from actions.reminder import listar
        return [(d["quando"][11:16], d["mensagem"]) for d in listar()
                if d["quando"][:10] == hoje.isoformat() and d["pendente"]]
    except Exception:
        return []


def uso_do_pc(agora: float | None = None) -> dict:
    """Minutos de PC ligado hoje e minutos seguidos sem pausa (uma pausa = 10 min sem medida),
    pelas medidas de minuto em minuto do detector de anomalias."""
    agora = agora or time.time()
    inicio = datetime.fromtimestamp(agora).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    try:
        from core.anomalia import ARQ_CSV
        with ARQ_CSV.open(encoding="utf-8") as f:
            ts = [int(r[0]) for r in csv.reader(f) if r and r[0].isdigit() and int(r[0]) >= inicio]
    except Exception:
        ts = []
    if not ts:
        return {"hoje_min": 0, "seguidos_min": 0}
    seguidos_desde = ts[0]
    for a, b in zip(ts, ts[1:]):
        if b - a > 600:
            seguidos_desde = b
    ativo = (agora - ts[-1]) <= 300
    return {"hoje_min": len(ts), "seguidos_min": int((ts[-1] - seguidos_desde) / 60) if ativo else 0}


def _clima() -> dict:
    try:
        from actions.weather_report import _buscar, _cidade_padrao
        cidade = _cidade_padrao()
        if not cidade:
            return {}
        _loc, dados = _buscar(cidade, dias=1)
        diario = dados.get("daily") or {}
        return {"max": (diario.get("temperature_2m_max") or [None])[0],
                "chuva_pct": (diario.get("precipitation_probability_max") or [None])[0]}
    except Exception:
        return {}


def coletar(hoje: date | None = None, com_clima: bool = True, agora: float | None = None) -> dict:
    hoje = hoje or _hoje()
    regs = _ler()["registros"]
    semana = {k: v for k, v in regs.items() if 0 <= (hoje - date.fromisoformat(k)).days < 7}
    return {"hoje": hoje.isoformat(), "registros": semana, "humor_diario": _humor_diario(7, hoje),
            "agua": _habito(("agua",), hoje), "exercicio": _habito(("exerc", "treino", "academia", "caminh", "corr"), hoje),
            "tarefas": _tarefas(hoje), "lembretes": _lembretes(hoje), "pc": uso_do_pc(agora),
            "clima": _clima() if com_clima else {}}


# ── o plano ──────────────────────────────────────────────────────────────────
def _dias(ctx: dict, campo: str, n: int) -> list[float]:
    hoje = date.fromisoformat(ctx["hoje"])
    out = []
    for i in range(n):
        v = ctx["registros"].get((hoje - timedelta(days=i)).isoformat(), {}).get(campo)
        if v is not None:
            out.append(float(v))
    return out


def _hm(minutos: int) -> str:
    minutos = int(minutos) % (24 * 60)
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def energia_prevista(ctx: dict) -> tuple[int, list[str]]:
    motivos, e = [], 3.0
    sono = _dias(ctx, "sono_h", 1)
    if sono:
        if sono[0] >= 7:
            e += 1; motivos.append(f"dormiu bem ({sono[0]:g} h)")
        elif sono[0] < 6:
            e -= 1; motivos.append(f"dormiu pouco ({sono[0]:g} h)")
        else:
            motivos.append(f"sono razoável ({sono[0]:g} h)")
    dito = _dias(ctx, "energia", 1)
    if dito:
        e = (e + dito[0]) / 2; motivos.append(f"você disse energia {dito[0]:g}")
    humor = list(ctx["humor_diario"].values()) + _dias(ctx, "humor", 3)
    if humor and sum(humor) / len(humor) <= 2:
        e -= 0.5; motivos.append("humor baixo nos últimos dias")
    ex = ctx.get("exercicio")
    if ex and ex["dias_sem"] <= 1:
        e += 0.5; motivos.append("se exercitou ontem ou hoje")
    if (ctx["pc"].get("hoje_min") or 0) > 9 * 60:
        e -= 0.5; motivos.append("muitas horas de tela hoje")
    return int(max(1, min(5, round(e)))), motivos or ["poucos dados ainda — conte como dormiu para afinar"]


def alertas_preventivos(ctx: dict) -> list[str]:
    out = []
    sono = _dias(ctx, "sono_h", 3)
    if len(sono) >= 3 and all(s < 6 for s in sono):
        out.append("Três noites seguidas com menos de 6 h de sono: hoje vale deitar mais cedo e evitar café depois das 14h.")
    elif len(sono) >= 2 and sum(sono) / len(sono) < 6.5:
        out.append(f"Média de sono de {sum(sono) / len(sono):.1f} h: tente recuperar com uma noite mais longa.")
    humores = [v for _, v in sorted(ctx["humor_diario"].items())] or list(reversed(_dias(ctx, "humor", 5)))
    if len(humores) >= 3 and (sum(humores[-3:]) / 3 <= 2 or humores[0] - humores[-1] >= 1.5):
        out.append("Seu humor vem caindo há alguns dias: reserve um tempo para algo que te faz bem e, se continuar, "
                   "converse com alguém de confiança ou um profissional.")
    t = ctx["tarefas"]
    if len(t["atrasadas"]) >= 5 or t["abertas"] >= 25:
        out.append(f"Sobrecarga: {len(t['atrasadas'])} tarefa(s) atrasada(s) e {t['abertas']} aberta(s). Escolha 3 para "
                   "hoje e renegocie ou adie o resto.")
    if (ctx["pc"].get("hoje_min") or 0) >= 10 * 60:
        out.append("Mais de 10 h de PC hoje: descanse os olhos (regra 20-20-20) e desligue as telas 1 h antes de dormir.")
    ex = ctx.get("exercicio")
    if ex and ex["dias_sem"] >= 4:
        out.append(f"{ex['dias_sem']} dias sem {ex['nome'].lower()}: até 15 minutos de caminhada já contam.")
    sintomas = ctx["registros"].get(ctx["hoje"], {}).get("sintomas")
    if sintomas:
        out.append(f"Você mencionou: {sintomas}. Pegue leve hoje e, se continuar ou piorar, procure um profissional de saúde.")
    return out


def plano(ctx: dict, agora: datetime | None = None) -> dict:
    agora = agora or datetime.now()
    energia, motivos = energia_prevista(ctx)
    acordou = ctx["registros"].get(ctx["hoje"], {}).get("acordou") or "07:00"
    h, m = (int(x) for x in acordou.split(":"))
    base = h * 60 + m                                          # tudo se ajusta à hora em que você acordou
    pico_ini, pico_fim = base + 120, base + 120 + (150 if energia >= 3 else 90)
    queda = base + 6 * 60 + 30
    t = ctx["tarefas"]
    foco = (t["alta"] + t["hoje"] + t["atrasadas"])[:3]
    blocos = [(_hm(base), "Acordar: água, luz natural e nada de tela nos primeiros 20 min")]
    blocos.append((_hm(pico_ini), "Foco profundo" + (f": {', '.join(foco)}" if foco else " — a tarefa mais importante do dia")
                   + (" (blocos de 50 min, energia baixa hoje)" if energia <= 2 else " (blocos de 90 min)")))
    blocos.append((_hm(pico_fim), "Pausa de 15 min: levantar, alongar, água"))
    blocos.append((_hm(base + 5 * 60 + 30), "Almoço sem tela"))
    blocos.append((_hm(queda), "Queda natural de energia: tarefas leves, e-mails e reuniões"))
    clima = ctx.get("clima") or {}
    chuva = (clima.get("chuva_pct") or 0) >= 60
    blocos.append((_hm(queda + 120), "Movimento: " + ("alongamento ou exercício em casa (previsão de chuva)" if chuva
                                                       else "caminhada de 15-20 min, de preferência ao ar livre")))
    blocos.append((_hm(queda + 150), "Segundo período bom: revisar, planejar amanhã, terminar o que ficou"))
    dormir = (base + 24 * 60 - 60 * META_SONO_H - 15) % (24 * 60)
    blocos.append((_hm(int(dormir) - 60), "Desacelerar: telas mais fracas, nada de trabalho"))
    blocos.append((_hm(int(dormir)), f"Hora de dormir para ter {META_SONO_H:g} h de sono"))
    for hora, msg in ctx.get("lembretes") or []:
        blocos.append((hora, f"Lembrete: {msg}"))
    blocos.sort(key=lambda b: b[0])

    agua_meta = META_AGUA + (2 if (clima.get("max") or 0) >= 30 else 0)
    dicas = [f"Água: {agua_meta} copos hoje" + (" (dia quente)" if agua_meta > META_AGUA else "") + "."]
    if energia <= 2:
        dicas.append("Energia baixa: corte o dia para o essencial e durma mais cedo.")
    if energia >= 4:
        dicas.append("Energia boa: aproveite o pico da manhã para a tarefa mais difícil.")
    return {"energia": energia, "motivos": motivos, "blocos": blocos, "alertas": alertas_preventivos(ctx),
            "dicas": dicas, "aviso": AVISO_SAUDE, "gerado": agora.isoformat(timespec="minutes")}


def plano_texto(p: dict) -> str:
    linhas = [f"Energia prevista: {p['energia']}/5 — " + "; ".join(p["motivos"]) + ".", "", "PLANO"]
    linhas += [f"{h}  {o}" for h, o in p["blocos"]]
    if p["alertas"]:
        linhas += ["", "PREVENÇÃO"] + [f"• {a}" for a in p["alertas"]]
    linhas += ["", "DICAS"] + [f"• {d}" for d in p["dicas"]] + ["", p["aviso"]]
    return "\n".join(linhas)


# ── ao longo do dia ──────────────────────────────────────────────────────────
def passo_vigia(agora: float | None = None, ctx: dict | None = None) -> list[str]:
    """Avisos de agora (pausa, água, dormir), cada um respeitando o seu intervalo mínimo."""
    agora = agora or time.time()
    dt = datetime.fromtimestamp(agora)
    ctx = ctx or coletar(dt.date(), com_clima=False, agora=agora)
    d = _ler()
    ult = d["avisos"]
    avisos: list[tuple[str, str]] = []
    if ctx["pc"]["seguidos_min"] >= PAUSA_APOS_MIN:
        avisos.append(("pausa", f"Você está há {ctx['pc']['seguidos_min']} minutos seguidos no PC: que tal 5 minutos "
                                "de pausa, levantar e beber água?"))
    agua = ctx.get("agua")
    if agua and 10 <= dt.hour <= 20:
        esperado = agua["meta"] * (dt.hour - 8) / 12
        if agua["hoje"] + 2 <= esperado:
            avisos.append(("agua", f"Água: {agua['hoje']:g} de {agua['meta']:g} até agora. Um copo agora ajuda."))
    if (dt.hour == 23 and dt.minute >= 30) or dt.hour < 2:
        if ctx["pc"]["seguidos_min"] > 0:
            avisos.append(("dormir", "Já passou das 23h30: se amanhã é dia cheio, essa é uma boa hora para encerrar."))
    saida = []
    for tipo, msg in avisos:
        if agora - float(ult.get(tipo) or 0) >= _ESPERA_AVISO_S[tipo]:
            ult[tipo] = agora
            saida.append(msg)
    if saida:
        armazem.salvar(ARQ, d)
    return saida
