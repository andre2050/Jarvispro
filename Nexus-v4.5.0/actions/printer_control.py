"""Controle de impressora por voz. Ver core/impressora.py."""
from core import confirm as _confirm
from core import impressora as I


def printer_control(parameters: dict, **_kw) -> str:
    acao = str(parameters.get("action") or "list").strip().lower()
    impressora = str(parameters.get("printer") or "")
    try:
        if acao in ("list", "listar"):
            lista = I.listar()
            if not lista:
                return "[failed] Nenhuma impressora instalada foi encontrada."
            return "[done] " + "; ".join(i["nome"] + (" (padrão)" if i["padrao"] else "") for i in lista)
        if acao in ("queue", "fila"):
            f = I.fila(impressora)
            return "[done] " + ("Na fila: " + " | ".join(f) if f else "A fila está vazia.")
        if acao in ("print_file", "imprimir_arquivo"):
            caminho, copias = str(parameters.get("path") or ""), parameters.get("copies", 1)
            p = I.validar_arquivo(caminho)
            nome = I.escolher(impressora)
            return _pedir(f"Imprimir “{p.name}”?", f"Impressora: {nome}. Cópias: {I._copias(copias)}.",
                          lambda: "[done] " + I.imprimir_arquivo(caminho, impressora, copias))
        if acao in ("print_text", "imprimir_texto"):
            texto, copias = str(parameters.get("text") or ""), parameters.get("copies", 1)
            if not texto.strip():
                return "[failed] Não há texto para imprimir."
            nome = I.escolher(impressora)
            return _pedir("Imprimir este texto?", f"Impressora: {nome}. {len(texto)} caracteres, começando com: {texto[:80]!r}",
                          lambda: "[done] " + I.imprimir_texto(texto, impressora, copias))
        if acao in ("cancel", "cancelar"):
            nome = I.escolher(impressora)
            return _pedir("Cancelar a fila de impressão?", f"Impressora: {nome}. Todos os trabalhos dela serão cancelados.",
                          lambda: "[done] " + I.cancelar(impressora))
        return "[failed] Ação desconhecida. Use list, queue, print_file, print_text ou cancel."
    except I.ErroImpressora as e:
        return f"[failed] {e}"


def _pedir(titulo: str, detalhe: str, executar) -> str:
    if _confirm.pending_title():
        return "Já há uma confirmação esperando na tela; resolva ela antes."

    def _rodar():
        try:
            return executar()
        except I.ErroImpressora as e:
            return f"[failed] {e}"
    return _confirm.request(key="printer_control", title=titulo, detail=detalhe, run=_rodar)


TOOL = {
    "name": "printer_control",
    "description": ("Printer control. action=list (printers) | queue (print jobs) | print_file (path, printer, copies) | print_text (text, printer, copies) | "
                    "cancel (clears the queue). Use for 'imprime este arquivo', 'quais impressoras tenho?', 'cancela a impressão'. "
                    "Printing and cancelling ask an on-screen CONFIRM first. Only files inside the user's home folder can be printed."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["list", "queue", "print_file", "print_text", "cancel"]},
        "path": {"type": "STRING", "description": "Full path of the file to print"},
        "text": {"type": "STRING", "description": "Text to print"},
        "printer": {"type": "STRING", "description": "Printer name or part of it; empty = default printer"},
        "copies": {"type": "INTEGER"}}, "required": ["action"]},
    "handler": printer_control,
}
