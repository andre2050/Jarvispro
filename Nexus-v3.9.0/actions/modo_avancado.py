"""Modo avançado: scripts seus em isolamento. Ver core/modo_avancado.py."""
from core import confirm as _confirm
from core import modo_avancado as M


def modo_avancado(parameters: dict, testar=None, **_kw) -> str:
    acao = str(parameters.get("action") or "list").strip().lower()
    nome = str(parameters.get("name") or "")
    try:
        if acao in ("save", "guardar"):
            return f"[done] Script “{M.guardar(nome, str(parameters.get('code') or ''), str(parameters.get('description') or ''))}” guardado. Na primeira execução vou pedir sua confirmação."
        if acao in ("remove", "remover"):
            return "[done] Removido." if M.remover(nome) else "Não achei."
        if acao in ("run", "executar"):
            args = parameters.get("args") if isinstance(parameters.get("args"), dict) else {}
            if M.precisa_confirmar(nome):
                if _confirm.pending_title():
                    return "Já há uma confirmação esperando na tela; resolva ela antes."
                def _rodar():
                    M.aprovar(nome)
                    return "[done] " + M.executar(nome, args, testar=testar)
                return _confirm.request(key="modo_avancado", title=f"Rodar o script “{nome}”?", detail="Roda isolado, sem rede e sem acesso aos seus arquivos. Aprovo este código.", run=_rodar)
            return "[done] " + M.executar(nome, args, testar=testar)
        itens = M.listar()
        return " | ".join(f"{i['nome']}{' ✓' if i['aprovado'] else ''} {i['descricao']}" for i in itens) or "Nenhum script guardado."
    except M.ErroScript as e:
        return f"[failed] {e}"


TOOL = {
    "name": "advanced_mode",
    "description": ("User script library. action=list | save (name, code with `def main(args)`, description) | run (name, args) | remove. Scripts are pure compute/text: "
                    "code that touches network, files, programs, screen or personal data is rejected. They run isolated, and the first run (or any run after the "
                    "code changed) asks an on-screen CONFIRM."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["list", "save", "run", "remove"]}, "name": {"type": "STRING"}, "code": {"type": "STRING"},
        "description": {"type": "STRING"}, "args": {"type": "OBJECT"}}, "required": ["action"]},
    "handler": modo_avancado,
}
