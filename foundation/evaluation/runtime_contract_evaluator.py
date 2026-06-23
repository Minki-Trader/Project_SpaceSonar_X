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

from foundation.evaluation.common import EVALUATION_TIME_UTC, file_sha256, finalize_result, load_yaml, write_yaml
from foundation.migrations.materialize_runtime_report_receipts_v1 import (
    ELIGIBLE_COMPLETION_SCOPES,
    REQUIRED_PERIOD_ROLES,
    runtime_surface_kind,
    target_attempt_paths,
    telemetry_summary_path,
)
from foundation.mt5.runtime_completion import RuntimeEvidencePaths, evaluate_runtime_attempt, reconstruct_runtime_attempt
from foundation.mt5.tester_report_receipt import load_receipt, tester_report_completed
from spacesonar.control_plane.store import filesystem_path


EVALUATOR_ID = "runtime_contract_evaluator_v2"


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


def attempt_evidence_paths(repo_root: Path, attempt_path: Path) -> dict[str, str | None]:
    attempt_root = attempt_path.parent
    terminal = attempt_root / "terminal_run_summary.yaml"
    telemetry = telemetry_summary_path(attempt_root)
    receipt = attempt_root / "tester_report_receipt.yaml"
    return {
        "attempt_manifest": attempt_path.relative_to(repo_root).as_posix(),
        "terminal_run_summary": terminal.relative_to(repo_root).as_posix() if path_exists(terminal) else None,
        "telemetry_summary": telemetry.relative_to(repo_root).as_posix() if telemetry else None,
        "tester_report_receipt": receipt.relative_to(repo_root).as_posix() if path_exists(receipt) else None,
    }


def group_key(manifest: dict[str, Any], kind: str) -> str:
    return "|".join(
        [
            str(manifest.get("campaign_id") or ""),
            str(manifest.get("cell_id") or ""),
            kind,
        ]
    )


def evaluate_runtime_contract(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    attempt_paths = target_attempt_paths(repo_root)
    missing = Counter()
    terminal_modes = Counter()
    surface_kinds = Counter()
    findings: list[dict[str, Any]] = []
    attempt_results: list[dict[str, Any]] = []
    input_hashes: list[dict[str, Any]] = []
    groups: dict[str, dict[str, bool]] = {}
    status_prefix_completion_violations = 0

    for attempt_path in attempt_paths:
        manifest = load_yaml(attempt_path) or {}
        attempt_id = str(manifest.get("attempt_id") or attempt_path.parent.name)
        stored_status = str(manifest.get("status") or "")
        if stored_status.startswith("completed_"):
            status_prefix_completion_violations += 1
        telemetry_path = telemetry_summary_path(attempt_path.parent)
        kind = runtime_surface_kind(manifest, telemetry_path)
        surface_kinds[kind] += 1
        evidence = attempt_evidence_paths(repo_root, attempt_path)
        input_hashes.extend(input_hash_or_missing(repo_root, evidence[key]) for key in sorted(evidence))
        missing_inputs = [key for key, rel_path in evidence.items() if not rel_path or not path_exists(repo_root / rel_path)]
        if missing_inputs:
            for item in missing_inputs:
                missing[f"missing_input:{item}"] += 1
            result = {
                "attempt_id": attempt_id,
                "status": "failed_missing_durable_input",
                "runtime_probe_complete": False,
                "period_role": str((manifest.get("period_identity") or {}).get("period_role") or ""),
                "runtime_surface_kind": kind,
                "missing_requirements": [f"missing_input:{item}" for item in missing_inputs],
                "stored_runtime_probe_complete": bool((manifest.get("execution_state") or {}).get("runtime_probe_complete")),
            }
            findings.append({"id": "missing_durable_runtime_input", "attempt_id": attempt_id, "missing": missing_inputs})
            attempt_results.append(result)
            groups.setdefault(group_key(manifest, kind), {})[result["period_role"]] = False
            continue

        paths = RuntimeEvidencePaths(
            attempt_manifest=Path(evidence["attempt_manifest"]),
            terminal_run_summary=Path(evidence["terminal_run_summary"]),
            telemetry_summary=Path(evidence["telemetry_summary"]),
            tester_report_receipt=Path(evidence["tester_report_receipt"]),
        )
        state = reconstruct_runtime_attempt(repo_root, paths)
        result = evaluate_runtime_attempt(
            state,
            required_period_roles=REQUIRED_PERIOD_ROLES,
            completion_eligible_surface_scopes=ELIGIBLE_COMPLETION_SCOPES,
        )
        receipt = load_receipt(repo_root / evidence["tester_report_receipt"])
        receipt_completed = tester_report_completed(receipt)
        terminal_modes[state.terminal_mode or "unknown"] += 1
        for requirement in result.missing_requirements:
            missing[requirement] += 1
        stored_complete = bool((manifest.get("execution_state") or {}).get("runtime_probe_complete"))
        if stored_complete != result.runtime_probe_complete:
            findings.append(
                {
                    "id": "stored_completion_projection_mismatch",
                    "attempt_id": attempt_id,
                    "stored_runtime_probe_complete": stored_complete,
                    "reconstructed_runtime_probe_complete": result.runtime_probe_complete,
                }
            )
        if stored_status.startswith("runtime_probe_completed") and not result.runtime_probe_complete:
            status_prefix_completion_violations += 1
        if receipt.get("source_report_sha256") and not receipt_completed:
            findings.append(
                {
                    "id": "tester_report_receipt_incomplete",
                    "attempt_id": attempt_id,
                    "missing_requirements": receipt.get("missing_requirements") or [],
                }
            )
        attempt_result = {
            "attempt_id": attempt_id,
            "status": "passed" if result.runtime_probe_complete else "failed",
            "runtime_probe_complete": result.runtime_probe_complete,
            "period_role": state.period_role,
            "runtime_surface_kind": kind,
            "missing_requirements": list(result.missing_requirements),
            "stored_runtime_probe_complete": stored_complete,
        }
        attempt_results.append(attempt_result)
        group_roles = groups.setdefault(group_key(manifest, kind), {})
        group_roles[state.period_role] = group_roles.get(state.period_role, False) or result.runtime_probe_complete

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
    status = "passed" if attempt_results and incomplete_count == 0 and pair_incomplete == 0 else "failed"
    if incomplete_count:
        findings.append({"id": "runtime_contract_incomplete_attempts", "count": incomplete_count})
    if pair_incomplete:
        findings.append({"id": "runtime_pair_groups_incomplete", "count": pair_incomplete})

    claim_effect = (
        "runtime_contract_integrity_passed_no_runtime_authority_no_economics_pass"
        if status == "passed"
        else "runtime_contract_integrity_failed_no_runtime_authority_no_economics_pass"
    )
    result = {
        "version": "evaluator_result_v1",
        "evaluator_id": EVALUATOR_ID,
        "executed_at_utc": EVALUATION_TIME_UTC,
        "input_hashes": input_hashes,
        "status": status,
        "metrics": {
            "attempt_count": len(attempt_results),
            "runtime_probe_complete_count": complete_count,
            "runtime_probe_incomplete_count": incomplete_count,
            "pair_groups_complete": pair_complete,
            "pair_groups_incomplete": pair_incomplete,
            "terminal_mode_counts": dict(sorted(terminal_modes.items())),
            "runtime_surface_kind_counts": dict(sorted(surface_kinds.items())),
            "missing_requirements_by_count": dict(sorted(missing.items())),
            "status_prefix_completion_violations": status_prefix_completion_violations,
        },
        "pair_group_results": pair_group_results,
        "attempt_results": attempt_results,
        "findings": findings,
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
