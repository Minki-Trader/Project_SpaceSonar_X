from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import re
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

from foundation.mt5.score_replay_decision_adapter import (
    ADAPTER_ID,
    SUPPORTED_DIRECTION_POLICIES,
    attempt_id_for,
    decision_family_execution_kind,
    is_direct_trade_adapter_eligible,
    normalize_policy,
)
from spacesonar.control_plane.store import dump_csv, dump_yaml, filesystem_path, repo_relative, sha256_file


GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WAVE_ID = "wave_us100_wave02_tradeability_decision_surface_v0"
CAMPAIGN_ID = "campaign_us100_wave02_cost_risk_holding_surface_v0"
IDEA_ID = "idea_us100_wave02_cost_risk_holding_surface_v0"
HYPOTHESIS_ID = "hyp_us100_wave02_cost_risk_holding_runtime_alignment_v0"
SURFACE_ID = "surface_us100_wave02_cost_risk_holding_v0"
SWEEP_ID = "sweep_us100_wave02_cost_risk_holding_broad_v0"

PARENT_WORK_ITEM_ID = "work_wave02_cost_risk_holding_l5_routing_decision_v0"
WORK_ITEM_ID = "work_wave02_cost_risk_holding_l4_decision_replay_adapter_preparation_v0"
NEXT_WORK_ITEM_ID = "work_wave02_cost_risk_holding_decision_replay_runtime_execution_v0"

OUTPUT_DIR = Path("lab/campaigns/campaign_us100_wave02_cost_risk_holding_surface_v0/l4_follow_through/decision_replay")
SUMMARY_PATH = OUTPUT_DIR / "adapter_prep_summary.yaml"
INDEX_PATH = OUTPUT_DIR / "adapter_prep_index.csv"
ELIGIBILITY_INDEX_PATH = OUTPUT_DIR / "adapter_eligibility_index.csv"
COMPILE_SUMMARY_PATH = OUTPUT_DIR / "adapter_compile_summary.yaml"
ROUTING_SUMMARY = OUTPUT_DIR / "l5_routing_decision_summary.yaml"
ROUTING_INDEX = OUTPUT_DIR / "l5_routing_decision_index.csv"
PAIR_INDEX = Path("lab/campaigns/campaign_us100_wave02_cost_risk_holding_surface_v0/l4_follow_through/l4_pair_judgment_index.csv")
SOURCE_PREP_INDEX = Path(
    "lab/campaigns/campaign_us100_wave02_cost_risk_holding_surface_v0/l4_follow_through/l4_attempt_preparation_index.csv"
)
CLOSEOUT_PATH = Path(
    "lab/goals/goal_us100_onnx_forward_boundary_v0/"
    "work_wave02_cost_risk_holding_l4_decision_replay_adapter_preparation_v0_closeout.yaml"
)
NEXT_WORK_ITEM = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml")
RESUME_CURSOR = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml")
GOAL_MANIFEST = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml")
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
CAMPAIGN_MANIFEST = Path("lab/campaigns/campaign_us100_wave02_cost_risk_holding_surface_v0/campaign_manifest.yaml")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")
GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")
EXECUTION_PROFILE = Path("configs/mt5/tester_execution_profile_v0.yaml")
RUNTIME_CONTRACT = Path("foundation/config/mt5_runtime_probe_contract.yaml")
PERIOD_PROFILE = Path("configs/mt5/period_profiles/split_set_v0_runtime_periods.yaml")
EA_SOURCE = Path("foundation/mt5/experts/SpaceSonar_L4_ScoreReplayDecisionProbe.mq5")
EA_BINARY = Path("foundation/mt5/experts/SpaceSonar_L4_ScoreReplayDecisionProbe.ex5")
EA_EXPERT_CONFIG_PATH = "Project_SpaceSonar_X\\foundation\\mt5\\experts\\SpaceSonar_L4_ScoreReplayDecisionProbe.ex5"
COMMON_DECISION_ROOT = "SpaceSonar\\wave02_cost_risk_holding_l4_decision_replay"

CLAIM_BOUNDARY = (
    "wave02_cost_risk_holding_decision_replay_adapter_preparation_only_"
    "no_selected_baseline_no_runtime_authority_no_economics_pass_no_candidate_no_live_readiness_no_goal_achieve"
)
NEXT_CLAIM_BOUNDARY = (
    "wave02_cost_risk_holding_decision_replay_runtime_execution_pending_"
    "no_selected_baseline_no_runtime_authority_no_economics_pass_no_candidate_no_live_readiness_no_goal_achieve"
)
STATUS = "wave02_cost_risk_holding_decision_replay_adapter_attempts_prepared_terminal_execution_next"
NEXT_STATUS = "wave02_cost_risk_holding_decision_replay_terminal_execution_pending"
NEXT_ACTION = (
    "execute prepared Wave02 cost/risk/holding sparse decision replay MT5 attempts "
    "with portable terminal only, then judge paired validation/research_oos results"
)
FORBIDDEN_CLAIMS = [
    "selected_baseline",
    "operating_reference",
    "operating_promotion",
    "runtime_authority",
    "economics_pass",
    "materialization_ready",
    "handoff_complete",
    "live_readiness",
    "reviewed_verified_pass",
    "goal_achieve",
]


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def path_exists(path: Path) -> bool:
    return os.path.exists(filesystem_path(path))


def read_yaml(path: Path) -> dict[str, Any]:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        payload = yaml.safe_load(handle)
    return payload if isinstance(payload, dict) else {}


def read_json(path: Path) -> dict[str, Any]:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
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
    write_text(path, dump_yaml(payload))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    write_text(path, dump_csv(fieldnames, rows))


def artifact_ref(path: Path, *, availability: str = "present_hash_recorded") -> dict[str, Any]:
    full = REPO_ROOT / path if not path.is_absolute() else path
    return {
        "path": repo_relative(REPO_ROOT, full),
        "sha256": sha256_file(full),
        "size_bytes": os.stat(filesystem_path(full)).st_size,
        "availability": availability,
    }


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
    redacted = value
    replacements = {
        "USERPROFILE": "${USERPROFILE}",
        "APPDATA": "${APPDATA}",
        "LOCALAPPDATA": "${LOCALAPPDATA}",
        "PROGRAMFILES": "${PROGRAMFILES}",
    }
    for env_name, token in replacements.items():
        raw = str(Path.home()) if env_name == "USERPROFILE" else os.environ.get(env_name)
        if raw:
            redacted = redacted.replace(raw, token)
    return redacted


