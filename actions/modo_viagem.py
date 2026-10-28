"""Modo viagem: prepara um pacote offline antes de sair, liga o modo só-local e lê a agenda sem internet. Limites em core/viagem.py."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import hibrido as H
from core import viagem as V

_MEM = Path(__file__).resolve().parent.parent / "memory"


def _json(nome, padrao):
    try:
        return json.loads((_MEM / nome).read_text(encoding="utf-8"))
    except Exception:
        return padrao


def _agenda(dias: int) -> list[dict]:
    from zoneinfo import ZoneInfo
    from core import integracoes as I
    tz = ZoneInfo("America/Sao_Paulo")
    d0 = datetime.now(tz)
    evs = I.interpretar_ics(I._baixar_ics(), d0.replace(hour=0, minute=0), d0 + timedelta(days=dias), tz)
    return [{"titulo": e["titulo"], "inicio": e["inicio"].astimezone(tz).isoformat(), "local": e.get("local", ""),
             "dia_inteiro": bool(e.get("dia_inteiro"))} for e in evs]


def _tarefas():
    d = _json("tarefas.json", [])
    d = d.get("tarefas", d) if isinstance(d, dict) else d
    return [{"titulo": str(t.get("titulo") or t.get("texto") or "")[:120], "feita": bool(t.get("feita") or t.get("concluida"))}
            for t in d if isinstance(t, dict)]


def _contatos():
    return [{"nome": str(c.get("nome")), "telefone": str(c.get("telefone") or c.get("fone") or "")}
            for c in _json("contatos.json", []) if isinstance(c, dict) and c.get("nome")]


def _documentos():
    d = _json("rag_pastas.json", {})
    pastas = d.get("pastas", d) if isinstance(d, dict) else d
    return [str(p)[:200] for p in (pastas if isinstance(pastas, list) else [])][:50]


FONTES = {"agenda": _agenda, "tarefas": _tarefas, "contatos": _contatos, "documentos": _documentos,
          "modelo_local": H.local_disponivel}


def modo_viagem(parameters: dict, fontes=None, **_kw) -> str:
    acao = str(parameters.get("action") or "status").strip().lower()
    try:
        if acao in ("prepare", "preparar"):
            r = V.preparar(fontes or FONTES, int(parameters.get("days") or 14))
            falta = ("\nAtenção: " + "; ".join(r["faltando"])) if r["faltando"] else ""
            return ("[done] Pacote de viagem salvo: " + ", ".join(f"{v} {k}" for k, v in r["itens"].items()) + "." + falta
                    + " Não baixa mapas nem clima.")
        if acao in ("on", "ligar"):
            return "[done] " + V.ativar(H.definir_modo, H.modo)
        if acao in ("off", "desligar"):
            return "[done] " + V.desativar(H.definir_modo)
        if acao in ("agenda",):
            return V.agenda_offline(str(parameters.get("period") or "hoje"))
        return V.status()
    except Exception as e:
        return f"[failed] Modo viagem: {e}"


TOOL = {
    "name": "travel_mode",
    "description": ("Travel/offline mode. action=prepare (with internet, before leaving: saves agenda, tasks, contacts, document list and checks "
                    "the local model) | on (router goes local-only) | off (restores the previous mode) | agenda (period hoje|amanha|semana, "
                    "from the saved copy) | status. Does NOT download maps or weather; live voice needs internet."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["prepare", "on", "off", "agenda", "status"]}, "days": {"type": "INTEGER"},
        "period": {"type": "STRING"}}, "required": ["action"]},
    "handler": modo_viagem,
}
