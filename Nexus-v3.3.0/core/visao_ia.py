"""Visão local com IA — NEXUS Ultra 2026 2.3: objetos e rostos, 100% no seu PC.

  • Objetos / pessoas: YOLOX (80 classes comuns: pessoa, celular, copo, cadeira, cachorro…).
  • Rostos: YuNet (acha o rosto) + SFace (transforma o rosto em 128 números). Reconhecer = comparar esses
    números com os que você cadastrou. A FOTO NÃO É GUARDADA — só os 128 números, em memory/rostos.npz.

Os modelos (OpenCV Zoo, licença livre) são baixados UMA vez para memory/modelos/ quando você pedir
("instala a visão de rostos"): ~0,2 MB (YuNet), ~39 MB (SFace) e ~36 MB (YOLOX). Sem eles, só dá para
contar rostos com o detector Haar que já vem no OpenCV (menos preciso; sem reconhecimento).

Cadastre só pessoas que concordaram. Reconhecimento facial erra (luz ruim, ângulo, gêmeos) e não deve
ser usado para decidir nada importante — por isso nenhuma ação sensível depende dele.
"""
from __future__ import annotations

import threading
import urllib.request
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent.parent
PASTA_MODELOS = BASE / "memory" / "modelos"
ARQ_ROSTOS = BASE / "memory" / "rostos.npz"
_ZOO = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
MODELOS = {
    "yunet": (_ZOO + "face_detection_yunet/face_detection_yunet_2023mar.onnx", "yunet.onnx", 100_000),
    "sface": (_ZOO + "face_recognition_sface/face_recognition_sface_2021dec.onnx", "sface.onnx", 30_000_000),
    "yolox": (_ZOO + "object_detection_yolox/object_detection_yolox_2022nov.onnx", "yolox.onnx", 30_000_000),
}
LIMIAR_ROSTO = 0.363            # limiar de cosseno recomendado para o SFace
MAX_VETORES_POR_PESSOA = 12
_trava = threading.Lock()
_cache: dict = {}

CLASSES_PT = [
    "pessoa", "bicicleta", "carro", "moto", "avião", "ônibus", "trem", "caminhão", "barco", "semáforo",
    "hidrante", "placa de pare", "parquímetro", "banco", "pássaro", "gato", "cachorro", "cavalo", "ovelha", "vaca",
    "elefante", "urso", "zebra", "girafa", "mochila", "guarda-chuva", "bolsa", "gravata", "mala", "frisbee",
    "esquis", "snowboard", "bola", "pipa", "taco de beisebol", "luva de beisebol", "skate", "prancha de surfe",
    "raquete de tênis", "garrafa", "taça de vinho", "copo", "garfo", "faca", "colher", "tigela", "banana", "maçã",
    "sanduíche", "laranja", "brócolis", "cenoura", "cachorro-quente", "pizza", "rosquinha", "bolo", "cadeira", "sofá",
    "planta", "cama", "mesa de jantar", "vaso sanitário", "televisão", "notebook", "mouse", "controle remoto",
    "teclado", "celular", "micro-ondas", "forno", "torradeira", "pia", "geladeira", "livro", "relógio", "vaso",
    "tesoura", "ursinho de pelúcia", "secador de cabelo", "escova de dentes"]


class VisaoIndisponivel(RuntimeError):
    pass


# ── modelos ──────────────────────────────────────────────────────────────────
def caminho(nome: str) -> Path:
    return PASTA_MODELOS / MODELOS[nome][1]


def instalado(nome: str) -> bool:
    try:
        return caminho(nome).stat().st_size >= MODELOS[nome][2]
    except OSError:
        return False


def baixar(nome: str, log=print) -> tuple[bool, str]:
    if nome not in MODELOS:
        return False, f"Modelo desconhecido: {nome}"
    if instalado(nome):
        return True, "já instalado"
    url, arq, minimo = MODELOS[nome]
    PASTA_MODELOS.mkdir(parents=True, exist_ok=True)
    tmp = PASTA_MODELOS / (arq + ".part")
    try:
        log(f"[VisãoIA] baixando {nome}…")
        with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
        if tmp.stat().st_size < minimo:
            tmp.unlink(missing_ok=True)
            return False, "o download veio incompleto"
        tmp.replace(PASTA_MODELOS / arq)
        _cache.clear()
        return True, "instalado"
    except Exception as e:
        tmp.unlink(missing_ok=True)
        return False, f"não consegui baixar: {e}"