def bundle_path(bundle_id: str) -> Path:
    return Path("runtime/packages") / bundle_id / "experiment_bundle.json"


def load_bundle(bundle_id: str) -> dict[str, Any]:
    return read_json(REPO_ROOT / bundle_path(bundle_id))


def infer_hold_bars(bundle: dict[str, Any]) -> tuple[int, str]:
    decision_surface = bundle.get("decision_surface") or {}
    for source_name, value in [
        ("decision_surface.holding_variant", decision_surface.get("holding_variant")),
        ("target_and_label.label_variant", (bundle.get("target_and_label") or {}).get("label_variant")),
        ("label_recipe_id", bundle.get("label_recipe_id")),
    ]:
        text = str(value or "")
        match = re.search(r"(?:timeout|_h|h)(\d+)", text)
        if match:
            return max(1, int(match.group(1))), source_name
    return 6, "fallback_h6_recorded_for_cost_risk_holding_without_explicit_horizon"


def build_tester_config_text(
    *,
    attempt_id: str,
    source_score_telemetry_common_path: str,
    period: dict[str, Any],
    execution_profile: dict[str, Any],
    decision_family: str,
    direction_policy: str,
    score_low_threshold: float,
    score_high_threshold: float,
    hold_bars: int,
) -> str:
    tester_defaults = execution_profile["tester_defaults"]
    sizing = execution_profile["position_sizing_boundary"]
    report_name = f"reports\\spacesonar\\{attempt_id}\\tester_report"
    execution_telemetry = f"{COMMON_DECISION_ROOT}\\{attempt_id}\\execution_telemetry.csv"
    trade_shape_telemetry = f"{COMMON_DECISION_ROOT}\\{attempt_id}\\trade_shape_telemetry.csv"
    lines = [
        "; SpaceSonar Wave02 cost/risk/holding L4 decision replay probe.",
        "; Replays CRH MT5 score telemetry into sparse tester trades; not runtime authority.",
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
        f"InpScoreLow={score_low_threshold}",
        f"InpFixedLot={sizing['default_lot']}",
        f"InpHoldBars={hold_bars}",
        "InpCloseOnFlat=true",
        "InpMaxSpreadPoints=0",
        "InpDeviationPoints=20",
        "InpMagicNumber=260629",
        "",
    ]
    return "\n".join(lines)


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
        "hold_bars_source",
        "from_date",
        "to_date",
        "status",
        "attempt_manifest_path",
        "tester_config_path",
        "source_score_telemetry_common_path",
        "execution_telemetry_common_path",
        "trade_shape_telemetry_common_path",
        "decision_family",
        "decision_execution_kind",
        "decision_output",
        "score_low_threshold",
        "score_high_threshold",
        "runtime_period_set_id",
        "tester_execution_profile_id",
        "claim_boundary",
    ]


def eligibility_fieldnames() -> list[str]:
    return [
        "cell_id",
        "run_id",
        "bundle_id",
        "decision_family",
        "decision_execution_kind",
        "proxy_judgment",
        "source_l5_routing_status",
        "routing_decision",
        "direct_trade_adapter_eligible",
        "eligibility_reason",
        "prepared_attempt_count",
        "claim_boundary",
        "next_action",
    ]


