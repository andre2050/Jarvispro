"""core/aprovacoes.py — aprender com as suas aprovações (NEXUS Ultra 2026 3.9).

Cada vez que você aprova ou nega um passo sensível de uma missão, o NEXUS anota (só o nome da ferramenta e da ação, nunca o
conteúdo). Depois de 5 aprovações seguidas do MESMO tipo de passo, sem nenhum "não", ele PERGUNTA: "quer que eu faça isso
sem perguntar?". Só a sua resposta cria a regra; dá para revogar a qualquer hora.
Travas que não mudam: só passos que ESCREVEM (anotar, salvar) podem virar automáticos. Apagar, mover, enviar, gastar, controlar
o PC e instalar NUNCA, por mais que você aprove. Uma regra vale só para a ferramenta+ação, e um "não" posterior a derruba.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent.parent / "config" / "aprovacoes.json"
MINIMO = 5
ADIAR_DIAS = 30
_NUNCA = {"send_message", "email_sender", "file_controller", "computer_control", "computer_use", "desktop_control",
          "shortcut_manager", "system_update", "plugin_factory", "loja_plugins", "rede_nexus", "finance"}


def _ler(arq: Path | None = None) -> dict:
    try:
        d = json.loads(Path(arq or ARQUIVO).read_text(encoding="utf-8"))
        if isinstance(d, dict):
            return {"contagem": d.get("contagem") or {}, "regras": d.get("regras") or {}, "adiadas": d.get("adiadas") or {}}
    except Exception:
        pass
    return {"contagem": {}, "regras": {}, "adiadas": {}}


def _gravar(d: dict, arq: Path | None = None) -> None:
    arq = Path(arq or ARQUIVO)
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(arq)


def assinatura(tool: str, args: dict | None) -> str:
    return f"{tool}:{str((args or {}).get('action') or '').lower()}"


def elegivel(tool: str, args: dict | None) -> bool:
    """Só passo que ESCREVE e não está na lista de nunca."""
    from core import simulacao as SIM
    return tool not in _NUNCA and SIM.efeito(tool, args) == SIM.ESCREVE


def registrar(tool: str, args: dict | None, aprovou: bool, arq: Path | None = None, agora: float | None = None) -> str | None:
    """Anota a decisão. Devolve a assinatura se AGORA vale perguntar se vira automático (uma vez só)."""
    if not elegivel(tool, args):
        return None
    d = _ler(arq)
    sig = assinatura(tool, args)
    c = d["contagem"].setdefault(sig, {"ok": 0, "nao": 0})
    if aprovou:
        c["ok"] += 1
    else:
        c["nao"] += 1
        c["ok"] = 0                              # um "não" zera a sequência
        d["regras"].pop(sig, None)               # e derruba a regra, se havia
    _gravar(d, arq)
    return sig if aprovou and sugestoes(arq, agora, so_sig=sig) else None


def sugestoes(arq: Path | None = None, agora: float | None = None, so_sig: str | None = None) -> list[str]:
    d = _ler(arq)
    agora = time.time() if agora is None else agora
    out = []
    for sig, c in d["contagem"].items():
        if so_sig and sig != so_sig:
            continue
        if c["ok"] >= MINIMO and c["nao"] == 0 and sig not in d["regras"] \
                and agora - float(d["adiadas"].get(sig, 0)) > ADIAR_DIAS * 86400:
            out.append(sig)
    return out


def aceitar(sig: str, arq: Path | None = None, agora: float | None = None) -> bool:
    d = _ler(arq)
    if sig not in d["contagem"] or sig.split(":")[0] in _NUNCA:
        return False
    d["regras"][sig] = {"desde": time.time() if agora is None else agora}
    _gravar(d, arq)
    return True


def recusar(sig: str, arq: Path | None = None, agora: float | None = None) -> None:
    d = _ler(arq)
    d["adiadas"][sig] = time.time() if agora is None else agora
    _gravar(d, arq)


def revogar(sig: str, arq: Path | None = None) -> bool:
    d = _ler(arq)
    ok = d["regras"].pop(sig, None) is not None
    if ok:
        d["contagem"][sig] = {"ok": 0, "nao": 0}
    _gravar(d, arq)
    return ok


def auto(tool: str, args: dict | None, arq: Path | None = None) -> bool:
    """O passo já tem regra de 'pode fazer sem perguntar'? Revalida a elegibilidade a cada uso."""
    if not elegivel(tool, args):
        return False
    return assinatura(tool, args) in _ler(arq)["regras"]


def regras(arq: Path | None = None) -> list[str]:
    return sorted(_ler(arq)["regras"])
