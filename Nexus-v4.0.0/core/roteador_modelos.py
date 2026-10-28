"""core/roteador_modelos.py — o cérebro de decisão do NEXUS (2.5.0).

Antes de cada pedido, uma rede neural local (NumPy, roda em milissegundos, nada sai do PC) decide
três coisas de uma vez, olhando o SENTIDO da frase (core/embeddings) e sinais de estrutura
(tamanho, "depois", "compara", "salva", código…):

    rapido   pedido simples        → modelo rápido e barato
    forte    precisa raciocinar    → modelo forte
    delegar  objetivo de vários passos → orquestrador de agentes (actions/orquestrador.py)

Ela nasce treinada com ~1000 frases geradas (pt/en) e APRENDE COM O SEU USO: quando um modelo rápido
falha num pedido, o pedido passa a contar como "forte"; quando um pedido virou uma tarefa de vários
passos, passa a contar como "delegar". O que ela aprende fica em memory/roteador_exemplos.json.

Errar para o lado seguro: na dúvida entre rápido e forte, usa o forte; só sugere delegar com
confiança alta (≥ 0,55) e frase longa o bastante.

    from core import roteador_modelos as RM
    d = RM.roteador.decidir("pesquisa os 3 melhores notebooks, compara e salva num arquivo")
    d.rota        # "delegar"
    RM.roteador.aprender(texto, "forte")        # o rápido não deu conta
"""
from __future__ import annotations

import json
import random
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from core import embeddings as E

_BASE = Path(__file__).resolve().parent.parent
ARQUIVO = _BASE / "memory" / "roteador_exemplos.json"

ROTAS = ("rapido", "forte", "delegar")
VERSAO_DADOS = 1
MAX_EXEMPLOS = 600
RETREINAR_A_CADA = 4              # exemplos novos até retreinar
LIMIAR_DELEGAR = 0.55
MIN_PALAVRAS_DELEGAR = 5


# ══════════════════════════════════════════════════════════════════════════════
# Dados de treino gerados
# ══════════════════════════════════════════════════════════════════════════════

_TEMAS = ["notebooks", "celulares", "fones de ouvido", "carros elétricos", "cafeteiras", "monitores",
          "passagens para Lisboa", "cursos de Python", "restaurantes japoneses", "bicicletas",
          "planos de internet", "tênis de corrida", "livros de finanças", "hotéis em Recife",
          "placas de vídeo", "geladeiras", "smartwatches", "cadeiras de escritório", "impressoras",
          "notícias sobre inteligência artificial", "receitas de bolo", "ferramentas de edição de vídeo",
          "faculdades de engenharia", "seguros de carro", "câmeras", "teclados mecânicos"]
_TEMAS_EN = ["laptops", "phones", "headphones", "electric cars", "coffee machines", "monitors",
             "flights to Lisbon", "Python courses", "running shoes", "internet plans", "AI news"]
_CODIGO = ["uma função que ordena uma lista", "um script que renomeia arquivos", "uma classe para guardar contatos",
           "um parser de CSV", "um servidor web simples", "um bot para o Discord", "uma API de tarefas",
           "um jogo da velha", "um conversor de moedas", "um scraper de preços", "testes para o meu módulo"]
_ASSUNTOS = ["a diferença entre Python e JavaScript", "como funciona o juro composto", "o que é uma rede neural",
             "como a vacina funciona", "por que o céu é azul", "a história do Império Romano",
             "como funciona o blockchain", "o que é inflação", "como investir em renda fixa",
             "a teoria da relatividade", "como um motor a combustão funciona", "a fotossíntese"]
_SIMPLES_PT = ["que horas são", "abre o spotify", "aumenta o volume", "diminui o volume", "silencia o som",
               "toca a próxima música", "pausa a música", "oi tudo bem", "bom dia", "boa noite", "obrigado",
               "me conta uma piada", "como está o tempo hoje", "quanto é 15 vezes 3", "que dia é hoje",
               "qual a capital da França", "liga um timer de 5 minutos", "anota comprar leite",
               "lê minhas notas", "tem e-mail novo", "quanta bateria eu tenho", "fecha o chrome",
               "abre o bloco de notas", "traduz cachorro para inglês", "o que significa saudade",
               "me chama de André", "quantos dias tem fevereiro", "que dia da semana é amanhã",
               "para de falar", "repete isso", "tá bom", "sim", "não", "pode ser", "valeu",
               "abre a calculadora", "tira o som", "volume em 40", "qual o status do sistema",
               "abre o youtube", "abre o whatsapp", "manda um oi", "quem é você", "como você se chama"]
