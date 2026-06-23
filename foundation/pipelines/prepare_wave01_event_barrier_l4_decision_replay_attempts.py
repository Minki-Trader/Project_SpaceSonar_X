from __future__ import annotations

import argparse
import json
import platform
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import foundation.pipelines.prepare_wave0_l4_decision_replay_attempts as base
from foundation.mt5.score_replay_decision_adapter import (
    ADAPTER_ID,
    CLAIM_BOUNDARY,
    attempt_id_for,
    decision_family_execution_kind,
    hold_bars_from_horizon,
    is_direct_trade_adapter_eligible,
)
from foundation.pipelines.run_mt5_fixed_fixture_probe import parse_compile_log

GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WORK_ITEM_ID = "work_wave01_event_barrier_l4_materialization_preflight_v0"
SUBWORK_ID = "work_wave01_event_barrier_l4_decision_replay_adapter_preparation_v0"
CAMPAIGN_ID = "campaign_us100_event_barrier_decision_surface_v0"
SWEEP_ID = "sweep_us100_event_barrier_broad_v0"
SUMMARY_ID = "wave01_event_barrier_l4_decision_replay_adapter_preparation_v0"
OUTPUT_DIR = Path("lab/campaigns/campaign_us100_event_barrier_decision_surface_v0/l4_follow_through/decision_replay")
SUMMARY_PATH = OUTPUT_DIR / "adapter_prep_summary.yaml"
INDEX_PATH = OUTPUT_DIR / "adapter_prep_index.csv"
ELIGIBILITY_INDEX_PATH = OUTPUT_DIR / "adapter_eligibility_index.csv"
COMPILE_SUMMARY_PATH = OUTPUT_DIR / "adapter_compile_summary.yaml"
COMPILE_LOG_PATH = OUTPUT_DIR / "adapter_compile.log"
CLOSEOUT_PATH = Path(
    "lab/goals/goal_us100_onnx_forward_boundary_v0/"
    "work_wave01_event_barrier_l4_decision_replay_adapter_preparation_v0_closeout.yaml"
)
PAIR_INDEX = Path("lab/campaigns/campaign_us100_event_barrier_decision_surface_v0/l4_follow_through/l4_pair_judgment_index.csv")
PREP_INDEX = Path("lab/campaigns/campaign_us100_event_barrier_decision_surface_v0/l4_follow_through/l4_attempt_preparation_index.csv")
EXECUTION_PROFILE = Path("configs/mt5/tester_execution_profile_v0.yaml")
RUNTIME_CONTRACT = Path("foundation/config/mt5_runtime_probe_contract.yaml")
PERIOD_PROFILE = Path("configs/mt5/period_profiles/split_set_v0_runtime_periods.yaml")
NEXT_WORK_ITEM = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml")
RESUME_CURSOR = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml")
GOAL_MANIFEST = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml")
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")
GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")
EA_SOURCE = Path("foundation/mt5/experts/SpaceSonar_L4_ScoreReplayDecisionProbe.mq5")
EA_BINARY = Path("foundation/mt5/experts/SpaceSonar_L4_ScoreReplayDecisionProbe.ex5")
EA_EXPERT_CONFIG_PATH = "Project_SpaceSonar_X\\foundation\\mt5\\experts\\SpaceSonar_L4_ScoreReplayDecisionProbe.ex5"
COMMON_DECISION_ROOT = "SpaceSonar\\wave01_event_barrier_l4_decision_replay"
DIRECTION_POLICY = "score_band_side"
NEXT_PHASE = "wave01_event_barrier_l4_decision_replay_adapter_prepared_terminal_execution_next"


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.dump(payload, handle, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=False)


def bundle_path(bundle_id: str) -> Path:
    return Path("runtime/packages") / bundle_id / "experiment_bundle.json"


def load_bundle(repo_root: Path, bundle_id: str) -> dict[str, Any]:
    return base.load_json(repo_root / bundle_path(bundle_id))


