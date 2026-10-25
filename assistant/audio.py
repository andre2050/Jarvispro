"""Microphone in, speaker out, interruptions and vision frames.

Mixin of NexusLive (assistant/core.py); methods moved verbatim from main.py."""
from __future__ import annotations

from .common import CHANNELS, CHUNK_SIZE, RECEIVE_SAMPLE_RATE, SEND_SAMPLE_RATE, _CURSOR_SLACK, _FIRST_SOUND, _REPEAT_MIN, _TAIL_MARGIN, _VIS_HOP, _clean_transcript, _is_repeat_chunk, _pcm_frames, _pcm_level, agora, asyncio, audio_devices, get_input_device, get_output_device, np, sd, time, traceback, types  # noqa: F401


# 1.4 — ferramentas que podem rodar juntas quando o Gemini pede várias de uma
# vez: não mexem no teclado/mouse e não gravam no mesmo arquivo.
_PARALELAS = frozenset({"open_app", "web_search", "weather_report", "recall_memory",
                        "system_status", "unit_converter", "isa_core", "explicar_ia"})


import re as _re

_VAZOU = _re.compile(r"^(?:function|function_call|tool_code|tool_call)\b[\s:]*", _re.IGNORECASE)


def _strip_leaked_token(txt: str) -> str:
    """'function Aqui estão…' → 'Aqui estão…'. Só mexe quando sobra texto de
    verdade depois (uma fala em inglês que começa com 'Function…' fica)."""
    m = _VAZOU.match(txt or "")
    if not m:
        return txt
    resto = txt[m.end():]
    if not resto:
        return ""
    if txt[:1].islower() and resto[:1].isupper():
        return resto
    return txt


