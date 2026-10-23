"""Running the tools the model calls.

Mixin of NexusLive (assistant/core.py); methods moved verbatim from main.py."""
from __future__ import annotations

from .common import _P, _capture_camera, _capture_screen, add_monitor, asyncio, get_system_status, list_monitors, remove_monitor, search_memory, traceback, types, undo_stack, update_memory  # noqa: F401


# 1.4 — o registro de auditoria e o de hábitos gravam em disco; feitos aqui
# dentro do laço do Gemini, atrasavam a resposta da ferramenta (num HD lento ou
# numa pasta do OneDrive, dezenas de ms por chamada). Agora vão para uma fila
# própria, na ordem em que aconteceram.
import concurrent.futures as _cf
import time as _time

_gravador = _cf.ThreadPoolExecutor(max_workers=1, thread_name_prefix="nexus-registro")


def _gravar_anotando(fn, *args) -> None:
    # 2.4.1 — o executor guarda o erro no Future e ninguém olhava: uma falha ao
    # gravar hábitos ou auditoria sumia sem rastro. Agora vai para falhas.log.
    try:
        fn(*args)
    except Exception:
        from core import protecao as _prot
        _prot.anotar(f"gravação em segundo plano '{getattr(fn, '__qualname__', '?')}'")


def _em_segundo_plano(fn, *args) -> None:
    try:
        _gravador.submit(_gravar_anotando, fn, *args)
    except RuntimeError:          # o app está fechando: grava aqui mesmo
        _gravar_anotando(fn, *args)


import re as _re

# 2.4 — o que conta como "pediu para desligar o NEXUS" (pt e en)
_PEDIDO_DESLIGAR = _re.compile(
    r"\b(deslig\w*|encerr\w*|fecha(r)?( o| a)? (nexus|programa|assistente|app|aplicativo|voc[eê])"
    r"|sai(r)? do nexus|pode (sair|ir)|tchau|at[eé] (logo|mais|amanh[aã])|boa noite|dorme? de vez"
    r"|shut ?down|turn (yourself )?off|quit|exit|good ?bye|bye)\b",
    _re.IGNORECASE)
_JANELA_DESLIGAR_S = 20.0


