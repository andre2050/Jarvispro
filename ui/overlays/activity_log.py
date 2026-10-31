"""Log de atividades com filtro — lê memory/activity.log."""
import re
from pathlib import Path

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QComboBox, QPushButton, QTextEdit, QMessageBox)
from core.protecao import engolida as _engolida

# project root = two folders up (this file lives in ui/overlays/)
_FILE = Path(__file__).resolve().parents[2] / "memory" / "activity.log"
_CAT = re.compile(r"\| ([A-Z]+):")
_CSS = """
#ActivityLog { background: #0b1620; border: 1px solid #1d3b4f; border-radius: 8px; }
QLabel { color: #cfe8ff; font-size: 11px; }
QLineEdit, QComboBox, QTextEdit { background: #0f2230; color: #cfe8ff;
    border: 1px solid #1d3b4f; border-radius: 4px; padding: 4px; }
QPushButton { background: #0f2230; color: #00d4ff; border: 1px solid #1d3b4f;
    border-radius: 5px; padding: 6px 12px; font-size: 10px; }
QPushButton:hover { border-color: #00d4ff; }
"""
_CATEGORIES = ["Todos", "SYS", "ERR", "FILE", "QUIZ", "outros"]


class ActivityLogOverlay(QWidget):
    _OW, _OH = 640, 460

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ActivityLog")
        self.setStyleSheet(_CSS)
        self.setFixedSize(self._OW, self._OH)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        title = QLabel("LOG DE ATIVIDADES")
        title.setStyleSheet("color:#00d4ff; font-size:13px; letter-spacing:3px;")
        root.addWidget(title)

        row = QHBoxLayout()
        self._text = QLineEdit()
        self._text.setPlaceholderText("Filtrar por texto...")
        self._text.textChanged.connect(self.refresh)
        self._cat = QComboBox()
        self._cat.addItems(_CATEGORIES)
        self._cat.currentIndexChanged.connect(self.refresh)
        row.addWidget(self._text, 1)
        row.addWidget(self._cat)
        root.addLayout(row)

        self._view = QTextEdit()
        self._view.setReadOnly(True)
        root.addWidget(self._view, 1)

        bar = QHBoxLayout()
        self._count = QLabel("")
        clear = QPushButton("LIMPAR LOG")
        clear.clicked.connect(self._clear)
        close = QPushButton("FECHAR")
        close.clicked.connect(self.hide)
        bar.addWidget(self._count, 1)
        bar.addWidget(clear)
        bar.addWidget(close)
        root.addLayout(bar)

        self.refresh()

    def refresh(self):
        try:
            lines = _FILE.read_text(encoding="utf-8").splitlines()[-2000:]
        except Exception:
            lines = []
        cat = self._cat.currentText()
        query = self._text.text().strip().lower()
        shown = []
        for line in lines:
            m = _CAT.search(line)
            kind = m.group(1) if m else "outros"
            if cat != "Todos" and kind != cat:
                continue
            if query and query not in line.lower():
                continue
            shown.append(line)
        self._view.setPlainText("\n".join(shown[-500:]) or "Nada encontrado.")
        self._count.setText(f"{len(shown)} linha(s)")

    def _clear(self):
        if QMessageBox.question(self, "Limpar log", "Apagar todo o log de atividades?") \
                != QMessageBox.StandardButton.Yes:
            return
        try:
            _FILE.write_text("", encoding="utf-8")
        except Exception:
            _engolida("ui/overlays/activity_log.py:92")
        self.refresh()
