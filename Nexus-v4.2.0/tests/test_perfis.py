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


def test_ambientes_gravam_cor_e_hub_e_devolvem_no_normal(tmp_path, monkeypatch):
    import memory.config_manager as CM
    cfg = {"ui_color": "#112233", "hud_style": "matrix"}
    monkeypatch.setattr(CM, "load_api_keys", lambda: dict(cfg))
    monkeypatch.setattr(CM, "_save_flag", lambda k, v: cfg.__setitem__(k, v))
    monkeypatch.setattr(CM, "get_hud_style", lambda: cfg["hud_style"])
    monkeypatch.setattr(P, "ARQUIVO", tmp_path / "perfil.json")
    avisos = []
    P.ao_mudar(lambda: avisos.append(1))
    try:
        r = P.definir("trabalho")
        assert "Trabalho ligado" in r and "Sem avisos no celular" in r
        assert cfg["ui_color"] == "#5aa9ff" and cfg["hud_style"] == "gears"
        P.definir("casa")                                        # troca de ambiente sem perder o original
        assert cfg["hud_style"] == "lotus"
        P.definir("normal")
        assert cfg == {"ui_color": "#112233", "hud_style": "matrix"}
        assert len(avisos) == 3
    finally:
        P._ouvintes.clear()


def test_todo_ambiente_usa_visual_e_cor_validos():
    from memory.config_manager import HUD_STYLES
    for chave, p in P.PERFIS.items():
        if p.get("hub"):
            assert p["hub"] in HUD_STYLES, chave
        if p.get("cor"):
            assert len(p["cor"]) == 7 and p["cor"].startswith("#")
    assert P.resolver("vou relaxar em casa") == "casa"
    assert P.silencia_integracao("push", "trabalho") and not P.silencia_integracao("push", "casa")
