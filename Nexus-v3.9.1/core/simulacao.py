"""Simulação "e se" (3.8) — mostra o que MUDARIA antes de qualquer ação grande, sem executar nada.

`simular(passos)` recebe a lista de passos {tool, args} (o plano de uma missão, por exemplo) e devolve, para cada um:
  efeito  le | escreve | apaga | move | envia | gasta | controla | instala | desconhecido
  risco   seguro | sensivel                      (sensivel = precisa da sua decisão)
  resumo  uma frase do que aconteceria, olhando o disco de verdade (existe? sobrescreve? quantos bytes? quantos arquivos?)
e um resumo geral. Nenhuma ferramenta é chamada, nenhum arquivo é tocado: só `os.stat` e `listdir`.
Você aprova o RESULTADO ("vai mover 12 arquivos e enviar 1 mensagem"), não só a intenção.
"""
from __future__ import annotations

import os
from pathlib import Path

LE, ESCREVE, APAGA, MOVE, ENVIA, GASTA, CONTROLA, INSTALA, DESCONHECIDO = (
    "le", "escreve", "apaga", "move", "envia", "gasta", "controla", "instala", "desconhecido")
SENSIVEIS = {ESCREVE, APAGA, MOVE, ENVIA, GASTA, CONTROLA, INSTALA}

# efeito padrão por ferramenta (None = decide pela ação)
EFEITOS_TOOL = {
    "web_search": LE, "weather_report": LE, "noticias": LE, "mapas": LE, "briefing": LE, "morning_briefing": LE,
    "resumo_diario": LE, "unit_converter": LE, "memoria_semantica": LE, "pesquisa_profunda": LE,
    "flight_finder": LE, "compras": LE, "auditoria": LE, "daily_planner": LE, "bom_dia": LE,
    "send_message": ENVIA, "ligar_whatsapp": ENVIA, "telegram_nexus": ENVIA,
    "email_reader": None, "file_controller": None, "notepad": ESCREVE, "quick_notes": ESCREVE, "tarefas": ESCREVE,
    "reminder": ESCREVE, "timer_action": ESCREVE, "diario": ESCREVE, "notion_nexus": ESCREVE,
    "computer_control": CONTROLA, "desktop": CONTROLA, "computer_settings": CONTROLA, "casa_inteligente": CONTROLA,
    "open_app": CONTROLA, "music_control": CONTROLA, "video_player": CONTROLA, "youtube_video": CONTROLA,
    "system_update": INSTALA, "game_updater": INSTALA, "loja_plugins": INSTALA, "fabrica_plugins": INSTALA,
    "price_alert": ESCREVE,
    "especialista": LE,          # 3.8: um agente especialista da missão (usa só ferramentas de leitura/redação)
}
EFEITOS_ACAO = {
    "file_controller": {"list": LE, "read": LE, "find": LE, "largest": LE, "disk_usage": LE, "info": LE, "summary": LE,
                        "folder_summary": LE, "open": LE, "watch": LE, "create_file": ESCREVE, "create_folder": ESCREVE,
                        "write": ESCREVE, "copy": ESCREVE, "delete": APAGA, "move": MOVE, "rename": MOVE,
                        "clean_temp": APAGA, "limpar_temp": APAGA, "hidden_files": ESCREVE},
    "email_reader": {"send": ENVIA, "reply": ENVIA, "status": LE, "latest": LE, "check": LE},
}


def efeito(tool: str, args: dict | None) -> str:
    args = args or {}
    base = EFEITOS_TOOL.get(tool, DESCONHECIDO)
    if base is None:
        acao = str(args.get("action") or "").lower()
        return EFEITOS_ACAO.get(tool, {}).get(acao, DESCONHECIDO)
    return base


def risco(tool: str, args: dict | None) -> str:
    e = efeito(tool, args)
    return "sensivel" if e in SENSIVEIS or e == DESCONHECIDO else "seguro"


def _tam(n: int) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024
    return f"{n} B"


def _caminho(args: dict, *chaves) -> Path | None:
    for k in chaves:
        v = args.get(k)
        if v:
            return Path(os.path.expandvars(str(v))).expanduser()
    return None


