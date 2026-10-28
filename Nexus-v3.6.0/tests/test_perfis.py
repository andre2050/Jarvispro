from core import perfis as P


def test_resolver_aliases():
    assert P.resolver("modo jogo") == "jogo"
    assert P.resolver("vou estudar") == "estudo"
    assert P.resolver("Trabalho") == "trabalho"
    assert P.resolver("volta pro normal") == "normal"
    assert P.resolver("banana") is None


def test_definir_e_ativo(tmp_path):
    arq = tmp_path / "perfil.json"
    assert P.ativo(arq) == "normal"
    assert "Estudo" in P.definir("estudo", arq)
    assert P.ativo(arq) == "estudo"
    assert P.definir("xyz", arq).startswith("[failed]")
    assert P.ativo(arq) == "estudo"


def test_bloqueio_e_silencio():
    assert P.bloqueada("youtube_video", "trabalho").startswith("[failed]")
    assert P.bloqueada("web_search", "trabalho") is None
    assert P.bloqueada("youtube_video", "normal") is None
    assert P.silencia_proativo("jogo") and not P.silencia_proativo("normal")
    assert P.silencia_agua("jogo") and not P.silencia_agua("estudo")


def test_bloco_prompt():
    assert P.bloco_prompt("normal") == ""
    assert "ESTUDO" in P.bloco_prompt("estudo")


def test_acao_voz(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "ARQUIVO", tmp_path / "p.json")
    P._cache.update(nome=None, lido_em=0.0)
    from actions.perfil import perfil
    assert "Jogo" in perfil({"name": "jogo"})
    assert "Jogo" in perfil({"action": "status"})
    assert "Normal" in perfil({"name": "normal"})
