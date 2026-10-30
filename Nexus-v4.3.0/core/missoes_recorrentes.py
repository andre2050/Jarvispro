"""core/missoes_recorrentes.py — missões agendadas (NEXUS Ultra 2026 3.9): "toda sexta, monte o resumo da semana".

Guarda só a META e o horário; cada disparo cria uma missão nova pelo mesmo caminho de sempre (plano, simulação, aprovação dos
passos sensíveis, orçamento, auditoria). Nada fica "pré-aprovado" por ser recorrente: se o plano de sexta tiver passo que
envia ou apaga, ele pergunta de novo naquela sexta (a menos que você tenha criado uma regra em Aprovações).
Se o PC estava desligado na hora, dispara ao ligar, até 6 horas depois; passou disso, pula aquele dia. Máx. 10 agendas.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime
from pathlib import Path

from core import rotinas_conversa as RC

ARQUIVO = Path(__file__).resolve().parent.parent / "config" / "missoes_recorrentes.json"
MAX_AGENDAS = 10
JANELA_ATRASO_H = 6
_HORA = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


class ErroAgenda(Exception):
    pass


def _ler(arq: Path | None = None) -> list[dict]:
    try:
        d = json.loads(Path(arq or ARQUIVO).read_text(encoding="utf-8"))
        return [x for x in d if isinstance(x, dict) and x.get("id")] if isinstance(d, list) else []
    except Exception:
        return []


def _gravar(itens: list[dict], arq: Path | None = None) -> None:
    arq = Path(arq or ARQUIVO)
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(itens, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(arq)


def adicionar(meta: str, dias, hora: str, orcamento: dict | None = None, ensaiar: bool = False, arq: Path | None = None) -> dict:
    meta = re.sub(r"\s+", " ", str(meta or "")).strip()[:400]
    if len(meta) < 8:
        raise ErroAgenda("Diga a meta completa da missão.")
    d = RC.parse_dias(dias)
    if not d:
        raise ErroAgenda("Não entendi os dias (ex.: sexta, dias úteis, todo dia).")
    m = _HORA.match(str(hora or "").strip())
    if not m:
        raise ErroAgenda("A hora deve ser como 08:30.")
    itens = _ler(arq)
    if len(itens) >= MAX_AGENDAS:
        raise ErroAgenda(f"Já há {MAX_AGENDAS} missões agendadas; remova uma.")
    from core import missoes as M
    item = {"id": uuid.uuid4().hex[:6], "meta": meta, "dias": d, "hora": f"{int(m.group(1)):02d}:{m.group(2)}", "ativa": True,
            "orcamento": M.limpar_orcamento(orcamento), "ensaiar": bool(ensaiar), "ultima": ""}
    itens.append(item)
    _gravar(itens, arq)
    return item


def remover(rid: str, arq: Path | None = None) -> bool:
    itens = _ler(arq)
    novo = [i for i in itens if i["id"] != rid]
    if len(novo) == len(itens):
        return False
    _gravar(novo, arq)
    return True


def pausar(rid: str, ativa: bool, arq: Path | None = None) -> bool:
    itens = _ler(arq)
    for i in itens:
        if i["id"] == rid:
            i["ativa"] = bool(ativa)
            _gravar(itens, arq)
            return True
    return False


def listar(arq: Path | None = None) -> list[dict]:
    return _ler(arq)


def texto(itens: list[dict]) -> str:
    if not itens:
        return "Nenhuma missão agendada."
    nomes = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
    return " | ".join(f"{i['id']}: {'/'.join(nomes[d] for d in i['dias'])} {i['hora']} “{i['meta'][:40]}”"
                      + ("" if i["ativa"] else " (pausada)") for i in itens)


def devidas(agora: datetime | None = None, arq: Path | None = None) -> list[dict]:
    agora = agora or datetime.now()
    hoje = agora.strftime("%Y-%m-%d")
    out = []
    for i in _ler(arq):
        if not i.get("ativa") or i.get("ultima") == hoje or agora.weekday() not in i["dias"]:
            continue
        h, mi = (int(x) for x in i["hora"].split(":"))
        alvo = agora.replace(hour=h, minute=mi, second=0, microsecond=0)
        atraso_h = (agora - alvo).total_seconds() / 3600
        if 0 <= atraso_h <= JANELA_ATRASO_H:
            out.append(i)
    return out


def disparar(criar, agora: datetime | None = None, arq: Path | None = None) -> list[tuple[str, str]]:
    """Cria as missões devidas com `criar(meta, orcamento, ensaiar) -> dict`. Marca o dia ANTES de criar (uma falha não repete
    a cada minuto). Devolve [(id da agenda, estado ou erro)]."""
    agora = agora or datetime.now()
    res = []
    itens = _ler(arq)
    for dev in devidas(agora, arq):
        for i in itens:
            if i["id"] == dev["id"]:
                i["ultima"] = agora.strftime("%Y-%m-%d")
        _gravar(itens, arq)
        try:
            m = criar(dev["meta"], dev.get("orcamento") or None, bool(dev.get("ensaiar")))
            res.append((dev["id"], m.get("estado", "?") if isinstance(m, dict) else "?"))
        except Exception as e:
            res.append((dev["id"], f"erro: {e}"))
    return res
