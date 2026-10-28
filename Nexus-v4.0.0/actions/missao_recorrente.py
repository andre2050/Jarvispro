"""Missões agendadas: "toda sexta às 17h, monte o resumo da semana". Cada disparo é uma missão normal (com as mesmas aprovações)."""
from core import missoes_recorrentes as R


def missao_recorrente(parameters: dict, **_kw) -> str:
    acao = str(parameters.get("action") or "list").strip().lower()
    rid = str(parameters.get("id") or "").strip()
    try:
        if acao in ("add", "agendar"):
            it = R.adicionar(str(parameters.get("goal") or ""), parameters.get("days"), str(parameters.get("time") or ""),
                             {"horas": parameters.get("budget_hours"), "chamadas": parameters.get("budget_calls"),
                              "sensiveis": parameters.get("budget_sensitive")}, bool(parameters.get("rehearse")))
            return f"[done] Agendado ({it['id']}): {R.texto([it])}. Cada vez, passos que enviam ou apagam continuam pedindo o seu sim."
        if acao in ("remove", "remover"):
            return "[done] Removida." if R.remover(rid) else "Não achei essa agenda."
        if acao in ("pause", "pausar", "resume", "retomar"):
            return "[done] Ok." if R.pausar(rid, acao in ("resume", "retomar")) else "Não achei essa agenda."
        return R.texto(R.listar())
    except R.ErroAgenda as e:
        return f"[failed] {e}"


TOOL = {
    "name": "recurring_mission",
    "description": ("Scheduled missions: action=add (goal, days like 'sexta' or 'dias úteis', time 'HH:MM', optional budget_*, rehearse) | "
                    "list | remove (id) | pause (id) | resume (id). Each run is a normal mission and still asks approval for sensitive steps."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["add", "list", "remove", "pause", "resume"]}, "goal": {"type": "STRING"},
        "days": {"type": "STRING"}, "time": {"type": "STRING"}, "id": {"type": "STRING"}, "rehearse": {"type": "BOOLEAN"},
        "budget_hours": {"type": "NUMBER"}, "budget_calls": {"type": "INTEGER"}, "budget_sensitive": {"type": "INTEGER"}},
        "required": ["action"]},
    "handler": missao_recorrente,
}
