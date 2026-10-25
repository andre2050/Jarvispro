"""Lógica do Painel de Configurações (sem Qt, para poder ser testada sozinha).

Reúne o que o painel mostra e faz:
  - status e informações "sobre" do projeto;
  - permissões do Atuador (quais grupos de ações o assistente pode executar);
  - backup e restauração de config/api_keys.json + memory/*.json;
  - reset em três níveis (preferências, memória, tudo).

Preferências do Atuador ficam em preferences['actuator_permissions'].
Nada aqui apaga dados sem antes criar uma cópia de segurança.
"""
from __future__ import annotations

import json
import platform
import sys
import time
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config" / "api_keys.json"
MEMORY_DIR = BASE_DIR / "memory"
BACKUP_DIR = MEMORY_DIR / "backups"
VERSION_FILE = BASE_DIR / "VERSION"

# Grupos do Atuador: rótulo exibido -> nomes de arquivo em actions/ (sem .py).
# Ações que não aparecem aqui ficam sempre liberadas.
ACTUATOR_GROUPS: dict[str, tuple[str, tuple[str, ...]]] = {
    "apps":      ("Abrir e fechar aplicativos", ("open_app", "desktop", "shortcut_manager")),
    "arquivos":  ("Ler, criar e mover arquivos", ("file_controller", "file_processor")),
    "sistema":   ("Volume, Wi-Fi, energia e ajustes do sistema", ("computer_settings", "computer_control", "system_update")),
    "navegador": ("Controlar o navegador", ("browser_control",)),
    "mensagens": ("Enviar mensagens e fazer ligações", ("send_message", "ligar_whatsapp")),
    # 2.1 — o agente que escreve e RODA programas passou a ter o seu interruptor
    "programacao": ("Criar e rodar programas (agente de código)", ("dev_agent", "code_helper")),
    "casa": ("Controlar a casa inteligente (luzes, cortinas, ar, fechaduras)", ("casa_inteligente",)),
}

# Caminhos de memória que entram em backup e que o reset mexe.
_MEMORY_FILES = ("long_term.json", "facts.json")


# ── Informações ──────────────────────────────────────────────────────────────

def app_version() -> str:
    """Versão mostrada no app: a de memory/version.json (a mesma do HUD)."""
    try:
        import json as _json
        data = _json.loads((MEMORY_DIR / "version.json").read_text(encoding="utf-8"))
        return str(data.get("version") or "desconhecida")
    except Exception:
        pass
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip() or "desconhecida"
    except Exception:
        return "desconhecida"


def _read_config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def api_key_status() -> list[tuple[str, bool]]:
    """(nome da chave, configurada?) — nunca devolve o valor da chave."""
    data = _read_config()
    out = []
    for key, value in data.items():
        lowered = key.lower()
        if "key" not in lowered and "token" not in lowered:
            continue
        out.append((key, isinstance(value, str) and bool(value.strip())))
    return out


def status_info(plugin_count: int | None = None) -> list[tuple[str, str]]:
    cfg = _read_config()
    keys = api_key_status()
    configured = sum(1 for _, ok in keys if ok)
    return [
        ("Versão", app_version()),
        ("Nome do assistente", str(cfg.get("assistant_name") or "NEXUS")),
        ("Sistema", f"{platform.system()} {platform.release()}"),
        ("Python", platform.python_version()),
        ("Chaves de API configuradas", f"{configured} de {len(keys)}"),
        ("Plugins carregados", "—" if plugin_count is None else str(plugin_count)),
        ("Pasta do projeto", str(BASE_DIR)),
    ]


def _licenca_resumo() -> str:
    try:
        from core import licenca
        return licenca.texto_curto()
    except Exception:
        return "não foi possível conferir"


def about_info() -> list[tuple[str, str]]:
    return [
        ("Sua licença", _licenca_resumo()),
        ("Projeto", "NEXUS Ultra 2026"),
        ("Versão", app_version()),
        ("Desenvolvedor", "André Luiz Lima Menezes"),
        ("Licença", "Veja o arquivo LICENSE na pasta do projeto"),
        ("Python", sys.version.split()[0]),
    ]


def diagnostics_text(plugin_count: int | None = None) -> str:
    lines = [f"{k}: {v}" for k, v in status_info(plugin_count)]
    return "\n".join(["NEXUS — diagnóstico"] + lines)


# ── Atuador ──────────────────────────────────────────────────────────────────

def actuator_permissions() -> dict[str, bool]:
    """Estado de cada grupo. Grupo ausente = liberado (comportamento de antes)."""
    from core import preferences as _P
    saved = _P.get("actuator_permissions") or {}
    if not isinstance(saved, dict):
        saved = {}
    return {g: bool(saved.get(g, True)) for g in ACTUATOR_GROUPS}


