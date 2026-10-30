"""Resumo diário: junta agenda, e-mails importantes e tarefas; fonte com defeito não derruba o resto."""
from core import resumo_diario as R


def _m(de, assunto, corpo="texto"):
    return {"from_name": de, "from_addr": "", "subject": assunto, "body": corpo, "date": "28/10 09:00"}


def test_importancia_por_vip_e_palavras():
    assert R.importancia(_m("Ana Souza", "oi"), ["ana"]) == 3
    assert R.importancia(_m("Loja", "Fatura vence amanhã"), []) >= 6
    assert R.importancia(_m("Loja", "Promoção de verão"), []) == 0


def test_resumo_completo_ordena_e_limita():
    emails = [_m("Spam", "Oferta"), _m("Banco", "Boleto vence hoje"), _m("Ana", "Reunião importante"),
              _m("Chefe", "bom dia"), _m("X", "contrato urgente prazo"), _m("Y", "fatura pagamento")]
    t = R.montar(agenda=lambda: "Agenda hoje: 10:00 Dentista",
                 emails=lambda: emails,
                 tarefas=lambda: [{"titulo": "Pagar IPTU", "prazo": "2026-10-28"}], vips=["chefe"])
    assert "10:00 Dentista" in t and "Pagar IPTU" in t
    assert t.count("<email>") == R.MAX_EMAILS and "Oferta" not in t
    assert "contrato urgente prazo" in t          # a mais pontuada vem primeiro
    assert "texto de terceiros" in t


def test_fonte_com_defeito_e_pulada():
    def quebra():
        raise RuntimeError("sem internet")
    t = R.montar(agenda=quebra, emails=quebra, tarefas=lambda: [], vips=[])
    assert "AGENDA: não consegui ler" in t and "E-MAILS: não consegui ler" in t and "nenhuma tarefa" in t


def test_acao_e_vips(tmp_path, monkeypatch):
    from actions import resumo_diario as A
    salvo = {}
    import memory.config_manager as CM
    monkeypatch.setattr(CM, "save_plugin_config", lambda ns, v: salvo.update({ns: v}))
    assert A.resumo_diario({"action": "set_vips", "vips": "Ana, banco"}).startswith("[done]")
    assert salvo["resumo_diario"]["vips"] == ["ana", "banco"]
    assert "Quais remetentes" in A.resumo_diario({"action": "set_vips"})
    assert A.TOOL["name"] == "resumo_diario"
