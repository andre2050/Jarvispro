"""Painel de latência (NEXUS Ultra 2026 3.3) — botão ⏱ Latência dentro da I.S.A.

Mostra onde o tempo vai em cada pedido, do FIM da sua fala até o NEXUS COMEÇAR A FALAR:
  • indicadores: tempo típico, 90% dos casos, pedidos medidos, respostas vindas do cache;
  • a média de cada etapa (escutar · preparar · rota · modelo · ferramenta), com o maior gargalo e o que fazer;
  • os últimos pedidos, uma barra empilhada por pedido.

Tudo vem de core/latencia.py (memory/latencia.json); nada sai do computador.
"""
from __future__ import annotations

from .._qt import *  # noqa: F401,F403
from .._base import C, FONT_MAIN, qcol  # noqa: F401
from ..overlays.base import _HudOverlay  # noqa: F401
from core.protecao import engolida as _engolida


def _f(size: float, bold: bool = False) -> QFont:
    f = QFont(FONT_MAIN)
    f.setPointSizeF(size)
    if bold:
        f.setWeight(QFont.Weight.DemiBold)
    return f


def _s(ms) -> str:
    if ms is None:
        return "—"
    return f"{ms / 1000:.1f} s".replace(".", ",") if ms >= 1000 else f"{int(ms)} ms"


def _cor_etapa(etapa: str) -> str:
    return {"escutar": C.ACC, "preparar": C.TEXT_MED, "rota": C.GREEN,
            "modelo": C.PRI, "ferramenta": C.ACC2}.get(etapa, C.TEXT_DIM)


class BarraEtapas(QWidget):
    """Uma barra empilhada: cada etapa com a sua cor, proporcional ao tempo (escala comum entre as linhas)."""

    def __init__(self, etapas: dict, escala_ms: float, altura: int = 12, parent=None):
        super().__init__(parent)
        self._et, self._escala = dict(etapas), max(1.0, float(escala_ms))
        self.setFixedHeight(altura)
        self.setMinimumWidth(120)

    def paintEvent(self, _e):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qcol(C.PANEL2))
        p.drawRoundedRect(0, 0, w, h, 3, 3)
        x = 0.0
        from core.latencia import ETAPAS
        for e in ETAPAS:
            ms = self._et.get(e)
            if not ms:
                continue
            largura = max(1.5, w * float(ms) / self._escala)
            p.setBrush(qcol(_cor_etapa(e)))
            p.drawRoundedRect(int(x), 0, int(min(largura, w - x)), h, 3, 3)
            x += largura
            if x >= w:
                break
        p.end()


