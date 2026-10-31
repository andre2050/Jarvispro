"""Price alerts — "tell me when bitcoin passes 500 thousand".

The user sets a one-shot alert: a coin, a direction (above/below) and a
target price in BRL or USD. A daemon thread checks CoinGecko's public API
every 60 seconds; when the target crosses, the alert fires: a chime (same
three-tone bell as the timers), a log entry, and the alert is marked
triggered so it never fires twice. Coins are identified by their CoinGecko
id, with the usual nicknames (btc, eth, sol…) mapped automatically.
"""

import json
import threading
import time
from pathlib import Path

try:
    CONFIG_DIR = Path(__file__).resolve().parent.parent / "memory"
except Exception:                                    # pragma: no cover
    CONFIG_DIR = Path("memory")

_FILE = CONFIG_DIR / "price_alerts.json"
_LOCK = threading.Lock()
_CHECK_SECS = 60

_ALIASES = {
    "btc": "bitcoin", "bitcoin": "bitcoin",
    "eth": "ethereum", "ethereum": "ethereum",
    "sol": "solana", "solana": "solana",
    "doge": "dogecoin", "dogecoin": "dogecoin",
    "ada": "cardano", "cardano": "cardano",
    "xrp": "ripple", "ripple": "ripple",
    "bnb": "binancecoin",
    "ltc": "litecoin",
    "dot": "polkadot",
}

# The most recent player (UI log handle) seen — the background thread uses
# it so a fired alert shows up in the log even when the model is idle.
_PLAYER = None
_THREAD: threading.Thread | None = None


