"""
core/janelas.py — janelas e processos do Windows, com educação (NEXUS Pro 1.5).

    fechar_app("chrome")      🚪 fecha um aplicativo PELO NOME: compara com o que
                              está rodando, pede para fechar (WM_CLOSE, como o X
                              da janela — o programa ainda pergunta "salvar?") e
                              NUNCA mira o próprio NEXUS nem o Windows.
    trazer_para_frente("x")   🪟 se o programa já está aberto, a janela dele vem
                              para a frente em vez de abrir uma segunda cópia.
    limite_da_plataforma()    🐧 o que esta sessão NÃO consegue fazer agora (janela
                              de administrador, tela bloqueada, Wayland, macOS sem
                              permissão) — para avisar em vez de narrar um clique
                              que nunca aconteceu.

Só ctypes + psutil: nada de pacote novo.
"""
from __future__ import annotations

import os
import platform
import re
import sys
import time
import unicodedata

_OS = platform.system()

# nome falado → nome do executável (sem .exe)
APELIDOS = {
    "word": "winword", "microsoft word": "winword", "excel": "excel", "powerpoint": "powerpnt",
    "outlook": "outlook", "bloco de notas": "notepad", "notepad": "notepad",
    "calculadora": "calculatorapp", "calculator": "calculatorapp", "paint": "mspaint",
    "explorador de arquivos": "explorer", "explorador": "explorer", "file explorer": "explorer",
    "vs code": "code", "vscode": "code", "visual studio code": "code", "visual studio": "devenv",
    "edge": "msedge", "microsoft edge": "msedge", "chrome": "chrome", "google chrome": "chrome",
    "firefox": "firefox", "opera": "opera", "opera gx": "opera", "brave": "brave",
    "spotify": "spotify", "discord": "discord", "steam": "steam", "whatsapp": "whatsapp",
    "telegram": "telegram", "teams": "ms-teams", "microsoft teams": "ms-teams", "zoom": "zoom",
    "obs": "obs64", "obs studio": "obs64", "vlc": "vlc", "epic games": "epicgameslauncher",
    "gerenciador de tarefas": "taskmgr", "task manager": "taskmgr", "terminal": "windowsterminal",
    "prompt de comando": "cmd", "cmd": "cmd", "powershell": "powershell", "capcut": "capcut",
    "photoshop": "photoshop", "netflix": "netflix", "minecraft": "minecraft",
}

# Nunca: o próprio Windows. (explorer só tem as JANELAS fechadas, nunca o processo)
_SISTEMA = {"system", "idle", "csrss", "winlogon", "wininit", "services", "lsass", "smss",
            "svchost", "dwm", "fontdrvhost", "sihost", "ctfmon", "searchhost",
            "startmenuexperiencehost", "shellexperiencehost", "textinputhost", "runtimebroker",
            "registry", "memcompression", "audiodg", "spoolsv", "securityhealthservice",
            "msmpeng", "lsaiso", "conhost", "applicationframehost"}
# Classes de janela que não são "do aplicativo" (área de trabalho, barra de tarefas)
_CLASSES_PROTEGIDAS = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
                       "NotifyIconOverflowWindow"}


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"\.exe$", "", t.strip())
    return re.sub(r"[^a-z0-9 ]+", " ", t).strip()


def _base_exe(nome_proc: str) -> str:
    return _norm(re.sub(r"\.exe$", "", str(nome_proc or ""), flags=re.I)).replace(" ", "")


# ── os processos do próprio NEXUS ─────────────────────────────────────────────
def pids_do_nexus() -> set[int]:
    """O próprio processo, os "pais" (python, Nexus.exe, o console) e os filhos
    que são o próprio NEXUS (python). Nunca são alvo."""
    out = {os.getpid()}
    try:
        import psutil
        eu = psutil.Process(os.getpid())
        for p in eu.parents():
            out.add(p.pid)
        for f in eu.children(recursive=True):
            try:
                if _base_exe(f.name()).startswith(("python", "nexus", "pythonw")):
                    out.add(f.pid)
            except Exception:
                pass
    except Exception:
        pass
    return out


def _alvo_exe(nome: str) -> str:
    n = _norm(nome)
    n = re.sub(r"^(o|a|os|as|meu|minha|the|app|aplicativo|programa)\s+", "", n)
    return APELIDOS.get(n, n.replace(" ", ""))


