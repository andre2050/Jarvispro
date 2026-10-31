"""Como a IA do NEXUS funciona (NEXUS Ultra 2026) — o estado real das quatro áreas.

Uma só fonte para o painel (ui/overlays/ia_painel.py) e para a voz
(actions/explicar_ia.py): para cada área da IA — machine learning, aprendizado
profundo, linguagem natural e visão computacional — diz O QUE É (em palavras
simples) e O QUE O NEXUS TEM de verdade agora (modelo pronto? quantos exemplos?
qual a precisão?).

Regras deste módulo:
  • só LÊ o estado; nunca treina, baixa ou instala nada;
  • nunca levanta erro — o que não der para ler vira "indisponível";
  • nada sai do computador.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from core.protecao import engolida as _engolida

# ── O que é cada área (texto curto, para tela e para voz) ───────────────────

AREAS = ("ml", "dl", "pln", "visao")

CONCEITOS: dict[str, dict[str, str]] = {
    "ml": {
        "titulo": "Machine learning",
        "icone": "📈",
        "resumo": ("Os sistemas aprendem com os dados a achar padrões e a prever ou decidir, "
                   "sem alguém programar cada regra. É como mostrar milhares de fotos de pássaros "
                   "a um computador até ele aprender sozinho como um pássaro se parece."),
        "no_nexus": "Aprende os seus hábitos, percebe quando o PC fica estranho e escolhe o modelo certo para cada pedido.",
    },
    "dl": {
        "titulo": "Aprendizado profundo",
        "icone": "🧠",
        "resumo": ("Um ramo do machine learning que usa redes neurais com muitas camadas, inspiradas no "
                   "cérebro. É muito boa em tarefas complexas, como reconhecer imagem e fala."),
        "no_nexus": "As redes neurais locais rodam em Keras/TensorFlow, com NumPy como reserva.",
    },
    "pln": {
        "titulo": "Linguagem natural",
        "icone": "💬",
        "resumo": ("O processamento de linguagem natural faz o computador entender, interpretar e gerar a "
                   "linguagem humana. É o que move assistentes de voz, tradutores e chatbots."),
        "no_nexus": "Entende o que você pede, mesmo com erro de digitação, e busca nas suas notas pelo sentido, não só pela palavra.",
    },
    "visao": {
        "titulo": "Visão computacional",
        "icone": "👁",
        "resumo": ("Permite ao computador ver e interpretar imagens e vídeos, do reconhecimento facial "
                   "aos carros autônomos."),
        "no_nexus": "Lê o texto da tela (OCR) e descreve imagens, a tela e a câmera.",
    },
}

BASE = ("Todas as áreas dependem de três coisas: dados (quanto mais e melhores, melhor o desempenho), "
        "algoritmos e poder computacional.")


@dataclass
class ItemIA:
    nome: str
    valor: str
    ok: bool | None = None      # True = pronto · False = faltando · None = só informação


@dataclass
class AreaIA:
    chave: str
    titulo: str
    icone: str
    resumo: str
    no_nexus: str
    itens: list[ItemIA] = field(default_factory=list)

    @property
    def prontos(self) -> tuple[int, int]:
        """(quantos itens estão prontos, quantos têm estado de pronto/faltando)."""
        marcados = [i for i in self.itens if i.ok is not None]
        return sum(1 for i in marcados if i.ok), len(marcados)


def _pct(x) -> str:
    try:
        return f"{float(x) * 100:.0f}%".replace(".", ",")
    except (TypeError, ValueError):
        return "—"


def _n(x) -> str:
    try:
        return f"{int(x):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


# ── Cada área: lê o estado dos módulos que já existem ───────────────────────

def _motor() -> tuple[str, bool]:
    """('Keras 3.x sobre TensorFlow 2.x' | 'NumPy', usando_keras) sem forçar o import do TensorFlow."""
    try:
        from core import neural_backend as nb
        estado = getattr(nb, "_estado", {}) or {}
        if estado.get("nome"):
            return nb.descricao(), estado["nome"] == "keras"
        if nb.tf_instalado():
            return "Keras/TensorFlow (carrega no primeiro uso)", True
        return "NumPy (TensorFlow não instalado)", False
    except Exception:
        return "indisponível", False


def _ml() -> list[ItemIA]:
    itens: list[ItemIA] = []
    try:
        from core import previsao_habitos as ph
        rel = ph.relatorio()
        if rel:
            partes = []
            if rel.get("eventos") is not None:
                partes.append(f"{_n(rel['eventos'])} registros")
            if rel.get("top1") is not None:
                partes.append(f"acerta {_pct(rel['top1'])} (3 palpites: {_pct(rel.get('top3'))})")
            itens.append(ItemIA("Previsão de hábitos", ", ".join(partes) or "treinada", True))
        else:
            itens.append(ItemIA("Previsão de hábitos", "ainda aprendendo seus hábitos", False))
    except Exception:
        itens.append(ItemIA("Previsão de hábitos", "indisponível", False))
    try:
        from core import anomalia
        if anomalia.treinado():
            rel = anomalia.relatorio()
            n = rel.get("amostras")
            itens.append(ItemIA("Detector de anomalias do PC", f"treinado com {_n(n)} medidas" if n else "treinado", True))
        else:
            itens.append(ItemIA("Detector de anomalias do PC", "coletando medidas do PC", False))
    except Exception:
        itens.append(ItemIA("Detector de anomalias do PC", "indisponível", False))
    try:
        from core.roteador_modelos import roteador
        itens.append(ItemIA("Roteador de modelos (rápido / forte / equipe)",
                            "pronto" if roteador.pronto else "treina no primeiro uso", bool(roteador.pronto)))
    except Exception:
        itens.append(ItemIA("Roteador de modelos", "indisponível", False))
    try:
        from core import autoavaliacao as AV
        r = AV.relatorio()
        if r["total"]:
            itens.append(ItemIA("Auto-avaliação", f"{r['total']} pedidos medidos · {r['ajustes_total']} ajuste(s) no roteador", True))
        else:
            itens.append(ItemIA("Auto-avaliação", "mede os pedidos a partir do próximo uso", None))
    except Exception:
        itens.append(ItemIA("Auto-avaliação", "indisponível", False))
    try:
        from core import memoria_semanal as MS
        u = MS.ultimo()
        itens.append(ItemIA("Memória semanal", f"resumo da semana {u['semana']} guardado" if u
                            else "o primeiro resumo sai nesta semana", True if u else None))
    except Exception:
        itens.append(ItemIA("Memória semanal", "indisponível", False))
    return itens


def _dl() -> list[ItemIA]:
    desc, keras = _motor()
    itens = [ItemIA("Motor das redes neurais", desc, True if desc != "indisponível" else False)]
    itens.append(ItemIA("Camadas", "várias camadas ocultas (MLP profundo, GELU/ReLU, regularização)", None))
    try:
        from core.intent_net import brain
        st = brain.stats()
        if st.get("val_acc") is None:
            itens.append(ItemIA("Rede de intenções", "carrega e treina no primeiro uso (leva poucos segundos)",
                                True if brain.ready else None))
        else:
            itens.append(ItemIA("Rede de intenções",
                                f"{st.get('status', '—')} · precisão {_pct(st['val_acc'])} · {_n(st.get('samples'))} exemplos",
                                bool(brain.ready)))
    except Exception:
        itens.append(ItemIA("Rede de intenções", "indisponível", False))
    return itens


def _pln() -> list[ItemIA]:
    itens: list[ItemIA] = []
    try:
        from core.intent_net import brain, INTENTS
        st = brain.stats()
        itens.append(ItemIA("Entende pedidos", f"{_n(st.get('intents', len(INTENTS) - 1))} intenções, com tolerância a erro de digitação",
                            bool(brain.ready)))
        itens.append(ItemIA("Aprende com você", f"{_n(st.get('user_examples', 0))} exemplos seus guardados", None))
    except Exception:
        itens.append(ItemIA("Entende pedidos", "indisponível", False))
    try:
        from core.indice_semantico import indice
        idx = indice()
        total = len(getattr(idx, "docs", []) or [])
        motor = getattr(idx, "motor", "") or "—"
        itens.append(ItemIA("Busca pelo sentido", f"{_n(total)} itens indexados · motor {motor}" if total
                            else "índice vazio (monte pela busca semântica)", total > 0))
    except Exception:
        itens.append(ItemIA("Busca pelo sentido", "indisponível", False))
    itens.append(ItemIA("Conversa e voz", "Gemini Live fala e entende o português", None))
    return itens


def _visao() -> list[ItemIA]:
    itens: list[ItemIA] = []
    try:
        from core import visao_local as vl
        sit = vl.situacao()
        ocr = sit.get("ocr") or []
        itens.append(ItemIA("Ler o texto da tela (OCR)", ", ".join(ocr) if ocr else "nenhum motor instalado", bool(ocr)))
        if sit.get("ollama"):
            itens.append(ItemIA("Descrever imagens offline", sit.get("modelo") or "Ollama no ar", True))
        else:
            itens.append(ItemIA("Descrever imagens offline", "Ollama não encontrado", False))
    except Exception:
        itens.append(ItemIA("Visão local", "indisponível", False))
    itens.append(ItemIA("Tela e câmera", "o Gemini enxerga a tela e a câmera quando você pede", None))
    return itens


_COLETORES = {"ml": _ml, "dl": _dl, "pln": _pln, "visao": _visao}


def area(chave: str) -> AreaIA:
    c = CONCEITOS[chave]
    try:
        itens = _COLETORES[chave]()
    except Exception:
        itens = [ItemIA("Estado", "indisponível", False)]
    return AreaIA(chave, c["titulo"], c["icone"], c["resumo"], c["no_nexus"], itens)


def tudo() -> list[AreaIA]:
    return [area(k) for k in AREAS]


# ── Texto corrido, para a voz ───────────────────────────────────────────────

_ALIAS = {
    "ml": "ml", "machine": "ml", "machine learning": "ml", "aprendizado de maquina": "ml",
    "aprendizado": "ml", "dados": "ml",
    "dl": "dl", "profundo": "dl", "aprendizado profundo": "dl", "deep": "dl", "rede neural": "dl",
    "redes neurais": "dl", "neural": "dl",
    "pln": "pln", "nlp": "pln", "linguagem": "pln", "linguagem natural": "pln",
    "processamento de linguagem natural": "pln",
    "visao": "visao", "visão": "visao", "visao computacional": "visao", "visão computacional": "visao",
    "imagem": "visao", "ver": "visao",
}


def resolver_area(texto: str | None) -> str | None:
    """'machine learning' → 'ml'. Aceita o nome da área em português ou inglês; None = visão geral."""
    t = (texto or "").strip().lower()
    if not t:
        return None
    t = t.replace("ã", "a").replace("á", "a").replace("â", "a").replace("é", "e").replace("ê", "e") \
         .replace("í", "i").replace("ó", "o").replace("ô", "o").replace("ú", "u").replace("ç", "c")
    if t in _ALIAS:
        return _ALIAS[t]
    for chave in sorted(_ALIAS, key=len, reverse=True):
        base = chave.replace("ã", "a").replace("á", "a").replace("é", "e").replace("ç", "c")
        if base in t:
            return _ALIAS[chave]
    return None


def _frase_estado(a: AreaIA) -> str:
    prontos, total = a.prontos
    if not total:
        return ""
    if prontos == total:
        return f"Aqui no seu PC, tudo isso está pronto ({prontos} de {total})."
    faltam = [i.nome for i in a.itens if i.ok is False]
    return (f"Aqui no seu PC, {prontos} de {total} partes estão prontas; "
            f"ainda faltam: {', '.join(faltam)}.")


def explicar(chave: str | None = None) -> str:
    """O que é a área + o que o NEXUS tem dela agora. Sem área: visão geral das quatro."""
    if chave in CONCEITOS:
        a = area(chave)
        return f"{a.titulo}: {a.resumo} No NEXUS: {a.no_nexus} {_frase_estado(a)}".strip()
    linhas = [BASE]
    for a in tudo():
        prontos, total = a.prontos
        sufixo = f" ({prontos} de {total} prontas)" if total else ""
        linhas.append(f"{a.titulo}{sufixo}: {a.no_nexus}")
    return " ".join(linhas)


# ── Tipos de IA: por capacidade e por funcionalidade ────────────────────────
# `existe` diz a verdade sobre hoje; `nexus` diz onde o NEXUS se encaixa.

@dataclass(frozen=True)
class TipoIA:
    chave: str
    sigla: str
    titulo: str
    existe: bool
    resumo: str
    exemplos: str
    risco: str
    nexus: str


TIPOS_CAPACIDADE: tuple[TipoIA, ...] = (
    TipoIA("ani", "ANI", "Inteligência artificial estreita", True,
           "É a única forma de IA que existe hoje. É feita para uma tarefa específica: identificar imagens, "
           "conversar, filtrar e-mails. Não tem raciocínio nem autoconsciência: combina dados com um algoritmo "
           "para prever dentro de limites predefinidos.",
           "Assistentes de voz, reconhecimento facial e modelos de linguagem como o Gemini.",
           "Dados de treino ruins geram resultados tendenciosos ou imprecisos, o que pesa em aprovação de "
           "empréstimo, contratação e policiamento. Golpistas também usam essa IA para fraudes sofisticadas.",
           "O NEXUS é uma ANI: um assistente de voz que junta o Gemini, redes neurais locais e regras. "
           "Ele não pensa como uma pessoa nem tem consciência."),
    TipoIA("agi", "AGI", "Inteligência artificial geral", False,
           "É uma etapa futura proposta: uma IA capaz de uma ampla gama de tarefas, com raciocínio parecido "
           "com o humano para aprender, se adaptar e melhorar sozinha.",
           "Só na ficção, como os dróides de Star Wars.",
           "Levanta preocupações éticas e de segurança: sem regulação, alguém poderia programá-la com más intenções.",
           "O NEXUS não é uma AGI. Ele só faz bem o que foi preparado para fazer."),
    TipoIA("asi", "ASI", "Superinteligência artificial", False,
           "É a forma teórica mais avançada: uma entidade autoconsciente, além do controle humano, que superaria "
           "a inteligência humana em raciocínio, criatividade e até inteligência emocional.",
           "Apenas teórica.",
           "Alguns pesquisadores veem uma chance pequena, mas não desprezível, de resultados extremamente ruins, "
           "incluindo ameaça existencial à humanidade.",
           "O NEXUS está muito longe disso: ele só age dentro das permissões que você liberou no atuador."),
)

TIPOS_FUNCAO: tuple[TipoIA, ...] = (
    TipoIA("reativa", "", "Máquinas reativas", True,
           "IA limitada que só reage a estímulos com base em regras pré-programadas. Não tem memória e não "
           "aprende com dados novos.",
           "O Deep Blue da IBM, que venceu o campeão de xadrez Garry Kasparov em 1997.",
           "",
           "Parte do NEXUS é reativa: as rotinas e os comandos fixos (abrir app, volume, timer) seguem regras."),
    TipoIA("memoria", "", "Memória limitada", True,
           "É a maioria da IA moderna. Usa memória para melhorar com o tempo, treinando com novos dados em redes "
           "neurais ou outros modelos. É uma memória de curto prazo, que costuma zerar quando a sessão acaba.",
           "Carros autônomos que observam outros veículos e chatbots como o Gemini, que lembram das mensagens "
           "anteriores da conversa.",
           "",
           "O NEXUS é principalmente de memória limitada: lembra da conversa, aprende com seus pedidos e hábitos, "
           "e ainda guarda memória no seu PC entre as sessões."),
    TipoIA("mente", "", "Teoria da mente", False,
           "A pesquisa avança, mas ela é só uma possibilidade. Seria uma IA capaz de emular a mente humana, decidir como "
           "um humano, reconhecer e lembrar emoções e reagir em situações sociais como uma pessoa.",
           "Nenhum até agora.",
           "",
           "O NEXUS não tem teoria da mente: ele não sente emoções nem entende situações sociais como uma pessoa."),
)

_TIPOS = {t.chave: t for t in TIPOS_CAPACIDADE + TIPOS_FUNCAO}
_TIPO_ALIAS = {
    "ani": "ani", "estreita": "ani", "fraca": "ani", "narrow": "ani",
    "agi": "agi", "geral": "agi", "general": "agi",
    "asi": "asi", "super": "asi", "superinteligencia": "asi", "superinteligência": "asi",
    "reativa": "reativa", "reativas": "reativa", "deep blue": "reativa",
    "memoria": "memoria", "memória": "memoria", "memoria limitada": "memoria", "memória limitada": "memoria",
    "mente": "mente", "teoria da mente": "mente", "emocoes": "mente", "emoções": "mente",
}


def tipo(chave: str) -> TipoIA:
    return _TIPOS[chave]


def resolver_tipo(texto: str | None) -> str | None:
    t = (texto or "").strip().lower()
    if not t:
        return None
    if t in _TIPO_ALIAS:
        return _TIPO_ALIAS[t]
    for k in sorted(_TIPO_ALIAS, key=len, reverse=True):
        if k in t:
            return _TIPO_ALIAS[k]
    return None


def explicar_tipo(chave: str | None = None) -> str:
    """Um tipo (ani, agi, asi, reativa, memoria, mente) ou, sem chave, a classificação inteira."""
    if chave in _TIPOS:
        t = _TIPOS[chave]
        situacao = "Existe hoje." if t.existe else "Ainda não existe."
        partes = [f"{t.titulo}{f' ({t.sigla})' if t.sigla else ''}: {t.resumo} {situacao}", f"Exemplos: {t.exemplos}"]
        if t.risco:
            partes.append(f"Riscos: {t.risco}")
        partes.append(f"No NEXUS: {t.nexus}")
        return " ".join(partes)
    cap = "; ".join(f"{t.titulo} ({t.sigla}): {'existe hoje' if t.existe else 'ainda não existe'}"
                    for t in TIPOS_CAPACIDADE)
    fun = "; ".join(f"{t.titulo}: {'existe hoje' if t.existe else 'ainda não existe'}" for t in TIPOS_FUNCAO)
    return (f"Por nível de inteligência: {cap}. Por funcionamento: {fun}. "
            f"O NEXUS é uma IA estreita (ANI) de memória limitada, com partes reativas.")


def como_aprendo() -> str:
    """Resposta a 'como você aprende?', com números reais."""
    partes = ["Eu aprendo com dados: cada pedido que você faz, cada correção e cada hábito viram exemplos de treino."]
    try:
        from core.intent_net import brain
        st = brain.stats()
        if st.get("val_acc") is not None:
            partes.append(f"Minha rede de intenções tem {_n(st.get('samples'))} exemplos "
                          f"e acerta {_pct(st.get('val_acc'))} nos testes"
                          + (f", sendo {_n(st['user_examples'])} seus." if st.get("user_examples") else "."))
    except Exception:
        _engolida("core/ia_status.py:410")
    partes.append("Tudo isso fica no seu computador.")
    return " ".join(partes)


def resumo_geral() -> dict:
    """Números para o cabeçalho do painel."""
    areas = tudo()
    ok = sum(a.prontos[0] for a in areas)
    total = sum(a.prontos[1] for a in areas)
    return {"prontos": ok, "total": total, "motor": _motor()[0], "gerado_em": time.time()}
