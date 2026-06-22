from __future__ import annotations

from pathlib import Path

from foundation.validation.routing_behavior_eval import evaluate
from spacesonar.control_plane.routing import route_work_item


ROOT = Path(__file__).resolve().parents[1]


def test_routing_behavior_cases_pass() -> None:
    errors, metrics = evaluate(ROOT)

    assert not errors
    assert metrics["accuracy"] >= 0.95
    assert metrics["protected_claim_guard_recall"] == 1.0


def test_runtime_token_mutation_changes_route() -> None:
    runtime = route_work_item("Run MT5 tester L4 runtime probe.")
    mutated = route_work_item("Explain the current status.")

    assert runtime.primary_family == "runtime_probe"
    assert mutated.primary_family != "runtime_probe"


def test_policy_path_forces_governance_route() -> None:
    decision = route_work_item("Small wording update", touched_paths=("AGENTS.md",))

    assert decision.primary_family == "policy_skill_governance"


def test_requested_runtime_authority_selects_protected_runtime_guard() -> None:
    decision = route_work_item("Approve this", requested_claims=("runtime_authority",))

    assert decision.primary_family == "runtime_probe"
    assert decision.policy_guard_set == "protected_runtime"