def processos(nome: str) -> list:
    """Processos rodando que correspondem ao nome falado (sem o NEXUS e o Windows)."""
    try:
        import psutil
    except ImportError:
        return []
    alvo = _alvo_exe(nome)
    if not alvo or len(alvo) < 2:
        return []
    meus = pids_do_nexus()
    exatos, parciais = [], []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            if p.pid in meus:
                continue
            base = _base_exe(p.info.get("name") or "")
            if not base or base in _SISTEMA:
                continue
            if base == alvo:
                exatos.append(p)
            elif len(alvo) >= 4 and (base.startswith(alvo) or alvo in base):
                parciais.append(p)
        except Exception:
            continue
    return exatos or parciais


# ── janelas (Windows) ─────────────────────────────────────────────────────────
def _user32():
    import ctypes
    return ctypes.windll.user32


def janelas(pids: set[int] | None = None) -> list[tuple[int, int, str, str]]:
    """[(hwnd, pid, título, classe)] das janelas visíveis de nível superior."""
    if _OS != "Windows":
        return []
    import ctypes
    from ctypes import wintypes
    u = _user32()
    out = []
    PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _cb(hwnd, _l):
        try:
            if not u.IsWindowVisible(hwnd):
                return True
            pid = wintypes.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pids is not None and pid.value not in pids:
                return True
            n = u.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(hwnd, buf, n + 1)
            cls = ctypes.create_unicode_buffer(256)
            u.GetClassNameW(hwnd, cls, 256)
            if buf.value.strip() and cls.value not in _CLASSES_PROTEGIDAS:
                out.append((int(hwnd), int(pid.value), buf.value, cls.value))
        except Exception:
            pass
        return True

    u.EnumWindows(PROC(_cb), 0)
    return out


def _janelas_do_app(nome: str) -> list[tuple[int, int, str, str]]:
    procs = processos(nome)
    pids = {p.pid for p in procs}
    achadas = janelas(pids) if pids else []
    if achadas:
        return achadas
    # sem processo com esse nome (apps da Store, Electron…): pelo título
    alvo = _norm(nome)
    if len(alvo) < 3:
        return []
    meus = pids_do_nexus()
    return [j for j in janelas() if j[1] not in meus and alvo in _norm(j[2])]


def trazer_para_frente(nome: str) -> str | None:
    """Se o app já tem uma janela aberta, traz para a frente. Devolve o título."""
    if _OS != "Windows":
        return None
    try:
        achadas = _janelas_do_app(nome)
    except Exception:
        return None
    if not achadas:
        return None
    hwnd, _pid, titulo, _cls = achadas[0]
    try:
        import ctypes
        u = _user32()
        if u.IsIconic(hwnd):
            u.ShowWindow(hwnd, 9)                 # SW_RESTORE
        else:
            u.ShowWindow(hwnd, 5)                 # SW_SHOW
        # O Windows só deixa trocar o foco depois de uma "entrada" do usuário;
        # um toque de ALT libera (o mesmo truque que os utilitários usam).
        u.keybd_event(0x12, 0, 0, 0)
        u.keybd_event(0x12, 0, 2, 0)
        u.SetForegroundWindow(hwnd)
        u.BringWindowToTop(hwnd)
        _ = ctypes  # noqa
    except Exception:
        return None
    return titulo


def fechar_app(nome: str, forcar: bool = False, espera: float = 5.0) -> str:
    """Fecha um aplicativo pelo nome, com educação."""
    if not str(nome or "").strip():
        return "Faltou o nome do aplicativo para fechar."
    alvo = _alvo_exe(nome)
    if alvo in ("python", "pythonw", "nexus", "nexuspro") or _norm(nome) in ("nexus", "voce", "você"):
        return ("Não fecho o próprio NEXUS por aqui. Para me desligar, diga "
                "'desliga o Nexus'.")
    procs = processos(nome)
    if _OS != "Windows":
        if not procs:
            return f"Não achei '{nome}' rodando."
        for p in procs:
            try:
                p.terminate()                      # SIGTERM: o pedido educado do Unix
            except Exception:
                pass
        return f"Pedi para fechar {nome} ({len(procs)} processo(s))."
    pids = {p.pid for p in procs}
    alvos = janelas(pids) if pids else []
    if not alvos and not procs:
        alvos = _janelas_do_app(nome)
        pids = {j[1] for j in alvos}
    if not alvos and not procs:
        return f"Não achei '{nome}' aberto agora."
    if alvo == "explorer":
        alvos = [j for j in alvos if j[3] == "CabinetWClass"]   # só as pastas abertas
        if not alvos:
            return "Não há pastas do Explorador abertas para fechar."
    u = _user32()
    WM_CLOSE = 0x0010
    for hwnd, *_ in alvos:
        try:
            u.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        except Exception:
            pass
    fim = time.monotonic() + espera
    restantes = pids
    if alvo != "explorer":
        while time.monotonic() < fim:
            time.sleep(0.25)
            restantes = {p.pid for p in procs if _vivo(p)}
            if not restantes:
                break
    else:
        time.sleep(0.5)
        restantes = set()
    if not restantes:
        return f"Fechei {nome}."
    if forcar:
        for p in procs:
            try:
                if p.pid in restantes:
                    p.terminate()
            except Exception:
                pass
        return (f"{nome} não fechou sozinho; encerrei à força "
                f"(alterações não salvas foram perdidas).")
    ainda = [j[2] for j in janelas(restantes)][:2]
    extra = f" (janela: {ainda[0]!r})" if ainda else ""
    return (f"Pedi para fechar {nome}, mas ele continua aberto{extra} — provavelmente está "
            f"perguntando se você quer salvar. Responda na janela dele; se quiser forçar, "
            f"peça para fechar à força.")


