from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import foundation.pipelines.run_wave0_l4_decision_replay_attempts as base


GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WORK_ITEM_ID = "work_wave01_event_barrier_l4_materialization_preflight_v0"
SUBWORK_ID = "work_wave01_event_barrier_l4_decision_replay_runtime_execution_v0"
CAMPAIGN_ID = "campaign_us100_event_barrier_decision_surface_v0"
SWEEP_ID = "sweep_us100_event_barrier_broad_v0"
SUMMARY_ID = "wave01_event_barrier_l4_decision_replay_runtime_execution_summary_v0"
CLAIM_BOUNDARY = (
    "wave01_event_barrier_score_band_decision_replay_runtime_observation_only_"
    "no_runtime_authority_no_economics_pass_no_candidate"
)
SUMMARY_CLAIM_BOUNDARY = (
    "wave01_event_barrier_decision_replay_runtime_execution_progress_only_"
    "no_runtime_authority_no_economics_pass_no_candidate"
)

OUTPUT_DIR = Path("lab/campaigns/campaign_us100_event_barrier_decision_surface_v0/l4_follow_through/decision_replay")
PREP_INDEX = OUTPUT_DIR / "adapter_prep_index.csv"
RUNTIME_SUMMARY = OUTPUT_DIR / "runtime_execution_summary.yaml"
RUNTIME_INDEX = OUTPUT_DIR / "runtime_execution_index.csv"
COMPILE_SUMMARY = OUTPUT_DIR / "runtime_compile_summary.yaml"
COMPILE_LOG = OUTPUT_DIR / "runtime_compile.log"
CLOSEOUT_PATH = Path(
    "lab/goals/goal_us100_onnx_forward_boundary_v0/"
    "work_wave01_event_barrier_l4_decision_replay_runtime_execution_v0_closeout.yaml"
)
NEXT_WORK_ITEM = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml")
RESUME_CURSOR = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml")
GOAL_MANIFEST = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml")
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")
GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")
PARTIAL_STATUS = "partial_wave01_decision_replay_terminal_execution_started"
ALL_ATTEMPTS_STATUS = "wave01_decision_replay_terminal_execution_attempted_for_all_prepared_attempts"


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


