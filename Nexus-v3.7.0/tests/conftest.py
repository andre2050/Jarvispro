"""Configuração dos testes do NEXUS: roda sem tela, sem placa de som e sem internet."""
import os
import sys
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# `sounddevice` precisa da biblioteca PortAudio do sistema; nos testes ela não é usada.
try:
    import sounddevice  # noqa: F401
except Exception:
    _fake = types.ModuleType("sounddevice")
    _fake.__dict__.update(query_devices=lambda *a, **k: [], default=types.SimpleNamespace(device=(None, None)))
    sys.modules["sounddevice"] = _fake

import pytest


@pytest.fixture(autouse=True)
def _falhas_isoladas(tmp_path, monkeypatch):
    """Erros anotados durante os testes vão para uma pasta temporária, não para o memory/falhas.log real."""
    from core import protecao
    monkeypatch.setattr(protecao, "ARQ_FALHAS", tmp_path / "falhas_teste.log")
    monkeypatch.setattr(protecao, "_vistos", {})


@pytest.fixture
def projeto(tmp_path):
    """Uma pasta de projeto vazia."""
    pasta = tmp_path / "proj"
    pasta.mkdir()
    return pasta
