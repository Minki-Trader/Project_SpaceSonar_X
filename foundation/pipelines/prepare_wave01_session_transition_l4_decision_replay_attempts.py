from __future__ import annotations

import argparse
import json
import platform
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import foundation.pipelines.prepare_wave0_l4_decision_replay_attempts as base
from foundation.mt5.score_replay_decision_adapter import ADAPTER_ID, CLAIM_BOUNDARY, attempt_id_for, hold_bars_from_horizon


GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WORK_ITEM_ID = "work_wave01_session_transition_l4_materialization_preflight_v0"
SUBWORK_ID = "work_wave01_session_transition_l4_decision_replay_adapter_preparation_v0"
CAMPAIGN_ID = "campaign_us100_session_transition_regime_surface_v0"
SWEEP_ID = "sweep_us100_session_transition_broad_v0"
SUMMARY_ID = "wave01_session_transition_l4_decision_replay_adapter_preparation_v0"
OUTPUT_DIR = Path("lab/campaigns/campaign_us100_session_transition_regime_surface_v0/l4_follow_through/decision_replay")
SUMMARY_PATH = OUTPUT_DIR / "adapter_prep_summary.yaml"
INDEX_PATH = OUTPUT_DIR / "adapter_prep_index.csv"
ELIGIBILITY_INDEX_PATH = OUTPUT_DIR / "adapter_eligibility_index.csv"
CLOSEOUT_PATH = Path(
    "lab/goals/goal_us100_onnx_forward_boundary_v0/"
    "work_wave01_session_transition_l4_decision_replay_adapter_preparation_v0_closeout.yaml"
)
PAIR_INDEX = Path("lab/campaigns/campaign_us100_session_transition_regime_surface_v0/l4_follow_through/l4_pair_judgment_index.csv")
PREP_INDEX = Path("lab/campaigns/campaign_us100_session_transition_regime_surface_v0/l4_follow_through/l4_attempt_preparation_index.csv")
EXECUTION_PROFILE = Path("configs/mt5/tester_execution_profile_v0.yaml")
EA_SOURCE = Path("foundation/mt5/experts/SpaceSonar_L4_ScoreReplayDecisionProbe.mq5")
EA_BINARY = Path("foundation/mt5/experts/SpaceSonar_L4_ScoreReplayDecisionProbe.ex5")
EA_EXPERT_CONFIG_PATH = "Project_SpaceSonar_X\\foundation\\mt5\\experts\\SpaceSonar_L4_ScoreReplayDecisionProbe.ex5"
COMMON_DECISION_ROOT = "SpaceSonar\\wave01_session_transition_l4_decision_replay"
INVERSE_SCORE_BAND_POLICY = "score_band_inverse_side"


@dataclass(frozen=True)
class SessionDecisionPolicy:
    eligible: bool
    reason: str
    execution_kind: str
    direction_policy: str
    decision_output: str


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


def session_decision_policy(pair: dict[str, str], bundle: dict[str, Any] | None) -> SessionDecisionPolicy:
    family = pair.get("decision_family", "")
    surface = (bundle or {}).get("decision_surface") or {}
    if pair.get("proxy_judgment") != "preserved_clue":
        return SessionDecisionPolicy(False, "not_preserved_clue", "not_applicable", "", "none")
    if surface.get("diagnostic_only") is True:
        return SessionDecisionPolicy(
            False,
            "diagnostic_or_no_trade_requires_new_decision_surface",
            "diagnostic_or_no_trade",
            "",
            "flat_only_until_new_decision_surface",
        )
    if family == "failed_breakout_reversion_abstain_exit":
        return SessionDecisionPolicy(
            True,
            "eligible_failed_breakout_reversion_inverse_score_band_adapter",
            "score_band_inverse_directional",
            INVERSE_SCORE_BAND_POLICY,
            "score_ge_high_short_score_le_low_long_otherwise_flat",
        )
    if family in {"compression_release_abstain_barrier_exit", "range_acceptance_abstain_timeout_exit"}:
        return SessionDecisionPolicy(
            False,
            "non_directional_event_score_requires_declared_side_surface",
            "non_directional_event_or_tradeability",
            "",
            "no_order_mapping_without_side_surface",
        )
    return SessionDecisionPolicy(False, "unsupported_session_transition_decision_family", "unsupported", "", "none")


