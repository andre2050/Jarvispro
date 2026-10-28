"""Testes das funções novas da 2.2: compras, hábitos, contatos, manutenção do PC, texto/dev e diário."""
import json
import os
import time
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from actions import compras, contatos, diario, manutencao_pc, rastreador_habitos as hab, texto_dev
from core import armazem


@pytest.fixture(autouse=True)
def isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(compras, "_ARQ", tmp_path / "compras.json")
    monkeypatch.setattr(hab, "_ARQ", tmp_path / "habitos.json")
    monkeypatch.setattr(contatos, "_ARQ", tmp_path / "contatos.json")
    monkeypatch.setattr(diario, "_ARQ", tmp_path / "diario.json")


# ── armazém ──────────────────────────────────────────────────────────────────
def test_armazem_arquivo_quebrado_e_guardado(tmp_path):
    f = tmp_path / "x.json"
    f.write_text("{isso nao e json", encoding="utf-8")
    assert armazem.carregar(f, []) == []
    assert (tmp_path / "x.json.quebrado").exists()


def test_armazem_arquivo_quebrado_fica_anotado_em_falhas_log(tmp_path):
    from core import protecao
    f = tmp_path / "compras.json"
    f.write_text("{ isso não é json", encoding="utf-8")
    armazem.carregar(f, [])
    assert "arquivo estragado: compras.json" in protecao.ARQ_FALHAS.read_text(encoding="utf-8")


def test_armazem_tipo_errado_devolve_padrao(tmp_path):
    f = tmp_path / "x.json"
    f.write_text('{"a": 1}', encoding="utf-8")
    assert armazem.carregar(f, []) == []


def test_armazem_achar_por_numero_nome_e_ambiguo():
    itens = [{"n": "Leite integral"}, {"n": "Leite de coco"}, {"n": "Pão"}]
    assert armazem.achar("3", itens, "n")[0]["n"] == "Pão"
    assert armazem.achar("pao", itens, "n")[0]["n"] == "Pão"
    assert armazem.achar("leite", itens, "n")[0] is None
    assert "Mais de um" in armazem.achar("leite", itens, "n")[1]
    assert armazem.achar("9", itens, "n")[0] is None


# ── compras ──────────────────────────────────────────────────────────────────
def run_c(**kw):
    return compras.compras(kw)


def test_compras_varios_itens_e_quantidade():
    r = run_c(action="add", items="leite, pão e 2 ovos")
    assert "leite" in r and "pão" in r and "2 ovos" in r
    lista = run_c(action="list")
    assert "1. leite" in lista and "3. 2 ovos" in lista


def test_compras_repetido_soma_quantidade():
    run_c(action="add", items="2 ovos")
    run_c(action="add", items="3 ovos")
    assert "5 ovos" in run_c(action="list")
    assert len(compras._ler()) == 1


def test_compras_comprei_e_limpar():
    run_c(action="add", items="leite, pão")
    assert "Faltam 1" in run_c(action="bought", target="leite")
    assert "leite" not in run_c(action="list")
    assert "1 item" in run_c(action="clear_bought")
    assert len(compras._ler()) == 1


def test_compras_listas_separadas():
    run_c(action="add", items="dipirona", list_name="Farmácia")
    run_c(action="add", items="arroz")
    assert "dipirona" in run_c(action="list", list_name="farmácia")
    assert "arroz" not in run_c(action="list", list_name="farmácia")
    assert "farmácia (1)" in run_c(action="lists")


def test_compras_vazio_e_remover():
    assert "vazia" in run_c(action="list")
    assert "Diga o que" in run_c(action="add", items="  ")
    run_c(action="add", items="sal")
    assert "Tirei da lista: sal" in run_c(action="remove", target="1")
    assert "vazia" in run_c(action="list")


# ── hábitos ──────────────────────────────────────────────────────────────────
def run_h(**kw):
    return hab.rastreador_habitos(kw)


def test_habito_criar_registrar_e_meta():
    run_h(action="create", name="Beber água", goal=8, unit="copos")
    assert "faltam 6" in run_h(action="log", name="agua", amount=2)
    r = run_h(action="log", name="água", amount=6)
    assert "meta de hoje batida" in r and "Sequência: 1" in r


def test_habito_nome_repetido_e_inexistente():
    run_h(action="create", name="Ler")
    assert "já tem" in run_h(action="create", name="ler")
    assert "Não encontrei" in run_h(action="log", name="correr")


