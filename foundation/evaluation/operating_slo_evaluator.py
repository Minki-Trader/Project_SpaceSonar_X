from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation.evaluation.agent_value_evaluator import evaluate_agent_value
from foundation.evaluation.common import EVALUATION_TIME_UTC, finalize_result, input_hash, load_yaml, write_yaml
from foundation.evaluation.routing_quality_evaluator import evaluate_routing_quality
from foundation.evaluation.runtime_contract_evaluator import evaluate_runtime_contract
from foundation.validation.repository_hygiene_validator import validate as validate_repository_hygiene


EVALUATOR_ID = "operating_slo_evaluator_v1"


def _cold_reentry_metrics(repo_root: Path, max_files: int) -> dict[str, int]:
    files = [
        "AGENTS.md",
        "docs/workspace/workspace_state.yaml",
        "docs/agent_control/work_family_registry.yaml",
        "docs/agent_control/policy_contract.yaml",
    ][:max_files]
    total_bytes = sum((repo_root / path).stat().st_size for path in files)
    return {"cold_reentry_truth_files": len(files), "cold_reentry_context_bytes": total_bytes}


def _transaction_metrics(repo_root: Path) -> dict[str, int]:
    receipts = list((repo_root / ".spacesonar" / "transactions").glob("*/transaction_receipt.yaml"))
    aborted_partial = 0
    for receipt in receipts:
        data = load_yaml(receipt) or {}
        if data.get("status", "").startswith("aborted") and data.get("committed_output_hashes"):
            aborted_partial += 1
    return {"transaction_receipt_count": len(receipts), "partial_unclassified_transactions": aborted_partial}


def evaluate_operating_slo(repo_root: Path) -> dict:
    slo_path = "docs/policies/codex_operating_slo.yaml"
    slo = load_yaml(repo_root / slo_path) or {}
    gates = slo.get("gates") or {}
    routing = evaluate_routing_quality(repo_root)
    runtime = evaluate_runtime_contract(repo_root)
    agents = evaluate_agent_value(repo_root)
    cold = _cold_reentry_metrics(repo_root, int(gates.get("cold_reentry_truth_files_max", 4)))
    transactions = _transaction_metrics(repo_root)
    hygiene_errors = validate_repository_hygiene(repo_root)
    policy_lint = subprocess.run(
        [sys.executable, "foundation/validation/policy_duplicate_lint.py", "--repo-root", "."],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )

    findings = []
    if cold["cold_reentry_truth_files"] > int(gates.get("cold_reentry_truth_files_max", 4)):
        findings.append({"id": "cold_reentry_file_count_exceeded", **cold})
    if cold["cold_reentry_context_bytes"] > int(gates.get("cold_reentry_context_bytes_max", 50000)):
        findings.append({"id": "cold_reentry_context_bytes_exceeded", **cold})
    if routing["metrics"]["accuracy"] < float(gates.get("routing_golden_accuracy_min", 0.95)):
        findings.append({"id": "routing_accuracy_below_slo", "value": routing["metrics"]["accuracy"]})
    if routing["metrics"]["protected_claim_guard_recall"] < float(gates.get("protected_claim_guard_recall_min", 1.0)):
        findings.append({"id": "protected_claim_recall_below_slo", "value": routing["metrics"]["protected_claim_guard_recall"]})
    if transactions["partial_unclassified_transactions"] > int(gates.get("partial_unclassified_transactions_max", 0)):
        findings.append({"id": "partial_unclassified_transactions", **transactions})
    if hygiene_errors:
        findings.extend({"id": "repository_hygiene_error", "detail": error} for error in hygiene_errors)
    if policy_lint.returncode != 0:
        findings.append({"id": "policy_duplicate_lint_failed", "detail": policy_lint.stdout + policy_lint.stderr})
    if agents["status"] != "passed":
        findings.append({"id": "agent_value_slo_failed", "details": agents["findings"]})

    metrics = {
        **cold,
        **transactions,
        "routing_golden_accuracy": routing["metrics"]["accuracy"],
        "protected_claim_guard_recall": routing["metrics"]["protected_claim_guard_recall"],
        "runtime_completion_contract_violations": runtime["metrics"]["status_prefix_completion_violations"],
        "runtime_contract_integrity": runtime["status"],
        "solo_work_share": agents["metrics"].get("solo_work_share"),
        "duplicate_agent_advice_ratio": agents["metrics"].get("duplicate_advice_ratio"),
        "tracked_ignored_artifact_count": 0 if not hygiene_errors else len(hygiene_errors),
    }
    result = {
        "version": "evaluator_result_v1",
        "evaluator_id": EVALUATOR_ID,
        "executed_at_utc": EVALUATION_TIME_UTC,
        "input_hashes": [
            input_hash(repo_root, slo_path),
            input_hash(repo_root, "AGENTS.md"),
            input_hash(repo_root, "docs/workspace/workspace_state.yaml"),
            input_hash(repo_root, "docs/agent_control/policy_contract.yaml"),
        ],
        "status": "failed" if findings else "passed",
        "metrics": metrics,
        "findings": findings,
        "claim_effect": "operating_slo_evaluated_no_runtime_authority_no_economics_pass",
    }
    return finalize_result(result)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = evaluate_operating_slo(Path(args.repo_root).resolve())
    if args.output:
        write_yaml(Path(args.output), result)
    else:
        print(result)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