def situacao() -> dict:
    return {n: instalado(n) for n in MODELOS}


def _cv2():
    try:
        import cv2
        return cv2
    except ImportError:
        raise VisaoIndisponivel("Falta o OpenCV: pip install opencv-python")


def para_bgr(img) -> np.ndarray:
    """Imagem PIL/RGB ou array → BGR uint8."""
    cv2 = _cv2()
    a = np.asarray(img)
    if a.ndim == 2:
        return cv2.cvtColor(a, cv2.COLOR_GRAY2BGR)
    return cv2.cvtColor(a[..., :3].astype(np.uint8), cv2.COLOR_RGB2BGR) if not isinstance(img, np.ndarray) \
        else a[..., :3].astype(np.uint8)


# ── rostos ───────────────────────────────────────────────────────────────────
def _detector_yunet(w: int, h: int):
    cv2 = _cv2()
    with _trava:
        if "yunet" not in _cache:
            _cache["yunet"] = cv2.FaceDetectorYN.create(str(caminho("yunet")), "", (w, h), 0.8, 0.3, 500)
        d = _cache["yunet"]
        d.setInputSize((w, h))
        return d


def detectar_rostos(bgr: np.ndarray) -> list[np.ndarray]:
    """Lista de linhas do YuNet (x,y,w,h, 10 pontos, nota). Cai no Haar (só caixa) se faltar o YuNet."""
    cv2 = _cv2()
    h, w = bgr.shape[:2]
    escala = 1.0
    if max(h, w) > 1280:                                          # imagens enormes: reduz para ficar rápido
        escala = 1280 / max(h, w)
        bgr = cv2.resize(bgr, (int(w * escala), int(h * escala)))
        h, w = bgr.shape[:2]
    if instalado("yunet"):
        _, faces = _detector_yunet(w, h).detect(bgr)
        saida = [] if faces is None else [f.copy() for f in faces]
        for f in saida:
            f[:14] /= escala
        return saida
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    caixas = casc.detectMultiScale(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), 1.1, 6, minSize=(40, 40))
    return [np.array([x / escala, y / escala, ww / escala, hh / escala] + [0] * 10 + [0.5], np.float32)
            for x, y, ww, hh in caixas]


def _reconhecedor():
    cv2 = _cv2()
    with _trava:
        if "sface" not in _cache:
            _cache["sface"] = cv2.FaceRecognizerSF.create(str(caminho("sface")), "")
        return _cache["sface"]


def vetor_do_rosto(bgr: np.ndarray, face: np.ndarray) -> np.ndarray:
    if not (instalado("sface") and instalado("yunet")):
        raise VisaoIndisponivel("Para reconhecer rostos, instale a visão de rostos (action=install).")
    rec = _reconhecedor()
    v = rec.feature(rec.alignCrop(bgr, face[:15].astype(np.float32).reshape(1, -1)[0]))
    v = np.asarray(v, np.float32).reshape(-1)
    return v / max(float(np.linalg.norm(v)), 1e-9)


def _carregar_rostos() -> dict[str, np.ndarray]:
    try:
        with np.load(ARQ_ROSTOS, allow_pickle=False) as z:
            nomes, vet = [str(n) for n in z["nomes"]], z["vetores"]
            return {n: vet[np.array([i for i, x in enumerate(nomes) if x == n])] for n in dict.fromkeys(nomes)}
    except Exception:
        return {}


def _gravar_rostos(d: dict[str, np.ndarray]) -> None:
    ARQ_ROSTOS.parent.mkdir(parents=True, exist_ok=True)
    nomes = [n for n, v in d.items() for _ in range(len(v))]
    vet = np.concatenate([v for v in d.values()]) if d else np.zeros((0, 128), np.float32)
    tmp = ARQ_ROSTOS.with_suffix(".tmp.npz")
    np.savez(tmp, nomes=np.array(nomes), vetores=vet.astype(np.float32))
    tmp.replace(ARQ_ROSTOS)


def cadastrar(nome: str, imagens: list[np.ndarray]) -> int:
    """Guarda os 'números' do maior rosto de cada imagem. Devolve quantos vetores entraram."""
    nome = nome.strip()[:40]
    novos = []
    for bgr in imagens:
        faces = detectar_rostos(bgr)
        if not faces:
            continue
        maior = max(faces, key=lambda f: f[2] * f[3])
        novos.append(vetor_do_rosto(bgr, maior))
    if not novos:
        return 0
    d = _carregar_rostos()
    atual = d.get(nome, np.zeros((0, 128), np.float32))
    d[nome] = np.concatenate([atual, np.array(novos)])[-MAX_VETORES_POR_PESSOA:]
    _gravar_rostos(d)
    return len(novos)


