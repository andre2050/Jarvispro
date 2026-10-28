"""4.1 — checkpoints/replay de missões, guardrails de entrada/saída e trace local."""
import json

import pytest

from core import auditoria as AU
from core import guardrails as G
from core import missoes as M
from core import missoes_checkpoint as CP
from core import trace_local as T
from tests.test_missoes import Fake


@pytest.fixture
def amb(tmp_path, monkeypatch):
    monkeypatch.setattr(AU, "ARQUIVO", tmp_path / "aud.jsonl")
    monkeypatch.setattr(T, "ARQUIVO", tmp_path / "trace.jsonl")
    monkeypatch.setattr(G, "ARQUIVO", tmp_path / "guard.json")
    return tmp_path


PLANO = [{"tool": "web_search", "args": {"query": "a"}, "titulo": "passo a"},
         {"tool": "web_search", "args": {"query": "b"}, "titulo": "passo b", "depende": [1]},
         {"tool": "web_search", "args": {"query": "c"}, "titulo": "passo c", "depende": [2]}]


def _concluida(amb):
    f = Fake(PLANO)
    mo = f.motor(amb)
    m = mo.criar("tres passos")
    assert mo.rodar_ate_parar(m["id"]) == "fim"
    return f, mo, m["id"]


# ── checkpoints ──────────────────────────────────────────────────────────────
def test_cada_passo_concluido_gera_checkpoint_e_voltar_refaz_dali(amb):
    f, mo, mid = _concluida(amb)
    m = M.carregar(mid, mo.pasta)
    assert [c["n"] for c in CP.listar(m)] == [1, 2, 3] and CP.listar(m)[1]["feitos"] == 2
    f.exec.clear()
    r = mo.voltar(mid, 1, {"p2": {"query": "b melhorado"}})
    m = M.carregar(mid, mo.pasta)
    assert m["estado"] == "pausada" and [p["estado"] for p in m["plano"]] == ["ok", "pendente", "pendente"]
    assert r["efeitos_que_ficam"] == ["passo b", "passo c"]                     # o mundo real não é desfeito: o usuário é avisado
    assert [c["n"] for c in m["checkpoints"]] == [1]
    mo.pausar(mid, False)
    assert mo.rodar_ate_parar(mid) == "fim"
    assert [e[1]["query"] for e in f.exec] == ["b melhorado", "c"]              # o passo a NÃO rodou de novo


def test_voltar_recusa_missao_em_andamento_checkpoint_inexistente_e_passo_ja_feito(amb):
    f, mo, mid = _concluida(amb)
    with pytest.raises(M.ErroMissao):
        mo.voltar(mid, 9)
    with pytest.raises(M.ErroMissao):
        mo.voltar(mid, 2, {"p1": {"query": "x"}})                                  # passo 1 já estava ok: não roda de novo
    m = M.carregar(mid, mo.pasta)
    m["estado"] = "executando"
    with pytest.raises(ValueError):
        CP.voltar(m, 1)


def test_checkpoints_ficam_limitados():
    m = {"plano": [{"id": "1", "estado": "ok", "resultado": "x" * 900, "tentativas": 1}], "estado": "pausada"}
    for _ in range(MAX := CP.MAX_CHECKPOINTS + 10):
        CP.registrar(m, m["plano"][0])
    assert len(m["checkpoints"]) == CP.MAX_CHECKPOINTS and len(m["checkpoints"][0]["passos"]["1"]["resultado"]) == 300


# ── guardrails ───────────────────────────────────────────────────────────────
def test_guardrails_padrao_bloqueiam_chave_pasta_do_sistema_e_comando_destrutivo(amb):
    chave = "AIza" + "a" * 30
    assert G.checar_entrada("send_message", {"text": f"minha chave {chave}"})[0] == "bloquear"
    assert G.checar_entrada("web_search", {"query": f"{chave}"})[0] == "ok"      # busca não é envio para fora
    assert G.checar_entrada("file_controller", {"action": "delete", "path": "C:\\Windows\\System32\\x.dll"})[0] == "bloquear"
    assert G.checar_entrada("file_controller", {"action": "delete", "path": "/etc/passwd"})[0] == "bloquear"
    assert G.checar_entrada("file_controller", {"action": "delete", "path": "C:\\Users\\eu\\Downloads\\a.txt"})[0] == "ok"
    assert G.checar_entrada("computer_settings", {"cmd": "rm -rf / --no-preserve-root"})[0] == "bloquear"


def test_guardrails_de_saida_ocultam_cartao_cpf_e_chaves(amb):
    t, usadas = G.filtrar_saida("web_search", "cartão 4111 1111 1111 1111, CPF 123.456.789-09, tel ok")
    assert "4111" not in t and "123.456" not in t and "[oculto]" in t and "tel ok" in t and len(usadas) == 2
    assert G.filtrar_saida("auditoria", "123.456.789-09")[0] == "123.456.789-09"   # ver o próprio dado é permitido


