"""Painel do núcleo I.S.A. (NEXUS Ultra 2026 1.3) — Ctrl+I.

O "centro de processamento de dados e tomada de decisões" do NEXUS, ao vivo:
  • indicadores: decisões, ações, tempo médio, há quanto tempo está ativo
  • 🧠 COGNIÇÃO: Gemini Live, rede neural local, memória, estado agora
  • ⚙ AUTOMAÇÃO: funções, plugins, permissões, o que está rodando
  • FLUXO DE DECISÕES: cada entrada, decisão, ação e resultado, com o tempo

Tudo vem de core/isa.py; nada sai do computador.
"""
from __future__ import annotations

import time

from .._qt import *  # noqa: F401,F403
from .._base import C, FONT_MAIN, qcol  # noqa: F401
from ..overlays.base import _HudOverlay  # noqa: F401


def _f(size: float, bold: bool = False, spacing: float = 0.0) -> QFont:
    f = QFont(FONT_MAIN)
    f.setPointSizeF(size)
    if bold:
        f.setWeight(QFont.Weight.DemiBold)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return f


def _duracao(seg: int) -> str:
    h, m = divmod(max(0, int(seg)) // 60, 60)
    return f"{h}h {m:02d}min" if h else f"{m} min"


def _ms(ms) -> str:
    if ms is None:
        return "—"
    return f"{ms} ms" if ms < 1000 else f"{ms / 1000:.1f} s".replace(".", ",")


_CORES = {   # tipo -> chave de cor em C
    "entrada": "TEXT", "decisao": "PRI", "acao": "ACC2", "resultado": "GREEN",
    "erro": "RED", "resposta": "TEXT_MED", "memoria": "ACC", "sistema": "TEXT_DIM",
}
_FILTROS = [
    ("Tudo", None),
    ("Decisões", {"decisao"}),
    ("Ações", {"acao", "resultado", "erro"}),
    ("Erros", {"erro"}),
    ("Conversa", {"entrada", "resposta"}),
]


class IsaEmblem(QWidget):
    """O desenho da I.S.A. em miniatura (o mesmo do HUD), animado."""

    def __init__(self, tamanho: int = 76, parent=None):
        super().__init__(parent)
        self.setFixedSize(tamanho, tamanho)
        self._hud = None
        try:
            from core.isa_hud import IsaHUD
            self._hud = IsaHUD()
        except Exception:
            self._hud = None
        self._estado = lambda: ("LISTENING", False)
        self._t = time.monotonic()
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._passo)
        self._tmr.start(40)

    def _passo(self):
        agora_ = time.monotonic()
        dt, self._t = agora_ - self._t, agora_
        if self._hud is not None:
            estado, mudo = self._estado()
            self._hud.step(dt, 0.0, speaking=estado == "SPEAKING",
                           thinking=estado in ("THINKING", "PROCESSING"),
                           muted=mudo, listening=estado == "LISTENING")
        self.update()

    def paintEvent(self, _e):
        if self._hud is None:
            return
        p = QPainter(self)
        if not p.isActive():
            return
        r = self.width() / 2
        self._hud.paint(p, r, r, r * 0.98, qcol(C.PRI), qcol(C.ACC2), qcol(C.BG), " ")
        p.end()


