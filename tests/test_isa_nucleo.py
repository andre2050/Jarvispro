import json
import os
import textwrap
import time

import pytest

from core import isa_arquitetura as AR
from core import isa_autonomia as AU
from core import isa_codigo as IC
from core import isa_modulos as MO
from core import missoes as M


def _projeto(tmp_path, arquivos: dict):
    for rel, cod in arquivos.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(cod), encoding="utf-8")
    return tmp_path


# ── análise de código recente ────────────────────────────────────────────────
RUIM = '''
import os, json, sys
def f(x, lista=[]):
    try:
        eval(x)
    except:
        pass
    os.system("ls")
    senha = "abcdefghijk123"
    return json.dumps(lista)  # TODO arrumar
'''


def test_analisa_problemas_reais_e_ignora_import_usado():
    achados = IC.analisar_texto(textwrap.dedent(RUIM), "x.py")
    tipos = {a["tipo"] for a in achados}
    assert {"perigo", "excecao", "padrao_mutavel", "segredo", "pendencia", "import_sem_uso"} <= tipos
    assert any("sys" in a["msg"] for a in achados if a["tipo"] == "import_sem_uso")
    assert not any("json" in a["msg"] for a in achados if a["tipo"] == "import_sem_uso")
    assert achados[0]["gravidade"] == "alta"                                  # graves primeiro
    assert IC.analisar_texto("def (:", "y.py")[0]["tipo"] == "sintaxe"
    assert IC.analisar_texto("import os\nprint(os.getcwd())\n") == []


def test_mudancas_desde_a_ultima_marca(tmp_path):
    raiz = _projeto(tmp_path, {"core/a.py": "x = 1\n", "core/b.py": "y = 2\n", "tests/t.py": "z=3\n"})
    snap = tmp_path / "snap.json"
    assert IC.mudancas(raiz, snap)["novos"] == ["core/a.py", "core/b.py"]       # sem marca: tudo é novo; tests ignorado
    assert IC.marcar(raiz, snap) == 2
    assert IC.mudancas(raiz, snap) == {"novos": [], "alterados": [], "removidos": []}
    (raiz / "core/a.py").write_text("x = 2\n")
    (raiz / "core/c.py").write_text("w = 1\n")
    (raiz / "core/b.py").unlink()
    assert IC.mudancas(raiz, snap) == {"novos": ["core/c.py"], "alterados": ["core/a.py"], "removidos": ["core/b.py"]}


def test_recentes_por_data_e_relatorio(tmp_path):
    raiz = _projeto(tmp_path, {"core/velho.py": "a=1\n", "core/novo.py": RUIM})
    os.utime(raiz / "core/velho.py", (1000, 1000))
    assert IC.recentes(3, raiz) == ["core/novo.py"]
    r = IC.analisar(["core/novo.py", "core/nao_existe.py"], raiz)
    assert r["arquivos"] == 1 and r["por_gravidade"]["alta"] >= 3
    assert "grave" in IC.texto(r) and "nada preocupante" in IC.texto(IC.analisar(["core/velho.py"], raiz))


# ── arquitetura ──────────────────────────────────────────────────────────────
def test_ciclo_de_topo_e_import_preguicoso(tmp_path):
    raiz = _projeto(tmp_path, {
        "core/a.py": "from core import b\n", "core/b.py": "from core import a\n",                 # ciclo de verdade
        "core/c.py": "def f():\n    from core import d\n", "core/d.py": "from core import c\n",   # preguiçoso: não é ciclo de topo
        "core/e.py": "x = 1\n"})
    g = AR.grafo(raiz, so_topo=True)
    assert AR.ciclos(g) == [["core.a", "core.b"]]
    assert AR.ciclos(AR.grafo(raiz, so_topo=False)) == [["core.a", "core.b"], ["core.c", "core.d"]]


def test_propostas_ordenadas_e_tendencia(tmp_path):
    grande = "\n".join(f"x{i} = {i}" for i in range(AR.LIMITE_ARQUIVO + 50)) + "\n"
    raiz = _projeto(tmp_path, {"core/a.py": "from core import b\n", "core/b.py": "from core import a\n", "core/grande.py": grande,
                               "core/sozinho.py": "x = 1\n"})
    arq = tmp_path / "arq.json"
    r = AR.rodar(raiz, arq)
    assert r["resumo"]["ciclos"] == 1 and r["resumo"]["grandes"] == 1 and "core.sozinho" in r["medidas"]["sem_uso"]
    assert r["propostas"][0]["titulo"].startswith("Desfazer dependência circular")      # melhor impacto/esforço primeiro
    assert r["tendencia"] == {}
    (raiz / "core/b.py").write_text("x = 1\n")                                          # resolveu o ciclo
    r2 = AR.rodar(raiz, arq)
    assert r2["tendencia"]["ciclos"] == -1 and "ciclos -1" in AR.texto(r2) and "Eu só proponho" in AR.texto(r2)


