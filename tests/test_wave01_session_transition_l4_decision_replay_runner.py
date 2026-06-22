from __future__ import annotations

from pathlib import Path

import foundation.pipelines.run_wave0_l4_decision_replay_attempts as base
from foundation.pipelines.run_wave01_session_transition_l4_decision_replay_attempts import (
    CLAIM_BOUNDARY,
    OUTPUT_DIR,
    PREP_INDEX,
    RUNTIME_INDEX,
    RUNTIME_SUMMARY,
    configure_base,
    normalize_attempt_outputs,
    normalize_summary,
    parse_args,
)


def test_session_transition_decision_replay_defaults_to_one_attempt_without_taskkill() -> None:
    args = parse_args([])

    assert args.limit == 1
    assert args.terminate_existing_terminal is False


def test_session_transition_decision_replay_configures_base_paths() -> None:
    original = {
        "WORK_ITEM_ID": base.WORK_ITEM_ID,
        "SUBWORK_ID": base.SUBWORK_ID,
        "CAMPAIGN_ID": base.CAMPAIGN_ID,
        "SWEEP_ID": base.SWEEP_ID,
        "OUTPUT_DIR": base.OUTPUT_DIR,
        "PREP_INDEX": base.PREP_INDEX,
        "RUNTIME_SUMMARY": base.RUNTIME_SUMMARY,
        "RUNTIME_INDEX": base.RUNTIME_INDEX,
        "CLAIM_BOUNDARY": base.CLAIM_BOUNDARY,
    }
    try:
        configure_base()
        assert base.OUTPUT_DIR == OUTPUT_DIR
        assert base.PREP_INDEX == PREP_INDEX
        assert base.RUNTIME_SUMMARY == RUNTIME_SUMMARY
        assert base.RUNTIME_INDEX == RUNTIME_INDEX
        assert "campaign_us100_session_transition_regime_surface_v0" in base.OUTPUT_DIR.as_posix()
        assert "campaign_us100_task_surface_scout_v0" not in base.OUTPUT_DIR.as_posix()
        assert base.CLAIM_BOUNDARY == CLAIM_BOUNDARY
    finally:
        for key, value in original.items():
            setattr(base, key, value)


def test_session_transition_normalize_summary_records_thin_runtime_scope() -> None:
    summary = {
        "version": "old",
        "summary_id": "old",
        "work_item_id": "old",
        "subwork_item_id": "old",
        "active_goal_id": "old",
        "campaign_id": "old",
        "sweep_id": "old",
        "status": "partial_wave01_session_transition_decision_replay_terminal_execution_started",
        "claim_boundary": "old",
        "runtime_contract_binding": {"runtime_level": "old"},
        "counts": {"execution_telemetry_observed_count": 1},
        "artifact_outputs": {
            "runtime_execution_summary": "old",
            "runtime_execution_index": "old",
        },
        "judgment": {"next_action": "old"},
    }

    normalized = normalize_summary(summary)

    assert normalized["version"] == "wave01_session_transition_l4_decision_replay_runtime_execution_summary_v1"
    assert normalized["campaign_id"] == "campaign_us100_session_transition_regime_surface_v0"
    assert normalized["artifact_outputs"]["runtime_execution_summary"] == RUNTIME_SUMMARY.as_posix()
    assert normalized["judgment"]["score_replay_decision_probe_observed"] is True
    assert normalized["try_first_disposition"]["policy_applied"].startswith("missing session-transition")


def test_session_transition_normalize_attempt_outputs_records_scope(tmp_path: Path) -> None:
    attempt_id = "attempt_wave01_st_cell_003_l4_decision_replay_validation_score_band_inverse_side_v0"
    attempt_root = tmp_path / "runtime" / "mt5_attempts" / attempt_id
    attempt_root.mkdir(parents=True)
    manifest_path = attempt_root / "attempt_manifest.yaml"
    terminal_path = attempt_root / "terminal_run_summary.yaml"
    telemetry_path = attempt_root / "execution_telemetry_summary.yaml"
    terminal_path.write_text("version: old\n", encoding="utf-8")
    telemetry_path.write_text("version: old\nclaim_boundary: old\n", encoding="utf-8")
    manifest_path.write_text("proxy_runtime_parity: {}\nartifact_identity: {}\n", encoding="utf-8")
    row = {
        "attempt_id": attempt_id,
        "attempt_manifest_path": f"runtime/mt5_attempts/{attempt_id}/attempt_manifest.yaml",
        "period_role": "validation",
    }
    execution_row = {"execution_telemetry_observed": True, "claim_boundary": "old"}

    normalized = normalize_attempt_outputs(tmp_path, row, execution_row)

    terminal = base.load_yaml(terminal_path)
    telemetry = base.load_yaml(telemetry_path)
    manifest = base.load_yaml(manifest_path)
    assert terminal["version"] == "wave01_session_transition_l4_decision_replay_terminal_run_summary_v1"
    assert telemetry["version"] == "wave01_session_transition_l4_decision_replay_execution_telemetry_summary_v1"
    assert telemetry["claim_boundary"] == CLAIM_BOUNDARY
    assert manifest["runtime_probe_routing"]["routing_scope"] == (
        "wave01_session_transition_inverse_score_band_decision_replay_runtime_execution"
    )
    assert manifest["runtime_probe_routing"]["thin_first_pass"] is True
    assert "inverse-polarity" in manifest["proxy_runtime_parity"]["prevention_memory"][0]
    assert normalized["claim_boundary"] == CLAIM_BOUNDARY

