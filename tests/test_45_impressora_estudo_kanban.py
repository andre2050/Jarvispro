"""4.5.0 — impressora, estudo (repetição espaçada + quiz) e Kanban (formato Obsidian)."""
import random
from datetime import date, timedelta
from pathlib import Path

import pytest

from core import estudo as E
from core import impressora as I
from core import kanban as K

HOJE = date(2026, 11, 1)


# ── impressora ────────────────────────────────────────────────────────────────

@pytest.fixture
def lpr(monkeypatch):
    """Um sistema de impressão de mentira (estilo Linux/macOS) que anota os comandos."""
    chamadas = []

    def falso(args, timeout=25):
        chamadas.append(list(args))
        if args[:2] == ["lpstat", "-e"]:
            return 0, "HP_Laser\nEpson_L3150\n"
        if args[:2] == ["lpstat", "-d"]:
            return 0, "system default destination: Epson_L3150\n"
        if args[:2] == ["lpstat", "-o"]:
            return 0, "Epson_L3150-12 andre 1024 Sat\n"
        return 0, ""
    monkeypatch.setattr(I, "_rodar", falso)
    monkeypatch.setattr(I, "_windows", lambda: False)
    return chamadas


def test_lista_e_acha_a_padrao(lpr):
    assert I.listar() == [{"nome": "HP_Laser", "padrao": False}, {"nome": "Epson_L3150", "padrao": True}]
    assert I.escolher("") == "Epson_L3150" and I.escolher("hp") == "HP_Laser"


def test_impressora_desconhecida_ou_ambigua(lpr, monkeypatch):
    with pytest.raises(I.ErroImpressora, match="Não achei essa impressora"):
        I.escolher("canon")
    monkeypatch.setattr(I, "listar", lambda: [{"nome": "HP_A", "padrao": True}, {"nome": "HP_B", "padrao": False}])
    with pytest.raises(I.ErroImpressora, match="Mais de uma"):
        I.escolher("hp")


def test_sem_impressoras(monkeypatch):
    monkeypatch.setattr(I, "listar", lambda: [])
    with pytest.raises(I.ErroImpressora, match="Nenhuma impressora"):
        I.escolher("")


def test_imprime_arquivo_dentro_da_pasta_do_usuario(lpr, tmp_path):
    arq = tmp_path / "doc.pdf"
    arq.write_bytes(b"%PDF")
    msg = I.imprimir_arquivo(str(arq), "hp", 3, raiz=tmp_path)
    assert "doc.pdf" in msg and "HP_Laser" in msg and "3 cópias" in msg
    assert ["lp", "-d", "HP_Laser", "-n", "3", str(arq)] in lpr


def test_recusa_arquivo_fora_tipo_ruim_ou_inexistente(lpr, tmp_path):
    fora = tmp_path.parent / "fora.pdf"
    fora.write_bytes(b"x")
    exe = tmp_path / "x.exe"
    exe.write_bytes(b"x")
    for caminho, trecho in ((fora, "pasta de usuário"), (exe, "Não imprimo"), (tmp_path / "nada.pdf", "Não achei")):
        with pytest.raises(I.ErroImpressora, match=trecho):
            I.validar_arquivo(str(caminho), raiz=tmp_path)
    assert not any(c[0] == "lp" for c in lpr)


def test_copias_ficam_entre_1_e_20():
    assert I._copias(0) == 1 and I._copias(-3) == 1 and I._copias("x") == 1 and I._copias(99) == 20 and I._copias("4") == 4


def test_imprime_texto_e_apaga_o_temporario(lpr, tmp_path):
    msg = I.imprimir_texto("olá mundo", "", 1, pasta_temp=tmp_path)
    assert "Epson_L3150" in msg and not list(tmp_path.glob("*.txt"))
    with pytest.raises(I.ErroImpressora):
        I.imprimir_texto("   ", pasta_temp=tmp_path)
    with pytest.raises(I.ErroImpressora, match="grande demais"):
        I.imprimir_texto("x" * 20001, pasta_temp=tmp_path)


