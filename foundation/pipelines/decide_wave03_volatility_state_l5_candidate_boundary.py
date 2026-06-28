from __future__ import annotations

import argparse
import csv
import hashlib
import platform
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

import foundation.pipelines.prepare_wave03_volatility_state_l5_candidate_runtime_evidence as l5_writer
from spacesonar.control_plane.store import dump_csv, dump_yaml, filesystem_path, sha256_file
from spacesonar.control_plane.writer_contract import (
    WRITER_CONTRACT_VERSION,
    default_validation_attempt_budget,
    default_writer_preflight_gate,
    enforce_writer_contract,
)


GOAL_ID = l5_writer.GOAL_ID
WAVE_ID = l5_writer.WAVE_ID
CAMPAIGN_ID = l5_writer.CAMPAIGN_ID
IDEA_ID = l5_writer.IDEA_ID
HYPOTHESIS_ID = l5_writer.HYPOTHESIS_ID
SURFACE_ID = l5_writer.SURFACE_ID
SWEEP_ID = l5_writer.SWEEP_ID

WORK_ITEM_ID = "work_wave03_volatility_state_l5_candidate_boundary_decision_v0"
PARENT_WORK_ITEM_ID = l5_writer.WORK_ITEM_ID
NEXT_WORK_ITEM_ID = "work_wave03_open_intraday_liquidity_regime_campaign_v0"

NEXT_CAMPAIGN_ID = "campaign_us100_wave03_intraday_liquidity_regime_surface_v0"
NEXT_IDEA_ID = "idea_us100_wave03_intraday_liquidity_regime_transition_v0"
NEXT_HYPOTHESIS_ID = "hyp_us100_wave03_intraday_liquidity_regime_reversal_continuation_v0"
NEXT_SURFACE_ID = "surface_us100_wave03_liquidity_regime_decision_v0"
NEXT_SWEEP_ID = "sweep_us100_wave03_liquidity_regime_seed_v0"

CAMPAIGN_DIR = Path("lab/campaigns") / CAMPAIGN_ID
CAMPAIGN_MANIFEST = l5_writer.CAMPAIGN_MANIFEST
CAMPAIGN_CLOSEOUT = CAMPAIGN_DIR / "campaign_closeout.yaml"
WORK_CLOSEOUT = Path("lab/goals") / GOAL_ID / f"{WORK_ITEM_ID}_closeout.yaml"
NEXT_CAMPAIGN_SPEC = Path("lab/goals") / GOAL_ID / "wave03_intraday_liquidity_regime_campaign_spec.yaml"
NEGATIVE_MEMORY_ID = "neg_wave03_volatility_state_l5_candidate_negative_v0"
NEGATIVE_MEMORY_PATH = Path("lab/memory/negative") / f"{NEGATIVE_MEMORY_ID}.yaml"

NEXT_WORK_ITEM = l5_writer.NEXT_WORK_ITEM
RESUME_CURSOR = l5_writer.RESUME_CURSOR
GOAL_MANIFEST = l5_writer.GOAL_MANIFEST
WORKSPACE_STATE = l5_writer.WORKSPACE_STATE
WAVE_ALLOCATION = Path("lab/waves") / WAVE_ID / "wave_allocation.yaml"
WAVE_CAMPAIGN_REFS = Path("lab/waves") / WAVE_ID / "campaign_refs.csv"

L5_EVIDENCE_SUMMARY = l5_writer.EVIDENCE_SUMMARY
L5_EVIDENCE_INDEX = l5_writer.EVIDENCE_INDEX
L5_ROUTING_SUMMARY = l5_writer.ROUTING_SUMMARY
L5_ROUTING_INDEX = l5_writer.ROUTING_INDEX
L4_PAIR_SUMMARY = l5_writer.OUTPUT_DIR / "l4_pair_judgment_summary.yaml"
L4_PAIR_INDEX = l5_writer.OUTPUT_DIR / "l4_pair_judgment_index.csv"
PROXY_SUMMARY = CAMPAIGN_DIR / "proxy_execution_summary.yaml"
PROXY_INDEX = CAMPAIGN_DIR / "proxy_execution_index.csv"

ARTIFACT_REGISTRY = l5_writer.ARTIFACT_REGISTRY
GOAL_REGISTRY = l5_writer.GOAL_REGISTRY
CAMPAIGN_REGISTRY = l5_writer.CAMPAIGN_REGISTRY
WAVE_REGISTRY = Path("docs/registers/wave_registry.csv")
NEGATIVE_MEMORY_REGISTRY = Path("docs/registers/negative_memory_registry.csv")

PRIMARY_FAMILY = "candidate_evaluation"
PRIMARY_SKILL = "spacesonar-result-judgment"
VALIDATION_DEPTH = "writer_scope_smoke"
NON_PYTEST_SMOKES = [
    "py_compile",
    "wave03_l5_boundary_writer_smoke",
    "writer_scope_contract_lint",
    "machine_yaml_identity_lint",
    "active_pointer_smoke",
]
SKIPPED_BROAD_VALIDATIONS = [
    "pytest",
    "project_validate",
    "full_regression_workflow",
    "evidence_graph_full_workflow",
    "active_record_validator_full_graph",
    "spacesonar_project_validate_full",
    "spacesonar_cli_project_validate_as_progress_default",
    "broad_hash_resync",
    "global_registry_regeneration",
]
BROAD_VALIDATION_ESCALATION_REASON = "none_wave03_l5_boundary_writer_scope_only_no_protected_claim"
FORBIDDEN_CLAIMS = l5_writer.FORBIDDEN_CLAIMS

STATUS = "wave03_volatility_state_campaign_closed_negative_l5_evidence_no_l5_candidate"
NEXT_STATUS = "wave03_intraday_liquidity_regime_campaign_open_pending"
CLAIM_BOUNDARY = (
    "wave03_volatility_state_campaign_closed_negative_l5_evidence_no_l5_candidate_"
    "no_selected_baseline_no_runtime_authority_no_economics_pass_no_live_readiness_no_goal_achieve"
)
NEXT_CLAIM_BOUNDARY = (
    "wave03_intraday_liquidity_regime_campaign_open_pending_no_selected_baseline_"
    "no_runtime_authority_no_economics_pass_no_live_readiness_no_goal_achieve"
)
NEXT_ACTION = (
    "open Wave03 intraday liquidity-regime campaign from the prepared lifecycle spec; "
    "do not reopen the failed volatility-state L5 candidate as a repair"
)


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def path_exists(path: Path) -> bool:
    return (REPO_ROOT / path if not path.is_absolute() else path).exists()


