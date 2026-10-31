"""Conversation threads — the assistant remembers what you were in the middle of.

Before this, the only thing that survived the end of a conversation was a
1-2 sentence summary, and that summary was read out once in the morning
briefing and then deleted. Talk to NEXUS at night about the bug you were
fixing and the next evening it had no idea it ever happened.

This module keeps two things in memory/conversations.json:

  sessions  — a short summary of each of the last conversations (rolling)
  threads   — the "open loops": things the user is in the middle of, plans
              with a date, a problem still unsolved, something they said they
              would do. Each one has a number so it can be closed later.

Both are injected into the system prompt at every session build, so the model
simply *knows* what happened last time — and it is allowed to ask about ONE
open thread, the way a friend who remembers would ("conseguiu resolver aquele
erro do painel?"). The proactive check-in can also pick a thread to follow up.

At the end of each session ONE model call reads the transcript and returns the
summary, the new threads, and which old threads were touched or resolved. The
user can also close or forget a thread by voice through the TOOL below.

Nothing here leaves the machine except that one end-of-session call, which uses
the same Gemini ladder as everything else (core.gemini).
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

from core.pt_time import agora
from core.protecao import engolida as _engolida

try:
    _DIR = Path(__file__).resolve().parent.parent / "memory"
except Exception:                                    # pragma: no cover
    _DIR = Path("memory")

_FILE = _DIR / "conversations.json"
_lock = threading.Lock()

_MAX_SESSIONS     = 12   # kept on disk
_PROMPT_SESSIONS  = 5    # shown to the model
_MAX_OPEN         = 12   # open threads shown to the model
_MAX_NEW_PER_RUN  = 3    # new threads one conversation may open
_STALE_DAYS       = 21   # untouched this long → archived, no longer mentioned
_MAX_TRANSCRIPT   = 60   # last N lines of the session sent to the summariser


# ── Storage ────────────────────────────────────────────────────────────────────

def _empty() -> dict:
    return {"sessions": [], "threads": [], "next_id": 1}


def _load() -> dict:
    try:
        data = json.loads(_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("sessions", [])
            data.setdefault("threads", [])
            data.setdefault("next_id", 1)
            return data
    except Exception:
        _engolida("actions/conversation_threads.py:68")
    return _empty()


def _save(data: dict) -> None:
    try:
        _DIR.mkdir(parents=True, exist_ok=True)
        tmp = _FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(_FILE)
    except Exception as e:
        print(f"[Threads] ⚠️ could not save: {e}")


def _today() -> str:
    return agora().strftime("%Y-%m-%d")


def _days_since(date_str: str) -> int:
    try:
        return (agora().date() - datetime.strptime(date_str, "%Y-%m-%d").date()).days
    except Exception:
        return 0


def _when(date_str: str) -> str:
    d = _days_since(date_str)
    if d <= 0:
        return "earlier today"
    if d == 1:
        return "yesterday"
    if d < 7:
        return f"{d} days ago"
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m")
    except Exception:
        return date_str


def _archive_stale(data: dict) -> bool:
    """Open threads nobody has touched in _STALE_DAYS stop being mentioned."""
    changed = False
    for t in data["threads"]:
        if t.get("status") == "open" and _days_since(t.get("last_seen", "")) > _STALE_DAYS:
            t["status"] = "stale"
            changed = True
    return changed


def _open_threads(data: dict) -> list[dict]:
    return [t for t in data["threads"] if t.get("status") == "open"]


# ── Prompt block ───────────────────────────────────────────────────────────────

def context_block() -> str:
    """What the model is told at session build. Empty string when unused."""
    with _lock:
        data = _load()
        if _archive_stale(data):
            _save(data)

    sessions = data["sessions"][-_PROMPT_SESSIONS:]
    threads  = _open_threads(data)[-_MAX_OPEN:]
    if not sessions and not threads:
        return ""

    out = []
    if sessions:
        out.append(
            "[RECENT CONVERSATIONS]\n"
            "Notes from your last conversations with the user, oldest first. "
            "You remember these the way a person remembers yesterday's chat: "
            "draw on them when they are relevant, never recite them, and never "
            "say you are reading notes."
        )
        for s in sessions:
            when = _when(s.get("date", ""))
            hhmm = s.get("time", "")
            out.append(f"- {when}{' ' + hhmm if hhmm else ''}: {s.get('summary', '')}")
        out.append("")

    if threads:
        out.append(
            "[OPEN THREADS]\n"
            "Things the user was in the middle of. When a conversation opens "
            "after a gap, or one of these subjects comes up, you may ask about "
            "ONE of them in a single natural sentence — how it went, whether it "
            "worked. That is a real follow-up from someone who remembers, not "
            "filler. At most one per conversation unless the user picks it up. "
            "Do not bring one up in the middle of an unrelated task. When the "
            "user says one is done, solved, cancelled or no longer relevant, "
            "silently call conversation_threads with action='close' and its "
            "number. If they reveal a new plan or an unsolved problem worth "
            "following up, you may call action='add'."
        )
        for t in threads:
            out.append(f"#{t['id']} (since {_when(t.get('opened', ''))}): {t.get('text', '')}")
        out.append("")

    return "\n".join(out)


# ── End-of-session digest ──────────────────────────────────────────────────────

def _digest_prompt(transcript: str, language: str, open_threads: list[dict]) -> str:
    existing = "\n".join(f"#{t['id']}: {t.get('text', '')}" for t in open_threads) or "(none)"
    return f"""You maintain the conversational memory of a personal voice assistant.
