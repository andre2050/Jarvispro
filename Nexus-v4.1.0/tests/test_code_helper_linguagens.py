"""code_helper escreve em qualquer linguagem: extensão certa, mesmo fora do mapa."""
from actions import code_helper as ch


def test_linguagens_conhecidas():
    assert ch._ext_for("Python") == ".py"
    assert ch._ext_for("C#") == ".cs"
    assert ch._ext_for("rust") == ".rs"
    assert ch._ext_for("PowerShell") == ".ps1"
    assert ch._ext_for("lua") == ".lua"


def test_linguagem_desconhecida_usa_ia(monkeypatch):
    monkeypatch.setattr(ch, "_ext_por_ia", lambda lang: ".zzz")
    ch._EXT_MAP.pop("linguagemx", None)
    assert ch._ext_for("LinguagemX") == ".zzz"
    # lembrou: não pergunta de novo
    monkeypatch.setattr(ch, "_ext_por_ia", lambda lang: ".erro")
    assert ch._ext_for("linguagemx") == ".zzz"


def test_sem_linguagem_cai_em_python():
    assert ch._ext_for("") == ".py"


def test_caminho_de_saida(tmp_path):
    assert ch._resolve_save_path(str(tmp_path / "a.go"), "go") == tmp_path / "a.go"
    assert ch._resolve_save_path("", "kotlin").name == "jarvis_code.kt"


def test_clean_code_remove_cerca_de_qualquer_linguagem():
    assert ch._clean_code("```c++\nint main(){}\n```") == "int main(){}"
    assert ch._clean_code("```c#\nclass A{}\n```") == "class A{}"


def test_run_sem_interpretador_nao_quebra(tmp_path):
    f = tmp_path / "x.zig"
    f.write_text("// nada")
    assert "salvo" in ch._run_file(f, [], 5)
