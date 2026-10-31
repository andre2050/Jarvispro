"""core/adaptacao.py — adaptação contínua ao seu modo de uso (NEXUS Ultra 4.0).

Em vez de depender de alguém mudar o código, o NEXUS ajusta alguns "botões" de comportamento conforme você usa — com freio e transparência.
Opt-in (começa DESLIGADO), tudo local. Botões e o que os move:
  • verbosidade 1–5 (quanto ele fala): você interrompe → menos; você pede detalhes → mais;
  • proatividade 1–5 (quantos avisos por conta própria): você age depois de um aviso → mais; ignora → menos;
  • horas de silêncio: horas do dia em que você nunca usa o NEXUS (≥ 50 usos medidos) viram "silêncio" só para avisos de voz espontâneos;
  • ferramentas favoritas: as que você mais usa.
Freios: só muda depois de 8 sinais e com tendência clara (≥ 60% na mesma direção), no máximo 1 passo por botão a cada 24 h, nunca sai de 1–5;
`travar` fixa um botão à mão (a adaptação não mexe), `reverter` desfaz a última mudança, `esquecer` zera tudo. Cada mudança fica no histórico com o motivo.
Só guarda contagens e horas — nenhum conteúdo de conversa.
"""
from __future__ import annotations

import json
import threading
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from core.protecao import engolida as _engolida

ARQUIVO = Path(__file__).resolve().parent.parent / "memory" / "adaptacao.json"
MIN_SINAIS = 8
TENDENCIA = 0.6
INTERVALO_S = 24 * 3600
MIN_USOS_HORA = 50
AGIU_EM_S = 120
IGNOROU_APOS_S = 300
_trava = threading.Lock()

BOTOES = {"verbosidade": ("interrompeu", "pediu_detalhes"), "proatividade": ("ignorou_aviso", "agiu_no_aviso")}   # (empurra para baixo, para cima)
_COOLDOWN = {1: 3.0, 2: 1.7, 3: 1.0, 4: 0.7, 5: 0.5}
_TEXTO_VERBOSIDADE = {1: "Responda de forma MUITO curta (uma frase).", 2: "Responda de forma curta, sem rodeios.", 4: "Pode dar um pouco mais de detalhe quando ajudar.",
                      5: "Pode explicar com detalhe; o usuário costuma pedir mais."}


def _novo() -> dict:
    return {"ligado": False, "botoes": {"verbosidade": 3, "proatividade": 3}, "travados": [], "contagens": {}, "ultima_mudanca": {}, "historico": [],
            "horas": [0] * 24, "usos": {}, "aviso_pendente": 0.0}


def _ler(arq=None) -> dict:
    try:
        d = json.loads(Path(arq or ARQUIVO).read_text(encoding="utf-8"))
        if isinstance(d, dict):
            base = _novo()
            base.update(d)
            return base
    except Exception:
        _engolida("core/adaptacao.py:50")
    return _novo()


def _gravar(d: dict, arq=None) -> None:
    arq = Path(arq or ARQUIVO)
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    tmp.replace(arq)


def ligado(arq=None) -> bool:
    return bool(_ler(arq).get("ligado"))


def ligar(sim: bool, arq=None) -> None:
    with _trava:
        d = _ler(arq)
        d["ligado"] = bool(sim)
        _gravar(d, arq)


def observar(sinal: str, valor: str = "", agora: float | None = None, arq=None) -> None:
    """Registra um sinal de uso. Sinais: interrompeu, pediu_detalhes, ignorou_aviso, agiu_no_aviso, uso (valor = nome da ferramenta), aviso (um aviso foi dado)."""
    try:
        agora = time.time() if agora is None else agora
        with _trava:
            d = _ler(arq)
            if not d["ligado"]:
                return
            if sinal == "aviso":
                d["aviso_pendente"] = agora
            elif sinal == "uso":
                d["horas"][datetime.fromtimestamp(agora).hour] += 1
                d["usos"][str(valor)[:40]] = d["usos"].get(str(valor)[:40], 0) + 1
                if d["aviso_pendente"] and agora - d["aviso_pendente"] <= AGIU_EM_S:
                    d["contagens"]["agiu_no_aviso"] = d["contagens"].get("agiu_no_aviso", 0) + 1
                    d["aviso_pendente"] = 0.0
            else:
                d["contagens"][sinal] = d["contagens"].get(sinal, 0) + 1
            _gravar(d, arq)
    except Exception:
        _engolida("core/adaptacao.py:93")


def _limpar_pendente(d: dict, agora: float) -> None:
    if d["aviso_pendente"] and agora - d["aviso_pendente"] > IGNOROU_APOS_S:
        d["contagens"]["ignorou_aviso"] = d["contagens"].get("ignorou_aviso", 0) + 1
        d["aviso_pendente"] = 0.0


