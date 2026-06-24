from __future__ import annotations

import csv
import hashlib
from io import StringIO
from pathlib import Path

import yaml

from foundation.validation.execution_provenance_validator import (
    _validate_execution_refs,
    _validate_historical_regeneration_lineage,
    validate,
    validate_agent_work_receipt,
)
from spacesonar.control_plane.store import read_yaml
from spacesonar.control_plane.provenance import validate_execution_batch_receipt


def test_same_path_may_have_different_pre_and_post_hashes() -> None:
    receipt = {
        "version": "execution_batch_receipt_v1",
        "batch_id": "batch_conflict",
        "work_item_id": "work_a",
        "command_argv": ["run"],
        "cwd": ".",
        "started_at_utc": "2026-06-24T00:00:00.000001Z",
        "ended_at_utc": "2026-06-24T00:00:00.000002Z",
        "git": {"source_snapshot": {"manifest_sha256": "abc"}},
        "environment": {"lock_file_sha256": "abc"},
        "inputs": [{"path": "same.txt", "sha256": "aaa", "size_bytes": 1}],
        "outputs": [{"path": "same.txt", "sha256": "bbb", "size_bytes": 1}],
        "claim_boundary": "test",
        "receipt_status": "finalized",
    }

    assert not any("conflicting hashes for same.txt" in error for error in validate_execution_batch_receipt(receipt))


def test_conflicting_duplicate_hash_within_same_phase_fails() -> None:
    receipt = {
        "version": "execution_batch_receipt_v1",
        "batch_id": "batch_conflict",
        "work_item_id": "work_a",
        "command_argv": ["run"],
        "cwd": ".",
        "started_at_utc": "2026-06-24T00:00:00.000001Z",
        "ended_at_utc": "2026-06-24T00:00:00.000002Z",
        "git": {"source_snapshot": {"manifest_sha256": "abc"}},
        "environment": {"lock_file_sha256": "abc"},
        "inputs": [
            {"path_at_execution": "same.txt", "sha256_at_start": "aaa", "size_bytes_at_start": 1},
            {"path_at_execution": "same.txt", "sha256_at_start": "bbb", "size_bytes_at_start": 1},
        ],
        "outputs": [{"path_at_execution": "same.txt", "sha256_at_end": "ccc", "size_bytes_at_end": 1}],
        "claim_boundary": "test",
        "receipt_status": "finalized",
    }

    assert any("conflicting inputs hashes for same.txt" in error for error in validate_execution_batch_receipt(receipt))


