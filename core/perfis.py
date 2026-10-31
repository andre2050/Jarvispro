"""Perfis de uso (NEXUS Ultra 2026 3.3): Trabalho, Estudo, Jogo — e o Normal.

3.7 — ambientes: cada perfil também pode trazer a sua COR da interface, o seu VISUAL do hub e silenciar os avisos
no celular (push). Ao sair do Normal o NEXUS lembra a cor e o visual que você usava e devolve quando você volta.

Cada perfil muda quatro coisas (mais o visual do ambiente), e só elas:
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
from core.protecao import engolida as _engolida

ARQUIVO = Path(__file__).resolve().parent.parent / "memory" / "perfil.json"

PERFIS: dict[str, dict] = {
    "normal": {
        "nome": "Normal", "descricao": "Tudo liberado, do jeito de sempre.",
        "tom": "", "proativo": True, "agua": True, "bloqueadas": (),
    },
    "casa": {
        "nome": "Casa", "descricao": "Descontraído e caloroso; tudo liberado, visual aconchegante.",
        "tom": "Seja caloroso e descontraído, como alguém em casa com o usuário; pode puxar assunto leve.",
        "proativo": True, "agua": True, "bloqueadas": (),
        "cor": "#ff9f6b", "hub": "lotus", "silencia": (),
    },
    "trabalho": {
        "nome": "Trabalho", "descricao": "Direto e sem conversa fiada; sem vídeos para não distrair.",
        "tom": "Seja objetivo e direto: respostas curtas, sem conversa fiada, sem piadas, sem puxar assunto.",
        "proativo": False, "agua": True,
        "bloqueadas": ("youtube_video", "video_player", "game_updater"),
        "cor": "#5aa9ff", "hub": "gears", "silencia": ("push",),
    },
    "estudo": {
        "nome": "Estudo", "descricao": "Didático e paciente; sem vídeos nem jogos para manter o foco.",
        "tom": ("Seja paciente e didático: explique passo a passo, com um exemplo simples, e confira se ficou "
                "claro. Não puxe assunto fora do estudo."),
        "proativo": False, "agua": True,
        "bloqueadas": ("youtube_video", "video_player", "game_updater"),
        "cor": "#34e0a1", "hub": "origami", "silencia": ("push",),
    },
    "jogo": {
        "nome": "Jogo", "descricao": "Quieto e breve; não interrompe nem atualiza nada no meio da partida.",
        "tom": "Seja animado e muito breve: no máximo uma frase por resposta. Nunca interrompa por iniciativa própria.",
        "proativo": False, "agua": False,
        "bloqueadas": ("system_update", "dev_agent", "manutencao_pc"),
        "cor": "#ff4fd8", "hub": "synthwave", "silencia": ("push",),
    },
}
_ALIAS = {
    "casa": "casa", "home": "casa", "descansar": "casa", "relaxar": "casa",
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
            _engolida("core/perfis.py:103")
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
        antes = {}
        try:
            antes = json.loads(arq.read_text(encoding="utf-8")).get("antes", {})
        except Exception:
            _engolida("core/perfis.py:124")
        dados = {"ativo": chave, "desde": int(time.time())}
        if arquivo is None:
            antes = _aplicar_ambiente(chave, antes)
        if antes:
            dados["antes"] = antes
        tmp = arq.with_suffix(".tmp")
        tmp.write_text(json.dumps(dados), encoding="utf-8")
        tmp.replace(arq)
    except Exception as e:
        return f"[failed] Não consegui guardar o perfil: {e}"
    with _trava:
        _cache.update(nome=chave if arquivo is None else _cache["nome"], lido_em=time.monotonic())
    try:
        from core import isa
        isa.definir("perfil", PERFIS[chave]["nome"])
    except Exception:
        _engolida("core/perfis.py:141")
    p = PERFIS[chave]
    extra = ""
    if p["bloqueadas"]:
        extra = " Ficam desativadas: " + ", ".join(p["bloqueadas"]) + "."
    if p.get("silencia"):
        extra += " Sem avisos no celular."
    return f"Perfil {p['nome']} ligado. {p['descricao']}{extra}"


_ouvintes: list = []


def ao_mudar(cb) -> None:
    """A interface se registra aqui para aplicar cor e visual ao vivo quando o perfil troca."""
    _ouvintes.append(cb)


def _aplicar_ambiente(chave: str, antes: dict) -> dict:
    """Grava cor/visual do ambiente na configuração; guarda os seus de antes para devolver no Normal."""
    try:
        from memory.config_manager import _save_flag, get_hud_style, load_api_keys
        p = PERFIS[chave]
        cfg = load_api_keys()
        if p.get("cor") or p.get("hub"):
            if not antes:                                    # primeira saída do Normal: lembra o que era seu
                antes = {"ui_color": cfg.get("ui_color", ""), "hud_style": get_hud_style()}
            if p.get("cor"):
                _save_flag("ui_color", p["cor"])
            if p.get("hub"):
                _save_flag("hud_style", p["hub"])
        elif antes:                                          # voltou ao Normal: devolve
            _save_flag("ui_color", antes.get("ui_color", ""))
            _save_flag("hud_style", antes.get("hud_style", "orb"))
            antes = {}
        for cb in list(_ouvintes):
            try:
                cb()
            except Exception:
                _engolida("core/perfis.py:180")
    except Exception:
        _engolida("core/perfis.py:182")
    return antes


def silencia_integracao(nome: str, perfil: str | None = None) -> bool:
    """True se o perfil ligado pede silêncio nessa integração (hoje: 'push')."""
    return nome in PERFIS.get(perfil or ativo(), PERFIS["normal"]).get("silencia", ())


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
