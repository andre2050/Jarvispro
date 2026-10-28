import os
import time

import pytest

from core import organizador_inteligente as OI


@pytest.fixture
def pasta(tmp_path):
    p = tmp_path / "area" / "Downloads"
    p.mkdir(parents=True)
    old = time.time() - 3600
    for n in ("foto.jpg", "nota fiscal maio.pdf", "relatorio.pdf", "setup.exe", ".oculto", "baixando.crdownload"):
        f = p / n
        f.write_text("x")
        os.utime(f, (old, old))
    (p / "subpasta").mkdir()
    (p / "novo.txt").write_text("x")                                        # recém-criado
    return p


def test_plano_por_tipo_e_o_que_fica(pasta, tmp_path):
    p = OI.plano(pasta, tmp_path / "r.json")
    destinos = {a.name: d.name for a, d, _ in p["mover"]}
    assert destinos == {"foto.jpg": "Imagens", "nota fiscal maio.pdf": "Documentos", "relatorio.pdf": "Documentos", "setup.exe": "Instaladores"}
    assert set(p["ficam"]) == {"oculto", "em andamento", "recente"}
    assert (pasta / "foto.jpg").exists()                                    # plano não mexe


def test_regra_sua_vence_o_tipo_e_destino_e_validado(pasta, tmp_path):
    rg = tmp_path / "r.json"
    OI.adicionar_regra("nota fiscal", "pdf", "Documentos/Notas", rg)
    destinos = {a.name: str(d.relative_to(pasta)) for a, d, _ in OI.plano(pasta, rg)["mover"]}
    assert destinos["nota fiscal maio.pdf"] == "Documentos/Notas" and destinos["relatorio.pdf"] == "Documentos"
    for ruim in ("../fora", "", "a/b/c/d"):
        with pytest.raises(ValueError):
            OI.adicionar_regra("x", "", ruim, rg)
    with pytest.raises(ValueError):
        OI.adicionar_regra("", "", "Pasta", rg)


def test_aplicar_nao_sobrescreve_e_desfaz(pasta, tmp_path):
    (pasta / "Imagens").mkdir()
    (pasta / "Imagens" / "foto.jpg").write_text("ja existia")
    reg = tmp_path / "reg.json"
    p = OI.plano(pasta, tmp_path / "r.json")
    assert "Arrumei 4" in OI.aplicar(p, reg)
    assert (pasta / "Imagens" / "foto.jpg").read_text() == "ja existia" and (pasta / "Imagens" / "foto (2).jpg").exists()
    assert not (pasta / "setup.exe").exists() and (pasta / ".oculto").exists() and (pasta / "novo.txt").exists()
    assert "Voltaram 4" in OI.desfazer(reg)
    assert (pasta / "foto.jpg").exists() and (pasta / "Imagens" / "foto.jpg").read_text() == "ja existia"
    assert not (pasta / "Instaladores").exists()                            # pasta criada e vazia foi removida
    assert "Não há" in OI.desfazer(reg)


def test_pastas_perigosas_recusadas(tmp_path):
    for ruim in ("/", str(os.path.expanduser("~")), tmp_path / "nao_existe"):
        with pytest.raises(ValueError):
            OI.plano(ruim)


def test_acao_apply_pede_confirmar_e_plan_nao_mexe(pasta, monkeypatch):
    from actions import organizador_inteligente as A
    from core import confirm
    pedidos = []
    monkeypatch.setattr(confirm, "pending_title", lambda: None)
    monkeypatch.setattr(confirm, "request", lambda **k: (pedidos.append(k) or "pedi"))
    assert "iriam para" in A.organizar_pasta({"folder_path": str(pasta)})
    assert A.organizar_pasta({"action": "apply", "folder_path": str(pasta)}) == "pedi" and pedidos
    assert (pasta / "foto.jpg").exists()                                    # só mexe após confirmar
    assert A.organizar_pasta({"folder_path": "/"}).startswith("[failed]")
