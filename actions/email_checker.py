"""Verificar email — "Nexus, verifica meu email".

Quando o usuário pede para checar o email, abre uma janela no HUD pedindo
EMAIL e SENHA, entra na caixa de entrada por IMAP (SSL) e devolve ao modelo
quantos emails não lidos existem, com remetente e assunto dos mais recentes.

Segurança:
  • A senha é digitada numa janela, NUNCA falada nem passada pelo modelo —
    ela não é parâmetro da ferramenta, então nunca vai para o Gemini.
  • A senha não é salva em lugar nenhum. Só o endereço de email pode ser
    lembrado (opcional) para já vir preenchido na próxima vez.
  • Os emails são lidos com BODY.PEEK, então NÃO são marcados como lidos.

Gmail / Outlook: use uma "senha de app" (Conta Google → Segurança →
Verificação em duas etapas → Senhas de app). A senha normal é recusada.
"""

from __future__ import annotations

import email
import imaplib
import json
import socket
import threading
from email.header import decode_header
from email.utils import parseaddr
from pathlib import Path
from core.protecao import engolida as _engolida

try:
    from memory.config_manager import CONFIG_DIR
except Exception:
    CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

_ACCOUNT_FILE = CONFIG_DIR / "email_account.json"   # só o endereço, nunca a senha
_TIMEOUT      = 20       # segundos para conectar no servidor
_MAX_LIST     = 10

_SERVERS = {
    "gmail.com":       "imap.gmail.com",
    "googlemail.com":  "imap.gmail.com",
    "outlook.com":     "outlook.office365.com",
    "outlook.com.br":  "outlook.office365.com",
    "hotmail.com":     "outlook.office365.com",
    "hotmail.com.br":  "outlook.office365.com",
    "live.com":        "outlook.office365.com",
    "msn.com":         "outlook.office365.com",
    "yahoo.com":       "imap.mail.yahoo.com",
    "yahoo.com.br":    "imap.mail.yahoo.com",
    "icloud.com":      "imap.mail.me.com",
    "me.com":          "imap.mail.me.com",
    "uol.com.br":      "imap.uol.com.br",
    "bol.com.br":      "imap.bol.com.br",
    "terra.com.br":    "imap.terra.com.br",
    "zoho.com":        "imap.zoho.com",
    "proton.me":       "127.0.0.1",   # só via Proton Bridge
}


# ── Configurações (sem senha) ─────────────────────────────────────────────────
# config/email_account.json guarda: email lembrado, servidor, quantos emails
# listar e se lista só os não lidos. A senha NUNCA entra neste arquivo.

DEFAULTS = {"email": "", "server": "", "max_results": 5, "unread_only": True}


