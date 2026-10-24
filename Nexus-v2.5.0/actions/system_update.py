"""System update — the assistant keeps itself current.

Every release is a ZIP with the whole project inside (any single top folder,
e.g. "Andre-LV/" or GitHub's "owner-repo-1a2b3c/"). Two ways in:

  * Local  — drop the ZIP into ``updates/``; it is noticed on boot, or say
             "check for updates" / "apply the update".
  * GitHub — set ``github_repo`` in config/update.json ("owner/repo"). The
             assistant looks at the repository's latest *release* now and then;
             when its tag (v8.8, 8.8...) is newer than memory/version.json it
             TELLS the user and waits. "Instala a atualização" downloads the
             release (its .zip asset, or the source zip GitHub makes) into
             updates/ and applies it like a local package.
             1.4.1: no release needed — the repository's main branch counts
             too. Its memory/version.json says which version is there; when it
             is newer, the ATUALIZAR button (or "atualiza o Nexus") downloads
             the branch zip. A release, when there is one, still wins on a tie.

Applying never touches the user's own data (keys, memory, notes, routines...),
backs up every file it replaces into backups/update-<old version>-<time>/, and
asks for a restart to finish. "Desfaz a atualização" restores that backup.
Network trouble or a missing release only ever produces a log line.
"""

import json
import re
import shutil
import time
import zipfile
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent      # overridable in tests
_UPDATES_DIR = _BASE / "updates"

# Never overwritten by an update — this is the user's own data.
_PROTECTED = {
    "config/api_keys.json",        # keys + all settings (also the email app password)
    "config/licenca.json",         # 1.5 — a licença ativada neste PC
    "config/quick_notes.json",     # quick notes
    "memory/facts.json",          # long-term memory bank
    "memory/price_alerts.json",    # active price alerts
    "memory/long_term.json",       # session memories
    "memory/conversations.json",   # conversation threads
    "memory/routines.json",        # the user's routines
    "memory/habits.json",          # learned habits
    "memory/email_state.json",     # which email was last read aloud
    "memory/update_state.json",    # which update was last announced
    "config/focus_state.json",     # a focus timer that may be running
    "config/email_account.json",   # email_checker: the remembered address
    "memory/intent_examples.json", # what the user typed — the network learned from it
    "memory/intent_net.npz",       # the network trained on those phrases
    "memory/intent_net_settings.json",
    "memory/activity.log",
    "memory/audit.log",
    "memory/projetos.json",        # 1.5 — a lista de projetos do usuário
    "memory/organizacao_desktop.json",   # 1.4.2 — para desfazer a organização da área de trabalho
}
_PROTECTED_PREFIXES = ("config/certs/", "config/whatsapp_web/", "updates/",
                       "backups/", ".git/")
_TOP_FOLDERS = {"nexus", "nexus-main", "andre-lv", "andre-lv-main", "mark_lv_fixed"}
_GITHUB_API = "https://api.github.com/repos/{repo}/releases/latest"
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _base() -> Path:
    return Path(_BASE)


def _version_file() -> Path:
    return _base() / "memory" / "version.json"


def _vt(v) -> tuple:
    """'6.10' → (6, 10), 'v8.8' → (8, 8) — tuple compare handles dotted versions."""
    try:
        return tuple(int(x) for x in str(v).strip().lstrip("vV").split("."))
    except Exception:
        return (0,)


def is_newer(candidate, current) -> bool:
    return _vt(candidate) > _vt(current)


def current_version() -> dict:
    try:
        data = json.loads(_version_file().read_text(encoding="utf-8"))
        if data.get("version"):
            return data
    except Exception:
        pass
    return {"version": "0.0", "codename": "unknown", "changelog": []}


def _ver_from_name(name: str):
    m = re.search(r"-v(\d+(?:\.\d+)*)", name.lower())
    return m.group(1) if m else None


def _zip_root(zf) -> str:
    """The folder the project sits in inside a package, e.g. "Andre-54.7.1/",
    GitHub's "owner-repo-1a2b3c/", or "" when main.py is at the zip's root.

    1.4.1: the folder that holds main.py wins. The NEXUS Pro packages carry
    the LEIA-ME files next to the Nexus/ folder, and the old "single top
    folder" rule saw two tops there and refused the whole package."""
    names = [i.filename.replace("\\", "/") for i in zf.infolist()
             if not i.filename.endswith("/")]
    if not names or "main.py" in names:
        return ""
    com_main = sorted({n[: -len("main.py")] for n in names
                       if n.endswith("/main.py") and n.count("/") == 1})
    if len(com_main) == 1:
        return com_main[0]
    if any("/" not in n for n in names):
        return ""
    tops = {n.split("/")[0] for n in names}
    return next(iter(tops)) + "/" if len(tops) == 1 else ""


