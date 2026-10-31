"""Everyday Tools — the small things a real assistant should do instantly.

Calculator (with percentages), date countdowns, world clock, dice/coins/
random picks and a password generator. 100% offline, stdlib only —
expressions are evaluated through a whitelisted AST walker, never eval().
"""

import ast
import math
import random
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo
from core.protecao import engolida as _engolida

_ZONES = {
    # EN + PT (o assistente fala com brasileiro, depois normaliza acentos)
    "sao paulo": "America/Sao_Paulo", "new york": "America/New_York",
    "nova york": "America/New_York", "london": "Europe/London",
    "londres": "Europe/London", "lisbon": "Europe/Lisbon",
    "lisboa": "Europe/Lisbon", "paris": "Europe/Paris",
    "berlim": "Europe/Berlin", "berlin": "Europe/Berlin",
    "moscow": "Europe/Moscow", "moscou": "Europe/Moscow",
    "dubai": "Asia/Dubai", "tokyo": "Asia/Tokyo", "toquio": "Asia/Tokyo",
    "beijing": "Asia/Shanghai", "pequim": "Asia/Shanghai",
    "shanghai": "Asia/Shanghai", "sydney": "Australia/Sydney",
    "los angeles": "America/Los_Angeles", "chicago": "America/Chicago",
    "india": "Asia/Kolkata", "mumbai": "Asia/Kolkata",
    "nova delhi": "Asia/Kolkata", "roma": "Europe/Rome",
    "madri": "Europe/Madrid", "madrid": "Europe/Madrid",
    "rome": "Europe/Rome", "inglaterra": "Europe/London",
    "brasil": "America/Sao_Paulo", "brazil": "America/Sao_Paulo",
    "brasilia": "America/Sao_Paulo",
}


def _noaccents(text: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", text)
                   if unicodedata.category(c) != "Mn")


# ── calculator ────────────────────────────────────────────────────────────────

def _prepare(expr: str) -> str:
    """Portuguese/English sugar → plain arithmetic."""
    e = expr.strip().lower()
    e = e.replace("x", "*").replace(",", ".")
    e = e.replace("elevado a", "**").replace("mais", "+").replace("menos", "-")
    e = e.replace("vezes", "*").replace("dividido por", "/")
    e = e.replace("over", "/").replace("plus", "+").replace("minus", "-")
    e = e.replace("times", "*").replace("percent", "%")
    # "15% de 240" → "(15/100)*240"  |  "80 + 15%" → "80*(1+15/100)"
    import re
    m = re.fullmatch(r"(.+?)\s*([+\-])\s*([\d.]+)\s*%", e)
    if m:                                   # X + N%  (de X mesmo)
        return f"({m.group(1)})*(1{m.group(2)}{m.group(3)}/100)"
    e = re.sub(r"([\d.]+)\s*%\s*(?:de|of)\s*", r"(\1/100)*", e)
    e = re.sub(r"([\d.]+)\s*%", r"(\1/100)", e)
    return e


def _eval_node(node):
    """Whitelisted AST evaluation — no eval(), no names, no calls."""
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp):
        a, b = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, ast.Add): return a + b
        if isinstance(node.op, ast.Sub): return a - b
        if isinstance(node.op, ast.Mult): return a * b
        if isinstance(node.op, ast.Div):
            if b == 0: raise ValueError("division by zero")
            return a / b
        if isinstance(node.op, ast.Pow): return a ** b
        if isinstance(node.op, ast.Mod): return a % b
        if isinstance(node.op, ast.FloorDiv): return a // b
    if isinstance(node, ast.UnaryOp):
        v = _eval_node(node.operand)
        if isinstance(node.op, ast.USub): return -v
        if isinstance(node.op, ast.UAdd): return v
    raise ValueError("unsupported expression")


def _format(v: float) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return f"{v:.4f}".rstrip("0").rstrip(".")


def calc(expr: str) -> dict:
    prepared = _prepare(expr)
    tree = ast.parse(prepared, mode="eval")
    value = _eval_node(tree)
    return {"expression": expr.strip(), "prepared": prepared,
            "result": _format(value)}


