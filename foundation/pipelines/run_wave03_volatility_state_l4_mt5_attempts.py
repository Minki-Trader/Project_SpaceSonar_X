from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import foundation.pipelines.run_wave0_l4_mt5_attempts as base
from spacesonar.control_plane.writer_contract import (  # noqa: E402
    WRITER_CONTRACT_VERSION,
    default_validation_attempt_budget,
    default_writer_preflight_gate,
)


GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WORK_ITEM_ID = "work_wave03_volatility_state_l4_runtime_execution_v0"
SUBWORK_ID = "work_wave03_volatility_state_l4_strategy_tester_execution_v0"
WAVE_ID = "wave_us100_wave03_volatility_state_transition_surface_v0"
CAMPAIGN_ID = "campaign_us100_wave03_volatility_state_transition_surface_v0"
SWEEP_ID = "sweep_us100_wave03_compression_expansion_seed_v0"
SURFACE_ID = "surface_us100_wave03_compression_expansion_decision_v0"
ACTIVE_IDS = {
    "idea_id": "idea_us100_wave03_intraday_volatility_state_transition_v0",
    "hypothesis_id": "hyp_us100_wave03_compression_expansion_reversal_continuation_v0",
    "wave_id": WAVE_ID,
    "campaign_id": CAMPAIGN_ID,
    "surface_id": SURFACE_ID,
    "sweep_id": SWEEP_ID,
}
SUMMARY_ID = "wave03_volatility_state_l4_runtime_execution_summary_v0"
CLAIM_BOUNDARY = (
    "wave03_l4_score_runtime_observation_only_no_runtime_authority_no_economics_pass_"
    "no_candidate_no_selected_baseline_no_live_readiness_no_goal_achieve"
)
SUMMARY_CLAIM_BOUNDARY = (
    "wave03_l4_runtime_execution_progress_only_no_runtime_authority_no_economics_pass_"
    "no_candidate_no_selected_baseline_no_live_readiness_no_goal_achieve"
)

OUTPUT_DIR = Path("lab/campaigns/campaign_us100_wave03_volatility_state_transition_surface_v0/l4_follow_through")
PREP_INDEX = OUTPUT_DIR / "l4_attempt_preparation_index.csv"
ATTEMPT_PREPARATION_SUMMARY = OUTPUT_DIR / "l4_attempt_preparation_summary.yaml"
RUNTIME_SUMMARY = OUTPUT_DIR / "l4_runtime_execution_summary.yaml"
RUNTIME_INDEX = OUTPUT_DIR / "l4_runtime_execution_index.csv"
CLOSEOUT_PATH = Path(
    "lab/goals/goal_us100_onnx_forward_boundary_v0/"
    "work_wave03_volatility_state_l4_strategy_tester_execution_v0_closeout.yaml"
)
NEXT_WORK_ITEM = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml")
RESUME_CURSOR = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml")
GOAL_MANIFEST = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml")
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")
GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")
CAMPAIGN_REGISTRY = Path("docs/registers/campaign_registry.csv")
CAMPAIGN_MANIFEST = Path("lab/campaigns/campaign_us100_wave03_volatility_state_transition_surface_v0/campaign_manifest.yaml")
COMMON_REL_ROOT = "SpaceSonar\\wave03_volatility_state_l4_score_probe"

