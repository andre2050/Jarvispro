"""
Habits — the assistant learns how you actually use it.

Every successful call to a *safe* tool is logged locally (tool, a trimmed copy of
its arguments, hour, weekday). From that log two things are derived, with plain
counting — no model call, no network, no cost:

  * time habits      "you open Spotify most weekday mornings around 9"
  * routine habits   "after morning_briefing you usually run weather_report
                      within a few minutes" -> candidate for a one-phrase routine

core/habits.py only observes and suggests. Turning a habit into an automation is
done by actions/smart_routines.py, always on the user's say-so.

Privacy: only the tools in SAFE_TOOLS are recorded, argument strings are cut to
120 characters, keys that look like secrets/messages are dropped, and everything
lives in memory/habits.json on this machine (listed in .gitignore).
"""
from __future__ import annotations

import json
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

_FILE = Path(__file__).resolve().parent.parent / "memory" / "habits.json"
_LOCK = threading.Lock()

MAX_EVENTS = 1500          # oldest events fall off — habits should track the present
SEQ_WINDOW_S = 300         # two calls this close together count as "one flow"
MIN_REPEATS = 3            # a pattern must be seen this many times to be suggested

# Tools that are harmless to repeat unattended. Anything that sends, deletes,
# pays or controls the whole machine is deliberately absent.
SAFE_TOOLS = frozenset({
    "open_app", "weather_report", "morning_briefing", "music_control",
    "quick_notes", "web_search", "timer_action", "unit_converter",
    "everyday_tools", "video_player", "youtube_video", "price_alert",
    "computer_settings", "system_update", "daily_planner",
    # 3.4 — só leem e mostram (e-mail aberto no navegador, clima, notícias, plano do dia)
    "bom_dia", "oraculo_bemestar",
})

_DROP_KEYS = ("key", "token", "password", "secret", "message", "body", "contact")


def _clean_args(args: dict | None) -> dict:
    out = {}
    for k, v in (args or {}).items():
        if any(bad in str(k).lower() for bad in _DROP_KEYS):
            continue
        if isinstance(v, (int, float, bool)):
            out[k] = v
        elif isinstance(v, str):
            out[k] = v[:120]
    return out


def _sig(tool: str, args: dict) -> str:
    """Identity of a habit: the tool plus its 'what' — `music_control:play`."""
    for k in ("action", "mode", "app_name", "app"):
        if args.get(k):
            return f"{tool}:{str(args[k]).lower()[:40]}"
    return tool


def _load() -> list:
    try:
        data = json.loads(_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(events: list) -> None:
    try:
        _FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(events[-MAX_EVENTS:], ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(_FILE)          # atomic: a crash never leaves half a file
    except Exception as e:
        print(f"[Habits] couldn't save: {e}")


def record(tool: str, args: dict | None = None, at: float | None = None) -> None:
    """Log one successful tool call. Never raises."""
    try:
        if tool not in SAFE_TOOLS:
            return
        clean = _clean_args(args)
        with _LOCK:
            events = _load()
            events.append({"t": at or time.time(), "tool": tool,
                           "sig": _sig(tool, clean), "args": clean})
            _save(events)
    except Exception as e:
        print(f"[Habits] record failed: {e}")


def _day_kind(ts: float) -> str:
    return "weekend" if datetime.fromtimestamp(ts).weekday() >= 5 else "weekday"


def time_habits(now: float | None = None, hours_window: int = 1,
                min_days: int = MIN_REPEATS) -> list[dict]:
    """Habits that fit the current moment: same kind of day, within
    `hours_window` hours of now, repeated on at least `min_days` distinct days."""
    now = now or time.time()
    cur_h, cur_kind = datetime.fromtimestamp(now).hour, _day_kind(now)
    days: dict[str, set] = defaultdict(set)
    last_args: dict[str, dict] = {}
    for e in _load():
        t = e.get("t", 0)
        if _day_kind(t) != cur_kind:
            continue
        h = datetime.fromtimestamp(t).hour
        if min((h - cur_h) % 24, (cur_h - h) % 24) > hours_window:
            continue
        days[e["sig"]].add(datetime.fromtimestamp(t).date().isoformat())
        last_args[e["sig"]] = {"tool": e["tool"], "args": e.get("args", {})}
    out = [{"sig": s, "days": len(d), **last_args[s]}
           for s, d in days.items() if len(d) >= min_days]
    return sorted(out, key=lambda x: -x["days"])


def sequences(min_repeats: int = MIN_REPEATS, max_len: int = 3) -> list[dict]:
    """Flows you repeat: A then B (then C) within SEQ_WINDOW_S, seen at least
    `min_repeats` times. Returns the most frequent first, with the latest
    arguments used so the flow can be replayed as a routine."""
    events = _load()
    flows: Counter = Counter()
    latest: dict[tuple, list] = {}
    for i, first in enumerate(events):
        chain = [first]
        for nxt in events[i + 1:]:
            if nxt["t"] - chain[-1]["t"] > SEQ_WINDOW_S:
                break
            if nxt["sig"] != chain[-1]["sig"]:
                chain.append(nxt)
            if len(chain) == max_len:
                break
        # count every prefix of length >= 2 so A->B surfaces even inside A->B->C
        for n in range(2, len(chain) + 1):
            key = tuple(e["sig"] for e in chain[:n])
            flows[key] += 1
            latest[key] = [{"tool": e["tool"], "params": e.get("args", {})}
                           for e in chain[:n]]
    out = [{"flow": list(k), "count": c, "steps": latest[k]}
           for k, c in flows.items() if c >= min_repeats]
    # prefer longer flows, then frequent ones
    return sorted(out, key=lambda x: (-len(x["flow"]), -x["count"]))[:5]


def describe(suggestion_list: list[dict]) -> str:
    """Short spoken-style summary of what was learned."""
    parts = []
    for s in suggestion_list[:3]:
        parts.append(f"{s['sig'].replace(':', ' ')} (seen on {s['days']} days at this hour)")
    return "; ".join(parts)


def forget_all() -> None:
    with _LOCK:
        _save([])
