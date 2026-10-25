"""The main window: layout, HUD, panels, shortcuts, tray, video.

Part of the ui package (split from the old single ui.py)."""
from __future__ import annotations

from ._qt import *  # noqa: F401,F403
from ._base import _base_dir  # noqa: F401
from ._base import API_FILE, APP_PROTOCOL, APP_VERSION, C, CONFIG_DIR, DEFAULT_UI_COLOR, FONT_MAIN, FONT_MONO, _DEFAULT_H, _DEFAULT_W, _LEFT_W, _MIN_H, _MIN_W, _OS, _RIGHT_W, _bg_color, _dt_now, _metrics, _pref_key, _read_full_config, _shortcut_seq, agora, apply_ui_accent, current_palette, data_curta, retheme_all_widgets  # noqa: F401
from ._base import LEGACY_DEFAULT_COLORS, accent2, mix  # noqa: F401
from .hud import HudCanvas, MetricBar  # noqa: F401
from .overlays.customize import CustomizeOverlay  # noqa: F401
from .overlays.panels import AudioDeviceOverlay, ConfirmBanner, MemoryOverlay, PluginManagerOverlay  # noqa: F401
from .overlays.remote import PluginSettingsOverlay, RemoteKeyOverlay  # noqa: F401
from .overlays.settings import SettingsPanelOverlay  # noqa: F401
from .overlays.setup import SetupOverlay  # noqa: F401
from .overlays.licenca import LicencaOverlay  # noqa: F401
from .overlays.tools import ClipOverlay, CommandsOverlay, IntelOverlay, NotesOverlay, VisionOverlay  # noqa: F401
from .widgets import ClipboardPanel, FileDropZone, LogWidget, _CameraPreview, _FILE_ICONS, _file_category, _fmt_size  # noqa: F401
from .modern import (ICONE_SETUP, ChatLog, CompactMetric, ControlButton, GradientLabel, HeaderBar, MenuButton, ProcessList, QuickBar,  # noqa: F401
                     RingGauge, SparkMetric, StatusCard, UptimeCard)
from . import quickbar as QB

