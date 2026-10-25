"""
Smart Routines — one phrase, several actions; and the assistant learns which.

    "cria o modo trabalho com Chrome, VS Code e Spotify"   -> create (apps)
    "cria a rotina 'modo estudo': abre o Notion, timer 25" -> create (steps)
    "modo trabalho"                      -> run: every app opens AT ONCE, then
                                            the other steps run in order
    "coloca o Discord no modo trabalho"  -> edit (add_apps)
    "tira o Spotify do modo trabalho"    -> edit (remove_apps)
    "quais rotinas eu tenho?"            -> list
    "o que você aprendeu dos meus hábitos?"  -> suggest (uses core/habits.py)
    "salva esse padrão como rotina manhã"    -> learn

Typing the routine name in the command box runs it straight away, without a
round trip to the model — see match_routine() and main.py _on_text_command.

Steps can only call tools in core.habits.SAFE_TOOLS — nothing that sends a
message, deletes a file or controls the whole machine can ride inside a routine
— and a routine can never call itself. Routines live in memory/routines.json.

Apps are opened in parallel through open_app.launch_direct (no keyboard, no
waiting). An app it cannot start that way — a Microsoft Store app with no
shortcut, say — falls back to the normal open_app, one at a time, after the
others are already on their way.
"""
from __future__ import annotations

import difflib
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core import habits

_FILE = Path(__file__).resolve().parent.parent / "memory" / "routines.json"
_LOCK = threading.Lock()
MAX_STEPS = 20          # apps + other steps, all together
MAX_ROUTINES = 50

# main.py hands over the live registry once, right after discovery.
_registry = None


def bind(registry) -> None:
    global _registry
    _registry = registry


# ── storage ──────────────────────────────────────────────────────────────────

# Ships ready to use. Written to routines.json only when that file does not
# exist yet — after that it is the user's like any other routine: edit it,
# delete it, and it never comes back on its own.
_DEFAULT_ROUTINES = {
    "modo trabalho": {
        "steps": [{"tool": "open_app", "params": {"app_name": "Chrome"}},
                  {"tool": "open_app", "params": {"app_name": "YouTube"}}],
        "description": "Abre o Google Chrome e o YouTube",
    },
}


def _load() -> dict:
    if not _FILE.exists():
        try:
            _save(json.loads(json.dumps(_DEFAULT_ROUTINES)))
        except Exception as e:
            print(f"[Routines] could not write default routines: {e}")
            return json.loads(json.dumps(_DEFAULT_ROUTINES))
    try:
        data = json.loads(_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(data: dict) -> None:
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_FILE)


def _norm(name: str) -> str:
    return " ".join(str(name or "").lower().split())


def _find(data: dict, name: str) -> str | None:
    """Exact match first, then the closest name — voice transcripts are fuzzy."""
    key = _norm(name)
    if not key:
        return None
    if key in data:
        return key
    close = difflib.get_close_matches(key, list(data), n=1, cutoff=0.6)
    return close[0] if close else None


# Words people put in front of a routine name when they type it.
_LEAD = re.compile(
    r"^(?:(?:nexus|jarvis|ok|ei|hey|por favor|pfv|pf)[,!]?\s+)*"
    r"(?:(?:ativa|ativar|ative|liga|ligar|inicia|iniciar|inicie|come[cç]a|"
    r"roda|rodar|executa|executar|entra|entrar|coloca|bota|abre|abrir|"
    r"start|run|activate|enable)\s+)?"
    r"(?:(?:no|na|em|o|a|meu|minha|the|my)\s+)?"
    r"(?:(?:rotina|routine)\s+)?",
    re.IGNORECASE,
)


def match_routine(text: str) -> str | None:
    """The routine a typed command names, or None.

    Deliberately strict — this runs WITHOUT asking the model, so it only fires
    when the whole command is the routine name (optionally preceded by "ativa",
    "modo", "rotina"...). "o que tem no modo trabalho?" is a question and must
    go to the model, so a near-miss never counts here.
    """
    raw = _norm(text).strip(" .!?")
    if not raw or len(raw) > 60:
        return None
    data = _load()
    if not data:
        return None
    if raw in data:
        return raw
    stripped = _LEAD.sub("", raw).strip(" .!?")
    if stripped in data:
        return stripped
    for key in data:                     # "trabalho" → "modo trabalho"
        if key in (f"modo {stripped}", f"modo de {stripped}"):
            return key
    return None


