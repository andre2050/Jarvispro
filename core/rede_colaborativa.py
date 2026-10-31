"""Aprendizado colaborativo (NEXUS Ultra 2026 3.4): os NEXUS da sua rede trocam o que aprenderam a consertar.

Desligado por padrão. Para ligar: preferência ``rede_colaborativa`` = verdadeiro e o MESMO código de grupo
(``rede_colaborativa_codigo``, 8+ caracteres) em cada PC — por voz: "liga a rede colaborativa com o código …".

O QUE VIAJA — só o placar da auto-regeneração: "para a falha <tipo genérico> o remédio <id do catálogo>
funcionou N vezes e falhou M". Nada de conversa, arquivo, nome, caminho ou dado pessoal: a falha vai como
assinatura genérica (ex.: ``ModuleNotFoundError:cv2``, ``ArquivoEstragado``).

COMO VIAJA — UDP na rede local (porta 47474, broadcast), a cada 30 min e quando você pede. Cada pacote é
assinado com HMAC-SHA256 do código do grupo: quem não tem o código não consegue mandar nada que seja aceito.
Pacotes velhos (mais de 10 min) ou repetidos são descartados, e o tamanho é limitado.

O QUE SE FAZ COM O QUE CHEGA — só muda a ORDEM em que os remédios que JÁ EXISTEM aqui são tentados (o que vem
da rede pesa a metade do que foi visto neste PC). Um remédio que este NEXUS não conhece é ignorado, e nada que
chega pela rede é executado: o que precisa de confirmação continua precisando.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import socket
import threading
import time

from core import armazem
from core.protecao import engolida as _engolida

PORTA = 47474
MAX_BYTES = 16_000
VALIDADE_S = 600
ANUNCIO_S = 1800
MAX_PARES = 20
_ID = hashlib.sha256(f"{os.getpid()}-{time.time()}-{os.urandom(8).hex()}".encode()).hexdigest()[:12]
_vistos: dict[str, float] = {}
_trava = threading.RLock()
_estado = {"rodando": False, "recebidos": 0, "rejeitados": 0, "pares": {}, "ultimo_envio": 0.0}
_parar = threading.Event()


def _pref(chave: str, padrao):
    try:
        from core import preferences
        v = preferences.get(chave)
        return padrao if v is None else v
    except Exception:
        return padrao


def ligada() -> bool:
    return bool(_pref("rede_colaborativa", False)) and len(str(_pref("rede_colaborativa_codigo", ""))) >= 8


def _chave(codigo: str) -> bytes:
    return hashlib.sha256(("nexus-rede-colaborativa:" + codigo).encode("utf-8")).digest()


# ── pacote ───────────────────────────────────────────────────────────────────
def montar(placar: dict, codigo: str, agora: float | None = None) -> bytes:
    """O pacote assinado com o placar (só pares assinatura|remédio conhecidos)."""
    from core.autoregeneracao import REMEDIOS
    itens = {k: v for k, v in placar.items()
             if "|" in k and k.split("|", 1)[1] in REMEDIOS and isinstance(v, list) and len(v) == 2}
    corpo = {"v": 1, "de": _ID, "t": agora or time.time(), "nonce": os.urandom(8).hex(),
             "placar": dict(list(itens.items())[:150])}
    bruto = json.dumps(corpo, separators=(",", ":"), sort_keys=True)
    assinatura = hmac.new(_chave(codigo), bruto.encode("utf-8"), hashlib.sha256).hexdigest()
    return json.dumps({"corpo": bruto, "sig": assinatura}).encode("utf-8")


def abrir(dados: bytes, codigo: str, agora: float | None = None) -> dict | None:
    """O placar de um pacote válido, ou None (assinatura errada, velho, repetido, grande, ou nosso)."""
    agora = agora or time.time()
    if len(dados) > MAX_BYTES:
        return None
    try:
        env = json.loads(dados.decode("utf-8"))
        bruto, sig = str(env["corpo"]), str(env["sig"])
    except Exception:
        return None
    esperado = hmac.new(_chave(codigo), bruto.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(esperado, sig):
        return None
    try:
        corpo = json.loads(bruto)
    except Exception:
        return None
    if corpo.get("v") != 1 or corpo.get("de") == _ID or abs(agora - float(corpo.get("t", 0))) > VALIDADE_S:
        return None
    with _trava:
        for k in [k for k, t in _vistos.items() if agora - t > VALIDADE_S]:
            _vistos.pop(k, None)
        if corpo.get("nonce") in _vistos:
            return None
        _vistos[str(corpo.get("nonce"))] = agora
    placar = corpo.get("placar")
    return {"de": str(corpo.get("de"))[:12], "placar": placar if isinstance(placar, dict) else {}}


def mesclar(placar_remoto: dict, de: str) -> int:
    """Guarda o placar de um par (o último de cada um vale; somado entre pares). Devolve quantos pares aceitou."""
    from core import autoregeneracao as AR
    aceitos: dict[str, list[int]] = {}
    for k, v in placar_remoto.items():
        if (isinstance(k, str) and "|" in k and k.split("|", 1)[1] in AR.REMEDIOS and isinstance(v, list)
                and len(v) == 2 and all(isinstance(x, int) and 0 <= x <= 10_000 for x in v)):
            aceitos[k[:120]] = [int(v[0]), int(v[1])]
    with _trava:
        _estado["pares"][de] = {"t": time.time(), "placar": aceitos}
        while len(_estado["pares"]) > MAX_PARES:                  # os mais antigos saem
            _estado["pares"].pop(min(_estado["pares"], key=lambda k: _estado["pares"][k]["t"]))
        soma: dict[str, list[int]] = {}
        for par in _estado["pares"].values():
            for k, (ok, ruim) in par["placar"].items():
                s = soma.setdefault(k, [0, 0])
                s[0] += ok
                s[1] += ruim
        d = AR._ler()
        d["rede"] = soma
        armazem.salvar(AR.ARQ, d)
    return len(aceitos)


# ── rede ─────────────────────────────────────────────────────────────────────
def anunciar() -> bool:
    if not ligada():
        return False
    from core import autoregeneracao as AR
    pacote = montar(AR._ler()["placar"], str(_pref("rede_colaborativa_codigo", "")))
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(pacote, ("255.255.255.255", PORTA))
        with _trava:
            _estado["ultimo_envio"] = time.time()
        return True
    except Exception:
        return False


def _ouvir() -> None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("", PORTA))
        s.settimeout(2.0)
    except Exception as e:
        print(f"[Rede colaborativa] não consegui ouvir na porta {PORTA}: {e}")
        with _trava:
            _estado["rodando"] = False
        return
    ultimo_anuncio = 0.0
    with s:
        while not _parar.is_set():
            if not ligada():
                break
            if time.time() - ultimo_anuncio > ANUNCIO_S:
                anunciar()
                ultimo_anuncio = time.time()
            try:
                dados, _origem = s.recvfrom(MAX_BYTES + 1)
            except socket.timeout:
                continue
            except Exception:
                time.sleep(1)
                continue
            pacote = abrir(dados, str(_pref("rede_colaborativa_codigo", "")))
            with _trava:
                if pacote is None:
                    _estado["rejeitados"] += 1
                    continue
                _estado["recebidos"] += 1
            n = mesclar(pacote["placar"], pacote["de"])
            try:
                from core import isa
                isa.registrar("sistema", "Rede colaborativa", f"aprendi {n} par(es) falha→remédio de outro NEXUS",
                              origem="isa")
            except Exception:
                _engolida("core/rede_colaborativa.py:180")
    with _trava:
        _estado["rodando"] = False


def garantir() -> bool:
    """Liga o ouvinte se a rede estiver ligada nas preferências (chamado pelo laço de segundo plano)."""
    if not ligada():
        _parar.set()
        return False
    with _trava:
        if _estado["rodando"]:
            return True
        _estado["rodando"] = True
    _parar.clear()
    threading.Thread(target=_ouvir, daemon=True, name="nexus-rede-colaborativa").start()
    return True


def configurar(ligar: bool, codigo: str = "") -> str:
    from core import preferences
    codigo = str(codigo or "").strip()
    if ligar:
        if len(codigo) < 8 and len(str(_pref("rede_colaborativa_codigo", ""))) < 8:
            return "Para ligar a rede colaborativa, diga um código de grupo com pelo menos 8 caracteres."
        valores = {"rede_colaborativa": True}
        if codigo:
            valores["rede_colaborativa_codigo"] = codigo
        preferences.save(valores)
        garantir()
        return ("Rede colaborativa ligada. Use o mesmo código nos outros PCs. Só o placar de reparos (sem dados "
                "pessoais) é trocado, assinado com o código.")
    preferences.save({"rede_colaborativa": False})
    _parar.set()
    return "Rede colaborativa desligada."


def status() -> dict:
    with _trava:
        return {"ligada": ligada(), "rodando": _estado["rodando"], "pares": len(_estado["pares"]),
                "recebidos": _estado["recebidos"], "rejeitados": _estado["rejeitados"],
                "ultimo_envio": _estado["ultimo_envio"]}
