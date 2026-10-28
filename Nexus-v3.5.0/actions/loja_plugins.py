"""Loja de plugins por voz (NEXUS Ultra 2026 3.5) — pacotes .nexusplugin assinados e com permissões.

Por voz:  "quais plugins da loja eu tenho?"   "instala o plugin da pasta Downloads/clima.nexusplugin"
          "remove o plugin clima"            "confia no autor Maria com a chave …"
Instalar SEMPRE mostra CONFIRMAR no HUD, com o autor, a assinatura e as permissões pedidas.
Plugin sem assinatura de autor confiável é recusado. Detalhes: core/plugin_loja.py."""
from __future__ import annotations

from pathlib import Path

from core import confirm as _confirm
from core import plugin_loja as L


def _achar(caminho: str) -> Path:
    p = Path(caminho.strip().strip('"')).expanduser()
    if p.is_file():
        return p
    for pasta in (Path.home() / "Downloads", Path.home() / "Desktop", Path.home() / "Documents"):
        q = pasta / p.name
        if q.is_file():
            return q
    return p


def loja_plugins(parameters: dict, player=None) -> str:
    acao = str(parameters.get("action") or "list").strip().lower()
    try:
        if acao in ("list", "listar"):
            itens = L.instalados()
            if not itens:
                return "Nenhum plugin instalado pela loja. Plugins soltos na pasta plugins/ continuam funcionando."
            return "Plugins da loja: " + " | ".join(
                f"{i['nome']} {i['versao']} ({'assinado por ' + i['assinado_por'] if i.get('assinado_por') else 'sem assinatura'}; "
                f"permissões: {', '.join(i['concedidas']) or 'nenhuma'})" for i in itens)
        if acao in ("install", "instalar"):
            caminho = str(parameters.get("path") or "").strip()
            if not caminho:
                return "Qual pacote .nexusplugin devo instalar? Diga o caminho do arquivo."
            pacote = L.abrir_pacote(_achar(caminho))
            if not pacote.assinado:
                return ("[failed] Recusei: " + pacote.resumo() + " Só instalo plugins assinados por um autor de confiança "
                        "(peça a chave pública do autor e diga “confia no autor …”).")
            if _confirm.pending_title():
                return "Já há uma confirmação esperando na tela; resolva ela antes."
            return _confirm.request(
                key=f"plugin_{pacote.id}", title=f"INSTALAR PLUGIN {pacote.manifesto['nome'].upper()}",
                detail=pacote.resumo(),
                run=lambda: "[done] " + L.instalar(pacote, conceder=pacote.permissoes))
        if acao in ("remove", "remover"):
            return "[done] " + L.remover(str(parameters.get("name") or parameters.get("path") or ""))
        if acao in ("trust", "confiar"):
            ok, msg = L.confiar_no_autor(str(parameters.get("name") or ""), str(parameters.get("key") or ""))
            return ("[done] " if ok else "[failed] ") + msg
        if acao in ("authors", "autores"):
            return "Autores confiáveis: " + ", ".join(L.autores_confiaveis())
    except L.ErroPacote as e:
        return f"[failed] {e}"
    except Exception as e:
        return f"[failed] Loja de plugins: {e}"
    return "Ação desconhecida. Use list, install, remove, trust ou authors."


TOOL = {
    "name": "loja_plugins",
    "description": (
        "PLUGIN STORE: signed .nexusplugin packages with declared permissions. action=list (installed store plugins), "
        "action=install with path (shows a CONFIRM banner with author, signature and permissions; unsigned packages "
        "are refused), action=remove with name, action=trust with name and key (trust a plugin author's public key), "
        "action=authors. Use for 'instala o plugin…', 'quais plugins da loja…', 'remove o plugin…'."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "list | install | remove | trust | authors"},
            "path": {"type": "STRING", "description": "For install: path or file name of the .nexusplugin package"},
            "name": {"type": "STRING", "description": "For remove: plugin id or name. For trust: the author's name"},
            "key": {"type": "STRING", "description": "For trust: the author's public key (base64)"},
        },
        "required": ["action"],
    },
    "handler": loja_plugins,
}
