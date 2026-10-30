"""Motor Keras/TensorFlow (core/keras_engine.py, core/keras_intent.py) e o seletor de motor."""
import numpy as np
import pytest

pytest.importorskip("tensorflow")

from core import neural_backend as nb          # noqa: E402
from core import neural_engine as npe          # noqa: E402
from core import keras_engine as ke            # noqa: E402


def _tabela(n=60, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for lab, (cx, cy) in zip("ABC", [(0, 0), (5, 5), (-5, 5)]):
        for _ in range(n):
            rows.append([f"{cx + rng.normal(0, 1):.2f}", f"{cy + rng.normal(0, 1):.2f}", lab])
    rng.shuffle(rows)
    return ["x1", "x2", "y"], rows


@pytest.mark.parametrize("act", list(npe.ACTIVATIONS))
def test_pesos_numpy_ida_e_volta(act):
    rng = np.random.default_rng(1)
    a = npe.MLP([3, 5, 4, 2], act, seed=3)
    k = ke.MLP.from_arrays([3, 5, 4, 2], act, a.W, a.b)
    X = rng.normal(size=(7, 3))
    assert np.abs(a.predict(X) - k.predict(X)).max() < 1e-4
    b = npe.MLP.from_arrays([3, 5, 4, 2], act, [np.asarray(w) for w in k.W], [np.asarray(x) for x in k.b])
    assert np.abs(a.predict(X) - b.predict(X)).max() < 1e-4


def test_treino_classifica_e_modelo_abre_nos_dois_motores():
    header, rows = _tabela()
    opts = {"epochs": 60, "ensemble": 1, "search": "off", "budget_s": 60}
    model, rep = ke.train_pipeline(header, rows, opts)
    assert rep["backend"] == "keras" and model["backend"] == "keras"
    assert rep["metrics"]["test"]["accuracy"] > 0.9
    linhas = [["0.1", "0.0"], ["5.0", "5.1"], ["-5.0", "4.9"]]
    a, b = ke.Predictor(model), npe.Predictor(model)       # o mesmo modelo, lido pelos dois motores
    for r, esperado in zip(linhas, "ABC"):
        ra, rb = a.predict_row(r), b.predict_row(r)
        assert ra["label"] == rb["label"] == esperado
        assert abs(ra["confidence"] - rb["confidence"]) < 1e-3


def test_finetune_distill_compress():
    header, rows = _tabela()
    model, _ = ke.train_pipeline(header, rows, {"epochs": 40, "ensemble": 1, "search": "off"})
    novo, _ = ke.finetune(model, header, rows, epochs=10, freeze=1)
    assert novo
    aluno, _ = ke.distill(model, header, rows, epochs=20)
    assert aluno
    comp, info = ke.compress(model, header, rows, sparsity=0.5)
    assert comp and info


def test_export_keras(tmp_path):
    header, rows = _tabela(30)
    model, _ = ke.train_pipeline(header, rows, {"epochs": 10, "ensemble": 1, "search": "off"})
    path = ke.export_keras(model, tmp_path / "m.keras")
    assert path.endswith(".keras") and (tmp_path / "m.keras").exists()


def test_intent_roundtrip_npz(tmp_path):
    from core import intent_net as inn
    from core.keras_intent import KerasIntentMLP
    sizes = (inn.DIM, 16, 8, 4)
    a = inn.IntentMLP(sizes)
    k = KerasIntentMLP(sizes)
    k.p = a.p
    X = np.random.default_rng(0).normal(size=(5, inn.DIM)).astype(np.float32)
    assert np.abs(a.logits(X) - k.logits(X)).max() < 1e-3
    f = tmp_path / "n.npz"
    k.save(f, {"x": 1})
    b, meta = inn.IntentMLP.load(f)
    assert meta == {"x": 1} and np.abs(b.logits(X) - k.logits(X)).max() < 1e-3


def test_selecao_de_motor(monkeypatch):
    try:
        nb.forcar("numpy")
        assert nb.nome() == "numpy" and not nb.keras_provavel()
        nb.forcar("keras")
        assert nb.nome() == "keras" and nb.usar_keras()
        assert "TensorFlow" in nb.descricao()
    finally:
        nb.forcar("auto")