class ToolsMixin:
    def _registrar_fala(self, texto: str) -> None:
        """Guarda as últimas falas/textos do usuário (para conferir pedidos perigosos)."""
        falas = getattr(self, "_falas_recentes", None)
        if falas is None:
            falas = self._falas_recentes = []
        falas.append((_time.monotonic(), str(texto or "")))
        del falas[:-12]

    def _pediu_para_desligar(self) -> bool:
        agora_ = _time.monotonic()
        recentes = " ".join(t for (q, t) in getattr(self, "_falas_recentes", []) or []
                            if agora_ - q <= _JANELA_DESLIGAR_S)
        return bool(_PEDIDO_DESLIGAR.search(recentes))

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})
        _t0 = _time.monotonic()       # 2.1 — quanto a função demora (vai para o audit.log)

        print(f"[NEXUS] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")
        try:
            self.ui.hud_modulo(name)                  # 2.3 — acende o módulo no visual Hub
        except Exception:
            pass
        self._learn_from_tool(name, args)

        # I.S.A. (1.3): toda função que o Gemini chama passa pelo núcleo de decisões
        from core import isa as _isa

        # 1.4 — modo ditado: tudo o que o usuário fala é texto para o Bloco de
        # Notas. Se o Gemini achar que uma frase ditada era um pedido ("abre o
        # Chrome"), nada é executado. Só a própria ferramenta do Bloco de Notas
        # passa (para ele poder encerrar o ditado).
        from core.bloco_de_notas import ditado as _ditado
        if _ditado.ativo and name != "notepad":
            print(f"[Ditado] 🚫 {name} ignorado — modo ditado ligado")
            _isa.registrar("decisao", f"Não executei {_isa.nome_da_funcao(name)}",
                           "o modo ditado está ligado: a fala é texto, não pedido", origem="ditado")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": ("DICTATION MODE: ignorado. O usuário está ditando um texto "
                                     "para o Bloco de Notas; nada foi executado. Fique em silêncio.")})

        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value and _P.get("save_memory_enabled"):
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
                _isa.registrar("memoria", f"Guardou na memória: {key.replace('_', ' ')}",
                               f"{category} · {str(value)[:80]}", origem="gemini")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        loop   = asyncio.get_running_loop()
        result = "Done."
        _isa_tok = _isa.iniciar_acao(name, args, origem="gemini")

        # 1.5 — ⚡ confirmação instantânea na tela: se a função passar de 1,5 s,
        # a conversa mostra na hora que ele está trabalhando nela (o Gemini 3.1
        # Live não fala enquanto uma função roda).
        def _avisar_trabalhando():
            try:
                self.ui.write_log(f"SYS: ⚙ {_isa.nome_da_funcao(name)} — trabalhando nisso…")
            except Exception:
                pass
        _aviso = loop.call_later(1.5, _avisar_trabalhando) if name not in (
            "screen_process", "close_camera", "recall_memory", "undo", "system_status") else None

        try:
            try:                                        # 2.3: trava de voz (desligada por padrão)
                from core import voz_id as _vid
                _bloqueio = _vid.verificar_dono(name, args)
            except Exception:
                _bloqueio = None
            if _bloqueio:
                result = _bloqueio

            elif name == "recall_memory":
                # Local file search: no network, no second model. Kept out of
                # the executor deliberately — it is a dictionary scan over a few
                # hundred short strings, and a thread hop would cost more than
                # the work itself.
                result = search_memory(args.get("query", ""), limit=8)

            elif name == "undo":
                if str(args.get("action", "")).lower().strip() == "list":
                    items = undo_stack.history()
                    result = ("Things I can undo, most recent first:\n"
                              + "\n".join(f"{i+1}. {t}" for i, t in enumerate(items))
                              ) if items else "I have not changed anything I can undo yet."
                else:
                    result = await loop.run_in_executor(None, undo_stack.undo_last)

            elif name == "screen_process" and _P.get("visao_somente_local"):
                # 1.4 — modo privado de visão: a imagem não sai do PC; o Gemini
                # recebe só o que a visão local viu (actions/local_vision.py).
                from actions.local_vision import resposta_privada
                self.ui.write_log("SYS: 🔒 Visão privada — analisando no seu PC, sem enviar a imagem.")
                result = await loop.run_in_executor(None, lambda: resposta_privada(args, self.ui))

            elif name == "screen_process":
                import time as _t_mod
                _now = _t_mod.monotonic()
                _cooldown = 4.0  # seconds — covers echo window after speaking ends
                if self._vision_busy or (_now - self._vision_last_time) < _cooldown:
                    _wait = max(0, _cooldown - (_now - self._vision_last_time))
                    print(f"[Vision] ⏳ Cooldown active ({_wait:.1f}s remaining) — ignoring duplicate call")
                    result = "Vision is still processing the previous request. I will not call this again."
                else:
                    self._vision_busy      = True
                    self._vision_last_time = _now
                    angle     = args.get("angle", "screen").lower()
                    user_text = args.get("text", "What do you see?")
                    if angle == "camera":
                        img_b, mime_t = await loop.run_in_executor(None, _capture_camera)
                        self.ui.start_camera_stream()
                        self._vision_cam_active = True
                        print(f"[Vision] 📷 Camera: {len(img_b):,} bytes")
                        _stall = "camera"
                    else:
                        img_b, mime_t = await loop.run_in_executor(None, _capture_screen)
                        print(f"[Vision] 🖥️  Screen: {len(img_b):,} bytes")
                        _stall = "screen"
                    self._pending_vision = (img_b, mime_t, user_text, angle)
                    # The image is attached to this same exchange, so there is
                    # nothing to stall for and nothing to announce. Asking for an
                    # acknowledgement here is what produced two spoken answers —
                    # the model filled that turn by answering the question from
                    # imagination, then answered it again once it could see.
                    result = (
                        f"[VISION_ACTIVE] {_stall.capitalize()} captured and attached to this "
                        f"same exchange. Do not acknowledge and do not answer yet — the image "
                        f"is arriving with this result. Reply once, from what you actually see "
                        f"in it."
                    )

            elif name == "close_camera":
                self.ui.stop_camera_stream()
                result = "Camera closed."

            elif name == "system_status":
                r = await loop.run_in_executor(None, get_system_status)
                result = str(r)

            elif name == "manage_monitor":
                action = args.get("action", "").lower().strip()
                topic  = args.get("topic", "").strip()
                if action == "add" and topic:
                    result = await asyncio.to_thread(add_monitor, topic)
                elif action == "remove" and topic:
                    result = await asyncio.to_thread(remove_monitor, topic)
                elif action == "list":
                    topics = await asyncio.to_thread(list_monitors)
                    result = ("Monitoring: " + ", ".join(topics)) if topics else "No topics are being monitored."
                else:
                    result = "Specify action (add/remove/list) and a topic."

            elif name == "shutdown_jarvis" and not self._pediu_para_desligar():
                # 2.4 — o NEXUS fechava sozinho: com barulho/TV o microfone virava frases
                # soltas ("Abuelo.", "botão, cara.") e o Gemini chamava esta função.
                # Agora só desliga se a última fala (ou texto) pediu isso de verdade.
                self.ui.write_log("SYS: Pedido de desligar ignorado — não ouvi você pedir para desligar.")
                result = ("NOT EXECUTED: the user did not clearly ask to shut down (their recent words "
                          "contain no shutdown request — it was probably background noise). Do NOT "
                          "shut down and do not call this again unless they explicitly ask. Continue "
                          "normally; say nothing about it.")

            elif name == "shutdown_jarvis":
                self.ui.write_log("SYS: Desligamento pedido.")
                async def _do_shutdown():
                    await self._save_session_summary()
                    if self.session:
                        try:
                            await self.session.send_client_content(
                                turns={"role": "user", "parts": [{"text": "Say a brief natural goodbye to the user."}]},
                                turn_complete=True,
                            )
                        except Exception:
                            pass
                    await asyncio.sleep(1.5)
                    # 2.4 — os._exit pulava a marca de "fechou direito": a próxima abertura
                    # dizia que o NEXUS tinha fechado de forma inesperada.
                    try:
                        from core import protecao as _prot
                        _prot.fechar_sessao()
                    except Exception:
                        pass
                    import os as _os
                    _os._exit(0)
                asyncio.create_task(_do_shutdown())

            elif self._action_registry.has(name):
                # file_processor: fall back to the currently-uploaded file when none is given
                if name == "file_processor" and not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                _ctx = {"player": self.ui, "speak": self.speak,
                        "response": None, "session_memory": None}
                r = await loop.run_in_executor(None, lambda: self._action_registry.run(name, args, _ctx))
                result = r or "Done."
                # Feed the habit log (core/habits.py) — routines 'suggest' learns
                # from it. It only keeps SAFE_TOOLS and never raises. Until now
                # nothing ever called it, so there was never anything to suggest.
                if not str(result).startswith(("Tool '", "Action '", "Failed", "Could not",
                                                "No application", "Unsupported")):
                    try:
                        from core import habits as _habits
                        _em_segundo_plano(_habits.record, name, dict(args))
                    except Exception:
                        from core import protecao as _prot
                        _prot.anotar("registro de hábitos")
                # web_search: mirror results to the on-screen content panel
                if (name == "web_search" and r
                        and not r.startswith("No results")
                        and not r.startswith("Search failed")):
                    _mode  = args.get("mode", "search")
                    _query = args.get("query") or ", ".join(args.get("items", []))
                    _label = f"{_mode.upper()} — {_query[:38]}" if _query else _mode.upper()
                    self.ui.show_content(_label, r)

            else:
                if self._plugin_registry.has(name):
                    r = await loop.run_in_executor(
                        None,
                        lambda: self._plugin_registry.run(name, args, player=self.ui, session_memory=None)
                    )
                    result = r or "Done."
                else:
                    result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)
            if name == "screen_process":
                # 1.4.3 — a captura falhou (câmera ocupada, índice errado…): sem
                # isto a visão ficava "ainda processando" até reconectar.
                self._vision_busy = False
                self._vision_cam_active = False
                self._pending_vision = None
                try:
                    self.ui.stop_camera_stream()
                except Exception:
                    pass

        if _aviso is not None:
            _aviso.cancel()
        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        # 1.5 — 🤝 diz o que verificou (done / unverified / failed) e 🛡️ o que
        # veio de fora (web, arquivo, tela, e-mail) vai embrulhado como dado.
        from core import verificacao as _ver
        _status, result = _ver.status_do_resultado(name, args, result)
        if _ver.precisa_embrulhar(name, args):
            result = _ver.embrulhar(name, result)

        _isa.concluir_acao(_isa_tok, result, ok=_status != "failed")
        print(f"[NEXUS] 📤 {name} [{_status}] → {str(result)[:80]}")
        from core.audit import record as _audit
        _em_segundo_plano(_audit, name, dict(args), f"[{_status}] {result}",
                          int((_time.monotonic() - _t0) * 1000))

        # A tool that declared itself NON_BLOCKING also says when its answer may
        # re-enter the conversation. Without this the model finishes whatever it
        # was saying and then reads the result out on top of it — which, for
        # something like a phone call already ringing, is exactly the noise the
        # non-blocking call was meant to avoid. Tools that declared nothing get
        # the API default and behave as they always have.
        _sched = (self._action_registry.scheduling(name)
                  or self._plugin_registry.scheduling(name))
        _extra = {"scheduling": _sched} if _sched else {}
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result, "status": _status},
            **_extra
        )