# ── dates ─────────────────────────────────────────────────────────────────────

def _parse_date(text: str) -> date:
    t = text.strip().lower()
    today = date.today()
    fmts = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m", "%d-%m",
            "%d de %b", "%d %b", "%d %B"]
    import locale  # nomes de mês em inglês
    for f in fmts:
        try:
            d = datetime.strptime(t, f).date()
            if d.year == 1900:
                d = d.replace(year=today.year)
                if d < today:
                    d = d.replace(year=today.year + 1)
            return d
        except ValueError:
            continue
    raise ValueError(f"couldn't read the date '{text}' — try 25/12 or "
                      "2026-12-25")


def date_diff(target: str, since: str = None) -> dict:
    tgt = _parse_date(target)
    ref = _parse_date(since) if since else date.today()
    days = (tgt - ref).days
    if days >= 0:
        return {"target": tgt.strftime("%d/%m/%Y"), "days": days,
                "direction": "until"}
    return {"target": tgt.strftime("%d/%m/%Y"), "days": -days,
            "direction": "since"}


# ── world clock ───────────────────────────────────────────────────────────────

def world_time(place: str) -> dict:
    p = place.strip()
    key = _noaccents(p.lower())            # para o mapa de aliases
    tz_name = _ZONES.get(key)
    if not tz_name and "/" in p:
        tz_name = p                        # IANA direto: preserva maiúsculas
    if not tz_name:
        raise ValueError(f"unknown place '{place}'")
    try:
        now = datetime.now(ZoneInfo(tz_name))
    except Exception:
        raise ValueError(f"unknown timezone '{tz_name}'")
    return {"place": place.strip().title(), "zone": tz_name,
            "time": now.strftime("%H:%M"), "date": now.strftime("%d/%m")}


# ── random ────────────────────────────────────────────────────────────────────

def random_pick(kind: str, low=None, high=None, options=None) -> dict:
    if kind == "coin":
        return {"result": random.choice(["heads", "tails"])}
    if kind == "dice":
        n, m = 1, 6
        if isinstance(low, str) and "d" in low.lower():
            a, b = low.lower().split("d", 1)
            n, m = int(a or 1), int(b or 6)
        elif isinstance(low, (int, float)):
            n, m = int(low), int(high or 6)
        rolls = [random.randint(1, m) for _ in range(max(1, min(n, 20)))]
        return {"result": f"{sum(rolls)}", "rolls": rolls,
                "detail": f"{n}d{m}: {rolls}"}
    if kind == "number":
        lo = int(low or 1)
        hi = int(high or 100)
        if hi < lo: lo, hi = hi, lo
        return {"result": str(random.randint(lo, hi)),
                "detail": f"between {lo} and {hi}"}
    if kind == "choice" and options:
        opts = [o.strip() for o in str(options).split(",") if o.strip()]
        if len(opts) < 2:
            raise ValueError("give me at least two options, comma separated")
        return {"result": random.choice(opts), "detail": f"of {opts}"}
    raise ValueError("unknown random kind")


# ── password ───────────────────────────────────────────────────────────────────

def make_password(length: int = 16) -> dict:
    import string
    n = max(8, min(int(length or 16), 32))
    alphabet = string.ascii_letters + string.digits + "!@#$%&*+-_=?"
    rng = random.SystemRandom()
    pw = "".join(rng.choice(alphabet) for _ in range(n))
    classes = sum([any(c.islower() for c in pw),
                   any(c.isupper() for c in pw),
                   any(c.isdigit() for c in pw),
                   any(c in "!@#$%&*+-_=?" for c in pw)])
    bits = round(n * math.log2(len(alphabet)))
    rating = ("strong" if classes == 4 and n >= 16 else
              "good" if classes >= 3 and n >= 12 else "weak")
    return {"password": pw, "length": n,
            "entropy": f"~{bits} bits", "rating": rating}


# ── handler ──────────────────────────────────────────────────────────────────

