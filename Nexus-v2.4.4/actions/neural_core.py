"""Neural Core — uma rede neural de verdade, treinada do zero (NumPy puro).

O motor está em core/neural_engine.py (camadas independentes: dados, rede,
treino, busca, ensemble, compressão). Este arquivo é a ponta: lê CSV, guarda os
modelos em memory/neural_models/, escreve relatórios e atende a ferramenta.

  Dataset: texto CSV (vírgula ou ponto e vírgula), última coluna = alvo.
  Alvo numérico → regressão, texto → classificação. Colunas de texto viram
  one-hot, células vazias são tratadas, duplicatas removidas.

  Ações: train · predict · explain · finetune · distill · compress · augment ·
         report · monitor · history · list · demo
"""

import html
import json
import time
from pathlib import Path

import numpy as np

from core import neural_engine as eng

_MODELS_DIR = Path(__file__).resolve().parent.parent / "memory" / "neural_models"
_SEED = 42
_MONITOR_MAX = 2000


# ── dados ─────────────────────────────────────────────────────────────────────

def _is_num(s: str) -> bool:
    try:
        float(s.replace(",", "."))
        return True
    except ValueError:
        return False


def parse_table(text: str):
    """CSV → (header|None, linhas de texto). Detecta separador e cabeçalho."""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if len(lines) < 3:
        raise ValueError("dataset needs at least 3 rows")
    sep = ";" if lines[0].count(";") >= lines[0].count(",") else ","
    table = [[c.strip() for c in l.split(sep)] for l in lines]
    header = None
    if all(not _is_num(c) for c in table[0]) and len(table) > 3 \
            and any(_is_num(c) for c in table[1]):
        header, table = table[0], table[1:]
    width = len(table[0])
    if width < 2:
        raise ValueError("each row needs at least feature,target columns")
    bad = [i for i, r in enumerate(table) if len(r) != width]
    if bad:
        raise ValueError(f"row {bad[0] + 1} has {len(table[bad[0]])} "
                         f"columns, expected {width}")
    return header, table


def parse_dataset(text: str) -> dict:
    """Compatível com a versão antiga: só features numéricas."""
    header, table = parse_table(text)
    try:
        feats = np.array([[float(c.replace(",", ".")) for c in r[:-1]] for r in table])
    except ValueError as e:
        raise ValueError(f"features must be numeric — {e}")
    return {"features": feats, "target_raw": [r[-1] for r in table], "header": header}


def _name_of(model_name: str, default: str = "") -> str:
    return (model_name.strip().lower().replace(" ", "_")
            or default or f"model_{time.strftime('%Y%m%d_%H%M%S')}")


def _save(model: dict, name: str) -> None:
    model["name"] = name
    _MODELS_DIR.mkdir(parents=True, exist_ok=True)
    (_MODELS_DIR / f"{name}.json").write_text(json.dumps(model), encoding="utf-8")


def _load(name: str) -> dict:
    path = _MODELS_DIR / f"{name.strip().lower().replace(' ', '_')}.json"
    if not path.exists():
        raise ValueError(f"model '{name}' not found")
    return json.loads(path.read_text(encoding="utf-8"))


def _log_experiment(name: str, kind: str, report: dict) -> None:
    """Diário de experimentos (o "TensorBoard" local): uma linha por treino."""
    try:
        _MODELS_DIR.mkdir(parents=True, exist_ok=True)
        m = (report.get("metrics") or {}).get("test") or {}
        rec = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "model": name, "kind": kind,
               "task": report.get("task"), "config": report.get("config"),
               "ensemble": report.get("ensemble"), "test": m,
               "quality": report.get("quality"), "seconds": report.get("seconds")}
        with open(_MODELS_DIR / "experiments.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")
    except Exception:
        pass


