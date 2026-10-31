"""The main window: layout, HUD, panels, shortcuts, tray, video.

Part of the ui package (split from the old single ui.py)."""
from __future__ import annotations

from ._qt import *  # noqa: F401,F403
from ._base import _base_dir  # noqa: F401
from ._base import APP_VERSION, C, DEFAULT_UI_COLOR, FONT_MAIN, FONT_MONO, _DEFAULT_H, _DEFAULT_W, _LEFT_W, _MIN_H, _MIN_W, _OS, _RIGHT_W, _bg_color, _dt_now, _metrics, _read_full_config, agora, apply_ui_accent, current_palette, data_curta, retheme_all_widgets  # noqa: F401
from ._base import LEGACY_DEFAULT_COLORS  # noqa: F401
from .hud import HudCanvas  # noqa: F401
from .overlays.customize import CustomizeOverlay  # noqa: F401
from .overlays.remote import RemoteKeyOverlay  # noqa: F401
from .overlays.settings import SettingsPanelOverlay  # noqa: F401
from .overlays.setup import SetupOverlay  # noqa: F401
from .widgets import ClipboardPanel, FileDropZone, _CameraPreview, _FILE_ICONS, _file_category, _fmt_size  # noqa: F401
from .modern import (ICONE_SETUP, ChatLog, ControlButton, GradientLabel, HeaderBar, MenuButton, ProcessList, QuickBar,  # noqa: F401
                     RingGauge, SparkMetric, StatusCard, UptimeCard)
from . import quickbar as QB
from core.protecao import engolida as _engolida
from .janela_camera_video import CameraVideoMixin
from .janela_atalhos_sistema import AtalhosSistemaMixin
from .janela_conteudo_estudo import ConteudoEstudoMixin
from .janela_voz_entrada import VozEntradaMixin
from .janela_paineis import PaineisMixin
from .janela_licenca_atalhos import LicencaAtalhosMixin

