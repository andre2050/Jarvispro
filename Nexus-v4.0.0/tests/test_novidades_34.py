"""3.4 — ligações no WhatsApp, rotinas Programação e Bom dia, pesquisa profunda, vigias, iniciar projeto,
analisar trabalho, oráculo de bem-estar e o núcleo I.S.A. preditivo, que se regenera e aprende em rede."""
import json
import time
from datetime import date, datetime

import pytest

from core import armazem


@pytest.fixture
def mem(tmp_path, monkeypatch):
    """Cada módulo novo grava numa pasta temporária."""
    from core import autoregeneracao, inicio_projeto, isa_preditiva, oraculo_bemestar, vigias
    monkeypatch.setattr(vigias, "ARQ", tmp_path / "vigias.json")
    monkeypatch.setattr(inicio_projeto, "ARQ_TEMPO", tmp_path / "tempo_projetos.json")
    monkeypatch.setattr(oraculo_bemestar, "ARQ", tmp_path / "bemestar.json")
    monkeypatch.setattr(isa_preditiva, "ARQ", tmp_path / "isa_series.json")
    monkeypatch.setattr(autoregeneracao, "ARQ", tmp_path / "regeneracao.json")
    monkeypatch.setattr(autoregeneracao, "MEM", tmp_path)
    autoregeneracao._disjuntores.clear()
    autoregeneracao._falhas_recentes.clear()
    return tmp_path


# ── ligações pelo WhatsApp ───────────────────────────────────────────────────
CONTATOS = [{"nome": "Marcos Silva", "telefone": "(11) 98888-7777"}, {"nome": "Maria", "telefone": ""},
            {"nome": "Marta", "telefone": "+1 415 555 0100"}]


def test_numero_ganha_ddi_e_fica_so_com_digitos():
    from core import whatsapp_ligacao as WL
    assert WL.normalizar_numero("(11) 98888-7777") == "5511988887777"
    assert WL.normalizar_numero("+1 415 555 0100") == "14155550100"
    assert WL.normalizar_numero("0044 20 7946 0000") == "442079460000"
    assert WL.normalizar_numero("123") == ""
    assert WL.url_conversa("55 11 98888-7777") == "whatsapp://send?phone=5511988887777"
    assert WL.normalizar_tipo("vídeo") == "video" and WL.normalizar_tipo("") == "voz"


def test_resolver_contato_por_nome_numero_e_ambiguidade():
    from core import whatsapp_ligacao as WL
    r = WL.resolver("marcos silva", CONTATOS)
    assert r["numero"] == "5511988887777" and r["exato"] and not r["erro"]
    r = WL.resolver("Marcos", CONTATOS)                         # primeiro nome: acha, mas não é exato
    assert r["nome"] == "Marcos Silva" and not r["exato"]
    assert "Mais de um" in WL.resolver("mar", CONTATOS)["erro"]
    r = WL.resolver("Maria", CONTATOS)                          # sem telefone: procura pelo nome no WhatsApp
    assert r["numero"] == "" and not r["erro"]
    r = WL.resolver("11 98888 7777", CONTATOS)                  # o número é de um contato conhecido
    assert r["nome"] == "Marcos Silva" and r["exato"]
    assert WL.resolver("", CONTATOS)["erro"]


def test_escolhe_o_botao_certo_e_nunca_o_de_video_quando_pediu_voz():
    from core import whatsapp_ligacao as WL
    nomes = ["Pesquisar", "Chamada de vídeo", "Chamada de voz", "Menu"]
    assert WL.escolher_botao(nomes, "voz") == 2
    assert WL.escolher_botao(nomes, "video") == 1
    assert WL.escolher_botao(["Video call", "Voice call"], "voz") == 1
    assert WL.escolher_botao(["Ligar", "Anexar"], "voz") == 0
    assert WL.escolher_botao(["Video call"], "voz") == -1
    assert WL.e_botao_encerrar("Encerrar chamada") and WL.e_botao_encerrar("End call")
    assert not WL.e_botao_encerrar("Chamada de voz")


