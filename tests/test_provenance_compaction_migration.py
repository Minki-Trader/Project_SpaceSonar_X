from __future__ import annotations

from pathlib import Path

from foundation.migrations import compact_historical_execution_provenance_v1 as migration
from spacesonar.control_plane.store import read_yaml


def test_migration_check_is_idempotent_on_committed_repo() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    report = migration.run(repo_root, write=False)

    assert report["status"] == "passed"
    assert report["changed_record_count"] == 0


def test_migration_inventory_contains_exact_37_88_125() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    inventory = read_yaml(repo_root / migration.MIGRATION_INVENTORY_PATH)

    assert inventory["record_counts"] == {
        "run_manifest": 37,
        "attempt_manifest": 88,
        "total": 125,
    }
    assert len(inventory["entries"]) == 125
    assert {entry["compaction_role"] for entry in inventory["entries"]} == {
        "metadata_compaction_only_not_original_execution_identity"
    }


def test_migration_rollback_restores_staged_records(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "a.txt"
    target.write_text("before\n", encoding="utf-8")

    def fake_build_plan(repo_root: Path) -> dict:
        return {
            "staged_texts": {Path("a.txt"): "after\n", Path("b.txt"): "new\n"},
            "inventory": {"record_counts": {"run_manifest": 1, "attempt_manifest": 1, "total": 2}},
            "receipt": {},
            "runtime_evaluator": {"status": "passed"},
        }

    monkeypatch.setattr(migration, "build_plan", fake_build_plan)
    monkeypatch.setattr(migration, "validate_execution_provenance", lambda repo_root: [])

    report = migration.run(tmp_path, write=True, fail_after_replace_count=1)

    assert report["transaction_status"] == "rolled_back_commit_failure"
    assert target.read_text(encoding="utf-8") == "before\n"
    assert not (tmp_path / "b.txt").exists()
    assert not (tmp_path / migration.FINALIZATION_RECEIPT_PATH).exists()


def test_runtime_evaluator_references_changed_attempt_hashes() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    inventory = read_yaml(repo_root / migration.MIGRATION_INVENTORY_PATH)
    evaluator = read_yaml(repo_root / migration.RUNTIME_EVALUATOR_PATH)
    input_hashes = evaluator.get("input_hashes") or []
    target_paths = {item.get("path"): item for item in input_hashes}
    first_attempt = next(
        entry
        for entry in inventory["entries"]
        if entry["record_type"] == "attempt_manifest" and entry["path"] in target_paths
    )

    assert target_paths[first_attempt["path"]]["sha256"] == first_attempt["post_migration_sha256"]


def test_receipt_input_and_output_hashes_match_inventory_pre_and_post() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    inventory = read_yaml(repo_root / migration.MIGRATION_INVENTORY_PATH)
    receipt = read_yaml(repo_root / migration.BATCH_RECEIPT_PATH)
    inputs = {item["path_at_execution"]: item for item in receipt["inputs"]}
    outputs = {item["path_at_execution"]: item for item in receipt["outputs"]}

    for entry in inventory["entries"]:
        assert inputs[entry["path"]]["sha256_at_start"] == entry["pre_migration_sha256"]
        assert outputs[entry["path"]]["sha256_at_end"] == entry["post_migration_sha256"]


def test_wp06_receipt_is_locked_and_noop_check_preserves_hash() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    before = (repo_root / migration.BATCH_RECEIPT_PATH).read_bytes()

    report = migration.run(repo_root, write=False)

    assert report["status"] == "passed"
    assert (repo_root / migration.BATCH_RECEIPT_PATH).read_bytes() == before


def test_migration_check_reports_finalized_receipt_drift(monkeypatch, tmp_path: Path) -> None:
    def fake_build_plan(repo_root: Path, **kwargs) -> dict:
        return {
            "staged_texts": {},
            "staged_bytes": {},
            "inventory": {"record_counts": {"run_manifest": 37, "attempt_manifest": 88, "total": 125}},
            "receipt": {},
            "runtime_evaluator": {"status": "passed"},
        }

    monkeypatch.setattr(migration, "build_plan", fake_build_plan)
    monkeypatch.setattr(migration, "validate_execution_provenance", lambda repo_root: ["receipt drift"])

    report = migration.run(tmp_path, write=False)

    assert report["status"] == "failed"
    assert report["failure_reason"] == "finalized_receipt_drift"


def test_migration_check_writes_zero_files() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    receipt_before = (repo_root / migration.BATCH_RECEIPT_PATH).read_bytes()
    final_before = (repo_root / migration.FINALIZATION_RECEIPT_PATH).read_bytes()

    report = migration.run(repo_root, write=False)

    assert report["status"] == "passed"
    assert (repo_root / migration.BATCH_RECEIPT_PATH).read_bytes() == receipt_before
    assert (repo_root / migration.FINALIZATION_RECEIPT_PATH).read_bytes() == final_before
