"""
core/embeddings.py — transformar texto em vetores para comparar SENTIDO (NEXUS Pro 2.3).

Dois motores, mesma interface (``embed(lista_de_textos) -> matriz float32 normalizada``):

  hash   Sempre disponível, só NumPy, instantâneo, nada é baixado.
         Letras (n-gramas de 3 a 5 dentro de cada palavra), palavras, pares de palavras e
         "conceitos" (grana/dinheiro/reais → @dinheiro; mercado/supermercado/compras →
         @compras…), com peso IDF aprendido do seu próprio texto. Entende erro de digitação,
         plural, acento e os sinônimos mais comuns do dia a dia. NÃO entende sinônimo raro.

  onnx   Opcional, muito mais esperto: um modelo multilíngue pequeno (MiniLM, ~120 MB
         quantizado) rodando no seu PC com onnxruntime. Entende paráfrase de verdade
         ("preciso de um lugar para dormir em Recife" ≈ "hotel no Recife"). É baixado uma
         única vez por ``baixar_modelo()`` (ação memoria_semantica › install_model) e depois
         roda offline. Se faltar o modelo ou o onnxruntime, o NEXUS fica no motor hash.

Nada sai do computador, a não ser o download único do modelo.
"""
from __future__ import annotations

import math
import re
import threading
import unicodedata
import zlib
from pathlib import Path
from typing import Callable

import numpy as np

_BASE = Path(__file__).resolve().parent.parent
PASTA_MODELO = _BASE / "memory" / "modelos" / "minilm"
_URL_BASE = "https://huggingface.co/Xenova/paraphrase-multilingual-MiniLM-L12-v2/resolve/main/"
_ARQUIVOS_MODELO = {"model_quantized.onnx": "onnx/model_quantized.onnx", "tokenizer.json": "tokenizer.json"}
_TAMANHO_MIN_MODELO = 20_000_000          # abaixo disso o download veio incompleto/errado

DIM_HASH = 512

_STOP = frozenset("""
a o as os um uma uns umas de do da dos das em no na nos nas por para pra com sem sobre entre ate ao aos
e ou mas que se eu tu ele ela nos eles elas meu minha meus minhas seu sua seus suas me te lhe isso isto
esse essa esses essas este esta estes estas aquele aquela ja foi ser sao era tem tinha ter vai vou fui
the of and to in is it for on with at by an be this that my your i you he she we they
""".split())

# conceitos: palavras (sem acento) que apontam para o mesmo assunto
_CONCEITOS = {
    "dinheiro": "dinheiro grana din reais real rs gasto gastos gastei gastar pagar paguei pagamento conta contas "
                "boleto fatura salario renda custa custou preco caro barato orcamento financas money cash pay",
    "compras": "mercado supermercado compras comprar comprei feira padaria acougue hortifruti shopping loja lista",
    "comida": "comida comer almoco jantar cafe lanche restaurante pizza hamburguer ifood fome refeicao receita cozinhar food eat",
    "saude": "saude medico medica dentista consulta exame remedio remedios farmacia dor hospital doutor clinica health doctor",
    "exercicio": "exercicio exercicios fisico fisica treino treinei treinar academia corrida correr corri corro corremos caminhada caminhei "
                 "musculacao esporte pedalar pedalei nadar nadei yoga km parque workout gym run",
    "transporte": "uber taxi onibus metro carro moto gasolina combustivel estacionamento viagem passagem trem aviao voo bus car",
    "casa": "casa apartamento aluguel condominio luz energia agua internet reforma moradia limpeza home rent",
    "trabalho": "trabalho reuniao projeto cliente chefe empresa prazo entrega relatorio escritorio emprego work meeting job",
    "estudo": "estudo estudar prova faculdade curso aula escola livro ler leitura tarefa trabalho exame study exam class",
    "familia": "mae pai irmao irma filho filha esposa marido namorada namorado avo avo tio tia primo prima familia family",
    "viagem": "viagem viajar hotel hospedagem passagem voo aeroporto turismo ferias pousada trip travel vacation flight",
    "tempo": "amanha hoje ontem semana mes ano horario hora data prazo agenda compromisso calendario schedule",
    "lembrar": "lembrar lembrete lembra anotar anota nota esquecer recordar aviso avisar remember reminder note",
    "tecnologia": "computador pc notebook celular telefone app aplicativo programa software internet wifi tech phone",
    "lazer": "filme serie musica show jogo jogar cinema festa passeio video youtube diversao movie game fun",
    "dormir": "dormir sono cama descansar insonia acordar noite sleep rest bed",
    "humor_bom": "feliz alegre animado otimo bom contente aliviado orgulhoso tranquilo happy great good",
    "humor_ruim": "triste cansado estressado ansioso preocupado mal chateado irritado esgotado sad tired stressed worried",
    "pessoa": "amigo amiga colega pessoa contato aniversario parabens friend",
    "casa_inteligente": "luz lampada tomada cortina fechadura portao ar condicionado sala quarto cozinha light lamp lock",
}
_PALAVRA_PARA_CONCEITO: dict[str, list[str]] = {}
for _c, _ps in _CONCEITOS.items():
    for _p in _ps.split():
        _PALAVRA_PARA_CONCEITO.setdefault(_p, []).append("@" + _c)