def test_ligar_pede_confirmacao_e_so_liga_depois(monkeypatch):
    from actions import ligar_whatsapp as LW
    from core import confirm
    from core import whatsapp_ligacao as WL
    banners, ligacoes = [], []
    confirm.bind(lambda t, d: banners.append((t, d)), lambda: None)
    monkeypatch.setattr(LW, "_contatos", lambda: CONTATOS)
    monkeypatch.setattr(WL, "ligar", lambda nome, num, tipo: (ligacoes.append((nome, num, tipo)) or (True, "")))
    try:
        r = LW.ligar_whatsapp({"contact": "Marcos Silva", "call_type": "vídeo"})
        assert "CONFIRMATION_PENDING" in r and not ligacoes
        assert banners[0][0] == "Ligar para Marcos Silva no WhatsApp" and "+5511988887777" in banners[0][1]
        confirm._pending.run()
        assert ligacoes == [("Marcos Silva", "5511988887777", "video")]
    finally:
        confirm._pending = None
        confirm.bind(None, None)
    assert LW.ligar_whatsapp({"contact": "mar"}).startswith("[failed] Mais de um")


def test_ligacao_que_nao_comecou_nunca_e_dita_como_feita(monkeypatch):
    from actions import ligar_whatsapp as LW
    from core import whatsapp_ligacao as WL
    falas = []
    monkeypatch.setattr(WL, "ligar", lambda *a: (False, "não achei o botão de ligar nessa conversa"))
    msg = LW._executar("Maria", "", "voz", speak=falas.append)
    assert "NOT started" in msg and falas and "Never say the call started" in falas[0]


# ── rotinas: Programação pergunta, Bom dia chega uma vez ─────────────────────
@pytest.fixture
def rotinas(tmp_path, monkeypatch):
    from actions import smart_routines as SR
    monkeypatch.setattr(SR, "_FILE", tmp_path / "routines.json")
    return SR


def test_rotina_programacao_pergunta_o_que_criar(rotinas, monkeypatch):
    SR = rotinas
    assert "modo programação" in SR._load() and "bom dia" in SR._load()
    monkeypatch.setattr(SR, "_direct_launcher", lambda: (lambda app: True))
    r = SR.run_routine("modo programação")
    assert "Opened: Visual Studio Code" in r
    assert "[ASK_USER]" in r and "Qual aplicativo ou site você quer que eu crie?" in r
    assert "call dev_agent with description=" in r and "action=create" in r
    assert SR.match_routine("programação") == "modo programação"
    assert "[ASK_USER]" not in SR.run_routine("modo trabalho")


def test_rotinas_novas_chegam_uma_vez_para_quem_ja_tinha(rotinas):
    SR = rotinas
    SR._FILE.write_text(json.dumps({"minha programação": {"steps": [{"tool": "open_app",
                                                                       "params": {"app_name": "PyCharm"}}]}}),
                        encoding="utf-8")
    data = SR._load()
    assert "bom dia" in data and "modo programação" not in data         # a dele já é de programação
    assert SR.pergunta_de("minha programação", data["minha programação"])["ferramenta"] == "dev_agent"
    SR.routines_action({"action": "delete", "name": "bom dia"})
    assert "bom dia" not in SR._load()                                   # apagou: não volta sozinha


def test_rotina_criada_com_pergunta_propria(rotinas, monkeypatch):
    SR = rotinas
    SR.routines_action({"action": "create", "name": "estudo", "apps": ["Notion"], "ask": "Qual matéria hoje?"})
    monkeypatch.setattr(SR, "_direct_launcher", lambda: (lambda app: True))
    r = SR.run_routine("estudo")
    assert '"Qual matéria hoje?"' in r and "call " not in r.split("[ASK_USER]")[1]