# ── steps ────────────────────────────────────────────────────────────────────

def _parse_steps(raw) -> tuple[list[dict], str]:
    """Accepts the model's `steps` array. Returns (clean_steps, error)."""
    if raw in (None, []):
        return [], ""
    if not isinstance(raw, list):
        return [], "steps must be a list"
    steps = []
    for i, st in enumerate(raw, 1):
        if not isinstance(st, dict):
            return [], f"step {i} is malformed"
        tool = str(st.get("tool") or "").strip()
        if tool == "routines" or tool not in habits.SAFE_TOOLS:
            return [], f"step {i}: '{tool}' can't be used inside a routine"
        params = st.get("params")
        if params is None and st.get("params_json"):
            try:
                params = json.loads(st["params_json"])
            except Exception:
                return [], f"step {i}: params_json is not valid JSON"
        if not isinstance(params, dict):
            params = {}
        steps.append({"tool": tool, "params": params})
    return steps, ""


def _clean_apps(raw) -> list[str]:
    if isinstance(raw, str):
        raw = [a for a in re.split(r"[,;\n]", raw)]
    if not isinstance(raw, list):
        return []
    out, seen = [], set()
    for a in raw:
        a = str(a or "").strip()
        if a and a.lower() not in seen:
            seen.add(a.lower())
            out.append(a[:200])
    return out


def _app_steps(apps: list[str]) -> list[dict]:
    return [{"tool": "open_app", "params": {"app_name": a}} for a in apps]


def _apps_of(r: dict) -> list[str]:
    return [str(s.get("params", {}).get("app_name", "")) for s in r.get("steps", [])
            if s.get("tool") == "open_app" and s.get("params", {}).get("app_name")]


def _describe(name: str, r: dict) -> str:
    apps = _apps_of(r)
    others = [s["tool"] for s in r.get("steps", []) if s.get("tool") != "open_app"]
    bits = []
    if apps:
        bits.append("opens " + ", ".join(apps))
    if others:
        bits.append("then " + " → ".join(others))
    return f"{name}: {'; '.join(bits) or 'empty'}"


# ── running ──────────────────────────────────────────────────────────────────

def _direct_launcher():
    try:
        from actions.open_app import launch_direct
        return launch_direct
    except Exception:
        return None


def run_routine(key: str, player=None, speak=None) -> str:
    """Run a saved routine by its exact key. Never raises."""
    data = _load()
    r = data.get(key)
    if not r:
        return f"No routine called '{key}'."

    steps = r.get("steps", [])
    apps = _apps_of(r)
    others = [s for s in steps if s.get("tool") != "open_app"]
    ctx = {"player": player, "speak": speak, "response": None, "session_memory": None}
    opened, failed, done = [], [], []

    def _log(msg: str) -> None:
        print(f"[Routines] {msg}")
        if player:
            try:
                player.write_log(f"SYS: {msg}")
            except Exception:
                pass

    _log(f"running '{key}'")

    # 1) every app at the same time, without the keyboard
    slow: list[str] = []
    launch_direct = _direct_launcher()
    if apps and launch_direct:
        with ThreadPoolExecutor(max_workers=min(8, len(apps))) as pool:
            results = list(pool.map(launch_direct, apps))
        for app, ok in zip(apps, results):
            (opened if ok else slow).append(app)
    else:
        slow = list(apps)

    # 2) the ones that need the normal open_app (Start Menu typing), in order
    for app in slow:
        if _registry is None or not _registry.has("open_app"):
            failed.append(f"{app} (open_app unavailable)")
            continue
        try:
            out = str(_registry.run("open_app", {"app_name": app}, ctx))
            if out.startswith("Opened"):
                opened.append(app)
            else:
                failed.append(app)
        except Exception as e:
            failed.append(f"{app} ({e})")

    for app in opened:
        habits.record("open_app", {"app_name": app})

    # 3) the remaining steps, in the order they were saved
    for st in others:
        tool = st["tool"]
        if _registry is None or tool not in habits.SAFE_TOOLS or not _registry.has(tool):
            failed.append(f"{tool} (unavailable)")
            continue
        try:
            out = _registry.run(tool, dict(st.get("params") or {}), ctx)
            if str(out).startswith(("Tool '", "Action '")):
                failed.append(tool)
            else:
                done.append(tool)
        except Exception as e:           # one bad step never stops the rest
            failed.append(f"{tool} ({e})")

    parts = [f"Routine '{key}' finished."]
    if opened:
        parts.append("Opened: " + ", ".join(opened) + ".")
    if done:
        parts.append("Also ran: " + ", ".join(done) + ".")
    if failed:
        parts.append("Could not do: " + ", ".join(failed) + ".")
    msg = " ".join(parts)
    _log(msg)
    return msg


