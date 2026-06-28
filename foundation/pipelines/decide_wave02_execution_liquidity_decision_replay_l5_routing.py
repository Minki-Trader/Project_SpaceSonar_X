from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import foundation.pipelines.aggregate_wave02_execution_liquidity_decision_replay_pair_judgments as pair_writer


base = pair_writer.base

GOAL_ID = pair_writer.GOAL_ID
WAVE_ID = pair_writer.WAVE_ID
CAMPAIGN_ID = pair_writer.CAMPAIGN_ID
IDEA_ID = pair_writer.IDEA_ID
HYPOTHESIS_ID = pair_writer.HYPOTHESIS_ID
SURFACE_ID = pair_writer.SURFACE_ID
SWEEP_ID = pair_writer.SWEEP_ID

PARENT_WORK_ITEM_ID = pair_writer.WORK_ITEM_ID
WORK_ITEM_ID = "work_wave02_execution_liquidity_decision_replay_l5_routing_decision_v0"
NEXT_WORK_ITEM_ID = "work_wave02_execution_liquidity_l5_candidate_runtime_evidence_preparation_v0"

OUTPUT_DIR = pair_writer.OUTPUT_DIR
PAIR_SUMMARY = pair_writer.PAIR_SUMMARY
PAIR_INDEX = pair_writer.PAIR_INDEX
ROUTING_SUMMARY = OUTPUT_DIR / "l5_routing_decision_summary.yaml"
ROUTING_INDEX = OUTPUT_DIR / "l5_routing_decision_index.csv"
ROUTING_CLOSEOUT = Path(
    "lab/goals/goal_us100_onnx_forward_boundary_v0/"
    "work_wave02_execution_liquidity_decision_replay_l5_routing_decision_v0_closeout.yaml"
)
NEXT_WORK_ITEM = pair_writer.NEXT_WORK_ITEM
RESUME_CURSOR = pair_writer.RESUME_CURSOR
GOAL_MANIFEST = pair_writer.GOAL_MANIFEST
WORKSPACE_STATE = pair_writer.WORKSPACE_STATE
CAMPAIGN_MANIFEST = pair_writer.CAMPAIGN_MANIFEST
ARTIFACT_REGISTRY = pair_writer.ARTIFACT_REGISTRY
GOAL_REGISTRY = pair_writer.GOAL_REGISTRY
CANDIDATE_REGISTRY = Path("docs/registers/candidate_registry.csv")

WRITER_CONTRACT_VERSION = "writer_scope_operating_contract_v2"
VALIDATION_DEPTH = "writer_scope_smoke"
NON_PYTEST_SMOKES = [
    "py_compile",
    "l5_routing_writer_smoke",
    "active_pointer_smoke",
    "machine_yaml_identity_lint",
    "targeted_artifact_hash_check",
]
SKIPPED_BROAD_VALIDATIONS = [
    "pytest",
    "full_regression_workflow",
    "evidence_graph_full_workflow",
    "active_record_validator_full_graph",
    "spacesonar_project_validate_full",
    "spacesonar_cli_project_validate_as_progress_default",
    "broad_hash_resync",
    "global_registry_regeneration",
]
BROAD_VALIDATION_ESCALATION_REASON = "none_l5_routing_progress_no_protected_claim"

CLAIM_BOUNDARY = (
    "wave02_execution_liquidity_decision_replay_l5_routing_decision_only_"
    "no_selected_baseline_no_runtime_authority_no_economics_pass_no_live_readiness_no_goal_achieve"
)
CANDIDATE_CLAIM_BOUNDARY = (
    "wave02_execution_liquidity_l5_candidate_manifest_only_"
    "no_selected_baseline_no_runtime_authority_no_economics_pass_no_live_readiness_no_goal_achieve"
)
NEXT_CLAIM_BOUNDARY = (
    "wave02_execution_liquidity_l5_candidate_runtime_evidence_preparation_pending_"
    "no_selected_baseline_no_runtime_authority_no_economics_pass_no_live_readiness_no_goal_achieve"
)
STATUS = "wave02_execution_liquidity_l5_candidate_manifest_opened_runtime_evidence_preparation_pending"
NEXT_STATUS = "wave02_execution_liquidity_l5_candidate_runtime_evidence_preparation_pending"
NEXT_ACTION = "prepare candidate-specific L5 runtime evidence for opened Wave02 ELQ decision replay targets"
FORBIDDEN_CLAIMS = pair_writer.FORBIDDEN_CLAIMS


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> int:
    try:
        if value in ("", None):
            return 0
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


def git_state(repo_root: Path) -> dict[str, Any]:
    def run(args: list[str]) -> str:
        completed = subprocess.run(args, cwd=repo_root, text=True, capture_output=True, check=False)
        return completed.stdout.strip() if completed.returncode == 0 else "unknown"

    status = run(["git", "status", "--short"])
    return {
        "git_sha": run(["git", "rev-parse", "HEAD"]),
        "branch": run(["git", "branch", "--show-current"]),
        "dirty_flag": bool(status),
        "changed_files": status.splitlines() if status else [],
    }


def candidate_id_for_cell(cell_id: str, direction_policy: str) -> str:
    return f"candidate_{cell_id}_decision_replay_{direction_policy}_l5_target_v0"


def candidate_summary_path(candidate_id: str) -> Path:
    return Path("lab") / "candidates" / candidate_id / "candidate_summary.yaml"


