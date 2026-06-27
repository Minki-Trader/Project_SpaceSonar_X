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
from foundation.evaluation.common import evaluation_time_utc, input_hash, load_yaml, semantic_result_payload, stable_sha256
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
from spacesonar.control_plane.registry_projection import _stage_registry_projections, artifact_row_for_text, project_registries, projection_diffs
from spacesonar.control_plane.state_projection import workspace_projection_diff, workspace_projection_text
from spacesonar.control_plane.store import dump_csv, filesystem_path, read_csv_rows
from spacesonar.control_plane.transaction import ControlPlaneTransaction


WAVE_CLOSEOUT_PATH = Path("lab/waves/wave_us100_closedbar_surface_cartography_v0/wave_closeout.yaml")
WAVE_ID = WAVE_CLOSEOUT_PATH.parent.name
ARTIFACT_REGISTRY_PATH = Path("docs/registers/artifact_registry.csv")
EVALUATOR_REGISTRY_PATH = Path("docs/agent_control/evaluator_registry.yaml")
GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
GOAL_MANIFEST_PATH = Path("lab/goals") / GOAL_ID / "goal_manifest.yaml"
NEXT_WORK_ITEM_PATH = Path("lab/goals") / GOAL_ID / "next_work_item.yaml"
RESUME_CURSOR_PATH = Path("lab/goals") / GOAL_ID / "resume_cursor.yaml"
WORKSPACE_STATE_PATH = Path("docs/workspace/workspace_state.yaml")
REPAIR_WORK_ITEM_ID = "work_wp07_closeout_evidence_repair_v0"
REPAIR_GOAL_STATUS = "wave01_operating_proof_evidence_repair_required"
REPAIR_PHASE = "wp07_closeout_evidence_repair"
REPAIR_WAVE_STATUS = "wave01_evaluator_backed_closeout_requires_evidence_repair"
REPAIR_GIT_STATUS = "blocked_pending_evaluator_evidence_repair_not_ready_for_main_integration"
COMPLETE_WORK_ITEM_ID = "work_post_wave01_user_directed_wave02_or_review_v0"
COMPLETE_GOAL_STATUS = "complete_wave01_operating_proof_window"
COMPLETE_GOAL_PHASE = "wave01_operating_closeout_complete"
COMPLETE_WAVE_STATUS = "wave01_operating_proof_window_closed"
COMPLETE_WAVE_NEXT_ACTION = COMPLETE_WORK_ITEM_ID
COMPLETE_GIT_STATUS = "wave_closeout_ready_for_boundary_commit_and_main_integration"
REPAIR_NEXT_ACTION = "repair_closeout_evaluator_evidence_before_wp08_or_main_integration"
COMPLETE_CLAIM_BOUNDARY = (
    "control_plane_stabilization_validated_standard_l4_runtime_contract_complete_"
    "no_runtime_authority_no_economics_pass_no_live_readiness_no_selected_baseline"
)
REPAIR_CLAIM_BOUNDARY = (
    "control_plane_closeout_evidence_repair_required_no_runtime_authority_"
    "no_economics_pass_no_live_readiness_no_selected_baseline"
)
EVALUATOR_FUNCTIONS = {
    RUNTIME_EVALUATOR_ID: evaluate_runtime_contract,
    ROUTING_EVALUATOR_ID: evaluate_routing_quality,
    AGENT_EVALUATOR_ID: evaluate_agent_value,
    OPERATING_EVALUATOR_ID: evaluate_operating_slo,
    RESEARCH_EVALUATOR_ID: evaluate_research_cycle_closeout,
}


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


def _input_hash_for_text(rel_path: Path, text: str) -> dict[str, Any]:
    encoded = text.encode("utf-8")
    return {
        "path": rel_path.as_posix(),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "size_bytes": len(encoded),
    }