# ── modularização ────────────────────────────────────────────────────────────
def test_saude_dependencias_e_recarga_segura(tmp_path, monkeypatch):
    s = MO.checar("auditoria")
    assert s["ok"] and s["ms"] >= 0 and MO.checar("nao_existe")["ok"] is False
    assert "core.simulacao" not in MO.dependencias("modulos")
    assert isinstance(MO.quem_usa("auditoria"), list)
    # módulo falso com arquivo quebrado: não recarrega e o módulo em uso fica intacto
    pasta = tmp_path / "core"
    pasta.mkdir()
    (pasta / "falso.py").write_text("VALOR = 1\n")
    monkeypatch.setattr(MO, "BASE", tmp_path)
    monkeypatch.setitem(MO.MODULOS, "falso", ("falso_mod", "teste"))
    (tmp_path / "falso_mod.py").write_text("VALOR = 1\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    import importlib
    mod = importlib.import_module("falso_mod")
    (tmp_path / "falso_mod.py").write_text("VALOR = 2\n")
    assert MO.recarregar("falso").startswith("Recarregado") and mod.VALOR == 2
    (tmp_path / "falso_mod.py").write_text("VALOR = (\n")
    assert "NÃO recarreguei" in MO.recarregar("falso") and mod.VALOR == 2
    (tmp_path / "falso_mod.py").write_text("raise RuntimeError('boom')\n")
    assert "NÃO recarreguei" in MO.recarregar("falso") and mod.VALOR == 2
    assert "Não conheço" in MO.recarregar("zzz")


# ── autonomia ────────────────────────────────────────────────────────────────
@pytest.fixture
def limpa(monkeypatch):
    AU._tarefas.clear()
    monkeypatch.setattr(AU, "nivel", lambda: "seguros")
    monkeypatch.setattr(AU, "_aud", lambda *a: None)
    yield
    AU._tarefas.clear()


def test_tarefa_que_cai_descansa_e_volta_ate_3_ciclos(limpa):
    assert [AU.tarefa_caiu("lembretes", t) for t in (1, 2, 3, 4)] == [5.0, 10.0, 15.0, 20.0]
    assert AU.tarefa_caiu("lembretes", 5) == 1800.0 and AU.tarefa_caiu("lembretes", 5) == 7200.0
    assert AU.tarefa_caiu("lembretes", 5) == 7200.0
    assert AU.tarefa_caiu("lembretes", 5) is None                          # 3 ciclos usados: desiste
    assert AU.estado_tarefas()["lembretes"]["ciclos"] == 3


def test_nivel_avisar_nao_regenera(limpa, monkeypatch):
    monkeypatch.setattr(AU, "nivel", lambda: "avisar")
    assert AU.tarefa_caiu("x", 5) is None and AU.tarefa_caiu("x", 2) == 10.0


def test_missao_travada_e_religada_mas_espera_marcada_nao(limpa, tmp_path):
    def faz(mid, estado, passos, t):
        m = {"id": mid, "objetivo": mid, "estado": estado, "criada": t, "plano": passos, "decisoes": [], "log": [{"t": t, "msg": "x"}]}
        M.salvar(m, tmp_path)
    agora = 100_000.0
    faz("parada", "executando", [{"estado": "pendente"}], agora - 3600)
    faz("espera", "executando", [{"estado": "esperando"}], agora - 3600)
    faz("recente", "executando", [{"estado": "pendente"}], agora - 60)
    faz("pausada", "pausada", [{"estado": "pendente"}], agora - 3600)
    assert AU.missoes_travadas(tmp_path, agora) == ["parada"]
    religadas = []
    assert "religuei a missão parada" in AU.religar_missoes(religadas.append, tmp_path, agora)[0] and religadas == ["parada"]
    AU.nivel = lambda: "avisar"
    assert "não mexi" in AU.religar_missoes(religadas.append, tmp_path, agora)[0] and religadas == ["parada"]
