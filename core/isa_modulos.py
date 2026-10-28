"""core/isa_modulos.py — I.S.A. modular (NEXUS Ultra 2026 3.9): cada peça do núcleo tem nome, papel, saúde e pode ser trocada sem reiniciar.

• Registro: o que é cada módulo do núcleo e de quais outros ele depende (lido do código, não escrito à mão).
• Saúde: importa o módulo, mede quanto custa e chama `saude()` se ele tiver (devolve (ok, mensagem)).
• Atualização a quente: `recarregar(nome)` primeiro TESTA o arquivo novo num módulo descartável; só se ele carregar sem erro é que
  recarrega de verdade. Se estiver quebrado, o módulo em uso continua exatamente como estava.
• Custo de importação: quanto cada módulo demora para carregar a frio (processo separado), para achar o que vale carregar só quando precisar.
Limite honesto: recarregar troca o código do módulo, mas objetos já criados (threads em andamento, instâncias) continuam com o código antigo até reiniciar.
"""
from __future__ import annotations

import ast
import importlib
import importlib.util
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
MODULOS = {
    "isa": ("core.isa", "fluxo de eventos e decisões"),
    "preditiva": ("core.isa_preditiva", "prevê problemas e ajusta o ritmo"),
    "regeneracao": ("core.autoregeneracao", "conserta falhas conhecidas"),
    "autonomia": ("core.isa_autonomia", "tarefas de fundo e missões que se recuperam"),
    "arquitetura": ("core.isa_arquitetura", "analisa a estrutura do código e propõe melhorias"),
    "codigo": ("core.isa_codigo", "revisa o código alterado recentemente"),
    "modulos": ("core.isa_modulos", "este registro"),
    "aprendizado": ("core.aprendizado", "aprende a sua rotina, com privacidade"),
    "estatisticas": ("core.estatisticas_pc", "estatísticas do PC e sugestões"),
    "auditoria": ("core.auditoria", "registro verificável de decisões"),
    "missoes": ("core.missoes", "missões de longa duração"),
}


def arquivo(nome: str) -> Path | None:
    m = MODULOS.get(nome)
    return (BASE / (m[0].replace(".", "/") + ".py")) if m else None


def dependencias(nome: str) -> list[str]:
    """Outros módulos do projeto (core./actions./…) que este importa, lidos do código."""
    p = arquivo(nome)
    if not p or not p.is_file():
        return []
    try:
        arv = ast.parse(p.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    achados = set()
    for n in ast.walk(arv):
        mods = []
        if isinstance(n, ast.Import):
            mods = [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods = [n.module] + [f"{n.module}.{a.name}" for a in n.names] if n.level == 0 else []
        for m in mods:
            if m.split(".")[0] in ("core", "actions", "assistant", "memory", "ui", "dashboard") and (BASE / (m.replace(".", "/") + ".py")).is_file():
                achados.add(m)
    return sorted(achados - {MODULOS[nome][0]})


def quem_usa(nome: str) -> list[str]:
    alvo = MODULOS[nome][0]
    return sorted(n for n in MODULOS if n != nome and alvo in dependencias(n))


def checar(nome: str) -> dict:
    """{nome, ok, mensagem, ms}. Nunca levanta erro."""
    if nome not in MODULOS:
        return {"nome": nome, "ok": False, "mensagem": "módulo desconhecido", "ms": 0}
    t0 = time.perf_counter()
    try:
        mod = importlib.import_module(MODULOS[nome][0])
    except Exception as e:
        return {"nome": nome, "ok": False, "mensagem": f"não carrega: {type(e).__name__}: {str(e)[:100]}",
                "ms": round((time.perf_counter() - t0) * 1000)}
    ms = round((time.perf_counter() - t0) * 1000)
    fn = getattr(mod, "saude", None)
    if callable(fn):
        try:
            ok, msg = fn()
            return {"nome": nome, "ok": bool(ok), "mensagem": str(msg)[:160], "ms": ms}
        except Exception as e:
            return {"nome": nome, "ok": False, "mensagem": f"saude() falhou: {str(e)[:100]}", "ms": ms}
    return {"nome": nome, "ok": True, "mensagem": "carregado", "ms": ms}


def saude() -> tuple[bool, str]:
    return True, f"{len(MODULOS)} módulos registrados"


def todos() -> list[dict]:
    return [checar(n) for n in MODULOS]


def _testa_arquivo(caminho: Path, nome_temp: str) -> str:
    """'' se o arquivo carrega num módulo descartável; senão o motivo."""
    try:
        compile(caminho.read_text(encoding="utf-8"), str(caminho), "exec")
        spec = importlib.util.spec_from_file_location(nome_temp, caminho)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)                       # type: ignore[union-attr]
        return ""
    except Exception as e:
        return f"{type(e).__name__}: {str(e)[:150]}"
    finally:
        sys.modules.pop(nome_temp, None)


def recarregar(nome: str) -> str:
    """Atualização a quente com teste prévio. Devolve a frase do resultado (começa com 'Recarregado' se deu certo)."""
    if nome not in MODULOS:
        return f"Não conheço o módulo “{nome}”."
    p = arquivo(nome)
    if not p or not p.is_file():
        return f"O arquivo do módulo “{nome}” não existe."
    erro = _testa_arquivo(p, f"_teste_{nome}")
    if erro:
        return f"NÃO recarreguei “{nome}”: o arquivo novo não carrega ({erro}). O módulo em uso continua como estava."
    mod = sys.modules.get(MODULOS[nome][0])
    if mod is None:
        importlib.import_module(MODULOS[nome][0])
        return f"Carregado “{nome}” (ainda não estava em uso)."
    try:
        importlib.invalidate_caches()
        try:                                                # um .pyc velho (mesmo tamanho/segundo) faria o reload usar o código antigo
            Path(importlib.util.cache_from_source(str(p))).unlink()
        except (OSError, ValueError):
            pass
        importlib.reload(mod)
    except Exception as e:                                  # o teste passou mas o reload real falhou: avisa claramente
        return f"Atenção: o teste passou mas o recarregamento de “{nome}” falhou ({type(e).__name__}); reinicie o NEXUS."
    return f"Recarregado “{nome}”. Objetos já em andamento continuam com o código antigo até reiniciar."


def custo_de_importacao(nome: str, tempo: float = 20.0) -> int | None:
    """Milissegundos para importar o módulo a frio, num processo separado. None se falhar."""
    if nome not in MODULOS:
        return None
    cod = (f"import time,sys;sys.path.insert(0,{str(BASE)!r});t=time.perf_counter();"
           f"import importlib;importlib.import_module({MODULOS[nome][0]!r});print(round((time.perf_counter()-t)*1000))")
    try:
        r = subprocess.run([sys.executable, "-I", "-c", cod], capture_output=True, text=True, timeout=tempo, cwd=str(BASE))
        return int(r.stdout.strip().splitlines()[-1])
    except Exception:
        return None


def resumo() -> str:
    linhas = []
    for s in todos():
        dep = len(dependencias(s["nome"]))
        linhas.append(f"{'✔' if s['ok'] else '✘'} {s['nome']}: {s['mensagem']} ({s['ms']} ms, {dep} dependências)")
    return "\n".join(linhas)
