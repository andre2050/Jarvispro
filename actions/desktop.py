#desktop.py
import os
from core.pt_time import agora
import sys
import json
import shutil
import subprocess
import tempfile
import platform
from pathlib import Path
from datetime import datetime
from core.protecao import engolida as _engolida

try:
    import pyautogui
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

def _get_api_key() -> str:
    path = _get_base_dir() / "config" / "api_keys.json"
    with open(path, "r", encoding="utf-8") as f:
        return __import__("core.cofre", fromlist=["resolver"]).resolver(json.load(f))["gemini_api_key"]
    
def _get_desktop() -> Path:
    # mesmo desktop real do file_controller (registro → OneDrive) — sem isso
    # cada módulo podia organizar uma pasta diferente.
    try:
        from actions.file_controller import _get_desktop as _real_desktop
        return _real_desktop()
    except Exception:
        _engolida("actions/desktop.py:39")
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DESKTOP_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Desktop"

def _copy2_sem_sobrescrever(src, dst, *args, **kwargs):
    """3.5.0 — shutil.copy2 da caixa de areia: copiar, nunca sobrescrever."""
    destino = Path(dst)
    if destino.is_dir():
        destino = destino / Path(src).name
    if destino.exists() or destino.is_symlink():
        raise PermissionError(f"já existe, não vou sobrescrever: {destino.name}")
    return shutil.copy2(src, dst)


def _copytree_sem_sobrescrever(src, dst, *args, **kwargs):
    """3.5.0 — shutil.copytree da caixa de areia: pasta de destino nova, sempre."""
    if Path(dst).exists():
        raise PermissionError(f"já existe, não vou misturar: {Path(dst).name}")
    return shutil.copytree(src, dst)


def _build_sandbox() -> dict:
    import time

    safe_builtins = {
        "print": print,
        "len": len, "str": str, "int": int, "float": float,
        "bool": bool, "list": list, "dict": dict, "tuple": tuple,
        "range": range, "enumerate": enumerate, "sorted": sorted,
        "isinstance": isinstance, "hasattr": hasattr,
        "max": max, "min": min, "sum": sum, "abs": abs,
        "zip": zip, "map": map, "filter": filter,
    }

    sandbox = {
        "__builtins__": safe_builtins,
        "Path": Path,
        "time": time,
        "shutil": type("shutil", (), {
            "copy2":      staticmethod(_copy2_sem_sobrescrever),
            "copytree":   staticmethod(_copytree_sem_sobrescrever),
            "disk_usage": shutil.disk_usage,
        })(),
        "os_path": os.path,  
    }

    if _PYAUTOGUI:
        sandbox["pyautogui"] = pyautogui

    if _OS == "Windows":
        try:
            import ctypes
            import winreg
            sandbox["ctypes"] = ctypes
            sandbox["winreg"] = type("winreg", (), {
                # Sadece okuma
                "OpenKey":      winreg.OpenKey,
                "QueryValueEx": winreg.QueryValueEx,
                "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
            })()
        except ImportError:
            pass

    return sandbox


# ── 2.1 — validação do código gerado pela IA ────────────────────────────────
# A "caixa de areia" abaixo só esconde os módulos; a regra "não apague, não rode
# programas" estava apenas no texto do pedido à IA. Agora o código é lido (AST)
# ANTES de rodar e recusado se tentar sair da caixa, apagar, mover ou executar.
_CHAMADAS_PROIBIDAS = frozenset({
    "eval", "exec", "compile", "open", "getattr", "setattr", "delattr", "globals",
    "locals", "vars", "input", "breakpoint", "__import__", "memoryview", "type",
    # apagar / mover / sobrescrever
    # ("replace" com 1 argumento é Path.replace — mover/sobrescrever; com 2 é
    # str.replace, que é inofensivo. Tratado à parte na função abaixo.)
    "unlink", "rmdir", "rmtree", "removedirs", "rename", "renames",
    "move", "truncate", "chmod", "chown", "symlink_to", "hardlink_to",
    # 3.5.0 — escrever também sobrescreve: "sem escrita" estava só no texto do pedido à IA
    "write_text", "write_bytes", "writelines",
    # rodar outros programas
    "system", "popen", "Popen", "spawn", "startfile", "run", "call", "check_output",
})
_CTYPES_OK = frozenset({"windll", "c_int", "c_uint", "c_long", "c_ulong", "c_short",
                        "c_ushort", "c_wchar_p", "c_char_p", "c_void_p", "byref",
                        "create_unicode_buffer", "create_string_buffer", "sizeof"})
