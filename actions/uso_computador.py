"""Computer-use: "abre o bloco de notas e escreve …", "preenche esse formulário". Vê a tela, mostra cada passo, pede CONFIRMAR
antes de começar e a cada passo delicado; para sozinho em janelas de banco/senha. Detalhes e limites: core/computer_use.py."""
import threading

from core import computer_use as C
from core import confirm as _confirm
from core.protecao import engolida as _engolida

_atual: C.Uso | None = None
_ultimo = ""
_trava = threading.Lock()
_mostrar_cb = None          # a interface pode registrar uma função (passo, n) para desenhar o retângulo na tela


def set_mostrar(fn) -> None:
    global _mostrar_cb
    _mostrar_cb = fn


def _perguntar(texto: str, espera: float = 45.0) -> bool:
    ok = threading.Event()
    r = _confirm.request(key="uso_computador_passo", title="Passo delicado no computador", detail=texto,
                         run=lambda: (ok.set() or "[done] aprovado"))
    if r.startswith("I cannot"):
        return False
    return ok.wait(espera)


def _rodar(objetivo: str) -> None:
    global _atual, _ultimo
    u = C.Uso(objetivo, C.ver_tela_real, C.decidir_real, C.agir_real,
              mostrar=lambda p, n: _mostrar_cb and _mostrar_cb(p, n), perguntar=_perguntar)
    _atual = u
    try:
        _ultimo = u.rodar()
    except Exception as e:
        _ultimo = f"Falhou: {e}"
    finally:
        _atual = None
    try:
        from actions import missao
        missao._avisar(f"Uso do computador: {_ultimo}")
    except Exception:
        _engolida("actions/uso_computador.py:43")


def uso_computador(parameters: dict, **_kw) -> str:
    acao = str(parameters.get("action") or "start").strip().lower()
    if acao in ("stop", "parar"):
        if _atual:
            _atual.parar()
            return "[done] Parando."
        return "Não há nada rodando."
    if acao == "status":
        return ("Rodando: " + "; ".join(_atual.historico[-3:])) if _atual else (_ultimo or "Nada rodando.")
    goal = str(parameters.get("goal") or "").strip()
    if len(goal) < 5:
        return "[failed] Diga o que devo fazer na tela."
    try:
        import pyautogui  # noqa: F401
    except ImportError:
        return "[failed] Falta o pacote pyautogui no PC."
    if _atual:
        return "[failed] Já estou usando o computador; diga 'parar' primeiro."
    if _confirm.pending_title():
        return "Já há uma confirmação esperando na tela; resolva ela antes."

    def _go():
        with _trava:
            threading.Thread(target=_rodar, args=(goal,), daemon=True, name="uso-computador").start()
        return "[done] Começando. Cada passo aparece na tela; diga 'parar' ou leve o mouse ao canto para interromper."
    return _confirm.request(key="uso_computador", title="Deixar o NEXUS usar o mouse e o teclado?",
                            detail=f"Objetivo: {goal[:200]}\nMáx. {C.MAX_PASSOS} passos / {C.MAX_SEGUNDOS // 60} min. Para sozinho em janelas de banco/senha.",
                            run=_go)


TOOL = {
    "name": "computer_use",
    "description": ("Operates the PC by LOOKING at the screen and clicking/typing step by step (visible steps, on-screen CONFIRM "
                    "first, approval for delicate steps, stops on bank/password windows). Use only when no dedicated tool does "
                    "the job. action=start (goal) | stop | status."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["start", "stop", "status"]}, "goal": {"type": "STRING"}}, "required": ["action"]},
    "handler": uso_computador,
}