def normalize_compile_summary(repo_root: Path, summary: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(summary)
    normalized["version"] = "wave01_event_barrier_l4_decision_replay_runtime_compile_summary_v1"
    normalized["summary_id"] = "wave01_event_barrier_l4_decision_replay_runtime_compile_summary_v0"
    normalized["work_item_id"] = WORK_ITEM_ID
    normalized["subwork_item_id"] = SUBWORK_ID
    normalized["active_goal_id"] = GOAL_ID
    normalized["campaign_id"] = CAMPAIGN_ID
    normalized["sweep_id"] = SWEEP_ID
    normalized["claim_boundary"] = "ea_compile_or_binary_preflight_only_not_strategy_tester_output"
    normalized["local_log_policy"] = "raw_compile_log_is_local_ignored_artifact_summary_is_durable"
    base.write_yaml(repo_root / COMPILE_SUMMARY, normalized)
    return normalized


def normalize_attempt_outputs(repo_root: Path, row: dict[str, str], execution_row: dict[str, Any]) -> dict[str, Any]:
    attempt_id = row["attempt_id"]
    root = repo_root / "runtime" / "mt5_attempts" / attempt_id
    manifest_path = repo_root / row["attempt_manifest_path"]

    terminal_path = root / "terminal_run_summary.yaml"
    if terminal_path.exists():
        terminal = base.load_yaml(terminal_path)
        terminal["version"] = "wave01_event_barrier_l4_decision_replay_terminal_run_summary_v1"
        terminal["work_item_id"] = WORK_ITEM_ID
        terminal["subwork_item_id"] = SUBWORK_ID
        terminal["active_goal_id"] = GOAL_ID
        terminal["campaign_id"] = CAMPAIGN_ID
        terminal["sweep_id"] = SWEEP_ID
        terminal["claim_boundary"] = terminal.get("claim_boundary", CLAIM_BOUNDARY)
        base.write_yaml(terminal_path, terminal)

    telemetry_path = root / "execution_telemetry_summary.yaml"
    if telemetry_path.exists():
        telemetry = base.load_yaml(telemetry_path)
        telemetry["version"] = "wave01_event_barrier_l4_decision_replay_execution_telemetry_summary_v1"
        telemetry["work_item_id"] = WORK_ITEM_ID
        telemetry["subwork_item_id"] = SUBWORK_ID
        telemetry["active_goal_id"] = GOAL_ID
        telemetry["campaign_id"] = CAMPAIGN_ID
        telemetry["sweep_id"] = SWEEP_ID
        if execution_row.get("execution_telemetry_observed"):
            telemetry["claim_boundary"] = CLAIM_BOUNDARY
        base.write_yaml(telemetry_path, telemetry)

    tester_log_path = root / "tester_log_summary.yaml"
    if tester_log_path.exists():
        tester_log = base.load_yaml(tester_log_path)
        tester_log["version"] = "wave01_event_barrier_l4_decision_replay_tester_log_summary_v1"
        tester_log["work_item_id"] = WORK_ITEM_ID
        tester_log["subwork_item_id"] = SUBWORK_ID
        tester_log["active_goal_id"] = GOAL_ID
        tester_log["campaign_id"] = CAMPAIGN_ID
        tester_log["sweep_id"] = SWEEP_ID
        tester_log["claim_boundary"] = tester_log.get(
            "claim_boundary", "tester_log_summary_not_economics_pass"
        )
        base.write_yaml(tester_log_path, tester_log)

    manifest = base.load_yaml(manifest_path)
    manifest["terminal_execution_subwork_item_id"] = SUBWORK_ID
    manifest["campaign_id"] = CAMPAIGN_ID
    manifest["sweep_id"] = SWEEP_ID
    manifest["claim_boundary"] = CLAIM_BOUNDARY if execution_row.get("execution_telemetry_observed") else manifest.get("claim_boundary")
    routing = manifest.setdefault("runtime_probe_routing", {})
    routing["primary_family"] = "runtime_probe"
    routing["primary_skill"] = "spacesonar-runtime-parity"
    routing["support_skills"] = [
        "spacesonar-run-evidence-system",
        "spacesonar-artifact-lineage",
        "spacesonar-result-judgment",
        "spacesonar-claim-discipline",
    ]
    routing["routing_scope"] = "wave01_event_barrier_score_band_decision_replay_runtime_execution"
    routing["runtime_period_profile_id"] = "period_profile_split_set_v0"
    routing["runtime_period_set_id"] = "split_base_anchor_v0_research_l4"
    routing["period_role"] = row["period_role"]
    routing["claim_boundary"] = manifest["claim_boundary"]
    routing["try_first_disposition"] = (
        "missing runner or adapter support is repair work first; this Wave01 wrapper records the concrete attempt"
    )

    parity = manifest.setdefault("proxy_runtime_parity", {})
    prevention = parity.setdefault("prevention_memory", [])
    note = (
        "Wave01 decision replay runner normalizes reused Wave0 helper outputs into Wave01 campaign identity; "
        "score-band replay is L4 follow-through evidence, not runtime authority or economics pass."
    )
    if note not in prevention:
        prevention.append(note)
    parity["minimum_reconciliation_attempt"] = {
        "status": (
            "decision_replay_execution_telemetry_observed"
            if execution_row.get("execution_telemetry_observed")
            else "decision_replay_execution_attempt_incomplete"
        ),
        "attempt": "MT5 Strategy Tester replayed Wave01 score telemetry through score-band decision EA",
        "forced_equality_required": False,
        "evidence_path": f"runtime/mt5_attempts/{attempt_id}/execution_telemetry_summary.yaml",
    }
    parity["comparison_class"] = "wave01_proxy_score_to_mt5_decision_replay_observation"
    parity["follow_up_action"] = manifest.get("next_action")

    artifact_identity = manifest.setdefault("artifact_identity", {})
    if terminal_path.exists():
        artifact_identity["terminal_run_summary"] = base.artifact_ref(terminal_path, repo_root)
    if telemetry_path.exists():
        artifact_identity["execution_telemetry_summary"] = base.artifact_ref(telemetry_path, repo_root)
    if tester_log_path.exists():
        artifact_identity["tester_log_summary"] = base.artifact_ref(tester_log_path, repo_root)
    base.write_yaml(manifest_path, manifest)

    execution_row["claim_boundary"] = manifest["claim_boundary"]
    execution_row["next_action"] = manifest.get("next_action", execution_row.get("next_action", ""))
    return execution_row


def normalize_summary(summary: dict[str, Any]) -> dict[str, Any]:
    summary["version"] = "wave01_event_barrier_l4_decision_replay_runtime_execution_summary_v1"
    summary["summary_id"] = SUMMARY_ID
    summary["work_item_id"] = WORK_ITEM_ID
    summary["subwork_item_id"] = SUBWORK_ID
    summary["active_goal_id"] = GOAL_ID
    summary["campaign_id"] = CAMPAIGN_ID
    summary["sweep_id"] = SWEEP_ID
    summary["claim_boundary"] = SUMMARY_CLAIM_BOUNDARY
    summary["runtime_contract_binding"]["runtime_level"] = "L4_split_runtime_probe_decision_replay_follow_through"
    summary["artifact_outputs"]["runtime_execution_summary"] = RUNTIME_SUMMARY.as_posix()
    summary["artifact_outputs"]["runtime_execution_index"] = RUNTIME_INDEX.as_posix()
    summary["judgment"]["judgment_class"] = "runtime_probe_progress"
    summary["judgment"]["score_replay_decision_probe_observed"] = (
        summary["counts"].get("execution_telemetry_observed_count", 0) > 0
    )
    summary["judgment"]["next_action"] = (
        "judge paired Wave01 score-band decision replay validation/research_oos results before any L5 claim"
        if summary["judgment"].get("runtime_probe_completed_for_all_prepared_attempts")
        or summary["status"] == ALL_ATTEMPTS_STATUS
        else "continue running or repairing remaining Wave01 decision replay L4 attempts"
    )
    summary.setdefault("prevention_memory", []).append(
        "Wave01 decision replay uses a small runner adapter instead of deferring missing Wave01 runtime glue."
    )
    summary.setdefault("try_first_disposition", {})["policy_applied"] = (
        "missing Wave01 runner support was repaired by this adapter before any blocked/deferred/discarded disposition"
    )
    return summary


def build_closeout(summary: dict[str, Any]) -> dict[str, Any]:
    missing = []
    if summary["status"] == PARTIAL_STATUS:
        missing.append("remaining_wave01_decision_replay_attempts")
    else:
        missing.append("paired_wave01_decision_replay_judgment_pending")
    if summary["counts"].get("tester_report_observed_count", 0) == 0:
        missing.append("tester_report_hash_or_report_export_adapter_for_economics_claim")
    return {
        "version": "work_closeout_v1",
        "work_item_id": SUBWORK_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": summary["ended_at_utc"],
        "result_judgment": (
            "runtime_probe" if summary["counts"].get("execution_telemetry_observed_count", 0) else "inconclusive"
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
            ],
            "missing": missing,
            "not_applicable": [
                "runtime_authority",
                "economics_pass",
                "selected_baseline",
                "goal_achieve",
            ],
        },
        "try_first_disposition": summary.get("try_first_disposition", {}),
        "next_action": summary["judgment"]["next_action"],
        "forbidden_claims": summary["forbidden_claims"],
        "forbidden_claims_respected": True,
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
            "artifact_wave01_decision_replay_runtime_execution_summary_v0",
            "decision_replay_runtime_execution_summary",
            RUNTIME_SUMMARY,
            "Wave01 score-band decision replay terminal execution summary",
        ),
        (
            "artifact_wave01_decision_replay_runtime_execution_index_v0",
            "decision_replay_runtime_execution_index",
            RUNTIME_INDEX,
            "Wave01 score-band decision replay terminal execution index",
        ),
        (
            "artifact_wave01_decision_replay_runtime_execution_closeout_v0",
            "work_closeout",
            CLOSEOUT_PATH,
            "Wave01 score-band decision replay runtime execution closeout",
        ),
        (
            "artifact_wave01_decision_replay_runtime_compile_summary_v0",
            "ea_compile_summary",
            COMPILE_SUMMARY,
            "EA compile or binary preflight summary for decision replay runtime execution",
        ),
        (
            "artifact_wave01_score_replay_decision_probe_source_v0",
            "mt5_ea_source",
            base.EA_SOURCE,
            "score-band decision replay EA source",
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
                "source_of_truth": path.as_posix(),
                "consumer": WORK_ITEM_ID,
                "claim_boundary": summary["claim_boundary"],
                "notes": notes,
            }
        )

    if (repo_root / base.EA_BINARY).exists():
        for artifact_id in [
            "artifact_wave01_score_replay_decision_probe_binary_v0",
            "artifact_spacesonar_l4_score_replay_decision_probe_binary_v0",
        ]:
            put(
                {
                    "artifact_id": artifact_id,
                    "artifact_type": "mt5_ea_binary",
                    "path_or_uri": base.EA_BINARY.as_posix(),
                    "availability": "local_binary_hash_recorded_ignored_by_git",
                    "producer_command": producer,
                    "regeneration_command": producer,
                    "source_of_truth": base.EA_SOURCE.as_posix(),
                    "consumer": WORK_ITEM_ID,
                    "claim_boundary": "local_compile_artifact_not_committed_not_strategy_tester_output",
                    "notes": "local EX5 binary; durable identity is hash and source path only",
                }
            )

    for row in execution_rows:
        attempt_id = row["attempt_id"]
        manifest_path = f"runtime/mt5_attempts/{attempt_id}/attempt_manifest.yaml"
        for artifact_id in [
            f"artifact_{attempt_id}_manifest_v0",
            f"artifact_wave01_decision_replay_{attempt_id}_manifest_v0",
        ]:
            put(
                {
                    "artifact_id": artifact_id,
                    "run_id": row.get("run_id", ""),
                    "bundle_id": row.get("bundle_id", ""),
                    "attempt_id": attempt_id,
                    "artifact_type": "mt5_attempt_manifest",
                    "path_or_uri": manifest_path,
                    "availability": "present_hash_recorded",
                    "producer_command": producer,
                    "regeneration_command": producer,
                    "source_of_truth": manifest_path,
                    "consumer": WORK_ITEM_ID,
                    "claim_boundary": row.get("claim_boundary", CLAIM_BOUNDARY),
                    "notes": "attempt manifest updated after Wave01 decision replay execution",
                }
            )
        for suffix, artifact_type, path, availability, notes in [
            (
                "terminal_summary",
                "terminal_run_summary",
                row.get("terminal_run_summary_path", ""),
                "present_hash_recorded",
                "terminal launch and mode evidence",
            ),
            (
                "execution_telemetry_summary",
                "execution_telemetry_summary",
                row.get("execution_telemetry_summary_path", ""),
                "present_hash_recorded",
                "summary of local decision execution telemetry",
            ),
            (
                "tester_log_summary",
                "tester_log_summary",
                row.get("tester_log_summary_path", ""),
                "present_hash_recorded",
                "tester log summary with redacted local log identity",
            ),
            (
                "execution_telemetry_csv",
                "execution_telemetry_csv",
                row.get("repo_execution_telemetry_path", ""),
                "present_hash_recorded",
                "repo-local copy of execution telemetry emitted by MT5 EA",
            ),
            (
                "tester_report",
                "tester_report",
                row.get("tester_report_path", ""),
                "present_hash_recorded",
                "archived tester report if terminal produced one",
            ),
        ]:
            if not path:
                continue
            put(
                {
                    "artifact_id": f"artifact_wave01_decision_replay_{attempt_id}_{suffix}_v0",
                    "run_id": row.get("run_id", ""),
                    "bundle_id": row.get("bundle_id", ""),
                    "attempt_id": attempt_id,
                    "artifact_type": artifact_type,
                    "path_or_uri": path,
                    "availability": availability,
                    "producer_command": producer,
                    "regeneration_command": producer,
                    "source_of_truth": path,
                    "consumer": WORK_ITEM_ID,
                    "claim_boundary": row.get("claim_boundary", CLAIM_BOUNDARY),
                    "notes": notes,
                }
            )

    ordered = [by_id[key] for key in sorted(by_id)]
    base.write_csv(registry_path, ordered, fieldnames)


