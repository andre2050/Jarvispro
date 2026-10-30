# -*- coding: utf-8 -*-
"""
NEXUS FORGE 2.0 - fábrica de aplicativos por voz para o Nexus
=============================================================

Você diz "Nexus, vamos criar um aplicativo do zero" e o Forge:
  1. ENTREVISTA você por voz (o que faz, onde roda, telas, nome);
  2. ARQUITETO: monta o plano (stack, arquivos, comando de teste) e pede sua aprovação;
  3. CONSTRUTOR: escreve o código inteiro, instala dependências e roda o app/testes;
  4. VERIFICAÇÃO: o próprio Forge roda o comando de teste e manda o construtor corrigir (até 3 rodadas);
  5. REVISOR: outro agente lê o código atrás de bugs e falhas de segurança; problemas graves são corrigidos;
  6. CHECKPOINTS em git a cada etapa: dá para "desfazer a última alteração";
  7. Depois você segue pedindo por voz: "no app, adiciona uma tela de login".

Comandos de voz reconhecidos (todos passam por forge.tratar_comando(frase)):
  - "vamos criar um aplicativo do zero"      -> novo projeto
  - "listar projetos" / "abrir projeto X"    -> retomar um projeto antigo
  - "no app, <pedido>"                       -> editar o projeto atual
  - "revisar o código"                       -> revisão de bugs/segurança + correção
  - "desfazer a última alteração"            -> volta ao checkpoint anterior
  - "empacotar o projeto"                    -> gera um .zip em NexusProjetos/_entregas
  - "gerar executável"                       -> PyInstaller (apps Python)
  - "publicar no github"                     -> cria o repositório e envia (pede confirmação)
  - "abrir a pasta do projeto"
  - "quanto gastei"                          -> consumo de tokens da missão e do dia

INTEGRAÇÃO NO NEXUS:
    O motor é independente de voz e de tela. No Nexus ele é usado pela ação
    `actions/forge_app.py` (descoberta sozinha ao iniciar), que cuida da conversa,
    do segundo plano e da confirmação na tela. Também roda sozinho no console:
        python -m core.forge_engine

REQUISITOS:
    pip install anthropic
    Chave: anthropic_api_key em config/api_keys.json (a mesma do claude_voice),
    ou a variável ANTHROPIC_API_KEY, ou o arquivo ~/.nexus_forge/api_key.txt
    git instalado; GitHub CLI (gh) só se quiser publicar.

VARIÁVEIS OPCIONAIS:
    NEXUS_FORGE_DIR               pasta dos projetos (padrão ~/NexusProjetos)
    NEXUS_FORGE_MODEL             modelo do construtor   (padrão claude-sonnet-5-5)
    NEXUS_FORGE_MODEL_ARQUITETO   modelo do arquiteto    (padrão = construtor)
    NEXUS_FORGE_MODEL_REVISOR     modelo do revisor      (padrão = construtor)
    NEXUS_FORGE_LIMITE_MISSAO     tokens máx. por missão (padrão 1500000)
    NEXUS_FORGE_LIMITE_DIA        tokens máx. por dia    (padrão 6000000)
    NEXUS_FORGE_REPO_PUBLICO=1    publica repositórios como públicos (padrão: privado)

AVISO DE SEGURANÇA (importante):
    O Forge roda os comandos sem shell, com lista de comandos permitidos, dentro de
    um venv do projeto e sem passar suas chaves de API ao processo filho. Mas o app
    gerado é código escrito por IA e, quando executado, pode fazer qualquer coisa que
    o seu usuário do Windows/Linux possa fazer. Para apps que você não revisou,
    prefira rodar o Nexus dentro de uma máquina virtual ou de um usuário separado.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
import zipfile
from datetime import date
from pathlib import Path
from typing import Callable, Optional

try:
    import anthropic
except ImportError:  # tratado em _cliente()
    anthropic = None

# ----------------------------------------------------------------------------
# Configuração
# ----------------------------------------------------------------------------
MODELO_PADRAO = os.environ.get("NEXUS_FORGE_MODEL", "claude-sonnet-5-5")
MODELO_ARQUITETO = os.environ.get("NEXUS_FORGE_MODEL_ARQUITETO", MODELO_PADRAO)
MODELO_REVISOR = os.environ.get("NEXUS_FORGE_MODEL_REVISOR", MODELO_PADRAO)
RAIZ_PADRAO = Path(os.environ.get("NEXUS_FORGE_DIR", Path.home() / "NexusProjetos"))
CONFIG_DIR = Path.home() / ".nexus_forge"

LIMITE_MISSAO = int(os.environ.get("NEXUS_FORGE_LIMITE_MISSAO", 1_500_000))
LIMITE_DIA = int(os.environ.get("NEXUS_FORGE_LIMITE_DIA", 6_000_000))
REPO_PUBLICO = os.environ.get("NEXUS_FORGE_REPO_PUBLICO", "0") == "1"

MAX_PASSOS = 60            # chamadas de ferramenta por rodada do agente
MAX_SAIDA = 8000           # max_tokens por resposta
MAX_RODADAS_VERIF = 3      # rodadas de teste -> correção
TIMEOUT_CMD = 180          # segundos por comando
TIMEOUT_EXE = 900          # segundos para gerar executável
SAIDA_MAX = 6000           # caracteres devolvidos de um comando
LEITURA_MAX = 40000        # caracteres devolvidos de um arquivo lido
ARQUIVO_MAX = 300_000      # bytes por arquivo escrito
ARQUIVOS_MAX = 300         # arquivos por projeto

COMANDOS_PERMITIDOS = {"python", "python3", "py", "pip", "pip3", "pytest", "node", "npm", "npx"}
EXT_BLOQUEADAS = {".exe", ".dll", ".msi", ".scr", ".com"}
PASTAS_INTERNAS = {".git", ".forge", ".venv"}
PASTAS_IGNORADAS = PASTAS_INTERNAS | {"__pycache__", "node_modules", "dist", "build", ".pytest_cache"}

GATILHO_CRIAR = re.compile(
    r"\b(criar|cria|fazer|faz|construir|constroi|desenvolver)\b.{0,25}\b(aplicativo|app|programa|software)\b"
)

RECEITAS = """\
Receitas de stack (escolha a que melhor serve ao pedido):
- PC com janela: Python + Tkinter (sem dependências extras quando possível).
- Navegador: HTML/CSS/JS puro, ou Python + Flask para app com servidor.
- Android: PWA instalável (manifest + service worker). Alternativa: Kivy, explicando no README como gerar o APK.
- Linha de comando: Python + argparse.
- Jogo simples: Python + pygame.
Prefira o que roda direto no PC do usuário sem toolchains pesadas."""

SISTEMA_ARQUITETO = f"""Você é o ARQUITETO do Nexus Forge. Recebe o pedido de um usuário brasileiro e devolve um plano de projeto.
{RECEITAS}
Responda SOMENTE com um JSON válido, sem texto fora dele, neste formato:
{{"titulo": "nome curto do app",
  "resumo": "2 frases em português simples, para ser lido em voz alta",
  "stack": "tecnologias escolhidas",
  "arquivos": ["lista", "de", "arquivos", "planejados"],
  "entrada": "arquivo principal para executar (ex: main.py) ou \\"\\" se não se aplica",
  "comando_teste": "um comando curto que valida o app SEM abrir janela nem servidor (ex: python -m pytest -q, ou python -m py_compile main.py)",
  "como_executar": "comando para rodar o app",
  "riscos": ["limitações ou coisas que o usuário deve saber"]}}"""

SISTEMA_CONSTRUTOR = """Você é o CONSTRUTOR do Nexus Forge. Constrói aplicativos completos e funcionais numa pasta de projeto usando APENAS as ferramentas fornecidas.
Regras:
- Código completo e funcional. Nada de TODO, "..." ou funções vazias.
- Escreva arquivos de tamanho razoável (um por chamada); divida em módulos quando fizer sentido.
- Comente o código em português e crie um README.md com como instalar e executar.
- Se usar bibliotecas, crie requirements.txt, instale com pip e RODE os testes/validações. Corrija todo erro que aparecer.
- Crie testes simples (pytest) para a lógica principal quando o stack for Python.
- Nunca execute em primeiro plano algo que não termina (janela, servidor). Valide com testes, py_compile ou import.
- Não peça nada ao usuário durante o trabalho; decida com bom senso.
- Quando terminar, chame a ferramenta concluir."""

SISTEMA_EDITOR = """Você é o CONSTRUTOR do Nexus Forge, trabalhando num projeto que JÁ EXISTE.
Leia os arquivos relevantes antes de mudar qualquer coisa, faça apenas o que foi pedido, mantenha o estilo do código
e atualize README e testes se necessário. Rode os testes depois. Quando terminar, chame concluir."""

SISTEMA_REVISOR = """Você é o REVISOR sênior do Nexus Forge (código e segurança). Leia os arquivos do projeto e reporte
problemas REAIS: bugs, falhas de segurança (injeção, segredos no código, caminhos inseguros), funcionalidade pedida que falta,
código que não vai rodar. Não invente problemas e não reporte questões de estilo. Ao terminar, chame reportar_revisao."""


class Orcamento(Exception):
    """Limite de tokens atingido."""


class ChaveAusente(RuntimeError):
    """O NEXUS não tem chave da Anthropic."""


class SDKAusente(RuntimeError):
    """O pacote anthropic não está instalado."""


# Frases curtas e acionáveis: o NEXUS as fala em voz alta.
MSG_SDK = ("O Forge precisa do pacote anthropic, que não está instalado neste computador. "
           "Rode o Instalar o NEXUS de novo ou, no terminal, pip install anthropic.")
MSG_SEM_CHAVE = ("O Forge usa o Claude e precisa da chave da Anthropic, que o NEXUS ainda não tem. "
                 "Cole a chave nas Configurações, em Motor de voz, no campo Chave do provedor, com o modelo Claude "
                 "selecionado. A chave do Gemini não serve para o Forge. Enquanto isso, o dev_agent funciona só com o Gemini.")
MSG_CHAVE_RECUSADA = ("A Anthropic recusou a chave que o NEXUS tem: inválida, apagada ou de outra conta. "
                      "Gere uma nova em console.anthropic.com, em API Keys, e cole de novo nas Configurações.")
MSG_SEM_CREDITO = ("A conta da Anthropic está sem crédito. Adicione crédito em console.anthropic.com, "
                   "em Plans e Billing, e tente de novo.")
MSG_SEM_RESPOSTA = "Não consegui falar com a Anthropic. Veja a internet e tente de novo."


# ----------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------
def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c)).strip()


def _slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _norm(texto)).strip("-")[:40] or "app"


def _json_de(texto: str) -> dict:
    m = re.search(r"\{.*\}", texto, re.S)
    if not m:
        raise ValueError("a resposta do arquiteto não veio em JSON")
    return json.loads(m.group(0))


def _tool(nome, descricao, props, obrigatorios):
    return {"name": nome, "description": descricao,
            "input_schema": {"type": "object", "properties": props, "required": obrigatorios}}


T_ESCREVER = _tool("escrever_arquivo", "Cria ou sobrescreve um arquivo do projeto (caminho relativo).",
                   {"caminho": {"type": "string"}, "conteudo": {"type": "string"}}, ["caminho", "conteudo"])
T_LER = _tool("ler_arquivo", "Lê um arquivo do projeto.", {"caminho": {"type": "string"}}, ["caminho"])
T_LISTAR = _tool("listar_arquivos", "Lista os arquivos do projeto.", {}, [])
T_CMD = _tool("executar_comando",
              "Executa um comando na pasta do projeto (python, pip, pytest, node, npm, npx). "
              "Sem shell, sem pipes. python/pip usam o venv do projeto.",
              {"comando": {"type": "string"}}, ["comando"])
T_CONCLUIR = _tool("concluir", "Chame quando o trabalho estiver pronto.",
                   {"resumo": {"type": "string", "description": "2 frases, em português, para ler em voz alta"},
                    "como_executar": {"type": "string"}}, ["resumo"])
T_REPORTAR = _tool("reportar_revisao", "Entrega o resultado da revisão.",
                   {"nota": {"type": "integer", "description": "0 a 10"},
                    "problemas": {"type": "array", "items": {"type": "object", "properties": {
                        "gravidade": {"type": "string", "enum": ["alta", "media", "baixa"]},
                        "arquivo": {"type": "string"}, "descricao": {"type": "string"}},
                        "required": ["gravidade", "descricao"]}}},
                   ["nota", "problemas"])

TOOLS_CONSTRUTOR = [T_ESCREVER, T_LER, T_LISTAR, T_CMD, T_CONCLUIR]
TOOLS_REVISOR = [T_LER, T_LISTAR, T_REPORTAR]


# ----------------------------------------------------------------------------
# Forge
# ----------------------------------------------------------------------------
class NexusForge:
    def __init__(self,
                 falar: Callable[[str], None] = print,
                 ouvir: Callable[[], str] = lambda: input("VOCÊ: "),
                 pasta_projetos: Optional[Path] = None,
                 progresso_voz: bool = True,
                 segundo_plano: bool = True):
        self.falar = falar
        self.ouvir = ouvir
        self.raiz = Path(pasta_projetos or RAIZ_PADRAO)
        self.raiz.mkdir(parents=True, exist_ok=True)
        self.progresso_voz = progresso_voz
        self.segundo_plano = segundo_plano
        self.pasta: Optional[Path] = None
        self.plano: dict = {}
        self.tokens_missao = 0
        self._lock = threading.Lock()
        self._ultimo_aviso = 0.0
        self._cliente_cache = None
        self._pendente = None   # (plano, brief) aguardando aprovação
        self._carregar_ultimo()

    # ------------------------------------------------------------ voz / entrada
    def _fala(self, texto: str):
        try:
            self.falar(texto)
        except Exception:
            print(texto)

    def _perguntar(self, pergunta: str, tentativas: int = 2) -> str:
        for _ in range(tentativas):
            self._fala(pergunta)
            resp = (self.ouvir() or "").strip()
            if resp:
                return resp
        return ""

    @staticmethod
    def _sim(resposta: str) -> bool:
        r = _norm(resposta)
        nao = re.search(r"\b(nao|cancela|cancelar|para|pare|deixa pra la|desiste)\b", r)
        sim = re.search(r"\b(sim|pode|bora|vai|manda|claro|isso|ok|comeca|positivo|confirmo|confirma)\b", r)
        return bool(sim) and not nao

    # ------------------------------------------------------------ roteador de voz
    def tratar_comando(self, frase: str) -> bool:
        """Devolve True se o Forge tratou o comando (o Nexus não deve processá-lo de novo)."""
        n = _norm(frase)
        if not n:
            return False

        if GATILHO_CRIAR.search(n):
            self.novo_projeto()
            return True
        if re.search(r"\b(listar|lista|quais)\b.*\bprojetos\b", n):
            self.listar_projetos()
            return True
        m = re.search(r"\b(abrir|abre|continuar|continua|retomar|retoma)\b.*\bprojeto\b\s*(.*)", n)
        if m:
            self.abrir_projeto(m.group(2))
            return True
        if re.search(r"\bquanto\b.*\b(gastei|gastou|custou|consumi)\b|\bconsumo de tokens\b", n):
            self.falar_uso()
            return True

        if self.pasta is None:   # comandos abaixo só fazem sentido com projeto aberto
            return False

        m = re.match(r"^(no|na)\s+(app|aplicativo|projeto)\b[\s,:]*(.+)$", n)
        if m:
            pedido = frase.strip()
            if len(pedido) == len(n):         # preserva acentos quando possível
                pedido = pedido[m.start(3):]
            else:
                pedido = m.group(3)
            self.editar(pedido)
            return True
        if re.search(r"\brevis(ar|a)\b.*\b(codigo|projeto|app|aplicativo)\b", n):
            self._bg(self._revisar_e_corrigir_cmd)
            return True
        if re.search(r"\bdesfaz(er|a)\b.*\b(alteracao|ultima|mudanca)\b", n):
            self.desfazer()
            return True
        if re.search(r"\b(empacot\w*|zipar|gerar zip)\b", n):
            self.empacotar()
            return True
        if re.search(r"\bgera(r)?\b.*\bexecutavel\b", n):
            self._bg(self.gerar_executavel)
            return True
        if re.search(r"\bpublic(ar|a)\b.*\bgithub\b", n):
            self.publicar()
            return True
        if re.search(r"\babr(ir|a)\b.*\bpasta\b", n):
            self.abrir_pasta()
            return True
        return False

    # ------------------------------------------------------------ novo projeto
    def novo_projeto(self):
        perguntas = [
            ("o_que", "Vamos lá. Me conta: o que o aplicativo precisa fazer?"),
            ("onde", "Vai rodar onde: no PC, no navegador ou no Android?"),
            ("telas", "Quais telas ou funções principais? Se não souber, diga: você decide."),
            ("nome", "Que nome quer dar? Pode dizer: você escolhe."),
        ]
        respostas = {}
        self.tokens_missao = 0   # a missão começa aqui: o arquiteto também conta no gasto
        for chave, pergunta in perguntas:
            r = self._perguntar(pergunta)
            if not r:
                self._fala("Não ouvi nada, então cancelei a criação do aplicativo.")
                return
            respostas[chave] = r
        brief = "\n".join(f"- {k}: {v}" for k, v in respostas.items())

        self._fala("Entendi. Estou montando o plano.")
        try:
            plano = self._arquiteto(brief)
        except Exception as e:
            self._fala(f"Não consegui montar o plano. {self._msg_erro(e)}")
            return

        riscos = plano.get("riscos") or []
        aviso = f" Atenção: {riscos[0]}" if riscos else ""
        self._fala(f"Plano pronto. {plano.get('titulo')}: {plano.get('resumo')} "
                   f"Vou usar {plano.get('stack')}, com cerca de {len(plano.get('arquivos', []))} arquivos.{aviso}")
        if not self._sim(self._perguntar("Posso começar a construir?")):
            self._fala("Combinado, não vou construir agora. Quando quiser, é só pedir de novo.")
            return

        self.pasta = self._pasta_nova(plano.get("titulo", "app"))
        self.plano = plano
        self._iniciar_projeto(plano, brief)
        self._fala(f"Começando. A pasta é {self.pasta.name}. Aviso quando terminar.")
        self._bg(self._construir, plano, brief, resetar=False)

    # ------------------------------------------------------------ API sem microfone (ação forge_app)
    def planejar(self, brief: str) -> dict:
        """Só o arquiteto: devolve o plano e o guarda como pendente. Nada é construído ainda."""
        self.tokens_missao = 0
        plano = self._arquiteto(brief)
        self._pendente = (plano, brief)
        return plano

    def construir_pendente(self) -> bool:
        """Constrói o plano guardado por planejar(). False se não há plano esperando."""
        if not self._pendente:
            return False
        plano, brief = self._pendente
        self._pendente = None
        self.pasta = self._pasta_nova(plano.get("titulo", "app"))
        self.plano = plano
        self._iniciar_projeto(plano, brief)
        self._bg(self._construir, plano, brief, resetar=False)
        return True

    def _arquiteto(self, brief: str) -> dict:
        prefs = self._ler_prefs()
        extra = f"\nPreferências já observadas do usuário: {json.dumps(prefs, ensure_ascii=False)}" if prefs else ""
        resp = self._cliente().messages.create(
            model=MODELO_ARQUITETO, max_tokens=2000, system=SISTEMA_ARQUITETO,
            messages=[{"role": "user", "content": f"Pedido do usuário:\n{brief}{extra}"}])
        self._gastar(resp)
        texto = "".join(b.text for b in resp.content if b.type == "text")
        plano = _json_de(texto)
        plano.setdefault("titulo", "app")
        plano.setdefault("arquivos", [])
        plano.setdefault("comando_teste", "")
        plano.setdefault("entrada", "")
        return plano

    def _construir(self, plano: dict, brief: str):
        self._marcar("início do projeto")
        inicio = (f"Construa este aplicativo do zero.\n\nPedido do usuário:\n{brief}\n\n"
                  f"Plano aprovado:\n{json.dumps(plano, ensure_ascii=False, indent=2)}")
        r = self._agente(SISTEMA_CONSTRUTOR, inicio, MODELO_PADRAO, TOOLS_CONSTRUTOR, "concluir")
        self._checkpoint("construção inicial")
        ok = self._verificar(plano)
        self._fala("Código escrito. Chamando o revisor.")
        nota = self._revisar_e_corrigir()
        if nota is not None:
            ok = self._verificar(plano) and ok
        self._checkpoint("versão final")
        self._salvar_pref(plano)
        self._historico("criação", brief)

        resumo = r.get("resumo", "Aplicativo criado.")
        teste = "Os testes passaram." if ok else "Atenção: os testes ainda não passaram; veja o README e peça um ajuste."
        revisao = f" O revisor deu nota {nota}." if nota is not None else ""
        self._fala(f"Pronto! {resumo} {teste}{revisao} Usei cerca de {self.tokens_missao // 1000} mil tokens.")

    # ------------------------------------------------------------ editar
    def editar(self, pedido: str):
        if self.pasta is None:
            self._fala("Não tem nenhum projeto aberto.")
            return
        self._fala("Certo, vou fazer essa alteração.")
        self._bg(self._editar, pedido)

    def _editar(self, pedido: str):
        self._marcar(f"antes de: {pedido[:50]}")
        hist = self._ler_historico(5)
        inicio = (f"Pedido de alteração: {pedido}\n\nPlano original:\n"
                  f"{json.dumps(self.plano, ensure_ascii=False)}\n\nPedidos anteriores:\n{hist}\n\n"
                  f"Arquivos atuais:\n{self._listar()}")
        r = self._agente(SISTEMA_EDITOR, inicio, MODELO_PADRAO, TOOLS_CONSTRUTOR, "concluir")
        self._checkpoint(f"edição: {pedido[:60]}")
        ok = self._verificar(self.plano)
        self._checkpoint("edição verificada")
        self._historico("edição", pedido)
        extra = "" if ok else " Mas atenção: os testes falharam."
        self._fala(f"Pronto. {r.get('resumo', 'Alteração feita.')}{extra}")

    # ------------------------------------------------------------ verificação e revisão
    def _verificar(self, plano: dict) -> bool:
        cmd = (plano or {}).get("comando_teste", "").strip()
        if not cmd:
            return True
        for rodada in range(MAX_RODADAS_VERIF):
            codigo, saida = self._comando(cmd)
            self._rastro("verificacao", rodada=rodada, codigo=codigo)
            if codigo == 0:
                return True
            if rodada == MAX_RODADAS_VERIF - 1:
                break
            self._fala("Os testes falharam. Mandando o construtor corrigir.")
            self._agente(SISTEMA_EDITOR,
                         f"O comando de teste `{cmd}` falhou (código {codigo}). Saída:\n{saida}\n\n"
                         f"Arquivos:\n{self._listar()}\n\nCorrija o código (não apague os testes só para passar).",
                         MODELO_PADRAO, TOOLS_CONSTRUTOR, "concluir")
            self._checkpoint(f"correção {rodada + 1}")
        return False

    def _revisar_e_corrigir(self) -> Optional[int]:
        try:
            rev = self._agente(SISTEMA_REVISOR,
                               f"Pedido e plano do projeto:\n{json.dumps(self.plano, ensure_ascii=False)}\n\n"
                               f"Arquivos:\n{self._listar()}",
                               MODELO_REVISOR, TOOLS_REVISOR, "reportar_revisao", max_passos=30)
        except Orcamento:
            raise
        except Exception as e:
            self._rastro("revisor_falhou", erro=repr(e))
            return None
        problemas = rev.get("problemas") or []
        self._rastro("revisao", nota=rev.get("nota"), problemas=problemas)
        graves = [p for p in problemas if p.get("gravidade") == "alta"]
        if graves:
            self._fala(f"O revisor achou {len(graves)} problema grave. Corrigindo.")
            lista = "\n".join(f"- [{p.get('arquivo', '?')}] {p.get('descricao')}" for p in graves)
            self._agente(SISTEMA_EDITOR, f"O revisor apontou problemas graves. Corrija:\n{lista}\n\n"
                                         f"Arquivos:\n{self._listar()}",
                         MODELO_PADRAO, TOOLS_CONSTRUTOR, "concluir")
            self._checkpoint("correções do revisor")
        self._gravar_revisao(rev)
        return rev.get("nota")

    def _revisar_e_corrigir_cmd(self):
        self._fala("Iniciando a revisão do código.")
        self._marcar("antes da revisão")
        nota = self._revisar_e_corrigir()
        ok = self._verificar(self.plano)
        self._checkpoint("revisão")
        self._fala(f"Revisão concluída. Nota {nota}. " + ("Testes passando." if ok else "Os testes ainda falham."))

    def _gravar_revisao(self, rev: dict):
        try:
            linhas = [f"# Revisão do Forge (nota {rev.get('nota')})\n"]
            for p in rev.get("problemas") or []:
                linhas.append(f"- **{p.get('gravidade')}** `{p.get('arquivo', '')}`: {p.get('descricao')}")
            (self.pasta / ".forge" / "revisao.md").write_text("\n".join(linhas), encoding="utf-8")
        except Exception:
            pass

    # ------------------------------------------------------------ agente (loop de ferramentas)
    def _agente(self, sistema, inicio, modelo, tools, final, max_passos=MAX_PASSOS) -> dict:
        cli = self._cliente()
        permitidas = {t["name"] for t in tools}
        msgs = [{"role": "user", "content": inicio}]
        sem_ferramenta = 0
        for passo in range(max_passos):
            self._checar_orcamento()
            resp = cli.messages.create(model=modelo, max_tokens=MAX_SAIDA, system=sistema,
                                       tools=tools, messages=msgs)
            self._gastar(resp)
            if resp.stop_reason == "max_tokens":
                msgs.append({"role": "assistant", "content": "(resposta cortada por tamanho)"})
                msgs.append({"role": "user", "content": "Sua resposta foi cortada. Escreva arquivos menores, um por chamada."})
                continue

            blocos = []
            for b in resp.content:
                if b.type == "text":
                    blocos.append({"type": "text", "text": b.text})
                elif b.type == "tool_use":
                    blocos.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
            msgs.append({"role": "assistant", "content": blocos or "..."})
            usos = [b for b in blocos if b["type"] == "tool_use"]

            if not usos:
                sem_ferramenta += 1
                if sem_ferramenta >= 2:
                    return {"resumo": "O agente parou sem concluir formalmente.", "problemas": []}
                msgs.append({"role": "user", "content": f"Use as ferramentas. Quando terminar, chame {final}."})
                continue
            sem_ferramenta = 0

            resultados = []
            for u in usos:
                if u["name"] == final:
                    self._rastro("fim_agente", ferramenta=final, passos=passo + 1)
                    return dict(u["input"])
                if u["name"] not in permitidas:
                    saida = f"ERRO: ferramenta {u['name']} não permitida neste papel."
                else:
                    saida = self._executar_ferramenta(u["name"], u["input"])
                resultados.append({"type": "tool_result", "tool_use_id": u["id"], "content": saida})
                self._progresso()
            msgs.append({"role": "user", "content": resultados})
            self._podar(msgs)

        return {"resumo": "Atingi o limite de passos desta rodada.", "problemas": []}

    @staticmethod
    def _podar(msgs, manter: int = 8):
        """Troca resultados e conteúdos de arquivo antigos por marcadores, para economizar tokens."""
        for m in msgs[:max(len(msgs) - manter, 0)]:
            if not isinstance(m["content"], list):
                continue
            for b in m["content"]:
                if b.get("type") == "tool_result" and len(str(b.get("content", ""))) > 400:
                    b["content"] = "[resultado antigo omitido; leia o arquivo de novo se precisar]"
                elif b.get("type") == "tool_use" and b.get("name") == "escrever_arquivo":
                    conteudo = b["input"].get("conteudo", "")
                    if len(conteudo) > 400:
                        b["input"] = {"caminho": b["input"].get("caminho"),
                                      "conteudo": "[conteúdo omitido; o arquivo foi salvo no disco]"}

    def _progresso(self):
        if not self.progresso_voz or time.time() - self._ultimo_aviso < 60:
            return
        self._ultimo_aviso = time.time()
        n = sum(1 for _ in self._arquivos())
        self._fala(f"Ainda trabalhando. O projeto já tem {n} arquivos.")

    # ------------------------------------------------------------ ferramentas (com guardrails)
    def _caminho_seguro(self, rel: str) -> Path:
        base = self.pasta.resolve()
        destino = (base / rel).resolve()
        if destino != base and base not in destino.parents:
            raise ValueError("caminho fora da pasta do projeto")
        partes = destino.relative_to(base).parts
        if partes and partes[0] in PASTAS_INTERNAS:
            raise ValueError("pasta reservada do Forge")
        return destino

    def _arquivos(self):
        for raiz, dirs, files in os.walk(self.pasta):
            dirs[:] = [d for d in dirs if d not in PASTAS_IGNORADAS]
            for f in files:
                yield Path(raiz) / f

    def _listar(self) -> str:
        linhas = []
        for p in sorted(self._arquivos()):
            linhas.append(f"{p.relative_to(self.pasta).as_posix()} ({p.stat().st_size} bytes)")
            if len(linhas) >= 400:
                linhas.append("...")
                break
        return "\n".join(linhas) or "(projeto vazio)"

    def _executar_ferramenta(self, nome: str, args: dict) -> str:
        self._rastro("ferramenta", nome=nome, args={k: str(v)[:120] for k, v in args.items()})
        try:
            if nome == "escrever_arquivo":
                destino = self._caminho_seguro(args["caminho"])
                if destino.suffix.lower() in EXT_BLOQUEADAS:
                    return "ERRO: extensão de executável bloqueada."
                conteudo = args["conteudo"]
                if len(conteudo.encode("utf-8")) > ARQUIVO_MAX:
                    return "ERRO: arquivo grande demais; divida em arquivos menores."
                if not destino.exists() and sum(1 for _ in self._arquivos()) >= ARQUIVOS_MAX:
                    return "ERRO: limite de arquivos do projeto atingido."
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_text(conteudo, encoding="utf-8")
                return f"ok: {args['caminho']} ({len(conteudo)} caracteres)"
            if nome == "ler_arquivo":
                destino = self._caminho_seguro(args["caminho"])
                if not destino.is_file():
                    return "ERRO: arquivo não existe."
                texto = destino.read_text(encoding="utf-8", errors="replace")
                if len(texto) > LEITURA_MAX:
                    texto = texto[:LEITURA_MAX] + "\n[...cortado...]"
                return texto
            if nome == "listar_arquivos":
                return self._listar()
            if nome == "executar_comando":
                codigo, saida = self._comando(args["comando"])
                return f"[código {codigo}]\n{saida}"
            return f"ERRO: ferramenta desconhecida {nome}"
        except Exception as e:
            return f"ERRO: {e}"

    def _venv_python(self) -> str:
        v = self.pasta / ".venv"
        win = os.name == "nt"
        py = v / ("Scripts" if win else "bin") / ("python.exe" if win else "python")
        if not py.exists():
            subprocess.run([sys.executable, "-m", "venv", str(v)], check=True,
                           capture_output=True, timeout=300)
        return str(py)

    def _env_limpo(self) -> dict:
        proibidas = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD")
        env = {k: v for k, v in os.environ.items() if not any(p in k.upper() for p in proibidas)}
        env["PYTHONIOENCODING"] = "utf-8"
        return env

    def _comando(self, comando: str):
        """Roda um comando permitido dentro do projeto. Devolve (código, saída)."""
        try:
            args = shlex.split(comando, posix=(os.name != "nt"))
            args = [a.strip('"') for a in args]
        except ValueError as e:
            return 2, f"comando inválido: {e}"
        if not args:
            return 2, "comando vazio"
        nome = Path(args[0]).name.lower()
        if nome.endswith(".exe"):
            nome = nome[:-4]
        if nome not in COMANDOS_PERMITIDOS:
            return 126, f"comando '{nome}' não permitido. Permitidos: {', '.join(sorted(COMANDOS_PERMITIDOS))}"
        resto = args[1:]
        if nome in ("python", "python3", "py") and "-c" in resto:
            return 126, "python -c não é permitido; escreva um arquivo .py."
        if "uninstall" in resto:
            return 126, "desinstalar pacotes não é permitido."
        for a in resto:
            if "://" in a or a.startswith("git+"):
                return 126, "URLs e instalações por git não são permitidas."
            if re.match(r"^[a-zA-Z]:[\\/]", a) or a.startswith(("/", "\\", "~")) or ".." in Path(a).parts:
                return 126, f"argumento '{a}' aponta para fora do projeto."

        try:
            if nome in ("python", "python3", "py"):
                cmd = [self._venv_python()] + resto
            elif nome in ("pip", "pip3"):
                cmd = [self._venv_python(), "-m", "pip"] + resto
            elif nome == "pytest":
                cmd = [self._venv_python(), "-m", "pytest"] + resto
            else:
                exe = shutil.which(nome)
                if not exe:
                    return 127, f"'{nome}' não está instalado neste computador."
                cmd = [exe] + resto
            r = subprocess.run(cmd, cwd=self.pasta, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=TIMEOUT_CMD, env=self._env_limpo(),
                               stdin=subprocess.DEVNULL)
            saida = (r.stdout or "") + (r.stderr or "")
            if len(saida) > SAIDA_MAX:
                saida = saida[:SAIDA_MAX // 2] + "\n[...cortado...]\n" + saida[-SAIDA_MAX // 2:]
            return r.returncode, saida.strip() or "(sem saída)"
        except subprocess.TimeoutExpired:
            return 124, f"tempo esgotado ({TIMEOUT_CMD}s); o processo foi encerrado."
        except Exception as e:
            return 1, f"erro ao executar: {e}"

    # ------------------------------------------------------------ git: checkpoints e desfazer
    def _git(self, *a):
        return subprocess.run(["git", "-c", "user.name=Nexus Forge", "-c", "user.email=forge@nexus.local", *a],
                              cwd=self.pasta, capture_output=True, text=True, encoding="utf-8", errors="replace")

    def _checkpoint(self, msg: str, vazio: bool = False):
        if shutil.which("git") is None:
            return
        if not (self.pasta / ".git").exists():
            self._git("init", "-q")
        self._git("add", "-A")
        extra = ["--allow-empty"] if vazio else []
        self._git("commit", "-q", "-m", f"forge: {msg}", *extra)

    def _head(self) -> str:
        return self._git("rev-parse", "HEAD").stdout.strip()

    def _marcar(self, msg: str):
        """Guarda um ponto de retorno (commit) antes de um trabalho começar."""
        self._checkpoint(msg, vazio=True)
        h = self._head()
        if not h:
            return
        arq = self.pasta / ".forge" / "marcos.json"
        marcos = json.loads(arq.read_text()) if arq.exists() else []
        marcos.append({"hash": h, "msg": msg})
        arq.write_text(json.dumps(marcos[-50:], ensure_ascii=False), encoding="utf-8")

    def desfazer(self):
        arq = self.pasta / ".forge" / "marcos.json"
        marcos = json.loads(arq.read_text()) if arq.exists() else []
        if len(marcos) < 2:
            self._fala("Não há alteração anterior para desfazer.")
            return
        ultimo = marcos.pop()
        self._checkpoint("estado antes de desfazer")
        self._git("reset", "--hard", ultimo["hash"])
        arq.write_text(json.dumps(marcos, ensure_ascii=False), encoding="utf-8")
        self._rastro("desfazer", para=ultimo["msg"])
        self._fala(f"Desfeito. Voltei para o estado anterior a: {ultimo['msg']}.")

    # ------------------------------------------------------------ entrega
    def empacotar(self):
        destino_dir = self.raiz / "_entregas"
        destino_dir.mkdir(exist_ok=True)
        zip_path = destino_dir / f"{self.pasta.name}-{time.strftime('%Y%m%d-%H%M%S')}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for p in self._arquivos():
                z.write(p, p.relative_to(self.pasta).as_posix())
        self._fala(f"Empacotei o projeto em um arquivo zip dentro da pasta de entregas: {zip_path.name}.")
        return zip_path

    def gerar_executavel(self):
        entrada = (self.plano or {}).get("entrada", "")
        if not entrada.endswith(".py") or not (self.pasta / entrada).exists():
            self._fala("Este projeto não tem um arquivo Python principal para virar executável.")
            return
        self._fala("Gerando o executável. Pode demorar alguns minutos.")
        py = self._venv_python()
        env = self._env_limpo()
        r = subprocess.run([py, "-m", "pip", "install", "-q", "pyinstaller"], cwd=self.pasta, env=env,
                           capture_output=True, text=True, timeout=TIMEOUT_EXE, stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            self._fala("Não consegui instalar o PyInstaller.")
            return
        r = subprocess.run([py, "-m", "PyInstaller", "--onefile", "--noconfirm", entrada], cwd=self.pasta,
                           env=env, capture_output=True, text=True, timeout=TIMEOUT_EXE, stdin=subprocess.DEVNULL)
        if r.returncode == 0:
            self._fala("Executável gerado na pasta dist do projeto.")
        else:
            self._rastro("pyinstaller_erro", saida=(r.stderr or "")[-1500:])
            self._fala("Não consegui gerar o executável. O erro ficou salvo no registro do projeto.")

    def publicar(self):
        """Modo console/voz: pergunta no microfone e publica. No Nexus a confirmação vem da tela (core/confirm)."""
        vis = "público" if REPO_PUBLICO else "privado"
        if not self._sim(self._perguntar(f"Vou publicar o projeto {self.pasta.name} no seu GitHub como repositório {vis}. Confirma?")):
            self._fala("Tudo bem, não publiquei nada.")
            return
        self._fala(self.publicar_agora())

    def publicar_agora(self) -> str:
        """Publica SEM perguntar: quem chama é responsável por ter a confirmação da pessoa."""
        gh = shutil.which("gh")
        if not gh:
            return "Para publicar eu preciso do GitHub CLI instalado e logado. Instale o gh e rode gh auth login."
        self._checkpoint("antes de publicar")
        if self._git("remote").stdout.strip():
            r = self._git("push", "-u", "origin", "HEAD")
        else:
            r = subprocess.run([gh, "repo", "create", self.pasta.name, "--public" if REPO_PUBLICO else "--private",
                                "--source", ".", "--remote", "origin", "--push"],
                               cwd=self.pasta, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode == 0:
            return "Publicado no GitHub com sucesso."
        self._rastro("publicar_erro", saida=(r.stderr or "")[-800:])
        return "Não consegui publicar. Veja se o gh está logado."

    def abrir_pasta(self):
        try:
            if os.name == "nt":
                os.startfile(self.pasta)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(self.pasta)])
            else:
                subprocess.Popen(["xdg-open", str(self.pasta)])
            self._fala("Abri a pasta do projeto.")
        except Exception:
            self._fala(f"A pasta do projeto é {self.pasta}.")

    # ------------------------------------------------------------ projetos
    def _pasta_nova(self, titulo: str) -> Path:
        base = self.raiz / _slug(titulo)
        p, i = base, 2
        while p.exists():
            p = Path(f"{base}-{i}")
            i += 1
        p.mkdir(parents=True)
        return p

    def _iniciar_projeto(self, plano: dict, brief: str):
        (self.pasta / ".forge").mkdir(exist_ok=True)
        (self.pasta / ".gitignore").write_text(".venv/\n.forge/\n__pycache__/\n*.pyc\nnode_modules/\ndist/\nbuild/\n",
                                               encoding="utf-8")
        (self.pasta / ".forge" / "plano.json").write_text(json.dumps(plano, ensure_ascii=False, indent=2),
                                                          encoding="utf-8")
        (self.raiz / ".ultimo").write_text(str(self.pasta), encoding="utf-8")

    def _carregar_ultimo(self):
        try:
            p = Path((self.raiz / ".ultimo").read_text(encoding="utf-8").strip())
            if (p / ".forge" / "plano.json").exists():
                self.pasta = p
                self.plano = json.loads((p / ".forge" / "plano.json").read_text(encoding="utf-8"))
        except Exception:
            pass

    def _projetos(self):
        return sorted(d for d in self.raiz.iterdir() if (d / ".forge" / "plano.json").exists())

    def listar_projetos(self):
        nomes = [d.name for d in self._projetos()]
        if not nomes:
            self._fala("Você ainda não tem projetos criados pelo Forge.")
        else:
            self._fala(f"Você tem {len(nomes)} projetos: " + ", ".join(nomes[:8]) + ".")

    def achar_projeto(self, nome: str) -> Optional[Path]:
        """Acha um projeto do Forge pelo nome (aproximado). Vazio/'último' = o projeto atual ou o mais novo."""
        nome = _slug(nome) if (nome or "").strip() else ""
        projs = self._projetos()
        achado = None
        if nome in ("", "ultimo", "anterior"):
            achado = self.pasta or (projs[-1] if projs else None)
        else:
            tokens = [t for t in nome.split("-") if len(t) > 2]
            for d in projs:
                if nome in d.name or (tokens and all(t in d.name for t in tokens)):
                    achado = d
        return achado

    @property
    def plano_pendente(self) -> Optional[dict]:
        """O plano que o arquiteto fez e que ainda espera aprovação (ou None)."""
        return self._pendente[0] if self._pendente else None

    def abrir_projeto(self, nome: str):
        achado = self.achar_projeto(nome)
        if not achado:
            self._fala("Não encontrei esse projeto. Diga 'listar projetos' para ver os nomes.")
            return
        self.pasta = achado
        self.plano = json.loads((achado / ".forge" / "plano.json").read_text(encoding="utf-8"))
        (self.raiz / ".ultimo").write_text(str(achado), encoding="utf-8")
        self._fala(f"Projeto {achado.name} aberto. Pode pedir alterações dizendo: no app, e o que você quer.")

    # ------------------------------------------------------------ memória, rastro, uso
    def _rastro(self, evento: str, **dados):
        try:
            if self.pasta is None or not (self.pasta / ".forge").exists():
                return
            linha = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "evento": evento, **dados}
            with open(self.pasta / ".forge" / "trace.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(linha, ensure_ascii=False, default=str)[:3000] + "\n")
        except Exception:
            pass

    def _historico(self, tipo: str, texto: str):
        try:
            with open(self.pasta / ".forge" / "historico.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": time.strftime("%Y-%m-%d %H:%M"), "tipo": tipo, "texto": texto[:500]},
                                   ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _ler_historico(self, n: int) -> str:
        try:
            linhas = (self.pasta / ".forge" / "historico.jsonl").read_text(encoding="utf-8").splitlines()[-n:]
            return "\n".join(f"- {json.loads(l)['tipo']}: {json.loads(l)['texto']}" for l in linhas) or "(nenhum)"
        except Exception:
            return "(nenhum)"

    def _ler_prefs(self) -> dict:
        try:
            return json.loads((CONFIG_DIR / "prefs.json").read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _salvar_pref(self, plano: dict):
        try:
            CONFIG_DIR.mkdir(exist_ok=True)
            prefs = self._ler_prefs()
            stacks = prefs.setdefault("stacks", {})
            s = str(plano.get("stack", ""))[:60]
            stacks[s] = stacks.get(s, 0) + 1
            prefs["projetos_criados"] = prefs.get("projetos_criados", 0) + 1
            (CONFIG_DIR / "prefs.json").write_text(json.dumps(prefs, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def _uso_arquivo(self) -> Path:
        return self.raiz / ".uso.json"

    def _uso_dia(self) -> int:
        try:
            return json.loads(self._uso_arquivo().read_text()).get(date.today().isoformat(), 0)
        except Exception:
            return 0

    def _gastar(self, resp):
        try:
            usados = int(resp.usage.input_tokens) + int(resp.usage.output_tokens)
        except Exception:
            return
        self.tokens_missao += usados
        try:
            dados = json.loads(self._uso_arquivo().read_text()) if self._uso_arquivo().exists() else {}
            hoje = date.today().isoformat()
            dados = {hoje: dados.get(hoje, 0) + usados}
            self._uso_arquivo().write_text(json.dumps(dados), encoding="utf-8")
        except Exception:
            pass

    def _checar_orcamento(self):
        if self.tokens_missao > LIMITE_MISSAO:
            raise Orcamento("Parei porque esta missão passou do limite de gasto que você definiu. "
                            "O que já foi feito está salvo; peça para continuar se quiser.")
        if self._uso_dia() > LIMITE_DIA:
            raise Orcamento("Parei porque o limite de gasto de hoje foi atingido.")

    def falar_uso(self):
        self._fala(f"Nesta missão usei cerca de {self.tokens_missao // 1000} mil tokens, "
                   f"e hoje no total {self._uso_dia() // 1000} mil.")

    # ------------------------------------------------------------ infraestrutura
    def _chave_e_origem(self):
        """Acha a chave da Anthropic e diz de onde veio (sem nunca mostrá-la). O que a pessoa colou nas Configurações
        do NEXUS (llm_keys.claude, o que a tela grava) vale mais que anthropic_api_key do json, que vale mais que
        a variável de ambiente."""
        try:
            from memory.config_manager import load_api_keys
            dados = load_api_keys()
            chave = str((dados.get("llm_keys") or {}).get("claude") or "").strip()
            if chave:
                return chave, "Configurações do NEXUS (provedor Claude)"
            chave = str(dados.get("anthropic_api_key") or "").strip()
            if chave:
                return chave, "anthropic_api_key em config/api_keys.json"
        except Exception:
            pass
        chave = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
        if chave:
            return chave, "variável de ambiente ANTHROPIC_API_KEY"
        arq = CONFIG_DIR / "api_key.txt"
        if arq.exists():
            chave = arq.read_text(encoding="utf-8").strip()
            if chave:
                return chave, "arquivo ~/.nexus_forge/api_key.txt"
        return "", ""

    def _chave(self) -> str:
        return self._chave_e_origem()[0]

    def _cliente(self):
        if self._cliente_cache:
            return self._cliente_cache
        if anthropic is None:
            raise SDKAusente(MSG_SDK)
        chave = self._chave()
        if not chave:
            raise ChaveAusente(MSG_SEM_CHAVE)
        self._cliente_cache = anthropic.Anthropic(api_key=chave)
        return self._cliente_cache

    def testar_chave(self):
        """Confere, sem gastar tokens, se o Forge consegue usar a Anthropic: pacote, chave e resposta da API.
        Devolve (ok, frase). A chave nunca aparece na frase."""
        if anthropic is None:
            return False, MSG_SDK
        chave, origem = self._chave_e_origem()
        if not chave:
            return False, MSG_SEM_CHAVE
        import urllib.error
        import urllib.request
        req = urllib.request.Request("https://api.anthropic.com/v1/models?limit=1",
                                     headers={"x-api-key": chave, "anthropic-version": "2023-06-01"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                if r.status == 200:
                    return True, (f"A chave da Anthropic ({origem}) é válida e o Forge está pronto. "
                                  "O saldo da conta só aparece quando o Forge gasta.")
                return False, f"A Anthropic respondeu algo inesperado ({r.status})."
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                return False, MSG_CHAVE_RECUSADA
            return False, f"A Anthropic respondeu com o erro {e.code}."
        except Exception:
            return False, MSG_SEM_RESPOSTA

    @staticmethod
    def _msg_erro(e: Exception) -> str:
        """Transforma o erro numa frase que diz o que fazer (nunca o JSON cru da API)."""
        if isinstance(e, (ChaveAusente, SDKAusente, Orcamento)):
            return str(e)
        nome = type(e).__name__
        t = str(e)
        low = t.lower()
        if "credit balance" in low:
            return MSG_SEM_CREDITO
        if nome == "OverloadedError" or "overloaded" in low:
            return "A Anthropic está sobrecarregada agora. Tente de novo daqui a pouco."
        if nome in ("AuthenticationError", "PermissionDeniedError") or "invalid x-api-key" in low \
                or "authentication_error" in low:
            return MSG_CHAVE_RECUSADA
        if nome == "RateLimitError" or "rate_limit" in low:
            return "O limite de uso da Anthropic foi atingido agora. Espere um pouco e tente de novo."
        if nome in ("APIConnectionError", "APITimeoutError"):
            return MSG_SEM_RESPOSTA
        if nome == "NotFoundError" and "model" in low:
            return "O modelo do Claude pedido não existe nesta conta. Confira a variável NEXUS_FORGE_MODEL."
        return re.sub(r"\s+", " ", t).strip()[:160]

    def _bg(self, fn, *args, resetar: bool = True):
        if not self._lock.acquire(blocking=False):
            self._fala("Ainda estou trabalhando em outra tarefa. Espere terminar.")
            return

        def alvo():
            try:
                if resetar:
                    self.tokens_missao = 0
                fn(*args)
            except Orcamento as e:
                self._fala(str(e))
            except Exception as e:
                self._rastro("erro", erro=repr(e))
                self._fala(f"Tive um problema: {self._msg_erro(e)}")
            finally:
                self._lock.release()

        if self.segundo_plano:
            threading.Thread(target=alvo, daemon=True).start()
        else:
            alvo()


# ----------------------------------------------------------------------------
# Modo console para testar sem o Nexus:  python -m core.forge_engine
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    forge = NexusForge(falar=lambda t: print("NEXUS:", t),
                       ouvir=lambda: input("VOCÊ: "),
                       segundo_plano=False)
    print("Forge em modo console. Diga, por exemplo: vamos criar um aplicativo do zero  (ou 'sair')")
    while True:
        frase = input("comando> ")
        if _norm(frase) in ("sair", "exit"):
            break
        if not forge.tratar_comando(frase):
            print("(o Forge não reconheceu esse comando)")
