"""Preferências do painel de controle.

Guardadas em config/api_keys.json, sob a chave 'preferences'. Valores ausentes
caem nos padrões abaixo, então um arquivo antigo continua funcionando.
"""
from __future__ import annotations

import copy
import time

DEFAULTS = {
    "background_color": "",        # vazio = cor padrão do tema
    "font_size": "medio",          # pequeno | medio | grande
    "show_clock": True,
    "show_date": True,
    "hour_format": "24",           # 24 | 12
    "temp_unit": "C",              # C | F
    "distance_unit": "km",         # km | mi
    "news_frequency": "diaria",    # diaria | 6h | manual
    "app_aliases": {},             # {"zap": "WhatsApp"}
    "quiet_when_busy": False,      # silencia alertas em reunião ou tela cheia
    "max_alerts_per_hour": 4,      # 0 = nenhum alerta de notícia
    "alert_keywords": "",          # vírgula; vazio = todos os alertas
    "sleep_after_minutes": 2,      # silêncio até o Nexus dormir (modo palavra de ativação)
    "save_memory_enabled": True,   # salvar fatos pessoais na memória
    "clear_history_on_exit": False,# não gravar o resumo da conversa ao sair
    "profile": "",
    "shortcut_mute": "F4",
    "shortcut_fullscreen": "F11",
    "shortcut_interrupt": "Escape",
    # 1.2 — atalhos novos (todos editáveis em Configurações › ATALHOS)
    "shortcut_command": "Ctrl+L",
    "shortcut_agenda": "Ctrl+N",
    "shortcut_isa": "Ctrl+I",       # 1.3 — núcleo I.S.A.
    "shortcut_ditado": "Ctrl+D",    # 1.4 — ditado no Bloco de Notas
    "open_app_busca_iniciar": False,  # 1.4 — se não achar o programa, digitar o nome no Iniciar
    # 1.4 — visão local (core/visao_local.py)
    "visao_somente_local": False,  # modo privado: a tela/câmera nunca vai para a nuvem
    "visao_local_modelo": "",      # modelo do Ollama para descrever (vazio = automático)
    "visao_ocr_motor": "auto",     # auto | windows | rapidocr
    "visao_ocr_idioma": "pt-BR",   # idioma do OCR do Windows
    "shortcut_commands": "F1",
    "shortcut_settings": "Ctrl+,",
    "shortcut_clipboard": "Ctrl+Shift+V",
    "shortcut_activity": "Ctrl+Shift+L",
    "shortcut_quickbar": "Ctrl+B",
    "shortcut_clear_chat": "Ctrl+Shift+K",
    # 1.2 — barra de acesso rápido
    "quick_bar": ["agenda", "ditado", "isa", "comandos", "area", "visao", "sistema", "config"],
    "quick_commands": [],          # [{"label": "Bom dia", "command": "me dá o briefing do dia"}]
    "custom_commands": [],         # 2.3: [{"phrase": "modo cinema", "command": "abre a Netflix"}] (core/comandos_usuario.py)
    "water_reminder_minutes": 0,   # 0 = desligado
    "weather_city": "",            # vazio = o Nexus pergunta ou usa a cidade do pedido
    "minimize_to_tray": False,     # fechar a janela deixa o Nexus na bandeja
    "voice_rate": 185,             # palavras por minuto (modo Claude)
    "voice_volume": 100,           # 0 a 100 (modo Claude)
    "audit_enabled": True,         # registrar cada ação em memory/audit.log
    "reply_tone": "",              # "" | formal | casual | direto
    "custom_vocabulary": "",       # nomes e termos para a transcrição acertar
    "panel_password_hash": "",
    "panel_password_salt": "",
    "battery_alert_percent": 20,   # 0 = desligado
    "anomalia_pc": True,           # 2.3: aprende o seu PC normal (1 medida/min, só números) e avisa quando destoa
    "brief_weekdays": [0, 1, 2, 3, 4, 5, 6],  # 0 = segunda ... 6 = domingo
    "actuator_permissions": {},    # grupo -> liberado? (ver core/settings_tools.py)
    "email_auto_read": True,       # ler em voz alta os e-mails novos assim que chegam
    "email_check_minutes": 2,      # de quanto em quanto tempo olhar a caixa de entrada
    "email_primary_only": True,    # Gmail: só a aba Principal (sem promoções/social)
    "auto_update_check": True,     # conferir as releases do GitHub e avisar quando houver versão nova
    "mic_sensitivity": 1.0,        # modo Claude: multiplica o limiar de ruído (0.6 = capta voz baixa, 1.6 = ignora barulho)
    "wake_sensitivity": 0.5,       # palavra de ativação: confiança mínima (0.35 = acorda fácil, 0.7 = menos alarme falso)
    "wake_engine": "auto",         # 1.5: "auto" | "nexus" (Whisper, "Hey Nexus") | "jarvis" (openWakeWord, "Hey Jarvis") | "treinada" (2.3: rede neural treinada na sua voz)
    # 3.4 — ligações, bom dia, bem-estar e o núcleo I.S.A. que se cuida sozinho
    "whatsapp_ddi": "55",          # DDI que entra quando você fala só DDD + número
    "whatsapp_ligar_confirmar": True,  # mostrar CONFIRMAR antes de ligar (falso = liga direto para contato salvo com nome exato)
    "email_webmail": "",           # endereço da caixa de entrada que o "bom dia" abre (vazio = pelo seu e-mail salvo)
    "bemestar_vigia": True,        # oráculo de bem-estar: avisos de pausa, água e sono ao longo do dia
    "desempenho_auto": True,       # I.S.A. ajusta o próprio ritmo do NEXUS conforme o uso do PC
    "autoregeneracao": True,       # I.S.A. corrige sozinha as falhas conhecidas (só remédios seguros)
    "carga_ferramentas": "completo",  # 4.5.0 — completo | recentes | essencial: quantas ferramentas o modelo enxerga
    "cofre_chaves": False,           # 4.6.0 — guarda chaves/senhas no cofre do sistema (Windows/macOS/Linux) em vez de texto puro
    "kanban_pasta": "",              # 4.5.0 — pasta dos quadros Kanban (vazio = memory/kanban; pode ser um cofre do Obsidian)
    "ferramentas_fixas": [],         # 4.5.0 — ferramentas que ficam sempre à vista nos perfis reduzidos
    "rede_colaborativa": False,    # trocar aprendizados de reparo com outros NEXUS da sua rede local
    "rede_colaborativa_codigo": "",  # código do grupo: só NEXUS com o mesmo código se entendem
}

