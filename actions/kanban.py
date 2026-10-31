"""Quadros Kanban em Markdown (compatíveis com o Obsidian). Ver core/kanban.py."""
from core import kanban as K


def kanban_board(parameters: dict, **_kw) -> str:
    acao = str(parameters.get("action") or "list").strip().lower()
    quadro = str(parameters.get("board") or "")
    try:
        if acao in ("list", "listar"):
            q = K.listar()
            return "[done] Quadros: " + ", ".join(q) + "." if q else "[done] Nenhum quadro ainda. Diga: cria o quadro Casa."
        if acao in ("create", "criar"):
            K.novo(quadro)
            return f"[done] Quadro “{quadro}” criado com as colunas A fazer, Fazendo e Feito."
        if acao in ("show", "mostrar"):
            return "[done] " + K.resumo(quadro)
        if acao in ("add", "adicionar"):
            col = K.adicionar(quadro, parameters.get("card"), str(parameters.get("column") or ""))
            return f"[done] Cartão adicionado em “{col}”."
        if acao in ("move", "mover"):
            return f"[done] Movido para “{K.mover(quadro, str(parameters.get('card') or ''), str(parameters.get('column') or ''))}”."
        if acao in ("done", "concluir"):
            return f"[done] Movido para “{K.mover(quadro, str(parameters.get('card') or ''), 'Feito')}”."
        if acao in ("remove", "remover"):
            return f"[done] Cartão “{K.remover(quadro, str(parameters.get('card') or ''))}” removido."
        if acao in ("folder", "pasta"):
            from core import preferences as P
            caminho = str(parameters.get("path") or "").strip()
            if not caminho:
                return f"[done] Os quadros ficam em {K.pasta()}."
            P.save({"kanban_pasta": str(K.validar_pasta(caminho))})
            return f"[done] Os quadros agora ficam em {K.pasta()}. Aponte para o seu cofre do Obsidian para vê-los lá."
        return "[failed] Ação desconhecida."
    except K.ErroKanban as e:
        return f"[failed] {e}"


TOOL = {
    "name": "kanban_board",
    "description": ("Kanban boards stored as Markdown files compatible with the Obsidian Kanban plugin. action=list | create (board) | show (board) | "
                    "add (board, card, column optional) | move (board, card, column) | done (board, card) | remove (board, card) | folder (path = Obsidian vault folder). "
                    "Use for 'cria o quadro Casa', 'adiciona X em A fazer', 'move X para Feito', 'mostra o quadro'."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["list", "create", "show", "add", "move", "done", "remove", "folder"]},
        "board": {"type": "STRING"}, "card": {"type": "STRING"}, "column": {"type": "STRING"},
        "path": {"type": "STRING", "description": "Folder for the boards (inside the user's home folder)"}}, "required": ["action"]},
    "handler": kanban_board,
}
