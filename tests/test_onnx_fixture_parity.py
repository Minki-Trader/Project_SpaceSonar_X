from __future__ import annotations

import numpy as np
import onnx
from sklearn.linear_model import LogisticRegression

from foundation.onnx.linear_sigmoid import build_linear_sigmoid_onnx
from foundation.parity.onnx_fixture import run_onnx_fixture, sigmoid_logistic_probability


def test_manual_linear_sigmoid_matches_sklearn_and_onnxruntime(tmp_path) -> None:
    x_train = np.array(
        [
            [0.0, 0.1, 1.0, 0.2],
            [0.2, 0.1, 0.8, 0.1],
            [0.4, 0.2, 0.4, 0.3],
            [0.8, 0.5, 0.2, 0.5],
            [1.0, 0.7, 0.1, 0.4],
            [1.2, 0.9, 0.0, 0.6],
        ],
        dtype=np.float32,
    )
    y_train = np.array([0, 0, 0, 1, 1, 1], dtype=np.int64)
    feature_mean = x_train.mean(axis=0).astype(np.float32)
    feature_scale = x_train.std(axis=0).astype(np.float32)
    feature_scale = np.where(feature_scale == 0.0, 1.0, feature_scale).astype(np.float32)

    model = LogisticRegression(C=1.0, solver="lbfgs", max_iter=500, random_state=0)
    model.fit((x_train - feature_mean) / feature_scale, y_train)

    coefficients = model.coef_.astype(np.float32).reshape(-1)
    intercept = float(model.intercept_[0])
    fixture = np.array([0.55, 0.25, 0.35, 0.22], dtype=np.float32)

    sklearn_probability = float(model.predict_proba(((fixture - feature_mean) / feature_scale).reshape(1, -1))[0, 1])
    manual_probability = sigmoid_logistic_probability(
        features=fixture,
        coefficients=coefficients,
        intercept=intercept,
        feature_mean=feature_mean,
        feature_scale=feature_scale,
    )
    assert abs(sklearn_probability - manual_probability) < 1e-6

    onnx_path = tmp_path / "linear_sigmoid.onnx"
    build_linear_sigmoid_onnx(
        feature_count=fixture.shape[0],
        coefficients=coefficients,
        intercept=intercept,
        feature_mean=feature_mean,
        feature_scale=feature_scale,
        output_path=onnx_path,
    )
    onnx.checker.check_model(onnx.load(onnx_path))

    onnx_probability = run_onnx_fixture(onnx_path, fixture)
    assert abs(manual_probability - onnx_probability) < 1e-5