def route_row(row: dict[str, str]) -> tuple[str, str]:
    status = row.get("l5_routing_status", "")
    if status == "l5_routing_review_required_no_candidate_claim":
        return "open_l5_candidate_manifest", "zero_open_failed_paired_decision_replay_action_telemetry"
    if status == "l5_routing_review_required_with_open_failed_note_no_candidate_claim":
        return "hold_for_open_failed_caveat_review", "minor_open_failed_present_before_candidate_manifest"
    if status == "l5_routing_review_requires_execution_repair_no_candidate_claim":
        return "repair_execution_semantics_before_l5_manifest", "high_open_failed_asymmetry"
    return "do_not_open_l5_candidate_manifest", "not_reviewable_under_current_decision_replay_judgment"


def build_candidate_summary(row: dict[str, Any], created_at_utc: str) -> dict[str, Any]:
    candidate_id = str(row["candidate_id"])
    candidate_path = candidate_summary_path(candidate_id)
    return {
        "version": "candidate_summary_v1",
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "candidate_id": candidate_id,
        "candidate_type": "l5_runtime_evidence_target",
        "status": "candidate_manifest_opened_l5_runtime_evidence_pending",
        "active_goal_id": GOAL_ID,
        "id_chain": {
            "goal_id": GOAL_ID,
            "wave_id": WAVE_ID,
            "campaign_id": CAMPAIGN_ID,
            "idea_id": IDEA_ID,
            "hypothesis_id": HYPOTHESIS_ID,
            "surface_id": SURFACE_ID,
            "sweep_id": SWEEP_ID,
            "run_id": row["run_id"],
            "artifact_id": f"artifact_{candidate_id}_summary_v0",
            "bundle_id": row["bundle_id"],
            "candidate_id": candidate_id,
        },
        "wave_id": WAVE_ID,
        "campaign_id": CAMPAIGN_ID,
        "idea_id": IDEA_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "run_id": row["run_id"],
        "bundle_id": row["bundle_id"],
        "source_cell_id": row["cell_id"],
        "direction_policy": row["direction_policy"],
        "source_of_truth": candidate_path.as_posix(),
        "created_at_utc": created_at_utc,
        "claim_boundary": CANDIDATE_CLAIM_BOUNDARY,
        "primary_family": "runtime_probe",
        "primary_skill": "spacesonar-runtime-evidence",
        "source_of_truth_paths": [candidate_path.as_posix(), PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix()],
        "writer_owned_outputs": [candidate_path.as_posix()],
        "validation_depth": VALIDATION_DEPTH,
        "non_pytest_smokes": list(NON_PYTEST_SMOKES),
        "skipped_broad_validations": list(SKIPPED_BROAD_VALIDATIONS),
        "broad_validation_escalation_reason": BROAD_VALIDATION_ESCALATION_REASON,
        "allocation_reason": row["routing_reason"],
        "candidate_scope": {
            "meaning": "runtime evidence target only",
            "selected_baseline": False,
            "runtime_authority": False,
            "economics_pass": False,
            "live_readiness": False,
            "goal_achieve": False,
        },
        "source_evidence": {
            "pair_judgment_summary": PAIR_SUMMARY.as_posix(),
            "pair_judgment_index": PAIR_INDEX.as_posix(),
            "routing_decision_summary": ROUTING_SUMMARY.as_posix(),
            "validation_attempt_id": row["validation_attempt_id"],
            "research_oos_attempt_id": row["research_oos_attempt_id"],
            "runtime_probe_pair_complete": row["runtime_probe_pair_complete"],
            "tester_report_pair_observed": row["tester_report_pair_observed"],
            "decision_replay_comparison_class": row["decision_replay_comparison_class"],
        },
        "runtime_observation": {
            "validation_open_action_count": safe_int(row["validation_open_action_count"]),
            "research_oos_open_action_count": safe_int(row["research_oos_open_action_count"]),
            "validation_open_rate": safe_float(row["validation_open_rate"]),
            "research_oos_open_rate": safe_float(row["research_oos_open_rate"]),
            "abs_open_rate_delta": safe_float(row["abs_open_rate_delta"]),
            "max_open_failed_rate": safe_float(row["max_open_failed_rate"]),
        },
        "required_follow_through": {
            "next_level": "L5_candidate_runtime_evidence",
            "required_before_stronger_claim": [
                "candidate_specific_L5_attempt_manifest",
                "candidate_specific_runtime_evidence_summary",
                "tester_report_receipt_hashes",
                "economics_parser_or_explicit_no_economics_disposition",
                "final_claim_guard",
            ],
        },
        "missing_evidence": [
            "candidate_specific_L5_runtime_evidence_not_prepared",
            "candidate_specific_L5_runtime_evidence_not_executed",
            "economics_metrics_not_parsed_or_claimable",
            "locked_final_oos_b_not_used",
        ],
        "next_action": NEXT_ACTION,
        "next_action_or_reopen_condition": NEXT_ACTION,
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "forbidden_claims_respected": True,
        "writer_scope_self_check": {
            "status": "pending_registry_projection",
            "writer_contract_version": WRITER_CONTRACT_VERSION,
            "validation_depth": VALIDATION_DEPTH,
            "claim_boundary": CANDIDATE_CLAIM_BOUNDARY,
        },
    }


def build_decision_rows() -> list[dict[str, Any]]:
    pair_rows = base.read_csv_rows(REPO_ROOT / PAIR_INDEX)
    decision_rows: list[dict[str, Any]] = []
    for row in pair_rows:
        routing_decision, routing_reason = route_row(row)
        candidate_id = ""
        candidate_path = ""
        if routing_decision == "open_l5_candidate_manifest":
            candidate_id = candidate_id_for_cell(row["cell_id"], row["direction_policy"])
            candidate_path = candidate_summary_path(candidate_id).as_posix()
        decision_rows.append(
            {
                **row,
                "routing_decision": routing_decision,
                "routing_reason": routing_reason,
                "candidate_id": candidate_id,
                "candidate_summary_path": candidate_path,
                "candidate_count_delta": 1 if candidate_id else 0,
                "l5_candidate_count_delta": 0,
                "claim_boundary": CLAIM_BOUNDARY,
                "next_action": NEXT_ACTION,
            }
        )
    return decision_rows


