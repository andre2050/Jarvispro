"""Comandos criados pelo usuário (2.3) — Configurações › COMANDO › Adicionar comando.

Cada comando é uma frase curta e o pedido que o NEXUS executa no lugar dela:
  {"phrase": "modo cinema", "command": "abre a Netflix e baixa o volume para 30"}

Guardados nas preferências (config/api_keys.json › preferences.custom_commands).
  - Digitado: a frase é trocada pelo pedido antes de ir para a rede local/Gemini.
  - Por voz: a lista entra nas instruções do Gemini (vale na próxima conexão).
"""
from __future__ import annotations

import unicodedata

MAX_COMANDOS = 30
MAX_FRASE = 60
MAX_PEDIDO = 300


def _prefs():
    from core import preferences as P
    return P


def _norm(texto: str) -> str:
    """Minúsculas, sem acento e sem pontuação nas pontas — 'Modo Cinema!' == 'modo cinema'."""
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return " ".join(t.lower().strip(" .,!?;:").split())


def listar() -> list[dict]:
    try:
        cmds = _prefs().get("custom_commands")
    except Exception:
        cmds = None
    out = []
    for c in cmds if isinstance(cmds, list) else []:
        if not isinstance(c, dict):
            continue
        frase = str(c.get("phrase", "")).strip()[:MAX_FRASE]
        pedido = str(c.get("command", "")).strip()[:MAX_PEDIDO]
        if frase and pedido:
            out.append({"phrase": frase, "command": pedido})
    return out


def adicionar(frase: str, pedido: str) -> str:
    """Salva um comando novo. Devolve "" se deu certo, ou o motivo do erro."""
    frase, pedido = str(frase or "").strip(), str(pedido or "").strip()
    if not frase or not pedido:
        return "Preencha a frase e o que o NEXUS deve fazer."
    if len(frase) > MAX_FRASE:
        return f"A frase pode ter no máximo {MAX_FRASE} letras."
    if len(pedido) > MAX_PEDIDO:
        return f"O pedido pode ter no máximo {MAX_PEDIDO} letras."
    cmds = listar()
    if any(_norm(c["phrase"]) == _norm(frase) for c in cmds):
        return f"Já existe um comando “{frase}”."
    if len(cmds) >= MAX_COMANDOS:
        return f"No máximo {MAX_COMANDOS} comandos."
    cmds.append({"phrase": frase, "command": pedido})
    _prefs().save({"custom_commands": cmds})
    return ""


def remover(indice: int) -> None:
    cmds = listar()
    if 0 <= indice < len(cmds):
        cmds.pop(indice)
        _prefs().save({"custom_commands": cmds})


def traduzir(texto: str) -> str | None:
    """O pedido do comando cuja frase é exatamente `texto`, ou None."""
    alvo = _norm(texto)
    if not alvo:
        return None
    for c in listar():
        if _norm(c["phrase"]) == alvo:
            return c["command"]
    return None


def bloco_prompt() -> str:
    """Trecho das instruções do Gemini com os comandos do usuário (vazio se não há)."""
    cmds = listar()
    if not cmds:
        return ""
    linhas = "\n".join(f'- "{c["phrase"]}" → {c["command"]}' for c in cmds)
    return ("[USER CUSTOM COMMANDS]\n"
            "The user created these shortcuts. When the user says one of these "
            "phrases (by voice or typed), do exactly what the arrow says, as if "
            "the user had asked for it directly:\n" + linhas + "\n")
