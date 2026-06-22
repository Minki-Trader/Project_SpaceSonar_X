from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation.pipelines.close_wave01_event_barrier_campaign import (
    artifact_ref,
    git_state,
    load_yaml,
    read_csv_rows,
    sha256,
    upsert_csv_row,
    utc_now,
    write_csv,
    write_yaml,
)


GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WAVE_ID = "wave_us100_closedbar_surface_cartography_v0"
CAMPAIGN_ID = "campaign_us100_session_transition_regime_surface_v0"
IDEA_ID = "idea_us100_m5_session_transition_regime_surface_v0"
HYPOTHESIS_ID = "hyp_us100_session_transition_regime_surface_v0"
SURFACE_ID = "surface_us100_session_transition_regime_surface_v0"
SWEEP_ID = "sweep_us100_session_transition_broad_v0"
WORK_ITEM_ID = "work_wave01_session_transition_campaign_closeout_v0"
NEXT_WORK_ID = "work_wave01_wave_closeout_or_next_multi_axis_surface_v0"
NEGATIVE_MEMORY_ID = "neg_wave01_session_transition_inverse_score_band_decision_replay_loss_v0"
CLUE_MEMORY_ID = "clue_wave01_session_transition_remaining_decision_surface_needed_v0"

FINAL_STATUS = "wave01_session_transition_closed_preserved_clues_no_candidate"
FINAL_PHASE = "wave01_session_transition_campaign_closed_preserved_clues_no_candidate"
CLAIM_BOUNDARY = (
    "wave01_session_transition_campaign_closed_preserved_clues_no_candidate_no_l5_"
    "no_runtime_authority_no_economics_pass"
)
NEXT_ACTION = NEXT_WORK_ID
NEXT_ACTION_DETAIL = (
    "Prepare Wave01 closeout review or open a genuinely new multi-axis surface. "
    "Do not continue session-transition inverse score-band replay as candidate repair. "
    "Remaining non-directional/diagnostic clues require a newly declared decision surface "
    "before any trade replay."
)

CAMPAIGN_ROOT = Path("lab/campaigns") / CAMPAIGN_ID
CAMPAIGN_MANIFEST = CAMPAIGN_ROOT / "campaign_manifest.yaml"
CAMPAIGN_CLOSEOUT = CAMPAIGN_ROOT / "campaign_closeout.yaml"
SURFACE_MANIFEST = Path("lab/surfaces") / SURFACE_ID / "surface_manifest.yaml"
SWEEP_MANIFEST = CAMPAIGN_ROOT / "sweeps" / SWEEP_ID / "sweep_manifest.yaml"
WAVE_ALLOCATION = Path("lab/waves") / WAVE_ID / "wave_allocation.yaml"
CAMPAIGN_REFS = Path("lab/waves") / WAVE_ID / "campaign_refs.csv"
GOAL_ROOT = Path("lab/goals") / GOAL_ID
GOAL_MANIFEST = GOAL_ROOT / "goal_manifest.yaml"
NEXT_WORK_ITEM = GOAL_ROOT / "next_work_item.yaml"
RESUME_CURSOR = GOAL_ROOT / "resume_cursor.yaml"
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
CAMPAIGN_REGISTRY = Path("docs/registers/campaign_registry.csv")
WAVE_REGISTRY = Path("docs/registers/wave_registry.csv")
GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")
IDEA_REGISTRY = Path("docs/registers/idea_registry.csv")
HYPOTHESIS_REGISTRY = Path("docs/registers/hypothesis_registry.csv")
SURFACE_REGISTRY = Path("docs/registers/experiment_surface_registry.csv")
SWEEP_REGISTRY = Path("docs/registers/sweep_registry.csv")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")
IDEA_MANIFEST = Path("lab/hypotheses") / f"{IDEA_ID}.yaml"
HYPOTHESIS_MANIFEST = Path("lab/hypotheses") / f"{HYPOTHESIS_ID}.yaml"

L4_PAIR_SUMMARY = CAMPAIGN_ROOT / "l4_follow_through/l4_pair_judgment_summary.yaml"
DECISION_REPLAY_DIR = CAMPAIGN_ROOT / "l4_follow_through/decision_replay"
ADAPTER_ELIGIBILITY_INDEX = DECISION_REPLAY_DIR / "adapter_eligibility_index.csv"
ADAPTER_PREP_SUMMARY = DECISION_REPLAY_DIR / "adapter_prep_summary.yaml"
DECISION_REPLAY_SUMMARY = DECISION_REPLAY_DIR / "judgment_summary.yaml"
DECISION_REPLAY_INDEX = DECISION_REPLAY_DIR / "judgment_index.csv"
DECISION_REPLAY_RUNTIME_SUMMARY = DECISION_REPLAY_DIR / "runtime_execution_summary.yaml"
REMAINING_CLUE_REVIEW = DECISION_REPLAY_DIR / "remaining_preserved_clue_review.yaml"
REMAINING_CLUE_INDEX = DECISION_REPLAY_DIR / "remaining_preserved_clue_review.csv"
NEGATIVE_MEMORY_PATH = Path("lab/memory/negative") / f"{NEGATIVE_MEMORY_ID}.yaml"
CLUE_MEMORY_PATH = Path("lab/memory/clues") / f"{CLUE_MEMORY_ID}.yaml"


