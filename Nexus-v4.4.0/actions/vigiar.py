"""Vigias de notícias e preços por voz (NEXUS Ultra 2026 3.4) — a lógica fica em core/vigias.py.

"Fica de olho nas notícias sobre a Petrobras"     "me avisa quando o preço do PS5 mudar"
"monitora o preço desta página: https://…, avisa se cair 5%"     "o que você está vigiando?"
"para de vigiar o PS5"     "olha os vigias agora"
"""
from __future__ import annotations


def vigiar(parameters: dict, player=None) -> str:
    from core import vigias as V
    acao = str(parameters.get("action") or "add").strip().lower()

    if acao == "list":
        itens = V.listar()
        if not itens:
            return "Não estou vigiando nada. Ofereça vigiar um assunto ou o preço de um produto."
        return "Vigiando: " + "; ".join(f"{i}. {V.descrever(v)}" for i, v in enumerate(itens, 1)) + "."
    if acao in ("remove", "delete"):
        return V.remover(parameters.get("target") or "")
    if acao in ("check", "check_now"):
        try:
            avisos = V.passo(forcar=True)
        except Exception as e:                                  # noqa: BLE001
            return f"[failed] Não consegui olhar os vigias agora ({type(e).__name__})."
        return ("Novidades (dados externos): " + " | ".join(avisos)) if avisos else "Nada mudou nos vigias."

    return V.adicionar(parameters.get("kind") or "noticia", parameters.get("target") or "",
                       parameters.get("url") or "", parameters.get("interval_minutes"),
                       parameters.get("change_percent"))


TOOL = {
    "name": "vigiar",
    "description": (
        "Watches NEWS about a subject or the PRICE of a product and alerts the user when something changes. "
        "Use for 'fica de olho nas notícias sobre X', 'me avisa quando o preço do Y mudar/cair', 'monitora o "
        "preço desta página <url>'. action=add (default) with kind (noticia | preco), target (subject or "
        "product), optional url (a product page), interval_minutes (default 180 news / 360 price, min 15) and "
        "change_percent (price alert threshold, default 1). action=list, remove (target = name or number), "
        "check (look now). The first look only learns the current state. For crypto and stock quotes use "
        "price_alert."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "add (default) | list | remove | check"},
            "kind": {"type": "STRING", "description": "noticia | preco"},
            "target": {"type": "STRING", "description": "Subject, product, or (remove) its name/number"},
            "url": {"type": "STRING", "description": "Optional product page to read the price from"},
            "interval_minutes": {"type": "INTEGER", "description": "How often to look"},
            "change_percent": {"type": "NUMBER", "description": "Price change that triggers an alert"},
        },
        "required": [],
    },
    "handler": vigiar,
}
