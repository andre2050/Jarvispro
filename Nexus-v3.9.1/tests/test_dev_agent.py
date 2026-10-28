"""Testes de actions/dev_agent.py com uma "IA" de mentira: o fluxo inteiro roda de verdade
(arquivos, conferência, execução do programa), só as respostas do modelo são roteirizadas."""
import json
import threading
import time
from types import SimpleNamespace

import pytest

from actions import dev_agent as DA
from core import dev_projeto as DP

_DORME = time.sleep      # o de verdade: a fixture abaixo troca time.sleep por um que não espera


class IAFalsa:
    """Responde conforme o texto do pedido. `roteiro` é uma lista de (trecho, resposta|função);
    a primeira cujo trecho aparece no prompt vale. Guarda todos os prompts em `.chamadas`."""

    def __init__(self, roteiro):
        self.roteiro = roteiro
        self.chamadas = []

    def __call__(self, tier=None):
        return self

    def generate_content(self, prompt):
        self.chamadas.append(prompt)
        for trecho, resp in self.roteiro:
            if trecho in prompt:
                texto = resp(prompt) if callable(resp) else resp
                return SimpleNamespace(text=texto)
        raise RuntimeError(f"a IA falsa não tem resposta para: {prompt[:120]!r}")


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr(DA, "PROJECTS_DIR", tmp_path / "NexusProjects")
    monkeypatch.setattr(DA, "_open_vscode", lambda pasta: True)
    monkeypatch.setattr(DA.webbrowser, "open", lambda url: True)
    monkeypatch.setattr(DA, "_checar_no_navegador", lambda obra: [])
    monkeypatch.setattr(DA.time, "sleep", lambda s: None)
    return tmp_path


def _ia(monkeypatch, roteiro):
    ia = IAFalsa(roteiro)
    monkeypatch.setattr(DA, "_get_model", ia)
    return ia


PLANO_SITE = json.dumps({
    "project_name": "Site da Padaria", "entry_point": "index.html", "run_command": "open index.html",
    "files": [
        {"path": "index.html", "description": "página inicial"},
        {"path": "styles.css", "description": "estilos"},
        {"path": "../../Startup/evil.bat", "description": "tentativa de escrever fora da pasta"},
    ],
    "dependencies": ["--index-url=http://evil"],
})
HTML = ('<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8"><title>Padaria</title>'
        '<link rel="stylesheet" href="styles.css"></head><body><h1 id="t">Pão quente</h1>'
        '<script src="script.js"></script></body></html>')


# ── site ────────────────────────────────────────────────────────────────────

def test_cria_site_e_completa_o_arquivo_que_a_ia_esqueceu(ambiente, monkeypatch):
    # o plano não listou script.js, mas o HTML chama: a conferência tem que perceber e escrever
    ia = _ia(monkeypatch, [
        ("Create a minimal, complete file plan", PLANO_SITE),
        ("Content of script.js", "document.getElementById('t').textContent = 'Pão quente!';"),
        ("Content of index.html", HTML),
        ("Content of styles.css", "body { font-family: sans-serif; }"),
    ])
    r = DA._criar("um site para a minha padaria", "html", "", 30)
    pasta = ambiente / "NexusProjects" / "Site_da_Padaria"
    assert r.startswith("[done]"), r
    assert (pasta / "index.html").exists() and (pasta / "styles.css").exists() and (pasta / "script.js").exists()
    assert not (ambiente / "Startup").exists()                       # o caminho malicioso foi recusado
    assert DP.verificar_projeto(pasta, web=True) == []
    meta = DP.ler_meta(pasta)
    assert meta["web"] is True and meta["entry_point"] == "index.html"
    assert "index.html" in (pasta / "LEIA-ME.txt").read_text(encoding="utf-8")
    # o CSS foi escrito olhando o HTML que já existia
    prompt_css = next(p for p in ia.chamadas if "Content of styles.css" in p)
    assert "Pão quente" in prompt_css


