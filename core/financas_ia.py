"""Finanças com IA — NEXUS Ultra 2026 2.3.

  1) CATEGORIA AUTOMÁTICA: "gastei 42 no ifood" → Alimentação. Compara a descrição com o que você já
     lançou (e com um vocabulário-base) usando os embeddings de sentido (core/embeddings.py) e vota
     pelos vizinhos mais parecidos. Só sugere quando a confiança passa de um limiar; senão pergunta.
  2) PREVISÃO DO MÊS: quanto você deve fechar o mês gastando, somando (a) o que já gastou, (b) contas fixas
     que costumam cair e ainda não caíram e (c) o ritmo diário variável, ponderado pelo dia da semana.
     É estatística honesta (não uma rede neural): com poucas dezenas de lançamentos por mês uma rede
     erraria mais. O `backtest` mostra o erro que esse método teria dado nos seus meses anteriores.

Só lê os lançamentos de config/finance_entries.json; não grava nada e não é conselho financeiro.
"""
from __future__ import annotations

import calendar
import re
import unicodedata
from datetime import datetime

import numpy as np

# vocabulário-base: categoria → termos típicos (ajuda quando você ainda tem poucos lançamentos)
SEMENTES = {
    "Mercado": ["supermercado", "mercado", "feira", "hortifruti", "atacadao", "padaria", "acougue", "compras do mes",
                "carrefour", "assai", "extra"],
    "Alimentação": ["restaurante", "lanche", "pizza", "ifood", "hamburguer", "almoco", "jantar", "cafe", "sorvete",
                    "delivery", "marmita", "churrasco", "bar", "rappi"],
    "Transporte": ["uber", "99", "taxi", "onibus", "metro", "gasolina", "combustivel", "estacionamento", "pedagio",
                   "passagem", "bilhete unico", "mecanico", "oficina"],
    "Moradia": ["aluguel", "condominio", "iptu", "luz", "energia", "agua", "gas", "internet", "reforma", "conserto casa"],
    "Saúde": ["farmacia", "remedio", "medico", "consulta", "exame", "dentista", "plano de saude", "hospital", "academia"],
    "Lazer": ["cinema", "show", "ingresso", "viagem", "hotel", "parque", "jogo", "festa", "balada", "passeio"],
    "Assinaturas": ["netflix", "spotify", "disney", "amazon prime", "youtube premium", "assinatura", "mensalidade app",
                    "hbo", "globoplay", "icloud"],
    "Educação": ["curso", "faculdade", "escola", "livro", "material escolar", "mensalidade", "apostila", "udemy"],
    "Compras": ["roupa", "sapato", "tenis", "shopping", "loja", "eletronico", "celular", "presente", "amazon", "shein"],
    "Contas": ["conta de telefone", "celular plano", "seguro", "taxa", "imposto", "multa", "boleto", "banco", "tarifa"],
}
LIMIAR_CONFIANCA = 0.45
SIM_MINIMA = 0.30
_cache: dict = {}


def _norm(t) -> str:
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t).strip()


def _embeds() -> list:
    """Motores que votam juntos: o hash (palavra exata) sempre; o MiniLM (sentido) se instalado.

    2.4.1 — o MiniLM sozinho acha tudo parecido com tudo (≈0,4 entre termos sem relação, contra ≈0,0
    no hash) e mal conhece marcas curtas: "corrida de uber" ficava mais perto de "boleto" que de "uber".
    A média dos dois acertou 57/57 gastos de teste, contra 55 só com o hash e 36 só com o MiniLM.
    O hash é um só deste módulo: o `ajustar` abaixo não pode mexer no IDF da busca semântica.
    """
    from core import embeddings
    if "hash" not in _cache:
        _cache["hash"] = embeddings.EmbedderHash()
    motores = [_cache["hash"]]
    auto = embeddings.get_embedder("auto")
    if auto.nome != "hash":
        motores.append(auto)
    return motores