def test_fila_e_cancelar(lpr):
    assert I.fila("") and "Epson_L3150-12" in I.fila("")[0]
    assert "Cancelei" in I.cancelar("hp") and ["cancel", "-a", "HP_Laser"] in lpr


def test_windows_escapa_aspas_e_usa_powershell(monkeypatch, tmp_path):
    cmds = []
    monkeypatch.setattr(I, "_windows", lambda: True)

    def falso(comando, timeout=25):
        cmds.append(comando)
        if "Win32_Printer" in comando:
            return 0, '[{"Name":"Sala d\'Ouro","Default":true}]'
        return 0, ""
    monkeypatch.setattr(I, "_ps", falso)
    arq = tmp_path / "relatório d'ouro.txt"
    arq.write_text("x")
    I.imprimir_arquivo(str(arq), "", 1, raiz=tmp_path)
    assert "d''Ouro" in cmds[-1] and "d''ouro.txt" in cmds[-1] and "Out-Printer" in cmds[-1]


def test_sem_cups_da_mensagem_clara(monkeypatch):
    import subprocess
    monkeypatch.setattr(I, "_windows", lambda: False)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    with pytest.raises(I.ErroImpressora, match="CUPS"):
        I.listar()


def test_acao_pede_confirmacao_antes_de_imprimir(lpr, tmp_path, monkeypatch):
    from actions import printer_control as A
    from core import confirm
    pedidos = []
    monkeypatch.setattr(confirm, "pending_title", lambda: "")
    monkeypatch.setattr(confirm, "request", lambda key, title, detail, run: pedidos.append((title, run)) or "aguardando")
    monkeypatch.setattr(I, "validar_arquivo", lambda c, raiz=None: Path(c))
    assert A.printer_control({"action": "print_file", "path": "/tmp/a.pdf"}) == "aguardando"
    assert pedidos and not any(c[0] == "lp" for c in lpr)          # ainda não imprimiu
    assert A.printer_control({"action": "list"}).startswith("[done]")
    assert A.printer_control({"action": "xyz"}).startswith("[failed]")
    assert A.printer_control({"action": "print_text", "text": ""}).startswith("[failed]")


# ── estudo ────────────────────────────────────────────────────────────────────

def _base(n=5):
    d = {"cartoes": [], "historico": []}
    for i in range(n):
        E.adicionar(d, f"pergunta {i}", f"resposta {i}", "teste", HOJE)
    return d


def test_sm2_acerto_aumenta_intervalo_e_erro_zera():
    d = _base(1)
    c = d["cartoes"][0]
    E.avaliar(c, 5, HOJE)
    assert c["intervalo"] == 1 and c["proxima"] == (HOJE + timedelta(days=1)).isoformat()
    E.avaliar(c, 5, HOJE)
    assert c["intervalo"] == 6
    E.avaliar(c, 5, HOJE)
    assert c["intervalo"] > 6 and c["facilidade"] > 2.5
    E.avaliar(c, 1, HOJE)
    assert c["repeticoes"] == 0 and c["intervalo"] == 1 and c["erros"] == 1


def test_facilidade_nunca_cai_abaixo_de_1_3():
    c = _base(1)["cartoes"][0]
    for _ in range(30):
        E.avaliar(c, 0, HOJE)
    assert c["facilidade"] == 1.3


def test_devidos_so_os_de_hoje_em_diante_ordenados():
    d = _base(3)
    E.avaliar(d["cartoes"][0], 5, HOJE)                  # volta amanhã
    assert [c["id"] for c in E.devidos(d, "", HOJE)] == [2, 3]
    assert len(E.devidos(d, "", HOJE + timedelta(days=1))) == 3
    assert E.devidos(d, "outro", HOJE) == []