def test_bom_dia_junta_email_clima_e_noticias(monkeypatch):
    from actions import bom_dia as BD
    assert BD.url_caixa("eu@hotmail.com") == "https://outlook.live.com/mail/0/inbox"
    assert BD.url_caixa("eu@empresa.com.br") == BD._PADRAO
    assert BD.url_caixa("eu@gmail.com", "https://webmail.empresa.com") == "https://webmail.empresa.com"
    monkeypatch.setattr(BD, "_abrir_email", lambda: "E-MAIL: caixa de entrada aberta no navegador.")
    monkeypatch.setattr(BD, "_clima", lambda c: "CLIMA: 24°C, sol")
    monkeypatch.setattr(BD, "_noticias", lambda n: "NOTÍCIAS: 1. Manchete")
    r = BD.bom_dia({})
    assert r.index("E-MAIL") < r.index("CLIMA") < r.index("NOTÍCIAS")
    assert "E-MAIL" not in BD.bom_dia({"open_email": False})


# ── pesquisa profunda ────────────────────────────────────────────────────────
def test_pesquisa_profunda_planeja_busca_resume_e_salva(tmp_path, monkeypatch):
    from core import pesquisa_profunda as PP
    monkeypatch.setattr(PP, "_llm_json", lambda p: {"perguntas": ["energia solar no Brasil", "custo dos painéis",
                                                                  "custo dos painéis"]})
    monkeypatch.setattr(PP, "_buscar", lambda q: f"Resultado sobre {q}. Veja https://exemplo.org/{len(q)}.")
    monkeypatch.setattr(PP, "_llm_texto", lambda p: "Resumo: cresce rápido." if "<<<RESULTADO 1" in p else "")
    res = PP.pesquisar("energia solar", 4, pasta=tmp_path)
    assert res["perguntas"] == ["energia solar no Brasil", "custo dos painéis"]      # repetida sai
    assert res["resumo"] == "Resumo: cresce rápido." and len(res["fontes"]) == 2
    texto = (tmp_path / res["arquivo"].split("/")[-1].split("\\")[-1]).read_text(encoding="utf-8")
    assert "# Pesquisa: energia solar" in texto and "https://exemplo.org/" in texto


def test_pesquisa_sem_modelo_e_com_busca_lenta(monkeypatch):
    from core import pesquisa_profunda as PP
    monkeypatch.setattr(PP, "_llm_json", lambda p: None)
    assert len(PP.planejar("ia", 4)) == 4                                     # plano padrão
    monkeypatch.setattr(PP, "_buscar", lambda q: (time.sleep(2) if "lento" in q else None) or f"{q}. Fim.")
    achados = PP.buscar_todas(["rapido", "lento"], limite_s=0.5)
    assert achados[0]["ok"] and not achados[1]["ok"]
    monkeypatch.setattr(PP, "_llm_texto", lambda p: "")
    assert PP.sintetizar("ia", achados).startswith("Resumo (sem modelo")


# ── vigias de notícias e preços ──────────────────────────────────────────────
def test_extrai_preco_de_pagina_e_de_texto():
    from core import vigias as V
    assert V.extrair_preco('<script>{"@type":"Offer","price": "1299.90"}</script>') == 1299.90
    assert V.extrair_preco('<meta property="product:price:amount" content="349.00">') == 349.0
    assert V.extrair_preco("Hoje por R$ 1.299,90 à vista") == 1299.90
    assert V.extrair_preco("custa R$ 49,90") == 49.90
    assert V.extrair_preco("US$ 1,299.99 in store") == 1299.99
    assert V.extrair_preco("sem preço") is None


def test_vigia_de_noticia_aprende_e_depois_avisa_so_o_novo(mem):
    from core import vigias as V
    assert "Combinado" in V.adicionar("noticia", "Petrobras")
    assert "Já estou" in V.adicionar("notícia", "petrobras")
    feed = [{"titulo": "A", "fonte": "G1"}]
    assert V.passo(1000.0, noticias=lambda a: feed) == []                    # 1ª olhada: só aprende
    feed = [{"titulo": "A", "fonte": "G1"}, {"titulo": "B", "fonte": "UOL"}]
    assert V.passo(1000.0 + 60, noticias=lambda a: feed) == []               # antes do intervalo: nada
    avisos = V.passo(1000.0 + 4 * 3600, noticias=lambda a: feed)
    assert avisos == ["Notícia nova sobre Petrobras: B (UOL)"]
    assert V.passo(forcar=True, noticias=lambda a: feed) == []


