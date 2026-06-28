from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import yaml


FORBIDDEN_DEFAULT_COMMANDS = {
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
}

WRITER_REQUIRED_FIELDS = {
    "primary_family",
    "primary_skill",
    "progress_class",
    "progress_effect",
    "next_executable_action",
    "experiment_or_boundary_effect",
    "source_of_truth_paths",
    "writer_owned_outputs",
    "validation_depth",
    "non_pytest_smokes",
    "skipped_broad_validations",
    "broad_validation_escalation_reason",
    "writer_preflight_gate",
    "validation_attempt_budget",
    "writer_scope_self_check",
    "claim_boundary",
    "forbidden_claims",
    "unresolved_blockers_or_none",
    "next_action_or_reopen_condition",
}

COMMAND_GATE_REQUIRED_FIELDS = {
    "command",
    "allowed_reason",
    "owner_surface",
    "source_of_truth_paths",
    "why_writer_scope_smoke_is_insufficient",
    "expected_claim_effect",
    "smaller_checks_already_attempted_or_not_applicable_reason",
}

STRICT_WRITER_FILENAMES = {
    "next_work_item.yaml",
    "workspace_state.yaml",
    "wave_allocation.yaml",
    "campaign_manifest.yaml",
    "campaign_closeout.yaml",
    "wave_closeout.yaml",
    "first_batch_run_specs_manifest.yaml",
    "proxy_execution_summary.yaml",
    "candidate_summary.yaml",
    "attempt_manifest.yaml",
}

PREFLIGHT_REQUIRED_NAMED_FIELDS = {
    "source_of_truth_paths",
    "writer_owned_outputs",
    "primary_family",
    "primary_skill",
    "progress_class",
    "progress_effect",
    "next_executable_action",
    "experiment_or_boundary_effect",
    "validation_attempt_budget",
    "claim_boundary",
    "forbidden_claims",
    "next_action_or_reopen_condition",
}

PROTECTED_CLAIM_KEYS = {
    "runtime_authority",
    "economics_pass",
    "live_readiness",
    "selected_baseline",
    "production_deployment",
    "goal_achieve",
    "materialization_ready",
    "handoff_complete",
    "reviewed_verified_pass",
}

COMMON_SKILL_PHRASES = [
    "Operational Stability Floor",
    "writer_scope_smoke",
    "writer_scope_operating_contract.yaml",
    "broad validation commands are not progress-loop defaults",
    "pytest, project validate, full regression, evidence graph, broad hash resync, or global registry regeneration",
]

SKILL_PHRASES = {
    ".agents/skills/spacesonar-session-bootstrap/SKILL.md": [
        "operational_stability_kernel.yaml",
        "writer_scope_operating_contract.yaml",
        "If the user asks to inspect all folders/files",
        "Do not spend the run loop traversing raw generated artifacts",
    ],
    ".agents/skills/spacesonar-architecture-guard/SKILL.md": [
        "writer_scope_contract_effect",
        "Broad validation commands are architecture-level escalation",
        "direct inspection repair matrix",
    ],
    ".agents/skills/spacesonar-code-change-quality/SKILL.md": [
        "no_pytest_reason",
        "For new or changed writers",
        "writer_contract_version",
        "writer_preflight_gate",
        "validation_attempt_budget",
        "src/spacesonar/control_plane/writer_contract.py",
    ],
    ".agents/skills/spacesonar-workflow-drift-guard/SKILL.md": [
        "writer_scope_contract_checked",
        "writer_preflight_gate_checked",
        "validation_attempt_budget_checked",
        "src/spacesonar/control_plane/writer_contract.py",
        "Direct inspection findings must be converted",
    ],
    ".agents/skills/spacesonar-evidence-provenance/SKILL.md": [
        "writer-time manifest/receipt/hash checks",
        "writer_contract_version",
        "writer_preflight_gate",
        "validation_attempt_budget",
        "src/spacesonar/control_plane/writer_contract.py",
    ],
}

MOJIBAKE_MARKERS = [
    "\ufffd",
]

MOJIBAKE_PATTERN = re.compile(r"\?[^\x00-\x7f]")

