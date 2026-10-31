"""Cofre de chaves (4.6.0): guarda chaves e senhas no cofre do sistema em vez de texto puro em config/api_keys.json.

Windows: Gerenciador de Credenciais. macOS: Keychain. Linux: Secret Service (GNOME/KDE). Usa a biblioteca `keyring`.

Como funciona: ligado, cada segredo do api_keys.json (chaves de API, tokens, senhas) vai para o cofre e no arquivo
sobra só a marca "@cofre". Quem lê a configuração recebe os valores de volta por `resolver()` (memory/config_manager.py
e os outros leitores já fazem isso). Quem grava continua gravando como sempre: um segredo NOVO digitado numa tela cai no
arquivo em texto puro até a próxima sincronização, que acontece ao abrir o NEXUS e ao salvar.

É opcional e começa DESLIGADO. Sem `keyring` ou sem cofre no sistema, nada muda e o NEXUS avisa. Desligar traz os
segredos de volta para o arquivo. Nada é apagado do cofre sem você pedir.
"""
from __future__ import annotations

import json
import re
from typing import Any

MARCA = "@cofre"
SERVICO = "NEXUS-Ultra-2026"
_NOME_SEGREDO = re.compile(r"(api_?key|token|password|senha|secret)$", re.IGNORECASE)
_NAO_E_SEGREDO = re.compile(r"(max_?tokens|tokens?_(used|limit|count)|password_(hash|salt)|_hash$|_salt$)", re.IGNORECASE)
MIN_TAM = 6


def _backend():
    """O cofre do sistema, ou None se não houver um de verdade."""
    try:
        import keyring
        from keyring.backends import fail, null
        k = keyring.get_keyring()
        if isinstance(k, (fail.Keyring, null.Keyring)) or "fail" in type(k).__module__ or "null" in type(k).__module__:
            return None
        return keyring
    except Exception:
        return None


def disponivel() -> bool:
    return _backend() is not None


def nome_do_cofre() -> str:
    b = _backend()
    return type(b.get_keyring()).__name__ if b else ""


def _eh_segredo(chave: str, valor: Any) -> bool:
    return (isinstance(valor, str) and len(valor.strip()) >= MIN_TAM and valor != MARCA
            and bool(_NOME_SEGREDO.search(str(chave))) and not _NAO_E_SEGREDO.search(str(chave)))


def _percorrer(d: Any, caminho: tuple = ()):
    """Gera (caminho, dicionário_pai, chave) de cada valor que é segredo ou marca."""
    if isinstance(d, dict):
        for k, v in d.items():
            if isinstance(v, (dict, list)):
                yield from _percorrer(v, caminho + (str(k),))
            elif _eh_segredo(k, v) or v == MARCA:
                yield caminho + (str(k),), d, k


def _nome(caminho: tuple) -> str:
    return ".".join(caminho)


def migrar(dados: dict, backend=None) -> tuple[dict, int]:
    """Move os segredos de `dados` para o cofre. Devolve (dados com marcas, quantos moveu). Não mexe no original.
    Se um segredo não puder ser guardado, ele continua no arquivo (nunca se perde nada)."""
    b = backend or _backend()
    if b is None:
        return dados, 0
    novo = json.loads(json.dumps(dados))
    n = 0
    for caminho, pai, chave in list(_percorrer(novo)):
        valor = pai[chave]
        if valor == MARCA:
            continue
        try:
            b.set_password(SERVICO, _nome(caminho), valor)
            if b.get_password(SERVICO, _nome(caminho)) != valor:
                continue            # não confirmou a gravação: deixa no arquivo
        except Exception:
            continue
        pai[chave] = MARCA
        n += 1
    return novo, n


def resolver(dados: Any, backend=None) -> Any:
    """Troca cada "@cofre" pelo valor guardado. Sem cofre (ou sem o valor), vira "" e a falta aparece como chave ausente."""
    if not isinstance(dados, dict):
        return dados
    if MARCA not in json.dumps(dados):
        return dados
    b = backend or _backend()
    novo = json.loads(json.dumps(dados))
    for caminho, pai, chave in list(_percorrer(novo)):
        if pai[chave] != MARCA:
            continue
        try:
            pai[chave] = (b.get_password(SERVICO, _nome(caminho)) if b else None) or ""
        except Exception:
            pai[chave] = ""
    return novo


