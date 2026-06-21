from __future__ import annotations

import argparse
import csv
import hashlib
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
UTC = timezone.utc

GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WAVE_ID = "wave_us100_closedbar_surface_cartography_v0"
CAMPAIGN_ID = "campaign_us100_event_barrier_decision_surface_v0"
IDEA_ID = "idea_us100_m5_event_barrier_decision_surface_v0"
HYPOTHESIS_ID = "hyp_us100_event_barrier_decision_surface_v0"
SURFACE_ID = "surface_us100_event_barrier_decision_surface_v0"
SWEEP_ID = "sweep_us100_event_barrier_broad_v0"
WORK_ITEM_ID = "work_wave01_event_barrier_first_batch_spec_v0"
NEXT_WORK_ITEM_ID = "work_wave01_event_barrier_execute_first_batch_proxy_v0"
EXPECTED_BRANCH = "codex/l4-pair-judgment-closeout"
DATASET_ID = "dataset_raw_us100_m5_wave0_export_20260621T152827Z"
ROW_KEY = "us100_bar_close_time"
RUNTIME_PERIOD_PROFILE_ID = "period_profile_split_set_v0"
RUNTIME_PERIOD_SET_ID = "split_base_anchor_v0_research_l4"
TESTER_EXECUTION_PROFILE_ID = "us100_m5_fpmarkets_tester_execution_v0"
CLAIM_BOUNDARY = "first_batch_specs_only_no_run_no_candidate_no_runtime_authority"

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