def _load() -> list:
    try:
        data = json.loads(_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def _save(alerts: list) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _FILE.write_text(json.dumps(alerts, indent=2, ensure_ascii=False),
                         encoding="utf-8")
    except Exception as e:
        print(f"[PriceAlert] could not save: {e}")


def _fetch_prices(coin_ids: set) -> dict:
    """One CoinGecko call for every pending coin. Free endpoint, no key."""
    import requests
    r = requests.get(
        "https://api.coingecko.com/api/v3/simple/price",
        params={"ids": ",".join(sorted(coin_ids)),
                "vs_currencies": "usd,brl"},
        timeout=8,
    )
    r.raise_for_status()
    return r.json()


def pending_summary() -> str:
    """One line describing active alerts, for the morning briefing."""
    pending = [a for a in _load() if not a.get("triggered")]
    if not pending:
        return ""
    parts = [f"{a['coin']} {a['direction']} "
             f"{a['target']:,.2f} {a['currency'].upper()}"
             for a in pending]
    return "PRICE ALERTS being watched: " + "; ".join(parts) + "."


def _check_alerts(player=None) -> list:
    """One pass over the pending alerts. Returns the alerts that fired."""
    with _LOCK:
        alerts = _load()
    pending_ids = {a["coin"] for a in alerts if not a.get("triggered")}
    if not pending_ids:
        return []
    try:
        prices = _fetch_prices(pending_ids)
    except Exception:
        return []                                  # network hiccup — next cycle

    fired = []
    now = time.time()
    with _LOCK:
        # Re-read inside the lock: the background thread and a manual
        # "check now" can race on the same file, and without this re-read
        # both would mark (and announce) the same alert twice.
        alerts = _load()
        for a in alerts:
            if a.get("triggered"):
                continue
            p = (prices.get(a["coin"], {}) or {}).get(a.get("currency", "brl"))
            if p is None:
                continue
            if ((a["direction"] == "above" and p >= a["target"])
                    or (a["direction"] == "below" and p <= a["target"])):
                a["triggered"]   = True
                a["triggered_at"] = now
                a["last_price"]  = p
                fired.append(a)
        if fired:
            _save(alerts)
        for a in fired:
            msg = (f"💰 {a['coin'].upper()} is now "
                   f"{a['last_price']:,.2f} {a['currency'].upper()} — "
                   f"{a['direction']} {a['target']:,.2f} as you asked, sir.")
            _log(msg, player)
            _chime()
    return fired


def _chime() -> None:
    """Same three-tone bell as the timers — one dependency, one sound."""
    try:
        from actions.timer_action import _beep
        threading.Thread(target=_beep, daemon=True).start()
    except Exception:
        print("\a")


def _ensure_thread(player=None) -> None:
    """Start the watcher once; harmless if called again."""
    global _THREAD
    if _THREAD is not None and _THREAD.is_alive():
        return
    _THREAD = threading.Thread(target=_watch_loop, daemon=True)
    _THREAD.start()


def _watch_loop() -> None:
    while True:
        try:
            _check_alerts(_PLAYER)
        except Exception:
            pass
        time.sleep(_CHECK_SECS)


# ── cotação na hora: ações (B3 e exterior) e criptomoedas ────────────────────
_SIMBOLO_B3 = __import__("re").compile(r"^[A-Z]{4}\d{1,2}$")
_MOEDA = {"BRL": "R$", "USD": "US$", "EUR": "€", "GBP": "£"}


def _preco(valor: float, moeda: str) -> str:
    s = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{_MOEDA.get(moeda.upper(), moeda.upper() + ' ')}{' ' if moeda.upper() in _MOEDA else ''}{s}".strip()


def _variacao(atual: float, anterior: float | None) -> str:
    if not anterior:
        return ""
    v = (atual - anterior) / anterior * 100
    return f" ({'+' if v >= 0 else ''}{v:.1f}% no dia)".replace(".", ",")


def formatar_acao(simbolo: str, meta: dict) -> str:
    """Resposta do Yahoo Finance (chart.result[0].meta) → frase."""
    atual = meta.get("regularMarketPrice")
    if atual is None:
        raise ValueError("sem preço")
    nome = meta.get("shortName") or meta.get("longName") or simbolo
    return (f"{nome} ({simbolo.replace('.SA', '')}): {_preco(float(atual), meta.get('currency', 'USD'))}"
            f"{_variacao(float(atual), meta.get('chartPreviousClose') or meta.get('previousClose'))}")


def formatar_cripto(moeda_id: str, d: dict) -> str:
    """Resposta do CoinGecko simple/price (com 24h) → frase."""
    brl, usd = d.get("brl"), d.get("usd")
    partes = []
    if brl is not None:
        partes.append(_preco(float(brl), "BRL") + _variacao(float(brl), float(brl) / (1 + d.get("brl_24h_change", 0) / 100)
                                                         if d.get("brl_24h_change") is not None else None))
    if usd is not None:
        partes.append(_preco(float(usd), "USD"))
    if not partes:
        raise ValueError("sem preço")
    return f"{moeda_id.capitalize()}: " + " · ".join(partes)


def cotar(simbolos: str) -> str:
    """Cotação de uma ou mais ações/criptomoedas. Nunca levanta: erros viram texto."""
    import re
    import requests
    quer = [x.strip() for x in re.split(r"[,;]|\be\b|\band\b", str(simbolos or "")) if x.strip()]
    if not quer:
        return "Qual ação ou criptomoeda? Diga o código, como PETR4, AAPL ou bitcoin."
    linhas = []
    for bruto in quer[:6]:
        chave = bruto.lower()
        try:
            if chave in _ALIASES or chave in _ALIASES.values():
                cid = _ALIASES.get(chave, chave)
                r = requests.get("https://api.coingecko.com/api/v3/simple/price",
                                 params={"ids": cid, "vs_currencies": "usd,brl", "include_24hr_change": "true"}, timeout=8)
                r.raise_for_status()
                d = r.json().get(cid)
                if not d:
                    raise ValueError("não achei")
                d = {**d, "brl_24h_change": d.get("brl_24h_change")}
                linhas.append(formatar_cripto(cid, d))
                continue
            sim = bruto.upper().replace(" ", "")
            if _SIMBOLO_B3.match(sim):
                sim += ".SA"
            r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sim}",
                             params={"interval": "1d", "range": "1d"},
                             headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
            r.raise_for_status()
            res = (r.json().get("chart", {}).get("result") or [None])[0]
            if not res:
                raise ValueError("não achei")
            linhas.append(formatar_acao(sim, res["meta"]))
        except Exception as e:
            linhas.append(f"{bruto}: não consegui a cotação ({type(e).__name__})")
    return " | ".join(linhas)


