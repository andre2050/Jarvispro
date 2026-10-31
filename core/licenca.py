"""
core/licenca.py — 🔑 chave de licença do NEXUS Ultra 2026 (offline, assinada).

Como funciona
  • Quem gera as chaves é só o desenvolvedor (André), com a CHAVE PRIVADA, que
    NUNCA fica dentro do NEXUS (fica na pasta "Ferramentas do desenvolvedor").
  • O NEXUS carrega apenas a chave PÚBLICA (abaixo). Ela confere se a assinatura
    da licença é verdadeira, mas não consegue criar licenças novas.
  • Funciona sem internet. Cada licença pode ter: nome do cliente, validade e
    (opcional) o ID de um computador específico.

Limite honesto: o NEXUS é um programa em Python, e quem sabe programar pode
editar este arquivo e tirar a verificação. A licença impede o uso casual e o
compartilhamento de chaves; não é um cofre. Para proteção mais forte, gere o
Nexus.exe (gerar_exe.bat) e distribua só o .exe.
"""
from __future__ import annotations

import base64
import hashlib
import json
import platform
import re
import time
import uuid
from datetime import date, datetime
from pathlib import Path
from core.protecao import engolida as _engolida

# Chave pública Ed25519 (32 bytes, base64). Só confere assinaturas.
PUBLIC_KEY_B64 = "IdYVqJpleK2MY8gwOjM0Z2vfkKKOgHfoIFyf8ppwfNY="

PREFIXO = "NEXUS"
_VERSAO = 1

_BASE = Path(__file__).resolve().parent.parent
ARQUIVO = _BASE / "config" / "licenca.json"


# ── ID da máquina ────────────────────────────────────────────────────────────
def _identidade_da_maquina() -> str:
    """Algo que NÃO muda com VPN, adaptador de rede, Wi-Fi/cabo ou renomear o PC.

    Windows: MachineGuid (gravado na instalação do sistema). Linux: /etc/machine-id.
    macOS: IOPlatformUUID. Só se nada disso existir cai no MAC (uuid.getnode)."""
    try:
        if platform.system() == "Windows":
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography",
                                0, winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)) as k:
                v = str(winreg.QueryValueEx(k, "MachineGuid")[0]).strip()
                if v:
                    return "win:" + v.lower()
        elif platform.system() == "Linux":
            for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
                try:
                    v = Path(p).read_text().strip()
                    if v:
                        return "lin:" + v
                except OSError:
                    pass
        elif platform.system() == "Darwin":
            import subprocess
            out = subprocess.run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                                 capture_output=True, text=True, timeout=5).stdout
            m = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', out)
            if m:
                return "mac:" + m.group(1)
    except Exception:
        _engolida("core/licenca.py:69")
    return f"mac:{uuid.getnode()}|{platform.machine()}"


def id_da_maquina() -> str:
    """Um código curto e estável deste computador (XXXX-XXXX-XXXX).

    O cliente manda este código para você, que gera a chave presa a ele."""
    bruto = _identidade_da_maquina()
    h = hashlib.sha256(bruto.encode("utf-8")).hexdigest().upper()[:12]
    return f"{h[:4]}-{h[4:8]}-{h[8:12]}"


def _norm_maq(s: str) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(s or "").upper())


# ── Ed25519 em Python puro (só VERIFICAR) ───────────────────────────────────
# Reserva para o caso do pacote 'cryptography' não estar instalado ou não vir no
# Nexus.exe: sem ele a licença NUNCA poderia ser conferida e o NEXUS não abriria.
# É a implementação de referência da RFC 8032, só a parte de verificação (não cria
# assinaturas, então não enfraquece nada). Leva alguns milissegundos.
_P = 2 ** 255 - 19
_Q = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _xrecover(y: int) -> int:
    xx = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P)
    x = pow(xx, (_P + 3) // 8, _P)
    if (x * x - xx) % _P != 0:
        x = x * _I % _P
    if x % 2 != 0:
        x = _P - x
    return x


_BY = 4 * pow(5, _P - 2, _P) % _P
_BX = _xrecover(_BY)
_B = (_BX % _P, _BY % _P, 1, _BX * _BY % _P)


def _ed_add(a, b):
    A = (a[1] - a[0]) * (b[1] - b[0]) % _P
    B = (a[1] + a[0]) * (b[1] + b[0]) % _P
    C = 2 * a[3] * b[3] * _D % _P
    D = 2 * a[2] * b[2] % _P
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _P, G * H % _P, F * G % _P, E * H % _P)


def _ed_mul(k: int, pt):
    q = (0, 1, 1, 0)
    while k > 0:
        if k & 1:
            q = _ed_add(q, pt)
        pt = _ed_add(pt, pt)
        k >>= 1
    return q