def test_html_escrito_primeiro_depois_css_e_js(ambiente, monkeypatch):
    ordem = []

    def marca(nome):
        def f(prompt):
            ordem.append(nome)
            return {"index.html": HTML, "styles.css": "a{}", "script.js": "var x = 1;"}[nome]
        return f

    plano = json.dumps({"entry_point": "index.html", "files": [
        {"path": "script.js"}, {"path": "styles.css"}, {"path": "index.html"}]})
    _ia(monkeypatch, [("file plan", plano), ("Content of script.js", marca("script.js")),
                      ("Content of styles.css", marca("styles.css")), ("Content of index.html", marca("index.html"))])
    DA._criar("site", "html", "ordem", 30)
    assert ordem == ["index.html", "styles.css", "script.js"]


def test_ia_corta_o_arquivo_no_meio_e_o_agente_corrige(ambiente, monkeypatch):
    html_cortado = HTML.replace("</body></html>", "")           # a IA parou no meio
    plano = json.dumps({"entry_point": "index.html", "files": [
        {"path": "index.html"}, {"path": "styles.css"}, {"path": "script.js"}]})
    _ia(monkeypatch, [
        ("file plan", plano),
        ("Fix the file below", HTML),
        ("Content of index.html", html_cortado),
        ("Content of styles.css", "a{}"), ("Content of script.js", "var x=1;"),
    ])
    r = DA._criar("site", "html", "cortado", 30)
    assert r.startswith("[done]"), r
    assert "</html>" in (ambiente / "NexusProjects" / "cortado" / "index.html").read_text(encoding="utf-8")


def test_erro_de_javascript_no_navegador_e_corrigido(ambiente, monkeypatch):
    chamadas = {"n": 0}

    def navegador(obra):
        chamadas["n"] += 1
        js = obra.ler("script.js")
        if "naoExiste" in js:
            return [{"arquivo": "index.html", "tipo": "execucao",
                     "problema": "erro de JavaScript ao abrir a página: ReferenceError: naoExiste is not defined at script.js:1"}]
        return []

    monkeypatch.setattr(DA, "_checar_no_navegador", navegador)
    plano = json.dumps({"entry_point": "index.html", "files": [{"path": "index.html"}, {"path": "styles.css"}, {"path": "script.js"}]})
    _ia(monkeypatch, [
        ("file plan", plano),
        ("Fix the file below", "console.log('ok');"),
        ("Content of index.html", HTML), ("Content of styles.css", "a{}"),
        ("Content of script.js", "naoExiste();"),
    ])
    r = DA._criar("site", "html", "js_quebrado", 30)
    assert r.startswith("[done]"), r
    assert "naoExiste" not in (ambiente / "NexusProjects" / "js_quebrado" / "script.js").read_text(encoding="utf-8")


def test_nao_escreve_por_cima_de_projeto_existente(ambiente, monkeypatch):
    plano = json.dumps({"project_name": "meu", "entry_point": "index.html", "files": [{"path": "index.html"}]})
    _ia(monkeypatch, [("file plan", plano), ("Content of index.html", HTML.replace("styles.css", "x.css").replace('<link rel="stylesheet" href="x.css">', "").replace('<script src="script.js"></script>', ""))])
    DA._criar("site", "html", "", 30)
    DA._criar("site", "html", "", 30)
    pastas = sorted(p.name for p in (ambiente / "NexusProjects").iterdir())
    assert pastas == ["meu", "meu_2"]


# ── programa (Python) ───────────────────────────────────────────────────────

PLANO_PY = json.dumps({"project_name": "calc", "entry_point": "main.py", "run_command": "python main.py",
                       "files": [{"path": "ops.py", "description": "operações", "imports": []},
                                 {"path": "main.py", "description": "entrada", "imports": ["ops"]}],
                       "dependencies": []})


def test_programa_roda_na_primeira(ambiente, monkeypatch):
    _ia(monkeypatch, [("file plan", PLANO_PY),
                      ("Content of ops.py", "def soma(a, b):\n    return a + b\n"),
                      ("Content of main.py", "from ops import soma\nprint('resultado', soma(2, 3))\n")])
    r = DA._criar("calculadora", "python", "", 30)
    assert r.startswith("[done]") and "resultado 5" in r, r
    assert "1 run attempt" in r


