"""Visão local (NEXUS Pro 1.4) — ler o texto e descrever imagens SEM internet.

Tudo aqui roda no seu computador; a imagem não sai dele.

  LER TEXTO (OCR)
    1º  OCR do próprio Windows (Windows 10/11) — rápido, entende acentos e
        português. Precisa do pacote de idioma de OCR (já vem com o Windows em
        português). Pacotes Python: winrt-Windows.Media.Ocr e companhia
        (estão no requirements.txt).
    2º  RapidOCR (pip install rapidocr-onnxruntime) — funciona em qualquer
        sistema; os modelos vêm dentro do pacote. Lê bem números, códigos e
        palavras, mas pode perder acentos.

  DESCREVER IMAGEM
    Um modelo de visão rodando no Ollama (https://ollama.com), no próprio PC:
        ollama pull gemma3:4b        (recomendado: descreve em português)
        ollama pull moondream        (mais leve, responde em inglês)
    O NEXUS usa o modelo escolhido em Configurações › VISÃO LOCAL, ou o
    primeiro modelo de visão que encontrar instalado.

De onde vem a imagem: "tela" (monitor principal), "janela" (a janela da frente),
"camera" (webcam) ou "arquivo" (um caminho de imagem).
"""
from __future__ import annotations

import base64
import io
import shutil
import sys
import threading
import time
from pathlib import Path

NO_WINDOWS = sys.platform.startswith("win")


class VisaoIndisponivel(RuntimeError):
    """Falta algo para rodar (Ollama, modelo, OCR). A mensagem diz o que fazer."""


def _pref(chave: str, padrao=None):
    try:
        from core import preferences as P
        v = P.get(chave)
        return padrao if v in (None, "") else v
    except Exception:
        return padrao


# ═══════════════════════════════════════════════════════════════════════════
#  Captura
# ═══════════════════════════════════════════════════════════════════════════

def _janela_da_frente() -> tuple[int, int, int, int] | None:
    """(esquerda, topo, largura, altura) da janela da frente — Windows.
    None se for a janela do próprio NEXUS (aí vale a tela inteira)."""
    if not NO_WINDOWS:
        return None
    import ctypes
    import os
    from ctypes import wintypes
    u = ctypes.windll.user32
    hwnd = u.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == os.getpid():
        return None
    r = wintypes.RECT()
    try:   # sem a sombra invisível da janela
        ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r), ctypes.sizeof(r))
    except Exception:
        u.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    if w < 40 or h < 40:
        return None
    return r.left, r.top, w, h


def capturar(origem: str = "tela", caminho: str = ""):
    """Devolve (imagem PIL em RGB, descrição da origem)."""
    from PIL import Image
    origem = (origem or "tela").lower()
    if origem in ("arquivo", "file"):
        p = Path(str(caminho or "")).expanduser()
        if not p.is_file():
            raise VisaoIndisponivel(f"Não achei a imagem '{caminho}'.")
        return Image.open(p).convert("RGB"), p.name
    if origem in ("camera", "câmera", "webcam"):
        try:
            import cv2
        except Exception:
            raise VisaoIndisponivel("A câmera precisa do OpenCV: pip install opencv-python")
        # 2.4.2 — a mesma abertura robusta da visão do Gemini (dois drivers, aquecimento,
        # quadro da vigia se ela estiver com a câmera)
        from actions.computer_vision import VisaoErro, capturar_camera
        try:
            frame = capturar_camera()
        except VisaoErro as e:
            raise VisaoIndisponivel(f"Não consegui usar a câmera: {e}.")
        return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)), "câmera"
    try:
        import mss
    except Exception:
        raise VisaoIndisponivel("A captura de tela precisa do mss: pip install mss")
    with mss.mss() as sct:
        alvo = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        nome = "tela"
        if origem in ("janela", "window"):
            ret = _janela_da_frente()
            if ret:
                alvo = {"left": ret[0], "top": ret[1], "width": ret[2], "height": ret[3]}
                nome = "janela da frente"
        shot = sct.grab(alvo)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    return img, nome


