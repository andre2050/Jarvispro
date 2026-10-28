"""core/organizador_inteligente.py — organização de arquivos por regras suas + categorias (NEXUS Ultra 2026 3.9).

Diferente do organizador da área de trabalho: funciona em QUALQUER pasta (Downloads, Documentos…), aceita regras suas
("nome contém 'nota fiscal' → Documentos/Notas", "extensão .dwg → Projetos") e, sem regra, usa a categoria por tipo.
`plano` só mostra; `aplicar` mexe, sempre pelo CONFIRMAR do chamador. Nunca sobrescreve (nome livre), nunca apaga, não entra em subpastas,
pula ocultos/atalhos/recentes/em andamento, no máximo 500 arquivos por vez, e grava registro para desfazer.
Regras em config/regras_organizacao.json (pessoal, fora do GitHub).
"""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

from core import organizador as O

ARQ_REGRAS = Path(__file__).resolve().parent.parent / "config" / "regras_organizacao.json"
ARQ_REG = Path(__file__).resolve().parent.parent / "memory" / "organizacao_inteligente.json"
MAX_ARQUIVOS = 500
MAX_REGRAS = 30


def _regras(arq=None) -> list[dict]:
    try:
        d = json.loads(Path(arq or ARQ_REGRAS).read_text(encoding="utf-8"))
        return [r for r in d if isinstance(r, dict)] if isinstance(d, list) else []
    except Exception:
        return []


def _destino_seguro(s: str) -> str:
    bruto = [p.strip() for p in re.split(r"[/\\]", str(s or ""))]
    if any(p == ".." for p in bruto) or str(s or "").strip().startswith(("/", "~")) or re.match(r"^[A-Za-z]:", str(s or "").strip()):
        raise ValueError("Pasta de destino inválida (até 3 níveis, relativa, sem '..').")
    partes = [re.sub(r'[<>:"|?*]', "", p).strip(" .") for p in bruto]
    partes = [p for p in partes if p]
    if not partes or len(partes) > 3:
        raise ValueError("Pasta de destino inválida (até 3 níveis, relativa, sem '..').")
    return "/".join(p[:40] for p in partes)


def adicionar_regra(texto: str = "", extensao: str = "", pasta: str = "", arq=None) -> str:
    texto, extensao = str(texto or "").strip().lower()[:40], str(extensao or "").strip().lower().lstrip(".")[:10]
    if not texto and not extensao:
        raise ValueError("A regra precisa de um trecho do nome ou de uma extensão.")
    r = {"texto": texto, "ext": extensao, "pasta": _destino_seguro(pasta)}
    lst = _regras(arq)
    if len(lst) >= MAX_REGRAS:
        raise ValueError(f"Já há {MAX_REGRAS} regras; remova alguma.")
    lst.append(r)
    _g(ARQ_REGRAS if arq is None else Path(arq), lst)
    return f"{'nome contém “' + texto + '”' if texto else ''}{' e ' if texto and extensao else ''}{'extensão .' + extensao if extensao else ''} → {r['pasta']}"


def remover_regra(n: int, arq=None) -> bool:
    lst = _regras(arq)
    if not 1 <= n <= len(lst):
        return False
    lst.pop(n - 1)
    _g(ARQ_REGRAS if arq is None else Path(arq), lst)
    return True


def _g(arq: Path, dados) -> None:
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(arq)


def _pasta_para(arq: Path, raiz: Path, regras: list[dict]) -> tuple[Path, str]:
    nome, ext = arq.name.lower(), arq.suffix.lower().lstrip(".")
    for r in regras:
        if (not r.get("texto") or r["texto"] in nome) and (not r.get("ext") or r["ext"] == ext):
            return raiz / r["pasta"], "regra sua"
    return raiz / O.categoria(arq), "tipo"


def _raiz_valida(raiz) -> Path:
    r = Path(raiz).expanduser().resolve()
    if not r.is_dir():
        raise ValueError("Essa pasta não existe.")
    if len(r.parts) <= 2 or r == Path.home().resolve() or str(r) in ("/", "C:\\"):
        raise ValueError("Escolha uma pasta específica (Downloads, Documentos…), não a raiz nem a pasta pessoal inteira.")
    if O._base().resolve() in (r, *r.parents) and r != O._base().resolve().parent:
        if r == O._base().resolve() or O._base().resolve() in r.parents:
            raise ValueError("Essa pasta é do próprio NEXUS.")
    return r


