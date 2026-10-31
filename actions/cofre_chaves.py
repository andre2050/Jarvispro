"""Cofre de chaves: 'guarda minhas chaves no cofre do sistema', 'tira as chaves do cofre'. Ver core/cofre.py."""
from core import cofre as C


def cofre_chaves(parameters: dict, **_kw) -> str:
    acao = str(parameters.get("action") or "status").strip().lower()
    if acao in ("on", "ligar", "enable"):
        r = C.ligar()
        if not r["ok"]:
            return "[failed] " + r["motivo"]
        return (f"[done] Cofre ligado ({C.nome_do_cofre()}). {r['moveu']} segredo(s) saíram do arquivo de configuração. "
                "Uma cópia de segurança ficou em config/api_keys.json.antes_do_cofre — apague depois de conferir que tudo funciona.")
    if acao in ("off", "desligar", "disable"):
        r = C.desligar()
        return ("[done] Cofre desligado. " + f"{r['voltou']} segredo(s) voltaram para o arquivo.") if r["ok"] else "[failed] " + r["motivo"]
    if C.disponivel():
        return f"[done] Cofre do sistema disponível ({C.nome_do_cofre()}). Estado: {'ligado' if C.ligado() else 'desligado'}."
    return "[done] Este computador não tem um cofre de senhas disponível; as chaves ficam no arquivo de configuração."


TOOL = {
    "name": "cofre_chaves",
    "description": ("Stores API keys and passwords in the operating system's credential vault instead of plain text in config/api_keys.json. "
                    "action=status (default) | on | off. Use for 'guarda minhas chaves no cofre', 'tira as chaves do cofre', 'minhas chaves estão seguras?'."),
    "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING", "enum": ["status", "on", "off"]}}},
    "handler": cofre_chaves,
}
