"""Ligações pelo WhatsApp (NEXUS Ultra 2026 3.4).

"Liga pro Marcos no WhatsApp" / "faz uma chamada de vídeo com a Maria" / "liga no zap pro 11 98888-7777"

Como funciona (sem Qt, para poder ser testado sozinho):

  1. RESOLVER   quem é: o nome vai para os contatos do NEXUS (memory/contatos.json) e vira um número;
                um número dito direto é aceito como está. O DDI padrão (55, Brasil) entra quando falta.
  2. ABRIR      a conversa certa: ``whatsapp://send?phone=<número>`` — o próprio WhatsApp Desktop abre
                a conversa daquela pessoa, sem digitar nada às cegas. Sem número (contato só no celular),
                o NEXUS procura pelo nome dentro do WhatsApp (Ctrl+F), como a função de mensagens.
  3. LIGAR      o botão de voz ou de vídeo é achado pela árvore de acessibilidade do Windows
                (pywinauto), pelo NOME do botão — nunca por coordenada de tela.
  4. CONFERIR   depois do clique, procura o botão de encerrar a chamada. Só diz "liguei" se ele apareceu;
                se não deu para conferir, diz isso (nunca afirma uma ligação que não começou).

Um plugin de WhatsApp instalado (plugins/_whatsapp_core.py) que saiba ligar é usado primeiro.
"""
from __future__ import annotations

import re
import sys
import time
import unicodedata
from core.protecao import engolida as _engolida

TIPOS = ("voz", "video")

# Nomes que o WhatsApp Desktop dá aos botões, nos idiomas mais comuns. Comparação sem acento.
_BOTAO_VOZ = ("ligacao de voz", "chamada de voz", "chamada de audio", "ligacao de audio", "voice call",
              "audio call", "llamada de voz", "llamada", "ligar", "chamar", "call")
_BOTAO_VIDEO = ("ligacao de video", "chamada de video", "video call", "videochamada", "videollamada",
                "llamada de video")
_BOTAO_ENCERRAR = ("encerrar", "desligar", "end call", "hang up", "finalizar", "colgar", "terminar")
_JANELA = re.compile(r".*WhatsApp.*", re.IGNORECASE)


def _sem_acento(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c)).strip()


# ── 1. quem ──────────────────────────────────────────────────────────────────
def normalizar_tipo(valor) -> str:
    v = _sem_acento(valor)
    return "video" if ("vid" in v or "camera" in v or "cam" == v) else "voz"


def normalizar_numero(valor, ddi: str = "55") -> str:
    """'(11) 98888-7777' → '5511988887777'; '+1 415 555 0100' → '14155550100'; '' se não parece número.

    Com 10 ou 11 dígitos (DDD + número, o jeito brasileiro de falar) o DDI padrão entra na frente.
    """
    bruto = str(valor or "").strip()
    digitos = re.sub(r"\D", "", bruto)
    if bruto.startswith("00"):
        digitos = digitos[2:]
    if not 8 <= len(digitos) <= 15:
        return ""
    if not bruto.startswith(("+", "00")) and len(digitos) in (10, 11) and ddi:
        digitos = re.sub(r"\D", "", ddi) + digitos
    return digitos


def parece_numero(valor) -> bool:
    return len(re.sub(r"\D", "", str(valor or ""))) >= 8 and not re.search(r"[a-zA-Z]{3,}", str(valor or ""))