def plano(raiz, regras_arq=None, agora: float | None = None) -> dict:
    raiz = _raiz_valida(raiz)
    agora = time.time() if agora is None else agora
    regras = _regras(regras_arq)
    mover, ficam = [], {}
    pastas_nossas = {(raiz / n).resolve() for n in O.NOMES} | {(raiz / r["pasta"].split("/")[0]).resolve() for r in regras}
    for item in sorted(raiz.iterdir(), key=lambda p: p.name.lower()):
        if item.resolve() in pastas_nossas:
            continue
        motivo = O._motivo_para_ficar(item, agora)
        if motivo:
            if motivo != "pasta":
                ficam.setdefault(motivo, []).append(item.name)
            continue
        pasta, por = _pasta_para(item, raiz, regras)
        if pasta.resolve() == item.parent.resolve():
            continue
        mover.append((item, pasta, por))
    if len(mover) > MAX_ARQUIVOS:
        ficam["além do limite"] = [m[0].name for m in mover[MAX_ARQUIVOS:]]
        mover = mover[:MAX_ARQUIVOS]
    return {"raiz": raiz, "mover": mover, "ficam": ficam}


def texto_plano(p: dict) -> str:
    if not p["mover"]:
        return f"A pasta {p['raiz'].name} já está arrumada: nada a mover."
    g: dict[str, list[str]] = {}
    for arq, pasta, _ in p["mover"]:
        g.setdefault(str(pasta.relative_to(p["raiz"])), []).append(arq.name)
    l = [f"Em {p['raiz'].name}, {len(p['mover'])} arquivo(s) iriam para:"]
    for pasta, nomes in g.items():
        l.append(f"• {pasta} ({len(nomes)}): " + ", ".join(nomes[:5]) + (f" e mais {len(nomes) - 5}" if len(nomes) > 5 else ""))
    if p["ficam"]:
        l.append("Ficam onde estão: " + "; ".join(f"{k} ({len(v)})" for k, v in p["ficam"].items()) + ".")
    return "\n".join(l)


def aplicar(p: dict, registro=None) -> str:
    movidos, criadas, falhas = [], [], []
    for arq, pasta, _ in p["mover"]:
        try:
            if not pasta.exists():
                pasta.mkdir(parents=True)
                criadas.append(str(pasta))
            dest = O._nome_livre(pasta / arq.name)
            shutil.move(str(arq), str(dest))
            movidos.append((str(arq), str(dest)))
        except Exception as e:
            falhas.append(f"{arq.name} ({getattr(e, 'strerror', None) or e})")
    if movidos:
        _g(Path(registro or ARQ_REG), {"raiz": str(p["raiz"]), "movidos": movidos, "pastas_criadas": criadas, "desfeito": False})
    msg = f"Arrumei {len(movidos)} arquivo(s) em {p['raiz'].name}." if movidos else "Não movi nada."
    if falhas:
        msg += f" {len(falhas)} ficaram: " + ", ".join(falhas[:4]) + "."
    return msg + (" Para voltar, diga “desfaz a arrumação”." if movidos else "")


def desfazer(registro=None) -> str:
    arq = Path(registro or ARQ_REG)
    try:
        reg = json.loads(arq.read_text(encoding="utf-8"))
    except Exception:
        reg = None
    if not reg or reg.get("desfeito"):
        return "Não há arrumação para desfazer."
    reg["desfeito"] = True
    ok, falta = 0, 0
    for origem, destino in reg["movidos"]:
        o, d = Path(origem), Path(destino)
        try:
            if not d.exists():
                raise FileNotFoundError
            alvo = O._nome_livre(o)
            o.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(d), str(alvo))
            ok += 1
        except Exception:
            falta += 1
    for pasta in sorted(reg.get("pastas_criadas", []), key=len, reverse=True):
        try:
            pp = Path(pasta)
            if pp.is_dir() and not any(pp.iterdir()):
                pp.rmdir()
        except Exception:
            pass
    _g(arq, reg)
    return f"Voltaram {ok} arquivo(s)." + (f" {falta} não foram achados." if falta else "")
