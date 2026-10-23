"""Proteção contra fechamento sozinho — NEXUS Pro 2.3.

Por que o NEXUS fechava sozinho: no PyQt6, um erro Python que escapa de um botão, timer ou sinal da
janela derruba o programa inteiro (o Qt chama abort) — sem janela de erro e sem rastro. O mesmo vale
para erros em threads de fundo e para quedas nativas (microfone, GPU, DLL).

O que isto faz:
  • sys.excepthook / threading.excepthook / unraisablehook: o erro é GRAVADO em memory/falhas.log e o
    NEXUS continua aberto (só o botão ou a tarefa que falhou é perdido);
  • faulthandler: se houver queda nativa, grava a pilha em memory/queda_nativa.log;
  • marca de "fechou direito": memory/sessao.json guarda se a última vez foi um fechamento normal. Se
    não foi, o NEXUS avisa no log ("fechei de forma inesperada da última vez, veja falhas.log").
"""
from __future__ import annotations

import faulthandler
import json
import sys
import threading
import time
import traceback
from pathlib import Path

PASTA = Path(__file__).resolve().parent.parent / "memory"
ARQ_FALHAS = PASTA / "falhas.log"
ARQ_QUEDA = PASTA / "queda_nativa.log"
ARQ_SESSAO = PASTA / "sessao.json"
MAX_BYTES = 200_000

_instalada = False
_arq_queda = None
_vistos: dict[str, float] = {}


def _agora() -> str:
    return time.strftime("%d/%m/%Y %H:%M:%S")


def registrar_falha(origem: str, texto: str) -> None:
    """Grava uma falha (sem repetir a mesma mais de uma vez por 5 s) e aparara o arquivo."""
    try:
        chave = texto.strip().splitlines()[-1][:200] if texto.strip() else origem
        t = time.monotonic()
        if t - _vistos.get(chave, -99) < 5:
            return
        _vistos[chave] = t
        PASTA.mkdir(parents=True, exist_ok=True)
        antigo = ""
        if ARQ_FALHAS.exists():
            antigo = ARQ_FALHAS.read_text(encoding="utf-8", errors="replace")[-MAX_BYTES:]
        ARQ_FALHAS.write_text(antigo + f"\n=== {_agora()} · {origem} ===\n{texto}\n", encoding="utf-8")
    except Exception:
        pass


def anotar(origem: str) -> None:
    """Chame dentro de um ``except``: grava o erro atual em falhas.log e deixa o programa seguir.

    Para os lugares que antes faziam ``except: pass`` — o erro continua não derrubando
    nada, mas agora fica um rastro do porquê a função "não fez nada" (2.4.1).
    """
    registrar_falha(origem, traceback.format_exc())


def _hook(tipo, valor, tb):
    if issubclass(tipo, (KeyboardInterrupt, SystemExit)):
        sys.__excepthook__(tipo, valor, tb)
        return
    texto = "".join(traceback.format_exception(tipo, valor, tb))
    registrar_falha("erro na janela/programa", texto)
    try:
        print(f"[NEXUS] erro contido (o programa continua aberto): {valor!r}")
    except Exception:
        pass


def _hook_thread(args):
    if args.exc_type is SystemExit:
        return
    texto = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
    nome = getattr(args.thread, "name", "?")
    registrar_falha(f"erro na tarefa de fundo '{nome}'", texto)


