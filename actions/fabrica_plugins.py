"""Fábrica de plugins por conversa: "cria um plugin que …". Escreve, revisa, testa em caixa de areia e só instala com CONFIRMAR."""
from pathlib import Path

from core import confirm as _confirm
from core import fabrica_plugins as F
from core import plugin_loja as L

_ULTIMA: dict = {}


def _llm(prompt: str) -> str:
    from core import gemini
    return gemini.text(prompt, tier=gemini.SMART, timeout_ms=90_000)


def fabrica_plugins(parameters: dict, llm=None, **_kw) -> str:
    acao = str(parameters.get("action") or "create").strip().lower()
    try:
        if acao in ("create", "criar"):
            p = F.preparar(str(parameters.get("request") or ""), llm or _llm, Path(L.PASTA_PLUGINS).parent / "plugins_gerados")
            if not p["ok"]:
                return f"[failed] {p.get('motivo')}"
            _ULTIMA.clear()
            _ULTIMA.update(p)
            return ("[done] Plugin criado e testado, ainda NÃO instalado. Leia este resumo ao usuário e pergunte se instala: "
                    + F.resumo(p))
        pasta = Path(L.PASTA_PLUGINS).parent / "plugins_gerados"
        pid = str(parameters.get("plugin") or "").strip().lower()
        if acao in ("versions", "versoes"):
            vs = F.versoes(pid, pasta)
            return " | ".join(f"v{v['versao']} ({v['linhas']} linhas; permissões: {', '.join(v['permissoes']) or 'nenhuma'})"
                              for v in vs) or "Não conheço esse plugin gerado."
        if acao in ("diff", "comparar"):
            c = F.comparar(pid, int(parameters.get("from") or 1), int(parameters.get("to") or 2), pasta)
            if not c:
                return "Não achei essas versões."
            return (f"De v{c['de']} para v{c['para']}: +{c['linhas_novas']} / -{c['linhas_removidas']} linhas. "
                    + (f"PERMISSÕES NOVAS: {', '.join(c['permissoes_novas'])}. " if c["permissoes_novas"] else "Sem permissões novas. ")
                    + "\n" + c["diff"][:900])
        if acao in ("improve", "melhorar"):
            p = F.evoluir(pid, str(parameters.get("request") or ""), llm or _llm, pasta)
            if not p["ok"]:
                return f"[failed] {p.get('motivo')}"
            _ULTIMA.clear()
            _ULTIMA.update(p)
            return "[done] Nova versão pronta e testada, ainda NÃO instalada. Leia ao usuário e pergunte: " + F.resumo(p)
        if acao in ("rollback", "voltar"):
            p = F.reempacotar(pid, int(parameters.get("version") or 0), pasta)
            if not p["ok"]:
                return f"[failed] {p.get('motivo')}"
            _ULTIMA.clear()
            _ULTIMA.update(p)
            return "[done] Versão antiga pronta para reinstalar (revisada e testada de novo). Leia ao usuário e pergunte: " + F.resumo(p)
        if acao in ("install", "instalar"):
            if not _ULTIMA.get("pacote"):
                return "[failed] Não há plugin pronto para instalar. Peça para criar primeiro."
            if _confirm.pending_title():
                return "Já há uma confirmação esperando na tela; resolva ela antes."
            pacote = L.abrir_pacote(_ULTIMA["pacote"])
            return _confirm.request(
                key="fabrica_plugins_install", title=f"Instalar o plugin gerado “{pacote.nome}”?", detail=F.resumo(_ULTIMA),
                run=lambda: "[done] " + L.instalar(pacote, conceder=pacote.permissoes, aceitar_nao_assinado=True))
        return "[failed] Ação desconhecida."
    except Exception as e:
        return f"[failed] Fábrica de plugins: {e}"


TOOL = {
    "name": "plugin_factory",
    "description": ("Creates a NEW plugin from a spoken request ('cria um plugin que …'): writes the code, reviews its "
                    "permissions, tests it in a sandbox. action=create (request) then, ONLY if the user says yes, install "
                    "(asks for on-screen CONFIRM). Every version is kept: versions (plugin) lists them, diff (plugin, from, to) shows what changed incl. NEW permissions, improve (plugin, request) makes a new version, rollback (plugin, version) goes back. Never install without the user's yes."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["create", "install", "versions", "diff", "improve", "rollback"]},
        "request": {"type": "STRING"}, "plugin": {"type": "STRING"}, "from": {"type": "INTEGER"}, "to": {"type": "INTEGER"},
        "version": {"type": "INTEGER"}}, "required": ["action"]},
    "handler": fabrica_plugins,
}