def _read_zip_version(zf) -> dict:
    """The version.json a package carries, from its root or its top folder."""
    root = _zip_root(zf)
    for cand in (root + "memory/version.json", "memory/version.json"):
        if cand in zf.namelist():
            return json.loads(zf.read(cand).decode("utf-8"))
    return {}


def _looks_like_jarvis(zf) -> bool:
    """A release must contain main.py at its root — refuses random ZIPs."""
    root = _zip_root(zf)
    names = set(n.replace("\\", "/") for n in zf.namelist())
    return (root + "main.py") in names or "main.py" in names


def inspect_package(zip_path: str) -> dict:
    """Version and notes of a package, read before anything is applied. {} if unreadable."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            data = _read_zip_version(zf)
        return {"version": str(data.get("version", "?")),
                "notes": (data.get("changelog") or [{}])[0].get("notes", "")}
    except Exception:
        return {}


def scan_updates() -> list:
    """Update packages in updates/, newest first: [{path, version, notes}]."""
    out = []
    d = _base() / "updates"
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.zip")):
        ver, notes = _ver_from_name(f.name), ""
        try:                      # the package carries its own version.json
            with zipfile.ZipFile(f) as zf:
                # Partial packages (only a few changed files, like the ones
                # made by hand) are NOT releases: applying one as "the update"
                # would drop files in the wrong place. Only full projects count.
                if not _looks_like_jarvis(zf):
                    continue
                data = _read_zip_version(zf)
                if data.get("version"):
                    ver = data["version"]
                    notes = (data.get("changelog") or [{}])[0].get("notes", "")
        except Exception:
            pass
        out.append({"path": str(f), "name": f.name, "version": ver or "?",
                    "notes": notes})
    out.sort(key=lambda p: _vt(p["version"]), reverse=True)
    return out


def remote_check() -> dict:
    """Optional: fetch a hosted manifest (config key 'update_url').
    Returns {} when not configured or unreachable."""
    try:
        from memory.config_manager import load_api_keys
        url = str(load_api_keys().get("update_url", "")).strip()
    except Exception:
        url = ""
    if not url:
        return {}
    try:
        import requests
        r = requests.get(url, timeout=8)
        data = r.json()
        return {"version": data.get("version", "?"),
                "notes": data.get("notes", ""),
                "download_url": data.get("download_url", "")}
    except Exception:
        return {}


# ── GitHub releases ──────────────────────────────────────────────────────────

def update_config() -> dict:
    """config/update.json — committed with the project, so everyone who
    downloads it from GitHub gets updates from the same repository."""
    try:
        data = json.loads((_base() / "config" / "update.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def github_repo() -> str:
    repo = str(update_config().get("github_repo") or "").strip().strip("/")
    repo = re.sub(r"^https?://github\.com/", "", repo).removesuffix(".git")
    return repo if _REPO_RE.match(repo) else ""


def github_token() -> str:
    """Read-only token for a PRIVATE repository (configurar_github.py saves it
    in config/api_keys.json, which is never published). '' for public repos."""
    try:
        from memory.config_manager import load_api_keys
        return str(load_api_keys().get("github_token") or "").strip()
    except Exception:
        return ""


def _gh_headers(accept: str = "application/vnd.github+json") -> dict:
    h = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
    tok = github_token()
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def github_latest(timeout: float = 8.0) -> dict:
    """The latest published release: {version, tag, notes, download_url,
    page}. {} when no repo is set, there is no release yet, or the network
    fails. Never raises."""
    repo = github_repo()
    if not repo:
        return {}
    try:
        import requests
        r = requests.get(_GITHUB_API.format(repo=repo), timeout=timeout,
                         headers=_gh_headers())
        if r.status_code != 200:
            hint = (" (private repository? run configurar_github.py to save a token)"
                    if r.status_code == 404 and not github_token() else "")
            print(f"[SystemUpdate] GitHub answered {r.status_code} for {repo}{hint}")
            return {}
        data = r.json()
    except Exception as e:
        print(f"[SystemUpdate] GitHub unreachable: {e}")
        return {}
    if data.get("draft") or data.get("prerelease"):
        return {}
    tag = str(data.get("tag_name") or "").strip()
    version = tag.lstrip("vV")
    if not version or _vt(version) == (0,):
        return {}
    # A .zip attached to the release wins; otherwise GitHub's source zip.
    want = str(update_config().get("asset_contains") or "").lower()
    assets = [a for a in data.get("assets") or []
              if str(a.get("name", "")).lower().endswith(".zip")
              and want in str(a.get("name", "")).lower()]
    # With a token (private repo) the asset must come through the API URL —
    # the browser link only works for whoever is logged in on a browser.
    if assets and github_token():
        url = assets[0].get("url") or ""
    else:
        url = (assets[0].get("browser_download_url") if assets
               else data.get("zipball_url")) or ""
    return {"version": version, "tag": tag,
            "notes": str(data.get("body") or "").strip()[:600],
            "download_url": url, "page": data.get("html_url", "")}


# ── 1.4.1: the repository's branch (no release needed) ───────────────────────

_branch_cache: dict = {}


def github_branch(timeout: float = 8.0) -> str:
    """config/update.json "branch", or the repository's default branch."""
    fixo = str(update_config().get("branch") or "").strip()
    if fixo:
        return fixo
    repo = github_repo()
    if repo in _branch_cache:
        return _branch_cache[repo]
    nome = "main"
    try:
        import requests
        r = requests.get(f"https://api.github.com/repos/{repo}", timeout=timeout,
                         headers=_gh_headers())
        if r.status_code == 200:
            nome = str(r.json().get("default_branch") or "main")
    except Exception:
        pass
    _branch_cache[repo] = nome
    return nome


