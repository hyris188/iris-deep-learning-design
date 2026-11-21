import json
from pathlib import Path

import numpy as np
import pytest
from sklearn.preprocessing import StandardScaler

from src.iris_classifier import ROOT, build_model, load_data, predict, split_indices, validate_measurements


def test_data_and_disjoint_stratified_split():
    x, y = load_data()
    split = split_indices(y)
    assert x.shape == (150, 4)
    assert np.bincount(y).tolist() == [50, 50, 50]
    sets = [set(v) for v in split.values()]
    assert len(set.union(*sets)) == 150
    assert all(not (sets[i] & sets[j]) for i in range(3) for j in range(i+1, 3))
    for name, count in [("train", 30), ("validation", 10), ("test", 10)]:
        assert np.bincount(y[split[name]]).tolist() == [count]*3


def test_saved_scaler_uses_only_train_rows():
    x, y = load_data()
    prep_path = ROOT / "artifacts/preprocessing.json"
    if not prep_path.exists():
        pytest.skip("Run training to validate saved preprocessing")
    prep = json.loads(prep_path.read_text())
    scaler = StandardScaler().fit(x[split_indices(y)["train"]])
    np.testing.assert_allclose(scaler.mean_, prep["mean"], rtol=0, atol=1e-12)
    np.testing.assert_allclose(scaler.scale_, prep["scale"], rtol=0, atol=1e-12)


@pytest.mark.parametrize("values", [[1, 2, 3], [1, 2, 3, 0], [1, -1, 2, 3], [1, 2, 3, float("nan")], [1, 2, 3, float("inf")], ["x", 2, 3, 4]])
def test_invalid_measurements(values):
    with pytest.raises(ValueError):
        validate_measurements(values)


def test_architecture_and_probability_simplex():
    model = build_model()
    assert model.count_params() == 243
    p = model(np.zeros((2, 4), dtype=np.float32), training=False).numpy()
    assert p.shape == (2, 3)
    np.testing.assert_allclose(p.sum(axis=1), 1.0, atol=1e-6)


def test_published_model_can_be_loaded_and_predict():
    if not (ROOT / "artifacts/iris_mlp.keras").exists():
        pytest.skip("No pretrained model")
    result = predict([5.1, 3.5, 1.4, 0.2])
    assert result["class"] == "Iris-setosa"
    assert sum(result["probabilities"].values()) == pytest.approx(1.0, abs=1e-6)
    assert predict([20.0, 20.0, 20.0, 20.0])["review_recommended"]
