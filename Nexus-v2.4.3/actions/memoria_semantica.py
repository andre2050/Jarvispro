"""Memória semântica — o NEXUS acha o que você disse pelo SENTIDO (NEXUS Pro 2.3).

Por voz:  "o que eu falei sobre a viagem?"        "procura nas minhas coisas algo sobre dinheiro"
          "o que anotei sobre o projeto da loja?"   "atualiza a memória semântica"
          "instala o modelo de sentido" (opcional, baixa uma vez ~120 MB e fica bem mais esperto)

Procura em notas, diário, tarefas, projetos, contatos, fatos da memória e resumos de conversas.
Diferença para `recall_memory`: aquele procura por PALAVRAS nos fatos guardados; este procura por
SENTIDO em tudo. Nada sai do PC (o texto achado só vai ao Gemini se você pedir para ele ler).
"""
from __future__ import annotations

from core import embeddings as E
from core import indice_semantico as IS

_ROTULO = {"notas": "nota", "diario": "diário", "tarefas": "tarefa", "projetos": "projeto",
           "contatos": "contato", "memoria": "memória", "conversas": "conversa"}


def _atualizar_se_preciso(forcar: bool = False) -> dict | None:
    ind = IS.indice()
    if forcar or not ind.docs or (E.get_embedder("auto").nome != ind.motor):
        return ind.atualizar(forcar=forcar)
    return None


def memoria_semantica(parameters: dict, player=None) -> str:
    acao = str(parameters.get("action") or "search").strip().lower()
    try:
        if acao in ("search", "buscar", "procurar"):
            q = str(parameters.get("query") or "").strip()
            if not q:
                return "O que devo procurar?"
            _atualizar_se_preciso()
            fontes = [f.strip() for f in str(parameters.get("sources") or "").split(",") if f.strip() in IS.FONTES]
            try:
                k = max(1, min(10, int(parameters.get("top") or 5)))
            except (TypeError, ValueError):
                k = 5
            achados = IS.indice().buscar(q, k=k, fontes=fontes or None)
            if not achados:
                return f"Não achei nada parecido com “{q}” nas suas notas, diário, tarefas e memórias."
            return f"{len(achados)} resultado(s) por sentido: " + " | ".join(
                f"[{_ROTULO.get(d['fonte'], d['fonte'])}] {d['texto']}" for _, d in achados)
        if acao in ("reindex", "atualizar", "update"):
            r = IS.indice().atualizar(forcar=bool(parameters.get("force")))
            return (f"[done] Índice atualizado: {r['total']} item(ns) ({r['novos']} novo(s), "
                    f"{r['removidos']} removido(s)), motor {r['motor']}.")
        if acao in ("status", "estado"):
            ind = IS.indice()
            motor = E.get_embedder("auto").nome
            return (f"Índice com {len(ind.docs)} item(ns), motor {ind.motor or 'ainda não criado'}. "
                    f"Motor disponível agora: {motor}. Modelo de sentido (ONNX): "
                    f"{'instalado' if E.modelo_instalado() else 'não instalado'}"
                    f"{'' if E.onnx_disponivel() else ' (faltam onnxruntime e tokenizers)'}.")
        if acao in ("install_model", "instalar_modelo"):
            ok, msg = E.baixar_modelo(print)
            if ok:
                IS.indice().atualizar(forcar=True)
            return ("[done] " if ok else "[failed] ") + msg
    except Exception as e:
        return f"[failed] Memória semântica: {e}"
    return "Ação desconhecida. Use search, reindex, status ou install_model."


TOOL = {
    "name": "memoria_semantica",
    "description": (
        "SEMANTIC SEARCH over everything the user told NEXUS: notes, journal, tasks, projects, contacts, "
        "remembered facts and past conversation summaries — matches by MEANING, not exact words ('o que "
        "eu falei sobre a viagem?', 'algo sobre dinheiro'). action=search with query (+ optional sources "
        "comma list: notas,diario,tarefas,projetos,contatos,memoria,conversas, and top); action=reindex; "
        "action=status; action=install_model (one-time ~120 MB download that makes it much smarter). "
        "Prefer this over recall_memory when the user asks for something by topic or idea."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "search | reindex | status | install_model"},
            "query": {"type": "STRING", "description": "For search: what to look for, in the user's own words"},
            "sources": {"type": "STRING", "description": "For search: comma list to restrict (notas,diario,tarefas,projetos,contatos,memoria,conversas)"},
            "top": {"type": "INTEGER", "description": "For search: how many results (default 5)"},
            "force": {"type": "BOOLEAN", "description": "For reindex: recompute everything"},
        },
        "required": ["action"],
    },
    "handler": memoria_semantica,
}
