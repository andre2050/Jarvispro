from core import aprovacoes as A
from core import missoes as M


def test_cinco_sins_viram_sugestao_e_so_a_resposta_cria_a_regra(tmp_path):
    arq = tmp_path / "a.json"
    r = [A.registrar("quick_notes", {"action": "add"}, True, arq) for _ in range(5)]
    assert r[:4] == [None] * 4 and r[4] == "quick_notes:add"
    assert A.sugestoes(arq) == ["quick_notes:add"] and not A.auto("quick_notes", {"action": "add"}, arq)
    assert A.aceitar("quick_notes:add", arq) and A.auto("quick_notes", {"action": "add"}, arq)
    assert A.sugestoes(arq) == []


def test_um_nao_zera_a_sequencia_e_derruba_a_regra(tmp_path):
    arq = tmp_path / "a.json"
    for _ in range(5):
        A.registrar("quick_notes", {"action": "add"}, True, arq)
    A.aceitar("quick_notes:add", arq)
    A.registrar("quick_notes", {"action": "add"}, False, arq)
    assert not A.auto("quick_notes", {"action": "add"}, arq) and A.sugestoes(arq) == []


def test_nunca_para_enviar_apagar_mover_controlar(tmp_path):
    arq = tmp_path / "a.json"
    for tool, args in (("send_message", {}), ("file_controller", {"action": "delete"}), ("file_controller", {"action": "move"}),
                       ("computer_control", {}), ("ferramenta_desconhecida", {})):
        assert not A.elegivel(tool, args)
        for _ in range(6):
            assert A.registrar(tool, args, True, arq) is None
        assert not A.aceitar(assinatura := A.assinatura(tool, args), arq) and not A.auto(tool, args, arq)


def test_recusar_adia_a_pergunta_e_revogar_remove(tmp_path):
    arq = tmp_path / "a.json"
    for _ in range(5):
        A.registrar("quick_notes", {"action": "add"}, True, arq, agora=1000)
    A.recusar("quick_notes:add", arq, agora=1000)
    assert A.sugestoes(arq, agora=1000 + 86400) == [] and A.sugestoes(arq, agora=1000 + 31 * 86400) == ["quick_notes:add"]
    A.aceitar("quick_notes:add", arq)
    assert A.revogar("quick_notes:add", arq) and not A.auto("quick_notes", {"action": "add"}, arq)


def test_motor_usa_a_regra_e_avisa_a_sugestao(tmp_path, monkeypatch):
    from core import auditoria as AU
    monkeypatch.setattr(AU, "ARQUIVO", tmp_path / "aud.jsonl")
    arq = tmp_path / "ap.json"
    avisos, exec_ = [], []
    mo = M.Motor(lambda o, c: [{"tool": "quick_notes", "args": {"action": "add", "text": "x"}, "titulo": "anotar"}],
                 lambda t, a, c: (exec_.append(t) or ("done", "ok")), avisar=lambda t, u=False: avisos.append(t),
                 pasta=tmp_path / "m", auto_aprovar=lambda t, a: A.auto(t, a, arq),
                 aprendeu=lambda t, a, ok: ("sugerir" if A.registrar(t, a, ok, arq) else None))
    for i in range(5):                                   # cinco aprovações manuais
        m = mo.criar(f"anotar {i}")
        mo.decidir(m["id"], "plano", True)
        mo.rodar_ate_parar(m["id"])
        d = [x for x in M.carregar(m["id"], mo.pasta)["decisoes"] if x["estado"] == "pendente"][0]
        mo.decidir(m["id"], d["id"], True)
        mo.rodar_ate_parar(m["id"])
    assert "sugerir" in avisos
    A.aceitar("quick_notes:add", arq)
    m = mo.criar("anotar de novo")
    assert m["estado"] == "executando"                    # com regra, nem o plano precisa de aprovação
    assert mo.rodar_ate_parar(m["id"]) == "fim"           # rodou sem perguntar o passo
    assert M.carregar(m["id"], mo.pasta)["estado"] == "concluida"
