"""Configuração do usuário — a ÚNICA janela de configurações do usuário.

Antes eram duas janelas: "Personalizar" (nome, voz, cor, tratamento, idioma,
horário de silêncio) e "Preferências" (todo o resto). Agora a parte de
personalização (ui.CustomizeOverlay em modo embedded) entra como a primeira
seção daqui, e um único SALVAR grava as duas partes.
"""
import platform
import re
import sys
import json

from pathlib import Path

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QComboBox, QCheckBox, QPushButton, QTextEdit,
                             QScrollArea, QFrame, QFileDialog)

from PyQt6.QtCore import Qt, pyqtSignal

from core import preferences as P

def _build_css() -> str:
    """Folha de estilo da janela, montada com as cores do tema ATUAL
    (muda junto com a cor escolhida em Cores/Skin)."""
    from .._base import C
    return f"""
#PreferencesOverlay {{ background: {C.BG}; border: 1px solid {C.BORDER_B}; border-radius: 10px; }}
QLabel {{ color: {C.TEXT}; font-size: 11px; }}
QLabel#Title {{ color: {C.PRI}; font-size: 14px; letter-spacing: 3px; }}
QLabel#Section {{ color: {C.PRI}; font-size: 10px; letter-spacing: 2px; padding-top: 8px; }}
QLineEdit, QComboBox, QTextEdit {{ background: {C.PANEL2}; color: {C.TEXT};
    border: 1px solid {C.BORDER}; border-radius: 6px; padding: 4px; }}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus {{ border: 1px solid {C.PRI}; }}
QCheckBox {{ color: {C.TEXT}; font-size: 11px; }}
QPushButton {{ background: {C.PANEL2}; color: {C.PRI}; border: 1px solid {C.BORDER};
    border-radius: 7px; padding: 6px 12px; font-size: 10px; letter-spacing: 1px; }}
QPushButton:hover {{ border-color: {C.PRI}; background: {C.PRI_GHO}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 7px; margin: 4px 1px; }}
QScrollBar::handle:vertical {{ background: {C.BORDER_B}; border-radius: 3px; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class PreferencesOverlay(QWidget):
    _OW, _OH = 540, 640
    _teste_motor_sig = pyqtSignal(str)      # 1.5 — resultado do TESTAR MODELO

    def __init__(self, parent=None, assistant_section=None):
        """assistant_section: o CustomizeOverlay(embedded=True) criado pela
        janela principal — fica no topo e é salvo junto."""
        super().__init__(parent)
        self._assistant = assistant_section
        self.setObjectName("PreferencesOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)   # o fundo do estilo precisa disto
        self.setStyleSheet(_build_css())
        if parent is not None:
            self._OH = max(420, min(self._OH, parent.height() - 16))
        self.setFixedSize(self._OW, self._OH)
        self._p = P.load()
        self._w: dict = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(8)
        title = QLabel("CONFIGURAÇÃO DO USUÁRIO")
        title.setObjectName("Title")
        root.addWidget(title)

        body = QWidget()
        form = QVBoxLayout(body)
        form.setSpacing(6)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        from PyQt6.QtCore import Qt as _Qt
        scroll.setHorizontalScrollBarPolicy(_Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root.addWidget(scroll, 1)

        if self._assistant is not None:
            self._section(form, "ASSISTENTE E VOCÊ")
            form.addWidget(self._assistant)

        self._section(form, "PERFIL RÁPIDO")
        prow = QHBoxLayout()
        self._profile_box = QComboBox()
        for pkey, ptext in P.PROFILE_LABELS.items():
            self._profile_box.addItem(ptext, pkey)
        prow.addWidget(self._profile_box, 1)
        apply_btn = QPushButton("APLICAR PERFIL")
        apply_btn.clicked.connect(self._apply_profile)
        prow.addWidget(apply_btn)
        form.addLayout(prow)

        self._section(form, "AMBIENTE")
        self._line(form, "background_color", "Cor de fundo (hex, ex. #05060d; vazio = padrão)")
        self._combo(form, "font_size", "Tamanho da fonte",
                    [("pequeno", "Pequeno"), ("medio", "Médio"), ("grande", "Grande")])

        self._section(form, "PAINEL")
        self._check(form, "show_clock", "Mostrar relógio")
        self._check(form, "show_date", "Mostrar data")

        self._section(form, "FORMATOS")
        self._combo(form, "hour_format", "Horário",
                    [("24", "24 horas"), ("12", "12 horas (AM/PM)")])
        self._combo(form, "temp_unit", "Temperatura",
                    [("C", "Celsius (°C)"), ("F", "Fahrenheit (°F)")])
        self._combo(form, "distance_unit", "Distância",
                    [("km", "Quilômetros"), ("mi", "Milhas")])

        self._section(form, "NOTÍCIAS")
        self._combo(form, "news_frequency", "Frequência do monitor",
                    [("diaria", "Uma vez por dia"), ("6h", "A cada 6 horas"),
                     ("manual", "Só quando eu pedir")])

        self._section(form, "FERRAMENTAS  (valem na próxima conversa)")
        self._combo(form, "carga_ferramentas", "Ferramentas que o NEXUS mostra à IA",
                    [("completo", "Todas (como sempre foi)"), ("recentes", "As essenciais e as que eu uso"),
                     ("essencial", "Só o básico (mais rápido)")])

        self._section(form, "ALERTAS E MODOS")
        self._check(form, "quiet_when_busy", "Silenciar notícias e check-ins em reunião ou jogo em tela cheia")
        self._line(form, "max_alerts_per_hour", "Máximo de alertas de notícias por hora (0 = nenhum)")
        self._line(form, "alert_keywords", "Palavras-chave dos alertas (vírgula; vazio = todos)")
        self._line(form, "sleep_after_minutes", "Dormir após quantos minutos de silêncio")
        self._line(form, "battery_alert_percent", "Avisar quando a bateria cair abaixo de (%, 0 = desligado)")

        self._section(form, "ATALHOS  (valem ao reabrir o app)")
        self._line(form, "shortcut_mute", "Mudo / microfone (ex. F4)")
        self._line(form, "shortcut_fullscreen", "Tela cheia (ex. F11)")
        self._line(form, "shortcut_interrupt", "Interromper a fala (ex. Escape)")

        self._section(form, "LEMBRETES E BRIEFING")
        self._line(form, "water_reminder_minutes", "Lembrete de água a cada N minutos (0 = desligado)")
        form.addWidget(QLabel("Dias do briefing da manhã:"))
        dias_row = QHBoxLayout()
        self._day_boxes = []
        for i, nome in enumerate(["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]):
            box = QCheckBox(nome)
            box.setChecked(i in (self._p.get("brief_weekdays") or []))
            dias_row.addWidget(box)
            self._day_boxes.append((i, box))
        form.addLayout(dias_row)

        self._section(form, "CLIMA")
        self._line(form, "weather_city", "Cidade padrão do clima (vazio = perguntar)")
        det = QPushButton("DETECTAR CIDADE PELA INTERNET  (envia seu IP a ipapi.co)")
        det.clicked.connect(self._detect_city)
        form.addWidget(det)

        self._section(form, "VOZ  (velocidade e volume valem só no modo Claude)")
        self._line(form, "voice_rate", "Velocidade (palavras por minuto, ex. 185)")
        self._line(form, "voice_volume", "Volume (0 a 100)")

        self._section(form, "JANELA")
        self._check(form, "minimize_to_tray", "Fechar a janela deixa o Nexus na bandeja (vale ao reabrir)")

        self._section(form, "MEMÓRIA")
        mem_row = QHBoxLayout()
        ex = QPushButton("EXPORTAR MEMÓRIA"); ex.clicked.connect(self._export_memory)
        im = QPushButton("IMPORTAR MEMÓRIA"); im.clicked.connect(self._import_memory)
        mem_row.addWidget(ex); mem_row.addWidget(im)
        form.addLayout(mem_row)

        self._section(form, "CONVERSA  (tom e vocabulário)")
        self._combo(form, "reply_tone", "Tom das respostas (só modo Claude)",
                    [("", "Padrão"), ("formal", "Formal"), ("casual", "Casual"), ("direto", "Direto")])
        self._line(form, "custom_vocabulary", "Nomes e termos próprios (vírgula) para a transcrição")

        # 1.4 — velocidade da resposta (config/api_keys.json: turn_tuning, proactive_audio)
        self._section(form, "VELOCIDADE DA RESPOSTA  (vale na hora — reconecta sem perder a conversa)")
        try:
            from memory.config_manager import get_proactive_audio_enabled, get_turn_tuning
            _rapido = bool(get_turn_tuning().get("enabled"))
            _proativo = bool(get_proactive_audio_enabled())
        except Exception:
            _rapido, _proativo = False, True
        self._vel_antes = (_rapido, _proativo)
        vrow = QHBoxLayout()
        vrow.addWidget(QLabel("Quando responder"), 1)
        self._velocidade = QComboBox()
        self._velocidade.addItem("Natural — espera você terminar a frase (padrão)", "natural")
        self._velocidade.addItem("Rápido — responde assim que você faz uma pausa", "rapido")
        self._velocidade.setCurrentIndex(1 if _rapido else 0)
        vrow.addWidget(self._velocidade, 1)
        form.addLayout(vrow)
        self._proativo = QCheckBox("Só responder quando a fala for para o NEXUS "
                                   "(se as respostas parecerem atrasadas, desligue)")
        self._proativo.setChecked(_proativo)
        form.addWidget(self._proativo)

        self._build_motor(form)      # 1.5 — MOTOR DE VOZ

        self._section(form, "SEGURANÇA")
        self._check(form, "audit_enabled", "Registrar ações em memory/audit.log")
        pw_btn = QPushButton("DEFINIR SENHA DO PAINEL  (vazio remove)")
        pw_btn.clicked.connect(self._set_password)
        form.addWidget(pw_btn)

        self._section(form, "PRIVACIDADE")
        self._check(form, "save_memory_enabled", "Salvar fatos pessoais na memória de longo prazo")
        self._check(form, "clear_history_on_exit", "Não gravar o resumo da conversa ao sair")

        self._section(form, "VISÃO LOCAL  (ler e descrever a tela sem internet)")
        self._check(form, "visao_somente_local",
                    "Modo privado: a tela e a câmera nunca vão para a nuvem (o NEXUS olha no próprio PC)")
        self._combo(form, "visao_ocr_motor", "Leitor de texto (OCR)",
                    [("auto", "Automático"), ("windows", "OCR do Windows"),
                     ("rapidocr", "RapidOCR (qualquer sistema)")])
        self._line(form, "visao_local_modelo",
                   "Modelo do Ollama para descrever imagens (vazio = automático; ex. gemma3:4b, moondream)")

        self._section(form, "PROGRAMAS")
        self._check(form, "open_app_busca_iniciar",
                    "Se não achar um programa, procurar digitando o nome no menu Iniciar")

        self._section(form, "APELIDOS DE APPS  (uma linha por apelido: apelido = nome do app)")
        self._aliases = QTextEdit()
        self._aliases.setPlainText("\n".join(f"{k} = {v}" for k, v in self._p["app_aliases"].items()))
        self._aliases.setFixedHeight(90)
        form.addWidget(self._aliases)

        self._section(form, "DIAGNÓSTICO")
        diag_btn = QPushButton("GERAR DIAGNÓSTICO")
        diag_btn.clicked.connect(self._diagnose)
        form.addWidget(diag_btn)
        self._diag = QTextEdit()
        self._diag.setReadOnly(True)
        self._diag.setFixedHeight(130)
        form.addWidget(self._diag)
        form.addStretch()

        bar = QHBoxLayout()
        self._status = QLabel("")
        close = QPushButton("FECHAR")
        close.clicked.connect(self._close)
        save = QPushButton("SALVAR")
        save.clicked.connect(self._save)
        bar.addWidget(self._status, 1)
        bar.addWidget(close)
        bar.addWidget(save)
        root.addLayout(bar)

    # ── 1.5 — MOTOR DE VOZ ──
    def _build_motor(self, form) -> None:
        from memory.config_manager import get_motor_config
        from core.llm_providers import PROVEDORES
        cfg = get_motor_config()
        self._motor_antes = json.dumps(cfg, sort_keys=True, ensure_ascii=False)
        self._section(form, "MOTOR DE VOZ  (vale na hora)")
        info = QLabel("Gemini Live: conversa por voz em tempo real (padrão). Motor próprio: "
                      "o Whisper ouve no seu PC, o modelo que você escolher pensa e a voz "
                      "que você escolher fala — inclusive tudo offline (Ollama + Piper).")
        info.setWordWrap(True)
        form.addWidget(info)

        def linha(rotulo, widget):
            r = QHBoxLayout()
            lab = QLabel(rotulo); lab.setWordWrap(True)
            r.addWidget(lab, 1); r.addWidget(widget, 1)
            form.addLayout(r)

        self._m_motor = QComboBox()
        self._m_motor.addItem("Gemini Live (tempo real)", "gemini_live")
        self._m_motor.addItem("Motor próprio (STT + LLM + TTS)", "proprio")
        self._m_motor.setCurrentIndex(1 if cfg["motor"] == "proprio" else 0)
        linha("Motor", self._m_motor)

        self._m_prov = QComboBox()
        for chave, d in PROVEDORES.items():
            self._m_prov.addItem(d["nome"], chave)
        i = self._m_prov.findData(cfg.get("llm_provider") or "gemini")
        self._m_prov.setCurrentIndex(i if i >= 0 else 0)
        linha("Modelo de texto (cérebro)", self._m_prov)

        self._m_modelo = QLineEdit(str(cfg.get("llm_model") or ""))
        linha("Nome do modelo (vazio = padrão)", self._m_modelo)
        self._m_url = QLineEdit(str(cfg.get("llm_url") or ""))
        linha("Endereço (vazio = padrão do provedor)", self._m_url)
        self._m_chave = QLineEdit()
        self._m_chave.setEchoMode(QLineEdit.EchoMode.Password)
        linha("Chave do provedor (Claude e Gemini usam as de sempre)", self._m_chave)
        self._m_chaves = dict(cfg.get("llm_keys") or {})

        def _prov_mudou(_i=0):
            from core.llm_providers import info_provedor
            prov = self._m_prov.currentData()
            d = info_provedor(prov)
            self._m_modelo.setPlaceholderText(d.get("modelo") or "o que estiver carregado")
            self._m_url.setPlaceholderText(d.get("url") or "API da Anthropic")
            self._m_chave.setText(self._m_chaves.get(prov, ""))
            self._m_chave.setPlaceholderText("não precisa (roda no PC)" if d.get("local") else "cole a chave aqui")
        self._m_prov.currentIndexChanged.connect(_prov_mudou)
        _prov_mudou()
        self._m_chave.textChanged.connect(
            lambda t: self._m_chaves.__setitem__(self._m_prov.currentData(), t.strip()))

        self._m_whisper = QComboBox()
        for v, t in (("tiny", "tiny — o mais leve"), ("base", "base — leve"),
                     ("small", "small — recomendado"), ("medium", "medium — mais preciso, pesado")):
            self._m_whisper.addItem(t, v)
        i = self._m_whisper.findData(cfg.get("whisper_model") or "small")
        self._m_whisper.setCurrentIndex(i if i >= 0 else 2)
        linha("Ouvido (Whisper, no seu PC)", self._m_whisper)

        self._m_tts = QComboBox()
        for v, t in (("piper", "Piper — neural e offline (~50 idiomas)"),
                     ("elevenlabs", "ElevenLabs — ao vivo, todas as línguas"),
                     ("edge", "Edge — vozes da Microsoft, online e grátis"),
                     ("clone", "Ricardo — voz clonada da amostra (XTTS, offline, só uso não comercial)"),
                     ("sistema", "Voz do Windows")):
            self._m_tts.addItem(t, v)
        # a amostra e a licença do modelo clonado ficam como estão; escolher a voz aceita a licença
        self._clone_voz = str(cfg.get("clone_voz") or "Ricardo")
        self._clone_aceita = bool(cfg.get("clone_licenca_aceita"))
        i = self._m_tts.findData(cfg.get("tts_motor") or "piper")
        self._m_tts.setCurrentIndex(i if i >= 0 else 0)
        linha("Voz", self._m_tts)
        self._m_el_chave = QLineEdit(str(cfg.get("elevenlabs_api_key") or ""))
        self._m_el_chave.setEchoMode(QLineEdit.EchoMode.Password)
        linha("Chave da ElevenLabs", self._m_el_chave)
        self._m_el_voz = QLineEdit(str(cfg.get("elevenlabs_voice_id") or ""))
        self._m_el_voz.setPlaceholderText("vazio = voz padrão")
        linha("Voice ID da ElevenLabs", self._m_el_voz)

        self._m_orc = QComboBox()
        for v, t in (("auto", "Automático — só para modelos no PC"), ("sempre", "Sempre"),
                     ("nunca", "Nunca (todas as ferramentas)")):
            self._m_orc.addItem(t, v)
        i = self._m_orc.findData(cfg.get("orcamento_ferramentas") or "auto")
        self._m_orc.setCurrentIndex(i if i >= 0 else 0)
        linha("Orçamento de ferramentas", self._m_orc)

        trow = QHBoxLayout()
        teste = QPushButton("TESTAR MODELO")
        teste.clicked.connect(self._testar_motor)
        self._m_status = QLabel("")
        self._m_status.setWordWrap(True)
        trow.addWidget(teste); trow.addWidget(self._m_status, 1)
        form.addLayout(trow)
        self._teste_motor_sig.connect(self._m_status.setText)
        dica = QLabel("No PC sem internet: instale o Ollama (ollama.com), rode  ollama pull qwen3:8b  "
                      "e escolha Ollama + Piper. Pacotes: pip install faster-whisper piper-tts. "
                      "Voz do Ricardo: pip install coqui-tts miniaudio (modelo de ~1,8 GB; "
                      "a amostra fica em config/voices/Ricardo.mp3).")
        dica.setWordWrap(True)
        form.addWidget(dica)

    def _valores_motor(self) -> dict:
        return {
            "motor": self._m_motor.currentData(),
            "llm_provider": self._m_prov.currentData(),
            "llm_model": self._m_modelo.text().strip(),
            "llm_url": self._m_url.text().strip(),
            "llm_keys": {k: v for k, v in self._m_chaves.items() if k not in ("claude", "gemini") or v},
            "whisper_model": self._m_whisper.currentData(),
            "tts_motor": self._m_tts.currentData(),
            "elevenlabs_api_key": self._m_el_chave.text().strip(),
            "elevenlabs_voice_id": self._m_el_voz.text().strip(),
            "clone_voz": self._clone_voz,
            "clone_licenca_aceita": self._clone_aceita or self._m_tts.currentData() == "clone",
            "orcamento_ferramentas": self._m_orc.currentData(),
        }

    def _testar_motor(self) -> None:
        import threading
        v = self._valores_motor()
        self._m_status.setText("Testando…")

        def _rodar():
            try:
                from core.llm_providers import CerebroLLM, testar_conexao
                prov = v["llm_provider"]
                chave = v["llm_keys"].get(prov, "")
                if not chave:
                    from memory.config_manager import get_motor_config
                    chave = (get_motor_config().get("llm_keys") or {}).get(prov, "")
                ok, msg = testar_conexao(CerebroLLM(prov, v["llm_model"], v["llm_url"], chave))
                self._teste_motor_sig.emit(("✔ " if ok else "✖ ") + msg)
            except Exception as e:
                self._teste_motor_sig.emit(f"✖ {str(e)[:200]}")
        threading.Thread(target=_rodar, daemon=True).start()

    def _salvar_motor(self) -> None:
        from memory.config_manager import get_motor_config, save_motor_config
        save_motor_config(self._valores_motor())
        depois = json.dumps(get_motor_config(), sort_keys=True, ensure_ascii=False)
        if depois != getattr(self, "_motor_antes", depois):
            self._motor_antes = depois
            cb = getattr(self.parent(), "on_live_settings_change", None)
            if not callable(cb):
                cb = getattr(self.window(), "on_live_settings_change", None)
            if callable(cb):
                cb("engine")

    # ── builders ──
    def _section(self, lay, text):
        lab = QLabel(text)
        lab.setWordWrap(True)          # títulos longos não alargam a janela
        lab.setObjectName("Section")
        lay.addWidget(lab)

    def _line(self, lay, key, label):
        row = QVBoxLayout()
        _lab = QLabel(label); _lab.setWordWrap(True)
        row.addWidget(_lab)
        edit = QLineEdit(str(self._p.get(key, "")))
        row.addWidget(edit)
        lay.addLayout(row)
        self._w[key] = edit

    def _combo(self, lay, key, label, options):
        row = QHBoxLayout()
        row.addWidget(QLabel(label), 1)
        box = QComboBox()
        current = str(self._p.get(key))
        for value, text in options:
            box.addItem(text, value)
            if value == current:
                box.setCurrentIndex(box.count() - 1)
        row.addWidget(box, 1)
        lay.addLayout(row)
        self._w[key] = box

    def _check(self, lay, key, label):
        box = QCheckBox(label)
        box.setChecked(bool(self._p.get(key)))
        lay.addWidget(box)
        self._w[key] = box

    # ── actions ──
    def _save(self):
        values = {}
        for key, w in self._w.items():
            if isinstance(w, QLineEdit):
                values[key] = w.text().strip()
            elif isinstance(w, QComboBox):
                values[key] = w.currentData()
            elif isinstance(w, QCheckBox):
                values[key] = w.isChecked()

        bg = values.get("background_color", "")
        if bg and not _HEX_RE.match(bg):
            self._status.setText("Cor inválida. Use o formato #rrggbb.")
            return
        values["brief_weekdays"] = [i for i, b in self._day_boxes if b.isChecked()]
        for ikey in ("max_alerts_per_hour", "sleep_after_minutes", "water_reminder_minutes",
                     "voice_rate", "voice_volume", "battery_alert_percent"):
            try:
                values[ikey] = int(values.get(ikey, 0))
            except (TypeError, ValueError):
                self._status.setText(f"Valor inválido em {ikey}: use um número.")
                return
        values["app_aliases"] = self._parse_aliases()
        P.save(values)
        try:   # 1.4 — velocidade da resposta (fica fora das preferências)
            from memory.config_manager import save_proactive_audio_enabled, save_turn_tuning
            _rap = self._velocidade.currentData() == "rapido"
            _pro = self._proativo.isChecked()
            save_turn_tuning({"enabled": _rap})
            save_proactive_audio_enabled(_pro)
            # 1.4.3 — aplica já (antes só valia ao reabrir o NEXUS)
            if (_rap, _pro) != getattr(self, "_vel_antes", (_rap, _pro)):
                self._vel_antes = (_rap, _pro)
                cb = getattr(self.parent(), "on_live_settings_change", None)
                if not callable(cb):
                    cb = getattr(self.window(), "on_live_settings_change", None)
                if callable(cb):
                    cb()
        except Exception as e:
            print(f"[Settings] velocidade da resposta não salva: {e}")
        try:   # 1.5 — motor de voz
            self._salvar_motor()
        except Exception as e:
            print(f"[Settings] motor de voz não salvo: {e}")
        if self._assistant is not None:
            try:
                self._assistant._save()     # nome, voz, cor, tratamento, idioma, silêncio
            except Exception as e:
                self._status.setText(f"Preferências salvas, mas a parte do assistente falhou: {e}")
                return
        self._status.setText("Salvo. Nome, voz, cor, formatos e apelidos valem agora; "
                             "a cor de fundo e a fonte, ao reabrir o app.")

    def _close(self):
        # Fechar sem salvar desfaz a prévia da cor da interface.
        if self._assistant is not None:
            try:
                self._assistant._cancel()
            except Exception:
                pass
        self.hide()

    def _apply_profile(self):
        pkey = self._profile_box.currentData()
        values = dict(P.PROFILES[pkey])
        values["profile"] = pkey
        P.save(values)
        self._fill(values)
        self._status.setText(f"Perfil aplicado: {self._profile_box.currentText()}.")

    def _fill(self, values: dict):
        for key, val in values.items():
            if key == "brief_weekdays":
                for i, box in self._day_boxes:
                    box.setChecked(i in (val or []))
                continue
            w = self._w.get(key)
            if isinstance(w, QLineEdit):
                w.setText(str(val))
            elif isinstance(w, QCheckBox):
                w.setChecked(bool(val))
            elif isinstance(w, QComboBox):
                idx = w.findData(str(val))
                if idx >= 0:
                    w.setCurrentIndex(idx)

    def _set_password(self):
        from PyQt6.QtWidgets import QInputDialog, QLineEdit
        pw, ok = QInputDialog.getText(self, "Senha do painel",
                                      "Nova senha (vazio remove a senha):",
                                      QLineEdit.EchoMode.Password)
        if not ok:
            return
        P.set_password(pw.strip())
        self._status.setText("Senha removida." if not pw.strip() else "Senha definida.")

    def _detect_city(self):
        try:
            import requests
            city = (requests.get("https://ipapi.co/json/", timeout=5).json().get("city") or "").strip()
        except Exception as e:
            self._status.setText(f"Falha ao detectar a cidade: {e}")
            return
        if city:
            self._w["weather_city"].setText(city)
            self._status.setText(f"Cidade detectada: {city}. Clique em SALVAR para aplicar.")
        else:
            self._status.setText("Não consegui detectar a cidade.")

    def _export_memory(self):
        import json
        from memory.memory_manager import load_memory
        path, _ = QFileDialog.getSaveFileName(self, "Exportar memória", "nexus_memoria.json",
                                              "JSON (*.json)")
        if not path:
            return
        Path(path).write_text(json.dumps(load_memory(), ensure_ascii=False, indent=2), encoding="utf-8")
        self._status.setText("Memória exportada.")

    def _import_memory(self):
        import json
        path, _ = QFileDialog.getOpenFileName(self, "Importar memória", "", "JSON (*.json)")
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as e:
            self._status.setText(f"Arquivo inválido: {e}")
            return
        if not isinstance(data, dict):
            self._status.setText("Arquivo inválido: esperado um objeto JSON.")
            return
        from memory.memory_manager import update_memory
        update_memory(data)
        self._status.setText("Memória importada e mesclada com a atual.")

    def _parse_aliases(self) -> dict:
        out = {}
        for line in self._aliases.toPlainText().splitlines():
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip().lower(), v.strip()
            if k and v:
                out[k] = v
        return out

    def _diagnose(self):
        try:
            from actions.system_update import current_version
            _ver = current_version().get("version", "?")
        except Exception:
            _ver = "?"
        lines = [f"Versão: NEXUS {_ver}",
                 f"Sistema: {platform.platform()}",
                 f"Python: {sys.version.split()[0]}"]
        try:
            import sounddevice as sd
            devs = sd.query_devices()
            ins = sum(1 for d in devs if d["max_input_channels"] > 0)
            outs = sum(1 for d in devs if d["max_output_channels"] > 0)
            lines.append(f"Áudio: {ins} entrada(s), {outs} saída(s)")
            lines.append(f"Microfone padrão: {sd.query_devices(kind='input')['name']}")
            lines.append(f"Alto-falante padrão: {sd.query_devices(kind='output')['name']}")
        except Exception as e:
            lines.append(f"Áudio: erro ao listar dispositivos ({e})")
        try:
            from memory.config_manager import load_api_keys
            keys = load_api_keys()
            for name in ("anthropic_api_key", "gemini_api_key"):
                val = str(keys.get(name) or "")
                lines.append(f"{name}: {'definida' if len(val) > 10 else 'vazia'}")
        except Exception as e:
            lines.append(f"Chaves: erro ao ler config ({e})")
        lines.append("Preferências: " + json.dumps(P.load(), ensure_ascii=False))
        self._diag.setPlainText("\n".join(lines))
