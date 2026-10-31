"""Perfil de ferramentas (4.5.0): quantas ferramentas o NEXUS apresenta ao Gemini a cada conversa.

Medido na 4.4.0: 123 ferramentas, cerca de 30 mil tokens de declarações em TODA conversa. Isso atrasa a
abertura da sessão e aumenta a chance de o modelo escolher a ferramenta errada. Três perfis:

    completo   (padrão) tudo, como sempre foi
    recentes   as essenciais + as que você usou nos últimos 30 dias + as que você fixou
    essencial  só as essenciais + as que você fixou
    dinamico   (4.6.0) como "recentes", mais duas ferramentas de busca: a IA procura o que precisa
               (tool_search) e chama (tool_call). Alcança TUDO sem carregar tudo

Só muda o que é APRESENTADO ao modelo. Nada é apagado, nada deixa de existir: voltar para "completo"
traz tudo de novo. As ferramentas de segurança e de configuração ficam sempre à vista. O perfil vale na
próxima vez que a conversa começar ou reconectar.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

MODOS = ("completo", "recentes", "essencial", "dinamico")
NOME_BUSCA, NOME_CHAMADA = "tool_search", "tool_call"
TODAS: list = []   # todas as declarações (antes do filtro), definido por assistant/session.py a cada conexão
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


def declaracoes_gateway() -> list[dict]:
    """As duas ferramentas do perfil dinâmico. `tool_call` roda pelo MESMO caminho de qualquer ferramenta
    (guardrails, confirmações, auditoria, I.S.A.): ela só troca o nome pelo da ferramenta escolhida."""
    return [
        {"name": NOME_BUSCA,
         "description": ("Finds NEXUS tools that are not in your list. Use it whenever the user asks for something none of your listed tools does "
                         "(a different app, a rarer feature). Describe what you need in a few words, in any language; it returns the best matches "
                         "with their parameters. Then run one with tool_call."),
         "parameters": {"type": "OBJECT", "properties": {"query": {"type": "STRING", "description": "What you need, e.g. 'print a file', 'study flashcards'"}},
                        "required": ["query"]}},
        {"name": NOME_CHAMADA,
         "description": "Runs a tool found with tool_search. name = the exact tool name; args = its parameters as an object.",
         "parameters": {"type": "OBJECT", "properties": {"name": {"type": "STRING"}, "args": {"type": "OBJECT"}}, "required": ["name"]}},
    ]


def _texto_de(d) -> str:
    desc = d.get("description", "") if isinstance(d, dict) else getattr(d, "description", "")
    return f"{_nome(d).replace('_', ' ')} {desc}"


def _norm(t: str) -> str:
    import re
    import unicodedata
    t = unicodedata.normalize("NFD", str(t).lower())
    return re.sub(r"[^a-z0-9 ]+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn"))


def _parametros(d) -> str:
    params = (d.get("parameters") if isinstance(d, dict) else getattr(d, "parameters", None)) or {}
    props = params.get("properties", {}) if isinstance(params, dict) else {}
    obrig = set(params.get("required", [])) if isinstance(params, dict) else set()
    partes = []
    for nome, esp in list(props.items())[:12]:
        tipo = str((esp or {}).get("type", "")).lower() if isinstance(esp, dict) else ""
        enum = (esp or {}).get("enum") if isinstance(esp, dict) else None
        partes.append(f"{nome}{'*' if nome in obrig else ''}" + (f" ({'|'.join(map(str, enum[:8]))})" if enum else (f" ({tipo})" if tipo else "")))
    return ", ".join(partes) or "sem parâmetros"


def buscar(decls: list, consulta: str, maximo: int = 5) -> str:
    """Texto com as ferramentas que melhor combinam com `consulta` (nome, descrição). Fora as duas do gateway."""
    palavras = {w for w in _norm(consulta).split() if len(w) > 2}
    if not palavras:
        return "Diga o que você precisa, em poucas palavras."
    pontos = []
    for d in decls:
        nome = _nome(d)
        if nome in (NOME_BUSCA, NOME_CHAMADA):
            continue
        alvo = set(_norm(_texto_de(d)).split())
        nota = sum(2.0 if w in alvo else 0.0 for w in palavras)
        nota += sum(0.8 for w in palavras for a in alvo if len(w) > 4 and a != w and (a.startswith(w[:5]) or w.startswith(a[:5])) and len(a) > 4)
        nota += 3.0 if any(w in _norm(nome.replace("_", " ")).split() for w in palavras) else 0.0
        if nota > 0:
            pontos.append((nota, nome, d))
    if not pontos:
        return "Não achei nenhuma ferramenta para isso."
    pontos.sort(key=lambda x: (-x[0], x[1]))
    linhas = []
    for _, nome, d in pontos[:maximo]:
        desc = (d.get("description", "") if isinstance(d, dict) else getattr(d, "description", ""))
        linhas.append(f"- {nome}: {str(desc).strip()[:180]} | parâmetros: {_parametros(d)}")
    return "Ferramentas encontradas (use tool_call com name e args):\n" + "\n".join(linhas)


def resolver_chamada(args: dict, validos) -> tuple[str, dict, str]:
    """(nome, argumentos, erro) do `tool_call`. `validos` = nomes que existem (ações e plugins carregados)."""
    import json
    nome = str((args or {}).get("name") or "").strip()
    if not nome:
        return "", {}, "Diga o nome da ferramenta (veja tool_search)."
    if nome in (NOME_BUSCA, NOME_CHAMADA):
        return "", {}, "Isso não se chama de dentro de tool_call."
    if nome not in validos:
        return "", {}, f"A ferramenta “{nome[:40]}” não existe ou está desativada. Use tool_search."
    ar = (args or {}).get("args") or {}
    if isinstance(ar, str):
        try:
            ar = json.loads(ar)
        except ValueError:
            return "", {}, "args precisa ser um objeto."
    if not isinstance(ar, dict):
        return "", {}, "args precisa ser um objeto."
    return nome, dict(ar), ""


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
    if modo in ("recentes", "dinamico"):
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
    saida = [d for d in decls if _nome(d) in ver]
    if modo == "dinamico":
        saida += [g for g in declaracoes_gateway() if _nome(g) not in {_nome(d) for d in saida}]
    return saida


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
    if modo == "dinamico":
        return ("[FERRAMENTAS] Perfil dinâmico: você vê só as ferramentas mais comuns. Existem muitas outras. Quando o pedido não "
                "couber nas que você vê, chame tool_search descrevendo o que precisa e depois tool_call com o nome e os argumentos. "
                "Nunca diga que não sabe fazer algo sem antes procurar com tool_search.")
    return ("[FERRAMENTAS] Perfil reduzido: só parte das ferramentas está disponível nesta conversa. Se o usuário pedir "
            "algo que nenhuma ferramenta sua faz, diga que a ferramenta está desligada neste perfil e ofereça trocar "
            "para o perfil completo com tool_load.")