class AudioMixin:
    _fala_fim: float | None = None     # 1.4 — quando você parou de falar
    _respondendo = False               # 1.4 — o 1º áudio da resposta já chegou
    def _tail_active(self) -> bool:
        """True while the speakers may still be finishing our last sentence."""
        return time.monotonic() < self._tail_until

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self._tail_until = 0.0
        else:
            # Hold the guard open across the device's own output latency plus a
            # margin for the room. The microphone is NOT muted during it — the
            # guard still lets a genuine reply through, so answering instantly
            # still works. Only our own echo is dropped.
            self._tail_until = time.monotonic() + self._out_latency + _TAIL_MARGIN
        if not value:
            # The echo history is deliberately NOT cleared here: the tail above
            # still needs it to recognise our own voice. It is dropped when the
            # tail expires. What the guard learned about the room always stays.
            self._out_level = 0.0
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    def interrupt(self) -> None:
        """Stop NEXUS mid-speech: drain queued audio and open mic immediately."""
        try:   # 1.5 — motor próprio: corta a voz local
            self._proprio_parar_fala()
        except Exception:
            pass
        self._interrupted = getattr(self, "_motor_ativo", "gemini_live") != "proprio"
        q = self.audio_in_queue
        if q:
            drained = 0
            while True:
                try:
                    q.get_nowait()
                    drained += 1
                except Exception:
                    break
            if drained:
                print(f"[NEXUS] ✋ Interrupted — {drained} audio chunks discarded")
        self.set_speaking(False)
        self._play_cursor = 0.0     # next batch starts a fresh timeline
        if self._turn_done_event:
            self._turn_done_event.clear()
        self.ui.write_log("SYS: Interrompido — ouvindo…")

    def speak(self, text: str):
        # 1.5 — no motor próprio, o aviso vai para o modelo escolhido
        if getattr(self, "_motor_ativo", "gemini_live") == "proprio":
            if not self._ditado.ativo:
                self._proprio_submit(text, "app")
            return
        if not self._loop or not self.session:
            return
        # 1.4 — durante o ditado o NEXUS não fala: lembretes e avisos esperam o
        # ditado acabar (assistant/dictation.py). Os avisos do próprio ditado
        # vão por _avisar_ditado.
        if self._ditado.ativo:
            print(f"[Ditado] 🤫 fala adiada: {text[:60]}")
            fila = getattr(self, "_fala_adiada", None)
            if fila is not None and len(fila) < 5:
                fila.append(text)
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"role": "user", "parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def speak_error(self, tool_name: str, error: str, falar: bool = False):
        """1.4.3 — por padrão só registra. A falha já volta ao Gemini na
        resposta da ferramenta; mandar também um turno "[ERRO]" fazia o NEXUS
        responder DUAS vezes (e a segunda chegava atrasada)."""
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        if falar:
            self.speak(f"[ERRO] A função {tool_name} falhou: {short}. Avise o usuário em uma frase curta.")

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            # Gemini 3.x Live rejects the old realtime_input.media_chunks field
            # (what `media=...` maps to) and closes the socket with a 1007. Send
            # mic / phone PCM through the new `audio` field instead. Queue items
            # are {"data": <bytes>, "mime_type": <str>} from _listen_audio and
            # the phone relay.
            await self.session.send_realtime_input(
                audio=types.Blob(
                    data=msg["data"],
                    mime_type=msg.get("mime_type", "audio/pcm"),
                )
            )

    async def _listen_audio(self):
        print("[NEXUS] 🎤 Mic started")
        loop = asyncio.get_running_loop()

        def callback(indata, frames, time_info, status):
            # ── 2.3: cadastro da voz / da palavra "Nexus" ────────────────────
            # Enquanto o cadastro guiado está ativo, o áudio vai só para ele (nada sai do PC).
            try:
                from core import voz_id as _vid
                if _vid.captura.ativa:
                    _vid.captura.alimentar(indata)
                    return
            except Exception:
                pass
            # ── Wake-word gate ───────────────────────────────────────────────
            # While asleep, the mic audio NEVER goes to Gemini (nothing is
            # streamed, so NEXUS can't respond to speech not addressed to it and
            # nothing leaves the machine). Frames are instead handed to the local
            # detector, which runs its model in ITS OWN thread — the cost here is
            # only a queue push, so the audio path is never slowed. When wake word
            # is off (default) or we're awake, this is a single boolean check.
            if self._wake_enabled and not self._awake:
                det = self._wake_detector
                if det is not None:
                    det.feed(indata)
                return
            with self._speaking_lock:
                jarvis_speaking = self._is_speaking

            # ── Barge-in ─────────────────────────────────────────────────────
            # While NEXUS talks the mic is not streamed, but it is still worth
            # listening to locally: if the user starts speaking, cut the answer
            # short the way a person would stop when interrupted.
            #
            # The whole difficulty is echo — on speakers the mic hears NEXUS.
            # So the test is not "is the mic loud" but "is the mic louder than
            # the echo of what we are playing right now", sustained long enough
            # that a cough or a keystroke cannot trigger it.
            if jarvis_speaking:
                # Nothing is streamed while NEXUS talks.
                #
                # Interrupting by voice used to live here: `EchoGuard` can pick a
                # user out from under our own echo, and `core/echo.py` still does
                # that for the tail below. Re-enabling is small — classify each
                # block here and call interrupt() after `required_blocks` of
                # agreement — but it depends on the listener's room, so it stays
                # out until it can be tried on real hardware.
                return

            # ── Echo tail ────────────────────────────────────────────────────
            # The speaking flag has dropped but the speakers have not finished.
            # Sending this to the model is how an assistant hears itself, decides
            # it was addressed, and answers its own last sentence. The microphone
            # stays OPEN — the guard only drops blocks that are our own voice, so
            # replying the instant it stops still works.
            if self._tail_active():
                try:
                    if not self._echo.is_user_speech(
                            indata, SEND_SAMPLE_RATE, _pcm_level(indata)):
                        return
                    self._tail_until = 0.0      # a real voice ends the tail early
                except Exception:
                    return
            elif self._echo._hist:
                self._echo.reset()

            # ── Push-to-talk ─────────────────────────────────────────────────
            # When it is on the microphone is closed by default and the chord
            # opens it, which is the whole point: nothing leaves the machine
            # unless you are holding the key.
            if self._ptt_enabled and not self._ptt_held:
                return
            
            if not self.ui.muted and not self._phone_active:
                data = indata.tobytes()
                try:                                    # 2.3: guarda os últimos segundos p/ a trava de voz
                    from core import voz_id as _vid
                    _vid.anel.adicionar(indata)
                except Exception:
                    pass
                loop.call_soon_threadsafe(
                    self.out_queue.put_nowait,
                    {"data": data, "mime_type": "audio/pcm"}
                )
                # Feed the live mic level to the HUD so the waveform reacts to
                # the user's actual voice while listening. Purely cosmetic — any
                # failure here must never disturb the mic.
                try:
                    self.ui.set_audio_level(_pcm_level(indata))
                except Exception:
                    pass

        try:
            def _open_mic(dev):
                return sd.InputStream(
                    samplerate=SEND_SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype="int16",
                    blocksize=CHUNK_SIZE,
                    device=dev,
                    callback=callback,
                )

            # Which microphone. resolve() returns None for "system default" and
            # for a saved device that is no longer present — so a headset
            # unplugged since the last run falls back to the built-in mic
            # instead of raising on startup and taking the session with it.
            _mic_name = get_input_device()
            _mic_dev  = audio_devices.resolve(_mic_name, "input")
            if _mic_dev is not None:
                print(f"[NEXUS] 🎤 Input device: {_mic_name}")
            try:
                _mic_stream = _open_mic(_mic_dev)
            except Exception as _e:
                # A device the picker listed but the driver will not open right
                # now — exclusive mode, a webcam already in use, a virtual mic
                # whose source went away. Chosen hardware failing must never
                # mean the assistant cannot hear at all.
                if _mic_dev is None:
                    raise
                print(f"[NEXUS] ⚠️  Mic '{_mic_name}' failed: {_e} — using default")
                self.ui.write_log(
                    f"SYS: O microfone '{_mic_name}' não está disponível — usando o padrão do sistema."
                )
                _mic_stream = _open_mic(None)

            with _mic_stream:
                print("[NEXUS] 🎤 Mic stream open")
                while True:
                    await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[NEXUS] ❌ Mic: {e}")
            raise

    async def _flush_pending_vision(self) -> bool:
        """Send a captured frame immediately after its tool response.

        The frame is already in hand by the time `screen_process` returns — the
        capture happened inside the tool call. The old flow still made the model
        speak a turn first and only injected the image on that turn's
        turn_complete, which cost a whole extra round trip AND produced two
        spoken answers: one improvised without the picture, then the real one.
        Sending it here means the model has the tool result and the image before
        it generates anything, so the user gets one answer, sooner.
        """
        if not (self._pending_vision and self.session):
            return False

        import base64 as _b64
        img_b, mime_t, question, angle = self._pending_vision
        self._pending_vision = None
        b64 = _b64.b64encode(img_b).decode("ascii")
        print(f"[Vision] 📤 {len(img_b):,} bytes (angle={angle}) → main session")

        # Label the source. Without it the image arrives carrying nothing but
        # the user's own sentence, and a screenshot of this app — which has a
        # face in the middle of it — got read as a photo of the user. What the
        # label *means* is explained once, in the generated [SELF] block.
        src = ("[IMAGE SOURCE: WEBCAM]" if angle == "camera"
               else "[IMAGE SOURCE: SCREEN CAPTURE]")
        await self.session.send_client_content(
            turns={"role": "user", "parts": [
                {"inline_data": {"mime_type": mime_t, "data": b64}},
                {"text": f"{src}\n\n{question}"},
            ]},
            turn_complete=True,
        )

        if self._vision_cam_active:
            # Camera: stay busy until NEXUS has finished speaking the answer,
            # then close the preview.
            self._vision_cam_active    = False
            self._vision_close_pending = True
        else:
            self._vision_busy = False
        return True

    @property
    def _ditado(self):
        from core.bloco_de_notas import ditado
        return ditado

    async def _receive_audio(self):
        print("[NEXUS] 👂 Recv started")
        out_buf, in_buf = [], []
        ditado = self._ditado

        try:
            while True:
                async for response in self.session.receive():

                    # ── Session resumption ───────────────────────────────────
                    # The server sends this periodically. `resumable` goes false
                    # while a turn is mid-flight — replaying a handle from that
                    # moment is what the flag exists to prevent — so only
                    # resumable handles are kept. This is three lines and it is
                    # the entire fix for "every reconnect forgets everything".
                    _sru = getattr(response, "session_resumption_update", None)
                    if _sru is not None:
                        if getattr(_sru, "resumable", False) and getattr(_sru, "new_handle", None):
                            if self._resume_handle is None:
                                print("[NEXUS] 🔗 Session resumption armed")
                            self._resume_handle = _sru.new_handle

                    # 1.4.3 — o servidor avisa que vai fechar a conexão: renovar
                    # num momento calmo (session.py › _watch_connection).
                    _ga = getattr(response, "go_away", None)
                    if _ga is not None:
                        self._on_go_away(_ga)

                    # 1.4.3 — chegou resposta: o pedido digitado não travou
                    if self._aguardando_desde is not None and (
                            response.data or response.tool_call or (
                                response.server_content is not None and (
                                    response.server_content.turn_complete
                                    or response.server_content.output_transcription
                                    or response.server_content.model_turn))):
                        self._aguardando_desde = None
                        self._pendente_digitado = None

                    # 1.4 — modo ditado: o NEXUS fica calado (a não ser o
                    # "pode falar" logo depois de ligar por voz).
                    _calado = ditado.ativo and not ditado.pode_falar()

                    if response.data:
                        if self._interrupted or _calado:
                            pass  # discard: interrupted / dictating
                        else:
                            # 1.4 — tempo de resposta: fim da sua fala → 1º áudio
                            if not self._respondendo:
                                self._respondendo = True
                                if self._fala_fim is not None:
                                    try:
                                        from core import isa as _isa
                                        _isa.registrar_latencia(
                                            (time.monotonic() - self._fala_fim) * 1000)
                                    except Exception:
                                        pass
                                    self._fala_fim = None
                            if self._turn_done_event and self._turn_done_event.is_set():
                                self._turn_done_event.clear()
                            # Split into ~50 ms chunks so interrupt() stops audio within 50 ms
                            # (24000 Hz × 2 bytes/sample × 0.05 s = 2400 bytes per slice)
                            _audio_data = response.data
                            _SLICE = 2400
                            for _i in range(0, len(_audio_data), _SLICE):
                                self.audio_in_queue.put_nowait(_audio_data[_i : _i + _SLICE])

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text and not _calado:
                            txt = _clean_transcript(sc.output_transcription.text)
                            # 1.4.3 — às vezes o nome interno "function" vaza no
                            # começo da fala ("function Aqui estão suas notas").
                            if not out_buf:
                                txt = _strip_leaked_token(txt)
                            # A turn that involves a tool call passes through
                            # several turn_completes, and the API re-sends the
                            # tail of the transcript across them. Comparing only
                            # against the previous chunk missed that — once
                            # out_buf had been flushed and emptied, the repeat
                            # sailed straight back in, which logged the answer
                            # twice AND made the avatar mouth it twice.
                            if txt and not _is_repeat_chunk(txt, out_buf):
                                out_buf.append(txt)
                                # Hand the words to the mouth as they arrive, so
                                # the avatar can form the consonants the audio
                                # alone cannot show. Pure string work — it adds
                                # nothing measurable to the response path.

                        if sc.input_transcription and sc.input_transcription.text:
                            if ditado.ativo and not ditado.pode_falar():
                                # a fala vai direto para o Bloco de Notas
                                ditado.receber_trecho(sc.input_transcription.text)
                                self._last_user_speech = time.monotonic()
                            else:
                                txt = _clean_transcript(sc.input_transcription.text)
                                if txt:
                                    in_buf.append(txt)
                                    self._last_user_speech = time.monotonic()
                                    self._registrar_fala(txt)   # 2.4 — trava do desligar
                                    if not self._respondendo:
                                        self._fala_fim = self._last_user_speech

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()
                            self._respondendo = False

                            # If this turn_complete ends an interrupted response, clear the
                            # flag and skip all further processing for that turn.
                            if self._interrupted:
                                self._interrupted = False
                                in_buf  = []
                                out_buf = []
                                continue

                            # 1.4 — ditado: o turno do Gemini não vai para a
                            # conversa; o trecho que faltava entra no Bloco de Notas.
                            if ditado.ativo:
                                if ditado.pode_falar():
                                    ditado.fim_da_confirmacao()   # disse "pode falar": agora é ditado
                                else:
                                    ditado.finalizar_turno()
                                    in_buf, out_buf = [], []
                                    continue

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self._last_out_logged = ""   # new exchange
                                self.ui.write_log(f"You: {full_in}")
                                self._session_log.append(f"User: {full_in}")
                                try:
                                    from core import isa as _isa
                                    _isa.registrar("entrada", full_in, "você falou", origem="voz")
                                except Exception:
                                    pass
                                if self._dashboard:
                                    asyncio.create_task(self._dashboard.broadcast({
                                        "type": "log", "speaker": "user",
                                        "text": full_in,
                                        "ts": agora().isoformat(),
                                    }))
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            # Second line of defence: even if a repeat slips
                            # into a *fresh* buffer after a flush, never log the
                            # same answer (or a tail of it) twice in a row.
                            if full_out and len(full_out) >= _REPEAT_MIN and self._last_out_logged:
                                if full_out in self._last_out_logged:
                                    full_out = ""
                            if full_out:
                                self._last_out_logged = full_out
                                self.ui.write_log(f"{self._asst_name}: {full_out}")
                                self._session_log.append(f"{self._asst_name}: {full_out}")
                                try:
                                    from core import isa as _isa
                                    _isa.registrar("resposta", full_out, origem="gemini")
                                except Exception:
                                    pass
                                if self._dashboard:
                                    asyncio.create_task(self._dashboard.broadcast({
                                        "type": "log", "speaker": "jarvis",
                                        "text": full_out,
                                        "ts": agora().isoformat(),
                                    }))
                            out_buf = []

                            if self._vision_close_pending:
                                # This turn_complete IS the vision answer — close camera + release busy flag
                                self._vision_close_pending = False
                                self._vision_busy = False
                                async def _cam_close():
                                    await asyncio.sleep(2.0)
                                    self.ui.stop_camera_stream()
                                asyncio.create_task(_cam_close())

                    if response.tool_call:
                        calls = list(response.tool_call.function_calls or [])
                        for fc in calls:
                            print(f"[NEXUS] 📞 {fc.name}")
                        # 1.4 — várias ferramentas independentes no mesmo pedido
                        # ("abre o Spotify e o Chrome") rodam ao mesmo tempo.
                        self._tools_running += 1
                        try:
                            if len(calls) > 1 and all(fc.name in _PARALELAS for fc in calls):
                                fn_responses = list(await asyncio.gather(
                                    *(self._execute_tool(fc) for fc in calls)))
                            else:
                                fn_responses = []
                                for fc in calls:
                                    fn_responses.append(await self._execute_tool(fc))
                            await self.session.send_tool_response(
                                function_responses=fn_responses
                            )
                        finally:
                            self._tools_running = max(0, self._tools_running - 1)
                        await self._flush_pending_vision()
        except Exception as e:
            print(f"[NEXUS] ❌ Recv: {e}")
            traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[NEXUS] 🔊 Play started")

        _spk_name = get_output_device()
        _spk_dev  = audio_devices.resolve(_spk_name, "output")
        if _spk_dev is not None:
            print(f"[NEXUS] 🔊 Output device: {_spk_name}")

        def _open_spk(dev):
            st = sd.RawOutputStream(
                samplerate=RECEIVE_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                device=dev,
            )
            st.start()
            return st

        try:
            stream = _open_spk(_spk_dev)
        except Exception as _e:
            # A chosen output that the host API accepts by name but refuses to
            # open (exclusive mode, wrong sample rate, device asleep) must not
            # cost the user their voice. Fall back to the default and say so.
            if _spk_dev is None:
                raise
            print(f"[NEXUS] ⚠️  Output device '{_spk_name}' failed: {_e} — using default")
            self.ui.write_log(f"SYS: O alto-falante '{_spk_name}' não está disponível — usando o padrão do sistema.")
            stream = _open_spk(None)

        # Ask the device how far behind the speakers actually are, rather than
        # assuming. This is what the echo tail is sized from, so a machine with a
        # large audio buffer gets a correspondingly longer guard — and one with a
        # tiny buffer is not penalised with a delay it does not need.
        try:
            lat = float(getattr(stream, "latency", 0.0) or 0.0)
            if 0.0 < lat < 1.0:
                self._out_latency = lat
            print(f"[NEXUS] 🔊 Output latency {self._out_latency*1000:.0f} ms "
                  f"→ echo tail {(self._out_latency + _TAIL_MARGIN)*1000:.0f} ms")
        except Exception:
            pass

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue

                self.set_speaking(True)

                # Batch all immediately-available chunks into one write to reduce
                # thread-pool round-trips (was one asyncio.to_thread per 50ms slice).
                # Cap at ~200 ms so interrupt() still stops audio within ~200 ms.
                batch = bytearray(chunk)
                while len(batch) < 9600:   # 9600 bytes ≈ 200 ms at 24 kHz / 16-bit mono
                    try:
                        batch.extend(self.audio_in_queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break

                # Drive the HUD waveform and the avatar's mouth from NEXUS's
                # own voice. The batch is up to 200 ms long, so we hand over a
                # *schedule* of 20 ms viseme frames instead of a single averaged
                # level and let the HUD play it out in step with the audio.
                try:
                    pcm = np.frombuffer(bytes(batch), dtype=np.int16)
                    hop = _VIS_HOP / RECEIVE_SAMPLE_RATE
                    frames = _pcm_frames(pcm, sr=RECEIVE_SAMPLE_RATE)
                    # When does this batch become audible? The stream was
                    # started at launch and its callback has been pulling
                    # silence ever since, so the first bytes of a reply reach
                    # the speaker about one callback period later — NOT one
                    # buffer later. `stream.latency` reports the buffer's
                    # capacity, which is how much can be queued ahead, and on
                    # Windows that is commonly 300-500 ms. Anchoring on it put
                    # the entire schedule a buffer late; that is the half second
                    # of lag, and it grew with whatever the device reported.
                    #
                    # After the anchor nothing needs measuring: the device
                    # consumes at exactly realtime, so each batch sounds one
                    # batch-duration after the one before it. The cursor is
                    # re-anchored only when it leaves the range physically
                    # possible — behind `now` means the device drained and this
                    # batch starts a fresh stretch of speech, while further
                    # ahead than the buffer can hold means it has drifted.
                    now = time.time()
                    horizon = self._out_latency + _CURSOR_SLACK
                    if not (now <= self._play_cursor <= now + horizon):
                        self._play_cursor = now + _FIRST_SOUND
                    at = self._play_cursor
                    # Advance by the batch's own duration whether or not it
                    # yielded frames, so a block too short to analyse cannot
                    # shift everything after it out of step with the audio.
                    self._play_cursor += pcm.size / RECEIVE_SAMPLE_RATE
                    if frames:
                        self.ui.push_visemes(frames, hop, at)
                        # Barge-in needs to know what we are playing, not just
                        # how loud: the guard subtracts this from the microphone.
                        self._out_level = max(f[0] for f in frames)
                        self._echo.note_output(pcm, RECEIVE_SAMPLE_RATE,
                                               self._out_level)
                    else:
                        lvl = _pcm_level(pcm)
                        self.ui.set_audio_level(lvl)
                        self._out_level = lvl
                        self._echo.note_output(pcm, RECEIVE_SAMPLE_RATE, lvl)
                except Exception:
                    pass

                try:
                    await asyncio.to_thread(stream.write, bytes(batch))
                except (RuntimeError, asyncio.CancelledError):
                    break   # executor shutting down — exit cleanly
        except Exception as e:
            print(f"[NEXUS] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()
