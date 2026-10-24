"""
core/indice_semantico.py — a memória que entende o SENTIDO (NEXUS Pro 2.3).

Junta o que o NEXUS sabe sobre você — notas, diário, tarefas, projetos, contatos, fatos da
memória, resumos de conversas — num índice de vetores (core/embeddings.py) e responde
"o que eu falei sobre a viagem?" mesmo quando a palavra "viagem" não está no texto.

O índice fica em memory/indice_semantico.npz, só no seu PC (fora do GitHub). Atualizar é
barato: só o que mudou é recalculado.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

import numpy as np

from core import embeddings as E

_BASE = Path(__file__).resolve().parent.parent
ARQUIVO = _BASE / "memory" / "indice_semantico.npz"
FONTES = ("notas", "diario", "tarefas", "projetos", "contatos", "memoria", "conversas")
_MAX_TEXTO = 400
_TRAVA = threading.RLock()


def _ler(arq: Path, padrao):
    try:
        d = json.loads(Path(arq).read_text(encoding="utf-8"))
        return d if isinstance(d, type(padrao)) else padrao
    except Exception:
        return padrao


# ── coleta: cada função devolve [{fonte, texto, quando}] e nunca levanta erro ──
def _notas(base: Path):
    for n in _ler(base / "config" / "quick_notes.json", []):
        if isinstance(n, dict) and n.get("text"):
            yield {"fonte": "notas", "texto": str(n["text"]), "quando": n.get("at")}


def _diario(base: Path):
    for e in _ler(base / "memory" / "diario.json", []):
        if isinstance(e, dict) and e.get("texto"):
            yield {"fonte": "diario", "texto": str(e["texto"]), "quando": e.get("quando")}


def _tarefas(base: Path):
    for t in _ler(base / "memory" / "tarefas.json", []):
        if isinstance(t, dict) and t.get("titulo"):
            extra = f" ({t['projeto']})" if t.get("projeto") else ""
            yield {"fonte": "tarefas", "texto": str(t["titulo"]) + extra, "quando": t.get("criada")}


def _projetos(base: Path):
    d = _ler(base / "memory" / "projetos.json", {})
    for p in d.get("projetos", []) if isinstance(d, dict) else []:
        if isinstance(p, dict) and p.get("nome"):
            partes = [str(p.get("nome")), str(p.get("proximo_passo") or p.get("proximo") or "")]
            partes += [str(n.get("texto", n)) if isinstance(n, dict) else str(n) for n in (p.get("notas") or [])[-3:]]
            yield {"fonte": "projetos", "texto": " — ".join(x for x in partes if x), "quando": None}


def _contatos(base: Path):
    for c in _ler(base / "memory" / "contatos.json", []):
        if isinstance(c, dict) and c.get("nome"):
            texto = c["nome"] + (f" — {c['notas']}" if c.get("notas") else "")
            yield {"fonte": "contatos", "texto": texto, "quando": None}


def _memoria(base: Path):
    d = _ler(base / "memory" / "long_term.json", {})
    if not isinstance(d, dict):
        return
    for cat, itens in d.items():
        if cat == "sessions" or not isinstance(itens, dict):
            continue
        for chave, ent in itens.items():
            val = ent.get("value") if isinstance(ent, dict) else ent
            if val:
                yield {"fonte": "memoria", "texto": f"{str(chave).replace('_', ' ')}: {val}",
                       "quando": ent.get("updated") if isinstance(ent, dict) else None}


def _conversas(base: Path):
    d = _ler(base / "memory" / "conversations.json", {})
    if not isinstance(d, dict):
        return
    for s in d.get("sessions", []):
        if isinstance(s, dict) and s.get("summary"):
            yield {"fonte": "conversas", "texto": str(s["summary"]), "quando": s.get("date")}
    for t in d.get("threads", []):
        if isinstance(t, dict):
            txt = t.get("topic") or t.get("title") or t.get("summary")
            if txt:
                yield {"fonte": "conversas", "texto": str(txt), "quando": t.get("updated") or t.get("date")}


_COLETORES = {"notas": _notas, "diario": _diario, "tarefas": _tarefas, "projetos": _projetos,
              "contatos": _contatos, "memoria": _memoria, "conversas": _conversas}


def coletar(base: Path = _BASE, fontes=FONTES) -> list[dict]:
    docs, vistos = [], set()
    for f in fontes:
        try:
            for d in _COLETORES[f](base):
                texto = " ".join(str(d["texto"]).split())[:_MAX_TEXTO]
                if len(texto) < 3:
                    continue
                chave = hashlib.sha1(f"{f}|{texto}".encode()).hexdigest()[:16]
                if chave in vistos:
                    continue
                vistos.add(chave)
                docs.append({"id": chave, "fonte": f, "texto": texto, "quando": d.get("quando")})
        except Exception as e:
            print(f"[Indice] fonte {f} ignorada: {e}")
    return docs


# ── índice ───────────────────────────────────────────────────────────────────
class Indice:
    def __init__(self, arquivo: Path = ARQUIVO, base: Path = _BASE):
        self.arquivo, self.base = Path(arquivo), Path(base)
        self.docs: list[dict] = []
        self.vetores = np.zeros((0, 1), np.float32)
        self.motor = ""
        self.atualizado_em = 0.0
        self._estado: dict = {}
        self._carregar()

    def _carregar(self) -> None:
        try:
            with np.load(self.arquivo, allow_pickle=False) as z:
                self.docs = json.loads(str(z["docs"]))
                self.vetores = z["vetores"].astype(np.float32)
                self.motor = str(z["motor"])
                self.atualizado_em = float(z["quando"])
                self._estado = {k[4:]: z[k] for k in z.files if k.startswith("est_")}
        except Exception:
            self.docs, self.vetores, self.motor = [], np.zeros((0, 1), np.float32), ""

    def _salvar(self) -> None:
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.arquivo.with_suffix(".tmp.npz")
        extra = {f"est_{k}": v for k, v in self._estado.items()}
        np.savez_compressed(tmp, docs=json.dumps(self.docs, ensure_ascii=False), vetores=self.vetores,
                            motor=self.motor, quando=self.atualizado_em, **extra)
        tmp.replace(self.arquivo)

    def atualizar(self, preferir: str = "auto", forcar: bool = False) -> dict:
        """Recalcula só o que mudou. Devolve {total, novos, removidos, motor}."""
        with _TRAVA:
            emb = E.get_embedder(preferir)
            novos_docs = coletar(self.base)
            motor_mudou = forcar or emb.nome != self.motor
            # o IDF do motor hash depende do corpus inteiro: quando muda bastante, refaz tudo
            refazer = motor_mudou or (emb.nome == "hash" and abs(len(novos_docs) - len(self.docs)) > max(20, len(self.docs) // 4))
            if refazer and emb.nome == "hash":
                emb.ajustar([d["texto"] for d in novos_docs])
            elif emb.nome == "hash" and self._estado:
                emb.carregar_estado(self._estado)
            antigos = {d["id"]: i for i, d in enumerate(self.docs)}
            mantidos = [] if refazer else [d for d in novos_docs if d["id"] in antigos]
            a_calcular = [d for d in novos_docs if refazer or d["id"] not in antigos]
            vet_novos = emb.embed([d["texto"] for d in a_calcular]) if a_calcular else np.zeros((0, 1), np.float32)
            partes_docs, partes_vet = [], []
            if mantidos:
                partes_docs += mantidos
                partes_vet.append(self.vetores[[antigos[d["id"]] for d in mantidos]])
            if a_calcular:
                partes_docs += a_calcular
                partes_vet.append(vet_novos)
            removidos = len([i for i in antigos if i not in {d["id"] for d in novos_docs}]) if not refazer else 0
            self.docs = partes_docs
            self.vetores = np.concatenate(partes_vet) if partes_vet else np.zeros((0, 1), np.float32)
            self.motor = emb.nome
            self._estado = emb.estado()
            self.atualizado_em = time.time()
            self._salvar()
            return {"total": len(self.docs), "novos": len(a_calcular), "removidos": removidos, "motor": emb.nome}

    def buscar(self, consulta: str, k: int = 5, minimo: float | None = None, fontes=None) -> list[tuple[float, dict]]:
        with _TRAVA:
            if not self.docs or not str(consulta).strip():
                return []
            emb = E.get_embedder("onnx" if self.motor == "onnx" else "hash")
            if emb.nome != self.motor:
                return []                      # índice de outro motor: precisa atualizar
            if emb.nome == "hash" and self._estado:
                emb.carregar_estado(self._estado)
            q = emb.embed([consulta])[0]
            if minimo is None:
                minimo = 0.30 if emb.nome == "onnx" else 0.22
            pool = E.cosseno_top(q, self.vetores, k=min(len(self.docs), max(k * 4, 20)))
            saida = []
            for i, s in pool:
                d = self.docs[i]
                if s >= minimo and (not fontes or d["fonte"] in fontes):
                    saida.append((s, d))
            return saida[:k]


_indice: Indice | None = None


def indice() -> Indice:
    global _indice
    if _indice is None:
        _indice = Indice()
    return _indice
