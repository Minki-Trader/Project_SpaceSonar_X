from __future__ import annotations

import csv
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]

NEW_WORK = "work_wave0_first_batch_l4_follow_through_v0"
OLD_WORK = "work_wave0_second_batch_tradeability_repair_spec_v0"
GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
L4_STATUS = "first_batch_axis_review_closed_l4_follow_through_required_next"
OLD_STATUS = "first_batch_axis_review_closed_second_batch_design_next"

GOAL_DIR = Path("lab/goals") / GOAL_ID
NEXT_WORK_PATH = GOAL_DIR / "next_work_item.yaml"
GOAL_MANIFEST_PATH = GOAL_DIR / "goal_manifest.yaml"
RESUME_CURSOR_PATH = GOAL_DIR / "resume_cursor.yaml"
TERMINAL_CONTRACT_PATH = GOAL_DIR / "terminal_eligibility_contract.yaml"
AMENDMENT_PATH = GOAL_DIR / "user_clarification_proxy_l4_policy_v0.yaml"
AXIS_CLOSEOUT_PATH = GOAL_DIR / "work_wave0_first_batch_axis_review_v0_closeout.yaml"
EXECUTE_CLOSEOUT_PATH = GOAL_DIR / "work_wave0_execute_first_batch_proxy_scout_v0_closeout.yaml"
WORKSPACE_PATH = Path("docs/workspace/workspace_state.yaml")

SWEEP_DIR = Path(
    "lab/campaigns/campaign_us100_task_surface_scout_v0/"
    "sweeps/sweep_wave0_broad_surface_scout_v0"
)
RUN_REFS_PATH = SWEEP_DIR / "run_refs.csv"
AXIS_REVIEW_PATH = SWEEP_DIR / "axis_review_wave0_first_batch_v0.yaml"
LEDGER_PATH = Path("lab/campaigns/campaign_us100_task_surface_scout_v0/anti_selection_ledger.yaml")
WAVE_PATH = Path("lab/waves/wave_us100_closedbar_surface_cartography_v0/wave_allocation.yaml")
CAMPAIGN_PATH = Path("lab/campaigns/campaign_us100_task_surface_scout_v0/campaign_manifest.yaml")
SWEEP_PATH = SWEEP_DIR / "sweep_manifest.yaml"
CLUE_TRADE_PATH = Path("lab/memory/clues/clue_wave0_tradeability_mid_horizon_v0.yaml")
CLUE_PATHQ_PATH = Path("lab/memory/clues/clue_wave0_path_quality_h12_side_signal_v0.yaml")
SURFACE_PATH = Path("lab/surfaces/surface_us100_task_input_decision_rotation_v0/surface_manifest.yaml")

CLAIM_BOUNDARY = "l4_follow_through_required_no_runtime_authority_no_candidate"
RUN_CLAIM_BOUNDARY = "first_batch_proxy_scout_l4_required_no_candidate_no_baseline_no_runtime_authority"
AXIS_CLAIM_BOUNDARY = "first_batch_axis_review_l4_required_no_candidate_no_baseline_no_runtime_authority"
RUNTIME_DECISION = {
    "required": True,
    "decision": "run_required",
    "reason": "User clarification: every valid proxy/model-bearing run must reach L4_split_runtime_probe.",
    "lowered_claim_if_not_run": "invalid_proxy_only_closeout_no_l4_runtime_evidence",
}
L4_MISSING = "L4_split_runtime_probe_required_pending_for_all_valid_proxy_runs"
OLD_NOT_APPLICABLE = "mt5_runtime_probe_not_applicable_no_runtime_claim"

