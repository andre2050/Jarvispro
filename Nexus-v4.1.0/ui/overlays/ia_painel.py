"""Painel "Como a IA do NEXUS funciona" (NEXUS Ultra 2026).

Duas abas:
  • ÁREAS DA IA — machine learning, aprendizado profundo, linguagem natural e
    visão computacional: o que cada uma é e o que o NEXUS tem de verdade agora;
  • TIPOS DE IA — por nível (ANI · AGI · ASI) e por funcionamento (reativa ·
    memória limitada · teoria da mente), dizendo o que existe hoje e onde o
    NEXUS se encaixa.

Tudo vem de core/ia_status.py. O estado é lido em segundo plano (alguns itens
consultam o Ollama), então o painel abre na hora; nada sai do computador.
"""
from __future__ import annotations

import threading

from .._qt import *  # noqa: F401,F403
from .._base import C, FONT_MAIN  # noqa: F401
from ..overlays.base import _HudOverlay  # noqa: F401


def _f(size: float, bold: bool = False, spacing: float = 0.0) -> QFont:
    f = QFont(FONT_MAIN)
    f.setPointSizeF(size)
    if bold:
        f.setWeight(QFont.Weight.DemiBold)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return f


def _rotulo(texto: str, tam: float, cor: str, negrito: bool = False, quebra: bool = True) -> QLabel:
    lb = QLabel(texto)
    lb.setFont(_f(tam, negrito))
    lb.setWordWrap(quebra)
    lb.setStyleSheet(f"color: {cor};")
    return lb


