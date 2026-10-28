"""Modo foco 3.7: lista de distrações (com CONFIRMAR) e silêncio dos avisos no celular."""
import types

from actions import focus_mode as F


class ProcFalso:
    def __init__(self, nome):
        self.info = {"name": nome}
        self.fechado = False

    def terminate(self):
        self.fechado = True


def test_lista_de_distracoes_nunca_inclui_protegidos(monkeypatch):
    salvo = {}
    import memory.config_manager as CM
    monkeypatch.setattr(CM, "save_plugin_config", lambda ns, v: salvo.update(v))
    r = F.set_distractions("Discord, steam.exe; explorer.exe, python, discord")
    assert r == ["discord", "steam.exe"] and salvo["apps"] == r


def test_acha_e_fecha_so_o_que_esta_na_lista():
    procs = [ProcFalso("Discord.exe"), ProcFalso("steam.exe"), ProcFalso("explorer.exe"), ProcFalso("code.exe")]
    ach = F._processos_abertos(["discord", "steam.exe", "explorer.exe"], lambda: procs)
    assert {p.info["name"] for p in ach} == {"Discord.exe", "steam.exe"}
    msg = F._fechar(["discord", "steam.exe", "explorer.exe"], lambda: procs)
    assert "2 programa(s)" in msg
    assert [p.fechado for p in procs] == [True, True, False, False]


def test_foco_com_fechar_pede_confirmar_e_so_fecha_depois(monkeypatch, tmp_path):
    procs = [ProcFalso("discord.exe")]
    monkeypatch.setattr(F, "_STATE", tmp_path / "foco.json")
    monkeypatch.setattr(F, "get_distractions", lambda: ["discord"])
    vistos = {}
    from core import confirm
    monkeypatch.setattr(confirm, "request", lambda key, titulo, detalhe, run: vistos.update(key=key, detalhe=detalhe, run=run) or "[CONFIRMATION_PENDING]")
    monkeypatch.setattr(F, "_processos_abertos", lambda apps, listar=None: procs)
    r = F.focus_mode({"action": "start", "minutes": 10, "close_distractions": True})
    assert "CONFIRMATION_PENDING" in r and vistos["key"] == "foco_fechar" and "discord" in vistos["detalhe"]
    assert not procs[0].fechado                      # nada fecha antes do CONFIRMAR


def test_push_silenciado_durante_o_foco(monkeypatch, tmp_path):
    from core import push_web as PW
    monkeypatch.setattr(F, "active_reason", lambda: "modo foco (5 min restantes)")
    r = PW.enviar("NEXUS", "oi", arq_subs=tmp_path / "s.json", enviar_fn=lambda *a: None)
    assert r["motivo"] == "modo foco ligado" and r["enviados"] == 0
    r = PW.enviar("NEXUS", "teste", arq_subs=tmp_path / "s.json", enviar_fn=lambda *a: None, ignorar_intervalo=True)
    assert r["motivo"] == "nenhum celular assinado"      # o teste explícito ainda passa