class MainWindow(CameraVideoMixin, AtalhosSistemaMixin, ConteudoEstudoMixin, VozEntradaMixin, PaineisMixin, LicencaAtalhosMixin, QMainWindow):
    _log_sig        = pyqtSignal(str)
    _state_sig      = pyqtSignal(str)
    _content_sig    = pyqtSignal(str, str)   # (title, text) — thread-safe content display
    _reconfig_sig   = pyqtSignal()           # trigger setup overlay from any thread
    _ambiente_sig   = pyqtSignal()           # perfil/ambiente mudou (3.7): reaplica cor e visual do hub
    _camera_sig     = pyqtSignal(bytes)      # show camera frame preview (small overlay)
    _cam_stream_sig = pyqtSignal(bool)       # True=start live stream, False=stop
    _cam_frame_sig  = pyqtSignal(bytes)      # live camera frame → HUD area
    _video_open_sig  = pyqtSignal(str, str, bool, str)  # video, title, muted, audio
    _wake_btns_sig   = pyqtSignal()          # wake state resolved off-thread
    _video_close_sig = pyqtSignal()
    _video_mute_sig  = pyqtSignal(bool)
    _clipboard_sig  = pyqtSignal(str)        # clipboard text changed (thread-safe)
    _confirm_sig    = pyqtSignal(str, str)   # (title, detail) — irreversible-action gate
    _confirm_hide_sig = pyqtSignal()
    _wake_dl_sig    = pyqtSignal(bool, str)  # wake-word install finished (ok, message)
    _quiz_sig       = pyqtSignal(str, object, object)  # (topic, questions, grader)
    _quiz_hide_sig  = pyqtSignal()
    _review_sig     = pyqtSignal(str, str, object, object)  # document review payload
    _ditado_sig     = pyqtSignal(bool)       # 1.4 — modo ditado ligou / desligou
    _ia_painel_sig  = pyqtSignal(str)        # Ultra 2026 — abre o painel "Como a IA funciona" (aba)
    _restart_sig    = pyqtSignal()           # 1.4.1 — reiniciar depois de atualizar
    _ocultar_sig    = pyqtSignal(bool)       # 1.4.2 — sair da frente para fotografar a tela

    def __init__(self, face_path: str):
        super().__init__()
        self._face_path = face_path

        # Load customization from config
        _cfg = _read_full_config()
        self._assistant_name: str = (_cfg.get("assistant_name") or "NEXUS").strip()
        _display = self._assistant_name.upper()

        # Apply the saved UI colour BEFORE panels/stylesheets are built
        _ui_color = (_cfg.get("ui_color") or "").strip()
        # (quem ainda tem a cor padrão antiga salva recebe o tema novo, não o velho)
        if _ui_color and _ui_color.lower() not in (DEFAULT_UI_COLOR, *LEGACY_DEFAULT_COLORS):
            apply_ui_accent(_ui_color)
        # Tema automático (3.5): hora do dia e/ou humor do diário; sobrepõe a cor só enquanto o modo estiver ligado
        self._tema_auto_cor = None
        try:
            from core import tema_auto as _TA
            _cor_auto = _TA.cor_agora()
            if _cor_auto and apply_ui_accent(_cor_auto):
                self._tema_auto_cor = _cor_auto
        except Exception:
            _engolida("ui/main_window.py:70")

        self.setWindowTitle(f"{APP_VERSION} — desenvolvido por André Luiz Lima Menezes")
        self.setMinimumSize(_MIN_W, _MIN_H)
        self.resize(_DEFAULT_W, _DEFAULT_H)
        self._tray = None
        self._setup_tray()

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            (screen.width()  - _DEFAULT_W) // 2,
            (screen.height() - _DEFAULT_H) // 2,
        )

        self.on_text_command   = None
        self.on_remote_clicked = None   # callable: () -> (url, key) | None
        self.on_interrupt      = None   # callable: () -> None — stop NEXUS mid-speech
        self.on_toggle_ditado  = None   # callable: () -> str — 1.4, liga/desliga o ditado
        self.on_voice_change   = None   # callable: () -> None — rebuild session with new voice
        self.on_audio_device_change = None  # callable: () -> None — reopen audio streams
        self.on_live_settings_change = None  # 1.4.3 — velocidade da resposta: reconectar já
        self._confirm_overlay  = None   # live ConfirmBanner, if one is on screen
        self.get_plugins       = None   # callable: () -> list[dict], set by NexusLive
        self.get_plugin_settings = None # callable: () -> list[dict] settings schemas, set by NexusLive
        self.on_wake_toggle    = None   # callable: (enable: bool) -> str, set by NexusLive
        self.on_wake_manual    = None   # callable: () -> None — manual sleep/wake
        self.on_push_to_talk   = None   # callable: (enable: bool) -> str scope
        self.ptt_hold          = None   # callable: (held: bool) -> None — windowed chord
        self.wake_get_state    = None   # callable: () -> dict {enabled, awake, ready}
        self._muted            = False
        self._current_file: str | None = None
        self._remote_overlay: RemoteKeyOverlay | None = None
        self._customize_overlay: CustomizeOverlay | None = None
        self._clip_history: list[str] = []     # in-memory clipboard history
        self._clip_self = False                # our own copy-back, not a capture

        central = QWidget()
        central.setStyleSheet(f"background: {_bg_color(C.BG)};")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._left_panel = self._build_left_panel()
        body.addWidget(self._left_panel, stretch=0)

        # Center column: HUD + resizable content panel via QSplitter
        self.hud = HudCanvas(face_path, _display)
        self.hud.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._content_panel = self._build_content_panel()
        self._quiz_panel = self._build_quiz_panel()

        # Live camera container — replaces HUD when camera stream is active
        _cam_cont = QWidget()
        _cam_cont.setStyleSheet("background: #000308;")
        _cam_v = QVBoxLayout(_cam_cont)
        _cam_v.setContentsMargins(0, 0, 0, 0)
        _cam_v.setSpacing(0)
        _cam_hdr = QHBoxLayout()
        _cam_hdr.setContentsMargins(8, 5, 8, 5)
        _cam_title = QLabel("◈  CÂMERA AO VIVO")
        _cam_title.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        _cam_title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        _cam_hdr.addWidget(_cam_title)
        _cam_hdr.addStretch()
        _cam_x = QPushButton("✕  FECHAR")
        _cam_x.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        _cam_x.setCursor(Qt.CursorShape.PointingHandCursor)
        _cam_x.setStyleSheet(f"""
            QPushButton {{
                color: {C.TEXT_DIM}; background: transparent;
                border: none; padding: 2px 6px;
            }}
            QPushButton:hover {{ color: {C.PRI}; }}
        """)
        _cam_x.clicked.connect(self.stop_camera_stream)
        _cam_hdr.addWidget(_cam_x)
        _cam_v.addLayout(_cam_hdr)
        self._cam_live_lbl = QLabel()
        self._cam_live_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cam_live_lbl.setStyleSheet("background: transparent;")
        self._cam_live_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        _cam_v.addWidget(self._cam_live_lbl, stretch=1)

        # ── Video surface ────────────────────────────────────────────────
        # Built exactly like the camera page above and stacked beside it,
        # because it is the same idea: something takes the centre of the HUD
        # for a while and then gives it back. Sharing the stack rather than
        # inventing a second mechanism means the avatar, the camera and a video
        # can never be on screen at once.
        self._video_split = False        # is the sound a separate stream?
        self._video_auto_muted = False   # did NEXUS close the mic, or the user?
        # A plain flag rather than reading the widget. video_is_playing() is
        # called from plugin threads, and reading a widget's state from one is
        # not something to rely on; an attribute is.
        self._video_on = False
        self._video_cont = QWidget()
        self._video_cont.setStyleSheet(f"background: {C.BG};")
        _vid_v = QVBoxLayout(self._video_cont)
        _vid_v.setContentsMargins(8, 6, 8, 8)
        _vid_v.setSpacing(4)

        _vid_hdr = QHBoxLayout()
        self._video_title = QLabel("▶  VÍDEO")
        self._video_title.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        self._video_title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        _vid_hdr.addWidget(self._video_title)
        _vid_hdr.addStretch()

        def _vid_btn(text: str) -> QPushButton:
            b = QPushButton(text)
            b.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{
                    color: {C.TEXT_DIM}; background: transparent;
                    border: none; padding: 2px 6px;
                }}
                QPushButton:hover {{ color: {C.PRI}; }}
            """)
            return b

        # Muted is the default and the button says so, because a soundtrack
        # talking over NEXUS is the one way this feature could make the
        # assistant worse rather than better.
        self._video_mute_btn = _vid_btn("🔇  SEM SOM")
        self._video_mute_btn.clicked.connect(self._toggle_video_mute)
        _vid_hdr.addWidget(self._video_mute_btn)

        _vid_x = _vid_btn("✕  FECHAR")
        _vid_x.clicked.connect(self.stop_video)
        _vid_hdr.addWidget(_vid_x)
        _vid_v.addLayout(_vid_hdr)

        if HAVE_VIDEO:
            # A GRAPHICS ITEM, NOT A QVideoWidget.
            #
            # QVideoWidget gets a native window of its own, and a native window
            # is painted by the compositor above every ordinary widget that
            # shares the screen with it — so the settings drawer opened
            # *underneath* the video and raise_() could not help, because the
            # two are not in the same painting order at all. A video item drawn
            # into a QGraphicsView goes through Qt's own painter like any other
            # widget, and anything laid over it stays over it.
            self._video_scene = QGraphicsScene(self)
            self._video_item = QGraphicsVideoItem()
            self._video_scene.addItem(self._video_item)
            self._video_widget = QGraphicsView(self._video_scene)
            self._video_widget.setStyleSheet("background: #000; border: none;")
            self._video_widget.setFrameShape(QGraphicsView.Shape.NoFrame)
            self._video_widget.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._video_widget.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._video_widget.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            _vid_v.addWidget(self._video_widget, stretch=1)

            self._video_audio = QAudioOutput()
            self._video_audio.setMuted(True)
            self._video_player = QMediaPlayer()
            self._video_player.setVideoOutput(self._video_item)
            # Keep the picture filling the view as the window is resized.
            self._video_item.nativeSizeChanged.connect(self._fit_video)
            self._video_player.setAudioOutput(self._video_audio)
            self._video_player.errorOccurred.connect(self._on_video_error)

            # A SECOND player, for sound that arrives separately.
            #
            # YouTube no longer serves a single stream carrying both picture and
            # sound — not for new uploads and not for old ones; checked against
            # three videos including the oldest on the site, and every one of
            # them offered zero combined formats. Picture and sound are two
            # URLs, so they are two players, started together and nudged back
            # into line by the timer below.
            #
            # A local file or a direct video URL still uses the first player
            # alone: one stream, one player, nothing to synchronise.
            self._video_sound = QMediaPlayer()
            self._video_sound_out = QAudioOutput()
            self._video_sound_out.setMuted(True)
            self._video_sound.setAudioOutput(self._video_sound_out)

            self._video_sync = QTimer(self)
            self._video_sync.setInterval(1000)
            self._video_sync.timeout.connect(self._sync_video_sound)
        else:
            self._video_scene = None
            self._video_item = None
            self._video_widget = None
            self._video_player = None
            self._video_audio = None
            self._video_sound = None
            self._video_sound_out = None
            self._video_sync = None
            _miss = QLabel("Este Qt não tem reprodução de vídeo instalada.")
            _miss.setAlignment(Qt.AlignmentFlag.AlignCenter)
            _miss.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            _vid_v.addWidget(_miss, stretch=1)

        # Stack: 0 = animated HUD, 1 = live camera, 2 = video
        self._hud_cam_stack = QStackedWidget()
        self._hud_cam_stack.addWidget(self.hud)
        self._hud_cam_stack.addWidget(_cam_cont)
        self._hud_cam_stack.addWidget(self._video_cont)

        self._center_split = QSplitter(Qt.Orientation.Vertical)
        self._center_split.setStyleSheet(f"""
            QSplitter::handle {{
                background: {C.BORDER};
                height: 4px;
            }}
            QSplitter::handle:hover {{
                background: {C.PRI_DIM};
            }}
        """)
        self._center_split.addWidget(self._hud_cam_stack)
        self._center_split.addWidget(self._content_panel)
        self._center_split.addWidget(self._quiz_panel)
        self._center_split.setStretchFactor(0, 3)
        self._center_split.setStretchFactor(1, 1)
        self._center_split.setCollapsible(0, False)
        body.addWidget(self._center_split, stretch=5)

        self._right_panel = self._build_right_panel()
        body.addWidget(self._right_panel, stretch=0)

        root.addLayout(body, stretch=1)
        self._root_layout = root
        # 1.2 — barra de acesso rápido, logo acima do rodapé
        self._quickbar = QuickBar(self._open_quickbar_editor)
        root.addWidget(self._quickbar)
        root.addWidget(self._build_footer())
        self._rebuild_quickbar()

        # Quick-access drawer (floating overlay, built after central widget layout is done)
        self._quick_drawer = self._build_quick_drawer()
        self._ctrl_drawer = self._build_controls_drawer()
        self._warm_wake_state()
        self._update_autostart_btn(self._check_autostart())
        from memory.config_manager import get_brief_enabled as _gbe
        self._update_brief_btn(_gbe())

        self._tema_tmr = QTimer(self)
        self._tema_tmr.timeout.connect(self._tick_tema_auto)
        self._tema_tmr.start(60_000)

        self._clock_tmr = QTimer(self)
        self._clock_tmr.timeout.connect(self._tick_clock)
        self._clock_tmr.start(1000)
        self._tick_clock()

        # Metric update timer
        self._metric_tmr = QTimer(self)
        self._metric_tmr.timeout.connect(self._update_metrics)
        self._metric_tmr.start(2000)
        self._update_metrics()

        self._log_sig.connect(self._log.append_log)
        self._state_sig.connect(self._apply_state)
        self._content_sig.connect(self._show_content)
        self._ambiente_sig.connect(self._aplicar_ambiente)
        try:
            from core import perfis as _perfis
            _perfis.ao_mudar(self._ambiente_sig.emit)
        except Exception:
            _engolida("ui/main_window.py:345")
        self._reconfig_sig.connect(self._show_setup)
        self._camera_sig.connect(self._show_camera_frame)
        self._confirm_sig.connect(self._show_confirm_banner)
        self._confirm_hide_sig.connect(self._hide_confirm_banner)
        self._cam_stream_sig.connect(self._on_cam_stream)
        self._cam_frame_sig.connect(self._on_cam_frame)
        self._wake_btns_sig.connect(self._refresh_wake_btns)
        self._video_open_sig.connect(self._on_video_open)
        self._video_close_sig.connect(self._on_video_close)
        self._video_mute_sig.connect(self._on_video_mute)
        self._clipboard_sig.connect(self._show_clipboard_panel)
        self._wake_dl_sig.connect(self._on_wake_install_done)
        self._quiz_sig.connect(self._show_quiz)
        self._quiz_hide_sig.connect(self._hide_quiz)
        self._review_sig.connect(self._show_review)
        self._ditado_sig.connect(self._on_ditado_mudou)
        self._ia_painel_sig.connect(self._open_ia_panel)
        self._restart_sig.connect(self._restart_app)
        self._ocultar_sig.connect(self._ocultar_para_captura)
        self._cam_stop = threading.Event()

        # Camera preview overlay (child of central widget, positioned in resizeEvent)
        self._cam_preview = _CameraPreview(self.centralWidget())

        # Clipboard panel (child of central widget, bottom-center)
        self._clipboard_panel = ClipboardPanel(self.centralWidget())
        self._clipboard_panel.action_requested.connect(self._on_clipboard_action)
        QApplication.clipboard().dataChanged.connect(self._on_clipboard_changed)

        self._overlay: SetupOverlay | None = None
        # 🔑 Licença: sem licença válida o NEXUS não liga (nem pede a chave do
        # Gemini). `_ready` só vira True com licença E configuração prontas —
        # é nele que o assistente espera (NexusUI.wait_for_api_key).
        self._license_status = self._license_check()
        self._licensed = bool(self._license_status["valida"])
        self._ready = self._licensed and self._check_config()
        if not self._licensed:
            self._show_license(self._license_status["motivo"])
        elif not self._ready:
            self._show_setup()

        # Atalhos de teclado: todos personalizáveis (Configurações › ATALHOS)
        self._shortcuts: list[QShortcut] = []
        self._install_shortcuts()

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cw = self.centralWidget()
        self._recentrar_licenca()
        if self._overlay and self._overlay.isVisible():
            ow, oh = 460, 390
            self._overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        if self._remote_overlay and self._remote_overlay.isVisible():
            ow, oh = RemoteKeyOverlay._OW, RemoteKeyOverlay._OH
            self._remote_overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        if self._customize_overlay and self._customize_overlay.isVisible():
            ow, oh = CustomizeOverlay._OW, CustomizeOverlay._OH
            self._customize_overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        # Camera preview — bottom-right corner of the center/HUD area
        pw = _CameraPreview._W
        ph = self._cam_preview.height() or _CameraPreview._H
        self._cam_preview.setGeometry(
            cw.width() - _RIGHT_W - pw - 12,
            cw.height() - ph - 28,
            pw, ph,
        )
        # Clipboard panel — bottom-center
        if hasattr(self, '_clipboard_panel') and self._clipboard_panel.isVisible():
            self._position_clipboard_panel()
        # Quick drawer — reposition if open
        if hasattr(self, '_quick_drawer') and self._quick_drawer.isVisible():
            self._position_quick_drawer()
        if hasattr(self, '_ctrl_drawer') and self._ctrl_drawer.isVisible():
            self._position_ctrl_drawer()
        self._fit_video()

    @staticmethod
    def _pt(x: float, casas: int = 1) -> str:
        """Número no formato brasileiro (vírgula decimal)."""
        return f"{x:.{casas}f}".replace(".", ",")

    @classmethod
    def _fmt_rate(cls, mb: float) -> str:
        return f"{mb * 1024:.0f} KB/s" if mb < 1.0 else f"{cls._pt(mb)} MB/s"

    def _update_metrics(self):
        snap = _metrics.snapshot()
        hist = snap.get("hist", {})
        pt = self._pt

        # CPU
        cpu = snap["cpu"]
        ghz = snap.get("cpu_ghz", 0.0)
        sub = f"{snap.get('cores', 0)} núcleos" + (f" · {pt(ghz)} GHz" if ghz else "")
        self._bar_cpu.set_value(cpu, f"{cpu:.0f}%", sub)

        # Memória
        mem = snap["mem"]
        self._bar_mem.set_value(mem, f"{mem:.0f}%",
                                f"{pt(snap.get('mem_used_gb', 0.0))}/{pt(snap.get('mem_total_gb', 0.0), 0)} GB")

        # Rede (total + baixa/sobe)
        net = snap["net"]
        net_pct = min(100, net * 10)             # 10 MB/s = 100%
        self._bar_net.set_history(hist.get("net", []))
        self._bar_net.set_value(net_pct, self._fmt_rate(net),
                                f"↓ {self._fmt_rate(snap.get('net_down', 0.0))}   ↑ {self._fmt_rate(snap.get('net_up', 0.0))}",
                                push=False)

        # GPU
        gpu = snap["gpu"]
        self._bar_gpu.set_history(hist.get("gpu", []))
        if gpu >= 0:
            nome = snap.get("gpu_name", "")
            vram = snap.get("gpu_mem_pct", -1.0)
            partes = [nome] if nome else []
            if vram >= 0:
                partes.append(f"VRAM {vram:.0f}%")
            self._bar_gpu.set_value(gpu, f"{gpu:.0f}%", " · ".join(partes), push=False)
        else:
            self._bar_gpu.set_value(0, "N/D", "placa NVIDIA não detectada", push=False)

        # Temperatura
        tmp = snap["tmp"]
        self._bar_tmp.set_history(hist.get("tmp", []))
        if tmp >= 0:
            tmp_pct = max(0.0, min(100.0, (tmp - 30.0) / 70.0 * 100.0))
            _unit, _shown = "°C", tmp
            try:
                from core import preferences as _P
                if str(_P.get("temp_unit")).upper() == "F":
                    _unit, _shown = "°F", tmp * 9 / 5 + 32
            except Exception:
                _engolida("ui/main_window.py:1029")
            origem = "da CPU" if snap.get("tmp_src") == "CPU" else "da placa de vídeo"
            self._bar_tmp.set_value(tmp_pct, f"{_shown:.0f}{_unit}", f"sensor {origem}", push=False)
        else:
            self._bar_tmp.set_value(0, "N/D", "sem sensor disponível", push=False)

        # Tempo ligado
        try:
            boot_t = psutil.boot_time()
            elapsed = time.time() - boot_t
            import datetime as _d
            dt = _d.datetime.fromtimestamp(boot_t)
            dias = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
            self._uptime_card.set_uptime(
                elapsed, f"desde {dias[dt.weekday()]} {dt:%d/%m} às {dt:%H:%M}")
        except Exception:
            self._uptime_card.set_uptime(0, "indisponível")

        # Processos do Windows
        try:
            self._proc_list.set_data(snap.get("procs", []),
                                     snap.get("proc_count") or len(psutil.pids()),
                                     snap.get("thread_count", 0))
        except Exception:
            self._proc_list.set_data([], 0)


    def _build_header(self) -> QWidget:
        w = HeaderBar()
        w.setFixedHeight(58)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(16, 0, 16, 0)

        def _badge(txt, color=C.TEXT_MED):
            l = QLabel(txt)
            l.setFont(QFont(FONT_MAIN, 8))
            l.setStyleSheet(f"color: {color}; background: transparent;")
            return l

        lay.addWidget(_badge(APP_VERSION, C.PRI_DIM))
        lay.addSpacing(8)
        self._drawer_btn = QPushButton("⚙")
        self._drawer_btn.setFixedSize(26, 26)
        self._drawer_btn.setFont(QFont(FONT_MAIN, 11))
        self._drawer_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._drawer_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 4px;
            }}
            QPushButton:hover {{ color: {C.PRI}; border-color: {C.PRI_DIM}; }}
            QPushButton:checked {{ color: {C.PRI}; border-color: {C.PRI}; background: {C.PRI_GHO}; }}
        """)
        self._drawer_btn.setCheckable(True)
        self._drawer_btn.setToolTip("Configurar — o que você ajusta uma vez")
        self._drawer_btn.clicked.connect(self._toggle_drawer)
        lay.addWidget(self._drawer_btn)

        # A SECOND drawer, and the split is by how often a thing is touched.
        #
        # One panel held twelve buttons: the ones you press once when you set
        # the assistant up sitting next to the ones you flick on and off every
        # day. Separating them by that — setup behind ⚙, everyday behind 🎛 —
        # is what makes each list short enough to read at a glance.
        self._ctrl_btn = QPushButton("🎛")
        self._ctrl_btn.setFixedSize(26, 26)
        self._ctrl_btn.setFont(QFont(FONT_MAIN, 11))
        self._ctrl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ctrl_btn.setToolTip("Controles — os botões do dia a dia")
        self._ctrl_btn.setStyleSheet(self._drawer_btn.styleSheet())
        self._ctrl_btn.setCheckable(True)
        self._ctrl_btn.clicked.connect(self._toggle_controls)
        lay.addSpacing(4)
        lay.addWidget(self._ctrl_btn)
        lay.addStretch()

        mid = QVBoxLayout(); mid.setSpacing(1)
        _disp = self._assistant_name.upper()
        self._title_lbl = GradientLabel(_disp)
        self._title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _tf = QFont(FONT_MAIN, 24, QFont.Weight.Light)
        _tf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 7)
        self._title_lbl.setFont(_tf)
        self._title_lbl.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        # o selo "ULTRA 2026" ao lado do nome
        self._pro_lbl = QLabel("ULTRA 2026")
        _pf = QFont(FONT_MAIN, 8, QFont.Weight.Bold)
        _pf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        self._pro_lbl.setFont(_pf)
        self._pro_lbl.setStyleSheet(
            f"color: {C.BG}; border-radius: 4px; padding: 1px 6px 1px 8px;"
            f" background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {C.ACC2}, stop:1 {C.ACC});")
        self._pro_lbl.setVisible(_disp == "NEXUS")
        _trow = QHBoxLayout(); _trow.setSpacing(8)
        _trow.addStretch(1)
        _trow.addWidget(self._title_lbl)
        _trow.addWidget(self._pro_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        _trow.addStretch(1)
        mid.addLayout(_trow)
        _sub_text = ("ASSISTENTE PESSOAL INTELIGENTE" if _disp == "NEXUS"
                     else "Assistente pessoal")
        self._sub_lbl = QLabel(_sub_text)
        self._sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _sf = QFont(FONT_MAIN, 8)
        _sf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)
        self._sub_lbl.setFont(_sf)
        self._sub_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        mid.addWidget(self._sub_lbl)
        lay.addLayout(mid)
        lay.addStretch()

        right_col = QVBoxLayout(); right_col.setSpacing(2)
        self._clock_lbl = QLabel("00:00:00")
        _cf = QFont(FONT_MONO, 17, QFont.Weight.Light)
        _cf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        self._clock_lbl.setFont(_cf)
        self._clock_lbl.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        self._clock_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._clock_lbl)
        self._date_lbl = QLabel("")
        self._date_lbl.setFont(QFont(FONT_MAIN, 7))
        self._date_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._date_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._date_lbl)
        lay.addLayout(right_col)
        return w

    def _tick_clock(self):
        self._clock_lbl.setText(agora().strftime("%H:%M:%S"))
        self._date_lbl.setText(data_curta(_dt_now()))
        try:
            from core import preferences as _P
            self._clock_lbl.setVisible(bool(_P.get("show_clock")))
            self._date_lbl.setVisible(bool(_P.get("show_date")))
        except Exception:
            _engolida("ui/main_window.py:1164")

    def _build_left_panel(self) -> QWidget:
        """Monitor do sistema (visual 2.2): CPU e memória em medidores de arco,
        rede/GPU/temperatura com gráfico ao vivo, tempo ligado, os processos que
        mais pesam e o cartão de ESTADO fixo embaixo."""
        outer = QWidget()
        outer.setFixedWidth(_LEFT_W)
        outer.setObjectName("LeftPanel")
        outer.setStyleSheet(f"QWidget#LeftPanel {{ background: {C.DARK}; border-right: 1px solid {C.BORDER}; }}")
        ov = QVBoxLayout(outer)
        ov.setContentsMargins(0, 0, 0, 0)
        ov.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: transparent; width: 5px; margin: 4px 1px; }}
            QScrollBar::handle:vertical {{ background: {C.BORDER_B}; border-radius: 2px; min-height: 20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
        """)
        inner = QWidget()
        inner.setObjectName("LeftInner")
        inner.setStyleSheet("QWidget#LeftInner { background: transparent; }")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(10, 10, 10, 6)
        lay.setSpacing(7)
        scroll.setWidget(inner)
        ov.addWidget(scroll, 1)

        # título: SISTEMA ········ Windows
        top = QHBoxLayout()
        top.setSpacing(6)
        _hf = QFont(FONT_MAIN, 7, QFont.Weight.Bold)
        _hf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.6)
        hdr = QLabel("SISTEMA")
        hdr.setFont(_hf)
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        top.addWidget(hdr)
        top.addStretch(1)
        os_name = {"Windows": "Windows", "Darwin": "macOS", "Linux": "Linux"}.get(_OS, _OS)
        chip = QLabel(f"●  {os_name}")
        chip.setFont(QFont(FONT_MAIN, 7, QFont.Weight.DemiBold))
        chip.setStyleSheet(
            f"color: {C.GREEN}; background: {C.PRI_GHO}; border: 1px solid {C.BORDER};"
            " border-radius: 8px; padding: 1px 8px;")
        chip.setToolTip("Sistema operacional detectado")
        top.addWidget(chip)
        lay.addLayout(top)

        # CPU + memória
        card = QFrame()
        card.setObjectName("MetricCard")
        card.setStyleSheet(
            f"QFrame#MetricCard {{ border: 1px solid {C.BORDER}; border-radius: 12px;"
            f" background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {C.PANEL2}, stop:1 {C.PANEL}); }}")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(4, 8, 4, 6)
        cv.setSpacing(0)
        rings = QHBoxLayout()
        rings.setSpacing(0)
        self._bar_cpu = RingGauge("CPU", None)
        self._bar_mem = RingGauge("MEMÓRIA", C.GREEN)
        self._bar_cpu.setToolTip("Uso do processador agora")
        self._bar_mem.setToolTip("Memória RAM em uso (usada/total)")
        rings.addWidget(self._bar_cpu)
        rings.addWidget(self._bar_mem)
        cv.addLayout(rings)
        lay.addWidget(card)

        # rede, GPU e temperatura (gráfico dos últimos ~80 s)
        lines = QFrame()
        lines.setObjectName("MetricLines")
        lines.setStyleSheet(
            f"QFrame#MetricLines {{ border: 1px solid {C.BORDER}; border-radius: 12px;"
            f" background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {C.PANEL2}, stop:1 {C.PANEL}); }}")
        lv = QVBoxLayout(lines)
        lv.setContentsMargins(9, 7, 9, 7)
        lv.setSpacing(5)
        self._bar_net = SparkMetric("REDE", C.GREEN)
        self._bar_gpu = SparkMetric("GPU", C.VIOLET)
        self._bar_tmp = SparkMetric("TEMPERATURA", "#ff7a59")
        self._bar_net.setToolTip("Tráfego de rede: baixando e enviando")
        self._bar_gpu.setToolTip("Uso da placa de vídeo (NVIDIA) e da memória de vídeo")
        self._bar_tmp.setToolTip("Temperatura. Usa o sensor da CPU; se o Windows não o liberar, "
                                 "usa o da placa NVIDIA.\nPara ver a da CPU em qualquer PC, "
                                 "deixe o LibreHardwareMonitor aberto.")
        for bar in (self._bar_net, self._bar_gpu, self._bar_tmp):
            lv.addWidget(bar)
        lay.addWidget(lines)

        # tempo ligado
        self._uptime_card = UptimeCard()
        lay.addWidget(self._uptime_card)

        # processos
        pframe = QFrame()
        pframe.setObjectName("ProcCard")
        pframe.setStyleSheet(
            f"QFrame#ProcCard {{ border: 1px solid {C.BORDER}; border-radius: 12px;"
            f" background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {C.PANEL2}, stop:1 {C.PANEL}); }}")
        pv = QVBoxLayout(pframe)
        pv.setContentsMargins(9, 6, 9, 6)
        self._proc_list = ProcessList()
        pv.addWidget(self._proc_list)
        lay.addWidget(pframe)
        lay.addStretch(1)

        # cartão de ESTADO (muda com o assistente: ouvindo, pensando, falando, mudo...)
        foot = QWidget()
        fl = QVBoxLayout(foot)
        fl.setContentsMargins(10, 2, 10, 8)
        self._status_card = StatusCard(APP_VERSION.replace("NEXUS ", ""))
        self._status_card._on_click = self._open_isa_panel
        fl.addWidget(self._status_card)
        ov.addWidget(foot)
        return outer

    def _build_right_panel(self) -> QWidget:
        """Coluna da direita (visual 1.2): CONVERSA em balões, ENVIAR ARQUIVO
        compacto e COMANDO com a caixa de texto e dois botões lado a lado."""
        w = QWidget()
        w.setFixedWidth(_RIGHT_W)
        w.setObjectName("RightPanel")
        w.setStyleSheet(f"QWidget#RightPanel {{ background: {C.DARK}; border-left: 1px solid {C.BORDER}; }}")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        def _sec(txt):
            f = QFont(FONT_MAIN, 7, QFont.Weight.DemiBold)
            f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.5)
            l = QLabel(txt)
            l.setFont(f)
            l.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            return l

        def _mini(txt, tip, fn):
            b = QPushButton(txt)
            b.setFixedHeight(22)
            b.setFont(QFont(FONT_MAIN, 7, QFont.Weight.DemiBold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(tip)
            b.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 11px; padding: 0 9px; }}
                QPushButton:hover {{ color: {C.PRI}; border-color: {C.PRI_DIM}; }}
            """)
            b.clicked.connect(fn)
            return b

        head = QHBoxLayout()
        head.setSpacing(5)
        head.addWidget(_sec("CONVERSA"))
        self._chat_count = QLabel("")
        self._chat_count.setFont(QFont(FONT_MAIN, 7))
        self._chat_count.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        head.addWidget(self._chat_count)
        head.addStretch(1)
        head.addWidget(_mini("⧉ Copiar", "Copiar a conversa para a área de transferência", self._copy_chat))
        head.addWidget(_mini("Limpar", "Limpar a conversa da tela (o NEXUS continua lembrando)",
                             self._clear_chat_view))
        lay.addLayout(head)

        self._log = ChatLog()
        self._log._sig.connect(lambda _t: QTimer.singleShot(50, self._update_chat_count))
        lay.addWidget(self._log, stretch=1)

        lay.addSpacing(2)
        lay.addWidget(_sec("ENVIAR ARQUIVO"))
        self._drop_zone = FileDropZone()
        self._drop_zone.file_selected.connect(self._on_file_selected)
        lay.addWidget(self._drop_zone)

        # Mantido para quem ainda usa o texto de ajuda (fica escondido no visual novo)
        self._file_hint = QLabel("")
        self._file_hint.hide()

        lay.addSpacing(2)
        lay.addWidget(_sec("COMANDO"))
        lay.addLayout(self._build_input_row())

        acoes = QHBoxLayout()
        acoes.setSpacing(6)
        self._interrupt_btn = QPushButton()
        self._interrupt_btn.setFixedHeight(32)
        self._interrupt_btn.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        self._interrupt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._interrupt_btn.setToolTip("Faz o NEXUS parar de falar na hora")
        self._interrupt_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL2}; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 16px;
            }}
            QPushButton:hover {{
                color: {C.MUTED_C}; border: 1px solid {C.MUTED_C};
            }}
            QPushButton:pressed {{ background: #1c0e14; }}
        """)
        self._interrupt_btn.clicked.connect(self._do_interrupt)
        acoes.addWidget(self._interrupt_btn, 1)

        self._mute_btn = QPushButton()
        self._mute_btn.setFixedHeight(32)
        self._mute_btn.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        self._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_btn.clicked.connect(self._toggle_mute)
        acoes.addWidget(self._mute_btn, 1)
        lay.addLayout(acoes)
        self._refresh_shortcut_labels()
        self._style_mute_btn()

        return w

    def _build_quick_drawer(self) -> QWidget:
        """Floating overlay panel shown when the ⚙ header button is toggled."""
        _BTN_STYLE_PRI = f"""
            QPushButton {{
                background: {C.PANEL2}; color: {C.PRI};
                border: 1px solid {C.BORDER}; border-radius: 6px;
                text-align: left; padding: 0 9px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.PRI}; }}
        """
        _BTN_STYLE_DIM = f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 6px;
                text-align: left; padding: 0 9px;
            }}
            QPushButton:hover {{ color: {C.PRI}; border-color: {C.BORDER_B}; }}
        """

        self._BTN_PRI, self._BTN_DIM = _BTN_STYLE_PRI, _BTN_STYLE_DIM
        w = QWidget(self.centralWidget())
        w.setObjectName("QuickDrawer")
        w.setStyleSheet(f"""
            QWidget#QuickDrawer {{
                background: {C.DARK};
                border: 1px solid {C.BORDER_B};
                border-top: none;
                border-radius: 0 0 6px 6px;
            }}
        """)
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(3)

        hdr = QLabel("◈  SETUP")
        _hf = QFont(FONT_MAIN, 7, QFont.Weight.Bold)
        _hf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.2)
        hdr.setFont(_hf)
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent; "
                          f"border-bottom: 1px solid {C.BORDER}; padding-bottom: 5px;")
        lay.addWidget(hdr)

        for i, (grupo, itens) in enumerate(SettingsPanelOverlay.MENU_GROUPS):
            # título de cada grupo (pequeno, discreto) para o menu ler em ordem
            gl = QLabel(grupo)
            _gf = QFont(FONT_MAIN, 6, QFont.Weight.Bold)
            _gf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.8)
            gl.setFont(_gf)
            gl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; padding: 0 2px;")
            lay.addSpacing(6 if i else 2)
            lay.addWidget(gl)
            for tab, label in itens:
                # a Configuração do usuário é a entrada principal: em destaque
                b = MenuButton(ICONE_SETUP.get(tab, ""), label, "primario" if tab == "usuario" else "normal")
                b.clicked.connect(lambda _=False, t=tab: self._pick_setup_option(t))
                lay.addWidget(b)

        lay.addSpacing(8)

        upd = MenuButton(ICONE_SETUP["atualizar"], "ATUALIZAR", "destaque")
        upd.clicked.connect(self._pick_update)
        lay.addWidget(upd)

        return w

    def _build_controls_drawer(self) -> QWidget:
        """The switches that get flicked every day, in their own panel."""
        w = QWidget(self.centralWidget())
        w.setObjectName("QuickDrawer")
        w.setStyleSheet(self._quick_drawer.styleSheet())
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(6)

        hdr = QLabel("◈  CONTROLES")
        _hf = QFont(FONT_MAIN, 7, QFont.Weight.Bold)
        _hf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.2)
        hdr.setFont(_hf)
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent; "
                          f"border-bottom: 1px solid {C.BORDER}; padding-bottom: 5px;")
        lay.addWidget(hdr)

        def _row(button, style=None, height=ControlButton.H):
            # (2.2) botões desenhados à mão: ícone vetorial + nome + pílula de estado.
            # O estilo antigo (style) é ignorado de propósito; o estado vem do texto.
            button.setFixedHeight(height)
            lay.addWidget(button)
            return button

        fs_btn = _row(ControlButton(f"⛶  TELA CHEIA  [{QB.nome_da_tecla(QB.tecla('shortcut_fullscreen'))}]"), self._BTN_DIM)
        self._fs_btn = fs_btn
        fs_btn.clicked.connect(self._toggle_fullscreen)

        self._brief_btn = _row(ControlButton())
        self._brief_btn.clicked.connect(self._toggle_brief)

        self._wake_btn = _row(ControlButton())
        self._wake_btn.clicked.connect(self._toggle_wake_word)
        self._wake_sleep_btn = _row(ControlButton())
        self._wake_sleep_btn.clicked.connect(self._tap_wake_manual)
        # Neutral until the real state lands from the background warm-up.
        self._wake_btn.setText("🎙  PALAVRA DE ATIVAÇÃO")
        self._wake_sleep_btn.hide()

        self._ptt_btn = _row(ControlButton())
        self._ptt_btn.clicked.connect(self._toggle_ptt)
        self._refresh_talk_btns()

        self._hud_btn = _row(ControlButton())
        self._hud_btn.clicked.connect(self._toggle_hud_style)
        self._refresh_hud_btn()

        w.adjustSize()
        return w

    def _warm_wake_state(self) -> None:
        """Work out the wake-word state off the UI thread, once.

        It used to be resolved when the drawer opened, and that made opening the
        drawer take two seconds the first time — measured at 2.10s, all of it
        `import openwakeword` dragging in onnxruntime behind it. The button
        count had nothing to do with it; the Qt thread was simply waiting on an
        import. Afterwards the same check costs about a millisecond, so it only
        ever needed to happen somewhere other than in front of the user.
        """
        def work():
            try:
                self._wake_state()
            except Exception:
                _engolida("ui/main_window.py:1515")
            self._wake_btns_sig.emit()
        threading.Thread(target=work, daemon=True, name="wake-state-warm").start()

    def _toggle_drawer(self, checked: bool):
        if checked:
            self._close_controls()
            self._position_quick_drawer()
            self._quick_drawer.show()
            self._quick_drawer.raise_()
        else:
            self._quick_drawer.hide()

    def _toggle_controls(self, checked: bool):
        if checked:
            self._close_setup()
            self._refresh_wake_btns()   # cheap now: the state was warmed at boot
            self._position_ctrl_drawer()
            self._ctrl_drawer.show()
            self._ctrl_drawer.raise_()
        else:
            self._ctrl_drawer.hide()

    def _close_setup(self):
        if hasattr(self, "_quick_drawer"):
            self._quick_drawer.hide()
        if hasattr(self, "_drawer_btn"):
            self._drawer_btn.setChecked(False)

    def _close_controls(self):
        if hasattr(self, "_ctrl_drawer"):
            self._ctrl_drawer.hide()
        if hasattr(self, "_ctrl_btn"):
            self._ctrl_btn.setChecked(False)

    def _place_drawer(self, drawer, left: int, width: int = 220):
        _W = width
        drawer.setFixedWidth(_W)
        drawer.adjustSize()
        drawer.setGeometry(left, 54, _W, drawer.sizeHint().height())

    def _position_quick_drawer(self):
        if hasattr(self, "_quick_drawer"):
            self._place_drawer(self._quick_drawer, 12, 244)

    def _position_ctrl_drawer(self):
        # Under its own header button rather than under the other one's.
        if hasattr(self, "_ctrl_drawer"):
            left = 12
            try:
                left = max(12, self._ctrl_btn.mapTo(self.centralWidget(),
                                                    QPoint(0, 0)).x() - 8)
            except Exception:
                _engolida("ui/main_window.py:1568")
            self._place_drawer(self._ctrl_drawer, left, 268)

    def _build_input_row(self) -> QHBoxLayout:
        """Caixa de comando (visual 1.2): uma pílula só, com o texto e o botão
        de enviar dentro dela."""
        row = QHBoxLayout(); row.setSpacing(0)
        box = QFrame()
        box.setObjectName("CmdBox")
        box.setStyleSheet(f"""
            QFrame#CmdBox {{ background: {C.PANEL2}; border: 1px solid {C.BORDER_B}; border-radius: 20px; }}
        """)
        box.setFixedHeight(42)
        h = QHBoxLayout(box)
        h.setContentsMargins(14, 3, 4, 3)
        h.setSpacing(6)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Digite um comando ou pergunta…")
        self._input.setFont(QFont(FONT_MAIN, 10))
        self._input.setStyleSheet(f"""
            QLineEdit {{ background: transparent; color: {C.WHITE}; border: none; padding: 0; }}
        """)
        self._input.returnPressed.connect(self._send)
        self._input.textChanged.connect(self._on_cmd_text)
        h.addWidget(self._input, 1)

        self._send_btn = QPushButton("➤")
        self._send_btn.setFixedSize(34, 34)
        self._send_btn.setFont(QFont(FONT_MAIN, 11, QFont.Weight.Bold))
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setToolTip("Enviar (Enter)")
        self._send_btn.setStyleSheet(f"""
            QPushButton {{ background: {C.PRI}; color: {C.BG}; border: none; border-radius: 17px; }}
            QPushButton:hover {{ background: {C.WHITE}; }}
            QPushButton:disabled {{ background: {C.BORDER_B}; color: {C.TEXT_DIM}; }}
        """)
        self._send_btn.clicked.connect(self._send)
        self._send_btn.setEnabled(False)
        h.addWidget(self._send_btn)
        self._cmd_box = box
        row.addWidget(box)
        return row

    def _on_cmd_text(self, text: str) -> None:
        self._send_btn.setEnabled(bool(text.strip()))
        self._cmd_box.setStyleSheet(f"""
            QFrame#CmdBox {{ background: {C.PANEL2}; border: 1px solid {C.PRI_DIM if text else C.BORDER_B};
                border-radius: 20px; }}
        """)

    # ── painel de conteúdo rico (1.5) ────────────────────────────────────────
    # Markdown só quando o texto tem sinais claros dele (título, tabela, lista,
    # **negrito**, link). O resto continua texto puro, exatamente como antes.
    _MD_SINAIS = None

    # ── document review ──────────────────────────────────────────────────────
    # Rendered as rich text into the content panel that already exists, rather
    # than into a panel of its own. A review is read, not clicked, so QTextEdit
    # gives scrolling, selection and copy for nothing, and the HUD gains no
    # widget it has to lay out. Severity decides colour and order here because
    # that is presentation; the plugin supplies no styling and knows no palette,
    # which is also what lets a re-theme repaint a review correctly.

    # Severity is marked by a symbol and a colour, not by a word. The findings
    # themselves are in the user's language, and "[SERIOUS]" sitting inside a
    # Turkish sentence is the kind of seam this project tries not to have —
    # while translating the tag would mean a table per language, which is worse.
    # A shape carries it in every language, and shape plus colour still reads
    # for someone who cannot separate red from amber. What the marks mean
    # arrives the way everything else does: NEXUS says it out loud.
    _REVIEW_MARKS = {"serious": ("RED", "▲"), "caution": ("ACC2", "●"), "note": ("PRI_DIM", "·")}

    # ── quiz panel ───────────────────────────────────────────────────────────
    # An interactive twin of the content panel. The plugin only ever hands over
    # questions; everything about asking, marking and reporting happens here,
    # and the finished result is pushed back into the conversation the same way
    # a dropped file is — as a message NEXUS reads and responds to. That keeps
    # the tool call short (it returns the moment the board is up) and leaves the
    # talking to the assistant, in the user's own language.

    def _build_footer(self) -> QWidget:
        wrap = QWidget()
        wrap.setStyleSheet(f"background: {C.DARK};")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        w = QWidget()
        w.setFixedHeight(22)
        w.setStyleSheet(f"background: {C.DARK}; border-top: 1px solid {C.BORDER};")
        lay = QHBoxLayout(w); lay.setContentsMargins(14, 0, 14, 0)

        def _fl(txt, color=C.TEXT_DIM):
            l = QLabel(txt)
            _ff = QFont(FONT_MAIN, 8)
            _ff.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1)
            l.setFont(_ff)
            l.setStyleSheet(f"color: {color}; background: transparent;")
            return l

        self._footer_keys = _fl("")
        lay.addWidget(self._footer_keys)
        lay.addStretch()
        lay.addWidget(_fl("NEXUS Ultra 2026  ·  Desenvolvido por André Luiz Lima Menezes  ·  2026"))
        v.addWidget(w)
        return wrap

    def _on_file_selected(self, path: str):
        self._current_file = path
        p    = Path(path)
        cat  = _file_category(p)
        icon, _ = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size = _fmt_size(p.stat().st_size)
        self._file_hint.setText(f"{icon}  {p.name}  ·  {size}  ·  diga ao {self._assistant_name} o que fazer com ele")
        self._log.append_log(f"FILE: {p.name} ({size}) carregado")
        if self.on_text_command:
            msg = (
                f"[FILE_UPLOADED] path={path} | name={p.name} | "
                f"type={p.suffix.lstrip('.')} | size={size} | "
                f"Briefly tell the user you can see the file '{p.name}' "
                f"({size}) has been uploaded and ask what they'd like to do with it."
            )
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

    def notify_phone_connected(self) -> None:
        if self._remote_overlay and self._remote_overlay.isVisible():
            self._remote_overlay.mark_connected()

    def _open_remote(self):
        if not self.on_remote_clicked:
            self._log.append_log("SYS: O painel do celular não está rodando — controle remoto indisponível.")
            return
        result = self.on_remote_clicked()
        if not result:
            self._log.append_log("SYS: Não consegui gerar a chave do celular.")
            return
        url    = result[0]
        key    = result[1]
        auto   = result[2] if len(result) >= 3 else ""
        manual = result[3] if len(result) >= 4 else url
        if self._remote_overlay:
            self._remote_overlay._do_close()
        cw  = self.centralWidget()
        ow, oh = RemoteKeyOverlay._OW, RemoteKeyOverlay._OH
        ov  = RemoteKeyOverlay(url, key, auto_login_url=auto, manual_url=manual,
                               expiry_secs=600, parent=cw)
        ov.set_new_key_callback(self.on_remote_clicked)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.closed.connect(lambda: setattr(self, '_remote_overlay', None))
        ov.show()
        self._remote_overlay = ov
        self._log.append_log(f"SYS: Chave do celular gerada — manual: {manual or url}")

    # ── Auto-start ──────────────────────────────────────────────────────────────

    def _toggle_brief(self):
        from memory.config_manager import get_brief_enabled, save_brief_enabled
        new_val = not get_brief_enabled()
        save_brief_enabled(new_val)
        self._update_brief_btn(new_val)

    # ── Wake word settings ───────────────────────────────────────────────────

    def _wake_state(self) -> dict:
        """Combined state for the two wake-word buttons. Readiness is a cheap,
        deterministic on-disk check now (see core.wake_word.is_ready), so there
        is nothing to cache — the button never flickers to a stale value."""
        if self.wake_get_state:
            try:
                s = self.wake_get_state()
                return {"ready": bool(s.get("ready")),
                        "enabled": bool(s.get("enabled")),
                        "awake": bool(s.get("awake"))}
            except Exception:
                _engolida("ui/main_window.py:2390")
        # Before NexusLive has wired its callback (drawer built at startup).
        ready, enabled = False, False
        try:
            from core.wake_word import is_ready
            from memory.config_manager import get_wake_word_enabled
            ready, enabled = is_ready(), get_wake_word_enabled()
        except Exception:
            _engolida("ui/main_window.py:2398")
        return {"ready": ready, "enabled": enabled, "awake": True}

    def _refresh_wake_btns(self):
        if not hasattr(self, '_wake_btn'):
            return
        st = self._wake_state()
        _on = f"""
            QPushButton {{ background: #001a08; color: {C.GREEN};
                border: 1px solid {C.GREEN_D}; border-radius: 3px;
                text-align: left; padding: 0 8px; }}
            QPushButton:hover {{ background: #002010; }}"""
        _off = f"""
            QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 3px;
                text-align: left; padding: 0 8px; }}
            QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}"""
        self._wake_btn.setEnabled(True)
        if not st["ready"]:
            self._wake_btn.setText("⬇  PALAVRA DE ATIVAÇÃO: BAIXAR")
            self._wake_btn.setStyleSheet(_off)
            self._wake_sleep_btn.hide()
        elif st["enabled"]:
            self._wake_btn.setText("🎙  PALAVRA DE ATIVAÇÃO: LIGADA")
            self._wake_btn.setStyleSheet(_on)
            self._wake_sleep_btn.show()
            self._wake_sleep_btn.setText("😴  DORMIR AGORA" if st["awake"] else "👂  ACORDAR AGORA")
            self._wake_sleep_btn.setStyleSheet(_off)
        else:
            self._wake_btn.setText("🎙  PALAVRA DE ATIVAÇÃO: DESLIGADA")
            self._wake_btn.setStyleSheet(_off)
            self._wake_sleep_btn.hide()

    def _refresh_talk_btns(self):
        """Repaint the push-to-talk row from the saved setting."""
        if not hasattr(self, "_ptt_btn"):
            return
        from core.hotkey import chord_label
        from memory.config_manager import get_push_to_talk_enabled
        _on = f"""
            QPushButton {{ background: #001a08; color: {C.GREEN};
                border: 1px solid {C.GREEN_D}; border-radius: 3px;
                text-align: left; padding: 0 8px; }}
            QPushButton:hover {{ background: #002010; }}"""
        _off = f"""
            QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 3px;
                text-align: left; padding: 0 8px; }}
            QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}"""

        ptt = get_push_to_talk_enabled()
        self._ptt_btn.setText(f"🎚  FALAR SEGURANDO: {chord_label()}" if ptt
                              else "🎚  FALAR SEGURANDO: DESLIGADO")
        self._ptt_btn.setStyleSheet(_on if ptt else _off)
        self._ptt_btn.setToolTip(
            "O microfone fica fechado até você segurar a tecla — nada é enviado "
            "enquanto você não estiver segurando." if ptt
            else "Segure uma tecla para falar, em vez de transmitir o microfone o tempo todo.")


    def _refresh_hud_btn(self):
        from memory.config_manager import get_hud_style
        from .hud import HUD_STYLE_INFO
        style = f"""
            QPushButton {{ background: {C.PANEL2}; color: {C.PRI};
                border: 1px solid {C.BORDER_A}; border-radius: 8px;
                text-align: left; padding: 0 10px; }}
            QPushButton:hover {{ color: {C.WHITE}; border: 1px solid {C.BORDER_B}; }}"""
        atual = get_hud_style()
        icone, nome, desc = HUD_STYLE_INFO.get(atual, HUD_STYLE_INFO["orb"])
        self._hud_btn.setText(f"{icone}  VISUAL DO HUB: {nome}")
        self._hud_btn.setToolTip(f"{desc}.\nClique para escolher entre os 20 visuais do hub.")
        self._hud_btn.setStyleSheet(style)

    def _toggle_hud_style(self):
        """Abre a lista de visuais do hub (os clássicos e os dez novos do Ultra 2026)."""
        from PyQt6.QtGui import QAction, QCursor
        from PyQt6.QtWidgets import QMenu
        from memory.config_manager import get_hud_style
        from .hud import HUD_STYLE_INFO
        atual = get_hud_style()
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background: {C.PANEL}; color: {C.TEXT}; border: 1px solid {C.BORDER_B};
                border-radius: 10px; padding: 6px; }}
            QMenu::item {{ padding: 7px 18px 7px 12px; border-radius: 7px; }}
            QMenu::item:selected {{ background: {C.PRI_GHO}; color: {C.WHITE}; }}
            QMenu::separator {{ height: 1px; background: {C.BORDER}; margin: 5px 8px; }}
        """)
        titulo = QAction("VISUAL DO HUB", menu)
        titulo.setEnabled(False)
        menu.addAction(titulo)
        menu.addSeparator()
        from .hud_novos import NOVOS_INFO
        grupos = (("NOVOS · 3.6", tuple(NOVOS_INFO)),)
        for titulo_g, chaves in grupos:
            menu.addSeparator()
            _t2 = QAction(titulo_g, menu)
            _t2.setEnabled(False)
            menu.addAction(_t2)
            for chave in chaves:
                icone, nome, desc = HUD_STYLE_INFO[chave]
                marca = "●" if chave == atual else "○"
                ac = QAction(f"{marca}  {icone}  {nome}   —   {desc}", menu)
                ac.triggered.connect(lambda _=False, k=chave: self._set_hud_style(k))
                menu.addAction(ac)
        menu.addSeparator()
        aj = QAction("🎛  Ajustar cor e velocidade deste visual…", menu)
        aj.triggered.connect(self._ajustar_visual)
        menu.addAction(aj)
        if self._hud_btn.isVisible():
            pos = self._hud_btn.mapToGlobal(QPoint(0, self._hud_btn.height()))
        else:
            pos = QCursor.pos()
        menu.exec(pos)

    def _aplicar_ambiente(self):
        """Perfil trocou (Trabalho, Casa, Estudo…): aplica a cor e o visual do hub que ele gravou na configuração."""
        try:
            cfg = _read_full_config()
            cor = (cfg.get("ui_color") or "").strip().lower() or DEFAULT_UI_COLOR
            antes = current_palette()
            if apply_ui_accent(cor):
                retheme_all_widgets(antes, current_palette())
            from memory.config_manager import get_hud_style
            self.hud.hud_style = get_hud_style()
            self.hud.recarregar_ajustes()
            self.hud._pulsos = []
            self.hud.update()
            self._refresh_hud_btn()
        except Exception as e:
            print(f"[Ambiente] ⚠️ {e}")

    def _ajustar_visual(self):
        """Editor do hub (3.7): cor e velocidade do visual atual, com prévia ao vivo."""
        from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout
        from core import hub_ajustes as HA
        estilo = self.hud.hud_style
        aj = HA.obter(estilo)
        dlg = QDialog(self)
        dlg.setWindowTitle("Ajustar visual do hub")
        dlg.setStyleSheet(f"QDialog {{ background: {C.PANEL}; }} QLabel {{ color: {C.TEXT}; }}")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(f"<b>{estilo}</b> — cor e velocidade"))
        def linha(rotulo, mn, mx, v):
            lay.addWidget(QLabel(rotulo))
            s = QSlider(Qt.Orientation.Horizontal)
            s.setRange(mn, mx)
            s.setValue(v)
            lay.addWidget(s)
            return s
        sm = linha("Cor", 0, 359, aj.get("matiz", 0))
        sv = linha("Velocidade", int(HA.VEL_MIN * 100), int(HA.VEL_MAX * 100), int(aj.get("velocidade", 1.0) * 100))
        usar = QPushButton("Usar a cor do tema" if "matiz" in aj else "Usando a cor do tema (mexa na barra para trocar)")
        usar.setCheckable(True)
        usar.setChecked("matiz" not in aj)
        lay.addWidget(usar)
        estado = {"matiz": aj.get("matiz")}
        def aplicar(*_):
            estado["matiz"] = None if usar.isChecked() else sm.value()
            HA.salvar(estilo, estado["matiz"], sv.value() / 100)
            self.hud.recarregar_ajustes()
            self.hud.update()
        def mexeu_cor(_v):
            usar.setChecked(False)
            aplicar()
        sm.valueChanged.connect(mexeu_cor)
        sv.valueChanged.connect(aplicar)
        usar.toggled.connect(aplicar)
        linha_bt = QHBoxLayout()
        rest = QPushButton("Restaurar padrão")
        ok = QPushButton("Pronto")
        def restaurar():
            HA.restaurar(estilo)
            self.hud.recarregar_ajustes()
            dlg.accept()
        rest.clicked.connect(restaurar)
        ok.clicked.connect(dlg.accept)
        linha_bt.addWidget(rest)
        linha_bt.addWidget(ok)
        lay.addLayout(linha_bt)
        dlg.exec()

    def _set_hud_style(self, want: str):
        """Troca o visual do hub na hora e guarda a escolha."""
        from memory.config_manager import HUD_STYLES, save_hud_style
        from .hud import HUD_STYLE_INFO
        if want not in HUD_STYLES:
            want = "galaxy"
        save_hud_style(want)
        try:
            self.hud.hud_style = want
            self.hud.recarregar_ajustes()
            self.hud._pulsos = []
            self.hud.update()
        except Exception:
            _engolida("ui/main_window.py:2594")
        self._refresh_hud_btn()
        self._log.append_log(f"SYS: Visual do hub: {HUD_STYLE_INFO[want][1].lower()}.")

    # ── Customization ────────────────────────────────────────────────────────────

    def _setup_tray(self):
        """Bandeja do sistema, quando a preferência minimize_to_tray estiver ligada."""
        try:
            from core import preferences as _P
            if not _P.get("minimize_to_tray"):
                return
        except Exception:
            return
        from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
        from PyQt6.QtGui import QIcon
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        ico = _base_dir() / "config" / "nexus.ico"
        tray = QSystemTrayIcon(QIcon(str(ico)) if ico.exists() else self.windowIcon(), self)
        menu = QMenu()
        menu.addAction("Mostrar").triggered.connect(self._show_from_tray)
        menu.addAction("Sair").triggered.connect(self._quit_from_tray)
        tray.setContextMenu(menu)
        tray.activated.connect(lambda reason: self._show_from_tray()
                               if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        tray.show()
        self._tray = tray

    def _show_from_tray(self):
        self.showNormal()
        self.activateWindow()

    def _quit_from_tray(self):
        self._really_quit = True
        if self._tray is not None:
            self._tray.hide()
        self.close()

    def closeEvent(self, e):
        if self._tray is not None and not getattr(self, "_really_quit", False):
            e.ignore()
            self.hide()
            return
        super().closeEvent(e)

    def _open_activity_log(self):
        from .overlays.activity_log import ActivityLogOverlay
        if getattr(self, "_log_overlay", None):
            self._log_overlay.hide()
        ov = ActivityLogOverlay(parent=self.centralWidget())
        self._centre_overlay(ov)
        self._log_overlay = ov

    def _update_system(self):
        """ATUALIZAR (1.4.1): confere o GitHub e instala a versão nova com um clique."""
        try:
            from .overlays.update import UpdateOverlay, reiniciar_nexus
            old = getattr(self, "_update_overlay", None)
            if old is not None:
                try:
                    old._fechar()
                except RuntimeError:
                    pass
            ov = UpdateOverlay(parent=self.centralWidget(), log=self.write_log,
                               escolher_zip=self._update_from_zip, reiniciar=reiniciar_nexus)
            self._centre_overlay(ov)
            self._update_overlay = ov
        except Exception as e:
            self._log.append_log(f"ERR: A janela de atualização não abriu — {e}")
            self._update_from_zip()

    def _organizar_area_de_trabalho(self) -> None:
        """1.4.2 — botão 🗂 Organizar: mostra quantos arquivos vão para pastas e organiza."""
        try:
            from core.organizador import plano, organizar
            pl = plano()
        except Exception as e:
            self._log.append_log(f"ERR: Não consegui ler a área de trabalho — {e}")
            return
        n = len(pl["mover"])
        if not n:
            self._log.append_log("SYS: 🗂 A área de trabalho já está organizada: não há arquivos soltos.")
            return
        resp = QMessageBox.question(
            self, "Organizar a área de trabalho",
            f"Guardar {n} arquivo(s) soltos da área de trabalho em pastas por tipo "
            "(Imagens, Documentos, Planilhas…)?\n\nAtalhos e pastas ficam onde estão. "
            "Dá para desfazer dizendo “desfaz a organização”.")
        if resp != QMessageBox.StandardButton.Yes:
            return

        def _trabalho():
            self.write_log(f"SYS: 🗂 {organizar()}")
        threading.Thread(target=_trabalho, daemon=True, name="organizar").start()

    def _ocultar_para_captura(self, ocultar: bool) -> None:
        """1.4.2 — a visão fotografa a tela: o NEXUS sai da frente e volta."""
        if ocultar:
            if self.isMinimized():
                self._estado_antes_captura = None
                return
            self._estado_antes_captura = self.windowState()
            self.showMinimized()
        else:
            estado = getattr(self, "_estado_antes_captura", None)
            self._estado_antes_captura = None
            if estado is None:
                return
            self.setWindowState(estado & ~Qt.WindowState.WindowMinimized)
            self.show()
            self.raise_()
            self.activateWindow()

    def _restart_app(self) -> None:
        """Reinicia o NEXUS (pedido por voz depois de uma atualização)."""
        from .overlays.update import reiniciar_nexus
        self._log.append_log("SYS: ↻ Reiniciando o NEXUS…")
        QTimer.singleShot(1500, reiniciar_nexus)

    def _update_from_zip(self):
        """Instalar um pacote .zip baixado à mão: mostra o que muda, confirma e aplica."""
        import shutil
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        from actions import system_update as su
        cur = su.current_version().get("version", "0.0")
        updates_dir = su._base() / "updates"
        updates_dir.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(
            self, f"Pacote de atualização (sistema atual: v{cur})",
            str(updates_dir), "Pacote de atualização (*.zip)")
        if not path:
            return
        info = su.inspect_package(path)
        if not info:
            self._log.append_log("SYS: Esse arquivo não é um pacote de atualização válido.")
            return
        new_v = info["version"]
        if su.is_newer(new_v, cur):
            question = (f"Atualizar de v{cur} para v{new_v}?\n\n{info['notes']}\n\n"
                        "Suas chaves, memória e configurações são preservadas.")
        else:
            question = (f"O pacote é v{new_v}, igual ou mais antigo que o atual (v{cur}). "
                        "Aplicar mesmo assim?")
        answer = QMessageBox.question(self, "Atualizar sistema", question)
        if answer != QMessageBox.StandardButton.Yes:
            return
        dest = updates_dir / Path(path).name
        if Path(path).resolve() != dest.resolve():
            shutil.copy2(path, dest)
        msg = su.apply_package(str(dest))
        self._log.append_log(f"SYS: {msg}")
        QMessageBox.information(self, "Atualizar sistema",
                                msg + "\n\nReinicie o app para concluir.")

    def _pick_update(self):
        """Botão ATUALIZAR do menu SETUP: fecha o menu e abre a atualização."""
        self._close_setup()
        self._update_system()

    # ── Audio devices ────────────────────────────────────────────────────────

    # ── Memory panel ─────────────────────────────────────────────────────────

    # ── clipboard history (shared with ClipOverlay) ──────────────────────────

    def _on_clipboard_change(self):
        """Capture every copy into the in-memory history (max 20).

        Our own 'copy back' click also changes the clipboard; _clip_self
        marks that so restoring an item doesn't duplicate it."""
        if getattr(self, "_clip_self", False):
            self._clip_self = False
            return
        try:
            text = QApplication.clipboard().text()
        except Exception:
            return
        text = text.strip()
        if not text or len(text) > 5000:
            return
        hist = getattr(self, "_clip_history", None)
        if hist is None:
            hist = self._clip_history = []
        if text in hist:
            hist.remove(text)
        hist.insert(0, text)
        while len(hist) > 20:
            hist.pop()

    # ── Irreversible-action confirmation ─────────────────────────────────────

    # ── Clipboard intelligence ───────────────────────────────────────────────────

    def _on_clipboard_changed(self):
        try:
            text = QApplication.clipboard().text().strip()
            if len(text) >= 10:
                self._clipboard_sig.emit(text)
        except Exception:
            _engolida("ui/main_window.py:3313")

    def _show_clipboard_panel(self, text: str):
        self._clipboard_panel.show_clipboard(text)
        self._position_clipboard_panel()

    def _position_clipboard_panel(self):
        cw = self.centralWidget()
        pw = ClipboardPanel._W
        ph = self._clipboard_panel.sizeHint().height() or ClipboardPanel._H
        x = (cw.width() - pw) // 2
        y = cw.height() - ph - 6
        self._clipboard_panel.setGeometry(x, y, pw, ph)
        self._clipboard_panel.raise_()

    def _on_clipboard_action(self, cmd: str):
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(cmd,), daemon=True).start()

    # ────────────────────────────────────────────────────────────────────────────

    def _apply_state(self, state: str):
        self.hud.state    = state
        self.hud.speaking = (state == "SPEAKING")
        card = getattr(self, "_status_card", None)
        if card is not None:
            card.set_core("MUTED" if self._muted else state)

    # ── 1.2: conversa, barra rápida, atalhos, notas e lembretes ─────────────

    def write_log(self, text: str) -> None:
        """Escreve na conversa. (Na 1.1 os painéis chamavam isto e o método não
        existia na janela — por isso Notas, Visão, Sistema e Área de
        transferência não abriam.)"""
        self._log.append_log(text)

    def _update_chat_count(self) -> None:
        n = self._log.message_count()
        self._chat_count.setText(f"·  {n} mensage{'m' if n == 1 else 'ns'}" if n else "")

    def _copy_chat(self) -> None:
        texto = self._log.plain_text()
        if texto:
            self._clip_self = True
            QApplication.clipboard().setText(texto)
            self._log.append_log("SYS: Conversa copiada para a área de transferência.")

    def _clear_chat_view(self) -> None:
        self._log.clear_view()
        self._update_chat_count()

    def _focus_command(self) -> None:
        self.activateWindow()
        self._input.setFocus()
        self._input.selectAll()

    # ── 1.4: modo ditado no Bloco de Notas ──────────────────────────────────

    def eventFilter(self, obj, ev):
        try:
            if obj is self.hud and ev.type() == QEvent.Type.Resize:
                self._place_ditado_pill()
        except Exception:
            _engolida("ui/main_window.py:3581")
        return super().eventFilter(obj, ev)
