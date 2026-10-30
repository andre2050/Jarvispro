"""Preparação para a próxima reunião. Ver core/reuniao.py."""
from core import reuniao as R


def preparar_reuniao(parameters: dict, llm=None, eventos=None, contatos=None, **_kw) -> str:
    try:
        ev = eventos() if eventos else R.proximo_evento()
        if contatos is None:
            from actions import contatos as C
            contatos = C._ler()
        if llm is None:
            try:
                from core import hibrido
                llm = lambda p: hibrido.completar(p, nuvem=lambda t: "", local=lambda t: "", auditar=False)[0]   # sem modelo ligado: só fatos
            except Exception:
                llm = None
        return R.preparar(ev, contatos, llm)
    except Exception as e:
        return f"[failed] Não consegui preparar: {str(e)[:120]}"


TOOL = {
    "name": "meeting_prep",
    "description": "Prepare the user for the next calendar meeting: when/where, which saved contacts are named in the title, and a few prep points. Read-only; uses only the calendar and saved contacts.",
    "parameters": {"type": "OBJECT", "properties": {}},
    "handler": preparar_reuniao,
}
