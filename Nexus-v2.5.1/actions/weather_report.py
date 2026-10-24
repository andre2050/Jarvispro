"""Clima de verdade (NEXUS Pro 2.0): temperatura, chuva e previsão — falada, não só aberta no navegador.

Fonte: Open-Meteo (grátis, sem chave, sem cadastro). Se a internet falhar, abre a busca do
Google no navegador, como antes, para você nunca ficar sem resposta.

    "como está o tempo?"            → agora + hoje na cidade salva (⚙ › Cidade)
    "vai chover amanhã em Recife?"  → previsão de amanhã
    "previsão da semana"            → 5 dias

Este módulo é a ÚNICA fonte de clima: o briefing (actions/briefing.py) também usa `resumo_atual`.
"""
from __future__ import annotations

import webbrowser
from datetime import date, timedelta
from urllib.parse import quote_plus

_GEO = "https://geocoding-api.open-meteo.com/v1/search"
_API = "https://api.open-meteo.com/v1/forecast"

# Código WMO → descrição curta em português
_CODIGOS = {
    0: "céu limpo", 1: "quase limpo", 2: "parcialmente nublado", 3: "nublado",
    45: "neblina", 48: "neblina com geada",
    51: "garoa fraca", 53: "garoa", 55: "garoa forte", 56: "garoa congelante", 57: "garoa congelante forte",
    61: "chuva fraca", 63: "chuva", 65: "chuva forte", 66: "chuva congelante", 67: "chuva congelante forte",
    71: "neve fraca", 73: "neve", 75: "neve forte", 77: "grãos de neve",
    80: "pancadas de chuva fracas", 81: "pancadas de chuva", 82: "pancadas de chuva fortes",
    85: "pancadas de neve", 86: "pancadas de neve fortes",
    95: "trovoadas", 96: "trovoadas com granizo", 99: "trovoadas com granizo forte",
}
_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def _desc(codigo) -> str:
    try:
        return _CODIGOS.get(int(codigo), "tempo variável")
    except (TypeError, ValueError):
        return "tempo variável"


def _cidade_padrao() -> str:
    for caminho in (("core.preferences", "weather_city"), ("memory.config_manager", "home_city")):
        try:
            if caminho[0] == "core.preferences":
                from core import preferences as P
                v = P.get(caminho[1])
            else:
                from memory.config_manager import load_api_keys
                v = load_api_keys().get(caminho[1])
            if v and str(v).strip():
                return str(v).strip()
        except Exception:
            continue
    return ""


# ── rede ─────────────────────────────────────────────────────────────────────
def _buscar(cidade: str, dias: int = 5) -> tuple[dict, dict]:
    """(local, dados). Levanta exceção se a cidade não existir ou a rede falhar."""
    import requests
    g = requests.get(_GEO, params={"name": cidade, "count": 1, "language": "pt"}, timeout=8)
    g.raise_for_status()
    res = (g.json().get("results") or [])
    if not res:
        raise LookupError(f"não encontrei a cidade “{cidade}”")
    loc = res[0]
    r = requests.get(_API, params={
        "latitude": loc["latitude"], "longitude": loc["longitude"], "timezone": "auto",
        "forecast_days": max(1, min(7, dias)),
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum",
    }, timeout=8)
    r.raise_for_status()
    return loc, r.json()


# ── texto (puro: testável sem internet) ──────────────────────────────────────
def _num(v, casas: int = 0) -> str:
    try:
        return f"{float(v):.{casas}f}".rstrip("0").rstrip(".") if casas else f"{round(float(v))}"
    except (TypeError, ValueError):
        return "?"


def _nome_dia(iso: str, hoje: date | None = None) -> str:
    hoje = hoje or date.today()
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return iso
    dif = (d - hoje).days
    if dif == 0:
        return "hoje"
    if dif == 1:
        return "amanhã"
    return _SEMANA[d.weekday()]


