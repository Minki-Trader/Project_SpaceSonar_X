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
from foundation.evaluation.common import load_yaml, semantic_result_payload, stable_sha256
from foundation.evaluation.operating_slo_evaluator import EVALUATOR_ID as OPERATING_SLO_EVALUATOR_ID
from foundation.evaluation.operating_slo_evaluator import evaluate_operating_slo
from foundation.evaluation.research_cycle_closeout_evaluator import EVALUATOR_ID as RESEARCH_EVALUATOR_ID
from foundation.evaluation.research_cycle_closeout_evaluator import evaluate_research_cycle_closeout
from foundation.evaluation.routing_quality_evaluator import EVALUATOR_ID as ROUTING_EVALUATOR_ID
from foundation.evaluation.routing_quality_evaluator import evaluate_routing_quality
from foundation.evaluation.runtime_contract_evaluator import EVALUATOR_ID as RUNTIME_EVALUATOR_ID
from foundation.evaluation.runtime_contract_evaluator import evaluate_runtime_contract


Evaluator = Callable[[Path], dict[str, Any]]
REGISTRY_PATH = Path("docs/agent_control/evaluator_registry.yaml")
EVALUATORS: dict[str, Evaluator] = {
    RUNTIME_EVALUATOR_ID: evaluate_runtime_contract,
    ROUTING_EVALUATOR_ID: evaluate_routing_quality,
    AGENT_EVALUATOR_ID: evaluate_agent_value,
    OPERATING_SLO_EVALUATOR_ID: evaluate_operating_slo,
    RESEARCH_EVALUATOR_ID: evaluate_research_cycle_closeout,
}


def load_evaluator_registry(repo_root: Path) -> list[dict[str, Any]]:
    registry = load_yaml(repo_root / REGISTRY_PATH) or {}
    return list(registry.get("evaluators") or [])


def _all_declared_result_paths(entries: list[dict[str, Any]]) -> set[str]:
    paths: set[str] = set()
    for entry in entries:
        if entry.get("canonical_result_path"):
            paths.add(str(entry["canonical_result_path"]))
        paths.update(str(path) for path in (entry.get("allowed_alias_paths") or []))
    return paths


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


def _compare_payload_to_fresh(repo_root: Path, rel_path: str, evaluator_id: str) -> list[str]:
    path = repo_root / rel_path
    committed = load_yaml(path) or {}
    errors: list[str] = []
    if committed.get("evaluator_id") != evaluator_id:
        errors.append(f"{rel_path}: evaluator_id {committed.get('evaluator_id')!r} does not match registry {evaluator_id!r}")
        return errors
    expected_output = stable_sha256(semantic_result_payload(committed))
    if committed.get("output_sha256") != expected_output:
        errors.append(f"{rel_path}: stored output_sha256 does not match committed semantic payload")
    evaluator = EVALUATORS.get(evaluator_id)
    if evaluator is None:
        errors.append(f"{rel_path}: unknown evaluator_id {evaluator_id!r}")
        return errors
    try:
        fresh = evaluator(repo_root)
    except Exception as exc:  # noqa: BLE001 - validator reports evaluator failures.
        errors.append(f"{rel_path}: fresh evaluator raised {type(exc).__name__}: {exc}")
        return errors
    if semantic_result_payload(committed) != semantic_result_payload(fresh):
        errors.append(f"{rel_path}: committed evaluator semantic payload does not match fresh recomputation")
    return errors


def compare_committed_evaluator_file(repo_root: Path, path: Path) -> list[str]:
    repo_root = repo_root.resolve()
    rel_path = path.relative_to(repo_root).as_posix()
    entries = load_evaluator_registry(repo_root)
    for entry in entries:
        paths = {str(entry.get("canonical_result_path") or ""), *[str(item) for item in (entry.get("allowed_alias_paths") or [])]}
        if rel_path in paths:
            return _compare_payload_to_fresh(repo_root, rel_path, str(entry.get("evaluator_id") or ""))
    return [f"{rel_path}: evaluator result path is not declared in {REGISTRY_PATH.as_posix()}"]


def validate_committed_evaluators(repo_root: Path) -> list[str]:
    repo_root = repo_root.resolve()
    errors: list[str] = []
    registry_path = repo_root / REGISTRY_PATH
    if not registry_path.exists():
        return [f"missing evaluator registry: {REGISTRY_PATH.as_posix()}"]
    entries = load_evaluator_registry(repo_root)
    active_entries = [entry for entry in entries if entry.get("role") == "active"]
    active_ids = [str(entry.get("evaluator_id") or "") for entry in active_entries]
    duplicates = sorted({item for item in active_ids if active_ids.count(item) > 1})
    for evaluator_id in duplicates:
        errors.append(f"evaluator_registry: duplicate active evaluator_id {evaluator_id}")

    declared_paths = _all_declared_result_paths(entries)
    for path in committed_evaluator_paths(repo_root):
        rel_path = path.relative_to(repo_root).as_posix()
        if rel_path not in declared_paths:
            errors.append(f"{rel_path}: undeclared active evaluator result")

    for entry in active_entries:
        evaluator_id = str(entry.get("evaluator_id") or "")
        canonical = str(entry.get("canonical_result_path") or "")
        if entry.get("required_for_operating_closeout") is True and not entry.get("closeout_requirement"):
            errors.append(f"evaluator_registry: {evaluator_id} missing closeout_requirement")
        if not canonical:
            errors.append(f"evaluator_registry: {evaluator_id} missing canonical_result_path")
            continue
        if not (repo_root / canonical).is_file():
            errors.append(f"{canonical}: missing active evaluator result")
        else:
            errors.extend(_compare_payload_to_fresh(repo_root, canonical, evaluator_id))
        for implementation_path in entry.get("implementation_paths") or []:
            if not (repo_root / str(implementation_path)).is_file():
                errors.append(f"evaluator_registry: {evaluator_id} implementation path missing: {implementation_path}")
        for alias_path in entry.get("allowed_alias_paths") or []:
            alias = str(alias_path)
            if not (repo_root / alias).exists():
                continue
            alias_errors = _compare_payload_to_fresh(repo_root, alias, evaluator_id)
            errors.extend(alias_errors)
            if not alias_errors and (repo_root / canonical).is_file():
                canonical_payload = semantic_result_payload(load_yaml(repo_root / canonical) or {})
                alias_payload = semantic_result_payload(load_yaml(repo_root / alias) or {})
                if alias_payload != canonical_payload:
                    errors.append(f"{alias}: compatibility snapshot differs from canonical evaluator {canonical}")
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
