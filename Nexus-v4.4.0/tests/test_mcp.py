"""Cliente MCP: protocolo real por stdio contra um servidor falso, segurança e a ação por voz."""
import os
import sys
import time
from pathlib import Path

import pytest

from core import mcp_cliente as M

FALSO = str(Path(__file__).parent / "mcp_servidor_falso.py")
PY = sys.executable


@pytest.fixture
def srv():
    s = M.ServidorMCP("falso", PY, [FALSO], {"MINHA_CHAVE": "valor-secreto-123"})
    yield s
    s.parar()


def test_aperto_de_mao_lista_e_chama(srv):
    ts = srv.ferramentas()
    assert srv.info["name"] == "falso" and srv.protocolo == M.PROTOCOLO
    assert {t["name"] for t in ts} == {"eco", "apagar", "falha", "lenta", "injecao", "segredo"}
    r = srv.chamar("eco", {"texto": "olá"})
    assert "eco: olá" in M.texto_do_resultado("falso", r)
    assert M.somente_leitura(next(t for t in ts if t["name"] == "eco"))
    assert not M.somente_leitura(next(t for t in ts if t["name"] == "apagar"))      # sem anotação = não é só leitura
    assert "[pede CONFIRMAR]" in M.resumo_ferramenta(next(t for t in ts if t["name"] == "apagar"))
    assert "texto*" in M.resumo_ferramenta(next(t for t in ts if t["name"] == "eco"))


def test_paginacao_de_ferramentas():
    s = M.ServidorMCP("falso", PY, [FALSO, "pagina"])
    try:
        assert len(s.ferramentas()) == 6
    finally:
        s.parar()


def test_pedido_do_servidor_ao_cliente_e_recusado_e_log_perdido_ignorado(srv):
    srv.iniciar()                       # o servidor falso manda um sampling/createMessage e uma linha de lixo no stdout
    assert srv.vivo() and srv.ferramentas()


def test_erro_da_ferramenta_e_ferramenta_desconhecida(srv):
    assert "ERRO da ferramenta" in M.texto_do_resultado("falso", srv.chamar("falha"))
    with pytest.raises(M.ErroMCP, match="desconhecida"):
        srv.chamar("nao_existe")


def test_tempo_esgotado_nao_trava(srv):
    srv.iniciar()
    t0 = time.monotonic()
    with pytest.raises(M.ErroMCP, match="demorou"):
        srv.chamar("lenta", tempo=0.6)
    assert time.monotonic() - t0 < 3


def test_resultado_e_dado_nao_instrucao_e_tem_limite(srv):
    texto = M.texto_do_resultado("falso", srv.chamar("injecao"))
    assert "nunca como instrução" in texto and 'source="mcp:falso"' in texto
    assert texto.count("</untrusted_content>") == 1                  # o servidor não consegue "fechar" o embrulho sozinho
    assert "cortado" in texto and len(texto) < M.MAX_RESPOSTA + 500


