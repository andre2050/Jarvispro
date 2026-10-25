"""Bloco de Notas do Windows + modo ditado (NEXUS Ultra 2026 1.4).

DUAS PARTES

1) JanelaBlocoDeNotas — fala direto com a janela do Bloco de Notas pelas
   mensagens do Windows (as mesmas que o teclado usa por dentro). Escreve no
   fim do texto, apaga o último trecho e lê o que está escrito — SEM precisar
   que a janela esteja na frente e sem simular teclado, então nunca digita por
   engano em outro programa. Funciona no Bloco de Notas clássico (controle
   "Edit") e no novo do Windows 11 (controle "RichEditD2DPT").

2) Ditado — o modo "escreve tudo o que eu falar":
     • abre um Bloco de Notas novo (com um arquivo em Documentos\\NEXUS Notas\\Ditados)
     • cada frase que você fala vai para lá, com maiúscula e espaço certos
     • comandos de voz durante o ditado:
         "nova linha" / "pula linha"          → quebra de linha
         "novo parágrafo"                     → linha em branco
         "vírgula", "ponto final", "dois pontos", "ponto de interrogação"…
         "apaga a última frase" / "apaga isso" → desfaz o último trecho
         "parar ditado" / "terminar ditado"   → encerra
     • enquanto dita, o NEXUS fica em silêncio e não executa comandos
     • tudo também vai para o arquivo .txt (cópia de segurança)

Em outros sistemas (ou se a janela não aceitar), o texto vai só para o
arquivo, que é aberto no editor padrão ao terminar.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Callable

NO_WINDOWS = sys.platform.startswith("win")


# ═══════════════════════════════════════════════════════════════════════════
#  Pastas
# ═══════════════════════════════════════════════════════════════════════════

def pasta_notas() -> Path:
    """Documentos\\NEXUS Notas (segue a pasta real, inclusive com OneDrive)."""
    try:
        from actions.file_controller import _get_documents
        docs = _get_documents()
    except Exception:
        docs = Path.home() / "Documents"
    if not docs.exists():
        docs = Path.home()
    pasta = docs / "NEXUS Notas"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def pasta_ditados() -> Path:
    p = pasta_notas() / "Ditados"
    p.mkdir(parents=True, exist_ok=True)
    return p


def nome_seguro(texto: str, limite: int = 60) -> str:
    texto = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", str(texto or "")).strip().strip(".")
    texto = re.sub(r"\s+", " ", texto)
    return texto[:limite].strip() or "nota"


# ═══════════════════════════════════════════════════════════════════════════
#  A janela do Bloco de Notas (Windows)
# ═══════════════════════════════════════════════════════════════════════════

WM_SETTEXT = 0x000C
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
EM_SETSEL = 0x00B1
EM_SCROLLCARET = 0x00B7
EM_REPLACESEL = 0x00C2
_CLASSES_EDITOR = ("RichEditD2DPT", "Edit", "RICHEDIT50W")


def _user32():
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    u.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    u.SendMessageW.restype = wintypes.LPARAM
    return u


def _classe(hwnd) -> str:
    import ctypes
    buf = ctypes.create_unicode_buffer(256)
    _user32().GetClassNameW(hwnd, buf, 256)
    return buf.value


def _titulo(hwnd) -> str:
    import ctypes
    buf = ctypes.create_unicode_buffer(512)
    _user32().GetWindowTextW(hwnd, buf, 512)
    return buf.value


def janelas_do_bloco() -> list[int]:
    """Todas as janelas principais do Bloco de Notas abertas agora."""
    if not NO_WINDOWS:
        return []
    import ctypes
    from ctypes import wintypes
    u = _user32()
    achadas: list[int] = []
    PROTO = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _cb(hwnd, _l):
        try:
            if u.IsWindowVisible(hwnd) and _classe(hwnd) == "Notepad":
                achadas.append(int(hwnd))
        except Exception:
            pass
        return True

    u.EnumWindows(PROTO(_cb), 0)
    return achadas


def _editor_de(hwnd: int) -> int | None:
    """O controle de texto visível dentro da janela (a aba ativa no Windows 11)."""
    import ctypes
    from ctypes import wintypes
    u = _user32()
    visiveis: list[int] = []
    ocultos: list[int] = []
    PROTO = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _cb(h, _l):
        try:
            if _classe(h) in _CLASSES_EDITOR:
                (visiveis if u.IsWindowVisible(h) else ocultos).append(int(h))
        except Exception:
            pass
        return True

    u.EnumChildWindows(hwnd, PROTO(_cb), 0)
    return (visiveis or ocultos or [None])[0]


class JanelaBlocoDeNotas:
    """Uma janela do Bloco de Notas, controlada por mensagens do Windows."""

    def __init__(self, hwnd: int):
        self.hwnd = hwnd

    @classmethod
    def abrir(cls, arquivo: Path | None = None, espera: float = 8.0) -> "JanelaBlocoDeNotas | None":
        if not NO_WINDOWS:
            return None
        antes = set(janelas_do_bloco())
        args = ["notepad.exe"] + ([str(arquivo)] if arquivo else [])
        subprocess.Popen(args)
        alvo = arquivo.stem.lower() if arquivo else ""
        fim = time.time() + espera
        while time.time() < fim:
            time.sleep(0.25)
            atuais = janelas_do_bloco()
            if alvo:
                for h in atuais:
                    if alvo in _titulo(h).lower() and _editor_de(h):
                        return cls(h)
            novas = [h for h in atuais if h not in antes]
            for h in novas:
                if _editor_de(h):
                    return cls(h)
        # Windows 11 pode abrir como ABA numa janela que já existia
        for h in janelas_do_bloco():
            if _editor_de(h):
                return cls(h)
        return None

    @classmethod
    def atual(cls) -> "JanelaBlocoDeNotas | None":
        """A janela do Bloco de Notas da frente (ou a primeira aberta)."""
        if not NO_WINDOWS:
            return None
        janelas = janelas_do_bloco()
        if not janelas:
            return None
        try:
            frente = int(_user32().GetForegroundWindow())
            if frente in janelas:
                return cls(frente)
        except Exception:
            pass
        return cls(janelas[0])

    def _editor(self) -> int | None:
        return _editor_de(self.hwnd)

    def viva(self) -> bool:
        try:
            return bool(_user32().IsWindow(self.hwnd)) and self._editor() is not None
        except Exception:
            return False

    def tamanho(self) -> int:
        ed = self._editor()
        return int(_user32().SendMessageW(ed, WM_GETTEXTLENGTH, 0, 0)) if ed else -1

    def escrever(self, texto: str) -> bool:
        """Acrescenta no FIM do texto. Devolve True se o texto realmente entrou."""
        import ctypes
        ed = self._editor()
        if not ed or not texto:
            return False
        u = _user32()
        antes = int(u.SendMessageW(ed, WM_GETTEXTLENGTH, 0, 0))
        buf = ctypes.create_unicode_buffer(texto.replace("\r\n", "\n").replace("\n", "\r\n"))
        u.SendMessageW(ed, EM_SETSEL, antes, antes)
        u.SendMessageW(ed, EM_REPLACESEL, 1, ctypes.addressof(buf))
        u.SendMessageW(ed, EM_SCROLLCARET, 0, 0)
        return int(u.SendMessageW(ed, WM_GETTEXTLENGTH, 0, 0)) > antes

    def apagar_ultimos(self, n: int) -> bool:
        import ctypes
        ed = self._editor()
        if not ed or n <= 0:
            return False
        u = _user32()
        total = int(u.SendMessageW(ed, WM_GETTEXTLENGTH, 0, 0))
        vazio = ctypes.create_unicode_buffer("")
        u.SendMessageW(ed, EM_SETSEL, max(0, total - n), total)
        u.SendMessageW(ed, EM_REPLACESEL, 1, ctypes.addressof(vazio))
        return True

    def ler(self, limite: int = 200_000) -> str:
        import ctypes
        ed = self._editor()
        if not ed:
            return ""
        u = _user32()
        n = min(limite, int(u.SendMessageW(ed, WM_GETTEXTLENGTH, 0, 0)))
        buf = ctypes.create_unicode_buffer(n + 1)
        u.SendMessageW(ed, WM_GETTEXT, n + 1, ctypes.addressof(buf))
        return buf.value

    def frente(self) -> None:
        try:
            _user32().SetForegroundWindow(self.hwnd)
        except Exception:
            pass


def abrir_no_editor(arquivo: Path) -> None:
    """Abre um arquivo no Bloco de Notas (Windows) ou no editor padrão."""
    if NO_WINDOWS:
        subprocess.Popen(["notepad.exe", str(arquivo)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-e", str(arquivo)])
    else:
        subprocess.Popen(["xdg-open", str(arquivo)])


# ═══════════════════════════════════════════════════════════════════════════
#  Ditado
# ═══════════════════════════════════════════════════════════════════════════

def _sem_acento(t: str) -> str:
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii").lower()


_PARAR = re.compile(
    r"\b(?:(?:parar|pare|para|terminar|termina|encerrar|encerra|finalizar|finaliza|acabar|acaba|"
    r"desligar|desliga|desativar|desativa|sair|sai)"
    r"\s+(?:o\s+|do\s+|de\s+|com\s+o\s+)?(?:modo\s+)?(?:ditado|escrever|digitar)|fim\s+do\s+ditado|"
    r"chega\s+de\s+(?:ditado|escrever|digitar)|pode\s+parar\s+de\s+(?:escrever|digitar))\b")
# "Nexus, parar ditado": o nome do assistente antes do comando não vai para o texto
_SO_CHAMADO = re.compile(r"^(?:(?:ok|ei|ey|hey|oi|e ai)\s*)?(?:nexus|jarvis)?$")
_DESFAZER = re.compile(r"^(?:apaga(?:r)?|desfaz(?:er)?|remove(?:r)?)\s*(?:a\s+)?(?:ultima\s+frase|isso|o\s+ultimo|a\s+ultima)?$")

# (expressão falada, o que entra no texto) — comparado sem acento
_SUBSTITUICOES = [
    (r"novo paragrafo|proximo paragrafo", "\n\n"),
    (r"nova linha|proxima linha|pula(?:r)? (?:uma )?linha|quebra de linha", "\n"),
    (r"ponto de interrogacao", "?"),
    (r"ponto de exclamacao", "!"),
    (r"ponto e virgula", ";"),
    (r"ponto final", "."),
    (r"dois pontos", ":"),
    (r"reticencias", "…"),
    (r"virgula", ","),
    (r"abre aspas", "“"),
    (r"fecha aspas", "”"),
    (r"abre parenteses", "("),
    (r"fecha parenteses", ")"),
    (r"travessao", "—"),
]
_COLA = {".", ",", ";", ":", "!", "?", "…", ")", "”"}   # gruda na palavra de antes


def _aplicar_comandos(frase: str) -> str:
    """Troca os comandos falados ("vírgula", "nova linha"…) pelos sinais e
    acerta espaços e maiúsculas dentro da frase."""
    frase = (frase or "").strip()
    sem = _sem_acento(frase)
    if len(sem) != len(frase):          # caractere estranho: não arrisca trocar nada
        return frase
    achados = []
    for padrao, sinal in _SUBSTITUICOES:
        for m in re.finditer(rf"\b(?:{padrao})\b", sem):
            achados.append((m.start(), m.end(), sinal))
    achados.sort(key=lambda a: (a[0], a[0] - a[1]))
    partes: list[tuple[str, str]] = []
    pos = 0
    for ini, fim, sinal in achados:
        if ini < pos:
            continue
        partes.append(("t", frase[pos:ini]))
        partes.append(("s", sinal))
        resto = re.match(r" *[.,!?]", frase[fim:])      # pontuação que a transcrição pôs no comando
        pos = fim + (resto.end() if resto else 0)
    partes.append(("t", frase[pos:]))

    out = ""
    for tipo, val in partes:
        if tipo == "t":
            v = val.strip()
            if not v:
                continue
            if out and not out.endswith((" ", "\n", "(", "“")):
                out += " "
            out += v
        elif val in _COLA:
            out = out.rstrip(" ") + val + " "
        elif val.startswith("\n"):
            out = out.rstrip(" ") + val
        elif val in ("(", "“"):
            out = (out.rstrip(" ") + " " if out.strip(" ") else out) + val
        elif val == "—":
            out = out.rstrip(" ") + " — "
    out = re.sub(r"([.,;:!?])(?: *\1)+", r"\1", out)
    out = re.sub(r" {2,}", " ", out)
    # maiúscula depois de ponto final, exclamação, interrogação ou linha nova
    out = re.sub(r"([.!?…] +|\n)([a-zà-ÿ])", lambda m: m.group(1) + m.group(2).upper(), out)
    return out.rstrip(" ")


class Ditado:
    """O modo ditado. Um só para o NEXUS inteiro: `ditado` (abaixo)."""

    PAUSA_PARA_ESCREVER = 1.1      # segundos sem fala nova = a frase terminou
    DESLIGA_SOZINHO = 15 * 60      # 15 min sem falar nada encerra o ditado

    def __init__(self):
        self._trava = threading.RLock()
        self.ativo = False
        self.janela: JanelaBlocoDeNotas | None = None
        self.arquivo: Path | None = None
        self._pendente = ""
        self._timer: threading.Timer | None = None
        self._segmentos: list[tuple[str, int]] = []    # (texto, quantos caracteres entraram)
        self._texto = ""                              # tudo o que foi ditado (cópia do arquivo)
        self._ultimo = 0.0
        self._inicio = 0.0
        self._vigia: threading.Thread | None = None
        self.so_arquivo = False
        self._aberto_no_editor = False    # (fora do Windows) o arquivo já foi aberto
        self._liberar_ate = 0.0           # o NEXUS pode falar "pode falar" logo ao ligar
        self._parado_em = 0.0             # quando o ditado terminou (evita aviso duplicado)
        self._espaco_no_inicio = False    # a transcrição marca palavras novas com espaço
        # Ligados pelo assistente: avisar o Gemini e escrever na conversa
        self.avisar_modelo: Callable[[str], None] | None = None
        self.log: Callable[[str], None] | None = None
        self.ao_mudar: list[Callable[[bool], None]] = []

    # ── ligar / desligar ────────────────────────────────────────────────────

    def iniciar(self, titulo: str = "", origem: str = "voz") -> tuple[bool, str]:
        with self._trava:
            if self.ativo:
                return True, "O ditado já está ligado: pode falar."
            pasta = pasta_ditados()
            nome = nome_seguro(titulo) if titulo else f"ditado {datetime.now():%Y-%m-%d %H-%M}"
            arquivo = pasta / f"{nome}.txt"
            n = 2
            while arquivo.exists():
                arquivo = pasta / f"{nome} ({n}).txt"
                n += 1
            arquivo.write_text("", encoding="utf-8")
            self.arquivo = arquivo
            self._texto, self._pendente, self._segmentos = "", "", []
            self._espaco_no_inicio = False
            self._aberto_no_editor = False
            self.janela = None
            self.so_arquivo = True
            try:
                self.janela = JanelaBlocoDeNotas.abrir(arquivo)
                self.so_arquivo = self.janela is None
            except Exception as e:
                print(f"[Ditado] não consegui controlar o Bloco de Notas: {e}")
                self.janela = None
                self.so_arquivo = True
            if self.so_arquivo and not NO_WINDOWS:
                try:
                    abrir_no_editor(arquivo)
                    self._aberto_no_editor = True
                except Exception:
                    pass
            self.ativo = True
            self._inicio = self._ultimo = time.time()
            # Ligado por voz, o NEXUS ainda diz "pode falar" (até o fim desse turno)
            self._liberar_ate = time.monotonic() + 6.0 if origem == "voz" else 0.0
            self._vigia = threading.Thread(target=self._vigiar, daemon=True, name="ditado-vigia")
            self._vigia.start()
        self._isa("sistema", "Ditado ligado", f"escrevendo em {arquivo.name}")
        self._avisar_tela(True)
        if origem != "voz" and self.avisar_modelo:
            self.avisar_modelo(INSTRUCAO_LIGADO)
        onde = ("no Bloco de Notas" if not self.so_arquivo else "no arquivo")
        return True, (f"Ditado ligado — escrevendo {onde} ({arquivo.name}). "
                      f"Diga 'parar ditado' para terminar.")

    def parar(self, origem: str = "voz") -> tuple[bool, str]:
        with self._trava:
            if not self.ativo:
                if time.monotonic() - self._parado_em < 20:
                    return True, "O ditado já foi encerrado agora há pouco."
                return False, "O ditado não estava ligado."
            self._escrever_pendente()
            self.ativo = False
            self._liberar_ate = 0.0
            self._parado_em = time.monotonic()
            if self._timer:
                self._timer.cancel()
            palavras = len(self._texto.split())
            arquivo = self.arquivo
            so_arquivo = self.so_arquivo
        if so_arquivo and arquivo is not None and not self._aberto_no_editor:
            try:
                abrir_no_editor(arquivo)
            except Exception:
                pass
        msg = (f"Ditado terminado: {palavras} palavra(s). Uma cópia ficou salva em "
               f"{arquivo}." if arquivo else "Ditado terminado.")
        self._isa("sistema", "Ditado terminado", f"{palavras} palavra(s) — {arquivo.name if arquivo else ''}")
        self._avisar_tela(False)
        if origem != "ferramenta" and self.avisar_modelo:
            self.avisar_modelo(
                f"[DITADO TERMINADO] O modo ditado acabou ({palavras} palavras escritas no "
                f"Bloco de Notas). Volte ao normal: diga em UMA frase curta que terminou e "
                f"que o texto está salvo. Não chame ferramentas.")
        return True, msg

    # ── texto que chega ─────────────────────────────────────────────────────

    def pode_falar(self) -> bool:
        """True logo depois de ligar por voz: o NEXUS confirma ("pode falar")."""
        return self.ativo and time.monotonic() < self._liberar_ate

    def fim_da_confirmacao(self) -> None:
        self._liberar_ate = 0.0

    def recem_parado(self, segundos: float = 20.0) -> bool:
        return not self.ativo and time.monotonic() - self._parado_em < segundos

    def receber_trecho(self, trecho: str) -> None:
        """Pedaços da transcrição da voz, conforme chegam (do jeito que vieram:
        a transcrição pode marcar palavra nova com um espaço no começo e
        partir uma palavra em dois pedaços)."""
        bruto = re.sub(r"<ctrl\d+>|[\x00-\x08\x0b-\x1f]", "", trecho or "", flags=re.I)
        limpo = bruto.strip()
        if not limpo or not self.ativo:
            return
        with self._trava:
            if bruto[:1].isspace():
                self._espaco_no_inicio = True
            if not self._pendente:
                junto = limpo
            elif bruto[:1].isspace() or self._pendente.endswith((" ", "\n")):
                junto = f"{self._pendente.rstrip(' ')} {limpo}"
            elif limpo[:1] in ".,;:!?…)”":
                junto = self._pendente + limpo
            elif self._espaco_no_inicio:
                junto = self._pendente + limpo          # pedaço da mesma palavra
            else:
                junto = f"{self._pendente} {limpo}"
            self._pendente = junto.strip()
            self._ultimo = time.time()
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(self.PAUSA_PARA_ESCREVER, self._escrever_pendente)
            self._timer.daemon = True
            self._timer.start()

    def finalizar_turno(self) -> None:
        """O Gemini fechou o turno: o que estava pendente entra agora."""
        if self.ativo:
            self._escrever_pendente()

    def frase(self, texto: str) -> str:
        """Uma frase completa (ex.: digitada na caixa de comando)."""
        with self._trava:
            self._pendente = f"{self._pendente} {texto}".strip()
        return self._escrever_pendente()

    def _escrever_pendente(self) -> str:
        with self._trava:
            frase = self._pendente.strip()
            self._pendente = ""
            if not frase or not self.ativo:
                return ""
            sem_tudo = _sem_acento(frase)
            sem = sem_tudo.strip(" .,!?")

            # parar (o que veio antes do comando ainda entra)
            m = _PARAR.search(sem_tudo)
            if m:
                base = frase if len(sem_tudo) == len(frase) else sem_tudo
                antes = base[: m.start()].strip(" ,.")
                if antes and not _SO_CHAMADO.match(_sem_acento(antes).strip(" ,.!?")):
                    self._gravar(antes)
                threading.Thread(target=self.parar, daemon=True).start()
                return "parar"

            # desfazer
            if _DESFAZER.match(sem):
                self._desfazer()
                return "desfazer"

            self._gravar(frase)
            return "escrito"

    def _formatar(self, frase: str) -> str:
        texto = _aplicar_comandos(frase)
        if not texto:
            return ""
        anterior = self._texto
        fim_de_frase = (not anterior.strip()) or anterior.rstrip(" ").endswith((".", "!", "?", "\n", "…"))
        if fim_de_frase and texto[:1].isalpha():
            texto = texto[:1].upper() + texto[1:]
        if (anterior and not anterior.endswith(("\n", " ", "(", "“"))
                and not texto.startswith(("\n",) + tuple(_COLA))):
            texto = " " + texto
        return texto

    def _gravar(self, frase: str) -> None:
        texto = self._formatar(frase)
        if not texto:
            return
        entrou = 0
        if self.janela is not None and not self.so_arquivo:
            try:
                antes = self.janela.tamanho()
                if self.janela.escrever(texto):
                    entrou = self.janela.tamanho() - antes
                else:
                    raise RuntimeError("a janela não aceitou o texto")
            except Exception as e:
                print(f"[Ditado] janela falhou ({e}) — seguindo só no arquivo")
                self.so_arquivo = True
                self._log("SYS: 📝 O Bloco de Notas parou de aceitar o texto (foi fechado?). "
                          "Sigo salvando no arquivo e abro ele quando o ditado terminar.")
        self._texto += texto
        self._segmentos.append((texto, entrou))
        self._salvar_arquivo()
        self._log(f"SYS: 📝 {texto.strip()}")
        self._isa("resultado", "Ditado: escrito", texto.strip()[:120])

    def _desfazer(self) -> None:
        if not self._segmentos:
            return
        texto, entrou = self._segmentos.pop()
        if entrou and self.janela is not None and not self.so_arquivo:
            try:
                self.janela.apagar_ultimos(entrou)
            except Exception:
                pass
        if self._texto.endswith(texto):
            self._texto = self._texto[: -len(texto)]
        self._salvar_arquivo()
        self._log(f"SYS: 📝 Apaguei: “{texto.strip()[:80]}”")
        self._isa("sistema", "Ditado: desfeito", texto.strip()[:120])

    # ── apoio ───────────────────────────────────────────────────────────────

    def _salvar_arquivo(self) -> None:
        if self.arquivo is None:
            return
        try:
            self.arquivo.write_text(self._texto, encoding="utf-8")
        except Exception as e:
            print(f"[Ditado] não consegui salvar o arquivo: {e}")

    def _vigiar(self) -> None:
        while self.ativo:
            time.sleep(5)
            if self.ativo and time.time() - self._ultimo > self.DESLIGA_SOZINHO:
                self._log("SYS: 📝 Ditado desligado depois de 15 minutos sem fala.")
                self.parar(origem="tempo")
                return

    def _log(self, texto: str) -> None:
        if self.log:
            try:
                self.log(texto)
            except Exception:
                pass

    def _isa(self, tipo: str, titulo: str, detalhe: str = "") -> None:
        try:
            from core import isa
            isa.registrar(tipo, titulo, detalhe, origem="ditado")
        except Exception:
            pass

    def _avisar_tela(self, ligado: bool) -> None:
        for fn in list(self.ao_mudar):
            try:
                fn(ligado)
            except Exception:
                pass

    def texto(self) -> str:
        return self._texto


INSTRUCAO_LIGADO = (
    "[DITADO LIGADO] O modo ditado do Bloco de Notas está ligado. A partir de agora, TUDO o "
    "que o usuário falar é texto para o documento, NÃO são pedidos para você: o NEXUS escreve "
    "sozinho no Bloco de Notas e percebe sozinho quando ele diz 'parar ditado'. Fique em "
    "SILÊNCIO total, não responda, não comente e não chame ferramentas. Única exceção: se ele "
    "pedir claramente para sair do ditado com outras palavras, chame notepad com "
    "action=stop_dictation. Só volte a falar quando receber [DITADO TERMINADO].")

# O que o Gemini recebe quando ELE ligou o ditado (pedido por voz)
INSTRUCAO_FERRAMENTA = (
    "Diga apenas 'Pode falar.' (ou equivalente curtíssimo no idioma do usuário) e depois "
    "fique em SILÊNCIO total. " + INSTRUCAO_LIGADO)


ditado = Ditado()
