"""Train, evaluate and use a small TensorFlow network on official UCI Iris data."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
CLASS_NAMES = ["Iris-setosa", "Iris-versicolor", "Iris-virginica"]
FEATURE_NAMES = ["sepal length", "sepal width", "petal length", "petal width"]
DATA_SHA256 = "daaeb5e3e889d07fbdd44544f5a39fe2372a07172e25899d577be0ad74df9e65"


def save_json(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_data(path=ROOT / "data/iris.csv"):
    path = Path(path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != DATA_SHA256:
        raise ValueError("Data checksum differs from the recorded official UCI CSV")
    with path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    x = np.asarray([[float(r[k]) for k in FEATURE_NAMES] for r in rows], dtype=np.float32)
    y = np.asarray([CLASS_NAMES.index(r["class"]) for r in rows], dtype=np.int64)
    if x.shape != (150, 4) or not np.isfinite(x).all() or np.any(x <= 0):
        raise ValueError("Unexpected Iris dimensions or measurements")
    return x, y


def split_indices(y, seed=42):
    """60/20/20 split; test data never participate in scaling or stopping."""
    dev, test = train_test_split(np.arange(len(y)), test_size=0.2, stratify=y, random_state=seed)
    train, val = train_test_split(dev, test_size=0.25, stratify=y[dev], random_state=seed)
    return {"train": train, "validation": val, "test": test}


def tensorflow():
    import tensorflow as tf
    try:
        tf.config.threading.set_intra_op_parallelism_threads(1)
        tf.config.threading.set_inter_op_parallelism_threads(1)
    except RuntimeError:
        pass  # Runtime already configured in this process.
    tf.config.experimental.enable_op_determinism()
    return tf


def build_model(seed=42, hidden=(16, 8), l2=1e-4):
    tf = tensorflow()
    tf.keras.backend.clear_session()
    tf.keras.utils.set_random_seed(seed)
    model = tf.keras.Sequential([tf.keras.Input(shape=(4,), name="measurements")])
    for i, units in enumerate(hidden):
        model.add(tf.keras.layers.Dense(units, activation="relu", kernel_regularizer=tf.keras.regularizers.l2(l2), name=f"hidden_{i+1}"))
    model.add(tf.keras.layers.Dense(3, activation="softmax", name="species"))
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=0.01),
                  loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    return model


def make_dataset(x, y, training=False, seed=42):
    tf = tensorflow()
    ds = tf.data.Dataset.from_tensor_slices((x.astype(np.float32), y))
    if training:
        ds = ds.shuffle(len(y), seed=seed, reshuffle_each_iteration=True)
    opts = tf.data.Options()
    opts.threading.private_threadpool_size = 1
    opts.threading.max_intra_op_parallelism = 1
    return ds.batch(16).with_options(opts)


def fit_network(x_train, y_train, x_val, y_val, seed=42, hidden=(16, 8), epochs=400):
    tf = tensorflow()
    model = build_model(seed, hidden)
    stop = tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=35,
                                           min_delta=1e-5, restore_best_weights=True)
    start, cpu_start = time.perf_counter(), time.process_time()
    hist = model.fit(make_dataset(x_train, y_train, True, seed),
                     validation_data=make_dataset(x_val, y_val),
                     epochs=epochs, callbacks=[stop], verbose=0)
    timing = {"training_wall_seconds": time.perf_counter()-start,
              "training_cpu_seconds": time.process_time()-cpu_start}
    return model, hist.history, timing


def score(y, predicted):
    return {"accuracy": float(accuracy_score(y, predicted)),
            "macro_f1": float(f1_score(y, predicted, average="macro", zero_division=0)),
            "confusion_matrix": confusion_matrix(y, predicted, labels=[0, 1, 2]).tolist(),
            "classification_report": classification_report(y, predicted, labels=[0, 1, 2],
                 target_names=CLASS_NAMES, output_dict=True, zero_division=0)}


def train(output=ROOT / "artifacts", epochs=400):
    tf = tensorflow()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    x, y = load_data()
    ix = split_indices(y)
    train_i, val_i, test_i = [ix[k] for k in ["train", "validation", "test"]]
    scaler = StandardScaler().fit(x[train_i])
    z = scaler.transform(x).astype(np.float32)
    model, history, timing = fit_network(z[train_i], y[train_i], z[val_i], y[val_i], epochs=epochs)
    # The main architecture is predeclared; no model selection uses test labels.
    model.save(output / "iris_mlp.keras")
    probabilities = model(z[test_i], training=False).numpy()
    predicted = probabilities.argmax(axis=1)
    metrics = score(y[test_i], predicted)
    metrics.update(timing)
    metrics.update({"split_seed": 42, "model_seed": 42, "parameter_count": model.count_params(),
                    "epochs_run": len(history["loss"]),
                    "best_epoch": int(np.argmin(history["val_loss"])+1),
                    "validation_accuracy": float(accuracy_score(y[val_i], model(z[val_i], training=False).numpy().argmax(axis=1))),
                    "test_size": len(test_i), "test_correct": int(np.sum(predicted == y[test_i])),
                    "data_sha256": DATA_SHA256,
                    "model_bytes": (output / "iris_mlp.keras").stat().st_size})
    save_json(output / "metrics.json", metrics)
    save_json(output / "split_indices.json", {k: v.tolist() for k, v in ix.items()})
    save_json(output / "preprocessing.json", {"mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(),
        "minimum": x[train_i].min(axis=0).tolist(), "maximum": x[train_i].max(axis=0).tolist(),
        "feature_names": FEATURE_NAMES, "feature_units": "cm", "class_names": CLASS_NAMES})
    save_json(output / "environment.json", {"python": platform.python_version(), "tensorflow": tf.__version__,
        "keras": tf.keras.__version__, "numpy": np.__version__, "platform": platform.platform(),
        "processor": platform.processor(), "training_device": "CPU", "tensorflow_threads": 1})
    with (output / "history.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file); writer.writerow(["epoch", *history.keys()])
        writer.writerows([i+1, *[history[k][i] for k in history]] for i in range(len(history["loss"])))
    with (output / "test_predictions.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["row_index_zero_based", *FEATURE_NAMES, "true_class", "predicted_class", *["p_"+n for n in CLASS_NAMES]])
        for row, pred, prob in zip(test_i, predicted, probabilities):
            writer.writerow([int(row), *x[row].tolist(), CLASS_NAMES[y[row]], CLASS_NAMES[pred], *prob.tolist()])
    lines=[]
    model.summary(print_fn=lambda line: lines.append(line))
    (output / "model_summary.txt").write_text("\n".join(lines)+"\n", encoding="utf-8")

    experiments = {"protocol": "Predeclared main model; baselines share splits; ablations and seed analysis use validation only.", "baselines": {}, "ablations": [], "initialization_seeds": []}
    for name, clf in [("majority", DummyClassifier(strategy="most_frequent")),
                      ("logistic_regression", LogisticRegression(C=1.0, max_iter=1000, random_state=42))]:
        clf.fit(z[train_i], y[train_i])
        experiments["baselines"][name] = score(y[test_i], clf.predict(z[test_i]))
    for name, features, hidden in [("unscaled_two_hidden", x, (16, 8)), ("scaled_one_hidden", z, (8,))]:
        m, h, t = fit_network(features[train_i], y[train_i], features[val_i], y[val_i], hidden=hidden, epochs=epochs)
        experiments["ablations"].append({"name": name, "validation_accuracy": float(accuracy_score(y[val_i], m(features[val_i], training=False).numpy().argmax(axis=1))),
           "parameters": m.count_params(), "epochs_run": len(h["loss"]), **t})
    # Fixed data split; only initialization and minibatch randomness change.
    for seed in [7, 21, 42, 87, 2026]:
        if seed == 42:
            acc = metrics["validation_accuracy"]
        else:
            m, _, _ = fit_network(z[train_i], y[train_i], z[val_i], y[val_i], seed=seed, epochs=epochs)
            acc = float(accuracy_score(y[val_i], m(z[val_i], training=False).numpy().argmax(axis=1)))
        experiments["initialization_seeds"].append({"seed": seed, "validation_accuracy": acc})
    values = [v["validation_accuracy"] for v in experiments["initialization_seeds"]]
    experiments["validation_seed_mean"] = float(np.mean(values))
    experiments["validation_seed_sample_std"] = float(np.std(values, ddof=1))
    save_json(output / "experiments.json", experiments)
    print(json.dumps({"test_accuracy": metrics["accuracy"], "macro_f1": metrics["macro_f1"],
                      "correct": metrics["test_correct"], "test_size": len(test_i),
                      "epochs": metrics["epochs_run"], "best_epoch": metrics["best_epoch"]}, indent=2))
    return metrics


def validate_measurements(values):
    try:
        x = np.asarray(values, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        raise ValueError("Measurements must be numeric") from exc
    if x.shape != (4,) or not np.isfinite(x).all() or np.any(x <= 0):
        raise ValueError("Supply exactly four finite positive measurements in cm")
    return x


def predict(values, artifacts=ROOT / "artifacts"):
    tf = tensorflow()
    x = validate_measurements(values)
    artifacts = Path(artifacts)
    prep = json.loads((artifacts / "preprocessing.json").read_text(encoding="utf-8"))
    scaled = ((x-np.array(prep["mean"]))/np.array(prep["scale"])).astype(np.float32)
    model = tf.keras.models.load_model(artifacts / "iris_mlp.keras", compile=False)
    p = model(scaled[None], training=False).numpy()[0]
    outside = bool(np.any(x < prep["minimum"]) or np.any(x > prep["maximum"]))
    return {"class": CLASS_NAMES[int(p.argmax())], "probabilities": dict(zip(CLASS_NAMES, map(float, p))),
            "review_recommended": bool(p.max() < 0.8 or outside), "outside_training_range": outside,
            "note": "Softmax scores are not calibrated real-world confidence; measurements are in cm."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    train_parser = sub.add_parser("train")
    train_parser.add_argument("--output", type=Path, default=ROOT / "artifacts")
    train_parser.add_argument("--epochs", type=int, default=400)
    predict_parser = sub.add_parser("predict")
    predict_parser.add_argument("measurements", type=float, nargs=4)
    predict_parser.add_argument("--artifacts", type=Path, default=ROOT / "artifacts")
    args = parser.parse_args()
    try:
        if args.command == "train":
            if args.epochs < 1:
                parser.error("--epochs must be positive")
            train(args.output, args.epochs)
        else:
            print(json.dumps(predict(args.measurements, args.artifacts), ensure_ascii=False, indent=2))
    except (ValueError, FileNotFoundError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
