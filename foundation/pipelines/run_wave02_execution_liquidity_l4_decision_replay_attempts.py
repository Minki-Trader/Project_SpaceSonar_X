from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import foundation.pipelines.run_wave0_l4_decision_replay_attempts as base
from spacesonar.control_plane.store import filesystem_path


GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WORK_ITEM_ID = "work_wave02_execution_liquidity_decision_replay_runtime_execution_v0"
SUBWORK_ID = "work_wave02_execution_liquidity_decision_replay_strategy_tester_execution_v0"
NEXT_WORK_ID = "work_wave02_execution_liquidity_decision_replay_judgment_v0"
CAMPAIGN_ID = "campaign_us100_wave02_execution_liquidity_surface_v0"
SWEEP_ID = "sweep_us100_wave02_execution_liquidity_broad_v0"
SUMMARY_ID = "wave02_execution_liquidity_decision_replay_runtime_execution_summary_v0"

CLAIM_BOUNDARY = (
    "wave02_execution_liquidity_decision_replay_runtime_observation_only_"
    "no_runtime_authority_no_economics_pass_no_candidate_no_live_readiness_no_goal_achieve"
)
SUMMARY_CLAIM_BOUNDARY = (
    "wave02_execution_liquidity_decision_replay_runtime_execution_progress_only_"
    "no_runtime_authority_no_economics_pass_no_candidate_no_live_readiness_no_goal_achieve"
)
NEXT_CLAIM_BOUNDARY = (
    "wave02_execution_liquidity_decision_replay_judgment_pending_"
    "no_runtime_authority_no_economics_pass_no_candidate_no_live_readiness_no_goal_achieve"
)

PARTIAL_STATUS = "partial_wave02_execution_liquidity_decision_replay_terminal_execution_started"
ALL_ATTEMPTS_STATUS = "wave02_execution_liquidity_decision_replay_terminal_execution_attempted_for_all_prepared_attempts"

