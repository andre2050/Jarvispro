"""Painel PRODUTIVIDADE (NEXUS Ultra 2026 2.0).

Um lugar só para o dia de trabalho:
  • TAREFAS ..... criar, marcar como feita, apagar (mesma lista da voz: actions/tarefas.py)
  • FOCO ........ Pomodoro com contagem regressiva (actions/focus_mode.py — silencia os avisos)
  • PROJETOS .... os ativos e o próximo passo de cada (actions/projetos.py)
  • NÚMEROS ..... abertas, para hoje, atrasadas, feitas hoje

Nada aqui guarda dados próprios: lê e grava nos mesmos arquivos das funções de voz,
então "o que tenho para fazer?" e este painel mostram sempre a mesma coisa.
"""
from __future__ import annotations

import time

from .._qt import *  # noqa: F401,F403
from .._base import C, FONT_MAIN, qcol  # noqa: F401
from ..overlays.base import _HudOverlay  # noqa: F401
from core.protecao import engolida as _engolida

_COR_PRIO = {"alta": lambda: C.RED, "media": lambda: C.ACC, "baixa": lambda: C.TEXT_DIM}
_ROTULO_PRIO = {"alta": "ALTA", "media": "MÉDIA", "baixa": "BAIXA"}
_FILTROS = (("abertas", "Abertas"), ("hoje", "Hoje"), ("atrasadas", "Atrasadas"), ("feitas", "Feitas"))


def _f(size: float, bold: bool = False) -> QFont:
    f = QFont(FONT_MAIN)
    f.setPointSizeF(size)
    if bold:
        f.setWeight(QFont.Weight.DemiBold)
    return f


