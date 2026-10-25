"""Mapas e rotas (NEXUS Ultra 2026 2.0).

    "como chego no aeroshopping de carro?"      → abre a rota no Google Maps (saída = onde você está)
    "quanto tempo de casa até o trabalho?"      → fala distância e tempo (se der para calcular)
    "farmácia aberta perto de mim"              → abre a busca no mapa
    "mostra o Cristo Redentor no mapa"          → abre o lugar

Abrir o mapa não precisa de chave nem de conta. A distância e o tempo vêm do OSRM + Nominatim
(públicos, sem chave) e valem para CARRO; a pé, de bicicleta e de transporte público o NEXUS abre
a rota no mapa (que calcula na hora) em vez de chutar um tempo.
"""
from __future__ import annotations

import webbrowser
from urllib.parse import quote, quote_plus

_MODOS = {"driving": "driving", "carro": "driving", "dirigindo": "driving", "drive": "driving",
          "walking": "walking", "a pe": "walking", "andando": "walking", "walk": "walking",
          "transit": "transit", "onibus": "transit", "transporte": "transit", "metro": "transit",
          "bicycling": "bicycling", "bicicleta": "bicycling", "bike": "bicycling"}
_NOME_MODO = {"driving": "de carro", "walking": "a pé", "transit": "de transporte público",
              "bicycling": "de bicicleta"}


def _modo(v: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", str(v or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c)).strip()
    return _MODOS.get(t, "driving")


def url_rota(destino: str, origem: str = "", modo: str = "driving") -> str:
    u = f"https://www.google.com/maps/dir/?api=1&destination={quote_plus(destino)}&travelmode={modo}"
    if origem:
        u += f"&origin={quote_plus(origem)}"
    return u


def url_busca(consulta: str) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(consulta)}"


def _geocodificar(lugar: str) -> tuple[float, float] | None:
    import requests
    r = requests.get("https://nominatim.openstreetmap.org/search",
                     params={"q": lugar, "format": "json", "limit": 1},
                     headers={"User-Agent": "NEXUS-Ultra-2026-assistente/2.0"}, timeout=8)
    r.raise_for_status()
    d = r.json()
    return (float(d[0]["lat"]), float(d[0]["lon"])) if d else None


def tempo_e_distancia(origem: str, destino: str) -> tuple[float, float]:
    """(km, minutos) de carro. Levanta exceção se não achar os lugares ou a rede falhar."""
    import requests
    a, b = _geocodificar(origem), _geocodificar(destino)
    if not a or not b:
        raise LookupError("não achei um dos lugares")
    r = requests.get(f"https://router.project-osrm.org/route/v1/driving/{a[1]},{a[0]};{b[1]},{b[0]}",
                     params={"overview": "false"}, timeout=10)
    r.raise_for_status()
    rota = r.json()["routes"][0]
    return rota["distance"] / 1000.0, rota["duration"] / 60.0


def _duracao(minutos: float) -> str:
    m = int(round(minutos))
    if m < 60:
        return f"{m} minutos"
    h, r = divmod(m, 60)
    return f"{h} h" + (f" {r} min" if r else "")


def mapas(parameters: dict, player=None) -> str:
    acao = str(parameters.get("action") or "route").strip().lower()
    destino = str(parameters.get("destination") or "").strip()
    origem = str(parameters.get("origin") or "").strip()
    consulta = str(parameters.get("query") or "").strip()
    modo = _modo(parameters.get("mode"))

    if acao in ("search", "nearby", "buscar", "place", "show"):
        q = consulta or destino
        if not q:
            return "O que procuro no mapa?"
        webbrowser.open(url_busca(q))
        return f"Abri o mapa com “{q}”."

    if not destino:
        return "Para onde? Diga o destino."
    texto = ""
    if origem and modo == "driving" and acao in ("time", "route", "duration"):
        try:
            km, mins = tempo_e_distancia(origem, destino)
            texto = f"{km:.0f} km, cerca de {_duracao(mins)} de carro, sem contar o trânsito de agora. "
        except Exception:
            texto = ""
    if acao in ("time", "duration") and not texto:
        # só pediu o tempo e não deu para calcular → mostra no mapa, que calcula na hora
        webbrowser.open(url_rota(destino, origem, modo))
        return (f"Não consegui calcular o tempo daqui; abri a rota {_NOME_MODO[modo]} para {destino} no mapa, "
                "que mostra o tempo com o trânsito de agora.")
    webbrowser.open(url_rota(destino, origem, modo))
    return f"{texto}Abri a rota {_NOME_MODO[modo]} até {destino} no mapa."


TOOL = {
    "name": "mapas",
    "description": (
        "Maps and directions. action=route (default) opens the route to destination in Google Maps "
        "(origin optional — when omitted the map starts from the user's location; mode = carro | a pé "
        "| transporte | bicicleta); action=time speaks distance and driving time between origin and "
        "destination; action=search opens a map search for query ('farmácia aberta perto de mim', "
        "'posto de gasolina'). Use for 'como chego em…', 'quanto tempo até…', 'o que tem perto…'."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "route | time | search (default route)"},
            "destination": {"type": "STRING", "description": "Where to go"},
            "origin": {"type": "STRING", "description": "Where from (optional)"},
            "mode": {"type": "STRING", "description": "carro | a pé | transporte | bicicleta"},
            "query": {"type": "STRING", "description": "For search: what to look for"},
        },
        "required": [],
    },
    "handler": mapas,
}
