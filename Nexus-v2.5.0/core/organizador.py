"""Organizar a área de trabalho (NEXUS Pro 1.4.2).

"Nexus, organiza a área de trabalho" → os arquivos soltos na Área de Trabalho
vão para pastas por tipo, ali mesmo na Área de Trabalho:

    Imagens · Documentos · Planilhas · Apresentações · Vídeos · Músicas ·
    Compactados · Instaladores · Código · Outros

e os ícones são alinhados em ordem. "por data" separa em pastas por mês
(2026-10, 2026-09…).

Fica onde está:
  • atalhos (.lnk, .url) e pastas
  • arquivos ocultos ou do sistema (desktop.ini, Thumbs.db)
  • downloads em andamento (.crdownload, .part, .tmp) e arquivos de trava do
    Office (~$...), e o que foi mexido há menos de 1 minuto (pode estar sendo
    salvo)
  • arquivos abertos em outro programa (o Windows não deixa mover)

Nome repetido não é problema: vira "foto (2).jpg". Nada é apagado.

Desfazer: "desfaz a organização" põe cada arquivo de volta onde estava — até
depois de fechar e abrir o NEXUS (o registro fica em memory/organizacao_desktop.json).
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

CATEGORIAS: list[tuple[str, set[str]]] = [
    ("Imagens", {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico", ".heic",
                 ".heif", ".tif", ".tiff", ".raw", ".psd", ".avif"}),
    ("Documentos", {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".md", ".epub", ".xps"}),
    ("Planilhas", {".xls", ".xlsx", ".xlsm", ".csv", ".ods"}),
    ("Apresentações", {".ppt", ".pptx", ".pps", ".ppsx", ".odp", ".key"}),
    ("Vídeos", {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".3gp"}),
    ("Músicas", {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a", ".opus"}),
    ("Compactados", {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso"}),
    ("Instaladores", {".exe", ".msi", ".msix", ".appx", ".dmg", ".pkg", ".deb", ".rpm",
                      ".appimage", ".apk"}),
    ("Código", {".py", ".js", ".ts", ".html", ".htm", ".css", ".json", ".xml", ".cpp", ".c",
                ".h", ".java", ".cs", ".go", ".rs", ".sh", ".bat", ".cmd", ".ps1", ".php",
                ".sql", ".ipynb", ".yml", ".yaml"}),
]
OUTROS = "Outros"
NOMES = [n for n, _e in CATEGORIAS] + [OUTROS]
# pastas que versões antigas criavam (em inglês): continuam sendo usadas
_ANTIGAS = {"Imagens": "Images", "Documentos": "Documents", "Vídeos": "Videos",
            "Músicas": "Music", "Compactados": "Archives", "Código": "Code", "Outros": "Others",
            "Instaladores": "Executables"}

_FICA = {".lnk", ".url", ".desktop", ".webloc", ".pif"}
_EM_ANDAMENTO = {".crdownload", ".part", ".partial", ".download", ".tmp", ".temp", ".opdownload"}
_DO_SISTEMA = {"desktop.ini", "thumbs.db", ".ds_store"}
RECENTE_SEG = 60


def _base() -> Path:
    return Path(__file__).resolve().parent.parent


def _registro() -> Path:
    return _base() / "memory" / "organizacao_desktop.json"


def area_de_trabalho() -> Path:
    from actions.file_controller import _get_desktop
    return _get_desktop()


def categoria(arq: Path) -> str:
    ext = arq.suffix.lower()
    for nome, exts in CATEGORIAS:
        if ext in exts:
            return nome
    return OUTROS


def _oculto(arq: Path) -> bool:
    if arq.name.startswith(".") or arq.name.lower() in _DO_SISTEMA:
        return True
    if sys.platform.startswith("win"):
        try:
            atrib = os.stat(arq).st_file_attributes        # type: ignore[attr-defined]
            return bool(atrib & 0x2 or atrib & 0x4)        # HIDDEN | SYSTEM
        except Exception:
            return False
    return False


def _motivo_para_ficar(arq: Path, agora: float) -> str:
    """'' = pode mover; senão, por que fica onde está."""
    if not arq.is_file():
        return "pasta"
    if _oculto(arq):
        return "oculto"
    ext = arq.suffix.lower()
    if ext in _FICA:
        return "atalho"
    if ext in _EM_ANDAMENTO or arq.name.startswith("~$"):
        return "em andamento"
    try:
        if agora - arq.stat().st_mtime < RECENTE_SEG:
            return "recente"
    except OSError:
        return "inacessível"
    return ""


def _pasta_destino(raiz: Path, nome: str) -> Path:
    antiga = _ANTIGAS.get(nome)
    if antiga and (raiz / antiga).is_dir() and not (raiz / nome).exists():
        return raiz / antiga
    return raiz / nome


def _nome_livre(destino: Path) -> Path:
    if not destino.exists():
        return destino
    n = 2
    while True:
        c = destino.with_name(f"{destino.stem} ({n}){destino.suffix}")
        if not c.exists():
            return c
        n += 1


def _pasta_para(arq: Path, raiz: Path, modo: str) -> Path:
    if modo == "data":
        try:
            quando = datetime.fromtimestamp(arq.stat().st_mtime)
        except OSError:
            quando = datetime.now()
        return raiz / quando.strftime("%Y-%m")
    return _pasta_destino(raiz, categoria(arq))


def plano(modo: str = "tipo", raiz: Path | None = None) -> dict:
    """O que seria feito, sem mexer em nada."""
    raiz = raiz or area_de_trabalho()
    agora = time.time()
    mover: list[tuple[Path, Path]] = []
    ficam: dict[str, list[str]] = {}
    pastas_nossas = {(raiz / n).resolve() for n in NOMES} | {(raiz / a).resolve() for a in _ANTIGAS.values()}
    try:
        itens = sorted(raiz.iterdir(), key=lambda p: p.name.lower())
    except Exception as e:
        raise RuntimeError(f"não consegui ler a área de trabalho ({raiz}): {e}")
    base = _base().resolve()
    for item in itens:
        if item.resolve() in pastas_nossas:
            continue
        motivo = _motivo_para_ficar(item, agora)
        if not motivo and base in item.resolve().parents:
            motivo = "do NEXUS"
        if motivo:
            if motivo != "pasta":
                ficam.setdefault(motivo, []).append(item.name)
            continue
        mover.append((item, _pasta_para(item, raiz, modo)))
    return {"raiz": raiz, "mover": mover, "ficam": ficam, "modo": modo}


def _resumo_pastas(movidos: list[tuple[str, str]]) -> str:
    cont: dict[str, int] = {}
    for _o, d in movidos:
        pasta = Path(d).parent.name
        cont[pasta] = cont.get(pasta, 0) + 1
    return ", ".join(f"{p} {n}" for p, n in sorted(cont.items(), key=lambda x: -x[1]))


def organizar(modo: str = "tipo", simular: bool = False, alinhar_icones: bool = True,
              raiz: Path | None = None) -> str:
    modo = "data" if str(modo).lower() in ("data", "by_date", "date", "mes", "mês") else "tipo"
    try:
        p = plano(modo, raiz)
    except RuntimeError as e:
        return f"Não consegui organizar: {e}."
    raiz = p["raiz"]
    if simular:
        if not p["mover"]:
            return "A área de trabalho já está organizada: não há arquivos soltos para guardar."
        grupos: dict[str, list[str]] = {}
        for arq, pasta in p["mover"]:
            grupos.setdefault(pasta.name, []).append(arq.name)
        linhas = [f"Se eu organizar, {len(p['mover'])} arquivo(s) vão para pastas:"]
        for pasta, nomes in grupos.items():
            linhas.append(f"• {pasta} ({len(nomes)}): " + ", ".join(nomes[:6])
                          + (f" e mais {len(nomes) - 6}" if len(nomes) > 6 else ""))
        linhas.append("Atalhos e pastas ficam onde estão. Nada foi mexido ainda.")
        return "\n".join(linhas)

    movidos: list[tuple[str, str]] = []
    criadas: list[str] = []
    abertos: list[str] = []
    for arq, pasta in p["mover"]:
        try:
            if not pasta.exists():
                pasta.mkdir(parents=True)
                criadas.append(str(pasta))
            destino = _nome_livre(pasta / arq.name)
            shutil.move(str(arq), str(destino))
            movidos.append((str(arq), str(destino)))
        except PermissionError:
            abertos.append(arq.name)
        except OSError as e:
            if getattr(e, "winerror", None) in (32, 33):     # arquivo em uso
                abertos.append(arq.name)
            else:
                abertos.append(f"{arq.name} ({e.strerror or e})")

    if movidos:
        reg = _salvar_registro(raiz, movidos, criadas, modo)
        try:
            from core.undo import push_undo
            push_undo(f"organizei a área de trabalho ({len(movidos)} arquivos)",
                      lambda r=reg: desfazer(r))
        except Exception:
            pass
        try:
            from core import isa
            isa.registrar("resultado", "Área de trabalho organizada",
                          f"{len(movidos)} arquivo(s) — {_resumo_pastas(movidos)}", origem="arquivos")
        except Exception:
            pass
    if alinhar_icones:
        try:
            from actions.file_controller import arrange_desktop_icons
            arrange_desktop_icons()
        except Exception:
            pass

    if not movidos and not abertos:
        msg = "A área de trabalho já está organizada: não há arquivos soltos para guardar."
    elif not movidos:
        msg = "Não consegui mover nenhum arquivo."
    else:
        como = "por mês" if modo == "data" else "por tipo"
        msg = (f"Organizei a área de trabalho {como}: {len(movidos)} arquivo(s) guardados em pastas "
               f"({_resumo_pastas(movidos)}). Atalhos e pastas ficaram onde estavam.")
    if abertos:
        msg += (f" {len(abertos)} ficaram porque estão abertos em outro programa: "
                + ", ".join(abertos[:5]) + ("…" if len(abertos) > 5 else "") + ".")
    ficam = p["ficam"]
    if ficam.get("recente") or ficam.get("em andamento"):
        n = len(ficam.get("recente", [])) + len(ficam.get("em andamento", []))
        msg += f" {n} arquivo(s) sendo baixados ou salvos agora ficaram para depois."
    if movidos:
        msg += " Para voltar tudo como estava, diga “desfaz a organização”."
    return msg


def _salvar_registro(raiz: Path, movidos, criadas, modo) -> dict:
    dados = {"quando": datetime.now().isoformat(timespec="microseconds"),
             "raiz": str(raiz), "modo": modo, "movidos": movidos, "pastas_criadas": criadas}
    try:
        reg = _registro()
        reg.parent.mkdir(parents=True, exist_ok=True)
        reg.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:
        print(f"[Organizar] não gravei o registro para desfazer: {e}")
    return dados


def desfazer(reg: dict | None = None) -> str:
    """Põe cada arquivo da última organização (ou da `reg` dada) de volta onde estava."""
    try:
        salvo = json.loads(_registro().read_text(encoding="utf-8"))
    except Exception:
        salvo = None
    if reg is None:
        reg = salvo
    if not reg or reg.get("desfeito"):
        return "Não há organização da área de trabalho para desfazer."
    reg["desfeito"] = True
    voltaram, faltaram = 0, []
    for origem, destino in reg.get("movidos", []):
        o, d = Path(origem), Path(destino)
        if not d.exists():
            faltaram.append(d.name)
            continue
        try:
            alvo = _nome_livre(o)
            o.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(d), str(alvo))
            voltaram += 1
        except Exception:
            faltaram.append(d.name)
    for pasta in sorted(reg.get("pastas_criadas", []), key=len, reverse=True):
        try:
            p = Path(pasta)
            if p.is_dir() and not any(p.iterdir()):
                p.rmdir()
        except Exception:
            pass
    if salvo and salvo.get("quando") == reg.get("quando"):
        try:
            _registro().replace(_registro().with_suffix(".desfeito.json"))
        except Exception:
            pass
    msg = f"Desfiz a organização: {voltaram} arquivo(s) voltaram para a área de trabalho."
    if faltaram:
        msg += (f" {len(faltaram)} não estavam mais na pasta (você mudou de lugar ou apagou): "
                + ", ".join(faltaram[:5]) + ".")
    return msg
