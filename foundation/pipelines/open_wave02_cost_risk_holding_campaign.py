from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]

GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WAVE_ID = "wave_us100_wave02_tradeability_decision_surface_v0"
PREVIOUS_CAMPAIGN_ID = "campaign_us100_wave02_tradeability_decision_surface_v0"

CAMPAIGN_ID = "campaign_us100_wave02_cost_risk_holding_surface_v0"
IDEA_ID = "idea_us100_wave02_cost_risk_holding_surface_v0"
HYPOTHESIS_ID = "hyp_us100_wave02_cost_risk_holding_runtime_alignment_v0"
SURFACE_ID = "surface_us100_wave02_cost_risk_holding_v0"
SWEEP_ID = "sweep_us100_wave02_cost_risk_holding_broad_v0"

WORK_ITEM_ID = "work_wave02_open_cost_risk_holding_campaign_v0"
PARENT_WORK_ITEM_ID = "work_wave02_next_campaign_or_wave_boundary_decision_v0"
NEXT_WORK_ITEM_ID = "work_wave02_cost_risk_holding_first_batch_spec_v0"

OPEN_STATUS = "wave02_cost_risk_holding_campaign_opened_planning_scaffold"
WORK_STATUS = "wave02_next_boundary_decision_closed_new_campaign_opened"
WAVE_STATUS = "wave02_campaign_002_open"
NEXT_STATUS = "wave02_cost_risk_holding_first_batch_spec_pending"

CLAIM_BOUNDARY = (
    "wave02_cost_risk_holding_campaign_open_no_model_run_no_candidate_no_runtime_authority_"
    "no_economics_pass_no_live_readiness_no_goal_achieve"
)
NEXT_CLAIM_BOUNDARY = (
    "wave02_cost_risk_holding_first_batch_spec_pending_no_candidate_no_runtime_authority_"
    "no_economics_pass_no_live_readiness_no_goal_achieve"
)
GOAL_CLAIM_BOUNDARY = "active_goal_wave02_campaign_002_open_not_goal_achieve"

FEATURE_RECIPE_ID = "feature_wave02_us100_cost_risk_holding_v0"
LABEL_RECIPE_ID = "label_wave02_cost_adjusted_tradeability_v0"
MODEL_RECIPE_ID = "model_wave02_cost_risk_onnx_scout_v0"
DECISION_RECIPE_ID = "decision_wave02_cost_risk_holding_abstain_v0"
EVAL_RECIPE_ID = "eval_wave02_cost_risk_runtime_v0"

CAMPAIGN_PATH = Path("lab/campaigns") / CAMPAIGN_ID / "campaign_manifest.yaml"
SURFACE_PATH = Path("lab/surfaces") / SURFACE_ID / "surface_manifest.yaml"
IDEA_PATH = Path("lab/hypotheses") / f"{IDEA_ID}.yaml"
HYPOTHESIS_PATH = Path("lab/hypotheses") / f"{HYPOTHESIS_ID}.yaml"
SWEEP_PATH = Path("lab/campaigns") / CAMPAIGN_ID / "sweeps" / SWEEP_ID / "sweep_manifest.yaml"
RUN_REFS_PATH = Path("lab/campaigns") / CAMPAIGN_ID / "sweeps" / SWEEP_ID / "run_refs.csv"
WORK_CLOSEOUT_PATH = Path("lab/goals") / GOAL_ID / f"{WORK_ITEM_ID}_closeout.yaml"
NEXT_WORK_ITEM_PATH = Path("lab/goals") / GOAL_ID / "next_work_item.yaml"
RESUME_CURSOR_PATH = Path("lab/goals") / GOAL_ID / "resume_cursor.yaml"
GOAL_MANIFEST_PATH = Path("lab/goals") / GOAL_ID / "goal_manifest.yaml"
WORKSPACE_STATE_PATH = Path("docs/workspace/workspace_state.yaml")
WAVE_ALLOCATION_PATH = Path("lab/waves") / WAVE_ID / "wave_allocation.yaml"
CAMPAIGN_REFS_PATH = Path("lab/waves") / WAVE_ID / "campaign_refs.csv"
PREVIOUS_CLOSEOUT_PATH = (
    Path("lab/campaigns") / PREVIOUS_CAMPAIGN_ID / "campaign_closeout.yaml"
)
NEGATIVE_MEMORY_PATH = Path(
    "lab/memory/negative/neg_wave02_tradeability_momentum_ret_1_decision_replay_l5_negative_v0.yaml"
)

RECIPE_PATHS = {
    FEATURE_RECIPE_ID: Path("configs/onnx_lab/feature_recipes") / f"{FEATURE_RECIPE_ID}.yaml",
    LABEL_RECIPE_ID: Path("configs/onnx_lab/label_recipes") / f"{LABEL_RECIPE_ID}.yaml",
    MODEL_RECIPE_ID: Path("configs/onnx_lab/model_recipes") / f"{MODEL_RECIPE_ID}.yaml",
    DECISION_RECIPE_ID: Path("configs/onnx_lab/decision_recipes") / f"{DECISION_RECIPE_ID}.yaml",
    EVAL_RECIPE_ID: Path("configs/onnx_lab/eval_recipes") / f"{EVAL_RECIPE_ID}.yaml",
    SURFACE_ID: Path("configs/onnx_lab/surface_contracts") / f"{SURFACE_ID}.yaml",
}

REGISTRY_PATHS = {
    "idea": Path("docs/registers/idea_registry.csv"),
    "hypothesis": Path("docs/registers/hypothesis_registry.csv"),
    "surface": Path("docs/registers/experiment_surface_registry.csv"),
    "sweep": Path("docs/registers/sweep_registry.csv"),
    "campaign": Path("docs/registers/campaign_registry.csv"),
    "wave": Path("docs/registers/wave_registry.csv"),
    "goal": Path("docs/registers/goal_registry.csv"),
    "recipe": Path("docs/registers/recipe_index.csv"),
    "artifact": Path("docs/registers/artifact_registry.csv"),
}

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

AXIS_TAGS = [
    "target_or_label_surface",
    "feature_or_input_surface",
    "model_or_training_surface",
    "decision_surface",
    "risk_or_sizing_surface",
    "horizon_or_holding_policy",
    "evaluation_or_runtime_surface",
    "execution_cost_surface",
    "us100_m5_closed_bar_only",
]


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = yaml.safe_load(handle)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a mapping")
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


