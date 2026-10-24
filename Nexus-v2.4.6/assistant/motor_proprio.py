"""MOTOR PRÓPRIO (NEXUS Pro 1.5): seu próprio STT + LLM + TTS no lugar do Gemini Live.

Mixin de NexusLive (assistant/core.py). Escolhido na Configuração do usuário ›
MOTOR DE VOZ, sem editar arquivo; trocar vale na hora.

    microfone → Whisper (no seu PC, descobre o idioma)
              → o modelo que você escolheu (Claude, Gemini, OpenAI, Groq, DeepSeek,
                Mistral, xAI, OpenRouter, Ollama, LM Studio, llama.cpp, vLLM),
                com as MESMAS ferramentas do NEXUS
              → a voz que você escolheu (Piper offline, ElevenLabs, Edge ou Windows),
                no idioma da resposta

Tudo continua aparecendo na janela: a conversa, o HUD (ouvindo / pensando /
falando), a onda da voz, o núcleo I.S.A. A caixa de comando, a barra rápida,
os lembretes e os timers falam por aqui também.

Diferenças do Gemini Live: é meio-duplex (enquanto ele fala, o microfone não
escuta — o botão de interromper corta a fala) e os avisos automáticos que
dependem da sessão do Gemini (e-mail novo, check-ins proativos) ficam para
quando voltar ao Gemini Live.
"""
from __future__ import annotations

import base64
import queue
import threading
import time
import types as _pytypes

import numpy as np

from .common import _pcm_level, agora, asyncio, audio_devices, data_hora  # noqa: F401

_TAXA_MIC = 16000
_BLOCO = 512                      # 32 ms
_SILENCIO_FIM = 0.5               # pausa que fecha a fala (2.4.5: 0,7 → 0,5 s; é tempo ganho em TODO pedido)
_FALA_MAX = 25.0
_FALA_MIN = 0.35
_PRE = 0.3
_RODADAS = 8

# Ferramentas rápidas: não precisam de "um instante…"
_RAPIDAS = frozenset({"save_memory", "recall_memory", "undo", "system_status", "open_app",
                      "computer_settings", "music_control", "timer_action", "quick_notes",
                      "close_camera", "isa_core", "unit_converter", "everyday_tools",
                      "memory_bank", "focus_mode", "tarefas", "compras", "rastreador_habitos",
                      "contatos", "texto_dev", "diario"})

# ⚡ Confirmação instantânea (no idioma de quem falou), dita enquanto a
# ferramenta roda — o motor próprio pode falar no meio de uma ferramenta.
_JA_VOU = {
    "pt": {"web_search": "Vou pesquisar.", "weather_report": "Vendo a previsão.",
           "email_checker": "Vou olhar seus e-mails.", "email_reader": "Vou olhar seus e-mails.",
           "screen_process": "Deixa eu ver.", "browser_control": "Um instante, no navegador.",
           "dev_agent": "Vou montar o projeto, isso leva alguns minutos.",
           "code_helper": "Vou cuidar do código.", "file_processor": "Vou ler o arquivo.",
           "agent_task": "Certo, vou cuidar disso passo a passo.",
           "send_message": "Enviando a mensagem.", "youtube_video": "Um instante, no YouTube.",
           "_": "Só um instante."},
    "en": {"web_search": "Let me look that up.", "weather_report": "Checking the forecast.",
           "email_checker": "Checking your email.", "screen_process": "Let me see.",
           "dev_agent": "Building the project, this takes a few minutes.",
           "agent_task": "On it, step by step.", "_": "One moment."},
    "es": {"web_search": "Voy a buscarlo.", "screen_process": "Déjame ver.", "_": "Un momento."},
}


def _ja_vou(nome: str, idioma: str) -> str:
    tab = _JA_VOU.get((idioma or "pt")[:2], _JA_VOU["en"])
    return tab.get(nome) or tab["_"]


