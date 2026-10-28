"""Rede neural: motor (core/neural_engine.py) + ferramenta (actions/neural_core.py)."""
import json
import numpy as np
import pytest

from core import neural_engine as eng
from actions import neural_core as nc


@pytest.fixture(autouse=True)
def _dir(tmp_path, monkeypatch):
    monkeypatch.setattr(nc, "_MODELS_DIR", tmp_path / "models")


def _blobs(n=40, seed=0):
    rng = np.random.default_rng(seed)
    lines = ["x1,x2,y"]
    for lab, (cx, cy) in zip("ABC", [(0, 0), (5, 5), (-5, 5)]):
        for _ in range(n):
            lines.append(f"{cx + rng.normal(0, 1):.2f},{cy + rng.normal(0, 1):.2f},{lab}")
    return "\n".join(lines)


@pytest.mark.parametrize("act", list(eng.ACTIVATIONS))
def test_gradient_numerico(act):
    rng = np.random.default_rng(1)
    net = eng.MLP([3, 5, 4, 2], act, seed=3)
    X, Y = rng.normal(size=(6, 3)), np.eye(2)[rng.integers(0, 2, 6)]
    w = np.ones(6)

    def loss():
        return eng.loss_and_delta(net.predict(X), Y, w, "classification")[0]

    out, cache = net.forward(X)
    _, d = eng.loss_and_delta(out, Y, w, "classification")
    gW, _ = net.backward(cache, d)
    for li in range(3):
        i, j = 0, 0
        old = net.W[li][i, j]
        net.W[li][i, j] = old + 1e-5; a = loss()
        net.W[li][i, j] = old - 1e-5; b = loss()
        net.W[li][i, j] = old
        assert abs((a - b) / 2e-5 - gW[li][i, j]) < 1e-5


@pytest.mark.parametrize("opt", eng.OPTIMIZERS)
def test_otimizadores_aprendem(opt):
    h, rows = nc.parse_table(_blobs(20))
    names, feats, y, _ = eng.clean_rows(h, rows)
    p = eng.Prep().fit(feats, names)
    X = p.transform(feats)
    _, _, yi = eng._prepare_target(y, "auto")
    Y = eng._onehot(yi, 3)
    net = eng.MLP([2, 8, 3])
    hist = eng.fit(net, X, Y, "classification", epochs=80, optimizer=opt, schedule="warmup_cosine")
    assert hist["train"][-1] < hist["train"][0] * 0.6


@pytest.mark.parametrize("sched", eng.SCHEDULES)
def test_agendas(sched):
    assert 0 < eng.lr_at(sched, 10, 100, 0.01) <= 0.01 + 1e-12


def test_treino_completo_com_tudo(tmp_path):
    rep = nc.train_dataset(_blobs(), "t", hidden="64,32,16", epochs=120, activation="gelu",
                           optimizer="adamw", dropout=0.1, noise=0.05, patience=10,
                           ensemble=3, synthetic=0.3, compress=0.4)
    assert rep["ensemble"] == 3 and rep["synthetic_added"] > 0
    assert rep["sparsity"] > 0.3
    assert rep["metrics"]["test"]["accuracy"] > 0.9
    assert rep["importance"] and (nc._MODELS_DIR / "t_report.html").exists()
    assert nc.predict("t", [5, 5])["label"] == "B"
    assert nc.predict("t", [5, 5])["members"] == 3


def test_parada_antecipada():
    h, rows = nc.parse_table(_blobs(30))
    m, rep = eng.train_pipeline(h, rows, {"epochs": 500, "patience": 5})
    assert rep["history"]["stopped_early"] and rep["history"]["epochs_run"] < 500


def test_automl_busca_e_ensemble():
    rep = nc.train_dataset(_blobs(30), "auto", auto=True, trials=4, budget_s=20)
    assert rep["leaderboard"] and rep["ensemble"] >= 3
    rep2 = nc.train_dataset(_blobs(30), "g", search="grid", trials=3, epochs=60)
    assert rep2["search_mode"] == "grid"


