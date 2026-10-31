"""Perfil de ferramentas: 'usa o perfil essencial', 'quantas ferramentas você tem?'. Ver core/carga_ferramentas.py."""
from core import carga_ferramentas as C
from core.protecao import engolida as _engolida

_NOMES = {"completo": "completo (todas as ferramentas)", "recentes": "recentes (as essenciais e as que você usa)",
          "essencial": "essencial (só o básico)",
          "dinamico": "dinâmico (o básico e uma busca que alcança o resto)"}


def _decls():
    """Todas as declarações que existem agora: as fixas e as das ações carregadas."""
    out = C.declaracoes_fixas()
    try:
        if C.REGISTRO is not None:
            out += C.REGISTRO.get_tool_declarations()
    except Exception:
        _engolida("actions/carga_ferramentas.py:16")
    return out


def tool_load(parameters: dict, **_kw) -> str:
    acao = str(parameters.get("action") or "status").strip().lower()
    nome = str(parameters.get("tool") or "").strip()
    from core import preferences as P
    if acao in ("set", "definir", "mode"):
        modo = str(parameters.get("mode") or "").strip().lower()
        if modo not in C.MODOS:
            return f"[failed] Perfis possíveis: {', '.join(C.MODOS)}."
        P.save({"carga_ferramentas": modo})
        return f"[done] Perfil {_NOMES[modo]}. Vale quando a próxima conversa começar ou reconectar."
    if acao in ("pin", "fixar", "unpin", "desafixar"):
        if not nome:
            return "[failed] Diga o nome da ferramenta."
        atuais = [x for x in C.fixas() if x != nome]
        if acao in ("pin", "fixar"):
            atuais.append(nome)
        P.save({"ferramentas_fixas": atuais[:60]})
        return f"[done] {'Fixada' if acao in ('pin', 'fixar') else 'Desafixada'}: {nome}."
    r = C.resumo(_decls())
    msg = (f"Perfil atual: {_NOMES[r['modo']]}. O modelo recebe {r['visiveis']} de {r['total']} ferramentas "
           f"(cerca de {r['tokens_visiveis']:,} de {r['tokens_total']:,} tokens).".replace(",", "."))
    if r["ocultas"]:
        msg += f" Fora de vista: {', '.join(r['ocultas'][:15])}{'…' if len(r['ocultas']) > 15 else ''}."
    return "[done] " + msg


TOOL = {
    "name": "tool_load",
    "description": ("Chooses how many tools NEXUS shows the AI each conversation (fewer = faster start and fewer wrong tool picks). "
                    "action=status (default) | set with mode completo|recentes|essencial|dinamico | pin / unpin a tool by name. "
                    "Use for 'usa o perfil essencial', 'quantas ferramentas você tem?', 'volta para o perfil completo'. "
                    "Takes effect when the next conversation starts."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["status", "set", "pin", "unpin"]},
        "mode": {"type": "STRING", "enum": ["completo", "recentes", "essencial", "dinamico"]},
        "tool": {"type": "STRING"}}},
    "handler": tool_load,
}
