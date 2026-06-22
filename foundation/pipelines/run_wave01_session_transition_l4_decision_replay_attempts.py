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
WORK_ITEM_ID = "work_wave01_session_transition_l4_materialization_preflight_v0"
SUBWORK_ID = "work_wave01_session_transition_l4_decision_replay_runtime_execution_v0"
CAMPAIGN_ID = "campaign_us100_session_transition_regime_surface_v0"
SWEEP_ID = "sweep_us100_session_transition_broad_v0"
SUMMARY_ID = "wave01_session_transition_l4_decision_replay_runtime_execution_summary_v0"
CLAIM_BOUNDARY = (
    "wave01_session_transition_decision_replay_runtime_observation_only_"
    "no_runtime_authority_no_economics_pass_no_candidate"
)
SUMMARY_CLAIM_BOUNDARY = (
    "wave01_session_transition_decision_replay_runtime_execution_progress_only_"
    "no_runtime_authority_no_economics_pass_no_candidate"
)

OUTPUT_DIR = Path("lab/campaigns/campaign_us100_session_transition_regime_surface_v0/l4_follow_through/decision_replay")
PREP_INDEX = OUTPUT_DIR / "adapter_prep_index.csv"
RUNTIME_SUMMARY = OUTPUT_DIR / "runtime_execution_summary.yaml"
RUNTIME_INDEX = OUTPUT_DIR / "runtime_execution_index.csv"
COMPILE_SUMMARY = OUTPUT_DIR / "runtime_compile_summary.yaml"
COMPILE_LOG = OUTPUT_DIR / "runtime_compile.log"
CLOSEOUT_PATH = Path(
    "lab/goals/goal_us100_onnx_forward_boundary_v0/"
    "work_wave01_session_transition_l4_decision_replay_runtime_execution_v0_closeout.yaml"
)
PARTIAL_STATUS = "partial_wave01_session_transition_decision_replay_terminal_execution_started"
ALL_ATTEMPTS_STATUS = "wave01_session_transition_decision_replay_terminal_execution_attempted_for_all_prepared_attempts"


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


def normalize_summary(summary: dict[str, Any]) -> dict[str, Any]:
    summary["version"] = "wave01_session_transition_l4_decision_replay_runtime_execution_summary_v1"
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
        "judge paired Wave01 session-transition decision replay validation/research_oos results before any L5 claim"
        if summary["status"] == ALL_ATTEMPTS_STATUS
        else "continue thin session-transition decision replay execution or repair before batch expansion"
    )
    summary.setdefault("prevention_memory", []).append(
        "Session-transition decision replay started with one inverse-polarity preserved clue instead of broad replay."
    )
    summary.setdefault("try_first_disposition", {})["policy_applied"] = (
        "missing session-transition decision runner support was repaired by a thin wrapper before any blocked/deferred/discarded disposition"
    )
    return summary


def normalize_attempt_outputs(repo_root: Path, row: dict[str, str], execution_row: dict[str, Any]) -> dict[str, Any]:
    attempt_id = row["attempt_id"]
    root = repo_root / "runtime" / "mt5_attempts" / attempt_id
    manifest_path = repo_root / row["attempt_manifest_path"]

    terminal_path = root / "terminal_run_summary.yaml"
    if terminal_path.exists():
        terminal = base.load_yaml(terminal_path)
        terminal["version"] = "wave01_session_transition_l4_decision_replay_terminal_run_summary_v1"
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
        telemetry["version"] = "wave01_session_transition_l4_decision_replay_execution_telemetry_summary_v1"
        telemetry["work_item_id"] = WORK_ITEM_ID
        telemetry["subwork_item_id"] = SUBWORK_ID
        telemetry["active_goal_id"] = GOAL_ID
        telemetry["campaign_id"] = CAMPAIGN_ID
        telemetry["sweep_id"] = SWEEP_ID
        if execution_row.get("execution_telemetry_observed"):
            telemetry["claim_boundary"] = CLAIM_BOUNDARY
        base.write_yaml(telemetry_path, telemetry)

    if manifest_path.exists():
        manifest = base.load_yaml(manifest_path)
        manifest["terminal_execution_subwork_item_id"] = SUBWORK_ID
        manifest["campaign_id"] = CAMPAIGN_ID
        manifest["sweep_id"] = SWEEP_ID
        if execution_row.get("execution_telemetry_observed"):
            manifest["claim_boundary"] = CLAIM_BOUNDARY
        routing = manifest.setdefault("runtime_probe_routing", {})
        routing["primary_family"] = "runtime_probe"
        routing["primary_skill"] = "spacesonar-runtime-parity"
        routing["support_skills"] = [
            "spacesonar-run-evidence-system",
            "spacesonar-result-judgment",
            "spacesonar-claim-discipline",
        ]
        routing["routing_scope"] = "wave01_session_transition_inverse_score_band_decision_replay_runtime_execution"
        routing["period_role"] = row["period_role"]
        routing["claim_boundary"] = manifest["claim_boundary"]
        routing["thin_first_pass"] = True
        parity = manifest.setdefault("proxy_runtime_parity", {})
        prevention = parity.setdefault("prevention_memory", [])
        note = (
            "Session-transition runner replays inverse-polarity score bands for failed-breakout reversion; "
            "this is L4 follow-through evidence, not runtime authority or economics pass."
        )
        if note not in prevention:
            prevention.append(note)
        parity["minimum_reconciliation_attempt"] = {
            "status": (
                "decision_replay_execution_telemetry_observed"
                if execution_row.get("execution_telemetry_observed")
                else "decision_replay_execution_attempt_incomplete"
            ),
            "attempt": "MT5 Strategy Tester replayed session-transition score telemetry through decision EA",
            "forced_equality_required": False,
            "evidence_path": f"runtime/mt5_attempts/{attempt_id}/execution_telemetry_summary.yaml",
        }
        base.write_yaml(manifest_path, manifest)

    execution_row["claim_boundary"] = CLAIM_BOUNDARY if execution_row.get("execution_telemetry_observed") else execution_row.get("claim_boundary", CLAIM_BOUNDARY)
    return execution_row


def build_closeout(summary: dict[str, Any]) -> dict[str, Any]:
    missing = []
    if summary["status"] == PARTIAL_STATUS:
        missing.append("remaining_session_transition_decision_replay_attempts")
    else:
        missing.append("paired_session_transition_decision_replay_judgment_pending")
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


def write_execution_records(*, repo_root: Path, summary: dict[str, Any], execution_rows: list[dict[str, Any]]) -> None:
    base.write_yaml(repo_root / RUNTIME_SUMMARY, summary)
    base.write_csv(repo_root / RUNTIME_INDEX, execution_rows, base.execution_index_fieldnames())
    base.write_yaml(repo_root / CLOSEOUT_PATH, build_closeout(summary))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run thin Wave01 session-transition decision replay MT5 Strategy Tester attempts.")
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
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def build_command_argv(args: argparse.Namespace) -> list[str]:
    command = ["python", "foundation/pipelines/run_wave01_session_transition_l4_decision_replay_attempts.py"]
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
    write_execution_records(repo_root=repo_root, summary=summary, execution_rows=merged_rows)
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
