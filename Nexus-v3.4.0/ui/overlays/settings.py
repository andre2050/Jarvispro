"""The CONFIGURAÇÕES hub (15 sections).

Part of the ui package (split from the old single ui.py)."""
from __future__ import annotations

from .._qt import *  # noqa: F401,F403
from .._base import C, FONT_MAIN, de_timestamp  # noqa: F401
from ..overlays.base import _HudOverlay  # noqa: F401

class SettingsPanelOverlay(_HudOverlay):
    """Painel de Configurações: uma porta de entrada para tudo que o assistente
    deixa ajustar. Itens que já têm painel próprio (personalização, comandos,
    plugins, APIs) abrem esse painel; o resto vive aqui. A lógica fica em
    core/settings_tools.py — este arquivo só mostra e chama."""

    _OW = 560

    # (2.2) A configuração do usuário é UMA só — a janela "Configuração do
    # usuário" (nome, voz, cores/skin, notificações, alertas, privacidade...),
    # aberta direto pelo menu SETUP. As abas USUÁRIO, SKIN e NOTIFIC. só
    # apontavam para ela e saíram do painel.
    # A chave é o nome da aba; o rótulo do menu SETUP (MENU_LABELS) usa o texto completo.
    _TABS = [
        ("audio", "ÁUDIO"), ("status", "STATUS"), ("apis", "APIs"),
        ("atuador", "ATUADOR"), ("backup", "BACKUP"), ("isa", "I.S.A."),
    ]
    # Telas que saíram da grade para ela não ficar bagunçada (o código das páginas continua aqui;
    # para trazer uma de volta, é só incluí-la em _TABS): RESETAR, GERENCIAR, SOBRE, COMANDO, LISTA,
    # AVANÇADO, AGENDA, BARRA, ATALHOS. Cada uma tem outro caminho: memória e log em STATUS, comandos
    # no F1, notas na central própria, barra/atalhos no editor de cada um, atualizar no SETUP.
    # Menu SETUP enxuto: só o núcleo I.S.A. (o ATUALIZAR é adicionado em main_window).
    # As demais seções continuam em _TABS, só não aparecem mais no menu.
    MENU_LABELS = [
        ("isa", "NÚCLEO I.S.A."),
    ]
    _DAYS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    _test_done = pyqtSignal(str)   # resultado de "testar chave", vindo de outra thread
    _mic_done = pyqtSignal(bool, str)   # resultado do teste de microfone

    def __init__(self, actions: dict, plugin_count: int | None = None,
                 parent=None, start: str = "status"):
        """actions: nome -> callable para abrir os painéis que já existem
        (customise, preferences, commands, plugins, plugin_settings)."""
        super().__init__(parent)
        self._actions = actions
        self._plugin_count = plugin_count
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            SettingsPanelOverlay {{
                background: rgba(8, 10, 28, 246);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._OW)

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(20, 16, 20, 16)
        self._lay.setSpacing(8)

        title = QLabel("CONFIGURAÇÕES")
        title.setFont(QFont(FONT_MAIN, 10, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.PRI}; background: transparent; letter-spacing: 2px;")
        self._lay.addWidget(title)

        # Abas em grade (4 por linha): mais legível que uma barra única com 12 itens.
        grid = QGridLayout(); grid.setSpacing(4)
        self._tab_btns: dict[str, QPushButton] = {}
        for i, (key, label) in enumerate(self._TABS):
            b = QPushButton(label)
            b.setCheckable(True)
            b.setFixedHeight(24)
            b.setFont(QFont(FONT_MAIN, 7, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {C.TEXT_MED};
                    border: 1px solid {C.BORDER}; border-radius: 4px; }}
                QPushButton:hover {{ color: {C.PRI}; border-color: {C.BORDER_B}; }}
                QPushButton:checked {{ color: {C.PRI}; background: {C.PRI_GHO};
                    border: 1px solid {C.PRI_DIM}; }}
            """)
            b.clicked.connect(lambda _=False, k=key: self._show(k))
            self._tab_btns[key] = b
            grid.addWidget(b, i // 4, i % 4)
        self._lay.addLayout(grid)

        self._stack = QStackedWidget()
        self._pages: dict[str, QWidget] = {}
        self._builders = {
            "audio": self._page_audio,
            "gerenciar": self._page_gerenciar,
            "status": self._page_status,
            "agenda": self._page_agenda,
            "apis": self._page_apis, "comandos": self._page_comandos,
            "lista": self._page_lista, "atuador": self._page_atuador,
            "avancado": self._page_avancado, "backup": self._page_backup,
            "sobre": self._page_sobre, "resetar": self._page_resetar,
            "barra": self._page_barra, "atalhos": self._page_atalhos, "isa": self._page_isa,
        }
        for key, _ in self._TABS:
            page = QWidget()
            page.setStyleSheet("background: transparent;")
            self._pages[key] = page
            self._stack.addWidget(page)
        self._lay.addWidget(self._stack, 1)

        self._msg = QLabel("")
        self._msg.setWordWrap(True)
        self._msg.setFont(QFont(FONT_MAIN, 8))
        self._msg.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._lay.addWidget(self._msg)

        self._test_done.connect(self._on_test_done)   # uma vez só
        self._mic_done.connect(lambda ok, msg: self._say(msg, C.GREEN if ok else C.MUTED_C))
        self._show(start)

    # ── helpers ─────────────────────────────────────────────────────────────

    def _label(self, text: str, size: int = 8, color: str | None = None, bold=False) -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setFont(QFont(FONT_MAIN, size, QFont.Weight.Bold if bold else QFont.Weight.Normal))
        lbl.setStyleSheet(f"color: {color or C.TEXT_MED}; background: transparent;")
        return lbl

    def _button(self, text: str, fn) -> QPushButton:
        b = QPushButton(text)
        b.setFixedHeight(30)
        b.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"""
            QPushButton {{ background: {C.PANEL2}; color: {C.PRI};
                border: 1px solid {C.BORDER}; border-radius: 6px; text-align: left; padding: 0 9px; }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.PRI}; }}
        """)
        b.clicked.connect(fn)
        return b

    def _check(self, text: str, checked: bool, on_toggle) -> QCheckBox:
        cb = QCheckBox(text)
        cb.setChecked(checked)
        cb.setFont(QFont(FONT_MAIN, 8))
        cb.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
        cb.toggled.connect(on_toggle)
        return cb

    def _show(self, key: str) -> None:
        if key not in self._builders:
            key = "status"
        for k, b in self._tab_btns.items():
            b.setChecked(k == key)
        # Página nova a cada abertura: tirar só os itens do layout deixava os
        # widgets dentro de sub-layouts visíveis por cima da página nova.
        old = self._pages[key]
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(6)
        self._builders[key](lay)
        self._stack.removeWidget(old)
        old.deleteLater()
        self._pages[key] = page
        self._stack.addWidget(page)
        self._stack.setCurrentWidget(page)
        self._msg.setText("")

    def _say(self, text: str, color: str | None = None) -> None:
        self._msg.setText(text)
        self._msg.setStyleSheet(f"color: {color or C.TEXT_MED}; background: transparent;")

    def _on_test_done(self, text: str) -> None:
        ok = text.startswith("Gemini: chave válida") or text.startswith("Anthropic: chave válida")
        self._say(text, C.GREEN if ok else C.MUTED_C)

    def _test_key(self, name: str) -> None:
        """Testa a chave em segundo plano para a tela não travar enquanto a API responde."""
        from core import settings_tools as S
        self._say("Testando a chave…")
        import threading
        def run():
            ok, msg = S.test_api_key(name)
            self._test_done.emit(msg)
        threading.Thread(target=run, daemon=True).start()

    def _open(self, name: str) -> None:
        fn = self._actions.get(name)
        if fn:
            fn()
        self.hide()

    def _run(self, name: str, refresh: str | None = None) -> None:
        """Roda uma ação sem fechar o painel (ex.: ligar/desligar início automático)."""
        fn = self._actions.get(name)
        if fn:
            fn()
        if refresh:
            self._show(refresh)

    @staticmethod
    def _prefs():
        from core import preferences as _P
        return _P

    # ── páginas ─────────────────────────────────────────────────────────────

    # ── ÁUDIO / AJUSTE DE ÁUDIO (9.2, refeito na 9.3) ─────────────────────────
    def _page_audio(self, lay):
        from memory.config_manager import (get_input_device, get_output_device,
                                           get_push_to_talk_enabled)
        P = self._prefs()
        for k, v in (("Microfone", get_input_device() or "padrão do sistema"),
                     ("Alto-falante", get_output_device() or "padrão do sistema")):
            row = QHBoxLayout()
            row.addWidget(self._label(k, 8, C.TEXT_DIM))
            val = self._label(v, 8, C.WHITE); val.setAlignment(Qt.AlignmentFlag.AlignRight)
            row.addWidget(val)
            lay.addLayout(row)
        lay.addWidget(self._button("🎧  Escolher microfone e alto-falante", lambda: self._open("audio")))
        lay.addWidget(self._button("🎙  Testar microfone (fale por 3 segundos)", self._test_mic))

        def combo(label, key, options, note=""):
            row = QHBoxLayout()
            row.addWidget(self._label(label, 8, C.TEXT_DIM), 1)
            box = QComboBox()
            box.setFont(QFont(FONT_MAIN, 8))
            box.setStyleSheet(f"QComboBox {{ background: {C.PANEL2}; color: {C.TEXT}; "
                              f"border: 1px solid {C.BORDER}; border-radius: 4px; padding: 3px 6px; }}")
            try:
                cur = float(P.get(key))
            except (TypeError, ValueError):
                cur = None
            for value, text in options:
                box.addItem(text, value)
                if cur is not None and abs(cur - value) < 1e-6:
                    box.setCurrentIndex(box.count() - 1)

            def changed(_i, b=box):
                P.save({key: float(b.currentData())})
                self._say(f"Salvo: {label.lower()} — {b.currentText()}.{note}")
            box.currentIndexChanged.connect(changed)
            row.addWidget(box, 1)
            lay.addLayout(row)

        def combo_txt(label, key, options, note=""):
            """Como o combo acima, mas para escolhas em texto."""
            row = QHBoxLayout()
            row.addWidget(self._label(label, 8, C.TEXT_DIM), 1)
            box = QComboBox()
            box.setFont(QFont(FONT_MAIN, 8))
            box.setStyleSheet(f"QComboBox {{ background: {C.PANEL2}; color: {C.TEXT}; "
                              f"border: 1px solid {C.BORDER}; border-radius: 4px; padding: 3px 6px; }}")
            cur = str(P.get(key) or "")
            for value, text in options:
                box.addItem(text, value)
                if value == cur:
                    box.setCurrentIndex(box.count() - 1)

            def changed(_i, b=box):
                P.save({key: str(b.currentData())})
                self._say(f"Salvo: {label.lower()} — {b.currentText()}.{note}")
            box.currentIndexChanged.connect(changed)
            row.addWidget(box, 1)
            lay.addLayout(row)

        combo("Sensibilidade do microfone (modo Claude)", "mic_sensitivity",
              [(0.6, "Alta — capta voz baixa"), (1.0, "Normal"),
               (1.6, "Baixa — ignora barulho")])
        combo_txt("Palavra de ativação", "wake_engine",
                  [("auto", "Automática (Nexus se der, senão Hey Jarvis)"),
                   ("nexus", "\"Nexus\" / \"Hey Nexus\" (Whisper, offline)"),
                   ("jarvis", "\"Hey Jarvis\" (openWakeWord)"),
                   ("treinada", "\"Nexus\" treinada na minha voz (cadastre: 'treina a palavra Nexus')")],
                  " Vale ao reabrir o app.")
        combo("Sensibilidade da palavra de ativação", "wake_sensitivity",
              [(0.35, "Alta — acorda mais fácil"), (0.5, "Normal"),
               (0.7, "Baixa — menos alarme falso")],
              " Vale ao reabrir o app.")
        ptt = bool(get_push_to_talk_enabled())
        lay.addWidget(self._button(
            f"🎚  Segurar para falar (Ctrl+Espaço): {'LIGADO' if ptt else 'DESLIGADO'}",
            self._toggle_ptt_here))
        lay.addStretch()
        lay.addWidget(self._label(
            "Dicas: se ele não te ouve, teste o microfone e escolha a sensibilidade Alta. "
            "Se ele responde a barulho ou à TV, use Baixa ou ligue o Segurar para falar. "
            "Se a palavra de ativação dispara sozinha, use a sensibilidade Baixa dela.", 7, C.TEXT_DIM))

    def _test_mic(self) -> None:
        from core import settings_tools as S
        self._say("Gravando 3 segundos… fale alguma coisa.")
        import threading

        def run():
            try:
                ok, msg = S.test_microphone(3.0)
            except Exception as e:
                ok, msg = False, f"Teste falhou: {e}"
            self._mic_done.emit(ok, msg)
        threading.Thread(target=run, daemon=True).start()

    def _toggle_ptt_here(self) -> None:
        fn = self._actions.get("ptt")
        if fn:
            fn()
        self._show("audio")

    def _page_gerenciar(self, lay):
        from core import settings_tools as S
        import json as _json
        try:
            facts = len(_json.loads((S.MEMORY_DIR / "facts.json").read_text(encoding="utf-8")))
        except Exception:
            facts = 0
        lay.addWidget(self._label(f"Memória do assistente: {facts} fatos guardados em facts.json."))
        lay.addWidget(self._label("Você pode ver, editar ou apagar o que ele lembra. "
                                  "Para apagar tudo, use RESETAR.", 7, C.TEXT_DIM))
        lay.addStretch()
        lay.addWidget(self._button("🧠  Abrir memória", lambda: self._open("memory")))

    def _page_status(self, lay):
        from core import settings_tools as S
        lay.addWidget(self._label("Estado atual do assistente.", 8))
        for k, v in S.status_info(self._plugin_count):
            row = QHBoxLayout()
            row.addWidget(self._label(k, 8, C.TEXT_DIM))
            val = self._label(v, 8, C.WHITE)
            val.setAlignment(Qt.AlignmentFlag.AlignRight)
            row.addWidget(val)
            lay.addLayout(row)
        lay.addWidget(self._label("Painéis", 8, C.PRI_DIM, bold=True))
        lay.addWidget(self._button("👁  Visão (câmera e tela)", lambda: self._open("vision")))
        lay.addWidget(self._button("📊  Inteligência e métricas", lambda: self._open("intel")))
        lay.addWidget(self._button("📋  Área de transferência", lambda: self._open("clip")))
        lay.addWidget(self._button("🧠  Memória", lambda: self._open("memory")))
        lay.addWidget(self._button("🎧  Dispositivos de áudio", lambda: self._open("audio")))
        lay.addWidget(self._button("📜  Log de atividades", lambda: self._open("log")))
        lay.addStretch()

    def _page_agenda(self, lay):
        P = self._prefs()
        days = set(P.get("brief_weekdays") or [])
        names = ", ".join(self._DAYS[i] for i in sorted(days) if 0 <= i < 7) or "nenhum"
        lay.addWidget(self._label(f"Briefing da manhã: {names}."))
        lay.addWidget(self._label("Notas e lembretes têm uma central própria: crie, procure, edite e "
                                  "cancele por lá — ou peça por voz. Dias do briefing ficam na "
                                  "Configuração do usuário > LEMBRETES E BRIEFING.", 7, C.TEXT_DIM))
        lay.addWidget(self._button("📝  Abrir notas e lembretes", lambda: self._open("agenda")))
        lay.addStretch()

    def _page_apis(self, lay):
        from core import settings_tools as S
        lay.addWidget(self._label("Chaves de API presentes em config/api_keys.json. Os valores não são mostrados."))
        keys = S.api_key_status()
        if not keys:
            lay.addWidget(self._label("Nenhuma chave encontrada.", 8, C.TEXT_DIM))
        for name, ok in keys:
            row = QHBoxLayout()
            row.addWidget(self._label(name, 8, C.TEXT_DIM))
            st = self._label("configurada" if ok else "vazia", 8, C.GREEN if ok else C.MUTED_C)
            st.setAlignment(Qt.AlignmentFlag.AlignRight)
            row.addWidget(st)
            if name in S.TESTABLE_KEYS and ok:
                tb = QPushButton("testar")
                tb.setFixedHeight(22)
                tb.setFont(QFont(FONT_MAIN, 7))
                tb.setCursor(Qt.CursorShape.PointingHandCursor)
                tb.setStyleSheet(f"QPushButton {{ background: transparent; color: {C.PRI};"
                                 f" border: 1px solid {C.BORDER_B}; border-radius: 4px; padding: 0 6px; }}")
                tb.clicked.connect(lambda _=False, n=name: self._test_key(n))
                row.addWidget(tb)
            lay.addLayout(row)
        lay.addStretch()
        lay.addWidget(self._button("◈  Configurar plugins e APIs", lambda: self._open("plugin_settings")))

    def _page_comandos(self, lay):
        lay.addWidget(self._label("Todos os comandos de voz que o assistente conhece, com exemplos."))
        lay.addWidget(self._button("📖  Ver lista de comandos", lambda: self._open("commands")))
        lay.addWidget(self._button("＋  Adicionar comando", lambda: self._open("add_command")))
        from core import comandos_usuario as _cu
        n = len(_cu.listar())
        lay.addWidget(self._label(
            f"Meus comandos: {n}. Crie uma frase sua (ex.: “modo cinema”) e diga o que o NEXUS "
            "deve fazer quando você falar ou digitar essa frase.", 7, C.TEXT_DIM))
        lay.addStretch()

    def _page_lista(self, lay):
        lay.addWidget(self._label("Plugins e ações carregados. Você pode ligar ou desligar cada um."))
        lay.addWidget(self._button("🧩  Gerenciar plugins", lambda: self._open("plugins")))
        lay.addStretch()

    def _page_atuador(self, lay):
        from core import settings_tools as S
        lay.addWidget(self._label(
            "Controla o que o assistente pode fazer no computador. Desligado = ele não executa "
            "e avisa que a permissão está desligada. Vale na hora, sem reiniciar.", 8))
        perms = S.actuator_permissions()
        per_action = S.actuator_action_permissions()
        for group, (label, stems) in S.ACTUATOR_GROUPS.items():
            lay.addWidget(self._check(
                label, perms.get(group, True),
                lambda on, g=group: self._set_actuator(g, on)))
            for stem in stems:
                row = QHBoxLayout()
                row.addSpacing(22)
                row.addWidget(self._check(
                    f"{stem}", per_action.get(stem, True),
                    lambda on, st=stem: self._set_actuator(st, on)))
                lay.addLayout(row)
        lay.addStretch()

    def _set_actuator(self, group: str, on: bool) -> None:
        from core import settings_tools as S
        try:
            S.set_actuator_permission(group, on)
            state = "liberada" if on else "bloqueada"
            self._say(f"Permissão {state}.", C.GREEN if on else C.MUTED_C)
        except Exception as e:
            self._say(f"Não consegui salvar: {e}", C.MUTED_C)

    def _page_avancado(self, lay):
        from core import settings_tools as S
        P = self._prefs()
        # Privacidade e registro ficam num lugar só: a Configuração do usuário.
        lay.addWidget(self._label(
            "Privacidade e registro (memória, resumo da conversa, audit.log): "
            "na Configuração do usuário, seções SEGURANÇA e PRIVACIDADE.", 8))
        lay.addWidget(self._label(f"Pasta do projeto: {S.BASE_DIR}", 7, C.TEXT_DIM))
        lay.addWidget(self._label(f"Backups: {S.BACKUP_DIR}", 7, C.TEXT_DIM))
        lay.addStretch()
        lay.addWidget(self._button("📁  Abrir pasta do projeto", self._open_project_folder))
        lay.addWidget(self._button("📋  Copiar diagnóstico", self._copy_diagnostics))
        lay.addWidget(self._label("Sistema", 8, C.PRI_DIM, bold=True))
        lay.addWidget(self._button("◉  Controle remoto (pelo celular)", lambda: self._open("remote")))
        lay.addWidget(self._button("⊞  Criar atalho na área de trabalho", lambda: self._open("shortcut")))
        on = bool(self._actions["autostart_state"]()) if "autostart_state" in self._actions else False
        lay.addWidget(self._button(
            f"◉  Iniciar com o sistema: {'ON' if on else 'OFF'}",
            lambda: self._run("autostart", refresh="avancado")))
        lay.addWidget(self._button("⬆  Atualizar sistema", lambda: self._open("update")))

    def _open_project_folder(self) -> None:
        from core import settings_tools as S
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(S.BASE_DIR)))

    def _copy_diagnostics(self) -> None:
        from core import settings_tools as S
        QApplication.clipboard().setText(S.diagnostics_text(self._plugin_count))
        self._say("Diagnóstico copiado para a área de transferência.", C.GREEN)

    def _page_backup(self, lay):
        lay.addWidget(self._label(
            "O backup guarda config/api_keys.json (com as chaves de API) e a memória. "
            "Guarde o arquivo em local seguro.", 8))
        lay.addWidget(self._button("💾  Criar backup", self._do_backup))
        lay.addWidget(self._button("♻  Restaurar backup", self._do_restore))
        lay.addWidget(self._label("Antes de restaurar, o estado atual é salvo em memory/backups/.", 7, C.TEXT_DIM))
        lay.addStretch()

    def _do_backup(self) -> None:
        from core import settings_tools as S
        import time as _t
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar backup", str(Path.home() / f"andre_lv_backup_{_t.strftime('%Y%m%d_%H%M')}.zip"),
            "Backup (*.zip)")
        if not path:
            return
        try:
            out = S.create_backup(path)
            self._say(f"Backup salvo em {out}.", C.GREEN)
        except Exception as e:
            self._say(f"Falha no backup: {e}", C.MUTED_C)

    def _do_restore(self) -> None:
        from core import settings_tools as S
        from PyQt6.QtWidgets import QMessageBox
        path, _ = QFileDialog.getOpenFileName(self, "Escolher backup", str(Path.home()), "Backup (*.zip)")
        if not path:
            return
        try:
            members = S.validate_backup(path)
        except Exception as e:
            self._say(f"Backup inválido: {e}", C.MUTED_C)
            return
        ok = QMessageBox.question(
            self, "Restaurar backup",
            "Isto substitui as configurações e a memória atuais por:\n\n"
            + "\n".join(members) + "\n\nReinicie o assistente depois. Continuar?")
        if ok != QMessageBox.StandardButton.Yes:
            return
        try:
            S.restore_backup(path)
            self._say("Backup restaurado. Reinicie o assistente para aplicar tudo.", C.GREEN)
        except Exception as e:
            self._say(f"Falha na restauração: {e}", C.MUTED_C)

    def _page_sobre(self, lay):
        from core import settings_tools as S
        for k, v in S.about_info():
            row = QHBoxLayout()
            row.addWidget(self._label(k, 8, C.TEXT_DIM))
            val = self._label(v, 8, C.WHITE); val.setAlignment(Qt.AlignmentFlag.AlignRight)
            row.addWidget(val)
            lay.addLayout(row)
        lay.addWidget(self._label(
            "NEXUS Ultra 2026 foi desenvolvido por André Luiz Lima Menezes.", 7, C.TEXT_DIM))
        lay.addStretch()
        lay.addWidget(self._button("📋  Copiar diagnóstico", self._copy_diagnostics))

    def _page_isa(self, lay):
        lay.addWidget(self._label(
            "A I.S.A. (Intelligent Systems Architecture) é o núcleo de decisões do NEXUS: junta a "
            "COGNIÇÃO (Gemini, rede neural local, memória) e a AUTOMAÇÃO (as funções que mexem no "
            "computador) e mostra, ao vivo, cada passo — o que chegou, quem decidiu, o que foi feito "
            "e quanto tempo levou. Nada sai do computador; o fluxo some quando o NEXUS fecha."))
        lay.addWidget(self._label("Atalho: Ctrl+I. Por voz: “Nexus, relatório da I.S.A.”. "
                                  "Visual: Controles › HUD › NÚCLEO I.S.A.", 7, C.TEXT_DIM))
        lay.addWidget(self._button("🧠  Abrir o núcleo I.S.A.", lambda: self._open("isa")))
        lay.addStretch()

    def _page_barra(self, lay):
        from .quickbar_editor import QuickBarEditor
        lay.addWidget(QuickBarEditor(on_saved=self._actions.get("quickbar_saved")), 1)

    def _page_atalhos(self, lay):
        from .quickbar_editor import ShortcutsEditor
        lay.addWidget(ShortcutsEditor(on_saved=self._actions.get("shortcuts_saved")), 1)

    def _page_resetar(self, lay):
        from core import settings_tools as S
        lay.addWidget(self._label(
            "Cada reset cria uma cópia de segurança antes. As chaves de API não são apagadas.", 8))
        lay.addWidget(self._button("↺  Resetar só preferências", lambda: self._do_reset("preferencias")))
        lay.addWidget(self._button("↺  Resetar só memória", lambda: self._do_reset("memoria")))
        lay.addWidget(self._button("⚠  Resetar tudo (preferências e memória)", lambda: self._do_reset("tudo")))
        backups = S.list_reset_backups()
        if backups:
            import time as _t
            when = de_timestamp(backups[0].stat().st_mtime).strftime("%d/%m %H:%M")
            lay.addWidget(self._button(f"↶  Desfazer o último reset ({when})", self._do_undo_reset))
        else:
            lay.addWidget(self._label("Nenhum reset para desfazer.", 7, C.TEXT_DIM))
        lay.addStretch()

    def _do_undo_reset(self) -> None:
        from core import settings_tools as S
        from PyQt6.QtWidgets import QMessageBox
        ok = QMessageBox.question(self, "Desfazer reset",
                                  "Restaurar a configuração e a memória de antes do último reset?")
        if ok != QMessageBox.StandardButton.Yes:
            return
        try:
            S.undo_last_reset()
            self._show("resetar")
            self._say("Reset desfeito. Reinicie o assistente para aplicar tudo.", C.GREEN)
        except Exception as e:
            self._say(f"Não consegui desfazer: {e}", C.MUTED_C)

    def _do_reset(self, level: str) -> None:
        from core import settings_tools as S
        from PyQt6.QtWidgets import QMessageBox
        label = S.RESET_LEVELS[level]
        ok = QMessageBox.question(self, "Confirmar reset",
                                  f"Resetar: {label}?\nUma cópia de segurança será criada antes.")
        if ok != QMessageBox.StandardButton.Yes:
            return
        try:
            safety = S.reset(level)
            where = f" Cópia de segurança: {safety.name}." if str(safety) not in ("", ".") else ""
            self._say(f"Reset concluído: {label}.{where}", C.GREEN)
        except Exception as e:
            self._say(f"Falha no reset: {e}", C.MUTED_C)
