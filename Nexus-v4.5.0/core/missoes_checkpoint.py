"""core/missoes_checkpoint.py — checkpoints e replay de missões (NEXUS Ultra 4.1).

Depois de cada passo que termina, a missão guarda um CHECKPOINT: o estado de todos os passos naquele ponto. Se a missão foi para o caminho
errado, você pode VOLTAR a um checkpoint (opcionalmente trocando os argumentos de um passo) e deixar o NEXUS refazer dali em diante.
Honestidade sobre o mundo real: voltar a missão NÃO desfaz o que os passos já fizeram fora dela (arquivo movido, mensagem enviada). O
rewind lista esses passos com efeito para você decidir (e o "desfazer" da missão continua valendo para o último). Só dá para voltar com a
missão pausada, falha, concluída ou esperando você — nunca enquanto está executando.
"""
from __future__ import annotations

import time

MAX_CHECKPOINTS = 30
ESTADOS_PERMITIDOS = ("pausada", "falhou", "concluida", "aguardando", "plano_pronto", "cancelada")
_CAMPOS = ("estado", "resultado", "tentativas", "verificado")


def registrar(m: dict, passo: dict, agora: float | None = None) -> int:
    """Guarda o checkpoint depois de `passo` terminar. Devolve o número dele (1, 2, …)."""
    cps = m.setdefault("checkpoints", [])
    n = (cps[-1]["n"] + 1) if cps else 1
    cps.append({"n": n, "t": round(time.time() if agora is None else agora, 1), "apos": passo["id"], "titulo": str(passo.get("titulo", ""))[:80],
                "passos": {str(p["id"]): {"estado": p["estado"], "resultado": str(p.get("resultado", ""))[:300], "tentativas": p.get("tentativas", 0),
                                     "verificado": p.get("verificado", False)} for p in m["plano"]}})
    del cps[:-MAX_CHECKPOINTS]
    return n


def listar(m: dict) -> list[dict]:
    return [{"n": c["n"], "t": c["t"], "apos": c["apos"], "titulo": c["titulo"],
             "feitos": sum(1 for s in c["passos"].values() if s["estado"] == "ok")} for c in m.get("checkpoints", [])]


def texto(m: dict) -> str:
    l = listar(m)
    if not l:
        return "Esta missão ainda não tem checkpoints (eles aparecem depois do primeiro passo concluído)."
    return "Checkpoints: " + " | ".join(f"#{c['n']} após “{c['titulo']}” ({c['feitos']} passo(s) feitos)" for c in l[-8:])


def efeitos_depois(m: dict, n: int) -> list[str]:
    """Passos concluídos DEPOIS do checkpoint n cujo efeito no mundo continua (não são desfeitos pelo rewind)."""
    cp = next((c for c in m.get("checkpoints", []) if c["n"] == n), None)
    if not cp:
        return []
    return [p["titulo"] for p in m["plano"] if p["estado"] == "ok" and cp["passos"].get(str(p["id"]), {}).get("estado") != "ok" and p["tool"] != "_esperar"]


def voltar(m: dict, n: int, args_novos: dict | None = None, risco=None) -> dict:
    """Restaura o estado do checkpoint n (em `m`, sem gravar). args_novos = {passo_id: {args}} troca argumentos de passos que vão rodar de novo.
    `risco(tool, args)` reclassifica o passo. Devolve {"efeitos_que_ficam": [...], "reiniciados": [...]}."""
    if m["estado"] not in ESTADOS_PERMITIDOS:
        raise ValueError("Pause a missão antes de voltar (ela está em andamento).")
    cp = next((c for c in m.get("checkpoints", []) if c["n"] == n), None)
    if not cp:
        raise ValueError(f"Não existe o checkpoint #{n}.")
    efeitos = efeitos_depois(m, n)
    reiniciados = []
    for p in m["plano"]:
        s = cp["passos"].get(str(p["id"]))
        if s is None or s["estado"] != "ok":                         # não estava concluído naquele ponto: recomeça do zero
            if p["estado"] != "pendente" or p.get("resultado"):
                reiniciados.append(p["id"])
            p.update({"estado": "pendente", "resultado": "", "tentativas": 0, "desfazer": "", "verificado": False})
            p.pop("libera_em", None)
        else:
            p.update({"estado": s["estado"], "resultado": s["resultado"], "tentativas": s["tentativas"], "verificado": s["verificado"]})
    for pid, novos in (args_novos or {}).items():
        p = next((x for x in m["plano"] if str(x["id"]) == str(pid)), None)
        if p is None or p["estado"] != "pendente":
            raise ValueError(f"O passo {pid} não vai rodar de novo; só dá para trocar argumentos de passos pendentes.")
        if not isinstance(novos, dict):
            raise ValueError("Os argumentos novos precisam ser um dicionário.")
        p["args"] = novos
        if risco:
            p["risco"] = risco(p["tool"], novos)
    for d in m.get("decisoes", []):
        if d["estado"] == "pendente":
            d["estado"] = "cancelada"
    m["checkpoints"] = [c for c in m["checkpoints"] if c["n"] <= n]
    m["estado"] = "pausada"
    return {"efeitos_que_ficam": efeitos, "reiniciados": reiniciados}