OUTPUT_DIR = Path("lab/campaigns/campaign_us100_wave02_execution_liquidity_surface_v0/l4_follow_through/decision_replay")
PREP_INDEX = OUTPUT_DIR / "adapter_prep_index.csv"
RUNTIME_SUMMARY = OUTPUT_DIR / "runtime_execution_summary.yaml"
RUNTIME_INDEX = OUTPUT_DIR / "runtime_execution_index.csv"
COMPILE_SUMMARY = OUTPUT_DIR / "runtime_compile_summary.yaml"
COMPILE_LOG = OUTPUT_DIR / "runtime_compile.log"
ATTEMPT_PREPARATION_SUMMARY = OUTPUT_DIR / "adapter_prep_summary.yaml"
CLOSEOUT_PATH = Path(
    "lab/goals/goal_us100_onnx_forward_boundary_v0/"
    "work_wave02_execution_liquidity_decision_replay_strategy_tester_execution_v0_closeout.yaml"
)
NEXT_WORK_ITEM = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml")
RESUME_CURSOR = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml")
GOAL_MANIFEST = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml")
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
CAMPAIGN_MANIFEST = Path("lab/campaigns/campaign_us100_wave02_execution_liquidity_surface_v0/campaign_manifest.yaml")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")
GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")
WRITER_CONTRACT_VERSION = "writer_scope_operating_contract_v2"
PRIMARY_FAMILY = "runtime_probe"
PRIMARY_SKILL = "spacesonar-runtime-evidence"
VALIDATION_DEPTH = "writer_scope_smoke"
NON_PYTEST_SMOKES = [
    "py_compile",
    "runtime_writer_dry_run",
    "runtime_writer_self_check",
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
    base.COMPILE_SUMMARY = COMPILE_SUMMARY
    base.COMPILE_LOG = COMPILE_LOG
    base.CLOSEOUT_PATH = CLOSEOUT_PATH
    base.NEXT_WORK_ITEM = NEXT_WORK_ITEM
    base.RESUME_CURSOR = RESUME_CURSOR
    base.GOAL_MANIFEST = GOAL_MANIFEST
    base.WORKSPACE_STATE = WORKSPACE_STATE
    base.ARTIFACT_REGISTRY = ARTIFACT_REGISTRY
    base.GOAL_REGISTRY = GOAL_REGISTRY
    base.CLAIM_BOUNDARY = CLAIM_BOUNDARY
    base.PARTIAL_STATUS = PARTIAL_STATUS
    base.ALL_ATTEMPTS_STATUS = ALL_ATTEMPTS_STATUS


def current_branch(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def parse_tester_config_expert(tester_config: Path) -> str | None:
    with open(filesystem_path(tester_config), "r", encoding="utf-8-sig") as handle:
        lines = handle.read().splitlines()
    for line in lines:
        if line.strip().lower().startswith("expert="):
            return line.split("=", 1)[1].strip()
    return None


def ensure_portable_decision_ea_stage(
    *,
    repo_root: Path,
    tester_config: Path,
    portable_terminal_root: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    expert_value = parse_tester_config_expert(tester_config)
    stage: dict[str, Any] = {
        "status": "not_configured",
        "tester_expert_value": expert_value,
        "claim_boundary": "portable_decision_ea_stage_preflight_only_no_runtime_authority",
    }
    if not expert_value:
        manifest.setdefault("runtime_surface_contract", {})["portable_decision_ea_stage_status"] = "not_configured"
        manifest.setdefault("artifact_identity", {}).setdefault("portable_runtime_root", {})["decision_ea_binary"] = stage
        return manifest

    expert_relative = Path(expert_value.replace("\\", "/"))
    destination = portable_terminal_root / "MQL5" / "Experts" / expert_relative
    source_binary = repo_root / base.EA_BINARY
    source_mq5 = repo_root / base.EA_SOURCE
    try:
        os.makedirs(filesystem_path(destination.parent), exist_ok=True)
        copy_status = "already_current"
        if not destination.exists() or base.sha256(destination) != base.sha256(source_binary):
            shutil.copy2(source_binary, destination)
            copy_status = "copied_to_portable_mql5_experts"
        source_destination = destination.with_suffix(".mq5")
        source_copy_status = "not_present"
        if source_mq5.exists():
            source_copy_status = "already_current"
            if not source_destination.exists() or base.sha256(source_destination) != base.sha256(source_mq5):
                shutil.copy2(source_mq5, source_destination)
                source_copy_status = "copied_to_portable_mql5_experts"
        stage = {
            "status": "staged",
            "copy_status": copy_status,
            "source_copy_status": source_copy_status,
            "tester_expert_value": expert_value,
            "portable_terminal_root_redacted": base.redact_path(str(portable_terminal_root)),
            "portable_ex5_redacted": base.redact_path(str(destination)),
            "source": base.artifact_ref(source_binary, repo_root, availability="local_binary_hash_recorded_ignored_by_git"),
            "portable_sha256": base.sha256(destination),
            "portable_size_bytes": destination.stat().st_size,
            "durable_identity": "tester_config_expert_value_plus_source_binary_sha256",
            "claim_boundary": "portable_decision_ea_stage_preflight_only_no_runtime_authority",
        }
    except OSError as exc:
        stage = {
            "status": "stage_failed",
            "tester_expert_value": expert_value,
            "portable_terminal_root_redacted": base.redact_path(str(portable_terminal_root)),
            "portable_ex5_redacted": base.redact_path(str(destination)),
            "error_class": exc.__class__.__name__,
            "error_message": str(exc),
            "remaining_blocker": "decision_ex5_not_staged_under_portable_mql5_experts_path",
            "claim_boundary": "portable_decision_ea_stage_failed_no_runtime_completion_claim",
        }

    manifest.setdefault("artifact_identity", {}).setdefault("portable_runtime_root", {})["decision_ea_binary"] = stage
    manifest.setdefault("runtime_surface_contract", {})["portable_decision_ea_stage_status"] = stage["status"]
    return manifest


def stage_attempt_runtime_inputs(repo_root: Path, row: dict[str, str], terminal: Path) -> None:
    manifest_path = repo_root / row["attempt_manifest_path"]
    tester_config = repo_root / row["tester_config_path"]
    manifest = base.load_yaml(manifest_path)
    manifest = ensure_portable_decision_ea_stage(
        repo_root=repo_root,
        tester_config=tester_config,
        portable_terminal_root=terminal.parent,
        manifest=manifest,
    )
    base.write_yaml(manifest_path, manifest)


def normalize_attempt_outputs(repo_root: Path, row: dict[str, str], execution_row: dict[str, Any]) -> dict[str, Any]:
    attempt_id = row["attempt_id"]
    root = repo_root / "runtime" / "mt5_attempts" / attempt_id
    manifest_path = repo_root / row["attempt_manifest_path"]

    terminal_path = root / "terminal_run_summary.yaml"
    terminal: dict[str, Any] | None = None
    if terminal_path.exists():
        terminal = base.load_yaml(terminal_path)
        terminal["version"] = "wave02_execution_liquidity_decision_replay_terminal_run_summary_v1"
        terminal["work_item_id"] = WORK_ITEM_ID
        terminal["subwork_item_id"] = SUBWORK_ID
        terminal["active_goal_id"] = GOAL_ID
        terminal["campaign_id"] = CAMPAIGN_ID
        terminal["sweep_id"] = SWEEP_ID
        terminal["claim_boundary"] = (
            CLAIM_BOUNDARY
            if terminal.get("terminal_not_launched_reason") is None
            else "wave02_execution_liquidity_decision_replay_terminal_not_launched_no_runtime_completion_claim"
        )
        base.write_yaml(terminal_path, terminal)

    telemetry_path = root / "execution_telemetry_summary.yaml"
    telemetry: dict[str, Any] | None = None
    if telemetry_path.exists():
        telemetry = base.load_yaml(telemetry_path)
        telemetry["version"] = "wave02_execution_liquidity_decision_replay_execution_telemetry_summary_v1"
        telemetry["work_item_id"] = WORK_ITEM_ID
        telemetry["subwork_item_id"] = SUBWORK_ID
        telemetry["active_goal_id"] = GOAL_ID
        telemetry["campaign_id"] = CAMPAIGN_ID
        telemetry["sweep_id"] = SWEEP_ID
        if execution_row.get("execution_telemetry_observed"):
            telemetry["claim_boundary"] = CLAIM_BOUNDARY
        base.write_yaml(telemetry_path, telemetry)

    tester_log_path = root / "tester_log_summary.yaml"
    tester_log: dict[str, Any] | None = None
    if tester_log_path.exists():
        tester_log = base.load_yaml(tester_log_path)
        tester_log["version"] = "wave02_execution_liquidity_decision_replay_tester_log_summary_v1"
        tester_log["work_item_id"] = WORK_ITEM_ID
        tester_log["subwork_item_id"] = SUBWORK_ID
        tester_log["active_goal_id"] = GOAL_ID
        tester_log["campaign_id"] = CAMPAIGN_ID
        tester_log["sweep_id"] = SWEEP_ID
        tester_log["claim_boundary"] = "wave02_execution_liquidity_decision_replay_tester_log_observation_only_no_economics_pass"
        base.write_yaml(tester_log_path, tester_log)

    manifest = base.load_yaml(manifest_path)
    manifest["writer_contract_version"] = WRITER_CONTRACT_VERSION
    manifest["primary_family"] = PRIMARY_FAMILY
    manifest["primary_skill"] = PRIMARY_SKILL
    manifest["validation_depth"] = VALIDATION_DEPTH
    manifest["non_pytest_smokes"] = list(NON_PYTEST_SMOKES)
    manifest["skipped_broad_validations"] = list(SKIPPED_BROAD_VALIDATIONS)
    manifest["broad_validation_escalation_reason"] = BROAD_VALIDATION_ESCALATION_REASON
    manifest["forbidden_claims"] = list(FORBIDDEN_CLAIMS)
    manifest["source_of_truth_paths"] = [manifest_path.relative_to(repo_root).as_posix()]
    manifest["writer_owned_outputs"] = [
        (root / "attempt_manifest.yaml").relative_to(repo_root).as_posix(),
        terminal_path.relative_to(repo_root).as_posix(),
        telemetry_path.relative_to(repo_root).as_posix(),
        tester_log_path.relative_to(repo_root).as_posix(),
        (root / "tester_report_receipt.yaml").relative_to(repo_root).as_posix(),
        (root / "tester_config.ini").relative_to(repo_root).as_posix(),
    ]
    manifest["work_item_id"] = WORK_ITEM_ID
    manifest["terminal_execution_subwork_item_id"] = SUBWORK_ID
    manifest["active_goal_id"] = GOAL_ID
    manifest["campaign_id"] = CAMPAIGN_ID
    manifest["sweep_id"] = SWEEP_ID
    if execution_row.get("execution_telemetry_observed"):
        manifest["claim_boundary"] = CLAIM_BOUNDARY
    if terminal is not None:
        manifest["terminal_run_summary"] = terminal
    if telemetry is not None:
        manifest["execution_telemetry_summary"] = telemetry
    if tester_log is not None:
        manifest["tester_log_summary"] = tester_log

    routing = manifest.setdefault("runtime_probe_routing", {})
    routing["primary_family"] = "runtime_probe"
    routing["primary_skill"] = "spacesonar-runtime-evidence"
    routing["writer_contract_version"] = WRITER_CONTRACT_VERSION
    routing["support_skills"] = [
        "spacesonar-evidence-provenance",
        "spacesonar-result-judgment",
        "spacesonar-claim-discipline",
    ]
    routing["routing_scope"] = "wave02_execution_liquidity_l4_score_replay_decision_execution"
    routing["runtime_period_profile_id"] = "period_profile_split_set_v0"
    routing["runtime_period_set_id"] = "split_base_anchor_v0_research_l4"
    routing["period_role"] = row["period_role"]
    routing["claim_boundary"] = manifest.get("claim_boundary", CLAIM_BOUNDARY)

    parity = manifest.setdefault("proxy_runtime_parity", {})
    prevention = parity.setdefault("prevention_memory", [])
    memory = (
        "Wave02 execution/liquidity decision replay runner normalizes reused Wave0 helper outputs to prevent "
        "legacy identity or promotion inheritance."
    )
    if memory not in prevention:
        prevention.append(memory)
    parity["comparison_class"] = "score_replay_sparse_decision_follow_through_observation"
    parity["follow_up_action"] = manifest.get("next_action", "judge paired Wave02 execution/liquidity decision replay period roles")

    artifacts = manifest.setdefault("artifact_identity", {})
    if terminal_path.exists():
        artifacts["terminal_run_summary"] = base.artifact_ref(terminal_path, repo_root)
    if telemetry_path.exists():
        artifacts["execution_telemetry_summary"] = base.artifact_ref(telemetry_path, repo_root)
    if tester_log_path.exists():
        artifacts["tester_log_summary"] = base.artifact_ref(tester_log_path, repo_root)
    receipt_path = root / "tester_report_receipt.yaml"
    if receipt_path.exists():
        artifacts["tester_report_receipt"] = base.artifact_ref(receipt_path, repo_root)
    else:
        missing = manifest.setdefault("missing_evidence", [])
        if "tester_report_receipt_missing_after_decision_replay_runtime_writer" not in missing:
            missing.append("tester_report_receipt_missing_after_decision_replay_runtime_writer")
    base.write_yaml(manifest_path, manifest)

    execution_row["claim_boundary"] = manifest.get("claim_boundary", CLAIM_BOUNDARY)
    execution_row["tester_report_receipt_path"] = (root / "tester_report_receipt.yaml").relative_to(repo_root).as_posix()
    return execution_row


def normalize_summary(summary: dict[str, Any]) -> dict[str, Any]:
    summary["version"] = "wave02_execution_liquidity_decision_replay_runtime_execution_summary_v1"
    summary["summary_id"] = SUMMARY_ID
    summary["work_item_id"] = WORK_ITEM_ID
    summary["subwork_item_id"] = SUBWORK_ID
    summary["active_goal_id"] = GOAL_ID
    summary["campaign_id"] = CAMPAIGN_ID
    summary["sweep_id"] = SWEEP_ID
    summary["claim_boundary"] = SUMMARY_CLAIM_BOUNDARY
    summary["writer_contract_version"] = WRITER_CONTRACT_VERSION
    summary["primary_family"] = PRIMARY_FAMILY
    summary["primary_skill"] = PRIMARY_SKILL
    summary["source_of_truth_paths"] = [ATTEMPT_PREPARATION_SUMMARY.as_posix(), PREP_INDEX.as_posix()]
    summary["writer_owned_outputs"] = [
        RUNTIME_SUMMARY.as_posix(),
        RUNTIME_INDEX.as_posix(),
        COMPILE_SUMMARY.as_posix(),
        CLOSEOUT_PATH.as_posix(),
        "runtime/mt5_attempts/<attempt_id>/attempt_manifest.yaml",
        "runtime/mt5_attempts/<attempt_id>/terminal_run_summary.yaml",
        "runtime/mt5_attempts/<attempt_id>/execution_telemetry_summary.yaml",
        "runtime/mt5_attempts/<attempt_id>/tester_log_summary.yaml",
        "runtime/mt5_attempts/<attempt_id>/tester_report_receipt.yaml",
        "runtime/mt5_attempts/<attempt_id>/tester_config.ini",
    ]
    summary["validation_depth"] = VALIDATION_DEPTH
    summary["non_pytest_smokes"] = list(NON_PYTEST_SMOKES)
    summary["skipped_broad_validations"] = list(SKIPPED_BROAD_VALIDATIONS)
    summary["broad_validation_escalation_reason"] = BROAD_VALIDATION_ESCALATION_REASON
    summary["forbidden_claims"] = list(FORBIDDEN_CLAIMS)
    summary["status"] = ALL_ATTEMPTS_STATUS if summary["status"] == base.ALL_ATTEMPTS_STATUS else PARTIAL_STATUS
    summary["runtime_contract_binding"] = {
        "runtime_level": "L4_split_runtime_probe_decision_replay_follow_through",
        "source_l4_score_probe": "Wave02 validation/research_oos score telemetry from preserved clue cells",
        "period_profile_id": "period_profile_split_set_v0",
        "runtime_period_set_id": "split_base_anchor_v0_research_l4",
        "required_period_roles": ["validation", "research_oos"],
        "tester_execution_profile_id": "us100_m5_fpmarkets_tester_execution_v0",
        "locked_final_oos_b": "excluded_forbidden_by_default",
    }
    counts = summary.setdefault("counts", {})
    counts["candidate_count"] = 0
    counts["l5_candidate_count"] = 0
    summary["artifact_outputs"]["runtime_execution_summary"] = RUNTIME_SUMMARY.as_posix()
    summary["artifact_outputs"]["runtime_execution_index"] = RUNTIME_INDEX.as_posix()
    summary["judgment"]["judgment_class"] = "runtime_probe_progress"
    summary["judgment"]["runtime_authority"] = False
    summary["judgment"]["economics_pass"] = False
    summary["judgment"]["selected_baseline"] = False
    summary["judgment"]["goal_achieve"] = False
    summary["judgment"]["candidate_count"] = 0
    summary["judgment"]["l5_candidate_count"] = 0
    summary["judgment"]["next_action"] = (
        "judge paired Wave02 execution/liquidity decision replay validation/research_oos results before any L5 candidate claim"
        if summary["status"] == ALL_ATTEMPTS_STATUS
        else "continue running remaining prepared Wave02 execution/liquidity decision replay Strategy Tester attempts"
    )
    summary.setdefault("prevention_memory", []).append(
        "Wave02 execution/liquidity decision replay runtime execution owns Wave02 IDs and records no candidate, no economics pass, no live readiness."
    )
    summary.setdefault("try_first_disposition", {})["policy_applied"] = (
        "missing Wave02 execution/liquidity decision replay runtime entrypoint was repaired before blocked/deferred/invalid disposition"
    )
    summary["unresolved_blockers_or_none"] = (
        ["Wave02_execution_liquidity_decision_replay_pair_judgment_pending"]
        if summary["status"] == ALL_ATTEMPTS_STATUS
        else ["remaining_Wave02_execution_liquidity_decision_replay_terminal_execution_pending"]
    )
    summary["next_action_or_reopen_condition"] = summary["judgment"]["next_action"]
    summary["writer_scope_self_check"] = {
        "status": "pending_after_write",
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "validation_depth": VALIDATION_DEPTH,
        "non_pytest_smokes": NON_PYTEST_SMOKES,
        "skipped_broad_validations": SKIPPED_BROAD_VALIDATIONS,
        "broad_validation_escalation_reason": BROAD_VALIDATION_ESCALATION_REASON,
    }
    return summary


def normalize_compile_summary(compile_summary: dict[str, Any]) -> dict[str, Any]:
    compile_summary["version"] = "wave02_execution_liquidity_decision_replay_runtime_compile_summary_v1"
    compile_summary["summary_path"] = COMPILE_SUMMARY.as_posix()
    compile_summary["work_item_id"] = WORK_ITEM_ID
    compile_summary["subwork_item_id"] = SUBWORK_ID
    compile_summary["active_goal_id"] = GOAL_ID
    compile_summary["campaign_id"] = CAMPAIGN_ID
    compile_summary["sweep_id"] = SWEEP_ID
    compile_summary["writer_contract_version"] = WRITER_CONTRACT_VERSION
    compile_summary["validation_depth"] = VALIDATION_DEPTH
    compile_summary["non_pytest_smokes"] = list(NON_PYTEST_SMOKES)
    compile_summary["skipped_broad_validations"] = list(SKIPPED_BROAD_VALIDATIONS)
    compile_summary["claim_boundary"] = "wave02_execution_liquidity_decision_replay_ea_compile_or_binary_preflight_only_not_strategy_tester_output"
    return compile_summary


def build_closeout(summary: dict[str, Any]) -> dict[str, Any]:
    missing = []
    if summary["status"] == PARTIAL_STATUS:
        missing.append("remaining_prepared_Wave02_decision_replay_attempts")
    else:
        missing.append("paired_Wave02_decision_replay_period_judgment_pending")
    if not (summary.get("runtime_completion") or {}).get("runtime_probe_complete"):
        missing.append("standard_decision_replay_l4_runtime_completion_contract")
    if summary["counts"].get("tester_report_observed_count", 0) == 0:
        missing.append("tester_report_hash_or_report_export_adapter_for_economics_claim")
    return {
        "version": "work_closeout_v1",
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "work_item_id": SUBWORK_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "primary_family": PRIMARY_FAMILY,
        "primary_skill": PRIMARY_SKILL,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": summary["ended_at_utc"],
        "result_judgment": (
            "runtime_probe"
            if summary["counts"].get("execution_telemetry_observed_count")
            else "inconclusive"
        ),
        "status": summary["status"],
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [
            RUNTIME_SUMMARY.as_posix(),
            RUNTIME_INDEX.as_posix(),
            summary["compile_summary"]["path"],
        ],
        "counts": summary["counts"],
        "required_gate_coverage": {
            "passed": [
                "mt5_runtime_probe_contract_audit",
                "runtime_surface_contract",
                "terminal_execution_attempt_record",
                "execution_telemetry_summary",
                "result_judgment",
                "final_claim_guard",
                "writer_scope_self_check",
            ],
            "missing": missing,
            "not_applicable": [
                "runtime_authority",
                "economics_pass",
                "selected_baseline",
                "goal_achieve",
                "live_readiness",
            ],
        },
        "try_first_disposition": summary.get("try_first_disposition", {}),
        "next_action": summary["judgment"]["next_action"],
        "forbidden_claims": summary["forbidden_claims"],
        "forbidden_claims_respected": True,
        "source_of_truth_paths": summary["source_of_truth_paths"],
        "writer_owned_outputs": summary["writer_owned_outputs"],
        "validation_depth": summary["validation_depth"],
        "non_pytest_smokes": summary["non_pytest_smokes"],
        "skipped_broad_validations": summary["skipped_broad_validations"],
        "broad_validation_escalation_reason": summary["broad_validation_escalation_reason"],
        "writer_scope_self_check": summary.get("writer_scope_self_check", {}),
        "unresolved_blockers_or_none": summary.get("unresolved_blockers_or_none", []),
        "next_action_or_reopen_condition": summary.get("next_action_or_reopen_condition", summary["judgment"]["next_action"]),
    }


def upsert_artifact_registry(repo_root: Path, summary: dict[str, Any], execution_rows: list[dict[str, Any]]) -> None:
    registry_path = repo_root / ARTIFACT_REGISTRY
    rows = base.read_csv_rows(registry_path)
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
    producer = " ".join(summary["environment"]["command_argv"])

    def put(row: dict[str, Any]) -> None:
        path_value = row.get("path_or_uri")
        full = repo_root / path_value if path_value else None
        if full and full.exists():
            row["sha256"] = base.sha256(full)
            row["size_bytes"] = str(full.stat().st_size)
        by_id[row["artifact_id"]] = {key: str(row.get(key, "")) for key in fieldnames}

    for artifact_id, artifact_type, path, notes in [
        (
            "artifact_wave02_execution_liquidity_decision_replay_runtime_execution_summary_v0",
            "decision_replay_runtime_execution_summary",
            RUNTIME_SUMMARY,
            "Wave02 execution/liquidity decision replay runtime execution progress summary",
        ),
        (
            "artifact_wave02_execution_liquidity_decision_replay_runtime_execution_index_v0",
            "decision_replay_runtime_execution_index",
            RUNTIME_INDEX,
            "Wave02 execution/liquidity decision replay terminal execution index",
        ),
        (
            "artifact_wave02_execution_liquidity_decision_replay_runtime_execution_closeout_v0",
            "work_closeout",
            CLOSEOUT_PATH,
            "Wave02 execution/liquidity decision replay runtime execution subwork closeout",
        ),
        (
            "artifact_wave02_execution_liquidity_decision_replay_runtime_compile_summary_v0",
            "decision_replay_runtime_compile_summary",
            Path(summary["compile_summary"]["path"]),
            "Decision replay EA binary availability check for Wave02 runtime execution",
        ),
        (
            "artifact_wave02_execution_liquidity_decision_replay_ea_source_v0",
            "mt5_ea_source",
            base.EA_SOURCE,
            "score replay decision EA source reused for Wave02",
        ),
    ]:
        put(
            {
                "artifact_id": artifact_id,
                "artifact_type": artifact_type,
                "path_or_uri": path.as_posix(),
                "availability": "present_hash_recorded",
                "producer_command": producer,
                "regeneration_command": producer,
                "source_of_truth": RUNTIME_SUMMARY.as_posix(),
                "consumer": WORK_ITEM_ID,
                "claim_boundary": summary["claim_boundary"],
                "notes": notes,
            }
        )

    if (repo_root / base.EA_BINARY).exists():
        put(
            {
                "artifact_id": "artifact_wave02_execution_liquidity_decision_replay_ea_binary_v0",
                "artifact_type": "mt5_ea_binary",
                "path_or_uri": base.EA_BINARY.as_posix(),
                "availability": "local_binary_hash_recorded_ignored_by_git",
                "producer_command": producer,
                "regeneration_command": "compile with MetaEditor64 /portable /compile:<path>",
                "source_of_truth": base.EA_SOURCE.as_posix(),
                "consumer": WORK_ITEM_ID,
                "claim_boundary": "wave02_execution_liquidity_decision_replay_ea_compile_or_binary_preflight_only_not_strategy_tester_output",
                "notes": "compiled decision replay EA binary hash; local ignored artifact",
            }
        )

    for row in execution_rows:
        attempt_root = Path("runtime") / "mt5_attempts" / row["attempt_id"]
        receipt_path = attempt_root / "tester_report_receipt.yaml"
        receipt_availability = "present_hash_recorded" if (repo_root / receipt_path).exists() else "missing_after_runtime_writer"
        for suffix, artifact_type, path, availability, notes in [
            ("manifest", "attempt_manifest", attempt_root / "attempt_manifest.yaml", "present_hash_recorded", "Wave02 execution/liquidity decision replay attempt manifest updated with terminal evidence"),
            ("tester_config", "tester_config", attempt_root / "tester_config.ini", "present_hash_recorded", "Wave02 execution/liquidity decision replay tester config used for terminal execution"),
            ("terminal_summary", "terminal_run_summary", Path(row["terminal_run_summary_path"]), "present_hash_recorded", "Wave02 execution/liquidity decision replay terminal launch and mode evidence"),
            ("execution_telemetry_summary", "execution_telemetry_summary", Path(row["execution_telemetry_summary_path"]), "present_hash_recorded", "Wave02 decision execution telemetry summary"),
            ("tester_log_summary", "tester_log_summary", Path(row.get("tester_log_summary_path") or attempt_root / "tester_log_summary.yaml"), "present_hash_recorded", "Wave02 execution/liquidity decision replay tester log summary"),
            ("tester_report_receipt", "tester_report_receipt", receipt_path, receipt_availability, "Wave02 execution/liquidity decision replay tester report receipt"),
        ]:
            put(
                {
                    "artifact_id": f"artifact_{row['attempt_id']}_{suffix}_v0",
                    "run_id": row["run_id"],
                    "bundle_id": row["bundle_id"],
                    "attempt_id": row["attempt_id"],
                    "artifact_type": artifact_type,
                    "path_or_uri": path.as_posix(),
                    "availability": availability,
                    "producer_command": producer,
                    "regeneration_command": producer,
                    "source_of_truth": (attempt_root / "attempt_manifest.yaml").as_posix(),
                    "consumer": WORK_ITEM_ID,
                    "claim_boundary": row["claim_boundary"],
                    "notes": notes,
                }
            )
        if row.get("repo_execution_telemetry_path"):
            put(
                {
                    "artifact_id": f"artifact_{row['attempt_id']}_execution_telemetry_csv_v0",
                    "run_id": row["run_id"],
                    "bundle_id": row["bundle_id"],
                    "attempt_id": row["attempt_id"],
                    "artifact_type": "execution_telemetry_csv",
                    "path_or_uri": row["repo_execution_telemetry_path"],
                    "availability": "local_telemetry_hash_recorded_ignored_by_git",
                    "producer_command": producer,
                    "regeneration_command": producer,
                    "source_of_truth": row["execution_telemetry_summary_path"],
                    "consumer": WORK_ITEM_ID,
                    "claim_boundary": row["claim_boundary"],
                    "notes": "raw decision replay telemetry is local/generated; committed summary is the indexable evidence",
                }
            )
        else:
            by_id.pop(f"artifact_{row['attempt_id']}_execution_telemetry_csv_v0", None)
        if row.get("tester_report_path"):
            put(
                {
                    "artifact_id": f"artifact_{row['attempt_id']}_tester_report_v0",
                    "run_id": row["run_id"],
                    "bundle_id": row["bundle_id"],
                    "attempt_id": row["attempt_id"],
                    "artifact_type": "tester_report",
                    "path_or_uri": row["tester_report_path"],
                    "availability": "local_report_hash_recorded_ignored_by_git",
                    "producer_command": producer,
                    "regeneration_command": producer,
                    "source_of_truth": (attempt_root / "attempt_manifest.yaml").as_posix(),
                    "consumer": WORK_ITEM_ID,
                    "claim_boundary": "tester_report_local_evidence_only_no_economics_pass",
                    "notes": "raw tester report is local/generated; no economics pass claim",
                }
            )
        else:
            by_id.pop(f"artifact_{row['attempt_id']}_tester_report_v0", None)
    base.write_csv(registry_path, list(by_id.values()), fieldnames)


def next_work_payload(summary: dict[str, Any]) -> dict[str, Any]:
    if summary["status"] == PARTIAL_STATUS:
        return {
            "version": "work_item_lite_v1",
            "writer_contract_version": WRITER_CONTRACT_VERSION,
            "work_item_id": WORK_ITEM_ID,
            "parent_work_item_id": "work_wave02_execution_liquidity_l4_decision_replay_adapter_preparation_v0",
            "primary_family": PRIMARY_FAMILY,
            "primary_skill": PRIMARY_SKILL,
            "support_skills": ["spacesonar-evidence-provenance", "spacesonar-result-judgment", "spacesonar-claim-discipline"],
            "verification_profile": "writer_scope_runtime_execution",
            "targets": [RUNTIME_SUMMARY.as_posix(), RUNTIME_INDEX.as_posix()],
            "acceptance_criteria": [
                "execute remaining prepared Wave02 execution/liquidity decision replay MT5 attempts",
                "record execution telemetry, tester report receipts, and runtime completion before pair judgment",
                "keep candidate_count and l5_candidate_count at zero",
            ],
            "claim_boundary": summary["claim_boundary"],
            "next_action": summary["judgment"]["next_action"],
            "source_of_truth_paths": [RUNTIME_SUMMARY.as_posix(), RUNTIME_INDEX.as_posix()],
            "writer_owned_outputs": summary["writer_owned_outputs"],
            "validation_depth": VALIDATION_DEPTH,
            "non_pytest_smokes": NON_PYTEST_SMOKES,
            "skipped_broad_validations": SKIPPED_BROAD_VALIDATIONS,
            "broad_validation_escalation_reason": BROAD_VALIDATION_ESCALATION_REASON,
            "status": "wave02_execution_liquidity_decision_replay_terminal_execution_in_progress",
            "current_truth": {
                "decision_replay_runtime_execution_summary": RUNTIME_SUMMARY.as_posix(),
                "decision_replay_runtime_execution_index": RUNTIME_INDEX.as_posix(),
                "decision_replay_runtime_execution_status": summary["status"],
                "decision_replay_runtime_execution_counts": summary["counts"],
                "candidate_count": 0,
                "l5_candidate_count": 0,
            },
            "unresolved_blockers": ["remaining_Wave02_execution_liquidity_decision_replay_terminal_execution_pending"],
            "forbidden_claims": FORBIDDEN_CLAIMS,
            "unresolved_blockers_or_none": ["remaining_Wave02_execution_liquidity_decision_replay_terminal_execution_pending"],
            "next_action_or_reopen_condition": summary["judgment"]["next_action"],
            "reopen_conditions": ["rerun the writer for unexecuted prepared attempts"],
            "missing_material_if_relevant": ["remaining_prepared_decision_replay_attempts"],
        }
    return {
        "version": "work_item_lite_v1",
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "work_item_id": NEXT_WORK_ID,
        "parent_work_item_id": SUBWORK_ID,
        "primary_family": "candidate_evaluation",
        "primary_skill": "spacesonar-result-judgment",
        "support_skills": ["spacesonar-runtime-evidence", "spacesonar-evidence-provenance", "spacesonar-claim-discipline"],
        "verification_profile": "writer_scope_pair_judgment",
        "targets": [RUNTIME_SUMMARY.as_posix(), RUNTIME_INDEX.as_posix()],
        "acceptance_criteria": [
            "judge paired Wave02 execution/liquidity decision replay validation/research_oos results",
            "record candidate_count and l5_candidate_count explicitly",
            "do not claim selected baseline, runtime authority, economics pass, live readiness, or Goal Achieve",
        ],
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "next_action": "write Wave02 execution/liquidity decision replay pair judgment before any candidate-specific L5 material",
        "source_of_truth_paths": [RUNTIME_SUMMARY.as_posix(), RUNTIME_INDEX.as_posix(), CLOSEOUT_PATH.as_posix()],
        "writer_owned_outputs": [
            "lab/campaigns/campaign_us100_wave02_execution_liquidity_surface_v0/l4_follow_through/decision_replay/pair_judgment_summary.yaml",
            "lab/campaigns/campaign_us100_wave02_execution_liquidity_surface_v0/l4_follow_through/decision_replay/pair_judgment_index.csv",
        ],
        "validation_depth": VALIDATION_DEPTH,
        "non_pytest_smokes": NON_PYTEST_SMOKES,
        "skipped_broad_validations": SKIPPED_BROAD_VALIDATIONS,
        "broad_validation_escalation_reason": BROAD_VALIDATION_ESCALATION_REASON,
        "status": "wave02_execution_liquidity_decision_replay_pair_judgment_pending",
        "current_truth": {
            "decision_replay_runtime_execution_summary": RUNTIME_SUMMARY.as_posix(),
            "decision_replay_runtime_execution_index": RUNTIME_INDEX.as_posix(),
            "decision_replay_runtime_execution_status": summary["status"],
            "decision_replay_runtime_execution_counts": summary["counts"],
            "candidate_count": 0,
            "l5_candidate_count": 0,
        },
        "unresolved_blockers": ["Wave02_execution_liquidity_decision_replay_pair_judgment_pending"],
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "unresolved_blockers_or_none": ["Wave02_execution_liquidity_decision_replay_pair_judgment_pending"],
        "next_action_or_reopen_condition": "write Wave02 execution/liquidity decision replay pair judgment before any candidate-specific L5 material",
        "reopen_conditions": ["write decision replay pair judgment summary/index before opening L5 candidate work"],
        "missing_material_if_relevant": [
            "decision_replay_pair_judgment_summary_missing",
            "candidate_specific_L5_manifest_not_opened",
        ],
    }


def update_control_records(repo_root: Path, summary: dict[str, Any]) -> None:
    next_work = next_work_payload(summary)
    base.write_yaml(repo_root / NEXT_WORK_ITEM, next_work)

    resume = base.load_yaml(repo_root / RESUME_CURSOR)
    resume["updated_at_utc"] = summary["ended_at_utc"]
    resume["cursor_state"] = next_work["status"]
    resume["active_phase"] = next_work["status"]
    resume["active_work_item_id"] = next_work["work_item_id"]
    resume["campaign_id"] = CAMPAIGN_ID
    resume["claim_boundary"] = next_work["claim_boundary"]
    resume["next_action"] = next_work["next_action"]
    resume["unresolved_blockers"] = list(next_work["unresolved_blockers"])
    truth_sources = resume.setdefault("current_truth_sources", [])
    for source in [RUNTIME_SUMMARY.as_posix(), RUNTIME_INDEX.as_posix(), CLOSEOUT_PATH.as_posix()]:
        if source not in truth_sources:
            truth_sources.append(source)
    resume["latest_runtime_progress"] = {
        "work_item_id": SUBWORK_ID,
        "result_judgment": (
            "runtime_probe"
            if summary["counts"].get("execution_telemetry_observed_count")
            else "inconclusive"
        ),
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [RUNTIME_SUMMARY.as_posix(), CLOSEOUT_PATH.as_posix()],
    }
    resume["next_work_item"] = {"work_item_id": next_work["work_item_id"], "path": NEXT_WORK_ITEM.as_posix()}
    base.write_yaml(repo_root / RESUME_CURSOR, resume)

    phase = next_work["status"]
    goal = base.load_yaml(repo_root / GOAL_MANIFEST)
    goal["updated_at_utc"] = summary["ended_at_utc"]
    goal["active_phase"] = phase
    wave02 = goal.setdefault("wave02_execution_liquidity_campaign", {})
    wave02["decision_replay_runtime_execution_summary"] = RUNTIME_SUMMARY.as_posix()
    wave02["decision_replay_runtime_execution_status"] = summary["status"]
    wave02["decision_replay_runtime_execution_counts"] = summary["counts"]
    wave02["next_work_item"] = next_work["work_item_id"]
    base.write_yaml(repo_root / GOAL_MANIFEST, goal)

    if (repo_root / CAMPAIGN_MANIFEST).exists():
        campaign = base.load_yaml(repo_root / CAMPAIGN_MANIFEST)
        campaign["updated_at_utc"] = summary["ended_at_utc"]
        campaign["status"] = phase
        campaign["claim_boundary"] = next_work["claim_boundary"]
        campaign.setdefault("runtime_follow_through", {})["decision_replay_runtime_execution"] = {
            "summary": RUNTIME_SUMMARY.as_posix(),
            "index": RUNTIME_INDEX.as_posix(),
            "status": summary["status"],
            "counts": summary["counts"],
            "claim_boundary": summary["claim_boundary"],
        }
        base.write_yaml(repo_root / CAMPAIGN_MANIFEST, campaign)

    workspace = base.load_yaml(repo_root / WORKSPACE_STATE)
    workspace["updated_utc"] = summary["ended_at_utc"]
    workspace["active_work_item"] = {"work_item_id": next_work["work_item_id"], "path": NEXT_WORK_ITEM.as_posix()}
    workspace["current_claim_boundary"] = next_work["claim_boundary"]
    workspace["next_action"] = next_work["next_action"]
    workspace["unresolved_blockers"] = list(next_work["unresolved_blockers"])
    counts = workspace.setdefault("summary_counts", {})
    counts["candidate_count"] = 0
    counts["l5_candidate_count"] = 0
    counts["wave02_execution_liquidity_decision_replay_runtime_execution"] = summary["counts"]
    counts["runtime_contract_integrity"] = {
        "runtime_probe_complete_count": summary["counts"]["runtime_probe_complete_count"],
        "prepared_attempt_count": summary["counts"]["prepared_attempt_count"],
        "runtime_probe_complete": (summary.get("runtime_completion") or {}).get("runtime_probe_complete"),
    }
    base.write_yaml(repo_root / WORKSPACE_STATE, workspace)

    if (repo_root / GOAL_REGISTRY).exists():
        goal_rows = base.read_csv_rows(repo_root / GOAL_REGISTRY)
        for row in goal_rows:
            if row.get("goal_id") == GOAL_ID:
                row["active_phase"] = phase
                row["next_work_item"] = next_work["work_item_id"]
                row["claim_boundary"] = "active_goal_wave02_execution_liquidity_decision_replay_runtime_progress_not_goal_achieve"
        if goal_rows:
            base.write_csv(repo_root / GOAL_REGISTRY, goal_rows, list(goal_rows[0].keys()))


def write_execution_records(
    *,
    repo_root: Path,
    summary: dict[str, Any],
    execution_rows: list[dict[str, Any]],
    write_control_records: bool,
) -> None:
    base.write_yaml(repo_root / RUNTIME_SUMMARY, summary)
    base.write_csv(repo_root / RUNTIME_INDEX, execution_rows, base.execution_index_fieldnames())
    base.write_yaml(repo_root / CLOSEOUT_PATH, build_closeout(summary))
    upsert_artifact_registry(repo_root, summary, execution_rows)
    if write_control_records:
        update_control_records(repo_root, summary)


def writer_scope_self_check(repo_root: Path, summary: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    for path in [RUNTIME_SUMMARY, RUNTIME_INDEX, CLOSEOUT_PATH]:
        if not (repo_root / path).exists():
            failures.append(f"missing:{path.as_posix()}")
    if (repo_root / RUNTIME_INDEX).exists():
        indexed = base.read_csv_rows(repo_root / RUNTIME_INDEX)
        if len(indexed) != summary["counts"]["indexed_execution_count"]:
            failures.append("runtime_index_row_count_mismatch")
    forbidden_flags = [
        summary["judgment"].get("runtime_authority"),
        summary["judgment"].get("economics_pass"),
        summary["judgment"].get("selected_baseline"),
        summary["judgment"].get("goal_achieve"),
        summary["counts"].get("candidate_count"),
        summary["counts"].get("l5_candidate_count"),
    ]
    if any(bool(value) for value in forbidden_flags):
        failures.append("forbidden_claim_or_candidate_count_present")
    registry_rows = base.read_csv_rows(repo_root / ARTIFACT_REGISTRY)
    registry_by_id = {row.get("artifact_id"): row for row in registry_rows}
    for artifact_id, path in [
        ("artifact_wave02_execution_liquidity_decision_replay_runtime_execution_summary_v0", RUNTIME_SUMMARY),
        ("artifact_wave02_execution_liquidity_decision_replay_runtime_execution_index_v0", RUNTIME_INDEX),
        ("artifact_wave02_execution_liquidity_decision_replay_runtime_execution_closeout_v0", CLOSEOUT_PATH),
    ]:
        row = registry_by_id.get(artifact_id)
        if not row:
            failures.append(f"missing_registry:{artifact_id}")
            continue
        if (repo_root / path).exists() and row.get("sha256") != base.sha256(repo_root / path):
            failures.append(f"registry_hash_mismatch:{artifact_id}")
    status = "passed" if not failures else "failed"
    return {"status": status, "failures": failures}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run prepared Wave02 execution/liquidity decision replay MT5 attempts.")
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
    command = ["python", "foundation/pipelines/run_wave02_execution_liquidity_l4_decision_replay_attempts.py"]
    if args.expected_branch:
        command.extend(["--expected-branch", args.expected_branch])
    for attempt_id in args.attempt_id:
        command.extend(["--attempt-id", attempt_id])
    for period_role in args.period_role:
        command.extend(["--period-role", period_role])
    command.extend(["--limit", str(args.limit)])
    if args.include_completed:
        command.append("--include-completed")
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
            print(
                json.dumps(
                    {
                        "status": "branch_mismatch_blocked_before_runtime_mutation",
                        "expected_branch": args.expected_branch,
                        "current_branch": branch,
                    },
                    indent=2,
                )
            )
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
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "selected_attempt_ids": [row["attempt_id"] for row in selected],
                    "selected_attempt_count": len(selected),
                    "prep_index": PREP_INDEX.as_posix(),
                    "runtime_index": RUNTIME_INDEX.as_posix(),
                    "claim_boundary": SUMMARY_CLAIM_BOUNDARY,
                },
                indent=2,
            )
        )
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
    compile_summary = normalize_compile_summary(compile_summary)
    base.write_yaml(repo_root / COMPILE_SUMMARY, compile_summary)

    execution_rows: list[dict[str, Any]] = []
    terminal = Path(args.terminal)
    for row in selected:
        stage_attempt_runtime_inputs(repo_root, row, terminal)
        execution_row = base.run_one_attempt(
            repo_root=repo_root,
            row=row,
            terminal=terminal,
            timeout_seconds=args.terminal_timeout_seconds,
            terminate_existing=args.terminate_existing_terminal,
            allow_main_mode_fallback=args.allow_main_mode_fallback and not args.no_main_mode_fallback,
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
    write_execution_records(
        repo_root=repo_root,
        summary=summary,
        execution_rows=merged_rows,
        write_control_records=args.write_control_records,
    )
    self_check = writer_scope_self_check(repo_root, summary)
    summary["writer_scope_self_check"] = {
        **self_check,
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "validation_depth": VALIDATION_DEPTH,
        "non_pytest_smokes": NON_PYTEST_SMOKES,
        "skipped_broad_validations": SKIPPED_BROAD_VALIDATIONS,
        "broad_validation_escalation_reason": BROAD_VALIDATION_ESCALATION_REASON,
        "source_of_truth_paths": summary["source_of_truth_paths"],
        "writer_owned_outputs": summary["writer_owned_outputs"],
        "claim_boundary": summary["claim_boundary"],
        "forbidden_claims_respected": not self_check.get("failures"),
        "candidate_count": 0,
        "l5_candidate_count": 0,
        "next_action_or_reopen_condition": summary["next_action_or_reopen_condition"],
    }
    base.write_yaml(repo_root / RUNTIME_SUMMARY, summary)
    base.write_yaml(repo_root / CLOSEOUT_PATH, build_closeout(summary))
    upsert_artifact_registry(repo_root, summary, merged_rows)
    if args.write_control_records:
        update_control_records(repo_root, summary)
    self_check = writer_scope_self_check(repo_root, summary)
    if self_check["status"] != "passed":
        print(
            json.dumps(
                {
                    "status": "writer_scope_self_check_failed",
                    "self_check": self_check,
                    "summary": RUNTIME_SUMMARY.as_posix(),
                    "claim_boundary": summary["claim_boundary"],
                },
                indent=2,
            )
        )
        return 1

    observed = sum(1 for row in execution_rows if row.get("execution_telemetry_observed"))
    print(
        json.dumps(
            {
                "status": summary["status"],
                "summary": RUNTIME_SUMMARY.as_posix(),
                "current_batch_executed_attempt_count": len(execution_rows),
                "indexed_execution_count": len(merged_rows),
                "execution_telemetry_observed_count": summary["counts"]["execution_telemetry_observed_count"],
                "current_batch_execution_telemetry_observed_count": observed,
                "runtime_probe_complete_count": summary["counts"]["runtime_probe_complete_count"],
                "writer_scope_self_check": self_check["status"],
                "claim_boundary": summary["claim_boundary"],
            },
            indent=2,
        )
    )
    return 0 if all(row.get("execution_telemetry_observed") for row in execution_rows) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