def _ed_eq(a, b) -> bool:
    return ((a[0] * b[2] - b[0] * a[2]) % _P == 0
            and (a[1] * b[2] - b[1] * a[2]) % _P == 0)


def _ed_decode(s: bytes):
    y = int.from_bytes(s, "little")
    sinal = y >> 255
    y &= (1 << 255) - 1
    if y >= _P:
        return None
    x = _xrecover(y)
    if (x * x - (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P)) % _P != 0:
        return None                       # não é ponto da curva
    if x == 0 and sinal == 1:
        return None
    if (x & 1) != sinal:
        x = _P - x
    return (x, y, 1, x * y % _P)


def _ed25519_verificar_puro(pub: bytes, msg: bytes, sig: bytes) -> bool:
    try:
        if len(pub) != 32 or len(sig) != 64:
            return False
        A = _ed_decode(pub)
        R = _ed_decode(sig[:32])
        S = int.from_bytes(sig[32:], "little")
        if A is None or R is None or S >= _Q:
            return False
        h = int.from_bytes(hashlib.sha512(sig[:32] + pub + msg).digest(), "little") % _Q
        return _ed_eq(_ed_mul(S, _B), _ed_add(R, _ed_mul(h, A)))
    except Exception:
        return False


def _assinatura_confere(corpo: bytes, assinatura: bytes) -> bool:
    """Confere a assinatura: pelo 'cryptography' e, se ele não existir, em Python puro."""
    pub = base64.b64decode(PUBLIC_KEY_B64)
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except Exception:
        return _ed25519_verificar_puro(pub, corpo, assinatura)
    try:
        Ed25519PublicKey.from_public_bytes(pub).verify(assinatura, corpo)
        return True
    except InvalidSignature:
        return False
    except Exception:
        return _ed25519_verificar_puro(pub, corpo, assinatura)


# ── Formato da chave ─────────────────────────────────────────────────────────
def _b32d(texto: str) -> bytes:
    t = re.sub(r"[^A-Z2-7]", "", texto.upper())
    t += "=" * (-len(t) % 8)
    return base64.b32decode(t)


def _b32e(dados: bytes) -> str:
    return base64.b32encode(dados).decode("ascii").rstrip("=")


def montar_chave(payload: dict, assinatura: bytes) -> str:
    """(usado pelo gerador) payload + assinatura → 'NEXUS-XXXXX-XXXXX-…'"""
    corpo = json.dumps(payload, separators=(",", ":"), ensure_ascii=False,
                       sort_keys=True).encode("utf-8")
    bruto = len(corpo).to_bytes(2, "big") + corpo + assinatura
    txt = _b32e(bruto)
    grupos = [txt[i:i + 5] for i in range(0, len(txt), 5)]
    return PREFIXO + "-" + "-".join(grupos)


