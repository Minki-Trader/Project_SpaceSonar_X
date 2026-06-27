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


GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WORK_ITEM_ID = "work_wave02_cost_risk_holding_l4_runtime_execution_v0"
SUBWORK_ID = "work_wave02_cost_risk_holding_l4_strategy_tester_execution_v0"
CAMPAIGN_ID = "campaign_us100_wave02_cost_risk_holding_surface_v0"
SWEEP_ID = "sweep_us100_wave02_cost_risk_holding_broad_v0"
ACTIVE_IDS = {
    "idea_id": "idea_us100_wave02_cost_risk_holding_surface_v0",
    "hypothesis_id": "hyp_us100_wave02_cost_risk_holding_runtime_alignment_v0",
    "wave_id": "wave_us100_wave02_tradeability_decision_surface_v0",
    "campaign_id": CAMPAIGN_ID,
    "surface_id": "surface_us100_wave02_cost_risk_holding_v0",
    "sweep_id": SWEEP_ID,
}
SUMMARY_ID = "wave02_cost_risk_holding_l4_runtime_execution_summary_v0"
CLAIM_BOUNDARY = (
    "wave02_cost_risk_holding_l4_score_runtime_observation_only_"
    "no_runtime_authority_no_economics_pass_no_candidate_no_live_readiness_no_goal_achieve"
)
SUMMARY_CLAIM_BOUNDARY = (
    "wave02_cost_risk_holding_l4_runtime_execution_progress_only_"
    "no_runtime_authority_no_economics_pass_no_candidate_no_live_readiness_no_goal_achieve"
)

OUTPUT_DIR = Path("lab/campaigns/campaign_us100_wave02_cost_risk_holding_surface_v0/l4_follow_through")
PREP_INDEX = OUTPUT_DIR / "l4_attempt_preparation_index.csv"
RUNTIME_SUMMARY = OUTPUT_DIR / "l4_runtime_execution_summary.yaml"
RUNTIME_INDEX = OUTPUT_DIR / "l4_runtime_execution_index.csv"
CLOSEOUT_PATH = Path(
    "lab/goals/goal_us100_onnx_forward_boundary_v0/"
    "work_wave02_cost_risk_holding_l4_strategy_tester_execution_v0_closeout.yaml"
)
NEXT_WORK_ITEM = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml")
RESUME_CURSOR = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml")
GOAL_MANIFEST = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml")
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")
GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")
CAMPAIGN_MANIFEST = Path("lab/campaigns/campaign_us100_wave02_cost_risk_holding_surface_v0/campaign_manifest.yaml")


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


