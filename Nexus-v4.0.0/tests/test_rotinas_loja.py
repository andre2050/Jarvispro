"""Rotinas na loja: pacote sem código, só ferramentas seguras, assinatura opcional, nunca substitui rotina sua."""
import json
import zipfile

import pytest

from actions import smart_routines as SR
from core import plugin_loja as L
from core import rotinas_loja as RL


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr(SR, "_FILE", tmp_path / "routines.json")
    SR._save({"bom dia": {"steps": [{"tool": "weather_report", "params": {"city": "Recife"}}], "description": "clima"},
              "foco": {"steps": [{"tool": "open_app", "params": {"app_name": "Notepad"}}], "description": "",
                       "agenda": {"dias": [0, 1, 2, 3, 4], "hora": "08:00"}}})
    return tmp_path


def _pacote(dest, rotinas, sig=None, extra=None):
    m = {"id": "pacote_teste", "nome": "Pacote teste", "versao": "1.0", "autor": "Maria", "rotinas": rotinas}
    bruto = json.dumps(m).encode()
    with zipfile.ZipFile(dest, "w") as z:
        z.writestr("rotina.json", bruto)
        if sig:
            z.writestr("rotina.sig", sig(bruto))
        for k, v in (extra or {}).items():
            z.writestr(k, v)
    return dest


def test_exporta_e_abre_com_assinatura(ambiente):
    priv, pub = L.gerar_par_de_chaves()
    out = RL.exportar(["Bom dia", "foco"], ambiente / "a.nexusrotina", {"id": "minhas_x", "nome": "Minhas", "versao": "1.0", "autor": "Maria"}, priv)
    p = RL.abrir(out, autores={"Maria": pub})
    assert p.assinado and p.autor_confiavel == "Maria" and set(p.rotinas) == {"bom dia", "foco"}
    assert "08:00" in p.resumo() or "segunda" in p.resumo().lower()
    p2 = RL.abrir(out, autores={})
    assert not p2.assinado and "SEM assinatura" in p2.resumo()


def test_recusa_ferramenta_insegura_e_arquivos_extras(ambiente):
    ruim = _pacote(ambiente / "r.nexusrotina", {"limpa": {"steps": [{"tool": "file_controller", "params": {"action": "delete"}}]}})
    with pytest.raises(RL.ErroRotinas, match="recusada"):
        RL.abrir(ruim)
    com_codigo = _pacote(ambiente / "c.nexusrotina", {"ok": {"steps": [{"tool": "weather_report", "params": {}}]}},
                         extra={"evil.py": "import os"})
    with pytest.raises(RL.ErroRotinas, match="só rotina.json"):
        RL.abrir(com_codigo)
    sem_agenda_valida = _pacote(ambiente / "d.nexusrotina", {"ok": {"steps": [{"tool": "weather_report", "params": {}}],
                                                                  "agenda": {"dias": "nunca", "hora": "x"}}})
    with pytest.raises(RL.ErroRotinas, match="agenda"):
        RL.abrir(sem_agenda_valida)
    zip_quebrado = ambiente / "q.nexusrotina"
    zip_quebrado.write_bytes(b"nao e zip")
    with pytest.raises(RL.ErroRotinas):
        RL.abrir(zip_quebrado)


def test_assinatura_forjada_nao_vale(ambiente):
    priv, pub = L.gerar_par_de_chaves()
    outra_priv, _ = L.gerar_par_de_chaves()
    out = RL.exportar(["bom dia"], ambiente / "f.nexusrotina", {"id": "minhas_x", "nome": "M", "versao": "1.0", "autor": "Maria"}, outra_priv)
    assert not RL.abrir(out, autores={"Maria": pub}).assinado


def test_instala_sem_substituir_as_suas(ambiente):
    pacote = RL.abrir(RL.exportar(["bom dia"], ambiente / "i.nexusrotina", {"id": "minhas_x", "nome": "M", "versao": "1.0", "autor": "Maria"}))
    antes = SR._load()["bom dia"]
    assert RL.instalar(pacote).startswith("Instalei: bom dia (loja)")
    assert RL.instalar(pacote).startswith("Instalei: bom dia (3)")
    dados = SR._load()
    assert dados["bom dia"] == antes and dados["bom dia (loja)"]["origem"] == "loja:minhas_x"


def test_acao_pede_confirmar_antes_de_instalar(ambiente, monkeypatch):
    from actions import loja_plugins as A
    from core import confirm
    out = RL.exportar(["foco"], ambiente / "z.nexusrotina", {"id": "minhas_x", "nome": "M", "versao": "1.0", "autor": "Maria"})
    vistos = {}
    monkeypatch.setattr(confirm, "request", lambda key, title, detail, run: vistos.update(t=title, d=detail, run=run) or "[CONFIRMATION_PENDING]")
    monkeypatch.setattr(confirm, "pending_title", lambda: "")
    n0 = len(SR._load())
    assert "CONFIRMATION_PENDING" in A.loja_plugins({"action": "install_routines", "path": str(out)})
    assert len(SR._load()) == n0                                    # nada foi salvo antes do CONFIRMAR
    assert "SEM assinatura" in vistos["d"]
    assert vistos["run"]().startswith("[done]") and len(SR._load()) == n0 + 1
    r = A.loja_plugins({"action": "export_routines", "name": "foco, bom dia", "path": str(ambiente / "e.nexusrotina")})
    assert r.startswith("[done]")
