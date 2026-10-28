"""Oráculo de bem-estar por voz (NEXUS Ultra 2026 3.4) — a lógica fica em core/oraculo_bemestar.py.

"Monta meu plano do dia"     "dormi 6 horas e acordei às 7"     "energia 3"
"como está meu bem-estar?"   "o que você está vendo de risco na minha rotina?"
"""
from __future__ import annotations


def oraculo_bemestar(parameters: dict, player=None) -> str:
    from core import oraculo_bemestar as OB
    acao = str(parameters.get("action") or "plan").strip().lower()

    if acao in ("log", "checkin", "registrar"):
        return OB.registrar(sono_h=parameters.get("sleep_hours"), energia=parameters.get("energy"),
                            humor=parameters.get("mood"), agua=parameters.get("water_glasses"),
                            exercicio_min=parameters.get("exercise_minutes"), acordou=parameters.get("woke_up"),
                            dormiu=parameters.get("went_to_bed"), sintomas=parameters.get("symptoms"))

    ctx = OB.coletar()
    if acao in ("risks", "prevencao", "alerts"):
        alertas = OB.alertas_preventivos(ctx)
        if not alertas:
            return "Não vejo nenhum sinal repetido de risco nos seus dados desta semana. " + OB.AVISO_SAUDE
        return "Sinais da semana (data): " + " | ".join(alertas) + " " + OB.AVISO_SAUDE

    p = OB.plano(ctx)
    texto = OB.plano_texto(p)
    if player is not None:
        try:
            player.show_content("🌿 PLANO DO DIA", texto)
        except Exception:
            pass
    proximos = " | ".join(f"{h} {o}" for h, o in p["blocos"][:5])
    return (f"Plan (data): energy {p['energia']}/5 because {'; '.join(p['motivos'])}. Blocks: {proximos}. "
            f"Prevention: {' | '.join(p['alertas']) or 'nothing repeated this week'}. Tips: {' '.join(p['dicas'])} "
            "The full plan is on screen. Tell the user the energy, the focus block and any prevention note in 3-4 "
            "short sentences, in their language, warmly. Say it is a routine plan, not medical advice. If you have "
            "no sleep data, ask how they slept (then call action=log).")


TOOL = {
    "name": "oraculo_bemestar",
    "description": (
        "Personal wellbeing oracle: builds TODAY's life plan from the user's own data (sleep and energy they "
        "reported, mood from the diary, water/exercise habits, tasks and reminders, PC screen time, weather) — "
        "predicted energy, focus blocks at their peak, breaks, movement, bedtime — and PREVENTION notes for "
        "patterns repeated over days (little sleep, falling mood, task overload, too much screen, no exercise). "
        "action=plan (default) for 'monta meu plano do dia', 'como otimizar meu dia'; action=log to record "
        "'dormi 6 horas', 'acordei às 7', 'energia 3', 'bebi 2 copos', 'fiz 30 min de exercício', symptoms; "
        "action=risks for 'algum risco na minha rotina?'. Never diagnoses: it is not medical advice. Health "
        "data stays on the PC."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "plan (default) | log | risks"},
            "sleep_hours": {"type": "NUMBER", "description": "log: hours slept last night"},
            "energy": {"type": "INTEGER", "description": "log: energy 1-5"},
            "mood": {"type": "INTEGER", "description": "log: mood 1-5"},
            "water_glasses": {"type": "INTEGER", "description": "log: glasses of water so far"},
            "exercise_minutes": {"type": "INTEGER", "description": "log: minutes of exercise today"},
            "woke_up": {"type": "STRING", "description": "log: wake-up time, e.g. '7h'"},
            "went_to_bed": {"type": "STRING", "description": "log: bedtime, e.g. '23h30'"},
            "symptoms": {"type": "STRING", "description": "log: anything the user said they feel"},
        },
        "required": [],
    },
    "handler": oraculo_bemestar,
}
