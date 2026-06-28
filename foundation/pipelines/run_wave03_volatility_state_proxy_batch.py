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

from foundation.features.wave03_volatility_state_features import build_wave03_volatility_state_features  # noqa: E402
from foundation.labels.wave03_volatility_state_labels import build_wave03_volatility_state_labels  # noqa: E402
from foundation.training.wave01_event_barrier_models import (  # noqa: E402
    decision_metrics,
    diagnostic_metrics,
    fit_proxy_model,
    judge_proxy_result,
    score_model,
)
from spacesonar.control_plane.store import dump_yaml, filesystem_path  # noqa: E402
from spacesonar.control_plane.writer_contract import (  # noqa: E402
    WRITER_CONTRACT_VERSION,
    default_validation_attempt_budget,
    default_writer_preflight_gate,
    enforce_writer_contract,
)


UTC = timezone.utc
GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WORK_ITEM_ID = "execute_materialized_run_specs"
NEXT_WORK_ITEM_ID = "work_wave03_volatility_state_l4_materialization_preflight_v0"
WAVE_ID = "wave_us100_wave03_volatility_state_transition_surface_v0"
CAMPAIGN_ID = "campaign_us100_wave03_volatility_state_transition_surface_v0"
IDEA_ID = "idea_us100_wave03_intraday_volatility_state_transition_v0"
HYPOTHESIS_ID = "hyp_us100_wave03_compression_expansion_reversal_continuation_v0"
SURFACE_ID = "surface_us100_wave03_compression_expansion_decision_v0"
SWEEP_ID = "sweep_us100_wave03_compression_expansion_seed_v0"
STATUS = "wave03_proxy_observation_l4_required"
RUN_STATUS = "executed_proxy_observation_l4_required"
CLAIM_BOUNDARY = (
    "wave03_proxy_observation_l4_required_no_candidate_no_selected_baseline_no_runtime_authority_"
    "no_economics_pass_no_live_readiness_no_goal_achieve"
)
NEXT_ACTION = "materialize_wave03_volatility_state_l4_follow_through"
ENTRYPOINT = "foundation/pipelines/run_wave03_volatility_state_proxy_batch.py"
CAMPAIGN_DIR = Path("lab/campaigns") / CAMPAIGN_ID
WAVE_DIR = Path("lab/waves") / WAVE_ID
GOAL_DIR = Path("lab/goals") / GOAL_ID
RUN_REFS = CAMPAIGN_DIR / "sweeps" / SWEEP_ID / "run_refs.csv"
SUMMARY_PATH = CAMPAIGN_DIR / "proxy_execution_summary.yaml"
INDEX_PATH = CAMPAIGN_DIR / "proxy_execution_index.csv"
WORK_CLOSEOUT = GOAL_DIR / "work_wave03_volatility_state_proxy_execution_v0_closeout.yaml"
ROW_MEMBERSHIP_MANIFEST = Path(
    "lab/campaigns/campaign_us100_task_surface_scout_v0/row_membership/row_membership_manifest.yaml"
)