def eligibility_reason(pair: dict[str, str], bundle: dict[str, Any] | None) -> tuple[bool, str, str]:
    decision_family = pair.get("decision_family", "")
    if pair.get("proxy_judgment") != "preserved_clue":
        return False, "not_preserved_clue", decision_family_execution_kind(decision_family)
    kind = decision_family_execution_kind(decision_family)
    if not is_direct_trade_adapter_eligible(decision_family):
        return False, "requires_new_decision_surface_not_direct_trade_adapter", kind
    decision_surface = (bundle or {}).get("decision_surface") or {}
    if decision_surface.get("score_low_threshold") is None or decision_surface.get("score_high_threshold") is None:
        return False, "missing_score_band_thresholds", kind
    return True, "eligible_score_band_directional_adapter", kind


def build_tester_config_text(
    *,
    attempt_id: str,
    source_score_telemetry_common_path: str,
    period: dict[str, str],
    execution_profile: dict[str, Any],
    decision_family: str,
    score_low_threshold: float,
    score_high_threshold: float,
    hold_bars: int,
) -> str:
    tester_defaults = execution_profile["tester_defaults"]
    sizing = execution_profile["position_sizing_boundary"]
    report_name = f"Project_SpaceSonar_X\\runtime\\mt5_attempts\\{attempt_id}\\tester_report"
    execution_telemetry = f"{COMMON_DECISION_ROOT}\\{attempt_id}\\execution_telemetry.csv"
    lines = [
        "; SpaceSonar Wave01 L4 score-band decision replay probe.",
        "; Replays MT5 score telemetry into sparse tester trades; not ONNX runtime authority.",
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
        "InpUseCommonFiles=true",
        f"InpDecisionFamily={decision_family}",
        f"InpDirectionPolicy={DIRECTION_POLICY}",
        f"InpScoreHigh={score_high_threshold}",
        f"InpScoreLow={score_low_threshold}",
        f"InpFixedLot={sizing['default_lot']}",
        f"InpHoldBars={hold_bars}",
        "InpCloseOnFlat=true",
        "InpMaxSpreadPoints=0",
        "InpDeviationPoints=20",
        "InpMagicNumber=260622",
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
        "from_date",
        "to_date",
        "status",
        "attempt_manifest_path",
        "tester_config_path",
        "source_score_telemetry_common_path",
        "execution_telemetry_common_path",
        "decision_family",
        "decision_execution_kind",
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
        "l5_routing_status",
        "direct_trade_adapter_eligible",
        "eligibility_reason",
        "prepared_attempt_count",
        "claim_boundary",
        "next_action",
    ]


