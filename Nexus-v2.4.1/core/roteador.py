"""
core/roteador.py — segunda opinião para a rede local de intenções (NEXUS Pro 2.3).

A `intent_net` (MLP) decide rápido, mas pode errar com muita confiança diante de uma frase
estranha. Aqui entra um VERIFICADOR independente: compara a frase, por sentido (core/embeddings),
com TODOS os exemplos conhecidos (as frases de treino e as suas) e vota pelos vizinhos mais
próximos. Só vale executar na hora quando as duas opiniões concordam:

  • MLP e vizinhos concordam               → executa local, sem esperar o Gemini
  • vizinhos discordam com firmeza         → NÃO executa local; vai para o Gemini
  • frase sem nenhum vizinho parecido      → NÃO executa local; vai para o Gemini
  • vizinhos sem opinião forte             → vale a decisão da rede (ex.: um programa novo em "abre o X")

Errar para o lado do Gemini só custa uns segundos; errar para o lado do "executo sozinho"
pode abrir/fechar/mudar algo sem você ter pedido. Por isso o desempate é sempre o Gemini.

Tudo local, em NumPy. O índice dos exemplos se refaz sozinho quando a rede é retreinada.
"""
from __future__ import annotations

import threading

import numpy as np

from core import embeddings as E

K = 7
SIM_MINIMA = 0.18          # abaixo disso nenhum exemplo se parece com a frase
SIM_FIRME = 0.45           # vizinho mais próximo a partir daqui é opinião "firme"
VOTO_MINIMO = 0.34         # fatia mínima dos votos (ponderados) para confirmar a intenção


class Verificador:
    def __init__(self):
        self._trava = threading.Lock()
        self._emb = E.EmbedderHash()
        self._M: np.ndarray | None = None
        self._y: list[str] = []
        self._assinatura = ""

    def construir(self, textos: list[str], rotulos: list[str]) -> None:
        with self._trava:
            self._emb = E.EmbedderHash()
            self._emb.ajustar(textos)
            self._M = self._emb.embed(textos)
            self._y = list(rotulos)
            self._assinatura = f"{len(textos)}|{hash(tuple(rotulos[:50]))}"

    @property
    def pronto(self) -> bool:
        return self._M is not None and len(self._y) > 0

    def vizinhos(self, texto: str, k: int = K) -> list[tuple[str, float]]:
        with self._trava:
            if not self.pronto:
                return []
            q = self._emb.embed([texto])[0]
            return [(self._y[i], s) for i, s in E.cosseno_top(q, self._M, k)]

    def opiniao(self, texto: str) -> tuple[str | None, float, float]:
        """(intenção mais votada, similaridade do vizinho mais próximo, fatia dos votos)."""
        viz = self.vizinhos(texto)
        if not viz:
            return None, 0.0, 0.0
        peso: dict[str, float] = {}
        for r, s in viz:
            peso[r] = peso.get(r, 0.0) + max(s, 0.0) ** 2
        total = sum(peso.values()) or 1.0
        melhor = max(peso, key=peso.get)
        return melhor, viz[0][1], peso[melhor] / total

    def concorda(self, texto: str, intencao: str) -> tuple[bool, str]:
        """(pode executar local?, motivo). Sem índice pronto, não atrapalha."""
        if not self.pronto:
            return True, "sem verificador"
        melhor, sim_top, _ = self.opiniao(texto)
        if melhor is None or sim_top < SIM_MINIMA:
            return False, "nenhuma frase conhecida se parece com esta"
        viz = self.vizinhos(texto)
        peso: dict[str, float] = {}
        for r, s in viz:
            peso[r] = peso.get(r, 0.0) + max(s, 0.0) ** 2
        total = sum(peso.values()) or 1.0
        fatia = peso.get(intencao, 0.0) / total
        if fatia >= VOTO_MINIMO:
            return True, f"vizinhos confirmam ({fatia:.0%})"
        if sim_top >= SIM_FIRME and melhor != intencao:
            return False, f"vizinhos apontam para “{melhor}” ({peso[melhor] / total:.0%})"
        # evidência fraca (ex.: nome de programa que nunca vimos): não veta, a rede decide
        return True, f"vizinhos neutros ({fatia:.0%})"


verificador = Verificador()
