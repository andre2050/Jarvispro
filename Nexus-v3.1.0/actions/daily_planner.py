"""
Daily Planner — turns your notes, memory and habits into a prioritised plan.

    "planeja meu dia"  /  "o que devo fazer primeiro?"  /  "tenho 2 horas, o que priorizo?"

Everything it knows is local: quick notes, what the memory holds about you, and
the habits core/habits.py has learned for this hour. One model call (the shared
ladder in core.gemini) orders it all; without a key it still answers with a
plain, deterministic list, so the skill never comes back empty.
"""
from __future__ import annotations
from core.pt_time import agora, dia_hora

from datetime import datetime

_MAX_SPOKEN = 600


def _notes() -> list[str]:
    try:
        from actions.quick_notes import _load
        return [str(n.get("text", "")).strip() for n in _load() if n.get("text")][-15:]
    except Exception:
        return []


def _facts() -> str:
    try:
        from memory.memory_manager import search_memory
        return search_memory("projeto tarefa rotina trabalho agenda prioridade", limit=6) or ""
    except Exception:
        return ""


def _habit_line() -> str:
    try:
        from core import habits
        return habits.describe(habits.time_habits())
    except Exception:
        return ""


def _language() -> str:
    try:
        from memory.config_manager import load_api_keys
        return str(load_api_keys().get("reply_language") or "pt")
    except Exception:
        return "pt"


def daily_planner_action(parameters: dict, player=None, session_memory=None) -> str:
    focus = str(parameters.get("focus") or "").strip()
    try:
        hours = float(parameters.get("hours_available") or 0)
    except (TypeError, ValueError):
        hours = 0.0

    notes, facts, habit = _notes(), _facts(), _habit_line()
    try:                                   # as tarefas abertas entram no plano
        from actions import tarefas as _T
        notes = _T.resumo_para_plano() + notes
    except Exception:
        pass
    if not (notes or facts or focus):
        return ("Sir, I have nothing to plan from yet. Tell me your tasks or ask me to "
                "take a few notes, and I'll organise them.")

    now = dia_hora(agora())
    plan = ""
    try:
        from core import gemini
        if gemini.api_key():
            prompt = (
                f"Reply language code: {_language()}. Now: {now}.\n"
                f"Time available: {hours or 'unspecified'} hours. Focus: {focus or 'none'}.\n"
                f"Pending notes:\n- " + "\n- ".join(notes or ["(none)"]) + "\n"
                f"Known about the user:\n{facts or '(nothing)'}\n"
                f"Usual routine at this hour: {habit or '(unknown)'}\n\n"
                "Write a short plan to be SPOKEN: the 3 most important things in order, "
                "one sentence each, with a rough time for each. Quick wins first only if "
                "they unblock something. No markdown, no preamble."
            )
            plan = gemini.text(prompt, tier=gemini.SMART, timeout_ms=30_000)
    except Exception as e:
        print(f"[Planner] model unavailable: {e}")

    if not plan:       # deterministic fallback
        items = ([focus] if focus else []) + notes[-3:][::-1]
        plan = "Sir, here is what's pending: " + "; ".join(items[:4]) + "."

    if player is not None:
        try:
            player.show_content("DAILY PLAN", plan)
        except Exception:
            pass
    return plan[:_MAX_SPOKEN]


TOOL = {
    "name": "daily_planner",
    "description": (
        "Builds a prioritised plan for the day (or for the next few hours) from the "
        "user's saved notes, memory and learned habits. Use for 'planeja meu dia', "
        "'o que devo fazer primeiro', 'tenho 2 horas livres, o que priorizo'. "
        "Do NOT use it to add notes (quick_notes) or to set an alarm (reminder)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "focus": {"type": "STRING", "description": "Optional topic to centre the plan on"},
            "hours_available": {"type": "NUMBER", "description": "Optional hours the user has"},
        },
    },
    "handler": daily_planner_action,
}
