from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from foundation.validation.routing_behavior_eval import evaluate
from spacesonar.control_plane.routing import _claim_alias_hits, load_claim_vocabulary, route_work_item


ROOT = Path(__file__).resolve().parents[1]


def test_routing_behavior_cases_pass() -> None:
    errors, metrics = evaluate(ROOT)

    assert not errors
    assert metrics["accuracy"] >= 0.95
    assert metrics["protected_claim_assertion_recall"] == 1.0
    assert metrics["protected_claim_read_only_recall"] == 1.0
    assert metrics["automatic_family_coverage"] == 1.0
    assert metrics["expected_automatic_family_coverage"] == 1.0
    assert metrics["correctly_matched_automatic_family_coverage"] == 1.0
    assert metrics["missing_golden_family_count"] == 0
    assert metrics["unknown_verification_profile_count"] == 0
    assert metrics["unknown_guard_set_count"] == 0
    assert metrics["unreachable_automatic_family_count"] == 0
    assert metrics["invalid_routing_mode_count"] == 0


def test_runtime_token_mutation_changes_route() -> None:
    runtime = route_work_item("Run MT5 tester L4 runtime probe.")
    mutated = route_work_item("Explain the current status.")

    assert runtime.primary_family == "runtime_probe"
    assert mutated.primary_family != "runtime_probe"


def test_policy_path_forces_governance_route() -> None:
    decision = route_work_item("Small wording update", touched_paths=("AGENTS.md",))

    assert decision.primary_family == "policy_skill_governance"


def test_policy_owned_paths_precede_generic_fix_terms() -> None:
    decision = route_work_item("Fix typo in AGENTS.md", touched_paths=("AGENTS.md",))

    assert decision.primary_family == "policy_skill_governance"


def test_requested_runtime_authority_selects_protected_runtime_guard() -> None:
    decision = route_work_item("Approve this", requested_claims=("runtime_authority",))

    assert decision.primary_family == "runtime_probe"
    assert decision.policy_guard_set == "protected_runtime"


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle) or {}


def test_routing_sources_keep_readable_utf8_korean_and_no_mojibake_alias_layer() -> None:
    routing_text = (ROOT / "src/spacesonar/control_plane/routing.py").read_text(encoding="utf-8-sig")
    test_text = Path(__file__).read_text(encoding="utf-8-sig")
    vocabulary = load_yaml(ROOT / "docs/agent_control/claim_vocabulary.yaml")

    assert "COMPAT_PROTECTED_CLAIM_ALIASES" not in routing_text
    assert "COMPAT_PROTECTED_CLAIM_ASSERTION_ALIASES" not in routing_text
    assert "BROKEN_INPUT_QUESTION" not in routing_text
    assert "_with_compat_claim_vocabulary" not in routing_text
    assert "\ufffd" not in routing_text
    assert "\ufffd" not in test_text
    for phrase in (
        "경제성 통과 여부?",
        "운영 배포로 설정해줘.",
        "라이브 준비 완료를 승인해줘.",
        "선택 기준선 상태는?",
    ):
        assert phrase in test_text
    aliases = vocabulary["protected_claim_aliases"]
    assert "경제성 통과" in aliases["economics_pass"]
    assert "운영 배포" in aliases["production_deployment"]
    assert "라이브 준비 완료" in aliases["live_readiness"]
    assert "선택 기준선" in aliases["selected_baseline"]


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


def test_every_routing_case_returns_registry_valid_profile_and_guard() -> None:
    registry = load_yaml(ROOT / "docs/agent_control/work_family_registry.yaml")
    cases = load_yaml(ROOT / "docs/agent_control/routing_behavior_cases.yaml")["cases"]
    profiles = set(registry["verification_profiles"])
    guard_sets = set(registry["route_guard_sets"])
    for case in cases:
        decision = route_work_item(
            case["request_text"],
            repo_root=ROOT,
            touched_paths=tuple(case.get("touched_paths") or []),
            execution_layers=tuple(case.get("execution_layers") or []),
            requested_claims=tuple(case.get("requested_claims") or []),
        )
        assert decision.primary_family in registry["work_families"], case["id"]
        assert decision.primary_skill == registry["work_families"][decision.primary_family]["primary_skill"]
        assert decision.verification_profile in profiles, case["id"]
        assert decision.policy_guard_set in guard_sets, case["id"]


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