def _why(status: int) -> str:
    if status == 404:
        return ("o repositório não foi encontrado (é privado? rode configurar_github.py "
                "para salvar um token)" if not github_token() else "o repositório não foi encontrado")
    if status in (401, 403, 429):
        return "o GitHub limitou as consultas agora — tente de novo daqui a alguns minutos"
    return f"o GitHub respondeu {status}"


def github_branch_latest(timeout: float = 8.0) -> tuple[dict, str]:
    """(info, erro) of the version sitting on the repository's branch.
    info = {version, tag, notes, download_url, page, source:'branch'} or {}."""
    repo = github_repo()
    if not repo:
        return {}, "nenhum repositório configurado em config/update.json"
    branch = github_branch(timeout)
    try:
        import requests
        r = requests.get(f"https://api.github.com/repos/{repo}/contents/memory/version.json",
                         params={"ref": branch}, timeout=timeout,
                         headers=_gh_headers("application/vnd.github.raw+json"))
    except Exception as e:
        return {}, f"sem conexão com o GitHub ({type(e).__name__})"
    if r.status_code != 200:
        return {}, _why(r.status_code)
    try:
        data = json.loads(r.content.decode("utf-8"))
    except Exception:
        return {}, "o memory/version.json do repositório não é um JSON válido"
    version = str(data.get("version") or "").strip()
    if not version or _vt(version) == (0,):
        return {}, "o repositório não diz qual é a versão (memory/version.json)"
    notes = str(((data.get("changelog") or [{}])[0] or {}).get("notes", "")).strip()
    return {"version": version, "tag": branch, "notes": notes[:1500],
            "download_url": f"https://api.github.com/repos/{repo}/zipball/{branch}",
            "page": f"https://github.com/{repo}/tree/{branch}", "source": "branch"}, ""


def github_newest(timeout: float = 8.0) -> tuple[dict, str]:
    """(info, erro): the newest of the latest release and the branch.
    A release wins a tie (its zip may carry more than the source)."""
    if not github_repo():
        return {}, "nenhum repositório configurado em config/update.json"
    rel = github_latest(timeout)
    if rel:
        rel = dict(rel, source="release")
    ram, erro = github_branch_latest(timeout)
    if rel and ram:
        return (ram if is_newer(ram["version"], rel["version"]) else rel), ""
    if rel or ram:
        return (rel or ram), ""
    return {}, erro or "não achei nenhuma versão publicada"


def check_online(timeout: float = 8.0) -> dict:
    """For the ATUALIZAR window: {current, latest, newer, error, repo}."""
    cur = current_version().get("version", "0.0")
    info, erro = github_newest(timeout)
    return {"current": cur, "latest": info, "repo": github_repo(),
            "newer": bool(info) and is_newer(info["version"], cur), "error": erro}