def _write_report(name: str, model: dict, report: dict) -> str:
    """Relatório HTML (curvas de perda, importância, ranking da busca)."""
    h = report.get("history") or {}
    def poly(vals, color, w=520, hgt=160):
        if len(vals) < 2:
            return ""
        lo, hi = min(vals), max(vals)
        rng_ = (hi - lo) or 1.0
        pts = " ".join(f"{i / (len(vals) - 1) * w:.1f},{hgt - (v - lo) / rng_ * (hgt - 8) - 4:.1f}"
                       for i, v in enumerate(vals))
        return f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{pts}"/>'
    imp = report.get("importance") or []
    mx = max([abs(v) for _, v in imp] + [1e-9])
    bars = "".join(
        f'<div class="r"><span>{html.escape(str(n))}</span><i style="width:{max(2, abs(v) / mx * 260):.0f}px"></i>'
        f'<b>{v:+.3f}</b></div>' for n, v in imp[:15])
    board = "".join(f"<tr><td>{s}</td><td>{html.escape(json.dumps(c))}</td></tr>"
                    for s, c in report.get("leaderboard", []))
    met = json.dumps(report.get("metrics"), indent=1, default=str)
    doc = f"""<!doctype html><meta charset="utf-8"><title>{html.escape(name)}</title>
<style>body{{background:#0a0b1e;color:#dfe6ff;font:14px Segoe UI,sans-serif;margin:24px}}
h1{{color:#3ee0ff}}h2{{color:#8b6bff;margin-top:26px}}pre{{background:#10122c;padding:10px;border-radius:8px}}
.r{{display:flex;align-items:center;gap:8px;margin:3px 0}}.r span{{width:150px}}
.r i{{display:block;height:10px;background:linear-gradient(90deg,#3ee0ff,#8b6bff);border-radius:5px}}
td{{padding:3px 10px;border-bottom:1px solid #223}}svg{{background:#10122c;border-radius:8px}}</style>
<h1>{html.escape(name)}</h1>
<p>{html.escape(report.get('quality',''))}{html.escape(report.get('held_out',''))}</p>
<p>Ensemble: {report.get('ensemble')} · amostras: {report.get('samples')} ·
features: {report.get('features')} → {report.get('encoded_features')} · sintéticas: {report.get('synthetic_added')}
· poda: {report.get('sparsity', 0) * 100:.0f}% · {report.get('seconds')}s</p>
<h2>Curvas de perda</h2>
<svg width="520" height="160">{poly(h.get('train', []), '#3ee0ff')}{poly(h.get('val', []), '#ff7a45')}</svg>
<p><span style="color:#3ee0ff">■ treino</span> &nbsp; <span style="color:#ff7a45">■ validação</span>
(melhor época: {h.get('best_epoch')}, rodou {h.get('epochs_run')})</p>
<h2>O que mais pesa (importância por permutação)</h2>{bars or '<p>—</p>'}
<h2>Configuração</h2><pre>{html.escape(json.dumps(report.get('config'), indent=1, default=str))}</pre>
<h2>Ranking da busca</h2><table>{board or '<tr><td>sem busca</td></tr>'}</table>
<h2>Métricas</h2><pre>{html.escape(met)}</pre>"""
    path = _MODELS_DIR / f"{name}_report.html"
    _MODELS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(doc, encoding="utf-8")
    return str(path)


# ── treino / previsão ─────────────────────────────────────────────────────────

def train_dataset(dataset_text: str, model_name: str = "", hidden=None,
                  epochs=300, lr=None, **opts) -> dict:
    """Treina em texto CSV; salva o modelo e devolve o relatório.

    opts: activation, optimizer, schedule, batch, l2, dropout, noise, patience,
    balance, synthetic, ensemble, search, trials, budget_s, auto, compress, task, seed."""
    header, rows = parse_table(dataset_text)
    model, rep = eng.train_pipeline(header, rows, {"hidden": hidden, "epochs": epochs,
                                                     "lr": lr, **opts})
    name = _name_of(model_name)
    _save(model, name)
    rep["name"] = name
    rep["header"] = header
    rep["report_file"] = _write_report(name, model, rep)
    _log_experiment(name, "auto" if rep["auto"] else "train", rep)
    return rep


def _net_from(model: dict):
    """Compatibilidade: devolve a primeira rede do modelo."""
    return eng.Predictor(model).nets[0]


def predict(model_name: str, features, log_use: bool = True) -> dict:
    """features: lista de valores (números ou texto) → previsão com o modelo salvo."""
    model = _load(model_name)
    pred = eng.Predictor(model)
    if len(features) != len(pred.prep.cols):
        raise ValueError(f"model expects {len(pred.prep.cols)} features, "
                         f"got {len(features)}")
    r = pred.predict_row(list(features))
    if log_use:
        _monitor_write(model_name, r)
    r.pop("_x", None); r.pop("_p", None)
    return r


def explain(model_name: str, features, top=5) -> dict:
    model = _load(model_name)
    pred = eng.Predictor(model)
    if len(features) != len(pred.prep.cols):
        raise ValueError(f"model expects {len(pred.prep.cols)} features, got {len(features)}")
    r = pred.predict_row(list(features))
    return {"prediction": {k: v for k, v in r.items() if not k.startswith("_")},
            "drivers": pred.explain_row(list(features), top)}