def price_alert_action(parameters: dict, player=None, session_memory=None) -> str:
    global _PLAYER
    if player is not None:
        _PLAYER = player

    action   = str(parameters.get("action") or "create").strip().lower()
    coin     = str(parameters.get("coin") or "").strip().lower()
    direction = str(parameters.get("direction") or "above").strip().lower()
    target   = parameters.get("target")
    currency = str(parameters.get("currency") or "brl").strip().lower()
    index    = parameters.get("alert_index")

    if action in ("quote", "cotacao", "price"):
        return cotar(parameters.get("symbol") or parameters.get("coin") or "")

    if action == "create":
        coin = _ALIASES.get(coin, coin)
        if not coin:
            msg = "Sir, which coin should I watch?"
            _log(msg, player)
            return msg
        if direction not in ("above", "below"):
            direction = "above"
        if currency not in ("brl", "usd"):
            currency = "brl"
        try:
            target = float(target)
        except (TypeError, ValueError):
            target = None
        if not target or target <= 0:
            msg = ("Sir, at what price? Tell me the value and whether it "
                   "should be above or below.")
            _log(msg, player)
            return msg
        alerts = _load()
        # one live alert per coin+direction+currency — replace the old one
        alerts = [a for a in alerts
                  if not (a["coin"] == coin and a["direction"] == direction
                          and a["currency"] == currency
                          and not a.get("triggered"))]
        alerts.append({
            "coin": coin, "direction": direction, "target": target,
            "currency": currency, "created_at": time.time(),
            "triggered": False,
        })
        _save(alerts)
        _ensure_thread(player)
        msg = (f"Watching {coin}, sir — I'll chime when it goes "
               f"{direction} {target:,.2f} {currency.upper()}.")
        _log(f"alert: {coin} {direction} {target} {currency}", player)
        return msg

    if action == "list":
        alerts = _load()
        if not alerts:
            msg = "Sir, there are no price alerts."
            _log(msg, player)
            return msg
        lines = []
        for i, a in enumerate(alerts, 1):
            state = ("FIRED at "
                     f"{a.get('last_price', 0):,.2f}"
                     if a.get("triggered") else "watching")
            lines.append(f"{i}. {a['coin']} {a['direction']} "
                         f"{a['target']:,.2f} {a['currency'].upper()} ({state})")
        msg = "Sir, your price alerts: " + " ".join(lines)
        _log(f"listed {len(alerts)} alerts", player)
        return msg

    if action == "cancel":
        alerts = _load()
        if not alerts:
            msg = "Sir, there are no price alerts to cancel."
            _log(msg, player)
            return msg
        try:
            idx = int(index) - 1
        except (TypeError, ValueError):
            msg = "Sir, which alert number should I cancel?"
            _log(msg, player)
            return msg
        if not (0 <= idx < len(alerts)):
            msg = f"Sir, alert {index} doesn't exist — there are {len(alerts)}."
            _log(msg, player)
            return msg
        removed = alerts.pop(idx)
        _save(alerts)
        msg = (f"Cancelled, sir: {removed['coin']} "
               f"{removed['direction']} {removed['target']:,.2f}.")
        _log(f"cancelled alert #{index}", player)
        return msg

    if action == "check":
        fired = _check_alerts(player)
        _ensure_thread(player)
        if not fired:
            pending = [a for a in _load() if not a.get("triggered")]
            if not pending:
                msg = "Sir, there is nothing being watched right now."
            else:
                msg = ("Nothing has fired yet, sir. Still watching: "
                       + pending_summary())
        else:
            a = fired[-1]
            msg = (f"{a['coin'].upper()} just crossed to "
                   f"{a['last_price']:,.2f} {a['currency'].upper()}, sir.")
        _log(msg, player)
        return msg

    msg = ("Sir, I can create an alert (coin, above/below, target, BRL/USD), "
           "list them, check them now, or cancel one by number.")
    _log(msg, player)
    return msg


def _log(message: str, player=None) -> None:
    print(f"[PriceAlert] {message}")
    if player:
        try:
            player.write_log(f"NEXUS: {message}")
        except Exception:
            pass


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "price_alert",
    "description": (
        "Market prices. action=quote gives the price RIGHT NOW of stocks (B3 tickers like PETR4, "
        "VALE3, or foreign ones like AAPL) and crypto — symbol may list several ('PETR4, bitcoin'). "
        "Also watches crypto prices and notifies the user when a target is "
        "crossed. Checks every minute in the background and chimes when an "
        "alert fires. Actions: create (coin + above/below + target price in "
        "BRL or USD), list, check (check right now), cancel (by number). "
        "Coins: bitcoin, ethereum, solana, dogecoin, cardano, ripple…"
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["quote", "create", "list", "check", "cancel"],
                "description": "What to do with the price alerts"
            },
            "coin": {
                "type": "STRING",
                "description": "Coin to watch (e.g. bitcoin, ethereum, btc, eth)"
            },
            "symbol": {
                "type": "STRING",
                "description": "For quote: ticker(s) or coin name(s), e.g. 'PETR4', 'AAPL', 'bitcoin, ethereum'"
            },
            "direction": {
                "type": "STRING",
                "enum": ["above", "below"],
                "description": "Fire when the price goes above or below the target"
            },
            "target": {
                "type": "NUMBER",
                "description": "Target price (for create)"
            },
            "currency": {
                "type": "STRING",
                "enum": ["brl", "usd"],
                "description": "Currency of the target price (default brl)"
            },
            "alert_index": {
                "type": "NUMBER",
                "description": "Alert number to cancel (for cancel)"
            },
        },
        "required": ["action"]
    },
    "handler": price_alert_action,
}
