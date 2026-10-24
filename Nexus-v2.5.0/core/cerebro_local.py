"""CÉREBRO LOCAL — NEXUS Pro 2.3.

Prepara um modelo de linguagem PEQUENO, rodando no seu PC (Ollama), que transforma o que você fala em
uma chamada de função do NEXUS — sem internet e sem Gemini — e passa adiante ("[ENCAMINHAR]") tudo o
que não entende.

O que este módulo faz (tudo aqui, sem baixar nada):
  • monta o conjunto de treino em formato de chamada de função (JSONL) a partir das frases-modelo da
    rede de intenções + dos exemplos que você já ensinou usando o NEXUS;
  • gera o Modelfile do Ollama (já funciona "de cara", só com instruções e exemplos, sem treino),
    o script de ajuste fino LoRA (para rodar numa GPU, se você quiser) e um LEIA-ME;
  • confere se o Ollama está rodando e se o modelo existe; avalia o modelo com as frases de validação.

O que NÃO faz: treinar o modelo. O ajuste fino precisa de GPU e das bibliotecas transformers/peft/trl;
o script gerado roda no SEU PC. Sem treino, o modelo ainda funciona pela instrução + exemplos, mas erra mais.
"""
from __future__ import annotations

import json
import random
import re
import urllib.request
from pathlib import Path

ENCAMINHAR = "[ENCAMINHAR]"
MODELO_PADRAO = "nexus-local"
BASE_PADRAO = "qwen2.5:1.5b"
OLLAMA = "http://localhost:11434"
PASTA_SAIDA = Path(__file__).resolve().parent.parent / "memory" / "cerebro_local"

# intenção da rede → (função do NEXUS, argumentos fixos)
_FUNCAO = {
    "time_now": ("hora_atual", {}), "date_today": ("data_de_hoje", {}),
    "open_app": ("open_app", {}),
    "volume_up": ("computer_settings", {"action": "volume_up"}),
    "volume_down": ("computer_settings", {"action": "volume_down"}),
    "volume_mute": ("computer_settings", {"action": "mute"}),
    "volume_set": ("computer_settings", {"action": "volume_set"}),
    "media_play_pause": ("music_control", {"command": "play_pause"}),
    "media_next": ("music_control", {"command": "next"}),
    "media_previous": ("music_control", {"command": "previous"}),
    "timer_start": ("timer_action", {"action": "start"}),
    "timer_status": ("timer_action", {"action": "status"}),
    "timer_cancel": ("timer_action", {"action": "cancel"}),
    "note_add": ("quick_notes", {"action": "add"}),
    "note_list": ("quick_notes", {"action": "list"}),
    "email_check": ("email_checker", {"action": "check"}),
    "system_status": ("system_status", {}),
}


def _obj(desc: str, **props) -> dict:
    return {"type": "object", "description": desc,
            "properties": {k: {"type": t} for k, t in props.items()}}


FERRAMENTAS = [
    {"name": "hora_atual", "description": "Diz as horas.", "parameters": _obj("")},
    {"name": "data_de_hoje", "description": "Diz a data de hoje.", "parameters": _obj("")},
    {"name": "open_app", "description": "Abre um programa. app_name = nome do programa.",
     "parameters": _obj("", app_name="string")},
    {"name": "computer_settings", "description": "Volume do computador. action = volume_up | volume_down | mute | volume_set (com value 0-100).",
     "parameters": _obj("", action="string", value="integer")},
    {"name": "music_control", "description": "Controla a música. command = play_pause | next | previous.",
     "parameters": _obj("", command="string")},
    {"name": "timer_action", "description": "Timer. action = start (com minutes e/ou seconds) | status | cancel.",
     "parameters": _obj("", action="string", minutes="number", seconds="number")},
    {"name": "quick_notes", "description": "Notas rápidas. action = add (com text) | list.",
     "parameters": _obj("", action="string", text="string")},
    {"name": "email_checker", "description": "Confere e-mails novos. action = check.",
     "parameters": _obj("", action="string")},
    {"name": "system_status", "description": "Uso de CPU, memória e disco.", "parameters": _obj("")},
]

SISTEMA = (
    "Você é o cérebro local do NEXUS. Para cada pedido do usuário, responda SOMENTE com uma chamada de "
    "função quando o pedido for um destes comandos simples. Se não for um comando simples, ou se faltar "
    f"informação, responda exatamente {ENCAMINHAR} (sem mais nada). Nunca invente argumentos."
)


# ── conjunto de treino ───────────────────────────────────────────────────────
def exemplos(por_intencao: int = 60, semente: int = 5) -> list[tuple[str, str, dict | None]]:
    """[(frase, função, argumentos)] — função '' = encaminhar."""
    from core import intent_net as I
    rng = random.Random(semente)
    X, Y = I.build_dataset(seed=semente)
    pares = list(zip(X, [I.INTENTS[y] for y in Y]))
    for e in I._load_examples():                                   # o que você ensinou usando o NEXUS
        if e.get("intent") in I.INTENTS and e.get("text"):
            pares += [(e["text"], e["intent"])] * 3
    rng.shuffle(pares)
    cont: dict[str, int] = {}
    saida, vistos = [], set()
    for frase, intent in pares:
        chave = (I.normalize(frase), intent)
        if chave in vistos:
            continue
        lim = por_intencao * (6 if intent == "none" else 1)
        if cont.get(intent, 0) >= lim:
            continue
        if intent == "none":
            saida.append((frase, "", None))
        else:
            slots = I.extract_slots(intent, frase)
            if slots is None or intent not in _FUNCAO:
                continue
            tool, fixos = _FUNCAO[intent]
            saida.append((frase, tool, {**fixos, **slots}))
        vistos.add(chave)
        cont[intent] = cont.get(intent, 0) + 1
    return saida


