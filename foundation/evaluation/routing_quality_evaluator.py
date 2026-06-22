from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation.evaluation.common import EVALUATION_TIME_UTC, finalize_result, input_hash, write_yaml
from foundation.validation.routing_behavior_eval import evaluate as evaluate_routing_behavior


EVALUATOR_ID = "routing_quality_evaluator_v1"


def evaluate_routing_quality(repo_root: Path) -> dict:
    errors, metrics = evaluate_routing_behavior(repo_root)
    result = {
        "version": "evaluator_result_v1",
        "evaluator_id": EVALUATOR_ID,
        "executed_at_utc": EVALUATION_TIME_UTC,
        "input_hashes": [
            input_hash(repo_root, "docs/agent_control/routing_behavior_cases.yaml"),
            input_hash(repo_root, "docs/agent_control/work_family_registry.yaml"),
        ],
        "status": "failed" if errors else "passed",
        "metrics": metrics,
        "findings": [{"id": "routing_error", "detail": error} for error in errors],
        "claim_effect": "routing_behavior_evaluated_no_runtime_or_economics_claim",
    }
    return finalize_result(result)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = evaluate_routing_quality(Path(args.repo_root).resolve())
    if args.output:
        write_yaml(Path(args.output), result)
    else:
        print(result)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
