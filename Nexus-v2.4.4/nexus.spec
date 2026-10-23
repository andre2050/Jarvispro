# -*- mode: python ; coding: utf-8 -*-
# Receita do Nexus.exe (NEXUS Pro — André Luiz Lima Menezes).
#
# Não precisa abrir este arquivo: dê dois cliques em gerar_exe.bat.
# (Ou, no terminal, dentro da pasta do Nexus:  python -m PyInstaller nexus.spec --noconfirm)
#
# O .exe leva o Python e as bibliotecas; o código do NEXUS fica nos .py ao lado
# dele (veja nexus_exe.py). Para o PyInstaller saber QUAIS bibliotecas levar,
# esta receita lê todos os "import" do projeto e inclui cada um que estiver
# instalado — então um plugin novo com uma biblioteca nova só precisa de um
# gerar_exe.bat de novo.

import ast
import importlib.util
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

PASTA = Path(SPECPATH)
IGNORAR_PASTAS = {"build", "dist", "_internal", ".venv", "venv", "env", "__pycache__",
                  "updates", "backups", ".git"}

# Nomes que são do próprio NEXUS: nunca entram no .exe (ficam como .py ao lado dele)
LOCAIS = {p.name for p in PASTA.iterdir() if p.is_dir() and (p / "__init__.py").exists()}
LOCAIS |= {p.stem for p in PASTA.glob("*.py")}
LOCAIS |= {"plugins", "actions", "core", "memory", "ui", "assistant", "dashboard", "config"}


def _arquivos():
    for f in PASTA.rglob("*.py"):
        if IGNORAR_PASTAS & set(f.relative_to(PASTA).parts):
            continue
        yield f


def _imports_do_projeto() -> set[str]:
    nomes: set[str] = set()
    for f in _arquivos():
        try:
            arvore = ast.parse(f.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for n in ast.walk(arvore):
            if isinstance(n, ast.Import):
                nomes.update(a.name for a in n.names)
            elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                nomes.add(n.module)
    return {n for n in nomes if n.split(".")[0] not in LOCAIS}


def _existe(nome: str) -> bool:
    try:
        return importlib.util.find_spec(nome) is not None
    except Exception:
        return False


ocultos: list[str] = []
faltando: list[str] = []
for nome in sorted(_imports_do_projeto()):
    topo = nome.split(".")[0]
    if not _existe(topo):
        faltando.append(topo)
        continue
    ocultos.append(nome if _existe(nome) else topo)

# A biblioteca padrão do Python vai inteira: plugins e scripts soltos (que o
# .exe roda no papel de "python") podem usar qualquer parte dela.
_STDLIB_FORA = {"tkinter", "turtle", "turtledemo", "idlelib", "test", "lib2to3", "ensurepip",
                "pydoc_data", "venv", "msilib", "antigravity", "this", "__phello__",
                "_tkinter", "xxlimited", "xxlimited_35", "xxsubtype", "_testcapi",
                "_testinternalcapi", "_testbuffer", "_testimportmultiple", "_testmultiphase",
                "_xxtestfuzz", "_ctypes_test", "_testclinic", "_testsinglephase"}
for _nome in sorted(getattr(sys, "stdlib_module_names", ())):
    if _nome in _STDLIB_FORA or _nome.startswith("_test"):
        continue
    if _existe(_nome):
        ocultos.append(_nome)

# Bibliotecas que carregam arquivos ou módulos "por nome" e precisam ir inteiras
COMPLETAS = [
    "google.genai", "uvicorn", "faster_whisper", "ctranslate2", "openwakeword",
    "onnxruntime", "comtypes", "pywinauto", "win10toast", "pyttsx3", "ddgs",
    "duckduckgo_search", "yt_dlp", "googleapiclient", "tzdata", "pptx", "docx",
    "pdfminer", "pdfplumber", "qrcode", "playwright", "sounddevice", "certifi",
    "anthropic", "edge_tts", "mediapipe",
    # 1.4 — visão local: OCR do Windows (winrt) e RapidOCR (modelos .onnx dentro do pacote)
    "winrt", "rapidocr_onnxruntime", "shapely", "pyclipper",
]
datas, binaries = [], []
# 1.4.2 — os arquivos de detecção de rostos (cv2/data/*.xml) não vinham no .exe,
# e "contar rostos" falhava só no Nexus.exe.
if _existe("cv2"):
    try:
        from PyInstaller.utils.hooks import collect_data_files
        datas += collect_data_files("cv2", subdir="data", includes=["*.xml"])
    except Exception as e:  # pragma: no cover
        print(f"[nexus.spec] não deu para incluir as cascatas do OpenCV: {e}")
for pacote in COMPLETAS:
    if not _existe(pacote.split(".")[0]):
        continue
    try:
        d, b, h = collect_all(pacote)
    except Exception as e:  # pragma: no cover
        print(f"[nexus.spec] não deu para incluir {pacote} inteiro: {e}")
        continue
    datas += d
    binaries += b
    ocultos += h

if faltando:
    print("[nexus.spec] Não instalados (as funções que dependem deles ficam de fora):",
          ", ".join(sorted(set(faltando))))

a = Analysis(
    ["nexus_exe.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(ocultos)),
    hookspath=[],
    runtime_hooks=[],
    excludes=sorted(LOCAIS - {"nexus_exe"}) + ["tkinter.test", "test", "unittest.test"],
    noarchive=False,
)
pyz = PYZ(a.pure)

icone = PASTA / "config" / "nexus.ico"
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Nexus",
    console=False,
    icon=str(icone) if icone.exists() else None,
    version=None,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Nexus", upx=False)
