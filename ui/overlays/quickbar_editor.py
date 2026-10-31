"""Editores da barra rápida e dos atalhos de teclado (NEXUS Ultra 2026 1.2).

São widgets comuns, então aparecem em dois lugares sem código repetido:
dentro de Configurações (abas BARRA e ATALHOS) e como janela própria
(botão "＋ Personalizar" da barra, Ctrl+B).
"""
from __future__ import annotations

from .._qt import *  # noqa: F401,F403
from .._base import C, FONT_MAIN  # noqa: F401
from ..overlays.base import _HudOverlay  # noqa: F401
from .. import quickbar as QB
from PyQt6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem
from core.protecao import engolida as _engolida

try:
    from PyQt6.QtWidgets import QKeySequenceEdit
except Exception:  # pragma: no cover
    QKeySequenceEdit = None


def _f(size: float, bold: bool = False) -> QFont:
    f = QFont(FONT_MAIN)
    f.setPointSizeF(size)
    if bold:
        f.setWeight(QFont.Weight.DemiBold)
    return f


def _estilo() -> str:
    return f"""
        QLabel {{ background: transparent; border: none; }}
        QLineEdit, QKeySequenceEdit QLineEdit {{
            background: {C.PANEL2}; color: {C.WHITE}; border: 1px solid {C.BORDER};
            border-radius: 8px; padding: 6px 9px;
        }}
        QLineEdit:focus {{ border-color: {C.PRI_DIM}; }}
        QListWidget {{ background: {C.PANEL}; color: {C.TEXT}; border: 1px solid {C.BORDER};
            border-radius: 9px; padding: 4px; outline: none; }}
        QListWidget::item {{ padding: 6px 6px; border-radius: 6px; }}
        QListWidget::item:selected {{ background: {C.PRI_GHO}; color: {C.WHITE}; }}
        QListWidget::indicator {{ width: 15px; height: 15px; }}
        QListWidget QScrollBar:vertical {{ background: transparent; width: 7px; margin: 4px 1px; }}
        QListWidget QScrollBar::handle:vertical {{ background: {C.BORDER_B}; border-radius: 3px; min-height: 24px; }}
        QListWidget QScrollBar::add-line:vertical, QListWidget QScrollBar::sub-line:vertical {{ height: 0; }}
        QPushButton#pri {{ background: {C.PRI}; color: {C.BG}; border: none; border-radius: 8px; padding: 0 14px; }}
        QPushButton#pri:hover {{ background: {C.WHITE}; }}
        QPushButton#sec {{ background: transparent; color: {C.TEXT_MED}; border: 1px solid {C.BORDER};
            border-radius: 8px; padding: 0 11px; }}
        QPushButton#sec:hover {{ color: {C.WHITE}; border-color: {C.BORDER_B}; }}
        QPushButton#chip {{ background: {C.PANEL2}; color: {C.ACC2}; border: 1px solid {C.BORDER};
            border-radius: 11px; padding: 0 9px; }}
        QPushButton#chip:hover {{ border-color: {C.ACC}; }}
        QPushButton#del {{ background: transparent; color: {C.TEXT_DIM}; border: none; }}
        QPushButton#del:hover {{ color: {C.RED}; }}
        QFrame#cmd {{ background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 8px; }}
    """


def _btn(texto: str, nome: str, fn, altura: int = 30) -> QPushButton:
    b = QPushButton(texto)
    b.setObjectName(nome)
    b.setFixedHeight(altura)
    b.setFont(_f(8.4, True))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.clicked.connect(fn)
    return b


def _secao(texto: str) -> QLabel:
    lbl = QLabel(texto)
    f = _f(7.4, True)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.6)
    lbl.setFont(f)
    lbl.setStyleSheet(f"color: {C.TEXT_MED};")
    return lbl


# ══════════════════════════════════════════════════════════════════════════
#  BARRA RÁPIDA
# ══════════════════════════════════════════════════════════════════════════