_SIMPLES_EN = ["what time is it", "open spotify", "turn the volume up", "mute", "next song", "pause the music",
               "hello", "good morning", "thanks", "tell me a joke", "how is the weather", "what is 15 times 3",
               "set a timer for 5 minutes", "who are you", "open the calculator", "what day is it", "yes", "no"]


def _gerar(seed: int = 7) -> tuple[list[str], list[str]]:
    rng = random.Random(seed)
    X, Y = [], []

    def put(t: str, r: str) -> None:
        if rng.random() < 0.12:                       # erro de digitação leve
            i = rng.randrange(1, max(2, len(t) - 1))
            t = t[:i] + t[i + 1:]
        X.append(t); Y.append(r)

    pre = ["", "", "", "nexus ", "ei nexus ", "por favor ", "me ajuda: ", "preciso que você ", "pode "]
    # rápido ───────────────────────────────────────────────────────────────────
    for _ in range(5):
        for s in _SIMPLES_PT + _SIMPLES_EN:
            put(rng.choice(pre) + s, "rapido")
    # forte: um passo só, mas que exige raciocínio / texto longo / código ────────
    modelos_forte = [
        "explica em detalhes {a}", "me explica {a} como se eu tivesse dez anos", "escreve {c}",
        "cria {c} e comenta o código", "revisa esse código e acha o bug", "por que esse código dá erro",
        "faz um resumo bem completo sobre {a}", "compara as vantagens e desvantagens de {a}",
        "me ajuda a decidir entre dois empregos, um paga mais e o outro tem mais tempo livre",
        "escreve um poema sobre {t}", "escreve um e-mail formal pedindo reembolso",
        "analisa os prós e contras de comprar {t} agora", "qual a melhor estratégia para estudar {a}",
        "reescreve esse texto de forma mais clara e profissional", "traduz esse parágrafo inteiro para inglês",
        "me ensina {a} passo a passo", "monta um plano de estudos para aprender {a} em 3 meses",
        "resolve esse problema de matemática e mostra o raciocínio", "otimiza essa função para ficar mais rápida",
        "explain {a} in depth", "write {c}", "debug this code and explain the problem",
        "write a detailed essay about {a}", "compare the pros and cons of {a}", "summarize this long article",
        "help me think through a hard decision about my career", "refactor this class to be cleaner",
        "me dá um parecer sincero sobre meu plano de negócio", "escreve uma carta de apresentação para uma vaga de analista",
        "cria uma história curta de ficção científica", "explica a lógica por trás desse algoritmo",
    ]
    for _ in range(9):
        for m in modelos_forte:
            put(rng.choice(pre) + m.format(a=rng.choice(_ASSUNTOS), c=rng.choice(_CODIGO),
                                           t=rng.choice(_TEMAS)), "forte")
    # delegar: objetivos de vários passos com ferramentas diferentes ───────────
    modelos_delegar = [
        "pesquisa os 3 melhores {t}, compara e salva num arquivo na área de trabalho",
        "procura as últimas notícias sobre {t}, resume e escreve um relatório",
        "pesquisa preços de {t} em várias lojas, faz uma tabela e salva",
        "busca informações sobre {t}, compara as opções e me manda um resumo salvo em um documento",
        "descobre o clima de amanhã, olha minhas notas e monta um plano para o dia",
        "pesquisa sobre {t}, depois escreve um texto e salva no meu computador",
        "faz uma pesquisa completa de {t}, organiza os resultados e cria uma planilha",
        "primeiro pesquisa {t}, depois compara, e por fim salva o resultado em um arquivo",
        "cria um projeto com {c}, escreve a documentação e salva tudo numa pasta",
        "pesquisa {t}, lê os artigos mais relevantes e prepara um resumo com as fontes",
        "monta um relatório sobre {t} com pesquisa na web e salva em um arquivo",
        "pesquisa {t} e também {u}, compara os dois e escreve a conclusão num arquivo",
        "research the 3 best {e}, compare them and save the result to a file",
        "look up the latest news about {e}, summarize it and write a report",
        "search prices for {e} in several stores, build a table and save it",
        "find information about {e} then write an article and save it on my desktop",
        "pega os dados dessa pasta, analisa, escreve um relatório e salva ao lado",
        "estuda {t}, compara com {u} e me entrega um documento com recomendação final",
    ]
    for _ in range(8):
        for m in modelos_delegar:
            put(rng.choice(pre) + m.format(t=rng.choice(_TEMAS), u=rng.choice(_TEMAS),
                                           c=rng.choice(_CODIGO), e=rng.choice(_TEMAS_EN)), "delegar")
    return X, Y


