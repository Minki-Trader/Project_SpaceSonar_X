from __future__ import annotations

from foundation.pipelines.materialize_wave0_l4_onnx_bundles import (
    CLAIM_BOUNDARY,
    TARGET_OPSET,
    exportable_from_preflight,
)


def test_exportable_from_preflight_includes_repaired_hgb_adapter_family() -> None:
    preflight = {
        "run_preflight": [
            {"run_id": "run_logistic", "model_family": "logistic_classification_scout"},
            {"run_id": "run_ridge", "model_family": "linear_or_ridge_rank_scout"},
            {"run_id": "run_hgb", "model_family": "onnx_realistic_tree_or_boosted_scout"},
        ]
    }

    exportable, blocked = exportable_from_preflight(preflight)

    assert exportable == ["run_logistic", "run_ridge", "run_hgb"]
    assert blocked == {}


def test_exportable_from_preflight_unknown_family_requires_attempted_probe() -> None:
    preflight = {"run_preflight": [{"run_id": "run_unknown", "model_family": "new_model_family"}]}

    exportable, blocked = exportable_from_preflight(preflight)

    assert exportable == []
    assert blocked == {"run_unknown": "blocked_unknown_model_family_export_adapter_requires_attempted_probe"}


def test_materializer_uses_mt5_compatible_preflight_boundary() -> None:
    assert TARGET_OPSET == 13
    assert "no_runtime_authority" in CLAIM_BOUNDARY
    assert "no_candidate" in CLAIM_BOUNDARY
