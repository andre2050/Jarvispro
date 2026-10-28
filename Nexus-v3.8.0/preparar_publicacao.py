"""Prepara uma versão nova do Nexus para publicar no GitHub — SEM segredos.

Rode de dentro da pasta do Nexus:

    python preparar_publicacao.py

O que ele faz:
  1. Pergunta o número da versão nova e o que mudou (gravado em
     memory/version.json no fim, só se tudo der certo).
  2. Cria, AO LADO da pasta do Nexus, uma cópia limpa chamada
     "Nexus-publicar", sem a sua chave do Gemini, sem senha de e-mail,
     sem certificados, sem suas memórias, notas e logs.
  3. Procura em todos os arquivos da cópia qualquer coisa que pareça chave
     ou senha. Se achar, PARA, apaga a cópia e mostra onde estava.
  4. Gera o zip "Nexus-Ultra-2026-vX.zip" pronto para anexar na release.

A sua pasta original não é alterada (só o memory/version.json).
"""
import json
import re
import shutil
import sys
import time
import zipfile
from fnmatch import fnmatch
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT_DIR = BASE.parent / "Nexus-publicar"
TOP = "Nexus"

# Tudo que é seu e NUNCA vai pro GitHub. (Mesma lista do .gitignore.)
EXCLUDE = [
    "config/api_keys.json", "config/licenca.json", "config/certs/*", "config/whatsapp_web/*",
    "config/quick_notes.json", "config/focus_state.json", "config/email_account.json",
    "memory/intent_examples.json", "memory/intent_net.npz", "memory/intent_net_settings.json",
    "memory/long_term.json", "memory/facts.json", "memory/conversations.json",
    "memory/routines.json", "memory/habits.json", "memory/projetos.json", "memory/email_state.json",
    "memory/update_state.json", "memory/price_alerts.json", "memory/*.db",
    "memory/reminders.json",
    # 2.1 — finanças, tarefas, casa inteligente, pastas vigiadas, registro de auditoria
    "config/finance_entries.json", "config/finance_budgets.json", "config/casa.json",
    "config/folder_watch.json", "config/facts.json", "config/shortcut_catalog.json",
    "memory/tarefas.json", "memory/compras.json", "memory/habitos_diarios.json",
    "memory/contatos.json", "memory/diario.json", "memory/*.quebrado", "memory/*.desfeito.json", "memory/audit.log*", "erro_ao_abrir.txt",
    # 2.3 — voz, rostos, métricas, quedas e modelos
    "memory/voz_dono.*", "memory/wake_nexus.npz", "memory/indice_semantico.npz", "memory/reconexoes.log",
    "memory/falhas.log", "memory/queda_nativa.log", "memory/sessao.json", "memory/metricas.csv", "memory/anomalia.json",
    "memory/previsao_habitos.json", "memory/rostos.npz", "memory/modelos/*", "memory/cerebro_local/*",
    "uploads/*", ".ruff_cache/*", ".pytest_cache/*", "*.log.*",
    "memory/organizacao_desktop*.json",   # 1.4.2 — onde estavam os arquivos da sua área de trabalho
    # 3.4 — bem-estar, vigias, tempo de projeto e o núcleo I.S.A.
    "memory/bemestar.json", "memory/vigias.json", "memory/tempo_projetos.json", "memory/isa_series.json",
    "memory/regeneracao.json", "memory/regeneracao_copias/*", "memory/routines_sementes.json",
    # estatísticas de uso e resumos da sua semana (3.2/3.3)
    "memory/autoavaliacao.json", "memory/latencia.json", "memory/resumo_semanal.json",
    # 3.5 — memória de documentos (RAG), plugins instalados pela loja e autores em quem você confia
    "memory/rag_documentos.npz", "memory/rag_pastas.json", "memory/emails_cache/*", "memory/backup_chave.json", "memory/presenca.json", "memory/rag_config.json", "memory/perfil.json", "config/focus_state.json", "memory/push_subs.json", "memory/push_vapid.pem", "memory/plugins_loja.json", "config/autores_confiaveis.json",
    # 3.8 — auditoria, missões, grafo, rede de NEXUS, agentes, modo do modelo, plugins gerados
    "memory/auditoria.jsonl", "memory/missoes/*", "memory/grafo.json", "memory/rede_backup/*", "config/rede_nexus.json",
    "config/agentes.json", "config/hibrido.json", "plugins_gerados/*",
    # o Nexus.exe gerado no seu PC (gerar_exe.bat) — grande demais para o GitHub
    "Nexus.exe", "_internal/*", "build/*", "dist/*",
    "*.log", "*.tmp", "*.part",
    "updates/*", "backups/*", "downloads/*", "screenshots/*", "logs/*",
    "*__pycache__*", "*.pyc", ".git/*", ".venv/*", "venv/*", "env/*",
    "*token*.json", "*client_secret*.json", "*credentials*.json",
    ".env", ".env.*", "*.key", "*.pem", "*.p12",
]

