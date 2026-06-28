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
        for command_id in [
            "pytest",
            "full_regression_workflow",
            "evidence_graph_full_workflow",
            "active_record_validator_full_graph",
            "spacesonar_project_validate_full",
            "spacesonar_cli_project_validate_as_progress_default",
            "broad_hash_resync",
            "global_registry_regeneration",
            "whole_tree_scan_as_proof",
            "volatile_local_tree_scan_as_proof",
        ]:
            if command_id not in forbidden:
                errors.append(f"operational_stability_kernel forbidden_default_commands missing {command_id}")
        hash_policy = kernel.get("hash_and_line_ending_policy") or {}
        if hash_policy.get("yaml_identity_mode") != "no_aliases_no_anchors_utf8_lf":
            errors.append("operational_stability_kernel hash_and_line_ending_policy.yaml_identity_mode mismatch")
        allowed_smokes = set(kernel.get("allowed_non_pytest_smokes") or [])
        if "scan_touched_yaml_for_alias_tokens" not in allowed_smokes:
            errors.append("operational_stability_kernel allowed_non_pytest_smokes missing scan_touched_yaml_for_alias_tokens")
        writer_commands = kernel.get("writer_scope_commands") or {}
        if "machine_yaml_identity_lint" not in writer_commands:
            errors.append("operational_stability_kernel writer_scope_commands missing machine_yaml_identity_lint")
        if "targeted_artifact_hash_refresh" not in writer_commands:
            errors.append("operational_stability_kernel writer_scope_commands missing targeted_artifact_hash_refresh")
        command_selection = kernel.get("default_command_selection") or {}
        if command_selection.get("project_validate_default") is not False:
            errors.append("operational_stability_kernel default_command_selection.project_validate_default must be false")
        if "identify_current_work_item_next_executable_writer_or_probe" not in set(
            command_selection.get("preferred_before_project_validate") or []
        ):
            errors.append("operational_stability_kernel must prefer next executable work before project validate")
        enforcement = kernel.get("hard_enforcement_points") or {}
        for enforcement_id in ["writer_before_write", "writer_after_write", "boundary_before_main_push"]:
            if not enforcement.get(enforcement_id):
                errors.append(f"operational_stability_kernel hard_enforcement_points missing {enforcement_id}")
        if "machine_yaml_has_no_aliases_or_anchors" not in set(enforcement.get("writer_after_write") or []):
            errors.append("operational_stability_kernel writer_after_write missing machine_yaml_has_no_aliases_or_anchors")
        ci_policy = kernel.get("ci_scope_gate_policy") or {}
        if ci_policy.get("default_behavior") != "non_blocking_boundary_classifier":
            errors.append("operational_stability_kernel ci_scope_gate_policy.default_behavior mismatch")
        repair_matrix = kernel.get("direct_inspection_repair_matrix") or []
        if not isinstance(repair_matrix, list) or len(repair_matrix) < 15:
            errors.append("operational_stability_kernel direct_inspection_repair_matrix must name at least 15 surfaces")
        contract_enforcement = kernel.get("writer_contract_enforcement") or {}
        for field in [
            "new_or_changed_writer_without_contract",
            "legacy_writer_reuse_without_contract",
            "broad_validation_finds_writer_gap",
        ]:
            if field not in contract_enforcement:
                errors.append(f"operational_stability_kernel writer_contract_enforcement missing {field}")

    contract_rel = "docs/agent_control/writer_scope_operating_contract.yaml"
    contract_path = repo_root / contract_rel
    if not contract_path.exists():
        errors.append(f"missing writer scope operating contract: {contract_rel}")
    elif (registry.get("global_rules") or {}).get("writer_scope_operating_contract") != contract_rel:
        errors.append("work_family_registry.yaml global_rules.writer_scope_operating_contract mismatch")
    else:
        contract = load_yaml(contract_path)
        if contract.get("default_validation_depth") != "writer_scope_smoke":
            errors.append("writer_scope_operating_contract default_validation_depth must be writer_scope_smoke")
        required_writer_fields = set(contract.get("required_writer_record_fields") or [])
        for field in [
            "writer_contract_version",
            "source_of_truth_paths",
            "writer_owned_outputs",
            "validation_depth",
            "non_pytest_smokes",
            "skipped_broad_validations",
            "broad_validation_escalation_reason",
            "writer_scope_self_check",
            "claim_boundary",
            "next_action_or_reopen_condition",
        ]:
            if field not in required_writer_fields:
                errors.append(f"writer_scope_operating_contract required_writer_record_fields missing {field}")
        machine_enforcement = contract.get("machine_enforcement") or {}
        for field in ["new_writer_records", "legacy_writer_reuse", "summary_or_closeout_records", "failure_policy"]:
            if field not in machine_enforcement:
                errors.append(f"writer_scope_operating_contract machine_enforcement missing {field}")

    if (registry.get("global_rules") or {}).get("operational_stability_lint") != (
        "foundation/validation/operational_stability_lint.py"
    ):
        errors.append("work_family_registry.yaml global_rules.operational_stability_lint mismatch")

    cases = prompts.get("cases", [])
    declared_count = (prompts.get("prompt_count_policy") or {}).get("current")
    if declared_count != len(cases):
        errors.append(f"prompt_count_policy.current {declared_count!r} does not match actual cases {len(cases)}")
    if not 12 <= len(cases) <= 20:
        errors.append(f"expected 12-20 smoke cases, found {len(cases)}")
    seen_case_ids: set[str] = set()

    for case in cases:
        case_id = case.get("id", "<missing-id>")
        if case_id in seen_case_ids:
            errors.append(f"duplicate smoke case id {case_id!r}")
        seen_case_ids.add(case_id)
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
        expected_depth = case.get("expected_validation_depth")
        if expected_depth and expected_depth != registry.get("global_rules", {}).get(
            "default_validation_depth", "writer_scope_smoke"
        ):
            errors.append(f"{case_id}: expected_validation_depth {expected_depth!r} is not writer_scope_smoke")
        skipped = as_set(case.get("expected_skipped_broad_validations"))
        unknown_skipped = sorted(skipped - forbidden) if "forbidden" in locals() else sorted(skipped)
        if unknown_skipped:
            errors.append(f"{case_id}: expected_skipped_broad_validations outside kernel forbidden defaults {unknown_skipped}")

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