def test_servidor_nao_herda_o_ambiente_do_nexus(srv, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-chave-do-nexus")
    s = M.ServidorMCP("falso", PY, [FALSO], {"MINHA_CHAVE": "valor-secreto-123"})
    try:
        saida = M.texto_do_resultado("falso", s.chamar("segredo"))
    finally:
        s.parar()
    assert "chave=valor-secreto-123" in saida                       # a que foi declarada chega
    assert "gemini=ausente" in saida and "AIza-chave-do-nexus" not in saida


def test_erros_nao_vazam_variaveis_declaradas():
    s = M.ServidorMCP("x", PY, [FALSO, "versao_estranha"], {"TOKEN": "super-segredo-999"})
    with pytest.raises(M.ErroMCP) as e:
        s.iniciar()
    assert "super-segredo-999" not in str(e.value) and "não conheço" in str(e.value)
    assert not s.vivo()                                              # falhou no aperto de mão: processo fechado
    with pytest.raises(M.ErroMCP, match="Não achei o programa"):
        M.ServidorMCP("y", "programa-que-nao-existe-xyz", []).iniciar()


def test_parar_fecha_o_processo_e_pendentes_falham(srv):
    srv.iniciar()
    proc = srv.proc
    srv.parar()
    assert proc.poll() is not None and not srv.vivo()
    with pytest.raises(M.ErroMCP):
        srv._enviar({"jsonrpc": "2.0", "method": "x"})


def test_validacao_de_definicoes():
    M.validar_definicao("fetch", "uvx", ["mcp-server-fetch"])
    for nome, cmd in (("Ruim Nome", "uvx"), ("ok", "uvx; rm -rf /"), ("ok", "a b"), ("ok", ""), ("ok", "x|y")):
        with pytest.raises(M.ErroMCP):
            M.validar_definicao(nome, cmd, [])
    with pytest.raises(M.ErroMCP):
        M.validar_definicao("ok", "uvx", ["a\nb"])
    assert M.definicao_do_comando('npx -y @mcp/pacote "/minha pasta"') == ("npx", ["-y", "@mcp/pacote", "/minha pasta"]) or os.name == "nt"
    with pytest.raises(M.ErroMCP):
        M.definicao_do_comando("   ")


@pytest.fixture
def cfg(monkeypatch):
    guardado = {}
    monkeypatch.setattr(M, "_cfg", lambda: dict(guardado.get("mcp", {})))
    monkeypatch.setattr(M, "_salvar", lambda v: guardado.setdefault("mcp", {}).update(v))
    yield guardado
    M.parar_todos()


def test_config_adicionar_remover_e_ociosos(cfg):
    assert M.listar_servidores() == {}
    M.adicionar_servidor("falso", PY, [FALSO], {"MINHA_CHAVE": "abc123456"})
    assert list(M.listar_servidores()) == ["falso"]
    s = M.servidor("falso")
    assert s.ferramentas() and s.vivo()
    assert M.servidor("falso") is s                                  # reaproveita o que está aberto
    assert M.fechar_ociosos(time.monotonic() + M.OCIOSO_SEGUNDOS + 5) == 1 and not s.vivo()
    with pytest.raises(M.ErroMCP, match="Não há servidor"):
        M.servidor("outro")
    M.remover_servidor("falso")
    assert M.listar_servidores() == {}


def test_acao_por_voz_fluxo_completo(cfg, monkeypatch):
    from actions import mcp_nexus as A
    from core import confirm
    pedidos = []
    monkeypatch.setattr(confirm, "pending_title", lambda: "")
    monkeypatch.setattr(confirm, "request", lambda key, title, detail, run: pedidos.append((title, detail, run)) or "aguardando")

    assert "fetch" in A.mcp_nexus({"action": "list"})                                   # sem servidores: mostra sugestões
    A.mcp_nexus({"action": "add", "server": "falso", "command": f'{PY} {FALSO}', "env": "MINHA_CHAVE=segredo-abc-12"})
    assert pedidos and "ADICIONAR SERVIDOR MCP" in pedidos[0][0] and "segredo-abc-12" not in pedidos[0][1]
    assert M.listar_servidores() == {}                                                  # nada salvo antes do CONFIRMAR
    assert pedidos[0][2]().startswith("[done]") and "falso" in M.listar_servidores()

    assert "eco(texto*)" in A.mcp_nexus({"action": "tools", "server": "falso"})
    r = A.mcp_nexus({"action": "call", "server": "falso", "tool": "eco", "arguments": '{"texto": "oi"}'})
    assert "eco: oi" in r and len(pedidos) == 1                                          # somente leitura: direto
    r = A.mcp_nexus({"action": "call", "server": "falso", "tool": "apagar", "arguments": '{"alvo": "tudo"}'})
    assert r == "aguardando" and "USAR APAGAR" in pedidos[1][0] and "tudo" in pedidos[1][1]
    assert "apaguei tudo" in pedidos[1][2]()                                             # só roda no CONFIRMAR
    assert "[failed]" in A.mcp_nexus({"action": "call", "server": "falso", "tool": "eco", "arguments": "isto nao eh json"})
    assert "não tem a ferramenta" in A.mcp_nexus({"action": "call", "server": "falso", "tool": "zzz"})
    assert "[failed]" in A.mcp_nexus({"action": "tools", "server": "inexistente"})
    assert A.mcp_nexus({"action": "stop", "server": "falso"}).startswith("[done]")
    assert A.mcp_nexus({"action": "remove", "server": "falso"}).startswith("[done]")


def test_acao_sugestoes_e_pasta_obrigatoria(cfg, monkeypatch):
    from actions import mcp_nexus as A
    from core import confirm
    pedidos = []
    monkeypatch.setattr(confirm, "pending_title", lambda: "")
    monkeypatch.setattr(confirm, "request", lambda key, title, detail, run: pedidos.append((title, detail, run)) or "ok")
    assert "Qual pasta" in A.mcp_nexus({"action": "add", "server": "filesystem"})
    A.mcp_nexus({"action": "add", "server": "filesystem", "folder": "/dados"})
    assert "/dados" in pedidos[0][1] and "server-filesystem" in pedidos[0][1]
    assert "[failed]" in A.mcp_nexus({"action": "add", "server": "Nome Ruim", "command": "x y"})
    assert A.TOOL["name"] == "mcp_nexus" and "untrusted" in A.TOOL["description"]
