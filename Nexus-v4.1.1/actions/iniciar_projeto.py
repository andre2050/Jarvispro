"""Iniciar projeto por voz (NEXUS Ultra 2026 3.4) — a lógica fica em core/inicio_projeto.py.

"Inicia o projeto Loja Virtual em Python"    "para o tempo do projeto"
"quanto tempo trabalhei na Loja Virtual?"    "volta a trabalhar no projeto Loja Virtual"
"""
from __future__ import annotations


def iniciar_projeto(parameters: dict, player=None) -> str:
    from core import inicio_projeto as IP
    acao = str(parameters.get("action") or "start").strip().lower()
    nome = " ".join(str(parameters.get("name") or "").split())

    if acao == "stop":
        r = IP.parar_tempo()
        if not r:
            return "Nenhum relógio de projeto estava correndo."
        return f"Parei o tempo de {r[0]}: {IP.fmt_duracao(r[1])} nesta sessão."

    if acao in ("time", "report"):
        alvo = nome or IP.relogio_atual()
        if not alvo:
            return "Diga de qual projeto quer saber o tempo."
        t = IP.total(alvo)
        if not t["projeto"]:
            return f"Ainda não contei tempo para {alvo}."
        return (f"{t['projeto']}: hoje {IP.fmt_duracao(t['hoje'])}, nos últimos 7 dias "
                f"{IP.fmt_duracao(t['semana'])}, no total {IP.fmt_duracao(t['total'])}"
                + (" (o relógio está correndo)." if IP.relogio_atual() == t["projeto"] else "."))

    if not nome:
        return "[failed] Ask the user for the project's name (and, if they know, the language or technology)."

    tipo = str(parameters.get("technology") or "")
    try:
        pasta, criados = IP.criar_pasta(nome, tipo, objetivo=str(parameters.get("goal") or "").strip()[:400])
    except Exception as e:                                       # noqa: BLE001
        return f"[failed] Não consegui criar a pasta do projeto ({e})."
    editor = IP.abrir_editor(pasta, str(parameters.get("editor") or ""))
    doc = IP.abrir_documentacao(tipo) if str(parameters.get("open_docs", True)).lower() not in ("false", "0") else ""
    anterior = IP.iniciar_tempo(pasta.name)

    registro = ""
    try:
        from actions.projetos import projetos as _projetos
        registro = _projetos({"action": "add", "name": pasta.name, "note": f"pasta: {pasta}"})
    except Exception:
        pass
    ja_existia = "already exists" in registro

    if player is not None:
        try:
            player.write_log(f"SYS: 🚀 Projeto {pasta.name}: {pasta}")
        except Exception:
            pass
    partes = [f"Project '{pasta.name}' started.",
              f"Folder: {pasta}" + (f" (created: {', '.join(criados)})" if criados else " (already existed, kept as is)") + ".",
              f"Opened in: {editor}." if editor else "Could not open an editor.",
              f"Documentation opened: {doc}." if doc else "",
              "Time tracking started" + (f" (stopped the clock of '{anterior}')" if anterior else "") + ".",
              "It is in the projects list." if registro and not ja_existia else
              ("It was already in the projects list." if ja_existia else "")]
    return (" ".join(p for p in partes if p) +
            " [ASK_USER] Now ask the user, in their language: \"Qual é o próximo passo deste projeto?\" "
            f"When they answer, call projetos with action=update, name={pasta.name} and next_step=<their answer>.")


TOOL = {
    "name": "iniciar_projeto",
    "description": (
        "Starts a work project in ONE command: creates the project folder (README, notes, .gitignore, "
        "subfolders for the technology) in Desktop/Projetos NEXUS, opens it in the editor (VS Code by "
        "default), opens the official documentation, starts time tracking, adds it to the projects list and "
        "then asks for the next step. Use for 'inicia o projeto X', 'começa um projeto novo em Python', "
        "'abre tudo para trabalhar no projeto X'. action=start (default) with name, technology (python, web, "
        "react, node, django, unity…), optional goal and editor; action=stop stops the clock; action=time "
        "tells how long was spent (name optional). To have NEXUS WRITE the program itself use dev_agent."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "start (default) | stop | time"},
            "name": {"type": "STRING", "description": "Project name"},
            "technology": {"type": "STRING", "description": "Language or framework (optional)"},
            "goal": {"type": "STRING", "description": "What the project is for (optional)"},
            "editor": {"type": "STRING", "description": "Editor to open (default VS Code)"},
            "open_docs": {"type": "BOOLEAN", "description": "Open the documentation (default true)"},
        },
        "required": [],
    },
    "handler": iniciar_projeto,
}
