from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation.evaluation.agent_value_evaluator import evaluate_agent_value
from foundation.evaluation.common import evaluation_time_utc, finalize_result, implementation_hashes, input_hash, load_yaml, write_yaml
from foundation.evaluation.routing_quality_evaluator import evaluate_routing_quality
from foundation.evaluation.runtime_contract_evaluator import evaluate_runtime_contract
from foundation.validation.repository_hygiene_validator import validate as validate_repository_hygiene
from spacesonar.control_plane.models import ExecutionContext
from spacesonar.control_plane.transaction import ControlPlaneTransaction


EVALUATOR_ID = "operating_slo_evaluator_v1"
TRUTH_FILES = (
    "AGENTS.md",
    "docs/workspace/workspace_state.yaml",
    "docs/agent_control/work_family_registry.yaml",
    "docs/agent_control/policy_contract.yaml",
)
EXPECTED_GATE_TYPES = {
    "cold_reentry_truth_files_max": int,
    "cold_reentry_context_bytes_max": int,
    "routing_golden_accuracy_min": (int, float),
    "protected_claim_guard_recall_min": (int, float),
    "transaction_idempotency_required": (int, float),
    "partial_unclassified_transactions_max": int,
    "durable_runs_with_unbounded_dirty_source_max": int,
    "runtime_completion_contract_violations_max": int,
    "self_attested_closeout_requirements_max": int,
    "routine_solo_or_single_agent_share_min": (int, float),
    "duplicate_agent_advice_ratio_max": (int, float),
    "agent_observation_coverage_ratio_min": (int, float),
}


def _cold_reentry_metrics(repo_root: Path) -> dict[str, int]:
    files = list(TRUTH_FILES)
    total_bytes = sum((repo_root / path).stat().st_size for path in files)
    return {"cold_reentry_truth_files": len(files), "cold_reentry_context_bytes": total_bytes}


def _transaction_metrics(repo_root: Path) -> dict[str, int | float | None]:
    receipts = list((repo_root / "lab" / "executions").glob("**/transaction_receipt.yaml"))
    aborted_partial = 0
    unclassified = 0
    for receipt in receipts:
        data = load_yaml(receipt) or {}
        status = str(data.get("status") or "")
        if status.startswith("aborted") and data.get("committed_output_hashes"):
            aborted_partial += 1
        if not status or status == "rollback_failed":
            unclassified += 1
    probe = _idempotency_probe()
    return {
        "durable_transaction_receipt_count": len(receipts),
        "transaction_idempotency_probe_count": probe["probe_count"],
        "transaction_idempotency_pass_count": probe["pass_count"],
        "transaction_idempotency_score": probe["score"],
        "partial_unclassified_transactions": aborted_partial + unclassified,
    }


def _idempotency_probe() -> dict[str, int | float | None]:
    with tempfile.TemporaryDirectory(prefix="spacesonar_tx_probe_") as tmp:
        root = Path(tmp)
        context = ExecutionContext(
            repo_root=root,
            work_item_id="work_wp07_transaction_idempotency_probe",
            claim_boundary="local_probe_only_no_runtime_authority_no_economics_pass",
            command_argv=("wp07-idempotency-probe",),
            validation_commands=("noop_probe",),
        )
        first = ControlPlaneTransaction(context)
        first.stage_text("probe/control.txt", "stable\n")
        first_result = first.commit(validate=lambda future_root: [])
        before = (root / "probe" / "control.txt").read_bytes()
        second = ControlPlaneTransaction(context)
        second.stage_text("probe/control.txt", "stable\n")
        second_result = second.commit(validate=lambda future_root: [])
        after = (root / "probe" / "control.txt").read_bytes()
    passed = (
        first_result.status in {"committed", "noop_already_applied"}
        and second_result.status == "noop_already_applied"
        and before == after
    )
    return {"probe_count": 1, "pass_count": 1 if passed else 0, "score": 1.0 if passed else 0.0}


def _batch_receipt_metrics(repo_root: Path) -> dict[str, int]:
    unbounded_dirty_source = 0
    for receipt_path in (repo_root / "lab" / "executions").glob("**/execution_batch_receipt.yaml"):
        receipt = load_yaml(receipt_path) or {}
        git = receipt.get("git") or {}
        snapshot = git.get("source_snapshot") or {}
        source_dirty = bool(git.get("source_dirty"))
        if source_dirty and not (snapshot.get("manifest_path") and snapshot.get("manifest_sha256")):
            unbounded_dirty_source += 1
    return {"durable_runs_with_unbounded_dirty_source": unbounded_dirty_source}


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


