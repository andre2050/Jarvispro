"""Auto-regeneração do Núcleo I.S.A. (NEXUS Ultra 2026 3.4): achar a falha, aplicar o remédio, conferir.

O núcleo olha, de minuto em minuto (preferência ``autoregeneracao``):

  SINAL                                         REMÉDIO (só os seguros rodam sozinhos)
  arquivo de dados estragado (*.quebrado)       restaura a última CÓPIA BOA que a própria I.S.A. guardou
                                                (só se nada novo foi gravado por cima depois)
  uma função falhando sem parar (3× em 10 min)  DISJUNTOR: pausa a função 10 min, com aviso claro, em vez de
                                                errar de novo a cada pedido; volta sozinha depois
  falta de pacote ("No module named x")         PEDE para instalar — só pacotes do requirements.txt e só
                                                depois do seu CONFIRMAR na tela
  memória do NEXUS crescendo (vazamento)        libera memória (coleta de lixo + caches)
  disco quase cheio                             apaga só o que é DO NEXUS e já venceu: pacotes de atualização
                                                baixados, cópias de segurança antigas (fica sempre as 5 últimas)
                                                e __pycache__

Cada reparo fica anotado em memory/regeneracao.json com o resultado. É assim que ela APRENDE: para a mesma
falha, o remédio que funcionou mais vezes vai primeiro (e, se a rede colaborativa estiver ligada, o que deu
certo nos outros NEXUS da sua casa também conta — ver core/rede_colaborativa.py).

Nada aqui apaga arquivo seu, mexe em outro programa ou instala algo sem perguntar.
"""
from __future__ import annotations

import gc
import json
import re
import shutil
import threading
import time
from pathlib import Path

from core import armazem

RAIZ = Path(__file__).resolve().parent.parent
MEM = armazem.PASTA_MEMORIA
ARQ = MEM / "regeneracao.json"
PASTA_COPIAS = MEM / "regeneracao_copias"
COPIA_A_CADA_S = 24 * 3600
DISJUNTOR_FALHAS = 3
DISJUNTOR_JANELA_S = 600
DISJUNTOR_PAUSA_S = 600
MAX_HISTORICO = 300
# arquivos de dados que valem uma cópia boa (pequenos e importantes)
_COPIAVEIS_MAX_BYTES = 2_000_000
_NAO_COPIAR = {"isa_series.json", "regeneracao.json", "latencia.json", "autoavaliacao.json"}

_trava = threading.RLock()
_disjuntores: dict[str, float] = {}           # função → até quando fica pausada
_falhas_recentes: dict[str, list[float]] = {}


# ── histórico e aprendizado ──────────────────────────────────────────────────
def _ler() -> dict:
    d = armazem.carregar(ARQ, {"historico": [], "placar": {}, "rede": {}, "copias": {}, "tratados": []})
    for k, v in (("historico", []), ("placar", {}), ("rede", {}), ("copias", {}), ("tratados", [])):
        d.setdefault(k, v)
    return d


def assinatura(texto: str) -> str:
    """A 'cara' de uma falha, sem nada pessoal: tipo do erro + módulo, sem caminhos, números ou nomes."""
    t = str(texto or "")
    tipo = re.findall(r"\b([A-Z][A-Za-z]+(?:Error|Exception))\b", t)
    mod = re.search(r"No module named ['\"]([\w.]+)", t)
    if mod:
        return f"ModuleNotFoundError:{mod.group(1).split('.')[0]}"
    if t.startswith("arquivo estragado") or ".quebrado" in t:
        return "ArquivoEstragado"
    if t.startswith("funcao:"):
        return "FuncaoFalhando"
    base = tipo[-1] if tipo else re.sub(r"[^a-z]+", "_", armazem.norm(t)[:40]).strip("_") or "desconhecida"
    return base


def ordem_remedios(sig: str, candidatos: list[str], d: dict | None = None) -> list[str]:
    """Os remédios para esta falha, do que mais funcionou para o que menos (local pesa 2×, rede 1×)."""
    d = d or _ler()

    def nota(rem: str) -> float:
        loc = d["placar"].get(f"{sig}|{rem}", [0, 0])
        rede = d["rede"].get(f"{sig}|{rem}", [0, 0])
        ok, ruim = 2 * loc[0] + rede[0], 2 * loc[1] + rede[1]
        return (ok + 1) / (ok + ruim + 2)                      # Laplace: remédio novo começa em 0,5
    return sorted(candidatos, key=lambda r: -nota(r))