def test_habito_sequencia_conta_dias_seguidos():
    hoje = date(2026, 10, 22)
    h = {"nome": "x", "meta": 1, "registros": {(hoje - timedelta(days=i)).isoformat(): 1 for i in (1, 2, 3)}}
    assert hab.sequencia(h, hoje) == 3                 # hoje aberto não quebra a de ontem
    h["registros"][hoje.isoformat()] = 1
    assert hab.sequencia(h, hoje) == 4
    h["registros"].pop((hoje - timedelta(days=2)).isoformat())
    assert hab.sequencia(h, hoje) == 2                 # buraco quebra
    assert hab.melhor_sequencia(h) == 2


def test_habito_desfazer_e_status():
    run_h(action="create", name="Exercício")
    run_h(action="log", name="exercicio")
    assert "✅" in run_h(action="status")
    assert "Agora: 0" in run_h(action="undo", name="exercicio")
    assert "⏳" in run_h(action="status")


def test_habito_quantidade_invalida_vira_um():
    run_h(action="create", name="Água", goal=3)
    assert "1 de 3" in run_h(action="log", name="agua", amount=-5)


# ── contatos ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("entrada, esperado", [
    ("12/03", "03-12"), ("12 de março", "03-12"), ("dia 5 de dezembro", "12-05"),
    ("12/03/1990", "1990-03-12"), ("1990-03-12", "1990-03-12"), ("29/02", "02-29"),
    ("31/02", ""), ("lixo", ""), ("", ""), ("5/5/95", "1995-05-05"),
])
def test_contatos_interpretar_data(entrada, esperado):
    assert contatos.interpretar_data(entrada) == esperado


def test_contatos_proximo_aniversario_e_idade():
    hoje = date(2026, 10, 22)
    assert contatos.proximo_aniversario("1990-10-22", hoje) == (date(2026, 10, 22), 36)
    assert contatos.proximo_aniversario("1990-03-12", hoje) == (date(2027, 3, 12), 37)
    assert contatos.proximo_aniversario("03-12", hoje) == (date(2027, 3, 12), None)
    assert contatos.proximo_aniversario("02-29", date(2027, 1, 1)) == (date(2027, 2, 28), None)


def test_contatos_salvar_buscar_atualizar():
    r = contatos.contatos({"action": "save", "name": "Marcos", "phone": "11 98888-7777", "birthday": "12 de março"})
    assert "Salvei" in r and "12 de março" in r
    assert "Atualizei" in contatos.contatos({"action": "save", "name": "marcos", "email": "m@ex.com"})
    achado = contatos.contatos({"action": "find", "name": "marc"})
    assert "98888-7777" in achado and "m@ex.com" in achado
    assert len(contatos._ler()) == 1


def test_contatos_valida_email_e_data():
    assert "não parece válido" in contatos.contatos({"action": "save", "name": "A", "email": "sem-arroba"})
    assert "Não entendi a data" in contatos.contatos({"action": "save", "name": "A", "birthday": "dia nenhum"})
    assert contatos._ler() == [] or contatos._ler()[0]["email"] == ""


def test_contatos_aniversarios_proximos(monkeypatch):
    monkeypatch.setattr(contatos, "_hoje", lambda: date(2026, 10, 22))
    contatos.contatos({"action": "save", "name": "Ana", "birthday": "23/10/1990"})
    contatos.contatos({"action": "save", "name": "Beto", "birthday": "30/10"})
    contatos.contatos({"action": "save", "name": "Caio", "birthday": "01/01"})
    r = contatos.contatos({"action": "birthdays", "days": 15})
    assert "Ana amanhã (36 anos)" in r and "Beto em 8 dias" in r and "Caio" not in r
    assert "Ninguém" in contatos.contatos({"action": "birthdays", "days": 1}) or "Ana" in contatos.contatos({"action": "birthdays", "days": 1})
    assert contatos.aniversariantes_de_hoje() == []


def test_contatos_remover_e_vazio():
    assert "vazia" in contatos.contatos({"action": "list"})
    contatos.contatos({"action": "save", "name": "Zé"})
    assert "Apaguei" in contatos.contatos({"action": "remove", "name": "ze"})
    assert "Não achei" in contatos.contatos({"action": "find", "name": "ze"})


# ── texto e dev ──────────────────────────────────────────────────────────────
def t(op, text="", **kw):
    return texto_dev.texto_dev({"operation": op, "text": text, **kw})


def test_texto_contar():
    assert t("count", "Olá mundo. Tudo bem?").startswith("4 palavra(s)")


