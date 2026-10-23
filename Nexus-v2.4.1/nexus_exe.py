"""Ponto de partida do Nexus.exe (NEXUS Pro — André Luiz Lima Menezes).

Como funciona
-------------
O Nexus.exe leva junto o Python e todas as bibliotecas. O código do NEXUS
continua nos arquivos .py ao lado dele (main.py, ui/, assistant/, actions/,
plugins/...), exatamente como quando você roda `python main.py`. Por isso:
  • plugins novos e atualizações do código funcionam sem gerar o .exe de novo;
  • a pasta memory/ e o config/ continuam no mesmo lugar.

O .exe também faz o papel de "python" quando o NEXUS precisa rodar um script
sozinho (os lembretes, por exemplo, chamam `Nexus.exe aviso.py` na hora
marcada): nesse caso ele roda o script e fecha, sem abrir a janela.

Gerar o .exe: dê dois cliques em gerar_exe.bat (veja o LEIA-ME).
"""
from __future__ import annotations

import os
import runpy
import sys
import traceback
from pathlib import Path

CONGELADO = bool(getattr(sys, "frozen", False))
PASTA = Path(sys.executable).resolve().parent if CONGELADO else Path(__file__).resolve().parent


def _saidas_padrao() -> None:
    """Num .exe sem console o Python começa sem stdout/stderr; scripts que
    escrevem na tela quebrariam. Usa a saída herdada se houver, senão o nada."""
    for fd, nome in ((1, "stdout"), (2, "stderr")):
        if getattr(sys, nome, None) is None:
            try:
                setattr(sys, nome, open(fd, "w", encoding="utf-8", errors="replace",
                                         buffering=1, closefd=False))
            except OSError:
                setattr(sys, nome, open(os.devnull, "w", encoding="utf-8"))


def _avisar(titulo: str, texto: str) -> None:
    try:
        if sys.platform.startswith("win"):
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, texto, titulo, 0x10)
            return
    except Exception:
        pass
    print(f"{titulo}: {texto}", file=sys.stderr)


def _como_python(args: list[str]) -> int | None:
    """Se o .exe foi chamado como um python (script.py, -m módulo, -c código),
    faz isso e devolve o código de saída. Senão devolve None (abre o NEXUS)."""
    if not args:
        return None
    primeiro = args[0]
    if primeiro == "-c" and len(args) >= 2:
        _saidas_padrao()
        sys.argv = ["-c", *args[2:]]
        exec(compile(args[1], "<string>", "exec"), {"__name__": "__main__"})
        return 0
    if primeiro == "-m" and len(args) >= 2:
        _saidas_padrao()
        modulo = args[1]
        sys.argv = [modulo, *args[2:]]
        try:
            runpy.run_module(modulo, run_name="__main__", alter_sys=True)
        except ImportError as e:
            print(f"O Nexus.exe não traz o módulo '{modulo}' ({e}). "
                  f"Para instalar pacotes novos, use a versão Python: python main.py",
                  file=sys.stderr)
            return 1
        return 0
    if primeiro.lower().endswith((".py", ".pyw")) and Path(primeiro).is_file():
        _saidas_padrao()
        sys.argv = list(args)
        sys.path.insert(0, str(Path(primeiro).resolve().parent))
        runpy.run_path(primeiro, run_name="__main__")
        return 0
    return None


def principal() -> None:
    import multiprocessing
    multiprocessing.freeze_support()

    os.chdir(PASTA)
    if str(PASTA) not in sys.path:
        sys.path.insert(0, str(PASTA))

    codigo = _como_python(sys.argv[1:])
    if codigo is not None:
        sys.exit(codigo)

    main_py = PASTA / "main.py"
    if not main_py.exists():
        _avisar("NEXUS Pro",
                "O Nexus.exe precisa ficar na pasta do Nexus, junto do main.py.\n\n"
                f"Pasta atual: {PASTA}")
        sys.exit(1)

    sys.argv[0] = str(main_py)
    try:
        runpy.run_path(str(main_py), run_name="__main__")
    except SystemExit:
        raise
    except BaseException:
        detalhe = traceback.format_exc()
        try:
            log = PASTA / "memory" / "erro_nexus_exe.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a", encoding="utf-8") as f:
                f.write(detalhe + "\n")
        except Exception:
            log = None
        _avisar("NEXUS Pro — erro ao abrir",
                "O NEXUS não conseguiu abrir.\n\n"
                + detalhe.strip().splitlines()[-1][:300]
                + (f"\n\nDetalhes em: {log}" if log else ""))
        sys.exit(1)


if __name__ == "__main__":
    principal()