_DLLS_OK = frozenset({"user32", "gdi32"})     # janelas e mouse — nada de kernel32/shell32
# 3.5.0 — dentro do user32 ainda há funções que desligam, bloqueiam ou fecham coisas.
# Desligar/reiniciar só passa pela confirmação do HUD (computer_settings), nunca por aqui.
_USER32_PROIBIDAS = frozenset({
    "ExitWindowsEx", "LockWorkStation", "BlockInput", "EndTask", "SwitchDesktop",
    "SetWindowsHookExA", "SetWindowsHookExW", "SendMessageA", "SendMessageW",
    "PostMessageA", "PostMessageW", "PostThreadMessageA", "PostThreadMessageW",
    "PostQuitMessage", "SendNotifyMessageA", "SendNotifyMessageW",
})


def _validar_codigo_gerado(code: str) -> str | None:
    """None se o código pode rodar; senão, o motivo da recusa (em português)."""
    import ast
    try:
        arvore = ast.parse(code, "<jarvis_desktop>", "exec")
    except SyntaxError as e:
        return f"o código gerado tem erro de sintaxe ({e.msg})"
    for no in ast.walk(arvore):
        if isinstance(no, (ast.Import, ast.ImportFrom)):
            return "importar módulos não é permitido"
        if isinstance(no, (ast.ClassDef, ast.AsyncFunctionDef, ast.Await,
                           ast.Global, ast.Nonlocal)):
            return "esse tipo de código não é permitido aqui"
        if (isinstance(no, ast.While) and isinstance(no.test, ast.Constant) and no.test.value
                and not any(isinstance(x, ast.Break) for x in ast.walk(no))):
            return "laço infinito sem 'break' não é permitido"
        if isinstance(no, ast.Name) and no.id.startswith("__"):
            return f"nome interno proibido: {no.id}"
        if isinstance(no, ast.Constant) and isinstance(no.value, str) and no.value in _USER32_PROIBIDAS:
            return f"user32.{no.value} não é permitido"      # u["ExitWindowsEx"](...)
        if isinstance(no, ast.Attribute) and no.attr in _USER32_PROIBIDAS:
            return f"user32.{no.attr} não é permitido"       # vale mesmo via variável: u = ...user32
        if isinstance(no, ast.Attribute):
            if no.attr.startswith("__") or no.attr.endswith("__"):
                return f"atributo interno proibido: {no.attr}"
            # ctypes só com a parte de janelas/mouse
            base = no.value
            if isinstance(base, ast.Name) and base.id == "ctypes" and no.attr not in _CTYPES_OK:
                return f"ctypes.{no.attr} não é permitido"
            if (isinstance(base, ast.Attribute) and base.attr == "windll"
                    and isinstance(base.value, ast.Name) and base.value.id == "ctypes"
                    and no.attr not in _DLLS_OK):
                return f"windll.{no.attr} não é permitido"
        if isinstance(no, ast.Call):
            f = no.func
            nome = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
            if nome in _CHAMADAS_PROIBIDAS:
                return f"a chamada '{nome}' não é permitida"
            if nome == "replace" and len(no.args) + len(no.keywords) < 2:
                return "mover/sobrescrever arquivos (Path.replace) não é permitido"
    return None


_TEMPO_MAXIMO_S = 60


