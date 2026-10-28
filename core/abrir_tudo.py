"""core/abrir_tudo.py — abrir pasta, arquivo ou programa pelo nome (NEXUS Ultra 2026 3.9).

"abre Downloads", "abre o relatório de outubro", "abre C:\\Projetos\\nota.pdf", "abre o Calculadora".
  • Pastas conhecidas (Downloads, Documentos, Imagens, Músicas, Vídeos, Área de Trabalho) por apelido; ou caminho que exista.
  • Arquivo por nome: procura nessas pastas (até 3 níveis); se achar um só, abre; se achar vários, lista (nunca escolhe no chute).
  • Programa: por nome, entregue ao open_app (que só abre apps instalados/conhecidos).
Segurança: NÃO abre por caminho arquivos que executam código ou rodam macros (.exe .bat .cmd .ps1 .msi .vbs .js .lnk .reg .hta .docm …) nem
caminhos de rede (\\\\servidor); cai fora de "..", aceita só o que existe. `abridor` e `app` são injetáveis.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

PERIGOSAS = {".exe", ".bat", ".cmd", ".com", ".scr", ".pif", ".ps1", ".psm1", ".msi", ".msp", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh",
             ".lnk", ".url", ".reg", ".hta", ".jar", ".dll", ".cpl", ".msc", ".chm", ".docm", ".xlsm", ".pptm", ".dotm", ".xlam", ".gadget",
             ".appref-ms", ".application", ".sh", ".py", ".pyw", ".appimage", ".desktop"}
APELIDOS = {"downloads": "Downloads", "download": "Downloads", "baixados": "Downloads", "documentos": "Documents", "meus documentos": "Documents",
            "imagens": "Pictures", "fotos": "Pictures", "figuras": "Pictures", "musicas": "Music", "musica": "Music", "videos": "Videos",
            "area de trabalho": "Desktop", "desktop": "Desktop", "home": ""}
PROCURAR_EM = ("Desktop", "Documents", "Downloads", "Pictures")
MAX_VARRIDOS = 4000


def _n(t) -> str:
    return unicodedata.normalize("NFKD", str(t or "").lower()).encode("ascii", "ignore").decode().strip()


def abridor_padrao(caminho: str) -> None:
    if sys.platform.startswith("win"):
        os.startfile(caminho)                                           # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", caminho])
    else:
        subprocess.Popen(["xdg-open", caminho])


def _casa() -> Path:
    return Path.home()


def pasta_conhecida(nome: str, casa: Path | None = None) -> Path | None:
    casa = casa or _casa()
    sub = APELIDOS.get(_n(nome).removeprefix("a pasta ").removeprefix("pasta ").removeprefix("de ").strip())
    if sub is None:
        return None
    p = casa / sub if sub else casa
    if sub == "Documents" and not p.exists() and (casa / "Documentos").exists():
        p = casa / "Documentos"
    return p if p.is_dir() else None


def _parece_caminho(t: str) -> bool:
    return bool(re.match(r"^([a-zA-Z]:[\\/]|~|/|\\\\)", t.strip())) or "/" in t or "\\" in t


def procurar_arquivo(consulta: str, casa: Path | None = None) -> list[Path]:
    casa = casa or _casa()
    palavras = [w for w in _n(consulta).split() if len(w) > 1 and w not in ("o", "a", "de", "do", "da", "arquivo", "documento")]
    if not palavras:
        return []
    achados, vistos = [], 0
    for base in PROCURAR_EM:
        raiz = casa / base
        if not raiz.is_dir():
            continue
        prof0 = len(raiz.parts)
        for dp, dns, fns in os.walk(raiz):
            if len(Path(dp).parts) - prof0 >= 3:
                dns[:] = []
            dns[:] = [d for d in dns if not d.startswith(".")]
            for f in fns:
                vistos += 1
                if vistos > MAX_VARRIDOS:
                    return achados
                if not f.startswith(".") and all(w in _n(f) for w in palavras) and Path(f).suffix.lower() not in PERIGOSAS:
                    achados.append(Path(dp) / f)
    return sorted(achados, key=lambda p: -p.stat().st_mtime)[:6]


def abrir(alvo: str, abridor=None, app=None, casa: Path | None = None) -> str:
    alvo = str(alvo or "").strip().strip('"').strip("'")
    if not alvo:
        return "Diga o que abrir (pasta, arquivo ou programa)."
    abridor = abridor or abridor_padrao
    if alvo.startswith("\\\\") or alvo.startswith("//"):
        return "Não abro caminhos de rede por aqui."
    p = pasta_conhecida(alvo, casa)
    if p:
        abridor(str(p))
        return f"[done] Abri a pasta {p.name}."
    if _parece_caminho(alvo):
        c = Path(os.path.expanduser(alvo))
        if ".." in c.parts:
            return "Não aceito caminhos com “..”."
        if not c.exists():
            return f"Não achei “{alvo}”."
        c = c.resolve()
        if c.is_file() and c.suffix.lower() in PERIGOSAS:
            return f"Não abro arquivos {c.suffix} por caminho (podem executar código). Para programas, diga o nome do programa."
        abridor(str(c))
        return f"[done] Abri {'a pasta' if c.is_dir() else 'o arquivo'} {c.name}."
    ach = procurar_arquivo(alvo, casa) if re.search(r"\w", alvo) and (len(alvo.split()) > 1 or "." in alvo) else []
    if len(ach) == 1:
        abridor(str(ach[0]))
        return f"[done] Abri {ach[0].name}."
    if len(ach) > 1:
        return "Achei mais de um: " + " | ".join(f"{p.name} ({p.parent.name})" for p in ach[:5]) + ". Diga qual."
    if app is None:
        from actions.open_app import open_app as app_real
        app = lambda nome: app_real({"app_name": nome})
    return str(app(alvo))


def saude() -> str:
    return "ok"