def _all_action_stems() -> set[str]:
    return {stem for _, stems in ACTUATOR_GROUPS.values() for stem in stems}


def actuator_action_permissions() -> dict[str, bool]:
    """Liberação de cada ação individual. Ausente = liberada."""
    from core import preferences as _P
    saved = _P.get("actuator_permissions") or {}
    if not isinstance(saved, dict):
        saved = {}
    return {stem: bool(saved.get(stem, True)) for stem in sorted(_all_action_stems())}


def set_actuator_permission(key: str, allowed: bool) -> None:
    """key pode ser um grupo ('apps') ou uma ação ('open_app')."""
    if key not in ACTUATOR_GROUPS and key not in _all_action_stems():
        raise ValueError(f"permissão desconhecida: {key}")
    from core import preferences as _P
    saved = _P.get("actuator_permissions") or {}
    current = dict(saved) if isinstance(saved, dict) else {}
    current[key] = bool(allowed)
    _P.save({"actuator_permissions": current})


def _group_of(action_stem: str) -> str | None:
    for group, (_, stems) in ACTUATOR_GROUPS.items():
        if action_stem in stems:
            return group
    return None


def actuator_allowed(action_stem: str) -> tuple[bool, str]:
    """(pode executar?, mensagem para o modelo se não puder).

    Bloqueia se o grupo OU a ação individual estiver desligada. Qualquer falha
    ao ler a preferência libera a ação, para que um erro de config nunca trave
    o assistente.
    """
    group = _group_of(action_stem)
    if group is None:
        return True, ""
    try:
        from core import preferences as _P
        saved = _P.get("actuator_permissions") or {}
        if not isinstance(saved, dict):
            saved = {}
    except Exception:
        return True, ""
    if not saved.get(group, True):
        label = ACTUATOR_GROUPS[group][0]
        return False, (f"Permissão desligada no painel de configurações: '{label}'. "
                       "Peça ao usuário para ativá-la se ele quiser que eu faça isso.")
    if not saved.get(action_stem, True):
        return False, (f"A ação '{action_stem}' está desligada no painel de configurações. "
                       "Peça ao usuário para ativá-la se ele quiser que eu faça isso.")
    return True, ""


# ── Testar chave de API ──────────────────────────────────────────────────────

TESTABLE_KEYS = ("gemini_api_key", "anthropic_api_key")


def test_api_key(name: str, timeout: float = 8.0) -> tuple[bool, str]:
    """Faz uma chamada leve à API e diz se a chave funciona. Nunca mostra a chave."""
    import urllib.error
    import urllib.request
    key = str(_read_config().get(name) or "").strip()
    if not key:
        return False, "a chave está vazia"
    if name == "gemini_api_key":
        label = "Gemini"
        req = urllib.request.Request(
            "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1",
            headers={"x-goog-api-key": key})
    elif name == "anthropic_api_key":
        label = "Anthropic"
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/models?limit=1",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
    else:
        return False, "não sei testar esta chave"
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if r.status == 200:
                return True, f"{label}: chave válida"
            return False, f"{label}: resposta inesperada ({r.status})"
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return False, f"{label}: chave recusada ({e.code})"
        return False, f"{label}: erro {e.code}"
    except Exception as e:
        return False, f"{label}: sem resposta ({type(e).__name__})"


# ── Backup e restauração ─────────────────────────────────────────────────────

def _backup_members() -> list[tuple[Path, str]]:
    items: list[tuple[Path, str]] = []
    if CONFIG_FILE.exists():
        items.append((CONFIG_FILE, "config/api_keys.json"))
    for name in _MEMORY_FILES:
        p = MEMORY_DIR / name
        if p.exists():
            items.append((p, f"memory/{name}"))
    return items


def create_backup(dest: str | Path) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    members = _backup_members()
    if not members:
        raise FileNotFoundError("nada para copiar (config e memória não encontradas)")
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, arc in members:
            zf.write(path, arc)
        zf.writestr("backup_info.json", json.dumps({
            "app": "NEXUS", "version": app_version(),
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "members": [arc for _, arc in members],
        }, indent=2, ensure_ascii=False))
    return dest


_ALLOWED_RESTORE = {"config/api_keys.json"} | {f"memory/{n}" for n in _MEMORY_FILES}


def validate_backup(src: str | Path) -> list[str]:
    """Devolve os membros que a restauração vai escrever. Levanta erro se inválido."""
    src = Path(src)
    if not zipfile.is_zipfile(src):
        raise ValueError("o arquivo não é um zip válido")
    with zipfile.ZipFile(src) as zf:
        names = zf.namelist()
        if "backup_info.json" not in names:
            raise ValueError("este zip não é um backup do NEXUS")
        usable = [n for n in names if n in _ALLOWED_RESTORE]
        if not usable:
            raise ValueError("o backup não contém config nem memória")
        for n in usable:
            json.loads(zf.read(n).decode("utf-8"))   # falha se o JSON estiver quebrado
    return usable