MOJIBAKE_SCAN_GLOBS = [
    "AGENTS.md",
    "docs/agent_control/*.yaml",
    ".agents/skills/*/SKILL.md",
    "src/spacesonar/control_plane/routing.py",
    "foundation/validation/*.py",
]


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def as_set(value: object) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, list):
        return {str(item) for item in value}
    return {str(value)}


def evaluate_validation_attempt_budget(errors: list[str], rel_path: str, budget: object) -> None:
    if not isinstance(budget, dict):
        errors.append(f"{rel_path}: validation_attempt_budget expected mapping")
        return
    if budget.get("max_writer_scope_attempts") != 2:
        errors.append(f"{rel_path}: validation_attempt_budget.max_writer_scope_attempts must be 2")
    attempts = as_set(budget.get("allowed_attempts"))
    for attempt in [
        "initial_writer_scope_smoke_after_write",
        "one_repair_then_same_scope_resmoke",
    ]:
        if attempt not in attempts:
            errors.append(f"{rel_path}: validation_attempt_budget.allowed_attempts missing {attempt}")
    if budget.get("third_attempt_effect") != "stop_and_record_blocker_or_escalation_gate":
        errors.append(f"{rel_path}: validation_attempt_budget.third_attempt_effect mismatch")
    if budget.get("broad_validation_resets_budget") is not False:
        errors.append(f"{rel_path}: validation_attempt_budget.broad_validation_resets_budget must be false")
    if (
        budget.get("repeated_same_failure_effect")
        != "move_invariant_into_writer_parser_adapter_manifest_or_scoped_lint_before_any_repeat"
    ):
        errors.append(f"{rel_path}: validation_attempt_budget.repeated_same_failure_effect mismatch")


def require_text(errors: list[str], repo_root: Path, rel_path: str, phrases: list[str]) -> None:
    path = repo_root / rel_path
    if not path.exists():
        errors.append(f"missing required file: {rel_path}")
        return
    text = read_text(path)
    for phrase in phrases:
        if phrase not in text:
            errors.append(f"{rel_path}: missing phrase {phrase!r}")


def evaluate_project_skills(errors: list[str], repo_root: Path) -> None:
    skills_root = repo_root / ".agents" / "skills"
    if not skills_root.exists():
        errors.append("missing project skills root: .agents/skills")
        return
    skill_files = sorted(skills_root.glob("*/SKILL.md"))
    if len(skill_files) < 20:
        errors.append(f".agents/skills: expected at least 20 project skills, found {len(skill_files)}")
    for path in skill_files:
        rel_path = path.relative_to(repo_root).as_posix()
        text = read_text(path)
        for phrase in COMMON_SKILL_PHRASES:
            if phrase not in text:
                errors.append(f"{rel_path}: missing operational stability floor phrase {phrase!r}")


def evaluate_claim_vocabulary(errors: list[str], repo_root: Path) -> None:
    rel_path = "docs/agent_control/claim_vocabulary.yaml"
    path = repo_root / rel_path
    if not path.exists():
        errors.append(f"missing claim vocabulary: {rel_path}")
        return

    text = read_text(path)
    if any(ord(char) > 127 for char in text):
        errors.append(f"{rel_path}: must stay ascii machine tokens only")
    for marker in MOJIBAKE_MARKERS:
        if marker in text:
            errors.append(f"{rel_path}: mojibake marker found {marker!r}")

    vocab = load_yaml(path)
    if not isinstance(vocab, dict):
        errors.append(f"{rel_path}: expected mapping")
        return
    if vocab.get("encoding_policy") != "ascii_machine_tokens_only_no_locale_text":
        errors.append(f"{rel_path}: encoding_policy mismatch")

    aliases = vocab.get("protected_claim_aliases") or {}
    if not isinstance(aliases, dict):
        errors.append(f"{rel_path}: protected_claim_aliases expected mapping")
        return
    for key in sorted(PROTECTED_CLAIM_KEYS):
        values = aliases.get(key)
        if not isinstance(values, list):
            errors.append(f"{rel_path}: protected_claim_aliases.{key} expected list")
            continue
        if key not in {str(value) for value in values}:
            errors.append(f"{rel_path}: protected_claim_aliases.{key} must include canonical token")

    substitutions = set(vocab.get("forbidden_substitutions") or [])
    for item in [
        "pytest_cannot_replace_writer_manifest_receipt_hash_contract",
        "full_regression_cannot_replace_current_work_item_next_executable_step",
    ]:
        if item not in substitutions:
            errors.append(f"{rel_path}: forbidden_substitutions missing {item}")