def test_execution_batch_ref_with_null_sha_fails(tmp_path: Path) -> None:
    receipt_path = tmp_path / "lab" / "executions" / "batch_ref" / "execution_batch_receipt.yaml"
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_text(
        yaml.safe_dump(
            {
                "version": "execution_batch_receipt_v1",
                "batch_id": "batch_ref",
                "work_item_id": "work_a",
                "command_argv": ["run"],
                "cwd": ".",
                "started_at_utc": "2026-06-24T00:00:00.000001Z",
                "ended_at_utc": "2026-06-24T00:00:00.000002Z",
                "git": {"source_snapshot": {"manifest_sha256": "abc"}},
                "environment": {"lock_file_sha256": "abc"},
                "inputs": [{"path": "uv.lock", "sha256": "abc", "size_bytes": 1}],
                "outputs": [{"path": "out.txt", "sha256": "def", "size_bytes": 1}],
                "claim_boundary": "test",
                "receipt_status": "finalized",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    run_path = tmp_path / "lab" / "runs" / "run_a" / "run_manifest.json"
    run_path.parent.mkdir(parents=True)
    run_path.write_text(
        '{"run_id":"run_a","execution_batch_ref":{"batch_id":"batch_ref","path":"lab/executions/batch_ref/execution_batch_receipt.yaml","sha256":null}}\n',
        encoding="utf-8",
    )

    errors = _validate_execution_refs(tmp_path)

    assert any("execution_batch_ref sha256 mismatch" in error for error in errors)


def test_new_run_and_attempt_without_batch_ref_fail(tmp_path: Path) -> None:
    run_path = tmp_path / "lab" / "runs" / "run_new" / "run_manifest.json"
    run_path.parent.mkdir(parents=True)
    run_path.write_text('{"version":"run_manifest_v3","run_id":"run_new"}\n', encoding="utf-8")
    attempt_path = tmp_path / "runtime" / "mt5_attempts" / "attempt_new" / "attempt_manifest.yaml"
    attempt_path.parent.mkdir(parents=True)
    attempt_path.write_text("version: mt5_attempt_manifest_v2\nattempt_id: attempt_new\n", encoding="utf-8")

    errors = _validate_execution_refs(tmp_path)

    assert any("execution_batch_ref missing for run_manifest_v3" in error for error in errors)
    assert any("execution_batch_ref missing for mt5_attempt_manifest_v2" in error for error in errors)


def test_disabled_regeneration_command_is_rejected(tmp_path: Path) -> None:
    legacy_path = tmp_path / "docs" / "agent_control" / "legacy_lifecycle_entrypoints.yaml"
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text(
        yaml.safe_dump(
            {
                "entrypoints": [
                    {
                        "path": "foundation/pipelines/old_lifecycle.py",
                        "classification": "historical_disabled",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    registry_path = tmp_path / "docs" / "registers" / "artifact_registry.csv"
    registry_path.parent.mkdir(parents=True)
    with registry_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["artifact_id", "path_or_uri", "producer_command", "regeneration_command"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "artifact_id": "artifact_old",
                "path_or_uri": "lab/old.yaml",
                "producer_command": "python foundation/pipelines/old_lifecycle.py",
                "regeneration_command": "python foundation/pipelines/old_lifecycle.py",
            }
        )

    errors = _validate_historical_regeneration_lineage(tmp_path)

    assert any("historical-disabled entrypoint without lineage marker" in error for error in errors)


def test_committed_wp06_provenance_state_validates() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    assert validate(repo_root) == []


def test_wp06_source_tree_hashes_and_finalization_anchor_match() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    receipt = read_yaml(repo_root / "lab/executions/batch_control_plane_corrective_v3_wp06_provenance_compaction/execution_batch_receipt.yaml")
    snapshot_ref = receipt["git"]["source_snapshot"]
    snapshot = read_yaml(repo_root / snapshot_ref["manifest_path"])
    finalization = read_yaml(repo_root / "lab/executions/batch_control_plane_corrective_v3_wp06_provenance_compaction/batch_finalization_receipt.yaml")

    assert receipt["git"]["source_tree_hash_at_start"] == snapshot_ref["source_tree_hash"]
    assert snapshot_ref["source_tree_hash"] == snapshot["source_tree_hash"]
    assert finalization["execution_batch_receipt_sha256"]
    assert finalization["transaction_receipt_sha256"]


def test_wp06_actual_timing_and_effect_inventory_are_exact() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    root = repo_root / "lab/executions/batch_control_plane_corrective_v3_wp06_provenance_compaction"
    start = read_yaml(root / "batch_start_receipt.yaml")
    receipt = read_yaml(root / "execution_batch_receipt.yaml")
    tx = read_yaml(root / "transaction_receipt.yaml")
    finalization = read_yaml(root / "batch_finalization_receipt.yaml")
    effects = read_yaml(root / "effect_inventory.yaml")

    assert receipt["started_at_utc"] == start["started_at_utc"]
    assert receipt["ended_at_utc"] == finalization["finalized_at_utc"]
    assert start["started_at_utc"] < tx["committed_at_utc"] <= finalization["finalized_at_utc"]
    assert tx["input_hashes"]
    assert set(tx["applied_paths"]) == set(effects["mutable_effect_paths"])
    assert set(tx["applied_paths"]) == {item["path"] for item in effects["effects"]}
    assert any(item["effect_type"] == "unchanged_projection" for item in effects["effects"])


def test_wp06_artifact_delta_reconstructs_registry() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    root = repo_root / "lab/executions/batch_control_plane_corrective_v3_wp06_provenance_compaction"
    delta = read_yaml(root / "evidence" / "artifact_registry_delta.yaml")
    old_snapshot = root / "evidence" / "artifact_registry_before.csv"
    with old_snapshot.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = {row["artifact_id"]: dict(row) for row in reader if row.get("artifact_id")}
    for item in delta["row_deltas"]:
        if item["new_row"] is None:
            rows.pop(item["artifact_id"], None)
        else:
            rows[item["artifact_id"]] = item["new_row"]
    handle = StringIO()
    writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in sorted(rows.values(), key=lambda value: str(value.get("path_or_uri") or "")):
        writer.writerow({key: "" if row.get(key) is None else row.get(key, "") for key in fieldnames})

    assert hashlib.sha256(handle.getvalue().encode("utf-8")).hexdigest() == delta["new_registry_sha256"]


def test_wp06_work_receipt_validates_and_tamper_fails(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    source = repo_root / "docs/workspace/agent_work_receipts/WP06.yaml"
    target = tmp_path / "docs/workspace/agent_work_receipts/WP06.yaml"
    target.parent.mkdir(parents=True)
    target.write_bytes(source.read_bytes())
    # Copy only referenced files needed for the hash-bound check.
    receipt = read_yaml(source)
    for ref in [*receipt.get("source_refs", []), receipt["wp06_batch_receipt_ref"], receipt["transaction_receipt_ref"], receipt["finalization_receipt_ref"]]:
        src = repo_root / ref["path"]
        dst = tmp_path / ref["path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())

    assert validate_agent_work_receipt(tmp_path, Path("docs/workspace/agent_work_receipts/WP06.yaml")) == []

    tampered = target.read_text(encoding="utf-8").replace("agent_mode: solo", "agent_mode: micro_specialist")
    target.write_text(tampered, encoding="utf-8")

    assert any("self-hash mismatch" in error for error in validate_agent_work_receipt(tmp_path, Path("docs/workspace/agent_work_receipts/WP06.yaml")))


def test_wp06_work_receipt_survives_canonical_progress_change(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    source = repo_root / "docs/workspace/agent_work_receipts/WP06.yaml"
    target = tmp_path / "docs/workspace/agent_work_receipts/WP06.yaml"
    target.parent.mkdir(parents=True)
    target.write_bytes(source.read_bytes())
    receipt = read_yaml(source)
    for ref in [*receipt.get("source_refs", []), receipt["wp06_batch_receipt_ref"], receipt["transaction_receipt_ref"], receipt["finalization_receipt_ref"]]:
        src = repo_root / ref["path"]
        dst = tmp_path / ref["path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
    progress = tmp_path / "docs/migrations/control_plane_corrective_v3_progress.yaml"
    progress.parent.mkdir(parents=True, exist_ok=True)
    progress.write_text("version: changed_later\n", encoding="utf-8")

    assert validate_agent_work_receipt(tmp_path, Path("docs/workspace/agent_work_receipts/WP06.yaml")) == []
