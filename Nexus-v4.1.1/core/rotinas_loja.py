"""Rotinas na loja (3.7): pacotes `.nexusrotina` com rotinas prontas para compartilhar.

Um pacote é um zip com `rotina.json` (e, opcional, `rotina.sig`, assinatura Ed25519 do autor — a mesma lista de autores
confiáveis dos plugins). Ele NÃO carrega código: só rotinas feitas de ferramentas seguras (as mesmas que a rotina por
conversa aceita; nunca enviar mensagem, apagar arquivo ou controlar mouse/teclado). Instalar mostra o que cada rotina faz
e pede CONFIRMAR; rotina que já existe com o mesmo nome ganha outro nome em vez de ser substituída.
"""
from __future__ import annotations

import base64
import json
import re
import zipfile
from pathlib import Path

from core import plugin_loja as L

EXTENSAO = ".nexusrotina"
MAX_PACOTE = 512 * 1024
MAX_ROTINAS = 12
MAX_PARAM_JSON = 2000
_ID = re.compile(r"^[a-z][a-z0-9_]{2,40}$")


class ErroRotinas(L.ErroPacote):
    pass


def _validar_rotina(nome: str, r: dict) -> dict:
    from actions import smart_routines as SR
    if not isinstance(r, dict):
        raise ErroRotinas(f"A rotina “{nome}” está malformada.")
    passos, erro = SR._parse_steps(r.get("steps"))
    if erro or not passos:
        raise ErroRotinas(f"A rotina “{nome}” foi recusada: {erro or 'sem passos'}.")
    if len(passos) > SR.MAX_STEPS:
        raise ErroRotinas(f"A rotina “{nome}” tem passos demais.")
    for p in passos:
        if len(json.dumps(p["params"], ensure_ascii=False)) > MAX_PARAM_JSON:
            raise ErroRotinas(f"A rotina “{nome}” tem um passo grande demais.")
    item = {"steps": passos, "description": str(r.get("description") or "")[:200]}
    ag = r.get("agenda")
    if ag is not None:
        from core import rotinas_conversa as RC
        dias = ag.get("dias") if isinstance(ag, dict) else None
        if isinstance(dias, str):
            dias = RC.parse_dias(dias)
        if not (isinstance(dias, list) and dias and all(isinstance(d, int) and 0 <= d <= 6 for d in dias)):
            dias = None
        hora = RC.parse_hora(ag.get("hora")) if isinstance(ag, dict) else None
        if not dias or not hora:
            raise ErroRotinas(f"A agenda da rotina “{nome}” é inválida.")
        item["agenda"] = {"dias": dias, "hora": hora}
    return item


class PacoteRotinas:
    def __init__(self, manifesto: dict, rotinas: dict[str, dict], autor_confiavel: str | None):
        self.manifesto, self.rotinas, self.autor_confiavel = manifesto, rotinas, autor_confiavel
        self.id = manifesto["id"]

    @property
    def assinado(self) -> bool:
        return self.autor_confiavel is not None

    def resumo(self) -> str:
        from actions import smart_routines as SR
        m = self.manifesto
        selo = f"assinado por {self.autor_confiavel}" if self.assinado else "SEM assinatura de autor confiável"
        partes = []
        for nome, r in self.rotinas.items():
            quando = ""
            if r.get("agenda"):
                from core import rotinas_conversa as RC
                quando = " — " + RC.descrever_agenda(r["agenda"])
            partes.append(f"{SR._describe(nome, r)}{quando}")
        return f"{m['nome']} {m['versao']}, de {m['autor']} ({selo}). " + " | ".join(partes)