# ═══════════════════════════════════════════════════════════════════════════
#  OCR
# ═══════════════════════════════════════════════════════════════════════════

_rapid = None
_rapid_trava = threading.Lock()


def _tem_ocr_windows() -> bool:
    if not NO_WINDOWS:
        return False
    try:
        import winrt.windows.media.ocr  # noqa: F401
        return True
    except Exception:
        return False


def _tem_rapidocr() -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec("rapidocr_onnxruntime") is not None
    except Exception:
        return False


def motores_ocr() -> list[str]:
    out = []
    if _tem_ocr_windows():
        out.append("windows")
    if _tem_rapidocr():
        out.append("rapidocr")
    return out


async def _aguardar(op):
    return await op


def _ocr_windows(img, idioma: str) -> tuple[list[str], str]:
    import asyncio
    from winrt.windows.globalization import Language
    from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter

    motor, usado = None, ""
    for codigo in dict.fromkeys([idioma, "pt-BR", "pt-PT", "en-US"]):
        try:
            if codigo and OcrEngine.is_language_supported(Language(codigo)):
                motor = OcrEngine.try_create_from_language(Language(codigo))
                if motor is not None:
                    usado = codigo
                    break
        except Exception:
            continue
    if motor is None:
        motor = OcrEngine.try_create_from_user_profile_languages()
        usado = "idioma do Windows"
    if motor is None:
        raise VisaoIndisponivel(
            "O OCR do Windows não tem nenhum idioma instalado. No PowerShell (administrador): "
            'Add-WindowsCapability -Online -Name "Language.OCR~~~pt-BR~0.0.1.0"')

    # texto pequeno de tela lê melhor ampliado (até o limite do motor)
    try:
        limite = int(OcrEngine.max_image_dimension)
    except Exception:
        limite = 4096
    if max(img.size) * 2 <= limite and img.width < 2200:
        from PIL import Image
        img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
    elif max(img.size) > limite:
        img = img.copy()
        img.thumbnail((limite, limite))
    rgba = img.convert("RGBA")
    escritor = DataWriter()
    escritor.write_bytes(rgba.tobytes())
    bitmap = SoftwareBitmap.create_copy_from_buffer(
        escritor.detach_buffer(), BitmapPixelFormat.RGBA8, rgba.width, rgba.height)
    resultado = asyncio.run(_aguardar(motor.recognize_async(bitmap)))
    linhas = [str(l.text) for l in resultado.lines]
    return linhas, f"OCR do Windows ({usado})"


def _ordenar_linhas(itens: list[tuple[list, str]]) -> list[str]:
    """Caixas do RapidOCR → linhas na ordem de leitura (cima→baixo, esq.→dir.)."""
    caixas = []
    for box, texto in itens:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        caixas.append(((min(ys) + max(ys)) / 2, min(xs), max(ys) - min(ys), texto))
    caixas.sort(key=lambda c: (c[0], c[1]))
    linhas: list[list] = []
    for cy, x, h, texto in caixas:
        if linhas and abs(cy - linhas[-1][0]) <= max(6.0, 0.5 * max(h, linhas[-1][2])):
            linhas[-1][3].append((x, texto))
        else:
            linhas.append([cy, x, h, [(x, texto)]])
    return [" ".join(t for _x, t in sorted(l[3])) for l in linhas]


def _ocr_rapid(img) -> tuple[list[str], str]:
    global _rapid
    import numpy as np
    with _rapid_trava:
        if _rapid is None:
            from rapidocr_onnxruntime import RapidOCR
            _rapid = RapidOCR()
        bgr = np.asarray(img.convert("RGB"))[:, :, ::-1].copy()
        resultado, _tempo = _rapid(bgr)
    itens = [(r[0], str(r[1])) for r in (resultado or []) if len(r) >= 2 and str(r[1]).strip()]
    return _ordenar_linhas(itens), "RapidOCR"


