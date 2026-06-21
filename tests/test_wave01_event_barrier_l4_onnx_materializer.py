from __future__ import annotations

import numpy as np
import onnxruntime as ort
import pandas as pd

from foundation.pipelines.materialize_wave01_event_barrier_l4_onnx_bundles import (
    CLAIM_BOUNDARY,
    EXPORTABLE_MODEL_FAMILIES,
    TARGET_OPSET,
    axis_from_run_spec,
    bundle_id_for_axis,
    cell_id_for_axis,
)
from foundation.onnx.skl2onnx_adapters import convert_sklearn_pipeline_for_lab
from foundation.training.wave01_event_barrier_models import fit_proxy_model, score_model


def test_wave01_materializer_includes_mlp_as_try_first_exportable_family() -> None:
    assert "small_mlp_secondary_only" in EXPORTABLE_MODEL_FAMILIES
    assert "tree_or_boosted_onnx_feasible_scout" in EXPORTABLE_MODEL_FAMILIES
    assert "logistic_or_linear_rank_scout" in EXPORTABLE_MODEL_FAMILIES


def test_wave01_materializer_uses_claim_limited_l4_preflight_boundary() -> None:
    assert TARGET_OPSET == 13
    assert "no_runtime_authority" in CLAIM_BOUNDARY
    assert "no_candidate" in CLAIM_BOUNDARY
    assert "no_baseline" in CLAIM_BOUNDARY


def test_wave01_materializer_axis_and_bundle_identity_are_event_barrier_specific() -> None:
    run_spec = {
        "axis_values": {
            "spec_id": "wave01_eb_cell_011",
            "label_surface": "range_edge_acceptance_rejection",
            "horizon_bars": "6",
            "timeout_bars": "6",
            "barrier_unit": "price_range_ratio",
            "upper_barrier": "0.75",
            "lower_barrier": "0.75",
            "feature_family": "price_return_range_volatility_context",
            "model_family": "small_mlp_secondary_only",
            "model_task": "range_edge_accept_or_reject_bucket",
            "decision_family": "range_edge_abstain_timeout_exit",
            "holding_policy": "range_edge_event_or_timeout",
            "risk_policy": "small_mlp_allowed_only_after_onnx_feasibility_smoke",
            "threshold_policy": "no_micro_search_before_broad_clue",
        }
    }

    axis = axis_from_run_spec(run_spec)

    assert axis["horizon_bars"] == 6
    assert axis["upper_barrier"] == 0.75
    assert cell_id_for_axis(axis) == "wave01_eb_cell_011"
    assert bundle_id_for_axis(axis) == "bundle_wave01_eb_cell_011_l4_onnx_export_v0"


def test_wave01_hgb_helper_fits_float32_runtime_surface_for_onnx_parity() -> None:
    rng = np.random.default_rng(21)
    raw = rng.normal(size=(1400, 8))
    features = pd.DataFrame(raw, columns=[f"f{i}" for i in range(raw.shape[1])])
    target = pd.Series(((raw[:, 0] * 0.8 - raw[:, 1] * 0.4 + raw[:, 2] * 0.2) > 0.0).astype(float))
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