class IaPainelOverlay(_HudOverlay):
    _OW = 780
    _OH = 640
    _estado_pronto = pyqtSignal(object)

    def __init__(self, parent=None, aba: str = "areas"):
        super().__init__(parent)
        self._areas_lay: QVBoxLayout | None = None
        self._vivo = True
        self.setObjectName("IaPainel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            QWidget#IaPainel {{ background: {C.DARK}; border: 1px solid {C.BORDER_B}; border-radius: 14px; }}
            QLabel {{ background: transparent; border: none; }}
            QFrame#card {{ background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 11px; }}
            QPushButton#chip {{ background: transparent; color: {C.TEXT_MED}; border: 1px solid {C.BORDER};
                border-radius: 12px; padding: 0 14px; }}
            QPushButton#chip:hover {{ color: {C.WHITE}; border-color: {C.BORDER_B}; }}
            QPushButton#chip:checked {{ color: {C.BG}; background: {C.PRI}; border-color: {C.PRI}; }}
            QPushButton#x {{ background: transparent; color: {C.TEXT_DIM}; border: none; border-radius: 6px; }}
            QPushButton#x:hover {{ color: {C.WHITE}; background: {C.PRI_GHO}; }}
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: transparent; width: 7px; }}
            QScrollBar::handle:vertical {{ background: {C.BORDER_B}; border-radius: 3px; min-height: 26px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        altura = min(self._OH, max(460, (parent.height() - 16) if parent else self._OH))
        self.setFixedSize(self._OW, altura)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 14, 22, 16)
        lay.setSpacing(10)

        topo = QHBoxLayout()
        tit = QVBoxLayout()
        tit.setSpacing(1)
        t = QLabel("🧬  Como a IA do NEXUS funciona")
        t.setFont(_f(15, True))
        t.setStyleSheet(f"color: {C.WHITE};")
        self._sub = QLabel("Dados, algoritmos e poder computacional — e o que o NEXUS tem de cada um")
        self._sub.setFont(_f(8.4))
        self._sub.setStyleSheet(f"color: {C.TEXT_DIM};")
        tit.addWidget(t)
        tit.addWidget(self._sub)
        topo.addLayout(tit, 1)
        x = QPushButton("✕")
        x.setObjectName("x")
        x.setFixedSize(28, 28)
        x.setCursor(Qt.CursorShape.PointingHandCursor)
        x.clicked.connect(self._fechar)
        topo.addWidget(x, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(topo)

        abas = QHBoxLayout()
        abas.setSpacing(6)
        self._chips: dict[str, QPushButton] = {}
        for chave, rotulo in (("areas", "ÁREAS DA IA"), ("tipos", "TIPOS DE IA")):
            b = QPushButton(rotulo)
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setFixedHeight(26)
            b.setFont(_f(8, True, 1.0))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=chave: self._trocar(k))
            self._chips[chave] = b
            abas.addWidget(b)
        abas.addStretch(1)
        lay.addLayout(abas)

        self._area = QScrollArea()
        self._area.setWidgetResizable(True)
        self._area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._area.viewport().setObjectName("ivp")
        self._area.viewport().setStyleSheet("QWidget#ivp { background: transparent; }")
        lay.addWidget(self._area, 1)

        self._estado_pronto.connect(self._mostrar_areas)
        self.destroyed.connect(lambda *_: setattr(self, "_vivo", False))
        self._trocar(aba if aba in self._chips else "areas")

    # ── abas ────────────────────────────────────────────────────────────────

    def _trocar(self, aba: str) -> None:
        for k, b in self._chips.items():
            b.setChecked(k == aba)
        host = QWidget()
        host.setObjectName("ihost")
        host.setStyleSheet("QWidget#ihost { background: transparent; }")
        v = QVBoxLayout(host)
        v.setContentsMargins(0, 0, 6, 0)
        v.setSpacing(8)
        self._area.setWidget(host)
        if aba == "areas":
            self._montar_areas(v)
        else:
            self._montar_tipos(v)
            v.addStretch(1)

    def _card(self, v: QVBoxLayout) -> QVBoxLayout:
        fr = QFrame()
        fr.setObjectName("card")
        inner = QVBoxLayout(fr)
        inner.setContentsMargins(16, 12, 16, 12)
        inner.setSpacing(5)
        v.addWidget(fr)
        return inner

    # ── ÁREAS ───────────────────────────────────────────────────────────────

    def _montar_areas(self, v: QVBoxLayout) -> None:
        try:
            from core import ia_status as st
        except Exception:
            v.addWidget(_rotulo("Não consegui carregar o estado da IA.", 9, C.RED))
            v.addStretch(1)
            return
        v.addWidget(_rotulo(st.BASE, 8.8, C.TEXT_MED))
        self._areas_lay = v
        self._carregando = _rotulo("Lendo o estado dos módulos…", 8.8, C.TEXT_DIM)
        v.addWidget(self._carregando)
        v.addStretch(1)

        def _ler():
            try:
                dados = st.tudo()
            except Exception:
                dados = []
            if self._vivo:
                try:
                    self._estado_pronto.emit(dados)
                except RuntimeError:
                    pass
        threading.Thread(target=_ler, daemon=True, name="ia-painel").start()

    def _mostrar_areas(self, areas) -> None:
        v = self._areas_lay
        if v is None or not self._chips["areas"].isChecked():
            return
        try:
            self._carregando.hide()
        except RuntimeError:
            return
        # as cartas entram antes do espaço elástico final
        pos = max(0, v.count() - 1)
        for a in areas:
            fr = QFrame()
            fr.setObjectName("card")
            inner = QVBoxLayout(fr)
            inner.setContentsMargins(16, 12, 16, 12)
            inner.setSpacing(5)
            cab = QHBoxLayout()
            cab.addWidget(_rotulo(f"{a.icone}  {a.titulo.upper()}", 9.6, C.WHITE, True, False))
            cab.addStretch(1)
            ok, total = a.prontos
            if total:
                cor = C.GREEN if ok == total else C.TEXT_MED
                cab.addWidget(_rotulo(f"{ok} de {total} prontas", 8.2, cor, True, False))
            inner.addLayout(cab)
            inner.addWidget(_rotulo(a.resumo, 8.6, C.TEXT_MED))
            inner.addWidget(_rotulo("No NEXUS: " + a.no_nexus, 8.6, C.PRI))
            for it in a.itens:
                linha = QHBoxLayout()
                marca, cor = ("●", C.GREEN) if it.ok else (("○", C.TEXT_DIM) if it.ok is False else ("·", C.TEXT_DIM))
                linha.addWidget(_rotulo(marca, 8.6, cor, True, False))
                linha.addWidget(_rotulo(it.nome, 8.6, C.TEXT_DIM, False, False))
                val = _rotulo(it.valor, 8.6, C.WHITE, True)
                val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                linha.addWidget(val, 1)
                inner.addLayout(linha)
            v.insertWidget(pos, fr)
            pos += 1

    # ── TIPOS ───────────────────────────────────────────────────────────────

    def _montar_tipos(self, v: QVBoxLayout) -> None:
        from core import ia_status as st
        grupos = (("POR NÍVEL DE INTELIGÊNCIA", st.TIPOS_CAPACIDADE),
                  ("POR COMO FUNCIONA", st.TIPOS_FUNCAO))
        for titulo, tipos in grupos:
            v.addWidget(_rotulo(titulo, 7.6, C.TEXT_MED, True, False))
            for t in tipos:
                inner = self._card(v)
                cab = QHBoxLayout()
                nome = f"{t.titulo}  ·  {t.sigla}" if t.sigla else t.titulo
                cab.addWidget(_rotulo(nome, 9.6, C.WHITE, True, False))
                cab.addStretch(1)
                cab.addWidget(_rotulo("existe hoje" if t.existe else "ainda não existe", 8.2,
                                      C.GREEN if t.existe else C.TEXT_DIM, True, False))
                inner.addLayout(cab)
                inner.addWidget(_rotulo(t.resumo, 8.6, C.TEXT_MED))
                inner.addWidget(_rotulo("Exemplos: " + t.exemplos, 8.4, C.TEXT_DIM))
                if t.risco:
                    inner.addWidget(_rotulo("Riscos: " + t.risco, 8.4, C.TEXT_DIM))
                inner.addWidget(_rotulo("No NEXUS: " + t.nexus, 8.6, C.PRI))

    # ── fechar ──────────────────────────────────────────────────────────────

    def _fechar(self) -> None:
        self._vivo = False
        self.hide()
        self.deleteLater()