def test_runtime_route_uses_runtime_verification_profile() -> None:
    decision = route_work_item("Run MT5 tester L4 runtime probe.")

    assert decision.primary_family == "runtime_probe"
    assert decision.verification_profile == "runtime"


def test_selected_baseline_uses_protected_candidate_model_route() -> None:
    decision = route_work_item("Mark the model as selected_baseline.", requested_claims=("selected_baseline",))

    assert decision.primary_family == "candidate_evaluation"
    assert decision.policy_guard_set == "protected_candidate_model"


def test_requested_family_cannot_override_protected_claim_assertions() -> None:
    live = route_work_item("Set live readiness.", requested_family="information_only")
    economics = route_work_item("Declare economics pass.", requested_family="candidate_evaluation")
    baseline = route_work_item("Mark this as selected baseline.", requested_family="information_only")

    assert live.primary_family == "runtime_probe"
    assert live.policy_guard_set == "protected_runtime"
    assert "requested_family_overridden_by_protected_claim" in live.matched_rules
    assert economics.primary_family == "runtime_probe"
    assert economics.policy_guard_set == "protected_runtime"
    assert "requested_family_overridden_by_protected_claim" in economics.matched_rules
    assert baseline.primary_family == "candidate_evaluation"
    assert baseline.policy_guard_set == "protected_candidate_model"
    assert "requested_family_overridden_by_protected_claim" in baseline.matched_rules


def test_requested_claim_matching_is_exact_and_fail_closed() -> None:
    vocabulary = load_claim_vocabulary(ROOT)

    assert _claim_alias_hits("", ("runtime_authority",), vocabulary) == {"runtime_authority"}
    assert _claim_alias_hits("", ("runtime authority",), vocabulary) == {"runtime_authority"}
    assert _claim_alias_hits("", ("runtime",), vocabulary) == {"generic_requested_claim"}
    assert _claim_alias_hits("", ("pass",), vocabulary) == {"generic_requested_claim"}
    assert _claim_alias_hits("", ("selected",), vocabulary) == {"generic_requested_claim"}
    assert _claim_alias_hits("", ("unknown_review_claim",), vocabulary) == {"generic_requested_claim"}


def test_partial_or_unknown_requested_claims_are_protected() -> None:
    for requested_claim in ("runtime", "pass", "selected", "unknown_review_claim"):
        decision = route_work_item("Approve this.", requested_claims=(requested_claim,))
        assert decision.primary_family == "runtime_probe"
        assert decision.policy_guard_set == "protected_runtime"


def test_invalid_requested_family_cannot_preempt_protected_claims() -> None:
    assertion = route_work_item("Approve live readiness.", requested_family="invalid_family")
    read_only = route_work_item("선택 기준선 상태는?", requested_family="invalid_family")

    assert assertion.primary_family == "runtime_probe"
    assert assertion.policy_guard_set == "protected_runtime"
    assert "requested_family_invalid_but_overridden_by_protected_claim" in assertion.matched_rules
    assert read_only.primary_family == "information_only"
    assert read_only.policy_guard_set == "protected_claim_read_only"
    assert "requested_family_invalid_but_overridden_by_protected_claim" in read_only.matched_rules


def test_invalid_requested_family_without_protected_claim_fails() -> None:
    with pytest.raises(KeyError):
        route_work_item("Explain current status.", requested_family="invalid_family")


def test_protected_runtime_assertion_aliases() -> None:
    for prompt in (
        "Approve live readiness.",
        "Declare economics pass.",
        "Grant runtime authority.",
        "라이브 준비 완료를 승인해줘.",
        "운영 배포로 설정해줘.",
    ):
        decision = route_work_item(prompt)
        assert decision.primary_family == "runtime_probe"
        assert decision.policy_guard_set == "protected_runtime"


