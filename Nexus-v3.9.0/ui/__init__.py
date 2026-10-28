"""NEXUS user interface (package).

Everything that used to live in the single ui.py, split by area. Every
top-level name is re-exported here, so `import ui`, `ui.C` and
`from ui import NexusUI` keep working exactly as before."""
from __future__ import annotations

from ._qt import *  # noqa: F401,F403
from ._qt import _WIN_HIDE  # noqa: F401
from ._base import API_FILE, APP_PROTOCOL, APP_VERSION, BASE_DIR, C, CONFIG_DIR, DEFAULT_UI_COLOR, FONT_MAIN, FONT_MONO, _DEFAULT_H, _DEFAULT_W, _DT, _HUE_LINKED, _LEFT_W, _MIN_H, _MIN_W, _OS, _PALETTE_DEFAULTS, _RIGHT_W, _SysMetrics, _base_dir, _bg_color, _dt_now, _metrics, _nvml_gpu_windows, _nvml_lib, _nvml_ok, _persist_activity, _pref_key, _read_full_config, _shortcut_seq, agora, apply_ui_accent, current_palette, data_curta, de_timestamp, qcol, retheme_all_widgets  # noqa: F401
from ._base import LEGACY_DEFAULT_COLORS, accent2, mix  # noqa: F401
from .hud import HudCanvas, MetricBar  # noqa: F401
from .widgets import ClipboardPanel, FileDropZone, HueWheel, LogWidget, _CameraPreview, _DropCanvas, _EXT_TO_CAT, _FILE_ICONS, _file_category, _fmt_size  # noqa: F401
from .overlays.setup import SetupOverlay  # noqa: F401
from .overlays.customize import CustomizeOverlay  # noqa: F401
from .overlays.base import _HudOverlay  # noqa: F401
from .overlays.panels import AudioDeviceOverlay, ConfirmBanner, MemoryOverlay, PluginManagerOverlay  # noqa: F401
from .overlays.tools import ClipOverlay, CommandsOverlay, IntelOverlay, NotesOverlay, VisionOverlay  # noqa: F401
from .overlays.remote import PluginSettingsOverlay, RemoteKeyOverlay  # noqa: F401
from .overlays.settings import SettingsPanelOverlay  # noqa: F401
from .main_window import MainWindow  # noqa: F401
from .app import NexusUI, _RootShim  # noqa: F401