def evaluate_mojibake_control_surfaces(errors: list[str], repo_root: Path) -> None:
    checked: set[Path] = set()
    for pattern in MOJIBAKE_SCAN_GLOBS:
        paths = [repo_root / pattern] if "*" not in pattern else list(repo_root.glob(pattern))
        for path in sorted(paths):
            if path in checked or not path.exists() or not path.is_file():
                continue
            checked.add(path)
            rel_path = path.relative_to(repo_root).as_posix()
            text = read_text(path)
            for marker in MOJIBAKE_MARKERS:
                if marker in text:
                    errors.append(f"{rel_path}: mojibake marker found {marker!r}")
            match = MOJIBAKE_PATTERN.search(text)
            if match:
                errors.append(f"{rel_path}: mojibake-like token found {match.group(0)!r}")


def evaluate_kernel(errors: list[str], repo_root: Path) -> None:
    rel_path = "docs/agent_control/operational_stability_kernel.yaml"
    path = repo_root / rel_path
    if not path.exists():
        errors.append(f"missing operational stability kernel: {rel_path}")
        return
    kernel = load_yaml(path)
    if not isinstance(kernel, dict):
        errors.append(f"{rel_path}: expected mapping")
        return

    if kernel.get("default_validation_depth") != "writer_scope_smoke":
        errors.append(f"{rel_path}: default_validation_depth must be writer_scope_smoke")
    if kernel.get("default_progress_unit") != "next_executable_experiment_writer_or_probe":
        errors.append(f"{rel_path}: default_progress_unit must be next_executable_experiment_writer_or_probe")
    if kernel.get("writer_scope_operating_contract_path") != "docs/agent_control/writer_scope_operating_contract.yaml":
        errors.append(f"{rel_path}: writer_scope_operating_contract_path mismatch")
    if kernel.get("strong_trigger_revision") != "validation_attempt_budget_v1":
        errors.append(f"{rel_path}: strong_trigger_revision mismatch")
    if kernel.get("global_write_time_guard_path") != "src/spacesonar/control_plane/writer_contract.py":
        errors.append(f"{rel_path}: global_write_time_guard_path mismatch")
    if kernel.get("transaction_write_time_guard_path") != "src/spacesonar/control_plane/transaction.py":
        errors.append(f"{rel_path}: transaction_write_time_guard_path mismatch")

    forbidden = as_set(kernel.get("forbidden_default_commands"))
    for command_id in sorted(FORBIDDEN_DEFAULT_COMMANDS - forbidden):
        errors.append(f"{rel_path}: forbidden_default_commands missing {command_id}")

    gate = kernel.get("broad_validation_command_intent_gate") or {}
    allowed_reasons = as_set(gate.get("allowed_only_when_one_of"))
    for automatic_boundary in ["campaign_closeout", "wave_closeout"]:
        if automatic_boundary in allowed_reasons:
            errors.append(f"{rel_path}: broad validation must not be automatically allowed by {automatic_boundary}")
    if "campaign_or_wave_boundary_with_recorded_archive_escalation_reason" not in allowed_reasons:
        errors.append(f"{rel_path}: broad_validation_command_intent_gate missing recorded archive escalation boundary reason")
    required_record = as_set(gate.get("required_record_before_running"))
    for field in sorted(COMMAND_GATE_REQUIRED_FIELDS - required_record):
        errors.append(f"{rel_path}: broad_validation_command_intent_gate missing {field}")

    matrix = kernel.get("direct_inspection_repair_matrix") or []
    if not isinstance(matrix, list) or len(matrix) < 15:
        errors.append(f"{rel_path}: direct_inspection_repair_matrix must contain at least 15 owner surfaces")
    else:
        for index, item in enumerate(matrix, start=1):
            if not isinstance(item, dict):
                errors.append(f"{rel_path}: direct_inspection_repair_matrix[{index}] expected mapping")
                continue
            for field in ["surface", "inspect", "gap_repair_target"]:
                if field not in item:
                    errors.append(f"{rel_path}: direct_inspection_repair_matrix[{index}] missing {field}")

    enforcement = kernel.get("writer_contract_enforcement") or {}
    for field in [
        "new_or_changed_writer_without_contract",
        "legacy_writer_reuse_without_contract",
        "broad_validation_finds_writer_gap",
        "required_writer_preflight_field",
        "required_validation_attempt_budget_field",
        "global_write_time_guard_required",
        "transaction_stage_yaml_enforces_strict_writer_surfaces",
    ]:
        if field not in enforcement:
            errors.append(f"{rel_path}: writer_contract_enforcement missing {field}")
    forbidden_gap_response = as_set(enforcement.get("forbidden_gap_response"))
    if "repeat_writer_scope_smoke_after_two_attempts_without_blocker_or_escalation_record" not in forbidden_gap_response:
        errors.append(f"{rel_path}: writer_contract_enforcement.forbidden_gap_response missing two-pass repeat guard")

    evaluate_validation_attempt_budget(errors, rel_path, kernel.get("validation_attempt_budget"))

    guarded = kernel.get("write_time_guarded_surfaces") or {}
    if guarded.get("guard_module") != "src/spacesonar/control_plane/writer_contract.py":
        errors.append(f"{rel_path}: write_time_guarded_surfaces.guard_module mismatch")
    if guarded.get("transaction_hook") != "ControlPlaneTransaction.stage_yaml":
        errors.append(f"{rel_path}: write_time_guarded_surfaces.transaction_hook mismatch")
    for filename in sorted(STRICT_WRITER_FILENAMES):
        if filename not in as_set(guarded.get("strict_writer_filenames")):
            errors.append(f"{rel_path}: write_time_guarded_surfaces.strict_writer_filenames missing {filename}")

    allowed_smokes = as_set(kernel.get("allowed_non_pytest_smokes"))
    if "claim_vocabulary_ascii_structure_lint" not in allowed_smokes:
        errors.append(f"{rel_path}: allowed_non_pytest_smokes missing claim_vocabulary_ascii_structure_lint")
    if "run_writer_scope_contract_lint_for_touched_writer_records" not in allowed_smokes:
        errors.append(f"{rel_path}: allowed_non_pytest_smokes missing run_writer_scope_contract_lint_for_touched_writer_records")

    hard = kernel.get("hard_enforcement_points") or {}
    before_write = as_set(hard.get("writer_before_write"))
    for field in [
        "writer_preflight_gate_passed_before_mutation",
        "validation_attempt_budget_declared",
    ]:
        if field not in before_write:
            errors.append(f"{rel_path}: hard_enforcement_points.writer_before_write missing {field}")
    after_write = as_set(hard.get("writer_after_write"))
    if "validation_attempt_budget_observed_and_not_exceeded" not in after_write:
        errors.append(
            f"{rel_path}: hard_enforcement_points.writer_after_write missing validation_attempt_budget_observed_and_not_exceeded"
        )

    writer_commands = kernel.get("writer_scope_commands") or {}
    if "writer_scope_contract_lint" not in writer_commands:
        errors.append(f"{rel_path}: writer_scope_commands missing writer_scope_contract_lint")

    experiment_loop = kernel.get("experiment_first_loop") or {}
    if experiment_loop.get("default_progress_unit") != "next_executable_experiment_writer_or_probe":
        errors.append(f"{rel_path}: experiment_first_loop.default_progress_unit mismatch")
    progress_negatives = as_set(experiment_loop.get("not_progress"))
    for item in ["validation", "inspection", "registry_projection"]:
        if item not in progress_negatives:
            errors.append(f"{rel_path}: experiment_first_loop.not_progress missing {item}")
    if experiment_loop.get("generic_review_gates_after_experiment_first") != "forbidden_unless_blocker_requires_user_choice":
        errors.append(f"{rel_path}: experiment_first_loop generic review gate policy mismatch")
    campaign_open = experiment_loop.get("campaign_open") or {}
    if campaign_open.get("default_proxy_spec_count") != 18:
        errors.append(f"{rel_path}: experiment_first_loop.campaign_open.default_proxy_spec_count must be 18")
    if campaign_open.get("meaningful_multi_axis_surface_required") is not True:
        errors.append(f"{rel_path}: experiment_first_loop.campaign_open must require a multi-axis surface")
    tiny_samples = experiment_loop.get("tiny_validation_samples") or {}
    if tiny_samples.get("default") != "forbidden":
        errors.append(f"{rel_path}: experiment_first_loop.tiny_validation_samples.default must be forbidden")
    broad_policy = experiment_loop.get("broad_validation") or {}
    if broad_policy.get("boundary_auto_allow") is not False:
        errors.append(f"{rel_path}: experiment_first_loop.broad_validation.boundary_auto_allow must be false")