class QuickBarEditor(QWidget):
    def __init__(self, on_saved=None, parent=None):
        super().__init__(parent)
        self._on_saved = on_saved
        self.setStyleSheet(_estilo())
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        lay.addWidget(_secao("BOTÕES DA BARRA"))
        dica = QLabel("Marque os que você quer na barra. Arraste (ou use ↑ ↓) para mudar a ordem. "
                      "Alt+1, Alt+2… abrem os botões nessa ordem.")
        dica.setWordWrap(True)
        dica.setFont(_f(8))
        dica.setStyleSheet(f"color: {C.TEXT_DIM};")
        lay.addWidget(dica)

        meio = QHBoxLayout()
        self._lista = QListWidget()
        self._lista.setFont(_f(9))
        self._lista.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._lista.setFixedHeight(190)
        meio.addWidget(self._lista, 1)
        lado = QVBoxLayout()
        lado.addWidget(_btn("↑", "sec", lambda: self._mover(-1)))
        lado.addWidget(_btn("↓", "sec", lambda: self._mover(1)))
        lado.addStretch(1)
        meio.addLayout(lado)
        lay.addLayout(meio)

        lay.addSpacing(4)
        lay.addWidget(_secao("COMANDOS RÁPIDOS"))
        dica2 = QLabel("Um botão que manda um pedido pronto para o NEXUS, como se você tivesse falado.")
        dica2.setWordWrap(True)
        dica2.setFont(_f(8))
        dica2.setStyleSheet(f"color: {C.TEXT_DIM};")
        lay.addWidget(dica2)

        self._cmds_box = QVBoxLayout()
        self._cmds_box.setSpacing(4)
        lay.addLayout(self._cmds_box)

        novo = QHBoxLayout()
        novo.setSpacing(6)
        self._novo_nome = QLineEdit()
        self._novo_nome.setPlaceholderText("Nome do botão")
        self._novo_nome.setMaxLength(24)
        self._novo_nome.setFixedWidth(140)
        self._novo_cmd = QLineEdit()
        self._novo_cmd.setPlaceholderText("O que o NEXUS deve fazer (ex.: ativar modo trabalho)")
        self._novo_cmd.returnPressed.connect(self._add_cmd)
        novo.addWidget(self._novo_nome)
        novo.addWidget(self._novo_cmd, 1)
        novo.addWidget(_btn("＋", "sec", self._add_cmd))
        lay.addLayout(novo)

        ex = QHBoxLayout()
        ex.setSpacing(5)
        lbl = QLabel("Ideias:")
        lbl.setFont(_f(8))
        lbl.setStyleSheet(f"color: {C.TEXT_DIM};")
        ex.addWidget(lbl)
        for e in QB.EXEMPLOS_COMANDOS:
            ex.addWidget(_btn(e["label"], "chip", lambda _=False, x=e: self._usar_exemplo(x), 24))
        ex.addStretch(1)
        lay.addLayout(ex)

        lay.addStretch(1)
        fim = QHBoxLayout()
        self._msg = QLabel("")
        self._msg.setFont(_f(8.2))
        self._msg.setStyleSheet(f"color: {C.TEXT_MED};")
        fim.addWidget(self._msg, 1)
        fim.addWidget(_btn("Restaurar padrão", "sec", self._padrao))
        fim.addWidget(_btn("Salvar", "pri", self._salvar))
        lay.addLayout(fim)

        self._cmds = QB.comandos_atuais()
        self._preencher(QB.barra_atual())
        self._rebuild_cmds()

    def _preencher(self, ativos: list[str]) -> None:
        self._lista.clear()
        ordem = ativos + [k for k in QB.FERRAMENTAS if k not in ativos]
        for chave in ordem:
            icone, nome, _m, dica = QB.FERRAMENTAS[chave]
            it = QListWidgetItem(f"{icone}   {nome}")
            it.setData(Qt.ItemDataRole.UserRole, chave)
            it.setToolTip(dica)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsDragEnabled)
            it.setCheckState(Qt.CheckState.Checked if chave in ativos else Qt.CheckState.Unchecked)
            self._lista.addItem(it)

    def _mover(self, passo: int) -> None:
        i = self._lista.currentRow()
        j = i + passo
        if i < 0 or not (0 <= j < self._lista.count()):
            return
        it = self._lista.takeItem(i)
        self._lista.insertItem(j, it)
        self._lista.setCurrentRow(j)

    def _rebuild_cmds(self) -> None:
        while self._cmds_box.count():
            w = self._cmds_box.takeAt(0).widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        for i, c in enumerate(self._cmds):
            fr = QFrame()
            fr.setObjectName("cmd")
            h = QHBoxLayout(fr)
            h.setContentsMargins(10, 4, 4, 4)
            n = QLabel(f"⚡ {c['label']}")
            n.setFont(_f(8.6, True))
            n.setStyleSheet(f"color: {C.ACC2};")
            t = QLabel(c["command"])
            t.setFont(_f(8.4))
            t.setStyleSheet(f"color: {C.TEXT_MED};")
            h.addWidget(n)
            h.addSpacing(6)
            h.addWidget(t, 1)
            h.addWidget(_btn("✕", "del", lambda _=False, k=i: self._del_cmd(k), 24))
            self._cmds_box.addWidget(fr)

    def _usar_exemplo(self, e: dict) -> None:
        self._novo_nome.setText(e["label"])
        self._novo_cmd.setText(e["command"])
        self._novo_cmd.setFocus()

    def _add_cmd(self) -> None:
        nome, cmd = self._novo_nome.text().strip(), self._novo_cmd.text().strip()
        if not nome or not cmd:
            self._msg.setText("Preencha o nome do botão e o pedido.")
            return
        if len(self._cmds) >= 8:
            self._msg.setText("No máximo 8 comandos rápidos.")
            return
        self._cmds.append({"label": nome[:24], "command": cmd[:300]})
        self._novo_nome.clear()
        self._novo_cmd.clear()
        self._msg.setText("")
        self._rebuild_cmds()

    def _del_cmd(self, i: int) -> None:
        if 0 <= i < len(self._cmds):
            self._cmds.pop(i)
            self._rebuild_cmds()

    def _padrao(self) -> None:
        self._preencher(list(QB.PADRAO_BARRA))
        self._msg.setText("Padrão restaurado — clique em Salvar para aplicar.")

    def selecionados(self) -> list[str]:
        out = []
        for i in range(self._lista.count()):
            it = self._lista.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                out.append(it.data(Qt.ItemDataRole.UserRole))
        return out

    def _salvar(self) -> None:
        from core import preferences as P
        P.save({"quick_bar": self.selecionados(), "quick_commands": self._cmds})
        self._msg.setText("Barra salva.")
        self._msg.setStyleSheet(f"color: {C.GREEN};")
        if self._on_saved:
            self._on_saved()


