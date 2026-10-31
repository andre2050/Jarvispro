"""Perfil de ferramentas (4.5.0): quantas ferramentas o NEXUS apresenta ao Gemini a cada conversa.

Medido na 4.4.0: 123 ferramentas, cerca de 30 mil tokens de declarações em TODA conversa. Isso atrasa a
abertura da sessão e aumenta a chance de o modelo escolher a ferramenta errada. Três perfis:

    completo   (padrão) tudo, como sempre foi
    recentes   as essenciais + as que você usou nos últimos 30 dias + as que você fixou
    essencial  só as essenciais + as que você fixou

Só muda o que é APRESENTADO ao modelo. Nada é apagado, nada deixa de existir: voltar para "completo"
traz tudo de novo. As ferramentas de segurança e de configuração ficam sempre à vista. O perfil vale na
próxima vez que a conversa começar ou reconectar.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

MODOS = ("completo", "recentes", "essencial")
REGISTRO = None   # o registro de ações carregado (definido por assistant/core.py ao iniciar)
DIAS_RECENTES = 30
MINIMO_RECENTES = 12   # com menos que isso, "recentes" ainda não aprendeu nada: mostra tudo

# Sempre à vista em qualquer perfil (declarações fixas + o que é preciso para voltar atrás).
SEMPRE = ("system_status", "screen_process", "close_camera", "manage_monitor", "shutdown_jarvis",
          "save_memory", "recall_memory", "undo", "tool_load", "manage_actions", "nexus_guide",
          "diagnostico", "guardrails", "privacidade", "auditoria", "approvals")

# O dia a dia: abrir, buscar, lembrar, tocar, escrever, conversar com o computador.
ESSENCIAIS = ("open_app", "open_anything", "web_search", "computer_control", "computer_settings",
              "desktop_control", "reminder", "timer_action", "weather_report", "music_control",
              "youtube_video", "send_message", "notepad", "quick_notes", "tarefas", "compras",
              "file_controller", "browser_control", "morning_briefing", "email_reader",
              "agenda_google", "focus_mode", "memory_bank", "routines", "conversation_threads",
              "daily_planner")


def declaracoes_fixas() -> list:
    """As declarações fixas do assistente, lidas direto do arquivo (sem carregar áudio, Qt nem Gemini)."""
    import importlib.util
    arq = Path(__file__).resolve().parent.parent / "assistant" / "tool_declarations.py"
    spec = importlib.util.spec_from_file_location("nexus_tool_declarations", arq)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return list(m.TOOL_DECLARATIONS)


def _nome(d) -> str:
    return str(d.get("name") if isinstance(d, dict) else getattr(d, "name", "") or "")


def modo_atual() -> str:
    try:
        from core import preferences as P
        m = str(P.get("carga_ferramentas") or "completo")
    except Exception:
        m = "completo"
    return m if m in MODOS else "completo"


def fixas() -> list[str]:
    try:
        from core import preferences as P
        v = P.get("ferramentas_fixas") or []
        return [str(x) for x in v if isinstance(x, str)][:60]
    except Exception:
        return []


def usadas_recentemente(dias: int = DIAS_RECENTES, agora: datetime | None = None, entradas=None) -> set[str]:
    """Nomes de ferramentas que apareceram no registro de auditoria nos últimos `dias` dias."""
    if entradas is None:
        try:
            from core import audit
            entradas = audit.ler()
        except Exception:
            entradas = []
    corte = (agora or datetime.now()) - timedelta(days=dias)
    saida: set[str] = set()
    for e in entradas:
        try:
            quando = datetime.strptime(str(e.get("ts")), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if quando >= corte and e.get("tool"):
            saida.add(str(e["tool"]))
    return saida


def nomes_visiveis(nomes, modo: str | None = None, usadas=None, fixadas=None) -> set[str]:
    """Quais dos `nomes` ficam à vista no perfil `modo`."""
    modo = modo or modo_atual()
    nomes = set(nomes)
    if modo == "completo":
        return nomes
    base = set(SEMPRE) | set(ESSENCIAIS) | set(fixas() if fixadas is None else fixadas)
    if modo == "recentes":
        base |= set(usadas_recentemente() if usadas is None else usadas)
    visiveis = nomes & base
    if modo == "recentes" and len(visiveis) < MINIMO_RECENTES:
        return nomes
    return visiveis


def filtrar(decls: list, modo: str | None = None, usadas=None, fixadas=None) -> list:
    """As declarações que o modelo vai ver. Mantém a ordem original."""
    modo = modo or modo_atual()
    if modo == "completo":
        return list(decls)
    ver = nomes_visiveis([_nome(d) for d in decls], modo, usadas, fixadas)
    return [d for d in decls if _nome(d) in ver]


def resumo(decls: list, modo: str | None = None, usadas=None, fixadas=None) -> dict:
    """Números para mostrar ao usuário: quantas ferramentas, quanto pesam, quais ficam de fora."""
    import json
    modo = modo or modo_atual()
    ver = filtrar(decls, modo, usadas, fixadas)
    nomes_ver = {_nome(d) for d in ver}
    peso = lambda lista: len(json.dumps(lista, default=str)) // 4   # noqa: E731  (~4 caracteres por token)
    return {"modo": modo, "total": len(decls), "visiveis": len(ver), "tokens_total": peso(decls),
            "tokens_visiveis": peso(ver), "ocultas": sorted(_nome(d) for d in decls if _nome(d) not in nomes_ver)}


def aviso_para_o_modelo(modo: str | None = None) -> str:
    """Uma linha para o prompt: o modelo precisa saber que nem tudo está à vista, para não prometer o que não vê."""
    modo = modo or modo_atual()
    if modo == "completo":
        return ""
    return ("[FERRAMENTAS] Perfil reduzido: só parte das ferramentas está disponível nesta conversa. Se o usuário pedir "
            "algo que nenhuma ferramenta sua faz, diga que a ferramenta está desligada neste perfil e ofereça trocar "
            "para o perfil completo com tool_load.")