PROXY_RUNTIME_PARITY = {
    "required_for_proxy_model_bearing_run": True,
    "status": "pending_L4_follow_through",
    "shared_contract": [
        "US100_M5_closed_bar_base_frame",
        "us100_bar_close_time_row_key",
        "split_set_v0_research_catalog",
        "declared_task_surface_per_run",
        "tester_execution_profile_us100_m5_fpmarkets_tester_execution_v0",
    ],
    "proxy_assumptions": [
        "train_validation_proxy_observation",
        "no_MT5_fill_spread_swap_slippage_or_execution_timing",
    ],
    "runtime_assumptions": [
        "split_base_anchor_v0_research_l4",
        "us100_m5_fpmarkets_tester_execution_v0",
        "MT5_Strategy_Tester_report_required",
    ],
    "known_differences": [
        "proxy_metrics_are_not_tester_reports",
        "proxy_decision_semantics_may_translate_differently_in_EA_MT5",
    ],
    "interpretation_drift_risks": [
        "bar_close_timing",
        "decision_threshold_translation",
        "no_trade_or_abstain_semantics",
        "lot_rounding_and_position_sizing",
        "spread_and_cost_model",
        "tester_execution_model",
    ],
    "minimum_reconciliation_attempt": {
        "required": True,
        "status": "pending_L4",
        "forced_equality_required": False,
        "attempts": [],
        "note": "Attempt repair, conversion, or interpretation check at least once; preserve true MT5 differences instead of forcing equality.",
    },
    "unit_semantics": {
        "point": "pending_L4",
        "pip": "pending_L4",
        "tick_size": "pending_L4",
        "digits": "pending_L4",
        "price_distance": "pending_L4",
        "atr_multiplier": "pending_when_ATR_stop_logic_exists",
        "lot_step": "pending_L4",
        "rounding_policy": "pending_L4",
    },
    "comparison_class": "pending_L4",
    "divergence_judgment": "pending_L4",
    "prevention_memory": [
        "record_unit_conversion_rule_before_reusing_ATR_or_stop_distance_logic",
        "record_MT5_interpretation_drift_before_reusing_proxy_decision_surface",
    ],
    "follow_up_action": NEW_WORK,
    "claim_boundary": "proxy_runtime_parity_tracking_only_no_runtime_authority",
}


TEXT_REPLACEMENTS = {
    OLD_WORK: NEW_WORK,
    OLD_STATUS: L4_STATUS,
    "work_wave0_first_batch_l4_follow_through_v0_closeout.yaml": "work_wave0_first_batch_axis_review_v0_closeout.yaml",
    "first_batch_proxy_scout_only_no_candidate_no_baseline_no_runtime": RUN_CLAIM_BOUNDARY,
    "first_batch_axis_review_only_no_candidate_no_baseline_no_runtime": AXIS_CLAIM_BOUNDARY,
    "preserved_clue_for_second_batch_design": "preserved_clue_for_l4_follow_through",
    "preserved_clue_for_second_batch_design": "preserved_clue_for_l4_follow_through",
    "rotate_plus_mix_tradeability_mid_horizon_second_batch_design_next": "first_batch_proxy_l4_follow_through_required_next",
    "first_batch_axis_review_points_to_tradeability_second_batch_design": "first_batch_axis_review_points_to_l4_follow_through",
    "open bounded second-batch design with h6/h12 tradeability controls, neighbor horizons, WFO-style checks, and predeclared threshold bands": (
        "drive source proxy runs through L4_split_runtime_probe; if L4 remains promising, continue to L5_candidate_runtime_evidence"
    ),
    "extend_in_second_batch_with_predeclared_controls_wfo_or_neighbor_surface": (
        "continue_to_L4_split_runtime_probe_then_L5_if_promising"
    ),
    "first_batch_axis_review_closed_preserved_clues_recorded_no_candidate": (
        "first_batch_axis_review_closed_l4_follow_through_required"
    ),
}


def rel(path: Path) -> str:
    return path.as_posix()


def read_yaml(path: Path) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def write_yaml(path: Path, data: dict) -> None:
    full = ROOT / path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=False, width=100),
        encoding="utf-8",
        newline="\n",
    )


def read_json(path: Path) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    (ROOT / path).write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")


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


def normalize_text(value: str) -> str:
    out = value
    for old, new in TEXT_REPLACEMENTS.items():
        out = out.replace(old, new)
    return out


def normalize_value(value):
    if isinstance(value, str):
        return normalize_text(value)
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_value(child) for key, child in value.items()}
    return value


def replace_missing_evidence(items: list[str] | None) -> list[str]:
    out: list[str] = []
    for item in items or []:
        if item == OLD_NOT_APPLICABLE:
            continue
        out.append(item)
    if L4_MISSING not in out:
        out.append(L4_MISSING)
    return out


