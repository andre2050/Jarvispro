"""Missões de longa duração: plano, simulação, decisões, retomada após reiniciar, conferência, desfazer, auditoria."""
import pytest

from core import auditoria as AU
from core import missoes as M


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr(AU, "ARQUIVO", tmp_path / "aud.jsonl")
    return tmp_path


class Fake:
    """Planejador, executor e demais peças falsas, com tudo registrado."""
    def __init__(self, plano, falhas=0, falta=""):
        self.plano, self.falhas, self.falta = plano, falhas, falta
        self.exec, self.avisos, self.pilha = [], [], []
        self.conferiu = 0

    def planejar(self, objetivo, contexto):
        return self.plano if not contexto else [{"tool": "web_search", "args": {"query": "extra"}, "titulo": "complemento"}]

    def executar(self, tool, args, ctx):
        self.exec.append((tool, dict(args), ctx))
        if tool == "web_search" and args.get("query") == "falha" and self.falhas > 0:
            self.falhas -= 1
            return "failed", "sem rede"
        if tool == "file_controller" and args.get("action") == "move":
            self.pilha.append("mover x")
        return "done", f"ok {tool}"

    def conferir(self, objetivo, passos):
        self.conferiu += 1
        return self.falta if self.conferiu == 1 else ""

    def motor(self, pasta):
        return M.Motor(self.planejar, self.executar, self.conferir, existe=lambda t: t != "inexistente",
                       avisar=lambda t, u=False: self.avisos.append((t, u)), pasta=pasta / "missoes",
                       desfazer_info=lambda: (len(self.pilha), self.pilha[-1] if self.pilha else ""),
                       desfazer_ultimo=lambda: self.pilha.pop() and "desfeito")


PLANO_SEGURO = [
    {"tool": "web_search", "args": {"query": "hotéis em Recife"}, "titulo": "pesquisar hotéis"},
    {"tool": "web_search", "args": {"query": "voos"}, "titulo": "pesquisar voos", "depende": []},
    {"tool": "quick_notes", "args": {"action": "add", "text": "plano"}, "titulo": "anotar plano", "depende": [1, 2]},
]


def test_plano_seguro_roda_sozinho_ate_o_fim(ambiente):
    f = Fake(PLANO_SEGURO)
    mo = f.motor(ambiente)
    m = mo.criar("monte o plano da viagem")
    assert m["estado"] == "plano_pronto" or m["estado"] == "executando"
    # quick_notes é "escreve" → sensível; então o plano precisa de aprovação
    assert m["estado"] == "plano_pronto" and m["simulacao"]["sensiveis"] == 1
    assert mo.passo(m["id"]) == "parada"                          # nada roda antes de aprovar o plano
    assert f.exec == []
    mo.decidir(m["id"], "plano", True)
    assert mo.rodar_ate_parar(m["id"]) == "espera"                # parou numa decisão do passo sensível
    m = M.carregar(m["id"], mo.pasta)
    assert m["estado"] == "aguardando" and [e[0] for e in f.exec] == ["web_search", "web_search"]
    d = [x for x in m["decisoes"] if x["estado"] == "pendente"][0]
    assert "anotar plano" in d["pergunta"] and any(u for _, u in f.avisos)
    mo.decidir(m["id"], d["id"], True)
    assert mo.rodar_ate_parar(m["id"]) == "fim"
    m = M.carregar(m["id"], mo.pasta)
    assert m["estado"] == "concluida" and "3 de 3" in m["relatorio"]
    assert f.exec[-1][2] == {"ator": "missao", "missao": m["id"], "motivo": "anotar plano"}


def test_plano_so_de_leitura_nao_pede_nada(ambiente):
    f = Fake([{"tool": "web_search", "args": {"query": "a"}, "titulo": "a"},
              {"tool": "weather_report", "args": {"city": "Recife"}, "titulo": "b", "depende": [1]}])
    mo = f.motor(ambiente)
    m = mo.criar("pesquisa simples")
    assert m["estado"] == "executando" and m["simulacao"]["sensiveis"] == 0
    assert mo.rodar_ate_parar(m["id"]) == "fim"
    assert M.carregar(m["id"], mo.pasta)["estado"] == "concluida"


