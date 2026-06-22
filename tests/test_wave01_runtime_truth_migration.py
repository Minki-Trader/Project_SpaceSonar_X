from __future__ import annotations

from pathlib import Path

import yaml

from foundation.migrations.reclassify_wave01_runtime_completion import run


def write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path
    attempt = repo / "runtime" / "mt5_attempts" / "attempt_wave01_eb_cell_001_l4_validation_v0" / "attempt_manifest.yaml"
    write_yaml(
        attempt,
        {
            "attempt_id": "attempt_wave01_eb_cell_001_l4_validation_v0",
            "campaign_id": "campaign_us100_event_barrier_decision_surface_v0",
            "status": "completed_l4_score_telemetry_observed",
            "result_judgment": "runtime_probe",
            "period_identity": {
                "period_profile_id": "period_profile_split_set_v0",
                "runtime_period_set_id": "split_base_anchor_v0_research_l4",
                "period_role": "validation",
            },
            "execution_identity": {
                "execution_profile_id": "us100_m5_fpmarkets_tester_execution_v0",
            },
            "runtime_surface_contract": {
                "decision_output": "telemetry_only_no_trades",
            },
            "terminal_run_summary": {
                "mode": "main_mode_config_fallback",
                "terminal_mode_policy": {"main_mode_fallback_used": True},
                "telemetry_file_observed_after_attempt": True,
                "telemetry_rows_observed_after_attempt": True,
            },
            "score_telemetry_summary": {
                "stats": {"row_count": 10},
                "telemetry": {"path": "runtime/mt5_attempts/attempt/telemetry/score.csv"},
            },
            "tester_report": {"observed": False, "status": "tester_report_missing_after_terminal_execution"},
            "missing_evidence": ["tester_report_missing_or_not_archived"],
        },
    )
    closeout = repo / "lab" / "waves" / "wave_us100_closedbar_surface_cartography_v0" / "wave_closeout.yaml"
    write_yaml(
        closeout,
        {
            "status": "wave01_operating_proof_window_closed",
            "result_judgment": "positive_operating_closeout",
            "handoff": {
                "negative_memory_ids": ["neg_wave01_event_barrier_score_band_decision_replay_loss_v0"],
                "preserved_clue_ids": ["clue_wave01_session_transition_remaining_decision_surface_needed_v0"],
            },
        },
    )
    return repo


def test_migration_reclassifies_telemetry_only_main_fallback_attempt(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)

    result = run(repo, write=True)
    manifest = load_yaml(
        repo / "runtime" / "mt5_attempts" / "attempt_wave01_eb_cell_001_l4_validation_v0" / "attempt_manifest.yaml"
    )

    assert result["changed_attempt_count"] == 1
    assert manifest["status"] == "telemetry_adapter_observed_runtime_contract_incomplete"
    assert manifest["execution_state"]["runtime_probe_complete"] is False
    assert "tester_report_observed" in manifest["execution_state"]["missing_requirements"]
    assert "portable_terminal_contract" in manifest["execution_state"]["missing_requirements"]
    assert manifest["migration_history"][0]["previous_status"] == "completed_l4_score_telemetry_observed"


def test_migration_is_idempotent_and_preserves_memory_ids(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)

    first = run(repo, write=True)
    second = run(repo, write=True)
    closeout = load_yaml(repo / "lab" / "waves" / "wave_us100_closedbar_surface_cartography_v0" / "wave_closeout.yaml")

    assert first["changed_attempt_count"] == 1
    assert second["changed_attempt_count"] == 0
    assert closeout["status"] == "wave01_control_plane_proof_closed_runtime_contract_incomplete"
    assert closeout["result_judgment"]["control_plane"] == "positive"
    assert closeout["result_judgment"]["runtime_contract"] == "incomplete"
    assert closeout["handoff"]["negative_memory_ids"] == ["neg_wave01_event_barrier_score_band_decision_replay_loss_v0"]
    assert closeout["handoff"]["preserved_clue_ids"] == ["clue_wave01_session_transition_remaining_decision_surface_needed_v0"]
