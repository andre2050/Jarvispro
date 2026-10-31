"""
core/dev_projeto.py — as partes do agente de programação que não precisam de IA (NEXUS Ultra 2026 2.1).

O agente (actions/dev_agent.py) pede à IA um plano e o código de cada arquivo. Tudo o que a IA
devolve é TEXTO NÃO CONFIÁVEL: um caminho como "../../Startup/x.bat", uma dependência como
"--index-url=http://..." ou um comando como "powershell -c ..." vindos do plano não podem ser
obedecidos às cegas. Este módulo é onde essas respostas são conferidas, e também onde o
projeto pronto é verificado SEM rodá-lo (arquivo que o HTML chama e não existe, erro de
sintaxe, função importada que não foi escrita, arquivo cortado no meio).

Não faz rede e não chama IA, por isso é totalmente testável (tests/test_dev_projeto.py).
"""
from __future__ import annotations

import ast
import difflib
import html.parser
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlparse
from core.protecao import engolida as _engolida

MAX_ARQUIVOS = 25
MAX_BYTES_ARQUIVO = 400_000
META = ".nexus_projeto.json"
BACKUPS = ".nexus_backup"

# pastas onde o agente nunca escreve
PASTAS_PROIBIDAS = frozenset({".git", ".venv", "venv", "node_modules", "__pycache__", BACKUPS})
# pastas que não entram quando se lê um projeto para alterá-lo
PASTAS_IGNORADAS = PASTAS_PROIBIDAS | {"dist", "build", ".idea", ".vscode", ".pytest_cache"}
EXT_BLOQUEADAS = frozenset({".exe", ".dll", ".msi", ".scr", ".com", ".lnk", ".reg", ".sys", ".pif"})
EXT_TEXTO = frozenset({
    ".py", ".pyw", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".html", ".htm", ".css", ".scss",
    ".json", ".md", ".txt", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".csv", ".svg", ".xml",
    ".sql", ".sh", ".bat", ".ps1", ".java", ".c", ".h", ".cpp", ".cs", ".go", ".rs", ".php", ".rb",
    ".kt", ".lua", ".vue", ".env.example", ".gitignore", "",
})

_RESERVADOS_WIN = frozenset({"con", "prn", "aux", "nul",
                             *(f"com{i}" for i in range(1, 10)),
                             *(f"lpt{i}" for i in range(1, 10))})


# ── caminhos ─────────────────────────────────────────────────────────────────

def caminho_seguro(rel, raiz: Path) -> Path | None:
    """Caminho ABSOLUTO dentro de `raiz` para o arquivo `rel` pedido pela IA, ou None se o
    pedido sair da pasta do projeto (../, C:\\, /etc, ~), usar nome reservado do Windows ou
    cair em pasta proibida (.git, .venv, node_modules…)."""
    if not isinstance(rel, str):
        return None
    r = rel.strip().replace("\\", "/")
    if not r or len(r) > 160 or "\x00" in r:
        return None
    if r.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", r):
        return None
    partes = [p for p in r.split("/") if p not in ("", ".")]
    if not partes or len(partes) > 8:
        return None
    for p in partes:
        if p == ".." or p != p.strip() or p.endswith((".", " ")):
            return None
        if re.search(r'[<>:"|?*\x00-\x1f]', p):
            return None
        if p.lower() in PASTAS_PROIBIDAS or p.split(".")[0].lower() in _RESERVADOS_WIN:
            return None
    if Path(partes[-1]).suffix.lower() in EXT_BLOQUEADAS:
        return None
    base = Path(raiz).resolve()
    destino = (base / Path(*partes)).resolve()
    if destino != base and base not in destino.parents:
        return None
    return destino


def nome_de_pasta(nome: str, padrao: str = "projeto") -> str:
    """Nome de pasta simples: sem acento, sem espaço, só [a-z0-9_-]."""
    t = unicodedata.normalize("NFKD", str(nome or "")).encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9_\-]+", "_", t).strip("_-")[:48]
    if t.lower() in _RESERVADOS_WIN:
        t = f"{t}_projeto"
    return t or padrao