class IsaOverlay(_HudOverlay):
    _OW = 780
    _OH = 640
    _novo_evento = pyqtSignal(object)

    def __init__(self, parent=None, estado=None, abrir_atuador=None, abrir_ia=None, abrir_latencia=None, abrir_privacidade=None):
        super().__init__(parent)
        self._estado_fn = estado or (lambda: ("LISTENING", False))
        self._abrir_atuador = abrir_atuador
        self._abrir_ia = abrir_ia
        self._abrir_latencia = abrir_latencia
        self._abrir_privacidade = abrir_privacidade
        self._filtro: set[str] | None = None
        self._linhas: list[QWidget] = []
        self.setObjectName("Isa")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            QWidget#Isa {{ background: {C.DARK}; border: 1px solid {C.BORDER_B}; border-radius: 14px; }}
            QLabel {{ background: transparent; border: none; }}
            QFrame#tile, QFrame#card {{ background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 11px; }}
            QFrame#ev {{ background: transparent; border: none; border-bottom: 1px solid {C.BORDER}; }}
            QPushButton#chip {{ background: transparent; color: {C.TEXT_MED}; border: 1px solid {C.BORDER};
                border-radius: 12px; padding: 0 11px; }}
            QPushButton#chip:hover {{ color: {C.WHITE}; border-color: {C.BORDER_B}; }}
            QPushButton#chip:checked {{ color: {C.BG}; background: {C.PRI}; border-color: {C.PRI}; }}
            QPushButton#sec {{ background: transparent; color: {C.TEXT_MED}; border: 1px solid {C.BORDER};
                border-radius: 9px; padding: 0 11px; }}
            QPushButton#sec:hover {{ color: {C.WHITE}; border-color: {C.BORDER_B}; }}
            QPushButton#link {{ background: transparent; color: {C.PRI}; border: none; padding: 0; text-align: right; }}
            QPushButton#link:hover {{ color: {C.WHITE}; }}
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

        # cabeçalho
        topo = QHBoxLayout()
        topo.setSpacing(12)
        self._emblema = IsaEmblem(64)
        self._emblema._estado = self._estado_fn
        topo.addWidget(self._emblema)
        tit = QVBoxLayout()
        tit.setSpacing(1)
        t = QLabel("Núcleo I.S.A.")
        t.setFont(_f(15, True))
        t.setStyleSheet(f"color: {C.WHITE};")
        sub = QLabel("Intelligent Systems Architecture  ·  o centro de decisões do NEXUS")
        sub.setFont(_f(8.4))
        sub.setStyleSheet(f"color: {C.TEXT_DIM};")
        tit.addStretch(1)
        tit.addWidget(t)
        tit.addWidget(sub)
        tit.addStretch(1)
        topo.addLayout(tit, 1)
        if self._abrir_privacidade:
            pv = QPushButton("🔒  Privacidade")
            pv.setObjectName("sec")
            pv.setFixedHeight(28)
            pv.setFont(_f(8.4, True))
            pv.setCursor(Qt.CursorShape.PointingHandCursor)
            pv.setToolTip("O que o NEXUS guarda, o que sai do computador e como apagar")
            pv.clicked.connect(self._abrir_privacidade)
            topo.addWidget(pv, 0, Qt.AlignmentFlag.AlignTop)
        if self._abrir_latencia:
            lat = QPushButton("⏱  Latência")
            lat.setObjectName("sec")
            lat.setFixedHeight(28)
            lat.setFont(_f(8.4, True))
            lat.setCursor(Qt.CursorShape.PointingHandCursor)
            lat.setToolTip("Onde o tempo vai: escutar, decidir, modelo pensar, ferramenta rodar")
            lat.clicked.connect(self._abrir_latencia)
            topo.addWidget(lat, 0, Qt.AlignmentFlag.AlignTop)
        if self._abrir_ia:
            ia = QPushButton("🧬  Como a IA funciona")
            ia.setObjectName("sec")
            ia.setFixedHeight(28)
            ia.setFont(_f(8.4, True))
            ia.setCursor(Qt.CursorShape.PointingHandCursor)
            ia.setToolTip("Machine learning, aprendizado profundo, linguagem natural, visão e tipos de IA")
            ia.clicked.connect(self._abrir_ia)
            topo.addWidget(ia, 0, Qt.AlignmentFlag.AlignTop)
        x = QPushButton("✕")
        x.setObjectName("x")
        x.setFixedSize(28, 28)
        x.setCursor(Qt.CursorShape.PointingHandCursor)
        x.clicked.connect(self._fechar)
        topo.addWidget(x, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(topo)

        # indicadores
        kpis = QHBoxLayout()
        kpis.setSpacing(8)
        self._k_dec = self._tile(kpis, "DECISÕES")
        self._k_acoes = self._tile(kpis, "AÇÕES")
        self._k_tempo = self._tile(kpis, "TEMPO MÉDIO")
        self._k_resp = self._tile(kpis, "RESPOSTA DE VOZ")      # 1.4
        self._k_ativo = self._tile(kpis, "ATIVO HÁ")
        lay.addLayout(kpis)

        # cognição | automação
        meio = QHBoxLayout()
        meio.setSpacing(8)
        self._cog = self._card(meio, "🧠  COGNIÇÃO", ["Gemini Live", "Rede neural local", "Memória", "Estado agora"])
        self._aut = self._card(meio, "⚙  AUTOMAÇÃO", ["Funções", "Plugins ativos", "Permissões", "Rodando agora"])
        lay.addLayout(meio)

        # fluxo
        cab = QHBoxLayout()
        cab.setSpacing(6)
        fl = QLabel("FLUXO DE DECISÕES")
        fl.setFont(_f(7.4, True, 1.6))
        fl.setStyleSheet(f"color: {C.TEXT_MED};")
        cab.addWidget(fl)
        cab.addSpacing(8)
        self._chips: list[QPushButton] = []
        for rotulo, tipos in _FILTROS:
            b = QPushButton(rotulo)
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setFixedHeight(24)
            b.setFont(_f(8, True))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, tp=tipos, bt=b: self._filtrar(tp, bt))
            self._chips.append(b)
            cab.addWidget(b)
        self._chips[0].setChecked(True)
        cab.addStretch(1)
        limpar = QPushButton("Limpar")
        limpar.setObjectName("sec")
        limpar.setFixedHeight(24)
        limpar.setFont(_f(8, True))
        limpar.setCursor(Qt.CursorShape.PointingHandCursor)
        limpar.clicked.connect(self._limpar)
        cab.addWidget(limpar)
        lay.addLayout(cab)

        self._area = QScrollArea()
        self._area.setWidgetResizable(True)
        self._area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._area.viewport().setObjectName("ivp")
        self._area.viewport().setStyleSheet("QWidget#ivp { background: transparent; }")
        host = QWidget()
        host.setObjectName("ihost")
        host.setStyleSheet("QWidget#ihost { background: transparent; }")
        self._lista = QVBoxLayout(host)
        self._lista.setContentsMargins(0, 0, 6, 0)
        self._lista.setSpacing(0)
        self._lista.addStretch(1)
        self._area.setWidget(host)
        lay.addWidget(self._area, 1)

        self._vazio = QLabel("Ainda nada por aqui. Fale ou digite algo para o NEXUS e veja\n"
                             "cada passo do raciocínio aparecer: o que chegou, quem decidiu e o que foi feito.")
        self._vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._vazio.setFont(_f(8.8))
        self._vazio.setStyleSheet(f"color: {C.TEXT_DIM}; padding: 24px;")
        self._lista.insertWidget(0, self._vazio)

        # dados
        self._novo_evento.connect(self._add_evento)
        try:
            from core import isa
            self._isa = isa
            for ev in reversed(isa.eventos(120)):
                self._add_evento(ev, animar=False)
            isa.ouvir(self._ao_evento)
        except Exception:
            self._isa = None
        self.destroyed.connect(lambda *_: self._desligar())
        self._mem_cache = (0.0, "—")
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._atualizar)
        self._tmr.start(1000)
        self._atualizar()

    # ── montagem ────────────────────────────────────────────────────────────

    def _tile(self, lay, rotulo: str):
        fr = QFrame()
        fr.setObjectName("tile")
        v = QVBoxLayout(fr)
        v.setContentsMargins(14, 9, 14, 10)
        v.setSpacing(1)
        r = QLabel(rotulo)
        r.setFont(_f(6.8, True, 1.6))
        r.setStyleSheet(f"color: {C.TEXT_DIM};")
        val = QLabel("—")
        val.setFont(_f(15, True))
        val.setStyleSheet(f"color: {C.WHITE};")
        sub = QLabel("")
        sub.setFont(_f(7.6))
        sub.setStyleSheet(f"color: {C.TEXT_MED};")
        v.addWidget(r)
        v.addWidget(val)
        v.addWidget(sub)
        lay.addWidget(fr, 1)
        return val, sub

    def _card(self, lay, titulo: str, linhas: list[str]) -> dict:
        fr = QFrame()
        fr.setObjectName("card")
        v = QVBoxLayout(fr)
        v.setContentsMargins(14, 10, 14, 10)
        v.setSpacing(5)
        t = QLabel(titulo)
        t.setFont(_f(8.2, True, 1.2))
        t.setStyleSheet(f"color: {C.TEXT_MED};")
        v.addWidget(t)
        valores = {}
        for nome in linhas:
            h = QHBoxLayout()
            n = QLabel(nome)
            n.setFont(_f(8.8))
            n.setStyleSheet(f"color: {C.TEXT_DIM};")
            h.addWidget(n)
            h.addStretch(1)
            if nome == "Permissões" and self._abrir_atuador:
                b = QPushButton("—")
                b.setObjectName("link")
                b.setFont(_f(8.8, True))
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.setToolTip("Ajustar o que o NEXUS pode fazer no computador")
                b.clicked.connect(self._abrir_atuador)
                h.addWidget(b)
                valores[nome] = b
            else:
                val = QLabel("—")
                val.setFont(_f(8.8, True))
                val.setStyleSheet(f"color: {C.WHITE};")
                h.addWidget(val)
                valores[nome] = val
            v.addLayout(h)
        lay.addWidget(fr, 1)
        return valores

    @staticmethod
    def _pinta(widget, texto: str, cor: str) -> None:
        widget.setText(texto)
        if isinstance(widget, QLabel):
            widget.setStyleSheet(f"color: {cor};")

    # ── atualização ─────────────────────────────────────────────────────────

    def _atualizar(self) -> None:
        if self._isa is None:
            return
        isa = self._isa
        s = isa.estatisticas()
        st = isa.status()

        self._k_dec[0].setText(str(s["decisoes"]))
        self._k_dec[1].setText(f"{s['pct_local']}% aqui no PC" if s["decisoes"] else "nenhuma ainda")
        self._k_acoes[0].setText(str(s["acoes_ok"]))
        self._k_acoes[1].setText(f"{s['acoes_erro']} com erro" if s["acoes_erro"] else "nenhum erro")
        self._k_acoes[1].setStyleSheet(f"color: {C.RED if s['acoes_erro'] else C.TEXT_MED};")
        self._k_tempo[0].setText(_ms(s["tempo_medio_ms"]))
        self._k_tempo[1].setText(f"máx {_ms(s['tempo_max_ms'])}" if s["tempo_max_ms"] else "")
        if s.get("resposta_media_ms") is not None:
            self._k_resp[0].setText(_ms(s["resposta_media_ms"]))
            self._k_resp[1].setText(f"última {_ms(s['resposta_ultima_ms'])}  ·  "
                                    f"{s['respostas_medidas']} medida(s)")
        else:
            self._k_resp[0].setText("—")
            self._k_resp[1].setText("fale com o NEXUS para medir")
        self._k_ativo[0].setText(_duracao(s["ativo_ha_s"]))
        self._k_ativo[1].setText(f"{s['entradas']} pedido(s)  ·  {s['respostas']} resposta(s)")

        # cognição
        con = str(st.get("conexao") or "aguardando")
        cor = C.GREEN if con == "conectado" else (C.RED if "inválida" in con else C.ACC)
        modelo = st.get("modelo")
        self._pinta(self._cog["Gemini Live"], con + (f"  ·  {modelo}" if modelo and con == "conectado" else ""), cor)
        try:
            from core import intent_net as _in
            ligada = _in.load_settings().get("enabled", True)
            pronta = bool(_in.brain.ready)
            txt, cor = (("pronta", C.GREEN) if pronta else ("treinando…", C.ACC)) if ligada else ("desligada", C.TEXT_DIM)
        except Exception:
            txt, cor = "indisponível", C.TEXT_DIM
        self._pinta(self._cog["Rede neural local"], txt, cor)
        agora_ = time.monotonic()
        if agora_ - self._mem_cache[0] > 5:
            try:
                from memory.memory_manager import all_entries_for_ui
                n = len(all_entries_for_ui())
                self._mem_cache = (agora_, f"{n} fato(s)")
            except Exception:
                self._mem_cache = (agora_, "—")
        self._pinta(self._cog["Memória"], self._mem_cache[1], C.WHITE)
        estado, mudo = self._estado_fn()
        nomes = {"LISTENING": "Ouvindo", "SPEAKING": "Falando", "THINKING": "Pensando",
                 "PROCESSING": "Processando", "SLEEPING": "Dormindo", "INITIALISING": "Iniciando"}
        txt = "Mudo" if mudo else nomes.get(estado, str(estado).title())
        cor = C.MUTED_C if mudo else {"LISTENING": C.GREEN, "SPEAKING": C.ACC}.get(estado, C.ACC2)
        self._pinta(self._cog["Estado agora"], txt, cor)

        # automação
        self._pinta(self._aut["Funções"], str(st.get("funcoes", "—")), C.WHITE)
        self._pinta(self._aut["Plugins ativos"], str(st.get("plugins", 0)), C.WHITE)
        try:
            from core.settings_tools import actuator_permissions
            perms = actuator_permissions()
            lib = sum(1 for v in perms.values() if v)
            self._aut["Permissões"].setText(f"{lib} de {len(perms)} grupos")
        except Exception:
            self._aut["Permissões"].setText("—")
        n = s["em_andamento"]
        self._pinta(self._aut["Rodando agora"], f"{n} ação(ões)" if n else "nada",
                    C.ACC if n else C.TEXT_MED)

    # ── fluxo ───────────────────────────────────────────────────────────────

    def _ao_evento(self, ev: dict) -> None:      # pode vir de outra thread
        try:
            self._novo_evento.emit(ev)
        except RuntimeError:
            pass

    def _linha(self, ev: dict) -> QFrame:
        from core.isa import TIPOS
        icone, nome_tipo = TIPOS.get(ev["tipo"], ("◈", "Sistema"))
        cor = getattr(C, _CORES.get(ev["tipo"], "TEXT"), C.TEXT)
        fr = QFrame()
        fr.setObjectName("ev")
        fr.setProperty("tipo", ev["tipo"])
        h = QHBoxLayout(fr)
        h.setContentsMargins(4, 7, 4, 7)
        h.setSpacing(10)
        hora = QLabel(ev["hora"])
        hora.setFont(_f(8))
        hora.setStyleSheet(f"color: {C.TEXT_DIM};")
        hora.setFixedWidth(54)
        h.addWidget(hora, 0, Qt.AlignmentFlag.AlignTop)
        ic = QLabel(icone)
        ic.setFont(_f(10))
        ic.setStyleSheet(f"color: {cor};")
        ic.setFixedWidth(20)
        ic.setToolTip(nome_tipo)
        h.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
        corpo = QVBoxLayout()
        corpo.setSpacing(1)
        t = QLabel(ev["titulo"])
        t.setWordWrap(True)
        t.setTextFormat(Qt.TextFormat.PlainText)
        t.setFont(_f(9.2, ev["tipo"] in ("decisao", "erro", "resultado")))
        t.setStyleSheet(f"color: {cor if ev['tipo'] in ('decisao', 'erro') else C.WHITE};")
        corpo.addWidget(t)
        if ev.get("detalhe"):
            d = QLabel(ev["detalhe"])
            d.setWordWrap(True)
            d.setTextFormat(Qt.TextFormat.PlainText)
            d.setFont(_f(8))
            d.setStyleSheet(f"color: {C.TEXT_DIM};")
            corpo.addWidget(d)
        h.addLayout(corpo, 1)
        if ev.get("origem"):
            o = QLabel(ev["origem"])
            o.setFont(_f(7.2, True))
            o.setStyleSheet(f"color: {C.TEXT_MED}; border: 1px solid {C.BORDER}; border-radius: 8px; padding: 1px 7px;")
            h.addWidget(o, 0, Qt.AlignmentFlag.AlignTop)
        if ev.get("ms") is not None:
            m = QLabel(_ms(ev["ms"]))
            m.setFont(_f(7.6, True))
            m.setStyleSheet(f"color: {C.GREEN if ev['tipo'] == 'resultado' else C.RED};")
            m.setFixedWidth(54)
            m.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            h.addWidget(m, 0, Qt.AlignmentFlag.AlignTop)
        return fr

    def _add_evento(self, ev: dict, animar: bool = True) -> None:
        if not ev:
            return
        self._vazio.hide()
        linha = self._linha(ev)
        self._lista.insertWidget(0, linha)
        self._linhas.insert(0, linha)
        linha.setVisible(self._filtro is None or ev["tipo"] in self._filtro)
        while len(self._linhas) > 160:
            velha = self._linhas.pop()
            velha.hide()
            velha.deleteLater()
        if animar:
            self._area.verticalScrollBar().setValue(0)

    def _filtrar(self, tipos, botao) -> None:
        self._filtro = tipos
        for b in self._chips:
            b.setChecked(b is botao)
        for linha in self._linhas:
            linha.setVisible(tipos is None or linha.property("tipo") in tipos)

    def _limpar(self) -> None:
        for linha in self._linhas:
            linha.hide()
            linha.deleteLater()
        self._linhas.clear()
        if self._isa is not None:
            self._isa.limpar()

    def _desligar(self) -> None:
        try:
            if self._isa is not None:
                self._isa.parar_de_ouvir(self._ao_evento)
        except Exception:
            pass

    def _fechar(self) -> None:
        self._desligar()
        self._tmr.stop()
        self.hide()
        self.deleteLater()