def everyday_tools_action(parameters: dict, player=None, session_memory=None) -> str:
    action = str(parameters.get("action") or "").strip().lower()

    try:
        if action == "calc":
            r = calc(str(parameters.get("expression") or ""))
            msg = f"Sir, {_format(r['result']) if isinstance(r['result'], float) else r['result']}."
            msg = f"Sir, {r['result']}."
            _log(f"calc: {r['expression']} = {r['result']}", player)
            return msg

        if action == "date":
            r = date_diff(str(parameters.get("target") or ""),
                          parameters.get("since"))
            word = "until" if r["direction"] == "until" else "since"
            d = "today" if not parameters.get("since") else "that date"
            msg = (f"Sir, {r['days']} days {word} {r['target']}, counting "
                   f"from {d}.")
            _log(f"date: {r['target']} → {r['days']} days {word}", player)
            return msg

        if action == "time":
            r = world_time(str(parameters.get("place") or "sao paulo"))
            msg = f"Sir, it's {r['time']} in {r['place']} ({r['date']})."
            _log(f"time: {r['place']} {r['time']}", player)
            return msg

        if action == "random":
            r = random_pick(str(parameters.get("kind") or "").strip().lower(),
                            parameters.get("low"), parameters.get("high"),
                            parameters.get("options"))
            extra = f" ({r['detail']})" if r.get("detail") else ""
            msg = f"Sir, {r['result']}{extra}."
            _log(f"random: {r['result']}", player)
            return msg

        if action == "password":
            r = make_password(int(parameters.get("length", 16)))
            msg = (f"Sir, password: {r['password']} — {r['length']} chars, "
                   f"{r['entropy']}, {r['rating']}.")
            _log("password generated (not logged)", player)
            return msg

        msg = ("Sir, I can: calculate (with percentages), count days to a "
               "date, tell the time anywhere, roll dice or flip a coin, pick "
               "randomly, and generate strong passwords.")
        _log(msg, player)
        return msg

    except ValueError as e:
        msg = f"Sir, {e}."
        _log(msg, player)
        return msg


def _log(message: str, player=None) -> None:
    print(f"[EverydayTools] {message}")
    if player:
        try:
            player.write_log(f"NEXUS: {message}")
        except Exception:
            _engolida("actions/everyday_tools.py:262")


TOOL = {
    "name": "everyday_tools",
    "description": (
        "Daily-life utilities: smart calculator with percentages "
        "('15% of 240', '80 + 15%'), date countdown ('days until 25/12'), "
        "world clock ('what time is it in Tokyo'), random (dice, coin, "
        "number range, pick from options) and strong password generation. "
        "All offline and instant."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["calc", "date", "time", "random", "password"],
                "description": "calc: math expression; date: countdown to a "
                               "target date; time: clock of a place; random: "
                               "dice/coin/number/choice; password: generate"
            },
            "expression": {
                "type": "STRING",
                "description": "Math expression, e.g. '15% de 240', "
                               "'(12+8)*3', '2**10'"
            },
            "target": {
                "type": "STRING",
                "description": "Date for countdown: '25/12', '2027-03-01'"
            },
            "since": {
                "type": "STRING",
                "description": "Optional start date for the count"
            },
            "place": {
                "type": "STRING",
                "description": "City/zone for the clock: 'tokyo', 'lisboa', "
                               "'America/New_York'"
            },
            "kind": {
                "type": "STRING",
                "enum": ["dice", "coin", "number", "choice"],
                "description": "Random kind"
            },
            "low": {
                "type": "STRING",
                "description": "Dice count or number-range minimum ('2d6' "
                               "for dice)"
            },
            "high": {
                "type": "STRING",
                "description": "Dice sides or number-range maximum"
            },
            "options": {
                "type": "STRING",
                "description": "Comma-separated options for 'choice'"
            },
            "length": {
                "type": "NUMBER",
                "description": "Password length (8-32, default 16)"
            },
        },
        "required": ["action"]
    },
    "handler": everyday_tools_action,
}
