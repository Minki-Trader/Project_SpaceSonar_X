from __future__ import annotations

from pathlib import Path

import foundation.pipelines.run_wave0_l4_decision_replay_attempts as base
from foundation.pipelines.run_wave01_event_barrier_l4_decision_replay_attempts import (
    CLAIM_BOUNDARY,
    COMPILE_SUMMARY,
    OUTPUT_DIR,
    PREP_INDEX,
    RUNTIME_INDEX,
    RUNTIME_SUMMARY,
    configure_base,
    normalize_attempt_outputs,
    normalize_summary,
    parse_args,
    upsert_artifact_registry,
)


def test_wave01_decision_replay_defaults_to_bounded_single_attempt_without_taskkill() -> None:
    args = parse_args([])

    assert args.limit == 1
    assert args.terminate_existing_terminal is False
    assert args.no_main_mode_fallback is False


def test_wave01_decision_replay_configures_paths_without_wave0_outputs() -> None:
    original = {
        "WORK_ITEM_ID": base.WORK_ITEM_ID,
        "SUBWORK_ID": base.SUBWORK_ID,
        "CAMPAIGN_ID": base.CAMPAIGN_ID,
        "SWEEP_ID": base.SWEEP_ID,
        "OUTPUT_DIR": base.OUTPUT_DIR,
        "PREP_INDEX": base.PREP_INDEX,
        "RUNTIME_SUMMARY": base.RUNTIME_SUMMARY,
        "RUNTIME_INDEX": base.RUNTIME_INDEX,
        "COMPILE_SUMMARY": base.COMPILE_SUMMARY,
        "CLAIM_BOUNDARY": base.CLAIM_BOUNDARY,
    }
    try:
        configure_base()

        assert base.OUTPUT_DIR == OUTPUT_DIR
        assert base.PREP_INDEX == PREP_INDEX
        assert base.RUNTIME_SUMMARY == RUNTIME_SUMMARY
        assert base.RUNTIME_INDEX == RUNTIME_INDEX
        assert base.COMPILE_SUMMARY == COMPILE_SUMMARY
        assert "decision_replay" in base.OUTPUT_DIR.as_posix()
        assert "campaign_us100_task_surface_scout_v0" not in base.OUTPUT_DIR.as_posix()
        assert base.CLAIM_BOUNDARY == CLAIM_BOUNDARY
    finally:
        for key, value in original.items():
            setattr(base, key, value)


def test_normalize_summary_rewrites_wave01_decision_replay_identity() -> None:
    summary = {
        "version": "decision_replay_runtime_execution_summary_v1",
        "summary_id": "old",
        "work_item_id": "old",
        "subwork_item_id": "old",
        "active_goal_id": "old",
        "campaign_id": "old",
        "sweep_id": "old",
        "status": "wave01_decision_replay_terminal_execution_attempted_for_all_prepared_attempts",
        "claim_boundary": "old",
        "runtime_contract_binding": {"runtime_level": "old"},
        "counts": {"execution_telemetry_observed_count": 2},
        "artifact_outputs": {
            "runtime_execution_summary": "old",
            "runtime_execution_index": "old",
        },
        "judgment": {
            "runtime_probe_completed_for_all_prepared_attempts": True,
            "next_action": "old",
        },
    }

    normalized = normalize_summary(summary)

    assert normalized["version"] == "wave01_event_barrier_l4_decision_replay_runtime_execution_summary_v1"
    assert normalized["summary_id"] == "wave01_event_barrier_l4_decision_replay_runtime_execution_summary_v0"
    assert normalized["campaign_id"] == "campaign_us100_event_barrier_decision_surface_v0"
    assert normalized["artifact_outputs"]["runtime_execution_summary"] == RUNTIME_SUMMARY.as_posix()
    assert "Wave01" in normalized["judgment"]["next_action"]
    assert normalized["try_first_disposition"]["policy_applied"].startswith("missing Wave01 runner")