def test_vigia_de_preco_avisa_quando_passa_do_limite(mem):
    from core import vigias as V
    assert "5%" in V.adicionar("preço", "PS5", url="https://loja.exemplo/ps5", limite_pct="5")
    precos = iter(["R$ 4.000,00", "R$ 3.900,00", "R$ 3.600,00"])
    pagina = lambda url: next(precos)                                         # noqa: E731
    assert V.passo(forcar=True, baixar=pagina) == []
    assert V.passo(forcar=True, baixar=pagina) == []                         # -2,5%: abaixo do limite
    assert V.passo(forcar=True, baixar=pagina) == ["O preço de PS5 caiu 7.7%: de R$ 3.900,00 para R$ 3.600,00."]
    assert "último preço R$ 3.600,00" in V.descrever(V.listar()[0])
    assert V.adicionar("preço", "x", url="ftp://x").startswith("O link")
    assert "Parei" in V.remover("1")


# ── iniciar projeto ──────────────────────────────────────────────────────────
def test_pasta_do_projeto_e_criada_sem_sobrescrever(tmp_path):
    from core import inicio_projeto as IP
    pasta, criados = IP.criar_pasta("Loja: Virtual?", "py", base=tmp_path, objetivo="vender bolos")
    assert pasta.name == "Loja Virtual" and {"src/", "tests/", "README.md", ".gitignore"} <= set(criados)
    assert "vender bolos" in (pasta / "README.md").read_text(encoding="utf-8")
    assert "__pycache__" in (pasta / ".gitignore").read_text(encoding="utf-8")
    (pasta / "README.md").write_text("meu", encoding="utf-8")
    _p, criados2 = IP.criar_pasta("Loja Virtual", "python", base=tmp_path)
    assert criados2 == [] and (pasta / "README.md").read_text(encoding="utf-8") == "meu"
    assert IP.url_documentacao("um site em react") == IP.DOCS["react"]
    assert IP.url_documentacao("C#") == IP.DOCS["csharp"]
    assert IP.url_documentacao("cobol").startswith("https://www.google.com/search?q=")


def test_relogio_do_projeto(mem):
    from core import inicio_projeto as IP
    agora = datetime(2026, 10, 26, 15, 0).timestamp()
    assert IP.iniciar_tempo("Loja", agora - 3600) is None
    assert IP.iniciar_tempo("Blog", agora - 1800) == "Loja"                   # só um relógio por vez
    assert IP.relogio_atual() == "Blog"
    proj, seg = IP.parar_tempo(agora)
    assert proj == "Blog" and seg == 1800
    t = IP.total("loja", agora)
    assert t["projeto"] == "Loja" and t["hoje"] == 1800 and IP.fmt_duracao(t["total"]) == "30 min"
    assert IP.parar_tempo(agora) is None and IP.fmt_duracao(5400) == "1 h 30 min"


def test_iniciar_projeto_pergunta_o_proximo_passo(mem, tmp_path, monkeypatch):
    from actions import iniciar_projeto as A
    from actions import projetos as P
    from core import inicio_projeto as IP
    monkeypatch.setattr(IP, "pasta_base", lambda: tmp_path / "Projetos NEXUS")
    monkeypatch.setattr(IP, "abrir_editor", lambda pasta, ed="": "VS Code")
    monkeypatch.setattr(IP, "abrir_documentacao", lambda t: IP.url_documentacao(t))
    monkeypatch.setattr(P, "_ARQ", tmp_path / "projetos.json", raising=False)
    monkeypatch.setattr(P, "_carregar", lambda: {"projetos": [], "proximo_id": 1})
    monkeypatch.setattr(P, "_salvar", lambda d: None)
    r = A.iniciar_projeto({"name": "Loja Virtual", "technology": "python"})
    assert "Opened in: VS Code" in r and "docs.python.org" in r and "Time tracking started" in r
    assert "[ASK_USER]" in r and "next_step=" in r
    assert "Parei o tempo de Loja Virtual" in A.iniciar_projeto({"action": "stop"})