def _execute_generated_code(code: str, player=None) -> str:
    if not code or code.strip() == "UNSAFE":
        return "This action cannot be performed safely."

    # Kod temizleme
    if code.startswith("```"):
        lines = code.split("\n")
        code  = "\n".join(lines[1:-1]).strip()

    motivo = _validar_codigo_gerado(code)
    if motivo:
        print(f"[Desktop] código recusado: {motivo}\nCode:\n{code[:300]}")
        return f"Não executei: {motivo}."

    sandbox      = _build_sandbox()
    output_lines = []
    sandbox["__builtins__"]["print"] = lambda *a: output_lines.append(" ".join(str(x) for x in a))

    # Roda numa thread própria: um laço infinito gerado pela IA não prende mais
    # a ferramenta para sempre (a thread é daemon e some quando o NEXUS fecha).
    import threading
    resultado: dict = {}

    def _rodar():
        try:
            exec(compile(code, "<jarvis_desktop>", "exec"), sandbox)
            resultado["ok"] = True
        except Exception as e:
            resultado["erro"] = e

    t = threading.Thread(target=_rodar, daemon=True, name="nexus-desktop-codigo")
    t.start()
    t.join(_TEMPO_MAXIMO_S)
    if t.is_alive():
        print(f"[Desktop] código passou de {_TEMPO_MAXIMO_S}s — abandonado\nCode:\n{code[:300]}")
        return f"A ação passou de {_TEMPO_MAXIMO_S} segundos e foi abandonada."
    if "erro" in resultado:
        e = resultado["erro"]
        print(f"[Desktop] Exec error: {e}\nCode:\n{code[:300]}")
        return f"Execution error: {e}"
    return "\n".join(output_lines) if output_lines else "Done."


def _ask_gemini_for_desktop_action(task: str) -> str:

    from google import genai as _genai

    desktop = str(_get_desktop())

    os_specific = ""
    if _OS == "Windows":
        os_specific = "- ctypes (Windows API calls, read-only)\n- winreg (registry READ only)"
    elif _OS == "Darwin":
        os_specific = "- subprocess is NOT available; use pyautogui or Path only"
    else:
        os_specific = "- subprocess is NOT available; use pyautogui or Path only"

    prompt = f"""You are a desktop automation assistant.
Current OS: {_OS}
Desktop path: {desktop}

Generate safe Python code to accomplish the task below.
Allowed modules ONLY:
- pyautogui (mouse, keyboard — if needed)
- pathlib.Path (file/folder inspection only, no deletion)
- shutil.copy2, shutil.copytree, shutil.disk_usage (NO move, NO rmtree)
- os_path (os.path equivalent, read-only)
- time.sleep
{os_specific}

Hard rules:
- NO file deletion (no unlink, no rmtree, no remove)
- NO subprocess calls
- NO exec() or eval() inside the code
- NO import statements (modules are pre-injected)
- NO file write operations except explicitly requested
- If task cannot be done safely with these tools, output exactly: UNSAFE

Output ONLY the Python code. No explanation, no markdown, no backticks.

Task: {task}"""

    try:
        from core import gemini
        response = gemini.call(prompt, tier=gemini.SMART, timeout_ms=30_000)
        if response is None:
            return "ERROR: every Gemini model on the ladder failed"
        code = (response.text or "").strip()
        if code.startswith("```"):
            lines = code.split("\n")
            code  = "\n".join(lines[1:-1]).strip()
        return code
    except Exception as e:
        return f"ERROR: {e}"