def _anotar(sig: str, remedio: str, ok: bool, detalhe: str) -> None:
    with _trava:
        d = _ler()
        d["historico"] = (d["historico"] + [{"t": time.time(), "falha": sig, "remedio": remedio, "ok": ok,
                                             "detalhe": str(detalhe)[:200]}])[-MAX_HISTORICO:]
        par = d["placar"].setdefault(f"{sig}|{remedio}", [0, 0])
        par[0 if ok else 1] += 1
        armazem.salvar(ARQ, d)
    try:
        from core import isa
        isa.registrar("sistema", f"Auto-regeneração: {REMEDIOS[remedio][0]}" if remedio in REMEDIOS else remedio,
                      ("✔ " if ok else "✖ ") + str(detalhe)[:200], origem="isa")
    except Exception:
        pass


# ── cópias boas ──────────────────────────────────────────────────────────────
def guardar_copias(agora: float | None = None, pasta_mem: Path | None = None) -> int:
    """Uma vez por dia, copia os .json de dados que estão ÍNTEGROS. Devolve quantos copiou."""
    agora = agora or time.time()
    pasta_mem = pasta_mem or MEM
    destino = pasta_mem / PASTA_COPIAS.name
    d = _ler()
    n = 0
    for arq in pasta_mem.glob("*.json"):
        if arq.name in _NAO_COPIAR or arq.stat().st_size > _COPIAVEIS_MAX_BYTES:
            continue
        if agora - float(d["copias"].get(arq.name, 0)) < COPIA_A_CADA_S:
            continue
        try:
            json.loads(arq.read_text(encoding="utf-8"))
        except Exception:
            continue                                            # estragado: nunca vira "cópia boa"
        destino.mkdir(parents=True, exist_ok=True)
        shutil.copy2(arq, destino / arq.name)
        d["copias"][arq.name] = agora
        n += 1
    if n:
        armazem.salvar(ARQ, d)
    return n


def _restaurar_copia(quebrado: Path) -> tuple[bool, str]:
    original = quebrado.with_name(quebrado.name.removesuffix(".quebrado"))
    copia = quebrado.parent / PASTA_COPIAS.name / original.name
    if original.exists():
        return False, f"{original.name} já foi regravado depois da falha; a cópia antiga não foi usada"
    if not copia.exists():
        return False, f"não há cópia boa de {original.name}"
    try:
        json.loads(copia.read_text(encoding="utf-8"))
        shutil.copy2(copia, original)
        return True, f"{original.name} restaurado da cópia boa"
    except Exception as e:                                      # noqa: BLE001
        return False, f"não consegui restaurar {original.name} ({e})"


# ── disjuntor ────────────────────────────────────────────────────────────────
def falha_de_funcao(nome: str, agora: float | None = None) -> bool:
    """Anota uma falha da função. True se o disjuntor acabou de desarmar (pausou a função)."""
    agora = agora or time.time()
    with _trava:
        lista = [t for t in _falhas_recentes.get(nome, []) if agora - t < DISJUNTOR_JANELA_S] + [agora]
        _falhas_recentes[nome] = lista
        if len(lista) >= DISJUNTOR_FALHAS and _disjuntores.get(nome, 0) <= agora:
            _disjuntores[nome] = agora + DISJUNTOR_PAUSA_S
            _falhas_recentes[nome] = []
            desarmou = True
        else:
            desarmou = False
    if desarmou:
        _anotar("FuncaoFalhando", "disjuntor", True, f"{nome} pausada por {DISJUNTOR_PAUSA_S // 60} min")
    return desarmou


def acerto_de_funcao(nome: str) -> None:
    with _trava:
        _falhas_recentes.pop(nome, None)