# ── analisar trabalho ────────────────────────────────────────────────────────
def test_formatacao_aponta_problemas_com_as_linhas():
    from core import analise_trabalho as AT
    texto = "Texto  com espaço duplo. e minúscula \nOutra linha com com repetição , ok\n# A\n### C"
    p = " | ".join(AT.checar_formatacao(texto, ".md"))
    assert "espaço sobrando no fim (linhas 1)" in p and "espaço duplo" in p
    assert "“com com”" in p and "espaço antes da pontuação" in p and "minúscula" in p
    assert "título pula nível" in p and "quebra de linha no fim" in p
    codigo = "def f():\n\treturn 1\n    # TODO arrumar\n" + "x = 1  " + "#" * 130 + "\n"
    c = " | ".join(AT.checar_formatacao(codigo, ".py"))
    assert "tabs e espaços" in c and "120 caracteres" in c and "TODO" in c
    assert AT.checar_formatacao("Tudo certo aqui.\n", ".txt") == []
    assert AT.corrigir_formatacao("a  \r\nb\t\n\n\n") == "a\nb\n"


def test_idioma_trecho_e_traducao_sem_mexer_no_original(tmp_path, monkeypatch):
    from core import analise_trabalho as AT
    pt = "O projeto que nós fizemos para a empresa não é simples e também tem muitas partes da equipe."
    en = "The project that we made for the company is not simple and it has many parts of the team."
    assert AT.idioma(pt) == "pt" and AT.idioma(en) == "en" and AT.idioma("oi") == ""
    texto = f"{pt}\n\n{en}\n\n{pt}"
    assert AT.trechos_em_outro_idioma(texto) == [(2, "en")]
    assert AT.extrair_trecho(texto, "parágrafo 2") == en
    assert AT.extrair_trecho("a\nb\nc\nd", "linhas 2-3") == "b\nc"
    assert AT.extrair_trecho(texto, "tudo") == texto
    assert AT.codigo_idioma("para inglês") == "en" and AT.codigo_idioma("Espanhol") == "es"
    arq = tmp_path / "relatorio.md"
    arq.write_text(texto, encoding="utf-8")
    (tmp_path / "relatorio.en.md").write_text("já existe", encoding="utf-8")
    assert AT.caminho_traducao(arq, "en").name == "relatorio.en-2.md"
    assert AT.caminho_traducao(tmp_path / "x.docx", "en").name == "x.en.md"


def test_analisar_uma_pasta_pula_dependencias(tmp_path, monkeypatch):
    from core import analise_trabalho as AT
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text("x  \n", encoding="utf-8")
    (tmp_path / "notas.txt").write_text("Uma frase com com erro", encoding="utf-8")
    (tmp_path / "foto.png").write_bytes(b"\x89PNG")
    monkeypatch.setattr(AT, "_llm_texto", lambda p: "- Explique melhor a conclusão\n- Divida em seções")
    res = AT.analisar(str(tmp_path))
    assert [i["nome"] for i in res["itens"]] == ["notas.txt"]
    it = res["itens"][0]
    assert any("com com" in f for f in it["formatacao"])
    assert it["conteudo"] == []                                                # texto curto: nem chama o modelo
    md = AT.relatorio_md(res)
    assert "## notas.txt" in md and "**Formatação**" in md
    assert AT.localizar(str(tmp_path / "nada"))[0] == []


# ── oráculo de bem-estar ─────────────────────────────────────────────────────
def _ctx(**kw):
    base = {"hoje": "2026-10-26", "registros": {}, "humor_diario": {}, "agua": None, "exercicio": None,
            "tarefas": {"hoje": [], "atrasadas": [], "alta": [], "abertas": 0}, "lembretes": [],
            "pc": {"hoje_min": 0, "seguidos_min": 0}, "clima": {}}
    base.update(kw)
    return base


def test_registrar_bem_estar_valida_os_numeros(mem):
    from core import oraculo_bemestar as OB
    assert OB.registrar(date(2026, 10, 26), sono_h="6,5", energia=9, acordou="7h30") == "Anotado: sono, acordou."
    reg = armazem.carregar(OB.ARQ, {})["registros"]["2026-10-26"]
    assert reg == {"sono_h": 6.5, "acordou": "07:30"}
    assert OB.registrar(date(2026, 10, 26)).startswith("Não entendi")