def _linha_dia(daily: dict, i: int, hoje: date | None = None) -> str:
    chuva = daily.get("precipitation_probability_max", [None] * (i + 1))[i]
    partes = [f"{_nome_dia(daily['time'][i], hoje)}: {_desc(daily['weather_code'][i])}, "
              f"mín {_num(daily['temperature_2m_min'][i])}° e máx {_num(daily['temperature_2m_max'][i])}°"]
    if chuva is not None:
        partes.append(f"{_num(chuva)}% de chance de chuva")
    return ", ".join(partes)


def formatar(loc: dict, dados: dict, quando: str = "hoje", hoje: date | None = None) -> str:
    nome = loc.get("name", "")
    if loc.get("admin1") and loc["admin1"] != nome:
        nome += f" ({loc['admin1']})"
    cur, daily = dados.get("current", {}), dados.get("daily", {})
    q = (quando or "hoje").strip().lower()
    if q in ("semana", "week", "proximos dias", "próximos dias", "5 dias"):
        n = len(daily.get("time", []))
        return f"Previsão para {nome}: " + " | ".join(_linha_dia(daily, i, hoje) for i in range(n))
    if q in ("amanhã", "amanha", "tomorrow") and len(daily.get("time", [])) > 1:
        return f"Amanhã em {nome} — " + _linha_dia(daily, 1, hoje).split(": ", 1)[1] + "."
    agora = ""
    if cur:
        agora = (f"Agora em {nome}: {_desc(cur.get('weather_code'))}, {_num(cur.get('temperature_2m'))}° "
                 f"(sensação de {_num(cur.get('apparent_temperature'))}°), umidade {_num(cur.get('relative_humidity_2m'))}%, "
                 f"vento de {_num(cur.get('wind_speed_10m'))} km/h. ")
    hoje_txt = ("Hoje: " + _linha_dia(daily, 0, hoje).split(": ", 1)[1] + ".") if daily.get("time") else ""
    return (agora + hoje_txt).strip()


def resumo_atual(cidade: str) -> str:
    """Uma frase com o clima de agora e de hoje (usada pelo briefing). Levanta exceção se falhar."""
    loc, dados = _buscar(cidade, dias=1)
    return formatar(loc, dados, "hoje")


# ── a ferramenta ─────────────────────────────────────────────────────────────
def weather_action(parameters: dict, player=None, session_memory=None) -> str:
    cidade = str(parameters.get("city") or "").strip() or _cidade_padrao()
    quando = str(parameters.get("when") or parameters.get("time") or "hoje").strip()
    if not cidade:
        return "Qual cidade? Diga o nome, ou salve a sua em Configurações para eu não perguntar."
    try:
        loc, dados = _buscar(cidade, dias=5)
        texto = formatar(loc, dados, quando)
        _log(f"clima de {loc.get('name', cidade)}", player)
        if session_memory:
            try:
                session_memory.set_last_search(query=f"clima {cidade} {quando}", response=texto)
            except Exception:
                pass
        return texto
    except LookupError as e:
        return f"Não consegui o clima: {e}. Confira o nome da cidade."
    except Exception as e:
        # Sem internet / serviço fora do ar: abre a busca para a pessoa não ficar sem nada.
        try:
            webbrowser.open(f"https://www.google.com/search?q={quote_plus(f'clima em {cidade} {quando}')}")
            return (f"Não consegui os dados do clima agora ({type(e).__name__}); "
                    f"abri a busca de {cidade} no navegador.")
        except Exception:
            return f"Não consegui o clima de {cidade} agora e também não consegui abrir o navegador."


def _log(message: str, player=None) -> None:
    print(f"[Clima] {message}")
    if player:
        try:
            player.write_log(f"SYS: ☀ {message}")
        except Exception:
            pass


TOOL = {
    "name": "weather_report",
    "description": (
        "REAL weather: current conditions plus the forecast, returned as text you can speak. "
        "city is optional (the saved city is used when omitted); when = hoje (default, includes "
        "right now), amanhã, or semana (next 5 days). Use for 'como está o tempo?', 'vai chover "
        "amanhã?', 'previsão da semana', 'preciso de guarda-chuva?'."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "city": {"type": "STRING", "description": "City name (optional — the saved city is used if empty)"},
            "when": {"type": "STRING", "description": "hoje | amanhã | semana (default hoje)"},
        },
        "required": [],
    },
    "handler": weather_action,
}
