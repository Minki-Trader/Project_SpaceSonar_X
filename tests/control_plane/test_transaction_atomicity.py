from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from spacesonar import cli
from spacesonar.control_plane import transaction as transaction_module
from spacesonar.control_plane.models import ExecutionContext, TransactionResult
from spacesonar.control_plane.store import sha256_file
from spacesonar.control_plane.transaction import ControlPlaneTransaction


def ctx(tmp_path: Path) -> ExecutionContext:
    return ExecutionContext(tmp_path, "work_test", "test_claim_boundary", ("test",))


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def init_git_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)


def test_validation_failure_commits_zero_files(tmp_path: Path) -> None:
    tx = ControlPlaneTransaction(ctx(tmp_path), tx_id="tx_test_validation")
    tx.stage_text("docs/current.yaml", "value: staged\n")

    result = tx.commit(validate=lambda _future: ["schema failed"])

    assert result.status == "aborted_validation_failed"
    assert not (tmp_path / "docs/current.yaml").exists()
    receipt = load_yaml(result.receipt_path)
    assert receipt["committed_output_hashes"] == []
    assert receipt["rollback_required"] is False


def test_validator_exception_is_validation_failure_with_zero_canonical_changes(tmp_path: Path) -> None:
    target = tmp_path / "docs/current.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("value: original\n", encoding="utf-8")
    tx = ControlPlaneTransaction(ctx(tmp_path), tx_id="tx_test_validator_exception")
    tx.stage_text("docs/current.yaml", "value: staged\n")

    def validate(_future: Path) -> list[str]:
        raise ValueError("broken graph")

    result = tx.commit(validate=validate)

    assert result.status == "aborted_validation_failed"
    assert target.read_text(encoding="utf-8") == "value: original\n"
    receipt = load_yaml(result.receipt_path)
    assert receipt["errors"] == ["ValueError: broken graph"]
    assert receipt["committed_output_hashes"] == []


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
    receipt = load_yaml(result.receipt_path)
    assert receipt["input_hashes"] == [{"path": "docs/current.yaml", "existed": True, "sha256": original_hash}]
    assert receipt["committed_output_hashes"] == []


def test_target_change_inside_validation_aborts_and_preserves_concurrent_content(tmp_path: Path) -> None:
    target = tmp_path / "docs/current.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("value: original\n", encoding="utf-8")
    tx = ControlPlaneTransaction(ctx(tmp_path), tx_id="tx_test_validation_race")
    tx.stage_text("docs/current.yaml", "value: staged\n")

    def validate(_future: Path) -> list[str]:
        target.write_text("value: concurrent-writer\n", encoding="utf-8")
        return []

    result = tx.commit(validate=validate)

    assert result.status == "aborted_precondition_failed"
    assert target.read_text(encoding="utf-8") == "value: concurrent-writer\n"
    assert "docs/current.yaml" in result.errors[0]


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
    receipt = load_yaml(result.receipt_path)
    journal = load_yaml(tmp_path / receipt["commit_journal_path"])
    assert receipt["committed_paths"] == []
    assert receipt["committed_output_hashes"] == []
    assert receipt["applied_paths_before_failure"] == ["docs/a.txt"]
    assert receipt["rollback_required"] is False
    assert receipt["rollback_errors"] == []
    assert len(receipt["preimages"]) == 2
    assert journal["state"] == "rolled_back"
    assert journal["applied_paths"] == ["docs/a.txt"]
    assert sorted(journal["rollback_paths"]) == ["docs/a.txt", "docs/b.txt"]


def test_failure_before_final_receipt_restores_all_canonical_files(tmp_path: Path) -> None:
    first = tmp_path / "docs/a.txt"
    second = tmp_path / "docs/b.txt"
    first.parent.mkdir(parents=True)
    first.write_text("A0\n", encoding="utf-8")
    second.write_text("B0\n", encoding="utf-8")
    tx = ControlPlaneTransaction(ctx(tmp_path), tx_id="tx_test_finalize_failure")
    tx.stage_text("docs/a.txt", "A1\n")
    tx.stage_text("docs/b.txt", "B1\n")

    result = tx.commit(fail_before_final_receipt=True)

    assert result.status == "rolled_back_commit_failure"
    assert first.read_text(encoding="utf-8") == "A0\n"
    assert second.read_text(encoding="utf-8") == "B0\n"
    receipt = load_yaml(result.receipt_path)
    journal = load_yaml(tmp_path / receipt["commit_journal_path"])
    assert receipt["applied_paths_before_failure"] == ["docs/a.txt", "docs/b.txt"]
    assert journal["state"] == "rolled_back"


