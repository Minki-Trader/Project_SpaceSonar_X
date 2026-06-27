from __future__ import annotations

import argparse
import csv
import hashlib
import json
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
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation.mt5.score_replay_decision_adapter import (
    ADAPTER_ID,
    CLAIM_BOUNDARY,
    DEFAULT_DIRECTION_POLICIES,
    SUPPORTED_DIRECTION_POLICIES,
    attempt_id_for,
    hold_bars_from_horizon,
    normalize_policy,
)


GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
PARENT_WORK_ITEM_ID = "work_wave0_first_batch_l4_follow_through_v0"
WORK_ITEM_ID = "work_wave0_l4_decision_replay_adapter_preparation_v0"
CAMPAIGN_ID = "campaign_us100_task_surface_scout_v0"
SWEEP_ID = "sweep_wave0_broad_surface_scout_v0"
SYNTHESIS_DIR = Path("lab/campaigns/campaign_us100_task_surface_scout_v0/synthesis")
SUMMARY_PATH = SYNTHESIS_DIR / "decision_replay_adapter_preparation_summary.yaml"
INDEX_PATH = SYNTHESIS_DIR / "decision_replay_adapter_preparation_index.csv"
COMPILE_SUMMARY_PATH = SYNTHESIS_DIR / "decision_replay_adapter_compile_summary.yaml"
COMPILE_LOG_PATH = SYNTHESIS_DIR / "decision_replay_adapter_compile.log"
CLOSEOUT_PATH = Path(
    "lab/goals/goal_us100_onnx_forward_boundary_v0/work_wave0_l4_decision_replay_adapter_preparation_v0_closeout.yaml"
)
INGREDIENT_REGISTRY = Path("docs/registers/ingredient_card_registry.csv")
PAIR_INDEX = Path("lab/campaigns/campaign_us100_task_surface_scout_v0/l4_follow_through/l4_pair_judgment_index.csv")
PREP_INDEX = Path("lab/campaigns/campaign_us100_task_surface_scout_v0/l4_follow_through/l4_attempt_preparation_index.csv")
EXECUTION_PROFILE = Path("configs/mt5/tester_execution_profile_v0.yaml")
PERIOD_PROFILE = Path("configs/mt5/period_profiles/split_set_v0_runtime_periods.yaml")
RUNTIME_CONTRACT = Path("foundation/config/mt5_runtime_probe_contract.yaml")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")
GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
GOAL_MANIFEST = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml")
NEXT_WORK_ITEM = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml")
RESUME_CURSOR = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml")
EA_SOURCE = Path("foundation/mt5/experts/SpaceSonar_L4_ScoreReplayDecisionProbe.mq5")
EA_BINARY = Path("foundation/mt5/experts/SpaceSonar_L4_ScoreReplayDecisionProbe.ex5")
EA_EXPERT_CONFIG_PATH = "Project_SpaceSonar_X\\foundation\\mt5\\experts\\SpaceSonar_L4_ScoreReplayDecisionProbe.ex5"
COMMON_DECISION_ROOT = "SpaceSonar\\l4_decision_replay"
NEXT_PHASE = "wave01_operating_proof_window_decision_replay_adapter_prepared_terminal_execution_next"


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle)


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.dump(payload, handle, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=False)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def rel(path: Path, repo_root: Path) -> str:
    full = path if path.is_absolute() else repo_root / path
    return full.resolve().relative_to(repo_root.resolve()).as_posix()


def artifact_ref(path: Path, repo_root: Path, *, availability: str = "present_hash_recorded") -> dict[str, Any]:
    full = path if path.is_absolute() else repo_root / path
    return {
        "path": rel(full, repo_root),
        "sha256": sha256(full),
        "size_bytes": full.stat().st_size,
        "availability": availability,
    }


def redact_path(value: str) -> str:
    redacted = value
    for env_name, token in {
        "USERPROFILE": "${USERPROFILE}",
        "APPDATA": "${APPDATA}",
        "LOCALAPPDATA": "${LOCALAPPDATA}",
        "PROGRAMFILES": "${PROGRAMFILES}",
    }.items():
        raw = str(Path.home()) if env_name == "USERPROFILE" else os.environ.get(env_name)
        if raw:
            redacted = redacted.replace(raw, token)
    return redacted


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


