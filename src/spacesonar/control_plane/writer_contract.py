from __future__ import annotations

from pathlib import Path
from typing import Any


WRITER_CONTRACT_VERSION = "writer_scope_operating_contract_v2"

REQUIRED_WRITER_FIELDS = {
    "writer_contract_version",
    "primary_family",
    "primary_skill",
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

PREFLIGHT_REQUIRED_NAMED_FIELDS = {
    "source_of_truth_paths",
    "writer_owned_outputs",
    "primary_family",
    "primary_skill",
    "validation_attempt_budget",
    "claim_boundary",
    "forbidden_claims",
    "next_action_or_reopen_condition",
}

ALLOWED_ATTEMPTS = {
    "initial_writer_scope_smoke_after_write",
    "one_repair_then_same_scope_resmoke",
}

THIRD_ATTEMPT_EFFECT = "stop_and_record_blocker_or_escalation_gate"
REPEATED_FAILURE_EFFECT = "move_invariant_into_writer_parser_adapter_manifest_or_scoped_lint_before_any_repeat"

STRICT_WRITER_FILENAMES = {
    "next_work_item.yaml",
    "campaign_closeout.yaml",
    "wave_closeout.yaml",
    "candidate_summary.yaml",
    "attempt_manifest.yaml",
}


def default_writer_preflight_gate() -> dict[str, Any]:
    return {
        "status": "passed_before_mutation",
        "checked_before_mutation": True,
        "fail_closed_when_missing": True,
        "required_fields_named": [
            "source_of_truth_paths",
            "writer_owned_outputs",
            "primary_family",
            "primary_skill",
            "validation_attempt_budget",
            "claim_boundary",
            "forbidden_claims",
            "next_action_or_reopen_condition",
        ],
    }


def default_validation_attempt_budget() -> dict[str, Any]:
    return {
        "max_writer_scope_attempts": 2,
        "allowed_attempts": [
            "initial_writer_scope_smoke_after_write",
            "one_repair_then_same_scope_resmoke",
        ],
        "third_attempt_effect": THIRD_ATTEMPT_EFFECT,
        "broad_validation_resets_budget": False,
        "repeated_same_failure_effect": REPEATED_FAILURE_EFFECT,
        "observed_writer_scope_attempts": 0,
    }


def writer_contract_required_for_path(rel_path: str | Path, payload: dict[str, Any] | None = None) -> bool:
    rel = Path(str(rel_path).replace("\\", "/"))
    name = rel.name
    text = rel.as_posix()
    if payload and payload.get("writer_contract_version"):
        return True
    if name in STRICT_WRITER_FILENAMES:
        return True
    if text.startswith("lab/campaigns/") and name.endswith("_summary.yaml"):
        return True
    if text.startswith("lab/campaigns/") and name == "summary.yaml":
        return True
    return False


def writer_contract_errors(rel_path: str | Path, payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    label = Path(str(rel_path).replace("\\", "/")).as_posix()
    missing = sorted(REQUIRED_WRITER_FIELDS - set(payload))
    errors.extend(f"{label}: missing writer contract field {field}" for field in missing)

    for field in [
        "primary_family",
        "primary_skill",
        "validation_depth",
        "broad_validation_escalation_reason",
        "claim_boundary",
        "next_action_or_reopen_condition",
    ]:
        _require_non_empty_text(errors, label, payload, field)
    for field in [
        "source_of_truth_paths",
        "writer_owned_outputs",
        "non_pytest_smokes",
        "skipped_broad_validations",
        "forbidden_claims",
    ]:
        _require_non_empty_list(errors, label, payload, field)
    for field in ["source_of_truth_paths", "writer_owned_outputs"]:
        _require_repo_relative_paths(errors, label, payload, field)

    if payload.get("writer_contract_version") != WRITER_CONTRACT_VERSION:
        errors.append(f"{label}: writer_contract_version must be {WRITER_CONTRACT_VERSION}")
    if payload.get("validation_depth") != "writer_scope_smoke":
        errors.append(f"{label}: validation_depth must be writer_scope_smoke")

    self_check = payload.get("writer_scope_self_check")
    if not isinstance(self_check, dict):
        errors.append(f"{label}: writer_scope_self_check must be a mapping")
    elif self_check.get("status") in {"pending_after_write", "required_before_close", None, ""}:
        errors.append(f"{label}: writer_scope_self_check.status cannot be pending or empty")

    gate = payload.get("writer_preflight_gate")
    if not isinstance(gate, dict):
        errors.append(f"{label}: writer_preflight_gate must be a mapping")
    else:
        if gate.get("status") != "passed_before_mutation":
            errors.append(f"{label}: writer_preflight_gate.status must be passed_before_mutation")
        if gate.get("checked_before_mutation") is not True:
            errors.append(f"{label}: writer_preflight_gate.checked_before_mutation must be true")
        if gate.get("fail_closed_when_missing") is not True:
            errors.append(f"{label}: writer_preflight_gate.fail_closed_when_missing must be true")
        named = _as_set(gate.get("required_fields_named"))
        for field in sorted(PREFLIGHT_REQUIRED_NAMED_FIELDS - named):
            errors.append(f"{label}: writer_preflight_gate.required_fields_named missing {field}")

    budget = payload.get("validation_attempt_budget")
    if not isinstance(budget, dict):
        errors.append(f"{label}: validation_attempt_budget must be a mapping")
    else:
        if budget.get("max_writer_scope_attempts") != 2:
            errors.append(f"{label}: validation_attempt_budget.max_writer_scope_attempts must be 2")
        attempts = _as_set(budget.get("allowed_attempts"))
        for attempt in sorted(ALLOWED_ATTEMPTS - attempts):
            errors.append(f"{label}: validation_attempt_budget.allowed_attempts missing {attempt}")
        if budget.get("third_attempt_effect") != THIRD_ATTEMPT_EFFECT:
            errors.append(f"{label}: validation_attempt_budget.third_attempt_effect mismatch")
        if budget.get("broad_validation_resets_budget") is not False:
            errors.append(f"{label}: validation_attempt_budget.broad_validation_resets_budget must be false")
        if budget.get("repeated_same_failure_effect") != REPEATED_FAILURE_EFFECT:
            errors.append(f"{label}: validation_attempt_budget.repeated_same_failure_effect mismatch")
        observed = budget.get("observed_writer_scope_attempts", 0)
        if not isinstance(observed, int):
            errors.append(f"{label}: validation_attempt_budget.observed_writer_scope_attempts must be an integer")
        elif observed > 2:
            errors.append(f"{label}: validation_attempt_budget.observed_writer_scope_attempts exceeds 2")

    return errors


def enforce_writer_contract(rel_path: str | Path, payload: dict[str, Any]) -> None:
    if not writer_contract_required_for_path(rel_path, payload):
        return
    errors = writer_contract_errors(rel_path, payload)
    if errors:
        raise ValueError("writer contract preflight failed before mutation: " + "; ".join(errors))


def _as_set(value: object) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, list):
        return {str(item) for item in value}
    return {str(value)}


def _require_non_empty_text(errors: list[str], label: str, payload: dict[str, Any], field: str) -> None:
    if field not in payload:
        return
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label}: {field} must be non-empty text")


def _require_non_empty_list(errors: list[str], label: str, payload: dict[str, Any], field: str) -> None:
    if field not in payload:
        return
    value = payload.get(field)
    if not isinstance(value, list) or not value or any(str(item).strip() == "" for item in value):
        errors.append(f"{label}: {field} must be a non-empty list")


def _require_repo_relative_paths(errors: list[str], label: str, payload: dict[str, Any], field: str) -> None:
    value = payload.get(field)
    if not isinstance(value, list):
        return
    for item in value:
        text = str(item).replace("\\", "/")
        path = Path(text)
        if path.is_absolute() or ".." in path.parts:
            errors.append(f"{label}: {field} path must be repo-relative: {item}")