def test_normalize_attempt_outputs_records_wave01_decision_replay_scope(tmp_path: Path) -> None:
    attempt_id = "attempt_wave01_eb_cell_002_l4_decision_replay_validation_score_band_side_v0"
    attempt_root = tmp_path / "runtime" / "mt5_attempts" / attempt_id
    attempt_root.mkdir(parents=True)
    manifest_path = attempt_root / "attempt_manifest.yaml"
    terminal_path = attempt_root / "terminal_run_summary.yaml"
    telemetry_path = attempt_root / "execution_telemetry_summary.yaml"
    tester_log_path = attempt_root / "tester_log_summary.yaml"
    terminal_path.write_text("version: old\n", encoding="utf-8")
    telemetry_path.write_text("version: old\nclaim_boundary: old\n", encoding="utf-8")
    tester_log_path.write_text("version: old\n", encoding="utf-8")
    manifest_path.write_text(
        "runtime_probe_routing:\n"
        "  routing_scope: wave0_l4_score_replay_decision_execution\n"
        "proxy_runtime_parity: {}\n"
        "artifact_identity: {}\n",
        encoding="utf-8",
    )
    row = {
        "attempt_id": attempt_id,
        "attempt_manifest_path": f"runtime/mt5_attempts/{attempt_id}/attempt_manifest.yaml",
        "period_role": "validation",
    }
    execution_row = {
        "execution_telemetry_observed": True,
        "claim_boundary": "old",
        "next_action": "old",
    }

    normalized = normalize_attempt_outputs(tmp_path, row, execution_row)

    terminal = base.load_yaml(terminal_path)
    telemetry = base.load_yaml(telemetry_path)
    tester_log = base.load_yaml(tester_log_path)
    manifest = base.load_yaml(manifest_path)
    assert terminal["version"] == "wave01_event_barrier_l4_decision_replay_terminal_run_summary_v1"
    assert telemetry["version"] == "wave01_event_barrier_l4_decision_replay_execution_telemetry_summary_v1"
    assert telemetry["claim_boundary"] == CLAIM_BOUNDARY
    assert tester_log["version"] == "wave01_event_barrier_l4_decision_replay_tester_log_summary_v1"
    assert manifest["runtime_probe_routing"]["routing_scope"] == (
        "wave01_event_barrier_score_band_decision_replay_runtime_execution"
    )
    assert "try_first_disposition" in manifest["runtime_probe_routing"]
    assert "Wave01 decision replay runner normalizes" in manifest["proxy_runtime_parity"]["prevention_memory"][0]
    assert normalized["claim_boundary"] == CLAIM_BOUNDARY


def test_upsert_artifact_registry_refreshes_attempt_manifest_hash(tmp_path: Path) -> None:
    attempt_id = "attempt_wave01_eb_cell_002_l4_decision_replay_validation_score_band_side_v0"
    registry = tmp_path / "docs" / "registers" / "artifact_registry.csv"
    manifest = tmp_path / "runtime" / "mt5_attempts" / attempt_id / "attempt_manifest.yaml"
    summary_path = tmp_path / RUNTIME_SUMMARY
    index_path = tmp_path / RUNTIME_INDEX
    closeout_path = tmp_path / "lab/goals/goal_us100_onnx_forward_boundary_v0/work_wave01_event_barrier_l4_decision_replay_runtime_execution_v0_closeout.yaml"
    compile_path = tmp_path / COMPILE_SUMMARY
    for path in [registry, manifest, summary_path, index_path, closeout_path, compile_path]:
        path.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text("status: completed\n", encoding="utf-8")
    summary_path.write_text("summary: ok\n", encoding="utf-8")
    index_path.write_text("index: ok\n", encoding="utf-8")
    closeout_path.write_text("closeout: ok\n", encoding="utf-8")
    compile_path.write_text("compile: ok\n", encoding="utf-8")
    registry.write_text(
        "artifact_id,run_id,bundle_id,attempt_id,artifact_type,path_or_uri,sha256,size_bytes,availability,"
        "producer_command,regeneration_command,source_of_truth,consumer,claim_boundary,notes\n"
        f"artifact_{attempt_id}_manifest_v0,,,,mt5_attempt_manifest,"
        f"runtime/mt5_attempts/{attempt_id}/attempt_manifest.yaml,stale,1,present_hash_recorded,,,,,,old\n",
        encoding="utf-8",
    )
    summary = {
        "environment": {"command_argv": ["python", "runner.py"]},
        "claim_boundary": CLAIM_BOUNDARY,
    }
    execution_rows = [
        {
            "attempt_id": attempt_id,
            "run_id": "run",
            "bundle_id": "bundle",
            "claim_boundary": CLAIM_BOUNDARY,
        }
    ]

    upsert_artifact_registry(tmp_path, summary, execution_rows)

    rows = base.read_csv_rows(registry)
    by_id = {row["artifact_id"]: row for row in rows}
    refreshed = by_id[f"artifact_{attempt_id}_manifest_v0"]
    assert refreshed["sha256"] == base.sha256(manifest)
    assert refreshed["size_bytes"] == str(manifest.stat().st_size)
