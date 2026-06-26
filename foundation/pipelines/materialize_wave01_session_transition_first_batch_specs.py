from __future__ import annotations

import argparse
import csv
import hashlib
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]

GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WAVE_ID = "wave_us100_closedbar_surface_cartography_v0"
CAMPAIGN_ID = "campaign_us100_session_transition_regime_surface_v0"
IDEA_ID = "idea_us100_m5_session_transition_regime_surface_v0"
HYPOTHESIS_ID = "hyp_us100_session_transition_regime_surface_v0"
SURFACE_ID = "surface_us100_session_transition_regime_surface_v0"
SWEEP_ID = "sweep_us100_session_transition_broad_v0"
WORK_ITEM_ID = "work_wave01_session_transition_first_batch_spec_v0"
NEXT_WORK_ITEM_ID = "work_wave01_session_transition_execute_first_batch_proxy_v0"
EXPECTED_BRANCH = "codex/l4-pair-judgment-closeout"

DATASET_ID = "dataset_raw_us100_m5_wave0_export_20260621T152827Z"
ROW_KEY = "us100_bar_close_time"
RUNTIME_PERIOD_PROFILE_ID = "period_profile_split_set_v0"
RUNTIME_PERIOD_SET_ID = "split_base_anchor_v0_research_l4"
TESTER_EXECUTION_PROFILE_ID = "us100_m5_fpmarkets_tester_execution_v0"

STATUS = "first_batch_specs_materialized_not_executed"
ACTIVE_PHASE = "wave01_campaign_003_first_batch_specs_materialized"
CLAIM_BOUNDARY = "session_transition_first_batch_specs_only_no_run_no_candidate_no_runtime_authority"
GOAL_CLAIM = "active_goal_session_transition_first_batch_specs_not_goal_achieve"
WAVE_CLAIM = "wave01_campaign_003_first_batch_specs_no_candidate_no_runtime_authority_not_goal_achieve"

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

PATHS = {
    "campaign_manifest": Path(f"lab/campaigns/{CAMPAIGN_ID}/campaign_manifest.yaml"),
    "surface_manifest": Path(f"lab/surfaces/{SURFACE_ID}/surface_manifest.yaml"),
    "sweep_manifest": Path(f"lab/campaigns/{CAMPAIGN_ID}/sweeps/{SWEEP_ID}/sweep_manifest.yaml"),
    "run_refs": Path(f"lab/campaigns/{CAMPAIGN_ID}/sweeps/{SWEEP_ID}/run_refs.csv"),
    "campaign_dir": Path(f"lab/campaigns/{CAMPAIGN_ID}"),
    "matrix": Path(f"lab/campaigns/{CAMPAIGN_ID}/first_batch_matrix.csv"),
    "run_specs_index": Path(f"lab/campaigns/{CAMPAIGN_ID}/run_specs_index.csv"),
    "first_batch_manifest": Path(f"lab/campaigns/{CAMPAIGN_ID}/first_batch_run_specs_manifest.yaml"),
    "anti_selection_ledger": Path(f"lab/campaigns/{CAMPAIGN_ID}/anti_selection_ledger.yaml"),
    "goal_manifest": Path(f"lab/goals/{GOAL_ID}/goal_manifest.yaml"),
    "resume_cursor": Path(f"lab/goals/{GOAL_ID}/resume_cursor.yaml"),
    "next_work_item": Path(f"lab/goals/{GOAL_ID}/next_work_item.yaml"),
    "closeout": Path(f"lab/goals/{GOAL_ID}/{WORK_ITEM_ID}_closeout.yaml"),
    "workspace_state": Path("docs/workspace/workspace_state.yaml"),
    "wave_allocation": Path(f"lab/waves/{WAVE_ID}/wave_allocation.yaml"),
    "campaign_refs": Path(f"lab/waves/{WAVE_ID}/campaign_refs.csv"),
    "campaign_registry": Path("docs/registers/campaign_registry.csv"),
    "surface_registry": Path("docs/registers/experiment_surface_registry.csv"),
    "sweep_registry": Path("docs/registers/sweep_registry.csv"),
    "wave_registry": Path("docs/registers/wave_registry.csv"),
    "goal_registry": Path("docs/registers/goal_registry.csv"),
    "artifact_registry": Path("docs/registers/artifact_registry.csv"),
    "feature_recipe": Path("configs/onnx_lab/feature_recipes/feature_wave01_us100_session_transition_regime_v0.yaml"),
    "label_recipe": Path("configs/onnx_lab/label_recipes/label_wave01_session_transition_regime_v0.yaml"),
    "model_recipe": Path("configs/onnx_lab/model_recipes/model_wave01_session_transition_onnx_scout_v0.yaml"),
    "decision_recipe": Path("configs/onnx_lab/decision_recipes/decision_wave01_session_transition_abstain_v0.yaml"),
    "eval_recipe": Path("configs/onnx_lab/eval_recipes/eval_wave01_session_transition_runtime_v0.yaml"),
    "surface_contract": Path("configs/onnx_lab/surface_contracts/surface_us100_session_transition_regime_surface_v0.yaml"),
    "split_recipe": Path("configs/onnx_lab/split_recipes/split_set_v0.yaml"),
    "runtime_contract": Path("foundation/config/mt5_runtime_probe_contract.yaml"),
    "runtime_period_profile": Path("configs/mt5/period_profiles/split_set_v0_runtime_periods.yaml"),
    "tester_execution_profile": Path("configs/mt5/tester_execution_profile_v0.yaml"),
}

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


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def repo_path(repo_root: Path, rel_path: Path) -> Path:
    return repo_root / rel_path


def rel(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = yaml.safe_load(handle)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path} does not contain a YAML mapping")
    return payload


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        yaml.dump(payload, handle, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=False)


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        return [], []
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


