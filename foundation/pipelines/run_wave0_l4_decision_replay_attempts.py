from __future__ import annotations

import argparse
import csv
import math
import re
import shutil
import statistics
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation.pipelines.run_mt5_fixed_fixture_probe import (
    DEFAULT_METAEDITOR,
    DEFAULT_TERMINAL,
    parse_compile_log,
    redact_path,
    run_process,
    run_terminal_sequence,
)
from foundation.pipelines.run_wave0_l4_mt5_attempts import (
    archive_tester_report,
    artifact_ref,
    common_relative_to_path,
    current_git_identity,
    dependency_summary,
    normalize_tester_report_config,
    prepare_tester_report_directories,
    read_csv_rows,
    repo_relative,
    selected_attempt_rows,
    sha256,
    write_csv,
)
from foundation.mt5.runtime_completion import (
    EXPECTED_EXECUTION_PROFILE_ID,
    EXPECTED_PERIOD_PROFILE_ID,
    EXPECTED_RUNTIME_PERIOD_SET_ID,
    RuntimeAttemptState,
    evaluate_runtime_attempt,
    runtime_status,
)
from foundation.pipelines.prepare_wave0_l4_decision_replay_attempts import (
    EA_BINARY,
    EA_SOURCE,
    INDEX_PATH as PREP_INDEX,
)


GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WORK_ITEM_ID = "work_wave0_first_batch_l4_follow_through_v0"
SUBWORK_ID = "work_wave0_l4_decision_replay_runtime_execution_v0"
CAMPAIGN_ID = "campaign_us100_task_surface_scout_v0"
SWEEP_ID = "sweep_wave0_broad_surface_scout_v0"
OUTPUT_DIR = Path("lab/campaigns/campaign_us100_task_surface_scout_v0/synthesis")
RUNTIME_SUMMARY = OUTPUT_DIR / "decision_replay_runtime_execution_summary.yaml"
RUNTIME_INDEX = OUTPUT_DIR / "decision_replay_runtime_execution_index.csv"
COMPILE_SUMMARY = OUTPUT_DIR / "decision_replay_runtime_execution_compile_summary.yaml"
COMPILE_LOG = OUTPUT_DIR / "decision_replay_runtime_execution_compile.log"
CLOSEOUT_PATH = Path(
    "lab/goals/goal_us100_onnx_forward_boundary_v0/work_wave0_l4_decision_replay_runtime_execution_v0_closeout.yaml"
)
NEXT_WORK_ITEM = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml")
RESUME_CURSOR = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml")
GOAL_MANIFEST = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml")
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")
GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")
CLAIM_BOUNDARY = "score_replay_decision_runtime_observation_only_no_runtime_authority_no_economics_pass_no_candidate"
PARTIAL_STATUS = "partial_decision_replay_terminal_execution_started"
ALL_ATTEMPTS_STATUS = "decision_replay_terminal_execution_attempted_for_all_prepared_attempts"


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle)


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.dump(payload, handle, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=False)


def execution_index_fieldnames() -> list[str]:
    return [
        "attempt_id",
        "source_attempt_id",
        "run_id",
        "bundle_id",
        "cell_id",
        "period_role",
        "direction_policy",
        "from_date",
        "to_date",
        "status",
        "result_judgment",
        "source_score_telemetry_observed",
        "execution_telemetry_observed",
        "execution_row_count",
        "open_action_count",
        "close_action_count",
        "open_failed_count",
        "tester_report_observed",
        "runtime_probe_complete",
        "tester_log_observed",
        "tester_final_balance",
        "terminal_mode",
        "terminal_exit_code",
        "terminal_timed_out",
        "terminal_run_summary_path",
        "execution_telemetry_summary_path",
        "tester_log_summary_path",
        "repo_execution_telemetry_path",
        "tester_report_path",
        "claim_boundary",
        "next_action",
    ]


def ensure_ea_binary(
    *,
    repo_root: Path,
    metaeditor: Path,
    force_compile: bool,
    skip_compile_if_missing: bool,
    timeout_seconds: int,
    started_at_utc: str,
    write_summary: bool = True,
) -> dict[str, Any]:
    source = repo_root / EA_SOURCE
    binary = repo_root / EA_BINARY
    should_compile = force_compile or (not binary.exists() and not skip_compile_if_missing)
    process: dict[str, Any] | None = None
    compile_log_ref: dict[str, Any] | None = None
    if should_compile:
        argv = [
            str(metaeditor),
            "/portable",
            f"/compile:{source}",
            f"/log:{repo_root / COMPILE_LOG}",
        ]
        process = run_process(argv, cwd=repo_root, timeout_seconds=timeout_seconds)
        compile_log_ref = parse_compile_log(repo_root / COMPILE_LOG)
    status = "ea_binary_available" if binary.exists() else "ea_binary_missing"
    summary = {
        "version": "decision_replay_runtime_compile_summary_v1",
        "summary_path": COMPILE_SUMMARY.as_posix(),
        "created_at_utc": started_at_utc,
        "status": status,
        "compile_attempted": should_compile,
        "compile_process": process,
        "compile_log": compile_log_ref,
        "ea_source": artifact_ref(source, repo_root),
        "ea_binary": (
            artifact_ref(binary, repo_root, availability="local_binary_hash_recorded_ignored_by_git")
            if binary.exists()
            else {"path": EA_BINARY.as_posix(), "availability": "missing"}
        ),
        "claim_boundary": "ea_compile_or_binary_preflight_only_not_strategy_tester_output",
    }
    if write_summary:
        write_yaml(repo_root / COMPILE_SUMMARY, summary)
    return summary


def normalize_decision_terminal_summary(summary: dict[str, Any]) -> dict[str, Any]:
    result = dict(summary)
    if result.get("mode") == "main_mode_config_fallback":
        result["attempt_claim_boundary"] = "local_decision_replay_main_mode_fallback_only_no_runtime_authority"
    for attempt in result.get("terminal_attempts", []):
        if attempt.get("mode") == "main_mode_config_fallback":
            attempt["attempt_claim_boundary"] = "local_decision_replay_main_mode_fallback_only_no_runtime_authority"
    policy = dict(result.get("terminal_mode_policy") or {})
    if policy.get("main_mode_fallback_used"):
        policy["fallback_reason"] = "portable_attempt_did_not_produce_decision_replay_execution_telemetry"
        policy["claim_effect"] = "decision_replay_local_main_mode_fallback_observation_only_no_standard_portable_completion_claim"
    elif policy:
        policy["claim_effect"] = "decision_replay_standard_portable_attempt_observation"
    result["terminal_mode_policy"] = policy
    return result


