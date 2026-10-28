"""OCR local (3.7) — lê fotos de recibos e PDFs escaneados para a memória de documentos.

Usa o Tesseract instalado no PC (https://github.com/UB-Mannheim/tesseract/wiki) com `pytesseract`; nada vai para a
internet. Se faltar qualquer peça, `disponivel()` diz o que falta e o resto do NEXUS segue normal.
Ligar/desligar é opt-in (memory/rag_config.json) porque OCR é lento.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
ARQ_CONFIG = _BASE / "memory" / "rag_config.json"
IMAGENS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
MAX_PAGINAS = 40
ESCALA_PDF = 2.0                 # ~144 dpi: bom equilíbrio entre leitura e tempo
_WIN = (r"C:\Program Files\Tesseract-OCR\tesseract.exe", r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe")


def _config(arq: Path | None = None) -> dict:
    try:
        return json.loads(Path(arq or ARQ_CONFIG).read_text(encoding="utf-8"))
    except Exception:
        return {}


def ativo(arq: Path | None = None) -> bool:
    return bool(_config(arq).get("ocr"))


def definir_ativo(valor: bool, arq: Path | None = None) -> None:
    arq = Path(arq or ARQ_CONFIG)
    cfg = _config(arq)
    cfg["ocr"] = bool(valor)
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(cfg), encoding="utf-8")


def _binario() -> str | None:
    achou = shutil.which("tesseract")
    if achou:
        return achou
    return next((p for p in _WIN if os.path.isfile(p)), None)


def faltando() -> str:
    """'' se tudo pronto; senão, o que instalar."""
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return "instale os pacotes: pip install pytesseract pillow"
    if not _binario():
        return "instale o Tesseract OCR (no Windows: https://github.com/UB-Mannheim/tesseract/wiki, marque o português)"
    return ""


def disponivel() -> bool:
    return not faltando()


def _idiomas() -> str:
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = _binario() or "tesseract"
        langs = set(pytesseract.get_languages(config=""))
    except Exception:
        return "eng"
    quer = [l for l in ("por", "eng") if l in langs]
    return "+".join(quer) or (sorted(langs - {"osd"})[0] if langs - {"osd"} else "eng")


def _ocr(img) -> str:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = _binario() or "tesseract"
    return pytesseract.image_to_string(img.convert("L"), lang=_idiomas(), timeout=60).strip()


def ler_imagem(path: Path) -> list[tuple[str, str]]:
    from PIL import Image
    with Image.open(path) as img:
        img.load()
        if max(img.size) > 4200:
            img.thumbnail((4200, 4200))
        txt = _ocr(img)
    return [("foto", txt)] if txt else []


def ler_pdf_escaneado(path: Path, paginas_com_texto: dict[int, str] | None = None) -> list[tuple[str, str]]:
    """OCR nas páginas do PDF que não têm texto digital. `paginas_com_texto` {n: texto} mantém as que já têm."""
    import pypdfium2 as pdfium
    ja = paginas_com_texto or {}
    saida: list[tuple[str, str]] = []
    pdf = pdfium.PdfDocument(str(path))
    try:
        for i in range(min(len(pdf), MAX_PAGINAS)):
            n = i + 1
            if ja.get(n, "").strip():
                saida.append((f"p. {n}", ja[n]))
                continue
            img = pdf[i].render(scale=ESCALA_PDF).to_pil()
            txt = _ocr(img)
            if txt:
                saida.append((f"p. {n} (OCR)", txt))
    finally:
        pdf.close()
    return saida