def _requirements_changed(backup_dir: Path) -> bool:
    """True when the update's requirements.txt asks for a library (or version)
    the old one did not — removing one needs nothing installed."""
    novo, velho = _base() / "requirements.txt", backup_dir / "requirements.txt"
    if not (novo.exists() and velho.exists()):
        return False

    def _libs(p: Path) -> set:
        out = set()
        for linha in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            linha = linha.split("#", 1)[0].strip()
            if linha:
                out.add(re.sub(r"\s+", "", linha.lower()))
        return out
    try:
        return bool(_libs(novo) - _libs(velho))
    except Exception:
        return False


def last_backup() -> Path | None:
    root = _base() / "backups"
    dirs = sorted((d for d in root.glob("update-*") if d.is_dir() and not d.name.endswith("-restored")),
                  key=lambda d: d.stat().st_mtime) if root.is_dir() else []
    return dirs[-1] if dirs else None


def download_release(info: dict, timeout: float = 60.0, progress=None) -> str:
    """Download a release into updates/. Returns the zip path; raises with a
    readable message on failure (the partial file is removed).
    `progress(bytes_so_far)` is called as the download goes (1.4.1)."""
    url = info.get("download_url") or ""
    if not url.startswith("https://"):
        raise ValueError("release has no download link")
    dest_dir = _base() / "updates"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"github-v{info['version']}.zip"
    part = dest.with_suffix(".part")
    import requests
    try:
        # requests drops the Authorization header by itself when GitHub
        # redirects the download to its storage host.
        accept = ("application/octet-stream" if "/releases/assets/" in url
                  else "application/vnd.github+json")
        with requests.get(url, stream=True, timeout=timeout,
                          headers=_gh_headers(accept)) as r:
            r.raise_for_status()
            baixado = 0
            with open(part, "wb") as f:
                for chunk in r.iter_content(64 * 1024):
                    if chunk:
                        f.write(chunk)
                        baixado += len(chunk)
                        if progress:
                            try:
                                progress(baixado)
                            except Exception:
                                pass
        with zipfile.ZipFile(part) as zf:
            if zf.testzip() is not None:
                raise ValueError("the downloaded file is damaged")
            if not _looks_like_jarvis(zf):
                raise ValueError("the release zip does not contain the Nexus project (no main.py)")
        part.replace(dest)
        return str(dest)
    except zipfile.BadZipFile:
        raise ValueError("the download is not a valid zip")
    finally:
        if part.exists():
            try:
                part.unlink()
            except Exception:
                pass


def _stamp_version(version: str, notes: str) -> None:
    """If the release forgot to bump memory/version.json, record the release
    version anyway — otherwise the same update would be offered forever."""
    cur = current_version()
    if not is_newer(version, cur.get("version", "0.0")):
        return
    cur["version"] = version
    log = cur.get("changelog") or []
    log.insert(0, {"version": version, "date": time.strftime("%Y-%m-%d"),
                   "notes": notes or "Atualização baixada do GitHub."})
    cur["changelog"] = log
    try:
        _version_file().write_text(json.dumps(cur, indent=2, ensure_ascii=False),
                                   encoding="utf-8")
    except Exception as e:
        print(f"[SystemUpdate] could not stamp version: {e}")


def apply_online(player=None, info: dict | None = None, progress=None) -> str:
    """Download the newest version from GitHub (release or branch) and apply it."""
    if info is None:
        info, erro = github_newest()
        if not info:
            return f"Could not find a version on GitHub: {erro}."
    cur = current_version().get("version", "0.0")
    if not is_newer(info["version"], cur):
        return f"Already up to date: running v{cur}, the newest on GitHub is v{info['version']}."
    _log(f"downloading v{info['version']} from GitHub", player)
    try:
        path = download_release(info, progress=progress)
    except Exception as e:
        msg = f"The download failed, nothing was changed: {e}"
        _log(msg, player)
        return msg
    result = apply_package(path, player)
    if result.startswith("Update applied"):
        _stamp_version(info["version"], info.get("notes", ""))
        result = re.sub(r"switching to v[\d.]*\d", f"switching to v{info['version']}", result)
        bk = last_backup()
        if bk is not None and _requirements_changed(bk):
            result += (" NEW_LIBRARIES: this version needs new Python libraries — "
                       "run 'python setup.py' (and gerar_exe.bat if you use Nexus.exe).")
    return result


# ── announcement bookkeeping (so a declined update is not repeated hourly) ──

def _state_file() -> Path:
    return _base() / "memory" / "update_state.json"