def review_fieldnames() -> list[str]:
    return [
        "cell_id",
        "run_id",
        "bundle_id",
        "decision_family",
        "decision_execution_kind",
        "prior_proxy_judgment",
        "closeout_judgment",
        "remaining_preserved_clue",
        "required_future_surface",
        "l5_routing_status",
        "claim_boundary",
        "forbidden_carryover",
        "evidence_path",
        "next_action",
    ]


def classify_eligibility_row(row: dict[str, str], negative_cells: set[str]) -> dict[str, Any]:
    cell_id = row["cell_id"]
    kind = row.get("decision_execution_kind", "")
    if cell_id in negative_cells:
        judgment = "negative_memory_recorded"
        remaining = False
        required_surface = "not_applicable_inverse_score_band_replay_closed_negative"
        l5_status = "no_l5_decision_replay_log_balance_loss_observed"
        forbidden = "do_not_continue_inverse_score_band_replay_as_candidate_repair"
        next_action = "do_not_reopen_without_new_decision_surface_and_new_L4"
        evidence_path = NEGATIVE_MEMORY_PATH.as_posix()
    elif kind == "non_directional_event_or_tradeability":
        judgment = "preserved_clue"
        remaining = True
        required_surface = "new_declared_side_surface_required_before_trade_replay"
        l5_status = "no_l5_preserved_clue_requires_declared_side_surface"
        forbidden = "do_not_force_event_or_tradeability_score_into_long_short_orders"
        next_action = "preserve_for_future_decision_surface_campaign_or_wave_handoff"
        evidence_path = REMAINING_CLUE_REVIEW.as_posix()
    elif kind == "diagnostic_or_no_trade":
        judgment = "preserved_clue"
        remaining = True
        required_surface = "new_declared_trade_or_no_trade_surface_required_before_trade_replay"
        l5_status = "no_l5_preserved_clue_requires_trade_surface"
        forbidden = "do_not_force_diagnostic_or_no_trade_score_into_order_execution"
        next_action = "preserve_for_future_tradeability_or_no_trade_surface"
        evidence_path = REMAINING_CLUE_REVIEW.as_posix()
    else:
        judgment = "inconclusive"
        remaining = False
        required_surface = "unknown_decision_execution_kind_requires_review"
        l5_status = "no_l5_unclassified_decision_execution_kind"
        forbidden = "do_not_claim_candidate"
        next_action = "manual_review_before_any_replay"
        evidence_path = REMAINING_CLUE_REVIEW.as_posix()

    return {
        "cell_id": cell_id,
        "run_id": row.get("run_id", ""),
        "bundle_id": row.get("bundle_id", ""),
        "decision_family": row.get("decision_family", ""),
        "decision_execution_kind": kind,
        "prior_proxy_judgment": row.get("proxy_judgment", ""),
        "closeout_judgment": judgment,
        "remaining_preserved_clue": str(remaining).lower(),
        "required_future_surface": required_surface,
        "l5_routing_status": l5_status,
        "claim_boundary": CLAIM_BOUNDARY,
        "forbidden_carryover": forbidden,
        "evidence_path": evidence_path,
        "next_action": next_action,
    }


