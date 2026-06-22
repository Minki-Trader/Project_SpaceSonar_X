from __future__ import annotations

import numpy as np
import onnxruntime as ort
import pandas as pd

from foundation.onnx.skl2onnx_adapters import convert_sklearn_pipeline_for_lab
from foundation.pipelines.materialize_wave01_session_transition_l4_onnx_bundles import (
    CLAIM_BOUNDARY,
    EXPORTABLE_MODEL_FAMILIES,
    TARGET_OPSET,
    axis_from_matrix_row,
    bundle_id_for_axis,
    cell_id_for_axis,
    label_contract,
)
from foundation.training.wave01_event_barrier_models import fit_proxy_model, score_model


def test_session_transition_materializer_keeps_claim_limited_l4_preflight_boundary() -> None:
    assert TARGET_OPSET == 13
    assert "no_runtime_authority" in CLAIM_BOUNDARY
    assert "no_candidate" in CLAIM_BOUNDARY
    assert "no_baseline" in CLAIM_BOUNDARY


def test_session_transition_materializer_includes_current_exportable_model_families() -> None:
    assert EXPORTABLE_MODEL_FAMILIES == {
        "logistic_or_linear_rank_scout",
        "tree_or_boosted_onnx_feasible_scout",
        "small_mlp_secondary_only",
    }


def test_session_transition_axis_identity_comes_from_matrix_row() -> None:
    row = {
        "spec_id": "wave01_st_cell_002",
        "label_surface": "pre_cash_compression_release",
        "horizon_bars": "12",
        "session_anchor": "pre_to_cash_transition",
        "transition_window_bars": "pre_24_to_post_24",
        "regime_label": "compression_to_expansion",
        "feature_family": "compression_expansion_causal_context",
    }

    axis = axis_from_matrix_row(row)

    assert axis["horizon_bars"] == 12
    assert cell_id_for_axis(axis) == "wave01_st_cell_002"
    assert bundle_id_for_axis(axis) == "bundle_wave01_st_cell_002_l4_onnx_export_v0"
    assert label_contract(axis) == {
        "label_surface": "pre_cash_compression_release",
        "horizon_bars": 12,
        "session_anchor": "pre_to_cash_transition",
        "transition_window_bars": "pre_24_to_post_24",
        "regime_label": "compression_to_expansion",
    }


def test_session_transition_hgb_path_still_converts_with_single_score_output() -> None:
    rng = np.random.default_rng(22)
    raw = rng.normal(size=(1400, 6))
    features = pd.DataFrame(raw, columns=[f"f{i}" for i in range(raw.shape[1])])
    target = pd.Series(((raw[:, 0] - raw[:, 1] * 0.5 + raw[:, 2] * 0.25) > 0.0).astype(float))
    train_mask = pd.Series([True] * 1100 + [False] * 300)
    fixture = features.loc[~train_mask].head(64)

    fit = fit_proxy_model(
        features,
        target,
        train_mask,
        model_family="tree_or_boosted_onnx_feasible_scout",
        task_kind="classification",
        target_name="synthetic_binary",
        threshold_policy="train_only_density_floor",
        target_threshold=None,
    )
    converted = convert_sklearn_pipeline_for_lab(
        fit.model,
        feature_count=features.shape[1],
        task_kind=fit.task_kind,
        target_opset=TARGET_OPSET,
    )
    session = ort.InferenceSession(converted.model.SerializeToString(), providers=["CPUExecutionProvider"])
    expected = score_model(fit.model, fixture, fit.task_kind)
    observed = session.run(None, {"features": fixture.astype("float32").to_numpy()})[0].reshape(-1)

    assert np.max(np.abs(expected - observed)) <= 1.0e-5
