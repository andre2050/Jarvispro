"""Tela de ativação da licença (NEXUS Ultra 2026 1.5).

Aparece na abertura quando não há licença válida. Mostra o ID deste
computador (para o cliente mandar ao desenvolvedor) e recebe a chave."""
from __future__ import annotations

from .._qt import *  # noqa: F401,F403
from .._base import C, FONT_MAIN  # noqa: F401


class LicencaOverlay(QWidget):
    ativada = pyqtSignal()
    sair = pyqtSignal()

    def __init__(self, motivo: str = "", parent=None):
        super().__init__(parent)
        from core import licenca
        self._lic = licenca

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            LicencaOverlay {{
                background: rgba(8, 10, 28, 250);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(30, 22, 30, 22)
        lay.setSpacing(8)

        def _lbl(txt, size=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter, wrap=False):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setWordWrap(wrap)
            w.setFont(QFont(FONT_MAIN, size,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        lay.addWidget(_lbl("◈  ATIVAR O NEXUS ULTRA 2026", 13, True))
        lay.addWidget(_lbl("Digite a chave de licença que você recebeu.", 9,
                           color=C.PRI_DIM))
        if motivo and "Nenhuma" not in motivo:
            lay.addWidget(_lbl(motivo, 9, True, C.RED, wrap=True))
        lay.addSpacing(4)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};"); lay.addWidget(sep)

        lay.addWidget(_lbl("ID DESTE COMPUTADOR", 8, color=C.TEXT_DIM,
                           align=Qt.AlignmentFlag.AlignLeft))
        linha = QHBoxLayout(); linha.setSpacing(6)
        self._id_lbl = _lbl(licenca.id_da_maquina(), 12, True, C.ACC2,
                            align=Qt.AlignmentFlag.AlignLeft)
        self._id_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        linha.addWidget(self._id_lbl, 1)
        b_copiar = QPushButton("COPIAR ID")
        b_copiar.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        b_copiar.setFixedHeight(26)
        b_copiar.setCursor(Qt.CursorShape.PointingHandCursor)
        b_copiar.setStyleSheet(self._estilo_botao())
        b_copiar.clicked.connect(self._copiar_id)
        linha.addWidget(b_copiar)
        lay.addLayout(linha)
        lay.addWidget(_lbl("Se a sua licença é presa a um computador, mande este ID "
                           "para quem vendeu o NEXUS.", 8, color=C.TEXT_DIM,
                           align=Qt.AlignmentFlag.AlignLeft, wrap=True))
        lay.addSpacing(4)

        lay.addWidget(_lbl("CHAVE DE LICENÇA", 8, color=C.TEXT_DIM,
                           align=Qt.AlignmentFlag.AlignLeft))
        self._chave = QTextEdit()
        self._chave.setAcceptRichText(False)
        self._chave.setPlaceholderText("NEXUS-XXXXX-XXXXX-XXXXX-…")
        self._chave.setFont(QFont("Courier New", 9))
        self._chave.setFixedHeight(84)
        self._chave.setStyleSheet(f"""
            QTextEdit {{
                background: {C.BG}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 8px;
            }}
            QTextEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        lay.addWidget(self._chave)

        self._msg = _lbl("", 9, True, C.RED, wrap=True)
        lay.addWidget(self._msg)

        b_ativar = QPushButton("▸  ATIVAR")
        b_ativar.setFont(QFont(FONT_MAIN, 10, QFont.Weight.Bold))
        b_ativar.setFixedHeight(36)
        b_ativar.setCursor(Qt.CursorShape.PointingHandCursor)
        b_ativar.setStyleSheet(self._estilo_botao())
        b_ativar.clicked.connect(self._ativar)
        lay.addWidget(b_ativar)

        b_sair = QPushButton("Sair")
        b_sair.setFont(QFont(FONT_MAIN, 8))
        b_sair.setFixedHeight(24)
        b_sair.setCursor(Qt.CursorShape.PointingHandCursor)
        b_sair.setStyleSheet(f"QPushButton {{ background: transparent; color: {C.TEXT_DIM};"
                             f" border: none; }} QPushButton:hover {{ color: {C.TEXT}; }}")
        b_sair.clicked.connect(self.sair.emit)
        lay.addWidget(b_sair)

    @staticmethod
    def _estilo_botao() -> str:
        return f"""
            QPushButton {{
                background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
        """

    def _copiar_id(self) -> None:
        QApplication.clipboard().setText(self._id_lbl.text())
        self._msg.setStyleSheet(f"color: {C.GREEN}; background: transparent;")
        self._msg.setText("ID copiado.")

    def _ativar(self) -> None:
        texto = self._chave.toPlainText().strip()
        if not texto:
            self._msg.setStyleSheet(f"color: {C.RED}; background: transparent;")
            self._msg.setText("Cole a chave de licença no campo acima.")
            return
        ok, msg = self._lic.ativar(texto)
        if ok:
            self._msg.setStyleSheet(f"color: {C.GREEN}; background: transparent;")
            self._msg.setText(msg)
            self.ativada.emit()
        else:
            self._msg.setStyleSheet(f"color: {C.RED}; background: transparent;")
            self._msg.setText(msg)
