from __future__ import annotations

from pathlib import Path

import yaml

from spacesonar.control_plane.models import ExecutionContext
from spacesonar.control_plane.transaction import ControlPlaneTransaction


def ctx(tmp_path: Path) -> ExecutionContext:
    return ExecutionContext(tmp_path, "work_test", "test_claim_boundary", ("test",))


def test_validation_failure_commits_zero_files(tmp_path: Path) -> None:
    tx = ControlPlaneTransaction(ctx(tmp_path), tx_id="tx_test_validation")
    tx.stage_text("docs/current.yaml", "value: staged\n")

    result = tx.commit(validate=lambda _staged: ["schema failed"])

    assert result.status == "aborted_validation_failed"
    assert not (tmp_path / "docs/current.yaml").exists()
    receipt = yaml.safe_load(result.receipt_path.read_text(encoding="utf-8"))
    assert receipt["committed_output_hashes"] == []


def test_exception_during_staging_commits_zero_files(tmp_path: Path) -> None:
    tx = ControlPlaneTransaction(ctx(tmp_path), tx_id="tx_test_exception")
    try:
        tx.stage_text("../outside.yaml", "nope\n")
    except ValueError:
        pass

    assert not (tmp_path / "outside.yaml").exists()


def test_successful_transaction_updates_all_intended_files(tmp_path: Path) -> None:
    tx = ControlPlaneTransaction(ctx(tmp_path), tx_id="tx_test_success")
    tx.stage_text("docs/a.txt", "A\n")
    tx.stage_text("docs/b.txt", "B\n")

    result = tx.commit()

    assert result.status == "committed"
    assert (tmp_path / "docs/a.txt").read_text(encoding="utf-8") == "A\n"
    assert (tmp_path / "docs/b.txt").read_text(encoding="utf-8") == "B\n"
    assert len(result.committed_paths) == 2
