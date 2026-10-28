"""Missões de longa duração (3.8) — metas que o NEXUS toca por horas, em segundo plano, e que sobrevivem a reiniciar.

"Organize meu mês", "pesquise e monte o plano da viagem": o NEXUS
  1. PLANEJA  — quebra a meta em passos (ferramentas reais) com dependências;
  2. MOSTRA   — simula o plano (core/simulacao.py) e, se houver passo sensível, espera a sua aprovação do plano;
  3. EXECUTA  — um passo por vez, gravando o estado em disco a cada passo (reiniciou? continua de onde parou);
  4. PARA NAS DECISÕES — passo sensível (enviar, mover, apagar, gastar, controlar o PC) vira uma DECISÃO com o que vai
                mudar de verdade naquele momento; você aprova ou nega pelo painel do celular ou por voz; o que for
                desfazível entra na pilha de desfazer;
  5. CONFERE  — no fim compara o resultado com a meta e, se faltou algo, acrescenta passos (uma vez);
  6. REGISTRA — tudo vai para a auditoria verificável (core/auditoria.py).

As peças que falam com o mundo (planejar, executar, conferir, avisar) são injetadas: nos testes são falsas; no uso
real são o modelo e as ferramentas do NEXUS. Tudo é opt-in: nada inicia sozinho sem você pedir uma missão.
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Callable

from core import simulacao as SIM

PASTA = Path(__file__).resolve().parent.parent / "memory" / "missoes"
MAX_PASSOS_PLANO = 25
MAX_PASSOS_TOTAL = 60
MAX_TENTATIVAS = 2
LIMITE_HORAS = 8
MAX_ATIVAS = 3
MAX_LOG = 200
PROIBIDAS = {"missao", "agent_task", "orchestrate", "dev_agent", "game_updater", "system_update", "desktop_control",
             "neural_core", "fabrica_plugins", "plugin_factory", "computer_use", "rede_nexus", "loja_plugins", "backup_cripto", "shortcut_manager", "focus_mode",
             "recurring_mission", "approvals", "connectors", "advanced_mode", "organize_folder", "travel_mode", "isa_nucleo", "routine_learning",
             "immunity", "long_history", "adaptation"}
ESPERAR = "_esperar"

ESTADOS_FINAIS = ("concluida", "falhou", "cancelada")


class ErroMissao(Exception):
    pass


def _agora() -> float:
    return time.time()


# ── armazenamento ────────────────────────────────────────────────────────────
def _arq(mid: str, pasta: Path | None = None) -> Path:
    if not re.fullmatch(r"[a-z0-9]{6,12}", mid):
        raise ErroMissao("Identificador de missão inválido.")
    return Path(pasta or PASTA) / f"{mid}.json"


def carregar(mid: str, pasta: Path | None = None) -> dict:
    try:
        return json.loads(_arq(mid, pasta).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ErroMissao("Não achei essa missão.") from None
    except ValueError:
        raise ErroMissao("O arquivo da missão está corrompido.") from None


def salvar(m: dict, pasta: Path | None = None) -> None:
    arq = _arq(m["id"], pasta)
    arq.parent.mkdir(parents=True, exist_ok=True)
    m["atualizada"] = _agora()
    m["log"] = m.get("log", [])[-MAX_LOG:]
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(arq)


def todas(pasta: Path | None = None) -> list[dict]:
    out = []
    for f in sorted(Path(pasta or PASTA).glob("*.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    return sorted(out, key=lambda m: -m.get("criada", 0))


def resumo(m: dict) -> dict:
    passos = m.get("plano", [])
    feitos = sum(1 for p in passos if p["estado"] in ("ok", "pulado", "negado"))
    return {"id": m["id"], "objetivo": m["objetivo"], "estado": m["estado"], "passos": len(passos), "feitos": feitos,
            "decisoes": sum(1 for d in m.get("decisoes", []) if d["estado"] == "pendente"),
            "criada": m.get("criada"), "atualizada": m.get("atualizada")}


def _log(m: dict, texto: str) -> None:
    m.setdefault("log", []).append({"t": round(_agora(), 1), "msg": str(texto)[:300]})


# ── plano ────────────────────────────────────────────────────────────────────
def validar_plano(bruto, existe: Callable[[str], bool]) -> tuple[list[dict], list[str]]:
    """Plano limpo (ids p1, p2…, dependências por id) e a lista de avisos do que foi descartado."""
    if not isinstance(bruto, list):
        return [], ["o planejador não devolveu uma lista de passos"]
    plano, avisos = [], []
    mapa: dict[int, str] = {}
    for i, p in enumerate(bruto[:MAX_PASSOS_PLANO], 1):
        if not isinstance(p, dict):
            avisos.append(f"passo {i} malformado")
            continue
        tool = str(p.get("tool") or "").strip()
        args = p.get("args") if isinstance(p.get("args"), dict) else {}
        if tool == ESPERAR:
            try:
                mins = max(1, min(24 * 60, int(float(args.get("minutos", 5)))))
            except (TypeError, ValueError):
                mins = 5
            args = {"minutos": mins}
        elif tool in PROIBIDAS:
            avisos.append(f"passo {i}: '{tool}' não pode ser usado numa missão")
            continue
        elif not existe(tool):
            avisos.append(f"passo {i}: ferramenta '{tool}' não existe")
            continue
        pid = f"p{len(plano) + 1}"
        mapa[i] = pid
        deps = []
        for d in (p.get("depende") or []):
            try:
                if int(d) in mapa and mapa[int(d)] != pid:
                    deps.append(mapa[int(d)])
            except (TypeError, ValueError):
                continue
        plano.append({"id": pid, "titulo": str(p.get("titulo") or tool)[:100], "tool": tool, "args": args,
                      "depende": deps, "estado": "pendente", "resultado": "", "tentativas": 0, "desfazer": "",
                      "risco": "seguro" if tool == ESPERAR else SIM.risco(tool, args)})
    return plano, avisos


def limpar_orcamento(o) -> dict:
    """{horas, chamadas, sensiveis}: só números positivos e sensatos; o resto é ignorado."""
    out = {}
    if isinstance(o, dict):
        for k, teto in (("horas", LIMITE_HORAS), ("chamadas", 500), ("sensiveis", 100)):
            try:
                v = float(o.get(k)) if k == "horas" else int(o.get(k))
            except (TypeError, ValueError):
                continue
            if v > 0:
                out[k] = min(v, teto)
    return out


def texto_ensaio(ensaio: list[dict]) -> str:
    return "\n".join(f"- [{e['modo']}] {e['titulo']}: {e['resultado'][:120]}" for e in ensaio) or "(nada a ensaiar)"


def simular_plano(m: dict) -> dict:
    return SIM.simular([{"tool": p["tool"], "args": p["args"], "titulo": p["titulo"]}
                        for p in m["plano"] if p["estado"] == "pendente" and p["tool"] != ESPERAR])


# ── o motor ──────────────────────────────────────────────────────────────────
class Motor:
    """Executa missões. `planejar(objetivo, contexto) -> list`, `executar(tool, args, ctx) -> (status, texto)`,
    `conferir(objetivo, passos) -> str` (o que faltou, '' = cumprido), `existe(tool) -> bool`, `avisar(texto, urgente)`."""

    def __init__(self, planejar, executar, conferir=None, existe=None, avisar=None, pasta: Path | None = None,
                 desfazer_info=None, desfazer_ultimo=None, auto_aprovar=None, aprendeu=None):
        self.planejar, self.executar = planejar, executar
        self.auto_aprovar = auto_aprovar or (lambda tool, args: False)     # regra "pode fazer sem perguntar" (core/aprovacoes)
        self.aprendeu = aprendeu or (lambda tool, args, aprovou: None)     # anota a sua decisão; devolve texto se vale sugerir
        self.conferir = conferir or (lambda objetivo, passos: "")
        self.existe = existe or (lambda t: True)
        self.avisar = avisar or (lambda texto, urgente=False: None)
        self.pasta = Path(pasta or PASTA)
        self.desfazer_info = desfazer_info or (lambda: (0, ""))          # (tamanho da pilha, rótulo do topo)
        self.desfazer_ultimo = desfazer_ultimo or (lambda: "Nada para desfazer.")
        self._trava = threading.RLock()

    # criação ------------------------------------------------------------------
    def criar(self, objetivo: str, orcamento: dict | None = None, ensaiar: bool = False) -> dict:
        objetivo = re.sub(r"\s+", " ", str(objetivo or "")).strip()[:400]
        if not objetivo:
            raise ErroMissao("Falta a meta: o que devo fazer?")
        if sum(1 for m in todas(self.pasta) if m["estado"] not in ESTADOS_FINAIS) >= MAX_ATIVAS:
            raise ErroMissao(f"Já há {MAX_ATIVAS} missões em andamento; espere uma terminar ou cancele uma.")
        mid = uuid.uuid4().hex[:8]
        m = {"id": mid, "objetivo": objetivo, "estado": "planejando", "criada": _agora(), "plano": [], "decisoes": [],
             "log": [], "replanos": 0, "limite_h": LIMITE_HORAS, "relatorio": "",
             "orcamento": limpar_orcamento(orcamento), "uso": {"chamadas": 0, "sensiveis": 0, "avisados": []}}
        if m["orcamento"].get("horas"):
            m["limite_h"] = min(LIMITE_HORAS, m["orcamento"]["horas"])
        _log(m, "Missão criada; planejando.")
        salvar(m, self.pasta)
        self._auditar(m, "criou a missão", objetivo)
        try:
            bruto = self.planejar(objetivo, "")
        except Exception as e:
            m["estado"], m["relatorio"] = "falhou", f"Não consegui planejar: {e}"
            _log(m, m["relatorio"])
            salvar(m, self.pasta)
            return m
        plano, avisos = validar_plano(bruto, self.existe)
        for a in avisos:
            _log(m, f"Plano: {a}.")
        if not plano:
            m["estado"], m["relatorio"] = "falhou", "O plano ficou vazio (nenhuma ferramenta utilizável)."
            salvar(m, self.pasta)
            return m
        m["plano"] = plano
        sim = simular_plano(m)
        m["simulacao"] = sim
        if ensaiar:
            m["ensaio"] = self._ensaio(m)
        exigem = [p for p in m["plano"] if p["risco"] == "sensivel" and not self.auto_aprovar(p["tool"], p["args"])]
        if exigem or ensaiar:
            m["estado"] = "plano_pronto"
            extra = ("\nENSAIO (nada de escrita foi feito):\n" + texto_ensaio(m["ensaio"])) if ensaiar else ""
            m["decisoes"].append({"id": "plano", "passo": "", "estado": "pendente",
                                  "pergunta": "Posso começar este plano?\n" + SIM.texto(sim) + extra})
            _log(m, "Plano pronto; aguardando a sua aprovação.")
            self.avisar(f"A missão “{objetivo[:60]}” tem um plano com {sim['sensiveis']} passo(s) sensível(is). "
                        "Veja e aprove no painel.", True)
        else:
            m["estado"] = "executando"
            _log(m, "Plano sem passos sensíveis; começando.")
        salvar(m, self.pasta)
        self._auditar(m, "planejou", f"{len(plano)} passos; {sim['resumo']}")
        return m

    # ensaio ---------------------------------------------------------------------
    def _ensaio(self, m: dict) -> list[dict]:
        """Roda o plano 'no seco': leituras de verdade, tudo que escreve/envia/apaga SIMULADO. Nada é salvo no plano."""
        feitos: dict[str, str] = {}
        rel = []
        for p in m["plano"]:
            if p["estado"] not in ("pendente", "aprovado", "esperando"):
                continue
            if any(feitos.get(d) == "falhou" for d in p["depende"]):
                feitos[p["id"]] = "falhou"
                rel.append({"titulo": p["titulo"], "tool": p["tool"], "modo": "pulado", "resultado": "um passo anterior falharia"})
                continue
            if p["tool"] == ESPERAR:
                feitos[p["id"]] = "ok"
                rel.append({"titulo": p["titulo"], "tool": p["tool"], "modo": "pulado",
                            "resultado": f"esperaria {p['args']['minutos']} min"})
            elif p["risco"] == "sensivel":
                feitos[p["id"]] = "ok"
                rel.append({"titulo": p["titulo"], "tool": p["tool"], "modo": "simulado",
                            "resultado": SIM.simular_passo(p)["resumo"]})
            else:
                try:
                    status, texto = self.executar(p["tool"], p["args"], {"ator": "ensaio", "missao": m["id"], "motivo": p["titulo"]})
                except Exception as e:
                    status, texto = "failed", f"erro: {e}"
                feitos[p["id"]] = "ok" if status in ("done", "unverified") else "falhou"
                rel.append({"titulo": p["titulo"], "tool": p["tool"], "modo": "real (leitura)", "resultado": str(texto)[:200]})
        return rel

    def ensaiar(self, mid: str) -> list[dict]:
        with self._trava:
            m = carregar(mid, self.pasta)
            m["ensaio"] = self._ensaio(m)
            _log(m, "Ensaio feito (nada de escrita foi executado).")
            salvar(m, self.pasta)
            self._auditar(m, "ensaiou o plano", f"{len(m['ensaio'])} passos")
            return m["ensaio"]

    # orçamento ------------------------------------------------------------------
    def _orcamento_estourou(self, m: dict, dim: str) -> bool:
        lim = (m.get("orcamento") or {}).get(dim)
        return bool(lim) and m["uso"][dim] >= lim

    def _contar(self, m: dict, dim: str) -> None:
        m["uso"][dim] += 1
        lim = (m.get("orcamento") or {}).get(dim)
        if lim and m["uso"][dim] >= 0.8 * lim and dim not in m["uso"]["avisados"] and m["uso"][dim] < lim:
            m["uso"]["avisados"].append(dim)
            _log(m, f"Orçamento: {m['uso'][dim]} de {lim} {dim} usados (80%).")
            self.avisar(f"Missão “{m['objetivo'][:50]}”: já usou {m['uso'][dim]} de {lim} {dim} do orçamento.", False)

    # decisões -----------------------------------------------------------------
    def decidir(self, mid: str, did: str, aprovar: bool) -> dict:
        with self._trava:
            m = carregar(mid, self.pasta)
            d = next((x for x in m["decisoes"] if x["id"] == did and x["estado"] == "pendente"), None)
            if d is None:
                raise ErroMissao("Essa decisão não está pendente.")
            d["estado"] = "aprovada" if aprovar else "negada"
            d["quando"] = _agora()
            self._auditar(m, "aprovou" if aprovar else "negou", d["pergunta"][:100], tipo="decisao", ator="usuario")
            if did == "plano":
                if aprovar:
                    m["estado"] = "executando"
                    _log(m, "Plano aprovado.")
                else:
                    m["estado"] = "cancelada"
                    m["relatorio"] = "Você não aprovou o plano."
                    _log(m, m["relatorio"])
            else:
                p = next((x for x in m["plano"] if x["id"] == d["passo"]), None)
                if p:
                    try:
                        dica = self.aprendeu(p["tool"], p["args"], aprovar)
                        if dica:
                            self.avisar(dica, False)
                    except Exception:
                        pass
                if p:
                    if aprovar:
                        p["estado"] = "aprovado"
                        _log(m, f"Aprovado: {p['titulo']}.")
                    else:
                        p["estado"], p["resultado"] = "negado", "Você negou este passo."
                        _log(m, f"Negado: {p['titulo']}.")
                if m["estado"] == "aguardando":
                    m["estado"] = "executando"
            salvar(m, self.pasta)
            return m

    def cancelar(self, mid: str) -> dict:
        with self._trava:
            m = carregar(mid, self.pasta)
            if m["estado"] in ESTADOS_FINAIS:
                return m
            m["estado"], m["relatorio"] = "cancelada", "Cancelada por você."
            for d in m["decisoes"]:
                if d["estado"] == "pendente":
                    d["estado"] = "negada"
            _log(m, "Missão cancelada.")
            salvar(m, self.pasta)
            self._auditar(m, "cancelou a missão", m["objetivo"], tipo="decisao", ator="usuario")
            return m

    def pausar(self, mid: str, pausar: bool = True) -> dict:
        with self._trava:
            m = carregar(mid, self.pasta)
            if pausar and m["estado"] == "executando":
                m["estado"] = "pausada"
            elif not pausar and m["estado"] == "pausada":
                m["estado"] = "executando"
            salvar(m, self.pasta)
            return m

    def desfazer(self, mid: str) -> str:
        """Desfaz a última ação desfazível da missão (a pilha de desfazer do NEXUS é global: só o topo)."""
        with self._trava:
            m = carregar(mid, self.pasta)
            ultimo = next((p for p in reversed(m["plano"]) if p.get("desfazer") and p["estado"] == "ok"), None)
            if ultimo is None:
                return "Nenhum passo desta missão pode ser desfeito."
            n, topo = self.desfazer_info()
            if not n or topo != ultimo["desfazer"]:
                return ("Outra ação mais recente está na frente na pilha de desfazer; desfaça ela primeiro ou use 'desfaz' "
                        "uma vez por ação.")
            msg = self.desfazer_ultimo()
            ultimo["estado"], ultimo["desfazer"] = "desfeito", ""
            _log(m, f"Desfeito: {ultimo['titulo']}.")
            salvar(m, self.pasta)
            self._auditar(m, "desfez", ultimo["titulo"], tipo="decisao", ator="usuario")
            return msg

    # um passo -----------------------------------------------------------------
    def _prontos(self, m: dict) -> list[dict]:
        por_id = {p["id"]: p for p in m["plano"]}
        prontos = []
        for p in m["plano"]:
            if p["estado"] not in ("pendente", "aprovado", "esperando"):
                continue
            ds = [por_id[d]["estado"] for d in p["depende"] if d in por_id]
            if any(s in ("falhou", "negado", "pulado") for s in ds):
                p["estado"], p["resultado"] = "pulado", "Pulado: um passo anterior não deu certo."
                continue
            if all(s in ("ok", "desfeito") for s in ds):
                if p["estado"] == "esperando" and p.get("libera_em", 0) > _agora():
                    continue
                prontos.append(p)
        return prontos

    def passo(self, mid: str) -> str:
        """Avança UMA coisa. Devolve: 'trabalhou' | 'espera' (decisão ou espera de tempo) | 'fim' | 'parada'."""
        with self._trava:
            m = carregar(mid, self.pasta)
            if m["estado"] in ESTADOS_FINAIS:
                return "fim"
            if m["estado"] in ("planejando", "plano_pronto", "pausada"):
                return "parada"
            if _agora() - m["criada"] > m.get("limite_h", LIMITE_HORAS) * 3600:
                return self._encerrar(m, "falhou", f"Passou do limite de {m.get('limite_h', LIMITE_HORAS)} horas.")
            if sum(1 for p in m["plano"] if p["estado"] in ("ok", "falhou")) >= MAX_PASSOS_TOTAL:
                return self._encerrar(m, "falhou", "Passou do máximo de passos por missão.")
            prontos = self._prontos(m)
            for p in prontos:
                if p["tool"] == ESPERAR:
                    if p["estado"] != "esperando":
                        p["estado"], p["libera_em"] = "esperando", _agora() + p["args"]["minutos"] * 60
                        _log(m, f"Esperando {p['args']['minutos']} min: {p['titulo']}.")
                        salvar(m, self.pasta)
                        return "trabalhou"
                    p["estado"], p["resultado"] = "ok", "Espera concluída."
                    salvar(m, self.pasta)
                    return "trabalhou"
                if p["risco"] == "sensivel" and self._orcamento_estourou(m, "sensiveis"):
                    p["estado"], p["resultado"] = "negado", "Orçamento de passos sensíveis esgotado."
                    _log(m, f"Orçamento de passos sensíveis esgotado: {p['titulo']} não foi feito.")
                    salvar(m, self.pasta)
                    return "trabalhou"
                if p["risco"] == "sensivel" and p["estado"] != "aprovado" and self.auto_aprovar(p["tool"], p["args"]):
                    p["estado"] = "aprovado"
                    _log(m, f"Regra sua: “{p['titulo']}” pode ser feito sem perguntar.")
                    self._auditar(m, "aprovou pela regra automática", p["titulo"], tipo="decisao", ator="regra")
                if p["risco"] == "sensivel" and p["estado"] != "aprovado":
                    if not any(d["passo"] == p["id"] and d["estado"] == "pendente" for d in m["decisoes"]):
                        sim = SIM.simular_passo(p)
                        m["decisoes"].append({"id": f"d{len(m['decisoes'])}", "passo": p["id"], "estado": "pendente",
                                              "pergunta": f"{p['titulo']}: {sim['resumo']}"})
                        p["estado"] = "aguardando_decisao"
                        _log(m, f"Preciso da sua decisão: {p['titulo']}.")
                        self.avisar(f"Missão “{m['objetivo'][:50]}”: preciso da sua decisão — {sim['resumo']}.", True)
                        salvar(m, self.pasta)
                        return "trabalhou"
                    continue
                return self._rodar(m, p)
            salvar(m, self.pasta)
            esperando = [p for p in m["plano"] if p["estado"] in ("aguardando_decisao", "esperando")]
            if esperando:
                if any(p["estado"] == "aguardando_decisao" for p in esperando) and m["estado"] != "aguardando":
                    m["estado"] = "aguardando"
                    salvar(m, self.pasta)
                return "espera"
            if any(p["estado"] in ("pendente", "aprovado") for p in m["plano"]):
                return "espera"
            return self._finalizar(m)

    def _rodar(self, m: dict, p: dict) -> str:
        if self._orcamento_estourou(m, "chamadas"):
            return self._encerrar(m, "falhou", f"Orçamento de {m['orcamento']['chamadas']} chamadas esgotado. "
                                                f"{sum(1 for x in m['plano'] if x['estado'] == 'ok')} passos concluídos até aqui.")
        self._contar(m, "chamadas")
        if p["risco"] == "sensivel":
            self._contar(m, "sensiveis")
        antes, _ = self.desfazer_info()
        p["estado"] = "rodando"
        p["tentativas"] += 1
        salvar(m, self.pasta)
        ctx = {"ator": "missao", "missao": m["id"], "motivo": p["titulo"]}
        try:
            status, texto = self.executar(p["tool"], p["args"], ctx)
        except Exception as e:
            status, texto = "failed", f"erro: {e}"
        p["resultado"] = str(texto)[:2000]
        if status in ("done", "unverified"):
            p["estado"] = "ok"
            p["verificado"] = status == "done"
            depois, topo = self.desfazer_info()
            if depois > antes:
                p["desfazer"] = topo
            _log(m, f"✔ {p['titulo']} ({status}).")
        else:
            p["estado"] = "pendente" if p["tentativas"] < MAX_TENTATIVAS else "falhou"
            _log(m, f"✘ {p['titulo']}: {str(texto)[:100]}" + (" — vou tentar de novo." if p["estado"] == "pendente" else ""))
        self._auditar(m, f"executou {p['tool']}", p["titulo"], resultado=f"[{status}] {str(texto)[:120]}")
        salvar(m, self.pasta)
        return "trabalhou"

    def _finalizar(self, m: dict) -> str:
        passos = [{"tool": p["tool"], "titulo": p["titulo"], "status": p["estado"], "result": p["resultado"]}
                  for p in m["plano"]]
        falta = ""
        try:
            falta = self.conferir(m["objetivo"], passos) if m["replanos"] < 1 else ""
        except Exception:
            falta = ""
        if falta:
            m["replanos"] += 1
            _log(m, f"Conferindo: ainda falta — {falta[:120]}")
            try:
                extra, avisos = validar_plano(self.planejar(m["objetivo"], f"JÁ FEITO: {json.dumps(passos, ensure_ascii=False)[:3000]}. FALTA: {falta}"),
                                              self.existe)
            except Exception:
                extra = []
            n0 = len(m["plano"])
            for p in extra[:8]:
                p["id"] = f"p{len(m['plano']) + 1}"
                p["depende"] = []
                m["plano"].append(p)
            if len(m["plano"]) > n0:
                self._auditar(m, "replanejou", falta[:100])
                salvar(m, self.pasta)
                return "trabalhou"
        ok = sum(1 for p in m["plano"] if p["estado"] == "ok")
        ruins = [p for p in m["plano"] if p["estado"] in ("falhou", "negado", "pulado")]
        linhas = [f"Missão: {m['objetivo']}", f"{ok} de {len(m['plano'])} passos concluídos."]
        linhas += [f"- {p['titulo']}: {p['resultado'][:160]}" for p in m["plano"] if p["estado"] == "ok"][:12]
        if ruins:
            linhas.append("Não deu certo / não feito: " + "; ".join(f"{p['titulo']} ({p['estado']})" for p in ruins))
        return self._encerrar(m, "concluida" if ok else "falhou", "\n".join(linhas))

    def _encerrar(self, m: dict, estado: str, relatorio: str) -> str:
        m["estado"], m["relatorio"] = estado, relatorio
        _log(m, f"Missão {estado}.")
        salvar(m, self.pasta)
        self._auditar(m, f"encerrou como {estado}", m["objetivo"], resultado=relatorio[:150])
        linhas = relatorio.splitlines()
        self.avisar(f"Missão “{m['objetivo'][:60]}” {estado}." + (f" {linhas[1]}" if len(linhas) > 1 else ""), False)
        return "fim"

    def _auditar(self, m: dict, o_que: str, detalhe: str = "", resultado: str = "", tipo: str = "acao", ator: str = "missao") -> None:
        try:
            from core import auditoria
            auditoria.registrar(tipo, ator, o_que, {"detalhe": detalhe}, motivo=m["objetivo"][:120], resultado=resultado,
                                missao=m["id"])
        except Exception:
            pass

    def rodar_ate_parar(self, mid: str, limite: int = 200) -> str:
        """Roda passos até algo precisar de gente/tempo ou acabar (usado nos testes e pelo laço de fundo)."""
        r = "parada"
        for _ in range(limite):
            r = self.passo(mid)
            if r != "trabalhou":
                break
        return r


# ── texto para voz / painel ──────────────────────────────────────────────────
def texto_status(m: dict) -> str:
    r = resumo(m)
    s = f"Missão {m['id']} “{m['objetivo'][:70]}”: {m['estado']}, {r['feitos']} de {r['passos']} passos."
    pend = [d for d in m.get("decisoes", []) if d["estado"] == "pendente"]
    if pend:
        s += " Esperando sua decisão: " + " | ".join(d["pergunta"].splitlines()[0][:120] for d in pend)
    return s


class Gerente:
    """Roda as missões em threads de fundo e retoma as que estavam em andamento quando o NEXUS reinicia."""

    def __init__(self, motor: Motor, ritmo_s: float = 2.0):
        self.motor, self.ritmo_s = motor, ritmo_s
        self._threads: dict[str, threading.Thread] = {}
        self._parar = threading.Event()

    def iniciar(self, mid: str) -> None:
        t = self._threads.get(mid)
        if t and t.is_alive():
            return
        t = threading.Thread(target=self._laco, args=(mid,), daemon=True, name=f"missao-{mid}")
        self._threads[mid] = t
        t.start()

    def retomar_todas(self) -> int:
        n = 0
        for m in todas(self.motor.pasta):
            if m["estado"] in ("executando", "aguardando", "pausada"):
                self.iniciar(m["id"])
                n += 1
        return n

    def _laco(self, mid: str) -> None:
        espera_sem_trabalho = 0
        while not self._parar.is_set():
            try:
                r = self.motor.passo(mid)
            except Exception:
                r = "fim"
            if r == "fim":
                return
            if r == "trabalhou":
                espera_sem_trabalho = 0
                self._parar.wait(self.ritmo_s)
            else:                                   # decisão pendente, espera de tempo ou plano por aprovar: olha de novo logo
                espera_sem_trabalho = min(espera_sem_trabalho + 1, 30)
                self._parar.wait(min(30.0, 1.0 * espera_sem_trabalho))

    def parar(self) -> None:
        self._parar.set()
