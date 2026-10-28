import json
import pytest
from core import rede_nexus as R


class Mundo:
    """Dois nós conversando em memória."""

    def __init__(self, tmp_path):
        self.t = [1000.0]
        self.nos = {}
        self.exec_log = []
        for nome in ("casa", "celular"):
            mem = tmp_path / nome / "memory"
            mem.mkdir(parents=True)
            self.nos[nome] = R.Rede(tmp_path / nome / "rede.json", mem, agora=lambda: self.t[0], enviar=self._enviar(nome),
                                    executar=lambda tool, args, n=nome: (self.exec_log.append((n, tool)) or f"{tool} ok"), auditar=False)
            self.nos[nome].eu(nome)

    def _enviar(self, de):
        def f(url, remetente, blob):
            alvo = self.nos["celular" if "celular" in url else "casa"]
            return alvo.tratar(remetente, blob)
        return f

    def parear(self):
        cod = self.nos["casa"].convidar()
        return self.nos["celular"].entrar(cod, "http://casa.local", "http://celular.local")


def test_pareamento_uma_vez_e_codigo_errado(tmp_path):
    m = Mundo(tmp_path)
    cod = m.nos["casa"].convidar()
    with pytest.raises(R.ErroRede):
        m.nos["celular"].entrar("AAAAA-BBBBB-CCCCC-DDDDD", "http://casa.local")
    pid = m.nos["celular"].entrar(cod, "http://casa.local", "http://celular.local")
    assert pid in m.nos["celular"].peers() and m.nos["casa"].peers()
    with pytest.raises(R.ErroRede):                      # o convite vale uma vez
        m.nos["celular"].entrar(cod, "http://casa.local")
    assert m.nos["celular"].ping(pid)


def test_convite_expira(tmp_path):
    m = Mundo(tmp_path)
    cod = m.nos["casa"].convidar()
    m.t[0] += 700
    with pytest.raises(R.ErroRede):
        m.nos["celular"].entrar(cod, "http://casa.local")


def test_anti_repeticao_e_horario(tmp_path):
    m = Mundo(tmp_path)
    m.parear()
    c, cel = m.nos["casa"], m.nos["celular"]
    pid = next(iter(cel.peers()))
    chave = cel._chave_peer(pid)
    blob = cel._cifrar(chave, {"tipo": "ping"})
    eu_cel = cel.eu()["id"]
    c.tratar(eu_cel, blob)
    with pytest.raises(R.ErroRede):
        c.tratar(eu_cel, blob)                            # mesma mensagem de novo
    velho = cel._cifrar(chave, {"tipo": "ping"})
    m.t[0] += 500
    with pytest.raises(R.ErroRede):
        c.tratar(eu_cel, velho)
    with pytest.raises(R.ErroRede):
        c.tratar("desconhecido", blob)


def test_sync_o_mais_novo_vence_com_backup(tmp_path):
    import os
    m = Mundo(tmp_path)
    pid = m.parear()
    casa_mem, cel_mem = m.nos["casa"].pasta_mem, m.nos["celular"].pasta_mem
    (casa_mem / "tarefas.json").write_text(json.dumps([{"t": "velha"}]))
    os.utime(casa_mem / "tarefas.json", (100, 100))
    (cel_mem / "tarefas.json").write_text(json.dumps([{"t": "nova"}]))
    os.utime(cel_mem / "tarefas.json", (200, 200))
    (casa_mem / "projetos.json").write_text(json.dumps({"p": 1}))
    (casa_mem / "senha.txt").write_text("nao sincroniza")
    r = m.nos["celular"].sincronizar(pid)
    assert "projetos.json" in r["recebidos"] and "tarefas.json" in r["enviados"]
    assert json.loads((casa_mem / "tarefas.json").read_text()) == [{"t": "nova"}]
    assert not (cel_mem / "senha.txt").exists()
    assert list((casa_mem / "rede_backup").glob("tarefas.json.*"))
    assert m.nos["celular"].sincronizar(pid) == {"recebidos": [], "enviados": []}   # nada de ida e volta