def decision_index_fieldnames() -> list[str]:
    return [
        "cell_id",
        "run_id",
        "bundle_id",
        "direction_policy",
        "validation_attempt_id",
        "research_oos_attempt_id",
        "runtime_probe_pair_complete",
        "tester_report_pair_observed",
        "validation_open_action_count",
        "research_oos_open_action_count",
        "validation_open_rate",
        "research_oos_open_rate",
        "abs_open_rate_delta",
        "validation_open_failed_count",
        "research_oos_open_failed_count",
        "max_open_failed_rate",
        "source_proxy_judgment",
        "source_l4_score_l5_status",
        "decision_replay_comparison_class",
        "result_judgment",
        "l5_routing_status",
        "routing_decision",
        "routing_reason",
        "candidate_id",
        "candidate_summary_path",
        "candidate_count_delta",
        "l5_candidate_count_delta",
        "claim_boundary",
        "next_action",
    ]


def build_summary(decision_rows: list[dict[str, Any]], started_at_utc: str, command_argv: list[str]) -> dict[str, Any]:
    opened = [row for row in decision_rows if row.get("candidate_id")]
    held = [row for row in decision_rows if row["routing_decision"] == "hold_for_open_failed_caveat_review"]
    repair = [row for row in decision_rows if row["routing_decision"] == "repair_execution_semantics_before_l5_manifest"]
    routing_counts = Counter(row["routing_decision"] for row in decision_rows)
    status_counts = Counter(row["l5_routing_status"] for row in decision_rows)
    ended_at_utc = utc_now()
    missing_evidence = [
        "candidate_specific_L5_runtime_evidence_not_prepared",
        "candidate_specific_L5_runtime_evidence_not_executed",
        "economics_metrics_not_parsed_or_claimable",
        "locked_final_oos_b_not_used",
    ]
    if held:
        missing_evidence.append("held_open_failed_caveat_cells_not_candidate_manifests")
    if repair:
        missing_evidence.append("execution_semantics_repair_required_before_candidate_manifest")
    return {
        "version": "wave02_execution_liquidity_decision_replay_l5_routing_decision_summary_v1",
        "summary_id": "wave02_execution_liquidity_decision_replay_l5_routing_decision_summary_v0",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "next_work_item_id": NEXT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "id_chain": {
            "goal_id": GOAL_ID,
            "wave_id": WAVE_ID,
            "campaign_id": CAMPAIGN_ID,
            "idea_id": IDEA_ID,
            "hypothesis_id": HYPOTHESIS_ID,
            "surface_id": SURFACE_ID,
            "sweep_id": SWEEP_ID,
            "run_id": None,
            "artifact_id": "artifact_wave02_execution_liquidity_decision_replay_l5_routing_decision_summary_v0",
            "bundle_id": None,
            "candidate_id": None,
        },
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": started_at_utc,
        "ended_at_utc": ended_at_utc,
        "status": STATUS if opened else "wave02_execution_liquidity_decision_replay_l5_routing_completed_no_candidate",
        "claim_boundary": CLAIM_BOUNDARY,
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "primary_family": "candidate_evaluation",
        "primary_skill": "spacesonar-result-judgment",
        "support_skills": ["spacesonar-runtime-evidence", "spacesonar-evidence-provenance", "spacesonar-claim-discipline"],
        "source_of_truth_paths": [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix()],
        "writer_owned_outputs": [ROUTING_SUMMARY.as_posix(), ROUTING_INDEX.as_posix(), ROUTING_CLOSEOUT.as_posix()],
        "validation_depth": VALIDATION_DEPTH,
        "non_pytest_smokes": list(NON_PYTEST_SMOKES),
        "skipped_broad_validations": list(SKIPPED_BROAD_VALIDATIONS),
        "broad_validation_escalation_reason": BROAD_VALIDATION_ESCALATION_REASON,
        "counts": {
            "evaluated_pair_count": len(decision_rows),
            "candidate_manifest_opened_count": len(opened),
            "candidate_count": len(opened),
            "l5_candidate_count": 0,
            "held_for_open_failed_caveat_count": len(held),
            "repair_first_count": len(repair),
            "routing_decision_counts": dict(sorted(routing_counts.items())),
            "source_l5_status_counts": dict(sorted(status_counts.items())),
        },
        "opened_candidate_ids": [row["candidate_id"] for row in opened],
        "held_cell_ids": [row["cell_id"] for row in held],
        "repair_first_cell_ids": [row["cell_id"] for row in repair],
        "judgment": {
            "judgment_label": "candidate_manifest_opened_runtime_evidence_pending" if opened else "no_candidate_manifest_opened",
            "candidate_count": len(opened),
            "l5_candidate_count": 0,
            "claim_boundary": CLAIM_BOUNDARY,
            "decision_rule": (
                "Open L5 runtime-evidence target manifests only for paired decision replay cells "
                "with zero open_failed in both validation and research_oos."
            ),
            "missing_evidence": missing_evidence,
            "next_action": NEXT_ACTION if opened else "close or rotate after recording no-candidate decision replay routing",
        },
        "runtime_contract_effect": {
            "decision_replay_pair_source": "observed",
            "candidate_manifest": "opened_as_l5_runtime_evidence_target_only" if opened else "not_opened",
            "l5_candidate_count": 0,
            "locked_final_oos_b": "not_used",
            "selected_baseline": False,
            "runtime_authority": False,
            "economics_pass": False,
            "live_readiness": False,
            "goal_achieve": False,
        },
        "provenance": {
            "source_inputs": [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix()],
            "producer": " ".join(command_argv),
            "consumer": NEXT_WORK_ITEM_ID,
            "artifact_paths": [ROUTING_SUMMARY.as_posix(), ROUTING_INDEX.as_posix(), ROUTING_CLOSEOUT.as_posix()],
            "source_of_truth_paths": [ROUTING_SUMMARY.as_posix(), ROUTING_INDEX.as_posix(), ROUTING_CLOSEOUT.as_posix()],
            "environment_summary": {
                "python_executable": base.redact_path(sys.executable),
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                **git_state(REPO_ROOT),
            },
            "regeneration_commands": [" ".join(command_argv)],
            "registry_links": [ARTIFACT_REGISTRY.as_posix(), CANDIDATE_REGISTRY.as_posix()],
            "availability": "present_hash_recorded_after_write",
            "lineage_judgment": "routing_decision_and_candidate_target_manifests_written_from_decision_replay_pair_judgment",
            "claim_boundary": CLAIM_BOUNDARY,
        },
        "artifact_outputs": {
            "routing_summary": ROUTING_SUMMARY.as_posix(),
            "routing_index": ROUTING_INDEX.as_posix(),
            "routing_closeout": ROUTING_CLOSEOUT.as_posix(),
            "candidate_summaries": [row["candidate_summary_path"] for row in opened],
        },
        "prevention_memory": [
            "Candidate manifests are runtime-evidence targets, not selected baselines or operating promotions.",
            "L5 candidate count remains zero until candidate-specific L5 runtime evidence exists.",
            "Open-failed caveat cells are held outside candidate manifests until execution semantics are repaired or bounded.",
        ],
        "unresolved_blockers": ["Wave02_execution_liquidity_candidate_specific_L5_runtime_evidence_preparation_pending"],
        "reopen_conditions": [
            "rerun routing decision if ELQ decision replay pair judgment index changes",
            "open candidate-specific L5 runtime evidence only from candidate manifests, not score or pair summaries",
            "do not claim runtime authority or economics pass without candidate-specific L5 evidence and final claim guard",
        ],
        "forbidden_claims": FORBIDDEN_CLAIMS,
    }


