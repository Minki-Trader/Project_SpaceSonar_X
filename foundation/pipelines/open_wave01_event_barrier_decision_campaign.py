from __future__ import annotations

import argparse
import csv
import hashlib
import subprocess
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]

GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WAVE_ID = "wave_us100_closedbar_surface_cartography_v0"
OLD_CAMPAIGN_ID = "campaign_us100_task_surface_scout_v0"
OLD_IDEA_ID = "idea_us100_m5_blank_slate_surface_map_v0"
NEW_CAMPAIGN_ID = "campaign_us100_event_barrier_decision_surface_v0"
IDEA_ID = "idea_us100_m5_event_barrier_decision_surface_v0"
HYPOTHESIS_ID = "hyp_us100_event_barrier_decision_surface_v0"
SURFACE_ID = "surface_us100_event_barrier_decision_surface_v0"
SWEEP_ID = "sweep_us100_event_barrier_broad_v0"
OPEN_WORK_ID = "work_wave01_open_event_barrier_decision_campaign_v0"
NEXT_WORK_ID = "work_wave01_event_barrier_first_batch_spec_v0"

OLD_CAMPAIGN_PATH = Path("lab/campaigns") / OLD_CAMPAIGN_ID / "campaign_manifest.yaml"
NEW_CAMPAIGN_PATH = Path("lab/campaigns") / NEW_CAMPAIGN_ID / "campaign_manifest.yaml"
NEW_SWEEP_PATH = Path("lab/campaigns") / NEW_CAMPAIGN_ID / "sweeps" / SWEEP_ID / "sweep_manifest.yaml"
NEW_RUN_REFS_PATH = Path("lab/campaigns") / NEW_CAMPAIGN_ID / "sweeps" / SWEEP_ID / "run_refs.csv"
NEW_SURFACE_PATH = Path("lab/surfaces") / SURFACE_ID / "surface_manifest.yaml"
NEW_IDEA_PATH = Path("lab/hypotheses") / f"{IDEA_ID}.yaml"
NEW_HYPOTHESIS_PATH = Path("lab/hypotheses") / f"{HYPOTHESIS_ID}.yaml"
WAVE_ALLOCATION_PATH = Path("lab/waves") / WAVE_ID / "wave_allocation.yaml"
CAMPAIGN_REFS_PATH = Path("lab/waves") / WAVE_ID / "campaign_refs.csv"
GOAL_MANIFEST_PATH = Path("lab/goals") / GOAL_ID / "goal_manifest.yaml"
NEXT_WORK_ITEM_PATH = Path("lab/goals") / GOAL_ID / "next_work_item.yaml"
RESUME_CURSOR_PATH = Path("lab/goals") / GOAL_ID / "resume_cursor.yaml"
CLOSEOUT_PATH = Path("lab/goals") / GOAL_ID / f"{OPEN_WORK_ID}_closeout.yaml"
WORKSPACE_STATE_PATH = Path("docs/workspace/workspace_state.yaml")

FEATURE_RECIPE_ID = "feature_wave01_us100_price_session_regime_flexible_v0"
LABEL_RECIPE_ID = "label_wave01_event_barrier_path_v0"
MODEL_RECIPE_ID = "model_wave01_onnx_feasible_scout_v0"
DECISION_RECIPE_ID = "decision_wave01_barrier_abstain_risk_v0"
EVAL_RECIPE_ID = "eval_wave01_event_barrier_runtime_v0"
SURFACE_CONTRACT_ID = SURFACE_ID

RECIPE_PATHS = {
    FEATURE_RECIPE_ID: Path("configs/onnx_lab/feature_recipes") / f"{FEATURE_RECIPE_ID}.yaml",
    LABEL_RECIPE_ID: Path("configs/onnx_lab/label_recipes") / f"{LABEL_RECIPE_ID}.yaml",
    MODEL_RECIPE_ID: Path("configs/onnx_lab/model_recipes") / f"{MODEL_RECIPE_ID}.yaml",
    DECISION_RECIPE_ID: Path("configs/onnx_lab/decision_recipes") / f"{DECISION_RECIPE_ID}.yaml",
    EVAL_RECIPE_ID: Path("configs/onnx_lab/eval_recipes") / f"{EVAL_RECIPE_ID}.yaml",
    SURFACE_CONTRACT_ID: Path("configs/onnx_lab/surface_contracts") / f"{SURFACE_CONTRACT_ID}.yaml",
}

REGISTRY_PATHS = {
    "campaign": Path("docs/registers/campaign_registry.csv"),
    "idea": Path("docs/registers/idea_registry.csv"),
    "hypothesis": Path("docs/registers/hypothesis_registry.csv"),
    "sweep": Path("docs/registers/sweep_registry.csv"),
    "surface": Path("docs/registers/experiment_surface_registry.csv"),
    "recipe": Path("docs/registers/recipe_index.csv"),
    "wave": Path("docs/registers/wave_registry.csv"),
    "goal": Path("docs/registers/goal_registry.csv"),
    "artifact": Path("docs/registers/artifact_registry.csv"),
}

FIRST_CAMPAIGN_CLOSED_STATUS = "decision_replay_judgment_closed_no_candidate"
NEW_CAMPAIGN_STATUS = "opened_planned_not_executed"
CLAIM_BOUNDARY = "campaign_open_planning_scaffold_no_model_run_no_candidate_no_runtime_authority"
OLD_CLOSEOUT_BOUNDARY = (
    "decision_replay_judgment_log_balance_only_no_runtime_authority_no_economics_pass_no_candidate"
)


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: object) -> bool:
        return True


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a mapping")
    return payload


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        yaml.dump(payload, handle, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=False)


def detect_lineterminator(path: Path) -> str:
    return "\n"


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    terminator = detect_lineterminator(path)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator=terminator)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def upsert_csv_row(path: Path, key: str, row: dict[str, str]) -> None:
    fieldnames, rows = read_csv_rows(path)
    for field in row:
        if field not in fieldnames:
            fieldnames.append(field)
    replaced = False
    for index, existing in enumerate(rows):
        if existing.get(key) == row[key]:
            merged = dict(existing)
            merged.update(row)
            rows[index] = merged
            replaced = True
            break
    if not replaced:
        rows.append(row)
    write_csv_rows(path, fieldnames, rows)