def _vivo(p) -> bool:
    try:
        return p.is_running() and p.status() != "zombie"
    except Exception:
        return False


# ── honestidade da plataforma ─────────────────────────────────────────────────
def _elevado(pid: int | None = None) -> bool | None:
    if _OS != "Windows":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        k32, adv = ctypes.windll.kernel32, ctypes.windll.advapi32
        if pid is None:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        h = k32.OpenProcess(0x1000, False, pid)          # QUERY_LIMITED_INFORMATION
        if not h:
            return True        # não deu nem para olhar: trata como protegido
        tok = wintypes.HANDLE()
        try:
            if not adv.OpenProcessToken(h, 0x0008, ctypes.byref(tok)):   # TOKEN_QUERY
                return True
            elev, tam = wintypes.DWORD(), wintypes.DWORD()
            adv.GetTokenInformation(tok, 20, ctypes.byref(elev), 4, ctypes.byref(tam))  # TokenElevation
            return bool(elev.value)
        finally:
            if tok:
                k32.CloseHandle(tok)
            k32.CloseHandle(h)
    except Exception:
        return None


def _tela_bloqueada() -> bool:
    if _OS != "Windows":
        return False
    try:
        u = _user32()
        h = u.OpenInputDesktop(0, False, 0x0100)          # DESKTOP_SWITCHDESKTOP
        if not h:
            return True
        ok = u.SwitchDesktop(h)
        u.CloseDesktop(h)
        return not ok
    except Exception:
        return False


def limite_da_plataforma() -> str:
    """'' quando dá para clicar e digitar; senão, o motivo — em uma frase."""
    try:
        if _OS == "Windows":
            if _tela_bloqueada():
                return ("o computador está com a tela bloqueada (ou numa janela de segurança do "
                        "Windows): cliques e teclas não chegam até destravar")
            u = _user32()
            import ctypes
            from ctypes import wintypes
            hwnd = u.GetForegroundWindow()
            pid = wintypes.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value and pid.value not in pids_do_nexus():
                if _elevado(pid.value) and not _elevado(None):
                    return ("a janela da frente está aberta como ADMINISTRADOR e o NEXUS não: o "
                            "Windows bloqueia cliques e teclas nela (abra o NEXUS como "
                            "administrador para controlar essa janela)")
        elif _OS == "Linux":
            if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland":
                return ("esta sessão é Wayland: o Linux não deixa um programa clicar, digitar ou "
                        "fotografar outras janelas")
        elif _OS == "Darwin":
            try:
                import ctypes
                q = ctypes.cdll.LoadLibrary(
                    "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
                if not q.AXIsProcessTrusted():
                    return ("o macOS ainda não deu a permissão de Acessibilidade ao NEXUS "
                            "(Ajustes › Privacidade e Segurança › Acessibilidade)")
            except Exception:
                pass
    except Exception:
        return ""
    return ""


def limites_fixos() -> list[str]:
    """O que nunca dá nesta sessão (para o autoconhecimento do prompt)."""
    out = []
    if _OS == "Linux" and (os.environ.get("WAYLAND_DISPLAY")
                           or os.environ.get("XDG_SESSION_TYPE") == "wayland"):
        out.append("- This is a Wayland session: you cannot click, type into or capture other "
                   "windows here. Say so instead of trying.")
    if _OS == "Windows" and _elevado(None) is False:
        out.append("- You run WITHOUT administrator rights: windows opened as administrator "
                   "(installers, Task Manager, some games) ignore your clicks and keys. When a "
                   "tool reports that, tell the user plainly.")
    return out


if __name__ == "__main__":     # teste rápido: python core/janelas.py chrome
    nome = sys.argv[1] if len(sys.argv) > 1 else "notepad"
    print("processos:", [p.pid for p in processos(nome)])
    print("limite:", limite_da_plataforma() or "nenhum")