def _cortar_no_tamanho(t: str) -> str:
    """Se vieram letras sobrando depois da chave (texto colado junto), corta no tamanho exato."""
    try:
        n = int.from_bytes(_b32d(t[:8])[:2], "big")
        total_bytes = 2 + n + 64
        chars = -(-total_bytes * 8 // 5)
        return t[:chars] if len(t) >= chars else t
    except Exception:
        return t


def _candidatas(texto: str) -> list[str]:
    """Acha as chaves dentro de um texto qualquer (cabeçalho, aspas, quebras de linha…)."""
    bruto = str(texto or "").upper()
    achados = re.findall(r"NEXUS[\s\-]+((?:[A-Z2-7]{2,5}[\s\-]*)+)", bruto)
    out = []
    for a in achados:
        grupos = re.sub(r"[^A-Z2-7]", "", a)
        if len(grupos) >= 100:                    # uma chave real tem ~200 letras
            out.append(_cortar_no_tamanho(grupos))
    if not out:                                    # colou sem o 'NEXUS-' no começo?
        t = re.sub(r"[^A-Za-z0-9]", "", bruto)
        if t.startswith("NEXUS"):
            out.append(_cortar_no_tamanho(re.sub(r"[^A-Z2-7]", "", t[5:])))
    return out


def _abrir(chave: str) -> tuple[dict, bytes, bytes]:
    """chave → (dados, corpo_assinado, assinatura). Levanta ValueError se malformada."""
    cands = _candidatas(chave)
    if not cands:
        raise ValueError("a chave deve começar com NEXUS-")
    ultimo = None
    for t in cands:
        try:
            bruto = _b32d(t)
            n = int.from_bytes(bruto[:2], "big")
            corpo = bruto[2:2 + n]
            assinatura = bruto[2 + n:]
            if len(corpo) != n or len(assinatura) != 64:
                raise ValueError("tamanho")
            dados = json.loads(corpo.decode("utf-8"))
            if not isinstance(dados, dict):
                raise ValueError("formato")
            return dados, corpo, assinatura
        except Exception:
            ultimo = ValueError("chave incompleta ou com caractere trocado")
    raise ultimo


# ── Verificação ──────────────────────────────────────────────────────────────
def verificar(chave: str, hoje: date | None = None,
              maquina: str | None = None) -> tuple[bool, str, dict]:
    """Confere uma chave. Devolve (valida, motivo_em_português, dados)."""
    try:
        dados, corpo, assinatura = _abrir(chave)
    except ValueError as e:
        return False, f"Chave inválida: {e}.", {}

    if not _assinatura_confere(corpo, assinatura):
        return False, "Chave inválida: a assinatura não confere.", {}

    if int(dados.get("v", 0)) != _VERSAO:
        return False, "Esta chave é de outra versão do NEXUS.", dados

    ate = str(dados.get("ate") or "").strip()
    if ate:
        try:
            limite = datetime.strptime(ate, "%Y-%m-%d").date()
        except ValueError:
            return False, "Chave inválida: validade ilegível.", dados
        if (hoje or date.today()) > limite:
            return False, f"Licença vencida em {limite.strftime('%d/%m/%Y')}.", dados

    maq = str(dados.get("maq") or "").strip()
    if maq and _norm_maq(maq) != _norm_maq(maquina or id_da_maquina()):
        return False, ("Esta licença é de outro computador. "
                       f"O ID deste PC é {id_da_maquina()}."), dados

    return True, "Licença válida.", dados


# ── Guardar / ler / status ───────────────────────────────────────────────────
def _ler_arquivo() -> dict:
    try:
        return json.loads(ARQUIVO.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _gravar(d: dict) -> None:
    ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
    ARQUIVO.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")


def ativar(chave: str) -> tuple[bool, str]:
    """Confere e, se for válida, grava em config/licenca.json."""
    ok, msg, dados = verificar(chave)
    if not ok:
        return False, msg
    _gravar({"chave": PREFIXO + "-" + "-".join(
                 c[i:i + 5] for c in _candidatas(chave)[:1] for i in range(0, len(c), 5)),
             "ativada_em": int(time.time()), "visto_em": int(time.time())})
    nome = dados.get("nome") or "você"
    return True, f"Licença ativada para {nome}."


def status() -> dict:
    """{'valida': bool, 'motivo': str, 'nome': str, 'ate': str, 'dias': int|None}"""
    d = _ler_arquivo()
    chave = d.get("chave", "")
    if not chave:
        return {"valida": False, "motivo": "Nenhuma licença ativada.", "nome": "",
                "ate": "", "dias": None}

    # relógio voltado para "ressuscitar" licença vencida: tolera 1 dia
    agora = int(time.time())
    visto = int(d.get("visto_em") or 0)
    if visto and agora < visto - 86400:
        return {"valida": False, "motivo": "A data do computador está atrás da última "
                "vez que o NEXUS abriu. Acerte o relógio.", "nome": "", "ate": "",
                "dias": None}

    ok, msg, dados = verificar(chave)
    if ok and agora > visto:
        d["visto_em"] = agora
        try:
            _gravar(d)
        except Exception:
            _engolida("core/licenca.py:334")
    ate = str(dados.get("ate") or "")
    dias = None
    if ate:
        try:
            dias = (datetime.strptime(ate, "%Y-%m-%d").date() - date.today()).days
        except ValueError:
            pass
    return {"valida": ok, "motivo": msg, "nome": str(dados.get("nome") or ""),
            "ate": ate, "dias": dias}


def valida() -> bool:
    return bool(status()["valida"])


def resumo() -> str:
    """Uma linha para o 'Sobre' e a conversa."""
    s = status()
    if not s["valida"]:
        return f"Licença: {s['motivo']}"
    quem = f" — {s['nome']}" if s["nome"] else ""
    if s["ate"]:
        return f"Licença ativa{quem} (vale até {s['ate'][8:10]}/{s['ate'][5:7]}/{s['ate'][:4]})"
    return f"Licença ativa{quem} (sem validade)"


def texto_curto() -> str:
    """Para o 'Sobre': 'ativa — Nome (vale até 31/12/2027)' ou o motivo do bloqueio."""
    s = status()
    if not s["valida"]:
        return s["motivo"]
    quem = f" — {s['nome']}" if s["nome"] else ""
    if s["ate"]:
        return f"ativa{quem} (vale até {s['ate'][8:10]}/{s['ate'][5:7]}/{s['ate'][:4]})"
    return f"ativa{quem} (sem validade)"
