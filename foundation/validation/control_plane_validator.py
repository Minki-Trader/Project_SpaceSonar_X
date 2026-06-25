from __future__ import annotations

import argparse
import csv
import importlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
for path in [REPO_ROOT, REPO_ROOT / "src"]:
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

from spacesonar.control_plane.store import filesystem_path


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
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        return handle.read()


def load_yaml(path: Path) -> Any:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle)


def load_json(path: Path) -> Any:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
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
                    with open(filesystem_path(path), "r", newline="", encoding="utf-8-sig") as handle:
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
    failure_disposition = set((fields.get("failure_disposition") or {}).get("required_fields", []))
    add_missing(
        errors,
        label="work_item.schema.yaml fields.failure_disposition",
        observed=failure_disposition,
        required={
            "status",
            "attempt_before_disposition",
            "failure_reproduction",
            "exact_failing_layer",
            "bounded_repair_or_fallback_attempt_or_attempt_blocker",
            "evidence_path",
            "remaining_blocker",
            "reopen_condition",
            "claim_effect",
        },
    )
    role_modes = set(data.get("agent_role_modes_allowed", []))
    add_missing(
        errors,
        label="work_item.schema.yaml agent_role_modes_allowed",
        observed=role_modes,
        required=EXPECTED_AGENT_ROLE_MODES,
    )
    return errors