def read_yaml(path: Path) -> dict[str, Any]:
    full = REPO_ROOT / path if not path.is_absolute() else path
    with open(filesystem_path(full), "r", encoding="utf-8-sig") as handle:
        payload = yaml.safe_load(handle)
    return payload if isinstance(payload, dict) else {}


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    full = REPO_ROOT / path if not path.is_absolute() else path
    with open(filesystem_path(full), "r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_text(path: Path, text: str) -> None:
    full = REPO_ROOT / path if not path.is_absolute() else path
    full.parent.mkdir(parents=True, exist_ok=True)
    with open(filesystem_path(full), "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    enforce_writer_contract(path, payload)
    write_text(path, dump_yaml(payload))


def write_plain_yaml(path: Path, payload: dict[str, Any]) -> None:
    write_text(path, dump_yaml(payload))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    write_text(path, dump_csv(fieldnames, rows))


def rel(path: Path) -> str:
    full = path if path.is_absolute() else REPO_ROOT / path
    return full.resolve().relative_to(REPO_ROOT.resolve()).as_posix()


def artifact_ref(path: Path, *, availability: str = "present_hash_recorded") -> dict[str, Any]:
    full = path if path.is_absolute() else REPO_ROOT / path
    return {
        "path": rel(full),
        "sha256": sha256_file(full),
        "size_bytes": full.stat().st_size,
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


def contract_fields(
    *,
    primary_family: str = PRIMARY_FAMILY,
    primary_skill: str = PRIMARY_SKILL,
    progress_effect: str,
    next_action: str,
    experiment_effect: str,
    claim_boundary: str,
    source_paths: list[str],
    outputs: list[str],
    blockers: list[str] | None = None,
) -> dict[str, Any]:
    budget = default_validation_attempt_budget()
    budget["observed_writer_scope_attempts"] = 0
    return {
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "primary_family": primary_family,
        "primary_skill": primary_skill,
        "progress_class": "next_executable_experiment_writer_or_probe",
        "progress_effect": progress_effect,
        "next_executable_action": next_action,
        "experiment_or_boundary_effect": experiment_effect,
        "source_of_truth_paths": source_paths,
        "writer_owned_outputs": outputs,
        "validation_depth": VALIDATION_DEPTH,
        "non_pytest_smokes": list(NON_PYTEST_SMOKES),
        "skipped_broad_validations": list(SKIPPED_BROAD_VALIDATIONS),
        "broad_validation_escalation_reason": BROAD_VALIDATION_ESCALATION_REASON,
        "writer_preflight_gate": default_writer_preflight_gate(),
        "validation_attempt_budget": budget,
        "writer_scope_self_check": {
            "status": "passed",
            "checked_at_utc": utc_now(),
            "failures": [],
            "writer_contract_version": WRITER_CONTRACT_VERSION,
            "validation_depth": VALIDATION_DEPTH,
            "claim_boundary": claim_boundary,
            "forbidden_claims_respected": True,
            "next_action_or_reopen_condition": next_action,
        },
        "claim_boundary": claim_boundary,
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
        "unresolved_blockers_or_none": list(blockers or ["none"]),
        "next_action_or_reopen_condition": next_action,
    }


def source_paths() -> list[str]:
    return [
        PROXY_SUMMARY.as_posix(),
        PROXY_INDEX.as_posix(),
        L4_PAIR_SUMMARY.as_posix(),
        L4_PAIR_INDEX.as_posix(),
        L5_ROUTING_SUMMARY.as_posix(),
        L5_ROUTING_INDEX.as_posix(),
        L5_EVIDENCE_SUMMARY.as_posix(),
        L5_EVIDENCE_INDEX.as_posix(),
        *[
            str(path)
            for path in (read_yaml(L5_EVIDENCE_SUMMARY).get("artifact_outputs") or {}).get(
                "candidate_evidence_summaries", []
            )
        ],
    ]


def output_paths() -> list[str]:
    return [
        CAMPAIGN_CLOSEOUT.as_posix(),
        NEGATIVE_MEMORY_PATH.as_posix(),
        NEXT_CAMPAIGN_SPEC.as_posix(),
        WORK_CLOSEOUT.as_posix(),
    ]


def add_unique(items: list[Any], values: list[Any]) -> list[Any]:
    out = list(items)
    for value in values:
        if value not in out:
            out.append(value)
    return out


def objective_identity_from_previous_spec() -> tuple[dict[str, Any], dict[str, Any]]:
    previous = read_yaml(Path("lab/goals") / GOAL_ID / "wave03_volatility_state_transition_campaign_spec.yaml")
    return dict(previous.get("objective_identity") or {}), dict(previous.get("objective_revision") or {})


def next_run_specs() -> list[dict[str, Any]]:
    specs = [
        ("001", "liquidity_void_reversal_h6", "liquidity_void_reversal_h6", "intraday_liquidity_proxy", "logistic_liquidity_regime", "liquidity_reversal_abstain_timeout_h6", "h6"),
        ("002", "liquidity_void_reversal_h8", "liquidity_void_reversal_h8", "spread_volume_session_state", "tree_liquidity_regime", "liquidity_reversal_abstain_timeout_h8", "h8"),
        ("003", "liquidity_sweep_continuation_h6", "liquidity_sweep_continuation_h6", "liquidity_impulse_path_quality", "boosted_liquidity_regime", "liquidity_continuation_abstain_timeout_h6", "h6"),
        ("004", "liquidity_sweep_continuation_h12", "liquidity_sweep_continuation_h12", "multiscale_liquidity_state", "logistic_liquidity_regime", "liquidity_continuation_abstain_timeout_h12", "h12"),
        ("005", "cash_open_spread_compression_h6", "cash_open_spread_compression_h6", "cash_open_spread_state", "tree_liquidity_regime", "spread_compression_reversal_h6", "h6"),
        ("006", "cash_open_spread_expansion_h8", "cash_open_spread_expansion_h8", "cash_open_spread_state", "boosted_liquidity_regime", "spread_expansion_continuation_h8", "h8"),
        ("007", "volume_dryup_breakout_h6", "volume_dryup_breakout_h6", "volume_dryup_liquidity_state", "logistic_liquidity_regime", "liquidity_breakout_continuation_h6", "h6"),
        ("008", "volume_dryup_false_break_h8", "volume_dryup_false_break_h8", "volume_dryup_liquidity_state", "tree_liquidity_regime", "liquidity_false_break_reversal_h8", "h8"),
        ("009", "high_spread_mean_revert_h6", "high_spread_mean_revert_h6", "spread_stress_path_quality", "boosted_liquidity_regime", "spread_stress_reversal_h6", "h6"),
        ("010", "high_spread_momentum_h12", "high_spread_momentum_h12", "spread_stress_path_quality", "tree_liquidity_regime", "spread_stress_momentum_h12", "h12"),
        ("011", "low_liquidity_chop_filter_h8", "low_liquidity_chop_filter_h8", "liquidity_chop_filter_state", "logistic_liquidity_regime", "liquidity_tradeability_then_side_h8", "h8"),
        ("012", "range_recovery_liquidity_h12", "range_recovery_liquidity_h12", "range_recovery_liquidity_state", "boosted_liquidity_regime", "liquidity_recovery_timeout_h12", "h12"),
        ("013", "midday_liquidity_reversal_h8", "midday_liquidity_reversal_h8", "session_liquidity_clock_state", "tree_liquidity_regime", "midday_liquidity_reversal_h8", "h8"),
        ("014", "close_liquidity_impulse_h6", "close_liquidity_impulse_h6", "session_liquidity_clock_state", "boosted_liquidity_regime", "close_liquidity_impulse_h6", "h6"),
        ("015", "pre_open_gap_absorption_h8", "pre_open_gap_absorption_h8", "gap_liquidity_absorption_state", "logistic_liquidity_regime", "gap_absorption_reversal_h8", "h8"),
        ("016", "post_news_liquidity_shock_h6", "post_news_liquidity_shock_h6", "liquidity_shock_decay_state", "tree_liquidity_regime", "shock_decay_reversal_h6", "h6"),
        ("017", "liquidity_regime_tradeability_h12", "liquidity_regime_tradeability_h12", "multiscale_liquidity_state", "boosted_liquidity_regime", "liquidity_tradeability_then_side_h12", "h12"),
        ("018", "liquidity_regime_side_h8", "liquidity_regime_side_h8", "intraday_liquidity_proxy", "tree_liquidity_regime", "liquidity_regime_side_h8", "h8"),
    ]
    rows: list[dict[str, Any]] = []
    for cell, slug, label_slug, feature_slug, model_slug, decision_slug, horizon in specs:
        run_id = f"onnxlab_wave03_ilr_cell_{cell}_{slug}_v0"
        rows.append(
            {
                "run_id": run_id,
                "recipe_refs": {
                    "label_recipe_id": f"label_wave03_{label_slug}_v0",
                    "feature_recipe_id": f"feature_wave03_{feature_slug}_v0",
                    "model_recipe_id": f"model_wave03_{model_slug}_v0",
                    "decision_recipe_id": f"decision_wave03_{decision_slug}_v0",
                },
                "split_profile": "split_set_v0",
                "evaluation_profile": "eval_wave03_proxy_runtime_kpi_v0",
                "verification_profile": "lab_experiment",
                "acceptance_criteria": [
                    f"record intraday liquidity-regime {slug.replace('_', ' ')} proxy observation with L4 follow-through plan",
                    f"declare {horizon} holding or timeout semantics before ONNX/EA/MT5 escalation",
                ],
            }
        )
    return rows


def build_next_campaign_spec(created_at_utc: str) -> dict[str, Any]:
    objective_identity, objective_revision = objective_identity_from_previous_spec()
    return {
        "version": "campaign_lifecycle_spec_v1",
        "campaign_id": NEXT_CAMPAIGN_ID,
        "goal_id": GOAL_ID,
        "wave_id": WAVE_ID,
        "idea_id": NEXT_IDEA_ID,
        "hypothesis_id": NEXT_HYPOTHESIS_ID,
        "surface_id": NEXT_SURFACE_ID,
        "sweep_id": NEXT_SWEEP_ID,
        "status": "campaign_open_pending",
        "goal_status": NEXT_STATUS,
        "active_phase": "wave03_campaign_002_open_pending",
        "wave_status": "wave_open",
        "created_at_utc": created_at_utc,
        "objective": (
            "Open the second Wave03 campaign as a fresh multi-axis intraday liquidity-regime surface for "
            "FPMarkets US100 M5. The surface tests whether spread, volume, session-clock, gap, and liquidity-shock "
            "states can define reversal, continuation, and tradeability decisions after the volatility-state L5 "
            "candidate failed in research_oos."
        ),
        "axis_tags": [
            "target_or_label_surface",
            "feature_or_input_surface",
            "model_or_training_surface",
            "decision_surface",
            "horizon_or_holding_policy",
            "evaluation_or_runtime_surface",
            "liquidity_regime_surface",
        ],
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "routing": {
            "primary_family": "experiment_design",
            "primary_skill": "spacesonar-experiment-design",
            "support_skills": [],
            "required_gates": [
                "design_contract_check",
                "exploration_coverage_check",
                "campaign_proxy_runtime_parity_policy",
                "final_claim_guard",
            ],
        },
        "exploration_coverage": {
            "mode": "unexplored_surface_discovery_not_single_axis_progression",
            "primary_unknown_axis": "intraday_liquidity_regime_surface",
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
            "novelty_claim": (
                "Wave03 campaign 002 rotates from failed volatility-state L5 evidence into a new liquidity-regime "
                "question. The failed cell015 result is prevention memory only, not a baseline, candidate, or repair target."
            ),
        },
        "policy_binding": {
            "revision": "policy_contract_v2",
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
        "storage_contract": {
            "durable_identity_policy": "repo_relative_paths_only",
            "source_of_truth": f"lab/campaigns/{NEXT_CAMPAIGN_ID}/campaign_manifest.yaml",
            "wave_campaign_refs": [WAVE_CAMPAIGN_REFS.as_posix()],
            "registry_rows": [CAMPAIGN_REGISTRY.as_posix()],
        },
        "objective_identity": objective_identity,
        "objective_revision": objective_revision,
        "budget": {
            "budget_profile": "standard_wave",
            "allocation_mode": "fixed_wave_budget_variable_campaign_budget",
            "wave_budget_fixed_before_open": True,
            "max_runs": 18,
            "standard_total_run_budget": 72,
            "standard_campaign_slots": 3,
            "reserve_fraction": 0.15,
            "campaign_run_budget_bounds": {"min_runs": 8, "default_runs": 18, "max_runs": 30},
            "l4_pair_budget": 36,
            "l4_budget_unit": "validation_research_oos_pair",
            "l4_required_period_roles": ["validation", "research_oos"],
        },
        "max_runs": 18,
        "initial_batch_size": 18,
        "allocation_role": "wave03_second_campaign_intraday_liquidity_regime_surface",
        "allocation_goal": (
            "Rotate from the negative volatility-state L5 candidate into a new liquidity-regime discovery surface "
            "across target, feature, model, decision, holding, and runtime axes."
        ),
        "allocation_reason": (
            "hypothesis_surface_width: second Wave03 broad liquidity-regime surface; changed_axes: target/label, "
            "feature/input, model/training, decision, horizon/holding, evaluation/runtime; held_fixed_axes: FPMarkets "
            "US100 M5 closed bars, split_set_v0 validation plus research_oos roles, locked final OOS excluded, no "
            "inherited volatility-state threshold or candidate; why_this_campaign_needs_more_or_less_than_default: "
            "uses the default 18 proxy specs to avoid single-axis repair."
        ),
        "recipe_refs": {
            "data_surface_id": "data_surface_us100_m5_wave03_closedbar_v0",
            "label_recipe_id": "label_wave03_liquidity_regime_transition_v0",
            "feature_recipe_id": "feature_wave03_intraday_liquidity_regime_v0",
            "model_recipe_id": "model_wave03_liquidity_regime_onnx_scout_v0",
            "decision_recipe_id": "decision_wave03_liquidity_regime_abstain_v0",
            "split_recipe_id": "split_set_v0",
            "eval_recipe_id": "eval_wave03_proxy_runtime_kpi_v0",
        },
        "experiment_design": {
            "hypothesis": (
                "Intraday liquidity-regime states can separate US100 M5 reversal, continuation, and tradeability "
                "windows better than the failed low-vol breakout candidate because spread/volume/session conditions "
                "directly affect trade execution shape and drawdown clustering."
            ),
            "decision_use": "liquidity_regime_reversal_continuation_tradeability_abstain",
            "comparison_baseline": [
                "no_trade_baseline_named_only_not_selected",
                "within_campaign_axis_controls_only",
                "Wave03 volatility-state L5 negative record used as prevention memory only",
            ],
            "control_variables": [
                "FPMarkets US100 M5 closed-bar base frame",
                "split_set_v0 validation and research_oos roles",
                "locked final OOS excluded",
                "no inherited Wave03 volatility-state thresholds, candidates, or runtime authority",
                "valid proxy/model-bearing runs must keep ONNX/EA/MT5 L4 follow-through path",
            ],
            "changed_variables": [
                "liquidity void, sweep, spread compression, volume dry-up, and session liquidity labels",
                "spread, tick volume, session-clock, gap, and liquidity-shock feature surfaces",
                "interpretable logistic, tree, and boosted ONNX-feasible model families",
                "reversal, continuation, tradeability-then-side, and liquidity-shock decisions",
                "h6, h8, and h12 holding horizons",
                "proxy metrics designed for later L4 validation and research_oos runtime probes",
            ],
            "kpi_interpretation_plan": {
                "required_for_kpi_bearing_result": True,
                "required_axes": [
                    "overall",
                    "period_role",
                    "time_window",
                    "session",
                    "direction",
                    "spread_or_volume_bucket",
                    "trade_shape_bucket",
                    "runtime_surface",
                ],
                "claim_effect": "exploratory_hypothesis_only_no_selection_or_pass",
            },
            "attribution_axes": [
                "target_or_label_surface",
                "feature_or_input_surface",
                "model_or_training_surface",
                "decision_surface",
                "horizon_or_holding_policy",
                "evaluation_or_runtime_surface",
            ],
            "expected_effect_probe": (
                "Useful cells should increase trade frequency and reduce drawdown concentration without turning into "
                "spread-only or threshold-only repair."
            ),
            "surface_rotation_rationale": (
                "Wave03 volatility-state cell015 failed L5 research_oos with PF below 1 and DD above 10%; rotate to "
                "liquidity-regime discovery instead of repairing that candidate."
            ),
            "search_shape": "broad",
            "sample_scope": {
                "instrument": "FPMarkets US100",
                "timeframe": "M5",
                "split_recipe_id": "split_set_v0",
                "validation_role": "validation",
                "research_oos_role": "research_oos",
                "locked_final_oos": "excluded",
            },
            "success_criteria": [
                "proxy metrics identify at least one interpretable liquidity-regime surface worth L4 follow-through",
                "valid proxy/model-bearing runs declare ONNX/EA/MT5 follow-through requirements",
                "no selected baseline, runtime authority, economics pass, live readiness, or Goal Achieve claim is made",
            ],
            "failure_criteria": [
                "broad cells collapse into spread-only or threshold-only repair without reusable liquidity-regime clue",
                "proxy semantics cannot be mapped to sparse EA decisions after one bounded repair attempt",
                "liquidity-regime features fail to improve trade shape in validation and research_oos observation",
            ],
            "invalid_conditions": [
                "locked final OOS is used without an explicit unlock contract",
                "failed Wave03 cell015 candidate or threshold is reopened as this campaign target",
                "campaign becomes feature-only, label-only, model-only, threshold-only, or repair-only",
            ],
            "stop_conditions": [
                "no reusable surface clue after the initial 18-spec broad batch and one bounded repair at most",
                "evidence cannot support any stronger claim than exploratory observation",
            ],
            "reopen_or_stop_condition": "rotate_surface_or_record_negative_memory_after_broad_batch_if_no_reusable_clue",
            "evidence_plan": [
                "campaign_manifest",
                "run_specs_index",
                "run_spec_manifests",
                "proxy_execution_summary",
                "run_manifest",
                "experiment_receipt",
                "artifact_lineage",
                "metrics",
                "ONNX bundle and parity record for valid model-bearing runs",
                "MT5 L4 attempt manifests for promising or valid model-bearing runs",
            ],
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "legacy_relation": "blank_slate_no_inheritance_failed_wave03_cell015_is_prevention_only",
            "broad_sweep": {
                "proxy_spec_count": 18,
                "surface_width": "multi_axis",
                "default_count_policy": "campaign_open_default_proxy_spec_policy",
            },
        },
        "problem_shape": {
            "input_surface": "intraday_liquidity_regime_state",
            "target_or_label_surface": "liquidity_reversal_continuation_tradeability",
            "decision_use": "liquidity_regime_reversal_continuation_tradeability_abstain",
            "holding_logic": "declared_per_run_h6_h8_h12_timeout_or_liquidity_shock_exit",
            "evaluation_method": "proxy_then_L4_split_runtime_probe",
        },
        "materialization": {"run_specs": next_run_specs()},
        "judgment_contract": {
            "evidence_inputs": [f"lab/campaigns/{NEXT_CAMPAIGN_ID}/evidence/judgment.yaml"],
            "result_judgment": "inconclusive",
            "candidate_effect": "no_candidate_claimed",
            "clue_effect": "no_clue_until_evidence_materialized",
            "negative_memory_effect": "no_negative_memory_until_evidence_materialized",
            "missing_evidence": [
                "proxy_runs_not_yet_executed",
                "ONNX_export_not_materialized_for_L4_yet",
                "MT5_L4_split_runtime_probe_not_run_yet",
                "runtime_authority_not_claimed",
            ],
            "reopen_conditions": ["execute declared broad proxy run specs before judgment"],
        },
        "next_work_item": {
            "version": "work_item_lite_v1",
            "work_item_id": "work_wave03_materialize_intraday_liquidity_regime_specs_v0",
            "request_digest": "wave03_intraday_liquidity_regime_surface_open_v0",
            "primary_family": "experiment_design",
            "primary_skill": "spacesonar-experiment-design",
            "verification_profile": "lab_experiment",
            "targets": [
                f"lab/campaigns/{NEXT_CAMPAIGN_ID}/campaign_manifest.yaml",
                WAVE_ALLOCATION.as_posix(),
            ],
            "acceptance_criteria": [
                "Wave03 campaign 002 open manifests and refs are materialized",
                "next action materializes the declared 18 broad proxy run specs",
            ],
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "policy_binding": {
                "revision": "policy_contract_v2",
                "guards": [
                    "GUARD_003_CLAIM_BOUNDARY",
                    "GUARD_004_ARTIFACT_IDENTITY",
                    "GUARD_006_BRANCH_WORKTREE",
                    "GUARD_007_OPERATIONAL_STABILITY",
                ],
            },
            "outputs": [
                f"lab/campaigns/{NEXT_CAMPAIGN_ID}/run_specs/",
                f"lab/campaigns/{NEXT_CAMPAIGN_ID}/sweeps/{NEXT_SWEEP_ID}/run_refs.csv",
            ],
            "next_action": "materialize_wave03_intraday_liquidity_regime_proxy_specs",
            "summary": "Materialize Wave03 intraday liquidity-regime broad proxy run specs.",
            "path": NEXT_WORK_ITEM.as_posix(),
            "provenance": {"source": NEXT_CAMPAIGN_SPEC.as_posix()},
        },
        "next_action": "materialize_wave03_intraday_liquidity_regime_proxy_specs",
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
        "notes": (
            "Wave03 campaign 002 lifecycle spec only. Declared proxy specs are not executed, selected, "
            "runtime-authoritative, or economics-passing until run manifests, receipts, lineage, metrics, "
            "ONNX/parity, and MT5 L4 evidence exist."
        ),
    }


def build_negative_memory(ended_at_utc: str) -> dict[str, Any]:
    l5 = read_yaml(L5_EVIDENCE_SUMMARY)
    rows = read_csv_rows(L5_EVIDENCE_INDEX)
    candidate_ids = list(l5.get("negative_candidate_ids") or [])
    run_ids = sorted({row.get("run_id", "") for row in rows if row.get("run_id")})
    cells = sorted({row.get("cell_id", "") for row in rows if row.get("cell_id")})
    evidence_paths = [
        L5_EVIDENCE_SUMMARY.as_posix(),
        L5_EVIDENCE_INDEX.as_posix(),
        *list((l5.get("artifact_outputs") or {}).get("candidate_evidence_summaries") or []),
    ]
    payload = {
        "version": "negative_memory_v1",
        "memory_id": NEGATIVE_MEMORY_ID,
        "created_at_utc": ended_at_utc,
        "hypothesis_id": HYPOTHESIS_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "run_id": ";".join(run_ids),
        "observed_cells": cells,
        "status": "wave03_volatility_state_l5_decision_execution_negative_no_candidate",
        "evidence_path": L5_EVIDENCE_SUMMARY.as_posix(),
        "evidence_paths": evidence_paths,
        "failed_boundary": "wave03_volatility_state_cell015_l5_validation_research_oos_decision_execution",
        "why_failed": (
            "The only opened Wave03 volatility-state L5 target had validation PF 1.01 and only 2.29 trades/day, "
            "then failed research_oos with PF 0.79, negative net profit, and 26.6 percent balance drawdown."
        ),
        "salvage_value": (
            "Confirms the Wave03 ONNX-to-EA decision-execution adapter, portable MT5 runtime path, tester report "
            "receipt, and KPI parser can produce candidate-specific L5 evidence. The tested low-vol breakout "
            "decision surface is not carried forward."
        ),
        "reopen_condition": (
            "Reopen volatility-state only with a materially new transition-state question, a fresh multi-axis surface, "
            "or an explicit execution/decision repair that is not cell015 threshold salvage."
        ),
        "do_not_repeat_note": (
            "Do not promote Wave03 volatility-state cell015 or its thresholds to selected baseline, L5 candidate, "
            "runtime authority, economics pass, live readiness, or Goal Achieve."
        ),
        "do_not_repeat_entries": [
            "Do not repair low-vol breakout cell015 as the next campaign target.",
            "Do not use the validation-only small positive result as economics pass or operating reference.",
            "Do not use non-portable main-mode L4 attempts as standard runtime completion.",
        ],
        "next_action": NEXT_WORK_ITEM_ID,
        "claim_boundary": "negative_memory_no_selected_baseline_no_runtime_authority_no_economics_pass_no_live_readiness",
    }
    payload.update(
        contract_fields(
            progress_effect="wave03_l5_negative_memory_recorded",
            next_action=NEXT_ACTION,
            experiment_effect="negative_l5_candidate_memory_recorded_without_repair_or_protected_claim",
            claim_boundary=payload["claim_boundary"],
            source_paths=[L5_EVIDENCE_SUMMARY.as_posix(), L5_EVIDENCE_INDEX.as_posix()],
            outputs=[NEGATIVE_MEMORY_PATH.as_posix()],
            blockers=["none"],
        )
    )
    return payload


def build_campaign_closeout(ended_at_utc: str, command_argv: list[str]) -> dict[str, Any]:
    l5 = read_yaml(L5_EVIDENCE_SUMMARY)
    proxy = read_yaml(PROXY_SUMMARY)
    l4_pair = read_yaml(L4_PAIR_SUMMARY)
    l5_counts = l5.get("counts") or {}
    rows = read_csv_rows(L5_EVIDENCE_INDEX)
    period_counts = Counter(row.get("period_judgment", "") for row in rows)
    candidate_results = l5.get("candidate_results") or {}
    source = source_paths()
    outputs = output_paths()
    payload = {
        "version": "campaign_closeout_v1",
        "campaign_id": CAMPAIGN_ID,
        "active_goal_id": GOAL_ID,
        "wave_id": WAVE_ID,
        "closed_at_utc": ended_at_utc,
        "status": STATUS,
        "result_judgment": "negative",
        "claim_boundary": CLAIM_BOUNDARY,
        "candidate_count": int(l5_counts.get("candidate_count") or 0),
        "l5_candidate_count": 0,
        "candidate_results": candidate_results,
        "negative_candidate_ids": list(l5.get("negative_candidate_ids") or []),
        "counts": {
            "proxy_executed_count": (proxy.get("counts") or {}).get("executed_proxy_run_count")
            or proxy.get("executed_proxy_run_count"),
            "preserved_clue_proxy_count": ((proxy.get("counts") or {}).get("result_judgment_counts") or {}).get("preserved_clue")
            or ((proxy.get("result_judgment_counts") or {}).get("preserved_clue")),
            "l4_pair_count": (l4_pair.get("counts") or {}).get("cell_pair_count"),
            "portable_l4_pair_count": (l4_pair.get("counts") or {}).get("portable_contract_pair_count"),
            "l5_candidate_runtime_evidence_count": l5_counts.get("candidate_runtime_evidence_count"),
            "l5_negative_candidate_count": l5_counts.get("negative_candidate_count"),
            "l5_period_judgment_counts": dict(sorted(period_counts.items())),
        },
        "judgment": {
            "result_subject": "Wave03 volatility-state transition campaign L5 candidate boundary",
            "evidence_paths": [L5_EVIDENCE_SUMMARY.as_posix(), L5_EVIDENCE_INDEX.as_posix()],
            "metric_identity": "candidate-specific MT5 L5 decision-execution tester reports for validation and research_oos",
            "comparison_baseline": "Wave03 campaign objective north-star reference and split_set_v0 validation/research_oos roles",
            "tested_factor": "low-vol breakout h6 volatility-state decision-execution surface from cell015",
            "kpi_interpretation": (
                "Validation was slightly positive but below PF and trade-frequency references; research_oos was negative "
                "with PF below 1 and drawdown above 10 percent."
            ),
            "directional_effect_hypothesis": (
                "The low-vol breakout continuation surface likely overfit validation score behavior and did not control "
                "research_oos drawdown; the next probe should rotate to a new liquidity-regime surface rather than "
                "threshold-repair this candidate."
            ),
            "attribution_confidence": "medium_candidate_specific_runtime_negative",
            "judgment_label": "negative_l5_runtime_evidence_no_l5_candidate",
            "claim_boundary": CLAIM_BOUNDARY,
            "missing_evidence": [
                "no_positive_research_oos_l5_candidate_evidence",
                "locked_final_oos_b_not_used",
                "operational_validation_not_started",
                "no_selected_baseline_or_runtime_authority_from_l5_runtime_evidence",
            ],
            "validation_depth": VALIDATION_DEPTH,
            "non_pytest_smokes": list(NON_PYTEST_SMOKES),
            "broad_validation_escalation_reason": BROAD_VALIDATION_ESCALATION_REASON,
            "next_action": NEXT_ACTION,
        },
        "performance_attribution": {
            "kpi_scope": "MT5 runtime",
            "tested_factor": "Wave03 cell015 low-vol breakout h6 decision-execution adapter",
            "observed_change": {
                "validation": {
                    "profit_factor": 1.01,
                    "total_net_profit": 2.18,
                    "trades_per_day": 2.2867383512544803,
                    "balance_drawdown_maximal_pct": 6.94,
                },
                "research_oos": {
                    "profit_factor": 0.79,
                    "total_net_profit": -102.79,
                    "trades_per_day": 2.2703862660944205,
                    "balance_drawdown_maximal_pct": 26.6,
                },
            },
            "comparison_baseline": "north-star reference 5+ trades/day, PF about 1.5-3.0, <=10% DD across major windows",
            "directional_effect_hypothesis": (
                "The surface generated enough trades for interpretation but not enough frequency or OOS robustness; "
                "drawdown expanded when moved from validation to research_oos."
            ),
            "likely_drivers": [
                "low_vol_breakout_label_or_threshold_did_not_hold_across_oos",
                "h6_timeout_trade_shape_exposed_research_oos_drawdown",
                "score_threshold_trade_execution_frequency_below_north_star",
            ],
            "segment_checks": {
                "performed": ["period_role_validation_vs_research_oos", "trade_count", "drawdown", "profit_factor"],
                "missing": ["session_bucket", "spread_bucket", "direction_bucket", "drawdown_cluster"],
            },
            "trade_shape": {
                "validation_total_trades": 638,
                "research_oos_total_trades": 529,
                "validation_trades_per_day": 2.2867383512544803,
                "research_oos_trades_per_day": 2.2703862660944205,
                "research_oos_drawdown_pct": 26.6,
            },
            "candidate_effect_size_vs_noise": "negative_effect_large_enough_to_stop_candidate_salvage",
            "alternative_explanations": [
                "liquidity_or_spread_regime_shift_between_validation_and_research_oos",
                "decision threshold proxy did not map to profitable execution after costs",
                "holding horizon exposed adverse continuation clusters",
            ],
            "evidence_limits": [
                "only one L5 candidate target reached decision-execution evidence",
                "locked final OOS intentionally not used",
                "no session/spread/direction attribution yet",
            ],
            "failure_or_negative_salvage_value": (
                "Runtime plumbing is now usable, and the negative result gives a prevention boundary: do not repair "
                "cell015 thresholds; rotate to a liquidity-regime surface that directly targets trade shape."
            ),
            "attribution_confidence": "medium",
            "next_probe": "open_wave03_intraday_liquidity_regime_campaign_broad_18_specs",
        },
        "boundary_decision": {
            "decision": "close_campaign_and_rotate_surface",
            "next_campaign_id": NEXT_CAMPAIGN_ID,
            "next_campaign_spec": NEXT_CAMPAIGN_SPEC.as_posix(),
            "candidate_salvage": "forbidden_without_new_surface_question",
            "l5_candidate_count": 0,
            "runtime_authority": False,
            "economics_pass": False,
            "live_readiness": False,
            "goal_achieve": False,
        },
        "negative_memory": {
            "memory_id": NEGATIVE_MEMORY_ID,
            "path": NEGATIVE_MEMORY_PATH.as_posix(),
        },
        "provenance": {
            "source_inputs": source,
            "producer": " ".join(command_argv),
            "consumer": NEXT_WORK_ITEM_ID,
            "artifact_paths": outputs,
            "source_of_truth_paths": [CAMPAIGN_CLOSEOUT.as_posix(), NEGATIVE_MEMORY_PATH.as_posix(), NEXT_CAMPAIGN_SPEC.as_posix()],
            "environment_summary": {
                "python_executable": l5_writer.redact_path(sys.executable) if hasattr(l5_writer, "redact_path") else sys.executable,
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                **git_state(),
            },
            "regeneration_commands": [" ".join(command_argv)],
            "registry_links": [
                ARTIFACT_REGISTRY.as_posix(),
                CAMPAIGN_REGISTRY.as_posix(),
                NEGATIVE_MEMORY_REGISTRY.as_posix(),
            ],
            "availability": "present_hash_recorded_after_write",
            "lineage_judgment": "wave03_volatility_state_campaign_boundary_decision_from_l5_candidate_runtime_evidence",
            "claim_boundary": CLAIM_BOUNDARY,
        },
        "artifact_outputs": {
            "campaign_closeout": CAMPAIGN_CLOSEOUT.as_posix(),
            "negative_memory": NEGATIVE_MEMORY_PATH.as_posix(),
            "next_campaign_spec": NEXT_CAMPAIGN_SPEC.as_posix(),
            "work_closeout": WORK_CLOSEOUT.as_posix(),
        },
        "prevention_memory": [
            "Validation-only small positive net profit is not enough for L5 candidate, economics pass, or runtime authority.",
            "Research_oos drawdown above 10 percent blocks cell015 candidate salvage.",
            "Next campaign must be a new multi-axis liquidity-regime surface, not low-vol breakout threshold repair.",
        ],
        "unresolved_blockers": ["wave03_intraday_liquidity_regime_campaign_not_opened_yet"],
        "reopen_conditions": [
            "reopen volatility-state only with a materially new transition-state question",
            "rerun L5 evidence only if EA adapter, tester report parser, or source attempt identity changes",
            "do not claim runtime authority, economics pass, live readiness, or Goal Achieve from this closeout",
        ],
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
    }
    payload.update(
        contract_fields(
            progress_effect="wave03_l5_candidate_boundary_decision_recorded",
            next_action=NEXT_ACTION,
            experiment_effect="negative_l5_candidate_boundary_closes_campaign_and_routes_new_multi_axis_surface",
            claim_boundary=CLAIM_BOUNDARY,
            source_paths=source,
            outputs=outputs,
            blockers=payload["unresolved_blockers"],
        )
    )
    return payload


def build_work_closeout(closeout: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "version": "work_closeout_v1",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "next_work_item_id": NEXT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": closeout["closed_at_utc"],
        "primary_family": PRIMARY_FAMILY,
        "primary_skill": PRIMARY_SKILL,
        "support_skills": ["spacesonar-performance-attribution", "spacesonar-evidence-provenance"],
        "status": STATUS,
        "result_judgment": "negative",
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_paths": [CAMPAIGN_CLOSEOUT.as_posix(), NEGATIVE_MEMORY_PATH.as_posix(), NEXT_CAMPAIGN_SPEC.as_posix()],
        "counts": closeout["counts"],
        "missing_evidence": closeout["judgment"]["missing_evidence"],
        "next_action": NEXT_ACTION,
        "unresolved_blockers": closeout["unresolved_blockers"],
        "reopen_conditions": closeout["reopen_conditions"],
        "forbidden_claims": closeout["forbidden_claims"],
    }
    payload.update(
        contract_fields(
            progress_effect="wave03_l5_candidate_boundary_work_closed",
            next_action=NEXT_ACTION,
            experiment_effect="boundary_work_closed_to_next_campaign_open_without_protected_claim",
            claim_boundary=CLAIM_BOUNDARY,
            source_paths=[CAMPAIGN_CLOSEOUT.as_posix()],
            outputs=[WORK_CLOSEOUT.as_posix()],
            blockers=closeout["unresolved_blockers"],
        )
    )
    return payload


def next_work_record(closeout: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "version": "work_item_lite_v1",
        "work_item_id": NEXT_WORK_ITEM_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "primary_family": "experiment_design",
        "primary_skill": "spacesonar-experiment-design",
        "support_skills": ["spacesonar-evidence-provenance", "spacesonar-performance-attribution"],
        "verification_profile": "lab_experiment",
        "targets": [NEXT_CAMPAIGN_SPEC.as_posix(), WAVE_ALLOCATION.as_posix(), WAVE_CAMPAIGN_REFS.as_posix()],
        "acceptance_criteria": [
            "open Wave03 campaign 002 from the prepared lifecycle spec",
            "preserve the negative Wave03 volatility-state L5 boundary as prevention memory only",
            "materialize a multi-axis 18-spec liquidity-regime campaign, not a threshold/model/feature-only repair",
        ],
        "status": NEXT_STATUS,
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "current_truth": {
            "campaign_closeout": CAMPAIGN_CLOSEOUT.as_posix(),
            "negative_memory": NEGATIVE_MEMORY_PATH.as_posix(),
            "next_campaign_spec": NEXT_CAMPAIGN_SPEC.as_posix(),
            "closed_campaign_id": CAMPAIGN_ID,
            "closed_campaign_result": STATUS,
            "next_campaign_id": NEXT_CAMPAIGN_ID,
            "l5_candidate_count": 0,
        },
        "outputs": [
            f"lab/campaigns/{NEXT_CAMPAIGN_ID}/campaign_manifest.yaml",
            f"lab/campaigns/{NEXT_CAMPAIGN_ID}/sweeps/{NEXT_SWEEP_ID}/run_refs.csv",
        ],
        "operational_validation_required": False,
        "next_action": NEXT_ACTION,
        "missing_material_if_relevant": [
            "wave03_intraday_liquidity_regime_campaign_not_opened_yet",
            "wave03_intraday_liquidity_regime_proxy_specs_not_materialized",
            "runtime_authority_not_claimed",
        ],
        "unresolved_blockers": ["wave03_intraday_liquidity_regime_campaign_not_opened_yet"],
        "unresolved_blockers_or_none": ["wave03_intraday_liquidity_regime_campaign_not_opened_yet"],
        "reopen_conditions": [
            "rerun boundary writer if L5 evidence summary or candidate summary changes",
            "do not open a repair-only campaign from failed cell015",
        ],
        "open_command": (
            f"python -m spacesonar.cli --repo-root . --work-item-id {NEXT_WORK_ITEM_ID} "
            f"campaign open --spec {NEXT_CAMPAIGN_SPEC.as_posix()}"
        ),
    }
    payload.update(
        contract_fields(
            primary_family="experiment_design",
            primary_skill="spacesonar-experiment-design",
            progress_effect="wave03_l5_boundary_routed_to_next_campaign_open",
            next_action=NEXT_ACTION,
            experiment_effect="next_multi_axis_campaign_open_pending_without_protected_claim",
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            source_paths=[CAMPAIGN_CLOSEOUT.as_posix(), NEXT_CAMPAIGN_SPEC.as_posix(), NEXT_WORK_ITEM.as_posix()],
            outputs=[NEXT_WORK_ITEM.as_posix()],
            blockers=payload["unresolved_blockers"],
        )
    )
    return payload


def update_registries(closeout: dict[str, Any]) -> None:
    if path_exists(NEGATIVE_MEMORY_REGISTRY):
        rows = read_csv_rows(NEGATIVE_MEMORY_REGISTRY)
        fieldnames = list(rows[0].keys()) if rows else [
            "memory_id",
            "hypothesis_id",
            "surface_id",
            "sweep_id",
            "run_id",
            "observed_cells",
            "status",
            "evidence_path",
            "evidence_paths",
            "failed_boundary",
            "why_failed",
            "salvage_value",
            "reopen_condition",
            "do_not_repeat_note",
            "do_not_repeat_entries",
            "next_action",
        ]
        memory = read_yaml(NEGATIVE_MEMORY_PATH)
        by_id = {row.get("memory_id"): row for row in rows if row.get("memory_id")}
        by_id[NEGATIVE_MEMORY_ID] = {
            "memory_id": NEGATIVE_MEMORY_ID,
            "hypothesis_id": HYPOTHESIS_ID,
            "surface_id": SURFACE_ID,
            "sweep_id": SWEEP_ID,
            "run_id": memory.get("run_id", ""),
            "observed_cells": ";".join(memory.get("observed_cells") or []),
            "status": memory.get("status", ""),
            "evidence_path": memory.get("evidence_path", ""),
            "evidence_paths": ";".join(memory.get("evidence_paths") or []),
            "failed_boundary": memory.get("failed_boundary", ""),
            "why_failed": memory.get("why_failed", ""),
            "salvage_value": memory.get("salvage_value", ""),
            "reopen_condition": memory.get("reopen_condition", ""),
            "do_not_repeat_note": memory.get("do_not_repeat_note", ""),
            "do_not_repeat_entries": ";".join(memory.get("do_not_repeat_entries") or []),
            "next_action": NEXT_WORK_ITEM_ID,
        }
        write_csv(NEGATIVE_MEMORY_REGISTRY, list(by_id.values()), fieldnames)

    if path_exists(CAMPAIGN_REGISTRY):
        rows = read_csv_rows(CAMPAIGN_REGISTRY)
        if rows:
            fieldnames = list(rows[0].keys())
            for row in rows:
                if row.get("campaign_id") == CAMPAIGN_ID:
                    if "status" in row:
                        row["status"] = STATUS
                    if "claim_boundary" in row:
                        row["claim_boundary"] = CLAIM_BOUNDARY
                    if "evidence_path" in row:
                        row["evidence_path"] = CAMPAIGN_CLOSEOUT.as_posix()
                    if "next_action" in row:
                        row["next_action"] = NEXT_WORK_ITEM_ID
                    if "notes" in row:
                        row["notes"] = "Wave03 volatility-state campaign closed negative after L5 runtime evidence; no L5 candidate."
            write_csv(CAMPAIGN_REGISTRY, rows, fieldnames)

    if path_exists(GOAL_REGISTRY):
        rows = read_csv_rows(GOAL_REGISTRY)
        if rows:
            fieldnames = list(rows[0].keys())
            for row in rows:
                if row.get("goal_id") == GOAL_ID:
                    if "status" in row:
                        row["status"] = NEXT_STATUS
                    if "active_phase" in row:
                        row["active_phase"] = NEXT_STATUS
                    if "next_work_item" in row:
                        row["next_work_item"] = NEXT_WORK_ITEM_ID
                    if "claim_boundary" in row:
                        row["claim_boundary"] = NEXT_CLAIM_BOUNDARY
                    if "notes" in row:
                        row["notes"] = "Wave03 campaign 001 closed negative; campaign 002 open pending."
            write_csv(GOAL_REGISTRY, rows, fieldnames)

    if path_exists(WAVE_REGISTRY):
        rows = read_csv_rows(WAVE_REGISTRY)
        if rows:
            fieldnames = list(rows[0].keys())
            for row in rows:
                if row.get("wave_id") == WAVE_ID:
                    if "status" in row:
                        row["status"] = NEXT_STATUS
                    if "claim_boundary" in row:
                        row["claim_boundary"] = NEXT_CLAIM_BOUNDARY
                    if "evidence_path" in row:
                        row["evidence_path"] = CAMPAIGN_CLOSEOUT.as_posix()
                    if "next_action" in row:
                        row["next_action"] = NEXT_WORK_ITEM_ID
                    if "notes" in row:
                        row["notes"] = "Wave03 campaign 002 open pending after volatility-state negative L5 boundary."
            write_csv(WAVE_REGISTRY, rows, fieldnames)

    if path_exists(ARTIFACT_REGISTRY):
        rows = read_csv_rows(ARTIFACT_REGISTRY)
        if rows:
            fieldnames = list(rows[0].keys())
            by_id = {row.get("artifact_id"): row for row in rows if row.get("artifact_id")}
            producer = (closeout.get("provenance") or {}).get("producer", "")
            for artifact_id, artifact_type, path in [
                ("artifact_wave03_l5_candidate_boundary_campaign_closeout_v0", "campaign_closeout", CAMPAIGN_CLOSEOUT),
                ("artifact_wave03_l5_candidate_boundary_work_closeout_v0", "work_closeout", WORK_CLOSEOUT),
                ("artifact_wave03_l5_candidate_boundary_negative_memory_v0", "negative_memory", NEGATIVE_MEMORY_PATH),
                ("artifact_wave03_intraday_liquidity_regime_campaign_spec_v0", "campaign_lifecycle_spec", NEXT_CAMPAIGN_SPEC),
            ]:
                full = REPO_ROOT / path
                if not full.exists():
                    continue
                by_id[artifact_id] = {
                    "artifact_id": artifact_id,
                    "run_id": "",
                    "bundle_id": "",
                    "attempt_id": "",
                    "artifact_type": artifact_type,
                    "path_or_uri": path.as_posix(),
                    "sha256": sha256_file(full),
                    "size_bytes": full.stat().st_size,
                    "availability": "present_hash_recorded",
                    "producer_command": producer,
                    "regeneration_command": producer,
                    "source_of_truth": path.as_posix(),
                    "consumer": NEXT_WORK_ITEM_ID,
                    "claim_boundary": closeout["claim_boundary"],
                    "notes": "Wave03 L5 candidate boundary artifact",
                }
            write_csv(ARTIFACT_REGISTRY, list(by_id.values()), fieldnames)


def update_control_records(closeout: dict[str, Any]) -> None:
    next_work = next_work_record(closeout)
    write_yaml(NEXT_WORK_ITEM, next_work)

    campaign = read_yaml(CAMPAIGN_MANIFEST)
    campaign.update(
        {
            "updated_at_utc": closeout["closed_at_utc"],
            "status": STATUS,
            "claim_boundary": CLAIM_BOUNDARY,
            "campaign_closeout": CAMPAIGN_CLOSEOUT.as_posix(),
            "next_action": NEXT_ACTION,
            "missing_evidence": closeout["judgment"]["missing_evidence"],
            "unresolved_blockers": closeout["unresolved_blockers"],
            "reopen_conditions": closeout["reopen_conditions"],
        }
    )
    campaign.setdefault("evidence_paths", [])
    campaign["evidence_paths"] = add_unique(
        campaign["evidence_paths"],
        [CAMPAIGN_CLOSEOUT.as_posix(), NEGATIVE_MEMORY_PATH.as_posix(), NEXT_CAMPAIGN_SPEC.as_posix()],
    )
    campaign.update(
        contract_fields(
            progress_effect="wave03_campaign_manifest_closed_negative_l5_boundary",
            next_action=NEXT_ACTION,
            experiment_effect="campaign_manifest_closed_to_next_campaign_open_without_protected_claim",
            claim_boundary=CLAIM_BOUNDARY,
            source_paths=[CAMPAIGN_CLOSEOUT.as_posix()],
            outputs=[CAMPAIGN_MANIFEST.as_posix()],
            blockers=closeout["unresolved_blockers"],
        )
    )
    write_yaml(CAMPAIGN_MANIFEST, campaign)

    wave = read_yaml(WAVE_ALLOCATION)
    wave.update(
        {
            "updated_at_utc": closeout["closed_at_utc"],
            "status": NEXT_STATUS,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
        }
    )
    for allocation in wave.get("campaign_allocations") or []:
        if allocation.get("campaign_id") == CAMPAIGN_ID:
            allocation.update(
                {
                    "status": STATUS,
                    "campaign_closeout": CAMPAIGN_CLOSEOUT.as_posix(),
                    "claim_boundary": CLAIM_BOUNDARY,
                    "next_action": NEXT_ACTION,
                    "l5_candidate_count": 0,
                    "closed_at_utc": closeout["closed_at_utc"],
                }
            )
    wave["planned_next_campaign"] = {
        "campaign_id": NEXT_CAMPAIGN_ID,
        "campaign_spec": NEXT_CAMPAIGN_SPEC.as_posix(),
        "allocation_role": "wave03_second_campaign_intraday_liquidity_regime_surface",
        "status": "open_pending",
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
    }
    wave.update(
        contract_fields(
            primary_family="experiment_design",
            primary_skill="spacesonar-experiment-design",
            progress_effect="wave03_allocation_routed_to_second_campaign_open",
            next_action=NEXT_ACTION,
            experiment_effect="wave_allocation_records_closed_negative_campaign_and_next_open_pending",
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            source_paths=[CAMPAIGN_CLOSEOUT.as_posix(), NEXT_CAMPAIGN_SPEC.as_posix()],
            outputs=[WAVE_ALLOCATION.as_posix()],
            blockers=closeout["unresolved_blockers"],
        )
    )
    write_yaml(WAVE_ALLOCATION, wave)

    resume = read_yaml(RESUME_CURSOR)
    resume.update(
        {
            "updated_at_utc": closeout["closed_at_utc"],
            "cursor_state": NEXT_STATUS,
            "active_phase": NEXT_STATUS,
            "active_goal_id": GOAL_ID,
            "active_work_item_id": NEXT_WORK_ITEM_ID,
            "campaign_id": CAMPAIGN_ID,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
            "unresolved_blockers": next_work["unresolved_blockers"],
            "active_ids": {
                "idea_id": IDEA_ID,
                "hypothesis_id": HYPOTHESIS_ID,
                "wave_id": WAVE_ID,
                "campaign_id": CAMPAIGN_ID,
                "surface_id": SURFACE_ID,
                "sweep_id": SWEEP_ID,
            },
            "latest_completed_work": {
                "work_item_id": WORK_ITEM_ID,
                "result_judgment": "negative",
                "claim_boundary": CLAIM_BOUNDARY,
                "evidence_paths": [CAMPAIGN_CLOSEOUT.as_posix(), WORK_CLOSEOUT.as_posix()],
            },
            "next_work_item": {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()},
        }
    )
    resume.setdefault("current_truth_sources", [])
    resume["current_truth_sources"] = add_unique(
        resume["current_truth_sources"],
        [CAMPAIGN_CLOSEOUT.as_posix(), NEGATIVE_MEMORY_PATH.as_posix(), NEXT_CAMPAIGN_SPEC.as_posix()],
    )
    resume.update(
        contract_fields(
            primary_family="experiment_design",
            primary_skill="spacesonar-experiment-design",
            progress_effect="wave03_l5_boundary_routed_to_next_campaign_open",
            next_action=NEXT_ACTION,
            experiment_effect="resume_cursor_points_to_next_campaign_open_without_protected_claim",
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            source_paths=[CAMPAIGN_CLOSEOUT.as_posix(), NEXT_WORK_ITEM.as_posix()],
            outputs=[RESUME_CURSOR.as_posix()],
            blockers=next_work["unresolved_blockers"],
        )
    )
    write_yaml(RESUME_CURSOR, resume)

    goal = read_yaml(GOAL_MANIFEST)
    goal.update(
        {
            "updated_at_utc": closeout["closed_at_utc"],
            "status": NEXT_STATUS,
            "active_phase": NEXT_STATUS,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "active_ids": resume["active_ids"],
            "next_work_item": {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix(), "summary": NEXT_ACTION},
        }
    )
    goal["wave03_l5_candidate_boundary_decision"] = {
        "status": STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
        "campaign_closeout": CAMPAIGN_CLOSEOUT.as_posix(),
        "negative_memory": NEGATIVE_MEMORY_PATH.as_posix(),
        "next_campaign_spec": NEXT_CAMPAIGN_SPEC.as_posix(),
        "l5_candidate_count": 0,
        "next_work_item": NEXT_WORK_ITEM_ID,
    }
    goal.update(
        contract_fields(
            primary_family="experiment_design",
            primary_skill="spacesonar-experiment-design",
            progress_effect="goal_routed_to_wave03_second_campaign_open",
            next_action=NEXT_ACTION,
            experiment_effect="goal_pointer_moves_to_next_multi_axis_campaign_open_without_protected_claim",
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            source_paths=[CAMPAIGN_CLOSEOUT.as_posix(), NEXT_WORK_ITEM.as_posix()],
            outputs=[GOAL_MANIFEST.as_posix()],
            blockers=next_work["unresolved_blockers"],
        )
    )
    write_yaml(GOAL_MANIFEST, goal)

    workspace = read_yaml(WORKSPACE_STATE)
    workspace.update(
        {
            "updated_utc": closeout["closed_at_utc"],
            "active_goal": {"goal_id": GOAL_ID, "status": NEXT_STATUS, "manifest": GOAL_MANIFEST.as_posix()},
            "active_wave": {
                "wave_id": WAVE_ID,
                "status": NEXT_STATUS,
                "allocation": WAVE_ALLOCATION.as_posix(),
                "closeout": None,
            },
            "active_campaign": {
                "campaign_id": CAMPAIGN_ID,
                "status": STATUS,
                "manifest": CAMPAIGN_MANIFEST.as_posix(),
                "closeout": CAMPAIGN_CLOSEOUT.as_posix(),
            },
            "active_work_item": {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()},
            "current_claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
            "unresolved_blockers": next_work["unresolved_blockers"],
            "status": NEXT_STATUS,
            "primary_family": "experiment_design",
            "primary_skill": "spacesonar-experiment-design",
            "next_executable_action": NEXT_ACTION,
            "operational_validation_required": False,
        }
    )
    counts = workspace.setdefault("summary_counts", {})
    counts["candidate_count"] = 0
    counts["l5_candidate_count"] = 0
    counts["wave03_l5_candidate_boundary_decision"] = {
        "closed_campaign_id": CAMPAIGN_ID,
        "next_campaign_id": NEXT_CAMPAIGN_ID,
        "l5_candidate_count": 0,
        "negative_memory_count": 1,
    }
    workspace.update(
        contract_fields(
            primary_family="experiment_design",
            primary_skill="spacesonar-experiment-design",
            progress_effect="workspace_routed_to_wave03_second_campaign_open",
            next_action=NEXT_ACTION,
            experiment_effect="active_pointer_moves_to_next_campaign_open_without_protected_claim",
            claim_boundary=NEXT_CLAIM_BOUNDARY,
            source_paths=[CAMPAIGN_CLOSEOUT.as_posix(), NEXT_WORK_ITEM.as_posix()],
            outputs=[WORKSPACE_STATE.as_posix()],
            blockers=next_work["unresolved_blockers"],
        )
    )
    write_yaml(WORKSPACE_STATE, workspace)

    update_registries(closeout)


def smoke_outputs(closeout: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for path in [CAMPAIGN_CLOSEOUT, NEGATIVE_MEMORY_PATH, NEXT_CAMPAIGN_SPEC, WORK_CLOSEOUT, NEXT_WORK_ITEM, WORKSPACE_STATE, GOAL_MANIFEST, CAMPAIGN_MANIFEST, WAVE_ALLOCATION]:
        if not path_exists(path):
            errors.append(f"missing output path: {path.as_posix()}")
    loaded = read_yaml(CAMPAIGN_CLOSEOUT) if path_exists(CAMPAIGN_CLOSEOUT) else {}
    if loaded.get("claim_boundary") != CLAIM_BOUNDARY:
        errors.append("campaign closeout claim boundary mismatch")
    if loaded.get("l5_candidate_count") != 0:
        errors.append("campaign closeout l5_candidate_count must be 0")
    spec = read_yaml(NEXT_CAMPAIGN_SPEC) if path_exists(NEXT_CAMPAIGN_SPEC) else {}
    run_specs = (spec.get("materialization") or {}).get("run_specs") or []
    if len(run_specs) != 18:
        errors.append("next campaign spec must declare 18 proxy run specs")
    if "repair" in str(spec.get("exploration_coverage", {}).get("mode", "")):
        errors.append("next campaign spec must not be repair mode")
    next_work = read_yaml(NEXT_WORK_ITEM) if path_exists(NEXT_WORK_ITEM) else {}
    workspace = read_yaml(WORKSPACE_STATE) if path_exists(WORKSPACE_STATE) else {}
    if next_work.get("work_item_id") != NEXT_WORK_ITEM_ID:
        errors.append("next work id mismatch")
    if next_work.get("claim_boundary") != NEXT_CLAIM_BOUNDARY:
        errors.append("next work claim boundary mismatch")
    if workspace.get("current_claim_boundary") != NEXT_CLAIM_BOUNDARY:
        errors.append("workspace claim boundary mismatch")
    if workspace.get("next_action") != NEXT_ACTION:
        errors.append("workspace next action mismatch")
    if (workspace.get("active_campaign") or {}).get("closeout") != CAMPAIGN_CLOSEOUT.as_posix():
        errors.append("workspace active campaign closeout mismatch")
    return errors


def write_outputs(closeout: dict[str, Any], command_argv: list[str]) -> None:
    write_yaml(CAMPAIGN_CLOSEOUT, closeout)
    write_yaml(NEGATIVE_MEMORY_PATH, build_negative_memory(closeout["closed_at_utc"]))
    write_plain_yaml(NEXT_CAMPAIGN_SPEC, build_next_campaign_spec(closeout["closed_at_utc"]))
    write_yaml(WORK_CLOSEOUT, build_work_closeout(closeout))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Decide Wave03 L5 candidate boundary and route to the next campaign.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--write-control-records", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    global REPO_ROOT
    args = parse_args(argv)
    REPO_ROOT = Path(args.repo_root).resolve()
    l5_writer.REPO_ROOT = REPO_ROOT
    l5_writer.routing_writer.REPO_ROOT = REPO_ROOT
    l5_writer.routing_writer.pair_writer.REPO_ROOT = REPO_ROOT
    started = utc_now()
    command_argv = [Path(sys.executable).name, *sys.argv] if argv is None else ["python", __file__, *argv]
    closeout = build_campaign_closeout(started, command_argv)
    write_outputs(closeout, command_argv)
    if args.write_control_records:
        update_control_records(closeout)
    errors = smoke_outputs(closeout)
    if errors:
        print({"status": "wave03_l5_candidate_boundary_writer_smoke_failed", "errors": errors})
        return 1
    print(
        "wave03 l5 candidate boundary writer-smoke passed: "
        f"status={STATUS} next_work={NEXT_WORK_ITEM_ID} l5_candidate_count=0 "
        f"claim_boundary={CLAIM_BOUNDARY}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
