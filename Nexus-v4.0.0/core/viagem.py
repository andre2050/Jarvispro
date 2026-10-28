"""core/viagem.py — modo viagem / offline completo (NEXUS Ultra 2026 3.9).

ANTES de sair (com internet): `preparar()` guarda no PC um PACOTE com a agenda dos próximos dias, as tarefas, os contatos
e os nomes dos documentos indexados, e confere o que falta para funcionar sem rede (modelo local rodando, OCR, etc.).
NA VIAGEM: `ativar()` põe o roteador de modelo em "offline" (só o modelo local; nada vai para a nuvem) e `agenda_offline()` lê
a agenda do pacote. `desativar()` devolve o modo que você tinha antes.
Limites honestos: NÃO baixa mapas nem clima; a voz ao vivo é da nuvem e não funciona sem internet (offline o NEXUS responde por
texto, com o modelo local — se ele estiver instalado); a agenda do pacote é uma cópia do dia em que foi feita.
As fontes são injetadas (`agenda`, `tarefas`, `contatos`, `documentos`, `modelo_local`): nos testes são falsas.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent.parent / "memory" / "pacote_viagem.json"


def _ler(arq: Path | None = None) -> dict:
    try:
        d = json.loads(Path(arq or ARQUIVO).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _gravar(d: dict, arq: Path | None = None) -> None:
    arq = Path(arq or ARQUIVO)
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(arq)


def preparar(fontes: dict, dias: int = 14, arq: Path | None = None, agora: float | None = None) -> dict:
    """Guarda o pacote e devolve {itens, faltando}. Cada fonte que falhar vira um aviso, não um erro."""
    agora = time.time() if agora is None else agora
    pacote = _ler(arq)
    itens, faltando = {}, []
    for nome in ("agenda", "tarefas", "contatos", "documentos"):
        fn = fontes.get(nome)
        if fn is None:
            faltando.append(f"{nome}: sem fonte configurada")
            continue
        try:
            v = fn() if nome != "agenda" else fn(dias)
            itens[nome] = v if isinstance(v, list) else []
        except Exception as e:
            faltando.append(f"{nome}: {str(e)[:80]}")
    try:
        local_ok = bool(fontes["modelo_local"]()) if fontes.get("modelo_local") else False
    except Exception:
        local_ok = False
    if not local_ok:
        faltando.append("modelo local não está rodando: sem internet o NEXUS não vai conseguir responder (instale o Ollama e um modelo)")
    pacote.update(criado=agora, dias=dias, **{k: v for k, v in itens.items()})
    pacote["modelo_local_ok"] = local_ok
    _gravar(pacote, arq)
    return {"itens": {k: len(v) for k, v in itens.items()}, "faltando": faltando, "modelo_local": local_ok}


def idade_h(arq: Path | None = None, agora: float | None = None) -> float | None:
    c = _ler(arq).get("criado")
    return None if c is None else ((time.time() if agora is None else agora) - c) / 3600


def ativar(definir_modo, modo_atual, arq: Path | None = None) -> str:
    """Põe o roteador em 'offline' guardando o modo anterior. `definir_modo(str)` e `modo_atual()` vêm de core/hibrido."""
    d = _ler(arq)
    if d.get("viajando"):
        return "O modo viagem já está ligado."
    d["viajando"], d["modo_anterior"] = True, modo_atual()
    _gravar(d, arq)
    definir_modo("offline")
    return "Modo viagem ligado: só o modelo local será usado (nada vai para a nuvem)."


def desativar(definir_modo, arq: Path | None = None) -> str:
    d = _ler(arq)
    if not d.get("viajando"):
        return "O modo viagem não estava ligado."
    anterior = d.get("modo_anterior") or "auto"
    d["viajando"] = False
    _gravar(d, arq)
    definir_modo(anterior)
    return f"Modo viagem desligado; voltei ao modo {anterior}."


def viajando(arq: Path | None = None) -> bool:
    return bool(_ler(arq).get("viajando"))


def agenda_offline(periodo: str = "hoje", agora: datetime | None = None, arq: Path | None = None) -> str:
    """Lê a agenda do pacote. `periodo`: hoje | amanha | semana. Cada evento guardado é {titulo, inicio (ISO), local, dia_inteiro}."""
    d = _ler(arq)
    if "agenda" not in d:
        return "Não há pacote de viagem com agenda. Prepare antes de sair, com internet."
    agora = agora or datetime.now()
    alvo = {"hoje": 0, "amanha": 1, "amanhã": 1}.get(str(periodo).lower())
    out = []
    for e in d["agenda"]:
        try:
            ini = datetime.fromisoformat(e["inicio"]).replace(tzinfo=None)
        except Exception:
            continue
        dd = (ini.date() - agora.date()).days
        if (alvo is not None and dd == alvo) or (alvo is None and 0 <= dd < 7):
            quando = "dia todo" if e.get("dia_inteiro") else ini.strftime("%H:%M")
            out.append((ini, f"{quando} {e.get('titulo', '')}" + (f" ({e['local']})" if e.get("local") else "")))
    cab = f"(cópia de {time.strftime('%d/%m %H:%M', time.localtime(d.get('criado', 0)))}) "
    if not out:
        return cab + f"Nada na agenda para {periodo}."
    return cab + f"Agenda {periodo}: " + " | ".join(t for _, t in sorted(out))


def status(arq: Path | None = None, agora: float | None = None) -> str:
    d = _ler(arq)
    if not d.get("criado"):
        return "Nenhum pacote de viagem preparado."
    h = idade_h(arq, agora)
    return (f"Pacote de {int(h)} h atrás: {len(d.get('agenda', []))} compromissos, {len(d.get('tarefas', []))} tarefas, "
            f"{len(d.get('contatos', []))} contatos, {len(d.get('documentos', []))} documentos. "
            f"Modelo local: {'ok' if d.get('modelo_local_ok') else 'NÃO está rodando'}. "
            f"Modo viagem: {'ligado' if d.get('viajando') else 'desligado'}.")