def bloqueada(nome: str, agora: float | None = None) -> str | None:
    """A mensagem para uma função com o disjuntor desarmado; None = liberada."""
    agora = agora or time.time()
    with _trava:
        ate = _disjuntores.get(nome, 0)
        if ate <= agora:
            _disjuntores.pop(nome, None)
            return None
    falta = int((ate - agora) // 60) + 1
    return (f"[failed] A função '{nome}' falhou várias vezes seguidas e a auto-regeneração da I.S.A. a pausou "
            f"por mais {falta} min para não errar de novo. Diga isso ao usuário em uma frase; ela volta sozinha.")


def disjuntores() -> dict[str, int]:
    agora = time.time()
    with _trava:
        return {k: int(v - agora) for k, v in _disjuntores.items() if v > agora}


# ── dependências (sempre com confirmação) ────────────────────────────────────
def pacote_do_requirements(modulo: str) -> str:
    """O nome no requirements.txt do pacote que fornece ``modulo`` ('' se não está lá: não instala)."""
    apelidos = {"cv2": "opencv-python", "PIL": "pillow", "docx": "python-docx", "pptx": "python-pptx",
                "yaml": "pyyaml", "win32api": "pywin32", "win32con": "pywin32", "bs4": "beautifulsoup4",
                "google": "google-genai", "sklearn": "scikit-learn", "duckduckgo_search": "ddgs"}
    nome = apelidos.get(modulo, modulo)
    try:
        linhas = (RAIZ / "requirements.txt").read_text(encoding="utf-8").splitlines()
    except Exception:
        return ""
    for l in linhas:
        pkg = re.split(r"[<>=;\[\s#]", l.strip(), maxsplit=1)[0]
        if pkg and armazem.norm(pkg).replace("_", "-") == armazem.norm(nome).replace("_", "-"):
            return pkg
    return ""


def _instalar(pacote: str) -> str:
    import subprocess
    import sys
    r = subprocess.run([sys.executable, "-m", "pip", "install", pacote], capture_output=True, text=True,
                       timeout=600)
    ok = r.returncode == 0
    _anotar(f"ModuleNotFoundError:{pacote}", "instalar_dependencia", ok,
            f"pip install {pacote}: " + ("ok" if ok else (r.stderr or r.stdout)[-160:]))
    return f"{pacote} {'instalado — reinicie o NEXUS' if ok else 'não instalou'}."


# ── limpeza do que é do NEXUS ────────────────────────────────────────────────
def limpar_sobras(raiz: Path | None = None, manter_backups: int = 5) -> tuple[int, int]:
    """(arquivos apagados, bytes liberados) — só pacotes de atualização, backups antigos e __pycache__."""
    raiz = raiz or RAIZ
    alvos: list[Path] = []
    upd = raiz / "updates"
    if upd.is_dir():
        alvos += [p for p in upd.glob("*.zip") if time.time() - p.stat().st_mtime > 7 * 86400]
    bk = raiz / "memory" / "backups"
    if bk.is_dir():
        zips = sorted(bk.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
        alvos += zips[manter_backups:]
    for pc in raiz.rglob("__pycache__"):
        if ".venv" not in pc.parts and "venv" not in pc.parts:
            alvos += list(pc.glob("*.pyc"))
    n = liberados = 0
    for p in alvos:
        try:
            tam = p.stat().st_size
            p.unlink()
            n += 1
            liberados += tam
        except Exception:
            continue
    return n, liberados


# ── o catálogo de remédios ───────────────────────────────────────────────────
def _rem_liberar_memoria(_ctx) -> tuple[bool, str]:
    n = gc.collect()
    try:
        from core import cache_respostas
        cache_respostas.limpar()
    except Exception:
        pass
    return True, f"memória liberada ({n} objetos) e caches limpos"


def _rem_limpar(_ctx) -> tuple[bool, str]:
    n, b = limpar_sobras()
    return n > 0, f"{n} arquivo(s) do NEXUS apagado(s), {b / 1e6:.0f} MB liberados" if n else "nada do NEXUS para limpar"


def _rem_restaurar(ctx) -> tuple[bool, str]:
    return _restaurar_copia(ctx["arquivo"])


REMEDIOS: dict[str, tuple[str, object, bool]] = {
    # id: (descrição, função(ctx) -> (ok, detalhe), precisa de confirmação?)
    "restaurar_copia": ("Restaurar a cópia boa do arquivo", _rem_restaurar, False),
    "disjuntor": ("Pausar a função que falha sem parar", None, False),
    "liberar_memoria": ("Liberar memória do NEXUS", _rem_liberar_memoria, False),
    "limpar_sobras": ("Apagar sobras do NEXUS (atualizações e backups antigos)", _rem_limpar, False),
    "instalar_dependencia": ("Instalar um pacote que falta", None, True),
}


# ── olhar e reparar ──────────────────────────────────────────────────────────
def _quebrados(pasta_mem: Path) -> list[Path]:
    return sorted(pasta_mem.glob("*.quebrado"))


def _ja_instalado(modulo: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(modulo) is not None
    except Exception:
        return False


def _modulos_faltando(arq_falhas: Path | None = None) -> list[str]:
    try:
        from core import protecao
        arq = arq_falhas or protecao.ARQ_FALHAS
        texto = arq.read_text(encoding="utf-8", errors="replace")[-60_000:]
    except Exception:
        return []
    return sorted(set(re.findall(r"No module named ['\"]([\w]+)", texto)))


def verificar(pasta_mem: Path | None = None, previsoes: list[dict] | None = None,
              confirmar=None) -> list[str]:
    """Uma rodada: acha os sinais, aplica os remédios seguros e devolve o que foi feito (frases curtas).

    ``confirmar(titulo, detalhe, fn)`` é usado para o que precisa do seu sim (instalar pacote); sem ele,
    isso só vira sugestão."""
    pasta_mem = pasta_mem or MEM
    feito: list[str] = []
    d = _ler()
    tratados = set(d["tratados"])

    for q in _quebrados(pasta_mem):
        chave = f"{q.name}:{int(q.stat().st_mtime)}"
        if chave in tratados:
            continue
        ok, det = _restaurar_copia(q)
        _anotar("ArquivoEstragado", "restaurar_copia", ok, det)
        tratados.add(chave)
        if ok:
            feito.append(det)

    for p in previsoes or []:
        if p.get("chave") == "vazamento":
            for rem in ordem_remedios("Vazamento", ["liberar_memoria"]):
                ok, det = REMEDIOS[rem][1](None)
                _anotar("Vazamento", rem, ok, det)
                feito.append(det)
        if p.get("chave") == "disco" and p.get("gravidade", 0) >= 3:
            ok, det = _rem_limpar(None)
            _anotar("DiscoCheio", "limpar_sobras", ok, det)
            if ok:
                feito.append(det)

    for mod in _modulos_faltando():
        chave = f"pip:{mod}"
        if chave in tratados or _ja_instalado(mod):
            continue
        pacote = pacote_do_requirements(mod)
        if not pacote:
            tratados.add(chave)                                 # fora do requirements: nunca instala sozinho
            continue
        if confirmar:
            if not confirmar(f"Instalar o pacote {pacote}", f"O NEXUS precisa de “{mod}” e ele não está instalado.",
                             lambda p=pacote: _instalar(p)):
                continue                                        # já havia outra confirmação na tela: tenta depois
            feito.append(f"pedi confirmação para instalar {pacote}")
        else:
            feito.append(f"falta o pacote {pacote}: peça 'roda a auto-regeneração' para eu oferecer a instalação")
        tratados.add(chave)

    with _trava:
        d2 = _ler()
        d2["tratados"] = sorted(tratados)[-200:]
        armazem.salvar(ARQ, d2)
    return feito


def relatorio() -> dict:
    d = _ler()
    hist = d["historico"]
    return {"reparos": len(hist), "ok": sum(1 for h in hist if h["ok"]),
            "ultimos": hist[-8:], "disjuntores": disjuntores(), "aprendidos": len(d["placar"]),
            "da_rede": len(d["rede"]), "copias": len(d["copias"])}


def resumo_texto() -> str:
    r = relatorio()
    partes = [f"Auto-regeneração: {r['reparos']} reparo(s) anotado(s), {r['ok']} com sucesso; "
              f"{r['aprendidos']} combinação(ões) falha→remédio aprendida(s)"
              + (f", {r['da_rede']} vinda(s) da rede" if r["da_rede"] else "") + "."]
    if r["disjuntores"]:
        partes.append("Pausadas agora: " + ", ".join(f"{k} ({v // 60 + 1} min)" for k, v in r["disjuntores"].items()) + ".")
    if r["ultimos"]:
        partes.append("Últimos: " + " | ".join(f"{time.strftime('%d/%m %H:%M', time.localtime(h['t']))} "
                                               f"{'✔' if h['ok'] else '✖'} {h['detalhe']}" for h in r["ultimos"][-4:]))
    return " ".join(partes)
