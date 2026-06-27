from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle)


def as_set(value: object) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, list):
        return {str(item) for item in value}
    return {str(value)}


def evaluate(repo_root: Path) -> list[str]:
    prompts = load_yaml(repo_root / "docs" / "agent_control" / "routing_smoke_prompts.yaml")
    registry = load_yaml(repo_root / "docs" / "agent_control" / "work_family_registry.yaml")
    work_families = registry.get("work_families", {})
    errors: list[str] = []

    kernel_rel = "docs/agent_control/operational_stability_kernel.yaml"
    kernel_path = repo_root / kernel_rel
    if not kernel_path.exists():
        errors.append(f"missing operational stability kernel: {kernel_rel}")
    elif (registry.get("global_rules") or {}).get("operational_stability_kernel") != kernel_rel:
        errors.append("work_family_registry.yaml global_rules.operational_stability_kernel mismatch")
    else:
        kernel = load_yaml(kernel_path)
        if kernel.get("default_validation_depth") != "writer_scope_smoke":
            errors.append("operational_stability_kernel default_validation_depth must be writer_scope_smoke")
        forbidden = set(kernel.get("forbidden_default_commands") or [])
        for command_id in ["pytest", "active_record_validator_full_graph", "spacesonar_project_validate_full"]:
            if command_id not in forbidden:
                errors.append(f"operational_stability_kernel forbidden_default_commands missing {command_id}")

    cases = prompts.get("cases", [])
    if not 12 <= len(cases) <= 20:
        errors.append(f"expected 12-20 smoke cases, found {len(cases)}")

    for case in cases:
        case_id = case.get("id", "<missing-id>")
        family_id = case.get("expected_primary_family")
        family = work_families.get(family_id)
        if family is None:
            errors.append(f"{case_id}: unknown family {family_id!r}")
            continue

        expected_skill = case.get("expected_primary_skill")
        if expected_skill != family.get("primary_skill"):
            errors.append(
                f"{case_id}: primary skill {expected_skill!r} does not match "
                f"registry {family.get('primary_skill')!r}"
            )

        case_support = as_set(case.get("expected_support_skills"))
        registry_support = as_set(family.get("support_skills"))
        extra_support = sorted(case_support - registry_support)
        if extra_support:
            errors.append(f"{case_id}: support skills outside registry defaults {extra_support}")

        case_gates = as_set(case.get("expected_required_gates"))
        registry_gates = as_set(family.get("required_gates"))
        missing_registry_gates = sorted(registry_gates - case_gates)
        if missing_registry_gates:
            errors.append(f"{case_id}: missing registry gates {missing_registry_gates}")

        if not case.get("expected_claim_boundary"):
            errors.append(f"{case_id}: missing expected_claim_boundary")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()

    errors = evaluate(repo_root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    cases = load_yaml(repo_root / "docs" / "agent_control" / "routing_smoke_prompts.yaml").get("cases", [])
    print(f"routing smoke eval passed: {len(cases)} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
