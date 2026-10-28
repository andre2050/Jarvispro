import threading
import time

from core.equipe_agentes import Equipe, Quadro


def test_agentes_veem_o_que_os_outros_publicaram_ao_vivo():
    q = Quadro()
    q.publicar("pesquisador", "O notebook X custa R$ 4500 na loja A", 0.9)
    t = q.texto_para("analista")
    assert "pesquisador" in t and "R$ 4500" in t
    assert q.texto_para("pesquisador") == ""                          # não lê o que ele mesmo disse


def test_detecta_conflito_de_numeros_sobre_o_mesmo_assunto():
    q = Quadro()
    q.publicar("pesquisador", "O notebook Acer Nitro custa R$ 4500 na loja A")
    q.publicar("analista", "O notebook Acer Nitro custa R$ 4200 na loja A")
    q.publicar("analista", "A bateria dura 6 horas")
    c = q.conflitos()
    assert len(c) == 1 and {c[0]["a"][0], c[0]["b"][0]} == {"pesquisador", "analista"}
    assert "POSSIBLE CONFLICTS" in q.texto_conflitos()


def test_sem_conflito_quando_assuntos_diferentes_ou_mesmo_agente_ou_mesmos_numeros():
    q = Quadro()
    q.publicar("a", "O voo para Recife custa 800 reais")
    q.publicar("b", "O hotel em Salvador custa 300 reais")
    q.publicar("a", "O voo para Recife custa 800 reais")            # mesmo agente repetindo
    q.publicar("b", "O voo para Recife custa 800 reais")            # concorda
    assert q.conflitos() == [] and q.texto_conflitos() == ""


def test_limite_de_notas_e_tamanho():
    q = Quadro()
    for i in range(60):
        q.publicar("a", f"nota {i} " + "x" * 1000, confianca=i / 60)
    ns = q.ler()
    assert len(ns) == 40 and all(len(n["texto"]) <= 400 for n in ns)
    assert len(q.texto_para("outro")) <= 1800


def test_equipe_roda_em_paralelo_de_verdade_e_compartilha_a_lousa():
    q = Quadro()
    vistos = {}
    barreira = threading.Barrier(2, timeout=5)

    def pesquisa(tarefa, quadro):
        quadro.publicar("pesquisa", "achei o dado 42")
        barreira.wait()                                              # só passa se os dois estiverem rodando ao mesmo tempo
        return "pesquisei"

    def analise(tarefa, quadro):
        barreira.wait()
        vistos["analista"] = quadro.texto_para("analise")
        return "analisei"

    r = Equipe({"pesquisa": pesquisa, "analise": analise}, q).executar({"pesquisa": "p", "analise": "a"})
    assert r["resultados"] == {"pesquisa": "pesquisei", "analise": "analisei"} and not r["erros"]
    assert "dado 42" in vistos["analista"]


def test_agente_que_quebra_ou_trava_nao_derruba_a_equipe():
    def bom(t, q):
        return "ok"

    def ruim(t, q):
        raise ValueError("falhou")

    def lento(t, q):
        time.sleep(1.5)
        return "tarde"
    r = Equipe({"bom": bom, "ruim": ruim, "lento": lento}, prazo_s=0.3).executar({"bom": "x", "ruim": "y", "lento": "z", "fantasma": "w"})
    assert r["resultados"] == {"bom": "ok"}
    assert "ValueError" in r["erros"]["ruim"] and "prazo" in r["erros"]["lento"] and "desconhecido" in r["erros"]["fantasma"]