def _monitor_path(name: str) -> Path:
    return _MODELS_DIR / f"{_name_of(name)}.monitor.jsonl"


def _monitor_write(name: str, r: dict) -> None:
    try:
        p = _monitor_path(name)
        _MODELS_DIR.mkdir(parents=True, exist_ok=True)
        rec = {"t": int(time.time()), "x": [round(float(v), 3) for v in r["_x"]],
               "conf": r.get("confidence")}
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        lines = p.read_text(encoding="utf-8").splitlines()
        if len(lines) > _MONITOR_MAX * 1.5:
            p.write_text("\n".join(lines[-_MONITOR_MAX:]) + "\n", encoding="utf-8")
    except Exception:
        pass


def monitor(model_name: str) -> dict:
    model = _load(model_name)
    p = _monitor_path(model_name)
    logs = []
    if p.exists():
        for l in p.read_text(encoding="utf-8").splitlines()[-500:]:
            try:
                logs.append(json.loads(l))
            except ValueError:
                pass
    return eng.drift_report(model, logs)


def history(limit=8) -> list:
    p = _MODELS_DIR / "experiments.jsonl"
    if not p.exists():
        return []
    out = []
    for l in p.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(l))
        except ValueError:
            pass
    return out


def list_models() -> list:
    if not _MODELS_DIR.is_dir():
        return []
    out = []
    for p in sorted(_MODELS_DIR.glob("*.json")):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
            out.append({"name": m["name"], "task": m["task"],
                        "quality": m.get("quality", "?"),
                        "created": m.get("created", "?"),
                        "ensemble": m.get("ensemble", 1)})
        except Exception:
            continue
    return out


def _demo_dataset() -> str:
    """3 gaussian blobs, 2 features, 150 rows — proves the net learns."""
    rng = np.random.default_rng(_SEED)
    centers = [(0, 0), (4, 4), (-4, 4)]
    lines = ["x1,x2,cluster"]
    for label, (cx, cy) in zip("ABC", centers):
        for _ in range(50):
            x1 = cx + rng.normal(0, 1.2)
            x2 = cy + rng.normal(0, 1.2)
            lines.append(f"{x1:.2f},{x2:.2f},{label}")
    return "\n".join(lines)


# ── handler ────────────────────────────────────────────────────────────────────

def _read_data(parameters):
    text = str(parameters.get("dataset") or "").strip()
    path = str(parameters.get("file_path") or "").strip()
    if not text and path:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    return text


def _opts(parameters: dict) -> dict:
    """Parâmetros da ferramenta → opções do motor (só o que foi informado)."""
    o = {}
    for k in ("activation", "optimizer", "schedule", "balance", "search", "task"):
        if parameters.get(k):
            o[k] = str(parameters[k]).strip().lower()
    for k, cast in (("batch_size", int), ("l2", float), ("dropout", float),
                    ("noise", float), ("patience", int), ("synthetic", float),
                    ("ensemble", int), ("trials", int), ("compress", float),
                    ("seed", int)):
        if parameters.get(k) not in (None, ""):
            o["batch" if k == "batch_size" else k] = cast(parameters[k])
    if parameters.get("auto") not in (None, ""):
        o["auto"] = str(parameters["auto"]).strip().lower() in ("1", "true", "yes", "sim")
    return o


def _pct(d, k):
    return f"{d[k] * 100:.0f}%" if d and k in d else "n/a"


def _train_msg(rep: dict) -> str:
    kind = ("regression" if rep["task"] == "regression"
            else f"{len(rep['classes'])} classes")
    cfg = rep["config"]
    msg = (f"Sir, neural network trained: model '{rep['name']}', "
           f"{rep['samples']} samples, {rep['features']} features, {kind}. "
           f"{rep['quality']}{rep['held_out']}. ")
    msg += (f"Architecture {cfg['hidden']} · {cfg['activation']} · {cfg['optimizer']}"
            f" · {rep['ensemble']} network(s)")
    h = rep.get("history") or {}
    if h.get("stopped_early"):
        msg += f", early-stopped at epoch {h['epochs_run']} (best {h['best_epoch'] + 1})"
    msg += ". "
    if rep.get("synthetic_added"):
        msg += f"Added {rep['synthetic_added']} synthetic samples. "
    if rep.get("balance") == "weights":
        msg += "Class weights balanced the data. "
    if rep.get("sparsity"):
        msg += f"Pruned {rep['sparsity'] * 100:.0f}% of the weights. "
    if rep.get("leaderboard"):
        msg += "Hyper-parameter search compared several setups and kept the best. "
    if rep.get("importance"):
        top = ", ".join(f"{n} ({v:+.2f})" for n, v in rep["importance"][:3])
        msg += f"Most influential inputs: {top}. "
    msg += f"Report: {rep['report_file']}"
    return msg


