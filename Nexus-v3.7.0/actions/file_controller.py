import os
import shutil
import platform
from pathlib import Path
from datetime import datetime

try:
    import send2trash
    _SEND2TRASH = True
except ImportError:
    _SEND2TRASH = False

from core.undo import push_undo

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"

# Undo keeps a file's previous contents in memory so `write` can be reversed.
# Above this size it does not — a 200 MB log would sit in RAM for the rest of
# the session to protect an edit nobody is going to take back.
_UNDO_CONTENT_LIMIT = 1_000_000


def _undo_move(src: Path, dst: Path):
    """Reverse of a move: put it back where it came from."""
    def _fn():
        if not dst.exists():
            return f"'{dst.name}' is no longer there — nothing moved back."
        src.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dst), str(src))
        return f"'{src.name}' is back in {src.parent.name}/."
    return _fn


def _undo_create(target: Path):
    """Reverse of a create: remove what we made — and only if we still made it.

    Deliberately refuses to touch a directory that has since been filled: the
    undo for 'create a folder' is not 'delete whatever ended up in it'."""
    def _fn():
        if not target.exists():
            return f"'{target.name}' is already gone."
        if target.is_dir():
            if any(target.iterdir()):
                return (f"'{target.name}' is not empty any more — "
                        f"leaving it alone rather than deleting your files.")
            target.rmdir()
        else:
            target.unlink()
        return f"Removed '{target.name}'."
    return _fn


def _undo_write(target: Path, previous: str | None):
    """Reverse of a write: restore the old contents, or remove a file that did
    not exist before the write created it."""
    def _fn():
        if previous is None:
            if target.exists():
                target.unlink()
                return f"Removed '{target.name}' — it did not exist before."
            return f"'{target.name}' is already gone."
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(previous, encoding="utf-8")
        return f"Restored the previous contents of '{target.name}'."
    return _fn


def _restore_from_trash(original: Path) -> str:
    """Best-effort undelete.

    delete_file uses send2trash, which is the right call: the file lands in the
    Recycle Bin / Trash where the person can also find it themselves. Getting it
    back out again is shell work and only reliable on Windows, where pywin32 is
    already a dependency. Everywhere else this says where the file is instead of
    pretending it failed — the file is not lost either way."""
    if _OS == "Windows":
        try:
            import win32com.client
            shell = win32com.client.Dispatch("Shell.Application")
            bin_folder = shell.NameSpace(10)      # ssfBITBUCKET
            for item in bin_folder.Items():
                if str(bin_folder.GetDetailsOf(item, 1)).strip().lower() == \
                        str(original.parent).strip().lower():
                    if str(item.Name).strip().lower() == original.name.strip().lower():
                        item.InvokeVerb("UNDELETE")
                        return f"'{original.name}' restored from the Recycle Bin."
        except Exception as e:
            print(f"[file] Recycle Bin restore failed: {e}")
    return (f"'{original.name}' is in the Recycle Bin — I could not pull it back "
            f"automatically, but it is there and can be restored by hand.")


_SAFE_ROOTS: list[Path] = [
    Path.home(),
]

def _is_safe_path(target: Path) -> bool:
    """Is the given path inside _SAFE_ROOTS? If not, reject the operation."""
    try:
        resolved = target.resolve()
        return any(
            resolved == root.resolve() or resolved.is_relative_to(root.resolve())
            for root in _SAFE_ROOTS
        )
    except Exception:
        return False

def _win_shell_dir(shell_name: str, fallback: str) -> Path:
    """Real user folder on Windows (handles OneDrive redirection).

    OneDrive silently relocates Desktop/Downloads/Documents to
    OneDrive\\Desktop etc.; Path.home()/Desktop then points at a stale or
    missing folder and 'organize my desktop' moves nothing. The registry's
    User Shell Folders key is the source of truth."""
    if _OS == "Windows":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer"
                r"\User Shell Folders")
            val = winreg.QueryValueEx(key, shell_name)[0]
            p = Path(os.path.expandvars(val))
            if p.exists():
                return p
        except Exception:
            pass
    return Path.home() / fallback


def _get_desktop() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DESKTOP_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    if _OS == "Windows":
        return _win_shell_dir("Desktop", "Desktop")
    return Path.home() / "Desktop"

def _get_downloads() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DOWNLOAD_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Downloads"

def _get_documents() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DOCUMENTS_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Documents"

def _get_pictures() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_PICTURES_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Pictures"

def _get_music() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_MUSIC_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Music"

def _get_videos() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_VIDEOS_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Videos"


