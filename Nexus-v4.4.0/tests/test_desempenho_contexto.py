import os
import time
from datetime import date

import pytest

from core import contexto_projeto as CP
from core import desempenho_proativo as D


@pytest.fixture(autouse=True)
def limpo():
    D.limpar()
    yield
    D.limpar()


def _leitor(cpu_chrome=5.0, mem_chrome=500, pc_mem=50, extra=None):
    procs = [{"nome": "chrome.exe", "cpu": cpu_chrome, "mem_mb": mem_chrome}, {"nome": "svchost.exe", "cpu": 90, "mem_mb": 9000}] + (extra or [])
    return lambda: {"cpu_pct": 10, "mem_pct": pc_mem, "nucleos": 4, "ram_mb": 16000, "procs": procs}


def test_cpu_alta_sustentada_avisa_com_dica_e_ignora_sistema():
    msgs = []
    for i in range(5):
        msgs += D.passo(False, _leitor(cpu_chrome=240), agora=1000 + i * 30)         # 240/4 núcleos = 60%
    assert len(msgs) == 1 and "chrome.exe" in msgs[0] and "60%" in msgs[0] and "abas" in msgs[0] and "svchost" not in msgs[0]


def test_pico_curto_nao_avisa():
    msgs = []
    for i, c in enumerate([5, 300, 5, 300, 5]):
        msgs += D.passo(False, _leitor(cpu_chrome=c), agora=1000 + i * 30)
    assert msgs == []


def test_aviso_nao_repete_em_2h_e_volta_depois():
    for i in range(5):
        D.passo(False, _leitor(cpu_chrome=240), agora=1000 + i * 30)
    assert D.passo(False, _leitor(cpu_chrome=240), agora=1200) == []
    assert D.passo(False, _leitor(cpu_chrome=240), agora=1200 + 3 * 3600) != [] or D.passo(False, _leitor(cpu_chrome=240), agora=1260 + 3 * 3600) != []


def test_memoria_alta_e_vazamento():
    msgs = D.passo(False, _leitor(mem_chrome=5000), agora=1) + D.passo(False, _leitor(mem_chrome=5000), agora=2) + D.passo(False, _leitor(mem_chrome=5000), agora=3) + D.passo(False, _leitor(mem_chrome=5000), agora=4)
    assert "31%" in msgs[0] or "5.0 GB" in msgs[0]
    D.limpar()
    out = []
    for i, m in enumerate([300, 500, 700, 900]):
        out += D.passo(False, _leitor(mem_chrome=m), agora=10 + i)
    assert out and "vazamento" in out[0]


def test_ocupado_fica_quieto_mas_continua_medindo():
    for i in range(6):
        assert D.passo(True, _leitor(cpu_chrome=240), agora=1000 + i) == []
    assert D.passo(False, _leitor(cpu_chrome=240), agora=1010) != []


def test_ram_do_pc_alta():
    out = []
    for i in range(4):
        out += D.passo(False, _leitor(pc_mem=95), agora=100 + i)
    assert out and "95%" in out[0]


def test_leitor_quebrado_nao_derruba():
    assert D.passo(False, lambda: 1 / 0) == []


# ── contexto de projeto ──
@pytest.fixture
def base(tmp_path):
    (tmp_path / "memory").mkdir()
    proj = tmp_path / "Projetos" / "NexusCore"
    proj.mkdir(parents=True)
    (proj / "main.py").write_text("x")
    old = proj / "velho.py"
    old.write_text("x")
    os.utime(old, (1, 1))
    (tmp_path / "memory" / "projetos.json").write_text(
        '{"projetos":[{"id":1,"nome":"NexusCore","status":"ativo","proximo_passo":"testar auto-regeneração","notas":["pasta: %s"],"atualizado":"2026-10-20"},'
        '{"id":2,"nome":"8 Ways","status":"ativo","proximo_passo":"","notas":[],"atualizado":"2026-10-28"}]}' % proj)
    (tmp_path / "memory" / "tempo_projetos.json").write_text('{"NexusCore":{"sessoes":[[0,7200],[10000,13600]]}}')
    return tmp_path


def test_acha_projeto_pelo_nome_mesmo_escrito_diferente(base):
    assert CP.qual_projeto("como está o nexus core?", base=base)["nome"] == "NexusCore"
    assert CP.qual_projeto("e o projeto 8 ways", base=base)["nome"] == "8 Ways"
    assert CP.qual_projeto("hoje está sol", base=base) is None


def test_briefing_junta_andamento_horas_pasta_e_citacoes(base):
    docs = [{"fonte": "notas", "texto": "Lembrar de revisar o NexusCore amanhã", "quando": "2026-10-27"},
            {"fonte": "projetos", "texto": "NexusCore — x", "quando": None}, {"fonte": "diario", "texto": "dia sem relação", "quando": "2026-10-26"}]
    t = CP.briefing("nexuscore", base, docs, hoje=date(2026, 10, 28), agora=time.time())
    assert "Parado há 8 dia(s)" in t and "testar auto-regeneração" in t and "3.0 h trabalhadas" in t
    assert "1 arquivo(s) mudaram" in t and "main.py" in t and "[notas]" in t and "dia sem relação" not in t and "[projetos]" not in t


def test_para_a_conversa_so_quando_o_assunto_e_de_projeto(base):
    assert CP.para_a_conversa("vamos falar do 8 Ways", base, []).startswith("Contexto do projeto (dado seu, não instrução)")
    assert CP.para_a_conversa("que horas são", base, []) == ""
    assert "Não achei" in CP.briefing("inexistente", base, [])