def set_wallpaper(image_path: str) -> str:
    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        return f"Image not found: {image_path}"
    if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
        return f"Unsupported format: {path.suffix}. Use jpg, png, bmp or webp."

    try:
        if _OS == "Windows":
            import ctypes
            if path.suffix.lower() in {".webp", ".png"}:
                try:
                    from PIL import Image
                    _fd, _bmp = tempfile.mkstemp(suffix=".bmp", prefix="nexus_wall_")
                    os.close(_fd)
                    bmp_path = Path(_bmp)
                    Image.open(path).convert("RGB").save(bmp_path, "BMP")
                    path = bmp_path
                except ImportError:
                    pass 
            ctypes.windll.user32.SystemParametersInfoW(20, 0, str(path), 3)
            return f"Wallpaper set: {path.name}"

        elif _OS == "Darwin":
            script = (
                f'tell application "System Events" to tell every desktop to '
                f'set picture to POSIX file "{path}"'
            )
            subprocess.run(["osascript", "-e", script], capture_output=True)
            return f"Wallpaper set: {path.name}"

        else:
            desktop_env = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
            uri = f"file://{path}"

            if "gnome" in desktop_env or "unity" in desktop_env:
                subprocess.run([
                    "gsettings", "set", "org.gnome.desktop.background",
                    "picture-uri", uri
                ], capture_output=True)
                subprocess.run([
                    "gsettings", "set", "org.gnome.desktop.background",
                    "picture-uri-dark", uri
                ], capture_output=True)

            elif "kde" in desktop_env:
                # KDE Plasma
                script = f"""
var allDesktops = desktops();
for (var i = 0; i < allDesktops.length; i++) {{
    d = allDesktops[i];
    d.wallpaperPlugin = "org.kde.image";
    d.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
    d.writeConfig("Image", "file://{path}");
}}
"""
                subprocess.run(
                    ["qdbus", "org.kde.plasmashell", "/PlasmaShell",
                     "org.kde.PlasmaShell.evaluateScript", script],
                    capture_output=True
                )

            elif "xfce" in desktop_env:
                subprocess.run([
                    "xfconf-query", "-c", "xfce4-desktop",
                    "-p", "/backdrop/screen0/monitor0/workspace0/last-image",
                    "-s", str(path)
                ], capture_output=True)

            else:
                result = subprocess.run(
                    ["feh", "--bg-scale", str(path)],
                    capture_output=True
                )
                if result.returncode != 0:
                    return (
                        f"Could not set wallpaper automatically on {desktop_env}. "
                        f"Try manually or install 'feh'."
                    )

            return f"Wallpaper set: {path.name}"

    except Exception as e:
        return f"Could not set wallpaper: {e}"


def set_wallpaper_from_url(url: str) -> str:
    """Baixa uma imagem (só http/https, com limite de tempo e de tamanho) e põe
    como papel de parede. 2.1: antes aceitava qualquer esquema (file://...) e não
    tinha timeout."""
    tmp = None
    try:
        import urllib.parse
        import urllib.request
        if urllib.parse.urlparse(url).scheme.lower() not in ("http", "https"):
            return "Só consigo baixar imagens de endereços http ou https."
        suffix = Path(url.split("?")[0]).suffix or ".jpg"
        fd, nome = tempfile.mkstemp(suffix=suffix, prefix="nexus_wall_")
        tmp = Path(nome)
        limite = 40 * 1024 * 1024
        with urllib.request.urlopen(url, timeout=20) as resp, os.fdopen(fd, "wb") as out:
            baixado = 0
            while True:
                bloco = resp.read(65536)
                if not bloco:
                    break
                baixado += len(bloco)
                if baixado > limite:
                    return "A imagem é grande demais (limite de 40 MB)."
                out.write(bloco)
        return set_wallpaper(str(tmp))
    except Exception as e:
        return f"Could not download wallpaper: {e}"
    finally:
        if tmp is not None:
            try:
                tmp.unlink()
            except Exception:
                _engolida("actions/desktop.py:398")


def get_current_wallpaper() -> str:
    try:
        if _OS == "Windows":
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop"
            )
            val, _ = winreg.QueryValueEx(key, "Wallpaper")
            winreg.CloseKey(key)
            return f"Current wallpaper: {val}"

        elif _OS == "Darwin":
            script = (
                'tell application "System Events" to get picture of desktop 1'
            )
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True
            )
            return f"Current wallpaper: {result.stdout.strip()}"

        else:
            desktop_env = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
            if "gnome" in desktop_env or "unity" in desktop_env:
                result = subprocess.run(
                    ["gsettings", "get", "org.gnome.desktop.background", "picture-uri"],
                    capture_output=True, text=True
                )
                return f"Current wallpaper: {result.stdout.strip()}"
            return "Wallpaper path retrieval not supported for this desktop environment."

    except Exception as e:
        return f"Could not get wallpaper: {e}"