def build_tester_config_text(
    *,
    attempt_id: str,
    source_score_telemetry_common_path: str,
    period: dict[str, str],
    execution_profile: dict[str, Any],
    decision_family: str,
    direction_policy: str,
    score_low_threshold: float,
    score_high_threshold: float,
    hold_bars: int,
) -> str:
    tester_defaults = execution_profile["tester_defaults"]
    sizing = execution_profile["position_sizing_boundary"]
    report_name = f"Project_SpaceSonar_X\\runtime\\mt5_attempts\\{attempt_id}\\tester_report"
    execution_telemetry = f"{COMMON_DECISION_ROOT}\\{attempt_id}\\execution_telemetry.csv"
    trade_shape_telemetry = f"{COMMON_DECISION_ROOT}\\{attempt_id}\\trade_shape_telemetry.csv"
    lines = [
        "; SpaceSonar Wave01 session-transition L4 decision replay probe.",
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
        "subwork_item_id": SUBWORK_ID,
        "runtime_learning_probe_decision": {
            "required": True,
            "decision": "run_required",
            "required_runtime_level": "session_transition_decision_replay_probe_before_L5",
            "reason": "A preserved session-transition clue with directional reversion semantics requires MT5 sparse-order replay before any L5 candidate claim.",
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
            "surface_scope": "session_transition_failed_breakout_reversion_sparse_decision_surface_from_mt5_score_telemetry",
            "source_score_telemetry_common_path": row["source_score_telemetry_common_path"],
            "source_score_attempt_manifest": source_attempt["attempt_manifest_path"],
            "decision_family": row["decision_family"],
            "decision_execution_kind": row["decision_execution_kind"],
            "direction_policy": row["direction_policy"],
            "score_low_threshold": float(row["score_low_threshold"]),
            "score_high_threshold": float(row["score_high_threshold"]),
            "hold_bars": int(row["hold_bars"]),
            "decision_output": row["decision_output"],
            "forbidden_interpretation": "not_ONNX_runtime_authority_not_economics_pass_until_terminal_report_and_judgment_exist",
        },
        "proxy_runtime_parity": {
            "status": "adapter_prepared_terminal_execution_pending",
            "shared_contract": [
                "US100_M5_closed_bar_base_frame",
                "period_profile_split_set_v0",
                "us100_m5_fpmarkets_tester_execution_v0",
                "source_MT5_score_telemetry_full_period",
                "score_thresholds_from_experiment_bundle",
            ],
            "known_differences": [
                "This adapter replays previously observed MT5 score telemetry and does not run ONNX in the trading EA.",
                "Failed-breakout reversion score uses inverse polarity: high score maps short, low score maps long.",
            ],
            "interpretation_drift_risks": [
                "bar_close_time_lookup_alignment",
                "score_low_high_threshold_translation",
                "inverse_side_mapping_for_failed_breakout_reversion",
                "hold_bars_exit_semantics",
                "tester_fill_cost_spread_lot_rounding",
            ],
            "minimum_reconciliation_attempt": {
                "status": "prepared",
                "attempt": "score telemetry bar_close_time will be replayed into inverse score-band sparse orders in MT5 terminal",
                "forced_equality_required": False,
            },
            "unit_semantics": {
                "score": "single_float_score_from_prior_MT5_score_probe",
                "high_threshold": float(row["score_high_threshold"]),
                "low_threshold": float(row["score_low_threshold"]),
                "side_mapping": row["decision_output"],
                "lot": "fixed_lot_0.02",
                "hold": f"{row['hold_bars']}_M5_closed_bars",
                "point_tick_digits": "to_be_recorded_from_tester_report",
            },
            "comparison_class": "pending_terminal_execution",
            "divergence_judgment": "pending_terminal_execution",
            "prevention_memory": [
                "Do not force non-directional compression/range-acceptance clues into long/short orders without a declared side surface.",
                "Do not treat score telemetry as economics evidence.",
                "If inverse score replay behavior differs from proxy expectation, record threshold, polarity, and bar-close semantics before judging the surface.",
            ],
            "follow_up_action": "execute the prepared thin session-transition decision replay attempt before any L5/economics claim",
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
                "thin_session_transition_decision_adapter_prepared",
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
        "next_action": "run one session-transition decision replay attempt; keep L5/economics claims forbidden until reports and judgment exist",
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


def build_records(
    repo_root: Path,
    *,
    created_at_utc: str,
    cell_id_filter: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, str]]:
    pair_rows = [row for row in base.read_csv_rows(repo_root / PAIR_INDEX) if row.get("proxy_judgment") == "preserved_clue"]
    prep_by_attempt = {row["attempt_id"]: row for row in base.read_csv_rows(repo_root / PREP_INDEX)}
    execution_profile = base.load_yaml(repo_root / EXECUTION_PROFILE)
    eligibility_rows: list[dict[str, Any]] = []
    attempt_rows: list[dict[str, Any]] = []
    manifests: dict[str, dict[str, Any]] = {}
    configs: dict[str, str] = {}

    for pair in sorted(pair_rows, key=lambda item: item["cell_id"]):
        bundle = load_bundle(repo_root, pair["bundle_id"])
        policy = session_decision_policy(pair, bundle)
        prepared_for_cell = 0
        should_prepare = policy.eligible and (cell_id_filter is None or pair["cell_id"] == cell_id_filter)
        if should_prepare:
            decision_surface = bundle["decision_surface"]
            low = float(decision_surface["score_low_threshold"])
            high = float(decision_surface["score_high_threshold"])
            hold_bars = hold_bars_from_horizon((bundle.get("target_and_label") or {}).get("horizon_bars"))
            for period_role, source_attempt_id in [
                ("validation", pair["validation_attempt_id"]),
                ("research_oos", pair["research_oos_attempt_id"]),
            ]:
                source_attempt = prep_by_attempt[source_attempt_id]
                attempt_id = attempt_id_for(pair["cell_id"], period_role, policy.direction_policy)
                attempt_dir = Path("runtime/mt5_attempts") / attempt_id
                row: dict[str, Any] = {
                    "attempt_id": attempt_id,
                    "source_attempt_id": source_attempt_id,
                    "run_id": pair["run_id"],
                    "bundle_id": pair["bundle_id"],
                    "cell_id": pair["cell_id"],
                    "period_role": period_role,
                    "direction_policy": policy.direction_policy,
                    "hold_bars": hold_bars,
                    "from_date": source_attempt["from_date"],
                    "to_date": source_attempt["to_date"],
                    "status": "prepared_pending_terminal_execution",
                    "attempt_manifest_path": (attempt_dir / "attempt_manifest.yaml").as_posix(),
                    "tester_config_path": (attempt_dir / "tester_config.ini").as_posix(),
                    "source_score_telemetry_common_path": source_attempt["telemetry_common_path"],
                    "execution_telemetry_common_path": f"{COMMON_DECISION_ROOT}\\{attempt_id}\\execution_telemetry.csv",
                    "trade_shape_telemetry_common_path": f"{COMMON_DECISION_ROOT}\\{attempt_id}\\trade_shape_telemetry.csv",
                    "decision_family": pair["decision_family"],
                    "decision_execution_kind": policy.execution_kind,
                    "decision_output": policy.decision_output,
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
                "decision_execution_kind": policy.execution_kind,
                "proxy_judgment": pair["proxy_judgment"],
                "l5_routing_status": pair["l5_routing_status"],
                "direct_trade_adapter_eligible": str(policy.eligible).lower(),
                "eligibility_reason": policy.reason if cell_id_filter is None or pair["cell_id"] == cell_id_filter or not policy.eligible else "eligible_but_not_selected_for_thin_first_pass",
                "prepared_attempt_count": prepared_for_cell,
                "claim_boundary": CLAIM_BOUNDARY,
                "next_action": "execute_prepared_decision_replay_attempts" if prepared_for_cell else "preserve_clue_until_declared_side_surface_or_selected_thin_pass",
            }
        )

    counts = {
        "preserved_clue_count": len(pair_rows),
        "direct_trade_adapter_eligible_cell_count": sum(row["direct_trade_adapter_eligible"] == "true" for row in eligibility_rows),
        "not_direct_trade_adapter_eligible_cell_count": sum(row["direct_trade_adapter_eligible"] == "false" for row in eligibility_rows),
        "prepared_attempt_count": len(attempt_rows),
        "prepared_cell_count": len({row["cell_id"] for row in attempt_rows}),
        "period_role_counts": dict(sorted(Counter(row["period_role"] for row in attempt_rows).items())),
        "decision_family_counts": dict(sorted(Counter(row["decision_family"] for row in attempt_rows).items())),
        "eligibility_reason_counts": dict(sorted(Counter(row["eligibility_reason"] for row in eligibility_rows).items())),
    }
    summary = {
        "version": "wave01_session_transition_l4_decision_replay_adapter_preparation_summary_v1",
        "summary_id": SUMMARY_ID,
        "work_item_id": WORK_ITEM_ID,
        "subwork_item_id": SUBWORK_ID,
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": created_at_utc,
        "status": "thin_session_transition_decision_replay_adapter_attempts_prepared_terminal_execution_next",
        "execution_weight": "thin_first_pass",
        "adapter_id": ADAPTER_ID,
        "claim_boundary": CLAIM_BOUNDARY,
        "counts": counts,
        "source_records": {
            "pair_judgment_index": PAIR_INDEX.as_posix(),
            "score_attempt_preparation_index": PREP_INDEX.as_posix(),
            "execution_profile": EXECUTION_PROFILE.as_posix(),
        },
        "artifact_paths": {
            "summary": SUMMARY_PATH.as_posix(),
            "attempt_index": INDEX_PATH.as_posix(),
            "eligibility_index": ELIGIBILITY_INDEX_PATH.as_posix(),
            "closeout": CLOSEOUT_PATH.as_posix(),
            "ea_source": EA_SOURCE.as_posix(),
        },
        "judgment": {
            "result_subject": "Wave01 session-transition preserved-clue decision replay adapter preparation",
            "judgment_label": "runtime_probe",
            "metric_identity": "no performance metric; adapter/config preparation only",
            "comparison_baseline": "Wave01 session-transition paired L4 score telemetry preserved clues",
            "claim_boundary": CLAIM_BOUNDARY,
            "missing_evidence": [
                "decision_replay_terminal_execution_not_run",
                "tester_reports_missing_until_execution",
                "economics_metrics_missing_until_tester_report",
                "non_directional_or_diagnostic_preserved_clues_require_declared_side_surface_before_trade_replay",
            ],
            "next_action": "execute one prepared session-transition decision replay attempt before any batch expansion or L5 claim",
        },
        "prevention_memory": [
            "Attempt-first is not heavy-first: prepare the smallest directional session-transition adapter path before broad replay.",
            "Do not force compression-release, range-acceptance, diagnostic, or no-trade clues into long/short orders without a declared side surface.",
            "Failed-breakout reversion uses inverse score-band polarity: high score -> short, low score -> long.",
        ],
        "environment": {
            "command_argv": ["python", "foundation/pipelines/prepare_wave01_session_transition_l4_decision_replay_attempts.py"],
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
    if cell_id_filter:
        summary["cell_id_filter"] = cell_id_filter
    return summary, attempt_rows, eligibility_rows, manifests, configs


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
    write_yaml(repo_root / CLOSEOUT_PATH, build_closeout(summary))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare thin Wave01 session-transition decision replay MT5 attempts.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--cell-id", default="wave01_st_cell_003")
    parser.add_argument("--write-records", action="store_true")
    return parser.parse_args(argv)


def main(*_args: object, **_kwargs: object) -> int:
    from foundation.pipelines.historical_lifecycle_guard import disabled_lifecycle_entrypoint

    return disabled_lifecycle_entrypoint(
        "a run-local/domain evidence command plus locked spacesonar lifecycle transaction for canonical state updates"
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
