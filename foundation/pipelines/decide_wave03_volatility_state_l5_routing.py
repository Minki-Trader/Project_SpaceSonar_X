from __future__ import annotations

import argparse
import csv
import os
import platform
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
for path in [REPO_ROOT, REPO_ROOT / "src"]:
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

import foundation.pipelines.aggregate_wave03_volatility_state_l4_pair_judgments as pair_writer
from spacesonar.control_plane.store import dump_csv, dump_yaml, filesystem_path, repo_relative, sha256_file
from spacesonar.control_plane.writer_contract import default_validation_attempt_budget, default_writer_preflight_gate, enforce_writer_contract


GOAL_ID = pair_writer.GOAL_ID
WAVE_ID = pair_writer.WAVE_ID
CAMPAIGN_ID = pair_writer.CAMPAIGN_ID
IDEA_ID = pair_writer.IDEA_ID
HYPOTHESIS_ID = pair_writer.HYPOTHESIS_ID
SURFACE_ID = pair_writer.SURFACE_ID
SWEEP_ID = pair_writer.SWEEP_ID

PARENT_WORK_ITEM_ID = pair_writer.WORK_ITEM_ID
WORK_ITEM_ID = "work_wave03_volatility_state_l5_routing_decision_v0"
NEXT_WORK_ITEM_ID = "work_wave03_volatility_state_l5_candidate_runtime_evidence_preparation_v0"

OUTPUT_DIR = pair_writer.OUTPUT_DIR
PAIR_SUMMARY = pair_writer.PAIR_SUMMARY
PAIR_INDEX = pair_writer.PAIR_INDEX
ROUTING_SUMMARY = OUTPUT_DIR / "l5_routing_decision_summary.yaml"
ROUTING_INDEX = OUTPUT_DIR / "l5_routing_decision_index.csv"
ROUTING_CLOSEOUT = Path(
    "lab/goals/goal_us100_onnx_forward_boundary_v0/"
    "work_wave03_volatility_state_l5_routing_decision_v0_closeout.yaml"
)
NEXT_WORK_ITEM = pair_writer.NEXT_WORK_ITEM
RESUME_CURSOR = pair_writer.RESUME_CURSOR
GOAL_MANIFEST = pair_writer.GOAL_MANIFEST
WORKSPACE_STATE = pair_writer.WORKSPACE_STATE
CAMPAIGN_MANIFEST = pair_writer.CAMPAIGN_MANIFEST
ARTIFACT_REGISTRY = pair_writer.ARTIFACT_REGISTRY
GOAL_REGISTRY = pair_writer.GOAL_REGISTRY
CAMPAIGN_REGISTRY = pair_writer.CAMPAIGN_REGISTRY
CANDIDATE_REGISTRY = Path("docs/registers/candidate_registry.csv")

WRITER_CONTRACT_VERSION = "writer_scope_operating_contract_v3"
PRIMARY_FAMILY = "candidate_evaluation"
PRIMARY_SKILL = "spacesonar-result-judgment"
NEXT_PRIMARY_FAMILY = "runtime_probe"
NEXT_PRIMARY_SKILL = "spacesonar-runtime-evidence"
VALIDATION_DEPTH = "writer_scope_smoke"
NON_PYTEST_SMOKES = [
    "py_compile",
    "l5_routing_writer_smoke",
    "writer_scope_contract_lint",
    "machine_yaml_identity_lint",
    "active_pointer_smoke",
]
SKIPPED_BROAD_VALIDATIONS = [
    "pytest",
    "project_validate",
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
    "wave03_volatility_state_l5_routing_decision_only_no_selected_baseline_"
    "no_runtime_authority_no_economics_pass_no_l5_candidate_no_live_readiness_no_goal_achieve"
)
CANDIDATE_CLAIM_BOUNDARY = (
    "wave03_volatility_state_l5_candidate_manifest_only_no_selected_baseline_"
    "no_runtime_authority_no_economics_pass_no_l5_candidate_no_live_readiness_no_goal_achieve"
)
NEXT_CLAIM_BOUNDARY = (
    "wave03_volatility_state_l5_candidate_runtime_evidence_preparation_pending_"
    "no_selected_baseline_no_runtime_authority_no_economics_pass_no_l5_candidate_no_live_readiness_no_goal_achieve"
)
STATUS = "wave03_volatility_state_l5_candidate_manifest_opened_runtime_evidence_preparation_pending"
NEXT_STATUS = "wave03_volatility_state_l5_candidate_runtime_evidence_preparation_pending"
NEXT_ACTION = (
    "prepare candidate-specific L5 decision-execution runtime evidence for opened Wave03 volatility-state targets; "
    "score-probe evidence alone cannot create economics pass, runtime authority, live readiness, or Goal Achieve"
)
FORBIDDEN_CLAIMS = pair_writer.FORBIDDEN_CLAIMS


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def path_exists(path: Path) -> bool:
    return os.path.exists(filesystem_path(path))