# Nomes em português que viram as pastas do usuário (1.4)
_ALIASES_PT = {
    "área de trabalho": "desktop", "area de trabalho": "desktop", "desktop": "desktop",
    "downloads": "downloads", "download": "downloads", "baixados": "downloads",
    "documentos": "documents", "meus documentos": "documents", "documents": "documents",
    "imagens": "pictures", "fotos": "pictures", "pictures": "pictures",
    "músicas": "music", "musicas": "music", "música": "music", "musica": "music", "music": "music",
    "vídeos": "videos", "videos": "videos", "vídeo": "videos",
    "pasta pessoal": "home", "minha pasta": "home", "usuário": "home", "usuario": "home", "home": "home",
}


def _get_temp() -> Path:
    import tempfile
    return Path(tempfile.gettempdir())


def _resolve_path(raw: str) -> Path:
    shortcuts: dict[str, Path] = {
        "desktop":   _get_desktop(),
        "downloads": _get_downloads(),
        "documents": _get_documents(),
        "pictures":  _get_pictures(),
        "music":     _get_music(),
        "videos":    _get_videos(),
        "home":      Path.home(),
        "temp":      _get_temp(),
        "tmp":       _get_temp(),
        "temporarios": _get_temp(),
        "temporários": _get_temp(),
        "arquivos temporarios": _get_temp(),
        "arquivos temporários": _get_temp(),
    }
    # 1.4.3 — "%temp%", "%USERPROFILE%\\Downloads", "~/x" e "AppData:Local/Temp"
    # (como o Gemini às vezes escreve) viram o caminho de verdade. Antes davam
    # "Path not found: %temp%".
    raw = str(raw or "")
    if "%" in raw:
        import re as _re
        raw = _re.sub(r"%([^%\\/]+)%",
                      lambda m: os.environ.get(m.group(1)) or os.environ.get(m.group(1).upper())
                      or (str(_get_temp()) if m.group(1).lower() in ("temp", "tmp") else m.group(0)),
                      raw)
    if "$" in raw:
        raw = os.path.expandvars(raw)
    if raw.strip().lower().startswith("appdata:"):
        raw = str(Path.home() / "AppData" / raw.strip()[len("appdata:"):].lstrip("/\\"))
    _limpo = raw.strip().strip('"').strip("'").lower()
    _limpo = _limpo.removeprefix("pasta ").removeprefix("a pasta ").removeprefix("minha ").removeprefix("meus ").strip()
    if _limpo in _ALIASES_PT:
        return shortcuts[_ALIASES_PT[_limpo]]
    raw   = raw.strip().strip('"').strip("'")
    lower = raw.lower()
    if lower in shortcuts:
        return shortcuts[lower]

    # "desktop/notes/a.md" and "desktop\notes\a.md" — a shortcut followed by a
    # sub-path.  Without this branch the whole string falls through to the
    # relative-path return below and is resolved against the process CWD instead
    # of the real Desktop: an "Access denied" when the project lives outside the
    # home directory, or — worse — a silent write into a stray "desktop" folder
    # inside the project when it lives inside it.
    head, sep, rest = raw.replace("\\", "/").partition("/")
    if sep and head.lower() in shortcuts:
        rest = rest.strip("/")
        return shortcuts[head.lower()] / rest if rest else shortcuts[head.lower()]

    return Path(raw).expanduser()

def _procura_pasta(nome: str, limite: int = 6) -> list[Path]:
    """Procura uma pasta pelo nome nos lugares de sempre (até 2 níveis)."""
    alvo = nome.strip().lower()
    if not alvo or len(alvo) < 2:
        return []
    raizes = [_get_desktop(), _get_documents(), _get_downloads(), _get_pictures(),
              _get_music(), _get_videos(), Path.home()]
    achados: list[Path] = []
    vistos = set()
    for raiz in raizes:
        try:
            if not raiz.exists():
                continue
            nivel1 = [d for d in raiz.iterdir() if d.is_dir() and not d.name.startswith(".")]
        except (PermissionError, OSError):
            continue
        candidatos = list(nivel1)
        for d in nivel1[:200]:
            try:
                candidatos += [x for x in d.iterdir() if x.is_dir() and not x.name.startswith(".")][:200]
            except (PermissionError, OSError):
                continue
        for d in candidatos:
            if d.name.lower() == alvo and str(d) not in vistos:
                vistos.add(str(d))
                achados.append(d)
                if len(achados) >= limite:
                    return achados
    return achados


