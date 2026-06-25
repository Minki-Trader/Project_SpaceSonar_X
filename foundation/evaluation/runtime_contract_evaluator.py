from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation.evaluation.common import evaluation_time_utc, file_sha256, finalize_result, implementation_hashes, load_yaml, write_yaml
from foundation.migrations.runtime_graph_target_inventory import (
    EXPECTED_ATTEMPT_COUNT,
    EXPECTED_PAIR_GROUP_COUNT,
    EXPECTED_SURFACE_KIND_COUNTS,
    INVENTORY_REL_PATH,
    discover_wave_l4_attempt_manifest_paths,
    inventory_attempts,
    load_runtime_graph_target_inventory,
    validate_runtime_graph_target_inventory,
)
from foundation.mt5.runtime_completion import RuntimeEvidencePaths, evaluate_runtime_attempt, reconstruct_runtime_attempt
from foundation.mt5.tester_report_receipt import (
    load_receipt,
    tester_report_completed,
    validate_tester_report_receipt_binding,
)
from spacesonar.control_plane.store import filesystem_path


EVALUATOR_ID = "runtime_contract_evaluator_v2"
REQUIRED_PERIOD_ROLES = ("validation", "research_oos")
ELIGIBLE_COMPLETION_SCOPES = ("full_period_deterministic", "full_period_sparse_decision_surface")


def path_exists(path: Path) -> bool:
    return os.path.exists(filesystem_path(path))


def input_hash_or_missing(repo_root: Path, rel_path: str | None) -> dict[str, Any]:
    if not rel_path:
        return {"path": None, "missing": True, "sha256": None, "size_bytes": None}
    path = repo_root / rel_path
    if not path_exists(path):
        return {"path": rel_path, "missing": True, "sha256": None, "size_bytes": None}
    return {
        "path": rel_path,
        "missing": False,
        "sha256": file_sha256(path),
        "size_bytes": os.stat(filesystem_path(path)).st_size,
    }


def group_key(entry: dict[str, Any]) -> str:
    return "|".join(
        [
            str(entry.get("campaign_id") or ""),
            str(entry.get("cell_id") or ""),
            str(entry.get("runtime_surface_kind") or ""),
        ]
    )


def _target_identity(entry: dict[str, Any]) -> str:
    return "|".join(
        [
            str(entry.get("campaign_id") or ""),
            str(entry.get("cell_id") or ""),
            str(entry.get("runtime_surface_kind") or ""),
            str(entry.get("period_role") or ""),
        ]
    )


def _duplicate_count(values: list[str]) -> int:
    counts = Counter(value for value in values if value)
    return sum(count - 1 for count in counts.values() if count > 1)


def _finding(findings: list[dict[str, Any]], finding_id: str, **kwargs: Any) -> None:
    findings.append({"id": finding_id, **kwargs})