def evaluate_writer_contract(errors: list[str], repo_root: Path) -> None:
    rel_path = "docs/agent_control/writer_scope_operating_contract.yaml"
    path = repo_root / rel_path
    if not path.exists():
        errors.append(f"missing writer scope operating contract: {rel_path}")
        return
    contract = load_yaml(path)
    if not isinstance(contract, dict):
        errors.append(f"{rel_path}: expected mapping")
        return

    if contract.get("version") != "writer_scope_operating_contract_v3":
        errors.append(f"{rel_path}: version must be writer_scope_operating_contract_v3")
    if contract.get("default_validation_depth") != "writer_scope_smoke":
        errors.append(f"{rel_path}: default_validation_depth must be writer_scope_smoke")
    if contract.get("default_progress_unit") != "next_executable_experiment_writer_or_probe":
        errors.append(f"{rel_path}: default_progress_unit must be next_executable_experiment_writer_or_probe")
    if contract.get("strong_trigger_revision") != "validation_attempt_budget_v1":
        errors.append(f"{rel_path}: strong_trigger_revision mismatch")
    if contract.get("global_write_time_guard") != "src/spacesonar/control_plane/writer_contract.py":
        errors.append(f"{rel_path}: global_write_time_guard mismatch")
    required_fields = as_set(contract.get("required_writer_record_fields"))
    for field in sorted(WRITER_REQUIRED_FIELDS - required_fields):
        errors.append(f"{rel_path}: required_writer_record_fields missing {field}")

    forbidden = as_set(contract.get("forbidden_default_commands"))
    for command_id in sorted(FORBIDDEN_DEFAULT_COMMANDS - forbidden):
        errors.append(f"{rel_path}: forbidden_default_commands missing {command_id}")

    gate = contract.get("broad_validation_command_intent_gate") or {}
    allowed_reasons = as_set(gate.get("allowed_only_when_one_of"))
    for automatic_boundary in ["campaign_closeout", "wave_closeout"]:
        if automatic_boundary in allowed_reasons:
            errors.append(f"{rel_path}: broad validation must not be automatically allowed by {automatic_boundary}")
    if "campaign_or_wave_boundary_with_recorded_archive_escalation_reason" not in allowed_reasons:
        errors.append(f"{rel_path}: broad_validation_command_intent_gate missing recorded archive escalation boundary reason")
    required_record = as_set(gate.get("required_record_before_running"))
    for field in sorted(COMMAND_GATE_REQUIRED_FIELDS - required_record):
        errors.append(f"{rel_path}: broad_validation_command_intent_gate missing {field}")

    enforcement = contract.get("machine_enforcement") or {}
    for field in [
        "new_writer_records",
        "legacy_writer_reuse",
        "summary_or_closeout_records",
        "failure_policy",
    ]:
        if field not in enforcement:
            errors.append(f"{rel_path}: machine_enforcement missing {field}")

    new_records = enforcement.get("new_writer_records") or {}
    if new_records.get("required_write_time_guard") != "src/spacesonar/control_plane/writer_contract.py":
        errors.append(f"{rel_path}: machine_enforcement.new_writer_records.required_write_time_guard mismatch")
    for field in ["missing_preflight_gate_effect", "missing_validation_attempt_budget_effect"]:
        if field not in new_records:
            errors.append(f"{rel_path}: machine_enforcement.new_writer_records missing {field}")

    before_gate = contract.get("writer_before_write_gate") or {}
    missing_before = as_set(before_gate.get("fail_before_mutation_when_missing"))
    for field in [
        "writer_contract_version",
        "progress_class",
        "progress_effect",
        "next_executable_action",
        "experiment_or_boundary_effect",
        "validation_attempt_budget",
        "claim_boundary",
    ]:
        if field not in missing_before:
            errors.append(f"{rel_path}: writer_before_write_gate.fail_before_mutation_when_missing missing {field}")
    preflight = before_gate.get("required_preflight_record") or {}
    if preflight.get("status") != "passed_before_mutation":
        errors.append(f"{rel_path}: writer_before_write_gate.required_preflight_record.status mismatch")
    if preflight.get("checked_before_mutation") is not True:
        errors.append(f"{rel_path}: writer_before_write_gate.required_preflight_record.checked_before_mutation must be true")
    if preflight.get("fail_closed_when_missing") is not True:
        errors.append(f"{rel_path}: writer_before_write_gate.required_preflight_record.fail_closed_when_missing must be true")
    named_fields = as_set(preflight.get("required_fields_named"))
    for field in sorted(PREFLIGHT_REQUIRED_NAMED_FIELDS - named_fields):
        errors.append(f"{rel_path}: writer_before_write_gate.required_preflight_record missing named field {field}")

    evaluate_validation_attempt_budget(errors, rel_path, (contract.get("validation_attempt_budget") or {}).get("default"))

    guarded = contract.get("write_time_guarded_surfaces") or {}
    if guarded.get("transaction_stage_yaml_enforced_by") != "src/spacesonar/control_plane/transaction.py":
        errors.append(f"{rel_path}: write_time_guarded_surfaces.transaction_stage_yaml_enforced_by mismatch")
    for filename in sorted(STRICT_WRITER_FILENAMES):
        if filename not in as_set(guarded.get("strict_writer_filenames")):
            errors.append(f"{rel_path}: write_time_guarded_surfaces.strict_writer_filenames missing {filename}")

    after_gate = contract.get("writer_after_write_gate") or {}
    missing_after = as_set(after_gate.get("fail_writer_local_when_missing"))
    if "validation_attempt_budget_observed_and_not_exceeded" not in missing_after:
        errors.append(f"{rel_path}: writer_after_write_gate missing validation_attempt_budget_observed_and_not_exceeded")

    progress = contract.get("progress_semantics") or {}
    if progress.get("validation_is_progress") is not False:
        errors.append(f"{rel_path}: progress_semantics.validation_is_progress must be false")
    if progress.get("inspection_is_progress") is not False:
        errors.append(f"{rel_path}: progress_semantics.inspection_is_progress must be false")
    if progress.get("registry_projection_is_proof") is not False:
        errors.append(f"{rel_path}: progress_semantics.registry_projection_is_proof must be false")
    if progress.get("default_progress_unit") != "next_executable_experiment_writer_or_probe":
        errors.append(f"{rel_path}: progress_semantics.default_progress_unit mismatch")
    forbidden_success = as_set(progress.get("forbidden_success_progress_classes"))
    for item in ["validation_only", "review_only", "inspection_only"]:
        if item not in forbidden_success:
            errors.append(f"{rel_path}: progress_semantics.forbidden_success_progress_classes missing {item}")


