"""I.S.A. — Intelligent Systems Architecture: o núcleo de decisões do NEXUS Ultra 2026.

A I.S.A. junta as duas metades do assistente num lugar só:

  🧠 COGNIÇÃO ... o que ele entende e decide (Gemini Live, rede neural local,
                  rotinas, memória)
  ⚙  AUTOMAÇÃO .. o que ele faz no computador (as funções em actions/ e os
                  plugins)

Cada passo vira um EVENTO:
  entrada   o que chegou (voz, texto, barra rápida)
  decisao   quem decidiu e o quê ("Gemini escolheu: Abrir programas")
  acao      uma função começou a rodar
  resultado a função terminou (com o tempo que levou)
  erro      a função falhou
  resposta  o que o NEXUS respondeu
  memoria   algo foi guardado na memória
  sistema   conexão, reconexão, modelo de voz…

O painel I.S.A. (Ctrl+I), o desenho do HUD e a função de voz "isa_core" leem
daqui. Nada sai do computador e nada é gravado em disco: o fluxo vive só na
memória enquanto o NEXUS está aberto.

Uso pelos outros módulos (nunca levanta exceção):
    from core import isa
    isa.registrar("sistema", "Conectado ao Gemini Live", "gemini-2.5-flash…")
    tok = isa.iniciar_acao("open_app", {"app_name": "Spotify"}, origem="gemini")
    ...
    isa.concluir_acao(tok, resultado)
"""
from __future__ import annotations

import json
import threading
import time
from collections import Counter, deque
from typing import Callable

__all__ = ["registrar", "iniciar_acao", "concluir_acao", "eventos", "definir", "status",
           "estatisticas", "em_andamento", "ouvir", "parar_de_ouvir", "limpar", "nome_da_funcao",
           "resumo_texto", "TIPOS", "registrar_latencia"]

TIPOS = {
    "entrada":   ("🗣", "Entrada"),
    "decisao":   ("🧭", "Decisão"),
    "acao":      ("⚙", "Ação"),
    "resultado": ("✔", "Resultado"),
    "erro":      ("✖", "Erro"),
    "resposta":  ("💬", "Resposta"),
    "memoria":   ("🧠", "Memória"),
    "sistema":   ("◈", "Sistema"),
}

_MAX = 500
_trava = threading.RLock()
_eventos: deque[dict] = deque(maxlen=_MAX)
_ouvintes: list[Callable[[dict], None]] = []
_status: dict[str, object] = {}
_contagem: Counter = Counter()
_origens: Counter = Counter()
_tempos: deque[float] = deque(maxlen=200)
_latencias: deque[float] = deque(maxlen=50)   # 1.4 — fim da sua fala → primeira palavra do NEXUS
_andamento: dict[int, dict] = {}
_seq = 0
_inicio = time.time()

# Palavras que indicam falha no texto que uma função devolve
_FALHA = ("Tool '", "Action '", "Failed", "Could not", "Unknown tool", "Não consegui",
          "Erro", "ERR", "Error", "is not available", "blocked", "não está disponível")
# Nunca mostrar o valor destes argumentos
_SEGREDOS = ("password", "senha", "token", "secret", "api_key", "apikey", "key", "chave", "cookie")


# ── nomes amigáveis ─────────────────────────────────────────────────────────

_NOMES_INTERNOS = {
    "save_memory": "Guardar na memória", "recall_memory": "Lembrar da memória",
    "undo": "Desfazer", "screen_process": "Olhar a tela / câmera", "close_camera": "Fechar a câmera",
    "system_status": "Estado do sistema", "manage_monitor": "Monitorar assunto",
    "shutdown_jarvis": "Desligar o NEXUS", "isa_core": "Relatório da I.S.A.", "explicar_ia": "Explicar a IA", "memoria_semanal": "Memória semanal", "conexao": "Internet e modo offline", "criar_rotina": "Criar rotina por conversa", "perfil": "Perfil de uso", "buscar_historico": "Busca no que você fez", "revisao_diaria": "Revisão do dia", "privacidade": "Privacidade",
}