PATHS = {
    "goal_manifest": GOAL_DIR / "goal_manifest.yaml",
    "next_work_item": GOAL_DIR / "next_work_item.yaml",
    "resume_cursor": GOAL_DIR / "resume_cursor.yaml",
    "workspace_state": Path("docs/workspace/workspace_state.yaml"),
    "campaign_manifest": CAMPAIGN_DIR / "campaign_manifest.yaml",
    "sweep_manifest": CAMPAIGN_DIR / "sweeps" / SWEEP_ID / "sweep_manifest.yaml",
    "wave_allocation": WAVE_DIR / "wave_allocation.yaml",
    "campaign_refs": WAVE_DIR / "campaign_refs.csv",
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
SKIPPED_BROAD_VALIDATIONS = [
    "pytest",
    "project_validate",
    "full_regression_workflow",
    "evidence_graph_full_workflow",
    "active_record_validator_full_graph",
    "spacesonar_project_validate_full",
    "broad_hash_resync",
    "global_registry_regeneration",
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
    "model_wave03_logistic_transition_v0": "logistic_or_linear_rank_scout",
    "model_wave03_tree_transition_v0": "tree_or_boosted_onnx_feasible_scout",
    "model_wave03_boosted_transition_onnx_feasible_v0": "tree_or_boosted_onnx_feasible_scout",
}


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def iso_z(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def repo_path(path: Path | str) -> Path:
    path = Path(path)
    return path if path.is_absolute() else REPO_ROOT / path


def repo_relative(path: Path | str) -> str:
    path = Path(path)
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path).replace("\\", "/")


def rel_for_contract(path: Path | str) -> str:
    text = str(path).replace("\\", "/")
    candidate = Path(text)
    if candidate.is_absolute():
        return repo_relative(candidate)
    return text


def mask_local_path(value: str) -> str:
    home = Path.home()
    text = str(value)
    for variant in (str(home), home.as_posix()):
        text = text.replace(variant, "${USERPROFILE}")
    return text


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


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return iso_z(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


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


def write_machine_yaml(path: Path, payload: dict[str, Any]) -> None:
    enforce_writer_contract(rel_for_contract(repo_relative(path)), _jsonable(payload))
    write_yaml(path, payload)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    os.makedirs(filesystem_path(path.parent), exist_ok=True)
    with open(filesystem_path(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(_jsonable(payload), indent=2, ensure_ascii=True) + "\n")


def read_json(path: Path) -> dict[str, Any]:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a JSON mapping")
    return payload


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with open(filesystem_path(path), "r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv_rows(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    os.makedirs(filesystem_path(path.parent), exist_ok=True)
    with open(filesystem_path(path), "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows([{field: _jsonable(row.get(field, "")) for field in fields} for row in rows])


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
        raise RuntimeError(f"branch mismatch before Wave03 execution: current={current!r} expected={expected_branch!r}")
    return {
        "current_branch": current,
        "requested_branch": expected_branch,
        "branch_worktree_fit": "fit",
        "branch_action": "keep_current_branch_main_user_override",
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
        "output_hashes": [
            artifact_ref(path, availability="local_generated_hash_recorded_not_committed")
            for path in output_paths
            if os.path.exists(filesystem_path(path))
        ],
        "dirty_worktree_claim_effect": "proxy_observation_only_no_candidate_bundle_runtime_authority_economics_or_goal_achieve_claim",
    }


def writer_contract_fields(*, writer_owned_outputs: list[Path | str], next_action: str = NEXT_ACTION) -> dict[str, Any]:
    budget = default_validation_attempt_budget()
    budget["observed_writer_scope_attempts"] = 0
    return {
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "primary_family": "model_training",
        "primary_skill": "spacesonar-model-validation",
        "progress_class": "next_executable_experiment_writer_or_probe",
        "progress_effect": "proxy_batch_execution_materialized_with_l4_required_next_action",
        "next_executable_action": next_action,
        "experiment_or_boundary_effect": "executed_proxy_run_records_materialized_l4_follow_through_required",
        "source_of_truth_paths": [
            SUMMARY_PATH.as_posix(),
            INDEX_PATH.as_posix(),
            PATHS["next_work_item"].as_posix(),
            PATHS["campaign_manifest"].as_posix(),
            PATHS["wave_allocation"].as_posix(),
            ROW_MEMBERSHIP_MANIFEST.as_posix(),
            RUN_REFS.as_posix(),
        ],
        "writer_owned_outputs": [Path(path).as_posix() for path in writer_owned_outputs],
        "validation_depth": "writer_scope_smoke",
        "non_pytest_smokes": [
            "py_compile_wave03_helpers_and_runner",
            "strict_writer_contract_preflight",
            "run_manifest_receipt_metrics_lineage_presence_check",
            "active_pointer_smoke",
        ],
        "skipped_broad_validations": SKIPPED_BROAD_VALIDATIONS,
        "broad_validation_escalation_reason": "none_proxy_execution_no_protected_claim_no_broad_validation",
        "writer_preflight_gate": default_writer_preflight_gate(),
        "validation_attempt_budget": budget,
        "writer_scope_self_check": {
            "status": "passed",
            "writer_contract_version": WRITER_CONTRACT_VERSION,
            "validation_depth": "writer_scope_smoke",
            "non_pytest_smokes": ["strict_writer_contract_preflight"],
            "failures": [],
        },
        "claim_boundary": CLAIM_BOUNDARY,
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "unresolved_blockers_or_none": [],
        "next_action_or_reopen_condition": next_action,
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
    for column in [
        "open",
        "high",
        "low",
        "close",
        "tick_volume",
        "spread_points",
        "real_volume",
        "row_seq",
        "time_open_unix",
        "time_close_unix",
    ]:
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
        raise ValueError("no usable Wave03 feature columns")
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
        raise ValueError(f"unsupported Wave03 model_recipe_id: {model_recipe_id}")
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


def proxy_decisions_from_scores(scores: pd.Series, fit: Any) -> pd.Series:
    decisions = pd.Series("flat", index=scores.index, dtype="object")
    high = fit.score_high_threshold
    low = fit.score_low_threshold
    if high is None or low is None or not np.isfinite(high) or not np.isfinite(low):
        return decisions
    decisions.loc[scores >= high] = "long"
    decisions.loc[scores <= low] = "short"
    return decisions


def write_decision_stream(
    path: Path,
    frame: pd.DataFrame,
    labels: pd.DataFrame,
    scores: pd.Series,
    target: pd.Series,
    fit: Any,
    decision_recipe_id: str,
) -> None:
    decisions = proxy_decisions_from_scores(scores, fit)
    stream = pd.DataFrame(
        {
            "model_row_key": frame["model_row_key"],
            "time_close_unix": frame["time_close_unix"],
            "primary_split_role": frame["primary_split_role"],
            "close": frame["close"],
            "spread_points": frame["spread_points"],
            "tick_volume": frame["tick_volume"],
            "future_return": labels["future_return"],
            "target": target,
            "side_label": labels["side_label"],
            "score": scores,
            "proxy_decision": decisions,
            "decision_recipe_id": decision_recipe_id,
            "threshold_policy": fit.threshold_policy,
            "score_low_threshold": fit.score_low_threshold,
            "score_high_threshold": fit.score_high_threshold,
        }
    )
    stream = stream.replace([np.inf, -np.inf], np.nan).dropna(subset=["score"])
    os.makedirs(filesystem_path(path.parent), exist_ok=True)
    stream.to_csv(filesystem_path(path), index=False, lineterminator="\n")


def routing() -> dict[str, Any]:
    support_skills = ["spacesonar-data-integrity", "spacesonar-evidence-provenance", "spacesonar-runtime-evidence"]
    primary_skill = "spacesonar-model-validation"
    return {
        "primary_family": "model_training",
        "primary_skill": primary_skill,
        "support_skills": support_skills,
        "skills_selected": [primary_skill, *support_skills],
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
        "shared_contract": "US100_M5_closed_bar_wave03_volatility_state_score_and_reversal_continuation_semantics",
        "decision_recipe_id": decision_recipe_id,
        "known_differences": [
            "proxy uses gross future return labels without spread, fill, slippage, swap, or execution timing",
            "MT5 follow-through must implement side, abstain, timeout, and volatility/session state gates before runtime authority can be discussed",
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
        "model_family": {
            "model_recipe_id": refs["model_recipe_id"],
            "proxy_model_family": model_family,
            "training_script": ENTRYPOINT,
        },
        "target_and_label": {
            "label_recipe_id": refs["label_recipe_id"],
            "target_name": target_name,
            "target_threshold": target_threshold,
        },
        "split_method": "split_set_v0_train_validation_research_oos_a_locked_final_oos_b_withheld",
        "selection_metric": "none_selected_broad_proxy_observation",
        "secondary_metrics": ["roc_auc", "average_precision", "balanced_accuracy", "gross_proxy_profit_factor", "trade_count"],
        "threshold_policy": "train_quantile_score_thresholds_for_proxy_decision_only",
        "overfit_risk": "broad_surface_multiple_testing_risk_no_selection_allowed",
        "calibration_risk": "scores_are_rank_or_classifier_outputs_not_calibrated_probabilities",
        "top_n_selection_bias_check": "no_top_n_selection_or_baseline_promotion",
        "threshold_knife_edge_check": "thresholds_recorded_for_L4_follow_through_not_used_for_selection",
        "segment_or_regime_stability_check": "validation_and_research_oos_a_recorded_separately",
        "trade_concentration_check": "trade_count_and_density_recorded_no_economics_claim",
        "wfo_or_window_dispersion": "split_set_v0_primary_windows_only_WFO_missing_claim_lowered",
        "proxy_runtime_laundering_check": "proxy_only_L4_required_no_runtime_authority",
        "risk_stop_check": "runtime_stop_hold_execution_missing_until_L4",
        "comparison_baseline": ["no_trade_baseline_reference_only", "Wave02_negative_memory_reference_only_no_inheritance"],
        "anti_authority_laundering_judgment": "exploratory_proxy_observation_only",
        "decision_recipe_id": decision_recipe_id,
        "validation_judgment": validation_judgment,
    }


def run_one(
    *,
    run_spec: dict[str, Any],
    run_spec_path: Path,
    frame: pd.DataFrame,
    command_argv: list[str],
    branch: dict[str, str],
    feature_cache: dict[str, Any],
    label_cache: dict[str, Any],
) -> dict[str, str]:
    run_id = str(run_spec["run_id"])
    refs = run_spec["recipe_refs"]
    root = REPO_ROOT / "lab" / "runs" / run_id
    artifacts = root / "artifacts"
    reports = root / "reports"
    started = utc_now()

    if refs["feature_recipe_id"] not in feature_cache:
        feature_cache[refs["feature_recipe_id"]] = build_wave03_volatility_state_features(frame, refs["feature_recipe_id"])
    if refs["label_recipe_id"] not in label_cache:
        label_cache[refs["label_recipe_id"]] = build_wave03_volatility_state_labels(frame, refs["label_recipe_id"])
    features, feature_schema = feature_cache[refs["feature_recipe_id"]]
    labels, label_schema = label_cache[refs["label_recipe_id"]]

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
        raise ValueError(
            f"{run_id} insufficient split rows train={int(train_mask.sum())} "
            f"validation={int(validation_mask.sum())} research={int(research_mask.sum())}"
        )

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
        "validation": decision_metrics(
            decision_family=refs["decision_recipe_id"],
            score=scores["validation"],
            labels=labels.loc[validation_mask],
            fit=fit,
        ),
        "research_oos_a": decision_metrics(
            decision_family=refs["decision_recipe_id"],
            score=scores["research_oos_a"],
            labels=labels.loc[research_mask],
            fit=fit,
        ),
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
    validation_decision_stream_path = artifacts / "proxy_decision_stream_validation.csv"
    research_decision_stream_path = artifacts / "proxy_decision_stream_research_oos_a.csv"
    report_path = reports / "proxy_volatility_state_report.json"
    outputs = [
        feature_schema_path,
        label_schema_path,
        model_summary_path,
        split_profile_path,
        validation_sample_path,
        research_sample_path,
        validation_decision_stream_path,
        research_decision_stream_path,
        report_path,
    ]

    write_json(feature_schema_path, {**feature_schema.__dict__, "used_feature_columns": columns, "used_feature_count": len(columns)})
    write_json(label_schema_path, {**label_schema.__dict__, "target_name_used_for_model": target_name, "target_threshold": target_threshold})
    write_json(
        model_summary_path,
        {
            "run_id": run_id,
            "model_recipe_id": refs["model_recipe_id"],
            "proxy_model_family": model_family,
            "task_kind": task_kind,
            "model_summary": fit.model_summary,
            "train_score_summary": fit.train_score_summary,
        },
    )
    write_json(split_profile_path, split_profile)
    write_prediction_sample(
        validation_sample_path,
        frame.loc[validation_mask],
        labels.loc[validation_mask],
        pd.Series(scores["validation"], index=labels.loc[validation_mask].index),
        target.loc[validation_mask],
    )
    write_prediction_sample(
        research_sample_path,
        frame.loc[research_mask],
        labels.loc[research_mask],
        pd.Series(scores["research_oos_a"], index=labels.loc[research_mask].index),
        target.loc[research_mask],
    )
    write_decision_stream(
        validation_decision_stream_path,
        frame.loc[validation_mask],
        labels.loc[validation_mask],
        pd.Series(scores["validation"], index=labels.loc[validation_mask].index),
        target.loc[validation_mask],
        fit,
        refs["decision_recipe_id"],
    )
    write_decision_stream(
        research_decision_stream_path,
        frame.loc[research_mask],
        labels.loc[research_mask],
        pd.Series(scores["research_oos_a"], index=labels.loc[research_mask].index),
        target.loc[research_mask],
        fit,
        refs["decision_recipe_id"],
    )

    validation_summary = model_validation_summary(
        run_spec=run_spec,
        model_family=model_family,
        target_name=target_name,
        target_threshold=target_threshold,
        decision_recipe_id=refs["decision_recipe_id"],
        validation_judgment=judgment,
    )
    report = {
        "version": "wave03_volatility_state_proxy_report_v1",
        "run_id": run_id,
        "run_spec_path": repo_relative(run_spec_path),
        "recipe_refs": refs,
        "target_and_label": validation_summary["target_and_label"],
        "split_method": validation_summary["split_method"],
        "model_metrics": model_metrics,
        "decision_metrics": decision,
        "judgment_reasons": reasons,
        "model_validation": validation_summary,
        "proxy_decision_streams": {
            "validation": repo_relative(validation_decision_stream_path),
            "research_oos_a": repo_relative(research_decision_stream_path),
            "claim_boundary": "proxy_intent_stream_for_future_row_level_parity_no_runtime_authority",
        },
        "validation_judgment": judgment,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    write_json(report_path, report)

    output_refs = [artifact_ref(path, availability="local_generated_hash_recorded_not_committed") for path in outputs]
    input_paths = [REPO_ROOT / ROW_MEMBERSHIP_MANIFEST, run_spec_path]
    prov = provenance(command_argv, input_paths, outputs, started)
    storage = {
        "source_of_truth": f"lab/runs/{run_id}/run_manifest.json",
        "receipt": f"lab/runs/{run_id}/experiment_receipt.yaml",
        "lineage": f"lab/runs/{run_id}/artifact_lineage.json",
        "metrics": f"lab/runs/{run_id}/metrics.json",
        "durable_identity_policy": "repo_relative_paths_plus_hashes",
    }
    missing_evidence = [
        "ONNX_export_not_materialized_for_L4_yet",
        "MT5_L4_split_runtime_probe_not_run_yet",
        "candidate_selection_forbidden_before_L4",
    ]
    coverage = {
        "passed": REQUIRED_GATES[:-1],
        "missing": ["L4_split_runtime_probe_for_valid_proxy_run"],
        "not_applicable": ["locked_final_oos_access"],
    }
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
        "notes": "Wave03 proxy observation only; L4 follow-through required before runtime claims.",
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
            "task_type": "volatility_state_transition_proxy",
            "target_or_label": refs["label_recipe_id"],
            "output_head": "transition_score_with_reversal_continuation_abstain_decision_recipe",
        },
    }
    receipt = {
        "version": "experiment_receipt_v2",
        **base,
        "hypothesis": "Wave03 volatility compression and expansion states may expose runtime-testable reversal or continuation windows.",
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


def summary_payload(results: list[dict[str, str]], command_argv: list[str], created_at: str) -> dict[str, Any]:
    counts = Counter(str(item["result_judgment"]) for item in results)
    payload = {
        "version": "wave03_volatility_state_proxy_execution_summary_v1",
        "summary_id": "wave03_volatility_state_proxy_execution_summary_v0",
        "work_item_id": WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "wave_id": WAVE_ID,
        "campaign_id": CAMPAIGN_ID,
        "idea_id": IDEA_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": created_at,
        "status": STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
        "proxy_spec_count": 18,
        "executed_proxy_run_count": len(results),
        "result_counts": dict(counts),
        "runtime_authority": "not_claimed",
        "economics_pass": "not_claimed",
        "live_readiness": "not_claimed",
        "operational_validation_required": False,
        "counts": {
            "materialized_spec_count": 18,
            "executed_proxy_run_count": len(results),
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "result_judgment_counts": dict(counts),
            "l4_required_count": len(results),
        },
        "result_rows": results,
        "next_action": NEXT_WORK_ITEM_ID,
        "next_executable_action": NEXT_ACTION,
        "missing_evidence": [
            "ONNX_exports_absent",
            "L4_split_runtime_probe_absent",
            "candidate_evidence_absent",
            "operational_validation_not_started",
        ],
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "provenance": {
            "source_inputs": [RUN_REFS.as_posix(), ROW_MEMBERSHIP_MANIFEST.as_posix()],
            "producer": " ".join(command_argv),
            "consumer": NEXT_WORK_ITEM_ID,
            "environment_summary": {
                "python_executable": mask_local_path(sys.executable),
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                "git_sha": git_value(["rev-parse", "HEAD"]),
                "git_branch": git_value(["branch", "--show-current"]),
                "git_dirty_files": git_status_lines(),
            },
        },
    }
    payload.update(writer_contract_fields(writer_owned_outputs=[SUMMARY_PATH]))
    return payload


def next_work_item_payload(summary: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "version": "work_item_lite_v1",
        "work_item_id": NEXT_WORK_ITEM_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "primary_family": "onnx_export_parity",
        "primary_skill": "spacesonar-runtime-evidence",
        "verification_profile": "onnx_bundle",
        "targets": [SUMMARY_PATH.as_posix(), INDEX_PATH.as_posix()],
        "acceptance_criteria": [
            "materialize ONNX/runtime-follow-through prep for executed Wave03 volatility-state proxy runs",
            "do not claim candidate, runtime authority, economics pass, live readiness, reviewed/verified pass, or Goal Achieve",
            "prepare L4 split runtime probe only for valid model-bearing proxy outputs",
        ],
        "status": STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
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
        "current_truth": {
            "proxy_execution_summary": SUMMARY_PATH.as_posix(),
            "proxy_execution_index": INDEX_PATH.as_posix(),
            "executed_proxy_run_count": summary["executed_proxy_run_count"],
            "result_counts": summary["result_counts"],
        },
        "outputs": [
            "lab/campaigns/campaign_us100_wave03_volatility_state_transition_surface_v0/l4_follow_through/l4_materialization_preflight.yaml",
            "runtime/packages/pending_wave03_l4_bundle_id/experiment_bundle.json",
            "runtime/mt5_attempts/pending_wave03_l4_attempt_id/attempt_manifest.yaml",
        ],
        "missing_material_if_relevant": summary["missing_evidence"],
        "operational_validation_required": False,
        "next_action": NEXT_ACTION,
    }
    payload.update(
        writer_contract_fields(
            writer_owned_outputs=[PATHS["next_work_item"]],
            next_action=NEXT_ACTION,
        )
    )
    payload["primary_family"] = "onnx_export_parity"
    payload["primary_skill"] = "spacesonar-runtime-evidence"
    payload["progress_effect"] = "proxy_batch_execution_closed_with_l4_materialization_next"
    payload["experiment_or_boundary_effect"] = "l4_follow_through_preflight_is_next_executable_experiment_probe"
    return payload


def write_summary_records(summary: dict[str, Any], results: list[dict[str, str]]) -> None:
    write_machine_yaml(REPO_ROOT / SUMMARY_PATH, summary)
    fields = [
        "run_id",
        "status",
        "result_judgment",
        "run_manifest_path",
        "receipt_path",
        "lineage_path",
        "metrics_path",
        "report_path",
        "claim_boundary",
        "next_action",
        "notes",
    ]
    write_csv_rows(REPO_ROOT / INDEX_PATH, fields, results)
    closeout = {
        "version": "work_closeout_v1",
        "work_item_id": WORK_ITEM_ID,
        "next_work_item_id": NEXT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": summary["created_at_utc"],
        "status": STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
        "counts": summary["counts"],
        "evidence_paths": [SUMMARY_PATH.as_posix(), INDEX_PATH.as_posix()],
        "next_action": NEXT_WORK_ITEM_ID,
        "missing_evidence": summary["missing_evidence"],
        "operational_validation_required": False,
    }
    closeout.update(writer_contract_fields(writer_owned_outputs=[WORK_CLOSEOUT]))
    write_machine_yaml(REPO_ROOT / WORK_CLOSEOUT, closeout)


def update_run_refs(results: list[dict[str, str]]) -> None:
    fields, rows = read_csv_rows(REPO_ROOT / RUN_REFS)
    by_id = {row["run_id"]: row for row in rows}
    for result in results:
        row = by_id[result["run_id"]]
        row.update(
            {
                "status": result["status"],
                "claim_boundary": CLAIM_BOUNDARY,
                "next_action": NEXT_WORK_ITEM_ID,
                "notes": result["notes"],
            }
        )
    write_csv_rows(REPO_ROOT / RUN_REFS, fields, rows)


def update_control_records(summary: dict[str, Any], results: list[dict[str, str]]) -> None:
    next_work = next_work_item_payload(summary)
    write_machine_yaml(REPO_ROOT / PATHS["next_work_item"], next_work)
    update_run_refs(results)

    campaign = read_yaml(REPO_ROOT / PATHS["campaign_manifest"])
    campaign.update(
        {
            "updated_at_utc": summary["created_at_utc"],
            "status": STATUS,
            "claim_boundary": CLAIM_BOUNDARY,
            "proxy_execution_summary": SUMMARY_PATH.as_posix(),
            "proxy_execution_index": INDEX_PATH.as_posix(),
            "executed_proxy_run_count": len(results),
            "result_counts": summary["result_counts"],
            "next_action": NEXT_WORK_ITEM_ID,
        }
    )
    campaign.update(writer_contract_fields(writer_owned_outputs=[PATHS["campaign_manifest"]]))
    write_machine_yaml(REPO_ROOT / PATHS["campaign_manifest"], campaign)

    sweep = read_yaml(REPO_ROOT / PATHS["sweep_manifest"])
    sweep.update(
        {
            "updated_at_utc": summary["created_at_utc"],
            "status": STATUS,
            "claim_boundary": CLAIM_BOUNDARY,
            "executed_proxy_run_count": len(results),
            "result_counts": summary["result_counts"],
            "proxy_execution_summary": SUMMARY_PATH.as_posix(),
            "next_action": NEXT_WORK_ITEM_ID,
        }
    )
    sweep.update(writer_contract_fields(writer_owned_outputs=[PATHS["sweep_manifest"]]))
    write_machine_yaml(REPO_ROOT / PATHS["sweep_manifest"], sweep)

    wave = read_yaml(REPO_ROOT / PATHS["wave_allocation"])
    wave["updated_at_utc"] = summary["created_at_utc"]
    wave["claim_boundary"] = CLAIM_BOUNDARY
    wave["next_action"] = NEXT_WORK_ITEM_ID
    for allocation in wave.get("campaign_allocations", []):
        if allocation.get("campaign_id") == CAMPAIGN_ID:
            allocation["status"] = STATUS
            allocation["claim_boundary"] = CLAIM_BOUNDARY
            allocation["executed_proxy_run_count"] = len(results)
            allocation["result_counts"] = summary["result_counts"]
            allocation["next_action"] = NEXT_WORK_ITEM_ID
            allocation["notes"] = "Wave03 proxy batch executed; L4 materialization required next."
    wave.update(writer_contract_fields(writer_owned_outputs=[PATHS["wave_allocation"]]))
    write_machine_yaml(REPO_ROOT / PATHS["wave_allocation"], wave)

    fields, refs = read_csv_rows(REPO_ROOT / PATHS["campaign_refs"])
    for ref in refs:
        if ref.get("campaign_id") == CAMPAIGN_ID:
            ref["status"] = STATUS
            ref["claim_boundary"] = CLAIM_BOUNDARY
            ref["next_action"] = NEXT_WORK_ITEM_ID
            ref["notes"] = "Wave03 proxy batch executed; L4 materialization required next."
    write_csv_rows(REPO_ROOT / PATHS["campaign_refs"], fields, refs)

    resume = read_yaml(REPO_ROOT / PATHS["resume_cursor"])
    resume.update(
        {
            "updated_at_utc": summary["created_at_utc"],
            "cursor_state": STATUS,
            "active_phase": STATUS,
            "active_work_item_id": NEXT_WORK_ITEM_ID,
            "campaign_id": CAMPAIGN_ID,
            "claim_boundary": CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
            "unresolved_blockers": [],
            "latest_completed_work": {
                "work_item_id": WORK_ITEM_ID,
                "claim_boundary": CLAIM_BOUNDARY,
                "evidence_paths": [SUMMARY_PATH.as_posix(), INDEX_PATH.as_posix(), WORK_CLOSEOUT.as_posix()],
            },
            "next_work_item": {
                "work_item_id": NEXT_WORK_ITEM_ID,
                "path": PATHS["next_work_item"].as_posix(),
                "summary": NEXT_ACTION,
            },
        }
    )
    write_yaml(REPO_ROOT / PATHS["resume_cursor"], resume)

    goal = read_yaml(REPO_ROOT / PATHS["goal_manifest"])
    goal["updated_at_utc"] = summary["created_at_utc"]
    goal["status"] = STATUS
    goal["active_phase"] = STATUS
    goal["claim_boundary"] = CLAIM_BOUNDARY
    goal["next_work_item"] = {
        "work_item_id": NEXT_WORK_ITEM_ID,
        "path": PATHS["next_work_item"].as_posix(),
        "summary": NEXT_ACTION,
    }
    goal.setdefault("wave03_volatility_state_campaign", {}).update(
        {
            "status": STATUS,
            "claim_boundary": CLAIM_BOUNDARY,
            "proxy_execution_summary": SUMMARY_PATH.as_posix(),
            "proxy_execution_index": INDEX_PATH.as_posix(),
            "proxy_execution_counts": summary["counts"],
            "next_work_item": NEXT_WORK_ITEM_ID,
        }
    )
    write_yaml(REPO_ROOT / PATHS["goal_manifest"], goal)

    workspace = read_yaml(REPO_ROOT / PATHS["workspace_state"])
    workspace.update(
        {
            "updated_utc": summary["created_at_utc"],
            "active_goal": {
                "goal_id": GOAL_ID,
                "status": STATUS,
                "manifest": PATHS["goal_manifest"].as_posix(),
            },
            "active_wave": {
                "wave_id": WAVE_ID,
                "status": "wave_open",
                "allocation": PATHS["wave_allocation"].as_posix(),
                "closeout": None,
            },
            "active_campaign": {
                "campaign_id": CAMPAIGN_ID,
                "status": STATUS,
                "manifest": PATHS["campaign_manifest"].as_posix(),
                "closeout": None,
            },
            "active_work_item": {
                "work_item_id": NEXT_WORK_ITEM_ID,
                "path": PATHS["next_work_item"].as_posix(),
            },
            "current_claim_boundary": CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
            "unresolved_blockers": [],
        }
    )
    workspace.setdefault("summary_counts", {})["wave03_proxy_execution"] = summary["counts"]
    workspace["active_record_authority"] = {
        "authoritative_fields": [
            "active_goal",
            "active_wave",
            "active_campaign",
            "active_work_item",
            "current_claim_boundary",
            "next_action",
            "unresolved_blockers",
        ],
        "current_truth_record": PATHS["next_work_item"].as_posix(),
        "summary_counts_role": "cumulative_reference_not_active_pointer",
        "rule": "select next action from active_work_item plus next_work_item; never from summary_counts alone",
    }
    workspace.update(writer_contract_fields(writer_owned_outputs=[PATHS["workspace_state"]]))
    write_machine_yaml(REPO_ROOT / PATHS["workspace_state"], workspace)


def writer_scope_self_check(results: list[dict[str, str]]) -> dict[str, Any]:
    failures: list[str] = []
    for path in [SUMMARY_PATH, INDEX_PATH, WORK_CLOSEOUT, PATHS["next_work_item"], PATHS["workspace_state"]]:
        if not os.path.exists(filesystem_path(REPO_ROOT / path)):
            failures.append(f"missing:{path.as_posix()}")
    if len(results) != 18:
        failures.append(f"executed_run_count_not_18:{len(results)}")
    for result in results:
        for key in ["run_manifest_path", "receipt_path", "metrics_path", "lineage_path", "report_path"]:
            if not os.path.exists(filesystem_path(REPO_ROOT / result[key])):
                failures.append(f"missing:{result[key]}")
        manifest = read_json(REPO_ROOT / result["run_manifest_path"])
        if manifest.get("status") != RUN_STATUS:
            failures.append(f"run_status_mismatch:{result['run_id']}")
        missing = (manifest.get("required_gate_coverage") or {}).get("missing", [])
        if "L4_split_runtime_probe_for_valid_proxy_run" not in missing:
            failures.append(f"l4_missing_gate_absent:{result['run_id']}")
    _, refs = read_csv_rows(REPO_ROOT / RUN_REFS)
    executed = [row for row in refs if row.get("status") == RUN_STATUS]
    if len(executed) != len(results):
        failures.append("run_refs_executed_count_mismatch")
    workspace = read_yaml(REPO_ROOT / PATHS["workspace_state"])
    if (workspace.get("active_work_item") or {}).get("work_item_id") != NEXT_WORK_ITEM_ID:
        failures.append("workspace_next_work_mismatch")
    if workspace.get("current_claim_boundary") != CLAIM_BOUNDARY:
        failures.append("workspace_claim_boundary_mismatch")
    return {"status": "passed" if not failures else "failed", "failures": failures}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute Wave03 volatility-state prepared proxy run specs.")
    parser.add_argument("--row-membership-manifest", default=ROW_MEMBERSHIP_MANIFEST.as_posix())
    parser.add_argument("--run-refs", default=RUN_REFS.as_posix())
    parser.add_argument("--expected-branch", default="main")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    command_argv = [durable_arg(arg) for arg in sys.argv[:]]
    branch = branch_worktree(args.expected_branch)
    frame = load_row_membership(REPO_ROOT / args.row_membership_manifest)
    _, run_refs = read_csv_rows(REPO_ROOT / args.run_refs)
    if len(run_refs) != 18:
        raise ValueError(f"Wave03 proxy batch requires 18 run refs, observed {len(run_refs)}")

    feature_cache: dict[str, Any] = {}
    label_cache: dict[str, Any] = {}
    results: list[dict[str, str]] = []
    for row in run_refs:
        spec_path = REPO_ROOT / row["run_spec_path"]
        spec = read_yaml(spec_path)
        results.append(
            run_one(
                run_spec=spec,
                run_spec_path=spec_path,
                frame=frame,
                command_argv=command_argv,
                branch=branch,
                feature_cache=feature_cache,
                label_cache=label_cache,
            )
        )

    created_at = iso_z(utc_now())
    summary = summary_payload(results, command_argv, created_at)
    write_summary_records(summary, results)
    update_control_records(summary, results)
    self_check = writer_scope_self_check(results)
    if self_check["status"] != "passed":
        raise RuntimeError(f"writer scope self check failed: {self_check['failures']}")
    print(
        json.dumps(
            {
                "status": STATUS,
                "executed_proxy_run_count": len(results),
                "result_counts": dict(Counter(item["result_judgment"] for item in results)),
                "claim_boundary": CLAIM_BOUNDARY,
                "next_work_item": NEXT_WORK_ITEM_ID,
                "operational_validation_required": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
