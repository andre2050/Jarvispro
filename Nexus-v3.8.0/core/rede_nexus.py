"""core/rede_nexus.py — rede de NEXUS: casa, celular, trabalho (NEXUS Ultra 2026 3.8).

Cada instalação é um "nó". Dois nós se PAREIAM com um código de 20 caracteres (mostrado num e digitado no outro, pela
pessoa; vale 10 minutos e uma vez). Do código sai a chave (HKDF) e toda mensagem vai cifrada com AES-256-GCM, com horário
e número único (anti-repetição). Duas coisas passam pela rede:
 • memória compartilhada: só uma lista fixa de arquivos (tarefas, projetos, contatos, memória longa), por data de
   modificação, com cópia de segurança antes de sobrescrever;
 • divisão de tarefas: um nó pede a outro que rode uma ferramenta SEGURA (só leitura). O nó que recebe só aceita se a
   pessoa ligou `aceitar_tarefas` (desligado por padrão), recusa tudo que escreve/envia/apaga e registra na auditoria.
Limites honestos: o código precisa ser digitado só nos dois aparelhos (quem o vê pode se parear); a rede precisa de um
endereço alcançável (mesmo Wi-Fi ou o túnel do 3.6); resolução de conflito é "o mais novo vence", não mescla campo a campo.
O transporte é injetado (`enviar`): nos testes dois nós conversam em memória.
"""
from __future__ import annotations

import base64
import json
import os
import secrets
import shutil
import time
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

BASE = Path(__file__).resolve().parent.parent
ARQ_CFG = BASE / "config" / "rede_nexus.json"
PASTA_MEM = BASE / "memory"
ARQUIVOS_SYNC = ("tarefas.json", "projetos.json", "contatos.json", "long_term.json", "diario.json")
MAX_ARQUIVO = 2_000_000
JANELA_S = 120
VALIDADE_CONVITE_S = 600
_ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class ErroRede(Exception):
    pass


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def _unb64(s: str) -> bytes:
    return base64.b64decode(s.encode())


def chave_do_codigo(codigo: str) -> bytes:
    c = "".join(ch for ch in str(codigo).upper() if ch in _ALFABETO)
    if len(c) != 20:
        raise ErroRede("Código inválido (são 20 caracteres).")
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=b"nexus-rede-3.8", info=b"pareamento").derive(c.encode())


def formatar_codigo(c: str) -> str:
    return "-".join(c[i:i + 5] for i in range(0, 20, 5))