@pytest.mark.parametrize("modo, esperado", [
    ("upper", "MEU NOME AQUI"), ("snake", "meu_nome_aqui"), ("kebab", "meu-nome-aqui"),
    ("camel", "meuNomeAqui"), ("pascal", "MeuNomeAqui"), ("title", "Meu Nome Aqui"),
])
def test_texto_caixa(modo, esperado):
    assert t("case", "meu nome aqui", mode=modo) == esperado


def test_texto_caixa_converte_entre_estilos():
    assert t("case", "meuNomeAqui", mode="snake") == "meu_nome_aqui"
    assert t("case", "meu_nome-aqui", mode="camel") == "meuNomeAqui"


def test_texto_hash_conhecido():
    assert t("hash", "abc", mode="md5") == "900150983cd24fb0d6963f7d28e17f72"
    assert t("hash", "abc").startswith("ba7816bf8f01cfea")
    assert "[failed]" in t("hash", "abc", mode="crc99")


def test_texto_base64_ida_e_volta_e_invalido():
    codificado = t("base64_encode", "olá, mundo")
    assert t("base64_decode", codificado) == "olá, mundo"
    assert t("base64_decode", codificado.rstrip("=")) == "olá, mundo"
    assert "[failed]" in t("base64_decode", "isso não é base64!!")


def test_texto_url_json_slug():
    assert t("url_encode", "a b&c") == "a%20b%26c"
    assert t("url_decode", "a%20b%26c") == "a b&c"
    assert t("json_format", '{"a":[1,2]}').count("\n") > 3
    assert t("json_minify", '{ "a": [1, 2] }') == '{"a":[1,2]}'
    assert "linha" in t("json_format", '{"a": ')
    assert t("slug", "Meu Post Nôvo! 2026") == "meu-post-novo-2026"


def test_texto_uuid_timestamp_e_linhas():
    assert len(t("uuid")) == 36
    assert "22/10/2026" in t("timestamp", "1792684800") or "2026" in t("timestamp", "1792684800")
    assert "timestamp" in t("timestamp", "22/10/2026 15:30")
    assert "[failed]" in t("timestamp", "ontem de manhã")
    assert t("sort_lines", "b\na\nÁ") .splitlines()[0] in ("a", "Á")
    assert t("unique_lines", "a\nb\na") == "a\nb"


def test_texto_limites_e_erros():
    assert "[failed]" in t("reverse", "")
    assert "[failed]" in t("reverse", "x" * 200_001)
    assert "desconhecida" in t("inventada", "x")


# ── diário ───────────────────────────────────────────────────────────────────
def d(**kw):
    return diario.diario(kw)


def test_diario_escrever_ler_e_buscar():
    assert "Humor 4" in d(action="write", text="Terminei a prova", mood=4)
    assert "Terminei a prova" in d(action="read")
    assert "1 anotação" in d(action="search", query="PROVA")
    assert "Não achei" in d(action="search", query="viagem")
    assert "Não há anotações" in d(action="read", date="ontem")


def test_diario_valida_humor_e_vazio():
    assert "1 a 5" in d(action="write", text="x", mood=9)
    assert "O que devo" in d(action="write")
    assert "vazio" in d(action="recent")


def test_diario_humor_media_e_tendencia():
    for m in (2, 2, 4, 5):
        d(action="write", text="x", mood=m)
    r = d(action="mood", days=7)
    assert "3.2" in r and "Subindo" in r and "melhor 5" in r


def test_diario_apagar_ultima():
    d(action="write", text="um")
    d(action="write", text="dois")
    d(action="remove_last")
    assert "dois" not in d(action="recent") and "um" in d(action="recent")


# ── manutenção do PC ─────────────────────────────────────────────────────────
def m(**kw):
    return manutencao_pc.manutencao_pc(kw)


def test_manutencao_humano():
    assert manutencao_pc.humano(512) == "512 B"
    assert manutencao_pc.humano(1536) == "1.5 KB"
    assert manutencao_pc.humano(5 * 1024 ** 3) == "5.0 GB"


def test_manutencao_disco_e_pastas_grandes(tmp_path):
    assert "livres" in m(action="disk")
    (tmp_path / "grande").mkdir()
    (tmp_path / "grande" / "a.bin").write_bytes(b"x" * 50_000)
    (tmp_path / "pequena").mkdir()
    (tmp_path / "pequena" / "b.bin").write_bytes(b"x" * 10)
    r = m(action="big_folders", path=str(tmp_path))
    assert r.index("grande/") < r.index("pequena/")
    assert "[failed]" in m(action="big_folders", path=str(tmp_path / "nao_existe"))


