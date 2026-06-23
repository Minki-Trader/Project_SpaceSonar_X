from __future__ import annotations

from pathlib import Path

import yaml

from spacesonar import cli
from spacesonar.control_plane.models import ExecutionContext, TransactionResult
from spacesonar.control_plane.store import sha256_file
from spacesonar.control_plane.transaction import ControlPlaneTransaction


def ctx(tmp_path: Path) -> ExecutionContext:
    return ExecutionContext(tmp_path, "work_test", "test_claim_boundary", ("test",))


def load_receipt(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_validation_failure_commits_zero_files(tmp_path: Path) -> None:
    tx = ControlPlaneTransaction(ctx(tmp_path), tx_id="tx_test_validation")
    tx.stage_text("docs/current.yaml", "value: staged\n")

    result = tx.commit(validate=lambda _future: ["schema failed"])

    assert result.status == "aborted_validation_failed"
    assert not (tmp_path / "docs/current.yaml").exists()
    receipt = load_receipt(result.receipt_path)
    assert receipt["committed_output_hashes"] == []
    assert receipt["rollback_required"] is False


def test_precondition_failure_commits_zero_files(tmp_path: Path) -> None:
    target = tmp_path / "docs/current.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("value: original\n", encoding="utf-8")
    original_hash = sha256_file(target)
    tx = ControlPlaneTransaction(ctx(tmp_path), tx_id="tx_test_precondition")
    tx.stage_text("docs/current.yaml", "value: staged\n")
    target.write_text("value: changed-outside-transaction\n", encoding="utf-8")

    result = tx.commit()

    assert result.status == "aborted_precondition_failed"
    assert target.read_text(encoding="utf-8") == "value: changed-outside-transaction\n"
    receipt = load_receipt(result.receipt_path)
    assert receipt["input_hashes"] == [{"path": "docs/current.yaml", "existed": True, "sha256": original_hash}]
    assert receipt["committed_output_hashes"] == []


def test_failure_after_first_replacement_restores_all_files(tmp_path: Path) -> None:
    first = tmp_path / "docs/a.txt"
    second = tmp_path / "docs/b.txt"
    first.parent.mkdir(parents=True)
    first.write_text("A0\n", encoding="utf-8")
    second.write_text("B0\n", encoding="utf-8")
    original_hashes = {first: sha256_file(first), second: sha256_file(second)}
    tx = ControlPlaneTransaction(ctx(tmp_path), tx_id="tx_test_rollback")
    tx.stage_text("docs/a.txt", "A1\n")
    tx.stage_text("docs/b.txt", "B1\n")

    result = tx.commit(fail_after_replace_count=1)

    assert result.status == "rolled_back_commit_failure"
    assert first.read_text(encoding="utf-8") == "A0\n"
    assert second.read_text(encoding="utf-8") == "B0\n"
    assert sha256_file(first) == original_hashes[first]
    assert sha256_file(second) == original_hashes[second]
    receipt = load_receipt(result.receipt_path)
    assert receipt["rollback_required"] is False
    assert receipt["rollback_errors"] == []
    assert len(receipt["preimages"]) == 2


def test_input_hashes_are_pre_mutation_and_committed_hashes_are_post_mutation(tmp_path: Path) -> None:
    target = tmp_path / "docs/current.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("value: original\n", encoding="utf-8")
    original_hash = sha256_file(target)
    tx = ControlPlaneTransaction(ctx(tmp_path), tx_id="tx_test_hashes")
    tx.stage_text("docs/current.yaml", "value: staged\n")

    result = tx.commit()

    receipt = load_receipt(result.receipt_path)
    assert result.status == "committed"
    assert receipt["input_hashes"] == [{"path": "docs/current.yaml", "existed": True, "sha256": original_hash}]
    assert receipt["committed_output_hashes"] == [
        {"path": "docs/current.yaml", "existed": True, "sha256": sha256_file(target)}
    ]
    assert receipt["input_hashes"][0]["sha256"] != receipt["committed_output_hashes"][0]["sha256"]


def test_merged_state_validation_can_read_unchanged_neighbors(tmp_path: Path) -> None:
    neighbor = tmp_path / "docs/neighbor.yaml"
    neighbor.parent.mkdir(parents=True)
    neighbor.write_text("neighbor: still-here\n", encoding="utf-8")
    tx = ControlPlaneTransaction(ctx(tmp_path), tx_id="tx_test_merged")
    tx.stage_text("docs/current.yaml", "value: staged\n")

    def validate(future_root: Path) -> list[str]:
        errors: list[str] = []
        if not (future_root / "docs/neighbor.yaml").exists():
            errors.append("unchanged neighbor missing")
        if (future_root / "docs/current.yaml").read_text(encoding="utf-8") != "value: staged\n":
            errors.append("staged replacement missing")
        return errors

    result = tx.commit(validate=validate)

    assert result.status == "committed"
    assert not result.errors


def test_identical_second_command_is_true_noop(tmp_path: Path) -> None:
    target = tmp_path / "docs/current.yaml"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"value: stable\n")
    tx = ControlPlaneTransaction(ctx(tmp_path), tx_id="tx_test_noop")
    tx.stage_text("docs/current.yaml", "value: stable\n")

    result = tx.commit()

    assert result.status == "noop_already_applied"
    assert result.committed_paths == ()
    assert target.read_text(encoding="utf-8") == "value: stable\n"
    receipt = load_receipt(result.receipt_path)
    assert receipt["committed_paths"] == []
    assert receipt["committed_output_hashes"] == []


def test_cli_exit_status_is_nonzero_for_abort_and_rollback_failure(tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.yaml"
    abort = TransactionResult("tx_abort", "aborted_validation_failed", receipt)
    rollback_failed = TransactionResult("tx_rollback", "rollback_failed", receipt)
    noop = TransactionResult("tx_noop", "noop_already_applied", receipt)

    assert cli.transaction_exit_code(abort) == 1
    assert cli.transaction_exit_code(rollback_failed) == 1
    assert cli.transaction_exit_code(noop) == 0


def test_cli_main_returns_nonzero_for_aborted_lifecycle_result(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    spec = tmp_path / "spec.yaml"
    spec.write_text("campaign_id: campaign_test_v0\n", encoding="utf-8")
    receipt = tmp_path / "receipt.yaml"

    monkeypatch.setattr(cli, "current_git_branch", lambda _repo_root: None)
    monkeypatch.setattr(
        cli,
        "open_campaign",
        lambda _spec, _ctx: TransactionResult("tx_abort", "aborted_validation_failed", receipt, errors=("bad",)),
    )

    result = cli.main(["--repo-root", str(tmp_path), "campaign", "open", "--spec", str(spec)])

    assert result == 1
    assert "aborted_validation_failed" in capsys.readouterr().out
