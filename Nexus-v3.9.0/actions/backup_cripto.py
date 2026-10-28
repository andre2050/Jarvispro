"""Backup criptografado por voz: "configura o backup na pasta do OneDrive", "faz backup agora", "restaura o último backup"."""
from __future__ import annotations


def backup_cripto(parameters: dict, player=None) -> str:
    from core import backup_cripto as B
    acao = str(parameters.get("action") or "status").strip().lower()
    try:
        if acao in ("setup", "configurar"):
            pasta = B.configurar(str(parameters.get("folder") or ""), str(parameters.get("passphrase") or ""))
            r = B.fazer_backup()
            return (f"[done] Backup configurado em {pasta} e o primeiro já foi feito ({r['kb']} KB). Ele roda sozinho a cada "
                    "24 horas. ANOTE a frase-senha: sem ela ninguém (nem eu) abre o backup, e eu não a guardo.")
        if acao in ("now", "agora"):
            r = B.fazer_backup()
            return f"[done] Backup feito: {r['arquivo']} ({r['kb']} KB), {r['guardados']} guardado(s)."
        if acao in ("list", "listar"):
            L = B.listar()
            return "Backups: " + ", ".join(L[:8]) if L else "Nenhum backup na pasta ainda."
        if acao in ("restore", "restaurar"):
            L = B.listar()
            nome = str(parameters.get("name") or "") or (L[0] if L else "")
            frase = str(parameters.get("passphrase") or "")
            if not nome or not frase:
                return "Para restaurar preciso da frase-senha (e, se quiser um específico, o nome do backup)."
            from core import confirm
            return confirm.request("backup_restaurar", "Restaurar backup (substitui memórias e configurações)", nome,
                                   lambda: f"[done] Backup restaurado: {B.restaurar(nome, frase)} arquivo(s). Reinicie o NEXUS.")
        if acao in ("off", "desligar"):
            B.desligar()
            return "[done] Backup automático desligado e a chave apagada deste PC. Os arquivos na nuvem continuam lá."
    except B.ErroBackup as e:
        return f"[failed] {e}"
    except Exception as e:
        return f"[failed] Backup: {e}"
    return ("Backup automático ligado." if B.pronto() else "Backup ainda não configurado.") + \
        (f" Últimos: {', '.join(B.listar()[:3])}." if B.pronto() and B.listar() else "")


TOOL = {
    "name": "backup_cripto",
    "description": ("Encrypted automatic backup of NEXUS memories and settings into a folder the user syncs with THEIR "
                    "own cloud (OneDrive, Drive, Dropbox, USB). AES-256-GCM, the passphrase is never stored. "
                    "action=setup with folder and passphrase (min 8 chars; tell the user to write it down); now; list; "
                    "restore (passphrase, optional name; asks CONFIRM on screen); off; status. Use for 'faz backup', "
                    "'configura backup na pasta X', 'restaura o backup'. Never repeat the passphrase aloud. Answer in Portuguese."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["setup", "now", "list", "restore", "off", "status"]},
            "folder": {"type": "STRING", "description": "setup: folder synced with the user's cloud"},
            "passphrase": {"type": "STRING", "description": "setup/restore: the user's passphrase"},
            "name": {"type": "STRING", "description": "restore: backup file name (default: newest)"},
        },
        "required": ["action"],
    },
    "handler": backup_cripto,
}