def test_negar_pula_dependentes_e_nega_plano_cancela(ambiente):
    f = Fake([{"tool": "send_message", "args": {"contact": "Ana", "message": "oi"}, "titulo": "avisar Ana"},
              {"tool": "web_search", "args": {"query": "depois"}, "titulo": "depois do aviso", "depende": [1]},
              {"tool": "web_search", "args": {"query": "livre"}, "titulo": "independente"}])
    mo = f.motor(ambiente)
    m = mo.criar("avisar e pesquisar")
    mo.decidir(m["id"], "plano", True)
    mo.rodar_ate_parar(m["id"])
    m = M.carregar(m["id"], mo.pasta)
    mo.decidir(m["id"], [d for d in m["decisoes"] if d["estado"] == "pendente"][0]["id"], False)
    assert mo.rodar_ate_parar(m["id"]) == "fim"
    m = M.carregar(m["id"], mo.pasta)
    est = {p["titulo"]: p["estado"] for p in m["plano"]}
    assert est == {"avisar Ana": "negado", "depois do aviso": "pulado", "independente": "ok"}
    assert not any(t == "send_message" for t, _, _ in f.exec)
    m2 = mo.criar("outra")
    mo.decidir(m2["id"], "plano", False)
    assert M.carregar(m2["id"], mo.pasta)["estado"] == "cancelada"


def test_retomar_depois_de_reiniciar(ambiente):
    f = Fake(PLANO_SEGURO[:2] + [{"tool": "web_search", "args": {"query": "terceira"}, "titulo": "terceira", "depende": [2]}])
    mo = f.motor(ambiente)
    m = mo.criar("três passos")
    assert mo.passo(m["id"]) == "trabalhou"                       # só um passo e o "app fecha"
    f2 = Fake([])                                                 # motor novo, mesmo disco
    mo2 = f2.motor(ambiente)
    assert mo2.rodar_ate_parar(m["id"]) == "fim"
    assert len(f2.exec) == 2 and M.carregar(m["id"], mo2.pasta)["estado"] == "concluida"


def test_falha_tenta_de_novo_e_depois_desiste(ambiente):
    f = Fake([{"tool": "web_search", "args": {"query": "falha"}, "titulo": "instável"},
              {"tool": "web_search", "args": {"query": "falha"}, "titulo": "dependente", "depende": [1]}], falhas=1)
    mo = f.motor(ambiente)
    m = mo.criar("insistir")
    assert mo.rodar_ate_parar(m["id"]) == "fim" and M.carregar(m["id"], mo.pasta)["estado"] == "concluida"
    f = Fake([{"tool": "web_search", "args": {"query": "falha"}, "titulo": "quebrado"}], falhas=9)
    mo = f.motor(ambiente)
    m = mo.criar("sempre falha")
    mo.rodar_ate_parar(m["id"])
    m = M.carregar(m["id"], mo.pasta)
    assert m["estado"] == "falhou" and m["plano"][0]["tentativas"] == 2


def test_conferencia_acrescenta_passos_uma_vez(ambiente):
    f = Fake([{"tool": "web_search", "args": {"query": "a"}, "titulo": "a"}], falta="faltou o preço")
    mo = f.motor(ambiente)
    m = mo.criar("com conferência")
    assert mo.rodar_ate_parar(m["id"]) == "fim"
    m = M.carregar(m["id"], mo.pasta)
    assert [p["titulo"] for p in m["plano"]] == ["a", "complemento"] and m["replanos"] == 1 and m["estado"] == "concluida"


def test_validacao_do_plano_descarta_o_que_nao_pode():
    plano, av = M.validar_plano([
        {"tool": "inexistente", "args": {}}, {"tool": "missao", "args": {}}, {"tool": "agent_task", "args": {}},
        {"tool": "web_search", "args": {"query": "x"}, "depende": [9, "x"]}, "lixo",
        {"tool": "_esperar", "args": {"minutos": 99999}}], lambda t: t != "inexistente")
    assert [p["tool"] for p in plano] == ["web_search", "_esperar"] and plano[1]["args"]["minutos"] == 1440
    assert plano[0]["depende"] == [] and len(av) == 4
    assert M.validar_plano("não é lista", lambda t: True)[0] == []
    assert len(M.validar_plano([{"tool": "web_search"}] * 40, lambda t: True)[0]) == M.MAX_PASSOS_PLANO


