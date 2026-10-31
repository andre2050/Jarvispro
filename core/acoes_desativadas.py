"""Ações desativadas por você (4.5.0) e sugestão de desativar as que vivem falhando.

Uma ação desativada não é carregada no próximo início: o modelo deixa de enxergá-la e ela deixa de gastar
tokens e de dar erro. O arquivo continua na pasta actions/; reativar traz tudo de volta.

Nunca podem ser desativadas as ações de segurança, de configuração e de diagnóstico (PROTEGIDAS).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

_ARQ = Path(__file__).resolve().parent.parent / "memory" / "acoes_desativadas.json"

PROTEGIDAS = frozenset({
    "tool_load", "manage_actions", "nexus_guide", "diagnostico", "guardrails", "privacidade", "auditoria",
    "approvals", "system_update", "memory_bank", "undo", "trace", "immunity",
})
_NOME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def carregar(arquivo: Path | None = None) -> list[str]:
    try:
        d = json.loads(Path(arquivo or _ARQ).read_text(encoding="utf-8"))
        return sorted({str(x) for x in d.get("desativadas", []) if isinstance(x, str) and _NOME.match(x)})
    except Exception:
        return []


def _gravar(nomes, arquivo: Path | None) -> None:
    arq = Path(arquivo or _ARQ)
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps({"desativadas": sorted(set(nomes))}, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(arq)


def desativar(nome: str, arquivo: Path | None = None) -> str:
    nome = (nome or "").strip()
    if not _NOME.match(nome):
        raise ValueError("Nome de ação inválido.")
    if nome in PROTEGIDAS:
        raise ValueError(f"“{nome}” é de segurança ou configuração e não pode ser desativada.")
    atuais = carregar(arquivo)
    if nome not in atuais:
        _gravar(atuais + [nome], arquivo)
    return nome


def reativar(nome: str, arquivo: Path | None = None) -> bool:
    atuais = carregar(arquivo)
    if nome not in atuais:
        return False
    _gravar([n for n in atuais if n != nome], arquivo)
    return True


def esta_desativada(nome: str, arquivo: Path | None = None) -> bool:
    return nome in carregar(arquivo)


def suspeitas(entradas, dias: int = 14, minimo: int = 5, taxa: float = 0.7, agora: datetime | None = None) -> list[dict]:
    """Ações que falharam em ao menos `taxa` das vezes, com no mínimo `minimo` chamadas nos últimos `dias` dias."""
    corte = (agora or datetime.now()) - timedelta(days=dias)
    cont: dict[str, list[int]] = {}
    for e in entradas:
        try:
            quando = datetime.strptime(str(e.get("ts")), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if quando < corte or not e.get("tool"):
            continue
        m = re.match(r"\s*\[(done|unverified|failed)\]", str(e.get("result", "")), re.IGNORECASE)
        falhou = bool(m and m.group(1).lower() == "failed")
        c = cont.setdefault(str(e["tool"]), [0, 0])
        c[0] += 1
        c[1] += int(falhou)
    achadas = [{"nome": n, "chamadas": t, "falhas": f, "taxa": round(f / t, 2)}
               for n, (t, f) in cont.items() if t >= minimo and f / t >= taxa and n not in PROTEGIDAS]
    return sorted(achadas, key=lambda x: (-x["taxa"], -x["chamadas"]))
