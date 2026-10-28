"""Telegram, agenda .ics e Notion — sem internet (http falso) e sem tocar na config real."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from core import integracoes as I

SP = ZoneInfo("America/Sao_Paulo")
TOKEN_TG = "123456789:" + "A" * 35
TOKEN_NT = "secret_" + "b" * 40


class Resp:
    def __init__(self, dados=None, texto="", status=200):
        self._d, self.text, self.status_code = dados, texto, status

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class Http:
    """Registra as chamadas e devolve respostas programadas por trecho da URL."""
    def __init__(self, rotas):
        self.rotas, self.chamadas = rotas, []

    def _r(self, metodo, url, **kw):
        self.chamadas.append((metodo, url, kw))
        for trecho, resp in self.rotas.items():
            if trecho in url:
                return resp(kw) if callable(resp) else resp
        raise RuntimeError("rota não prevista: " + url)

    def get(self, url, **kw):
        return self._r("get", url, **kw)

    def post(self, url, **kw):
        return self._r("post", url, **kw)


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    guardado = {}
    monkeypatch.setattr(I, "_cfg", lambda ns: dict(guardado.get(ns, {})))
    monkeypatch.setattr(I, "_salvar", lambda ns, v: guardado.setdefault(ns, {}).update(v))
    return guardado


# ── Telegram ─────────────────────────────────────────────────────────────────
def _tg_http(updates):
    return Http({"getMe": Resp({"ok": True, "result": {"username": "meu_bot"}}),
                 "getUpdates": Resp({"ok": True, "result": updates}),
                 "sendMessage": Resp({"ok": True, "result": {}})})


def test_telegram_fluxo_completo_e_ignora_estranhos(cfg):
    ups = [{"message": {"chat": {"id": 999, "type": "private"}, "from": {"first_name": "Estranho"}, "date": 1, "text": "oi sou golpe"}},
           {"message": {"chat": {"id": 42, "type": "private"}, "from": {"first_name": "André"}, "date": 1761660000, "text": "comprar pão"}}]
    h = _tg_http(ups)
    with pytest.raises(I.ErroIntegracao, match="token"):
        I.telegram_configurar("lixo", h)
    assert "@meu_bot" in I.telegram_configurar(TOKEN_TG, h)
    with pytest.raises(I.ErroIntegracao, match="reconhece"):
        I.telegram_enviar("oi", h)
    assert "André" in I.telegram_reconhecer(h)            # o mais recente é o do André
    assert cfg["telegram"]["chat_id"] == "42"
    assert I.telegram_enviar("lembrete", h) == "Mandei no seu Telegram."
    enviado = [c for c in h.chamadas if "sendMessage" in c[1]][0][2]["json"]
    assert enviado == {"chat_id": "42", "text": "lembrete"}
    lido = I.telegram_ler(5, h)
    assert "comprar pão" in lido and "golpe" not in lido     # mensagem de outro chat é ignorada


def test_telegram_erro_nao_vaza_o_token(cfg):
    def quebra(kw):
        raise RuntimeError(f"falha em https://api.telegram.org/bot{TOKEN_TG}/getMe")
    with pytest.raises(I.ErroIntegracao) as e:
        I.telegram_configurar(TOKEN_TG, Http({"getMe": quebra}))
    assert TOKEN_TG not in str(e.value) and "•••" in str(e.value)
    cfg["telegram"] = {"token": TOKEN_TG, "chat_id": "1"}
    with pytest.raises(I.ErroIntegracao) as e:
        I.telegram_enviar("x", Http({"sendMessage": Resp({"ok": False, "description": f"bad {TOKEN_TG}"})}))
    assert TOKEN_TG not in str(e.value)


def test_telegram_so_reconhece_chat_privado(cfg):
    cfg["telegram"] = {"token": TOKEN_TG}
    grupo = [{"message": {"chat": {"id": -5, "type": "group"}, "date": 1, "text": "oi"}}]
    with pytest.raises(I.ErroIntegracao, match="Ainda não vi"):
        I.telegram_reconhecer(_tg_http(grupo))


# ── Agenda ───────────────────────────────────────────────────────────────────
ICS = """BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART;TZID=America/Sao_Paulo:20261028T150000
DTEND;TZID=America/Sao_Paulo:20261028T160000
SUMMARY:Reunião com o time
LOCATION:Sala 3\\, 2º andar
END:VEVENT
BEGIN:VEVENT
DTSTART:20261029T120000Z
DTEND:20261029T130000Z
SUMMARY:Dentista
END:VEVENT
BEGIN:VEVENT
DTSTART;VALUE=DATE:20261028
DTEND;VALUE=DATE:20261029
SUMMARY:Feriado do servidor
END:VEVENT
BEGIN:VEVENT
DTSTART;TZID=America/Sao_Paulo:20261026T180000
DTEND;TZID=America/Sao_Paulo:20261026T190000
RRULE:FREQ=WEEKLY;BYDAY=MO
EXDATE;TZID=America/Sao_Paulo:20261109T180000
SUMMARY:Academia
END:VEVENT
BEGIN:VEVENT
DTSTART;TZID=America/Sao_Paulo:20261028T090000
DTEND;TZID=America/Sao_Paulo:20261028T100000
STATUS:CANCELLED
SUMMARY:Cancelada
END:VEVENT
END:VCALENDAR
"""
AGORA = datetime(2026, 10, 28, 12, 0, tzinfo=SP)


def _ag(cfg):
    cfg["calendario"] = {"ics_url": "https://calendar.example/secreto.ics"}
    return Http({"secreto.ics": Resp(texto=ICS)})


def test_agenda_hoje_amanha_semana_e_proximo(cfg):
    h = _ag(cfg)
    hoje = I.agenda_consultar("hoje", AGORA, h, SP)
    assert "15:00 Reunião com o time (Sala 3, 2º andar)" in hoje and "dia todo Feriado do servidor" in hoje
    assert "Cancelada" not in hoje and "Dentista" not in hoje
    assert "09:00 Dentista" in I.agenda_consultar("amanhã", AGORA, h, SP)          # 12:00Z = 09:00 em SP
    semana = I.agenda_consultar("semana", AGORA, h, SP)
    assert "Academia" in semana and "Dentista" in semana
    assert "15:00 Reunião" in I.agenda_consultar("proximo", AGORA, h, SP)
    assert "Nada na agenda" in I.agenda_consultar("hoje", datetime(2026, 12, 20, 8, tzinfo=SP), h, SP)


def test_agenda_repeticao_semanal_e_excecao(cfg):
    h = _ag(cfg)
    seg = datetime(2026, 11, 2, 8, tzinfo=SP)
    assert "18:00 Academia" in I.agenda_consultar("hoje", seg, h, SP)
    excluida = datetime(2026, 11, 9, 8, tzinfo=SP)                                   # EXDATE
    assert "Academia" not in I.agenda_consultar("hoje", excluida, h, SP)
    assert "Academia" not in I.agenda_consultar("hoje", datetime(2026, 10, 19, 8, tzinfo=SP), h, SP)  # antes do início


def test_agenda_configurar_valida_e_nao_vaza_url(cfg):
    with pytest.raises(I.ErroIntegracao, match="https"):
        I.agenda_configurar("http://inseguro/x.ics")
    with pytest.raises(I.ErroIntegracao) as e:
        I.agenda_configurar("https://calendar.example/segredo123.ics", Http({"segredo123": Resp(texto="<html>não é ics</html>")}))
    assert "segredo123" not in str(e.value) and cfg["calendario"]["ics_url"] == ""      # desfaz a configuração ruim
    assert "conectada" in I.agenda_configurar("https://calendar.example/ok.ics", Http({"ok.ics": Resp(texto=ICS)}))
    with pytest.raises(I.ErroIntegracao, match="hoje, amanhã"):
        I.agenda_consultar("ano que vem", AGORA, Http({"ok.ics": Resp(texto=ICS)}), SP)


# ── Notion ───────────────────────────────────────────────────────────────────
DB = "a" * 32


def test_notion_configurar_criar_e_buscar(cfg):
    h = Http({"/users/me": Resp({"object": "user"}),
              f"/databases/{DB}": Resp({"object": "database", "properties": {"Tags": {"type": "multi_select"}, "Nome": {"type": "title"}}}),
              "/pages": Resp({"object": "page"}),
              "/search": Resp({"object": "list", "results": [
                  {"properties": {"Nome": {"type": "title", "title": [{"plain_text": "Viagem a Recife"}]}}},
                  {"title": [{"plain_text": "Banco de ideias"}], "properties": {}}]})})
    h.get = lambda url, **kw: h._r("get", url, **kw)
    with pytest.raises(I.ErroIntegracao, match="token"):
        I.notion_configurar("lixo", DB, h)
    assert "conectado" in I.notion_configurar(TOKEN_NT, f"https://www.notion.so/ws/{DB}?v=1", h)
    assert cfg["notion"]["database_id"] == DB
    assert "Criei “Ideia do app”" in I.notion_criar("Ideia do app", "linha 1\n\nlinha 2", h)
    criacao = [c for c in h.chamadas if c[0] == "post" and c[1].endswith("/pages")][0][2]
    assert criacao["json"]["parent"] == {"database_id": DB}
    assert criacao["json"]["properties"]["Nome"]["title"][0]["text"]["content"] == "Ideia do app"   # achou a coluna de título
    assert len(criacao["json"]["children"]) == 2
    assert criacao["headers"]["Notion-Version"] == "2022-06-28"
    assert I.notion_buscar("viagem", 5, h) == "No Notion: Viagem a Recife | Banco de ideias"


def test_notion_erros_claros_e_sem_vazar_token(cfg):
    with pytest.raises(I.ErroIntegracao, match="não está configurado"):
        I.notion_buscar("x")
    cfg["notion"] = {"token": TOKEN_NT}
    with pytest.raises(I.ErroIntegracao, match="banco de dados"):
        I.notion_criar("t")
    h = Http({"/search": Resp({"object": "error", "message": f"token {TOKEN_NT} inválido"})})
    with pytest.raises(I.ErroIntegracao) as e:
        I.notion_buscar("x", 3, h)
    assert TOKEN_NT not in str(e.value)


def test_acoes_registram_ferramentas_e_tratam_erros(cfg):
    from actions import agenda_google, notion_nexus, telegram_nexus
    for m in (agenda_google, notion_nexus, telegram_nexus):
        assert m.TOOL["handler"] and m.TOOL["parameters"]["required"] == ["action"]
    assert telegram_nexus.telegram_nexus({"action": "send", "text": "oi"}).startswith("[failed]")
    assert agenda_google.agenda_google({"action": "query"}).startswith("[failed]")
    assert notion_nexus.notion_nexus({"action": "search", "query": "x"}).startswith("[failed]")
    assert "desconhecida" in notion_nexus.notion_nexus({"action": "zzz"})