def test_categoricos_faltantes_e_regressao():
    rng = np.random.default_rng(2)
    L = ["cor,tamanho,preco"]
    for _ in range(80):
        c = rng.choice(["azul", "verde", "rosa"])
        t = rng.uniform(1, 10)
        base = {"azul": 10, "verde": 20, "rosa": 30}[c]
        L.append(f"{c},{'' if rng.random() < 0.1 else f'{t:.1f}'},{base + 2 * t:.1f}")
    rep = nc.train_dataset("\n".join(L), "preco", epochs=200)
    assert rep["task"] == "regression" and rep["encoded_features"] == 4
    assert rep["metrics"]["test"]["r2"] > 0.8
    assert 30 < nc.predict("preco", ["rosa", 5])["value"] < 50
    assert nc.predict("preco", ["nova_cor", ""])["task"] == "regression"   # inédito + vazio


def test_desbalanceado_pesos_e_oversample():
    rng = np.random.default_rng(3)
    L = ["a,b,c"]
    for _ in range(90):
        L.append(f"{rng.normal(0, 1):.2f},{rng.normal(0, 1):.2f},comum")
    for _ in range(10):
        L.append(f"{rng.normal(3, .5):.2f},{rng.normal(3, .5):.2f},raro")
    assert nc.train_dataset("\n".join(L), "w", balance="weights", epochs=80)["balance"] == "weights"
    assert nc.train_dataset("\n".join(L), "o", balance="oversample", epochs=80)["synthetic_added"] > 0


def test_finetune_destilacao_compressao_e_explicacao():
    nc.train_dataset(_blobs(), "base", ensemble=2, epochs=100)
    d = _blobs(15, seed=9)
    ft = nc.neural_core_action({"action": "finetune", "model_name": "base", "dataset": d,
                                "freeze": 1, "epochs": 30})
    assert "fine-tuned" in ft and nc.predict("base_ft", [5, 5])["label"] == "B"
    ds = nc.neural_core_action({"action": "distill", "model_name": "base", "dataset": d,
                                "hidden": "6"})
    m = nc._load("base_student")
    assert "agrees" in ds and len(m["members"]) == 1
    cp = nc.neural_core_action({"action": "compress", "model_name": "base", "dataset": d,
                                "compress": 0.6})
    assert nc._load("base_small")["sparsity"] > 0.5 and "pruned" in cp
    ex = nc.neural_core_action({"action": "explain", "model_name": "base", "features": "5,5"})
    assert "drove" in ex


def test_modelo_antigo_v1_continua_funcionando(tmp_path):
    net = eng.MLP([2, 4, 2], "relu", seed=1)
    old = {"name": "velho", "task": "classification", "classes": ["a", "b"],
           "mean": [0.0, 0.0], "std": [1.0, 1.0], "y_mean": 0.0, "y_std": 1.0,
           "sizes": net.sizes, "W": [w.tolist() for w in net.W],
           "b": [b.tolist() for b in net.b], "header": None, "features": 2,
           "created": "x", "quality": "q"}
    nc._MODELS_DIR.mkdir(parents=True)
    (nc._MODELS_DIR / "velho.json").write_text(json.dumps(old))
    assert nc.predict("velho", [1.0, 2.0])["label"] in ("a", "b")
    assert nc.list_models()[0]["name"] == "velho"


def test_augment_monitor_historico_e_lista():
    out = nc.neural_core_action({"action": "augment", "dataset": _blobs(10), "synthetic": 0.5})
    assert "synthetic" in out
    nc.train_dataset(_blobs(), "m", epochs=60)
    assert "only" in nc.neural_core_action({"action": "monitor", "model_name": "m"})
    for _ in range(6):
        nc.predict("m", [0, 0])
    assert "healthy" in nc.neural_core_action({"action": "monitor", "model_name": "m"})
    for _ in range(8):
        nc.predict("m", [40, 40])                      # entradas muito fora do treino
    assert "needs attention" in nc.neural_core_action({"action": "monitor", "model_name": "m"})
    assert "experiments" in nc.neural_core_action({"action": "history"})
    assert "m (" in nc.neural_core_action({"action": "list"})


def test_erros_viram_mensagem():
    assert "couldn't" in nc.neural_core_action({"action": "train", "dataset": "a,b\n1,2", })
    assert "couldn't" in nc.neural_core_action({"action": "train", "dataset": _blobs(5),
                                                  "activation": "foo"})
    assert "not found" in nc.neural_core_action({"action": "predict", "model_name": "x", "features": "1"})