def test_terse_protected_claim_mentions_are_read_only() -> None:
    for prompt in (
        "Live readiness?",
        "Selected baseline?",
        "경제성 통과 여부?",
        "선택 기준선 상태는?",
        "What is production deployment status?",
    ):
        decision = route_work_item(prompt)
        assert decision.primary_family == "information_only"
        assert decision.policy_guard_set == "protected_claim_read_only"


def test_assertion_intent_is_token_aware() -> None:
    read_only = route_work_item("What is live readiness in this dataset?")
    assertion = route_work_item("Set live readiness.")
    korean_assertion = route_work_item("운영 배포로 설정해줘.")

    assert read_only.primary_family == "information_only"
    assert read_only.policy_guard_set == "protected_claim_read_only"
    assert assertion.primary_family == "runtime_probe"
    assert assertion.policy_guard_set == "protected_runtime"
    assert korean_assertion.primary_family == "runtime_probe"
    assert korean_assertion.policy_guard_set == "protected_runtime"


def test_explanation_only_runtime_path_does_not_trigger_execution() -> None:
    decision = route_work_item(
        "Just explain this file.",
        touched_paths=("foundation/config/mt5_runtime_probe_contract.yaml",),
    )

    assert decision.primary_family == "information_only"
    assert decision.policy_guard_set == "runtime_read_only"


def test_read_only_protected_claim_uses_protected_read_only_guard() -> None:
    decision = route_work_item("What is the current live-readiness status?")

    assert decision.primary_family == "information_only"
    assert decision.policy_guard_set == "protected_claim_read_only"


def test_required_automatic_routes() -> None:
    cases = {
        "Design an experiment hypothesis with broad sweep axes.": "experiment_design",
        "Open bounded synthesis using ingredient cards and mix-2.": "synthesis_campaign",
        "Materialize experiment bundle and package model/schema/EA inputs.": "bundle_materialization",
        "Evaluate candidate metrics before promotion decision.": "candidate_evaluation",
        "Refactor and extract module for ownership-preserving restructuring.": "code_refactor",
    }
    for prompt, family in cases.items():
        assert route_work_item(prompt).primary_family == family


def test_policy_semantic_and_implementation_validator_changes_split() -> None:
    implementation = route_work_item(
        "Fix a Python parsing exception in control_plane_validator.py.",
        touched_paths=("foundation/validation/control_plane_validator.py",),
    )
    semantic = route_work_item(
        "Change protected-claim validation policy and guard semantics.",
        touched_paths=("foundation/validation/control_plane_validator.py", "docs/agent_control/policy_contract.yaml"),
    )

    assert implementation.primary_family == "code_edit"
    assert implementation.primary_skill == "spacesonar-code-change-quality"
    assert semantic.primary_family == "policy_skill_governance"
    assert semantic.primary_skill == "spacesonar-work-item-router"


def test_ambiguity_lowers_confidence_and_records_reasons() -> None:
    decision = route_work_item("Maybe update docs and train something later, not sure.")

    assert decision.primary_family == "policy_skill_governance"
    assert decision.confidence < 0.70
    assert decision.ambiguous_reasons


def minimal_registry(primary_skill: str = "spacesonar-session-bootstrap") -> dict:
    return {
        "version": "test_registry_v1",
        "verification_profiles": {"information_only": {}, "policy_skill_governance": {}},
        "route_guard_sets": {"answer_only": {}, "safe_default": {}},
        "work_families": {
            "information_only": {
                "routing_mode": "automatic",
                "primary_skill": primary_skill,
                "support_skills": [],
                "required_gates": [],
            },
            "policy_skill_governance": {
                "routing_mode": "explicit_only",
                "primary_skill": "spacesonar-work-item-router",
                "support_skills": [],
                "required_gates": [],
            },
        },
    }


