"""Long-term memory — "remember that my daughter's name is Ana".

A persistent fact store the model can write to and query. Facts survive
restarts and, more importantly, are injected into the system prompt at
session build, so the assistant *knows* them without any tool call — the
tool exists for saving, searching and forgetting, not for recall of the
short list the prompt already carries.
"""

import json
import time
from pathlib import Path
from core.protecao import engolida as _engolida

try:
    CONFIG_DIR = Path(__file__).resolve().parent.parent / "memory"
except Exception:                                    # pragma: no cover
    CONFIG_DIR = Path("memory")

_FILE = CONFIG_DIR / "facts.json"
_MAX_PROMPT_FACTS = 30


def _load() -> list:
    try:
        data = json.loads(_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        _engolida("actions/memory_bank.py:29")
    return []


def _save(facts: list) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _FILE.write_text(json.dumps(facts, indent=2, ensure_ascii=False),
                         encoding="utf-8")
    except Exception as e:
        print(f"[MemoryBank] could not save: {e}")


def all_facts() -> list:
    return _load()


def facts_prompt_block() -> str:
    """The block injected into the system prompt — empty string when unused."""
    facts = _load()
    if not facts:
        return ""
    lines = [f"- {f['text']}" for f in facts[:_MAX_PROMPT_FACTS]]
    more = len(facts) - _MAX_PROMPT_FACTS
    if more > 0:
        lines.append(f"(and {more} older fact(s) — use the memory_bank tool "
                     "to search them)")
    return ("[KNOWN FACTS] The user explicitly asked you to remember these. "
            "Treat them as true and use them naturally, without reciting "
            "the list:\n" + "\n".join(lines))


def memory_bank_action(parameters: dict, player=None, session_memory=None) -> str:
    action = str(parameters.get("action") or "").strip().lower()
    text   = str(parameters.get("text") or "").strip()
    index  = parameters.get("fact_index")

    if action == "save":
        if not text:
            msg = "Sir, what fact would you like me to remember?"
            _log(msg, player)
            return msg
        facts = _load()
        # skip exact duplicates
        if any(str(f.get("text", "")).strip().lower() == text.lower()
               for f in facts):
            msg = "I already had that one noted, sir."
            _log(msg, player)
            return msg
        facts.append({"text": text, "at": time.time()})
        _save(facts)
        msg = f"Committed to memory, sir: {text}"
        _log(f"saved fact: {text!r}", player)
        return msg

    if action == "recall":
        query = text.lower()
        if not query:
            facts = _load()
            if not facts:
                msg = "Sir, there is nothing in the memory bank yet."
            else:
                lines = [f"{i}. {f['text']}" for i, f in enumerate(facts, 1)]
                msg = "Sir, everything I remember: " + " ".join(lines)
            _log("listed all facts", player)
            return msg
        hits = [(i, f) for i, f in enumerate(_load(), 1)
                if query in str(f.get("text", "")).lower()]
        if not hits:
            msg = f"Sir, I don't remember anything about '{text}'."
            _log(f"recall '{text}': 0 hits", player)
            return msg
        lines = [f"{i}. {f['text']}" for i, f in hits]
        msg = (f"Sir, {len(hits)} fact(s) matching '{text}': "
               + " ".join(lines))
        _log(f"recall '{text}': {len(hits)} hits", player)
        return msg

    if action == "delete":
        facts = _load()
        if not facts:
            msg = "Sir, the memory bank is empty."
            _log(msg, player)
            return msg
        try:
            idx = int(index) - 1
        except (TypeError, ValueError):
            msg = ("Sir, which fact number should I forget? Say 'recall' "
                   "without a query to see them numbered.")
            _log(msg, player)
            return msg
        if not (0 <= idx < len(facts)):
            msg = f"Sir, fact {index} doesn't exist — I hold {len(facts)}."
            _log(msg, player)
            return msg
        removed = facts.pop(idx)["text"]
        _save(facts)
        msg = f"Forgotten, sir: {removed}"
        _log(f"deleted fact #{index}", player)
        return msg

    if action == "clear":
        _save([])
        msg = "Memory bank cleared, sir."
        _log(msg, player)
        return msg

    msg = ("Sir, I can save a fact, recall what I remember, delete one by "
           "number, or clear everything.")
    _log(msg, player)
    return msg


def _log(message: str, player=None) -> None:
    print(f"[MemoryBank] {message}")
    if player:
        try:
            player.write_log(f"NEXUS: {message}")
        except Exception:
            _engolida("actions/memory_bank.py:148")


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "memory_bank",
    "description": (
        "Long-term memory of personal facts the user asks you to remember "
        "(names, preferences, routines, numbers). Actions: save (remember a "
        "fact), recall (search the memory, or list everything when no query "
        "is given), delete (forget one fact by number), clear (forget all). "
        "Saved facts are automatically known in future sessions."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["save", "recall", "delete", "clear"],
                "description": "What to do with the memory bank"
            },
            "text": {
                "type": "STRING",
                "description": "The fact (for save), or the search query "
                               "(for recall)"
            },
            "fact_index": {
                "type": "NUMBER",
                "description": "Fact number to forget (for delete)"
            },
        },
        "required": ["action"]
    },
    "handler": memory_bank_action,
}
