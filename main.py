import platform as _platform
from core.pt_time import agora
import subprocess as _subprocess

# ── Nuclear: force CREATE_NO_WINDOW on EVERY subprocess call on Windows ───────
# This patches Popen itself, so no per-file flag is needed anywhere.
if _platform.system() == "Windows":
    _OrigPopen = _subprocess.Popen

    class _Popen(_OrigPopen):
        def __init__(self, args, **kw):
            kw["creationflags"] = kw.get("creationflags", 0) | _subprocess.CREATE_NO_WINDOW
            kw.pop("startupinfo", None)   # drop any stale/shared STARTUPINFO
            super().__init__(args, **kw)

    _subprocess.Popen = _Popen


# ── Console must survive non-UTF-8 code pages ────────────────────────────────
# Every status line in this file carries an emoji, and on a legacy Windows
# console the active code page is the system one — cp1254 in Turkey, cp1251 in
# Russia, cp932 in Japan. Printing an emoji there raises UnicodeEncodeError, and
# because most of these prints sit inside the receive loop it takes the session
# down on startup. Reconfiguring to UTF-8 with a replacement fallback costs
# nothing and makes the app launch the same way in every locale.
import sys as _sys

for _stream in ("stdout", "stderr"):
    try:
        _s = getattr(_sys, _stream, None)
        if _s is not None and hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        _s = None          # pythonw / redirected pipes / anything exotic — never fatal

# ─────────────────────────────────────────────────────────────────────────────

# Everything else lives in the assistant/ package (engine) and ui/ (window).
# 2.4 — o motor (assistant/: Gemini, numpy, áudio, OpenCV…) leva ~4 s para
# carregar e a janela só aparecia depois disso. Agora a janela abre primeiro
# (0,7 s) e o motor é importado na thread do runner, com a janela já na tela.
import asyncio
import threading
from core.protecao import engolida as _engolida
from ui import NexusUI  # noqa: F401


def _esperar_o_antigo_sair() -> bool:
    """1.4.1 — ao reiniciar depois de uma atualização, o NEXUS novo espera o
    antigo fechar de vez (microfone, porta do celular) antes de começar.
    2.4: devolve True quando é um reinício (a trava de cópia única espera mais)."""
    import os as _os
    pid = _os.environ.pop("NEXUS_ESPERAR_PID", "")
    if not pid.isdigit():
        return False
    try:
        import psutil
        psutil.Process(int(pid)).wait(timeout=15)
    except Exception:
        _engolida("main.py:59")
    return True


def _guardar_resumo_ao_fechar(jarvis) -> None:
    """1.4.3 — fechou a janela: guarda o resumo da conversa (para o "da última
    vez falamos de…" do dia seguinte). Antes ele só era gravado quando a
    conexão caía, e a conversa final de cada dia se perdia."""
    try:
        loop = getattr(jarvis, "_loop", None)
        if jarvis is None or loop is None or not loop.is_running():
            return
        if len(getattr(jarvis, "_session_log", []) or []) < 3:
            return
        asyncio.run_coroutine_threadsafe(jarvis._save_session_summary(), loop).result(timeout=8)
    except Exception as e:
        print(f"[NEXUS] resumo ao fechar não salvo: {e}")