def _hook_unraisable(args):
    registrar_falha("erro ignorado pelo Python",
                    f"{args.err_msg}: {args.exc_value!r}\n"
                    + "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))


def instalar() -> None:
    """Chame UMA vez, no começo do programa."""
    global _instalada, _arq_queda
    if _instalada:
        return
    _instalada = True
    sys.excepthook = _hook
    threading.excepthook = _hook_thread
    sys.unraisablehook = _hook_unraisable
    try:
        PASTA.mkdir(parents=True, exist_ok=True)
        if ARQ_QUEDA.exists() and ARQ_QUEDA.stat().st_size > MAX_BYTES:
            ARQ_QUEDA.unlink()
        _arq_queda = open(ARQ_QUEDA, "a", buffering=1, encoding="utf-8")
        _arq_queda.write(f"\n--- início {_agora()} ---\n")
        faulthandler.enable(file=_arq_queda, all_threads=True)
    except Exception:
        pass


# ── uma cópia só (2.4) ───────────────────────────────────────────────────────
# Abrir o NEXUS de novo (atalho novo, duplo clique duas vezes) rodava DUAS cópias:
# as duas ouviam o microfone, disputavam a porta do celular e a CPU, respondiam em
# dobro — e uma acabava derrubando a outra. Agora a segunda só traz a primeira
# para a frente e sai.
_mutex = None
_NOME_MUTEX = "Local\\NEXUS_Pro_uma_copia_so"
_TITULO = "desenvolvido por André Luiz Lima Menezes"   # parte do título da janela principal


def ja_esta_aberto(esperar_s: float = 0.0) -> bool:
    """True se outra cópia do NEXUS já está rodando neste usuário (só Windows).

    esperar_s: num reinício (atualização), a cópia antiga ainda está saindo — espera
    até esse tempo por ela antes de desistir."""
    global _mutex
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        k32.CreateMutexW.restype = ctypes.c_void_p
        k32.CloseHandle.argtypes = [ctypes.c_void_p]
        limite = time.monotonic() + max(0.0, esperar_s)
        while True:
            _mutex = k32.CreateMutexW(None, False, _NOME_MUTEX)
            if not _mutex or k32.GetLastError() != 183:          # ERROR_ALREADY_EXISTS
                return False
            if time.monotonic() >= limite:
                return True
            k32.CloseHandle(_mutex)
            _mutex = None
            time.sleep(0.5)
    except Exception:
        return False


def trazer_copia_aberta() -> bool:
    """Traz a janela da cópia que já está aberta para a frente."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        u32 = ctypes.windll.user32
        achou = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def _cada(hwnd, _):
            n = u32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                u32.GetWindowTextW(hwnd, buf, n + 1)
                if _TITULO in buf.value:
                    achou.append(hwnd)
                    return False
            return True
        u32.EnumWindows(_cada, 0)
        if not achou:
            return False
        u32.ShowWindow(achou[0], 9)            # SW_RESTORE (se estava minimizada)
        u32.SetForegroundWindow(achou[0])
        return True
    except Exception:
        return False


# ── marca de fechamento normal ───────────────────────────────────────────────
def _ler_sessao() -> dict:
    try:
        d = json.loads(ARQ_SESSAO.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def abrir_sessao() -> str | None:
    """Marca "aberto". Devolve um aviso se a vez anterior NÃO terminou com fechamento normal."""
    antes = _ler_sessao()
    aviso = None
    if antes.get("aberto"):
        aviso = ("O NEXUS tinha fechado de forma inesperada na vez anterior"
                 + (f" (aberto desde {antes.get('desde')})" if antes.get("desde") else "")
                 + ". O motivo, se foi registrado, está em memory/falhas.log e memory/queda_nativa.log.")
    try:
        PASTA.mkdir(parents=True, exist_ok=True)
        ARQ_SESSAO.write_text(json.dumps({"aberto": True, "desde": _agora()}), encoding="utf-8")
    except Exception:
        pass
    return aviso


def fechar_sessao() -> None:
    try:
        ARQ_SESSAO.write_text(json.dumps({"aberto": False, "fechou": _agora()}), encoding="utf-8")
    except Exception:
        pass


def relatorio(linhas: int = 25) -> str:
    """Resumo para a função de diagnóstico."""
    partes = []
    s = _ler_sessao()
    if s.get("aberto"):
        partes.append(f"Sessão atual aberta desde {s.get('desde')}.")
    try:
        txt = ARQ_FALHAS.read_text(encoding="utf-8", errors="replace").strip()
        n = txt.count("=== ")
        ult = "\n".join(txt.splitlines()[-linhas:])
        partes.append(f"{n} falha(s) contida(s) registradas. Últimas linhas:\n{ult}")
    except Exception:
        partes.append("Nenhuma falha contida registrada.")
    try:
        q = ARQ_QUEDA.read_text(encoding="utf-8", errors="replace")
        if "Fatal" in q or "Windows fatal" in q or "Current thread" in q:
            partes.append("Há registro de queda nativa em memory/queda_nativa.log.")
    except Exception:
        pass
    return "\n".join(partes)