def upsert_csv_row(path: Path, key: str, row: dict[str, Any]) -> None:
    fields, rows = read_csv_rows(path)
    for field in row:
        if field not in fields:
            fields.append(field)
    serialized = {field: str(row.get(field, "")) for field in fields}
    for index, existing in enumerate(rows):
        if existing.get(key) == str(row[key]):
            merged = dict(existing)
            merged.update(serialized)
            rows[index] = merged
            break
    else:
        rows.append(serialized)
    write_csv_rows(path, fields, rows)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_identity(path: Path, repo_root: Path) -> dict[str, Any]:
    return {
        "path": rel(path, repo_root),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


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


def key_package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for module_name in ["yaml"]:
        module = sys.modules.get(module_name)
        versions[module_name] = str(getattr(module, "__version__", "unknown")) if module else "unknown"
    return versions


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


def first_batch_rows() -> list[dict[str, Any]]:
    rows = [
        {
            "spec_id": "wave01_st_cell_001",
            "label_surface": "cash_open_transition_followthrough",
            "horizon_bars": 6,
            "session_anchor": "ny_cash_open",
            "transition_window_bars": "pre_6_to_post_12",
            "regime_label": "open_range_expansion",
            "feature_family": "session_state_price_range_context",
            "feature_scope": "bar_position_return_range_realized_volatility_session_phase",
            "model_family": "logistic_or_linear_rank_scout",
            "model_task": "transition_followthrough_classification",
            "decision_family": "cash_open_abstain_timeout_exit",
            "holding_policy": "timeout_6_or_session_window_exit",
            "risk_policy": "fixed_lot_0_02_distance_conversion_required_before_L4",
            "threshold_policy": "train_only_coarse_density_no_pf_search",
            "split_use": "train_validation_research_oos_a_no_locked_final",
            "purpose": "test whether cash open transition state carries short-horizon followthrough information",
        },
        {
            "spec_id": "wave01_st_cell_002",
            "label_surface": "pre_cash_compression_release",
            "horizon_bars": 12,
            "session_anchor": "pre_to_cash_transition",
            "transition_window_bars": "pre_24_to_post_24",
            "regime_label": "compression_to_expansion",
            "feature_family": "compression_expansion_causal_context",
            "feature_scope": "rolling_range_contraction_expansion_and_break_location",
            "model_family": "tree_or_boosted_onnx_feasible_scout",
            "model_task": "release_or_no_release_event",
            "decision_family": "compression_release_abstain_barrier_exit",
            "holding_policy": "event_or_timeout_12",
            "risk_policy": "atr_distance_conversion_required_before_L4",
            "threshold_policy": "train_only_min_density_guard",
            "split_use": "train_validation_research_oos_a_no_locked_final",
            "purpose": "probe whether compression before cash open changes event tradeability",
        },
        {
            "spec_id": "wave01_st_cell_003",
            "label_surface": "cash_open_failed_breakout_reversion",
            "horizon_bars": 9,
            "session_anchor": "ny_cash_open",
            "transition_window_bars": "post_3_to_post_18",
            "regime_label": "failed_open_breakout",
            "feature_family": "range_edge_reversal_context",
            "feature_scope": "open_range_edge_distance_reversal_pressure_volatility",
            "model_family": "logistic_or_linear_rank_scout",
            "model_task": "failed_breakout_reversion_bucket",
            "decision_family": "failed_breakout_reversion_abstain_exit",
            "holding_policy": "confirm_or_timeout_9",
            "risk_policy": "entry_exit_distance_units_explicit_before_MT5",
            "threshold_policy": "train_only_coarse_abstain_band",
            "split_use": "train_validation_research_oos_a_no_locked_final",
            "purpose": "separate transition reversion from generic event-barrier replay",
        },
        {
            "spec_id": "wave01_st_cell_004",
            "label_surface": "mid_session_no_trade_regime",
            "horizon_bars": 18,
            "session_anchor": "ny_mid_session",
            "transition_window_bars": "cash_midday_block",
            "regime_label": "quiet_no_touch_or_low_edge",
            "feature_family": "causal_quiet_regime_context",
            "feature_scope": "low_range_low_volume_proxy_time_of_day_and_range_position",
            "model_family": "tree_or_boosted_onnx_feasible_scout",
            "model_task": "no_trade_regime_detection",
            "decision_family": "explicit_no_trade_gate",
            "holding_policy": "no_position_filter_or_timeout_18",
            "risk_policy": "no_trade_state_must_translate_to_EA_skip_before_L4",
            "threshold_policy": "train_only_no_trade_density_guard",
            "split_use": "train_validation_research_oos_a_no_locked_final",
            "purpose": "learn whether abstaining during quiet session states is itself a surface",
        },
        {
            "spec_id": "wave01_st_cell_005",
            "label_surface": "cash_close_transition_dislocation",
            "horizon_bars": 6,
            "session_anchor": "ny_cash_close",
            "transition_window_bars": "pre_close_12_to_close",
            "regime_label": "late_session_dislocation_or_fade",
            "feature_family": "session_state_price_range_context",
            "feature_scope": "late_session_range_extension_pullback_and_volatility",
            "model_family": "logistic_or_linear_rank_scout",
            "model_task": "late_session_fade_or_extension",
            "decision_family": "cash_close_abstain_timeout_exit",
            "holding_policy": "close_before_or_at_session_boundary",
            "risk_policy": "timeout_close_timing_must_be_declared_before_L4",
            "threshold_policy": "train_only_session_density_bands",
            "split_use": "train_validation_research_oos_a_no_locked_final",
            "purpose": "probe cash-close behavior without inheriting a fixed holding duration",
        },
        {
            "spec_id": "wave01_st_cell_006",
            "label_surface": "overnight_to_pre_cash_state_shift",
            "horizon_bars": 24,
            "session_anchor": "overnight_to_pre_cash",
            "transition_window_bars": "pre_session_block",
            "regime_label": "state_shift_before_cash",
            "feature_family": "causal_regime_transition_context",
            "feature_scope": "overnight_range_gap_proxy_trend_and_volatility_state",
            "model_family": "small_mlp_secondary_only",
            "model_task": "state_shift_tradeability_rank",
            "decision_family": "diagnostic_tradeability_abstain",
            "holding_policy": "diagnostic_timeout_only_until_trade_surface_declared",
            "risk_policy": "diagnostic_no_position_until_decision_surface_declares_trade",
            "threshold_policy": "rank_only_no_probability_claim",
            "split_use": "train_validation_research_oos_a_no_locked_final",
            "purpose": "allow one secondary nonlinear scout for pre-cash state shift, with no superiority claim",
        },
        {
            "spec_id": "wave01_st_cell_007",
            "label_surface": "session_blind_control_same_horizon",
            "horizon_bars": 12,
            "session_anchor": "none_session_blind_control",
            "transition_window_bars": "none",
            "regime_label": "control_same_horizon",
            "feature_family": "price_return_range_volatility_context",
            "feature_scope": "same_price_range_inputs_without_session_state",
            "model_family": "logistic_or_linear_rank_scout",
            "model_task": "session_blind_control_event",
            "decision_family": "session_blind_abstain_timeout_exit",
            "holding_policy": "timeout_12",
            "risk_policy": "control_surface_still_requires_L4_if_valid_proxy_model_bearing",
            "threshold_policy": "train_only_control_density_bands",
            "split_use": "train_validation_research_oos_a_no_locked_final",
            "purpose": "control whether session features add meaning beyond price-only context",
        },
        {
            "spec_id": "wave01_st_cell_008",
            "label_surface": "range_expansion_continuation_vs_exhaustion",
            "horizon_bars": 3,
            "session_anchor": "active_cash_transition",
            "transition_window_bars": "post_expansion_1_to_6",
            "regime_label": "fast_expansion_continuation_or_exhaustion",
            "feature_family": "fast_transition_shock_context",
            "feature_scope": "short_horizon_return_range_shock_and_session_phase",
            "model_family": "logistic_or_linear_rank_scout",
            "model_task": "fast_continuation_exhaustion_classification",
            "decision_family": "fast_event_abstain_timeout_exit",
            "holding_policy": "very_short_timeout_3",
            "risk_policy": "spread_and_fill_timing_risk_declared_before_L4",
            "threshold_policy": "train_only_density_floor",
            "split_use": "train_validation_research_oos_a_no_locked_final",
            "purpose": "expose very short execution drift around transition shocks",
        },
        {
            "spec_id": "wave01_st_cell_009",
            "label_surface": "post_transition_range_acceptance",
            "horizon_bars": 18,
            "session_anchor": "post_cash_open",
            "transition_window_bars": "post_12_to_post_36",
            "regime_label": "range_acceptance_or_rejection",
            "feature_family": "range_acceptance_context",
            "feature_scope": "open_range_acceptance_rejection_distance_and_volatility",
            "model_family": "tree_or_boosted_onnx_feasible_scout",
            "model_task": "range_acceptance_rejection_bucket",
            "decision_family": "range_acceptance_abstain_timeout_exit",
            "holding_policy": "acceptance_or_timeout_18",
            "risk_policy": "range_distance_conversion_required_before_L4",
            "threshold_policy": "no_micro_search_before_repeated_clue",
            "split_use": "train_validation_research_oos_a_no_locked_final",
            "purpose": "test whether post-open range acceptance is a distinct surface",
        },
        {
            "spec_id": "wave01_st_cell_010",
            "label_surface": "session_transition_volatility_decay",
            "horizon_bars": 36,
            "session_anchor": "any_major_transition",
            "transition_window_bars": "post_transition_decay_block",
            "regime_label": "volatility_decay_or_persistence",
            "feature_family": "compression_expansion_causal_context",
            "feature_scope": "realized_volatility_decay_range_persistence_and_session_phase",
            "model_family": "logistic_or_linear_rank_scout",
            "model_task": "volatility_decay_tradeability_rank",
            "decision_family": "volatility_decay_no_trade_or_tradeability_gate",
            "holding_policy": "timeout_36_or_no_trade_filter",
            "risk_policy": "skip_or_timeout_semantics_required_before_L4",
            "threshold_policy": "rank_only_no_probability_claim",
            "split_use": "train_validation_research_oos_a_no_locked_final",
            "purpose": "capture transition after-effect as tradeability or no-trade state",
        },
    ]
    for row in rows:
        row["valid_proxy_model_bearing"] = True
        row["locked_final_oos_b_used"] = False
        row["auxiliary_symbols"] = "none"
        row["feature_count_policy"] = "variable_declared_per_run_no_fixed_count"
        row["runtime_level_required"] = "L4_split_runtime_probe"
    return rows


def validate_rows(rows: list[dict[str, Any]]) -> None:
    if len(rows) != 10:
        raise ValueError(f"expected 10 session-transition first-batch specs, got {len(rows)}")
    required_axes = [
        "label_surface",
        "feature_family",
        "model_family",
        "decision_family",
        "holding_policy",
        "session_anchor",
        "regime_label",
    ]
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


def write_matrix(repo_root: Path, rows: list[dict[str, Any]]) -> Path:
    fields = [
        "spec_id",
        "label_surface",
        "horizon_bars",
        "session_anchor",
        "transition_window_bars",
        "regime_label",
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
    path = repo_path(repo_root, PATHS["matrix"])
    write_csv_rows(path, fields, rows)
    return path


def planned_run_id(row: dict[str, Any]) -> str:
    return f"onnxlab_{row['spec_id']}_session_transition_surface_v0"


def write_run_specs_index(repo_root: Path, rows: list[dict[str, Any]]) -> tuple[Path, list[dict[str, Any]]]:
    index_rows: list[dict[str, Any]] = []
    for row in rows:
        run_id = planned_run_id(row)
        index_rows.append(
            {
                "spec_id": row["spec_id"],
                "planned_run_id": run_id,
                "status": "planned_not_executed",
                "spec_source": "first_batch_matrix_row",
                "matrix_path": PATHS["matrix"].as_posix(),
                "valid_proxy_model_bearing": "true",
                "runtime_level_required": "L4_split_runtime_probe",
                "claim_boundary": CLAIM_BOUNDARY,
                "next_action": NEXT_WORK_ITEM_ID,
            }
        )
    index_path = repo_path(repo_root, PATHS["run_specs_index"])
    write_csv_rows(
        index_path,
        [
            "spec_id",
            "planned_run_id",
            "status",
            "spec_source",
            "matrix_path",
            "valid_proxy_model_bearing",
            "runtime_level_required",
            "claim_boundary",
            "next_action",
        ],
        index_rows,
    )
    return index_path, index_rows


def write_run_refs(repo_root: Path, spec_rows: list[dict[str, Any]], created_at: str) -> Path:
    rows = [
        {
            "run_id": ref["planned_run_id"],
            "campaign_id": CAMPAIGN_ID,
            "surface_id": SURFACE_ID,
            "sweep_id": SWEEP_ID,
            "run_spec_id": ref["spec_id"],
            "status": "planned_not_executed",
            "spec_source": "first_batch_matrix_row",
            "matrix_path": PATHS["matrix"].as_posix(),
            "run_manifest_path": "",
            "receipt_path": "",
            "claim_boundary": CLAIM_BOUNDARY,
            "result_judgment": "not_evaluated",
            "next_action": NEXT_WORK_ITEM_ID,
            "created_at_utc": created_at,
            "notes": "planned session-transition run spec; no proxy execution yet",
        }
        for ref in spec_rows
    ]
    path = repo_path(repo_root, PATHS["run_refs"])
    write_csv_rows(
        path,
        [
            "run_id",
            "campaign_id",
            "surface_id",
            "sweep_id",
            "run_spec_id",
            "status",
            "spec_source",
            "matrix_path",
            "run_manifest_path",
            "receipt_path",
            "claim_boundary",
            "result_judgment",
            "next_action",
            "created_at_utc",
            "notes",
        ],
        rows,
    )
    return path


def write_anti_selection_ledger(repo_root: Path, rows: list[dict[str, Any]], outputs: dict[str, Path], created_at: str) -> Path:
    payload = {
        "version": "anti_selection_ledger_v1",
        "ledger_id": "anti_selection_wave01_session_transition_first_batch_v0",
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": created_at,
        "status": STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
        "selection_policy": {
            "selected_before_proxy_scores": True,
            "locked_final_oos_b_used": False,
            "feature_count_fixed": False,
            "model_head_fixed": False,
            "holding_duration_fixed": False,
            "threshold_optimized_for_pf": False,
            "auxiliary_symbols_used": False,
            "spec_count": len(rows),
        },
        "coverage_summary": {
            "label_surface_count": len({row["label_surface"] for row in rows}),
            "feature_family_count": len({row["feature_family"] for row in rows}),
            "model_family_count": len({row["model_family"] for row in rows}),
            "decision_family_count": len({row["decision_family"] for row in rows}),
            "session_anchor_count": len({row["session_anchor"] for row in rows}),
            "regime_label_count": len({row["regime_label"] for row in rows}),
            "multi_axis_discovery": True,
            "feature_only_or_label_only_or_model_only": False,
        },
        "anti_selection_rules": [
            "Do not drop weak-looking proxy specs before L4 unless invalid setup is recorded with try-first disposition.",
            "Do not add threshold micro-search before repeated surface clue exists.",
            "Do not use OOS-B for selection or adaptive repair.",
            "Do not convert a repair of score_band_side or momentum_ret_1 into a session-transition hypothesis.",
            "Proxy-bad/runtime-good and proxy-good/runtime-bad are parity evidence, not embarrassment to hide.",
        ],
        "evidence_paths": {key: rel(path, repo_root) for key, path in outputs.items()},
        "next_action": NEXT_WORK_ITEM_ID,
    }
    path = repo_path(repo_root, PATHS["anti_selection_ledger"])
    write_yaml(path, payload)
    return path


def write_first_batch_manifest(
    repo_root: Path,
    rows: list[dict[str, Any]],
    outputs: dict[str, Path],
    created_at: str,
) -> Path:
    payload = {
        "version": "first_batch_run_specs_manifest_v1",
        "manifest_id": "first_batch_run_specs_wave01_session_transition_v0",
        "active_goal_id": GOAL_ID,
        "wave_id": WAVE_ID,
        "campaign_id": CAMPAIGN_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": created_at,
        "status": STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
        "spec_count": len(rows),
        "coverage_summary": {
            "label_surface_count": len({row["label_surface"] for row in rows}),
            "feature_family_count": len({row["feature_family"] for row in rows}),
            "model_family_count": len({row["model_family"] for row in rows}),
            "decision_family_count": len({row["decision_family"] for row in rows}),
            "holding_policy_count": len({row["holding_policy"] for row in rows}),
            "session_anchor_count": len({row["session_anchor"] for row in rows}),
            "regime_label_count": len({row["regime_label"] for row in rows}),
            "multi_axis_discovery": True,
            "feature_only_or_label_only_or_model_only": False,
            "valid_proxy_model_bearing_specs_require_L4": True,
            "locked_final_oos_b_used": False,
            "auxiliary_symbols_used": False,
            "fixed_feature_count_used": False,
        },
        "source_inputs": {
            "campaign_manifest": artifact_identity(repo_path(repo_root, PATHS["campaign_manifest"]), repo_root),
            "surface_manifest": artifact_identity(repo_path(repo_root, PATHS["surface_manifest"]), repo_root),
            "sweep_manifest": artifact_identity(repo_path(repo_root, PATHS["sweep_manifest"]), repo_root),
            "recipes": recipe_identity(repo_root),
        },
        "outputs": {
            "first_batch_matrix": artifact_identity(outputs["matrix"], repo_root),
            "run_specs_index": artifact_identity(outputs["run_specs_index"], repo_root),
            "run_refs": artifact_identity(outputs["run_refs"], repo_root),
            "anti_selection_ledger": artifact_identity(outputs["anti_selection_ledger"], repo_root),
        },
        "spec_source_policy": {
            "source_of_truth": "first_batch_matrix_row",
            "run_specs_index_role": "compact_index_only",
            "per_run_manifest_creation": "defer_until_proxy_execution",
            "reason": "Avoid heavy pre-run generated YAML; execution creates run-local evidence when it becomes meaningful.",
        },
        "runtime_learning_probe_decision": {
            "required_for_valid_proxy_model_bearing_specs": True,
            "target_level": "L4_split_runtime_probe",
            "runtime_period_profile_id": RUNTIME_PERIOD_PROFILE_ID,
            "runtime_period_set_id": RUNTIME_PERIOD_SET_ID,
            "required_period_roles": ["validation", "research_oos"],
            "tester_execution_profile_id": TESTER_EXECUTION_PROFILE_ID,
            "proxy_only_closeout_allowed": False,
            "l4_promising_result_effect": "continue_to_L5_candidate_runtime_evidence",
        },
        "proxy_runtime_parity": {
            "required": True,
            "minimum_reconciliation_attempt": "required_after_first_proxy_runtime_difference",
            "forced_equality_required": False,
            "unit_semantics": "point_pip_tick_digits_price_distance_and_timeout_semantics_declared_per_run_before_L4",
            "prevention_memory": [
                "Session boundary and timeout differences are recorded, not hand-waved away.",
                "Missing adapter/glue triggers smallest repo-controlled repair attempt before blocked/deferred/invalid/discarded.",
            ],
        },
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "missing_evidence": [
            "proxy_runs_not_executed",
            "features_not_materialized",
            "labels_not_materialized",
            "models_not_trained",
            "ONNX_exports_not_materialized",
            "MT5_L4_not_run",
            "L5_not_applicable_until_L4_promising_result",
        ],
        "next_action": NEXT_WORK_ITEM_ID,
    }
    path = repo_path(repo_root, PATHS["first_batch_manifest"])
    write_yaml(path, payload)
    return path


def spec_summary(rows: list[dict[str, Any]], outputs: dict[str, Path], repo_root: Path) -> dict[str, Any]:
    return {
        "status": STATUS,
        "spec_count": len(rows),
        "matrix": rel(outputs["matrix"], repo_root),
        "run_specs_index": rel(outputs["run_specs_index"], repo_root),
        "run_refs": rel(outputs["run_refs"], repo_root),
        "manifest": rel(outputs["first_batch_manifest"], repo_root),
        "anti_selection_ledger": rel(outputs["anti_selection_ledger"], repo_root),
        "runtime_follow_through": "L4_required_for_all_valid_proxy_model_bearing_specs",
        "l4_promising_result_effect": "continue_to_L5_candidate_runtime_evidence",
        "claim_boundary": CLAIM_BOUNDARY,
    }


def update_yaml_records(repo_root: Path, created_at: str, outputs: dict[str, Path], rows: list[dict[str, Any]]) -> None:
    summary = spec_summary(rows, outputs, repo_root)

    campaign_path = repo_path(repo_root, PATHS["campaign_manifest"])
    campaign = read_yaml(campaign_path)
    campaign["status"] = STATUS
    campaign["updated_at_utc"] = created_at
    campaign["claim_boundary"] = CLAIM_BOUNDARY
    campaign["first_batch_specs"] = summary
    campaign["next_action"] = NEXT_WORK_ITEM_ID
    write_yaml(campaign_path, campaign)

    surface_path = repo_path(repo_root, PATHS["surface_manifest"])
    surface = read_yaml(surface_path)
    surface["status"] = STATUS
    surface["updated_at_utc"] = created_at
    surface["claim_boundary"] = CLAIM_BOUNDARY
    surface["first_batch_specs"] = summary
    surface["next_action"] = NEXT_WORK_ITEM_ID
    write_yaml(surface_path, surface)

    sweep_path = repo_path(repo_root, PATHS["sweep_manifest"])
    sweep = read_yaml(sweep_path)
    sweep["status"] = STATUS
    sweep["updated_at_utc"] = created_at
    sweep["evidence_boundary"] = "first_batch_specs_only_no_run_evidence"
    sweep["claim_boundary"] = CLAIM_BOUNDARY
    sweep["first_batch_specs"] = summary
    sweep["next_action"] = NEXT_WORK_ITEM_ID
    write_yaml(sweep_path, sweep)

    closeout = {
        "version": "work_closeout_v1",
        "work_item_id": WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "status": STATUS,
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
        "claim_limits": [
            "no_proxy_run",
            "no_model_training",
            "no_ONNX_export",
            "no_MT5_L4",
            "no_candidate",
            "no_runtime_authority",
            "no_economics_pass",
            "no_goal_achieve",
        ],
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "next_action": NEXT_WORK_ITEM_ID,
    }
    write_yaml(repo_path(repo_root, PATHS["closeout"]), closeout)

    update_wave_goal_workspace(repo_root, created_at, outputs, rows)


def update_wave_goal_workspace(repo_root: Path, created_at: str, outputs: dict[str, Path], rows: list[dict[str, Any]]) -> None:
    summary = spec_summary(rows, outputs, repo_root)

    wave_path = repo_path(repo_root, PATHS["wave_allocation"])
    wave = read_yaml(wave_path)
    wave["status"] = ACTIVE_PHASE
    wave["updated_at_utc"] = created_at
    wave["claim_boundary"] = WAVE_CLAIM
    wave["next_action"] = NEXT_WORK_ITEM_ID
    wave["next_action_detail"] = "Execute first broad proxy batch for the session-transition regime campaign, then force L4 follow-through."
    for allocation in wave.get("campaign_allocations") or []:
        if allocation.get("campaign_id") == CAMPAIGN_ID:
            allocation["status"] = STATUS
            allocation["claim_boundary"] = CLAIM_BOUNDARY
            allocation["first_batch_matrix"] = summary["matrix"]
            allocation["first_batch_run_specs_manifest"] = summary["manifest"]
            allocation["run_specs_index"] = summary["run_specs_index"]
            allocation["anti_selection_ledger"] = summary["anti_selection_ledger"]
            allocation["next_action"] = NEXT_WORK_ITEM_ID
    write_yaml(wave_path, wave)

    goal_path = repo_path(repo_root, PATHS["goal_manifest"])
    goal = read_yaml(goal_path)
    goal["updated_at_utc"] = created_at
    goal["claim_boundary"] = GOAL_CLAIM
    goal["active_phase"] = ACTIVE_PHASE
    goal["active_ids"] = {
        "idea_id": IDEA_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "wave_id": WAVE_ID,
        "campaign_id": CAMPAIGN_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
    }
    current_wave = goal.setdefault("program_budgets", {}).setdefault("current_wave0_spec", {})
    current_wave["status"] = ACTIVE_PHASE
    current_wave["session_transition_first_batch_manifest"] = summary["manifest"]
    current_wave["session_transition_run_specs_index"] = summary["run_specs_index"]
    current_wave["next_work_item"] = NEXT_WORK_ITEM_ID
    goal["session_transition_campaign"] = {
        "campaign_id": CAMPAIGN_ID,
        "status": STATUS,
        "campaign_manifest": rel(repo_path(repo_root, PATHS["campaign_manifest"]), repo_root),
        "surface_manifest": rel(repo_path(repo_root, PATHS["surface_manifest"]), repo_root),
        "sweep_manifest": rel(repo_path(repo_root, PATHS["sweep_manifest"]), repo_root),
        "first_batch_manifest": summary["manifest"],
        "run_specs_index": summary["run_specs_index"],
        "spec_count": len(rows),
        "runtime_follow_through": "L4_required_for_all_valid_proxy_model_bearing_specs",
        "claim_boundary": CLAIM_BOUNDARY,
        "next_work_item": NEXT_WORK_ITEM_ID,
    }
    goal["next_work_item"] = {
        "path": rel(repo_path(repo_root, PATHS["next_work_item"]), repo_root),
        "work_item_id": NEXT_WORK_ITEM_ID,
        "summary": "Execute first broad proxy batch for the Wave01 session-transition regime campaign.",
    }
    write_yaml(goal_path, goal)

    resume_path = repo_path(repo_root, PATHS["resume_cursor"])
    resume = read_yaml(resume_path)
    resume["updated_at_utc"] = created_at
    resume["active_phase"] = ACTIVE_PHASE
    resume["active_ids"] = goal["active_ids"]
    truth_sources = list(resume.get("current_truth_sources") or [])
    for path in [
        outputs["matrix"],
        outputs["run_specs_index"],
        outputs["run_refs"],
        outputs["first_batch_manifest"],
        outputs["anti_selection_ledger"],
        repo_path(repo_root, PATHS["closeout"]),
    ]:
        value = rel(path, repo_root)
        if value not in truth_sources:
            truth_sources.append(value)
    resume["current_truth_sources"] = truth_sources
    resume["latest_completed_work"] = {
        "work_item_id": WORK_ITEM_ID,
        "result_judgment": "planning_scaffold",
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_paths": [
            summary["manifest"],
            summary["matrix"],
            summary["run_specs_index"],
            summary["anti_selection_ledger"],
        ],
    }
    resume["next_work_item"] = {
        "work_item_id": NEXT_WORK_ITEM_ID,
        "path": rel(repo_path(repo_root, PATHS["next_work_item"]), repo_root),
    }
    write_yaml(resume_path, resume)

    workspace_path = repo_path(repo_root, PATHS["workspace_state"])
    workspace = read_yaml(workspace_path)
    workspace["updated_utc"] = created_at
    claims = workspace.setdefault("current_claims", {})
    claims.update(
        {
            "active_goal_phase": ACTIVE_PHASE,
            "active_goal_claim_boundary": GOAL_CLAIM,
            "active_campaign_id": CAMPAIGN_ID,
            "active_surface_id": SURFACE_ID,
            "active_sweep_id": SWEEP_ID,
            "next_work_item_id": NEXT_WORK_ITEM_ID,
            "wave0_third_campaign_status": STATUS,
            "wave0_third_campaign_manifest": rel(repo_path(repo_root, PATHS["campaign_manifest"]), repo_root),
            "wave0_third_campaign_surface": rel(repo_path(repo_root, PATHS["surface_manifest"]), repo_root),
            "wave0_third_campaign_sweep": rel(repo_path(repo_root, PATHS["sweep_manifest"]), repo_root),
            "wave0_third_campaign_first_batch_matrix": summary["matrix"],
            "wave0_third_campaign_run_specs_index": summary["run_specs_index"],
            "wave0_third_campaign_first_batch_manifest": summary["manifest"],
            "wave0_third_campaign_anti_selection_ledger": summary["anti_selection_ledger"],
            "wave0_third_campaign_planned_spec_count": len(rows),
            "wave0_third_campaign_claim_boundary": CLAIM_BOUNDARY,
            "wave0_third_campaign_next_work_item": NEXT_WORK_ITEM_ID,
        }
    )
    write_yaml(workspace_path, workspace)


def next_work_item_payload(
    repo_root: Path,
    created_at: str,
    outputs: dict[str, Path],
    rows: list[dict[str, Any]],
    command_argv: list[str],
    started_at: str,
    input_hashes: dict[str, str],
) -> dict[str, Any]:
    output_hashes = {
        "first_batch_manifest": sha256_file(outputs["first_batch_manifest"]),
        "first_batch_matrix": sha256_file(outputs["matrix"]),
        "run_specs_index": sha256_file(outputs["run_specs_index"]),
        "run_refs": sha256_file(outputs["run_refs"]),
        "anti_selection_ledger": sha256_file(outputs["anti_selection_ledger"]),
    }
    branch = git_value(repo_root, ["branch", "--show-current"])
    return {
        "version": "onnx_lab_work_item_v1",
        "work_item_id": NEXT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "created_at_utc": created_at,
        "status": "planned_not_started",
        "user_request": "Execute the first broad proxy batch for the session-transition regime campaign and keep all valid proxy/model-bearing specs on the L4 path.",
        "current_truth": {
            "first_batch_manifest": rel(outputs["first_batch_manifest"], repo_root),
            "first_batch_matrix": rel(outputs["matrix"], repo_root),
            "run_specs_index": rel(outputs["run_specs_index"], repo_root),
            "run_refs": rel(outputs["run_refs"], repo_root),
            "campaign_manifest": rel(repo_path(repo_root, PATHS["campaign_manifest"]), repo_root),
            "sweep_manifest": rel(repo_path(repo_root, PATHS["sweep_manifest"]), repo_root),
            "spec_count": len(rows),
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
            "skills_selected": [
                "spacesonar-model-validation",
                "spacesonar-experiment-design",
                "spacesonar-data-integrity",
                "spacesonar-run-evidence-system",
                "spacesonar-runtime-parity",
                "spacesonar-claim-discipline",
            ],
            "skills_not_used": ["spacesonar-reference-scout"],
            "critical_skills_not_selected": [],
            "not_selected_claim_effect": "no_external_api_or_version_sensitive_reference_needed_for_local_proxy_execution_plan",
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
        "branch_worktree": {
            "current_branch": branch,
            "requested_branch": EXPECTED_BRANCH,
            "branch_worktree_fit": "fit" if branch == EXPECTED_BRANCH else "mismatch_blocked",
            "branch_action": "keep_current_branch" if branch == EXPECTED_BRANCH else "stop_before_mutation",
            "policy_reference": "docs/policies/branch_policy.md",
            "mismatch_claim_effect": "no_reproducible_run_claim_if_branch_mismatch",
        },
        "agent_allocation": {
            "phase": "proxy_execution_preflight",
            "selected_agents": [],
            "role_modes": [],
            "selection_reason": "Task Force/sub-agent spawning is disabled; Codex uses selected skills, validators, and source-of-truth records.",
            "why_not_smaller": "Codex solo is the smallest active allocation.",
            "why_not_larger": "No sub-agent allocation is active under docs/policies/agent_allocation_policy.md.",
            "max_threads_is_capacity_only": True,
            "claim_effect": "solo_execution_only_no_task_force_review_claim",
        },
        "acceptance_criteria": [
            "Execute proxy/model-bearing specs without using locked final OOS-B.",
            "Create run-local manifest, receipt, lineage, and metrics for every executed meaningful run.",
            "Keep feature count variable per run; do not introduce inherited fixed feature defaults.",
            "Do not close any valid proxy/model-bearing run proxy-only.",
            "Materialize ONNX/EA/MT5 L4 path or record try-first failure disposition before invalid/block/defer/discard.",
            "Do not claim candidate, baseline, runtime authority, economics pass, or Goal Achieve.",
        ],
        "runtime_learning_probe_decision": {
            "required": True,
            "decision": "L4_required_after_valid_proxy_model_execution",
            "target_level": "L4_split_runtime_probe",
            "runtime_period_profile_id": RUNTIME_PERIOD_PROFILE_ID,
            "runtime_period_set_id": RUNTIME_PERIOD_SET_ID,
            "l4_promising_result_effect": "continue_to_L5_candidate_runtime_evidence",
        },
        "claim_boundary": "planned_proxy_execution_work_item_no_run_no_candidate_no_runtime_authority",
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "next_action": "build_or_run_session_transition_proxy_executor_then_L4_follow_through",
        "execution_provenance": {
            "git_sha": git_value(repo_root, ["rev-parse", "HEAD"]),
            "branch": branch,
            "dirty_flag": bool(git_status_lines(repo_root)),
            "changed_files": git_status_lines(repo_root),
            "command_argv": command_argv,
            "python_executable": sys.executable.replace(str(Path.home()), "${USERPROFILE}"),
            "python_version": sys.version.split()[0],
            "key_package_versions": key_package_versions(),
            "started_at_utc": started_at,
            "ended_at_utc": created_at,
            "input_hashes": input_hashes,
            "output_hashes": output_hashes,
            "unknown_git_claim_effect": "planning_scaffold_only_no_reproducible_run_or_goal_achieve_claim",
        },
    }


def update_csv_registries(repo_root: Path, outputs: dict[str, Path], rows: list[dict[str, Any]]) -> None:
    upsert_csv_row(
        repo_path(repo_root, PATHS["campaign_registry"]),
        "campaign_id",
        {
            "campaign_id": CAMPAIGN_ID,
            "status": STATUS,
            "created_at_utc": "2026-06-22T01:44:27Z",
            "campaign_path": rel(repo_path(repo_root, PATHS["campaign_manifest"]), repo_root),
            "objective": "Open US100 M5 session transition regime decision holding surface before micro search",
            "axis_tags": "session_transition_surface;target_or_label_surface;feature_or_input_surface;model_or_training_surface;decision_surface;regime_surface;horizon_or_holding_policy;evaluation_or_runtime_surface;us100_m5_closed_bar_only",
            "primary_family": "experiment_design",
            "primary_skill": "spacesonar-experiment-design",
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_path": rel(outputs["first_batch_manifest"], repo_root),
            "next_action": NEXT_WORK_ITEM_ID,
            "notes": "first broad session-transition specs materialized; no run/model/runtime claim",
        },
    )
    upsert_csv_row(
        repo_path(repo_root, PATHS["surface_registry"]),
        "surface_id",
        {
            "surface_id": SURFACE_ID,
            "hypothesis_id": HYPOTHESIS_ID,
            "status": STATUS,
            "created_at_utc": "2026-06-22T01:44:27Z",
            "surface_path": rel(repo_path(repo_root, PATHS["surface_manifest"]), repo_root),
            "label_recipe_id": "label_wave01_session_transition_regime_v0",
            "feature_recipe_id": "feature_wave01_us100_session_transition_regime_v0",
            "feature_recipe_mix_id": "not_applicable_no_mix_in_standard_campaign_open",
            "model_recipe_id": "model_wave01_session_transition_onnx_scout_v0",
            "decision_recipe_id": "decision_wave01_session_transition_abstain_v0",
            "split_recipe_id": "split_set_v0",
            "eval_recipe_id": "eval_wave01_session_transition_runtime_v0",
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_path": rel(outputs["first_batch_manifest"], repo_root),
            "next_action": NEXT_WORK_ITEM_ID,
            "notes": "first broad specs materialized; feature count remains variable per run",
        },
    )
    upsert_csv_row(
        repo_path(repo_root, PATHS["sweep_registry"]),
        "sweep_id",
        {
            "sweep_id": SWEEP_ID,
            "campaign_id": CAMPAIGN_ID,
            "surface_id": SURFACE_ID,
            "status": STATUS,
            "created_at_utc": "2026-06-22T01:44:27Z",
            "sweep_path": rel(repo_path(repo_root, PATHS["sweep_manifest"]), repo_root),
            "sweep_type": "broad_session_transition_regime_surface_scout",
            "axis_count": "7",
            "run_ref_path": rel(outputs["run_refs"], repo_root),
            "evidence_boundary": "first_batch_specs_only",
            "evidence_path": rel(outputs["first_batch_manifest"], repo_root),
            "next_action": NEXT_WORK_ITEM_ID,
            "notes": "run_refs now points to planned session-transition run specs; no executed run evidence yet",
        },
    )
    upsert_csv_row(
        repo_path(repo_root, PATHS["wave_registry"]),
        "wave_id",
        {
            "wave_id": WAVE_ID,
            "status": ACTIVE_PHASE,
            "created_at_utc": "2026-06-21T15:18:51Z",
            "wave_path": rel(repo_path(repo_root, PATHS["wave_allocation"]), repo_root),
            "allocation_goal": "Map US100 M5 closed-bar task label input decision and holding surfaces before optimization",
            "max_runs": "48",
            "claim_boundary": WAVE_CLAIM,
            "evidence_path": rel(outputs["first_batch_manifest"], repo_root),
            "next_action": NEXT_WORK_ITEM_ID,
            "notes": "third campaign first batch specs materialized; proxy execution next",
        },
    )
    upsert_csv_row(
        repo_path(repo_root, PATHS["goal_registry"]),
        "goal_id",
        {
            "goal_id": GOAL_ID,
            "status": "active_long_running",
            "created_at_utc": "2026-06-21T15:18:51Z",
            "goal_path": rel(repo_path(repo_root, PATHS["goal_manifest"]), repo_root),
            "terminal_contract_path": "lab/goals/goal_us100_onnx_forward_boundary_v0/terminal_eligibility_contract.yaml",
            "active_phase": ACTIVE_PHASE,
            "claim_boundary": GOAL_CLAIM,
            "next_work_item": NEXT_WORK_ITEM_ID,
            "notes": "session transition first batch specs materialized; durable Codex operation still active",
        },
    )
    upsert_csv_row(
        repo_path(repo_root, PATHS["campaign_refs"]),
        "campaign_id",
        {
            "wave_id": WAVE_ID,
            "campaign_id": CAMPAIGN_ID,
            "campaign_path": rel(repo_path(repo_root, PATHS["campaign_manifest"]), repo_root),
            "allocation_role": "third_unexplored_session_transition_regime_surface",
            "status": STATUS,
            "max_runs": "24",
            "initial_batch_size": str(len(rows)),
            "claim_boundary": CLAIM_BOUNDARY,
            "next_action": NEXT_WORK_ITEM_ID,
            "notes": "first broad session-transition specs materialized; no proxy execution yet",
        },
    )


def update_artifact_row(
    repo_root: Path,
    *,
    artifact_id: str,
    rel_path: Path,
    artifact_type: str,
    consumer: str,
    producer: str,
    claim_boundary: str,
    notes: str,
    source_of_truth: Path | None = None,
) -> None:
    full_path = repo_path(repo_root, rel_path)
    identity = artifact_identity(full_path, repo_root)
    upsert_csv_row(
        repo_path(repo_root, PATHS["artifact_registry"]),
        "artifact_id",
        {
            "artifact_id": artifact_id,
            "run_id": "",
            "bundle_id": "",
            "attempt_id": "",
            "artifact_type": artifact_type,
            "path_or_uri": identity["path"],
            "sha256": identity["sha256"],
            "size_bytes": str(identity["size_bytes"]),
            "availability": "present_hash_recorded",
            "producer_command": producer,
            "regeneration_command": producer,
            "source_of_truth": (source_of_truth or rel_path).as_posix(),
            "consumer": consumer,
            "claim_boundary": claim_boundary,
            "notes": notes,
        },
    )


def update_artifact_registry(repo_root: Path, outputs: dict[str, Path], producer: str) -> None:
    manifest_rel = PATHS["first_batch_manifest"]
    artifacts = [
        ("artifact_wave0_campaign_refs_v0", PATHS["campaign_refs"], "wave_campaign_refs", WAVE_ID, WAVE_CLAIM, "Wave campaign refs synchronized after session transition specs"),
        ("artifact_wave01_wave_allocation_v0", PATHS["wave_allocation"], "wave_allocation", WAVE_ID, WAVE_CLAIM, "Wave allocation synchronized after session transition specs"),
        ("artifact_wave01_session_transition_campaign_manifest_v0", PATHS["campaign_manifest"], "campaign_manifest", CAMPAIGN_ID, CLAIM_BOUNDARY, "Session transition campaign manifest after first batch specs"),
        ("artifact_wave01_session_transition_surface_manifest_v0", PATHS["surface_manifest"], "surface_manifest", SURFACE_ID, CLAIM_BOUNDARY, "Session transition surface manifest after first batch specs"),
        ("artifact_wave01_session_transition_sweep_manifest_v0", PATHS["sweep_manifest"], "sweep_manifest", SWEEP_ID, CLAIM_BOUNDARY, "Session transition sweep manifest after first batch specs"),
        ("artifact_wave01_session_transition_run_refs_v0", PATHS["run_refs"], "run_refs", SWEEP_ID, CLAIM_BOUNDARY, "Run refs populated with planned session-transition specs"),
        ("artifact_wave01_session_transition_first_batch_matrix_v0", PATHS["matrix"], "first_batch_matrix", CAMPAIGN_ID, CLAIM_BOUNDARY, "Session transition first batch matrix"),
        ("artifact_wave01_session_transition_run_specs_index_v0", PATHS["run_specs_index"], "run_specs_index", CAMPAIGN_ID, CLAIM_BOUNDARY, "Session transition planned run specs index"),
        ("artifact_wave01_session_transition_first_batch_manifest_v0", PATHS["first_batch_manifest"], "first_batch_manifest", CAMPAIGN_ID, CLAIM_BOUNDARY, "Session transition first batch source of truth"),
        ("artifact_wave01_session_transition_anti_selection_ledger_v0", PATHS["anti_selection_ledger"], "anti_selection_ledger", CAMPAIGN_ID, CLAIM_BOUNDARY, "Anti-selection ledger before proxy execution"),
        ("artifact_wave01_session_transition_first_batch_spec_closeout_v0", PATHS["closeout"], "work_closeout", WORK_ITEM_ID, CLAIM_BOUNDARY, "Work closeout for session transition first batch specs"),
    ]
    for artifact_id, rel_path, artifact_type, consumer, boundary, notes in artifacts:
        update_artifact_row(
            repo_root,
            artifact_id=artifact_id,
            rel_path=rel_path,
            artifact_type=artifact_type,
            consumer=consumer,
            producer=producer,
            claim_boundary=boundary,
            notes=notes,
            source_of_truth=manifest_rel if rel_path in {PATHS["matrix"], PATHS["run_specs_index"], PATHS["run_refs"], PATHS["anti_selection_ledger"], PATHS["closeout"]} else rel_path,
        )


def collect_input_hashes(repo_root: Path) -> dict[str, str]:
    keys = [
        "campaign_manifest",
        "surface_manifest",
        "sweep_manifest",
        "feature_recipe",
        "label_recipe",
        "model_recipe",
        "decision_recipe",
        "eval_recipe",
        "surface_contract",
        "runtime_contract",
        "runtime_period_profile",
        "tester_execution_profile",
    ]
    return {key: sha256_file(repo_path(repo_root, PATHS[key])) for key in keys}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize Wave01 session-transition first batch specs.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--created-at-utc", default=None)
    parser.add_argument("--write-control-records", action="store_true")
    parser.add_argument("--expected-branch", default=EXPECTED_BRANCH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _repo_root = Path(args.repo_root).resolve()
    print(
        "historical lifecycle entrypoint disabled by WP04; use python -m spacesonar.cli campaign materialize --campaign-id <id>",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