# ══════════════════════════════════════════════════════════════════════════
#  ATALHOS DE TECLADO
# ══════════════════════════════════════════════════════════════════════════

class ShortcutsEditor(QWidget):
    def __init__(self, on_saved=None, parent=None):
        super().__init__(parent)
        self._on_saved = on_saved
        self.setStyleSheet(_estilo())
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        dica = QLabel("Clique na caixa e aperte a tecla (ou combinação) que você quer. "
                      "↺ volta para a tecla original.")
        dica.setWordWrap(True)
        dica.setFont(_f(8))
        dica.setStyleSheet(f"color: {C.TEXT_DIM};")
        lay.addWidget(dica)

        grade = QGridLayout()
        grade.setHorizontalSpacing(8)
        grade.setVerticalSpacing(5)
        self._campos: dict[str, object] = {}
        for linha, (chave, rotulo, padrao, _m) in enumerate(QB.ATALHOS):
            nome = QLabel(rotulo)
            nome.setFont(_f(8.8))
            nome.setStyleSheet(f"color: {C.TEXT};")
            grade.addWidget(nome, linha, 0)
            if QKeySequenceEdit is not None:
                campo = QKeySequenceEdit(QKeySequence(QB.tecla(chave)))
                try:
                    campo.setMaximumSequenceLength(1)
                except Exception:
                    _engolida("ui/overlays/quickbar_editor.py:286")
                try:
                    campo.setClearButtonEnabled(True)
                except Exception:
                    _engolida("ui/overlays/quickbar_editor.py:290")
            else:
                campo = QLineEdit(QB.tecla(chave))
            campo.setFixedWidth(170)
            campo.setFixedHeight(30)
            self._campos[chave] = campo
            grade.addWidget(campo, linha, 1)
            r = _btn("↺", "sec", lambda _=False, k=chave, p=padrao: self._restaurar(k, p), 28)
            r.setFixedWidth(32)
            r.setToolTip(f"Voltar para {QB.nome_da_tecla(padrao)}")
            grade.addWidget(r, linha, 2)
        lay.addLayout(grade)

        fixos = QLabel("Fixos:  Alt+1 … Alt+9 = botões da barra rápida  ·  "
                       "Ctrl+Espaço = falar segurando (ligue em Controles)")
        fixos.setWordWrap(True)
        fixos.setFont(_f(7.8))
        fixos.setStyleSheet(f"color: {C.TEXT_DIM};")
        lay.addSpacing(4)
        lay.addWidget(fixos)

        lay.addStretch(1)
        fim = QHBoxLayout()
        self._msg = QLabel("")
        self._msg.setWordWrap(True)
        self._msg.setFont(_f(8.2))
        self._msg.setStyleSheet(f"color: {C.TEXT_MED};")
        fim.addWidget(self._msg, 1)
        fim.addWidget(_btn("Restaurar todos", "sec", self._restaurar_todos))
        fim.addWidget(_btn("Salvar atalhos", "pri", self._salvar))
        lay.addLayout(fim)

    def _texto(self, campo) -> str:
        if QKeySequenceEdit is not None and isinstance(campo, QKeySequenceEdit):
            return campo.keySequence().toString(QKeySequence.SequenceFormat.PortableText).strip()
        return campo.text().strip()

    def _por(self, campo, seq: str) -> None:
        if QKeySequenceEdit is not None and isinstance(campo, QKeySequenceEdit):
            campo.setKeySequence(QKeySequence(seq))
        else:
            campo.setText(seq)

    def _restaurar(self, chave: str, padrao: str) -> None:
        self._por(self._campos[chave], padrao)

    def _restaurar_todos(self) -> None:
        for chave, _r, padrao, _m in QB.ATALHOS:
            self._por(self._campos[chave], padrao)
        self._msg.setText("Teclas originais de volta — clique em Salvar atalhos.")

    def valores(self) -> dict[str, str]:
        return {k: self._texto(c) for k, c in self._campos.items()}

    def _salvar(self) -> None:
        valores = self.valores()
        usados: dict[str, str] = {}
        nomes = {k: r for k, r, _p, _m in QB.ATALHOS}
        for chave, seq in valores.items():
            if not seq:
                continue
            if seq.lower().startswith("alt+") and seq[4:].isdigit():
                self._msg.setText(f"{seq} é usado pela barra rápida. Escolha outra tecla para "
                                  f"“{nomes[chave]}”.")
                self._msg.setStyleSheet(f"color: {C.MUTED_C};")
                return
            if seq in usados:
                self._msg.setText(f"A tecla {seq} está em dois atalhos: “{nomes[usados[seq]]}” "
                                  f"e “{nomes[chave]}”.")
                self._msg.setStyleSheet(f"color: {C.MUTED_C};")
                return
            usados[seq] = chave
        from core import preferences as P
        P.save(valores)
        self._msg.setText("Atalhos salvos e já valendo.")
        self._msg.setStyleSheet(f"color: {C.GREEN};")
        if self._on_saved:
            self._on_saved()