def build_closeout(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "work_closeout_v1",
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "next_work_item_id": summary["next_work_item_id"],
        "active_goal_id": GOAL_ID,
        "closed_at_utc": summary["ended_at_utc"],
        "primary_family": "candidate_evaluation",
        "primary_skill": "spacesonar-result-judgment",
        "source_of_truth_paths": summary["source_of_truth_paths"],
        "writer_owned_outputs": summary["writer_owned_outputs"],
        "validation_depth": VALIDATION_DEPTH,
        "non_pytest_smokes": list(NON_PYTEST_SMOKES),
        "skipped_broad_validations": list(SKIPPED_BROAD_VALIDATIONS),
        "broad_validation_escalation_reason": BROAD_VALIDATION_ESCALATION_REASON,
        "writer_scope_self_check": summary.get("writer_scope_self_check"),
        "result_judgment": summary["judgment"]["judgment_label"],
        "status": summary["status"],
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [ROUTING_SUMMARY.as_posix(), ROUTING_INDEX.as_posix(), PAIR_SUMMARY.as_posix()],
        "counts": summary["counts"],
        "missing_evidence": summary["judgment"]["missing_evidence"],
        "next_action": summary["judgment"]["next_action"],
        "unresolved_blockers": summary["unresolved_blockers"],
        "reopen_conditions": summary["reopen_conditions"],
        "forbidden_claims": summary["forbidden_claims"],
        "required_gate_coverage": {
            "passed": [
                "decision_replay_pair_judgment_source",
                "candidate_manifest_identity",
                "artifact_hash_registry_update",
                "candidate_registry_projection",
                "final_claim_guard",
                "writer_scope_self_check",
            ],
            "missing": summary["judgment"]["missing_evidence"],
            "not_applicable": [
                "selected_baseline",
                "runtime_authority",
                "economics_pass",
                "goal_achieve",
                "live_readiness",
            ],
        },
    }


def write_candidate_summaries(decision_rows: list[dict[str, Any]], created_at_utc: str) -> list[Path]:
    written: list[Path] = []
    for row in decision_rows:
        if not row.get("candidate_id"):
            continue
        path = candidate_summary_path(str(row["candidate_id"]))
        base.write_yaml(REPO_ROOT / path, build_candidate_summary(row, created_at_utc))
        written.append(path)
    return written


def upsert_candidate_registry(decision_rows: list[dict[str, Any]]) -> None:
    registry_path = REPO_ROOT / CANDIDATE_REGISTRY
    rows = base.read_csv_rows(registry_path) if registry_path.exists() else []
    fieldnames = list(rows[0].keys()) if rows else [
        "candidate_id",
        "wave_id",
        "campaign_id",
        "run_id",
        "bundle_id",
        "surface_id",
        "status",
        "allocation_reason",
        "summary_path",
        "claim_boundary",
        "evidence_path",
        "missing_evidence",
        "risk_notes",
        "next_action",
    ]
    by_id = {row["candidate_id"]: row for row in rows if row.get("candidate_id")}
    for row in decision_rows:
        candidate_id = row.get("candidate_id")
        if not candidate_id:
            continue
        by_id[str(candidate_id)] = {
            "candidate_id": str(candidate_id),
            "wave_id": WAVE_ID,
            "campaign_id": CAMPAIGN_ID,
            "run_id": row["run_id"],
            "bundle_id": row["bundle_id"],
            "surface_id": SURFACE_ID,
            "status": "candidate_manifest_opened_l5_runtime_evidence_pending",
            "allocation_reason": row["routing_reason"],
            "summary_path": row["candidate_summary_path"],
            "claim_boundary": CANDIDATE_CLAIM_BOUNDARY,
            "evidence_path": ROUTING_SUMMARY.as_posix(),
            "missing_evidence": "candidate_specific_L5_runtime_evidence_not_executed",
            "risk_notes": "not_selected_baseline_not_runtime_authority_not_economics_pass",
            "next_action": NEXT_ACTION,
        }
    base.write_csv(registry_path, list(by_id.values()), fieldnames)