def parse_execution_telemetry(path: Path) -> dict[str, Any]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return {"status": "empty_execution_telemetry", "row_count": 0}

    scores: list[float] = []
    spreads: list[float] = []
    action_counts: Counter[str] = Counter()
    signal_counts: Counter[str] = Counter()
    source_decision_counts: Counter[str] = Counter()
    symbol_counts: Counter[str] = Counter()
    period_counts: Counter[str] = Counter()
    direction_policy_counts: Counter[str] = Counter()
    decision_family_counts: Counter[str] = Counter()
    for row in rows:
        action_counts[str(row.get("action", ""))] += 1
        signal_counts[str(row.get("execution_signal", ""))] += 1
        source_decision_counts[str(row.get("source_decision", ""))] += 1
        symbol_counts[str(row.get("symbol", ""))] += 1
        period_counts[str(row.get("period", ""))] += 1
        direction_policy_counts[str(row.get("direction_policy", ""))] += 1
        decision_family_counts[str(row.get("decision_family", ""))] += 1
        try:
            value = float(row.get("score", "nan"))
            if math.isfinite(value):
                scores.append(value)
        except ValueError:
            pass
        try:
            spread = float(row.get("spread_points", "nan"))
            if math.isfinite(spread):
                spreads.append(spread)
        except ValueError:
            pass

    open_actions = sum(action_counts[action] for action in ["open_long", "open_short"])
    close_actions = sum(action_counts[action] for action in ["close_hold_elapsed", "close_flat"])
    return {
        "status": "execution_telemetry_observed",
        "row_count": len(rows),
        "first_bar_close_time": rows[0].get("bar_close_time"),
        "last_bar_close_time": rows[-1].get("bar_close_time"),
        "symbol_counts": dict(sorted(symbol_counts.items())),
        "period_counts": dict(sorted(period_counts.items())),
        "decision_family_counts": dict(sorted(decision_family_counts.items())),
        "direction_policy_counts": dict(sorted(direction_policy_counts.items())),
        "source_decision_counts": dict(sorted(source_decision_counts.items())),
        "execution_signal_counts": dict(sorted(signal_counts.items())),
        "action_counts": dict(sorted(action_counts.items())),
        "trade_action_counts": {
            "open_action_count": open_actions,
            "close_action_count": close_actions,
            "open_failed_count": action_counts["open_failed"],
            "skip_spread_count": action_counts["skip_spread"],
            "no_trade_flat_count": action_counts["no_trade_flat"],
            "hold_same_direction_count": action_counts["hold_same_direction"],
        },
        "score_stats": {
            "finite_count": len(scores),
            "min": min(scores) if scores else None,
            "max": max(scores) if scores else None,
            "mean": statistics.fmean(scores) if scores else None,
        },
        "spread_points_stats": {
            "finite_count": len(spreads),
            "min": min(spreads) if spreads else None,
            "max": max(spreads) if spreads else None,
            "mean": statistics.fmean(spreads) if spreads else None,
        },
    }


def terminal_data_root(repo_root: Path) -> Path:
    for parent in [repo_root, *repo_root.parents]:
        if parent.name.lower() == "mql5":
            return parent.parent
    raise RuntimeError(f"could not derive terminal data root from repo root: {repo_root}")


