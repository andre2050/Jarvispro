"""4.6.0 — o motor que reinicia herda a conversa."""
from types import SimpleNamespace as NS

from core.continuidade import herdar


def test_herda_handle_e_falas():
    velho = NS(_resume_handle="h123", _session_log=["oi", "tudo bem"])
    novo = NS(_resume_handle=None, _session_log=[])
    r = herdar(velho, novo)
    assert r == {"handle": True, "falas": 2}
    assert novo._resume_handle == "h123" and novo._session_log == ["oi", "tudo bem"]
    novo._session_log.append("x")
    assert velho._session_log == ["oi", "tudo bem"]          # cópia, não o mesmo objeto


def test_sem_nada_para_herdar_nao_mexe():
    velho = NS(_resume_handle=None, _session_log=[])
    novo = NS(_resume_handle=None, _session_log=["a"])
    assert herdar(velho, novo) == {"handle": False, "falas": 0}
    assert novo._session_log == ["a"] and novo._resume_handle is None


def test_motor_velho_estranho_nao_derruba():
    assert herdar(object(), NS()) == {"handle": False, "falas": 0}
    assert herdar(NS(_session_log="nao e lista", _resume_handle=""), NS()) == {"handle": False, "falas": 0}


def test_main_usa_a_continuidade():
    from pathlib import Path
    texto = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
    assert "core.continuidade" in texto and "velho, jarvis = jarvis, NexusLive(ui)" in texto