def evaluate_runtime_contract(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    inventory = load_runtime_graph_target_inventory(repo_root)
    attempts = sorted(
        inventory_attempts(inventory),
        key=lambda item: (
            str(item.get("campaign_id") or ""),
            str(item.get("cell_id") or ""),
            str(item.get("runtime_surface_kind") or ""),
            0 if item.get("period_role") == "validation" else 1,
            str(item.get("attempt_id") or ""),
        ),
    )
    inventory_errors = validate_runtime_graph_target_inventory(repo_root, inventory)
    inventory_paths = {str(item.get("manifest_path") or "") for item in attempts}
    discovered_paths = set(discover_wave_l4_attempt_manifest_paths(repo_root))
    unexpected_paths = sorted(discovered_paths - inventory_paths)
    missing_inventory_paths = sorted(inventory_paths - discovered_paths)

    missing = Counter()
    terminal_modes = Counter()
    surface_kinds = Counter(str(item.get("runtime_surface_kind") or "") for item in attempts)
    findings: list[dict[str, Any]] = []
    attempt_results: list[dict[str, Any]] = []
    input_hashes: list[dict[str, Any]] = [input_hash_or_missing(repo_root, INVENTORY_REL_PATH.as_posix())]
    groups: dict[str, dict[str, bool]] = {
        group_key(item): {role: False for role in REQUIRED_PERIOD_ROLES}
        for item in attempts
    }

    duplicate_attempt_id_count = _duplicate_count([str(item.get("attempt_id") or "") for item in attempts])
    duplicate_manifest_path_count = _duplicate_count([str(item.get("manifest_path") or "") for item in attempts])
    duplicate_target_identity_count = _duplicate_count([_target_identity(item) for item in attempts])
    receipt_projection_mismatch_count = 0
    receipt_binding_failure_count = 0
    status_prefix_completion_violations = 0
    expected_target_missing_count = 0
    stored_execution_projection_mismatch_count = 0

    for error in inventory_errors:
        _finding(findings, "target_inventory_error", message=error)
    for path in unexpected_paths:
        _finding(findings, "unexpected_target_attempt", path=path)
    for path in missing_inventory_paths:
        _finding(findings, "expected_target_missing", path=path)

    for entry in attempts:
        attempt_id = str(entry.get("attempt_id") or "")
        manifest_rel = str(entry.get("manifest_path") or "")
        terminal_rel = str(entry.get("expected_terminal_summary_path") or "")
        telemetry_rel = str(entry.get("expected_telemetry_summary_path") or "")
        receipt_rel = str(entry.get("expected_tester_report_receipt_path") or "")
        for rel_path in sorted([manifest_rel, terminal_rel, telemetry_rel, receipt_rel]):
            input_hashes.append(input_hash_or_missing(repo_root, rel_path))

        missing_inputs = [
            name
            for name, rel_path in {
                "attempt_manifest": manifest_rel,
                "terminal_run_summary": terminal_rel,
                "telemetry_summary": telemetry_rel,
                "tester_report_receipt": receipt_rel,
            }.items()
            if not rel_path or not path_exists(repo_root / rel_path)
        ]
        if missing_inputs:
            expected_target_missing_count += int("attempt_manifest" in missing_inputs)
            for item in missing_inputs:
                missing[f"missing_input:{item}"] += 1
            result = {
                "attempt_id": attempt_id,
                "status": "failed_missing_durable_input",
                "runtime_probe_complete": False,
                "period_role": str(entry.get("period_role") or ""),
                "runtime_surface_kind": str(entry.get("runtime_surface_kind") or ""),
                "missing_requirements": [f"missing_input:{item}" for item in missing_inputs],
                "stored_runtime_probe_complete": False,
                "receipt_binding_errors": [],
            }
            attempt_results.append(result)
            groups.setdefault(group_key(entry), {role: False for role in REQUIRED_PERIOD_ROLES})[
                str(entry.get("period_role") or "")
            ] = False
            _finding(findings, "missing_durable_runtime_input", attempt_id=attempt_id, missing=missing_inputs)
            continue

        manifest = load_yaml(repo_root / manifest_rel) or {}
        stored_status = str(manifest.get("status") or "")
        if stored_status.startswith("completed_"):
            status_prefix_completion_violations += 1
        receipt = load_receipt(repo_root / receipt_rel)
        binding_errors = validate_tester_report_receipt_binding(manifest, receipt, repo_root / receipt_rel)
        if binding_errors:
            receipt_binding_failure_count += 1
            receipt_projection_mismatch_count += sum(
                1 for item in binding_errors if item.startswith("manifest_receipt_")
            )
            _finding(findings, "receipt_binding_failure", attempt_id=attempt_id, errors=binding_errors)

        paths = RuntimeEvidencePaths(
            attempt_manifest=Path(manifest_rel),
            terminal_run_summary=Path(terminal_rel),
            telemetry_summary=Path(telemetry_rel),
            tester_report_receipt=Path(receipt_rel),
        )
        state = reconstruct_runtime_attempt(repo_root, paths)
        result = evaluate_runtime_attempt(
            state,
            required_period_roles=REQUIRED_PERIOD_ROLES,
            completion_eligible_surface_scopes=ELIGIBLE_COMPLETION_SCOPES,
        )
        receipt_completed = tester_report_completed(receipt)
        if state.tester_report_completed != receipt_completed:
            _finding(findings, "receipt_predicate_projection_mismatch", attempt_id=attempt_id)
        terminal_modes[state.terminal_mode or "unknown"] += 1
        for requirement in result.missing_requirements:
            missing[requirement] += 1
        stored_complete = bool((manifest.get("execution_state") or {}).get("runtime_probe_complete"))
        if stored_complete != result.runtime_probe_complete:
            _finding(
                findings,
                "stored_completion_projection_mismatch",
                attempt_id=attempt_id,
                stored_runtime_probe_complete=stored_complete,
                reconstructed_runtime_probe_complete=result.runtime_probe_complete,
            )
        if stored_status.startswith("runtime_probe_completed") and not result.runtime_probe_complete:
            status_prefix_completion_violations += 1
        if receipt.get("source_report_sha256") and not receipt_completed:
            _finding(
                findings,
                "tester_report_receipt_incomplete",
                attempt_id=attempt_id,
                missing_requirements=receipt.get("missing_requirements") or [],
            )
        execution_state = manifest.get("execution_state") or {}
        stored_projection = {
            "terminal_launched": bool(execution_state.get("terminal_launched")),
            "telemetry_file_observed": bool(execution_state.get("telemetry_file_observed")),
            "telemetry_rows_observed": bool(execution_state.get("telemetry_rows_observed")),
            "tester_report_observed": bool(execution_state.get("tester_report_observed")),
            "tester_report_completed": bool(execution_state.get("tester_report_completed")),
            "terminal_mode": str(execution_state.get("terminal_mode") or ""),
            "runtime_probe_complete": stored_complete,
            "missing_requirements": tuple(str(item) for item in execution_state.get("missing_requirements", [])),
        }
        reconstructed_projection = {
            "terminal_launched": state.terminal_launched,
            "telemetry_file_observed": state.telemetry_file_observed,
            "telemetry_rows_observed": state.telemetry_rows_observed,
            "tester_report_observed": state.tester_report_observed,
            "tester_report_completed": state.tester_report_completed,
            "terminal_mode": state.terminal_mode,
            "runtime_probe_complete": result.runtime_probe_complete,
            "missing_requirements": tuple(str(item) for item in result.missing_requirements),
        }
        mismatched_projection_fields = [
            field
            for field, value in stored_projection.items()
            if value != reconstructed_projection[field]
        ]
        if mismatched_projection_fields:
            stored_execution_projection_mismatch_count += 1
            _finding(
                findings,
                "stored_execution_projection_mismatch",
                attempt_id=attempt_id,
                fields=mismatched_projection_fields,
            )
        attempt_result = {
            "attempt_id": attempt_id,
            "status": "passed" if result.runtime_probe_complete and not binding_errors else "failed",
            "runtime_probe_complete": result.runtime_probe_complete and not binding_errors,
            "period_role": state.period_role,
            "runtime_surface_kind": str(entry.get("runtime_surface_kind") or ""),
            "missing_requirements": list(result.missing_requirements),
            "stored_runtime_probe_complete": stored_complete,
            "receipt_binding_errors": binding_errors,
        }
        attempt_results.append(attempt_result)
        groups.setdefault(group_key(entry), {role: False for role in REQUIRED_PERIOD_ROLES})[state.period_role] = (
            result.runtime_probe_complete and not binding_errors
        )

    pair_group_results = []
    for key, roles in sorted(groups.items()):
        complete = all(roles.get(role) for role in REQUIRED_PERIOD_ROLES)
        pair_group_results.append(
            {
                "group_key": key,
                "roles": {role: bool(roles.get(role)) for role in REQUIRED_PERIOD_ROLES},
                "complete": complete,
            }
        )
        if not complete:
            missing["pair_group_incomplete"] += 1

    complete_count = sum(1 for item in attempt_results if item["runtime_probe_complete"])
    incomplete_count = len(attempt_results) - complete_count
    pair_complete = sum(1 for item in pair_group_results if item["complete"])
    pair_incomplete = len(pair_group_results) - pair_complete
    violation_counts = {
        "expected_target_missing": expected_target_missing_count + len(missing_inventory_paths),
        "unexpected_target_present": len(unexpected_paths),
        "duplicate_target_identity": duplicate_target_identity_count,
        "duplicate_attempt_id": duplicate_attempt_id_count,
        "duplicate_manifest_path": duplicate_manifest_path_count,
        "receipt_projection_mismatch": receipt_projection_mismatch_count,
        "receipt_to_attempt_binding_failure": receipt_binding_failure_count,
        "stored_execution_projection_mismatch": stored_execution_projection_mismatch_count,
        "status_prefix_completion_violations": status_prefix_completion_violations,
        "incomplete_attempt": incomplete_count,
        "incomplete_pair_group": pair_incomplete,
        "inventory_error": len(inventory_errors),
    }
    status = "passed" if all(value == 0 for value in violation_counts.values()) and len(attempts) == EXPECTED_ATTEMPT_COUNT and len(pair_group_results) == EXPECTED_PAIR_GROUP_COUNT else "failed"
    if incomplete_count:
        _finding(findings, "runtime_contract_incomplete_attempts", count=incomplete_count)
    if pair_incomplete:
        _finding(findings, "runtime_pair_groups_incomplete", count=pair_incomplete)
    for key, value in violation_counts.items():
        if value:
            _finding(findings, key, count=value)

    claim_effect = (
        "runtime_contract_integrity_passed_no_runtime_authority_no_economics_pass"
        if status == "passed"
        else "runtime_contract_integrity_failed_no_runtime_authority_no_economics_pass"
    )
    result = {
        "version": "evaluator_result_v1",
        "evaluator_id": EVALUATOR_ID,
        "executed_at_utc": evaluation_time_utc(),
        "input_hashes": sorted(input_hashes, key=lambda item: str(item.get("path") or "")),
        "implementation_hashes": implementation_hashes(
            repo_root,
            (
                "foundation/evaluation/runtime_contract_evaluator.py",
                "foundation/mt5/runtime_completion.py",
                "foundation/mt5/tester_report_receipt.py",
                "foundation/migrations/runtime_graph_target_inventory.py",
            ),
        ),
        "status": status,
        "metrics": {
            "expected_attempt_count": EXPECTED_ATTEMPT_COUNT,
            "attempt_count": len(attempt_results),
            "runtime_probe_complete_count": complete_count,
            "runtime_probe_incomplete_count": incomplete_count,
            "expected_pair_group_count": EXPECTED_PAIR_GROUP_COUNT,
            "pair_group_count": len(pair_group_results),
            "pair_groups_complete": pair_complete,
            "pair_groups_incomplete": pair_incomplete,
            "expected_surface_kind_counts": dict(EXPECTED_SURFACE_KIND_COUNTS),
            "terminal_mode_counts": dict(sorted(terminal_modes.items())),
            "runtime_surface_kind_counts": dict(sorted(surface_kinds.items())),
            "missing_requirements_by_count": dict(sorted(missing.items())),
            **violation_counts,
        },
        "pair_group_results": pair_group_results,
        "attempt_results": sorted(attempt_results, key=lambda item: str(item.get("attempt_id") or "")),
        "findings": sorted(findings, key=lambda item: (str(item.get("id") or ""), str(item.get("attempt_id") or ""), str(item.get("path") or ""), str(item.get("message") or ""))),
        "claim_effect": claim_effect,
    }
    return finalize_result(result)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    result = evaluate_runtime_contract(repo_root)
    if args.output:
        write_yaml(Path(args.output), result)
    else:
        print(result)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
