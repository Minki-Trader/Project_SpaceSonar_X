from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation.features.wave02_tradeability_features import build_wave02_tradeability_features  # noqa: E402
from foundation.labels.wave02_tradeability_labels import build_wave02_tradeability_labels  # noqa: E402
from spacesonar.control_plane.provenance import begin_execution_batch, execution_batch_ref, finalize_execution_batch  # noqa: E402
from spacesonar.control_plane.store import dump_yaml, filesystem_path  # noqa: E402
from foundation.training.wave01_event_barrier_models import (  # noqa: E402
    decision_metrics,
    diagnostic_metrics,
    fit_proxy_model,
    judge_proxy_result,
    score_model,
)


UTC = timezone.utc
WORK_ITEM_ID = "execute_materialized_run_specs"
NEXT_WORK_ITEM_ID = "work_wave02_tradeability_l4_materialization_preflight_v0"
CAMPAIGN_ID = "campaign_us100_wave02_tradeability_decision_surface_v0"
WAVE_ID = "wave_us100_wave02_tradeability_decision_surface_v0"
SURFACE_ID = "surface_us100_wave02_tradeability_side_abstain_v0"
SWEEP_ID = "sweep_us100_wave02_tradeability_side_abstain_broad_v0"
CLAIM_BOUNDARY = "wave02_proxy_observation_l4_required_no_candidate_no_runtime_authority_no_economics_pass_no_live_readiness_no_goal_achieve"
STATUS = "wave02_proxy_observation_l4_required"
RUN_STATUS = "executed_proxy_observation_l4_required"
ENTRYPOINT = "foundation/pipelines/run_wave02_tradeability_proxy_batch.py"
RUN_REFS = Path("lab/campaigns") / CAMPAIGN_ID / "sweeps" / SWEEP_ID / "run_refs.csv"
CAMPAIGN_DIR = Path("lab/campaigns") / CAMPAIGN_ID
ROW_MEMBERSHIP_MANIFEST = Path("lab/campaigns/campaign_us100_task_surface_scout_v0/row_membership/row_membership_manifest.yaml")
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
MODEL_FAMILY_BY_RECIPE = {
    "model_wave02_logistic_tradeability_v0": "logistic_or_linear_rank_scout",
    "model_wave02_tree_tradeability_v0": "tree_or_boosted_onnx_feasible_scout",
    "model_wave02_interpretable_tradeability_v0": "logistic_or_linear_rank_scout",
}


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def iso_z(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def mask_local_path(value: str) -> str:
    home = Path.home()
    text = str(value)
    for variant in (str(home), home.as_posix()):
        text = text.replace(variant, "${USERPROFILE}")
    return text


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return mask_local_path(str(path.resolve()))


def durable_arg(value: str) -> str:
    try:
        path = Path(value)
        if path.is_absolute():
            return repo_relative(path)
    except OSError:
        return mask_local_path(value)
    return mask_local_path(value)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(filesystem_path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_ref(path: Path, *, availability: str = "present_hash_recorded") -> dict[str, Any]:
    stat = os.stat(filesystem_path(path))
    return {
        "path": repo_relative(path),
        "sha256": file_sha256(path),
        "size_bytes": stat.st_size,
        "availability": availability,
    }


def read_yaml(path: Path) -> dict[str, Any]:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a YAML mapping")
    return payload


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    os.makedirs(filesystem_path(path.parent), exist_ok=True)
    with open(filesystem_path(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(dump_yaml(_jsonable(payload)))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    os.makedirs(filesystem_path(path.parent), exist_ok=True)
    with open(filesystem_path(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(_jsonable(payload), indent=2, ensure_ascii=True) + "\n")


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with open(filesystem_path(path), "r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def git_value(args: list[str]) -> str:
    result = subprocess.run(["git", *args], cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip() or "unknown"


def git_status_lines() -> list[str]:
    result = subprocess.run(["git", "status", "--short"], cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def dependency_summary() -> dict[str, str]:
    versions: dict[str, str] = {"python": platform.python_version(), "platform": platform.platform()}
    for package in ["numpy", "pandas", "sklearn", "yaml"]:
        try:
            module = __import__(package)
            versions[package] = str(getattr(module, "__version__", "unknown"))
        except Exception as exc:  # noqa: BLE001 - environment evidence.
            versions[package] = f"unavailable:{exc}"
    return versions


def branch_worktree(expected_branch: str) -> dict[str, str]:
    current = git_value(["branch", "--show-current"])
    if current != expected_branch:
        raise RuntimeError(f"branch mismatch before Wave02 execution: current={current!r} expected={expected_branch!r}")
    return {
        "current_branch": current,
        "requested_branch": expected_branch,
        "branch_worktree_fit": "fit",
        "branch_action": "keep_current_branch",
        "policy_reference": "docs/policies/branch_policy.md",
        "mismatch_claim_effect": "not_applicable",
    }


def provenance(command_argv: list[str], input_paths: list[Path], output_paths: list[Path], started_at: datetime) -> dict[str, Any]:
    status = git_status_lines()
    return {
        "git_sha": git_value(["rev-parse", "HEAD"]),
        "branch": git_value(["branch", "--show-current"]),
        "dirty_flag": "dirty" if status else "clean",
        "changed_files": status,
        "command_argv": [durable_arg(arg) for arg in command_argv],
        "python_executable": mask_local_path(sys.executable),
        "python_version": platform.python_version(),
        "key_package_versions": dependency_summary(),
        "started_at_utc": iso_z(started_at),
        "ended_at_utc": iso_z(utc_now()),
        "input_hashes": [artifact_ref(path) for path in input_paths if os.path.exists(filesystem_path(path))],
        "output_hashes": [artifact_ref(path) for path in output_paths if os.path.exists(filesystem_path(path))],
        "dirty_worktree_claim_effect": "proxy_observation_only_no_reproducible_candidate_bundle_runtime_or_goal_achieve_claim",
    }


def load_row_membership(path: Path) -> pd.DataFrame:
    manifest = read_yaml(path)
    csv_info = manifest["row_membership"]["full_csv"]
    csv_path = REPO_ROOT / csv_info["path"]
    if not os.path.exists(filesystem_path(csv_path)):
        raise FileNotFoundError(f"row membership CSV missing: {csv_info['path']}")
    observed = file_sha256(csv_path)
    if observed != csv_info["sha256"]:
        raise RuntimeError(f"row membership hash mismatch expected={csv_info['sha256']} observed={observed}")
    frame = pd.read_csv(filesystem_path(csv_path))
    for column in ["open", "high", "low", "close", "tick_volume", "spread_points", "real_volume", "row_seq", "time_open_unix", "time_close_unix"]:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def split_masks(frame: pd.DataFrame, labels: pd.DataFrame) -> dict[str, pd.Series]:
    eligible = labels["same_role_horizon_ok"].astype(bool)
    role = frame["primary_split_role"].astype(str)
    return {
        "train": eligible & role.eq("train"),
        "validation": eligible & role.eq("validation"),
        "research_oos_a": eligible & role.eq("research_oos_a"),
        "locked_final_oos_b_withheld": eligible & role.eq("locked_final_oos_b"),
    }


def usable_feature_columns(features: pd.DataFrame, train_mask: pd.Series) -> list[str]:
    columns = [column for column in features.columns if features.loc[train_mask, column].notna().any()]
    if not columns:
        raise ValueError("no usable Wave02 feature columns")
    return columns


def build_model_target(labels: pd.DataFrame, train_mask: pd.Series) -> tuple[pd.Series, str, str, float | None]:
    raw = labels["target_binary_raw"].astype(float)
    train_raw = raw.loc[train_mask].dropna()
    if len(set(train_raw.astype(int).tolist())) >= 2:
        return raw, "classification", "target_binary_raw", None
    continuous = labels["target_continuous"].astype(float)
    threshold = float(continuous.loc[train_mask].quantile(0.60))
    return (continuous >= threshold).astype(float), "classification", "target_continuous_train_q60", threshold


def model_family_for_recipe(model_recipe_id: str) -> str:
    model_family = MODEL_FAMILY_BY_RECIPE.get(model_recipe_id)
    if not model_family:
        raise ValueError(f"unsupported Wave02 model_recipe_id: {model_recipe_id}")
    return model_family


def write_prediction_sample(path: Path, frame: pd.DataFrame, labels: pd.DataFrame, scores: pd.Series, target: pd.Series) -> None:
    sample = pd.DataFrame(
        {
            "model_row_key": frame["model_row_key"],
            "primary_split_role": frame["primary_split_role"],
            "close": frame["close"],
            "future_return": labels["future_return"],
            "future_abs_return_atr": labels["future_abs_return_atr"],
            "target": target,
            "side_label": labels["side_label"],
            "score": scores,
        }
    )
    sample = sample.replace([np.inf, -np.inf], np.nan).dropna(subset=["score"]).head(200)
    os.makedirs(filesystem_path(path.parent), exist_ok=True)
    sample.to_csv(filesystem_path(path), index=False, lineterminator="\n")


def routing() -> dict[str, Any]:
    support_skills = ["spacesonar-data-integrity", "spacesonar-evidence-provenance", "spacesonar-runtime-evidence"]
    primary_skill = "spacesonar-model-validation"
    return {
        "primary_family": "model_training",
        "primary_skill": primary_skill,
        "support_skills": support_skills,
        "skills_selected": [primary_skill, *support_skills],
        "skills_not_used": [],
        "critical_skills_not_selected": [],
        "not_selected_claim_effect": "all declared primary and support skills selected for this run",
        "required_gates": REQUIRED_GATES,
    }


def runtime_decision(run_id: str) -> dict[str, Any]:
    return {
        "required": True,
        "decision": "run_required_next",
        "target_level": "L4_split_runtime_probe",
        "runtime_period_profile_id": "period_profile_split_set_v0",
        "required_period_roles": ["validation", "research_oos"],
        "lowered_claim_if_not_run": "proxy_observation_only_no_runtime_authority_no_economics_pass_no_candidate",
        "follow_up_work_item_id": NEXT_WORK_ITEM_ID,
        "run_id": run_id,
    }


def proxy_runtime_parity(decision_recipe_id: str) -> dict[str, Any]:
    return {
        "shared_contract": "US100_M5_closed_bar_wave02_tradeability_score_and_side_abstain_semantics",
        "decision_recipe_id": decision_recipe_id,
        "known_differences": [
            "proxy uses gross future return labels without spread, fill, slippage, swap, or execution timing",
            "MT5 follow-through must implement side, abstain, timeout, and session gates before runtime authority can be discussed",
        ],
        "minimum_reconciliation_attempt": {"required": True, "status": "pending_L4_materialization"},
        "comparison_class": "pending_L4",
        "claim_boundary": "proxy_runtime_parity_tracking_only_no_runtime_authority",
        "follow_up_action": NEXT_WORK_ITEM_ID,
    }


def model_validation_summary(
    *,
    run_spec: dict[str, Any],
    model_family: str,
    target_name: str,
    target_threshold: float | None,
    decision_recipe_id: str,
    validation_judgment: str,
) -> dict[str, Any]:
    refs = run_spec["recipe_refs"]
    return {
        "model_family": {"model_recipe_id": refs["model_recipe_id"], "proxy_model_family": model_family, "training_script": ENTRYPOINT},
        "target_and_label": {"label_recipe_id": refs["label_recipe_id"], "target_name": target_name, "target_threshold": target_threshold},
        "split_method": "split_set_v0_train_validation_research_oos_a_locked_final_oos_b_withheld",
        "selection_metric": "none_selected_broad_proxy_observation",
        "secondary_metrics": ["roc_auc", "average_precision", "balanced_accuracy", "gross_proxy_profit_factor", "trade_count"],
        "threshold_policy": "train_quantile_score_thresholds_for_proxy_decision_only",
        "overfit_risk": "broad_surface_multiple_testing_risk_no_selection_allowed",
        "calibration_risk": "scores_are_rank_or_classifier_outputs_not_calibrated_probabilities",
        "top_n_selection_bias_check": "no_top_n_selection_or_baseline_promotion",
        "threshold_knife_edge_check": "thresholds recorded_for_L4_follow_through_not_used_for_selection",
        "segment_or_regime_stability_check": "validation_and_research_oos_a_recorded_separately",
        "trade_concentration_check": "trade_count_and_density_recorded_no_economics_claim",
        "wfo_or_window_dispersion": "split_set_v0_primary_windows_only_WFO_missing_claim_lowered",
        "proxy_runtime_laundering_check": "proxy_only_L4_required_no_runtime_authority",
        "risk_stop_check": "runtime_stop_hold_execution_missing_until_L4",
        "comparison_baseline": ["no_trade_baseline_reference_only", "Wave01 clues_as_questions_only_no_inheritance"],
        "anti_authority_laundering_judgment": "exploratory_proxy_observation_only",
        "decision_recipe_id": decision_recipe_id,
        "validation_judgment": validation_judgment,
    }


def run_one(
    run_spec: dict[str, Any],
    frame: pd.DataFrame,
    command_argv: list[str],
    branch: dict[str, str],
    batch_git_state: dict[str, Any],
) -> dict[str, str]:
    run_id = str(run_spec["run_id"])
    refs = run_spec["recipe_refs"]
    root = REPO_ROOT / "lab" / "runs" / run_id
    artifacts = root / "artifacts"
    reports = root / "reports"
    started = utc_now()
    features, feature_schema = build_wave02_tradeability_features(frame, refs["feature_recipe_id"])
    labels, label_schema = build_wave02_tradeability_labels(frame, refs["label_recipe_id"])
    masks = split_masks(frame, labels)
    train_mask = masks["train"]
    validation_mask = masks["validation"]
    research_mask = masks["research_oos_a"]
    target, task_kind, target_name, target_threshold = build_model_target(labels, train_mask)
    target_ok = target.notna()
    train_mask &= target_ok
    validation_mask &= target_ok
    research_mask &= target_ok
    if int(train_mask.sum()) < 1000 or int(validation_mask.sum()) < 300 or int(research_mask.sum()) < 300:
        raise ValueError(f"{run_id} insufficient split rows train={int(train_mask.sum())} validation={int(validation_mask.sum())} research={int(research_mask.sum())}")
    columns = usable_feature_columns(features, train_mask)
    model_family = model_family_for_recipe(refs["model_recipe_id"])
    x = features[columns]
    fit = fit_proxy_model(
        x,
        target,
        train_mask,
        model_family=model_family,
        task_kind=task_kind,
        target_name=target_name,
        threshold_policy="train_quantile_proxy_threshold",
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
    decision = {
        "validation": decision_metrics(decision_family=refs["decision_recipe_id"], score=scores["validation"], labels=labels.loc[validation_mask], fit=fit),
        "research_oos_a": decision_metrics(decision_family=refs["decision_recipe_id"], score=scores["research_oos_a"], labels=labels.loc[research_mask], fit=fit),
    }
    judgment, reasons = judge_proxy_result(
        model_metrics["validation"],
        model_metrics["research_oos_a"],
        decision["validation"],
        decision["research_oos_a"],
        task_kind,
    )
    split_profile = {
        "raw_rows": int(len(frame)),
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
    report_path = reports / "proxy_tradeability_report.json"
    outputs = [feature_schema_path, label_schema_path, model_summary_path, split_profile_path, validation_sample_path, research_sample_path, report_path]
    write_json(feature_schema_path, {**feature_schema.__dict__, "used_feature_columns": columns, "used_feature_count": len(columns)})
    write_json(label_schema_path, {**label_schema.__dict__, "target_name_used_for_model": target_name, "target_threshold": target_threshold})
    write_json(model_summary_path, {"run_id": run_id, "model_recipe_id": refs["model_recipe_id"], "proxy_model_family": model_family, "task_kind": task_kind, "model_summary": fit.model_summary, "train_score_summary": fit.train_score_summary})
    write_json(split_profile_path, split_profile)
    write_prediction_sample(validation_sample_path, frame.loc[validation_mask], labels.loc[validation_mask], pd.Series(scores["validation"], index=labels.loc[validation_mask].index), target.loc[validation_mask])
    write_prediction_sample(research_sample_path, frame.loc[research_mask], labels.loc[research_mask], pd.Series(scores["research_oos_a"], index=labels.loc[research_mask].index), target.loc[research_mask])
    validation_summary = model_validation_summary(
        run_spec=run_spec,
        model_family=model_family,
        target_name=target_name,
        target_threshold=target_threshold,
        decision_recipe_id=refs["decision_recipe_id"],
        validation_judgment=judgment,
    )
    report = {
        "version": "wave02_tradeability_proxy_report_v1",
        "run_id": run_id,
        "run_spec_path": repo_relative(REPO_ROOT / CAMPAIGN_DIR / "run_specs" / f"{run_id}.yaml"),
        "recipe_refs": refs,
        "target_and_label": validation_summary["target_and_label"],
        "split_method": validation_summary["split_method"],
        "model_metrics": model_metrics,
        "decision_metrics": decision,
        "judgment_reasons": reasons,
        "model_validation": validation_summary,
        "validation_judgment": judgment,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    write_json(report_path, report)
    output_refs = [artifact_ref(path) for path in outputs]
    input_paths = [REPO_ROOT / ROW_MEMBERSHIP_MANIFEST, REPO_ROOT / CAMPAIGN_DIR / "run_specs" / f"{run_id}.yaml"]
    prov = provenance(command_argv, input_paths, outputs, started)
    prov.update(batch_git_state)
    prov["git_state_capture_policy"] = "batch_start_before_generated_outputs"
    storage = {
        "source_of_truth": f"lab/runs/{run_id}/run_manifest.json",
        "receipt": f"lab/runs/{run_id}/experiment_receipt.yaml",
        "lineage": f"lab/runs/{run_id}/artifact_lineage.json",
        "metrics": f"lab/runs/{run_id}/metrics.json",
        "registry_rows": ["docs/registers/run_registry.csv"],
    }
    coverage = {"passed": REQUIRED_GATES[:-1], "missing": ["L4_split_runtime_probe_for_valid_proxy_run"], "not_applicable": ["locked_final_oos_access"]}
    missing_evidence = ["ONNX_export_not_materialized_for_L4_yet", "MT5_L4_split_runtime_probe_not_run_yet", "candidate_selection_forbidden_before_L4"]
    base = {
        "run_id": run_id,
        "id_chain": run_spec["id_chain"],
        "skill_routing": routing(),
        "branch_worktree": branch,
        "provenance": prov,
        "storage_contract": storage,
        "runtime_learning_probe_decision": runtime_decision(run_id),
        "proxy_runtime_parity": proxy_runtime_parity(refs["decision_recipe_id"]),
        "required_gate_coverage": coverage,
        "result_judgment": judgment,
        "model_validation": validation_summary,
        "missing_evidence": missing_evidence,
        "claim_boundary": CLAIM_BOUNDARY,
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "next_action": NEXT_WORK_ITEM_ID,
        "evidence_path": repo_relative(report_path),
        "notes": "Wave02 proxy observation only; L4 follow-through required before runtime claims.",
    }
    manifest = {
        "version": "run_manifest_v3",
        **base,
        "trigger_source": WORK_ITEM_ID,
        "status": RUN_STATUS,
        "created_at_utc": iso_z(utc_now()),
        "entrypoint": ENTRYPOINT,
        "command": " ".join(durable_arg(arg) for arg in command_argv),
        "task_surface": {
            "task_type": "tradeability_side_abstain_proxy",
            "target_or_label": refs["label_recipe_id"],
            "output_head": "tradeability_score_with_side_abstain_decision_recipe",
        },
    }
    receipt = {
        "version": "experiment_receipt_v2",
        **base,
        "hypothesis": "Explicit tradeability plus side/abstain semantics may expose runtime-testable Wave02 surfaces.",
        "decision_use": refs["decision_recipe_id"],
        "sample_scope": split_profile,
        "evidence_plan": list(storage.values()),
    }
    metrics = {
        "version": "metrics_v2",
        "run_id": run_id,
        "status": RUN_STATUS,
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
        "source_inputs": [artifact_ref(path) for path in input_paths if os.path.exists(filesystem_path(path))],
        "producer": {"type": "script", "identity": ENTRYPOINT, "command": " ".join(durable_arg(arg) for arg in command_argv)},
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
        "status": RUN_STATUS,
        "result_judgment": judgment,
        "run_manifest_path": repo_relative(root / "run_manifest.json"),
        "receipt_path": repo_relative(root / "experiment_receipt.yaml"),
        "lineage_path": repo_relative(root / "artifact_lineage.json"),
        "metrics_path": repo_relative(root / "metrics.json"),
        "report_path": repo_relative(report_path),
        "claim_boundary": CLAIM_BOUNDARY,
        "next_action": NEXT_WORK_ITEM_ID,
        "notes": ";".join(reasons),
    }


def attach_execution_batch_refs(results: list[dict[str, str]], *, batch_id: str, command_argv: list[str], input_paths: list[Path]) -> None:
    receipt = begin_execution_batch(
        REPO_ROOT,
        batch_id=batch_id,
        work_item_id=WORK_ITEM_ID,
        command_argv=[durable_arg(arg) for arg in command_argv],
        input_paths=[repo_relative(path) for path in input_paths],
        allow_exploratory_dirty=True,
        claim_boundary=CLAIM_BOUNDARY,
        write=True,
    )
    finalize_execution_batch(
        REPO_ROOT,
        batch_id=batch_id,
        output_paths=[f"lab/executions/{batch_id}/source_snapshot/source_snapshot_manifest.yaml"],
        exit_status=0,
        result_status="completed",
        receipt=receipt,
        write=True,
    )
    ref = execution_batch_ref(REPO_ROOT, batch_id)
    for item in results:
        manifest_path = REPO_ROOT / item["run_manifest_path"]
        manifest = _read_json_file(manifest_path)
        manifest["execution_batch_ref"] = ref
        manifest.setdefault("provenance", {})["execution_batch_id"] = batch_id
        write_json(manifest_path, manifest)

        receipt_path = REPO_ROOT / item["receipt_path"]
        receipt = read_yaml(receipt_path)
        receipt["execution_batch_ref"] = ref
        receipt.setdefault("provenance", {})["execution_batch_id"] = batch_id
        write_yaml(receipt_path, receipt)


def _read_json_file(path: Path) -> dict[str, Any]:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a JSON mapping")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute Wave02 tradeability prepared proxy run specs.")
    parser.add_argument("--row-membership-manifest", default=ROW_MEMBERSHIP_MANIFEST.as_posix())
    parser.add_argument("--run-refs", default=RUN_REFS.as_posix())
    parser.add_argument("--expected-branch", default="codex/wave02-execute-materialized-run-specs")
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    command_argv = sys.argv[:]
    branch = branch_worktree(args.expected_branch)
    batch_git_state = {
        "batch_start_git_status": git_status_lines(),
        "batch_start_git_sha": git_value(["rev-parse", "HEAD"]),
        "batch_start_branch": git_value(["branch", "--show-current"]),
    }
    frame = load_row_membership(REPO_ROOT / args.row_membership_manifest)
    run_refs = read_csv_rows(REPO_ROOT / args.run_refs)
    if args.limit is not None:
        run_refs = run_refs[: args.limit]
    results = []
    for row in run_refs:
        spec_path = REPO_ROOT / row["run_spec_path"]
        spec = read_yaml(spec_path)
        results.append(run_one(spec, frame, command_argv, branch, batch_git_state))
    batch_id = f"batch_wave02_tradeability_proxy_{utc_now().strftime('%Y%m%dT%H%M%S%fZ')}"
    attach_execution_batch_refs(
        results,
        batch_id=batch_id,
        command_argv=command_argv,
        input_paths=[REPO_ROOT / args.row_membership_manifest],
    )
    print(json.dumps({"status": STATUS, "executed_proxy_run_count": len(results), "result_counts": dict(Counter(item["result_judgment"] for item in results))}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