def build_attempt_manifest(
    *,
    row: dict[str, Any],
    source_attempt: dict[str, str],
    bundle: dict[str, Any],
    created_at_utc: str,
) -> dict[str, Any]:
    ea_binary_available = path_exists(REPO_ROOT / EA_BINARY)
    return {
        "version": "mt5_attempt_manifest_v2",
        "attempt_id": row["attempt_id"],
        "parent_score_attempt_id": row["source_attempt_id"],
        "adapter_id": ADAPTER_ID,
        "run_id": row["run_id"],
        "cell_id": row["cell_id"],
        "bundle_id": row["bundle_id"],
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": created_at_utc,
        "status": "prepared_pending_terminal_execution",
        "claim_boundary": CLAIM_BOUNDARY,
        "source_of_truth": row["attempt_manifest_path"],
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "runtime_learning_probe_decision": {
            "required": True,
            "decision": "run_required",
            "required_runtime_level": "L4_split_runtime_probe_decision_replay_follow_through",
            "reason": (
                "Wave02 CRH preserved score observations require sparse score-band decision replay "
                "before any candidate-specific L5 routing claim."
            ),
            "lowered_claim_if_not_run": "decision_replay_adapter_preparation_only_no_runtime_authority_no_economics_pass_no_candidate",
        },
        "period_identity": {
            "period_profile_id": "period_profile_split_set_v0",
            "runtime_period_set_id": row["runtime_period_set_id"],
            "period_role": row["period_role"],
            "from_date": row["from_date"],
            "to_date": row["to_date"],
            "locked_final_oos_b": "excluded_forbidden_by_default",
        },
        "execution_identity": {
            "execution_profile_id": row["tester_execution_profile_id"],
            "symbol": "US100",
            "timeframe": "M5",
            "sizing_policy": {"fixed_lot": 0.02, "source": EXECUTION_PROFILE.as_posix()},
            "score_replay_not_onnx_execution": True,
            "direction_policy": row["direction_policy"],
        },
        "runtime_surface_contract": {
            "completion_surface_scope": "full_period_sparse_decision_surface",
            "surface_scope": "wave02_cost_risk_holding_sparse_score_band_decision_replay_from_mt5_score_telemetry",
            "source_score_telemetry_common_path": row["source_score_telemetry_common_path"],
            "source_score_attempt_manifest": source_attempt["attempt_manifest_path"],
            "decision_family": row["decision_family"],
            "decision_execution_kind": row["decision_execution_kind"],
            "direction_policy": row["direction_policy"],
            "score_low_threshold": float(row["score_low_threshold"]),
            "score_high_threshold": float(row["score_high_threshold"]),
            "hold_bars": int(row["hold_bars"]),
            "hold_bars_source": row["hold_bars_source"],
            "decision_output": row["decision_output"],
            "forbidden_interpretation": "not_runtime_authority_not_economics_pass_not_candidate_until_terminal_judgment_exists",
        },
        "proxy_runtime_parity": {
            "status": "adapter_prepared_terminal_execution_pending",
            "shared_contract": [
                "US100_M5_closed_bar_base_frame",
                "period_profile_split_set_v0",
                "us100_m5_fpmarkets_tester_execution_v0",
                "source_MT5_score_telemetry_full_period",
                "score_band_thresholds_from_CRH_bundle",
                "score_band_side_policy_high_long_low_short",
            ],
            "known_differences": [
                "This adapter replays previously observed MT5 score telemetry and does not run ONNX in the trading EA.",
                "CRH score telemetry decision field is unknown; execution uses declared score_low/high thresholds.",
                "The adapter observes sparse tester trades but cannot create runtime authority or economics pass by itself.",
            ],
            "interpretation_drift_risks": [
                "bar_close_time_lookup_alignment",
                "score_threshold_translation",
                "score_band_side_direction_policy",
                "hold_bars_exit_semantics",
                "tester_fill_cost_spread_lot_rounding",
            ],
            "minimum_reconciliation_attempt": {
                "status": "prepared",
                "attempt": "score telemetry bar_close_time will be replayed into sparse MT5 orders using score band side thresholds",
                "forced_equality_required": False,
            },
            "unit_semantics": {
                "score": "single_float_score_from_prior_MT5_score_probe",
                "high_threshold": float(row["score_high_threshold"]),
                "low_threshold": float(row["score_low_threshold"]),
                "side_mapping": row["decision_output"],
                "lot": "fixed_lot_0.02",
                "hold": f"{row['hold_bars']}_M5_closed_bars",
            },
            "comparison_class": "pending_terminal_execution",
            "divergence_judgment": "pending_terminal_execution",
            "prevention_memory": [
                "Do not infer CRH candidate status from score telemetry alone.",
                "Score band replay is a bounded adapter attempt, not selected baseline or runtime authority.",
                "If replay loses or is unstable, record negative memory instead of repairing into a candidate track.",
            ],
            "follow_up_action": NEXT_ACTION,
            "claim_boundary": "proxy_runtime_parity_tracking_only_no_runtime_authority",
        },
        "artifact_identity": {
            "ea_entrypoint": artifact_ref(EA_SOURCE),
            "ea_binary": artifact_ref(EA_BINARY, availability="local_binary_hash_recorded_ignored_by_git")
            if ea_binary_available
            else {"path": EA_BINARY.as_posix(), "availability": "compile_pending_not_committed"},
            "bundle": artifact_ref(bundle_path(row["bundle_id"])),
            "source_score_attempt": {"path": source_attempt["attempt_manifest_path"], "availability": "present_hash_recorded"},
            "tester_config": {"path": row["tester_config_path"], "availability": "pending_write"},
        },
        "required_gate_coverage": {
            "passed": [
                "source_score_telemetry_observed",
                "wave02_crh_decision_adapter_prepared",
                "tester_config_prepared",
                "locked_final_excluded",
            ],
            "missing": ["Strategy_Tester_terminal_execution", "tester_report_hash", "economics_metrics"],
            "not_applicable": ["locked_final_oos_b_access"],
        },
        "missing_evidence": [
            "decision_replay_terminal_execution_not_run",
            "tester_report_missing_until_terminal_execution",
            "economics_metrics_missing_until_tester_report",
            "candidate_specific_L5_manifest_not_opened",
        ],
        "next_action": NEXT_ACTION,
        "forbidden_claims": FORBIDDEN_CLAIMS,
    }