def build_remaining_preserved_clue_review(
    repo_root: Path,
    *,
    created_at_utc: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    eligibility_rows = read_csv_rows(repo_root / ADAPTER_ELIGIBILITY_INDEX)
    judgment_rows = read_csv_rows(repo_root / DECISION_REPLAY_INDEX)
    negative_cells = {row["cell_id"] for row in judgment_rows if row.get("result_judgment") == "negative"}
    review_rows = [classify_eligibility_row(row, negative_cells) for row in eligibility_rows]
    remaining_rows = [row for row in review_rows if row["remaining_preserved_clue"] == "true"]
    kind_counts = Counter(row["decision_execution_kind"] for row in remaining_rows)
    judgment_counts = Counter(row["closeout_judgment"] for row in review_rows)
    l5_counts = Counter(row["l5_routing_status"] for row in review_rows)

    summary = {
        "version": "wave01_session_transition_remaining_preserved_clue_review_v1",
        "review_id": "wave01_session_transition_remaining_preserved_clue_review_v0",
        "created_at_utc": created_at_utc,
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "status": "remaining_preserved_clues_reviewed_requires_new_decision_surface",
        "claim_boundary": CLAIM_BOUNDARY,
        "source_records": {
            "adapter_eligibility_index": ADAPTER_ELIGIBILITY_INDEX.as_posix(),
            "decision_replay_judgment_index": DECISION_REPLAY_INDEX.as_posix(),
            "decision_replay_judgment_summary": DECISION_REPLAY_SUMMARY.as_posix(),
        },
        "artifact_paths": {
            "review_summary": REMAINING_CLUE_REVIEW.as_posix(),
            "review_index": REMAINING_CLUE_INDEX.as_posix(),
            "clue_memory": CLUE_MEMORY_PATH.as_posix(),
        },
        "counts": {
            "source_preserved_clue_count": len(eligibility_rows),
            "negative_memory_recorded_count": len(negative_cells),
            "remaining_preserved_clue_count": len(remaining_rows),
            "remaining_non_directional_event_count": kind_counts.get("non_directional_event_or_tradeability", 0),
            "remaining_diagnostic_or_no_trade_count": kind_counts.get("diagnostic_or_no_trade", 0),
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "closeout_judgment_counts": dict(sorted(judgment_counts.items())),
            "l5_routing_status_counts": dict(sorted(l5_counts.items())),
        },
        "judgment": {
            "result_subject": "Wave01 session-transition remaining preserved clues after decision replay",
            "metric_identity": "adapter eligibility plus one MT5 decision replay judgment; no tester report economics",
            "comparison_baseline": "declared decision execution kind per preserved clue",
            "judgment_label": "preserved_clue",
            "claim_boundary": CLAIM_BOUNDARY,
            "missing_evidence": [
                "declared_side_surface_missing_for_non_directional_event_clues",
                "declared_trade_surface_missing_for_diagnostic_no_trade_clues",
                "tester_reports_missing_for_decision_replay_pairs",
                "economics_pass_forbidden",
            ],
            "next_action": NEXT_ACTION_DETAIL,
        },
        "prevention_memory": [
            "Non-directional event/tradeability scores must not be forced into long/short orders.",
            "Diagnostic/no-trade scores require an explicit trade or no-trade decision surface before replay.",
            "Remaining preserved clues are not L5 candidates and are not selected baseline evidence.",
        ],
        "forbidden_claims": forbidden_claims(),
    }
    clue_memory = {
        "version": "clue_memory_v1",
        "clue_id": CLUE_MEMORY_ID,
        "created_at_utc": created_at_utc,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "subject": "Remaining Wave01 session-transition preserved clues require new decision-surface semantics",
        "clue_type": "preserved_decision_surface_requirement",
        "evidence_paths": [
            REMAINING_CLUE_REVIEW.as_posix(),
            REMAINING_CLUE_INDEX.as_posix(),
            ADAPTER_ELIGIBILITY_INDEX.as_posix(),
            DECISION_REPLAY_SUMMARY.as_posix(),
        ],
        "claim_boundary": CLAIM_BOUNDARY,
        "observed_cells": [row["cell_id"] for row in remaining_rows],
        "required_future_surfaces": sorted({row["required_future_surface"] for row in remaining_rows}),
        "do_not_repeat": sorted({row["forbidden_carryover"] for row in remaining_rows}),
        "candidate_effect": "no_candidate_no_l5_until_new_decision_surface_and_MT5_L4",
        "reopen_condition": (
            "Open a genuinely new decision/tradeability surface with side or trade/no-trade semantics, "
            "then run MT5 L4 before any candidate or L5 claim."
        ),
    }
    return summary, review_rows, clue_memory


def forbidden_claims() -> list[str]:
    return [
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


def build_closeout(repo_root: Path, closed_at: str) -> dict[str, Any]:
    campaign = load_yaml(repo_root / CAMPAIGN_MANIFEST)
    pair_summary = load_yaml(repo_root / L4_PAIR_SUMMARY)
    replay_summary = load_yaml(repo_root / DECISION_REPLAY_SUMMARY)
    runtime_summary = load_yaml(repo_root / DECISION_REPLAY_RUNTIME_SUMMARY)
    adapter_summary = load_yaml(repo_root / ADAPTER_PREP_SUMMARY)
    review_summary, _, clue_memory = build_remaining_preserved_clue_review(repo_root, created_at_utc=closed_at)
    replay_counts = replay_summary.get("counts") or {}
    pair_counts = pair_summary.get("counts") or {}
    adapter_counts = adapter_summary.get("counts") or {}
    review_counts = review_summary["counts"]
    result_counts = campaign.get("result_counts") or {}
    replay_missing = list((replay_summary.get("judgment") or {}).get("missing_evidence") or [])
    review_missing = list((review_summary.get("judgment") or {}).get("missing_evidence") or [])
    missing_evidence = sorted(set(replay_missing + review_missing + ["locked_final_oos_b_not_used"]))

    return {
        "version": "campaign_closeout_v1",
        "closeout_id": WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "wave_id": WAVE_ID,
        "campaign_id": CAMPAIGN_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "closed_at_utc": closed_at,
        "status": FINAL_STATUS,
        "result_judgment": "preserved_clue",
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_paths": [
            DECISION_REPLAY_SUMMARY.as_posix(),
            DECISION_REPLAY_INDEX.as_posix(),
            DECISION_REPLAY_RUNTIME_SUMMARY.as_posix(),
            L4_PAIR_SUMMARY.as_posix(),
            ADAPTER_PREP_SUMMARY.as_posix(),
            REMAINING_CLUE_REVIEW.as_posix(),
            REMAINING_CLUE_INDEX.as_posix(),
            NEGATIVE_MEMORY_PATH.as_posix(),
            CLUE_MEMORY_PATH.as_posix(),
        ],
        "campaign_result": {
            "proxy_first_batch": {
                "status": campaign.get("status"),
                "result_counts": result_counts,
                "candidate_count": campaign.get("candidate_count", 0),
                "claim_boundary": campaign.get("claim_boundary"),
            },
            "l4_score_pair_judgment": {
                "status": pair_summary.get("status"),
                "counts": pair_counts,
                "claim_boundary": pair_summary.get("claim_boundary"),
            },
            "decision_replay_judgment": {
                "status": replay_summary.get("status"),
                "counts": replay_counts,
                "claim_boundary": replay_summary.get("claim_boundary"),
            },
            "remaining_preserved_clue_review": {
                "status": review_summary["status"],
                "counts": review_counts,
                "claim_boundary": review_summary["claim_boundary"],
            },
        },
        "counts": {
            "valid_proxy_model_bearing_run_count": 10,
            "l4_score_pair_count": pair_counts.get("cell_pair_count", 0),
            "direct_trade_adapter_eligible_cell_count": adapter_counts.get(
                "direct_trade_adapter_eligible_cell_count", 0
            ),
            "not_direct_trade_adapter_eligible_cell_count": adapter_counts.get(
                "not_direct_trade_adapter_eligible_cell_count", 0
            ),
            "decision_replay_pair_count": replay_counts.get("cell_pair_count", 0),
            "decision_replay_negative_count": replay_counts.get("negative_count", 0),
            "remaining_preserved_clue_count": review_counts["remaining_preserved_clue_count"],
            "remaining_non_directional_event_count": review_counts["remaining_non_directional_event_count"],
            "remaining_diagnostic_or_no_trade_count": review_counts["remaining_diagnostic_or_no_trade_count"],
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "tester_report_pair_observed_count": replay_counts.get("tester_report_pair_observed_count", 0),
            "runtime_execution_indexed_count": (runtime_summary.get("counts") or {}).get("indexed_execution_count", 0),
        },
        "negative_memory_ids": [NEGATIVE_MEMORY_ID],
        "preserved_clue_ids": [clue_memory["clue_id"]],
        "prevention_memory": [
            "Failed-breakout inverse score-band replay lost in validation and research_oos; no L5.",
            "Non-directional event/tradeability clues need a declared side surface before trade replay.",
            "Diagnostic/no-trade clues need a declared trade or no-trade surface before replay.",
            "Do not force remaining preserved clues into orders as a campaign repair.",
        ],
        "salvage": {
            "negative_memory": NEGATIVE_MEMORY_ID,
            "preserved_clue_memory": clue_memory["clue_id"],
            "mt5_runner_clue": "decision replay runner and telemetry path executed end-to-end for one eligible inverse-side clue",
            "reopen_condition": clue_memory["reopen_condition"],
        },
        "missing_evidence": missing_evidence,
        "next_action": NEXT_ACTION,
        "next_action_detail": NEXT_ACTION_DETAIL,
        "forbidden_claims": forbidden_claims(),
        "forbidden_claims_respected": True,
        "source_truth_effect": {
            "campaign_manifest": CAMPAIGN_MANIFEST.as_posix(),
            "surface_manifest": SURFACE_MANIFEST.as_posix(),
            "sweep_manifest": SWEEP_MANIFEST.as_posix(),
            "wave_campaign_refs": CAMPAIGN_REFS.as_posix(),
            "campaign_registry": CAMPAIGN_REGISTRY.as_posix(),
            "surface_registry": SURFACE_REGISTRY.as_posix(),
            "sweep_registry": SWEEP_REGISTRY.as_posix(),
            "workspace_state": WORKSPACE_STATE.as_posix(),
        },
        "runtime_claim_effect": "no_runtime_authority_no_economics_pass_no_L5_candidate",
    }


def update_manifest_common(path: Path, repo_root: Path, closeout: dict[str, Any]) -> None:
    payload = load_yaml(repo_root / path)
    payload["status"] = FINAL_STATUS
    payload["updated_at_utc"] = closeout["closed_at_utc"]
    payload["claim_boundary"] = CLAIM_BOUNDARY
    payload["evidence_path"] = CAMPAIGN_CLOSEOUT.as_posix()
    payload["next_action"] = NEXT_ACTION
    payload["next_action_detail"] = NEXT_ACTION_DETAIL
    if path == CAMPAIGN_MANIFEST:
        payload["campaign_closeout"] = {
            "path": CAMPAIGN_CLOSEOUT.as_posix(),
            "status": FINAL_STATUS,
            "result_judgment": closeout["result_judgment"],
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "negative_memory_ids": closeout["negative_memory_ids"],
            "preserved_clue_ids": closeout["preserved_clue_ids"],
            "claim_boundary": CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
        }
        parity = payload.setdefault("proxy_runtime_parity", {})
        parity["status"] = "campaign_closed_with_negative_memory_and_preserved_decision_surface_clues"
        parity["divergence_judgment"] = "one_inverse_score_band_replay_negative_remaining_clues_need_new_decision_surface"
        prevention = list(parity.get("prevention_memory") or [])
        for item in closeout["prevention_memory"]:
            if item not in prevention:
                prevention.append(item)
        parity["prevention_memory"] = prevention
        parity["follow_up_action"] = NEXT_ACTION
        payload["proxy_runtime_parity"] = parity
        git_integration = payload.setdefault("git_integration", {})
        git_integration["status"] = "campaign_close_branch_committed_pending_main_boundary"
    if path == SURFACE_MANIFEST:
        payload["closeout"] = {
            "campaign_closeout": CAMPAIGN_CLOSEOUT.as_posix(),
            "result_judgment": closeout["result_judgment"],
            "candidate_count": 0,
            "l5_candidate_count": 0,
        }
    if path == SWEEP_MANIFEST:
        payload["closeout"] = {
            "campaign_closeout": CAMPAIGN_CLOSEOUT.as_posix(),
            "result_judgment": closeout["result_judgment"],
            "counts": closeout["counts"],
        }
    write_yaml(repo_root / path, payload)


def update_idea_and_hypothesis(repo_root: Path, closeout: dict[str, Any]) -> None:
    for path in [IDEA_MANIFEST, HYPOTHESIS_MANIFEST]:
        payload = load_yaml(repo_root / path)
        payload["status"] = FINAL_STATUS
        payload["updated_at_utc"] = closeout["closed_at_utc"]
        payload["claim_boundary"] = CLAIM_BOUNDARY
        payload["evidence_path"] = CAMPAIGN_CLOSEOUT.as_posix()
        payload["next_action"] = NEXT_ACTION
        payload["notes"] = "Session-transition campaign closed with preserved decision-surface clues and no L5 candidate."
        write_yaml(repo_root / path, payload)


def update_wave(repo_root: Path, closeout: dict[str, Any]) -> None:
    wave = load_yaml(repo_root / WAVE_ALLOCATION)
    wave["status"] = "wave01_three_campaigns_closed_no_candidate"
    wave["updated_at_utc"] = closeout["closed_at_utc"]
    wave["claim_boundary"] = "wave01_three_campaigns_closed_no_candidate_not_goal_achieve"
    wave["next_action"] = NEXT_ACTION
    wave["next_action_detail"] = NEXT_ACTION_DETAIL
    for allocation in wave.get("campaign_allocations") or []:
        if allocation.get("campaign_id") != CAMPAIGN_ID:
            continue
        allocation["status"] = FINAL_STATUS
        allocation["claim_boundary"] = CLAIM_BOUNDARY
        allocation["campaign_closeout"] = CAMPAIGN_CLOSEOUT.as_posix()
        allocation["decision_replay_judgment_summary"] = DECISION_REPLAY_SUMMARY.as_posix()
        allocation["remaining_preserved_clue_review"] = REMAINING_CLUE_REVIEW.as_posix()
        allocation["negative_memory_ids"] = closeout["negative_memory_ids"]
        allocation["preserved_clue_ids"] = closeout["preserved_clue_ids"]
        allocation["next_action"] = NEXT_ACTION
        allocation["next_action_detail"] = NEXT_ACTION_DETAIL
    wave["notes"] = (
        "Three Wave01 campaigns closed with no candidate. Session-transition replay produced "
        "one negative memory and preserved decision-surface clues; prepare Wave01 closeout review "
        "or rotate to a genuinely new surface."
    )
    write_yaml(repo_root / WAVE_ALLOCATION, wave)


def update_csv_indexes(repo_root: Path, closeout: dict[str, Any]) -> None:
    upsert_csv_row(
        repo_root / CAMPAIGN_REFS,
        "campaign_id",
        {
            "wave_id": WAVE_ID,
            "campaign_id": CAMPAIGN_ID,
            "campaign_path": CAMPAIGN_MANIFEST.as_posix(),
            "allocation_role": "third_unexplored_session_transition_regime_surface",
            "status": FINAL_STATUS,
            "max_runs": "24",
            "initial_batch_size": "10",
            "claim_boundary": CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
            "notes": "closed with preserved decision-surface clues; candidate_count=0; no L5 candidate",
        },
    )
    upsert_csv_row(
        repo_root / CAMPAIGN_REGISTRY,
        "campaign_id",
        {
            "campaign_id": CAMPAIGN_ID,
            "status": FINAL_STATUS,
            "created_at_utc": "2026-06-22T01:44:27Z",
            "campaign_path": CAMPAIGN_MANIFEST.as_posix(),
            "objective": "Open US100 M5 session transition regime decision holding surface before micro search",
            "axis_tags": (
                "session_transition_surface;target_or_label_surface;feature_or_input_surface;"
                "model_or_training_surface;decision_surface;regime_surface;"
                "horizon_or_holding_policy;evaluation_or_runtime_surface;us100_m5_closed_bar_only"
            ),
            "primary_family": "experiment_design",
            "primary_skill": "spacesonar-experiment-design",
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_path": CAMPAIGN_CLOSEOUT.as_posix(),
            "next_action": NEXT_ACTION,
            "notes": "closed preserved clues; candidate_count=0; no L5 candidate",
        },
    )
    upsert_csv_row(
        repo_root / SURFACE_REGISTRY,
        "surface_id",
        {
            "surface_id": SURFACE_ID,
            "hypothesis_id": HYPOTHESIS_ID,
            "status": FINAL_STATUS,
            "created_at_utc": "2026-06-22T01:44:27Z",
            "surface_path": SURFACE_MANIFEST.as_posix(),
            "label_recipe_id": "label_wave01_session_transition_regime_v0",
            "feature_recipe_id": "feature_wave01_us100_session_transition_regime_v0",
            "feature_recipe_mix_id": "not_applicable_no_mix_in_standard_campaign_open",
            "model_recipe_id": "model_wave01_session_transition_onnx_scout_v0",
            "decision_recipe_id": "decision_wave01_session_transition_abstain_v0",
            "split_recipe_id": "split_set_v0",
            "eval_recipe_id": "eval_wave01_session_transition_runtime_v0",
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_path": CAMPAIGN_CLOSEOUT.as_posix(),
            "next_action": NEXT_ACTION,
            "notes": "session-transition surface closed with preserved decision-surface clues",
        },
    )
    upsert_csv_row(
        repo_root / SWEEP_REGISTRY,
        "sweep_id",
        {
            "sweep_id": SWEEP_ID,
            "campaign_id": CAMPAIGN_ID,
            "surface_id": SURFACE_ID,
            "status": FINAL_STATUS,
            "created_at_utc": "2026-06-22T01:44:27Z",
            "sweep_path": SWEEP_MANIFEST.as_posix(),
            "sweep_type": "broad_session_transition_regime_surface_scout",
            "axis_count": "7",
            "run_ref_path": (CAMPAIGN_ROOT / "sweeps" / SWEEP_ID / "run_refs.csv").as_posix(),
            "evidence_boundary": CLAIM_BOUNDARY,
            "evidence_path": CAMPAIGN_CLOSEOUT.as_posix(),
            "next_action": NEXT_ACTION,
            "notes": "session-transition sweep closed with preserved clues and no candidate",
        },
    )
    upsert_csv_row(
        repo_root / IDEA_REGISTRY,
        "idea_id",
        {
            "idea_id": IDEA_ID,
            "status": FINAL_STATUS,
            "created_at_utc": "2026-06-22T01:44:27Z",
            "axis_tags": "session_transition_surface;regime_surface;decision_surface;holding_policy;us100_m5_only",
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_path": CAMPAIGN_CLOSEOUT.as_posix(),
            "next_action": NEXT_ACTION,
            "notes": "session/regime idea closed with preserved clues and no candidate",
        },
    )
    upsert_csv_row(
        repo_root / HYPOTHESIS_REGISTRY,
        "hypothesis_id",
        {
            "hypothesis_id": HYPOTHESIS_ID,
            "idea_id": IDEA_ID,
            "status": FINAL_STATUS,
            "hypothesis": "Session transition and regime context may expose tradeability/no-trade surfaces",
            "decision_use": "abstain_capable_session_transition_regime_entry_exit_surface",
            "comparison_baseline": "no_trade_session_blind_prior_negative_memory_reference_only",
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_path": CAMPAIGN_CLOSEOUT.as_posix(),
            "next_action": NEXT_ACTION,
            "notes": "session/regime hypothesis closed with preserved clues and no candidate",
        },
    )
    upsert_csv_row(
        repo_root / WAVE_REGISTRY,
        "wave_id",
        {
            "wave_id": WAVE_ID,
            "status": "wave01_three_campaigns_closed_no_candidate",
            "created_at_utc": "2026-06-21T15:18:51Z",
            "wave_path": WAVE_ALLOCATION.as_posix(),
            "allocation_goal": "Map US100 M5 closed-bar task label input decision and holding surfaces before optimization",
            "max_runs": "48",
            "claim_boundary": "wave01_three_campaigns_closed_no_candidate_not_goal_achieve",
            "evidence_path": CAMPAIGN_CLOSEOUT.as_posix(),
            "next_action": NEXT_ACTION,
            "notes": "three campaigns closed no candidate; prepare Wave01 closeout review or rotate",
        },
    )
    upsert_csv_row(
        repo_root / GOAL_REGISTRY,
        "goal_id",
        {
            "goal_id": GOAL_ID,
            "status": "active_long_running",
            "created_at_utc": "2026-06-21T15:18:51Z",
            "goal_path": GOAL_MANIFEST.as_posix(),
            "terminal_contract_path": (GOAL_ROOT / "terminal_eligibility_contract.yaml").as_posix(),
            "active_phase": FINAL_PHASE,
            "claim_boundary": "active_goal_wave01_three_campaigns_closed_not_goal_achieve",
            "next_work_item": NEXT_WORK_ID,
            "notes": "session-transition campaign closed; durable Codex operation still active",
        },
    )


def update_next_work_item(repo_root: Path, closeout: dict[str, Any]) -> None:
    state = git_state(repo_root)
    next_work = {
        "version": "onnx_lab_work_item_v1",
        "work_item_id": NEXT_WORK_ID,
        "active_goal_id": GOAL_ID,
        "created_at_utc": closeout["closed_at_utc"],
        "status": "planned_wave01_closeout_review_or_next_surface_after_session_transition_closeout",
        "current_truth": {
            "claim_boundary": CLAIM_BOUNDARY,
            "latest_closed_campaign_id": CAMPAIGN_ID,
            "latest_closed_campaign_status": FINAL_STATUS,
            "campaign_closeout": CAMPAIGN_CLOSEOUT.as_posix(),
            "negative_memory_ids": closeout["negative_memory_ids"],
            "preserved_clue_ids": closeout["preserved_clue_ids"],
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "next_allowed_shapes": [
                "Wave01_closeout_review",
                "new_multi_axis_surface",
                "bounded_synthesis_previous_material_only",
                "new_decision_surface_for_preserved_clues",
            ],
            "forbidden_carryover": [
                "inverse_score_band_replay_candidate_repair",
                "force_non_directional_event_score_into_side_orders",
                "force_diagnostic_no_trade_score_into_order_execution",
                "feature_only_campaign",
                "label_only_campaign",
                "model_only_campaign",
                "threshold_only_campaign",
                "repair_only_campaign",
            ],
        },
        "work_classification": {
            "primary_family": "experiment_design",
            "detected_families": ["experiment_design", "workspace_state_sync", "run_evidence_system"],
            "mutation_intent": "decide_wave01_closeout_or_next_surface",
        },
        "skill_routing": {
            "primary_family": "experiment_design",
            "primary_skill": "spacesonar-experiment-design",
            "support_skills": [
                "spacesonar-exploration-mandate",
                "spacesonar-run-evidence-system",
                "spacesonar-claim-discipline",
            ],
            "required_gates": [
                "design_contract_check",
                "exploration_coverage_check",
                "campaign_proxy_runtime_parity_policy",
                "final_claim_guard",
            ],
        },
        "acceptance_criteria": [
            "If Wave01 closeout is attempted, verify manifests, registries, evidence, validators, and handoff records.",
            "If another campaign is opened, it must be new multi-axis work or bounded synthesis under policy.",
            "Remaining preserved clues require a newly declared decision surface before trade replay.",
            "Valid proxy/model-bearing runs remain L4 mandatory, with L5 only if L4 remains promising.",
        ],
        "claim_boundary": "planning_wave01_closeout_or_next_surface_no_candidate_no_runtime_authority_no_goal_achieve",
        "forbidden_claims": closeout["forbidden_claims"],
        "next_action": NEXT_ACTION,
        "next_action_detail": NEXT_ACTION_DETAIL,
        "execution_provenance": {
            "git_sha": state["git_sha"],
            "branch": state["branch"],
            "dirty_flag": state["dirty_flag"],
            "changed_files": state["changed_files"],
            "command_argv": [
                "python",
                "foundation/pipelines/close_wave01_session_transition_campaign.py",
                "--write-control-records",
            ],
            "started_at_utc": closeout["closed_at_utc"],
            "ended_at_utc": closeout["closed_at_utc"],
            "input_hashes": [
                artifact_ref(repo_root, DECISION_REPLAY_SUMMARY),
                artifact_ref(repo_root, DECISION_REPLAY_INDEX),
                artifact_ref(repo_root, ADAPTER_ELIGIBILITY_INDEX),
            ],
            "output_hashes": [
                artifact_ref(repo_root, CAMPAIGN_CLOSEOUT),
                artifact_ref(repo_root, REMAINING_CLUE_REVIEW),
                artifact_ref(repo_root, CLUE_MEMORY_PATH),
            ],
            "unknown_git_claim_effect": "not_applicable_git_state_recorded_claim_still_lowered_no_goal_achieve",
        },
    }
    write_yaml(repo_root / NEXT_WORK_ITEM, next_work)


def update_goal_and_workspace(repo_root: Path, closeout: dict[str, Any]) -> None:
    goal = load_yaml(repo_root / GOAL_MANIFEST)
    goal["updated_at_utc"] = closeout["closed_at_utc"]
    goal["active_phase"] = FINAL_PHASE
    goal["claim_boundary"] = "active_goal_wave01_three_campaigns_closed_not_goal_achieve"
    goal["next_work_item"] = {
        "path": NEXT_WORK_ITEM.as_posix(),
        "work_item_id": NEXT_WORK_ID,
        "summary": "Prepare Wave01 closeout review or open next multi-axis surface.",
    }
    session = goal.setdefault("session_transition_campaign", {})
    session["status"] = FINAL_STATUS
    session["campaign_closeout"] = CAMPAIGN_CLOSEOUT.as_posix()
    session["claim_boundary"] = CLAIM_BOUNDARY
    session["next_work_item"] = NEXT_WORK_ID
    session["negative_memory_ids"] = closeout["negative_memory_ids"]
    session["preserved_clue_ids"] = closeout["preserved_clue_ids"]
    session["candidate_count"] = 0
    session["l5_candidate_count"] = 0
    session["campaign_closeout_counts"] = closeout["counts"]
    write_yaml(repo_root / GOAL_MANIFEST, goal)

    workspace = load_yaml(repo_root / WORKSPACE_STATE)
    workspace["updated_utc"] = closeout["closed_at_utc"]
    claims = workspace.setdefault("current_claims", {})
    claims["active_goal_phase"] = FINAL_PHASE
    claims["active_goal_claim_boundary"] = "active_goal_wave01_three_campaigns_closed_not_goal_achieve"
    claims["next_work_item_id"] = NEXT_WORK_ID
    claims["wave0_third_campaign_status"] = FINAL_STATUS
    claims["wave0_third_campaign_claim_boundary"] = CLAIM_BOUNDARY
    claims["wave0_third_campaign_next_work_item"] = NEXT_WORK_ID
    claims["wave01_session_transition_campaign_closeout"] = CAMPAIGN_CLOSEOUT.as_posix()
    claims["wave01_session_transition_campaign_status"] = FINAL_STATUS
    claims["wave01_session_transition_campaign_claim_boundary"] = CLAIM_BOUNDARY
    claims["wave01_session_transition_candidate_count"] = 0
    claims["wave01_session_transition_l5_candidate_count"] = 0
    claims["wave01_session_transition_remaining_preserved_clue_review"] = REMAINING_CLUE_REVIEW.as_posix()
    claims["wave01_session_transition_preserved_clue_ids"] = closeout["preserved_clue_ids"]
    claims["wave01_session_transition_campaign_closeout_counts"] = closeout["counts"]
    write_yaml(repo_root / WORKSPACE_STATE, workspace)


def update_resume_cursor(repo_root: Path, closeout: dict[str, Any]) -> None:
    resume = load_yaml(repo_root / RESUME_CURSOR)
    resume["updated_at_utc"] = closeout["closed_at_utc"]
    resume["active_phase"] = FINAL_PHASE
    sources = resume.setdefault("current_truth_sources", [])
    for source in [
        CAMPAIGN_CLOSEOUT.as_posix(),
        REMAINING_CLUE_REVIEW.as_posix(),
        REMAINING_CLUE_INDEX.as_posix(),
        CLUE_MEMORY_PATH.as_posix(),
        CAMPAIGN_MANIFEST.as_posix(),
        SURFACE_MANIFEST.as_posix(),
        SWEEP_MANIFEST.as_posix(),
        CAMPAIGN_REFS.as_posix(),
        CAMPAIGN_REGISTRY.as_posix(),
        SURFACE_REGISTRY.as_posix(),
        SWEEP_REGISTRY.as_posix(),
        WAVE_ALLOCATION.as_posix(),
        WAVE_REGISTRY.as_posix(),
    ]:
        if source not in sources:
            sources.append(source)
    resume["latest_completed_work"] = {
        "work_item_id": WORK_ITEM_ID,
        "result_judgment": closeout["result_judgment"],
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_paths": [CAMPAIGN_CLOSEOUT.as_posix(), CLUE_MEMORY_PATH.as_posix()],
    }
    resume["next_work_item"] = {"work_item_id": NEXT_WORK_ID, "path": NEXT_WORK_ITEM.as_posix()}
    write_yaml(repo_root / RESUME_CURSOR, resume)


def upsert_artifact_registry(repo_root: Path) -> None:
    producer = "python foundation/pipelines/close_wave01_session_transition_campaign.py --write-control-records"

    def put(artifact_id: str, artifact_type: str, path: Path, consumer: str, claim_boundary: str, notes: str) -> None:
        full = repo_root / path
        upsert_csv_row(
            repo_root / ARTIFACT_REGISTRY,
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
                "producer_command": producer,
                "regeneration_command": producer,
                "source_of_truth": path.as_posix(),
                "consumer": consumer,
                "claim_boundary": claim_boundary,
                "notes": notes,
            },
        )

    put("artifact_wave01_session_transition_campaign_manifest_v0", "campaign_manifest", CAMPAIGN_MANIFEST, CAMPAIGN_ID, CLAIM_BOUNDARY, "Session transition campaign manifest closed with preserved clues")
    put("artifact_wave01_session_transition_surface_manifest_v0", "surface_manifest", SURFACE_MANIFEST, SURFACE_ID, CLAIM_BOUNDARY, "Session transition surface synchronized to campaign closeout")
    put("artifact_wave01_session_transition_sweep_manifest_v0", "sweep_manifest", SWEEP_MANIFEST, SWEEP_ID, CLAIM_BOUNDARY, "Session transition sweep synchronized to campaign closeout")
    put("artifact_wave0_campaign_refs_v0", "wave_campaign_refs", CAMPAIGN_REFS, WAVE_ID, "wave01_three_campaigns_closed_no_candidate_not_goal_achieve", "Wave campaign refs synchronized after session transition closeout")
    put("artifact_wave01_wave_allocation_v0", "wave_allocation", WAVE_ALLOCATION, WAVE_ID, "wave01_three_campaigns_closed_no_candidate_not_goal_achieve", "Wave allocation synchronized after session transition closeout")
    put("artifact_wave01_session_transition_campaign_closeout_v0", "campaign_closeout", CAMPAIGN_CLOSEOUT, CAMPAIGN_ID, CLAIM_BOUNDARY, "Source-of-truth campaign closeout for Wave01 session-transition campaign")
    put("artifact_wave01_session_transition_remaining_preserved_clue_review_v0", "preserved_clue_review", REMAINING_CLUE_REVIEW, CAMPAIGN_ID, CLAIM_BOUNDARY, "Remaining preserved clues require new decision-surface semantics")
    put("artifact_wave01_session_transition_remaining_preserved_clue_index_v0", "preserved_clue_review_index", REMAINING_CLUE_INDEX, CAMPAIGN_ID, CLAIM_BOUNDARY, "Index of remaining session-transition preserved clues")
    put("artifact_wave01_session_transition_remaining_clue_memory_v0", "clue_memory", CLUE_MEMORY_PATH, CAMPAIGN_ID, CLAIM_BOUNDARY, "Preserved clue memory for future decision-surface campaign")