def test_aplicar_barra_nome_fora_da_lista_e_json_invalido(tmp_path):
    n = R.Rede(tmp_path / "r.json", tmp_path / "mem", auditar=False)
    ok = n._aplicar({"../x.json": {"dados": R._b64(b"{}"), "mtime": 1}, "tarefas.json": {"dados": R._b64(b"lixo"), "mtime": 1}}, "x")
    assert ok == [] and not (tmp_path / "mem" / "tarefas.json").exists()


def test_tarefas_so_leitura_e_so_se_aceitar(tmp_path):
    m = Mundo(tmp_path)
    pid = m.parear()
    cel = m.nos["celular"]
    assert "não aceita" in cel.delegar(pid, "web_search", {"query": "x"})
    m.nos["casa"].definir_aceitar_tarefas(True)
    assert "web_search ok" in cel.delegar(pid, "web_search", {"query": "x"})
    assert "não é uma ferramenta segura" in cel.delegar(pid, "send_message", {})
    assert "não é uma ferramenta segura" in cel.delegar(pid, "missao", {})
    assert "não é uma ferramenta segura" in cel.delegar(pid, "ferramenta_inexistente", {})
    assert m.exec_log == [("casa", "web_search")]


def test_chave_nao_fica_em_texto_claro_no_codigo_e_esquecer(tmp_path):
    m = Mundo(tmp_path)
    pid = m.parear()
    assert m.nos["celular"].esquecer(pid) and not m.nos["celular"].peers()


def test_fila_entrega_quando_o_outro_volta_e_expira(tmp_path):
    m = Mundo(tmp_path)
    pid = m.parear()
    cel, casa = m.nos["celular"], m.nos["casa"]
    casa.definir_aceitar_tarefas(True)
    with pytest.raises(R.ErroRede):
        cel.enfileirar(pid, "send_message", {})                     # escrita nem entra na fila
    qid = cel.enfileirar(pid, "web_search", {"query": "x"})
    ligado = cel.enviar
    def desligado(url, rem, blob):
        raise OSError("sem rede")
    cel.enviar = desligado                                          # a casa está desligada
    assert cel.processar_fila() == [] and cel._fila()[0]["tentativas"] == 1
    cel.enviar = ligado                                             # a casa voltou
    assert cel.processar_fila() == [(qid, "feita")]
    assert "web_search ok" in cel.resultados()[0]["resultado"]
    q2 = cel.enfileirar(pid, "web_search", {"query": "y"})
    m.t[0] += R.Rede.VALIDADE_FILA_S + 10
    cel.enviar = desligado
    assert cel.processar_fila() == [(q2, "expirada")]


def test_fila_tem_limite_e_recusa_do_outro_lado_vira_falha(tmp_path):
    m = Mundo(tmp_path)
    pid = m.parear()
    cel = m.nos["celular"]
    for i in range(R.Rede.MAX_FILA):
        cel.enfileirar(pid, "web_search", {"query": str(i)})
    with pytest.raises(R.ErroRede):
        cel.enfileirar(pid, "web_search", {})
    assert {e for _, e in cel.processar_fila()} == {"falhou"}       # a casa não aceita tarefas (desligado)


def test_sync_automatico_respeita_intervalo_e_so_com_online(tmp_path):
    m = Mundo(tmp_path)
    pid = m.parear()
    cel = m.nos["celular"]
    (m.nos["casa"].pasta_mem / "tarefas.json").write_text("[1]")
    assert not cel.sync_auto()
    r = cel.sincronizar_todos()
    assert "casa" in r and "recebi 1" in r["casa"]
    assert cel.sincronizar_todos() == {}                            # dentro do intervalo
    m.t[0] += 1000
    assert "casa" in cel.sincronizar_todos()