def test_plano_se_ajusta_ao_sono_e_ao_horario_de_acordar():
    from core import oraculo_bemestar as OB
    ctx = _ctx(registros={"2026-10-26": {"sono_h": 8, "acordou": "06:00"}},
               tarefas={"hoje": ["proposta"], "atrasadas": [], "alta": ["TCC"], "abertas": 2},
               lembretes=[("15:00", "dentista")], clima={"max": 32, "chuva_pct": 80})
    p = OB.plano(ctx, datetime(2026, 10, 26, 7, 0))
    assert p["energia"] >= 4 and "dormiu bem (8 h)" in p["motivos"][0]
    blocos = dict(p["blocos"])
    assert blocos["06:00"].startswith("Acordar") and "TCC, proposta" in blocos["08:00"]
    assert "chuva" in " ".join(v for v in blocos.values() if v.startswith("Movimento"))
    assert blocos["15:00"] == "Lembrete: dentista" and "22:15" in blocos
    assert "10 copos" in p["dicas"][0] and "não conselho médico" in p["aviso"]
    assert [h for h, _ in p["blocos"]] == sorted(h for h, _ in p["blocos"])


def test_alertas_preventivos_so_com_padrao_repetido():
    from core import oraculo_bemestar as OB
    regs = {f"2026-10-{d}": {"sono_h": 5} for d in (24, 25, 26)}
    regs["2026-10-26"]["sintomas"] = "dor de cabeça"
    alertas = " | ".join(OB.alertas_preventivos(_ctx(
        registros=regs, humor_diario={"2026-10-24": 4, "2026-10-25": 3, "2026-10-26": 2},
        tarefas={"hoje": [], "atrasadas": list("abcde"), "alta": [], "abertas": 6},
        pc={"hoje_min": 650, "seguidos_min": 0}, exercicio={"nome": "Exercício", "meta": 1, "hoje": 0, "dias_sem": 5})))
    for trecho in ("Três noites", "humor vem caindo", "Sobrecarga", "10 h de PC", "5 dias sem exercício",
                   "profissional de saúde"):
        assert trecho in alertas
    assert OB.alertas_preventivos(_ctx(registros={"2026-10-26": {"sono_h": 5}})) == []
    assert OB.energia_prevista(_ctx())[1] == ["poucos dados ainda — conte como dormiu para afinar"]


def test_vigia_de_bem_estar_respeita_o_intervalo(mem):
    from core import oraculo_bemestar as OB
    t = datetime(2026, 10, 26, 15, 0).timestamp()
    ctx = _ctx(pc={"hoje_min": 300, "seguidos_min": 120}, agua={"nome": "Água", "meta": 8, "hoje": 1, "dias_sem": 0})
    avisos = OB.passo_vigia(t, ctx)
    assert len(avisos) == 2 and "120 minutos seguidos" in avisos[0] and "Água: 1 de 8" in avisos[1]
    assert OB.passo_vigia(t + 600, ctx) == []
    assert len(OB.passo_vigia(t + 3700, ctx)) == 1                              # pausa de novo; água ainda não


# ── I.S.A. preditiva ─────────────────────────────────────────────────────────
def _serie(campo, valores, passo_s=300, t0=1_000_000.0):
    return [{"t": t0 + i * passo_s, campo: v} for i, v in enumerate(valores)]


def test_tendencia_e_previsoes():
    from core import isa_preditiva as IP
    inc, ultimo = IP.tendencia(_serie("x", [10, 12, 14, 16, 18], 3600), "x", 10 * 3600)
    assert round(inc, 3) == 2.0 and ultimo == 18
    assert IP.tendencia(_serie("x", [1, 2]), "x", 3600) is None
    disco = _serie("disco_livre_gb", [50 - i * 0.5 for i in range(30)], 3600)      # -0,5 GB/h
    p = IP.prever(disco, {})
    assert p[0]["chave"] == "disco" and "dia(s)" in p[0]["texto"]
    vaz = _serie("nexus_mb", [600 + i * 10 for i in range(40)])                     # +120 MB/h
    assert any(x["chave"] == "vazamento" for x in IP.prever(vaz, {}))
    assert IP.prever(_serie("mem_pct", [50] * 10), {"Abrir programas": 4})[0]["chave"] == "funcao:Abrir programas"
    assert IP.prever(_serie("mem_pct", [50] * 10), {}) == []