def devolver(dados: dict, backend=None) -> tuple[dict, int]:
    """Desligar o cofre: coloca os valores de volta no arquivo. Só devolve `dados` completo se TODOS os valores vieram."""
    b = backend or _backend()
    novo = json.loads(json.dumps(dados))
    n = 0
    for caminho, pai, chave in list(_percorrer(novo)):
        if pai[chave] != MARCA:
            continue
        try:
            v = b.get_password(SERVICO, _nome(caminho)) if b else None
        except Exception:
            v = None
        if v:
            pai[chave] = v
            n += 1
    return novo, n


def sobrou_marca(dados: dict) -> bool:
    return MARCA in json.dumps(dados)


def esquecer_tudo(dados: dict, backend=None) -> int:
    """Apaga do cofre os segredos que este arquivo aponta. Só a pedido do usuário."""
    b = backend or _backend()
    n = 0
    if b is None:
        return 0
    for caminho, pai, chave in _percorrer(dados):
        try:
            b.delete_password(SERVICO, _nome(caminho))
            n += 1
        except Exception:
            pass
    return n


def ligado() -> bool:
    try:
        from core import preferences as P
        return bool(P.get("cofre_chaves"))
    except Exception:
        return False


# ── ligar / desligar / sincronizar o arquivo de configuração ─────────────────

def _arquivo():
    from memory.config_manager import CONFIG_FILE
    return CONFIG_FILE


def _gravar(path, dados: dict) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(dados, indent=4, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def sincronizar(path=None, backend=None) -> int:
    """Com o cofre ligado, move para ele qualquer segredo que tenha caído no arquivo em texto puro.
    Seguro de chamar sempre: sem cofre ou desligado, não faz nada. Devolve quantos moveu."""
    if backend is None and not ligado():
        return 0
    try:
        p = path or _arquivo()
        dados = json.loads(p.read_text(encoding="utf-8"))
        novo, n = migrar(dados, backend)
        if n:
            _gravar(p, novo)
        return n
    except Exception:
        try:
            from core import protecao
            protecao.anotar("sincronizar o cofre de chaves")
        except Exception:
            pass
        return 0


def ligar(path=None, backend=None) -> dict:
    """Liga o cofre: guarda os segredos e marca a preferência. Devolve {"ok", "moveu", "motivo"}."""
    b = backend or _backend()
    if b is None:
        return {"ok": False, "moveu": 0, "motivo": "O sistema não tem um cofre de senhas disponível (instale 'keyring' e use o login do sistema)."}
    p = path or _arquivo()
    try:
        dados = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "moveu": 0, "motivo": f"Não consegui ler a configuração: {e}"}
    novo, n = migrar(dados, b)
    if n:
        # cópia de segurança antes de tirar as chaves do arquivo
        try:
            p.with_suffix(".json.antes_do_cofre").write_text(json.dumps(dados, indent=4, ensure_ascii=False), encoding="utf-8")
        except Exception:
            return {"ok": False, "moveu": 0, "motivo": "Não consegui fazer a cópia de segurança; nada foi alterado."}
        _gravar(p, novo)
    try:
        from core import preferences as P
        P.save({"cofre_chaves": True})
    except Exception:
        pass
    return {"ok": True, "moveu": n, "motivo": ""}


def desligar(path=None, backend=None) -> dict:
    """Desliga o cofre: os valores voltam para o arquivo. Se algum não puder ser lido, nada é alterado."""
    b = backend or _backend()
    p = path or _arquivo()
    try:
        dados = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "voltou": 0, "motivo": f"Não consegui ler a configuração: {e}"}
    novo, n = devolver(dados, b)
    if sobrou_marca(novo):
        return {"ok": False, "voltou": 0, "motivo": "Alguns valores não estão no cofre deste computador; o cofre continua ligado."}
    if n:
        _gravar(p, novo)
    try:
        from core import preferences as P
        P.save({"cofre_chaves": False})
    except Exception:
        pass
    return {"ok": True, "voltou": n, "motivo": ""}