def write_empty_run_refs(path: Path) -> None:
    fieldnames = [
        "run_id",
        "campaign_id",
        "surface_id",
        "sweep_id",
        "status",
        "run_manifest_path",
        "receipt_path",
        "claim_boundary",
        "next_action",
        "notes",
    ]
    write_csv_rows(path, fieldnames, [])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_value(repo_root: Path, args: list[str]) -> str:
    result = subprocess.run(["git", *args], cwd=repo_root, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip() or "unknown"


def git_changed_files(repo_root: Path) -> list[str]:
    result = subprocess.run(["git", "status", "--short"], cwd=repo_root, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return ["unknown"]
    return [line for line in result.stdout.splitlines() if line.strip()]


def now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def campaign_manifest(created_at: str, branch: str) -> dict[str, Any]:
    return {
        "version": "campaign_manifest_v1",
        "campaign_id": NEW_CAMPAIGN_ID,
        "campaign_type": "standard_experiment",
        "active_goal_id": GOAL_ID,
        "status": NEW_CAMPAIGN_STATUS,
        "created_at_utc": created_at,
        "updated_at_utc": created_at,
        "target_branch": branch,
        "wave_ids": [WAVE_ID],
        "idea_ids": [IDEA_ID],
        "hypothesis_ids": [HYPOTHESIS_ID],
        "objective": (
            "Open a new US100 M5 event/barrier decision surface that treats label, input, model, "
            "decision, risk, holding, and runtime feasibility as interacting axes."
        ),
        "axis_tags": [
            "event_barrier_surface",
            "target_or_label_surface",
            "feature_or_input_surface",
            "model_or_training_surface",
            "decision_surface",
            "risk_or_sizing_surface",
            "horizon_or_holding_policy",
            "evaluation_or_runtime_surface",
            "us100_m5_closed_bar_only",
        ],
        "surface_policy": "broad_first_extreme_edges_before_micro_search",
        "exploration_coverage": {
            "mode": "unexplored_surface_discovery_not_single_axis_progression",
            "primary_unknown_axis": "event_barrier_decision_risk_holding_surface",
            "required_research_axes": [
                "target_or_label_surface",
                "feature_or_input_surface",
                "model_or_training_surface",
            ],
            "companion_axes": [
                "decision_surface",
                "horizon_or_holding_policy",
                "evaluation_or_runtime_surface",
            ],
            "forbidden_research_shapes": [
                "feature_only_wave_or_campaign",
                "label_only_wave_or_campaign",
                "model_only_wave_or_campaign",
                "threshold_only_wave_or_campaign",
                "repair_only_wave_or_campaign",
            ],
            "single_axis_exception_policy": "not_applicable_research_campaign",
            "novelty_claim": (
                "new event/barrier and path-quality decision surface after the first campaign closed "
                "naive momentum_ret_1 score replay as negative memory"
            ),
        },
        "prior_material_boundary": {
            "uses_prior_material_as": "prevention_boundary_only",
            "source_negative_memory_ids": ["neg_wave0_decision_replay_momentum_ret_1_loss_v0"],
            "forbidden_carryover": [
                "do_not_relabel_momentum_ret_1_score_replay_as_new_candidate",
                "do_not_use_preserved_score_clue_as_tradeability_without_new_decision_policy_evidence",
            ],
            "new_surface_requirement": (
                "new runs must change the event/barrier, risk, holding, or decision policy surface; "
                "not just repair the prior score replay candidate"
            ),
        },
        "bounded_synthesis": {
            "enabled": False,
            "source_scope": "not_applicable_standard_experiment",
            "next_wave_influence": "not_applicable",
            "claim_boundary": "not_bounded_synthesis_no_previous_material_mixing_claim",
        },
        "candidate_repair_policy": {
            "allowed_scope": "bounded_run_or_sweep_only",
            "max_repeated_candidate_repairs_without_new_surface_clue": 1,
            "repeated_repair_action": "close_or_open_new_surface_or_divergence_campaign",
            "forbidden_use": "long_candidate_extension_inside_wave_or_campaign",
            "carryover_policy": "forbidden_to_relabel_repair_as_new_hypothesis_without_recorded_new_surface_or_divergence",
            "neighborhood_perturbation_scope": "meaningful_adjacent_variables_only",
            "neighborhood_stop_condition": "stop_when_micro_tuning_candidate_laundering_or_no_new_prevention_memory",
        },
        "failure_disposition_policy": {
            "cannot_unsupported_unavailable_are_diagnosis_only": True,
            "explanation_only_closeout_forbidden": True,
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
        "storage_contract": {
            "source_of_truth": NEW_CAMPAIGN_PATH.as_posix(),
            "wave_campaign_refs": [CAMPAIGN_REFS_PATH.as_posix()],
            "registry_rows": [REGISTRY_PATHS["campaign"].as_posix()],
            "durable_identity_policy": "repo_relative_paths_only",
            "wave_link_policy": "central_campaign_folder_referenced_by_wave_allocation",
        },
        "git_integration": {
            "policy_reference": "docs/policies/branch_policy.md",
            "open_event": "campaign_open",
            "close_event": "campaign_close",
            "main_push_policy": "boundary_only_after_coherent_commit",
            "per_run_main_push_default": False,
            "status": "branch_open_pending_main_boundary",
        },
        "skill_routing": {
            "primary_family": "experiment_design",
            "primary_skill": "spacesonar-experiment-design",
            "support_skills": [
                "spacesonar-exploration-mandate",
                "spacesonar-data-integrity",
                "spacesonar-model-validation",
                "spacesonar-run-evidence-system",
                "spacesonar-claim-discipline",
            ],
        },
        "required_gates": [
            "design_contract_check",
            "exploration_coverage_check",
            "campaign_proxy_runtime_parity_policy",
            "first_batch_spec_before_execution",
            "final_claim_guard",
        ],
        "claim_boundary": CLAIM_BOUNDARY,
        "forbidden_claims": [
            "selected_baseline",
            "operating_reference",
            "runtime_authority",
            "economics_pass",
            "materialization_ready",
            "handoff_complete",
            "live_readiness",
            "reviewed_verified_pass",
            "goal_achieve",
        ],
        "experiment_design": {
            "idea_id": IDEA_ID,
            "hypothesis_id": HYPOTHESIS_ID,
            "surface_id": SURFACE_ID,
            "sweep_id": SWEEP_ID,
            "hypothesis": (
                "Event/barrier labels paired with explicit path-quality and risk/holding decisions may "
                "separate tradeable US100 M5 states better than replaying prior score clues through a "
                "naive momentum direction policy."
            ),
            "decision_use": "abstain_capable_event_barrier_entry_exit_risk_surface",
            "comparison_baseline": [
                "no_trade_baseline",
                "same_direction_disabled_baseline",
                "permuted_label_or_time_shift_check_when_executable",
                "naive_momentum_ret_1_is_negative_memory_only_not_candidate_baseline",
            ],
            "control_variables": [
                "FPMarkets_US100_M5_closed_bar_base_frame",
                "us100_bar_close_time_row_key",
                "split_set_v0_research_catalog",
                "locked_final_oos_b_forbidden",
                "no_auxiliary_symbols",
                "0.02_lot_tester_default_when_strategy_tester_runs_are_needed",
            ],
            "changed_variables": [
                "barrier_definition",
                "path_quality_label",
                "timeout_or_holding_policy",
                "abstain_or_no_trade_zone",
                "risk_distance_unit_semantics",
                "simple_onnx_feasible_model_family",
            ],
            "sample_scope": "clean_universe_split_set_v0_validation_and_research_oos_before_locked_final",
            "success_criteria": [
                "repeated_surface_clue_across_barrier_or_holding_neighbors",
                "trade_density_visible_without_threshold_knife_edge",
                "unit_semantics_are_declared_before_MT5_L4",
                "candidate_not_claimed_without_L4",
            ],
            "failure_criteria": [
                "loss_or_no_trade_under_both_validation_and_research_oos_L4",
                "signal_depends_on_one_short_regime",
                "risk_distance_or_barrier_units_do_not_translate_after_repair_attempt",
                "threshold_knife_edge",
            ],
            "invalid_conditions": [
                "feature_or_label_leakage",
                "locked_final_oos_b_used",
                "auxiliary_symbol_input_used_without_live_chart_evidence",
                "missing_MT5_executable_path_after_try_first_repair_attempt",
            ],
            "stop_conditions": [
                "first_batch_spec_ready",
                "all_valid_proxy_model_runs_reach_L4_or_record_failure_disposition",
                "no_repeated_surface_clue_after_broad_batch_close_as_negative_or_inconclusive",
            ],
            "evidence_plan": [
                NEW_CAMPAIGN_PATH.as_posix(),
                NEW_SURFACE_PATH.as_posix(),
                NEW_SWEEP_PATH.as_posix(),
                NEW_RUN_REFS_PATH.as_posix(),
                *[path.as_posix() for path in RECIPE_PATHS.values()],
            ],
        },
        "recipe_refs": {
            "feature_recipe_id": FEATURE_RECIPE_ID,
            "label_recipe_id": LABEL_RECIPE_ID,
            "model_recipe_id": MODEL_RECIPE_ID,
            "decision_recipe_id": DECISION_RECIPE_ID,
            "eval_recipe_id": EVAL_RECIPE_ID,
            "surface_contract_id": SURFACE_CONTRACT_ID,
        },
        "dataset_identity": {
            "reuse_allowed_as": "same_base_US100_M5_closed_bar_dataset_identity",
            "dataset_id": "dataset_raw_us100_m5_wave0_export_20260621T152827Z",
            "source_of_truth": "lab/campaigns/campaign_us100_task_surface_scout_v0/dataset_identity.yaml",
            "row_membership_manifest": "lab/campaigns/campaign_us100_task_surface_scout_v0/row_membership/row_membership_manifest.yaml",
            "claim_boundary": "base_dataset_identity_only_no_feature_or_label_default",
        },
        "runtime_learning_probe_decision_default": {
            "required_for_valid_proxy_model_bearing_runs": True,
            "target_level": "L4_split_runtime_probe",
            "decision": "required_after_first_batch_proxy_model_bearing_specs_execute",
            "reason": "Project policy requires L4 for every valid proxy/model-bearing run.",
            "l4_promising_result_effect": "continue_to_L5_candidate_runtime_evidence",
        },
        "proxy_runtime_parity": {
            "required_for_proxy_model_bearing_runs": True,
            "status": "planned_before_first_batch",
            "shared_contract": [
                "FPMarkets_US100_M5_closed_bar_base_frame",
                "us100_bar_close_time_row_key",
                "split_set_v0_research_catalog",
                "declared_event_barrier_label_per_run",
                "declared_feature_order_per_run",
                "declared_decision_and_holding_policy_per_run",
                "tester_execution_profile_us100_m5_fpmarkets_tester_execution_v0",
            ],
            "known_differences": [
                "proxy_event_barrier_simulation_may_not_equal_MT5_fill_and_stop_execution",
                "tester_report_and_equity_parser_required_before_economics_claim",
                "risk_distance_units_must_be_converted_through_point_digits_tick_size_before_MT5",
            ],
            "interpretation_drift_risks": [
                "bar_close_timing",
                "barrier_touch_order_inside_bar",
                "spread_and_fill_timing",
                "price_distance_unit_conversion",
                "lot_step_rounding",
                "timeout_close_timing",
                "no_trade_or_abstain_semantics",
            ],
            "minimum_reconciliation_attempt": {
                "required": True,
                "status": "pending_first_proxy_runtime_difference",
                "forced_equality_required": False,
                "note": "Repair or explain at least one proxy-vs-MT5 semantic difference before closure.",
            },
            "unit_semantics": {
                "point": "must_record_before_MT5_L4_if_distance_used",
                "pip": "not_assumed",
                "tick_size": "must_record_before_MT5_L4_if_distance_used",
                "digits": "must_record_before_MT5_L4_if_distance_used",
                "price_distance": "explicit_conversion_required",
                "atr_multiplier": "allowed_only_with_conversion_rule",
                "lot_step": "tester_profile_default_until_run_specific",
                "rounding_policy": "explicit_per_run_before_MT5_L4",
            },
            "comparison_classes": [
                "proxy_good_runtime_good",
                "proxy_good_runtime_bad",
                "proxy_bad_runtime_bad",
                "proxy_bad_runtime_good",
                "invalid_or_unmaterializable",
            ],
            "divergence_judgment": "pending_first_L4",
            "prevention_memory": [
                "do_not_reuse_momentum_ret_1_score_replay_negative_memory_as_candidate",
                "record_price_distance_unit_conversion_before_reusing_barrier_or_ATR_stop_logic",
            ],
            "follow_up_action": NEXT_WORK_ID,
            "claim_boundary": "campaign_parity_tracking_only_no_runtime_authority",
        },
        "next_action": NEXT_WORK_ID,
        "notes": (
            "Campaign opened as a new multi-axis surface, not bounded synthesis and not a repair continuation. "
            "No runs, models, candidates, economics, runtime authority, or Goal Achieve claim."
        ),
    }


def surface_manifest(created_at: str) -> dict[str, Any]:
    return {
        "version": "surface_manifest_v1",
        "surface_id": SURFACE_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "status": NEW_CAMPAIGN_STATUS,
        "created_at_utc": created_at,
        "inheritance_policy": "no_prior_feature_label_target_model_or_runtime_defaults",
        "problem_shape": {
            "input_surface": "US100_M5_closed_bar_price_session_regime_flexible_features",
            "target_or_label_surface": "event_barrier_path_quality_timeout_surface",
            "decision_use": "abstain_capable_entry_exit_risk_holding_decision",
            "holding_logic": "timeout_or_barrier_exit_declared_per_run",
            "evaluation_method": "split_set_v0_validation_research_oos_then_L4_for_valid_proxy_model_runs",
        },
        "recipe_refs": {
            "data_surface_id": "dataset_raw_us100_m5_wave0_export_20260621T152827Z",
            "label_recipe_id": LABEL_RECIPE_ID,
            "feature_recipe_id": FEATURE_RECIPE_ID,
            "feature_recipe_mix_id": "not_applicable_no_mix_in_standard_campaign_open",
            "model_recipe_id": MODEL_RECIPE_ID,
            "decision_recipe_id": DECISION_RECIPE_ID,
            "split_recipe_id": "split_set_v0",
            "eval_recipe_id": EVAL_RECIPE_ID,
        },
        "data_contract": {
            "symbol_contract": "FPMarkets_US100_M5_closed_bar_only",
            "timeframe": "M5",
            "row_key": "us100_bar_close_time",
            "timezone_or_session_policy": "inherit_split_set_v0_research_binding_no_utc_claim",
            "feature_boundary": "causal_history_only_declared_per_run",
            "label_boundary": "future_event_barrier_with_tail_drop_and_split_boundary_check",
            "leakage_boundary": "same_role_future_rows_only_no_locked_final_for_selection",
            "missing_gap_policy": "use_existing_row_membership_exclusions",
        },
        "storage_contract": {
            "source_of_truth": NEW_SURFACE_PATH.as_posix(),
            "registry_rows": [REGISTRY_PATHS["surface"].as_posix()],
            "durable_identity_policy": "repo_relative_paths_only",
        },
        "runtime_level_target": "L4_split_runtime_probe_for_valid_proxy_model_runs",
        "runtime_learning_probe_decision": {
            "required": True,
            "decision": "required_after_valid_proxy_model_run",
            "reason": "Every valid proxy/model-bearing surface must reach L4 or record failure disposition.",
        },
        "claim_boundary": CLAIM_BOUNDARY,
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
        "known_differences": [
            "event_barrier_proxy_touch_order_may_differ_from_MT5_execution",
            "price_distance_units_require_MT5_symbol_contract_conversion",
        ],
        "notes": "Surface open only; feature count, label thresholds, model family, and output head are not fixed.",
    }


def sweep_manifest(created_at: str) -> dict[str, Any]:
    return {
        "version": "sweep_manifest_v1",
        "sweep_id": SWEEP_ID,
        "campaign_id": NEW_CAMPAIGN_ID,
        "surface_id": SURFACE_ID,
        "status": "planned_not_executed",
        "created_at_utc": created_at,
        "sweep_type": "broad_event_barrier_surface_scout",
        "axes": [
            "event_barrier_label",
            "path_quality_or_mfe_mae",
            "feature_input_family",
            "onnx_feasible_model_family",
            "decision_abstain_risk_holding_policy",
            "runtime_parity_unit_semantics",
        ],
        "fixed_controls": [
            "US100_M5_closed_bar",
            "split_set_v0",
            "locked_final_oos_b_forbidden",
            "no_auxiliary_symbols",
            "0.02_lot_default_when_MT5_strategy_tester_runs_execute",
        ],
        "parameter_space": {
            "label_surface": [
                "up_down_barrier_touch_or_timeout",
                "mfe_mae_path_quality",
                "time_to_event_or_no_touch",
            ],
            "feature_surface": [
                "price_return_range_volatility_context",
                "session_state_context",
                "causal_regime_context",
            ],
            "model_surface": [
                "logistic_or_linear_rank_scout",
                "tree_or_boosted_onnx_feasible_scout",
                "small_mlp_secondary_only_if_first_batch_needs_it",
            ],
            "decision_surface": [
                "abstain_band",
                "barrier_exit",
                "timeout_exit",
                "risk_distance_conversion_required",
            ],
        },
        "run_ref_path": NEW_RUN_REFS_PATH.as_posix(),
        "storage_contract": {
            "source_of_truth": NEW_SWEEP_PATH.as_posix(),
            "registry_rows": [REGISTRY_PATHS["sweep"].as_posix()],
            "durable_identity_policy": "repo_relative_paths_only",
        },
        "runtime_learning_probe_decision": {
            "required": True,
            "decision": "L4_required_for_each_valid_proxy_model_bearing_run",
            "reason": "Proxy-only closure is forbidden for valid proxy/model-bearing runs.",
        },
        "failure_disposition": {
            "required_before_blocked_deferred_invalid_or_discarded": True,
            "status": "not_applicable_at_campaign_open",
            "failure_reproduction": None,
            "exact_failing_layer": None,
            "root_cause_hypothesis": None,
            "repair_or_fallback_attempts": [],
            "attempt_blocker_if_no_repair": None,
            "evidence_paths": [],
            "remaining_blocker": None,
            "reopen_condition": None,
            "claim_effect": "lower_to_investigation_in_progress_until_recorded",
        },
        "evidence_boundary": "planned_sweep_only_no_run_evidence",
        "required_gates": [
            "first_batch_spec_created_before_execution",
            "proxy_runtime_parity_policy_declared",
            "final_claim_guard",
        ],
        "stop_conditions": [
            "first_batch_spec_ready",
            "valid_proxy_model_run_without_L4_is_invalid_closeout",
            "candidate_claim_attempted_without_L4_or_L5_evidence",
        ],
        "notes": "The sweep is open with zero executed runs; run_refs.csv is an empty index until specs are materialized.",
    }


def idea_manifest(created_at: str) -> dict[str, Any]:
    return {
        "version": "idea_manifest_v1",
        "idea_id": IDEA_ID,
        "status": NEW_CAMPAIGN_STATUS,
        "created_at_utc": created_at,
        "axis_tags": [
            "event_barrier_surface",
            "decision_surface",
            "risk_or_holding_policy",
            "us100_m5_only",
        ],
        "claim_boundary": CLAIM_BOUNDARY,
        "legacy_relation": "none",
        "prior_material_use": "negative_memory_prevention_boundary_only",
        "evidence_path": NEW_CAMPAIGN_PATH.as_posix(),
        "next_action": NEXT_WORK_ID,
        "notes": "New blank-slate surface; not a continuation of the first campaign momentum_ret_1 decision replay.",
    }


def hypothesis_manifest(created_at: str) -> dict[str, Any]:
    return {
        "version": "hypothesis_manifest_v1",
        "hypothesis_id": HYPOTHESIS_ID,
        "idea_id": IDEA_ID,
        "status": NEW_CAMPAIGN_STATUS,
        "created_at_utc": created_at,
        "hypothesis": (
            "Event/barrier path labels plus explicit decision/risk/holding logic may expose a tradeable "
            "surface that naive score replay could not."
        ),
        "decision_use": "abstain_capable_event_barrier_entry_exit_risk_surface",
        "comparison_baseline": "no_trade_permuted_label_and_negative_memory_momentum_ret_1_reference_only",
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_path": NEW_CAMPAIGN_PATH.as_posix(),
        "next_action": NEXT_WORK_ID,
        "notes": "Hypothesis open only; no feature count, model head, direction mapping, or holding duration is fixed.",
    }


def recipe_payloads(created_at: str) -> dict[str, dict[str, Any]]:
    return {
        FEATURE_RECIPE_ID: {
            "version": "feature_recipe_v1",
            "recipe_id": FEATURE_RECIPE_ID,
            "status": "skeleton_open_no_feature_set_claim",
            "created_at_utc": created_at,
            "feature_count_policy": "variable_declared_per_run_no_fixed_count",
            "forbidden_defaults": [
                "fixed_feature_count",
                "inherited_feature_list",
                "auxiliary_symbol_without_live_chart_evidence",
            ],
            "allowed_families": [
                "price_return_range_volatility_context",
                "session_state_context",
                "causal_regime_context",
            ],
            "boundary": "causal_history_only",
            "claim_boundary": "recipe_skeleton_only_not_feature_set_not_candidate",
        },
        LABEL_RECIPE_ID: {
            "version": "label_recipe_v1",
            "recipe_id": LABEL_RECIPE_ID,
            "status": "skeleton_open_no_target_claim",
            "created_at_utc": created_at,
            "label_family": "event_barrier_path_quality_timeout",
            "tail_drop_policy": "required_per_horizon_or_barrier_timeout",
            "purge_embargo_policy": "evaluate_before_model_selection",
            "forbidden_defaults": [
                "fixed_holding_period",
                "inherited_direction_mapping",
                "locked_final_oos_selection",
            ],
            "claim_boundary": "recipe_skeleton_only_no_default_target_no_direction_mapping",
        },
        MODEL_RECIPE_ID: {
            "version": "model_recipe_v1",
            "recipe_id": MODEL_RECIPE_ID,
            "status": "skeleton_open_no_model_superiority_claim",
            "created_at_utc": created_at,
            "model_family_policy": "onnx_feasible_scout_models_only_until_repeated_surface_clue",
            "allowed_families": [
                "logistic_or_linear_rank_scout",
                "tree_or_boosted_onnx_feasible_scout",
                "small_mlp_secondary_only",
            ],
            "forbidden_actions": [
                "hyperparameter_micro_search_before_broad_clue",
                "candidate_claim_without_L4",
                "locked_final_oos_selection",
            ],
            "claim_boundary": "recipe_skeleton_only_no_model_candidate",
        },
        DECISION_RECIPE_ID: {
            "version": "decision_recipe_v1",
            "recipe_id": DECISION_RECIPE_ID,
            "status": "skeleton_open_no_runtime_claim",
            "created_at_utc": created_at,
            "decision_family": "event_barrier_abstain_risk_holding_surface",
            "unit_semantics_required": [
                "point",
                "digits",
                "tick_size",
                "price_distance",
                "lot_step",
                "rounding_policy",
            ],
            "forbidden_defaults": [
                "naive_momentum_ret_1_score_replay_as_candidate",
                "ATR_or_barrier_distance_without_conversion_rule",
            ],
            "claim_boundary": "recipe_skeleton_only_no_runtime_or_economics_claim",
        },
        EVAL_RECIPE_ID: {
            "version": "eval_recipe_v1",
            "recipe_id": EVAL_RECIPE_ID,
            "status": "skeleton_open_L4_required_for_valid_proxy_model_runs",
            "created_at_utc": created_at,
            "split_recipe_id": "split_set_v0",
            "runtime_period_profile": "period_profile_split_set_v0",
            "locked_final_oos_b_policy": "forbidden_until_candidate_freeze",
            "required_runtime_level": "L4_split_runtime_probe",
            "l4_promising_result_effect": "continue_to_L5_candidate_runtime_evidence",
            "claim_boundary": "research_scout_eval_only_no_runtime_authority",
        },
        SURFACE_CONTRACT_ID: {
            "version": "surface_contract_v1",
            "surface_contract_id": SURFACE_CONTRACT_ID,
            "status": "skeleton_open_no_runtime_contract_claim",
            "created_at_utc": created_at,
            "row_key": "us100_bar_close_time",
            "dataset_id": "dataset_raw_us100_m5_wave0_export_20260621T152827Z",
            "feature_order_policy": "declared_per_run_and_hashed_before_ONNX_export",
            "task_surface_policy": "declared_per_run_no_default_output_head",
            "runtime_follow_through": {
                "valid_proxy_model_bearing_run_requires_l4": True,
                "l4_promising_result_effect": "continue_to_L5_candidate_runtime_evidence",
            },
            "claim_boundary": "surface_contract_skeleton_only_not_runtime_authority",
        },
    }


def update_first_campaign(repo_root: Path, created_at: str, branch: str) -> None:
    path = repo_root / OLD_CAMPAIGN_PATH
    campaign = load_yaml(path)
    campaign["status"] = FIRST_CAMPAIGN_CLOSED_STATUS
    campaign["updated_at_utc"] = created_at
    campaign["target_branch"] = branch
    campaign["claim_boundary"] = OLD_CLOSEOUT_BOUNDARY
    campaign["next_action"] = NEXT_WORK_ID
    campaign.setdefault("forbidden_claims", [])
    campaign["decision_replay_closeout"] = {
        "status": FIRST_CAMPAIGN_CLOSED_STATUS,
        "result_judgment": "negative",
        "candidate_count": 0,
        "l5_candidate_count": 0,
        "evidence_paths": [
            "lab/campaigns/campaign_us100_task_surface_scout_v0/synthesis/decision_replay_judgment_summary.yaml",
            "lab/memory/negative/neg_wave0_decision_replay_momentum_ret_1_loss_v0.yaml",
        ],
        "negative_memory_ids": ["neg_wave0_decision_replay_momentum_ret_1_loss_v0"],
        "next_action": NEXT_WORK_ID,
        "claim_boundary": OLD_CLOSEOUT_BOUNDARY,
    }
    parity = campaign.get("proxy_runtime_parity") or {}
    parity["status"] = "decision_replay_L4_judged_negative_no_L5_candidate"
    parity["divergence_judgment"] = "proxy_preserved_clue_runtime_negative_under_naive_decision_adapter"
    parity["follow_up_action"] = NEXT_WORK_ID
    campaign["proxy_runtime_parity"] = parity
    git_integration = campaign.get("git_integration") or {}
    git_integration["status"] = "campaign_close_branch_committed_pending_main_boundary"
    campaign["git_integration"] = git_integration
    write_yaml(path, campaign)


def update_wave(repo_root: Path, created_at: str) -> None:
    wave = load_yaml(repo_root / WAVE_ALLOCATION_PATH)
    wave["status"] = "campaign_001_closed_campaign_002_opened"
    wave["updated_at_utc"] = created_at
    wave["claim_boundary"] = "wave01_campaign_002_open_no_candidate_no_baseline_no_runtime_authority"
    wave["next_action"] = NEXT_WORK_ID
    budget = wave.get("budget") or {}
    budget["formal_mt5_strategy_tester_runs"] = 30
    budget["runtime_probe_budget"] = "L4 mandatory for all valid proxy/model-bearing runs; L5 only when L4 remains promising"
    wave["budget"] = budget

    allocations = list(wave.get("campaign_allocations") or [])
    for allocation in allocations:
        if allocation.get("campaign_id") == OLD_CAMPAIGN_ID:
            allocation["status"] = FIRST_CAMPAIGN_CLOSED_STATUS
            allocation["claim_boundary"] = OLD_CLOSEOUT_BOUNDARY
            allocation["decision_replay_judgment_summary"] = (
                "lab/campaigns/campaign_us100_task_surface_scout_v0/synthesis/decision_replay_judgment_summary.yaml"
            )
            allocation["negative_memory_ids"] = ["neg_wave0_decision_replay_momentum_ret_1_loss_v0"]
            allocation["next_action"] = NEXT_WORK_ID
    if not any(item.get("campaign_id") == NEW_CAMPAIGN_ID for item in allocations):
        allocations.append(
            {
                "campaign_id": NEW_CAMPAIGN_ID,
                "allocation_role": "second_unexplored_event_barrier_decision_surface",
                "max_runs": 24,
                "initial_batch_size": 10,
                "status": NEW_CAMPAIGN_STATUS,
                "campaign_manifest": NEW_CAMPAIGN_PATH.as_posix(),
                "surface_manifest": NEW_SURFACE_PATH.as_posix(),
                "sweep_manifest": NEW_SWEEP_PATH.as_posix(),
                "run_refs": NEW_RUN_REFS_PATH.as_posix(),
                "claim_boundary": CLAIM_BOUNDARY,
                "next_action": NEXT_WORK_ID,
            }
        )
    wave["campaign_allocations"] = allocations
    wave["notes"] = (
        "Campaign 001 closed with negative decision replay judgment and no candidate. "
        "Campaign 002 opened as a new event/barrier decision surface, not a repair continuation."
    )
    write_yaml(repo_root / WAVE_ALLOCATION_PATH, wave)


def update_registries(repo_root: Path, created_at: str) -> None:
    upsert_csv_row(
        repo_root / REGISTRY_PATHS["campaign"],
        "campaign_id",
        {
            "campaign_id": OLD_CAMPAIGN_ID,
            "status": FIRST_CAMPAIGN_CLOSED_STATUS,
            "created_at_utc": "2026-06-21T15:18:51Z",
            "campaign_path": OLD_CAMPAIGN_PATH.as_posix(),
            "objective": "Scout explicit US100 M5 task target label feature input decision holding and model scout surfaces before optimization",
            "axis_tags": "task_surface;target_or_label_surface;feature_or_input_surface;model_or_training_surface;decision_use;evaluation_or_runtime_surface;horizon_or_holding_policy;us100_m5_closed_bar_only",
            "primary_family": "experiment_design",
            "primary_skill": "spacesonar-experiment-design",
            "claim_boundary": OLD_CLOSEOUT_BOUNDARY,
            "evidence_path": "lab/campaigns/campaign_us100_task_surface_scout_v0/synthesis/decision_replay_judgment_summary.yaml",
            "next_action": NEXT_WORK_ID,
            "notes": "decision_replay_judgment_negative_no_l5_candidate_rotate_to_new_surface",
        },
    )
    upsert_csv_row(
        repo_root / REGISTRY_PATHS["campaign"],
        "campaign_id",
        {
            "campaign_id": NEW_CAMPAIGN_ID,
            "status": NEW_CAMPAIGN_STATUS,
            "created_at_utc": created_at,
            "campaign_path": NEW_CAMPAIGN_PATH.as_posix(),
            "objective": "Open US100 M5 event barrier decision risk holding surface before micro search",
            "axis_tags": "event_barrier_surface;target_or_label_surface;feature_or_input_surface;model_or_training_surface;decision_surface;risk_or_sizing_surface;horizon_or_holding_policy;evaluation_or_runtime_surface;us100_m5_closed_bar_only",
            "primary_family": "experiment_design",
            "primary_skill": "spacesonar-experiment-design",
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_path": NEW_CAMPAIGN_PATH.as_posix(),
            "next_action": NEXT_WORK_ID,
            "notes": "standard campaign open; prior negative memory is prevention boundary only",
        },
    )
    upsert_csv_row(
        repo_root / REGISTRY_PATHS["idea"],
        "idea_id",
        {
            "idea_id": OLD_IDEA_ID,
            "status": FIRST_CAMPAIGN_CLOSED_STATUS,
            "created_at_utc": "2026-06-21T15:18:51Z",
            "axis_tags": "task_surface;target_label;decision_use;us100_m5_only",
            "claim_boundary": "decision_replay_negative_memory_only_no_candidate",
            "evidence_path": "lab/campaigns/campaign_us100_task_surface_scout_v0/synthesis/decision_replay_judgment_summary.yaml",
            "next_action": NEXT_WORK_ID,
            "notes": "first campaign closed no candidate",
        },
    )
    upsert_csv_row(
        repo_root / REGISTRY_PATHS["idea"],
        "idea_id",
        {
            "idea_id": IDEA_ID,
            "status": NEW_CAMPAIGN_STATUS,
            "created_at_utc": created_at,
            "axis_tags": "event_barrier_surface;decision_surface;risk_holding_policy;us100_m5_only",
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_path": NEW_IDEA_PATH.as_posix(),
            "next_action": NEXT_WORK_ID,
            "notes": "new surface open; not legacy or momentum_ret_1 repair continuation",
        },
    )
    upsert_csv_row(
        repo_root / REGISTRY_PATHS["hypothesis"],
        "hypothesis_id",
        {
            "hypothesis_id": "hyp_surface_diversity_before_model_search_v0",
            "idea_id": "idea_us100_m5_blank_slate_surface_map_v0",
            "status": FIRST_CAMPAIGN_CLOSED_STATUS,
            "hypothesis": "Diverse explicit task surfaces should be mapped before model search",
            "decision_use": "scout_tradeability_and_abstain_capable_decisions",
            "comparison_baseline": "no_trade_random_or_manual_rule_when_defined",
            "claim_boundary": "decision_replay_negative_memory_only_no_candidate",
            "evidence_path": "lab/campaigns/campaign_us100_task_surface_scout_v0/synthesis/decision_replay_judgment_summary.yaml",
            "next_action": NEXT_WORK_ID,
            "notes": "first campaign closed no candidate",
        },
    )
    upsert_csv_row(
        repo_root / REGISTRY_PATHS["hypothesis"],
        "hypothesis_id",
        {
            "hypothesis_id": HYPOTHESIS_ID,
            "idea_id": IDEA_ID,
            "status": NEW_CAMPAIGN_STATUS,
            "hypothesis": "Event barrier path labels with explicit decision risk and holding logic may expose a tradeable surface",
            "decision_use": "abstain_capable_event_barrier_entry_exit_risk_surface",
            "comparison_baseline": "no_trade_permuted_label_negative_memory_reference_only",
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_path": NEW_HYPOTHESIS_PATH.as_posix(),
            "next_action": NEXT_WORK_ID,
            "notes": "open hypothesis no candidate or runtime authority",
        },
    )
    upsert_csv_row(
        repo_root / REGISTRY_PATHS["surface"],
        "surface_id",
        {
            "surface_id": SURFACE_ID,
            "hypothesis_id": HYPOTHESIS_ID,
            "status": NEW_CAMPAIGN_STATUS,
            "created_at_utc": created_at,
            "surface_path": NEW_SURFACE_PATH.as_posix(),
            "label_recipe_id": LABEL_RECIPE_ID,
            "feature_recipe_id": FEATURE_RECIPE_ID,
            "feature_recipe_mix_id": "not_applicable_no_mix_in_standard_campaign_open",
            "model_recipe_id": MODEL_RECIPE_ID,
            "decision_recipe_id": DECISION_RECIPE_ID,
            "split_recipe_id": "split_set_v0",
            "eval_recipe_id": EVAL_RECIPE_ID,
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_path": NEW_SURFACE_PATH.as_posix(),
            "next_action": NEXT_WORK_ID,
            "notes": "feature count variable per run; event barrier path decision surface",
        },
    )
    upsert_csv_row(
        repo_root / REGISTRY_PATHS["sweep"],
        "sweep_id",
        {
            "sweep_id": SWEEP_ID,
            "campaign_id": NEW_CAMPAIGN_ID,
            "surface_id": SURFACE_ID,
            "status": "planned_not_executed",
            "created_at_utc": created_at,
            "sweep_path": NEW_SWEEP_PATH.as_posix(),
            "sweep_type": "broad_event_barrier_surface_scout",
            "axis_count": "6",
            "run_ref_path": NEW_RUN_REFS_PATH.as_posix(),
            "evidence_boundary": "planned_sweep_only",
            "evidence_path": NEW_SWEEP_PATH.as_posix(),
            "next_action": NEXT_WORK_ID,
            "notes": "empty run_refs until first batch specs are materialized",
        },
    )
    upsert_csv_row(
        repo_root / REGISTRY_PATHS["wave"],
        "wave_id",
        {
            "wave_id": WAVE_ID,
            "status": "campaign_001_closed_campaign_002_opened",
            "created_at_utc": "2026-06-21T15:18:51Z",
            "wave_path": WAVE_ALLOCATION_PATH.as_posix(),
            "allocation_goal": "Map US100 M5 closed-bar task label input decision and holding surfaces before optimization",
            "max_runs": "48",
            "claim_boundary": "wave01_campaign_002_open_no_candidate_no_baseline_no_runtime_authority",
            "evidence_path": NEW_CAMPAIGN_PATH.as_posix(),
            "next_action": NEXT_WORK_ID,
            "notes": "first campaign closed no candidate; second event barrier campaign opened",
        },
    )
    upsert_csv_row(
        repo_root / REGISTRY_PATHS["goal"],
        "goal_id",
        {
            "goal_id": GOAL_ID,
            "status": "active_long_running",
            "created_at_utc": "2026-06-21T15:18:51Z",
            "goal_path": GOAL_MANIFEST_PATH.as_posix(),
            "terminal_contract_path": "lab/goals/goal_us100_onnx_forward_boundary_v0/terminal_eligibility_contract.yaml",
            "active_phase": "wave01_campaign_002_event_barrier_opened",
            "claim_boundary": "active_goal_control_plane_campaign_open_not_goal_achieve",
            "next_work_item": NEXT_WORK_ID,
            "notes": "durable_codex_operation_primary_wave01_closeout_continues",
        },
    )
    upsert_csv_row(
        repo_root / CAMPAIGN_REFS_PATH,
        "campaign_id",
        {
            "wave_id": WAVE_ID,
            "campaign_id": OLD_CAMPAIGN_ID,
            "campaign_path": OLD_CAMPAIGN_PATH.as_posix(),
            "allocation_role": "primary_initial_surface_scout",
            "status": FIRST_CAMPAIGN_CLOSED_STATUS,
            "max_runs": "48",
            "initial_batch_size": "12",
            "claim_boundary": OLD_CLOSEOUT_BOUNDARY,
            "next_action": NEXT_WORK_ID,
            "notes": "closed with negative decision replay judgment and no L5 candidate",
        },
    )
    upsert_csv_row(
        repo_root / CAMPAIGN_REFS_PATH,
        "campaign_id",
        {
            "wave_id": WAVE_ID,
            "campaign_id": NEW_CAMPAIGN_ID,
            "campaign_path": NEW_CAMPAIGN_PATH.as_posix(),
            "allocation_role": "second_unexplored_event_barrier_decision_surface",
            "status": NEW_CAMPAIGN_STATUS,
            "max_runs": "24",
            "initial_batch_size": "10",
            "claim_boundary": CLAIM_BOUNDARY,
            "next_action": NEXT_WORK_ID,
            "notes": "central campaign source of truth; not bounded synthesis or repair continuation",
        },
    )


def update_recipe_index(repo_root: Path, created_at: str) -> None:
    type_by_id = {
        FEATURE_RECIPE_ID: "feature",
        LABEL_RECIPE_ID: "label",
        MODEL_RECIPE_ID: "model",
        DECISION_RECIPE_ID: "decision",
        EVAL_RECIPE_ID: "eval",
        SURFACE_CONTRACT_ID: "surface_contract",
    }
    feasibility_by_id = {
        FEATURE_RECIPE_ID: "runtime_feasible_after_per_run_feature_order_hash",
        LABEL_RECIPE_ID: "training_label_only_until_exported_run",
        MODEL_RECIPE_ID: "onnx_feasible_scout_only",
        DECISION_RECIPE_ID: "requires_MT5_unit_semantics_before_L4",
        EVAL_RECIPE_ID: "L4_required_for_valid_proxy_model_runs",
        SURFACE_CONTRACT_ID: "contract_skeleton_only",
    }
    for recipe_id, path in RECIPE_PATHS.items():
        full_path = repo_root / path
        upsert_csv_row(
            repo_root / REGISTRY_PATHS["recipe"],
            "recipe_id",
            {
                "recipe_id": recipe_id,
                "recipe_type": type_by_id[recipe_id],
                "status": "skeleton_open_no_candidate",
                "created_at_utc": created_at,
                "recipe_path": path.as_posix(),
                "sha256": sha256(full_path),
                "runtime_feasibility": feasibility_by_id[recipe_id],
                "claim_boundary": "recipe_skeleton_only_no_candidate_no_runtime_authority",
                "next_action": NEXT_WORK_ID,
                "notes": "created for event barrier decision campaign; feature count is variable per run",
            },
        )


def update_goal_and_workspace(repo_root: Path, created_at: str, branch: str) -> None:
    goal = load_yaml(repo_root / GOAL_MANIFEST_PATH)
    goal["updated_at_utc"] = created_at
    goal["claim_boundary"] = "active_goal_control_plane_campaign_open_not_goal_achieve"
    goal["active_phase"] = "wave01_campaign_002_event_barrier_opened"
    goal["active_ids"] = {
        "idea_id": IDEA_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "wave_id": WAVE_ID,
        "campaign_id": NEW_CAMPAIGN_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
    }
    blank_slate = goal.get("blank_slate_contract") or {}
    for key in list(blank_slate):
        if "historical" in key and "feature_surface" in key:
            blank_slate.pop(key, None)
    blank_slate["inherited_feature_list_allowed"] = False
    blank_slate["inherited_fixed_feature_count_allowed"] = False
    goal["blank_slate_contract"] = blank_slate
    branch_worktree = goal.get("branch_worktree") or {}
    branch_worktree["current_branch"] = branch
    branch_worktree["branch_worktree_fit"] = "fit"
    branch_worktree["branch_action"] = "keep_current_branch"
    branch_worktree["mismatch_claim_effect"] = "no_branch_mismatch_detected_for_campaign_open"
    goal["branch_worktree"] = branch_worktree
    current_spec = (goal.get("program_budgets") or {}).get("current_wave0_spec") or {}
    current_spec["status"] = "campaign_001_closed_campaign_002_opened"
    current_spec["next_campaign_id"] = NEW_CAMPAIGN_ID
    current_spec["next_campaign_manifest"] = NEW_CAMPAIGN_PATH.as_posix()
    current_spec["next_work_item"] = NEXT_WORK_ID
    goal.setdefault("program_budgets", {})["current_wave0_spec"] = current_spec
    goal["next_work_item"] = {
        "path": NEXT_WORK_ITEM_PATH.as_posix(),
        "work_item_id": NEXT_WORK_ID,
        "summary": "Materialize first broad batch specs for the Wave01 event/barrier decision campaign.",
    }
    write_yaml(repo_root / GOAL_MANIFEST_PATH, goal)

    next_work = {
        "version": "onnx_lab_work_item_v1",
        "work_item_id": NEXT_WORK_ID,
        "active_goal_id": GOAL_ID,
        "created_at_utc": created_at,
        "status": "planned_not_started",
        "user_request": (
            "Materialize the first broad batch specs for the event/barrier decision campaign while preserving "
            "Wave01 Codex operating stability."
        ),
        "current_truth": {
            "campaign_manifest": NEW_CAMPAIGN_PATH.as_posix(),
            "surface_manifest": NEW_SURFACE_PATH.as_posix(),
            "sweep_manifest": NEW_SWEEP_PATH.as_posix(),
            "run_refs": NEW_RUN_REFS_PATH.as_posix(),
            "negative_memory_boundary": "lab/memory/negative/neg_wave0_decision_replay_momentum_ret_1_loss_v0.yaml",
        },
        "work_classification": {
            "primary_family": "experiment_design",
            "detected_families": ["experiment_design", "data_feature_build", "model_training", "runtime_probe"],
            "mutation_intent": "materialize_first_batch_run_specs_not_execute_yet",
            "execution_intent": "design_to_L4_follow_through_path_for_valid_proxy_model_runs",
        },
        "skill_routing": {
            "primary_family": "experiment_design",
            "primary_skill": "spacesonar-experiment-design",
            "support_skills": [
                "spacesonar-exploration-mandate",
                "spacesonar-data-integrity",
                "spacesonar-model-validation",
                "spacesonar-runtime-parity",
                "spacesonar-claim-discipline",
            ],
            "required_gates": [
                "design_contract_check",
                "exploration_coverage_check",
                "feature_label_boundary_check",
                "campaign_proxy_runtime_parity_policy",
                "final_claim_guard",
            ],
        },
        "acceptance_criteria": [
            "Create a first broad batch matrix for the event/barrier decision surface.",
            "Do not fix feature count, model head, direction mapping, or holding duration as defaults.",
            "Every valid proxy/model-bearing spec must include an L4 follow-through path or a failure-disposition requirement.",
            "Do not use locked final OOS-B.",
            "Do not claim candidate, baseline, runtime authority, economics pass, or Goal Achieve.",
        ],
        "runtime_learning_probe_decision": {
            "required": True,
            "decision": "L4_required_after_valid_proxy_model_execution",
            "reason": "Project policy forbids proxy-only closeout for valid proxy/model-bearing runs.",
        },
        "claim_boundary": "planned_first_batch_spec_only_no_run_no_candidate_no_runtime_authority",
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
        "next_action": "write first batch specs and anti-selection ledger for event/barrier decision campaign",
    }
    write_yaml(repo_root / NEXT_WORK_ITEM_PATH, next_work)

    resume = load_yaml(repo_root / RESUME_CURSOR_PATH)
    resume["updated_at_utc"] = created_at
    resume["active_phase"] = "wave01_campaign_002_event_barrier_opened"
    resume["active_ids"] = {
        "idea_id": IDEA_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "wave_id": WAVE_ID,
        "campaign_id": NEW_CAMPAIGN_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
    }
    sources = list(dict.fromkeys(list(resume.get("current_truth_sources") or []) + [
        NEW_CAMPAIGN_PATH.as_posix(),
        NEW_SURFACE_PATH.as_posix(),
        NEW_SWEEP_PATH.as_posix(),
        NEW_IDEA_PATH.as_posix(),
        NEW_HYPOTHESIS_PATH.as_posix(),
        CLOSEOUT_PATH.as_posix(),
    ]))
    resume["current_truth_sources"] = sources
    resume["latest_completed_work"] = {
        "work_item_id": OPEN_WORK_ID,
        "result_judgment": "planning_scaffold",
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_paths": [
            NEW_CAMPAIGN_PATH.as_posix(),
            NEW_SURFACE_PATH.as_posix(),
            NEW_SWEEP_PATH.as_posix(),
            CLOSEOUT_PATH.as_posix(),
        ],
    }
    resume["next_work_item"] = {
        "work_item_id": NEXT_WORK_ID,
        "path": NEXT_WORK_ITEM_PATH.as_posix(),
    }
    write_yaml(repo_root / RESUME_CURSOR_PATH, resume)

    state = load_yaml(repo_root / WORKSPACE_STATE_PATH)
    claims = state.get("current_claims") or {}
    claims.update(
        {
            "active_goal_phase": "wave01_campaign_002_event_barrier_opened",
            "active_campaign_id": NEW_CAMPAIGN_ID,
            "active_hypothesis_id": HYPOTHESIS_ID,
            "active_surface_id": SURFACE_ID,
            "active_sweep_id": SWEEP_ID,
            "next_work_item_id": NEXT_WORK_ID,
            "active_goal_claim_boundary": "active_goal_control_plane_campaign_open_not_goal_achieve",
            "wave0_first_campaign_status": FIRST_CAMPAIGN_CLOSED_STATUS,
            "wave0_second_campaign_status": NEW_CAMPAIGN_STATUS,
            "wave0_second_campaign_manifest": NEW_CAMPAIGN_PATH.as_posix(),
            "wave0_second_campaign_surface": NEW_SURFACE_PATH.as_posix(),
            "wave0_second_campaign_sweep": NEW_SWEEP_PATH.as_posix(),
            "wave0_second_campaign_next_work_item": NEXT_WORK_ID,
            "wave0_second_campaign_claim_boundary": CLAIM_BOUNDARY,
        }
    )
    state["current_claims"] = claims
    state["updated_utc"] = created_at
    write_yaml(repo_root / WORKSPACE_STATE_PATH, state)


def closeout_payload(repo_root: Path, created_at: str, branch: str, command_argv: list[str]) -> dict[str, Any]:
    changed_files = git_changed_files(repo_root)
    return {
        "version": "work_closeout_v1",
        "work_item_id": OPEN_WORK_ID,
        "active_goal_id": GOAL_ID,
        "created_at_utc": created_at,
        "result_judgment": "planning_scaffold",
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_paths": [
            NEW_CAMPAIGN_PATH.as_posix(),
            NEW_SURFACE_PATH.as_posix(),
            NEW_SWEEP_PATH.as_posix(),
            NEW_IDEA_PATH.as_posix(),
            NEW_HYPOTHESIS_PATH.as_posix(),
            CAMPAIGN_REFS_PATH.as_posix(),
        ],
        "completed_actions": [
            "synced_first_campaign_closeout_status",
            "opened_second_event_barrier_decision_campaign",
            "created_recipe_skeletons_without_fixed_feature_count",
            "updated_wave_campaign_refs_and_goal_cursor",
        ],
        "claim_limits": [
            "no_model_run",
            "no_proxy_result",
            "no_MT5_L4_for_new_campaign_yet",
            "no_candidate",
            "no_runtime_authority",
            "no_economics_pass",
            "no_goal_achieve",
        ],
        "next_action": NEXT_WORK_ID,
        "execution_provenance": {
            "git_sha": git_value(repo_root, ["rev-parse", "HEAD"]),
            "branch": branch,
            "dirty_flag": bool(changed_files),
            "changed_files": changed_files,
            "command_argv": command_argv,
            "python_executable": sys.executable.replace(str(Path.home()), "${USERPROFILE}"),
            "python_version": sys.version.split()[0],
            "started_at_utc": created_at,
            "ended_at_utc": created_at,
        },
    }


def upsert_artifact_row(repo_root: Path, artifact_id: str, rel_path: Path, artifact_type: str, consumer: str) -> None:
    full_path = repo_root / rel_path
    upsert_csv_row(
        repo_root / REGISTRY_PATHS["artifact"],
        "artifact_id",
        {
            "artifact_id": artifact_id,
            "run_id": "",
            "bundle_id": "",
            "attempt_id": "",
            "artifact_type": artifact_type,
            "path_or_uri": rel_path.as_posix(),
            "sha256": sha256(full_path),
            "size_bytes": str(full_path.stat().st_size),
            "availability": "present_hash_recorded",
            "producer_command": "python foundation/pipelines/open_wave01_event_barrier_decision_campaign.py --write-control-records",
            "regeneration_command": "python foundation/pipelines/open_wave01_event_barrier_decision_campaign.py --write-control-records",
            "source_of_truth": rel_path.as_posix(),
            "consumer": consumer,
            "claim_boundary": CLAIM_BOUNDARY,
            "notes": "campaign open planning scaffold only; no model/runtime/candidate claim",
        },
    )


def update_artifact_registry(repo_root: Path) -> None:
    artifacts = [
        ("artifact_wave0_campaign_refs_v0", CAMPAIGN_REFS_PATH, "wave_campaign_refs", WAVE_ID),
        ("artifact_wave01_event_barrier_campaign_manifest_v0", NEW_CAMPAIGN_PATH, "campaign_manifest", NEW_CAMPAIGN_ID),
        ("artifact_wave01_event_barrier_surface_manifest_v0", NEW_SURFACE_PATH, "surface_manifest", SURFACE_ID),
        ("artifact_wave01_event_barrier_sweep_manifest_v0", NEW_SWEEP_PATH, "sweep_manifest", SWEEP_ID),
        ("artifact_wave01_event_barrier_run_refs_v0", NEW_RUN_REFS_PATH, "run_refs", SWEEP_ID),
        ("artifact_wave01_event_barrier_open_closeout_v0", CLOSEOUT_PATH, "work_closeout", OPEN_WORK_ID),
    ]
    for recipe_id, path in RECIPE_PATHS.items():
        artifacts.append((f"artifact_{recipe_id}", path, "recipe", recipe_id))
    for artifact_id, rel_path, artifact_type, consumer in artifacts:
        upsert_artifact_row(repo_root, artifact_id, rel_path, artifact_type, consumer)


def write_new_records(repo_root: Path, created_at: str, branch: str) -> None:
    write_yaml(repo_root / NEW_CAMPAIGN_PATH, campaign_manifest(created_at, branch))
    write_yaml(repo_root / NEW_SURFACE_PATH, surface_manifest(created_at))
    write_yaml(repo_root / NEW_SWEEP_PATH, sweep_manifest(created_at))
    write_empty_run_refs(repo_root / NEW_RUN_REFS_PATH)
    write_yaml(repo_root / NEW_IDEA_PATH, idea_manifest(created_at))
    write_yaml(repo_root / NEW_HYPOTHESIS_PATH, hypothesis_manifest(created_at))
    for recipe_id, payload in recipe_payloads(created_at).items():
        write_yaml(repo_root / RECIPE_PATHS[recipe_id], payload)


def run(repo_root: Path, created_at: str, write_control_records: bool) -> dict[str, Any]:
    branch = git_value(repo_root, ["branch", "--show-current"])
    command_argv = ["python", "foundation/pipelines/open_wave01_event_barrier_decision_campaign.py"]
    if write_control_records:
        command_argv.append("--write-control-records")

    write_new_records(repo_root, created_at, branch)
    update_first_campaign(repo_root, created_at, branch)
    update_wave(repo_root, created_at)
    update_registries(repo_root, created_at)
    update_recipe_index(repo_root, created_at)
    update_goal_and_workspace(repo_root, created_at, branch)
    write_yaml(repo_root / CLOSEOUT_PATH, closeout_payload(repo_root, created_at, branch, command_argv))
    update_artifact_registry(repo_root)

    summary = {
        "status": "campaign_opened",
        "campaign_id": NEW_CAMPAIGN_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "next_work_item": NEXT_WORK_ID,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    if write_control_records:
        print(yaml.dump(summary, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=False))
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Open Wave01 event/barrier decision campaign records.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--created-at-utc", default=now_utc())
    parser.add_argument("--write-control-records", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    run(repo_root, args.created_at_utc, args.write_control_records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