def test_importar_varios_formatos_e_repetido_atualiza():
    d = {"cartoes": [], "historico": []}
    n = E.importar(d, "capital da França :: Paris\n2+2 | 4\nH2O => água\nlinha sem separador\n:: vazio", "geral", HOJE)
    assert n == 3 and len(d["cartoes"]) == 3
    E.adicionar(d, "Capital da França", "Paris, claro", "geral", HOJE)
    assert len(d["cartoes"]) == 3 and d["cartoes"][0]["r"] == "Paris, claro"
    with pytest.raises(ValueError):
        E.adicionar(d, "só pergunta", "")


def test_quiz_tem_a_correta_e_distratores_distintos():
    d = _base(6)
    qs = E.montar_quiz(d, 4, "", random.Random(1), HOJE)
    assert len(qs) == 4
    for q in qs:
        assert len(q["opcoes"]) == 4 and len(set(q["opcoes"])) == 4
        assert q["opcoes"][q["correta"]] == "resposta " + q["pergunta"].split()[1]


def test_quiz_com_poucos_cartoes():
    with pytest.raises(ValueError, match="pelo menos 2"):
        E.montar_quiz(_base(1))
    qs = E.montar_quiz(_base(2), 5, "", random.Random(0), HOJE)
    assert len(qs) == 2 and all(len(q["opcoes"]) == 2 for q in qs)


def test_ler_escolha():
    q = {"opcoes": ["Paris", "Roma", "Lima"], "correta": 0}
    assert E.ler_escolha("b", q) == 1 and E.ler_escolha("3", q) == 2 and E.ler_escolha("paris", q) == 0
    assert E.ler_escolha("D", q) is None and E.ler_escolha("", q) is None and E.ler_escolha("9", q) is None


def test_arquivo_quebrado_nao_derruba(tmp_path):
    arq = tmp_path / "e.json"
    arq.write_text("{ruim", encoding="utf-8")
    assert E.carregar(arq) == {"cartoes": [], "historico": []}


def test_acao_study_fluxo_completo(tmp_path, monkeypatch):
    from actions import estudo as A
    monkeypatch.setattr(E, "_ARQ", tmp_path / "e.json")
    monkeypatch.setattr(A.E, "_ARQ", tmp_path / "e.json")
    assert "ainda não tem cartões" in A.study({"action": "stats"})
    assert "3 cartões" in A.study({"action": "import", "text": "a1 :: r1\na2 :: r2\na3 :: r3"})
    assert A.study({"action": "add", "question": "a4", "answer": "r4"}).startswith("[done] Cartão 4")
    assert "Cartão 1" in A.study({"action": "next"}) and A.study({"action": "show", "card": "1"}) == "[done] Resposta: r1"
    assert "volta em 1 dia" in A.study({"action": "grade", "card": "1", "grade": 5})
    assert A.study({"action": "grade", "card": "1", "grade": "x"}).startswith("[failed]")
    assert A.study({"action": "answer", "choice": "A"}).startswith("[failed] Não há quiz")
    ini = A.study({"action": "quiz", "count": 2})
    assert ini.startswith("[done] Quiz começou") and "A)" in ini
    for _ in range(2):
        r = A.study({"action": "answer", "choice": "A"})
    assert "Fim do quiz" in r
    assert "Fim do quiz" not in A.study({"action": "stats"}) and E.carregar(tmp_path / "e.json")["historico"]
    assert A.study({"action": "remove", "card": "a4"}) == "[done] Cartão removido."
    assert A.study({"action": "answer", "choice": "A"}).startswith("[failed]")


# ── Kanban ────────────────────────────────────────────────────────────────────

def test_cria_quadro_no_formato_do_obsidian(tmp_path):
    arq = K.novo("Casa", base=tmp_path)
    t = arq.read_text(encoding="utf-8")
    assert t.startswith("---\n\nkanban-plugin: board\n\n---") and "## A fazer" in t and "## Feito" in t
    assert K.listar(tmp_path) == ["Casa"]
    with pytest.raises(K.ErroKanban, match="já existe"):
        K.novo("Casa", base=tmp_path)


