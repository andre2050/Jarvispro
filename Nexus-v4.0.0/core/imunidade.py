"""core/imunidade.py — imunidade a problemas conhecidos (NEXUS Ultra 2026 4.0).

A auto-regeneração da 3.4 consertava depois que a falha acontecia. Aqui o NEXUS GUARDA a "digital" de cada falha (assinatura sem
números, caminhos e endereços), conta quantas vezes ela volta e o que resolveu. Quando uma falha já conhecida tem uma VACINA que deu
certo, ela é aplicada ANTES da próxima vez (ex.: espera de rede antes de tentar de novo, liberar memória antes de estourar).
Falhas desconhecidas e repetidas viram um RELATÓRIO de bug (arquivo, linha, quantas vezes): o NEXUS nunca reescreve o próprio código
sozinho. Vacinas só usam remédios seguros e reversíveis (os do catálogo da auto-regeneração); instalar pacote continua pedindo seu sim.
Dados em memory/imunidade.json (local, fora do GitHub). Nunca levanta erro para quem chama.
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent.parent / "memory" / "imunidade.json"
MAX_ASSINATURAS = 200
REINCIDENTE_N = 3                 # vezes em 24 h para virar relatório de bug
JANELA_S = 24 * 3600
_trava = threading.Lock()

# padrão no texto da falha → (id da vacina, tipo, explicação). tipo: "remedio" (função segura do catálogo), "espera" (segundos), "aviso"
VACINAS: list[tuple[re.Pattern, str, str, str]] = [
    (re.compile(r"MemoryError|out of memory|Cannot allocate memory", re.I), "liberar_memoria", "remedio", "Pouca memória: libero caches antes de tentar de novo."),
    (re.compile(r"JSONDecodeError|Expecting value|Extra data|Unterminated string", re.I), "restaurar_copia", "remedio", "Arquivo de dados estragado: restauro a cópia boa."),
    (re.compile(r"ConnectionError|Timeout|timed out|getaddrinfo|Temporary failure in name resolution|Network is unreachable|SSLError|ConnectionReset", re.I),
     "espera_rede", "espera", "Rede instável: espero e tento de novo com intervalo crescente."),
    (re.compile(r"database is locked|PermissionError|being used by another process|WinError 32|Errno 13", re.I),
     "espera_arquivo", "espera", "Arquivo em uso por outro programa: espero um instante e tento de novo."),
    (re.compile(r"No module named", re.I), "instalar_dependencia", "aviso", "Falta um pacote: só instalo com o seu sim (veja a sugestão da auto-regeneração)."),
    (re.compile(r"No space left|Errno 28|disk full", re.I), "limpar_sobras", "remedio", "Disco cheio: apago só sobras do NEXUS (atualizações e backups antigos)."),
]
_ESPERAS = {"espera_rede": (5, 15, 45, 120), "espera_arquivo": (1, 3, 8)}
_REMEDIOS_SEGUROS = {"liberar_memoria", "restaurar_copia", "limpar_sobras"}


def assinatura(texto: str) -> str:
    """Digital da falha: tipo do erro + mensagem sem números/caminhos/endereços/hex."""
    linhas = [l.strip() for l in str(texto or "").strip().splitlines() if l.strip()]
    ultima = linhas[-1] if linhas else "desconhecida"
    s = re.sub(r"0x[0-9a-fA-F]+", "0x?", ultima)
    s = re.sub(r"[A-Za-z]:\\[^\s'\"]+|/[\w./-]{3,}", "<caminho>", s)
    s = re.sub(r"https?://\S+", "<url>", s)
    s = re.sub(r"\d+", "N", s)
    return s[:120]


def onde(texto: str) -> str:
    """'arquivo.py:linha' do último quadro do traceback que é do NEXUS (vazio se não achar)."""
    achados = re.findall(r'File "([^"]+)", line (\d+)', str(texto or ""))
    for arq, linha in reversed(achados):
        a = arq.replace("\\", "/")
        if "site-packages" in a or "/lib/python" in a or "<frozen" in a:
            continue
        return f"{a.rsplit('/', 1)[-1]}:{linha}"
    return ""


def _ler(arq=None) -> dict:
    try:
        d = json.loads(Path(arq or ARQUIVO).read_text(encoding="utf-8"))
        if isinstance(d, dict) and isinstance(d.get("falhas"), dict):
            return d
    except Exception:
        pass
    return {"falhas": {}}


def _gravar(d: dict, arq=None) -> None:
    arq = Path(arq or ARQUIVO)
    arq.parent.mkdir(parents=True, exist_ok=True)
    if len(d["falhas"]) > MAX_ASSINATURAS:
        antigas = sorted(d["falhas"], key=lambda k: d["falhas"][k]["ultima"])[:len(d["falhas"]) - MAX_ASSINATURAS]
        for k in antigas:
            d["falhas"].pop(k, None)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    tmp.replace(arq)


def vacina_para(texto: str) -> tuple[str, str, str] | None:
    for rx, vid, tipo, expl in VACINAS:
        if rx.search(str(texto or "")):
            return vid, tipo, expl
    return None


def registrar(texto: str, origem: str = "", agora: float | None = None, arq=None) -> dict | None:
    """Anota uma falha. Devolve o registro da assinatura (ou None se der erro)."""
    try:
        agora = time.time() if agora is None else agora
        sig = assinatura(texto)
        v = vacina_para(texto)
        with _trava:
            d = _ler(arq)
            f = d["falhas"].setdefault(sig, {"n": 0, "primeira": agora, "ultima": agora, "recentes": [], "vacina": v[0] if v else "",
                                             "ok": 0, "ruim": 0, "onde": "", "origem": ""})
            f["n"] += 1
            f["ultima"] = agora
            f["recentes"] = [t for t in f["recentes"] if agora - t < JANELA_S][-20:] + [agora]
            f["onde"] = onde(texto) or f["onde"]
            f["origem"] = str(origem)[:60] or f["origem"]
            if v and not f["vacina"]:
                f["vacina"] = v[0]
            _gravar(d, arq)
            return dict(f, assinatura=sig)
    except Exception:
        return None


def resultado(sig: str, ok: bool, arq=None) -> None:
    """Conta se a vacina funcionou (a falha não voltou logo depois / o remédio deu certo)."""
    try:
        with _trava:
            d = _ler(arq)
            f = d["falhas"].get(sig)
            if f:
                f["ok" if ok else "ruim"] += 1
                _gravar(d, arq)
    except Exception:
        pass


def confiavel(f: dict) -> bool:
    """A vacina merece ser aplicada ANTES: já foi usada, deu certo mais vezes do que falhou."""
    return bool(f.get("vacina")) and f.get("ok", 0) >= 1 and f["ok"] > f.get("ruim", 0) * 2


def antes_de(sinal: str, arq=None) -> dict | None:
    """Pergunta 'tem vacina para o que costuma dar errado aqui?'. `sinal` = trecho da assinatura ou da origem.
    Devolve {"vacina","tipo","espera_s"|None,"motivo"} só para vacinas confiáveis e seguras; senão None."""
    s = str(sinal or "").lower()
    for sig, f in _ler(arq)["falhas"].items():
        if (s and (s in sig.lower() or s in str(f.get("origem", "")).lower())) and confiavel(f):
            vid = f["vacina"]
            v = next((x for x in VACINAS if x[1] == vid), None)
            if not v or (v[2] == "remedio" and vid not in _REMEDIOS_SEGUROS) or v[2] == "aviso":
                continue
            espera = _ESPERAS.get(vid, (None,))[0] if v[2] == "espera" else None
            return {"vacina": vid, "tipo": v[2], "espera_s": espera, "motivo": v[3]}
    return None


def espera_crescente(vacina: str, tentativa: int) -> float | None:
    seq = _ESPERAS.get(vacina)
    if not seq:
        return None
    return float(seq[min(max(tentativa, 1) - 1, len(seq) - 1)])


def tratar(texto: str, origem: str = "", remedios: dict | None = None, ctx: dict | None = None,
           agora: float | None = None, arq=None) -> str:
    """Registra e, se houver vacina SEGURA com função disponível em `remedios`, aplica. Devolve a frase do que fez ('' = nada)."""
    f = registrar(texto, origem, agora, arq)
    if not f:
        return ""
    v = vacina_para(texto)
    if not v:
        return ""
    vid, tipo, expl = v
    if tipo == "remedio" and vid in _REMEDIOS_SEGUROS and remedios and vid in remedios:
        try:
            ok, det = remedios[vid](ctx or {})
        except Exception as e:
            ok, det = False, str(e)[:80]
        resultado(f["assinatura"], bool(ok), arq)
        return f"vacina “{vid}”: {det}"
    return expl if f["n"] <= 1 or tipo == "aviso" else ""


def bugs_reincidentes(agora: float | None = None, arq=None) -> list[dict]:
    """Falhas SEM vacina que se repetiram {REINCIDENTE_N}+ vezes em 24 h: viram relatório (arquivo:linha, vezes)."""
    agora = time.time() if agora is None else agora
    out = []
    for sig, f in _ler(arq)["falhas"].items():
        rec = [t for t in f["recentes"] if agora - t < JANELA_S]
        if len(rec) >= REINCIDENTE_N and not f.get("vacina"):
            out.append({"assinatura": sig, "vezes_24h": len(rec), "onde": f.get("onde", ""), "origem": f.get("origem", "")})
    return sorted(out, key=lambda x: -x["vezes_24h"])[:10]


def relatorio(agora: float | None = None, arq=None) -> str:
    d = _ler(arq)["falhas"]
    if not d:
        return "Nenhuma falha registrada ainda: nada a vacinar."
    imunes = [(s, f) for s, f in d.items() if confiavel(f)]
    top = sorted(d.items(), key=lambda kv: -kv[1]["n"])[:3]
    l = [f"{len(d)} tipo(s) de falha conhecidos; {len(imunes)} com vacina que funciona."]
    l.append("Mais comuns: " + "; ".join(f"“{s[:60]}” ×{f['n']}" for s, f in top) + ".")
    bugs = bugs_reincidentes(agora, arq)
    if bugs:
        l.append("Sem remédio e voltando (precisam de correção no código): " + "; ".join(
            f"“{b['assinatura'][:50]}” ×{b['vezes_24h']}" + (f" em {b['onde']}" if b["onde"] else "") for b in bugs[:3]) + ".")
    return " ".join(l)


def esquecer(arq=None) -> None:
    _gravar({"falhas": {}}, arq)


def saude() -> tuple[bool, str]:
    d = _ler()["falhas"]
    return True, f"{len(d)} assinatura(s), {sum(1 for f in d.values() if confiavel(f))} vacina(s) confiável(is)"