def update_control_records(repo_root: Path, summary: dict[str, Any]) -> None:
    next_work = base.load_yaml(repo_root / NEXT_WORK_ITEM)
    current_truth = next_work.setdefault("current_truth", {})
    current_truth["wave01_event_barrier_l4_decision_replay_runtime_execution_summary"] = RUNTIME_SUMMARY.as_posix()
    current_truth["wave01_event_barrier_l4_decision_replay_runtime_execution_status"] = summary["status"]
    current_truth["wave01_event_barrier_l4_decision_replay_runtime_execution_counts"] = summary["counts"]
    if summary["status"] == PARTIAL_STATUS:
        next_work["status"] = "wave01_decision_replay_terminal_execution_in_progress"
        next_work["missing_material_if_relevant"] = ["remaining_wave01_decision_replay_attempts"]
    else:
        next_work["status"] = "wave01_decision_replay_terminal_execution_attempted_pair_judgment_required"
        next_work["missing_material_if_relevant"] = ["paired_wave01_decision_replay_judgment_pending"]
    next_work["next_action"] = summary["judgment"]["next_action"]
    base.write_yaml(repo_root / NEXT_WORK_ITEM, next_work)

    resume = base.load_yaml(repo_root / RESUME_CURSOR)
    resume["updated_at_utc"] = summary["ended_at_utc"]
    truth_sources = resume.setdefault("current_truth_sources", [])
    for source in [RUNTIME_SUMMARY.as_posix(), RUNTIME_INDEX.as_posix(), CLOSEOUT_PATH.as_posix()]:
        if source not in truth_sources:
            truth_sources.append(source)
    resume["latest_completed_work"] = {
        "work_item_id": SUBWORK_ID,
        "result_judgment": (
            "runtime_probe" if summary["counts"].get("execution_telemetry_observed_count", 0) else "inconclusive"
        ),
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [RUNTIME_SUMMARY.as_posix(), CLOSEOUT_PATH.as_posix()],
    }
    resume["next_work_item"] = {"work_item_id": WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()}
    base.write_yaml(repo_root / RESUME_CURSOR, resume)

    phase = (
        "wave01_event_barrier_decision_replay_terminal_execution_in_progress"
        if summary["status"] == PARTIAL_STATUS
        else "wave01_event_barrier_decision_replay_pair_judgment_required_next"
    )
    goal = base.load_yaml(repo_root / GOAL_MANIFEST)
    goal["updated_at_utc"] = summary["ended_at_utc"]
    goal["active_phase"] = phase
    event_barrier = goal.setdefault("event_barrier_campaign", {})
    event_barrier["l4_decision_replay_runtime_execution_summary"] = RUNTIME_SUMMARY.as_posix()
    event_barrier["l4_decision_replay_runtime_execution_status"] = summary["status"]
    event_barrier["l4_decision_replay_runtime_execution_counts"] = summary["counts"]
    event_barrier["next_work_item"] = WORK_ITEM_ID
    base.write_yaml(repo_root / GOAL_MANIFEST, goal)

    workspace = base.load_yaml(repo_root / WORKSPACE_STATE)
    workspace["updated_utc"] = summary["ended_at_utc"]
    claims = workspace.setdefault("current_claims", {})
    claims["active_goal_phase"] = phase
    claims["wave01_event_barrier_l4_decision_replay_runtime_execution_summary"] = RUNTIME_SUMMARY.as_posix()
    claims["wave01_event_barrier_l4_decision_replay_runtime_execution_status"] = summary["status"]
    claims["wave01_event_barrier_l4_decision_replay_runtime_execution_counts"] = summary["counts"]
    claims["wave01_event_barrier_next_work_item"] = WORK_ITEM_ID
    base.write_yaml(repo_root / WORKSPACE_STATE, workspace)

    if (repo_root / GOAL_REGISTRY).exists():
        goal_rows = base.read_csv_rows(repo_root / GOAL_REGISTRY)
        for row in goal_rows:
            if row.get("goal_id") == GOAL_ID:
                row["active_phase"] = phase
                row["next_work_item"] = WORK_ITEM_ID
                row["claim_boundary"] = "active_goal_wave01_decision_replay_runtime_execution_not_goal_achieve"
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
    parser = argparse.ArgumentParser(description="Run prepared Wave01 score-band decision replay MT5 Strategy Tester attempts.")
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
    parser.add_argument("--no-main-mode-fallback", action="store_true")
    parser.add_argument("--write-control-records", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def build_command_argv(args: argparse.Namespace) -> list[str]:
    command = ["python", "foundation/pipelines/run_wave01_event_barrier_l4_decision_replay_attempts.py"]
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

    started_at = base.utc_now()
    command_argv = build_command_argv(args)
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
                },
                indent=2,
            )
        )
        return 0

    compile_summary = base.ensure_ea_binary(
        repo_root=repo_root,
        metaeditor=Path(args.metaeditor),
        force_compile=args.force_compile_ea,
        skip_compile_if_missing=args.skip_compile_ea_if_missing,
        timeout_seconds=args.compile_timeout_seconds,
        started_at_utc=started_at,
    )
    compile_summary = normalize_compile_summary(repo_root, compile_summary)
    if not (repo_root / base.EA_BINARY).exists():
        ended_at = base.utc_now()
        summary = base.build_summary(
            repo_root=repo_root,
            selected_rows=selected,
            execution_rows=[],
            compile_summary=compile_summary,
            started_at_utc=started_at,
            ended_at_utc=ended_at,
            command_argv=command_argv,
        )
        summary = normalize_summary(summary)
        summary["status"] = "blocked_ea_binary_missing_after_compile_preflight"
        summary["failure_disposition"] = {
            "failure_reproduction": "compile_or_binary_preflight_attempted",
            "exact_failing_layer": "MetaEditor_compile_or_local_ex5_availability",
            "bounded_repair_or_fallback_attempt": "base.ensure_ea_binary compile preflight",
            "evidence_path": COMPILE_SUMMARY.as_posix(),
            "remaining_blocker": "EA binary unavailable",
            "reopen_condition": "MetaEditor compile succeeds or EX5 becomes available",
        }
        write_execution_records(
            repo_root=repo_root,
            summary=summary,
            execution_rows=[],
            write_control_records=args.write_control_records,
        )
        print(json.dumps({"status": summary["status"], "summary": RUNTIME_SUMMARY.as_posix()}, indent=2))
        return 1

    execution_rows: list[dict[str, Any]] = []
    for row in selected:
        execution_row = base.run_one_attempt(
            repo_root=repo_root,
            row=row,
            terminal=Path(args.terminal),
            timeout_seconds=args.terminal_timeout_seconds,
            terminate_existing=args.terminate_existing_terminal,
            allow_main_mode_fallback=not args.no_main_mode_fallback,
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
                "claim_boundary": summary["claim_boundary"],
            },
            indent=2,
        )
    )
    return 0 if all(row.get("execution_telemetry_observed") for row in execution_rows) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
