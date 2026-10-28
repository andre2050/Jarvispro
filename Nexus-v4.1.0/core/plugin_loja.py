"""
core/plugin_loja.py — loja de plugins do NEXUS: pacotes assinados e com permissões (NEXUS Ultra 2026 3.5).

Um plugin da loja é um arquivo `.nexusplugin` (um .zip) com:

    plugin.json   manifesto: id, nome, versão, autor, descrição, permissões e o SHA-256 de cada arquivo
    plugin.sig    assinatura Ed25519 do manifesto (bytes do plugin.json, exatamente como estão no pacote)
    *.py          o código (um plugin por pacote; pode ter ajudantes com "_" no começo)

O que a loja garante
  • ASSINATURA — o autor assina com a chave dele. Só vale se a chave pública do autor estiver na sua lista
    de confiáveis (config/autores_confiaveis.json); a chave do desenvolvedor do NEXUS já vem confiada.
    Pacote sem assinatura ou de autor desconhecido só entra se você disser que aceita o risco.
  • PERMISSÕES — o manifesto declara o que o plugin precisa (rede, arquivos, programas, tela, microfone, pessoais).
    O código é lido por análise estática (AST): se usar algo que não declarou, o pacote é RECUSADO.
    Você concede (ou não) as permissões na instalação; plugin sem as permissões concedidas não carrega.
  • INTEGRIDADE — o hash de cada arquivo é conferido na instalação e a cada abertura do NEXUS:
    arquivo alterado depois de instalado não carrega.
  • Plugins soltos na pasta plugins/ (sem manifesto) continuam funcionando como sempre — são "locais".

Limite honesto: a análise estática pega o uso direto e comum (import, open, subprocess, eval…), não código
ofuscado de propósito. Por isso a assinatura de um autor em quem você confia é a proteção principal.
"""
from __future__ import annotations

import ast
import base64
import hashlib
import io
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
PASTA_PLUGINS = _BASE / "plugins"
ARQ_REGISTRO = _BASE / "memory" / "plugins_loja.json"
ARQ_AUTORES = _BASE / "config" / "autores_confiaveis.json"

EXTENSAO = ".nexusplugin"
TAMANHO_MAX_PACOTE = 5 * 1024 * 1024
MAX_ARQUIVOS = 30

PERMISSOES = {
    "rede": "acessar a internet",
    "arquivos": "ler e escrever arquivos no seu computador",
    "programas": "executar programas e comandos do sistema",
    "tela": "ver a tela e usar mouse/teclado",
    "midia": "usar microfone ou câmera",
    "pessoais": "ler suas memórias, notas, e-mails e chaves do NEXUS",
}

_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,40}$")
_VERSAO_RE = re.compile(r"^\d+\.\d+(\.\d+)?$")
_ARQ_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,60}\.py$")

# o que cada módulo/chamada indica (para conferir o que o código REALMENTE usa)
_IMPORTS = {
    "rede": {"requests", "urllib", "urllib3", "http", "httpx", "socket", "ssl", "aiohttp", "websocket", "websockets",
             "smtplib", "ftplib", "imaplib", "poplib", "telnetlib", "xmlrpc", "asyncio.streams"},
    "programas": {"subprocess", "multiprocessing", "ctypes", "pty", "winreg", "webbrowser", "runpy", "code", "pexpect"},
    "tela": {"pyautogui", "pynput", "keyboard", "mouse", "mss", "pygetwindow", "pyscreeze", "PIL.ImageGrab", "cv2"},
    "midia": {"sounddevice", "pyaudio", "speech_recognition", "cv2"},
    "arquivos": {"shutil", "glob", "tempfile", "send2trash", "sqlite3", "pickle", "shelve", "zipfile", "tarfile"},
}
_PROIBIDOS_SEMPRE = {"importlib", "builtins", "marshal"}    # carregar código por baixo dos panos
_CHAMADAS_PROGRAMAS = {"os.system", "os.popen", "os.startfile", "os.execv", "os.execl", "os.spawnl", "os.fork",
                       "os.kill", "os.killpg"}
_CHAMADAS_ARQUIVOS = {"os.remove", "os.unlink", "os.rmdir", "os.rename", "os.replace", "os.makedirs", "os.mkdir",
                      "os.listdir", "os.scandir", "os.walk", "os.chmod", "os.removedirs"}
_METODOS_ARQUIVOS = {"read_text", "write_text", "read_bytes", "write_bytes", "unlink", "mkdir", "rmdir", "touch",
                     "iterdir", "rglob", "glob", "rename", "replace"}