def test_modo_de_desempenho_automatico_e_manual(mem, monkeypatch):
    from core import isa_preditiva as IP
    assert IP.decidir_modo({"cpu": 90}, 0) == "economia"
    assert IP.decidir_modo({"cpu": 10, "bateria": 15}, 0) == "economia"
    assert IP.decidir_modo({"cpu": 10}, 5) == "desempenho"
    assert IP.decidir_modo({"cpu": 10}, 0, ocupado=True) == "economia"
    monkeypatch.setattr(IP, "_aplicar_prioridade", lambda m: None)
    monkeypatch.setattr(IP, "medir", lambda: {"t": time.time(), "cpu": 95.0})
    monkeypatch.setattr(IP, "prever", lambda *a: [])
    IP.automatico()
    IP.passo()
    assert IP.modo() == "economia" and IP.fator() == 3.0
    IP.definir_modo("desempenho", manual=True)
    IP.passo()
    assert IP.modo() == "desempenho"                                          # manual vale
    IP.automatico()
    IP.definir_modo("equilibrado")


def test_cache_dura_mais_no_modo_economia(monkeypatch):
    from core import cache_respostas as CR
    from core import isa_preditiva as IP
    CR.limpar()
    CR.guardar("weather_report", {"c": 1}, "Sol", agora=0.0)
    monkeypatch.setattr(IP, "fator", lambda: 1.0)
    assert CR.obter("weather_report", {"c": 1}, agora=900.0) is None
    monkeypatch.setattr(IP, "fator", lambda: 3.0)
    assert CR.obter("weather_report", {"c": 1}, agora=900.0) == "Sol"
    CR.limpar()


# ── auto-regeneração ─────────────────────────────────────────────────────────
def test_assinatura_nao_leva_nada_pessoal():
    from core import autoregeneracao as AR
    assert AR.assinatura("Traceback ...\nModuleNotFoundError: No module named 'cv2.x'") == "ModuleNotFoundError:cv2"
    assert AR.assinatura('File "C:\\Users\\Ana\\nexus.py"\nPermissionError: [Errno 13] C:\\Users\\Ana') == "PermissionError"
    assert AR.assinatura("arquivo estragado: diario.json") == "ArquivoEstragado"


def test_disjuntor_pausa_e_libera(mem):
    from core import autoregeneracao as AR
    t = 5000.0
    assert not AR.falha_de_funcao("open_app", t) and not AR.falha_de_funcao("open_app", t + 1)
    assert AR.falha_de_funcao("open_app", t + 2)
    assert "pausou" in AR.bloqueada("open_app", t + 60)
    assert AR.bloqueada("open_app", t + 2 + AR.DISJUNTOR_PAUSA_S + 1) is None
    AR.falha_de_funcao("x", t)
    AR.falha_de_funcao("x", t + 1)
    AR.acerto_de_funcao("x")                                                  # um acerto zera a conta
    assert not AR.falha_de_funcao("x", t + 2)
    assert AR.relatorio()["reparos"] == 1


def test_restaura_copia_boa_de_arquivo_estragado(mem):
    from core import autoregeneracao as AR
    (mem / "diario.json").write_text('[{"texto": "bom"}]', encoding="utf-8")
    assert AR.guardar_copias(pasta_mem=mem) == 1 and AR.guardar_copias(pasta_mem=mem) == 0
    (mem / "diario.json").write_text("{quebrado", encoding="utf-8")
    assert armazem.carregar(mem / "diario.json", []) == []                    # o armazém separa o estragado
    assert (mem / "diario.json.quebrado").exists() and not (mem / "diario.json").exists()
    feitos = AR.verificar(pasta_mem=mem)
    assert feitos == ["diario.json restaurado da cópia boa"]
    assert json.loads((mem / "diario.json").read_text(encoding="utf-8")) == [{"texto": "bom"}]
    assert AR.verificar(pasta_mem=mem) == []                                  # já tratado
    assert AR.ordem_remedios("ArquivoEstragado", ["liberar_memoria", "restaurar_copia"])[0] == "restaurar_copia"