def latest_tester_log_path(repo_root: Path) -> Path | None:
    logs = terminal_data_root(repo_root) / "Tester" / "logs"
    if not logs.exists():
        return None
    candidates = [path for path in logs.glob("*.log") if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def parse_tester_log_summary(*, log_path: Path, tester_config: Path, attempt_id: str) -> dict[str, Any]:
    text = log_path.read_text(encoding="utf-16", errors="ignore")
    lines = text.splitlines()
    start_index = 0
    config_text = str(tester_config)
    for index, line in enumerate(lines):
        if attempt_id in line or config_text in line:
            start_index = index
    context = lines[start_index:]
    context_text = "\n".join(context)

    final_balance_match = re.search(r"final balance\s+(-?\d+(?:\.\d+)?)\s+([A-Z]+)", context_text)
    orders_match = re.search(r"orders_attempted=(\d+)", context_text)
    rows_match = re.search(r"rows_loaded=(\d+)\s+rows_observed=(\d+)", context_text)
    test_passed_match = re.search(r"Test passed in ([^\r\n]+)", context_text)
    finished_match = re.search(r'last test passed with result "([^"]+)" in ([^\r\n]+)', context_text)
    agent_log_match = re.search(r'log file "([^"]+)" written', context_text)

    return {
        "status": "tester_log_observed",
        "tester_log": {
            "redacted_path": redact_path(str(log_path)),
            "sha256": sha256(log_path),
            "size_bytes": log_path.stat().st_size,
            "availability": "local_tester_log_hash_recorded_not_committed",
        },
        "final_balance": float(final_balance_match.group(1)) if final_balance_match else None,
        "final_balance_currency": final_balance_match.group(2) if final_balance_match else None,
        "orders_attempted": int(orders_match.group(1)) if orders_match else None,
        "rows_loaded": int(rows_match.group(1)) if rows_match else None,
        "rows_observed": int(rows_match.group(2)) if rows_match else None,
        "test_passed_duration": test_passed_match.group(1).strip() if test_passed_match else None,
        "terminal_finished_result": finished_match.group(1) if finished_match else None,
        "terminal_finished_duration": finished_match.group(2).strip() if finished_match else None,
        "agent_log_redacted_path": redact_path(agent_log_match.group(1)) if agent_log_match else None,
        "context_tail": [redact_path(line) for line in context[-30:]],
        "claim_boundary": "tester_log_summary_observation_only_no_economics_pass",
    }


def build_tester_log_summary(repo_root: Path, root: Path, tester_config: Path, attempt_id: str) -> dict[str, Any]:
    log_path = latest_tester_log_path(repo_root)
    summary_path = f"runtime/mt5_attempts/{attempt_id}/tester_log_summary.yaml"
    if not log_path:
        summary = {
            "version": "decision_replay_tester_log_summary_v1",
            "summary_path": summary_path,
            "attempt_id": attempt_id,
            "status": "tester_log_missing",
            "claim_boundary": "tester_log_missing_no_economics_claim",
        }
        write_yaml(root / "tester_log_summary.yaml", summary)
        return summary
    parsed = parse_tester_log_summary(log_path=log_path, tester_config=tester_config, attempt_id=attempt_id)
    summary = {
        "version": "decision_replay_tester_log_summary_v1",
        "summary_path": summary_path,
        "attempt_id": attempt_id,
        **parsed,
    }
    write_yaml(root / "tester_log_summary.yaml", summary)
    return summary


def failure_disposition(
    *,
    reproduction: str,
    exact_failing_layer: str,
    attempt: str,
    evidence_path: str,
    remaining_blocker: str,
    reopen_condition: str,
) -> dict[str, Any]:
    return {
        "required_before_judgments": ["blocked", "deferred", "invalid", "discarded"],
        "status": "recorded",
        "failure_reproduction": reproduction,
        "exact_failing_layer": exact_failing_layer,
        "root_cause_hypothesis": remaining_blocker,
        "repo_controlled_support_gap": True,
        "repair_or_fallback_attempts": [attempt],
        "attempt_blocker_if_no_repair": None,
        "evidence_paths": [evidence_path],
        "remaining_blocker": remaining_blocker,
        "reopen_condition": reopen_condition,
        "claim_effect": "lower_to_investigation_in_progress_until_repaired_or_rerun",
    }


def update_coverage(manifest: dict[str, Any], *, telemetry_observed: bool, report_observed: bool) -> None:
    coverage = manifest.setdefault("required_gate_coverage", {})
    passed = coverage.setdefault("passed", [])
    missing = coverage.setdefault("missing", [])

    def mark_passed(gate: str) -> None:
        if gate in missing:
            missing.remove(gate)
        if gate not in passed:
            passed.append(gate)

    if telemetry_observed:
        mark_passed("Strategy_Tester_terminal_execution")
        mark_passed("execution_telemetry_csv")
        mark_passed("result_judgment_from_score_replay_decision_probe")
    if report_observed:
        mark_passed("tester_report_hash")


def run_one_attempt(
    *,
    repo_root: Path,
    row: dict[str, str],
    terminal: Path,
    timeout_seconds: int,
    terminate_existing: bool,
    allow_main_mode_fallback: bool,
) -> dict[str, Any]:
    attempt_id = row["attempt_id"]
    root = repo_root / "runtime" / "mt5_attempts" / attempt_id
    manifest_path = repo_root / row["attempt_manifest_path"]
    tester_config = repo_root / row["tester_config_path"]
    manifest = load_yaml(manifest_path)
    report_config_summary = normalize_tester_report_config(tester_config, attempt_id)
    manifest.setdefault("artifact_identity", {})["tester_config"] = artifact_ref(tester_config, repo_root)
    write_yaml(manifest_path, manifest)
    source_common = common_relative_to_path(row["source_score_telemetry_common_path"])
    execution_common = common_relative_to_path(row["execution_telemetry_common_path"])
    execution_common.parent.mkdir(parents=True, exist_ok=True)
    if execution_common.exists():
        execution_common.unlink()
    portable_terminal_root = terminal.parent if terminal else DEFAULT_TERMINAL.parent
    main_data_root = terminal_data_root(repo_root)
    report_directory_summary = prepare_tester_report_directories(
        repo_root=repo_root,
        attempt_root=root,
        tester_config=tester_config,
        portable_terminal_root=portable_terminal_root,
        main_terminal_data_root=main_data_root,
    )

    source_observed = source_common.exists()
    if not source_observed:
        terminal_summary = {
            "version": "decision_replay_terminal_run_summary_v1",
            "summary_path": f"runtime/mt5_attempts/{attempt_id}/terminal_run_summary.yaml",
            "attempt_id": attempt_id,
            "run_id": row["run_id"],
            "bundle_id": row["bundle_id"],
            "terminal_not_launched_reason": "source_score_telemetry_missing",
            "source_score_telemetry_redacted": redact_path(str(source_common)),
            "claim_boundary": "missing_source_score_telemetry_no_terminal_execution",
        }
        write_yaml(root / "terminal_run_summary.yaml", terminal_summary)
    else:
        terminal_summary = run_terminal_sequence(
            terminal=terminal,
            tester_config=tester_config,
            common_telemetry=execution_common,
            timeout_seconds=timeout_seconds,
            terminate_existing=terminate_existing,
            allow_main_mode_fallback=allow_main_mode_fallback,
        )
        terminal_summary = normalize_decision_terminal_summary(terminal_summary)
        terminal_summary = {
            **terminal_summary,
            "version": "decision_replay_terminal_run_summary_v1",
            "summary_path": f"runtime/mt5_attempts/{attempt_id}/terminal_run_summary.yaml",
            "attempt_id": attempt_id,
            "source_attempt_id": row["source_attempt_id"],
            "run_id": row["run_id"],
            "bundle_id": row["bundle_id"],
            "tester_config": artifact_ref(tester_config, repo_root),
            "tester_report_config": report_config_summary,
            "tester_report_resolution_prelaunch": report_directory_summary,
            "source_score_telemetry_redacted": redact_path(str(source_common)),
            "execution_telemetry_redacted": redact_path(str(execution_common)),
            "claim_boundary": "decision_replay_terminal_execution_evidence_only_no_runtime_authority_no_economics_pass",
        }
        write_yaml(root / "terminal_run_summary.yaml", terminal_summary)

    telemetry_observed = execution_common.exists()
    telemetry_artifact: dict[str, Any] | None = None
    if telemetry_observed:
        repo_telemetry = root / "telemetry" / "execution_telemetry.csv"
        repo_telemetry.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(execution_common, repo_telemetry)
        telemetry_stats = parse_execution_telemetry(repo_telemetry)
        telemetry_artifact = artifact_ref(repo_telemetry, repo_root, availability="local_telemetry_hash_recorded_ignored_by_git")
        telemetry_summary = {
            "version": "decision_replay_execution_telemetry_summary_v1",
            "summary_path": f"runtime/mt5_attempts/{attempt_id}/execution_telemetry_summary.yaml",
            "attempt_id": attempt_id,
            "source_attempt_id": row["source_attempt_id"],
            "run_id": row["run_id"],
            "bundle_id": row["bundle_id"],
            "period_role": row["period_role"],
            "direction_policy": row["direction_policy"],
            "telemetry": telemetry_artifact,
            "common_telemetry_redacted": redact_path(str(execution_common)),
            "stats": telemetry_stats,
            "claim_boundary": CLAIM_BOUNDARY,
        }
    else:
        fail = failure_disposition(
            reproduction=(
                "source telemetry was checked and MT5 terminal launch was attempted"
                if source_observed
                else "source score telemetry common file was checked before terminal launch"
            ),
            exact_failing_layer=(
                "mt5_strategy_tester_common_file_execution_telemetry"
                if source_observed
                else "source_score_telemetry_common_file"
            ),
            attempt=(
                "portable attempt plus configured main-mode fallback when enabled"
                if source_observed
                else "bounded preflight avoided launching a tester run with missing source telemetry"
            ),
            evidence_path=f"runtime/mt5_attempts/{attempt_id}/terminal_run_summary.yaml",
            remaining_blocker=(
                "execution telemetry CSV not observed in MT5 Common Files"
                if source_observed
                else "source score telemetry CSV not present in MT5 Common Files"
            ),
            reopen_condition=(
                "rerun after EA journal inspection or terminal cleanup if process state was stale"
                if source_observed
                else "recopy source score telemetry from the source L4 attempt or rerun the source score probe"
            ),
        )
        telemetry_summary = {
            "version": "decision_replay_execution_telemetry_summary_v1",
            "summary_path": f"runtime/mt5_attempts/{attempt_id}/execution_telemetry_summary.yaml",
            "attempt_id": attempt_id,
            "source_attempt_id": row["source_attempt_id"],
            "run_id": row["run_id"],
            "bundle_id": row["bundle_id"],
            "period_role": row["period_role"],
            "direction_policy": row["direction_policy"],
            "telemetry": {"path": None, "availability": "missing_after_terminal_execution"},
            "common_telemetry_redacted": redact_path(str(execution_common)),
            "source_score_telemetry_observed": source_observed,
            "stats": {"status": "execution_telemetry_missing", "row_count": 0},
            "failure_disposition": fail,
            "claim_boundary": "terminal_attempt_no_execution_telemetry_no_decision_replay_completion",
        }
    write_yaml(root / "execution_telemetry_summary.yaml", telemetry_summary)

    report = archive_tester_report(
        repo_root,
        root,
        tester_config,
        portable_terminal_root=portable_terminal_root,
        main_terminal_data_root=main_data_root,
    ) if source_observed else {
        "observed": False,
        "status": "tester_report_not_requested_source_score_telemetry_missing",
        "path": None,
        "claim_boundary": "missing_source_no_tester_report_claim",
    }
    report_observed = bool(report.get("observed"))
    report_completed = report.get("status") == "tester_report_archived_local_hash_recorded"
    tester_log_summary = build_tester_log_summary(repo_root, root, tester_config, attempt_id) if source_observed else {
        "version": "decision_replay_tester_log_summary_v1",
        "summary_path": f"runtime/mt5_attempts/{attempt_id}/tester_log_summary.yaml",
        "attempt_id": attempt_id,
        "status": "not_applicable_source_score_telemetry_missing",
        "claim_boundary": "tester_log_not_checked_source_missing",
    }
    tester_log_observed = tester_log_summary.get("status") == "tester_log_observed"

    stats = telemetry_summary.get("stats") or {}
    trade_counts = stats.get("trade_action_counts") or {}
    result_judgment = "runtime_probe" if telemetry_observed else "inconclusive"
    terminal_mode = (terminal_summary.get("terminal_mode_policy") or {}).get("main_mode_fallback_used")
    terminal_mode_label = "main_mode_config_fallback" if terminal_mode else "portable_contract_attempt"
    completion = evaluate_runtime_attempt(
        RuntimeAttemptState(
            terminal_launched=source_observed,
            telemetry_file_observed=telemetry_observed,
            telemetry_rows_observed=telemetry_observed and int(stats.get("row_count") or 0) > 0,
            tester_report_observed=report_observed,
            tester_report_completed=report_completed,
            terminal_mode=terminal_mode_label,
            period_role=row["period_role"],
            period_profile_id=EXPECTED_PERIOD_PROFILE_ID,
            runtime_period_set_id=row.get("runtime_period_set_id") or EXPECTED_RUNTIME_PERIOD_SET_ID,
            execution_profile_id=row.get("tester_execution_profile_id") or EXPECTED_EXECUTION_PROFILE_ID,
            surface_scope="full_period_sparse_decision_surface",
        ),
        required_period_roles=["validation", "research_oos"],
        completion_eligible_surface_scopes=["full_period_deterministic", "full_period_sparse_decision_surface"],
    )
    status = (
        runtime_status(completion, telemetry_kind="decision_replay_execution_telemetry")
        if source_observed
        else "decision_replay_source_score_telemetry_missing"
    )
    manifest["status"] = status
    manifest["claim_boundary"] = CLAIM_BOUNDARY if telemetry_observed else telemetry_summary["claim_boundary"]
    manifest["result_judgment"] = result_judgment
    manifest["execution_state"] = {
        "terminal_launched": source_observed,
        "telemetry_file_observed": telemetry_observed,
        "telemetry_rows_observed": telemetry_observed and int(stats.get("row_count") or 0) > 0,
        "tester_report_observed": report_observed,
        "tester_report_completed": report_completed,
        "terminal_mode": terminal_mode_label,
        "portable_contract_satisfied": completion.portable_contract_satisfied,
        "report_contract_satisfied": completion.report_contract_satisfied,
        "period_contract_satisfied": completion.period_contract_satisfied,
        "surface_contract_satisfied": completion.surface_contract_satisfied,
        "runtime_probe_complete": completion.runtime_probe_complete,
        "missing_requirements": list(completion.missing_requirements),
        "completion_claim_boundary": completion.claim_boundary,
    }
    manifest["runtime_probe_routing"] = {
        "primary_family": "runtime_probe",
        "primary_skill": "spacesonar-runtime-parity",
        "support_skills": [
            "spacesonar-run-evidence-system",
            "spacesonar-artifact-lineage",
            "spacesonar-result-judgment",
            "spacesonar-claim-discipline",
        ],
        "routing_scope": "wave0_l4_score_replay_decision_execution",
        "runtime_period_profile_id": "period_profile_split_set_v0",
        "runtime_period_set_id": "split_base_anchor_v0_research_l4",
        "period_role": row["period_role"],
        "claim_boundary": manifest["claim_boundary"],
    }
    manifest["terminal_run_summary"] = terminal_summary
    manifest["execution_telemetry_summary"] = telemetry_summary
    manifest["tester_log_summary"] = tester_log_summary
    manifest["tester_report"] = report
    if "failure_disposition" in telemetry_summary:
        manifest["failure_disposition"] = telemetry_summary["failure_disposition"]
    artifact_identity = manifest.setdefault("artifact_identity", {})
    artifact_identity["terminal_run_summary"] = artifact_ref(root / "terminal_run_summary.yaml", repo_root)
    artifact_identity["execution_telemetry_summary"] = artifact_ref(root / "execution_telemetry_summary.yaml", repo_root)
    if source_observed:
        artifact_identity["tester_log_summary"] = artifact_ref(root / "tester_log_summary.yaml", repo_root)
    if telemetry_artifact:
        artifact_identity.setdefault("telemetry", {})["repo_execution_copy"] = telemetry_artifact
    artifact_identity["tester_reports"] = [report]
    manifest["missing_evidence"] = []
    if not source_observed:
        manifest["missing_evidence"].append("source_score_telemetry_common_file_missing")
    if not telemetry_observed:
        manifest["missing_evidence"].append("execution_telemetry_csv_missing_after_terminal_execution")
    if not report_observed:
        manifest["missing_evidence"].append("tester_report_missing_or_not_archived")
    if report_observed is False and tester_log_observed:
        manifest["missing_evidence"].append("tester_report_missing_but_tester_log_summary_observed")
    manifest["next_action"] = (
        "parse tester report and judge sparse decision surface with lowered claim boundary"
        if telemetry_observed and report_observed
        else "continue/repair decision replay terminal execution before L5 or economics claim"
    )
    parity = manifest.setdefault("proxy_runtime_parity", {})
    parity["minimum_reconciliation_attempt"] = {
        "status": "decision_replay_execution_telemetry_observed" if telemetry_observed else "decision_replay_execution_attempt_incomplete",
        "attempt": "MT5 Strategy Tester replayed prior score telemetry through sparse decision EA",
        "forced_equality_required": False,
        "evidence_path": f"runtime/mt5_attempts/{attempt_id}/execution_telemetry_summary.yaml",
    }
    parity["divergence_judgment"] = (
        "runtime_decision_execution_observed_pending_tester_report_or_economics_parse"
        if telemetry_observed
        else "runtime_decision_execution_telemetry_missing_after_try_first_record"
    )
    parity["comparison_class"] = "score_replay_decision_observation_not_standard_onnx_l4"
    parity["follow_up_action"] = manifest["next_action"]
    update_coverage(manifest, telemetry_observed=telemetry_observed, report_observed=report_observed)
    write_yaml(manifest_path, manifest)

    return {
        "attempt_id": attempt_id,
        "source_attempt_id": row["source_attempt_id"],
        "run_id": row["run_id"],
        "bundle_id": row["bundle_id"],
        "cell_id": row["cell_id"],
        "period_role": row["period_role"],
        "direction_policy": row["direction_policy"],
        "from_date": row["from_date"],
        "to_date": row["to_date"],
        "status": status,
        "result_judgment": result_judgment,
        "source_score_telemetry_observed": source_observed,
        "execution_telemetry_observed": telemetry_observed,
        "execution_row_count": stats.get("row_count", 0),
        "open_action_count": trade_counts.get("open_action_count", 0),
        "close_action_count": trade_counts.get("close_action_count", 0),
        "open_failed_count": trade_counts.get("open_failed_count", 0),
        "tester_report_observed": report_observed,
        "runtime_probe_complete": completion.runtime_probe_complete,
        "tester_log_observed": tester_log_observed,
        "tester_final_balance": tester_log_summary.get("final_balance"),
        "terminal_mode": terminal_mode_label,
        "terminal_exit_code": terminal_summary.get("exit_code"),
        "terminal_timed_out": terminal_summary.get("timed_out"),
        "terminal_run_summary_path": terminal_summary["summary_path"],
        "execution_telemetry_summary_path": telemetry_summary["summary_path"],
        "tester_log_summary_path": tester_log_summary.get("summary_path", ""),
        "repo_execution_telemetry_path": telemetry_artifact["path"] if telemetry_artifact else "",
        "tester_report_path": report.get("path") or "",
        "claim_boundary": manifest["claim_boundary"],
        "next_action": manifest["next_action"],
    }


def merge_execution_rows(repo_root: Path, new_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_attempt: dict[str, dict[str, Any]] = {}
    index_path = repo_root / RUNTIME_INDEX
    if index_path.exists():
        for row in read_csv_rows(index_path):
            if row.get("attempt_id"):
                by_attempt[row["attempt_id"]] = dict(row)
    for row in new_rows:
        by_attempt[str(row["attempt_id"])] = dict(row)
    prep_rows = read_csv_rows(repo_root / PREP_INDEX)
    ordered = [by_attempt[row["attempt_id"]] for row in prep_rows if row["attempt_id"] in by_attempt]
    prep_ids = {row["attempt_id"] for row in prep_rows}
    extras = [row for attempt_id, row in sorted(by_attempt.items()) if attempt_id not in prep_ids]
    return [*ordered, *extras]


def bool_count(rows: list[dict[str, Any]], key: str) -> int:
    return sum(str(row.get(key)).lower() == "true" for row in rows)


def int_sum(rows: list[dict[str, Any]], key: str) -> int:
    total = 0
    for row in rows:
        try:
            total += int(row.get(key) or 0)
        except (TypeError, ValueError):
            pass
    return total


def build_summary(
    *,
    repo_root: Path,
    selected_rows: list[dict[str, str]],
    execution_rows: list[dict[str, Any]],
    compile_summary: dict[str, Any],
    started_at_utc: str,
    ended_at_utc: str,
    command_argv: list[str],
) -> dict[str, Any]:
    prepared_rows = read_csv_rows(repo_root / PREP_INDEX)
    touched_manifest_count = 0
    runtime_complete_count = 0
    missing_requirements_by_count: Counter[str] = Counter()
    for row in prepared_rows:
        manifest_path = repo_root / row["attempt_manifest_path"]
        if manifest_path.exists():
            manifest = load_yaml(manifest_path)
            state = manifest.get("execution_state") or {}
            if state:
                touched_manifest_count += 1
                if state.get("runtime_probe_complete"):
                    runtime_complete_count += 1
                for requirement in state.get("missing_requirements", []):
                    missing_requirements_by_count[str(requirement)] += 1
    all_attempts_touched = touched_manifest_count >= len(prepared_rows)
    all_attempts_runtime_complete = all_attempts_touched and runtime_complete_count == len(prepared_rows)
    execution_telemetry_count = bool_count(execution_rows, "execution_telemetry_observed")
    tester_report_count = bool_count(execution_rows, "tester_report_observed")
    tester_log_count = bool_count(execution_rows, "tester_log_observed")
    if all_attempts_runtime_complete and tester_report_count > 0:
        next_action = "parse tester reports and decide whether any sparse decision surface deserves L5"
    elif all_attempts_touched and execution_telemetry_count == len(prepared_rows) and tester_log_count == len(prepared_rows):
        next_action = "judge sparse decision surfaces from execution telemetry and tester log summaries; no economics pass until report/equity parser evidence exists"
    elif all_attempts_touched and execution_telemetry_count == len(prepared_rows):
        next_action = "backfill tester log or report evidence before sparse decision judgment"
    else:
        next_action = "continue or repair score replay decision terminal execution before L5 or economics claim"
    return {
        "version": "decision_replay_runtime_execution_summary_v1",
        "summary_id": "wave0_l4_decision_replay_runtime_execution_summary_v0",
        "work_item_id": WORK_ITEM_ID,
        "subwork_item_id": SUBWORK_ID,
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": started_at_utc,
        "ended_at_utc": ended_at_utc,
        "status": ALL_ATTEMPTS_STATUS if all_attempts_touched else PARTIAL_STATUS,
        "claim_boundary": "score_replay_decision_runtime_progress_only_no_runtime_authority_no_economics_pass_no_candidate",
        "runtime_contract_binding": {
            "runtime_level": "score_replay_decision_probe_not_standard_l4_completion",
            "source_l4_score_probe": "prior MT5 score telemetry from validation/research_oos period roles",
            "period_profile_id": "period_profile_split_set_v0",
            "runtime_period_set_id": "split_base_anchor_v0_research_l4",
            "required_period_roles": ["validation", "research_oos"],
            "tester_execution_profile_id": "us100_m5_fpmarkets_tester_execution_v0",
            "locked_final_oos_b": "excluded_forbidden_by_default",
        },
        "counts": {
            "prepared_attempt_count": len(prepared_rows),
            "selected_attempt_count": len(selected_rows),
            "indexed_execution_count": len(execution_rows),
            "executed_attempt_count": len(execution_rows),
            "completed_manifest_count": runtime_complete_count,
            "touched_manifest_count": touched_manifest_count,
            "source_score_telemetry_observed_count": bool_count(execution_rows, "source_score_telemetry_observed"),
            "execution_telemetry_observed_count": execution_telemetry_count,
            "execution_telemetry_missing_count": len(execution_rows) - execution_telemetry_count,
            "tester_report_observed_count": tester_report_count,
            "tester_report_missing_count": len(execution_rows) - tester_report_count,
            "tester_log_observed_count": tester_log_count,
            "terminal_execution_count": len(execution_rows),
            "telemetry_observation_count": execution_telemetry_count,
            "tester_report_observation_count": tester_report_count,
            "portable_contract_count": sum(str(row.get("terminal_mode")) == "portable_contract_attempt" for row in execution_rows),
            "runtime_probe_complete_count": runtime_complete_count,
            "runtime_probe_incomplete_count": len(execution_rows) - runtime_complete_count,
            "open_action_count": int_sum(execution_rows, "open_action_count"),
            "close_action_count": int_sum(execution_rows, "close_action_count"),
            "open_failed_count": int_sum(execution_rows, "open_failed_count"),
            "period_role_counts": dict(sorted(Counter(row["period_role"] for row in execution_rows).items())),
            "direction_policy_counts": dict(sorted(Counter(row["direction_policy"] for row in execution_rows).items())),
            "status_counts": dict(sorted(Counter(row["status"] for row in execution_rows).items())),
            "result_judgment_counts": dict(sorted(Counter(row["result_judgment"] for row in execution_rows).items())),
        },
        "runtime_completion": {
            "all_prepared_attempts_executed": all_attempts_touched,
            "all_prepared_attempts_runtime_complete": all_attempts_runtime_complete,
            "runtime_probe_complete": all_attempts_runtime_complete,
            "missing_requirements_by_count": dict(sorted(missing_requirements_by_count.items())),
        },
        "compile_summary": {
            "path": compile_summary["summary_path"],
            "status": compile_summary["status"],
            "compile_attempted": compile_summary["compile_attempted"],
            "ea_binary": compile_summary["ea_binary"],
        },
        "artifact_outputs": {
            "runtime_execution_summary": RUNTIME_SUMMARY.as_posix(),
            "runtime_execution_index": RUNTIME_INDEX.as_posix(),
            "attempt_terminal_summaries": [row["terminal_run_summary_path"] for row in execution_rows],
            "attempt_execution_telemetry_summaries": [row["execution_telemetry_summary_path"] for row in execution_rows],
            "attempt_tester_log_summaries": [row["tester_log_summary_path"] for row in execution_rows if row.get("tester_log_summary_path")],
        },
        "environment": {
            "command_argv": command_argv,
            "cwd": ".",
            "python_executable": redact_path(sys.executable),
            "python_version": sys.version.split()[0],
            "dependency_summary": dependency_summary(),
            "started_at_utc": started_at_utc,
            "ended_at_utc": ended_at_utc,
            **current_git_identity(repo_root),
        },
        "judgment": {
            "judgment_class": "runtime_probe_progress",
            "standard_l4_completed": all_attempts_runtime_complete,
            "runtime_probe_completed_for_all_prepared_attempts": all_attempts_runtime_complete,
            "all_prepared_attempts_executed": all_attempts_touched,
            "score_replay_decision_probe_observed": bool_count(execution_rows, "execution_telemetry_observed") > 0,
            "runtime_authority": False,
            "economics_pass": False,
            "selected_baseline": False,
            "goal_achieve": False,
            "next_action": next_action,
        },
        "forbidden_claims": [
            "selected_baseline",
            "runtime_authority",
            "economics_pass",
            "materialization_ready",
            "handoff_complete",
            "live_readiness",
            "reviewed_verified_pass",
            "goal_achieve",
        ],
    }


def build_closeout(summary: dict[str, Any]) -> dict[str, Any]:
    missing = ["remaining_decision_replay_attempts"] if summary["status"] == PARTIAL_STATUS else []
    if not (summary.get("runtime_completion") or {}).get("runtime_probe_complete"):
        missing.append("standard_l4_runtime_completion_contract")
    if summary["counts"].get("tester_report_observed_count") == 0:
        missing.append("tester_report_hash_or_report_export_adapter_for_economics_claim")
    return {
        "version": "work_closeout_v1",
        "work_item_id": SUBWORK_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": summary["ended_at_utc"],
        "result_judgment": "runtime_probe" if summary["counts"]["execution_telemetry_observed_count"] else "inconclusive",
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [
            RUNTIME_SUMMARY.as_posix(),
            RUNTIME_INDEX.as_posix(),
            summary["compile_summary"]["path"],
        ],
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
        "next_action": summary["judgment"]["next_action"],
        "forbidden_claims_respected": True,
    }


def upsert_artifact_registry(repo_root: Path, summary: dict[str, Any], execution_rows: list[dict[str, Any]]) -> None:
    registry_path = repo_root / ARTIFACT_REGISTRY
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
    by_id = {row["artifact_id"]: row for row in rows}
    producer = " ".join(summary["environment"]["command_argv"])

    def put(row: dict[str, Any]) -> None:
        path_value = row.get("path_or_uri")
        full = repo_root / path_value if path_value else None
        if full and full.exists():
            row["sha256"] = sha256(full)
            row["size_bytes"] = str(full.stat().st_size)
        by_id[row["artifact_id"]] = {key: str(row.get(key, "")) for key in fieldnames}

    put(
        {
            "artifact_id": "artifact_wave0_l4_decision_replay_runtime_execution_summary_v0",
            "artifact_type": "decision_replay_runtime_execution_summary",
            "path_or_uri": RUNTIME_SUMMARY.as_posix(),
            "availability": "present_hash_recorded",
            "producer_command": producer,
            "regeneration_command": producer,
            "source_of_truth": RUNTIME_SUMMARY.as_posix(),
            "consumer": WORK_ITEM_ID,
            "claim_boundary": summary["claim_boundary"],
            "notes": "score replay sparse decision terminal execution summary; no runtime authority or economics pass",
        }
    )
    put(
        {
            "artifact_id": "artifact_wave0_l4_decision_replay_runtime_execution_index_v0",
            "artifact_type": "decision_replay_runtime_execution_index",
            "path_or_uri": RUNTIME_INDEX.as_posix(),
            "availability": "present_hash_recorded",
            "producer_command": producer,
            "regeneration_command": producer,
            "source_of_truth": RUNTIME_SUMMARY.as_posix(),
            "consumer": WORK_ITEM_ID,
            "claim_boundary": summary["claim_boundary"],
            "notes": "index of score replay sparse decision terminal executions",
        }
    )
    put(
        {
            "artifact_id": "artifact_wave0_l4_decision_replay_runtime_compile_summary_v0",
            "artifact_type": "decision_replay_runtime_compile_summary",
            "path_or_uri": summary["compile_summary"]["path"],
            "availability": "present_hash_recorded",
            "producer_command": producer,
            "regeneration_command": producer,
            "source_of_truth": RUNTIME_SUMMARY.as_posix(),
            "consumer": WORK_ITEM_ID,
            "claim_boundary": "ea_compile_or_binary_preflight_only_not_strategy_tester_output",
            "notes": "score replay decision EA binary availability check for runtime execution",
        }
    )
    if (repo_root / EA_BINARY).exists():
        put(
            {
                "artifact_id": "artifact_spacesonar_l4_score_replay_decision_probe_binary_v0",
                "artifact_type": "mt5_ea_binary",
                "path_or_uri": EA_BINARY.as_posix(),
                "availability": "local_binary_hash_recorded_ignored_by_git",
                "producer_command": producer,
                "regeneration_command": "compile with MetaEditor64 /portable /compile:<path>",
                "source_of_truth": EA_SOURCE.as_posix(),
                "consumer": WORK_ITEM_ID,
                "claim_boundary": "ea_compile_or_binary_preflight_only_not_strategy_tester_output",
                "notes": "compiled score replay decision EA binary hash; local ignored artifact",
            }
        )
    for row in execution_rows:
        attempt_root = f"runtime/mt5_attempts/{row['attempt_id']}"
        for suffix, artifact_type, path, availability, note in [
            ("manifest", "mt5_attempt_manifest", f"{attempt_root}/attempt_manifest.yaml", "present_hash_recorded", "decision replay attempt manifest updated with terminal evidence"),
            ("tester_config", "mt5_tester_config", f"{attempt_root}/tester_config.ini", "present_hash_recorded", "tester config used for score replay decision execution"),
            ("terminal_summary", "terminal_run_summary", row["terminal_run_summary_path"], "present_hash_recorded", "terminal launch and mode evidence"),
            ("execution_telemetry_summary", "execution_telemetry_summary", row["execution_telemetry_summary_path"], "present_hash_recorded", "summary of local decision execution telemetry"),
            ("tester_log_summary", "tester_log_summary", row.get("tester_log_summary_path", ""), "present_hash_recorded", "tester log summary with redacted local log identity"),
        ]:
            if not path:
                continue
            put(
                {
                    "artifact_id": f"artifact_{row['attempt_id']}_{suffix}_v0",
                    "run_id": row["run_id"],
                    "bundle_id": row["bundle_id"],
                    "attempt_id": row["attempt_id"],
                    "artifact_type": artifact_type,
                    "path_or_uri": path,
                    "availability": availability,
                    "producer_command": producer,
                    "regeneration_command": producer,
                    "source_of_truth": f"{attempt_root}/attempt_manifest.yaml",
                    "consumer": WORK_ITEM_ID,
                    "claim_boundary": row["claim_boundary"],
                    "notes": note,
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
                    "notes": "raw execution telemetry is local/generated and ignored; summary is committed",
                }
            )
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
                    "source_of_truth": f"{attempt_root}/attempt_manifest.yaml",
                    "consumer": WORK_ITEM_ID,
                    "claim_boundary": "tester_report_local_evidence_only_no_economics_pass",
                    "notes": "raw tester report is generated/local; parse before economics claim",
                }
            )
    write_csv(registry_path, list(by_id.values()), fieldnames)


