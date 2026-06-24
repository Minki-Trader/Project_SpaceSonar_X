from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation.evaluation.agent_value_evaluator import EVALUATOR_ID as AGENT_EVALUATOR_ID
from foundation.evaluation.agent_value_evaluator import evaluate_agent_value
from foundation.evaluation.common import evaluation_time_utc, load_yaml, stable_sha256, write_yaml
from foundation.evaluation.fresh_evaluator_validator import compare_committed_evaluator_file
from foundation.evaluation.operating_slo_evaluator import EVALUATOR_ID as OPERATING_EVALUATOR_ID
from foundation.evaluation.operating_slo_evaluator import evaluate_operating_slo
from foundation.evaluation.research_cycle_closeout_evaluator import EVALUATOR_ID as RESEARCH_EVALUATOR_ID
from foundation.evaluation.research_cycle_closeout_evaluator import evaluate_research_cycle_closeout
from foundation.evaluation.routing_quality_evaluator import EVALUATOR_ID as ROUTING_EVALUATOR_ID
from foundation.evaluation.routing_quality_evaluator import evaluate_routing_quality
from foundation.evaluation.runtime_contract_evaluator import EVALUATOR_ID as RUNTIME_EVALUATOR_ID
from foundation.evaluation.runtime_contract_evaluator import evaluate_runtime_contract


WAVE_CLOSEOUT_PATH = Path("lab/waves/wave_us100_closedbar_surface_cartography_v0/wave_closeout.yaml")
EVALUATION_DIR = Path("lab/evaluations/control_plane_stabilization_v2")
INCOMPLETE_CLAIM_BOUNDARY = (
    "control_plane_stabilization_validated_runtime_contract_incomplete_no_runtime_authority_"
    "no_economics_pass_no_live_readiness_no_selected_baseline"
)
COMPLETE_CLAIM_BOUNDARY = (
    "control_plane_stabilization_validated_standard_l4_runtime_contract_complete_"
    "no_runtime_authority_no_economics_pass_no_live_readiness_no_selected_baseline"
)


@dataclass(frozen=True)
class CloseoutEvaluation:
    closeout: dict[str, Any]
    digest: str
    requirement_audit: list[dict[str, Any]]


def _result_path(evaluator_id: str) -> Path:
    return EVALUATION_DIR / f"{evaluator_id}.yaml"


def _write_result(repo_root: Path, evaluator_id: str, result: dict[str, Any], *, write: bool) -> dict[str, Any]:
    rel_path = _result_path(evaluator_id)
    if write:
        write_yaml(repo_root / rel_path, result)
    return {
        "evaluator_id": evaluator_id,
        "evaluator_result_path": rel_path.as_posix(),
        "evaluator_result_sha256": result["output_sha256"],
        "status": result["status"],
    }


