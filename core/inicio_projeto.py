"""Iniciar um projeto com uma frase (NEXUS Ultra 2026 3.4).

"Nexus, inicia o projeto Loja Virtual em Python"  →
  1. PASTA        Área de Trabalho/Projetos NEXUS/Loja Virtual, com README.md, NOTAS.md, .gitignore e as
                  subpastas do tipo (Python: src/ e tests/; site: css/ e js/…). Pasta que já existe não é
                  apagada nem sobrescrita: só ganha o que faltar.
  2. EDITOR       abre a pasta no VS Code (ou no editor que você pedir; sem editor, no Explorador).
  3. DOCUMENTAÇÃO abre a documentação oficial da tecnologia (Python, MDN, React, Django…).
  4. TEMPO        começa a contar o tempo do projeto (memory/tempo_projetos.json). "Para o tempo" encerra;
                  "quanto tempo trabalhei na Loja Virtual?" soma hoje, a semana e o total.
  5. PRÓXIMO PASSO registra o projeto na sua lista de projetos e PERGUNTA qual é o próximo passo.

Iniciar outro projeto encerra o tempo do anterior (só um relógio corre por vez).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

from core import armazem
from core.protecao import engolida as _engolida

ARQ_TEMPO = armazem.PASTA_MEMORIA / "tempo_projetos.json"


def pasta_base() -> Path:
    desk = Path.home() / "Desktop"
    if not desk.exists() and (Path.home() / "Área de Trabalho").exists():
        desk = Path.home() / "Área de Trabalho"
    return desk / "Projetos NEXUS"


# ── tipo e documentação ──────────────────────────────────────────────────────
DOCS = {
    "python": "https://docs.python.org/pt-br/3/",
    "django": "https://docs.djangoproject.com/pt-br/stable/",
    "flask": "https://flask.palletsprojects.com/",
    "fastapi": "https://fastapi.tiangolo.com/pt/",
    "javascript": "https://developer.mozilla.org/pt-BR/docs/Web/JavaScript",
    "typescript": "https://www.typescriptlang.org/docs/",
    "node": "https://nodejs.org/docs/latest/api/",
    "react": "https://react.dev/learn",
    "vue": "https://vuejs.org/guide/introduction.html",
    "web": "https://developer.mozilla.org/pt-BR/docs/Web/HTML",
    "java": "https://docs.oracle.com/en/java/",
    "csharp": "https://learn.microsoft.com/pt-br/dotnet/csharp/",
    "unity": "https://docs.unity3d.com/Manual/index.html",
    "godot": "https://docs.godotengine.org/pt-br/stable/",
    "rust": "https://doc.rust-lang.org/book/",
    "go": "https://go.dev/doc/",
    "flutter": "https://docs.flutter.dev/",
    "kotlin": "https://kotlinlang.org/docs/home.html",
    "php": "https://www.php.net/manual/pt_BR/",
    "cpp": "https://en.cppreference.com/w/",
}
_APELIDOS = {"py": "python", "js": "javascript", "nodejs": "node", "node.js": "node", "ts": "typescript",
             "html": "web", "css": "web", "site": "web", "website": "web", "pagina": "web", "c#": "csharp",
             "dotnet": "csharp", ".net": "csharp", "c++": "cpp", "golang": "go", "dart": "flutter",
             "reactjs": "react", "vuejs": "vue"}

_ESTRUTURA = {
    "python": ("src", "tests"), "django": ("src", "tests"), "flask": ("src", "templates", "static"),
    "fastapi": ("src", "tests"), "web": ("css", "js", "img"), "javascript": ("src",), "typescript": ("src",),
    "node": ("src",), "react": ("src", "public"), "vue": ("src", "public"),
}
_FAMILIA_GITIGNORE = {"django": "python", "flask": "python", "fastapi": "python", "javascript": "node",
                      "typescript": "node", "react": "node", "vue": "node"}
_GITIGNORE = {
    "python": "__pycache__/\n*.pyc\n.venv/\nvenv/\n.env\n",
    "node": "node_modules/\ndist/\n.env\n",
    "web": ".DS_Store\nThumbs.db\n",
}


def normalizar_tipo(valor: str) -> str:
    t = armazem.norm(valor).replace(" ", "")
    if not t:
        return ""
    if t in DOCS:
        return t
    if t in _APELIDOS:
        return _APELIDOS[t]
    for chave in list(DOCS) + list(_APELIDOS):            # "um site em react" → react
        if armazem.norm(chave) in armazem.norm(valor).split():
            return _APELIDOS.get(chave, chave)
    return t[:30]


def url_documentacao(tipo: str) -> str:
    tipo = normalizar_tipo(tipo)
    if tipo in DOCS:
        return DOCS[tipo]
    from urllib.parse import quote_plus
    return "https://www.google.com/search?q=" + quote_plus(f"documentação oficial {tipo or 'programação'}")


# ── 1. pasta ─────────────────────────────────────────────────────────────────
def nome_de_pasta(nome: str) -> str:
    limpo = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", str(nome or "")).strip(" .")
    return " ".join(limpo.split())[:60] or f"Projeto {datetime.now():%Y-%m-%d}"


def criar_pasta(nome: str, tipo: str = "", base: Path | None = None, objetivo: str = "") -> tuple[Path, list[str]]:
    """Cria (ou completa) a pasta do projeto. Devolve (pasta, o que foi criado). Nunca sobrescreve arquivo."""
    tipo = normalizar_tipo(tipo)
    pasta = (base or pasta_base()) / nome_de_pasta(nome)
    criados: list[str] = []
    if not pasta.exists():
        criados.append(pasta.name + "/")
    pasta.mkdir(parents=True, exist_ok=True)
    for sub in _ESTRUTURA.get(tipo, ("docs",)):
        if not (pasta / sub).exists():
            (pasta / sub).mkdir()
            criados.append(sub + "/")
    hoje = datetime.now().strftime("%d/%m/%Y")
    arquivos = {
        "README.md": (f"# {nome_de_pasta(nome)}\n\nCriado em {hoje} pelo NEXUS Ultra 2026."
                      + (f"\n\n## Objetivo\n\n{objetivo}\n" if objetivo else "\n")
                      + (f"\n## Tecnologia\n\n{tipo}\n\nDocumentação: {url_documentacao(tipo)}\n" if tipo else "")),
        "NOTAS.md": f"# Notas — {nome_de_pasta(nome)}\n\n## {hoje}\n\n- Projeto iniciado.\n",
        ".gitignore": _GITIGNORE.get(_FAMILIA_GITIGNORE.get(tipo, tipo), ".env\n"),
    }
    for arq, conteudo in arquivos.items():
        if not (pasta / arq).exists():
            (pasta / arq).write_text(conteudo, encoding="utf-8")
            criados.append(arq)
    return pasta, criados


# ── 2. editor ────────────────────────────────────────────────────────────────
def _vscode() -> str:
    achado = shutil.which("code")
    if achado:
        return achado
    for var, resto in (("LOCALAPPDATA", ("Programs", "Microsoft VS Code", "Code.exe")),
                       ("ProgramFiles", ("Microsoft VS Code", "Code.exe"))):
        raiz = os.environ.get(var, "")
        if raiz and Path(raiz, *resto).exists():
            return str(Path(raiz, *resto))
    return ""


def abrir_editor(pasta: Path, editor: str = "") -> str:
    """Abre a pasta no editor. Devolve o nome do que abriu ('' se nada abriu)."""
    ed = armazem.norm(editor)
    if not ed or "code" in ed or "vs" in ed:
        exe = _vscode()
        if exe:
            try:
                subprocess.Popen([exe, str(pasta)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 shell=False)
                return "VS Code"
            except Exception:
                _engolida("core/inicio_projeto.py:160")
    elif editor:
        try:
            from actions.open_app import launch_direct
            if launch_direct(editor):
                return editor
        except Exception:
            _engolida("core/inicio_projeto.py:167")
    try:                                                     # último recurso: a pasta no Explorador
        if sys.platform == "win32":
            os.startfile(str(pasta))                         # type: ignore[attr-defined]
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(pasta)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "explorador de arquivos"
    except Exception:
        return ""


def abrir_documentacao(tipo: str) -> str:
    url = url_documentacao(tipo)
    try:
        webbrowser.open(url)
        return url
    except Exception:
        return ""


# ── 4. tempo ─────────────────────────────────────────────────────────────────
def _tempo() -> dict:
    return armazem.carregar(ARQ_TEMPO, {})


def iniciar_tempo(nome: str, agora: float | None = None) -> str | None:
    """Começa a contar o tempo de ``nome``. Encerra (e devolve o nome de) outro relógio que estava correndo."""
    agora = agora or time.time()
    d = _tempo()
    encerrado = None
    for proj, info in d.items():
        sess = info.get("sessoes") or []
        if sess and sess[-1][1] is None:
            if proj == nome:
                return None                                   # já está contando
            sess[-1][1] = agora
            encerrado = proj
    d.setdefault(nome, {"sessoes": []})["sessoes"].append([agora, None])
    armazem.salvar(ARQ_TEMPO, d)
    return encerrado


def parar_tempo(agora: float | None = None) -> tuple[str, float] | None:
    """Para o relógio que estiver correndo. (projeto, segundos desta sessão) ou None."""
    agora = agora or time.time()
    d = _tempo()
    for proj, info in d.items():
        sess = info.get("sessoes") or []
        if sess and sess[-1][1] is None:
            sess[-1][1] = agora
            armazem.salvar(ARQ_TEMPO, d)
            return proj, agora - sess[-1][0]
    return None


def relogio_atual() -> str:
    for proj, info in _tempo().items():
        sess = info.get("sessoes") or []
        if sess and sess[-1][1] is None:
            return proj
    return ""


def total(nome: str, agora: float | None = None) -> dict:
    """Segundos de hoje, dos últimos 7 dias e no total (a sessão aberta conta até agora)."""
    agora = agora or time.time()
    d = _tempo()
    chave = next((k for k in d if armazem.norm(k) == armazem.norm(nome)), None) or \
        next((k for k in d if armazem.norm(nome) in armazem.norm(k)), None)
    if not chave:
        return {"projeto": "", "hoje": 0.0, "semana": 0.0, "total": 0.0}
    ini_hoje = datetime.fromtimestamp(agora).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    ini_semana = (datetime.fromtimestamp(ini_hoje) - timedelta(days=6)).timestamp()
    soma = {"hoje": 0.0, "semana": 0.0, "total": 0.0}
    for a, b in d[chave].get("sessoes") or []:
        b = b or agora
        soma["total"] += max(0.0, b - a)
        soma["semana"] += max(0.0, b - max(a, ini_semana))
        soma["hoje"] += max(0.0, b - max(a, ini_hoje))
    return {"projeto": chave, **soma}


def fmt_duracao(seg: float) -> str:
    m = int(seg // 60)
    h, m = divmod(m, 60)
    if h and m:
        return f"{h} h {m} min"
    return f"{h} h" if h else f"{m} min"
