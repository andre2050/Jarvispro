"""
core/tunel.py — acesso de fora de casa ao painel do celular, por túnel (NEXUS Ultra 2026 3.6).

Usa o `cloudflared` (Cloudflare "Quick Tunnel", grátis, sem conta): ele liga o painel do seu PC a um endereço
https://algo.trycloudflare.com com certificado VÁLIDO. Isso resolve duas coisas de uma vez: acessar de fora de casa e
o navegador do celular aceitar instalar o app (PWA) e receber avisos (push).

Segurança
  • Só abre com o seu CONFIRMAR (feito em actions/tunel_painel.py) e fecha sozinho depois de algumas horas.
  • O painel continua exigindo a chave de 6 dígitos que muda, login criptografado e bloqueio por tentativas
    (o servidor enxerga o IP real do visitante pelo cabeçalho do túnel, não o 127.0.0.1).
  • O endereço é novo a cada vez; ninguém o acha sem você mostrar.
  • O NEXUS não baixa o cloudflared por conta própria: instale você (Windows: winget install Cloudflare.cloudflared).
Limite honesto: com o túnel aberto, o painel fica acessível pela internet a quem tiver o endereço e a chave.
"""
from __future__ import annotations

import atexit
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from core.protecao import engolida as _engolida

_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
DURACAO_PADRAO_H = 4.0
DURACAO_MAX_H = 12.0
TEMPO_ABRIR = 40.0


class ErroTunel(Exception):
    """Mensagem segura para falar em voz alta."""


def achar_cloudflared() -> str | None:
    from pathlib import Path
    base = Path(__file__).resolve().parent.parent
    for p in (shutil.which("cloudflared"), str(base / "config" / "ferramentas" / "cloudflared.exe"),
              str(base / "config" / "ferramentas" / "cloudflared")):
        if p and os.path.exists(p):
            return p
    return None


class Tunel:
    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.url = ""
        self.expira_em = 0.0
        self._timer: threading.Timer | None = None
        self.ultimas: list[str] = []        # últimas linhas do cloudflared (para diagnóstico)
        self._ao_mudar = None
        self._trava = threading.RLock()

    def ao_mudar(self, fn) -> None:
        """fn(url_ou_vazio) é chamada quando o túnel abre ou fecha (o servidor usa para trocar a URL pública)."""
        self._ao_mudar = fn

    def ativo(self) -> bool:
        return self.proc is not None and self.proc.poll() is None and bool(self.url)

    def iniciar(self, porta: int, https: bool, horas: float = DURACAO_PADRAO_H, binario: str | None = None,
                argumentos_extra: list[str] | None = None) -> str:
        with self._trava:
            if self.ativo():
                return self.url
            exe = binario or achar_cloudflared()
            if not exe:
                raise ErroTunel("Não achei o cloudflared. Instale (Windows: winget install Cloudflare.cloudflared) e tente de novo.")
            origem = f"{'https' if https else 'http'}://127.0.0.1:{int(porta)}"
            cmd = [exe, "tunnel", "--no-autoupdate", "--url", origem] + (["--no-tls-verify"] if https else []) + list(argumentos_extra or [])
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
            try:
                self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False,
                                             creationflags=flags, bufsize=0)
            except OSError as e:
                raise ErroTunel(f"Não consegui abrir o cloudflared: {str(e)[:100]}")
            achou = threading.Event()
            ultimas = self.ultimas = []
            proc = self.proc

            def ler():
                try:
                    for bruta in iter(proc.stdout.readline, b""):
                        linha = bruta.decode("utf-8", errors="replace")
                        ultimas.append(linha.strip())
                        del ultimas[:-8]
                        m = _URL.search(linha)
                        if m and not self.url:
                            self.url = m.group(0)
                            achou.set()
                except Exception:
                    _engolida("core/tunel.py:95")
                achou.set()

            threading.Thread(target=ler, daemon=True, name="tunel-leitor").start()
            achou.wait(TEMPO_ABRIR)
            if not self.url:
                self.parar()
                raise ErroTunel("O túnel não abriu a tempo (sem internet ou cloudflared com problema). "
                                + (ultimas[-1][:120] if ultimas else ""))
            horas = max(0.1, min(float(horas), DURACAO_MAX_H))
            self.expira_em = time.time() + horas * 3600
            self._timer = threading.Timer(horas * 3600, self.parar)
            self._timer.daemon = True
            self._timer.start()
            if self._ao_mudar:
                self._ao_mudar(self.url)
            return self.url

    def parar(self) -> None:
        with self._trava:
            p, self.proc = self.proc, None
            had = bool(self.url)
            self.url, self.expira_em = "", 0.0
            if self._timer:
                self._timer.cancel()
                self._timer = None
        if p is not None:
            try:
                p.terminate()
                p.wait(timeout=4)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    _engolida("core/tunel.py:129")
        if had and self._ao_mudar:
            self._ao_mudar("")

    def restante_min(self) -> int:
        return max(0, int((self.expira_em - time.time()) / 60)) if self.ativo() else 0


_tunel = Tunel()
atexit.register(_tunel.parar)


def tunel() -> Tunel:
    return _tunel