def ocr(img, idioma: str | None = None, motor: str | None = None) -> dict:
    """Lê o texto da imagem. {"texto", "linhas", "motor", "ms"}."""
    idioma = idioma or _pref("visao_ocr_idioma", "pt-BR")
    motor = (motor or _pref("visao_ocr_motor", "auto") or "auto").lower()
    disponiveis = motores_ocr()
    ordem = [m for m in (["windows", "rapidocr"] if motor == "auto" else [motor]) if m in disponiveis]
    if not ordem:
        if NO_WINDOWS:
            dica = ("instale os pacotes do OCR do Windows: pip install winrt-Windows.Media.Ocr "
                    "winrt-Windows.Globalization winrt-Windows.Graphics.Imaging "
                    "winrt-Windows.Storage.Streams winrt-Windows.Foundation "
                    "winrt-Windows.Foundation.Collections  (ou: pip install rapidocr-onnxruntime)")
        else:
            dica = "instale o leitor offline: pip install rapidocr-onnxruntime"
        raise VisaoIndisponivel(f"Nenhum leitor de texto offline instalado — {dica}")
    t0 = time.perf_counter()
    erros = []
    for m in ordem:
        try:
            linhas, nome = _ocr_windows(img, idioma) if m == "windows" else _ocr_rapid(img)
            linhas = [l.strip() for l in linhas if l and l.strip()]
            return {"texto": "\n".join(linhas), "linhas": linhas, "motor": nome,
                    "ms": int((time.perf_counter() - t0) * 1000)}
        except VisaoIndisponivel as e:
            erros.append(str(e))
        except Exception as e:
            erros.append(f"{m}: {e}")
    raise VisaoIndisponivel("Não consegui ler o texto: " + " | ".join(erros))


# ═══════════════════════════════════════════════════════════════════════════
#  Descrição (Ollama)
# ═══════════════════════════════════════════════════════════════════════════

# Modelos de visão conhecidos, na ordem em que o NEXUS prefere usar
_MODELOS_VISAO = ("gemma3", "qwen2.5vl", "llama3.2-vision", "minicpm-v", "llava-llama3",
                  "llava-phi3", "llava", "granite3.2-vision", "mistral-small3.1", "moondream",
                  "bakllava")
_SO_TEXTO = ("gemma3:1b", "gemma3:270m")
MODELO_SUGERIDO = "gemma3:4b"


def _url_ollama() -> str:
    try:
        from core import llm_client
        if llm_client.get_llm_provider() == "ollama":
            return llm_client.get_llm_settings()[0].rstrip("/")
    except Exception:
        pass
    return "http://localhost:11434"


def _modelos_instalados(url: str) -> list[str]:
    import requests
    r = requests.get(f"{url}/api/tags", timeout=3)
    r.raise_for_status()
    return [m.get("name", "") for m in r.json().get("models", []) if m.get("name")]


def _enxerga(url: str, nome: str) -> bool:
    base = nome.split(":")[0].lower()
    if nome.lower() in _SO_TEXTO:
        return False
    if any(base == p or base.startswith(p) for p in _MODELOS_VISAO):
        return True
    try:   # Ollama novo diz as "capabilities" do modelo
        import requests
        r = requests.post(f"{url}/api/show", json={"model": nome}, timeout=3)
        return "vision" in (r.json().get("capabilities") or [])
    except Exception:
        return False


def _ollama_no_ar(url: str) -> bool:
    try:
        _modelos_instalados(url)
        return True
    except Exception:
        pass
    if shutil.which("ollama"):
        try:
            from core.llm_client import ensure_ollama_running
            return bool(ensure_ollama_running(timeout=12))
        except Exception:
            return False
    return False