def test_espera_de_tempo_segura_o_passo_seguinte(ambiente, monkeypatch):
    f = Fake([{"tool": "_esperar", "args": {"minutos": 30}, "titulo": "esperar meia hora"},
              {"tool": "web_search", "args": {"query": "depois"}, "titulo": "checar", "depende": [1]}])
    mo = f.motor(ambiente)
    m = mo.criar("checar mais tarde")
    assert mo.rodar_ate_parar(m["id"]) == "espera" and f.exec == []
    relogio = [M._agora() + 31 * 60]
    monkeypatch.setattr(M, "_agora", lambda: relogio[0])
    assert mo.rodar_ate_parar(m["id"]) == "fim" and len(f.exec) == 1


def test_desfazer_so_o_topo_da_pilha(ambiente):
    f = Fake([{"tool": "file_controller", "args": {"action": "move", "path": "/x/a", "destination": "/y"}, "titulo": "mover a"}])
    mo = f.motor(ambiente)
    m = mo.criar("mover")
    mo.decidir(m["id"], "plano", True)
    mo.rodar_ate_parar(m["id"])
    m = M.carregar(m["id"], mo.pasta)
    mo.decidir(m["id"], [d for d in m["decisoes"] if d["estado"] == "pendente"][0]["id"], True)
    mo.rodar_ate_parar(m["id"])
    m = M.carregar(m["id"], mo.pasta)
    assert m["plano"][0]["desfazer"] == "mover x"
    f.pilha.append("outra coisa")                                  # algo mais novo na frente
    assert "mais recente" in mo.desfazer(m["id"])
    f.pilha.pop()
    assert mo.desfazer(m["id"]) == "desfeito"
    assert M.carregar(m["id"], mo.pasta)["plano"][0]["estado"] == "desfeito"


def test_limites_e_cancelar(ambiente, monkeypatch):
    f = Fake(PLANO_SEGURO[:1])
    mo = f.motor(ambiente)
    ids = [mo.criar(f"m{i}")["id"] for i in range(M.MAX_ATIVAS)]
    with pytest.raises(M.ErroMissao, match="em andamento"):
        mo.criar("uma a mais")
    assert mo.cancelar(ids[0])["estado"] == "cancelada"
    mo.criar("agora cabe")
    with pytest.raises(M.ErroMissao):
        M.carregar("../../etc", mo.pasta)
    m = M.carregar(ids[1], mo.pasta)
    monkeypatch.setattr(M, "_agora", lambda: m["criada"] + 9 * 3600)
    assert mo.passo(ids[1]) == "fim" and "limite" in M.carregar(ids[1], mo.pasta)["relatorio"]


def test_auditoria_registra_a_missao(ambiente):
    f = Fake([{"tool": "web_search", "args": {"query": "a"}, "titulo": "a"}])
    mo = f.motor(ambiente)
    m = mo.criar("auditar")
    mo.rodar_ate_parar(m["id"])
    ls = AU.ler(50)
    assert any("executou web_search" in d["o_que"] and d["missao"] == m["id"] for d in ls) and AU.verificar()[0]


def test_gerente_roda_em_segundo_plano(ambiente):
    f = Fake(PLANO_SEGURO[:2])
    mo = f.motor(ambiente)
    m = mo.criar("em segundo plano")
    g = M.Gerente(mo, ritmo_s=0.01)
    g.iniciar(m["id"])
    for _ in range(300):
        if M.carregar(m["id"], mo.pasta)["estado"] == "concluida":
            break
        import time; time.sleep(0.02)
    g.parar()
    assert M.carregar(m["id"], mo.pasta)["estado"] == "concluida"
    assert g.retomar_todas() == 0
