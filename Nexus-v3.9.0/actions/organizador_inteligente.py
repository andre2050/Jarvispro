"""Organização inteligente de qualquer pasta, com regras suas. Ver core/organizador_inteligente.py."""
from core import confirm as _confirm
from core import organizador_inteligente as OI


def organizar_pasta(parameters: dict, **_kw) -> str:
    acao = str(parameters.get("action") or "plan").strip().lower()
    try:
        if acao in ("add_rule", "regra"):
            return "[done] Regra: " + OI.adicionar_regra(parameters.get("contains", ""), parameters.get("extension", ""), parameters.get("folder", ""))
        if acao in ("rules", "regras"):
            r = OI._regras()
            return " | ".join(f"{i}. {x.get('texto') or ''} {('.' + x['ext']) if x.get('ext') else ''} → {x['pasta']}" for i, x in enumerate(r, 1)) or "Sem regras suas ainda."
        if acao in ("remove_rule",):
            return "[done] Regra removida." if OI.remover_regra(int(parameters.get("number") or 0)) else "Não achei essa regra."
        if acao in ("undo", "desfazer"):
            return OI.desfazer()
        p = OI.plano(str(parameters.get("folder_path") or ""))
        if acao in ("apply", "aplicar") and p["mover"]:
            if _confirm.pending_title():
                return "Já há uma confirmação esperando na tela; resolva ela antes."
            return _confirm.request(key="organizar_pasta", title=f"Arrumar {p['raiz'].name}?", detail=OI.texto_plano(p)[:400], run=lambda: "[done] " + OI.aplicar(p))
        return OI.texto_plano(p)
    except (ValueError, OSError) as e:
        return f"[failed] {e}"


TOOL = {
    "name": "organize_folder",
    "description": ("Smart organizer for any folder (Downloads, Documents…). action=plan (default, changes nothing) | apply (asks on-screen CONFIRM) | undo | "
                    "add_rule (contains, extension, folder) | rules | remove_rule (number). folder_path required for plan/apply. Never overwrites or deletes."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["plan", "apply", "undo", "add_rule", "rules", "remove_rule"]}, "folder_path": {"type": "STRING"},
        "contains": {"type": "STRING"}, "extension": {"type": "STRING"}, "folder": {"type": "STRING"}, "number": {"type": "INTEGER"}}},
    "handler": organizar_pasta,
}