def escolher_modelo(url: str | None = None) -> str:
    url = url or _url_ollama()
    if not _ollama_no_ar(url):
        raise VisaoIndisponivel(
            "Para descrever imagens sem internet, o NEXUS usa o Ollama, que não está instalado "
            f"ou não está aberto. Instale em ollama.com e depois rode: ollama pull {MODELO_SUGERIDO}")
    instalados = _modelos_instalados(url)
    escolhido = str(_pref("visao_local_modelo", "") or "").strip()
    if escolhido:
        for nome in instalados:
            if nome == escolhido or nome.split(":")[0] == escolhido or nome == f"{escolhido}:latest":
                return nome
        raise VisaoIndisponivel(
            f"O modelo '{escolhido}' (Configurações › VISÃO LOCAL) não está instalado no Ollama. "
            f"Rode: ollama pull {escolhido}")
    candidatos = [n for n in instalados if _enxerga(url, n)]
    if not candidatos:
        raise VisaoIndisponivel(
            "O Ollama está funcionando, mas nenhum modelo instalado enxerga imagens. "
            f"Rode: ollama pull {MODELO_SUGERIDO}  (ou: ollama pull moondream, mais leve)")

    def _ordem(n: str) -> int:
        base = n.split(":")[0].lower()
        for i, p in enumerate(_MODELOS_VISAO):
            if base.startswith(p):
                return i
        return len(_MODELOS_VISAO)
    return sorted(candidatos, key=_ordem)[0]


def descrever(img, pergunta: str = "", modelo: str | None = None) -> dict:
    """Descreve a imagem com um modelo de visão local. {"texto", "modelo", "ms"}."""
    import requests
    url = _url_ollama()
    modelo = modelo or escolher_modelo(url)
    copia = img.copy()
    copia.thumbnail((1280, 1280))
    buf = io.BytesIO()
    copia.convert("RGB").save(buf, format="JPEG", quality=85)
    pedido = (pergunta or "").strip()
    prompt = ("Descreva esta imagem em português do Brasil, de forma objetiva, em no máximo "
              "5 frases: o que aparece, textos importantes e o que a pessoa provavelmente está "
              "fazendo.") if not pedido else (
              f"Olhe a imagem e responda em português do Brasil, de forma objetiva: {pedido}")
    t0 = time.perf_counter()
    try:
        r = requests.post(f"{url}/api/generate", json={
            "model": modelo, "prompt": prompt, "stream": False,
            "images": [base64.b64encode(buf.getvalue()).decode("ascii")],
            "keep_alive": "10m",
            "options": {"temperature": 0.2, "num_predict": 400},
        }, timeout=(5, 240))
    except requests.exceptions.Timeout:
        raise VisaoIndisponivel(f"O modelo {modelo} demorou demais para responder (o PC está lento?).")
    except Exception as e:
        raise VisaoIndisponivel(f"Não consegui falar com o Ollama: {e}")
    if r.status_code != 200:
        try:
            erro = r.json().get("error", r.text)
        except Exception:
            erro = r.text
        raise VisaoIndisponivel(f"O Ollama recusou ({modelo}): {str(erro)[:200]}")
    texto = str(r.json().get("response", "")).strip()
    if not texto:
        raise VisaoIndisponivel(f"O modelo {modelo} não devolveu nenhuma descrição.")
    return {"texto": texto, "modelo": modelo, "ms": int((time.perf_counter() - t0) * 1000)}


# ═══════════════════════════════════════════════════════════════════════════
#  Situação
# ═══════════════════════════════════════════════════════════════════════════

def situacao() -> dict:
    """O que está pronto para usar (painel, I.S.A., ferramenta status)."""
    out = {"ocr": motores_ocr(), "ollama": False, "modelo": "", "aviso": ""}
    url = _url_ollama()
    try:
        _modelos_instalados(url)
        out["ollama"] = True
        out["modelo"] = escolher_modelo(url)
    except VisaoIndisponivel as e:
        out["aviso"] = str(e)
    except Exception:
        out["aviso"] = (f"Ollama não encontrado em {url}. Para descrever imagens offline: "
                        f"instale em ollama.com e rode: ollama pull {MODELO_SUGERIDO}")
    return out