def test_actual_receipt_write_failure_after_replacements_still_rolls_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "docs/a.txt"
    second = tmp_path / "docs/b.txt"
    first.parent.mkdir(parents=True)
    first.write_text("A0\n", encoding="utf-8")
    second.write_text("B0\n", encoding="utf-8")
    original_hashes = {first: sha256_file(first), second: sha256_file(second)}
    tx = ControlPlaneTransaction(ctx(tmp_path), tx_id="tx_test_receipt_write_failure")
    tx.stage_text("docs/a.txt", "A1\n")
    tx.stage_text("docs/b.txt", "B1\n")

    def fail_receipt(_receipt: dict) -> None:
        raise OSError("receipt unavailable")

    monkeypatch.setattr(tx, "_write_receipt", fail_receipt)

    result = tx.commit()

    assert result.status == "rolled_back_commit_failure"
    assert first.read_text(encoding="utf-8") == "A0\n"
    assert second.read_text(encoding="utf-8") == "B0\n"
    assert sha256_file(first) == original_hashes[first]
    assert sha256_file(second) == original_hashes[second]
    assert any(error.startswith("receipt_persistence_failed:OSError:receipt unavailable") for error in result.errors)
    assert not result.receipt_path.exists()


def test_rollback_journal_write_failure_is_nonfatal_to_canonical_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "docs/a.txt"
    second = tmp_path / "docs/b.txt"
    first.parent.mkdir(parents=True)
    first.write_text("A0\n", encoding="utf-8")
    second.write_text("B0\n", encoding="utf-8")
    original_hashes = {first: sha256_file(first), second: sha256_file(second)}
    tx = ControlPlaneTransaction(ctx(tmp_path), tx_id="tx_test_rollback_journal_failure")
    tx.stage_text("docs/a.txt", "A1\n")
    tx.stage_text("docs/b.txt", "B1\n")
    original_write_journal = tx._write_commit_journal

    def fail_terminal_journal(*, state: str, **kwargs) -> None:
        if state in {"rolled_back", "rollback_failed"}:
            assert first.read_text(encoding="utf-8") == "A0\n"
            assert second.read_text(encoding="utf-8") == "B0\n"
            raise OSError("journal unavailable")
        original_write_journal(state=state, **kwargs)

    monkeypatch.setattr(tx, "_write_commit_journal", fail_terminal_journal)

    result = tx.commit(fail_after_replace_count=1)

    assert result.status == "rolled_back_commit_failure"
    assert sha256_file(first) == original_hashes[first]
    assert sha256_file(second) == original_hashes[second]
    assert any(error.startswith("journal_persistence_failed:OSError:journal unavailable") for error in result.errors)
    receipt = load_yaml(result.receipt_path)
    assert receipt["rollback_verification"] == [
        {"path": "docs/a.txt", "status": "passed", "error": None},
        {"path": "docs/b.txt", "status": "passed", "error": None},
    ]


def test_rollback_still_returns_when_journal_and_receipt_persistence_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "docs/a.txt"
    second = tmp_path / "docs/b.txt"
    first.parent.mkdir(parents=True)
    first.write_text("A0\n", encoding="utf-8")
    second.write_text("B0\n", encoding="utf-8")
    original_hashes = {first: sha256_file(first), second: sha256_file(second)}
    tx = ControlPlaneTransaction(ctx(tmp_path), tx_id="tx_test_all_audit_failure")
    tx.stage_text("docs/a.txt", "A1\n")
    tx.stage_text("docs/b.txt", "B1\n")
    original_write_journal = tx._write_commit_journal

    def fail_terminal_journal(*, state: str, **kwargs) -> None:
        if state in {"rolled_back", "rollback_failed"}:
            raise OSError("journal unavailable")
        original_write_journal(state=state, **kwargs)

    def fail_receipt(_receipt: dict) -> None:
        raise OSError("receipt unavailable")

    monkeypatch.setattr(tx, "_write_commit_journal", fail_terminal_journal)
    monkeypatch.setattr(tx, "_write_receipt", fail_receipt)

    result = tx.commit(fail_after_replace_count=1)

    assert result.status == "rolled_back_commit_failure"
    assert first.read_text(encoding="utf-8") == "A0\n"
    assert second.read_text(encoding="utf-8") == "B0\n"
    assert sha256_file(first) == original_hashes[first]
    assert sha256_file(second) == original_hashes[second]
    assert any(error.startswith("journal_persistence_failed:OSError:journal unavailable") for error in result.errors)
    assert any(error.startswith("receipt_persistence_failed:OSError:receipt unavailable") for error in result.errors)
    assert not result.receipt_path.exists()