def test_manutencao_pastas_nao_segue_atalho(tmp_path):
    fora = tmp_path / "fora"
    fora.mkdir()
    (fora / "enorme.bin").write_bytes(b"x" * 100_000)
    dentro = tmp_path / "dentro"
    dentro.mkdir()
    try:
        os.symlink(fora, dentro / "atalho")
    except (OSError, NotImplementedError):
        pytest.skip("sem suporte a symlink")
    total, ok = manutencao_pc.tamanho_pasta(dentro, time.monotonic() + 5)
    assert ok and total == 0


def test_manutencao_temporarios_so_velhos_e_com_confirmacao(tmp_path, monkeypatch):
    monkeypatch.setattr(manutencao_pc.tempfile, "gettempdir", lambda: str(tmp_path))
    velho, novo = tmp_path / "velho.tmp", tmp_path / "novo.tmp"
    velho.write_bytes(b"x" * 1000)
    novo.write_bytes(b"x" * 1000)
    passado = time.time() - 5 * 86400
    os.utime(velho, (passado, passado))
    assert "1 arquivo" in m(action="temp_scan")

    pedidos = []
    from core import confirm
    monkeypatch.setattr(confirm, "pending_title", lambda: "")
    monkeypatch.setattr(confirm, "request", lambda key, titulo, detalhe, run: pedidos.append(run) or "aguardando")
    assert m(action="temp_clean") == "aguardando"
    assert velho.exists(), "nada pode ser apagado antes do CONFIRMAR"
    msg = pedidos[0]()
    assert "[done]" in msg and not velho.exists() and novo.exists()


def test_manutencao_temp_nao_apaga_fora_da_pasta(tmp_path, monkeypatch):
    temp = tmp_path / "temp"
    temp.mkdir()
    de_fora = tmp_path / "importante.txt"
    de_fora.write_text("não apagar")
    monkeypatch.setattr(manutencao_pc.tempfile, "gettempdir", lambda: str(temp))
    manutencao_pc._apagar_temp([de_fora])
    assert de_fora.exists()


def test_manutencao_backup_confere_e_nao_sobrescreve(tmp_path):
    src = tmp_path / "Projeto"
    (src / "sub").mkdir(parents=True)
    (src / "a.txt").write_text("olá")
    (src / "sub" / "b.txt").write_text("mundo")
    (src / "node_modules").mkdir()
    (src / "node_modules" / "lixo.js").write_text("x")
    destino = tmp_path / "bk"
    r = m(action="backup", path=str(src), destination=str(destino))
    assert r.startswith("[done]") and "2 arquivo(s)" in r
    zips = list(destino.glob("Projeto_*.zip"))
    assert len(zips) == 1
    with zipfile.ZipFile(zips[0]) as z:
        assert sorted(z.namelist()) == ["a.txt", "sub/b.txt"]


def test_manutencao_backup_recusa_destino_dentro_da_origem(tmp_path):
    src = tmp_path / "P"
    src.mkdir()
    assert "[failed]" in m(action="backup", path=str(src), destination=str(src / "bk"))
    assert "[failed]" in m(action="backup", path=str(tmp_path / "nao_existe"))
    assert "[failed]" in m(action="backup")


@pytest.mark.parametrize("host", ["google.com; rm -rf /", "a b", "$(whoami)", "", "-n 100 x.com", "a|b", "-oProxyCommand=x"])
def test_manutencao_ping_rejeita_host_perigoso(host):
    assert m(action="ping", host=host).startswith("[failed]")


def test_manutencao_rede_bateria_e_acao_invalida():
    assert "IP na rede local" in m(action="network")
    assert "ateria" in m(action="battery")
    assert "desconhecida" in m(action="inventada")


# ── as 6 ações são descobertas pelo carregador ───────────────────────────────
def test_novas_acoes_sao_descobertas_e_validas():
    from core import action_loader
    mods = {"compras": compras, "rastreador_habitos": hab, "contatos": contatos,
            "manutencao_pc": manutencao_pc, "texto_dev": texto_dev, "diario": diario}
    for nome, mod in mods.items():
        tool = mod.TOOL
        assert tool["name"] == nome and callable(tool["handler"])
        assert action_loader._NAME_RE.match(tool["name"])
        assert tool["parameters"]["type"] == "OBJECT" and tool["description"]
        assert set(tool["parameters"]["required"]) <= set(tool["parameters"]["properties"])