def test_erro_em_tempo_de_execucao_e_corrigido(ambiente, monkeypatch):
    _ia(monkeypatch, [("file plan", PLANO_PY),
                      ("Fix the file below", "from ops import soma\nprint('resultado', soma(2, 3))\n"),
                      ("Content of ops.py", "def soma(a, b):\n    return a + b\n"),
                      ("Content of main.py", "from ops import soma\nprint(variavel_inexistente)\n")])
    r = DA._criar("calculadora", "python", "", 30)
    assert r.startswith("[done]") and "resultado 5" in r, r
    assert "2 run attempts" in r


def test_import_de_funcao_que_ninguem_escreveu_e_pego_antes_de_rodar(ambiente, monkeypatch):
    # main importa "multiplica", que ops.py não define. A conferência estática acha, sem rodar nada.
    _ia(monkeypatch, [("file plan", PLANO_PY),
                      ("Fix the file below", "from ops import soma\nprint('resultado', soma(2, 3))\n"),
                      ("Content of ops.py", "def soma(a, b):\n    return a + b\n"),
                      ("Content of main.py", "from ops import soma, multiplica\nprint(multiplica(2, 3))\n")])
    r = DA._criar("calculadora", "python", "", 30)
    assert r.startswith("[done]"), r
    assert "1 run attempt" in r                         # já saiu certo na primeira execução


def test_programa_com_erro_que_nao_se_resolve_termina_como_failed(ambiente, monkeypatch):
    _ia(monkeypatch, [("file plan", PLANO_PY),
                      ("Fix the file below", "raise ValueError('sempre')\n"),
                      ("Content of ops.py", "X = 1\n"),
                      ("Content of main.py", "raise ValueError('sempre')\n")])
    r = DA._criar("x", "python", "", 30)
    assert r.startswith("[failed]") and "ValueError" in r


def test_comando_de_execucao_perigoso_nao_e_executado(ambiente, monkeypatch):
    plano = json.dumps({"entry_point": "main.py", "run_command": "powershell -c Remove-Item -Recurse C:\\x",
                        "files": [{"path": "main.py"}]})
    _ia(monkeypatch, [("file plan", plano), ("Content of main.py", "print('oi')\n")])
    r = DA._criar("x", "python", "perigo", 30)
    assert r.startswith("[unverified]") and "not run automatically" in r


def test_dependencias_vao_para_o_venv_nunca_para_o_python_do_nexus(ambiente, monkeypatch):
    instalados = []
    monkeypatch.setattr(DA, "_python_do_projeto", lambda obra: "/venv/python")

    def falso_run(cmd, **kw):
        if cmd[1:3] == ["-m", "pip"]:
            instalados.append(cmd)
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="oi\n", stderr="")

    monkeypatch.setattr(DA.subprocess, "run", falso_run)
    plano = json.dumps({"entry_point": "main.py", "run_command": "python main.py",
                        "files": [{"path": "main.py"}], "dependencies": ["requests", "-r outra.txt", "flask==3.0"]})
    _ia(monkeypatch, [("file plan", plano), ("Content of main.py", "print('oi')\n")])
    r = DA._criar("x", "python", "deps", 30)
    assert r.startswith("[done]"), r
    assert instalados and instalados[0][0] == "/venv/python"
    assert instalados[0][-2:] == ["requests", "flask==3.0"]            # a opção "-r outra.txt" nunca chegou ao pip


def test_sem_venv_nada_e_instalado(ambiente, monkeypatch):
    monkeypatch.setattr(DA, "_python_do_projeto", lambda obra: None)
    chamadas = []
    monkeypatch.setattr(DA.subprocess, "run", lambda cmd, **kw: chamadas.append(cmd) or SimpleNamespace(returncode=0, stdout="ok\n", stderr=""))
    from actions.dev_agent import _Obra
    obra = _Obra("x", "python", ambiente)
    msg = DA._pip_install(obra, ["requests"])
    assert "installed nothing" in msg and chamadas == []


