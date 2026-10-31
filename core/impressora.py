"""Controle de impressora (4.5.0): listar, ver a fila, imprimir arquivo ou texto e cancelar.

Windows usa PowerShell; Linux e macOS usam lpstat/lp/cancel. Nada passa por "shell": os comandos são listas.
Regras de segurança:
  • só imprime arquivos dentro da sua pasta de usuário, de tipos comuns (pdf, txt, imagens, Office);
  • a impressora precisa estar na lista que o próprio sistema informou;
  • no máximo 20 cópias; texto até 20 mil caracteres;
  • imprimir e cancelar pedem CONFIRMAR na tela (veja actions/printer_control.py).
"""
from __future__ import annotations

import json
import platform
import re
import subprocess
import tempfile
from pathlib import Path

EXTENSOES = {".pdf", ".txt", ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".md", ".csv"}
MAX_COPIAS = 20
MAX_TEXTO = 20000


class ErroImpressora(Exception):
    pass


def _windows() -> bool:
    return platform.system() == "Windows"


def _rodar(args: list[str], timeout: int = 25) -> tuple[int, str]:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, errors="replace")
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except FileNotFoundError:
        raise ErroImpressora("Não achei o sistema de impressão neste computador (no Linux/macOS instale o CUPS).")
    except subprocess.TimeoutExpired:
        raise ErroImpressora("O sistema de impressão não respondeu a tempo.")


def _ps(comando: str, timeout: int = 25) -> tuple[int, str]:
    return _rodar(["powershell", "-NoProfile", "-NonInteractive", "-Command", comando], timeout)


def _aspas(valor: str) -> str:
    """Texto seguro dentro de aspas simples do PowerShell: só a aspa simples precisa ser dobrada."""
    return str(valor).replace("'", "''")


def listar() -> list[dict]:
    """[{'nome': ..., 'padrao': bool}]"""
    if _windows():
        cod, out = _ps("Get-CimInstance Win32_Printer | Select-Object Name,Default | ConvertTo-Json -Compress")
        if cod != 0 or not out.strip():
            return []
        try:
            dado = json.loads(out)
        except ValueError:
            return []
        if isinstance(dado, dict):
            dado = [dado]
        return [{"nome": str(i.get("Name")), "padrao": bool(i.get("Default"))} for i in dado if i.get("Name")]
    cod, out = _rodar(["lpstat", "-e"])
    nomes = [ln.strip() for ln in out.splitlines() if ln.strip()] if cod == 0 else []
    cod, out = _rodar(["lpstat", "-d"])
    m = re.search(r":\s*(\S+)\s*$", out.strip()) if cod == 0 else None
    padrao = m.group(1) if m else ""
    return [{"nome": n, "padrao": n == padrao} for n in nomes]


def escolher(impressora: str = "") -> str:
    """O nome exato de uma impressora que existe. Vazio = a padrão. Aceita parte do nome."""
    lista = listar()
    if not lista:
        raise ErroImpressora("Nenhuma impressora instalada foi encontrada.")
    if not impressora.strip():
        padrao = next((i["nome"] for i in lista if i["padrao"]), lista[0]["nome"])
        return padrao
    alvo = impressora.strip().lower()
    for i in lista:
        if i["nome"].lower() == alvo:
            return i["nome"]
    achadas = [i["nome"] for i in lista if alvo in i["nome"].lower()]
    if len(achadas) == 1:
        return achadas[0]
    if not achadas:
        raise ErroImpressora("Não achei essa impressora. As que tenho: " + ", ".join(i["nome"] for i in lista) + ".")
    raise ErroImpressora("Mais de uma impressora combina: " + ", ".join(achadas) + ". Diga o nome inteiro.")


