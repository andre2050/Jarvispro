"""Bloco de Notas por voz (NEXUS Pro 1.4).

  "abre o bloco de notas"                         → action=open
  "escreve no bloco de notas uma lista de compras" → action=write (o Gemini monta o texto)
  "acrescenta 'comprar leite' no bloco de notas"   → action=append (na janela aberta)
  "lê o que está no bloco de notas"                → action=read
  "salva o bloco de notas como receita"            → action=save
  "abre o bloco de notas e escreve o que eu falar" → action=dictate  (modo ditado)
  "parar ditado"                                   → action=stop_dictation
  "abre minhas notas no bloco de notas"            → action=notes
  "quais notas eu tenho na pasta?"                 → action=list

Os arquivos ficam em Documentos\\NEXUS Notas (os ditados em ...\\Ditados).
A janela é controlada por core/bloco_de_notas.py, sem simular teclado.
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path


def _B():
    from core import bloco_de_notas as B
    return B


def _arquivo_novo(titulo: str) -> Path:
    B = _B()
    pasta = B.pasta_notas()
    nome = B.nome_seguro(titulo) if titulo else f"nota {datetime.now():%Y-%m-%d %H-%M}"
    arq = pasta / f"{nome}.txt"
    n = 2
    while arq.exists():
        arq = pasta / f"{nome} ({n}).txt"
        n += 1
    return arq


def _achar_arquivo(nome: str) -> Path | None:
    if not nome:
        return None
    p = Path(nome).expanduser()
    if p.is_file():
        return p
    pasta = _B().pasta_notas()
    alvo = nome.lower().removesuffix(".txt").strip()
    for arq in sorted(pasta.rglob("*.txt"), key=lambda a: -a.stat().st_mtime):
        if arq.stem.lower() == alvo:
            return arq
    for arq in sorted(pasta.rglob("*.txt"), key=lambda a: -a.stat().st_mtime):
        if alvo in arq.stem.lower():
            return arq
    return None


def notepad(parameters: dict, player=None) -> str:
    B = _B()
    acao = str(parameters.get("action") or "open").strip().lower()
    texto = str(parameters.get("text") or "")
    titulo = str(parameters.get("title") or "").strip()

    if acao in ("dictate", "start_dictation", "ditado"):
        ok, msg = B.ditado.iniciar(titulo, origem="voz")
        return msg + " " + B.INSTRUCAO_FERRAMENTA if ok else f"Não consegui ligar o ditado: {msg}"

    if acao in ("stop_dictation", "parar_ditado"):
        if B.ditado.recem_parado():
            # o NEXUS já tinha percebido o "parar ditado" e já avisou
            return ("O ditado já foi encerrado e salvo. Não repita a confirmação: "
                    "se ainda não confirmou, diga só uma frase curta.")
        ok, msg = B.ditado.parar(origem="ferramenta")
        return msg if ok else msg + " Nada a fazer."

    if B.ditado.ativo and acao not in ("read",):
        return ("O modo ditado está ligado: tudo o que o usuário fala vai para o Bloco de Notas. "
                "Fique em silêncio. Para sair, ele diz 'parar ditado'.")

    if acao == "open":
        arq = _achar_arquivo(titulo or texto) if (titulo or texto) else None
        if (titulo or texto) and arq is None and not texto:
            return f"Não consegui abrir: não achei a nota '{titulo}' em {B.pasta_notas()}."
        try:
            B.abrir_no_editor(arq) if arq else _abrir_vazio()
        except Exception as e:
            return f"Não consegui abrir o Bloco de Notas: {e}"
        return f"Opened o Bloco de Notas{f' com {arq.name}' if arq else ''}."

    if acao == "write":
        if not texto.strip():
            return "Não consegui escrever: faltou o texto (escreva o conteúdo completo em 'text')."
        arq = _arquivo_novo(titulo)
        arq.write_text(texto.replace("\r\n", "\n"), encoding="utf-8")
        try:
            B.abrir_no_editor(arq)
        except Exception as e:
            return f"Salvei em {arq}, mas não consegui abrir o Bloco de Notas: {e}"
        if player:
            player.write_log(f"SYS: 📝 Escrevi no Bloco de Notas — {arq.name}")
        return f"Escrevi o texto no Bloco de Notas e salvei em {arq}."

    if acao == "append":
        if not texto.strip():
            return "Não consegui acrescentar: faltou o texto."
        jan = B.JanelaBlocoDeNotas.atual()
        if jan is not None:
            atual = jan.ler()
            prefixo = "" if not atual or atual.endswith(("\n", "\r")) else "\n"
            if jan.escrever(prefixo + texto):
                return "Acrescentei o texto no Bloco de Notas aberto."
        # sem janela: no arquivo mais recente da pasta
        recentes = sorted(B.pasta_notas().rglob("*.txt"), key=lambda a: -a.stat().st_mtime)
        if not recentes:
            return "Não consegui acrescentar: não há Bloco de Notas aberto nem nota salva. Use action=write."
        arq = recentes[0]
        with arq.open("a", encoding="utf-8") as f:
            f.write(("\n" if arq.stat().st_size else "") + texto)
        B.abrir_no_editor(arq)
        return f"Não havia Bloco de Notas aberto: acrescentei em {arq.name} e abri."

    if acao == "read":
        jan = B.JanelaBlocoDeNotas.atual()
        conteudo = jan.ler() if jan is not None else ""
        origem = "do Bloco de Notas aberto"
        if not conteudo and titulo:
            arq = _achar_arquivo(titulo)
            if arq:
                conteudo, origem = arq.read_text(encoding="utf-8", errors="replace"), f"de {arq.name}"
        if not conteudo.strip():
            return "O Bloco de Notas está vazio (ou não há nenhum aberto)."
        corte = conteudo[:4000]
        return f"Texto {origem} ({len(conteudo)} caracteres){' — primeiros 4000' if len(conteudo) > 4000 else ''}:\n{corte}"

    if acao == "save":
        jan = B.JanelaBlocoDeNotas.atual()
        conteudo = jan.ler() if jan is not None else ""
        if not conteudo.strip():
            return "Não consegui salvar: não há texto no Bloco de Notas aberto."
        arq = _arquivo_novo(titulo or (conteudo.strip().splitlines()[0][:40] if conteudo.strip() else ""))
        arq.write_text(conteudo.replace("\r\n", "\n"), encoding="utf-8")
        return f"Salvei o texto do Bloco de Notas em {arq}."

    if acao == "notes":
        try:
            from actions.quick_notes import _load
            notas = _load()
        except Exception:
            notas = []
        if not notas:
            return "Você não tem notas rápidas para abrir."
        linhas = [f"Minhas notas — {datetime.now():%d/%m/%Y %H:%M}", ""]
        for n in reversed(notas):
            quando = datetime.fromtimestamp(n.get("at", time.time())).strftime("%d/%m %H:%M")
            linhas.append(f"• {n.get('text', '')}   ({quando})")
        arq = B.pasta_notas() / "Minhas notas.txt"
        arq.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        B.abrir_no_editor(arq)
        return f"Abri suas {len(notas)} nota(s) no Bloco de Notas ({arq.name})."

    if acao == "list":
        arquivos = sorted(B.pasta_notas().rglob("*.txt"), key=lambda a: -a.stat().st_mtime)[:12]
        if not arquivos:
            return f"Ainda não há notas salvas em {B.pasta_notas()}."
        return "Notas mais recentes: " + " | ".join(
            f"{a.stem} ({datetime.fromtimestamp(a.stat().st_mtime):%d/%m %H:%M})" for a in arquivos)

    return "Ação desconhecida. Use open, write, append, read, save, dictate, stop_dictation, notes ou list."


def _abrir_vazio() -> None:
    import subprocess
    import sys
    if sys.platform.startswith("win"):
        subprocess.Popen(["notepad.exe"])
    else:
        arq = _arquivo_novo("")
        arq.write_text("", encoding="utf-8")
        _B().abrir_no_editor(arq)


TOOL = {
    "name": "notepad",
    "description": (
        "Windows Notepad (Bloco de Notas) integration. action=open (empty, or a saved note by title), "
        "write (create a NEW note with the full 'text' you composed and open it in Notepad), "
        "append (add 'text' to the Notepad window that is open), read (get the text of the open "
        "Notepad so you can summarize/correct it), save (save the open Notepad text as a note), "
        "dictate (DICTATION MODE: opens Notepad and types everything the user says from now on — "
        "use when the user says 'escreve o que eu falar', 'modo ditado', 'anota tudo que eu disser'), "
        "stop_dictation, notes (open the quick notes in Notepad), list (saved notes). "
        "Files live in Documents/NEXUS Notas."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING",
                       "description": "open | write | append | read | save | dictate | stop_dictation | notes | list"},
            "text": {"type": "STRING", "description": "Text to write/append (full content for write)"},
            "title": {"type": "STRING", "description": "Optional note title / file name"},
        },
        "required": ["action"],
    },
    "handler": notepad,
}
