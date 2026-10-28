"""Painel de privacidade (NEXUS Ultra 2026 3.3) — botão 🔒 Privacidade dentro da I.S.A.

Três blocos: o que o NEXUS guarda no PC (com tamanho e data), o que sai do computador, e um botão
"Apagar" em cada item — que sempre pede confirmação antes. Tudo vem de core/privacidade.py.
"""
from __future__ import annotations

from .._qt import *  # noqa: F401,F403
from .._base import C, FONT_MAIN  # noqa: F401
from ..overlays.base import _HudOverlay  # noqa: F401


def _f(size: float, bold: bool = False) -> QFont:
    f = QFont(FONT_MAIN)
    f.setPointSizeF(size)
    if bold:
        f.setWeight(QFont.Weight.DemiBold)
    return f


class PrivacidadeOverlay(_HudOverlay):
    _OW = 780
    _OH = 640

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Privacidade")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            QWidget#Privacidade {{ background: {C.DARK}; border: 1px solid {C.BORDER_B}; border-radius: 14px; }}
            QLabel {{ background: transparent; border: none; }}
            QFrame#card {{ background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 11px; }}
            QPushButton#sec {{ background: transparent; color: {C.TEXT_MED}; border: 1px solid {C.BORDER};
                border-radius: 9px; padding: 0 11px; }}
            QPushButton#sec:hover {{ color: {C.WHITE}; border-color: {C.BORDER_B}; }}
            QPushButton#perigo {{ background: transparent; color: {C.RED}; border: 1px solid {C.RED};
                border-radius: 9px; padding: 0 11px; }}
            QPushButton#perigo:hover {{ color: {C.WHITE}; background: {C.RED}; }}
            QPushButton#x {{ background: transparent; color: {C.TEXT_DIM}; border: none; border-radius: 6px; }}
            QPushButton#x:hover {{ color: {C.WHITE}; background: {C.PRI_GHO}; }}
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: transparent; width: 7px; }}
            QScrollBar::handle:vertical {{ background: {C.BORDER_B}; border-radius: 3px; min-height: 26px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        self.setFixedSize(self._OW, min(self._OH, max(460, (parent.height() - 16) if parent else self._OH)))
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(22, 14, 22, 16)
        self._lay.setSpacing(10)

        topo = QHBoxLayout()
        tit = QVBoxLayout()
        tit.setSpacing(1)
        t = QLabel("🔒  Privacidade")
        t.setFont(_f(15, True))
        t.setStyleSheet(f"color: {C.WHITE};")
        sub = QLabel("O que o NEXUS guarda, o que sai do computador e como apagar")
        sub.setFont(_f(8.4))
        sub.setStyleSheet(f"color: {C.TEXT_DIM};")
        tit.addWidget(t)
        tit.addWidget(sub)
        topo.addLayout(tit, 1)
        x = QPushButton("✕")
        x.setObjectName("x")
        x.setFixedSize(28, 28)
        x.setCursor(Qt.CursorShape.PointingHandCursor)
        x.clicked.connect(self._fechar)
        topo.addWidget(x, 0, Qt.AlignmentFlag.AlignTop)
        self._lay.addLayout(topo)

        self._area = QScrollArea()
        self._area.setWidgetResizable(True)
        self._area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._area.viewport().setObjectName("ivp")
        self._area.viewport().setStyleSheet("QWidget#ivp { background: transparent; }")
        self._lay.addWidget(self._area, 1)
        self._montar()

    def _rot(self, texto: str, tam: float, cor: str, negrito: bool = False, quebra: bool = True) -> QLabel:
        lb = QLabel(texto)
        lb.setFont(_f(tam, negrito))
        lb.setWordWrap(quebra)
        lb.setStyleSheet(f"color: {cor};")
        return lb

    def _card(self, v) -> QVBoxLayout:
        fr = QFrame()
        fr.setObjectName("card")
        inner = QVBoxLayout(fr)
        inner.setContentsMargins(16, 12, 16, 12)
        inner.setSpacing(6)
        v.addWidget(fr)
        return inner

    def _montar(self) -> None:
        from core import privacidade as P
        host = QWidget()
        host.setObjectName("ihost")
        host.setStyleSheet("QWidget#ihost { background: transparent; }")
        v = QVBoxLayout(host)
        v.setContentsMargins(0, 0, 6, 0)
        v.setSpacing(10)

        c = self._card(v)
        c.addWidget(self._rot("GUARDADO NO SEU COMPUTADOR", 8.2, C.TEXT_MED, True, False))
        itens = P.estado()
        if not any(e["existe"] for e in itens):
            c.addWidget(self._rot("Ainda não guardei nada.", 9, C.TEXT_DIM))
        for e in itens:
            if not e["existe"]:
                continue
            linha = QHBoxLayout()
            col = QVBoxLayout()
            col.setSpacing(0)
            col.addWidget(self._rot(e["nome"], 9, C.WHITE, True, False))
            col.addWidget(self._rot(f"{e['o_que']} · {e['tamanho']} · mudou em {e['mudou']}", 7.8, C.TEXT_DIM))
            linha.addLayout(col, 1)
            b = QPushButton("Apagar")
            b.setObjectName("perigo")
            b.setFixedHeight(26)
            b.setFont(_f(8, True))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, ch=e["chave"], nome=e["nome"]: self._apagar(ch, nome))
            linha.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
            c.addLayout(linha)

        c2 = self._card(v)
        c2.addWidget(self._rot("O QUE SAI DO COMPUTADOR", 8.2, C.TEXT_MED, True, False))
        for titulo, desc in P.SAI_DO_PC:
            c2.addWidget(self._rot(titulo, 8.8, C.WHITE, True, False))
            c2.addWidget(self._rot(desc, 8.2, C.TEXT_MED))
        v.addStretch(1)
        self._area.setWidget(host)

    def _apagar(self, chave: str, nome: str) -> None:
        resp = QMessageBox.question(
            self, "Apagar", f"Apagar “{nome}”? Isso não pode ser desfeito.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if resp != QMessageBox.StandardButton.Yes:
            return
        try:
            from core import privacidade as P
            P.apagar(chave, confirmar=True)
        except Exception:
            pass
        self._montar()

    def _fechar(self) -> None:
        self.hide()
        self.deleteLater()