def _nome_do_usuario(cat_semente: str, existentes: list[str]) -> str:
    """Se você já escreve essa categoria do seu jeito ("Alimentacao"), usa o seu."""
    chave = _norm(cat_semente)
    for c in existentes:
        if _norm(c) == chave or chave in _norm(c) or _norm(c) in chave:
            return c
    return cat_semente


def _base(lancs: list[dict]):
    """(textos, categorias, pesos) — seus lançamentos de despesa valem mais que o vocabulário-base."""
    existentes = sorted({str(e.get("category") or "") for e in lancs if e.get("type") == "expense"} - {""})
    textos, cats, pesos = [], [], []
    for cat, termos in SEMENTES.items():
        nome = _nome_do_usuario(cat, existentes)
        for t in termos:
            textos.append(t); cats.append(nome); pesos.append(0.6)
    vistos = set()
    for e in lancs:
        if e.get("type") != "expense" or not str(e.get("description") or "").strip():
            continue
        cat = str(e.get("category") or "").strip()
        if not cat or _norm(cat) == "geral":
            continue
        chave = (_norm(e["description"]), _norm(cat))
        if chave in vistos:
            continue
        vistos.add(chave)
        textos.append(str(e["description"])); cats.append(cat); pesos.append(1.0)
    return textos, cats, np.array(pesos, np.float32)


def prever_categoria(descricao: str, lancs: list[dict], k: int = 7) -> tuple[str, float] | None:
    """(categoria, confiança 0–1) ou None se nada se parece o bastante."""
    if not _norm(descricao):
        return None
    textos, cats, pesos = _base(lancs)
    motores = _embeds()
    chave = (tuple(id(m) for m in motores), tuple(textos))
    if _cache.get("chave") != chave:
        for m in motores:
            try:
                m.ajustar(textos)                                # IDF só no motor hash
            except AttributeError:
                pass
        _cache.update(chave=chave, Ms=[m.embed(textos) for m in motores])
    sims = np.mean([M @ m.embed([descricao])[0] for M, m in zip(_cache["Ms"], motores)], axis=0)
    ordem = np.argsort(-sims)[:k]
    if sims[ordem[0]] < SIM_MINIMA:
        return None
    pontos: dict[str, float] = {}
    for i in ordem:
        if sims[i] <= 0.15:
            continue
        pontos[cats[i]] = pontos.get(cats[i], 0.0) + float(sims[i]) ** 3 * float(pesos[i])
    if not pontos:
        return None
    total = sum(pontos.values())
    cat, v = max(pontos.items(), key=lambda kv: kv[1])
    return cat, v / total


def sugerir(descricao: str, lancs: list[dict]) -> str | None:
    """A categoria só quando a confiança passa do limiar."""
    r = prever_categoria(descricao, lancs)
    return r[0] if r and r[1] >= LIMIAR_CONFIANCA else None


# ── previsão do mês ──────────────────────────────────────────────────────────
def _data(e: dict) -> datetime:
    from core.pt_time import de_timestamp
    return de_timestamp(float(e["timestamp"]))


def _despesas(lancs):
    return [(e, _data(e)) for e in lancs if e.get("type") == "expense" and e.get("timestamp")]


def _fixas(desp: list, ano: int, mes: int) -> list[tuple[str, float, int]]:
    """Contas que se repetem: (categoria+descrição, valor médio, dia do mês) vistas em ≥2 dos 3 meses anteriores."""
    meses = []
    a, m = ano, mes
    for _ in range(3):
        m -= 1
        if m == 0:
            a, m = a - 1, 12
        meses.append((a, m))
    grupos: dict[str, list] = {}
    for e, d in desp:
        if (d.year, d.month) in meses:
            chave = _norm(e.get("description")) or _norm(e.get("category"))
            grupos.setdefault(_norm(e.get("category")) + "|" + chave, []).append((d, float(e["amount"])))
    out = []
    for chave, itens in grupos.items():
        ms = {(d.year, d.month) for d, _ in itens}
        valores = [v for _, v in itens]
        if len(ms) >= 2 and np.std(valores) <= 0.15 * np.mean(valores) + 1e-9:   # valor parecido todo mês
            out.append((chave, float(np.mean(valores)), int(round(np.mean([d.day for d, _ in itens])))))
    return out


