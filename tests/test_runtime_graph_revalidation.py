from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from foundation.evaluation.runtime_contract_evaluator import evaluate_runtime_contract
from foundation.migrations.materialize_runtime_report_receipts_v1 import run as run_receipt_migration
from foundation.mt5.runtime_completion import (
    EXPECTED_EXECUTION_PROFILE_ID,
    EXPECTED_PERIOD_PROFILE_ID,
    EXPECTED_RUNTIME_PERIOD_SET_ID,
)
from foundation.mt5.tester_report_receipt import file_sha256
from foundation.validation.active_record_validator import validate_runtime_completion_truth
from spacesonar.control_plane.store import filesystem_path


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def load_yaml(path: Path) -> dict[str, Any]:
    with open(filesystem_path(path), "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def read_text(path: Path) -> str:
    with open(filesystem_path(path), "r", encoding="utf-8") as handle:
        return handle.read()


def utc_timestamp(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC).timestamp()


def _tester_config_text(expert: str) -> str:
    return "\n".join(
        [
            f"Expert={expert}",
            "Symbol=US100",
            "Period=M5",
            "FromDate=2024.06.05",
            "ToDate=2025.03.10",
            "Model=4",
            "Deposit=500",
            "Leverage=100",
            "",
        ]
    )


def _tester_report_text(expert: str) -> str:
    return "\n".join(
        [
            f"Expert: {expert}",
            "Symbol: US100",
            "Period: M5 (2024.06.05 - 2025.03.10)",
            "Model: 4",
            "Initial deposit: 500.00",
            "Leverage: 1:100",
            "Fatal errors: 0",
            "Total trades: 1",
            "",
        ]
    )


def complete_receipt(attempt_id: str) -> dict[str, Any]:
    return {
        "receipt_version": "tester_report_receipt_v1",
        "attempt_id": attempt_id,
        "source_report_sha256": "a" * 64,
        "source_report_size_bytes": 100,
        "source_report_mtime_utc": "2020-01-01T00:00:01.123456Z",
        "source_origin": "attempt_archive_path",
        "source_report_extension": ".htm",
        "launch_started_at_utc": "2020-01-01T00:00:00.999999Z",
        "report_observed_at_utc": "2020-01-01T00:00:01.123456Z",
        "prelaunch_report_sha256": None,
        "postlaunch_report_sha256": "a" * 64,
        "freshness_reason": "absent_prelaunch_created_after_launch",
        "report_fresh_for_launch": True,
        "parse_status": "parsed",
        "completion_marker_observed": True,
        "symbol": "US100",
        "timeframe": "M5",
        "from_date": "2024.06.05",
        "to_date": "2025.03.10",
        "model": "4",
        "deposit": "500.00",
        "leverage": "1:100",
        "expert": "SpaceSonar_ONNX_L4_ScoreProbe",
        "fatal_error_count": 0,
        "expected_identity_missing_fields": [],
        "tester_identity_match": True,
        "tester_report_completed": True,
        "missing_requirements": [],
    }


def seed_attempt(
    repo: Path,
    *,
    attempt_id: str,
    campaign_id: str = "campaign_wp03_fixture_v0",
    cell_id: str = "cell_001",
    period_role: str = "validation",
    kind: str = "score_probe",
    stored_complete: bool = True,
    receipt: dict[str, Any] | None = None,
) -> Path:
    attempt_root = repo / "runtime" / "mt5_attempts" / attempt_id
    attempt_root.mkdir(parents=True, exist_ok=True)
    telemetry_name = "execution_telemetry_summary.yaml" if kind == "decision_replay" else "score_telemetry_summary.yaml"
    scope = "full_period_sparse_decision_surface" if kind == "decision_replay" else "full_period_deterministic"
    manifest = {
        "attempt_id": attempt_id,
        "campaign_id": campaign_id,
        "cell_id": cell_id,
        "period_identity": {
            "period_role": period_role,
            "period_profile_id": EXPECTED_PERIOD_PROFILE_ID,
            "runtime_period_set_id": EXPECTED_RUNTIME_PERIOD_SET_ID,
        },
        "execution_identity": {
            "execution_profile_id": EXPECTED_EXECUTION_PROFILE_ID,
        },
        "runtime_surface_contract": {
            "completion_surface_scope": scope,
            "runtime_surface_kind": kind,
        },
        "status": "runtime_probe_completed" if stored_complete else "prepared",
        "execution_state": {
            "terminal_launched": True,
            "telemetry_file_observed": True,
            "telemetry_rows_observed": True,
            "tester_report_observed": True,
            "tester_report_completed": True,
            "terminal_mode": "portable_contract_attempt",
            "runtime_probe_complete": stored_complete,
            "missing_requirements": [],
        },
        "tester_report_receipt": {
            "path": f"runtime/mt5_attempts/{attempt_id}/tester_report_receipt.yaml",
        },
    }
    write_yaml(attempt_root / "attempt_manifest.yaml", manifest)
    write_yaml(
        attempt_root / "terminal_run_summary.yaml",
        {
            "terminal_launched": True,
            "mode": "portable_contract_attempt",
            "started_at_utc": "2020-01-01T00:00:00.999999Z",
            "terminal_mode_policy": {
                "portable_attempted": True,
                "main_mode_fallback_allowed": False,
                "main_mode_fallback_used": False,
            },
        },
    )
    write_yaml(
        attempt_root / telemetry_name,
        {
            "telemetry": {
                "path": f"runtime/mt5_attempts/{attempt_id}/telemetry.csv",
            },
            "stats": {"row_count": 1},
        },
    )
    if receipt is None:
        receipt = complete_receipt(attempt_id)
    write_yaml(attempt_root / "tester_report_receipt.yaml", receipt)
    return attempt_root / "attempt_manifest.yaml"


def seed_migration_attempt(
    repo: Path,
    *,
    attempt_id: str = "attempt_wave01_wp03_cell_001_l4_validation_v0",
    period_role: str = "validation",
    kind: str = "score_probe",
    report_present: bool = True,
    stored_hash_override: str | None = None,
) -> Path:
    attempt_root = repo / "runtime" / "mt5_attempts" / attempt_id
    attempt_root.mkdir(parents=True, exist_ok=True)
    expert = "foundation/mt5/experts/SpaceSonar_ONNX_L4_ScoreProbe.ex5"
    config = attempt_root / "tester_config.ini"
    config.write_text(_tester_config_text(expert), encoding="utf-8")
    report = attempt_root / "reports" / "tester_report.htm"
    report_record: dict[str, Any] = {
        "path": report.relative_to(repo).as_posix(),
        "sha256": stored_hash_override or "missing",
        "size_bytes": None,
    }
    if report_present:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(_tester_report_text(expert), encoding="utf-8")
        report_time = utc_timestamp("2020-01-01T00:00:01.123456Z")
        os.utime(report, (report_time, report_time))
        report_record["sha256"] = stored_hash_override or file_sha256(report)
        report_record["size_bytes"] = report.stat().st_size
    telemetry_name = "execution_telemetry_summary.yaml" if kind == "decision_replay" else "score_telemetry_summary.yaml"
    write_yaml(
        attempt_root / "attempt_manifest.yaml",
        {
            "attempt_id": attempt_id,
            "campaign_id": "campaign_wp03_fixture_v0",
            "cell_id": "cell_001",
            "period_identity": {
                "period_role": period_role,
                "period_profile_id": EXPECTED_PERIOD_PROFILE_ID,
                "runtime_period_set_id": EXPECTED_RUNTIME_PERIOD_SET_ID,
            },
            "execution_identity": {"execution_profile_id": EXPECTED_EXECUTION_PROFILE_ID},
            "runtime_surface_contract": {"surface_scope": "historical_descriptive_scope"},
            "status": "runtime_probe_completed",
            "execution_state": {
                "terminal_launched": True,
                "telemetry_file_observed": True,
                "telemetry_rows_observed": True,
                "tester_report_observed": True,
                "tester_report_completed": True,
                "terminal_mode": "portable_contract_attempt",
                "runtime_probe_complete": True,
                "missing_requirements": [],
            },
            "tester_report": report_record,
            "artifact_identity": {
                "tester_config": {"path": config.relative_to(repo).as_posix()},
                "tester_reports": [report_record],
            },
        },
    )
    write_yaml(
        attempt_root / "terminal_run_summary.yaml",
        {
            "terminal_launched": True,
            "mode": "portable_contract_attempt",
            "started_at_utc": "2020-01-01T00:00:00.999999Z",
            "terminal_mode_policy": {
                "portable_attempted": True,
                "main_mode_fallback_allowed": False,
                "main_mode_fallback_used": False,
            },
        },
    )
    write_yaml(
        attempt_root / telemetry_name,
        {
            "telemetry": {"path": f"runtime/mt5_attempts/{attempt_id}/telemetry.csv"},
            "stats": {"row_count": 1},
        },
    )
    return attempt_root / "attempt_manifest.yaml"


def test_evaluator_rejects_unpaired_duplicate_roles(tmp_path: Path) -> None:
    seed_attempt(tmp_path, attempt_id="attempt_wave01_wp03_cell_a_l4_validation_v0", cell_id="cell_a")
    seed_attempt(tmp_path, attempt_id="attempt_wave01_wp03_cell_a_l4_validation_extra_v0", cell_id="cell_a")
    seed_attempt(
        tmp_path,
        attempt_id="attempt_wave01_wp03_cell_b_l4_research_oos_v0",
        cell_id="cell_b",
        period_role="research_oos",
    )
    seed_attempt(
        tmp_path,
        attempt_id="attempt_wave01_wp03_cell_b_l4_research_oos_extra_v0",
        cell_id="cell_b",
        period_role="research_oos",
    )

    result = evaluate_runtime_contract(tmp_path)

    assert result["status"] == "failed"
    assert result["metrics"]["runtime_probe_complete_count"] == 4
    assert result["metrics"]["pair_groups_complete"] == 0
    assert result["metrics"]["pair_groups_incomplete"] == 2


def test_evaluator_does_not_mix_score_and_decision_replay_pairing(tmp_path: Path) -> None:
    seed_attempt(tmp_path, attempt_id="attempt_wave01_wp03_cell_001_l4_validation_v0", cell_id="cell_001")
    seed_attempt(
        tmp_path,
        attempt_id="attempt_wave01_wp03_cell_001_l4_decision_replay_research_oos_v0",
        cell_id="cell_001",
        period_role="research_oos",
        kind="decision_replay",
    )

    result = evaluate_runtime_contract(tmp_path)

    assert result["status"] == "failed"
    assert result["metrics"]["runtime_surface_kind_counts"] == {"decision_replay": 1, "score_probe": 1}
    assert result["metrics"]["pair_groups_complete"] == 0
    assert result["metrics"]["pair_groups_incomplete"] == 2


def test_stored_completion_true_but_receipt_fails_is_rejected(tmp_path: Path) -> None:
    receipt = complete_receipt("attempt_wave01_wp03_cell_001_l4_validation_v0")
    receipt["tester_identity_match"] = False
    receipt["tester_report_completed"] = False
    receipt["missing_requirements"] = ["tester_identity_match"]
    seed_attempt(tmp_path, attempt_id="attempt_wave01_wp03_cell_001_l4_validation_v0", receipt=receipt)

    result = evaluate_runtime_contract(tmp_path)
    errors = validate_runtime_completion_truth(tmp_path)

    assert result["status"] == "failed"
    assert result["metrics"]["runtime_probe_incomplete_count"] == 1
    assert any("stored runtime_probe_complete projection conflicts" in error for error in errors)


def test_migration_records_missing_raw_report_without_fabricating_completion(tmp_path: Path) -> None:
    seed_migration_attempt(tmp_path, report_present=False)

    result = run_receipt_migration(tmp_path, write=True)
    manifest = load_yaml(tmp_path / "runtime/mt5_attempts/attempt_wave01_wp03_cell_001_l4_validation_v0/attempt_manifest.yaml")
    receipt = load_yaml(tmp_path / "runtime/mt5_attempts/attempt_wave01_wp03_cell_001_l4_validation_v0/tester_report_receipt.yaml")

    assert result["transaction_status"] == "committed"
    assert result["report_receipts_created"] == 0
    assert manifest["execution_state"]["runtime_probe_complete"] is False
    assert manifest["execution_state"]["tester_report_observed"] is False
    assert receipt["tester_report_completed"] is False
    assert "tester_report_observed" in manifest["execution_state"]["missing_requirements"]


def test_migration_report_hash_mismatch_keeps_attempt_incomplete(tmp_path: Path) -> None:
    seed_migration_attempt(tmp_path, stored_hash_override="0" * 64)

    result = run_receipt_migration(tmp_path, write=True)
    manifest = load_yaml(tmp_path / "runtime/mt5_attempts/attempt_wave01_wp03_cell_001_l4_validation_v0/attempt_manifest.yaml")
    receipt = load_yaml(tmp_path / "runtime/mt5_attempts/attempt_wave01_wp03_cell_001_l4_validation_v0/tester_report_receipt.yaml")

    assert result["transaction_status"] == "committed"
    assert receipt["stored_report_sha256_match"] is False
    assert receipt["tester_report_completed"] is False
    assert manifest["execution_state"]["runtime_probe_complete"] is False
    assert "runtime_completion_missing:tester_report_completed" in manifest["missing_evidence"]
    assert "tester_report_receipt_missing:stored_report_sha256_match" in manifest["missing_evidence"]


def test_migration_is_idempotent_after_receipt_materialization(tmp_path: Path) -> None:
    seed_migration_attempt(tmp_path)

    first = run_receipt_migration(tmp_path, write=True)
    second = run_receipt_migration(tmp_path, write=True)

    assert first["transaction_status"] == "committed"
    assert first["attempts_complete"] == 1
    assert second["transaction_status"] == "noop_already_applied"
    assert second["changed_record_count"] == 0


def test_migration_rollback_restores_all_related_records(tmp_path: Path) -> None:
    first_manifest = seed_migration_attempt(tmp_path, attempt_id="attempt_wave01_wp03_cell_001_l4_validation_v0")
    seed_migration_attempt(
        tmp_path,
        attempt_id="attempt_wave01_wp03_cell_001_l4_research_oos_v0",
        period_role="research_oos",
    )
    original_manifest = read_text(first_manifest)

    result = run_receipt_migration(tmp_path, write=True, fail_after_replace_count=1)

    assert result["transaction_status"] == "rolled_back_commit_failure"
    assert read_text(first_manifest) == original_manifest
    assert not (first_manifest.parent / "tester_report_receipt.yaml").exists()


def test_evaluator_digest_changes_when_durable_input_changes(tmp_path: Path) -> None:
    seed_attempt(tmp_path, attempt_id="attempt_wave01_wp03_cell_001_l4_validation_v0")
    seed_attempt(
        tmp_path,
        attempt_id="attempt_wave01_wp03_cell_001_l4_research_oos_v0",
        period_role="research_oos",
    )

    first = evaluate_runtime_contract(tmp_path)
    receipt_path = tmp_path / "runtime/mt5_attempts/attempt_wave01_wp03_cell_001_l4_validation_v0/tester_report_receipt.yaml"
    receipt = load_yaml(receipt_path)
    receipt["fatal_error_count"] = 1
    receipt["tester_report_completed"] = False
    write_yaml(receipt_path, receipt)
    second = evaluate_runtime_contract(tmp_path)

    assert first["status"] == "passed"
    assert second["status"] == "failed"
    assert first["output_sha256"] != second["output_sha256"]