def dependency_summary() -> dict[str, str]:
    return {"python": platform.python_version(), "yaml": yaml.__version__}


def index_by(rows: list[dict[str, str]], key: str) -> dict[str, dict[str, str]]:
    return {row[key]: row for row in rows}


def ingredient_rows(repo_root: Path) -> list[dict[str, str]]:
    rows = read_csv_rows(repo_root / INGREDIENT_REGISTRY)
    return [
        row
        for row in rows
        if row.get("status") == "ingredient_ready_requires_decision_execution_adapter"
        and "do_not_open_L5" in row.get("do_not_repeat", "")
    ]


def horizon_from_bundle(bundle: dict[str, Any]) -> int:
    return hold_bars_from_horizon((bundle.get("target_and_label") or {}).get("horizon_bars"))


def build_tester_config_text(
    *,
    attempt_id: str,
    source_score_telemetry_common_path: str,
    period: dict[str, str],
    execution_profile: dict[str, Any],
    decision_family: str,
    direction_policy: str,
    score_high_threshold: float,
    hold_bars: int,
) -> str:
    tester_defaults = execution_profile["tester_defaults"]
    sizing = execution_profile["position_sizing_boundary"]
    report_name = f"Project_SpaceSonar_X\\runtime\\mt5_attempts\\{attempt_id}\\tester_report"
    execution_telemetry = f"{COMMON_DECISION_ROOT}\\{attempt_id}\\execution_telemetry.csv"
    trade_shape_telemetry = f"{COMMON_DECISION_ROOT}\\{attempt_id}\\trade_shape_telemetry.csv"
    lines = [
        "; SpaceSonar L4 score replay sparse decision probe.",
        "; Replays MT5 score telemetry into tester trades; not ONNX runtime authority.",
        "[Tester]",
        f"Expert={EA_EXPERT_CONFIG_PATH}",
        f"Symbol={execution_profile['scope']['symbol']}",
        f"Period={execution_profile['scope']['timeframe']}",
        "Optimization=0",
        f"Model={tester_defaults['model']['mt5_value']}",
        "Dates=1",
        f"FromDate={period['from_date']}",
        f"ToDate={period['to_date']}",
        "ForwardMode=0",
        f"Deposit={tester_defaults['initial_deposit']['value']}",
        f"Currency={tester_defaults['initial_deposit']['currency']}",
        "ProfitInPips=0",
        f"Leverage={str(tester_defaults['leverage']['value']).split(':')[-1]}",
        f"ExecutionMode={tester_defaults['execution_mode']['mt5_value']}",
        "OptimizationCriterion=0",
        "Visual=0",
        "ReplaceReport=1",
        f"Report={report_name}",
        "ShutdownTerminal=1",
        "",
        "[TesterInputs]",
        f"InpScoreTelemetryPath={source_score_telemetry_common_path}",
        f"InpExecutionTelemetryPath={execution_telemetry}",
        f"InpTradeShapeTelemetryPath={trade_shape_telemetry}",
        f"InpAttemptId={attempt_id}",
        "InpEmitTradeShapeTelemetry=true",
        "InpUseCommonFiles=true",
        f"InpDecisionFamily={decision_family}",
        f"InpDirectionPolicy={direction_policy}",
        f"InpScoreHigh={score_high_threshold}",
        f"InpFixedLot={sizing['default_lot']}",
        f"InpHoldBars={hold_bars}",
        "InpCloseOnFlat=true",
        "InpMaxSpreadPoints=0",
        "InpDeviationPoints=20",
        "InpMagicNumber=260621",
        "",
    ]
    return "\n".join(lines)


