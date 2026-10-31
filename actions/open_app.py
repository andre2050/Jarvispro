import time
import subprocess
import platform
import shutil
from core.protecao import engolida as _engolida

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

_SYSTEM = platform.system()

_APP_ALIASES: dict[str, dict[str, str]] = {

    "chrome":             {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "google chrome":      {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "firefox":            {"Windows": "firefox",                 "Darwin": "Firefox",              "Linux": "firefox"},
    "edge":               {"Windows": "msedge",                  "Darwin": "Microsoft Edge",       "Linux": "microsoft-edge"},
    "brave":              {"Windows": "brave",                   "Darwin": "Brave Browser",        "Linux": "brave-browser"},
    "safari":             {"Windows": "msedge",                  "Darwin": "Safari",               "Linux": "firefox"},
    "opera":              {"Windows": "opera",                   "Darwin": "Opera",                "Linux": "opera"},
    "whatsapp":           {"Windows": "WhatsApp",                "Darwin": "WhatsApp",             "Linux": "whatsapp"},
    "telegram":           {"Windows": "Telegram",                "Darwin": "Telegram",             "Linux": "telegram"},
    "discord":            {"Windows": "Discord",                 "Darwin": "Discord",              "Linux": "discord"},
    "slack":              {"Windows": "Slack",                   "Darwin": "Slack",                "Linux": "slack"},
    "zoom":               {"Windows": "Zoom",                    "Darwin": "zoom.us",              "Linux": "zoom"},
    "teams":              {"Windows": "msteams",                 "Darwin": "Microsoft Teams",      "Linux": "teams"},
    "skype":              {"Windows": "skype",                   "Darwin": "Skype",                "Linux": "skype"},
    "signal":             {"Windows": "signal",                  "Darwin": "Signal",               "Linux": "signal"},
    "spotify":            {"Windows": "Spotify",                 "Darwin": "Spotify",              "Linux": "spotify"},
    "vlc":                {"Windows": "vlc",                     "Darwin": "VLC",                  "Linux": "vlc"},
    "netflix":            {"Windows": "Netflix",                 "Darwin": "Netflix",              "Linux": "firefox"},
    "vscode":             {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "visual studio code": {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "code":               {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "terminal":           {"Windows": "wt",                      "Darwin": "Terminal",             "Linux": "x-terminal-emulator"},
    "cmd":                {"Windows": "cmd.exe",                 "Darwin": "Terminal",             "Linux": "bash"},
    "prompt de comando":  {"Windows": "cmd.exe",                 "Darwin": "Terminal",             "Linux": "bash"},
    "linha de comando":   {"Windows": "cmd.exe",                 "Darwin": "Terminal",             "Linux": "bash"},
    "webcam":             {"Windows": "camera",                  "Darwin": "Photo Booth",          "Linux": "cheese"},
    "powershell":         {"Windows": "powershell.exe",          "Darwin": "Terminal",             "Linux": "bash"},
    "postman":            {"Windows": "Postman",                 "Darwin": "Postman",              "Linux": "postman"},
    "git":                {"Windows": "git-bash",                "Darwin": "Terminal",             "Linux": "bash"},
    "figma":              {"Windows": "Figma",                   "Darwin": "Figma",                "Linux": "figma"},
    "blender":            {"Windows": "blender",                 "Darwin": "Blender",              "Linux": "blender"},
    "word":               {"Windows": "winword",                 "Darwin": "Microsoft Word",       "Linux": "libreoffice --writer"},
    "excel":              {"Windows": "excel",                   "Darwin": "Microsoft Excel",      "Linux": "libreoffice --calc"},
    "powerpoint":         {"Windows": "powerpnt",                "Darwin": "Microsoft PowerPoint", "Linux": "libreoffice --impress"},
    "libreoffice":        {"Windows": "soffice",                 "Darwin": "LibreOffice",          "Linux": "libreoffice"},
    "notepad":            {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "textedit":           {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "explorer":           {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "file explorer":      {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "finder":             {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "task manager":       {"Windows": "taskmgr.exe",             "Darwin": "Activity Monitor",     "Linux": "gnome-system-monitor"},
    "settings":           {"Windows": "ms-settings:",            "Darwin": "System Preferences",   "Linux": "gnome-control-center"},
    "calculator":         {"Windows": "calc.exe",                "Darwin": "Calculator",           "Linux": "gnome-calculator"},
    "paint":              {"Windows": "mspaint.exe",             "Darwin": "Preview",              "Linux": "gimp"},
    # Websites people call "apps": opened in the default browser (see _open_url).
    "youtube":            {"Windows": "https://www.youtube.com", "Darwin": "https://www.youtube.com", "Linux": "https://www.youtube.com"},
    "instagram":          {"Windows": "Instagram",              "Darwin": "Instagram",            "Linux": "firefox"},
    "tiktok":             {"Windows": "TikTok",                  "Darwin": "TikTok",               "Linux": "firefox"},
    "notion":             {"Windows": "Notion",                  "Darwin": "Notion",               "Linux": "notion"},
    "obsidian":           {"Windows": "Obsidian",                "Darwin": "Obsidian",             "Linux": "obsidian"},
    "capcut":             {"Windows": "CapCut",                  "Darwin": "CapCut",               "Linux": "capcut"},
    "steam":              {"Windows": "steam",                   "Darwin": "Steam",                "Linux": "steam"},
    "epic":               {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
    "epic games":         {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
}


def _normalize(raw: str) -> str:
    key = raw.lower().strip()

    if key in _APP_ALIASES:
        return _APP_ALIASES[key].get(_SYSTEM, raw)

    for alias_key, os_map in _APP_ALIASES.items():
        if alias_key in key or key in alias_key:
            return os_map.get(_SYSTEM, raw)

    return raw


def _sem_acento(texto: str) -> str:
    """'Câmera' → 'camera'. 2.4.1 — 'câmera' não achava o app 'Camera HD'."""
    import unicodedata
    t = unicodedata.normalize("NFKD", str(texto or "").lower().strip())
    return "".join(c for c in t if not unicodedata.combining(c))


_PALAVRAS_VAZIAS = {"do", "da", "de", "dos", "das", "o", "a", "os", "as", "the", "app", "aplicativo", "programa"}


def _por_palavras(key: str, nomes) -> str | None:
    """Todas as palavras pedidas aparecem no nome, em qualquer ordem: 'windows backup' e
    'backup windows' → 'backup do windows' (2.4.1). O nome mais curto ganha."""
    import re
    pedidas = {p for p in re.split(r"[^a-z0-9.]+", key) if p and p not in _PALAVRAS_VAZIAS}
    if not pedidas or not any(len(p) >= 3 for p in pedidas):
        return None
    achados = sorted((n for n in nomes if pedidas <= set(re.split(r"[^a-z0-9.]+", n))), key=len)
    return achados[0] if achados else None


def _iniciar_exe(exe: str) -> None:
    """Inicia um executável achado no PATH.

    2.4.1 — antes ia com stdout/stderr jogados fora e sem janela própria: o cmd e o
    python abriam em branco (ou dentro do console escondido do NEXUS) e pareciam não
    ter aberto. Agora programas de console ganham a própria janela, começando na pasta
    do usuário. Para programas com janela (Chrome, Bloco de Notas…) a flag não muda nada.
    """
    import os
    flags = subprocess.CREATE_NEW_CONSOLE if _SYSTEM == "Windows" else 0
    subprocess.Popen([exe], creationflags=flags, cwd=os.path.expanduser("~"))

# ── Windows: Start Menu shortcuts ─────────────────────────────────────────────
# Most desktop apps (Spotify, Discord, Steam, Office...) are not on PATH, so the
# old route was to press Win, type the name and hit Enter — about 4 seconds of
# simulated keyboard per app, and impossible to do for several apps at once.
# Every installed app leaves a .lnk in one of these two folders, and opening
# that shortcut is instant and needs no keyboard at all.
_SKIP_SHORTCUT_WORDS = ("uninstall", "desinstalar", "remove", "readme", "help",
                        "ajuda", "manual", "website", "site")
_shortcut_index: dict[str, str] | None = None


def _start_menu_shortcuts() -> dict[str, str]:
    global _shortcut_index
    if _shortcut_index is not None:
        return _shortcut_index
    import os
    from pathlib import Path
    index: dict[str, str] = {}
    roots = [os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
             os.path.expandvars(r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs")]
    for root in roots:
        try:
            for lnk in Path(root).rglob("*.lnk"):
                stem = _sem_acento(lnk.stem)
                if any(w in stem for w in _SKIP_SHORTCUT_WORDS):
                    continue
                index.setdefault(stem, str(lnk))
        except Exception:
            continue
    _shortcut_index = index
    return index


def _find_shortcut(app_name: str) -> str | None:
    """Exact shortcut name first, then one that starts with it, then the
    closest name. Short or empty names never fuzzy-match."""
    key = _sem_acento(app_name)
    if len(key) < 2:
        return None
    idx = _start_menu_shortcuts()
    if key in idx:
        return idx[key]
    # "visual studio" → "visual studio code", but "word" must not → "wordpad"
    starts = sorted((s for s in idx
                     if s.startswith(key) and not s[len(key)].isalnum()), key=len)
    if starts:
        return idx[starts[0]]
    # "chrome" → "google chrome", "excel" → "microsoft excel" (palavra inteira:
    # "word" continua sem virar "wordpad")
    import re
    padrao = re.compile(rf"\b{re.escape(key)}\b")
    contem = sorted((s for s in idx if padrao.search(s)), key=len)
    if contem:
        return idx[contem[0]]
    palavras = _por_palavras(key, idx)
    if palavras:
        return idx[palavras]
    if len(key) >= 4:
        import difflib
        close = difflib.get_close_matches(key, list(idx), n=1, cutoff=0.85)
        if close:
            return idx[close[0]]
    return None


# ── Windows: apps da Microsoft Store e todo o menu Iniciar (1.4) ──────────────
# WhatsApp, Spotify da Store, Netflix, Calculadora... não deixam .lnk nas pastas
# do menu Iniciar — por isso caíam na "digitação" no Iniciar, que dizia "abri"
# mesmo quando não abria nada. O Windows lista todos eles (Get-StartApps) e
# abre qualquer um por AppsFolder, sem teclado.
_store_index: dict[str, str] | None = None
_store_lock = None


def _store_apps() -> dict[str, str]:
    global _store_index, _store_lock
    import threading
    if _store_lock is None:
        _store_lock = threading.Lock()
    with _store_lock:
        if _store_index is not None:
            return _store_index
        index: dict[str, str] = {}
        if _SYSTEM == "Windows":
            try:
                import json as _json
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
                     "Get-StartApps | ConvertTo-Json -Compress"],
                    capture_output=True, timeout=20)
                dados = _json.loads(r.stdout.decode("utf-8", "ignore") or "[]")
                if isinstance(dados, dict):
                    dados = [dados]
                for d in dados:
                    nome, appid = str(d.get("Name") or ""), str(d.get("AppID") or "")
                    if nome and appid and not any(w in nome.lower() for w in _SKIP_SHORTCUT_WORDS):
                        index.setdefault(_sem_acento(nome), appid)
            except Exception as e:
                print(f"[open_app] Get-StartApps falhou: {e}")
        _store_index = index
        return index


def _find_store_app(app_name: str) -> str | None:
    key = _sem_acento(app_name)
    if len(key) < 2:
        return None
    idx = _store_apps()
    if key in idx:
        return idx[key]
    import re
    padrao = re.compile(rf"\b{re.escape(key)}\b")
    contem = sorted((n for n in idx if padrao.search(n)), key=len)
    if contem:
        return idx[contem[0]]
    palavras = _por_palavras(key, idx)
    if palavras:
        return idx[palavras]
    if len(key) >= 4:
        import difflib
        close = difflib.get_close_matches(key, list(idx), n=1, cutoff=0.85)
        if close:
            return idx[close[0]]
    return None


def _open_store_app(appid: str) -> bool:
    try:
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{appid}"])
        return True
    except Exception as e:
        print(f"[open_app] AppsFolder falhou: {e}")
        return False


def suggestions(app_name: str, n: int = 3) -> list[str]:
    """Nomes de programas instalados parecidos com o que foi pedido."""
    import difflib
    key = _sem_acento(app_name)
    nomes = set()
    if _SYSTEM == "Windows":
        nomes |= set(_start_menu_shortcuts()) | set(_store_apps())
    elif _SYSTEM == "Linux":
        from pathlib import Path as _P
        for d in ("/usr/share/applications", str(_P.home() / ".local/share/applications")):
            try:
                nomes |= {f.stem.lower() for f in _P(d).glob("*.desktop")}
            except Exception:
                _engolida("actions/open_app.py:268")
    contem = sorted((x for x in nomes if key and key in x), key=len)[:n]
    parecidos = difflib.get_close_matches(key, sorted(nomes), n=n, cutoff=0.6)
    out = []
    for x in contem + parecidos:
        if x not in out:
            out.append(x)
    return [x.title() for x in out[:n]]


def _process_names() -> set[str]:
    """'nome#pid' de cada processo. 2.4.1 — só o nome não via um cmd ou python NOVO
    quando já havia outro rodando (o próprio NEXUS é python.exe)."""
    if not _PSUTIL:
        return set()
    try:
        return {f"{(p.info.get('name') or '').lower()}#{p.pid}" for p in psutil.process_iter(["name"])}
    except Exception:
        return set()


def _subiu(antes: set[str], agora_: set[str], *nomes: str) -> bool:
    """Apareceu um processo com nome novo (como antes da 2.4.1) ou um processo novo
    cujo nome bate com o que foi pedido (cmd.exe, python.exe…)."""
    import re
    tokens = {t for n in nomes for t in re.split(r"[^a-z0-9]+", _sem_acento(n))
              if len(t) >= 3 and t != "exe"}
    nomes_antes = {e.rsplit("#", 1)[0] for e in antes}
    for e in agora_ - antes:
        nome = e.rsplit("#", 1)[0]
        if nome not in nomes_antes or any(t in nome for t in tokens):
            return True
    return False


def _confirm_later(app_name: str, before: set[str], player=None, wait: float = 8.0) -> None:
    """Confere, sem segurar a resposta, se o programa apareceu nos processos.
    Se não apareceu, avisa na conversa e no núcleo I.S.A."""
    if not _PSUTIL or not before:
        return
    import threading

    def _check():
        import re
        tokens = [t for t in re.split(r"[^a-z0-9]+", app_name.lower()) if len(t) >= 3]
        if not tokens:
            return
        fim = time.time() + wait
        while time.time() < fim:
            if _subiu(before, _process_names(), app_name):
                return
            time.sleep(0.8)
        agora_ = {e.rsplit("#", 1)[0] for e in _process_names()}
        if any(any(t in n for t in tokens) for n in agora_):
            return          # já estava aberto (só veio para a frente)
        msg = (f"{app_name} não apareceu depois de {int(wait)} s — talvez não esteja "
               f"instalado, ou esteja demorando para abrir.")
        try:
            if player:
                player.write_log(f"SYS: ⚠ {msg}")
            from core import isa as _isa
            _isa.registrar("erro", f"Abrir {app_name}: não confirmado", msg, origem="automação")
        except Exception:
            _engolida("actions/open_app.py:331")

    threading.Thread(target=_check, daemon=True, name="open-app-check").start()


def _prewarm() -> None:
    """Monta as listas de programas em segundo plano ao iniciar (Windows),
    para o primeiro "abre o X" não esperar o PowerShell."""
    if _SYSTEM != "Windows":
        return
    import threading

    def _go():
        try:
            _start_menu_shortcuts()
            _store_apps()
        except Exception:
            _engolida("actions/open_app.py:348")
    threading.Thread(target=_go, daemon=True, name="open-app-warm").start()


def _is_url(target: str) -> bool:
    return str(target or "").lower().startswith(("http://", "https://"))


def _open_url(url: str) -> bool:
    """A website in the default browser — works the same on every OS."""
    try:
        import webbrowser
        return bool(webbrowser.open(url, new=2))
    except Exception as e:
        print(f"[open_app] could not open {url}: {e}")
        return False


def launch_direct(app_name: str) -> bool:
    """Start an app WITHOUT touching the keyboard and without waiting for it.

    Used by routines to open several apps at the same time. Returns False when
    the only way left would be typing into the Start Menu / Spotlight — the
    caller then falls back to open_app() for that one app, one at a time.
    Apps: Windows only for now. Websites (YouTube...): every system.
    """
    import os
    name = (app_name or "").strip()
    if not name:
        return False
    try:
        from core import preferences as _prefs
        name = (_prefs.get("app_aliases") or {}).get(name.lower(), name)
    except Exception:
        _engolida("actions/open_app.py:382")
    if _is_url(name) or _is_url(_normalize(name)):
        return _open_url(name if _is_url(name) else _normalize(name))
    if _SYSTEM != "Windows":
        return False
    try:
        # 1) a full path the user configured: C:\...\app.exe or a .lnk
        if os.path.exists(name):
            os.startfile(name)
            return True
        normalized = _normalize(name)
        # 2) on PATH (code, chrome, notepad.exe...)
        for cand in (normalized, name):
            # 2.1 — antes isto passava o TEXTO digitado/falado para o shell
            # (shell=True). Um nome como "calc.x & outra-coisa" achava "calc" no
            # PATH e o shell executava também o que vinha depois do "&". Agora só
            # o caminho que o próprio PATH resolveu é iniciado, sem shell.
            exe = shutil.which(cand) or shutil.which(cand.split(".")[0])
            if exe:
                _iniciar_exe(exe)
                return True
        # 3) a URI (ms-settings:, spotify:, steam://...)
        if ":" in normalized:
            os.startfile(normalized)
            return True
        # 4) the Start Menu shortcut
        for cand in (name, normalized):
            lnk = _find_shortcut(cand)
            if lnk:
                os.startfile(lnk)
                return True
        # 5) apps da Microsoft Store (AppsFolder)
        for cand in (name, normalized):
            appid = _find_store_app(cand)
            if appid:
                return _open_store_app(appid)
    except Exception as e:
        print(f"[open_app] direct launch of {app_name!r} failed: {e}")
    return False


def _launch_windows(app_name: str) -> bool:
    """Abre sem esperar e sem digitar. Ordem: caminho, PATH, URI, atalho do
    menu Iniciar, app da Store. Só digita no Iniciar se a preferência
    open_app_busca_iniciar estiver ligada (ela dizia "abri" mesmo sem abrir)."""
    import os
    if os.path.exists(app_name):
        os.startfile(app_name)
        return True

    exe = shutil.which(app_name) or shutil.which(app_name.split(".")[0])
    if exe:
        try:
            _iniciar_exe(exe)
            return True
        except Exception as e:
            print(f"[open_app] subprocess failed: {e}")

    if ":" in app_name and not os.path.isabs(app_name):
        try:
            os.startfile(app_name)          # ms-settings:, spotify:, steam://
            return True
        except Exception as e:
            print(f"[open_app] URI failed: {e}")

    try:
        lnk = _find_shortcut(app_name)
        if lnk:
            os.startfile(lnk)
            return True
    except PermissionError:
        raise                       # vira uma mensagem clara em open_app()
    except Exception as e:
        print(f"[open_app] shortcut launch failed: {e}")

    appid = _find_store_app(app_name)
    if appid and _open_store_app(appid):
        return True

    try:
        from core import preferences as _prefs
        busca = bool(_prefs.get("open_app_busca_iniciar"))
    except Exception:
        busca = False
    if busca:
        try:
            import pyautogui
            pyautogui.PAUSE = 0.1
            pyautogui.press("win")
            time.sleep(0.7)
            pyautogui.write(app_name, interval=0.05)
            time.sleep(0.9)
            pyautogui.press("enter")
            return True
        except Exception as e:
            print(f"[open_app] Start Menu search failed: {e}")

    return False


def _launch_macos(app_name: str) -> bool:

    try:
        result = subprocess.run(
            ["open", "-a", app_name],
            capture_output=True, timeout=8
        )
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        _engolida("actions/open_app.py:493")

    try:
        result = subprocess.run(
            ["open", "-a", f"{app_name}.app"],
            capture_output=True, timeout=8
        )
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        _engolida("actions/open_app.py:504")

    binary = shutil.which(app_name) or shutil.which(app_name.lower())
    if binary:
        try:
            subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.0)
            return True
        except Exception:
            _engolida("actions/open_app.py:517")

    try:
        import pyautogui
        pyautogui.hotkey("command", "space")
        time.sleep(0.6)
        pyautogui.write(app_name, interval=0.05)
        time.sleep(0.8)
        pyautogui.press("enter")
        time.sleep(1.5)
        return True
    except Exception as e:
        print(f"[open_app] Spotlight failed: {e}")

    return False


_LINUX_TERMINAL_FALLBACKS = [
    "x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal",
    "xterm", "lxterminal", "mate-terminal", "tilix", "alacritty", "kitty",
]

def _launch_linux(app_name: str) -> bool:

    # terminal emulators: try common ones in order
    if app_name in ("x-terminal-emulator", "gnome-terminal", "terminal"):
        for term in _LINUX_TERMINAL_FALLBACKS:
            if shutil.which(term):
                try:
                    subprocess.Popen([term], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    time.sleep(1.0)
                    return True
                except Exception:
                    continue

    binary = (
        shutil.which(app_name) or
        shutil.which(app_name.lower()) or
        shutil.which(app_name.lower().replace(" ", "-")) or
        shutil.which(app_name.lower().replace(" ", "_"))
    )
    if binary:
        try:
            subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.0)
            return True
        except Exception:
            _engolida("actions/open_app.py:568")

    try:
        subprocess.run(
            ["xdg-open", app_name],
            capture_output=True, timeout=5
        )
        return True
    except Exception:
        _engolida("actions/open_app.py:577")

    for desktop_name in [
        app_name.lower(),
        app_name.lower().replace(" ", "-"),
        app_name.lower().replace(" ", ""),
    ]:
        try:
            result = subprocess.run(
                ["gtk-launch", desktop_name],
                capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return True
        except Exception:
            _engolida("actions/open_app.py:592")

    return False


_OS_LAUNCHERS = {
    "Windows": _launch_windows,
    "Darwin":  _launch_macos,
    "Linux":   _launch_linux,
}

def open_app(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    app_name = str((parameters or {}).get("app_name", "") or "").strip().strip('"').strip("'")
    try:
        from core import preferences as _prefs
        app_name = (_prefs.get("app_aliases") or {}).get(app_name.lower(), app_name)
    except Exception:
        _engolida("actions/open_app.py:614")

    if not app_name:
        return "Não consegui abrir: faltou o nome do programa."

    launcher = _OS_LAUNCHERS.get(_SYSTEM)
    if launcher is None:
        return f"Não consegui abrir: sistema não suportado ({_SYSTEM})."

    normalized = _normalize(app_name)
    print(f"[open_app] Launching: '{app_name}' → '{normalized}' ({_SYSTEM})")

    if player:
        player.write_log(f"[open_app] {app_name}")

    if _is_url(normalized):
        if _open_url(normalized):
            return f"Opened {app_name} no navegador."
        return f"Não consegui abrir {app_name}: o navegador padrão não respondeu."

    # 1.5 — 🪟 já está aberto? traz a janela para a frente em vez de abrir outra
    if _SYSTEM == "Windows":
        try:
            from core.janelas import trazer_para_frente
            titulo = trazer_para_frente(app_name) or (
                normalized.lower() != app_name.lower() and trazer_para_frente(normalized))
            if titulo:
                return (f"{app_name} was already open — I brought its window to the front "
                        f"({titulo[:60]}) instead of opening a second copy.")
        except Exception as e:
            print(f"[open_app] trazer para frente falhou: {e}")

    antes = _process_names()
    try:
        if launcher(normalized) or (normalized.lower() != app_name.lower() and launcher(app_name)):
            # 1.5 — 🤝 diz o que verificou: confere por até 1,5 s se o programa subiu
            fim = time.monotonic() + 0.7          # 2.3: antes 1,5 s — responde mais rápido
            while time.monotonic() < fim:
                time.sleep(0.1)
                if _subiu(antes, _process_names(), app_name, normalized):
                    return f"Opened {app_name} (confirmed: it is running)."
            _confirm_later(app_name, antes, player)
            return (f"[unverified] Started {app_name}, but it has not shown up yet "
                    f"(it may still be loading). Say you are opening it, not that it is open.")
    except PermissionError:
        return (f"Não consegui abrir {app_name}: o Windows negou a permissão. "
                f"Tente abrir como administrador uma vez.")
    except OSError as e:
        return f"Não consegui abrir {app_name}: {e.strerror or e}."
    except Exception as e:
        print(f"[open_app] Error: {e}")
        return f"Não consegui abrir {app_name}: {e}"

    dicas = suggestions(app_name)
    texto = f"Não consegui abrir {app_name}: não encontrei esse programa instalado."
    if _SYSTEM == "Windows" and _sem_acento(app_name) in ("camera", "a camera", "webcam"):
        # 2.4.1 — o app Câmera do Windows pode ter sido desinstalado
        texto += (" O app Câmera do Windows não está instalado neste PC; ele é grátis na Microsoft Store "
                  "(ms-windows-store://pdp/?ProductId=9WZDNCRFJBBG).")
    if dicas:
        texto += " Parecidos instalados: " + ", ".join(dicas) + "."
    texto += (" Se ele estiver instalado com outro nome, diga o nome exato do menu Iniciar "
              "ou crie um apelido em Configuração do usuário › APELIDOS DE APPS.")
    return texto


_prewarm()


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "open_app",
    "description": "Opens any application on the computer. Use this whenever the user asks to open, launch, or start any app, website, or program. Always call this tool — never just say you opened it.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "app_name": {
                "type": "STRING",
                "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
            }
        },
        "required": [
            "app_name"
        ]
    },
    "handler": open_app,
}