# ══════════════════════════════════════════════════════════════════════════════
# Features
# ══════════════════════════════════════════════════════════════════════════════

_RE_PASSOS = re.compile(r"\b(depois|em seguida|então|por fim|primeiro|e também|e tamb[eé]m|and then|after that|"
                        r"then|finally|first)\b", re.I)
_RE_SALVAR = re.compile(r"\b(salva|salvar|salve|arquivo|planilha|relat[oó]rio|documento|pasta|tabela|"
                        r"save|file|report|spreadsheet)\b", re.I)
_RE_PESQUISA = re.compile(r"\b(pesquis\w*|procur\w*|busc\w*|descobr\w*|not[ií]cias|pre[cç]os|research|look up|"
                          r"search|find)\b", re.I)
_RE_COMPARA = re.compile(r"\b(compar\w*|melhor(es)?|prós|contras|vantagens|desvantagens|versus|pros|cons)\b", re.I)
_RE_CODIGO = re.compile(r"(```|\bdef\b|\bclass\b|\bfunção\b|\bfunction\b|\bscript\b|\bc[oó]digo\b|\bcode\b|\bbug\b|"
                        r"\bapi\b|\bprojeto\b|\btestes?\b)", re.I)
_RE_RACIOCINIO = re.compile(r"\b(explica\w*|analis\w*|resum\w*|escreve\w*|reescreve\w*|decid\w*|estrat[eé]gia|"
                            r"detalhes?|explain|analy[sz]e|summar\w*|write|essay|why|por que)\b", re.I)
N_MANUAIS = 12


def _manuais(texto: str) -> np.ndarray:
    pal = texto.split()
    return np.array([
        min(len(texto) / 220.0, 1.5),
        min(len(pal) / 35.0, 1.5),
        min(len(_RE_PASSOS.findall(texto)) / 2.0, 1.5),
        1.0 if _RE_SALVAR.search(texto) else 0.0,
        1.0 if _RE_PESQUISA.search(texto) else 0.0,
        1.0 if _RE_COMPARA.search(texto) else 0.0,
        1.0 if _RE_CODIGO.search(texto) else 0.0,
        1.0 if _RE_RACIOCINIO.search(texto) else 0.0,
        min(texto.count(",") / 4.0, 1.5),
        1.0 if "?" in texto else 0.0,
        1.0 if len(pal) <= 3 else 0.0,
        min(len(_RE_SALVAR.findall(texto)) + len(_RE_PESQUISA.findall(texto)) + len(_RE_COMPARA.findall(texto)), 4) / 4.0,
    ], np.float32)


# ══════════════════════════════════════════════════════════════════════════════
# A rede: (512 embedding + 12 sinais) → 48 → 3
# ══════════════════════════════════════════════════════════════════════════════

class _Rede:
    def __init__(self, n_in: int, n_hid: int = 48, n_out: int = 3, seed: int = 3):
        rng = np.random.default_rng(seed)
        self.W1 = (rng.normal(0, np.sqrt(2.0 / n_in), (n_in, n_hid))).astype(np.float32)
        self.b1 = np.zeros(n_hid, np.float32)
        self.W2 = (rng.normal(0, np.sqrt(2.0 / n_hid), (n_hid, n_out))).astype(np.float32)
        self.b2 = np.zeros(n_out, np.float32)
        self._m = [np.zeros_like(p) for p in self.params]
        self._v = [np.zeros_like(p) for p in self.params]
        self._t = 0

    @property
    def params(self):
        return [self.W1, self.b1, self.W2, self.b2]

    def proba(self, X: np.ndarray) -> np.ndarray:
        h = np.maximum(0.0, X @ self.W1 + self.b1)
        z = h @ self.W2 + self.b2
        z = z - z.max(axis=1, keepdims=True)
        e = np.exp(z)
        return e / e.sum(axis=1, keepdims=True)

    def passo(self, X, y, w, lr=3e-3, l2=1e-4, drop=0.15, rng=None) -> float:
        h = np.maximum(0.0, X @ self.W1 + self.b1)
        if drop and rng is not None:
            m = (rng.random(h.shape) > drop).astype(np.float32) / (1 - drop)
            hd = h * m
        else:
            m, hd = None, h
        z = hd @ self.W2 + self.b2
        z = z - z.max(axis=1, keepdims=True)
        p = np.exp(z); p /= p.sum(axis=1, keepdims=True)
        n = len(X)
        perda = float(-(w * np.log(p[np.arange(n), y] + 1e-9)).sum() / w.sum())
        dz = p.copy(); dz[np.arange(n), y] -= 1.0
        dz *= (w / w.sum())[:, None]
        gW2 = hd.T @ dz + l2 * self.W2
        gb2 = dz.sum(0)
        dh = dz @ self.W2.T
        if m is not None:
            dh *= m
        dh *= (h > 0)
        gW1 = X.T @ dh + l2 * self.W1
        gb1 = dh.sum(0)
        self._t += 1
        for i, (p_, g) in enumerate(zip(self.params, [gW1, gb1, gW2, gb2])):
            self._m[i] = 0.9 * self._m[i] + 0.1 * g
            self._v[i] = 0.999 * self._v[i] + 0.001 * g * g
            mh = self._m[i] / (1 - 0.9 ** self._t)
            vh = self._v[i] / (1 - 0.999 ** self._t)
            p_ -= (lr * mh / (np.sqrt(vh) + 1e-8)).astype(np.float32)
        return perda


