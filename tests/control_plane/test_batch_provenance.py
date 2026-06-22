from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from spacesonar.control_plane.provenance import (
    DirtySourceError,
    build_execution_batch_receipt,
    execution_batch_ref,
    source_tree_hash,
)


def run(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, text=True, capture_output=True)


def seed_git_repo(root: Path) -> None:
    run(root, "init")
    run(root, "config", "user.email", "test@example.com")
    run(root, "config", "user.name", "Test")
    (root / "src").mkdir()
    (root / "src/module.py").write_text("VALUE = 1\n", encoding="utf-8")
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
    assert (tmp_path / "lab/executions/batch_dirty/source.patch").exists()
    assert ref["sha256"]


def test_source_tree_hash_is_stable_and_changes_with_source(tmp_path: Path) -> None:
    seed_git_repo(tmp_path)
    first = source_tree_hash(tmp_path)
    assert source_tree_hash(tmp_path) == first

    (tmp_path / "src/module.py").write_text("VALUE = 4\n", encoding="utf-8")

    assert source_tree_hash(tmp_path) != first