PROFILES = {
    "trabalho":    {"quiet_when_busy": True,  "max_alerts_per_hour": 2, "news_frequency": "6h",     "sleep_after_minutes": 5},
    "estudo":      {"quiet_when_busy": True,  "max_alerts_per_hour": 0, "news_frequency": "manual", "sleep_after_minutes": 10},
    "descanso":    {"quiet_when_busy": False, "max_alerts_per_hour": 1, "news_frequency": "diaria", "sleep_after_minutes": 2},
    "apresentacao": {"quiet_when_busy": True, "max_alerts_per_hour": 0, "news_frequency": "manual", "sleep_after_minutes": 30},
}
PROFILE_LABELS = {"trabalho": "Trabalho", "estudo": "Estudo", "descanso": "Descanso",
                  "apresentacao": "Apresentação"}

# Leitura do arquivo a cada segundo (relógio) é desperdício; cache curto.
_cache: tuple[float, dict] | None = None
_CACHE_SECONDS = 3.0


def load() -> dict:
    global _cache
    now = time.monotonic()
    if _cache and now - _cache[0] < _CACHE_SECONDS:
        return copy.deepcopy(_cache[1])
    try:
        from memory.config_manager import load_api_keys
        stored = load_api_keys().get("preferences") or {}
    except Exception:
        stored = {}
    out = copy.deepcopy(DEFAULTS)
    if isinstance(stored, dict):
        out.update({k: v for k, v in stored.items() if k in DEFAULTS})
    _cache = (now, out)
    return copy.deepcopy(out)


def get(key: str):
    return load().get(key, DEFAULTS.get(key))


def _hash(password: str, salt: str) -> str:
    import hashlib
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                               bytes.fromhex(salt), 200_000).hex()


def password_set() -> bool:
    return bool(get("panel_password_hash"))


def check_password(password: str) -> bool:
    if not password_set():
        return True
    return _hash(password, str(get("panel_password_salt"))) == get("panel_password_hash")


def set_password(password: str) -> None:
    """Empty password removes the lock."""
    if not password:
        save({"panel_password_hash": "", "panel_password_salt": ""})
        return
    import os
    salt = os.urandom(16).hex()
    save({"panel_password_salt": salt, "panel_password_hash": _hash(password, salt)})


def save(values: dict) -> None:
    global _cache
    from memory.config_manager import _patch_config
    current = load()
    current.update({k: v for k, v in values.items() if k in DEFAULTS})
    _patch_config(preferences=current)
    _cache = None
