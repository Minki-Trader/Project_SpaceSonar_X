from __future__ import annotations

import csv
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

import foundation.evaluation.runtime_contract_evaluator as evaluator_mod
import foundation.migrations.materialize_runtime_report_receipts_v1 as migration_cli
from foundation.evaluation.runtime_contract_evaluator import evaluate_runtime_contract
from foundation.migrations.materialize_runtime_report_receipts_v1 import (
    HISTORICAL_FRESHNESS_REASON,
    run as run_receipt_migration,
    validate_receipt_artifact_rows,
)
from foundation.migrations.runtime_graph_target_inventory import (
    DECISION_REPLAY_PREPARATION_INDEXES,
    EXPECTED_ATTEMPT_COUNT,
    EXPECTED_PAIR_GROUP_COUNT,
    INVENTORY_REL_PATH,
    SCORE_PREPARATION_INDEXES,
    generate_runtime_graph_target_inventory,
    validate_runtime_graph_target_inventory,
)
from foundation.mt5.runtime_completion import (
    EXPECTED_EXECUTION_PROFILE_ID,
    EXPECTED_PERIOD_PROFILE_ID,
    EXPECTED_RUNTIME_PERIOD_SET_ID,
)
from foundation.mt5.tester_report_receipt import file_sha256
from foundation.validation.active_record_validator import validate_runtime_completion_truth