def sem_acento(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def palavras(t: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", sem_acento(t))


def _h(chave: str, dim: int) -> tuple[int, float]:
    v = zlib.crc32(chave.encode("utf-8"))
    return v % dim, (1.0 if (v >> 31) & 1 else -1.0)


class EmbedderHash:
    """Vetores por hashing de letras/palavras/conceitos (sem modelo, sem rede)."""
    nome = "hash"

    def __init__(self, dim: int = DIM_HASH):
        self.dim = dim
        self.idf: np.ndarray | None = None          # peso por posição do vetor, aprendido do corpus

    def _bruto(self, texto: str) -> np.ndarray:
        v = np.zeros(self.dim, np.float32)
        ps = [p for p in palavras(texto) if p not in _STOP]
        if not ps:
            ps = palavras(texto)
        cont: dict[str, float] = {}

        def add(chave: str, peso: float) -> None:
            cont[chave] = cont.get(chave, 0.0) + peso

        for i, p in enumerate(ps):
            add("w:" + p, 1.0)
            for c in _PALAVRA_PARA_CONCEITO.get(p, ()):
                add("c:" + c, 1.4)
            if len(p) >= 6:
                add("s:" + p[:5], 0.5)               # raiz grosseira: conjugações e plurais se encontram
            if len(p) >= 3:
                s = f"<{p}>"
                for n in (3, 4, 5):
                    for k in range(len(s) - n + 1):
                        add(f"g{n}:" + s[k:k + n], 0.3)
            if i + 1 < len(ps):
                add("b:" + p + "_" + ps[i + 1], 0.6)
        for chave, peso in cont.items():
            idx, sinal = _h(chave, self.dim)
            v[idx] += sinal * ((1.0 + math.log(peso)) if peso > 1 else peso)
        return v

    def ajustar(self, corpus: list[str]) -> None:
        """Aprende o IDF do corpus: o que aparece em todo texto pesa menos."""
        n = len(corpus)
        if n < 8:
            self.idf = None
            return
        df = np.zeros(self.dim, np.float32)
        for t in corpus:
            df += (np.abs(self._bruto(t)) > 0)
        self.idf = (np.log((n + 1.0) / (df + 1.0)) + 1.0).astype(np.float32)

    def embed(self, textos: list[str]) -> np.ndarray:
        M = np.stack([self._bruto(t) for t in textos]) if textos else np.zeros((0, self.dim), np.float32)
        if self.idf is not None:
            M = M * self.idf
        n = np.linalg.norm(M, axis=1, keepdims=True)
        return (M / np.maximum(n, 1e-9)).astype(np.float32)

    # persistência do IDF junto com o índice
    def estado(self) -> dict:
        return {"idf": self.idf} if self.idf is not None else {}

    def carregar_estado(self, d: dict) -> None:
        self.idf = d.get("idf")


class EmbedderOnnx:
    """MiniLM multilíngue em ONNX (opcional). Pooling pela média, vetor normalizado."""
    nome = "onnx"
    dim = 384

    def __init__(self, pasta: Path = PASTA_MODELO, max_tokens: int = 128):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.tok = Tokenizer.from_file(str(pasta / "tokenizer.json"))
        self.tok.enable_truncation(max_length=max_tokens)
        self.tok.enable_padding(pad_id=self.tok.token_to_id("<pad>") or 1, pad_token="<pad>")
        self.sess = ort.InferenceSession(str(pasta / "model_quantized.onnx"),
                                         providers=["CPUExecutionProvider"])
        self.entradas = {i.name for i in self.sess.get_inputs()}
        self._trava = threading.Lock()

    def embed(self, textos: list[str]) -> np.ndarray:
        if not textos:
            return np.zeros((0, self.dim), np.float32)
        saidas = []
        for i in range(0, len(textos), 32):
            lote = [t if str(t).strip() else "." for t in textos[i:i + 32]]
            enc = self.tok.encode_batch(lote)
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
            feed = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in self.entradas:
                feed["token_type_ids"] = np.zeros_like(ids)
            with self._trava:
                oculto = self.sess.run(None, feed)[0]                  # (n, seq, 384)
            m = mask[..., None].astype(np.float32)
            media = (oculto * m).sum(1) / np.maximum(m.sum(1), 1e-9)
            saidas.append(media)
        M = np.concatenate(saidas).astype(np.float32)
        return M / np.maximum(np.linalg.norm(M, axis=1, keepdims=True), 1e-9)

    def estado(self) -> dict:
        return {}

    def carregar_estado(self, d: dict) -> None:
        pass


# ── escolha e instalação do motor ────────────────────────────────────────────
def modelo_instalado(pasta: Path = PASTA_MODELO) -> bool:
    try:
        return all((pasta / n).exists() and (pasta / n).stat().st_size > 1000 for n in _ARQUIVOS_MODELO) and \
            (pasta / "model_quantized.onnx").stat().st_size >= _TAMANHO_MIN_MODELO
    except OSError:
        return False


def onnx_disponivel() -> bool:
    import importlib.util
    return all(importlib.util.find_spec(m) is not None for m in ("onnxruntime", "tokenizers"))


_cache: dict[str, object] = {}
_trava_cache = threading.Lock()


def get_embedder(preferir: str = "auto"):
    """'hash', 'onnx' ou 'auto' (onnx se estiver instalado e funcionando; senão hash)."""
    with _trava_cache:
        if preferir in ("auto", "onnx") and modelo_instalado() and onnx_disponivel():
            if "onnx" not in _cache:
                try:
                    _cache["onnx"] = EmbedderOnnx()
                except Exception as e:
                    print(f"[Embeddings] modelo ONNX não carregou ({e}) — usando o motor hash")
                    _cache["onnx"] = None
            if _cache.get("onnx") is not None:
                return _cache["onnx"]
        if "hash" not in _cache:
            _cache["hash"] = EmbedderHash()
        return _cache["hash"]


def baixar_modelo(log: Callable[[str], None] = print, pasta: Path = PASTA_MODELO) -> tuple[bool, str]:
    """Baixa o MiniLM multilíngue (uma vez). Precisa de internet, de onnxruntime e de tokenizers."""
    if not onnx_disponivel():
        return False, "Faltam os pacotes onnxruntime e tokenizers (pip install onnxruntime tokenizers)."
    import requests
    pasta.mkdir(parents=True, exist_ok=True)
    try:
        for destino, caminho in _ARQUIVOS_MODELO.items():
            alvo = pasta / destino
            if alvo.exists() and alvo.stat().st_size > 1000:
                continue
            log(f"Baixando {destino}…")
            tmp = alvo.with_suffix(alvo.suffix + ".part")
            with requests.get(_URL_BASE + caminho, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for bloco in r.iter_content(1 << 20):
                        f.write(bloco)
            tmp.replace(alvo)
        if not modelo_instalado(pasta):
            return False, "O download terminou, mas o arquivo do modelo parece incompleto."
        with _trava_cache:
            _cache.pop("onnx", None)
        EmbedderOnnx(pasta).embed(["teste"])
        return True, "Modelo de sentido instalado."
    except Exception as e:
        return False, f"Não consegui baixar o modelo: {e}"


def cosseno_top(consulta: np.ndarray, matriz: np.ndarray, k: int = 5) -> list[tuple[int, float]]:
    """Índices e similaridades (vetores já normalizados) dos k mais parecidos."""
    if matriz.shape[0] == 0:
        return []
    s = matriz @ consulta
    k = min(k, len(s))
    idx = np.argpartition(-s, k - 1)[:k]
    idx = idx[np.argsort(-s[idx])]
    return [(int(i), float(s[i])) for i in idx]
