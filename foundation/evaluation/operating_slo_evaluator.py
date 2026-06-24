from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation.evaluation.agent_value_evaluator import evaluate_agent_value
from foundation.evaluation.common import evaluation_time_utc, finalize_result, input_hash, load_yaml, write_yaml
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


def _transaction_metrics(repo_root: Path) -> dict[str, int | float | None]:
    receipts = [
        *(repo_root / "lab" / "executions").glob("**/transaction_receipt.yaml"),
        *(repo_root / ".spacesonar" / "transactions").glob("*/transaction_receipt.yaml"),
    ]
    aborted_partial = 0
    unclassified = 0
    for receipt in receipts:
        data = load_yaml(receipt) or {}
        status = str(data.get("status") or "")
        if status.startswith("aborted") and data.get("committed_output_hashes"):
            aborted_partial += 1
        if not status:
            unclassified += 1
    idempotency_score = 1.0 if receipts and not aborted_partial and not unclassified else None
    return {
        "transaction_receipt_count": len(receipts),
        "transaction_idempotency_score": idempotency_score,
        "partial_unclassified_transactions": aborted_partial + unclassified,
    }


def _batch_receipt_metrics(repo_root: Path) -> dict[str, int]:
    dirty_without_complete_snapshot = 0
    for receipt_path in (repo_root / "lab" / "executions").glob("**/execution_batch_receipt.yaml"):
        receipt = load_yaml(receipt_path) or {}
        git = receipt.get("git") or {}
        snapshot = git.get("source_snapshot") or {}
        source_dirty = bool(git.get("source_dirty"))
        if source_dirty and not (snapshot.get("manifest_path") and snapshot.get("manifest_sha256")):
            dirty_without_complete_snapshot += 1
    return {"durable_runs_with_dirty_source": dirty_without_complete_snapshot}


def _closeout_metrics(repo_root: Path) -> dict[str, int]:
    self_attested = 0
    for closeout_path in (repo_root / "lab" / "waves").glob("**/wave_closeout.yaml"):
        closeout = load_yaml(closeout_path) or {}
        for item in closeout.get("requirement_audit") or []:
            if item.get("status") == "passed" and not item.get("evaluator_id"):
                self_attested += 1
    return {"self_attested_closeout_requirements": self_attested}


def _runtime_violation_count(runtime_metrics: dict[str, Any]) -> int:
    keys = [
        "expected_target_missing",
        "unexpected_target_present",
        "duplicate_target_identity",
        "duplicate_attempt_id",
        "duplicate_manifest_path",
        "receipt_projection_mismatch",
        "receipt_to_attempt_binding_failure",
        "stored_execution_projection_mismatch",
        "status_prefix_completion_violations",
        "incomplete_attempt",
        "incomplete_pair_group",
        "inventory_error",
    ]
    return sum(int(runtime_metrics.get(key) or 0) for key in keys)


def _require_metric(findings: list[dict[str, Any]], metrics: dict[str, Any], metric: str) -> bool:
    if metric not in metrics or metrics.get(metric) is None:
        findings.append({"id": "required_slo_metric_unavailable", "metric": metric})
        return False
    return True


def _gate_value(gates: dict[str, Any], name: str) -> Any:
    return gates[name] if name in gates else None