def _validate_gate_schema(gates: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    observed = set(gates)
    expected = set(EXPECTED_GATE_TYPES)
    for gate in sorted(expected - observed):
        findings.append({"id": "required_slo_gate_unavailable", "gate": gate})
    for gate in sorted(observed - expected):
        findings.append({"id": "unknown_slo_gate", "gate": gate})
    for gate, expected_type in EXPECTED_GATE_TYPES.items():
        if gate not in gates:
            continue
        value = gates[gate]
        if isinstance(value, bool) or not isinstance(value, expected_type):
            findings.append({"id": "invalid_slo_gate_type", "gate": gate, "value": value})
    return findings


def evaluate_operating_slo(repo_root: Path) -> dict:
    slo_path = "docs/policies/codex_operating_slo.yaml"
    slo = load_yaml(repo_root / slo_path) or {}
    gates = slo.get("gates") or {}
    gate_findings = _validate_gate_schema(gates)
    routing = evaluate_routing_quality(repo_root)
    runtime = evaluate_runtime_contract(repo_root)
    agents = evaluate_agent_value(repo_root)
    cold = _cold_reentry_metrics(repo_root)
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

    findings: list[dict[str, Any]] = list(gate_findings)
    required_metrics = [
        "cold_reentry_truth_files",
        "cold_reentry_context_bytes",
        "routing_golden_accuracy",
        "protected_claim_guard_recall",
        "transaction_idempotency_probe_count",
        "transaction_idempotency_pass_count",
        "transaction_idempotency_score",
        "partial_unclassified_transactions",
        "durable_runs_with_unbounded_dirty_source",
        "runtime_completion_contract_violations",
        "self_attested_closeout_requirements",
        "routine_solo_or_single_agent_share",
        "duplicate_agent_advice_ratio",
    ]
    available = {metric: _require_metric(findings, metrics, metric) for metric in required_metrics}

    if available["cold_reentry_truth_files"] and "cold_reentry_truth_files_max" in gates and metrics["cold_reentry_truth_files"] > int(gates["cold_reentry_truth_files_max"]):
        findings.append({"id": "cold_reentry_file_count_exceeded", **cold})
    if available["cold_reentry_context_bytes"] and "cold_reentry_context_bytes_max" in gates and metrics["cold_reentry_context_bytes"] > int(gates["cold_reentry_context_bytes_max"]):
        findings.append({"id": "cold_reentry_context_bytes_exceeded", **cold})
    if available["routing_golden_accuracy"] and "routing_golden_accuracy_min" in gates and metrics["routing_golden_accuracy"] < float(gates["routing_golden_accuracy_min"]):
        findings.append({"id": "routing_accuracy_below_slo", "value": metrics["routing_golden_accuracy"]})
    if available["protected_claim_guard_recall"] and "protected_claim_guard_recall_min" in gates and metrics["protected_claim_guard_recall"] < float(gates["protected_claim_guard_recall_min"]):
        findings.append({"id": "protected_claim_recall_below_slo", "value": metrics["protected_claim_guard_recall"]})
    if available["transaction_idempotency_probe_count"] and metrics["transaction_idempotency_probe_count"] <= 0:
        findings.append({"id": "transaction_idempotency_probe_missing"})
    if available["transaction_idempotency_score"] and "transaction_idempotency_required" in gates and metrics["transaction_idempotency_score"] < float(gates["transaction_idempotency_required"]):
        findings.append({"id": "transaction_idempotency_below_slo", "value": metrics["transaction_idempotency_score"]})
    if available["partial_unclassified_transactions"] and "partial_unclassified_transactions_max" in gates and metrics["partial_unclassified_transactions"] > int(gates["partial_unclassified_transactions_max"]):
        findings.append({"id": "partial_unclassified_transactions", **transactions})
    if available["durable_runs_with_unbounded_dirty_source"] and "durable_runs_with_unbounded_dirty_source_max" in gates and metrics["durable_runs_with_unbounded_dirty_source"] > int(gates["durable_runs_with_unbounded_dirty_source_max"]):
        findings.append({"id": "durable_unbounded_dirty_source_run", "count": metrics["durable_runs_with_unbounded_dirty_source"]})
    if available["runtime_completion_contract_violations"] and "runtime_completion_contract_violations_max" in gates and metrics["runtime_completion_contract_violations"] > int(gates["runtime_completion_contract_violations_max"]):
        findings.append({"id": "runtime_completion_contract_violations", "count": metrics["runtime_completion_contract_violations"]})
    if available["self_attested_closeout_requirements"] and "self_attested_closeout_requirements_max" in gates and metrics["self_attested_closeout_requirements"] > int(gates["self_attested_closeout_requirements_max"]):
        findings.append({"id": "self_attested_closeout_requirements", "count": metrics["self_attested_closeout_requirements"]})
    if available["routine_solo_or_single_agent_share"] and "routine_solo_or_single_agent_share_min" in gates and metrics["routine_solo_or_single_agent_share"] < float(gates["routine_solo_or_single_agent_share_min"]):
        findings.append({"id": "routine_solo_or_single_agent_share_below_slo", "value": metrics["routine_solo_or_single_agent_share"]})
    if available["duplicate_agent_advice_ratio"] and "duplicate_agent_advice_ratio_max" in gates and metrics["duplicate_agent_advice_ratio"] > float(gates["duplicate_agent_advice_ratio_max"]):
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
            input_hash(repo_root, "docs/agent_control/work_family_registry.yaml"),
        ],
        "implementation_hashes": implementation_hashes(
            repo_root,
            (
                "foundation/evaluation/operating_slo_evaluator.py",
                "foundation/evaluation/agent_value_evaluator.py",
                "foundation/evaluation/routing_quality_evaluator.py",
                "foundation/evaluation/runtime_contract_evaluator.py",
                "src/spacesonar/control_plane/transaction.py",
            ),
        ),
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
