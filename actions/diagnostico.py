"""Diagnóstico do próprio NEXUS (NEXUS Ultra 2026 2.1).

    "o que deu errado hoje?"          → falhas do dia, agrupadas
    "como foi o NEXUS essa semana?"   → resumo: quantas ações, quantas deram certo, o que mais usei
    "o que está lento?"               → ferramentas que demoram
    "o NEXUS está saudável?"          → chaves, permissões, disco, pacotes que faltam
    "estou sem internet?"             → testa a conexão com o Gemini

Lê o registro que o próprio NEXUS já grava (memory/audit.log) — não pergunta nada pela internet, não
mexe em nada e NUNCA mostra chaves, argumentos das ações nem o conteúdo dos resultados: só o nome da
ferramenta, o horário e um motivo curto da falha (cortado e sem caracteres de controle).
O motivo curto pode ter vindo de fora (uma página da web, por exemplo), então a lista de falhas é
entregue ao modelo como conteúdo NÃO confiável (core/verificacao.py).
"""
from __future__ import annotations

import importlib.util
import platform
import re
import shutil
import socket
from datetime import datetime, timedelta
from pathlib import Path

from core import audit
from core.pt_time import agora

_BASE = Path(__file__).resolve().parent.parent
_MAX_LINHAS = 20000
_MOTIVO_MAX = 90

# pacote → para que serve (se faltar, o que deixa de funcionar)
_PACOTES = {
    "PyQt6": ("PyQt6", "a janela do NEXUS"),
    "sounddevice": ("sounddevice", "microfone e voz"),
    "google.genai": ("google-genai", "a conversa por voz com o Gemini"),
    "playwright": ("playwright", "navegador automático e o agente de código (conferência no navegador)"),
    "fastapi": ("fastapi", "o controle remoto pelo celular"),
    "uvicorn": ("uvicorn", "o controle remoto pelo celular"),
    "cryptography": ("cryptography", "a criptografia do controle remoto"),
    "psutil": ("psutil", "informações do computador"),
    "pyautogui": ("pyautogui", "controlar mouse e teclado"),
    "cv2": ("opencv-python", "câmera e visão"),
    "mss": ("mss", "capturar a tela"),
    "bs4": ("beautifulsoup4", "pesquisa na web"),
    "requests": ("requests", "pesquisa na web"),
}


# ── leitura do registro ──────────────────────────────────────────────────────