class Rede:
    def __init__(self, arq: Path | None = None, pasta_mem: Path | None = None, agora=time.time, enviar=None,
                 executar=None, auditar=True):
        self.arq, self.pasta_mem = Path(arq or ARQ_CFG), Path(pasta_mem or PASTA_MEM)
        self.agora, self.enviar, self.executar, self.auditar = agora, enviar, executar, auditar
        self._convite: tuple[bytes, float] | None = None
        self._vistos: dict[str, float] = {}

    # ── configuração ──
    def _cfg(self) -> dict:
        try:
            d = json.loads(self.arq.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                return d
        except Exception:
            pass
        return {}

    def _gravar(self, d: dict) -> None:
        self.arq.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.arq.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except Exception:
            pass
        tmp.replace(self.arq)

    def eu(self, nome: str | None = None) -> dict:
        d = self._cfg()
        e = d.get("eu") or {}
        if not e.get("id"):
            e = {"id": secrets.token_hex(4), "nome": nome or "nexus"}
            d["eu"] = e
            self._gravar(d)
        elif nome and nome != e.get("nome"):
            e["nome"] = nome
            d["eu"] = e
            self._gravar(d)
        return e

    def peers(self) -> dict:
        return dict(self._cfg().get("peers") or {})

    def aceitar_tarefas(self) -> bool:
        return bool(self._cfg().get("aceitar_tarefas", False))

    def definir_aceitar_tarefas(self, v: bool) -> None:
        d = self._cfg()
        d["aceitar_tarefas"] = bool(v)
        self._gravar(d)

    def esquecer(self, peer_id: str) -> bool:
        d = self._cfg()
        ok = (d.get("peers") or {}).pop(peer_id, None) is not None
        self._gravar(d)
        return ok

    # ── pareamento ──
    def convidar(self) -> str:
        codigo = "".join(secrets.choice(_ALFABETO) for _ in range(20))
        self._convite = (chave_do_codigo(codigo), self.agora() + VALIDADE_CONVITE_S)
        return formatar_codigo(codigo)

    def entrar(self, codigo: str, url: str, minha_url: str = "", nome_peer: str = "") -> str:
        """No segundo aparelho: guarda o primeiro e se apresenta a ele (cifrado com a chave do código)."""
        if not str(url).startswith(("http://", "https://")):
            raise ErroRede("O endereço do outro NEXUS deve começar com http:// ou https://.")
        chave = chave_do_codigo(codigo)
        eu = self.eu()
        hello = self._cifrar(chave, {"tipo": "hello", "id": eu["id"], "nome": eu["nome"], "url": minha_url})
        if not self.enviar:
            raise ErroRede("Sem transporte de rede.")
        resp = self.enviar(url, "hello:" + eu["id"], hello)
        d = self._abrir(chave, resp)
        if d.get("tipo") != "hello_ok":
            raise ErroRede("O outro NEXUS recusou o pareamento.")
        cfg = self._cfg()
        cfg.setdefault("peers", {})[d["id"]] = {"nome": nome_peer or d.get("nome", "nexus"), "url": url,
                                                  "chave": _b64(chave), "desde": self.agora()}
        self._gravar(cfg)
        self._aud(f"pareado com {d.get('nome')}")
        return d["id"]

    # ── mensagens cifradas ──
    def _cifrar(self, chave: bytes, dados: dict) -> bytes:
        corpo = dict(dados, ts=self.agora(), n=secrets.token_hex(8))
        nonce = os.urandom(12)
        return nonce + AESGCM(chave).encrypt(nonce, json.dumps(corpo, ensure_ascii=False).encode(), b"nexus-rede")

    def _abrir(self, chave: bytes, blob: bytes) -> dict:
        try:
            nonce, ct = blob[:12], blob[12:]
            d = json.loads(AESGCM(chave).decrypt(nonce, ct, b"nexus-rede"))
        except Exception:
            raise ErroRede("Mensagem inválida ou chave errada.")
        agora = self.agora()
        if abs(agora - float(d.get("ts", 0))) > JANELA_S:
            raise ErroRede("Mensagem fora do horário (relógios diferentes ou repetição).")
        n = str(d.get("n"))
        if n in self._vistos:
            raise ErroRede("Mensagem repetida.")
        self._vistos = {k: t for k, t in self._vistos.items() if agora - t < 2 * JANELA_S}
        self._vistos[n] = agora
        return d

    def _chave_peer(self, peer_id: str) -> bytes:
        p = self.peers().get(peer_id)
        if not p:
            raise ErroRede("NEXUS desconhecido.")
        return _unb64(p["chave"])

    # ── lado que recebe ──
    def tratar(self, remetente: str, blob: bytes) -> bytes:
        """Entrada do servidor (/api/rede). `remetente` é o cabeçalho X-Nexus-Peer ('hello:<id>' no pareamento)."""
        if remetente.startswith("hello:"):
            if not self._convite or self.agora() > self._convite[1]:
                raise ErroRede("Não há convite aberto.")
            chave = self._convite[0]
            d = self._abrir(chave, blob)
            if d.get("tipo") != "hello" or not d.get("id"):
                raise ErroRede("Apresentação inválida.")
            self._convite = None                                # vale uma vez só
            cfg = self._cfg()
            cfg.setdefault("peers", {})[str(d["id"])[:16]] = {"nome": str(d.get("nome", "nexus"))[:40], "url": str(d.get("url", "")),
                                                              "chave": _b64(chave), "desde": self.agora()}
            self._gravar(cfg)
            eu = self.eu()
            self._aud(f"pareado com {d.get('nome')}")
            return self._cifrar(chave, {"tipo": "hello_ok", "id": eu["id"], "nome": eu["nome"]})
        chave = self._chave_peer(remetente)
        d = self._abrir(chave, blob)
        t = d.get("tipo")
        if t == "ping":
            r = {"tipo": "pong", "nome": self.eu()["nome"]}
        elif t == "sync":
            r = self._sync_responder(d)
        elif t == "push":
            r = {"tipo": "ok", "aplicados": self._aplicar(d.get("arquivos") or {}, remetente)}
        elif t == "tarefa":
            r = self._tarefa_receber(d, remetente)
        else:
            raise ErroRede("Tipo de mensagem desconhecido.")
        return self._cifrar(chave, r)

    # ── memória compartilhada ──
    def _meta_local(self) -> dict:
        out = {}
        for n in ARQUIVOS_SYNC:
            p = self.pasta_mem / n
            if p.is_file() and p.stat().st_size <= MAX_ARQUIVO:
                out[n] = p.stat().st_mtime
        return out

    def _ler_arquivos(self, nomes) -> dict:
        out = {}
        for n in nomes:
            if n in ARQUIVOS_SYNC and (self.pasta_mem / n).is_file():
                p = self.pasta_mem / n
                if p.stat().st_size <= MAX_ARQUIVO:
                    out[n] = {"mtime": p.stat().st_mtime, "dados": _b64(p.read_bytes())}
        return out

    def _sync_responder(self, d: dict) -> dict:
        remoto = {k: float(v) for k, v in (d.get("meta") or {}).items() if k in ARQUIVOS_SYNC}
        local = self._meta_local()
        meus_mais_novos = [n for n, m in local.items() if m > remoto.get(n, -1) + 1]
        quero = [n for n, m in remoto.items() if m > local.get(n, -1) + 1]
        return {"tipo": "sync_ok", "arquivos": self._ler_arquivos(meus_mais_novos), "quero": quero}

    def _aplicar(self, arquivos: dict, de: str) -> list[str]:
        aplicados = []
        for nome, item in arquivos.items():
            if nome not in ARQUIVOS_SYNC or not isinstance(item, dict):
                continue
            try:
                dados = _unb64(item["dados"])
                if len(dados) > MAX_ARQUIVO:
                    continue
                json.loads(dados.decode("utf-8"))                # só JSON válido
                destino = self.pasta_mem / nome
                self.pasta_mem.mkdir(parents=True, exist_ok=True)
                if destino.exists():
                    bk = self.pasta_mem / "rede_backup"
                    bk.mkdir(exist_ok=True)
                    shutil.copy2(destino, bk / f"{nome}.{int(self.agora())}")
                tmp = destino.with_suffix(".rede_tmp")
                tmp.write_bytes(dados)
                os.utime(tmp, (float(item["mtime"]), float(item["mtime"])))   # mesma data nos dois: não fica indo e voltando
                tmp.replace(destino)
                aplicados.append(nome)
            except Exception:
                continue
        if aplicados:
            self._aud(f"memória atualizada por outro NEXUS: {', '.join(aplicados)}", de)
        return aplicados

    def sincronizar(self, peer_id: str) -> dict:
        """Troca o que cada lado tem de mais novo. Devolve {recebidos, enviados}."""
        chave = self._chave_peer(peer_id)
        p = self.peers()[peer_id]
        r = self._abrir(chave, self.enviar(p["url"], self.eu()["id"], self._cifrar(chave, {"tipo": "sync", "meta": self._meta_local()})))
        recebidos = self._aplicar(r.get("arquivos") or {}, peer_id)
        quero = [n for n in (r.get("quero") or []) if n in ARQUIVOS_SYNC]
        enviados = []
        if quero:
            arqs = self._ler_arquivos(quero)
            self._abrir(chave, self.enviar(p["url"], self.eu()["id"], self._cifrar(chave, {"tipo": "push", "arquivos": arqs})))
            enviados = list(arqs)
        return {"recebidos": recebidos, "enviados": enviados}

    # ── divisão de tarefas ──
    def _tarefa_receber(self, d: dict, de: str) -> dict:
        from core import missoes as M
        from core import simulacao as SIM
        tool, args = str(d.get("tool") or ""), d.get("args") if isinstance(d.get("args"), dict) else {}
        if not self.aceitar_tarefas():
            return {"tipo": "tarefa_res", "ok": False, "texto": "Este NEXUS não aceita tarefas de outros (desligado)."}
        if tool in M.PROIBIDAS or tool == "especialista" or SIM.risco(tool, args) != "seguro":
            self._aud(f"tarefa recusada de {de}: {tool}", "só ferramentas de leitura são aceitas")
            return {"tipo": "tarefa_res", "ok": False, "texto": f"'{tool}' não é uma ferramenta segura (só leitura é aceita)."}
        if not self.executar:
            return {"tipo": "tarefa_res", "ok": False, "texto": "Este NEXUS ainda não está pronto para tarefas."}
        self._aud(f"tarefa recebida de {de}: {tool}", "pedido de outro NEXUS")
        try:
            texto = str(self.executar(tool, args))[:2000]
        except Exception as e:
            return {"tipo": "tarefa_res", "ok": False, "texto": f"Falhou: {e}"[:300]}
        return {"tipo": "tarefa_res", "ok": True, "texto": texto}

    def delegar(self, peer_id: str, tool: str, args: dict | None = None) -> str:
        chave = self._chave_peer(peer_id)
        p = self.peers()[peer_id]
        r = self._abrir(chave, self.enviar(p["url"], self.eu()["id"],
                                           self._cifrar(chave, {"tipo": "tarefa", "tool": tool, "args": args or {}})))
        texto = str(r.get("texto") or "")
        try:
            from core import verificacao as V
            texto = V.embrulhar("rede_nexus", texto)           # o que vem de outro nó é dado, nunca instrução
        except Exception:
            pass
        return ("" if r.get("ok") else "[failed] ") + texto

    def ping(self, peer_id: str) -> bool:
        try:
            chave = self._chave_peer(peer_id)
            r = self._abrir(chave, self.enviar(self.peers()[peer_id]["url"], self.eu()["id"], self._cifrar(chave, {"tipo": "ping"})))
            return r.get("tipo") == "pong"
        except Exception:
            return False

    def _aud(self, o_que: str, motivo: str = "") -> None:
        if not self.auditar:
            return
        try:
            from core import auditoria
            auditoria.registrar("sistema", "rede_nexus", o_que, motivo=motivo)
        except Exception:
            pass
