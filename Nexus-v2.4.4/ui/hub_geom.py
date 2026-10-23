"""Geometria do visual "HUB" (sem Qt, para poder ser testada): módulos em órbita e pacotes de dados."""
from __future__ import annotations

import math

# (rótulo, funções do NEXUS que acendem esse módulo)
MODULOS = (
    ("SISTEMA", {"system_status", "system_monitor", "manutencao_pc", "anomalia_pc", "computer_settings", "open_app",
                 "desktop", "file_controller", "computer_control", "shortcut_manager", "diagnostico", "focus_mode"}),
    ("MEMÓRIA", {"save_memory", "recall_memory", "memoria_semantica", "memory_bank", "quick_notes", "notepad", "diario",
                 "contatos", "tarefas", "projetos", "reminder", "daily_planner", "rastreador_habitos", "previsao_habitos"}),
    ("WEB", {"web_search", "browser_control", "weather_report", "noticias", "flight_finder", "mapas", "email_checker",
             "email_reader", "send_message", "game_updater"}),
    ("VISÃO", {"screen_process", "visao_ia", "local_vision", "computer_vision"}),
    ("FINANÇAS", {"simple_finance", "financas_ia", "price_alert", "compras"}),
    ("MÍDIA", {"music_control", "video_player", "youtube_video", "casa_inteligente", "voz_treino"}),
)


def modulo_da_funcao(nome: str) -> int | None:
    """Índice do módulo que a função acende (None = só o núcleo)."""
    for i, (_, funcoes) in enumerate(MODULOS):
        if nome in funcoes:
            return i
    return None


def posicoes(cx: float, cy: float, raio: float, rot: float, n: int = len(MODULOS)) -> list[tuple[float, float]]:
    """Posição dos n módulos num círculo de `raio`, girado em `rot` radianos (começa no alto)."""
    return [(cx + raio * math.cos(rot - math.pi / 2 + i * 2 * math.pi / n),
             cy + raio * math.sin(rot - math.pi / 2 + i * 2 * math.pi / n)) for i in range(n)]


def pacotes(fase: float, estado: str, falando: bool, n: int = len(MODULOS), por_ligacao: int = 2) -> list[tuple[int, float]]:
    """[(ligação, t)] com t em 0..1 do núcleo (0) ao módulo (1). Falando = saem do núcleo; ouvindo = entram;
    pensando = vão e voltam rápido; parado = deriva devagar."""
    out = []
    vel = {"THINKING": 1.6, "PROCESSING": 1.6}.get(estado, 0.9 if (falando or estado == "LISTENING") else 0.25)
    for i in range(n):
        for k in range(por_ligacao):
            t = (fase * vel * 0.5 + i * 0.17 + k / por_ligacao) % 1.0
            if estado == "LISTENING" and not falando:
                t = 1.0 - t                                         # entrando no núcleo
            elif estado in ("THINKING", "PROCESSING"):
                t = 1.0 - abs(2.0 * t - 1.0)                       # vai e volta
            out.append((i, t))
    return out
