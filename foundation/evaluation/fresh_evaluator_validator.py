from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation.evaluation.agent_value_evaluator import EVALUATOR_ID as AGENT_EVALUATOR_ID
from foundation.evaluation.agent_value_evaluator import evaluate_agent_value
from foundation.evaluation.common import load_yaml
from foundation.evaluation.operating_slo_evaluator import EVALUATOR_ID as OPERATING_SLO_EVALUATOR_ID
from foundation.evaluation.operating_slo_evaluator import evaluate_operating_slo
from foundation.evaluation.research_cycle_closeout_evaluator import EVALUATOR_ID as RESEARCH_EVALUATOR_ID
from foundation.evaluation.research_cycle_closeout_evaluator import evaluate_research_cycle_closeout
from foundation.evaluation.routing_quality_evaluator import EVALUATOR_ID as ROUTING_EVALUATOR_ID
from foundation.evaluation.routing_quality_evaluator import evaluate_routing_quality
from foundation.evaluation.runtime_contract_evaluator import EVALUATOR_ID as RUNTIME_EVALUATOR_ID
from foundation.evaluation.runtime_contract_evaluator import evaluate_runtime_contract


Evaluator = Callable[[Path], dict[str, Any]]
COMPARISON_KEYS = ("evaluator_id", "output_sha256", "input_hashes", "status", "metrics", "findings")
EVALUATORS: dict[str, Evaluator] = {
    RUNTIME_EVALUATOR_ID: evaluate_runtime_contract,
    ROUTING_EVALUATOR_ID: evaluate_routing_quality,
    AGENT_EVALUATOR_ID: evaluate_agent_value,
    OPERATING_SLO_EVALUATOR_ID: evaluate_operating_slo,
    RESEARCH_EVALUATOR_ID: evaluate_research_cycle_closeout,
}


def committed_evaluator_paths(repo_root: Path) -> list[Path]:
    paths: list[Path] = []
    root = repo_root / "lab" / "evaluations"
    if not root.exists():
        return paths
    for path in sorted(root.rglob("*.yaml")):
        payload = load_yaml(path) or {}
        if isinstance(payload, dict) and payload.get("version") == "evaluator_result_v1":
            paths.append(path)
    return paths


def compare_committed_evaluator_file(repo_root: Path, path: Path) -> list[str]:
    rel_path = path.relative_to(repo_root).as_posix()
    committed = load_yaml(path) or {}
    evaluator_id = str(committed.get("evaluator_id") or "")
    evaluator = EVALUATORS.get(evaluator_id)
    if evaluator is None:
        return [f"{rel_path}: unknown evaluator_id {evaluator_id!r}"]
    try:
        fresh = evaluator(repo_root)
    except Exception as exc:  # noqa: BLE001 - validator reports evaluator failures.
        return [f"{rel_path}: fresh evaluator raised {type(exc).__name__}: {exc}"]
    errors: list[str] = []
    for key in COMPARISON_KEYS:
        if committed.get(key) != fresh.get(key):
            errors.append(f"{rel_path}: committed evaluator {key} does not match fresh recomputation")
    return errors


def validate_committed_evaluators(repo_root: Path) -> list[str]:
    repo_root = repo_root.resolve()
    errors: list[str] = []
    paths = committed_evaluator_paths(repo_root)
    if not paths:
        return ["no committed evaluator_result_v1 files found under lab/evaluations"]
    for path in paths:
        errors.extend(compare_committed_evaluator_file(repo_root, path))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    errors = validate_committed_evaluators(Path(args.repo_root).resolve())
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("committed evaluator fresh comparison passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