def current_branch(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def normalize_attempt_outputs(repo_root: Path, row: dict[str, str], execution_row: dict[str, Any]) -> dict[str, Any]:
    attempt_id = row["attempt_id"]
    root = repo_root / "runtime" / "mt5_attempts" / attempt_id
    manifest_path = repo_root / row["attempt_manifest_path"]

    terminal_path = root / "terminal_run_summary.yaml"
    terminal: dict[str, Any] | None = None
    if terminal_path.exists():
        terminal = base.load_yaml(terminal_path)
        terminal["version"] = "wave02_cost_risk_holding_l4_terminal_run_summary_v1"
        terminal["work_item_id"] = WORK_ITEM_ID
        terminal["subwork_item_id"] = SUBWORK_ID
        terminal["active_goal_id"] = GOAL_ID
        terminal["campaign_id"] = CAMPAIGN_ID
        terminal["sweep_id"] = SWEEP_ID
        base.write_yaml(terminal_path, terminal)

    score_path = root / "score_telemetry_summary.yaml"
    score: dict[str, Any] | None = None
    if score_path.exists():
        score = base.load_yaml(score_path)
        score["version"] = "wave02_cost_risk_holding_l4_score_telemetry_summary_v1"
        score["work_item_id"] = WORK_ITEM_ID
        score["subwork_item_id"] = SUBWORK_ID
        score["active_goal_id"] = GOAL_ID
        score["campaign_id"] = CAMPAIGN_ID
        score["sweep_id"] = SWEEP_ID
        diagnostic_evidence = score.setdefault("diagnostic_evidence", {})
        if diagnostic_evidence:
            diagnostic_evidence["claim_boundary"] = "wave02_ea_score_probe_diagnostic_observation_only_no_runtime_authority"
        if execution_row.get("telemetry_observed"):
            score["claim_boundary"] = CLAIM_BOUNDARY
        base.write_yaml(score_path, score)

    diagnostic_path = root / "score_diagnostic_summary.yaml"
    diagnostic: dict[str, Any] | None = None
    if diagnostic_path.exists():
        diagnostic = base.load_yaml(diagnostic_path)
        diagnostic["version"] = "wave02_cost_risk_holding_l4_score_diagnostic_summary_v1"
        diagnostic["work_item_id"] = WORK_ITEM_ID
        diagnostic["subwork_item_id"] = SUBWORK_ID
        diagnostic["active_goal_id"] = GOAL_ID
        diagnostic["campaign_id"] = CAMPAIGN_ID
        diagnostic["sweep_id"] = SWEEP_ID
        diagnostic["claim_boundary"] = "wave02_ea_score_probe_diagnostic_observation_only_no_runtime_authority"
        base.write_yaml(diagnostic_path, diagnostic)

    manifest = base.load_yaml(manifest_path)
    manifest["terminal_execution_subwork_item_id"] = SUBWORK_ID
    manifest["campaign_id"] = CAMPAIGN_ID
    manifest["sweep_id"] = SWEEP_ID
    if execution_row.get("telemetry_observed"):
        manifest["claim_boundary"] = CLAIM_BOUNDARY
    if terminal is not None:
        manifest["terminal_run_summary"] = terminal
    if score is not None:
        manifest["score_telemetry_summary"] = score
    if diagnostic is not None:
        manifest["score_diagnostic_summary"] = diagnostic
    routing = manifest.setdefault("runtime_probe_routing", {})
    routing["primary_family"] = "runtime_probe"
    routing["primary_skill"] = "spacesonar-runtime-evidence"
    routing["support_skills"] = ["spacesonar-evidence-provenance", "spacesonar-claim-discipline"]
    routing["routing_scope"] = "wave02_cost_risk_holding_l4_split_runtime_score_probe_execution"
    routing["runtime_period_profile_id"] = "period_profile_split_set_v0"
    routing["runtime_period_set_id"] = "split_base_anchor_v0_research_l4"
    routing["period_role"] = row["period_role"]
    routing["claim_boundary"] = manifest.get("claim_boundary", CLAIM_BOUNDARY)
    parity = manifest.setdefault("proxy_runtime_parity", {})
    prevention = parity.setdefault("prevention_memory", [])
    memory = (
        "Wave02 cost/risk/holding L4 runner normalizes reused score-probe helper outputs to prevent "
        "Wave0/Wave01 identity drift."
    )
    if memory not in prevention:
        prevention.append(memory)
    parity["comparison_class"] = "pending_pair_aggregation_after_wave02_l4_period_roles"
    parity["follow_up_action"] = manifest.get("next_action", "continue Wave02 cost/risk/holding L4 period-role execution")
    manifest.setdefault("artifact_identity", {})["terminal_run_summary"] = base.artifact_ref(terminal_path, repo_root)
    manifest["artifact_identity"]["score_telemetry_summary"] = base.artifact_ref(score_path, repo_root)
    if diagnostic_path.exists():
        manifest["artifact_identity"]["score_diagnostic_summary"] = base.artifact_ref(diagnostic_path, repo_root)
    receipt_path = root / "tester_report_receipt.yaml"
    if receipt_path.exists():
        manifest["artifact_identity"]["tester_report_receipt"] = base.artifact_ref(receipt_path, repo_root)
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
    summary["version"] = "wave02_cost_risk_holding_l4_runtime_execution_summary_v1"
    summary["summary_id"] = SUMMARY_ID
    summary["work_item_id"] = WORK_ITEM_ID
    summary["subwork_item_id"] = SUBWORK_ID
    summary["active_goal_id"] = GOAL_ID
    summary["campaign_id"] = CAMPAIGN_ID
    summary["sweep_id"] = SWEEP_ID
    summary["claim_boundary"] = SUMMARY_CLAIM_BOUNDARY
    summary["artifact_outputs"]["runtime_execution_summary"] = RUNTIME_SUMMARY.as_posix()
    summary["artifact_outputs"]["runtime_execution_index"] = RUNTIME_INDEX.as_posix()
    summary["judgment"]["next_action"] = (
        "aggregate paired Wave02 cost/risk/holding validation/research_oos L4 telemetry before any L5 candidate routing"
        if summary["judgment"]["runtime_probe_completed_for_all_prepared_attempts"]
        else "continue running remaining prepared Wave02 cost/risk/holding L4 Strategy Tester attempts"
    )
    summary.setdefault("prevention_memory", []).append(
        "Wave02 cost/risk/holding runtime execution uses CRH-specific IDs and claim boundaries while reusing the score-probe helper."
    )
    summary.setdefault("try_first_disposition", {})["policy_applied"] = (
        "missing Wave02 cost/risk/holding score-probe runner entrypoint was repaired before blocked/deferred/invalid disposition"
    )
    return summary


def build_closeout(summary: dict[str, Any]) -> dict[str, Any]:
    missing = []
    if summary["status"] == base.PARTIAL_STATUS:
        missing.append("remaining_prepared_Wave02_L4_attempts")
    else:
        missing.append("paired_Wave02_L4_period_aggregation_pending")
    if not (summary.get("runtime_completion") or {}).get("runtime_probe_complete"):
        missing.append("standard_l4_runtime_completion_contract")
    return {
        "version": "work_closeout_v1",
        "work_item_id": SUBWORK_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": summary["ended_at_utc"],
        "result_judgment": "runtime_probe" if summary["counts"]["telemetry_observed_count"] else "inconclusive",
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
                "result_judgment",
                "final_claim_guard",
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
    }


def counts_payload(summary: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(summary["counts"])


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
            "artifact_wave02_cost_risk_holding_l4_runtime_execution_summary_v0",
            "l4_runtime_execution_summary",
            RUNTIME_SUMMARY,
            "Wave02 cost/risk/holding L4 runtime execution progress summary",
        ),
        (
            "artifact_wave02_cost_risk_holding_l4_runtime_execution_index_v0",
            "l4_runtime_execution_index",
            RUNTIME_INDEX,
            "Wave02 cost/risk/holding L4 terminal execution index",
        ),
        (
            "artifact_wave02_cost_risk_holding_l4_runtime_execution_closeout_v0",
            "work_closeout",
            CLOSEOUT_PATH,
            "Wave02 cost/risk/holding L4 runtime execution subwork closeout",
        ),
        (
            "artifact_wave02_cost_risk_holding_l4_runtime_compile_summary_v0",
            "l4_runtime_compile_summary",
            Path(summary["compile_summary"]["path"]),
            "EA binary availability check for Wave02 cost/risk/holding L4 execution",
        ),
        (
            "artifact_wave02_cost_risk_holding_l4_score_probe_ea_source_v0",
            "mt5_ea_source",
            base.EA_SOURCE,
            "non-trading L4 score telemetry probe source reused for Wave02",
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
                "artifact_id": "artifact_wave02_cost_risk_holding_l4_score_probe_ea_binary_v0",
                "artifact_type": "mt5_ea_binary",
                "path_or_uri": base.EA_BINARY.as_posix(),
                "availability": "local_binary_hash_recorded_ignored_by_git",
                "producer_command": producer,
                "regeneration_command": "compile with MetaEditor64 /portable /compile:<path>",
                "source_of_truth": base.EA_SOURCE.as_posix(),
                "consumer": WORK_ITEM_ID,
                "claim_boundary": "ea_compile_or_binary_preflight_only_not_strategy_tester_output",
                "notes": "compiled EA binary hash; local ignored artifact",
            }
        )

    for row in execution_rows:
        attempt_root = Path("runtime") / "mt5_attempts" / row["attempt_id"]
        receipt_path = attempt_root / "tester_report_receipt.yaml"
        receipt_availability = (
            "present_hash_recorded"
            if (repo_root / receipt_path).exists()
            else "missing_after_runtime_writer"
        )
        for suffix, artifact_type, path, availability, notes in [
            ("manifest", "attempt_manifest", attempt_root / "attempt_manifest.yaml", "present_hash_recorded", "Wave02 attempt manifest updated with L4 terminal execution evidence"),
            ("tester_config", "tester_config", attempt_root / "tester_config.ini", "present_hash_recorded", "Wave02 tester config used for terminal execution"),
            ("terminal_summary", "terminal_run_summary", Path(row["terminal_run_summary_path"]), "present_hash_recorded", "Wave02 terminal launch and mode evidence"),
            ("score_telemetry_summary", "score_telemetry_summary", Path(row["score_telemetry_summary_path"]), "present_hash_recorded", "Wave02 score telemetry summary"),
            (
                "score_diagnostic_summary",
                "score_diagnostic_summary",
                Path(row.get("score_diagnostic_summary_path") or attempt_root / "score_diagnostic_summary.yaml"),
                "present_hash_recorded" if (repo_root / attempt_root / "score_diagnostic_summary.yaml").exists() else "missing_after_runtime_writer",
                "Wave02 EA score-probe diagnostic summary; observation only, not runtime authority",
            ),
            ("tester_report_receipt", "tester_report_receipt", receipt_path, receipt_availability, "Wave02 tester report receipt; records missing report requirements when no report is observed"),
        ]:
            artifact_claim_boundary = (
                "wave02_ea_score_probe_diagnostic_observation_only_no_runtime_authority"
                if suffix == "score_diagnostic_summary"
                else row["claim_boundary"]
            )
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
                    "claim_boundary": artifact_claim_boundary,
                    "notes": notes,
                }
            )
        if row.get("repo_telemetry_path"):
            put(
                {
                    "artifact_id": f"artifact_{row['attempt_id']}_score_telemetry_csv_v0",
                    "run_id": row["run_id"],
                    "bundle_id": row["bundle_id"],
                    "attempt_id": row["attempt_id"],
                    "artifact_type": "score_telemetry_csv",
                    "path_or_uri": row["repo_telemetry_path"],
                    "availability": "local_telemetry_hash_recorded_ignored_by_git",
                    "producer_command": producer,
                    "regeneration_command": producer,
                    "source_of_truth": (attempt_root / "score_telemetry_summary.yaml").as_posix(),
                    "consumer": WORK_ITEM_ID,
                    "claim_boundary": row["claim_boundary"],
                    "notes": "raw Wave02 score telemetry is local/generated; committed summary is the indexable evidence",
                }
            )
        else:
            by_id.pop(f"artifact_{row['attempt_id']}_score_telemetry_csv_v0", None)
        diagnostic_csv = attempt_root / "telemetry" / "score_diagnostics.csv"
        if (repo_root / diagnostic_csv).exists():
            put(
                {
                    "artifact_id": f"artifact_{row['attempt_id']}_score_diagnostics_csv_v0",
                    "run_id": row["run_id"],
                    "bundle_id": row["bundle_id"],
                    "attempt_id": row["attempt_id"],
                    "artifact_type": "score_diagnostics_csv",
                    "path_or_uri": diagnostic_csv.as_posix(),
                    "availability": "local_diagnostic_hash_recorded_ignored_by_git",
                    "producer_command": producer,
                    "regeneration_command": producer,
                    "source_of_truth": (attempt_root / "score_diagnostic_summary.yaml").as_posix(),
                    "consumer": WORK_ITEM_ID,
                    "claim_boundary": "wave02_ea_score_probe_diagnostic_observation_only_no_runtime_authority",
                    "notes": "raw Wave02 EA diagnostic events are local/generated; committed summary is the indexable evidence",
                }
            )
        else:
            by_id.pop(f"artifact_{row['attempt_id']}_score_diagnostics_csv_v0", None)
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


