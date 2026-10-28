"""Instalador tolerante do NEXUS (2.0).

O `setup.py` instala tudo de uma vez: se UM pacote não existe para o seu Python
(ex.: o Python 3.15 ainda não tem o ctranslate2 do Whisper), o pip desiste de
TODOS e o NEXUS nem abre. Este instalador:

  1. tenta tudo de uma vez (rápido, o caso normal);
  2. se falhar, instala pacote por pacote, pula o que não der e segue;
  3. no fim diz o que ficou de fora e se o NEXUS consegue abrir.

Uso:   python instalar_pacotes.py
"""
from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent

# Sem estes o NEXUS não abre.
ESSENCIAIS = {
    "PyQt6": "PyQt6", "sounddevice": "sounddevice", "numpy": "numpy",
    "google.genai": "google-genai", "psutil": "psutil", "requests": "requests",
    "cryptography": "cryptography",
}

# Opcionais: o que cada um libera (para explicar quando faltar).
OPCIONAIS = {
    "faster-whisper": "motor de voz próprio e a palavra de ativação \"Nexus\" (o NEXUS usa o Gemini normalmente)",
    "rapidocr-onnxruntime": "OCR reserva (no Windows o NEXUS usa o OCR do próprio sistema)",
    "opencv-python": "visão local: QR code, rostos e vigia de movimento",
    "playwright": "controle do navegador",
    "pyttsx3": "voz do Windows no motor próprio",
    "yt-dlp": "vídeos do YouTube no HUD",
    "pynvml": "medidor de GPU NVIDIA",
}


def _linhas(arquivo: Path) -> list[str]:
    out = []
    for bruto in arquivo.read_text(encoding="utf-8").splitlines():
        t = bruto.split("#")[0].strip()
        if t:
            out.append(t)
    return out


def _nome(linha: str) -> str:
    """'uvicorn[standard]>=0.27,<1; marcador' -> 'uvicorn'."""
    base = linha.split(";")[0]
    for sep in ("[", ">", "<", "=", "!", "~", " "):
        base = base.split(sep)[0]
    return base.strip().lower()


def _pip(*args: str, mostrar: bool = True) -> bool:
    cmd = [sys.executable, "-m", "pip", *args]
    if mostrar:
        return subprocess.run(cmd).returncode == 0
    return subprocess.run(cmd, capture_output=True, text=True).returncode == 0


def _tem(modulo: str) -> bool:
    try:
        return importlib.util.find_spec(modulo) is not None
    except (ImportError, ValueError):
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--req", default=str(AQUI / "requirements.txt"))
    ap.add_argument("--essenciais", default="", help="(teste) módulo=pacote,… no lugar da lista padrão")
    a = ap.parse_args()

    v = sys.version_info
    print(f"NEXUS — instalação tolerante · Python {v[0]}.{v[1]}.{v[2]} · {sys.executable}")
    if v[:2] < (3, 11):
        print("\nO NEXUS precisa do Python 3.11 ou mais novo. Instale o Python 3.13 em python.org.")
        return 1
    if v[:2] > (3, 13):
        print(f"\nAviso: o Python {v[0]}.{v[1]} é mais novo que o 3.13 em que o NEXUS foi testado. "
              "Alguns pacotes opcionais podem não existir para ele; vou instalar o que for possível.")

    essenciais = ESSENCIAIS
    if a.essenciais:
        essenciais = dict(p.split("=") for p in a.essenciais.split(",") if p)

    req = Path(a.req)
    linhas = _linhas(req)
    print(f"\n[1/3] Instalando os {len(linhas)} pacotes de uma vez…\n")
    _pip("install", "--upgrade", "pip", mostrar=False)
    ok_tudo = _pip("install", "-r", str(req))

    falharam: list[str] = []
    if not ok_tudo:
        print("\n[2/3] Não deu de uma vez. Instalando um por um e pulando o que não existe "
              "para este Python…\n")
        for i, linha in enumerate(linhas, 1):
            nome = _nome(linha)
            print(f"  ({i}/{len(linhas)}) {nome} … ", end="", flush=True)
            if _pip("install", linha, mostrar=False):
                print("ok")
            else:
                print("NÃO INSTALOU")
                falharam.append(nome)
    else:
        print("\n[2/3] Tudo instalado de uma vez.")

    print("\n[3/3] Conferindo o essencial…")
    faltam = [pac for mod, pac in essenciais.items() if not _tem(mod)]

    print("\n" + "=" * 62)
    if falharam:
        print("Ficaram de fora (não existem para este Python ou deram erro):")
        for n in falharam:
            print(f"  - {n}" + (f"  →  sem isso: {OPCIONAIS[n]}" if n in OPCIONAIS else ""))
        print("Para ter tudo, instale o Python 3.13 e rode este instalador com ele.\n")
    if faltam:
        print("FALTA O ESSENCIAL, o NEXUS ainda não abre: " + ", ".join(faltam))
        print("Mande esta janela inteira (texto) para quem cuida do NEXUS.")
        print("=" * 62)
        return 1
    print("O NEXUS consegue abrir. Use o \"Abrir NEXUS (mostra erros).bat\".")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
