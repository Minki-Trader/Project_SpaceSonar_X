from __future__ import annotations

from pathlib import Path

import numpy as np
import onnxruntime as ort


def run_onnx_fixture(onnx_path: Path, features: np.ndarray) -> float:
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    output_name = session.get_outputs()[0].name
    result = session.run([output_name], {input_name: features.astype(np.float32)})[0]
    return float(np.asarray(result).reshape(-1)[0])


def sigmoid_logistic_probability(
    *,
    features: np.ndarray,
    coefficients: np.ndarray,
    intercept: float,
    feature_mean: np.ndarray,
    feature_scale: np.ndarray,
) -> float:
    safe_scale = np.where(feature_scale == 0.0, 1.0, feature_scale)
    scaled = (features - feature_mean) / safe_scale
    logit = float(np.dot(scaled, coefficients) + intercept)
    return float(1.0 / (1.0 + np.exp(-logit)))