def _mensagens(frase: str, tool: str, args: dict | None) -> dict:
    ass = ({"role": "assistant", "content": ENCAMINHAR} if not tool else
           {"role": "assistant", "content": "", "tool_calls": [
               {"type": "function", "function": {"name": tool, "arguments": args or {}}}]})
    return {"messages": [{"role": "system", "content": SISTEMA},
                         {"role": "user", "content": frase}, ass],
            "tools": [{"type": "function", "function": f} for f in FERRAMENTAS]}


_SCRIPT_LORA = '''"""Ajuste fino (LoRA) do cérebro local do NEXUS — rode no SEU PC, de preferência com GPU.

  pip install "transformers>=4.44" "peft>=0.12" "trl>=0.11" datasets accelerate torch
  python treinar_lora.py

Gera ./nexus-local-lora (adaptador). Depois, converta/mescle com a ferramenta de sua escolha
(llama.cpp: convert_lora_to_gguf.py) e crie o modelo no Ollama com um Modelfile contendo
  FROM <base>   e   ADAPTER ./nexus-local-lora.gguf
"""
import json
from datasets import Dataset
from peft import LoraConfig
from trl import SFTConfig, SFTTrainer

BASE = "{base_hf}"          # modelo base (Hugging Face), o mesmo do Ollama: {base}


def carregar(arq):
    linhas = [json.loads(l) for l in open(arq, encoding="utf-8")]
    return Dataset.from_list([{{"messages": l["messages"]}} for l in linhas])


treino, valid = carregar("treino.jsonl"), carregar("validacao.jsonl")
cfg = SFTConfig(output_dir="nexus-local-lora", num_train_epochs=3, per_device_train_batch_size=8,
                gradient_accumulation_steps=2, learning_rate=2e-4, logging_steps=20,
                eval_strategy="epoch", save_strategy="epoch", bf16=True, max_length=768)
lora = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, task_type="CAUSAL_LM",
                  target_modules=["q_proj", "k_proj", "v_proj", "o_proj"])
SFTTrainer(model=BASE, args=cfg, train_dataset=treino, eval_dataset=valid, peft_config=lora).train()
print("Pronto: ./nexus-local-lora")
'''

_BASE_HF = {"qwen2.5:0.5b": "Qwen/Qwen2.5-0.5B-Instruct", "qwen2.5:1.5b": "Qwen/Qwen2.5-1.5B-Instruct",
            "qwen2.5:3b": "Qwen/Qwen2.5-3B-Instruct"}


def _modelfile(base: str, amostra: list[tuple[str, str, dict | None]]) -> str:
    shots = []
    for frase, tool, args in amostra:
        resp = ENCAMINHAR if not tool else json.dumps({"name": tool, "arguments": args}, ensure_ascii=False)
        shots.append(f"Usuário: {frase}\nResposta: {resp}")
    sistema = SISTEMA + "\n\nFunções:\n" + "\n".join(
        f"- {f['name']}: {f['description']}" for f in FERRAMENTAS) + "\n\nExemplos:\n" + "\n\n".join(shots)
    sistema = sistema.replace('"""', "'''")
    return (f"FROM {base}\nPARAMETER temperature 0\nPARAMETER num_ctx 2048\n"
            f'SYSTEM """{sistema}"""\n')