def build_records(created_at_utc: str, direction_policy: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, str]]:
    routing_rows = [
        row
        for row in read_csv_rows(REPO_ROOT / ROUTING_INDEX)
        if row.get("routing_decision") == "prepare_decision_execution_adapter"
    ]
    pair_rows_by_cell = {row["cell_id"]: row for row in read_csv_rows(REPO_ROOT / PAIR_INDEX)}
    source_prep_by_attempt = {row["attempt_id"]: row for row in read_csv_rows(REPO_ROOT / SOURCE_PREP_INDEX)}
    execution_profile = read_yaml(REPO_ROOT / EXECUTION_PROFILE)
    direction_policy = normalize_policy(direction_policy)
    attempt_rows: list[dict[str, Any]] = []
    eligibility_rows: list[dict[str, Any]] = []
    manifests: dict[str, dict[str, Any]] = {}
    configs: dict[str, str] = {}

    for route in sorted(routing_rows, key=lambda item: item["cell_id"]):
        pair = pair_rows_by_cell[route["cell_id"]]
        bundle = load_bundle(pair["bundle_id"])
        decision_surface = bundle.get("decision_surface") or {}
        decision_family = pair["decision_family"]
        execution_kind = decision_family_execution_kind(decision_family)
        eligible = is_direct_trade_adapter_eligible(decision_family)
        eligibility_reason = (
            "eligible_crh_score_band_side_adapter"
            if eligible and execution_kind == "score_band_directional"
            else "requires_new_decision_surface_not_direct_trade_adapter"
        )
        prepared_for_cell = 0
        if eligible:
            low = float(decision_surface["score_low_threshold"])
            high = float(decision_surface["score_high_threshold"])
            hold_bars, hold_source = infer_hold_bars(bundle)
            for period_role, source_attempt_id in [
                ("validation", pair["validation_attempt_id"]),
                ("research_oos", pair["research_oos_attempt_id"]),
            ]:
                source_attempt = source_prep_by_attempt[source_attempt_id]
                attempt_id = attempt_id_for(pair["cell_id"], period_role, direction_policy)
                attempt_dir = Path("runtime/mt5_attempts") / attempt_id
                row: dict[str, Any] = {
                    "attempt_id": attempt_id,
                    "source_attempt_id": source_attempt_id,
                    "run_id": pair["run_id"],
                    "bundle_id": pair["bundle_id"],
                    "cell_id": pair["cell_id"],
                    "period_role": period_role,
                    "direction_policy": direction_policy,
                    "hold_bars": hold_bars,
                    "hold_bars_source": hold_source,
                    "from_date": source_attempt["from_date"],
                    "to_date": source_attempt["to_date"],
                    "status": "prepared_pending_terminal_execution",
                    "attempt_manifest_path": (attempt_dir / "attempt_manifest.yaml").as_posix(),
                    "tester_config_path": (attempt_dir / "tester_config.ini").as_posix(),
                    "source_score_telemetry_common_path": source_attempt["telemetry_common_path"],
                    "execution_telemetry_common_path": f"{COMMON_DECISION_ROOT}\\{attempt_id}\\execution_telemetry.csv",
                    "trade_shape_telemetry_common_path": f"{COMMON_DECISION_ROOT}\\{attempt_id}\\trade_shape_telemetry.csv",
                    "decision_family": decision_family,
                    "decision_execution_kind": execution_kind,
                    "decision_output": "score_ge_high_long_score_le_low_short_else_flat",
                    "score_low_threshold": low,
                    "score_high_threshold": high,
                    "runtime_period_set_id": source_attempt["runtime_period_set_id"],
                    "tester_execution_profile_id": source_attempt["tester_execution_profile_id"],
                    "claim_boundary": CLAIM_BOUNDARY,
                }
                attempt_rows.append(row)
                configs[attempt_id] = build_tester_config_text(
                    attempt_id=attempt_id,
                    source_score_telemetry_common_path=row["source_score_telemetry_common_path"],
                    period=row,
                    execution_profile=execution_profile,
                    decision_family=row["decision_family"],
                    direction_policy=row["direction_policy"],
                    score_low_threshold=low,
                    score_high_threshold=high,
                    hold_bars=hold_bars,
                )
                manifests[attempt_id] = build_attempt_manifest(
                    row=row,
                    source_attempt=source_attempt,
                    bundle=bundle,
                    created_at_utc=created_at_utc,
                )
                prepared_for_cell += 1

        eligibility_rows.append(
            {
                "cell_id": pair["cell_id"],
                "run_id": pair["run_id"],
                "bundle_id": pair["bundle_id"],
                "decision_family": decision_family,
                "decision_execution_kind": execution_kind,
                "proxy_judgment": pair["proxy_judgment"],
                "source_l5_routing_status": route["source_l5_routing_status"],
                "routing_decision": route["routing_decision"],
                "direct_trade_adapter_eligible": str(eligible).lower(),
                "eligibility_reason": eligibility_reason,
                "prepared_attempt_count": prepared_for_cell,
                "claim_boundary": CLAIM_BOUNDARY,
                "next_action": "execute_prepared_decision_replay_attempts"
                if prepared_for_cell
                else "preserve_clue_until_new_decision_surface_is_declared",
            }
        )

    counts = {
        "routing_cell_count": len(routing_rows),
        "direct_trade_adapter_eligible_cell_count": sum(row["direct_trade_adapter_eligible"] == "true" for row in eligibility_rows),
        "not_direct_trade_adapter_eligible_cell_count": sum(row["direct_trade_adapter_eligible"] == "false" for row in eligibility_rows),
        "prepared_attempt_count": len(attempt_rows),
        "prepared_cell_count": len({row["cell_id"] for row in attempt_rows}),
        "candidate_count": 0,
        "l5_candidate_count": 0,
        "period_role_counts": dict(sorted(Counter(row["period_role"] for row in attempt_rows).items())),
        "decision_family_counts": dict(sorted(Counter(row["decision_family"] for row in attempt_rows).items())),
        "direction_policy_counts": dict(sorted(Counter(row["direction_policy"] for row in attempt_rows).items())),
        "hold_bars_source_counts": dict(sorted(Counter(row["hold_bars_source"] for row in attempt_rows).items())),
        "eligibility_reason_counts": dict(sorted(Counter(row["eligibility_reason"] for row in eligibility_rows).items())),
    }
    summary = {
        "version": "wave02_cost_risk_holding_l4_decision_replay_adapter_preparation_summary_v1",
        "summary_id": "wave02_cost_risk_holding_l4_decision_replay_adapter_preparation_v0",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": "work_wave02_cost_risk_holding_l5_routing_decision_v0",
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
            "artifact_id": "artifact_wave02_cost_risk_holding_decision_replay_adapter_prep_summary_v0",
            "bundle_id": None,
            "candidate_id": None,
        },
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": created_at_utc,
        "status": STATUS,
        "execution_weight": "bounded_all_crh_adapter_routed_pairs",
        "adapter_id": ADAPTER_ID,
        "claim_boundary": CLAIM_BOUNDARY,
        "primary_family": "runtime_probe",
        "primary_skill": "spacesonar-runtime-evidence",
        "support_skills": ["spacesonar-evidence-provenance", "spacesonar-result-judgment"],
        "validation_depth": "writer_scope_smoke",
        "skipped_broad_validations": ["pytest", "full_regression_workflow", "evidence_graph_full_workflow"],
        "counts": counts,
        "source_records": {
            "routing_decision_summary": ROUTING_SUMMARY.as_posix(),
            "routing_decision_index": ROUTING_INDEX.as_posix(),
            "pair_judgment_index": PAIR_INDEX.as_posix(),
            "score_attempt_preparation_index": SOURCE_PREP_INDEX.as_posix(),
            "execution_profile": EXECUTION_PROFILE.as_posix(),
            "runtime_contract": RUNTIME_CONTRACT.as_posix(),
            "period_profile": PERIOD_PROFILE.as_posix(),
        },
        "artifact_paths": {
            "summary": SUMMARY_PATH.as_posix(),
            "attempt_index": INDEX_PATH.as_posix(),
            "eligibility_index": ELIGIBILITY_INDEX_PATH.as_posix(),
            "compile_summary": COMPILE_SUMMARY_PATH.as_posix(),
            "closeout": CLOSEOUT_PATH.as_posix(),
            "ea_source": EA_SOURCE.as_posix(),
        },
        "experiment_design": {
            "idea_id": IDEA_ID,
            "hypothesis_id": HYPOTHESIS_ID,
            "surface_id": SURFACE_ID,
            "sweep_id": SWEEP_ID,
            "hypothesis": "CRH preserved score clues may only matter if score bands can be translated into sparse tester trades.",
            "decision_use": "score_band_side_high_long_low_short_sparse_replay",
            "comparison_baseline": "Wave02 CRH non-trading score-probe pair observations",
            "control_variables": [
                "FPMarkets US100 M5",
                "split_set_v0 validation and research_oos periods",
                "fixed_lot 0.02 tester profile",
                "locked_final_oos_b excluded",
            ],
            "changed_variables": ["decision_execution_adapter", "score_band_side_policy", "sparse_order_replay"],
            "kpi_interpretation_plan": "tester report/trade-shape metrics only after terminal execution; no economics pass",
            "attribution_axes": ["cell_id", "period_role", "direction_policy", "hold_bars", "score_threshold"],
            "expected_effect_probe": "CRH score bands should produce interpretable sparse order streams before any candidate-specific evidence is opened",
            "surface_rotation_rationale": "score probes are insufficient; sparse decision replay is the smallest runtime follow-through",
            "search_shape": "runtime follow-through",
            "next_surface_options": ["execute_prepared_decision_replay", "rotate_if_decision_replay_negative"],
            "axis_balance_check": "runtime_follow_through_not_single_axis_repair",
            "sample_scope": "validation_and_research_oos_only_locked_final_excluded",
            "success_criteria": ["paired terminal execution produces interpretable reports without protected claim"],
            "failure_criteria": ["loss_or_runtime_friction_in_both_period_roles", "missing_terminal_report_after_repair_attempt"],
            "invalid_conditions": ["locked_final_oos_b_used", "candidate_claim_without_L5_manifest"],
            "stop_conditions": ["negative paired decision replay judgment"],
            "reopen_or_stop_condition": "rerun preparation only if routing decision, pair judgment, or source score attempts change",
            "evidence_plan": [SUMMARY_PATH.as_posix(), INDEX_PATH.as_posix(), ELIGIBILITY_INDEX_PATH.as_posix()],
            "claim_boundary": CLAIM_BOUNDARY,
            "legacy_relation": "uses generic score replay adapter with CRH family support, not legacy winner or promotion inheritance",
            "axis_tags": ["decision_surface", "risk_or_sizing_surface", "horizon_or_holding_policy", "evaluation_or_runtime_surface"],
        },
        "judgment": {
            "result_subject": "Wave02 CRH sparse score-band decision replay adapter preparation",
            "judgment_label": "runtime_probe",
            "metric_identity": "no performance metric; adapter/config preparation only",
            "comparison_baseline": "Wave02 CRH paired L4 score telemetry preserved clues",
            "tested_factor": "CRH score thresholds translated through score-band sparse order policy",
            "kpi_interpretation": "not evaluated until MT5 decision replay execution",
            "directional_effect_hypothesis": "score-high/score-low CRH bars may become testable sparse orders",
            "attribution_confidence": "design_preparation_only",
            "claim_boundary": CLAIM_BOUNDARY,
            "missing_evidence": [
                "decision_replay_terminal_execution_not_run",
                "tester_reports_missing_until_execution",
                "economics_metrics_missing_until_tester_report",
                "candidate_specific_L5_manifest_not_opened",
            ],
            "next_action": NEXT_ACTION,
        },
        "environment": {
            "command_argv": ["python", "foundation/pipelines/prepare_wave02_cost_risk_holding_l4_decision_replay_attempts.py"],
            "cwd": ".",
            "python_executable": redact_path(sys.executable),
            "python_version": platform.python_version(),
            "dependency_summary": {"python": platform.python_version(), "yaml": yaml.__version__},
            **git_state(),
        },
        "forbidden_claims": FORBIDDEN_CLAIMS,
    }
    return summary, attempt_rows, eligibility_rows, manifests, configs