def nome_da_funcao(nome: str) -> str:
    """'open_app' -> 'Abrir programas' (usa a lista em português da F1)."""
    if nome in _NOMES_INTERNOS:
        return _NOMES_INTERNOS[nome]
    try:
        from ui.comandos_pt import COMANDOS
        if nome in COMANDOS:
            return COMANDOS[nome][0]
    except Exception:
        pass
    return nome.replace("_", " ").strip().capitalize()


def _resumo_args(args: dict | None, limite: int = 110) -> str:
    if not args:
        return ""
    limpo = {}
    for k, v in dict(args).items():
        kl = str(k).lower()
        if kl in _SEGREDOS or kl.endswith(("_key", "password", "senha", "token", "secret")):
            limpo[k] = "•••"
        elif isinstance(v, str) and len(v) > 60:
            limpo[k] = v[:57] + "…"
        else:
            limpo[k] = v
    try:
        txt = json.dumps(limpo, ensure_ascii=False, default=str)
    except Exception:
        txt = str(limpo)
    txt = txt.strip("{}")
    return txt if len(txt) <= limite else txt[: limite - 1] + "…"


def _parece_falha(resultado) -> bool:
    txt = str(resultado or "").strip()
    return txt.startswith(_FALHA) or " failed:" in txt[:80]


# ── registro ────────────────────────────────────────────────────────────────

def registrar(tipo: str, titulo: str, detalhe: str = "", origem: str = "",
              ms: float | None = None) -> dict:
    """Anota um evento e avisa quem estiver ouvindo (painel, HUD). Nunca falha."""
    global _seq
    try:
        tipo = tipo if tipo in TIPOS else "sistema"
        agora_ = time.time()
        with _trava:
            _seq += 1
            ev = {
                "id": _seq, "t": agora_, "hora": time.strftime("%H:%M:%S", time.localtime(agora_)),
                "tipo": tipo, "titulo": str(titulo or "").strip()[:160],
                "detalhe": str(detalhe or "").strip()[:240], "origem": str(origem or ""),
                "ms": None if ms is None else int(ms),
            }
            _eventos.append(ev)
            _contagem[tipo] += 1
            if tipo == "decisao" and origem:
                _origens[origem] += 1
            ouvintes = list(_ouvintes)
        for fn in ouvintes:
            try:
                fn(ev)
            except Exception:
                pass
        return ev
    except Exception:
        return {}


def iniciar_acao(nome: str, args: dict | None = None, origem: str = "gemini") -> dict:
    """Uma decisão de usar uma função + o começo da execução."""
    titulo = nome_da_funcao(nome)
    quem = {"gemini": "Gemini", "rede local": "Rede neural local", "rotina": "Rotina",
            "barra rápida": "Barra rápida"}.get(origem, origem.capitalize() or "NEXUS")
    registrar("decisao", f"{quem} escolheu: {titulo}", _resumo_args(args), origem=origem)
    ev = registrar("acao", f"Executando: {titulo}", "", origem=origem)
    tok = {"id": ev.get("id", 0), "nome": nome, "titulo": titulo, "t0": time.perf_counter(),
           "origem": origem}
    with _trava:
        _andamento[tok["id"]] = tok
    return tok


def concluir_acao(tok: dict | None, resultado=None, ok: bool | None = None) -> None:
    if not tok:
        return
    try:
        ms = (time.perf_counter() - tok["t0"]) * 1000
        with _trava:
            _andamento.pop(tok.get("id"), None)
            _tempos.append(ms)
        falhou = _parece_falha(resultado) if ok is None else not ok
        texto = str(resultado or "").replace("\n", " ").strip()
        if falhou:
            registrar("erro", f"{tok['titulo']} falhou", texto[:200], origem=tok.get("origem", ""), ms=ms)
        else:
            registrar("resultado", f"{tok['titulo']} — pronto", texto[:200], origem=tok.get("origem", ""), ms=ms)
    except Exception:
        pass