# ══════════════════════════════════════════════════════════════════════════════
# O roteador
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Decisao:
    rota: str                  # rapido | forte | delegar
    confianca: float           # probabilidade da rota escolhida
    dificuldade: float         # 0 (trivial) … 1 (objetivo de vários passos)
    motivo: str = ""

    @property
    def tier(self) -> str:
        """Nível para core/gemini.py: 'fast' ou 'smart' (delegar usa o forte)."""
        return "fast" if self.rota == "rapido" else "smart"


class Roteador:
    def __init__(self, arquivo: Path | None = None):
        self._arquivo = arquivo or ARQUIVO
        self._trava = threading.RLock()
        self._pronto = False
        self._emb = E.EmbedderHash()
        self._rede: _Rede | None = None
        self._base: tuple[list[str], list[str]] | None = None
        self._novos_desde_treino = 0
        self.aprendidos = 0
        self.decisoes = {r: 0 for r in ROTAS}

    # ── dados ──
    def _carregar_exemplos(self) -> list[dict]:
        try:
            d = json.loads(self._arquivo.read_text(encoding="utf-8"))
            if d.get("versao") == VERSAO_DADOS:
                return [e for e in d.get("exemplos", []) if e.get("rota") in ROTAS and e.get("texto")]
        except Exception:
            pass
        return []

    def _salvar_exemplos(self, ex: list[dict]) -> None:
        try:
            self._arquivo.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._arquivo.with_suffix(".tmp")
            tmp.write_text(json.dumps({"versao": VERSAO_DADOS, "exemplos": ex[-MAX_EXEMPLOS:]},
                                      ensure_ascii=False), encoding="utf-8")
            tmp.replace(self._arquivo)
        except Exception:
            pass

    def _vetor(self, textos: list[str]) -> np.ndarray:
        emb = self._emb.embed(textos)
        man = np.stack([_manuais(t) for t in textos])
        return np.concatenate([emb, man], axis=1).astype(np.float32)

    # ── treino ──
    def treinar(self, epocas: int = 70) -> None:
        with self._trava:
            if self._base is None:
                self._base = _gerar()
            Xb, Yb = self._base
            proprios = self._carregar_exemplos()
            textos = list(Xb) + [e["texto"] for e in proprios]
            rotulos = list(Yb) + [e["rota"] for e in proprios]
            pesos = [1.0] * len(Xb) + [3.0] * len(proprios)      # o que VOCÊ ensinou pesa mais
            self._emb = E.EmbedderHash()
            self._emb.ajustar(textos)
            X = self._vetor(textos)
            y = np.array([ROTAS.index(r) for r in rotulos])
            w = np.array(pesos, np.float32)
            rede = _Rede(X.shape[1])
            rng = np.random.default_rng(5)
            n = len(X)
            for ep in range(epocas):
                ordem = rng.permutation(n)
                lr = 3e-3 * (0.5 * (1 + np.cos(np.pi * ep / epocas))) + 2e-4
                for i in range(0, n, 64):
                    ix = ordem[i:i + 64]
                    rede.passo(X[ix], y[ix], w[ix], lr=lr, rng=rng)
            self._rede = rede
            self._pronto = True
            self._novos_desde_treino = 0

    def _garantir(self) -> None:
        if not self._pronto:
            with self._trava:
                if not self._pronto:
                    self.treinar()

    @property
    def pronto(self) -> bool:
        return self._pronto

    def aquecer(self) -> threading.Thread:
        t = threading.Thread(target=self._garantir, daemon=True, name="nexus-roteador-treino")
        t.start()
        return t

    # ── uso ──
    def probabilidades(self, texto: str) -> np.ndarray:
        self._garantir()
        with self._trava:
            return self._rede.proba(self._vetor([texto]))[0]

    def decidir(self, texto: str) -> Decisao:
        t = str(texto or "").strip()
        if not t or t.startswith("["):                       # mensagens do próprio app: sem rodeio
            return Decisao("rapido", 1.0, 0.0, "mensagem do app")
        if "```" in t and len(t) > 60:
            return self._registrar(Decisao("forte", 0.95, 0.6, "tem código no pedido"))
        try:
            p = self.probabilidades(t)
        except Exception as e:                               # nunca derruba o assistente
            return Decisao("forte", 0.0, 0.5, f"roteador indisponível ({type(e).__name__})")
        n_pal = len(t.split())
        if p[2] >= LIMIAR_DELEGAR and n_pal >= MIN_PALAVRAS_DELEGAR:
            d = Decisao("delegar", float(p[2]), 1.0, "objetivo de vários passos")
        else:
            # rápido só quando a rede está claramente a favor; na dúvida usa o forte
            q = p[:2] / max(float(p[:2].sum()), 1e-9)
            if q[0] >= 0.6:
                d = Decisao("rapido", float(q[0]), float(0.5 * p[1]), "pedido simples")
            else:
                d = Decisao("forte", float(q[1]), float(0.5 + 0.5 * p[2]), "pede raciocínio")
        return self._registrar(d)

    def _registrar(self, d: Decisao) -> Decisao:
        self.decisoes[d.rota] = self.decisoes.get(d.rota, 0) + 1
        return d

    # ── aprender com o uso ──
    def aprender(self, texto: str, rota: str) -> None:
        """Um exemplo novo: 'este pedido deveria ter ido para `rota`'."""
        t = str(texto or "").strip()
        if rota not in ROTAS or len(t) < 3 or t.startswith("[") or len(t) > 400:
            return
        with self._trava:
            ex = self._carregar_exemplos()
            ex = [e for e in ex if e["texto"] != t]
            ex.append({"texto": t, "rota": rota, "quando": int(time.time())})
            self._salvar_exemplos(ex)
            self.aprendidos += 1
            self._novos_desde_treino += 1
            precisa = self._pronto and self._novos_desde_treino >= RETREINAR_A_CADA
        if precisa:
            threading.Thread(target=self.treinar, daemon=True, name="nexus-roteador-retreino").start()

    def esquecer(self) -> None:
        with self._trava:
            self._salvar_exemplos([])
            self._pronto = False
            self._rede = None

    def estatisticas(self) -> dict:
        ex = self._carregar_exemplos()
        return {"pronto": self._pronto, "aprendidos": len(ex),
                "decisoes": dict(self.decisoes),
                "ensinados": {r: sum(1 for e in ex if e["rota"] == r) for r in ROTAS}}