def fila(impressora: str = "") -> list[str]:
    nome = escolher(impressora)
    if _windows():
        cod, out = _ps(f"Get-PrintJob -PrinterName '{_aspas(nome)}' | Select-Object Id,DocumentName,JobStatus | ConvertTo-Json -Compress")
        if cod != 0 or not out.strip():
            return []
        try:
            dado = json.loads(out)
        except ValueError:
            return []
        if isinstance(dado, dict):
            dado = [dado]
        return [f"{i.get('Id')}: {i.get('DocumentName')} ({i.get('JobStatus')})" for i in dado]
    cod, out = _rodar(["lpstat", "-o", nome])
    return [ln.strip() for ln in out.splitlines() if ln.strip()] if cod == 0 else []


def validar_arquivo(caminho: str, raiz: Path | None = None) -> Path:
    """O arquivo precisa existir, estar na sua pasta de usuário e ser de um tipo comum."""
    p = Path(str(caminho or "").strip().strip('"')).expanduser()
    try:
        p = p.resolve()
    except OSError:
        raise ErroImpressora("Caminho inválido.")
    base = (raiz or Path.home()).resolve()
    if p != base and not p.is_relative_to(base):
        raise ErroImpressora("Só imprimo arquivos dentro da sua pasta de usuário.")
    if not p.is_file():
        raise ErroImpressora("Não achei esse arquivo.")
    if p.suffix.lower() not in EXTENSOES:
        raise ErroImpressora(f"Não imprimo arquivos {p.suffix or 'sem extensão'}.")
    if re.search(r"[\x00-\x1f]", str(p)):
        raise ErroImpressora("Caminho inválido.")
    return p


def _copias(n) -> int:
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 1
    return max(1, min(MAX_COPIAS, n))


def imprimir_arquivo(caminho: str, impressora: str = "", copias=1, raiz: Path | None = None) -> str:
    p = validar_arquivo(caminho, raiz)
    nome = escolher(impressora)
    n = _copias(copias)
    if _windows():
        for _ in range(n):
            if p.suffix.lower() in (".txt", ".md", ".csv"):
                cod, out = _ps(f"Get-Content -LiteralPath '{_aspas(str(p))}' | Out-Printer -Name '{_aspas(nome)}'", 60)
            else:
                cod, out = _ps(f"Start-Process -FilePath '{_aspas(str(p))}' -Verb PrintTo -ArgumentList '\"{_aspas(nome)}\"' -WindowStyle Hidden", 60)
            if cod != 0:
                raise ErroImpressora("A impressão não começou: " + out.strip()[:120])
    else:
        cod, out = _rodar(["lp", "-d", nome, "-n", str(n), str(p)], 60)
        if cod != 0:
            raise ErroImpressora("A impressão não começou: " + out.strip()[:120])
    return f"Mandei “{p.name}” para a impressora {nome}" + (f" ({n} cópias)." if n > 1 else ".")


def imprimir_texto(texto: str, impressora: str = "", copias=1, pasta_temp: Path | None = None) -> str:
    texto = str(texto or "")
    if not texto.strip():
        raise ErroImpressora("Não há texto para imprimir.")
    if len(texto) > MAX_TEXTO:
        raise ErroImpressora("Texto grande demais para imprimir de uma vez (máximo 20 mil caracteres).")
    pasta = Path(pasta_temp or tempfile.gettempdir())
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8", dir=str(pasta)) as f:
        f.write(texto)
        arq = Path(f.name)
    try:
        return imprimir_arquivo(str(arq), impressora, copias, raiz=pasta)
    finally:
        # Dá tempo do spooler pegar o arquivo no Windows (Out-Printer lê na hora; lp copia na hora).
        try:
            arq.unlink()
        except OSError:
            pass


def cancelar(impressora: str = "") -> str:
    nome = escolher(impressora)
    if _windows():
        cod, out = _ps(f"Get-PrintJob -PrinterName '{_aspas(nome)}' | Remove-PrintJob", 30)
    else:
        cod, out = _rodar(["cancel", "-a", nome])
    if cod != 0:
        raise ErroImpressora("Não consegui cancelar: " + out.strip()[:120])
    return f"Cancelei os trabalhos na fila da impressora {nome}."