def main():
    import traceback
    # 2.3 — erros que antes derrubavam o programa em silêncio agora são gravados e contidos
    from core import protecao
    protecao.instalar()
    try:
        from core import cofre as _cofre
        _cofre.sincronizar()     # 4.6.0 — segredo digitado fora do cofre vai para ele (só se o cofre estiver ligado)
    except Exception:
        protecao.anotar("sincronizar o cofre de chaves")
    reinicio = _esperar_o_antigo_sair()
    # 2.4 — uma cópia só: abrir de novo traz a janela que já está aberta
    if protecao.ja_esta_aberto(esperar_s=15 if reinicio else 0):
        if not protecao.trazer_copia_aberta():
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(
                    None, "O NEXUS já está aberto (veja a barra de tarefas ou a bandeja).",
                    "NEXUS Ultra 2026", 0x40)
            except Exception:
                _engolida("main.py:98")
        return
    aviso_queda = protecao.abrir_sessao()
    ui = NexusUI("face.png")
    caixa = {}
    if aviso_queda:
        try:
            ui.write_log("SYS: ⚠ " + aviso_queda)
        except Exception:
            _engolida("main.py:107")

    def runner():
        try:
            from assistant.core import NexusLive   # 2.4 — carrega com a janela já aberta
        except Exception:
            protecao.registrar_falha("o motor não carregou", traceback.format_exc())
            try:
                ui.write_log("ERR: O motor do NEXUS não carregou — veja memory/falhas.log "
                             "(rode 'Instalar o NEXUS (primeira vez).bat' se faltar pacote).")
            except Exception:
                _engolida("main.py:118")
            return
        ui.wait_for_api_key()
        jarvis = NexusLive(ui)
        caixa["jarvis"] = jarvis
        # 2.3 — se o motor cair por um erro inesperado, recomeça sozinho (até 5 vezes em 10 minutos)
        # em vez de deixar a janela aberta e muda.
        quedas: list[float] = []
        while True:
            try:
                asyncio.run(jarvis.run())
                return
            except KeyboardInterrupt:
                print("\n🔴 Shutting down...")
                return
            except Exception:
                import time as _t
                protecao.registrar_falha("o motor do assistente caiu", traceback.format_exc())
                agora_ = _t.monotonic()
                quedas[:] = [q for q in quedas if agora_ - q < 600] + [agora_]
                if len(quedas) > 5:
                    try:
                        ui.write_log("ERR: O motor caiu várias vezes seguidas — veja memory/falhas.log.")
                    except Exception:
                        _engolida("main.py:142")
                    return
                try:
                    ui.write_log("SYS: ⚠ O motor tropeçou e foi reiniciado sozinho.")
                except Exception:
                    _engolida("main.py:147")
                _t.sleep(1.5)
                velho, jarvis = jarvis, NexusLive(ui)
                try:   # 4.6.0 — o motor novo continua a conversa do que caiu (handle e falas só na memória)
                    from core.continuidade import herdar
                    if herdar(velho, jarvis)["handle"]:
                        ui.write_log("SYS: Retomando a conversa de onde parou.")
                except Exception:
                    protecao.anotar("continuidade ao reiniciar o motor")
                caixa["jarvis"] = jarvis

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()
    _guardar_resumo_ao_fechar(caixa.get("jarvis"))
    protecao.fechar_sessao()

def _registrar_erro_ao_abrir() -> None:
    """Se o NEXUS cair ao abrir, grava o motivo em erro_ao_abrir.txt (ao lado do
    main.py) e avisa na tela. Antes, com duplo clique, a janela de texto fechava
    sozinha e o erro se perdia."""
    import traceback as _tb
    texto = _tb.format_exc()
    try:
        from pathlib import Path as _P
        arq = _P(__file__).resolve().parent / "erro_ao_abrir.txt"
        arq.write_text(f"NEXUS — erro ao abrir ({agora().strftime('%d/%m/%Y %H:%M:%S')})\n\n{texto}",
                       encoding="utf-8")
        onde = str(arq)
    except Exception:
        onde = "(não consegui gravar o arquivo)"
    print(texto)
    try:
        if _platform.system() == "Windows":
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                None, "O NEXUS não conseguiu abrir.\n\nO motivo foi gravado em:\n" + onde +
                "\n\nMande esse arquivo para quem cuida do NEXUS.", "NEXUS Ultra 2026", 0x10)
    except Exception:
        _engolida("main.py:185")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except KeyboardInterrupt:
        pass
    except Exception:
        _registrar_erro_ao_abrir()
        raise SystemExit(1)