"""Manage a local catalog of named shortcuts; no arbitrary shell commands."""
import json, re
from pathlib import Path
TOOL={"name":"shortcut_manager","description":"Create, list, or delete named keyboard shortcut mappings for the assistant's local shortcut catalog. Actions: add, list, delete. This stores mappings; it does not register global OS hotkeys.",
"parameters":{"type":"OBJECT","properties":{"action":{"type":"STRING","enum":["add","list","delete"]},"name":{"type":"STRING"},"keys":{"type":"STRING"},"target":{"type":"STRING"}},"required":["action"]},"handler":None}
_FILE=Path(__file__).resolve().parent.parent/"config"/"shortcut_catalog.json"
def _load():
 try:
  d=json.loads(_FILE.read_text(encoding="utf-8")); return d if isinstance(d,dict) else {}
 except Exception:return {}
def shortcut_manager(parameters, player=None):
 d=_load(); action=str(parameters.get("action","list")).lower(); name=str(parameters.get("name","")).strip()[:60]
 if action=="list": return "Atalhos cadastrados: "+("; ".join(f"{n}: {v['keys']} → {v['target']}" for n,v in d.items()) if d else "nenhum")
 if not name:return "Informe um nome para o atalho."
 if action=="delete":
  if name not in d:return "Esse atalho não existe."
  del d[name]
 else:
  keys=str(parameters.get("keys","")).strip()
  target=str(parameters.get("target","")).strip()
  if not re.fullmatch(r"(?i)(ctrl|alt|shift|win|cmd|f[1-9]|f1[0-2]|[a-z0-9])([+](ctrl|alt|shift|win|cmd|f[1-9]|f1[0-2]|[a-z0-9]))*",keys): return "Combinação de teclas inválida. Exemplo: Ctrl+Alt+J."
  if not target or len(target)>180:return "Informe um destino/ação curto para o atalho."
  d[name]={"keys":keys,"target":target}
 _FILE.parent.mkdir(parents=True,exist_ok=True); _FILE.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")
 return "Atalho removido." if action=="delete" else f"Atalho '{name}' salvo no catálogo. Observação: ainda não registra tecla global no sistema."
TOOL["handler"]=shortcut_manager