_CHAMADAS_PROIBIDAS = {"eval", "exec", "compile", "__import__"}
_CAMINHOS_PESSOAIS = ("memory/", "memory\\", "config/api_keys", "api_keys.json", "long_term.json")


# ── manifesto e assinatura ───────────────────────────────────────────────────
class ErroPacote(Exception):
    """Pacote inválido ou recusado — a mensagem é segura para falar em voz alta."""


def _b64(s: str) -> bytes:
    return base64.b64decode(s + "=" * (-len(s) % 4))


def _verificar_ed25519(pub: bytes, msg: bytes, sig: bytes) -> bool:
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        try:
            Ed25519PublicKey.from_public_bytes(pub).verify(sig, msg)
            return True
        except InvalidSignature:
            return False
    except ImportError:
        from core import licenca
        return licenca._ed25519_verificar_puro(pub, msg, sig)
    except Exception:
        return False


def chave_do_desenvolvedor() -> str:
    from core import licenca
    return licenca.PUBLIC_KEY_B64


def autores_confiaveis(arq: Path | None = None) -> dict[str, str]:
    """{nome: chave_publica_b64}. A chave do desenvolvedor do NEXUS entra sempre."""
    autores = {"Desenvolvedor do NEXUS": chave_do_desenvolvedor()}
    try:
        d = json.loads(Path(arq or ARQ_AUTORES).read_text(encoding="utf-8"))
        for nome, chave in (d.get("autores") or {}).items():
            if isinstance(nome, str) and isinstance(chave, str) and len(_b64(chave)) == 32:
                autores[nome] = chave
    except Exception:
        pass
    return autores


def confiar_no_autor(nome: str, chave_b64: str, arq: Path | None = None) -> tuple[bool, str]:
    nome = " ".join(str(nome).split())[:60]
    try:
        if len(_b64(chave_b64.strip())) != 32:
            raise ValueError
    except Exception:
        return False, "Essa não parece uma chave pública válida (32 bytes em base64)."
    if not nome:
        return False, "Dê um nome para o autor."
    arq = Path(arq or ARQ_AUTORES)
    try:
        d = json.loads(arq.read_text(encoding="utf-8"))
    except Exception:
        d = {}
    d.setdefault("autores", {})[nome] = chave_b64.strip()
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return True, f"Agora confio nos plugins assinados por {nome}."


