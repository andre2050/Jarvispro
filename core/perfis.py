"""Perfis de uso (NEXUS Ultra 2026 3.3): Trabalho, Estudo, Jogo — e o Normal.

Cada perfil muda quatro coisas, e só elas:
  • TOM            uma instrução curta de estilo que entra no prompt (no motor próprio vale já no próximo
                   pedido; no Gemini Live vale na próxima conexão);
  • PROATIVIDADE   se o NEXUS puxa conversa sozinho (nos três perfis ele fica quieto);
  • LEMBRETE DE ÁGUA  silenciado no Jogo;
  • FERRAMENTAS    algumas ficam desativadas (ex.: vídeos no Trabalho e no Estudo), com um aviso claro
                   de que é o perfil — e é só dizer "volta pro perfil normal" para liberar.

Nada de segurança muda de perfil para perfil: as travas do atuador, as confirmações e as permissões são
sempre as mesmas. O perfil ativo fica em memory/perfil.json e sobrevive ao reinício.
"""
from __future__ import annotations

import json
import threading
import time
import unicodedata
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent.parent / "memory" / "perfil.json"

PERFIS: dict[str, dict] = {
    "normal": {
        "nome": "Normal", "descricao": "Tudo liberado, do jeito de sempre.",
        "tom": "", "proativo": True, "agua": True, "bloqueadas": (),
    },
    "trabalho": {
        "nome": "Trabalho", "descricao": "Direto e sem conversa fiada; sem vídeos para não distrair.",
        "tom": "Seja objetivo e direto: respostas curtas, sem conversa fiada, sem piadas, sem puxar assunto.",
        "proativo": False, "agua": True,
        "bloqueadas": ("youtube_video", "video_player", "game_updater"),
    },
    "estudo": {
        "nome": "Estudo", "descricao": "Didático e paciente; sem vídeos nem jogos para manter o foco.",
        "tom": ("Seja paciente e didático: explique passo a passo, com um exemplo simples, e confira se ficou "
                "claro. Não puxe assunto fora do estudo."),
        "proativo": False, "agua": True,
        "bloqueadas": ("youtube_video", "video_player", "game_updater"),
    },
    "jogo": {
        "nome": "Jogo", "descricao": "Quieto e breve; não interrompe nem atualiza nada no meio da partida.",
        "tom": "Seja animado e muito breve: no máximo uma frase por resposta. Nunca interrompa por iniciativa própria.",
        "proativo": False, "agua": False,
        "bloqueadas": ("system_update", "dev_agent", "manutencao_pc"),
    },
}
_ALIAS = {
    "normal": "normal", "padrao": "normal", "comum": "normal", "nenhum": "normal", "sair": "normal",
    "trabalho": "trabalho", "trabalhar": "trabalho", "work": "trabalho", "foco": "trabalho",
    "estudo": "estudo", "estudar": "estudo", "study": "estudo", "prova": "estudo",
    "jogo": "jogo", "jogar": "jogo", "game": "jogo", "gamer": "jogo", "gaming": "jogo",
}

_trava = threading.RLock()
_cache: dict = {"nome": None, "lido_em": 0.0}


def _sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(t or "").lower()) if unicodedata.category(c) != "Mn")


def resolver(texto: str | None) -> str | None:
    """'modo jogo' / 'vou estudar' → 'jogo' / 'estudo'. None = não é um perfil conhecido."""
    t = _sem_acento(texto).strip()
    if not t:
        return None
    if t in _ALIAS:
        return _ALIAS[t]
    for chave in sorted(_ALIAS, key=len, reverse=True):
        if chave in t:
            return _ALIAS[chave]
    return None


def ativo(arquivo: Path | None = None) -> str:
    """O perfil em uso ('normal' se nunca escolheu). Lê o disco no máximo a cada 2 segundos."""
    try:
        agora = time.monotonic()
        with _trava:
            if arquivo is None and _cache["nome"] and agora - _cache["lido_em"] < 2.0:
                return _cache["nome"]
        nome = "normal"
        try:
            d = json.loads((arquivo or ARQUIVO).read_text(encoding="utf-8"))
            if d.get("ativo") in PERFIS:
                nome = d["ativo"]
        except Exception:
            pass
        if arquivo is None:
            with _trava:
                _cache.update(nome=nome, lido_em=agora)
        return nome
    except Exception:
        return "normal"


def definir(nome: str, arquivo: Path | None = None) -> str:
    """Troca o perfil. Devolve o texto para o NEXUS dizer."""
    chave = resolver(nome)
    if chave is None:
        return "[failed] Não conheço esse perfil. Os perfis são: " + ", ".join(p["nome"] for p in PERFIS.values()) + "."
    arq = arquivo or ARQUIVO
    try:
        arq.parent.mkdir(parents=True, exist_ok=True)
        tmp = arq.with_suffix(".tmp")
        tmp.write_text(json.dumps({"ativo": chave, "desde": int(time.time())}), encoding="utf-8")
        tmp.replace(arq)
    except Exception as e:
        return f"[failed] Não consegui guardar o perfil: {e}"
    with _trava:
        _cache.update(nome=chave if arquivo is None else _cache["nome"], lido_em=time.monotonic())
    try:
        from core import isa
        isa.definir("perfil", PERFIS[chave]["nome"])
    except Exception:
        pass
    p = PERFIS[chave]
    extra = ""
    if p["bloqueadas"]:
        extra = " Ficam desativadas: " + ", ".join(p["bloqueadas"]) + "."
    return f"Perfil {p['nome']} ligado. {p['descricao']}{extra}"


# ── o que cada parte do NEXUS consulta ──────────────────────────────────────
def bloqueada(ferramenta: str, perfil: str | None = None) -> str | None:
    """A mensagem para a ferramenta desativada pelo perfil; None = liberada."""
    chave = perfil or ativo()
    p = PERFIS.get(chave)
    if p and ferramenta in p["bloqueadas"]:
        return (f"[failed] O perfil {p['nome']} está ligado e desativa '{ferramenta}'. Diga isso ao usuário em "
                "uma frase e ofereça voltar ao perfil normal se ele quiser usar.")
    return None


def silencia_proativo(perfil: str | None = None) -> bool:
    return not PERFIS.get(perfil or ativo(), PERFIS["normal"])["proativo"]


def silencia_agua(perfil: str | None = None) -> bool:
    return not PERFIS.get(perfil or ativo(), PERFIS["normal"])["agua"]


def bloco_prompt(perfil: str | None = None) -> str:
    chave = perfil or ativo()
    p = PERFIS.get(chave)
    if not p or not p["tom"]:
        return ""
    return f"[PERFIL: {p['nome'].upper()}]\n{p['tom']}\n"


def listar() -> str:
    return "; ".join(f"{p['nome']}: {p['descricao']}" for p in PERFIS.values())


def texto_estado(perfil: str | None = None) -> str:
    p = PERFIS[perfil or ativo()]
    return f"O perfil ligado é {p['nome']}. {p['descricao']}"
