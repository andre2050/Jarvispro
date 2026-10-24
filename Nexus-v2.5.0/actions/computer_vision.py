"""Visão do computador — análise local com OpenCV (NEXUS Pro 1.4.2).

O screen_process manda a imagem para o Gemini (visão por IA). Este arquivo é a
outra visão: OpenCV rodando no próprio PC, sem internet —

  • QR code na tela ou na câmera
  • contar rostos na câmera
  • analisar a tela ou a câmera (brilho, nitidez, cores principais)
  • vigia de movimento: olha a câmera e avisa quando algo se mexe
    (aviso na conversa, notificação do Windows, som e uma foto do momento
    em Imagens\\NEXUS Vigia)

O que foi corrigido na 1.4.2 (antes "não funcionava direito"):
  - a câmera era lida no primeiro quadro, que quase sempre vem preto (a
    exposição ainda está ajustando) → rostos e QR na câmera não achavam nada.
    Agora ela "aquece" até a imagem ficar boa, e usa a câmera escolhida nas
    configurações (camera_index), não a primeira que abrisse;
  - "QR na tela" e "analisar a tela" fotografavam a própria janela do NEXUS
    (que estava na frente) → agora o NEXUS sai da frente por um instante;
  - o QR passou a tentar vários jeitos (detector Aruco, cinza, ampliado,
    preto-e-branco), cada monitor separado;
  - a cor "dominante" era a mais clara, não a que mais aparece;
  - o aviso de movimento só ia para o console (ninguém via); ligar logo
    depois de desligar podia deixar a vigia parada; a mudança de luz da
    câmera ao abrir disparava alarme falso;
  - no Nexus.exe faltava o arquivo de detecção de rostos (nexus.spec);
  - tudo em português.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

try:
    import cv2
    import numpy as np
except Exception:                     # pragma: no cover
    cv2 = None
    np = None


class VisaoErro(RuntimeError):
    """Algo impediu a captura/análise. A mensagem já é para o usuário."""


def _no_windows() -> bool:
    return sys.platform.startswith("win")


# ═══════════════════════════════════════════════════════════════════════════
#  Câmera
# ═══════════════════════════════════════════════════════════════════════════

_cam_trava = threading.Lock()
_cam_boa: dict = {}                 # {"idx": int, "backend": int} que funcionou


def _backends() -> list[int]:
    if _no_windows():
        return [cv2.CAP_DSHOW, cv2.CAP_MSMF]
    if sys.platform == "darwin":
        return [cv2.CAP_AVFOUNDATION]
    return [cv2.CAP_ANY]


def _indice_configurado() -> int | None:
    """A câmera escolhida (config/api_keys.json → camera_index)."""
    try:
        from actions.screen_processor import _load_config
        cfg = _load_config()
        if "camera_index" in cfg:
            return int(cfg["camera_index"])
    except Exception:
        pass
    return None


def _candidatos() -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    if _cam_boa:
        out.append((_cam_boa["idx"], _cam_boa["backend"]))
    conf = _indice_configurado()
    for idx in ([conf] if conf is not None else []) + [0, 1, 2, 3]:
        for be in _backends():
            if (idx, be) not in out:
                out.append((idx, be))
    return out


_NOMES_DE_APP = {"whatsapp": "WhatsApp", "msteams": "Teams", "teams": "Teams", "zoom": "Zoom",
                 "skype": "Skype", "discord": "Discord", "camerahd": "Camera HD", "windowscamera": "Câmera do Windows",
                 "chrome": "Google Chrome", "msedge": "Microsoft Edge", "firefox": "Firefox", "obs64": "OBS",
                 "obs32": "OBS", "telegram": "Telegram", "meet": "Google Meet"}


def _nome_amigavel(chave: str) -> str:
    """'5319275A.WhatsAppDesktop_cv1g…' → 'WhatsApp'; 'C:#…#zoom.exe' → 'Zoom'."""
    import re
    if "#" in chave:                                   # app comum: caminho com # no lugar de \
        base = chave.rsplit("#", 1)[-1]
        base = re.sub(r"\.exe$", "", base, flags=re.I)
    else:                                              # app da Store: Editor.NomeDoApp_hash
        base = chave.split("_", 1)[0].split(".")[-1]
    chave_n = re.sub(r"[^a-z0-9]", "", base.lower())
    for k, nome in _NOMES_DE_APP.items():
        if k in chave_n:
            return nome
    return base


def quem_usa_camera() -> list[str]:
    """Programas que estão com a câmera agora (Windows). 2.4.3 — no Windows só um
    programa usa a webcam por vez; antes o NEXUS dizia só "não achei nenhuma câmera"
    quando era o WhatsApp que estava com ela. O próprio Windows anota quem está usando
    (Configurações › Privacidade › Câmera): início marcado e fim zerado = em uso."""
    if not _no_windows():
        return []
    try:
        import winreg
    except ImportError:
        return []
    raiz = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam"
    meu_exe = os.path.normcase(os.path.abspath(sys.executable))
    achados: list[str] = []

    def _varrer(caminho: str) -> None:
        try:
            chave = winreg.OpenKey(winreg.HKEY_CURRENT_USER, caminho)
        except OSError:
            return
        with chave:
            i = 0
            while True:
                try:
                    nome = winreg.EnumKey(chave, i)
                except OSError:
                    break
                i += 1
                if nome == "NonPackaged":
                    continue
                try:
                    with winreg.OpenKey(chave, nome) as sub:
                        inicio = winreg.QueryValueEx(sub, "LastUsedTimeStart")[0]
                        fim = winreg.QueryValueEx(sub, "LastUsedTimeStop")[0]
                except OSError:
                    continue
                if not inicio or fim:
                    continue
                if os.path.normcase(nome.replace("#", "\\")) == meu_exe:
                    continue                           # o próprio NEXUS (a vigia, a prévia)
                amigavel = _nome_amigavel(nome)
                if amigavel not in achados:
                    achados.append(amigavel)

    _varrer(raiz)
    _varrer(raiz + r"\NonPackaged")
    return achados


# Programas que costumam pegar a câmera: nome do processo → nome para o usuário.
# Plano B de quem_usa_camera(): nem todo app aparece no registro do Windows (o Camera
# HD, por exemplo, segura a câmera sem anotar nada lá).
_PROCESSOS_DE_CAMERA = {"whatsapp": "WhatsApp", "ms-teams": "Teams", "teams": "Teams", "zoom": "Zoom",
                        "skype": "Skype", "discord": "Discord", "webcamrecorderclient": "Camera HD",
                        "windowscamera": "Câmera do Windows", "obs64": "OBS", "obs32": "OBS",
                        "telegram": "Telegram"}


def _apps_de_camera_abertos() -> list[str]:
    try:
        import psutil
    except ImportError:
        return []
    abertos: list[str] = []
    for p in psutil.process_iter(["name"]):
        nome = (p.info.get("name") or "").lower().removesuffix(".exe")
        amigavel = _PROCESSOS_DE_CAMERA.get(nome)
        if amigavel and amigavel not in abertos:
            abertos.append(amigavel)
    return abertos


def _msg_sem_camera() -> str:
    try:
        quem = quem_usa_camera()
    except Exception:
        quem = []
    if quem:
        nomes = " e ".join(quem)
        return (f"a câmera está sendo usada pelo {nomes} — no Windows só um programa usa a câmera por vez. "
                f"Feche a câmera (ou a chamada) no {nomes} e peça de novo")
    try:
        talvez = _apps_de_camera_abertos()
    except Exception:
        talvez = []
    if talvez:
        nomes = ", ".join(talvez)
        return (f"a câmera não abriu — provavelmente outro programa está com ela (no Windows só um usa por vez). "
                f"Abertos agora e que costumam usar a câmera: {nomes}. Feche a câmera ou a chamada neles "
                "e peça de novo")
    return ("não achei nenhuma câmera funcionando (ela está ligada? outro programa, como Teams ou Zoom, "
            "está usando?)")


def abrir_camera(largura: int = 1280, altura: int = 720):
    """Abre a câmera (a escolhida primeiro) e devolve o VideoCapture aberto."""
    if cv2 is None:
        raise VisaoErro("o OpenCV não está instalado — pip install opencv-python")
    with _cam_trava:
        for idx, be in _candidatos():
            try:
                cap = cv2.VideoCapture(idx, be)
            except Exception:
                continue
            if not cap.isOpened():
                cap.release()
                continue
            try:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, largura)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, altura)
            except Exception:
                pass
            ok, quadro = cap.read()
            if ok and quadro is not None:
                _cam_boa.update(idx=idx, backend=be)
                return cap
            cap.release()
    raise VisaoErro(_msg_sem_camera())


def _aquecer(cap, segundos: float = 1.6):
    """Lê quadros até a imagem ficar boa — o primeiro costuma vir preto."""
    melhor, fim = None, time.time() + segundos
    lidos = 0
    while time.time() < fim:
        ok, q = cap.read()
        if not ok or q is None:
            time.sleep(0.03)
            continue
        lidos += 1
        melhor = q
        if lidos >= 6 and float(q.mean()) > 18:
            break
    return melhor


def capturar_camera():
    """Um quadro bom da câmera (BGR). Se a vigia está ligada, usa a câmera dela."""
    if cv2 is None:
        raise VisaoErro("o OpenCV não está instalado — pip install opencv-python")
    q = _vigia.quadro_recente()
    if q is not None:
        return q
    cap = abrir_camera()
    try:
        quadro = _aquecer(cap)
    finally:
        cap.release()
    if quadro is None:
        raise VisaoErro("a câmera abriu, mas não mandou imagem")
    return quadro


# ═══════════════════════════════════════════════════════════════════════════
#  Tela
# ═══════════════════════════════════════════════════════════════════════════

def _nexus_na_frente() -> bool:
    """A janela da frente é do próprio NEXUS? (só dá para saber no Windows)"""
    if not _no_windows():
        return False
    try:
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(u.GetForegroundWindow(), ctypes.byref(pid))
        return pid.value == os.getpid()
    except Exception:
        return False


def capturar_telas(ocultar=None, forcar: bool = False) -> list:
    """Uma imagem (BGR) por monitor. `ocultar(True/False)` tira o NEXUS da
    frente durante a foto — para não fotografar a própria janela."""
    if cv2 is None:
        raise VisaoErro("o OpenCV não está instalado — pip install opencv-python")
    try:
        import mss
    except Exception:
        raise VisaoErro("a captura de tela precisa do mss — pip install mss")
    esconder = bool(ocultar) and (forcar or _nexus_na_frente())
    if esconder:
        try:
            ocultar(True)
        except Exception:
            esconder = False
        time.sleep(0.65)             # tempo de a janela sair da frente
    try:
        with mss.mss() as sct:
            mons = sct.monitors[1:] or sct.monitors[:1]
            telas = [np.asarray(sct.grab(m))[:, :, :3].copy() for m in mons]
    except Exception as e:
        raise VisaoErro(f"não consegui fotografar a tela ({e})")
    finally:
        if esconder:
            try:
                ocultar(False)
            except Exception:
                pass
    return telas


# ═══════════════════════════════════════════════════════════════════════════
#  QR code
# ═══════════════════════════════════════════════════════════════════════════

def _detectores():
    out = []
    if hasattr(cv2, "QRCodeDetectorAruco"):
        try:
            out.append(cv2.QRCodeDetectorAruco())
        except Exception:
            pass
    out.append(cv2.QRCodeDetector())
    return out


def _variantes(frame):
    """(imagem, escala) para tentar — do mais rápido ao mais caro."""
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    yield frame, 1.0
    yield gray, 1.0
    if max(h, w) > 2400:                       # telas 4K / várias telas
        f = 2000 / max(h, w)
        yield cv2.resize(gray, (int(w * f), int(h * f)), interpolation=cv2.INTER_AREA), f
    if max(h, w) < 1700:                       # QR pequeno: ampliar ajuda
        yield cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC), 2.0
    _t, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    yield bw, 1.0


def ler_qr(frame) -> list[dict]:
    """QR codes da imagem: [{"texto", "pontos"}] (pontos na escala original)."""
    achados: dict[str, object] = {}
    for img, escala in _variantes(frame):
        for det in _detectores():
            try:
                ok, textos, pontos, _r = det.detectAndDecodeMulti(img)
            except Exception:
                ok, textos, pontos = False, (), None
            if ok and textos:
                for i, t in enumerate(textos):
                    if t and t not in achados:
                        p = None if pontos is None else (np.asarray(pontos[i]) / escala)
                        achados[t] = p
            if not achados:
                try:
                    t, pts, _r = det.detectAndDecode(img)
                    if t:
                        achados[t] = None if pts is None else (np.asarray(pts).reshape(-1, 2) / escala)
                except Exception:
                    pass
            if achados:
                return [{"texto": t, "pontos": p} for t, p in achados.items()]
    return []


# ═══════════════════════════════════════════════════════════════════════════
#  Rostos
# ═══════════════════════════════════════════════════════════════════════════

_cascatas: dict = {}


def _pasta_cascatas() -> Path:
    if not hasattr(cv2, "CascadeClassifier"):
        raise VisaoErro("contar rostos precisa do OpenCV 4 — pip install \"opencv-python>=4.8,<5\"")
    lugares = []
    try:
        lugares.append(Path(cv2.data.haarcascades))
    except Exception:
        pass
    base = getattr(sys, "_MEIPASS", None)          # dentro do Nexus.exe
    if base:
        lugares.append(Path(base) / "cv2" / "data")
    lugares.append(Path(__file__).resolve().parent.parent / "config" / "cascatas")
    for p in lugares:
        if (p / "haarcascade_frontalface_default.xml").is_file():
            return p
    raise VisaoErro("o arquivo de detecção de rostos do OpenCV não foi encontrado"
                    + (" — gere o Nexus.exe de novo (gerar_exe.bat)" if base else
                       " — reinstale: pip install --force-reinstall opencv-python"))


def _cascata(nome: str):
    if nome not in _cascatas:
        c = cv2.CascadeClassifier(str(_pasta_cascatas() / nome))
        if c.empty():
            raise VisaoErro(f"o arquivo {nome} do OpenCV está corrompido")
        _cascatas[nome] = c
    return _cascatas[nome]


def _sobrepoe(a, b) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    return inter > 0.35 * min(aw * ah, bw * bh)


def achar_rostos(frame) -> list[tuple[int, int, int, int]]:
    """Rostos (x, y, w, h): de frente e, se não achar, de perfil."""
    h, w = frame.shape[:2]
    f = 960 / w if w > 960 else 1.0
    img = cv2.resize(frame, (int(w * f), int(h * f))) if f != 1.0 else frame
    gray = cv2.equalizeHist(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    lado = max(36, int(min(gray.shape[:2]) * 0.07))
    caixas: list = []
    tentativas = [("haarcascade_frontalface_default.xml", 5, False),
                  ("haarcascade_frontalface_alt2.xml", 4, False),
                  ("haarcascade_profileface.xml", 5, False),
                  ("haarcascade_profileface.xml", 5, True)]
    for nome, vizinhos, espelhar in tentativas:      # para no primeiro jeito que achar
        if caixas:
            break
        try:
            casc = _cascata(nome)
        except VisaoErro:
            if nome == "haarcascade_frontalface_default.xml":
                raise
            continue
        g = cv2.flip(gray, 1) if espelhar else gray
        achou = casc.detectMultiScale(g, scaleFactor=1.1, minNeighbors=vizinhos,
                                      minSize=(lado, lado))
        for (x, y, cw, ch) in (achou if achou is not None else []):
            if espelhar:
                x = g.shape[1] - x - cw
            nova = (int(x / f), int(y / f), int(cw / f), int(ch / f))
            if not any(_sobrepoe(nova, c) for c in caixas):
                caixas.append(nova)
    return caixas


# ═══════════════════════════════════════════════════════════════════════════
#  Análise
# ═══════════════════════════════════════════════════════════════════════════

def nome_da_cor(rgb) -> str:
    import colorsys
    r, g, b = (max(0, min(255, int(v))) / 255 for v in rgb)
    hh, ss, vv = colorsys.rgb_to_hsv(r, g, b)
    if vv < 0.12:
        return "preto"
    if ss < 0.15:
        return ("cinza-escuro" if vv < 0.4 else "cinza" if vv < 0.7
                else "cinza-claro" if vv < 0.9 else "branco")
    graus = hh * 360
    for limite, nome in ((15, "vermelho"), (40, "laranja"), (68, "amarelo"), (160, "verde"),
                         (195, "ciano"), (255, "azul"), (290, "roxo"), (335, "rosa"), (361, "vermelho")):
        if graus < limite:
            break
    if nome == "laranja" and vv < 0.55:
        return "marrom"
    if vv < 0.4:
        return f"{nome} escuro"
    if vv > 0.85 and ss < 0.45:
        return f"{nome} claro"
    return nome


def analisar(frame) -> dict:
    """Brilho, nitidez e as 3 cores que mais aparecem."""
    h, w = frame.shape[:2]
    f = 480 / w if w > 480 else 1.0
    pequeno = cv2.resize(frame, (max(1, int(w * f)), max(1, int(h * f)))) if f != 1.0 else frame
    gray = cv2.cvtColor(pequeno, cv2.COLOR_BGR2GRAY)
    brilho = float(gray.mean()) / 255.0
    nitidez = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    pix = pequeno.reshape(-1, 3).astype(np.float32)
    k = 3 if len(pix) >= 3 else 1
    _r, rotulos, centros = cv2.kmeans(
        pix, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 12, 1.0),
        3, cv2.KMEANS_PP_CENTERS)
    contagem = np.bincount(rotulos.flatten(), minlength=k)
    ordem = np.argsort(-contagem)
    cores = []
    for i in ordem:
        b, g, r = (int(x) for x in centros[i])
        cores.append({"rgb": (r, g, b), "hex": f"#{r:02x}{g:02x}{b:02x}",
                      "nome": nome_da_cor((r, g, b)),
                      "pct": int(round(100 * contagem[i] / max(1, contagem.sum())))})
    cores = [c for c in cores if c["pct"] >= 1] or cores[:1]
    return {"largura": w, "altura": h, "brilho": round(brilho, 2),
            "nitidez": round(nitidez, 1), "cores": cores}


def _txt_brilho(b: float) -> str:
    return ("muito escura" if b < 0.15 else "escura" if b < 0.35 else "boa" if b < 0.7
            else "clara" if b < 0.88 else "muito clara")


def _txt_nitidez(n: float) -> str:
    return "borrada" if n < 40 else "um pouco borrada" if n < 120 else "nítida"


# ═══════════════════════════════════════════════════════════════════════════
#  Vigia de movimento
# ═══════════════════════════════════════════════════════════════════════════

def _limiar(sensibilidade: int) -> float:
    """1..10 → fração da imagem que precisa mudar (mais sensível = menos)."""
    s = max(1, min(10, int(sensibilidade)))
    return 0.0025 * (11 - s)          # 5 → 1,5% da imagem · 10 → 0,25% · 1 → 2,5%


def _pasta_fotos() -> Path:
    try:
        from actions.file_controller import _get_pictures
        base = _get_pictures()
    except Exception:
        base = Path.home() / "Pictures"
    if not base.exists():
        base = Path.home()
    p = base / "NEXUS Vigia"
    p.mkdir(parents=True, exist_ok=True)
    return p


class _Vigia:
    PASSO = 0.25                       # 4 olhadas por segundo
    APRENDER = 2.0                     # segundos iniciais só aprendendo o fundo

    def __init__(self):
        self._trava = threading.Lock()
        self.ativo = False
        self.sensibilidade = 5
        self.intervalo = 30.0
        self.inicio = 0.0
        self.movimentos = 0
        self.ultimo_alerta = 0.0
        self.ultima_foto: Path | None = None
        self.salvar_fotos = True
        self._parar: threading.Event | None = None
        self._thread: threading.Thread | None = None
        self._quadro = None
        self._quadro_t = 0.0
        self._avisos: list = []        # funções que recebem a mensagem (conversa)

    # ── controle ────────────────────────────────────────────────────────────

    def ligar(self, sensibilidade=5, intervalo=30.0, avisar=None, salvar_fotos=True) -> str:
        with self._trava:
            if self.ativo:
                return f"A vigia já está ligada — {self.status()}."
            cap = abrir_camera(640, 480)
            parar = threading.Event()
            self.sensibilidade = max(1, min(10, int(float(sensibilidade or 5))))
            self.intervalo = max(5.0, float(intervalo or 30))
            self.inicio = time.time()
            self.movimentos = 0
            self.ultimo_alerta = 0.0
            self.ultima_foto = None
            self.salvar_fotos = bool(salvar_fotos)
            self._avisos = [a for a in ([avisar] if avisar else []) if callable(a)]
            self._parar = parar
            self.ativo = True
            # uma thread NOVA a cada vez: ligar logo depois de desligar não fica sem vigia
            self._thread = threading.Thread(target=self._laco, args=(cap, parar),
                                            daemon=True, name="nexus-vigia")
            self._thread.start()
        return (f"Vigia de movimento ligada (sensibilidade {self.sensibilidade}/10). Quando algo se "
                f"mexer na frente da câmera eu aviso"
                + (" e guardo uma foto em Imagens\\NEXUS Vigia." if self.salvar_fotos else "."))

    def desligar(self) -> str:
        with self._trava:
            if not self.ativo:
                return "A vigia de movimento não estava ligada."
            self.ativo = False
            parar, thread = self._parar, self._thread
            n, desde = self.movimentos, self.inicio
        if parar:
            parar.set()
        if thread and thread is not threading.current_thread():
            thread.join(timeout=3)
        mins = max(0, int((time.time() - desde) // 60))
        return (f"Vigia de movimento desligada — ficou {mins} min ligada e viu "
                f"{n} movimento(s).")

    def adicionar_aviso(self, fn) -> None:
        if callable(fn) and fn not in self._avisos:
            self._avisos.append(fn)

    def status(self) -> str:
        if not self.ativo:
            return "desligada"
        mins = int((time.time() - self.inicio) // 60)
        txt = (f"ligada há {mins} min · sensibilidade {self.sensibilidade}/10 · "
               f"{self.movimentos} movimento(s)")
        if self.ultimo_alerta:
            txt += f" · último às {datetime.fromtimestamp(self.ultimo_alerta):%H:%M:%S}"
        return txt

    def quadro_recente(self):
        if self.ativo and self._quadro is not None and time.time() - self._quadro_t < 2.0:
            return self._quadro.copy()
        return None

    # ── o laço ──────────────────────────────────────────────────────────────

    def _laco(self, cap, parar: threading.Event) -> None:
        fundo = None
        falhas = 0
        comeco = time.time()
        try:
            _aquecer(cap, 1.2)
            while not parar.is_set():
                ok, q = cap.read()
                if not ok or q is None:
                    falhas += 1
                    if falhas >= 20:
                        self._avisar("⚠ A vigia de movimento parou: a câmera deixou de mandar imagem.")
                        with self._trava:
                            self.ativo = False
                        return
                    parar.wait(self.PASSO)
                    continue
                falhas = 0
                self._quadro, self._quadro_t = q, time.time()
                cinza = cv2.GaussianBlur(cv2.cvtColor(cv2.resize(q, (320, 240)),
                                                      cv2.COLOR_BGR2GRAY), (21, 21), 0)
                if fundo is None:
                    fundo = cinza.astype("float32")
                    continue
                diff = cv2.absdiff(cinza, cv2.convertScaleAbs(fundo))
                _t, mascara = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
                mascara = cv2.dilate(mascara, None, iterations=2)
                fracao = float(np.count_nonzero(mascara)) / mascara.size
                aprendendo = time.time() - comeco < self.APRENDER
                if fracao > 0.65 or aprendendo:
                    # a luz mudou de uma vez (ou a câmera ainda ajustando): aprende o novo fundo
                    cv2.accumulateWeighted(cinza, fundo, 0.5)
                elif fracao >= _limiar(self.sensibilidade):
                    agora = time.time()
                    if agora - self.ultimo_alerta >= self.intervalo:
                        self.ultimo_alerta = agora
                        self.movimentos += 1
                        self._alerta(q, mascara, fracao)
                    cv2.accumulateWeighted(cinza, fundo, 0.08)
                else:
                    cv2.accumulateWeighted(cinza, fundo, 0.04)
                parar.wait(self.PASSO)
        except Exception as e:
            self._avisar(f"⚠ A vigia de movimento parou por um erro: {e}")
            with self._trava:
                self.ativo = False
        finally:
            try:
                cap.release()
            except Exception:
                pass

    def _alerta(self, quadro, mascara, fracao: float) -> None:
        hora = datetime.now()
        foto = None
        if self.salvar_fotos:
            try:
                marcado = quadro.copy()
                m = cv2.resize(mascara, (quadro.shape[1], quadro.shape[0]))
                contornos, _h = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                for c in contornos:
                    if cv2.contourArea(c) > 0.002 * m.size:
                        x, y, w, h = cv2.boundingRect(c)
                        cv2.rectangle(marcado, (x, y), (x + w, y + h), (60, 60, 255), 2)
                cv2.putText(marcado, hora.strftime("%d/%m/%Y %H:%M:%S"), (10, 24),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                foto = _pasta_fotos() / f"movimento {hora:%Y-%m-%d %H-%M-%S}.jpg"
                cv2.imwrite(str(foto), marcado)
                self.ultima_foto = foto
            except Exception as e:
                print(f"[Vigia] não salvei a foto: {e}")
                foto = None
        msg = (f"🚨 Movimento na frente da câmera às {hora:%H:%M:%S}"
               + (f" — foto salva em {foto}" if foto else "") + ".")
        self._avisar(msg)
        _som()
        _notificacao("NEXUS Pro — Vigia de movimento",
                     f"Algo se mexeu na frente da câmera às {hora:%H:%M:%S}.")
        try:
            from core import isa
            isa.registrar("sistema", "Vigia: movimento detectado",
                          f"{fracao * 100:.1f}% da imagem mudou", origem="visão")
        except Exception:
            pass

    def _avisar(self, msg: str) -> None:
        print(f"[Vigia] {msg}")
        for fn in list(self._avisos):
            try:
                fn(f"SYS: {msg}")
            except Exception:
                pass


_vigia = _Vigia()


def motion_status() -> str:
    """(compatibilidade) situação da vigia em uma linha."""
    return _vigia.status()


def _som() -> None:
    try:
        from actions.timer_action import _beep
        threading.Thread(target=_beep, daemon=True).start()
    except Exception:
        print("\a")


def _notificacao(titulo: str, texto: str) -> None:
    if not _no_windows():
        return

    def _mostrar():
        try:
            from win10toast import ToastNotifier
            ToastNotifier().show_toast(titulo, texto, duration=8, threaded=False)
        except Exception:
            pass
    threading.Thread(target=_mostrar, daemon=True).start()


# ═══════════════════════════════════════════════════════════════════════════
#  Execução (voz e painel)
# ═══════════════════════════════════════════════════════════════════════════

def _marcar_qr(frame, achados):
    out = frame.copy()
    for a in achados:
        p = a.get("pontos")
        if p is not None and len(p) >= 4:
            pts = np.asarray(p, dtype=np.int32).reshape(-1, 1, 2)
            cv2.polylines(out, [pts], True, (80, 230, 120), max(2, out.shape[1] // 400))
    return out


def _marcar_rostos(frame, caixas):
    out = frame.copy()
    esp = max(2, out.shape[1] // 320)
    for i, (x, y, w, h) in enumerate(caixas, 1):
        cv2.rectangle(out, (x, y), (x + w, y + h), (255, 180, 90), esp)
        cv2.putText(out, str(i), (x + 4, y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 180, 90), 2)
    return out


def _com_paleta(frame, cores):
    """A imagem com uma faixa das cores principais embaixo."""
    h, w = frame.shape[:2]
    faixa = max(18, h // 12)
    out = np.zeros((h + faixa, w, 3), dtype=np.uint8)
    out[:h] = frame
    x = 0
    for c in cores:
        largura = int(w * c["pct"] / 100)
        r, g, b = c["rgb"]
        out[h:, x:x + largura] = (b, g, r)
        x += largura
    if x < w and cores:
        r, g, b = cores[-1]["rgb"]
        out[h:, x:] = (b, g, r)
    return out


def executar(parametros: dict, ocultar=None, forcar_ocultar: bool = False,
             avisar=None) -> dict:
    """Roda uma ação e devolve {"msg", "imagem" (BGR marcada ou None),
    "texto" (para copiar), "link"}. Usado pela voz e pelo painel Visão."""
    if cv2 is None:
        return {"msg": "O OpenCV não está instalado neste computador — rode: pip install opencv-python",
                "imagem": None, "texto": "", "link": ""}
    acao = str(parametros.get("action") or "").strip().lower()
    angulo = str(parametros.get("angle") or "").strip().lower()
    vazio = {"imagem": None, "texto": "", "link": ""}
    try:
        if acao not in ("qr", "faces", "analyze", "motion", "stop"):
            return dict(vazio, msg=("Eu leio QR code (da tela ou da câmera), conto rostos na câmera, "
                                    "analiso a tela ou a câmera e vigio a câmera — diga, por "
                                    "exemplo, 'vigia a câmera e me avisa se mexer'."))
        if acao == "stop":
            acao, parametros = "motion", dict(parametros, op="stop")
        if acao == "motion":
            op = str(parametros.get("op") or "status").strip().lower()
            if op == "start":
                return dict(vazio, msg=_vigia.ligar(parametros.get("sensitivity", 5),
                                                    parametros.get("cooldown_seconds", 30),
                                                    avisar, parametros.get("save_photos", True) is not False))
            if op == "stop":
                return dict(vazio, msg=_vigia.desligar())
            st = _vigia.status()
            return dict(vazio, msg=f"Vigia de movimento: {st}.")

        if angulo not in ("screen", "camera"):
            angulo = "camera" if acao == "faces" else "screen"

        if angulo == "screen":
            telas = capturar_telas(ocultar, forcar_ocultar)
            onde = "tela"
        else:
            telas = [capturar_camera()]
            onde = "câmera"

        if acao == "qr":
            todos, imagem = [], None
            for t in telas:
                achou = ler_qr(t)
                if achou:
                    todos += [a for a in achou if a["texto"] not in {x["texto"] for x in todos}]
                    imagem = _marcar_qr(t, achou) if imagem is None else imagem
            if imagem is None:
                imagem = telas[0]
            if not todos:
                dica = (" Deixe o QR inteiro aparecendo na tela, sem nada por cima." if onde == "tela"
                        else " Aproxime o QR da câmera (uns 20 cm), com boa luz e parado.")
                return {"msg": f"Não achei QR code na {onde}.{dica}", "imagem": imagem,
                        "texto": "", "link": ""}
            textos = [a["texto"] for a in todos]
            link = next((t for t in textos if t.lower().startswith(("http://", "https://"))), "")
            msg = (f"Li {len(textos)} QR code(s) na {onde}: " + " | ".join(textos)
                   + (" (é um link — posso abrir no navegador)" if link else ""))
            return {"msg": msg, "imagem": imagem, "texto": "\n".join(textos), "link": link}

        if acao == "faces":
            quadro = telas[0]
            caixas = achar_rostos(quadro)
            escuro = float(quadro.mean()) < 35
            if not caixas:
                msg = (f"Não vi nenhum rosto na {onde}."
                       + (" A imagem está muito escura — acenda uma luz ou chegue mais perto."
                          if escuro else " Olhe para a câmera, com o rosto inteiro aparecendo."))
            else:
                msg = f"Vejo {len(caixas)} rosto(s) na {onde}."
            return {"msg": msg, "imagem": _marcar_rostos(quadro, caixas),
                    "texto": "", "link": ""}

        if acao == "analyze":
            quadro = telas[0]
            info = analisar(quadro)
            cores = info["cores"]
            cores_txt = ", ".join(f"{c['nome']} ({c['pct']}%)" for c in cores)
            msg = (f"Análise da {onde} ({info['largura']}×{info['altura']}): brilho "
                   f"{info['brilho'] * 100:.0f}% ({_txt_brilho(info['brilho'])}), imagem "
                   f"{_txt_nitidez(info['nitidez'])} (nitidez {info['nitidez']:.0f}). "
                   f"Cores principais: {cores_txt}.")
            texto = "\n".join(f"{c['nome']}  {c['hex']}  {c['pct']}%" for c in cores)
            return {"msg": msg, "imagem": _com_paleta(quadro, cores), "texto": texto, "link": ""}

    except VisaoErro as e:
        return dict(vazio, msg=f"Não consegui: {e}.")
    except Exception as e:
        return dict(vazio, msg=f"A visão falhou: {e}")
    return dict(vazio, msg="Nada a fazer.")


def computer_vision_action(parameters: dict, player=None, session_memory=None) -> str:
    """A ferramenta de voz. Fora da frente: o NEXUS se esconde só se estiver na frente."""
    ocultar = getattr(player, "ocultar_janela", None) if player is not None else None
    avisar = getattr(player, "write_log", None) if player is not None else None
    r = executar(parameters, ocultar=ocultar, avisar=avisar)
    if avisar and str(parameters.get("op") or "") != "status":
        try:
            avisar(f"SYS: 👁 {r['msg']}")
        except Exception:
            pass
    print(f"[ComputerVision] {r['msg']}")
    return r["msg"]


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "computer_vision",
    "description": (
        "Local computer vision with OpenCV (offline, no AI model). Read QR codes from the "
        "screen or the camera, count faces on the camera, analyze a frame (brightness, "
        "sharpness, main colours), and the motion sentinel: watches the camera and, when "
        "something moves, warns in the chat, plays a sound and saves a photo. "
        "angle='screen' or 'camera'. For motion: op start/stop/status, sensitivity 1-10, "
        "cooldown_seconds."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["qr", "faces", "analyze", "motion"],
                "description": "qr: read QR codes; faces: count faces (camera); analyze: frame "
                               "stats; motion: camera sentinel"
            },
            "angle": {
                "type": "STRING",
                "enum": ["screen", "camera"],
                "description": "Where to look (default: qr/analyze→screen, faces→camera)"
            },
            "op": {
                "type": "STRING",
                "enum": ["start", "stop", "status"],
                "description": "For action=motion: start/stop/status the watch"
            },
            "sensitivity": {
                "type": "NUMBER",
                "description": "Motion sensitivity 1-10 (default 5; higher = smaller movements)"
            },
            "cooldown_seconds": {
                "type": "NUMBER",
                "description": "Seconds between motion alerts (default 30)"
            },
        },
        "required": ["action"]
    },
    "handler": computer_vision_action,
}
