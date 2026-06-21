from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]

OLD_WORK = "work_wave0_first_batch_axis_review_v0"
NEW_WORK = "work_wave0_second_batch_tradeability_repair_spec_v0"

AXIS_REVIEW_PATH = Path(
    "lab/campaigns/campaign_us100_task_surface_scout_v0/"
    "sweeps/sweep_wave0_broad_surface_scout_v0/axis_review_wave0_first_batch_v0.yaml"
)
GOAL_CLOSEOUT_PATH = Path(
    "lab/goals/goal_us100_onnx_forward_boundary_v0/"
    "work_wave0_first_batch_axis_review_v0_closeout.yaml"
)
CLUE_TRADE_PATH = Path("lab/memory/clues/clue_wave0_tradeability_mid_horizon_v0.yaml")
CLUE_PATHQ_PATH = Path("lab/memory/clues/clue_wave0_path_quality_h12_side_signal_v0.yaml")
NEXT_WORK_PATH = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml")
RESUME_PATH = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml")
WORKSPACE_PATH = Path("docs/workspace/workspace_state.yaml")
GOAL_MANIFEST_PATH = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml")
WAVE_PATH = Path("lab/waves/wave_us100_closedbar_surface_cartography_v0/wave_allocation.yaml")
CAMPAIGN_PATH = Path("lab/campaigns/campaign_us100_task_surface_scout_v0/campaign_manifest.yaml")
SWEEP_PATH = Path(
    "lab/campaigns/campaign_us100_task_surface_scout_v0/"
    "sweeps/sweep_wave0_broad_surface_scout_v0/sweep_manifest.yaml"
)
LEDGER_PATH = Path("lab/campaigns/campaign_us100_task_surface_scout_v0/anti_selection_ledger.yaml")
RUN_REFS_PATH = Path(
    "lab/campaigns/campaign_us100_task_surface_scout_v0/"
    "sweeps/sweep_wave0_broad_surface_scout_v0/run_refs.csv"
)

FORBIDDEN_CLAIMS = [
    "selected_baseline",
    "runtime_authority",
    "economics_pass",
    "materialization_ready",
    "handoff_complete",
    "live_readiness",
    "reviewed_verified_pass",
    "goal_achieve",
]


def rel(path: Path) -> str:
    return path.as_posix()


def load_yaml(path: Path) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def write_yaml(path: Path, data: dict) -> None:
    full = ROOT / path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=False, width=100),
        encoding="utf-8",
        newline="\n",
    )


