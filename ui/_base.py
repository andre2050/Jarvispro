"""Paths, config helpers, fonts, the theme palette and system metrics.

Part of the ui package (split from the old single ui.py)."""
from __future__ import annotations

from ._qt import *  # noqa: F401,F403

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    # the project root (this file now lives in ui/)
    return Path(__file__).absolute().resolve().parent.parent

BASE_DIR   = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"


def _read_full_config() -> dict:
    """Read api_keys.json config dict. Returns {} on any error."""
    try:
        return __import__("core.cofre", fromlist=["resolver"]).resolver(json.loads(API_FILE.read_text(encoding="utf-8")))
    except Exception:
        return {}


# Single source of truth for the release name — the window title, the header
# badge and the readme must never disagree again.
from core.pt_time import data_curta, agora, de_timestamp
from datetime import datetime as _DT
from core.protecao import engolida as _engolida

def _dt_now():
    return agora()

def _bg_color(default: str) -> str:
    """Background colour from preferences, if it is a valid #rrggbb value."""
    import re
    try:
        from core import preferences as _P
        val = str(_P.get("background_color") or "").strip()
    except Exception:
        val = ""
    return val if re.fullmatch(r"#[0-9a-fA-F]{6}", val) else default


def _persist_activity(text: str) -> None:
    """Write each activity line to memory/activity.log so it can be filtered later."""
    try:
        import time as _t
        f = _base_dir() / "memory" / "activity.log"
        f.parent.mkdir(parents=True, exist_ok=True)
        with f.open("a", encoding="utf-8") as fh:
            fh.write(f"{_t.strftime('%Y-%m-%d %H:%M:%S')} | {text}\n")
    except Exception:
        _engolida("ui/_base.py:55")


def _pref_key(pref_key: str, default: str) -> str:
    """The key name shown on screen, following the user's shortcut setting."""
    try:
        from core import preferences as _P
        return str(_P.get(pref_key) or "").strip() or default
    except Exception:
        return default


def _shortcut_seq(pref_key: str, default: str):
    """Shortcut from preferences; falls back to the default if the text is not a key."""
    from PyQt6.QtGui import QKeySequence
    try:
        from core import preferences as _P
        seq = QKeySequence(str(_P.get(pref_key) or "").strip())
    except Exception:
        seq = QKeySequence()
    return seq if not seq.isEmpty() else QKeySequence(default)
def _versao_instalada() -> str:
    """1.5 — a versão vem de memory/version.json (antes era escrita aqui à mão e
    ficava para trás: a 1.4.3 aparecia como 1.4.2)."""
    try:
        _vj = Path(__file__).resolve().parent.parent / "memory" / "version.json"
        return str(json.loads(_vj.read_text(encoding="utf-8")).get("version") or "1.5")
    except Exception:
        return "1.5"


APP_VERSION  = f"NEXUS Ultra 2026 {_versao_instalada()}"
APP_PROTOCOL = APP_VERSION.split()[-1]
DESENVOLVEDOR = "André Luiz Lima Menezes"

_DEFAULT_W, _DEFAULT_H = 1120, 760
_MIN_W,     _MIN_H     = 900, 640
_LEFT_W  = 208
_RIGHT_W = 340

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"


# The one typeface. A clean geometric sans present on Windows (and
# substituted by the system default elsewhere); monospace is kept for data
# that benefits from aligned digits.
FONT_MAIN = "Segoe UI"
FONT_MONO = "Consolas"


class C:
    # ── NEXUS Ultra 2026 · tema "Ultra 2026" (refinado na 3.6: mais profundidade e contraste) ─────────────────────────────────
    # Grafite profundo com leve tom azul-violeta, bordas de vidro fosco e um
    # acento periwinkle luminoso que se desfaz em violeta/magenta nos degradês
    # (ver accent2()). As cores de estado são fixas: violeta = falando,
    # âmbar = pensando, verde = ouvindo.
    BG        = "#070814"
    PANEL     = "#0e1124"
    PANEL2    = "#171b38"
    BORDER    = "#2a3066"
    BORDER_B  = "#6f7cff"
    BORDER_A  = "#3d46a0"
    PRI       = "#8a9bff"
    PRI_DIM   = "#5f6fe6"
    PRI_GHO   = "#151a45"
    ACC       = "#ffc970"
    ACC2      = "#ffe6b3"
    VIOLET    = "#c9adff"
    GREEN     = "#61f7cf"
    GREEN_D   = "#2dd4bf"
    RED       = "#ff6b86"
    MUTED_C   = "#ff5c7a"
    TEXT      = "#f1f3ff"
    TEXT_DIM  = "#7d83a8"
    TEXT_MED  = "#b8bfe6"
    WHITE     = "#fcfcff"
    DARK      = "#04050c"
    BAR_BG    = "#1e2352"