def write_csv_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def upsert_csv_row(path: Path, key: str, row: dict[str, Any]) -> None:
    fieldnames, rows = read_csv_rows(path)
    for field in row:
        if field not in fieldnames:
            fieldnames.append(field)
    serialized = {field: serialize_csv_value(row.get(field, "")) for field in fieldnames}
    for index, existing in enumerate(rows):
        if existing.get(key) == str(row[key]):
            merged = dict(existing)
            merged.update(serialized)
            rows[index] = merged
            break
    else:
        rows.append(serialized)
    write_csv_rows(path, fieldnames, rows)


def serialize_csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ";".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_value(args: list[str]) -> str:
    result = subprocess.run(["git", *args], cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip() or "unknown"


def git_changed_files() -> list[str]:
    result = subprocess.run(["git", "status", "--short"], cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return ["unknown"]
    return [line for line in result.stdout.splitlines() if line.strip()]


def git_state() -> dict[str, Any]:
    changed = git_changed_files()
    return {
        "git_sha": git_value(["rev-parse", "HEAD"]),
        "branch": git_value(["branch", "--show-current"]),
        "dirty_flag": bool(changed),
        "changed_files": changed,
    }


def common_recipe_payload(
    *, version: str, recipe_id: str, created_at: str, next_action: str, extra: dict[str, Any]
) -> dict[str, Any]:
    payload = {
        "version": version,
        "recipe_id": recipe_id,
        "status": "skeleton_open_no_candidate",
        "created_at_utc": created_at,
        "campaign_id": CAMPAIGN_ID,
        "surface_id": SURFACE_ID,
        "claim_boundary": "recipe_skeleton_only_no_candidate_no_runtime_authority_no_economics_pass",
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "next_action": next_action,
    }
    payload.update(extra)
    return payload


def recipe_payloads(created_at: str) -> dict[Path, dict[str, Any]]:
    return {
        RECIPE_PATHS[FEATURE_RECIPE_ID]: common_recipe_payload(
            version="feature_recipe_v1",
            recipe_id=FEATURE_RECIPE_ID,
            created_at=created_at,
            next_action=NEXT_WORK_ITEM_ID,
            extra={
                "feature_count_policy": "variable_declared_per_run_no_fixed_count",
                "input_families": [
                    "causal_us100_m5_price_return_range_volatility",
                    "session_state_and_spread_proxy_context",
                    "execution_cost_and_open_failed_avoidance_context",
                    "holding_window_and_reversal_pressure_context",
                ],
                "forbidden_defaults": [
                    "fixed_feature_count",
                    "inherited_feature_list",
                    "momentum_ret_1_replay_as_decision_policy",
                    "auxiliary_symbol_without_live_chart_evidence",
                ],
            },
        ),
        RECIPE_PATHS[LABEL_RECIPE_ID]: common_recipe_payload(
            version="label_recipe_v1",
            recipe_id=LABEL_RECIPE_ID,
            created_at=created_at,
            next_action=NEXT_WORK_ITEM_ID,
            extra={
                "label_family": "cost_adjusted_tradeability_with_abstain_and_adverse_excursion",
                "horizon_policy": "variable_declared_per_run_with_tail_drop",
                "target_semantics": [
                    "tradeable_after_cost_proxy",
                    "side_conditional_return_exceeds_adverse_excursion",
                    "abstain_when_cost_or_reversal_risk_dominates",
                ],
                "forbidden_defaults": [
                    "fixed_horizon",
                    "legacy_direction_mapping",
                    "momentum_ret_1_replay_label",
                    "locked_final_oos_selection",
                ],
            },
        ),
        RECIPE_PATHS[MODEL_RECIPE_ID]: common_recipe_payload(
            version="model_recipe_v1",
            recipe_id=MODEL_RECIPE_ID,
            created_at=created_at,
            next_action=NEXT_WORK_ITEM_ID,
            extra={
                "model_family_policy": "onnx_feasible_scout_declared_per_run",
                "candidate_families": [
                    "logistic_or_linear_rank_scout",
                    "tree_or_boosted_onnx_feasible_scout",
                ],
                "output_head_policy": "tradeability_score_side_abstain_or_cost_risk_head_declared_per_run",
                "forbidden_defaults": [
                    "inherited_model_family",
                    "selected_baseline",
                    "fixed_threshold",
                    "runtime_authority",
                ],
            },
        ),
        RECIPE_PATHS[DECISION_RECIPE_ID]: common_recipe_payload(
            version="decision_recipe_v1",
            recipe_id=DECISION_RECIPE_ID,
            created_at=created_at,
            next_action=NEXT_WORK_ITEM_ID,
            extra={
                "decision_family": "abstain_capable_cost_risk_holding_gate",
                "holding_policy": "timeout_stop_or_signal_decay_exit_declared_per_run",
                "risk_policy": "fixed_research_lot_or_cost_cap_declared_per_run_no_operating_sizing",
                "mt5_semantics_required_before_l4": [
                    "entry_cost_proxy",
                    "open_failed_handling",
                    "timeout_close",
                    "stop_or_adverse_excursion_close",
                    "no_trade_or_abstain",
                    "lot_rounding",
                ],
                "forbidden_defaults": [
                    "momentum_ret_1_replay",
                    "candidate_repair_from_previous_campaign",
                    "operating_risk_policy",
                ],
            },
        ),
        RECIPE_PATHS[EVAL_RECIPE_ID]: common_recipe_payload(
            version="eval_recipe_v1",
            recipe_id=EVAL_RECIPE_ID,
            created_at=created_at,
            next_action=NEXT_WORK_ITEM_ID,
            extra={
                "split_recipe_id": "split_set_v0",
                "required_period_roles": ["validation", "research_oos"],
                "locked_final_oos_policy": "excluded_without_unlock_contract",
                "runtime_follow_through": "proxy_model_bearing_runs_require_l4_split_runtime_probe_then_l5_if_promising",
                "forbidden_defaults": [
                    "selected_baseline",
                    "economics_pass",
                    "live_readiness",
                    "goal_achieve",
                ],
            },
        ),
        RECIPE_PATHS[SURFACE_ID]: {
            "version": "surface_contract_v1",
            "surface_contract_id": SURFACE_ID,
            "status": "skeleton_open_no_candidate",
            "created_at_utc": created_at,
            "campaign_id": CAMPAIGN_ID,
            "surface_id": SURFACE_ID,
            "claim_boundary": "recipe_skeleton_only_no_candidate_no_runtime_authority_no_economics_pass",
            "forbidden_claims": FORBIDDEN_CLAIMS,
            "next_action": NEXT_WORK_ITEM_ID,
            "row_key": "us100_bar_close_time",
            "primary_symbol": "US100",
            "timeframe": "M5",
            "auxiliary_symbols": "forbidden_unless_live_chart_verified",
            "proxy_runtime_parity_required": True,
            "runtime_follow_through_required": True,
        },
    }


def campaign_manifest(created_at: str) -> dict[str, Any]:
    return {
        "version": "campaign_manifest_v2",
        "campaign_id": CAMPAIGN_ID,
        "campaign_type": "standard_experiment",
        "active_goal_id": GOAL_ID,
        "status": OPEN_STATUS,
        "created_at_utc": created_at,
        "updated_at_utc": created_at,
        "wave_ids": [WAVE_ID],
        "idea_ids": [IDEA_ID],
        "hypothesis_ids": [HYPOTHESIS_ID],
        "objective": (
            "Open the second Wave02 campaign as a cost/risk/holding surface. The campaign tests whether "
            "explicit entry-cost, open-failed avoidance, adverse-excursion, abstain, and timeout/exit "
            "semantics create a more runtime-testable decision surface than repeating the closed "
            "momentum_ret_1 decision replay."
        ),
        "axis_tags": AXIS_TAGS,
        "exploration_coverage": {
            "mode": "unexplored_surface_discovery_not_single_axis_progression",
            "primary_unknown_axis": "decision_risk_holding_execution_cost_surface",
            "required_research_axes": [
                "target_or_label_surface",
                "feature_or_input_surface",
                "model_or_training_surface",
            ],
            "companion_axes": [
                "decision_surface",
                "risk_or_sizing_surface",
                "horizon_or_holding_policy",
                "evaluation_or_runtime_surface",
            ],
            "forbidden_research_shapes": [
                "feature_only_campaign",
                "label_only_campaign",
                "threshold_only_campaign",
                "repair_only_campaign",
                "momentum_ret_1_replay_repair",
            ],
            "novelty_claim": (
                "This campaign rotates away from closed momentum_ret_1 replay and asks whether cost/risk/holding "
                "semantics can prevent untradeable action streams before L5 candidate evidence."
            ),
        },
        "policy_binding": {
            "revision": "policy_contract_v2",
            "guard_set": "runtime_research",
            "guards": [
                "GUARD_001_ATTEMPT_BEFORE_DISPOSITION",
                "GUARD_002_RUNTIME_COMPLETION_TRUTH",
                "GUARD_003_CLAIM_BOUNDARY",
                "GUARD_004_ARTIFACT_IDENTITY",
                "GUARD_005_LOCKED_OOS",
                "GUARD_006_BRANCH_WORKTREE",
                "GUARD_007_OPERATIONAL_STABILITY",
            ],
        },
        "routing": {
            "primary_family": "experiment_design",
            "primary_skill": "spacesonar-experiment-design",
            "support_skills": ["spacesonar-evidence-provenance"],
            "required_gates": [
                "design_contract_check",
                "exploration_coverage_check",
                "campaign_proxy_runtime_parity_policy",
                "final_claim_guard",
            ],
        },
        "required_gates": [
            "campaign_lifecycle_spec_valid",
            "exploration_coverage_check",
            "proxy_runtime_parity_policy",
            "final_claim_guard",
        ],
        "claim_boundary": CLAIM_BOUNDARY,
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "experiment_design": experiment_design_payload(),
        "recipes": {
            "feature_recipe_id": FEATURE_RECIPE_ID,
            "label_recipe_id": LABEL_RECIPE_ID,
            "model_recipe_id": MODEL_RECIPE_ID,
            "decision_recipe_id": DECISION_RECIPE_ID,
            "eval_recipe_id": EVAL_RECIPE_ID,
            "surface_contract_id": SURFACE_ID,
        },
        "storage_contract": {
            "source_of_truth": CAMPAIGN_PATH.as_posix(),
            "surface_manifest": SURFACE_PATH.as_posix(),
            "sweep_manifest": SWEEP_PATH.as_posix(),
            "run_refs": RUN_REFS_PATH.as_posix(),
            "registry_rows": [
                REGISTRY_PATHS["campaign"].as_posix(),
                REGISTRY_PATHS["idea"].as_posix(),
                REGISTRY_PATHS["hypothesis"].as_posix(),
                REGISTRY_PATHS["surface"].as_posix(),
                REGISTRY_PATHS["sweep"].as_posix(),
            ],
            "durable_identity_policy": "repo_relative_paths_only",
        },
        "previous_campaign_boundary": {
            "campaign_id": PREVIOUS_CAMPAIGN_ID,
            "closeout": PREVIOUS_CLOSEOUT_PATH.as_posix(),
            "negative_memory": NEGATIVE_MEMORY_PATH.as_posix(),
            "carry_forward_rule": "do_not_reopen_momentum_ret_1_replay_as_candidate_repair",
        },
        "next_action": NEXT_WORK_ITEM_ID,
    }


def experiment_design_payload() -> dict[str, Any]:
    return {
        "idea_id": IDEA_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "hypothesis": (
            "A cost/risk/holding-aware abstain surface may reduce untradeable action streams by requiring the model "
            "or decision policy to account for entry friction, open_failed risk, adverse excursion, and timeout/exit "
            "before a score can become an MT5 decision."
        ),
        "decision_use": "abstain_capable_cost_risk_holding_gate",
        "comparison_baseline": [
            "no_trade_baseline",
            "closed_wave02_momentum_ret_1_replay_negative_memory_reference_only",
        ],
        "control_variables": [
            "FPMarkets US100 M5 closed-bar base frame",
            "split_set_v0 validation and research_oos roles",
            "locked final OOS excluded",
            "no inherited Wave01/Wave02 thresholds or candidates",
        ],
        "changed_variables": [
            "cost-adjusted tradeability label",
            "execution/open_failed avoidance feature context",
            "adverse-excursion-aware holding/exit semantics",
            "abstain-capable risk/holding decision policy",
        ],
        "kpi_interpretation_plan": {
            "required_for_kpi_bearing_result": True,
            "fields": [
                "trade_count",
                "net_profit",
                "profit_factor",
                "relative_drawdown_pct",
                "open_failed_count",
                "action_density",
            ],
            "axis_mapping": {
                "open_failed_count": "execution_cost_surface",
                "relative_drawdown_pct": "risk_or_holding_policy",
                "trade_count": "decision_surface_and_abstain_gate",
                "profit_factor": "cost_adjusted_tradeability_label",
            },
        },
        "attribution_axes": [
            "label_cost_adjustment",
            "feature_execution_context",
            "decision_abstain_policy",
            "holding_timeout_or_stop_policy",
            "model_family",
            "period_role",
        ],
        "expected_effect_probe": "lower_open_failed_density_and_lower_drawdown_without_claiming_economics_pass",
        "surface_rotation_rationale": (
            "The previous Wave02 campaign produced negative candidate-specific report evidence. The next useful "
            "question is whether explicit cost/risk/holding semantics prevent bad decision streams before L5, not "
            "whether the same momentum_ret_1 replay can be repaired."
        ),
        "search_shape": "broad",
        "next_surface_options": [
            "microstructure_cost_gate_surface",
            "session_risk_holding_surface",
            "volatility_stop_timeout_surface",
        ],
        "axis_balance_check": "multi_axis_surface_declared_not_single_axis_repair",
        "sample_scope": "split_set_v0_validation_and_research_oos_only_locked_final_oos_excluded",
        "success_criteria": [
            "proxy result produces repeated clue with declared changed_variables",
            "L4 runtime score/decision probe is feasible for promising model-bearing runs",
            "candidate-specific L5 evidence only if validation and research_oos report evidence justify it",
        ],
        "failure_criteria": [
            "negative or invalid candidate-specific runtime evidence",
            "open_failed dominance persists without reusable execution-semantics lesson",
            "no repeated surface clue after broad sweep",
        ],
        "invalid_conditions": [
            "locked_final_oos_used",
            "inherited selected baseline or threshold",
            "proxy-only closure for a valid model-bearing run",
            "missing manifest/receipt/hash for proof-bearing artifacts",
        ],
        "stop_conditions": [
            "close campaign negative memory if broad sweep cannot produce L4/L5-worthy clue",
            "rotate surface if cost/risk/holding semantics do not improve runtime-testability",
        ],
        "reopen_or_stop_condition": (
            "Reopen previous momentum_ret_1 replay only after explicit execution-semantics repair; otherwise keep "
            "this campaign focused on new cost/risk/holding surface evidence."
        ),
        "evidence_plan": [
            "campaign_manifest",
            "surface_manifest",
            "sweep_manifest",
            "run_manifest_and_receipt_per_materialized_run",
            "runtime_attempt_manifest_for_l4_follow_through",
            "candidate_summary_only_after_l5_routing",
        ],
        "claim_boundary": CLAIM_BOUNDARY,
        "legacy_relation": "blank_slate_no_legacy_winner_or_promotion_inheritance",
        "axis_tags": AXIS_TAGS,
        "broad_sweep": {
            "initial_batch_size": 6,
            "max_runs": 18,
            "budget_role": "wave02_second_campaign_rotation",
        },
        "extreme_sweep": "allowed_only_after_repeated_surface_clue",
        "micro_search_gate": "forbidden_until_repeated_runtime_testable_clue",
        "failure_memory": "record negative memory instead of carrying weak candidate repair",
    }


def idea_manifest(created_at: str) -> dict[str, Any]:
    return {
        "version": "idea_manifest_v1",
        "idea_id": IDEA_ID,
        "status": OPEN_STATUS,
        "created_at_utc": created_at,
        "axis_tags": AXIS_TAGS,
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_path": CAMPAIGN_PATH.as_posix(),
        "next_action": NEXT_WORK_ITEM_ID,
        "notes": "Wave02 second campaign idea opened as a new cost/risk/holding surface; no candidate claim.",
    }


def hypothesis_manifest(created_at: str) -> dict[str, Any]:
    design = experiment_design_payload()
    return {
        "version": "hypothesis_manifest_v1",
        "hypothesis_id": HYPOTHESIS_ID,
        "idea_id": IDEA_ID,
        "status": OPEN_STATUS,
        "created_at_utc": created_at,
        "hypothesis": design["hypothesis"],
        "decision_use": design["decision_use"],
        "comparison_baseline": design["comparison_baseline"],
        "changed_variables": design["changed_variables"],
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_path": CAMPAIGN_PATH.as_posix(),
        "next_action": NEXT_WORK_ITEM_ID,
        "notes": "Hypothesis open for broad surface scout only; no model run or candidate claim.",
    }


def surface_manifest(created_at: str) -> dict[str, Any]:
    return {
        "version": "surface_manifest_v1",
        "surface_id": SURFACE_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "campaign_id": CAMPAIGN_ID,
        "status": OPEN_STATUS,
        "created_at_utc": created_at,
        "axis_tags": AXIS_TAGS,
        "recipes": {
            "feature_recipe_id": FEATURE_RECIPE_ID,
            "label_recipe_id": LABEL_RECIPE_ID,
            "model_recipe_id": MODEL_RECIPE_ID,
            "decision_recipe_id": DECISION_RECIPE_ID,
            "eval_recipe_id": EVAL_RECIPE_ID,
            "split_recipe_id": "split_set_v0",
        },
        "claim_boundary": CLAIM_BOUNDARY,
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "storage_contract": {
            "source_of_truth": SURFACE_PATH.as_posix(),
            "campaign_manifest": CAMPAIGN_PATH.as_posix(),
            "surface_contract": RECIPE_PATHS[SURFACE_ID].as_posix(),
        },
        "next_action": NEXT_WORK_ITEM_ID,
    }


def sweep_manifest(created_at: str) -> dict[str, Any]:
    return {
        "version": "sweep_manifest_v1",
        "sweep_id": SWEEP_ID,
        "campaign_id": CAMPAIGN_ID,
        "surface_id": SURFACE_ID,
        "status": "open_no_runs_materialized",
        "created_at_utc": created_at,
        "sweep_type": "broad_cost_risk_holding_surface_scout",
        "axis_count": 7,
        "initial_batch_size": 6,
        "max_runs": 18,
        "run_refs": RUN_REFS_PATH.as_posix(),
        "claim_boundary": CLAIM_BOUNDARY,
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "next_action": NEXT_WORK_ITEM_ID,
        "notes": "Empty run_refs index until first batch specs are materialized.",
    }


def write_empty_run_refs(path: Path) -> None:
    write_csv_rows(
        path,
        [
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
        ],
        [],
    )


def next_work_item(created_at: str) -> dict[str, Any]:
    return {
        "version": "work_item_lite_v1",
        "work_item_id": NEXT_WORK_ITEM_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "primary_family": "experiment_design",
        "primary_skill": "spacesonar-experiment-design",
        "verification_profile": "writer_scope_first_batch_spec",
        "targets": [CAMPAIGN_PATH.as_posix(), SWEEP_PATH.as_posix(), RUN_REFS_PATH.as_posix()],
        "acceptance_criteria": [
            "materialize first batch run manifests for the cost/risk/holding surface",
            "each run declares changed_variables, feature/label/model/decision/eval recipes, and split roles",
            "no selected baseline, runtime authority, economics pass, live readiness, or Goal Achieve claim",
        ],
        "created_at_utc": created_at,
        "status": NEXT_STATUS,
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "next_action": "materialize first broad batch run specs for Wave02 cost/risk/holding campaign",
        "current_truth": {
            "campaign_manifest": CAMPAIGN_PATH.as_posix(),
            "surface_manifest": SURFACE_PATH.as_posix(),
            "sweep_manifest": SWEEP_PATH.as_posix(),
            "run_refs": RUN_REFS_PATH.as_posix(),
        },
        "unresolved_blockers": ["Wave02_cost_risk_holding_first_batch_specs_not_materialized"],
        "reopen_conditions": ["rerun campaign open writer if campaign registry or wave allocation is manually edited"],
        "missing_material_if_relevant": [
            "run_manifests_not_materialized",
            "proxy_results_absent",
            "l4_runtime_follow_through_absent",
            "candidate_evidence_absent",
            "operational_validation_not_started",
        ],
    }


def work_closeout(created_at: str, command_argv: list[str]) -> dict[str, Any]:
    artifacts = source_of_truth_paths()
    return {
        "version": "work_closeout_v1",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "next_work_item_id": NEXT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": created_at,
        "primary_family": "experiment_design",
        "primary_skill": "spacesonar-experiment-design",
        "support_skills": ["spacesonar-evidence-provenance"],
        "status": WORK_STATUS,
        "decision": "open_wave02_second_campaign",
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_paths": [
            PREVIOUS_CLOSEOUT_PATH.as_posix(),
            NEGATIVE_MEMORY_PATH.as_posix(),
            CAMPAIGN_PATH.as_posix(),
            SWEEP_PATH.as_posix(),
        ],
        "created_artifacts": [path.as_posix() for path in artifacts],
        "missing_evidence": [
            "run_manifests_not_materialized",
            "proxy_results_absent",
            "l4_runtime_follow_through_absent",
            "candidate_evidence_absent",
            "operational_validation_not_started",
        ],
        "next_action": NEXT_WORK_ITEM_ID,
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "provenance": {
            "source_inputs": [PREVIOUS_CLOSEOUT_PATH.as_posix(), NEGATIVE_MEMORY_PATH.as_posix()],
            "producer": " ".join(command_argv),
            "consumer": NEXT_WORK_ITEM_ID,
            "source_of_truth_paths": [path.as_posix() for path in artifacts],
            "environment_summary": {
                "python_executable": redact_path(sys.executable),
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                **git_state(),
            },
        },
    }


def source_of_truth_paths() -> list[Path]:
    return [
        CAMPAIGN_PATH,
        SURFACE_PATH,
        IDEA_PATH,
        HYPOTHESIS_PATH,
        SWEEP_PATH,
        RUN_REFS_PATH,
        *RECIPE_PATHS.values(),
        WORK_CLOSEOUT_PATH,
    ]


def redact_path(path: str) -> str:
    home = str(Path.home())
    return path.replace(home, "${USERPROFILE}")


def write_source_records(created_at: str, command_argv: list[str]) -> None:
    write_yaml(REPO_ROOT / CAMPAIGN_PATH, campaign_manifest(created_at))
    write_yaml(REPO_ROOT / SURFACE_PATH, surface_manifest(created_at))
    write_yaml(REPO_ROOT / IDEA_PATH, idea_manifest(created_at))
    write_yaml(REPO_ROOT / HYPOTHESIS_PATH, hypothesis_manifest(created_at))
    write_yaml(REPO_ROOT / SWEEP_PATH, sweep_manifest(created_at))
    write_empty_run_refs(REPO_ROOT / RUN_REFS_PATH)
    for path, payload in recipe_payloads(created_at).items():
        write_yaml(REPO_ROOT / path, payload)
    write_yaml(REPO_ROOT / WORK_CLOSEOUT_PATH, work_closeout(created_at, command_argv))


def update_wave_records(created_at: str) -> None:
    wave = load_yaml(REPO_ROOT / WAVE_ALLOCATION_PATH)
    wave["status"] = WAVE_STATUS
    wave["updated_at_utc"] = created_at
    wave["claim_boundary"] = CLAIM_BOUNDARY
    wave["next_action"] = NEXT_WORK_ITEM_ID
    allocations = wave.setdefault("campaign_allocations", [])
    allocation = {
        "campaign_id": CAMPAIGN_ID,
        "allocation_role": "wave02_second_campaign_cost_risk_holding_surface_rotation",
        "max_runs": 18,
        "initial_batch_size": 6,
        "allocation_reason": (
            "hypothesis_surface_width: second Wave02 campaign rotates to cost/risk/holding semantics after negative "
            "momentum_ret_1 replay; changed_axes: target_or_label_surface, feature_or_input_surface, "
            "model_or_training_surface, decision_surface, risk_or_sizing_surface, horizon_or_holding_policy, "
            "evaluation_or_runtime_surface; held_fixed_axes: FPMarkets US100 M5 closed-bar frame, split_set_v0 "
            "validation/research_oos, locked final OOS excluded, no inherited candidates; "
            "why_this_campaign_needs_more_or_less_than_default: default 18 run budget with initial 6-run broad batch."
        ),
        "budget": {
            "run_budget": 18,
            "hypothesis_surface_width": "new cost/risk/holding surface after negative first Wave02 campaign",
            "changed_axes": [
                "target_or_label_surface",
                "feature_or_input_surface",
                "model_or_training_surface",
                "decision_surface",
                "risk_or_sizing_surface",
                "horizon_or_holding_policy",
                "evaluation_or_runtime_surface",
            ],
            "held_fixed_axes": [
                "FPMarkets US100 M5 closed-bar base frame",
                "split_set_v0 validation and research_oos roles",
                "locked final OOS excluded",
                "no inherited Wave01 or Wave02 thresholds or candidates",
            ],
            "why_this_campaign_needs_more_or_less_than_default": "uses default Wave02 campaign budget with smaller first batch before L4 follow-through spend",
        },
        "status": OPEN_STATUS,
        "campaign_manifest": CAMPAIGN_PATH.as_posix(),
        "surface_manifest": SURFACE_PATH.as_posix(),
        "sweep_manifest": SWEEP_PATH.as_posix(),
        "claim_boundary": CLAIM_BOUNDARY,
        "next_action": NEXT_WORK_ITEM_ID,
        "notes": "Second Wave02 campaign opened as cost/risk/holding surface rotation; no candidate or runtime authority claim.",
    }
    replace_or_append_mapping(allocations, "campaign_id", CAMPAIGN_ID, allocation)
    write_yaml(REPO_ROOT / WAVE_ALLOCATION_PATH, wave)

    fields, rows = read_csv_rows(REPO_ROOT / CAMPAIGN_REFS_PATH)
    row = {
        "wave_id": WAVE_ID,
        "campaign_id": CAMPAIGN_ID,
        "campaign_path": CAMPAIGN_PATH.as_posix(),
        "allocation_role": "wave02_second_campaign_cost_risk_holding_surface_rotation",
        "status": OPEN_STATUS,
        "max_runs": "18",
        "initial_batch_size": "6",
        "claim_boundary": CLAIM_BOUNDARY,
        "next_action": NEXT_WORK_ITEM_ID,
        "notes": "Second Wave02 campaign opened as new cost/risk/holding surface; no candidate claim.",
    }
    if not fields:
        fields = list(row.keys())
    replace_or_append_mapping(rows, "campaign_id", CAMPAIGN_ID, row)
    write_csv_rows(REPO_ROOT / CAMPAIGN_REFS_PATH, fields, rows)


def replace_or_append_mapping(rows: list[dict[str, Any]], key: str, value: str, row: dict[str, Any]) -> None:
    for index, existing in enumerate(rows):
        if existing.get(key) == value:
            rows[index] = row
            return
    rows.append(row)


def update_control_records(created_at: str) -> None:
    next_work = next_work_item(created_at)
    write_yaml(REPO_ROOT / NEXT_WORK_ITEM_PATH, next_work)

    resume = load_yaml(REPO_ROOT / RESUME_CURSOR_PATH)
    resume["updated_at_utc"] = created_at
    resume["cursor_state"] = NEXT_STATUS
    resume["active_phase"] = NEXT_STATUS
    resume["active_work_item_id"] = NEXT_WORK_ITEM_ID
    resume["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    resume["next_action"] = next_work["next_action"]
    resume["unresolved_blockers"] = list(next_work["unresolved_blockers"])
    resume["latest_completed_work"] = {
        "work_item_id": WORK_ITEM_ID,
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_paths": [WORK_CLOSEOUT_PATH.as_posix(), CAMPAIGN_PATH.as_posix()],
    }
    resume["next_work_item"] = {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM_PATH.as_posix()}
    sources = resume.setdefault("current_truth_sources", [])
    for source in [CAMPAIGN_PATH.as_posix(), SURFACE_PATH.as_posix(), SWEEP_PATH.as_posix(), WORK_CLOSEOUT_PATH.as_posix()]:
        if source not in sources:
            sources.append(source)
    write_yaml(REPO_ROOT / RESUME_CURSOR_PATH, resume)

    goal = load_yaml(REPO_ROOT / GOAL_MANIFEST_PATH)
    goal["updated_at_utc"] = created_at
    goal["active_phase"] = NEXT_STATUS
    goal["claim_boundary"] = GOAL_CLAIM_BOUNDARY
    campaign_state = goal.setdefault("wave02_cost_risk_holding_campaign", {})
    campaign_state.update(
        {
            "campaign_id": CAMPAIGN_ID,
            "campaign_manifest": CAMPAIGN_PATH.as_posix(),
            "status": OPEN_STATUS,
            "claim_boundary": CLAIM_BOUNDARY,
            "next_work_item": NEXT_WORK_ITEM_ID,
        }
    )
    write_yaml(REPO_ROOT / GOAL_MANIFEST_PATH, goal)

    workspace = load_yaml(REPO_ROOT / WORKSPACE_STATE_PATH)
    workspace["updated_utc"] = created_at
    workspace["active_wave"] = {
        "wave_id": WAVE_ID,
        "status": WAVE_STATUS,
        "allocation": WAVE_ALLOCATION_PATH.as_posix(),
        "closeout": None,
    }
    workspace["active_campaign"] = {
        "campaign_id": CAMPAIGN_ID,
        "status": OPEN_STATUS,
        "manifest": CAMPAIGN_PATH.as_posix(),
    }
    workspace["active_work_item"] = {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM_PATH.as_posix()}
    workspace["current_claim_boundary"] = NEXT_CLAIM_BOUNDARY
    workspace["next_action"] = next_work["next_action"]
    workspace["unresolved_blockers"] = list(next_work["unresolved_blockers"])
    counts = workspace.setdefault("summary_counts", {})
    counts["wave02_campaign_002_open"] = {
        "campaign_id": CAMPAIGN_ID,
        "initial_batch_size": 6,
        "max_runs": 18,
        "candidate_count": 0,
        "l5_candidate_count": 0,
    }
    write_yaml(REPO_ROOT / WORKSPACE_STATE_PATH, workspace)


def update_registries(created_at: str) -> None:
    upsert_csv_row(
        REPO_ROOT / REGISTRY_PATHS["idea"],
        "idea_id",
        {
            "idea_id": IDEA_ID,
            "status": OPEN_STATUS,
            "created_at_utc": created_at,
            "axis_tags": AXIS_TAGS,
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_path": CAMPAIGN_PATH.as_posix(),
            "next_action": NEXT_WORK_ITEM_ID,
            "notes": "Second Wave02 cost/risk/holding idea opened; no candidate claim.",
        },
    )
    upsert_csv_row(
        REPO_ROOT / REGISTRY_PATHS["hypothesis"],
        "hypothesis_id",
        {
            "hypothesis_id": HYPOTHESIS_ID,
            "idea_id": IDEA_ID,
            "status": OPEN_STATUS,
            "hypothesis": experiment_design_payload()["hypothesis"],
            "decision_use": "abstain_capable_cost_risk_holding_gate",
            "comparison_baseline": "no_trade_baseline;closed_wave02_momentum_ret_1_negative_memory_reference_only",
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_path": CAMPAIGN_PATH.as_posix(),
            "next_action": NEXT_WORK_ITEM_ID,
            "notes": "Open hypothesis for broad surface scout; no model run or candidate claim.",
        },
    )
    upsert_csv_row(
        REPO_ROOT / REGISTRY_PATHS["surface"],
        "surface_id",
        {
            "surface_id": SURFACE_ID,
            "hypothesis_id": HYPOTHESIS_ID,
            "status": OPEN_STATUS,
            "created_at_utc": created_at,
            "surface_path": SURFACE_PATH.as_posix(),
            "label_recipe_id": LABEL_RECIPE_ID,
            "feature_recipe_id": FEATURE_RECIPE_ID,
            "feature_recipe_mix_id": "not_applicable_no_mix_in_standard_campaign_open",
            "model_recipe_id": MODEL_RECIPE_ID,
            "decision_recipe_id": DECISION_RECIPE_ID,
            "split_recipe_id": "split_set_v0",
            "eval_recipe_id": EVAL_RECIPE_ID,
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_path": CAMPAIGN_PATH.as_posix(),
            "next_action": NEXT_WORK_ITEM_ID,
            "notes": "Surface open only; no feature count, model family, threshold, or candidate fixed.",
        },
    )
    upsert_csv_row(
        REPO_ROOT / REGISTRY_PATHS["sweep"],
        "sweep_id",
        {
            "sweep_id": SWEEP_ID,
            "campaign_id": CAMPAIGN_ID,
            "surface_id": SURFACE_ID,
            "status": "open_no_runs_materialized",
            "created_at_utc": created_at,
            "sweep_path": SWEEP_PATH.as_posix(),
            "sweep_type": "broad_cost_risk_holding_surface_scout",
            "axis_count": "7",
            "run_ref_path": RUN_REFS_PATH.as_posix(),
            "evidence_boundary": CLAIM_BOUNDARY,
            "evidence_path": CAMPAIGN_PATH.as_posix(),
            "next_action": NEXT_WORK_ITEM_ID,
            "notes": "Empty run_refs index until first batch specs are materialized.",
        },
    )
    upsert_csv_row(
        REPO_ROOT / REGISTRY_PATHS["campaign"],
        "campaign_id",
        {
            "campaign_id": CAMPAIGN_ID,
            "status": OPEN_STATUS,
            "created_at_utc": created_at,
            "campaign_path": CAMPAIGN_PATH.as_posix(),
            "objective": "Open Wave02 cost/risk/holding surface after negative tradeability replay campaign.",
            "axis_tags": AXIS_TAGS,
            "primary_family": "experiment_design",
            "primary_skill": "spacesonar-experiment-design",
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_path": CAMPAIGN_PATH.as_posix(),
            "next_action": NEXT_WORK_ITEM_ID,
            "notes": "Campaign opened as new multi-axis surface, not momentum_ret_1 repair.",
        },
    )
    upsert_csv_row(
        REPO_ROOT / REGISTRY_PATHS["wave"],
        "wave_id",
        {
            "wave_id": WAVE_ID,
            "status": WAVE_STATUS,
            "created_at_utc": "2026-06-27T12:15:00Z",
            "wave_path": WAVE_ALLOCATION_PATH.as_posix(),
            "allocation_goal": "Wave02 continues with cost/risk/holding surface after negative first campaign.",
            "max_runs": "72",
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_path": WAVE_ALLOCATION_PATH.as_posix(),
            "next_action": NEXT_WORK_ITEM_ID,
            "notes": "Campaign 002 open; no selected baseline, runtime authority, economics pass, live readiness, or Goal Achieve.",
        },
    )
    upsert_csv_row(
        REPO_ROOT / REGISTRY_PATHS["goal"],
        "goal_id",
        {
            "goal_id": GOAL_ID,
            "status": "active_wave02_pre_operational_research",
            "active_phase": NEXT_STATUS,
            "next_work_item": NEXT_WORK_ITEM_ID,
            "claim_boundary": GOAL_CLAIM_BOUNDARY,
        },
    )
    update_recipe_registry(created_at)
    update_artifact_registry(created_at)


def update_recipe_registry(created_at: str) -> None:
    recipe_types = {
        FEATURE_RECIPE_ID: "feature",
        LABEL_RECIPE_ID: "label",
        MODEL_RECIPE_ID: "model",
        DECISION_RECIPE_ID: "decision",
        EVAL_RECIPE_ID: "eval",
        SURFACE_ID: "surface_contract",
    }
    for recipe_id, path in RECIPE_PATHS.items():
        upsert_csv_row(
            REPO_ROOT / REGISTRY_PATHS["recipe"],
            "recipe_id",
            {
                "recipe_id": recipe_id,
                "recipe_type": recipe_types[recipe_id],
                "status": "skeleton_open_no_candidate",
                "created_at_utc": created_at,
                "recipe_path": path.as_posix(),
                "sha256": sha256(REPO_ROOT / path),
                "runtime_feasibility": "requires_l4_follow_through_for_model_bearing_runs",
                "claim_boundary": "recipe_skeleton_only_no_candidate_no_runtime_authority_no_economics_pass",
                "next_action": NEXT_WORK_ITEM_ID,
                "notes": "Wave02 campaign 002 recipe skeleton; no fixed candidate or operating claim.",
            },
        )


def update_artifact_registry(created_at: str) -> None:
    artifacts = {
        "artifact_wave02_cost_risk_holding_campaign_manifest_v0": ("campaign_manifest", CAMPAIGN_PATH),
        "artifact_wave02_cost_risk_holding_surface_manifest_v0": ("surface_manifest", SURFACE_PATH),
        "artifact_wave02_cost_risk_holding_sweep_manifest_v0": ("sweep_manifest", SWEEP_PATH),
        "artifact_wave02_cost_risk_holding_run_refs_v0": ("run_refs", RUN_REFS_PATH),
        "artifact_wave02_cost_risk_holding_campaign_open_closeout_v0": ("work_closeout", WORK_CLOSEOUT_PATH),
    }
    for artifact_id, (artifact_type, path) in artifacts.items():
        full = REPO_ROOT / path
        upsert_csv_row(
            REPO_ROOT / REGISTRY_PATHS["artifact"],
            "artifact_id",
            {
                "artifact_id": artifact_id,
                "run_id": "",
                "bundle_id": "",
                "attempt_id": "",
                "artifact_type": artifact_type,
                "path_or_uri": path.as_posix(),
                "sha256": sha256(full),
                "size_bytes": str(full.stat().st_size),
                "availability": "present_hash_recorded",
                "producer_command": "python foundation/pipelines/open_wave02_cost_risk_holding_campaign.py --write-control-records",
                "regeneration_command": "python foundation/pipelines/open_wave02_cost_risk_holding_campaign.py --write-control-records",
                "source_of_truth": CAMPAIGN_PATH.as_posix(),
                "consumer": NEXT_WORK_ITEM_ID,
                "claim_boundary": CLAIM_BOUNDARY,
                "notes": f"Wave02 campaign 002 {artifact_type}",
            },
        )


def writer_scope_self_check() -> dict[str, Any]:
    failures: list[str] = []
    for path in source_of_truth_paths():
        if not (REPO_ROOT / path).exists():
            failures.append(f"missing:{path.as_posix()}")
    for path in [NEXT_WORK_ITEM_PATH, WORKSPACE_STATE_PATH, WAVE_ALLOCATION_PATH, CAMPAIGN_REFS_PATH]:
        if not (REPO_ROOT / path).exists():
            failures.append(f"missing:{path.as_posix()}")

    campaign = load_yaml(REPO_ROOT / CAMPAIGN_PATH)
    if campaign.get("status") != OPEN_STATUS:
        failures.append("campaign_status_mismatch")
    if campaign.get("claim_boundary") != CLAIM_BOUNDARY:
        failures.append("campaign_claim_boundary_mismatch")
    if "selected_baseline" not in campaign.get("forbidden_claims", []):
        failures.append("campaign_forbidden_claims_missing")

    wave = load_yaml(REPO_ROOT / WAVE_ALLOCATION_PATH)
    allocations = wave.get("campaign_allocations") or []
    allocation = next((item for item in allocations if item.get("campaign_id") == CAMPAIGN_ID), None)
    if not allocation or allocation.get("status") != OPEN_STATUS:
        failures.append("wave_allocation_missing_or_status_mismatch")

    _, refs = read_csv_rows(REPO_ROOT / CAMPAIGN_REFS_PATH)
    ref = next((row for row in refs if row.get("campaign_id") == CAMPAIGN_ID), None)
    if not ref or ref.get("status") != OPEN_STATUS:
        failures.append("wave_campaign_ref_missing_or_status_mismatch")

    workspace = load_yaml(REPO_ROOT / WORKSPACE_STATE_PATH)
    if (workspace.get("active_campaign") or {}).get("campaign_id") != CAMPAIGN_ID:
        failures.append("workspace_active_campaign_mismatch")
    if (workspace.get("active_work_item") or {}).get("work_item_id") != NEXT_WORK_ITEM_ID:
        failures.append("workspace_next_work_mismatch")

    forbidden_terms = ["runtime_authority", "economics_pass", "live_readiness", "goal_achieve"]
    if not all(f"no_{term}" in CLAIM_BOUNDARY or term == "goal_achieve" for term in forbidden_terms):
        failures.append("claim_boundary_missing_forbidden_terms")
    return {"status": "passed" if not failures else "failed", "failures": failures}


def build_command_argv(args: argparse.Namespace) -> list[str]:
    command = ["python", "foundation/pipelines/open_wave02_cost_risk_holding_campaign.py"]
    if args.write_control_records:
        command.append("--write-control-records")
    if args.dry_run:
        command.append("--dry-run")
    return command


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Open Wave02 campaign 002 cost/risk/holding surface.")
    parser.add_argument("--write-control-records", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    created_at = utc_now()
    command_argv = build_command_argv(args)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "decision": "open_wave02_second_campaign",
                    "campaign_id": CAMPAIGN_ID,
                    "next_work_item": NEXT_WORK_ITEM_ID,
                    "claim_boundary": CLAIM_BOUNDARY,
                    "created_paths": [path.as_posix() for path in source_of_truth_paths()],
                },
                indent=2,
            )
        )
        return 0

    write_source_records(created_at, command_argv)
    if args.write_control_records:
        update_wave_records(created_at)
        update_control_records(created_at)
        update_registries(created_at)
    self_check = writer_scope_self_check()
    if self_check["status"] != "passed":
        print(
            json.dumps(
                {
                    "status": "writer_scope_self_check_failed",
                    "self_check": self_check,
                    "campaign_id": CAMPAIGN_ID,
                    "claim_boundary": CLAIM_BOUNDARY,
                },
                indent=2,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "status": OPEN_STATUS,
                "campaign_id": CAMPAIGN_ID,
                "next_work_item": NEXT_WORK_ITEM_ID,
                "writer_scope_self_check": self_check["status"],
                "claim_boundary": CLAIM_BOUNDARY,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
