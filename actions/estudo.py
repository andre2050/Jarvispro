"""Estudo por voz: cartões com repetição espaçada e quiz. Ver core/estudo.py."""
from core import estudo as E

_quiz: dict = {"perguntas": [], "i": 0, "acertos": 0, "baralho": ""}


def _pergunta_atual() -> str:
    q = _quiz["perguntas"][_quiz["i"]]
    return E.formatar_pergunta(q, _quiz["i"] + 1, len(_quiz["perguntas"]))


def study(parameters: dict, **_kw) -> str:
    acao = str(parameters.get("action") or "stats").strip().lower()
    baralho = str(parameters.get("deck") or "")
    dado = E.carregar()
    try:
        if acao in ("add", "adicionar"):
            c = E.adicionar(dado, parameters.get("question"), parameters.get("answer"), baralho)
            E.salvar(dado)
            return f"[done] Cartão {c['id']} guardado no baralho “{c['baralho']}”."
        if acao in ("import", "importar"):
            n = E.importar(dado, str(parameters.get("text") or ""), baralho)
            E.salvar(dado)
            return f"[done] {n} cartões guardados." if n else "[failed] Não achei cartões. Use uma linha por cartão: pergunta :: resposta."
        if acao in ("next", "revisar", "proximo"):
            fila = E.devidos(dado, baralho)
            if not fila:
                return "[done] Nada para revisar hoje. Bom trabalho!"
            c = fila[0]
            return f"[done] Cartão {c['id']} (faltam {len(fila)} hoje): {c['p']} — pergunte e só depois mostre a resposta."
        if acao in ("show", "mostrar"):
            c = E.achar(dado, parameters.get("card"))
            return f"[done] Resposta: {c['r']}" if c else "[failed] Não achei esse cartão."
        if acao in ("grade", "nota", "avaliar"):
            c = E.achar(dado, parameters.get("card"))
            if not c:
                return "[failed] Não achei esse cartão."
            try:
                nota = int(parameters.get("grade"))
            except (TypeError, ValueError):
                return "[failed] Dê uma nota de 0 (não lembrei) a 5 (fácil)."
            E.avaliar(c, nota)
            E.salvar(dado)
            return f"[done] Anotado. Esse cartão volta em {c['intervalo']} dia(s)."
        if acao in ("remove", "remover"):
            ok = E.remover(dado, parameters.get("card"))
            E.salvar(dado)
            return "[done] Cartão removido." if ok else "[failed] Não achei esse cartão."
        if acao in ("quiz", "quiz_start", "iniciar_quiz"):
            perguntas = E.montar_quiz(dado, int(parameters.get("count") or 5), baralho)
            _quiz.update(perguntas=perguntas, i=0, acertos=0, baralho=baralho)
            return "[done] Quiz começou. " + _pergunta_atual()
        if acao in ("answer", "responder", "quiz_answer"):
            if not _quiz["perguntas"]:
                return "[failed] Não há quiz em andamento. Peça um quiz primeiro."
            q = _quiz["perguntas"][_quiz["i"]]
            esc = E.ler_escolha(parameters.get("choice"), q)
            if esc is None:
                return "[failed] Responda com a letra (A, B, C ou D)."
            certa = esc == q["correta"]
            c = E.achar(dado, str(q["id"]))
            if c:
                E.avaliar(c, 4 if certa else 1)
            _quiz["acertos"] += int(certa)
            _quiz["i"] += 1
            retorno = "Certo!" if certa else f"Errado. A resposta era {E.LETRAS[q['correta']]}) {q['opcoes'][q['correta']]}."
            if _quiz["i"] >= len(_quiz["perguntas"]):
                total, acertos = len(_quiz["perguntas"]), _quiz["acertos"]
                dado["historico"].append({"quando": E.date.today().isoformat(), "acertos": acertos, "total": total})
                _quiz["perguntas"] = []
                E.salvar(dado)
                return f"[done] {retorno} Fim do quiz: {acertos} de {total}."
            E.salvar(dado)
            return f"[done] {retorno} " + _pergunta_atual()
        s = E.estatisticas(dado)
        if not s["cartoes"]:
            return "[done] Você ainda não tem cartões. Diga, por exemplo: cria o cartão capital da França :: Paris."
        return (f"[done] {s['cartoes']} cartões, {s['para_hoje']} para revisar hoje, {s['dominados']} dominados"
                + (f", acerto de {int(s['acerto'] * 100)}%." if s["acerto"] is not None else "."))
    except ValueError as e:
        return f"[failed] {e}"


TOOL = {
    "name": "study",
    "description": ("Study helper: flashcards with spaced repetition and multiple-choice quizzes. action=add (question, answer, deck) | import (text, "
                    "one 'question :: answer' per line) | next (next due card; ask it, then show) | show (card) | grade (card, grade 0-5) | remove (card) | "
                    "quiz (count, deck) then answer (choice A-D) | stats. Use for 'cria um cartão', 'o que devo revisar hoje?', 'me faz um quiz', 'como estou nos estudos?'."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["add", "import", "next", "show", "grade", "remove", "quiz", "answer", "stats"]},
        "question": {"type": "STRING"}, "answer": {"type": "STRING"}, "deck": {"type": "STRING"}, "text": {"type": "STRING"},
        "card": {"type": "STRING", "description": "Card number or part of the question"}, "grade": {"type": "INTEGER"},
        "count": {"type": "INTEGER"}, "choice": {"type": "STRING", "description": "A, B, C or D"}}, "required": ["action"]},
    "handler": study,
}