def test_modulo_faltando_so_instala_biblioteca_de_verdade(ambiente, monkeypatch):
    pedidos = []
    monkeypatch.setattr(DA, "_pip_install", lambda obra, pacotes: pedidos.append(pacotes) or "installed: x")
    from actions.dev_agent import _Obra
    (ambiente / "proj").mkdir()
    (ambiente / "proj" / "meu_modulo.py").write_text("x=1", encoding="utf-8")
    obra = _Obra("x", "python", ambiente / "proj")
    assert DA._auto_instalar_faltante(obra, "ModuleNotFoundError: No module named 'cv2'")
    assert pedidos == [["opencv-python"]]
    assert not DA._auto_instalar_faltante(obra, "ModuleNotFoundError: No module named 'tkinter'")       # biblioteca padrão
    assert not DA._auto_instalar_faltante(obra, "ModuleNotFoundError: No module named 'meu_modulo'")    # do próprio projeto
    assert len(pedidos) == 1


# ── planejamento com defeito ────────────────────────────────────────────────

def test_plano_que_nao_e_json(ambiente, monkeypatch):
    _ia(monkeypatch, [("file plan", "desculpe, não consigo")])
    assert DA._criar("x", "python", "", 30).startswith("[failed] Planning failed")


def test_plano_so_com_caminhos_maliciosos(ambiente, monkeypatch):
    _ia(monkeypatch, [("file plan", json.dumps({"files": [{"path": "../../x.py"}, {"path": "C:/y.py"}]}))])
    assert DA._criar("x", "python", "", 30).startswith("[failed] Planning failed")


def test_limite_de_uso_da_ia(ambiente, monkeypatch):
    def limite(prompt):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")
    _ia(monkeypatch, [("file plan", limite)])
    assert "rate limit" in DA._criar("x", "python", "", 30)


def test_resposta_com_explicacao_em_volta_do_codigo():
    texto = "Claro! Aqui está:\n```python\nprint('oi')\n```\nEspero que ajude."
    assert DA._strip_fences(texto) == "print('oi')"
    assert DA._strip_fences("```html\n<p>a</p>\n```") == "<p>a</p>"
    assert DA._strip_fences("sem cercas") == "sem cercas"
    assert DA._json_do_texto('Aqui: {"a": 1} fim') == {"a": 1}


# ── alterar, listar, abrir, desfazer ────────────────────────────────────────

def _site_pronto(ambiente, monkeypatch):
    plano = json.dumps({"project_name": "padaria", "entry_point": "index.html", "files": [
        {"path": "index.html"}, {"path": "styles.css"}, {"path": "script.js"}]})
    _ia(monkeypatch, [("file plan", plano), ("Content of index.html", HTML),
                      ("Content of styles.css", "button { background: blue; }\n" + "/* x */\n" * 120),
                      ("Content of script.js", "var x = 1;")])
    DA._criar("site da padaria", "html", "", 30)
    return ambiente / "NexusProjects" / "padaria"


def test_alterar_projeto_com_backup_e_desfazer(ambiente, monkeypatch):
    pasta = _site_pronto(ambiente, monkeypatch)
    original = (pasta / "styles.css").read_text(encoding="utf-8")
    novo = original.replace("blue", "green")
    ia = _ia(monkeypatch, [
        ("changing an EXISTING project", json.dumps({"changes": [
            {"path": "styles.css", "action": "edit", "what": "botão verde"},
            {"path": "../../fora.css", "action": "edit", "what": "malicioso"}]})),
        ("Content of styles.css", novo) if False else ("New content of styles.css", novo),
    ])
    r = DA._alterar("padaria", "deixa o botão verde", 30)
    assert r.startswith("[done]") and "styles.css" in r and "undo" in r, r
    assert "green" in (pasta / "styles.css").read_text(encoding="utf-8")
    assert not (ambiente / "fora.css").exists()
    assert DP.ler_meta(pasta)["history"][0]["files"] == ["styles.css"]
    # o prompt de alteração recebeu o arquivo INTEIRO, não uma versão cortada
    assert "blue" in next(p for p in ia.chamadas if "New content of styles.css" in p)

    assert DA._desfazer("padaria").startswith("[done]")
    assert (pasta / "styles.css").read_text(encoding="utf-8") == original
    assert DA._desfazer("padaria").startswith("[failed]")               # nada mais a desfazer