def update_control_records(repo_root: Path, summary: dict[str, Any]) -> None:
    next_work = base.load_yaml(repo_root / NEXT_WORK_ITEM)
    current_truth = next_work.setdefault("current_truth", {})
    current_truth["l4_runtime_execution_summary"] = RUNTIME_SUMMARY.as_posix()
    current_truth["l4_runtime_execution_status"] = summary["status"]
    current_truth["l4_runtime_execution_counts"] = counts_payload(summary)
    current_truth["runtime_probe_completed"] = (summary.get("runtime_completion") or {}).get("runtime_probe_complete")
    current_truth["candidate_count"] = 0
    current_truth["l5_candidate_count"] = 0
    next_work["status"] = (
        "l4_strategy_tester_execution_in_progress"
        if summary["status"] == base.PARTIAL_STATUS
        else "l4_strategy_tester_execution_completed_for_prepared_attempts"
    )
    next_work["claim_boundary"] = summary["claim_boundary"]
    next_work["missing_material_if_relevant"] = (
        ["remaining_prepared_L4_attempts"]
        if summary["status"] == base.PARTIAL_STATUS
        else ["paired_L4_period_aggregation_pending"]
    )
    next_work["unresolved_blockers"] = (
        ["L4_split_runtime_probe_terminal_execution_pending"]
        if summary["status"] == base.PARTIAL_STATUS
        else ["Wave02_cost_risk_holding_L4_pair_judgment_pending"]
    )
    next_work["reopen_conditions"] = (
        ["portable Strategy Tester execution records telemetry and completed report hashes"]
        if summary["status"] == base.PARTIAL_STATUS
        else ["write Wave02 cost/risk/holding l4_pair_judgment_summary and l4_pair_judgment_index before L5 routing"]
    )
    next_work["next_action"] = summary["judgment"]["next_action"]
    base.write_yaml(repo_root / NEXT_WORK_ITEM, next_work)

    resume = base.load_yaml(repo_root / RESUME_CURSOR)
    resume["updated_at_utc"] = summary["ended_at_utc"]
    resume["cursor_state"] = next_work["status"]
    resume["active_phase"] = next_work["status"]
    resume["active_work_item_id"] = WORK_ITEM_ID
    resume["campaign_id"] = CAMPAIGN_ID
    resume["claim_boundary"] = summary["claim_boundary"]
    resume["next_action"] = summary["judgment"]["next_action"]
    resume["unresolved_blockers"] = next_work["unresolved_blockers"]
    resume["active_ids"] = ACTIVE_IDS
    truth_sources = resume.setdefault("current_truth_sources", [])
    for source in [RUNTIME_SUMMARY.as_posix(), RUNTIME_INDEX.as_posix(), CLOSEOUT_PATH.as_posix()]:
        if source not in truth_sources:
            truth_sources.append(source)
    resume["latest_runtime_progress"] = {
        "work_item_id": SUBWORK_ID,
        "result_judgment": "runtime_probe" if summary["counts"]["telemetry_observed_count"] else "inconclusive",
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [RUNTIME_SUMMARY.as_posix(), CLOSEOUT_PATH.as_posix()],
    }
    base.write_yaml(repo_root / RESUME_CURSOR, resume)

    phase = (
        "wave02_cost_risk_holding_l4_terminal_execution_in_progress"
        if summary["status"] == base.PARTIAL_STATUS
        else "wave02_cost_risk_holding_l4_pair_judgment_required_next"
    )
    campaign_status = (
        "wave02_cost_risk_holding_l4_runtime_execution_in_progress"
        if summary["status"] == base.PARTIAL_STATUS
        else "wave02_cost_risk_holding_l4_runtime_execution_completed_pair_judgment_next"
    )
    goal = base.load_yaml(repo_root / GOAL_MANIFEST)
    goal["updated_at_utc"] = summary["ended_at_utc"]
    goal["claim_boundary"] = summary["claim_boundary"]
    goal["active_phase"] = phase
    goal["active_ids"] = ACTIVE_IDS
    wave02 = goal.setdefault("wave02_cost_risk_holding_campaign", {})
    wave02["l4_runtime_execution_summary"] = RUNTIME_SUMMARY.as_posix()
    wave02["l4_runtime_execution_status"] = summary["status"]
    wave02["l4_runtime_execution_counts"] = counts_payload(summary)
    wave02["next_work_item"] = WORK_ITEM_ID
    base.write_yaml(repo_root / GOAL_MANIFEST, goal)

    workspace = base.load_yaml(repo_root / WORKSPACE_STATE)
    workspace["updated_utc"] = summary["ended_at_utc"]
    workspace.setdefault("active_campaign", {})["status"] = campaign_status
    workspace["next_action"] = summary["judgment"]["next_action"]
    workspace["current_claim_boundary"] = summary["claim_boundary"]
    workspace["unresolved_blockers"] = (
        ["L4_split_runtime_probe_terminal_execution_pending"]
        if summary["status"] == base.PARTIAL_STATUS
        else ["Wave02_cost_risk_holding_L4_pair_judgment_pending"]
    )
    workspace["summary_counts"]["runtime_contract_integrity"] = {
        "runtime_probe_complete_count": summary["counts"]["runtime_probe_complete_count"],
        "prepared_attempt_count": summary["counts"]["prepared_attempt_count"],
        "runtime_probe_complete": (summary.get("runtime_completion") or {}).get("runtime_probe_complete"),
    }
    workspace["summary_counts"]["wave02_cost_risk_holding_l4_runtime_execution"] = {
        **counts_payload(summary),
        "candidate_count": 0,
        "l5_candidate_count": 0,
    }
    materialization = workspace.setdefault("wave02_cost_risk_holding_l4_materialization", {})
    materialization["status"] = campaign_status
    materialization["claim_boundary"] = summary["claim_boundary"]
    materialization["l4_runtime_execution_summary"] = RUNTIME_SUMMARY.as_posix()
    materialization["l4_runtime_execution_status"] = summary["status"]
    materialization["l4_runtime_execution_counts"] = counts_payload(summary)
    materialization["runtime_probe_complete"] = (summary.get("runtime_completion") or {}).get("runtime_probe_complete")
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
        follow["runtime_execution_counts"] = counts_payload(summary)
        follow["runtime_probe_complete"] = (summary.get("runtime_completion") or {}).get("runtime_probe_complete")
        evidence = campaign.setdefault("evidence_paths", [])
        for source in [RUNTIME_SUMMARY.as_posix(), RUNTIME_INDEX.as_posix()]:
            if source not in evidence:
                evidence.append(source)
        campaign["missing_evidence"] = next_work["missing_material_if_relevant"]
        campaign["unresolved_blockers"] = next_work["unresolved_blockers"]
        campaign["reopen_conditions"] = next_work["reopen_conditions"]
        base.write_yaml(campaign_path, campaign)

    if (repo_root / GOAL_REGISTRY).exists():
        goal_rows = base.read_csv_rows(repo_root / GOAL_REGISTRY)
        for row in goal_rows:
            if row.get("goal_id") == GOAL_ID:
                row["active_phase"] = phase
                row["next_work_item"] = WORK_ITEM_ID
                row["claim_boundary"] = "active_goal_wave02_cost_risk_holding_l4_runtime_execution_not_goal_achieve"
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run prepared Wave02 cost/risk/holding L4 MT5 Strategy Tester attempts.")
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
    command = ["python", "foundation/pipelines/run_wave02_cost_risk_holding_l4_mt5_attempts.py"]
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


