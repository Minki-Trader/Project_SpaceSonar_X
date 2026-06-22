from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation.evaluation.common import EVALUATION_TIME_UTC, finalize_result, input_hash, load_yaml, write_yaml


EVALUATOR_ID = "agent_value_evaluator_v1"


def evaluate_agent_value(repo_root: Path) -> dict:
    metrics_path = "docs/workspace/agent_operating_metrics.yaml"
    data = load_yaml(repo_root / metrics_path) or {}
    metrics = data.get("agent_operating_metrics") or {}
    findings = []
    if float(metrics.get("solo_work_share", 0.0)) < 0.80:
        findings.append({"id": "solo_or_single_agent_share_below_slo", "value": metrics.get("solo_work_share")})
    if float(metrics.get("duplicate_advice_ratio", 1.0)) > 0.20:
        findings.append({"id": "duplicate_advice_ratio_above_slo", "value": metrics.get("duplicate_advice_ratio")})
    if int(metrics.get("unsupported_assertion_count", 0)) > 0:
        findings.append({"id": "unsupported_agent_assertions", "count": metrics.get("unsupported_assertion_count")})
    result = {
        "version": "evaluator_result_v1",
        "evaluator_id": EVALUATOR_ID,
        "executed_at_utc": EVALUATION_TIME_UTC,
        "input_hashes": [input_hash(repo_root, metrics_path)],
        "status": "failed" if findings else "passed",
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
