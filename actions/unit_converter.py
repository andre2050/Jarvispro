"""Unit, measure and live currency conversion by voice.

Two layers, one tool:

- Everyday units (length, weight, temperature, volume, speed, data) are
  converted offline from a static table — instant, no network.
- Currencies (USD to BRL, EUR to JPY, ...) use live exchange rates from
  open.er-api.com, cached in config/currency_cache.json for 6 hours so
  repeated questions cost nothing; if the network is down, the last cached
  rates still answer the question.

The model passes natural unit words ("kilometers", "km", "miles") — they are
normalised by prefix matching, so "mile" finds "miles" and "kilo" finds
"kilograms" only if unambiguous.
"""

import json
import time
from pathlib import Path
from core.protecao import engolida as _engolida

try:
    import requests
except Exception:                                   # pragma: no cover
    requests = None

# ── Config dir: same place api_keys.json lives ────────────────────────────────
try:
    from memory.config_manager import CONFIG_DIR
except Exception:
    CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

_CACHE_FILE   = CONFIG_DIR / "currency_cache.json"
_CACHE_MAX_AG = 6 * 3600          # 6 hours

# ── Static unit tables (base unit: metres / grams / litres / bytes ...) ──────
# Each entry: canonical name → factor to the base unit.
_LENGTH = {
    "millimeters": 0.001, "centimeters": 0.01, "meters": 1.0, "kilometers": 1000.0,
    "inches": 0.0254, "feet": 0.3048, "yards": 0.9144, "miles": 1609.344,
    "nautical_miles": 1852.0,
}
_WEIGHT = {
    "milligrams": 1e-6, "grams": 0.001, "kilograms": 1.0, "tonnes": 1000.0,
    "ounces": 0.0283495, "pounds": 0.453592, "stones": 6.35029,
}
_VOLUME = {
    "milliliters": 0.001, "centiliters": 0.01, "liters": 1.0,
    "cups": 0.236588, "pints": 0.473176, "gallons": 3.78541,
}
_SPEED = {
    "meters_per_second": 1.0, "kilometers_per_hour": 0.277778,
    "miles_per_hour": 0.44704, "knots": 0.514444,
}
_DATA = {
    "bytes": 1.0, "kilobytes": 1024.0, "megabytes": 1024.0 ** 2,
    "gigabytes": 1024.0 ** 3, "terabytes": 1024.0 ** 4,
}
_AREA = {
    "square_meters": 1.0, "square_kilometers": 1e6, "square_feet": 0.092903,
    "square_miles": 2.58999e6, "hectares": 10000.0, "acres": 4046.86,
}

_TABLES = {
    "length": _LENGTH, "weight": _WEIGHT, "volume": _VOLUME,
    "speed": _SPEED, "data": _DATA, "area": _AREA,
}

# ── Currencies supported by the live-rate API (subset; API knows more) ───────
# The enum below is what the model is allowed to pass; ISO 4217 codes.
_CURRENCY = {
    "USD", "EUR", "BRL", "GBP", "JPY", "CAD", "AUD", "CHF", "CNY", "INR",
    "MXN", "ARS", "TRY", "ZAR", "SEK", "NOK", "KRW", "RUB", "PLN", "CZK",
    "ILS", "AED", "SAR", "HKD", "SGD", "NZD", "THB", "IDR", "MYR", "PHP",
    "COP", "CLP", "PEN", "UYU", "BOB", "PYG", "VES", "BTC", "ETH",
}

_ALIASES = {
    "c": "celsius", "f": "fahrenheit", "k": "kelvin",
    "celsius": "celsius", "fahrenheit": "fahrenheit", "kelvin": "kelvin",
}


def _norm(unit: str) -> str:
    return unit.strip().lower().replace(" ", "_").replace("°", "")


_ALIAS_MAP = {
    "km": "kilometers", "kmh": "kilometers_per_hour", "km_h": "kilometers_per_hour",
    "cm": "centimeters", "mm": "millimeters",
    "mi": "miles", "ft": "feet", "in": "inches", "yd": "yards",
    "kg": "kilograms", "lb": "pounds", "lbs": "pounds", "oz": "ounces",
    "g": "grams", "mg": "milligrams", "t": "tonnes",
    "l": "liters", "ml": "milliliters", "gal": "gallons",
    "mph": "miles_per_hour", "kn": "knots", "mps": "meters_per_second", "m_s": "meters_per_second",
    "kb": "kilobytes", "mb": "megabytes", "gb": "gigabytes", "tb": "terabytes",
    "ha": "hectares", "ac": "acres",
}


def _find_unit(unit: str):
    """Return (kind, canonical_name) for a unit word, or (None, None).

    Order: temperature alias → exact short alias → exact table name →
    prefix match, accepted ONLY when it is unique across every table
    (so 'mi' finds 'miles' and never collides with 'milligrams').
    """
    u = _norm(unit)
    if u in _ALIASES:
        return "temperature", _ALIASES[u]
    if u in _ALIAS_MAP:
        canon = _ALIAS_MAP[u]
        for kind, table in _TABLES.items():
            if canon in table:
                return kind, canon
        return None, None
    for kind, table in _TABLES.items():
        if u in table:
            return kind, u
    hits = [
        (kind, k)
        for kind, table in _TABLES.items()
        for k in table
        if k.startswith(u) and len(u) >= 3
    ]
    if len(hits) == 1:
        return hits[0]
    return None, None