ARTIFACT_FIELDS = [
    "artifact_id",
    "run_id",
    "bundle_id",
    "attempt_id",
    "artifact_type",
    "path_or_uri",
    "sha256",
    "size_bytes",
    "availability",
    "producer_command",
    "regeneration_command",
    "source_of_truth",
    "consumer",
    "claim_boundary",
    "notes",
]
PREP_FIELDS = ["attempt_id", "attempt_manifest_path", "cell_id", "period_role"]
STARTED_AT = "2020-01-01T00:00:00.999999Z"
ENDED_AT = "2020-01-01T00:00:02.000000Z"
REPORT_TIME = "2020-01-01T00:00:01.123456Z"
AFTER_END_TIME = "2020-01-01T00:03:00.000000Z"
EXPERT = "foundation/mt5/experts/SpaceSonar_ONNX_L4_ScoreProbe.ex5"


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def load_yaml(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    return loaded if isinstance(loaded, dict) else {}


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def utc_timestamp(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC).timestamp()


def campaign_id_from_index(path: Path) -> str:
    parts = path.as_posix().split("/")
    return parts[parts.index("campaigns") + 1]


def mt5_tester_config_text(*, replace_report: bool = True) -> str:
    return "\n".join(
        [
            f"Expert={EXPERT}",
            "Symbol=US100",
            "Period=M5",
            "FromDate=2024.06.05",
            "ToDate=2025.03.10",
            "Model=4",
            "Deposit=500",
            "Leverage=100",
            f"ReplaceReport={'true' if replace_report else 'false'}",
            "",
        ]
    )


def mt5_tester_report_text() -> str:
    return "\n".join(
        [
            "Expert: SpaceSonar_ONNX_L4_ScoreProbe",
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


def make_entries() -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    score_index = SCORE_PREPARATION_INDEXES[0]
    decision_index = DECISION_REPLAY_PREPARATION_INDEXES[0]
    for index in range(1, 35):
        cell_id = f"score_cell_{index:03d}"
        for role in ("validation", "research_oos"):
            attempt_id = f"attempt_wave0_wp03_{cell_id}_l4_{role}_v0"
            entries.append(
                {
                    "attempt_id": attempt_id,
                    "manifest_path": f"runtime/mt5_attempts/{attempt_id}/attempt_manifest.yaml",
                    "cell_id": cell_id,
                    "period_role": role,
                    "runtime_surface_kind": "score_probe",
                    "source_index": score_index.as_posix(),
                    "campaign_id": campaign_id_from_index(score_index),
                }
            )
    for index in range(1, 10):
        cell_id = f"decision_cell_{index:03d}"
        for role in ("validation", "research_oos"):
            attempt_id = f"attempt_wave01_wp03_{cell_id}_l4_decision_replay_{role}_v0"
            entries.append(
                {
                    "attempt_id": attempt_id,
                    "manifest_path": f"runtime/mt5_attempts/{attempt_id}/attempt_manifest.yaml",
                    "cell_id": cell_id,
                    "period_role": role,
                    "runtime_surface_kind": "decision_replay",
                    "source_index": decision_index.as_posix(),
                    "campaign_id": campaign_id_from_index(decision_index),
                }
            )
    return entries


def seed_runtime_graph_repo(
    repo: Path,
    *,
    raw_report_missing: set[str] | None = None,
    report_mtime_after_end: set[str] | None = None,
    replace_report_disabled: set[str] | None = None,
) -> list[dict[str, str]]:
    raw_report_missing = raw_report_missing or set()
    report_mtime_after_end = report_mtime_after_end or set()
    replace_report_disabled = replace_report_disabled or set()
    entries = make_entries()
    score_rows = [
        {
            "attempt_id": item["attempt_id"],
            "attempt_manifest_path": item["manifest_path"],
            "cell_id": item["cell_id"],
            "period_role": item["period_role"],
        }
        for item in entries
        if item["runtime_surface_kind"] == "score_probe"
    ]
    decision_rows = [
        {
            "attempt_id": item["attempt_id"],
            "attempt_manifest_path": item["manifest_path"],
            "cell_id": item["cell_id"],
            "period_role": item["period_role"],
        }
        for item in entries
        if item["runtime_surface_kind"] == "decision_replay"
    ]
    for index_path in SCORE_PREPARATION_INDEXES:
        write_csv(repo / index_path, score_rows if index_path == SCORE_PREPARATION_INDEXES[0] else [], PREP_FIELDS)
    for index_path in DECISION_REPLAY_PREPARATION_INDEXES:
        write_csv(
            repo / index_path,
            decision_rows if index_path == DECISION_REPLAY_PREPARATION_INDEXES[0] else [],
            PREP_FIELDS,
        )
    write_csv(repo / "docs/registers/artifact_registry.csv", [], ARTIFACT_FIELDS)
    for entry in entries:
        seed_attempt(repo, entry, raw_report_missing, report_mtime_after_end, replace_report_disabled)
    return entries


def seed_attempt(
    repo: Path,
    entry: dict[str, str],
    raw_report_missing: set[str],
    report_mtime_after_end: set[str],
    replace_report_disabled: set[str],
) -> None:
    attempt_id = entry["attempt_id"]
    attempt_root = repo / "runtime" / "mt5_attempts" / attempt_id
    attempt_root.mkdir(parents=True, exist_ok=True)
    config = attempt_root / "tester_config.ini"
    config.write_text(
        mt5_tester_config_text(replace_report=attempt_id not in replace_report_disabled),
        encoding="utf-8",
    )
    report = attempt_root / "reports" / "tester_report.htm"
    report_record: dict[str, Any] = {
        "path": report.relative_to(repo).as_posix(),
        "sha256": None,
        "size_bytes": None,
    }
    if attempt_id not in raw_report_missing:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(mt5_tester_report_text(), encoding="utf-8")
        report_time = utc_timestamp(AFTER_END_TIME if attempt_id in report_mtime_after_end else REPORT_TIME)
        os.utime(report, (report_time, report_time))
        report_record["sha256"] = file_sha256(report)
        report_record["size_bytes"] = report.stat().st_size
    telemetry_name = (
        "execution_telemetry_summary.yaml"
        if entry["runtime_surface_kind"] == "decision_replay"
        else "score_telemetry_summary.yaml"
    )
    scope = (
        "full_period_sparse_decision_surface"
        if entry["runtime_surface_kind"] == "decision_replay"
        else "full_period_deterministic"
    )
    manifest = {
        "attempt_id": attempt_id,
        "campaign_id": entry["campaign_id"],
        "cell_id": entry["cell_id"],
        "period_identity": {
            "period_role": entry["period_role"],
            "period_profile_id": EXPECTED_PERIOD_PROFILE_ID,
            "runtime_period_set_id": EXPECTED_RUNTIME_PERIOD_SET_ID,
        },
        "execution_identity": {"execution_profile_id": EXPECTED_EXECUTION_PROFILE_ID},
        "runtime_surface_contract": {
            "surface_scope": "legacy_descriptive_scope",
            "completion_surface_scope": scope,
            "runtime_surface_kind": entry["runtime_surface_kind"],
        },
        "status": "runtime_probe_completed",
        "execution_state": {
            "terminal_launched": True,
            "telemetry_file_observed": True,
            "telemetry_rows_observed": True,
            "tester_report_observed": True,
            "tester_report_completed": True,
            "terminal_mode": "portable_contract_attempt",
            "portable_contract_satisfied": True,
            "report_contract_satisfied": True,
            "period_contract_satisfied": True,
            "surface_contract_satisfied": True,
            "runtime_probe_complete": True,
            "missing_requirements": [],
        },
        "tester_report": report_record,
        "artifact_identity": {
            "tester_config": {"path": config.relative_to(repo).as_posix()},
            "tester_reports": [report_record],
        },
        "missing_evidence": [],
    }
    write_yaml(attempt_root / "attempt_manifest.yaml", manifest)
    write_yaml(
        attempt_root / "terminal_run_summary.yaml",
        {
            "terminal_launched": True,
            "mode": "portable_contract_attempt",
            "started_at_utc": STARTED_AT,
            "ended_at_utc": ENDED_AT,
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


def write_inventory(repo: Path) -> dict[str, Any]:
    inventory = generate_runtime_graph_target_inventory(repo)
    write_yaml(repo / INVENTORY_REL_PATH, inventory)
    return inventory


def materialize_committed_repo(repo: Path) -> tuple[list[dict[str, str]], dict[str, Any]]:
    entries = seed_runtime_graph_repo(repo)
    result = run_receipt_migration(repo, write=True, rebuild_from_raw=True)
    assert result["transaction_status"] == "committed"
    assert result["attempts_complete"] == EXPECTED_ATTEMPT_COUNT
    assert result["pair_groups_complete"] == EXPECTED_PAIR_GROUP_COUNT
    return entries, result


def first_pair(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    first = entries[0]
    return [
        item
        for item in entries
        if item["campaign_id"] == first["campaign_id"]
        and item["cell_id"] == first["cell_id"]
        and item["runtime_surface_kind"] == first["runtime_surface_kind"]
    ]


def receipt_path(repo: Path, entry: dict[str, str]) -> Path:
    return repo / Path(entry["manifest_path"]).parent / "tester_report_receipt.yaml"


def mutate_receipt(repo: Path, entry: dict[str, str], **updates: Any) -> dict[str, Any]:
    path = receipt_path(repo, entry)
    receipt = load_yaml(path)
    receipt.update(updates)
    write_yaml(path, receipt)
    return receipt


def remove_all_raw_report_dirs(repo: Path) -> None:
    for reports_dir in (repo / "runtime" / "mt5_attempts").glob("*/reports"):
        shutil.rmtree(reports_dir)


def test_clean_checkout_without_ignored_raw_reports_remains_idempotent(tmp_path: Path) -> None:
    entries, _result = materialize_committed_repo(tmp_path)
    receipt_before = load_yaml(receipt_path(tmp_path, entries[0]))
    remove_all_raw_report_dirs(tmp_path)

    check = run_receipt_migration(tmp_path, write=False)
    evaluator = evaluate_runtime_contract(tmp_path)
    receipt_after = load_yaml(receipt_path(tmp_path, entries[0]))

    assert check["changed_record_count"] == 0
    assert check["receipt_binding_failure_count"] == 0
    assert evaluator["status"] == "passed"
    assert receipt_after["tester_report_completed"] is True
    assert receipt_after == receipt_before


def test_evaluator_fails_when_both_manifests_of_one_pair_are_missing(tmp_path: Path) -> None:
    entries, _result = materialize_committed_repo(tmp_path)
    for entry in first_pair(entries):
        (tmp_path / entry["manifest_path"]).unlink()

    result = evaluate_runtime_contract(tmp_path)

    assert result["status"] == "failed"
    assert result["metrics"]["expected_attempt_count"] == EXPECTED_ATTEMPT_COUNT
    assert result["metrics"]["attempt_count"] == EXPECTED_ATTEMPT_COUNT
    assert result["metrics"]["expected_target_missing"] > 0
    assert result["metrics"]["pair_groups_complete"] == EXPECTED_PAIR_GROUP_COUNT - 1


def test_evaluator_keeps_pair_when_execution_state_blocks_are_missing(tmp_path: Path) -> None:
    entries, _result = materialize_committed_repo(tmp_path)
    for entry in first_pair(entries):
        manifest_path = tmp_path / entry["manifest_path"]
        manifest = load_yaml(manifest_path)
        manifest.pop("execution_state", None)
        write_yaml(manifest_path, manifest)

    result = evaluate_runtime_contract(tmp_path)
    errors = validate_runtime_completion_truth(tmp_path)

    assert result["status"] == "failed"
    assert result["metrics"]["attempt_count"] == EXPECTED_ATTEMPT_COUNT
    assert result["metrics"]["stored_execution_projection_mismatch"] == 2
    assert any("stored runtime_probe_complete projection conflicts" in error for error in errors)


def test_unexpected_target_attempt_fails_inventory_bound_evaluator(tmp_path: Path) -> None:
    materialize_committed_repo(tmp_path)
    extra_root = tmp_path / "runtime/mt5_attempts/attempt_wave01_unregistered_l4_validation_v0"
    extra_root.mkdir(parents=True)
    write_yaml(extra_root / "attempt_manifest.yaml", {"attempt_id": extra_root.name})

    result = evaluate_runtime_contract(tmp_path)

    assert result["status"] == "failed"
    assert result["metrics"]["unexpected_target_present"] == 1


def test_duplicate_inventory_attempt_id_fails(tmp_path: Path) -> None:
    materialize_committed_repo(tmp_path)
    inventory = load_yaml(tmp_path / INVENTORY_REL_PATH)
    inventory["attempts"][1]["attempt_id"] = inventory["attempts"][0]["attempt_id"]
    write_yaml(tmp_path / INVENTORY_REL_PATH, inventory)

    result = evaluate_runtime_contract(tmp_path)

    assert result["status"] == "failed"
    assert result["metrics"]["duplicate_attempt_id"] == 1
    assert any("duplicate attempt_id" in error for error in validate_runtime_graph_target_inventory(tmp_path))


def test_receipt_attempt_id_mismatch_fails_binding_and_check_mode(tmp_path: Path) -> None:
    entries, _result = materialize_committed_repo(tmp_path)
    target = entries[0]
    before = receipt_path(tmp_path, target).read_text(encoding="utf-8")
    mutate_receipt(tmp_path, target, attempt_id="attempt_wave01_other_l4_validation_v0")

    result = evaluate_runtime_contract(tmp_path)
    check = run_receipt_migration(tmp_path, write=False)

    assert result["status"] == "failed"
    assert result["metrics"]["receipt_to_attempt_binding_failure"] == 1
    assert check["receipt_binding_failure_count"] == 1
    assert receipt_path(tmp_path, target).read_text(encoding="utf-8") != before


def test_receipt_source_sha_differs_from_stored_sha_fails(tmp_path: Path) -> None:
    entries, _result = materialize_committed_repo(tmp_path)
    mutate_receipt(tmp_path, entries[0], source_report_sha256="b" * 64)

    result = evaluate_runtime_contract(tmp_path)

    assert result["status"] == "failed"
    assert result["metrics"]["receipt_to_attempt_binding_failure"] == 1
    assert any(
        "source_report_sha256_differs_from_stored_sha256" in str(item)
        for item in result["findings"]
    )


def test_missing_stored_report_sha_fails_historical_completion(tmp_path: Path) -> None:
    entries, _result = materialize_committed_repo(tmp_path)
    mutate_receipt(tmp_path, entries[0], stored_report_sha256=None)

    result = evaluate_runtime_contract(tmp_path)

    assert result["status"] == "failed"
    assert result["metrics"]["receipt_to_attempt_binding_failure"] == 1
    assert any("stored_report_sha256_missing" in str(item) for item in result["findings"])


def test_historical_report_mtime_after_terminal_end_stays_incomplete(tmp_path: Path) -> None:
    target_id = make_entries()[0]["attempt_id"]
    seed_runtime_graph_repo(tmp_path, report_mtime_after_end={target_id})

    result = run_receipt_migration(tmp_path, write=False, rebuild_from_raw=True)
    target = next(item for item in result["diagnostics"] if item["attempt_id"] == target_id)

    assert result["attempts_incomplete"] == 1
    assert target["receipt_completed"] is False
    assert "tester_report_completed" in target["missing_requirements"]


def test_replace_report_disabled_stays_incomplete(tmp_path: Path) -> None:
    target_id = make_entries()[0]["attempt_id"]
    seed_runtime_graph_repo(tmp_path, replace_report_disabled={target_id})

    result = run_receipt_migration(tmp_path, write=False, rebuild_from_raw=True)
    target = next(item for item in result["diagnostics"] if item["attempt_id"] == target_id)

    assert result["attempts_incomplete"] == 1
    assert target["replace_report_enabled"] is False
    assert target["receipt_completed"] is False


def test_missing_raw_report_does_not_fabricate_receipt_or_completion(tmp_path: Path) -> None:
    target_id = make_entries()[0]["attempt_id"]
    seed_runtime_graph_repo(tmp_path, raw_report_missing={target_id})

    result = run_receipt_migration(tmp_path, write=False, rebuild_from_raw=True)
    target = next(item for item in result["diagnostics"] if item["attempt_id"] == target_id)

    assert result["report_receipts_missing"] == 1
    assert result["attempts_incomplete"] == 1
    assert target["receipt_completed"] is False
    assert target["used_committed_receipt"] is False


def test_historical_receipt_does_not_claim_fabricated_prelaunch_absence(tmp_path: Path) -> None:
    entries, _result = materialize_committed_repo(tmp_path)
    receipt = load_yaml(receipt_path(tmp_path, entries[0]))

    assert receipt["freshness_reason"] == HISTORICAL_FRESHNESS_REASON
    assert receipt["prelaunch_observation_available"] is False
    assert receipt["freshness_reason"] != "absent_prelaunch_created_after_launch"


def test_registry_inventory_and_receipts_roll_back_together(tmp_path: Path) -> None:
    entries = seed_runtime_graph_repo(tmp_path)
    first_manifest = tmp_path / entries[0]["manifest_path"]
    original_manifest = first_manifest.read_text(encoding="utf-8")
    registry_path = tmp_path / "docs/registers/artifact_registry.csv"
    original_registry = registry_path.read_text(encoding="utf-8")

    result = run_receipt_migration(
        tmp_path,
        write=True,
        rebuild_from_raw=True,
        fail_after_replace_count=2,
    )

    assert result["transaction_status"] == "rolled_back_commit_failure"
    assert first_manifest.read_text(encoding="utf-8") == original_manifest
    assert registry_path.read_text(encoding="utf-8") == original_registry
    assert not (tmp_path / INVENTORY_REL_PATH).exists()
    assert not receipt_path(tmp_path, entries[0]).exists()


def test_receipt_artifact_rows_are_present_and_hash_valid(tmp_path: Path) -> None:
    materialize_committed_repo(tmp_path)

    errors = validate_receipt_artifact_rows(tmp_path)
    rows = list(csv.DictReader((tmp_path / "docs/registers/artifact_registry.csv").open(encoding="utf-8")))
    receipt_rows = [row for row in rows if row["artifact_type"] == "tester_report_receipt"]

    assert errors == []
    assert len(receipt_rows) == EXPECTED_ATTEMPT_COUNT
    for row in receipt_rows:
        path = tmp_path / row["path_or_uri"]
        assert row["sha256"] == file_sha256(path)
        assert str(path.stat().st_size) == row["size_bytes"]


def test_aborted_precondition_cli_status_is_nonzero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        migration_cli,
        "run",
        lambda *_args, **_kwargs: {"transaction_status": "aborted_precondition_failed"},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["materialize_runtime_report_receipts_v1.py", "--repo-root", str(tmp_path), "--write"],
    )

    assert migration_cli.main() == 1


def test_rolled_back_transaction_cli_status_is_nonzero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        migration_cli,
        "run",
        lambda *_args, **_kwargs: {"transaction_status": "rolled_back_commit_failure"},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["materialize_runtime_report_receipts_v1.py", "--repo-root", str(tmp_path), "--write"],
    )

    assert migration_cli.main() == 1


def test_evaluator_digest_is_independent_of_inventory_discovery_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    materialize_committed_repo(tmp_path)
    first = evaluator_mod.evaluate_runtime_contract(tmp_path)
    original_inventory_attempts = evaluator_mod.inventory_attempts

    def reversed_inventory_attempts(inventory: dict[str, Any]) -> list[dict[str, Any]]:
        return list(reversed(original_inventory_attempts(inventory)))

    monkeypatch.setattr(evaluator_mod, "inventory_attempts", reversed_inventory_attempts)
    second = evaluator_mod.evaluate_runtime_contract(tmp_path)

    assert first["status"] == "passed"
    assert second["status"] == "passed"
    assert first["output_sha256"] == second["output_sha256"]