def registrar_latencia(ms: float) -> None:
    """1.4 — quanto tempo você esperou, do fim da sua fala até o NEXUS começar
    a responder (inclui o tempo das ferramentas que ele chamou no meio)."""
    try:
        ms = float(ms)
    except (TypeError, ValueError):
        return
    if 0 < ms < 60_000:
        with _trava:
            _latencias.append(ms)


def em_andamento() -> int:
    with _trava:
        return len(_andamento)


def eventos(limite: int = 200, tipos: set[str] | None = None) -> list[dict]:
    """Os eventos mais recentes, do mais novo para o mais antigo."""
    with _trava:
        lista = list(_eventos)
    if tipos:
        lista = [e for e in lista if e["tipo"] in tipos]
    return list(reversed(lista[-limite:]))


def limpar() -> None:
    with _trava:
        _eventos.clear()
    registrar("sistema", "Fluxo limpo", "Os contadores continuam.")


# ── estado dos módulos ──────────────────────────────────────────────────────

def definir(chave: str, valor) -> None:
    with _trava:
        _status[chave] = valor


def status(chave: str | None = None, padrao=None):
    with _trava:
        if chave is None:
            return dict(_status)
        return _status.get(chave, padrao)


# ── ouvintes (painel e HUD) ─────────────────────────────────────────────────

def ouvir(fn: Callable[[dict], None]) -> None:
    with _trava:
        if fn not in _ouvintes:
            _ouvintes.append(fn)


def parar_de_ouvir(fn: Callable[[dict], None]) -> None:
    with _trava:
        if fn in _ouvintes:
            _ouvintes.remove(fn)


# ── números ─────────────────────────────────────────────────────────────────

def estatisticas() -> dict:
    with _trava:
        tempos = list(_tempos)
        latencias = list(_latencias)
        cont = dict(_contagem)
        orig = dict(_origens)
        andamento = len(_andamento)
    decisoes = cont.get("decisao", 0)
    locais = orig.get("rede local", 0) + orig.get("rotina", 0)
    return {
        "decisoes": decisoes,
        "acoes_ok": cont.get("resultado", 0),
        "acoes_erro": cont.get("erro", 0),
        "entradas": cont.get("entrada", 0),
        "respostas": cont.get("resposta", 0),
        "tempo_medio_ms": int(sum(tempos) / len(tempos)) if tempos else None,
        "tempo_max_ms": int(max(tempos)) if tempos else None,
        "resposta_media_ms": int(sum(latencias) / len(latencias)) if latencias else None,
        "resposta_ultima_ms": int(latencias[-1]) if latencias else None,
        "respostas_medidas": len(latencias),
        "decisoes_locais": locais,
        "decisoes_gemini": orig.get("gemini", 0),
        "pct_local": (int(round(100 * locais / (locais + orig.get("gemini", 0))))
                      if (locais + orig.get("gemini", 0)) else 0),
        "em_andamento": andamento,
        "ativo_ha_s": int(time.time() - _inicio),
    }


def resumo_texto(n: int = 8) -> str:
    """Texto curto para a função de voz: números + as últimas decisões e ações."""
    s = estatisticas()
    partes = [f"Desde que abri: {s['decisoes']} decisão(ões), {s['acoes_ok']} ação(ões) concluída(s)"
              + (f" e {s['acoes_erro']} com erro" if s["acoes_erro"] else "") + "."]
    if s["decisoes"]:
        partes.append(f"{s['pct_local']}% das decisões foram tomadas aqui no computador "
                      f"(rede neural local ou rotinas), o resto pelo Gemini.")
    if s["tempo_medio_ms"] is not None:
        partes.append(f"Tempo médio das ações: {s['tempo_medio_ms']} ms.")
    if s.get("resposta_media_ms") is not None:
        partes.append(f"Tempo médio de resposta de voz (fim da fala até a primeira palavra): "
                      f"{s['resposta_media_ms']} ms em {s['respostas_medidas']} resposta(s).")
    recentes = [e for e in eventos(60) if e["tipo"] in ("decisao", "resultado", "erro")][:n]
    if recentes:
        partes.append("Últimos passos: " + " | ".join(
            f"{e['hora'][:5]} {e['titulo']}" for e in reversed(recentes)))
    return " ".join(partes)
