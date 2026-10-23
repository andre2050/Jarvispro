"""Manutenção do PC — espaço em disco, limpeza, backup, rede e bateria (NEXUS Pro 2.2).

Por voz:  "quanto espaço livre eu tenho?"          "o que está ocupando espaço na pasta Downloads?"
          "limpa os arquivos temporários"          "faz backup da pasta Projetos"
          "qual o meu IP?"   "testa a conexão com o google.com"   "como está a bateria?"

Segurança:
  • Limpar temporários NÃO apaga nada sem o seu CONFIRMAR na tela (mostra o tamanho antes).
    Só mexe na pasta temporária do sistema, só em arquivos parados há 2 dias ou mais, nunca segue
    atalhos e pula o que estiver em uso.
  • Backup só LÊ a pasta de origem; grava um .zip novo (nunca sobrescreve) e confere o arquivo no fim.
  • Ping só aceita nome de servidor/IP, sem espaço nem símbolos, e roda sem shell.
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path

_WIN_HIDE = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
_HOST_OK = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9.\-]*[A-Za-z0-9])?$")
_IGNORAR_BACKUP = {"__pycache__", "node_modules", ".venv", "venv", ".git", ".cache", "$RECYCLE.BIN"}
_LIMITE_BACKUP = 4 * 1024 ** 3          # 4 GB de origem
_TEMPO_BACKUP = 300.0


def humano(n: float) -> str:
    for un in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or un == "TB":
            return f"{n:.0f} {un}" if un == "B" else f"{n:.1f} {un}"
        n /= 1024
    return f"{n:.1f} TB"


# ── disco ────────────────────────────────────────────────────────────────────
def _disco() -> str:
    """Lista partições acessíveis; usa pontos comuns como fallback se a enumeração falhar."""
    import psutil
    linhas = []
    vistos = set()
    try:
        particoes = psutil.disk_partitions(all=False)
    except Exception:
        particoes = []

    for p in particoes:
        ponto = getattr(p, "mountpoint", None)
        if not ponto or ponto in vistos or "cdrom" in (getattr(p, "opts", "") or "").lower():
            continue
        vistos.add(ponto)
        try:
            u = psutil.disk_usage(ponto)
        except (OSError, PermissionError, ValueError):
            continue
        except Exception:
            continue
        if u.total > 0:
            linhas.append(f"{ponto}: {humano(u.free)} livres de {humano(u.total)} ({u.percent:.0f}% usado)")

    # Em alguns containers, WSLs e sistemas restritos disk_partitions() pode
    # retornar vazio mesmo quando disk_usage() consegue consultar o volume.
    if not linhas:
        candidatos = [Path.cwd(), Path.home(), Path(os.path.abspath(os.sep))]
        if sys.platform == "win32":
            candidatos.insert(0, Path(os.environ.get("SystemDrive", "C:") + os.sep))
        for candidato in candidatos:
            try:
                ponto = str(candidato.resolve())
                if ponto in vistos:
                    continue
                u = psutil.disk_usage(ponto)
                if u.total > 0:
                    vistos.add(ponto)
                    linhas.append(f"{ponto}: {humano(u.free)} livres de {humano(u.total)} ({u.percent:.0f}% usado)")
                    break
            except Exception:
                continue
    return " | ".join(linhas[:8]) or "Não consegui ler os discos. Verifique as permissões do sistema."


def tamanho_pasta(pasta: Path, prazo: float, parar_em: int = 2_000_000) -> tuple[int, bool]:
    """Soma o tamanho de tudo dentro da pasta, sem seguir atalhos. Devolve (bytes, completo?)."""
    total, vistos = 0, 0
    pilha = [pasta]
    while pilha:
        if time.monotonic() > prazo or vistos > parar_em:
            return total, False
        atual = pilha.pop()
        try:
            with os.scandir(atual) as it:
                for e in it:
                    vistos += 1
                    try:
                        if e.is_symlink():
                            continue
                        if e.is_dir(follow_symlinks=False):
                            pilha.append(Path(e.path))
                        elif e.is_file(follow_symlinks=False):
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total, True


def _pastas_grandes(caminho: str, quantas: int) -> str:
    base = Path(os.path.expanduser(caminho or "~")).resolve()
    if not base.is_dir():
        return f"[failed] A pasta não existe: {base}"
    prazo = time.monotonic() + 20
    medidas, soltos = [], 0
    try:
        filhos = list(os.scandir(base))
    except OSError as e:
        return f"[failed] Não consegui abrir {base}: {e.strerror or e}"
    completo = True
    for e in filhos:
        try:
            if e.is_symlink():
                continue
            if e.is_dir(follow_symlinks=False):
                t, ok = tamanho_pasta(Path(e.path), prazo)
                completo &= ok
                medidas.append((t, e.name + "/"))
            elif e.is_file(follow_symlinks=False):
                soltos += e.stat(follow_symlinks=False).st_size
        except OSError:
            continue
    if soltos:
        medidas.append((soltos, "(arquivos soltos)"))
    if not medidas:
        return f"A pasta {base.name or base} está vazia."
    medidas.sort(reverse=True)
    top = " | ".join(f"{n} {humano(t)}" for t, n in medidas[:quantas])
    return (f"Em {base}: {top}. Total {humano(sum(t for t, _ in medidas))}"
            + ("" if completo else " (a medição parou no tempo limite; os números são mínimos)") + ".")


# ── temporários ──────────────────────────────────────────────────────────────
def _candidatos_temp(dias: float) -> tuple[list[Path], int]:
    raiz = Path(tempfile.gettempdir()).resolve()
    corte = time.time() - dias * 86400
    arquivos, total = [], 0
    for dirpath, dirnames, filenames in os.walk(raiz, followlinks=False):
        dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))]
        for nome in filenames:
            p = Path(dirpath) / nome
            try:
                st = p.lstat()
                if p.is_symlink() or st.st_mtime > corte:
                    continue
                arquivos.append(p)
                total += st.st_size
            except OSError:
                continue
        if len(arquivos) > 200_000:
            break
    return arquivos, total


def _apagar_temp(arquivos: list[Path]) -> str:
    raiz = Path(tempfile.gettempdir()).resolve()
    apagados = livres = 0
    for p in arquivos:
        try:
            if raiz not in p.resolve().parents:        # nunca fora da pasta temporária
                continue
            tam = p.lstat().st_size
            p.unlink()
            apagados += 1
            livres += tam
        except OSError:
            continue                                   # em uso: fica
    for dirpath, _d, _f in os.walk(raiz, topdown=False):
        try:
            if Path(dirpath) != raiz:
                os.rmdir(dirpath)                      # só apaga pasta vazia
        except OSError:
            pass
    return f"[done] Limpeza feita: {apagados} arquivo(s) temporário(s) apagado(s), {humano(livres)} liberados."


def _limpar_temp(dias: float) -> str:
    arquivos, total = _candidatos_temp(dias)
    if not arquivos:
        return f"Não há temporários parados há {dias:g} dia(s) ou mais. Nada a limpar."
    from core import confirm
    if confirm.pending_title():
        return "[failed] Já existe uma confirmação na tela. Peça ao usuário para responder a ela primeiro."
    return confirm.request(
        "manutencao_pc", "Limpar arquivos temporários",
        f"{len(arquivos)} arquivo(s), {humano(total)}, na pasta temporária do sistema,\n"
        f"parados há {dias:g} dia(s) ou mais. Arquivos em uso são pulados.",
        lambda a=arquivos: _apagar_temp(a))


# ── backup ───────────────────────────────────────────────────────────────────
def _backup(origem: str, destino: str) -> str:
    src = Path(os.path.expanduser(origem or "")).resolve() if origem else None
    if not src or not src.is_dir():
        return "[failed] Diga qual pasta copiar (ela precisa existir)."
    dest_dir = Path(os.path.expanduser(destino)).resolve() if destino else Path.home() / "Documents" / "NexusBackups"
    if src == dest_dir or src in dest_dir.parents:
        return "[failed] O destino não pode ficar dentro da pasta de origem."
    if src == Path(src.anchor):
        return "[failed] Escolha uma pasta, não o disco inteiro."
    prazo = time.monotonic() + _TEMPO_BACKUP
    tam, completo = tamanho_pasta(src, time.monotonic() + 30)
    if not completo or tam > _LIMITE_BACKUP:
        return f"[failed] A pasta é grande demais para o backup por voz (limite {humano(_LIMITE_BACKUP)})."
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return f"[failed] Não consegui criar a pasta de destino: {e.strerror or e}"
    nome = re.sub(r"[^\w\-]+", "_", src.name or "backup") + "_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".zip"
    alvo = dest_dir / nome
    n = 0
    try:
        with zipfile.ZipFile(alvo, "x", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
            for dirpath, dirnames, filenames in os.walk(src, followlinks=False):
                dirnames[:] = [d for d in dirnames if d not in _IGNORAR_BACKUP
                               and not os.path.islink(os.path.join(dirpath, d))]
                for f in filenames:
                    if time.monotonic() > prazo:
                        raise TimeoutError
                    p = Path(dirpath) / f
                    if p.is_symlink():
                        continue
                    try:
                        z.write(p, p.relative_to(src).as_posix())
                        n += 1
                    except OSError:
                        continue                       # arquivo em uso: pula
        with zipfile.ZipFile(alvo) as z:
            ruim = z.testzip()
        if ruim:
            raise zipfile.BadZipFile(ruim)
    except TimeoutError:
        alvo.unlink(missing_ok=True)
        return "[failed] O backup demorou mais de 5 minutos e foi cancelado. Tente uma pasta menor."
    except Exception as e:
        alvo.unlink(missing_ok=True)
        return f"[failed] O backup não deu certo: {e}"
    return f"[done] Backup conferido: {n} arquivo(s), {humano(alvo.stat().st_size)}, salvo em {alvo}"


# ── rede e bateria ───────────────────────────────────────────────────────────
def _ip_local() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))                # UDP: não envia nada, só escolhe a interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _rede() -> str:
    import psutil
    ip = _ip_local()
    st = psutil.net_io_counters()
    return (f"IP na rede local: {ip}. Desde que o PC ligou: {humano(st.bytes_recv)} baixados e "
            f"{humano(st.bytes_sent)} enviados.")


def _ip_publico() -> str:
    import requests
    try:
        r = requests.get("https://api.ipify.org", timeout=6)
        ip = r.text.strip()
        if r.ok and re.fullmatch(r"[0-9a-fA-F:.]{3,45}", ip):
            return f"Seu IP público é {ip}."
    except Exception:
        pass
    return "[failed] Não consegui consultar o IP público (sem internet?)."


def _ping(host: str) -> str:
    host = str(host or "").strip()
    if not _HOST_OK.match(host):
        return "[failed] Diga um endereço válido, como google.com ou 8.8.8.8."
    cmd = ["ping", "-n", "4", host] if sys.platform == "win32" else ["ping", "-c", "4", "-W", "3", host]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=25, **_WIN_HIDE)
    except FileNotFoundError:
        return "[failed] O comando ping não existe neste computador."
    except subprocess.TimeoutExpired:
        return f"[failed] {host} não respondeu a tempo."
    saida = r.stdout or ""
    perda = re.search(r"(\d+)%\s*(?:packet\s*)?(?:loss|perd)", saida, re.IGNORECASE)
    media = re.search(r"(?:Average|M[eé]dia)\s*=\s*(\d+)\s*ms", saida, re.IGNORECASE) or \
        re.search(r"= [\d.]+/([\d.]+)/", saida)
    if r.returncode != 0 and not media:
        return f"[failed] Sem resposta de {host}. A conexão pode estar fora, ou o servidor bloqueia ping."
    ms = f"{float(media.group(1)):.0f} ms de média" if media else "respondeu"
    return f"{host}: {ms}" + (f", {perda.group(1)}% de perda." if perda else ".")


def _bateria() -> str:
    import psutil
    try:
        leitor = getattr(psutil, "sensors_battery", None)
        b = leitor() if callable(leitor) else None
    except (OSError, RuntimeError, NotImplementedError):
        return "Não foi possível consultar a bateria neste sistema."
    except Exception:
        return "O sistema não conseguiu informar o estado da bateria."
    if b is None:
        return "Este computador não tem bateria (ou o sistema não informa)."
    try:
        resto = ""
        if not b.power_plugged and b.secsleft and b.secsleft > 0:
            resto = f", cerca de {b.secsleft // 3600}h{(b.secsleft % 3600) // 60:02d} restantes"
        estado = "na tomada" if b.power_plugged else "na bateria"
        return f"Bateria em {float(b.percent):.0f}%, {estado}{resto}."
    except (AttributeError, TypeError, ValueError):
        return "A bateria foi detectada, mas o sistema retornou dados incompletos."


def manutencao_pc(parameters: dict, player=None) -> str:
    acao = str(parameters.get("action") or "disk").strip().lower()
    try:
        if acao in ("disk", "disco", "space"):
            return _disco()
        if acao in ("big_folders", "ocupando", "usage"):
            try:
                n = max(1, min(15, int(parameters.get("top") or 6)))
            except (TypeError, ValueError):
                n = 6
            return _pastas_grandes(parameters.get("path") or "~", n)
        if acao in ("temp_scan", "temp"):
            arq, tot = _candidatos_temp(_dias(parameters))
            return f"{len(arq)} arquivo(s) temporário(s) velhos, {humano(tot)} que dá para liberar."
        if acao in ("temp_clean", "limpar"):
            return _limpar_temp(_dias(parameters))
        if acao == "backup":
            return _backup(parameters.get("path") or "", parameters.get("destination") or "")
        if acao in ("network", "rede"):
            return _rede()
        if acao in ("public_ip", "ip"):
            return _ip_publico()
        if acao == "ping":
            return _ping(parameters.get("host"))
        if acao in ("battery", "bateria"):
            return _bateria()
    except ImportError as e:
        return f"[failed] Falta instalar um pacote: {e.name}."
    return "Ação desconhecida. Use disk, big_folders, temp_scan, temp_clean, backup, network, public_ip, ping ou battery."


def _dias(p: dict) -> float:
    try:
        return max(0.0, min(365.0, float(p.get("days") if p.get("days") is not None else 2)))
    except (TypeError, ValueError):
        return 2.0


TOOL = {
    "name": "manutencao_pc",
    "description": (
        "PC MAINTENANCE: action=disk (free space per drive); action=big_folders with path (what is using "
        "space; default home) + optional top; action=temp_scan (how much temp junk), action=temp_clean "
        "(asks the user to CONFIRM on screen before deleting anything — tell them to press CONFIRM; "
        "optional days = minimum age, default 2); action=backup with path (folder to zip, verified, never "
        "overwrites) + optional destination folder; action=network (local IP and traffic), public_ip, "
        "ping with host (e.g. google.com), battery."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "disk | big_folders | temp_scan | temp_clean | backup | network | public_ip | ping | battery"},
            "path": {"type": "STRING", "description": "Folder for big_folders / backup (e.g. ~/Downloads)"},
            "destination": {"type": "STRING", "description": "For backup: folder to save the .zip in (default Documents/NexusBackups)"},
            "host": {"type": "STRING", "description": "For ping: host name or IP, e.g. google.com"},
            "top": {"type": "INTEGER", "description": "For big_folders: how many entries (default 6)"},
            "days": {"type": "NUMBER", "description": "For temp_scan/temp_clean: only files older than this many days (default 2)"},
        },
        "required": ["action"],
    },
    "handler": manutencao_pc,
}
