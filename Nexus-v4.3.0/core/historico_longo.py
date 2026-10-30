"""core/historico_longo.py — retenção de histórico longo (NEXUS Ultra 4.0).

O NEXUS só guarda os resumos das últimas conversas; as antigas se perdiam. Aqui tudo o que já foi resumido (conversas, diário, notas) vai
para um ARQUIVO PERMANENTE no seu PC (memory/historico_longo.jsonl), sem duplicar, e dá para perguntar "quando falamos do carro?",
"o que decidi sobre o plano de saúde no ano passado?":
  • ingestão incremental e idempotente; entradas com padrão de segredo (cartão, CPF, chave de API) NÃO entram;
  • compactação: com mais de 180 dias o texto é encurtado a 240 caracteres (as palavras-chave ficam), então o arquivo não incha;
  • busca por palavras (pontuação tipo BM25 + recência + período falado: "mês passado", "últimos 30 dias");
  • duas estratégias de busca COMPETEM (palavras × semântica do índice); a que acertar mais vence, sem você mexer (core/competicao.py);
  • `esquecer(tema)` apaga o que casa; `esquecer_tudo` zera; `exportar` mostra tudo. Nada sai do PC.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
import unicodedata
from collections import Counter
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
ARQUIVO = BASE / "memory" / "historico_longo.jsonl"
MAX_ENTRADAS = 20000
COMPACTA_APOS_DIAS = 180
TAM_COMPACTO = 240
_trava = threading.Lock()
_SEGREDO = re.compile(r"(\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b|\b(?:\d[ -]?){13,19}\b|AIza[0-9A-Za-z_-]{20,}|sk-[A-Za-z0-9]{20,}|\bsenha\s*(é|e|:)\s*\S+)", re.I)
_STOP = {"o", "a", "os", "as", "um", "uma", "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas", "que", "e", "ou", "para", "pra", "por",
         "com", "se", "sobre", "ele", "ela", "foi", "ser", "ter", "mais", "como", "mas", "seu", "sua", "usuario", "falamos", "quando", "qual", "eu", "meu", "minha"}


def _n(t) -> str:
    return unicodedata.normalize("NFKD", str(t or "").lower()).encode("ascii", "ignore").decode()


def tokens(texto: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]{2,}", _n(texto)) if w not in _STOP]


def _ler(arq=None) -> list[dict]:
    out = []
    try:
        for l in Path(arq or ARQUIVO).read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(l)
                if isinstance(e, dict) and e.get("texto"):
                    out.append(e)
            except Exception:
                continue
    except OSError:
        pass
    return out


def _gravar_tudo(itens: list[dict], arq=None) -> None:
    arq = Path(arq or ARQUIVO)
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in itens) + ("\n" if itens else ""), encoding="utf-8")
    tmp.replace(arq)


def _id(fonte: str, texto: str) -> str:
    return hashlib.sha1(f"{fonte}|{_n(texto)}".encode()).hexdigest()[:16]


def _data(q) -> str:
    try:
        return datetime.strptime(str(q)[:10], "%Y-%m-%d").date().isoformat()
    except Exception:
        return ""


def coletar_fontes(base: Path | None = None) -> list[dict]:
    """Conversas resumidas, diário e notas, como {fonte, texto, quando}."""
    try:
        from core import indice_semantico
        return [d for d in indice_semantico.coletar(base or BASE, ("conversas", "diario", "notas")) if d.get("texto")]
    except Exception:
        return []


def ingerir(docs: list[dict] | None = None, arq=None, hoje: date | None = None) -> dict:
    """Soma o que é novo ao arquivo. Devolve {novos, total, ignorados_segredo}."""
    docs = coletar_fontes() if docs is None else docs
    hoje = hoje or date.today()
    with _trava:
        atuais = _ler(arq)
        tem = {e["id"] for e in atuais}
        novos, segredo = [], 0
        for d in docs:
            texto = re.sub(r"\s+", " ", str(d.get("texto") or "")).strip()
            if not texto:
                continue
            if _SEGREDO.search(texto):
                segredo += 1
                continue
            fonte = str(d.get("fonte") or "?")
            i = _id(fonte, texto)
            if i in tem:
                continue
            tem.add(i)
            novos.append({"id": i, "fonte": fonte, "data": _data(d.get("quando")) or hoje.isoformat(), "texto": texto[:1500],
                          "tags": [w for w, _ in Counter(tokens(texto)).most_common(8)], "compacto": False})
        todos = atuais + novos
        if novos or any(_deve_compactar(e, hoje) for e in todos):
            todos = compactar(todos, hoje)
            todos = sorted(todos, key=lambda e: e["data"])[-MAX_ENTRADAS:]
            _gravar_tudo(todos, arq)
        return {"novos": len(novos), "total": len(todos), "ignorados_segredo": segredo}


def _deve_compactar(e: dict, hoje: date) -> bool:
    try:
        idade = (hoje - date.fromisoformat(e["data"])).days
    except Exception:
        return False
    return idade > COMPACTA_APOS_DIAS and not e.get("compacto") and len(e["texto"]) > TAM_COMPACTO


def compactar(itens: list[dict], hoje: date) -> list[dict]:
    for e in itens:
        if _deve_compactar(e, hoje):
            e["texto"] = e["texto"][:TAM_COMPACTO].rstrip() + "…"
            e["compacto"] = True
    return itens


def _sem_periodo(consulta: str) -> str:
    """Tira da consulta as palavras de período ("mês passado", "últimos 30 dias") para não contarem como assunto."""
    try:
        from core import busca_historico
        return " ".join(busca_historico.termos(consulta)) or consulta
    except Exception:
        return consulta


def buscar_palavras(consulta: str, dias: tuple[date, date] | None = None, limite: int = 5, arq=None, hoje: date | None = None) -> list[dict]:
    """Pontuação por palavras raras (IDF), com bônus por palavra-chave e por recência."""
    itens = _ler(arq)
    q = set(tokens(_sem_periodo(consulta)))
    if not itens or not q:
        return []
    hoje = hoje or date.today()
    docs = [set(tokens(e["texto"])) | set(e.get("tags", [])) for e in itens]
    N = len(itens)
    df = Counter(w for d in docs for w in d)
    out = []
    for e, d in zip(itens, docs):
        if dias and not (dias[0].isoformat() <= e["data"] <= dias[1].isoformat()):
            continue
        achou = q & d
        if not achou:
            continue
        s = sum(math.log(1 + N / df[w]) for w in achou) / len(q) + 0.3 * len(achou & set(e.get("tags", []))) / len(q)
        try:
            s *= 1 + 0.2 / (1 + (hoje - date.fromisoformat(e["data"])).days / 30)
        except Exception:
            pass
        if len(achou) / len(q) >= 0.5 or len(q) == 1:
            out.append((s, e))
    return [dict(e, nota=round(s, 3)) for s, e in sorted(out, key=lambda x: -x[0])[:limite]]


def buscar_semantica(consulta: str, dias=None, limite: int = 5, arq=None, hoje=None, indice=None) -> list[dict]:
    """Variante que usa o índice semântico (se existir) e depois confere no arquivo."""
    if indice is None:
        from core import indice_semantico
        indice = indice_semantico.indice()
    achados = indice.buscar(consulta, k=limite * 3, fontes={"conversas", "diario", "notas"})
    textos = {_n(e["texto"])[:60]: e for e in _ler(arq)}
    out = []
    for s, d in achados:
        e = textos.get(_n(d.get("texto"))[:60])
        if e and (not dias or dias[0].isoformat() <= e["data"] <= dias[1].isoformat()):
            out.append(dict(e, nota=round(float(s), 3)))
    return out[:limite]


def _periodo(consulta: str, hoje: date):
    try:
        from core import busca_historico
        p = busca_historico.periodo(consulta, hoje)
        return (p[0], p[1]) if p else None
    except Exception:
        return None


def _registrar_competicao() -> None:
    from core import competicao
    competicao.registrar("historico", "palavras", lambda c, d, l, a, h: buscar_palavras(c, d, l, a, h), valida=lambda r: bool(r))
    competicao.registrar("historico", "semantica", lambda c, d, l, a, h: buscar_semantica(c, d, l, a, h), valida=lambda r: bool(r))


def buscar(consulta: str, limite: int = 5, arq=None, hoje: date | None = None, competir: bool = True) -> list[dict]:
    hoje = hoje or date.today()
    dias = _periodo(consulta, hoje)
    if competir:
        try:
            from core import competicao
            if "historico" not in competicao._variantes:
                _registrar_competicao()
            res, _nome = competicao.executar("historico", consulta, dias, limite, arq, hoje, restricao="preciso")
            return res
        except Exception:
            pass
    return buscar_palavras(consulta, dias, limite, arq, hoje)


def lembrar(consulta: str, limite: int = 4, arq=None, hoje: date | None = None, competir: bool = True) -> str:
    r = buscar(consulta, limite, arq, hoje, competir)
    if not r:
        return "Não achei nada no seu histórico sobre isso."
    def dt(e):
        try:
            return date.fromisoformat(e["data"]).strftime("%d/%m/%Y")
        except Exception:
            return e["data"]
    return " | ".join(f"{dt(e)} ({e['fonte']}): {e['texto'][:160]}" for e in r)


def esquecer(tema: str, arq=None) -> int:
    q = set(tokens(tema))
    if not q:
        return 0
    with _trava:
        itens = _ler(arq)
        ficam = [e for e in itens if not (q <= (set(tokens(e["texto"])) | set(e.get("tags", []))))]
        _gravar_tudo(ficam, arq)
        return len(itens) - len(ficam)


def esquecer_tudo(arq=None) -> int:
    with _trava:
        n = len(_ler(arq))
        _gravar_tudo([], arq)
        return n


def exportar(arq=None) -> str:
    return json.dumps(_ler(arq), ensure_ascii=False, indent=1)


def resumo(arq=None) -> str:
    it = _ler(arq)
    if not it:
        return "O histórico longo ainda está vazio."
    return f"{len(it)} lembrança(s), de {it[0]['data']} até {it[-1]['data']}."


def saude() -> tuple[bool, str]:
    return True, f"{len(_ler())} lembrança(s)"