# Keys tied to the accent colour — status colours (ACC, GREEN, RED…) stay fixed
_HUE_LINKED = (
    "BG", "PANEL", "PANEL2", "BORDER", "BORDER_B", "BORDER_A",
    "PRI", "PRI_DIM", "PRI_GHO", "TEXT", "TEXT_DIM", "TEXT_MED",
    "WHITE", "DARK", "BAR_BG",
)
_PALETTE_DEFAULTS: dict[str, str] = {k: getattr(C, k) for k in _HUE_LINKED}

DEFAULT_UI_COLOR = _PALETTE_DEFAULTS["PRI"]
# Cores padrão das versões anteriores: quem tinha uma delas salva na
# configuração continua recebendo o tema novo (só cor escolhida de verdade vale).
LEGACY_DEFAULT_COLORS = ("#5cc8ff", "#3ee0ff", "#7b8cff")  # padrões antigos (Aurora) migram para o Ultra 2026


def accent2(base: str | None = None, shift: float = 0.13) -> str:
    """A segunda cor dos degradês: o acento girado em direção ao violeta.

    Calculada a partir de C.PRI, então acompanha qualquer cor que o usuário
    escolher em Skin/Personalizar."""
    import colorsys
    h = (base or C.PRI).lstrip("#")
    try:
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return "#8b6bff"
    hh, ss, vv = colorsys.rgb_to_hsv(r, g, b)
    r2, g2, b2 = colorsys.hsv_to_rgb((hh + shift) % 1.0, min(1.0, ss * 0.92), min(1.0, vv * 1.0))
    return "#{:02x}{:02x}{:02x}".format(int(r2 * 255 + 0.5), int(g2 * 255 + 0.5), int(b2 * 255 + 0.5))


def mix(c1: str, c2: str, t: float) -> str:
    """Mistura duas cores #rrggbb (t = 0 → c1, t = 1 → c2)."""
    t = max(0.0, min(1.0, t))
    a, b = c1.lstrip("#"), c2.lstrip("#")
    out = []
    for i in (0, 2, 4):
        x, y = int(a[i:i + 2], 16), int(b[i:i + 2], 16)
        out.append(int(x + (y - x) * t + 0.5))
    return "#{:02x}{:02x}{:02x}".format(*out)


def apply_ui_accent(accent_hex: str) -> bool:
    """
    Re-derives the whole teal-family palette from the chosen accent colour
    (hue shift — brightness/saturation ratios are preserved, design stays intact).
    Painted elements (HUD, waveform, metrics) pick up the new colour on the next
    frame; stylesheet-based panels pick it up when they are rebuilt.
    """
    import colorsys

    accent_hex = (accent_hex or "").strip().lower()
    if not (accent_hex.startswith("#") and len(accent_hex) == 7):
        return False
    try:
        int(accent_hex[1:], 16)
    except ValueError:
        return False

    def _hsv(h: str) -> tuple[float, float, float]:
        r = int(h[1:3], 16) / 255
        g = int(h[3:5], 16) / 255
        b = int(h[5:7], 16) / 255
        return colorsys.rgb_to_hsv(r, g, b)

    base_h            = _hsv(_PALETTE_DEFAULTS["PRI"])[0]
    acc_h, acc_s, _av = _hsv(accent_hex)
    dh   = acc_h - base_h
    grey = acc_s < 0.08   # near-grey accent → the whole theme is desaturated

    for key, hex0 in _PALETTE_DEFAULTS.items():
        h, s, v = _hsv(hex0)
        if grey:
            s *= 0.15
        r, g, b = colorsys.hsv_to_rgb((h + dh) % 1.0, s, v)
        setattr(C, key, "#{:02x}{:02x}{:02x}".format(
            int(r * 255 + 0.5), int(g * 255 + 0.5), int(b * 255 + 0.5)))
    return True


