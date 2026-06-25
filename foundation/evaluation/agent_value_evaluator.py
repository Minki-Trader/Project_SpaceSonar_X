from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation.evaluation.common import evaluation_time_utc, finalize_result, implementation_hashes, input_hash, load_yaml, write_yaml


EVALUATOR_ID = "agent_value_evaluator_v1"


def evaluate_agent_value(repo_root: Path) -> dict:
    metrics_path = "docs/workspace/agent_operating_metrics.yaml"
    data = load_yaml(repo_root / metrics_path) or {}
    metrics = data.get("agent_operating_metrics") or {}
    slo = load_yaml(repo_root / "docs/policies/codex_operating_slo.yaml") or {}
    gates = slo.get("gates") or {}
    findings = []
    required_metrics = (
        "observation_window_id",
        "observation_window_status",
        "work_item_count",
        "observed_work_item_count",
        "observed_distinct_work_family_count",
        "observation_coverage_ratio",
        "routine_solo_or_single_agent_share",
        "duplicate_advice_ratio",
        "unsupported_assertion_count",
        "receipt_validation_failure_count",
    )
    for metric in required_metrics:
        if metric not in metrics or metrics.get(metric) is None:
            findings.append({"id": "required_agent_metric_unavailable", "metric": metric})
    if "routine_solo_or_single_agent_share" in metrics and float(metrics.get("routine_solo_or_single_agent_share", 0.0)) < 0.80:
        findings.append({"id": "routine_solo_or_single_agent_share_below_slo", "value": metrics.get("routine_solo_or_single_agent_share")})
    if "duplicate_advice_ratio" in metrics and float(metrics.get("duplicate_advice_ratio", 1.0)) > 0.20:
        findings.append({"id": "duplicate_advice_ratio_above_slo", "value": metrics.get("duplicate_advice_ratio")})
    if "unsupported_assertion_count" in metrics and int(metrics.get("unsupported_assertion_count", 0)) > 0:
        findings.append({"id": "unsupported_agent_assertions", "count": metrics.get("unsupported_assertion_count")})
    coverage_min = gates.get("agent_observation_coverage_ratio_min")
    if coverage_min is None:
        findings.append({"id": "required_agent_slo_gate_unavailable", "gate": "agent_observation_coverage_ratio_min"})
    elif "observation_coverage_ratio" in metrics and float(metrics.get("observation_coverage_ratio") or 0.0) < float(coverage_min):
        findings.append(
            {
                "id": "agent_observation_coverage_below_slo",
                "value": metrics.get("observation_coverage_ratio"),
                "minimum": coverage_min,
            }
        )
    observed_min = gates.get("agent_observed_work_item_count_min")
    if observed_min is None:
        findings.append({"id": "required_agent_slo_gate_unavailable", "gate": "agent_observed_work_item_count_min"})
    elif int(metrics.get("observed_work_item_count") or 0) < int(observed_min):
        findings.append(
            {
                "id": "agent_observed_work_item_count_below_slo",
                "value": metrics.get("observed_work_item_count"),
                "minimum": observed_min,
            }
        )
    family_min = gates.get("agent_observed_distinct_work_family_count_min")
    if family_min is None:
        findings.append({"id": "required_agent_slo_gate_unavailable", "gate": "agent_observed_distinct_work_family_count_min"})
    elif int(metrics.get("observed_distinct_work_family_count") or 0) < int(family_min):
        findings.append(
            {
                "id": "agent_observed_distinct_work_family_count_below_slo",
                "value": metrics.get("observed_distinct_work_family_count"),
                "minimum": family_min,
            }
        )
    closed_required = gates.get("agent_observation_window_closed_required")
    if closed_required is None:
        findings.append({"id": "required_agent_slo_gate_unavailable", "gate": "agent_observation_window_closed_required"})
    elif bool(closed_required) and metrics.get("observation_window_status") != "closed":
        findings.append(
            {
                "id": "agent_observation_window_not_closed",
                "value": metrics.get("observation_window_status"),
            }
        )
    receipt_failure_max = gates.get("agent_receipt_validation_failure_count_max")
    if receipt_failure_max is None:
        findings.append({"id": "required_agent_slo_gate_unavailable", "gate": "agent_receipt_validation_failure_count_max"})
    elif int(metrics.get("receipt_validation_failure_count") or 0) > int(receipt_failure_max):
        findings.append(
            {
                "id": "agent_receipt_validation_failures",
                "count": metrics.get("receipt_validation_failure_count"),
                "maximum": receipt_failure_max,
            }
        )
    if int(metrics.get("failed_or_aborted_work_item_count") or 0) > 0:
        findings.append(
            {
                "id": "agent_observation_window_contains_failed_drill",
                "count": metrics.get("failed_or_aborted_work_item_count"),
            }
        )
    insufficient = any(
        item.get("id")
        in {
            "agent_observation_coverage_below_slo",
            "agent_observed_work_item_count_below_slo",
            "agent_observed_distinct_work_family_count_below_slo",
            "agent_observation_window_not_closed",
            "required_agent_slo_gate_unavailable",
        }
        for item in findings
    )
    result = {
        "version": "evaluator_result_v1",
        "evaluator_id": EVALUATOR_ID,
        "executed_at_utc": evaluation_time_utc(),
        "input_hashes": [
            input_hash(repo_root, metrics_path),
            input_hash(repo_root, "docs/policies/codex_operating_slo.yaml"),
        ],
        "implementation_hashes": implementation_hashes(
            repo_root,
            (
                "foundation/evaluation/agent_value_evaluator.py",
                "src/spacesonar/control_plane/agent_metrics.py",
            ),
        ),
        "status": "insufficient_evidence" if insufficient else ("failed" if findings else "passed"),
        "metrics": metrics,
        "findings": findings,
        "claim_effect": "agent_metrics_are_operating_telemetry_only_no_reviewed_pass",
    }
    return finalize_result(result)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = evaluate_agent_value(Path(args.repo_root).resolve())
    if args.output:
        write_yaml(Path(args.output), result)
    else:
        print(result)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