def test_input_hashes_are_pre_mutation_and_committed_hashes_are_post_mutation(tmp_path: Path) -> None:
    target = tmp_path / "docs/current.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("value: original\n", encoding="utf-8")
    original_hash = sha256_file(target)
    tx = ControlPlaneTransaction(ctx(tmp_path), tx_id="tx_test_hashes")
    tx.stage_text("docs/current.yaml", "value: staged\n")

    result = tx.commit()

    receipt = load_yaml(result.receipt_path)
    journal = load_yaml(tmp_path / receipt["commit_journal_path"])
    assert result.status == "committed"
    assert journal["state"] == "committed"
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


def test_validator_modifying_future_neighbor_does_not_mutate_canonical_neighbor(tmp_path: Path) -> None:
    neighbor = tmp_path / "docs/neighbor.yaml"
    neighbor.parent.mkdir(parents=True)
    neighbor.write_text("neighbor: original\n", encoding="utf-8")
    original_hash = sha256_file(neighbor)
    tx = ControlPlaneTransaction(ctx(tmp_path), tx_id="tx_test_future_isolated")
    tx.stage_text("docs/current.yaml", "value: staged\n")

    def validate(future_root: Path) -> list[str]:
        (future_root / "docs/neighbor.yaml").write_text("neighbor: mutated-in-future\n", encoding="utf-8")
        return []

    result = tx.commit(validate=validate)

    assert result.status == "committed"
    assert neighbor.read_text(encoding="utf-8") == "neighbor: original\n"
    assert sha256_file(neighbor) == original_hash


def test_identical_target_with_invalid_graph_is_validation_failure_not_noop(tmp_path: Path) -> None:
    target = tmp_path / "docs/current.yaml"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"value: stable\n")
    tx = ControlPlaneTransaction(ctx(tmp_path), tx_id="tx_test_noop_invalid")
    tx.stage_text("docs/current.yaml", "value: stable\n")

    result = tx.commit(validate=lambda _future: ["graph invalid"])

    assert result.status == "aborted_validation_failed"
    assert target.read_text(encoding="utf-8") == "value: stable\n"


def test_identical_second_command_is_true_noop_after_validation(tmp_path: Path) -> None:
    target = tmp_path / "docs/current.yaml"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"value: stable\n")
    tx = ControlPlaneTransaction(ctx(tmp_path), tx_id="tx_test_noop")
    tx.stage_text("docs/current.yaml", "value: stable\n")

    result = tx.commit(validate=lambda future: [] if (future / "docs/current.yaml").exists() else ["missing"])

    assert result.status == "noop_already_applied"
    assert result.committed_paths == ()
    assert target.read_text(encoding="utf-8") == "value: stable\n"
    receipt = load_yaml(result.receipt_path)
    assert receipt["committed_paths"] == []
    assert receipt["committed_output_hashes"] == []


def test_two_same_command_transactions_created_in_one_second_are_distinct(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 6, 23, 1, 2, 3, 123456, tzinfo=tz or UTC)

    monkeypatch.setattr(transaction_module, "datetime", FixedDatetime)
    context = ctx(tmp_path)

    first = ControlPlaneTransaction(context)
    second = ControlPlaneTransaction(context)

    assert first.transaction_id != second.transaction_id
    assert first.receipt_path != second.receipt_path
    first.stage_text("docs/a.txt", "A\n")
    assert first.commit().status == "committed"
    first_receipt = first.receipt_path.read_text(encoding="utf-8")
    second.stage_text("docs/b.txt", "B\n")
    assert second.commit().status == "committed"
    assert first.receipt_path.read_text(encoding="utf-8") == first_receipt


def test_long_transaction_id_uses_short_internal_workspace(tmp_path: Path) -> None:
    long_tx_id = f"tx_{'x' * 80}"
    tx = ControlPlaneTransaction(ctx(tmp_path), tx_id=long_tx_id)
    legacy_future_root = tmp_path / ".spacesonar" / "transactions" / long_tx_id / "future"

    assert tx.receipt_path.parent == tmp_path / ".spacesonar" / "transactions" / long_tx_id
    assert transaction_module.short_workspace_id(long_tx_id) in tx.future_root.parts
    assert tx.future_root.name == "f"
    assert len(str(tx.future_root)) < len(str(legacy_future_root))

    tx.stage_text("docs/current.txt", "current\n")
    observed: list[Path] = []

    def validate(future_root: Path) -> list[str]:
        observed.append(future_root)
        return [] if (future_root / "docs/current.txt").exists() else ["staged file missing"]

    result = tx.commit(validate=validate)

    assert result.status == "committed"
    assert observed == [tx.future_root]