def _hash(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _validar_manifesto(m: dict) -> None:
    if not isinstance(m, dict):
        raise ErroPacote("O manifesto (plugin.json) está inválido.")
    if not _ID_RE.match(str(m.get("id", ""))):
        raise ErroPacote("O id do plugin deve ter letras minúsculas, números e _ (3 a 41 caracteres).")
    if not _VERSAO_RE.match(str(m.get("versao", ""))):
        raise ErroPacote("A versão do plugin deve ser como 1.0 ou 1.2.3.")
    for campo in ("nome", "autor", "descricao"):
        if not isinstance(m.get(campo), str) or not m[campo].strip():
            raise ErroPacote(f"O manifesto precisa do campo “{campo}”.")
    perms = m.get("permissoes", [])
    if not isinstance(perms, list) or any(p not in PERMISSOES for p in perms):
        raise ErroPacote("Permissão desconhecida no manifesto. Válidas: " + ", ".join(PERMISSOES) + ".")
    arqs = m.get("arquivos")
    if not isinstance(arqs, dict) or not arqs or len(arqs) > MAX_ARQUIVOS:
        raise ErroPacote("O manifesto precisa listar os arquivos (com o hash de cada um).")
    for nome, h in arqs.items():
        if not _ARQ_RE.match(nome):
            raise ErroPacote(f"Nome de arquivo não permitido no pacote: {nome!r}.")
        if not re.fullmatch(r"[0-9a-f]{64}", str(h)):
            raise ErroPacote(f"Hash inválido para {nome}.")
    if not any(not n.startswith("_") for n in arqs):
        raise ErroPacote("O pacote precisa de um arquivo principal (nome sem _ no começo).")


# ── análise estática: o que o código realmente usa ───────────────────────────
def _nome_pontilhado(no: ast.AST) -> str:
    partes = []
    while isinstance(no, ast.Attribute):
        partes.append(no.attr)
        no = no.value
    if isinstance(no, ast.Name):
        partes.append(no.id)
    return ".".join(reversed(partes))


def permissoes_usadas(codigo: str) -> tuple[set[str], list[str]]:
    """(permissões que o código usa, problemas graves). Nunca levanta erro."""
    usadas: set[str] = set()
    graves: list[str] = []
    try:
        arvore = ast.parse(codigo)
    except SyntaxError as e:
        return usadas, [f"o código tem erro de sintaxe (linha {e.lineno})"]

    def marcar_modulo(mod: str) -> None:
        raiz = mod.split(".")[0]
        if raiz in ("memory", "actions", "assistant") or mod.startswith(("core.memoria", "core.cerebro", "core.preferences")):
            usadas.add("pessoais")
        if raiz in _PROIBIDOS_SEMPRE:
            graves.append(f"usa “{raiz}” (carrega código escondido)")
        for perm, mods in _IMPORTS.items():
            if raiz in mods or mod in mods:
                usadas.add(perm)

    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for a in no.names:
                marcar_modulo(a.name)
        elif isinstance(no, ast.ImportFrom):
            if no.module:
                marcar_modulo(no.module)
                for a in no.names:
                    marcar_modulo(f"{no.module}.{a.name}")
        elif isinstance(no, ast.Call):
            nome = _nome_pontilhado(no.func)
            if nome in _CHAMADAS_PROIBIDAS:
                graves.append(f"chama {nome}() (executa texto como código)")
            if nome in _CHAMADAS_PROGRAMAS:
                usadas.add("programas")
            if nome in _CHAMADAS_ARQUIVOS or nome in ("open", "io.open", "Path", "pathlib.Path", "os.path.expanduser"):
                usadas.add("arquivos")
            if isinstance(no.func, ast.Attribute) and no.func.attr in _METODOS_ARQUIVOS:
                usadas.add("arquivos")
            if nome.endswith(("shutil.rmtree", "shutil.move", "shutil.copy")):
                usadas.add("arquivos")
        elif isinstance(no, ast.Constant) and isinstance(no.value, str):
            if any(c in no.value for c in _CAMINHOS_PESSOAIS) and len(no.value) < 200:
                usadas.add("pessoais")
        elif isinstance(no, ast.Attribute) and no.attr in ("__subclasses__", "__globals__", "__builtins__", "__code__"):
            graves.append(f"mexe em “{no.attr}” (escapa das proteções)")
    return usadas, graves


# ── abrir e conferir um pacote ───────────────────────────────────────────────
class Pacote:
    def __init__(self, manifesto: dict, bruto: bytes, arquivos: dict[str, bytes], autor_confiavel: str | None):
        self.manifesto = manifesto
        self.bruto = bruto
        self.arquivos = arquivos
        self.autor_confiavel = autor_confiavel      # nome do autor confiável que assinou, ou None
        self.id = manifesto["id"]
        self.versao = manifesto["versao"]
        self.permissoes = sorted(manifesto.get("permissoes", []))

    @property
    def assinado(self) -> bool:
        return self.autor_confiavel is not None

    def resumo(self) -> str:
        m = self.manifesto
        perms = ", ".join(PERMISSOES[p] for p in self.permissoes) or "nenhuma permissão especial"
        selo = f"assinado por {self.autor_confiavel}" if self.assinado else "NÃO ASSINADO ou de autor desconhecido"
        return f"{m['nome']} {self.versao}, de {m['autor']} ({selo}). Pede: {perms}."


def abrir_pacote(caminho: str | Path, autores: dict[str, str] | None = None) -> Pacote:
    """Lê, confere hashes, assinatura e permissões. Levanta ErroPacote se algo não bater."""
    p = Path(caminho)
    if not p.is_file() or p.suffix.lower() != EXTENSAO:
        raise ErroPacote(f"Não achei o pacote {EXTENSAO}: {p.name}")
    if p.stat().st_size > TAMANHO_MAX_PACOTE:
        raise ErroPacote("O pacote é grande demais para um plugin.")
    try:
        z = zipfile.ZipFile(p)
    except zipfile.BadZipFile:
        raise ErroPacote("O arquivo não é um pacote válido (zip quebrado).")
    with z:
        nomes = z.namelist()
        if len(nomes) > MAX_ARQUIVOS + 2 or any(n.startswith("/") or ".." in n.split("/") or "\\" in n for n in nomes):
            raise ErroPacote("O pacote tem caminhos de arquivo suspeitos.")
        if sum(i.file_size for i in z.infolist()) > 4 * TAMANHO_MAX_PACOTE:
            raise ErroPacote("O pacote descompactado é grande demais.")
        if "plugin.json" not in nomes:
            raise ErroPacote("O pacote não tem plugin.json.")
        bruto = z.read("plugin.json")
        try:
            manifesto = json.loads(bruto.decode("utf-8"))
        except ValueError:
            raise ErroPacote("O plugin.json não é um JSON válido.")
        _validar_manifesto(manifesto)
        extras = set(nomes) - set(manifesto["arquivos"]) - {"plugin.json", "plugin.sig"}
        if extras:
            raise ErroPacote("O pacote tem arquivos fora do manifesto: " + ", ".join(sorted(extras)))
        arquivos: dict[str, bytes] = {}
        for nome, h in manifesto["arquivos"].items():
            if nome not in nomes:
                raise ErroPacote(f"Falta o arquivo {nome} no pacote.")
            dados = z.read(nome)
            if _hash(dados) != h:
                raise ErroPacote(f"O arquivo {nome} não confere com o hash do manifesto (pacote adulterado).")
            arquivos[nome] = dados
        assinatura = z.read("plugin.sig") if "plugin.sig" in nomes else b""

    autor = None
    if assinatura:
        try:
            sig = _b64(assinatura.decode("ascii").strip())
        except Exception:
            sig = b""
        for nome, chave in (autores if autores is not None else autores_confiaveis()).items():
            if sig and _verificar_ed25519(_b64(chave), bruto, sig):
                autor = nome
                break

    declaradas = set(manifesto.get("permissoes", []))
    for nome, dados in arquivos.items():
        usadas, graves = permissoes_usadas(dados.decode("utf-8", errors="replace"))
        if graves:
            raise ErroPacote(f"{nome} foi recusado: {'; '.join(graves[:3])}.")
        faltou = usadas - declaradas
        if faltou:
            raise ErroPacote(f"{nome} usa recursos que o manifesto não declara: "
                             + ", ".join(sorted(faltou)) + ". Pacote recusado.")
    return Pacote(manifesto, bruto, arquivos, autor)


# ── registro de instalados ───────────────────────────────────────────────────
def _ler_registro(arq: Path | None = None) -> dict:
    try:
        d = json.loads(Path(arq or ARQ_REGISTRO).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _gravar_registro(d: dict, arq: Path | None = None) -> None:
    arq = Path(arq or ARQ_REGISTRO)
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(arq)


def instalar(pacote: Pacote, conceder: list[str] | None = None, aceitar_nao_assinado: bool = False,
             pasta: Path | None = None, arq_registro: Path | None = None) -> str:
    """Instala um pacote JÁ aberto. `conceder`: permissões que a pessoa aprovou (precisa cobrir as declaradas)."""
    pasta = Path(pasta or PASTA_PLUGINS)
    if not pacote.assinado and not aceitar_nao_assinado:
        raise ErroPacote("Pacote sem assinatura de um autor confiável. " + pacote.resumo())
    conceder_set = set(conceder if conceder is not None else [])
    faltam = set(pacote.permissoes) - conceder_set
    if faltam:
        raise ErroPacote("Permissões não concedidas: " + ", ".join(sorted(faltam)) + ".")
    reg = _ler_registro(arq_registro)
    outro = [i for i, r in reg.items() if i != pacote.id and set(r.get("arquivos", {})) & set(pacote.arquivos)]
    if outro:
        raise ErroPacote(f"Os arquivos desse plugin colidem com o plugin já instalado “{outro[0]}”.")
    for nome in pacote.arquivos:
        alvo = pasta / nome
        if alvo.exists() and not any(nome in r.get("arquivos", {}) for r in reg.values()):
            raise ErroPacote(f"Já existe um arquivo seu chamado {nome} na pasta de plugins; não vou sobrescrever.")
    pasta.mkdir(parents=True, exist_ok=True)
    escritos = []
    try:
        for nome, dados in pacote.arquivos.items():
            tmp = pasta / (nome + ".tmp")
            tmp.write_bytes(dados)
            tmp.replace(pasta / nome)
            escritos.append(nome)
    except OSError as e:
        raise ErroPacote(f"Não consegui gravar o plugin: {e}")
    reg[pacote.id] = {
        "nome": pacote.manifesto["nome"], "versao": pacote.versao, "autor": pacote.manifesto["autor"],
        "assinado_por": pacote.autor_confiavel, "permissoes": pacote.permissoes,
        "concedidas": sorted(conceder_set & set(pacote.permissoes)),
        "arquivos": {n: _hash(d) for n, d in pacote.arquivos.items()},
    }
    _gravar_registro(reg, arq_registro)
    return f"Plugin {pacote.manifesto['nome']} {pacote.versao} instalado. Ele passa a valer ao reiniciar o NEXUS."


def remover(id_plugin: str, pasta: Path | None = None, arq_registro: Path | None = None) -> str:
    pasta = Path(pasta or PASTA_PLUGINS)
    reg = _ler_registro(arq_registro)
    alvo = str(id_plugin).strip().lower()
    achado = next((i for i, r in reg.items() if alvo in (i.lower(), str(r.get("nome", "")).lower())), None)
    if achado is None:
        raise ErroPacote(f"“{id_plugin}” não é um plugin da loja.")
    for nome in reg[achado].get("arquivos", {}):
        try:
            (pasta / nome).unlink()
        except FileNotFoundError:
            pass
    nome = reg.pop(achado)["nome"]
    _gravar_registro(reg, arq_registro)
    return f"Plugin {nome} removido."


def instalados(arq_registro: Path | None = None) -> list[dict]:
    return [{"id": i, **r} for i, r in sorted(_ler_registro(arq_registro).items())]


def conferir_arquivo(nome_arquivo: str, pasta: Path | None = None, arq_registro: Path | None = None) -> tuple[bool, str]:
    """Usado pelo carregador de plugins: este arquivo pode carregar? Plugins locais (fora da loja) sempre podem."""
    pasta = Path(pasta or PASTA_PLUGINS)
    for i, r in _ler_registro(arq_registro).items():
        h = r.get("arquivos", {}).get(nome_arquivo)
        if h is None:
            continue
        try:
            if _hash((pasta / nome_arquivo).read_bytes()) != h:
                return False, f"O arquivo mudou depois de instalado pela loja ({r.get('nome', i)}); reinstale o pacote."
        except OSError:
            return False, "Arquivo do plugin ausente."
        if set(r.get("permissoes", [])) - set(r.get("concedidas", [])):
            return False, f"Faltam permissões concedidas para {r.get('nome', i)}."
        return True, ""
    return True, ""


def origem_do_arquivo(nome_arquivo: str, arq_registro: Path | None = None) -> dict | None:
    for i, r in _ler_registro(arq_registro).items():
        if nome_arquivo in r.get("arquivos", {}):
            return {"id": i, **{k: r.get(k) for k in ("nome", "versao", "autor", "assinado_por", "permissoes", "concedidas")}}
    return None


# ── para quem CRIA plugins (usado por ferramentas/assinar_plugin.py) ─────────
def gerar_par_de_chaves() -> tuple[str, str]:
    """(privada_b64, publica_b64) — guarde a privada; compartilhe só a pública."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    k = Ed25519PrivateKey.generate()
    priv = k.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    pub = k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(priv).decode(), base64.b64encode(pub).decode()


def empacotar(pasta_fonte: str | Path, destino: str | Path, meta: dict, chave_privada_b64: str | None = None) -> Path:
    """Monta o .nexusplugin a partir de uma pasta com os .py. `meta`: id, nome, versao, autor, descricao, permissoes.
    Se `permissoes` não vier, usa o que a análise estática achou. Com chave privada, assina."""
    fonte = Path(pasta_fonte)
    arquivos = {p.name: p.read_bytes() for p in sorted(fonte.glob("*.py"))}
    if not arquivos:
        raise ErroPacote("Nenhum .py na pasta.")
    usadas: set[str] = set()
    for dados in arquivos.values():
        u, _ = permissoes_usadas(dados.decode("utf-8", errors="replace"))
        usadas |= u
    manifesto = {
        "id": meta["id"], "nome": meta["nome"], "versao": meta["versao"], "autor": meta["autor"],
        "descricao": meta["descricao"], "permissoes": sorted(meta.get("permissoes", usadas)),
        "arquivos": {n: _hash(d) for n, d in arquivos.items()},
    }
    _validar_manifesto(manifesto)
    bruto = json.dumps(manifesto, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8")
    destino = Path(destino)
    if destino.suffix.lower() != EXTENSAO:
        destino = destino.with_suffix(EXTENSAO)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("plugin.json", bruto)
        for n, d in arquivos.items():
            z.writestr(n, d)
        if chave_privada_b64:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            sig = Ed25519PrivateKey.from_private_bytes(_b64(chave_privada_b64)).sign(bruto)
            z.writestr("plugin.sig", base64.b64encode(sig))
    return destino