Read the conversation below and return ONLY a JSON object, no prose, no fences:

{{
  "summary": "2-3 sentences in {language}: what the user talked about, did or decided. Concrete names, numbers and outcomes, no filler.",
  "new_threads": ["short note in {language} about something the user is in the middle of"],
  "touched": [ids of EXISTING open threads that came up again but are still open],
  "resolved": [ids of EXISTING open threads the user said are done, solved, cancelled or no longer relevant]
}}

What counts as a thread — something with a natural next step a friend would ask about later:
- a project or task in progress ("está corrigindo o bug do painel de configurações")
- a plan with a time ("vai viajar para Salvador na sexta")
- a problem still unsolved, or something being tested or waited on
- something the user said they would do

NOT a thread: anything the assistant already finished in this conversation, small
talk, a one-off question that was answered, weather, music, opening apps.
At most {_MAX_NEW_PER_RUN} new threads; usually zero or one. Never duplicate an existing
open thread — put its id in "touched" instead. Write each thread as a note about
the user in the third person, under 15 words.

Existing open threads:
{existing}

Conversation:
{transcript}
"""


def digest_session(log_lines: list[str], language: str = "English") -> str | None:
    """Summarise the session and update the threads.

    Returns the summary text (so the caller can keep feeding the morning
    briefing), "" when there was nothing worth keeping, or None when the model
    call failed — the caller then falls back to the old one-line summary.
    """
    lines = [l for l in (log_lines or []) if str(l).strip()]
    if len(lines) < 3:
        return ""

    with _lock:
        data = _load()
    open_now = _open_threads(data)

    transcript = "\n".join(lines[-_MAX_TRANSCRIPT:])
    prompt = _digest_prompt(transcript, language or "English", open_now)

    try:
        from core import gemini
        result = gemini.as_json(prompt, gemini.SMART, None, 30_000)
    except Exception as e:
        print(f"[Threads] ⚠️ digest failed: {e}")
        return None
    if not isinstance(result, dict):
        return None

    summary = str(result.get("summary") or "").strip()

    def _ids(key: str) -> set[int]:
        out = set()
        for v in result.get(key) or []:
            try:
                out.add(int(str(v).lstrip("#")))
            except (TypeError, ValueError):
                pass
        return out

    resolved = _ids("resolved")
    touched  = _ids("touched")
    new      = [str(t).strip() for t in (result.get("new_threads") or []) if str(t).strip()]

    today = _today()
    now   = agora().strftime("%H:%M")

    with _lock:
        data = _load()                      # re-read: the tool may have written meanwhile
        for t in data["threads"]:
            if t.get("status") != "open":
                continue
            if t["id"] in resolved:
                t["status"] = "closed"
                t["closed"] = today
            elif t["id"] in touched:
                t["last_seen"] = today

        known = {str(t.get("text", "")).strip().lower() for t in _open_threads(data)}
        for text in new[:_MAX_NEW_PER_RUN]:
            if text.lower() in known:
                continue
            data["threads"].append({
                "id": data["next_id"], "text": text[:200],
                "opened": today, "last_seen": today,
                "followed_up": "", "status": "open",
            })
            data["next_id"] += 1

        if summary:
            data["sessions"].append({"date": today, "time": now, "summary": summary[:400]})
            data["sessions"] = data["sessions"][-_MAX_SESSIONS:]

        # closed / stale threads are history — keep the file small
        data["threads"] = (_open_threads(data)
                           + [t for t in data["threads"] if t.get("status") != "open"][-30:])
        _save(data)

    print(f"[Threads] 🧵 session digested — {len(new)} new, "
          f"{len(resolved)} resolved, {len(touched)} touched.")
    return summary


# ── Proactive follow-up ────────────────────────────────────────────────────────

def pick_followup() -> str | None:
    """One open thread the assistant has not asked about today, or None.

    Opened-today threads are skipped — asking "how did it go?" an hour after
    the user mentioned it is nagging, not remembering. The chosen thread is
    marked so it is not picked again the same day.
    """
    today = _today()
    with _lock:
        data = _load()
        candidates = [t for t in _open_threads(data)
                      if t.get("followed_up") != today and t.get("opened") != today]
        if not candidates:
            return None
        candidates.sort(key=lambda t: (t.get("followed_up") or "", t.get("last_seen") or ""))
        chosen = candidates[0]
        chosen["followed_up"] = today
        _save(data)
    return chosen.get("text") or None


# ── Tool ───────────────────────────────────────────────────────────────────────

def conversation_threads_action(parameters: dict, player=None) -> str:
    action = str(parameters.get("action") or "").strip().lower()
    text   = str(parameters.get("text") or "").strip()
    try:
        tid = int(str(parameters.get("thread_id") or "0").lstrip("#"))
    except (TypeError, ValueError):
        tid = 0
    today = _today()

    with _lock:
        data = _load()

        if action == "list":
            threads = _open_threads(data)
            if not threads:
                return "No open threads."
            return "Open threads: " + " ".join(f"#{t['id']}: {t['text']}." for t in threads)

        if action == "add":
            if not text:
                return "Nothing to add — give the thread text."
            if any(t["text"].strip().lower() == text.lower() for t in _open_threads(data)):
                return "Already tracked."
            data["threads"].append({
                "id": data["next_id"], "text": text[:200],
                "opened": today, "last_seen": today,
                "followed_up": "", "status": "open",
            })
            data["next_id"] += 1
            _save(data)
            _log(f"opened thread: {text!r}", player)
            return "Thread saved. Say nothing about it."

        if action in ("close", "forget"):
            for i, t in enumerate(data["threads"]):
                if t.get("id") == tid:
                    if action == "forget":
                        data["threads"].pop(i)
                    else:
                        t["status"] = "closed"
                        t["closed"] = today
                    _save(data)
                    _log(f"{action} thread #{tid}", player)
                    return ("Thread closed. Say nothing about it." if action == "close"
                            else "Thread forgotten. Confirm in a few words.")
            return f"There is no thread #{tid}."

    return "Unknown action. Use list, add, close or forget."


def _log(message: str, player=None) -> None:
    print(f"[Threads] {message}")
    if player:
        try:
            player.write_log(f"SYS: {message}")
        except Exception:
            _engolida("actions/conversation_threads.py:368")


TOOL = {
    "name": "conversation_threads",
    "description": (
        "Your memory of what the user is in the middle of between conversations "
        "(the [OPEN THREADS] list). Actions: close (the user says a thread is "
        "done, solved or no longer relevant — pass its number), add (the user "
        "reveals a plan or an unsolved problem worth asking about later), "
        "forget (the user asks you to forget that subject), list (read them). "
        "Use silently; never announce it."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["list", "add", "close", "forget"],
                "description": "What to do",
            },
            "thread_id": {
                "type": "NUMBER",
                "description": "Thread number from [OPEN THREADS] (close / forget)",
            },
            "text": {
                "type": "STRING",
                "description": "Short third-person note about the user, in their language (add)",
            },
        },
        "required": ["action"],
    },
    "handler": conversation_threads_action,
    # Left BLOCKING on purpose: the call is an instant local file write, and no
    # other bundled action uses NON_BLOCKING yet, so it is not worth the risk
    # of a Live model rejecting the declaration. The results tell the model to
    # stay quiet instead.
}