# ── dependências ─────────────────────────────────────────────────────────────

_PIP_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}(\[[A-Za-z0-9_,-]{1,40}\])?"
    r"((==|>=|<=|~=|!=|>|<)[A-Za-z0-9.*]{1,20}(,(==|>=|<=|~=|!=|>|<)[A-Za-z0-9.*]{1,20})*)?$")
_NPM_RE = re.compile(
    r"^(@[a-z0-9][a-z0-9._-]{0,60}/)?[a-z0-9][a-z0-9._-]{0,60}(@[A-Za-z0-9.^~*<>=-]{1,30})?$")


def dependencia_pip(dep) -> str | None:
    """A dependência só passa se for NOME[extras]==versão. Nada de opções ("--index-url"),
    URLs, git+https, caminhos ou "-r arquivo" — o pip trataria isso como ordem."""
    d = str(dep or "").strip()
    return d if _PIP_RE.match(d) else None


def dependencia_npm(dep) -> str | None:
    d = str(dep or "").strip()
    return d if _NPM_RE.match(d) else None


# nome do `import` ≠ nome do pacote no PyPI
PACOTE_DO_IMPORT = {
    "cv2": "opencv-python", "PIL": "pillow", "bs4": "beautifulsoup4", "yaml": "pyyaml",
    "sklearn": "scikit-learn", "skimage": "scikit-image", "dotenv": "python-dotenv",
    "dateutil": "python-dateutil", "serial": "pyserial", "docx": "python-docx",
    "pptx": "python-pptx", "fitz": "pymupdf", "jwt": "pyjwt", "magic": "python-magic",
    "Crypto": "pycryptodome", "OpenSSL": "pyopenssl", "telegram": "python-telegram-bot",
    "discord": "discord.py", "flask_cors": "flask-cors", "flask_sqlalchemy": "flask-sqlalchemy",
    "win32com": "pywin32", "win32api": "pywin32", "win32gui": "pywin32", "win32con": "pywin32",
    "pythoncom": "pywin32", "usb": "pyusb", "attr": "attrs", "git": "gitpython",
    "speech_recognition": "SpeechRecognition", "pyaudio": "PyAudio", "mpl_toolkits": "matplotlib",
    "googleapiclient": "google-api-python-client", "google_auth_oauthlib": "google-auth-oauthlib",
}


def modulo_instalavel(modulo: str) -> str | None:
    """Pacote do PyPI que corresponde a um `import` que faltou, ou None quando NÃO se deve
    instalar nada: módulo da biblioteca padrão (tkinter ausente não se resolve com pip — e
    "pip install tkinter" instalaria um pacote qualquer) ou nome que não é um identificador."""
    base = str(modulo or "").split(".")[0]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,60}", base):
        return None
    if base in getattr(sys, "stdlib_module_names", ()):
        return None
    return PACOTE_DO_IMPORT.get(base, base.replace("_", "-"))


# ── comando de execução ──────────────────────────────────────────────────────

_PYTHONS = {"python", "python3", "py"}
_ARG_PROIBIDO = re.compile(r"[|&;<>$`\n\r]|(^|[/\\])\.\.([/\\]|$)|^[/\\~]|^[A-Za-z]:[/\\]")


def comando_seguro(run_command, python: str | None = None) -> list[str] | None:
    """Lista de argumentos para executar (sem shell) ou None se o comando não é permitido.

    O plano da IA traz um `run_command`; ele só vale se for rodar o PRÓPRIO projeto com
    python / node / npm start|test|run <script>. "powershell -c …", "del", "curl …", "npx"
    (baixa e roda pacote qualquer) e caminhos fora do projeto são recusados."""
    partes = str(run_command or "").split()
    if not partes or len(partes) > 12:
        return None
    exe = partes[0].lower()
    exe = exe[:-4] if exe.endswith(".exe") else exe
    args = partes[1:]
    if any(_ARG_PROIBIDO.search(a) for a in args):
        return None
    if exe in _PYTHONS:
        if not args or args[0] == "-c":
            return None
        return [python or sys.executable, *args]
    if exe == "node":
        if not args or args[0] in ("-e", "--eval", "-p", "--print"):
            return None
        return ["node", *args]
    if exe == "npm":
        if args[:1] in (["start"], ["test"]):
            return ["npm", *args[:1]]
        if len(args) == 2 and args[0] == "run" and re.fullmatch(r"[\w:-]{1,40}", args[1]):
            return ["npm", "run", args[1]]
    return None


