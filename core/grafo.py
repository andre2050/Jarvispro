"""core/grafo.py — memória em grafo de conhecimento (NEXUS Ultra 2026 3.8).

Pessoas, projetos, compromissos, preferências e notas viram nós; quando um texto cita o nome de outro nó, nasce uma
ligação "menciona" guardando de ONDE veio (a fonte). Assim dá para perguntar "o que tenho a ver com a Maria?" e receber
a vizinhança com a origem de cada fato. Tudo local, em memory/grafo.json. Heurístico (sem IA): só liga o que está escrito.
As fontes são funções injetadas: cada uma devolve itens {tipo, nome, texto, fonte}.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import deque
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent.parent / "memory" / "grafo.json"
TIPOS = ("pessoa", "projeto", "compromisso", "preferencia", "nota", "lugar")
MIN_NOME = 3
MAX_NOS = 3000
MAX_TEXTO = 600


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


def _id(tipo: str, nome: str) -> str:
    return f"{tipo}:{_sem_acento(nome).strip()}"


class Grafo:
    def __init__(self):
        self.nos: dict[str, dict] = {}
        self.arestas: list[dict] = []

    # ── montagem ──
    def adicionar(self, tipo: str, nome: str, texto: str = "", fonte: str = "") -> str | None:
        nome = " ".join(str(nome or "").split())[:80]
        if tipo not in TIPOS or len(nome) < 2 or len(self.nos) >= MAX_NOS and _id(tipo, nome) not in self.nos:
            return None
        i = _id(tipo, nome)
        n = self.nos.setdefault(i, {"tipo": tipo, "nome": nome, "textos": [], "fontes": []})
        t = " ".join(str(texto or "").split())[:MAX_TEXTO]
        if t and t not in n["textos"] and len(n["textos"]) < 8:
            n["textos"].append(t)
        if fonte and fonte not in n["fontes"] and len(n["fontes"]) < 8:
            n["fontes"].append(fonte)
        return i

    def ligar(self, a: str, rel: str, b: str, fonte: str = "") -> None:
        if a == b or a not in self.nos or b not in self.nos:
            return
        if any(e["a"] == a and e["b"] == b and e["rel"] == rel for e in self.arestas):
            return
        self.arestas.append({"a": a, "rel": rel, "b": b, "fonte": fonte})

    def ligar_mencoes(self) -> int:
        """Se o texto de um nó cita o nome de outro (palavra inteira, sem acento), liga os dois."""
        padroes = {}
        for i, n in self.nos.items():
            nome = _sem_acento(n["nome"])
            if len(nome) >= MIN_NOME:
                padroes[i] = re.compile(r"(?<!\w)" + re.escape(nome) + r"(?!\w)")
        antes = len(self.arestas)
        for i, n in self.nos.items():
            corpo = _sem_acento(" ".join(n["textos"] + [n["nome"]]))
            for j, p in padroes.items():
                if i != j and p.search(corpo):
                    self.ligar(i, "menciona", j, (n["fontes"] or [""])[0])
        return len(self.arestas) - antes

    # ── consulta ──
    def achar(self, consulta: str) -> list[str]:
        q = _sem_acento(consulta).strip()
        if not q:
            return []
        exatos = [i for i, n in self.nos.items() if _sem_acento(n["nome"]) == q]
        return exatos or [i for i, n in self.nos.items() if q in _sem_acento(n["nome"])][:5]

    def _vizinhos(self, i: str):
        for e in self.arestas:
            if e["a"] == i:
                yield e["b"], e, "→"
            elif e["b"] == i:
                yield e["a"], e, "←"

    def vizinhanca(self, consulta: str, profundidade: int = 2, limite: int = 25) -> dict:
        ini = self.achar(consulta)
        if not ini:
            return {"achou": False, "consulta": consulta, "fatos": []}
        raiz = ini[0]
        visto, fila, fatos = {raiz}, deque([(raiz, 0)]), []
        while fila and len(fatos) < limite:
            i, d = fila.popleft()
            if d >= max(1, min(profundidade, 3)):
                continue
            for j, e, _sentido in self._vizinhos(i):
                fatos.append({"de": self.nos[e["a"]]["nome"], "rel": e["rel"], "para": self.nos[e["b"]]["nome"],
                              "fonte": e["fonte"], "nivel": d + 1})
                if j not in visto:
                    visto.add(j)
                    fila.append((j, d + 1))
                if len(fatos) >= limite:
                    break
        n = self.nos[raiz]
        return {"achou": True, "no": {"tipo": n["tipo"], "nome": n["nome"], "textos": n["textos"], "fontes": n["fontes"]},
                "fatos": fatos}

    def caminho(self, a: str, b: str) -> list[str] | None:
        ia, ib = self.achar(a), self.achar(b)
        if not ia or not ib:
            return None
        ini, fim = ia[0], ib[0]
        pai, fila = {ini: None}, deque([ini])
        while fila:
            i = fila.popleft()
            if i == fim:
                rota = []
                while i is not None:
                    rota.append(self.nos[i]["nome"])
                    i = pai[i]
                return rota[::-1]
            for j, _e, _s in self._vizinhos(i):
                if j not in pai:
                    pai[j] = i
                    fila.append(j)
        return None

    # ── disco ──
    def salvar(self, arq: Path | None = None) -> None:
        arq = Path(arq or ARQUIVO)
        arq.parent.mkdir(parents=True, exist_ok=True)
        tmp = arq.with_suffix(".tmp")
        tmp.write_text(json.dumps({"nos": self.nos, "arestas": self.arestas}, ensure_ascii=False), encoding="utf-8")
        tmp.replace(arq)

    @classmethod
    def carregar(cls, arq: Path | None = None) -> "Grafo":
        g = cls()
        try:
            d = json.loads(Path(arq or ARQUIVO).read_text(encoding="utf-8"))
            if isinstance(d.get("nos"), dict) and isinstance(d.get("arestas"), list):
                g.nos, g.arestas = d["nos"], [e for e in d["arestas"] if isinstance(e, dict) and {"a", "rel", "b"} <= set(e)]
        except Exception:
            pass
        return g


def construir(fontes: dict | None = None) -> Grafo:
    """Reconstrói o grafo do zero a partir das fontes (padrão: contatos, projetos, tarefas, preferências, diário)."""
    fontes = fontes if fontes is not None else fontes_padrao()
    g = Grafo()
    for nome_fonte, fn in fontes.items():
        try:
            itens = fn() or []
        except Exception:
            continue
        for it in itens:
            if isinstance(it, dict):
                g.adicionar(str(it.get("tipo")), it.get("nome", ""), it.get("texto", ""), it.get("fonte") or nome_fonte)
    g.ligar_mencoes()
    return g


def _json(nome: str, padrao):
    try:
        return json.loads((Path(__file__).resolve().parent.parent / "memory" / nome).read_text(encoding="utf-8"))
    except Exception:
        return padrao


def fontes_padrao() -> dict:
    def contatos():
        return [{"tipo": "pessoa", "nome": c.get("nome"), "texto": " ".join(str(c.get(k, "")) for k in ("relacao", "obs", "notas", "empresa"))}
                for c in _json("contatos.json", []) if isinstance(c, dict)]

    def projetos():
        d = _json("projetos.json", {})
        return [{"tipo": "projeto", "nome": p.get("nome"), "texto": " ".join([str(p.get("proximo_passo", ""))] + [str(x) for x in p.get("notas", [])])}
                for p in (d.get("projetos", []) if isinstance(d, dict) else []) if isinstance(p, dict)]

    def tarefas():
        d = _json("tarefas.json", [])
        d = d.get("tarefas", d) if isinstance(d, dict) else d
        return [{"tipo": "compromisso", "nome": str(t.get("titulo") or t.get("texto") or t.get("nome") or "")[:60],
                 "texto": str(t.get("titulo") or t.get("texto") or "")} for t in d if isinstance(t, dict)]

    def preferencias():
        d = _json("long_term.json", {})
        out = []
        for grupo in ("preferences", "projects", "relationships"):
            for k, v in (d.get(grupo, {}) if isinstance(d, dict) else {}).items():
                valor = v.get("value") if isinstance(v, dict) else v
                tipo = "preferencia" if grupo == "preferences" else "projeto" if grupo == "projects" else "pessoa"
                out.append({"tipo": tipo, "nome": k.replace("_", " "), "texto": str(valor)})
        return out

    def diario():
        d = _json("diario.json", [])
        return [{"tipo": "nota", "nome": "diário " + str(e.get("quando", ""))[:10], "texto": str(e.get("texto", ""))}
                for e in (d if isinstance(d, list) else []) if isinstance(e, dict)][-60:]

    return {"contatos": contatos, "projetos": projetos, "tarefas": tarefas, "preferencias": preferencias, "diario": diario}


def texto(res: dict) -> str:
    if not res.get("achou"):
        return f"Não conheço “{res.get('consulta')}” no grafo."
    n = res["no"]
    linhas = [f"{n['nome']} ({n['tipo']})" + (f": {n['textos'][0][:120]}" if n["textos"] else "")]
    for f in res["fatos"][:12]:
        linhas.append(f"- {f['de']} {f['rel']} {f['para']}" + (f" [fonte: {f['fonte']}]" if f["fonte"] else ""))
    if not res["fatos"]:
        linhas.append("Sem ligações ainda.")
    return "\n".join(linhas)