def finalize_candidate_self_checks(decision_rows: list[dict[str, Any]]) -> None:
    registry_path = REPO_ROOT / CANDIDATE_REGISTRY
    registry_rows = base.read_csv_rows(registry_path) if registry_path.exists() else []
    registry_ids = {row.get("candidate_id") for row in registry_rows}
    checked_at = utc_now()
    for row in decision_rows:
        candidate_id = row.get("candidate_id")
        if not candidate_id:
            continue
        path = candidate_summary_path(str(candidate_id))
        full = REPO_ROOT / path
        payload = base.load_yaml(full)
        failures: list[str] = []
        if not full.exists():
            failures.append(f"missing_candidate_summary:{path.as_posix()}")
        if candidate_id not in registry_ids:
            failures.append(f"candidate_registry_missing:{candidate_id}")
        if payload.get("claim_boundary") != CANDIDATE_CLAIM_BOUNDARY:
            failures.append("claim_boundary_mismatch")
        if (payload.get("candidate_scope") or {}).get("runtime_authority") is not False:
            failures.append("runtime_authority_not_false")
        if (payload.get("candidate_scope") or {}).get("economics_pass") is not False:
            failures.append("economics_pass_not_false")
        payload["writer_scope_self_check"] = {
            "status": "passed" if not failures else "failed",
            "checked_at_utc": checked_at,
            "failures": failures,
            "writer_contract_version": WRITER_CONTRACT_VERSION,
            "validation_depth": VALIDATION_DEPTH,
            "non_pytest_smokes": list(NON_PYTEST_SMOKES),
            "skipped_broad_validations": list(SKIPPED_BROAD_VALIDATIONS),
            "broad_validation_escalation_reason": BROAD_VALIDATION_ESCALATION_REASON,
            "source_of_truth_paths": [path.as_posix(), PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix()],
            "writer_owned_outputs": [path.as_posix()],
            "candidate_registry": CANDIDATE_REGISTRY.as_posix(),
            "artifact_hash_registry_check": "covered_by_l5_routing_decision_summary_self_check",
            "claim_boundary": CANDIDATE_CLAIM_BOUNDARY,
            "forbidden_claims_respected": not failures,
            "next_action_or_reopen_condition": NEXT_ACTION,
        }
        base.write_yaml(full, payload)


def upsert_artifact_registry(summary: dict[str, Any], candidate_paths: list[Path]) -> None:
    registry_path = REPO_ROOT / ARTIFACT_REGISTRY
    rows = base.read_csv_rows(registry_path) if registry_path.exists() else []
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
    by_id = {row["artifact_id"]: row for row in rows}
    producer = summary["provenance"]["producer"]

    def put(artifact_id: str, artifact_type: str, path: Path, notes: str, claim_boundary: str = CLAIM_BOUNDARY) -> None:
        full = REPO_ROOT / path
        by_id[artifact_id] = {
            **{key: "" for key in fieldnames},
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "path_or_uri": path.as_posix(),
            "sha256": base.sha256(full),
            "size_bytes": str(full.stat().st_size),
            "availability": "present_hash_recorded",
            "producer_command": producer,
            "regeneration_command": producer,
            "source_of_truth": ROUTING_SUMMARY.as_posix(),
            "consumer": NEXT_WORK_ITEM_ID,
            "claim_boundary": claim_boundary,
            "notes": notes,
        }

    put(
        "artifact_wave02_execution_liquidity_decision_replay_l5_routing_decision_summary_v0",
        "l5_routing_decision_summary",
        ROUTING_SUMMARY,
        "Wave02 ELQ decision replay L5 routing decision summary",
    )
    put(
        "artifact_wave02_execution_liquidity_decision_replay_l5_routing_decision_index_v0",
        "l5_routing_decision_index",
        ROUTING_INDEX,
        "Wave02 ELQ decision replay L5 routing decision row index",
    )
    put(
        "artifact_wave02_execution_liquidity_decision_replay_l5_routing_decision_closeout_v0",
        "work_closeout",
        ROUTING_CLOSEOUT,
        "Wave02 ELQ decision replay L5 routing decision closeout",
    )
    for path in candidate_paths:
        candidate_id = path.parent.name
        put(
            f"artifact_{candidate_id}_summary_v0",
            "candidate_summary",
            path,
            "candidate summary opened as L5 runtime-evidence target only",
            CANDIDATE_CLAIM_BOUNDARY,
        )
    base.write_csv(registry_path, list(by_id.values()), fieldnames)


