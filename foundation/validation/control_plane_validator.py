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
    role_modes = list(data.get("agent_role_modes_allowed", []))
    if role_modes:
        errors.append("work_item.schema.yaml agent_role_modes_allowed must be empty because Task Force/sub-agents are disabled")
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
    if "spacesonar-task-force-review" in (data.get("skill_specific") or {}):
        errors.append("skill_receipt_schema.yaml must not define spacesonar-task-force-review because Task Force/sub-agents are disabled")
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
        "wave_allocation.template.yaml": load_yaml(repo_root / "lab" / "templates" / "wave_allocation.template.yaml"),
        "kpi_ledger_manifest.template.yaml": load_yaml(repo_root / "lab" / "templates" / "kpi_ledger_manifest.template.yaml"),
        "campaign_manifest.template.yaml": load_yaml(repo_root / "lab" / "templates" / "campaign_manifest.template.yaml"),
        "ingredient_card.template.yaml": load_yaml(repo_root / "lab" / "templates" / "ingredient_card.template.yaml"),
        "synthesis_mix_queue.template.yaml": load_yaml(repo_root / "lab" / "templates" / "synthesis_mix_queue.template.yaml"),
    }

    for name, data in templates.items():
        if name in {
            "wave_allocation.template.yaml",
            "kpi_ledger_manifest.template.yaml",
            "campaign_manifest.template.yaml",
            "ingredient_card.template.yaml",
            "synthesis_mix_queue.template.yaml",
        }:
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
            "cadence",
            "source_campaign_ids",
            "ingredient_registry",
            "synthesis_registry",
            "mix_depth_policy",
            "ingredient_lifecycle_policy",
            "kpi_policy",
            "next_wave_influence",
            "runtime_follow_through",
            "closeout_artifacts",
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
            "ingredient_lifecycle",
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
            "cadence",
            "mix_depth_policy",
            "ingredient_lifecycle_policy",
            "selection_policy",
            "kpi_policy",
            "next_wave_influence",
            "storage_contract",
            "claim_boundary",
        },
    )
    kpi_template = templates["kpi_ledger_manifest.template.yaml"]
    add_missing(
        errors,
        label="kpi_ledger_manifest.template.yaml top-level",
        observed=set(kpi_template),
        required={
            "summary",
            "kpi_policy",
            "record_files",
            "schema_ref",
            "claim_boundary",
            "forbidden_claims",
        },
    )
    kpi_policy = kpi_template.get("kpi_policy", {})
    add_missing(
        errors,
        label="kpi_ledger_manifest.template.yaml kpi_policy",
        observed=set(kpi_policy),
        required={
            "fixed_schema",
            "mt5_missing_is_repair_trigger_before_na",
            "proxy_only_runs_excluded_from_comparison_ledger",
            "non_trading_score_probe_excluded_from_kpi_ledger",
            "score_probe_retained_only_in_runtime_evidence_not_kpi",
            "overall_and_segment_breakdowns_required",
            "fake_segment_placeholder_forbidden",
            "observed_segment_requires_metric_or_count_basis",
            "missing_segment_requires_next_materialization_step",
            "required_segment_axes",
            "optional_segment_axes",
            "segment_claim_policy",
        },
    )
    wave_template = templates["wave_allocation.template.yaml"]
    add_missing(
        errors,
        label="wave_allocation.template.yaml top-level",
        observed=set(wave_template),
        required={
            "budget",
            "campaign_allocations",
            "storage_contract",
            "git_integration",
            "fixed_controls",
            "sampling_plan",
        },
    )
    wave_budget = wave_template.get("budget", {})
    add_missing(
        errors,
        label="wave_allocation.template.yaml budget",
        observed=set(wave_budget),
        required={
            "budget_profile",
            "allocation_mode",
            "wave_budget_fixed_before_open",
            "max_runs",
            "standard_total_run_budget",
            "standard_campaign_slots",
            "reserve_fraction",
            "campaign_run_budget_bounds",
            "per_campaign_allocation_reason_required",
            "hypothesis_allocation_reason_required",
            "allocation_reason_must_name",
            "mid_wave_budget_increase_policy",
            "budget_exception",
            "l4_pair_budget",
            "l4_budget_unit",
            "l4_required_period_roles",
            "decision_replay_pair_budget",
        },
    )
    profile_policy = load_yaml(repo_root / "docs" / "workspace" / "lab_profile.yaml").get("wave_budget_policy", {})
    bounds = wave_budget.get("campaign_run_budget_bounds") or {}
    profile_bounds = profile_policy.get("campaign_run_budget_bounds") or {}
    if wave_budget.get("budget_profile") != profile_policy.get("default_profile"):
        errors.append("wave_allocation.template.yaml budget_profile does not match lab_profile wave_budget_policy.default_profile")
    if wave_budget.get("allocation_mode") != profile_policy.get("allocation_mode"):
        errors.append("wave_allocation.template.yaml allocation_mode does not match lab_profile wave_budget_policy")
    if wave_budget.get("max_runs") != wave_budget.get("standard_total_run_budget"):
        errors.append("wave_allocation.template.yaml max_runs must equal standard_total_run_budget")
    if wave_budget.get("standard_total_run_budget") != profile_policy.get("standard_total_run_budget"):
        errors.append("wave_allocation.template.yaml standard_total_run_budget does not match lab_profile")
    if wave_budget.get("standard_campaign_slots") != profile_policy.get("standard_campaign_slots"):
        errors.append("wave_allocation.template.yaml standard_campaign_slots does not match lab_profile")
    if bounds != profile_bounds:
        errors.append("wave_allocation.template.yaml campaign_run_budget_bounds does not match lab_profile")
    if not (bounds.get("min_runs", 0) <= bounds.get("default_runs", -1) <= bounds.get("max_runs", -1)):
        errors.append("wave_allocation.template.yaml campaign_run_budget_bounds must satisfy min <= default <= max")
    if wave_budget.get("l4_pair_budget") != (profile_policy.get("l4_pair_budget_policy") or {}).get("standard_pair_budget"):
        errors.append("wave_allocation.template.yaml l4_pair_budget does not match lab_profile standard_pair_budget")
    return errors