def _descrever_arquivo(tool: str, args: dict, ef: str) -> str:
    acao = str(args.get("action") or "").lower()
    origem = _caminho(args, "path", "source", "src", "file")
    nome = args.get("name")
    if origem and nome and not origem.suffix and acao in ("create_file", "write", "create_folder"):
        origem = origem / str(nome)
    destino = _caminho(args, "destination", "dest", "to")
    if acao in ("move", "rename", "copy"):
        if origem is None:
            return f"{acao} sem origem informada"
        if not origem.exists():
            return f"vai {acao} {origem.name}, mas a origem NÃO existe"
        extra = ""
        if origem.is_dir():
            try:
                extra = f" (pasta com {sum(1 for _ in origem.rglob('*'))} itens)"
            except OSError:
                pass
        alvo = destino or (origem.parent / str(args.get("new_name") or "?"))
        sobre = " — vai SOBRESCREVER um item que já existe lá" if alvo.exists() and not alvo.is_dir() else ""
        verbo = {"move": "mover", "rename": "renomear", "copy": "copiar"}[acao]
        return f"vai {verbo} {origem.name}{extra} para {alvo}{sobre}"
    if acao == "delete":
        if origem is None:
            return "vai apagar algo (sem caminho informado)"
        if not origem.exists():
            return f"vai apagar {origem.name}, mas ele não existe"
        if origem.is_dir():
            try:
                n = sum(1 for _ in origem.rglob("*"))
            except OSError:
                n = 0
            return f"vai APAGAR a pasta {origem.name} com {n} itens"
        return f"vai APAGAR {origem.name} ({_tam(origem.stat().st_size)})"
    if acao in ("clean_temp", "limpar_temp"):
        return "vai apagar arquivos temporários do sistema"
    if acao in ("write", "create_file"):
        if origem is None:
            return "vai gravar um arquivo (sem caminho informado)"
        if origem.exists():
            return f"vai SOBRESCREVER {origem.name} ({_tam(origem.stat().st_size)} hoje)" if not args.get("append") \
                else f"vai acrescentar texto ao fim de {origem.name}"
        return f"vai criar {origem.name} ({len(str(args.get('content') or ''))} caracteres)"
    if acao == "create_folder":
        return f"vai criar a pasta {origem.name if origem else '?'}" + (" (já existe)" if origem and origem.exists() else "")
    return f"{tool} {acao}"


def simular_passo(passo: dict) -> dict:
    tool, args = str(passo.get("tool") or ""), passo.get("args") if isinstance(passo.get("args"), dict) else {}
    ef = efeito(tool, args)
    if tool == "file_controller" and ef != LE:
        resumo = _descrever_arquivo(tool, args, ef)
    elif ef == ENVIA:
        para = args.get("contact") or args.get("to") or args.get("recipient") or args.get("name") or "alguém"
        txt = args.get("message") or args.get("body") or args.get("text") or ""
        resumo = f"vai ENVIAR uma mensagem para {para} ({len(str(txt))} caracteres)"
    elif ef == GASTA:
        resumo = "pode gerar um gasto"
    elif ef == CONTROLA:
        alvo = args.get("app_name") or args.get("action") or ""
        resumo = f"vai controlar o computador ({tool} {alvo})".strip()
    elif ef == INSTALA:
        resumo = f"vai instalar ou atualizar algo ({tool})"
    elif ef == ESCREVE:
        resumo = f"vai guardar dados ({tool})"
    elif ef == LE:
        resumo = "só lê informação"
    else:
        resumo = f"não sei o efeito de {tool}: trato como sensível"
    return {"tool": tool, "efeito": ef, "risco": "sensivel" if ef in SENSIVEIS or ef == DESCONHECIDO else "seguro",
            "resumo": resumo, "titulo": str(passo.get("titulo") or "")[:80]}


def simular(passos: list[dict]) -> dict:
    itens = [simular_passo(p) for p in passos if isinstance(p, dict)]
    cont: dict[str, int] = {}
    for i in itens:
        cont[i["efeito"]] = cont.get(i["efeito"], 0) + 1
    rot = {LE: "leitura(s)", ESCREVE: "gravação(ões)", APAGA: "exclusão(ões)", MOVE: "movimentação(ões)",
           ENVIA: "envio(s)", GASTA: "gasto(s)", CONTROLA: "controle(s) do PC", INSTALA: "instalação(ões)",
           DESCONHECIDO: "passo(s) de efeito desconhecido"}
    partes = [f"{n} {rot[e]}" for e, n in sorted(cont.items(), key=lambda x: -x[1])]
    sensiveis = [i for i in itens if i["risco"] == "sensivel"]
    return {"itens": itens, "contagem": cont, "sensiveis": len(sensiveis),
            "resumo": (f"{len(itens)} passo(s): " + ", ".join(partes) + ". " if itens else "Plano vazio. ")
                      + (f"{len(sensiveis)} precisam da sua decisão." if sensiveis else "Nada que precise da sua decisão.")}


def texto(sim: dict) -> str:
    linhas = [sim["resumo"]]
    for n, i in enumerate(sim["itens"], 1):
        marca = "⚠ " if i["risco"] == "sensivel" else "· "
        linhas.append(f"{marca}{n}. {i['titulo'] or i['tool']}: {i['resumo']}")
    return "\n".join(linhas)