def ensure_list_item(items: list[str], value: str) -> list[str]:
    if value not in items:
        items.append(value)
    return items


def update_gate_coverage(data: dict) -> None:
    routing = data.get("skill_routing")
    if isinstance(routing, dict):
        required = list(routing.get("required_gates") or [])
        ensure_list_item(required, "onnx_export_or_runtime_materialization_required")
        ensure_list_item(required, "L4_split_runtime_probe_for_valid_proxy_run")
        routing["required_gates"] = required

        not_applicable = [
            item
            for item in routing.get("not_applicable_gates") or []
            if item not in {"onnx_export", "mt5_strategy_tester"}
        ]
        routing["not_applicable_gates"] = not_applicable

    coverage = data.get("required_gate_coverage")
    if isinstance(coverage, dict):
        not_applicable = [
            item
            for item in coverage.get("not_applicable") or []
            if item not in {"onnx_export", "mt5_strategy_tester"}
        ]
        missing = list(coverage.get("missing") or [])
        ensure_list_item(missing, "onnx_export_or_runtime_materialization_required")
        ensure_list_item(missing, "L4_split_runtime_probe_for_valid_proxy_run")
        coverage["not_applicable"] = not_applicable
        coverage["missing"] = missing


def update_runtime_decision(data: dict) -> None:
    data["runtime_learning_probe_decision"] = dict(RUNTIME_DECISION)
    data["proxy_runtime_parity"] = dict(PROXY_RUNTIME_PARITY)
    data["missing_evidence"] = replace_missing_evidence(data.get("missing_evidence"))
    data["claim_boundary"] = RUN_CLAIM_BOUNDARY
    if "claim_scope" in data:
        data["claim_scope"] = data["claim_boundary"]
    update_gate_coverage(data)


def run_ids() -> list[str]:
    rows, _ = read_csv(RUN_REFS_PATH)
    return [row["run_id"] for row in rows]


def update_run_records() -> None:
    for run_id in run_ids():
        base = Path("lab/runs") / run_id
        manifest = read_json(base / "run_manifest.json")
        update_runtime_decision(manifest)
        manifest.setdefault("runtime_follow_through_policy", {})["l4_required"] = True
        manifest["runtime_follow_through_policy"]["l5_if_l4_promising"] = True
        manifest["next_action"] = NEW_WORK
        write_json(base / "run_manifest.json", manifest)

        metrics = read_json(base / "metrics.json")
        update_runtime_decision(metrics)
        metrics["measurement_scope"] = metrics.get("measurement_scope", "").replace(
            "no_oos_b_no_runtime", "no_oos_b_l4_required_no_runtime_authority"
        )
        write_json(base / "metrics.json", metrics)

        receipt = read_yaml(base / "experiment_receipt.yaml")
        update_runtime_decision(receipt)
        receipt.setdefault("runtime_follow_through_policy", {})["l4_required"] = True
        receipt["runtime_follow_through_policy"]["l5_if_l4_promising"] = True
        receipt["next_action"] = NEW_WORK
        write_yaml(base / "experiment_receipt.yaml", receipt)

        report_path = base / "reports" / "proxy_scout_report.json"
        if (ROOT / report_path).exists():
            report = normalize_value(read_json(report_path))
            report["claim_boundary"] = RUN_CLAIM_BOUNDARY
            report["runtime_follow_through_policy"] = {
                "l4_required": True,
                "l5_if_l4_promising": True,
                "missing_evidence": L4_MISSING,
            }
            write_json(report_path, report)

        update_lineage(base / "artifact_lineage.json")


def update_lineage(path: Path) -> None:
    lineage = read_json(path)
    lineage["consumer"] = [NEW_WORK]
    lineage["lineage_judgment"] = "usable_proxy_evidence_with_l4_follow_through_required"
    artifact_hashes: list[str] = []
    artifact_sizes: list[int] = []
    for item in lineage.get("artifact_paths", []):
        if not isinstance(item, dict) or not item.get("path"):
            continue
        artifact_path = Path(item["path"])
        full = ROOT / artifact_path
        if full.exists():
            item["sha256"] = sha256(artifact_path)
            item["size_bytes"] = full.stat().st_size
        if item.get("sha256"):
            artifact_hashes.append(item["sha256"])
        if item.get("size_bytes") is not None:
            artifact_sizes.append(int(item["size_bytes"]))
    lineage["artifact_hashes"] = artifact_hashes
    lineage["artifact_sizes"] = artifact_sizes
    if "docs/registers/run_registry.csv" not in lineage.get("registry_links", []):
        lineage.setdefault("registry_links", []).append("docs/registers/run_registry.csv")
    write_json(path, lineage)