def update_control_records(repo_root: Path, summary: dict[str, Any]) -> None:
    next_work = load_yaml(repo_root / NEXT_WORK_ITEM)
    current_truth = next_work.setdefault("current_truth", {})
    current_truth["l4_decision_replay_runtime_execution_summary"] = RUNTIME_SUMMARY.as_posix()
    current_truth["l4_decision_replay_runtime_execution_status"] = summary["status"]
    current_truth["l4_decision_replay_runtime_execution_counts"] = summary["counts"]
    next_work["status"] = (
        "decision_replay_terminal_execution_in_progress"
        if summary["status"] == PARTIAL_STATUS
        else "decision_replay_terminal_execution_attempted_for_prepared_attempts"
    )
    next_work["missing_material_if_relevant"] = (
        ["remaining_decision_replay_attempts"]
        if summary["status"] == PARTIAL_STATUS
        else ["tester_report_export_or_tester_log_economics_parser_pending"]
    )
    next_work["next_action"] = summary["judgment"]["next_action"]
    write_yaml(repo_root / NEXT_WORK_ITEM, next_work)

    resume = load_yaml(repo_root / RESUME_CURSOR)
    resume["updated_at_utc"] = summary["ended_at_utc"]
    sources = resume.setdefault("current_truth_sources", [])
    for source in [RUNTIME_SUMMARY.as_posix(), RUNTIME_INDEX.as_posix()]:
        if source not in sources:
            sources.append(source)
    resume["latest_completed_work"] = {
        "work_item_id": SUBWORK_ID,
        "result_judgment": "runtime_probe" if summary["counts"]["execution_telemetry_observed_count"] else "inconclusive",
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [RUNTIME_SUMMARY.as_posix(), CLOSEOUT_PATH.as_posix()],
    }
    resume["next_work_item"] = {"work_item_id": WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()}
    write_yaml(repo_root / RESUME_CURSOR, resume)

    phase = "wave01_operating_proof_window_decision_replay_terminal_execution_in_progress"
    if summary["status"] == ALL_ATTEMPTS_STATUS:
        phase = "wave01_operating_proof_window_decision_replay_terminal_execution_attempted"
    goal = load_yaml(repo_root / GOAL_MANIFEST)
    goal["updated_at_utc"] = summary["ended_at_utc"]
    goal["active_phase"] = phase
    wave_spec = goal.setdefault("program_budgets", {}).setdefault("current_wave0_spec", {})
    wave_spec["l4_decision_replay_runtime_execution_summary"] = RUNTIME_SUMMARY.as_posix()
    wave_spec["l4_decision_replay_runtime_execution_status"] = summary["status"]
    wave_spec["l4_decision_replay_runtime_execution_counts"] = summary["counts"]
    write_yaml(repo_root / GOAL_MANIFEST, goal)

    workspace = load_yaml(repo_root / WORKSPACE_STATE)
    workspace["updated_utc"] = summary["ended_at_utc"]
    claims = workspace.setdefault("current_claims", {})
    claims["wave0_l4_decision_replay_runtime_execution_summary"] = RUNTIME_SUMMARY.as_posix()
    claims["wave0_l4_decision_replay_runtime_execution_status"] = summary["status"]
    claims["wave0_l4_decision_replay_runtime_execution_counts"] = summary["counts"]
    claims["active_goal_phase"] = phase
    write_yaml(repo_root / WORKSPACE_STATE, workspace)

    goal_rows = read_csv_rows(repo_root / GOAL_REGISTRY)
    for row in goal_rows:
        if row.get("goal_id") == GOAL_ID:
            row["active_phase"] = phase
            row["next_work_item"] = WORK_ITEM_ID
    write_csv(repo_root / GOAL_REGISTRY, goal_rows, list(goal_rows[0].keys()) if goal_rows else [])