def evaluate_registry(errors: list[str], repo_root: Path) -> None:
    rel_path = "docs/agent_control/work_family_registry.yaml"
    registry = load_yaml(repo_root / rel_path)
    if not isinstance(registry, dict):
        errors.append(f"{rel_path}: expected mapping")
        return
    rules = registry.get("global_rules") or {}
    expected_refs = {
        "operational_stability_kernel": "docs/agent_control/operational_stability_kernel.yaml",
        "writer_scope_operating_contract": "docs/agent_control/writer_scope_operating_contract.yaml",
        "operational_stability_lint": "foundation/validation/operational_stability_lint.py",
        "global_write_time_guard": "src/spacesonar/control_plane/writer_contract.py",
    }
    for key, expected_value in expected_refs.items():
        if rules.get(key) != expected_value:
            errors.append(f"{rel_path}: global_rules.{key} mismatch")
    for key in [
        "direct_inspection_policy",
        "experiment_first_progress_policy",
        "generic_review_gate_policy",
        "campaign_open_default_proxy_spec_policy",
        "tiny_validation_sample_policy",
        "writer_scope_operating_contract_policy",
        "writer_preflight_gate_policy",
        "validation_attempt_budget_policy",
        "write_time_guard_policy",
        "broad_validation_command_gate_policy",
        "active_writer_contract_policy",
        "claim_vocabulary_policy",
    ]:
        if key not in rules:
            errors.append(f"{rel_path}: global_rules missing {key}")


