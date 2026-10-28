"""Rotinas por conversa (NEXUS Ultra 2026 3.3): propõe, mostra e só salva com o seu sim."""
from __future__ import annotations


def criar_rotina(parameters: dict, player=None) -> str:
    from core import rotinas_conversa as RC
    acao = str(parameters.get("action") or "propose").strip().lower()

    if acao == "confirm":
        return RC.confirmar()
    if acao == "cancel":
        return RC.cancelar()
    if acao == "list":
        ag = RC.agendadas()
        return ("Rotinas agendadas: " + "; ".join(f"{a['nome']} ({a['quando']})" for a in ag) + "."
                if ag else "Não há rotinas agendadas.")

    return RC.propor(parameters.get("name") or "", parameters.get("apps"), parameters.get("steps"),
                     parameters.get("days"), parameters.get("time"), parameters.get("description") or "")


TOOL = {
    "name": "criar_rotina",
    "description": ("Builds a routine from what the user said in ONE sentence, shows it, and saves it only after "
                    "the user says yes. Use for 'toda segunda de manhã abre o Spotify e me diz o clima', 'cria "
                    "uma rotina que...', 'todo dia às 8h...'. FLOW: 1) action=propose with name, apps (list), "
                    "steps (only safe tools, e.g. weather_report, music_control, timer_action, quick_notes) and, "
                    "if there is a schedule, days (e.g. ['segunda'] / 'dias úteis' / 'todo dia') and time (e.g. "
                    "'08:00'); 2) READ the preview to the user and ask if you may save; 3) on yes call "
                    "action=confirm; on no call action=cancel. NEVER confirm without the user's yes. "
                    "action=list shows the scheduled routines. Routines can never send messages, delete files "
                    "or control the mouse/keyboard. Answer in Portuguese, briefly."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "propose | confirm | cancel | list"},
            "name": {"type": "STRING", "description": "routine name, e.g. 'segunda de manhã'"},
            "apps": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "apps to open"},
            "steps": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
                "tool": {"type": "STRING"}, "params": {"type": "OBJECT"}}},
                "description": "other safe tool calls: [{tool, params}]"},
            "days": {"type": "STRING", "description": "when: 'segunda', 'dias úteis', 'todo dia', 'segunda e quarta'"},
            "time": {"type": "STRING", "description": "hour: '08:00', '8h30', 'de manhã'"},
            "description": {"type": "STRING", "description": "short description"},
        },
        "required": [],
    },
    "handler": criar_rotina,
}
