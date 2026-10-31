"""Quadros Kanban (4.5.0) em arquivos Markdown no formato do plugin Kanban do Obsidian.

    "cria o quadro Casa"                          "adiciona 'trocar lâmpada' em A fazer no quadro Casa"
    "move 'trocar lâmpada' para Feito"            "mostra o quadro Casa"

Cada quadro é um .md: as colunas são "## Título" e os cartões são "- [ ] texto" (ou "- [x]" nas colunas de
concluído). Aponte a pasta para um cofre do Obsidian e os mesmos quadros aparecem lá. Por padrão ficam em
memory/kanban. O bloco "%% kanban:settings" do Obsidian é preservado ao salvar.
"""
from __future__ import annotations

import re
from pathlib import Path

from core import armazem

PASTA_PADRAO = armazem.PASTA_MEMORIA / "kanban"
COLUNAS_PADRAO = ("A fazer", "Fazendo", "Feito")
_CONCLUIDO = {"feito", "concluido", "concluído", "pronto", "done", "completo", "finalizado"}
_NOME = re.compile(r"^[\w][\w \-]{0,39}$", re.UNICODE)
MAX_CARTOES = 500
CABECALHO = "---\n\nkanban-plugin: board\n\n---\n\n"


class ErroKanban(Exception):
    pass


def pasta() -> Path:
    try:
        from core import preferences as P
        v = str(P.get("kanban_pasta") or "").strip()
    except Exception:
        v = ""
    return Path(v).expanduser() if v else PASTA_PADRAO


def validar_pasta(caminho: str) -> Path:
    p = Path(str(caminho or "").strip().strip('"')).expanduser()
    try:
        p = p.resolve()
    except OSError:
        raise ErroKanban("Caminho inválido.")
    if not p.is_dir():
        raise ErroKanban("Essa pasta não existe.")
    if p != Path.home().resolve() and not p.is_relative_to(Path.home().resolve()):
        raise ErroKanban("Só aceito pastas dentro da sua pasta de usuário.")
    return p


def _arquivo(nome: str, base: Path | None = None) -> Path:
    nome = str(nome or "").strip()
    if not _NOME.match(nome):
        raise ErroKanban("Nome de quadro inválido (use letras, números, espaço e hífen, até 40 caracteres).")
    return (base or pasta()) / f"{nome}.md"


def eh_concluida(coluna: str) -> bool:
    return armazem.norm(coluna) in {armazem.norm(x) for x in _CONCLUIDO}


def interpretar(texto: str) -> dict:
    """Markdown do Obsidian → {'colunas': [{'titulo', 'cartoes': [{'texto','feito'}]}], 'resto': bloco de ajustes}."""
    resto = ""
    i = texto.find("%% kanban:settings")
    if i >= 0:
        resto, texto = texto[i:].rstrip() + "\n", texto[:i]
    texto = re.sub(r"\A---\n.*?\n---\n", "", texto, flags=re.S)
    colunas, atual = [], None
    for linha in texto.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", linha)
        if m:
            atual = {"titulo": m.group(1), "cartoes": []}
            colunas.append(atual)
            continue
        c = re.match(r"^- \[([ xX])\]\s+(.*)$", linha)
        if c and atual is not None and c.group(2).strip():
            atual["cartoes"].append({"texto": c.group(2).strip(), "feito": c.group(1) in "xX"})
    return {"colunas": colunas, "resto": resto}


def escrever(q: dict) -> str:
    partes = [CABECALHO]
    for col in q["colunas"]:
        partes.append(f"## {col['titulo']}\n\n")
        for c in col["cartoes"]:
            partes.append(f"- [{'x' if c['feito'] or eh_concluida(col['titulo']) else ' '}] {c['texto']}\n")
        partes.append("\n")
    texto = "".join(partes)
    return texto + ("\n" + q["resto"] if q.get("resto") else "")


def novo(nome: str, colunas=COLUNAS_PADRAO, base: Path | None = None) -> Path:
    arq = _arquivo(nome, base)
    if arq.exists():
        raise ErroKanban("Esse quadro já existe.")
    arq.parent.mkdir(parents=True, exist_ok=True)
    q = {"colunas": [{"titulo": c, "cartoes": []} for c in colunas], "resto": ""}
    arq.write_text(escrever(q), encoding="utf-8")
    return arq