class ProdutividadeOverlay(_HudOverlay):
    _OW, _OH = 880, 600

    def __init__(self, parent=None, log=None):
        super().__init__(parent)
        self.setObjectName("Prod")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._log_fn = log
        self._filtro = "abertas"
        self._confirm: dict[str, float] = {}
        self.setStyleSheet(f"""
            QWidget#Prod {{ background: {C.DARK}; border: 1px solid {C.BORDER_B}; border-radius: 16px; }}
            QLabel {{ background: transparent; border: none; }}
            QLineEdit, QComboBox {{
                background: {C.PANEL2}; color: {C.WHITE}; border: 1px solid {C.BORDER};
                border-radius: 10px; padding: 7px 10px; selection-background-color: {C.PRI_DIM};
            }}
            QLineEdit:focus, QComboBox:focus {{ border-color: {C.PRI_DIM}; }}
            QComboBox::drop-down {{ border: none; width: 22px; }}
            QComboBox QAbstractItemView {{ background: {C.PANEL2}; color: {C.WHITE};
                selection-background-color: {C.PRI_DIM}; border: 1px solid {C.BORDER_B}; }}
            QPushButton#pri {{ background: {C.PRI}; color: {C.BG}; border: none; border-radius: 10px; padding: 0 16px; }}
            QPushButton#pri:hover {{ background: {C.WHITE}; }}
            QPushButton#sec {{ background: transparent; color: {C.TEXT_MED}; border: 1px solid {C.BORDER};
                border-radius: 10px; padding: 0 12px; }}
            QPushButton#sec:hover {{ color: {C.WHITE}; border-color: {C.BORDER_B}; }}
            QPushButton#chip {{ background: transparent; color: {C.TEXT_MED}; border: 1px solid {C.BORDER};
                border-radius: 13px; padding: 0 12px; }}
            QPushButton#chip:hover {{ color: {C.PRI}; border-color: {C.PRI_DIM}; }}
            QPushButton#chip:checked {{ background: {C.PRI_GHO}; color: {C.PRI}; border-color: {C.PRI_DIM}; }}
            QPushButton#ico {{ background: transparent; color: {C.TEXT_DIM}; border: none; border-radius: 7px; }}
            QPushButton#ico:hover {{ color: {C.WHITE}; background: {C.PRI_GHO}; }}
            QPushButton#del {{ background: transparent; color: {C.TEXT_DIM}; border: none; border-radius: 7px; }}
            QPushButton#del:hover {{ color: {C.RED}; }}
            QPushButton#chk {{ background: transparent; color: {C.TEXT_DIM}; border: 1.5px solid {C.BORDER_B};
                border-radius: 11px; }}
            QPushButton#chk:hover {{ border-color: {C.GREEN}; color: {C.GREEN}; }}
            QPushButton#chk:checked {{ background: {C.GREEN}; color: {C.BG}; border-color: {C.GREEN}; }}
            QFrame#card {{ background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 12px; }}
            QFrame#row {{ background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 11px; }}
            QFrame#row:hover {{ border-color: {C.BORDER_B}; }}
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: transparent; width: 7px; }}
            QScrollBar::handle:vertical {{ background: {C.BORDER_B}; border-radius: 3px; min-height: 26px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        self.setFixedSize(self._OW, min(self._OH, max(460, (parent.height() - 20) if parent else self._OH)))

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(22, 16, 22, 16)
        raiz.setSpacing(12)

        # cabeçalho
        cab = QHBoxLayout()
        t = QLabel("🎯  Produtividade")
        t.setFont(_f(13.5, True))
        t.setStyleSheet(f"color: {C.WHITE};")
        cab.addWidget(t)
        cab.addStretch(1)
        x = QPushButton("✕")
        x.setObjectName("ico")
        x.setFixedSize(28, 28)
        x.setCursor(Qt.CursorShape.PointingHandCursor)
        x.setToolTip("Fechar")
        x.clicked.connect(self._fechar)
        cab.addWidget(x)
        raiz.addLayout(cab)

        # números
        self._cards: dict[str, QLabel] = {}
        linha = QHBoxLayout()
        linha.setSpacing(10)
        for chave, rotulo, cor in (("abertas", "ABERTAS", C.PRI), ("para_hoje", "PARA HOJE", C.ACC),
                                   ("atrasadas", "ATRASADAS", C.RED), ("feitas_hoje", "FEITAS HOJE", C.GREEN)):
            card = QFrame()
            card.setObjectName("card")
            v = QVBoxLayout(card)
            v.setContentsMargins(14, 8, 14, 8)
            v.setSpacing(0)
            n = QLabel("0")
            n.setFont(_f(20, True))
            n.setStyleSheet(f"color: {cor};")
            r = QLabel(rotulo)
            r.setFont(_f(7.5, True))
            r.setStyleSheet(f"color: {C.TEXT_DIM}; letter-spacing: 1px;")
            v.addWidget(n)
            v.addWidget(r)
            self._cards[chave] = n
            linha.addWidget(card, 1)
        raiz.addLayout(linha)

        corpo = QHBoxLayout()
        corpo.setSpacing(16)
        corpo.addLayout(self._coluna_tarefas(), 1)
        corpo.addLayout(self._coluna_lateral(), 0)
        raiz.addLayout(corpo, 1)

        self._msg = QLabel("")
        self._msg.setFont(_f(8.4))
        self._msg.setStyleSheet(f"color: {C.TEXT_MED};")
        raiz.addWidget(self._msg)

        self._relogio = QTimer(self)
        self._relogio.timeout.connect(self._tique)
        self._relogio.start(1000)
        self._atualizar_tudo()

    # ── construção ──────────────────────────────────────────────────────────
    def _botao(self, texto: str, nome: str, fn, altura: int = 34, dica: str = "") -> QPushButton:
        b = QPushButton(texto)
        b.setObjectName(nome)
        b.setFixedHeight(altura)
        b.setFont(_f(8.8, True))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        if dica:
            b.setToolTip(dica)
        b.clicked.connect(fn)
        return b

    def _coluna_tarefas(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(8)
        tit = QLabel("TAREFAS")
        tit.setFont(_f(8, True))
        tit.setStyleSheet(f"color: {C.TEXT_DIM}; letter-spacing: 2px;")
        col.addWidget(tit)

        nova = QHBoxLayout()
        nova.setSpacing(6)
        self._nova = QLineEdit()
        self._nova.setPlaceholderText("Nova tarefa… (Enter para adicionar)")
        self._nova.setFont(_f(9.5))
        self._nova.returnPressed.connect(self._adicionar)
        nova.addWidget(self._nova, 1)
        self._prio = QComboBox()
        for rot, val in (("Média", "media"), ("Alta", "alta"), ("Baixa", "baixa")):
            self._prio.addItem(rot, val)
        self._prio.setFixedWidth(84)
        nova.addWidget(self._prio)
        self._prazo = QComboBox()
        for rot, val in (("Sem prazo", ""), ("Hoje", "hoje"), ("Amanhã", "amanhã"), ("Em 1 semana", "semana que vem")):
            self._prazo.addItem(rot, val)
        self._prazo.setFixedWidth(116)
        nova.addWidget(self._prazo)
        nova.addWidget(self._botao("Adicionar", "pri", self._adicionar, 36))
        col.addLayout(nova)

        filtros = QHBoxLayout()
        filtros.setSpacing(6)
        self._chips: dict[str, QPushButton] = {}
        for chave, rot in _FILTROS:
            b = QPushButton(rot)
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setFixedHeight(26)
            b.setFont(_f(8.4, True))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=chave: self._trocar_filtro(k))
            self._chips[chave] = b
            filtros.addWidget(b)
        filtros.addStretch(1)
        self._limpar = self._botao("Limpar feitas", "sec", self._limpar_feitas, 26,
                                   "Tira da lista as tarefas já concluídas")
        self._limpar.setFont(_f(8, True))
        filtros.addWidget(self._limpar)
        col.addLayout(filtros)

        self._area = QScrollArea()
        self._area.setWidgetResizable(True)
        self._area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._area.viewport().setObjectName("lvp")
        self._area.viewport().setStyleSheet("QWidget#lvp { background: transparent; }")
        host = QWidget()
        host.setObjectName("lhost")
        host.setStyleSheet("QWidget#lhost { background: transparent; }")
        self._lista = QVBoxLayout(host)
        self._lista.setContentsMargins(0, 0, 4, 0)
        self._lista.setSpacing(6)
        self._area.setWidget(host)
        col.addWidget(self._area, 1)
        return col

    def _coluna_lateral(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(12)

        # FOCO
        foco = QFrame()
        foco.setObjectName("card")
        foco.setFixedWidth(290)
        v = QVBoxLayout(foco)
        v.setContentsMargins(16, 12, 16, 14)
        v.setSpacing(6)
        t = QLabel("FOCO")
        t.setFont(_f(8, True))
        t.setStyleSheet(f"color: {C.TEXT_DIM}; letter-spacing: 2px;")
        v.addWidget(t)
        self._tempo = QLabel("25:00")
        self._tempo.setFont(_f(34, True))
        self._tempo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._tempo.setStyleSheet(f"color: {C.WHITE};")
        v.addWidget(self._tempo)
        self._foco_txt = QLabel("")
        self._foco_txt.setFont(_f(8.6))
        self._foco_txt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._foco_txt.setWordWrap(True)
        self._foco_txt.setStyleSheet(f"color: {C.TEXT_MED};")
        v.addWidget(self._foco_txt)
        b1 = QHBoxLayout()
        b1.setSpacing(6)
        b1.addWidget(self._botao("▶ 25 min", "pri", lambda: self._foco("start", 25), 34, "Bloco de foco: o NEXUS fica em silêncio"))
        b1.addWidget(self._botao("▶ 50 min", "sec", lambda: self._foco("start", 50), 34))
        v.addLayout(b1)
        b2 = QHBoxLayout()
        b2.setSpacing(6)
        b2.addWidget(self._botao("☕ Pausa 5", "sec", lambda: self._foco("break", 5), 30))
        b2.addWidget(self._botao("■ Parar", "sec", lambda: self._foco("stop", 0), 30))
        v.addLayout(b2)
        col.addWidget(foco)

        # PROJETOS
        proj = QFrame()
        proj.setObjectName("card")
        proj.setFixedWidth(290)
        pv = QVBoxLayout(proj)
        pv.setContentsMargins(16, 12, 16, 14)
        pv.setSpacing(6)
        pt = QLabel("PROJETOS ATIVOS")
        pt.setFont(_f(8, True))
        pt.setStyleSheet(f"color: {C.TEXT_DIM}; letter-spacing: 2px;")
        pv.addWidget(pt)
        self._proj_lbl = QLabel("")
        self._proj_lbl.setWordWrap(True)
        self._proj_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._proj_lbl.setFont(_f(9))
        self._proj_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        pv.addWidget(self._proj_lbl, 1)
        dica = QLabel("Para criar: diga “registra o projeto…”")
        dica.setFont(_f(7.8))
        dica.setStyleSheet(f"color: {C.TEXT_DIM};")
        pv.addWidget(dica)
        col.addWidget(proj, 1)
        return col

    # ── ações ───────────────────────────────────────────────────────────────
    def _say(self, texto: str, cor: str | None = None) -> None:
        self._msg.setText(texto)
        self._msg.setStyleSheet(f"color: {cor or C.TEXT_MED};")

    def _fechar(self) -> None:
        self._relogio.stop()
        self.hide()
        self.deleteLater()

    def _trocar_filtro(self, chave: str) -> None:
        self._filtro = chave
        self._montar_lista()

    def _adicionar(self) -> None:
        from actions import tarefas as T
        titulo = self._nova.text().strip()
        if not titulo:
            self._say("Escreva a tarefa primeiro.", C.ACC)
            return
        t = T.adicionar(titulo, self._prio.currentData(), self._prazo.currentData())
        if not t:
            self._say("Não consegui anotar essa tarefa.", C.RED)
            return
        self._nova.clear()
        self._prio.setCurrentIndex(0)
        self._prazo.setCurrentIndex(0)
        if self._filtro in ("feitas",):
            self._filtro = "abertas"
        self._say(f"Anotada: {t['titulo']}", C.GREEN)
        self._atualizar_tudo()

    def _marcar(self, id_: int, feita: bool) -> None:
        from actions import tarefas as T
        T.marcar(id_, feita)
        self._atualizar_tudo()

    def _apagar(self, id_: int, botao: QPushButton) -> None:
        agora_ = time.time()
        if agora_ - self._confirm.get(f"d{id_}", 0) < 3:
            from actions import tarefas as T
            T.remover(id_)
            self._confirm.pop(f"d{id_}", None)
            self._atualizar_tudo()
            return
        self._confirm[f"d{id_}"] = agora_
        botao.setText("Apagar?")
        botao.setFixedWidth(60)
        QTimer.singleShot(3000, lambda: self._restaurar_apagar(id_, botao))

    def _restaurar_apagar(self, id_: int, botao: QPushButton) -> None:
        try:
            if time.time() - self._confirm.get(f"d{id_}", 0) >= 2.9:
                botao.setText("✕")
                botao.setFixedWidth(28)
        except RuntimeError:
            pass          # a linha já foi refeita

    def _limpar_feitas(self) -> None:
        from actions import tarefas as T
        n = T.limpar_feitas()
        self._say(f"Tirei {n} tarefa(s) concluída(s)." if n else "Não há tarefas concluídas para limpar.")
        self._atualizar_tudo()

    def _foco(self, acao: str, minutos: int) -> None:
        try:
            from actions import focus_mode as F
            F.focus_mode({"action": acao, "minutes": minutos})
        except Exception as e:
            self._say(f"Não consegui mexer no foco: {e}", C.RED)
            return
        self._say({"start": f"Foco de {minutos} min iniciado. O NEXUS fica em silêncio até acabar.",
                   "break": f"Pausa de {minutos} min.", "stop": "Foco parado."}.get(acao, ""), C.GREEN)
        self._tique()
        if self._log_fn:
            try:
                self._log_fn(f"SYS: 🎯 Foco — {acao} {minutos or ''}".strip())
            except Exception:
                _engolida("ui/overlays/produtividade.py:355")

    # ── atualização da tela ─────────────────────────────────────────────────
    def _atualizar_tudo(self) -> None:
        self._montar_lista()
        self._numeros()
        self._projetos()
        self._tique()

    def _numeros(self) -> None:
        try:
            from actions import tarefas as T
            e = T.estatisticas()
        except Exception:
            return
        for k, lbl in self._cards.items():
            lbl.setText(str(e.get(k, 0)))

    def _projetos(self) -> None:
        try:
            from actions import projetos as P
            ativos = P.ativos()
        except Exception:
            ativos = []
        if not ativos:
            self._proj_lbl.setText(f"<span style='color:{C.TEXT_DIM}'>Nenhum projeto ativo.</span>")
            return
        partes = []
        for p in ativos[:6]:
            passo = (p.get("proximo_passo") or "").strip()
            partes.append(f"<b style='color:{C.WHITE}'>{_esc(p['nome'])}</b>"
                          + (f"<br><span style='color:{C.TEXT_MED}'>→ {_esc(passo)}</span>" if passo else ""))
        self._proj_lbl.setText("<br><br>".join(partes))

    def _tique(self) -> None:
        """Contagem regressiva do foco (1×/s, leve: lê um arquivo pequeno)."""
        try:
            from actions import focus_mode as F
            d = F._read()
            hoje = F._today_count(d)
        except Exception:
            return
        kind, ends = d.get("kind"), float(d.get("ends_at") or 0)
        falta = max(0, int(ends - time.time())) if kind in ("focus", "break") else 0
        if falta > 0:
            self._tempo.setText(f"{falta // 60:02d}:{falta % 60:02d}")
            self._tempo.setStyleSheet(f"color: {C.PRI if kind == 'focus' else C.GREEN};")
            self._foco_txt.setText(("Concentrado — avisos silenciados. " if kind == "focus" else "Pausa. ")
                                   + f"Blocos hoje: {hoje}")
        else:
            m = int(d.get("focus_minutes") or 25)
            self._tempo.setText(f"{m:02d}:00")
            self._tempo.setStyleSheet(f"color: {C.WHITE};")
            self._foco_txt.setText(f"Pronto para começar. Blocos hoje: {hoje}")

    def _montar_lista(self) -> None:
        from actions import tarefas as T
        for k, b in self._chips.items():
            b.setChecked(k == self._filtro)
        self._limpar.setVisible(self._filtro == "feitas")
        while self._lista.count():
            it = self._lista.takeAt(0)
            w = it.widget()
            if w is not None:
                w.hide()
                w.setParent(None)      # some já; deleteLater sozinho deixaria a linha antiga visível
                w.deleteLater()
        itens = T.listar(self._filtro)
        if not itens:
            vazio = {"abertas": "Nenhuma tarefa aberta.\nEscreva uma acima, ou diga “anota a tarefa…”.",
                     "hoje": "Nada com prazo para hoje. 🎉", "atrasadas": "Nenhuma tarefa atrasada. 👏",
                     "feitas": "Ainda não há tarefas concluídas."}[self._filtro]
            lb = QLabel(vazio)
            lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lb.setFont(_f(9.5))
            lb.setStyleSheet(f"color: {C.TEXT_DIM}; padding: 40px 10px;")
            self._lista.addWidget(lb)
            self._lista.addStretch(1)
            return
        h = time.strftime("%Y-%m-%d")
        for t in itens:
            self._lista.addWidget(self._linha(t, h))
        self._lista.addStretch(1)

    def _linha(self, t: dict, hoje_iso: str) -> QFrame:
        from actions import tarefas as T
        fr = QFrame()
        fr.setObjectName("row")
        lay = QHBoxLayout(fr)
        lay.setContentsMargins(10, 8, 8, 8)
        lay.setSpacing(10)
        chk = QPushButton("✔" if t.get("feita") else "")
        chk.setObjectName("chk")
        chk.setCheckable(True)
        chk.setChecked(bool(t.get("feita")))
        chk.setFixedSize(22, 22)
        chk.setFont(_f(9, True))
        chk.setCursor(Qt.CursorShape.PointingHandCursor)
        chk.setToolTip("Marcar como feita" if not t.get("feita") else "Reabrir")
        chk.clicked.connect(lambda _=False, i=t["id"], f=not t.get("feita"): self._marcar(i, f))
        lay.addWidget(chk)

        meio = QVBoxLayout()
        meio.setSpacing(1)
        tit = QLabel(t["titulo"])
        tit.setFont(_f(10))
        tit.setWordWrap(True)
        feita = bool(t.get("feita"))
        tit.setStyleSheet(f"color: {C.TEXT_DIM if feita else C.WHITE};"
                          + (" text-decoration: line-through;" if feita else ""))
        meio.addWidget(tit)
        partes = []
        atrasada = bool(t.get("prazo")) and t["prazo"] < hoje_iso and not feita
        if t.get("prazo"):
            cor = C.RED if atrasada else (C.ACC if t["prazo"] == hoje_iso else C.TEXT_MED)
            partes.append(f"<span style='color:{cor}'>⏱ {_esc(T._prazo_legivel(t['prazo']))}</span>")
        if t.get("projeto"):
            partes.append(f"<span style='color:{C.PRI_DIM}'>◈ {_esc(t['projeto'])}</span>")
        if partes:
            meta = QLabel("   ".join(partes))
            meta.setTextFormat(Qt.TextFormat.RichText)
            meta.setFont(_f(8.2))
            meio.addWidget(meta)
        lay.addLayout(meio, 1)

        if not feita:
            cor = _COR_PRIO[t.get("prio", "media")]()
            bd = QLabel(_ROTULO_PRIO.get(t.get("prio"), "MÉDIA"))
            bd.setFont(_f(7, True))
            bd.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bd.setFixedSize(46, 18)
            bd.setStyleSheet(f"color: {cor}; border: 1px solid {cor}; border-radius: 9px;")
            lay.addWidget(bd)
        x = QPushButton("✕")
        x.setObjectName("del")
        x.setFixedSize(28, 28)
        x.setCursor(Qt.CursorShape.PointingHandCursor)
        x.setToolTip("Apagar (clique duas vezes)")
        x.clicked.connect(lambda _=False, i=t["id"], b=x: self._apagar(i, b))
        lay.addWidget(x)
        return fr


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
