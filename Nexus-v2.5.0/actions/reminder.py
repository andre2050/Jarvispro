import json
from core.pt_time import agora, hora_extensa
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_CNW: dict = (
    {"creationflags": subprocess.CREATE_NO_WINDOW}
    if platform.system() == "Windows" else {}
)

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _get_os() -> str:
    _sys = platform.system()
    if _sys == "Darwin":
        return "mac"
    if _sys == "Linux":
        return "linux"
    return "windows"


def _scripts_dir() -> Path:
    d = Path.home() / ".nexus" / "reminders"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sanitise(text: str, max_len: int = 200) -> str:
    return (
        text.replace("\\", "")
            .replace('"', "")
            .replace("'", "")
            .replace("\n", " ")
            .replace("\r", "")
            .strip()
    )[:max_len]

def _write_notify_script(task_name: str, message: str, os_name: str) -> Path:
    script_path = _scripts_dir() / f"{task_name}.py"
    msg_literal = json.dumps(message)  

    if os_name == "windows":
        notify_block = f"""
message = {msg_literal}
notified = False

try:
    from plyer import notification
    notification.notify(title="NEXUS Pro — Lembrete", message=message, timeout=15)
    notified = True
except Exception as e:
    erros.append(f"plyer: {{e!r}}")

if not notified:
    try:
        from win10toast import ToastNotifier
        ToastNotifier().show_toast("NEXUS Pro — Lembrete", message, duration=15, threaded=False)
        notified = True
    except Exception as e:
        erros.append(f"win10toast: {{e!r}}")

if not notified:
    try:
        import subprocess
        r = subprocess.run(["msg", "*", "/TIME:30", message], check=False)
        notified = r.returncode == 0
        if not notified:
            erros.append(f"msg: saiu com código {{r.returncode}}")
    except Exception as e:
        erros.append(f"msg: {{e!r}}")

try:
    import winsound
    for freq in [800, 1000, 1200]:
        winsound.Beep(freq, 180)
        import time; time.sleep(0.08)
except Exception:
    pass
"""

    elif os_name == "mac":
        notify_block = f"""
message = {msg_literal}
notified = False

try:
    from plyer import notification
    notification.notify(title="NEXUS Pro — Lembrete", message=message, timeout=15)
    notified = True
except Exception as e:
    erros.append(f"plyer: {{e!r}}")

if not notified:
    try:
        import subprocess
        script = 'display notification "{{}}" with title "NEXUS Pro — Lembrete"'.format(
            message.replace('"', '')
        )
        notified = subprocess.run(["osascript", "-e", script], check=False).returncode == 0
    except Exception as e:
        erros.append(f"osascript: {{e!r}}")
"""

    else:  # linux
        notify_block = f"""
message = {msg_literal}
notified = False

try:
    from plyer import notification
    notification.notify(title="NEXUS Pro — Lembrete", message=message, timeout=15)
    notified = True
except Exception as e:
    erros.append(f"plyer: {{e!r}}")

if not notified:
    try:
        import subprocess
        notified = subprocess.run(
            ["notify-send", "--urgency=normal", "--expire-time=15000",
             "NEXUS Pro — Lembrete", message],
            check=False
        ).returncode == 0
    except Exception as e:
        erros.append(f"notify-send: {{e!r}}")
"""

    # 2.4.1 — se nenhum aviso apareceu, o lembrete se perdia sem rastro. Agora fica
    # anotado em memory/falhas.log (mesmo formato do core/protecao.py).
    falhas_literal = json.dumps(str(_base_dir() / "memory" / "falhas.log"))
    script_body = f"""# Criado pelo lembrete do NEXUS Pro — não edite
import sys, os, pathlib
erros = []
{notify_block}
if not notified:
    try:
        import time
        with open({falhas_literal}, "a", encoding="utf-8") as _f:
            _f.write(f"\\n=== {{time.strftime('%d/%m/%Y %H:%M:%S')}} · lembrete não apareceu ===\\n"
                     f"{{message}}\\n" + "\\n".join(erros) + "\\n")
    except Exception:
        pass
# Self-delete after firing
try:
    pathlib.Path(__file__).unlink(missing_ok=True)
except Exception:
    pass
"""
    script_path.write_text(script_body, encoding="utf-8")
    script_path.chmod(0o600)   # owner read/write only
    return script_path