def _parecidas(nome: str, n: int = 3) -> list[str]:
    import difflib
    nomes = set()
    for raiz in (_get_desktop(), _get_documents(), _get_downloads(), Path.home()):
        try:
            nomes |= {d.name for d in raiz.iterdir() if d.is_dir() and not d.name.startswith(".")}
        except (PermissionError, OSError):
            continue
    return difflib.get_close_matches(nome, sorted(nomes), n=n, cutoff=0.6)


def open_path(path: str) -> str:
    """Open a folder in Explorer / a file with its default app.

    Accepts 'C:\\Users\\Andre', 'c:/users/andre', 'C:', 'unidade C',
    quotes and shortcuts (desktop, downloads... e em português: área de
    trabalho, documentos, imagens...). Opening is read-only, so unlike
    delete/move it is not gated to the home directory — any existing path on
    the drive opens fine.

    1.4: se o caminho não existir, procura uma pasta com esse nome nos lugares
    de sempre; se não achar, sugere nomes parecidos. Erros em português."""
    import subprocess
    if not str(path or "").strip():
        return "Não consegui abrir: faltou dizer qual pasta ou arquivo."
    try:
        base = _resolve_path(path)

        # "C:", "c:", "C", "unidade C" → raiz da unidade
        import re
        m = re.fullmatch(
            r"(?:unidade |drive |disco )?([a-zA-Z]):?[\\/]?", path.strip())
        if m and not path.strip().lower().startswith(("desktop", "downloads",
                                                      "documents", "pictures",
                                                      "music", "videos", "home")):
            base = Path(f"{m.group(1).upper()}:\\")

        if not base.exists():
            achados = _procura_pasta(Path(str(path).strip().strip('"')).name)
            if len(achados) == 1:
                base = achados[0]
            elif len(achados) > 1:
                lista = "; ".join(str(a) for a in achados[:5])
                return (f"Achei mais de uma pasta chamada '{achados[0].name}': {lista}. "
                        f"Qual delas devo abrir?")
            else:
                dicas = _parecidas(Path(str(path)).name)
                extra = (" Pastas com nome parecido: " + ", ".join(dicas) + ".") if dicas else ""
                return f"Não consegui abrir: não encontrei '{path}'.{extra}"

        if _OS == "Windows":
            os.startfile(str(base))            # Explorer / app padrão
        elif _OS == "Darwin":
            subprocess.Popen(["open", str(base)])
        else:
            subprocess.Popen(["xdg-open", str(base)])
        return f"Opened: {base}"

    except PermissionError:
        return f"Não consegui abrir '{path}': sem permissão para acessar esse local."
    except OSError as e:
        if getattr(e, "winerror", None) == 1155:
            return f"Não consegui abrir '{path}': não há nenhum programa para abrir esse tipo de arquivo."
        return f"Não consegui abrir '{path}': {e.strerror or e}."
    except Exception as e:
        return f"Não consegui abrir '{path}': {e}"


# ── hidden files ──────────────────────────────────────────────────────────

# Nunca mexer: seção do registro do usuário e estruturas de apps/repositórios.
_HIDDEN_DENY_NAMES = {"desktop.ini", "thumbs.db", ".ds_store"}
_HIDDEN_DENY_DIRS = {".git", ".venv", "venv", "node_modules",
                     "__pycache__", ".idea", ".vscode", "appdata"}


def _is_hidden_attr(p: Path) -> bool:
    """Windows FILE_ATTRIBUTE_HIDDEN via ctypes (POSIX: só o ponto inicial)."""
    if p.name.startswith("."):
        return True
    if _OS == "Windows":
        try:
            import ctypes
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(p))
            return attrs != -1 and bool(attrs & 0x2)     # FILE_ATTRIBUTE_HIDDEN
        except Exception:
            return False
    return False


