"""Voice timers and alarms — "set a timer for 10 minutes".

Runs in a background thread so the conversation never blocks; when the time
is up, a three-tone chime plays through the default sound output (sounddevice
is already a project dependency) and the assistant's log records it. Works
even when the model is mid-answer. Timers can be listed or cancelled by
voice, and more than one can run at the same time.
"""

import threading
import time
from core.protecao import engolida as _engolida

try:
    import numpy as np
    _SD = None
    try:
        import sounddevice as sd
        _SD = sd
    except Exception:
        _SD = None
except Exception:                                   # pragma: no cover
    np = None

# name → {"ends_at": epoch, "cancel": threading.Event, "label": str}
_ACTIVE: dict[str, dict] = {}
_LOCK = threading.Lock()


def _beep() -> None:
    """Three rising tones, ~2 seconds, on the default output."""
    if np is None or _SD is None:
        print("\a")                                  # console bell fallback
        return
    try:
        rate = 44100
        tones = (880.0, 1100.0, 1320.0)
        chunks = []
        for f in tones:
            t = np.arange(int(rate * 0.45)) / rate
            env = np.minimum(1.0, np.minimum(t / 0.02, (0.45 - t) / 0.05))
            chunks.append(np.sin(2 * np.pi * f * t) * env * 0.4)
        wave = np.concatenate(chunks).astype(np.float32)
        for _ in range(2):                          # ring twice
            _SD.play(wave, rate, blocking=False)
            time.sleep(len(wave) / rate + 0.15)
    except Exception:
        print("\a")


def _run_timer(name: str, seconds: float, label: str, player=None) -> None:
    with _LOCK:
        old = _ACTIVE.pop(name, None)
        if old:
            old["cancel"].set()
            try:
                old["thread"].cancel()             # stop the pending thread
            except Exception:
                _engolida("actions/timer_action.py:58")
        entry = {
            "ends_at":   time.time() + seconds,
            "cancel":    threading.Event(),
            "label":     label,
            "thread":    None,
            "paused":    False,
            "remaining": 0.0,
        }
        _ACTIVE[name] = entry
    timer = threading.Timer(seconds, _fire, args=(name, label, player))
    entry["thread"] = timer
    timer.daemon = True
    timer.start()


def _fire(name: str, label: str, player=None) -> None:
    with _LOCK:
        entry = _ACTIVE.pop(name, None)
    if entry is None or entry["cancel"].is_set():
        return                                     # cancelled — stay silent
    what = f"timer {name}" + (f" — {label}" if label else "")
    _log(f"⏰ {what} finished", player)
    threading.Thread(target=_beep, daemon=True).start()


