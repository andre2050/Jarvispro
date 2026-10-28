"""Testes da casa inteligente contra um Home Assistant FALSO de verdade (servidor HTTP local).

Cobre: comandos e conferência do resultado, aparelhos que não obedecem, nomes aproximados, grupos,
confirmação na tela para itens sensíveis, token nunca vazando, redirecionamento, servidor fora do ar,
descoberta de aparelhos, webhooks e endereços inválidos.
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from actions import casa_inteligente as ca
from core import confirm

TOKEN = "tok_SEGREDO_123456"


class FakeHA:
    """Servidor mínimo com a API REST do Home Assistant (estados e serviços)."""

    def __init__(self):
        self.estados = {
            "light.sala": {"state": "off", "attributes": {"friendly_name": "Luz da Sala"}},
            "light.quarto": {"state": "off", "attributes": {"friendly_name": "Luz do Quarto"}},
            "light.cozinha": {"state": "on", "attributes": {"friendly_name": "Luz da Cozinha"}},
            "lock.porta": {"state": "locked", "attributes": {"friendly_name": "Porta da Frente"}},
            "cover.cortina": {"state": "closed", "attributes": {"friendly_name": "Cortina do Quarto"}},
            "cover.garagem": {"state": "closed", "attributes": {"friendly_name": "Portão", "device_class": "garage"}},
            "climate.ar": {"state": "cool", "attributes": {"friendly_name": "Ar da Sala", "temperature": 24,
                                                           "current_temperature": 26}},
            "script.alarme": {"state": "off", "attributes": {"friendly_name": "Disparar alarme"}},
            "sensor.temp": {"state": "21", "attributes": {"friendly_name": "Sensor"}},
            "alarm_control_panel.casa": {"state": "armed", "attributes": {}},
        }
        self.offline: set[str] = set()          # aparelhos que recebem o comando mas não mudam
        self.pedidos: list[dict] = []
        self.token = TOKEN
        self.resposta_gigante = False
        self.redireciona_para: str | None = None
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _enviar(self, codigo, dados=None):
                corpo = json.dumps(dados).encode() if dados is not None else b""
                self.send_response(codigo)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

            def _registrar(self, corpo=None):
                outer.pedidos.append({"metodo": self.command, "caminho": self.path,
                                      "auth": self.headers.get("Authorization"), "corpo": corpo})

            def _autorizado(self):
                if self.headers.get("Authorization") != f"Bearer {outer.token}":
                    self._enviar(401, {"message": "401: Unauthorized"})
                    return False
                return True

            def do_GET(self):
                self._registrar()
                if outer.redireciona_para:
                    self.send_response(302)
                    self.send_header("Location", outer.redireciona_para + self.path)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if self.path.startswith("/hook/"):
                    return self._enviar(200, {"ok": True})
                if not self._autorizado():
                    return
                if self.path == "/api/states":
                    if outer.resposta_gigante:
                        return self._enviar(200, [{"entity_id": "light.x", "pad": "x" * (3 * 1024 * 1024)}])
                    return self._enviar(200, [dict(entity_id=k, **v) for k, v in outer.estados.items()])
                if self.path.startswith("/api/states/"):
                    eid = self.path.rsplit("/", 1)[1]
                    if eid not in outer.estados:
                        return self._enviar(404, {"message": "Entity not found."})
                    return self._enviar(200, dict(entity_id=eid, **outer.estados[eid]))
                self._enviar(404)

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                corpo = json.loads(self.rfile.read(n) or b"{}")
                self._registrar(corpo)
                if self.path.startswith("/hook/"):
                    return self._enviar(200, {"ok": True})
                if not self._autorizado():
                    return
                partes = self.path.split("/")
                if len(partes) != 5 or partes[:3] != ["", "api", "services"]:
                    return self._enviar(404)
                dominio, servico = partes[3], partes[4]
                eid = corpo.get("entity_id")
                if eid not in outer.estados:
                    return self._enviar(400, {"message": "unknown entity"})
                if eid not in outer.offline:
                    outer.aplicar(eid, dominio, servico, corpo)
                self._enviar(200, [])

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()

    def aplicar(self, eid, dominio, servico, corpo):
        e = self.estados[eid]
        novo = {"turn_on": "on", "turn_off": "off", "lock": "locked", "unlock": "unlocked",
                "open_cover": "open", "close_cover": "closed"}.get(servico)
        if servico == "toggle":
            novo = "off" if e["state"] == "on" else "on"
        if novo:
            e["state"] = novo
        if "brightness_pct" in corpo:
            e["attributes"]["brightness"] = round(corpo["brightness_pct"] * 255 / 100)
        if "temperature" in corpo:
            e["attributes"]["temperature"] = corpo["temperature"]

    def servicos(self):
        return [p for p in self.pedidos if p["metodo"] == "POST" and p["caminho"].startswith("/api/services/")]

    def parar(self):
        self.srv.shutdown()
        self.srv.server_close()


@pytest.fixture
def ha():
    s = FakeHA()
    yield s
    s.parar()


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr(ca, "_CONFIG", tmp_path / "casa.json")
    monkeypatch.setattr(ca, "_KEYS", tmp_path / "api_keys.json")
    monkeypatch.setattr(ca, "_ESPERA", 0)
    monkeypatch.setenv("NEXUS_HA_TOKEN", TOKEN)
    # sem tela por padrão: nenhuma confirmação disponível
    monkeypatch.setattr(confirm, "_show_cb", None)
    monkeypatch.setattr(confirm, "_hide_cb", None)
    monkeypatch.setattr(confirm, "_pending", None)
    return tmp_path


def configurar(ha, aparelhos=None, **extra):
    aparelhos = aparelhos if aparelhos is not None else {
        "luz da sala": {"entity_id": "light.sala"},
        "luz do quarto": {"entity_id": "light.quarto"},
        "luz da cozinha": {"entity_id": "light.cozinha"},
        "porta da frente": {"entity_id": "lock.porta", "sensitive": True},
        "cortina do quarto": {"entity_id": "cover.cortina"},
        "portão": {"entity_id": "cover.garagem", "sensitive": True},
        "ar da sala": {"entity_id": "climate.ar"},
        "alarme": {"entity_id": "script.alarme"},
    }
    cfg = {"home_assistant": {"url": ha.url}, "devices": aparelhos, **extra}
    ca._CONFIG.write_text(json.dumps(cfg), encoding="utf-8")


def run(**kw):
    return ca.casa_inteligente(kw)


def com_tela(monkeypatch):
    """Liga uma 'tela' falsa para as confirmações e devolve a lista do que foi mostrado."""
    mostrados = []
    monkeypatch.setattr(confirm, "_show_cb", lambda t, d: mostrados.append((t, d)))
    monkeypatch.setattr(confirm, "_hide_cb", lambda: None)
    return mostrados


def esperar(cond, limite=3.0):
    fim = time.monotonic() + limite
    while time.monotonic() < fim:
        if cond():
            return True
        time.sleep(0.02)
    return False


# ── comandos básicos e conferência ───────────────────────────────────────────

def test_ligar_luz_confere_que_ligou(ha):
    configurar(ha)
    r = run(action="on", device="luz da sala")
    assert r == "[done] luz da sala: ligado."
    (req,) = ha.servicos()
    assert req["caminho"] == "/api/services/light/turn_on"
    assert req["corpo"] == {"entity_id": "light.sala"}
    assert req["auth"] == f"Bearer {TOKEN}"


def test_desligar_e_alternar(ha):
    configurar(ha)
    assert run(action="off", device="luz da cozinha") == "[done] luz da cozinha: desligado."
    assert run(action="toggle", device="luz da cozinha") == "[done] luz da cozinha: ligado."
    assert ha.estados["light.cozinha"]["state"] == "on"


def test_aparelho_que_nao_obedece_vira_unverified(ha):
    configurar(ha)
    ha.offline.add("light.sala")
    r = run(action="on", device="luz da sala")
    assert r.startswith("[unverified]") and "continua desligado" in r


def test_brilho(ha):
    configurar(ha)
    assert run(action="set_brightness", device="luz da sala", value=40) == "[done] luz da sala: ligado em 40%."
    assert ha.servicos()[0]["corpo"]["brightness_pct"] == 40
    assert "brilho 40%" in run(action="status", device="luz da sala")


@pytest.mark.parametrize("valor", [150, -1, "abc", None])
def test_brilho_invalido_nao_envia_nada(ha, valor):
    configurar(ha)
    assert run(action="set_brightness", device="luz da sala", value=valor).startswith("[failed]")
    assert ha.servicos() == []


def test_temperatura_do_ar(ha):
    configurar(ha)
    assert run(action="set_temperature", device="ar da sala", value=22) == "[done] ar da sala ajustado para 22°."
    assert "ajustado para 22" in run(action="status", device="ar da sala")


@pytest.mark.parametrize("valor", [5, 50, "frio", None])
def test_temperatura_fora_do_limite_nao_envia(ha, valor):
    configurar(ha)
    assert run(action="set_temperature", device="ar da sala", value=valor).startswith("[failed]")
    assert ha.servicos() == []


def test_acao_que_o_tipo_nao_aceita(ha):
    configurar(ha)
    r = run(action="unlock", device="luz da sala")
    assert r.startswith("[failed]") and "não aceita" in r
    assert ha.servicos() == []


def test_acao_desconhecida_ou_vazia(ha):
    configurar(ha)
    assert run(action="explodir", device="luz da sala").startswith("[failed]")
    assert run().startswith("[failed]")
    assert ca.casa_inteligente(None).startswith("[failed]")
    assert ha.servicos() == []


# ── achar o aparelho ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("pedido", ["luz da sala", "a luz da sala", "LUZ DA SALA", "luz sala", "Luz  da  Sala "])
def test_nome_aproximado(ha, pedido):
    configurar(ha)
    assert run(action="on", device=pedido).startswith("[done]")
    assert ha.servicos()[-1]["corpo"]["entity_id"] == "light.sala"


def test_nome_ambiguo_pergunta_qual(ha):
    configurar(ha)
    r = run(action="status", device="luz")
    assert r.startswith("[failed]") and "Qual deles" in r and "luz da sala" in r and "luz do quarto" in r


def test_nome_desconhecido_lista_o_que_existe(ha):
    configurar(ha)
    r = run(action="on", device="geladeira")
    assert r.startswith("[failed]") and "luz da sala" in r


def test_sem_aparelhos_cadastrados(ha):
    configurar(ha, aparelhos={})
    assert "discover" in run(action="on", device="luz")


def test_apelidos(ha):
    configurar(ha, aparelhos={"luz da sala": {"entity_id": "light.sala", "aliases": ["abajur"]}})
    assert run(action="on", device="abajur").startswith("[done]")


# ── grupos ───────────────────────────────────────────────────────────────────

def test_apagar_todas_as_luzes_ignora_as_sensiveis(ha):
    configurar(ha)
    ha.estados["light.sala"]["state"] = "on"
    ha.estados["light.quarto"]["state"] = "on"
    cfg = json.loads(ca._CONFIG.read_text(encoding="utf-8"))
    cfg["devices"]["luz do escritório"] = {"entity_id": "light.sala", "sensitive": True}
    ca._CONFIG.write_text(json.dumps(cfg), encoding="utf-8")
    r = run(action="off", device="todas as luzes")
    assert r == "[done] 3 aparelhos desligados."
    assert {s["corpo"]["entity_id"] for s in ha.servicos()} == {"light.sala", "light.quarto", "light.cozinha"}
    assert len(ha.servicos()) == 3                     # o “escritório” sensível ficou de fora


def test_grupo_com_aparelho_offline_avisa(ha):
    configurar(ha)
    ha.offline.add("light.sala")
    ha.estados["light.sala"]["state"] = "on"
    r = run(action="off", device="luzes")
    assert r.startswith("[unverified]") and "2 de 3" in r


def test_abrir_todas_as_cortinas(ha):
    configurar(ha)
    assert run(action="open", device="as cortinas") == "[done] 1 aparelhos abertos."
    assert ha.estados["cover.cortina"]["state"] == "open"


def test_nome_exato_vence_o_grupo(ha):
    configurar(ha, aparelhos={"luzes": {"entity_id": "light.sala"}, "luz do quarto": {"entity_id": "light.quarto"}})
    assert run(action="on", device="luzes") == "[done] luzes: ligado."
    assert len(ha.servicos()) == 1


# ── confirmação na tela ──────────────────────────────────────────────────────

def test_trancar_nao_pede_confirmacao(ha):
    configurar(ha)
    ha.estados["lock.porta"]["state"] = "unlocked"
    assert run(action="lock", device="porta da frente") == "[done] porta da frente: trancado."


def test_destrancar_so_acontece_depois_do_clique(ha, monkeypatch):
    configurar(ha)
    mostrados = com_tela(monkeypatch)
    r = run(action="unlock", device="porta da frente")
    assert "[CONFIRMATION_PENDING]" in r
    assert len(mostrados) == 1 and "porta da frente" in mostrados[0][0]
    assert ha.servicos() == [] and ha.estados["lock.porta"]["state"] == "locked"
    confirm.resolve(True)
    assert esperar(lambda: ha.estados["lock.porta"]["state"] == "unlocked")
    assert ha.servicos()[0]["caminho"] == "/api/services/lock/unlock"


def test_cancelar_nao_executa(ha, monkeypatch):
    configurar(ha)
    com_tela(monkeypatch)
    run(action="unlock", device="porta da frente")
    confirm.resolve(False)
    time.sleep(0.2)
    assert ha.servicos() == [] and ha.estados["lock.porta"]["state"] == "locked"


def test_sem_tela_sensivel_e_recusado(ha):
    configurar(ha)
    r = run(action="unlock", device="porta da frente")
    assert "not available" in r and "not done it" in r.replace("have not done it", "not done it")
    assert ha.servicos() == []


def test_portao_abre_com_confirmacao_e_fecha_sem(ha, monkeypatch):
    configurar(ha)
    com_tela(monkeypatch)
    assert "[CONFIRMATION_PENDING]" in run(action="open", device="portão")
    confirm.resolve(False)
    ha.estados["cover.garagem"]["state"] = "open"
    assert run(action="close", device="portão").startswith("[done]")


def test_script_sempre_pede_confirmacao(ha, monkeypatch):
    configurar(ha, aparelhos={"alarme": {"entity_id": "script.alarme", "sensitive": False}})
    com_tela(monkeypatch)
    assert "[CONFIRMATION_PENDING]" in run(action="on", device="alarme")
    assert ha.servicos() == []


def test_duas_confirmacoes_nao_empilham(ha, monkeypatch):
    configurar(ha)
    com_tela(monkeypatch)
    run(action="unlock", device="porta da frente")
    r = run(action="open", device="portão")
    assert r.startswith("[failed]") and "confirmação" in r


def test_aparelho_marcado_sensivel_pede_para_ligar(ha, monkeypatch):
    configurar(ha, aparelhos={"forno": {"entity_id": "light.sala", "sensitive": True}})
    com_tela(monkeypatch)
    assert "[CONFIRMATION_PENDING]" in run(action="on", device="forno")
    confirm.resolve(False)
    assert run(action="off", device="forno").startswith("[done]")


# ── segurança ────────────────────────────────────────────────────────────────

def test_token_errado_da_mensagem_clara_e_sem_vazar(ha, monkeypatch):
    configurar(ha)
    monkeypatch.setenv("NEXUS_HA_TOKEN", "token_errado_ABC")
    for r in (run(action="on", device="luz da sala"), run(action="status", device="luz da sala"),
              run(action="discover")):
        assert r.startswith("[failed]") and "token" in r
        assert "token_errado_ABC" not in r and TOKEN not in r


def test_token_nunca_aparece_nas_respostas(ha):
    configurar(ha)
    saidas = [run(action="on", device="luz da sala"), run(action="list"), run(action="setup_help"),
              run(action="status", device="luz da sala"), run(action="discover")]
    assert all(TOKEN not in s for s in saidas)


def test_token_vem_do_api_keys_quando_nao_ha_variavel(ha, monkeypatch, ambiente):
    configurar(ha)
    monkeypatch.delenv("NEXUS_HA_TOKEN")
    assert run(action="on", device="luz da sala").startswith("[failed]")             # sem token em lugar nenhum
    (ambiente / "api_keys.json").write_text(json.dumps({"home_assistant_token": TOKEN}), encoding="utf-8")
    assert run(action="on", device="luz da sala").startswith("[done]")


def test_redirecionamento_nao_e_seguido_e_o_token_nao_vaza(ha):
    alvo = FakeHA()
    try:
        ha.redireciona_para = alvo.url
        configurar(ha)
        r = run(action="status", device="luz da sala")
        assert r.startswith("[failed]") and "redireciona" in r
        assert alvo.pedidos == []                       # o outro servidor nunca foi procurado
    finally:
        alvo.parar()


def test_servidor_fora_do_ar_nao_derruba(ha):
    configurar(ha)
    ha.parar()
    r = run(action="on", device="luz da sala")
    assert r.startswith("[failed]") and "Não consegui falar" in r


def test_resposta_gigante_e_ignorada(ha):
    configurar(ha)
    ha.resposta_gigante = True
    r = run(action="discover")
    assert r.startswith("[failed]") and "grande demais" in r


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://x/y", "http://usuario:senha@127.0.0.1/", "javascript:1",
                                 "", "isso não é url", "http://"])
def test_enderecos_invalidos_sao_recusados(url, ha):
    ca._CONFIG.write_text(json.dumps({"home_assistant": {"url": url},
                                      "devices": {"luz": {"entity_id": "light.sala"}}}), encoding="utf-8")
    assert run(action="on", device="luz").startswith("[failed]")
    assert ha.pedidos == []


def test_sem_configuracao_explica_como_configurar():
    r = run(action="on", device="luz")
    assert r.startswith("[failed]") and "discover" in r
    ca._CONFIG.write_text(json.dumps({"devices": {"luz": {"entity_id": "light.sala"}}}), encoding="utf-8")
    assert "setup_help" in run(action="on", device="luz")


def test_config_corrompida_nao_derruba():
    ca._CONFIG.write_text("{não é json", encoding="utf-8")
    assert run(action="list").startswith("[done] Nenhum aparelho")
    assert run(action="on", device="luz").startswith("[failed]")


# ── cadastro ─────────────────────────────────────────────────────────────────

def test_descobrir_importa_so_o_que_o_nexus_sabe_controlar(ha):
    configurar(ha, aparelhos={})
    r = run(action="discover")
    assert r.startswith("[done] Cadastrei") and "3 light" in r and "lock" in r
    aps = json.loads(ca._CONFIG.read_text(encoding="utf-8"))["devices"]
    ids = {a["entity_id"] for a in aps.values()}
    assert "sensor.temp" not in ids and "alarm_control_panel.casa" not in ids          # não controláveis
    assert aps["Porta da Frente"]["sensitive"] is True
    assert aps["Portão"]["sensitive"] is True                                          # cover de garagem
    assert aps["Cortina do Quarto"]["sensitive"] is False
    assert aps["Disparar alarme"]["sensitive"] is True                                 # script
    assert aps["Luz da Sala"]["sensitive"] is False
    # depois de descobrir, dá para usar pelo nome do Home Assistant
    assert run(action="on", device="luz da sala").startswith("[done]")


def test_descobrir_nao_duplica_nem_sobrescreve(ha):
    configurar(ha, aparelhos={"minha luz": {"entity_id": "light.sala", "sensitive": True}})
    run(action="discover")
    aps = json.loads(ca._CONFIG.read_text(encoding="utf-8"))["devices"]
    assert aps["minha luz"] == {"entity_id": "light.sala", "sensitive": True}
    assert sum(a["entity_id"] == "light.sala" for a in aps.values()) == 1
    assert "Nada novo" in run(action="discover")


def test_descobrir_limpa_nomes_estranhos_e_resolve_repetidos(ha):
    ha.estados["light.a"] = {"state": "off", "attributes": {"friendly_name": "Luz\x00da Sala\n" + "x" * 200}}
    ha.estados["light.b"] = {"state": "off", "attributes": {"friendly_name": "Luz da Sala"}}
    configurar(ha, aparelhos={})
    run(action="discover")
    aps = json.loads(ca._CONFIG.read_text(encoding="utf-8"))["devices"]
    assert all(len(n) <= 60 and "\x00" not in n and "\n" not in n for n in aps)
    assert len(aps) == len({a["entity_id"] for a in aps.values()})


def test_limite_de_aparelhos(ha, monkeypatch):
    monkeypatch.setattr(ca, "MAX_APARELHOS", 3)
    configurar(ha, aparelhos={})
    run(action="discover")
    assert len(json.loads(ca._CONFIG.read_text(encoding="utf-8"))["devices"]) == 3


@pytest.mark.parametrize("eid", ["sensor.temp", "../etc/passwd", "light.x; drop", "light", "LIGHT.sala!", "", None,
                                 "alarm_control_panel.casa"])
def test_add_device_valida_entity_id(eid):
    ca._CONFIG.write_text(json.dumps({"devices": {}}), encoding="utf-8")
    assert run(action="add_device", device="x", entity_id=eid).startswith("[failed]")
    assert json.loads(ca._CONFIG.read_text(encoding="utf-8"))["devices"] == {}


def test_add_e_remove_device():
    ca._CONFIG.write_text(json.dumps({"home_assistant": {"url": "http://x"}}), encoding="utf-8")
    assert run(action="add_device", device="Luz do Quintal", entity_id="light.quintal", sensitive=True).startswith("[done]")
    cfg = json.loads(ca._CONFIG.read_text(encoding="utf-8"))
    assert cfg["devices"]["Luz do Quintal"] == {"entity_id": "light.quintal", "sensitive": True}
    assert cfg["home_assistant"] == {"url": "http://x"}                                # o resto da config fica
    assert "🔒" in run(action="list")
    assert run(action="remove_device", device="luz do quintal").startswith("[done]")
    assert run(action="remove_device", device="luz do quintal").startswith("[failed]")


def test_setup_help_cria_modelo_sem_sobrescrever(ha):
    assert not ca._CONFIG.exists()
    r = run(action="setup_help")
    assert r.startswith("[done]") and "Token" in r.replace("token", "Token") and ca._CONFIG.exists()
    ca._CONFIG.write_text(json.dumps({"home_assistant": {"url": "http://meu"}, "devices": {}}), encoding="utf-8")
    run(action="setup_help")
    assert json.loads(ca._CONFIG.read_text(encoding="utf-8"))["home_assistant"]["url"] == "http://meu"


def test_gravacao_nao_deixa_arquivo_temporario(ha, ambiente):
    ca._CONFIG.write_text("{}", encoding="utf-8")
    run(action="add_device", device="a", entity_id="light.a")
    assert sorted(p.name for p in ambiente.iterdir()) == ["casa.json"]


# ── status ───────────────────────────────────────────────────────────────────

def test_status_da_fechadura_e_da_luz(ha):
    configurar(ha)
    assert run(action="status", device="porta da frente") == "[done] porta da frente: trancado."
    assert run(action="status", device="luz da cozinha") == "[done] luz da cozinha: ligado."


def test_status_de_entidade_que_sumiu_do_ha(ha):
    configurar(ha, aparelhos={"fantasma": {"entity_id": "light.nao_existe"}})
    r = run(action="status", device="fantasma")
    assert r.startswith("[failed]") and "entity_id" in r


# ── webhooks ─────────────────────────────────────────────────────────────────

def test_webhook_liga_mas_nao_finge_confirmar(ha):
    ca._CONFIG.write_text(json.dumps({"devices": {"luz do quintal": {"webhook": {
        "on": ha.url + "/hook/on", "off": ha.url + "/hook/off"}}}}), encoding="utf-8")
    r = run(action="on", device="luz do quintal")
    assert r.startswith("[unverified]") and "não confirma" in r
    assert ha.pedidos[0]["caminho"] == "/hook/on" and ha.pedidos[0]["metodo"] == "GET"
    assert ha.pedidos[0]["auth"] is None                                       # webhook não leva o token do HA
    assert ha.url not in r                                                    # a URL (que pode ter segredo) não é impressa


def test_webhook_post_e_acao_sem_endereco(ha):
    ca._CONFIG.write_text(json.dumps({"devices": {"tomada": {"webhook": {
        "on": ha.url + "/hook/on", "method": "POST"}}}}), encoding="utf-8")
    assert run(action="on", device="tomada").startswith("[unverified]")
    assert ha.pedidos[0]["metodo"] == "POST"
    r = run(action="off", device="tomada")
    assert r.startswith("[failed]") and "não tem endereço" in r


def test_webhook_com_url_invalida_ou_sem_status(ha):
    ca._CONFIG.write_text(json.dumps({"devices": {"x": {"webhook": {"on": "file:///etc/passwd"}}}}), encoding="utf-8")
    assert run(action="on", device="x").startswith("[failed]")
    assert "webhook" in run(action="status", device="x")
    assert ha.pedidos == []


def test_webhook_sensivel_pede_confirmacao(ha, monkeypatch):
    ca._CONFIG.write_text(json.dumps({"devices": {"portão": {"sensitive": True, "webhook": {
        "on": ha.url + "/hook/abrir"}}}}), encoding="utf-8")
    com_tela(monkeypatch)
    assert "[CONFIRMATION_PENDING]" in run(action="on", device="portão")
    assert ha.pedidos == []
    confirm.resolve(True)
    assert esperar(lambda: len(ha.pedidos) == 1)


# ── integração com o resto do NEXUS ──────────────────────────────────────────

def test_tool_bem_formada_e_com_interruptor_de_permissao():
    t = ca.TOOL
    assert t["name"] == "casa_inteligente" and callable(t["handler"])
    enum = set(t["parameters"]["properties"]["action"]["enum"])
    assert {"on", "off", "unlock", "discover", "setup_help", "status", "list"} <= enum
    assert enum == set(ca._ACOES_COMANDO) | set(ca._OUTRAS)
    from core import settings_tools as S
    assert "casa_inteligente" in S.ACTUATOR_GROUPS["casa"][1]


def test_carregador_do_nexus_aceita_a_ferramenta_e_respeita_o_interruptor(tmp_path, monkeypatch):
    """O mesmo carregador que o NEXUS usa: descobre a ferramenta e obedece ao painel de permissões."""
    import shutil
    from core import action_loader
    from core import preferences
    pasta = tmp_path / "acoes"
    pasta.mkdir()
    shutil.copy(ca.__file__, pasta / "casa_inteligente.py")
    reg = action_loader.discover_actions(pasta, logger=lambda m: None)
    assert "casa_inteligente" in reg.names()
    decl = [d for d in reg.get_tool_declarations()]
    assert any("casa_inteligente" in json.dumps(d) for d in decl)
    assert reg.run("casa_inteligente", {"action": "list"}).startswith("[done]")
    monkeypatch.setattr(preferences, "get", lambda k: {"casa": False} if k == "actuator_permissions" else None)
    r = reg.run("casa_inteligente", {"action": "list"})
    assert "Permissão desligada" in r