# ── the tool ─────────────────────────────────────────────────────────────────

def routines_action(parameters: dict, player=None, speak=None, session_memory=None) -> str:
    action = str(parameters.get("action") or "").strip().lower()
    name = str(parameters.get("name") or "").strip()

    if action == "list":
        data = _load()
        if not data:
            return ("The user has no routines yet. Offer to create one: ask which "
                    "apps it should open.")
        return "Routines: " + "; ".join(_describe(n, r) for n, r in data.items())

    if action == "create":
        if not name:
            return "Ask the user what to call this routine."
        apps = _clean_apps(parameters.get("apps"))
        extra, err = _parse_steps(parameters.get("steps"))
        if err:
            return f"Could not save the routine: {err}."
        steps = _app_steps(apps) + extra
        if not steps:
            return ("A routine needs at least one app or step. Ask the user which "
                    "apps it should open.")
        if len(steps) > MAX_STEPS:
            return f"A routine can have at most {MAX_STEPS} apps and steps together."
        with _LOCK:
            data = _load()
            if _norm(name) not in data and len(data) >= MAX_ROUTINES:
                return "The routine limit is reached; delete one first."
            data[_norm(name)] = {"steps": steps,
                                 "description": str(parameters.get("description") or "")[:200]}
            _save(data)
        return f"Saved. {_describe(_norm(name), data[_norm(name)])}"

    if action == "edit":
        add = _clean_apps(parameters.get("add_apps"))
        remove = {a.lower() for a in _clean_apps(parameters.get("remove_apps"))}
        extra, err = _parse_steps(parameters.get("steps"))
        if err:
            return f"Could not change the routine: {err}."
        with _LOCK:
            data = _load()
            key = _find(data, name)
            if not key:
                return (f"There is no routine called '{name}'. Existing: "
                        f"{', '.join(data) or 'none'}.")
            steps = data[key].get("steps", [])
            if remove:
                kept = []
                for s in steps:
                    app = str(s.get("params", {}).get("app_name", "")).lower()
                    if s.get("tool") == "open_app" and (
                            app in remove or any(r in app or app in r for r in remove)):
                        continue
                    kept.append(s)
                steps = kept
            have = {a.lower() for a in _apps_of({"steps": steps})}
            new_apps = [a for a in add if a.lower() not in have]
            # apps stay grouped at the front, extra steps go at the end
            n_apps = sum(1 for s in steps if s.get("tool") == "open_app")
            steps = steps[:n_apps] + _app_steps(new_apps) + steps[n_apps:] + extra
            if len(steps) > MAX_STEPS:
                return f"A routine can have at most {MAX_STEPS} apps and steps together."
            data[key]["steps"] = steps
            _save(data)
        return f"Updated. {_describe(key, data[key])}"

    if action == "delete":
        with _LOCK:
            data = _load()
            key = _find(data, name)
            if not key:
                return f"There is no routine called '{name}'."
            data.pop(key)
            _save(data)
        return f"Routine '{key}' deleted."

    if action == "run":
        data = _load()
        key = _find(data, name)
        if not key:
            return (f"There is no routine called '{name}' yet. Ask the user which "
                    "apps it should open, then create it with action='create' and "
                    "the apps list. Existing routines: "
                    f"{', '.join(data) or 'none'}.")
        return run_routine(key, player=player, speak=speak)

    if action == "suggest":
        flows = habits.sequences()
        timed = habits.time_habits()
        if not flows and not timed:
            return ("Not enough repetition seen yet to suggest anything — it takes "
                    "a few days of use.")
        bits = []
        if timed:
            bits.append("At this time of day the user usually: " + habits.describe(timed))
        for i, f in enumerate(flows, 1):
            bits.append(f"Pattern {i}: {' then '.join(f['flow'])} (seen {f['count']} times)")
        bits.append("They can say 'save pattern N as <name>' to turn one into a routine.")
        return ". ".join(bits)

    if action == "learn":
        flows = habits.sequences()
        try:
            idx = int(parameters.get("pattern_index") or 1) - 1
        except (TypeError, ValueError):
            idx = 0
        if not name:
            return "Ask the user what to call the new routine."
        if not flows or not 0 <= idx < len(flows):
            return "That pattern does not exist; ask for suggestions first."
        steps, err = _parse_steps(flows[idx]["steps"])
        if err or not steps:
            return f"That pattern can't become a routine: {err or 'it is empty'}."
        with _LOCK:
            data = _load()
            data[_norm(name)] = {"steps": steps, "description": "learned from habits"}
            _save(data)
        return f"Saved. Routine '{name}' now runs: {' then '.join(s['tool'] for s in steps)}."

    if action == "forget_habits":
        habits.forget_all()
        return "Habit history erased."

    return "routines supports: create, edit, run, list, delete, suggest, learn, forget_habits."