def _convert_temperature(value: float, from_u: str, to_u: str):
    if from_u == to_u:
        return value
    c = value
    if from_u == "fahrenheit":
        c = (value - 32) * 5.0 / 9.0
    elif from_u == "kelvin":
        c = value - 273.15
    if to_u == "fahrenheit":
        return c * 9.0 / 5.0 + 32
    if to_u == "kelvin":
        return c + 273.15
    return c


def _fetch_rates(base: str) -> dict:
    """Live rates with a 6h cache; falls back to the cache when offline."""
    cache = {}
    try:
        cache = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        cache = {}
    entry = cache.get(base)
    if entry and (time.time() - entry.get("fetched_at", 0)) < _CACHE_MAX_AG:
        return entry["rates"]

    if requests is not None:
        try:
            resp = requests.get(
                f"https://open.er-api.com/v6/latest/{base}", timeout=10,
            )
            resp.raise_for_status()
            rates = resp.json().get("rates") or {}
            if rates:
                cache[base] = {"fetched_at": time.time(), "rates": rates}
                _save_cache(cache)
                return rates
        except Exception:
            _engolida("actions/unit_converter.py:168")

    if entry:                       # stale but better than nothing
        return entry["rates"]
    return {}


def _save_cache(cache: dict) -> None:
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(
            json.dumps(cache, indent=1), encoding="utf-8",
        )
    except Exception:
        _engolida("actions/unit_converter.py:182")


def _fmt(value: float) -> str:
    if abs(value) >= 1000:
        return f"{value:,.2f}".replace(",", " ")
    if abs(value) >= 1:
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return f"{value:.6g}"


def unit_converter_action(parameters: dict, player=None, session_memory=None) -> str:
    value     = parameters.get("value")
    from_unit = parameters.get("from_unit") or ""
    to_unit   = parameters.get("to_unit") or ""

    if value is None:
        msg = "Sir, I need a value to convert, for example 'convert 10 kilometers to miles'."
        _log(msg, player)
        return msg

    try:
        value = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        msg = f"Sir, '{parameters.get('value')}' is not a number I can convert."
        _log(msg, player)
        return msg

    fu = str(from_unit).strip().upper()
    tu = str(to_unit).strip().upper()

    # ── Currency pair? Both sides must be currency codes. ─────────────────
    if fu in _CURRENCY and tu in _CURRENCY:
        if fu == tu:
            msg = f"Sir, {value} {fu} is {value} {tu}."
            _log(msg, player)
            return msg
        rates = _fetch_rates(fu)
        rate = rates.get(tu)
        if rate is None:
            msg = (f"Sir, I couldn't get an exchange rate from {fu} to {tu} "
                   "right now — the network may be down and no cached rate exists.")
            _log(msg, player)
            return msg
        result = value * float(rate)
        msg = f"Sir, {_fmt(value)} {fu} is {_fmt(result)} {tu}."
        _log(msg, player)
        return msg

    # ── Ordinary units ─────────────────────────────────────────────────────
    f_kind, f_canon = _find_unit(str(from_unit))
    t_kind, t_canon = _find_unit(str(to_unit))

    if f_kind is None or t_kind is None:
        msg = (f"Sir, I don't know how to convert '{from_unit}' to '{to_unit}'. "
               "I handle length, weight, temperature, volume, speed, data, area "
               "and common currencies.")
        _log(msg, player)
        return msg

    if f_kind != t_kind:
        msg = f"Sir, {f_canon.replace('_', ' ')} and {t_canon.replace('_', ' ')} measure different things, so I can't convert between them."
        _log(msg, player)
        return msg

    if f_kind == "temperature":
        result = _convert_temperature(value, f_canon, t_canon)
    else:
        table = _TABLES[f_kind]
        result = (value * table[f_canon]) / table[t_canon]

    pretty_from = f_canon.replace("_per_", " per ").replace("_", " ")
    pretty_to   = t_canon.replace("_per_", " per ").replace("_", " ")
    msg = f"Sir, {_fmt(value)} {pretty_from} is {_fmt(result)} {pretty_to}."
    _log(msg, player)
    return msg


def _log(message: str, player=None) -> None:
    print(f"[Units] {message}")
    if player:
        try:
            player.write_log(f"NEXUS: {message}")
        except Exception:
            _engolida("actions/unit_converter.py:266")


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "unit_converter",
    "description": (
        "Converts values between units and currencies: length, weight, "
        "temperature, volume, speed, data size, area, and live exchange "
        "rates for ~30 currencies (USD to BRL, EUR to JPY, ...). "
        "Example: value=10, from_unit=kilometers, to_unit=miles."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "value": {
                "type": "NUMBER",
                "description": "The number to convert"
            },
            "from_unit": {
                "type": "STRING",
                "description": "Source unit or currency code, e.g. kilometers, kg, celsius, USD"
            },
            "to_unit": {
                "type": "STRING",
                "description": "Target unit or currency code, e.g. miles, pounds, fahrenheit, BRL"
            },
        },
        "required": ["value", "from_unit", "to_unit"]
    },
    "handler": unit_converter_action,
}