def evaluate_lab_profile(errors: list[str], repo_root: Path) -> None:
    rel_path = "docs/workspace/lab_profile.yaml"
    path = repo_root / rel_path
    if not path.exists():
        errors.append(f"missing lab profile: {rel_path}")
        return
    profile = load_yaml(path)
    if not isinstance(profile, dict):
        errors.append(f"{rel_path}: expected mapping")
        return
    run_loop = (
        profile.get("execution_weight_policy", {})
        .get("validation_cadence", {})
        .get("run_loop_default", {})
    )
    guard = run_loop.get("write_time_guard") or {}
    if guard.get("guard_module") != "src/spacesonar/control_plane/writer_contract.py":
        errors.append(f"{rel_path}: run_loop_default.write_time_guard.guard_module mismatch")
    if guard.get("transaction_hook") != "ControlPlaneTransaction.stage_yaml":
        errors.append(f"{rel_path}: run_loop_default.write_time_guard.transaction_hook mismatch")
    if guard.get("strict_writer_surfaces_fail_before_mutation") is not True:
        errors.append(f"{rel_path}: run_loop_default.write_time_guard.strict_writer_surfaces_fail_before_mutation must be true")
    required_fields = as_set(run_loop.get("required_writer_contract_fields"))
    for field in ["writer_preflight_gate", "validation_attempt_budget"]:
        if field not in required_fields:
            errors.append(f"{rel_path}: run_loop_default.required_writer_contract_fields missing {field}")
    evaluate_validation_attempt_budget(errors, rel_path, run_loop.get("validation_attempt_budget"))
    loop = profile.get("experiment_first_operating_loop") or {}
    if loop.get("default_progress_unit") != "next_executable_experiment_writer_or_probe":
        errors.append(f"{rel_path}: experiment_first_operating_loop.default_progress_unit mismatch")
    if loop.get("validation_is_progress") is not False:
        errors.append(f"{rel_path}: experiment_first_operating_loop.validation_is_progress must be false")
    if loop.get("inspection_is_progress") is not False:
        errors.append(f"{rel_path}: experiment_first_operating_loop.inspection_is_progress must be false")
    if loop.get("registry_projection_is_proof") is not False:
        errors.append(f"{rel_path}: experiment_first_operating_loop.registry_projection_is_proof must be false")
    campaign_open = loop.get("campaign_open") or {}
    if campaign_open.get("default_proxy_spec_count") != 18:
        errors.append(f"{rel_path}: experiment_first_operating_loop.campaign_open.default_proxy_spec_count must be 18")
    if campaign_open.get("meaningful_multi_axis_surface_required") is not True:
        errors.append(f"{rel_path}: experiment_first_operating_loop.campaign_open must require a multi-axis surface")