def write_tmp_repo(root: Path, primary_skill: str = "spacesonar-session-bootstrap") -> None:
    (root / "docs/agent_control").mkdir(parents=True)
    (root / ".agents/skills" / primary_skill).mkdir(parents=True)
    (root / ".agents/skills/spacesonar-work-item-router").mkdir(parents=True, exist_ok=True)
    (root / "docs/agent_control/work_family_registry.yaml").write_text(
        yaml.safe_dump(minimal_registry(primary_skill), sort_keys=False),
        encoding="utf-8",
    )
    (root / "docs/agent_control/claim_vocabulary.yaml").write_text(
        yaml.safe_dump({"version": "claim_vocabulary_v1", "protected_claim_aliases": {}, "protected_claim_assertion_intent_aliases": []}, sort_keys=False),
        encoding="utf-8",
    )
    (root / "docs/agent_control/routing_behavior_cases.yaml").write_text(
        yaml.safe_dump(
            {
                "version": "routing_behavior_cases_test_v1",
                "cases": [
                    {
                        "id": "info",
                        "request_text": "Explain status.",
                        "touched_paths": [],
                        "execution_layers": [],
                        "requested_claims": [],
                        "expected_primary_family": "information_only",
                        "expected_primary_skill": primary_skill,
                        "expected_verification_profile": "information_only",
                        "expected_guard_set": "answer_only",
                        "minimum_confidence": 0.8,
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    for skill_name in (primary_skill, "spacesonar-work-item-router"):
        (root / ".agents/skills" / skill_name / "SKILL.md").write_text(
            f"---\nname: {skill_name}\ndescription: test\n---\n\n# Test\n",
            encoding="utf-8",
        )


def test_registry_edit_same_process_changes_next_route(tmp_path: Path) -> None:
    write_tmp_repo(tmp_path, "spacesonar-session-bootstrap")
    first = route_work_item("Explain status.", repo_root=tmp_path)
    (tmp_path / ".agents/skills/spacesonar-alt-bootstrap").mkdir(parents=True)
    (tmp_path / ".agents/skills/spacesonar-alt-bootstrap/SKILL.md").write_text(
        "---\nname: spacesonar-alt-bootstrap\ndescription: test\n---\n\n# Test\n",
        encoding="utf-8",
    )
    (tmp_path / "docs/agent_control/work_family_registry.yaml").write_text(
        yaml.safe_dump(minimal_registry("spacesonar-alt-bootstrap"), sort_keys=False),
        encoding="utf-8",
    )
    second = route_work_item("Explain status.", repo_root=tmp_path)

    assert first.primary_skill == "spacesonar-session-bootstrap"
    assert second.primary_skill == "spacesonar-alt-bootstrap"


def test_evaluator_uses_requested_repo_root_registry(tmp_path: Path) -> None:
    write_tmp_repo(tmp_path, "spacesonar-alt-bootstrap")
    errors, metrics = evaluate(tmp_path)

    assert not errors
    assert metrics["accuracy"] == 1.0


def test_each_automatic_family_has_expected_golden_case() -> None:
    registry = load_yaml(ROOT / "docs/agent_control/work_family_registry.yaml")
    cases = load_yaml(ROOT / "docs/agent_control/routing_behavior_cases.yaml")["cases"]
    automatic = {family for family, payload in registry["work_families"].items() if payload["routing_mode"] == "automatic"}
    expected = {case["expected_primary_family"] for case in cases}

    assert automatic <= expected


def test_incorrect_route_cannot_satisfy_automatic_family_coverage(tmp_path: Path) -> None:
    write_tmp_repo(tmp_path, "spacesonar-session-bootstrap")
    cases_path = tmp_path / "docs/agent_control/routing_behavior_cases.yaml"
    payload = yaml.safe_load(cases_path.read_text(encoding="utf-8"))
    payload["cases"][0]["expected_guard_set"] = "safe_default"
    cases_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    errors, metrics = evaluate(tmp_path)

    assert errors
    assert metrics["expected_automatic_family_coverage"] == 1.0
    assert metrics["correctly_matched_automatic_family_coverage"] == 0.0
    assert metrics["unreachable_automatic_family_count"] == 1


def test_invalid_routing_mode_fails_evaluation(tmp_path: Path) -> None:
    write_tmp_repo(tmp_path, "spacesonar-session-bootstrap")
    registry_path = tmp_path / "docs/agent_control/work_family_registry.yaml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    registry["work_families"]["information_only"]["routing_mode"] = "sometimes"
    registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")
    errors, metrics = evaluate(tmp_path)

    assert errors
    assert metrics["invalid_routing_mode_count"] == 1