class LatenciaOverlay(_HudOverlay):
    _OW = 780
    _OH = 640

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Latencia")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            QWidget#Latencia {{ background: {C.DARK}; border: 1px solid {C.BORDER_B}; border-radius: 14px; }}
            QLabel {{ background: transparent; border: none; }}
            QFrame#tile, QFrame#card {{ background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 11px; }}
            QPushButton#sec {{ background: transparent; color: {C.TEXT_MED}; border: 1px solid {C.BORDER};
                border-radius: 9px; padding: 0 11px; }}
            QPushButton#sec:hover {{ color: {C.WHITE}; border-color: {C.BORDER_B}; }}
            QPushButton#x {{ background: transparent; color: {C.TEXT_DIM}; border: none; border-radius: 6px; }}
            QPushButton#x:hover {{ color: {C.WHITE}; background: {C.PRI_GHO}; }}
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: transparent; width: 7px; }}
            QScrollBar::handle:vertical {{ background: {C.BORDER_B}; border-radius: 3px; min-height: 26px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        altura = min(self._OH, max(460, (parent.height() - 16) if parent else self._OH))
        self.setFixedSize(self._OW, altura)

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(22, 14, 22, 16)
        self._lay.setSpacing(10)

        topo = QHBoxLayout()
        tit = QVBoxLayout()
        tit.setSpacing(1)
        t = QLabel("⏱  Latência")
        t.setFont(_f(15, True))
        t.setStyleSheet(f"color: {C.WHITE};")
        sub = QLabel("Do fim da sua fala até o NEXUS começar a falar — onde o tempo vai")
        sub.setFont(_f(8.4))
        sub.setStyleSheet(f"color: {C.TEXT_DIM};")
        tit.addWidget(t)
        tit.addWidget(sub)
        topo.addLayout(tit, 1)
        limpar = QPushButton("Limpar")
        limpar.setObjectName("sec")
        limpar.setFixedHeight(26)
        limpar.setFont(_f(8, True))
        limpar.setCursor(Qt.CursorShape.PointingHandCursor)
        limpar.clicked.connect(self._limpar)
        topo.addWidget(limpar, 0, Qt.AlignmentFlag.AlignTop)
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

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._montar)
        self._tmr.start(5000)
        self._montar()

    # ── montagem ────────────────────────────────────────────────────────────
    def _rot(self, texto: str, tam: float, cor: str, negrito: bool = False, quebra: bool = True) -> QLabel:
        lb = QLabel(texto)
        lb.setFont(_f(tam, negrito))
        lb.setWordWrap(quebra)
        lb.setStyleSheet(f"color: {cor};")
        return lb

    def _tile(self, lay, rotulo: str, valor: str, sub: str = "") -> None:
        fr = QFrame()
        fr.setObjectName("tile")
        v = QVBoxLayout(fr)
        v.setContentsMargins(14, 9, 14, 10)
        v.setSpacing(1)
        v.addWidget(self._rot(rotulo, 6.8, C.TEXT_DIM, True, False))
        v.addWidget(self._rot(valor, 15, C.WHITE, True, False))
        v.addWidget(self._rot(sub, 7.6, C.TEXT_MED, False, False))
        lay.addWidget(fr, 1)

    def _montar(self) -> None:
        try:
            from core import cache_respostas, latencia
            r = latencia.relatorio()
            cache = cache_respostas.estatisticas()
        except Exception:
            r, cache = None, {}
        host = QWidget()
        host.setObjectName("ihost")
        host.setStyleSheet("QWidget#ihost { background: transparent; }")
        v = QVBoxLayout(host)
        v.setContentsMargins(0, 0, 6, 0)
        v.setSpacing(10)

        if not r or r["fala_mediana_ms"] is None:
            v.addWidget(self._rot("Ainda não medi nenhum pedido. Fale ou digite algo para o NEXUS e volte aqui: "
                                  "cada pedido mostra quanto tempo foi para escutar, preparar, decidir a rota, "
                                  "o modelo pensar e as ferramentas rodarem.", 9, C.TEXT_DIM))
            v.addStretch(1)
            self._area.setWidget(host)
            return

        kpis = QHBoxLayout()
        kpis.setSpacing(8)
        self._tile(kpis, "TEMPO TÍPICO", _s(r["fala_mediana_ms"]), "fim da fala → 1ª fala")
        self._tile(kpis, "90% DOS CASOS", _s(r["fala_p90_ms"]), "até")
        self._tile(kpis, "1ª PALAVRA DO MODELO", _s(r["primeiro_token_mediana_ms"]), "típico")
        total = r["ferramentas"]
        self._tile(kpis, "CACHE", f"{r['cache_acertos']} de {total}" if total else "—", "chamadas de ferramenta")
        self._tile(kpis, "PEDIDOS", str(r["pedidos"]), f"{r['detalhados']} detalhados")
        v.addLayout(kpis)

        # médias por etapa
        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 12, 16, 12)
        cl.setSpacing(6)
        cl.addWidget(self._rot("MÉDIA DE CADA ETAPA", 8.2, C.TEXT_MED, True, False))
        maior = max(r["medias"].values()) if r["medias"] else 1
        for e in latencia.ETAPAS:
            if e not in r["medias"]:
                continue
            linha = QHBoxLayout()
            nome = self._rot(latencia.NOMES[e], 8.8, C.WHITE if e == r["gargalo"] else C.TEXT_MED,
                             e == r["gargalo"], False)
            nome.setFixedWidth(130)
            linha.addWidget(nome)
            linha.addWidget(BarraEtapas({e: r["medias"][e]}, maior), 1)
            val = self._rot(_s(r["medias"][e]), 8.8, C.WHITE, True, False)
            val.setFixedWidth(70)
            val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            linha.addWidget(val)
            cl.addLayout(linha)
        if r["gargalo"]:
            cl.addWidget(self._rot(f"Maior gargalo: {latencia.NOMES[r['gargalo']].lower()}. "
                                   + latencia.DICAS[r["gargalo"]], 8.6, C.PRI))
        v.addWidget(card)

        # últimos pedidos
        ult = [p for p in r["ultimos"] if p.get("etapas")][-12:]
        if ult:
            card2 = QFrame()
            card2.setObjectName("card")
            c2 = QVBoxLayout(card2)
            c2.setContentsMargins(16, 12, 16, 12)
            c2.setSpacing(5)
            c2.addWidget(self._rot("ÚLTIMOS PEDIDOS", 8.2, C.TEXT_MED, True, False))
            escala = max(sum(p["etapas"].values()) for p in ult)
            for p in reversed(ult):
                linha = QHBoxLayout()
                txt = (p.get("texto") or "(sem texto)")[:34]
                rotulo = self._rot(f"{txt}", 8.4, C.TEXT_MED, False, False)
                rotulo.setFixedWidth(220)
                linha.addWidget(rotulo)
                linha.addWidget(BarraEtapas(p["etapas"], escala, 10), 1)
                val = self._rot(_s(p.get("primeira_fala_ms")), 8.4, C.WHITE, True, False)
                val.setFixedWidth(60)
                val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                linha.addWidget(val)
                c2.addLayout(linha)
            leg = QHBoxLayout()
            for e in latencia.ETAPAS:
                leg.addWidget(self._rot(f"■ {latencia.NOMES[e]}", 7.6, _cor_etapa(e), False, False))
            leg.addStretch(1)
            c2.addLayout(leg)
            v.addWidget(card2)
        v.addStretch(1)
        self._area.setWidget(host)

    def _limpar(self) -> None:
        try:
            from core import cache_respostas, latencia
            latencia.esquecer()
            cache_respostas.limpar()
        except Exception:
            _engolida("ui/overlays/latencia_painel.py:252")
        self._montar()

    def _fechar(self) -> None:
        self._tmr.stop()
        self.hide()
        self.deleteLater()