class MainWindow(QMainWindow):
    _log_sig        = pyqtSignal(str)
    _state_sig      = pyqtSignal(str)
    _content_sig    = pyqtSignal(str, str)   # (title, text) — thread-safe content display
    _reconfig_sig   = pyqtSignal()           # trigger setup overlay from any thread
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

    def _show_camera_frame(self, img_bytes: bytes):
        """Slot — display camera preview overlay (main thread)."""
        self._cam_preview.show_frame(img_bytes)
        cw = self.centralWidget()
        pw = _CameraPreview._W
        ph = self._cam_preview.height()
        self._cam_preview.setGeometry(
            cw.width() - _RIGHT_W - pw - 12,
            cw.height() - ph - 28,
            pw, ph,
        )

    # --- Live camera stream in HUD area ------------------------------------
    def _on_cam_stream(self, start: bool) -> None:
        if start:
            self._hud_cam_stack.setCurrentIndex(1)
        else:
            self._hud_cam_stack.setCurrentIndex(0)
            self._cam_live_lbl.clear()

    def _on_cam_frame(self, data: bytes) -> None:
        px = QPixmap()
        px.loadFromData(data)
        if not px.isNull():
            w, h = self._cam_live_lbl.width(), self._cam_live_lbl.height()
            if w > 1 and h > 1:
                self._cam_live_lbl.setPixmap(
                    px.scaled(w, h,
                              Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
                )

    def start_camera_stream(self) -> None:
        self._cam_stop.clear()
        self._cam_stream_sig.emit(True)
        t = threading.Thread(target=self._cam_loop, daemon=True, name="cam-stream")
        t.start()

    def _cam_loop(self) -> None:
        try:
            import cv2
            # 2.4.2 — a mesma abertura da foto do Gemini (câmera escolhida, depois as
            # outras, nos dois drivers do Windows); 640×480 basta para a prévia.
            from actions.computer_vision import VisaoErro, abrir_camera
            try:
                cap = abrir_camera(640, 480)
            except VisaoErro as e:
                print(f"[Camera] prévia sem câmera: {e}")
                return
            # warm-up frames
            for _ in range(5):
                cap.read()
            while not self._cam_stop.wait(0.033) and cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 65])
                    self._cam_frame_sig.emit(buf.tobytes())
            cap.release()
        except Exception as e:
            print(f"[Camera] Stream error: {e}")
        finally:
            self._cam_stream_sig.emit(False)

    def stop_camera_stream(self) -> None:
        self._cam_stop.set()

    # --- Video in the HUD area ---------------------------------------------
    #
    # Everything below runs on the Qt thread. Plugins and the assistant reach it
    # through the signals above, the same way every other panel is driven, so a
    # background thread never touches a widget.
    def _on_video_open(self, source: str, title: str, muted: bool,
                       audio_source: str = "") -> None:
        if not HAVE_VIDEO or not self._video_player:
            self.write_log("SYS: Este Qt não tem reprodução de vídeo "
                           "install.")
            return
        # A video and the live camera cannot share the centre of the HUD.
        self._cam_stop.set()

        self._video_title.setText(f"▶  {(title or 'VÍDEO')[:44].upper()}")
        self._video_split = bool(audio_source)
        self._set_video_muted(bool(muted))

        url = (QUrl.fromLocalFile(source) if Path(source).exists()
               else QUrl(source))
        self._video_player.setSource(url)
        if self._video_split:
            self._video_sound.setSource(QUrl(audio_source))
        self._hud_cam_stack.setCurrentIndex(2)
        self._video_on = True
        # Re-run now that the video counts as playing: _set_video_muted ran
        # before this line and saw no video, so its mic check was a no-op.
        self._sync_mic_for_video()
        self._video_player.play()
        if self._video_split:
            self._video_sound.play()
            self._video_sync.start()

    def _fit_video(self, *_a) -> None:
        """Size the picture to the panel, keeping its shape."""
        if not (self._video_item and self._video_widget):
            return
        try:
            native = self._video_item.nativeSize()
            if native.isEmpty():
                return
            view = self._video_widget.viewport().size()
            scale = min(view.width() / native.width(),
                        view.height() / native.height())
            w, h = native.width() * scale, native.height() * scale
            self._video_item.setSize(QSizeF(w, h))
            self._video_scene.setSceneRect(0, 0, w, h)
            self._video_widget.centerOn(self._video_item)
        except Exception:
            pass

    def _on_video_close(self) -> None:
        if self._video_sync:
            self._video_sync.stop()
        for p in (self._video_player, self._video_sound):
            if p:
                p.stop()
                p.setSource(QUrl())
        self._video_split = False
        self._video_on = False
        self._hud_cam_stack.setCurrentIndex(0)
        self._sync_mic_for_video()      # gives the microphone back

    def _set_video_muted(self, muted: bool) -> None:
        """Silence whichever output is carrying the sound for this video."""
        muted = bool(muted)
        if self._video_audio:
            # When the sound is a separate stream this player has none, but
            # muting it too costs nothing and keeps the two paths identical.
            self._video_audio.setMuted(muted)
        if self._video_sound_out:
            self._video_sound_out.setMuted(muted)
        self._sync_video_mute_btn()
        self._sync_mic_for_video()

    def _on_video_mute(self, muted: bool) -> None:
        self._set_video_muted(muted)

    def _sync_mic_for_video(self) -> None:
        """Close the microphone while the video is making sound.

        NEXUS subtracts its OWN output from the microphone — that is what
        core/echo.py does — but a video plays through a different output
        entirely, so the guard has never heard of it and the assistant answers
        the film. There is no arrangement in which an open microphone and a
        loudspeaker in the same room do not do that.

        So the microphone closes for exactly as long as the sound is on, and
        opens again by itself the moment it goes off or the video is closed.
        Only if NEXUS closed it: a microphone the user muted themselves stays
        muted, and pressing the mute key during a video hands the decision back
        to them for good.
        """
        sound_on = bool(self._video_on and self._video_sound_out
                        and not self._video_sound_out.isMuted())
        if sound_on and not self._muted:
            self._video_auto_muted = True
            self._set_muted(True, "The video's sound is on — silence it, close "
                                  "it, or press F4 to talk. Typing still works.")
        elif not sound_on and self._video_auto_muted:
            self._video_auto_muted = False
            self._set_muted(False, "The video is quiet again.")

    def _sync_video_sound(self) -> None:
        """Keep the separate soundtrack in step with the picture.

        Two players started at the same moment do not stay together: they buffer
        independently, and measured on a real stream they were about half a
        second apart after nine seconds. So the sound is nudged back to the
        picture whenever it drifts far enough to hear — and only then, because
        correcting a smaller gap is itself audible.
        """
        if not (self._video_split and self._video_sound and self._video_player):
            return
        try:
            if self._video_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                return
            drift = self._video_sound.position() - self._video_player.position()
            if abs(drift) > 300:
                self._video_sound.setPosition(self._video_player.position())
        except Exception:
            pass

    def _sync_video_mute_btn(self) -> None:
        out = self._video_sound_out if self._video_split else self._video_audio
        muted = bool(out and out.isMuted())
        self._video_mute_btn.setText("🔇  SEM SOM" if muted else "🔊  COM SOM")

    def _toggle_video_mute(self) -> None:
        out = self._video_sound_out if self._video_split else self._video_audio
        if out:
            self._set_video_muted(not out.isMuted())

    def _on_video_error(self, *_a) -> None:
        err = ""
        try:
            err = self._video_player.errorString()
        except Exception:
            pass
        self.write_log(f"SYS: Não deu para tocar o vídeo{(' — ' + err) if err else ''}.")
        self._on_video_close()

    def stop_video(self) -> None:
        self._video_close_sig.emit()

    def video_is_playing(self) -> bool:
        return bool(self._video_on)

    # ------------------------------------------------------------------
    # Icon generation — arc-reactor style, rendered with Pillow
    # ------------------------------------------------------------------
    @staticmethod
    def _build_jarvis_icon(out_path: Path) -> bool:
        """
        Render the NEXUS constellation icon at 4× resolution and downsample
        for crisp results at all sizes. Saves a multi-res .ico to out_path.
        Returns True on success.
        """
        try:
            import math
            import PIL.Image
            import PIL.ImageDraw
            import PIL.ImageFilter
        except ImportError:
            return False

        BG     = (9, 7, 20)
        RING   = (165, 148, 255)
        LINE   = (150, 135, 235)
        STAR   = (240, 238, 255)
        WARM   = (255, 150, 95)       # Betelgeuse
        COOL   = (165, 200, 255)      # Rigel
        GOLD   = (255, 196, 107)      # the belt
        # Nexus, in units of the radius (same figure as core/nexus_hud.py)
        P = {"me": (-0.02, -0.62), "be": (-0.38, -0.42), "bl": (0.34, -0.36),
             "an": (-0.13, 0.04), "al": (0.0, -0.01), "mi": (0.13, -0.07),
             "sa": (-0.28, 0.52), "ri": (0.36, 0.46)}
        LINES = [("me", "be"), ("me", "bl"), ("be", "an"), ("bl", "mi"),
                 ("an", "al"), ("al", "mi"), ("an", "sa"), ("mi", "ri")]

        def _render(sz: int) -> PIL.Image.Image:
            S  = sz * 4                     # draw at 4× then downscale
            img = PIL.Image.new("RGBA", (S, S), (0, 0, 0, 0))
            d   = PIL.ImageDraw.Draw(img)
            cx = cy = S // 2
            R = S // 2 - 2
            d.ellipse([cx-R, cy-R, cx+R, cy+R], fill=(*BG, 255))
            lw = max(2, S // 40)
            d.ellipse([cx-R, cy-R, cx+R, cy+R], outline=(*RING, 230), width=lw)
            xy = {k: (cx + v[0] * R, cy + v[1] * R) for k, v in P.items()}
            if sz >= 32:                    # lines only where they can be seen
                for a_, b_ in LINES:
                    d.line([xy[a_], xy[b_]], fill=(*LINE, 200), width=max(1, S // 70))
            glow = PIL.Image.new("RGBA", (S, S), (0, 0, 0, 0))
            gd = PIL.ImageDraw.Draw(glow)
            for k in ("an", "al", "mi"):
                x, y = xy[k]; g = R * 0.11
                gd.ellipse([x-g, y-g, x+g, y+g], fill=(*GOLD, 120))
            glow = glow.filter(PIL.ImageFilter.GaussianBlur(S // 18))
            img = PIL.Image.alpha_composite(img, glow)
            d = PIL.ImageDraw.Draw(img)
            for k, (x, y) in xy.items():
                col = WARM if k == "be" else COOL if k == "ri" else GOLD if k in ("an", "al", "mi") else STAR
                rr = R * (0.055 if k in ("an", "al", "mi") else 0.065 if k in ("be", "ri") else 0.045)
                if sz < 32:
                    rr *= 1.5
                d.ellipse([x-rr, y-rr, x+rr, y+rr], fill=(*col, 255))
            return img.resize((sz, sz), PIL.Image.LANCZOS)

        try:
            sizes  = [256, 128, 64, 48, 32, 16]
            frames = [_render(s) for s in sizes]
            frames[0].save(
                out_path,
                format="ICO",
                append_images=frames[1:],
                sizes=[(s, s) for s in sizes],
            )
            return True
        except Exception as e:
            print(f"[Shortcut] ⚠️  Icon generation failed: {e}")
            return False

    @staticmethod
    def _create_lnk_windows(lnk: str, target: str, args: str,
                             work_dir: str, icon_loc: str) -> None:
        """
        Create a Windows .lnk shortcut WITHOUT launching PowerShell or cmd.
        Tries win32com (pywin32) first; falls back to wscript.exe + VBScript.
        wscript.exe is a GUI-mode host — it never opens a console window.
        """
        # ── Option 1: pywin32 (pure Python COM, zero subprocess) ──────────
        try:
            from win32com.client import Dispatch   # type: ignore
            sh = Dispatch("WScript.Shell")
            sc = sh.CreateShortCut(lnk)
            sc.TargetPath       = target
            sc.Arguments        = f'"{args}"'
            sc.WorkingDirectory = work_dir
            sc.Description      = "J.A.R.V.I.S AI Assistant"
            sc.IconLocation     = icon_loc
            sc.save()
            return
        except ImportError:
            pass

        # ── Option 2: wscript.exe + VBScript (always available on Windows,
        #    GUI-mode executable — never opens a console window) ────────────
        vbs = "\n".join([
            'Set ws = CreateObject("WScript.Shell")',
            f'Set sc = ws.CreateShortcut("{lnk}")',
            f'sc.TargetPath = "{target}"',
            f'sc.Arguments = Chr(34) & "{args}" & Chr(34)',
            f'sc.WorkingDirectory = "{work_dir}"',
            'sc.Description = "J.A.R.V.I.S AI Assistant"',
            f'sc.IconLocation = "{icon_loc}"',
            'sc.Save',
        ])
        import tempfile
        fd, tmp = tempfile.mkstemp(suffix=".vbs")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(vbs)
            proc = subprocess.Popen(
                ["wscript.exe", "/nologo", tmp],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
            )
            proc.wait(timeout=10)
        finally:
            try:
                os.unlink(tmp)
            except Exception:
                pass

    @staticmethod
    def _get_desktop_dir() -> Path:
        """
        Resolve the user's REAL desktop directory instead of assuming
        ~/Desktop, which breaks when:
          • OneDrive "Known Folder Move" relocates the desktop
            (C:/Users/x/OneDrive/Desktop) — very common on Win 10/11;
          • the XDG desktop is localized on Linux (~/Masaüstü,
            ~/Schreibtisch, ~/Bureau, …).
        Falls back to ~/Desktop only as a last resort.
        """
        home = Path.home()
        _os = platform.system()

        if _os == "Windows":
            # ── 1) SHGetKnownFolderPath(FOLDERID_Desktop) — the canonical
            #       answer; follows OneDrive redirection. No dependencies. ──
            try:
                import ctypes
                from ctypes import wintypes

                class _GUID(ctypes.Structure):
                    _fields_ = [("Data1", wintypes.DWORD),
                                ("Data2", wintypes.WORD),
                                ("Data3", wintypes.WORD),
                                ("Data4", ctypes.c_ubyte * 8)]

                # FOLDERID_Desktop {B4BFCC3A-DB2C-424C-B029-7FE99A87C641}
                fid = _GUID(0xB4BFCC3A, 0xDB2C, 0x424C,
                            (ctypes.c_ubyte * 8)(0xB0, 0x29, 0x7F, 0xE9,
                                                 0x9A, 0x87, 0xC6, 0x41))
                buf = ctypes.c_wchar_p()
                if ctypes.windll.shell32.SHGetKnownFolderPath(
                        ctypes.byref(fid), 0, None, ctypes.byref(buf)) == 0:
                    p = Path(buf.value)
                    ctypes.windll.ole32.CoTaskMemFree(buf)
                    if p.is_dir():
                        return p
            except Exception:
                pass

            # ── 2) Registry: User Shell Folders (may contain %VARS%) ──────
            try:
                import winreg
                with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows\CurrentVersion"
                        r"\Explorer\User Shell Folders") as key:
                    val, _t = winreg.QueryValueEx(key, "Desktop")
                p = Path(os.path.expandvars(val))
                if p.is_dir():
                    return p
            except Exception:
                pass

        elif _os == "Linux":
            # ── xdg-user-dir honours localized names (~/Masaüstü, …) ──────
            try:
                out = subprocess.run(["xdg-user-dir", "DESKTOP"],
                                     capture_output=True, text=True, timeout=5)
                p = Path(out.stdout.strip())
                if out.stdout.strip() and p != home and p.is_dir():
                    return p
            except Exception:
                pass
            try:
                cfg = home / ".config" / "user-dirs.dirs"
                for line in cfg.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("XDG_DESKTOP_DIR"):
                        val = line.split("=", 1)[1].strip().strip('"')
                        p = Path(val.replace("$HOME", str(home)))
                        if p != home and p.is_dir():
                            return p
            except Exception:
                pass

        # macOS: ~/Desktop is always the real path (localization is
        # display-only). Everything else lands here as a last resort.
        return home / "Desktop"

    def _create_desktop_shortcut(self):
        """
        Create a desktop shortcut on Windows / macOS / Linux.
        Never opens a terminal, console, or PowerShell window on any platform.
        """
        import stat as _stat
        script  = _base_dir() / "main.py"
        python  = Path(sys.executable)
        desktop = self._get_desktop_dir()
        congelado = bool(getattr(sys, "frozen", False))   # rodando pelo Nexus.exe

        # Arc-reactor icon (.ico — also exported as .png for Linux/macOS)
        ico_path = _base_dir() / "config" / "nexus.ico"
        if not ico_path.exists():
            self._build_jarvis_icon(ico_path)

        try:
            _os = platform.system()

            # ── Windows ───────────────────────────────────────────────────────
            if _os == "Windows":
                pythonw  = python.parent / "pythonw.exe"
                target   = str(python if congelado else (pythonw if pythonw.exists() else python))
                lnk      = str(desktop / "NEXUS Ultra 2026.lnk")
                icon_loc = str(ico_path) if ico_path.exists() else f"{target},0"
                self._create_lnk_windows(lnk, target, "" if congelado else str(script),
                                         str(script.parent), icon_loc)

            # ── macOS — proper .app bundle (no Terminal window) ───────────────
            elif _os == "Darwin":
                app     = desktop / "NEXUS Ultra 2026.app"
                mac_dir = app / "Contents" / "MacOS"
                res_dir = app / "Contents" / "Resources"
                mac_dir.mkdir(parents=True, exist_ok=True)
                res_dir.mkdir(exist_ok=True)

                # Launcher executable (bash — runs as background process,
                # macOS does NOT open Terminal for executables inside .app bundles)
                launcher = mac_dir / "NEXUS"
                launcher.write_text(
                    "#!/usr/bin/env bash\n"
                    f'cd "{script.parent}"\n'
                    + (f'exec "{python}"\n' if congelado else f'exec "{python}" "{script}"\n')
                )
                launcher.chmod(launcher.stat().st_mode
                               | _stat.S_IEXEC | _stat.S_IXGRP | _stat.S_IXOTH)

                # Minimal Info.plist (required for .app recognition)
                (app / "Contents" / "Info.plist").write_text(
                    '<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                    '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                    '<plist version="1.0"><dict>\n'
                    '  <key>CFBundleExecutable</key><string>NEXUS</string>\n'
                    '  <key>CFBundleIdentifier</key>'
                    '<string>com.nexus.assistant</string>\n'
                    '  <key>CFBundleName</key><string>NEXUS Ultra 2026</string>\n'
                    '  <key>CFBundlePackageType</key><string>APPL</string>\n'
                    '  <key>CFBundleVersion</key><string>1.0</string>\n'
                    '</dict></plist>\n'
                )

                # Optional: copy icon as .icns (skip silently if Pillow is missing)
                try:
                    import PIL.Image
                    icns = res_dir / "AppIcon.icns"
                    PIL.Image.open(ico_path).save(icns, format="ICNS")
                    # Inject icon reference into plist
                    plist = app / "Contents" / "Info.plist"
                    txt = plist.read_text()
                    plist.write_text(
                        txt.replace(
                            '</dict></plist>',
                            '  <key>CFBundleIconFile</key>'
                            '<string>AppIcon</string>\n</dict></plist>\n',
                        )
                    )
                except Exception:
                    pass  # icon is optional

            # ── Linux — .desktop file (Terminal=false, no console) ────────────
            else:
                # Export .ico → .png for better desktop integration
                png_path = ico_path.with_suffix(".png")
                if not png_path.exists() and ico_path.exists():
                    try:
                        import PIL.Image
                        PIL.Image.open(ico_path).resize(
                            (256, 256), PIL.Image.LANCZOS
                        ).save(png_path, format="PNG")
                    except Exception:
                        png_path = ico_path  # fallback to .ico

                icon_line = f"Icon={png_path}\n" if png_path.exists() else ""
                desk = desktop / "NEXUS Ultra 2026.desktop"
                desk.write_text(
                    "[Desktop Entry]\n"
                    "Name=NEXUS Ultra 2026\n"
                    + (f"Exec={python}\n" if congelado else f"Exec={python} {script}\n") +
                    f"Path={script.parent}\n"
                    "Type=Application\n"
                    "Terminal=false\n"
                    "Categories=Utility;\n"
                    + icon_line
                )
                desk.chmod(desk.stat().st_mode | 0o755)

            self._log.append_log("SYS: Atalho criado na área de trabalho.")
        except Exception as e:
            self._log.append_log(f"ERR: Não consegui criar o atalho — {e}")

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
                pass
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
            pass

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

        for tab, label in SettingsPanelOverlay.MENU_LABELS:
            # a Configuração do usuário é a entrada principal: em destaque
            b = MenuButton(ICONE_SETUP.get(tab, ""), label, "primario" if tab == "usuario" else "normal")
            b.clicked.connect(lambda _=False, t=tab: self._pick_setup_option(t))
            lay.addWidget(b)

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
                pass
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
                pass
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

    def _build_content_panel(self) -> QWidget:
        """
        Collapsible panel below the HUD — shows search results, news, briefings.
        Hidden by default; appears when show_content() is called.
        """
        w = QWidget()
        w.setObjectName("ContentPanel")
        w.setStyleSheet(f"""
            QWidget#ContentPanel {{
                background: {C.PANEL};
                border-top: 1px solid {C.BORDER_B};
            }}
        """)
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 7, 12, 8)
        lay.setSpacing(5)

        # ── header row ───────────────────────────────────────────────────────
        hdr = QHBoxLayout(); hdr.setSpacing(6)

        dot = QLabel("◈")
        dot.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        dot.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        hdr.addWidget(dot)

        self._content_title_lbl = QLabel("BRIEFING")
        self._content_title_lbl.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        self._content_title_lbl.setStyleSheet(
            f"color: {C.PRI}; background: transparent; letter-spacing: 1px;"
        )
        hdr.addWidget(self._content_title_lbl)
        hdr.addStretch()

        self._content_ts_lbl = QLabel("")
        self._content_ts_lbl.setFont(QFont(FONT_MAIN, 7))
        self._content_ts_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        hdr.addWidget(self._content_ts_lbl)

        dismiss = QPushButton("FECHAR  ✕")
        dismiss.setFont(QFont(FONT_MAIN, 7))
        dismiss.setFixedHeight(18)
        dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 2px; padding: 0 5px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        dismiss.clicked.connect(w.hide)
        hdr.addWidget(dismiss)
        lay.addLayout(hdr)

        # ── separator ─────────────────────────────────────────────────────────
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};"); lay.addWidget(sep)

        # ── text display ──────────────────────────────────────────────────────
        # 1.5 — QTextBrowser (um QTextEdit que entende links): o painel agora
        # mostra títulos, listas, tabelas, negrito e links, não só texto puro.
        # Links nunca abrem sozinhos: só no clique, e só http/https/mailto.
        self._content_display = QTextBrowser()
        self._content_display.setOpenLinks(False)
        self._content_display.setOpenExternalLinks(False)
        self._content_display.anchorClicked.connect(self._content_link_clicked)
        self._content_display.setReadOnly(True)
        self._content_display.setFont(QFont(FONT_MAIN, 8))
        self._content_display.setMinimumHeight(60)
        self._content_display.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._content_display.setStyleSheet(f"""
            QTextBrowser, QTextEdit {{
                background: {C.DARK};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 3px;
                padding: 6px 8px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG}; width: 6px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B}; border-radius: 3px; min-height: 16px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0; border: none;
            }}
        """)
        lay.addWidget(self._content_display)

        return w

    # ── painel de conteúdo rico (1.5) ────────────────────────────────────────
    # Markdown só quando o texto tem sinais claros dele (título, tabela, lista,
    # **negrito**, link). O resto continua texto puro, exatamente como antes.
    _MD_SINAIS = None

    @classmethod
    def _parece_markdown(cls, text: str) -> bool:
        import re
        if cls._MD_SINAIS is None:
            cls._MD_SINAIS = re.compile(
                r"^\s{0,3}(#{1,4}\s+\S|\|.+\|\s*$|[-*•]\s+\S|\d{1,2}[.)]\s+\S)"
                r"|\*\*[^*\n]+\*\*|\[[^\]\n]+\]\(https?://[^)\s]+\)", re.M)
        return bool(cls._MD_SINAIS.search(text or ""))

    @staticmethod
    def _md_preparar(text: str) -> str:
        """Markdown junta linhas seguidas num parágrafo só. Para não perder as
        quebras de linha do texto original, linhas comuns ganham quebra forçada
        (dois espaços no fim); tabelas, listas e títulos ficam como estão."""
        import re
        estrutural = re.compile(r"^\s{0,3}(#{1,4}\s|\||[-*•]\s|\d{1,2}[.)]\s|>)")
        text = (text or "").replace("•", "-").replace("\r\n", "\n")
        linhas = text.split("\n")
        out = []
        for i, ln in enumerate(linhas):
            prox = linhas[i + 1] if i + 1 < len(linhas) else ""
            if (ln.strip() and prox.strip() and not estrutural.match(ln)
                    and not estrutural.match(prox) and not ln.endswith("  ")):
                ln += "  "
            out.append(ln)
        return "\n".join(out)

    @staticmethod
    def _content_css() -> str:
        return (
            f"h1,h2,h3,h4 {{ color: {C.PRI}; }} "
            f"a {{ color: {C.ACC2}; }} "
            f"b, strong {{ color: {C.WHITE}; }} "
            f"th {{ color: {C.PRI}; background-color: {C.PANEL}; }} "
            f"code {{ color: {C.ACC2}; }}"
        )

    def _content_estilizar(self) -> None:
        """O Qt desenha o Markdown com as cores do sistema (links azul-escuros,
        borda branca); aqui ele passa a usar as cores do tema do NEXUS."""
        try:
            pal = self._content_display.palette()
            pal.setColor(QPalette.ColorRole.Link, QColor(C.ACC2))
            pal.setColor(QPalette.ColorRole.LinkVisited, QColor(C.PRI_DIM))
            self._content_display.setPalette(pal)

            doc = self._content_display.document()
            # tabelas: borda e respiro no tom do tema
            for fr in doc.rootFrame().childFrames():
                if isinstance(fr, QTextTable):
                    f = fr.format()
                    f.setBorderBrush(QBrush(QColor(C.BORDER_B)))
                    f.setBorder(1)
                    f.setCellPadding(5)
                    f.setCellSpacing(0)
                    fr.setFormat(f)
            # títulos na cor de destaque; links na cor do tema
            cur = QTextCursor(doc)
            blk = doc.begin()
            while blk.isValid():
                if blk.blockFormat().headingLevel() > 0:
                    cur.setPosition(blk.position())
                    cur.setPosition(blk.position() + blk.length() - 1,
                                    QTextCursor.MoveMode.KeepAnchor)
                    fmt = QTextCharFormat()
                    fmt.setForeground(QBrush(QColor(C.PRI)))
                    cur.mergeCharFormat(fmt)
                # links: o Qt pinta com azul-escuro fixo; troca pela cor do tema
                it = blk.begin()
                while not it.atEnd():
                    frag = it.fragment()
                    if frag.isValid() and frag.charFormat().isAnchor():
                        cur.setPosition(frag.position())
                        cur.setPosition(frag.position() + frag.length(),
                                        QTextCursor.MoveMode.KeepAnchor)
                        lf = QTextCharFormat()
                        lf.setForeground(QBrush(QColor(C.ACC2)))
                        cur.mergeCharFormat(lf)
                    it += 1
                blk = blk.next()
        except Exception as e:  # cosmético: nunca derruba o painel
            print(f"[Painel] estilo do Markdown não aplicado: {e}")

    def _content_link_clicked(self, url) -> None:
        """Só abre http, https e mailto, e só quando você clica."""
        try:
            if url.scheme().lower() in ("http", "https", "mailto"):
                QDesktopServices.openUrl(url)
        except Exception:
            pass

    def _show_content(self, title: str, text: str):
        """Slot — runs on Qt main thread. Updates and shows the content panel."""
        import time as _time
        # The panel opens below the head, so the head looks down at it. It is a
        # tiny thing that answers "did that land?" before you read a word.
        self.hud.glance(0.0, -0.85, hold=1.3)
        self._content_title_lbl.setText(title.upper()[:48])
        self._content_ts_lbl.setText(agora().strftime("%H:%M:%S"))
        if self._parece_markdown(text):
            self._content_display.document().setDefaultStyleSheet(self._content_css())
            self._content_display.setMarkdown(self._md_preparar(text))
            self._content_estilizar()
        else:
            self._content_display.setPlainText(text)
        self._content_display.moveCursor(
            self._content_display.textCursor().MoveOperation.Start
        )
        first_show = not self._content_panel.isVisible()
        self._content_panel.show()
        if first_show:
            total = self._center_split.height()
            self._center_split.setSizes([max(total - 220, 120), 220])

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

    @staticmethod
    def _esc(s) -> str:
        return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace("\n", "<br>"))

    def _show_review(self, title: str, summary: str, findings, unclear):
        """Slot — Qt main thread. Lays a document review into the content panel."""
        e = self._esc
        parts = [f'<div style="color:{C.TEXT}; font-family:Courier New;">']

        if summary:
            parts.append(
                f'<div style="color:{C.WHITE}; border-left:2px solid {C.PRI};'
                f' padding-left:8px; margin-bottom:10px;">{e(summary)}</div>')

        for f in (findings or []):
            key, mark = self._REVIEW_MARKS.get(f.get("severity"), ("PRI_DIM", "·"))
            colour = getattr(C, key)
            parts.append(f'<div style="margin-bottom:11px;">')
            parts.append(
                f'<span style="color:{colour}; font-weight:bold;">{mark}</span> '
                f'<span style="color:{C.WHITE}; font-weight:bold;">'
                f'{e(f.get("heading"))}</span>')
            if f.get("detail"):
                parts.append(f'<div style="margin-left:12px;">{e(f["detail"])}</div>')
            if f.get("quote"):
                # The document's own wording, visually separated from the
                # explanation so the two are never mistaken for each other.
                parts.append(
                    f'<div style="margin-left:12px; color:{C.TEXT_DIM};'
                    f' border-left:1px solid {C.BORDER}; padding-left:7px;">'
                    f'&ldquo;{e(f["quote"])}&rdquo;</div>')
            if f.get("suggestion"):
                parts.append(
                    f'<div style="margin-left:12px; color:{C.PRI};">'
                    f'&rarr; {e(f["suggestion"])}</div>')
            parts.append('</div>')

        if unclear:
            parts.append(
                f'<div style="margin-top:6px; border-top:1px solid {C.BORDER};'
                f' padding-top:7px; color:{C.TEXT_MED};">'
                'The document does not settle:</div>')
            for u in unclear:
                parts.append(
                    f'<div style="margin-left:12px; color:{C.TEXT_MED};">'
                    f'&middot; {e(u)}</div>')
        parts.append('</div>')

        import time as _time
        self.hud.glance(0.0, -0.85, hold=1.3)
        # Left as written, not upper-cased. The other content-panel titles are
        # the app's own English labels, but this one is the document's name in
        # the user's language, and str.upper() applies English casing rules to
        # it: Turkish "Sözleşmesi" comes back "SÖZLEŞMESI", having lost the
        # dotted capital İ. Python has no locale-aware upper to reach for, and
        # imposing one language's rules on all of them is the bug, not the fix.
        self._content_title_lbl.setText((title or "Document")[:48])
        self._content_ts_lbl.setText(agora().strftime("%H:%M:%S"))
        self._content_display.setHtml("".join(parts))
        self._content_display.moveCursor(
            self._content_display.textCursor().MoveOperation.Start)
        first_show = not self._content_panel.isVisible()
        self._content_panel.show()
        if first_show:
            total = self._center_split.height()
            self._center_split.setSizes([max(total - 260, 120), 260, 0])

    # ── quiz panel ───────────────────────────────────────────────────────────
    # An interactive twin of the content panel. The plugin only ever hands over
    # questions; everything about asking, marking and reporting happens here,
    # and the finished result is pushed back into the conversation the same way
    # a dropped file is — as a message NEXUS reads and responds to. That keeps
    # the tool call short (it returns the moment the board is up) and leaves the
    # talking to the assistant, in the user's own language.

    def _quiz_btn(self, text: str, primary: bool = False) -> QPushButton:
        b = QPushButton(text)
        b.setFont(QFont(FONT_MAIN, 8))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setMinimumHeight(24)
        edge = C.BORDER_B if primary else C.BORDER
        col = C.PRI if primary else C.TEXT_MED
        b.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL2}; color: {col};
                border: 1px solid {edge}; border-radius: 2px;
                padding: 3px 9px; text-align: left;
            }}
            QPushButton:hover {{ color: {C.WHITE}; border-color: {C.PRI_DIM}; }}
            QPushButton:disabled {{ color: {C.TEXT_DIM}; border-color: {C.BORDER}; }}
        """)
        return b

    def _build_quiz_panel(self) -> QWidget:
        w = QWidget()
        w.setObjectName("QuizPanel")
        w.setStyleSheet(f"""
            QWidget#QuizPanel {{
                background: {C.PANEL};
                border-top: 1px solid {C.BORDER_B};
            }}
        """)
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 7, 12, 8)
        lay.setSpacing(6)

        hdr = QHBoxLayout(); hdr.setSpacing(6)
        dot = QLabel("◈")
        dot.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        dot.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        hdr.addWidget(dot)

        self._quiz_title_lbl = QLabel("QUIZ")
        self._quiz_title_lbl.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        self._quiz_title_lbl.setStyleSheet(
            f"color: {C.PRI}; background: transparent; letter-spacing: 1px;")
        hdr.addWidget(self._quiz_title_lbl)
        hdr.addStretch()

        self._quiz_count_lbl = QLabel("")
        self._quiz_count_lbl.setFont(QFont(FONT_MAIN, 7))
        self._quiz_count_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        hdr.addWidget(self._quiz_count_lbl)

        quit_btn = QPushButton("FECHAR  ✕")
        quit_btn.setFont(QFont(FONT_MAIN, 7))
        quit_btn.setFixedHeight(18)
        quit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        quit_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 2px; padding: 0 5px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        quit_btn.clicked.connect(self._hide_quiz)
        hdr.addWidget(quit_btn)
        lay.addLayout(hdr)

        rule = QFrame(); rule.setFixedHeight(1)
        rule.setStyleSheet(f"background: {C.BORDER};")
        lay.addWidget(rule)

        self._quiz_q_lbl = QLabel("")
        self._quiz_q_lbl.setWordWrap(True)
        self._quiz_q_lbl.setFont(QFont(FONT_MAIN, 9))
        self._quiz_q_lbl.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        lay.addWidget(self._quiz_q_lbl)

        self._quiz_answers = QWidget()
        self._quiz_answers.setStyleSheet("background: transparent;")
        self._quiz_answers_lay = QVBoxLayout(self._quiz_answers)
        self._quiz_answers_lay.setContentsMargins(0, 2, 0, 0)
        self._quiz_answers_lay.setSpacing(4)
        lay.addWidget(self._quiz_answers)

        self._quiz_note_lbl = QLabel("")
        self._quiz_note_lbl.setWordWrap(True)
        self._quiz_note_lbl.setFont(QFont(FONT_MAIN, 8))
        self._quiz_note_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._quiz_note_lbl.hide()
        lay.addWidget(self._quiz_note_lbl)

        foot = QHBoxLayout()
        foot.addStretch()
        self._quiz_next_btn = self._quiz_btn("PRÓXIMA  →", primary=True)
        self._quiz_next_btn.setFixedWidth(110)
        self._quiz_next_btn.clicked.connect(self._quiz_next)
        self._quiz_next_btn.hide()
        foot.addWidget(self._quiz_next_btn)
        lay.addLayout(foot)

        self._quiz = None
        return w

    def _show_quiz(self, topic: str, questions, grader=None):
        """Slot — Qt main thread. Puts a fresh quiz on the board."""
        if not questions:
            return
        self._quiz = {
            "topic": topic or "",
            "questions": list(questions),
            "grader": grader,
            "i": 0,
            "results": [],
            "answered": False,
        }
        self._quiz_title_lbl.setText((topic or "quiz").upper()[:48])
        self.hud.glance(0.0, -0.85, hold=1.3)
        first_show = not self._quiz_panel.isVisible()
        self._quiz_panel.show()
        if first_show:
            total = self._center_split.height()
            self._center_split.setSizes([max(total - 250, 120), 0, 250])
        self._quiz_render()

    def _hide_quiz(self):
        self._quiz = None
        self._quiz_panel.hide()

    def _quiz_clear_answers(self):
        while self._quiz_answers_lay.count():
            item = self._quiz_answers_lay.takeAt(0)
            child = item.widget()
            if child is not None:
                child.setParent(None)
                child.deleteLater()

    def _quiz_render(self):
        q = self._quiz["questions"][self._quiz["i"]]
        n, total = self._quiz["i"] + 1, len(self._quiz["questions"])
        self._quiz_count_lbl.setText(f"{n} / {total}")
        self._quiz_q_lbl.setText(q.get("question", ""))
        self._quiz_note_lbl.hide()
        self._quiz_next_btn.hide()
        self._quiz["answered"] = False
        self._quiz_clear_answers()

        opts = q.get("options") or []
        if opts:
            for text in opts:
                b = self._quiz_btn("   " + text)
                b.clicked.connect(lambda _=False, t=text: self._quiz_submit(t))
                self._quiz_answers_lay.addWidget(b)
        else:
            row = QWidget(); row.setStyleSheet("background: transparent;")
            h = QHBoxLayout(row); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(6)
            field = QLineEdit()
            field.setFont(QFont(FONT_MAIN, 9))
            field.setPlaceholderText("sua resposta")
            field.setStyleSheet(f"""
                QLineEdit {{
                    background: {C.PANEL2}; color: {C.WHITE};
                    border: 1px solid {C.BORDER}; border-radius: 2px; padding: 4px 7px;
                }}
                QLineEdit:focus {{ border-color: {C.PRI_DIM}; }}
            """)
            send = self._quiz_btn("RESPONDER", primary=True)
            send.setFixedWidth(90)
            field.returnPressed.connect(lambda: self._quiz_submit(field.text()))
            send.clicked.connect(lambda: self._quiz_submit(field.text()))
            h.addWidget(field, stretch=1)
            h.addWidget(send)
            self._quiz_answers_lay.addWidget(row)
            field.setFocus()

    def _quiz_submit(self, given: str):
        if self._quiz is None or self._quiz["answered"]:
            return
        self._quiz["answered"] = True
        q = self._quiz["questions"][self._quiz["i"]]
        grader = self._quiz.get("grader")
        verdict = None
        if callable(grader):
            try:
                verdict = grader(q, given)
            except Exception:
                verdict = None
        self._quiz["results"].append({
            "question": q.get("question", ""),
            "type": q.get("type", ""),
            "given": str(given or "").strip(),
            "answer": q.get("answer", ""),
            "correct": verdict,
        })

        for i in range(self._quiz_answers_lay.count()):
            wdg = self._quiz_answers_lay.itemAt(i).widget()
            if wdg is not None:
                wdg.setEnabled(False)

        if verdict is True:
            mark, colour = "✓  correct", C.GREEN
        elif verdict is False:
            mark, colour = "✕  " + str(q.get("answer", "")), C.RED
        else:
            # Open answers and near-miss gap-fills are NEXUS's to judge. Saying
            # so is honest; marking it wrong here would be a guess.
            mark, colour = "…  noted — I'll go over this one with you", C.ACC2
        note = q.get("note") or ""
        self._quiz_note_lbl.setText(mark + (("\n" + note) if note else ""))
        self._quiz_note_lbl.setStyleSheet(f"color: {colour}; background: transparent;")
        self._quiz_note_lbl.show()

        last = self._quiz["i"] >= len(self._quiz["questions"]) - 1
        self._quiz_next_btn.setText("TERMINAR  →" if last else "PRÓXIMA  →")
        self._quiz_next_btn.show()
        self._quiz_next_btn.setFocus()

    def _quiz_next(self):
        if self._quiz is None:
            return
        if self._quiz["i"] >= len(self._quiz["questions"]) - 1:
            self._quiz_finish()
        else:
            self._quiz["i"] += 1
            self._quiz_render()

    def _quiz_finish(self):
        if self._quiz is None:
            return
        topic = self._quiz["topic"]
        results = self._quiz["results"]
        right = sum(1 for r in results if r["correct"] is True)
        unsure = sum(1 for r in results if r["correct"] is None)
        total = len(results)
        self._quiz_panel.hide()
        self._quiz = None

        self._log.append_log(f"QUIZ: {topic or 'quiz'} — {right}/{total} correct")

        # Hand it back to NEXUS as a message, not as a tool return: the tool
        # call ended minutes ago. This is the same channel a dropped file uses.
        lines = [f"[QUIZ_DONE] topic={topic or 'general'} | "
                 f"auto-marked {right}/{total} correct"
                 + (f", {unsure} still need your marking" if unsure else "")]
        for i, r in enumerate(results, 1):
            state = ("correct" if r["correct"] is True
                     else "wrong" if r["correct"] is False else "NEEDS MARKING")
            lines.append(
                f"{i}. [{r['type']}] {r['question']} | they answered: "
                f"{r['given'] or '(blank)'} | expected: {r['answer']} | {state}")
        lines.append(
            "Mark every question flagged NEEDS MARKING yourself — accept an answer "
            "that means the same thing. Then tell them how they did in their own "
            "language: the score, what they got wrong and why, in a couple of "
            "sentences. Offer another round only if it fits. "
            "Remember something only if it would still matter next week — that they "
            "are working through a subject, or keep missing the same thing. A score "
            "from one session is not worth a memory, and a memory per quiz would "
            "bury the things that are.")
        msg = "\n".join(lines)
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

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

    def _check_autostart(self) -> bool:
        """Returns True if auto-start is currently registered on this OS."""
        try:
            if _OS == "Windows":
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
                try:
                    winreg.QueryValueEx(key, "NEXUS_AI")
                    return True
                except FileNotFoundError:
                    return False
                finally:
                    winreg.CloseKey(key)
            elif _OS == "Darwin":
                return (Path.home() / "Library" / "LaunchAgents"
                        / "com.nexus.assistant.plist").exists()
            else:
                return (Path.home() / ".config" / "autostart" / "nexus.desktop").exists()
        except Exception:
            return False

    def _toggle_autostart(self):
        currently_on = self._check_autostart()
        try:
            script = str(_base_dir() / "main.py")
            if _OS == "Windows":
                import winreg
                reg = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS)
                if currently_on:
                    winreg.DeleteValue(reg, "NEXUS_AI")
                elif getattr(sys, "frozen", False):          # Nexus.exe
                    winreg.SetValueEx(reg, "NEXUS_AI", 0, winreg.REG_SZ,
                                      f'"{sys.executable}"')
                else:
                    pythonw = Path(sys.executable).parent / "pythonw.exe"
                    exe = str(pythonw if pythonw.exists() else sys.executable)
                    winreg.SetValueEx(reg, "NEXUS_AI", 0, winreg.REG_SZ,
                                      f'"{exe}" "{script}"')
                winreg.CloseKey(reg)
            elif _OS == "Darwin":
                plist_dir = Path.home() / "Library" / "LaunchAgents"
                plist_dir.mkdir(parents=True, exist_ok=True)
                plist = plist_dir / "com.nexus.assistant.plist"
                if currently_on:
                    plist.unlink(missing_ok=True)
                else:
                    plist.write_text(
                        '<?xml version="1.0" encoding="UTF-8"?>\n'
                        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                        '<plist version="1.0"><dict>\n'
                        '  <key>Label</key><string>com.nexus.assistant</string>\n'
                        '  <key>ProgramArguments</key><array>\n'
                        f'    <string>{sys.executable}</string>\n'
                        + ("" if getattr(sys, "frozen", False) else f'    <string>{script}</string>\n') +
                        '  </array>\n'
                        '  <key>RunAtLoad</key><true/>\n'
                        '</dict></plist>\n'
                    )
            else:
                desk_dir = Path.home() / ".config" / "autostart"
                desk_dir.mkdir(parents=True, exist_ok=True)
                desk = desk_dir / "nexus.desktop"
                if currently_on:
                    desk.unlink(missing_ok=True)
                else:
                    desk.write_text(
                        "[Desktop Entry]\n"
                        f"Name={self._assistant_name}\n"
                        + (f"Exec={sys.executable}\n" if getattr(sys, "frozen", False)
                           else f"Exec={sys.executable} {script}\n") +
                        "Type=Application\nTerminal=false\n"
                        "X-GNOME-Autostart-enabled=true\n"
                    )
            enabled = not currently_on
            self._update_autostart_btn(enabled)
            self._log.append_log(
                f"SYS: Iniciar com o computador {'ligado' if enabled else 'desligado'}.")
        except Exception as e:
            self._log.append_log(f"ERR: O início automático falhou — {e}")

    def _update_autostart_btn(self, enabled: bool):
        if not hasattr(self, '_autostart_btn'):
            return
        if enabled:
            self._autostart_btn.setText("◉  INICIAR COM O PC: LIGADO")
            self._autostart_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #001a08; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 3px;
                }}
                QPushButton:hover {{ background: #002010; }}
            """)
        else:
            self._autostart_btn.setText("◉  INICIAR COM O PC: DESLIGADO")
            self._autostart_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 3px;
                }}
                QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
            """)

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
                pass
        # Before NexusLive has wired its callback (drawer built at startup).
        ready, enabled = False, False
        try:
            from core.wake_word import is_ready
            from memory.config_manager import get_wake_word_enabled
            ready, enabled = is_ready(), get_wake_word_enabled()
        except Exception:
            pass
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
        self._hud_btn.setToolTip(f"{desc}.\nClique para escolher entre os {len(HUD_STYLE_INFO)} visuais do hub.")
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
        from .hud_ultra import ULTRA_INFO
        _primeiro_ultra = next(iter(ULTRA_INFO), "")
        for chave, (icone, nome, desc) in HUD_STYLE_INFO.items():
            if chave == _primeiro_ultra:
                menu.addSeparator()
                _t2 = QAction("NOVOS · ULTRA 2026", menu)
                _t2.setEnabled(False)
                menu.addAction(_t2)
            marca = "●" if chave == atual else "○"
            ac = QAction(f"{marca}  {icone}  {nome}   —   {desc}", menu)
            ac.triggered.connect(lambda _=False, k=chave: self._set_hud_style(k))
            menu.addAction(ac)
        if self._hud_btn.isVisible():
            pos = self._hud_btn.mapToGlobal(QPoint(0, self._hud_btn.height()))
        else:
            pos = QCursor.pos()
        menu.exec(pos)

    def _set_hud_style(self, want: str):
        """Troca o visual do hub na hora e guarda a escolha."""
        from memory.config_manager import HUD_STYLES, save_hud_style
        from .hud import HUD_STYLE_INFO
        if want not in HUD_STYLES:
            want = "orb"
        save_hud_style(want)
        try:
            self.hud.hud_style = want
            self.hud._pulsos = []
            self.hud.update()
        except Exception:
            pass
        self._refresh_hud_btn()
        self._log.append_log(f"SYS: Visual do hub: {HUD_STYLE_INFO[want][1].lower()}.")

    def _toggle_ptt(self):
        from memory.config_manager import (get_push_to_talk_enabled,
                                           save_push_to_talk_enabled)
        want = not get_push_to_talk_enabled()
        save_push_to_talk_enabled(want)
        scope = None
        if self.on_push_to_talk:
            try:
                scope = self.on_push_to_talk(want)
            except Exception as e:
                self._log.append_log(f"ERR: Falar segurando falhou — {e}")
                save_push_to_talk_enabled(False)
                want = False
        self._apply_ptt_shortcut(want and scope != "global")
        self._refresh_talk_btns()

    def _apply_ptt_shortcut(self, needed: bool):
        """Bind the chord inside the window when no global hook is available.

        On macOS and Linux there is no dependency-free way to read global key
        state, so the chord is at least live whenever this window has focus.
        Qt gives no key-release for a QShortcut, so a press latches the mic open
        and a short timer closes it; held down, auto-repeat keeps pushing that
        timer out, which behaves like holding a key.
        """
        from PyQt6.QtGui import QKeySequence, QShortcut
        from core.hotkey import qt_sequence

        if not needed:
            sc = getattr(self, "_ptt_sc", None)
            if sc is not None:
                sc.setEnabled(False)
                self._ptt_sc = None
            self._ptt_hold(False)
            return
        if getattr(self, "_ptt_sc", None) is not None:
            return

        self._ptt_release = QTimer(self)
        self._ptt_release.setSingleShot(True)
        self._ptt_release.setInterval(420)
        self._ptt_release.timeout.connect(lambda: self._ptt_hold(False))

        def _press():
            self._ptt_hold(True)
            self._ptt_release.start()

        self._ptt_sc = QShortcut(QKeySequence(qt_sequence()), self)
        self._ptt_sc.setAutoRepeat(True)
        self._ptt_sc.activated.connect(_press)

    def _ptt_hold(self, held: bool):
        """Report a windowed press/release to whoever owns the microphone."""
        cb = getattr(self, "ptt_hold", None)
        if cb:
            try:
                cb(bool(held))
            except Exception:
                pass

    def _toggle_wake_word(self):
        st = self._wake_state()
        if not st["ready"]:
            # First time: download openwakeword + model in a worker thread.
            self._wake_btn.setText("⬇  BAIXANDO… (só uma vez)")
            self._wake_btn.setEnabled(False)
            def _work():
                try:
                    from core.wake_word import install_and_download
                    ok, msg = install_and_download(
                        logger=lambda m: self._log_sig.emit(f"SYS: {m}"))
                except Exception as e:
                    ok, msg = False, str(e)
                if ok and self.on_wake_toggle:
                    try:
                        self.on_wake_toggle(True)   # auto-enable after a successful download
                    except Exception:
                        pass
                self._wake_dl_sig.emit(ok, msg)
            threading.Thread(target=_work, daemon=True).start()
            return
        # Already downloaded → just flip enabled/disabled through NexusLive.
        if self.on_wake_toggle:
            try:
                self.on_wake_toggle(not st["enabled"])
            except Exception:
                pass
        self._refresh_wake_btns()

    def _on_wake_install_done(self, ok: bool, msg: str):
        self._log_sig.emit(f"SYS: {'Wake word ready.' if ok else 'Wake word setup failed: ' + msg}")
        self._refresh_wake_btns()

    def _tap_wake_manual(self):
        if self.on_wake_manual:
            try:
                self.on_wake_manual()
            except Exception:
                pass
        self._refresh_wake_btns()

    def _update_brief_btn(self, enabled: bool):
        if not hasattr(self, '_brief_btn'):
            return
        if enabled:
            self._brief_btn.setText("☀  BRIEFING DA MANHÃ: LIGADO")
            self._brief_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #001a08; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 3px;
                    text-align: left; padding: 0 8px;
                }}
                QPushButton:hover {{ background: #002010; }}
            """)
        else:
            self._brief_btn.setText("☀  BRIEFING DA MANHÃ: DESLIGADO")
            self._brief_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 3px;
                    text-align: left; padding: 0 8px;
                }}
                QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
            """)

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

    def _pick_setup_option(self, tab: str):
        """Escolher uma opção do menu SETUP fecha o menu e abre a seção.
        CONFIGURAÇÃO DO USUÁRIO abre direto a janela do usuário (a única)."""
        self._close_setup()
        if tab == "usuario":
            self._open_preferences()
            return
        self._open_settings_panel(tab)

    def _open_settings_panel(self, tab: str = "status"):
        """Painel de Configurações: status, atuador, backup, reset, sobre etc.
        Os itens que já têm painel próprio abrem o painel existente."""
        if getattr(self, "_settings_overlay", None):
            self._settings_overlay.hide()
        try:
            plugins = self.get_plugins() if self.get_plugins else []
            count = len(plugins)
        except Exception:
            count = None
        cw = self.centralWidget()
        ov = SettingsPanelOverlay(
            actions={
                "customise": self._open_customize,
                "preferences": self._open_preferences,
                "commands": self._open_commands_panel,
                "add_command": lambda: self._open_commands_panel(adicionar=True),
                "plugins": self._open_plugin_manager,
                "plugin_settings": self._open_plugin_settings,
                "vision": self._open_vision_panel,
                "intel": self._open_intel_panel,
                "clip": self._open_clip_panel,
                "memory": self._open_memory_panel,
                "audio": self._open_audio_devices,
                "ptt": self._toggle_ptt,
                "log": self._open_activity_log,
                "remote": self._open_remote,
                "shortcut": self._create_desktop_shortcut,
                "autostart": self._toggle_autostart,
                "autostart_state": self._check_autostart,
                "update": self._update_system,
                "agenda": self._open_agenda,
                "isa": self._open_isa_panel,
                "quickbar_saved": self._rebuild_quickbar,
                "shortcuts_saved": self._reload_shortcuts,
            },
            plugin_count=count,
            parent=cw,
            start=tab,
        )
        ov.setFixedHeight(min(640, cw.height() - 16))
        self._centre_overlay(ov)
        ov.show()
        ov.raise_()
        self._settings_overlay = ov

    def _open_preferences(self):
        from core import preferences as _P
        if _P.password_set():
            from PyQt6.QtWidgets import QInputDialog, QLineEdit
            pw, ok = QInputDialog.getText(self, "Painel protegido", "Senha do painel:",
                                          QLineEdit.EchoMode.Password)
            if not ok or not _P.check_password(pw):
                self._log.append_log("SYS: Senha do painel incorreta.")
                return
        from .overlays.user_settings import PreferencesOverlay
        if getattr(self, "_prefs_overlay", None):
            self._prefs_overlay.hide()
        if self._customize_overlay:
            self._customize_overlay.hide()
        cw = self.centralWidget()
        ov = PreferencesOverlay(parent=cw,
                                assistant_section=self._make_customize(embedded=True))
        self._centre_overlay(ov)
        self._prefs_overlay = ov

    def _open_customize(self):
        """Personalizar e Preferências viraram UMA janela (Configuração do
        usuário). Quem chamava a personalização cai nela também."""
        self._open_preferences()

    def _make_customize(self, embedded: bool = False, parent=None) -> "CustomizeOverlay":
        """The name / voice / colour / formality / language / quiet-hours block,
        filled from config and wired to save — floating or embedded."""
        cfg = _read_full_config()
        try:
            from memory.config_manager import (get_formality, get_language,
                                               get_quiet_hours)
            _formality = get_formality()
            _language  = get_language()
            _quiet     = get_quiet_hours() or {
                "enabled": False, "start": "22:00", "end": "07:00"}
        except Exception:
            _formality = "casual"
            _language  = "auto"
            _quiet     = {"enabled": False, "start": "22:00", "end": "07:00"}
        ov = CustomizeOverlay(
            cfg.get("assistant_name", "NEXUS") or "NEXUS",
            cfg.get("user_name", ""),
            cfg.get("ui_color", "") or DEFAULT_UI_COLOR,
            cfg.get("voice_name", ""),
            formality=_formality,
            language=_language,
            quiet_hours=_quiet,
            parent=parent,
            embedded=embedded,
        )
        ov.on_preview = self._preview_ui_color
        ov.on_hud_style = self._set_hud_style
        ov.saved.connect(self._apply_name_update)
        return ov

    def _open_customize_floating(self):
        """The old standalone window — kept only in case a plugin calls it."""
        if self._customize_overlay:
            self._customize_overlay.hide()
        cw = self.centralWidget()
        ov = self._make_customize(embedded=False, parent=cw)
        ow, oh = CustomizeOverlay._OW, CustomizeOverlay._OH
        oh = min(oh, cw.height() - 16)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.show()
        self._customize_overlay = ov

    def _preview_ui_color(self, hex_color: str):
        """Live preview — paints the whole interface the new colour (does NOT write to config)."""
        old = current_palette()
        if apply_ui_accent(hex_color):
            retheme_all_widgets(old, current_palette())

    def _apply_name_update(self, name: str, user_name: str, ui_color: str = "",
                           voice: str = "", formality: str = "casual",
                           language: str = "auto", quiet_hours: dict = None):
        """Update all name/theme-dependent UI elements and persist to config."""
        self._assistant_name = name.strip() or "NEXUS"
        display = self._assistant_name.upper()
        self.setWindowTitle(f"{display} — {APP_VERSION} — desenvolvido por André Luiz Lima Menezes")
        self._title_lbl.setText(display)
        if hasattr(self, "_pro_lbl"):
            self._pro_lbl.setVisible(display == "NEXUS")
        self._sub_lbl.setText("ASSISTENTE PESSOAL INTELIGENTE" if display == "NEXUS"
                              else "Assistente pessoal")
        self._log._ai_name_lc = self._assistant_name.lower()
        self.hud._assistant_name = display

        color_changed = False
        if ui_color:
            old = current_palette()
            if apply_ui_accent(ui_color):
                # Live-paint the whole interface (panels, buttons, borders, HUD)
                retheme_all_widgets(old, current_palette())
                color_changed = old["PRI"] != C.PRI

        # Voice change → persist and, if it actually changed, rebuild the Live
        # session so the new voice takes effect (it's fixed at connect time).
        voice_changed = False
        if voice:
            from memory.config_manager import get_voice, save_voice
            if voice != get_voice():
                save_voice(voice)
                voice_changed = True

        try:
            data = _read_full_config()
            data["assistant_name"] = self._assistant_name
            data["user_name"] = user_name.strip()
            if ui_color:
                data["ui_color"] = ui_color.strip().lower()
            API_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")
            self._log.append_log(f"SYS: Identidade atualizada — {display}")
            if color_changed:
                self._log.append_log(f"SYS: Cor aplicada — {ui_color}")
            if voice_changed:
                self._log.append_log(f"SYS: Voice set — {voice}")
        except Exception as e:
            self._log.append_log(f"ERR: Não consegui salvar a configuração — {e}")

        # Formality + quiet hours — persist; formality changes the prompt,
        # so it needs a session rebuild exactly like a voice change.
        formality_changed = False
        try:
            from memory.config_manager import (get_formality, get_language,
                                               save_formality, save_language,
                                               save_quiet_hours)
            formality = formality if formality in ("formal", "casual") else "casual"
            if formality != get_formality():
                save_formality(formality)
                formality_changed = True
                self._log.append_log(f"SYS: Tratamento — {formality}")
            language = language if language in ("auto", "pt", "en") else "auto"
            if language != get_language():
                save_language(language)
                formality_changed = True          # same rebuild trigger
                self._log.append_log(f"SYS: Idioma das respostas — {language}")
            qh = quiet_hours or {}
            save_quiet_hours(bool(qh.get("enabled")),
                             str(qh.get("start", "22:00")),
                             str(qh.get("end", "07:00")))
            if qh.get("enabled"):
                self._log.append_log(
                    f"SYS: Horário de silêncio {qh.get('start')} → {qh.get('end')}")
            else:
                self._log.append_log("SYS: Horário de silêncio desligado")
        except Exception as e:
            self._log.append_log(f"ERR: Não consegui salvar o tratamento ou o horário de silêncio — {e}")

        if (voice_changed or formality_changed) and self.on_voice_change:
            self.on_voice_change()

    def _centre_overlay(self, ov) -> None:
        """Place a floating overlay in the middle of the HUD and show it."""
        cw = self.centralWidget()
        ov.adjustSize()
        ov.setGeometry(
            max(0, (cw.width()  - ov.width())  // 2),
            max(0, (cw.height() - ov.height()) // 2),
            ov.width(), ov.height(),
        )
        ov.show()
        ov.raise_()

    # ── Audio devices ────────────────────────────────────────────────────────

    def _open_audio_devices(self):
        ov = AudioDeviceOverlay(parent=self.centralWidget())
        ov.picked.connect(self._on_audio_devices_applied)
        self._centre_overlay(ov)
        self._audio_overlay = ov            # keep a reference so it isn't GC'd

    def _on_audio_devices_applied(self):
        self._log.append_log("SYS: Dispositivos de áudio atualizados.")
        if self.on_audio_device_change:
            self.on_audio_device_change()

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

    def _open_clip_panel(self):
        try:
            # start monitoring on first open (and only once)
            if not getattr(self, "_clip_hooked", False):
                QApplication.clipboard().dataChanged.connect(
                    self._on_clipboard_change)
                self._clip_hooked = True
            ov = ClipOverlay(parent=self.centralWidget(), log=self.write_log,
                             history=self._clip_history)
            ov._copy_back = self._clip_copy_back(ov)
            self._centre_overlay(ov)
            self._clip_overlay = ov
        except Exception as e:
            msg = f"A área de transferência não abriu — {e}"
            print(f"[UI] {msg}")
            try:
                self.write_log(f"SYS: {msg}")
            except Exception:
                pass

    def _clip_copy_back(self, ov):
        """Wrap ClipOverlay._copy_back so our own copies don't re-enter
        the history."""
        orig = ov._copy_back
        def _guarded(text):
            self._clip_self = True
            try:
                orig(text)
            except Exception:
                self._clip_self = False
        return _guarded

    def _open_notes_panel(self):
        # 1.2: o painel antigo de notas virou a central de Notas e Lembretes
        self._open_agenda()

    def _open_notes_panel_antigo(self):
        try:
            ov = NotesOverlay(parent=self.centralWidget(), log=self.write_log)
            self._centre_overlay(ov)
            self._notes_overlay = ov
        except Exception as e:
            msg = f"O painel de notas não abriu — {e}"
            print(f"[UI] {msg}")
            try:
                self.write_log(f"SYS: {msg}")
            except Exception:
                pass

    def _open_intel_panel(self):
        try:
            ov = IntelOverlay(parent=self.centralWidget(), log=self.write_log)
            self._centre_overlay(ov)
            self._intel_overlay = ov
        except Exception as e:
            msg = f"O painel de sistema não abriu — {e}"
            print(f"[UI] {msg}")
            try:
                self.write_log(f"SYS: {msg}")
            except Exception:
                pass

    def _open_commands_panel(self, adicionar: bool = False):
        try:
            ov = CommandsOverlay(parent=self.centralWidget(), adicionar=adicionar)
            self._centre_overlay(ov)
            self._commands_overlay = ov
        except Exception as e:
            msg = f"A lista de comandos não abriu — {e}"
            print(f"[UI] {msg}")
            try:
                self.write_log(f"SYS: {msg}")
            except Exception:
                pass

    def _open_vision_panel(self):
        # PyQt6 encerra o app em exceção não tratada dentro de um slot —
        # qualquer falha aqui precisa virar mensagem no log, não crash.
        try:
            ov = VisionOverlay(parent=self.centralWidget(), log=self.write_log)
            self._centre_overlay(ov)
            self._vision_overlay = ov
        except Exception as e:
            msg = f"O painel de visão não abriu — {e}"
            print(f"[UI] {msg}")
            try:
                self.write_log(f"SYS: {msg}")
            except Exception:
                pass

    def _open_memory_panel(self):
        ov = MemoryOverlay(parent=self.centralWidget())
        self._centre_overlay(ov)
        self._memory_overlay = ov

    # ── Irreversible-action confirmation ─────────────────────────────────────

    def _show_confirm_banner(self, title: str, detail: str):
        self._hide_confirm_banner()
        ov = ConfirmBanner(title, detail, parent=self.centralWidget())
        ov.answered.connect(self._on_confirm_answered)
        self._centre_overlay(ov)
        self._confirm_overlay = ov

    def _hide_confirm_banner(self):
        ov = getattr(self, "_confirm_overlay", None)
        if ov is not None:
            ov.hide()
            ov.deleteLater()
            self._confirm_overlay = None

    def _on_confirm_answered(self, accepted: bool):
        # Tear the banner down first: core.confirm.resolve() may be about to
        # shut the machine down, and a live widget mid-callback is not where you
        # want to be when that happens.
        self._hide_confirm_banner()
        try:
            from core.confirm import resolve
            resolve(bool(accepted))
        except Exception as e:
            self._log.append_log(f"ERR: A confirmação falhou — {e}")

    def _open_plugin_manager(self):
        plugins = self.get_plugins() if self.get_plugins else []
        cw = self.centralWidget()
        ov = PluginManagerOverlay(plugins, parent=cw)
        ov.adjustSize()
        ov.setGeometry(
            (cw.width()  - ov.width())  // 2,
            (cw.height() - ov.height()) // 2,
            ov.width(), ov.height(),
        )
        ov.show()
        ov.raise_()
        self._plugin_manager_overlay = ov   # keep a reference so it isn't GC'd

    def _open_plugin_settings(self):
        sections = self.get_plugin_settings() if self.get_plugin_settings else []
        cw = self.centralWidget()
        ov = PluginSettingsOverlay(sections, parent=cw)
        ow = PluginSettingsOverlay._OW
        oh = min(560, cw.height() - 16)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.show()
        ov.raise_()
        self._plugin_settings_overlay = ov   # keep a reference so it isn't GC'd

    # ── Clipboard intelligence ───────────────────────────────────────────────────

    def _on_clipboard_changed(self):
        try:
            text = QApplication.clipboard().text().strip()
            if len(text) >= 10:
                self._clipboard_sig.emit(text)
        except Exception:
            pass

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

    def _do_interrupt(self):
        if self.on_interrupt:
            self.on_interrupt()

    def _toggle_mute(self):
        # A deliberate press settles the question: whatever the video did, or is
        # about to do, the user has now said what they want.
        self._video_auto_muted = False
        self._set_muted(not self._muted)

    def _set_muted(self, muted: bool, note: str = ""):
        muted = bool(muted)
        if muted == self._muted:
            return
        self._muted = muted
        self.hud.muted = muted
        self._style_mute_btn()
        if muted:
            self._apply_state("MUTED")
            self._log.append_log("SYS: Microfone desligado." + (f" {note}" if note else ""))
        else:
            self._apply_state("LISTENING")
            self._log.append_log("SYS: Microfone ligado." + (f" {note}" if note else ""))

    def _style_mute_btn(self):
        tecla = QB.nome_da_tecla(QB.tecla("shortcut_mute"))
        if self._muted:
            self._mute_btn.setText(f"🔇  Mudo  ·  {tecla}")
            self._mute_btn.setToolTip("O microfone está desligado. Clique para ligar.")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.MUTED_C};
                    border: 1px solid {C.MUTED_C}; border-radius: 16px;
                }}
            """)
        else:
            self._mute_btn.setText(f"🎙  Ouvindo  ·  {tecla}")
            self._mute_btn.setToolTip("O microfone está ligado. Clique para silenciar.")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C.PANEL2}; color: {C.GREEN};
                    border: 1px solid {C.BORDER}; border-radius: 16px;
                }}
                QPushButton:hover {{ border: 1px solid {C.GREEN}; }}
            """)

    def _send(self):
        txt = self._input.text().strip()
        if not txt: return
        self._input.clear()
        self._log.append_log(f"You: {txt}")
        try:
            from core import isa as _isa
            _isa.registrar("entrada", txt, "você digitou", origem="texto")
        except Exception:
            pass
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(txt,), daemon=True).start()

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

    def _open_agenda(self, start: str = "notas") -> None:
        try:
            from .overlays.agenda import AgendaOverlay
            old = getattr(self, "_agenda_overlay", None)
            if old is not None:
                try:
                    old.hide(); old.deleteLater()
                except RuntimeError:
                    pass
            ov = AgendaOverlay(parent=self.centralWidget(), log=self.write_log, start=start)
            self._centre_overlay(ov)
            self._agenda_overlay = ov
        except Exception as e:
            self._log.append_log(f"ERR: A central de notas e lembretes não abriu — {e}")

    def _open_produtividade(self) -> None:
        """Painel Produtividade: tarefas, foco (Pomodoro) e projetos."""
        try:
            from .overlays.produtividade import ProdutividadeOverlay
            old = getattr(self, "_produtiv_overlay", None)
            if old is not None:
                try:
                    old.hide(); old.deleteLater()
                except RuntimeError:
                    pass
            ov = ProdutividadeOverlay(parent=self.centralWidget(), log=self.write_log)
            self._centre_overlay(ov)
            self._produtiv_overlay = ov
        except Exception as e:
            self._log.append_log(f"ERR: O painel de produtividade não abriu — {e}")

    def _open_isa_panel(self) -> None:
        """1.3 — Núcleo I.S.A.: o centro de decisões, ao vivo."""
        try:
            from .overlays.isa import IsaOverlay
            old = getattr(self, "_isa_overlay", None)
            if old is not None:
                try:
                    old._fechar()
                except RuntimeError:
                    pass
            ov = IsaOverlay(parent=self.centralWidget(),
                            estado=lambda: (self.hud.state, self._muted),
                            abrir_atuador=lambda: self._open_settings_panel("atuador"),
                            abrir_ia=lambda: self._open_ia_panel("areas"))
            self._centre_overlay(ov)
            self._isa_overlay = ov
        except Exception as e:
            self._log.append_log(f"ERR: O núcleo I.S.A. não abriu — {e}")

    def _open_ia_panel(self, aba: str = "areas") -> None:
        """Ultra 2026 — "Como a IA do NEXUS funciona": áreas da IA e tipos de IA."""
        try:
            from .overlays.ia_painel import IaPainelOverlay
            old = getattr(self, "_ia_overlay", None)
            if old is not None:
                try:
                    old._fechar()
                except RuntimeError:
                    pass
            ov = IaPainelOverlay(parent=self.centralWidget(), aba=aba or "areas")
            self._centre_overlay(ov)
            self._ia_overlay = ov
        except Exception as e:
            self._log.append_log(f"ERR: O painel da IA não abriu — {e}")

    # ── 1.4: modo ditado no Bloco de Notas ──────────────────────────────────

    def _toggle_ditado(self) -> None:
        """Botão 🎙 Ditado / Ctrl+D: liga ou desliga o ditado."""
        if self.on_toggle_ditado:
            threading.Thread(target=self.on_toggle_ditado, daemon=True).start()
            return
        # Ainda conectando: o ditado funciona sem o Gemini pela caixa de comando,
        # mas pela voz precisa da sessão.
        self._log.append_log("SYS: 📝 O ditado fica disponível assim que o NEXUS terminar de conectar.")

    def _ditado_pill(self) -> QPushButton:
        pill = getattr(self, "_ditado_btn", None)
        if pill is None:
            pill = QPushButton(self.hud)
            pill.setObjectName("ditadoPill")
            pill.setCursor(Qt.CursorShape.PointingHandCursor)
            pill.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
            pill.setFixedHeight(30)
            pill.clicked.connect(self._toggle_ditado)
            pill.hide()
            self._ditado_btn = pill
            self.hud.installEventFilter(self)
        tecla = QB.nome_da_tecla(QB.tecla("shortcut_ditado"))
        pill.setText(f"●  DITANDO NO BLOCO DE NOTAS   ·   parar ({tecla})")
        pill.setToolTip("Tudo o que você fala vai para o Bloco de Notas.\n"
                        "Diga “parar ditado” ou clique aqui para terminar.\n"
                        "Durante o ditado: “vírgula”, “ponto final”, “nova linha”, "
                        "“novo parágrafo”, “apaga a última frase”.")
        pill.setStyleSheet(f"""
            QPushButton#ditadoPill {{
                background: {C.PANEL}; color: {C.MUTED_C};
                border: 1px solid {C.MUTED_C}; border-radius: 14px;
                padding: 0 18px;
            }}
            QPushButton#ditadoPill:hover {{ background: {C.PRI_GHO}; color: {C.WHITE}; }}
        """)
        pill.adjustSize()
        return pill

    def _place_ditado_pill(self) -> None:
        pill = getattr(self, "_ditado_btn", None)
        if pill is None or not pill.isVisible():
            return
        pill.adjustSize()
        pill.move(max(6, (self.hud.width() - pill.width()) // 2), 12)
        pill.raise_()

    def eventFilter(self, obj, ev):
        try:
            if obj is self.hud and ev.type() == QEvent.Type.Resize:
                self._place_ditado_pill()
        except Exception:
            pass
        return super().eventFilter(obj, ev)

    def _on_ditado_mudou(self, ligado: bool) -> None:
        pill = self._ditado_pill()
        pill.setVisible(bool(ligado))
        self._ditando = bool(ligado)
        if ligado:
            self._place_ditado_pill()
        # o botão da barra rápida acompanha
        try:
            self._quickbar.set_active("ditado", bool(ligado))
        except Exception:
            pass

    def _open_quickbar_editor(self) -> None:
        from .overlays.quickbar_editor import QuickBarOverlay
        old = getattr(self, "_qb_overlay", None)
        if old is not None:
            try:
                old.hide(); old.deleteLater()
            except RuntimeError:
                pass
        ov = QuickBarOverlay(on_saved=self._rebuild_quickbar, parent=self.centralWidget())
        self._centre_overlay(ov)
        self._qb_overlay = ov

    def _open_shortcuts_panel(self) -> None:
        from .overlays.quickbar_editor import ShortcutsOverlay
        old = getattr(self, "_sc_overlay", None)
        if old is not None:
            try:
                old.hide(); old.deleteLater()
            except RuntimeError:
                pass
        ov = ShortcutsOverlay(on_saved=self._reload_shortcuts, parent=self.centralWidget())
        self._centre_overlay(ov)
        self._sc_overlay = ov

    def _quick_items(self) -> list[dict]:
        items = []
        for chave in QB.barra_atual():
            icone, nome, metodo, dica = QB.FERRAMENTAS[chave]
            fn = getattr(self, metodo, None)
            if fn is None:
                continue
            items.append({"icon": icone, "label": nome, "tooltip": dica, "callback": fn, "id": chave})
        for c in QB.comandos_atuais():
            items.append({"icon": "⚡", "label": c["label"], "kind": "command",
                          "tooltip": f"Pede ao NEXUS: “{c['command']}”",
                          "callback": (lambda cmd=c["command"]: self._quick_command(cmd))})
        for i, it in enumerate(items[:9], start=1):
            it["tooltip"] = f"{it['tooltip']}   (Alt+{i})"
        return items

    def _rebuild_quickbar(self) -> None:
        self._quick_list = self._quick_items()
        self._quickbar.build(self._quick_list)
        if getattr(self, "_ditando", False):
            self._quickbar.set_active("ditado", True)

    def _quick_command(self, cmd: str) -> None:
        self._log.append_log(f"You: {cmd}")
        try:
            from core import isa as _isa
            _isa.registrar("entrada", cmd, "comando rápido", origem="barra rápida")
        except Exception:
            pass
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(cmd,), daemon=True).start()

    def _run_quick(self, n: int) -> None:
        items = getattr(self, "_quick_list", [])
        if 0 <= n < len(items):
            items[n]["callback"]()

    def _install_shortcuts(self) -> None:
        for sc in getattr(self, "_shortcuts", []):
            sc.setEnabled(False)
            sc.deleteLater()
        self._shortcuts = []
        for chave, _rotulo, padrao, metodo in QB.ATALHOS:
            fn = getattr(self, metodo, None)
            seq = QKeySequence(QB.tecla(chave) or padrao)
            if fn is None or seq.isEmpty():
                continue
            sc = QShortcut(seq, self)
            sc.activated.connect(fn)
            self._shortcuts.append(sc)
        for i in range(9):
            sc = QShortcut(QKeySequence(f"Alt+{i + 1}"), self)
            sc.activated.connect(lambda n=i: self._run_quick(n))
            self._shortcuts.append(sc)
        self._refresh_shortcut_labels()

    def _reload_shortcuts(self) -> None:
        self._install_shortcuts()
        self._rebuild_quickbar()
        self._log.append_log("SYS: ⌨ Atalhos atualizados.")

    def _refresh_shortcut_labels(self) -> None:
        k = lambda chave: QB.nome_da_tecla(QB.tecla(chave))
        if hasattr(self, "_interrupt_btn"):
            self._interrupt_btn.setText(f"✋  Interromper  ·  {k('shortcut_interrupt')}")
        if hasattr(self, "_mute_btn") and hasattr(self, "_muted"):
            self._style_mute_btn()
        if hasattr(self, "_fs_btn"):
            self._fs_btn.setText(f"⛶  TELA CHEIA  [{k('shortcut_fullscreen')}]")
        if hasattr(self, "_footer_keys"):
            self._footer_keys.setText(
                f"[{k('shortcut_mute')}] Microfone   ·   [{k('shortcut_fullscreen')}] Tela cheia   ·   "
                f"[{k('shortcut_agenda')}] Notas   ·   [{k('shortcut_commands')}] Comandos")
        if hasattr(self, "_input"):
            self._input.setToolTip(f"Digite e aperte Enter. Atalho para vir aqui: {k('shortcut_command')}")

    def _check_config(self) -> bool:
        if not API_FILE.exists(): return False
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8"))
            return bool(d.get("gemini_api_key")) and bool(d.get("os_system"))
        except Exception:
            return False

    @staticmethod
    def _license_check() -> dict:
        """Estado da licença. Se o módulo faltar ou quebrar, NÃO libera: erro vira bloqueio."""
        try:
            from core import licenca
            return licenca.status()
        except Exception as e:
            return {"valida": False, "motivo": f"Não foi possível conferir a licença ({e}).",
                    "nome": "", "ate": "", "dias": None}

    def _show_license(self, motivo: str = ""):
        try:
            self._show_license_overlay(motivo)
        except Exception as e:  # nunca deixar o NEXUS "mudo": sem tela, sem como ativar
            print(f"[Licença] tela de ativação falhou ({e}); usando a caixa simples.")
            self._license_fallback_dialog(motivo)

    def _license_fallback_dialog(self, motivo: str = ""):
        from PyQt6.QtWidgets import QInputDialog
        from core import licenca
        texto = ((motivo + "\n\n") if motivo and "Nenhuma" not in motivo else "") + \
            f"ID deste computador: {licenca.id_da_maquina()}\n\nCole a chave de licença:"
        while True:
            chave, ok = QInputDialog.getMultiLineText(self, "Ativar o NEXUS Ultra 2026", texto)
            if not ok:
                self._quit_unlicensed()
                return
            ativou, msg = licenca.ativar(chave)
            if ativou:
                self._on_license_ok()
                return
            texto = msg + "\n\nID deste computador: " + licenca.id_da_maquina() + "\n\nCole a chave de licença:"

    def _recentrar_licenca(self):
        """Centraliza a tela de ativação (cabe em janela pequena também)."""
        lic = getattr(self, "_license_overlay", None)
        if lic is None:
            return
        cw = self.centralWidget()
        ow = min(520, max(320, cw.width() - 20))
        oh = min(470, max(380, cw.height() - 20))
        lic.setGeometry(max(0, (cw.width() - ow) // 2), max(0, (cw.height() - oh) // 2), ow, oh)

    def _show_license_overlay(self, motivo: str = ""):
        ov = LicencaOverlay(motivo, self.centralWidget())
        ov.ativada.connect(self._on_license_ok)
        ov.sair.connect(self._quit_unlicensed)
        self._license_overlay = ov
        self._recentrar_licenca()
        ov.show()
        ov.raise_()
        # o tamanho real do centro só existe depois que a janela aparece e o
        # layout assenta: recentra logo depois (e de novo, por segurança)
        QTimer.singleShot(0, self._recentrar_licenca)
        QTimer.singleShot(250, self._recentrar_licenca)

    def _quit_unlicensed(self):
        self._really_quit = True
        if self._tray is not None:
            self._tray.hide()
        self.close()
        QApplication.quit()

    def _on_license_ok(self):
        self._licensed = True
        ov = getattr(self, "_license_overlay", None)
        if ov is not None:
            ov.hide()
            ov.deleteLater()
            self._license_overlay = None
        if self._check_config():
            self._ready = True
            self._apply_state("LISTENING")
            self._assistant_name = _read_full_config().get("assistant_name", "NEXUS") or "NEXUS"
            self._log.append_log(f"SYS: Licença ativada. {self._assistant_name} online.")
        else:
            self._show_setup()

    def _show_setup(self):
        ov = SetupOverlay(self.centralWidget())
        cw = self.centralWidget()
        ow, oh = 460, 390
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.done.connect(self._on_setup_done)
        ov.show()
        self._overlay = ov

    def _on_setup_done(self, key: str, os_name: str):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        API_FILE.write_text(
            json.dumps({"gemini_api_key": key, "os_system": os_name}, indent=4),
            encoding="utf-8",
        )
        self._ready = True
        if self._overlay:
            self._overlay.hide()
            self._overlay = None
        self._apply_state("LISTENING")
        self._assistant_name = _read_full_config().get("assistant_name", "NEXUS") or "NEXUS"
        self._log.append_log(f"SYS: Pronto. Sistema: {os_name.upper()}. {self._assistant_name} online.")
