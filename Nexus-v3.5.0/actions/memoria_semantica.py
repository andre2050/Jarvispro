"""Memória semântica — o NEXUS acha o que você disse pelo SENTIDO (NEXUS Ultra 2026 2.3).

Por voz:  "o que eu falei sobre a viagem?"        "procura nas minhas coisas algo sobre dinheiro"
          "o que anotei sobre o projeto da loja?"   "atualiza a memória semântica"
          "instala o modelo de sentido" (opcional, baixa uma vez ~120 MB e fica bem mais esperto)

Documentos (RAG pessoal, 3.5): "indexa a pasta Documentos/Contratos", "o que o contrato diz sobre multa?",
          "procura nos meus documentos algo sobre garantia", "quais pastas você lê?", "para de ler a pasta X".
          A resposta vem com a FONTE (arquivo e página/linha). Só entram as pastas que você adicionar.

Procura em notas, diário, tarefas, projetos, contatos, fatos da memória e resumos de conversas.
Diferença para `recall_memory`: aquele procura por PALAVRAS nos fatos guardados; este procura por
SENTIDO em tudo. Nada sai do PC (o texto achado só vai ao Gemini se você pedir para ele ler).
"""
from __future__ import annotations

import threading

from core import embeddings as E
from core import indice_semantico as IS
from core import rag_documentos as RD

_ROTULO = {"notas": "nota", "diario": "diário", "tarefas": "tarefa", "projetos": "projeto",
           "contatos": "contato", "memoria": "memória", "conversas": "conversa"}


def _atualizar_se_preciso(forcar: bool = False) -> dict | None:
    ind = IS.indice()
    if forcar or not ind.docs or (E.get_embedder("auto").nome != ind.motor):
        return ind.atualizar(forcar=forcar)
    return None


def _indexar_docs_em_segundo_plano() -> None:
    try:
        RD.indice().atualizar()
    except Exception as e:
        print(f"[RAG] indexação falhou: {e}")


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
        if acao in ("add_folder", "adicionar_pasta", "indexar_pasta"):
            ok, msg = RD.adicionar_pasta(str(parameters.get("folder") or parameters.get("query") or ""))
            if ok:
                threading.Thread(target=_indexar_docs_em_segundo_plano, daemon=True, name="rag-index").start()
                msg += " Estou lendo os arquivos em segundo plano; peça o status para ver o andamento."
            return ("[done] " if ok else "[failed] ") + msg
        if acao in ("remove_folder", "remover_pasta"):
            ok, msg = RD.remover_pasta(str(parameters.get("folder") or parameters.get("query") or ""))
            if ok:
                RD.indice().atualizar()
            return ("[done] " if ok else "[failed] ") + msg
        if acao in ("folders", "pastas"):
            pastas = RD.listar_pastas()
            if not pastas:
                return "Nenhuma pasta de documentos adicionada ainda. Diga “indexa a pasta …” para começar."
            return "Pastas na memória de documentos: " + " | ".join(pastas)
        if acao in ("docs_reindex", "indexar_docs"):
            if not RD.listar_pastas():
                return "Nenhuma pasta de documentos adicionada ainda. Diga “indexa a pasta …” para começar."
            r = RD.indice().atualizar(forcar=bool(parameters.get("force")))
            return (f"[done] Documentos: {r['arquivos']} arquivo(s), {r['trechos']} trecho(s) — "
                    f"{r['novos_arquivos']} novo(s), {r['alterados']} alterado(s), {r['removidos']} removido(s); motor {r['motor']}.")
        if acao in ("docs_status", "docs_estado"):
            ind = RD.indice()
            return (f"Documentos: {len(ind.assinaturas)} arquivo(s), {len(ind.trechos)} trecho(s), "
                    f"{len(RD.listar_pastas())} pasta(s); motor {ind.motor or 'ainda não criado'}.")
        if acao in ("docs_search", "ask_docs", "buscar_docs", "perguntar_docs"):
            q = str(parameters.get("query") or "").strip()
            if not q:
                return "O que devo procurar nos documentos?"
            if not RD.listar_pastas():
                return "Nenhuma pasta de documentos adicionada ainda. Diga “indexa a pasta …” para começar."
            ind = RD.indice()
            if not ind.trechos or E.get_embedder("auto").nome != ind.motor:
                ind.atualizar()
            try:
                k = max(1, min(8, int(parameters.get("top") or 4)))
            except (TypeError, ValueError):
                k = 4
            achados = ind.buscar(q, k=k, pasta=str(parameters.get("folder") or ""))
            if not achados:
                return f"Não achei nada sobre “{q}” nos documentos indexados."
            blocos = [f"({n}) [{RD.citacao(t)}] {t['texto']}" for n, (_, t) in enumerate(achados, 1)]
            return ("Trechos dos seus documentos (responda SÓ com base neles e cite a fonte entre colchetes; "
                    "se não bastarem, diga que não encontrou): " + " || ".join(blocos))
        if acao in ("install_model", "instalar_modelo"):
            ok, msg = E.baixar_modelo(print)
            if ok:
                IS.indice().atualizar(forcar=True)
            return ("[done] " if ok else "[failed] ") + msg
    except Exception as e:
        return f"[failed] Memória semântica: {e}"
    return ("Ação desconhecida. Use search, reindex, status, install_model, add_folder, remove_folder, folders, "
            "docs_reindex, docs_status ou docs_search.")


TOOL = {
    "name": "memoria_semantica",
    "description": (
        "SEMANTIC SEARCH over everything the user told NEXUS: notes, journal, tasks, projects, contacts, "
        "remembered facts and past conversation summaries — matches by MEANING, not exact words ('o que "
        "eu falei sobre a viagem?', 'algo sobre dinheiro'). action=search with query (+ optional sources "
        "comma list: notas,diario,tarefas,projetos,contatos,memoria,conversas, and top); action=reindex; "
        "action=status; action=install_model (one-time ~120 MB download that makes it much smarter). "
        "Prefer this over recall_memory when the user asks for something by topic or idea. "
        "DOCUMENTS (the user's own files: PDF, Word, PowerPoint, text, code): action=add_folder with folder "
        "(opt-in, indexes in background), remove_folder, folders, docs_reindex, docs_status, and "
        "action=docs_search with query (+ optional folder filter, top) — use it for 'o que o contrato diz "
        "sobre…', 'procura nos meus documentos…'. It returns excerpts WITH their source (file, page/line): answer "
        "only from them and cite the source; never invent content that is not in the excerpts."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "search | reindex | status | install_model | add_folder | remove_folder | folders | docs_reindex | docs_status | docs_search"},
            "folder": {"type": "STRING", "description": "For add_folder/remove_folder: the folder path or name. For docs_search: optional filter on the file path"},
            "query": {"type": "STRING", "description": "For search: what to look for, in the user's own words"},
            "sources": {"type": "STRING", "description": "For search: comma list to restrict (notas,diario,tarefas,projetos,contatos,memoria,conversas)"},
            "top": {"type": "INTEGER", "description": "For search: how many results (default 5)"},
            "force": {"type": "BOOLEAN", "description": "For reindex: recompute everything"},
        },
        "required": ["action"],
    },
    "handler": memoria_semantica,
}