def validate_policy_contract_and_context_slo(repo_root: Path) -> list[str]:
    errors: list[str] = []
    policy_path = repo_root / "docs" / "agent_control" / "policy_contract.yaml"
    if not policy_path.exists():
        return ["missing required path: docs/agent_control/policy_contract.yaml"]
    policy = load_yaml(policy_path)
    guards = policy.get("guards") or {}
    for guard_id in [
        "GUARD_001_ATTEMPT_BEFORE_DISPOSITION",
        "GUARD_002_RUNTIME_COMPLETION_TRUTH",
        "GUARD_003_CLAIM_BOUNDARY",
        "GUARD_004_ARTIFACT_IDENTITY",
        "GUARD_005_LOCKED_OOS",
        "GUARD_006_BRANCH_WORKTREE",
    ]:
        if guard_id not in guards:
            errors.append(f"policy_contract.yaml missing {guard_id}")

    agents_path = repo_root / "AGENTS.md"
    if agents_path.exists():
        text = read_text(agents_path)
        if len(text.splitlines()) > 140:
            errors.append("AGENTS.md exceeds 140 line boot-kernel limit")
        if len(text.encode("utf-8")) > 18000:
            errors.append("AGENTS.md exceeds 18000 byte boot-kernel limit")

    workspace_path = repo_root / "docs" / "workspace" / "workspace_state.yaml"
    if workspace_path.exists() and len(read_text(workspace_path).splitlines()) > 100:
        errors.append("workspace_state.yaml exceeds 100 line compact projection limit")

    lite_path = repo_root / "docs" / "agent_control" / "work_item_lite.schema.yaml"
    if lite_path.exists():
        lite = load_yaml(lite_path)
        if len(lite.get("required_top_level") or []) > 12:
            errors.append("work_item_lite.schema.yaml has more than 12 required top-level fields")
    else:
        errors.append("missing required path: docs/agent_control/work_item_lite.schema.yaml")
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
    failure_disposition = data.get("conditional_required_fields", {}).get("failure_disposition") or {}
    failure_required_when = set(failure_disposition.get("required_when", []))
    add_missing(
        errors,
        label="skill_receipt_schema.yaml failure_disposition.required_when",
        observed=failure_required_when,
        required={
            "result_judgment_is_blocked",
            "result_judgment_is_deferred",
            "result_judgment_is_invalid",
            "result_judgment_is_discarded",
            "tool_adapter_converter_parser_runtime_or_data_support_gap_blocks_progress",
        },
    )
    failure_fields = set(failure_disposition.get("required_fields", []))
    add_missing(
        errors,
        label="skill_receipt_schema.yaml failure_disposition.required_fields",
        observed=failure_fields,
        required={
            "attempt_before_disposition",
            "failure_reproduction_or_attempt_blocker",
            "exact_failing_layer",
            "bounded_repair_or_fallback_attempt_or_attempt_blocker",
            "evidence_paths",
            "remaining_blocker",
            "reopen_condition",
            "claim_effect",
        },
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
        "campaign_manifest.template.yaml": load_yaml(repo_root / "lab" / "templates" / "campaign_manifest.template.yaml"),
        "ingredient_card.template.yaml": load_yaml(repo_root / "lab" / "templates" / "ingredient_card.template.yaml"),
        "synthesis_mix_queue.template.yaml": load_yaml(repo_root / "lab" / "templates" / "synthesis_mix_queue.template.yaml"),
    }

    for name, data in templates.items():
        if name in {"campaign_manifest.template.yaml", "ingredient_card.template.yaml", "synthesis_mix_queue.template.yaml"}:
            continue
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
    campaign_template = templates["campaign_manifest.template.yaml"]
    add_missing(
        errors,
        label="campaign_manifest.template.yaml top-level",
        observed=set(campaign_template),
        required={
            "campaign_type",
            "exploration_coverage",
            "bounded_synthesis",
            "candidate_repair_policy",
            "proxy_runtime_parity",
        },
    )
    coverage = campaign_template.get("exploration_coverage", {})
    add_missing(
        errors,
        label="campaign_manifest.template.yaml exploration_coverage",
        observed=set(coverage),
        required={
            "mode",
            "primary_unknown_axis",
            "required_research_axes",
            "companion_axes",
            "forbidden_research_shapes",
            "single_axis_exception_policy",
            "novelty_claim",
        },
    )
    synthesis = campaign_template.get("bounded_synthesis", {})
    add_missing(
        errors,
        label="campaign_manifest.template.yaml bounded_synthesis",
        observed=set(synthesis),
        required={
            "source_scope",
            "source_campaign_ids",
            "ingredient_registry",
            "synthesis_registry",
            "mix_depth_policy",
            "next_wave_influence",
            "runtime_follow_through",
            "claim_boundary",
        },
    )
    ingredient_template = templates["ingredient_card.template.yaml"]
    add_missing(
        errors,
        label="ingredient_card.template.yaml top-level",
        observed=set(ingredient_template),
        required={
            "version",
            "ingredient_card_id",
            "source_campaign_ids",
            "evidence_paths",
            "forbidden_uses",
            "storage_contract",
            "claim_boundary",
        },
    )
    mix_template = templates["synthesis_mix_queue.template.yaml"]
    add_missing(
        errors,
        label="synthesis_mix_queue.template.yaml top-level",
        observed=set(mix_template),
        required={
            "version",
            "campaign_id",
            "queue_id",
            "source_scope",
            "mix_depth_policy",
            "selection_policy",
            "next_wave_influence",
            "storage_contract",
            "claim_boundary",
        },
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
    profiles = review_policy.get("allocation_profiles") or {}
    for profile in ["solo", "micro_specialist", "micro_adversarial", "formal_protected_review", "full_roster"]:
        if profile not in profiles:
            errors.append(f"codex_task_force_registry.yaml: missing allocation profile {profile}")
    if review_policy.get("max_depth") != 1:
        errors.append("codex_task_force_registry.yaml: max_depth must be 1")
    receipt_fields = set((data.get("micro_consult_receipt_schema") or {}).get("required_fields", []))
    add_missing(
        errors,
        label="codex_task_force_registry.yaml micro_consult_receipt_schema",
        observed=receipt_fields,
        required=REQUIRED_TASK_FORCE_RECEIPT_FIELDS,
    )
    v2_fields = set((data.get("consult_receipt_v2_schema") or {}).get("required_fields", []))
    add_missing(
        errors,
        label="codex_task_force_registry.yaml consult_receipt_v2_schema",
        observed=v2_fields,
        required={
            "consult_id",
            "profile",
            "question_digest",
            "selected_agent_ids",
            "source_refs",
            "opinions",
            "owner_decision",
            "verification_refs",
            "claim_effect",
            "metrics",
        },
    )
    return errors


def validate_agent_consult_receipts(repo_root: Path) -> list[str]:
    src_path = str(repo_root / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    from spacesonar.control_plane.agent_metrics import consult_metric_errors

    registry = load_yaml(repo_root / "docs" / "agent_control" / "codex_task_force_registry.yaml")
    agents = {item.get("id") for item in registry.get("roster", [])}
    review_policy = registry.get("review_policy") or {}
    profiles = review_policy.get("allocation_profiles") or {}
    role_modes_allowed = set(review_policy.get("role_modes") or {})
    classifications_allowed = set((registry.get("consult_receipt_v2_schema") or {}).get("allowed_opinion_classifications") or [])
    errors: list[str] = []
    for path in sorted(repo_root.glob("lab/**/*consult*.yaml")):
        data = load_yaml(path)
        if data.get("version") != "agent_consult_receipt_v2":
            continue
        label = rel(path, repo_root)
        selected = data.get("selected_agent_ids") or []
        profile = data.get("profile")
        if profile not in profiles:
            errors.append(f"{label}: unknown consult profile {profile}")
            continue
        if len(selected) < int(profiles[profile].get("min_agents", 0)) or len(selected) > int(profiles[profile].get("max_agents", 0)):
            errors.append(f"{label}: selected_agent_ids count does not fit profile {profile}")
        unknown = sorted(set(selected) - agents)
        if unknown:
            errors.append(f"{label}: unknown registry agent ids {unknown}")
        role_modes = data.get("role_modes") or {}
        if isinstance(role_modes, dict):
            role_values = set(role_modes.values())
            role_agent_ids = set(role_modes)
            unknown_role_agents = sorted(role_agent_ids - set(selected))
            if unknown_role_agents:
                errors.append(f"{label}: role_modes include agents not selected {unknown_role_agents}")
        else:
            role_values = set(role_modes)
        unknown_modes = sorted(role_values - role_modes_allowed)
        if unknown_modes:
            errors.append(f"{label}: unknown role modes {unknown_modes}")
        if len(selected) >= 3 and not data.get("escalation_reason"):
            errors.append(f"{label}: 3 or more agents require escalation_reason")
        if len(selected) >= 5:
            if not data.get("why_not_smaller"):
                errors.append(f"{label}: 5 or more agents require why_not_smaller")
            trigger = data.get("full_roster_trigger")
            allowed = set(profiles["full_roster"].get("allowed_only_when") or [])
            if trigger not in allowed:
                errors.append(f"{label}: full roster trigger is not allowed")
        for opinion in data.get("opinions") or []:
            classification = opinion.get("classification")
            refs = opinion.get("evidence_refs") or []
            if classification not in classifications_allowed:
                errors.append(f"{label}: unknown opinion classification {classification}")
            if classification in {"accepted", "rewritten"} and not refs:
                errors.append(f"{label}: accepted/rewritten advice requires evidence_refs")
        errors.extend(consult_metric_errors(data, label=label))
        if data.get("claim_effect") != "advisory_only_no_reviewed_pass":
            errors.append(f"{label}: consult claim_effect cannot satisfy reviewed/pass gates")
    return errors


def validate_agent_operating_metrics_projection(repo_root: Path) -> list[str]:
    src_path = str(repo_root / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    from spacesonar.control_plane.agent_metrics import agent_operating_events_diff, agent_operating_metrics_diff

    return [*agent_operating_events_diff(repo_root), *agent_operating_metrics_diff(repo_root)]


def validate_execution_provenance(repo_root: Path) -> list[str]:
    for path in [repo_root, repo_root / "src"]:
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)
    from foundation.validation.execution_provenance_validator import validate as validate_execution_provenance_records

    return validate_execution_provenance_records(repo_root)


def validate_fresh_evaluators(repo_root: Path) -> list[str]:
    for path in [repo_root, repo_root / "src"]:
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)
    from foundation.evaluation.fresh_evaluator_validator import validate_committed_evaluators

    return validate_committed_evaluators(repo_root)


def validate_remote_repository_settings(repo_root: Path) -> list[str]:
    for path in [repo_root, repo_root / "src"]:
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)
    from foundation.validation.remote_repository_settings_verifier import validate_record

    return validate_record(repo_root)