def should_announce(version: str, every_days: float = 3.0) -> bool:
    try:
        st = json.loads(_state_file().read_text(encoding="utf-8"))
    except Exception:
        st = {}
    if st.get("version") != version:
        return True
    return time.time() - float(st.get("at", 0)) > every_days * 86400


def mark_announced(version: str) -> None:
    try:
        _state_file().parent.mkdir(parents=True, exist_ok=True)
        _state_file().write_text(json.dumps({"version": version, "at": time.time()}),
                                 encoding="utf-8")
    except Exception:
        pass


# ── applying, with a backup ──────────────────────────────────────────────────

def _is_protected(rel: str) -> bool:
    return rel in _PROTECTED or rel.startswith(_PROTECTED_PREFIXES)


def apply_package(zip_path: str, player=None) -> str:
    """Extract an update package over the app folder, protecting user data.
    Every file it replaces is copied to backups/ first (see rollback)."""
    applied, skipped = 0, 0
    old_ver = current_version().get("version", "0.0")
    backup = _base() / "backups" / f"update-{old_ver}-{time.strftime('%Y%m%d-%H%M%S')}"
    created: list[str] = []
    base = _base().resolve()
    try:
        with zipfile.ZipFile(zip_path) as zf:
            root = _zip_root(zf)
            for info in zf.infolist():
                nm = info.filename.replace("\\", "/")
                if nm.endswith("/"):
                    continue
                if root:
                    if not nm.startswith(root):
                        continue                   # LEIA-ME etc. next to the project folder
                    nm = nm[len(root):]            # strip the package folder
                parts = [p for p in nm.split("/") if p not in ("", ".")]
                if "__pycache__" in parts:
                    continue
                if parts and parts[0].lower() in _TOP_FOLDERS:
                    parts = parts[1:]              # legacy package folder names
                if not parts:
                    continue
                # A zip from the internet may try "../../x" or "C:/x" to write
                # outside the app folder. Such entries are refused outright.
                if ".." in parts or ":" in parts[0] or nm.startswith("/"):
                    skipped += 1
                    continue
                rel = "/".join(parts)
                if _is_protected(rel):
                    skipped += 1
                    continue
                dest = _base() / Path(*parts)
                if base not in dest.resolve().parents:
                    skipped += 1
                    continue
                if dest.exists():
                    bk = backup / Path(*parts)
                    bk.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(dest, bk)
                else:
                    created.append(rel)
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                applied += 1
    except Exception as e:
        msg = f"Sir, the update failed: {e}"
        if applied:
            msg += " Some files were already replaced — say 'undo the update' to restore them."
        _write_manifest(backup, old_ver, created)
        _log(msg, player)
        return msg
    _write_manifest(backup, old_ver, created)
    ver = current_version().get("version", "?")
    msg = (f"Update applied, sir — {applied} files written"
           + (f", {skipped} of your data files left untouched" if skipped else "")
           + f". Restart me to finish switching to v{ver}.")
    _log(msg, player)
    return msg


def _write_manifest(backup: Path, old_ver: str, created: list) -> None:
    try:
        backup.mkdir(parents=True, exist_ok=True)
        (backup / "_manifest.json").write_text(
            json.dumps({"from_version": old_ver, "created": created,
                        "at": time.strftime("%Y-%m-%d %H:%M:%S")}, indent=1),
            encoding="utf-8")
    except Exception as e:
        print(f"[SystemUpdate] could not write backup manifest: {e}")


def rollback(player=None) -> str:
    """Put back the files the most recent update replaced, and remove the
    files it added. The backup is then moved aside so it is not reused."""
    bk = last_backup()      # 1.4.1: a backup already restored is not used again
    if bk is None:
        return "There is no update backup to restore."
    try:
        manifest = json.loads((bk / "_manifest.json").read_text(encoding="utf-8"))
    except Exception:
        manifest = {}
    restored = removed = 0
    for f in bk.rglob("*"):
        if f.is_file() and f.name != "_manifest.json":
            rel = f.relative_to(bk)
            dest = _base() / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
            restored += 1
    for rel in manifest.get("created", []):
        p = _base() / Path(*rel.split("/"))
        try:
            if p.is_file():
                p.unlink()
                removed += 1
        except Exception:
            pass
    try:
        bk.rename(bk.with_name(bk.name + "-restored"))
    except Exception:
        pass
    msg = (f"Restored v{manifest.get('from_version', '?')}: {restored} files put back"
           + (f", {removed} added files removed" if removed else "")
           + ". Restart me to finish.")
    _log(msg, player)
    return msg


