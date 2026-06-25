from __future__ import annotations

from pathlib import Path

from spacesonar.control_plane.models import ExecutionContext
from spacesonar.control_plane.transaction import ControlPlaneTransaction


def _context(repo_root: Path) -> ExecutionContext:
    return ExecutionContext(
        repo_root=repo_root,
        work_item_id="work_agentproof_transaction_visibility_v1",
        claim_boundary="transaction_visibility_fixture_only_no_runtime_authority",
        command_argv=("pytest", "test_transaction_visibility"),
    )


def test_staged_replacement_is_visible_to_validation_future(tmp_path: Path) -> None:
    tx = ControlPlaneTransaction(_context(tmp_path))
    tx.stage_text("state/current.txt", "after\n")
    observed: list[str] = []

    def validate(future_root: Path) -> list[str]:
        observed.append((future_root / "state/current.txt").read_text(encoding="utf-8"))
        return []

    result = tx.commit(validate=validate)

    assert result.status == "committed"
    assert observed == ["after\n"]
    assert (tmp_path / "state/current.txt").read_text(encoding="utf-8") == "after\n"


def test_staged_deletion_is_visible_to_validation_future(tmp_path: Path) -> None:
    target = tmp_path / "state/current.txt"
    target.parent.mkdir(parents=True)
    target.write_text("before\n", encoding="utf-8")
    tx = ControlPlaneTransaction(_context(tmp_path))
    tx.stage_delete("state/current.txt")
    observed: list[bool] = []

    def validate(future_root: Path) -> list[str]:
        observed.append((future_root / "state/current.txt").exists())
        return []

    result = tx.commit(validate=validate)

    assert result.status == "committed"
    assert observed == [False]
    assert not target.exists()