def evaluate_operating_slo(repo_root: Path) -> dict:
    slo_path = "docs/policies/codex_operating_slo.yaml"
    slo = load_yaml(repo_root / slo_path) or {}
    gates = slo.get("gates") or {}
    routing = evaluate_routing_quality(repo_root)
    runtime = evaluate_runtime_contract(repo_root)
    agents = evaluate_agent_value(repo_root)
    cold = _cold_reentry_metrics(repo_root, int(gates.get("cold_reentry_truth_files_max", 4)))
    transactions = _transaction_metrics(repo_root)
    batches = _batch_receipt_metrics(repo_root)
    closeouts = _closeout_metrics(repo_root)
    hygiene_errors = validate_repository_hygiene(repo_root)
    policy_lint = subprocess.run(
        [sys.executable, "foundation/validation/policy_duplicate_lint.py", "--repo-root", "."],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )

    metrics = {
        **cold,
        **transactions,
        **batches,
        **closeouts,
        "routing_golden_accuracy": routing["metrics"].get("accuracy"),
        "protected_claim_guard_recall": routing["metrics"].get("protected_claim_guard_recall"),
        "runtime_completion_contract_violations": _runtime_violation_count(runtime["metrics"]),
        "runtime_contract_integrity": runtime["status"],
        "routine_solo_or_single_agent_share": agents["metrics"].get("routine_solo_or_single_agent_share"),
        "solo_work_share": agents["metrics"].get("solo_work_share"),
        "observation_coverage_ratio": agents["metrics"].get("observation_coverage_ratio"),
        "duplicate_agent_advice_ratio": agents["metrics"].get("duplicate_advice_ratio"),
        "tracked_ignored_artifact_count": 0 if not hygiene_errors else len(hygiene_errors),
    }

    findings: list[dict[str, Any]] = []
    required_metrics = [
        "cold_reentry_truth_files",
        "cold_reentry_context_bytes",
        "routing_golden_accuracy",
        "protected_claim_guard_recall",
        "transaction_idempotency_score",
        "partial_unclassified_transactions",
        "durable_runs_with_dirty_source",
        "runtime_completion_contract_violations",
        "self_attested_closeout_requirements",
        "routine_solo_or_single_agent_share",
        "duplicate_agent_advice_ratio",
    ]
    available = {metric: _require_metric(findings, metrics, metric) for metric in required_metrics}

    if available["cold_reentry_truth_files"] and metrics["cold_reentry_truth_files"] > int(gates.get("cold_reentry_truth_files_max", 4)):
        findings.append({"id": "cold_reentry_file_count_exceeded", **cold})
    if available["cold_reentry_context_bytes"] and metrics["cold_reentry_context_bytes"] > int(gates.get("cold_reentry_context_bytes_max", 50000)):
        findings.append({"id": "cold_reentry_context_bytes_exceeded", **cold})
    if available["routing_golden_accuracy"] and metrics["routing_golden_accuracy"] < float(gates.get("routing_golden_accuracy_min", 0.95)):
        findings.append({"id": "routing_accuracy_below_slo", "value": metrics["routing_golden_accuracy"]})
    if available["protected_claim_guard_recall"] and metrics["protected_claim_guard_recall"] < float(gates.get("protected_claim_guard_recall_min", 1.0)):
        findings.append({"id": "protected_claim_recall_below_slo", "value": metrics["protected_claim_guard_recall"]})
    if available["transaction_idempotency_score"] and metrics["transaction_idempotency_score"] < float(gates.get("transaction_idempotency_required", 1.0)):
        findings.append({"id": "transaction_idempotency_below_slo", "value": metrics["transaction_idempotency_score"]})
    if available["partial_unclassified_transactions"] and metrics["partial_unclassified_transactions"] > int(gates.get("partial_unclassified_transactions_max", 0)):
        findings.append({"id": "partial_unclassified_transactions", **transactions})
    if available["durable_runs_with_dirty_source"] and metrics["durable_runs_with_dirty_source"] > int(gates.get("durable_runs_with_dirty_source_max", 0)):
        findings.append({"id": "durable_dirty_source_run", "count": metrics["durable_runs_with_dirty_source"]})
    if available["runtime_completion_contract_violations"] and metrics["runtime_completion_contract_violations"] > int(gates.get("runtime_completion_contract_violations_max", 0)):
        findings.append({"id": "runtime_completion_contract_violations", "count": metrics["runtime_completion_contract_violations"]})
    if available["self_attested_closeout_requirements"] and metrics["self_attested_closeout_requirements"] > int(gates.get("self_attested_closeout_requirements_max", 0)):
        findings.append({"id": "self_attested_closeout_requirements", "count": metrics["self_attested_closeout_requirements"]})
    if available["routine_solo_or_single_agent_share"] and metrics["routine_solo_or_single_agent_share"] < float(gates.get("routine_solo_or_single_agent_share_min", 0.80)):
        findings.append({"id": "routine_solo_or_single_agent_share_below_slo", "value": metrics["routine_solo_or_single_agent_share"]})
    if available["duplicate_agent_advice_ratio"] and metrics["duplicate_agent_advice_ratio"] > float(gates.get("duplicate_agent_advice_ratio_max", 0.20)):
        findings.append({"id": "duplicate_agent_advice_ratio_above_slo", "value": metrics["duplicate_agent_advice_ratio"]})
    if hygiene_errors:
        findings.extend({"id": "repository_hygiene_error", "detail": error} for error in hygiene_errors)
    if policy_lint.returncode != 0:
        findings.append({"id": "policy_duplicate_lint_failed", "detail": policy_lint.stdout + policy_lint.stderr})
    if agents["status"] != "passed":
        findings.append({"id": "agent_value_slo_failed", "details": agents["findings"]})
    result = {
        "version": "evaluator_result_v1",
        "evaluator_id": EVALUATOR_ID,
        "executed_at_utc": evaluation_time_utc(),
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
