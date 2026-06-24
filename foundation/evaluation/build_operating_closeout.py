from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from foundation.evaluation.agent_value_evaluator import EVALUATOR_ID as AGENT_EVALUATOR_ID
from foundation.evaluation.agent_value_evaluator import evaluate_agent_value
from foundation.evaluation.common import evaluation_time_utc, load_yaml, semantic_result_payload, stable_sha256
from foundation.evaluation.fresh_evaluator_validator import compare_committed_evaluator_file, load_evaluator_registry, validate_committed_evaluators
from foundation.evaluation.operating_slo_evaluator import EVALUATOR_ID as OPERATING_EVALUATOR_ID
from foundation.evaluation.operating_slo_evaluator import evaluate_operating_slo
from foundation.evaluation.research_cycle_closeout_evaluator import EVALUATOR_ID as RESEARCH_EVALUATOR_ID
from foundation.evaluation.research_cycle_closeout_evaluator import evaluate_research_cycle_closeout
from foundation.evaluation.routing_quality_evaluator import EVALUATOR_ID as ROUTING_EVALUATOR_ID
from foundation.evaluation.routing_quality_evaluator import evaluate_routing_quality
from foundation.evaluation.runtime_contract_evaluator import EVALUATOR_ID as RUNTIME_EVALUATOR_ID
from foundation.evaluation.runtime_contract_evaluator import evaluate_runtime_contract
from foundation.validation.refresh_artifact_registry_hashes import refresh_registry
from spacesonar.control_plane.models import ExecutionContext, TransactionResult
from spacesonar.control_plane.store import dump_csv, filesystem_path, read_csv_rows
from spacesonar.control_plane.transaction import ControlPlaneTransaction


WAVE_CLOSEOUT_PATH = Path("lab/waves/wave_us100_closedbar_surface_cartography_v0/wave_closeout.yaml")
ARTIFACT_REGISTRY_PATH = Path("docs/registers/artifact_registry.csv")
EVALUATOR_REGISTRY_PATH = Path("docs/agent_control/evaluator_registry.yaml")
COMPLETE_CLAIM_BOUNDARY = (
    "control_plane_stabilization_validated_standard_l4_runtime_contract_complete_"
    "no_runtime_authority_no_economics_pass_no_live_readiness_no_selected_baseline"
)
REPAIR_CLAIM_BOUNDARY = (
    "control_plane_closeout_evidence_repair_required_no_runtime_authority_"
    "no_economics_pass_no_live_readiness_no_selected_baseline"
)


@dataclass(frozen=True)
class CloseoutEvaluation:
    closeout: dict[str, Any]
    digest: str
    requirement_audit: list[dict[str, Any]]
    staged_texts: dict[Path, str]


def _yaml_text(payload: dict[str, Any]) -> str:
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=False)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _registered_result_path(repo_root: Path, evaluator_id: str) -> Path:
    for entry in load_evaluator_registry(repo_root):
        if entry.get("evaluator_id") == evaluator_id and entry.get("role") == "active":
            return Path(str(entry["canonical_result_path"]))
    raise KeyError(f"active evaluator is not registered: {evaluator_id}")


def _result_ref(repo_root: Path, evaluator_id: str, result: dict[str, Any]) -> tuple[Path, str, dict[str, Any]]:
    rel_path = _registered_result_path(repo_root, evaluator_id)
    text = _yaml_text(result)
    existing_path = repo_root / rel_path
    if existing_path.exists():
        existing = load_yaml(existing_path) or {}
        if semantic_result_payload(existing) == semantic_result_payload(result):
            text = existing_path.read_text(encoding="utf-8")
    return rel_path, text, {
        "evaluator_id": evaluator_id,
        "evaluator_result_path": rel_path.as_posix(),
        "evaluator_output_sha256": result["output_sha256"],
        "evaluator_file_sha256": _sha256_text(text),
        "evaluator_result_sha256": result["output_sha256"],
        "status": result["status"],
    }