def build_attempt_manifest(
    *,
    repo_root: Path,
    row: dict[str, Any],
    source_attempt: dict[str, str],
    created_at_utc: str,
) -> dict[str, Any]:
    ea_binary_available = (repo_root / EA_BINARY).exists()
    return {
        "version": "mt5_attempt_manifest_v1",
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
        "subwork_item_id": SUBWORK_ID,
        "runtime_learning_probe_decision": {
            "required": True,
            "decision": "run_required",
            "required_runtime_level": "score_band_decision_replay_probe_before_L5",
            "reason": "Wave01 preserved clue has a declared directional score-band decision surface; score telemetry must be replayed into MT5 sparse orders before any L5 candidate claim.",
            "lowered_claim_if_not_run": "decision_replay_adapter_preparation_only_no_runtime_authority_no_economics_pass",
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
            "sizing_policy": {"fixed_lot": 0.02, "source": "configs/mt5/tester_execution_profile_v0.yaml"},
            "score_replay_not_onnx_execution": True,
        },
        "runtime_surface_contract": {
            "completion_surface_scope": "full_period_sparse_decision_surface",
            "surface_scope": "full_period_sparse_decision_surface_from_mt5_score_telemetry",
            "source_score_telemetry_common_path": row["source_score_telemetry_common_path"],
            "source_score_attempt_manifest": source_attempt["attempt_manifest_path"],
            "decision_family": row["decision_family"],
            "decision_execution_kind": row["decision_execution_kind"],
            "direction_policy": row["direction_policy"],
            "score_low_threshold": float(row["score_low_threshold"]),
            "score_high_threshold": float(row["score_high_threshold"]),
            "hold_bars": int(row["hold_bars"]),
            "decision_output": "score_ge_high_long_score_le_low_short_otherwise_flat",
            "forbidden_interpretation": "not_ONNX_runtime_authority_not_economics_pass_until_terminal_report_and_judgment_exist",
        },
        "proxy_runtime_parity": {
            "status": "adapter_prepared_terminal_execution_pending",
            "shared_contract": [
                "US100_M5_closed_bar_base_frame",
                "period_profile_split_set_v0",
                "us100_m5_fpmarkets_tester_execution_v0",
                "source_MT5_score_telemetry_full_period",
                "score_band_thresholds_from_experiment_bundle",
            ],
            "known_differences": [
                "This adapter replays previously observed MT5 score telemetry and does not run ONNX in the trading EA.",
                "Proxy score-band decision used gross future return; MT5 replay creates sparse orders with tester fills and spread.",
            ],
            "interpretation_drift_risks": [
                "bar_close_time_lookup_alignment",
                "score_low_high_threshold_translation",
                "hold_bars_exit_semantics",
                "tester_fill_cost_spread_lot_rounding",
            ],
            "minimum_reconciliation_attempt": {
                "status": "prepared",
                "attempt": "score telemetry bar_close_time will be replayed into score-band sparse orders in MT5 terminal",
                "forced_equality_required": False,
            },
            "unit_semantics": {
                "score": "single_float_score_from_prior_MT5_score_probe",
                "high_threshold": float(row["score_high_threshold"]),
                "low_threshold": float(row["score_low_threshold"]),
                "side_mapping": "score_ge_high_long_score_le_low_short",
                "lot": "fixed_lot_0.02",
                "hold": f"{row['hold_bars']}_M5_closed_bars",
                "point_tick_digits": "to_be_recorded_from_tester_report",
            },
            "comparison_class": "pending_terminal_execution",
            "divergence_judgment": "pending_terminal_execution",
            "prevention_memory": [
                "Do not treat score telemetry as economics evidence.",
                "Do not convert diagnostic/no-trade clues into trades without a newly declared decision surface.",
                "If score replay behavior differs from proxy score-band expectation, record threshold and bar-close semantics before judging the surface.",
            ],
            "follow_up_action": "execute prepared Wave01 score-band decision replay attempts before any L5/economics claim",
            "claim_boundary": "proxy_runtime_parity_tracking_only_no_runtime_authority",
        },
        "artifact_identity": {
            "ea_entrypoint": base.artifact_ref(repo_root / EA_SOURCE, repo_root),
            "ea_binary": base.artifact_ref(repo_root / EA_BINARY, repo_root, availability="local_binary_hash_recorded_ignored_by_git")
            if ea_binary_available
            else {"path": EA_BINARY.as_posix(), "availability": "compile_pending_not_committed"},
            "bundle": base.artifact_ref(repo_root / bundle_path(row["bundle_id"]), repo_root),
            "source_score_attempt": {"path": source_attempt["attempt_manifest_path"], "availability": "present_hash_recorded"},
            "tester_config": {"path": row["tester_config_path"], "availability": "pending_write"},
        },
        "required_gate_coverage": {
            "passed": [
                "source_score_telemetry_observed",
                "decision_replay_adapter_source_created",
                "tester_config_prepared",
                "locked_final_excluded",
            ],
            "missing": [
                "Strategy_Tester_terminal_execution",
                "tester_report_hash",
                "economics_metrics",
            ],
            "not_applicable": ["locked_final_oos_b_access"],
        },
        "missing_evidence": [
            "decision_replay_terminal_execution_not_run",
            "tester_report_missing_until_terminal_execution",
            "economics_metrics_missing_until_tester_report",
        ],
        "next_action": "execute Wave01 score-band decision replay attempts; keep L5/economics claims forbidden until reports and judgment exist",
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


def build_records(repo_root: Path, *, created_at_utc: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, str]]:
    pair_rows = [row for row in base.read_csv_rows(repo_root / PAIR_INDEX) if row.get("proxy_judgment") == "preserved_clue"]
    prep_by_attempt = {row["attempt_id"]: row for row in base.read_csv_rows(repo_root / PREP_INDEX)}
    execution_profile = base.load_yaml(repo_root / EXECUTION_PROFILE)

    eligibility_rows: list[dict[str, Any]] = []
    attempt_rows: list[dict[str, Any]] = []
    manifests: dict[str, dict[str, Any]] = {}
    configs: dict[str, str] = {}

    for pair in sorted(pair_rows, key=lambda item: item["cell_id"]):
        bundle = load_bundle(repo_root, pair["bundle_id"])
        eligible, reason, kind = eligibility_reason(pair, bundle)
        prepared_for_cell = 0
        if eligible:
            decision_surface = bundle["decision_surface"]
            low = float(decision_surface["score_low_threshold"])
            high = float(decision_surface["score_high_threshold"])
            hold_bars = hold_bars_from_horizon((bundle.get("target_and_label") or {}).get("horizon_bars"))
            for period_role, source_attempt_id in [
                ("validation", pair["validation_attempt_id"]),
                ("research_oos", pair["research_oos_attempt_id"]),
            ]:
                source_attempt = prep_by_attempt[source_attempt_id]
                attempt_id = attempt_id_for(pair["cell_id"], period_role, DIRECTION_POLICY)
                attempt_dir = Path("runtime/mt5_attempts") / attempt_id
                row: dict[str, Any] = {
                    "attempt_id": attempt_id,
                    "source_attempt_id": source_attempt_id,
                    "run_id": pair["run_id"],
                    "bundle_id": pair["bundle_id"],
                    "cell_id": pair["cell_id"],
                    "period_role": period_role,
                    "direction_policy": DIRECTION_POLICY,
                    "hold_bars": hold_bars,
                    "from_date": source_attempt["from_date"],
                    "to_date": source_attempt["to_date"],
                    "status": "prepared_pending_terminal_execution",
                    "attempt_manifest_path": (attempt_dir / "attempt_manifest.yaml").as_posix(),
                    "tester_config_path": (attempt_dir / "tester_config.ini").as_posix(),
                    "source_score_telemetry_common_path": source_attempt["telemetry_common_path"],
                    "execution_telemetry_common_path": f"{COMMON_DECISION_ROOT}\\{attempt_id}\\execution_telemetry.csv",
                    "decision_family": pair["decision_family"],
                    "decision_execution_kind": kind,
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
                    score_low_threshold=low,
                    score_high_threshold=high,
                    hold_bars=hold_bars,
                )
                manifests[attempt_id] = build_attempt_manifest(
                    repo_root=repo_root,
                    row=row,
                    source_attempt=source_attempt,
                    created_at_utc=created_at_utc,
                )
                prepared_for_cell += 1

        eligibility_rows.append(
            {
                "cell_id": pair["cell_id"],
                "run_id": pair["run_id"],
                "bundle_id": pair["bundle_id"],
                "decision_family": pair["decision_family"],
                "decision_execution_kind": kind,
                "proxy_judgment": pair["proxy_judgment"],
                "l5_routing_status": pair["l5_routing_status"],
                "direct_trade_adapter_eligible": str(eligible).lower(),
                "eligibility_reason": reason,
                "prepared_attempt_count": prepared_for_cell,
                "claim_boundary": CLAIM_BOUNDARY,
                "next_action": "execute_prepared_decision_replay_attempts" if eligible else "preserve_clue_until_new_decision_surface_is_declared",
            }
        )

    counts = {
        "preserved_clue_count": len(pair_rows),
        "direct_trade_adapter_eligible_cell_count": sum(row["direct_trade_adapter_eligible"] == "true" for row in eligibility_rows),
        "not_direct_trade_adapter_eligible_cell_count": sum(row["direct_trade_adapter_eligible"] == "false" for row in eligibility_rows),
        "prepared_attempt_count": len(attempt_rows),
        "period_role_counts": dict(sorted(Counter(row["period_role"] for row in attempt_rows).items())),
        "decision_family_counts": dict(sorted(Counter(row["decision_family"] for row in attempt_rows).items())),
        "eligibility_reason_counts": dict(sorted(Counter(row["eligibility_reason"] for row in eligibility_rows).items())),
    }
    summary = {
        "version": "wave01_event_barrier_l4_decision_replay_adapter_preparation_summary_v1",
        "summary_id": SUMMARY_ID,
        "work_item_id": WORK_ITEM_ID,
        "subwork_item_id": SUBWORK_ID,
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": created_at_utc,
        "status": "wave01_decision_replay_adapter_attempts_prepared_terminal_execution_next",
        "adapter_id": ADAPTER_ID,
        "claim_boundary": CLAIM_BOUNDARY,
        "counts": counts,
        "source_records": {
            "pair_judgment_index": PAIR_INDEX.as_posix(),
            "score_attempt_preparation_index": PREP_INDEX.as_posix(),
            "runtime_contract": RUNTIME_CONTRACT.as_posix(),
            "period_profile": PERIOD_PROFILE.as_posix(),
            "execution_profile": EXECUTION_PROFILE.as_posix(),
        },
        "artifact_paths": {
            "summary": SUMMARY_PATH.as_posix(),
            "attempt_index": INDEX_PATH.as_posix(),
            "eligibility_index": ELIGIBILITY_INDEX_PATH.as_posix(),
            "compile_summary": COMPILE_SUMMARY_PATH.as_posix(),
            "closeout": CLOSEOUT_PATH.as_posix(),
            "ea_source": EA_SOURCE.as_posix(),
        },
        "judgment": {
            "result_subject": "Wave01 preserved-clue score-band decision replay adapter preparation",
            "judgment_label": "runtime_probe",
            "metric_identity": "no performance metric; adapter/config preparation only",
            "comparison_baseline": "Wave01 paired L4 score telemetry preserved clues",
            "claim_boundary": CLAIM_BOUNDARY,
            "missing_evidence": [
                "decision_replay_terminal_execution_not_run",
                "tester_reports_missing_until_execution",
                "economics_metrics_missing_until_tester_report",
                "diagnostic_or_no_trade_preserved_clues_require_new_decision_surface_before_trade_replay",
            ],
            "next_action": "execute prepared Wave01 score-band decision replay attempts, then judge validation/research_oos pairs before any L5 claim",
        },
        "prevention_memory": [
            "Do not defer because a decision replay adapter is missing; build the smallest repo-controlled adapter first.",
            "Do not force diagnostic/no-trade preserved clues into orders without a newly declared decision surface.",
            "Score-band side mapping is score >= high -> long, score <= low -> short, otherwise flat.",
        ],
        "environment": {
            "command_argv": [
                "python",
                "foundation/pipelines/prepare_wave01_event_barrier_l4_decision_replay_attempts.py",
            ],
            "cwd": ".",
            "python_executable": base.redact_path(sys.executable),
            "python_version": platform.python_version(),
            "dependency_summary": {"python": platform.python_version(), "yaml": yaml.__version__},
            **base.git_state(repo_root),
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
    return summary, attempt_rows, eligibility_rows, manifests, configs


def build_compile_summary(repo_root: Path, created_at_utc: str) -> dict[str, Any]:
    binary_available = (repo_root / EA_BINARY).exists()
    compile_log = parse_compile_log(repo_root / COMPILE_LOG_PATH)
    log_exists = bool(compile_log.pop("exists", False))
    compile_log["exists_at_generation"] = log_exists
    compile_log["availability"] = "local_ignored_not_committed_contains_absolute_paths"
    errors = compile_log.get("compile_errors")
    warnings = compile_log.get("compile_warnings")
    if log_exists:
        compile_result = (
            "compile_success_derived_from_log_and_binary"
            if binary_available and errors == 0 and warnings == 0
            else "compile_log_observed_not_success"
        )
    else:
        compile_result = "compile_not_run_by_preparer"
    return {
        "version": "wave01_decision_replay_adapter_compile_summary_v1",
        "summary_id": "wave01_decision_replay_adapter_compile_summary_v0",
        "created_at_utc": created_at_utc,
        "status": "ea_binary_available" if binary_available else "ea_binary_missing",
        "claim_boundary": "ea_compile_evidence_only_not_strategy_tester_output",
        "ea_source": base.artifact_ref(repo_root / EA_SOURCE, repo_root),
        "ea_binary": base.artifact_ref(repo_root / EA_BINARY, repo_root, availability="local_binary_hash_recorded_ignored_by_git")
        if binary_available
        else {"path": EA_BINARY.as_posix(), "availability": "missing_local_binary"},
        "compile_log": compile_log,
        "raw_log_policy": "not_committed_because_MetaEditor_log_contains_local_absolute_paths",
        "compile_result": compile_result,
        "compile_success_derived_from_log_and_binary": bool(binary_available and errors == 0 and warnings == 0),
        "missing_evidence": [] if binary_available and errors == 0 and warnings == 0 else ["ea_compile_success_not_observed"],
    }


def build_closeout(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "work_closeout_v1",
        "work_item_id": SUBWORK_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": summary["created_at_utc"],
        "result_judgment": "runtime_probe",
        "status": summary["status"],
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [
            SUMMARY_PATH.as_posix(),
            INDEX_PATH.as_posix(),
            ELIGIBILITY_INDEX_PATH.as_posix(),
            COMPILE_SUMMARY_PATH.as_posix(),
        ],
        "counts": summary["counts"],
        "missing_evidence": summary["judgment"]["missing_evidence"],
        "next_action": summary["judgment"]["next_action"],
        "forbidden_claims": summary["forbidden_claims"],
    }


def write_records(
    repo_root: Path,
    summary: dict[str, Any],
    attempt_rows: list[dict[str, Any]],
    eligibility_rows: list[dict[str, Any]],
    manifests: dict[str, dict[str, Any]],
    configs: dict[str, str],
    *,
    write_control_records: bool,
) -> None:
    (repo_root / OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    for row in attempt_rows:
        attempt_dir = repo_root / "runtime" / "mt5_attempts" / row["attempt_id"]
        attempt_dir.mkdir(parents=True, exist_ok=True)
        tester_config_path = repo_root / row["tester_config_path"]
        tester_config_path.write_text(configs[row["attempt_id"]], encoding="utf-8")
        manifests[row["attempt_id"]]["artifact_identity"]["tester_config"] = base.artifact_ref(tester_config_path, repo_root)
        write_yaml(repo_root / row["attempt_manifest_path"], manifests[row["attempt_id"]])

    base.write_csv(repo_root / INDEX_PATH, attempt_rows, attempt_index_fieldnames())
    base.write_csv(repo_root / ELIGIBILITY_INDEX_PATH, eligibility_rows, eligibility_fieldnames())
    write_yaml(repo_root / SUMMARY_PATH, summary)
    write_yaml(repo_root / COMPILE_SUMMARY_PATH, build_compile_summary(repo_root, summary["created_at_utc"]))
    write_yaml(repo_root / CLOSEOUT_PATH, build_closeout(summary))
    upsert_artifact_registry(repo_root, summary, attempt_rows)
    if write_control_records:
        update_control_records(repo_root, summary)


def upsert_artifact_registry(repo_root: Path, summary: dict[str, Any], attempt_rows: list[dict[str, Any]]) -> None:
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
    producer = "python foundation/pipelines/prepare_wave01_event_barrier_l4_decision_replay_attempts.py --write-control-records"

    def put(row: dict[str, Any]) -> None:
        path_text = row.get("path_or_uri", "")
        full = repo_root / path_text if path_text and "://" not in path_text else None
        if full and full.exists():
            row["sha256"] = base.sha256(full)
            row["size_bytes"] = str(full.stat().st_size)
        by_id[row["artifact_id"]] = {key: str(row.get(key, "")) for key in fieldnames}

    for artifact_id, artifact_type, path, notes in [
        ("artifact_wave01_decision_replay_adapter_summary_v0", "decision_replay_adapter_summary", SUMMARY_PATH, "Wave01 decision replay adapter preparation summary"),
        ("artifact_wave01_decision_replay_adapter_index_v0", "decision_replay_adapter_index", INDEX_PATH, "prepared Wave01 decision replay attempts"),
        ("artifact_wave01_decision_replay_adapter_eligibility_index_v0", "decision_replay_adapter_eligibility_index", ELIGIBILITY_INDEX_PATH, "eligibility routing for all preserved clues"),
        ("artifact_wave01_decision_replay_adapter_compile_summary_v0", "ea_compile_summary", COMPILE_SUMMARY_PATH, "compile status for score replay decision EA"),
        ("artifact_wave01_decision_replay_adapter_closeout_v0", "work_closeout", CLOSEOUT_PATH, "closeout for Wave01 decision replay adapter preparation"),
        ("artifact_wave01_score_replay_decision_probe_source_v0", "mt5_ea_source", EA_SOURCE, "score-band capable score replay decision EA source"),
        ("artifact_spacesonar_l4_score_replay_decision_probe_source_v0", "mt5_ea_source", EA_SOURCE, "current score replay decision EA source hash after score-band adapter patch"),
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
                "consumer": SUBWORK_ID,
                "claim_boundary": summary["claim_boundary"],
                "notes": notes,
            }
        )

    if (repo_root / EA_BINARY).exists():
        for artifact_id, notes in [
            ("artifact_wave01_score_replay_decision_probe_binary_v0", "compiled score-band capable score replay decision EA binary"),
            ("artifact_spacesonar_l4_score_replay_decision_probe_binary_v0", "current score replay decision EA binary hash after score-band adapter compile"),
        ]:
            put(
                {
                    "artifact_id": artifact_id,
                    "artifact_type": "mt5_ea_binary",
                    "path_or_uri": EA_BINARY.as_posix(),
                    "availability": "local_binary_hash_recorded_ignored_by_git",
                    "producer_command": "MetaEditor64 /portable /compile:foundation/mt5/experts/SpaceSonar_L4_ScoreReplayDecisionProbe.mq5",
                    "regeneration_command": "compile with MetaEditor64 /portable /compile:<path>",
                    "source_of_truth": EA_SOURCE.as_posix(),
                    "consumer": SUBWORK_ID,
                    "claim_boundary": "ea_compile_or_binary_preflight_only_not_strategy_tester_output",
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
                    "consumer": SUBWORK_ID,
                    "claim_boundary": summary["claim_boundary"],
                    "notes": "Wave01 score-band decision replay preparation only; terminal execution pending",
                }
            )
    base.write_csv(registry_path, list(by_id.values()), fieldnames)


def update_control_records(repo_root: Path, summary: dict[str, Any]) -> None:
    state = base.git_state(repo_root)
    output_hashes = [
        base.artifact_ref(repo_root / SUMMARY_PATH, repo_root),
        base.artifact_ref(repo_root / INDEX_PATH, repo_root),
        base.artifact_ref(repo_root / ELIGIBILITY_INDEX_PATH, repo_root),
        base.artifact_ref(repo_root / COMPILE_SUMMARY_PATH, repo_root),
        base.artifact_ref(repo_root / CLOSEOUT_PATH, repo_root),
    ]
    input_hashes = [
        base.artifact_ref(repo_root / PAIR_INDEX, repo_root),
        base.artifact_ref(repo_root / PREP_INDEX, repo_root),
        base.artifact_ref(repo_root / EA_SOURCE, repo_root),
    ]

    next_work = base.load_yaml(repo_root / NEXT_WORK_ITEM)
    truth = next_work.setdefault("current_truth", {})
    truth["wave01_event_barrier_l4_decision_replay_adapter_preparation_summary"] = SUMMARY_PATH.as_posix()
    truth["wave01_event_barrier_l4_decision_replay_adapter_preparation_status"] = summary["status"]
    truth["wave01_event_barrier_l4_decision_replay_adapter_preparation_counts"] = summary["counts"]
    next_work["status"] = "wave01_event_barrier_l4_decision_replay_adapter_prepared_terminal_execution_next"
    next_work["missing_material_if_relevant"] = summary["judgment"]["missing_evidence"]
    next_work["next_action"] = summary["judgment"]["next_action"]
    next_work["execution_provenance"] = {
        "git_sha": state["git_sha"],
        "branch": state["branch"],
        "dirty_flag": state["dirty_flag"],
        "changed_files": state["changed_files"],
        "command_argv": summary["environment"]["command_argv"] + ["--write-control-records"],
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

    resume = base.load_yaml(repo_root / RESUME_CURSOR)
    resume["updated_at_utc"] = summary["created_at_utc"]
    sources = resume.setdefault("current_truth_sources", [])
    for source in [SUMMARY_PATH.as_posix(), INDEX_PATH.as_posix(), ELIGIBILITY_INDEX_PATH.as_posix(), CLOSEOUT_PATH.as_posix()]:
        if source not in sources:
            sources.append(source)
    resume["latest_completed_work"] = {
        "work_item_id": SUBWORK_ID,
        "result_judgment": "runtime_probe",
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [SUMMARY_PATH.as_posix(), CLOSEOUT_PATH.as_posix()],
    }
    resume["next_work_item"] = {"work_item_id": WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()}
    write_yaml(repo_root / RESUME_CURSOR, resume)

    goal = base.load_yaml(repo_root / GOAL_MANIFEST)
    goal["updated_at_utc"] = summary["created_at_utc"]
    goal["active_phase"] = NEXT_PHASE
    event_barrier = goal.setdefault("event_barrier_campaign", {})
    event_barrier["l4_decision_replay_adapter_preparation_summary"] = SUMMARY_PATH.as_posix()
    event_barrier["l4_decision_replay_adapter_preparation_status"] = summary["status"]
    event_barrier["l4_decision_replay_adapter_preparation_counts"] = summary["counts"]
    event_barrier["next_work_item"] = WORK_ITEM_ID
    write_yaml(repo_root / GOAL_MANIFEST, goal)

    workspace = base.load_yaml(repo_root / WORKSPACE_STATE)
    workspace["updated_utc"] = summary["created_at_utc"]
    claims = workspace.setdefault("current_claims", {})
    claims["active_goal_phase"] = NEXT_PHASE
    claims["wave01_event_barrier_l4_decision_replay_adapter_preparation_summary"] = SUMMARY_PATH.as_posix()
    claims["wave01_event_barrier_l4_decision_replay_adapter_preparation_status"] = summary["status"]
    claims["wave01_event_barrier_l4_decision_replay_adapter_preparation_counts"] = summary["counts"]
    claims["wave0_second_campaign_next_work_item"] = WORK_ITEM_ID
    write_yaml(repo_root / WORKSPACE_STATE, workspace)

    registry_path = repo_root / GOAL_REGISTRY
    if registry_path.exists():
        rows = base.read_csv_rows(registry_path)
        for row in rows:
            if row.get("goal_id") == GOAL_ID:
                row["active_phase"] = NEXT_PHASE
                row["next_work_item"] = WORK_ITEM_ID
                row["claim_boundary"] = "active_goal_wave01_decision_replay_adapter_prepared_not_goal_achieve"
        if rows:
            base.write_csv(registry_path, rows, list(rows[0].keys()))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare Wave01 score-band decision replay MT5 attempts.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--write-control-records", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    created_at = base.utc_now()
    summary, rows, eligibility, manifests, configs = build_records(repo_root, created_at_utc=created_at)
    if args.write_control_records:
        summary["environment"]["command_argv"].append("--write-control-records")
    write_records(
        repo_root,
        summary,
        rows,
        eligibility,
        manifests,
        configs,
        write_control_records=args.write_control_records,
    )
    print(
        json.dumps(
            {
                "status": summary["status"],
                "summary": SUMMARY_PATH.as_posix(),
                "prepared_attempt_count": summary["counts"]["prepared_attempt_count"],
                "eligible_cells": summary["counts"]["direct_trade_adapter_eligible_cell_count"],
                "not_direct_trade_cells": summary["counts"]["not_direct_trade_adapter_eligible_cell_count"],
                "claim_boundary": CLAIM_BOUNDARY,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