def load_settings() -> dict:
    out = dict(DEFAULTS)
    try:
        data = json.loads(_ACCOUNT_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            out.update({k: data[k] for k in DEFAULTS if k in data})
    except Exception:
        _engolida("actions/email_checker.py:73")
    return out


def save_settings(**changes) -> dict:
    data = load_settings()
    data.update({k: v for k, v in changes.items() if k in DEFAULTS})
    data.pop("password", None)
    try:
        _ACCOUNT_FILE.parent.mkdir(parents=True, exist_ok=True)
        _ACCOUNT_FILE.write_text(json.dumps(data, indent=1, ensure_ascii=False),
                                 encoding="utf-8")
    except Exception as e:
        print(f"[Email] ⚠️ não consegui salvar as configurações: {e}")
    return data


def _load_account() -> dict:
    return load_settings()


def _save_account(user: str, server: str) -> None:
    save_settings(email=user, server=server)


def _forget_account() -> None:
    save_settings(email="", server="")


def _guess_server(user: str) -> str:
    domain = user.rsplit("@", 1)[-1].lower().strip()
    return _SERVERS.get(domain) or (f"imap.{domain}" if domain else "")


# ── Janela de login (roda na thread do Qt) ────────────────────────────────────
# O handler roda numa thread do executor, e janelas Qt só podem ser criadas na
# thread principal. Um QObject movido para a thread do app recebe o pedido por
# BlockingQueuedConnection: a thread do handler espera até a janela fechar.

_bridge = None
_bridge_lock = threading.Lock()


def _ask_credentials(player, prefill_user: str, prefill_server: str) -> dict | None:
    """Mostra a janela e devolve {user, password, server, remember} ou None."""
    try:
        from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal, pyqtSlot
        from PyQt6.QtWidgets import QApplication
    except Exception:
        return None

    app = QApplication.instance()
    if app is None:
        return None

    global _bridge
    with _bridge_lock:
        if _bridge is None:
            class _Bridge(QObject):
                ask = pyqtSignal(object)

                def __init__(self):
                    super().__init__()
                    self.ask.connect(self._on_ask,
                                     Qt.ConnectionType.BlockingQueuedConnection)

                @pyqtSlot(object)
                def _on_ask(self, box: dict):
                    try:
                        box["result"] = _run_dialog(box["parent"], box["user"], box["server"])
                    except Exception as e:
                        print(f"[Email] ⚠️ falha na janela de login: {e}")
                        box["result"] = None

            b = _Bridge()
            b.moveToThread(app.thread())
            _bridge = b

    parent = getattr(player, "_win", None)
    box = {"parent": parent, "user": prefill_user, "server": prefill_server, "result": None}

    if QThread.currentThread() is app.thread():
        # Chamado já na thread do Qt (não acontece no fluxo normal): roda direto.
        box["result"] = _run_dialog(parent, prefill_user, prefill_server)
    else:
        _bridge.ask.emit(box)       # bloqueia até a janela fechar
    return box["result"]


def _run_dialog(parent, prefill_user: str, prefill_server: str) -> dict | None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QFont
    from PyQt6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel,
                                 QLineEdit, QPushButton, QVBoxLayout)

    # Cores e fonte do HUD, com valores padrão se o ui.py mudar.
    acc, text, med, border, bg, font = ("#ff9d5c", "#d9e2ec", "#93a6b8",
                                        "#2b3644", "#0a0c10", "Segoe UI")
    try:
        import ui as _ui
        acc, text, med = _ui.C.ACC, _ui.C.TEXT, _ui.C.TEXT_MED
        border, bg, font = _ui.C.BORDER_B, _ui.C.BG, _ui.FONT_MAIN
    except Exception:
        _engolida("actions/email_checker.py:176")

    dlg = QDialog(parent)
    dlg.setWindowTitle("Verificar email")
    dlg.setModal(True)
    dlg.setFixedWidth(420)
    dlg.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    dlg.setStyleSheet(f"""
        QDialog {{ background: {bg}; border: 1px solid {acc}; }}
        QLabel  {{ color: {text}; background: transparent; }}
        QLineEdit {{ background: rgba(255,255,255,8); color: {text};
                     border: 1px solid {border}; border-radius: 3px; padding: 6px; }}
        QLineEdit:focus {{ border-color: {acc}; }}
        QCheckBox {{ color: {med}; background: transparent; }}
    """)

    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(20, 16, 20, 16)
    lay.setSpacing(8)

    hdr = QLabel("✉  VERIFICAR EMAIL")
    hdr.setFont(QFont(font, 11, QFont.Weight.Bold))
    hdr.setStyleSheet(f"color: {acc};")
    lay.addWidget(hdr)

    info = QLabel("Digite seu usuário e senha. A senha não é salva.\n"
                  "Gmail/Outlook: use uma senha de app.")
    info.setWordWrap(True)
    info.setFont(QFont(font, 8))
    info.setStyleSheet(f"color: {med};")
    lay.addWidget(info)

    def _field(label: str, value: str = "", password: bool = False) -> QLineEdit:
        lbl = QLabel(label)
        lbl.setFont(QFont(font, 9))
        lay.addWidget(lbl)
        edit = QLineEdit(value)
        edit.setFont(QFont(font, 10))
        if password:
            edit.setEchoMode(QLineEdit.EchoMode.Password)
        lay.addWidget(edit)
        return edit

    user_ed = _field("Usuário (email)", prefill_user)
    pass_ed = _field("Senha", password=True)
    srv_ed  = _field("Servidor IMAP", prefill_server or _guess_server(prefill_user))

    # Servidor acompanha o domínio digitado, até o usuário mexer nele à mão.
    srv_state = {"manual": bool(prefill_server)}
    srv_ed.textEdited.connect(lambda _t: srv_state.update(manual=True))
    user_ed.textChanged.connect(
        lambda t: None if srv_state["manual"] else srv_ed.setText(_guess_server(t)))

    show_pw = QCheckBox("Mostrar senha")
    show_pw.toggled.connect(lambda on: pass_ed.setEchoMode(
        QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
    lay.addWidget(show_pw)

    remember = QCheckBox("Lembrar meu email (a senha nunca é salva)")
    remember.setChecked(bool(prefill_user))
    lay.addWidget(remember)

    err = QLabel("")
    err.setStyleSheet("color: #ff6b6b;")
    err.setFont(QFont(font, 8))
    lay.addWidget(err)

    row = QHBoxLayout(); row.setSpacing(8)
    ok = QPushButton("▸  ENTRAR")
    cancel = QPushButton("CANCELAR")
    for b, color in ((ok, acc), (cancel, med)):
        b.setFixedHeight(32)
        b.setFont(QFont(font, 9, QFont.Weight.Bold if b is ok else QFont.Weight.Normal))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {color};
                border: 1px solid {color}; border-radius: 3px; }}
            QPushButton:hover {{ background: rgba(255,157,92,40); }}
        """)
        row.addWidget(b)
    lay.addLayout(row)

    def _accept():
        if "@" not in user_ed.text().strip():
            err.setText("Digite um email válido."); user_ed.setFocus(); return
        if not pass_ed.text():
            err.setText("Digite a senha."); pass_ed.setFocus(); return
        if not srv_ed.text().strip():
            err.setText("Digite o servidor IMAP."); srv_ed.setFocus(); return
        dlg.accept()

    ok.clicked.connect(_accept)
    cancel.clicked.connect(dlg.reject)
    pass_ed.returnPressed.connect(_accept)
    user_ed.returnPressed.connect(lambda: pass_ed.setFocus())
    ok.setDefault(True)

    (pass_ed if prefill_user else user_ed).setFocus()
    dlg.raise_(); dlg.activateWindow()

    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None

    result = {"user": user_ed.text().strip(), "password": pass_ed.text(),
              "server": srv_ed.text().strip(), "remember": remember.isChecked()}
    pass_ed.clear()
    return result


# ── IMAP ──────────────────────────────────────────────────────────────────────

def _decode(value) -> str:
    if not value:
        return ""
    out = []
    for part, enc in decode_header(value):
        if isinstance(part, bytes):
            try:
                out.append(part.decode(enc or "utf-8", errors="replace"))
            except LookupError:
                out.append(part.decode("utf-8", errors="replace"))
        else:
            out.append(part)
    return " ".join("".join(out).split())


def _sender(raw: str) -> str:
    name, addr = parseaddr(_decode(raw))
    return name or addr or "remetente desconhecido"


def _check(user: str, password: str, server: str, limit: int, unread_only: bool) -> tuple[bool, str, list]:
    """(ok, mensagem_de_erro, emails). Nunca levanta exceção.

    1.4.3 — uma nova tentativa quando o servidor demora (o "The read operation
    timed out" do Gmail costuma passar na segunda)."""
    ok, err, mails = _check_once(user, password, server, limit, unread_only)
    if not ok and ("timed out" in err.lower() or "timeout" in err.lower()):
        ok, err, mails = _check_once(user, password, server, limit, unread_only)
    return ok, err, mails


def _check_once(user: str, password: str, server: str, limit: int, unread_only: bool) -> tuple[bool, str, list]:
    host, _, port = server.partition(":")
    try:
        conn = imaplib.IMAP4_SSL(host, int(port) if port.isdigit() else 993, timeout=_TIMEOUT)
    except (socket.gaierror, OSError) as e:
        return False, f"Could not reach the email server '{server}' ({e}).", []

    try:
        try:
            conn.login(user, password)
        except imaplib.IMAP4.error:
            return False, ("Login failed: wrong username or password. For Gmail or Outlook "
                           "the user must use an app password, not the normal one."), []

        conn.select("INBOX", readonly=True)       # readonly: nada é marcado como lido
        status, data = conn.search(None, "UNSEEN" if unread_only else "ALL")
        ids = data[0].split() if status == "OK" and data and data[0] else []

        mails = []
        alvo = list(reversed(ids[-limit:]))       # mais recentes primeiro
        if alvo:
            # 1.4.3 — um único FETCH para todos (antes: uma ida e volta ao
            # servidor por e-mail, 5 vezes mais lento).
            conjunto = b",".join(alvo).decode()
            st, msg_data = conn.fetch(conjunto, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            por_id = {}
            if st == "OK" and msg_data:
                for item in msg_data:
                    if isinstance(item, tuple) and len(item) >= 2:
                        num = item[0].split()[0] if item[0] else b""
                        por_id[num] = item[1]
            for num in alvo:
                raw = por_id.get(num)
                if raw is None:
                    continue
                msg = email.message_from_bytes(raw)
                mails.append({"from": _sender(msg.get("From")),
                              "subject": _decode(msg.get("Subject")) or "(sem assunto)",
                              "date": _decode(msg.get("Date"))})
        mails.append({"_total": len(ids)})
        return True, "", mails
    except Exception as e:
        return False, f"Error while reading the inbox: {e}", []
    finally:
        try:
            conn.logout()
        except Exception:
            _engolida("actions/email_checker.py:365")


# ── Handler ───────────────────────────────────────────────────────────────────

def _qt_available() -> bool:
    try:
        from PyQt6.QtWidgets import QApplication
        return QApplication.instance() is not None
    except Exception:
        return False


def check_now(user: str, password: str, server: str = "",
              limit: int | None = None, unread_only: bool | None = None) -> tuple[bool, str]:
    """Usado pelo painel de Configurações > EMAIL. Devolve (ok, texto em português)."""
    cfg = load_settings()
    server = (server or "").strip() or _guess_server(user)
    limit = max(1, min(_MAX_LIST, int(limit or cfg["max_results"] or 5)))
    unread_only = cfg["unread_only"] if unread_only is None else unread_only
    ok, error, mails = _check(user.strip(), password, server, limit, unread_only)
    if not ok:
        if error.startswith("Login failed"):
            return False, ("Usuário ou senha incorretos. No Gmail/Outlook use uma "
                           "SENHA DE APP, não a senha normal da conta.")
        if error.startswith("Could not reach"):
            return False, f"Não consegui conectar no servidor '{server}'. Confira o servidor e a internet."
        return False, f"Erro ao ler a caixa de entrada: {error}"
    total = mails.pop()["_total"]
    kind = "não lidos" if unread_only else "na caixa"
    if total == 0:
        return True, f"Conexão OK. Nenhum email {kind}."
    lines = "\n".join(f"• {m['from']} — {m['subject']}" for m in mails)
    return True, f"Conexão OK. {total} email(s) {kind}:\n{lines}"


def _log(msg: str, player) -> None:
    print(f"[Email] {msg}")
    if player is not None and hasattr(player, "write_log"):
        try:
            player.write_log(f"SYS: Email — {msg}")
        except Exception:
            _engolida("actions/email_checker.py:407")


def email_checker(parameters: dict, player=None) -> str:
    action = str(parameters.get("action") or "check").strip().lower()

    if action == "forget":
        _forget_account()
        _log("saved address forgotten", player)
        return "Done: the saved email address was forgotten. Next time the user will type it again."

    saved = load_settings()
    try:
        limit = max(1, min(_MAX_LIST, int(parameters.get("max_results") or saved["max_results"] or 5)))
    except (TypeError, ValueError):
        limit = 5
    unread_only = str(parameters.get("unread_only", saved["unread_only"])).lower() \
        not in ("false", "0", "no")

    creds = _ask_credentials(player, saved.get("email", ""), saved.get("server", ""))
    if creds is None and not _qt_available():
        return ("The login window could not be opened (no interface available). "
                "Ask the user to use Settings > EMAIL > 'Testar / verificar agora'.")
    if creds is None:
        _log("cancelled", player)
        return "The user cancelled the email login window. Nothing was checked."

    _log(f"checking {creds['user']}…", player)
    ok, error, mails = _check(creds["user"], creds["password"], creds["server"],
                              limit, unread_only)
    creds["password"] = ""          # não guarda a senha depois de usar

    if not ok:
        _log(error, player)
        return error

    if creds["remember"]:
        _save_account(creds["user"], creds["server"])
    else:
        _forget_account()

    total = mails.pop()["_total"]
    kind = "unread" if unread_only else "total"
    if total == 0:
        _log("no new emails", player)
        return f"The inbox of {creds['user']} has no {kind} emails."

    lines = [f"{i}. From {m['from']} — {m['subject']}" for i, m in enumerate(mails, 1)]
    if player is not None and hasattr(player, "show_content"):
        try:
            player.show_content(f"EMAIL — {total} {'NÃO LIDOS' if unread_only else 'NA CAIXA'}",
                                "\n".join(f"{i}. {m['from']}\n   {m['subject']}"
                                          for i, m in enumerate(mails, 1)))
        except Exception:
            _engolida("actions/email_checker.py:461")

    _log(f"{total} {kind}", player)
    return (f"{creds['user']} has {total} {kind} email(s). The {len(mails)} most recent: "
            + " ".join(lines)
            + " Tell the user briefly in their own language; do not read email addresses aloud.")


TOOL = {
    "name": "email_checker",
    "description": (
        "Checks the user's email inbox (Gmail, Outlook, Hotmail, Yahoo, iCloud, UOL, any IMAP). "
        "Use when the user asks to check/verify/read their email or asks if they have new emails "
        "(e.g. 'verifica meu email', 'tenho email novo?'). A login window opens on screen where the "
        "user types username and password — NEVER ask for the password by voice and never pass it "
        "as a parameter. Returns the unread count plus sender and subject of the most recent ones. "
        "action='forget' erases the remembered email address."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "'check' (default) to check the inbox, 'forget' to erase the saved address.",
            },
            "max_results": {
                "type": "INTEGER",
                "description": "How many recent emails to list (1-10, default 5).",
            },
            "unread_only": {
                "type": "BOOLEAN",
                "description": "True (default) lists only unread emails; false lists the latest emails.",
            },
        },
    },
    "handler": email_checker,
}
