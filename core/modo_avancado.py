"""core/modo_avancado.py — scripts seus, rodando isolados (NEXUS Ultra 2026 3.9).

Uma biblioteca de scripts Python pequenos que VOCÊ aprova. Cada um define `def main(args: dict) -> str`. Ao guardar, o código é
analisado (core.plugin_loja.permissoes_usadas): o que usa rede, programas, arquivos, tela ou dados pessoais é recusado; só sobra
cálculo/texto. Para rodar, vai ao mesmo isolamento da fábrica de plugins (processo separado -I, sem rede, limites de CPU/memória/tempo,
pasta temporária). A PRIMEIRA execução — e toda execução depois de o código mudar — exige CONFIRMAR na tela (quem decide é o hash do
código, não o modelo). Resposta cortada em 200 caracteres. Para IA local, `perguntar_local` usa só o modelo no seu PC (modo privado).
Biblioteca em config/scripts_avancados.json (pessoal, fora do GitHub).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent.parent / "config" / "scripts_avancados.json"
MAX_SCRIPTS = 20
MAX_CODIGO = 8000
_RODAPE = "\n\nTOOL = {'name': 'script', 'description': 'script', 'parameters': {}, 'handler': lambda p, **k: str(main(p))}\n"


class ErroScript(Exception):
    pass


def _ler(arq=None) -> dict:
    try:
        d = json.loads(Path(arq or ARQUIVO).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _gravar(d: dict, arq=None) -> None:
    arq = Path(arq or ARQUIVO)
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(arq)


def _nome(n: str) -> str:
    n = re.sub(r"[^a-z0-9_]+", "_", str(n or "").lower()).strip("_")[:30]
    if len(n) < 2:
        raise ErroScript("Dê um nome ao script (letras e números).")
    return n


def _hash(codigo: str) -> str:
    return hashlib.sha256(codigo.encode("utf-8")).hexdigest()


def guardar(nome: str, codigo: str, descricao: str = "", arq=None) -> str:
    from core import plugin_loja as L
    nome, codigo = _nome(nome), str(codigo or "").replace("\r\n", "\n")
    if not codigo.strip() or len(codigo) > MAX_CODIGO:
        raise ErroScript(f"O código precisa ter entre 1 e {MAX_CODIGO} caracteres.")
    if not re.search(r"^def main\(\w+", codigo, re.M):
        raise ErroScript("Falta a função `def main(args): ...` que devolve texto.")
    usadas, graves = L.permissoes_usadas(codigo)
    if graves or usadas:
        motivo = "; ".join(graves) or "usa: " + ", ".join(sorted(usadas))
        raise ErroScript(f"O modo avançado só aceita cálculo e texto, sem acesso ao mundo. Recusado ({motivo}).")
    lib = _ler(arq)
    if nome not in lib and len(lib) >= MAX_SCRIPTS:
        raise ErroScript(f"Já há {MAX_SCRIPTS} scripts; remova um.")
    lib[nome] = {"codigo": codigo, "descricao": str(descricao)[:120], "hash": _hash(codigo), "aprovado": lib.get(nome, {}).get("aprovado") if lib.get(nome, {}).get("hash") == _hash(codigo) else None}
    _gravar(lib, arq)
    return nome


def remover(nome: str, arq=None) -> bool:
    lib = _ler(arq)
    ok = lib.pop(_nome(nome), None) is not None
    _gravar(lib, arq)
    return ok


def listar(arq=None) -> list[dict]:
    return [{"nome": n, "descricao": s.get("descricao", ""), "aprovado": s.get("aprovado") == s.get("hash")} for n, s in _ler(arq).items()]


def precisa_confirmar(nome: str, arq=None) -> bool:
    s = _ler(arq).get(_nome(nome))
    if not s:
        raise ErroScript("Não achei esse script.")
    return s.get("aprovado") != _hash(s["codigo"])


def aprovar(nome: str, arq=None) -> None:
    lib = _ler(arq)
    s = lib.get(_nome(nome))
    if not s:
        raise ErroScript("Não achei esse script.")
    s["aprovado"] = _hash(s["codigo"])
    _gravar(lib, arq)


def executar(nome: str, args: dict | None = None, arq=None, testar=None, tempo: int = 10) -> str:
    """Roda no isolamento. Exige aprovação do hash atual (use `aprovar` depois do CONFIRMAR)."""
    if precisa_confirmar(nome, arq):
        raise ErroScript("Esse código ainda não foi aprovado por você.")
    s = _ler(arq)[_nome(nome)]
    if _hash(s["codigo"]) != s["hash"]:
        raise ErroScript("O código foi alterado fora do NEXUS; guarde de novo.")
    if testar is None:
        from core import fabrica_plugins
        testar = fabrica_plugins.testar
    r = testar(s["codigo"] + _RODAPE, [dict(args or {})], tempo)
    if not r.get("ok"):
        raise ErroScript("O script falhou: " + str(r.get("erro"))[:200])
    return (r["resultados"] or [""])[0]


def perguntar_local(texto: str, local=None) -> str:
    """Só o modelo no PC (modo privado): nada vai para a nuvem. `local(texto)->str` injetável."""
    from core import hibrido
    if local is None:
        return "IA local não configurada neste PC."
    resp, rota = hibrido.completar(str(texto)[:2000], nuvem=lambda t: "", local=local, online=False, local_ok=True, modo_atual="privado", auditar=False)
    return resp or "O modelo local não respondeu."


def saude() -> str:
    return f"{len(_ler())} script(s)"
