"""Music / media playback control by voice.

Sends the operating system's media keys (play/pause, next, previous, mute) so
whatever player is currently active — Spotify, YouTube in the browser, VLC,
the system player — reacts exactly as if the user had pressed the key on
the keyboard. Works on Windows, macOS and most Linux desktops via pyautogui,
which is already a project dependency.
"""
from core.protecao import engolida as _engolida

try:
    import pyautogui
except Exception:                                   # pragma: no cover
    pyautogui = None

# OS media-key names understood by pyautogui on each platform.
_MEDIA_KEYS = {
    "play_pause": {
        "win32":  "playpause",
        "darwin": "playpause",
        "linux":  "playpause",
    },
    "next": {
        "win32":  "nexttrack",
        "darwin": "nexttrack",
        "linux":  "nexttrack",
    },
    "previous": {
        "win32":  "prevtrack",
        "darwin":  "prevtrack",
        "linux":  "prevtrack",
    },
    "mute": {
        "win32":  "volumemute",
        "darwin": "mute",
        "linux":  "mute",
    },
    "volume_up": {
        "win32":  "volumeup",
        "darwin": "volumeup",
        "linux":  "volumeup",
    },
    "volume_down": {
        "win32":  "volumedown",
        "darwin": "volumedown",
        "linux":  "volumedown",
    },
}


def _platform_key() -> str:
    import sys
    if sys.platform.startswith("win"):
        return "win32"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def music_action(parameters: dict, player=None, session_memory=None) -> str:
    command = str(parameters.get("command") or "").strip().lower()

    if not command:
        msg = "Sir, the music command is missing. Say play, pause, next, previous or mute."
        _log(msg, player)
        return msg

    if pyautogui is None:
        msg = "Sir, the automation module is not available, so I cannot control media playback."
        _log(msg, player)
        return msg

    if command not in _MEDIA_KEYS:
        msg = f"Sir, I don't know the music command '{command}'. Use play_pause, next, previous or mute."
        _log(msg, player)
        return msg

    key = _MEDIA_KEYS[command][_platform_key()]
    # 1.4.3 — cada tecla de volume do Windows mexe só 2 %: 5 toques = 10 %,
    # que é o que se espera de "aumenta o volume".
    vezes = 5 if command in ("volume_up", "volume_down") else 1

    try:
        pyautogui.press(key, presses=vezes, interval=0.02)
    except Exception as e:
        msg = f"Sir, I couldn't send the media key: {e}"
        _log(msg, player)
        return msg

    labels = {
        "play_pause": "toggled play and pause",
        "next":        "skipped to the next track",
        "previous":    "went back to the previous track",
        "mute":        "toggled mute",
        "volume_up":   "raised the volume (about 10%)",
        "volume_down": "lowered the volume (about 10%)",
    }
    # 1.4.3 — volume_up/volume_down não tinham frase: a tecla era enviada e
    # depois a função "falhava" com KeyError ('volume_up').
    msg = f"Sir, {labels.get(command, command.replace('_', ' '))}."
    _log(msg, player)
    return msg


def _log(message: str, player=None) -> None:
    print(f"[Music] {message}")
    if player:
        try:
            player.write_log(f"NEXUS: {message}")
        except Exception:
            _engolida("actions/music_control.py:110")


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "music_control",
    "description": (
        "Controls music and media playback with the OS media keys: play or "
        "pause the current track, skip to the next track, go back to the "
        "previous track, toggle mute, or raise/lower the system volume. "
        "Works with whatever player is currently active (Spotify, YouTube, "
        "VLC, system player)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "command": {
                "type": "STRING",
                "enum": ["play_pause", "next", "previous", "mute",
                         "volume_up", "volume_down"],
                "description": "Which media action to perform"
            }
        },
        "required": ["command"]
    },
    "handler": music_action,
}