def test_alterar_recusa_resposta_que_encolheu_o_arquivo(ambiente, monkeypatch):
    pasta = _site_pronto(ambiente, monkeypatch)
    original = (pasta / "styles.css").read_text(encoding="utf-8")
    _ia(monkeypatch, [("changing an EXISTING project", json.dumps({"changes": [{"path": "styles.css", "what": "x"}]})),
                      ("New content of styles.css", "button { }")])             # resposta "resumida"
    r = DA._alterar("padaria", "muda", 30)
    assert r.startswith("[failed]")
    assert (pasta / "styles.css").read_text(encoding="utf-8") == original


def test_alterar_projeto_que_nao_existe(ambiente):
    assert DA._alterar("fantasma", "muda", 30).startswith("[failed]")


def test_listar_e_abrir(ambiente, monkeypatch):
    assert "No projects" in DA._listar()
    _site_pronto(ambiente, monkeypatch)
    assert "padaria" in DA._listar()
    abertos = []
    monkeypatch.setattr(DA.webbrowser, "open", lambda url: abertos.append(url) or True)
    assert DA._abrir("a padaria").startswith("[done]") and abertos
    assert DA._abrir("inexistente xyz").startswith("[failed]")


# ── segundo plano ───────────────────────────────────────────────────────────

def test_em_segundo_plano_responde_na_hora_e_avisa_no_fim(ambiente, monkeypatch):
    liberar = threading.Event()
    faladas = []

    def trabalho():
        liberar.wait(5)
        return "[done] pronto"

    r = DA._em_segundo_plano("create: teste", trabalho, faladas.append)
    assert r.startswith("[done] I started")
    # com um projeto em andamento, outro pedido é recusado com educação
    r2 = DA._em_segundo_plano("create: outro", lambda: "x", faladas.append)
    assert r2.startswith("[failed]") and "still working" in r2
    liberar.set()
    for _ in range(100):
        if faladas:
            break
        _DORME(0.02)
    assert faladas and faladas[0].startswith("[DEV_DONE]") and "[done] pronto" in faladas[0]
    # terminou: libera para o próximo
    for _ in range(100):
        if DA._trava.acquire(blocking=False):
            DA._trava.release()
            break
        _DORME(0.02)
    assert DA._em_segundo_plano("create: de novo", lambda: "ok", lambda t: None).startswith("[done] I started")


def test_em_segundo_plano_erro_vira_aviso(ambiente):
    faladas = []

    def quebra():
        raise RuntimeError("boom")

    DA._em_segundo_plano("create: x", quebra, faladas.append)
    for _ in range(100):
        if faladas:
            break
        _DORME(0.02)
    assert faladas and "[failed]" in faladas[0] and "boom" in faladas[0]


def test_dev_agent_sem_speak_roda_direto(ambiente, monkeypatch):
    _ia(monkeypatch, [("file plan", PLANO_PY), ("Content of ops.py", "X = 1\n"),
                      ("Content of main.py", "print('oi')\n")])
    r = DA.dev_agent({"description": "um programa", "language": "python"})
    assert r.startswith("[done]")


def test_dev_agent_parametros_invalidos(ambiente):
    assert DA.dev_agent({}).startswith("[failed]")
    assert DA.dev_agent({"action": "modify"}).startswith("[failed]")
    assert "No projects" in DA.dev_agent({"action": "list"})


def test_tool_declarada_corretamente():
    from core.action_loader import _validate
    import actions.dev_agent as modulo
    rec = _validate(modulo, "dev_agent.py")
    assert rec.valid, rec.error
    assert rec.name == "dev_agent"