def ajustar(agora: float | None = None, arq=None) -> list[str]:
    """Aplica as mudanças que os sinais justificam. Devolve frases do que mudou."""
    agora = time.time() if agora is None else agora
    mudou = []
    with _trava:
        d = _ler(arq)
        if not d["ligado"]:
            return []
        _limpar_pendente(d, agora)
        for botao, (baixo, alto) in BOTOES.items():
            c = d["contagens"]
            neg, pos = c.get(baixo, 0), c.get(alto, 0)
            n = neg + pos
            if botao in d["travados"] or n < MIN_SINAIS:
                continue
            if agora - d["ultima_mudanca"].get(botao, 0) < INTERVALO_S:
                continue
            if max(neg, pos) / n < TENDENCIA:
                continue
            passo = 1 if pos > neg else -1
            antes = d["botoes"][botao]
            novo = max(1, min(5, antes + passo))
            c[baixo] = c[alto] = 0
            if novo == antes:
                continue
            d["botoes"][botao] = novo
            d["ultima_mudanca"][botao] = agora
            motivo = f"{max(neg, pos)} de {n} sinais apontaram {'para cima' if passo > 0 else 'para baixo'}"
            d["historico"] = (d["historico"] + [{"t": agora, "botao": botao, "de": antes, "para": novo, "motivo": motivo}])[-30:]
            mudou.append(f"{botao}: {antes} → {novo} ({motivo})")
        _gravar(d, arq)
    return mudou


def valor(botao: str, arq=None) -> int:
    return int(_ler(arq)["botoes"].get(botao, 3))


def fator_cooldown(arq=None) -> float:
    """Multiplicador do intervalo entre avisos (proatividade baixa = mais espaçados). 1.0 se desligado."""
    d = _ler(arq)
    return _COOLDOWN[d["botoes"]["proatividade"]] if d["ligado"] else 1.0


def horas_de_silencio(arq=None) -> list[int]:
    d = _ler(arq)
    total = sum(d["horas"])
    if not d["ligado"] or total < MIN_USOS_HORA:
        return []
    return [h for h, n in enumerate(d["horas"]) if n / total < 0.005]


def calar_agora(hora: int | None = None, arq=None) -> bool:
    """True se agora cai numa hora em que você nunca usa — avisos de voz espontâneos esperam."""
    h = datetime.now().hour if hora is None else hora
    return h in horas_de_silencio(arq)


def favoritas(n: int = 5, arq=None) -> list[str]:
    return [k for k, _ in Counter(_ler(arq)["usos"]).most_common(n)]


def bloco_prompt(arq=None) -> str:
    d = _ler(arq)
    if not d["ligado"]:
        return ""
    v = d["botoes"]["verbosidade"]
    linhas = []
    if v in _TEXTO_VERBOSIDADE:
        linhas.append(_TEXTO_VERBOSIDADE[v])
    return ("[ADAPTAÇÃO AO USUÁRIO — ajuste automático] " + " ".join(linhas)) if linhas else ""


def travar(botao: str, valor_: int | None = None, arq=None) -> str:
    if botao not in BOTOES:
        raise ValueError("Botões: " + ", ".join(BOTOES))
    with _trava:
        d = _ler(arq)
        if valor_ is not None:
            d["botoes"][botao] = max(1, min(5, int(valor_)))
        if botao not in d["travados"]:
            d["travados"].append(botao)
        _gravar(d, arq)
    return f"{botao} fixado em {d['botoes'][botao]}; a adaptação não mexe mais nele."


def destravar(botao: str, arq=None) -> None:
    with _trava:
        d = _ler(arq)
        d["travados"] = [b for b in d["travados"] if b != botao]
        _gravar(d, arq)


def reverter(arq=None) -> str:
    with _trava:
        d = _ler(arq)
        if not d["historico"]:
            return "Não há mudança para desfazer."
        h = d["historico"].pop()
        d["botoes"][h["botao"]] = h["de"]
        d["travados"] = list(dict.fromkeys(d["travados"] + [h["botao"]]))   # evita voltar a mudar logo em seguida
        _gravar(d, arq)
        return f"{h['botao']} voltou para {h['de']} (e ficou fixado)."


def esquecer(arq=None) -> None:
    with _trava:
        lig = _ler(arq)["ligado"]
        d = _novo()
        d["ligado"] = lig
        _gravar(d, arq)


def resumo(arq=None) -> str:
    d = _ler(arq)
    if not d["ligado"]:
        return "A adaptação contínua está desligada. Ligada, ajusto o quanto falo e o quanto aviso conforme você usa; só guardo contagens, e você trava ou desfaz."
    b = d["botoes"]
    l = [f"Verbosidade {b['verbosidade']}/5, proatividade {b['proatividade']}/5" + (f" (fixados: {', '.join(d['travados'])})" if d["travados"] else "") + "."]
    hs = horas_de_silencio(arq)
    if hs:
        l.append(f"Silêncio de avisos em {len(hs)} hora(s) em que você nunca usa.")
    if d["usos"]:
        l.append("Mais usadas: " + ", ".join(favoritas(3, arq)) + ".")
    if d["historico"]:
        h = d["historico"][-1]
        l.append(f"Última mudança: {h['botao']} {h['de']}→{h['para']} ({h['motivo']}).")
    return " ".join(l)


def saude() -> tuple[bool, str]:
    return True, "ligada" if ligado() else "desligada (opt-in)"
