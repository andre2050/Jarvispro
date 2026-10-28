"""
core/push_web.py — avisos no celular com o app FECHADO (Web Push) (NEXUS Ultra 2026 3.6).

Como funciona
  • O celular, depois que você liga o 🔔 no painel, entrega ao NEXUS uma "assinatura" (endereço do serviço de push do
    navegador + chaves). O NEXUS guarda isso em memory/push_subs.json (só no seu PC).
  • Quando o NEXUS tem algo a dizer e NENHUM celular está com o painel aberto, ele manda um aviso curto pelo serviço de
    push do navegador (Google, Mozilla, Apple ou Microsoft). O conteúdo viaja CRIPTOGRAFADO de ponta a ponta com as
    chaves do seu celular: nem o serviço de push consegue ler. Cortado em 160 letras, sem anexos.
  • As chaves de identificação (VAPID) ficam em memory/push_vapid.pem. Nada disso vai para o GitHub.

Segurança
  • Só aceita assinaturas cujo endereço seja https de um serviço de push conhecido — senão alguém com acesso ao painel
    poderia usar o NEXUS para fazer pedidos a qualquer endereço da sua rede (SSRF).
  • No máximo 10 celulares e um aviso a cada 20 s.
  • Precisa do pacote `pywebpush` (pip install pywebpush) e de https confiável no painel (túnel — core/tunel.py).
"""
from __future__ import annotations

import base64
import json
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

_BASE = Path(__file__).resolve().parent.parent
ARQ_SUBS = _BASE / "memory" / "push_subs.json"
ARQ_CHAVE = _BASE / "memory" / "push_vapid.pem"
ASSUNTO_VAPID = "mailto:nexus-ultra@users.noreply.github.com"   # o pywebpush exige um mailto: na identificação VAPID
MAX_ASSINATURAS = 10
INTERVALO_MIN = 20.0
MAX_CORPO = 160

HOSTS_PERMITIDOS = ("fcm.googleapis.com", "updates.push.services.mozilla.com", "web.push.apple.com")
SUFIXOS_PERMITIDOS = (".push.apple.com", ".notify.windows.com", ".push.services.mozilla.com")

