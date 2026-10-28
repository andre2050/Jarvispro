"""
core/integracoes.py — Telegram, agenda (Google Calendar e qualquer .ics) e Notion (NEXUS Ultra 2026 3.5).

Tudo com as SUAS chaves, guardadas em config/api_keys.json (fora do GitHub), e nenhuma delas aparece em
resposta, log ou erro. Cada função recebe `http` (padrão: requests) para poder ser testada sem internet.

  Telegram  O NEXUS manda e lê mensagens SÓ do seu próprio chat com o seu bot (chat_id fixo). Mensagens
            de outras pessoas são ignoradas — o bot não vira porta de entrada.
  Agenda    Lê o "endereço secreto em formato iCal" do Google Calendar (ou qualquer link .ics https).
            Só leitura, sem login OAuth. Entende eventos repetidos (semanal, mensal…).
  Notion    Cria notas/páginas num banco de dados do Notion e procura nas suas páginas (token de integração).
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

NS_TELEGRAM, NS_AGENDA, NS_NOTION = "telegram", "calendario", "notion"
_TIMEOUT = 20


class ErroIntegracao(Exception):
    """Mensagem segura para falar em voz alta (nunca contém chaves)."""


def _cfg(ns: str) -> dict:
    from memory.config_manager import get_plugin_config
    return get_plugin_config(ns)


def _salvar(ns: str, valores: dict) -> None:
    from memory.config_manager import save_plugin_config
    save_plugin_config(ns, valores)


def _http(http):
    if http is not None:
        return http
    import requests
    return requests


def _limpa(texto: str, *segredos: str) -> str:
    for s in segredos:
        if s:
            texto = texto.replace(s, "•••")
    return texto


# ═══ Telegram ════════════════════════════════════════════════════════════════
_TG = "https://api.telegram.org/bot{token}/{metodo}"


def _tg(metodo: str, dados: dict | None = None, http=None, token: str | None = None) -> dict:
    token = token or _cfg(NS_TELEGRAM).get("token", "")
    if not token:
        raise ErroIntegracao("O Telegram ainda não está configurado. Diga “configura o Telegram” e passe o token do bot.")
    try:
        r = _http(http).post(_TG.format(token=token, metodo=metodo), json=dados or {}, timeout=_TIMEOUT)
        d = r.json()
    except Exception as e:
        raise ErroIntegracao("Não consegui falar com o Telegram: " + _limpa(str(e), token)[:120])
    if not d.get("ok"):
        raise ErroIntegracao("O Telegram recusou: " + _limpa(str(d.get("description", "erro")), token)[:120])
    return d


def telegram_configurar(token: str, http=None) -> str:
    token = str(token or "").strip()
    if not re.fullmatch(r"\d{6,12}:[A-Za-z0-9_-]{30,50}", token):
        raise ErroIntegracao("Esse token não parece do BotFather (algo como 123456789:AA…).")
    me = _tg("getMe", http=http, token=token)["result"]
    novo = {"token": token}
    if _cfg(NS_TELEGRAM).get("token") != token:
        novo["chat_id"] = ""          # bot novo: o chat precisa ser reconhecido de novo
    _salvar(NS_TELEGRAM, novo)
    return (f"Bot @{me.get('username', '?')} conectado. Agora mande qualquer mensagem para ele no Telegram "
            f"e diga “reconhece meu Telegram”.")


def telegram_reconhecer(http=None) -> str:
    """Guarda como SEU chat o da mensagem mais recente enviada ao bot (só em chat privado)."""
    ups = _tg("getUpdates", {"limit": 20, "timeout": 0}, http)["result"]
    privados = [u["message"] for u in ups if isinstance(u.get("message"), dict)
                and u["message"].get("chat", {}).get("type") == "private"]
    if not privados:
        raise ErroIntegracao("Ainda não vi mensagem sua para o bot. Mande uma no Telegram e tente de novo.")
    m = privados[-1]
    _salvar(NS_TELEGRAM, {"chat_id": str(m["chat"]["id"])})
    nome = m.get("from", {}).get("first_name", "você")
    return f"Reconheci o chat de {nome}. Só ele fala com o NEXUS por aqui."


def _chat_id() -> str:
    cid = str(_cfg(NS_TELEGRAM).get("chat_id") or "")
    if not cid:
        raise ErroIntegracao("O Telegram ainda não reconhece o seu chat. Diga “reconhece meu Telegram”.")
    return cid


def telegram_enviar(texto: str, http=None) -> str:
    texto = str(texto or "").strip()
    if not texto:
        raise ErroIntegracao("O que devo mandar no Telegram?")
    _tg("sendMessage", {"chat_id": _chat_id(), "text": texto[:4000]}, http)
    return "Mandei no seu Telegram."


def telegram_ler(limite: int = 5, http=None) -> str:
    cid = _chat_id()
    ups = _tg("getUpdates", {"limit": 50, "timeout": 0}, http)["result"]
    msgs = [u["message"] for u in ups if isinstance(u.get("message"), dict)
            and str(u["message"].get("chat", {}).get("id")) == cid and u["message"].get("text")]
    if not msgs:
        return "Nenhuma mensagem sua nova no Telegram."
    msgs = msgs[-max(1, min(10, int(limite))):]
    return "Suas mensagens no Telegram: " + " | ".join(
        f"{datetime.fromtimestamp(m['date']).strftime('%d/%m %H:%M')}: {m['text'][:300]}" for m in msgs)


# ═══ Agenda (.ics) ═══════════════════════════════════════════════════════════
def _desdobrar(texto: str) -> list[str]:
    linhas: list[str] = []
    for l in texto.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if l[:1] in (" ", "\t") and linhas:
            linhas[-1] += l[1:]
        else:
            linhas.append(l)
    return linhas


def _desescapar(v: str) -> str:
    for velho, novo in (("\\n", " "), ("\\N", " "), ("\\,", ","), ("\\;", ";"), ("\\\\", "\\")):
        v = v.replace(velho, novo)
    return v.strip()


def _data(valor: str, params: str, tz_padrao) -> tuple[datetime, bool]:
    """(datetime com fuso, dia_inteiro)."""
    v = valor.strip()
    if re.fullmatch(r"\d{8}", v):
        return datetime(int(v[:4]), int(v[4:6]), int(v[6:8]), tzinfo=tz_padrao), True
    m = re.fullmatch(r"(\d{8})T(\d{6})(Z?)", v)
    if not m:
        raise ValueError(valor)
    base = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    if m.group(3):
        return base.replace(tzinfo=timezone.utc).astimezone(tz_padrao), False
    tzm = re.search(r"TZID=([^;:]+)", params)
    if tzm:
        try:
            return base.replace(tzinfo=ZoneInfo(tzm.group(1).strip('"'))).astimezone(tz_padrao), False
        except Exception:
            pass
    return base.replace(tzinfo=tz_padrao), False


def interpretar_ics(texto: str, inicio: datetime, fim: datetime, tz=None) -> list[dict]:
    """Eventos entre `inicio` e `fim` (com fuso), em ordem. Expande eventos repetidos."""
    from dateutil import rrule
    tz = tz or inicio.tzinfo or timezone.utc
    eventos, atual = [], None
    for l in _desdobrar(texto):
        if l == "BEGIN:VEVENT":
            atual = {}
        elif l == "END:VEVENT" and atual is not None:
            eventos.append(atual)
            atual = None
        elif atual is not None and ":" in l:
            chave, _, valor = l.partition(":")
            nome, _, params = chave.partition(";")
            atual.setdefault(nome.upper(), []).append((valor, params))
    saida: list[dict] = []
    for e in eventos:
        try:
            if e.get("STATUS", [("", "")])[0][0].upper() == "CANCELLED" or "DTSTART" not in e:
                continue
            ini, dia = _data(*e["DTSTART"][0], tz)
            if "DTEND" in e:
                f, _ = _data(*e["DTEND"][0], tz)
            else:
                f = ini + (timedelta(days=1) if dia else timedelta(0))
            dur = max(f - ini, timedelta(0))
            titulo = _desescapar(e.get("SUMMARY", [("(sem título)", "")])[0][0]) or "(sem título)"
            local = _desescapar(e.get("LOCATION", [("", "")])[0][0])
            ocorrencias = [ini]
            if "RRULE" in e:
                regra = rrule.rrulestr(e["RRULE"][0][0], dtstart=ini.replace(tzinfo=None) if dia else ini)
                ocorrencias = []
                for o in regra.between((inicio - dur).replace(tzinfo=None) if dia else inicio - dur,
                                       fim.replace(tzinfo=None) if dia else fim, inc=True):
                    ocorrencias.append(o.replace(tzinfo=tz) if dia else o)
                excl = set()
                for valor, params in e.get("EXDATE", []):
                    for v in valor.split(","):
                        try:
                            excl.add(_data(v, params, tz)[0])
                        except ValueError:
                            pass
                ocorrencias = [o for o in ocorrencias if o not in excl]
            for o in ocorrencias:
                if o < fim and (o + dur > inicio or (dur == timedelta(0) and o >= inicio)):
                    saida.append({"inicio": o, "fim": o + dur, "dia_inteiro": dia, "titulo": titulo, "local": local})
        except Exception:
            continue
    return sorted(saida, key=lambda x: x["inicio"])


def _baixar_ics(http=None) -> str:
    url = str(_cfg(NS_AGENDA).get("ics_url") or "")
    if not url:
        raise ErroIntegracao("A agenda ainda não está configurada. Diga “configura minha agenda” e passe o endereço iCal.")
    try:
        r = _http(http).get(url, timeout=_TIMEOUT)
        r.raise_for_status()
        if "BEGIN:VCALENDAR" not in r.text[:2000]:
            raise ValueError("não é um calendário")
        return r.text
    except Exception as e:
        raise ErroIntegracao("Não consegui ler a agenda: " + _limpa(str(e), url)[:100])


def agenda_configurar(url: str, http=None) -> str:
    url = str(url or "").strip()
    if not url.lower().startswith("https://"):
        raise ErroIntegracao("Use o endereço https do calendário (no Google Agenda: Configurações › o calendário › "
                             "“Endereço secreto no formato iCal”).")
    _salvar(NS_AGENDA, {"ics_url": url})
    try:
        _baixar_ics(http)
    except ErroIntegracao:
        _salvar(NS_AGENDA, {"ics_url": ""})
        raise
    return "Agenda conectada (só leitura). Pergunte “o que tenho hoje?” ou “o que tenho amanhã?”."


def _fmt(ev: dict, tz) -> str:
    ini = ev["inicio"].astimezone(tz)
    quando = "dia todo" if ev["dia_inteiro"] else ini.strftime("%H:%M")
    return f"{quando} {ev['titulo']}" + (f" ({ev['local']})" if ev["local"] else "")


def agenda_consultar(periodo: str = "hoje", agora: datetime | None = None, http=None, tz=None) -> str:
    tz = tz or ZoneInfo("America/Sao_Paulo")
    agora = (agora or datetime.now(tz)).astimezone(tz)
    d0 = datetime.combine(agora.date(), time(0), tz)
    p = str(periodo or "hoje").strip().lower()
    if p in ("hoje", "today"):
        ini, fim, rot = d0, d0 + timedelta(days=1), "hoje"
    elif p in ("amanha", "amanhã", "tomorrow"):
        ini, fim, rot = d0 + timedelta(days=1), d0 + timedelta(days=2), "amanhã"
    elif p in ("semana", "week"):
        ini, fim, rot = d0, d0 + timedelta(days=7), "nos próximos 7 dias"
    elif p in ("proximo", "próximo", "next"):
        ini, fim, rot = agora, agora + timedelta(days=30), "o próximo"
    else:
        raise ErroIntegracao("Posso ver hoje, amanhã, semana ou o próximo compromisso.")
    evs = interpretar_ics(_baixar_ics(http), ini, fim, tz)
    if p in ("proximo", "próximo", "next"):
        evs = [e for e in evs if e["fim"] > agora and not e["dia_inteiro"]][:1]
    if not evs:
        return f"Nada na agenda {rot}." if rot != "o próximo" else "Nenhum compromisso nos próximos 30 dias."
    if p in ("semana", "week"):
        return f"Agenda {rot}: " + " | ".join(
            f"{e['inicio'].astimezone(tz).strftime('%a %d/%m')} {_fmt(e, tz)}" for e in evs[:15])
    return f"Agenda {rot}: " + " | ".join(_fmt(e, tz) for e in evs[:12])


# ═══ Notion ══════════════════════════════════════════════════════════════════
_NOTION = "https://api.notion.com/v1"
_NOTION_VER = "2022-06-28"


def _notion(metodo: str, caminho: str, corpo: dict | None = None, http=None) -> dict:
    token = _cfg(NS_NOTION).get("token", "")
    if not token:
        raise ErroIntegracao("O Notion ainda não está configurado. Diga “configura o Notion” e passe o token da integração.")
    cab = {"Authorization": f"Bearer {token}", "Notion-Version": _NOTION_VER, "Content-Type": "application/json"}
    try:
        r = getattr(_http(http), metodo)(_NOTION + caminho, headers=cab, json=corpo, timeout=_TIMEOUT) if corpo is not None \
            else getattr(_http(http), metodo)(_NOTION + caminho, headers=cab, timeout=_TIMEOUT)
        d = r.json()
    except Exception as e:
        raise ErroIntegracao("Não consegui falar com o Notion: " + _limpa(str(e), token)[:120])
    if d.get("object") == "error":
        raise ErroIntegracao("O Notion recusou: " + _limpa(str(d.get("message", "erro")), token)[:140])
    return d


def _id_notion(texto: str) -> str:
    """Extrai o id (32 hex) de um link do Notion ou de um id com/sem traços. O que vem depois de ? ou # é ignorado."""
    caminho = re.split(r"[?#]", str(texto or "").strip())[0].replace("-", "")
    achados = re.findall(r"[0-9a-fA-F]{32}", caminho)
    return achados[-1].lower() if achados else ""


