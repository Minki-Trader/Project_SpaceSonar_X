from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from spacesonar import cli
from spacesonar.control_plane.lifecycle import open_campaign
from spacesonar.control_plane.models import ExecutionContext


REPO_ROOT = Path(__file__).resolve().parents[2]
PROGRESS_REL = Path("docs/migrations/control_plane_corrective_v3_progress.yaml")


def write_progress_ledger(
    repo_root: Path,
    *,
    version: str = cli.CORRECTIVE_LEDGER_VERSION,
    work_item_id: str = cli.CORRECTIVE_WORK_ITEM_ID,
    branch: str = cli.CORRECTIVE_BRANCH,
    wp02_status: str = "pending",
    wp04_status: str = "pending",
) -> None:
    progress_path = repo_root / PROGRESS_REL
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.write_text(
        yaml.safe_dump(
            {
                "version": version,
                "work_item_id": work_item_id,
                "branch": branch,
                "work_units": {
                    "WP00": {"status": "completed"},
                    "WP01": {"status": "pending"},
                    "WP02": {"status": wp02_status},
                    "WP04": {"status": wp04_status},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def force_corrective_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "current_git_branch", lambda _repo_root: cli.CORRECTIVE_BRANCH)


def assert_no_lifecycle_artifacts(repo_root: Path) -> None:
    assert not (repo_root / "lab" / "campaigns").exists()
    assert not (repo_root / "lab" / "waves").exists()
    assert not (repo_root / ".spacesonar").exists()


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
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
) -> None:
    force_corrective_branch(monkeypatch)
    write_progress_ledger(tmp_path)

    result = cli.main(["--repo-root", str(tmp_path), *argv])

    assert result == cli.CORRECTIVE_LIFECYCLE_GUARD_EXIT
    stderr = capsys.readouterr().err
    assert "Work Packets 02 and 04 must complete before activation" in stderr
    assert_no_lifecycle_artifacts(tmp_path)


def test_missing_ledger_fails_closed_on_corrective_branch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    force_corrective_branch(monkeypatch)

    result = cli.main(["--repo-root", str(tmp_path), "campaign", "materialize", "--campaign-id", "campaign_test_v0"])

    assert result == cli.CORRECTIVE_LIFECYCLE_GUARD_EXIT
    assert "progress ledger is missing" in capsys.readouterr().err
    assert_no_lifecycle_artifacts(tmp_path)


def test_malformed_yaml_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    force_corrective_branch(monkeypatch)
    progress_path = tmp_path / PROGRESS_REL
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.write_text("version: [\n", encoding="utf-8")

    result = cli.main(["--repo-root", str(tmp_path), "campaign", "materialize", "--campaign-id", "campaign_test_v0"])

    assert result == cli.CORRECTIVE_LIFECYCLE_GUARD_EXIT
    assert "progress ledger is unreadable" in capsys.readouterr().err
    assert_no_lifecycle_artifacts(tmp_path)


def test_non_mapping_yaml_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    force_corrective_branch(monkeypatch)
    progress_path = tmp_path / PROGRESS_REL
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.write_text("- not-a-mapping\n", encoding="utf-8")

    result = cli.main(["--repo-root", str(tmp_path), "campaign", "materialize", "--campaign-id", "campaign_test_v0"])

    assert result == cli.CORRECTIVE_LIFECYCLE_GUARD_EXIT
    assert "progress ledger root is not a mapping" in capsys.readouterr().err
    assert_no_lifecycle_artifacts(tmp_path)


def test_wrong_version_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    force_corrective_branch(monkeypatch)
    write_progress_ledger(tmp_path, version="wrong_version")

    result = cli.main(["--repo-root", str(tmp_path), "campaign", "materialize", "--campaign-id", "campaign_test_v0"])

    assert result == cli.CORRECTIVE_LIFECYCLE_GUARD_EXIT
    assert "progress ledger version mismatch" in capsys.readouterr().err
    assert_no_lifecycle_artifacts(tmp_path)


def test_wrong_work_item_id_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    force_corrective_branch(monkeypatch)
    write_progress_ledger(tmp_path, work_item_id="wrong_work_item")

    result = cli.main(["--repo-root", str(tmp_path), "campaign", "materialize", "--campaign-id", "campaign_test_v0"])

    assert result == cli.CORRECTIVE_LIFECYCLE_GUARD_EXIT
    assert "progress ledger work_item_id mismatch" in capsys.readouterr().err
    assert_no_lifecycle_artifacts(tmp_path)


def test_wrong_ledger_branch_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    force_corrective_branch(monkeypatch)
    write_progress_ledger(tmp_path, branch="main")

    result = cli.main(["--repo-root", str(tmp_path), "campaign", "materialize", "--campaign-id", "campaign_test_v0"])

    assert result == cli.CORRECTIVE_LIFECYCLE_GUARD_EXIT
    assert "progress ledger branch mismatch" in capsys.readouterr().err
    assert_no_lifecycle_artifacts(tmp_path)


def test_wp02_and_wp04_completed_release_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    force_corrective_branch(monkeypatch)
    write_progress_ledger(tmp_path, wp02_status="completed", wp04_status="completed")
    spec = tmp_path / "spec.yaml"
    spec.write_text(
        yaml.safe_dump(
            {
                "campaign_id": "campaign_released_v0",
                "status": "campaign_opened",
                "created_at_utc": "2026-06-22T00:00:00Z",
                "objective": "guard release dispatches lifecycle command",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = cli.main(["--repo-root", str(tmp_path), "campaign", "open", "--spec", str(spec)])

    assert result == 0
    assert (tmp_path / "lab/campaigns/campaign_released_v0/campaign_manifest.yaml").exists()


def test_lifecycle_api_still_operates_in_temporary_fixture_repo(tmp_path: Path) -> None:
    write_progress_ledger(tmp_path)
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
    assert facts["runtime_attempt_manifest_count_total"] == 88
    assert facts["runtime_target_attempt_manifest_count"] == 86
    assert facts["runtime_target_definition"]["wave0_or_wave01_l4_attempt_with_execution_state"] is True
