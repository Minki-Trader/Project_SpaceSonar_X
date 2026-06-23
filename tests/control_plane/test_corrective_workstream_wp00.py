from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from spacesonar import cli
from spacesonar.control_plane.lifecycle import open_campaign
from spacesonar.control_plane.models import ExecutionContext


REPO_ROOT = Path(__file__).resolve().parents[2]
PROGRESS_REL = Path("docs/migrations/control_plane_corrective_v3_progress.yaml")


def write_in_progress_ledger(repo_root: Path) -> None:
    progress_path = repo_root / PROGRESS_REL
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.write_text(
        yaml.safe_dump(
            {
                "version": "corrective_workflow_progress_v1",
                "work_item_id": "work_codex_control_plane_corrective_v3",
                "work_units": {
                    "WP00": {"status": "completed"},
                    "WP01": {"status": "pending"},
                    "WP02": {"status": "pending"},
                    "WP04": {"status": "pending"},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    "argv",
    [
        ["campaign", "open", "--spec", "spec.yaml"],
        ["campaign", "materialize", "--campaign-id", "campaign_test_v0"],
        ["campaign", "judge", "--campaign-id", "campaign_test_v0"],
        ["campaign", "close", "--campaign-id", "campaign_test_v0"],
        ["wave", "close", "--wave-id", "wave_test_v0"],
    ],
)
def test_corrective_guard_blocks_canonical_lifecycle_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    write_in_progress_ledger(tmp_path)

    result = cli.main(["--repo-root", str(tmp_path), *argv])

    assert result == cli.CORRECTIVE_LIFECYCLE_GUARD_EXIT
    stderr = capsys.readouterr().err
    assert "Work Packets 02 and 04 must complete before activation" in stderr


def test_lifecycle_api_still_operates_in_temporary_fixture_repo(tmp_path: Path) -> None:
    write_in_progress_ledger(tmp_path)
    spec = tmp_path / "campaign_spec.yaml"
    spec.write_text(
        yaml.safe_dump(
            {
                "campaign_id": "campaign_fixture_v0",
                "status": "campaign_opened",
                "created_at_utc": "2026-06-22T00:00:00Z",
                "objective": "fixture lifecycle API remains callable",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    context = ExecutionContext(tmp_path, "work_fixture", "fixture_claim_boundary", ("test",))

    result = open_campaign(spec, context)

    assert result.status == "committed"
    assert (tmp_path / "lab/campaigns/campaign_fixture_v0/campaign_manifest.yaml").exists()


def test_wp00_progress_ledger_parses_and_records_baseline_facts() -> None:
    progress = yaml.safe_load((REPO_ROOT / PROGRESS_REL).read_text(encoding="utf-8-sig"))

    assert progress["version"] == "corrective_workflow_progress_v1"
    assert progress["baseline_commit"] == "fbcde1e67221f0618e17388e6617c8dd3ff4c22d"
    assert progress["branch"] == "codex/control-plane-corrective-v3"
    assert progress["invariants"]["locked_final_oos_b_used"] is False
    assert progress["invariants"]["runtime_authority"] is False
    facts = progress["baseline_facts"]
    assert facts["candidate_count"] == 0
    assert facts["l5_candidate_count"] == 0
    assert facts["current_wave01_runtime_contract_status"] == "passed"
    assert facts["runtime_attempt_manifest_count"] == 88
