from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
for item in (REPO_ROOT, SRC_ROOT):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from spacesonar.control_plane.routing import route_work_item


def load_yaml(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle)


def _skill_frontmatter(text: str) -> dict[str, object]:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    return yaml.safe_load(parts[1]) or {}


def _skill_exists_or_stub(repo_root: Path, skill_name: str) -> bool:
    skill_path = repo_root / ".agents" / "skills" / skill_name / "SKILL.md"
    if not skill_path.exists():
        return False
    metadata = _skill_frontmatter(skill_path.read_text(encoding="utf-8-sig"))
    return metadata.get("name") == skill_name and (
        "replaced_by" not in metadata or bool(metadata.get("compatibility_until"))
    )


def evaluate(repo_root: Path) -> tuple[list[str], dict[str, float]]:
    cases = load_yaml(repo_root / "docs/agent_control/routing_behavior_cases.yaml").get("cases", [])
    registry = load_yaml(repo_root / "docs/agent_control/work_family_registry.yaml")
    families = registry.get("work_families") or {}
    profiles = registry.get("verification_profiles") or {}
    guard_sets = registry.get("route_guard_sets") or {}
    errors: list[str] = []
    correct = 0
    protected_assertion = 0
    protected_assertion_correct = 0
    protected_read_only = 0
    protected_read_only_correct = 0
    unknown_profile_count = 0
    unknown_guard_set_count = 0
    observed_families: set[str] = set()
    for case in cases:
        expected_profile = case["expected_verification_profile"]
        expected_guard_set = case["expected_guard_set"]
        if expected_profile not in profiles:
            errors.append(f"{case['id']}: fixture expects unknown verification profile {expected_profile}")
            unknown_profile_count += 1
        if expected_guard_set not in guard_sets:
            errors.append(f"{case['id']}: fixture expects unknown guard set {expected_guard_set}")
            unknown_guard_set_count += 1
        decision = route_work_item(
            case["request_text"],
            repo_root=repo_root,
            registry=registry,
            touched_paths=tuple(case.get("touched_paths") or []),
            execution_layers=tuple(case.get("execution_layers") or []),
            requested_claims=tuple(case.get("requested_claims") or []),
        )
        observed_families.add(decision.primary_family)
        if decision.primary_family not in families:
            errors.append(f"{case['id']}: router returned unknown family {decision.primary_family}")
        elif decision.primary_skill != (families[decision.primary_family] or {}).get("primary_skill"):
            errors.append(f"{case['id']}: router returned skill absent from active family registry")
        if decision.verification_profile not in profiles:
            unknown_profile_count += 1
            errors.append(f"{case['id']}: router returned unknown verification profile {decision.verification_profile}")
        if decision.policy_guard_set not in guard_sets:
            unknown_guard_set_count += 1
            errors.append(f"{case['id']}: router returned unknown guard set {decision.policy_guard_set}")
        if not _skill_exists_or_stub(repo_root, decision.primary_skill):
            errors.append(f"{case['id']}: router returned missing skill or invalid stub {decision.primary_skill}")
        expected = (
            decision.primary_family == case["expected_primary_family"]
            and decision.primary_skill == case["expected_primary_skill"]
            and decision.verification_profile == expected_profile
            and decision.policy_guard_set == expected_guard_set
            and decision.confidence >= float(case.get("minimum_confidence", 0))
        )
        if "maximum_confidence" in case:
            expected = expected and decision.confidence <= float(case["maximum_confidence"])
        if case.get("expected_ambiguous"):
            expected = expected and bool(decision.ambiguous_reasons)
        correct += int(expected)
        if case.get("protected_claim_assertion"):
            protected_assertion += 1
            protected_assertion_correct += int(decision.policy_guard_set in {"protected_runtime", "protected_candidate_model"})
        if case.get("protected_claim_read_only"):
            protected_read_only += 1
            protected_read_only_correct += int(decision.policy_guard_set == "protected_claim_read_only")
        if not expected:
            errors.append(f"{case['id']}: expected route mismatch got={decision}")
    accuracy = correct / len(cases) if cases else 0.0
    protected_assertion_recall = protected_assertion_correct / protected_assertion if protected_assertion else 1.0
    protected_read_only_recall = protected_read_only_correct / protected_read_only if protected_read_only else 1.0
    automatic_families = {
        family
        for family, payload in families.items()
        if (payload or {}).get("routing_mode") == "automatic"
    }
    missing_automatic_families = sorted(automatic_families - observed_families)
    automatic_coverage = (len(automatic_families) - len(missing_automatic_families)) / len(automatic_families) if automatic_families else 1.0
    metrics = {
        "accuracy": accuracy,
        "protected_claim_guard_recall": protected_assertion_recall,
        "protected_claim_assertion_recall": protected_assertion_recall,
        "protected_claim_read_only_recall": protected_read_only_recall,
        "automatic_family_coverage": automatic_coverage,
        "unknown_verification_profile_count": float(unknown_profile_count),
        "unknown_guard_set_count": float(unknown_guard_set_count),
        "unreachable_automatic_family_count": float(len(missing_automatic_families)),
    }
    if accuracy < 0.95:
        errors.append(f"routing behavior accuracy below 0.95: {accuracy:.3f}")
    if protected_assertion_recall < 1.0:
        errors.append(f"protected claim assertion recall below 1.0: {protected_assertion_recall:.3f}")
    if protected_read_only_recall < 1.0:
        errors.append(f"protected claim read-only recall below 1.0: {protected_read_only_recall:.3f}")
    if automatic_coverage < 1.0:
        errors.append(f"automatic family coverage below 1.0; missing {missing_automatic_families}")
    if unknown_profile_count:
        errors.append(f"unknown verification profile count nonzero: {unknown_profile_count}")
    if unknown_guard_set_count:
        errors.append(f"unknown guard set count nonzero: {unknown_guard_set_count}")
    return errors, metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    errors, metrics = evaluate(Path(args.repo_root).resolve())
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        print(yaml.dump(metrics, sort_keys=False))
        return 1
    print("routing behavior eval passed")
    print(yaml.dump(metrics, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