def notion_configurar(token: str, database_id: str = "", http=None) -> str:
    token = str(token or "").strip()
    if not re.fullmatch(r"(secret_|ntn_)[A-Za-z0-9]{20,80}", token):
        raise ErroIntegracao("Esse token não parece de uma integração do Notion (começa com secret_ ou ntn_).")
    dbid = _id_notion(database_id)
    _salvar(NS_NOTION, {"token": token, **({"database_id": dbid} if len(dbid) == 32 else {})})
    try:
        _notion("get", "/users/me", http=http)
    except ErroIntegracao:
        _salvar(NS_NOTION, {"token": ""})
        raise
    extra = "" if len(dbid) == 32 else " Falta o banco de dados: passe o link ou o id dele (compartilhado com a integração)."
    return "Notion conectado." + extra


def _titulo_da_propriedade(db: dict) -> str:
    for nome, p in (db.get("properties") or {}).items():
        if p.get("type") == "title":
            return nome
    raise ErroIntegracao("Esse banco do Notion não tem coluna de título.")


def notion_criar(titulo: str, texto: str = "", http=None) -> str:
    titulo = " ".join(str(titulo or "").split())[:200]
    if not titulo:
        raise ErroIntegracao("Qual o título da nota no Notion?")
    dbid = _cfg(NS_NOTION).get("database_id", "")
    if not dbid:
        raise ErroIntegracao("Falta o banco de dados do Notion. Diga “configura o Notion” com o link do banco.")
    coluna = _titulo_da_propriedade(_notion("get", f"/databases/{dbid}", http=http))
    corpo = {"parent": {"database_id": dbid},
             "properties": {coluna: {"title": [{"text": {"content": titulo}}]}}}
    paragrafos = [p.strip() for p in str(texto or "").split("\n") if p.strip()][:50]
    if paragrafos:
        corpo["children"] = [{"object": "block", "type": "paragraph",
                              "paragraph": {"rich_text": [{"type": "text", "text": {"content": p[:1900]}}]}}
                             for p in paragrafos]
    _notion("post", "/pages", corpo, http)
    return f"Criei “{titulo}” no seu Notion."


def notion_buscar(consulta: str, limite: int = 5, http=None) -> str:
    consulta = str(consulta or "").strip()
    if not consulta:
        raise ErroIntegracao("O que devo procurar no Notion?")
    d = _notion("post", "/search", {"query": consulta, "page_size": max(1, min(10, int(limite)))}, http)
    achados = []
    for r in d.get("results", []):
        titulo = ""
        for p in (r.get("properties") or {}).values():
            if p.get("type") == "title":
                titulo = "".join(t.get("plain_text", "") for t in p.get("title", []))
        if not titulo and isinstance(r.get("title"), list):
            titulo = "".join(t.get("plain_text", "") for t in r["title"])
        achados.append(titulo or "(sem título)")
    return ("No Notion: " + " | ".join(achados)) if achados else f"Não achei nada sobre “{consulta}” no Notion."
