"""
core/tema_auto.py — tema que acompanha o seu dia e o seu humor (NEXUS Ultra 2026 3.5).

Modos (config "tema_auto" › modo):
  desligado  a cor é a que você escolheu em Skin/Personalizar (padrão)
  horario    madrugada violeta, manhã azul claro, tarde o azul-violeta Ultra, noite violeta quente
  humor      segue a média do seu humor no diário nos últimos 3 dias (1 a 5): baixo → verde-água calmo,
             alto → rosa quente; sem humor anotado, não muda nada
  ambos      a cor do horário, puxada um pouco para a cor do humor

O que a pessoa escolheu NUNCA é apagado: ao desligar o modo automático, a cor dela volta. Só aparência;
o humor vem do diário (memory/diario.json), que fica só no seu PC.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

NS = "tema_auto"
MODOS = ("desligado", "horario", "humor", "ambos")
_BASE = Path(__file__).resolve().parent.parent
ARQ_DIARIO = _BASE / "memory" / "diario.json"

# (hora_inicial, nome, cor) — a faixa vale até a próxima hora inicial
FAIXAS = (
    (0, "madrugada", "#8a7bff"),
    (6, "manhã", "#4fb8ff"),
    (12, "tarde", "#7b8cff"),      # o próprio azul-violeta do Ultra 2026
    (18, "noite", "#b57bff"),
)
COR_HUMOR_BAIXO = "#4fd1c0"        # verde-água: calmo
COR_HUMOR_ALTO = "#ff8fb1"         # rosa quente: animado
JANELA_HUMOR_DIAS = 3
PESO_HUMOR_EM_AMBOS = 0.4


def _mix(c1: str, c2: str, t: float) -> str:
    a, b = c1.lstrip("#"), c2.lstrip("#")
    return "#" + "".join(f"{int(int(a[i:i+2], 16) + (int(b[i:i+2], 16) - int(a[i:i+2], 16)) * t + 0.5):02x}" for i in (0, 2, 4))


def faixa_do_horario(hora: int) -> tuple[str, str]:
    """(nome, cor) da faixa do dia para essa hora (0-23)."""
    nome, cor = FAIXAS[0][1], FAIXAS[0][2]
    for inicio, n, c in FAIXAS:
        if hora % 24 >= inicio:
            nome, cor = n, c
    return nome, cor


def humor_recente(agora: datetime | None = None, arq: Path | None = None) -> float | None:
    """Média do humor (1-5) dos últimos dias no diário, ou None se não houver nenhum."""
    agora = agora or datetime.now()
    limite = agora.replace(tzinfo=None) - timedelta(days=JANELA_HUMOR_DIAS)
    try:
        itens = json.loads(Path(arq or ARQ_DIARIO).read_text(encoding="utf-8"))
    except Exception:
        return None
    notas = []
    for e in itens if isinstance(itens, list) else []:
        try:
            h = e.get("humor")
            q = datetime.fromisoformat(str(e.get("quando"))).replace(tzinfo=None)
            if h is not None and 1 <= int(h) <= 5 and q >= limite:
                notas.append(int(h))
        except Exception:
            continue
    return sum(notas) / len(notas) if notas else None


def cor_do_humor(media: float) -> str:
    """Do verde-água (humor 1) ao rosa (humor 5), passando pelo azul-violeta neutro no meio (3)."""
    neutro = FAIXAS[2][2]
    if media <= 3:
        return _mix(COR_HUMOR_BAIXO, neutro, (max(media, 1) - 1) / 2)
    return _mix(neutro, COR_HUMOR_ALTO, (min(media, 5) - 3) / 2)


def cor_do_momento(modo: str, agora: datetime | None = None, media_humor: float | None = None) -> str | None:
    """A cor de acento para este momento, ou None quando o modo não manda mudar nada."""
    agora = agora or datetime.now()
    if modo == "horario":
        return faixa_do_horario(agora.hour)[1]
    if modo == "humor":
        return cor_do_humor(media_humor) if media_humor is not None else None
    if modo == "ambos":
        base = faixa_do_horario(agora.hour)[1]
        return _mix(base, cor_do_humor(media_humor), PESO_HUMOR_EM_AMBOS) if media_humor is not None else base
    return None


# ── configuração (guardada junto das outras, em config/api_keys.json) ────────
def modo_atual() -> str:
    try:
        from memory.config_manager import get_plugin_setting
        m = str(get_plugin_setting(NS, "modo", "desligado")).lower()
    except Exception:
        return "desligado"
    return m if m in MODOS else "desligado"


def definir_modo(modo: str) -> None:
    from memory.config_manager import save_plugin_config
    save_plugin_config(NS, {"modo": modo})


def cor_agora(modo: str | None = None, agora: datetime | None = None) -> str | None:
    """Atalho para a interface: a cor do modo salvo (ou do `modo` dado) agora."""
    modo = modo or modo_atual()
    if modo == "desligado":
        return None
    media = humor_recente(agora) if modo in ("humor", "ambos") else None
    return cor_do_momento(modo, agora, media)
