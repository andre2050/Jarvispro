"""Simulação 'e se': descreve o que mudaria olhando o disco de verdade, sem tocar em nada."""
from core import simulacao as S


def test_classifica_efeito_e_risco():
    assert S.efeito("web_search", {}) == S.LE and S.risco("web_search", {}) == "seguro"
    assert S.efeito("file_controller", {"action": "delete"}) == S.APAGA
    assert S.efeito("file_controller", {"action": "read"}) == S.LE
    assert S.efeito("file_controller", {"action": "inventada"}) == S.DESCONHECIDO
    assert S.risco("ferramenta_nova", {}) == "sensivel"               # desconhecido nunca passa como seguro
    assert S.efeito("email_reader", {"action": "send"}) == S.ENVIA and S.efeito("send_message", {}) == S.ENVIA


def test_arquivos_existentes_e_inexistentes(tmp_path):
    a = tmp_path / "relatorio.txt"
    a.write_text("x" * 2048)
    pasta = tmp_path / "fotos"
    pasta.mkdir()
    for i in range(5):
        (pasta / f"{i}.jpg").write_bytes(b"1")
    ja = tmp_path / "destino.txt"
    ja.write_text("velho")
    r = S.simular([
        {"tool": "file_controller", "args": {"action": "delete", "path": str(a)}, "titulo": "limpar"},
        {"tool": "file_controller", "args": {"action": "delete", "path": str(pasta)}},
        {"tool": "file_controller", "args": {"action": "move", "path": str(a), "destination": str(ja)}},
        {"tool": "file_controller", "args": {"action": "write", "path": str(ja), "content": "novo"}},
        {"tool": "file_controller", "args": {"action": "write", "path": str(tmp_path / "novo.md"), "content": "abc"}},
        {"tool": "file_controller", "args": {"action": "move", "path": str(tmp_path / "fantasma.txt"), "destination": str(tmp_path)}},
    ])
    t = [i["resumo"] for i in r["itens"]]
    assert "APAGAR relatorio.txt (2.0 KB)" in t[0]
    assert "pasta fotos com 5 itens" in t[1]
    assert "SOBRESCREVER" in t[2] and "destino.txt" in t[2]
    assert "SOBRESCREVER destino.txt (5 B hoje)" in t[3]
    assert "vai criar novo.md (3 caracteres)" in t[4]
    assert "NÃO existe" in t[5]
    assert a.exists() and pasta.exists() and ja.read_text() == "velho"    # nada foi tocado


def test_resumo_geral_e_texto():
    r = S.simular([{"tool": "web_search", "args": {"query": "x"}},
                   {"tool": "send_message", "args": {"contact": "Ana", "message": "oi"}, "titulo": "avisar"},
                   {"tool": "email_reader", "args": {"action": "send", "to": "b@x.com", "body": "texto"}}])
    assert r["sensiveis"] == 2 and "1 leitura(s)" in r["resumo"] and "2 envio(s)" in r["resumo"]
    t = S.texto(r)
    assert "⚠ 2. avisar: vai ENVIAR uma mensagem para Ana (2 caracteres)" in t and "· 1." in t
    assert S.simular([])["resumo"].startswith("Plano vazio")


def test_nao_chama_ferramenta_nenhuma(monkeypatch):
    import os
    chamadas = []
    monkeypatch.setattr(os, "remove", lambda *a: chamadas.append(a))
    S.simular([{"tool": "file_controller", "args": {"action": "delete", "path": "/tmp/x"}}])
    assert chamadas == []