def test_explicit_transaction_id_with_existing_directory_fails_before_staging(tmp_path: Path) -> None:
    existing = tmp_path / ".spacesonar/transactions/tx_existing"
    existing.mkdir(parents=True)

    with pytest.raises(FileExistsError):
        ControlPlaneTransaction(ctx(tmp_path), tx_id="tx_existing")

    assert list(existing.iterdir()) == []


def test_ignored_heavy_artifact_is_absent_from_git_future_tree(tmp_path: Path) -> None:
    init_git_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("ignored-heavy.bin\n.spacesonar/transactions/\n", encoding="utf-8")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "kept.txt").write_text("kept\n", encoding="utf-8")
    (tmp_path / "ignored-heavy.bin").write_bytes(b"heavy")
    tx = ControlPlaneTransaction(ctx(tmp_path), tx_id="tx_test_git_future")
    tx.stage_text("docs/current.txt", "current\n")

    def validate(future_root: Path) -> list[str]:
        errors: list[str] = []
        if (future_root / "ignored-heavy.bin").exists():
            errors.append("ignored heavy artifact copied")
        if not (future_root / "docs/kept.txt").exists():
            errors.append("unignored neighbor missing")
        return errors

    result = tx.commit(validate=validate)

    assert result.status == "committed"


def test_successful_stage_delete_records_hashes_and_validation_sees_deletion(tmp_path: Path) -> None:
    target = tmp_path / "docs/delete-me.txt"
    target.parent.mkdir(parents=True)
    target.write_text("remove\n", encoding="utf-8")
    original_hash = sha256_file(target)
    tx = ControlPlaneTransaction(ctx(tmp_path), tx_id="tx_test_delete")
    tx.stage_delete("docs/delete-me.txt")

    def validate(future_root: Path) -> list[str]:
        return ["delete target still visible"] if (future_root / "docs/delete-me.txt").exists() else []

    result = tx.commit(validate=validate)

    assert result.status == "committed"
    assert not target.exists()
    receipt = load_yaml(result.receipt_path)
    assert receipt["input_hashes"] == [{"path": "docs/delete-me.txt", "existed": True, "sha256": original_hash}]
    assert receipt["committed_output_hashes"] == [
        {"path": "docs/delete-me.txt", "existed": False, "sha256": None}
    ]


def test_stage_delete_rolls_back_after_injected_failure(tmp_path: Path) -> None:
    target = tmp_path / "docs/delete-me.txt"
    target.parent.mkdir(parents=True)
    target.write_text("remove\n", encoding="utf-8")
    original_hash = sha256_file(target)
    tx = ControlPlaneTransaction(ctx(tmp_path), tx_id="tx_test_delete_rollback")
    tx.stage_delete("docs/delete-me.txt")

    result = tx.commit(fail_after_replace_count=1)

    assert result.status == "rolled_back_commit_failure"
    assert target.exists()
    assert sha256_file(target) == original_hash
    receipt = load_yaml(result.receipt_path)
    assert receipt["applied_paths_before_failure"] == ["docs/delete-me.txt"]
    assert receipt["committed_output_hashes"] == []


def test_delete_absent_file_is_noop_with_absent_input_hash(tmp_path: Path) -> None:
    tx = ControlPlaneTransaction(ctx(tmp_path), tx_id="tx_test_delete_absent")
    tx.stage_delete("docs/missing.txt")

    result = tx.commit(validate=lambda future: [] if not (future / "docs/missing.txt").exists() else ["still exists"])

    assert result.status == "noop_already_applied"
    receipt = load_yaml(result.receipt_path)
    assert receipt["input_hashes"] == [{"path": "docs/missing.txt", "existed": False, "sha256": None}]
    assert receipt["committed_output_hashes"] == []


@pytest.mark.parametrize("bad_path", ["", ".", ".git/config", ".spacesonar/transactions/x", ".venv/x", "../x"])
def test_reserved_or_invalid_transaction_paths_are_rejected(tmp_path: Path, bad_path: str) -> None:
    tx = ControlPlaneTransaction(ctx(tmp_path), tx_id=f"tx_bad_{abs(hash(bad_path))}")

    with pytest.raises(ValueError):
        tx.stage_text(bad_path, "bad\n")


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
    monkeypatch: pytest.MonkeyPatch,
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