def test_regras_do_usuario_valem_so_endurecem_e_regex_ruim_e_recusada(amb):
    G.adicionar({"nome": "sem_projeto_x", "tool": "send_message", "onde": "entrada", "padrao": "projeto\\s+x", "acao": "bloquear", "motivo": "segredo de trabalho"})
    assert G.checar_entrada("send_message", {"text": "fala do Projeto X"}) == ("ok", "", "")  # case-sensitive: não casou
    assert G.checar_entrada("send_message", {"text": "fala do projeto x"})[0] == "bloquear"
    G.adicionar({"nome": "avisa", "onde": "entrada", "padrao": "banco", "acao": "avisar"})
    assert G.checar_entrada("notes", {"text": "banco"})[0] == "avisar"
    with pytest.raises(ValueError):
        G.adicionar({"nome": "ruim", "onde": "entrada", "padrao": "(", "acao": "bloquear"})
    with pytest.raises(ValueError):
        G.adicionar({"nome": "ruim", "onde": "entrada", "padrao": "x", "acao": "desligar"})
    assert G.remover("sem_projeto_x") == 1 and G.remover("chave_para_fora") == 0   # as padrão não saem
    (amb / "guard.json").write_text(json.dumps([{"nome": "x", "onde": "entrada", "padrao": "(", "acao": "bloquear"}]))
    assert G.checar_entrada("a", {"b": "c"})[0] == "ok"                           # regex inválida no arquivo é ignorada


def test_o_registro_aplica_guardrails_e_trace(amb):
    from core.action_loader import ActionRecord, ActionRegistry
    chamadas = []
    envio = ActionRecord("send_message", handler=lambda parameters, **k: chamadas.append(parameters) or "enviado", file="send_message.py", valid=True)
    leitor = ActionRecord("web_search", handler=lambda parameters, **k: "o cartão 4111 1111 1111 1111 vazou", file="web_search.py", valid=True)
    reg = ActionRegistry({"send_message": envio, "web_search": leitor}, lambda m: None)
    r = reg.run("send_message", {"text": "AIza" + "b" * 30}, {"ator": "missao", "missao": "m1"})
    assert r.startswith("[failed] Guardrail") and chamadas == []
    assert reg.run("send_message", {"text": "oi"}, {}) == "enviado"
    out = reg.run("web_search", {"query": "x"}, {"ator": "agente", "missao": "m1"})
    assert "4111" not in out and "[oculto]" in out
    tl = T.linha_do_tempo("m1")
    assert [(e["nome"], e["ok"], e["extra"]) for e in tl] == [("send_message", False, "guardrail"), ("web_search", True, "")]
    assert not any("AIza" in json.dumps(e) for e in T.ler())                      # a chave não vai para o trace


# ── trace ────────────────────────────────────────────────────────────────────
def test_trace_resume_lentas_e_falhas_e_filtra_por_missao(amb):
    T.registrar("web_search", "missao", "m1", 120, True, {"query": "a"}, "ok", agora=1000)
    T.registrar("web_search", "missao", "m1", 4000, False, {"query": "b"}, "[failed] sem rede", agora=1001)
    T.registrar("weather_report", "voce", "", 30, True, {"city": "Recife"}, "sol", agora=1002)
    st = T.estatisticas()
    assert st["web_search"]["n"] == 2 and st["web_search"]["falhas"] == 1 and st["web_search"]["ms_max"] == 4000
    assert len(T.linha_do_tempo("m1")) == 2 and len(T.linha_do_tempo(minutos=1, agora=1002.5)) == 3
    txt = T.texto("m1", agora=1005)
    assert "✘" in txt and "Mais falham: web_search (1/2)" in txt and "Mais lentas" in txt
    assert T.texto("nenhuma") == "Nada no trace nesse período."


def test_trace_nunca_derruba_e_aninha_segredos(amb, tmp_path):
    T.registrar("x", args={"api_key": "segredo", "text": "t" * 500}, arq=tmp_path / "t.jsonl")
    l = T.ler(tmp_path / "t.jsonl")[0]
    assert l["args"]["api_key"] == "[oculto]" and "500 caracteres" in l["args"]["text"]
    T.registrar("x", arq=tmp_path)                                               # caminho inválido (pasta): engolido
    T._aparar(tmp_path / "t.jsonl", 0)


def test_acoes_missao_checkpoints_rewind_e_novas_ferramentas(amb, monkeypatch):
    from actions import guardrails as AG, trace as AT, missao as AM
    assert "Regras:" in AG.guardrails({"action": "list"})
    assert AG.guardrails({"action": "add", "name": "n", "pattern": "xyz", "effect": "bloquear"}).startswith("[done]")
    assert AG.guardrails({"action": "remove", "name": "chave_para_fora"}).startswith("[failed]")
    assert AT.trace({"minutes": 5}) == "Nada no trace nesse período."
    assert "guardrails" in M.PROIBIDAS
    f, mo, mid = _concluida(amb)
    monkeypatch.setattr(M, "PASTA", mo.pasta)
    monkeypatch.setattr(AM, "motor", lambda: mo)
    monkeypatch.setattr(AM, "gerente", lambda: type("G", (), {"iniciar": lambda s, i: None})())
    assert "#3" in AM.missao({"action": "checkpoints", "id": mid})
    r = AM.missao({"action": "rewind", "id": mid, "checkpoint": 1, "step": "p2", "new_args": '{"query": "novo"}'})
    assert r.startswith("[done]") and "NÃO foi desfeito" in r
    assert AM.missao({"action": "rewind", "id": mid}).startswith("[failed]")
    assert AM.missao({"action": "rewind", "id": mid, "checkpoint": 1, "step": "p2", "new_args": "{ruim"}).startswith("[failed]")