ARTIFACT_REGISTRY_HEADER = [
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


PATHS = {
    "campaign_manifest": Path(f"lab/campaigns/{CAMPAIGN_ID}/campaign_manifest.yaml"),
    "surface_manifest": Path(f"lab/surfaces/{SURFACE_ID}/surface_manifest.yaml"),
    "sweep_manifest": Path(f"lab/campaigns/{CAMPAIGN_ID}/sweeps/{SWEEP_ID}/sweep_manifest.yaml"),
    "run_refs": Path(f"lab/campaigns/{CAMPAIGN_ID}/sweeps/{SWEEP_ID}/run_refs.csv"),
    "campaign_dir": Path(f"lab/campaigns/{CAMPAIGN_ID}"),
    "run_specs_dir": Path(f"lab/campaigns/{CAMPAIGN_ID}/run_specs"),
    "matrix": Path(f"lab/campaigns/{CAMPAIGN_ID}/first_batch_matrix.csv"),
    "run_specs_index": Path(f"lab/campaigns/{CAMPAIGN_ID}/run_specs_index.csv"),
    "first_batch_manifest": Path(f"lab/campaigns/{CAMPAIGN_ID}/first_batch_run_specs_manifest.yaml"),
    "anti_selection_ledger": Path(f"lab/campaigns/{CAMPAIGN_ID}/anti_selection_ledger.yaml"),
    "goal_manifest": Path(f"lab/goals/{GOAL_ID}/goal_manifest.yaml"),
    "resume_cursor": Path(f"lab/goals/{GOAL_ID}/resume_cursor.yaml"),
    "next_work_item": Path(f"lab/goals/{GOAL_ID}/next_work_item.yaml"),
    "closeout": Path(f"lab/goals/{GOAL_ID}/{WORK_ITEM_ID}_closeout.yaml"),
    "workspace_state": Path("docs/workspace/workspace_state.yaml"),
    "campaign_registry": Path("docs/registers/campaign_registry.csv"),
    "sweep_registry": Path("docs/registers/sweep_registry.csv"),
    "artifact_registry": Path("docs/registers/artifact_registry.csv"),
    "feature_recipe": Path("configs/onnx_lab/feature_recipes/feature_wave01_us100_price_session_regime_flexible_v0.yaml"),
    "label_recipe": Path("configs/onnx_lab/label_recipes/label_wave01_event_barrier_path_v0.yaml"),
    "model_recipe": Path("configs/onnx_lab/model_recipes/model_wave01_onnx_feasible_scout_v0.yaml"),
    "decision_recipe": Path("configs/onnx_lab/decision_recipes/decision_wave01_barrier_abstain_risk_v0.yaml"),
    "eval_recipe": Path("configs/onnx_lab/eval_recipes/eval_wave01_event_barrier_runtime_v0.yaml"),
    "surface_contract": Path("configs/onnx_lab/surface_contracts/surface_us100_event_barrier_decision_surface_v0.yaml"),
    "split_recipe": Path("configs/onnx_lab/split_recipes/split_set_v0.yaml"),
    "runtime_contract": Path("foundation/config/mt5_runtime_probe_contract.yaml"),
    "runtime_period_profile": Path("configs/mt5/period_profiles/split_set_v0_runtime_periods.yaml"),
    "tester_execution_profile": Path("configs/mt5/tester_execution_profile_v0.yaml"),
}


def first_batch_rows() -> list[dict[str, Any]]:
    rows = [
        {
            "spec_id": "wave01_eb_cell_001",
            "label_surface": "symmetric_barrier_touch_or_timeout",
            "horizon_bars": 6,
            "barrier_unit": "atr_multiplier",
            "upper_barrier": 0.8,
            "lower_barrier": 0.8,
            "timeout_bars": 6,
            "feature_family": "price_return_range_volatility_context",
            "feature_scope": "compact_price_volatility_context",
            "model_family": "logistic_or_linear_rank_scout",
            "model_task": "three_class_event_touch_timeout",
            "decision_family": "abstain_band_with_barrier_exit",
            "holding_policy": "barrier_or_timeout_declared_per_run",
            "risk_policy": "fixed_lot_0_02_distance_conversion_required_before_L4",
            "threshold_policy": "train_only_coarse_density_bands",
            "split_use": "train_validation_research_oos_a_no_locked_final",
            "purpose": "small symmetric event barrier sanity surface",
        },
        {
            "spec_id": "wave01_eb_cell_002",
            "label_surface": "asymmetric_upside_breakout_barrier",
            "horizon_bars": 12,
            "barrier_unit": "atr_multiplier",
            "upper_barrier": 1.2,
            "lower_barrier": 0.7,
            "timeout_bars": 12,
            "feature_family": "multiscale_price_range_volatility_context",
            "feature_scope": "multi_horizon_returns_ranges_volatility",
            "model_family": "tree_or_boosted_onnx_feasible_scout",
            "model_task": "event_direction_with_no_touch",
            "decision_family": "breakout_entry_abstain_timeout_exit",
            "holding_policy": "event_touch_or_timeout_declared_per_run",
            "risk_policy": "barrier_distance_to_point_tick_conversion_required",
            "threshold_policy": "train_only_abstain_quantile_grid",
            "split_use": "train_validation_research_oos_a_no_locked_final",
            "purpose": "breakout edge with asymmetric barriers",
        },
        {
            "spec_id": "wave01_eb_cell_003",
            "label_surface": "mfe_mae_path_quality_ratio",
            "horizon_bars": 12,
            "barrier_unit": "price_range_ratio",
            "upper_barrier": 1.0,
            "lower_barrier": 1.0,
            "timeout_bars": 12,
            "feature_family": "causal_regime_context",
            "feature_scope": "rolling_volatility_trend_regime_context",
            "model_family": "logistic_or_linear_rank_scout",
            "model_task": "path_quality_rank_or_bucket",
            "decision_family": "direction_agnostic_tradeability_abstain",
            "holding_policy": "timeout_path_quality_observation",
            "risk_policy": "no_trade_until_decision_surface_declares_direction",
            "threshold_policy": "rank_only_no_probability_claim",
            "split_use": "train_validation_research_oos_a_no_locked_final",
            "purpose": "path quality without inherited long short direction",
        },
        {
            "spec_id": "wave01_eb_cell_004",
            "label_surface": "time_to_event_or_no_touch",
            "horizon_bars": 24,
            "barrier_unit": "atr_multiplier",
            "upper_barrier": 1.4,
            "lower_barrier": 1.4,
            "timeout_bars": 24,
            "feature_family": "session_state_context",
            "feature_scope": "cash_pre_after_session_flags_only",
            "model_family": "logistic_or_linear_rank_scout",
            "model_task": "time_to_touch_bucket",
            "decision_family": "no_trade_vs_fast_event_abstain",
            "holding_policy": "fast_event_or_timeout",
            "risk_policy": "distance_units_declared_before_MT5",
            "threshold_policy": "none_diagnostic_rank",
            "split_use": "train_validation_research_oos_a_no_locked_final",
            "purpose": "session-conditioned fast touch/no-touch scout",
        },
        {
            "spec_id": "wave01_eb_cell_005",
            "label_surface": "failed_breakout_reversal_barrier",
            "horizon_bars": 9,
            "barrier_unit": "atr_multiplier",
            "upper_barrier": 0.9,
            "lower_barrier": 1.3,
            "timeout_bars": 9,
            "feature_family": "price_return_range_volatility_context",
            "feature_scope": "range_position_and_recent_reversal_context",
            "model_family": "logistic_or_linear_rank_scout",
            "model_task": "failed_event_direction_bucket",
            "decision_family": "reversal_entry_abstain_timeout_exit",
            "holding_policy": "failed_touch_confirmation_or_timeout",
            "risk_policy": "barrier_to_stop_takeprofit_conversion_required",
            "threshold_policy": "train_only_coarse_abstain_band",
            "split_use": "train_validation_research_oos_a_no_locked_final",
            "purpose": "opposite-side path after failed touch",
        },
        {
            "spec_id": "wave01_eb_cell_006",
            "label_surface": "compression_then_expansion_barrier",
            "horizon_bars": 24,
            "barrier_unit": "atr_multiplier",
            "upper_barrier": 1.8,
            "lower_barrier": 1.8,
            "timeout_bars": 24,
            "feature_family": "causal_regime_context",
            "feature_scope": "volatility_compression_and_expansion_context",
            "model_family": "tree_or_boosted_onnx_feasible_scout",
            "model_task": "large_move_event_or_timeout",
            "decision_family": "sparse_event_abstain_barrier_exit",
            "holding_policy": "large_event_or_timeout",
            "risk_policy": "fixed_lot_0_02_sparse_event_distance_conversion_required",
            "threshold_policy": "train_only_min_density_guard",
            "split_use": "train_validation_research_oos_a_no_locked_final",
            "purpose": "extreme-ish sparse expansion event surface",
        },
        {
            "spec_id": "wave01_eb_cell_007",
            "label_surface": "volatility_shock_continuation",
            "horizon_bars": 3,
            "barrier_unit": "atr_multiplier",
            "upper_barrier": 0.6,
            "lower_barrier": 0.6,
            "timeout_bars": 3,
            "feature_family": "price_return_range_volatility_context",
            "feature_scope": "short_horizon_shock_context",
            "model_family": "logistic_or_linear_rank_scout",
            "model_task": "shock_continuation_direction_or_timeout",
            "decision_family": "fast_event_abstain_timeout_exit",
            "holding_policy": "very_short_event_or_timeout",
            "risk_policy": "spread_and_fill_timing_risk_declared_before_L4",
            "threshold_policy": "train_only_density_floor",
            "split_use": "train_validation_research_oos_a_no_locked_final",
            "purpose": "fast shock surface to expose execution timing drift",
        },
        {
            "spec_id": "wave01_eb_cell_008",
            "label_surface": "session_transition_barrier_touch",
            "horizon_bars": 12,
            "barrier_unit": "atr_multiplier",
            "upper_barrier": 1.0,
            "lower_barrier": 1.0,
            "timeout_bars": 12,
            "feature_family": "session_state_context",
            "feature_scope": "ny_session_transition_and_price_context",
            "model_family": "logistic_or_linear_rank_scout",
            "model_task": "session_touch_direction_or_timeout",
            "decision_family": "session_gated_abstain_barrier_exit",
            "holding_policy": "session_transition_event_or_timeout",
            "risk_policy": "session_close_timeout_semantics_required_before_L4",
            "threshold_policy": "train_only_session_density_bands",
            "split_use": "train_validation_research_oos_a_no_locked_final",
            "purpose": "session transition touch/no-touch surface",
        },
        {
            "spec_id": "wave01_eb_cell_009",
            "label_surface": "low_volatility_no_touch_regime",
            "horizon_bars": 36,
            "barrier_unit": "atr_multiplier",
            "upper_barrier": 1.5,
            "lower_barrier": 1.5,
            "timeout_bars": 36,
            "feature_family": "causal_regime_context",
            "feature_scope": "quiet_regime_persistence_context",
            "model_family": "tree_or_boosted_onnx_feasible_scout",
            "model_task": "no_touch_or_tradeability_regime",
            "decision_family": "no_trade_regime_filter",
            "holding_policy": "timeout_only_regime_filter",
            "risk_policy": "no_position_when_no_touch_probability_high",
            "threshold_policy": "train_only_no_trade_density_guard",
            "split_use": "train_validation_research_oos_a_no_locked_final",
            "purpose": "explicit no-trade/event-avoidance surface",
        },
        {
            "spec_id": "wave01_eb_cell_010",
            "label_surface": "pullback_to_barrier_mean_reversion",
            "horizon_bars": 18,
            "barrier_unit": "atr_multiplier",
            "upper_barrier": 0.9,
            "lower_barrier": 0.9,
            "timeout_bars": 18,
            "feature_family": "multiscale_price_range_volatility_context",
            "feature_scope": "pullback_distance_and_range_context",
            "model_family": "logistic_or_linear_rank_scout",
            "model_task": "pullback_resolution_event",
            "decision_family": "mean_reversion_abstain_barrier_exit",
            "holding_policy": "pullback_resolution_or_timeout",
            "risk_policy": "entry_distance_and_exit_distance_conversion_required",
            "threshold_policy": "train_only_coarse_abstain_band",
            "split_use": "train_validation_research_oos_a_no_locked_final",
            "purpose": "mean-reversion event surface with explicit timeout",
        },
        {
            "spec_id": "wave01_eb_cell_011",
            "label_surface": "range_edge_acceptance_rejection",
            "horizon_bars": 6,
            "barrier_unit": "price_range_ratio",
            "upper_barrier": 0.75,
            "lower_barrier": 0.75,
            "timeout_bars": 6,
            "feature_family": "price_return_range_volatility_context",
            "feature_scope": "range_edge_location_context",
            "model_family": "small_mlp_secondary_only",
            "model_task": "range_edge_accept_or_reject_bucket",
            "decision_family": "range_edge_abstain_timeout_exit",
            "holding_policy": "range_edge_event_or_timeout",
            "risk_policy": "small_mlp_allowed_only_after_onnx_feasibility_smoke",
            "threshold_policy": "no_micro_search_before_broad_clue",
            "split_use": "train_validation_research_oos_a_no_locked_final",
            "purpose": "one secondary nonlinear scout without superiority claim",
        },
        {
            "spec_id": "wave01_eb_cell_012",
            "label_surface": "extreme_timeout_path_quality",
            "horizon_bars": 48,
            "barrier_unit": "mfe_mae_ratio",
            "upper_barrier": 2.0,
            "lower_barrier": 2.0,
            "timeout_bars": 48,
            "feature_family": "multiscale_price_range_volatility_context",
            "feature_scope": "longer_context_price_range_path_context",
            "model_family": "logistic_or_linear_rank_scout",
            "model_task": "longer_path_quality_rank",
            "decision_family": "diagnostic_path_quality_no_trade_until_decision_surface",
            "holding_policy": "diagnostic_timeout_only",
            "risk_policy": "diagnostic_no_position_until_trade_surface_declared",
            "threshold_policy": "rank_only_no_probability_claim",
            "split_use": "train_validation_research_oos_a_no_locked_final",
            "purpose": "extreme horizon path-quality boundary scout",
        },
    ]
    for row in rows:
        row["valid_proxy_model_bearing"] = True
        row["locked_final_oos_b_used"] = False
        row["auxiliary_symbols"] = "none"
        row["feature_count_policy"] = "variable_declared_per_run_no_fixed_count"
        row["runtime_level_required"] = "L4_split_runtime_probe"
    return rows


def now_utc() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def repo_path(repo_root: Path, rel_path: Path) -> Path:
    return repo_root / rel_path


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} does not contain a YAML mapping")
    return payload


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8")


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv_rows(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def git_value(repo_root: Path, args: list[str], default: str = "unknown") -> str:
    result = subprocess.run(["git", *args], cwd=repo_root, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return default
    return result.stdout.strip() or default


def git_status_lines(repo_root: Path) -> list[str]:
    result = subprocess.run(["git", "status", "--short"], cwd=repo_root, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def artifact_identity(path: Path, repo_root: Path) -> dict[str, Any]:
    return {"path": rel(path, repo_root), "sha256": sha256_file(path), "size_bytes": path.stat().st_size}


def recipe_identity(repo_root: Path) -> dict[str, dict[str, Any]]:
    keys = [
        "feature_recipe",
        "label_recipe",
        "model_recipe",
        "decision_recipe",
        "eval_recipe",
        "surface_contract",
        "split_recipe",
        "runtime_contract",
        "runtime_period_profile",
        "tester_execution_profile",
    ]
    return {key: artifact_identity(repo_path(repo_root, PATHS[key]), repo_root) for key in keys}


def build_run_spec(row: dict[str, Any], repo_root: Path, created_at: str) -> dict[str, Any]:
    spec_id = str(row["spec_id"])
    return {
        "version": "planned_run_spec_v1",
        "run_spec_id": spec_id,
        "planned_run_id": f"onnxlab_{spec_id}_event_barrier_surface_v0",
        "status": "planned_not_executed",
        "created_at_utc": created_at,
        "id_chain": {
            "goal_id": GOAL_ID,
            "wave_id": WAVE_ID,
            "campaign_id": CAMPAIGN_ID,
            "idea_id": IDEA_ID,
            "hypothesis_id": HYPOTHESIS_ID,
            "surface_id": SURFACE_ID,
            "sweep_id": SWEEP_ID,
        },
        "claim_boundary": CLAIM_BOUNDARY,
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "data_contract": {
            "dataset_id": DATASET_ID,
            "base_frame": "FPMarkets_US100_M5_closed_bars",
            "row_key": ROW_KEY,
            "timestamp_source": "MT5_server_datetime_from_history_audit",
            "utc_conversion_status": "not_claimed",
            "row_membership_manifest": "lab/campaigns/campaign_us100_task_surface_scout_v0/row_membership/row_membership_manifest.yaml",
            "feature_boundary": "causal_history_only_declared_per_run",
            "label_boundary": "future_event_barrier_with_tail_drop_and_split_boundary_check",
            "split_boundary": "split_set_v0_train_validation_research_oos_a_locked_final_excluded",
            "locked_final_oos_b_used": False,
            "auxiliary_symbols": "none",
        },
        "axis_values": row,
        "feature_contract": {
            "feature_family": row["feature_family"],
            "feature_scope": row["feature_scope"],
            "feature_count_policy": "variable_declared_per_run_no_fixed_count",
            "feature_order_policy": "declared_and_hashed_before_ONNX_export",
            "forbidden_defaults": ["fixed_feature_count", "inherited_feature_list"],
        },
        "label_contract": {
            "label_surface": row["label_surface"],
            "horizon_bars": row["horizon_bars"],
            "timeout_bars": row["timeout_bars"],
            "barrier_unit": row["barrier_unit"],
            "upper_barrier": row["upper_barrier"],
            "lower_barrier": row["lower_barrier"],
            "tail_drop_policy": "required_for_timeout_or_horizon",
            "direction_mapping": "declared_by_this_spec_not_inherited",
        },
        "model_contract": {
            "model_family": row["model_family"],
            "model_task": row["model_task"],
            "output_head": "declared_at_execution_no_default_head",
            "hyperparameter_policy": "no_micro_search_before_broad_clue",
            "onnx_feasibility_required_before_runtime": True,
        },
        "decision_contract": {
            "decision_family": row["decision_family"],
            "holding_policy": row["holding_policy"],
            "risk_policy": row["risk_policy"],
            "threshold_policy": row["threshold_policy"],
            "sizing_policy": "fixed_lot_0_02_default_when_MT5_runs_execute",
        },
        "proxy_runtime_parity": {
            "required": True,
            "shared_contract": [
                "dataset_id",
                ROW_KEY,
                "split_set_v0",
                "declared_feature_order",
                "declared_label_surface",
                "declared_decision_holding_risk_policy",
                TESTER_EXECUTION_PROFILE_ID,
            ],
            "known_differences": [
                "proxy_barrier_touch_order_may_not_equal_MT5_intra_bar_execution",
                "spread_fill_and_timeout_close_timing_may_differ",
                "price_distance_units_require_point_digits_tick_size_conversion",
            ],
            "minimum_reconciliation_attempt": {
                "required": True,
                "status": "pending_first_proxy_runtime_difference",
                "forced_equality_required": False,
            },
            "unit_semantics": {
                "barrier_unit": row["barrier_unit"],
                "point": "must_record_before_MT5_L4",
                "digits": "must_record_before_MT5_L4",
                "tick_size": "must_record_before_MT5_L4",
                "price_distance_conversion": "required_before_MT5_L4",
                "lot_step": "tester_profile_default_until_run_specific",
                "rounding_policy": "explicit_before_MT5_L4",
            },
            "comparison_classes": [
                "proxy_good_runtime_good",
                "proxy_good_runtime_bad",
                "proxy_bad_runtime_bad",
                "proxy_bad_runtime_good",
                "invalid_or_unmaterializable",
            ],
            "divergence_judgment": "pending_execution_and_L4",
            "prevention_memory": [
                "do_not_reuse_momentum_ret_1_score_replay_negative_memory_as_candidate",
                "record_price_distance_unit_conversion_before_reusing_barrier_or_ATR_stop_logic",
            ],
        },
        "runtime_learning_probe_decision": {
            "required": True,
            "decision": "run_required_after_valid_proxy_model_execution",
            "target_level": "L4_split_runtime_probe",
            "runtime_period_profile_id": RUNTIME_PERIOD_PROFILE_ID,
            "runtime_period_set_id": RUNTIME_PERIOD_SET_ID,
            "tester_execution_profile_id": TESTER_EXECUTION_PROFILE_ID,
            "required_period_roles": ["validation", "research_oos"],
            "l4_promising_result_effect": "continue_to_L5_candidate_runtime_evidence",
            "proxy_only_closeout_allowed": False,
        },
        "failure_disposition_policy": {
            "required_before_blocked_deferred_invalid_or_discarded": [
                "failure_reproduction",
                "exact_failing_layer",
                "bounded_repair_or_fallback_attempt",
                "evidence_path",
                "remaining_blocker",
                "reopen_condition",
            ],
            "repo_controlled_support_gap_action": "build_or_patch_smallest_adapter_or_fallback",
            "no_adapter_exists_claim_effect": "repair_trigger_not_blocker",
        },
        "result_judgment": "not_evaluated",
        "missing_evidence": [
            "features_not_materialized",
            "labels_not_materialized",
            "model_not_trained",
            "proxy_metrics_not_computed",
            "onnx_not_exported",
            "MT5_L4_not_run",
        ],
        "next_action": NEXT_WORK_ITEM_ID,
    }


def write_matrix(repo_root: Path, rows: list[dict[str, Any]]) -> Path:
    matrix_path = repo_path(repo_root, PATHS["matrix"])
    fieldnames = [
        "spec_id",
        "label_surface",
        "horizon_bars",
        "barrier_unit",
        "upper_barrier",
        "lower_barrier",
        "timeout_bars",
        "feature_family",
        "feature_scope",
        "model_family",
        "model_task",
        "decision_family",
        "holding_policy",
        "risk_policy",
        "threshold_policy",
        "split_use",
        "valid_proxy_model_bearing",
        "runtime_level_required",
        "locked_final_oos_b_used",
        "auxiliary_symbols",
        "feature_count_policy",
        "purpose",
    ]
    write_csv_rows(matrix_path, fieldnames, rows)
    return matrix_path


def materialize_run_specs(repo_root: Path, rows: list[dict[str, Any]], created_at: str) -> tuple[Path, Path, list[dict[str, Any]]]:
    spec_dir = repo_path(repo_root, PATHS["run_specs_dir"])
    index_rows: list[dict[str, Any]] = []
    spec_refs: list[dict[str, Any]] = []
    for row in rows:
        spec = build_run_spec(row, repo_root, created_at)
        spec_path = spec_dir / f"{row['spec_id']}.yaml"
        write_yaml(spec_path, spec)
        identity = artifact_identity(spec_path, repo_root)
        index_rows.append(
            {
                "run_spec_id": row["spec_id"],
                "planned_run_id": spec["planned_run_id"],
                "status": "planned_not_executed",
                "run_spec_path": identity["path"],
                "sha256": identity["sha256"],
                "size_bytes": identity["size_bytes"],
                "label_surface": row["label_surface"],
                "feature_family": row["feature_family"],
                "model_family": row["model_family"],
                "decision_family": row["decision_family"],
                "runtime_level_required": "L4_split_runtime_probe",
                "claim_boundary": CLAIM_BOUNDARY,
            }
        )
        spec_refs.append({"run_spec_id": row["spec_id"], "planned_run_id": spec["planned_run_id"], **identity})
    index_path = repo_path(repo_root, PATHS["run_specs_index"])
    write_csv_rows(
        index_path,
        [
            "run_spec_id",
            "planned_run_id",
            "status",
            "run_spec_path",
            "sha256",
            "size_bytes",
            "label_surface",
            "feature_family",
            "model_family",
            "decision_family",
            "runtime_level_required",
            "claim_boundary",
        ],
        index_rows,
    )
    return spec_dir, index_path, spec_refs


def write_run_refs(repo_root: Path, spec_refs: list[dict[str, Any]], created_at: str) -> Path:
    rows = [
        {
            "run_spec_id": item["run_spec_id"],
            "planned_run_id": item["planned_run_id"],
            "status": "planned_not_executed",
            "created_at_utc": created_at,
            "run_spec_path": item["path"],
            "claim_boundary": CLAIM_BOUNDARY,
            "result_judgment": "not_evaluated",
            "next_action": NEXT_WORK_ITEM_ID,
        }
        for item in spec_refs
    ]
    path = repo_path(repo_root, PATHS["run_refs"])
    write_csv_rows(
        path,
        [
            "run_spec_id",
            "planned_run_id",
            "status",
            "created_at_utc",
            "run_spec_path",
            "claim_boundary",
            "result_judgment",
            "next_action",
        ],
        rows,
    )
    return path


def write_anti_selection_ledger(repo_root: Path, rows: list[dict[str, Any]], matrix_path: Path, created_at: str) -> Path:
    path = repo_path(repo_root, PATHS["anti_selection_ledger"])
    payload = {
        "version": "anti_selection_ledger_v1",
        "ledger_id": "anti_selection_wave01_event_barrier_first_batch_v0",
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": created_at,
        "status": "initialized_before_results",
        "result_viewed": False,
        "claim_boundary": "first_batch_spec_anti_selection_plan_only_no_result_no_candidate",
        "source_inputs": {
            "first_batch_matrix": artifact_identity(matrix_path, repo_root),
            "campaign_manifest": artifact_identity(repo_path(repo_root, PATHS["campaign_manifest"]), repo_root),
            "sweep_manifest": artifact_identity(repo_path(repo_root, PATHS["sweep_manifest"]), repo_root),
        },
        "search_space_budget": {
            "initial_batch_size": len(rows),
            "max_repairs_per_surface": 1,
            "repair_scope": "invalid_setup_or_parity_semantics_only_not_performance_rescue",
            "locked_final_oos_use": "forbidden",
            "fine_search_gate": "requires_repeated_surface_clue_after_broad_batch",
        },
        "selection_rules": [
            "No spec can become a candidate from a planned run spec or a single proxy observation.",
            "Every valid proxy/model-bearing spec must reach L4 validation and research_oos or record invalid/failure disposition with repair evidence.",
            "OOS-A can be observed for research; adaptive repair after OOS-A must be labeled adaptive_oos_result.",
            "OOS-B locked final stays inaccessible until candidate freeze and explicit unlock.",
            "Threshold knife-edge behavior is preserved as clue, inconclusive, or negative memory, not candidate.",
            "Proxy-bad/runtime-good and proxy-good/runtime-bad both become parity divergence evidence.",
        ],
        "first_batch_specs": [row["spec_id"] for row in rows],
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "next_action": NEXT_WORK_ITEM_ID,
    }
    write_yaml(path, payload)
    return path


def write_first_batch_manifest(
    repo_root: Path,
    rows: list[dict[str, Any]],
    matrix_path: Path,
    run_specs_index: Path,
    run_refs: Path,
    anti_selection_ledger: Path,
    spec_refs: list[dict[str, Any]],
    created_at: str,
) -> Path:
    path = repo_path(repo_root, PATHS["first_batch_manifest"])
    label_count = len({row["label_surface"] for row in rows})
    feature_count = len({row["feature_family"] for row in rows})
    model_count = len({row["model_family"] for row in rows})
    decision_count = len({row["decision_family"] for row in rows})
    payload = {
        "version": "first_batch_run_specs_manifest_v1",
        "manifest_id": "first_batch_run_specs_wave01_event_barrier_v0",
        "active_goal_id": GOAL_ID,
        "wave_id": WAVE_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": created_at,
        "status": "first_batch_specs_materialized_not_executed",
        "claim_boundary": CLAIM_BOUNDARY,
        "spec_count": len(rows),
        "coverage_summary": {
            "label_surface_count": label_count,
            "feature_family_count": feature_count,
            "model_family_count": model_count,
            "decision_family_count": decision_count,
            "multi_axis_discovery": True,
            "feature_only_or_label_only_or_model_only": False,
            "valid_proxy_model_bearing_specs_require_L4": True,
            "locked_final_oos_b_used": False,
        },
        "source_inputs": {
            "campaign_manifest": artifact_identity(repo_path(repo_root, PATHS["campaign_manifest"]), repo_root),
            "surface_manifest": artifact_identity(repo_path(repo_root, PATHS["surface_manifest"]), repo_root),
            "sweep_manifest": artifact_identity(repo_path(repo_root, PATHS["sweep_manifest"]), repo_root),
            "recipes": recipe_identity(repo_root),
        },
        "outputs": {
            "first_batch_matrix": artifact_identity(matrix_path, repo_root),
            "run_specs_index": artifact_identity(run_specs_index, repo_root),
            "run_refs": artifact_identity(run_refs, repo_root),
            "anti_selection_ledger": artifact_identity(anti_selection_ledger, repo_root),
            "run_specs": spec_refs,
        },
        "runtime_learning_probe_decision": {
            "required_for_valid_proxy_model_bearing_specs": True,
            "target_level": "L4_split_runtime_probe",
            "runtime_period_profile_id": RUNTIME_PERIOD_PROFILE_ID,
            "runtime_period_set_id": RUNTIME_PERIOD_SET_ID,
            "required_period_roles": ["validation", "research_oos"],
            "l4_promising_result_effect": "continue_to_L5_candidate_runtime_evidence",
        },
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "missing_evidence": [
            "features_not_materialized",
            "labels_not_materialized",
            "models_not_trained",
            "proxy_metrics_not_computed",
            "ONNX_exports_not_materialized",
            "MT5_L4_not_run",
        ],
        "next_action": NEXT_WORK_ITEM_ID,
    }
    write_yaml(path, payload)
    return path


def update_yaml_records(repo_root: Path, created_at: str, outputs: dict[str, Path], rows: list[dict[str, Any]]) -> None:
    campaign_path = repo_path(repo_root, PATHS["campaign_manifest"])
    campaign = read_yaml(campaign_path)
    campaign["status"] = "first_batch_specs_materialized_not_executed"
    campaign["updated_at_utc"] = created_at
    campaign["claim_boundary"] = CLAIM_BOUNDARY
    campaign["first_batch_specs"] = {
        "status": "materialized_not_executed",
        "spec_count": len(rows),
        "matrix": rel(outputs["matrix"], repo_root),
        "run_specs_index": rel(outputs["run_specs_index"], repo_root),
        "run_refs": rel(outputs["run_refs"], repo_root),
        "manifest": rel(outputs["first_batch_manifest"], repo_root),
        "anti_selection_ledger": rel(outputs["anti_selection_ledger"], repo_root),
        "runtime_follow_through": "L4_required_for_all_valid_proxy_model_bearing_specs",
        "claim_boundary": CLAIM_BOUNDARY,
    }
    campaign["next_action"] = NEXT_WORK_ITEM_ID
    write_yaml(campaign_path, campaign)

    sweep_path = repo_path(repo_root, PATHS["sweep_manifest"])
    sweep = read_yaml(sweep_path)
    sweep["status"] = "first_batch_specs_materialized_not_executed"
    sweep["updated_at_utc"] = created_at
    sweep["evidence_boundary"] = "first_batch_specs_only_no_run_evidence"
    sweep["first_batch_specs"] = campaign["first_batch_specs"]
    sweep["next_action"] = NEXT_WORK_ITEM_ID
    write_yaml(sweep_path, sweep)

    closeout_path = repo_path(repo_root, PATHS["closeout"])
    closeout = {
        "version": "work_closeout_v1",
        "work_item_id": WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "status": "first_batch_specs_materialized_not_executed",
        "closed_at_utc": created_at,
        "result_judgment": "planning_scaffold",
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_paths": [
            rel(outputs["matrix"], repo_root),
            rel(outputs["run_specs_index"], repo_root),
            rel(outputs["run_refs"], repo_root),
            rel(outputs["first_batch_manifest"], repo_root),
            rel(outputs["anti_selection_ledger"], repo_root),
        ],
        "spec_count": len(rows),
        "runtime_follow_through": {
            "valid_proxy_model_bearing_specs_require_L4": True,
            "l4_promising_result_effect": "continue_to_L5_candidate_runtime_evidence",
        },
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "next_action": NEXT_WORK_ITEM_ID,
    }
    write_yaml(closeout_path, closeout)

    next_work = {
        "version": "onnx_lab_work_item_v1",
        "work_item_id": NEXT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "created_at_utc": created_at,
        "status": "planned_not_started",
        "user_request": "Execute the first broad proxy batch for the Wave01 event/barrier decision campaign, then force valid proxy/model-bearing results through L4 follow-through.",
        "current_truth": {
            "first_batch_manifest": rel(outputs["first_batch_manifest"], repo_root),
            "run_specs_index": rel(outputs["run_specs_index"], repo_root),
            "campaign_manifest": rel(campaign_path, repo_root),
            "sweep_manifest": rel(sweep_path, repo_root),
        },
        "work_classification": {
            "primary_family": "model_training",
            "detected_families": ["data_feature_build", "model_training", "onnx_export_parity", "runtime_probe"],
            "mutation_intent": "execute_proxy_batch_and_prepare_L4_follow_through",
        },
        "skill_routing": {
            "primary_family": "model_training",
            "primary_skill": "spacesonar-model-validation",
            "support_skills": [
                "spacesonar-experiment-design",
                "spacesonar-data-integrity",
                "spacesonar-run-evidence-system",
                "spacesonar-runtime-parity",
                "spacesonar-claim-discipline",
            ],
            "required_gates": [
                "split_boundary_check",
                "feature_label_boundary_check",
                "run_manifest",
                "experiment_receipt",
                "proxy_runtime_parity_decision",
                "L4_follow_through_required_for_valid_proxy_model_runs",
                "final_claim_guard",
            ],
        },
        "acceptance_criteria": [
            "Execute proxy/model-bearing specs without using locked final OOS-B.",
            "Create run-local manifest, receipt, lineage, and metrics for every executed meaningful run.",
            "Do not close any valid proxy/model-bearing run proxy-only.",
            "Materialize ONNX/EA/MT5 L4 path or record try-first failure disposition before invalid/block/defer/discard.",
        ],
        "claim_boundary": "planned_proxy_execution_work_item_no_run_no_candidate_no_runtime_authority",
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "next_action": "build_or_run_event_barrier_proxy_executor_then_L4_follow_through",
    }
    write_yaml(repo_path(repo_root, PATHS["next_work_item"]), next_work)

    goal_path = repo_path(repo_root, PATHS["goal_manifest"])
    goal = read_yaml(goal_path)
    goal["updated_at_utc"] = created_at
    goal["claim_boundary"] = "active_goal_first_batch_specs_materialized_not_goal_achieve"
    goal["active_phase"] = "wave01_campaign_002_first_batch_specs_materialized"
    goal["active_ids"] = {
        "idea_id": IDEA_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "wave_id": WAVE_ID,
        "campaign_id": CAMPAIGN_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
    }
    goal["event_barrier_campaign"] = {
        "campaign_id": CAMPAIGN_ID,
        "status": "first_batch_specs_materialized_not_executed",
        "first_batch_manifest": rel(outputs["first_batch_manifest"], repo_root),
        "run_specs_index": rel(outputs["run_specs_index"], repo_root),
        "spec_count": len(rows),
        "runtime_follow_through": "L4_required_for_all_valid_proxy_model_bearing_specs",
        "claim_boundary": CLAIM_BOUNDARY,
        "next_work_item": NEXT_WORK_ITEM_ID,
    }
    goal["next_work_item"] = {"path": rel(repo_path(repo_root, PATHS["next_work_item"]), repo_root), "work_item_id": NEXT_WORK_ITEM_ID}
    write_yaml(goal_path, goal)

    resume_path = repo_path(repo_root, PATHS["resume_cursor"])
    resume = read_yaml(resume_path)
    resume["updated_at_utc"] = created_at
    resume["active_phase"] = "wave01_campaign_002_first_batch_specs_materialized"
    truth_sources = list(resume.get("current_truth_sources") or [])
    for output in [
        outputs["matrix"],
        outputs["run_specs_index"],
        outputs["run_refs"],
        outputs["first_batch_manifest"],
        outputs["anti_selection_ledger"],
        closeout_path,
    ]:
        value = rel(output, repo_root)
        if value not in truth_sources:
            truth_sources.append(value)
    resume["current_truth_sources"] = truth_sources
    resume["latest_completed_work"] = {
        "work_item_id": WORK_ITEM_ID,
        "result_judgment": "planning_scaffold",
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_paths": closeout["evidence_paths"],
    }
    resume["next_work_item"] = {"work_item_id": NEXT_WORK_ITEM_ID, "path": rel(repo_path(repo_root, PATHS["next_work_item"]), repo_root)}
    write_yaml(resume_path, resume)

    workspace_path = repo_path(repo_root, PATHS["workspace_state"])
    workspace = read_yaml(workspace_path)
    workspace["updated_utc"] = created_at
    claims = workspace.setdefault("current_claims", {})
    claims["active_campaign_id"] = CAMPAIGN_ID
    claims["active_goal_phase"] = "wave01_campaign_002_first_batch_specs_materialized"
    claims["next_work_item_id"] = NEXT_WORK_ITEM_ID
    claims["active_goal_claim_boundary"] = "active_goal_first_batch_specs_materialized_not_goal_achieve"
    claims["wave0_second_campaign_status"] = "first_batch_specs_materialized_not_executed"
    claims["wave0_second_campaign_first_batch_matrix"] = rel(outputs["matrix"], repo_root)
    claims["wave0_second_campaign_run_specs_index"] = rel(outputs["run_specs_index"], repo_root)
    claims["wave0_second_campaign_first_batch_manifest"] = rel(outputs["first_batch_manifest"], repo_root)
    claims["wave0_second_campaign_anti_selection_ledger"] = rel(outputs["anti_selection_ledger"], repo_root)
    claims["wave0_second_campaign_planned_spec_count"] = len(rows)
    claims["wave0_second_campaign_claim_boundary"] = CLAIM_BOUNDARY
    claims["wave0_second_campaign_next_work_item"] = NEXT_WORK_ITEM_ID
    write_yaml(workspace_path, workspace)


def update_csv_registries(repo_root: Path, created_at: str, outputs: dict[str, Path]) -> None:
    goal_path = repo_path(repo_root, Path("docs/registers/goal_registry.csv"))
    fields, rows = read_csv_rows(goal_path)
    for row in rows:
        if row.get("goal_id") == GOAL_ID:
            row["active_phase"] = "wave01_campaign_002_first_batch_specs_materialized"
            row["claim_boundary"] = "active_goal_first_batch_specs_materialized_not_goal_achieve"
            row["next_work_item"] = NEXT_WORK_ITEM_ID
            row["notes"] = "durable_codex_operation_primary_wave01_first_batch_specs_materialized"
    write_csv_rows(goal_path, fields, rows)

    campaign_path = repo_path(repo_root, PATHS["campaign_registry"])
    fields, rows = read_csv_rows(campaign_path)
    for row in rows:
        if row.get("campaign_id") == CAMPAIGN_ID:
            row["status"] = "first_batch_specs_materialized_not_executed"
            row["claim_boundary"] = CLAIM_BOUNDARY
            row["evidence_path"] = rel(outputs["first_batch_manifest"], repo_root)
            row["next_action"] = NEXT_WORK_ITEM_ID
            row["notes"] = "first broad event/barrier specs materialized; no run/model/runtime claim"
    write_csv_rows(campaign_path, fields, rows)

    sweep_path = repo_path(repo_root, PATHS["sweep_registry"])
    fields, rows = read_csv_rows(sweep_path)
    for row in rows:
        if row.get("sweep_id") == SWEEP_ID:
            row["status"] = "first_batch_specs_materialized_not_executed"
            row["evidence_boundary"] = "first_batch_specs_only"
            row["evidence_path"] = rel(outputs["first_batch_manifest"], repo_root)
            row["next_action"] = NEXT_WORK_ITEM_ID
            row["notes"] = "run_refs now points to planned run specs; no executed run evidence yet"
    write_csv_rows(sweep_path, fields, rows)

    artifact_path = repo_path(repo_root, PATHS["artifact_registry"])
    fields, rows = read_csv_rows(artifact_path)
    if not fields:
        fields = ARTIFACT_REGISTRY_HEADER
    by_id = {row.get("artifact_id"): row for row in rows}
    by_id.pop("artifact_wave01_event_barrier_run_refs_v1", None)
    command = "python foundation/pipelines/materialize_wave01_event_barrier_first_batch_specs.py --write-control-records"
    artifacts = [
        ("artifact_wave01_event_barrier_first_batch_matrix_v0", "first_batch_matrix", outputs["matrix"], "first batch matrix"),
        ("artifact_wave01_event_barrier_run_specs_index_v0", "run_specs_index", outputs["run_specs_index"], "planned run specs index"),
        ("artifact_wave01_event_barrier_run_refs_v0", "run_refs", outputs["run_refs"], "sweep run refs populated with planned spec refs"),
        ("artifact_wave01_event_barrier_first_batch_manifest_v0", "first_batch_manifest", outputs["first_batch_manifest"], "first batch spec source of truth"),
        ("artifact_wave01_event_barrier_anti_selection_ledger_v0", "anti_selection_ledger", outputs["anti_selection_ledger"], "anti-selection ledger before execution"),
        ("artifact_wave01_event_barrier_first_batch_spec_closeout_v0", "work_closeout", repo_path(repo_root, PATHS["closeout"]), "work item closeout"),
    ]
    for artifact_id, artifact_type, path, notes in artifacts:
        identity = artifact_identity(path, repo_root)
        by_id[artifact_id] = {
            "artifact_id": artifact_id,
            "run_id": "",
            "bundle_id": "",
            "attempt_id": "",
            "artifact_type": artifact_type,
            "path_or_uri": identity["path"],
            "sha256": identity["sha256"],
            "size_bytes": str(identity["size_bytes"]),
            "availability": "present_hash_recorded",
            "producer_command": command,
            "regeneration_command": command,
            "source_of_truth": rel(outputs["first_batch_manifest"], repo_root),
            "consumer": CAMPAIGN_ID,
            "claim_boundary": CLAIM_BOUNDARY,
            "notes": notes,
        }
    merged = list(by_id.values())
    write_csv_rows(artifact_path, fields, merged)


def validate_rows(rows: list[dict[str, Any]]) -> None:
    if len(rows) != 12:
        raise ValueError(f"expected 12 first-batch specs, got {len(rows)}")
    required_axes = ["label_surface", "feature_family", "model_family", "decision_family", "holding_policy"]
    for axis in required_axes:
        if len({str(row[axis]) for row in rows}) < 3:
            raise ValueError(f"axis {axis} is not broad enough")
    for row in rows:
        if row["locked_final_oos_b_used"]:
            raise ValueError(f"{row['spec_id']} uses locked final OOS-B")
        if row["auxiliary_symbols"] != "none":
            raise ValueError(f"{row['spec_id']} uses auxiliary symbols without live-chart evidence")
        if row["feature_count_policy"] != "variable_declared_per_run_no_fixed_count":
            raise ValueError(f"{row['spec_id']} violates feature-count policy")
        if row["runtime_level_required"] != "L4_split_runtime_probe":
            raise ValueError(f"{row['spec_id']} missing L4 requirement")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--created-at-utc", default=None)
    parser.add_argument("--write-control-records", action="store_true")
    parser.add_argument("--expected-branch", default=EXPECTED_BRANCH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    created_at = args.created_at_utc or now_utc()
    rows = first_batch_rows()
    validate_rows(rows)

    current_branch = git_value(repo_root, ["branch", "--show-current"])
    if current_branch != args.expected_branch:
        raise RuntimeError(f"branch mismatch: expected {args.expected_branch}, observed {current_branch}")

    matrix = write_matrix(repo_root, rows)
    _spec_dir, run_specs_index, spec_refs = materialize_run_specs(repo_root, rows, created_at)
    run_refs = write_run_refs(repo_root, spec_refs, created_at)
    anti_selection_ledger = write_anti_selection_ledger(repo_root, rows, matrix, created_at)
    first_batch_manifest = write_first_batch_manifest(
        repo_root,
        rows,
        matrix,
        run_specs_index,
        run_refs,
        anti_selection_ledger,
        spec_refs,
        created_at,
    )
    outputs = {
        "matrix": matrix,
        "run_specs_index": run_specs_index,
        "run_refs": run_refs,
        "anti_selection_ledger": anti_selection_ledger,
        "first_batch_manifest": first_batch_manifest,
    }

    if args.write_control_records:
        update_yaml_records(repo_root, created_at, outputs, rows)
        update_csv_registries(repo_root, created_at, outputs)

    print(
        yaml.safe_dump(
            {
                "status": "first_batch_specs_materialized_not_executed",
                "spec_count": len(rows),
                "claim_boundary": CLAIM_BOUNDARY,
                "outputs": {key: rel(path, repo_root) for key, path in outputs.items()},
                "current_branch": current_branch,
                "changed_files": git_status_lines(repo_root),
            },
            sort_keys=False,
            allow_unicode=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