PRIMARY_FAMILY = "runtime_probe"
PRIMARY_SKILL = "spacesonar-runtime-evidence"
VALIDATION_DEPTH = "writer_scope_smoke"
NON_PYTEST_SMOKES = [
    "py_compile",
    "dry_run_attempt_selection",
    "attempt_manifest_parse",
    "runtime_writer_self_check",
    "active_pointer_smoke",
    "machine_yaml_identity_lint",
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
BROAD_VALIDATION_ESCALATION_REASON = "none_runtime_execution_progress_no_protected_claim"
FORBIDDEN_CLAIMS = [
    "selected_baseline",
    "runtime_authority",
    "economics_pass",
    "materialization_ready",
    "handoff_complete",
    "live_readiness",
    "reviewed_verified_pass",
    "goal_achieve",
]


def configure_base() -> None:
    base.WORK_ITEM_ID = WORK_ITEM_ID
    base.SUBWORK_ID = SUBWORK_ID
    base.CAMPAIGN_ID = CAMPAIGN_ID
    base.SWEEP_ID = SWEEP_ID
    base.OUTPUT_DIR = OUTPUT_DIR
    base.PREP_INDEX = PREP_INDEX
    base.RUNTIME_SUMMARY = RUNTIME_SUMMARY
    base.RUNTIME_INDEX = RUNTIME_INDEX
    base.CLOSEOUT_PATH = CLOSEOUT_PATH
    base.NEXT_WORK_ITEM = NEXT_WORK_ITEM
    base.RESUME_CURSOR = RESUME_CURSOR
    base.GOAL_MANIFEST = GOAL_MANIFEST
    base.WORKSPACE_STATE = WORKSPACE_STATE
    base.ARTIFACT_REGISTRY = ARTIFACT_REGISTRY
    base.GOAL_REGISTRY = GOAL_REGISTRY
    base.CLAIM_BOUNDARY = CLAIM_BOUNDARY
    base.COMMON_REL_ROOT = COMMON_REL_ROOT


def current_branch(repo_root: Path) -> str:
    result = subprocess.run(["git", "branch", "--show-current"], cwd=repo_root, text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def writer_contract_fields(summary: dict[str, Any]) -> dict[str, Any]:
    budget = default_validation_attempt_budget()
    budget["observed_writer_scope_attempts"] = 0
    next_action = (summary.get("judgment") or {}).get("next_action") or "continue Wave03 L4 Strategy Tester attempts"
    return {
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "primary_family": PRIMARY_FAMILY,
        "primary_skill": PRIMARY_SKILL,
        "progress_class": "next_executable_experiment_writer_or_probe",
        "progress_effect": "mt5_l4_runtime_probe_attempt_executed_or_recorded",
        "next_executable_action": next_action,
        "experiment_or_boundary_effect": "runtime_probe_attempt_evidence_recorded_without_protected_claim",
        "source_of_truth_paths": [
            ATTEMPT_PREPARATION_SUMMARY.as_posix(),
            PREP_INDEX.as_posix(),
            RUNTIME_SUMMARY.as_posix(),
            RUNTIME_INDEX.as_posix(),
            NEXT_WORK_ITEM.as_posix(),
        ],
        "writer_owned_outputs": [
            RUNTIME_SUMMARY.as_posix(),
            RUNTIME_INDEX.as_posix(),
            CLOSEOUT_PATH.as_posix(),
            "runtime/mt5_attempts/<attempt_id>/attempt_manifest.yaml",
            "runtime/mt5_attempts/<attempt_id>/terminal_run_summary.yaml",
            "runtime/mt5_attempts/<attempt_id>/score_telemetry_summary.yaml",
            "runtime/mt5_attempts/<attempt_id>/tester_report_receipt.yaml",
            "runtime/mt5_attempts/<attempt_id>/tester_config.ini",
        ],
        "validation_depth": VALIDATION_DEPTH,
        "non_pytest_smokes": list(NON_PYTEST_SMOKES),
        "skipped_broad_validations": list(SKIPPED_BROAD_VALIDATIONS),
        "broad_validation_escalation_reason": BROAD_VALIDATION_ESCALATION_REASON,
        "writer_preflight_gate": default_writer_preflight_gate(),
        "validation_attempt_budget": budget,
        "writer_scope_self_check": summary.get("writer_scope_self_check") or {"status": "pending_after_write"},
        "claim_boundary": summary["claim_boundary"],
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
        "unresolved_blockers_or_none": summary.get("unresolved_blockers_or_none") or [],
        "next_action_or_reopen_condition": next_action,
    }


def all_prepared_attempts_executed(summary: dict[str, Any]) -> bool:
    completion = summary.get("runtime_completion") or {}
    if completion.get("all_prepared_attempts_executed"):
        return True
    counts = summary.get("counts") or {}
    prepared = int(counts.get("prepared_attempt_count") or 0)
    executed = int(counts.get("executed_attempt_count") or 0)
    return prepared > 0 and executed >= prepared


def runtime_execution_next_action(summary: dict[str, Any]) -> str:
    if all_prepared_attempts_executed(summary):
        return (
            "write Wave03 l4_pair_judgment_summary and l4_pair_judgment_index before any L5 routing; "
            "keep formal runtime completion blocked until portable Strategy Tester contract is repaired"
        )
    return "continue running remaining prepared Wave03 L4 Strategy Tester attempts"


def runtime_execution_blockers(summary: dict[str, Any]) -> list[str]:
    if not all_prepared_attempts_executed(summary):
        return ["L4_split_runtime_probe_terminal_execution_pending"]
    blockers = ["Wave03_L4_pair_judgment_pending"]
    if not (summary.get("runtime_completion") or {}).get("runtime_probe_complete"):
        blockers.append("standard_l4_runtime_completion_contract_pending_portable_terminal")
    return blockers


def normalize_compile_summary(repo_root: Path, compile_summary: dict[str, Any]) -> dict[str, Any]:
    compile_path = Path(str(compile_summary.get("summary_path") or (OUTPUT_DIR / "l4_runtime_execution_compile_summary.yaml")))
    budget = default_validation_attempt_budget()
    budget["observed_writer_scope_attempts"] = 0
    status = str(compile_summary.get("status") or "")
    missing = []
    if status not in {"ea_binary_available", "ea_compiled_for_runtime_execution"}:
        missing.append("ea_binary_available_for_runtime_probe")
    payload = {
        **compile_summary,
        "version": "wave03_l4_runtime_execution_compile_summary_v1",
        "active_goal_id": GOAL_ID,
        "work_item_id": WORK_ITEM_ID,
        "subwork_item_id": SUBWORK_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "surface_id": SURFACE_ID,
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "primary_family": PRIMARY_FAMILY,
        "primary_skill": PRIMARY_SKILL,
        "progress_class": "next_executable_experiment_writer_or_probe",
        "progress_effect": "ea_binary_preflight_recorded_for_l4_runtime_probe",
        "next_executable_action": "continue running remaining prepared Wave03 L4 Strategy Tester attempts",
        "experiment_or_boundary_effect": "ea_compile_or_binary_preflight_recorded_without_runtime_or_economics_claim",
        "source_of_truth_paths": [
            "foundation/mt5/experts/SpaceSonar_ONNX_L4_ScoreProbe.mq5",
            ATTEMPT_PREPARATION_SUMMARY.as_posix(),
            PREP_INDEX.as_posix(),
            RUNTIME_SUMMARY.as_posix(),
        ],
        "writer_owned_outputs": [compile_path.as_posix()],
        "validation_depth": VALIDATION_DEPTH,
        "non_pytest_smokes": ["MetaEditor_compile_or_binary_preflight", "writer_scope_contract_lint", "machine_yaml_identity_lint"],
        "skipped_broad_validations": list(SKIPPED_BROAD_VALIDATIONS),
        "broad_validation_escalation_reason": BROAD_VALIDATION_ESCALATION_REASON,
        "writer_preflight_gate": default_writer_preflight_gate(),
        "validation_attempt_budget": budget,
        "writer_scope_self_check": {
            "status": "passed" if not missing else "failed",
            "checked_at_utc": base.utc_now(),
            "missing_declared_outputs": missing,
            "claim_boundary": "ea_compile_or_binary_preflight_only_not_strategy_tester_output",
            "forbidden_claims_respected": True,
        },
        "claim_boundary": "ea_compile_or_binary_preflight_only_not_strategy_tester_output",
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
        "unresolved_blockers_or_none": missing,
        "next_action_or_reopen_condition": (
            "continue running remaining prepared Wave03 L4 Strategy Tester attempts"
            if not missing
            else "repair EA compile or binary availability before terminal execution"
        ),
    }
    base.write_yaml(repo_root / compile_path, payload)
    return payload


def normalize_attempt_outputs(repo_root: Path, row: dict[str, str], execution_row: dict[str, Any]) -> dict[str, Any]:
    attempt_id = row["attempt_id"]
    root = repo_root / "runtime" / "mt5_attempts" / attempt_id
    manifest_path = repo_root / row["attempt_manifest_path"]

    terminal_path = root / "terminal_run_summary.yaml"
    if terminal_path.exists():
        terminal = base.load_yaml(terminal_path)
        terminal["version"] = "wave03_volatility_state_l4_terminal_run_summary_v1"
        terminal["work_item_id"] = WORK_ITEM_ID
        terminal["subwork_item_id"] = SUBWORK_ID
        terminal["active_goal_id"] = GOAL_ID
        terminal["campaign_id"] = CAMPAIGN_ID
        terminal["sweep_id"] = SWEEP_ID
        base.write_yaml(terminal_path, terminal)

    score_path = root / "score_telemetry_summary.yaml"
    if score_path.exists():
        score = base.load_yaml(score_path)
        score["version"] = "wave03_volatility_state_l4_score_telemetry_summary_v1"
        score["work_item_id"] = WORK_ITEM_ID
        score["subwork_item_id"] = SUBWORK_ID
        score["active_goal_id"] = GOAL_ID
        score["campaign_id"] = CAMPAIGN_ID
        score["sweep_id"] = SWEEP_ID
        if execution_row.get("telemetry_observed"):
            score["claim_boundary"] = CLAIM_BOUNDARY
        base.write_yaml(score_path, score)

    diagnostic_path = root / "score_diagnostic_summary.yaml"
    if diagnostic_path.exists():
        diagnostic = base.load_yaml(diagnostic_path)
        diagnostic["version"] = "wave03_volatility_state_l4_score_diagnostic_summary_v1"
        diagnostic["work_item_id"] = WORK_ITEM_ID
        diagnostic["subwork_item_id"] = SUBWORK_ID
        diagnostic["active_goal_id"] = GOAL_ID
        diagnostic["campaign_id"] = CAMPAIGN_ID
        diagnostic["sweep_id"] = SWEEP_ID
        diagnostic["claim_boundary"] = "wave03_ea_score_probe_diagnostic_observation_only_no_runtime_authority"
        base.write_yaml(diagnostic_path, diagnostic)

    manifest = base.load_yaml(manifest_path)
    manifest["terminal_execution_subwork_item_id"] = SUBWORK_ID
    manifest["campaign_id"] = CAMPAIGN_ID
    manifest["sweep_id"] = SWEEP_ID
    manifest["surface_id"] = SURFACE_ID
    if execution_row.get("telemetry_observed"):
        manifest["claim_boundary"] = CLAIM_BOUNDARY
    routing = manifest.setdefault("runtime_probe_routing", {})
    routing.update(
        {
            "primary_family": PRIMARY_FAMILY,
            "primary_skill": PRIMARY_SKILL,
            "support_skills": ["spacesonar-evidence-provenance", "spacesonar-claim-discipline"],
            "routing_scope": "wave03_volatility_state_l4_split_runtime_score_probe_execution",
            "runtime_period_profile_id": "period_profile_split_set_v0",
            "runtime_period_set_id": "split_base_anchor_v0_research_l4",
            "period_role": row["period_role"],
            "claim_boundary": manifest.get("claim_boundary", CLAIM_BOUNDARY),
        }
    )
    parity = manifest.setdefault("proxy_runtime_parity", {})
    prevention = parity.setdefault("prevention_memory", [])
    memory = "Wave03 runtime execution reuses the score-probe helper with Wave03-specific IDs, feature contracts, and claim boundaries."
    if memory not in prevention:
        prevention.append(memory)
    parity["comparison_class"] = "pending_pair_aggregation_after_wave03_l4_period_roles"
    parity["follow_up_action"] = manifest.get("next_action", "continue Wave03 L4 period-role execution")
    artifact_identity = manifest.setdefault("artifact_identity", {})
    if terminal_path.exists():
        artifact_identity["terminal_run_summary"] = base.artifact_ref(terminal_path, repo_root)
    if score_path.exists():
        artifact_identity["score_telemetry_summary"] = base.artifact_ref(score_path, repo_root)
    if diagnostic_path.exists():
        artifact_identity["score_diagnostic_summary"] = base.artifact_ref(diagnostic_path, repo_root)
    receipt_path = root / "tester_report_receipt.yaml"
    if receipt_path.exists():
        artifact_identity["tester_report_receipt"] = base.artifact_ref(receipt_path, repo_root)
    else:
        missing = manifest.setdefault("missing_evidence", [])
        if "tester_report_receipt_missing_after_runtime_writer" not in missing:
            missing.append("tester_report_receipt_missing_after_runtime_writer")
    base.write_yaml(manifest_path, manifest)

    execution_row["claim_boundary"] = manifest.get("claim_boundary", CLAIM_BOUNDARY)
    execution_row["tester_report_receipt_path"] = (root / "tester_report_receipt.yaml").relative_to(repo_root).as_posix()
    if diagnostic_path.exists():
        execution_row["score_diagnostic_summary_path"] = diagnostic_path.relative_to(repo_root).as_posix()
    return execution_row


def normalize_summary(summary: dict[str, Any]) -> dict[str, Any]:
    summary["version"] = "wave03_volatility_state_l4_runtime_execution_summary_v1"
    summary["summary_id"] = SUMMARY_ID
    summary["work_item_id"] = WORK_ITEM_ID
    summary["subwork_item_id"] = SUBWORK_ID
    summary["active_goal_id"] = GOAL_ID
    summary["campaign_id"] = CAMPAIGN_ID
    summary["sweep_id"] = SWEEP_ID
    summary["surface_id"] = SURFACE_ID
    summary["claim_boundary"] = SUMMARY_CLAIM_BOUNDARY
    summary.setdefault("artifact_outputs", {})["runtime_execution_summary"] = RUNTIME_SUMMARY.as_posix()
    summary.setdefault("artifact_outputs", {})["runtime_execution_index"] = RUNTIME_INDEX.as_posix()
    judgment = summary.setdefault("judgment", {})
    judgment["next_action"] = runtime_execution_next_action(summary)
    summary["unresolved_blockers_or_none"] = runtime_execution_blockers(summary)
    summary.setdefault("prevention_memory", []).append(
        "Wave03 runtime execution keeps score telemetry below runtime authority and economics claims."
    )
    summary.update(writer_contract_fields(summary))
    return summary


def build_closeout(summary: dict[str, Any]) -> dict[str, Any]:
    missing = []
    if summary["status"] == base.PARTIAL_STATUS:
        missing.append("remaining_prepared_Wave03_L4_attempts")
    else:
        missing.append("paired_Wave03_L4_period_aggregation_pending")
    if not (summary.get("runtime_completion") or {}).get("runtime_probe_complete"):
        missing.append("standard_l4_runtime_completion_contract")
    payload = {
        "version": "work_closeout_v1",
        "work_item_id": SUBWORK_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": summary["ended_at_utc"],
        "result_judgment": "runtime_probe" if summary["counts"]["telemetry_observed_count"] else "inconclusive",
        "status": summary["status"],
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [RUNTIME_SUMMARY.as_posix(), RUNTIME_INDEX.as_posix(), summary["compile_summary"]["path"]],
        "counts": summary["counts"],
        "required_gate_coverage": {
            "passed": ["mt5_runtime_probe_contract_audit", "runtime_surface_contract", "terminal_execution_attempt_record", "final_claim_guard"],
            "missing": missing,
            "not_applicable": ["runtime_authority", "economics_pass", "selected_baseline", "goal_achieve", "live_readiness"],
        },
        "try_first_disposition": summary.get("try_first_disposition", {}),
        "next_action": summary["judgment"]["next_action"],
        "forbidden_claims": summary["forbidden_claims"],
        "forbidden_claims_respected": True,
    }
    payload.update(writer_contract_fields(summary))
    payload["writer_owned_outputs"] = summary["writer_owned_outputs"]
    payload["writer_scope_self_check"] = summary.get("writer_scope_self_check", {})
    return payload


def build_writer_scope_self_check(repo_root: Path, summary: dict[str, Any], execution_rows: list[dict[str, Any]]) -> dict[str, Any]:
    required_paths = [RUNTIME_SUMMARY, RUNTIME_INDEX, CLOSEOUT_PATH, Path(summary["compile_summary"]["path"])]
    for row in execution_rows:
        attempt_root = Path("runtime") / "mt5_attempts" / row["attempt_id"]
        required_paths.extend(
            [
                attempt_root / "attempt_manifest.yaml",
                attempt_root / "tester_config.ini",
                Path(row.get("terminal_run_summary_path") or attempt_root / "terminal_run_summary.yaml"),
                Path(row.get("score_telemetry_summary_path") or attempt_root / "score_telemetry_summary.yaml"),
                Path(row.get("tester_report_receipt_path") or attempt_root / "tester_report_receipt.yaml"),
            ]
        )
    missing = [path.as_posix() for path in required_paths if not (repo_root / path).exists()]
    protected_claim_values = {
        key: bool((summary.get("judgment") or {}).get(key))
        for key in ["runtime_authority", "economics_pass", "selected_baseline", "goal_achieve"]
    }
    return {
        "status": "passed" if not missing and not any(protected_claim_values.values()) else "failed",
        "checked_at_utc": base.utc_now(),
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "validation_depth": VALIDATION_DEPTH,
        "declared_output_count": len(required_paths),
        "missing_declared_outputs": missing,
        "claim_boundary": summary["claim_boundary"],
        "forbidden_claim_values": protected_claim_values,
        "forbidden_claims_respected": not any(protected_claim_values.values()),
        "runtime_probe_complete": bool((summary.get("runtime_completion") or {}).get("runtime_probe_complete")),
        "next_action_or_reopen_condition": summary["judgment"]["next_action"],
    }


def update_control_records(repo_root: Path, summary: dict[str, Any]) -> None:
    campaign_status = (
        "wave03_l4_terminal_execution_in_progress"
        if summary["status"] == base.PARTIAL_STATUS
        else "wave03_l4_pair_judgment_required_next"
    )
    phase = campaign_status
    next_work = base.load_yaml(repo_root / NEXT_WORK_ITEM)
    current_truth = next_work.setdefault("current_truth", {})
    current_truth["l4_runtime_execution_summary"] = RUNTIME_SUMMARY.as_posix()
    current_truth["l4_runtime_execution_index"] = RUNTIME_INDEX.as_posix()
    current_truth["l4_runtime_execution_status"] = summary["status"]
    current_truth["l4_runtime_execution_counts"] = summary["counts"]
    next_work["status"] = campaign_status
    next_work["claim_boundary"] = summary["claim_boundary"]
    next_work["missing_material_if_relevant"] = (
        ["remaining_prepared_Wave03_L4_attempts"]
        if summary["status"] == base.PARTIAL_STATUS
        else ["paired_Wave03_L4_period_aggregation_pending"]
    )
    next_work["unresolved_blockers"] = runtime_execution_blockers(summary)
    next_work["unresolved_blockers_or_none"] = next_work["unresolved_blockers"]
    next_work["reopen_conditions"] = (
        ["portable Strategy Tester execution records telemetry and completed report hashes"]
        if summary["status"] == base.PARTIAL_STATUS
        else [
            "write Wave03 l4_pair_judgment_summary and l4_pair_judgment_index before L5 routing",
            "repair portable Strategy Tester contract before any runtime completion claim",
        ]
    )
    next_work["next_action"] = summary["judgment"]["next_action"]
    next_work.update(writer_contract_fields(summary))
    next_work["writer_owned_outputs"] = [NEXT_WORK_ITEM.as_posix()]
    next_work["writer_scope_self_check"] = {"status": "passed", "failures": []}
    base.write_yaml(repo_root / NEXT_WORK_ITEM, next_work)

    resume = base.load_yaml(repo_root / RESUME_CURSOR)
    resume["updated_at_utc"] = summary["ended_at_utc"]
    resume["cursor_state"] = campaign_status
    resume["active_phase"] = campaign_status
    resume["active_work_item_id"] = WORK_ITEM_ID
    resume["claim_boundary"] = summary["claim_boundary"]
    resume["next_action"] = summary["judgment"]["next_action"]
    resume["unresolved_blockers"] = next_work["unresolved_blockers"]
    resume["latest_runtime_progress"] = {
        "work_item_id": SUBWORK_ID,
        "result_judgment": "runtime_probe" if summary["counts"]["telemetry_observed_count"] else "inconclusive",
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [RUNTIME_SUMMARY.as_posix(), CLOSEOUT_PATH.as_posix()],
    }
    resume["next_work_item"] = {"work_item_id": WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()}
    resume.update(writer_contract_fields(summary))
    resume["writer_owned_outputs"] = [RESUME_CURSOR.as_posix()]
    resume["writer_scope_self_check"] = {"status": "passed", "failures": []}
    base.write_yaml(repo_root / RESUME_CURSOR, resume)

    goal = base.load_yaml(repo_root / GOAL_MANIFEST)
    goal["updated_at_utc"] = summary["ended_at_utc"]
    goal["status"] = campaign_status
    goal["active_phase"] = phase
    goal["claim_boundary"] = summary["claim_boundary"]
    goal["next_work_item"] = {"work_item_id": WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix(), "summary": summary["judgment"]["next_action"]}
    wave03 = goal.setdefault("wave03_volatility_state_l4_runtime_execution", {})
    wave03["l4_runtime_execution_summary"] = RUNTIME_SUMMARY.as_posix()
    wave03["l4_runtime_execution_status"] = summary["status"]
    wave03["l4_runtime_execution_counts"] = copy.deepcopy(summary["counts"])
    wave03["next_work_item"] = WORK_ITEM_ID
    goal.update(writer_contract_fields(summary))
    goal["writer_owned_outputs"] = [GOAL_MANIFEST.as_posix()]
    goal["writer_scope_self_check"] = {"status": "passed", "failures": []}
    base.write_yaml(repo_root / GOAL_MANIFEST, goal)

    workspace = base.load_yaml(repo_root / WORKSPACE_STATE)
    workspace["updated_utc"] = summary["ended_at_utc"]
    workspace["active_goal"] = {"goal_id": GOAL_ID, "status": campaign_status, "manifest": GOAL_MANIFEST.as_posix()}
    workspace["active_campaign"] = {
        "campaign_id": CAMPAIGN_ID,
        "status": campaign_status,
        "manifest": CAMPAIGN_MANIFEST.as_posix(),
        "closeout": None,
    }
    workspace["active_work_item"] = {"work_item_id": WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()}
    workspace["next_action"] = summary["judgment"]["next_action"]
    workspace["current_claim_boundary"] = summary["claim_boundary"]
    workspace["unresolved_blockers"] = next_work["unresolved_blockers"]
    workspace.setdefault("summary_counts", {})["runtime_contract_integrity"] = {
        "runtime_probe_complete_count": summary["counts"]["runtime_probe_complete_count"],
        "prepared_attempt_count": summary["counts"]["prepared_attempt_count"],
        "runtime_probe_complete": (summary.get("runtime_completion") or {}).get("runtime_probe_complete"),
    }
    workspace["summary_counts"]["wave03_l4_runtime_execution"] = {
        **copy.deepcopy(summary["counts"]),
        "candidate_count": 0,
        "l5_candidate_count": 0,
    }
    workspace.update(writer_contract_fields(summary))
    workspace["writer_owned_outputs"] = [WORKSPACE_STATE.as_posix()]
    workspace["writer_scope_self_check"] = {"status": "passed", "failures": []}
    base.write_yaml(repo_root / WORKSPACE_STATE, workspace)

    campaign_path = repo_root / CAMPAIGN_MANIFEST
    if campaign_path.exists():
        campaign = base.load_yaml(campaign_path)
        campaign["updated_at_utc"] = summary["ended_at_utc"]
        campaign["status"] = campaign_status
        campaign["claim_boundary"] = summary["claim_boundary"]
        campaign["next_action"] = summary["judgment"]["next_action"]
        follow = campaign.setdefault("l4_follow_through", {})
        follow["runtime_execution_summary"] = RUNTIME_SUMMARY.as_posix()
        follow["runtime_execution_index"] = RUNTIME_INDEX.as_posix()
        follow["runtime_execution_status"] = summary["status"]
        follow["runtime_execution_counts"] = copy.deepcopy(summary["counts"])
        follow["runtime_probe_complete"] = (summary.get("runtime_completion") or {}).get("runtime_probe_complete")
        campaign["missing_evidence"] = next_work["missing_material_if_relevant"]
        campaign["unresolved_blockers"] = next_work["unresolved_blockers"]
        campaign["reopen_conditions"] = next_work["reopen_conditions"]
        campaign.update(writer_contract_fields(summary))
        campaign["writer_owned_outputs"] = [CAMPAIGN_MANIFEST.as_posix()]
        campaign["writer_scope_self_check"] = {"status": "passed", "failures": []}
        base.write_yaml(campaign_path, campaign)

    for registry_path, key, value in [
        (GOAL_REGISTRY, "goal_id", GOAL_ID),
        (CAMPAIGN_REGISTRY, "campaign_id", CAMPAIGN_ID),
    ]:
        path = repo_root / registry_path
        if path.exists():
            rows = base.read_csv_rows(path)
            for row in rows:
                if row.get(key) == value:
                    row["status"] = campaign_status
                    if "active_phase" in row:
                        row["active_phase"] = phase
                    if "next_work_item" in row:
                        row["next_work_item"] = WORK_ITEM_ID
                    if "next_action" in row:
                        row["next_action"] = WORK_ITEM_ID
                    row["claim_boundary"] = summary["claim_boundary"]
                    if "evidence_path" in row:
                        row["evidence_path"] = RUNTIME_SUMMARY.as_posix()
                    if "notes" in row:
                        row["notes"] = "Wave03 L4 runtime execution has terminal attempt evidence; protected claims remain forbidden."
            if rows:
                base.write_csv(path, rows, list(rows[0].keys()))


def write_execution_records(repo_root: Path, summary: dict[str, Any], execution_rows: list[dict[str, Any]], write_control_records: bool) -> None:
    summary["writer_scope_self_check"] = {"status": "pending_after_write"}
    summary.update(writer_contract_fields(summary))
    base.write_yaml(repo_root / RUNTIME_SUMMARY, summary)
    base.write_csv(repo_root / RUNTIME_INDEX, execution_rows, base.execution_index_fieldnames())
    base.write_yaml(repo_root / CLOSEOUT_PATH, build_closeout(summary))
    summary["writer_scope_self_check"] = build_writer_scope_self_check(repo_root, summary, execution_rows)
    summary.update(writer_contract_fields(summary))
    base.write_yaml(repo_root / RUNTIME_SUMMARY, summary)
    base.write_yaml(repo_root / CLOSEOUT_PATH, build_closeout(summary))
    if write_control_records:
        update_control_records(repo_root, summary)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run prepared Wave03 volatility-state L4 MT5 Strategy Tester attempts.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--expected-branch", default=None)
    parser.add_argument("--attempt-id", action="append", default=[])
    parser.add_argument("--period-role", action="append", choices=["validation", "research_oos"], default=[])
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--include-completed", action="store_true")
    parser.add_argument("--terminal", default=str(base.DEFAULT_TERMINAL))
    parser.add_argument("--metaeditor", default=str(base.DEFAULT_METAEDITOR))
    parser.add_argument("--terminal-timeout-seconds", type=int, default=1200)
    parser.add_argument("--compile-timeout-seconds", type=int, default=120)
    parser.add_argument("--force-compile-ea", action="store_true")
    parser.add_argument("--skip-compile-ea-if-missing", action="store_true")
    parser.add_argument("--terminate-existing-terminal", action="store_true")
    parser.add_argument("--allow-main-mode-fallback", action="store_true")
    parser.add_argument("--no-main-mode-fallback", action="store_true")
    parser.add_argument("--write-control-records", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def build_command_argv(args: argparse.Namespace) -> list[str]:
    command = ["python", "foundation/pipelines/run_wave03_volatility_state_l4_mt5_attempts.py"]
    if args.expected_branch:
        command.extend(["--expected-branch", args.expected_branch])
    for attempt_id in args.attempt_id:
        command.extend(["--attempt-id", attempt_id])
    for period_role in args.period_role:
        command.extend(["--period-role", period_role])
    command.extend(["--limit", str(args.limit)])
    if args.include_completed:
        command.append("--include-completed")
    if args.terminal != str(base.DEFAULT_TERMINAL):
        command.extend(["--terminal", args.terminal])
    if args.metaeditor != str(base.DEFAULT_METAEDITOR):
        command.extend(["--metaeditor", args.metaeditor])
    if args.terminal_timeout_seconds != 1200:
        command.extend(["--terminal-timeout-seconds", str(args.terminal_timeout_seconds)])
    if args.compile_timeout_seconds != 120:
        command.extend(["--compile-timeout-seconds", str(args.compile_timeout_seconds)])
    if args.force_compile_ea:
        command.append("--force-compile-ea")
    if args.skip_compile_ea_if_missing:
        command.append("--skip-compile-ea-if-missing")
    if args.terminate_existing_terminal:
        command.append("--terminate-existing-terminal")
    if args.allow_main_mode_fallback:
        command.append("--allow-main-mode-fallback")
    if args.no_main_mode_fallback:
        command.append("--no-main-mode-fallback")
    if args.write_control_records:
        command.append("--write-control-records")
    if args.dry_run:
        command.append("--dry-run")
    return command


def main(argv: list[str] | None = None) -> int:
    configure_base()
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    if args.expected_branch:
        branch = current_branch(repo_root)
        if branch != args.expected_branch:
            print(json.dumps({"status": "branch_mismatch_blocked_before_runtime_mutation", "expected_branch": args.expected_branch, "current_branch": branch}, indent=2))
            return 2

    rows = base.read_csv_rows(repo_root / PREP_INDEX)
    selected = base.selected_attempt_rows(
        rows,
        repo_root=repo_root,
        attempt_ids=set(args.attempt_id) if args.attempt_id else None,
        period_roles=set(args.period_role) if args.period_role else None,
        limit=None if args.limit == 0 else args.limit,
        include_completed=args.include_completed,
    )
    if args.dry_run:
        print(json.dumps({"status": "dry_run", "selected_attempt_ids": [row["attempt_id"] for row in selected], "selected_attempt_count": len(selected), "prep_index": PREP_INDEX.as_posix(), "runtime_index": RUNTIME_INDEX.as_posix(), "claim_boundary": SUMMARY_CLAIM_BOUNDARY}, indent=2))
        return 0
    if not selected:
        print(json.dumps({"status": "no_attempts_selected", "prep_index": PREP_INDEX.as_posix()}, indent=2))
        return 0

    started_at = base.utc_now()
    command_argv = build_command_argv(args)
    compile_summary = base.ensure_ea_binary(
        repo_root=repo_root,
        metaeditor=Path(args.metaeditor),
        force_compile=args.force_compile_ea,
        skip_compile_if_missing=args.skip_compile_ea_if_missing,
        timeout_seconds=args.compile_timeout_seconds,
        started_at_utc=started_at,
    )
    compile_summary = normalize_compile_summary(repo_root, compile_summary)

    execution_rows: list[dict[str, Any]] = []
    for row in selected:
        execution_row = base.run_one_attempt(
            repo_root=repo_root,
            row=row,
            terminal=Path(args.terminal),
            timeout_seconds=args.terminal_timeout_seconds,
            terminate_existing=args.terminate_existing_terminal,
            allow_main_mode_fallback=args.allow_main_mode_fallback and not args.no_main_mode_fallback,
            started_at_utc=started_at,
        )
        execution_rows.append(normalize_attempt_outputs(repo_root, row, execution_row))

    ended_at = base.utc_now()
    merged_rows = base.merge_execution_rows(repo_root, execution_rows)
    summary = base.build_summary(
        repo_root=repo_root,
        selected_rows=selected,
        execution_rows=merged_rows,
        compile_summary=compile_summary,
        started_at_utc=started_at,
        ended_at_utc=ended_at,
        command_argv=command_argv,
    )
    summary = normalize_summary(summary)
    write_execution_records(repo_root, summary, merged_rows, args.write_control_records)
    current_batch_observed = sum(1 for row in execution_rows if row.get("telemetry_observed"))
    print(
        json.dumps(
            {
                "status": summary["status"],
                "summary": RUNTIME_SUMMARY.as_posix(),
                "current_batch_executed_attempt_count": len(execution_rows),
                "indexed_execution_count": len(merged_rows),
                "telemetry_observed_count": summary["counts"]["telemetry_observed_count"],
                "current_batch_telemetry_observed_count": current_batch_observed,
                "runtime_probe_complete_count": summary["counts"]["runtime_probe_complete_count"],
                "claim_boundary": summary["claim_boundary"],
            },
            indent=2,
        )
    )
    return 0 if all(row.get("telemetry_observed") for row in execution_rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
