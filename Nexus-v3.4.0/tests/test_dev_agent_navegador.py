"""Teste do navegador invisível de verdade (Playwright + Chromium). Pulado se não houver."""
import pytest

from actions import dev_agent as DA

pytest.importorskip("playwright")


def _chromium_ok() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            pw.chromium.launch(headless=True).close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _chromium_ok(), reason="Chromium do Playwright não está disponível")


def _obra(pasta, html, js):
    (pasta / "index.html").write_text(html, encoding="utf-8")
    (pasta / "script.js").write_text(js, encoding="utf-8")
    o = DA._Obra("site", "html", pasta)
    o.entry, o.web = "index.html", True
    o.arquivos = [{"path": "index.html"}, {"path": "script.js"}]
    return o


HTML = "<!DOCTYPE html><html><head><meta charset='utf-8'></head><body><p id='x'>oi</p><script src='script.js'></script></body></html>"


def test_site_sem_erro(tmp_path):
    assert DA._checar_no_navegador(_obra(tmp_path, HTML, "document.getElementById('x').textContent='ok';")) == []


def test_erro_de_javascript_e_encontrado(tmp_path):
    problemas = DA._checar_no_navegador(_obra(tmp_path, HTML, "document.getElementById('nao-existe').textContent = 1;"))
    assert problemas and problemas[0]["tipo"] == "execucao"
    assert "null" in problemas[0]["problema"]


def test_console_error_conta_mas_arquivo_externo_ausente_nao(tmp_path):
    html = HTML.replace("</body>", "<img src='https://exemplo.invalid/a.png'></body>")
    assert DA._checar_no_navegador(_obra(tmp_path, html, "var a = 1;")) == []
    problemas = DA._checar_no_navegador(_obra(tmp_path, HTML, "console.error('quebrou de propósito');"))
    assert len(problemas) == 1 and "quebrou de propósito" in problemas[0]["problema"]
