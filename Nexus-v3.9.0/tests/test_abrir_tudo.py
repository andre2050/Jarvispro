import pytest

from core import abrir_tudo as A


@pytest.fixture
def casa(tmp_path):
    for d in ("Downloads", "Documents", "Desktop", "Pictures"):
        (tmp_path / d).mkdir()
    (tmp_path / "Documents" / "relatorio outubro.pdf").write_text("x")
    (tmp_path / "Downloads" / "relatorio setembro.pdf").write_text("x")
    (tmp_path / "Downloads" / "instalar.exe").write_text("x")
    (tmp_path / "Documents" / "ficha.docm").write_text("x")
    return tmp_path


def _run(alvo, casa, app=None):
    ab = []
    r = A.abrir(alvo, ab.append, app or (lambda n: f"app:{n}"), casa)
    return r, ab


def test_pasta_por_apelido(casa):
    r, ab = _run("a pasta de Imagens", casa)
    assert ab == [str(casa / "Pictures")] and r.startswith("[done]")
    assert _run("área de trabalho", casa)[1] == [str(casa / "Desktop")]


def test_arquivo_por_nome_unico_ou_varios(casa):
    r, ab = _run("relatório de outubro", casa)
    assert ab == [str(casa / "Documents" / "relatorio outubro.pdf")]
    r, ab = _run("relatório pdf", casa)
    assert not ab and "mais de um" in r and "outubro" in r and "setembro" in r


def test_nunca_abre_executavel_nem_macro_por_nome_ou_caminho(casa):
    for alvo in (str(casa / "Downloads" / "instalar.exe"), str(casa / "Documents" / "ficha.docm")):
        r, ab = _run(alvo, casa)
        assert not ab and "Não abro" in r
    assert not _run("instalar exe", casa)[1]                        # busca por nome também ignora perigosos


def test_caminho_rede_dotdot_e_inexistente(casa):
    for alvo, msg in (("\\\\servidor\\x", "rede"), (str(casa / "Documents" / ".." / "x"), "“..”"), (str(casa / "nada.txt"), "Não achei")):
        r, ab = _run(alvo, casa)
        assert not ab and msg in r


def test_nome_simples_vai_para_o_open_app(casa):
    r, ab = _run("Calculadora", casa)
    assert r == "app:Calculadora" and not ab
    assert "Diga o que abrir" in _run("  ", casa)[0]
