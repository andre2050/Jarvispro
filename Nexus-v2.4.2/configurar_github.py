"""Liga o auto-update do Nexus ao seu repositório do GitHub (público ou privado).

Rode uma vez, com o Nexus FECHADO, de dentro da pasta do Nexus:

    python configurar_github.py

Ele pergunta o repositório (ex.: andre/Nexus-Pro) e, se for PRIVADO, um token
de leitura. Testa o acesso e salva:
  - o repositório em config/update.json (vai junto pro GitHub);
  - o token em config/api_keys.json (NUNCA vai pro GitHub).

Como criar o token (só leitura, só desse repositório):
  1. github.com → sua foto → Settings → Developer settings
     → Personal access tokens → Fine-grained tokens → Generate new token
  2. Nome: Nexus. Expiration: o maior prazo que aparecer.
  3. Repository access: "Only select repositories" → escolha o Nexus-Pro.
  4. Permissions → Repository permissions → Contents: "Read-only".
  5. Generate token e copie (começa com github_pat_).
"""
import getpass
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from memory.config_manager import _patch_config, load_api_keys  # noqa: E402


def main() -> None:
    print("=" * 60)
    print(" NEXUS — ligar o auto-update ao GitHub")
    print("=" * 60)
    upd_file = BASE / "config" / "update.json"
    try:
        upd = json.loads(upd_file.read_text(encoding="utf-8"))
    except Exception:
        upd = {}
    atual = upd.get("github_repo") or ""
    repo = input(f"Repositório (usuario/nome){f' [{atual}]' if atual else ''}: ").strip() or atual
    repo = re.sub(r"^https?://github\.com/", "", repo).strip("/").removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        print("Formato inválido. Use usuario/repositorio, ex.: andre/Nexus-Pro.")
        return

    print("\nSe o repositório for PRIVADO, cole o token de leitura (github_pat_...).")
    print("Se for público, só aperte Enter. O token não aparece enquanto você digita.")
    token = getpass.getpass("Token: ").strip()

    import requests
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    print(f"\nTestando o acesso a {repo}...")
    try:
        r = requests.get(f"https://api.github.com/repos/{repo}", headers=headers, timeout=10)
    except Exception as e:
        print(f"❌ Não consegui falar com o GitHub: {e}")
        return
    if r.status_code == 401:
        print("❌ Token recusado. Confira se copiou inteiro e se não expirou. Nada foi salvo.")
        return
    if r.status_code == 404:
        print("❌ Repositório não encontrado.")
        print("   Se ele é privado, o token precisa ter acesso a ele (Contents: Read-only).")
        print("   Nada foi salvo.")
        return
    if r.status_code != 200:
        print(f"❌ O GitHub respondeu {r.status_code}. Nada foi salvo.")
        return
    privado = bool(r.json().get("private"))

    upd["github_repo"] = repo
    upd_file.write_text(json.dumps(upd, indent=4, ensure_ascii=False), encoding="utf-8")
    if token:
        _patch_config(github_token=token)
    elif "github_token" in load_api_keys():
        _patch_config(github_token="")
    print(f"\n✅ Pronto! Auto-update ligado em {repo} ({'privado' if privado else 'público'}).")
    if privado and not token:
        print("⚠ O repositório é privado e nenhum token foi salvo — o auto-update não vai enxergá-lo.")
    print("O Nexus confere as releases alguns minutos depois de abrir e a cada 6 horas.")


if __name__ == "__main__":
    try:
        main()
    finally:
        if sys.platform == "win32":
            input("\nAperte Enter para fechar...")
