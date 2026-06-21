from __future__ import annotations

import numpy as np
import onnxruntime as ort
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from foundation.onnx.skl2onnx_adapters import (
    HIST_GRADIENT_BOOSTING_CAST_ADAPTER_ID,
    SINGLE_SCORE_OUTPUT_ADAPTER_ID,
    convert_sklearn_pipeline_for_lab,
)


def test_hist_gradient_boosting_adapter_converts_and_matches_probability() -> None:
    rng = np.random.default_rng(7)
    x = rng.normal(size=(240, 6)).astype(np.float32)
    y = ((x[:, 0] * 0.7 - x[:, 1] * 0.3 + x[:, 2] * 0.2) > 0.0).astype(int)
    model = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            (
                "hist_gradient_boosting",
                HistGradientBoostingClassifier(
                    max_iter=8,
                    learning_rate=0.1,
                    max_leaf_nodes=5,
                    random_state=11,
                ),
            ),
        ]
    )
    model.fit(x, y)

    converted = convert_sklearn_pipeline_for_lab(
        model,
        feature_count=x.shape[1],
        task_kind="classification",
        target_opset=13,
    )
    session = ort.InferenceSession(converted.model.SerializeToString(), providers=["CPUExecutionProvider"])
    outputs = session.run(None, {"features": x[:32].astype(np.float32)})
    observed = outputs[0].reshape(-1)
    expected = model.predict_proba(x[:32])[:, 1]

    assert converted.adapter_ids == [HIST_GRADIENT_BOOSTING_CAST_ADAPTER_ID, SINGLE_SCORE_OUTPUT_ADAPTER_ID]
    assert [output.name for output in session.get_outputs()] == ["score"]
    assert np.max(np.abs(observed - expected)) <= 1.0e-5