def evaluate_write_time_guard(errors: list[str], repo_root: Path) -> None:
    guard_path = repo_root / "src/spacesonar/control_plane/writer_contract.py"
    transaction_path = repo_root / "src/spacesonar/control_plane/transaction.py"
    if not guard_path.exists():
        errors.append("missing write-time guard: src/spacesonar/control_plane/writer_contract.py")
        return
    guard_text = read_text(guard_path)
    for phrase in [
        "def enforce_writer_contract",
        "def writer_contract_required_for_path",
        "writer_scope_operating_contract_v3",
        "STRICT_WRITER_FILENAMES",
        "FORBIDDEN_SUCCESS_PROGRESS_CLASSES",
        "next_executable_experiment_writer_or_probe",
        "validation_only",
        "review_only",
        "inspection_only",
        *sorted(STRICT_WRITER_FILENAMES),
        "observed_writer_scope_attempts exceeds 2",
    ]:
        if phrase not in guard_text:
            errors.append(f"src/spacesonar/control_plane/writer_contract.py: missing {phrase}")
    if not transaction_path.exists():
        errors.append("missing transaction writer: src/spacesonar/control_plane/transaction.py")
        return
    transaction_text = read_text(transaction_path)
    for phrase in [
        "from .writer_contract import enforce_writer_contract",
        "enforce_writer_contract(rel, data)",
    ]:
        if phrase not in transaction_text:
            errors.append(f"src/spacesonar/control_plane/transaction.py: missing {phrase}")


