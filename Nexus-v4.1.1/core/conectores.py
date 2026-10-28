"""core/conectores.py — conectores de casa e produtividade (NEXUS Ultra 2026 3.9).

Um catálogo de "receitas" prontas (Todoist, Trello, Home Assistant, IFTTT, ntfy, Discord) mais conectores seus. Você escolhe a receita e
preenche os dados UMA vez (token, lista, evento); depois é só "cria a tarefa X no Todoist" ou "ativa a cena cinema".
Segurança: quem escolhe o ENDEREÇO é a receita/sua configuração, nunca o modelo — o modelo só dá o texto/parâmetro. Só https (http apenas
para o Home Assistant na sua rede local), sem seguir redirecionamentos, sem endereços internos/loopback fora do Home Assistant, resposta
curta e marcada como dado de terceiros. Receitas que mexem no mundo real (IFTTT, cena de casa) pedem CONFIRMAR.
A configuração (com tokens) fica em config/conectores.json, fora do GitHub. Não testado com as contas reais — veja o aviso no LEIA-ME.
"""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import urllib.parse
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent.parent / "config" / "conectores.json"
MAX_RESPOSTA = 600
TIMEOUT_S = 10

# receita: url (com {campos}), metodo, headers, corpo (dict ou str), pede (campos que VOCÊ preenche ao criar), usa (campos que o pedido preenche)
RECEITAS = {
    "todoist": {"descricao": "criar tarefa no Todoist", "url": "https://api.todoist.com/rest/v2/tasks", "metodo": "POST",
                "headers": {"Authorization": "Bearer {token}"}, "corpo": {"content": "{texto}"}, "pede": ["token"], "usa": ["texto"], "confirmar": False},
    "trello": {"descricao": "criar cartão no Trello", "url": "https://api.trello.com/1/cards", "metodo": "POST",
               "query": {"idList": "{lista}", "key": "{chave}", "token": "{token}", "name": "{texto}"},
               "pede": ["lista", "chave", "token"], "usa": ["texto"], "confirmar": False},
    "ntfy": {"descricao": "mandar aviso para o celular (ntfy)", "url": "https://ntfy.sh/{topico}", "metodo": "POST",
             "corpo": "{texto}", "pede": ["topico"], "usa": ["texto"], "confirmar": False},
    "discord": {"descricao": "mensagem num canal do Discord (webhook)", "url": "{webhook}", "metodo": "POST",
                "corpo": {"content": "{texto}"}, "pede": ["webhook"], "usa": ["texto"], "confirmar": True, "dominio": "discord.com"},
    "ifttt": {"descricao": "disparar um applet do IFTTT", "url": "https://maker.ifttt.com/trigger/{evento}/with/key/{chave}", "metodo": "POST",
              "corpo": {"value1": "{texto}"}, "pede": ["evento", "chave"], "usa": ["texto"], "confirmar": True},
    "home_assistant_cena": {"descricao": "ativar uma cena do Home Assistant", "url": "{base}/api/services/scene/turn_on", "metodo": "POST",
                            "headers": {"Authorization": "Bearer {token}"}, "corpo": {"entity_id": "scene.{texto}"},
                            "pede": ["base", "token"], "usa": ["texto"], "confirmar": True, "lan": True},
}
_CAMPO = re.compile(r"\{(\w+)\}")


class ErroConector(Exception):
    pass


