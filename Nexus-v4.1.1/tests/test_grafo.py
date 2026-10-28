from core import grafo as G


def _fontes():
    return {
        "contatos": lambda: [{"tipo": "pessoa", "nome": "Maria", "texto": "irmã, mora em Recife"},
                             {"tipo": "pessoa", "nome": "João", "texto": "sócio do projeto Alfa"}],
        "projetos": lambda: [{"tipo": "projeto", "nome": "Alfa", "texto": "reunião com Maria sexta"}],
        "tarefas": lambda: [{"tipo": "compromisso", "nome": "Ligar para Joao", "texto": "Ligar para Joao sobre Alfa"}],
        "quebrada": lambda: 1 / 0,
    }


def test_constroi_liga_por_mencao_e_guarda_fonte():
    g = G.construir(_fontes())
    r = g.vizinhanca("alfa")
    assert r["achou"] and any(f["para"] == "Maria" and f["fonte"] == "projetos" for f in r["fatos"])
    assert "[fonte: projetos]" in G.texto(r)


def test_sem_acento_e_caminho():
    g = G.construir(_fontes())
    assert g.achar("JOAO") and g.caminho("maria", "joão") is not None
    assert g.caminho("maria", "inexistente") is None
    assert not G.texto(g.vizinhanca("zzz")).startswith("Maria")


def test_salvar_e_carregar(tmp_path):
    g = G.construir(_fontes())
    g.salvar(tmp_path / "g.json")
    g2 = G.Grafo.carregar(tmp_path / "g.json")
    assert len(g2.nos) == len(g.nos) and len(g2.arestas) == len(g.arestas)
    (tmp_path / "ruim.json").write_text("{lixo")
    assert G.Grafo.carregar(tmp_path / "ruim.json").nos == {}


def test_nome_curto_nao_vira_ligacao_e_tipo_invalido_ignorado():
    g = G.Grafo()
    assert g.adicionar("alienigena", "Zed") is None
    a = g.adicionar("pessoa", "Al", "texto")
    g.adicionar("nota", "n", "fala de Al")
    g.ligar_mencoes()
    assert not g.arestas and a


def test_primeira_montagem_e_base_e_depois_o_novo_vira_novidade(tmp_path):
    base = _fontes()
    g0 = G.construir(base)
    assert g0.novidades("maria", 7)["itens"] == []                       # primeira montagem: nada é novidade
    novo = dict(base)
    novo["diario"] = lambda: [{"tipo": "nota", "nome": "diário hoje", "texto": "almocei com Maria e falei do projeto Alfa"}]
    novo["contatos"] = lambda: [{"tipo": "pessoa", "nome": "Maria", "texto": "irmã, mora em Recife, agora trabalha na Acme"},
                                {"tipo": "pessoa", "nome": "João", "texto": "sócio do projeto Alfa"}]
    t0 = 1_000_000.0
    g1 = G.construir(novo, anterior=g0, agora=t0)
    r = g1.novidades("maria", 7, agora=t0 + 3600)
    tipos = {i["tipo"] for i in r["itens"]}
    assert "ligacao" in tipos and "texto" in tipos
    assert any("Acme" in i["texto"] for i in r["itens"] if i["tipo"] == "texto")
    assert "diário" in G.texto_novidades(r)
    assert g1.novidades("maria", 7, agora=t0 + 30 * 86400)["itens"] == []   # passou da janela
    g2 = G.construir(novo, anterior=g1, agora=t0 + 5000)                   # reconstruir de novo não "renova" a data
    assert g2.novidades("maria", 7, agora=t0 + 8000)["itens"][0]["quando"] == t0


def test_atualiza_so_quando_a_fonte_mudou(tmp_path):
    import os
    mem = tmp_path / "mem"
    mem.mkdir()
    (mem / "contatos.json").write_text("[]")
    arq = tmp_path / "g.json"
    assert G.atualizar_se_mudou(arq, _fontes(), mem) is True               # não existia
    assert G.atualizar_se_mudou(arq, _fontes(), mem) is False              # nada mudou
    os.utime(mem / "contatos.json", (arq.stat().st_mtime + 50,) * 2)
    assert G.atualizar_se_mudou(arq, _fontes(), mem) is True
