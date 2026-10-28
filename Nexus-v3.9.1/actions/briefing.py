"""Morning briefing — the day in one breath.

Gathers the real day context the user would otherwise ask for one by one:
weather, pending notes, running timers and price alerts — plus the date
itself. Used two ways: as a tool the model can call any time ("good
morning", "what's my day like"), and by the startup briefing in main.py,
which feeds this straight into its phase-2 prompt so the assistant opens
the session already knowing the day.

Weather comes from actions/weather_report.py (Open-Meteo, free, no key); the city is the one saved as
home city (the tool can save it too — "my city is Fortaleza").
"""

import time as _time
from core.pt_time import agora
from core.pt_time import data_extensa
from datetime import datetime
from urllib.parse import quote_plus


def fetch_weather(city: str) -> str:
    """Clima de agora e de hoje — a fonte é a mesma da ferramenta weather_report."""
    from actions.weather_report import resumo_atual
    return resumo_atual(city)


def gather_context(city: str = None, player=None) -> str:
    """Every available day-context section, newline-joined. Sections that
    are unavailable are simply omitted; total failure returns ''."""
    sections = []

    # ── weather ──
    _city = (city or "").strip()
    if not _city:
        try:
            from memory.config_manager import load_api_keys
            _city = str(load_api_keys().get("home_city", "")).strip()
        except Exception:
            _city = ""
    if _city:
        try:
            sections.append(f"WEATHER in {_city}: {fetch_weather(_city)}")
        except Exception as e:
            _log(f"weather unavailable: {e!r}", player)

    # ── pending notes ──
    try:
        from actions.quick_notes import _load as _notes_load
        notes = _notes_load()
        if notes:
            recent = "; ".join(str(n.get("text", "")) for n in notes[-3:])
            sections.append(f"NOTES ({len(notes)} pending): {recent}")
    except Exception:
        pass

    # ── running timers ──
    try:
        from actions.timer_action import _ACTIVE
        if _ACTIVE:
            parts = []
            for n, v in _ACTIVE.items():
                if v.get("paused"):
                    left = max(0, int(v.get("remaining", 0.0)))
                else:
                    left = max(0, int(v["ends_at"] - _time.time()))
                parts.append(f"{n} "
                             f"({'paused, ' if v.get('paused') else ''}"
                             f"{left // 60} min left)")
            sections.append("TIMERS: " + "; ".join(parts))
    except Exception:
        pass

    # ── price alerts ──
    try:
        from actions.price_alert import pending_summary
        s = pending_summary()
        if s:
            sections.append(s)
    except Exception:
        pass

    # ── aniversários de hoje (2.2) ──
    try:
        from actions.contatos import aniversariantes_de_hoje
        nomes = aniversariantes_de_hoje()
        if nomes:
            sections.append("BIRTHDAYS TODAY: " + ", ".join(nomes))
    except Exception:
        pass

    # ── hábitos de hoje (2.2) ──
    try:
        from actions import rastreador_habitos as _H
        dados = _H._ler()
        hoje = _H._hoje()
        abertos = [h["nome"] for h in dados["habitos"] if _H.total_do_dia(h, hoje) < float(h["meta"])]
        if abertos:
            sections.append("HABITS STILL OPEN TODAY: " + ", ".join(abertos[:5]))
    except Exception:
        pass

    return "\n".join(sections)


def briefing_action(parameters: dict, player=None, session_memory=None) -> str:
    city      = str(parameters.get("city") or "").strip()
    save_city = bool(parameters.get("save_city"))

    # "my city is X" — persist it so every future briefing uses it
    if save_city and city:
        try:
            from memory.config_manager import save_city as _save_cfg_city
            _save_cfg_city(city)
            _log(f"home city saved: {city}", player)
        except Exception as e:
            _log(f"could not save city: {e!r}", player)

    now = agora()
    out = [f"Hoje é {data_extensa(now)}, "
           f"{now:%H:%M}."]
    ctx = gather_context(city, player)
    if ctx:
        out.append(ctx)
    msg = "\n".join(out)
    _log("briefing gathered" + (" with weather" if "WEATHER" in msg else ""),
         player)
    return msg


def _log(message: str, player=None) -> None:
    print(f"[Briefing] {message}")
    if player:
        try:
            player.write_log(f"NEXUS: {message}")
        except Exception:
            pass


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "morning_briefing",
    "description": (
        "Gathers the day context: date and time, current weather for the "
        "user's city, pending quick notes, running timers and active price "
        "alerts. Use it when the user greets you (good morning) or asks "
        "what their day looks like, then present the result naturally. "
        "If the user tells you their city, pass city + save_city=true to "
        "persist it for every future briefing."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "city": {
                "type": "STRING",
                "description": "City for the weather (optional — the saved "
                               "home city is used by default)"
            },
            "save_city": {
                "type": "BOOLEAN",
                "description": "Set true together with 'city' to save it as "
                               "the user's home city"
            },
        },
        "required": []
    },
    "handler": briefing_action,
}