def ambiente_limpo() -> dict[str, str]:
    """Variáveis de ambiente para o programa gerado: sem nada que pareça chave/senha/token."""
    ruim = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "CREDENTIAL", "AUTH")
    return {k: v for k, v in os.environ.items() if not any(m in k.upper() for m in ruim)}


# ── plano da IA ──────────────────────────────────────────────────────────────

def e_projeto_web(linguagem: str, entry_point: str = "", run_command: str = "") -> bool:
    lang = str(linguagem or "").strip().lower()
    ep = str(entry_point or "").lower()
    primeiro = (str(run_command or "").split() or [""])[0].lower()
    return (lang in ("html", "web", "site", "website", "css", "página", "pagina", "landing page")
            or ep.endswith((".html", ".htm")) or primeiro in ("start", "open", "xdg-open", "explorer"))


def e_projeto_node(linguagem: str, entry_point: str = "") -> bool:
    lang = str(linguagem or "").strip().lower()
    return lang in ("javascript", "js", "node", "nodejs", "node.js") or str(entry_point).lower().endswith((".js", ".mjs"))


def validar_plano(plano, raiz: Path, node: bool = False) -> dict:
    """Limpa o plano devolvido pela IA. Levanta ValueError se não sobrar nada utilizável.

    Resultado: {"project_name", "entry_point", "run_command", "files": [{path, description,
    imports}], "dependencies": [...], "descartados": [motivos]}"""
    if not isinstance(plano, dict):
        raise ValueError("o plano não é um objeto JSON")
    descartados: list[str] = []
    arquivos: list[dict] = []
    vistos: set[str] = set()
    for fi in plano.get("files") or []:
        if not isinstance(fi, dict):
            continue
        destino = caminho_seguro(fi.get("path"), raiz)
        if destino is None:
            descartados.append(f"caminho recusado: {str(fi.get('path'))[:60]!r}")
            continue
        rel = destino.relative_to(Path(raiz).resolve()).as_posix()
        if rel.lower() in vistos:
            continue
        vistos.add(rel.lower())
        imps = [str(i) for i in (fi.get("imports") or []) if isinstance(i, str)][:12]
        arquivos.append({"path": rel, "description": str(fi.get("description") or "")[:400],
                         "imports": imps})
        if len(arquivos) >= MAX_ARQUIVOS:
            descartados.append(f"mais de {MAX_ARQUIVOS} arquivos: o resto foi cortado")
            break
    if not arquivos:
        raise ValueError("o plano não trouxe nenhum arquivo válido")

    caminhos = [a["path"] for a in arquivos]
    entry = ""
    cand = plano.get("entry_point")
    if isinstance(cand, str):
        c = caminho_seguro(cand, raiz)
        if c is not None:
            rel = c.relative_to(Path(raiz).resolve()).as_posix()
            entry = next((p for p in caminhos if p.lower() == rel.lower()), "")
    if not entry:
        entry = next((p for p in caminhos if p.lower() in ("main.py", "index.html", "app.py", "main.js", "index.js")),
                     caminhos[-1])

    deps: list[str] = []
    for d in plano.get("dependencies") or []:
        ok = None if isinstance(d, dict) else (dependencia_npm(d) if node else dependencia_pip(d))
        if ok:
            deps.append(ok)
        else:
            descartados.append(f"dependência recusada: {str(d)[:50]!r}")
    return {
        "project_name": str(plano.get("project_name") or ""),
        "entry_point": entry,
        "run_command": str(plano.get("run_command") or ""),
        "files": arquivos,
        "dependencies": list(dict.fromkeys(deps))[:20],
        "descartados": descartados,
    }