def neural_core_action(parameters: dict, player=None, session_memory=None) -> str:
    action = str(parameters.get("action") or "").strip().lower()
    try:
        return _dispatch(action, parameters, player)
    except ValueError as e:
        msg = f"Sir, I couldn't do that: {e}"
        _log(msg, player)
        return msg
    except OSError as e:
        msg = f"Sir, file problem: {e}"
        _log(msg, player)
        return msg


def _hidden_param(parameters):
    h = parameters.get("hidden")
    if isinstance(h, str) and h.strip() and h.strip().lower() not in eng.SIZE_PRESETS:
        h = [p for p in h.replace(";", ",").split(",") if p.strip()]
    return h


def _features_param(parameters):
    feats = parameters.get("features")
    if isinstance(feats, str):
        feats = [f.strip() for f in feats.replace(";", ",").split(",") if f.strip()]
    if not feats:
        raise ValueError("give me the feature values")
    return feats


def _model_name(parameters):
    name = str(parameters.get("model_name") or "").strip()
    if not name:
        models = list_models()
        name = models[0]["name"] if models else ""
    return name


def _dispatch(action: str, parameters: dict, player) -> str:
    if action == "demo":
        rep = train_dataset(_demo_dataset(), model_name="demo", epochs=300)
        p = predict("demo", [0.0, 0.0], log_use=False)
        msg = (f"Sir, I trained a fresh neural network on the built-in demo "
               f"dataset — 150 samples, 2 features, 3 classes. "
               f"{rep['quality']}{rep['held_out']}. A point at (0, 0) reads "
               f"as '{p['label']}' with {p['confidence'] * 100:.0f}% "
               f"confidence. The model 'demo' is saved.")
        _log(f"demo trained: {rep['quality']}", player)
        return msg

    if action == "train":
        text = _read_data(parameters)
        if not text:
            msg = ("Sir, give me the dataset — CSV text or a file path. "
                   "Last column is the target.")
            _log(msg, player); return msg
        rep = train_dataset(text, parameters.get("model_name") or "",
                            _hidden_param(parameters),
                            int(parameters.get("epochs") or 300),
                            float(parameters["learning_rate"])
                            if parameters.get("learning_rate") else None,
                            **_opts(parameters))
        _log(f"trained '{rep['name']}': {rep['quality']}", player)
        return _train_msg(rep)

    if action == "predict":
        name = _model_name(parameters)
        feats = _features_param(parameters)
        r = predict(name, feats)
        if r["task"] == "classification":
            msg = (f"Sir, prediction: '{r['label']}' — "
                   f"{r['confidence'] * 100:.0f}% confident")
            if r.get("runner_up"):
                msg += (f" (runner-up '{r['runner_up'][0]}' "
                        f"{r['runner_up'][1] * 100:.0f}%)")
            if r.get("members", 1) > 1:
                msg += f"; {r['members']} networks voted, spread {r['spread'] * 100:.0f}%"
            msg += "."
        else:
            msg = f"Sir, predicted value: {r['value']:.2f}."
            if r.get("members", 1) > 1:
                msg += f" ({r['members']} networks, spread ±{r['spread']:.2f})"
        _log(f"predict '{name}' → {r}", player)
        return msg

    if action == "explain":
        name = _model_name(parameters)
        r = explain(name, _features_param(parameters))
        pr = r["prediction"]
        head = (f"'{pr['label']}' ({pr['confidence'] * 100:.0f}%)"
                if pr["task"] == "classification" else f"{pr['value']:.2f}")
        parts = ", ".join(f"{n} {'pushed it up' if d > 0 else 'pulled it down'} "
                          f"({d:+.2f})" for n, d in r["drivers"])
        msg = f"Sir, the model says {head}. What drove that: {parts}."
        _log(f"explain '{name}'", player)
        return msg

    if action in ("finetune", "distill", "compress"):
        name = _model_name(parameters)
        model = _load(name)
        text = _read_data(parameters)
        header, rows = parse_table(text) if text else (None, None)
        out_name = _name_of(str(parameters.get("output_name") or ""),
                            f"{name}_{ {'finetune': 'ft', 'distill': 'student', 'compress': 'small'}[action] }")
        if action == "finetune":
            if not rows:
                raise ValueError("fine-tuning needs new data (dataset or file_path)")
            lr = float(parameters["learning_rate"]) if parameters.get("learning_rate") else None
            new, info = eng.finetune(model, header, rows,
                                     int(parameters.get("epochs") or 80), lr,
                                     int(parameters.get("freeze") or 0))
            acc_key = "accuracy" if model["task"] == "classification" else "r2"
            msg = (f"Sir, I fine-tuned '{name}' on {info['samples']} new samples "
                   f"({info['frozen']} layer(s) frozen) and saved it as '{out_name}'. "
                   f"Held-out {acc_key}: {info['before'].get(acc_key, float('nan')):.2f} → "
                   f"{info['after'].get(acc_key, float('nan')):.2f}.")
        elif action == "distill":
            if not rows:
                raise ValueError("distillation needs data (dataset or file_path)")
            new, info = eng.distill(model, header, rows, _hidden_param(parameters),
                                    int(parameters.get("epochs") or 300))
            msg = (f"Sir, distilled '{name}' into a student with layers {info['hidden']}: "
                   f"{info['student_params']} parameters instead of {info['teacher_params']}, "
                   f"saved as '{out_name}'.")
            if "agreement" in info:
                msg += (f" It agrees with the teacher on {info['agreement'] * 100:.0f}% of cases; "
                        f"accuracy {_pct(info['student'], 'accuracy')} vs "
                        f"{_pct(info['teacher'], 'accuracy')}.")
        else:
            sp = float(parameters.get("compress") or parameters.get("sparsity") or 0.5)
            new, info = eng.compress(model, header, rows, sp)
            msg = (f"Sir, pruned {info['sparsity'] * 100:.0f}% of the weights of '{name}' "
                   f"and saved it as '{out_name}'.")
            if info["after"]:
                k = "accuracy" if model["task"] == "classification" else "r2"
                msg += f" {k}: {info['before'][k]:.2f} → {info['after'][k]:.2f}."
        new["quality"] = model.get("quality", "?") + f" ({action})"
        new["created"] = time.strftime("%Y-%m-%d %H:%M")
        _save(new, out_name)
        _log(f"{action} '{name}' → '{out_name}'", player)
        return msg

    if action == "augment":
        text = _read_data(parameters)
        if not text:
            raise ValueError("give me the dataset to augment")
        header, rows = parse_table(text)
        extra = eng.synthesize(header, rows, float(parameters.get("synthetic") or 0.5))
        sep = ","
        lines = ([sep.join(header)] if header else []) + [sep.join(r) for r in rows] \
            + [sep.join(r) for r in extra]
        out = Path(str(parameters.get("output_path") or "")) if parameters.get("output_path") \
            else _MODELS_DIR / f"dataset_aumentado_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        msg = (f"Sir, I generated {len(extra)} synthetic samples (SMOTE interpolation) "
               f"and saved the enlarged dataset of {len(rows) + len(extra)} rows at {out}.")
        _log(msg, player)
        return msg

    if action == "report":
        name = _model_name(parameters)
        path = _MODELS_DIR / f"{name}_report.html"
        if not path.exists():
            raise ValueError(f"no report for '{name}' — train it first")
        msg = f"Sir, the report with curves and input importance is at {path}."
        _log(msg, player)
        return msg

    if action == "monitor":
        name = _model_name(parameters)
        r = monitor(name)
        if not r["enough"]:
            msg = (f"Sir, only {r['n']} predictions logged for '{name}' — I need at "
                   f"least 5 to judge drift.")
        elif r["alerts"]:
            msg = f"Sir, '{name}' needs attention: " + "; ".join(r["alerts"]) + "."
        else:
            msg = f"Sir, '{name}' looks healthy over its last {r['n']} predictions."
            if "conf_now" in r:
                msg += f" Confidence {r['conf_now'] * 100:.0f}% (training {r['conf_base'] * 100:.0f}%)."
        _log(f"monitor '{name}'", player)
        return msg

    if action == "history":
        h = history()
        if not h:
            msg = "Sir, no experiments logged yet."
        else:
            msg = "Sir, last experiments: " + " | ".join(
                f"{e['t'][5:16]} {e['model']} [{e['kind']}] {e.get('quality', '')}" for e in h)
        _log("history", player)
        return msg

    if action == "list":
        models = list_models()
        if not models:
            msg = ("Sir, no trained models yet — train one or ask for the "
                   "demo.")
        else:
            lines = [f"{m['name']} ({m['task']}, {m['quality']}"
                     f"{', ' + str(m['ensemble']) + ' nets' if m.get('ensemble', 1) > 1 else ''})"
                     for m in models]
            msg = "Sir, trained models: " + " | ".join(lines)
        _log("list models", player)
        return msg

    msg = ("Sir, the neural core can: train (with layers, activations, optimizers, "
           "early stopping, search/AutoML, ensembles), predict, explain a prediction, "
           "fine-tune, distill, compress, augment a dataset, show a report, monitor "
           "drift, show experiment history, list models, or run the demo.")
    _log(msg, player)
    return msg