def build_compile_summary(created_at_utc: str) -> dict[str, Any]:
    return {
        "version": "wave02_cost_risk_holding_decision_replay_adapter_compile_summary_v1",
        "summary_path": COMPILE_SUMMARY_PATH.as_posix(),
        "created_at_utc": created_at_utc,
        "status": "ea_binary_available" if path_exists(REPO_ROOT / EA_BINARY) else "ea_binary_missing_compile_required",
        "compile_attempted": False,
        "ea_source": artifact_ref(EA_SOURCE),
        "ea_binary": artifact_ref(EA_BINARY, availability="local_binary_hash_recorded_ignored_by_git")
        if path_exists(REPO_ROOT / EA_BINARY)
        else {"path": EA_BINARY.as_posix(), "availability": "missing"},
        "claim_boundary": "ea_binary_preflight_only_not_strategy_tester_output",
    }


def build_closeout(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "work_closeout_v1",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": "work_wave02_cost_risk_holding_l5_routing_decision_v0",
        "next_work_item_id": NEXT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": summary["created_at_utc"],
        "result_judgment": "runtime_probe",
        "status": summary["status"],
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [SUMMARY_PATH.as_posix(), INDEX_PATH.as_posix(), ELIGIBILITY_INDEX_PATH.as_posix(), COMPILE_SUMMARY_PATH.as_posix()],
        "counts": summary["counts"],
        "missing_evidence": summary["judgment"]["missing_evidence"],
        "next_action": summary["judgment"]["next_action"],
        "forbidden_claims": summary["forbidden_claims"],
    }