def carregar(nome: str, base: Path | None = None) -> dict:
    arq = _arquivo(nome, base)
    if not arq.is_file():
        raise ErroKanban(f"Não achei o quadro “{nome}”. Quadros: {', '.join(listar(base)) or 'nenhum ainda'}.")
    q = interpretar(arq.read_text(encoding="utf-8", errors="replace"))
    if not q["colunas"]:
        raise ErroKanban("Esse arquivo não parece um quadro Kanban.")
    return q


def salvar(nome: str, q: dict, base: Path | None = None) -> None:
    arq = _arquivo(nome, base)
    tmp = arq.with_suffix(".md.tmp")
    tmp.write_text(escrever(q), encoding="utf-8")
    tmp.replace(arq)


def listar(base: Path | None = None) -> list[str]:
    p = base or pasta()
    if not p.is_dir():
        return []
    achados = []
    for f in sorted(p.glob("*.md")):
        try:
            if "kanban-plugin" in f.read_text(encoding="utf-8", errors="replace")[:300]:
                achados.append(f.stem)
        except OSError:
            continue
    return achados


def _coluna(q: dict, nome: str) -> dict:
    n = armazem.norm(nome)
    for c in q["colunas"]:
        if armazem.norm(c["titulo"]) == n:
            return c
    achadas = [c for c in q["colunas"] if n and n in armazem.norm(c["titulo"])]
    if len(achadas) == 1:
        return achadas[0]
    raise ErroKanban(f"Não achei a coluna “{nome}”. Colunas: {', '.join(c['titulo'] for c in q['colunas'])}.")


def _achar_cartao(q: dict, alvo: str):
    n = armazem.norm(alvo)
    if not n:
        raise ErroKanban("Diga qual cartão.")
    todos = [(col, c) for col in q["colunas"] for c in col["cartoes"]]
    exatos = [(col, c) for col, c in todos if armazem.norm(c["texto"]) == n]
    achados = exatos or [(col, c) for col, c in todos if n in armazem.norm(c["texto"])]
    if not achados:
        raise ErroKanban(f"Não achei o cartão “{alvo}”.")
    if len(achados) > 1:
        raise ErroKanban("Mais de um cartão combina: " + "; ".join(c["texto"] for _, c in achados[:5]) + ". Seja mais específico.")
    return achados[0]


def adicionar(nome: str, texto: str, coluna: str = "", base: Path | None = None) -> str:
    texto = re.sub(r"\s+", " ", str(texto or "")).strip()[:200]
    if not texto:
        raise ErroKanban("Diga o texto do cartão.")
    q = carregar(nome, base)
    if sum(len(c["cartoes"]) for c in q["colunas"]) >= MAX_CARTOES:
        raise ErroKanban("O quadro está cheio (500 cartões).")
    col = _coluna(q, coluna) if coluna else q["colunas"][0]
    col["cartoes"].append({"texto": texto, "feito": eh_concluida(col["titulo"])})
    salvar(nome, q, base)
    return col["titulo"]


def mover(nome: str, alvo: str, coluna: str, base: Path | None = None) -> str:
    q = carregar(nome, base)
    origem, cartao = _achar_cartao(q, alvo)
    destino = _coluna(q, coluna)
    origem["cartoes"].remove(cartao)
    cartao["feito"] = eh_concluida(destino["titulo"])
    destino["cartoes"].append(cartao)
    salvar(nome, q, base)
    return destino["titulo"]


def remover(nome: str, alvo: str, base: Path | None = None) -> str:
    q = carregar(nome, base)
    origem, cartao = _achar_cartao(q, alvo)
    origem["cartoes"].remove(cartao)
    salvar(nome, q, base)
    return cartao["texto"]


def resumo(nome: str, base: Path | None = None) -> str:
    q = carregar(nome, base)
    return " | ".join(f"{c['titulo']} ({len(c['cartoes'])}): " + ("; ".join(x["texto"] for x in c["cartoes"][:6]) or "vazia") for c in q["colunas"])