def _required_evaluator_entries(repo_root: Path) -> list[dict[str, Any]]:
    entries = [
        entry
        for entry in load_evaluator_registry(repo_root)
        if entry.get("role") == "active" and entry.get("required_for_operating_closeout") is True
    ]
    missing_requirements = [str(entry.get("evaluator_id") or "") for entry in entries if not entry.get("closeout_requirement")]
    if missing_requirements:
        raise ValueError(f"required evaluators missing closeout_requirement: {', '.join(sorted(missing_requirements))}")
    return sorted(entries, key=lambda item: str(item.get("closeout_requirement") or item.get("evaluator_id") or ""))


def _evaluate_registered_evaluators(repo_root: Path, entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    unsupported: list[str] = []
    for entry in entries:
        evaluator_id = str(entry.get("evaluator_id") or "")
        evaluator = EVALUATOR_FUNCTIONS.get(evaluator_id)
        if evaluator is None:
            unsupported.append(evaluator_id)
            continue
        results[evaluator_id] = evaluator(repo_root)
    if unsupported:
        raise ValueError(f"required evaluator unsupported by operating closeout builder: {', '.join(sorted(unsupported))}")
    return results


def _result_ref(repo_root: Path, entry: dict[str, Any], result: dict[str, Any]) -> tuple[Path, str, dict[str, Any]]:
    evaluator_id = str(entry.get("evaluator_id") or "")
    rel_path = Path(str(entry["canonical_result_path"]))
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


def _build_audit(required_entries: list[dict[str, Any]], result_refs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    audit = []
    for entry in required_entries:
        evaluator_id = str(entry.get("evaluator_id") or "")
        ref = result_refs[evaluator_id]
        audit.append(
            {
                "requirement": str(entry.get("closeout_requirement") or ""),
                **ref,
                "status": ref["status"],
            }
        )
    return audit


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


def _load_goal_and_wave(repo_root: Path) -> tuple[Path, dict[str, Any], Path, dict[str, Any], Path]:
    goal_path = GOAL_MANIFEST_PATH
    goal = load_yaml(repo_root / goal_path) or {}
    active_goal_id = str(goal.get("active_goal_id") or goal.get("goal_id") or "")
    if active_goal_id != GOAL_ID:
        raise ValueError(f"unexpected active goal id {active_goal_id!r}; expected {GOAL_ID!r}")
    wave_id = WAVE_ID
    wave_path = Path("lab/waves") / str(wave_id) / "wave_allocation.yaml"
    wave = load_yaml(repo_root / wave_path) or {}
    if wave.get("wave_id") != wave_id:
        raise ValueError(f"wave allocation id mismatch for {wave_path.as_posix()}")
    storage = wave.get("storage_contract") or {}
    closeout_path = Path(str(storage.get("wave_closeout") or wave.get("wave_closeout") or (wave_path.parent / "wave_closeout.yaml").as_posix()))
    return goal_path, goal, wave_path, wave, closeout_path


def _goal_still_points_to_wave01(goal: dict[str, Any], wave: dict[str, Any]) -> bool:
    active_ids = goal.get("active_ids") or {}
    return (active_ids.get("wave_id") or (goal.get("objective_revision") or {}).get("internal_active_wave_id")) == wave.get("wave_id")


def _derived_closeout_id(wave: dict[str, Any]) -> str:
    return f"{wave['wave_id']}_operating_closeout_v0"


def _repair_next_work() -> dict[str, Any]:
    return {
        "path": NEXT_WORK_ITEM_PATH.as_posix(),
        "work_item_id": REPAIR_WORK_ITEM_ID,
        "summary": "Repair evaluator evidence consistency before WP08 or main integration.",
    }


def _complete_next_work() -> dict[str, Any]:
    return {
        "path": NEXT_WORK_ITEM_PATH.as_posix(),
        "work_item_id": COMPLETE_WORK_ITEM_ID,
        "summary": "Wave01 evaluator-backed closeout complete; await user-directed Wave02 or review.",
    }


def _finding_ids(value: Any) -> list[str]:
    ids: list[str] = []
    if isinstance(value, dict):
        finding_id = value.get("id")
        if finding_id:
            ids.append(str(finding_id))
        for item in value.values():
            ids.extend(_finding_ids(item))
    elif isinstance(value, list):
        for item in value:
            ids.extend(_finding_ids(item))
    return ids


def _blocking_finding_ids(required_entries: list[dict[str, Any]], result_payloads: dict[str, dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for entry in required_entries:
        evaluator_id = str(entry.get("evaluator_id") or "")
        result = result_payloads.get(evaluator_id) or {}
        if result.get("status") == "passed":
            continue
        blockers.extend(_finding_ids(result.get("findings") or []))
        if not blockers:
            requirement = str(entry.get("closeout_requirement") or evaluator_id or "required_evaluator")
            blockers.append(f"{requirement}_not_passed")
    return sorted(set(blockers))


def _missing_material_from_blockers(blocking_finding_ids: list[str]) -> list[str]:
    missing: list[str] = []
    if "agent_observation_coverage_below_slo" in blocking_finding_ids or "agent_value_slo_failed" in blocking_finding_ids:
        missing.append("agent_observation_coverage_work_receipts")
    for finding_id in blocking_finding_ids:
        if finding_id in {"agent_observation_coverage_below_slo", "agent_value_slo_failed"}:
            continue
        missing.append(f"evaluator_finding:{finding_id}")
    return sorted(set(missing))


def _preserve_wave_completion_assertion(wave: dict[str, Any], updated_wave: dict[str, Any]) -> None:
    if isinstance(updated_wave.get("wave01_operating_completion_assertion"), dict):
        assertion = dict(updated_wave["wave01_operating_completion_assertion"])
    else:
        assertion = {
            "status": wave.get("status"),
            "claim_boundary": wave.get("claim_boundary"),
            "next_action": wave.get("next_action"),
            "git_integration_status": (wave.get("git_integration") or {}).get("status"),
            "asserted_at_utc": wave.get("updated_at_utc") or wave.get("created_at_utc"),
        }
    assertion["validation_status"] = "superseded_by_fresh_evaluator_insufficient_evidence"
    updated_wave["wave01_operating_completion_assertion"] = assertion


def _state_transition_payloads(
    repo_root: Path,
    *,
    all_required_passed: bool,
    problem_requirements: list[str],
    blocking_finding_ids: list[str],
    generated_at_utc: str,
    goal: dict[str, Any],
    wave: dict[str, Any],
    closeout: dict[str, Any],
) -> dict[Path, dict[str, Any]]:
    next_work = load_yaml(repo_root / NEXT_WORK_ITEM_PATH) if (repo_root / NEXT_WORK_ITEM_PATH).exists() else {}
    cursor = load_yaml(repo_root / RESUME_CURSOR_PATH) if (repo_root / RESUME_CURSOR_PATH).exists() else {}
    updated_goal = dict(goal)
    updated_wave = dict(wave)
    active_ids = dict(updated_goal.get("active_ids") or {})
    active_ids["campaign_id"] = None
    updated_goal["active_ids"] = active_ids
    updated_next_work = dict(next_work)
    updated_cursor = dict(cursor)
    updated_goal["updated_at_utc"] = generated_at_utc
    updated_next_work["updated_at_utc"] = generated_at_utc
    updated_cursor["updated_at_utc"] = generated_at_utc
    updated_wave["updated_at_utc"] = generated_at_utc
    if all_required_passed:
        next_work_pointer = _complete_next_work()
        updated_goal["status"] = COMPLETE_GOAL_STATUS
        updated_goal["active_phase"] = COMPLETE_GOAL_PHASE
        updated_goal["claim_boundary"] = COMPLETE_CLAIM_BOUNDARY
        updated_goal["next_work_item"] = next_work_pointer
        for historical_key in ["wave01_operating_closeout", "goal_achieve_state"]:
            if isinstance(updated_goal.get(historical_key), dict):
                historical = dict(updated_goal[historical_key])
                if historical.get("validation_status") == "superseded_by_fresh_evaluator_insufficient_evidence":
                    historical.pop("validation_status", None)
                updated_goal[historical_key] = historical
        updated_next_work.update(
            {
                "version": updated_next_work.get("version", "onnx_lab_work_item_v1"),
                "work_item_id": COMPLETE_WORK_ITEM_ID,
                "active_goal_id": GOAL_ID,
                "status": COMPLETE_WAVE_STATUS,
                "claim_boundary": "post_wave01_handoff_no_candidate_no_runtime_authority_no_economics_pass_no_live_readiness",
                "next_action": COMPLETE_WORK_ITEM_ID,
                "next_action_detail": "Wave01 evaluator-backed closeout is complete. Continue only with user-directed Wave02, review, or a newly declared surface.",
                "next_allowed_shapes": [
                    "user_directed_wave02_open",
                    "new_unexplored_multi_axis_surface",
                    "previous_material_only_bounded_synthesis_mix2_then_mix3",
                    "post_closeout_review",
                ],
                "blocking_requirements": [],
                "blocking_findings": [],
                "missing_material_if_relevant": [],
            }
        )
        updated_cursor.update(
            {
                "version": updated_cursor.get("version", "active_goal_resume_cursor_v1"),
                "active_goal_id": GOAL_ID,
                "cursor_state": COMPLETE_GOAL_STATUS,
                "active_phase": COMPLETE_GOAL_PHASE,
                "next_work_item": {"work_item_id": COMPLETE_WORK_ITEM_ID, "path": NEXT_WORK_ITEM_PATH.as_posix()},
            }
        )
        updated_wave["status"] = COMPLETE_WAVE_STATUS
        updated_wave["claim_boundary"] = "active_goal_complete_wave01_operating_proof_only_no_candidate_no_runtime_authority_no_economics_pass_no_live_readiness"
        updated_wave["next_action"] = COMPLETE_WAVE_NEXT_ACTION
        updated_wave["next_action_detail"] = "Await user-directed Wave02, a new unexplored multi-axis campaign, previous-material-only bounded synthesis, or review."
        updated_wave.pop("wave01_operating_completion_assertion", None)
        git_integration = dict(updated_wave.get("git_integration") or {})
        git_integration["status"] = COMPLETE_GIT_STATUS
        updated_wave["git_integration"] = git_integration
    else:
        next_work_pointer = _repair_next_work()
        updated_goal["status"] = REPAIR_GOAL_STATUS
        updated_goal["active_phase"] = REPAIR_PHASE
        updated_goal["claim_boundary"] = REPAIR_CLAIM_BOUNDARY
        updated_goal["next_work_item"] = next_work_pointer
        for historical_key in ["wave01_operating_closeout", "goal_achieve_state"]:
            if isinstance(updated_goal.get(historical_key), dict):
                historical = dict(updated_goal[historical_key])
                historical["validation_status"] = "superseded_by_fresh_evaluator_insufficient_evidence"
                updated_goal[historical_key] = historical
        updated_next_work.update(
            {
                "version": updated_next_work.get("version", "onnx_lab_work_item_v1"),
                "work_item_id": REPAIR_WORK_ITEM_ID,
                "active_goal_id": GOAL_ID,
                "status": REPAIR_GOAL_STATUS,
                "claim_boundary": REPAIR_CLAIM_BOUNDARY,
                "next_action": REPAIR_NEXT_ACTION,
                "next_action_detail": "Repair failed or insufficient evaluator evidence before WP08 or main integration.",
                "next_allowed_shapes": ["closeout_evidence_repair"],
                "blocking_requirements": problem_requirements,
                "blocking_findings": blocking_finding_ids,
                "missing_material_if_relevant": _missing_material_from_blockers(blocking_finding_ids),
            }
        )
        updated_cursor.update(
            {
                "version": updated_cursor.get("version", "active_goal_resume_cursor_v1"),
                "active_goal_id": GOAL_ID,
                "cursor_state": REPAIR_GOAL_STATUS,
                "active_phase": REPAIR_PHASE,
                "next_work_item": {"work_item_id": REPAIR_WORK_ITEM_ID, "path": NEXT_WORK_ITEM_PATH.as_posix()},
            }
        )
        cursor_active_ids = dict(updated_cursor.get("active_ids") or updated_goal.get("active_ids") or {})
        cursor_active_ids["campaign_id"] = None
        updated_cursor["active_ids"] = cursor_active_ids
        updated_wave["status"] = REPAIR_WAVE_STATUS
        updated_wave["claim_boundary"] = REPAIR_CLAIM_BOUNDARY
        updated_wave["next_action"] = REPAIR_WORK_ITEM_ID
        updated_wave["next_action_detail"] = "Repair evaluator evidence before WP08 or main integration."
        git_integration = dict(updated_wave.get("git_integration") or {})
        git_integration["status"] = REPAIR_GIT_STATUS
        updated_wave["git_integration"] = git_integration
        _preserve_wave_completion_assertion(wave, updated_wave)
    current_truth = dict(updated_next_work.get("current_truth") or {})
    current_truth.update(
        {
            "active_goal_status": updated_goal["status"],
            "wave_id": closeout["wave_id"],
            "wave_closeout": closeout["source_of_truth"],
            "candidate_count": closeout["result"]["candidate_count"],
            "l5_candidate_count": closeout["result"]["l5_candidate_count"],
            "claim_boundary": updated_goal["claim_boundary"],
        }
    )
    updated_next_work["current_truth"] = current_truth

    cursor_active_ids = dict(updated_cursor.get("active_ids") or updated_goal.get("active_ids") or {})
    cursor_active_ids["campaign_id"] = None
    updated_cursor["active_ids"] = cursor_active_ids

    return {
        GOAL_MANIFEST_PATH: updated_goal,
        NEXT_WORK_ITEM_PATH: updated_next_work,
        RESUME_CURSOR_PATH: updated_cursor,
        Path("lab/waves") / str(wave["wave_id"]) / "wave_allocation.yaml": updated_wave,
    }


def _handoff(
    repo_root: Path,
    research: dict[str, Any],
    *,
    all_required_passed: bool,
    failed_or_insufficient_requirements: list[str],
    blocking_finding_ids: list[str],
    candidate_count: int | None,
    l5_candidate_count: int | None,
    locked_final_oos_used: bool | None,
) -> dict[str, Any]:
    negative_ids: set[str] = set()
    clue_ids: set[str] = set()
    for item in research.get("input_hashes") or []:
        path = str(item.get("path") or "")
        if path.startswith("lab/memory/negative/") and path.endswith(".yaml"):
            negative_ids.add(Path(path).stem)
        if path.startswith("lab/memory/clues/") and path.endswith(".yaml"):
            clue_ids.add(Path(path).stem)
    if all_required_passed:
        next_action = "work_post_wave01_user_directed_wave02_or_review_v0"
        claim_boundary = COMPLETE_CLAIM_BOUNDARY
    else:
        next_action = REPAIR_NEXT_ACTION
        claim_boundary = REPAIR_CLAIM_BOUNDARY
    return {
        "negative_memory_ids": sorted(negative_ids),
        "preserved_clue_ids": sorted(clue_ids),
        "candidate_count": candidate_count,
        "l5_candidate_count": l5_candidate_count,
        "locked_final_oos_used": locked_final_oos_used,
        "blocking_requirements": list(failed_or_insufficient_requirements),
        "blocking_findings": list(blocking_finding_ids),
        "next_action": next_action,
        "claim_boundary": claim_boundary,
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


def _compose_closeout_evaluation(
    repo_root: Path,
    *,
    existing: dict[str, Any],
    goal_path: Path,
    goal: dict[str, Any],
    wave_path: Path,
    wave: dict[str, Any],
    closeout_path: Path,
    required_entries: list[dict[str, Any]],
    result_payloads: dict[str, dict[str, Any]],
    generated_at_utc: str,
) -> CloseoutEvaluation:
    runtime = result_payloads[RUNTIME_EVALUATOR_ID]
    routing = result_payloads[ROUTING_EVALUATOR_ID]
    agent = result_payloads[AGENT_EVALUATOR_ID]
    operating = result_payloads[OPERATING_EVALUATOR_ID]
    research = result_payloads[RESEARCH_EVALUATOR_ID]
    staged_texts: dict[Path, str] = {}
    result_refs: dict[str, dict[str, Any]] = {}
    for entry in required_entries:
        evaluator_id = str(entry.get("evaluator_id") or "")
        result = result_payloads[evaluator_id]
        rel_path, text, ref = _result_ref(repo_root, entry, result)
        staged_texts[rel_path] = text
        result_refs[evaluator_id] = ref
        for alias_path in entry.get("allowed_alias_paths") or []:
            staged_texts[Path(str(alias_path))] = text

    audit = _build_audit(required_entries, result_refs)
    problem_requirements = _required_problem_requirements(audit)
    all_required_passed = not problem_requirements
    blocking_finding_ids = _blocking_finding_ids(required_entries, result_payloads)
    runtime_passed = runtime["status"] == "passed"
    research_metrics = research.get("metrics") or {}
    candidate_count = research_metrics.get("candidate_count")
    l5_candidate_count = research_metrics.get("l5_candidate_count")
    locked_final_oos_used = research_metrics.get("locked_final_oos_used")
    closeout_status = (
        "wave01_control_plane_proof_closed_runtime_contract_complete"
        if all_required_passed and runtime_passed
        else REPAIR_WAVE_STATUS
    )
    claim_boundary = COMPLETE_CLAIM_BOUNDARY if all_required_passed and runtime_passed else REPAIR_CLAIM_BOUNDARY
    next_action = (
        "work_post_wave01_user_directed_wave02_or_review_v0"
        if all_required_passed
        else REPAIR_NEXT_ACTION
    )
    active_goal_id = str(goal.get("active_goal_id") or goal.get("goal_id") or GOAL_ID)
    wave_id = str(wave.get("wave_id") or (goal.get("active_ids") or {}).get("wave_id") or "")
    wave_summary = {
        "wave_id": wave_id,
        "campaign_count": research_metrics.get("campaign_count"),
        "candidate_count": candidate_count,
        "l5_candidate_count": l5_candidate_count,
        "runtime_authority": False,
        "economics_pass": False,
        "locked_final_oos_used": locked_final_oos_used,
        "runtime_contract_integrity": runtime["status"],
        "operating_slo_status": operating["status"],
        "agent_value_status": agent["status"],
        "research_cycle_status": research["status"],
    }
    closeout = {
        "version": "wave_closeout_v2",
        "closeout_id": _derived_closeout_id(wave),
        "generated_by": "foundation.evaluation.build_operating_closeout",
        "generated_at_utc": generated_at_utc,
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
        "active_goal_id": active_goal_id,
        "wave_id": wave_id,
        "source_of_truth": closeout_path.as_posix(),
        "source_inputs": [],
        "wave_summary": wave_summary,
        "campaign_summaries": _campaign_summaries(research),
        "requirement_audit": audit,
        "evaluation_results": list(result_refs.values()),
        "handoff": _handoff(
            repo_root,
            research,
            all_required_passed=all_required_passed,
            failed_or_insufficient_requirements=problem_requirements,
            blocking_finding_ids=blocking_finding_ids,
            candidate_count=candidate_count,
            l5_candidate_count=l5_candidate_count,
            locked_final_oos_used=locked_final_oos_used,
        ),
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
        "unresolved_blockers": [] if all_required_passed else blocking_finding_ids,
        "next_action": next_action,
    }
    state_yaml_overrides = (
        _state_transition_payloads(
            repo_root,
            all_required_passed=all_required_passed,
            problem_requirements=problem_requirements,
            blocking_finding_ids=blocking_finding_ids,
            generated_at_utc=generated_at_utc,
            goal=goal,
            wave=wave,
            closeout=closeout,
        )
        if _goal_still_points_to_wave01(goal, wave)
        else {}
    )
    goal_text = _yaml_text(state_yaml_overrides.get(GOAL_MANIFEST_PATH, goal))
    wave_text = _yaml_text(state_yaml_overrides.get(wave_path, wave))
    closeout["source_inputs"] = [
        _input_hash_for_text(GOAL_MANIFEST_PATH, goal_text),
        _input_hash_for_text(wave_path, wave_text),
        input_hash(repo_root, EVALUATOR_REGISTRY_PATH.as_posix()),
        *_source_inputs(runtime, routing, agent, operating, research),
    ]
    closeout["evaluation_digest"] = _closeout_digest(closeout)
    staged_texts[closeout_path] = _yaml_text(closeout)
    for rel_path, payload in state_yaml_overrides.items():
        staged_texts[rel_path] = _yaml_text(payload)
    yaml_overrides = {
        closeout_path: closeout,
        **state_yaml_overrides,
    }
    if state_yaml_overrides:
        workspace_text = workspace_projection_text(repo_root, yaml_overrides=yaml_overrides)
        staged_texts[WORKSPACE_STATE_PATH] = workspace_text
    return CloseoutEvaluation(closeout=closeout, digest=closeout["evaluation_digest"], requirement_audit=audit, staged_texts=staged_texts)


def evaluate_operating_closeout(repo_root: Path, *, write: bool = False) -> CloseoutEvaluation:
    repo_root = repo_root.resolve()
    existing = load_yaml(repo_root / WAVE_CLOSEOUT_PATH) or {}
    generated_at_utc = evaluation_time_utc() if write or not existing.get("generated_at_utc") else str(existing["generated_at_utc"])
    goal_path, goal, wave_path, wave, closeout_path = _load_goal_and_wave(repo_root)
    required_entries = _required_evaluator_entries(repo_root)
    initial_results = _evaluate_registered_evaluators(repo_root, required_entries)
    initial = _compose_closeout_evaluation(
        repo_root,
        existing=existing,
        goal_path=goal_path,
        goal=goal,
        wave_path=wave_path,
        wave=wave,
        closeout_path=closeout_path,
        required_entries=required_entries,
        result_payloads=initial_results,
        generated_at_utc=generated_at_utc,
    )
    future_results = _evaluate_against_staged_future(repo_root, required_entries, initial.staged_texts)
    return _compose_closeout_evaluation(
        repo_root,
        existing=existing,
        goal_path=goal_path,
        goal=goal,
        wave_path=wave_path,
        wave=wave,
        closeout_path=closeout_path,
        required_entries=required_entries,
        result_payloads=future_results,
        generated_at_utc=generated_at_utc,
    )


def load_committed_closeout(repo_root: Path) -> dict[str, Any]:
    return load_yaml(repo_root / WAVE_CLOSEOUT_PATH) or {}


def validate_committed_closeout(repo_root: Path) -> list[str]:
    errors: list[str] = []
    committed = load_committed_closeout(repo_root)
    recomputed = evaluate_operating_closeout(repo_root, write=False).closeout
    required_requirements = sorted(str(entry.get("closeout_requirement") or "") for entry in _required_evaluator_entries(repo_root))
    observed_requirements = sorted(str(item.get("requirement") or "") for item in committed.get("requirement_audit") or [])
    if observed_requirements != required_requirements:
        errors.append(f"committed closeout requirement_audit does not match evaluator registry required set: expected {required_requirements}, observed {observed_requirements}")
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

    errors.extend(f"registry projection drift: {item}" for item in projection_diffs(future_root))
    if workspace_projection_diff(future_root):
        errors.append("workspace projection drift")
    errors.extend(validate_execution_provenance(future_root))
    errors.extend(validate_control_plane(future_root, include_active_records=False))
    errors.extend(validate_active_records(future_root))
    registry_report = refresh_registry(future_root, future_root / ARTIFACT_REGISTRY_PATH, write=False)
    errors.extend(f"artifact registry missing path: {path}" for path in registry_report.missing_paths)
    errors.extend(f"artifact registry hash drift: {change.artifact_id}" for change in registry_report.changed_rows)
    return errors


def _artifact_type_for_path(rel_path: Path) -> str:
    text = rel_path.as_posix()
    if text.startswith("lab/evaluations/"):
        return "evaluator_result"
    if text.endswith("wave_closeout.yaml"):
        return "control_plane_closeout"
    if text == WORKSPACE_STATE_PATH.as_posix():
        return "workspace_projection"
    if text == EVALUATOR_REGISTRY_PATH.as_posix():
        return "evaluator_registry"
    if text.startswith("lab/goals/"):
        return "goal_state"
    return "control_plane_state"


def _extra_artifacts(repo_root: Path, staged_texts: dict[Path, str], *, claim_boundary: str) -> list[dict[str, str]]:
    artifacts = []
    for rel_path, text in sorted(staged_texts.items(), key=lambda item: item[0].as_posix()):
        if rel_path == ARTIFACT_REGISTRY_PATH or rel_path.as_posix().startswith("docs/registers/"):
            continue
        artifacts.append(
            artifact_row_for_text(
                rel_path,
                text,
                artifact_type=_artifact_type_for_path(rel_path),
                producer_command="python foundation/evaluation/build_operating_closeout.py --repo-root . --write",
                regeneration_command="python foundation/evaluation/build_operating_closeout.py --repo-root . --write",
                source_of_truth=rel_path.as_posix(),
                consumer="wave01_operating_closeout",
                claim_boundary=claim_boundary,
                notes="WP07 evaluator-backed state-consistency artifact.",
            )
        )
    evaluator_registry_path = repo_root / EVALUATOR_REGISTRY_PATH
    if evaluator_registry_path.exists() and EVALUATOR_REGISTRY_PATH not in staged_texts:
        registry_text = evaluator_registry_path.read_text(encoding="utf-8")
        artifacts.append(
            artifact_row_for_text(
                EVALUATOR_REGISTRY_PATH,
                registry_text,
                artifact_type="evaluator_registry",
                producer_command="manual_control_plane_policy",
                regeneration_command="python foundation/evaluation/fresh_evaluator_validator.py --repo-root .",
                source_of_truth=EVALUATOR_REGISTRY_PATH.as_posix(),
                consumer="fresh_evaluator_validator",
                claim_boundary=claim_boundary,
                notes="Authoritative evaluator registry for WP07 closeout validation.",
            )
        )
    return artifacts


def _yaml_overrides_from_staged(staged_texts: dict[Path, str]) -> dict[Path, dict[str, Any]]:
    overrides: dict[Path, dict[str, Any]] = {}
    for rel_path, text in staged_texts.items():
        if rel_path.suffix.lower() not in {".yaml", ".yml"}:
            continue
        loaded = yaml.safe_load(text)
        if isinstance(loaded, dict):
            overrides[Path(rel_path.as_posix())] = loaded
    return overrides


def _write_staged_texts(repo_root: Path, staged_texts: dict[Path, str]) -> None:
    for rel_path, text in staged_texts.items():
        path = repo_root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


def _evaluate_against_staged_future(
    repo_root: Path,
    entries: list[dict[str, Any]],
    staged_texts: dict[Path, str],
) -> dict[str, dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="spacesonar_closeout_eval_future_") as tmp:
        future_root = Path(tmp) / "repo"
        shutil.copytree(
            filesystem_path(repo_root),
            filesystem_path(future_root),
            ignore=shutil.ignore_patterns(".git", ".spacesonar", ".venv", "__pycache__"),
        )
        _write_staged_texts(future_root, staged_texts)
        for rel_path, text in project_registries(future_root).items():
            path = future_root / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
        return _evaluate_registered_evaluators(future_root, entries)


def write_operating_closeout_transaction(
    repo_root: Path,
    *,
    fail_after_replace_count: int | None = None,
) -> TransactionResult:
    evaluation = evaluate_operating_closeout(repo_root, write=True)
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
    _stage_registry_projections(
        tx,
        context.repo_root,
        yaml_overrides=_yaml_overrides_from_staged(evaluation.staged_texts),
        text_overrides=evaluation.staged_texts,
        extra_artifacts=_extra_artifacts(context.repo_root, evaluation.staged_texts, claim_boundary=evaluation.closeout["claim_boundary"]),
    )
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