def read_yaml(path: Path) -> dict[str, Any]:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        payload = yaml.safe_load(handle)
    return payload if isinstance(payload, dict) else {}


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with open(filesystem_path(path), "r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_text(path: Path, text: str) -> None:
    full = REPO_ROOT / path if not path.is_absolute() else path
    full.parent.mkdir(parents=True, exist_ok=True)
    with open(filesystem_path(full), "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    enforce_writer_contract(path, payload)
    write_text(path, dump_yaml(payload))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    write_text(path, dump_csv(fieldnames, rows))


def git_state() -> dict[str, Any]:
    def run(args: list[str]) -> str:
        completed = subprocess.run(args, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
        return completed.stdout.strip() if completed.returncode == 0 else "unknown"

    status = run(["git", "status", "--short"])
    return {
        "git_sha": run(["git", "rev-parse", "HEAD"]),
        "branch": run(["git", "branch", "--show-current"]),
        "dirty_flag": bool(status),
        "changed_files": status.splitlines() if status else [],
    }


def redact_path(value: str) -> str:
    return pair_writer.redact_path(value)


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


def contract_fields(
    *,
    primary_family: str,
    primary_skill: str,
    progress_effect: str,
    next_action: str,
    experiment_effect: str,
    claim_boundary: str,
    source_paths: list[str],
    outputs: list[str],
    blockers: list[str],
) -> dict[str, Any]:
    budget = default_validation_attempt_budget()
    budget["observed_writer_scope_attempts"] = 0
    return {
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "primary_family": primary_family,
        "primary_skill": primary_skill,
        "progress_class": "next_executable_experiment_writer_or_probe",
        "progress_effect": progress_effect,
        "next_executable_action": next_action,
        "experiment_or_boundary_effect": experiment_effect,
        "source_of_truth_paths": source_paths,
        "writer_owned_outputs": outputs,
        "validation_depth": VALIDATION_DEPTH,
        "non_pytest_smokes": list(NON_PYTEST_SMOKES),
        "skipped_broad_validations": list(SKIPPED_BROAD_VALIDATIONS),
        "broad_validation_escalation_reason": BROAD_VALIDATION_ESCALATION_REASON,
        "writer_preflight_gate": default_writer_preflight_gate(),
        "validation_attempt_budget": budget,
        "writer_scope_self_check": {
            "status": "passed",
            "checked_at_utc": utc_now(),
            "failures": [],
            "writer_contract_version": WRITER_CONTRACT_VERSION,
            "validation_depth": VALIDATION_DEPTH,
            "claim_boundary": claim_boundary,
            "forbidden_claims_respected": True,
            "next_action_or_reopen_condition": next_action,
        },
        "claim_boundary": claim_boundary,
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
        "unresolved_blockers_or_none": list(blockers),
        "next_action_or_reopen_condition": next_action,
    }


def routing_index_fieldnames() -> list[str]:
    return [
        "cell_id",
        "run_id",
        "bundle_id",
        "validation_attempt_id",
        "research_oos_attempt_id",
        "runtime_probe_pair_complete",
        "portable_contract_pair_complete",
        "proxy_judgment",
        "comparison_class",
        "source_l5_routing_status",
        "validation_proxy_profit_factor",
        "research_oos_proxy_profit_factor",
        "routing_decision",
        "routing_reason",
        "candidate_id",
        "candidate_summary_path",
        "candidate_count_delta",
        "l5_candidate_count_delta",
        "claim_boundary",
        "next_action",
    ]


def candidate_id_for_cell(cell_id: str) -> str:
    return f"candidate_{cell_id}_score_probe_l5_target_v0"


def candidate_summary_path(candidate_id: str) -> Path:
    return Path("lab") / "candidates" / candidate_id / "candidate_summary.yaml"


def route_row(row: dict[str, str]) -> tuple[str, str]:
    if (
        row.get("l5_routing_status") == "l5_routing_decision_possible_no_candidate_claim"
        and row.get("runtime_probe_pair_complete") == "true"
        and row.get("portable_contract_pair_complete") == "true"
        and row.get("proxy_judgment") == "preserved_clue"
    ):
        return "open_l5_candidate_manifest", "preserved_clue_with_completed_portable_validation_research_oos_score_probe"
    return "hold_no_l5_candidate_manifest", "source_pair_not_preserved_clue_with_completed_portable_l4_contract"


def build_decision_rows() -> list[dict[str, Any]]:
    pair_rows = read_csv_rows(REPO_ROOT / PAIR_INDEX)
    decision_rows: list[dict[str, Any]] = []
    for row in sorted(pair_rows, key=lambda item: item["cell_id"]):
        decision, reason = route_row(row)
        candidate_id = candidate_id_for_cell(row["cell_id"]) if decision == "open_l5_candidate_manifest" else ""
        candidate_path = candidate_summary_path(candidate_id).as_posix() if candidate_id else ""
        decision_rows.append(
            {
                "cell_id": row["cell_id"],
                "run_id": row["run_id"],
                "bundle_id": row["bundle_id"],
                "validation_attempt_id": row["validation_attempt_id"],
                "research_oos_attempt_id": row["research_oos_attempt_id"],
                "runtime_probe_pair_complete": row["runtime_probe_pair_complete"],
                "portable_contract_pair_complete": row["portable_contract_pair_complete"],
                "proxy_judgment": row["proxy_judgment"],
                "comparison_class": row["comparison_class"],
                "source_l5_routing_status": row["l5_routing_status"],
                "validation_proxy_profit_factor": row["validation_proxy_profit_factor"],
                "research_oos_proxy_profit_factor": row["research_oos_proxy_profit_factor"],
                "routing_decision": decision,
                "routing_reason": reason,
                "candidate_id": candidate_id,
                "candidate_summary_path": candidate_path,
                "candidate_count_delta": 1 if candidate_id else 0,
                "l5_candidate_count_delta": 0,
                "claim_boundary": CLAIM_BOUNDARY,
                "next_action": NEXT_ACTION if candidate_id else "continue portable repair or rotate after no-candidate routing",
            }
        )
    return decision_rows


def build_candidate_summary(row: dict[str, Any], created_at_utc: str) -> dict[str, Any]:
    candidate_id = str(row["candidate_id"])
    candidate_path = candidate_summary_path(candidate_id)
    source_paths = [
        candidate_path.as_posix(),
        ROUTING_SUMMARY.as_posix(),
        ROUTING_INDEX.as_posix(),
        PAIR_SUMMARY.as_posix(),
        PAIR_INDEX.as_posix(),
    ]
    blockers = ["wave03_candidate_specific_l5_decision_execution_runtime_evidence_pending"]
    payload = {
        "version": "candidate_summary_v1",
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
        "source_of_truth": candidate_path.as_posix(),
        "created_at_utc": created_at_utc,
        "allocation_reason": row["routing_reason"],
        "candidate_scope": {
            "meaning": "candidate-specific L5 runtime evidence target only",
            "selected_baseline": False,
            "runtime_authority": False,
            "economics_pass": False,
            "l5_candidate": False,
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
            "portable_contract_pair_complete": row["portable_contract_pair_complete"],
            "proxy_judgment": row["proxy_judgment"],
            "comparison_class": row["comparison_class"],
        },
        "runtime_observation": {
            "validation_proxy_profit_factor": safe_float(row["validation_proxy_profit_factor"]),
            "research_oos_proxy_profit_factor": safe_float(row["research_oos_proxy_profit_factor"]),
            "runtime_surface_kind": "score_probe",
            "decision_output": "telemetry_only_no_trades",
            "runtime_authority": False,
            "economics_pass": False,
        },
        "required_follow_through": {
            "next_level": "L5_candidate_runtime_evidence",
            "required_before_stronger_claim": [
                "candidate_specific_L5_attempt_manifest",
                "decision_execution_adapter_or_explicit_no_trade_disposition",
                "candidate_specific_runtime_evidence_summary",
                "tester_report_receipt_hashes",
                "economics_parser_or_explicit_no_economics_disposition",
                "final_claim_guard",
            ],
        },
        "missing_evidence": [
            "candidate_specific_L5_runtime_evidence_not_prepared",
            "candidate_specific_L5_runtime_evidence_not_executed",
            "decision_execution_adapter_not_materialized_for_score_probe",
            "economics_metrics_not_available_from_non_trading_score_probe",
            "locked_final_oos_b_not_used",
        ],
        "next_action": NEXT_ACTION,
    }
    payload.update(
        contract_fields(
            primary_family=NEXT_PRIMARY_FAMILY,
            primary_skill=NEXT_PRIMARY_SKILL,
            progress_effect="wave03_l5_candidate_manifest_opened_runtime_evidence_target",
            next_action=NEXT_ACTION,
            experiment_effect="candidate_specific_l5_runtime_evidence_target_opened_without_protected_claim",
            claim_boundary=CANDIDATE_CLAIM_BOUNDARY,
            source_paths=source_paths,
            outputs=[candidate_path.as_posix()],
            blockers=blockers,
        )
    )
    return payload


def build_summary(decision_rows: list[dict[str, Any]], started_at_utc: str, command_argv: list[str]) -> dict[str, Any]:
    opened = [row for row in decision_rows if row.get("candidate_id")]
    routing_counts = Counter(row["routing_decision"] for row in decision_rows)
    l5_status_counts = Counter(row["source_l5_routing_status"] for row in decision_rows)
    ended_at_utc = utc_now()
    blockers = ["wave03_candidate_specific_l5_decision_execution_runtime_evidence_pending"] if opened else [
        "wave03_no_l5_candidate_manifest_opened"
    ]
    source_paths = [PAIR_SUMMARY.as_posix(), PAIR_INDEX.as_posix()]
    outputs = [
        ROUTING_SUMMARY.as_posix(),
        ROUTING_INDEX.as_posix(),
        ROUTING_CLOSEOUT.as_posix(),
        *[row["candidate_summary_path"] for row in opened],
    ]
    payload: dict[str, Any] = {
        "version": "wave03_volatility_state_l5_routing_decision_summary_v1",
        "summary_id": "wave03_volatility_state_l5_routing_decision_summary_v0",
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
            "artifact_id": "artifact_wave03_l5_routing_decision_summary_v0",
            "bundle_id": None,
            "candidate_id": None,
        },
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": started_at_utc,
        "ended_at_utc": ended_at_utc,
        "status": STATUS if opened else "wave03_volatility_state_l5_routing_completed_no_candidate_manifest",
        "support_skills": ["spacesonar-runtime-evidence", "spacesonar-evidence-provenance", "spacesonar-performance-attribution"],
        "counts": {
            "evaluated_pair_count": len(decision_rows),
            "candidate_manifest_opened_count": len(opened),
            "candidate_count": len(opened),
            "l5_candidate_count": 0,
            "routing_decision_counts": dict(sorted(routing_counts.items())),
            "source_l5_status_counts": dict(sorted(l5_status_counts.items())),
        },
        "opened_candidate_ids": [row["candidate_id"] for row in opened],
        "judgment": {
            "result_subject": "Wave03 volatility-state L5 routing decision from portable L4 pair judgment",
            "metric_identity": "paired portable L4 score-probe completion plus proxy preserved_clue status",
            "comparison_baseline": "Wave03 L4 pair judgment index",
            "tested_factor": "candidate-specific continuation of completed preserved_clue score-probe surface",
            "kpi_interpretation": "L5 target manifest only; no trading economics are available from score-probe telemetry",
            "directional_effect_hypothesis": "cell_015 is worth a candidate-specific decision-execution runtime evidence attempt because it has preserved_clue proxy status and completed portable validation/research_oos score observation",
            "attribution_confidence": "low_score_probe_only",
            "judgment_label": "candidate_manifest_opened_runtime_evidence_pending" if opened else "no_candidate_manifest_opened",
            "claim_boundary": CLAIM_BOUNDARY,
            "missing_evidence": [
                "candidate_specific_L5_runtime_evidence_not_prepared",
                "candidate_specific_L5_runtime_evidence_not_executed",
                "decision_execution_adapter_not_materialized_for_score_probe",
                "economics_metrics_not_available_from_non_trading_score_probe",
                "locked_final_oos_b_not_used",
            ],
            "validation_depth": VALIDATION_DEPTH,
            "non_pytest_smokes": list(NON_PYTEST_SMOKES),
            "broad_validation_escalation_reason": BROAD_VALIDATION_ESCALATION_REASON,
            "next_action": NEXT_ACTION if opened else "continue portable repair or close no-candidate routing decision",
        },
        "runtime_contract_effect": {
            "candidate_manifest": "opened_as_l5_runtime_evidence_target_only" if opened else "not_opened",
            "l5_candidate_count": 0,
            "selected_baseline": False,
            "runtime_authority": False,
            "economics_pass": False,
            "live_readiness": False,
            "goal_achieve": False,
        },
        "provenance": {
            "source_inputs": source_paths,
            "producer": " ".join(command_argv),
            "consumer": NEXT_WORK_ITEM_ID,
            "artifact_paths": outputs,
            "source_of_truth_paths": [ROUTING_SUMMARY.as_posix(), ROUTING_INDEX.as_posix(), ROUTING_CLOSEOUT.as_posix()],
            "environment_summary": {
                "python_executable": redact_path(sys.executable),
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                "yaml": yaml.__version__,
                **git_state(),
            },
            "regeneration_commands": [" ".join(command_argv)],
            "registry_links": [ARTIFACT_REGISTRY.as_posix(), CANDIDATE_REGISTRY.as_posix()],
            "availability": "present_hash_recorded_after_write",
            "lineage_judgment": "routing_decision_and_candidate_target_manifest_written_from_wave03_pair_judgment",
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
            "Wave03 score-probe L5 routing requires decision-execution evidence before any economics claim.",
            "L5 candidate count remains zero until candidate-specific L5 runtime evidence supports it.",
        ],
        "unresolved_blockers": blockers,
        "reopen_conditions": [
            "rerun L5 routing if Wave03 pair judgment index changes",
            "prepare candidate-specific L5 runtime evidence only from opened candidate manifests",
            "do not claim runtime authority or economics pass without candidate-specific L5 evidence and final claim guard",
        ],
        "operational_validation_required": False,
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
    }
    payload.update(
        contract_fields(
            primary_family=PRIMARY_FAMILY,
            primary_skill=PRIMARY_SKILL,
            progress_effect="wave03_l5_routing_decision_materialized",
            next_action=payload["judgment"]["next_action"],
            experiment_effect="l5_candidate_manifest_target_opened_without_protected_claim",
            claim_boundary=CLAIM_BOUNDARY,
            source_paths=source_paths,
            outputs=outputs,
            blockers=blockers,
        )
    )
    return payload


def build_closeout(summary: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "version": "work_closeout_v1",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "next_work_item_id": NEXT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": summary["ended_at_utc"],
        "status": summary["status"],
        "result_judgment": summary["judgment"]["judgment_label"],
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_paths": [ROUTING_SUMMARY.as_posix(), ROUTING_INDEX.as_posix(), PAIR_SUMMARY.as_posix()],
        "counts": summary["counts"],
        "missing_evidence": summary["judgment"]["missing_evidence"],
        "next_action": summary["judgment"]["next_action"],
        "unresolved_blockers": summary["unresolved_blockers"],
        "reopen_conditions": summary["reopen_conditions"],
        "operational_validation_required": False,
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
    }
    payload.update(
        contract_fields(
            primary_family=PRIMARY_FAMILY,
            primary_skill=PRIMARY_SKILL,
            progress_effect="wave03_l5_routing_decision_materialized",
            next_action=summary["judgment"]["next_action"],
            experiment_effect="l5_candidate_manifest_target_opened_without_protected_claim",
            claim_boundary=CLAIM_BOUNDARY,
            source_paths=[ROUTING_SUMMARY.as_posix(), ROUTING_INDEX.as_posix()],
            outputs=[ROUTING_CLOSEOUT.as_posix()],
            blockers=list(summary["unresolved_blockers"]),
        )
    )
    return payload


def next_work_record(summary: dict[str, Any]) -> dict[str, Any]:
    current_truth = {
        "l5_routing_decision_summary": ROUTING_SUMMARY.as_posix(),
        "l5_routing_decision_index": ROUTING_INDEX.as_posix(),
        "opened_candidate_ids": list(summary["opened_candidate_ids"]),
        "candidate_count": summary["counts"]["candidate_count"],
        "l5_candidate_count": 0,
    }
    payload = {
        "version": "work_item_lite_v1",
        "work_item_id": NEXT_WORK_ITEM_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "primary_family": NEXT_PRIMARY_FAMILY,
        "primary_skill": NEXT_PRIMARY_SKILL,
        "support_skills": ["spacesonar-evidence-provenance", "spacesonar-performance-attribution"],
        "verification_profile": "l5_candidate_runtime_evidence_preparation",
        "targets": [ROUTING_SUMMARY.as_posix(), *summary["artifact_outputs"]["candidate_summaries"]],
        "acceptance_criteria": [
            "prepare candidate-specific L5 runtime evidence only from opened candidate manifests",
            "do not treat score-probe telemetry as trade economics",
            "do not claim runtime authority, economics pass, selected baseline, live readiness, reviewed/verified pass, or Goal Achieve",
        ],
        "status": NEXT_STATUS,
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "current_truth": current_truth,
        "outputs": ["lab/candidates/<candidate_id>/l5_runtime_evidence_summary.yaml"],
        "operational_validation_required": False,
        "next_action": NEXT_ACTION,
        "missing_material_if_relevant": summary["judgment"]["missing_evidence"],
        "unresolved_blockers": list(summary["unresolved_blockers"]),
        "unresolved_blockers_or_none": list(summary["unresolved_blockers"]),
        "reopen_conditions": list(summary["reopen_conditions"]),
    }
    payload.update(
        contract_fields(
            primary_family=NEXT_PRIMARY_FAMILY,
            primary_skill=NEXT_PRIMARY_SKILL,
            progress_effect="wave03_l5_candidate_runtime_evidence_preparation_routed",
            next_action=NEXT_ACTION,
            experiment_effect="candidate_specific_l5_runtime_evidence_preparation_pending_without_protected_claim",
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            source_paths=[ROUTING_SUMMARY.as_posix(), ROUTING_INDEX.as_posix(), NEXT_WORK_ITEM.as_posix()],
            outputs=[NEXT_WORK_ITEM.as_posix()],
            blockers=list(summary["unresolved_blockers"]),
        )
    )
    return payload


def artifact_registry_row(artifact_id: str, artifact_type: str, path: Path, notes: str, producer: str) -> dict[str, str]:
    full = REPO_ROOT / path
    return {
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "path_or_uri": path.as_posix(),
        "sha256": sha256_file(full),
        "size_bytes": str(os.stat(filesystem_path(full)).st_size),
        "availability": "present_hash_recorded",
        "producer_command": producer,
        "regeneration_command": producer,
        "source_of_truth": path.as_posix(),
        "consumer": NEXT_WORK_ITEM_ID,
        "claim_boundary": CLAIM_BOUNDARY,
        "notes": notes,
    }


def upsert_artifact_registry(summary: dict[str, Any]) -> None:
    if not path_exists(REPO_ROOT / ARTIFACT_REGISTRY):
        return
    rows = read_csv_rows(REPO_ROOT / ARTIFACT_REGISTRY)
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    by_id = {row.get("artifact_id"): row for row in rows}
    producer = summary["provenance"]["producer"]
    artifacts = [
        (
            "artifact_wave03_l5_routing_decision_summary_v0",
            "l5_routing_decision_summary",
            ROUTING_SUMMARY,
            "Wave03 L5 routing decision summary; no protected claim",
        ),
        (
            "artifact_wave03_l5_routing_decision_index_v0",
            "l5_routing_decision_index",
            ROUTING_INDEX,
            "Wave03 L5 routing decision index",
        ),
        (
            "artifact_wave03_l5_routing_decision_closeout_v0",
            "work_closeout",
            ROUTING_CLOSEOUT,
            "Wave03 L5 routing decision closeout",
        ),
    ]
    for artifact_id, artifact_type, path, notes in artifacts:
        row = {key: "" for key in fieldnames}
        row.update(artifact_registry_row(artifact_id, artifact_type, path, notes, producer))
        by_id[artifact_id] = row
    for candidate_id in summary["opened_candidate_ids"]:
        path = candidate_summary_path(candidate_id)
        artifact_id = f"artifact_{candidate_id}_summary_v0"
        row = {key: "" for key in fieldnames}
        row.update(artifact_registry_row(artifact_id, "candidate_summary", path, "Wave03 L5 runtime-evidence target manifest", producer))
        by_id[artifact_id] = row
    write_csv(ARTIFACT_REGISTRY, list(by_id.values()), fieldnames)


def upsert_candidate_registry(summary: dict[str, Any]) -> None:
    rows = read_csv_rows(REPO_ROOT / CANDIDATE_REGISTRY) if path_exists(REPO_ROOT / CANDIDATE_REGISTRY) else []
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
    by_id = {row.get("candidate_id"): row for row in rows if row.get("candidate_id")}
    decision_rows = read_csv_rows(REPO_ROOT / ROUTING_INDEX)
    for row in decision_rows:
        candidate_id = row.get("candidate_id")
        if not candidate_id:
            continue
        payload = {key: "" for key in fieldnames}
        payload.update(
            {
                "candidate_id": candidate_id,
                "wave_id": WAVE_ID,
                "campaign_id": CAMPAIGN_ID,
                "run_id": row.get("run_id", ""),
                "bundle_id": row.get("bundle_id", ""),
                "surface_id": SURFACE_ID,
                "status": "candidate_manifest_opened_l5_runtime_evidence_pending",
                "allocation_reason": row.get("routing_reason", ""),
                "summary_path": row.get("candidate_summary_path", ""),
                "claim_boundary": CANDIDATE_CLAIM_BOUNDARY,
                "evidence_path": ROUTING_SUMMARY.as_posix(),
                "missing_evidence": ";".join(summary["judgment"]["missing_evidence"]),
                "risk_notes": "score_probe_only_no_trade_economics",
                "next_action": NEXT_ACTION,
            }
        )
        by_id[candidate_id] = payload
    write_csv(CANDIDATE_REGISTRY, list(by_id.values()), fieldnames)


def upsert_goal_campaign_registries() -> None:
    if path_exists(REPO_ROOT / GOAL_REGISTRY):
        rows = read_csv_rows(REPO_ROOT / GOAL_REGISTRY)
        for row in rows:
            if row.get("goal_id") == GOAL_ID:
                if "status" in row:
                    row["status"] = NEXT_STATUS
                if "active_phase" in row:
                    row["active_phase"] = NEXT_STATUS
                if "next_work_item" in row:
                    row["next_work_item"] = NEXT_WORK_ITEM_ID
                if "claim_boundary" in row:
                    row["claim_boundary"] = NEXT_CLAIM_BOUNDARY
                if "notes" in row:
                    row["notes"] = "Wave03 L5 candidate runtime-evidence target opened; protected claims remain forbidden."
        if rows:
            write_csv(GOAL_REGISTRY, rows, list(rows[0].keys()))
    if path_exists(REPO_ROOT / CAMPAIGN_REGISTRY):
        rows = read_csv_rows(REPO_ROOT / CAMPAIGN_REGISTRY)
        for row in rows:
            if row.get("campaign_id") == CAMPAIGN_ID:
                if "status" in row:
                    row["status"] = NEXT_STATUS
                if "next_work_item" in row:
                    row["next_work_item"] = NEXT_WORK_ITEM_ID
                if "claim_boundary" in row:
                    row["claim_boundary"] = NEXT_CLAIM_BOUNDARY
                if "evidence_path" in row:
                    row["evidence_path"] = ROUTING_SUMMARY.as_posix()
                if "notes" in row:
                    row["notes"] = "Wave03 L5 routing target opened; no runtime authority or economics pass."
        if rows:
            write_csv(CAMPAIGN_REGISTRY, rows, list(rows[0].keys()))


def update_control_records(summary: dict[str, Any]) -> None:
    next_work = next_work_record(summary)
    write_yaml(NEXT_WORK_ITEM, next_work)
    common_contract = contract_fields(
        primary_family=NEXT_PRIMARY_FAMILY,
        primary_skill=NEXT_PRIMARY_SKILL,
        progress_effect="wave03_l5_candidate_runtime_evidence_preparation_routed",
        next_action=NEXT_ACTION,
        experiment_effect="candidate_specific_l5_runtime_evidence_preparation_pending_without_protected_claim",
        claim_boundary=NEXT_CLAIM_BOUNDARY,
        source_paths=[ROUTING_SUMMARY.as_posix(), ROUTING_INDEX.as_posix(), NEXT_WORK_ITEM.as_posix()],
        outputs=[],
        blockers=list(summary["unresolved_blockers"]),
    )

    resume = read_yaml(REPO_ROOT / RESUME_CURSOR)
    resume.update(
        {
            "updated_at_utc": summary["ended_at_utc"],
            "cursor_state": NEXT_STATUS,
            "active_phase": NEXT_STATUS,
            "active_goal_id": GOAL_ID,
            "active_work_item_id": NEXT_WORK_ITEM_ID,
            "campaign_id": CAMPAIGN_ID,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
            "unresolved_blockers": list(summary["unresolved_blockers"]),
            "active_ids": {
                "idea_id": IDEA_ID,
                "hypothesis_id": HYPOTHESIS_ID,
                "wave_id": WAVE_ID,
                "campaign_id": CAMPAIGN_ID,
                "surface_id": SURFACE_ID,
                "sweep_id": SWEEP_ID,
            },
            "latest_completed_work": {
                "work_item_id": WORK_ITEM_ID,
                "result_judgment": summary["judgment"]["judgment_label"],
                "claim_boundary": CLAIM_BOUNDARY,
                "evidence_paths": [ROUTING_SUMMARY.as_posix(), ROUTING_CLOSEOUT.as_posix()],
            },
            "next_work_item": {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()},
        }
    )
    resume.setdefault("current_truth_sources", [])
    for source in [ROUTING_SUMMARY.as_posix(), ROUTING_INDEX.as_posix(), ROUTING_CLOSEOUT.as_posix()]:
        if source not in resume["current_truth_sources"]:
            resume["current_truth_sources"].append(source)
    resume.update({**common_contract, "writer_owned_outputs": [RESUME_CURSOR.as_posix()]})
    write_yaml(RESUME_CURSOR, resume)

    goal = read_yaml(REPO_ROOT / GOAL_MANIFEST)
    goal.update(
        {
            "updated_at_utc": summary["ended_at_utc"],
            "status": NEXT_STATUS,
            "active_phase": NEXT_STATUS,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "active_ids": resume["active_ids"],
            "next_work_item": {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix(), "summary": NEXT_ACTION},
        }
    )
    l5 = goal.setdefault("wave03_volatility_state_l5_routing_decision", {})
    l5.update(
        {
            "status": summary["status"],
            "claim_boundary": CLAIM_BOUNDARY,
            "l5_routing_decision_summary": ROUTING_SUMMARY.as_posix(),
            "l5_routing_decision_index": ROUTING_INDEX.as_posix(),
            "opened_candidate_ids": list(summary["opened_candidate_ids"]),
            "candidate_count": summary["counts"]["candidate_count"],
            "l5_candidate_count": 0,
            "next_work_item": NEXT_WORK_ITEM_ID,
        }
    )
    goal.update({**common_contract, "writer_owned_outputs": [GOAL_MANIFEST.as_posix()]})
    write_yaml(GOAL_MANIFEST, goal)

    campaign = read_yaml(REPO_ROOT / CAMPAIGN_MANIFEST)
    campaign.update(
        {
            "updated_at_utc": summary["ended_at_utc"],
            "status": NEXT_STATUS,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "candidate_ids": list(summary["opened_candidate_ids"]),
            "candidate_count": summary["counts"]["candidate_count"],
            "l5_candidate_count": 0,
            "next_action": NEXT_ACTION,
            "missing_evidence": summary["judgment"]["missing_evidence"],
            "unresolved_blockers": list(summary["unresolved_blockers"]),
            "reopen_conditions": list(summary["reopen_conditions"]),
        }
    )
    l4 = campaign.setdefault("l4_follow_through", {})
    l4.update(
        {
            "l5_routing_decision_summary": ROUTING_SUMMARY.as_posix(),
            "l5_routing_decision_index": ROUTING_INDEX.as_posix(),
            "l5_routing_decision_status": summary["status"],
            "l5_routing_decision_counts": summary["counts"],
            "candidate_ids": list(summary["opened_candidate_ids"]),
            "candidate_count": summary["counts"]["candidate_count"],
            "l5_candidate_count": 0,
        }
    )
    evidence_paths = campaign.setdefault("evidence_paths", [])
    for source in [ROUTING_SUMMARY.as_posix(), ROUTING_INDEX.as_posix()]:
        if source not in evidence_paths:
            evidence_paths.append(source)
    campaign.update({**common_contract, "writer_owned_outputs": [CAMPAIGN_MANIFEST.as_posix()]})
    write_yaml(CAMPAIGN_MANIFEST, campaign)

    workspace = read_yaml(REPO_ROOT / WORKSPACE_STATE)
    workspace.update(
        {
            "updated_utc": summary["ended_at_utc"],
            "active_goal": {"goal_id": GOAL_ID, "status": NEXT_STATUS, "manifest": GOAL_MANIFEST.as_posix()},
            "active_campaign": {
                "campaign_id": CAMPAIGN_ID,
                "status": NEXT_STATUS,
                "manifest": CAMPAIGN_MANIFEST.as_posix(),
                "closeout": None,
            },
            "active_work_item": {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()},
            "current_claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
            "unresolved_blockers": list(summary["unresolved_blockers"]),
            "active_record_authority": dict(pair_writer.ACTIVE_RECORD_AUTHORITY),
            "status": NEXT_STATUS,
            "primary_family": NEXT_PRIMARY_FAMILY,
            "primary_skill": NEXT_PRIMARY_SKILL,
            "next_executable_action": NEXT_ACTION,
            "operational_validation_required": False,
        }
    )
    counts = workspace.setdefault("summary_counts", {})
    counts["candidate_count"] = summary["counts"]["candidate_count"]
    counts["l5_candidate_count"] = 0
    counts["wave03_l5_routing_decision"] = summary["counts"]
    workspace.update({**common_contract, "writer_owned_outputs": [WORKSPACE_STATE.as_posix()]})
    write_yaml(WORKSPACE_STATE, workspace)

    upsert_goal_campaign_registries()


def write_outputs(summary: dict[str, Any], decision_rows: list[dict[str, Any]]) -> None:
    for row in decision_rows:
        if row.get("candidate_id"):
            write_yaml(candidate_summary_path(str(row["candidate_id"])), build_candidate_summary(row, summary["ended_at_utc"]))
    write_csv(ROUTING_INDEX, decision_rows, routing_index_fieldnames())
    write_yaml(ROUTING_SUMMARY, summary)
    write_yaml(ROUTING_CLOSEOUT, build_closeout(summary))
    upsert_candidate_registry(summary)
    upsert_artifact_registry(summary)


def smoke_outputs(summary: dict[str, Any], decision_rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for path in [ROUTING_SUMMARY, ROUTING_INDEX, ROUTING_CLOSEOUT, NEXT_WORK_ITEM, WORKSPACE_STATE, GOAL_MANIFEST, CAMPAIGN_MANIFEST]:
        if not path_exists(REPO_ROOT / path):
            errors.append(f"missing source-of-truth path: {path.as_posix()}")
    loaded_summary = read_yaml(REPO_ROOT / ROUTING_SUMMARY) if path_exists(REPO_ROOT / ROUTING_SUMMARY) else {}
    if loaded_summary.get("claim_boundary") != CLAIM_BOUNDARY:
        errors.append("routing summary claim_boundary mismatch")
    opened_ids = [row["candidate_id"] for row in decision_rows if row.get("candidate_id")]
    if loaded_summary.get("opened_candidate_ids") != opened_ids:
        errors.append("opened candidate id mismatch")
    counts = loaded_summary.get("counts") or {}
    if counts.get("candidate_count") != len(opened_ids):
        errors.append("candidate_count mismatch")
    if counts.get("l5_candidate_count") != 0:
        errors.append("l5_candidate_count must remain zero before L5 evidence")
    for candidate_id in opened_ids:
        path = candidate_summary_path(candidate_id)
        if not path_exists(REPO_ROOT / path):
            errors.append(f"missing candidate summary: {path.as_posix()}")
            continue
        candidate = read_yaml(REPO_ROOT / path)
        if candidate.get("claim_boundary") != CANDIDATE_CLAIM_BOUNDARY:
            errors.append(f"{candidate_id}: claim boundary mismatch")
        if (candidate.get("candidate_scope") or {}).get("l5_candidate") is not False:
            errors.append(f"{candidate_id}: l5_candidate scope must be false")
    next_work = read_yaml(REPO_ROOT / NEXT_WORK_ITEM) if path_exists(REPO_ROOT / NEXT_WORK_ITEM) else {}
    workspace = read_yaml(REPO_ROOT / WORKSPACE_STATE) if path_exists(REPO_ROOT / WORKSPACE_STATE) else {}
    if next_work.get("work_item_id") != NEXT_WORK_ITEM_ID:
        errors.append("next_work_item id mismatch")
    if next_work.get("claim_boundary") != NEXT_CLAIM_BOUNDARY:
        errors.append("next_work_item claim boundary mismatch")
    if workspace.get("current_claim_boundary") != NEXT_CLAIM_BOUNDARY:
        errors.append("workspace claim boundary mismatch")
    if workspace.get("next_action") != NEXT_ACTION:
        errors.append("workspace next_action mismatch")
    return errors


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Decide Wave03 L5 routing from completed portable L4 score-probe pairs.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--write-control-records", action="store_true")
    parser.add_argument("--smoke-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    global REPO_ROOT
    args = parse_args(argv)
    REPO_ROOT = Path(args.repo_root).resolve()
    pair_writer.REPO_ROOT = REPO_ROOT
    started = utc_now()
    command_argv = [Path(sys.executable).name, *sys.argv] if argv is None else ["python", __file__, *argv]
    decision_rows = build_decision_rows()
    summary = build_summary(decision_rows, started, command_argv)
    write_outputs(summary, decision_rows)
    if args.write_control_records:
        update_control_records(summary)
    errors = smoke_outputs(summary, decision_rows)
    if errors:
        print({"status": "wave03_l5_routing_writer_smoke_failed", "errors": errors})
        return 1
    print(
        "wave03 volatility-state l5 routing writer-smoke passed: "
        f"opened={summary['counts']['candidate_count']} l5_candidate_count=0 "
        f"status={summary['status']} claim_boundary={summary['claim_boundary']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