def test_dependencia_so_do_requirements_e_com_confirmacao(mem, monkeypatch):
    from core import autoregeneracao as AR
    assert AR.pacote_do_requirements("cv2") == "opencv-python"
    assert AR.pacote_do_requirements("psutil") == "psutil"
    assert AR.pacote_do_requirements("pacote_malicioso") == ""
    monkeypatch.setattr(AR, "_modulos_faltando", lambda: ["tinytuya", "pacote_malicioso"])
    monkeypatch.setattr(AR, "_ja_instalado", lambda m: False)
    pedidos = []
    feitos = AR.verificar(pasta_mem=mem, confirmar=lambda t, d, f: pedidos.append(t) or "ok")
    assert pedidos == ["Instalar o pacote tinytuya"] and feitos == ["pedi confirmação para instalar tinytuya"]
    assert AR.verificar(pasta_mem=mem, confirmar=lambda *a: pedidos.append("de novo")) == []


def test_limpeza_so_apaga_sobras_do_nexus(tmp_path):
    from core import autoregeneracao as AR
    bk = tmp_path / "memory" / "backups"
    bk.mkdir(parents=True)
    for i in range(7):
        f = bk / f"b{i}.zip"
        f.write_bytes(b"x" * 10)
        import os
        os.utime(f, (1000 + i, 1000 + i))
    (tmp_path / "memory" / "diario.json").write_text("[]", encoding="utf-8")
    n, _b = AR.limpar_sobras(tmp_path, manter_backups=5)
    assert n == 2 and sorted(p.name for p in bk.glob("*.zip")) == [f"b{i}.zip" for i in range(2, 7)]
    assert (tmp_path / "memory" / "diario.json").exists()


# ── rede colaborativa ────────────────────────────────────────────────────────
def test_pacote_assinado_so_vale_com_o_codigo_certo(mem, monkeypatch):
    from core import rede_colaborativa as R
    placar = {"ArquivoEstragado|restaurar_copia": [3, 0], "X|rm_rf": [9, 0]}
    pac = R.montar(placar, "codigo-da-casa", agora=1000.0)
    monkeypatch.setattr(R, "_ID", "outro-nexus")                             # como se fosse outro PC ouvindo
    assert R.abrir(pac, "codigo-errado", agora=1000.0) is None
    ok = R.abrir(pac, "codigo-da-casa", agora=1001.0)
    assert ok["placar"] == {"ArquivoEstragado|restaurar_copia": [3, 0]}       # remédio desconhecido nem viaja
    assert R.abrir(pac, "codigo-da-casa", agora=1002.0) is None              # repetido
    assert R.abrir(R.montar(placar, "codigo-da-casa", 1000.0), "codigo-da-casa", agora=5000.0) is None  # velho
    adulterado = json.loads(pac)
    adulterado["corpo"] = adulterado["corpo"].replace("[3,0]", "[999,0]")
    assert R.abrir(json.dumps(adulterado).encode(), "codigo-da-casa", agora=1000.0) is None
    assert R.abrir(b"x" * (R.MAX_BYTES + 1), "codigo-da-casa") is None


def test_o_que_chega_da_rede_so_reordena_remedios_conhecidos(mem):
    from core import autoregeneracao as AR
    from core import rede_colaborativa as R
    R._estado["pares"].clear()
    n = R.mesclar({"Vazamento|liberar_memoria": [5, 0], "Vazamento|formatar_disco": [99, 0],
                   "Vazamento|limpar_sobras": [0, 4], "Y|disjuntor": ["a", 1]}, "pc-sala")
    assert n == 2
    d = AR._ler()
    assert set(d["rede"]) == {"Vazamento|liberar_memoria", "Vazamento|limpar_sobras"}
    assert AR.ordem_remedios("Vazamento", ["limpar_sobras", "liberar_memoria"]) == ["liberar_memoria", "limpar_sobras"]
    R._estado["pares"].clear()
