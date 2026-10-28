from types import SimpleNamespace as NS
from datetime import datetime

from core import aprendizado as A
from core import estatisticas_pc as E


def _t(dia, h):                      # 2026-10-26 é segunda
    return datetime(2026, 10, dia, h, 0).timestamp()


def test_aprendizado_comeca_desligado_e_nao_conta_nada(tmp_path):
    arq = tmp_path / "a.json"
    assert not A.ligado(arq) and A.atualizar([{"t": _t(26, 9), "tool": "x"}], arq) == 0
    assert "desligado" in A.resumo(arq)


def test_conta_por_faixa_e_sugere_so_o_repetido(tmp_path):
    arq = tmp_path / "a.json"
    A.ligar(True, arq, agora=_t(1, 0))
    ev = [{"t": _t(d, 9), "tool": "open_app"} for d in (26, 27, 28, 29)] + [{"t": _t(26, 20), "tool": "music_control"}]
    now = _t(29, 12)
    assert A.atualizar(ev, arq, now) == 5
    s = A.sugestoes(arq, now)
    assert [x["tool"] for x in s] == ["open_app"] and "dia útil" in s[0]["quando"]
    assert A.agora_costuma(arq, _t(30, 10)) == ["open_app"]
    assert A.atualizar(ev, arq, now) == 0                                    # não conta duas vezes


def test_esquecimento_gradual_e_apagar(tmp_path):
    arq = tmp_path / "a.json"
    A.ligar(True, arq, agora=_t(1, 0))
    A.atualizar([{"t": _t(d, 9), "tool": "open_app"} for d in (26, 27, 28, 29)], arq, _t(29, 12))
    assert A.sugestoes(arq, _t(29, 12) + 60 * 86400) == []                   # 60 dias depois pesa 1/4
    assert "open_app" in A.exportar(arq)
    A.esquecer(arq)
    assert A.sugestoes(arq, _t(29, 12)) == [] and A.ligado(arq)


def test_guarda_so_contagens_sem_conteudo(tmp_path):
    arq = tmp_path / "a.json"
    A.ligar(True, arq, agora=0)
    A.atualizar([{"t": _t(26, 9), "tool": "open_app", "args": {"app_name": "segredo"}}], arq, _t(27, 0))
    assert "segredo" not in arq.read_text()


def _psu(mem=50, swap=0, cpu=10, disco=40, boot_h=2, bat=None):
    mk = lambda **k: NS(**k)
    procs = [NS(info={"name": "chrome", "memory_info": NS(rss=900e6), "cpu_percent": 5}), NS(info={"name": "chrome", "memory_info": NS(rss=600e6), "cpu_percent": 3}),
             NS(info={"name": "code", "memory_info": NS(rss=300e6), "cpu_percent": 1})]
    return NS(cpu_percent=lambda interval=None, percpu=False: [cpu, cpu] if percpu else cpu,
              virtual_memory=lambda: mk(used=8 * 1024 ** 3, total=16 * 1024 ** 3, percent=mem), swap_memory=lambda: mk(used=1e9, total=4e9, percent=swap),
              disk_partitions=lambda all=False: [mk(mountpoint="C:\\")], disk_usage=lambda p: mk(free=100e9 * (100 - disco) / 100, total=100e9, percent=disco),
              net_io_counters=lambda: mk(bytes_sent=5e6, bytes_recv=9e6), boot_time=lambda: 0 - boot_h * 3600, process_iter=lambda attrs=None: procs,
              sensors_battery=lambda: bat, sensors_temperatures=lambda: {"cpu": [mk(current=60)]})


def test_coleta_soma_processos_por_nome_e_texto():
    d = E.coletar(psu=_psu(), agora=0)
    assert d["top_mem"][0] == {"nome": "chrome", "mem_mb": 1500, "cpu": 8.0, "n": 2}
    t = E.texto(d)
    assert "Memória 8.0/16.0" in t and "chrome 1500 MB" in t and "tranquilo" in t


def test_sugestoes_por_regra():
    d = E.coletar(psu=_psu(mem=92, swap=60, cpu=95, disco=95, boot_h=24 * 9, bat=NS(percent=10, power_plugged=False)), agora=0)
    s = " ".join(E.sugestoes(d))
    for trecho in ("Memória em 92%", "memória de disco", "Processador em 95%", "quase cheio", "9 dias", "Bateria em 10%"):
        assert trecho in s


def test_sensor_faltando_nao_derruba():
    p = _psu()
    p.sensors_battery = lambda: 1 / 0
    p.sensors_temperatures = lambda: 1 / 0
    d = E.coletar(psu=p, agora=0)
    assert d["bateria"] is None and d["temp_max"] is None
