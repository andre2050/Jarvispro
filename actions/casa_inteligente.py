"""Casa inteligente — o NEXUS liga luz, abre cortina, ajusta o ar e muito mais (NEXUS Ultra 2026 2.1).

    "acende a luz da sala"            "apaga todas as luzes"        "abre a cortina do quarto"
    "põe o ar em 22 graus"            "luz da sala em 40 por cento" "a porta está trancada?"
    "ativa a cena cinema"             "tranca a porta da frente"    "destranca a porta" (pede confirmação)

Funciona com dois tipos de ligação, os dois configurados por VOCÊ em config/casa.json:

  1. Home Assistant (recomendado): uma central que conversa com Tuya, Philips Hue, Sonoff, Zigbee, Alexa,
     Google Home e centenas de outras marcas. O NEXUS usa a API oficial dele.
  2. Webhooks: um endereço para ligar e outro para desligar (IFTTT, Tuya Smart Life via HA, Shelly etc.).

Segurança — o que foi pensado:
  • Quem escolhe o endereço é o arquivo de configuração, nunca o modelo: a IA só diz "qual aparelho" e "qual
    ação". Ela não consegue mandar o NEXUS acessar outro site.
  • O token do Home Assistant não é impresso, não vai para o modelo e não vai para o GitHub
    (config/casa.json está na lista de exclusão do preparar_publicacao.py).
  • Só tipos de aparelho conhecidos (luz, tomada, ventilador, cortina, ar, fechadura, cena, script).
  • Aparelhos marcados como sensíveis (fechaduras, portão/garagem, scripts) pedem CONFIRMAÇÃO NA TELA para
    abrir/destrancar/ligar — um clique seu, que o modelo não consegue forjar. Fechar e trancar nunca pedem.
  • O pedido não segue redirecionamentos (para o token não ser enviado a outro endereço).
  • Depois de ligar/desligar, o NEXUS pergunta ao aparelho se ele realmente mudou; se não mudou, avisa.

Não foi testado com os seus aparelhos de verdade — veja LEIA-ME 2.1 para configurar e testar.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
_CONFIG = _BASE / "config" / "casa.json"
_KEYS = _BASE / "config" / "api_keys.json"
_LOCK = threading.RLock()

TIMEOUT_S = 8
MAX_RESPOSTA = 2 * 1024 * 1024
MAX_APARELHOS = 200
_ESPERA = 0.7                       # segundos até conferir se o aparelho mudou

# tipo de aparelho → ações permitidas e o serviço do Home Assistant que cada uma chama
_SERVICOS: dict[str, dict[str, str]] = {
    "light":         {"on": "turn_on", "off": "turn_off", "toggle": "toggle", "set_brightness": "turn_on"},
    "switch":        {"on": "turn_on", "off": "turn_off", "toggle": "toggle"},
    "fan":           {"on": "turn_on", "off": "turn_off", "toggle": "toggle"},
    "input_boolean": {"on": "turn_on", "off": "turn_off", "toggle": "toggle"},
    "cover":         {"open": "open_cover", "close": "close_cover", "on": "open_cover", "off": "close_cover"},
    "climate":       {"on": "turn_on", "off": "turn_off", "set_temperature": "set_temperature"},
    "lock":          {"lock": "lock", "unlock": "unlock"},
    "scene":         {"on": "turn_on"},
    "script":        {"on": "turn_on"},
}
DOMINIOS = tuple(_SERVICOS)
_SEMPRE_SENSIVEIS = {"lock", "script"}
# com aparelho sensível, estas ações pedem confirmação na tela (as "seguras" — desligar, fechar, trancar — não)
_PEDEM_CONFIRMACAO = {"on", "open", "unlock", "toggle", "set_brightness", "set_temperature"}
_ALIAS_ACAO = {"activate": "on", "turn_on": "on", "turn_off": "off", "run": "on", "ativar": "on"}
_ESTADO_ESPERADO = {
    ("light", "on"): ("on",), ("light", "off"): ("off",), ("light", "set_brightness"): ("on",),
    ("switch", "on"): ("on",), ("switch", "off"): ("off",),
    ("fan", "on"): ("on",), ("fan", "off"): ("off",),
    ("input_boolean", "on"): ("on",), ("input_boolean", "off"): ("off",),
    ("lock", "lock"): ("locked", "locking"), ("lock", "unlock"): ("unlocked", "unlocking", "open"),
    ("cover", "open"): ("open", "opening"), ("cover", "close"): ("closed", "closing"),
    ("cover", "on"): ("open", "opening"), ("cover", "off"): ("closed", "closing"),
}
_ENTIDADE = re.compile(r"^([a-z_]+)\.([a-z0-9_]+)$")
_GRUPOS = {                        # "apaga todas as luzes" → todos os aparelhos desse tipo, exceto sensíveis
    "luzes": "light", "luz": "light", "lampadas": "light", "lampada": "light",
    "ventiladores": "fan", "ventilador": "fan",
    "cortinas": "cover", "persianas": "cover", "cortina": "cover", "persiana": "cover",
    "tomadas": "switch",
}
_ARTIGOS = {"a", "o", "as", "os", "da", "de", "do", "das", "dos", "na", "no", "em", "todas", "todos", "toda", "todo"}


class Erro(Exception):
    """Mensagem já pronta para o usuário."""


# ── texto ────────────────────────────────────────────────────────────────────

def _norm(t) -> str:
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t)).strip()


def _limpo(t, limite=60) -> str:
    """Texto vindo de fora (nome no Home Assistant): sem caracteres de controle e com tamanho limitado."""
    return re.sub(r"[\x00-\x1f\x7f]", " ", str(t or "")).strip()[:limite]


# ── configuração ─────────────────────────────────────────────────────────────

def _ler() -> dict:
    try:
        d = json.loads(_CONFIG.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _gravar(cfg: dict) -> None:
    """Grava inteiro ou não grava (arquivo temporário + troca no fim)."""
    _CONFIG.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=_CONFIG.name + ".", suffix=".tmp", dir=str(_CONFIG.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _CONFIG)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _url_valida(url) -> str:
    """http(s) com endereço e sem usuário:senha embutido. Devolve '' se for inválida."""
    try:
        u = urllib.parse.urlsplit(str(url or "").strip())
    except ValueError:
        return ""
    if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password:
        return ""
    return str(url).strip().rstrip("/")


def _token(cfg: dict) -> str:
    t = os.environ.get("NEXUS_HA_TOKEN", "").strip()
    if not t:
        try:
            t = str(json.loads(_KEYS.read_text(encoding="utf-8")).get("home_assistant_token") or "").strip()
        except (OSError, ValueError, AttributeError):
            t = ""
    if not t:
        t = str((cfg.get("home_assistant") or {}).get("token") or "").strip()
    return t


def _aparelhos(cfg: dict) -> dict[str, dict]:
    d = cfg.get("devices")
    return {str(k): v for k, v in d.items() if isinstance(v, dict)} if isinstance(d, dict) else {}


def _dominio(ap: dict) -> str:
    m = _ENTIDADE.match(str(ap.get("entity_id") or ""))
    return m.group(1) if m and m.group(1) in _SERVICOS else ""


def _sensivel(ap: dict) -> bool:
    return bool(ap.get("sensitive")) or _dominio(ap) in _SEMPRE_SENSIVEIS


# ── HTTP (sem redirecionamento, com limite de tempo e de tamanho) ────────────

class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_ABRIDOR = urllib.request.build_opener(_SemRedirecionar)


def _http(metodo: str, url: str, token: str = "", corpo: dict | None = None, rotulo: str = "O Home Assistant"):
    """(status, dados JSON ou None). Levanta Erro com mensagem amigável."""
    cab = {"Accept": "application/json"}
    if token:
        cab["Authorization"] = "Bearer " + token
    dados = None
    if corpo is not None:
        dados = json.dumps(corpo).encode()
        cab["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=dados, headers=cab, method=metodo)
    host = urllib.parse.urlsplit(url).hostname or "?"
    try:
        with _ABRIDOR.open(req, timeout=TIMEOUT_S) as r:
            bruto = r.read(MAX_RESPOSTA + 1)
            status = r.status
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise Erro(f"{rotulo} recusou o acesso: o token está errado, vencido ou sem permissão.")
        if e.code == 404:
            raise Erro(f"{rotulo} não encontrou esse endereço ou aparelho (verifique o entity_id/URL).")
        if 300 <= e.code < 400:
            raise Erro("O endereço configurado redireciona para outro lugar; por segurança eu não sigo.")
        raise Erro(f"O servidor respondeu com erro {e.code}.")
    except (urllib.error.URLError, TimeoutError, OSError):
        raise Erro(f"Não consegui falar com {host}. Confira se está ligado, na mesma rede e com o endereço certo.")
    if len(bruto) > MAX_RESPOSTA:
        raise Erro("A resposta do servidor veio grande demais; ignorei.")
    try:
        return status, json.loads(bruto) if bruto.strip() else None
    except ValueError:
        return status, None


def _ha(cfg: dict) -> tuple[str, str]:
    url = _url_valida((cfg.get("home_assistant") or {}).get("url"))
    if not url:
        raise Erro("O Home Assistant ainda não está configurado. Use a ação setup_help para ver como.")
    token = _token(cfg)
    if not token:
        raise Erro("Falta o token do Home Assistant. Use a ação setup_help para ver onde colocar.")
    return url, token


# ── achar o aparelho ─────────────────────────────────────────────────────────

def _achar(cfg: dict, pedido) -> tuple[str, dict]:
    aps = _aparelhos(cfg)
    if not aps:
        raise Erro("Ainda não há aparelhos cadastrados. Use discover (Home Assistant) ou add_device.")
    chave = _norm(pedido)
    if not chave:
        raise Erro("Qual aparelho? Diga o nome, por exemplo: luz da sala.")

    def nomes(nome, ap):
        return {_norm(nome)} | {_norm(a) for a in ap.get("aliases", []) if isinstance(a, str)}

    exatos = [(n, a) for n, a in aps.items() if chave in nomes(n, a)]
    if len(exatos) == 1:
        return exatos[0]
    palavras = [p for p in chave.split() if p not in _ARTIGOS] or chave.split()
    def casa(p, n, a):
        return any(w.startswith(p) or (len(w) >= 3 and p.startswith(w))
                   for x in nomes(n, a) for w in x.split())

    cand = [(n, a) for n, a in aps.items() if all(casa(p, n, a) for p in palavras)]
    if len(cand) == 1:
        return cand[0]
    if not cand:
        raise Erro(f"Não achei “{_limpo(pedido)}”. Aparelhos que conheço: " + ", ".join(list(aps)[:15]) + ".")
    raise Erro("Qual deles? " + ", ".join(n for n, _ in cand[:8]) + ".")


def _alvos_do_grupo(cfg: dict, pedido, acao: str) -> list[tuple[str, dict]]:
    """“todas as luzes” → todos os aparelhos do tipo, menos os sensíveis."""
    palavras = [p for p in _norm(pedido).split() if p not in _ARTIGOS]
    tipos = {_GRUPOS[p] for p in palavras if p in _GRUPOS}
    if len(palavras) != 1 or len(tipos) != 1:
        return []
    tipo = tipos.pop()
    if acao not in _SERVICOS[tipo]:
        return []
    return [(n, a) for n, a in _aparelhos(cfg).items() if _dominio(a) == tipo and not _sensivel(a)]


# ── executar ─────────────────────────────────────────────────────────────────

def _corpo(ap: dict, acao: str, p: dict) -> dict:
    corpo = {"entity_id": ap["entity_id"]}
    if acao == "set_brightness":
        try:
            n = int(float(p.get("value")))
        except (TypeError, ValueError):
            raise Erro("Diga o brilho de 0 a 100 por cento.")
        if not 0 <= n <= 100:
            raise Erro("O brilho precisa estar entre 0 e 100 por cento.")
        corpo["brightness_pct"] = n
    elif acao == "set_temperature":
        try:
            t = float(str(p.get("value")).replace(",", "."))
        except (TypeError, ValueError):
            raise Erro("Diga a temperatura em graus, por exemplo 22.")
        if not 10 <= t <= 35:
            raise Erro("Por segurança só aceito temperaturas entre 10 e 35 graus.")
        corpo["temperature"] = t
    return corpo


def _executar_ha(cfg: dict, nome: str, ap: dict, acao: str, p: dict) -> str:
    dom = _dominio(ap)
    servico = _SERVICOS.get(dom, {}).get(acao)
    if not dom or not servico:
        raise Erro(f"“{nome}” não aceita a ação {acao}.")
    corpo = _corpo(ap, acao, p)
    url, token = _ha(cfg)
    esperado = _ESTADO_ESPERADO.get((dom, acao))
    if acao == "toggle":                      # só dá para saber o resultado esperado olhando antes
        try:
            _, antes = _http("GET", f"{url}/api/states/{ap['entity_id']}", token)
            esperado = {"on": ("off",), "off": ("on",)}.get(str((antes or {}).get("state")))
        except Erro:
            esperado = None
    _http("POST", f"{url}/api/services/{dom}/{servico}", token, corpo)
    if acao == "set_temperature":
        time.sleep(_ESPERA)
        try:
            _, st = _http("GET", f"{url}/api/states/{ap['entity_id']}", token)
            atual = ((st or {}).get("attributes") or {}).get("temperature")
        except Erro:
            return f"[unverified] Enviei o comando para {nome}, mas não consegui conferir."
        if isinstance(atual, (int, float)) and abs(float(atual) - corpo["temperature"]) < 0.51:
            return f"[done] {nome} ajustado para {atual:g}°."
        return f"[unverified] Enviei o comando, mas {nome} mostra {atual if atual is not None else 'sem'} de temperatura ajustada."
    if not esperado:
        return f"[done] Comando enviado para {nome} (o Home Assistant recebeu; esse tipo de aparelho não informa o resultado)."
    time.sleep(_ESPERA)
    try:
        _, st = _http("GET", f"{url}/api/states/{ap['entity_id']}", token)
    except Erro:
        return f"[unverified] Enviei o comando para {nome}, mas não consegui conferir se ele mudou."
    estado = str((st or {}).get("state", ""))
    if estado in esperado:
        extra = f" em {corpo['brightness_pct']}%" if "brightness_pct" in corpo else ""
        return f"[done] {nome}: {_estado_pt(estado)}{extra}."
    return f"[unverified] Enviei o comando, mas {nome} continua {_estado_pt(estado)}. Pode estar offline ou sem resposta."


def _estado_pt(e: str) -> str:
    return {"on": "ligado", "off": "desligado", "locked": "trancado", "unlocked": "destrancado",
            "open": "aberto", "closed": "fechado", "opening": "abrindo", "closing": "fechando",
            "locking": "trancando", "unlocking": "destrancando", "unavailable": "indisponível",
            "unknown": "desconhecido"}.get(e, e)


def _executar_webhook(nome: str, ap: dict, acao: str) -> str:
    hooks = ap.get("webhook") if isinstance(ap.get("webhook"), dict) else {}
    url = _url_valida(hooks.get(acao))
    if not url:
        raise Erro(f"“{nome}” não tem endereço configurado para a ação {acao}.")
    metodo = "POST" if str(hooks.get("method", "GET")).upper() == "POST" else "GET"
    _http(metodo, url, rotulo="O endereço do webhook")
    return f"[unverified] Enviei “{acao}” para {nome}. Esse tipo de ligação não confirma o resultado."


def _acionar(cfg: dict, nome: str, ap: dict, acao: str, p: dict) -> str:
    try:
        if ap.get("entity_id"):
            return _executar_ha(cfg, nome, ap, acao, p)
        if ap.get("webhook"):
            return _executar_webhook(nome, ap, acao)
        raise Erro(f"“{nome}” está sem entity_id nem webhook.")
    except Erro as e:
        return f"[failed] {e}"


def _comando(p: dict, acao: str) -> str:
    cfg = _ler()
    acao = _ALIAS_ACAO.get(acao, acao)
    pedido = p.get("device")
    # “todas as luzes”: liga/desliga/abre/fecha tudo do tipo, sem os sensíveis
    if acao in ("on", "off", "open", "close") and _norm(pedido) and not any(
            _norm(pedido) == _norm(n) for n in _aparelhos(cfg)):
        grupo = _alvos_do_grupo(cfg, pedido, acao)
        if grupo:
            with ThreadPoolExecutor(max_workers=6) as ex:
                res = list(ex.map(lambda na: _acionar(cfg, na[0], na[1], acao, p), grupo))
            ok = sum(r.startswith("[done]") for r in res)
            verbo = {"on": "ligados", "off": "desligados", "open": "abertos", "close": "fechados"}[acao]
            if ok == len(grupo):
                return f"[done] {ok} aparelhos {verbo}."
            return f"[unverified] {ok} de {len(grupo)} {verbo}; os outros não confirmaram (offline?)."
    try:
        nome, ap = _achar(cfg, pedido)
    except Erro as e:
        return f"[failed] {e}"
    dom = _dominio(ap)
    if ap.get("entity_id") and dom and acao not in _SERVICOS[dom]:
        return f"[failed] “{nome}” ({dom}) não aceita a ação {acao}. Aceita: {', '.join(_SERVICOS[dom])}."
    if _sensivel(ap) and acao in _PEDEM_CONFIRMACAO:
        from core import confirm
        if confirm.pending_title():
            return "[failed] Já existe uma confirmação na tela. Peça ao usuário para responder a ela primeiro."
        return confirm.request(
            "casa_inteligente", f"Casa: {acao} — {nome}",
            f"Aparelho sensível: {nome}\nAção: {acao}\nConfirme só se foi você quem pediu.",
            lambda c=cfg, n=nome, a=ap, ac=acao, pp=dict(p): _acionar(c, n, a, ac, pp))
    return _acionar(cfg, nome, ap, acao, p)


def _status(p: dict) -> str:
    cfg = _ler()
    try:
        nome, ap = _achar(cfg, p.get("device"))
    except Erro as e:
        return f"[failed] {e}"
    if not ap.get("entity_id"):
        return f"[failed] “{nome}” usa webhook, que não informa o estado."
    try:
        url, token = _ha(cfg)
        _, st = _http("GET", f"{url}/api/states/{ap['entity_id']}", token)
    except Erro as e:
        return f"[failed] {e}"
    st = st if isinstance(st, dict) else {}
    attrs = st.get("attributes") if isinstance(st.get("attributes"), dict) else {}
    extra = []
    if isinstance(attrs.get("brightness"), (int, float)):
        extra.append(f"brilho {round(attrs['brightness'] / 255 * 100)}%")
    if isinstance(attrs.get("current_temperature"), (int, float)):
        extra.append(f"temperatura {attrs['current_temperature']}°")
    if isinstance(attrs.get("temperature"), (int, float)):
        extra.append(f"ajustado para {attrs['temperature']}°")
    return f"[done] {nome}: {_estado_pt(str(st.get('state', 'desconhecido')))}" + (f" ({', '.join(extra)})" if extra else "") + "."


# ── cadastro ─────────────────────────────────────────────────────────────────

def _listar(_p: dict) -> str:
    aps = _aparelhos(_ler())
    if not aps:
        return "[done] Nenhum aparelho cadastrado. Use discover (Home Assistant) ou add_device."
    por_tipo: dict[str, list[str]] = {}
    for n, a in aps.items():
        por_tipo.setdefault(_dominio(a) or "webhook", []).append(n + (" 🔒" if _sensivel(a) else ""))
    return "[done] Aparelhos: " + "; ".join(f"{t}: {', '.join(v[:12])}" for t, v in por_tipo.items()) + "."


def _descobrir(_p: dict) -> str:
    cfg = _ler()
    try:
        url, token = _ha(cfg)
        _, estados = _http("GET", f"{url}/api/states", token)
    except Erro as e:
        return f"[failed] {e}"
    if not isinstance(estados, list):
        return "[failed] O Home Assistant respondeu algo que não entendi."
    with _LOCK:
        cfg = _ler()
        aps = _aparelhos(cfg)
        ja = {str(a.get("entity_id")) for a in aps.values()}
        usados = {_norm(n) for n in aps}
        novos: dict[str, int] = {}
        for est in estados:
            if not isinstance(est, dict):
                continue
            eid = str(est.get("entity_id") or "")
            m = _ENTIDADE.match(eid)
            if not m or m.group(1) not in _SERVICOS or eid in ja:
                continue
            attrs = est.get("attributes") if isinstance(est.get("attributes"), dict) else {}
            nome = _limpo(attrs.get("friendly_name")) or m.group(2).replace("_", " ")
            if _norm(nome) in usados:
                nome = f"{nome} ({m.group(2).replace('_', ' ')})"[:60]
            if _norm(nome) in usados or len(aps) >= MAX_APARELHOS:
                continue
            sens = m.group(1) in _SEMPRE_SENSIVEIS or (
                m.group(1) == "cover" and str(attrs.get("device_class")) in ("garage", "gate", "door"))
            aps[nome] = {"entity_id": eid, "sensitive": sens}
            usados.add(_norm(nome))
            novos[m.group(1)] = novos.get(m.group(1), 0) + 1
        if novos:
            cfg["devices"] = aps
            _gravar(cfg)
    if not novos:
        return f"[done] Nada novo para cadastrar ({len(aps)} aparelhos já conhecidos)."
    return ("[done] Cadastrei " + ", ".join(f"{n} {t}" for t, n in sorted(novos.items()))
            + ". Fechaduras, portões e scripts ficam como sensíveis (pedem confirmação na tela).")


def _adicionar(p: dict) -> str:
    nome = _limpo(p.get("device"))
    eid = str(p.get("entity_id") or "").strip().lower()
    if not nome or not _ENTIDADE.match(eid) or _ENTIDADE.match(eid).group(1) not in _SERVICOS:
        return ("[failed] Informe o nome e um entity_id válido, de um destes tipos: "
                + ", ".join(DOMINIOS) + " (ex.: light.sala).")
    with _LOCK:
        cfg = _ler()
        aps = _aparelhos(cfg)
        if len(aps) >= MAX_APARELHOS and nome not in aps:
            return f"[failed] Limite de {MAX_APARELHOS} aparelhos."
        aps[nome] = {"entity_id": eid, "sensitive": bool(p.get("sensitive"))}
        cfg["devices"] = aps
        _gravar(cfg)
    return f"[done] Cadastrei “{nome}” ({eid})" + (" como sensível." if aps[nome]["sensitive"] else ".")


def _remover(p: dict) -> str:
    with _LOCK:
        cfg = _ler()
        try:
            nome, _ = _achar(cfg, p.get("device"))
        except Erro as e:
            return f"[failed] {e}"
        aps = _aparelhos(cfg)
        aps.pop(nome, None)
        cfg["devices"] = aps
        _gravar(cfg)
    return f"[done] Removi “{nome}”."


_AJUDA = (
    "Para ligar o NEXUS à sua casa: 1) instale o Home Assistant (home-assistant.io) e adicione seus aparelhos "
    "lá; 2) no Home Assistant, abra seu perfil → Segurança → Tokens de acesso de longa duração → Criar token; "
    "3) no arquivo config/casa.json coloque o endereço, por exemplo "
    '{"home_assistant": {"url": "http://homeassistant.local:8123"}}; 4) coloque o token em config/api_keys.json '
    'como "home_assistant_token": "…" (nunca diga o token em voz alta); 5) peça “descobrir meus aparelhos”. '
    "Fechaduras, portões e scripts pedem confirmação na tela. Sem Home Assistant, dá para usar webhooks no "
    'casa.json: "devices": {"luz do quarto": {"webhook": {"on": "https://…", "off": "https://…"}}}.'
)


def _ajuda(_p: dict) -> str:
    if not _CONFIG.exists():
        try:
            _gravar({"home_assistant": {"url": "http://homeassistant.local:8123"}, "devices": {}})
        except OSError:
            pass
    return "[done] " + _AJUDA


_ACOES_COMANDO = ("on", "off", "toggle", "open", "close", "lock", "unlock", "set_brightness", "set_temperature")
_OUTRAS = {"status": _status, "list": _listar, "discover": _descobrir, "add_device": _adicionar,
           "remove_device": _remover, "setup_help": _ajuda}


def casa_inteligente(parameters: dict, player=None) -> str:
    p = parameters or {}
    acao = str(p.get("action") or "").strip().lower()
    acao = _ALIAS_ACAO.get(acao, acao)
    try:
        if acao in _ACOES_COMANDO:
            return _comando(p, acao)
        fn = _OUTRAS.get(acao)
        if fn is None:
            return f"[failed] Ação desconhecida: {acao or '(vazia)'}. Use: {', '.join(_ACOES_COMANDO + tuple(_OUTRAS))}."
        return fn(p)
    except Erro as e:
        return f"[failed] {e}"
    except OSError as e:
        return f"[failed] Problema com o arquivo de configuração: {e}"


TOOL = {
    "name": "casa_inteligente",
    "description": (
        "Smart home control through the user's own Home Assistant (or webhooks), configured in config/casa.json. "
        "Use for 'acende a luz da sala', 'apaga todas as luzes', 'abre a cortina', 'põe o ar em 22', 'luz da sala em "
        "40%', 'a porta está trancada?', 'ativa a cena cinema'. action: on, off, toggle, open, close, lock, unlock, "
        "set_brightness (value 0-100), set_temperature (value in °C), status, list; discover imports all devices from "
        "Home Assistant; add_device / remove_device; setup_help explains the one-time setup (read it to the user, never "
        "ask them to say a token aloud). device = the name the user says. Sensitive devices (locks, gates, scripts) "
        "ask for an on-screen confirmation before opening/unlocking/running — tell the user to confirm on the HUD "
        "and do not claim it was done. Results start with [done], [unverified] (command sent but the device did not "
        "confirm — say so) or [failed]."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": list(_ACOES_COMANDO) + list(_OUTRAS)},
            "device": {"type": "STRING", "description": "Device name as the user says it (e.g. 'luz da sala', 'todas as luzes')"},
            "value": {"type": "NUMBER", "description": "Brightness percent or temperature in °C"},
            "entity_id": {"type": "STRING", "description": "For add_device: Home Assistant entity, e.g. light.sala"},
            "sensitive": {"type": "BOOLEAN", "description": "For add_device: ask for confirmation before turning on/opening"},
        },
        "required": ["action"],
    },
    "handler": casa_inteligente,
}