def resolver(alvo: str, contatos: list[dict], ddi: str = "55") -> dict:
    """Quem ligar. Devolve {nome, numero, exato, erro}.

    ``numero`` vazio com ``erro`` vazio = contato achado sem telefone (procura pelo nome no WhatsApp).
    ``exato`` = o nome bateu inteiro com um contato (vale para pular a confirmação, se você permitir).
    """
    alvo = str(alvo or "").strip()
    if not alvo:
        return {"nome": "", "numero": "", "exato": False, "erro": "Diga para quem ligar."}
    if parece_numero(alvo):
        num = normalizar_numero(alvo, ddi)
        if not num:
            return {"nome": alvo, "numero": "", "exato": False, "erro": "Esse número não parece completo."}
        for c in contatos:                                   # o número é de alguém conhecido?
            if c.get("telefone") and normalizar_numero(c["telefone"], ddi) == num:
                return {"nome": c["nome"], "numero": num, "exato": True, "erro": ""}
        return {"nome": alvo, "numero": num, "exato": False, "erro": ""}

    chave = _sem_acento(alvo)
    exatos = [c for c in contatos if _sem_acento(c.get("nome")) == chave]
    achados = exatos or [c for c in contatos if chave in _sem_acento(c.get("nome"))
                         or _sem_acento(c.get("nome")).split(" ")[0] == chave]
    if len(achados) > 1:
        nomes = " | ".join(str(c.get("nome")) for c in achados[:4])
        return {"nome": alvo, "numero": "", "exato": False,
                "erro": f"Mais de um contato combina ({nomes}). Pergunte qual deles."}
    if achados:
        c = achados[0]
        num = normalizar_numero(c.get("telefone"), ddi) if c.get("telefone") else ""
        return {"nome": c["nome"], "numero": num, "exato": bool(exatos), "erro": ""}
    # não está nos contatos do NEXUS: procura pelo nome dentro do próprio WhatsApp
    return {"nome": alvo, "numero": "", "exato": False, "erro": ""}


def url_conversa(numero: str) -> str:
    return f"whatsapp://send?phone={re.sub(r'[^0-9]', '', numero)}"


# ── 3. o botão certo ─────────────────────────────────────────────────────────
def escolher_botao(nomes: list[str], tipo: str) -> int:
    """Índice do botão que liga (voz ou vídeo) numa lista de nomes de botões; -1 se nenhum.

    Prefere o nome mais específico ("chamada de vídeo" vence "chamada"). Separado do pywinauto para
    poder ser testado com os nomes reais que o WhatsApp usa.
    """
    alvos = _BOTAO_VIDEO if tipo == "video" else _BOTAO_VOZ
    melhor, melhor_pos = -1, len(alvos) + 1
    for i, nome in enumerate(nomes):
        n = _sem_acento(nome)
        if not n:
            continue
        if tipo != "video" and any(v in n for v in ("video", "videollamada")):
            continue                                         # pediu voz: nunca clicar no de vídeo
        for pos, alvo in enumerate(alvos):
            if (n == alvo or n.startswith(alvo)) and pos < melhor_pos:
                melhor, melhor_pos = i, pos
                break
    return melhor


def e_botao_encerrar(nome: str) -> bool:
    n = _sem_acento(nome)
    return any(n.startswith(a) or f" {a}" in n for a in _BOTAO_ENCERRAR)


# ── 2-4. o WhatsApp de verdade (só no Windows) ───────────────────────────────
def _plugin_liga(nome: str, numero: str, tipo: str):
    """Usa um plugin de WhatsApp que saiba ligar. None = não há (segue o caminho próprio)."""
    try:
        from plugins import _whatsapp_core as wa
        transporte, _why = wa.get()
    except Exception:
        return None
    if transporte is None:
        return None
    for metodo in ("call_contact", "start_call", "call"):
        fn = getattr(transporte, metodo, None)
        if callable(fn):
            try:
                ok, falha = fn(numero or nome, video=(tipo == "video"))
                return bool(ok), str(falha or "")
            except TypeError:
                continue
            except Exception as e:                           # noqa: BLE001
                return False, str(e)
    return None


def _janela_whatsapp(espera: float = 12.0):
    from pywinauto import Desktop
    fim = time.monotonic() + espera
    while time.monotonic() < fim:
        try:
            for w in Desktop(backend="uia").windows(title_re=_JANELA.pattern, visible_only=True):
                return w
        except Exception:
            _engolida("core/whatsapp_ligacao.py:164")
        time.sleep(0.4)
    return None


def _botoes(janela) -> list:
    try:
        return [b for b in janela.descendants(control_type="Button")]
    except Exception:
        return []


def _nome(el) -> str:
    try:
        return str(el.window_text() or el.element_info.name or "")
    except Exception:
        return ""


