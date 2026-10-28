"""Quick voice notes — a persistent scratchpad the user talks to.

"Take a note: buy milk" / "what are my notes?" / "delete note 2" /
"clear all my notes". Notes live in config/quick_notes.json, survive
restarts, and each carries the timestamp of when it was taken so the
assistant can say "you asked me to remember this yesterday".
"""

import json
import time
from datetime import datetime
from pathlib import Path

# ── Config dir: same place api_keys.json lives ────────────────────────────────
try:
    from memory.config_manager import CONFIG_DIR
except Exception:
    CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

_NOTES_FILE = CONFIG_DIR / "quick_notes.json"
MAX_NOTES   = 200


def _load() -> list:
    try:
        data = json.loads(_NOTES_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def _save(notes: list) -> None:
    try:
        _NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
        _NOTES_FILE.write_text(
            json.dumps(notes[-MAX_NOTES:], indent=1, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"[Notes] ⚠️ couldn't save notes: {e}")


def _when(at: float) -> str:
    diff = time.time() - at
    if diff < 60:
        return "just now"
    if diff < 3600:
        return f"{int(diff // 60)} minutes ago"
    if diff < 86400:
        return f"{int(diff // 3600)} hours ago"
    days = int(diff // 86400)
    return f"{days} days ago" if days != 1 else "yesterday"


def quick_notes_action(parameters: dict, player=None, session_memory=None) -> str:
    action = str(parameters.get("action") or "").strip().lower()
    text   = str(parameters.get("text") or "").strip()
    index  = parameters.get("note_index")

    if action == "add":
        if not text:
            msg = "Sir, what would you like me to note down?"
            _log(msg, player)
            return msg
        notes = _load()
        notes.append({"text": text, "at": time.time()})
        _save(notes)
        msg = f"Noted, sir: {text}"
        _log(f"added: {text!r}", player)
        return msg

    if action == "list":
        notes = _load()
        if not notes:
            msg = "Sir, you have no notes yet. Ask me to take one any time."
            _log(msg, player)
            return msg
        lines = []
        for i, n in enumerate(reversed(notes), start=1):   # newest first
            lines.append(f"{i}. {n['text']} (from {_when(n['at'])})")
        msg = "Sir, your notes, newest first: " + " ".join(lines)
        _log(f"listed {len(notes)} notes", player)
        return msg

    if action == "delete":
        notes = _load()
        if not notes:
            msg = "Sir, there is nothing to delete."
            _log(msg, player)
            return msg
        try:
            idx = int(index) - 1                     # 1-based, newest first
        except (TypeError, ValueError):
            msg = "Sir, which note number should I delete? Ask for the list first."
            _log(msg, player)
            return msg
        if not (0 <= idx < len(notes)):
            msg = f"Sir, note {index} doesn't exist — you have {len(notes)}."
            _log(msg, player)
            return msg
        removed = notes.pop(-(idx + 1))              # stored oldest→newest
        _save(notes)
        msg = f"Deleted, sir: {removed['text']}."
        _log(msg, player)
        return msg

    if action == "search":
        query = text.lower()
        if not query:
            msg = "Sir, what should I search for in your notes?"
            _log(msg, player)
            return msg
        notes = _load()
        hits = [(i, n) for i, n in enumerate(reversed(notes), start=1)
                if query in str(n.get("text", "")).lower()]
        if not hits:
            msg = f"Sir, no notes mention '{text}'."
            _log(f"search '{text}': 0 hits", player)
            return msg
        lines = [f"{i}. {n['text']} (from {_when(n['at'])})" for i, n in hits]
        msg = (f"Sir, {len(hits)} note(s) mentioning '{text}', "
               f"newest first: " + " ".join(lines))
        _log(f"search '{text}': {len(hits)} hits", player)
        return msg

    if action == "read":
        notes = _load()
        if not notes:
            msg = "Sir, you have no notes yet."
            _log(msg, player)
            return msg
        try:
            idx = int(index) - 1                     # 1-based, newest first
        except (TypeError, ValueError):
            msg = "Sir, which note number should I read? The list comes first."
            _log(msg, player)
            return msg
        if not (0 <= idx < len(notes)):
            msg = f"Sir, note {index} doesn't exist — you have {len(notes)}."
            _log(msg, player)
            return msg
        n = notes[-(idx + 1)]                        # stored oldest→newest
        msg = f"Note {index}: {n['text']} — taken {_when(n['at'])}."
        _log(f"read note {index}", player)
        return msg

    if action == "clear":
        _save([])
        msg = "All notes cleared, sir."
        _log(msg, player)
        return msg

    msg = ("Sir, I can take a note, list your notes, delete one by number, "
           "or clear them all.")
    _log(msg, player)
    return msg


def _log(message: str, player=None) -> None:
    print(f"[Notes] {message}")
    if player:
        try:
            player.write_log(f"NEXUS: {message}")
        except Exception:
            pass


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "quick_notes",
    "description": (
        "A persistent voice scratchpad. Actions: add (remember a note the "
        "user dictates), list (read the notes back, newest first), search "
        "(find notes containing a word or phrase), read (read one note back "
        "by its number), delete (remove one note by its number), clear "
        "(erase every note). Notes survive restarts and carry timestamps."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["add", "list", "search", "read", "delete", "clear"],
                "description": "What to do with the notes"
            },
            "text": {
                "type": "STRING",
                "description": "The note text (only needed for 'add')"
            },
            "note_index": {
                "type": "NUMBER",
                "description": "Note number to delete, as shown by 'list' (only for 'delete')"
            },
        },
        "required": ["action"]
    },
    "handler": quick_notes_action,
}
