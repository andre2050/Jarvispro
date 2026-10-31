"""Central de Notas e Lembretes (NEXUS Ultra 2026 1.2).

Uma janela só para as duas coisas, com abas:
  • NOTAS ....... escrever, procurar, editar, copiar e apagar
  • LEMBRETES ... marcar com data e hora, ver os próximos e cancelar

Usa os mesmos arquivos dos comandos de voz (config/quick_notes.json e
memory/reminders.json): o que você cria aqui o NEXUS fala, e vice-versa.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .._qt import *  # noqa: F401,F403
from .._base import C, FONT_MAIN, agora, qcol  # noqa: F401
from ..overlays.base import _HudOverlay  # noqa: F401
from PyQt6.QtCore import QDateTime
from PyQt6.QtWidgets import QDateTimeEdit
from core.protecao import engolida as _engolida

_DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def _f(size: float, bold: bool = False) -> QFont:
    f = QFont(FONT_MAIN)
    f.setPointSizeF(size)
    if bold:
        f.setWeight(QFont.Weight.DemiBold)
    return f


def ha_quanto(ts: float) -> str:
    """'agora mesmo', 'há 5 min', 'ontem', 'há 3 dias'."""
    import time
    d = max(0, time.time() - float(ts or 0))
    if d < 60:
        return "agora mesmo"
    if d < 3600:
        return f"há {int(d // 60)} min"
    if d < 86400:
        h = int(d // 3600)
        return f"há {h} hora" + ("s" if h > 1 else "")
    dias = int(d // 86400)
    return "ontem" if dias == 1 else f"há {dias} dias"


def quando_amigavel(dt: datetime, ref: datetime | None = None) -> str:
    """'hoje às 15:30', 'amanhã às 09:00', 'sex, 23/10 às 08:00'."""
    ref = ref or agora()
    dia = (dt.date() - ref.date()).days
    hora = dt.strftime("%H:%M")
    if dia == 0:
        return f"hoje às {hora}"
    if dia == 1:
        return f"amanhã às {hora}"
    if dia == -1:
        return f"ontem às {hora}"
    return f"{_DIAS[dt.weekday()]}, {dt:%d/%m} às {hora}"


def falta_quanto(dt: datetime, ref: datetime | None = None) -> str:
    ref = ref or agora()
    s = (dt - ref).total_seconds()
    if s <= 0:
        return "já passou"
    if s < 3600:
        return f"em {max(1, int(s // 60))} min"
    if s < 86400:
        h, m = int(s // 3600), int((s % 3600) // 60)
        return f"em {h} h" + (f" {m:02d} min" if m else "")
    return f"em {int(s // 86400)} dia(s)"


class AgendaOverlay(_HudOverlay):
    _OW = 600
    _OH = 580
    _agendado = pyqtSignal(bool, str)

    def __init__(self, parent=None, log=None, start: str = "notas"):
        super().__init__(parent)
        self._log_fn = log
        self._confirm: dict[str, float] = {}     # botão -> quando foi o 1º clique
        self._editing: tuple | None = None       # (at, texto) da nota em edição
        self.setObjectName("Agenda")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            QWidget#Agenda {{ background: {C.DARK}; border: 1px solid {C.BORDER_B}; border-radius: 14px; }}
            QLabel {{ background: transparent; border: none; }}
            QLineEdit, QTextEdit, QDateTimeEdit {{
                background: {C.PANEL2}; color: {C.WHITE}; border: 1px solid {C.BORDER};
                border-radius: 9px; padding: 7px 10px; selection-background-color: {C.PRI_DIM};
            }}
            QLineEdit:focus, QTextEdit:focus, QDateTimeEdit:focus {{ border-color: {C.PRI_DIM}; }}
            QDateTimeEdit::drop-down {{ border: none; width: 22px; }}
            QPushButton#tab {{ background: transparent; color: {C.TEXT_MED}; border: none;
                border-bottom: 2px solid transparent; padding: 8px 14px; }}
            QPushButton#tab:hover {{ color: {C.WHITE}; }}
            QPushButton#tab:checked {{ color: {C.PRI}; border-bottom: 2px solid {C.PRI}; }}
            QPushButton#pri {{ background: {C.PRI}; color: {C.BG}; border: none; border-radius: 9px;
                padding: 0 16px; }}
            QPushButton#pri:hover {{ background: {C.WHITE}; }}
            QPushButton#sec {{ background: transparent; color: {C.TEXT_MED}; border: 1px solid {C.BORDER};
                border-radius: 9px; padding: 0 12px; }}
            QPushButton#sec:hover {{ color: {C.WHITE}; border-color: {C.BORDER_B}; }}
            QPushButton#chip {{ background: {C.PANEL2}; color: {C.TEXT_MED}; border: 1px solid {C.BORDER};
                border-radius: 12px; padding: 0 10px; }}
            QPushButton#chip:hover {{ color: {C.PRI}; border-color: {C.PRI_DIM}; }}
            QPushButton#ico {{ background: transparent; color: {C.TEXT_DIM}; border: none; border-radius: 6px; }}
            QPushButton#ico:hover {{ color: {C.WHITE}; background: {C.PRI_GHO}; }}
            QPushButton#del {{ background: transparent; color: {C.TEXT_DIM}; border: none; border-radius: 6px; }}
            QPushButton#del:hover {{ color: {C.RED}; background: {qcol(C.RED, 30).name(QColor.NameFormat.HexArgb)}; }}
            QFrame#card {{ background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 11px; }}
            QFrame#card:hover {{ border-color: {C.BORDER_B}; }}
            QFrame#cardOld {{ background: transparent; border: 1px dashed {C.BORDER}; border-radius: 11px; }}
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: transparent; width: 7px; }}
            QScrollBar::handle:vertical {{ background: {C.BORDER_B}; border-radius: 3px; min-height: 26px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        self.setFixedSize(self._OW, min(self._OH, max(420, (parent.height() - 20) if parent else self._OH)))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 16, 22, 16)
        lay.setSpacing(10)

        head = QHBoxLayout()
        ttl = QLabel("Notas e lembretes")
        ttl.setFont(_f(13, True))
        ttl.setStyleSheet(f"color: {C.WHITE};")
        head.addWidget(ttl)
        head.addStretch(1)
        fechar = QPushButton("✕")
        fechar.setObjectName("ico")
        fechar.setFixedSize(28, 28)
        fechar.setCursor(Qt.CursorShape.PointingHandCursor)
        fechar.setToolTip("Fechar")
        fechar.clicked.connect(self._close_panel)
        head.addWidget(fechar)
        lay.addLayout(head)

        tabs = QHBoxLayout()
        tabs.setSpacing(4)
        self._tab_notas = QPushButton("📝  Notas")
        self._tab_lemb = QPushButton("⏰  Lembretes")
        for b, chave in ((self._tab_notas, "notas"), (self._tab_lemb, "lembretes")):
            b.setObjectName("tab")
            b.setCheckable(True)
            b.setFont(_f(9.5, True))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=chave: self._show(k))
            tabs.addWidget(b)
        tabs.addStretch(1)
        lay.addLayout(tabs)
        linha = QFrame()
        linha.setFixedHeight(1)
        linha.setStyleSheet(f"background: {C.BORDER};")
        lay.addWidget(linha)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("QStackedWidget { background: transparent; }")
        self._stack.addWidget(self._build_notas())
        self._stack.addWidget(self._build_lembretes())
        lay.addWidget(self._stack, 1)

        self._msg = QLabel("")
        self._msg.setFont(_f(8.4))
        self._msg.setWordWrap(True)
        self._msg.setStyleSheet(f"color: {C.TEXT_MED};")
        lay.addWidget(self._msg)

        self._agendado.connect(self._on_agendado)
        self._show(start)

    # ── geral ───────────────────────────────────────────────────────────────

    def _say(self, text: str, cor: str | None = None) -> None:
        self._msg.setText(text)
        self._msg.setStyleSheet(f"color: {cor or C.TEXT_MED};")

    def _log(self, text: str) -> None:
        if self._log_fn:
            try:
                self._log_fn(text)
            except Exception:
                _engolida("ui/overlays/agenda.py:184")

    def _close_panel(self):
        self.hide()
        self.deleteLater()

    def _show(self, key: str) -> None:
        notas = key != "lembretes"
        self._tab_notas.setChecked(notas)
        self._tab_lemb.setChecked(not notas)
        self._stack.setCurrentIndex(0 if notas else 1)
        self._say("")
        if notas:
            self._rebuild_notas()
            self._nova.setFocus()
        else:
            self._rebuild_lembretes()
            self._lemb_texto.setFocus()

    def _confirmou(self, chave: str, botao: QPushButton, texto_confirmar: str) -> bool:
        """Ações que apagam pedem dois cliques (o 1º vira 'Confirmar?')."""
        import time
        agora_ = time.time()
        if agora_ - self._confirm.get(chave, 0) < 4:
            self._confirm.pop(chave, None)
            return True
        self._confirm[chave] = agora_
        botao.setText(texto_confirmar)
        QTimer.singleShot(4000, lambda: self._confirm.pop(chave, None))
        return False

    def _botao(self, texto: str, nome: str, fn, altura: int = 34, dica: str = "") -> QPushButton:
        b = QPushButton(texto)
        b.setObjectName(nome)
        b.setFixedHeight(altura)
        b.setFont(_f(8.6, True))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        if dica:
            b.setToolTip(dica)
        b.clicked.connect(fn)
        return b

    def _lista(self) -> tuple[QScrollArea, QVBoxLayout]:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.viewport().setObjectName("lvp")
        area.viewport().setStyleSheet("QWidget#lvp { background: transparent; }")
        host = QWidget()
        host.setObjectName("lhost")
        host.setStyleSheet("QWidget#lhost { background: transparent; }")
        v = QVBoxLayout(host)
        v.setContentsMargins(0, 2, 6, 2)
        v.setSpacing(7)
        v.addStretch(1)
        area.setWidget(host)
        return area, v

    @staticmethod
    def _limpar(v: QVBoxLayout) -> None:
        while v.count() > 1:
            it = v.takeAt(0)
            w = it.widget()
            if w is not None:
                w.hide()
                w.deleteLater()

    def _vazio(self, v: QVBoxLayout, texto: str) -> None:
        lbl = QLabel(texto)
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setFont(_f(9))
        lbl.setStyleSheet(f"color: {C.TEXT_DIM}; padding: 30px 10px;")
        v.insertWidget(v.count() - 1, lbl)

    # ══ NOTAS ═══════════════════════════════════════════════════════════════

    def _build_notas(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(8)

        nova = QHBoxLayout()
        nova.setSpacing(6)
        self._nova = QLineEdit()
        self._nova.setPlaceholderText("Escreva uma nota e aperte Enter…")
        self._nova.setFont(_f(9.6))
        self._nova.returnPressed.connect(self._add_nota)
        nova.addWidget(self._nova, 1)
        nova.addWidget(self._botao("＋  Adicionar", "pri", self._add_nota))
        v.addLayout(nova)

        self._busca = QLineEdit()
        self._busca.setPlaceholderText("🔎  Procurar nas notas")
        self._busca.setFont(_f(9))
        self._busca.textChanged.connect(lambda _t: self._rebuild_notas())
        v.addWidget(self._busca)

        area, self._lista_notas = self._lista()
        v.addWidget(area, 1)

        rodape = QHBoxLayout()
        self._contagem = QLabel("")
        self._contagem.setFont(_f(8))
        self._contagem.setStyleSheet(f"color: {C.TEXT_DIM};")
        rodape.addWidget(self._contagem)
        rodape.addStretch(1)
        self._apagar_tudo = self._botao("🗑  Apagar todas", "sec", self._clear_notas, 30)
        rodape.addWidget(self._apagar_tudo)
        v.addLayout(rodape)
        return page

    def _load_notas(self) -> list:
        try:
            from actions.quick_notes import _load
            return [n for n in _load() if isinstance(n, dict)]
        except Exception:
            return []

    def _save_notas(self, notas: list) -> None:
        from actions.quick_notes import _save
        _save(notas)

    def _add_nota(self) -> None:
        texto = self._nova.text().strip()
        if not texto:
            return
        import time
        notas = self._load_notas()
        notas.append({"text": texto[:500], "at": time.time()})
        self._save_notas(notas)
        self._nova.clear()
        self._log(f"SYS: 📝 Nota salva — {texto[:60]}")
        self._busca.clear()
        self._rebuild_notas()
        self._say("Nota salva.", C.GREEN)

    def _acha(self, notas: list, chave: tuple) -> int:
        for i, n in enumerate(notas):
            if (n.get("at"), n.get("text")) == chave:
                return i
        return -1

    def _del_nota(self, chave: tuple, botao: QPushButton) -> None:
        if not self._confirmou(f"del{chave}", botao, "Apagar?"):
            return
        notas = self._load_notas()
        i = self._acha(notas, chave)
        if i >= 0:
            notas.pop(i)
            self._save_notas(notas)
            self._say("Nota apagada.")
        self._rebuild_notas()

    def _edit_nota(self, chave: tuple) -> None:
        self._editing = chave
        self._rebuild_notas()

    def _save_edit(self, chave: tuple, editor: QTextEdit) -> None:
        texto = editor.toPlainText().strip()
        notas = self._load_notas()
        i = self._acha(notas, chave)
        if i >= 0 and texto:
            notas[i]["text"] = texto[:500]
            import time
            notas[i]["edited"] = time.time()
            self._save_notas(notas)
            self._say("Nota atualizada.", C.GREEN)
        self._editing = None
        self._rebuild_notas()

    def _copy_nota(self, texto: str) -> None:
        QApplication.clipboard().setText(texto)
        self._say("Nota copiada para a área de transferência.")

    def _clear_notas(self) -> None:
        if not self._load_notas():
            return
        if not self._confirmou("clear", self._apagar_tudo, "Tem certeza? Clique de novo"):
            return
        self._save_notas([])
        self._apagar_tudo.setText("🗑  Apagar todas")
        self._log("SYS: 📝 Todas as notas foram apagadas.")
        self._rebuild_notas()

    def _rebuild_notas(self) -> None:
        v = self._lista_notas
        self._limpar(v)
        notas = self._load_notas()
        filtro = self._busca.text().strip().lower()
        mostrar = [n for n in reversed(notas) if not filtro or filtro in str(n.get("text", "")).lower()]
        total = len(notas)
        self._tab_notas.setText(f"📝  Notas  {total}" if total else "📝  Notas")
        self._contagem.setText(
            (f"{len(mostrar)} de {total} nota(s)" if filtro else f"{total} nota(s)") if total else "")
        self._apagar_tudo.setVisible(total > 0)
        if not mostrar:
            self._vazio(v, "Nenhuma nota encontrada." if filtro else
                        "Nenhuma nota ainda.\nEscreva uma acima ou peça por voz: “Nexus, anota: comprar pão”.")
            return
        for n in mostrar:
            v.insertWidget(v.count() - 1, self._card_nota(n))

    def _card_nota(self, n: dict) -> QFrame:
        chave = (n.get("at"), n.get("text"))
        texto = str(n.get("text", ""))
        card = QFrame()
        card.setObjectName("card")
        h = QHBoxLayout(card)
        h.setContentsMargins(14, 10, 8, 10)
        h.setSpacing(8)
        corpo = QVBoxLayout()
        corpo.setSpacing(4)

        if self._editing == chave:
            ed = QTextEdit()
            ed.setPlainText(texto)
            ed.setFont(_f(9.6))
            ed.setFixedHeight(84)
            corpo.addWidget(ed)
            bts = QHBoxLayout()
            bts.addStretch(1)
            bts.addWidget(self._botao("Cancelar", "sec", lambda: self._edit_nota(None), 30))
            bts.addWidget(self._botao("Salvar", "pri", lambda _=False, c=chave, e=ed: self._save_edit(c, e), 30))
            corpo.addLayout(bts)
            h.addLayout(corpo, 1)
            QTimer.singleShot(0, ed.setFocus)
            return card

        t = QLabel(texto)
        t.setWordWrap(True)
        t.setTextFormat(Qt.TextFormat.PlainText)
        t.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        t.setFont(_f(9.8))
        t.setStyleSheet(f"color: {C.WHITE};")
        corpo.addWidget(t)
        meta = ha_quanto(n.get("at", 0))
        if n.get("edited"):
            meta += "  ·  editada"
        m = QLabel(meta)
        m.setFont(_f(7.8))
        m.setStyleSheet(f"color: {C.TEXT_DIM};")
        corpo.addWidget(m)
        h.addLayout(corpo, 1)

        for icone, dica, fn, nome in (
            ("✎", "Editar", lambda _=False, c=chave: self._edit_nota(c), "ico"),
            ("⧉", "Copiar", lambda _=False, x=texto: self._copy_nota(x), "ico"),
        ):
            b = self._botao(icone, nome, fn, 28, dica)
            b.setFixedWidth(30)
            h.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
        apagar = self._botao("✕", "del", lambda: None, 28, "Apagar (clique duas vezes)")
        apagar.setMinimumWidth(30)
        apagar.clicked.disconnect()
        apagar.clicked.connect(lambda _=False, c=chave, b=apagar: self._del_nota(c, b))
        h.addWidget(apagar, 0, Qt.AlignmentFlag.AlignTop)
        return card

    # ══ LEMBRETES ═══════════════════════════════════════════════════════════

    def _build_lembretes(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(8)

        form = QHBoxLayout()
        form.setSpacing(6)
        self._lemb_texto = QLineEdit()
        self._lemb_texto.setPlaceholderText("Do que eu devo te lembrar?")
        self._lemb_texto.setFont(_f(9.6))
        self._lemb_texto.returnPressed.connect(self._add_lembrete)
        form.addWidget(self._lemb_texto, 1)
        self._lemb_quando = QDateTimeEdit()
        self._lemb_quando.setCalendarPopup(True)
        self._lemb_quando.setDisplayFormat("dd/MM/yyyy  HH:mm")
        self._lemb_quando.setFont(_f(9.4))
        self._lemb_quando.setFixedWidth(170)
        self._definir(agora() + timedelta(hours=1))
        form.addWidget(self._lemb_quando)
        self._btn_agendar = self._botao("⏰  Marcar", "pri", self._add_lembrete)
        form.addWidget(self._btn_agendar)
        v.addLayout(form)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        hoje = agora()
        opcoes = [
            ("+15 min", lambda: agora() + timedelta(minutes=15)),
            ("+1 hora", lambda: agora() + timedelta(hours=1)),
            ("Hoje 18h", lambda: agora().replace(hour=18, minute=0)),
            ("Amanhã 9h", lambda: (agora() + timedelta(days=1)).replace(hour=9, minute=0)),
            ("Segunda 9h", lambda: (agora() + timedelta(days=(7 - agora().weekday()) or 7)).replace(hour=9, minute=0)),
        ]
        for rotulo, fn in opcoes:
            if rotulo == "Hoje 18h" and hoje.hour >= 18:
                continue
            chips.addWidget(self._botao(rotulo, "chip", lambda _=False, f=fn: self._definir(f()), 26))
        chips.addStretch(1)
        v.addLayout(chips)

        area, self._lista_lemb = self._lista()
        v.addWidget(area, 1)

        dica = QLabel("O aviso aparece na hora marcada, mesmo com o NEXUS fechado. "
                      "Também dá para pedir por voz: “Nexus, me lembra de ligar pro dentista amanhã às 10”.")
        dica.setWordWrap(True)
        dica.setFont(_f(7.8))
        dica.setStyleSheet(f"color: {C.TEXT_DIM};")
        v.addWidget(dica)
        return page

    def _definir(self, dt: datetime) -> None:
        dt = dt.replace(second=0, microsecond=0)
        self._lemb_quando.setDateTime(QDateTime(dt.year, dt.month, dt.day, dt.hour, dt.minute))

    def _add_lembrete(self) -> None:
        texto = self._lemb_texto.text().strip()
        if not texto:
            self._say("Escreva do que eu devo te lembrar.", C.ACC)
            self._lemb_texto.setFocus()
            return
        q = self._lemb_quando.dateTime()
        d, t = q.date(), q.time()
        quando = datetime(d.year(), d.month(), d.day(), t.hour(), t.minute())
        if quando <= agora():
            self._say("Esse horário já passou — escolha um horário no futuro.", C.ACC)
            return
        self._btn_agendar.setEnabled(False)
        self._say("Marcando o lembrete…")

        import threading

        def trabalho():
            try:
                from actions.reminder import agendar
                ok, msg, _id = agendar(quando, texto)
            except Exception as e:
                ok, msg = False, f"Não consegui marcar: {e}"
            self._agendado.emit(ok, msg)

        threading.Thread(target=trabalho, daemon=True, name="agenda-lembrete").start()

    def _on_agendado(self, ok: bool, msg: str) -> None:
        self._btn_agendar.setEnabled(True)
        self._say(msg, C.GREEN if ok else C.MUTED_C)
        if ok:
            self._log(f"SYS: ⏰ {msg} — {self._lemb_texto.text().strip()[:50]}")
            self._lemb_texto.clear()
        self._rebuild_lembretes()

    def _cancelar(self, task_id: str, botao: QPushButton) -> None:
        if not self._confirmou(f"lemb{task_id}", botao, "Cancelar?"):
            return
        try:
            from actions.reminder import cancelar
            ok, msg = cancelar(task_id)
        except Exception as e:
            ok, msg = False, f"Não consegui cancelar: {e}"
        self._say(msg, C.TEXT_MED if ok else C.MUTED_C)
        if ok:
            self._log(f"SYS: ⏰ {msg}")
        self._rebuild_lembretes()

    def _limpar_passados(self) -> None:
        try:
            from actions.reminder import limpar_concluidos
            n = limpar_concluidos()
            self._say(f"{n} lembrete(s) antigo(s) tirado(s) da lista.")
        except Exception as e:
            self._say(f"Não consegui limpar: {e}", C.MUTED_C)
        self._rebuild_lembretes()

    def _rebuild_lembretes(self) -> None:
        v = self._lista_lemb
        self._limpar(v)
        try:
            from actions.reminder import listar
            itens = listar()
        except Exception:
            itens = []
        prox = [d for d in itens if d["pendente"]]
        passados = [d for d in itens if not d["pendente"]][-10:]
        self._tab_lemb.setText(f"⏰  Lembretes  {len(prox)}" if prox else "⏰  Lembretes")

        if not prox and not passados:
            self._vazio(v, "Nenhum lembrete marcado.\nEscolha a data e a hora acima, ou peça por voz.")
            return
        if prox:
            v.insertWidget(v.count() - 1, self._secao(f"PRÓXIMOS  ·  {len(prox)}"))
            for d in prox:
                v.insertWidget(v.count() - 1, self._card_lembrete(d, True))
        if passados:
            linha = QWidget()
            linha.setObjectName("lsec")
            linha.setStyleSheet("QWidget#lsec { background: transparent; }")
            h = QHBoxLayout(linha)
            h.setContentsMargins(0, 8, 0, 0)
            h.addWidget(self._secao("JÁ PASSARAM"))
            h.addStretch(1)
            h.addWidget(self._botao("Limpar", "sec", self._limpar_passados, 24))
            v.insertWidget(v.count() - 1, linha)
            for d in reversed(passados):
                v.insertWidget(v.count() - 1, self._card_lembrete(d, False))

    def _secao(self, texto: str) -> QLabel:
        lbl = QLabel(texto)
        f = _f(7.4, True)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.6)
        lbl.setFont(f)
        lbl.setStyleSheet(f"color: {C.TEXT_MED};")
        return lbl

    def _card_lembrete(self, d: dict, pendente: bool) -> QFrame:
        try:
            dt = datetime.fromisoformat(d["quando"])
        except ValueError:
            dt = agora()
        card = QFrame()
        card.setObjectName("card" if pendente else "cardOld")
        h = QHBoxLayout(card)
        h.setContentsMargins(14, 9, 8, 9)
        h.setSpacing(10)

        hora = QLabel(dt.strftime("%H:%M"))
        hora.setFont(_f(13, True))
        hora.setStyleSheet(f"color: {C.PRI if pendente else C.TEXT_DIM};")
        hora.setFixedWidth(56)
        h.addWidget(hora)

        corpo = QVBoxLayout()
        corpo.setSpacing(2)
        t = QLabel(d.get("mensagem", ""))
        t.setWordWrap(True)
        t.setTextFormat(Qt.TextFormat.PlainText)
        t.setFont(_f(9.6))
        t.setStyleSheet(f"color: {C.WHITE if pendente else C.TEXT_DIM};")
        corpo.addWidget(t)
        meta = quando_amigavel(dt) + (f"  ·  {falta_quanto(dt)}" if pendente else "")
        m = QLabel(meta)
        m.setFont(_f(7.8))
        m.setStyleSheet(f"color: {C.TEXT_MED if pendente else C.TEXT_DIM};")
        corpo.addWidget(m)
        h.addLayout(corpo, 1)

        if pendente:
            b = self._botao("Cancelar", "del", lambda: None, 28, "Cancelar este lembrete (clique duas vezes)")
            b.clicked.disconnect()
            b.clicked.connect(lambda _=False, i=d["id"], bt=b: self._cancelar(i, bt))
            h.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
        return card
