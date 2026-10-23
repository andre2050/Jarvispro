"""
core/llm_providers.py — o "cérebro" do MOTOR PRÓPRIO (NEXUS Pro 1.5).

Um único jeito de conversar com qualquer modelo de texto que saiba chamar
ferramentas:

    Claude (Anthropic)                       → API própria da Anthropic
    Gemini, OpenAI, Groq, DeepSeek, Mistral,
    xAI (Grok), OpenRouter, Ollama, LM Studio,
    llama.cpp, vLLM                          → o mesmo protocolo (chat/completions
                                               compatível com OpenAI)

Por isso basta UMA configuração: provedor, modelo, endereço e chave.

Também ficam aqui:
  • limpar_pensamento(): os blocos <think>…</think> do qwen3, deepseek-r1 e
    destilações nunca chegam à voz nem à conversa;
  • orcamento_ferramentas(): um modelo pequeno recebe só as ferramentas que
    importam para o pedido, por quantidade e por tamanho, em vez de todas.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
import uuid
from dataclasses import dataclass, field

import requests

# modelos de texto do Gemini para tentar quando o escolhido não existe mais (erro 404)
_GEMINI_ALTERNATIVOS = ("gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite",
                        "gemini-flash-latest", "gemini-2.5-flash-lite")

# ── Provedores ────────────────────────────────────────────────────────────────
# url: base do chat/completions compatível com OpenAI ("" = Claude nativo)
# local: roda no próprio PC (sem chave; orçamento de ferramentas ligado)
PROVEDORES: dict[str, dict] = {
    "claude":     {"nome": "Claude (Anthropic)", "url": "", "modelo": "claude-haiku-5-5",
                   "local": False, "chave": "anthropic_api_key"},
    "gemini":     {"nome": "Gemini (Google)", "local": False, "chave": "gemini_api_key",
                   "url": "https://generativelanguage.googleapis.com/v1beta/openai",
                   "modelo": "gemini-3.5-flash"},   # 2.3: o 2.5-flash saiu do ar para contas novas (erro 404)
    "openai":     {"nome": "OpenAI", "url": "https://api.openai.com/v1",
                   "modelo": "gpt-5-mini", "local": False},
    "groq":       {"nome": "Groq", "url": "https://api.groq.com/openai/v1",
                   "modelo": "llama-3.3-70b-versatile", "local": False},
    "deepseek":   {"nome": "DeepSeek", "url": "https://api.deepseek.com/v1",
                   "modelo": "deepseek-chat", "local": False},
    "mistral":    {"nome": "Mistral", "url": "https://api.mistral.ai/v1",
                   "modelo": "mistral-small-latest", "local": False},
    "xai":        {"nome": "xAI (Grok)", "url": "https://api.x.ai/v1",
                   "modelo": "grok-3-mini", "local": False},
    "openrouter": {"nome": "OpenRouter", "url": "https://openrouter.ai/api/v1",
                   "modelo": "meta-llama/llama-3.3-70b-instruct", "local": False},
    "ollama":     {"nome": "Ollama (no PC)", "url": "http://localhost:11434/v1",
                   "modelo": "qwen3:8b", "local": True},
    "lmstudio":   {"nome": "LM Studio (no PC)", "url": "http://localhost:1234/v1",
                   "modelo": "", "local": True},
    "llamacpp":   {"nome": "llama.cpp (no PC)", "url": "http://localhost:8080/v1",
                   "modelo": "", "local": True},
    "vllm":       {"nome": "vLLM", "url": "http://localhost:8000/v1",
                   "modelo": "", "local": True},
}


def info_provedor(nome: str) -> dict:
    return PROVEDORES.get(str(nome or "").strip().lower(), PROVEDORES["gemini"])


# ── Raciocínio privado ────────────────────────────────────────────────────────
_THINK = re.compile(r"<(think|thinking|reasoning)>.*?</\1>", re.IGNORECASE | re.DOTALL)
_THINK_ABERTO = re.compile(r"<(?:think|thinking|reasoning)>.*\Z", re.IGNORECASE | re.DOTALL)
_THINK_FECHA = re.compile(r"\A.*?</(?:think|thinking|reasoning)>", re.IGNORECASE | re.DOTALL)


def limpar_pensamento(texto: str) -> str:
    """Tira o raciocínio interno de modelos como qwen3 / deepseek-r1.

    '<think>planejando…</think>Olá!'  →  'Olá!'
    'planejando…</think>Olá!'          →  'Olá!'   (abertura cortada pelo servidor)
    'Olá! <think>e agora…'             →  'Olá!'   (resposta cortada no meio)"""
    t = str(texto or "")
    t = _THINK.sub("", t)
    if re.search(r"</(?:think|thinking|reasoning)>", t, re.IGNORECASE):
        t = _THINK_FECHA.sub("", t)
    t = _THINK_ABERTO.sub("", t)
    return t.strip()


# ── Orçamento de ferramentas ──────────────────────────────────────────────────
# Sempre vão (são baratas e são o "básico" de um assistente de voz)
ESSENCIAIS = ("save_memory", "recall_memory", "open_app", "web_search",
              "computer_settings", "system_status", "undo")

# Palavras do português que apontam para uma ferramenta (as descrições estão
# em inglês; isto evita que "toca uma música" perca para "music_control").
_DICAS = {
    "open_app": "abre abrir abra inicia executa programa aplicativo app",
    "computer_settings": "volume brilho wifi desliga reinicia bloqueia janela fecha tela cheia modo escuro som",
    "web_search": "pesquisa procura busca noticia noticias preco quanto custa quem e o que e compara",
    "weather_report": "tempo clima chuva chover temperatura frio calor previsao",
    "reminder": "lembra lembrete lembretes lembrar avisa avise me lembre cancela lembrete",
    "timer_action": "timer cronometro temporizador alarme minutos segundos",
    "email_checker": "email emails e-mail caixa de entrada gmail outlook",
    "email_reader": "email emails e-mail le meus manda enviar envia responde responder mandar",
    "music_control": "musica toca pausa proxima anterior play spotify",
    "file_controller": "arquivo arquivos pasta pastas apaga move copia renomeia temp temporarios ocultos",
    "screen_process": "tela ve olha olhe camera vendo enxerga mostra",
    "quick_notes": "nota notas anota anote",
    "notepad": "bloco de notas ditado escreve",
    "browser_control": "navegador site pagina aba clica chrome edge firefox",
    "send_message": "mensagem manda envia whatsapp telegram",
    "youtube_video": "youtube video videos",
    "video_player": "video assistir reproduz",
    "code_helper": "codigo script programa python roda",
    "dev_agent": "projeto cria um programa site completo",
    "routines": "rotina rotinas modo",
    "unit_converter": "converte dolar euro real km milhas graus",
    "memory_bank": "lembra de mim memoria guarda",
    "desktop_control": "area de trabalho papel de parede organiza icones",
    "agent_task": "tarefa varios passos sozinho autonomo planeja e executa",
    "daily_planner": "planeja meu dia agenda plano",
    "everyday_tools": "calcula porcentagem dias ate fuso",
    "focus_mode": "foco pomodoro concentrar",
    "noticias": "noticia noticias manchete manchetes jornal aconteceu",
    "mapas": "mapa mapas rota chegar caminho trajeto perto distancia onde fica",
    "tarefas": "tarefa tarefas afazeres fazer lista pendente concluir feita produtividade",
    "projetos": "projeto projetos proximo passo registra terminei pausa",
    "computer_control": "clica digita aperta tecla mouse",
    "compras": "compras comprar mercado supermercado farmacia feira lista falta comprei",
    "rastreador_habitos": "habito habitos meta sequencia bebi agua copos exercicio treinei li paginas meditei",
    "contatos": "contato contatos telefone numero aniversario aniversarios faz anos email da agenda",
    "manutencao_pc": "espaco disco limpa temporarios backup ip ping conexao bateria ocupando",
    "texto_dev": "palavras maiusculas minusculas hash base64 json uuid timestamp slug codifica formata",
    "diario": "diario humor escrevi escreve no diario como me senti",
    "voz_treino": "voz treino cadastra minha voz trava de voz palavra nexus treinar chamada reconhecer dono",
    "cerebro_local": "cerebro local ollama modelo offline prepara avalia funcao lora treino",
    "previsao_habitos": "previsao habitos costumo fazer agora dia tipico rotina prever treinar",
    "anomalia_pc": "anomalia pc estranho lento travando cpu memoria disco rede detector normal",
    "financas_ia": "financas previsao fechar mes gastando categoria do gasto prever despesa quanto vou gastar",
    "visao_ia": "visao camera rostos reconhecer quem esta objetos pessoas contar frente cadastra rosto yolo",
}


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", t)


def _nome_decl(d) -> str:
    return (d.get("name") if isinstance(d, dict) else getattr(d, "name", "")) or ""


def _tam_decl(d) -> int:
    try:
        return len(json.dumps(d, ensure_ascii=False, default=str))
    except Exception:
        return 800


def orcamento_ferramentas(decls: list, pedido: str, max_qtd: int = 12,
                          max_chars: int = 9000, essenciais=ESSENCIAIS) -> list:
    """As ferramentas que importam para ESTE pedido, dentro de um orçamento.

    Ordem: as essenciais, depois as mais parecidas com o pedido (nome, descrição
    e as dicas em português), cortando por quantidade e por tamanho total."""
    if not decls:
        return []
    palavras = {w for w in _norm(pedido).split() if len(w) > 2}
    por_nome = {_nome_decl(d): d for d in decls}

    def nota(d) -> float:
        nome = _nome_decl(d)
        texto = _norm(f"{nome.replace('_', ' ')} "
                      f"{d.get('description', '') if isinstance(d, dict) else getattr(d, 'description', '')} "
                      f"{_DICAS.get(nome, '')}")
        alvo = set(texto.split())
        n = sum(1.0 for w in palavras if w in alvo)
        n += sum(0.5 for w in palavras for a in alvo if len(w) > 4 and a.startswith(w[:5]))
        n += 3.0 * sum(1 for w in palavras if w in _DICAS.get(nome, "").split())
        return n

    escolhidas, total = [], 0
    for nome in essenciais:
        d = por_nome.get(nome)
        if d is not None and d not in escolhidas:
            escolhidas.append(d); total += _tam_decl(d)
    resto = sorted((d for d in decls if d not in escolhidas), key=nota, reverse=True)
    for d in resto:
        if len(escolhidas) >= max_qtd:
            break
        if nota(d) <= 0:
            break
        t = _tam_decl(d)
        if total + t > max_chars:
            continue
        escolhidas.append(d); total += t
    return escolhidas


# ── Esquema das ferramentas ───────────────────────────────────────────────────
def esquema_json(node):
    """Declarações do Gemini usam tipos em MAIÚSCULAS ("OBJECT"); o JSON Schema
    do Claude e do protocolo OpenAI quer minúsculas. Nomes de propriedades não
    são mexidos."""
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == "properties" and isinstance(v, dict):
                out[k] = {pk: esquema_json(pv) for pk, pv in v.items()}
            elif k == "type" and isinstance(v, str):
                out[k] = v.lower()
            elif k in ("handler", "behavior", "scheduling"):
                continue
            else:
                out[k] = esquema_json(v)
        return out
    if isinstance(node, list):
        return [esquema_json(x) for x in node]
    return node


def _decl_dict(d) -> dict:
    if isinstance(d, dict):
        return d
    out = {"name": getattr(d, "name", ""), "description": getattr(d, "description", "") or ""}
    params = getattr(d, "parameters", None)
    if params is not None:
        try:
            out["parameters"] = params.model_dump(exclude_none=True)
        except Exception:
            out["parameters"] = {"type": "OBJECT", "properties": {}}
    return out


def ferramentas_openai(decls: list) -> list:
    out = []
    for d in decls:
        d = _decl_dict(d)
        params = esquema_json(d.get("parameters") or {"type": "OBJECT", "properties": {}})
        params.setdefault("type", "object")
        params.setdefault("properties", {})
        out.append({"type": "function", "function": {
            "name": d["name"], "description": (d.get("description") or "")[:1024],
            "parameters": params}})
    return out


def ferramentas_claude(decls: list) -> list:
    out = []
    for d in decls:
        d = _decl_dict(d)
        params = esquema_json(d.get("parameters") or {"type": "OBJECT", "properties": {}})
        params.setdefault("type", "object")
        params.setdefault("properties", {})
        out.append({"name": d["name"], "description": (d.get("description") or "")[:1024],
                    "input_schema": params})
    return out


# ── Conversa ──────────────────────────────────────────────────────────────────
# Formato neutro das mensagens (convertido para cada protocolo na hora):
#   {"role": "user", "content": str, "images": [(mime, base64)]}
#   {"role": "assistant", "content": str, "tool_calls": [{"id","name","args"}]}
#   {"role": "tool", "tool_call_id": str, "name": str, "content": str}

@dataclass
class Resposta:
    texto: str = ""
    chamadas: list = field(default_factory=list)   # [{"id","name","args"}]


class ErroLLM(RuntimeError):
    pass


class CerebroLLM:
    def __init__(self, provedor: str, modelo: str = "", url: str = "", chave: str = "",
                 timeout: float = 60.0):
        self.provedor = str(provedor or "gemini").strip().lower()
        info = info_provedor(self.provedor)
        self.nativo_claude = self.provedor == "claude"
        self.url = (url or info.get("url") or "").rstrip("/")
        self.modelo = (modelo or info.get("modelo") or "").strip()
        self.chave = (chave or "").strip()
        self.timeout = timeout
        self.local = bool(info.get("local"))
        self._http = requests.Session()
        self._claude = None
        if self.nativo_claude:
            if not self.chave:
                raise ErroLLM("falta a chave da Anthropic (anthropic_api_key)")
            import anthropic
            self._claude = anthropic.Anthropic(api_key=self.chave, timeout=timeout, max_retries=1)
        elif not self.local and not self.chave:
            raise ErroLLM(f"falta a chave do {info.get('nome', self.provedor)}")

    # ── descobrir o modelo carregado (LM Studio, llama.cpp, vLLM) ──
    def _modelo(self) -> str:
        if self.modelo:
            return self.modelo
        try:
            r = self._http.get(f"{self.url}/models", headers=self._headers(), timeout=5)
            r.raise_for_status()
            ids = [m.get("id") for m in (r.json().get("data") or []) if m.get("id")]
            if ids:
                self.modelo = ids[0]
                return self.modelo
        except Exception as e:
            raise ErroLLM(f"não achei um modelo carregado em {self.url} ({e})")
        raise ErroLLM(f"nenhum modelo carregado em {self.url}")

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.chave:
            h["Authorization"] = f"Bearer {self.chave}"
        if self.provedor == "openrouter":
            h["HTTP-Referer"] = "https://github.com/andre2050/Jarvispro"
            h["X-Title"] = "NEXUS Pro"
        return h

    def descricao(self) -> str:
        return f"{info_provedor(self.provedor).get('nome', self.provedor)} · {self.modelo or 'modelo carregado'}"

    # ── chamada ──
    def conversar(self, sistema: str, mensagens: list, ferramentas: list,
                  max_tokens: int = 1024) -> Resposta:
        if self.nativo_claude:
            return self._claude_chat(sistema, mensagens, ferramentas, max_tokens)
        return self._openai_chat(sistema, mensagens, ferramentas, max_tokens)

    # ── OpenAI-compatível ──
    def _openai_msgs(self, sistema: str, mensagens: list) -> list:
        out = [{"role": "system", "content": sistema}] if sistema else []
        for m in mensagens:
            r = m.get("role")
            if r == "user":
                imgs = m.get("images") or []
                if imgs:
                    partes = [{"type": "text", "text": m.get("content") or ""}]
                    for mime, b64 in imgs:
                        partes.append({"type": "image_url",
                                       "image_url": {"url": f"data:{mime};base64,{b64}"}})
                    out.append({"role": "user", "content": partes})
                else:
                    out.append({"role": "user", "content": m.get("content") or ""})
            elif r == "assistant":
                msg = {"role": "assistant", "content": m.get("content") or ""}
                if m.get("tool_calls"):
                    msg["tool_calls"] = [{"id": c["id"], "type": "function", "function": {
                        "name": c["name"], "arguments": json.dumps(c.get("args") or {}, ensure_ascii=False)}}
                        for c in m["tool_calls"]]
                out.append(msg)
            elif r == "tool":
                out.append({"role": "tool", "tool_call_id": m.get("tool_call_id"),
                            "name": m.get("name"), "content": m.get("content") or ""})
        return out

    def _openai_chat(self, sistema, mensagens, ferramentas, max_tokens) -> Resposta:
        corpo = {"model": self._modelo(), "messages": self._openai_msgs(sistema, mensagens),
                 "max_tokens": max_tokens, "temperature": 0.6}
        if ferramentas:
            corpo["tools"] = ferramentas_openai(ferramentas)
            corpo["tool_choice"] = "auto"
        if self.provedor == "openai":
            corpo.pop("max_tokens", None)
            corpo["max_completion_tokens"] = max_tokens
            corpo.pop("temperature", None)
        try:
            r = self._http.post(f"{self.url}/chat/completions", headers=self._headers(),
                                data=json.dumps(corpo, ensure_ascii=False).encode("utf-8"),
                                timeout=self.timeout)
        except requests.exceptions.ConnectionError:
            if self.local:
                raise ErroLLM(f"o servidor local não respondeu em {self.url} — ele está aberto?")
            raise
        if r.status_code == 404 and self.provedor == "gemini" and "model" in r.text.lower():
            # 2.3 — o Google aposenta modelos: se este não existe mais para a sua conta, tenta os atuais
            # em ordem e passa a usar o primeiro que responde (sem você precisar mexer em nada).
            tentados = getattr(self, "_gemini_tentados", set())
            tentados.add(corpo["model"])
            self._gemini_tentados = tentados
            for alt in _GEMINI_ALTERNATIVOS:
                if alt not in tentados:
                    self.modelo = alt
                    return self._openai_chat(sistema, mensagens, ferramentas, max_tokens)
        if r.status_code >= 400:
            raise ErroLLM(f"{r.status_code}: {r.text[:300]}")
        dados = r.json()
        try:
            msg = dados["choices"][0]["message"]
        except Exception:
            raise ErroLLM(f"resposta inesperada: {str(dados)[:200]}")
        chamadas = []
        for c in msg.get("tool_calls") or []:
            fn = c.get("function") or {}
            args = fn.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args.strip() else {}
                except Exception:
                    args = {}
            chamadas.append({"id": c.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                             "name": fn.get("name") or "", "args": args or {}})
        texto = msg.get("content") or ""
        if isinstance(texto, list):        # alguns servidores mandam partes
            texto = "".join(p.get("text", "") for p in texto if isinstance(p, dict))
        return Resposta(texto=limpar_pensamento(texto), chamadas=chamadas)

    # ── Claude ──
    def _claude_msgs(self, mensagens: list) -> list:
        out: list[dict] = []
        for m in mensagens:
            r = m.get("role")
            if r == "user":
                imgs = m.get("images") or []
                partes = [{"type": "image", "source": {"type": "base64", "media_type": mime,
                                                       "data": b64}} for mime, b64 in imgs]
                partes.append({"type": "text", "text": m.get("content") or " "})
                if out and out[-1]["role"] == "user":
                    # duas falas seguidas do usuário (ex.: resultado + imagem): uma só
                    ant = out[-1]["content"]
                    if isinstance(ant, str):
                        ant = [{"type": "text", "text": ant}]
                    out[-1]["content"] = ant + partes
                elif imgs:
                    out.append({"role": "user", "content": partes})
                else:
                    out.append({"role": "user", "content": m.get("content") or " "})
            elif r == "assistant":
                blocos = []
                if m.get("content"):
                    blocos.append({"type": "text", "text": m["content"]})
                for c in m.get("tool_calls") or []:
                    blocos.append({"type": "tool_use", "id": c["id"], "name": c["name"],
                                   "input": c.get("args") or {}})
                out.append({"role": "assistant", "content": blocos or [{"type": "text", "text": " "}]})
            elif r == "tool":
                bloco = {"type": "tool_result", "tool_use_id": m.get("tool_call_id"),
                         "content": m.get("content") or ""}
                if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list) \
                        and out[-1]["content"] and out[-1]["content"][0].get("type") == "tool_result":
                    out[-1]["content"].append(bloco)
                else:
                    out.append({"role": "user", "content": [bloco]})
        return out

    def _claude_chat(self, sistema, mensagens, ferramentas, max_tokens) -> Resposta:
        kw = {"model": self.modelo, "max_tokens": max_tokens, "system": sistema,
              "messages": self._claude_msgs(mensagens)}
        if ferramentas:
            kw["tools"] = ferramentas_claude(ferramentas)
        resp = self._claude.messages.create(**kw)
        texto, chamadas = [], []
        for b in resp.content:
            tipo = getattr(b, "type", "")
            if tipo == "text":
                texto.append(getattr(b, "text", ""))
            elif tipo == "tool_use":
                chamadas.append({"id": b.id, "name": b.name, "args": dict(b.input or {})})
        return Resposta(texto=limpar_pensamento("".join(texto)), chamadas=chamadas)


def janela_historico(hist: list, maximo: int = 30) -> list:
    """Últimas mensagens, começando SEMPRE numa fala do usuário (nunca num
    resultado de ferramenta solto, que os servidores recusam)."""
    msgs = hist[-maximo:]
    while msgs and not (msgs[0].get("role") == "user"):
        msgs = msgs[1:]
    return msgs


def testar_conexao(cerebro: CerebroLLM) -> tuple[bool, str]:
    """Pergunta curta para o botão TESTAR da configuração."""
    t0 = time.monotonic()
    try:
        r = cerebro.conversar("Responda só com: ok", [{"role": "user", "content": "teste"}], [],
                              max_tokens=16)
        return True, f"respondeu em {time.monotonic() - t0:.1f} s: {r.texto[:40]!r}"
    except Exception as e:
        return False, str(e)[:200]
