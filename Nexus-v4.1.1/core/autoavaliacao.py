"""Auto-avaliação do NEXUS (Ultra 2026 3.2).

O NEXUS anota, para cada pedido do motor próprio, qual rota o roteador escolheu (rápido, forte ou
delegar), quanto demorou, se deu certo e se alguma ferramenta falhou. Com isso ele:

  • AJUSTA O ROTEADOR sozinho, com regras conservadoras:
      - pedido que foi para o modelo RÁPIDO e falhou (erro do modelo ou ferramenta com falha)
        → ensina "forte" para pedidos parecidos;
      - pedido SIMPLES (até 6 palavras, sem ferramenta) que foi para o modelo FORTE, deu certo e
        demorou muito, DUAS vezes → ensina "rápido".
    Só ensina o roteador; nunca mexe em permissões, arquivos ou configuração.
  • CONTA COMO ESTÁ SE SAINDO: pedidos, taxa de erro e tempo de resposta (mediana e p90) por rota,
    e quantos ajustes fez ("Nexus, como você está se saindo?").

Tudo fica em memory/autoavaliacao.json (só no PC). Nunca levanta erro para quem chama.
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent.parent / "memory" / "autoavaliacao.json"
VERSAO = 1
MAX_EVENTOS = 400
LENTO_MS = 8000            # "demorou muito" para um pedido simples
MAX_PALAVRAS_SIMPLES = 6
REPETICOES_PARA_REBAIXAR = 2
ROTAS = ("rapido", "forte", "delegar")

_trava = threading.RLock()


def _norm(texto: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\wÀ-ÿ ]+", " ", str(texto or "").lower())).strip()


def _carregar(arquivo: Path | None = None) -> dict:
    try:
        d = json.loads((arquivo or ARQUIVO).read_text(encoding="utf-8"))
        if d.get("versao") == VERSAO and isinstance(d.get("eventos"), list):
            return d
    except Exception:
        pass
    return {"versao": VERSAO, "eventos": [], "ajustes": []}


def _salvar(d: dict, arquivo: Path | None = None) -> None:
    arq = arquivo or ARQUIVO
    try:
        arq.parent.mkdir(parents=True, exist_ok=True)
        d["eventos"] = d["eventos"][-MAX_EVENTOS:]
        d["ajustes"] = d["ajustes"][-100:]
        tmp = arq.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        tmp.replace(arq)
    except Exception:
        pass


def _ensinar(texto: str, rota: str) -> bool:
    try:
        from core import roteador_modelos as RM
        RM.roteador.aprender(texto, rota)
        return True
    except Exception:
        return False


def registrar(texto: str, rota: str, ok: bool, ms: float, ferramentas: int = 0, falhas: int = 0,
              arquivo: Path | None = None, ensinar=None) -> str | None:
    """Anota um pedido e aplica as regras de ajuste. Devolve a rota ensinada (ou None)."""
    if rota not in ROTAS:
        return None
    texto = str(texto or "").strip()
    if not texto or texto.startswith("["):         # mensagens do próprio app não contam
        return None
    ensinar = ensinar or _ensinar
    ensinada = None
    try:
        with _trava:
            d = _carregar(arquivo)
            ev = {"t": int(time.time()), "texto": texto[:200], "rota": rota, "ok": bool(ok),
                  "ms": int(max(0, ms)), "ferramentas": int(ferramentas), "falhas": int(falhas)}
            d["eventos"].append(ev)

            if rota == "rapido" and (not ok or falhas > 0):
                if ensinar(texto, "forte"):
                    ensinada = "forte"
                    d["ajustes"].append({"t": ev["t"], "texto": texto[:120], "para": "forte",
                                         "motivo": "o modelo rápido falhou"})
            elif (rota == "forte" and ok and falhas == 0 and ferramentas == 0 and ms >= LENTO_MS
                  and len(texto.split()) <= MAX_PALAVRAS_SIMPLES):
                chave = _norm(texto)
                lentos = [e for e in d["eventos"]
                          if e["rota"] == "forte" and e["ok"] and e["ms"] >= LENTO_MS
                          and e["ferramentas"] == 0 and _norm(e["texto"]) == chave]
                if len(lentos) >= REPETICOES_PARA_REBAIXAR and ensinar(texto, "rapido"):
                    ensinada = "rapido"
                    d["ajustes"].append({"t": ev["t"], "texto": texto[:120], "para": "rapido",
                                         "motivo": "pedido simples e lento no modelo forte"})
                    d["eventos"] = [e for e in d["eventos"]
                                    if not (e["rota"] == "forte" and _norm(e["texto"]) == chave)]
            _salvar(d, arquivo)
    except Exception:
        return None
    return ensinada


class Turno:
    """Acompanha UM pedido do motor próprio: `falha_ferramenta()` / `ferramenta()` durante, `fechar()` no fim."""

    def __init__(self, texto: str, rota: str | None):
        self.texto, self.rota = texto, rota
        self.t0 = time.monotonic()
        self.ferramentas = 0
        self.falhas = 0
        self._fechado = False

    def ferramenta(self, falhou: bool = False) -> None:
        self.ferramentas += 1
        if falhou:
            self.falhas += 1

    def fechar(self, ok: bool) -> str | None:
        if self._fechado or self.rota not in ROTAS:
            return None
        self._fechado = True
        return registrar(self.texto, self.rota, ok, (time.monotonic() - self.t0) * 1000,
                         self.ferramentas, self.falhas)


# ── o que ele aprendeu sobre si mesmo ───────────────────────────────────────

def _percentil(valores: list[int], p: float) -> int | None:
    if not valores:
        return None
    v = sorted(valores)
    return int(v[min(len(v) - 1, int(round(p * (len(v) - 1))))])


def relatorio(arquivo: Path | None = None) -> dict:
    d = _carregar(arquivo)
    por_rota = {}
    for r in ROTAS:
        ev = [e for e in d["eventos"] if e["rota"] == r]
        ms = [e["ms"] for e in ev if e["ok"]]
        por_rota[r] = {
            "pedidos": len(ev),
            "erros": sum(1 for e in ev if not e["ok"] or e["falhas"] > 0),
            "mediana_ms": _percentil(ms, 0.5),
            "p90_ms": _percentil(ms, 0.9),
        }
    return {"total": len(d["eventos"]), "rotas": por_rota, "ajustes": list(d["ajustes"]),
            "ajustes_total": len(d["ajustes"])}


def _seg(ms) -> str:
    if ms is None:
        return "sem medida"
    return f"{ms / 1000:.1f} s".replace(".", ",")


def resumo_texto(arquivo: Path | None = None) -> str:
    r = relatorio(arquivo)
    if not r["total"]:
        return "Ainda não tenho pedidos suficientes para me avaliar."
    nomes = {"rapido": "modelo rápido", "forte": "modelo forte", "delegar": "equipe de agentes"}
    partes = []
    for k in ROTAS:
        s = r["rotas"][k]
        if not s["pedidos"]:
            continue
        partes.append(f"{nomes[k]}: {s['pedidos']} pedido(s), {s['erros']} com problema, "
                      f"resposta típica em {_seg(s['mediana_ms'])} (90% até {_seg(s['p90_ms'])})")
    txt = "Nos últimos pedidos, " + "; ".join(partes) + "."
    if r["ajustes_total"]:
        ult = r["ajustes"][-1]
        txt += (f" Já me ajustei {r['ajustes_total']} vez(es); o último foi mandar "
                f"“{ult['texto'][:60]}” para o modelo {'forte' if ult['para'] == 'forte' else 'rápido'} "
                f"({ult['motivo']}).")
    else:
        txt += " Ainda não precisei me ajustar."
    return txt


def esquecer(arquivo: Path | None = None) -> None:
    with _trava:
        _salvar({"versao": VERSAO, "eventos": [], "ajustes": []}, arquivo)