def esquecer(nome: str) -> bool:
    d = _carregar_rostos()
    chave = next((n for n in d if n.lower() == nome.strip().lower()), None)
    if not chave:
        return False
    d.pop(chave)
    _gravar_rostos(d)
    return True


def cadastrados() -> dict[str, int]:
    return {n: len(v) for n, v in _carregar_rostos().items()}


def reconhecer(bgr: np.ndarray) -> list[dict]:
    """[{'nome': str|None, 'chance': cosseno, 'caixa': (x,y,w,h)}] para cada rosto."""
    d = _carregar_rostos()
    out = []
    for f in detectar_rostos(bgr):
        caixa = tuple(int(x) for x in f[:4])
        if not d:
            out.append({"nome": None, "chance": 0.0, "caixa": caixa})
            continue
        v = vetor_do_rosto(bgr, f)
        melhor, nota = None, -1.0
        for n, vs in d.items():
            s = float((vs @ v).max())
            if s > nota:
                melhor, nota = n, s
        out.append({"nome": melhor if nota >= LIMIAR_ROSTO else None, "chance": nota, "caixa": caixa})
    return out


# ── objetos ──────────────────────────────────────────────────────────────────
def _yolox():
    cv2 = _cv2()
    with _trava:
        if "yolox" not in _cache:
            if not instalado("yolox"):
                raise VisaoIndisponivel("Para ver objetos, instale a visão de objetos (action=install).")
            net = cv2.dnn.readNet(str(caminho("yolox")))
            strides = [8, 16, 32]
            grids, exp = [], []
            for s in strides:
                n = 640 // s
                xv, yv = np.meshgrid(np.arange(n), np.arange(n))
                g = np.stack((xv, yv), 2).reshape(1, -1, 2)
                grids.append(g); exp.append(np.full((1, g.shape[1], 1), s))
            _cache["yolox"] = (net, np.concatenate(grids, 1), np.concatenate(exp, 1))
        return _cache["yolox"]


def detectar_objetos(bgr: np.ndarray, conf: float = 0.4, nms: float = 0.5) -> list[dict]:
    """[{'classe': 'pessoa', 'nota': 0.9, 'caixa': (x,y,w,h)}] mais confiantes primeiro."""
    cv2 = _cv2()
    net, grids, strides = _yolox()
    h, w = bgr.shape[:2]
    esc = min(640 / h, 640 / w)
    rgb = cv2.cvtColor(cv2.resize(bgr, (int(w * esc), int(h * esc))), cv2.COLOR_BGR2RGB)
    tela = np.full((640, 640, 3), 114, np.float32)
    tela[:rgb.shape[0], :rgb.shape[1]] = rgb
    net.setInput(np.transpose(tela, (2, 0, 1))[None])
    saida = net.forward(net.getUnconnectedOutLayersNames())[0][0].copy()
    saida[:, :2] = (saida[:, :2] + grids[0]) * strides[0]
    saida[:, 2:4] = np.exp(saida[:, 2:4]) * strides[0]
    caixas = np.stack([saida[:, 0] - saida[:, 2] / 2, saida[:, 1] - saida[:, 3] / 2, saida[:, 2], saida[:, 3]], 1)
    pont = saida[:, 4:5] * saida[:, 5:]
    nota, cls = pont.max(1), pont.argmax(1)
    manter = cv2.dnn.NMSBoxesBatched(caixas.tolist(), nota.tolist(), cls.tolist(), conf, nms)
    res = []
    for i in (np.array(manter).reshape(-1) if len(manter) else []):
        x, y, bw, bh = (caixas[i] / esc).tolist()
        res.append({"classe": CLASSES_PT[int(cls[i])], "nota": float(nota[i]),
                    "caixa": (int(x), int(y), int(bw), int(bh))})
    return sorted(res, key=lambda r: -r["nota"])


def resumo_objetos(objs: list[dict]) -> str:
    if not objs:
        return "não vi nenhum objeto que eu conheça"
    cont: dict[str, int] = {}
    for o in objs:
        cont[o["classe"]] = cont.get(o["classe"], 0) + 1
    return ", ".join(f"{c} (x{n})" if n != 1 else c for c, n in sorted(cont.items(), key=lambda kv: -kv[1]))
