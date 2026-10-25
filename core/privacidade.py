"""Painel de privacidade (NEXUS Ultra 2026 3.3): o que o NEXUS guarda, o que sai do PC e como apagar.

  • GUARDADO  — cada arquivo de dados do NEXUS, com o que é, quando mudou e o tamanho;
  • SAI DO PC — as vezes em que algo vai para fora (serviços que você usa), dito sem enfeite;
  • APAGAR    — um item por vez, SEMPRE com confirmação ("apaga o diário" mostra o que vai sumir e pede o seu "sim").

Não são apagáveis por aqui: chaves de API, licença e configuração do app (só dados que o NEXUS aprendeu ou
guardou). Os relatórios em Documentos são seus arquivos e ficam onde estão.
"""
from __future__ import annotations

import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MEM, CFG = RAIZ / "memory", RAIZ / "config"


@dataclass(frozen=True)
class Item:
    chave: str
    nome: str
    arquivos: tuple[Path, ...]
    o_que: str


CATALOGO: tuple[Item, ...] = (
    Item("conversas", "Conversas", (MEM / "conversations.json", MEM / "sessao.json"), "o histórico do que você e o NEXUS conversaram"),
    Item("fatos", "O que sei sobre você", (MEM / "facts.json", MEM / "long_term.json", CFG / "facts.json"), "fatos e preferências que você me contou"),
    Item("diario", "Diário e humor", (MEM / "diario.json",), "o que você escreveu no diário e as notas de humor"),
    Item("notas", "Anotações rápidas", (CFG / "quick_notes.json",), "as anotações soltas"),
    Item("tarefas", "Tarefas e projetos", (MEM / "tarefas.json", MEM / "projetos.json"), "a sua lista de afazeres e projetos"),
    Item("lembretes", "Lembretes", (MEM / "reminders.json",), "os avisos agendados (os avisos já criados no sistema continuam)"),
    Item("habitos", "Hábitos e rotinas", (MEM / "habits.json", MEM / "habitos_diarios.json", MEM / "previsao_habitos.json",
                                         MEM / "routines.json", MEM / "resumo_semanal.json"), "o que você repete, rotinas e o resumo semanal"),
    Item("autoavaliacao", "Auto-avaliação e latência", (MEM / "autoavaliacao.json", MEM / "latencia.json", MEM / "metricas.csv",
                                                        MEM / "roteador_exemplos.json", MEM / "intent_examples.json"),
         "como o NEXUS se saiu, o tempo de resposta e o que o roteador aprendeu"),
    Item("financas", "Finanças e compras", (CFG / "finance_entries.json", CFG / "finance_budgets.json", MEM / "compras.json",
                                           MEM / "price_alerts.json"), "gastos, orçamentos, compras e alertas de preço"),
    Item("contatos", "Contatos", (MEM / "contatos.json",), "os contatos que você cadastrou"),
    Item("casa", "Casa e foco", (CFG / "casa.json", CFG / "focus_state.json"), "dispositivos da casa e estado do modo foco"),
    Item("registros", "Registros do app", (MEM / "activity.log", MEM / "audit.log", MEM / "falhas.log",
                                           MEM / "queda_nativa.log", MEM / "reconexoes.log"), "logs de atividade, auditoria e erros"),
    Item("perfil", "Perfil de uso", (MEM / "perfil.json",), "o perfil ligado (Trabalho, Estudo, Jogo)"),
)

SAI_DO_PC = (
    ("Conversa por voz no modo Gemini Live", "O áudio e o texto da conversa vão para a Google enquanto você conversa. "
     "Isso não acontece no motor próprio."),
    ("Conversa no motor próprio", "A transcrição (Whisper), o modelo (Ollama) e a voz rodam no seu PC; só sai algo "
     "se você configurou um modelo em nuvem."),
    ("Pesquisa, clima e notícias", "O texto da consulta vai para o serviço que responde (busca, previsão, notícias)."),
    ("E-mail, GitHub e atualização", "Só quando você pede: o NEXUS fala com a sua conta de e-mail e com o GitHub "
     "para verificar atualizações."),
    ("Tudo o mais", "Diário, anotações, tarefas, finanças, contatos, hábitos e métricas ficam só no seu PC."),
)