def _log(message: str, player=None) -> None:
    print(f"[NeuralCore] {message}")
    if player:
        try:
            player.write_log(f"NEXUS: {message}")
        except Exception:
            pass


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
def _s(desc):
    return {"type": "STRING", "description": desc}


def _n(desc):
    return {"type": "NUMBER", "description": desc}


TOOL = {
    "name": "neural_core",
    "description": (
        "A real neural network (multilayer perceptron in pure NumPy, trained "
        "locally). Train it on the user's CSV (last column = target; text = "
        "classification, number = regression; text columns and blanks are "
        "handled). Options: hidden layers/neurons, 7 activations, 6 optimizers "
        "(sgd/momentum/nesterov/rmsprop/adam/adamw), learning-rate schedules, "
        "batch size, L2/dropout regularisation, noise augmentation, early "
        "stopping, class balancing, synthetic data (SMOTE), ensembles, "
        "grid/random hyper-parameter search and full AutoML (auto=true). "
        "Also: predict, explain a prediction, fine-tune a saved model on new "
        "data, distil it into a small student, prune/compress it, augment a "
        "CSV, write an HTML report, monitor drift in production, list "
        "experiments and models, and run a demo."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING",
                       "enum": ["train", "predict", "explain", "finetune", "distill",
                                "compress", "augment", "report", "monitor", "history",
                                "list", "demo"],
                       "description": "What to do (train = learn from CSV; auto=true "
                                      "makes train search the best setup itself)"},
            "dataset": _s("CSV text (comma or semicolon separated); last column is the target"),
            "file_path": _s("Alternative to dataset: path to a CSV file"),
            "model_name": _s("Name to save/find the model (optional)"),
            "output_name": _s("Name for the new model made by finetune/distill/compress"),
            "features": _s("For predict/explain: comma-separated values (numbers or text)"),
            "hidden": _s("Hidden layers, e.g. '64,32,16', or small/medium/large/deep"),
            "activation": _s("relu, leaky_relu, tanh, sigmoid, elu, gelu or swish"),
            "optimizer": _s("sgd, momentum, nesterov, rmsprop, adam or adamw"),
            "schedule": _s("Learning-rate schedule: constant, step, exp, cosine, warmup_cosine, plateau"),
            "epochs": _n("Training passes (default 300; finetune 80)"),
            "learning_rate": _n("Step size (default depends on the optimizer)"),
            "batch_size": _n("Mini-batch size (0 = whole dataset; default 32)"),
            "l2": _n("L2 weight regularisation (default 1e-4)"),
            "dropout": _n("Dropout rate 0–0.5 against overfitting"),
            "noise": _n("Gaussian noise added to inputs while training (augmentation)"),
            "patience": _n("Early stopping patience in epochs (default 25)"),
            "balance": _s("Imbalanced classes: none, weights or oversample"),
            "synthetic": _n("Fraction of synthetic rows to add (SMOTE), e.g. 0.5; for augment too"),
            "ensemble": _n("How many networks to combine (1–10)"),
            "search": _s("Hyper-parameter search: none, random or grid"),
            "trials": _n("Number of search trials (default 12)"),
            "auto": {"type": "BOOLEAN", "description": "AutoML: search + balance + ensemble of the best"},
            "compress": _n("Fraction of weights to prune after training (0–0.95)"),
            "freeze": _n("finetune: how many first layers to keep frozen"),
            "task": _s("Force classification or regression (default: automatic)"),
        },
        "required": ["action"]
    },
    "handler": neural_core_action,
}