SECRET_PATTERNS = [
    (re.compile(r"AIza[0-9A-Za-z_\-]{35}"), "chave do Google/Gemini"),
    (re.compile(r"sk-ant-[0-9A-Za-z_\-]{20,}"), "chave da Anthropic"),
    (re.compile(r"sk-[A-Za-z0-9]{32,}"), "chave de API (sk-...)"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "chave privada"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), "token do GitHub"),
]
TEXT_EXT = {".py", ".json", ".txt", ".md", ".html", ".js", ".css", ".cfg",
            ".ini", ".toml", ".yml", ".yaml", ".env", ".bat", ".sh", ".obj", ""}


def excluded(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    return any(fnmatch(rel, pat) or rel.startswith(pat.rstrip("*")) and pat.endswith("/*")
               for pat in EXCLUDE)


def my_secrets() -> list[str]:
    """Os valores reais do seu api_keys.json — procurados literalmente na cópia."""
    out = []
    try:
        data = json.loads((BASE / "config" / "api_keys.json").read_text(encoding="utf-8"))
    except Exception:
        return out

    def walk(d):
        if isinstance(d, dict):
            for k, v in d.items():
                if isinstance(v, str) and len(v) >= 12 and re.search(
                        r"key|password|token|secret|senha", str(k), re.I):
                    out.append(v.replace(" ", ""))
                    out.append(v)
                else:
                    walk(v)
    walk(data)
    return [s for s in set(out) if s]


def bump(v: str) -> str:
    parts = v.split(".")
    try:
        parts[-1] = str(int(parts[-1]) + 1)
        return ".".join(parts)
    except ValueError:
        return v


def scan(folder: Path) -> list[str]:
    real = my_secrets()
    problems = []
    for f in folder.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in TEXT_EXT:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        rel = f.relative_to(folder)
        for s in real:
            if s in text:
                problems.append(f"{rel}: contém a sua chave/senha de verdade")
        for rx, what in SECRET_PATTERNS:
            if rx.search(text):
                problems.append(f"{rel}: parece ter {what}")
    return problems


def main() -> None:
    print("=" * 64)
    print(" NEXUS — preparar versão para o GitHub (sem segredos)")
    print("=" * 64)
    vfile = BASE / "memory" / "version.json"
    data = json.loads(vfile.read_text(encoding="utf-8"))
    cur = str(data.get("version", "0.0"))
    sug = bump(cur)
    new = input(f"Versão atual: {cur}. Número da versão nova [{sug}]: ").strip().lstrip("vV") or sug
    if not re.fullmatch(r"\d+(\.\d+)*", new):
        print("Versão inválida (use números, ex.: 8.8). Nada foi feito.")
        return
    notes = input("O que mudou nesta versão (uma frase): ").strip() or "Melhorias e correções."

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    dest_root = OUT_DIR / TOP
    copied = skipped = 0
    for f in BASE.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(BASE).as_posix()
        if excluded(rel):
            skipped += 1
            continue
        d = dest_root / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, d)
        copied += 1
    print(f"✔ Cópia limpa: {copied} arquivos ({skipped} deixados de fora: chaves, memórias, logs, cache, updates)")

    problems = scan(dest_root)
    if problems:
        shutil.rmtree(OUT_DIR, ignore_errors=True)
        print("\n❌ PAREI: encontrei algo que parece segredo na cópia:")
        for p in problems[:30]:
            print("   -", p)
        print("Tire isso desses arquivos e rode de novo. Nada foi gerado.")
        return
    print("✔ Nenhuma chave ou senha encontrada na cópia")

    # Só agora a versão muda — se a verificação parou acima, nada foi alterado.
    if new != cur:
        data["version"] = new
        data["released"] = time.strftime("%Y-%m-%d")
        log = data.get("changelog") or []
        log.insert(0, {"version": new, "date": data["released"], "notes": notes})
        data["changelog"] = log
        text = json.dumps(data, indent=2, ensure_ascii=False)
        vfile.write_text(text, encoding="utf-8")
        (dest_root / "memory" / "version.json").write_text(text, encoding="utf-8")
        print(f"✔ memory/version.json agora é v{new}")

    zpath = OUT_DIR / f"{TOP}-v{new}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in dest_root.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(OUT_DIR).as_posix())
    print(f"✔ Zip da release: {zpath}")

    print("\nPRÓXIMOS PASSOS (detalhes no LEIA-ME):")
    print(f"  1. Envie o conteúdo de {dest_root} para o seu repositório")
    print("     (GitHub Desktop ou arrastando no site).")
    print(f"  2. No GitHub: Releases → Draft a new release → tag v{new}")
    print(f"  3. Anexe o arquivo {zpath.name} e clique em Publish release.")


if __name__ == "__main__":
    try:
        main()
    finally:
        if sys.platform == "win32":
            input("\nAperte Enter para fechar...")