def _sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(t or "").lower()) if unicodedata.category(c) != "Mn")


def _tam(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    return f"{n / 1024:.0f} KB" if n < 1048576 else f"{n / 1048576:.1f} MB".replace(".", ",")


def estado(catalogo=CATALOGO) -> list[dict]:
    """[{'chave','nome','o_que','existe','bytes','tamanho','mudou'}] — só os itens que existem no PC vêm com existe=True."""
    out = []
    for it in catalogo:
        total, ultimo, achou = 0, 0.0, False
        for a in it.arquivos:
            try:
                st = a.stat()
                total += st.st_size
                ultimo = max(ultimo, st.st_mtime)
                achou = True
            except OSError:
                continue
        out.append({"chave": it.chave, "nome": it.nome, "o_que": it.o_que, "existe": achou, "bytes": total,
                    "tamanho": _tam(total) if achou else "—",
                    "mudou": time.strftime("%d/%m/%Y", time.localtime(ultimo)) if achou else "—"})
    return out


def resolver(texto: str, catalogo=CATALOGO) -> Item | None:
    t = _sem_acento(texto)
    if not t.strip():
        return None
    sinonimos = {"conversas": ("conversa", "historico"), "fatos": ("fato", "sobre mim", "memoria"),
                 "diario": ("diario", "humor"), "notas": ("nota", "anotac"), "tarefas": ("tarefa", "projeto"),
                 "lembretes": ("lembrete",), "habitos": ("habito", "rotina"),
                 "autoavaliacao": ("avaliac", "latencia", "metrica", "roteador"),
                 "financas": ("financ", "gasto", "compra"), "contatos": ("contato",),
                 "casa": ("casa", "foco"), "registros": ("registro", "log", "auditoria"), "perfil": ("perfil",)}
    for it in catalogo:
        if it.chave in t or _sem_acento(it.nome) in t or any(s in t for s in sinonimos.get(it.chave, ())):
            return it
    return None


def resumo_texto() -> str:
    itens = [e for e in estado() if e["existe"]]
    if not itens:
        return "Ainda não guardei nada no seu computador."
    lista = "; ".join(f"{e['nome']} ({e['tamanho']})" for e in itens)
    return f"Guardo no seu computador: {lista}. Para saber o que sai do PC, pergunte “o que sai do meu computador?”."


def sai_texto() -> str:
    return " ".join(f"{t}: {d}" for t, d in SAI_DO_PC)


def apagar(alvo: str, confirmar: bool = False, catalogo=CATALOGO) -> str:
    """Sem confirmar=True só descreve o que seria apagado. Com ele, apaga os arquivos daquele item."""
    if _sem_acento(alvo).strip() in ("tudo", "todos", "tudo isso"):
        itens = [it for it in catalogo if any(a.exists() for a in it.arquivos)]
        nome = "TUDO o que o NEXUS guardou"
    else:
        it = resolver(alvo, catalogo)
        if it is None:
            return "[failed] Não sei qual item apagar. Os itens são: " + ", ".join(i.nome for i in catalogo) + "."
        itens, nome = [it], it.nome
    arqs = [a for it in itens for a in it.arquivos if a.exists()]
    if not arqs:
        return f"Não há nada guardado em “{nome}”."
    if not confirmar:
        return (f"Isso apaga {nome} ({len(arqs)} arquivo(s), {_tam(sum(a.stat().st_size for a in arqs))}) e não dá "
                "para desfazer. Pergunte ao usuário se quer mesmo apagar e só então repita o pedido com a confirmação.")
    apagados = 0
    for a in arqs:
        try:
            a.unlink()
            apagados += 1
        except OSError:
            continue
    try:
        from core import cache_respostas
        cache_respostas.limpar()
    except Exception:
        pass
    if apagados < len(arqs):
        return f"Apaguei {apagados} de {len(arqs)} arquivo(s) de {nome}; algum está em uso e fica para depois."
    return f"Pronto, apaguei {nome}."
