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
