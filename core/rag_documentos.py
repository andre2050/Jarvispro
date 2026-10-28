"""
core/rag_documentos.py — memória de DOCUMENTOS com fonte citada (NEXUS Ultra 2026 3.5, RAG pessoal).

O `indice_semantico` guarda o que você DISSE ao NEXUS (notas, diário, tarefas…). Este módulo guarda
o que está nos seus ARQUIVOS: PDF, Word, PowerPoint, texto, Markdown, planilhas CSV, JSON e código.
Cada arquivo é cortado em trechos com a sua localização (página ou linha), os trechos viram vetores
(core/embeddings.py) e a busca devolve o trecho + de onde ele veio — para o NEXUS poder dizer
"segundo contrato.pdf, p. 3, …" em vez de inventar.

Privacidade (tudo opt-in):
  • Só entram as pastas que VOCÊ adicionou ("indexa a pasta Documentos/Contratos").
  • O índice fica em memory/rag_documentos.npz e a lista de pastas em memory/rag_pastas.json,
    ambos só no seu PC (fora do GitHub). Nada é enviado a ninguém para indexar ou buscar.
  • Pastas de sistema, ocultas, de dependências e do próprio NEXUS são ignoradas.

Atualizar é barato: só arquivo novo ou modificado (data + tamanho) é lido de novo; o que sumiu sai do índice.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path

import numpy as np

from core import embeddings as E

_BASE = Path(__file__).resolve().parent.parent
ARQUIVO = _BASE / "memory" / "rag_documentos.npz"
ARQ_PASTAS = _BASE / "memory" / "rag_pastas.json"
CACHE_EMAILS = _BASE / "memory" / "emails_cache"       # e-mails opt-in (core/rag_emails.py)

EXTENSOES = {
    ".txt", ".md", ".rst", ".csv", ".json", ".log",
    ".py", ".js", ".ts", ".html", ".css", ".java", ".c", ".cpp", ".cs", ".go", ".rs", ".sql", ".yml", ".yaml", ".ini",
    ".pdf", ".docx", ".pptx",
}
_IGNORAR_PASTAS = {
    "node_modules", ".git", ".venv", "venv", "env", "__pycache__", "site-packages", "_internal", "dist", "build",
    "$recycle.bin", "system volume information", "windows", "program files", "program files (x86)", "appdata",
    "backups", "updates",
}
TAMANHO_MAX_ARQUIVO = 25 * 1024 * 1024      # acima disso o arquivo é pulado
MAX_ARQUIVOS = 5000                         # teto de segurança por indexação
MAX_CARACTERES_ARQUIVO = 600_000            # texto lido de um arquivo (o resto é ignorado)
TAMANHO_TRECHO = 650                        # ~160 tokens: cabe no modelo ONNX (128 tokens) sem perder o fim
SOBREPOSICAO = 110
_TRAVA = threading.RLock()


# ── pastas escolhidas pela pessoa ────────────────────────────────────────────
def pastas_extras() -> list[str]:
    """Fontes internas lidas junto com as pastas do usuário (hoje: o cache de e-mails, só se ele ligou)."""
    return [str(CACHE_EMAILS)] if (CACHE_EMAILS / "_indice.json").is_file() else []


def listar_pastas(arq: Path | None = None) -> list[str]:
    try:
        d = json.loads(Path(arq or ARQ_PASTAS).read_text(encoding="utf-8"))
        return [str(p) for p in d.get("pastas", []) if isinstance(p, str)]
    except Exception:
        return []


def _salvar_pastas(pastas: list[str], arq: Path | None) -> None:
    arq = Path(arq or ARQ_PASTAS)
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps({"pastas": pastas}, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(arq)


def _pasta_proibida(p: Path) -> str | None:
    """Motivo para recusar uma pasta (raiz do disco, home inteira ou pasta do próprio NEXUS)."""
    p = p.resolve()
    if p == Path(p.anchor):
        return "Não indexo o disco inteiro: escolha uma pasta específica."
    if p == Path.home().resolve():
        return "Não indexo a pasta pessoal inteira: escolha uma subpasta (Documentos, por exemplo)."
    try:
        p.relative_to(_BASE.resolve())
        return "Essa é a pasta do próprio NEXUS (tem chaves e memórias). Escolha outra."
    except ValueError:
        pass
    return None


def adicionar_pasta(pasta: str, arq: Path | None = None) -> tuple[bool, str]:
    p = Path(os.path.expandvars(os.path.expanduser(str(pasta).strip().strip('"')))).resolve()
    if not p.is_dir():
        return False, f"Não achei a pasta “{pasta}”."
    motivo = _pasta_proibida(p)
    if motivo:
        return False, motivo
    atuais = listar_pastas(arq)
    if str(p) in atuais:
        return True, f"A pasta {p.name} já está na memória de documentos."
    _salvar_pastas(atuais + [str(p)], arq)
    return True, f"Pasta {p.name} adicionada à memória de documentos."


def remover_pasta(pasta: str, arq: Path | None = None) -> tuple[bool, str]:
    alvo = str(pasta).strip().strip('"').lower()
    atuais = listar_pastas(arq)
    restam = [p for p in atuais if alvo not in (p.lower(), Path(p).name.lower())]
    if len(restam) == len(atuais):
        return False, f"“{pasta}” não está na lista de pastas."
    _salvar_pastas(restam, arq)
    return True, f"Pasta {Path(pasta).name} removida; os trechos dela saem do índice na próxima atualização."


# ── leitura: cada leitor devolve [(localização, texto)] e nunca levanta erro ──
def _ler_texto(path: Path) -> list[tuple[str, str]]:
    bruto = path.read_bytes()[:MAX_CARACTERES_ARQUIVO * 3]
    for cod in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            texto = bruto.decode(cod)
            break
        except UnicodeError:
            continue
    else:
        texto = bruto.decode("utf-8", errors="ignore")
    return [("", texto[:MAX_CARACTERES_ARQUIVO])]


def _ler_pdf(path: Path) -> list[tuple[str, str]]:
    paginas: list[tuple[str, str]] = []
    total = 0
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            for i, pg in enumerate(pdf.pages, 1):
                t = pg.extract_text() or ""
                paginas.append((f"p. {i}", t))
                total += len(t)
                if total > MAX_CARACTERES_ARQUIVO:
                    break
        return paginas
    except ImportError:
        pass
    try:
        import PyPDF2
        with open(path, "rb") as f:
            for i, pg in enumerate(PyPDF2.PdfReader(f).pages, 1):
                t = pg.extract_text() or ""
                paginas.append((f"p. {i}", t))
                total += len(t)
                if total > MAX_CARACTERES_ARQUIVO:
                    break
    except Exception:
        return []
    return paginas


def _ler_docx(path: Path) -> list[tuple[str, str]]:
    from docx import Document
    doc = Document(str(path))
    partes = [p.text for p in doc.paragraphs if p.text.strip()]
    for tab in doc.tables:
        for linha in tab.rows:
            partes.append(" | ".join(c.text.strip() for c in linha.cells))
    return [("", "\n".join(partes)[:MAX_CARACTERES_ARQUIVO])]


def _ler_pptx(path: Path) -> list[tuple[str, str]]:
    from pptx import Presentation
    saida = []
    for i, slide in enumerate(Presentation(str(path)).slides, 1):
        textos = [sh.text_frame.text for sh in slide.shapes if getattr(sh, "has_text_frame", False) and sh.has_text_frame]
        saida.append((f"slide {i}", "\n".join(t for t in textos if t.strip())))
    return saida


def ler_arquivo(path: Path) -> list[tuple[str, str]]:
    """[(localização, texto)] de um arquivo; lista vazia se não der para ler (sem levantar erro)."""
    try:
        ext = path.suffix.lower()
        if ext == ".pdf":
            return _ler_pdf(path)
        if ext == ".docx":
            return _ler_docx(path)
        if ext == ".pptx":
            return _ler_pptx(path)
        return _ler_texto(path)
    except Exception as e:
        print(f"[RAG] {path.name} ignorado: {e}")
        return []


# ── corte em trechos ─────────────────────────────────────────────────────────
def cortar(texto: str, tamanho: int = TAMANHO_TRECHO, sobre: int = SOBREPOSICAO) -> list[tuple[int, str]]:
    """Corta em trechos de ~`tamanho` letras, preferindo parar no fim de parágrafo/frase.
    Devolve [(linha_inicial, trecho)] — a linha (1 = primeira) serve de localização."""
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    if not texto.strip():
        return []
    saida: list[tuple[int, str]] = []
    n, i = len(texto), 0
    while i < n:
        fim = min(n, i + tamanho)
        if fim < n:
            janela = texto[i + tamanho // 2:fim]
            corte = max(janela.rfind("\n\n"), janela.rfind(". "), janela.rfind("\n"), janela.rfind("; "))
            if corte > 0:
                fim = i + tamanho // 2 + corte + 1
        trecho = " ".join(texto[i:fim].split())
        if len(trecho) >= 25:
            saida.append((texto.count("\n", 0, i) + 1, trecho))
        if fim >= n:
            break
        i = max(fim - sobre, i + 1)
    return saida


def _assinatura(p: Path) -> str:
    st = p.stat()
    return f"{st.st_mtime_ns}:{st.st_size}"


def _arquivos(pastas: list[str]):
    vistos = 0
    for raiz in pastas:
        for dirpath, dirnames, nomes in os.walk(raiz):
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d.lower() not in _IGNORAR_PASTAS]
            for nome in nomes:
                p = Path(dirpath) / nome
                if p.suffix.lower() not in EXTENSOES or nome.startswith(("~$", ".")):
                    continue
                try:
                    if p.stat().st_size > TAMANHO_MAX_ARQUIVO or p.stat().st_size == 0:
                        continue
                except OSError:
                    continue
                yield p
                vistos += 1
                if vistos >= MAX_ARQUIVOS:
                    return


def _palavras_chave(consulta: str) -> set[str]:
    return {p for p in E.palavras(consulta) if len(p) > 2 and p not in E._STOP}


# ── índice ───────────────────────────────────────────────────────────────────
class IndiceDocumentos:
    def __init__(self, arquivo: Path | None = None, arq_pastas: Path | None = None):
        self.arquivo, self.arq_pastas = Path(arquivo or ARQUIVO), Path(arq_pastas or ARQ_PASTAS)
        self.trechos: list[dict] = []        # {id, arquivo, nome, loc, linha, texto}
        self.vetores = np.zeros((0, 1), np.float32)
        self.assinaturas: dict[str, str] = {}   # caminho -> assinatura do arquivo quando foi lido
        self.motor = ""
        self.atualizado_em = 0.0
        self._estado: dict = {}
        self._carregar()

    def _carregar(self) -> None:
        try:
            with np.load(self.arquivo, allow_pickle=False) as z:
                self.trechos = json.loads(str(z["trechos"]))
                self.vetores = z["vetores"].astype(np.float32)
                self.assinaturas = json.loads(str(z["assinaturas"]))
                self.motor = str(z["motor"])
                self.atualizado_em = float(z["quando"])
                self._estado = {k[4:]: z[k] for k in z.files if k.startswith("est_")}
        except Exception:
            self.trechos, self.vetores, self.assinaturas, self.motor = [], np.zeros((0, 1), np.float32), {}, ""

    def _salvar(self) -> None:
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.arquivo.with_suffix(".tmp.npz")
        extra = {f"est_{k}": v for k, v in self._estado.items()}
        np.savez_compressed(tmp, trechos=json.dumps(self.trechos, ensure_ascii=False), vetores=self.vetores,
                            assinaturas=json.dumps(self.assinaturas, ensure_ascii=False),
                            motor=self.motor, quando=self.atualizado_em, **extra)
        tmp.replace(self.arquivo)

    def atualizar(self, preferir: str = "auto", forcar: bool = False, pastas: list[str] | None = None) -> dict:
        """Lê só o que mudou. Devolve {arquivos, trechos, novos_arquivos, alterados, removidos, motor}."""
        with _TRAVA:
            pastas = pastas if pastas is not None else listar_pastas(self.arq_pastas) + pastas_extras()
            emb = E.get_embedder(preferir)
            motor_mudou = forcar or emb.nome != self.motor
            atuais = {str(p): p for p in _arquivos(pastas)}
            antigas = {} if motor_mudou else self.assinaturas

            removidos = [c for c in antigas if c not in atuais]
            novos = [c for c in atuais if c not in antigas]
            alterados = [c for c in atuais if c in antigas and _assinatura(atuais[c]) != antigas[c]]
            a_ler = set(novos) | set(alterados)

            mantidos = [i for i, t in enumerate(self.trechos)
                        if not motor_mudou and t["arquivo"] in atuais and t["arquivo"] not in a_ler]
            trechos_novos: list[dict] = []
            assinaturas = {c: antigas[c] for c in atuais if c in antigas and c not in a_ler}
            for c in (atuais if motor_mudou else a_ler):
                p = atuais[c]
                for loc, texto in ler_arquivo(p):
                    for linha, trecho in cortar(texto):
                        tid = hashlib.sha1(f"{c}|{loc}|{linha}|{trecho[:80]}".encode()).hexdigest()[:16]
                        trechos_novos.append({"id": tid, "arquivo": c, "nome": p.name, "loc": loc or f"linha {linha}",
                                              "linha": linha, "texto": trecho})
                try:
                    assinaturas[c] = _assinatura(p)
                except OSError:
                    pass

            total_final = len(mantidos) + len(trechos_novos)
            if emb.nome == "hash":
                # o IDF do motor hash depende do corpus: refaz tudo quando ele muda bastante
                refazer = motor_mudou or abs(total_final - len(self.trechos)) > max(40, len(self.trechos) // 4)
                if refazer:
                    todos = [self.trechos[i]["texto"] for i in mantidos] + [t["texto"] for t in trechos_novos]
                    emb.ajustar(todos)
                    vet_mant = emb.embed([self.trechos[i]["texto"] for i in mantidos]) if mantidos else None
                else:
                    if self._estado:
                        emb.carregar_estado(self._estado)
                    vet_mant = self.vetores[mantidos] if mantidos else None
            else:
                vet_mant = self.vetores[mantidos] if mantidos else None
            vet_novos = emb.embed([t["texto"] for t in trechos_novos]) if trechos_novos else None

            partes = [v for v in (vet_mant, vet_novos) if v is not None]
            self.vetores = np.concatenate(partes) if partes else np.zeros((0, 1), np.float32)
            self.trechos = [self.trechos[i] for i in mantidos] + trechos_novos
            self.assinaturas = assinaturas
            self.motor = emb.nome
            self._estado = emb.estado()
            self.atualizado_em = time.time()
            self._salvar()
            return {"arquivos": len(self.assinaturas), "trechos": len(self.trechos),
                    "novos_arquivos": len(novos), "alterados": len(alterados), "removidos": len(removidos),
                    "motor": emb.nome}

    def buscar(self, consulta: str, k: int = 5, minimo: float | None = None, pasta: str = "") -> list[tuple[float, dict]]:
        """[(pontuação, trecho)] — sentido (vetores) + um empurrão para trechos com as palavras exatas.
        `pasta`: restringe a arquivos cujo caminho contém esse texto."""
        with _TRAVA:
            if not self.trechos or not str(consulta).strip():
                return []
            emb = E.get_embedder("onnx" if self.motor == "onnx" else "hash")
            if emb.nome != self.motor:
                return []                          # índice de outro motor: precisa atualizar
            if emb.nome == "hash" and self._estado:
                emb.carregar_estado(self._estado)
            q = emb.embed([consulta])[0]
            if minimo is None:
                minimo = 0.30 if emb.nome == "onnx" else 0.20
            chaves = _palavras_chave(consulta)
            filtro = pasta.strip().lower()
            candidatos = E.cosseno_top(q, self.vetores, k=min(len(self.trechos), max(k * 8, 40)))
            saida = []
            for i, s in candidatos:
                t = self.trechos[i]
                if filtro and filtro not in t["arquivo"].lower():
                    continue
                if chaves:
                    palavras_trecho = set(E.palavras(t["texto"]))
                    s += 0.12 * len(chaves & palavras_trecho) / len(chaves)
                if s >= minimo:
                    saida.append((s, t))
            saida.sort(key=lambda x: -x[0])
            return self._variar(saida, k)

    @staticmethod
    def _variar(achados: list[tuple[float, dict]], k: int) -> list[tuple[float, dict]]:
        """No máximo 2 trechos por arquivo no começo da lista, para uma fonte só não ocupar tudo."""
        por_arquivo: dict[str, int] = {}
        escolhidos, resto = [], []
        for s, t in achados:
            if por_arquivo.get(t["arquivo"], 0) < 2:
                por_arquivo[t["arquivo"]] = por_arquivo.get(t["arquivo"], 0) + 1
                escolhidos.append((s, t))
            else:
                resto.append((s, t))
        return (escolhidos + resto)[:k]


_indice: IndiceDocumentos | None = None


def indice() -> IndiceDocumentos:
    global _indice
    if _indice is None:
        _indice = IndiceDocumentos()
    return _indice


def citacao(t: dict) -> str:
    """'contrato.pdf, p. 3' — a fonte como o NEXUS deve citar."""
    if str(t["nome"]).startswith("E-mail de "):
        return re.sub(r" #\d+\.txt$", "", t["nome"])           # “E-mail de Ana · Reunião · 12-10”
    return f"{t['nome']}, {t['loc']}"