def current_palette() -> dict[str, str]:
    """A snapshot of the accent-linked colours currently on class C."""
    return {k: getattr(C, k) for k in _HUE_LINKED}


def retheme_all_widgets(old: dict[str, str], new: dict[str, str]) -> None:
    """
    LIVE full theme change. Replaces the old palette colours with the new ones
    in EVERY widget's stylesheet across the app and repaints them. This way the
    colour change applies INSTANTLY across the whole interface — panels, buttons,
    borders included — not just the painted elements. No restart needed.
    """
    mapping = {old[k].lower(): new[k].lower()
               for k in old if old[k].lower() != new.get(k, old[k]).lower()}
    if not mapping:
        return
    app = QApplication.instance()
    if app is None:
        return
    for w in app.allWidgets():
        try:
            ss = w.styleSheet()
            if ss:
                s2 = ss
                for o, n in mapping.items():
                    if o in s2:
                        s2 = s2.replace(o, n)
                if s2 != ss:
                    w.setStyleSheet(s2)
            w.update()
        except Exception:
            _engolida("ui/_base.py:245")


def aplicar_tema_automatico(ultima: str | None, cor: str | None = None) -> str | None:
    """Tema automático (core/tema_auto.py): aplica ao vivo a cor do momento e devolve a que ficou valendo.

    `ultima` é a cor automática já aplicada antes (None se nunca). Sem cor automática (modo desligado), se havia
    uma aplicada, devolve a interface à cor que a pessoa escolheu em Skin; nunca grava nada na configuração."""
    try:
        if cor is None:
            from core import tema_auto
            cor = tema_auto.cor_agora()
        if cor == ultima:
            return ultima
        antes = current_palette()
        if cor is None:                                   # desligou: volta à cor escolhida pela pessoa
            escolhida = (_read_full_config().get("ui_color") or "").strip().lower() or DEFAULT_UI_COLOR
            apply_ui_accent(escolhida)
        elif not apply_ui_accent(cor):
            return ultima
        retheme_all_widgets(antes, current_palette())
        return cor
    except Exception:
        return ultima


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h); c.setAlpha(a); return c


# ── GPU via NVML (sem subprocess, sem janela de console) ─────────────────────
_nvml_lib: object = None   # DLL do ctypes em cache
_nvml_ok:  object = None   # None=não testado, True=funciona, False=indisponível


def _nvml_gpu_windows() -> float:
    """Uso (%) da GPU NVIDIA pela nvml.dll direto — sem subprocess."""
    info = _nvml_read_windows()
    return float(info["util"]) if info else -1.0


def _nvml_read_windows() -> dict | None:
    """Uso, temperatura e memória da GPU NVIDIA 0 pela nvml.dll (ou pynvml)."""
    global _nvml_lib, _nvml_ok
    if _nvml_ok is False:
        return None
    try:
        import ctypes

        class _Util(ctypes.Structure):
            _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]

        class _Mem(ctypes.Structure):
            _fields_ = [("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong),
                        ("used", ctypes.c_ulonglong)]

        if _nvml_lib is None:
            for dll_name in ("nvml", r"C:\Windows\System32\nvml.dll",
                             r"C:\Program Files\NVIDIA Corporation\NVSMI\nvml.dll"):
                try:
                    lib = ctypes.WinDLL(dll_name)
                    lib.nvmlInit_v2()
                    _nvml_lib = lib
                    break
                except Exception:
                    continue

        if _nvml_lib is None:
            import pynvml  # type: ignore
            pynvml.nvmlInit()
            h = pynvml.nvmlDeviceGetHandleByIndex(0)
            _nvml_ok = True
            out = {"util": float(pynvml.nvmlDeviceGetUtilizationRates(h).gpu),
                   "temp": -1.0, "mem_pct": -1.0, "mem_used": 0.0, "mem_total": 0.0, "name": ""}
            try:
                out["temp"] = float(pynvml.nvmlDeviceGetTemperature(h, 0))
                m = pynvml.nvmlDeviceGetMemoryInfo(h)
                out.update(mem_used=m.used / 2**20, mem_total=m.total / 2**20,
                           mem_pct=100.0 * m.used / max(1, m.total))
                nm = pynvml.nvmlDeviceGetName(h)
                out["name"] = nm.decode() if isinstance(nm, bytes) else str(nm)
            except Exception:
                _engolida("ui/_base.py:327")
            return out

        dev = ctypes.c_void_p()
        _nvml_lib.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(dev))
        util = _Util()
        _nvml_lib.nvmlDeviceGetUtilizationRates(dev, ctypes.byref(util))
        out = {"util": float(util.gpu), "temp": -1.0, "mem_pct": -1.0,
               "mem_used": 0.0, "mem_total": 0.0, "name": ""}
        try:
            t = ctypes.c_uint()
            if _nvml_lib.nvmlDeviceGetTemperature(dev, 0, ctypes.byref(t)) == 0:
                out["temp"] = float(t.value)
            m = _Mem()
            if _nvml_lib.nvmlDeviceGetMemoryInfo(dev, ctypes.byref(m)) == 0:
                out.update(mem_used=m.used / 2**20, mem_total=m.total / 2**20,
                           mem_pct=100.0 * m.used / max(1, m.total))
            buf = ctypes.create_string_buffer(96)
            if _nvml_lib.nvmlDeviceGetName(dev, buf, 96) == 0:
                out["name"] = buf.value.decode(errors="ignore")
        except Exception:
            _engolida("ui/_base.py:348")
        _nvml_ok = True
        return out
    except Exception:
        _nvml_ok = False
        return None


