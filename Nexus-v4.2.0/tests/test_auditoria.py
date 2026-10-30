"""Auditoria: corrente de hashes, sem segredos, explicação, e quem chama nunca quebra."""
import json

from core import auditoria as A


def _reg(arq, n=3):
    for i in range(n):
        A.registrar("acao", "nexus", f"usou ferramenta{i}", {"city": f"Recife{i}"}, motivo=f"motivo {i}",
                    modelo="local", resultado="ok", arq=arq, agora=1000 + i)


def test_corrente_integra_e_detecta_adulteracao(tmp_path):
    arq = tmp_path / "a.jsonl"
    _reg(arq, 4)
    assert A.verificar(arq) == (True, "Registro íntegro: 4 linha(s) conferidas.")
    linhas = arq.read_text(encoding="utf-8").splitlines()
    # 1) trocar um conteúdo
    d = json.loads(linhas[1]); d["resultado"] = "falso"
    ruim = tmp_path / "b.jsonl"
    ruim.write_text("\n".join([linhas[0], json.dumps(d), *linhas[2:]]) + "\n", encoding="utf-8")
    ok, msg = A.verificar(ruim)
    assert not ok and "linha 2" in msg
    # 2) apagar uma linha do meio
    cortado = tmp_path / "c.jsonl"
    cortado.write_text("\n".join([linhas[0], linhas[2], linhas[3]]) + "\n", encoding="utf-8")
    ok, msg = A.verificar(cortado)
    assert not ok and "quebra" in msg
    assert A.verificar(tmp_path / "nao_existe") == (True, "Nenhum registro ainda.")


def test_segredos_e_corpos_nao_entram(tmp_path):
    arq = tmp_path / "a.jsonl"
    A.registrar("acao", "nexus", "usou send_message", {"api_key": "AIzaSEGREDO", "message": "oi " * 100,
                "to": "Ana", "nested": {"password": "SENHA-XYZ", "ok": 1}}, arq=arq)
    bruto = arq.read_text(encoding="utf-8")
    assert "AIzaSEGREDO" not in bruto and "SENHA-XYZ" not in bruto and "oi oi oi oi oi oi oi oi oi oi oi oi oi oi" not in bruto
    d = A.ler(1, arq)[0]
    assert d["params"]["api_key"] == "[oculto]" and d["params"]["to"] == "Ana" and "texto de 300" in d["params"]["message"]


def test_explicar_acha_pelo_assunto(tmp_path):
    arq = tmp_path / "a.jsonl"
    A.registrar("acao", "nexus", "usou weather_report", {"city": "Recife"}, motivo="você pediu o clima", modelo="gemini", arq=arq, agora=1000)
    A.registrar("acao", "nexus", "usou open_app", {"app_name": "Spotify"}, motivo="rotina de manhã", arq=arq, agora=1001)
    r = A.explicar("por que você abriu o spotify?", arq=arq)
    assert "open_app" in r and "rotina de manhã" in r and "weather" not in r
    assert "Não encontrei" in A.explicar("banana", arq=arq)
    assert "weather_report" in A.explicar("", arq=arq)


def test_aparar_e_retomar_corrente(tmp_path):
    arq = tmp_path / "a.jsonl"
    _reg(arq, 6)
    assert A.aparar(arq, maximo=3) == 3
    assert A.verificar(arq)[0]                       # a primeira linha que sobra serve de âncora
    A.registrar("acao", "nexus", "mais uma", arq=arq)
    assert A.verificar(arq) == (True, "Registro íntegro: 4 linha(s) conferidas.")


def test_registrar_nunca_levanta(tmp_path):
    assert A.registrar("acao", "x", "y", arq=tmp_path / "pasta_inexistente" / "dentro" / "a.jsonl") != ""
    assert A.registrar("acao", "x", "y", params=object(), arq=tmp_path) == ""      # um diretório: falha engolida


def test_registro_das_ferramentas_e_das_decisoes(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "ARQUIVO", tmp_path / "a.jsonl")
    from core import action_loader as AL
    AL._auditar("weather_report", {"city": "Recife", "token": "abc"}, "Sol", {"motivo": "pediu", "modelo": "gemini", "missao": "m1"})
    AL._auditar("tarefas", {}, "x", {})                                           # ferramenta de uso interno: não audita
    ls = A.ler(10)
    assert len(ls) == 1 and ls[0]["missao"] == "m1" and ls[0]["params"]["token"] == "[oculto]"
    from core import confirm
    confirm._auditar_decisao(types_p := type("P", (), {"title": "APAGAR X", "detail": "d", "key": "k"})(), "aprovou")
    assert A.ler(10)[-1]["tipo"] == "decisao" and "aprovou" in A.ler(10)[-1]["o_que"]


def test_acao_de_voz(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "ARQUIVO", tmp_path / "a.jsonl")
    from actions import auditoria as AA
    A.registrar("acao", "nexus", "usou open_app", {"app_name": "Spotify"}, motivo="você pediu")
    assert "open_app" in AA.auditoria({"action": "explain", "query": "spotify"})
    assert AA.auditoria({"action": "verify"})[:6] == "[done]"
    assert "open_app" in AA.auditoria({"action": "recent"})


def test_consultar_filtra_por_texto_tipo_missao_e_dias(tmp_path):
    arq = tmp_path / "a.jsonl"
    A.registrar("acao", "missao", "enviou e-mail", {"to": "x"}, motivo="avisar", missao="m1", arq=arq, agora=1_000_000)
    A.registrar("decisao", "usuario", "aprovou", {}, motivo="plano", missao="m1", arq=arq, agora=1_000_500)
    A.registrar("acao", "nexus", "abriu o Chrome", {}, arq=arq, agora=1_090_000)
    assert [d["tipo"] for d in A.consultar(arq=arq)] == ["acao", "decisao", "acao"]       # mais novo primeiro
    assert len(A.consultar(q="e-mail", arq=arq)) == 1 and len(A.consultar(tipo="decisao", arq=arq)) == 1
    assert len(A.consultar(missao="m1", arq=arq)) == 2
    assert len(A.consultar(dias=1, arq=arq, agora=1_090_100)) == 1
    assert A.consultar(q="inexistente", arq=arq) == [] and A.consultar(arq=tmp_path / "nao.jsonl") == []