def test_adicionar_mover_e_concluir_marca_x(tmp_path):
    K.novo("Casa", base=tmp_path)
    assert K.adicionar("Casa", "trocar lâmpada", base=tmp_path) == "A fazer"
    assert K.adicionar("Casa", "comprar tinta", "fazendo", base=tmp_path) == "Fazendo"
    assert K.mover("Casa", "lâmpada", "Feito", base=tmp_path) == "Feito"
    t = (tmp_path / "Casa.md").read_text(encoding="utf-8")
    assert "- [x] trocar lâmpada" in t and "- [ ] comprar tinta" in t
    K.mover("Casa", "lampada", "A fazer", base=tmp_path)      # sem acento também acha, e desmarca
    assert "- [ ] trocar lâmpada" in (tmp_path / "Casa.md").read_text(encoding="utf-8")
    assert K.remover("Casa", "tinta", base=tmp_path) == "comprar tinta"


def test_preserva_ajustes_do_obsidian(tmp_path):
    arq = tmp_path / "Q.md"
    arq.write_text("---\n\nkanban-plugin: board\n\n---\n\n## A fazer\n\n- [ ] um\n\n\n%% kanban:settings\n```\n{\"kanban-plugin\":\"board\",\"list-collapse\":[false]}\n```\n%%\n", encoding="utf-8")
    K.adicionar("Q", "dois", base=tmp_path)
    t = arq.read_text(encoding="utf-8")
    assert "- [ ] um" in t and "- [ ] dois" in t and '"list-collapse":[false]' in t and t.count("kanban:settings") == 1


def test_erros_claros(tmp_path):
    K.novo("Casa", base=tmp_path)
    K.adicionar("Casa", "igual um", base=tmp_path)
    K.adicionar("Casa", "igual dois", base=tmp_path)
    with pytest.raises(K.ErroKanban, match="Mais de um"):
        K.mover("Casa", "igual", "Feito", base=tmp_path)
    with pytest.raises(K.ErroKanban, match="coluna"):
        K.adicionar("Casa", "x", "inexistente", base=tmp_path)
    with pytest.raises(K.ErroKanban, match="Não achei o quadro"):
        K.carregar("Nada", tmp_path)
    with pytest.raises(K.ErroKanban, match="Não achei o cartão"):
        K.remover("Casa", "fantasma", base=tmp_path)
    (tmp_path / "Livre.md").write_text("só texto", encoding="utf-8")
    with pytest.raises(K.ErroKanban, match="não parece"):
        K.carregar("Livre", tmp_path)


def test_nome_de_quadro_nao_escapa_da_pasta(tmp_path):
    for ruim in ("../x", "a/b", "..\\x", "", "x" * 50, "a\nb"):
        with pytest.raises(K.ErroKanban):
            K.novo(ruim, base=tmp_path)
    assert not list(tmp_path.parent.glob("x.md"))


def test_pasta_so_dentro_do_usuario(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    (tmp_path / "cofre").mkdir()
    assert K.validar_pasta(str(tmp_path / "cofre")) == (tmp_path / "cofre").resolve()
    with pytest.raises(K.ErroKanban, match="dentro da sua pasta"):
        K.validar_pasta("/tmp")
    with pytest.raises(K.ErroKanban, match="não existe"):
        K.validar_pasta(str(tmp_path / "nada"))


def test_acao_kanban(tmp_path, monkeypatch):
    from actions import kanban as A
    monkeypatch.setattr(K, "pasta", lambda: tmp_path)
    assert "Nenhum quadro" in A.kanban_board({"action": "list"})
    assert "criado" in A.kanban_board({"action": "create", "board": "Casa"})
    assert "A fazer" in A.kanban_board({"action": "add", "board": "Casa", "card": "lavar o carro"})
    assert "Feito" in A.kanban_board({"action": "done", "board": "Casa", "card": "carro"})
    assert "Feito (1): lavar o carro" in A.kanban_board({"action": "show", "board": "Casa"})
    assert A.kanban_board({"action": "add", "board": "../x", "card": "a"}).startswith("[failed]")
