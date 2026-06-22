from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation.evaluation.common import EVALUATION_TIME_UTC, finalize_result, input_hash, load_yaml, write_yaml


EVALUATOR_ID = "runtime_contract_evaluator_v2"


def _attempt_records(repo_root: Path) -> list[tuple[str, dict[str, Any]]]:
    records: list[tuple[str, dict[str, Any]]] = []
    for path in sorted((repo_root / "runtime" / "mt5_attempts").glob("*/attempt_manifest.yaml")):
        data = load_yaml(path) or {}
        if data.get("execution_state") is None:
            continue
        rel_path = path.relative_to(repo_root).as_posix()
        records.append((rel_path, data))
    return records


def evaluate_runtime_contract(repo_root: Path) -> dict[str, Any]:
    records = _attempt_records(repo_root)
    missing = Counter()
    terminal_modes = Counter()
    status_prefix_violations = 0
    complete_count = 0
    tester_report_count = 0
    telemetry_count = 0
    for _, data in records:
        state = data.get("execution_state") or {}
        status = str(data.get("status", ""))
        complete = bool(state.get("runtime_probe_complete"))
        complete_count += int(complete)
        tester_report_count += int(bool(state.get("tester_report_observed")))
        telemetry_count += int(bool(state.get("telemetry_rows_observed")))
        terminal_modes[str(state.get("terminal_mode", "unknown"))] += 1
        if status.startswith("completed_") and not complete:
            status_prefix_violations += 1
        for requirement in state.get("missing_requirements") or []:
            missing[str(requirement)] += 1

    incomplete_count = len(records) - complete_count
    findings = []
    if incomplete_count:
        findings.append({"id": "runtime_contract_incomplete_attempts", "count": incomplete_count})
    if missing.get("tester_report_observed"):
        findings.append({"id": "missing_tester_reports", "count": missing["tester_report_observed"]})
    if terminal_modes.get("main_mode_config_fallback"):
        findings.append({"id": "main_mode_fallback_observations", "count": terminal_modes["main_mode_config_fallback"]})
    if status_prefix_violations:
        findings.append({"id": "status_prefix_completion_violations", "count": status_prefix_violations})

    status = "failed" if incomplete_count else "passed"
    claim_effect = (
        "runtime_contract_integrity_passed_no_runtime_authority_no_economics_pass"
        if status == "passed"
        else "runtime_contract_integrity_failed_no_runtime_authority_no_economics_pass"
    )
    result = {
        "version": "evaluator_result_v1",
        "evaluator_id": EVALUATOR_ID,
        "executed_at_utc": EVALUATION_TIME_UTC,
        "input_hashes": [input_hash(repo_root, rel_path) for rel_path, _ in records],
        "status": status,
        "metrics": {
            "attempt_count": len(records),
            "telemetry_observation_count": telemetry_count,
            "tester_report_observation_count": tester_report_count,
            "runtime_probe_complete_count": complete_count,
            "runtime_probe_incomplete_count": incomplete_count,
            "terminal_mode_counts": dict(sorted(terminal_modes.items())),
            "missing_requirements_by_count": dict(sorted(missing.items())),
            "status_prefix_completion_violations": status_prefix_violations,
        },
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