def validate_task_force_decommissioned(repo_root: Path) -> list[str]:
    errors: list[str] = []
    forbidden_paths = [
        repo_root / "docs" / "agent_control" / "codex_task_force_registry.yaml",
        repo_root / ".agents" / "skills" / "spacesonar-task-force-review" / "SKILL.md",
    ]
    for path in forbidden_paths:
        if path.exists():
            errors.append(f"{rel(path, repo_root)} must not exist because Task Force/sub-agents are disabled")
    policy_path = repo_root / "docs" / "policies" / "agent_allocation_policy.md"
    text = read_text(policy_path) if policy_path.exists() else ""
    required_phrases = ["Sub-agent / Task Force spawning is disabled", "There is no active Task Force roster"]
    for phrase in required_phrases:
        if phrase not in text:
            errors.append(f"docs/policies/agent_allocation_policy.md missing decommission phrase: {phrase}")
    return errors


def validate_agent_consult_receipts(repo_root: Path) -> list[str]:
    errors: list[str] = []
    for path in sorted(repo_root.glob("lab/**/*consult*.yaml")):
        data = load_yaml(path)
        if data.get("version") != "agent_consult_receipt_v2":
            continue
        label = rel(path, repo_root)
        if not label.startswith("lab/goals/goal_us100_onnx_forward_boundary_v0/task_force_consultation_initial"):
            errors.append(f"{label}: active agent consult receipts are disabled; keep only archived historical receipts")
    return errors


def validate_agent_operating_metrics_projection(repo_root: Path) -> list[str]:
    src_path = str(repo_root / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    from spacesonar.control_plane.agent_metrics import (
        AGENT_WINDOWS_PATH,
        agent_operating_events_diff,
        agent_operating_metrics_diff,
        validate_agent_observation_windows,
    )

    errors: list[str] = []
    if (repo_root / AGENT_WINDOWS_PATH).exists():
        errors.extend(validate_agent_observation_windows(repo_root))
    return [*errors, *agent_operating_events_diff(repo_root), *agent_operating_metrics_diff(repo_root)]


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


def validate_kpi_ledgers(repo_root: Path) -> list[str]:
    for path in [repo_root, repo_root / "src"]:
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)
    from foundation.validation.kpi_ledger_validator import validate as validate_kpi_ledger_records

    return validate_kpi_ledger_records(repo_root)


def validate_remote_repository_settings(repo_root: Path) -> list[str]:
    for path in [repo_root, repo_root / "src"]:
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)
    from foundation.validation.remote_repository_settings_verifier import validate_record

    return validate_record(repo_root)


def validate_operating_closeout(repo_root: Path) -> list[str]:
    current_policy_closeout = (
        repo_root
        / "lab"
        / "waves"
        / "wave_us100_closedbar_surface_cartography_v0"
        / "current_policy_closeout_amendment.yaml"
    )
    if current_policy_closeout.exists():
        payload = load_yaml(current_policy_closeout)
        if payload.get("status") == "wave01_current_policy_closed_complete":
            return []
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
        "foundation.validation.kpi_ledger_validator",
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
    errors.extend(validate_task_force_decommissioned(repo_root))
    errors.extend(validate_agent_consult_receipts(repo_root))
    errors.extend(validate_agent_operating_metrics_projection(repo_root))
    errors.extend(validate_execution_provenance(repo_root))
    errors.extend(validate_fresh_evaluators(repo_root))
    errors.extend(validate_kpi_ledgers(repo_root))
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
