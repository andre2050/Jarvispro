"""4.5.0 — perfil de ferramentas, ações desativadas e guia do NEXUS."""
import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from core import acoes_desativadas as D
from core import action_loader as L
from core import carga_ferramentas as C
from core import guia_nexus as G

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def reais():
    """As declarações de verdade: as fixas do assistente + as ações que o NEXUS carrega."""
    spec = importlib.util.spec_from_file_location("td_real", RAIZ / "assistant" / "tool_declarations.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    reg = L.discover_actions(RAIZ / "actions", {d["name"] for d in m.TOOL_DECLARATIONS}, lambda s: None, desativadas=set())
    return list(m.TOOL_DECLARATIONS) + reg.get_tool_declarations()


def _d(*nomes):
    return [{"name": n, "description": "x" * 20} for n in nomes]


# ── perfil de ferramentas ─────────────────────────────────────────────────────

def test_completo_nao_muda_nada():
    d = _d("a", "b", "open_app")
    assert C.filtrar(d, "completo") == d


def test_essencial_so_deixa_essenciais_sempre_e_fixadas():
    d = _d("open_app", "web_search", "undo", "tool_load", "coisa_rara", "outra_rara", "fixada")
    nomes = [x["name"] for x in C.filtrar(d, "essencial", usadas=set(), fixadas=["fixada"])]
    assert nomes == ["open_app", "web_search", "undo", "tool_load", "fixada"]


def test_recentes_inclui_o_que_foi_usado():
    base = [n for n in C.ESSENCIAIS][:14]
    d = _d(*base, "rara_usada", "rara_nao_usada")
    nomes = {x["name"] for x in C.filtrar(d, "recentes", usadas={"rara_usada"}, fixadas=[])}
    assert "rara_usada" in nomes and "rara_nao_usada" not in nomes


def test_recentes_sem_historico_mostra_tudo_em_vez_de_esconder():
    d = _d("open_app", "coisa_rara", "outra_rara")
    assert C.filtrar(d, "recentes", usadas=set(), fixadas=[]) == d


def test_ordem_original_e_mantida():
    d = _d("web_search", "open_app", "undo")
    assert [x["name"] for x in C.filtrar(d, "essencial", usadas=set(), fixadas=[])] == ["web_search", "open_app", "undo"]


def test_usadas_recentemente_ignora_o_antigo_e_linhas_ruins():
    agora = datetime(2026, 11, 1, 12, 0, 0)
    f = lambda dias: (agora - timedelta(days=dias)).strftime("%Y-%m-%d %H:%M:%S")   # noqa: E731
    entradas = [{"ts": f(1), "tool": "novo"}, {"ts": f(45), "tool": "velho"}, {"ts": "lixo", "tool": "x"}, {"ts": f(2)}]
    assert C.usadas_recentemente(30, agora, entradas) == {"novo"}


def test_modo_invalido_vira_completo(monkeypatch):
    from core import preferences as P
    monkeypatch.setattr(P, "get", lambda k: "bagunca" if k == "carga_ferramentas" else [])
    assert C.modo_atual() == "completo"


def test_aviso_so_aparece_em_perfil_reduzido():
    assert C.aviso_para_o_modelo("completo") == ""
    assert "tool_load" in C.aviso_para_o_modelo("essencial")


def test_nomes_do_perfil_existem_de_verdade(reais):
    """Se uma ferramenta for renomeada, o perfil não pode ficar apontando para o nada."""
    existentes = {d["name"] for d in reais}
    faltando = [n for n in (*C.SEMPRE, *C.ESSENCIAIS) if n not in existentes]
    assert not faltando, faltando


def test_perfil_essencial_corta_o_peso_pela_metade_ou_mais(reais):
    r = C.resumo(reais, "essencial", usadas=set(), fixadas=[])
    assert r["total"] > 100 and r["visiveis"] < r["total"] / 2
    assert r["tokens_visiveis"] < r["tokens_total"] / 2
    assert "undo" not in r["ocultas"] and "tool_load" not in r["ocultas"]


def test_acao_tool_load_muda_e_fixa(monkeypatch):
    from actions import carga_ferramentas as A
    from core import preferences as P
    guardado = {}
    monkeypatch.setattr(P, "save", lambda v: guardado.update(v))
    monkeypatch.setattr(P, "get", lambda k: guardado.get(k, "completo" if k == "carga_ferramentas" else []))
    assert A.tool_load({"action": "set", "mode": "essencial"}).startswith("[done]") and guardado["carga_ferramentas"] == "essencial"
    assert A.tool_load({"action": "set", "mode": "xyz"}).startswith("[failed]")
    A.tool_load({"action": "pin", "tool": "weather_report"})
    assert guardado["ferramentas_fixas"] == ["weather_report"]
    A.tool_load({"action": "unpin", "tool": "weather_report"})
    assert guardado["ferramentas_fixas"] == []
    assert A.tool_load({"action": "pin"}).startswith("[failed]")


def test_status_mostra_quantas(monkeypatch):
    from actions import carga_ferramentas as A
    monkeypatch.setattr(C, "REGISTRO", None)
    out = A.tool_load({})
    assert out.startswith("[done] Perfil atual") and "ferramentas" in out


# ── ações desativadas ─────────────────────────────────────────────────────────

def test_desativar_reativar_e_persistir(tmp_path):
    arq = tmp_path / "d.json"
    assert D.desativar("noticias", arq) == "noticias" and D.esta_desativada("noticias", arq)
    D.desativar("noticias", arq)
    assert D.carregar(arq) == ["noticias"]
    assert D.reativar("noticias", arq) and not D.esta_desativada("noticias", arq)
    assert not D.reativar("noticias", arq)


def test_protegidas_e_nomes_ruins_nao_passam(tmp_path):
    arq = tmp_path / "d.json"
    for nome in ("guardrails", "privacidade", "manage_actions", "tool_load", "diagnostico"):
        with pytest.raises(ValueError):
            D.desativar(nome, arq)
    for ruim in ("", "../x", "a b", "x;rm"):
        with pytest.raises(ValueError):
            D.desativar(ruim, arq)
    assert D.carregar(arq) == []


def test_arquivo_quebrado_vira_lista_vazia(tmp_path):
    arq = tmp_path / "d.json"
    arq.write_text("{nao json", encoding="utf-8")
    assert D.carregar(arq) == []
    arq.write_text(json.dumps({"desativadas": ["ok_nome", "../mau", 7]}), encoding="utf-8")
    assert D.carregar(arq) == ["ok_nome"]


def test_protegidas_existem_como_acoes_ou_fixas(reais):
    existentes = {d["name"] for d in reais}
    assert {"guardrails", "privacidade", "auditoria", "approvals", "diagnostico"} <= existentes


def _acao(pasta: Path, nome: str):
    (pasta / f"{nome}.py").write_text(
        f'def f(parameters, **k):\n    return "ok"\nTOOL = {{"name": "{nome}", "description": "d", "handler": f}}\n', encoding="utf-8")


def test_loader_nao_carrega_a_desativada(tmp_path):
    pasta = tmp_path / "actions_teste"
    pasta.mkdir()
    _acao(pasta, "zz_um")
    _acao(pasta, "zz_dois")
    reg = L.discover_actions(pasta, set(), lambda s: None, desativadas={"zz_dois"})
    assert reg.names() == {"zz_um"}
    reg2 = L.discover_actions(pasta, set(), lambda s: None, desativadas=set())
    assert reg2.names() == {"zz_um", "zz_dois"}


def test_suspeitas_pega_quem_falha_muito():
    agora = datetime(2026, 11, 1, 12, 0, 0)
    ts = (agora - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    velho = (agora - timedelta(days=40)).strftime("%Y-%m-%d %H:%M:%S")
    e = [{"ts": ts, "tool": "ruim", "result": "[failed] x"} for _ in range(6)]
    e += [{"ts": ts, "tool": "boa", "result": "[done] ok"} for _ in range(6)]
    e += [{"ts": ts, "tool": "pouca", "result": "[failed] x"} for _ in range(2)]
    e += [{"ts": velho, "tool": "antiga", "result": "[failed] x"} for _ in range(9)]
    e += [{"ts": ts, "tool": "guardrails", "result": "[failed] x"} for _ in range(9)]
    achadas = D.suspeitas(e, agora=agora)
    assert [x["nome"] for x in achadas] == ["ruim"] and achadas[0]["taxa"] == 1.0


def test_acao_manage_actions(tmp_path, monkeypatch):
    from actions import gerenciar_acoes as A
    monkeypatch.setattr(D, "_ARQ", tmp_path / "d.json")
    assert "desativada" in A.manage_actions({"action": "disable", "name": "noticias"})
    assert "noticias" in A.manage_actions({"action": "list"})
    assert A.manage_actions({"action": "disable", "name": "guardrails"}).startswith("[failed]")
    assert "reativada" in A.manage_actions({"action": "enable", "name": "noticias"})
    assert "Nenhuma ação desativada" in A.manage_actions({})


# ── guia ──────────────────────────────────────────────────────────────────────

def test_guia_aponta_so_para_ferramentas_que_existem(reais):
    existentes = {d["name"] for d in reais}
    faltando = {g: [f for f in v["ferramentas"] if f not in existentes] for g, v in G.GRUPOS.items()}
    assert not any(faltando.values()), faltando


def test_guia_acha_assunto_por_palavra():
    assert "mensagens" in G.escolher("o que você faz com e-mail?")
    assert "internet" in G.escolher("pesquisar na internet")
    assert "criar" in G.escolher("programar código")
    assert G.escolher("") == list(G.GRUPOS)


def test_guia_texto_e_assunto_desconhecido():
    assert "Controlar o computador" in G.texto("")
    assert G.texto("xyzqwerty").startswith("Não achei")
    assert "Por exemplo" in G.texto("e-mail")


def test_guia_respeita_o_que_esta_carregado():
    assert G.texto("e-mail", disponiveis={"web_search"}).startswith("Nenhuma")
    assert "Mensagens" in G.texto("e-mail", disponiveis={"send_message"})


def test_acao_guia():
    from actions import guia_nexus as A
    assert A.nexus_guide({"topic": "música"}).startswith("[done]")
