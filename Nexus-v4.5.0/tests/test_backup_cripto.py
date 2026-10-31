"""Backup criptografado: cifra de verdade, frase errada falha, restaura só em memory/ e config/, sem segredos em claro."""
import io
import zipfile

import pytest

from core import backup_cripto as B


@pytest.fixture
def cen(tmp_path):
    base = tmp_path / "nexus"
    (base / "memory").mkdir(parents=True)
    (base / "config").mkdir()
    (base / "memory" / "notas.json").write_text('{"nota": "senha do wifi é BANANA-9921"}', encoding="utf-8")
    (base / "config" / "api_keys.json").write_text('{"gemini_api_key": "CHAVE-SECRETA-XYZ"}', encoding="utf-8")
    (base / "memory" / "codigo.py").write_text("print('nao entra')", encoding="utf-8")
    (base / "memory" / "rag_documentos.npz").write_bytes(b"x" * 10)
    (base / "memory" / "__pycache__").mkdir()
    (base / "memory" / "__pycache__" / "a.pyc").write_bytes(b"x")
    nuvem = tmp_path / "OneDrive"
    nuvem.mkdir()
    return base, nuvem, tmp_path / "chave.json"


def test_arquivo_na_nuvem_nao_tem_nada_legivel(cen):
    base, nuvem, cfg = cen
    B.configurar(str(nuvem), "frase bem comprida 123", cfg)
    r = B.fazer_backup(base, cfg)
    blob = (nuvem / r["arquivo"]).read_bytes()
    assert blob.startswith(B.MAGIA)
    for segredo in (b"BANANA", b"CHAVE-SECRETA", b"api_keys", b"notas.json", b"PK\x03\x04"):
        assert segredo not in blob


def test_restaura_com_a_frase_certa_e_so_o_que_deve(cen, tmp_path):
    base, nuvem, cfg = cen
    B.configurar(str(nuvem), "frase bem comprida 123", cfg)
    r = B.fazer_backup(base, cfg)
    novo = tmp_path / "outro_pc"
    (novo / "memory").mkdir(parents=True)
    n = B.restaurar(r["arquivo"], "frase bem comprida 123", novo, pasta=str(nuvem))
    assert n == 2 and "BANANA" in (novo / "memory" / "notas.json").read_text(encoding="utf-8")
    assert not (novo / "memory" / "codigo.py").exists() and not (novo / "memory" / "rag_documentos.npz").exists()


def test_frase_errada_e_arquivo_adulterado_falham(cen, tmp_path):
    base, nuvem, cfg = cen
    B.configurar(str(nuvem), "frase bem comprida 123", cfg)
    nome = B.fazer_backup(base, cfg)["arquivo"]
    with pytest.raises(B.ErroBackup, match="Frase errada"):
        B.restaurar(nome, "outra frase qualquer", tmp_path / "x", pasta=str(nuvem))
    f = nuvem / nome
    b = bytearray(f.read_bytes())
    b[-5] ^= 1
    f.write_bytes(bytes(b))
    with pytest.raises(B.ErroBackup):
        B.restaurar(nome, "frase bem comprida 123", tmp_path / "x", pasta=str(nuvem))


def test_zip_malicioso_nao_escapa_das_pastas(tmp_path):
    base = tmp_path / "pc"
    base.mkdir()
    sal = b"s" * 16
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../fora.txt", "x")
        z.writestr("memory/../../fora2.txt", "x")
        z.writestr("main.py", "x")
        z.writestr("memory/ok.json", "{}")
    nuvem = tmp_path / "n"
    nuvem.mkdir()
    (nuvem / "nexus-backup-1.nexusbak").write_bytes(B.cifrar(buf.getvalue(), B._kdf("frase de teste 1", sal), sal))
    assert B.restaurar("nexus-backup-1.nexusbak", "frase de teste 1", base, pasta=str(nuvem)) == 1
    assert (base / "memory" / "ok.json").exists() and not (tmp_path / "fora.txt").exists() and not (base / "main.py").exists()
    with pytest.raises(B.ErroBackup):
        B.restaurar("../../etc/passwd", "x", base, pasta=str(nuvem))


def test_rodizio_intervalo_e_validacoes(cen, monkeypatch):
    base, nuvem, cfg = cen
    monkeypatch.setattr(B, "_BASE", base)
    with pytest.raises(B.ErroBackup):
        B.configurar(str(nuvem / "nao_existe"), "frase bem comprida 123", cfg)
    with pytest.raises(B.ErroBackup):
        B.configurar(str(nuvem), "curta", cfg)
    with pytest.raises(B.ErroBackup):
        B.configurar(str(base), "frase bem comprida 123", cfg)          # dentro do NEXUS
    B.configurar(str(nuvem), "frase bem comprida 123", cfg)
    assert B.precisa_backup(cfg, agora=1e10)
    for i in range(10):
        B.fazer_backup(base, cfg, agora=1.7e9 + i * 100)
    assert len(B.listar(cfg)) == B.MANTER
    assert not B.precisa_backup(cfg, agora=1.7e9 + 1000 + 3600)
    assert B.precisa_backup(cfg, agora=1.7e9 + 1000 + 25 * 3600)


def test_acao_pede_confirmar_para_restaurar(cen, monkeypatch):
    from actions import backup_cripto as A
    base, nuvem, cfg = cen
    monkeypatch.setattr(B, "ARQ_CONFIG", cfg)
    monkeypatch.setattr(B, "_BASE", base)
    assert "não configurado" in A.backup_cripto({"action": "status"})
    r = A.backup_cripto({"action": "setup", "folder": str(nuvem), "passphrase": "frase bem comprida 123"})
    assert r.startswith("[done]") and "ANOTE" in r
    assert "frase bem" not in r
    vistos = {}
    from core import confirm
    monkeypatch.setattr(confirm, "request", lambda k, t, d, run: vistos.update(k=k, run=run) or "[CONFIRMATION_PENDING]")
    assert "CONFIRMATION_PENDING" in A.backup_cripto({"action": "restore", "passphrase": "frase bem comprida 123"})
    assert vistos["k"] == "backup_restaurar"
    assert A.backup_cripto({"action": "setup", "folder": "/nao/existe", "passphrase": "frase bem comprida 123"}).startswith("[failed]")