def _summary_status(*, operating_status: str, research_status: str, runtime_status: str) -> dict[str, Any]:
    return {
        "control_plane_operating_proof": operating_status,
        "research_cycle_closeout": research_status,
        "runtime_contract_integrity": runtime_status,
        "runtime_authority": "not_claimed",
        "economics_pass": "not_claimed",
        "candidate_count": 0,
        "l5_candidate_count": 0,
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


def _closeout_digest(closeout: dict[str, Any]) -> str:
    payload = {
        "result": closeout["result"],
        "wave_summary": closeout["wave_summary"],
        "requirement_audit": closeout["requirement_audit"],
        "claim_boundary": closeout["claim_boundary"],
        "not_claimed": closeout["not_claimed"],
    }
    return stable_sha256(payload)


def evaluate_operating_closeout(repo_root: Path, *, write: bool = False) -> CloseoutEvaluation:
    existing = load_yaml(repo_root / WAVE_CLOSEOUT_PATH) or {}
    runtime = evaluate_runtime_contract(repo_root)
    routing = evaluate_routing_quality(repo_root)
    agent = evaluate_agent_value(repo_root)
    operating = evaluate_operating_slo(repo_root)
    research = evaluate_research_cycle_closeout(repo_root)
    result_refs = {
        RUNTIME_EVALUATOR_ID: _write_result(repo_root, RUNTIME_EVALUATOR_ID, runtime, write=write),
        ROUTING_EVALUATOR_ID: _write_result(repo_root, ROUTING_EVALUATOR_ID, routing, write=write),
        AGENT_EVALUATOR_ID: _write_result(repo_root, AGENT_EVALUATOR_ID, agent, write=write),
        OPERATING_EVALUATOR_ID: _write_result(repo_root, OPERATING_EVALUATOR_ID, operating, write=write),
        RESEARCH_EVALUATOR_ID: _write_result(repo_root, RESEARCH_EVALUATOR_ID, research, write=write),
    }

    audit = _build_audit(result_refs)
    wave_summary = existing.get("wave_summary") or {}
    wave_summary.update(
        {
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "runtime_authority": False,
            "economics_pass": False,
            "runtime_contract_integrity": runtime["status"],
        }
    )
    runtime_passed = runtime["status"] == "passed"
    claim_boundary = COMPLETE_CLAIM_BOUNDARY if runtime_passed else INCOMPLETE_CLAIM_BOUNDARY
    closeout_status = (
        "wave01_control_plane_proof_closed_runtime_contract_complete"
        if runtime_passed
        else "wave01_control_plane_proof_closed_runtime_contract_incomplete"
    )
    runtime_contract_judgment = "complete" if runtime_passed else "incomplete"
    runtime_reason = (
        "all recorded Wave0/Wave01 L4 attempts have portable terminal execution, telemetry rows, and archived tester reports"
        if runtime_passed
        else "standard tester reports and portable contract completion are not present for all L4 attempts"
    )
    handoff = existing.get("handoff", {})
    if runtime_passed:
        handoff = dict(handoff)
        handoff["unresolved_risks"] = [
            risk
            for risk in handoff.get("unresolved_risks", [])
            if risk not in {
                "tester_reports_missing_for_score_and_decision_replay_attempts",
                "report_or_equity_parser_improvement_before_any_economics_claim",
            }
        ]

    closeout = {
        "version": "wave_closeout_v2",
        "closeout_id": existing.get("closeout_id", "wave01_operating_closeout_v0"),
        "generated_by": "foundation.evaluation.build_operating_closeout",
        "generated_at_utc": evaluation_time_utc(),
        "status": closeout_status,
        "result": _summary_status(
            operating_status=operating["status"],
            research_status=research["status"],
            runtime_status=runtime["status"],
        ),
        "result_judgment": {
            "control_plane": "positive",
            "runtime_contract": runtime_contract_judgment,
            "research_outcome": "no_candidate_with_negative_memory_and_preserved_clues",
        },
        "claim_boundary": claim_boundary,
        "active_goal_id": existing.get("active_goal_id", "goal_us100_onnx_forward_boundary_v0"),
        "wave_id": existing.get("wave_id", "wave_us100_closedbar_surface_cartography_v0"),
        "source_of_truth": WAVE_CLOSEOUT_PATH.as_posix(),
        "source_inputs": existing.get("source_inputs", []),
        "wave_summary": wave_summary,
        "campaign_summaries": existing.get("campaign_summaries", []),
        "requirement_audit": audit,
        "evaluation_results": list(result_refs.values()),
        "handoff": handoff,
        "runtime_contract_integrity": {
            "status": runtime["status"],
            "reason": runtime_reason,
            "runtime_authority": False,
            "economics_pass": False,
            "evaluator_id": RUNTIME_EVALUATOR_ID,
            "evaluator_result_path": result_refs[RUNTIME_EVALUATOR_ID]["evaluator_result_path"],
            "evaluator_result_sha256": result_refs[RUNTIME_EVALUATOR_ID]["evaluator_result_sha256"],
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
        "next_action": "work_post_wave01_user_directed_wave02_or_review_v0",
    }
    closeout["evaluation_digest"] = _closeout_digest(closeout)
    if write:
        write_yaml(repo_root / WAVE_CLOSEOUT_PATH, closeout)
    return CloseoutEvaluation(closeout=closeout, digest=closeout["evaluation_digest"], requirement_audit=audit)


def load_committed_closeout(repo_root: Path) -> dict[str, Any]:
    return load_yaml(repo_root / WAVE_CLOSEOUT_PATH) or {}


def validate_committed_closeout(repo_root: Path) -> list[str]:
    errors: list[str] = []
    committed = load_committed_closeout(repo_root)
    recomputed = evaluate_operating_closeout(repo_root, write=False)
    for item in committed.get("requirement_audit") or []:
        required = {"requirement", "evaluator_id", "evaluator_result_path", "evaluator_result_sha256", "status"}
        missing = required - set(item)
        if missing:
            errors.append(f"closeout requirement {item.get('requirement')}: missing evaluator fields {sorted(missing)}")
        if item.get("status") == "passed" and not item.get("evaluator_id"):
            errors.append(f"closeout requirement {item.get('requirement')}: self-attested passed status")
        rel_path = item.get("evaluator_result_path")
        if rel_path:
            evaluator_path = repo_root / rel_path
            if not evaluator_path.exists():
                errors.append(f"closeout requirement {item.get('requirement')}: missing evaluator result {rel_path}")
            else:
                evaluator_payload = load_yaml(evaluator_path) or {}
                if evaluator_payload.get("evaluator_id") != item.get("evaluator_id"):
                    errors.append(f"closeout requirement {item.get('requirement')}: evaluator_id mismatch")
                if evaluator_payload.get("status") != item.get("status"):
                    errors.append(f"closeout requirement {item.get('requirement')}: evaluator status mismatch")
                if evaluator_payload.get("output_sha256") != item.get("evaluator_result_sha256"):
                    errors.append(f"closeout requirement {item.get('requirement')}: evaluator output_sha256 mismatch")
                errors.extend(compare_committed_evaluator_file(repo_root, evaluator_path))
    if committed.get("evaluation_digest") != recomputed.digest:
        errors.append("committed closeout evaluation_digest does not match recomputed digest")
    if committed.get("requirement_audit") != recomputed.requirement_audit:
        errors.append("committed closeout requirement_audit does not match recomputed evaluator audit")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    if args.write:
        evaluation = evaluate_operating_closeout(repo_root, write=True)
        print(f"wrote {WAVE_CLOSEOUT_PATH.as_posix()} evaluation_digest={evaluation.digest}")
        return 0
    if args.check:
        errors = validate_committed_closeout(repo_root)
        if errors:
            for error in errors:
                print(f"ERROR: {error}")
            return 1
        print("operating closeout validation passed")
        return 0
    evaluation = evaluate_operating_closeout(repo_root, write=False)
    print(evaluation.closeout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