def startup_check(player=None) -> str:
    """One line for the boot log — '' when everything is current."""
    cur = current_version().get("version", "0.0")
    pkgs = scan_updates()
    if pkgs and pkgs[0]["version"] != "?" and is_newer(pkgs[0]["version"], cur):
        return (f"Update package v{pkgs[0]['version']} detected in updates/ "
                f"(running v{cur}) — say 'apply the update' when ready.")
    return ""


def system_update_action(parameters: dict, player=None, session_memory=None) -> str:
    action = str(parameters.get("action") or "check").strip().lower()
    cur = current_version()

    if action == "check":
        cur_v = cur.get("version", "0.0")
        lines = [f"Running NEXUS v{cur_v}"
                 + (f" — {cur['codename']}" if cur.get("codename") else "") + "."]
        gh, erro = github_newest()
        if gh:
            if is_newer(gh["version"], cur_v):
                lines.append(f"GitHub: v{gh['version']} is available"
                             + (f" — {gh['notes'][:200]}" if gh.get("notes") else "")
                             + ". Ask if they want it installed (action='apply_online').")
            else:
                lines.append(f"GitHub: up to date (newest there is v{gh['version']}).")
        elif github_repo():
            lines.append(f"GitHub: could not check — {erro}.")
        pkgs = scan_updates()
        newer = [p for p in pkgs if p["version"] == "?" or is_newer(p["version"], cur_v)]
        if newer:
            lines.append(f"Local package v{newer[0]['version']} in updates/ is ready (action='apply').")
        rem = remote_check()
        if rem and is_newer(rem["version"], cur_v):
            lines.append(f"Remote manifest: v{rem['version']} is available online.")
        _log(f"check: running v{cur_v}", player)
        return " ".join(lines)

    if action == "apply_online":
        return apply_online(player)

    if action == "apply":
        pkgs = scan_updates()
        if not pkgs:
            if github_repo():
                return apply_online(player)
            msg = ("Sir, there is nothing to apply — drop an update ZIP "
                   "into the 'updates' folder next to the app first.")
            _log(msg, player)
            return msg
        idx = parameters.get("package_index")
        try:
            idx = int(idx) - 1
            pkg = pkgs[idx] if 0 <= idx < len(pkgs) else pkgs[0]
        except (TypeError, ValueError):
            pkg = pkgs[0]
        return apply_package(pkg["path"], player)

    if action == "rollback":
        return rollback(player)

    if action == "restart":
        if player is not None and hasattr(player, "restart_app"):
            player.restart_app()
            return "Restarting NEXUS now — say one short goodbye sentence."
        return "I cannot restart myself from here; close and open NEXUS again."

    if action == "changelog":
        entries = cur.get("changelog", [])
        if not entries:
            msg = "No changelog on file, sir."
        else:
            lines = [f"v{e.get('version', '?')} — {e.get('notes', '')}"
                     for e in entries[:6]]
            msg = "Recent updates, sir: " + " | ".join(lines)
        _log("changelog shown", player)
        return msg

    msg = ("Sir, I can check for updates, install the newest one from GitHub, "
           "apply a local package, undo the last update, or read the changelog.")
    _log(msg, player)
    return msg


def _log(message: str, player=None) -> None:
    print(f"[SystemUpdate] {message}")
    if player:
        try:
            player.write_log(f"NEXUS: {message}")
        except Exception:
            pass


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "system_update",
    "description": (
        "Keeps the assistant itself up to date. 'check' looks at the project's "
        "GitHub repository (releases and the main branch) and the local 'updates' "
        "folder ('tem atualização?'). "
        "'apply_online' downloads and installs the newest version from GitHub — only "
        "after the user said yes ('instala a atualização'). 'apply' installs a "
        "ZIP from the updates folder. 'rollback' undoes the last update "
        "('desfaz a atualização'). 'changelog' reads what changed. 'restart' "
        "restarts NEXUS to finish an install — only when the user says so. The user's "
        "keys, memory and notes are never touched; a restart finishes the install."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["check", "apply_online", "apply", "rollback", "changelog", "restart"],
                "description": "What to do"
            },
            "package_index": {
                "type": "NUMBER",
                "description": "apply: package number in updates/ (optional — newest "
                               "by default)"
            },
        },
        "required": ["action"]
    },
    "handler": system_update_action,
}
