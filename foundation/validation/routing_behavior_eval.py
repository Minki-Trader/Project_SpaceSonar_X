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


def evaluate(repo_root: Path) -> tuple[list[str], dict[str, float]]:
    cases = load_yaml(repo_root / "docs/agent_control/routing_behavior_cases.yaml").get("cases", [])
    registry = load_yaml(repo_root / "docs/agent_control/work_family_registry.yaml")
    families = registry.get("work_families") or {}
    errors: list[str] = []
    correct = 0
    protected = 0
    protected_correct = 0
    for case in cases:
        decision = route_work_item(
            case["request_text"],
            touched_paths=tuple(case.get("touched_paths") or []),
            execution_layers=tuple(case.get("execution_layers") or []),
            requested_claims=tuple(case.get("requested_claims") or []),
        )
        if decision.primary_family not in families:
            errors.append(f"{case['id']}: router returned unknown family {decision.primary_family}")
        elif decision.primary_skill != (families[decision.primary_family] or {}).get("primary_skill"):
            errors.append(f"{case['id']}: router returned skill absent from active family registry")
        expected = (
            decision.primary_family == case["expected_primary_family"]
            and decision.primary_skill == case["expected_primary_skill"]
            and decision.verification_profile == case["expected_verification_profile"]
            and decision.policy_guard_set == case["expected_guard_set"]
            and decision.confidence >= float(case.get("minimum_confidence", 0))
        )
        correct += int(expected)
        if case.get("requested_claims"):
            protected += 1
            protected_correct += int(decision.policy_guard_set.startswith("protected"))
        if not expected:
            errors.append(f"{case['id']}: expected route mismatch got={decision}")
    accuracy = correct / len(cases) if cases else 0.0
    protected_recall = protected_correct / protected if protected else 1.0
    metrics = {"accuracy": accuracy, "protected_claim_guard_recall": protected_recall}
    if accuracy < 0.95:
        errors.append(f"routing behavior accuracy below 0.95: {accuracy:.3f}")
    if protected_recall < 1.0:
        errors.append(f"protected claim guard recall below 1.0: {protected_recall:.3f}")
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