_trava = threading.RLock()
_ultimo_envio = 0.0


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# ── chaves VAPID ─────────────────────────────────────────────────────────────
def chave_publica(arq: Path | None = None) -> str:
    """A chave pública (applicationServerKey, base64url) para o navegador. Cria o par na primeira vez."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    arq = Path(arq or ARQ_CHAVE)
    with _trava:
        if arq.exists():
            priv = serialization.load_pem_private_key(arq.read_bytes(), password=None)
        else:
            priv = ec.generate_private_key(ec.SECP256R1())
            arq.parent.mkdir(parents=True, exist_ok=True)
            arq.write_bytes(priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                               serialization.NoEncryption()))
            try:
                arq.chmod(0o600)
            except OSError:
                pass
        pub = priv.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return _b64u(pub)


# ── assinaturas ──────────────────────────────────────────────────────────────
def endpoint_permitido(url: str) -> bool:
    try:
        u = urlparse(str(url))
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not host or u.username or u.password or (u.port not in (None, 443)):
        return False
    return host in HOSTS_PERMITIDOS or any(host.endswith(s) for s in SUFIXOS_PERMITIDOS)


def validar_assinatura(sub) -> dict:
    """Devolve a assinatura limpa ({endpoint, keys:{p256dh, auth}}) ou levanta ValueError com o motivo."""
    if not isinstance(sub, dict):
        raise ValueError("assinatura inválida")
    endpoint = str(sub.get("endpoint") or "")
    if len(endpoint) > 1000 or not endpoint_permitido(endpoint):
        raise ValueError("endereço de push não permitido")
    keys = sub.get("keys") if isinstance(sub.get("keys"), dict) else {}
    p256dh, auth = str(keys.get("p256dh") or ""), str(keys.get("auth") or "")
    if not (re.fullmatch(r"[A-Za-z0-9_-]{80,100}", p256dh) and re.fullmatch(r"[A-Za-z0-9_-]{20,30}", auth)):
        raise ValueError("chaves da assinatura inválidas")
    return {"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}}


def _ler(arq: Path) -> list[dict]:
    try:
        d = json.loads(Path(arq).read_text(encoding="utf-8"))
        return [x for x in d if isinstance(x, dict) and x.get("endpoint")] if isinstance(d, list) else []
    except Exception:
        return []


def _gravar(subs: list[dict], arq: Path) -> None:
    arq = Path(arq)
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(subs, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(arq)


def assinar(sub, arq: Path | None = None) -> int:
    """Guarda a assinatura (troca a antiga do mesmo celular). Devolve quantos celulares ficam."""
    limpa = validar_assinatura(sub)
    arq = Path(arq or ARQ_SUBS)
    with _trava:
        subs = [s for s in _ler(arq) if s["endpoint"] != limpa["endpoint"]]
        subs.append({**limpa, "criado": time.strftime("%Y-%m-%d %H:%M")})
        subs = subs[-MAX_ASSINATURAS:]
        _gravar(subs, arq)
        return len(subs)


def cancelar(endpoint: str, arq: Path | None = None) -> int:
    arq = Path(arq or ARQ_SUBS)
    with _trava:
        subs = [s for s in _ler(arq) if s["endpoint"] != endpoint]
        _gravar(subs, arq)
        return len(subs)


def quantas(arq: Path | None = None) -> int:
    return len(_ler(Path(arq or ARQ_SUBS)))


def disponivel() -> bool:
    import importlib.util
    return importlib.util.find_spec("pywebpush") is not None


# ── envio ────────────────────────────────────────────────────────────────────
def _status_do_erro(e: Exception) -> int | None:
    r = getattr(e, "response", None)
    return getattr(r, "status_code", None) if r is not None else None


def _webpush_real(sub: dict, dados: str, arq_chave: Path) -> None:
    from pywebpush import webpush
    webpush(subscription_info=sub, data=dados, vapid_private_key=str(arq_chave),
            vapid_claims={"sub": ASSUNTO_VAPID}, ttl=3600, timeout=10)


def enviar(titulo: str, corpo: str, arq_subs: Path | None = None, arq_chave: Path | None = None,
           enviar_fn=None, agora: float | None = None, ignorar_intervalo: bool = False) -> dict:
    """Manda o aviso a todos os celulares assinados. Nunca levanta erro: devolve {enviados, removidos, falhas, motivo}."""
    global _ultimo_envio
    arq_subs, arq_chave = Path(arq_subs or ARQ_SUBS), Path(arq_chave or ARQ_CHAVE)
    res = {"enviados": 0, "removidos": 0, "falhas": 0, "motivo": ""}
    if not ignorar_intervalo:
        try:                                                    # modo foco (3.7): nada de aviso no celular
            from actions import focus_mode as _F
            if _F.active_reason():
                res["motivo"] = "modo foco ligado"
                return res
            from core import perfis as _P
            if _P.silencia_integracao("push"):
                res["motivo"] = "perfil sem avisos no celular"
                return res
        except Exception:
            pass
    agora = time.monotonic() if agora is None else agora
    with _trava:
        subs = _ler(arq_subs)
        if not subs:
            res["motivo"] = "nenhum celular assinado"
            return res
        if enviar_fn is None and not disponivel():
            res["motivo"] = "falta o pacote pywebpush (pip install pywebpush)"
            return res
        if not ignorar_intervalo and agora - _ultimo_envio < INTERVALO_MIN:
            res["motivo"] = "aviso recente demais"
            return res
        _ultimo_envio = agora
    chave_publica(arq_chave)                                   # garante que o par existe
    dados = json.dumps({"title": str(titulo)[:60] or "NEXUS", "body": " ".join(str(corpo).split())[:MAX_CORPO], "tag": "nexus"},
                       ensure_ascii=False)
    manter = []
    for s in subs:
        try:
            if not endpoint_permitido(s["endpoint"]):
                raise ValueError("endereço não permitido")
            (enviar_fn or _webpush_real)({"endpoint": s["endpoint"], "keys": s["keys"]}, dados, arq_chave)
            res["enviados"] += 1
            manter.append(s)
        except Exception as e:
            if _status_do_erro(e) in (404, 410) or isinstance(e, ValueError):
                res["removidos"] += 1                           # celular desinstalou/revogou: esquece
            else:
                res["falhas"] += 1
                manter.append(s)
    if res["removidos"]:
        with _trava:
            _gravar(manter, arq_subs)
    return res
