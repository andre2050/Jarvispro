"""Modo ditado (NEXUS Ultra 2026 1.4): a ponte entre a voz e o Bloco de Notas.

Mixin of NexusLive (assistant/core.py). A lógica do ditado em si fica em
core/bloco_de_notas.py; aqui só se liga o ditado ao Gemini e à janela:

  • o Gemini é avisado quando o ditado liga ou desliga pelo botão / atalho
  • enquanto dita, a voz do NEXUS não toca e ele não executa ferramentas
    (veja _receive_audio em audio.py e _execute_tool em tools.py)
"""
from __future__ import annotations

from .common import asyncio, threading


class DictationMixin:
    def _setup_dictation(self) -> None:
        try:
            from core.bloco_de_notas import ditado
        except Exception as e:
            print(f"[Ditado] ⚠️ indisponível: {e}")
            return
        self._fala_adiada: list[str] = []
        ditado.avisar_modelo = self._avisar_ditado
        ditado.log = self.ui.write_log
        ditado.ao_mudar.append(self._ditado_mudou)
        try:
            ditado.ao_mudar.append(self.ui.set_ditado)
            self.ui.on_toggle_ditado = self._alternar_ditado
        except Exception as e:
            print(f"[Ditado] ⚠️ sem indicador na tela: {e}")

    def _avisar_ditado(self, texto: str) -> None:
        """Manda um aviso interno ([DITADO LIGADO] / [DITADO TERMINADO]) ao Gemini."""
        if not self._loop or not self.session:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self.session.send_client_content(
                    turns={"role": "user", "parts": [{"text": texto}]},
                    turn_complete=True),
                self._loop)
        except Exception as e:
            print(f"[Ditado] ⚠️ não consegui avisar o Gemini: {e}")

    def _ditado_mudou(self, ligado: bool) -> None:
        """Ao terminar o ditado, o que o NEXUS deixou de falar (um lembrete que
        disparou no meio, por exemplo) é dito agora — depois da confirmação."""
        if ligado or not self._fala_adiada:
            return
        fila, self._fala_adiada = self._fala_adiada[:], []

        def _depois():
            for texto in fila:
                self.speak(texto)

        t = threading.Timer(6.0, _depois)
        t.daemon = True
        t.start()

    def _alternar_ditado(self) -> str:
        """Botão 🎙 Ditado da barra rápida / atalho Ctrl+D."""
        from core.bloco_de_notas import ditado
        if ditado.ativo:
            _ok, msg = ditado.parar(origem="botao")
        else:
            _ok, msg = ditado.iniciar(origem="botao")
        self.ui.write_log(f"SYS: 📝 {msg}")
        return msg
