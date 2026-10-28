from core import privacidade as P
from core.privacidade import Item


def _cat(tmp_path):
    (tmp_path / "d.json").write_text("[1]", encoding="utf-8")
    (tmp_path / "n.json").write_text("[2,3]", encoding="utf-8")
    return (Item("diario", "Diário e humor", (tmp_path / "d.json",), "x"),
            Item("notas", "Anotações rápidas", (tmp_path / "n.json", tmp_path / "nao.json"), "y"))


def test_estado(tmp_path):
    e = {x["chave"]: x for x in P.estado(_cat(tmp_path))}
    assert e["diario"]["existe"] and e["notas"]["bytes"] == 5


def test_apagar_pede_confirmacao(tmp_path):
    cat = _cat(tmp_path)
    r = P.apagar("diário", False, cat)
    assert "não dá para desfazer" in r and (tmp_path / "d.json").exists()
    assert P.apagar("diário", True, cat) == "Pronto, apaguei Diário e humor."
    assert not (tmp_path / "d.json").exists() and (tmp_path / "n.json").exists()


def test_apagar_tudo_e_desconhecido(tmp_path):
    cat = _cat(tmp_path)
    assert P.apagar("banana", True, cat).startswith("[failed]")
    assert "Pronto" in P.apagar("tudo", True, cat)
    assert not (tmp_path / "n.json").exists()
    assert "Não há nada" in P.apagar("notas", True, cat)


def test_catalogo_nao_inclui_chaves_nem_licenca():
    todos = {a.name for it in P.CATALOGO for a in it.arquivos}
    assert not todos & {"api_keys.json", "licenca.json", "update.json", "email_account.json"}


def test_acao_exige_confirmacao(tmp_path, monkeypatch):
    cat = _cat(tmp_path)
    monkeypatch.setattr(P, "CATALOGO", cat)
    monkeypatch.setattr(P, "apagar", lambda alvo, confirmar=False, catalogo=cat: f"{alvo}:{confirmar}")
    from actions.privacidade import privacidade
    assert privacidade({"action": "delete", "item": "diario"}) == "diario:False"
    assert privacidade({"action": "delete", "item": "diario", "confirmed": True}) == "diario:True"
    assert privacidade({"action": "delete", "item": "notas", "confirmed": True}) == "notas:False"   # sem pergunta antes
