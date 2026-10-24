"""Configura o e-mail que o Nexus lê em voz alta.

Rode uma vez, com o Nexus FECHADO, de dentro da pasta do Nexus:

    python configurar_email.py

Ele pede o endereço de e-mail e a SENHA DE APP (não é a senha normal do Gmail),
testa a conexão e, se der certo, salva em config/api_keys.json. A senha não
aparece na tela enquanto você digita — é normal.

Como gerar a senha de app do Gmail:
  1. Ative a verificação em duas etapas: myaccount.google.com/security
  2. Abra myaccount.google.com/apppasswords
  3. Dê um nome (ex.: Nexus) e clique em Criar
  4. Copie as 16 letras que aparecem
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from actions.email_reader import guess_host, test_login       # noqa: E402
from memory.config_manager import save_plugin_config, get_plugin_config  # noqa: E402


def main() -> None:
    print("=" * 60)
    print(" NEXUS — configurar leitura de e-mails")
    print("=" * 60)
    atual = get_plugin_config("email").get("address")
    if atual:
        print(f"E-mail configurado hoje: {atual}")
        if input("Quer remover a configuração de e-mail? (s/N) ").strip().lower() == "s":
            save_plugin_config("email", {"address": "", "app_password": "", "imap_host": ""})
            print("Removido. O Nexus não vai mais ler e-mails.")
            return

    address = input("Seu e-mail (ex.: voce@gmail.com): ").strip()
    if "@" not in address:
        print("Isso não parece um e-mail. Nada foi salvo.")
        return
    print("\nAgora a SENHA DE APP (16 letras, gerada em myaccount.google.com/apppasswords).")
    print("Ela não aparece enquanto você digita.")
    password = getpass.getpass("Senha de app: ").replace(" ", "").strip()
    if not password:
        print("Senha vazia. Nada foi salvo.")
        return

    host = guess_host(address)
    print(f"\nTestando a conexão com {host}...")
    ok, msg = test_login(address, password, host)
    if not ok:
        print(f"\n❌ Não funcionou: {msg}")
        print("Confira se é a SENHA DE APP (não a senha normal) e se a verificação")
        print("em duas etapas está ativada. Nada foi salvo.")
        return

    save_plugin_config("email", {"address": address, "app_password": password,
                                 "imap_host": host})
    print("\n✅ Pronto! E-mail conectado.")
    print("Abra o Nexus: a partir de agora ele lê em voz alta os e-mails que chegarem.")
    print('Pra desligar a leitura automática, é só falar: "para de ler meus e-mails".')


if __name__ == "__main__":
    try:
        main()
    finally:
        if sys.platform == "win32":
            input("\nAperte Enter para fechar...")