FILE_TYPE_MAP = {
    "Images":      {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico", ".heic"},
    "Documents":   {".pdf", ".doc", ".docx", ".txt", ".xls", ".xlsx",
                    ".ppt", ".pptx", ".csv", ".odt", ".ods", ".odp"},
    "Videos":      {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v"},
    "Music":       {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"},
    "Archives":    {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
    "Code":        {".py", ".js", ".ts", ".html", ".css", ".json", ".xml",
                    ".cpp", ".java", ".cs", ".go", ".rs", ".sh", ".php"},
    "Executables": {".exe", ".msi", ".bat", ".cmd", ".sh", ".appimage", ".deb", ".rpm"},
}

_SKIP_EXTENSIONS = {
    "Windows": {".lnk", ".url"},
    "Darwin":  {".webloc"},
    "Linux":   {".desktop"},
}



def _win_desktop_listview():
    """Acha a lista de ícones da área de trabalho do Windows (SysListView32)."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    found = []

    def _find_defview(hwnd, _lparam):
        dv = user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None)
        if dv:
            found.append(dv)
            return False
        return True

    # Em algumas versões o Explorer põe a área de trabalho num WorkerW ao lado do Progman.
    progman = user32.FindWindowW("Progman", None)
    dv = user32.FindWindowExW(progman, None, "SHELLDLL_DefView", None) if progman else 0
    if dv:
        found.append(dv)
    else:
        proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(proto(_find_defview), 0)
    if not found:
        return 0
    return user32.FindWindowExW(found[0], None, "SysListView32", None)


def arrange_desktop_icons() -> str:
    """Organiza os ÍCONES da área de trabalho na tela, em grade. Não cria pastas
    e não move arquivos."""
    import platform as _pf
    system = _pf.system()
    if system == "Windows":
        try:
            import ctypes
            LVM_ARRANGE = 0x1016          # LVM_FIRST + 22
            LVA_SNAPTOGRID = 5            # alinha os ícones à grade, em ordem
            lv = _win_desktop_listview()
            if not lv:
                return "Não encontrei os ícones da área de trabalho para organizar."
            ctypes.windll.user32.SendMessageW(lv, LVM_ARRANGE, LVA_SNAPTOGRID, 0)
            return "Ícones da área de trabalho organizados em ordem. Nenhum arquivo foi movido."
        except Exception as e:
            return f"Não consegui organizar os ícones: {e}"
    if system == "Darwin":
        import subprocess
        try:
            subprocess.run(["osascript", "-e",
                            'tell application "Finder" to clean up desktop'],
                           check=True, timeout=15)
            return "Ícones da área de trabalho organizados. Nenhum arquivo foi movido."
        except Exception as e:
            return f"Não consegui organizar os ícones no Mac: {e}"
    return ("Organizar os ícones na tela ainda não é suportado neste sistema. "
            "Posso listar seus arquivos por tipo, sem mover nada.")


def organize_desktop(mode: str = "by_type") -> str:
    """1.4.2 — os arquivos soltos vão para pastas por tipo (core/organizador.py)."""
    from core.organizador import organizar
    m = str(mode or "").lower()
    return organizar("data" if m in ("by_date", "data", "date") else "tipo",
                     simular=m in ("preview", "simular"))


def list_desktop() -> str:
    desktop = _get_desktop()
    items   = []
    for item in sorted(desktop.iterdir()):
        if item.name.startswith("."):
            continue
        if item.is_dir():
            try:
                count = len(list(item.iterdir()))
            except PermissionError:
                count = "?"
            items.append(f"📁 {item.name}/ ({count} items)")
        else:
            size     = item.stat().st_size
            size_str = (
                f"{size / 1024:.1f} KB" if size < 1024 * 1024
                else f"{size / 1024 / 1024:.1f} MB"
            )
            items.append(f"📄 {item.name} ({size_str})")

    if not items:
        return "Desktop is empty."
    return f"Desktop ({len(items)} items):\n" + "\n".join(items)


def clean_desktop() -> str:
    desktop     = _get_desktop()
    skip_exts   = _SKIP_EXTENSIONS.get(_OS, set())
    today       = agora().strftime("%Y-%m-%d")
    archive_dir = desktop / f"Desktop Archive {today}"
    archive_dir.mkdir(exist_ok=True)

    moved = 0
    for item in desktop.iterdir():
        if item.is_dir() or item.name.startswith("."):
            continue
        if item.suffix.lower() in skip_exts:
            continue
        new_path = archive_dir / item.name
        if not new_path.exists():
            shutil.move(str(item), str(new_path))
            moved += 1

    return f"Desktop cleaned: {moved} files archived to '{archive_dir.name}'."


def get_desktop_stats() -> str:
    desktop    = _get_desktop()
    files      = [i for i in desktop.iterdir() if i.is_file()]
    folders    = [i for i in desktop.iterdir() if i.is_dir()]
    total_size = sum(f.stat().st_size for f in files if f.exists())
    size_str   = (
        f"{total_size / 1024:.1f} KB" if total_size < 1024 * 1024
        else f"{total_size / 1024 / 1024:.1f} MB"
    )
    return (
        f"Desktop stats ({_OS}):\n"
        f"  Files   : {len(files)}\n"
        f"  Folders : {len(folders)}\n"
        f"  Size    : {size_str}\n"
        f"  Path    : {desktop}"
    )

def desktop_control(
    parameters: dict = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    parameters:
        action : wallpaper | wallpaper_url | current_wallpaper |
                 organize  | clean | list | stats |
                 task (AI-powered)
        path   : image path for 'wallpaper'
        url    : image URL for 'wallpaper_url'
        mode   : 'by_type' or 'by_date' for 'organize'
        task   : natural language description for AI-powered actions
    """
    params = parameters or {}
    action = params.get("action", "").lower().strip()
    task   = params.get("task", "").strip()

    if player:
        player.write_log(f"[desktop] {action or task[:40]}")

    try:
        if action == "wallpaper":
            path = params.get("path", "")
            return set_wallpaper(path) if path else "No image path provided."

        elif action == "wallpaper_url":
            url = params.get("url", "")
            return set_wallpaper_from_url(url) if url else "No URL provided."

        elif action == "current_wallpaper":
            return get_current_wallpaper()

        elif action == "organize":
            # 1.4.2 — organiza de verdade: arquivos em pastas por tipo (ou por mês)
            return organize_desktop(params.get("mode", "by_type"))

        elif action == "undo_organize":
            from core.organizador import desfazer
            return desfazer()

        elif action == "arrange_icons":
            return arrange_desktop_icons()

        elif action == "clean":
            return clean_desktop()

        elif action == "list":
            return list_desktop()

        elif action == "stats":
            return get_desktop_stats()

        elif action == "task" or task:
            actual_task = task or params.get("description", "")
            if not actual_task:
                return "Please describe what you want to do on the desktop."

            print(f"[Desktop] Asking Gemini: {actual_task}")
            if player:
                player.write_log("[Desktop] Generating action...")

            code = _ask_gemini_for_desktop_action(actual_task)
            return _execute_generated_code(code, player=player)

        else:
            if action:
                code = _ask_gemini_for_desktop_action(action)
                return _execute_generated_code(code, player=player)
            return "No action or task specified."

    except Exception as e:
        print(f"[Desktop] Error: {e}")
        return f"Desktop control error: {e}"


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "desktop_control",
    "description": (
        "Controls the desktop (área de trabalho): wallpaper / papel de parede, "
        "organize / 'organiza a área de trabalho' (moves the loose files into folders "
        "on the desktop: Imagens, Documentos, Planilhas, Apresentações, Vídeos, Músicas, "
        "Compactados, Instaladores, Código, Outros — shortcuts and folders stay; "
        "mode by_date = by month, mode preview = only say what would move), undo_organize "
        "/ 'desfaz a organização' (puts every file back), arrange_icons (only lines the "
        "icons up), clean, list / 'o que tem na minha área de trabalho', "
        "stats, or a free-form natural language task."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "wallpaper | wallpaper_url | current_wallpaper | organize | undo_organize | arrange_icons | clean | list | stats | task"
            },
            "path": {
                "type": "STRING",
                "description": "Image path for wallpaper"
            },
            "url": {
                "type": "STRING",
                "description": "Image URL for wallpaper_url"
            },
            "mode": {
                "type": "STRING",
                "description": "For organize: by_type (default), by_date (folders by month) or preview (only list what would move)"
            },
            "task": {
                "type": "STRING",
                "description": "Natural language desktop task"
            }
        },
        "required": [
            "action"
        ]
    },
    "handler": desktop_control,
}