def _build_audit(result_refs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "requirement": "control_plane_operating_proof",
            **result_refs[OPERATING_EVALUATOR_ID],
            "status": result_refs[OPERATING_EVALUATOR_ID]["status"],
        },
        {
            "requirement": "research_cycle_closeout",
            **result_refs[RESEARCH_EVALUATOR_ID],
            "status": result_refs[RESEARCH_EVALUATOR_ID]["status"],
        },
        {
            "requirement": "runtime_contract_integrity",
            **result_refs[RUNTIME_EVALUATOR_ID],
            "status": result_refs[RUNTIME_EVALUATOR_ID]["status"],
        },
        {
            "requirement": "routing_behavior_quality",
            **result_refs[ROUTING_EVALUATOR_ID],
            "status": result_refs[ROUTING_EVALUATOR_ID]["status"],
        },
        {
            "requirement": "agent_value_metrics",
            **result_refs[AGENT_EVALUATOR_ID],
            "status": result_refs[AGENT_EVALUATOR_ID]["status"],
        },
    ]


def semantic_closeout_payload(closeout: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in closeout.items()
        if key not in {"generated_at_utc", "evaluation_digest"}
    }


def _closeout_digest(closeout: dict[str, Any]) -> str:
    return stable_sha256(semantic_closeout_payload(closeout))


def _required_problem_requirements(audit: list[dict[str, Any]]) -> list[str]:
    return [
        str(item.get("requirement"))
        for item in audit
        if item.get("status") != "passed"
    ]


