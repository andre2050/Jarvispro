"""Busca no que você já fez (NEXUS Ultra 2026 3.3): relatórios dos agentes, anotações e diário.

"Nexus, o que eu anotei sobre o carro semana passada?"  ·  "procura o relatório da pesquisa de notebook"

Procura por palavras (sem acento, sem maiúsculas) em três lugares, todos só no seu PC:
  • relatórios dos agentes  → Documentos/NEXUS Agente/*.md
  • anotações rápidas       → config/quick_notes.json
  • diário                  → memory/diario.json
e entende o período: hoje, ontem, esta semana, semana passada, este mês, mês passado, "últimos 3 dias".
Só LÊ; não apaga nem muda nada. Nunca levanta erro para quem chama.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from core.protecao import engolida as _engolida

RAIZ = Path(__file__).resolve().parent.parent
PASTA_RELATORIOS = Path.home() / "Documents" / "NEXUS Agente"
ARQ_NOTAS = RAIZ / "config" / "quick_notes.json"
ARQ_DIARIO = RAIZ / "memory" / "diario.json"
MAX_RESULTADOS = 6

_BOBAGENS = {
    "o", "a", "os", "as", "um", "uma", "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas", "que",
    "eu", "meu", "minha", "sobre", "para", "pra", "por", "com", "e", "ou", "qual", "quais", "foi", "fiz",
    "fez", "anotei", "escrevi", "pesquisei", "procura", "procurar", "busca", "buscar", "acha", "achar",
    "relatorio", "relatorios", "nota", "notas", "diario", "anotacao", "anotacoes", "nexus", "te", "me",
    "tinha", "tenho", "ja", "algo", "alguma", "coisa", "falei", "disse", "aquilo", "aquele", "aquela",
}


def _sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(t or "").lower()) if unicodedata.category(c) != "Mn")


def _palavras(t: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", _sem_acento(t))


# ── período ─────────────────────────────────────────────────────────────────
def periodo(texto: str, hoje: date | None = None) -> tuple[date, date, str] | None:
    """(inicio, fim, rotulo) inclusive, ou None se o texto não fala de período."""
    t = _sem_acento(texto)
    h = hoje or date.today()
    if "anteontem" in t:
        d = h - timedelta(days=2)
        return d, d, "anteontem"
    if "ontem" in t:
        d = h - timedelta(days=1)
        return d, d, "ontem"
    if re.search(r"\bhoje\b", t):
        return h, h, "hoje"
    m = re.search(r"ultimos?\s+(\d{1,3})\s+dias?", t)
    if m:
        n = max(1, int(m.group(1)))
        return h - timedelta(days=n - 1), h, f"últimos {n} dias"
    if re.search(r"semana\s+(passada|anterior)", t):
        seg = h - timedelta(days=h.weekday() + 7)
        return seg, seg + timedelta(days=6), "semana passada"
    if re.search(r"(esta|essa|nesta)\s+semana", t):
        seg = h - timedelta(days=h.weekday())
        return seg, h, "esta semana"
    if re.search(r"mes\s+(passado|anterior)", t):
        fim = h.replace(day=1) - timedelta(days=1)
        return fim.replace(day=1), fim, "mês passado"
    if re.search(r"(este|esse|neste)\s+mes", t):
        return h.replace(day=1), h, "este mês"
    return None


def termos(texto: str) -> list[str]:
    """As palavras que importam na busca (sem o período e sem palavras de ligação)."""
    t = _sem_acento(texto)
    t = re.sub(r"ultimos?\s+\d{1,3}\s+dias?|semana\s+(passada|anterior)|(esta|essa|nesta)\s+semana|"
               r"mes\s+(passado|anterior)|(este|esse|neste)\s+mes|anteontem|ontem|hoje", " ", t)
    return [p for p in _palavras(t) if p not in _BOBAGENS and len(p) > 1]


# ── fontes ──────────────────────────────────────────────────────────────────
def _ler_json(arq: Path) -> list:
    try:
        d = json.loads(arq.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except Exception:
        return []


def itens(relatorios: Path | None = None, notas: Path | None = None, diario: Path | None = None) -> list[dict]:
    """Tudo o que pode ser procurado: [{'fonte','quando':datetime,'titulo','texto'}]."""
    out: list[dict] = []
    for n in _ler_json(notas or ARQ_NOTAS):
        try:
            out.append({"fonte": "anotação", "quando": datetime.fromtimestamp(float(n["at"])),
                        "titulo": "", "texto": str(n.get("text") or "")})
        except Exception:
            continue
    for e in _ler_json(diario or ARQ_DIARIO):
        try:
            out.append({"fonte": "diário", "quando": datetime.fromisoformat(e["quando"]),
                        "titulo": "", "texto": str(e.get("texto") or "")})
        except Exception:
            continue
    pasta = relatorios or PASTA_RELATORIOS
    try:
        for arq in pasta.glob("*.md"):
            try:
                txt = arq.read_text(encoding="utf-8", errors="replace")
                linha = next((l.strip("# ").strip() for l in txt.splitlines() if l.strip()), arq.stem)
                out.append({"fonte": "relatório", "quando": datetime.fromtimestamp(arq.stat().st_mtime),
                            "titulo": linha, "texto": txt[:6000], "arquivo": str(arq)})
            except Exception:
                continue
    except Exception:
        _engolida("core/busca_historico.py:117")
    return out


# ── busca ───────────────────────────────────────────────────────────────────
def buscar(pedido: str, hoje: date | None = None, **fontes) -> dict:
    """{'periodo': rotulo|None, 'termos': [...], 'resultados': [...]} — mais relevante e mais recente primeiro."""
    per = periodo(pedido, hoje)
    ts = termos(pedido)
    achados = []
    for it in itens(**fontes):
        dia = it["quando"].date()
        if per and not (per[0] <= dia <= per[1]):
            continue
        base = _sem_acento(it["titulo"] + " " + it["texto"])
        if ts:
            pontos = sum(1 for t in ts if t in base)
            if pontos == 0:
                continue
            pontos += 0.5 * sum(1 for t in ts if t in _sem_acento(it["titulo"]))
        else:
            pontos = 1
        achados.append((pontos, it["quando"], it))
    achados.sort(key=lambda x: (-x[0], -x[1].timestamp()))
    return {"periodo": per[2] if per else None, "termos": ts,
            "resultados": [a[2] for a in achados[:MAX_RESULTADOS]], "total": len(achados)}


def _trecho(it: dict, ts: list[str], tam: int = 110) -> str:
    texto = re.sub(r"\s+", " ", it["texto"]).strip()
    base = _sem_acento(texto)
    pos = min((base.find(t) for t in ts if t in base), default=0)
    ini = max(0, pos - 30)
    corte = texto[ini:ini + tam].strip()
    return ("…" if ini else "") + corte + ("…" if ini + tam < len(texto) else "")


def responder(pedido: str, hoje: date | None = None, **fontes) -> str:
    try:
        r = buscar(pedido, hoje, **fontes)
    except Exception as e:
        return f"[failed] Não consegui procurar agora: {e}"
    onde = f" ({r['periodo']})" if r["periodo"] else ""
    if not r["resultados"]:
        if not r["termos"] and not r["periodo"]:
            return "Diga o que procurar, por exemplo: “o que anotei sobre o carro semana passada?”."
        return f"Não achei nada sobre isso{onde} nos relatórios, nas anotações e no diário."
    linhas = []
    for it in r["resultados"][:5]:
        quando = f"{it['quando']:%d/%m %H:%M}"
        cab = it["titulo"] or it["fonte"]
        linhas.append(f"{it['fonte']} · {quando} · {cab[:60]}: {_trecho(it, r['termos'])}")
    mais = f" (mostrando 5 de {r['total']})" if r["total"] > 5 else ""
    return f"Achei {r['total']} resultado(s){onde}{mais}:\n" + "\n".join(linhas)