TOOL = {
    "name": "routines",
    "description": (
        "Named routines: ONE phrase opens several apps at once and can chain other "
        "safe tools. Use 'run' when the user says the name of a saved routine "
        "('modo trabalho', 'rotina da manhã'). 'create' when they define one — put "
        "the apps to open in 'apps' ('cria o modo trabalho com Chrome, VS Code e "
        "Spotify'); other actions go in 'steps'. 'edit' to add or remove apps "
        "('coloca o Discord no modo trabalho', 'tira o Spotify'). 'list' for 'quais "
        "rotinas eu tenho'; 'delete'; 'suggest' for 'o que você aprendeu dos meus "
        "hábitos'; 'learn' to save a suggested pattern. If the user asks to run a "
        "routine that does not exist yet, ask which apps it should open and create "
        "it. Steps may only use: open_app, weather_report, morning_briefing, "
        "music_control, quick_notes, web_search, timer_action, unit_converter, "
        "everyday_tools, video_player, youtube_video, price_alert, "
        "computer_settings, system_update, daily_planner. Do NOT use this for a "
        "single action — call that tool directly."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING",
                       "description": "create | edit | run | list | delete | suggest | learn | forget_habits"},
            "name": {"type": "STRING", "description": "Routine name, e.g. 'modo trabalho' (create/edit/run/delete/learn)"},
            "description": {"type": "STRING", "description": "Optional one-line purpose"},
            "apps": {
                "type": "ARRAY",
                "description": "create: apps to open all at once, by name or full path",
                "items": {"type": "STRING"},
            },
            "add_apps": {
                "type": "ARRAY",
                "description": "edit: apps to add to the routine",
                "items": {"type": "STRING"},
            },
            "remove_apps": {
                "type": "ARRAY",
                "description": "edit: apps to take out of the routine",
                "items": {"type": "STRING"},
            },
            "steps": {
                "type": "ARRAY",
                "description": "create/edit: other actions besides opening apps, in the order to run",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "tool": {"type": "STRING", "description": "Tool name from the allowed list"},
                        "params_json": {"type": "STRING",
                                        "description": "That tool's arguments as a JSON object string, e.g. {\"minutes\":25}"},
                    },
                    "required": ["tool"],
                },
            },
            "pattern_index": {"type": "INTEGER",
                              "description": "learn only: which suggested pattern (1 = first)"},
        },
        "required": ["action"],
    },
    "handler": routines_action,
}