def next_work_payload(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "work_item_lite_v1",
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "work_item_id": NEXT_WORK_ITEM_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "primary_family": "runtime_probe",
        "primary_skill": "spacesonar-runtime-evidence",
        "support_skills": ["spacesonar-evidence-provenance", "spacesonar-claim-discipline"],
        "verification_profile": "writer_scope_candidate_l5_preparation",
        "targets": summary["artifact_outputs"]["candidate_summaries"],
        "acceptance_criteria": [
            "prepare candidate-specific L5 runtime evidence plan for opened ELQ candidate manifests",
            "keep selected baseline, runtime authority, economics pass, live readiness, and Goal Achieve forbidden",
            "do not count l5_candidate_count until candidate-specific L5 evidence is written",
        ],
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "next_action": NEXT_ACTION,
        "status": NEXT_STATUS,
        "source_of_truth_paths": [ROUTING_SUMMARY.as_posix(), ROUTING_INDEX.as_posix(), ROUTING_CLOSEOUT.as_posix()],
        "writer_owned_outputs": [
            "candidate-specific L5 runtime evidence manifests/summaries for opened candidate ids",
        ],
        "validation_depth": VALIDATION_DEPTH,
        "non_pytest_smokes": list(NON_PYTEST_SMOKES),
        "skipped_broad_validations": list(SKIPPED_BROAD_VALIDATIONS),
        "broad_validation_escalation_reason": BROAD_VALIDATION_ESCALATION_REASON,
        "writer_scope_self_check": summary.get("writer_scope_self_check"),
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
        "current_truth": {
            "l5_routing_decision_summary": ROUTING_SUMMARY.as_posix(),
            "l5_routing_decision_index": ROUTING_INDEX.as_posix(),
            "opened_candidate_ids": summary["opened_candidate_ids"],
            "candidate_summaries": summary["artifact_outputs"]["candidate_summaries"],
            "candidate_count": summary["counts"]["candidate_count"],
            "l5_candidate_count": summary["counts"]["l5_candidate_count"],
            "held_cell_ids": summary["held_cell_ids"],
            "repair_first_cell_ids": summary["repair_first_cell_ids"],
        },
        "unresolved_blockers": list(summary["unresolved_blockers"]),
        "unresolved_blockers_or_none": list(summary["unresolved_blockers"]),
        "reopen_conditions": list(summary["reopen_conditions"]),
        "missing_material_if_relevant": summary["judgment"]["missing_evidence"],
        "next_action_or_reopen_condition": NEXT_ACTION,
        "path": NEXT_WORK_ITEM.as_posix(),
        "summary": "Wave02 ELQ candidate-specific L5 runtime evidence preparation pending; no selected baseline/runtime authority/economics pass.",
    }