def prever_mes(lancs: list[dict], hoje: datetime) -> dict | None:
    """{'gasto_ate_agora', 'previsto', 'faixa': (min,max), 'fixas_a_cair', 'ritmo_diario'} ou None sem dados."""
    desp = _despesas(lancs)
    if len(desp) < 15:
        return None
    ano, mes = hoje.year, hoje.month
    dias_mes = calendar.monthrange(ano, mes)[1]
    do_mes = [(e, d) for e, d in desp if (d.year, d.month) == (ano, mes) and d <= hoje]
    gasto = sum(float(e["amount"]) for e, _ in do_mes)
    fixas = _fixas(desp, ano, mes)
    chaves_do_mes = {_norm(e.get("category")) + "|" + (_norm(e.get("description")) or _norm(e.get("category")))
                     for e, _ in do_mes}
    a_cair = [(c, v, dia) for c, v, dia in fixas if c not in chaves_do_mes and dia >= hoje.day]
    fixas_chaves = {c for c, _, _ in fixas}
    # ritmo variável: média diária dos últimos 60 dias SEM as contas fixas, ponderada pelo dia da semana
    inicio = hoje.timestamp() - 60 * 86400
    var = [(e, d) for e, d in desp if d.timestamp() >= inicio and d <= hoje and
           (_norm(e.get("category")) + "|" + (_norm(e.get("description")) or _norm(e.get("category")))) not in fixas_chaves]
    dias_obs = max(1, min(60, (hoje - min((d for _, d in desp), default=hoje)).days + 1))
    por_dia_sem = np.zeros(7)
    for e, d in var:
        por_dia_sem[d.weekday()] += float(e["amount"])
    n_sem = np.maximum(1, np.array([sum(1 for k in range(dias_obs) if
                                        datetime.fromtimestamp(hoje.timestamp() - k * 86400).weekday() == w)
                                    for w in range(7)]))
    media_dia_sem = por_dia_sem / n_sem                                  # R$ esperado em cada dia da semana
    restantes = [datetime(ano, mes, d) for d in range(hoje.day + 1, dias_mes + 1)]
    variavel = float(sum(media_dia_sem[x.weekday()] for x in restantes))
    previsto = gasto + sum(v for _, v, _ in a_cair) + variavel
    # faixa: variação típica do ritmo (desvio dos gastos diários) nos dias que faltam
    diarios = {}
    for e, d in var:
        diarios[d.date()] = diarios.get(d.date(), 0.0) + float(e["amount"])
    desvio = float(np.std(list(diarios.values()))) if len(diarios) > 3 else 0.0
    folga = 1.28 * desvio * (len(restantes) ** 0.5)
    return {"gasto_ate_agora": round(gasto, 2), "previsto": round(previsto, 2),
            "faixa": (round(max(gasto, previsto - folga), 2), round(previsto + folga, 2)),
            "fixas_a_cair": [(c.split("|", 1)[1] or c, round(v, 2), dia) for c, v, dia in a_cair],
            "ritmo_diario": round(float(media_dia_sem.mean()), 2), "dias_restantes": len(restantes)}


def backtest(lancs: list[dict], hoje: datetime, dia: int = 15) -> list[dict]:
    """Para cada um dos últimos meses completos: o que o método previa no dia `dia` x o que gastou de fato."""
    desp = _despesas(lancs)
    if not desp:
        return []
    out = []
    a, m = hoje.year, hoje.month
    for _ in range(6):
        m -= 1
        if m == 0:
            a, m = a - 1, 12
        ref = datetime(a, m, min(dia, calendar.monthrange(a, m)[1]), 23, 59)
        antes = [e for e, d in desp if d <= ref]
        real = sum(float(e["amount"]) for e, d in desp if (d.year, d.month) == (a, m))
        if real <= 0 or len(antes) < 15:
            continue
        p = prever_mes(antes, ref)
        if p:
            out.append({"mes": f"{m:02d}/{a}", "previsto": p["previsto"], "real": round(real, 2),
                        "erro": abs(p["previsto"] - real) / real})
    return out