def timer_action(parameters: dict, player=None, session_memory=None) -> str:
    action  = str(parameters.get("action") or "start").strip().lower()
    minutes = parameters.get("minutes")
    seconds = parameters.get("seconds") or 0
    name    = str(parameters.get("name") or "").strip().lower()
    label   = str(parameters.get("label") or "").strip()

    if action == "start":
        try:
            mins = float(str(minutes).replace(",", ".")) if minutes is not None else 0.0
            secs = float(str(seconds).replace(",", ".")) if seconds is not None else 0.0
        except (TypeError, ValueError):
            msg = "Sir, how long should the timer run? Give me minutes or seconds."
            _log(msg, player)
            return msg
        total = mins * 60 + secs
        if total <= 0 or total > 24 * 3600:
            msg = "Sir, give me a duration between one second and 24 hours."
            _log(msg, player)
            return msg
        if not name:
            name = f"timer{len(_ACTIVE) + 1}"
        _run_timer(name, total, label, player)
        human = _human(total)
        what = label or name
        msg = f"Timer set for {human}, sir. I'll chime when it's done."
        _log(f"started {name} ({human}) — {label}", player)
        return msg

    if action == "cancel":
        target = name
        with _LOCK:
            if target and target in _ACTIVE:
                entry = _ACTIVE.pop(target)
                entry["cancel"].set()
                try:
                    entry["thread"].cancel()
                except Exception:
                    _engolida("actions/timer_action.py:122")
                msg = f"Timer {target} cancelled, sir."
            elif target:
                msg = f"Sir, there is no timer named {target}."
            elif _ACTIVE:
                for v in _ACTIVE.values():
                    v["cancel"].set()
                    try:
                        v["thread"].cancel()
                    except Exception:
                        _engolida("actions/timer_action.py:132")
                _ACTIVE.clear()
                msg = "All timers cancelled, sir."
            else:
                msg = "Sir, there are no timers running."
        _log(msg, player)
        return msg

    if action in ("extend", "pause", "resume"):
        extra = float(minutes or 0) * 60 + float(seconds or 0)
        with _LOCK:
            entry = _ACTIVE.get(name) if name else None
            if name and entry is None:
                msg = f"Sir, there is no timer named {name}."
            elif not _ACTIVE:
                msg = "Sir, there are no timers running."
            else:
                if not name:                       # applies to the soonest one
                    name = min(_ACTIVE, key=lambda k: _ACTIVE[k]["ends_at"])
                    entry = _ACTIVE[name]

                if action == "extend":
                    if entry.get("paused"):
                        entry["remaining"] = max(0.0, entry["remaining"]) + extra
                        msg = (f"Timer {name} extended by {_human(extra)} — "
                               f"{_human(entry['remaining'])} left, still paused, sir.")
                    elif extra > 0:
                        remaining = max(0.0, entry["ends_at"] - time.time()) + extra
                        try:
                            entry["thread"].cancel()
                        except Exception:
                            _engolida("actions/timer_action.py:163")
                        t = threading.Timer(remaining, _fire,
                                            args=(name, entry["label"], player))
                        entry["thread"]  = t
                        entry["ends_at"] = time.time() + remaining
                        t.daemon = True
                        t.start()
                        msg = (f"Timer {name} extended — "
                               f"{_human(remaining)} left now, sir.")
                    else:
                        msg = "Sir, extend by how much? Tell me the minutes."

                elif action == "pause":
                    if entry.get("paused"):
                        msg = f"Timer {name} is already paused, sir."
                    else:
                        entry["remaining"] = max(0.0, entry["ends_at"] - time.time())
                        try:
                            entry["thread"].cancel()
                        except Exception:
                            _engolida("actions/timer_action.py:183")
                        entry["paused"] = True
                        msg = (f"Timer {name} paused — "
                               f"{_human(entry['remaining'])} left, sir.")

                else:                               # resume
                    if not entry.get("paused"):
                        msg = f"Timer {name} isn't paused, sir."
                    else:
                        remaining = max(0.0, entry["remaining"])
                        t = threading.Timer(remaining, _fire,
                                            args=(name, entry["label"], player))
                        entry["thread"]  = t
                        entry["ends_at"] = time.time() + remaining
                        entry["paused"]  = False
                        t.daemon = True
                        t.start()
                        msg = f"Timer {name} resumed — {_human(remaining)} left, sir."
        _log(msg, player)
        return msg

    if action == "status":
        with _LOCK:
            if not _ACTIVE:
                msg = "Sir, no timers are running."
            else:
                parts = []
                for n, v in sorted(_ACTIVE.items(), key=lambda kv: kv[1]["ends_at"]):
                    if v.get("paused"):
                        left = max(0, int(v.get("remaining", 0.0)))
                        parts.append(f"{n} with {_human(left)} left (paused)")
                    else:
                        left = max(0, int(v["ends_at"] - time.time()))
                        parts.append(f"{n} with {_human(left)} left")
                msg = "Sir, running timers: " + "; ".join(parts) + "."
        _log(msg, player)
        return msg

    msg = ("Sir, I can start, cancel, check, pause, resume and extend timers. Just tell me the duration.")
    _log(msg, player)
    return msg


def _human(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} hour{'s' if h != 1 else ''} and {m} minute{'s' if m != 1 else ''}"
    if m and s:
        return f"{m} minute{'s' if m != 1 else ''} and {s} seconds"
    if m:
        return f"{m} minute{'s' if m != 1 else ''}"
    return f"{s} seconds"


def _log(message: str, player=None) -> None:
    print(f"[Timer] {message}")
    if player:
        try:
            player.write_log(f"NEXUS: {message}")
        except Exception:
            _engolida("actions/timer_action.py:245")


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "timer_action",
    "description": (
        "Voice timers and alarms. Start a countdown (minutes and/or "
        "seconds, up to 24h), cancel one by name or all at once, and ask "
        "how much time is left. Several timers can run at the same time; "
        "each chimes when finished. Example: action=start, minutes=10, "
        "name=laundry, label='take the clothes out'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["start", "cancel", "status", "extend", "pause", "resume"],
                "description": "Start, cancel, check, pause, resume or "
                               "add time to a running timer"
            },
            "minutes": {
                "type": "NUMBER",
                "description": "Duration in minutes (for start, or the "
                               "extra time for extend)"
            },
            "seconds": {
                "type": "NUMBER",
                "description": "Extra duration in seconds (for start)"
            },
            "name": {
                "type": "STRING",
                "description": "A short name to refer to this timer, e.g. 'pizza'"
            },
            "label": {
                "type": "STRING",
                "description": "What the timer is for, e.g. 'tea is ready'"
            },
        },
        "required": ["action"]
    },
    "handler": timer_action,
}