def _campaign_summaries(research: dict[str, Any]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for result in research.get("campaign_results") or []:
        summaries.append(
            {
                "campaign_id": result.get("campaign_id"),
                "status": result.get("status"),
                "evidence_path": result.get("evidence_path"),
                "evidence_class": result.get("evidence_class"),
                "candidate_count": result.get("candidate_count"),
                "l5_candidate_count": result.get("l5_candidate_count"),
                "forbidden_claims_respected": result.get("forbidden_claims_respected"),
            }
        )
    return sorted(summaries, key=lambda item: str(item.get("campaign_id") or ""))


def _source_inputs(*results: dict[str, Any]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for result in results:
        for item in result.get("input_hashes") or []:
            path = str(item.get("path") or "")
            if path:
                seen[path] = item
    return [seen[key] for key in sorted(seen)]


def _handoff(repo_root: Path, research: dict[str, Any]) -> dict[str, Any]:
    negative_ids: set[str] = set()
    clue_ids: set[str] = set()
    for item in research.get("input_hashes") or []:
        path = str(item.get("path") or "")
        if path.startswith("lab/memory/negative/") and path.endswith(".yaml"):
            negative_ids.add(Path(path).stem)
        if path.startswith("lab/memory/clues/") and path.endswith(".yaml"):
            clue_ids.add(Path(path).stem)
    return {
        "negative_memory_ids": sorted(negative_ids),
        "preserved_clue_ids": sorted(clue_ids),
        "next_action": "work_post_wave01_user_directed_wave02_or_review_v0",
        "claim_boundary": REPAIR_CLAIM_BOUNDARY if research.get("status") != "passed" else COMPLETE_CLAIM_BOUNDARY,
    }


def _artifact_id_for_path(rel_path: Path) -> str:
    clean = rel_path.as_posix().replace("/", "_").replace(".", "_").replace("-", "_")
    return f"artifact_{clean}"


def _artifact_registry_text(repo_root: Path, staged_texts: dict[Path, str]) -> str:
    registry_path = repo_root / ARTIFACT_REGISTRY_PATH
    rows = read_csv_rows(registry_path)
    fieldnames = list(rows[0].keys()) if rows else [
        "artifact_id",
        "run_id",
        "bundle_id",
        "attempt_id",
        "artifact_type",
        "path_or_uri",
        "sha256",
        "size_bytes",
        "availability",
        "producer_command",
        "regeneration_command",
        "source_of_truth",
        "consumer",
        "claim_boundary",
        "notes",
    ]
    updated_rows = [dict(row) for row in rows]
    existing_paths = {row.get("path_or_uri") for row in updated_rows}
    for rel_path, text in sorted(staged_texts.items(), key=lambda item: item[0].as_posix()):
        if rel_path == ARTIFACT_REGISTRY_PATH:
            continue
        path_text = rel_path.as_posix()
        matched = False
        for row in updated_rows:
            if row.get("path_or_uri") != path_text:
                continue
            matched = True
            row.update(
                {
                    "sha256": _sha256_text(text),
                    "size_bytes": str(len(text.encode("utf-8"))),
                    "availability": row.get("availability") or "present_hash_recorded",
                    "producer_command": row.get("producer_command") or "python foundation/evaluation/build_operating_closeout.py --repo-root . --write",
                    "regeneration_command": "python foundation/evaluation/build_operating_closeout.py --repo-root . --write",
                    "source_of_truth": row.get("source_of_truth") or path_text,
                    "consumer": row.get("consumer") or "wave01_operating_closeout",
                    "claim_boundary": row.get("claim_boundary") or REPAIR_CLAIM_BOUNDARY,
                    "notes": row.get("notes") or "WP07 evaluator-backed closeout transactional artifact.",
                }
            )
        if not matched:
            row = {key: "" for key in fieldnames}
            row.update(
                {
                    "artifact_id": _artifact_id_for_path(rel_path),
                    "artifact_type": "evaluator_result" if "lab/evaluations/" in path_text else "control_plane_closeout",
                    "path_or_uri": path_text,
                    "sha256": _sha256_text(text),
                    "size_bytes": str(len(text.encode("utf-8"))),
                    "availability": "present_hash_recorded",
                    "producer_command": "python foundation/evaluation/build_operating_closeout.py --repo-root . --write",
                    "regeneration_command": "python foundation/evaluation/build_operating_closeout.py --repo-root . --write",
                    "source_of_truth": path_text,
                    "consumer": "wave01_operating_closeout",
                    "claim_boundary": REPAIR_CLAIM_BOUNDARY,
                    "notes": "WP07 evaluator-backed closeout transactional artifact.",
                }
            )
            updated_rows.append(row)
            existing_paths.add(path_text)
    if EVALUATOR_REGISTRY_PATH.as_posix() not in existing_paths:
        registry_text = (repo_root / EVALUATOR_REGISTRY_PATH).read_text(encoding="utf-8")
        row = {key: "" for key in fieldnames}
        row.update(
            {
                "artifact_id": _artifact_id_for_path(EVALUATOR_REGISTRY_PATH),
                "artifact_type": "evaluator_registry",
                "path_or_uri": EVALUATOR_REGISTRY_PATH.as_posix(),
                "sha256": _sha256_text(registry_text),
                "size_bytes": str(len(registry_text.encode("utf-8"))),
                "availability": "present_hash_recorded",
                "producer_command": "manual_control_plane_policy",
                "regeneration_command": "python foundation/evaluation/fresh_evaluator_validator.py --repo-root .",
                "source_of_truth": EVALUATOR_REGISTRY_PATH.as_posix(),
                "consumer": "fresh_evaluator_validator",
                "claim_boundary": REPAIR_CLAIM_BOUNDARY,
                "notes": "Authoritative evaluator registry for WP07 closeout validation.",
            }
        )
        updated_rows.append(row)
    ordered = sorted(updated_rows, key=lambda row: str(row.get("artifact_id") or ""))
    return dump_csv(fieldnames, ordered)


def evaluate_operating_closeout(repo_root: Path, *, write: bool = False) -> CloseoutEvaluation:
    del write
    repo_root = repo_root.resolve()
    existing = load_yaml(repo_root / WAVE_CLOSEOUT_PATH) or {}
    runtime = evaluate_runtime_contract(repo_root)
    routing = evaluate_routing_quality(repo_root)
    agent = evaluate_agent_value(repo_root)
    operating = evaluate_operating_slo(repo_root)
    research = evaluate_research_cycle_closeout(repo_root)
    result_payloads = {
        RUNTIME_EVALUATOR_ID: runtime,
        ROUTING_EVALUATOR_ID: routing,
        AGENT_EVALUATOR_ID: agent,
        OPERATING_EVALUATOR_ID: operating,
        RESEARCH_EVALUATOR_ID: research,
    }
    staged_texts: dict[Path, str] = {}
    result_refs: dict[str, dict[str, Any]] = {}
    for evaluator_id, result in result_payloads.items():
        rel_path, text, ref = _result_ref(repo_root, evaluator_id, result)
        staged_texts[rel_path] = text
        result_refs[evaluator_id] = ref
        for entry in load_evaluator_registry(repo_root):
            if entry.get("evaluator_id") == evaluator_id:
                for alias_path in entry.get("allowed_alias_paths") or []:
                    staged_texts[Path(str(alias_path))] = text

    audit = _build_audit(result_refs)
    problem_requirements = _required_problem_requirements(audit)
    all_required_passed = not problem_requirements
    runtime_passed = runtime["status"] == "passed"
    research_metrics = research.get("metrics") or {}
    candidate_count = research_metrics.get("candidate_count")
    l5_candidate_count = research_metrics.get("l5_candidate_count")
    closeout_status = (
        "wave01_control_plane_proof_closed_runtime_contract_complete"
        if all_required_passed and runtime_passed
        else "wave01_evaluator_backed_closeout_requires_evidence_repair"
    )
    claim_boundary = COMPLETE_CLAIM_BOUNDARY if all_required_passed and runtime_passed else REPAIR_CLAIM_BOUNDARY
    next_action = (
        "work_post_wave01_user_directed_wave02_or_review_v0"
        if all_required_passed
        else "repair_closeout_evaluator_evidence_before_wp08_or_main_integration"
    )
    wave_summary = {
        "wave_id": existing.get("wave_id", "wave_us100_closedbar_surface_cartography_v0"),
        "campaign_count": research_metrics.get("campaign_count"),
        "candidate_count": candidate_count,
        "l5_candidate_count": l5_candidate_count,
        "runtime_authority": False,
        "economics_pass": False,
        "locked_final_oos_used": research_metrics.get("locked_final_oos_used"),
        "runtime_contract_integrity": runtime["status"],
        "operating_slo_status": operating["status"],
        "agent_value_status": agent["status"],
        "research_cycle_status": research["status"],
    }
    closeout = {
        "version": "wave_closeout_v2",
        "closeout_id": existing.get("closeout_id", "wave01_operating_closeout_v0"),
        "generated_by": "foundation.evaluation.build_operating_closeout",
        "generated_at_utc": evaluation_time_utc(),
        "status": closeout_status,
        "result": {
            "control_plane_operating_proof": operating["status"],
            "research_cycle_closeout": research["status"],
            "runtime_contract_integrity": runtime["status"],
            "routing_behavior_quality": routing["status"],
            "agent_value_metrics": agent["status"],
            "runtime_authority": "not_claimed",
            "economics_pass": "not_claimed",
            "candidate_count": candidate_count,
            "l5_candidate_count": l5_candidate_count,
        },
        "result_judgment": {
            "control_plane": "positive" if operating["status"] == "passed" else "evidence_repair_required",
            "runtime_contract": "complete" if runtime_passed else "incomplete",
            "research_outcome": "no_candidate_with_negative_memory_and_preserved_clues"
            if research["status"] == "passed" and candidate_count == 0 and l5_candidate_count == 0
            else "research_closeout_evidence_repair_required",
            "failed_or_insufficient_requirements": problem_requirements,
        },
        "claim_boundary": claim_boundary,
        "active_goal_id": existing.get("active_goal_id", "goal_us100_onnx_forward_boundary_v0"),
        "wave_id": existing.get("wave_id", "wave_us100_closedbar_surface_cartography_v0"),
        "source_of_truth": WAVE_CLOSEOUT_PATH.as_posix(),
        "source_inputs": _source_inputs(runtime, routing, agent, operating, research),
        "wave_summary": wave_summary,
        "campaign_summaries": _campaign_summaries(research),
        "requirement_audit": audit,
        "evaluation_results": list(result_refs.values()),
        "handoff": _handoff(repo_root, research),
        "runtime_contract_integrity": {
            "status": runtime["status"],
            "reason": "runtime contract evaluated from committed attempt, terminal, telemetry, and tester-report receipt evidence",
            "runtime_authority": False,
            "economics_pass": False,
            "evaluator_id": RUNTIME_EVALUATOR_ID,
            "evaluator_result_path": result_refs[RUNTIME_EVALUATOR_ID]["evaluator_result_path"],
            "evaluator_output_sha256": result_refs[RUNTIME_EVALUATOR_ID]["evaluator_output_sha256"],
            "evaluator_file_sha256": result_refs[RUNTIME_EVALUATOR_ID]["evaluator_file_sha256"],
        },
        "not_claimed": [
            "runtime_authority",
            "economics_pass",
            "live_readiness",
            "selected_baseline",
            "reviewed_or_verified_pass",
            "production_deployment",
        ],
        "migration_history": existing.get("migration_history", []),
        "next_action": next_action,
    }
    closeout["evaluation_digest"] = _closeout_digest(closeout)
    staged_texts[WAVE_CLOSEOUT_PATH] = _yaml_text(closeout)
    staged_texts[ARTIFACT_REGISTRY_PATH] = _artifact_registry_text(repo_root, staged_texts)
    return CloseoutEvaluation(closeout=closeout, digest=closeout["evaluation_digest"], requirement_audit=audit, staged_texts=staged_texts)


def load_committed_closeout(repo_root: Path) -> dict[str, Any]:
    return load_yaml(repo_root / WAVE_CLOSEOUT_PATH) or {}


def validate_committed_closeout(repo_root: Path) -> list[str]:
    errors: list[str] = []
    committed = load_committed_closeout(repo_root)
    recomputed = evaluate_operating_closeout(repo_root, write=False).closeout
    for item in committed.get("requirement_audit") or []:
        required = {
            "requirement",
            "evaluator_id",
            "evaluator_result_path",
            "evaluator_output_sha256",
            "evaluator_file_sha256",
            "status",
        }
        missing = required - set(item)
        if missing:
            errors.append(f"closeout requirement {item.get('requirement')}: missing evaluator fields {sorted(missing)}")
        if item.get("status") == "passed" and not item.get("evaluator_id"):
            errors.append(f"closeout requirement {item.get('requirement')}: self-attested passed status")
        rel_path = item.get("evaluator_result_path")
        if rel_path:
            evaluator_path = repo_root / str(rel_path)
            if not evaluator_path.exists():
                errors.append(f"closeout requirement {item.get('requirement')}: missing evaluator result {rel_path}")
            else:
                evaluator_payload = load_yaml(evaluator_path) or {}
                evaluator_file_sha = hashlib.sha256(evaluator_path.read_bytes()).hexdigest()
                if evaluator_payload.get("evaluator_id") != item.get("evaluator_id"):
                    errors.append(f"closeout requirement {item.get('requirement')}: evaluator_id mismatch")
                if evaluator_payload.get("status") != item.get("status"):
                    errors.append(f"closeout requirement {item.get('requirement')}: evaluator status mismatch")
                if evaluator_payload.get("output_sha256") != item.get("evaluator_output_sha256"):
                    errors.append(f"closeout requirement {item.get('requirement')}: evaluator output_sha256 mismatch")
                if evaluator_file_sha != item.get("evaluator_file_sha256"):
                    errors.append(f"closeout requirement {item.get('requirement')}: evaluator file sha256 mismatch")
                errors.extend(compare_committed_evaluator_file(repo_root, evaluator_path))
    expected_digest = _closeout_digest(committed) if committed else None
    if committed.get("evaluation_digest") != expected_digest:
        errors.append("committed closeout evaluation_digest does not match committed semantic payload")
    if semantic_closeout_payload(committed) != semantic_closeout_payload(recomputed):
        errors.append("committed closeout semantic payload does not match recomputed closeout")
    return errors


def _transaction_validation(future_root: Path) -> list[str]:
    with tempfile.TemporaryDirectory(prefix="spacesonar_closeout_future_") as tmp:
        validation_root = Path(tmp) / "repo"
        shutil.copytree(filesystem_path(future_root), filesystem_path(validation_root))
        return _transaction_validation_short_path(validation_root)


def _transaction_validation_short_path(future_root: Path) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_committed_evaluators(future_root))
    errors.extend(validate_committed_closeout(future_root))
    from foundation.validation.execution_provenance_validator import validate as validate_execution_provenance
    from foundation.validation.active_record_validator import validate as validate_active_records
    from foundation.validation.control_plane_validator import validate as validate_control_plane

    errors.extend(validate_execution_provenance(future_root))
    errors.extend(validate_control_plane(future_root, include_active_records=False))
    errors.extend(validate_active_records(future_root))
    registry_report = refresh_registry(future_root, future_root / ARTIFACT_REGISTRY_PATH, write=False)
    errors.extend(f"artifact registry missing path: {path}" for path in registry_report.missing_paths)
    errors.extend(f"artifact registry hash drift: {change.artifact_id}" for change in registry_report.changed_rows)
    return errors


def write_operating_closeout_transaction(
    repo_root: Path,
    *,
    fail_after_replace_count: int | None = None,
) -> TransactionResult:
    evaluation = evaluate_operating_closeout(repo_root, write=False)
    context = ExecutionContext(
        repo_root=repo_root.resolve(),
        work_item_id="work_codex_control_plane_corrective_v3",
        claim_boundary=evaluation.closeout["claim_boundary"],
        command_argv=("python", "foundation/evaluation/build_operating_closeout.py", "--repo-root", ".", "--write"),
        validation_commands=(
            "fresh_evaluator_validator",
            "build_operating_closeout --check",
            "execution_provenance_validator",
            "control_plane_validator",
            "active_record_validator",
            "artifact_registry_hash_validation",
        ),
    )
    tx = ControlPlaneTransaction(context)
    for rel_path, text in sorted(evaluation.staged_texts.items(), key=lambda item: item[0].as_posix()):
        tx.stage_text(rel_path, text)
    return tx.commit(validate=_transaction_validation, fail_after_replace_count=fail_after_replace_count)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--fail-after-replace-count", type=int)
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    if args.write:
        result = write_operating_closeout_transaction(repo_root, fail_after_replace_count=args.fail_after_replace_count)
        print(
            yaml.safe_dump(
                {
                    "transaction_id": result.transaction_id,
                    "status": result.status,
                    "receipt_path": result.receipt_path.as_posix(),
                    "errors": list(result.errors),
                },
                sort_keys=False,
            )
        )
        return 0 if result.status in {"committed", "noop_already_applied"} else 1
    if args.check:
        errors = validate_committed_closeout(repo_root)
        if errors:
            for error in errors:
                print(f"ERROR: {error}")
            return 1
        print("operating closeout validation passed")
        return 0
    evaluation = evaluate_operating_closeout(repo_root, write=False)
    print(yaml.safe_dump(evaluation.closeout, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
