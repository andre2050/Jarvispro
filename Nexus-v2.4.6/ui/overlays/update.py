"""Janela ATUALIZAR O NEXUS (1.4.1) — puxa a versão nova direto do GitHub.

Abre pelo botão ⬆ ATUALIZAR (menu SETUP), por Configurações › Atualizar
sistema ou por voz ("atualiza o Nexus"). O que ela faz:

  1. confere no GitHub (config/update.json → github_repo) qual é a versão mais
     nova: a última release ou, se não houver release, a da branch principal
     (o memory/version.json que está lá);
  2. mostra o que mudou e, com um clique, baixa e instala — suas chaves,
     memória, notas e configurações nunca são tocadas, e cada arquivo trocado
     vai antes para backups/;
  3. avisa se a versão nova pede bibliotecas novas e oferece instalar;
  4. reinicia o NEXUS para terminar (ou desfaz a última atualização).

Também dá para instalar um .zip baixado à mão.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
from pathlib import Path

from .._qt import *  # noqa: F401,F403
from .._base import C, FONT_MAIN  # noqa: F401
from ..overlays.base import _HudOverlay  # noqa: F401


def _mb(n: int) -> str:
    return f"{n / 1_048_576:.1f} MB".replace(".", ",")


class UpdateOverlay(_HudOverlay):
    _OW = 470
    _sinal = pyqtSignal(str, object)       # (evento, dados) vindos das threads

    def __init__(self, parent=None, log=None, escolher_zip=None, reiniciar=None):
        super().__init__(parent)
        self._log_fn = log
        self._escolher_zip = escolher_zip      # o fluxo antigo: escolher um .zip
        self._reiniciar = reiniciar
        self._info: dict = {}
        self._ocupado = False
        self._sinal.connect(self._evento)
        self.setObjectName("UpdateOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            QWidget#UpdateOverlay {{
                background: rgba(8, 10, 28, 248);
                border: 1px solid {C.BORDER_B}; border-radius: 10px;
            }}
            QLabel {{ background: transparent; }}
            QPushButton#upPri {{
                background: {C.PRI_DIM}; color: {C.WHITE};
                border: 1px solid {C.PRI}; border-radius: 6px; padding: 0 14px;
            }}
            QPushButton#upPri:hover {{ background: {C.PRI}; }}
            QPushButton#upPri:disabled {{ background: {C.PANEL2}; color: {C.TEXT_DIM};
                border-color: {C.BORDER}; }}
            QPushButton#upSec {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER_B}; border-radius: 6px; padding: 0 12px;
            }}
            QPushButton#upSec:hover {{ color: {C.WHITE}; border-color: {C.PRI_DIM}; }}
            QPushButton#upSec:disabled {{ color: {C.TEXT_DIM}; }}
            QTextEdit#upNotas {{ background: {C.PANEL}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 6px; }}
        """)
        self.setFixedWidth(self._OW)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)

        topo = QHBoxLayout()
        tit = QLabel("⬆  ATUALIZAR O NEXUS")
        tit.setFont(QFont(FONT_MAIN, 12, QFont.Weight.Bold))
        tit.setStyleSheet(f"color: {C.PRI};")
        topo.addWidget(tit)
        topo.addStretch(1)
        x = QPushButton("✕")
        x.setFixedSize(26, 26)
        x.setCursor(Qt.CursorShape.PointingHandCursor)
        x.setStyleSheet(f"QPushButton {{ background: transparent; color: {C.TEXT_DIM}; border: none; }}"
                        f"QPushButton:hover {{ color: {C.TEXT}; }}")
        x.clicked.connect(self._fechar)
        topo.addWidget(x)
        lay.addLayout(topo)

        self._versoes = QLabel("")
        self._versoes.setFont(QFont(FONT_MAIN, 10, QFont.Weight.DemiBold))
        self._versoes.setStyleSheet(f"color: {C.WHITE};")
        self._versoes.setWordWrap(True)
        lay.addWidget(self._versoes)

        self._status = QLabel("")
        self._status.setFont(QFont(FONT_MAIN, 9))
        self._status.setStyleSheet(f"color: {C.TEXT_MED};")
        self._status.setWordWrap(True)
        self._status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self._status)

        self._barra = QProgressBar()
        self._barra.setFixedHeight(6)
        self._barra.setTextVisible(False)
        self._barra.setRange(0, 0)
        self._barra.setStyleSheet(f"""
            QProgressBar {{ background: {C.BAR_BG}; border: none; border-radius: 3px; }}
            QProgressBar::chunk {{ background: {C.PRI}; border-radius: 3px; }}
        """)
        lay.addWidget(self._barra)

        self._notas = QTextEdit()
        self._notas.setObjectName("upNotas")
        self._notas.setReadOnly(True)
        self._notas.setFont(QFont(FONT_MAIN, 9))
        self._notas.setFixedHeight(150)
        self._notas.hide()
        lay.addWidget(self._notas)

        def _botao(texto: str, nome: str, fn) -> QPushButton:
            b = QPushButton(texto)
            b.setObjectName(nome)
            b.setFixedHeight(32)
            b.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(fn)
            return b

        linha = QHBoxLayout()
        linha.setSpacing(8)
        self._b_instalar = _botao("⬇  BAIXAR E INSTALAR", "upPri", self._instalar)
        self._b_libs = _botao("📦  BIBLIOTECAS", "upPri", self._instalar_libs)
        self._b_libs.setToolTip("Instala as bibliotecas novas que esta versão usa (pip)")
        self._b_reiniciar = _botao("↻  REINICIAR AGORA", "upPri", self._reiniciar_agora)
        self._b_verificar = _botao("🔄  VERIFICAR DE NOVO", "upSec", self.verificar)
        for b in (self._b_instalar, self._b_libs, self._b_reiniciar, self._b_verificar):
            linha.addWidget(b)
        lay.addLayout(linha)

        linha2 = QHBoxLayout()
        linha2.setSpacing(8)
        self._b_zip = _botao("📁  Instalar um .zip…", "upSec", self._do_zip)
        self._b_desfazer = _botao("↶  Desfazer a última", "upSec", self._desfazer)
        self._b_github = _botao("🌐  Ver no GitHub", "upSec", self._abrir_github)
        for b in (self._b_zip, self._b_desfazer, self._b_github):
            b.setFixedHeight(28)
            b.setFont(QFont(FONT_MAIN, 8))
            linha2.addWidget(b)
        linha2.addStretch(1)
        lay.addLayout(linha2)

        self._b_instalar.hide()
        self._b_reiniciar.hide()
        self._b_libs.hide()
        self._atualizar_desfazer()
        self.verificar()

    # ── threads → tela ──────────────────────────────────────────────────────

    def _emitir(self, evento: str, dados=None) -> None:
        try:
            self._sinal.emit(evento, dados)
        except RuntimeError:
            pass                    # a janela foi fechada enquanto trabalhava

    def _evento(self, evento: str, dados) -> None:
        if evento == "verificado":
            self._mostrar_verificacao(dados)
        elif evento == "progresso":
            self._status.setText(f"Baixando do GitHub… {_mb(int(dados))}")
        elif evento == "instalado":
            self._mostrar_instalacao(dados)
        elif evento == "libs":
            self._mostrar_libs(dados)
        self._ajustar()

    def _ajustar(self) -> None:
        """Recalcula a altura (textos com quebra de linha) mantendo o centro."""
        lay = self.layout()
        lay.activate()
        h = lay.heightForWidth(self.width()) if lay.hasHeightForWidth() else -1
        if h <= 0:
            h = lay.sizeHint().height()
        centro = self.geometry().center().y()
        self.resize(self.width(), h)
        if self.isVisible() and self.parentWidget() is not None:
            self.move(self.x(), max(0, centro - h // 2))

    # ── 1) verificar ────────────────────────────────────────────────────────

    def verificar(self) -> None:
        if self._ocupado:
            return
        from actions import system_update as su
        cur = su.current_version().get("version", "?")
        repo = su.github_repo()
        self._versoes.setText(f"Você está na v{cur}")
        self._b_instalar.hide()
        self._notas.hide()
        if not repo:
            self._barra.hide()
            self._status.setText(
                "Nenhum repositório do GitHub configurado (config/update.json). Rode "
                "configurar_github.py, ou instale um .zip baixado à mão.")
            return
        self._ocupado = True
        self._barra.setRange(0, 0)
        self._barra.show()
        self._status.setText(f"Procurando versão nova em github.com/{repo}…")
        self._b_verificar.setEnabled(False)
        threading.Thread(target=lambda: self._emitir("verificado", su.check_online()),
                         daemon=True).start()

    def _mostrar_verificacao(self, r: dict) -> None:
        self._ocupado = False
        self._barra.hide()
        self._b_verificar.setEnabled(True)
        cur, info = r.get("current", "?"), r.get("latest") or {}
        self._info = info
        if r.get("error") and not info:
            self._status.setText(f"Não consegui verificar: {r['error']}.")
            return
        onde = "release" if info.get("source") == "release" else f"branch {info.get('tag', 'main')}"
        if r.get("newer"):
            self._versoes.setText(f"Versão nova: v{info['version']}   ·   você está na v{cur}")
            self._status.setText(f"Encontrada no GitHub ({r.get('repo')}, {onde}). Suas chaves, "
                                 "memória, notas e configurações ficam como estão.")
            self._notas.setPlainText(info.get("notes") or "(sem descrição do que mudou)")
            self._notas.show()
            self._b_instalar.show()
            self._b_instalar.setEnabled(True)
            self._b_instalar.setFocus()
        else:
            self._versoes.setText(f"Você já está na versão mais nova: v{cur}")
            self._status.setText(f"No GitHub ({r.get('repo')}, {onde}) a mais nova é a "
                                 f"v{info.get('version', '?')}.")

    # ── 2) instalar ─────────────────────────────────────────────────────────

    def _instalar(self) -> None:
        if self._ocupado or not self._info:
            return
        self._ocupado = True
        self._b_instalar.setEnabled(False)
        self._b_verificar.setEnabled(False)
        self._b_zip.setEnabled(False)
        self._barra.setRange(0, 0)
        self._barra.show()
        self._status.setText("Baixando do GitHub…")
        info = dict(self._info)

        def _trabalho():
            from actions import system_update as su
            try:
                r = su.apply_online(info=info, progress=lambda n: self._emitir("progresso", n))
            except Exception as e:
                r = f"The update failed: {e}"
            self._emitir("instalado", {"texto": r, "versao": info.get("version")})

        threading.Thread(target=_trabalho, daemon=True).start()

    def _mostrar_instalacao(self, d: dict) -> None:
        self._ocupado = False
        self._barra.hide()
        self._b_verificar.setEnabled(True)
        self._b_zip.setEnabled(True)
        texto = str(d.get("texto") or "")
        if texto.startswith("Update applied"):
            n = re.search(r"(\d+) files written", texto)
            self._versoes.setText(f"✔  v{d.get('versao')} instalada")
            self._b_instalar.hide()
            self._notas.hide()
            partes = [f"{n.group(1) if n else 'Os'} arquivos atualizados. Seus dados ficaram "
                      "como estavam e uma cópia do que mudou está em backups/."]
            if "NEW_LIBRARIES" in texto:
                if getattr(sys, "frozen", False):
                    partes.append("Esta versão usa bibliotecas novas: no Python, rode "
                                  "python setup.py e depois o gerar_exe.bat para gerar o Nexus.exe de novo.")
                else:
                    partes.append("Esta versão usa bibliotecas novas — clique em 📦 BIBLIOTECAS "
                                  "antes de reiniciar.")
                    self._b_libs.show()
            partes.append("Reinicie o NEXUS para terminar.")
            self._status.setText(" ".join(partes))
            self._b_verificar.hide()
            self._b_reiniciar.show()
            self._log(f"SYS: ⬆ NEXUS v{d.get('versao')} instalado — reinicie para terminar.")
        elif texto.startswith("Already up to date"):
            self._status.setText("Você já está na versão mais nova.")
        else:
            self._b_instalar.setEnabled(True)
            msg = texto.replace("The download failed, nothing was changed:",
                                "O download falhou e nada foi mudado:")
            msg = msg.replace("Sir, the update failed:", "A atualização falhou:")
            msg = msg.replace("Some files were already replaced — say 'undo the update' to restore them.",
                              "Alguns arquivos já tinham sido trocados — use “Desfazer a última”.")
            self._status.setText(msg)
            self._log(f"ERR: Atualização — {msg[:160]}")
        self._atualizar_desfazer()

    # ── 3) bibliotecas novas (só rodando pelo Python) ───────────────────────

    def _instalar_libs(self) -> None:
        if self._ocupado:
            return
        self._ocupado = True
        self._b_libs.setEnabled(False)
        self._b_reiniciar.setEnabled(False)
        self._barra.setRange(0, 0)
        self._barra.show()
        self._status.setText("Instalando as bibliotecas novas (pode levar alguns minutos)…")
        from actions import system_update as su
        base = su._base()

        def _trabalho():
            try:
                p = subprocess.run([sys.executable, "-m", "pip", "install", "-r",
                                    str(base / "requirements.txt")],
                                   cwd=str(base), capture_output=True, text=True, timeout=1800)
                ok, saida = p.returncode == 0, (p.stderr or p.stdout or "")[-400:]
            except Exception as e:
                ok, saida = False, str(e)
            self._emitir("libs", {"ok": ok, "saida": saida})

        threading.Thread(target=_trabalho, daemon=True).start()

    def _mostrar_libs(self, d: dict) -> None:
        self._ocupado = False
        self._barra.hide()
        self._b_reiniciar.setEnabled(True)
        if d.get("ok"):
            self._b_libs.hide()
            self._status.setText("Bibliotecas instaladas. Reinicie o NEXUS para terminar.")
        else:
            self._b_libs.setEnabled(True)
            self._status.setText("Não consegui instalar as bibliotecas. Rode  python setup.py  na "
                                 f"pasta do NEXUS. Detalhe: {str(d.get('saida', ''))[-200:]}")

    # ── outros botões ───────────────────────────────────────────────────────

    def _reiniciar_agora(self) -> None:
        if self._reiniciar:
            self._status.setText("Reiniciando o NEXUS…")
            QTimer.singleShot(150, self._reiniciar)

    def _do_zip(self) -> None:
        if self._escolher_zip:
            self._fechar()
            self._escolher_zip()

    def _atualizar_desfazer(self) -> None:
        try:
            from actions import system_update as su
            self._b_desfazer.setVisible(su.last_backup() is not None)
        except Exception:
            self._b_desfazer.hide()

    def _desfazer(self) -> None:
        if self._ocupado:
            return
        resp = QMessageBox.question(self, "Desfazer a atualização",
                                    "Voltar para a versão anterior à última atualização?")
        if resp != QMessageBox.StandardButton.Yes:
            return
        from actions import system_update as su
        r = su.rollback()
        if r.startswith("Restored"):
            v = re.search(r"Restored v([\w.?]+)", r)
            self._versoes.setText(f"↶  Voltou para a v{v.group(1) if v else '?'}")
            self._status.setText("A versão anterior foi restaurada. Reinicie o NEXUS para terminar.")
            self._b_instalar.hide()
            self._notas.hide()
            self._b_verificar.hide()
            self._b_reiniciar.show()
            self._log("SYS: ↶ Atualização desfeita — reinicie para terminar.")
            self._ajustar()
        else:
            self._status.setText("Não há atualização para desfazer.")
        self._atualizar_desfazer()

    def _abrir_github(self) -> None:
        from actions import system_update as su
        repo = su.github_repo()
        url = (self._info or {}).get("page") or (f"https://github.com/{repo}" if repo else "")
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _log(self, texto: str) -> None:
        if self._log_fn:
            try:
                self._log_fn(texto)
            except Exception:
                pass

    def _fechar(self) -> None:
        self.hide()
        self.deleteLater()


def reiniciar_nexus() -> None:
    """Abre um NEXUS novo e fecha este. O novo espera este sair de vez antes
    de abrir microfone e porta do celular (NEXUS_ESPERAR_PID, em main.py)."""
    from actions.system_update import _base
    base = _base()
    env = dict(os.environ, NEXUS_ESPERAR_PID=str(os.getpid()))
    if getattr(sys, "frozen", False):
        cmd = [sys.executable]                                   # Nexus.exe
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"               # um processo novo, do zero
    else:
        cmd = [sys.executable, str(base / "main.py")]
    extra: dict = {}
    if sys.platform.startswith("win"):
        extra["creationflags"] = 0x00000008 | 0x00000200        # DETACHED_PROCESS | NEW_PROCESS_GROUP
    else:
        extra["start_new_session"] = True
    subprocess.Popen(cmd, cwd=str(base), env=env, close_fds=True, **extra)
    try:                                     # 2.4 — o os._exit abaixo pulava a marca de "fechou direito"
        from core import protecao as _prot
        _prot.fechar_sessao()
    except Exception:
        pass
    # Depois do quit o laço do Qt para: quem garante a saída é esta thread.
    saida = threading.Timer(1.5, os._exit, args=(0,))
    saida.daemon = False
    saida.start()
    app = QApplication.instance()
    if app is not None:
        app.quit()
