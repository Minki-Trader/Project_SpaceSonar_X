from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation.features.wave01_session_transition_features import build_wave01_session_transition_features  # noqa: E402
from foundation.labels.wave01_session_transition_labels import build_wave01_session_transition_labels  # noqa: E402
from foundation.pipelines.run_wave01_event_barrier_proxy_batch import (  # noqa: E402
    artifact_ref,
    branch_worktree,
    durable_arg,
    failure_disposition_not_applicable,
    git_status_lines,
    git_value,
    load_row_membership,
    provenance,
    read_csv_rows,
    repo_relative,
    split_masks,
    update_registry_row,
    usable_feature_columns,
    write_csv,
    write_json,
    write_prediction_sample,
    write_yaml,
)
from foundation.training.wave01_event_barrier_models import (  # noqa: E402
    build_model_target,
    decision_metrics,
    diagnostic_metrics,
    fit_proxy_model,
    judge_proxy_result,
    score_model,
)
from foundation.validation.refresh_artifact_registry_hashes import refresh_registry  # noqa: E402


UTC = timezone.utc
WORK_ITEM_ID = "work_wave01_session_transition_execute_first_batch_proxy_v0"
NEXT_WORK_ITEM_ID = "work_wave01_session_transition_l4_materialization_preflight_v0"
CLAIM_BOUNDARY = "wave01_session_transition_proxy_batch_l4_required_no_candidate_no_baseline_no_runtime_authority"
CAMPAIGN_ID = "campaign_us100_session_transition_regime_surface_v0"
SURFACE_ID = "surface_us100_session_transition_regime_surface_v0"
SWEEP_ID = "sweep_us100_session_transition_broad_v0"
WAVE_ID = "wave_us100_closedbar_surface_cartography_v0"
IDEA_ID = "idea_us100_m5_session_transition_regime_surface_v0"
HYPOTHESIS_ID = "hyp_us100_session_transition_regime_surface_v0"

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
REQUIRED_GATES = [
    "branch_worktree_fit",
    "time_axis_check",
    "feature_label_boundary_check",
    "split_boundary_check",
    "selection_bias_check",
    "run_manifest",
    "experiment_receipt",
    "storage_contract_check",
    "runtime_learning_probe_decision",
    "proxy_runtime_parity_decision",
    "final_claim_guard",
    "L4_split_runtime_probe_for_valid_proxy_run",
]
INPUT_REFS = [
    "lab/campaigns/campaign_us100_session_transition_regime_surface_v0/first_batch_matrix.csv",
    "lab/campaigns/campaign_us100_task_surface_scout_v0/row_membership/row_membership_manifest.yaml",
    "configs/onnx_lab/feature_recipes/feature_wave01_us100_session_transition_regime_v0.yaml",
    "configs/onnx_lab/label_recipes/label_wave01_session_transition_regime_v0.yaml",
    "configs/onnx_lab/model_recipes/model_wave01_session_transition_onnx_scout_v0.yaml",
    "configs/onnx_lab/decision_recipes/decision_wave01_session_transition_abstain_v0.yaml",
    "configs/onnx_lab/eval_recipes/eval_wave01_session_transition_runtime_v0.yaml",
    "foundation/config/mt5_runtime_probe_contract.yaml",
    "configs/mt5/period_profiles/split_set_v0_runtime_periods.yaml",
    "configs/mt5/tester_execution_profile_v0.yaml",
]


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def iso_z(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a YAML mapping")
    return payload


def read_matrix(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return {row["spec_id"]: row for row in csv.DictReader(handle)}


def routing() -> dict[str, Any]:
    skills = [
        "spacesonar-model-validation",
        "spacesonar-experiment-design",
        "spacesonar-data-integrity",
        "spacesonar-run-evidence-system",
        "spacesonar-runtime-parity",
        "spacesonar-claim-discipline",
    ]
    return {
        "primary_family": "model_training",
        "primary_skill": "spacesonar-model-validation",
        "support_skills": skills[1:],
        "skills_selected": skills,
        "skills_not_used": [],
        "critical_skills_not_selected": [],
        "not_selected_claim_effect": "all critical execution/evidence skills selected",
        "required_gates": REQUIRED_GATES,
    }


def runtime_decision() -> dict[str, Any]:
    return {
        "required": True,
        "decision": "run_required",
        "target_level": "L4_split_runtime_probe",
        "runtime_period_profile_id": "period_profile_split_set_v0",
        "runtime_period_set_id": "split_base_anchor_v0_research_l4",
        "tester_execution_profile_id": "us100_m5_fpmarkets_tester_execution_v0",
        "required_period_roles": ["validation", "research_oos"],
        "lowered_claim_if_not_run": "proxy_observation_only_no_runtime_authority_no_economics_pass_no_candidate",
    }


def parity(row: dict[str, str]) -> dict[str, Any]:
    return {
        "shared_contract": "US100_M5_closed_bar_row_membership_feature_order_label_surface_score_output",
        "known_differences": [
            "proxy is vectorized closed-bar research; MT5 must implement session boundary, timeout, abstain, and lot semantics",
            "proxy metrics have no spread/fill/slippage/swap/execution timing claim",
        ],
        "interpretation_drift_risks": [
            row["risk_policy"],
            "America/New_York session derivation vs MT5 tester execution clock",
            "score threshold and timeout conversion in EA adapter",
        ],
        "minimum_reconciliation_attempt": {
            "required": True,
            "status": "pending_L4_materialization",
            "forced_equality_required": False,
        },
        "unit_semantics": "price_distance_timeout_bar_count_session_boundary_and_lot_semantics_declared_before_L4",
        "comparison_class": "pending_L4",
        "divergence_judgment": "pending_L4",
        "prevention_memory": [
            "Record MT5 session/timeout/unit drift as prevention memory instead of forcing equality.",
        ],
        "follow_up_action": NEXT_WORK_ITEM_ID,
        "claim_boundary": "proxy_runtime_parity_tracking_only_no_runtime_authority",
    }


def normalize_decision_family(decision_family: str) -> str:
    if "diagnostic" in decision_family or "no_trade" in decision_family:
        return "diagnostic_path_quality_no_trade"
    return decision_family


def row_label_contract(row: dict[str, str]) -> dict[str, Any]:
    return {
        "label_surface": row["label_surface"],
        "horizon_bars": int(row["horizon_bars"]),
        "session_anchor": row["session_anchor"],
        "transition_window_bars": row["transition_window_bars"],
        "regime_label": row["regime_label"],
        "direction_mapping": "declared_by_label_surface_no_legacy_mapping",
    }


def row_id_chain() -> dict[str, str]:
    return {
        "goal_id": "goal_us100_onnx_forward_boundary_v0",
        "wave_id": WAVE_ID,
        "campaign_id": CAMPAIGN_ID,
        "idea_id": IDEA_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
    }


def run_one(
    row: dict[str, str],
    run_ref: dict[str, str],
    frame: pd.DataFrame,
    row_manifest_path: Path,
    command_argv: list[str],
    branch: dict[str, str],
    batch_git_state: dict[str, Any],
) -> dict[str, str]:
    run_id = run_ref["run_id"]
    root = REPO_ROOT / "lab" / "runs" / run_id
    artifacts = root / "artifacts"
    reports = root / "reports"
    started = utc_now()

    features, feature_schema = build_wave01_session_transition_features(frame, row["feature_family"])
    labels, label_schema = build_wave01_session_transition_labels(frame, row_label_contract(row))
    masks = split_masks(frame, labels)
    train_mask = masks["train"]
    validation_mask = masks["validation"]
    research_mask = masks["research_oos_a"]
    target, task_kind, target_name, target_threshold = build_model_target(
        labels,
        train_mask,
        label_surface=row["label_surface"],
        model_family=row["model_family"],
        model_task=row["model_task"],
    )
    target_ok = target.notna()
    train_mask &= target_ok
    validation_mask &= target_ok
    research_mask &= target_ok
    if int(train_mask.sum()) < 1000 or int(validation_mask.sum()) < 300 or int(research_mask.sum()) < 300:
        raise ValueError(
            f"insufficient split rows train={int(train_mask.sum())} validation={int(validation_mask.sum())} research_oos={int(research_mask.sum())}"
        )

    columns = usable_feature_columns(features, train_mask)
    x = features[columns]
    fit = fit_proxy_model(
        x,
        target,
        train_mask,
        model_family=row["model_family"],
        task_kind=task_kind,
        target_name=target_name,
        threshold_policy=row["threshold_policy"],
        target_threshold=target_threshold,
    )
    scores = {
        "train": score_model(fit.model, x.loc[train_mask], task_kind),
        "validation": score_model(fit.model, x.loc[validation_mask], task_kind),
        "research_oos_a": score_model(fit.model, x.loc[research_mask], task_kind),
    }
    model_metrics = {
        "train": diagnostic_metrics(target.loc[train_mask], scores["train"], task_kind),
        "validation": diagnostic_metrics(target.loc[validation_mask], scores["validation"], task_kind),
        "research_oos_a": diagnostic_metrics(target.loc[research_mask], scores["research_oos_a"], task_kind),
    }
    decision_family = normalize_decision_family(row["decision_family"])
    decision = {
        "validation": decision_metrics(decision_family=decision_family, score=scores["validation"], labels=labels.loc[validation_mask], fit=fit),
        "research_oos_a": decision_metrics(decision_family=decision_family, score=scores["research_oos_a"], labels=labels.loc[research_mask], fit=fit),
    }
    for value in decision.values():
        value["declared_decision_family"] = row["decision_family"]
    judgment, reasons = judge_proxy_result(
        model_metrics["validation"],
        model_metrics["research_oos_a"],
        decision["validation"],
        decision["research_oos_a"],
        task_kind,
    )

    split_profile = {
        "raw_rows": int(len(frame)),
        "same_role_session_horizon_rows": int(labels["same_role_horizon_ok"].sum()),
        "train_label_eligible_rows": int(train_mask.sum()),
        "validation_label_eligible_rows": int(validation_mask.sum()),
        "research_oos_a_label_eligible_rows": int(research_mask.sum()),
        "locked_final_oos_b_withheld_rows": int(masks["locked_final_oos_b_withheld"].sum()),
        "locked_final_oos_b_use": "withheld_not_used",
    }
    feature_schema_path = artifacts / "feature_schema.json"
    label_schema_path = artifacts / "label_schema.json"
    model_summary_path = artifacts / "model_summary.json"
    split_profile_path = artifacts / "split_profile.json"
    validation_sample_path = artifacts / "prediction_sample_validation.csv"
    research_sample_path = artifacts / "prediction_sample_research_oos_a.csv"
    report_path = reports / "proxy_session_transition_report.json"
    outputs = [feature_schema_path, label_schema_path, model_summary_path, split_profile_path, validation_sample_path, research_sample_path, report_path]

    write_json(feature_schema_path, {**feature_schema.__dict__, "used_feature_columns": columns, "used_feature_count": len(columns), "claim_boundary": "feature_schema_only_not_fixed_feature_set"})
    write_json(label_schema_path, {**label_schema.__dict__, "label_contract": row_label_contract(row), "target_name_used_for_model": target_name, "target_threshold": target_threshold})
    write_json(model_summary_path, {"run_id": run_id, "model_family": row["model_family"], "model_task": row["model_task"], "task_kind": task_kind, "model_summary": fit.model_summary, "train_score_summary": fit.train_score_summary})
    write_json(split_profile_path, split_profile)
    write_prediction_sample(validation_sample_path, frame.loc[validation_mask], labels.loc[validation_mask], pd.Series(scores["validation"], index=labels.loc[validation_mask].index))
    write_prediction_sample(research_sample_path, frame.loc[research_mask], labels.loc[research_mask], pd.Series(scores["research_oos_a"], index=labels.loc[research_mask].index))

    report = {
        "version": "wave01_session_transition_proxy_report_v1",
        "run_id": run_id,
        "run_spec_id": row["spec_id"],
        "spec_source": "first_batch_matrix_row",
        "axis_values": row,
        "target_and_label": {**row_label_contract(row), "target_name": target_name, "target_threshold": target_threshold},
        "split_method": "split_set_v0_train_validation_research_oos_a_locked_final_oos_b_withheld",
        "selection_metric": "none_selected_first_batch_proxy_observation",
        "model_metrics": model_metrics,
        "decision_metrics": decision,
        "judgment_reasons": reasons,
        "validation_judgment": judgment,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    write_json(report_path, report)

    output_refs = [artifact_ref(path) for path in outputs]
    prov = provenance(command_argv, [REPO_ROOT / item for item in INPUT_REFS], outputs, started)
    prov.update(batch_git_state)
    prov["git_state_capture_policy"] = "batch_start_before_generated_outputs"
    coverage = {
        "passed": REQUIRED_GATES[:-1],
        "missing": ["L4_split_runtime_probe_for_valid_proxy_run"],
        "not_applicable": ["locked_final_oos_access"],
    }
    missing_evidence = ["ONNX_export_not_materialized_for_L4_yet", "MT5_L4_split_runtime_probe_not_run_yet", "candidate_selection_forbidden_before_L4"]
    storage = {
        "source_of_truth": f"lab/runs/{run_id}/run_manifest.json",
        "receipt_path": f"lab/runs/{run_id}/experiment_receipt.yaml",
        "lineage_path": f"lab/runs/{run_id}/artifact_lineage.json",
        "metrics_path": f"lab/runs/{run_id}/metrics.json",
        "registry_rows": ["docs/registers/run_registry.csv"],
    }
    base_record = {
        "run_id": run_id,
        "id_chain": {**row_id_chain(), "artifact_ids": [], "bundle_id": None, "candidate_id": None},
        "skill_routing": routing(),
        "branch_worktree": branch,
        "provenance": prov,
        "storage_contract": storage,
        "runtime_learning_probe_decision": runtime_decision(),
        "proxy_runtime_parity": parity(row),
        "failure_disposition": failure_disposition_not_applicable(),
        "required_gate_coverage": coverage,
        "result_judgment": judgment,
        "missing_evidence": missing_evidence,
        "claim_boundary": CLAIM_BOUNDARY,
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "next_action": NEXT_WORK_ITEM_ID,
    }
    manifest = {
        "version": "run_manifest_v2",
        **base_record,
        "trigger_source": WORK_ITEM_ID,
        "status": "executed_proxy_observation_l4_required",
        "created_at_utc": iso_z(utc_now()),
        "entrypoint": "foundation/pipelines/run_wave01_session_transition_proxy_batch.py",
        "command": " ".join(durable_arg(arg) for arg in command_argv),
        "task_surface": {
            "task_type": row["model_task"],
            "target_or_label": row["label_surface"],
            "horizon_or_holding_policy": row["holding_policy"],
            "output_head": "classification_score_or_regression_rank_declared_by_fit",
        },
    }
    receipt = {
        "version": "experiment_receipt_v2",
        **base_record,
        "hypothesis": "Session-transition state may expose reusable US100 M5 target/feature/model/decision interactions.",
        "decision_use": row["decision_family"],
        "sample_scope": split_profile,
        "evidence_plan": list(storage.values()),
    }
    metrics = {
        "version": "metrics_v2",
        "run_id": run_id,
        "status": "executed_proxy_observation_l4_required",
        "sample_counts": split_profile,
        "model_metrics": model_metrics,
        "trading_proxy_metrics": decision,
        "runtime_metrics": {},
        "judgment_label": judgment,
        "claim_boundary": CLAIM_BOUNDARY,
        "missing_evidence": missing_evidence,
    }
    lineage = {
        "version": "artifact_lineage_v2",
        "run_id": run_id,
        "source_inputs": [artifact_ref(REPO_ROOT / item) for item in INPUT_REFS if (REPO_ROOT / item).exists()],
        "producer": {"type": "script", "identity": "foundation/pipelines/run_wave01_session_transition_proxy_batch.py", "command": " ".join(durable_arg(arg) for arg in command_argv)},
        "source_of_truth_paths": [storage["source_of_truth"]],
        "artifact_paths": output_refs,
        "artifact_hashes": [{item["path"]: item["sha256"]} for item in output_refs],
        "availability": "present_hash_recorded",
        "lineage_judgment": "usable_proxy_observation_lineage_L4_missing",
    }
    write_json(root / "run_manifest.json", manifest)
    write_yaml(root / "experiment_receipt.yaml", receipt)
    write_json(root / "metrics.json", metrics)
    write_json(root / "artifact_lineage.json", lineage)
    return {
        "run_id": run_id,
        "run_spec_id": row["spec_id"],
        "status": "executed_proxy_observation_l4_required",
        "run_manifest_path": repo_relative(root / "run_manifest.json"),
        "receipt_path": repo_relative(root / "experiment_receipt.yaml"),
        "lineage_path": repo_relative(root / "artifact_lineage.json"),
        "metrics_path": repo_relative(root / "metrics.json"),
        "claim_boundary": CLAIM_BOUNDARY,
        "result_judgment": judgment,
        "next_action": NEXT_WORK_ITEM_ID,
        "notes": ";".join(reasons),
    }


def update_refs(path: Path, results: list[dict[str, str]]) -> None:
    by_spec = {item["run_spec_id"]: item for item in results}
    rows = []
    for row in read_csv_rows(path):
        key = "run_spec_id" if "run_spec_id" in row else "spec_id"
        if row[key] in by_spec:
            row.update(by_spec[row[key]])
        rows.append(row)
    write_csv(path, rows, list(rows[0].keys()))


def update_run_registry(path: Path, results: list[dict[str, str]]) -> None:
    fieldnames = [
        "run_id", "wave_id", "campaign_id", "idea_id", "hypothesis_id", "surface_id", "sweep_id",
        "status", "created_at_utc", "primary_family", "primary_skill", "manifest_path", "receipt_path",
        "lineage_path", "metrics_path", "claim_boundary", "result_judgment", "required_gates",
        "evidence_path", "next_action", "notes",
    ]
    existing = read_csv_rows(path) if path.exists() else []
    by_run = {row["run_id"]: row for row in existing}
    for item in results:
        manifest = json.loads((REPO_ROOT / item["run_manifest_path"]).read_text(encoding="utf-8-sig"))
        coverage = manifest["required_gate_coverage"]
        by_run[item["run_id"]] = {
            "run_id": item["run_id"],
            "wave_id": WAVE_ID,
            "campaign_id": CAMPAIGN_ID,
            "idea_id": IDEA_ID,
            "hypothesis_id": HYPOTHESIS_ID,
            "surface_id": SURFACE_ID,
            "sweep_id": SWEEP_ID,
            "status": item["status"],
            "created_at_utc": manifest["created_at_utc"],
            "primary_family": "model_training",
            "primary_skill": "spacesonar-model-validation",
            "manifest_path": item["run_manifest_path"],
            "receipt_path": item["receipt_path"],
            "lineage_path": item["lineage_path"],
            "metrics_path": item["metrics_path"],
            "claim_boundary": CLAIM_BOUNDARY,
            "result_judgment": item["result_judgment"],
            "required_gates": "|".join(coverage["passed"] + [f"missing:{gate}" for gate in coverage["missing"]] + [f"not_applicable:{gate}" for gate in coverage["not_applicable"]]),
            "evidence_path": f"lab/runs/{item['run_id']}/reports/proxy_session_transition_report.json",
            "next_action": NEXT_WORK_ITEM_ID,
            "notes": "Wave01 session-transition proxy observation; L4 required; no protected claim",
        }
    ordered = [row["run_id"] for row in existing]
    ordered.extend(run_id for run_id in sorted(by_run) if run_id not in ordered)
    write_csv(path, [by_run[run_id] for run_id in ordered], fieldnames)


def update_state(results: list[dict[str, str]]) -> None:
    counts = dict(sorted(Counter(item["result_judgment"] for item in results).items()))
    campaign_dir = REPO_ROOT / "lab/campaigns/campaign_us100_session_transition_regime_surface_v0"
    for rel in ["campaign_manifest.yaml", "first_batch_run_specs_manifest.yaml", "anti_selection_ledger.yaml", "sweeps/sweep_us100_session_transition_broad_v0/sweep_manifest.yaml"]:
        path = campaign_dir / rel
        payload = read_yaml(path)
        payload["status"] = "executed_proxy_observation_l4_required"
        payload["updated_at_utc"] = iso_z(utc_now())
        payload["claim_boundary"] = CLAIM_BOUNDARY
        payload["result_counts"] = counts
        payload["candidate_count"] = 0
        payload["next_action"] = NEXT_WORK_ITEM_ID
        write_yaml(path, payload)

    closeout = {
        "version": "work_closeout_v1",
        "work_item_id": WORK_ITEM_ID,
        "status": "proxy_execution_completed_L4_required_next",
        "closed_at_utc": iso_z(utc_now()),
        "result_judgment": "proxy_observation",
        "claim_boundary": CLAIM_BOUNDARY,
        "result_counts": counts,
        "candidate_count": 0,
        "runtime_learning_probe_decision": {"required": True, "decision": "run_required_next", "target_level": "L4_split_runtime_probe", "next_work_item": NEXT_WORK_ITEM_ID},
        "evidence_paths": {
            "run_refs": "lab/campaigns/campaign_us100_session_transition_regime_surface_v0/sweeps/sweep_us100_session_transition_broad_v0/run_refs.csv",
            "run_registry": "docs/registers/run_registry.csv",
        },
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "next_work_item": NEXT_WORK_ITEM_ID,
    }
    write_yaml(REPO_ROOT / f"lab/goals/goal_us100_onnx_forward_boundary_v0/{WORK_ITEM_ID}_closeout.yaml", closeout)

    next_work = {
        "version": "onnx_lab_work_item_v1",
        "work_item_id": NEXT_WORK_ITEM_ID,
        "active_goal_id": "goal_us100_onnx_forward_boundary_v0",
        "created_at_utc": iso_z(utc_now()),
        "status": "planned_next",
        "current_truth": {"claim_boundary": CLAIM_BOUNDARY, "result_counts": counts, "valid_proxy_model_bearing_run_count": len(results)},
        "work_classification": {"primary_family": "onnx_export_parity", "detected_families": ["onnx_export_parity", "runtime_probe"], "mutation_intent": "materialize_L4_follow_through"},
        "skill_routing": {"primary_family": "onnx_export_parity", "primary_skill": "spacesonar-runtime-parity", "support_skills": ["spacesonar-artifact-lineage", "spacesonar-run-evidence-system", "spacesonar-claim-discipline"], "required_gates": ["onnx_export_smoke", "python_onnx_parity", "proxy_runtime_parity_record", "bundle_integrity_hash", "L4_split_runtime_probe_for_valid_proxy_run", "final_claim_guard"]},
        "acceptance_criteria": ["Prepare L4 validation and research_oos attempts for every valid proxy/model-bearing run.", "Do not use locked final OOS-B.", "Do not claim runtime authority or economics pass."],
        "claim_boundary": "planned_session_transition_L4_materialization_preflight_no_runtime_authority_no_candidate",
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "next_action": "build_wave01_session_transition_onnx_materialization_and_L4_attempt_preparation",
    }
    write_yaml(REPO_ROOT / "lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml", next_work)

    for registry, key, updates in [
        ("campaign_registry.csv", "campaign_id", {"status": "executed_proxy_observation_l4_required", "claim_boundary": CLAIM_BOUNDARY, "evidence_path": "lab/campaigns/campaign_us100_session_transition_regime_surface_v0/sweeps/sweep_us100_session_transition_broad_v0/run_refs.csv", "next_action": NEXT_WORK_ITEM_ID}),
        ("sweep_registry.csv", "sweep_id", {"status": "executed_proxy_observation_l4_required", "evidence_boundary": CLAIM_BOUNDARY, "evidence_path": "lab/campaigns/campaign_us100_session_transition_regime_surface_v0/sweeps/sweep_us100_session_transition_broad_v0/run_refs.csv", "next_action": NEXT_WORK_ITEM_ID}),
    ]:
        update_registry_row(REPO_ROOT / "docs/registers" / registry, key, CAMPAIGN_ID if key == "campaign_id" else SWEEP_ID, updates)

    update_registry_row(
        REPO_ROOT / "docs/registers/goal_registry.csv",
        "goal_id",
        "goal_us100_onnx_forward_boundary_v0",
        {
            "active_phase": "wave01_campaign_003_proxy_executed_l4_required",
            "claim_boundary": "active_goal_session_transition_proxy_executed_L4_required_not_goal_achieve",
            "next_work_item": NEXT_WORK_ITEM_ID,
            "notes": "Wave01 session-transition proxy batch executed; L4 materialization preflight required next",
        },
    )

    wave_path = REPO_ROOT / "lab/waves/wave_us100_closedbar_surface_cartography_v0/wave_allocation.yaml"
    wave = read_yaml(wave_path)
    wave["status"] = "wave01_campaign_003_proxy_executed_l4_required"
    wave["claim_boundary"] = "wave01_campaign_003_proxy_executed_l4_required_no_candidate_no_runtime_authority"
    wave["next_action"] = NEXT_WORK_ITEM_ID
    wave["updated_at_utc"] = iso_z(utc_now())
    for allocation in wave.get("campaign_allocations") or []:
        if allocation.get("campaign_id") == CAMPAIGN_ID:
            allocation["status"] = "executed_proxy_observation_l4_required"
            allocation["claim_boundary"] = CLAIM_BOUNDARY
            allocation["next_action"] = NEXT_WORK_ITEM_ID
    write_yaml(wave_path, wave)

    campaign_refs_path = REPO_ROOT / "lab/waves/wave_us100_closedbar_surface_cartography_v0/campaign_refs.csv"
    ref_rows = []
    for row in read_csv_rows(campaign_refs_path):
        if row.get("campaign_id") == CAMPAIGN_ID:
            row["status"] = "executed_proxy_observation_l4_required"
            row["claim_boundary"] = CLAIM_BOUNDARY
            row["next_action"] = NEXT_WORK_ITEM_ID
            row["notes"] = "first broad session-transition proxy batch executed; L4 materialization preflight required next"
        ref_rows.append(row)
    write_csv(campaign_refs_path, ref_rows, list(ref_rows[0].keys()))

    goal = read_yaml(REPO_ROOT / "lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml")
    goal["updated_at_utc"] = iso_z(utc_now())
    goal["active_phase"] = "wave01_campaign_003_proxy_executed_l4_required"
    goal["claim_boundary"] = "active_goal_session_transition_proxy_executed_L4_required_not_goal_achieve"
    goal["next_work_item"] = {"path": "lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml", "work_item_id": NEXT_WORK_ITEM_ID}
    goal["session_transition_campaign"]["status"] = "executed_proxy_observation_l4_required"
    goal["session_transition_campaign"]["claim_boundary"] = CLAIM_BOUNDARY
    goal["session_transition_campaign"]["next_work_item"] = NEXT_WORK_ITEM_ID
    goal["session_transition_campaign"]["result_counts"] = counts
    write_yaml(REPO_ROOT / "lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml", goal)

    state = read_yaml(REPO_ROOT / "docs/workspace/workspace_state.yaml")
    claims = state["current_claims"]
    claims["active_goal_phase"] = "wave01_campaign_003_proxy_executed_l4_required"
    claims["active_goal_claim_boundary"] = "active_goal_session_transition_proxy_executed_L4_required_not_goal_achieve"
    claims["next_work_item_id"] = NEXT_WORK_ITEM_ID
    claims["wave0_third_campaign_status"] = "executed_proxy_observation_l4_required"
    claims["wave0_third_campaign_claim_boundary"] = CLAIM_BOUNDARY
    claims["wave0_third_campaign_next_work_item"] = NEXT_WORK_ITEM_ID
    claims["wave0_third_campaign_proxy_result_counts"] = counts
    claims["wave0_third_campaign_executed_proxy_run_count"] = len(results)
    claims["wave0_third_campaign_L4_status"] = "L4_materialization_preflight_required_next"
    state["updated_utc"] = iso_z(utc_now())
    write_yaml(REPO_ROOT / "docs/workspace/workspace_state.yaml", state)
    refresh_registry(REPO_ROOT, REPO_ROOT / "docs/registers/artifact_registry.csv", write=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute Wave01 session-transition first-batch proxy observations.")
    parser.add_argument("--row-membership-manifest", default=INPUT_REFS[1])
    parser.add_argument("--matrix", default=INPUT_REFS[0])
    parser.add_argument("--run-refs", default="lab/campaigns/campaign_us100_session_transition_regime_surface_v0/sweeps/sweep_us100_session_transition_broad_v0/run_refs.csv")
    parser.add_argument("--run-specs-index", default="lab/campaigns/campaign_us100_session_transition_regime_surface_v0/run_specs_index.csv")
    parser.add_argument("--expected-branch", default="codex/l4-pair-judgment-closeout")
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    branch = branch_worktree(args.expected_branch)
    status = git_status_lines()
    batch_git_state = {
        "git_sha": git_value(["rev-parse", "HEAD"]),
        "branch": git_value(["branch", "--show-current"]),
        "dirty_flag": "dirty" if status else "clean",
        "changed_files": status,
    }
    row_manifest_path = REPO_ROOT / args.row_membership_manifest
    frame = load_row_membership(read_yaml(row_manifest_path))
    matrix_rows = read_matrix(REPO_ROOT / args.matrix)
    run_refs = read_csv_rows(REPO_ROOT / args.run_refs)
    if args.limit is not None:
        run_refs = run_refs[: args.limit]
    results = [
        run_one(matrix_rows[row["run_spec_id"]], row, frame, row_manifest_path, sys.argv[:], branch, batch_git_state)
        for row in run_refs
    ]
    update_refs(REPO_ROOT / args.run_refs, results)
    update_refs(REPO_ROOT / args.run_specs_index, results)
    update_run_registry(REPO_ROOT / "docs/registers/run_registry.csv", results)
    update_state(results)
    print(json.dumps({"status": "wave01_session_transition_proxy_batch_executed_l4_required", "run_count": len(results), "result_counts": dict(sorted(Counter(item["result_judgment"] for item in results).items())), "claim_boundary": CLAIM_BOUNDARY, "next_work_item": NEXT_WORK_ITEM_ID}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