def _schedule_windows(target_dt: datetime, task_name: str,
                      script_path: Path, message: str) -> str:
    python_exe = Path(sys.executable)
    pythonw = python_exe.parent / "pythonw.exe"
    if pythonw.exists():
        python_exe = pythonw

    xml_path = _scripts_dir() / f"{task_name}.xml"
    xml_content = (
        '<?xml version="1.0" encoding="UTF-16"?>\n'
        '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
        '  <RegistrationInfo><Description>NEXUS Pro — Lembrete</Description></RegistrationInfo>\n'
        '  <Triggers><TimeTrigger>\n'
        f'    <StartBoundary>{target_dt.strftime("%Y-%m-%dT%H:%M:%S")}</StartBoundary>\n'
        '    <Enabled>true</Enabled>\n'
        '  </TimeTrigger></Triggers>\n'
        '  <Actions><Exec>\n'
        f'    <Command>{python_exe}</Command>\n'
        f'    <Arguments>"{script_path}"</Arguments>\n'
        '  </Exec></Actions>\n'
        '  <Settings>\n'
        '    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n'
        '    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n'
        '    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n'
        '    <StartWhenAvailable>true</StartWhenAvailable>\n'
        '    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>\n'
        '    <Enabled>true</Enabled>\n'
        '  </Settings>\n'
        '  <Principals><Principal>\n'
        '    <LogonType>InteractiveToken</LogonType>\n'
        '    <RunLevel>LeastPrivilege</RunLevel>\n'
        '  </Principal></Principals>\n'
        '</Task>'
    )

    xml_path.write_text(xml_content, encoding="utf-16")

    result = subprocess.run(
        ["schtasks", "/Create", "/TN", task_name, "/XML", str(xml_path), "/F"],
        capture_output=True, text=True, **_CNW,
    )

    try:
        xml_path.unlink(missing_ok=True)
    except Exception:
        pass

    if result.returncode != 0:
        script_path.unlink(missing_ok=True)
        err = (result.stderr or result.stdout).strip()
        print(f"[Reminder] ❌ schtasks: {err}")
        return ""  

    return task_name


