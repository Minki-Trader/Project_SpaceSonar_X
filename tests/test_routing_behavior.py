from __future__ import annotations

from pathlib import Path

import yaml

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


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle) or {}


def skill_frontmatter(skill_name: str) -> dict:
    text = (ROOT / ".agents" / "skills" / skill_name / "SKILL.md").read_text(encoding="utf-8-sig")
    assert text.startswith("---")
    return yaml.safe_load(text.split("---", 2)[1]) or {}


def test_canonical_skill_directories_exist() -> None:
    for skill_name in (
        "spacesonar-session-bootstrap",
        "spacesonar-evidence-provenance",
        "spacesonar-runtime-evidence",
        "spacesonar-code-change-quality",
        "spacesonar-experiment-design",
    ):
        metadata = skill_frontmatter(skill_name)
        assert metadata["name"] == skill_name
        assert "replaced_by" not in metadata


def test_compatibility_stubs_are_small_and_policy_free() -> None:
    consolidation = load_yaml(ROOT / "docs/agent_control/skill_consolidation_map.yaml")
    old_to_new = {
        old_skill: new_skill
        for new_skill, payload in consolidation["canonical_skills"].items()
        for old_skill in payload.get("replaces", [])
        if old_skill != new_skill
    }
    for old_skill, new_skill in old_to_new.items():
        skill_path = ROOT / ".agents" / "skills" / old_skill / "SKILL.md"
        metadata = skill_frontmatter(old_skill)
        text = skill_path.read_text(encoding="utf-8-sig")
        assert metadata["replaced_by"] == new_skill
        assert metadata["compatibility_until"]
        assert len([line for line in text.splitlines() if line.strip()]) <= 10
        assert "Do not claim" not in text
        assert "Guardrails" not in text
        assert not (skill_path.parent / "agents" / "openai.yaml").exists()


def test_every_family_resolves_to_valid_canonical_skills_and_limits() -> None:
    registry = load_yaml(ROOT / "docs/agent_control/work_family_registry.yaml")
    global_guards = set(registry["global_guards"])
    canonical = set(load_yaml(ROOT / "docs/agent_control/skill_consolidation_map.yaml")["canonical_skills"])
    available = {path.parent.name for path in (ROOT / ".agents" / "skills").glob("*/SKILL.md")}
    for family, payload in registry["work_families"].items():
        explicit = [payload["primary_skill"], *payload.get("support_skills", [])]
        assert not (set(explicit) & global_guards), family
        assert len(explicit) <= 3, family
        for skill_name in explicit:
            metadata = skill_frontmatter(skill_name)
            assert skill_name in available
            assert skill_name in canonical or "replaced_by" not in metadata


def test_data_feature_route_is_not_code_edit() -> None:
    decision = route_work_item(
        "Create a US100 M5 feature recipe and check label boundary.",
        touched_paths=("foundation/features/new_recipe.py",),
    )

    assert decision.primary_family == "data_feature_build"
    assert decision.primary_skill == "spacesonar-data-integrity"


def test_workspace_projection_route_is_workspace_sync() -> None:
    decision = route_work_item(
        "Sync workspace_state.yaml projection.",
        touched_paths=("docs/workspace/workspace_state.yaml",),
    )

    assert decision.primary_family == "workspace_state_sync"
    assert decision.primary_skill == "spacesonar-workspace-state-sync"


def test_selected_baseline_uses_protected_candidate_model_route() -> None:
    decision = route_work_item("Mark the model as selected_baseline.", requested_claims=("selected_baseline",))

    assert decision.primary_family == "candidate_evaluation"
    assert decision.policy_guard_set == "protected_candidate_model"


def test_explanation_only_runtime_path_does_not_trigger_execution() -> None:
    decision = route_work_item(
        "Just explain this file.",
        touched_paths=("foundation/config/mt5_runtime_probe_contract.yaml",),
    )

    assert decision.primary_family == "information_only"
    assert decision.policy_guard_set == "runtime_read_only"


def test_ambiguity_lowers_confidence_and_records_reasons() -> None:
    decision = route_work_item("Maybe update docs and train something later, not sure.")

    assert decision.primary_family == "policy_skill_governance"
    assert decision.confidence < 0.70
    assert decision.ambiguous_reasons
