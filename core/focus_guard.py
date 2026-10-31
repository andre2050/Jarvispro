"""Modo reunião, tela cheia e limites de alerta de notícias."""
from __future__ import annotations

import time
from collections import deque

from core import preferences as P
from core.protecao import engolida as _engolida

MEETING_APPS = {"teams.exe", "ms-teams.exe", "zoom.exe", "zoomwebhost.exe",
                "webex.exe", "skype.exe", "lync.exe"}
_HOUR = 3600
_alert_times: deque = deque()


def _meeting_app() -> str | None:
    try:
        import psutil
        for p in psutil.process_iter(["name"]):
            name = p.info.get("name") or ""
            if name.lower() in MEETING_APPS:
                return name
    except Exception:
        _engolida("core/focus_guard.py:23")
    return None


def _fullscreen_app() -> str | None:
    """Windows only: the foreground window covers the whole screen (games, videos)."""
    try:
        import ctypes
        import ctypes.wintypes as wt
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        rect = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        if rect.left <= 0 and rect.top <= 0 and rect.right >= sw and rect.bottom >= sh:
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            import psutil
            name = psutil.Process(pid.value).name()
            if name.lower() in ("explorer.exe", "searchhost.exe"):
                return None
            return name
    except Exception:
        _engolida("core/focus_guard.py:48")
    return None


def busy_reason() -> str | None:
    """Why alerts should wait right now, or None.

    A running focus block (actions/focus_mode.py) always counts — the user
    asked for silence. Meetings and full screen count only when the
    quiet_when_busy preference is on."""
    try:
        import sys
        fm = sys.modules.get("actions.focus_mode")
        if fm is None:
            from actions import focus_mode as fm
        reason = fm.active_reason()
        if reason:
            return reason
    except Exception:
        _engolida("core/focus_guard.py:67")
    if not P.get("quiet_when_busy"):
        return None
    meeting = _meeting_app()
    if meeting:
        return f"reunião ({meeting})"
    full = _fullscreen_app()
    if full:
        return f"tela cheia ({full})"
    return None


def monitor_allowed() -> bool:
    """False when news checks are set to manual, or the user is busy."""
    if str(P.get("news_frequency")) == "manual":
        return False
    return busy_reason() is None


def filter_alerts(alerts: list[str]) -> list[str]:
    """Apply the keyword filter and the per-hour limit to a batch of news alerts."""
    if not alerts:
        return alerts
    kws = [k.strip().lower() for k in str(P.get("alert_keywords") or "").split(",") if k.strip()]
    if kws:
        alerts = [a for a in alerts if any(k in a.lower() for k in kws)]
    try:
        limit = int(P.get("max_alerts_per_hour"))
    except (TypeError, ValueError):
        limit = 4
    now = time.time()
    while _alert_times and now - _alert_times[0] > _HOUR:
        _alert_times.popleft()
    out = []
    for a in alerts:
        if len(_alert_times) >= limit:
            break
        _alert_times.append(now)
        out.append(a)
    return out