def source_newer_than_binary(repo_root: Path) -> bool:
    source = repo_root / base.EA_SOURCE
    binary = repo_root / base.EA_BINARY
    return source.exists() and binary.exists() and source.stat().st_mtime_ns > binary.stat().st_mtime_ns


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
    if source_newer_than_binary(repo_root) and not args.skip_compile_ea_if_missing:
        args.force_compile_ea = True
    command_argv = build_command_argv(args)
    compile_summary = base.ensure_ea_binary(
        repo_root=repo_root,
        metaeditor=Path(args.metaeditor),
        force_compile=args.force_compile_ea,
        skip_compile_if_missing=args.skip_compile_ea_if_missing,
        timeout_seconds=args.compile_timeout_seconds,
        started_at_utc=started_at,
    )

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
    write_execution_records(
        repo_root=repo_root,
        summary=summary,
        execution_rows=merged_rows,
        write_control_records=args.write_control_records,
    )
    observed = sum(1 for row in execution_rows if row.get("telemetry_observed"))
    print(
        json.dumps(
            {
                "status": summary["status"],
                "summary": RUNTIME_SUMMARY.as_posix(),
                "current_batch_executed_attempt_count": len(execution_rows),
                "indexed_execution_count": len(merged_rows),
                "telemetry_observed_count": summary["counts"]["telemetry_observed_count"],
                "current_batch_telemetry_observed_count": observed,
                "runtime_probe_complete_count": summary["counts"]["runtime_probe_complete_count"],
                "claim_boundary": summary["claim_boundary"],
            },
            indent=2,
        )
    )
    return 0 if all(row.get("telemetry_observed") for row in execution_rows) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
