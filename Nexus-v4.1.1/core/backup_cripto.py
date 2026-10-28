"""Backup criptografado automático (3.7): suas memórias e configurações, cifradas, numa pasta que sincroniza com a SUA nuvem.

Como funciona
  • Você escolhe uma pasta (a do OneDrive, Google Drive, Dropbox… ou um pendrive) e uma FRASE-SENHA.
  • O NEXUS junta memory/ e config/ (dados e chaves, sem código nem caches), cifra com AES-256-GCM (chave derivada da
    frase por scrypt) e grava `nexus-backup-AAAAMMDD-HHMM.nexusbak` na pasta. A nuvem só vê um arquivo ilegível.
  • A frase NÃO é guardada. Para o backup automático, o PC guarda só a chave derivada em memory/backup_chave.json
    (fora do GitHub): quem roubar o arquivo da nuvem não consegue abri-lo; para restaurar em outro PC basta a frase.
  • Mantém os últimos 7 backups. Restaurar pede CONFIRMAR no HUD, só aceita nomes seguros e não toca em código.
"""
from __future__ import annotations

import io
import json
import os
import secrets
import time
import zipfile
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
ARQ_CONFIG = _BASE / "memory" / "backup_chave.json"
MAGIA = b"NXBK1"
PREFIXO = "nexus-backup-"
EXT = ".nexusbak"
MANTER = 7
INTERVALO_H = 24
MAX_BYTES = 300 * 1024 * 1024
RAIZES = ("memory", "config")
IGNORAR_NOMES = {"rag_documentos.npz", "backup_chave.json", "queda_nativa.log"}
IGNORAR_DIRS = {"__pycache__", "emails_cache", "regeneracao_copias", "certs_antigos"}
IGNORAR_EXT = {".py", ".pyc", ".tmp", ".log"}


class ErroBackup(Exception):
    pass


def _kdf(frase: str, sal: bytes) -> bytes:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    return Scrypt(salt=sal, length=32, n=2 ** 15, r=8, p=1).derive(frase.encode("utf-8"))


def _aes(chave: bytes):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM(chave)


def _arquivos(base: Path):
    for raiz in RAIZES:
        for dp, dn, fn in os.walk(base / raiz):
            dn[:] = [d for d in dn if d not in IGNORAR_DIRS and not d.startswith(".")]
            for nome in fn:
                p = Path(dp) / nome
                if nome in IGNORAR_NOMES or p.suffix.lower() in IGNORAR_EXT or nome.startswith("."):
                    continue
                yield p


def _compactar(base: Path) -> bytes:
    buf = io.BytesIO()
    total = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in _arquivos(base):
            total += p.stat().st_size
            if total > MAX_BYTES:
                raise ErroBackup("Os dados passam de 300 MB; limpe algo antes de fazer o backup.")
            z.write(p, p.relative_to(base).as_posix())
    return buf.getvalue()


def cifrar(dados: bytes, chave: bytes, sal: bytes) -> bytes:
    nonce = secrets.token_bytes(12)
    return MAGIA + sal + nonce + _aes(chave).encrypt(nonce, dados, MAGIA + sal)


def decifrar(blob: bytes, frase: str) -> bytes:
    if not blob.startswith(MAGIA) or len(blob) < len(MAGIA) + 16 + 12 + 16:
        raise ErroBackup("Esse arquivo não é um backup do NEXUS.")
    sal = blob[5:21]
    nonce = blob[21:33]
    try:
        return _aes(_kdf(frase, sal)).decrypt(nonce, blob[33:], MAGIA + sal)
    except Exception:
        raise ErroBackup("Frase errada ou arquivo alterado.") from None