def hidden_files(path: str = "home", mode: str = "list",
                 confirm: bool = False, recursive: bool = False) -> str:
    """List or delete (to trash, reversible) hidden files inside a folder.

    Deletion only runs with confirm=True, never touches ntuser*, registry
    hives, AppData, .git and friends, and is restricted to the home
    directory — the same safety gate as every other destructive action."""
    base = _resolve_path(path)
    if not _is_safe_path(base):
        return f"Access denied: deletions are limited to your user folder — {base}"
    if not base.exists():
        return f"Path not found: {base}"

    found: list[Path] = []
    it = base.rglob("*") if recursive else base.iterdir()
    for p in it:
        if len(found) >= 200:                    # teto de segurança
            break
        low = p.name.lower()
        if low.startswith("ntuser"):              # seção do registro — nunca
            continue
        if any(part.lower() in _HIDDEN_DENY_DIRS for part in p.parts):
            continue
        if low in _HIDDEN_DENY_NAMES:
            continue
        if p.is_file() and _is_hidden_attr(p):
            found.append(p)

    if not found:
        return "No hidden files found in this folder."

    if mode != "delete":
        listing = "\n".join(f"  • {f.name} ({_format_size(f.stat().st_size)})"
                            for f in found[:15])
        more = "" if len(found) <= 15 else f"\n  … and {len(found) - 15} more."
        return (f"{len(found)} hidden file(s) found:\n{listing}{more}"
                f"\nSay 'delete hidden files' with confirm to remove them.")

    if not confirm:
        return (f"Found {len(found)} hidden file(s). I will only delete with "
                f"explicit confirmation — say 'confirm delete hidden files'.")

    deleted, failed = 0, []
    for f in found:
        try:
            _safe_trash(f)
            deleted += 1
        except Exception as e:
            failed.append(f"{f.name}: {e}")
    if deleted == 0:
        return (f"Could not delete any of the {len(found)} hidden file(s): "
                f"{'; '.join(failed[:5])}")
    result = f"Moved {deleted} hidden file(s) to the trash."
    if failed:
        result += f"\nCould not delete: {'; '.join(failed[:5])}"
    return result


def clean_temp(confirm: bool = False, min_age_hours: float = 1.0) -> str:
    """1.4.3 — limpa a pasta de arquivos temporários (%TEMP%), como a Limpeza
    de Disco do Windows: apaga o que tem mais de 1 hora e pula o que está em uso
    (é normal sobrar uma parte). Só apaga com confirm=True; sem isso, só mede."""
    import time as _t
    base = _get_temp()
    if not base.exists():
        return f"Temp folder not found: {base}"
    limite = _t.time() - max(0.0, float(min_age_hours)) * 3600
    itens, total = [], 0
    try:
        for p in base.iterdir():
            try:
                st = p.stat()
                if st.st_mtime > limite:
                    continue
                if p.is_dir() and not p.is_symlink():
                    tam = 0
                    for f in p.rglob("*"):
                        try:
                            if f.is_file():
                                tam += f.stat().st_size
                        except Exception:
                            pass
                else:
                    tam = st.st_size
                itens.append((p, tam))
                total += tam
            except Exception:
                continue
    except Exception as e:
        return f"Could not read the temp folder: {e}"
    if not itens:
        return f"The temp folder ({base}) is already clean — nothing older than {min_age_hours:g} h."
    if not confirm:
        return (f"Temp folder {base}: {len(itens)} item(s), {_format_size(total)} can be removed "
                f"(older than {min_age_hours:g} h). These are temporary files, deleted permanently "
                f"(not to the Recycle Bin). Ask the user to confirm, then call again with confirm=true.")
    apagados, liberado, em_uso = 0, 0, 0
    for p, tam in itens:
        try:
            if p.is_dir() and not p.is_symlink():
                shutil.rmtree(p, ignore_errors=False)
            else:
                p.unlink()
            apagados += 1
            liberado += tam
        except Exception:
            em_uso += 1           # arquivo aberto por algum programa: fica
    msg = f"Cleaned the temp folder: {apagados} item(s) removed, {_format_size(liberado)} freed."
    if em_uso:
        msg += f" {em_uso} item(s) are in use by other programs and were left (this is normal)."
    return msg


def _pedir_confirmacao(chave: str, titulo: str, detalhe: str, executar) -> str:
    """3.5.0 — estaciona uma ação destrutiva atrás da confirmação da INTERFACE.

    O `confirm=true` que vem nos parâmetros da ferramenta é escrito pelo modelo,
    então não prova que uma pessoa disse sim. Aqui a ação só roda se o HUD
    chamar core.confirm.resolve(True). Sem interface ligada, não apaga nada."""
    from core import confirm as _confirm
    if _confirm.pending_title():
        return ("There is already a confirmation waiting on screen. "
                "Ask the user to answer that one first.")
    return _confirm.request(key=chave, title=titulo, detail=detalhe, run=executar)