def abrir(caminho: str | Path, autores: dict[str, str] | None = None) -> PacoteRotinas:
    p = Path(caminho)
    if not p.is_file() or p.suffix.lower() != EXTENSAO:
        raise ErroRotinas(f"Não achei o pacote {EXTENSAO}: {p.name}")
    if p.stat().st_size > MAX_PACOTE:
        raise ErroRotinas("O pacote é grande demais para só rotinas.")
    try:
        z = zipfile.ZipFile(p)
    except zipfile.BadZipFile:
        raise ErroRotinas("O arquivo não é um pacote válido (zip quebrado).")
    with z:
        nomes = set(z.namelist())
        if not nomes <= {"rotina.json", "rotina.sig"} or "rotina.json" not in nomes:
            raise ErroRotinas("O pacote deve ter só rotina.json (e rotina.sig).")
        if sum(i.file_size for i in z.infolist()) > 4 * MAX_PACOTE:
            raise ErroRotinas("O pacote descompactado é grande demais.")
        bruto = z.read("rotina.json")
        sig_b = z.read("rotina.sig") if "rotina.sig" in nomes else b""
    try:
        m = json.loads(bruto.decode("utf-8"))
    except ValueError:
        raise ErroRotinas("O rotina.json não é um JSON válido.")
    if not isinstance(m, dict) or not _ID.match(str(m.get("id", ""))) or not all(
            isinstance(m.get(k), str) and m[k].strip() for k in ("nome", "versao", "autor")):
        raise ErroRotinas("Manifesto inválido (faltam id, nome, versao ou autor).")
    rot = m.get("rotinas")
    if not isinstance(rot, dict) or not rot or len(rot) > MAX_ROTINAS:
        raise ErroRotinas(f"O pacote deve ter de 1 a {MAX_ROTINAS} rotinas.")
    limpas = {}
    for nome, r in rot.items():
        nome_l = " ".join(str(nome).lower().split())[:60]
        if not nome_l:
            raise ErroRotinas("Uma rotina está sem nome.")
        limpas[nome_l] = _validar_rotina(nome_l, r)
    autor = None
    if sig_b:
        try:
            sig = base64.b64decode(sig_b.decode("ascii").strip())
        except Exception:
            sig = b""
        for nome, chave in (autores if autores is not None else L.autores_confiaveis()).items():
            if sig and L._verificar_ed25519(L._b64(chave), bruto, sig):
                autor = nome
                break
    return PacoteRotinas(m, limpas, autor)


def instalar(pacote: PacoteRotinas) -> str:
    from actions import smart_routines as SR
    novos = []
    with SR._LOCK:
        data = SR._load()
        for nome, item in pacote.rotinas.items():
            alvo, n = nome, 2
            while alvo in data:                                  # nunca substitui uma rotina sua
                alvo = f"{nome} ({'loja' if n == 2 else n})"
                n += 1
            if len(data) >= SR.MAX_ROUTINES:
                break
            data[alvo] = dict(item, origem=f"loja:{pacote.id}")
            novos.append(alvo)
        SR._save(data)
    if not novos:
        return "Nenhuma rotina instalada: o limite de rotinas foi atingido."
    return "Instalei: " + ", ".join(novos) + "."


def exportar(nomes: list[str], destino: str | Path, meta: dict, chave_privada_b64: str | None = None) -> Path:
    """Empacota rotinas SUAS (já salvas) num .nexusrotina. `meta`: id, nome, versao, autor, descricao."""
    from actions import smart_routines as SR
    data = SR._load()
    rot = {}
    for n in nomes:
        k = SR._norm(n)
        if k not in data:
            raise ErroRotinas(f"Não tenho a rotina “{n}”.")
        r = data[k]
        rot[k] = {"steps": r["steps"], "description": r.get("description", ""),
                  **({"agenda": r["agenda"]} if r.get("agenda") else {})}
    if not rot:
        raise ErroRotinas("Diga quais rotinas exportar.")
    manifesto = {"id": meta["id"], "nome": meta["nome"], "versao": meta["versao"], "autor": meta["autor"],
                 "descricao": meta.get("descricao", ""), "rotinas": rot}
    bruto = json.dumps(manifesto, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8")
    destino = Path(destino)
    if destino.suffix.lower() != EXTENSAO:
        destino = destino.with_suffix(EXTENSAO)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("rotina.json", bruto)
        if chave_privada_b64:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            z.writestr("rotina.sig", base64.b64encode(Ed25519PrivateKey.from_private_bytes(L._b64(chave_privada_b64)).sign(bruto)))
    abrir(destino, autores={})                                   # confere que o que saiu é válido
    return destino