# ══════════════════════════════════════════════════════════════════════════
#  Janelas próprias (os mesmos editores, flutuando sobre o HUD)
# ══════════════════════════════════════════════════════════════════════════

class _EditorOverlay(_HudOverlay):
    _OW = 560

    def __init__(self, titulo: str, editor: QWidget, parent=None):
        super().__init__(parent)
        self.setObjectName("EditorOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            QWidget#EditorOverlay {{ background: {C.DARK}; border: 1px solid {C.BORDER_B}; border-radius: 14px; }}
            QLabel {{ background: transparent; }}
            QPushButton#x {{ background: transparent; color: {C.TEXT_DIM}; border: none; border-radius: 6px; }}
            QPushButton#x:hover {{ color: {C.WHITE}; background: {C.PRI_GHO}; }}
        """)
        self.setFixedWidth(self._OW)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 16, 22, 16)
        lay.setSpacing(10)
        topo = QHBoxLayout()
        t = QLabel(titulo)
        t.setFont(_f(13, True))
        t.setStyleSheet(f"color: {C.WHITE};")
        topo.addWidget(t)
        topo.addStretch(1)
        x = QPushButton("✕")
        x.setObjectName("x")
        x.setFixedSize(28, 28)
        x.setCursor(Qt.CursorShape.PointingHandCursor)
        x.clicked.connect(self._fechar)
        topo.addWidget(x)
        lay.addLayout(topo)
        lay.addWidget(editor, 1)

    def _fechar(self):
        self.hide()
        self.deleteLater()


class QuickBarOverlay(_EditorOverlay):
    def __init__(self, on_saved=None, parent=None):
        super().__init__("Personalizar a barra rápida", QuickBarEditor(on_saved), parent)


class ShortcutsOverlay(_EditorOverlay):
    def __init__(self, on_saved=None, parent=None):
        super().__init__("Atalhos de teclado", ShortcutsEditor(on_saved), parent)