def _schedule_mac(target_dt: datetime, task_name: str,
                  script_path: Path) -> str:
    agents_dir = Path.home() / "Library" / "LaunchAgents"
    agents_dir.mkdir(parents=True, exist_ok=True)

    label     = f"com.nexus.reminder.{task_name}"
    plist_path = agents_dir / f"{label}.plist"

    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>             <string>{label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{sys.executable}</string>
    <string>{script_path}</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Year</key>   <integer>{target_dt.year}</integer>
    <key>Month</key>  <integer>{target_dt.month}</integer>
    <key>Day</key>    <integer>{target_dt.day}</integer>
    <key>Hour</key>   <integer>{target_dt.hour}</integer>
    <key>Minute</key> <integer>{target_dt.minute}</integer>
  </dict>
  <key>RunAtLoad</key>         <false/>
  <key>StandardOutPath</key>   <string>/dev/null</string>
  <key>StandardErrorPath</key> <string>/dev/null</string>
</dict>
</plist>
"""
    plist_path.write_text(plist_content, encoding="utf-8")
    plist_path.chmod(0o644)

    result = subprocess.run(
        ["launchctl", "load", str(plist_path)],
        capture_output=True, text=True,
    )

    if result.returncode != 0:
        plist_path.unlink(missing_ok=True)
        script_path.unlink(missing_ok=True)
        print(f"[Reminder] ❌ launchctl: {result.stderr.strip()}")
        return ""

    return label


def _schedule_linux(target_dt: datetime, task_name: str,
                    script_path: Path) -> str:

    if shutil.which("systemd-run"):
        on_calendar = target_dt.strftime("%Y-%m-%d %H:%M:00")
        result = subprocess.run(
            [
                "systemd-run",
                "--user",
                f"--on-calendar={on_calendar}",
                f"--unit={task_name}",
                "--",
                sys.executable, str(script_path),
            ],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return task_name
        print(f"[Reminder] ⚠️ systemd-run failed: {result.stderr.strip()}, trying 'at'")

    if shutil.which("at"):
        at_time = target_dt.strftime("%H:%M %Y-%m-%d")
        cmd_str = f"{sys.executable} {script_path}\n"
        result  = subprocess.run(
            ["at", at_time],
            input=cmd_str, capture_output=True, text=True,
        )
        if result.returncode == 0:
            return task_name
        print(f"[Reminder] ❌ at: {result.stderr.strip()}")
        return ""

    print("[Reminder] ❌ Neither systemd-run nor at found on this Linux system.")
    return ""

# ── Registro dos lembretes (1.2) ──────────────────────────────────────────────
# O agendador do sistema (Agendador de Tarefas, launchd, systemd) dispara o
# aviso mesmo com o NEXUS fechado, mas não sabe listar "os lembretes do NEXUS".
# Por isso cada lembrete criado também é anotado em memory/reminders.json — é
# dali que a central de Notas e Lembretes e o comando de voz leem e cancelam.

def _registry_file() -> Path:
    return _base_dir() / "memory" / "reminders.json"


def _registry_load() -> list:
    try:
        data = json.loads(_registry_file().read_text(encoding="utf-8"))
        return [d for d in data if isinstance(d, dict) and d.get("id") and d.get("quando")]
    except Exception:
        return []


def _registry_save(items: list) -> None:
    f = _registry_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    items = sorted(items, key=lambda d: d.get("quando", ""))[-300:]
    f.write_text(json.dumps(items, indent=1, ensure_ascii=False), encoding="utf-8")


def listar() -> list[dict]:
    """Todos os lembretes registrados, do mais próximo ao mais distante.

    Cada item: {"id", "quando" (AAAA-MM-DDTHH:MM), "mensagem", "pendente": bool}.
    """
    agora_ = agora()   # já vem sem fuso (horário de Brasília)
    out = []
    for d in _registry_load():
        try:
            quando = datetime.fromisoformat(d["quando"])
        except ValueError:
            continue
        out.append({"id": d["id"], "quando": d["quando"], "mensagem": d.get("mensagem", ""),
                    "pendente": quando > agora_})
    return out


def agendar(target_dt: datetime, message: str) -> tuple[bool, str, str]:
    """Agenda um lembrete no sistema. Devolve (deu_certo, mensagem, id)."""
    agora_ = agora()   # já vem sem fuso (horário de Brasília)
    target_dt = target_dt.replace(second=0, microsecond=0, tzinfo=None)
    if target_dt <= agora_:
        return False, "Esse horário já passou — escolha um horário no futuro.", ""

    os_name   = _get_os()
    safe_msg  = _sanitise(message or "Lembrete") or "Lembrete"
    task_name = f"NEXUSReminder_{target_dt.strftime('%Y%m%d_%H%M%S')}"
    # dois lembretes no mesmo minuto não podem ter o mesmo nome de tarefa
    existentes = {d["id"] for d in _registry_load()}
    n = 1
    base = task_name
    while task_name in existentes:
        n += 1
        task_name = f"{base}_{n}"

    try:
        script_path = _write_notify_script(task_name, safe_msg, os_name)
    except Exception as e:
        return False, f"Não consegui preparar o lembrete: {e}", ""

    try:
        if os_name == "windows":
            job_id = _schedule_windows(target_dt, task_name, script_path, safe_msg)
        elif os_name == "mac":
            job_id = _schedule_mac(target_dt, task_name, script_path)
        else:
            job_id = _schedule_linux(target_dt, task_name, script_path)
    except Exception as e:
        script_path.unlink(missing_ok=True)
        print(f"[Reminder] ❌ Scheduling exception: {e}")
        return False, "Algo deu errado ao agendar o lembrete.", ""

    if not job_id:
        return False, "O agendador do sistema não aceitou o lembrete.", ""

    items = _registry_load()
    items.append({"id": task_name, "quando": target_dt.strftime("%Y-%m-%dT%H:%M"),
                  "mensagem": safe_msg, "os": os_name,
                  "criado": agora_.strftime("%Y-%m-%dT%H:%M:%S")})
    try:
        _registry_save(items)
    except Exception as e:
        print(f"[Reminder] ⚠️ não consegui registrar o lembrete: {e}")
    return True, f"Lembrete marcado para {hora_extensa(target_dt)}.", task_name


def cancelar(task_id: str) -> tuple[bool, str]:
    """Cancela um lembrete: tira do agendador do sistema e do registro."""
    items = _registry_load()
    item = next((d for d in items if d["id"] == task_id), None)
    if item is None:
        return False, "Não encontrei esse lembrete."
    os_name = item.get("os") or _get_os()
    try:
        if os_name == "windows":
            subprocess.run(["schtasks", "/Delete", "/TN", task_id, "/F"],
                           capture_output=True, text=True, **_CNW)
        elif os_name == "mac":
            plist = Path.home() / "Library" / "LaunchAgents" / f"com.nexus.reminder.{task_id}.plist"
            subprocess.run(["launchctl", "unload", str(plist)], capture_output=True, text=True)
            plist.unlink(missing_ok=True)
        else:
            if shutil.which("systemctl"):
                subprocess.run(["systemctl", "--user", "stop", f"{task_id}.timer"],
                               capture_output=True, text=True)
    except Exception as e:
        print(f"[Reminder] ⚠️ cancelar no sistema: {e}")
    # Sem o script, mesmo uma tarefa que sobrar no sistema não mostra nada.
    try:
        (_scripts_dir() / f"{task_id}.py").unlink(missing_ok=True)
    except Exception:
        pass
    _registry_save([d for d in items if d["id"] != task_id])
    return True, f"Lembrete cancelado: {item.get('mensagem', '')}"


def limpar_concluidos() -> int:
    """Tira do registro os lembretes que já passaram. Devolve quantos saíram."""
    pendentes = {d["id"] for d in listar() if d["pendente"]}
    items = _registry_load()
    ficam = [d for d in items if d["id"] in pendentes]
    _registry_save(ficam)
    return len(items) - len(ficam)


def _quando(iso: str) -> str:
    try:
        from core.pt_time import hora_extensa
        return hora_extensa(datetime.fromisoformat(iso))
    except Exception:
        return iso.replace("T", " ")


def _definir(parameters: dict, player) -> str:
    date_str = str(parameters.get("date") or "").strip()
    time_str = str(parameters.get("time") or "").strip()
    message = str(parameters.get("message") or "Lembrete").strip()
    if not date_str or not time_str:
        return "Preciso da data e da hora para marcar o lembrete."
    try:
        target_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except ValueError:
        return "Não entendi a data ou a hora. Use AAAA-MM-DD e HH:MM."
    ok, msg, _task = agendar(target_dt, message)
    if not ok:
        return msg
    if player:
        player.write_log(f"SYS: ⏰ Lembrete marcado — {date_str} {time_str} — {_sanitise(message)[:40]}")
    return msg


def _listar(pendentes: list) -> str:
    if not pendentes:
        return "Não há lembretes marcados."
    linhas = [f"{i}. {d['mensagem']} — {_quando(d['quando'])}" for i, d in enumerate(pendentes, 1)]
    return f"{len(pendentes)} lembrete(s) marcado(s): " + " | ".join(linhas)


def _cancelar(pendentes: list, alvo: str, player) -> str:
    if not pendentes:
        return "Não há lembretes para cancelar."
    escolhido = None
    if alvo.isdigit() and 1 <= int(alvo) <= len(pendentes):
        escolhido = pendentes[int(alvo) - 1]
    elif alvo:
        achados = [d for d in pendentes if alvo.lower() in d["mensagem"].lower()]
        if len(achados) == 1:
            escolhido = achados[0]
        elif len(achados) > 1:
            return ("Mais de um lembrete combina com isso: "
                    + " | ".join(f"{d['mensagem']} ({_quando(d['quando'])})" for d in achados)
                    + ". Diga o número.")
    if escolhido is None:
        return "Não encontrei esse lembrete. Peça a lista primeiro e diga o número."
    ok, msg = cancelar(escolhido["id"])
    if ok and player:
        player.write_log(f"SYS: ⏰ {msg}")
    return msg


def reminder(parameters: dict, response=None, player=None, session_memory=None) -> str:
    """Um só lugar para lembretes: set (padrão) | list | cancel | clear_done."""
    acao = str(parameters.get("action") or "set").strip().lower()
    if acao in ("set", "add", "create", ""):
        return _definir(parameters, player)
    pendentes = [d for d in listar() if d["pendente"]]
    if acao == "list":
        return _listar(pendentes)
    if acao == "cancel":
        return _cancelar(pendentes, str(parameters.get("target") or "").strip(), player)
    if acao == "clear_done":
        return f"Tirei {limpar_concluidos()} lembrete(s) que já passaram da lista."
    return "Ação desconhecida. Use set, list, cancel ou clear_done."


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "reminder",
    "description": ("Timed reminders. action=set (default) schedules one with date, time and message; "
                    "action=list reads the pending ones; action=cancel with target = the list number "
                    "or words from the text; action=clear_done removes reminders that already fired."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "set | list | cancel | clear_done (default set)"},
            "date": {"type": "STRING", "description": "For set: date in YYYY-MM-DD"},
            "time": {"type": "STRING", "description": "For set: time in HH:MM (24h)"},
            "message": {"type": "STRING", "description": "For set: reminder text"},
            "target": {"type": "STRING", "description": "For cancel: list number or part of the text"},
        },
        "required": [],
    },
    "handler": reminder,
}