def write_execution_records(
    *,
    repo_root: Path,
    summary: dict[str, Any],
    execution_rows: list[dict[str, Any]],
    write_control_records: bool,
) -> None:
    write_yaml(repo_root / RUNTIME_SUMMARY, summary)
    write_csv(repo_root / RUNTIME_INDEX, execution_rows, execution_index_fieldnames())
    write_yaml(repo_root / CLOSEOUT_PATH, build_closeout(summary))
    upsert_artifact_registry(repo_root, summary, execution_rows)
    if write_control_records:
        update_control_records(repo_root, summary)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run prepared Wave0/Wave01 score replay decision MT5 attempts.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--attempt-id", action="append", default=[])
    parser.add_argument("--period-role", action="append", choices=["validation", "research_oos"], default=[])
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--include-completed", action="store_true")
    parser.add_argument("--terminal", default=str(DEFAULT_TERMINAL))
    parser.add_argument("--metaeditor", default=str(DEFAULT_METAEDITOR))
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
    command = ["python", "foundation/pipelines/run_wave0_l4_decision_replay_attempts.py"]
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
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    started_at = utc_now()
    command_argv = build_command_argv(args)
    rows = read_csv_rows(repo_root / PREP_INDEX)
    selected = selected_attempt_rows(
        rows,
        repo_root=repo_root,
        attempt_ids=set(args.attempt_id) if args.attempt_id else None,
        period_roles=set(args.period_role) if args.period_role else None,
        limit=None if args.limit == 0 else args.limit,
        include_completed=args.include_completed,
    )
    compile_summary = ensure_ea_binary(
        repo_root=repo_root,
        metaeditor=Path(args.metaeditor),
        force_compile=args.force_compile_ea,
        skip_compile_if_missing=args.skip_compile_ea_if_missing,
        timeout_seconds=args.compile_timeout_seconds,
        started_at_utc=started_at,
        write_summary=not args.dry_run,
    )
    if args.dry_run:
        ended_at = utc_now()
        summary = build_summary(
            repo_root=repo_root,
            selected_rows=selected,
            execution_rows=[],
            compile_summary=compile_summary,
            started_at_utc=started_at,
            ended_at_utc=ended_at,
            command_argv=command_argv,
        )
        summary["status"] = "dry_run_no_terminal_execution"
        summary["selected_attempt_ids"] = [row["attempt_id"] for row in selected]
        print(yaml.dump(summary, sort_keys=False, allow_unicode=False))
        return 0

    execution_rows: list[dict[str, Any]] = []
    for row in selected:
        execution_rows.append(
            run_one_attempt(
                repo_root=repo_root,
                row=row,
                terminal=Path(args.terminal),
                timeout_seconds=args.terminal_timeout_seconds,
                terminate_existing=args.terminate_existing_terminal,
                allow_main_mode_fallback=args.allow_main_mode_fallback and not args.no_main_mode_fallback,
            )
        )
    merged_rows = merge_execution_rows(repo_root, execution_rows)
    ended_at = utc_now()
    summary = build_summary(
        repo_root=repo_root,
        selected_rows=selected,
        execution_rows=merged_rows,
        compile_summary=compile_summary,
        started_at_utc=started_at,
        ended_at_utc=ended_at,
        command_argv=command_argv,
    )
    write_execution_records(
        repo_root=repo_root,
        summary=summary,
        execution_rows=merged_rows,
        write_control_records=args.write_control_records,
    )
    print(yaml.dump(summary, sort_keys=False, allow_unicode=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
