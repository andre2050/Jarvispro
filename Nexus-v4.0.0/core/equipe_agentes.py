"""core/equipe_agentes.py — arquitetura multi-agentes com quadro compartilhado (NEXUS Ultra 4.0).

O orquestrador (3.2) já divide o trabalho entre especialistas (pesquisa, análise, código, agenda, finanças…) e os roda em paralelo, mas cada
um só enxergava o resultado FINAL dos outros. Aqui entra o QUADRO da equipe: uma lousa onde cada agente publica o que descobriu enquanto
trabalha, e os outros leem na hora (mesmo na mesma onda, em paralelo). O quadro também:
  • detecta CONFLITOS (dois agentes dizendo coisas diferentes sobre o mesmo assunto, ex.: dois preços para o mesmo item) para a síntese tratar;
  • limita tamanho (40 notas, cada uma curta) e entrega o conteúdo ao modelo como DADO, nunca como instrução;
  • guarda quem disse o quê e com que confiança.
`Equipe` roda agentes de verdade em paralelo (threads) sobre um quadro, com prazo — usado nos testes e por quem quiser montar uma equipe fora do orquestrador.
"""
from __future__ import annotations

import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _Timeout

MAX_NOTAS = 40
TAM_NOTA = 400
TAM_LEITURA = 1800
_STOP = {"o", "a", "os", "as", "um", "uma", "de", "do", "da", "dos", "das", "em", "no", "na", "que", "e", "ou", "para", "por", "com", "é", "foi", "são", "the", "of", "is", "and", "to",
         "custa", "reais", "real", "preco", "valor", "total", "cerca", "aproximadamente", "horas", "dias", "tem", "esta", "sao"}


def _n(t) -> str:
    return unicodedata.normalize("NFKD", str(t or "").lower()).encode("ascii", "ignore").decode()


def _palavras(t: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", _n(t)) if w not in _STOP}


def _numeros(t: str) -> set[str]:
    return {x.replace(",", ".").rstrip(".") for x in re.findall(r"\d+(?:[.,]\d+)?", str(t))}


class Quadro:
    def __init__(self):
        self._notas: list[dict] = []
        self._trava = threading.Lock()

    def publicar(self, agente: str, texto: str, confianca: float = 0.7, topico: str = "") -> None:
        texto = re.sub(r"\s+", " ", str(texto or "")).strip()[:TAM_NOTA]
        if not texto:
            return
        with self._trava:
            self._notas.append({"agente": str(agente)[:30], "texto": texto, "confianca": max(0.0, min(1.0, float(confianca))), "topico": str(topico)[:60], "t": time.time()})
            if len(self._notas) > MAX_NOTAS:
                self._notas = sorted(self._notas, key=lambda n: (-n["confianca"], -n["t"]))[:MAX_NOTAS]
                self._notas.sort(key=lambda n: n["t"])

    def ler(self, exceto: str = "") -> list[dict]:
        with self._trava:
            return [dict(n) for n in self._notas if n["agente"] != exceto]

    def texto_para(self, agente: str) -> str:
        """O que os OUTROS agentes já descobriram, pronto para o prompt (cortado em TAM_LEITURA)."""
        linhas = [f"[{n['agente']} · confiança {n['confianca']:.1f}] {n['texto']}" for n in self.ler(exceto=agente)]
        t = "\n".join(linhas)
        return t[-TAM_LEITURA:] if len(t) > TAM_LEITURA else t

    def conflitos(self) -> list[dict]:
        """Pares de notas de agentes diferentes sobre o mesmo assunto com números diferentes."""
        ns, out = self.ler(), []
        for i, a in enumerate(ns):
            for b in ns[i + 1:]:
                if a["agente"] == b["agente"]:
                    continue
                pa, pb = _palavras(a["texto"]), _palavras(b["texto"])
                if not pa or not pb:
                    continue
                mesmo_assunto = (a["topico"] and a["topico"] == b["topico"]) or (len(pa & pb) >= 2 and len(pa & pb) / min(len(pa), len(pb)) >= 0.6)
                na, nb = _numeros(a["texto"]), _numeros(b["texto"])
                if mesmo_assunto and na and nb and na != nb and not (na <= nb or nb <= na):
                    out.append({"a": (a["agente"], a["texto"]), "b": (b["agente"], b["texto"])})
        return out[:5]

    def texto_conflitos(self) -> str:
        c = self.conflitos()
        if not c:
            return ""
        return "POSSIBLE CONFLICTS between agents (data, resolve or flag them in the final answer): " + " || ".join(
            f"{x['a'][0]} says “{x['a'][1][:120]}” but {x['b'][0]} says “{x['b'][1][:120]}”" for x in c)


class Equipe:
    """Roda `agentes` ({nome: fn(tarefa, quadro) -> texto}) em paralelo, cada um com a mesma lousa."""

    def __init__(self, agentes: dict, quadro: Quadro | None = None, prazo_s: float = 120.0, max_paralelo: int = 4):
        self.agentes, self.quadro, self.prazo_s, self.max_paralelo = agentes, quadro or Quadro(), prazo_s, max_paralelo

    def executar(self, tarefas: dict[str, str]) -> dict:
        """tarefas: {agente: tarefa}. Devolve {"resultados": {agente: texto}, "erros": {agente: msg}, "conflitos": [...]}."""
        res: dict[str, str] = {}
        erros: dict[str, str] = {}
        fim = time.monotonic() + self.prazo_s
        with ThreadPoolExecutor(max_workers=max(1, min(self.max_paralelo, len(tarefas) or 1)), thread_name_prefix="nexus-equipe") as ex:
            futs = {n: ex.submit(self._um, n, t) for n, t in tarefas.items() if n in self.agentes}
            for n in tarefas:
                if n not in self.agentes:
                    erros[n] = "agente desconhecido"
            for n, f in futs.items():
                try:
                    res[n] = f.result(timeout=max(0.1, fim - time.monotonic()))
                except _Timeout:
                    erros[n] = "passou do prazo"
                except Exception as e:                                       # noqa: BLE001
                    erros[n] = f"{type(e).__name__}: {str(e)[:80]}"
        return {"resultados": res, "erros": erros, "conflitos": self.quadro.conflitos()}

    def _um(self, nome: str, tarefa: str) -> str:
        r = str(self.agentes[nome](tarefa, self.quadro) or "")
        self.quadro.publicar(nome, r, 0.7)
        return r


def saude() -> tuple[bool, str]:
    return True, "quadro e equipe prontos"