def validate_operating_closeout(repo_root: Path) -> list[str]:
    for path in [repo_root, repo_root / "src"]:
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)
    from foundation.evaluation.build_operating_closeout import validate_committed_closeout

    return validate_committed_closeout(repo_root)


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
        "foundation.validation.active_record_validator",
        "foundation.validation.control_plane_validator",
        "foundation.validation.refresh_artifact_registry_hashes",
        "foundation.validation.remote_repository_settings_verifier",
    ]:
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001 - validator reports import failures.
            errors.append(f"import smoke failed for {module_name}: {exc}")
    return errors


def validate(repo_root: Path, *, include_active_records: bool = False) -> list[str]:
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
                "lab/templates/ingredient_card.template.yaml",
                "lab/templates/synthesis_mix_queue.template.yaml",
                "docs/registers/ingredient_card_registry.csv",
                "docs/registers/synthesis_campaign_registry.csv",
            ],
        )
    )
    errors.extend(validate_yaml_json_csv_parse(repo_root))
    errors.extend(validate_work_item_schema(repo_root))
    errors.extend(validate_policy_contract_and_context_slo(repo_root))
    errors.extend(validate_skill_receipt_schema(repo_root))
    errors.extend(validate_templates(repo_root))
    errors.extend(validate_task_force_registry(repo_root))
    errors.extend(validate_agent_consult_receipts(repo_root))
    errors.extend(validate_agent_operating_metrics_projection(repo_root))
    errors.extend(validate_execution_provenance(repo_root))
    errors.extend(validate_fresh_evaluators(repo_root))
    errors.extend(validate_remote_repository_settings(repo_root))
    errors.extend(validate_operating_closeout(repo_root))
    errors.extend(validate_routing_smoke_prompts(repo_root))
    errors.extend(validate_import_smoke(repo_root))

    if include_active_records:
        from foundation.validation.active_record_validator import validate as validate_active_records

        errors.extend(validate_active_records(repo_root))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--include-active-records", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    errors = validate(repo_root, include_active_records=args.include_active_records)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("control-plane validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
