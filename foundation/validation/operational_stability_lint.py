from __future__ import annotations

import argparse
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
    "source_of_truth_paths",
    "writer_owned_outputs",
    "validation_depth",
    "non_pytest_smokes",
    "skipped_broad_validations",
    "broad_validation_escalation_reason",
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
    ],
    ".agents/skills/spacesonar-workflow-drift-guard/SKILL.md": [
        "writer_scope_contract_checked",
        "Direct inspection findings must be converted",
    ],
    ".agents/skills/spacesonar-evidence-provenance/SKILL.md": [
        "writer-time manifest/receipt/hash checks",
        "writer_contract_version",
    ],
}

MOJIBAKE_MARKERS = [
    "\ufffd",
    "?쇱",
    "?뱀",
    "?꾨",
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
    if kernel.get("writer_scope_operating_contract_path") != "docs/agent_control/writer_scope_operating_contract.yaml":
        errors.append(f"{rel_path}: writer_scope_operating_contract_path mismatch")

    forbidden = as_set(kernel.get("forbidden_default_commands"))
    for command_id in sorted(FORBIDDEN_DEFAULT_COMMANDS - forbidden):
        errors.append(f"{rel_path}: forbidden_default_commands missing {command_id}")

    gate = kernel.get("broad_validation_command_intent_gate") or {}
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
    ]:
        if field not in enforcement:
            errors.append(f"{rel_path}: writer_contract_enforcement missing {field}")
    allowed_smokes = as_set(kernel.get("allowed_non_pytest_smokes"))
    if "claim_vocabulary_ascii_structure_lint" not in allowed_smokes:
        errors.append(f"{rel_path}: allowed_non_pytest_smokes missing claim_vocabulary_ascii_structure_lint")


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

    if contract.get("default_validation_depth") != "writer_scope_smoke":
        errors.append(f"{rel_path}: default_validation_depth must be writer_scope_smoke")
    required_fields = as_set(contract.get("required_writer_record_fields"))
    for field in sorted(WRITER_REQUIRED_FIELDS - required_fields):
        errors.append(f"{rel_path}: required_writer_record_fields missing {field}")

    forbidden = as_set(contract.get("forbidden_default_commands"))
    for command_id in sorted(FORBIDDEN_DEFAULT_COMMANDS - forbidden):
        errors.append(f"{rel_path}: forbidden_default_commands missing {command_id}")

    enforcement = contract.get("machine_enforcement") or {}
    for field in [
        "new_writer_records",
        "legacy_writer_reuse",
        "summary_or_closeout_records",
        "failure_policy",
    ]:
        if field not in enforcement:
            errors.append(f"{rel_path}: machine_enforcement missing {field}")


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
    }
    for key, expected_value in expected_refs.items():
        if rules.get(key) != expected_value:
            errors.append(f"{rel_path}: global_rules.{key} mismatch")
    for key in [
        "direct_inspection_policy",
        "writer_scope_operating_contract_policy",
        "broad_validation_command_gate_policy",
        "active_writer_contract_policy",
        "claim_vocabulary_policy",
    ]:
        if key not in rules:
            errors.append(f"{rel_path}: global_rules missing {key}")


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
        for phrase in ["workflow_dispatch", "acknowledge_not_default", "uv run pytest -q"]:
            if phrase not in regression_text:
                errors.append(f".github/workflows/full-regression.yml: missing {phrase}")


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
        ],
    )
    require_text(
        errors,
        repo_root,
        "foundation/pipelines/README.md",
        [
            "New or changed writers follow",
            "writer_contract_version",
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
        ],
    )
    for rel_path, phrases in SKILL_PHRASES.items():
        require_text(errors, repo_root, rel_path, phrases)

    evaluate_project_skills(errors, repo_root)
    evaluate_claim_vocabulary(errors, repo_root)
    evaluate_kernel(errors, repo_root)
    evaluate_writer_contract(errors, repo_root)
    evaluate_registry(errors, repo_root)
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