def build_attempt_manifest(
    *,
    repo_root: Path,
    attempt_row: dict[str, Any],
    bundle: dict[str, Any],
    source_attempt: dict[str, str],
    created_at_utc: str,
    write_mode: bool,
) -> dict[str, Any]:
    tester_config_path = Path(attempt_row["tester_config_path"])
    ea_binary_available = (repo_root / EA_BINARY).exists()
    artifact_tester_config = (
        artifact_ref(repo_root / tester_config_path, repo_root)
        if write_mode and (repo_root / tester_config_path).exists()
        else {"path": tester_config_path.as_posix(), "status": "pending_write", "availability": "not_written"}
    )
    missing_gates = [
        "Strategy_Tester_terminal_execution",
        "tester_report_hash",
        "economics_metrics",
    ]
    if not ea_binary_available:
        missing_gates.insert(0, "EA_compile_for_score_replay_adapter")
    missing_evidence = [
        "decision_replay_terminal_execution_not_run",
        "tester_report_missing_until_terminal_execution",
        "economics_metrics_missing_until_tester_report",
    ]
    if not ea_binary_available:
        missing_evidence.insert(0, "score_replay_EA_not_compiled_in_this_preparation_step")
    return {
        "version": "mt5_attempt_manifest_v2",
        "attempt_id": attempt_row["attempt_id"],
        "parent_score_attempt_id": attempt_row["source_attempt_id"],
        "adapter_id": ADAPTER_ID,
        "run_id": attempt_row["run_id"],
        "cell_id": attempt_row["cell_id"],
        "bundle_id": attempt_row["bundle_id"],
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": created_at_utc,
        "status": "prepared_pending_terminal_execution" if write_mode else "dry_run_not_written",
        "claim_boundary": CLAIM_BOUNDARY,
        "source_of_truth": attempt_row["attempt_manifest_path"],
        "work_item_id": PARENT_WORK_ITEM_ID,
        "subwork_item_id": WORK_ITEM_ID,
        "runtime_learning_probe_decision": {
            "required": True,
            "decision": "run_required",
            "required_runtime_level": "decision_replay_runtime_probe_before_L5",
            "reason": "Non-diagnostic L4 score-observed ingredient requires a sparse decision-execution adapter before any L5/economics claim.",
            "lowered_claim_if_not_run": "score_replay_adapter_preparation_only_no_runtime_or_economics_claim",
        },
        "period_identity": {
            "period_profile_id": "period_profile_split_set_v0",
            "runtime_period_set_id": source_attempt["runtime_period_set_id"],
            "period_role": attempt_row["period_role"],
            "from_date": attempt_row["from_date"],
            "to_date": attempt_row["to_date"],
            "locked_final_oos_b": "excluded_forbidden_by_default",
        },
        "execution_identity": {
            "execution_profile_id": source_attempt["tester_execution_profile_id"],
            "symbol": "US100",
            "timeframe": "M5",
            "sizing_policy": {"fixed_lot": 0.02, "source": "configs/mt5/tester_execution_profile_v0.yaml"},
            "score_replay_not_onnx_execution": True,
        },
        "runtime_surface_contract": {
            "completion_surface_scope": "full_period_sparse_decision_surface",
            "surface_scope": "full_period_sparse_decision_surface_from_mt5_score_telemetry",
            "source_score_telemetry_common_path": attempt_row["source_score_telemetry_common_path"],
            "source_score_attempt_manifest": source_attempt["attempt_manifest_path"],
            "decision_family": attempt_row["decision_family"],
            "direction_policy": attempt_row["direction_policy"],
            "score_high_threshold": float(attempt_row["score_high_threshold"]),
            "hold_bars": int(attempt_row["hold_bars"]),
            "decision_output": "sparse_tester_trade_orders",
            "forbidden_interpretation": "not_ONNX_runtime_authority_not_standard_L4_completion_until_terminal_report_exists",
        },
        "proxy_runtime_parity": {
            "status": "adapter_prepared_terminal_execution_pending",
            "shared_contract": [
                "US100_M5_closed_bar_base_frame",
                "period_profile_split_set_v0",
                "us100_m5_fpmarkets_tester_execution_v0",
                "source_MT5_score_telemetry_full_period",
            ],
            "known_differences": [
                "This adapter replays previously observed MT5 score telemetry and does not run ONNX in the trading EA.",
                "Direction-agnostic tradeability scores require an explicit side policy before tester trades can exist.",
            ],
            "interpretation_drift_risks": [
                "bar_close_time_lookup_alignment",
                "score_threshold_translation",
                "direction_policy_injected_for_direction_agnostic_surface",
                "tester_fill_cost_spread_lot_rounding",
                "hold_bars_exit_semantics",
            ],
            "minimum_reconciliation_attempt": {
                "status": "prepared",
                "attempt": "score telemetry bar_close_time will be replayed into sparse orders in MT5 terminal",
                "forced_equality_required": False,
            },
            "unit_semantics": {
                "score": "single_float_score_from_prior_MT5_score_probe",
                "direction": attempt_row["direction_policy"],
                "lot": "fixed_lot_0.02",
                "hold": f"{attempt_row['hold_bars']}_M5_closed_bars",
                "point_tick_digits": "to_be_recorded_from_tester_report",
            },
            "comparison_class": "pending_terminal_execution",
            "divergence_judgment": "pending_terminal_execution",
            "prevention_memory": [
                "Do not treat score telemetry as economics evidence.",
                "Do not hide direction policy injection for direction-agnostic tradeability surfaces.",
                "If score replay trades differ from score-probe decisions, record bar-close lookup and threshold semantics before judging the surface.",
            ],
            "follow_up_action": "execute prepared decision-replay attempts before any L5/economics claim",
            "claim_boundary": "proxy_runtime_parity_tracking_only_no_runtime_authority",
        },
        "artifact_identity": {
            "ea_entrypoint": artifact_ref(repo_root / EA_SOURCE, repo_root),
            "ea_binary": artifact_ref(repo_root / EA_BINARY, repo_root, availability="local_binary_hash_recorded_ignored_by_git")
            if ea_binary_available
            else {"path": EA_BINARY.as_posix(), "availability": "compile_pending_not_committed"},
            "tester_config": artifact_tester_config,
            "bundle": artifact_ref(repo_root / f"runtime/packages/{attempt_row['bundle_id']}/experiment_bundle.json", repo_root),
            "source_score_attempt": {"path": source_attempt["attempt_manifest_path"], "availability": "present_hash_recorded"},
        },
        "required_gate_coverage": {
            "passed": [
                "source_score_telemetry_observed",
                "decision_replay_adapter_source_created",
                "score_replay_EA_compile_succeeded" if ea_binary_available else "score_replay_EA_compile_pending",
                "tester_config_prepared" if write_mode else "tester_config_dry_run_rendered",
                "locked_final_excluded",
            ],
            "missing": missing_gates,
            "not_applicable": ["locked_final_oos_b_access"],
        },
        "missing_evidence": missing_evidence,
        "next_action": "compile and execute score-replay decision attempts; keep L5/economics claims forbidden until tester reports exist",
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


def attempt_index_fieldnames() -> list[str]:
    return [
        "attempt_id",
        "source_attempt_id",
        "run_id",
        "bundle_id",
        "cell_id",
        "period_role",
        "direction_policy",
        "hold_bars",
        "from_date",
        "to_date",
        "status",
        "attempt_manifest_path",
        "tester_config_path",
        "source_score_telemetry_common_path",
        "execution_telemetry_common_path",
        "trade_shape_telemetry_common_path",
        "decision_family",
        "score_high_threshold",
        "runtime_period_set_id",
        "tester_execution_profile_id",
        "claim_boundary",
    ]


def build_attempt_rows_manifests_configs(
    repo_root: Path,
    *,
    direction_policies: list[str],
    write_mode: bool,
    created_at_utc: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, str]]:
    normalized_policies = [normalize_policy(policy) for policy in direction_policies]
    ingredients = ingredient_rows(repo_root)
    pair_by_cell = index_by(read_csv_rows(repo_root / PAIR_INDEX), "cell_id")
    prep_by_attempt = index_by(read_csv_rows(repo_root / PREP_INDEX), "attempt_id")
    execution_profile = load_yaml(repo_root / EXECUTION_PROFILE)
    rows: list[dict[str, Any]] = []
    manifests: dict[str, dict[str, Any]] = {}
    configs: dict[str, str] = {}

    for ingredient in ingredients:
        cell_id = ingredient["ingredient_card_id"].replace("ingredient_", "").replace("_l4_runtime_score_observed_v0", "")
        pair = pair_by_cell[cell_id]
        bundle = load_json(repo_root / "runtime" / "packages" / pair["bundle_id"] / "experiment_bundle.json")
        hold_bars = horizon_from_bundle(bundle)
        score_high = float((bundle.get("decision_surface") or {}).get("score_high_threshold") or 0.0)
        for period_role, source_attempt_id in [
            ("validation", pair["validation_attempt_id"]),
            ("research_oos", pair["research_oos_attempt_id"]),
        ]:
            source_attempt = prep_by_attempt[source_attempt_id]
            for policy in normalized_policies:
                attempt_id = attempt_id_for(cell_id, period_role, policy)
                attempt_dir = Path("runtime/mt5_attempts") / attempt_id
                row: dict[str, Any] = {
                    "attempt_id": attempt_id,
                    "source_attempt_id": source_attempt_id,
                    "run_id": pair["run_id"],
                    "bundle_id": pair["bundle_id"],
                    "cell_id": cell_id,
                    "period_role": period_role,
                    "direction_policy": policy,
                    "hold_bars": hold_bars,
                    "from_date": source_attempt["from_date"],
                    "to_date": source_attempt["to_date"],
                    "status": "prepared_pending_terminal_execution" if write_mode else "dry_run_not_written",
                    "attempt_manifest_path": (attempt_dir / "attempt_manifest.yaml").as_posix(),
                    "tester_config_path": (attempt_dir / "tester_config.ini").as_posix(),
                    "source_score_telemetry_common_path": source_attempt["telemetry_common_path"],
                    "execution_telemetry_common_path": f"{COMMON_DECISION_ROOT}\\{attempt_id}\\execution_telemetry.csv",
                    "trade_shape_telemetry_common_path": f"{COMMON_DECISION_ROOT}\\{attempt_id}\\trade_shape_telemetry.csv",
                    "decision_family": pair["decision_family"],
                    "score_high_threshold": score_high,
                    "runtime_period_set_id": source_attempt["runtime_period_set_id"],
                    "tester_execution_profile_id": source_attempt["tester_execution_profile_id"],
                    "claim_boundary": CLAIM_BOUNDARY,
                }
                config_text = build_tester_config_text(
                    attempt_id=attempt_id,
                    source_score_telemetry_common_path=row["source_score_telemetry_common_path"],
                    period=row,
                    execution_profile=execution_profile,
                    decision_family=row["decision_family"],
                    direction_policy=policy,
                    score_high_threshold=score_high,
                    hold_bars=hold_bars,
                )
                rows.append(row)
                configs[attempt_id] = config_text
                manifests[attempt_id] = build_attempt_manifest(
                    repo_root=repo_root,
                    attempt_row=row,
                    bundle=bundle,
                    source_attempt=source_attempt,
                    created_at_utc=created_at_utc,
                    write_mode=write_mode,
                )

    counts = {
        "source_ingredient_count": len(ingredients),
        "prepared_attempt_count": len(rows),
        "direction_policy_counts": dict(Counter(row["direction_policy"] for row in rows)),
        "period_role_counts": dict(Counter(row["period_role"] for row in rows)),
        "decision_family_counts": dict(Counter(row["decision_family"] for row in rows)),
    }
    ea_binary_available = (repo_root / EA_BINARY).exists()
    missing_evidence = [
        "decision_replay_terminal_execution_not_run",
        "tester_reports_missing_until_execution",
        "economics_metrics_missing_until_tester_report",
    ]
    if not ea_binary_available:
        missing_evidence.insert(0, "score_replay_EA_compile_not_run")
    summary = {
        "version": "wave0_l4_decision_replay_adapter_preparation_summary_v1",
        "summary_id": "wave0_l4_decision_replay_adapter_preparation_v0",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": created_at_utc,
        "status": "decision_replay_adapter_attempts_prepared" if write_mode else "dry_run_not_written",
        "adapter_id": ADAPTER_ID,
        "claim_boundary": CLAIM_BOUNDARY,
        "counts": counts,
        "source_records": {
            "ingredient_registry": INGREDIENT_REGISTRY.as_posix(),
            "pair_judgment_index": PAIR_INDEX.as_posix(),
            "score_attempt_preparation_index": PREP_INDEX.as_posix(),
            "runtime_contract": RUNTIME_CONTRACT.as_posix(),
            "period_profile": PERIOD_PROFILE.as_posix(),
            "execution_profile": EXECUTION_PROFILE.as_posix(),
        },
        "artifact_paths": {
            "summary": SUMMARY_PATH.as_posix(),
            "index": INDEX_PATH.as_posix(),
            "ea_source": EA_SOURCE.as_posix(),
            "compile_summary": COMPILE_SUMMARY_PATH.as_posix(),
        },
        "compile_status": {
            "ea_binary_available": ea_binary_available,
            "ea_binary": artifact_ref(repo_root / EA_BINARY, repo_root, availability="local_binary_hash_recorded_ignored_by_git")
            if ea_binary_available
            else {"path": EA_BINARY.as_posix(), "availability": "missing_local_binary"},
            "compile_summary": COMPILE_SUMMARY_PATH.as_posix(),
        },
        "judgment": {
            "judgment_label": "runtime_probe",
            "result_subject": "score replay sparse decision adapter preparation",
            "metric_identity": "no performance metric; adapter/config preparation only",
            "comparison_baseline": "non-trading L4 score telemetry attempts",
            "missing_evidence": missing_evidence,
            "next_action": "compile and execute prepared score-replay decision attempts before any L5/economics claim",
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
        "environment": {
            "command_argv": ["python", "foundation/pipelines/prepare_wave0_l4_decision_replay_attempts.py"],
            "cwd": ".",
            "python_executable": redact_path(sys.executable),
            "python_version": platform.python_version(),
            "dependency_summary": dependency_summary(),
            **git_state(repo_root),
        },
    }
    return summary, rows, manifests, configs


def compile_result_line(repo_root: Path) -> str:
    log_path = repo_root / COMPILE_LOG_PATH
    if not log_path.exists():
        return "compile_log_not_available"
    raw = log_path.read_bytes()
    text = ""
    for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "cp949"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        if "Result:" in text:
            break
    if "Result:" not in text:
        text = raw.decode("utf-8", errors="replace").replace("\x00", "")
    lines = text.splitlines()
    for line in reversed(lines):
        if "Result:" in line:
            return line.strip()
    return "compile_result_line_missing"


def build_compile_summary(repo_root: Path, created_at_utc: str) -> dict[str, Any]:
    binary_available = (repo_root / EA_BINARY).exists()
    return {
        "version": "score_replay_adapter_compile_summary_v1",
        "summary_id": "score_replay_adapter_compile_summary_v0",
        "created_at_utc": created_at_utc,
        "status": "ea_binary_available" if binary_available else "ea_binary_missing",
        "claim_boundary": "ea_compile_evidence_only_not_strategy_tester_output",
        "ea_source": artifact_ref(repo_root / EA_SOURCE, repo_root),
        "ea_binary": artifact_ref(repo_root / EA_BINARY, repo_root, availability="local_binary_hash_recorded_ignored_by_git")
        if binary_available
        else {"path": EA_BINARY.as_posix(), "availability": "missing_local_binary"},
        "compile_result": compile_result_line(repo_root),
        "raw_log_policy": "raw_compile_log_not_committed_because_it_contains_local_absolute_paths",
        "raw_log_path_local": COMPILE_LOG_PATH.as_posix(),
        "missing_evidence": [] if binary_available else ["ea_binary_missing_or_compile_not_run"],
    }


def write_records(
    repo_root: Path,
    summary: dict[str, Any],
    rows: list[dict[str, Any]],
    manifests: dict[str, dict[str, Any]],
    configs: dict[str, str],
) -> None:
    for row in rows:
        attempt_dir = repo_root / "runtime" / "mt5_attempts" / row["attempt_id"]
        attempt_dir.mkdir(parents=True, exist_ok=True)
        (repo_root / row["tester_config_path"]).write_text(configs[row["attempt_id"]], encoding="utf-8")
    for row in rows:
        manifests[row["attempt_id"]]["artifact_identity"]["tester_config"] = artifact_ref(
            repo_root / row["tester_config_path"], repo_root
        )
        write_yaml(repo_root / row["attempt_manifest_path"], manifests[row["attempt_id"]])
    write_csv(repo_root / INDEX_PATH, rows, attempt_index_fieldnames())
    write_yaml(repo_root / SUMMARY_PATH, summary)
    write_yaml(repo_root / COMPILE_SUMMARY_PATH, build_compile_summary(repo_root, summary["created_at_utc"]))
    write_yaml(repo_root / CLOSEOUT_PATH, build_closeout(summary))
    upsert_artifact_registry(repo_root, summary, rows)
    update_control_records(repo_root, summary)


def build_closeout(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "work_closeout_v1",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": summary["created_at_utc"],
        "result_judgment": "runtime_probe",
        "status": summary["status"],
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [SUMMARY_PATH.as_posix(), INDEX_PATH.as_posix(), COMPILE_SUMMARY_PATH.as_posix(), EA_SOURCE.as_posix()],
        "counts": summary["counts"],
        "missing_evidence": summary["judgment"]["missing_evidence"],
        "next_action": summary["judgment"]["next_action"],
        "forbidden_claims": summary["forbidden_claims"],
    }


def upsert_artifact_registry(repo_root: Path, summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    registry_path = repo_root / ARTIFACT_REGISTRY
    existing = read_csv_rows(registry_path)
    fieldnames = list(existing[0].keys()) if existing else [
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
    by_id = {row["artifact_id"]: row for row in existing}
    producer = " ".join(summary["environment"]["command_argv"] + ["--write-records"])

    def put(row: dict[str, Any]) -> None:
        full = repo_root / row["path_or_uri"]
        if full.exists():
            row["sha256"] = sha256(full)
            row["size_bytes"] = str(full.stat().st_size)
        by_id[row["artifact_id"]] = {key: str(row.get(key, "")) for key in fieldnames}

    for artifact_id, artifact_type, path, notes in [
        ("artifact_wave0_l4_decision_replay_adapter_summary_v0", "decision_replay_adapter_summary", SUMMARY_PATH, "summary for score replay decision adapter preparation"),
        ("artifact_wave0_l4_decision_replay_adapter_index_v0", "decision_replay_adapter_index", INDEX_PATH, "index of prepared score replay decision attempts"),
        ("artifact_wave0_l4_decision_replay_adapter_compile_summary_v0", "ea_compile_summary", COMPILE_SUMMARY_PATH, "redacted compile summary for score replay adapter EA"),
        ("artifact_wave0_l4_decision_replay_adapter_closeout_v0", "work_closeout", CLOSEOUT_PATH, "closeout for score replay adapter preparation"),
        ("artifact_spacesonar_l4_score_replay_decision_probe_source_v0", "mt5_ea_source", EA_SOURCE, "score replay sparse decision EA source"),
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

    for row in rows:
        for suffix, artifact_type, path_key in [
            ("manifest", "mt5_attempt_manifest", "attempt_manifest_path"),
            ("tester_config", "mt5_tester_config", "tester_config_path"),
        ]:
            put(
                {
                    "artifact_id": f"artifact_{row['attempt_id']}_{suffix}_v0",
                    "run_id": row["run_id"],
                    "bundle_id": row["bundle_id"],
                    "attempt_id": row["attempt_id"],
                    "artifact_type": artifact_type,
                    "path_or_uri": row[path_key],
                    "availability": "present_hash_recorded",
                    "producer_command": producer,
                    "regeneration_command": producer,
                    "source_of_truth": row["attempt_manifest_path"],
                    "consumer": WORK_ITEM_ID,
                    "claim_boundary": summary["claim_boundary"],
                    "notes": "score replay adapter preparation; not runtime authority or economics",
                }
            )
    write_csv(registry_path, list(by_id.values()), fieldnames)


def update_control_records(repo_root: Path, summary: dict[str, Any]) -> None:
    state = git_state(repo_root)
    output_hashes = [
        artifact_ref(repo_root / SUMMARY_PATH, repo_root),
        artifact_ref(repo_root / INDEX_PATH, repo_root),
        artifact_ref(repo_root / COMPILE_SUMMARY_PATH, repo_root),
        artifact_ref(repo_root / CLOSEOUT_PATH, repo_root),
        artifact_ref(repo_root / EA_SOURCE, repo_root),
    ]
    input_hashes = [
        artifact_ref(repo_root / INGREDIENT_REGISTRY, repo_root),
        artifact_ref(repo_root / PAIR_INDEX, repo_root),
        artifact_ref(repo_root / PREP_INDEX, repo_root),
    ]

    next_work = load_yaml(repo_root / NEXT_WORK_ITEM)
    current_truth = next_work.setdefault("current_truth", {})
    current_truth["l4_decision_replay_adapter_preparation_summary"] = SUMMARY_PATH.as_posix()
    current_truth["l4_decision_replay_adapter_preparation_status"] = summary["status"]
    current_truth["l4_decision_replay_adapter_preparation_counts"] = summary["counts"]
    next_work["status"] = "decision_replay_adapter_prepared_terminal_execution_next"
    next_work["missing_material_if_relevant"] = summary["judgment"]["missing_evidence"]
    next_work["next_action"] = summary["judgment"]["next_action"]
    next_work["branch_worktree"] = {
        "current_branch": state["branch"],
        "requested_branch": state["branch"],
        "branch_worktree_fit": "fit" if str(state["branch"]).startswith("codex/") else "unchecked_lowered_claim",
        "branch_action": "keep_current_branch",
        "policy_reference": "docs/policies/branch_policy.md",
        "mismatch_claim_effect": "no_branch_mismatch_detected_for_decision_replay_adapter_preparation",
    }
    next_work["execution_provenance"] = {
        "git_sha": state["git_sha"],
        "branch": state["branch"],
        "dirty_flag": state["dirty_flag"],
        "changed_files": state["changed_files"],
        "command_argv": summary["environment"]["command_argv"] + ["--write-records"],
        "python_executable": summary["environment"]["python_executable"],
        "python_version": summary["environment"]["python_version"],
        "key_package_versions": summary["environment"]["dependency_summary"],
        "started_at_utc": summary["created_at_utc"],
        "ended_at_utc": summary["created_at_utc"],
        "input_hashes": input_hashes,
        "output_hashes": output_hashes,
        "unknown_git_claim_effect": "not_applicable_git_state_recorded_claim_still_lowered_no_runtime_authority",
    }
    write_yaml(repo_root / NEXT_WORK_ITEM, next_work)

    resume = load_yaml(repo_root / RESUME_CURSOR)
    resume["updated_at_utc"] = summary["created_at_utc"]
    sources = resume.setdefault("current_truth_sources", [])
    for source in [SUMMARY_PATH.as_posix(), INDEX_PATH.as_posix(), CLOSEOUT_PATH.as_posix(), EA_SOURCE.as_posix()]:
        if source not in sources:
            sources.append(source)
    resume["latest_completed_work"] = {
        "work_item_id": WORK_ITEM_ID,
        "result_judgment": "runtime_probe",
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [SUMMARY_PATH.as_posix(), CLOSEOUT_PATH.as_posix()],
    }
    resume["next_work_item"] = {"work_item_id": PARENT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()}
    write_yaml(repo_root / RESUME_CURSOR, resume)

    goal = load_yaml(repo_root / GOAL_MANIFEST)
    goal["updated_at_utc"] = summary["created_at_utc"]
    goal["active_phase"] = NEXT_PHASE
    wave_spec = goal.setdefault("program_budgets", {}).setdefault("current_wave0_spec", {})
    wave_spec["l4_decision_replay_adapter_preparation_summary"] = SUMMARY_PATH.as_posix()
    wave_spec["l4_decision_replay_adapter_preparation_status"] = summary["status"]
    wave_spec["l4_decision_replay_adapter_preparation_counts"] = summary["counts"]
    write_yaml(repo_root / GOAL_MANIFEST, goal)

    workspace = load_yaml(repo_root / WORKSPACE_STATE)
    workspace["updated_utc"] = summary["created_at_utc"]
    claims = workspace.setdefault("current_claims", {})
    claims["active_goal_phase"] = NEXT_PHASE
    claims["wave0_l4_decision_replay_adapter_preparation_summary"] = SUMMARY_PATH.as_posix()
    claims["wave0_l4_decision_replay_adapter_preparation_status"] = summary["status"]
    claims["wave0_l4_decision_replay_adapter_preparation_counts"] = summary["counts"]
    write_yaml(repo_root / WORKSPACE_STATE, workspace)

    if (repo_root / GOAL_REGISTRY).exists():
        goal_rows = read_csv_rows(repo_root / GOAL_REGISTRY)
        for row in goal_rows:
            if row.get("goal_id") == GOAL_ID:
                row["active_phase"] = NEXT_PHASE
                row["next_work_item"] = PARENT_WORK_ITEM_ID
        if goal_rows:
            write_csv(repo_root / GOAL_REGISTRY, goal_rows, list(goal_rows[0].keys()))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare Wave01 score-replay sparse decision MT5 attempts.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--direction-policy", action="append", choices=SUPPORTED_DIRECTION_POLICIES)
    parser.add_argument("--write-records", action="store_true")
    return parser.parse_args(argv)


def main(*_args: object, **_kwargs: object) -> int:
    from foundation.pipelines.historical_lifecycle_guard import disabled_lifecycle_entrypoint

    return disabled_lifecycle_entrypoint(
        "a run-local/domain evidence command plus locked spacesonar lifecycle transaction for canonical state updates"
    )


if __name__ == "__main__":
    raise SystemExit(main())