def write_records(repo_root: Path, closed_at: str) -> dict[str, Any]:
    review, review_rows, clue_memory = build_remaining_preserved_clue_review(repo_root, created_at_utc=closed_at)
    write_yaml(repo_root / REMAINING_CLUE_REVIEW, review)
    write_csv(repo_root / REMAINING_CLUE_INDEX, review_rows, review_fieldnames())
    write_yaml(repo_root / CLUE_MEMORY_PATH, clue_memory)
    closeout = build_closeout(repo_root, closed_at)
    write_yaml(repo_root / CAMPAIGN_CLOSEOUT, closeout)
    update_manifest_common(CAMPAIGN_MANIFEST, repo_root, closeout)
    update_manifest_common(SURFACE_MANIFEST, repo_root, closeout)
    update_manifest_common(SWEEP_MANIFEST, repo_root, closeout)
    update_idea_and_hypothesis(repo_root, closeout)
    update_wave(repo_root, closeout)
    update_csv_indexes(repo_root, closeout)
    update_next_work_item(repo_root, closeout)
    update_goal_and_workspace(repo_root, closeout)
    update_resume_cursor(repo_root, closeout)
    upsert_artifact_registry(repo_root)
    return closeout


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--write-control-records", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    closed_at = utc_now()
    closeout = build_closeout(repo_root, closed_at)
    if args.write_control_records:
        closeout = write_records(repo_root, closed_at)
    print(
        {
            "status": closeout["status"],
            "campaign_closeout": CAMPAIGN_CLOSEOUT.as_posix(),
            "candidate_count": closeout["counts"]["candidate_count"],
            "l5_candidate_count": closeout["counts"]["l5_candidate_count"],
            "remaining_preserved_clue_count": closeout["counts"]["remaining_preserved_clue_count"],
            "next_work_item": NEXT_WORK_ID,
            "claim_boundary": closeout["claim_boundary"],
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