def _quando(e: dict) -> datetime | None:
    try:
        return datetime.strptime(str(e.get("ts")), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _status(e: dict) -> str:
    m = re.match(r"\s*\[(done|unverified|failed)\]", str(e.get("result", "")), re.IGNORECASE)
    return m.group(1).lower() if m else "done"


def _motivo(e: dict) -> str:
    t = re.sub(r"^\s*\[(done|unverified|failed)\]\s*", "", str(e.get("result", "")), flags=re.IGNORECASE)
    t = re.sub(r"[\x00-\x1f\x7f]+", " ", t)
    t = re.sub(r"<[^>]{0,200}>", "", t)                         # tags (inclusive a do conteúdo não confiável)
    t = re.sub(r"\s+", " ", t).strip()
    return (t[:_MOTIVO_MAX] + "…") if len(t) > _MOTIVO_MAX else t


def _periodo(nome) -> tuple[datetime | None, datetime | None, str]:
    t = re.sub(r"[^a-z]", "", str(nome or "hoje").lower().replace("ã", "a").replace("ê", "e"))
    h = agora()
    dia = h.replace(hour=0, minute=0, second=0, microsecond=0)
    if t in ("ontem", "yesterday"):
        return dia - timedelta(days=1), dia, "ontem"
    if t.startswith("sema") or t == "week":
        return h - timedelta(days=7), None, "nos últimos 7 dias"
    if t in ("tudo", "all", "total", "sempre", "geral"):
        return None, None, "em todo o registro"
    return dia, None, "hoje"


def _entradas(nome) -> tuple[list[dict], str]:
    """Registros do período (do mais antigo ao mais novo), incluindo o arquivo que já foi girado."""
    ini, fim, rotulo = _periodo(nome)
    atual = audit._FILE
    bruto = audit.ler(atual.with_name(atual.name + ".1"), _MAX_LINHAS) + audit.ler(atual, _MAX_LINHAS)
    saida = []
    for e in bruto:
        q = _quando(e)
        if q is None or (ini and q < ini) or (fim and q >= fim):
            continue
        saida.append(e)
    return saida, rotulo


def _segundos(ms: float) -> str:
    return f"{ms / 1000:.1f}".replace(".", ",") + " s"


def _registro_ligado() -> bool:
    try:
        from core import preferences as P
        return bool(P.get("audit_enabled"))
    except Exception:
        return True


def _sem_dados(rotulo: str) -> str:
    if not _registro_ligado():
        return ("[done] O registro de ações está desligado nas configurações, então não há o que analisar. "
                "Ligue 'registro de auditoria' para eu poder diagnosticar.")
    return f"[done] Ainda não há ações registradas {rotulo}."


# ── ações ────────────────────────────────────────────────────────────────────

def _resumo(p: dict) -> str:
    es, rotulo = _entradas(p.get("period"))
    if not es:
        return _sem_dados(rotulo)
    por: dict[str, dict] = {}
    for e in es:
        d = por.setdefault(str(e["tool"]), {"n": 0, "failed": 0, "unverified": 0, "ms": []})
        d["n"] += 1
        s = _status(e)
        if s in ("failed", "unverified"):
            d[s] += 1
        if isinstance(e.get("ms"), (int, float)):
            d["ms"].append(float(e["ms"]))
    total = len(es)
    falhas = sum(d["failed"] for d in por.values())
    incertas = sum(d["unverified"] for d in por.values())
    ok = total - falhas - incertas
    linhas = [f"Diagnóstico {rotulo}: {total} ações; {ok} deram certo ({ok * 100 // total}%), "
              f"{incertas} sem confirmação, {falhas} falharam."]
    mais = sorted(por.items(), key=lambda kv: -kv[1]["n"])[:5]
    linhas.append("Mais usadas: " + ", ".join(f"{k} {v['n']}" for k, v in mais) + ".")
    ruins = sorted(((k, v) for k, v in por.items() if v["failed"] and v["n"] >= 3 and v["failed"] / v["n"] >= 0.4),
                   key=lambda kv: -kv[1]["failed"])[:3]
    if ruins:
        linhas.append("Atenção: " + "; ".join(f"{k} falhou {v['failed']} de {v['n']} vezes" for k, v in ruins)
                      + ". Peça “o que deu errado” para ver os motivos.")
    lentas = [(k, sum(v["ms"]) / len(v["ms"])) for k, v in por.items() if len(v["ms"]) >= 3]
    lentas = sorted((x for x in lentas if x[1] >= 3000), key=lambda x: -x[1])[:2]
    if lentas:
        linhas.append("Demoram: " + ", ".join(f"{k} (média {_segundos(m)})" for k, m in lentas) + ".")
    if not ruins and not falhas:
        linhas.append("Nenhuma falha no período.")
    return "[done] " + " ".join(linhas)


def _falhas(p: dict) -> str:
    es, rotulo = _entradas(p.get("period"))
    if not es:
        return _sem_dados(rotulo)
    try:
        n = max(1, min(25, int(p.get("count") or 8)))
    except (TypeError, ValueError):
        n = 8
    grupos: dict[tuple[str, str], dict] = {}
    for e in es:
        if _status(e) != "failed":
            continue
        chave = (str(e["tool"]), _motivo(e))
        g = grupos.setdefault(chave, {"n": 0, "ultima": e["ts"]})
        g["n"] += 1
        g["ultima"] = e["ts"]
    if not grupos:
        return f"[done] Nenhuma falha {rotulo}. 👍"
    ordenados = sorted(grupos.items(), key=lambda kv: kv[1]["ultima"], reverse=True)[:n]
    linhas = []
    for (tool, motivo), g in ordenados:
        hora = str(g["ultima"])[11:16]
        linhas.append(f"{hora} {tool}" + (f" ×{g['n']}" if g["n"] > 1 else "") + (f": {motivo}" if motivo else ""))
    total = sum(g["n"] for g in grupos.values())
    return f"[done] {total} falhas {rotulo}: " + " | ".join(linhas)


def _lentas(p: dict) -> str:
    es, rotulo = _entradas(p.get("period") or "semana")
    tempos: dict[str, list[float]] = {}
    for e in es:
        if isinstance(e.get("ms"), (int, float)):
            tempos.setdefault(str(e["tool"]), []).append(float(e["ms"]))
    medias = [(k, sum(v) / len(v), max(v), len(v)) for k, v in tempos.items() if len(v) >= 3]
    if not medias:
        return (f"[done] Ainda não há dados de tempo suficientes {rotulo} "
                "(preciso de pelo menos 3 usos de uma ferramenta).")
    medias.sort(key=lambda x: -x[1])
    return (f"[done] Ferramentas mais lentas {rotulo}: "
            + "; ".join(f"{k} média {_segundos(m)} (máx {_segundos(mx)}, {n} usos)" for k, m, mx, n in medias[:6]) + ".")


def _pasta_tamanho(pasta: Path, limite_arquivos: int = 20000) -> int:
    total = n = 0
    try:
        for f in pasta.rglob("*"):
            n += 1
            if n > limite_arquivos:
                break
            try:
                if f.is_file():
                    total += f.stat().st_size
            except OSError:
                pass
    except OSError:
        pass
    return total


def _mb(b: float) -> str:
    return f"{b / 1024 / 1024:.1f}".replace(".", ",") + " MB"


def _saude(_p: dict) -> str:
    avisos, infos = [], []
    try:
        from core import settings_tools as S
        infos.append(f"versão {S.app_version()}")
        chaves = S.api_key_status()
        faltam = [n for n, ok in chaves if not ok]
        gemini = dict(chaves).get("gemini_api_key")
        if gemini is False:
            avisos.append("falta a chave do Gemini (o NEXUS não consegue conversar sem ela)")
        elif gemini:
            infos.append("chave do Gemini configurada")
        outras = [n for n in faltam if n != "gemini_api_key"]
        if outras:
            infos.append("chaves opcionais ainda vazias: " + ", ".join(outras))
        desligadas = [k for k, v in S.actuator_permissions().items() if not v]
        desligadas += [k for k, v in S.actuator_action_permissions().items() if not v and k not in desligadas]
        if desligadas:
            avisos.append("permissões desligadas no painel (o NEXUS vai recusar): " + ", ".join(sorted(desligadas)))
    except Exception:
        avisos.append("não consegui ler as configurações")
    infos.append(f"Python {platform.python_version()} em {platform.system()}")
    try:
        livre = shutil.disk_usage(_BASE).free
        (avisos if livre < 1024 ** 3 else infos).append(
            f"{'pouco espaço em disco: ' if livre < 1024 ** 3 else 'disco livre: '}{livre / 1024 ** 3:.1f} GB".replace(".", ","))
    except OSError:
        pass
    faltando = {}
    for modulo, (pacote, uso) in _PACOTES.items():
        try:
            achou = importlib.util.find_spec(modulo) is not None
        except (ImportError, ValueError):
            achou = False
        if not achou:
            faltando.setdefault(pacote, uso)
    if faltando:
        avisos.append("pacotes que faltam: " + "; ".join(f"{p} ({u})" for p, u in faltando.items())
                      + ". Rode “Instalar o NEXUS” de novo para instalar")
    try:
        tam = audit._FILE.stat().st_size
        infos.append(f"registro de ações {_mb(tam)}")
    except OSError:
        if not _registro_ligado():
            avisos.append("o registro de ações está desligado (sem ele o diagnóstico fica cego)")
    infos.append(f"memória do NEXUS {_mb(_pasta_tamanho(_BASE / 'memory'))}")
    if avisos:
        return "[done] Atenção: " + "; ".join(avisos) + ". Resto: " + "; ".join(infos) + "."
    return "[done] Tudo certo: " + "; ".join(infos) + "."


def _internet(_p: dict) -> str:
    alvo = ("generativelanguage.googleapis.com", 443)
    try:
        socket.create_connection(alvo, timeout=4).close()
    except OSError:
        try:
            socket.create_connection(("1.1.1.1", 443), timeout=4).close()
            return "[done] Tem internet, mas não consegui chegar ao Gemini agora (pode ser bloqueio, firewall ou instabilidade do serviço)."
        except OSError:
            return "[done] Sem internet no momento: não consegui conectar em nenhum dos dois endereços."
    return "[done] A internet está funcionando e o Gemini está alcançável."


def _reconexoes(_p: dict) -> str:
    from core import reconexoes
    return "[done] " + reconexoes.resumo(60)


def _quedas(_p: dict) -> str:
    from core import protecao
    return "[done] " + protecao.relatorio()


_ACOES = {"crashes": _quedas, "report": _resumo, "failures": _falhas, "slow": _lentas, "health": _saude, "internet": _internet,
          "reconnections": _reconexoes}


def diagnostico(parameters: dict, player=None) -> str:
    p = parameters or {}
    acao = str(p.get("action") or "report").strip().lower()
    fn = _ACOES.get(acao)
    if fn is None:
        return f"[failed] Ação desconhecida: {acao}. Use: {', '.join(_ACOES)}."
    try:
        return fn(p)
    except Exception as e:                      # diagnosticar nunca pode derrubar o assistente
        return f"[failed] O diagnóstico encontrou um problema ao se executar: {type(e).__name__}"


TOOL = {
    "name": "diagnostico",
    "description": (
        "Self-diagnostics of NEXUS itself, read-only. report: summary of what NEXUS did and how it went (period: "
        "hoje, ontem, semana, tudo) — counts, success rate, most used tools, tools that fail often or are slow. "
        "failures: the recent failed actions grouped with a short reason. slow: slowest tools. health: version, "
        "missing API keys (never shows keys), permissions switched off, disk space, missing packages. internet: "
        "checks connectivity to Gemini. crashes: errors contained and unexpected closings of the app (use for 'ele fechou sozinho'). reconnections: why and how often the voice connection dropped or was renewed, and whether the conversation was kept (use for 'por que ele desconecta?', 'ele caiu de novo'). Use for 'o que deu errado hoje?', 'como foi o NEXUS essa semana?', 'o que "
        "está lento?', 'o NEXUS está saudável?', 'estou sem internet?'."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": list(_ACOES)},
            "period": {"type": "STRING", "description": "hoje (default) | ontem | semana | tudo"},
            "count": {"type": "INTEGER", "description": "For failures: how many groups to list (default 8)"},
        },
        "required": [],
    },
    "handler": diagnostico,
}