def restore_backup(src: str | Path) -> list[str]:
    """Restaura o backup. Antes, salva uma cópia do estado atual em memory/backups/."""
    members = validate_backup(src)
    safety = BACKUP_DIR / f"antes_da_restauracao_{time.strftime('%Y%m%d_%H%M%S')}.zip"
    try:
        create_backup(safety)
    except FileNotFoundError:
        pass  # nada para salvar ainda; a restauração segue
    with zipfile.ZipFile(src) as zf:
        for name in members:
            target = (BASE_DIR / name).resolve()
            if BASE_DIR.resolve() not in target.parents:
                continue   # proteção contra caminhos fora do projeto
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(name))
    return members


# ── Reset ────────────────────────────────────────────────────────────────────

RESET_LEVELS = {
    "preferencias": "Preferências",
    "memoria": "Memória",
    "tudo": "Tudo (preferências, memória e permissões)",
}


def reset(level: str) -> Path:
    """Reseta o nível pedido. Sempre cria cópia de segurança antes e devolve o caminho dela.
    As chaves de API nunca são apagadas por aqui."""
    if level not in RESET_LEVELS:
        raise ValueError(f"nível desconhecido: {level}")
    safety = BACKUP_DIR / f"antes_do_reset_{level}_{time.strftime('%Y%m%d_%H%M%S')}.zip"
    try:
        create_backup(safety)
    except FileNotFoundError:
        safety = Path("")

    if level in ("preferencias", "tudo"):
        from core import preferences as _P
        from memory.config_manager import _patch_config
        _patch_config(preferences=dict(_P.DEFAULTS))
        _P._cache = None

    if level in ("memoria", "tudo"):
        (MEMORY_DIR / "long_term.json").write_text("{}", encoding="utf-8")
        (MEMORY_DIR / "facts.json").write_text("[]", encoding="utf-8")

    return safety


def list_reset_backups() -> list[Path]:
    """Cópias feitas antes de cada reset, da mais nova para a mais antiga."""
    if not BACKUP_DIR.exists():
        return []
    return sorted(BACKUP_DIR.glob("antes_do_reset_*.zip"),
                  key=lambda p: p.stat().st_mtime, reverse=True)


def undo_last_reset() -> Path:
    """Restaura a cópia do reset mais recente. Ela é renomeada para não ser
    desfeita duas vezes; o próximo 'desfazer' usa o reset anterior."""
    items = list_reset_backups()
    if not items:
        raise FileNotFoundError("nenhum reset para desfazer")
    target = items[0]
    restore_backup(target)
    target.rename(target.with_name("desfeito_" + target.name))
    from core import preferences as _P
    _P._cache = None
    return target


# ── Teste do microfone ───────────────────────────────────────────────────────

def test_microphone(seconds: float = 3.0) -> tuple[bool, str]:
    """Grava alguns segundos no microfone escolhido e diz se ele está captando."""
    try:
        import numpy as np
        import sounddevice as sd
    except Exception as e:
        return False, f"Biblioteca de áudio indisponível ({type(e).__name__})."
    try:
        from core import audio_devices
        from memory.config_manager import get_input_device
        dev = audio_devices.resolve(get_input_device(), "input")
    except Exception:
        dev = None
    try:
        rate = int(sd.query_devices(dev, "input")["default_samplerate"])
        data = sd.rec(int(seconds * rate), samplerate=rate, channels=1,
                      dtype="float32", device=dev)
        sd.wait()
    except Exception as e:
        return False, f"Não consegui abrir o microfone: {e}"
    x = np.asarray(data).reshape(-1)
    if x.size == 0:
        return False, "O microfone não enviou nenhum som."
    peak = float(np.max(np.abs(x)))
    rms = float(np.sqrt(np.mean(x ** 2)))
    if peak < 0.003:
        return False, ("Nenhum som captado. Confirme o microfone escolhido e se ele não está "
                       "no mudo ou desligado no sistema.")
    if peak > 0.98:
        return False, "O som está saturando (muito alto). Afaste o microfone ou baixe o volume de entrada."
    if rms < 0.01:
        return True, (f"Captou um som baixo (nível médio {rms:.3f}). "
                      "Se o NEXUS não ouvir, aumente a sensibilidade do microfone.")
    return True, f"Microfone funcionando (nível médio {rms:.3f}). Fale normalmente para testar."

