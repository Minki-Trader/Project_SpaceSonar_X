from __future__ import annotations

import csv
from pathlib import Path

import yaml

from foundation.validation.execution_provenance_validator import (
    _validate_execution_refs,
    _validate_historical_regeneration_lineage,
    validate,
)
from spacesonar.control_plane.provenance import validate_execution_batch_receipt


def test_same_path_with_conflicting_batch_hashes_fails() -> None:
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

    assert any("conflicting hashes for same.txt" in error for error in validate_execution_batch_receipt(receipt))


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
