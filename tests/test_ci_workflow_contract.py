from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_yaml(rel_path: str) -> dict:
    data = yaml.safe_load((REPO_ROOT / rel_path).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _workflow_on(workflow: dict) -> dict:
    return workflow.get("on", workflow.get(True))


def test_control_plane_workflow_keeps_full_graph_manual() -> None:
    workflow = _load_yaml(".github/workflows/control-plane.yml")

    jobs = workflow["jobs"]

    assert {"ci-scope-gate", "control-plane-fast", "unit", "evidence-graph-full"} <= set(jobs)
    assert "full-suite" not in jobs
    assert "workflow_dispatch" in _workflow_on(workflow)
    assert jobs["evidence-graph-full"]["if"] == "github.event_name == 'workflow_dispatch'"


def test_ci_scope_gate_is_active_after_bootstrap() -> None:
    workflow = _load_yaml(".github/workflows/control-plane.yml")

    assert workflow["jobs"]["ci-scope-gate"]["if"] == "github.event_name == 'pull_request' || github.event_name == 'push'"
    steps = workflow["jobs"]["ci-scope-gate"]["steps"]
    commands = [step.get("run") for step in steps if isinstance(step, dict)]

    assert any(
        command
        and "foundation/validation/ci_scope_gate.py" in command
        for command in commands
    )
    assert any(command and 'ADVISORY="--advisory"' in command for command in commands)


def test_branch_protection_required_checks_use_ci_scope_gate() -> None:
    policy = _load_yaml("docs/policies/github_branch_protection_required.yaml")

    assert policy["required_settings"]["pull_request_required"] is False
    assert policy["required_settings"]["direct_push"] == "allowed_at_boundary"
    assert policy["required_settings"]["required_checks"] == []


def test_full_regression_workflow_is_manual_and_runs_complete_pytest() -> None:
    workflow = _load_yaml(".github/workflows/full-regression.yml")

    assert workflow.get("on", workflow.get(True)) == {"workflow_dispatch": None}

    steps = workflow["jobs"]["full-regression"]["steps"]
    commands = [step.get("run") for step in steps if isinstance(step, dict)]

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


def test_main_integration_readiness_records_direct_push_remote_settings() -> None:
    ledger = _load_yaml("docs/migrations/control_plane_corrective_v3.yaml")
    remote_settings = _load_yaml("docs/policies/remote_repository_settings.yaml")

    assert ledger["remote_branch_protection"] == "not_enabled_or_not_visible"
    assert remote_settings["remote_branch_protection"] == "not_enabled_or_not_visible"
    assert remote_settings["checks"] == {
        "pull_request_required_on_main": False,
        "required_status_checks": False,
        "squash_merge_enabled": True,
        "merge_commit_disabled": True,
        "rebase_merge_disabled": True,
        "force_push_disabled": "unverified_external_state",
        "direct_push_restricted": False,
    }
    assert ledger["main_integration_readiness"]["required_checks"] == [
        "control-plane-fast",
        "unit",
    ]
    assert ledger["main_integration_readiness"]["manual_boundary_checks"] == [
        "evidence-graph-full",
        "full-regression",
    ]