roteador = Roteador()


# ══════════════════════════════════════════════════════════════════════════════
# Escolher o modelo (motor próprio)
# ══════════════════════════════════════════════════════════════════════════════

_CLAUDE_RAPIDO = "claude-haiku-5-5"
_CLAUDE_FORTE = "claude-sonnet-5-5"


def cerebro_para(base, cfg: dict, rota: str):
    """O CerebroLLM para a rota, com o MESMO provedor e chave do `base` e o modelo de
    `llm_model_rapido` / `llm_model_forte` da configuração. Sem isso configurado, devolve o `base`
    (nada muda para quem não ajustou) — exceto no Claude, que já usa Haiku (rápido) e Sonnet (forte)."""
    if rota == "delegar":
        rota = "forte"
    campo = "llm_model_rapido" if rota == "rapido" else "llm_model_forte"
    modelo = str((cfg or {}).get(campo) or "").strip()
    if not modelo and getattr(base, "provedor", "") == "claude":
        # 2.5 — com o Claude já vem pronto: Haiku nos pedidos simples, Sonnet nos difíceis
        modelo = _CLAUDE_RAPIDO if rota == "rapido" else _CLAUDE_FORTE
    if not modelo or modelo == getattr(base, "modelo", ""):
        return base
    cache = getattr(base, "_variantes", None)
    if cache is None:
        cache = base._variantes = {}
    if modelo not in cache:
        from core import llm_providers as L
        outro = L.CerebroLLM.__new__(L.CerebroLLM)
        outro.__dict__.update(base.__dict__)
        outro.modelo = modelo
        outro._variantes = {}
        cache[modelo] = outro
    return cache[modelo]