def _format_size(b: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"

def _safe_trash(target: Path) -> str:

    if not _SEND2TRASH:
        return (
            "send2trash is not installed. "
            "Run: pip install send2trash — "
            "Permanent deletion is disabled for safety."
        )
    send2trash.send2trash(str(target))
    return f"Moved to Trash: {target.name}"


def list_files(path: str = "desktop", show_hidden: bool = False) -> str:
    try:
        target = _resolve_path(path)
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        if not target.exists():
            return f"Path not found: {target}"
        if not target.is_dir():
            return f"Not a directory: {target}"

        items = []
        for item in sorted(target.iterdir()):
            if not show_hidden and item.name.startswith("."):
                continue
            if item.is_dir():
                items.append(f"📁 {item.name}/")
            else:
                size = _format_size(item.stat().st_size)
                items.append(f"📄 {item.name} ({size})")

        if not items:
            return f"Directory is empty: {target.name}/"

        return f"Contents of {target.name}/ ({len(items)} items):\n" + "\n".join(items)

    except PermissionError:
        return f"Permission denied: {path}"
    except Exception as e:
        return f"Error listing files: {e}"


def create_file(path: str, name: str = "", content: str = "") -> str:
    try:
        base   = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        target.parent.mkdir(parents=True, exist_ok=True)
        existed = target.exists()
        previous = None
        if existed:
            try:
                previous = target.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                previous = None
        target.write_text(content, encoding="utf-8")
        push_undo(f"created {target.name}",
                  _undo_write(target, previous) if existed else _undo_create(target))
        return f"File created: {target.name}"
    except Exception as e:
        return f"Could not create file: {e}"


def create_folder(path: str, name: str = "") -> str:
    try:
        base   = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        already = target.exists()
        target.mkdir(parents=True, exist_ok=True)
        # Only offer to undo a folder we actually made. "mkdir -p" on something
        # that was already there is not a change, and undoing it would delete a
        # directory the user has had for years.
        if not already:
            push_undo(f"created folder {target.name}", _undo_create(target))
        return f"Folder created: {target.name}"
    except Exception as e:
        return f"Could not create folder: {e}"


def delete_file(path: str, name: str = "") -> str:
    try:
        base   = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        if not target.exists():
            return f"Not found: {target.name}"

        # Safe-directory check — protect critical user folders
        protected = {
            _get_desktop(), _get_downloads(), _get_documents(),
            _get_pictures(), _get_music(), _get_videos(), Path.home()
        }
        if target.resolve() in {p.resolve() for p in protected}:
            return f"Protected directory, cannot delete: {target.name}"

        original = target.resolve()
        result   = _safe_trash(target)
        if result.startswith("Moved to Trash"):
            push_undo(f"deleted {original.name}",
                      lambda p=original: _restore_from_trash(p))
        return result

    except PermissionError:
        return f"Permission denied: {path}"
    except Exception as e:
        return f"Could not delete: {e}"


def move_file(path: str, name: str = "", destination: str = "") -> str:
    try:
        base   = _resolve_path(path)
        src    = (base / name) if name else base
        dst    = _resolve_path(destination) if destination else None

        if not src.exists():
            return f"Source not found: {src.name}"
        if dst is None:
            return "No destination specified."
        if not _is_safe_path(src):
            return f"Access denied (source): {src}"
        if not _is_safe_path(dst):
            return f"Access denied (destination): {dst}"

        if dst.is_dir():
            dst = dst / src.name

        dst.parent.mkdir(parents=True, exist_ok=True)
        origin = src.resolve()
        shutil.move(str(src), str(dst))
        push_undo(f"moved {origin.name} to {dst.parent.name}/",
                  _undo_move(origin, dst.resolve()))
        return f"Moved: {src.name} → {dst.parent.name}/"

    except Exception as e:
        return f"Could not move: {e}"


def copy_file(path: str, name: str = "", destination: str = "") -> str:
    try:
        base = _resolve_path(path)
        src  = (base / name) if name else base
        dst  = _resolve_path(destination) if destination else None

        if not src.exists():
            return f"Source not found: {src.name}"
        if dst is None:
            return "No destination specified."
        if not _is_safe_path(src):
            return f"Access denied (source): {src}"
        if not _is_safe_path(dst):
            return f"Access denied (destination): {dst}"

        if dst.is_dir():
            dst = dst / src.name

        dst.parent.mkdir(parents=True, exist_ok=True)

        if src.is_dir():
            shutil.copytree(str(src), str(dst))
        else:
            shutil.copy2(str(src), str(dst))

        # The undo for a copy is deleting the copy — never the original.
        _copy = dst.resolve()
        def _undo_copy():
            if not _copy.exists():
                return f"The copy '{_copy.name}' is already gone."
            if _copy.is_dir():
                shutil.rmtree(_copy)
            else:
                _copy.unlink()
            return f"Removed the copy in {_copy.parent.name}/."
        push_undo(f"copied {src.name} to {dst.parent.name}/", _undo_copy)

        return f"Copied: {src.name} → {dst.parent.name}/"

    except Exception as e:
        return f"Could not copy: {e}"


def rename_file(path: str, name: str = "", new_name: str = "") -> str:
    try:
        base     = _resolve_path(path)
        target   = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        if not target.exists():
            return f"Not found: {target.name}"
        if not new_name:
            return "No new name provided."

        new_path = target.parent / new_name
        if new_path.exists():
            return f"A file named '{new_name}' already exists here."

        old_path = target.resolve()
        target.rename(new_path)
        push_undo(f"renamed {old_path.name} to {new_name}",
                  _undo_move(old_path, new_path.resolve()))
        return f"Renamed: {target.name} → {new_name}"

    except Exception as e:
        return f"Could not rename: {e}"


def read_file(path: str, name: str = "", max_chars: int = 4000) -> str:
    try:
        base   = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        if not target.exists():
            return f"File not found: {target.name}"
        if not target.is_file():
            return f"Not a file: {target.name}"

        content = target.read_text(encoding="utf-8", errors="ignore")
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n\n[Truncated — {len(content)} total chars]"
        return content

    except Exception as e:
        return f"Could not read file: {e}"


def write_file(path: str, name: str = "", content: str = "",
               append: bool = False) -> str:
    try:
        base   = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        target.parent.mkdir(parents=True, exist_ok=True)

        # Snapshot before writing. None means "did not exist", which is a
        # different undo (delete it) from "existed and had this in it".
        previous: str | None = None
        undoable = True
        if target.exists():
            try:
                if target.stat().st_size > _UNDO_CONTENT_LIMIT:
                    undoable = False       # too large to hold in memory
                else:
                    previous = target.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                undoable = False           # binary, locked, unreadable

        mode = "a" if append else "w"
        with open(target, mode, encoding="utf-8") as f:
            f.write(content)

        action = "Appended to" if append else "Written to"
        if undoable:
            push_undo(f"wrote to {target.name}", _undo_write(target, previous))
            return f"{action}: {target.name}"
        return (f"{action}: {target.name}. "
                f"(Too large to keep a copy of the old contents, so this one "
                f"cannot be undone.)")
    except Exception as e:
        return f"Could not write file: {e}"


def find_files(name: str = "", extension: str = "",
               path: str = "home", max_results: int = 20) -> str:
    try:
        search_path = _resolve_path(path)
        if not _is_safe_path(search_path):
            return f"Access denied: {search_path}"
        if not search_path.exists():
            return f"Search path not found: {path}"

        results    = []
        dir_count  = 0
        max_dirs   = 500  # performance + safety limit

        for item in search_path.rglob("*"):
            if item.is_dir():
                dir_count += 1
                if dir_count > max_dirs:
                    break
                continue
            if not item.is_file():
                continue
            if extension and item.suffix.lower() != extension.lower():
                continue
            if name and name.lower() not in item.name.lower():
                continue
            size = _format_size(item.stat().st_size)
            results.append(f"📄 {item.name} ({size}) — {item.parent}")
            if len(results) >= max_results:
                break

        if not results:
            query = name or extension or "files"
            return f"No {query} found in {search_path.name}/"

        return f"Found {len(results)} file(s):\n" + "\n".join(results)

    except Exception as e:
        return f"Search error: {e}"


def get_largest_files(path: str = "downloads", count: int = 10) -> str:
    count = min(count, 50)  # maksimum 50
    try:
        search_path = _resolve_path(path)
        if not _is_safe_path(search_path):
            return f"Access denied: {search_path}"
        if not search_path.exists():
            return f"Path not found: {path}"

        files = []
        for item in search_path.rglob("*"):
            if item.is_file():
                try:
                    files.append((item.stat().st_size, item))
                except Exception:
                    continue

        files.sort(reverse=True)
        top = files[:count]

        if not top:
            return "No files found."

        lines = [f"Top {len(top)} largest files in {search_path.name}/:"]
        for size, f in top:
            lines.append(f"  {_format_size(size):>10}  {f.name}  ({f.parent})")

        return "\n".join(lines)

    except Exception as e:
        return f"Error: {e}"


def get_disk_usage(path: str = "home") -> str:
    try:
        target = _resolve_path(path)
        usage  = shutil.disk_usage(target)
        pct    = usage.used / usage.total * 100
        return (
            f"Disk usage ({target}):\n"
            f"  Total : {_format_size(usage.total)}\n"
            f"  Used  : {_format_size(usage.used)} ({pct:.1f}%)\n"
            f"  Free  : {_format_size(usage.free)}"
        )
    except Exception as e:
        return f"Could not get disk usage: {e}"




def get_file_info(path: str, name: str = "") -> str:
    try:
        base   = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        if not target.exists():
            return f"Not found: {target.name}"

        stat = target.stat()
        info = {
            "Name":      target.name,
            "Type":      "Folder" if target.is_dir() else "File",
            "Size":      _format_size(stat.st_size),
            "Location":  str(target.parent),
            "Created":   datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M"),
            "Modified":  datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            "Extension": target.suffix or "—",
        }
        return "\n".join(f"  {k}: {v}" for k, v in info.items())

    except Exception as e:
        return f"Could not get file info: {e}"

def _tamanho_legivel(total: int) -> str:
    if total >= 1024 ** 3:
        return f"{total / 1024 ** 3:.2f} GB"
    if total >= 1024 ** 2:
        return f"{total / 1024 ** 2:.1f} MB"
    return f"{total / 1024:.1f} KB"


_PASTAS_IGNORADAS = {".git", "__pycache__", "node_modules"}


def _percorrer(pasta: Path):
    """Gera (caminho, stat) de cada arquivo, sem entrar em .git/node_modules."""
    for base, dirs, files in os.walk(pasta):
        dirs[:] = [d for d in dirs if d not in _PASTAS_IGNORADAS]
        for nome in files:
            p = Path(base) / nome
            try:
                yield p, p.stat()
            except OSError:
                continue


def folder_summary(path: str) -> str:
    """Conta arquivos, tipos e tamanho de uma pasta (não lê o conteúdo)."""
    pasta = _resolve_path(path)
    if not pasta.is_dir():
        return "Não encontrei essa pasta. Informe um caminho válido."
    total = qtd = 0
    tipos: dict[str, int] = {}
    for p, st in _percorrer(pasta):
        total += st.st_size
        qtd += 1
        ext = p.suffix.lower() or "(sem extensão)"
        tipos[ext] = tipos.get(ext, 0) + 1
    topo = sorted(tipos.items(), key=lambda x: x[1], reverse=True)[:8]
    tipos_txt = ", ".join(f"{e}: {n}" for e, n in topo) or "nenhum arquivo encontrado"
    return (f"Pasta {pasta}: {qtd} arquivos, tamanho total {_tamanho_legivel(total)}. "
            f"Tipos mais comuns: {tipos_txt}")


def folder_watch(path: str, mode: str = "check") -> str:
    """Vigia sob demanda: 'baseline' guarda o estado, 'check' diz o que mudou."""
    import json
    pasta = _resolve_path(path)
    if not pasta.is_dir():
        return "Não encontrei essa pasta. Informe um caminho de pasta existente."
    atual = {str(p): {"size": st.st_size, "mtime_ns": st.st_mtime_ns} for p, st in _percorrer(pasta)}
    arq = Path(__file__).resolve().parent.parent / "config" / "folder_watch.json"
    try:
        estado = json.loads(arq.read_text(encoding="utf-8"))
    except Exception:
        estado = {}
    chave = str(pasta.resolve())
    if mode == "baseline" or chave not in estado:
        estado[chave] = atual
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text(json.dumps(estado, indent=2), encoding="utf-8")
        return (f"Referência criada para {pasta}. {len(atual)} arquivos registrados. "
                "Peça para verificar alterações depois.")
    antigo = estado[chave]
    novos = sorted(set(atual) - set(antigo))
    sumiram = sorted(set(antigo) - set(atual))
    mudaram = sorted(p for p in set(antigo) & set(atual) if antigo[p] != atual[p])
    if not (novos or sumiram or mudaram):
        return f"Nenhuma alteração detectada em {pasta}."
    detalhes = [*(f"novo: {p}" for p in novos[:5]), *(f"alterado: {p}" for p in mudaram[:5]),
                *(f"removido: {p}" for p in sumiram[:5])]
    return (f"Alterações detectadas: {len(novos)} novos, {len(mudaram)} modificados, "
            f"{len(sumiram)} removidos. " + "; ".join(detalhes))


def file_controller(
    parameters: dict = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    action = params.get("action", "").lower().strip()
    path   = params.get("path", "desktop")
    name   = params.get("name", "")

    if player:
        player.write_log(f"[file] {action} {name or path}")

    try:
        if action == "list":
            return list_files(path)

        elif action == "create_file":
            return create_file(path, name=name, content=params.get("content", ""))

        elif action == "create_folder":
            return create_folder(path, name=name)

        elif action == "delete":
            return delete_file(path, name=name)

        elif action == "move":
            return move_file(path, name=name, destination=params.get("destination", ""))

        elif action == "copy":
            return copy_file(path, name=name, destination=params.get("destination", ""))

        elif action == "rename":
            return rename_file(path, name=name, new_name=params.get("new_name", ""))

        elif action == "read":
            return read_file(path, name=name)

        elif action == "write":
            return write_file(
                path, name=name,
                content=params.get("content", ""),
                append=params.get("append", False)
            )

        elif action == "find":
            return find_files(
                name=name or params.get("name", ""),
                extension=params.get("extension", ""),
                path=path,
                max_results=min(int(params.get("max_results", 20)), 50),
            )

        elif action == "largest":
            return get_largest_files(
                path=path,
                count=int(params.get("count", 10)),
            )

        elif action == "disk_usage":
            return get_disk_usage(path)

        elif action == "open":
            return open_path(path)

        elif action == "hidden_files":
            modo = str(params.get("mode", "list")).lower()
            recursivo = bool(params.get("recursive", False))
            if modo != "delete":
                return hidden_files(path=path, mode=modo, confirm=False, recursive=recursivo)
            # 3.5.0 — apagar NÃO depende mais do `confirm` que o modelo escreve:
            # só roda se a pessoa apertar CONFIRMAR no HUD (core/confirm.py).
            resumo = hidden_files(path=path, mode="delete", confirm=False, recursive=recursivo)
            if not resumo.startswith("Found "):
                return resumo                       # nada a apagar, ou acesso negado
            return _pedir_confirmacao(
                "hidden_files_delete", "Apagar arquivos ocultos", resumo,
                lambda: hidden_files(path=path, mode="delete", confirm=True, recursive=recursivo),
            )

        elif action == "info":
            return get_file_info(path, name=name)

        elif action in ("summary", "folder_summary"):
            return folder_summary(path)

        elif action in ("watch", "folder_watch"):
            return folder_watch(path, mode=str(params.get("mode", "check")).lower())

        elif action in ("clean_temp", "limpar_temp", "limpar_temporarios"):
            # 3.5.0 — a limpeza é permanente: só roda com o CONFIRMAR da pessoa no HUD.
            resumo = clean_temp(confirm=False)
            if "can be removed" not in resumo or not bool(params.get("confirm", False)):
                return resumo                       # só mede (ou já está limpa)
            return _pedir_confirmacao(
                "clean_temp", "Limpar arquivos temporários", resumo,
                lambda: clean_temp(confirm=True),
            )

        else:
            return f"Unknown action: '{action}'"

    except Exception as e:
        return f"File controller error ({action}): {e}"


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "file_controller",
    "description": "Manages files and folders: list, create, delete, move, copy, rename, read, write, find, disk usage.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "File and folder control: list, create, delete (to trash, reversible), move, copy, rename, read, write, find, largest, disk_usage, info, open / 'abre C:\\...' (opens any path in Explorer or its default app), summary / 'quanto espaço a pasta ocupa' (counts files, types and size of a folder), watch / 'vigia a pasta' (mode='baseline' saves the state, mode='check' reports what was added, changed or removed), hidden_files / 'arquivos ocultos' (list, or mode='delete' + confirm=true to move them to the trash), clean_temp / 'limpa os arquivos temporários', '%temp%' (first call without confirm to measure; after the user says yes, call again with confirm=true)"
            },
            "path": {
                "type": "STRING",
                "description": "File/folder path or shortcut: desktop, downloads, documents, pictures, music, videos, home, temp. Environment variables like %TEMP% or %USERPROFILE% work."
            },
            "mode": {
                "type": "STRING",
                "description": "hidden_files: 'list' or 'delete'. watch: 'baseline' or 'check' (default)."
            },
            "confirm": {
                "type": "BOOLEAN",
                "description": "set true to ask for a deletion (hidden_files delete, clean_temp) AFTER the user said yes out loud; a confirm button then appears on the HUD and nothing is deleted until the user presses it"
            },
            "recursive": {
                "type": "BOOLEAN",
                "description": "hidden_files: also look inside subfolders"
            },
            "destination": {
                "type": "STRING",
                "description": "Destination path for move/copy"
            },
            "new_name": {
                "type": "STRING",
                "description": "New name for rename"
            },
            "content": {
                "type": "STRING",
                "description": "Content for create_file/write"
            },
            "name": {
                "type": "STRING",
                "description": "File name to search for"
            },
            "extension": {
                "type": "STRING",
                "description": "File extension to search (e.g. .pdf)"
            },
            "count": {
                "type": "INTEGER",
                "description": "Number of results for largest"
            }
        },
        "required": [
            "action"
        ]
    },
    "handler": file_controller,
}
