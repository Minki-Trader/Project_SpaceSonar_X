from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

import pytest
import yaml

from spacesonar.control_plane.provenance import (
    BatchReceiptError,
    DirtySourceError,
    add_provenance_compaction_marker,
    build_execution_batch_receipt,
    build_source_snapshot_payload,
    create_attempt_manifest,
    create_run_manifest,
    execution_batch_ref,
    provenance_compaction_marker,
    source_snapshot,
    source_tree_hash,
    validate_execution_batch_receipt,
)


def run(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, text=True, capture_output=True)


def seed_git_repo(root: Path) -> None:
    run(root, "init")
    run(root, "config", "user.email", "test@example.com")
    run(root, "config", "user.name", "Test")
    (root / "src").mkdir()
    (root / "src/module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests/test_seed.py").write_text("def test_seed():\n    assert True\n", encoding="utf-8")
    (root / "docs/contracts").mkdir(parents=True)
    (root / "docs/contracts/seed.yaml").write_text("version: seed\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("# seed\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname = \"seed\"\nversion = \"0.0.0\"\n", encoding="utf-8")
    (root / "lab/runs/run_a").mkdir(parents=True)
    (root / "lab/runs/run_a/manifest.yaml").write_text("status: old\n", encoding="utf-8")
    (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    run(root, "add", ".")
    run(root, "commit", "-m", "seed")


def test_dirty_reusable_source_blocks_durable_run(tmp_path: Path) -> None:
    seed_git_repo(tmp_path)
    (tmp_path / "src/module.py").write_text("VALUE = 2\n", encoding="utf-8")

    with pytest.raises(DirtySourceError):
        build_execution_batch_receipt(
            tmp_path,
            batch_id="batch_a",
            work_item_id="work_a",
            command_argv=["run"],
        )


def test_dirty_expanded_source_surface_blocks_durable_run(tmp_path: Path) -> None:
    mutations = {
        "tests": ("tests/test_seed.py", "def test_seed():\n    assert False\n"),
        "pyproject": ("pyproject.toml", "[project]\nname = \"changed\"\nversion = \"0.0.0\"\n"),
        "agents": ("AGENTS.md", "# changed\n"),
        "contracts": ("docs/contracts/seed.yaml", "version: changed\n"),
    }
    for name, (rel_path, text) in mutations.items():
        repo = tmp_path / name
        repo.mkdir()
        seed_git_repo(repo)
        (repo / rel_path).write_text(text, encoding="utf-8")
        with pytest.raises(DirtySourceError):
            build_execution_batch_receipt(
                repo,
                batch_id=f"batch_{name}",
                work_item_id="work_a",
                command_argv=["run"],
            )


def test_generated_only_dirtiness_does_not_block_run(tmp_path: Path) -> None:
    seed_git_repo(tmp_path)
    (tmp_path / "lab/runs/run_a/manifest.yaml").write_text("status: new\n", encoding="utf-8")

    receipt = build_execution_batch_receipt(
        tmp_path,
        batch_id="batch_generated",
        work_item_id="work_a",
        command_argv=["run"],
    )

    assert receipt["git"]["source_dirty"] is False
    assert receipt["git"]["generated_output_dirty"] is True


def test_exploratory_dirty_mode_records_source_patch_and_batch_ref(tmp_path: Path) -> None:
    seed_git_repo(tmp_path)
    (tmp_path / "src/module.py").write_text("VALUE = 3\n", encoding="utf-8")

    receipt = build_execution_batch_receipt(
        tmp_path,
        batch_id="batch_dirty",
        work_item_id="work_a",
        command_argv=["run", "--allow-exploratory-dirty"],
        allow_exploratory_dirty=True,
    )
    ref = execution_batch_ref(tmp_path, "batch_dirty")

    assert receipt["git"]["source_diff"]["sha256"]
    assert (tmp_path / receipt["git"]["source_snapshot"]["tracked_patch_path"]).exists()
    assert ref["sha256"]


def test_source_tree_hash_is_stable_and_changes_with_source(tmp_path: Path) -> None:
    seed_git_repo(tmp_path)
    first = source_tree_hash(tmp_path)
    assert source_tree_hash(tmp_path) == first

    (tmp_path / "src/module.py").write_text("VALUE = 4\n", encoding="utf-8")

    assert source_tree_hash(tmp_path) != first


def test_staged_change_is_captured(tmp_path: Path) -> None:
    seed_git_repo(tmp_path)
    (tmp_path / "src/module.py").write_text("VALUE = 5\n", encoding="utf-8")
    run(tmp_path, "add", "src/module.py")

    snapshot = source_snapshot(tmp_path, "batch_staged")

    assert snapshot["staged_patch_path"]
    assert snapshot["staged_patch_sha256"]


def test_build_source_snapshot_payload_writes_zero_files(tmp_path: Path) -> None:
    seed_git_repo(tmp_path)
    (tmp_path / "src/module.py").write_text("VALUE = 12\n", encoding="utf-8")

    payload = build_source_snapshot_payload(tmp_path, "batch_payload")

    assert payload["manifest"]["tracked_patch_path"]
    assert not (tmp_path / "lab" / "executions" / "batch_payload").exists()


def test_unstaged_change_is_captured(tmp_path: Path) -> None:
    seed_git_repo(tmp_path)
    (tmp_path / "src/module.py").write_text("VALUE = 6\n", encoding="utf-8")

    snapshot = source_snapshot(tmp_path, "batch_unstaged")

    assert snapshot["tracked_patch_path"]
    assert snapshot["tracked_patch_sha256"]


def test_untracked_source_is_archived(tmp_path: Path) -> None:
    seed_git_repo(tmp_path)
    (tmp_path / "src/new_module.py").write_text("VALUE = 7\n", encoding="utf-8")

    snapshot = source_snapshot(tmp_path, "batch_untracked")

    assert snapshot["untracked_archive_path"]
    assert "src/new_module.py" in snapshot["untracked_paths"]
    with zipfile.ZipFile(tmp_path / snapshot["untracked_archive_path"]) as archive:
        assert "src/new_module.py" in archive.namelist()


def test_untracked_source_archive_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    seed_git_repo(first)
    seed_git_repo(second)
    (first / "src/new_module.py").write_text("VALUE = 7\n", encoding="utf-8")
    (second / "src/new_module.py").write_text("VALUE = 7\n", encoding="utf-8")

    first_snapshot = source_snapshot(first, "batch_untracked")
    second_snapshot = source_snapshot(second, "batch_untracked")

    assert first_snapshot["untracked_archive_sha256"] == second_snapshot["untracked_archive_sha256"]


def test_deleted_source_is_captured(tmp_path: Path) -> None:
    seed_git_repo(tmp_path)
    (tmp_path / "src/module.py").unlink()

    snapshot = source_snapshot(tmp_path, "batch_deleted")

    assert "src/module.py" in snapshot["deleted_paths"]


def test_renamed_source_is_captured(tmp_path: Path) -> None:
    seed_git_repo(tmp_path)
    run(tmp_path, "mv", "src/module.py", "src/module_renamed.py")

    snapshot = source_snapshot(tmp_path, "batch_renamed")

    assert "src/module.py->src/module_renamed.py" in snapshot["renamed_paths"]


def test_binary_source_change_is_captured(tmp_path: Path) -> None:
    seed_git_repo(tmp_path)
    (tmp_path / "src/blob.bin").write_bytes(b"\0old")
    run(tmp_path, "add", "src/blob.bin")
    run(tmp_path, "commit", "-m", "add binary")
    (tmp_path / "src/blob.bin").write_bytes(b"\0new")

    snapshot = source_snapshot(tmp_path, "batch_binary")

    assert "src/blob.bin" in snapshot["binary_source_paths"]
    assert snapshot["tracked_patch_path"]


def test_source_tree_hash_changes_for_each_source_mutation(tmp_path: Path) -> None:
    mutations = {
        "unstaged": lambda repo: (repo / "src/module.py").write_text("VALUE = 8\n", encoding="utf-8"),
        "untracked": lambda repo: (repo / "src/extra.py").write_text("VALUE = 9\n", encoding="utf-8"),
        "deleted": lambda repo: (repo / "src/module.py").unlink(),
        "renamed": lambda repo: run(repo, "mv", "src/module.py", "src/module_renamed.py"),
        "binary": lambda repo: (repo / "src/blob.bin").write_bytes(b"\0new"),
    }
    for name, mutate in mutations.items():
        repo = tmp_path / name
        repo.mkdir()
        seed_git_repo(repo)
        if name == "binary":
            (repo / "src/blob.bin").write_bytes(b"\0old")
            run(repo, "add", "src/blob.bin")
            run(repo, "commit", "-m", "add binary")
        before = source_tree_hash(repo)
        mutate(repo)
        assert source_tree_hash(repo) != before, name


def test_batch_receipt_has_nonempty_inputs_and_outputs(tmp_path: Path) -> None:
    seed_git_repo(tmp_path)

    receipt = build_execution_batch_receipt(
        tmp_path,
        batch_id="batch_complete",
        work_item_id="work_a",
        command_argv=["run"],
    )

    assert receipt["inputs"]
    assert receipt["outputs"]
    assert receipt["git"]["source_snapshot"]["manifest_sha256"]


def test_missing_input_or_output_hash_fails_receipt_validation() -> None:
    receipt = {
        "version": "execution_batch_receipt_v1",
        "batch_id": "batch_hash",
        "work_item_id": "work_a",
        "command_argv": ["run"],
        "cwd": ".",
        "started_at_utc": "2026-06-24T00:00:00.000001Z",
        "ended_at_utc": "2026-06-24T00:00:00.000002Z",
        "git": {"source_snapshot": {"manifest_sha256": "abc"}},
        "environment": {"lock_file_sha256": "abc"},
        "inputs": [{"path": "uv.lock", "sha256": None, "size_bytes": 1}],
        "outputs": [{"path": "out.txt", "sha256": "abc", "size_bytes": None}],
        "claim_boundary": "test",
        "receipt_status": "finalized",
    }

    errors = validate_execution_batch_receipt(receipt)

    assert any("inputs has null path/hash/size" in error for error in errors)
    assert any("outputs has null path/hash/size" in error for error in errors)


def test_finalized_receipt_cannot_be_overwritten(tmp_path: Path) -> None:
    seed_git_repo(tmp_path)
    build_execution_batch_receipt(
        tmp_path,
        batch_id="batch_once",
        work_item_id="work_a",
        command_argv=["run"],
    )

    with pytest.raises(BatchReceiptError):
        build_execution_batch_receipt(
            tmp_path,
            batch_id="batch_once",
            work_item_id="work_a",
            command_argv=["run"],
        )


def test_run_and_attempt_records_reference_batch_receipt(tmp_path: Path) -> None:
    seed_git_repo(tmp_path)
    build_execution_batch_receipt(
        tmp_path,
        batch_id="batch_ref",
        work_item_id="work_a",
        command_argv=["run"],
    )

    run_record = create_run_manifest(tmp_path, {"run_id": "run_a"}, execution_batch_id="batch_ref")
    attempt_record = create_attempt_manifest(tmp_path, {"attempt_id": "attempt_a"}, execution_batch_id="batch_ref")

    assert run_record["execution_batch_ref"]["batch_id"] == "batch_ref"
    assert run_record["version"] == "run_manifest_v3"
    assert run_record["execution_batch_ref"]["sha256"]
    assert attempt_record["version"] == "mt5_attempt_manifest_v2"
    assert attempt_record["execution_batch_ref"]["path"] == "lab/executions/batch_ref/execution_batch_receipt.yaml"


def test_run_and_attempt_creation_requires_batch_ref(tmp_path: Path) -> None:
    with pytest.raises(BatchReceiptError):
        create_run_manifest(tmp_path, {"run_id": "run_a"}, execution_batch_id="")
    with pytest.raises(BatchReceiptError):
        create_attempt_manifest(tmp_path, {"attempt_id": "attempt_a"}, execution_batch_id="")


def test_execution_batch_ref_with_null_sha_fails(tmp_path: Path) -> None:
    receipt_path = tmp_path / "lab" / "executions" / "batch_bad" / "execution_batch_receipt.yaml"
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_text(
        yaml.safe_dump(
            {
                "version": "execution_batch_receipt_v1",
                "batch_id": "batch_bad",
                "work_item_id": "work_a",
                "command_argv": ["run"],
                "cwd": ".",
                "started_at_utc": "2026-06-24T00:00:00.000001Z",
                "ended_at_utc": "2026-06-24T00:00:00.000002Z",
                "git": {"source_snapshot": {"manifest_sha256": None}},
                "environment": {"lock_file_sha256": "abc"},
                "inputs": [{"path": "uv.lock", "sha256": None, "size_bytes": None}],
                "outputs": [{"path": "out.txt", "sha256": None, "size_bytes": None}],
                "claim_boundary": "test",
                "receipt_status": "finalized",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(BatchReceiptError):
        execution_batch_ref(tmp_path, "batch_bad")


def test_historical_provenance_remains_when_compaction_marker_is_added(tmp_path: Path) -> None:
    record_path = tmp_path / "lab/runs/run_a/run_manifest.json"
    record_path.parent.mkdir(parents=True)
    record_path.write_text(
        '{"run_id":"run_a","historical_inline_provenance":{"git_status":["M src/module.py"]}}\n',
        encoding="utf-8",
    )

    changed = add_provenance_compaction_marker(
        record_path,
        "lab/executions/batch_control_plane_stabilization_v2_runtime_revalidation/execution_batch_receipt.yaml",
    )

    assert changed is True
    text = record_path.read_text(encoding="utf-8")
    assert "historical_inline_provenance" in text
    assert "provenance_compaction" in text
    assert provenance_compaction_marker(
        "lab/executions/batch_control_plane_stabilization_v2_runtime_revalidation/execution_batch_receipt.yaml"
    )["historical_inline_provenance_retained"] is True
