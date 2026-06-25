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


def test_wp08_hygiene_completed_does_not_imply_main_readiness() -> None:
    ledger = _load_yaml("docs/migrations/control_plane_corrective_v3.yaml")
    progress = _load_yaml("docs/migrations/control_plane_corrective_v3_progress.yaml")

    assert ledger["wp08_final_hygiene"]["status"] == "completed"
    assert ledger["main_integration_readiness"]["status"] == "blocked"
    assert progress["wp08_final_hygiene"]["status"] == "completed"
    assert progress["main_integration_readiness"]["status"] == "blocked"
    assert ledger["workflow_status"] == "wp08_hygiene_completed_main_integration_blocked"


def test_main_readiness_blocked_when_closeout_requires_repair() -> None:
    ledger = _load_yaml("docs/migrations/control_plane_corrective_v3.yaml")

    assert ledger["operating_closeout"]["status"] == "wave01_evaluator_backed_closeout_requires_evidence_repair"
    assert "operating_closeout_evidence_repair_required" in ledger["main_integration_readiness"]["blockers"]
    assert "agent_observation_coverage_below_slo" in ledger["main_integration_readiness"]["blockers"]


def test_main_readiness_blocked_when_remote_protection_is_not_verified() -> None:
    ledger = _load_yaml("docs/migrations/control_plane_corrective_v3.yaml")

    assert ledger["remote_branch_protection"] == "not_enabled_or_not_visible"
    assert "main_branch_protection_missing_or_not_visible" in ledger["main_integration_readiness"]["blockers"]

