from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_yaml(rel_path: str) -> dict:
    data = yaml.safe_load((REPO_ROOT / rel_path).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_control_plane_workflow_contains_full_suite_job() -> None:
    workflow = _load_yaml(".github/workflows/control-plane.yml")

    jobs = workflow["jobs"]

    assert {"control-plane-fast", "unit", "evidence-graph-full", "full-suite"} <= set(jobs)


def test_full_suite_runs_complete_pytest() -> None:
    workflow = _load_yaml(".github/workflows/control-plane.yml")

    steps = workflow["jobs"]["full-suite"]["steps"]
    commands = [step.get("run") for step in steps if isinstance(step, dict)]

    assert "uv sync --locked --extra dev --extra onnxlab" in commands
    assert "uv run pytest -q" in commands


def test_wp08_hygiene_completed_does_not_imply_wave_progression_readiness() -> None:
    ledger = _load_yaml("docs/migrations/control_plane_corrective_v3.yaml")
    progress = _load_yaml("docs/migrations/control_plane_corrective_v3_progress.yaml")

    assert ledger["wp08_final_hygiene"]["status"] == "completed"
    assert ledger["wave_progression_readiness"]["status"] == "blocked"
    assert progress["wp08_final_hygiene"]["status"] == "completed"
    assert progress["wave_progression_readiness"]["status"] == "blocked"
    assert ledger["workflow_status"] == "wp08_hygiene_completed_wave_progression_blocked"


def test_wave_progression_readiness_blocked_when_closeout_requires_repair() -> None:
    ledger = _load_yaml("docs/migrations/control_plane_corrective_v3.yaml")

    assert ledger["operating_closeout"]["status"] == "wave01_evaluator_backed_closeout_requires_evidence_repair"
    assert "operating_closeout_evidence_repair_required" in ledger["wave_progression_readiness"]["blockers"]
    assert "agent_observation_coverage_below_slo" in ledger["wave_progression_readiness"]["blockers"]
    assert ledger["wave_progression_readiness"]["active_work_item_id"] == "work_wp07_closeout_evidence_repair_v0"


def test_main_integration_readiness_records_verified_remote_protection() -> None:
    ledger = _load_yaml("docs/migrations/control_plane_corrective_v3.yaml")
    remote_settings = _load_yaml("docs/policies/remote_repository_settings.yaml")

    assert ledger["remote_branch_protection"] == "verified"
    assert remote_settings["remote_branch_protection"] == "verified"
    assert remote_settings["checks"] == {
        "pull_request_required_on_main": True,
        "required_status_checks": True,
        "squash_merge_enabled": True,
        "merge_commit_disabled": True,
        "rebase_merge_disabled": True,
        "force_push_disabled": True,
        "direct_push_restricted": True,
    }
    assert ledger["main_integration_readiness"]["required_checks"] == [
        "control-plane-fast",
        "unit",
        "evidence-graph-full",
        "full-suite",
    ]