def ordenar_para_escrita(arquivos: list[dict], web: bool) -> list[dict]:
    """Ordem em que os arquivos são escritos. Python: quem importa menos vem antes. Site: o
    HTML primeiro (ele define os ids e classes), depois o CSS e por fim o JS — assim os dois
    últimos são escritos olhando o HTML de verdade, e não adivinhando."""
    if web:
        peso = {".html": 0, ".htm": 0, ".css": 1, ".scss": 1, ".json": 2, ".js": 3, ".mjs": 3}
        return sorted(arquivos, key=lambda a: (peso.get(Path(a["path"]).suffix.lower(), 2),
                                               a["path"] != "index.html", a["path"]))
    return sorted(arquivos, key=lambda a: len(a.get("imports") or []))


# ── verificação sem rodar ────────────────────────────────────────────────────

class _Refs(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.refs: list[tuple[str, str]] = []

    def handle_starttag(self, tag, attrs):
        d = {k: v for k, v in attrs if v}
        if tag == "link" and d.get("href"):
            self.refs.append((tag, d["href"]))
        elif tag in ("script", "img", "source", "video", "audio", "iframe", "embed") and d.get("src"):
            self.refs.append((tag, d["src"]))
        elif tag == "video" and d.get("poster"):
            self.refs.append((tag, d["poster"]))
        elif tag == "a" and d.get("href"):
            self.refs.append((tag, d["href"]))


def _ref_local(valor: str) -> str | None:
    v = (valor or "").strip()
    if not v or v.startswith(("#", "data:", "mailto:", "tel:", "javascript:", "//", "blob:")):
        return None
    u = urlparse(v)
    if u.scheme or u.netloc:
        return None
    caminho = unquote(u.path)
    return caminho or None


def _ler(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _arquivos_do_projeto(projeto: Path, sufixos: tuple[str, ...]) -> list[Path]:
    achados = []
    for raiz, dirs, nomes in os.walk(projeto):
        dirs[:] = [d for d in dirs if d.lower() not in PASTAS_IGNORADAS]
        for n in nomes:
            if n.lower().endswith(sufixos):
                achados.append(Path(raiz) / n)
    return sorted(achados)


def _rel(projeto: Path, p: Path) -> str:
    try:
        return p.resolve().relative_to(Path(projeto).resolve()).as_posix()
    except ValueError:
        return p.name


def verificar_html(projeto: Path) -> list[dict]:
    problemas = []
    for h in _arquivos_do_projeto(projeto, (".html", ".htm")):
        texto = _ler(h)
        rel = _rel(projeto, h)
        if not texto.strip():
            problemas.append({"arquivo": rel, "tipo": "vazio", "problema": f"{rel} está vazio"})
            continue
        if "<html" in texto.lower() and "</html>" not in texto.lower():
            problemas.append({"arquivo": rel, "tipo": "cortado",
                              "problema": f"{rel} termina no meio (falta </html>) — o arquivo foi cortado"})
        if "<html" in texto.lower() and not re.search(r"<meta[^>]+charset", texto, re.I):
            # sem isto o navegador lê o arquivo local como Latin-1 e "ção" vira "Ã§Ã£o"
            problemas.append({"arquivo": rel, "tipo": "charset",
                              "problema": f'{rel} não tem <meta charset="utf-8"> no <head> '
                                          f"(os acentos aparecem quebrados no navegador)"})
        parser = _Refs()
        try:
            parser.feed(texto)
        except Exception:
            _engolida("core/dev_projeto.py:341")
        for tag, valor in parser.refs:
            local = _ref_local(valor)
            if not local:
                continue
            if tag == "a" and not local.lower().endswith((".html", ".htm")):
                continue
            alvo = (Path(projeto) / local.lstrip("/")) if local.startswith("/") else (h.parent / local)
            try:
                alvo = alvo.resolve()
            except OSError:
                continue
            if not alvo.exists():
                problemas.append({"arquivo": rel, "tipo": "ausente", "alvo": local,
                                  "problema": f"{rel} usa '{local}', mas esse arquivo não existe"})
    return problemas


def verificar_css(projeto: Path) -> list[dict]:
    problemas = []
    for c in _arquivos_do_projeto(projeto, (".css",)):
        texto = re.sub(r"/\*.*?\*/", "", _ler(c), flags=re.S)
        if texto.count("{") != texto.count("}"):
            rel = _rel(projeto, c)
            problemas.append({"arquivo": rel, "tipo": "cortado",
                              "problema": f"{rel} tem mais chaves abertas do que fechadas (ou o contrário): "
                                          f"o arquivo foi cortado ou tem erro"})
    return problemas


def verificar_json(projeto: Path) -> list[dict]:
    problemas = []
    for j in _arquivos_do_projeto(projeto, (".json",)):
        try:
            json.loads(_ler(j))
        except ValueError as e:
            rel = _rel(projeto, j)
            problemas.append({"arquivo": rel, "tipo": "sintaxe", "problema": f"{rel} não é um JSON válido ({e})"})
    return problemas


_MODULO_SEM_ERRO = re.compile(r"Cannot use import statement|Unexpected token 'export'|import\.meta|top-level await", re.I)


def verificar_js(projeto: Path) -> list[dict]:
    """`node --check` em cada .js (se o Node estiver instalado). Sintaxe de módulo ES não conta
    como erro: um script de navegador com `import` está certo, só não é CommonJS."""
    node = shutil.which("node")
    if not node:
        return []
    problemas = []
    for js in _arquivos_do_projeto(projeto, (".js", ".mjs", ".cjs")):
        try:
            r = subprocess.run([node, "--check", str(js)], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=15)
        except (OSError, subprocess.SubprocessError):
            continue
        if r.returncode != 0 and not _MODULO_SEM_ERRO.search(r.stderr or ""):
            rel = _rel(projeto, js)
            linhas = [l for l in (r.stderr or "").splitlines() if l.strip()]
            problemas.append({"arquivo": rel, "tipo": "sintaxe",
                              "problema": f"{rel}: erro de sintaxe — {' | '.join(linhas[:4])[:300]}"})
    return problemas


def _nomes_definidos(arvore: ast.AST) -> tuple[set[str], bool]:
    """Nomes do nível de módulo + True se o módulo é dinâmico (import *, __getattr__)."""
    nomes: set[str] = set()
    dinamico = False
    for no in getattr(arvore, "body", []):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nomes.add(no.name)
            if no.name == "__getattr__":
                dinamico = True
        elif isinstance(no, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            alvos = no.targets if isinstance(no, ast.Assign) else [no.target]
            for a in alvos:
                for n in ast.walk(a):
                    if isinstance(n, ast.Name):
                        nomes.add(n.id)
        elif isinstance(no, (ast.Import, ast.ImportFrom)):
            for al in no.names:
                if al.name == "*":
                    dinamico = True
                nomes.add((al.asname or al.name).split(".")[0])
        elif isinstance(no, (ast.If, ast.Try, ast.With, ast.For, ast.While)):
            # definições dentro de if/try (ex.: try: import x / except: x = None)
            sub = ast.Module(body=[n for n in ast.walk(no) if isinstance(n, ast.stmt) and n is not no], type_ignores=[])
            n2, d2 = _nomes_definidos(sub)
            nomes |= n2
            dinamico = dinamico or d2
    return nomes, dinamico


def verificar_python(projeto: Path) -> list[dict]:
    """Erro de sintaxe em cada .py e `from modulo_do_projeto import nome` de algo que o módulo
    não define — o defeito mais comum quando a IA escreve vários arquivos um a um."""
    problemas = []
    arvores: dict[str, ast.AST] = {}
    arquivos = _arquivos_do_projeto(projeto, (".py",))
    for p in arquivos:
        rel = _rel(projeto, p)
        try:
            arvores[rel] = ast.parse(_ler(p), filename=rel)
        except SyntaxError as e:
            problemas.append({"arquivo": rel, "tipo": "sintaxe",
                              "problema": f"{rel}: SyntaxError: {e.msg} (linha {e.lineno})"})
    modulos: dict[str, str] = {}
    for rel in arvores:
        mod = rel[:-3].replace("/", ".")
        modulos[mod[:-9] if mod.endswith(".__init__") else mod] = rel
    for rel, arv in arvores.items():
        for no in ast.walk(arv):
            if not isinstance(no, ast.ImportFrom) or no.level or not no.module:
                continue
            alvo_rel = modulos.get(no.module)
            if not alvo_rel or alvo_rel == rel:
                continue
            definidos, dinamico = _nomes_definidos(arvores[alvo_rel])
            if dinamico:
                continue
            for al in no.names:
                if al.name == "*" or al.name in definidos:
                    continue
                if f"{no.module}.{al.name}" in modulos:      # é um submódulo, não um nome
                    continue
                problemas.append({
                    "arquivo": rel, "tipo": "import", "alvo": alvo_rel,
                    "problema": (f"{rel} importa '{al.name}' de {no.module}, mas {alvo_rel} só define: "
                                 f"{', '.join(sorted(definidos)[:25]) or '(nada)'}")})
    return problemas


def verificar_projeto(projeto: Path, web: bool) -> list[dict]:
    """Todos os problemas que dá para achar sem executar nada."""
    projeto = Path(projeto)
    achados = verificar_python(projeto) + verificar_json(projeto)
    if web:
        achados += verificar_html(projeto) + verificar_css(projeto)
    achados += verificar_js(projeto)
    return achados


# ── leitura do projeto, backups e metadados ──────────────────────────────────

def ler_meta(projeto: Path) -> dict:
    try:
        d = json.loads((Path(projeto) / META).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def gravar_meta(projeto: Path, **campos) -> None:
    meta = ler_meta(projeto)
    meta.update({k: v for k, v in campos.items() if v is not None})
    try:
        (Path(projeto) / META).write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def ler_arquivos(projeto: Path, limite_total: int = 60_000, limite_arquivo: int = 12_000) -> dict[str, str]:
    """{caminho relativo: texto} dos arquivos de texto do projeto, para a IA ver antes de alterar."""
    projeto = Path(projeto)
    saida: dict[str, str] = {}
    total = 0
    for raiz, dirs, nomes in os.walk(projeto):
        dirs[:] = sorted(d for d in dirs if d.lower() not in PASTAS_IGNORADAS)
        for n in sorted(nomes):
            p = Path(raiz) / n
            if n == META or p.suffix.lower() not in EXT_TEXTO:
                continue
            try:
                if p.stat().st_size > MAX_BYTES_ARQUIVO:
                    continue
            except OSError:
                continue
            texto = _ler(p)
            if len(texto) > limite_arquivo:
                texto = texto[:limite_arquivo] + "\n…(arquivo cortado para caber)"
            if total + len(texto) > limite_total:
                return saida
            saida[_rel(projeto, p)] = texto
            total += len(texto)
    return saida


def _normalizar(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", t)


def listar_projetos(raiz: Path) -> list[dict]:
    """Pastas de projeto em `raiz`, a mais recente primeiro."""
    raiz = Path(raiz)
    itens = []
    try:
        for d in raiz.iterdir():
            if d.is_dir() and not d.name.startswith("."):
                meta = ler_meta(d)
                itens.append({"nome": d.name, "pasta": str(d), "descricao": str(meta.get("description") or "")[:160],
                              "mtime": d.stat().st_mtime})
    except OSError:
        return []
    return sorted(itens, key=lambda x: x["mtime"], reverse=True)


def achar_projeto(raiz: Path, nome: str) -> Path | None:
    """Acha a pasta de um projeto pelo nome falado ("o site da padaria" → site_padaria)."""
    lista = listar_projetos(raiz)
    if not lista:
        return None
    if not str(nome or "").strip():
        return Path(lista[0]["pasta"])            # sem nome: o último mexido
    alvo = _normalizar(nome)
    por_nome = {_normalizar(i["nome"]): i for i in lista}
    if alvo in por_nome:
        return Path(por_nome[alvo]["pasta"])
    contem = [i for k, i in por_nome.items() if alvo and (alvo in k or k in alvo)]
    if len(contem) >= 1:
        return Path(contem[0]["pasta"])
    perto = difflib.get_close_matches(alvo, list(por_nome), n=1, cutoff=0.6)
    if perto:
        return Path(por_nome[perto[0]]["pasta"])
    # procura também na descrição guardada
    palavras = [w for w in re.split(r"\W+", str(nome).lower()) if len(w) > 3]
    for i in lista:
        desc = i["descricao"].lower()
        if palavras and all(w in desc for w in palavras):
            return Path(i["pasta"])
    return None


def fazer_backup(projeto: Path, caminhos: list[str]) -> Path:
    """Copia os arquivos que vão mudar (e anota os que vão ser criados) antes de uma alteração."""
    projeto = Path(projeto)
    pasta = projeto / BACKUPS / time.strftime("%Y%m%d-%H%M%S")
    n = 1
    while pasta.exists():
        pasta = projeto / BACKUPS / f"{time.strftime('%Y%m%d-%H%M%S')}-{n}"
        n += 1
    pasta.mkdir(parents=True, exist_ok=True)
    criados = []
    for rel in caminhos:
        origem = caminho_seguro(rel, projeto)
        if origem is None:
            continue
        if origem.exists():
            destino = pasta / rel
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origem, destino)
        else:
            criados.append(rel)
    (pasta / "_manifesto.json").write_text(json.dumps({"criados": criados}, ensure_ascii=False), encoding="utf-8")
    return pasta


def restaurar_ultimo_backup(projeto: Path) -> str | None:
    """Desfaz a última alteração: volta os arquivos antigos e apaga os que ela criou.
    Devolve um resumo, ou None se não há backup."""
    projeto = Path(projeto)
    base = projeto / BACKUPS
    try:
        pastas = sorted(p for p in base.iterdir() if p.is_dir() and not p.name.endswith("-restaurado"))
    except OSError:
        return None
    if not pastas:
        return None
    ultimo = pastas[-1]
    voltaram = removidos = 0
    for f in ultimo.rglob("*"):
        if f.is_file() and f.name != "_manifesto.json":
            destino = caminho_seguro(f.relative_to(ultimo).as_posix(), projeto)
            if destino is None:
                continue
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, destino)
            voltaram += 1
    try:
        criados = json.loads((ultimo / "_manifesto.json").read_text(encoding="utf-8")).get("criados", [])
    except (OSError, ValueError):
        criados = []
    for rel in criados:
        alvo = caminho_seguro(rel, projeto)
        if alvo is not None and alvo.is_file():
            alvo.unlink()
            removidos += 1
    try:
        ultimo.rename(ultimo.with_name(ultimo.name + "-restaurado"))
    except OSError:
        pass
    return f"{voltaram} arquivo(s) voltaram ao que eram e {removidos} criado(s) foram removidos"


def leia_me(nome: str, descricao: str, comando: str, arquivos: list[str], web: bool, pasta_python: bool) -> str:
    """LEIA-ME.txt gerado sem IA: como abrir e o que tem em cada pedaço."""
    como = ("Dê dois cliques em index.html (abre no navegador)." if web
            else f"Abra um terminal nesta pasta e rode:  {comando}" if comando else "Abra a pasta no VS Code.")
    linhas = [f"{nome}", "=" * max(len(nome), 8), "", f"O que é: {descricao}", "", "Como usar:", f"  {como}"]
    if pasta_python:
        linhas += ["", "As bibliotecas deste projeto ficam na pasta .venv (não mexem no Python do NEXUS).",
                   "Para rodar fora do NEXUS use o python que está em .venv\\Scripts\\ (Windows)."]
    linhas += ["", "Arquivos:"] + [f"  - {a}" for a in arquivos] + ["", "Criado pelo NEXUS Ultra 2026 (André Luiz Lima Menezes)."]
    return "\n".join(linhas) + "\n"