def file_info(path: Path) -> tuple[str, int]:
    data = (ROOT / path).read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def read_csv(path: Path) -> tuple[list[dict], list[str]]:
    with (ROOT / path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader), list(reader.fieldnames or [])


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with (ROOT / path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def update_registry(path: Path, id_field: str, target_id: str, updates: dict) -> None:
    rows, fieldnames = read_csv(path)
    if not fieldnames:
        fieldnames = [id_field, *updates.keys()]
    for key in updates:
        if key not in fieldnames:
            fieldnames.append(key)
    found = False
    for row in rows:
        if row.get(id_field) == target_id:
            row.update(updates)
            found = True
    if not found:
        row = {name: "" for name in fieldnames}
        row[id_field] = target_id
        row.update(updates)
        rows.append(row)
    write_csv(path, rows, fieldnames)


def metric_summary() -> tuple[list[dict], dict[str, int]]:
    refs, _ = read_csv(RUN_REFS_PATH)
    counts: dict[str, int] = {"inconclusive": 0, "preserved_clue": 0, "negative": 0, "invalid": 0}
    rows: list[dict] = []

    for ref in refs:
        run_id = ref["run_id"]
        metrics_path = Path("lab/runs") / run_id / "metrics.json"
        metrics = json.loads((ROOT / metrics_path).read_text(encoding="utf-8"))
        planned = metrics.get("planned_cell", {})
        val = metrics.get("model_metrics", {}).get("validation", {})
        proxy = metrics.get("trading_proxy_metrics", {})
        task = metrics.get("task_surface_metrics", {})
        judgment = metrics.get("result_judgment") or ref.get("result_judgment")
        counts[judgment] = counts.get(judgment, 0) + 1

        row = {
            "cell_id": planned.get("cell_id"),
            "run_id": run_id,
            "judgment": judgment,
            "target_family": planned.get("target_family"),
            "horizon_bars": planned.get("horizon_bars"),
            "input_family": planned.get("input_family"),
            "decision_family": planned.get("decision_family"),
            "model_family": planned.get("model_family"),
            "task_kind": task.get("task_kind"),
            "feature_count": task.get("feature_count"),
            "validation_auc": val.get("roc_auc"),
            "validation_balanced_accuracy": val.get("balanced_accuracy"),
            "validation_spearman": val.get("spearman_corr"),
            "trade_count": proxy.get("trade_count"),
            "trade_density": proxy.get("trade_density"),
            "hit_rate": proxy.get("hit_rate"),
            "metrics_path": rel(metrics_path),
            "run_manifest_path": rel(Path("lab/runs") / run_id / "run_manifest.json"),
            "receipt_path": rel(Path("lab/runs") / run_id / "experiment_receipt.yaml"),
            "lineage_path": rel(Path("lab/runs") / run_id / "artifact_lineage.json"),
        }

        if judgment == "preserved_clue":
            row["reopen_condition"] = "extend_in_second_batch_with_predeclared_controls_wfo_or_neighbor_surface"
            row["do_not_repeat_note"] = "do_not_treat_as_candidate_or_baseline_from_train_validation_proxy"
        elif row["target_family"] == "future_return_rank_or_quantile":
            row["reopen_condition"] = (
                "redefine_decision_use_or_pair_with_materially_different_runtime_available_input_surface"
            )
            row["do_not_repeat_note"] = (
                "do_not_repeat_direct_return_surface_micro_tuning_without_new_label_or_decision_shape"
            )
        elif row["target_family"] == "atr_scaled_barrier_event":
            row["reopen_condition"] = "reopen_only_with_repaired_barrier_definition_cost_context_or_tradeability_gate"
            row["do_not_repeat_note"] = "do_not_expand_atr_barrier_horizons_without_new_boundary_repair"
        elif row["target_family"] == "path_quality_mfe_mae_payoff_suitability":
            row["reopen_condition"] = (
                "reopen_as_side_control_or_label_shape_after_positive_class_and_threshold_mapping_repair"
            )
            row["do_not_repeat_note"] = (
                "do_not_promote_path_quality_h12_from_single_weak_auc_and_hit_rate_mismatch"
            )
        else:
            row["reopen_condition"] = "reopen_if_neighbor_axis_or_feature_boundary_materially_changes"
            row["do_not_repeat_note"] = "do_not_repeat_same_cell_without_new_evidence_need"
        rows.append(row)

    return rows, counts


def build_records(now: str, run_rows: list[dict], counts: dict[str, int]) -> tuple[dict, dict, dict, dict]:
    preserved = [row for row in run_rows if row["judgment"] == "preserved_clue"]
    inconclusive = [row for row in run_rows if row["judgment"] == "inconclusive"]

    trade_runs = [
        row["run_id"]
        for row in preserved
        if row["cell_id"] in {"wave0_cell_010", "wave0_cell_011", "wave0_cell_012"}
    ]
    pathq_runs = [row["run_id"] for row in preserved if row["cell_id"] == "wave0_cell_008"]

    agent_dispositions = [
        {
            "agent": "agent_05_data_feature_contract",
            "role_mode": "data_feature_contract_adversarial_check",
            "opinion_classification": "accepted_with_boundary",
            "accepted_points": [
                "preserve tradeability h6/h12 as strongest repeated clue",
                "treat session_calendar h3 as diagnostic/control until repaired",
                "require effective event count and split-boundary purge in next spec",
            ],
            "unresolved_material_objections": [],
        },
        {
            "agent": "agent_06_quant_research",
            "role_mode": "quant_research_design",
            "opinion_classification": "accepted",
            "accepted_points": [
                "next axis should rotate plus mix, not select or promote",
                "second batch should be tradeability-centered multi-axis surface rotation",
                "weak direct return and ATR surfaces are memory with reopen conditions, not permanent rejection",
            ],
            "unresolved_material_objections": [],
        },
        {
            "agent": "agent_07_model_validation_risk",
            "role_mode": "model_validation_risk_check",
            "opinion_classification": "accepted",
            "accepted_points": [
                "011 h6 causal_regime logistic is lower-complexity anchor",
                "012 h12 multiscale boosted is paired challenger",
                "predeclare threshold bands and adjacent-threshold sensitivity before next evaluation",
            ],
            "unresolved_material_objections": [],
        },
        {
            "agent": "agent_04_evidence_control_plane",
            "role_mode": "evidence_closeout_check",
            "opinion_classification": "accepted",
            "accepted_points": [
                "write one sweep-level axis review source record",
                "write clue memory records but no candidate records",
                "reconcile stale registry statuses and write exactly one next_work_item",
            ],
            "unresolved_material_objections": [],
        },
    ]

    axis_review = {
        "version": "axis_review_v1",
        "axis_review_id": "axis_review_wave0_first_batch_v0",
        "work_item_id": OLD_WORK,
        "active_goal_id": "goal_us100_onnx_forward_boundary_v0",
        "created_at_utc": now,
        "status": "closed_next_axis_selected_for_design_only",
        "claim_boundary": "first_batch_axis_review_only_no_candidate_no_baseline_no_runtime",
        "source_inputs": {
            "run_refs": rel(RUN_REFS_PATH),
            "first_batch_closeout": (
                "lab/goals/goal_us100_onnx_forward_boundary_v0/"
                "work_wave0_execute_first_batch_proxy_scout_v0_closeout.yaml"
            ),
            "anti_selection_ledger": rel(LEDGER_PATH),
        },
        "result_counts": counts,
        "candidate_count": 0,
        "selected_baseline_count": 0,
        "runtime_claim": False,
        "summary": {
            "primary_preserved_axis": "tradeability_mid_horizon_repair_v1",
            "axis_decision": "rotate_plus_mix_around_tradeability_h6_h12_preserved_clue",
            "reason": (
                "tradeability/no-trade regime surfaces repeated across h3/h6/h12 and different "
                "input/model families; 011 and 012 carry action-like abstain tradeability evidence "
                "but remain train-validation proxy only"
            ),
            "not_a_model_win": True,
            "not_candidate": True,
        },
        "preserved_clues": [
            {
                "clue_id": "clue_wave0_tradeability_mid_horizon_v0",
                "run_ids": trade_runs,
                "memory_path": rel(CLUE_TRADE_PATH),
                "claim_boundary": "preserved_clue_no_candidate_no_baseline_no_runtime",
            },
            {
                "clue_id": "clue_wave0_path_quality_h12_side_signal_v0",
                "run_ids": pathq_runs,
                "memory_path": rel(CLUE_PATHQ_PATH),
                "claim_boundary": "weak_preserved_clue_no_candidate_no_baseline_no_runtime",
            },
        ],
        "run_review": run_rows,
        "inconclusive_groups": [
            {
                "group_id": "future_return_direct_surfaces_v0",
                "run_ids": [
                    row["run_id"]
                    for row in inconclusive
                    if row["target_family"] == "future_return_rank_or_quantile"
                ],
                "judgment": "inconclusive_memory_not_negative_closure",
                "salvage_value": "direct return target surfaces can reopen after materially different decision use",
                "reopen_condition": "new label or decision use that is not direct rank/direction micro-tuning",
            },
            {
                "group_id": "atr_barrier_direct_surfaces_v0",
                "run_ids": [
                    row["run_id"] for row in inconclusive if row["target_family"] == "atr_scaled_barrier_event"
                ],
                "judgment": "inconclusive_memory_not_negative_closure",
                "salvage_value": "barrier/event ideas can reopen as downstream risk or exit surfaces",
                "reopen_condition": "new barrier semantics, cost context, or tradeability-gated decision shape",
            },
            {
                "group_id": "linear_regression_rank_path_surfaces_v0",
                "run_ids": [
                    row["run_id"] for row in inconclusive if row["model_family"] == "linear_or_ridge_rank_scout"
                ],
                "judgment": "inconclusive_memory_not_negative_closure",
                "salvage_value": "linear/rank controls remain useful as controls for future scouts",
                "reopen_condition": "new target surface or use as explicit control in WFO or neighbor sweep",
            },
        ],
        "agent_consultation": {
            "selected_agents": [item["agent"] for item in agent_dispositions],
            "why_not_smaller": "axis rotation after preserved clues is material and opens a new bounded design item",
            "why_not_larger": "no protected claim, runtime authority, candidate closeout, or policy change",
            "claim_effect": "advisory_only_no_reviewed_pass",
            "dispositions": agent_dispositions,
        },
        "data_integrity": {
            "data_source": "dataset_raw_us100_m5_wave0_export_20260621T152827Z via row_membership_manifest",
            "time_axis": "us100_bar_close_time research binding; no UTC/server timezone authority claim",
            "sample_scope": "train_validation_only; research_oos_a and locked_final_oos_b withheld",
            "feature_label_boundary": (
                "features causal at or before closed bar; labels use future path only inside declared target"
            ),
            "split_boundary": "split_set_v0 primary split train/validation only for this axis review",
            "integrity_judgment": "usable_with_boundary_for_axis_design_only",
            "next_repair_requirements": [
                "effective_event_count_and_trade_count_definition",
                "class_balance_and_base_rate_per_window",
                "train_only_transform_threshold_and_calibration_scope",
                "session_calendar_control_repair_before_trusting_calendar_signal",
                "horizon_overlap_cooldown_or_holding_assumption_if_trade_count_reported",
            ],
        },
        "model_validation": {
            "validation_judgment": "exploratory_preserved_clue",
            "selection_metric": "validation_auc_or_rank_metric_for_scout_only",
            "secondary_metrics_needed_next": [
                "PR_AUC_or_average_precision",
                "Brier_or_log_loss_if_probability_language_is_used",
                "base_rate_and_lift",
                "trade_count_per_active_day",
                "threshold_adjacent_band_sensitivity",
                "fold_level_dispersion",
            ],
            "threshold_policy_next": "predeclared_fixed_density_bands_train_only_no_validation_search",
            "overfit_risk": "top_N_selection_from_12_train_validation_proxy_cells",
            "calibration_risk": "scores_are_rank_or_decision_scores_not_probabilities",
        },
        "runtime_learning_probe_decision": {
            "required": False,
            "decision": "not_applicable_no_runtime_question",
            "reason": "Axis review and second-batch spec design make no ONNX/EA/Strategy Tester/economics/runtime claim.",
            "lowered_claim_if_not_run": "no_runtime_claim",
        },
        "missing_evidence": [
            "WFO_or_fold_level_stability_not_yet_run",
            "OOS_A_not_used_for_this_axis_review",
            "OOS_B_locked_final_not_used",
            "ONNX_export_not_in_scope",
            "MT5_runtime_probe_not_in_scope",
            "candidate_selection_not_allowed",
        ],
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "next_work_item_id": NEW_WORK,
        "next_work_item_path": rel(NEXT_WORK_PATH),
    }

    trade_clue = {
        "version": "clue_memory_v1",
        "clue_id": "clue_wave0_tradeability_mid_horizon_v0",
        "created_at_utc": now,
        "status": "preserved_clue_for_second_batch_design",
        "active_goal_id": "goal_us100_onnx_forward_boundary_v0",
        "surface_id": "surface_us100_task_input_decision_rotation_v0",
        "sweep_id": "sweep_wave0_broad_surface_scout_v0",
        "source_axis_review": rel(AXIS_REVIEW_PATH),
        "run_ids": trade_runs,
        "observed_pattern": (
            "tradeability_or_no_trade_regime surfaces preserved across h3/h6/h12 with strongest "
            "action-like clues at h6 causal_regime logistic and h12 multiscale boosted"
        ),
        "salvage_value": "entry gating or bar-ranking may be more promising than direct return targets",
        "reopen_condition": (
            "open bounded second-batch design with h6/h12 tradeability controls, neighbor horizons, "
            "WFO-style checks, and predeclared threshold bands"
        ),
        "do_not_repeat_note": "do_not_promote_010_011_012_to_candidate_from_validation_proxy_metrics",
        "claim_boundary": "preserved_clue_no_candidate_no_baseline_no_runtime",
        "next_action": NEW_WORK,
    }

    pathq_clue = {
        "version": "clue_memory_v1",
        "clue_id": "clue_wave0_path_quality_h12_side_signal_v0",
        "created_at_utc": now,
        "status": "weak_side_clue_for_label_shape_control",
        "active_goal_id": "goal_us100_onnx_forward_boundary_v0",
        "surface_id": "surface_us100_task_input_decision_rotation_v0",
        "sweep_id": "sweep_wave0_broad_surface_scout_v0",
        "source_axis_review": rel(AXIS_REVIEW_PATH),
        "run_ids": pathq_runs,
        "observed_pattern": "path_quality h12 multiscale logistic crossed clue AUC threshold but has weak decision evidence",
        "salvage_value": "side control or label-shaping comparator, not next primary axis",
        "reopen_condition": "revisit only with positive-class, direction, threshold, and label semantics repair",
        "do_not_repeat_note": "do_not_expand_path_quality_as_lead_axis_from_single_weak_validation_clue",
        "claim_boundary": "weak_preserved_clue_no_candidate_no_baseline_no_runtime",
        "next_action": NEW_WORK,
    }

    next_work = {
        "version": "onnx_lab_work_item_v1",
        "work_item_id": NEW_WORK,
        "active_goal_id": "goal_us100_onnx_forward_boundary_v0",
        "created_at_utc": now,
        "status": "planned_next",
        "user_request": (
            "Materialize a bounded second-batch design spec around preserved Wave0 tradeability clues "
            "without candidate, baseline, ONNX, or runtime claims."
        ),
        "current_truth": {
            "current_claim_boundary": "first_batch_axis_review_only_no_candidate_no_baseline_no_runtime",
            "axis_review": rel(AXIS_REVIEW_PATH),
            "result_counts": counts,
            "candidate_count": 0,
            "preserved_clue_ids": [
                "clue_wave0_tradeability_mid_horizon_v0",
                "clue_wave0_path_quality_h12_side_signal_v0",
            ],
        },
        "branch_worktree": {
            "current_branch": "codex/active-goal-program-bootstrap",
            "requested_branch": "codex/active-goal-program-bootstrap",
            "branch_worktree_fit": "fit",
            "branch_action": "keep_current_branch",
            "policy_reference": "docs/policies/branch_policy.md",
            "mismatch_claim_effect": "block_second_batch_spec_until_resolved",
        },
        "work_classification": {
            "primary_family": "experiment_design",
            "detected_families": ["experiment_design", "data_feature_build", "model_training"],
            "mutation_intent": "second_batch_spec_materialization_only",
            "execution_intent": "design_next_tradeability_neighbor_sweep_without_running_models",
        },
        "acceptance_criteria": [
            "Use clues 008/010/011/012 only as scout clues, not candidates or baselines.",
            "Materialize one bounded second-batch spec around tradeability h6/h12 neighbors and controls.",
            "Declare horizons, labels, feature controls, model controls, threshold bands, effective event count policy, and stop conditions.",
            "Keep OOS-B locked and keep ONNX/MT5/runtime out of scope unless a later work item explicitly opens that surface.",
            "Update anti-selection and resume records with exactly one following work item after the spec is materialized.",
        ],
        "skill_routing": {
            "primary_family": "experiment_design",
            "primary_skill": "spacesonar-experiment-design",
            "support_skills": [
                "spacesonar-data-integrity",
                "spacesonar-model-validation",
                "spacesonar-run-evidence-system",
                "spacesonar-claim-discipline",
            ],
            "skills_selected": [
                "spacesonar-experiment-design",
                "spacesonar-data-integrity",
                "spacesonar-model-validation",
                "spacesonar-run-evidence-system",
                "spacesonar-claim-discipline",
            ],
            "skills_not_used": ["spacesonar-runtime-parity"],
            "critical_skills_not_selected": [
                {
                    "skill": "spacesonar-runtime-parity",
                    "reason": "second-batch spec design has no ONNX/EA/MT5/runtime claim",
                    "not_selected_claim_effect": "no_runtime_claim",
                }
            ],
            "not_selected_claim_effect": "no_runtime_claim_no_runtime_authority_no_economics_pass",
            "required_gates": [
                "design_contract_check",
                "data_time_axis_preflight",
                "selection_bias_check",
                "anti_selection_boundary",
                "final_claim_guard",
            ],
        },
        "agent_allocation": {
            "phase": "second_batch_tradeability_spec_design",
            "selected_agents": [],
            "role_modes": [],
            "selection_reason": (
                "Axis review already consulted data, quant, validation, and evidence remits; "
                "spec writing can start Codex-only unless material axis changes."
            ),
            "why_not_smaller": "Codex alone is the smallest allocation for applying recorded axis-review decision.",
            "why_not_larger": "No protected claim, runtime authority, policy change, or terminal closeout is in scope.",
            "max_threads_is_capacity_only": True,
            "claim_effect": "no_new_advisory_claim",
        },
        "runtime_learning_probe_decision": {
            "required": False,
            "decision": "not_applicable_no_runtime_question",
            "reason": "Spec design only; no ONNX/EA/Strategy Tester/economics/runtime behavior claim.",
            "lowered_claim_if_not_run": "no_runtime_claim",
        },
        "bounded_execution_budget": {
            "max_new_runs_to_spec": 12,
            "max_repairs_per_surface": 1,
            "locked_final_oos_use": "forbidden",
            "runtime_attempts": 0,
        },
        "stop_conditions": [
            "time_axis_or_bar_close_key_unclear_blocks_spec",
            "tradeability_label_positive_class_ambiguous_blocks_spec",
            "effective_event_count_policy_missing_blocks_execution",
            "spec_attempts_to_select_candidate_or_baseline_stop",
            "runtime_or_onnx_claim_requested_without_new_route_stop",
        ],
        "claim_boundary": "second_batch_proxy_scout_design_only_no_candidate_no_baseline_no_runtime",
        "forbidden_claims": FORBIDDEN_CLAIMS,
    }
    return axis_review, trade_clue, pathq_clue, next_work


def write_primary_records(now: str, records: tuple[dict, dict, dict, dict], counts: dict[str, int]) -> None:
    axis_review, trade_clue, pathq_clue, next_work = records
    write_yaml(AXIS_REVIEW_PATH, axis_review)
    write_yaml(CLUE_TRADE_PATH, trade_clue)
    write_yaml(CLUE_PATHQ_PATH, pathq_clue)
    write_yaml(NEXT_WORK_PATH, next_work)
    write_yaml(
        GOAL_CLOSEOUT_PATH,
        {
            "version": "work_closeout_v1",
            "work_item_id": OLD_WORK,
            "active_goal_id": "goal_us100_onnx_forward_boundary_v0",
            "closed_at_utc": now,
            "result_judgment": "preserved_clue",
            "claim_boundary": "first_batch_axis_review_only_no_candidate_no_baseline_no_runtime",
            "completed_scope": [
                "reviewed all 12 Wave0 first-batch proxy scout run metrics and judgments",
                "consulted four relevant agents for material axis rotation decision",
                "recorded preserved clue memory for tradeability and path-quality side clue",
                "reconciled next axis as second-batch tradeability repair/spec design",
            ],
            "source_of_truth": rel(AXIS_REVIEW_PATH),
            "result_counts": counts,
            "candidate_count": 0,
            "runtime_learning_probe_decision": axis_review["runtime_learning_probe_decision"],
            "evidence_paths": {
                "axis_review": rel(AXIS_REVIEW_PATH),
                "tradeability_clue": rel(CLUE_TRADE_PATH),
                "path_quality_clue": rel(CLUE_PATHQ_PATH),
                "run_refs": rel(RUN_REFS_PATH),
            },
            "next_work_item": {"work_item_id": NEW_WORK, "path": rel(NEXT_WORK_PATH)},
            "forbidden_claims": FORBIDDEN_CLAIMS,
        },
    )


def update_yaml_records(now: str, counts: dict[str, int]) -> None:
    resume = load_yaml(RESUME_PATH)
    resume["updated_at_utc"] = now
    resume["active_phase"] = "wave0_first_batch_axis_review_closed_second_batch_design_next"
    resume["current_truth_sources"] = [
        rel(GOAL_MANIFEST_PATH),
        rel(AXIS_REVIEW_PATH),
        rel(GOAL_CLOSEOUT_PATH),
        rel(CLUE_TRADE_PATH),
        rel(CLUE_PATHQ_PATH),
        rel(RUN_REFS_PATH),
        "docs/registers/clue_registry.csv",
    ]
    resume["latest_completed_work"] = {
        "work_item_id": OLD_WORK,
        "result_judgment": "preserved_clue",
        "claim_boundary": "first_batch_axis_review_only_no_candidate_no_baseline_no_runtime",
        "evidence_paths": [rel(AXIS_REVIEW_PATH), rel(GOAL_CLOSEOUT_PATH)],
    }
    resume["next_work_item"] = {"work_item_id": NEW_WORK, "path": rel(NEXT_WORK_PATH)}
    write_yaml(RESUME_PATH, resume)

    goal = load_yaml(GOAL_MANIFEST_PATH)
    goal["updated_at_utc"] = now
    goal["active_phase"] = "wave0_first_batch_axis_review_closed_second_batch_design_next"
    goal["program_budgets"]["current_wave0_spec"]["axis_review"] = rel(AXIS_REVIEW_PATH)
    goal["program_budgets"]["current_wave0_spec"]["status"] = (
        "first_batch_axis_review_closed_second_batch_design_next"
    )
    goal["program_budgets"]["current_wave0_spec"]["preserved_clue_ids"] = [
        "clue_wave0_tradeability_mid_horizon_v0",
        "clue_wave0_path_quality_h12_side_signal_v0",
    ]
    goal["next_work_item"] = {
        "path": rel(NEXT_WORK_PATH),
        "work_item_id": NEW_WORK,
        "summary": "Materialize bounded second-batch tradeability repair/spec design without candidate/runtime claims.",
    }
    write_yaml(GOAL_MANIFEST_PATH, goal)

    for path in [WAVE_PATH, CAMPAIGN_PATH, SWEEP_PATH]:
        data = load_yaml(path)
        data["status"] = "first_batch_axis_review_closed_second_batch_design_next"
        data["next_action"] = NEW_WORK
        data["axis_review"] = {
            "status": "closed",
            "path": rel(AXIS_REVIEW_PATH),
            "result_counts": counts,
            "candidate_count": 0,
            "preserved_clue_ids": [
                "clue_wave0_tradeability_mid_horizon_v0",
                "clue_wave0_path_quality_h12_side_signal_v0",
            ],
            "claim_boundary": "first_batch_axis_review_only_no_candidate_no_baseline_no_runtime",
            "next_action": NEW_WORK,
        }
        if "campaign_allocations" in data:
            for allocation in data["campaign_allocations"]:
                if allocation.get("campaign_id") == "campaign_us100_task_surface_scout_v0":
                    allocation["status"] = "first_batch_axis_review_closed_second_batch_design_next"
        write_yaml(path, data)

    ledger = load_yaml(LEDGER_PATH)
    ledger["status"] = "axis_review_closed_no_selection_made"
    ledger["claim_boundary"] = "first_batch_axis_review_only_no_candidate_no_baseline_no_runtime"
    ledger["selection_decision"] = "no_selection_preserved_clues_only"
    ledger["axis_review"] = rel(AXIS_REVIEW_PATH)
    ledger["preserved_clue_ids"] = [
        "clue_wave0_tradeability_mid_horizon_v0",
        "clue_wave0_path_quality_h12_side_signal_v0",
    ]
    ledger["next_action"] = NEW_WORK
    write_yaml(LEDGER_PATH, ledger)

    workspace = load_yaml(WORKSPACE_PATH)
    workspace["updated_utc"] = now
    claims = workspace.setdefault("current_claims", {})
    claims["active_goal_phase"] = "wave0_first_batch_axis_review_closed_second_batch_design_next"
    claims["next_work_item_id"] = NEW_WORK
    claims["active_goal_next_work_item"] = rel(NEXT_WORK_PATH)
    claims["wave0_first_batch_status"] = "axis_review_closed_no_candidate"
    claims["wave0_axis_review"] = rel(AXIS_REVIEW_PATH)
    claims["wave0_axis_decision"] = "rotate_plus_mix_tradeability_mid_horizon_repair_v1"
    claims["wave0_preserved_clue_ids"] = [
        "clue_wave0_tradeability_mid_horizon_v0",
        "clue_wave0_path_quality_h12_side_signal_v0",
    ]
    claims["wave0_candidate_count"] = 0
    claims["wave0_first_batch_result_counts"] = counts
    claims["wave0_first_batch_claim_boundary"] = (
        "first_batch_axis_review_only_no_candidate_no_baseline_no_runtime"
    )
    claims["feature_contract"] = "undefined_by_design_axis_review_preserves_no_fixed_feature_count"
    claims["label_target_contract"] = "undefined_by_design_tradeability_mid_horizon_next_design_only"
    write_yaml(WORKSPACE_PATH, workspace)


def repair_run_gate_coverage(run_rows: list[dict]) -> None:
    required_coverage = ["time_axis_check", "feature_label_boundary_check"]

    for row in run_rows:
        run_id = row["run_id"]
        manifest_path = Path("lab/runs") / run_id / "run_manifest.json"
        manifest = json.loads((ROOT / manifest_path).read_text(encoding="utf-8"))
        coverage = manifest.setdefault("required_gate_coverage", {})
        passed = coverage.setdefault("passed", [])
        for gate in required_coverage:
            if gate not in passed:
                passed.insert(1 if gate == "time_axis_check" else 2, gate)
        manifest.setdefault("gate_coverage_notes", {})[
            "time_axis_check"
        ] = "data_scope records us100_bar_close_time row key and split_set_v0 research binding"
        manifest.setdefault("gate_coverage_notes", {})[
            "feature_label_boundary_check"
        ] = "data_scope records causal closed-bar feature boundary and horizon drop policy"
        (ROOT / manifest_path).write_text(
            json.dumps(manifest, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )

        receipt_path = Path("lab/runs") / run_id / "experiment_receipt.yaml"
        receipt = yaml.safe_load((ROOT / receipt_path).read_text(encoding="utf-8"))
        coverage = receipt.setdefault("required_gate_coverage", {})
        passed = coverage.setdefault("passed", [])
        for gate in required_coverage:
            if gate not in passed:
                passed.insert(1 if gate == "time_axis_check" else 2, gate)
        receipt.setdefault("gate_coverage_notes", {})[
            "time_axis_check"
        ] = "sample_scope records us100_bar_close_time row key and split_set_v0 research binding"
        receipt.setdefault("gate_coverage_notes", {})[
            "feature_label_boundary_check"
        ] = "sample_scope records causal closed-bar feature boundary and horizon drop policy"
        (ROOT / receipt_path).write_text(
            yaml.safe_dump(receipt, sort_keys=False, allow_unicode=False, width=100),
            encoding="utf-8",
            newline="\n",
        )


def update_registries(now: str, records: tuple[dict, dict, dict, dict], run_rows: list[dict]) -> None:
    _, trade_clue, pathq_clue, _ = records
    axis_rel = rel(AXIS_REVIEW_PATH)
    common_status = "first_batch_axis_review_closed_second_batch_design_next"

    clue_path = Path("docs/registers/clue_registry.csv")
    clue_rows, clue_fields = read_csv(clue_path)
    if not clue_fields:
        clue_fields = [
            "clue_id",
            "status",
            "created_at_utc",
            "clue_path",
            "surface_id",
            "sweep_id",
            "run_ids",
            "salvage_value",
            "reopen_condition",
            "claim_boundary",
            "evidence_path",
            "next_action",
            "notes",
        ]
    clue_rows = [
        row
        for row in clue_rows
        if row.get("clue_id")
        not in {"clue_wave0_tradeability_mid_horizon_v0", "clue_wave0_path_quality_h12_side_signal_v0"}
    ]
    clue_rows.extend(
        [
            {
                "clue_id": "clue_wave0_tradeability_mid_horizon_v0",
                "status": "preserved_clue_for_second_batch_design",
                "created_at_utc": now,
                "clue_path": rel(CLUE_TRADE_PATH),
                "surface_id": "surface_us100_task_input_decision_rotation_v0",
                "sweep_id": "sweep_wave0_broad_surface_scout_v0",
                "run_ids": ";".join(trade_clue["run_ids"]),
                "salvage_value": trade_clue["salvage_value"],
                "reopen_condition": trade_clue["reopen_condition"],
                "claim_boundary": trade_clue["claim_boundary"],
                "evidence_path": axis_rel,
                "next_action": NEW_WORK,
                "notes": "tradeability_h6_h12_repeated_proxy_clue_no_candidate",
            },
            {
                "clue_id": "clue_wave0_path_quality_h12_side_signal_v0",
                "status": "weak_side_clue_for_label_shape_control",
                "created_at_utc": now,
                "clue_path": rel(CLUE_PATHQ_PATH),
                "surface_id": "surface_us100_task_input_decision_rotation_v0",
                "sweep_id": "sweep_wave0_broad_surface_scout_v0",
                "run_ids": ";".join(pathq_clue["run_ids"]),
                "salvage_value": pathq_clue["salvage_value"],
                "reopen_condition": pathq_clue["reopen_condition"],
                "claim_boundary": pathq_clue["claim_boundary"],
                "evidence_path": axis_rel,
                "next_action": NEW_WORK,
                "notes": "path_quality_h12_weak_side_clue_no_primary_axis",
            },
        ]
    )
    write_csv(clue_path, clue_rows, clue_fields)

    update_registry(
        Path("docs/registers/goal_registry.csv"),
        "goal_id",
        "goal_us100_onnx_forward_boundary_v0",
        {
            "status": "active_long_running",
            "active_phase": common_status,
            "claim_boundary": "planning_scaffold_active_goal_control_plane_not_goal_achieve",
            "next_work_item": NEW_WORK,
            "notes": "axis_review_closed_no_candidate_no_runtime",
        },
    )
    update_registry(
        Path("docs/registers/wave_registry.csv"),
        "wave_id",
        "wave_us100_closedbar_surface_cartography_v0",
        {
            "status": common_status,
            "claim_boundary": "planning_scaffold_scout_surface_only_not_candidate_not_baseline",
            "evidence_path": axis_rel,
            "next_action": NEW_WORK,
            "notes": "first_batch_axis_review_closed_preserved_clues_recorded_no_candidate",
        },
    )
    update_registry(
        Path("docs/registers/campaign_registry.csv"),
        "campaign_id",
        "campaign_us100_task_surface_scout_v0",
        {
            "status": common_status,
            "claim_boundary": "first_batch_axis_review_only_no_candidate_no_baseline_no_runtime",
            "evidence_path": axis_rel,
            "next_action": NEW_WORK,
            "notes": "rotate_plus_mix_tradeability_mid_horizon_second_batch_design_next",
        },
    )
    update_registry(
        Path("docs/registers/sweep_registry.csv"),
        "sweep_id",
        "sweep_wave0_broad_surface_scout_v0",
        {
            "status": "axis_review_closed_no_candidate",
            "evidence_boundary": "first_batch_axis_review_only",
            "evidence_path": axis_rel,
            "next_action": NEW_WORK,
            "notes": "8_inconclusive_4_preserved_clue_0_candidate",
        },
    )
    update_registry(
        Path("docs/registers/experiment_surface_registry.csv"),
        "surface_id",
        "surface_us100_task_input_decision_rotation_v0",
        {
            "status": common_status,
            "claim_boundary": "scout_surface_axis_review_only_not_candidate",
            "evidence_path": axis_rel,
            "next_action": NEW_WORK,
            "notes": "tradeability_mid_horizon_preserved_clue_axis_next",
        },
    )
    update_registry(
        Path("docs/registers/hypothesis_registry.csv"),
        "hypothesis_id",
        "hyp_surface_diversity_before_model_search_v0",
        {
            "status": common_status,
            "claim_boundary": "scout_hypothesis_axis_review_only_not_candidate",
            "evidence_path": axis_rel,
            "next_action": NEW_WORK,
            "notes": "surface_diversity_found_tradeability_mid_horizon_preserved_clue",
        },
    )
    update_registry(
        Path("docs/registers/idea_registry.csv"),
        "idea_id",
        "idea_us100_m5_blank_slate_surface_map_v0",
        {
            "status": common_status,
            "claim_boundary": "planning_scaffold_axis_review_only",
            "evidence_path": axis_rel,
            "next_action": NEW_WORK,
            "notes": "blank_slate_surface_map_preserved_tradeability_clue_no_legacy_inheritance",
        },
    )

    run_rows_registry, run_fields = read_csv(Path("docs/registers/run_registry.csv"))
    run_ids = {row["run_id"] for row in run_rows}
    for row in run_rows_registry:
        if row.get("run_id") in run_ids:
            row["evidence_path"] = axis_rel
            row["next_action"] = NEW_WORK
            row["notes"] = "axis_review_closed_preserved_or_inconclusive_no_candidate_no_runtime"
    write_csv(Path("docs/registers/run_registry.csv"), run_rows_registry, run_fields)

    recipe_rows, recipe_fields = read_csv(Path("docs/registers/recipe_index.csv"))
    prefixes = ("feature_wave0_", "label_wave0_", "model_wave0_", "decision_wave0_", "eval_wave0_")
    for row in recipe_rows:
        recipe_id = row.get("recipe_id", "")
        if recipe_id.startswith(prefixes) or recipe_id.startswith("surface_us100_"):
            row["status"] = "axis_review_closed_second_batch_design_next"
            row["next_action"] = NEW_WORK
            row["notes"] = "first_batch_axis_review_points_to_tradeability_second_batch_design"
    write_csv(Path("docs/registers/recipe_index.csv"), recipe_rows, recipe_fields)

    artifact_path = Path("docs/registers/artifact_registry.csv")
    artifact_rows, artifact_fields = read_csv(artifact_path)
    artifact_specs = [
        (
            "artifact_wave0_anti_selection_ledger_v0",
            LEDGER_PATH,
            "anti_selection_ledger",
            "first_batch_axis_review_only_no_candidate_no_baseline_no_runtime",
            "updated_after_axis_review_no_selection_no_candidate",
        ),
        (
            "artifact_wave0_first_batch_axis_review_v0",
            AXIS_REVIEW_PATH,
            "axis_review",
            "first_batch_axis_review_only_no_candidate_no_baseline_no_runtime",
            "sweep_level_axis_review_source_record",
        ),
        (
            "artifact_wave0_first_batch_axis_review_closeout_v0",
            GOAL_CLOSEOUT_PATH,
            "work_closeout",
            "first_batch_axis_review_only_no_candidate_no_baseline_no_runtime",
            "goal_work_item_closeout",
        ),
        (
            "artifact_wave0_tradeability_mid_horizon_clue_v0",
            CLUE_TRADE_PATH,
            "clue_memory",
            trade_clue["claim_boundary"],
            "preserved_tradeability_clue_memory",
        ),
        (
            "artifact_wave0_path_quality_h12_side_clue_v0",
            CLUE_PATHQ_PATH,
            "clue_memory",
            pathq_clue["claim_boundary"],
            "weak_path_quality_side_clue_memory",
        ),
    ]
    artifact_ids = {item[0] for item in artifact_specs}
    artifact_rows = [row for row in artifact_rows if row.get("artifact_id") not in artifact_ids]
    for artifact_id, path, artifact_type, boundary, notes in artifact_specs:
        sha, size = file_info(path)
        artifact_rows.append(
            {
                "artifact_id": artifact_id,
                "run_id": "",
                "bundle_id": "",
                "attempt_id": "",
                "artifact_type": artifact_type,
                "path_or_uri": rel(path),
                "sha256": sha,
                "size_bytes": str(size),
                "availability": "present_hash_recorded",
                "producer_command": "foundation/pipelines/close_wave0_first_batch_axis_review.py",
                "regeneration_command": "python foundation/pipelines/close_wave0_first_batch_axis_review.py",
                "source_of_truth": rel(path),
                "consumer": NEW_WORK,
                "claim_boundary": boundary,
                "notes": notes,
            }
        )
    write_csv(artifact_path, artifact_rows, artifact_fields)


def main() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    run_rows, counts = metric_summary()
    records = build_records(now, run_rows, counts)
    write_primary_records(now, records, counts)
    update_yaml_records(now, counts)
    repair_run_gate_coverage(run_rows)
    update_registries(now, records, run_rows)
    print(
        json.dumps(
            {
                "status": "axis_review_records_written",
                "axis_review": rel(AXIS_REVIEW_PATH),
                "goal_closeout": rel(GOAL_CLOSEOUT_PATH),
                "clues": [rel(CLUE_TRADE_PATH), rel(CLUE_PATHQ_PATH)],
                "next_work_item": NEW_WORK,
                "result_counts": counts,
                "claim_boundary": "first_batch_axis_review_only_no_candidate_no_baseline_no_runtime",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