def write_records(
    summary: dict[str, Any],
    attempt_rows: list[dict[str, Any]],
    eligibility_rows: list[dict[str, Any]],
    manifests: dict[str, dict[str, Any]],
    configs: dict[str, str],
) -> None:
    for row in attempt_rows:
        attempt_dir = REPO_ROOT / "runtime" / "mt5_attempts" / row["attempt_id"]
        attempt_dir.mkdir(parents=True, exist_ok=True)
        tester_config_path = Path(row["tester_config_path"])
        write_text(tester_config_path, configs[row["attempt_id"]])
        manifests[row["attempt_id"]]["artifact_identity"]["tester_config"] = artifact_ref(tester_config_path)
        write_yaml(Path(row["attempt_manifest_path"]), manifests[row["attempt_id"]])
    write_csv(INDEX_PATH, attempt_rows, attempt_index_fieldnames())
    write_csv(ELIGIBILITY_INDEX_PATH, eligibility_rows, eligibility_fieldnames())
    write_yaml(SUMMARY_PATH, summary)
    write_yaml(COMPILE_SUMMARY_PATH, build_compile_summary(summary["created_at_utc"]))
    write_yaml(CLOSEOUT_PATH, build_closeout(summary))
    upsert_artifact_registry(summary, attempt_rows)


def upsert_artifact_registry(summary: dict[str, Any], attempt_rows: list[dict[str, Any]]) -> None:
    registry_path = REPO_ROOT / ARTIFACT_REGISTRY
    existing = read_csv_rows(registry_path) if path_exists(registry_path) else []
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
        full = REPO_ROOT / row["path_or_uri"]
        if path_exists(full):
            row["sha256"] = sha256_file(full)
            row["size_bytes"] = str(os.stat(filesystem_path(full)).st_size)
        by_id[row["artifact_id"]] = {key: str(row.get(key, "")) for key in fieldnames}

    for artifact_id, artifact_type, path, notes in [
        ("artifact_wave02_cost_risk_holding_decision_replay_adapter_prep_summary_v0", "decision_replay_adapter_summary", SUMMARY_PATH, "summary for Wave02 CRH decision replay adapter preparation"),
        ("artifact_wave02_cost_risk_holding_decision_replay_adapter_prep_index_v0", "decision_replay_adapter_index", INDEX_PATH, "index of prepared Wave02 CRH decision replay attempts"),
        ("artifact_wave02_cost_risk_holding_decision_replay_adapter_eligibility_index_v0", "decision_replay_adapter_eligibility_index", ELIGIBILITY_INDEX_PATH, "eligibility index for Wave02 CRH decision replay"),
        ("artifact_wave02_cost_risk_holding_decision_replay_adapter_compile_summary_v0", "ea_compile_summary", COMPILE_SUMMARY_PATH, "EA binary/source preflight for CRH decision replay adapter"),
        ("artifact_wave02_cost_risk_holding_decision_replay_adapter_prep_closeout_v0", "work_closeout", CLOSEOUT_PATH, "closeout for Wave02 CRH decision replay adapter preparation"),
    ]:
        put(
            {
                "artifact_id": artifact_id,
                "artifact_type": artifact_type,
                "path_or_uri": path.as_posix(),
                "availability": "present_hash_recorded",
                "producer_command": producer,
                "regeneration_command": producer,
                "source_of_truth": SUMMARY_PATH.as_posix(),
                "consumer": NEXT_WORK_ITEM_ID,
                "claim_boundary": summary["claim_boundary"],
                "notes": notes,
            }
        )
    for row in attempt_rows:
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
                    "consumer": NEXT_WORK_ITEM_ID,
                    "claim_boundary": summary["claim_boundary"],
                    "notes": "Wave02 CRH decision replay adapter preparation; not candidate, runtime authority, or economics pass",
                }
            )
    write_csv(ARTIFACT_REGISTRY, list(by_id.values()), fieldnames)