class MotorProprioMixin:
    _motor_ativo = "gemini_live"
    _proprio_fila: asyncio.Queue | None = None
    _proprio_tocador = None
    _proprio_idioma = "pt"

    # ── escolha do motor ────────────────────────────────────────────────────
    def _modo_motor(self) -> str:
        try:
            from memory.config_manager import get_motor_config
            return get_motor_config()["motor"]
        except Exception:
            return "gemini_live"

    def _proprio_submit(self, texto: str, origem: str = "digitado", imagens=None) -> bool:
        """Thread-safe: entrega um pedido ao motor próprio (texto digitado, um
        aviso do app, a fala de um lembrete…)."""
        fila, loop = self._proprio_fila, self._loop
        if fila is None or loop is None:
            return False
        loop.call_soon_threadsafe(fila.put_nowait, ("texto", texto, origem, imagens))
        return True

    def _proprio_parar_fala(self) -> None:
        t = self._proprio_tocador
        if t is not None:
            t.parar()

    # ── o laço ─────────────────────────────────────────────────────────────
    async def _run_proprio(self) -> None:
        from memory.config_manager import get_motor_config, get_output_device, get_input_device
        from core import llm_providers as L
        from core import voz_propria as V

        loop = asyncio.get_running_loop()
        self._motor_ativo = "proprio"
        self._proprio_fila = asyncio.Queue()
        self._proprio_hist: list[dict] = []
        cfg = get_motor_config()
        self.ui.set_state("THINKING")
        log = lambda m: self.ui.write_log(f"SYS: {m}")   # noqa: E731

        # ── cérebro ──
        prov = str(cfg.get("llm_provider") or "gemini").lower()
        try:
            self._proprio_cerebro = L.CerebroLLM(
                prov, cfg.get("llm_model") or "", cfg.get("llm_url") or "",
                (cfg.get("llm_keys") or {}).get(prov, ""))
        except Exception as e:
            log(f"Motor próprio: o modelo não abriu — {e}. Ajuste em Configuração do usuário › "
                f"MOTOR DE VOZ (ou volte para o Gemini Live).")
            self.ui.set_state("SLEEPING")
            await self._reconnect_event.wait()
            self._reconnect_event.clear()
            return

        # ── pacotes da voz local: instala sozinho na primeira vez ──
        await asyncio.to_thread(self._garantir_pacotes, cfg, log)

        # ── voz ──
        voz = await asyncio.to_thread(V.criar_voz, cfg, log)
        self._proprio_voz = voz
        try:
            disp_saida = audio_devices.resolve(get_output_device(), "output")
        except Exception:
            disp_saida = None
        self._proprio_tocador = V.Tocador(disp_saida, ao_nivel=self.ui.set_audio_level)

        # ── ouvido ──
        ouvido = None
        try:
            from core import preferences as _Pp
            vocab = str(_Pp.get("custom_vocabulary") or "")
        except Exception:
            vocab = ""
        try:
            log(f"Motor próprio: carregando o Whisper '{cfg.get('whisper_model') or 'small'}' "
                f"(na 1ª vez ele baixa o modelo)…")
            ouvido = await asyncio.to_thread(V.OuvidoWhisper, cfg.get("whisper_model") or "small",
                                             cfg.get("stt_idioma") or "auto", vocab)
        except ImportError:
            log("Motor próprio: para ouvir pelo microfone instale  pip install faster-whisper  "
                "— por enquanto só pela caixa de comando.")
        except Exception as e:
            log(f"Motor próprio: o Whisper não abriu ({e}) — por enquanto só pela caixa de comando.")

        self._proprio_orcamento = (str(cfg.get("orcamento_ferramentas") or "auto").lower())
        self._proprio_stream = bool(cfg.get("llm_streaming", True))      # 2.4.6
        desc = (f"{ouvido.descricao if ouvido else 'sem microfone'} + "
                f"{self._proprio_cerebro.descricao()} + {getattr(voz, 'nome', 'voz')}")
        log(f"NEXUS online — motor próprio: {desc}.")
        try:
            from core import isa as _isa
            _isa.definir("conexao", "motor próprio")
            _isa.definir("modelo", self._proprio_cerebro.descricao())
        except Exception:
            pass

        # ── microfone em thread própria ──
        parar_mic = threading.Event()
        if ouvido is not None:
            try:
                disp_mic = audio_devices.resolve(get_input_device(), "input")
            except Exception:
                disp_mic = None
            threading.Thread(target=self._proprio_microfone, args=(disp_mic, parar_mic, loop),
                             daemon=True, name="nexus-mic-proprio").start()

        if self._wake_enabled:
            self._ensure_wake_detector()
            self._awake = False
            self.ui.set_state("SLEEPING")
        else:
            self._awake = True
            self.ui.set_state("LISTENING")
        sono = asyncio.create_task(self._run_sleep_watch())

        try:
            while not self._reconnect_event.is_set():
                try:
                    item = await asyncio.wait_for(self._proprio_fila.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                tipo = item[0]
                try:
                    if tipo == "voz":
                        audio = item[1]
                        self.ui.set_state("THINKING")
                        texto, idioma = await asyncio.to_thread(ouvido.transcrever, audio)
                        if not texto.strip():
                            self.ui.set_state("LISTENING" if not self.ui.muted else "SLEEPING")
                            continue
                        self._proprio_idioma = idioma or self._proprio_idioma
                        await self._proprio_turno(texto, "voz")
                    else:
                        _, texto, origem, imagens = item
                        await self._proprio_turno(texto, origem, imagens)
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    log(f"Motor próprio: {type(e).__name__}: {str(e)[:200]}")
                finally:
                    if not self.ui.muted and self._awake:
                        self.ui.set_state("LISTENING")
        finally:
            parar_mic.set()
            sono.cancel()
            self._proprio_fila = None
            self._motor_ativo = "gemini_live"
            try:
                self._proprio_tocador.parar()
                self._proprio_tocador.fechar()
            except Exception:
                pass
            self._proprio_tocador = None
            self._reconnect_event.clear()
            self.set_speaking(False)
            if len(self._session_log) >= 3:
                asyncio.create_task(self._save_session_summary())

    @staticmethod
    def _garantir_pacotes(cfg: dict, log) -> None:
        import importlib.util
        import sys as _sys
        precisa = [("faster_whisper", "faster-whisper")]
        precisa += {"piper": [("piper", "piper-tts")],
                    "edge": [("edge_tts", "edge-tts"), ("miniaudio", "miniaudio")],
                    "sistema": [("pyttsx3", "pyttsx3")]}.get(str(cfg.get("tts_motor") or "piper"), [])
        faltam = [(m, p) for m, p in precisa if importlib.util.find_spec(m) is None]
        if not faltam:
            return
        nomes = " ".join(p for _, p in faltam)
        if getattr(_sys, "frozen", False):
            log(f"Motor próprio: faltam pacotes — rode uma vez:  python -m pip install {nomes}")
            return
        log(f"Motor próprio: instalando {nomes} (só na primeira vez, pode levar alguns minutos)…")
        try:
            from core.installer import _pip
            for _m, pacote in faltam:
                _pip(pacote, lambda m: log(m.replace("SYS: ", "").replace("ERR: ", "")))
            importlib.invalidate_caches()
        except Exception as e:
            log(f"Motor próprio: não consegui instalar ({e}). Rode:  pip install {nomes}")

    # ── microfone (thread) ──────────────────────────────────────────────────
    def _proprio_microfone(self, disp, parar: threading.Event, loop) -> None:
        import sounddevice as sd
        q: queue.Queue = queue.Queue(maxsize=600)

        def cb(indata, frames, t, status):
            # dormindo: só a palavra de ativação ouve
            if self._wake_enabled and not self._awake:
                det = self._wake_detector
                if det is not None:
                    det.feed(indata)
                return
            with self._speaking_lock:
                falando = self._is_speaking
            if falando or self._tail_active() or self.ui.muted:
                return
            if self._ptt_enabled and not self._ptt_held:
                return
            try:
                q.put_nowait(indata[:, 0].copy())
            except queue.Full:
                pass

        try:
            st = sd.InputStream(samplerate=_TAXA_MIC, channels=1, dtype="int16",
                                blocksize=_BLOCO, device=disp, callback=cb)
        except Exception:
            st = sd.InputStream(samplerate=_TAXA_MIC, channels=1, dtype="int16",
                                blocksize=_BLOCO, callback=cb)
        try:
            from core import preferences as _Pp
            sens = float(_Pp.get("mic_sensitivity") or 1.0)
        except Exception:
            sens = 1.0
        limiar = 400.0 * sens
        niveis: list[float] = []
        pre: list[np.ndarray] = []
        partes: list[np.ndarray] = []
        gravando, silencio, inicio = False, 0.0, 0.0
        dur = _BLOCO / _TAXA_MIC
        with st:
            while not parar.is_set():
                try:
                    bloco = q.get(timeout=0.3)
                except queue.Empty:
                    continue
                nivel = float(np.sqrt(np.mean(bloco.astype(np.float32) ** 2)))
                try:
                    self.ui.set_audio_level(_pcm_level(bloco))
                except Exception:
                    pass
                if not gravando:
                    # ruído da sala: o limiar acompanha o ambiente
                    niveis.append(nivel); niveis = niveis[-60:]
                    if len(niveis) >= 20:
                        limiar = max(250.0, float(np.percentile(niveis, 80)) * 3.0) * sens
                    pre.append(bloco); pre = pre[-int(_PRE / dur):]
                    if nivel > limiar:
                        gravando, partes, silencio, inicio = True, list(pre), 0.0, time.monotonic()
                    continue
                partes.append(bloco)
                silencio = 0.0 if nivel > limiar * 0.7 else silencio + dur
                if silencio >= _SILENCIO_FIM or time.monotonic() - inicio > _FALA_MAX:
                    audio = np.concatenate(partes).astype(np.float32) / 32768.0
                    gravando, pre, partes = False, [], []
                    if audio.size / _TAXA_MIC >= _FALA_MIN:
                        self._last_user_speech = time.monotonic()
                        fila = self._proprio_fila
                        if fila is not None:
                            loop.call_soon_threadsafe(fila.put_nowait, ("voz", audio))

    # ── falar ──────────────────────────────────────────────────────────────
    async def _proprio_falar(self, texto: str, idioma: str | None = None) -> None:
        from core import voz_propria as V
        voz, tocador = getattr(self, "_proprio_voz", None), self._proprio_tocador
        limpo = V.falavel(texto)
        if not limpo or voz is None or tocador is None:
            return
        if self._ditado.ativo:
            return
        idioma = idioma or self._idioma_da_resposta()
        tocador.novo_turno()
        self.set_speaking(True)
        try:
            def _tocar():
                # 2.4.5 — a síntese da frase seguinte roda ENQUANTO a anterior toca (antes era
                # uma depois da outra: cada frase abria uma pausa do tamanho da sua síntese).
                fila: queue.Queue = queue.Queue(maxsize=3)
                parar = threading.Event()

                def _enviar(item) -> bool:
                    while not parar.is_set():
                        try:
                            fila.put(item, timeout=0.2)
                            return True
                        except queue.Full:
                            pass
                    return False

                def _produzir():
                    try:
                        for frase in V.frases(limpo):
                            for pcm in voz.sintetizar(frase, idioma):
                                if tocador.interrompido or not _enviar(pcm):
                                    return
                    except Exception as e:           # a falha chega ao consumidor
                        _enviar(e)
                        return
                    _enviar(None)                    # fim

                produtor = threading.Thread(target=_produzir, daemon=True, name="nexus-tts-sintese")
                produtor.start()
                try:
                    while True:
                        item = fila.get()
                        if item is None:
                            return
                        if isinstance(item, Exception):
                            raise item
                        if not tocador.tocar(item):
                            return
                finally:
                    parar.set()
            await asyncio.to_thread(_tocar)
        except Exception as e:
            self.ui.write_log(f"SYS: A voz falhou ({str(e)[:120]}).")
        finally:
            self.set_speaking(False)
            self.ui.set_audio_level(0.0)

    def _idioma_da_resposta(self) -> str:
        """A voz segue o idioma: o forçado na configuração, ou o da última fala."""
        try:
            from memory.config_manager import get_language
            forcado = get_language()
            if forcado in ("pt", "en"):
                return forcado
        except Exception:
            pass
        return self._proprio_idioma or "pt"

    # ── um pedido ───────────────────────────────────────────────────────────
    def _proprio_sistema(self) -> str:
        try:
            si = self._build_config().system_instruction
            if hasattr(si, "parts"):
                si = "\n".join(getattr(p, "text", "") or "" for p in si.parts)
            sistema = str(si or "")
        except Exception:
            from .common import _load_system_prompt
            sistema = _load_system_prompt()
        from core.voz_propria import NOMES_IDIOMA
        idioma = self._idioma_da_resposta()
        return (sistema + "\n\n[MOTOR PRÓPRIO]\nYour reply is converted to speech by a TTS: plain "
                "sentences only — no markdown, no lists, no emoji, no URLs. Keep it short unless "
                "asked for detail. When you call a tool that takes a while, put one short sentence "
                "saying what you are doing in the same reply as the tool call. "
                f"The user is speaking {NOMES_IDIOMA.get(idioma, idioma)} ({idioma}); reply in "
                "that language unless [IDENTITY] forces another.\n"
                f"Current date and time: {data_hora(agora())}.")

    def _proprio_ferramentas(self, pedido: str) -> list:
        from core import llm_providers as L
        from .tool_declarations import TOOL_DECLARATIONS
        decls = (list(TOOL_DECLARATIONS) + self._action_registry.get_tool_declarations()
                 + self._plugin_registry.get_tool_declarations())
        modo = getattr(self, "_proprio_orcamento", "auto")
        cerebro = self._proprio_cerebro
        if modo == "sempre" or (modo == "auto" and cerebro.local):
            return L.orcamento_ferramentas(decls, pedido)
        return decls

    async def _proprio_turno(self, texto: str, origem: str, imagens=None) -> None:
        from core import llm_providers as L
        if origem == "voz":
            self.ui.write_log(f"You: {texto}")
            self._registrar_fala(texto)       # 2.4 — trava do desligar (o digitado já passou por typed.py)
        if origem in ("voz", "digitado"):
            self._session_log.append(f"User: {texto}")
            try:
                from core import isa as _isa
                _isa.registrar("entrada", texto, "você " + ("falou" if origem == "voz" else "digitou"),
                               origem="voz" if origem == "voz" else "texto")
            except Exception:
                pass
        if self._wake_enabled and not self._awake and origem != "app":
            return
        hist = self._proprio_hist
        hist.append({"role": "user", "content": texto, "images": imagens or []})
        cerebro = self._proprio_cerebro
        fala_pendente = None
        t0 = time.monotonic()
        primeira = True

        # 2.4.5 — o prompt (lê arquivos e a memória) e as declarações das ferramentas eram
        # refeitos a cada rodada do mesmo pedido; agora são montados uma vez por pedido.
        sistema = self._proprio_sistema()
        ferramentas = self._proprio_ferramentas(texto)

        # 2.4.6 — STREAMING: a voz começa na primeira frase, sem esperar o modelo terminar.
        from core import voz_propria as V
        voz, tocador = getattr(self, "_proprio_voz", None), self._proprio_tocador
        streaming = (bool(getattr(self, "_proprio_stream", False)) and voz is not None
                     and tocador is not None and hasattr(cerebro, "conversar_stream")
                     and not self._ditado.ativo)
        if streaming:
            tocador.novo_turno()
        fala_anterior = None

        for _ in range(_RODADAS):
            self.ui.set_state("THINKING")
            fala = None
            try:
                if streaming:
                    fala = V.FalaEmFluxo(
                        voz, tocador, self._idioma_da_resposta(),
                        ao_comecar=lambda: self.set_speaking(True),
                        ao_terminar=lambda: (self.set_speaking(False), self.ui.set_audio_level(0.0)),
                        ao_erro=lambda m: self.ui.write_log(f"SYS: {m}"),
                        depois_de=fala_anterior)
                    resp = await asyncio.to_thread(cerebro.conversar_stream, sistema,
                                                   L.janela_historico(hist, 30), ferramentas,
                                                   fala.alimentar)
                    fala.fechar()
                else:
                    resp = await asyncio.to_thread(cerebro.conversar, sistema,
                                                   L.janela_historico(hist, 30), ferramentas)
            except Exception as e:
                if fala is not None:
                    fala.cancelar()
                if hist and hist[-1].get("images"):
                    # modelo sem visão: tenta de novo sem a imagem
                    hist[-1]["images"] = []
                    hist[-1]["content"] += "\n[the image could not be sent: this model has no vision]"
                    continue
                self.ui.write_log(f"ERR: {cerebro.descricao()} — {str(e)[:200]}")
                await self._proprio_falar("Não consegui falar com o modelo agora."
                                          if self._idioma_da_resposta() == "pt"
                                          else "I could not reach the model right now.")
                if hist and hist[-1].get("role") == "user":
                    hist.pop()
                return
            if primeira:
                primeira = False
                try:
                    from core import isa as _isa
                    _isa.registrar_latencia((time.monotonic() - t0) * 1000)
                except Exception:
                    pass
            hist.append({"role": "assistant", "content": resp.texto, "tool_calls": resp.chamadas})

            if not resp.chamadas:
                if fala_pendente is not None:
                    await fala_pendente
                if resp.texto:
                    self.ui.write_log(f"{self._asst_name}: {resp.texto}")
                    self._session_log.append(f"{self._asst_name}: {resp.texto}")
                    try:
                        from core import isa as _isa
                        _isa.registrar("resposta", resp.texto, origem="motor próprio")
                    except Exception:
                        pass
                    if fala is not None and fala.enfileirou:
                        await asyncio.to_thread(fala.esperar)     # já falou em fluxo
                    else:
                        await self._proprio_falar(resp.texto)
                return

            # ⚡ fala enquanto a ferramenta roda: a frase do modelo, ou uma curta daqui
            if fala_pendente is not None:
                await fala_pendente
            frase = resp.texto
            if frase:
                self.ui.write_log(f"{self._asst_name}: {frase}")
            elif any(c["name"] not in _RAPIDAS for c in resp.chamadas):
                lenta = next(c["name"] for c in resp.chamadas if c["name"] not in _RAPIDAS)
                frase = _ja_vou(lenta, self._idioma_da_resposta())
            if fala is not None and fala.enfileirou:
                # a frase do modelo já está sendo falada em fluxo, enquanto a ferramenta roda
                fala_anterior = fala
                fala_pendente = asyncio.create_task(asyncio.to_thread(fala.esperar))
            else:
                fala_pendente = asyncio.create_task(self._proprio_falar(frase)) if frase else None

            for c in resp.chamadas:
                fc = _pytypes.SimpleNamespace(name=c["name"], args=c.get("args") or {}, id=c["id"])
                try:
                    r = await self._execute_tool(fc)
                    dados = getattr(r, "response", None) or {}
                    saida = dados.get("result") if isinstance(dados, dict) else dados
                    status = dados.get("status") if isinstance(dados, dict) else None
                except Exception as e:
                    saida, status = f"Tool '{c['name']}' failed: {e}", "failed"
                conteudo = str(saida)[:6000]
                if status:
                    conteudo = f"[status: {status}] {conteudo}"
                hist.append({"role": "tool", "tool_call_id": c["id"], "name": c["name"],
                             "content": conteudo})

            # a visão: a imagem capturada vai junto, como no Gemini Live
            pv = self._pending_vision
            if pv:
                self._pending_vision = None
                img_b, mime, pergunta, angulo = pv
                fonte = "[IMAGE SOURCE: WEBCAM]" if angulo == "camera" else "[IMAGE SOURCE: SCREEN CAPTURE]"
                hist.append({"role": "user", "content": f"{fonte}\n\n{pergunta}",
                             "images": [(mime, base64.b64encode(img_b).decode("ascii"))]})
                self._vision_busy = False
                if self._vision_cam_active:
                    self._vision_cam_active = False

                    async def _fechar_cam():
                        await asyncio.sleep(4.0)
                        self.ui.stop_camera_stream()
                    asyncio.create_task(_fechar_cam())

        if fala_pendente is not None:
            await fala_pendente
        await self._proprio_falar("Não consegui terminar: foram passos demais."
                                  if self._idioma_da_resposta() == "pt"
                                  else "I could not finish: too many steps.")