def update_yaml_state(now: str) -> None:
    amendment = {
        "version": "goal_policy_clarification_v1",
        "active_goal_id": GOAL_ID,
        "created_at_utc": now,
        "status": "accepted_user_clarification",
        "clarification": "All valid proxy/model-bearing runs must reach L4_split_runtime_probe; if L4 remains promising continue to L5_candidate_runtime_evidence.",
        "claim_effect": "proxy_only_closeout_for_valid_proxy_runs_is_forbidden",
        "not_a_new_runtime_authority_claim": True,
        "affected_next_work_item": NEW_WORK,
    }
    write_yaml(AMENDMENT_PATH, amendment)

    next_work = {
        "version": "onnx_lab_work_item_v1",
        "work_item_id": NEW_WORK,
        "active_goal_id": GOAL_ID,
        "created_at_utc": now,
        "status": "planned_next",
        "user_request": "Materialize and execute L4 MT5 split-runtime follow-through for every valid Wave0 first-batch proxy/model-bearing run.",
        "current_truth": {
            "axis_review": rel(AXIS_REVIEW_PATH),
            "policy_clarification": rel(AMENDMENT_PATH),
            "source_run_refs": rel(RUN_REFS_PATH),
            "proxy_run_count": len(run_ids()),
            "required_runtime_level": "L4_split_runtime_probe",
            "l5_rule": "if_L4_remains_promising_continue_to_L5_candidate_runtime_evidence",
            "candidate_count": 0,
        },
        "work_classification": {
            "primary_family": "runtime_probe",
            "detected_families": ["onnx_export_parity", "bundle_materialization", "runtime_probe", "model_training"],
            "mutation_intent": "materialize_runtime_follow_through_for_existing_proxy_runs",
            "execution_intent": "all_valid_proxy_runs_to_L4_then_L5_if_promising",
        },
        "skill_routing": {
            "primary_family": "runtime_probe",
            "primary_skill": "spacesonar-runtime-parity",
            "support_skills": [
                "spacesonar-artifact-lineage",
                "spacesonar-environment-reproducibility",
                "spacesonar-run-evidence-system",
                "spacesonar-model-validation",
                "spacesonar-claim-discipline",
            ],
            "skills_selected": [
                "spacesonar-runtime-parity",
                "spacesonar-artifact-lineage",
                "spacesonar-environment-reproducibility",
                "spacesonar-run-evidence-system",
                "spacesonar-model-validation",
                "spacesonar-claim-discipline",
            ],
            "skills_not_used": [],
            "critical_skills_not_selected": [],
            "not_selected_claim_effect": "none",
            "required_gates": [
                "onnx_export_or_runtime_materialization_plan",
                "bundle_integrity_hash",
                "python_onnx_parity_where_model_exported",
                "mt5_runtime_probe_contract_audit",
                "proxy_runtime_parity_record",
                "L4_split_runtime_probe_for_all_valid_proxy_runs",
                "result_judgment",
                "final_claim_guard",
            ],
        },
        "acceptance_criteria": [
            "For each of the 12 Wave0 first-batch proxy runs, either produce L4 MT5 split-runtime evidence or record a repair/invalid reason before it can count as proxy evidence.",
            "For each L4 follow-through attempt, record proxy_runtime_parity with shared contract, known differences, interpretation drift risks, comparison class, divergence judgment, and follow-up action.",
            "Make at least one explicit reconciliation attempt for any proxy-vs-MT5 mismatch; then record whether the result was repaired, accepted as an expected difference, or preserved as a surprise clue.",
            "Record unit semantics when relevant, including point, pip, tick size, digits, price distance, ATR stop conversion, lot step, and rounding policy.",
            "Use runtime_period_set_id split_base_anchor_v0_research_l4 with validation and research_oos roles.",
            "Keep OOS-B locked unless a later frozen candidate explicitly unlocks it.",
            "Do not stop at proxy-only closeout for any valid proxy/model-bearing run.",
            "If an L4 result remains promising, write the next work item toward L5_candidate_runtime_evidence.",
            "Do not claim runtime authority, economics pass, selected baseline, live readiness, or Goal Achieve.",
        ],
        "runtime_learning_probe_decision": dict(RUNTIME_DECISION),
        "proxy_runtime_parity": {
            "required_for_all_campaign_proxy_runs": True,
            "shared_contract_required": True,
            "known_differences_required": True,
            "interpretation_drift_risks_required": True,
            "minimum_reconciliation_attempt_required": True,
            "forced_equality_required": False,
            "unit_semantics_required_when_applicable": True,
            "comparison_classes": [
                "proxy_good_runtime_good",
                "proxy_good_runtime_bad",
                "proxy_bad_runtime_bad",
                "proxy_bad_runtime_good",
                "invalid_or_unmaterializable",
            ],
            "divergence_judgment_required": True,
            "prevention_memory_required": True,
            "example_unit_drift": "atr_SL_TP_point_vs_MT5_point_tick_digits_price_distance",
            "proxy_bad_runtime_good_effect": "preserve_as_clue_or_open_new_hypothesis_surface",
            "proxy_good_runtime_bad_effect": "treat_as_interpretation_or_execution_drift_until_explained",
            "proxy_bad_runtime_bad_effect": "record_negative_evidence_with_boundary",
            "claim_boundary": "campaign_parity_tracking_only_no_runtime_authority",
        },
        "runtime_period_profile": "period_profile_split_set_v0",
        "runtime_period_set_id": "split_base_anchor_v0_research_l4",
        "tester_execution_profile_id": "us100_m5_fpmarkets_tester_execution_v0",
        "bounded_execution_budget": {
            "proxy_runs_requiring_l4": len(run_ids()),
            "runtime_attempts": "one_or_more_attempts_per_valid_proxy_run_until_L4_or_repair_record",
            "locked_final_oos_use": "forbidden",
        },
        "stop_conditions": [
            "proxy_run_cannot_be_materialized_to_ONNX_EA_MT5_without_repair",
            "MT5_terminal_or_tester_environment_blocked_after_repair_attempts",
            "feature_order_or_decision_surface_mismatch",
            "runtime_period_profile_missing",
        ],
        "claim_boundary": CLAIM_BOUNDARY,
        "branch_worktree": {
            "current_branch": "codex/active-goal-program-bootstrap",
            "requested_branch": "codex/active-goal-program-bootstrap",
            "branch_worktree_fit": "fit",
            "branch_action": "keep_current_branch",
            "policy_reference": "docs/policies/branch_policy.md",
            "mismatch_claim_effect": "block_l4_follow_through_until_resolved",
        },
        "agent_allocation": {
            "phase": "wave0_first_batch_l4_follow_through",
            "selected_agents": [],
            "role_modes": [],
            "selection_reason": "User clarified execution policy; Codex applies record correction before runtime execution.",
            "why_not_smaller": "Codex alone is the smallest allocation for deterministic policy-record sync.",
            "why_not_larger": "Task Force/sub-agent allocation is disabled; runtime execution uses Codex, skills, validators, and source-of-truth records.",
            "max_threads_is_capacity_only": True,
            "claim_effect": "no_new_advisory_claim",
        },
        "execution_provenance": {
            "git_sha": "unknown_dirty_worktree_policy_sync",
            "branch": "codex/active-goal-program-bootstrap",
            "dirty_flag": "dirty",
            "changed_files": ["policy_and_record_sync_by_apply_proxy_l4_policy_clarification"],
            "command_argv": ["python", "foundation/pipelines/apply_proxy_l4_policy_clarification.py"],
            "python_executable": sys.executable.replace(str(Path.home()), "${USERPROFILE}"),
            "python_version": platform.python_version(),
            "key_package_versions": {
                "python": platform.python_version(),
                "yaml": getattr(yaml, "__version__", "unknown"),
            },
            "started_at_utc": now,
            "ended_at_utc": now,
            "input_hashes": [
                {"path": rel(RUN_REFS_PATH), "sha256": sha256(RUN_REFS_PATH)},
                {"path": rel(AXIS_REVIEW_PATH), "sha256": sha256(AXIS_REVIEW_PATH)},
            ],
            "output_hashes": [],
            "unknown_git_claim_effect": "planning_scaffold_only_no_reproducible_bundle_runtime_handoff_pass_readiness_or_goal_achieve",
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
    write_yaml(NEXT_WORK_PATH, next_work)

    for path in [
        GOAL_MANIFEST_PATH,
        RESUME_CURSOR_PATH,
        WORKSPACE_PATH,
        AXIS_CLOSEOUT_PATH,
        EXECUTE_CLOSEOUT_PATH,
        AXIS_REVIEW_PATH,
        LEDGER_PATH,
        WAVE_PATH,
        CAMPAIGN_PATH,
        SWEEP_PATH,
        SURFACE_PATH,
        CLUE_TRADE_PATH,
        CLUE_PATHQ_PATH,
    ]:
        if not (ROOT / path).exists():
            continue
        data = normalize_value(read_yaml(path))
        if path == GOAL_MANIFEST_PATH:
            data["updated_at_utc"] = now
            data["active_phase"] = "wave0_first_batch_l4_follow_through_next"
            data.setdefault("program_budgets", {}).setdefault("current_wave0_spec", {})[
                "proxy_to_runtime_policy"
            ] = "all_valid_proxy_runs_require_L4_split_runtime_probe"
            data["program_budgets"]["current_wave0_spec"]["status"] = "l4_follow_through_required_next"
            data["next_work_item"] = {
                "path": rel(NEXT_WORK_PATH),
                "work_item_id": NEW_WORK,
                "summary": "Drive every valid Wave0 first-batch proxy/model-bearing run to L4 MT5 split-runtime evidence.",
            }
        elif path == RESUME_CURSOR_PATH:
            data["updated_at_utc"] = now
            data["active_phase"] = "wave0_first_batch_l4_follow_through_next"
            data["next_work_item"] = {"work_item_id": NEW_WORK, "path": rel(NEXT_WORK_PATH)}
            data.setdefault("current_truth_sources", [])
            for source in [rel(AMENDMENT_PATH), rel(NEXT_WORK_PATH)]:
                if source not in data["current_truth_sources"]:
                    data["current_truth_sources"].append(source)
        elif path == WORKSPACE_PATH:
            data["updated_utc"] = now
            claims = data.setdefault("current_claims", {})
            claims["active_goal_phase"] = "wave0_first_batch_l4_follow_through_next"
            claims["next_work_item_id"] = NEW_WORK
            claims["active_goal_next_work_item"] = rel(NEXT_WORK_PATH)
            claims["proxy_to_runtime_policy"] = "all_valid_proxy_runs_require_L4_split_runtime_probe"
            claims["l4_to_l5_policy"] = "if_L4_remains_promising_continue_to_L5_candidate_runtime_evidence"
            claims["proxy_only_closeout_allowed"] = False
            claims["wave0_first_batch_status"] = "l4_follow_through_required_next"
        else:
            data = normalize_value(data)
            data["next_action"] = NEW_WORK
            if path == AXIS_REVIEW_PATH:
                data["next_work_item_id"] = NEW_WORK
            data["proxy_to_runtime_policy"] = {
                "every_valid_proxy_run_requires_l4": True,
                "proxy_only_closeout_allowed": False,
                "l4_promising_result_effect": "continue_to_L5_candidate_runtime_evidence",
            }
        write_yaml(path, data)


def update_registries() -> None:
    for path in [
        Path("docs/registers/goal_registry.csv"),
        Path("docs/registers/wave_registry.csv"),
        Path("docs/registers/campaign_registry.csv"),
        Path("docs/registers/sweep_registry.csv"),
        Path("docs/registers/experiment_surface_registry.csv"),
        Path("docs/registers/hypothesis_registry.csv"),
        Path("docs/registers/idea_registry.csv"),
        Path("docs/registers/clue_registry.csv"),
        Path("docs/registers/run_registry.csv"),
        Path("docs/registers/recipe_index.csv"),
    ]:
        rows, fields = read_csv(path)
        if "next_action" in fields:
            next_field = "next_action"
        elif "next_work_item" in fields:
            next_field = "next_work_item"
        else:
            next_field = None
        for row in rows:
            for key, value in list(row.items()):
                row[key] = normalize_text(value or "")
            if next_field and row.get(next_field) in {OLD_WORK, "work_wave0_second_batch_tradeability_repair_spec_v0", "work_wave0_first_batch_axis_review_v0"}:
                row[next_field] = NEW_WORK
            if "status" in row and "wave0" in row.get(next_field or "", NEW_WORK):
                row["status"] = row["status"].replace("second_batch_design_next", "l4_follow_through_required_next")
            if "notes" in row and row.get(next_field) == NEW_WORK:
                row["notes"] = "proxy_to_l4_policy_clarified_all_valid_proxy_runs_require_l4"
            if path.name == "run_registry.csv" and row.get("run_id", "").startswith("onnxlab_wave0_cell_"):
                row["claim_boundary"] = RUN_CLAIM_BOUNDARY
                gates = [item for item in row.get("required_gates", "").split("|") if item]
                gates = [
                    item
                    for item in gates
                    if item not in {"not_applicable:onnx_export", "not_applicable:mt5_strategy_tester"}
                ]
                ensure_list_item(gates, "missing:onnx_export_or_runtime_materialization_required")
                ensure_list_item(gates, "missing:L4_split_runtime_probe_for_valid_proxy_run")
                row["required_gates"] = "|".join(gates)
        write_csv(path, rows, fields)

    rows, fields = read_csv(RUN_REFS_PATH)
    for row in rows:
        for key, value in list(row.items()):
            row[key] = normalize_text(value or "")
        row["claim_boundary"] = RUN_CLAIM_BOUNDARY
        row["notes"] = "valid_proxy_run_requires_L4_split_runtime_probe_follow_through"
    write_csv(RUN_REFS_PATH, rows, fields)


def sha256(path: Path) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def update_artifact_hashes() -> None:
    path = Path("docs/registers/artifact_registry.csv")
    rows, fields = read_csv(path)
    artifact_ids = {row.get("artifact_id") for row in rows}
    for row in rows:
        for key, value in list(row.items()):
            row[key] = normalize_text(value or "")
        rel_path = row.get("path_or_uri", "")
        if row.get("consumer") in {OLD_WORK, "work_wave0_second_batch_tradeability_repair_spec_v0"}:
            row["consumer"] = NEW_WORK
        if "second_batch" in row.get("notes", "") or row.get("consumer") == NEW_WORK:
            row["notes"] = "proxy_to_l4_policy_clarified_all_valid_proxy_runs_require_l4"
        if rel_path and "://" not in rel_path and (ROOT / rel_path).exists() and row.get("availability") == "present_hash_recorded":
            file_path = Path(rel_path)
            row["sha256"] = sha256(file_path)
            row["size_bytes"] = str((ROOT / file_path).stat().st_size)
    if "artifact_proxy_l4_policy_clarification_v0" not in artifact_ids:
        rows.append(
            {
                "artifact_id": "artifact_proxy_l4_policy_clarification_v0",
                "run_id": "",
                "bundle_id": "",
                "attempt_id": "",
                "artifact_type": "goal_policy_clarification",
                "path_or_uri": rel(AMENDMENT_PATH),
                "sha256": sha256(AMENDMENT_PATH),
                "size_bytes": str((ROOT / AMENDMENT_PATH).stat().st_size),
                "availability": "present_hash_recorded",
                "producer_command": "foundation/pipelines/apply_proxy_l4_policy_clarification.py",
                "regeneration_command": "python foundation/pipelines/apply_proxy_l4_policy_clarification.py",
                "source_of_truth": rel(AMENDMENT_PATH),
                "consumer": NEW_WORK,
                "claim_boundary": CLAIM_BOUNDARY,
                "notes": "user clarified all valid proxy runs require L4 and L5 if promising",
            }
        )
    write_csv(path, rows, fields)


def main(*_args: object, **_kwargs: object) -> int:
    from foundation.pipelines.historical_lifecycle_guard import disabled_lifecycle_entrypoint

    return disabled_lifecycle_entrypoint(
        "a run-local/domain evidence command plus locked spacesonar lifecycle transaction for canonical state updates"
    )


if __name__ == "__main__":
    main()