# ── configuração (pasta + chave derivada) ────────────────────────────────────
def _cfg(arq: Path | None = None) -> dict:
    try:
        d = json.loads(Path(arq or ARQ_CONFIG).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def configurar(pasta: str, frase: str, arq: Path | None = None) -> str:
    p = Path(str(pasta)).expanduser()
    if not p.is_dir():
        raise ErroBackup("Não achei essa pasta. Crie-a (ou abra o app da nuvem) e tente de novo.")
    try:
        if p.resolve() == _BASE.resolve() or _BASE.resolve() in p.resolve().parents:
            raise ErroBackup("Escolha uma pasta fora da pasta do NEXUS (a da sua nuvem).")
    except OSError:
        pass
    if len(frase or "") < 8:
        raise ErroBackup("A frase-senha precisa ter pelo menos 8 caracteres.")
    sal = secrets.token_bytes(16)
    arq = Path(arq or ARQ_CONFIG)
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps({"pasta": str(p), "sal": sal.hex(), "chave": _kdf(frase, sal).hex(),
                               "ativo": True, "ultimo": 0}), encoding="utf-8")
    try:
        os.chmod(arq, 0o600)
    except OSError:
        pass
    return str(p)


def desligar(arq: Path | None = None) -> None:
    arq = Path(arq or ARQ_CONFIG)
    if arq.exists():
        arq.unlink()


def pronto(arq: Path | None = None) -> bool:
    c = _cfg(arq)
    return bool(c.get("ativo") and c.get("chave") and c.get("pasta"))


def fazer_backup(base: Path | None = None, arq: Path | None = None, agora: float | None = None) -> dict:
    base = Path(base or _BASE)
    c = _cfg(arq)
    if not (c.get("chave") and c.get("pasta")):
        raise ErroBackup("O backup ainda não foi configurado: diga a pasta e a frase-senha.")
    pasta = Path(c["pasta"])
    if not pasta.is_dir():
        raise ErroBackup("A pasta do backup não está acessível agora (nuvem desconectada?).")
    zipado = _compactar(base)
    sal = bytes.fromhex(c["sal"])
    blob = cifrar(zipado, bytes.fromhex(c["chave"]), sal)
    t = time.localtime(agora or time.time())
    nome = f"{PREFIXO}{time.strftime('%Y%m%d-%H%M%S', t)}{EXT}"
    tmp = pasta / (nome + ".part")
    tmp.write_bytes(blob)
    tmp.replace(pasta / nome)
    antigos = sorted(f for f in pasta.glob(f"{PREFIXO}*{EXT}"))
    for f in antigos[:-MANTER]:
        f.unlink(missing_ok=True)
    c["ultimo"] = agora or time.time()
    Path(arq or ARQ_CONFIG).write_text(json.dumps(c), encoding="utf-8")
    return {"arquivo": nome, "kb": len(blob) // 1024, "guardados": min(len(antigos), MANTER)}


def listar(arq: Path | None = None) -> list[str]:
    c = _cfg(arq)
    p = Path(c.get("pasta", ""))
    return sorted((f.name for f in p.glob(f"{PREFIXO}*{EXT}")), reverse=True) if p.is_dir() else []


def precisa_backup(arq: Path | None = None, agora: float | None = None) -> bool:
    c = _cfg(arq)
    return pronto(arq) and (agora or time.time()) - float(c.get("ultimo") or 0) >= INTERVALO_H * 3600


def _nome_seguro(n: str) -> bool:
    return n.startswith(PREFIXO) and n.endswith(EXT) and "/" not in n and "\\" not in n and ".." not in n


def restaurar(nome: str, frase: str, base: Path | None = None, arq: Path | None = None, pasta: str | None = None) -> int:
    """Decifra e escreve os arquivos em memory/ e config/. Devolve quantos. Só caminhos dessas duas pastas."""
    base = Path(base or _BASE)
    pasta_b = Path(pasta or _cfg(arq).get("pasta", ""))
    if not _nome_seguro(nome):
        raise ErroBackup("Nome de backup inválido.")
    f = pasta_b / nome
    if not f.is_file():
        raise ErroBackup("Não achei esse backup na pasta.")
    dados = decifrar(f.read_bytes(), frase)
    n = 0
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        for info in z.infolist():
            alvo = (base / info.filename).resolve()
            top = info.filename.split("/")[0]
            if info.is_dir() or top not in RAIZES or base.resolve() not in alvo.parents or alvo.suffix.lower() in IGNORAR_EXT:
                continue                                  # nada fora de memory/ e config/, nunca código
            if info.file_size > MAX_BYTES:
                continue
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_bytes(z.read(info))
            n += 1
    return n