_HIST_LEN = 40          # pontos dos gráfico (~80 s com leitura a cada 2 s)
_PROC_IGNORE = {"system idle process", "idle", "system", "registry", "memory compression",
                "secure system"}


def _short_gpu_name(name: str) -> str:
    n = (name or "").replace("NVIDIA", "").replace("GeForce", "").replace("(TM)", "").strip()
    return " ".join(n.split())[:18]


class _SysMetrics:
    def __init__(self):
        import collections
        self.cpu  = 0.0
        self.mem  = 0.0
        self.net  = 0.0          # MB/s (baixa + sobe)
        self.net_down = 0.0      # MB/s
        self.net_up   = 0.0      # MB/s
        self.gpu  = -1.0
        self.tmp  = -1.0
        self.tmp_src = ""        # "CPU" ou "GPU": de onde veio a temperatura
        self.gpu_mem_pct = -1.0
        self.gpu_mem_used = 0.0  # MB
        self.gpu_mem_total = 0.0
        self.gpu_name = ""
        self.mem_used_gb = 0.0
        self.mem_total_gb = 0.0
        self.cpu_ghz = 0.0
        self.cores = psutil.cpu_count(logical=True) or 1
        self.procs: list[tuple[str, float, float]] = []   # (nome, cpu %, RAM MB)
        self.proc_count = 0
        self.thread_count = 0
        self.hist = {k: collections.deque(maxlen=_HIST_LEN)
                     for k in ("cpu", "mem", "net", "gpu", "tmp")}
        self._lock = threading.Lock()
        self._last_net = psutil.net_io_counters()
        self._last_net_t = time.time()
        self._running = True
        # GPU (NVML) e temperatura (WMI) são as consultas caras: abre uma vez e reaproveita.
        self._slow_tick = 0            # gpu/temp/processos a cada 3ª leitura
        self._pynvml    = None
        self._pynvml_h  = None
        self._pynvml_ok = None         # None=não testado, False=indisponível aqui
        self._nv_unix   = None
        self._wmi_conn  = None
        self._wmi_ok    = None
        self._wmi_hw    = None         # LibreHardwareMonitor / OpenHardwareMonitor
        self._wmi_hw_ok = None
        try:
            psutil.cpu_percent(interval=None)
            for p in psutil.process_iter(["cpu_percent"]):   # primeira leitura = referência
                pass
        except Exception:
            _engolida("ui/_base.py:409")
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self):
        while self._running:
            try:
                self._update()
            except Exception:
                _engolida("ui/_base.py:418")
            time.sleep(2.0)

    # ── leitura ──────────────────────────────────────────────────────────────
    def _update(self):
        cpu = psutil.cpu_percent(interval=None)
        vm = psutil.virtual_memory()
        mem = vm.percent

        nc  = psutil.net_io_counters()
        now = time.time()
        dt  = now - self._last_net_t
        down = up = 0.0
        if dt > 0:
            up   = max(0.0, (nc.bytes_sent - self._last_net.bytes_sent) / dt) / (1024 * 1024)
            down = max(0.0, (nc.bytes_recv - self._last_net.bytes_recv) / dt) / (1024 * 1024)
        self._last_net   = nc
        self._last_net_t = now

        try:
            f = psutil.cpu_freq()
            ghz = (f.current / 1000.0) if f and f.current else 0.0
        except Exception:
            ghz = 0.0

        self._slow_tick = (self._slow_tick + 1) % 3
        if self._slow_tick == 1:
            g = self._get_gpu()
            gpu = g["util"] if g else -1.0
            tmp, src = self._get_temp(g)
            procs, count, threads = self._get_procs()
            with self._lock:
                self.gpu, self.tmp, self.tmp_src = gpu, tmp, src
                if g:
                    self.gpu_mem_pct = g.get("mem_pct", -1.0)
                    self.gpu_mem_used = g.get("mem_used", 0.0)
                    self.gpu_mem_total = g.get("mem_total", 0.0)
                    self.gpu_name = _short_gpu_name(g.get("name", "")) or self.gpu_name
                else:
                    self.gpu_mem_pct = -1.0
                self.procs, self.proc_count, self.thread_count = procs, count, threads

        with self._lock:
            self.cpu, self.mem = cpu, mem
            self.net, self.net_down, self.net_up = down + up, down, up
            self.mem_used_gb = (vm.total - vm.available) / 2**30
            self.mem_total_gb = vm.total / 2**30
            self.cpu_ghz = ghz
            h = self.hist
            h["cpu"].append(cpu)
            h["mem"].append(mem)
            h["net"].append(min(100.0, (down + up) * 10.0))      # 10 MB/s = 100%
            h["gpu"].append(max(0.0, self.gpu))
            h["tmp"].append(max(0.0, min(100.0, (self.tmp - 30.0) / 70.0 * 100.0)) if self.tmp >= 0 else 0.0)

    def _get_procs(self):
        """Processos agrupados por nome (o Chrome tem dezenas): CPU % do total e RAM em MB."""
        grupos: dict[str, list[float]] = {}
        count = threads = 0
        ncpu = float(self.cores)
        for p in psutil.process_iter(["name", "cpu_percent", "memory_info", "num_threads"]):
            try:
                i = p.info
                count += 1
                threads += int(i.get("num_threads") or 0)
                nome = str(i.get("name") or "?")
                if nome.lower().replace(".exe", "") in _PROC_IGNORE or p.pid == 0:
                    continue
                mi = i.get("memory_info")
                g = grupos.setdefault(nome[:-4] if nome.lower().endswith(".exe") else nome, [0.0, 0.0])
                g[0] += float(i.get("cpu_percent") or 0.0) / ncpu
                g[1] += (mi.rss / 2**20) if mi else 0.0
            except Exception:
                continue
        lista = [(n, v[0], v[1]) for n, v in grupos.items()]
        return lista, count, threads

    def _get_gpu(self) -> dict | None:
        if self._pynvml_ok is not False:
            try:
                if self._pynvml_h is None:
                    import pynvml  # type: ignore
                    pynvml.nvmlInit()
                    self._pynvml    = pynvml
                    self._pynvml_h  = pynvml.nvmlDeviceGetHandleByIndex(0)
                    self._pynvml_ok = True
                nv, h = self._pynvml, self._pynvml_h
                out = {"util": float(nv.nvmlDeviceGetUtilizationRates(h).gpu),
                       "temp": -1.0, "mem_pct": -1.0, "mem_used": 0.0, "mem_total": 0.0, "name": ""}
                try:
                    out["temp"] = float(nv.nvmlDeviceGetTemperature(h, 0))
                    m = nv.nvmlDeviceGetMemoryInfo(h)
                    out.update(mem_used=m.used / 2**20, mem_total=m.total / 2**20,
                               mem_pct=100.0 * m.used / max(1, m.total))
                    nm = nv.nvmlDeviceGetName(h)
                    out["name"] = nm.decode() if isinstance(nm, bytes) else str(nm)
                except Exception:
                    _engolida("ui/_base.py:515")
                return out
            except Exception:
                self._pynvml_ok = False

        if _OS == "Windows":
            return _nvml_read_windows()

        try:
            import ctypes

            class _Util(ctypes.Structure):
                _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]

            if self._nv_unix is None:
                _lib = "libnvidia-ml.so.1" if _OS == "Linux" else "libnvidia-ml.dylib"
                nv = ctypes.CDLL(_lib)
                nv.nvmlInit_v2()
                dev = ctypes.c_void_p()
                nv.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(dev))
                self._nv_unix = (nv, dev)

            nv, dev = self._nv_unix
            u = _Util()
            nv.nvmlDeviceGetUtilizationRates(dev, ctypes.byref(u))
            out = {"util": float(u.gpu), "temp": -1.0, "mem_pct": -1.0,
                   "mem_used": 0.0, "mem_total": 0.0, "name": ""}
            t = ctypes.c_uint()
            if nv.nvmlDeviceGetTemperature(dev, 0, ctypes.byref(t)) == 0:
                out["temp"] = float(t.value)
            return out
        except Exception:
            _engolida("ui/_base.py:547")
        return None

    def _get_temp(self, gpu: dict | None = None) -> tuple[float, str]:
        """(graus °C, origem). Tenta o sensor da CPU de várias formas; sem nenhum,
        cai para a temperatura da placa de vídeo NVIDIA, que quase sempre responde."""
        try:
            temps = psutil.sensors_temperatures()
            for name in ["coretemp", "k10temp", "cpu_thermal", "acpitz",
                         "cpu-thermal", "zenpower", "it8688"]:
                if name in temps and temps[name]:
                    return float(temps[name][0].current), "CPU"
            for entries in temps.values():
                if entries:
                    return float(entries[0].current), "CPU"
        except Exception:
            _engolida("ui/_base.py:563")

        if _OS == "Windows":
            # Sensores do LibreHardwareMonitor / OpenHardwareMonitor, se estiverem abertos.
            if self._wmi_hw_ok is not False:
                try:
                    if self._wmi_hw is None:
                        import wmi  # type: ignore
                        for ns in ("root/LibreHardwareMonitor", "root/OpenHardwareMonitor"):
                            try:
                                self._wmi_hw = wmi.WMI(namespace=ns)
                                self._wmi_hw.Sensor(SensorType="Temperature")
                                break
                            except Exception:
                                self._wmi_hw = None
                        if self._wmi_hw is None:
                            raise RuntimeError("sem monitor de hardware")
                    cand = [s for s in self._wmi_hw.Sensor(SensorType="Temperature")
                            if any(k in str(s.Name) for k in ("CPU Package", "Core (Tctl", "Core Average", "CPU Core"))
                            and s.Value]
                    if cand:
                        return float(cand[0].Value), "CPU"
                except Exception:
                    self._wmi_hw_ok = False
                    self._wmi_hw = None

            if self._wmi_ok is not False:
                try:
                    if self._wmi_conn is None:
                        import wmi  # type: ignore
                        self._wmi_conn = wmi.WMI(namespace="root/wmi")
                    tz = self._wmi_conn.MSAcpi_ThermalZoneTemperature()
                    if tz:
                        v = (tz[0].CurrentTemperature / 10.0) - 273.15
                        if 5 < v < 120:
                            return v, "CPU"
                except Exception:
                    self._wmi_ok   = False
                    self._wmi_conn = None

        if gpu and gpu.get("temp", -1.0) > 0:
            return float(gpu["temp"]), "GPU"
        return -1.0, ""

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "cpu": self.cpu, "mem": self.mem, "net": self.net,
                "net_down": self.net_down, "net_up": self.net_up,
                "gpu": self.gpu, "tmp": self.tmp, "tmp_src": self.tmp_src,
                "gpu_mem_pct": self.gpu_mem_pct, "gpu_mem_used": self.gpu_mem_used,
                "gpu_mem_total": self.gpu_mem_total, "gpu_name": self.gpu_name,
                "mem_used_gb": self.mem_used_gb, "mem_total_gb": self.mem_total_gb,
                "cpu_ghz": self.cpu_ghz, "cores": self.cores,
                "procs": list(self.procs), "proc_count": self.proc_count,
                "thread_count": self.thread_count,
                "hist": {k: list(v) for k, v in self.hist.items()},
            }


_metrics = _SysMetrics()
