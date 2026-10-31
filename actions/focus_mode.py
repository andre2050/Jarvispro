"""Focus mode — Pomodoro by voice, and the assistant actually keeps quiet.

    "me dá 25 minutos de foco"     -> start (minutes; 25 when not said)
    "quanto falta do foco?"         -> status
    "cancela o foco"                -> stop
    "pode marcar a pausa"           -> break (5 minutes unless said)

While a focus block runs, core.focus_guard.busy_reason() reports it, and every
background voice that asks that question stays silent: proactive check-ins,
news alerts, the email reader, update notices, water reminders and hardware
alerts. Only the user can start a conversation. A battery alert still gets
through below 10 % — losing unsaved work is worse than an interruption.

When the block ends, main.py (_run_focus_watch) asks finished() and the
assistant says it is over and suggests a 5-minute break; when the break ends it
offers another block of the same length. The state lives in
config/focus_state.json, so a restart in the middle keeps the timer.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import date
from pathlib import Path
from core.protecao import engolida as _engolida

_STATE = Path(__file__).resolve().parent.parent / "config" / "focus_state.json"
_LOCK = threading.Lock()
DEFAULT_FOCUS = 25
DEFAULT_BREAK = 5


def _read() -> dict:
    try:
        d = json.loads(_STATE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _write(data: dict) -> None:
    try:
        _STATE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(_STATE)
    except Exception as e:
        print(f"[Focus] could not save state: {e}")


def _minutes(value, default: int, top: int) -> int:
    try:
        return max(1, min(top, int(float(value))))
    except (TypeError, ValueError):
        return default


def _today_count(d: dict) -> int:
    return int(d.get("done_today", 0)) if d.get("day") == date.today().isoformat() else 0


# ── distractions (3.7): apps the user wants closed during focus ─────────────
PROTEGIDOS = {"explorer.exe", "system", "svchost.exe", "csrss.exe", "winlogon.exe", "lsass.exe", "services.exe",
              "dwm.exe", "python.exe", "pythonw.exe", "nexus.exe", "systemd", "init", "bash", "sh", "python3", "python"}


def _nome_app(n: str) -> str:
    n = str(n or "").strip().lower()
    return n if n.endswith(".exe") or "." in n else n


def get_distractions() -> list[str]:
    try:
        from memory.config_manager import get_plugin_config
        v = get_plugin_config("foco").get("apps", [])
        return [str(x) for x in v] if isinstance(v, list) else []
    except Exception:
        return []


def set_distractions(texto: str) -> list[str]:
    from memory.config_manager import save_plugin_config
    nomes = []
    for x in str(texto or "").replace(";", ",").split(","):
        x = _nome_app(x)
        if x and x not in PROTEGIDOS and x not in nomes and len(x) <= 60:
            nomes.append(x)
    save_plugin_config("foco", {"apps": nomes[:20]})
    return nomes[:20]


def _processos_abertos(apps: list[str], listar=None) -> list:
    """Processos cujo nome bate com a lista (com ou sem .exe), sem tocar nos protegidos."""
    try:
        procs = list(listar()) if listar else list(__import__("psutil").process_iter(["name"]))
    except Exception:
        return []
    quer = {a.lower().removesuffix(".exe") for a in apps}
    achados = []
    for p in procs:
        nome = (p.info.get("name") or "").lower()
        if nome in PROTEGIDOS or nome.removesuffix(".exe") not in quer:
            continue
        achados.append(p)
    return achados


def _fechar(apps: list[str], listar=None) -> str:
    n = 0
    for p in _processos_abertos(apps, listar):
        try:
            p.terminate()                          # pede para fechar; nunca kill forçado
            n += 1
        except Exception:
            _engolida("actions/focus_mode.py:115")
    return f"[done] Pedi para fechar {n} programa(s) de distração."


# ── queried by the rest of the app ───────────────────────────────────────────

def remaining() -> int:
    """Seconds left in the running FOCUS block (0 when none or finished)."""
    d = _read()
    if d.get("kind") != "focus" or not d.get("ends_at"):
        return 0
    return max(0, int(d["ends_at"] - time.time()))


def active_reason() -> str | None:
    """For core.focus_guard: why alerts must wait, or None."""
    left = remaining()
    if left <= 0:
        return None
    return f"modo foco ({(left + 59) // 60} min restantes)"


def finished() -> dict | None:
    """A block or break that just reached its end, returned ONCE.

    {"kind": "focus"|"break", "minutes": n, "done_today": k, "focus_minutes": m}
    """
    with _LOCK:
        d = _read()
        kind, ends = d.get("kind"), d.get("ends_at")
        if kind not in ("focus", "break") or not ends or time.time() < ends:
            return None
        out = {"kind": kind, "minutes": d.get("minutes", 0),
               "focus_minutes": d.get("focus_minutes", d.get("minutes", DEFAULT_FOCUS))}
        if kind == "focus":
            today = date.today().isoformat()
            count = _today_count(d) + 1
            out["done_today"] = count
            _write({"kind": "idle", "day": today, "done_today": count,
                    "focus_minutes": out["focus_minutes"]})
        else:
            out["done_today"] = _today_count(d)
            _write({"kind": "idle", "day": d.get("day"), "done_today": out["done_today"],
                    "focus_minutes": out["focus_minutes"]})
        return out


# ── the tool ─────────────────────────────────────────────────────────────────

def focus_mode(parameters: dict, player=None) -> str:
    action = str(parameters.get("action") or "status").strip().lower()
    with _LOCK:
        d = _read()
        now = time.time()

        if action == "start":
            minutes = _minutes(parameters.get("minutes"), DEFAULT_FOCUS, 180)
            _write({"kind": "focus", "started_at": now, "ends_at": now + minutes * 60,
                    "minutes": minutes, "focus_minutes": minutes,
                    "day": d.get("day") or date.today().isoformat(),
                    "done_today": _today_count(d)})
            _log(f"focus started: {minutes} min", player)
            extra = ""
            if str(parameters.get("close_distractions", "")).lower() in ("1", "true", "yes", "sim"):
                apps = get_distractions()
                abertos = _processos_abertos(apps)
                if not apps:
                    extra = " No distraction apps are set yet: ask which ones to close (action=distractions)."
                elif abertos:
                    from core import confirm
                    nomes = sorted({(p.info.get("name") or "?") for p in abertos})
                    extra = " " + confirm.request("foco_fechar", "Fechar programas de distração",
                                                  ", ".join(nomes), lambda: _fechar(apps))
            return (f"Focus started for {minutes} minutes. Confirm in one short sentence. "
                    "From now on you stay silent unless the user speaks to you — no "
                    "check-ins, alerts, phone push notifications or email reading until it ends." + extra)

        if action == "distractions":
            nomes = set_distractions(parameters.get("apps"))
            return ("[done] Distrações do modo foco: " + ", ".join(nomes) + ". Diga 'foco de 25 minutos e fecha as distrações' "
                    "e eu peço o seu CONFIRMAR.") if nomes else "[failed] Diga os nomes dos programas (ex.: discord, steam)."

        if action == "break":
            minutes = _minutes(parameters.get("minutes"), DEFAULT_BREAK, 60)
            _write({"kind": "break", "started_at": now, "ends_at": now + minutes * 60,
                    "minutes": minutes,
                    "focus_minutes": d.get("focus_minutes", DEFAULT_FOCUS),
                    "day": d.get("day") or date.today().isoformat(),
                    "done_today": _today_count(d)})
            _log(f"break started: {minutes} min", player)
            return f"Break timer set for {minutes} minutes. Confirm in a few words."

        if action == "stop":
            was = d.get("kind")
            _write({"kind": "idle", "day": d.get("day"), "done_today": _today_count(d),
                    "focus_minutes": d.get("focus_minutes", DEFAULT_FOCUS)})
            _log("focus/break cancelled", player)
            if was in ("focus", "break") and d.get("ends_at", 0) > now:
                return ("Focus cancelled; notifications are back on." if was == "focus"
                        else "Break cancelled.")
            return "There was no focus session running."

    # status
    kind, ends = d.get("kind"), d.get("ends_at", 0)
    count = _today_count(d)
    if kind in ("focus", "break") and ends > time.time():
        left = int(ends - time.time())
        what = "focus" if kind == "focus" else "break"
        return (f"{left // 60} min {left % 60} s left in the {what}. "
                f"Focus blocks completed today: {count}.")
    return f"No focus session running. Focus blocks completed today: {count}."


def _log(message: str, player=None) -> None:
    print(f"[Focus] {message}")
    if player:
        try:
            player.write_log(f"SYS: {message}")
        except Exception:
            _engolida("actions/focus_mode.py:234")


TOOL = {
    "name": "focus_mode",
    "description": (
        "Pomodoro focus timer that also SILENCES you: while it runs there are no "
        "check-ins, alerts or email reading; at the end you announce it and "
        "suggest a break. Actions: start ('me dá 25 minutos de foco', 'modo foco "
        "por 50 minutos' — minutes, 25 when not said), status ('quanto falta?'), "
        "stop ('cancela o foco'), break (the user accepted the pause — minutes, 5 "
        "when not said). 3.7: start with close_distractions=true also asks (CONFIRM on screen) to close the "
        "apps listed with action=distractions apps='discord, steam'; phone push notifications are silenced too."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["start", "status", "stop", "break", "distractions"]},
            "close_distractions": {"type": "BOOLEAN", "description": "start: also close the distraction apps (needs CONFIRM)"},
            "apps": {"type": "STRING", "description": "distractions: comma list of program names"},
            "minutes": {"type": "INTEGER",
                        "description": "start: focus minutes (1-180, default 25); "
                                       "break: pause minutes (default 5)"},
        },
        "required": ["action"],
    },
    "handler": focus_mode,
}
