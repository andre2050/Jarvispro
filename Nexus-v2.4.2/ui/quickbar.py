"""Catálogo da barra de acesso rápido e dos atalhos de teclado (NEXUS Pro 1.2).

Tudo o que o usuário escolhe fica nas preferências (config/api_keys.json):
  quick_bar       lista com os ids dos botões, na ordem da barra
  quick_commands  comandos rápidos criados por ele: [{"label", "command"}]
  shortcut_*      a tecla de cada atalho
"""
from __future__ import annotations

# id -> (ícone, nome, método da MainWindow, explicação)
FERRAMENTAS: dict[str, tuple[str, str, str, str]] = {
    "agenda":     ("📝", "Notas e lembretes", "_open_agenda", "Ver, criar e apagar notas e lembretes"),
    "produtiv":   ("🎯", "Produtividade", "_open_produtividade",
                   "Tarefas, foco (Pomodoro) e projetos num lugar só"),
    "ditado":     ("🎙", "Ditado", "_toggle_ditado",
                   "Abre o Bloco de Notas e escreve tudo o que você falar (de novo para parar)"),
    "isa":        ("🧠", "I.S.A.", "_open_isa_panel", "Núcleo I.S.A.: o que o NEXUS pensou, decidiu e fez"),
    "organizar":  ("🗂", "Organizar", "_organizar_area_de_trabalho",
                   "Guarda os arquivos soltos da área de trabalho em pastas por tipo"),
    "comandos":   ("📖", "Comandos", "_open_commands_panel", "Tudo o que você pode pedir por voz"),
    "area":       ("📋", "Área de transferência", "_open_clip_panel", "O que você copiou recentemente"),
    "visao":      ("👁", "Visão", "_open_vision_panel", "Tela e câmera"),
    "sistema":    ("📊", "Sistema", "_open_intel_panel", "Programas abertos e uso do computador"),
    "memoria":    ("🧠", "Memória", "_open_memory_panel", "O que o NEXUS lembra sobre você"),
    "plugins":    ("🧩", "Plugins", "_open_plugin_manager", "Ligar e desligar plugins"),
    "audio":      ("🎧", "Áudio", "_open_audio_devices", "Microfone e alto-falante"),
    "celular":    ("📱", "Celular", "_open_remote", "Controlar o NEXUS pelo celular"),
    "atividades": ("🧾", "Atividades", "_open_activity_log", "Tudo o que aconteceu hoje"),
    "config":     ("⚙", "Configurações", "_open_settings_panel", "Todas as configurações"),
    "usuario":    ("👤", "Meu perfil", "_open_preferences", "Nome, voz, cores e preferências"),
    "telacheia":  ("⛶", "Tela cheia", "_toggle_fullscreen", "Entrar ou sair da tela cheia"),
    "hud":        ("✨", "Trocar visual", "_toggle_hud_style", "Escolher o visual do hub (6 modelos)"),
    "atalhos":    ("⌨", "Atalhos", "_open_shortcuts_panel", "Personalizar as teclas de atalho"),
}

PADRAO_BARRA = ["produtiv", "agenda", "ditado", "isa", "comandos", "area", "visao", "sistema", "config"]
# Barras padrão das versões anteriores: quem nunca mexeu na barra ganha os
# botões novos sozinho; quem personalizou fica com a barra que montou.
_PADROES_ANTIGOS = (
    ["agenda", "ditado", "isa", "comandos", "area", "visao", "sistema", "config"],   # 1.5
    ["agenda", "isa", "comandos", "area", "visao", "sistema", "config"],   # 1.3
    ["agenda", "comandos", "area", "visao", "sistema", "config"],          # 1.2
)

# Exemplos que aparecem no editor (não entram sozinhos na barra)
EXEMPLOS_COMANDOS = [
    {"label": "Bom dia", "command": "me dá o briefing do dia"},
    {"label": "Modo trabalho", "command": "ativar modo trabalho"},
    {"label": "Foco 25 min", "command": "me dá 25 minutos de foco"},
]

# (chave da preferência, o que faz, tecla padrão, método da MainWindow)
ATALHOS: list[tuple[str, str, str, str]] = [
    ("shortcut_mute", "Ligar / desligar o microfone", "F4", "_toggle_mute"),
    ("shortcut_interrupt", "Interromper a fala", "Escape", "_do_interrupt"),
    ("shortcut_fullscreen", "Tela cheia", "F11", "_toggle_fullscreen"),
    ("shortcut_command", "Ir para a caixa de comando", "Ctrl+L", "_focus_command"),
    ("shortcut_agenda", "Notas e lembretes", "Ctrl+N", "_open_agenda"),
    ("shortcut_produtiv", "Produtividade (tarefas e foco)", "Ctrl+P", "_open_produtividade"),
    ("shortcut_isa", "Núcleo I.S.A.", "Ctrl+I", "_open_isa_panel"),
    ("shortcut_ditado", "Ditado no Bloco de Notas (ligar / parar)", "Ctrl+D", "_toggle_ditado"),
    ("shortcut_commands", "Lista de comandos de voz", "F1", "_open_commands_panel"),
    ("shortcut_settings", "Configurações", "Ctrl+,", "_open_settings_panel"),
    ("shortcut_clipboard", "Área de transferência", "Ctrl+Shift+V", "_open_clip_panel"),
    ("shortcut_activity", "Log de atividades", "Ctrl+Shift+L", "_open_activity_log"),
    ("shortcut_quickbar", "Personalizar a barra rápida", "Ctrl+B", "_open_quickbar_editor"),
    ("shortcut_clear_chat", "Limpar a conversa da tela", "Ctrl+Shift+K", "_clear_chat_view"),
]

DEFAULTS = {chave: tecla for chave, _o, tecla, _m in ATALHOS}


def _prefs():
    from core import preferences as P
    return P


def barra_atual() -> list[str]:
    try:
        ids = _prefs().get("quick_bar")
    except Exception:
        ids = None
    if not isinstance(ids, list) or ids in _PADROES_ANTIGOS:
        return list(PADRAO_BARRA)
    return [i for i in ids if i in FERRAMENTAS]


def comandos_atuais() -> list[dict]:
    try:
        cmds = _prefs().get("quick_commands")
    except Exception:
        cmds = None
    out = []
    for c in cmds if isinstance(cmds, list) else []:
        if isinstance(c, dict) and str(c.get("label", "")).strip() and str(c.get("command", "")).strip():
            out.append({"label": str(c["label"]).strip()[:24], "command": str(c["command"]).strip()[:300]})
    return out


def tecla(chave: str) -> str:
    try:
        valor = str(_prefs().get(chave) or "").strip()
    except Exception:
        valor = ""
    return valor or DEFAULTS.get(chave, "")


def nome_da_tecla(seq: str) -> str:
    """Como a tecla aparece na tela: 'Escape' vira 'Esc'."""
    return {"Escape": "Esc", "Ctrl+,": "Ctrl+,"}.get(seq, seq)