def _abrir_conversa(nome: str, numero: str) -> tuple[object | None, str]:
    """Abre a conversa e devolve (janela, erro)."""
    import os
    if numero:
        try:
            os.startfile(url_conversa(numero))               # type: ignore[attr-defined]
        except Exception as e:                               # noqa: BLE001
            return None, f"o WhatsApp Desktop não abriu o link da conversa ({e}). Ele está instalado?"
        janela = _janela_whatsapp()
        if janela is None:
            return None, "a janela do WhatsApp não apareceu"
        time.sleep(1.5)                                      # a conversa termina de carregar
        return janela, ""
    # sem número: procura pelo nome dentro do WhatsApp
    try:
        os.startfile("whatsapp:")                            # type: ignore[attr-defined]
    except Exception:
        _engolida("core/whatsapp_ligacao.py:200")
    janela = _janela_whatsapp()
    if janela is None:
        return None, "a janela do WhatsApp não apareceu"
    try:
        import pyautogui
        janela.set_focus()
        pyautogui.hotkey("ctrl", "f")
        time.sleep(0.5)
        try:
            import pyperclip
            pyperclip.copy(nome)
            pyautogui.hotkey("ctrl", "v")
        except Exception:
            pyautogui.write(nome, interval=0.03)
        time.sleep(1.2)
        pyautogui.press("enter")
        time.sleep(1.5)
    except Exception as e:                                   # noqa: BLE001
        return None, f"não consegui procurar {nome} no WhatsApp ({e})"
    # confere que a conversa aberta é a da pessoa: o nome dela aparece no topo
    try:
        textos = [_sem_acento(_nome(t)) for t in janela.descendants(control_type="Text")[:80]]
        if not any(_sem_acento(nome) in t for t in textos if t):
            return None, f"não encontrei a conversa de {nome} no WhatsApp"
    except Exception:
        _engolida("core/whatsapp_ligacao.py:226")
    return janela, ""


def _clicar_ligar(janela, tipo: str) -> str:
    botoes = _botoes(janela)
    i = escolher_botao([_nome(b) for b in botoes], tipo)
    if i < 0:
        return "não achei o botão de ligar nessa conversa"
    alvo = botoes[i]
    try:
        alvo.click_input()
    except Exception as e:                                   # noqa: BLE001
        return f"não consegui clicar em ligar ({e})"
    # o WhatsApp novo abre um menuzinho "Voz / Vídeo" depois do botão "Ligar"
    time.sleep(0.8)
    if _sem_acento(_nome(alvo)) in ("ligar", "call", "llamada", "chamar"):
        try:
            itens = janela.descendants(control_type="MenuItem") + _botoes(janela)
            j = escolher_botao([_nome(x) for x in itens], tipo)
            if j >= 0:
                itens[j].click_input()
        except Exception:
            _engolida("core/whatsapp_ligacao.py:249")
    return ""


def _conferir_chamada(espera: float = 6.0) -> bool:
    """A chamada começou se algum botão de encerrar apareceu (na janela do WhatsApp ou na da chamada)."""
    try:
        from pywinauto import Desktop
    except Exception:
        return False
    fim = time.monotonic() + espera
    while time.monotonic() < fim:
        try:
            for w in Desktop(backend="uia").windows(visible_only=True):
                if "whatsapp" not in _sem_acento(_nome(w)):
                    continue
                if any(e_botao_encerrar(_nome(b)) for b in _botoes(w)):
                    return True
        except Exception:
            _engolida("core/whatsapp_ligacao.py:268")
        time.sleep(0.5)
    return False


def ligar(nome: str, numero: str, tipo: str = "voz") -> tuple[bool, str]:
    """Faz a ligação. Devolve (começou?, explicação). Nunca levanta exceção."""
    tipo = tipo if tipo in TIPOS else "voz"
    via_plugin = _plugin_liga(nome, numero, tipo)
    if via_plugin is not None:
        return via_plugin
    if sys.platform != "win32":
        return False, "a ligação pelo WhatsApp Desktop só funciona no Windows por enquanto"
    try:
        import pywinauto  # noqa: F401
    except Exception:
        return False, "falta o pacote pywinauto (pip install pywinauto)"
    try:
        janela, erro = _abrir_conversa(nome, numero)
        if janela is None:
            return False, erro
        erro = _clicar_ligar(janela, tipo)
        if erro:
            return False, erro
        if _conferir_chamada():
            return True, ""
        return True, "cliquei em ligar, mas não consegui conferir na tela se a chamada começou"
    except Exception as e:                                   # noqa: BLE001
        return False, f"o WhatsApp não respondeu como esperado ({e})"
