from core import imunidade as I

TB = 'Traceback (most recent call last):\n  File "/home/x/nexus/core/foo.py", line 42, in f\n    a, b = tres()\nValueError: too many values to unpack (expected 2)\n'


def test_assinatura_ignora_numeros_caminhos_e_enderecos():
    a = I.assinatura("PermissionError: [Errno 13] Permission denied: 'C:\\Users\\Ana\\x 1.json'")
    b = I.assinatura("PermissionError: [Errno 13] Permission denied: 'C:\\Users\\Bia\\y 2.json'")
    assert a == b and "Ana" not in a
    assert I.assinatura("TimeoutError: https://a.com/x?id=77 em 30s") == I.assinatura("TimeoutError: https://b.org/y?id=99 em 45s")
    assert I.assinatura("") == "desconhecida"


def test_onde_acha_o_ultimo_quadro_do_nexus():
    assert I.onde(TB) == "foo.py:42"
    assert I.onde('File "/usr/lib/python3.13/site-packages/x.py", line 1') == ""


def test_conta_repeticoes_e_associa_vacina(tmp_path):
    arq = tmp_path / "i.json"
    for i in range(3):
        f = I.registrar("requests.ConnectionError: timed out after 30s", "email", 1000 + i, arq)
    assert f["n"] == 3 and f["vacina"] == "espera_rede" and f["origem"] == "email"


def test_vacina_so_e_aplicada_antes_depois_de_dar_certo(tmp_path):
    arq = tmp_path / "i.json"
    f = I.registrar("ConnectionError: Network is unreachable", "email", 1, arq)
    assert I.antes_de("unreachable", arq) is None                       # ainda não provou nada
    I.resultado(f["assinatura"], True, arq)
    v = I.antes_de("email", arq)
    assert v and v["vacina"] == "espera_rede" and v["espera_s"] == 5
    for _ in range(3):
        I.resultado(f["assinatura"], False, arq)
    assert I.antes_de("email", arq) is None                             # deixou de funcionar: para de aplicar


def test_aviso_nunca_vira_acao_automatica(tmp_path):
    arq = tmp_path / "i.json"
    f = I.registrar("ModuleNotFoundError: No module named 'foo'", "x", 1, arq)
    I.resultado(f["assinatura"], True, arq)
    assert I.antes_de("foo", arq) is None                               # instalar pacote só com o sim do usuário


def test_tratar_aplica_so_remedio_seguro_e_registra_resultado(tmp_path):
    arq = tmp_path / "i.json"
    chamou = []
    rem = {"liberar_memoria": lambda ctx: (chamou.append(1) or (True, "liberei")), "instalar_dependencia": lambda ctx: (chamou.append("PERIGO"), (True, "x"))[1]}
    assert "liberei" in I.tratar("MemoryError", "x", rem, arq=arq)
    assert I.tratar("ModuleNotFoundError: No module named 'zzz'", "x", rem, arq=arq).startswith("Falta um pacote")
    assert chamou == [1]
    assert I.confiavel(I._ler(arq)["falhas"]["MemoryError"])


def test_remedio_que_quebra_nao_derruba(tmp_path):
    assert "vacina" in I.tratar("MemoryError", "x", {"liberar_memoria": lambda c: 1 / 0}, arq=tmp_path / "i.json")


def test_bug_sem_vacina_vira_relatorio_so_com_reincidencia(tmp_path):
    arq = tmp_path / "i.json"
    for t in (100, 200):
        I.registrar(TB, "isa", t, arq)
    assert I.bugs_reincidentes(300, arq) == []
    I.registrar(TB, "isa", 300, arq)
    b = I.bugs_reincidentes(400, arq)
    assert b[0]["vezes_24h"] == 3 and b[0]["onde"] == "foo.py:42"
    assert "foo.py:42" in I.relatorio(400, arq)
    assert I.bugs_reincidentes(400 + 2 * 86400, arq) == []              # passou da janela


def test_espera_crescente_e_limite_de_assinaturas(tmp_path):
    assert [I.espera_crescente("espera_rede", n) for n in (1, 2, 9)] == [5.0, 15.0, 120.0] and I.espera_crescente("x", 1) is None
    arq = tmp_path / "i.json"
    for i in range(I.MAX_ASSINATURAS + 20):
        I.registrar(f"Erro{'x' * (i % 90)}{chr(65 + i % 26)}{'y' * (i // 26)}: z", "o", i, arq)
    assert len(I._ler(arq)["falhas"]) <= I.MAX_ASSINATURAS
