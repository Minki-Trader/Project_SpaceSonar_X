from __future__ import annotations

import argparse
import csv
import importlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml


REQUIRED_WORK_ITEM_TOP_LEVEL = {
    "branch_worktree",
    "agent_allocation",
    "execution_provenance",
}
REQUIRED_SKILL_ROUTING_FIELDS = {
    "skills_selected",
    "skills_not_used",
    "critical_skills_not_selected",
    "not_selected_claim_effect",
}
REQUIRED_BRANCH_FIELDS = {
    "current_branch",
    "requested_branch",
    "branch_worktree_fit",
    "branch_action",
    "policy_reference",
    "mismatch_claim_effect",
}
REQUIRED_AGENT_ALLOCATION_FIELDS = {
    "phase",
    "selected_agents",
    "role_modes",
    "selection_reason",
    "why_not_smaller",
    "why_not_larger",
    "max_threads_is_capacity_only",
    "claim_effect",
}
REQUIRED_PROVENANCE_FIELDS = {
    "git_sha",
    "branch",
    "dirty_flag",
    "changed_files",
    "command_argv",
    "python_executable",
    "python_version",
    "key_package_versions",
    "started_at_utc",
    "ended_at_utc",
    "input_hashes",
    "output_hashes",
    "unknown_git_claim_effect",
}
REQUIRED_TASK_FORCE_RECEIPT_FIELDS = {
    "role_modes",
    "why_not_smaller",
    "why_not_larger",
    "critical_agents_not_selected",
    "not_selected_claim_effect",
}
EXPECTED_AGENT_ROLE_MODES = {
    "scout",
    "design",
    "preflight",
    "adversarial_check",
    "evidence_check",
    "runtime_check",
    "closeout_check",
}
ROUTING_CASE_REQUIRED_KEYS = {
    "id",
    "prompt",
    "expected_primary_family",
    "expected_primary_skill",
    "expected_support_skills",
    "expected_required_gates",
    "expected_claim_boundary",
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def rel(path: Path, repo_root: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def add_missing(
    errors: list[str],
    *,
    label: str,
    observed: set[str],
    required: set[str],
) -> None:
    missing = sorted(required - observed)
    if missing:
        errors.append(f"{label}: missing {missing}")


def ensure_paths(repo_root: Path, rel_paths: list[str]) -> list[str]:
    errors: list[str] = []
    for rel_path in rel_paths:
        if not (repo_root / rel_path).exists():
            errors.append(f"missing required path: {rel_path}")
    return errors


def validate_yaml_json_csv_parse(repo_root: Path) -> list[str]:
    errors: list[str] = []
    parse_roots = [
        repo_root / "docs",
        repo_root / "configs",
        repo_root / "lab" / "templates",
        repo_root / ".agents" / "skills",
    ]
    for root in parse_roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            try:
                if suffix in {".yaml", ".yml"}:
                    load_yaml(path)
                elif suffix == ".json":
                    load_json(path)
                elif suffix == ".csv":
                    with path.open("r", newline="", encoding="utf-8-sig") as handle:
                        reader = csv.reader(handle)
                        next(reader, None)
            except Exception as exc:  # noqa: BLE001 - validator reports all parse failures.
                errors.append(f"{rel(path, repo_root)}: parse failed: {exc}")
    return errors


def validate_work_item_schema(repo_root: Path) -> list[str]:
    path = repo_root / "docs" / "agent_control" / "work_item.schema.yaml"
    data = load_yaml(path)
    errors: list[str] = []
    required_top_level = set(data.get("required_top_level", []))
    add_missing(
        errors,
        label="work_item.schema.yaml required_top_level",
        observed=required_top_level,
        required=REQUIRED_WORK_ITEM_TOP_LEVEL,
    )
    fields = data.get("fields", {})
    for field_name, required in {
        "branch_worktree": REQUIRED_BRANCH_FIELDS,
        "agent_allocation": REQUIRED_AGENT_ALLOCATION_FIELDS,
        "execution_provenance": REQUIRED_PROVENANCE_FIELDS,
    }.items():
        observed = set((fields.get(field_name) or {}).get("required_fields", []))
        add_missing(errors, label=f"work_item.schema.yaml fields.{field_name}", observed=observed, required=required)
    skill_routing = set((fields.get("skill_routing") or {}).get("required_fields", []))
    add_missing(
        errors,
        label="work_item.schema.yaml fields.skill_routing",
        observed=skill_routing,
        required=REQUIRED_SKILL_ROUTING_FIELDS,
    )
    role_modes = set(data.get("agent_role_modes_allowed", []))
    add_missing(
        errors,
        label="work_item.schema.yaml agent_role_modes_allowed",
        observed=role_modes,
        required=EXPECTED_AGENT_ROLE_MODES,
    )
    return errors


def validate_skill_receipt_schema(repo_root: Path) -> list[str]:
    path = repo_root / "docs" / "agent_control" / "skill_receipt_schema.yaml"
    data = load_yaml(path)
    errors: list[str] = []
    common = set(data.get("required_common_fields", []))
    add_missing(
        errors,
        label="skill_receipt_schema.yaml required_common_fields",
        observed=common,
        required={
            "branch_worktree_fit",
            "branch_action",
            "provenance",
            "critical_skills_not_selected",
            "not_selected_claim_effect",
        },
    )
    task_force = set((data.get("skill_specific", {}).get("spacesonar-task-force-review") or {}).get("required_fields", []))
    add_missing(
        errors,
        label="skill_receipt_schema.yaml spacesonar-task-force-review",
        observed=task_force,
        required={"role_modes"},
    )
    return errors


def validate_templates(repo_root: Path) -> list[str]:
    errors: list[str] = []
    templates = {
        "experiment_receipt.template.yaml": load_yaml(repo_root / "lab" / "templates" / "experiment_receipt.template.yaml"),
        "run_manifest.template.json": load_json(repo_root / "lab" / "templates" / "run_manifest.template.json"),
        "experiment_bundle.template.json": load_json(repo_root / "lab" / "templates" / "experiment_bundle.template.json"),
        "attempt_manifest.template.yaml": load_yaml(repo_root / "lab" / "templates" / "attempt_manifest.template.yaml"),
        "runtime_evidence.template.yaml": load_yaml(repo_root / "lab" / "templates" / "runtime_evidence.template.yaml"),
    }

    for name, data in templates.items():
        if name in {"experiment_bundle.template.json", "attempt_manifest.template.yaml", "runtime_evidence.template.yaml"}:
            required_top = {"branch_worktree", "provenance"}
        else:
            required_top = {"branch_worktree", "agent_allocation", "provenance"}
        add_missing(errors, label=f"{name} top-level", observed=set(data), required=required_top)
        add_missing(
            errors,
            label=f"{name} branch_worktree",
            observed=set(data.get("branch_worktree", {})),
            required=REQUIRED_BRANCH_FIELDS,
        )
        if "agent_allocation" in required_top:
            add_missing(
                errors,
                label=f"{name} agent_allocation",
                observed=set(data.get("agent_allocation", {})),
                required=REQUIRED_AGENT_ALLOCATION_FIELDS,
            )
        add_missing(
            errors,
            label=f"{name} provenance",
            observed=set(data.get("provenance", {})),
            required=REQUIRED_PROVENANCE_FIELDS,
        )
        if "skill_routing" in data:
            add_missing(
                errors,
                label=f"{name} skill_routing",
                observed=set(data.get("skill_routing", {})),
                required=REQUIRED_SKILL_ROUTING_FIELDS,
            )
    return errors


def validate_task_force_registry(repo_root: Path) -> list[str]:
    path = repo_root / "docs" / "agent_control" / "codex_task_force_registry.yaml"
    data = load_yaml(path)
    errors: list[str] = []
    review_policy = data.get("review_policy", {})
    if review_policy.get("max_threads_capacity_rule") is None:
        errors.append("codex_task_force_registry.yaml: missing max_threads_capacity_rule")
    add_missing(
        errors,
        label="codex_task_force_registry.yaml role_modes",
        observed=set(review_policy.get("role_modes", {})),
        required=EXPECTED_AGENT_ROLE_MODES,
    )
    if not review_policy.get("allocation_shapes"):
        errors.append("codex_task_force_registry.yaml: missing allocation_shapes")
    receipt_fields = set((data.get("micro_consult_receipt_schema") or {}).get("required_fields", []))
    add_missing(
        errors,
        label="codex_task_force_registry.yaml micro_consult_receipt_schema",
        observed=receipt_fields,
        required=REQUIRED_TASK_FORCE_RECEIPT_FIELDS,
    )
    return errors


def validate_routing_smoke_prompts(repo_root: Path) -> list[str]:
    path = repo_root / "docs" / "agent_control" / "routing_smoke_prompts.yaml"
    data = load_yaml(path)
    work_families = load_yaml(repo_root / "docs" / "agent_control" / "work_family_registry.yaml").get(
        "work_families", {}
    )
    errors: list[str] = []
    cases = data.get("cases", [])
    if not 12 <= len(cases) <= 20:
        errors.append(f"routing_smoke_prompts.yaml: expected 12-20 cases, found {len(cases)}")
    if data.get("prompt_count_policy", {}).get("current") != len(cases):
        errors.append("routing_smoke_prompts.yaml: prompt_count_policy.current does not match cases length")
    seen: set[str] = set()
    for idx, case in enumerate(cases, start=1):
        label = f"routing_smoke_prompts.yaml case {idx}"
        add_missing(errors, label=label, observed=set(case), required=ROUTING_CASE_REQUIRED_KEYS)
        case_id = case.get("id")
        if case_id in seen:
            errors.append(f"routing_smoke_prompts.yaml: duplicate case id {case_id}")
        seen.add(case_id)
        family = case.get("expected_primary_family")
        if family not in work_families:
            errors.append(f"{label}: unknown expected_primary_family {family!r}")
            continue
        expected_skill = work_families[family].get("primary_skill")
        if case.get("expected_primary_skill") != expected_skill:
            errors.append(
                f"{label}: expected_primary_skill {case.get('expected_primary_skill')!r} "
                f"does not match registry primary_skill {expected_skill!r}"
            )
    return errors


def validate_import_smoke(repo_root: Path) -> list[str]:
    errors: list[str] = []
    sys.path.insert(0, str(repo_root / "src"))
    sys.path.insert(0, str(repo_root))
    for module_name in [
        "spacesonar",
        "foundation.collectors.raw_m5_inventory",
        "foundation.validation.control_plane_validator",
    ]:
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001 - validator reports import failures.
            errors.append(f"import smoke failed for {module_name}: {exc}")
    return errors


def validate(repo_root: Path) -> list[str]:
    errors: list[str] = []
    errors.extend(
        ensure_paths(
            repo_root,
            [
                "docs/policies/branch_policy.md",
                "docs/policies/agent_allocation_policy.md",
                "docs/agent_control/routing_smoke_prompts.yaml",
                "lab/templates/experiment_receipt.template.yaml",
                "lab/templates/run_manifest.template.json",
            ],
        )
    )
    errors.extend(validate_yaml_json_csv_parse(repo_root))
    errors.extend(validate_work_item_schema(repo_root))
    errors.extend(validate_skill_receipt_schema(repo_root))
    errors.extend(validate_templates(repo_root))
    errors.extend(validate_task_force_registry(repo_root))
    errors.extend(validate_routing_smoke_prompts(repo_root))
    errors.extend(validate_import_smoke(repo_root))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    errors = validate(repo_root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("control-plane validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
