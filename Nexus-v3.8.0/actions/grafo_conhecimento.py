"""Memória em grafo: "o que eu tenho a ver com a Maria?", "como o projeto X liga com o João?". Detalhes: core/grafo.py."""
from core import grafo as G


def grafo_conhecimento(parameters: dict, **_kw) -> str:
    acao = str(parameters.get("action") or "about").strip().lower()
    try:
        if acao in ("rebuild", "reconstruir"):
            g = G.construir()
            g.salvar()
            return f"[done] Grafo atualizado: {len(g.nos)} itens e {len(g.arestas)} ligações."
        g = G.Grafo.carregar()
        if not g.nos:
            g = G.construir()
            g.salvar()
        if acao in ("path", "caminho"):
            r = g.caminho(str(parameters.get("query") or ""), str(parameters.get("to") or ""))
            return " → ".join(r) if r else "Não achei ligação entre os dois."
        return "[done] " + G.texto(g.vizinhanca(str(parameters.get("query") or ""), int(parameters.get("depth") or 2)))
    except Exception as e:
        return f"[failed] Grafo: {e}"


TOOL = {
    "name": "knowledge_graph",
    "description": ("Knowledge graph of the user's world (people, projects, commitments, preferences, notes) built from local "
                    "memory, with the SOURCE of each link. action=about (query=name): what is connected to it; "
                    "path (query, to): how two things connect; rebuild: refresh from the sources. Say the source when it matters."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["about", "path", "rebuild"]},
        "query": {"type": "STRING"}, "to": {"type": "STRING"}, "depth": {"type": "INTEGER"}},
        "required": ["action"]},
    "handler": grafo_conhecimento,
}