def evaluate_ci(errors: list[str], repo_root: Path) -> None:
    rel_path = ".github/workflows/control-plane.yml"
    path = repo_root / rel_path
    if not path.exists():
        errors.append(f"missing CI workflow: {rel_path}")
        return
    text = read_text(path)
    for phrase in [
        "foundation/validation/operational_stability_lint.py",
        "docs/agent_control/writer_scope_operating_contract.yaml",
        "docs/agent_control/codex_operating_format.yaml",
    ]:
        if phrase not in text:
            errors.append(f"{rel_path}: missing {phrase}")

    full_regression = repo_root / ".github/workflows/full-regression.yml"
    if full_regression.exists():
        regression_text = read_text(full_regression)
        for phrase in [
            "workflow_dispatch",
            "acknowledge_not_default",
            "allowed_reason",
            "owner_surface",
            "source_of_truth_paths",
            "why_writer_scope_smoke_is_insufficient",
            "expected_claim_effect",
            "smaller_checks_already_attempted_or_not_applicable_reason",
            "claim_boundary",
            "uv run pytest -q",
        ]:
            if phrase not in regression_text:
                errors.append(f".github/workflows/full-regression.yml: missing {phrase}")

    mt5_manual = repo_root / ".github/workflows/mt5-runtime-manual.yml"
    if mt5_manual.exists():
        mt5_text = read_text(mt5_manual)
        for forbidden in [
            "active_record_validator.py --repo-root .",
            "control_plane_validator.py --repo-root .",
            "pytest -q",
        ]:
            if forbidden in mt5_text:
                errors.append(f".github/workflows/mt5-runtime-manual.yml: forbidden routine broad command {forbidden}")


def evaluate(repo_root: Path) -> list[str]:
    errors: list[str] = []
    require_text(
        errors,
        repo_root,
        "AGENTS.md",
        [
            "GUARD_007_OPERATIONAL_STABILITY",
            "operational_stability_kernel.yaml",
            "writer_scope_operating_contract.yaml",
            "Direct inspection means source-of-truth",
            "Strong trigger rule",
            "validation_attempt_budget",
            "src/spacesonar/control_plane/writer_contract.py",
            "ControlPlaneTransaction.stage_yaml",
        ],
    )
    require_text(
        errors,
        repo_root,
        "foundation/pipelines/README.md",
        [
            "New or changed writers follow",
            "writer_contract_version",
            "writer_preflight_gate",
            "validation_attempt_budget",
            "src/spacesonar/control_plane/writer_contract.py",
            "ControlPlaneTransaction.stage_yaml",
            "Broad validation requires a recorded command-intent gate",
        ],
    )
    require_text(
        errors,
        repo_root,
        "foundation/validation/README.md",
        [
            "operational_stability_lint.py",
            "Default operation must not call `pytest`",
            "Broad validation commands require the operational command-intent gate",
            "claim_vocabulary.yaml",
            "writer_scope_contract_lint.py",
            "src/spacesonar/control_plane/writer_contract.py",
            "two passes",
        ],
    )
    for rel_path, phrases in SKILL_PHRASES.items():
        require_text(errors, repo_root, rel_path, phrases)

    evaluate_project_skills(errors, repo_root)
    evaluate_mojibake_control_surfaces(errors, repo_root)
    evaluate_claim_vocabulary(errors, repo_root)
    evaluate_kernel(errors, repo_root)
    evaluate_writer_contract(errors, repo_root)
    evaluate_registry(errors, repo_root)
    evaluate_lab_profile(errors, repo_root)
    evaluate_write_time_guard(errors, repo_root)
    evaluate_ci(errors, repo_root)
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
    print("operational stability lint passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
