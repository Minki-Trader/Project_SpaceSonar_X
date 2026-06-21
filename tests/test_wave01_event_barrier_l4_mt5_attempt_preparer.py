from __future__ import annotations

import foundation.pipelines.prepare_wave0_l4_mt5_attempts as base
from foundation.pipelines.prepare_wave01_event_barrier_l4_mt5_attempts import (
    CLAIM_BOUNDARY,
    MATERIALIZATION_SUMMARY,
    SUMMARY_ID,
    SUMMARY_PATH,
    configure_base,
    normalize_summary,
)


def test_wave01_attempt_preparer_configures_wave01_paths_without_wave0_registry_identity() -> None:
    original = {
        "WORK_ITEM_ID": base.WORK_ITEM_ID,
        "SUBWORK_ID": base.SUBWORK_ID,
        "CAMPAIGN_ID": base.CAMPAIGN_ID,
        "SWEEP_ID": base.SWEEP_ID,
        "MATERIALIZATION_SUMMARY": base.MATERIALIZATION_SUMMARY,
        "MATERIALIZATION_INDEX": base.MATERIALIZATION_INDEX,
        "OUTPUT_DIR": base.OUTPUT_DIR,
        "SUMMARY_PATH": base.SUMMARY_PATH,
        "INDEX_PATH": base.INDEX_PATH,
        "CLOSEOUT_PATH": base.CLOSEOUT_PATH,
        "NEXT_WORK_ITEM": base.NEXT_WORK_ITEM,
        "RESUME_CURSOR": base.RESUME_CURSOR,
        "GOAL_MANIFEST": base.GOAL_MANIFEST,
        "WORKSPACE_STATE": base.WORKSPACE_STATE,
        "ARTIFACT_REGISTRY": base.ARTIFACT_REGISTRY,
        "GOAL_REGISTRY": base.GOAL_REGISTRY,
        "CLAIM_BOUNDARY": base.CLAIM_BOUNDARY,
        "NEXT_PHASE": base.NEXT_PHASE,
    }
    try:
        configure_base()

        assert base.MATERIALIZATION_SUMMARY == MATERIALIZATION_SUMMARY
        assert base.SUMMARY_PATH == SUMMARY_PATH
        assert "wave01_event_barrier" in CLAIM_BOUNDARY
        assert "no_runtime_authority" in CLAIM_BOUNDARY
    finally:
        for key, value in original.items():
            setattr(base, key, value)


def test_wave01_attempt_preparer_normalizes_summary_identity() -> None:
    summary = {
        "version": "wave0_l4_mt5_attempt_preparation_summary_v1",
        "summary_id": "wave0_l4_mt5_attempt_preparation_summary_v0",
        "source_inputs": {
            "onnx_materialization_summary": "old",
            "onnx_materialization_index": "old",
        },
        "artifact_outputs": {"index_csv": "old"},
        "judgment": {"next_action": "old"},
        "counts": {"prepared_attempt_count": 24},
    }

    normalized = normalize_summary(summary)

    assert normalized["summary_id"] == SUMMARY_ID
    assert normalized["version"] == "wave01_event_barrier_l4_mt5_attempt_preparation_summary_v1"
    assert normalized["claim_boundary"] == CLAIM_BOUNDARY
