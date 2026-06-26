from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_PR_CHECKS = [
    "control-plane-fast",
    "unit",
    "evidence-graph-full",
]
SCOPED_UNIT_COMMAND = (
    "uv run pytest tests/test_runtime_completion_contract.py "
    "tests/test_wave01_runtime_truth_migration.py tests/control_plane "
    "tests/test_routing_behavior.py -q"
)


def _load_yaml(rel_path: str) -> dict:
    data = yaml.safe_load((REPO_ROOT / rel_path).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _workflow_triggers(workflow: dict) -> dict:
    triggers = workflow.get("on", workflow.get(True))
    assert isinstance(triggers, dict)
    return triggers


def _job_commands(workflow: dict) -> list[str]:
    commands: list[str] = []
    for job in workflow["jobs"].values():
        steps = job.get("steps", [])
        commands.extend(step.get("run") for step in steps if isinstance(step, dict) and step.get("run"))
    return commands


def test_control_plane_workflow_contains_required_partial_gate_jobs() -> None:
    workflow = _load_yaml(".github/workflows/control-plane.yml")

    jobs = workflow["jobs"]

    assert set(REQUIRED_PR_CHECKS) <= set(jobs)
    assert "full-suite" not in jobs


def test_control_plane_pr_push_path_uses_scoped_pytest_not_full_regression() -> None:
    workflow = _load_yaml(".github/workflows/control-plane.yml")

    commands = _job_commands(workflow)

    assert SCOPED_UNIT_COMMAND in commands
    assert "uv run pytest -q" not in commands


def test_full_regression_workflow_is_manual_and_runs_complete_pytest() -> None:
    workflow = _load_yaml(".github/workflows/full-regression.yml")
    triggers = _workflow_triggers(workflow)
    commands = _job_commands(workflow)

    assert "workflow_dispatch" in triggers
    assert "pull_request" not in triggers
    assert "push" not in triggers
    assert "uv sync --locked --extra dev --extra onnxlab" in commands
    assert "uv run pytest -q" in commands


def test_post_wp08_agent_observation_proof_updates_wave_progression_readiness() -> None:
    ledger = _load_yaml("docs/migrations/control_plane_corrective_v3.yaml")
    progress = _load_yaml("docs/migrations/control_plane_corrective_v3_progress.yaml")

    assert ledger["wp08_final_hygiene"]["status"] == "completed"
    assert progress["wp08_final_hygiene"]["status"] == "completed"
    assert ledger["post_wp08_agent_observation_proof"]["status"] == "completed"
    assert progress["post_wp08_agent_observation_proof"]["status"] == "completed"
    assert ledger["wave_progression_readiness"]["status"] == "ready_for_user_directed_wave02_or_review"
    assert progress["wave_progression_readiness"]["status"] == "ready_for_user_directed_wave02_or_review"
    assert ledger["workflow_status"] == "post_wp08_agent_observation_proof_completed_wave_progression_ready_for_user_direction"
    assert ledger["post_wp08_agent_observation_proof"]["wave02_created"] is False


def test_wave_progression_readiness_ready_after_closeout_evidence_repair() -> None:
    ledger = _load_yaml("docs/migrations/control_plane_corrective_v3.yaml")

    assert ledger["operating_closeout"]["status"] == "wave01_control_plane_proof_closed_runtime_contract_complete"
    assert ledger["operating_closeout"]["agent_value_metrics"] == "passed"
    assert ledger["operating_closeout"]["control_plane_operating_proof"] == "passed"
    assert ledger["wave_progression_readiness"]["blockers"] == []
    assert ledger["wave_progression_readiness"]["active_work_item_id"] == "work_post_wave01_user_directed_wave02_or_review_v0"


def test_main_integration_readiness_records_verified_remote_protection() -> None:
    ledger = _load_yaml("docs/migrations/control_plane_corrective_v3.yaml")
    remote_settings = _load_yaml("docs/policies/remote_repository_settings.yaml")
    branch_protection = _load_yaml("docs/policies/github_branch_protection_required.yaml")

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
    assert branch_protection["required_settings"]["required_checks"] == REQUIRED_PR_CHECKS
    assert branch_protection["required_settings"]["full_regression"] == {
        "workflow": ".github/workflows/full-regression.yml",
        "required_for_campaign_closeout_merge": False,
        "trigger": "workflow_dispatch",
        "claim_effect": "full_regression_verified_only_after_successful_manual_run",
    }