def _ler(arq: Path | None = None) -> dict:
    try:
        d = json.loads(Path(arq or ARQUIVO).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _gravar(d: dict, arq: Path | None = None) -> None:
    arq = Path(arq or ARQUIVO)
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        import os
        os.chmod(tmp, 0o600)
    except Exception:
        pass
    tmp.replace(arq)


def _nome(n: str) -> str:
    n = re.sub(r"[^a-z0-9_]+", "_", str(n or "").lower()).strip("_")[:30]
    if len(n) < 2:
        raise ErroConector("Dê um nome ao conector (letras e números).")
    return n


def adicionar(nome: str, receita: str, dados: dict, arq: Path | None = None) -> str:
    r = RECEITAS.get(receita)
    if not r:
        raise ErroConector("Receita desconhecida. Disponíveis: " + ", ".join(RECEITAS))
    faltam = [c for c in r["pede"] if not str((dados or {}).get(c, "")).strip()]
    if faltam:
        raise ErroConector("Faltam dados: " + ", ".join(faltam))
    limpos = {c: str(dados[c]).strip()[:300] for c in r["pede"]}
    if receita == "home_assistant_cena":
        limpos["base"] = limpos["base"].rstrip("/")
    cfg = _ler(arq)
    if len(cfg) >= 20 and _nome(nome) not in cfg:
        raise ErroConector("Já há 20 conectores; remova um.")
    cfg[_nome(nome)] = {"receita": receita, "dados": limpos}
    _gravar(cfg, arq)
    _url_final(r, limpos, {"texto": "x"}, checar_ip=False)      # valida o formato já na criação; o IP é checado ao enviar
    return _nome(nome)


def remover(nome: str, arq: Path | None = None) -> bool:
    cfg = _ler(arq)
    ok = cfg.pop(_nome(nome), None) is not None
    _gravar(cfg, arq)
    return ok


def listar(arq: Path | None = None) -> list[dict]:
    return [{"nome": n, "receita": c["receita"], "descricao": RECEITAS[c["receita"]]["descricao"],
             "confirmar": RECEITAS[c["receita"]]["confirmar"]} for n, c in _ler(arq).items() if c.get("receita") in RECEITAS]


def _preencher(txt: str, vals: dict, quote: bool = False) -> str:
    return _CAMPO.sub(lambda m: (urllib.parse.quote(str(vals.get(m.group(1), ""))) if quote else str(vals.get(m.group(1), ""))), txt)


def _eh_interno(host: str, resolver=socket.getaddrinfo) -> bool:
    try:
        ips = {i[4][0] for i in resolver(host, None)}
    except Exception:
        return True                                                       # não resolve: trata como inseguro
    for ip in ips:
        a = ipaddress.ip_address(ip)
        if a.is_private or a.is_loopback or a.is_link_local or a.is_reserved or a.is_multicast:
            return True
    return False


def _url_final(r: dict, dados: dict, pedido: dict, resolver=socket.getaddrinfo, checar_ip: bool = True) -> str:
    vals = dict(dados, **pedido)
    url = _preencher(r["url"], vals, quote=True) if "{webhook}" not in r["url"] and "{base}" not in r["url"] else _preencher(r["url"], vals)
    if r.get("query"):
        q = {k: _preencher(v, vals) for k, v in r["query"].items()}
        url += "?" + urllib.parse.urlencode(q)
    u = urllib.parse.urlsplit(url)
    if u.username or u.password or not u.hostname:
        raise ErroConector("Endereço inválido.")
    lan = bool(r.get("lan"))
    if u.scheme != "https" and not (lan and u.scheme == "http"):
        raise ErroConector("Só https é aceito" + (" (http só para o Home Assistant da sua rede)." if not lan else "."))
    if r.get("dominio") and not (u.hostname == r["dominio"] or u.hostname.endswith("." + r["dominio"])):
        raise ErroConector(f"O endereço precisa ser de {r['dominio']}.")
    if checar_ip and not lan and _eh_interno(u.hostname, resolver):
        raise ErroConector("Esse endereço é interno ou não resolve; não vou acessar.")
    return url


def preparar(nome: str, texto: str, arq: Path | None = None, resolver=socket.getaddrinfo) -> dict:
    """Monta a requisição (sem enviar). Devolve {url, metodo, headers, corpo, confirmar, descricao}."""
    c = _ler(arq).get(_nome(nome))
    if not c or c.get("receita") not in RECEITAS:
        raise ErroConector("Não achei esse conector. Disponíveis: " + (", ".join(x["nome"] for x in listar(arq)) or "nenhum"))
    r = RECEITAS[c["receita"]]
    texto = re.sub(r"\s+", " ", str(texto or "")).strip()[:500]
    if not texto:
        raise ErroConector("Falta o texto (o que criar/avisar/ativar).")
    if c["receita"] == "home_assistant_cena":
        texto = re.sub(r"[^a-z0-9_]+", "_", texto.lower()).strip("_")
    vals = dict(c["dados"], texto=texto)
    corpo = r.get("corpo")
    if isinstance(corpo, dict):
        corpo = {k: _preencher(v, vals) for k, v in corpo.items()}
    elif isinstance(corpo, str):
        corpo = _preencher(corpo, vals)
    return {"url": _url_final(r, c["dados"], {"texto": texto}, resolver), "metodo": r["metodo"],
            "headers": {k: _preencher(v, vals) for k, v in (r.get("headers") or {}).items()}, "corpo": corpo,
            "confirmar": r["confirmar"], "descricao": r["descricao"]}


def enviar(req: dict, http=None) -> str:
    """Envia sem seguir redirecionamentos. `http(req) -> (status, texto)` é injetável. Devolve a frase do resultado."""
    http = http or _http_real
    try:
        status, texto = http(req)
    except Exception as e:
        raise ErroConector(f"Falhou ao falar com o serviço: {str(e)[:100]}")
    if not (200 <= status < 300):
        raise ErroConector(f"O serviço respondeu {status}.")
    return f"{req['descricao']}: feito ({status})." + (f" Resposta (dado de terceiros): {texto[:MAX_RESPOSTA]}" if texto.strip() else "")


def _http_real(req: dict) -> tuple[int, str]:
    import urllib.request

    class _Sem(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    corpo = req["corpo"]
    dados = json.dumps(corpo).encode() if isinstance(corpo, dict) else (corpo.encode() if isinstance(corpo, str) else None)
    h = dict(req["headers"])
    if isinstance(corpo, dict):
        h["Content-Type"] = "application/json"
    rq = urllib.request.Request(req["url"], data=dados, headers=h, method=req["metodo"])
    op = urllib.request.build_opener(_Sem)
    try:
        with op.open(rq, timeout=TIMEOUT_S) as r:
            return r.status, r.read(4000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
