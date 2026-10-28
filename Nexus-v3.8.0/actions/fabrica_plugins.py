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
                    "(asks for on-screen CONFIRM). Never install without the user's yes."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["create", "install"]}, "request": {"type": "STRING"}}, "required": ["action"]},
    "handler": fabrica_plugins,
}