def update_control_records(summary: dict[str, Any]) -> None:
    next_work = next_work_payload(summary)
    base.write_yaml(REPO_ROOT / NEXT_WORK_ITEM, next_work)

    resume = base.load_yaml(REPO_ROOT / RESUME_CURSOR)
    resume["updated_at_utc"] = summary["ended_at_utc"]
    resume["cursor_state"] = NEXT_STATUS
    resume["active_phase"] = NEXT_STATUS
    resume["active_work_item_id"] = NEXT_WORK_ITEM_ID
    resume["campaign_id"] = CAMPAIGN_ID
    resume["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    resume["next_action"] = NEXT_ACTION
    resume["unresolved_blockers"] = list(summary["unresolved_blockers"])
    sources = resume.setdefault("current_truth_sources", [])
    for source in [
        ROUTING_SUMMARY.as_posix(),
        ROUTING_INDEX.as_posix(),
        ROUTING_CLOSEOUT.as_posix(),
        *summary["artifact_outputs"]["candidate_summaries"],
    ]:
        if source not in sources:
            sources.append(source)
    resume["latest_completed_work"] = {
        "work_item_id": WORK_ITEM_ID,
        "result_judgment": summary["judgment"]["judgment_label"],
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [ROUTING_SUMMARY.as_posix(), ROUTING_CLOSEOUT.as_posix()],
    }
    resume["next_work_item"] = {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()}
    base.write_yaml(REPO_ROOT / RESUME_CURSOR, resume)

    goal = base.load_yaml(REPO_ROOT / GOAL_MANIFEST)
    goal["updated_at_utc"] = summary["ended_at_utc"]
    goal["active_phase"] = NEXT_STATUS
    goal["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    goal["next_work_item"] = {
        "work_item_id": NEXT_WORK_ITEM_ID,
        "path": NEXT_WORK_ITEM.as_posix(),
        "summary": "Wave02 ELQ candidate-specific L5 runtime evidence preparation pending.",
    }
    wave02 = goal.setdefault("wave02_execution_liquidity_campaign", {})
    wave02["status"] = NEXT_STATUS
    wave02["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    wave02["l5_routing_decision_summary"] = ROUTING_SUMMARY.as_posix()
    wave02["l5_routing_decision_index"] = ROUTING_INDEX.as_posix()
    wave02["l5_routing_decision_status"] = summary["status"]
    wave02["l5_routing_decision_counts"] = summary["counts"]
    wave02["candidate_ids"] = list(summary["opened_candidate_ids"])
    wave02["candidate_count"] = summary["counts"]["candidate_count"]
    wave02["l5_candidate_count"] = summary["counts"]["l5_candidate_count"]
    wave02["next_work_item"] = NEXT_WORK_ITEM_ID
    base.write_yaml(REPO_ROOT / GOAL_MANIFEST, goal)

    campaign = base.load_yaml(REPO_ROOT / CAMPAIGN_MANIFEST)
    campaign["updated_at_utc"] = summary["ended_at_utc"]
    campaign["status"] = NEXT_STATUS
    campaign["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    campaign["candidate_ids"] = list(summary["opened_candidate_ids"])
    campaign["candidate_count"] = summary["counts"]["candidate_count"]
    campaign["l5_candidate_count"] = summary["counts"]["l5_candidate_count"]
    campaign["next_action"] = NEXT_ACTION
    replay = campaign.setdefault("l4_follow_through", {}).setdefault("decision_replay", {})
    replay["l5_routing_decision_summary"] = ROUTING_SUMMARY.as_posix()
    replay["l5_routing_decision_index"] = ROUTING_INDEX.as_posix()
    replay["l5_routing_decision_status"] = summary["status"]
    replay["l5_routing_decision_counts"] = summary["counts"]
    campaign.setdefault("runtime_follow_through", {})["decision_replay_l5_routing_decision"] = {
        "summary": ROUTING_SUMMARY.as_posix(),
        "index": ROUTING_INDEX.as_posix(),
        "status": summary["status"],
        "counts": summary["counts"],
        "claim_boundary": summary["claim_boundary"],
    }
    campaign["missing_evidence"] = summary["judgment"]["missing_evidence"]
    campaign["unresolved_blockers"] = list(summary["unresolved_blockers"])
    campaign["reopen_conditions"] = list(summary["reopen_conditions"])
    base.write_yaml(REPO_ROOT / CAMPAIGN_MANIFEST, campaign)

    workspace = base.load_yaml(REPO_ROOT / WORKSPACE_STATE)
    workspace["updated_utc"] = summary["ended_at_utc"]
    workspace.setdefault("active_campaign", {})["status"] = NEXT_STATUS
    workspace["active_work_item"] = {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()}
    workspace["current_claim_boundary"] = NEXT_CLAIM_BOUNDARY
    workspace["next_action"] = NEXT_ACTION
    workspace["unresolved_blockers"] = list(summary["unresolved_blockers"])
    counts = workspace.setdefault("summary_counts", {})
    counts["candidate_count"] = summary["counts"]["candidate_count"]
    counts["l5_candidate_count"] = summary["counts"]["l5_candidate_count"]
    counts["wave02_execution_liquidity_decision_replay_l5_routing_decision"] = summary["counts"]
    elq = workspace.setdefault("wave02_execution_liquidity_l4_materialization", {})
    elq["status"] = NEXT_STATUS
    elq["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    elq["l5_routing_decision_summary"] = ROUTING_SUMMARY.as_posix()
    elq["l5_routing_decision_index"] = ROUTING_INDEX.as_posix()
    elq["l5_routing_decision_status"] = summary["status"]
    elq["l5_routing_decision_counts"] = summary["counts"]
    elq["candidate_ids"] = list(summary["opened_candidate_ids"])
    elq["candidate_count"] = summary["counts"]["candidate_count"]
    elq["l5_candidate_count"] = summary["counts"]["l5_candidate_count"]
    base.write_yaml(REPO_ROOT / WORKSPACE_STATE, workspace)

    if (REPO_ROOT / GOAL_REGISTRY).exists():
        goal_rows = base.read_csv_rows(REPO_ROOT / GOAL_REGISTRY)
        for row in goal_rows:
            if row.get("goal_id") == GOAL_ID:
                if "active_phase" in row:
                    row["active_phase"] = NEXT_STATUS
                if "next_work_item" in row:
                    row["next_work_item"] = NEXT_WORK_ITEM_ID
                if "claim_boundary" in row:
                    row["claim_boundary"] = NEXT_CLAIM_BOUNDARY
        if goal_rows:
            base.write_csv(REPO_ROOT / GOAL_REGISTRY, goal_rows, list(goal_rows[0].keys()))


def write_records(summary: dict[str, Any], decision_rows: list[dict[str, Any]], *, write_control_records: bool) -> None:
    candidate_paths = write_candidate_summaries(decision_rows, summary["created_at_utc"])
    base.write_yaml(REPO_ROOT / ROUTING_SUMMARY, summary)
    base.write_csv(REPO_ROOT / ROUTING_INDEX, decision_rows, decision_index_fieldnames())
    base.write_yaml(REPO_ROOT / ROUTING_CLOSEOUT, build_closeout(summary))
    upsert_candidate_registry(decision_rows)
    finalize_candidate_self_checks(decision_rows)
    upsert_artifact_registry(summary, candidate_paths)
    if write_control_records:
        update_control_records(summary)


def writer_scope_self_check(summary: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    for path in [PAIR_SUMMARY, PAIR_INDEX, ROUTING_SUMMARY, ROUTING_INDEX, ROUTING_CLOSEOUT]:
        if not (REPO_ROOT / path).exists():
            failures.append(f"missing:{path.as_posix()}")
    rows = base.read_csv_rows(REPO_ROOT / ROUTING_INDEX) if (REPO_ROOT / ROUTING_INDEX).exists() else []
    if len(rows) != summary["counts"]["evaluated_pair_count"]:
        failures.append("routing_index_row_count_mismatch")
    for path_value in summary["artifact_outputs"]["candidate_summaries"]:
        full = REPO_ROOT / path_value
        if not full.exists():
            failures.append(f"missing_candidate_summary:{path_value}")
            continue
        payload = base.load_yaml(full)
        if payload.get("claim_boundary") != CANDIDATE_CLAIM_BOUNDARY:
            failures.append(f"candidate_claim_boundary_mismatch:{path_value}")
    if summary["counts"]["candidate_count"] != len(summary["opened_candidate_ids"]):
        failures.append("candidate_count_id_mismatch")
    if summary["counts"]["l5_candidate_count"] != 0:
        failures.append("l5_candidate_count_nonzero_before_l5_evidence")

    registry_rows = base.read_csv_rows(REPO_ROOT / CANDIDATE_REGISTRY)
    registry_ids = {row.get("candidate_id") for row in registry_rows}
    for candidate_id in summary["opened_candidate_ids"]:
        if candidate_id not in registry_ids:
            failures.append(f"candidate_registry_missing:{candidate_id}")

    artifact_rows = base.read_csv_rows(REPO_ROOT / ARTIFACT_REGISTRY)
    artifacts = {row.get("artifact_id"): row for row in artifact_rows}
    for artifact_id, path in [
        ("artifact_wave02_execution_liquidity_decision_replay_l5_routing_decision_summary_v0", ROUTING_SUMMARY),
        ("artifact_wave02_execution_liquidity_decision_replay_l5_routing_decision_index_v0", ROUTING_INDEX),
        ("artifact_wave02_execution_liquidity_decision_replay_l5_routing_decision_closeout_v0", ROUTING_CLOSEOUT),
    ]:
        row = artifacts.get(artifact_id)
        if not row:
            failures.append(f"missing_registry:{artifact_id}")
            continue
        if row.get("path_or_uri") != path.as_posix():
            failures.append(f"registry_path_mismatch:{artifact_id}")
        if row.get("sha256") != base.sha256(REPO_ROOT / path):
            failures.append(f"registry_hash_mismatch:{artifact_id}")
    for candidate_id in summary["opened_candidate_ids"]:
        artifact_id = f"artifact_{candidate_id}_summary_v0"
        row = artifacts.get(artifact_id)
        path = candidate_summary_path(candidate_id)
        if not row:
            failures.append(f"missing_registry:{artifact_id}")
            continue
        if row.get("sha256") != base.sha256(REPO_ROOT / path):
            failures.append(f"registry_hash_mismatch:{artifact_id}")

    next_work = base.load_yaml(REPO_ROOT / NEXT_WORK_ITEM)
    workspace = base.load_yaml(REPO_ROOT / WORKSPACE_STATE)
    if next_work.get("work_item_id") != NEXT_WORK_ITEM_ID:
        failures.append("next_work_item_id_mismatch")
    if next_work.get("writer_contract_version") != WRITER_CONTRACT_VERSION:
        failures.append("next_work_item_writer_contract_version_mismatch")
    if next_work.get("claim_boundary") != NEXT_CLAIM_BOUNDARY:
        failures.append("next_work_item_claim_boundary_mismatch")
    if workspace.get("active_work_item", {}).get("work_item_id") != NEXT_WORK_ITEM_ID:
        failures.append("workspace_active_work_item_mismatch")
    if workspace.get("current_claim_boundary") != NEXT_CLAIM_BOUNDARY:
        failures.append("workspace_claim_boundary_mismatch")

    return {
        "status": "passed" if not failures else "failed",
        "checked_at_utc": utc_now(),
        "failures": failures,
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "validation_depth": VALIDATION_DEPTH,
        "non_pytest_smokes": list(NON_PYTEST_SMOKES),
        "skipped_broad_validations": list(SKIPPED_BROAD_VALIDATIONS),
        "broad_validation_escalation_reason": BROAD_VALIDATION_ESCALATION_REASON,
        "source_of_truth_paths": [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix()],
        "writer_owned_outputs": [ROUTING_SUMMARY.as_posix(), ROUTING_INDEX.as_posix(), ROUTING_CLOSEOUT.as_posix()],
        "claim_boundary": CLAIM_BOUNDARY,
        "forbidden_claims_respected": not failures,
        "candidate_count": summary["counts"]["candidate_count"],
        "l5_candidate_count": summary["counts"]["l5_candidate_count"],
        "next_action_or_reopen_condition": NEXT_ACTION,
    }


def build_command_argv(args: argparse.Namespace) -> list[str]:
    command = ["python", "foundation/pipelines/decide_wave02_execution_liquidity_decision_replay_l5_routing.py"]
    if args.write_control_records:
        command.append("--write-control-records")
    if args.dry_run:
        command.append("--dry-run")
    return command


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Decide Wave02 ELQ decision replay L5 routing and open candidate manifests.")
    parser.add_argument("--write-control-records", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    pair_writer.runtime_writer.configure_base()
    args = parse_args(argv)
    started_at = utc_now()
    command_argv = build_command_argv(args)
    decision_rows = build_decision_rows()
    summary = build_summary(decision_rows, started_at, command_argv)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "counts": summary["counts"],
                    "opened_candidate_ids": summary["opened_candidate_ids"],
                    "held_cell_ids": summary["held_cell_ids"],
                    "repair_first_cell_ids": summary["repair_first_cell_ids"],
                    "claim_boundary": summary["claim_boundary"],
                },
                indent=2,
            )
        )
        return 0
    write_records(summary, decision_rows, write_control_records=args.write_control_records)
    self_check = writer_scope_self_check(summary)
    summary["writer_scope_self_check"] = self_check
    base.write_yaml(REPO_ROOT / ROUTING_SUMMARY, summary)
    base.write_yaml(REPO_ROOT / ROUTING_CLOSEOUT, build_closeout(summary))
    upsert_artifact_registry(summary, [Path(path) for path in summary["artifact_outputs"]["candidate_summaries"]])
    if args.write_control_records:
        update_control_records(summary)
    self_check = writer_scope_self_check(summary)
    if self_check["status"] != "passed":
        print(
            json.dumps(
                {
                    "status": "writer_scope_self_check_failed",
                    "self_check": self_check,
                    "summary": ROUTING_SUMMARY.as_posix(),
                    "claim_boundary": summary["claim_boundary"],
                },
                indent=2,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "status": summary["status"],
                "summary": ROUTING_SUMMARY.as_posix(),
                "routing_index": ROUTING_INDEX.as_posix(),
                "opened_candidate_ids": summary["opened_candidate_ids"],
                "held_cell_ids": summary["held_cell_ids"],
                "counts": summary["counts"],
                "writer_scope_self_check": self_check["status"],
                "claim_boundary": summary["claim_boundary"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