def exportar(destino: Path | None = None, base: str = BASE_PADRAO, por_intencao: int = 60) -> dict:
    """Grava treino.jsonl, validacao.jsonl, Modelfile, treinar_lora.py e LEIA-ME.txt."""
    destino = Path(destino) if destino else PASTA_SAIDA
    destino.mkdir(parents=True, exist_ok=True)
    ex = exemplos(por_intencao)
    if len(ex) < 50:
        raise ValueError("Poucos exemplos para exportar.")
    rng = random.Random(1)
    rng.shuffle(ex)
    n_val = max(20, len(ex) // 10)
    valid, treino = ex[:n_val], ex[n_val:]
    for nome, lista in (("treino.jsonl", treino), ("validacao.jsonl", valid)):
        (destino / nome).write_text(
            "\n".join(json.dumps(_mensagens(*e), ensure_ascii=False) for e in lista) + "\n", encoding="utf-8")
    # exemplos curtos no Modelfile: 1 por função + alguns "encaminhar"
    shots, vistos = [], set()
    for e in treino:
        if e[1] not in vistos or (e[1] == "" and sum(1 for s in shots if s[1] == "") < 4):
            if e[1] == "" and e[1] in vistos and sum(1 for s in shots if s[1] == "") >= 4:
                continue
            vistos.add(e[1]); shots.append(e)
    (destino / "Modelfile").write_text(_modelfile(base, shots[:14]), encoding="utf-8")
    (destino / "treinar_lora.py").write_text(
        _SCRIPT_LORA.format(base=base, base_hf=_BASE_HF.get(base, "Qwen/Qwen2.5-1.5B-Instruct")), encoding="utf-8")
    (destino / "LEIA-ME.txt").write_text(
        f"CÉREBRO LOCAL DO NEXUS\n\n1) Instale o Ollama (ollama.com) e rode:  ollama pull {base}\n"
        f"2) Nesta pasta:  ollama create {MODELO_PADRAO} -f Modelfile\n"
        f"   Já funciona assim, sem treino (instruções + exemplos). Teste:  ollama run {MODELO_PADRAO}\n"
        "3) Opcional, para errar menos: rode treinar_lora.py numa máquina com GPU (instruções no topo do arquivo).\n"
        "4) Diga ao NEXUS: 'avalia o cérebro local' para medir o acerto com as frases de validação.\n\n"
        f"Quando o modelo não entende, ele responde {ENCAMINHAR} e o pedido segue para o Gemini como sempre.\n",
        encoding="utf-8")
    return {"pasta": str(destino), "treino": len(treino), "validacao": len(valid), "base": base}


# ── Ollama ───────────────────────────────────────────────────────────────────
def _http(caminho: str, corpo: dict | None = None, timeout: float = 60.0) -> dict:
    req = urllib.request.Request(
        OLLAMA + caminho, data=json.dumps(corpo).encode() if corpo is not None else None,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:        # só localhost
        return json.loads(r.read().decode("utf-8"))


def status(modelo: str = MODELO_PADRAO) -> dict:
    try:
        nomes = [m.get("name", "") for m in _http("/api/tags", timeout=3).get("models", [])]
    except Exception:
        return {"ollama": False, "modelo": False, "modelos": []}
    return {"ollama": True, "modelo": any(n == modelo or n.startswith(modelo + ":") for n in nomes), "modelos": nomes}


def _conferir_resposta(msg: dict) -> tuple[str, dict] | None:
    """(função, argumentos) da resposta do modelo, ou None = encaminhar."""
    for tc in msg.get("tool_calls") or []:
        f = tc.get("function") or {}
        if f.get("name"):
            a = f.get("arguments")
            return f["name"], (json.loads(a) if isinstance(a, str) else dict(a or {}))
    txt = (msg.get("content") or "").strip()
    if not txt or ENCAMINHAR in txt:
        return None
    m = re.search(r"\{.*\}", txt, re.S)                           # modelo que escreveu o JSON no texto
    if m:
        try:
            d = json.loads(m.group(0))
            if isinstance(d, dict) and d.get("name"):
                return str(d["name"]), dict(d.get("arguments") or {})
        except ValueError:
            pass
    return None


_FUNCOES_VALIDAS = {f["name"] for f in FERRAMENTAS}


def decidir(frase: str, modelo: str = MODELO_PADRAO, chamar=None) -> tuple[str, dict] | None:
    """O que o cérebro local faria com a frase. None = encaminhar ao Gemini. `chamar` é para testes."""
    chamar = chamar or (lambda corpo: _http("/api/chat", corpo))
    r = chamar({"model": modelo, "stream": False,
                "messages": [{"role": "system", "content": SISTEMA}, {"role": "user", "content": frase}],
                "tools": [{"type": "function", "function": f} for f in FERRAMENTAS],
                "options": {"temperature": 0}})
    d = _conferir_resposta(r.get("message") or {})
    if d is None or d[0] not in _FUNCOES_VALIDAS:                  # função inventada = não confiar
        return None
    return d


def avaliar(modelo: str = MODELO_PADRAO, pasta: Path | None = None, limite: int = 60, chamar=None) -> dict:
    arq = Path(pasta or PASTA_SAIDA) / "validacao.jsonl"
    if not arq.exists():
        raise FileNotFoundError("Exporte o conjunto antes (action=export).")
    linhas = [json.loads(l) for l in arq.read_text(encoding="utf-8").splitlines() if l.strip()][:limite]
    certos = encaminhou_certo = erros_perigosos = total_enc = 0
    for l in linhas:
        frase = l["messages"][1]["content"]
        esp = _conferir_resposta(l["messages"][2])
        obt = decidir(frase, modelo, chamar)
        if esp is None:
            total_enc += 1
            if obt is None:
                encaminhou_certo += 1
                certos += 1
            else:
                erros_perigosos += 1          # executaria algo que ninguém pediu
        else:
            if obt is not None and obt[0] == esp[0] and {k: str(v) for k, v in obt[1].items()} == {k: str(v) for k, v in esp[1].items()}:
                certos += 1
            elif obt is not None:
                erros_perigosos += 1
    n = max(1, len(linhas))
    return {"frases": len(linhas), "acerto": certos / n, "erros_perigosos": erros_perigosos,
            "encaminhou_certo": encaminhou_certo, "para_encaminhar": total_enc}
