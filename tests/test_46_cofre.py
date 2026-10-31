"""4.6.0 — cofre de chaves: usa um cofre falso em memória (o real depende do sistema)."""
import json

import pytest

from core import cofre as C


class Falso:
    def __init__(self):
        self.d = {}

    def set_password(self, s, n, v):
        self.d[(s, n)] = v

    def get_password(self, s, n):
        return self.d.get((s, n))

    def delete_password(self, s, n):
        del self.d[(s, n)]


DADOS = {"gemini_api_key": "AIzaSECRETO123", "os_system": "windows", "preferences": {"voice": "x", "panel_password_hash": "abcdef123456"},
         "plugin_config": {"email": {"password": "senha-do-email", "host": "imap.x"}}, "max_tokens": 4096, "home_assistant_token": "tok-ha-123"}


def test_migra_so_segredos():
    novo, n = C.migrar(DADOS, Falso())
    assert n == 3
    assert novo["gemini_api_key"] == C.MARCA and novo["home_assistant_token"] == C.MARCA
    assert novo["plugin_config"]["email"]["password"] == C.MARCA
    assert novo["max_tokens"] == 4096 and novo["os_system"] == "windows"
    assert novo["preferences"]["panel_password_hash"] == "abcdef123456"
    assert DADOS["gemini_api_key"] == "AIzaSECRETO123"          # o original não é alterado


def test_ida_e_volta():
    f = Falso()
    novo, _ = C.migrar(DADOS, f)
    assert C.resolver(novo, f) == DADOS


def test_segredo_nao_confirmado_fica_no_arquivo():
    class Ruim(Falso):
        def get_password(self, s, n):
            return None
    novo, n = C.migrar(DADOS, Ruim())
    assert n == 0 and novo == DADOS


def test_resolver_sem_cofre_vira_vazio_sem_quebrar(monkeypatch):
    monkeypatch.setattr(C, "_backend", lambda: None)
    r = C.resolver({"gemini_api_key": C.MARCA, "a": 1})
    assert r == {"gemini_api_key": "", "a": 1}


def test_resolver_nao_mexe_em_arquivo_sem_marca():
    d = {"gemini_api_key": "x" * 20}
    assert C.resolver(d) is d


def test_ligar_sincronizar_desligar(tmp_path, monkeypatch):
    p = tmp_path / "api_keys.json"
    p.write_text(json.dumps(DADOS), encoding="utf-8")
    f = Falso()
    monkeypatch.setattr(C, "_backend", lambda: f)
    import core.preferences as P
    monkeypatch.setattr(P, "save", lambda v: None)
    r = C.ligar(p, f)
    assert r["ok"] and r["moveu"] == 3
    assert "AIzaSECRETO123" not in p.read_text(encoding="utf-8")
    assert (tmp_path / "api_keys.json.antes_do_cofre").exists()
    # um segredo novo cai em texto puro e a sincronização o leva ao cofre
    d = json.loads(p.read_text(encoding="utf-8"))
    d["anthropic_api_key"] = "sk-ant-novissima"
    p.write_text(json.dumps(d), encoding="utf-8")
    assert C.sincronizar(p, f) == 1
    assert "sk-ant-novissima" not in p.read_text(encoding="utf-8")
    r = C.desligar(p, f)
    assert r["ok"] and r["voltou"] == 4
    assert json.loads(p.read_text(encoding="utf-8"))["gemini_api_key"] == "AIzaSECRETO123"


def test_desligar_sem_todos_os_valores_nao_altera(tmp_path):
    p = tmp_path / "api_keys.json"
    p.write_text(json.dumps({"gemini_api_key": C.MARCA}), encoding="utf-8")
    r = C.desligar(p, Falso())
    assert not r["ok"] and json.loads(p.read_text(encoding="utf-8"))["gemini_api_key"] == C.MARCA


def test_ligar_sem_cofre_no_sistema(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "_backend", lambda: None)
    r = C.ligar(tmp_path / "x.json")
    assert not r["ok"] and "cofre" in r["motivo"].lower()


def test_leitores_comuns_enxergam_o_valor(tmp_path, monkeypatch):
    f = Falso()
    novo, _ = C.migrar(DADOS, f)
    monkeypatch.setattr(C, "_backend", lambda: f)
    import memory.config_manager as CM
    arq = tmp_path / "api_keys.json"
    arq.write_text(json.dumps(novo), encoding="utf-8")
    monkeypatch.setattr(CM, "CONFIG_FILE", arq)
    assert CM.load_api_keys()["gemini_api_key"] == "AIzaSECRETO123"
    CM._patch_config(input_device="mic")          # gravar outra coisa não devolve o segredo ao arquivo
    assert "AIzaSECRETO123" not in arq.read_text(encoding="utf-8")


def test_acao_status_nao_quebra():
    from actions import cofre_chaves as A
    assert A.cofre_chaves({"action": "status"}).startswith("[done]")


def test_nenhum_leitor_cru_da_chave_do_gemini():
    """Qualquer leitor novo de ["gemini_api_key"] tem de passar pelo cofre."""
    import re
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent
    ruins = []
    for pasta in ("actions", "assistant", "core", "dashboard", "ui", "memory", "config"):
        for f in (raiz / pasta).rglob("*.py"):
            t = f.read_text(encoding="utf-8", errors="ignore")
            if re.search(r'json\.load\(f\)\["gemini_api_key"\]', t) or re.search(r'_json\.load\(f\)\.get\("gemini_api_key"\)', t):
                ruins.append(str(f.relative_to(raiz)))
    assert not ruins, ruins