def update_control_records(summary: dict[str, Any]) -> None:
    state = git_state()
    output_hashes = [artifact_ref(path) for path in [SUMMARY_PATH, INDEX_PATH, ELIGIBILITY_INDEX_PATH, COMPILE_SUMMARY_PATH, CLOSEOUT_PATH]]
    input_hashes = [artifact_ref(path) for path in [ROUTING_SUMMARY, ROUTING_INDEX, PAIR_INDEX, SOURCE_PREP_INDEX, EXECUTION_PROFILE, RUNTIME_CONTRACT, PERIOD_PROFILE]]
    next_work = {
        "version": "work_item_lite_v1",
        "work_item_id": NEXT_WORK_ITEM_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "primary_family": "runtime_probe",
        "primary_skill": "spacesonar-runtime-evidence",
        "verification_profile": "runtime_preflight_terminal_execution",
        "targets": [INDEX_PATH.as_posix(), SUMMARY_PATH.as_posix()],
        "acceptance_criteria": [
            "execute prepared Wave02 CRH decision replay validation/research_oos MT5 attempts",
            "record execution telemetry, tester report receipts, and runtime completion before any pair judgment",
            "keep candidate_count and l5_candidate_count at zero until candidate-specific L5 manifest exists",
        ],
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "policy_binding": {
            "revision": "policy_contract_v2",
            "guards": [
                "GUARD_001_ATTEMPT_BEFORE_DISPOSITION",
                "GUARD_002_RUNTIME_COMPLETION_TRUTH",
                "GUARD_003_CLAIM_BOUNDARY",
                "GUARD_004_ARTIFACT_IDENTITY",
                "GUARD_007_OPERATIONAL_STABILITY",
            ],
        },
        "outputs": [
            "runtime/mt5_attempts/<attempt_id>/attempt_manifest.yaml",
            "runtime/mt5_attempts/<attempt_id>/telemetry/execution_telemetry.csv",
            "runtime/mt5_attempts/<attempt_id>/reports/tester_report.htm",
        ],
        "next_action": NEXT_ACTION,
        "path": NEXT_WORK_ITEM.as_posix(),
        "summary": "Execute prepared Wave02 CRH sparse decision replay attempts.",
        "provenance": {
            "source": WORK_ITEM_ID,
            "campaign_id": CAMPAIGN_ID,
            "source_of_truth": SUMMARY_PATH.as_posix(),
        },
        "current_truth": {
            "decision_replay_adapter_preparation_summary": SUMMARY_PATH.as_posix(),
            "decision_replay_adapter_preparation_index": INDEX_PATH.as_posix(),
            "decision_replay_adapter_eligibility_index": ELIGIBILITY_INDEX_PATH.as_posix(),
            "decision_replay_adapter_preparation_status": summary["status"],
            "decision_replay_adapter_preparation_counts": summary["counts"],
            "candidate_count": 0,
            "l5_candidate_count": 0,
        },
        "unresolved_blockers": ["Wave02_cost_risk_holding_decision_replay_terminal_execution_pending"],
        "reopen_conditions": [
            "rerun adapter preparation if Wave02 CRH routing decision, pair judgment, or source score attempt index changes",
            "do not open candidate-specific L5 materialization until decision replay pair judgment exists",
        ],
        "status": NEXT_STATUS,
        "missing_material_if_relevant": summary["judgment"]["missing_evidence"],
        "execution_provenance": {
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
            "unknown_git_claim_effect": "dirty_worktree_recorded_claim_lowered_no_candidate_runtime_authority_or_economics_pass",
        },
    }
    write_yaml(NEXT_WORK_ITEM, next_work)

    resume = read_yaml(REPO_ROOT / RESUME_CURSOR)
    resume["updated_at_utc"] = summary["created_at_utc"]
    resume["cursor_state"] = NEXT_STATUS
    resume["active_phase"] = NEXT_STATUS
    resume["active_work_item_id"] = NEXT_WORK_ITEM_ID
    resume["campaign_id"] = CAMPAIGN_ID
    resume["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    resume["next_action"] = NEXT_ACTION
    resume["unresolved_blockers"] = ["Wave02_cost_risk_holding_decision_replay_terminal_execution_pending"]
    sources = resume.setdefault("current_truth_sources", [])
    for source in [SUMMARY_PATH.as_posix(), INDEX_PATH.as_posix(), ELIGIBILITY_INDEX_PATH.as_posix(), COMPILE_SUMMARY_PATH.as_posix(), CLOSEOUT_PATH.as_posix()]:
        if source not in sources:
            sources.append(source)
    resume["latest_completed_work"] = {
        "work_item_id": WORK_ITEM_ID,
        "result_judgment": "runtime_probe",
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [SUMMARY_PATH.as_posix(), CLOSEOUT_PATH.as_posix()],
    }
    resume["next_work_item"] = {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()}
    write_yaml(RESUME_CURSOR, resume)

    goal = read_yaml(REPO_ROOT / GOAL_MANIFEST)
    goal["updated_at_utc"] = summary["created_at_utc"]
    goal["active_phase"] = NEXT_STATUS
    goal["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    goal["next_work_item"] = {
        "work_item_id": NEXT_WORK_ITEM_ID,
        "path": NEXT_WORK_ITEM.as_posix(),
        "summary": "Wave02 CRH decision replay terminal execution pending; no candidate claim.",
    }
    wave02 = goal.setdefault("wave02_cost_risk_holding_campaign", {})
    wave02["status"] = NEXT_STATUS
    wave02["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    wave02["next_work_item"] = NEXT_WORK_ITEM_ID
    wave02["candidate_count"] = 0
    wave02["l5_candidate_count"] = 0
    wave02["decision_replay_adapter_preparation_summary"] = SUMMARY_PATH.as_posix()
    wave02["decision_replay_adapter_preparation_index"] = INDEX_PATH.as_posix()
    wave02["decision_replay_adapter_eligibility_index"] = ELIGIBILITY_INDEX_PATH.as_posix()
    wave02["decision_replay_adapter_preparation_status"] = summary["status"]
    wave02["decision_replay_adapter_preparation_counts"] = summary["counts"]
    write_yaml(GOAL_MANIFEST, goal)

    campaign = read_yaml(REPO_ROOT / CAMPAIGN_MANIFEST)
    campaign["updated_at_utc"] = summary["created_at_utc"]
    campaign["status"] = NEXT_STATUS
    campaign["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    campaign["candidate_count"] = 0
    campaign["l5_candidate_count"] = 0
    campaign["next_action"] = NEXT_ACTION
    l4 = campaign.setdefault("l4_follow_through", {})
    replay = l4.setdefault("decision_replay", {})
    replay["adapter_preparation_summary"] = SUMMARY_PATH.as_posix()
    replay["adapter_preparation_index"] = INDEX_PATH.as_posix()
    replay["adapter_eligibility_index"] = ELIGIBILITY_INDEX_PATH.as_posix()
    replay["adapter_preparation_status"] = summary["status"]
    replay["adapter_preparation_counts"] = summary["counts"]
    campaign["missing_evidence"] = summary["judgment"]["missing_evidence"]
    write_yaml(CAMPAIGN_MANIFEST, campaign)

    workspace = read_yaml(REPO_ROOT / WORKSPACE_STATE)
    workspace["updated_utc"] = summary["created_at_utc"]
    workspace.setdefault("active_campaign", {})["status"] = NEXT_STATUS
    workspace["current_claim_boundary"] = NEXT_CLAIM_BOUNDARY
    workspace["next_action"] = NEXT_ACTION
    workspace["unresolved_blockers"] = ["Wave02_cost_risk_holding_decision_replay_terminal_execution_pending"]
    workspace["active_work_item"] = {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()}
    counts = workspace.setdefault("summary_counts", {})
    counts["candidate_count"] = 0
    counts["l5_candidate_count"] = 0
    counts["wave02_cost_risk_holding_decision_replay_adapter_preparation"] = summary["counts"]
    crh = workspace.setdefault("wave02_cost_risk_holding_l4_materialization", {})
    crh["status"] = NEXT_STATUS
    crh["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    crh["decision_replay_adapter_preparation_summary"] = SUMMARY_PATH.as_posix()
    crh["decision_replay_adapter_preparation_index"] = INDEX_PATH.as_posix()
    crh["decision_replay_adapter_eligibility_index"] = ELIGIBILITY_INDEX_PATH.as_posix()
    crh["decision_replay_adapter_preparation_status"] = summary["status"]
    crh["decision_replay_adapter_preparation_counts"] = summary["counts"]
    crh["candidate_count"] = 0
    crh["l5_candidate_count"] = 0
    write_yaml(WORKSPACE_STATE, workspace)

    if path_exists(REPO_ROOT / GOAL_REGISTRY):
        goal_rows = read_csv_rows(REPO_ROOT / GOAL_REGISTRY)
        for row in goal_rows:
            if row.get("goal_id") == GOAL_ID:
                if "active_phase" in row:
                    row["active_phase"] = NEXT_STATUS
                if "next_work_item" in row:
                    row["next_work_item"] = NEXT_WORK_ITEM_ID
                if "claim_boundary" in row:
                    row["claim_boundary"] = NEXT_CLAIM_BOUNDARY
        if goal_rows:
            write_csv(GOAL_REGISTRY, goal_rows, list(goal_rows[0].keys()))


def smoke_outputs(summary: dict[str, Any], attempt_rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for path in [SUMMARY_PATH, INDEX_PATH, ELIGIBILITY_INDEX_PATH, COMPILE_SUMMARY_PATH, CLOSEOUT_PATH]:
        if not path_exists(REPO_ROOT / path):
            errors.append(f"missing output path: {path.as_posix()}")
    loaded_summary = read_yaml(REPO_ROOT / SUMMARY_PATH) if path_exists(REPO_ROOT / SUMMARY_PATH) else {}
    index_rows = read_csv_rows(REPO_ROOT / INDEX_PATH) if path_exists(REPO_ROOT / INDEX_PATH) else []
    eligibility_rows = read_csv_rows(REPO_ROOT / ELIGIBILITY_INDEX_PATH) if path_exists(REPO_ROOT / ELIGIBILITY_INDEX_PATH) else []
    if loaded_summary.get("claim_boundary") != CLAIM_BOUNDARY:
        errors.append("summary claim_boundary mismatch")
    if loaded_summary.get("validation_depth") != "writer_scope_smoke":
        errors.append("summary validation_depth mismatch")
    counts = loaded_summary.get("counts") or {}
    if counts.get("prepared_attempt_count") != len(index_rows):
        errors.append("prepared_attempt_count mismatch")
    if counts.get("prepared_attempt_count") != 12:
        errors.append("expected 12 prepared attempts")
    if counts.get("candidate_count") != 0 or counts.get("l5_candidate_count") != 0:
        errors.append("candidate counts must stay zero")
    if len(eligibility_rows) != counts.get("routing_cell_count"):
        errors.append("eligibility row count mismatch")
    for row in index_rows:
        for key in ["attempt_manifest_path", "tester_config_path", "source_score_telemetry_common_path"]:
            if not row.get(key):
                errors.append(f"{row.get('attempt_id')}: missing {key}")
        for path_key in ["attempt_manifest_path", "tester_config_path"]:
            if not path_exists(REPO_ROOT / row[path_key]):
                errors.append(f"{row.get('attempt_id')}: missing {path_key}")

    registry_rows = read_csv_rows(REPO_ROOT / ARTIFACT_REGISTRY)
    by_id = {row.get("artifact_id"): row for row in registry_rows}
    for artifact_id, path in [
        ("artifact_wave02_cost_risk_holding_decision_replay_adapter_prep_summary_v0", SUMMARY_PATH),
        ("artifact_wave02_cost_risk_holding_decision_replay_adapter_prep_index_v0", INDEX_PATH),
        ("artifact_wave02_cost_risk_holding_decision_replay_adapter_eligibility_index_v0", ELIGIBILITY_INDEX_PATH),
        ("artifact_wave02_cost_risk_holding_decision_replay_adapter_compile_summary_v0", COMPILE_SUMMARY_PATH),
        ("artifact_wave02_cost_risk_holding_decision_replay_adapter_prep_closeout_v0", CLOSEOUT_PATH),
    ]:
        row = by_id.get(artifact_id)
        if not row:
            errors.append(f"artifact registry missing {artifact_id}")
            continue
        full = REPO_ROOT / path
        if row.get("sha256") != sha256_file(full):
            errors.append(f"{artifact_id}: sha256 mismatch")
    for attempt_row in index_rows:
        for suffix, path_key in [("manifest", "attempt_manifest_path"), ("tester_config", "tester_config_path")]:
            artifact_id = f"artifact_{attempt_row['attempt_id']}_{suffix}_v0"
            registry_row = by_id.get(artifact_id)
            if not registry_row:
                errors.append(f"artifact registry missing {artifact_id}")
                continue
            full = REPO_ROOT / attempt_row[path_key]
            if registry_row.get("sha256") != sha256_file(full):
                errors.append(f"{artifact_id}: sha256 mismatch")
    next_work = read_yaml(REPO_ROOT / NEXT_WORK_ITEM)
    if next_work.get("work_item_id") != NEXT_WORK_ITEM_ID:
        errors.append("next_work_item id mismatch")
    if next_work.get("current_truth", {}).get("decision_replay_adapter_preparation_summary") != SUMMARY_PATH.as_posix():
        errors.append("next_work_item missing preparation summary")
    return errors


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare Wave02 CRH score replay decision MT5 attempts.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--direction-policy", default="score_band_side", choices=SUPPORTED_DIRECTION_POLICIES)
    parser.add_argument("--write-records", action="store_true")
    parser.add_argument("--smoke-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    global REPO_ROOT
    REPO_ROOT = Path(args.repo_root).resolve()
    if args.smoke_only:
        summary = read_yaml(REPO_ROOT / SUMMARY_PATH)
        attempt_rows = read_csv_rows(REPO_ROOT / INDEX_PATH)
        errors = smoke_outputs(summary, attempt_rows)
    else:
        created_at_utc = utc_now()
        summary, attempt_rows, eligibility_rows, manifests, configs = build_records(created_at_utc, args.direction_policy)
        if args.write_records:
            write_records(summary, attempt_rows, eligibility_rows, manifests, configs)
            update_control_records(summary)
            errors = smoke_outputs(summary, attempt_rows)
        else:
            errors = []
            print(dump_yaml({"summary": summary, "attempt_rows": attempt_rows, "eligibility_rows": eligibility_rows}))
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    if args.write_records or args.smoke_only:
        print(
            "wave02 CRH decision replay adapter writer-smoke passed: "
            f"attempts={len(attempt_rows)} claim_boundary={CLAIM_BOUNDARY}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
