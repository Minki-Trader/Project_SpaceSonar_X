from __future__ import annotations

import argparse
import csv
import json
import math
import platform
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import foundation.pipelines.materialize_wave02_cost_risk_holding_first_batch_specs as spec_writer
from foundation.features.wave02_cost_risk_holding_features import build_wave02_cost_risk_holding_features
from foundation.labels.wave02_cost_risk_holding_labels import build_wave02_cost_risk_holding_labels
from foundation.training.wave01_event_barrier_models import (
    decision_metrics,
    diagnostic_metrics,
    fit_proxy_model,
    judge_proxy_result,
    score_model,
)


GOAL_ID = spec_writer.GOAL_ID
WAVE_ID = spec_writer.WAVE_ID
CAMPAIGN_ID = spec_writer.CAMPAIGN_ID
SURFACE_ID = spec_writer.SURFACE_ID
SWEEP_ID = spec_writer.SWEEP_ID
WORK_ITEM_ID = "work_wave02_cost_risk_holding_execute_proxy_batch_v0"
PARENT_WORK_ITEM_ID = spec_writer.WORK_ITEM_ID
NEXT_WORK_ITEM_ID = "work_wave02_cost_risk_holding_l4_materialization_preflight_v0"

STATUS = "wave02_cost_risk_holding_proxy_batch_executed_l4_required"
RUN_STATUS = "executed_proxy_observation_l4_required"
NEXT_STATUS = "wave02_cost_risk_holding_l4_materialization_preflight_pending"
CLAIM_BOUNDARY = (
    "wave02_cost_risk_holding_proxy_observation_l4_required_no_candidate_no_runtime_authority_"
    "no_economics_pass_no_live_readiness_no_goal_achieve"
)
NEXT_CLAIM_BOUNDARY = (
    "wave02_cost_risk_holding_l4_materialization_pending_no_candidate_no_runtime_authority_"
    "no_economics_pass_no_live_readiness_no_goal_achieve"
)

ROW_MEMBERSHIP_MANIFEST = Path("lab/campaigns/campaign_us100_task_surface_scout_v0/row_membership/row_membership_manifest.yaml")
SUMMARY_PATH = spec_writer.CAMPAIGN_DIR / "proxy_execution_summary.yaml"
INDEX_PATH = spec_writer.CAMPAIGN_DIR / "proxy_execution_index.csv"
WORK_CLOSEOUT = Path("lab/goals") / GOAL_ID / f"{WORK_ITEM_ID}_closeout.yaml"

FORBIDDEN_CLAIMS = spec_writer.FORBIDDEN_CLAIMS

MODEL_FAMILY_BY_VARIANT = {
    "linear_rank_scout": "logistic_or_linear_rank_scout",
    "tree_scout": "tree_or_boosted_onnx_feasible_scout",
}


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


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON mapping")
    return payload


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        yaml.dump(jsonable(payload), handle, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=False)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(jsonable(payload), handle, indent=2, ensure_ascii=True)
        handle.write("\n")


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
            writer.writerow({field: serialize_csv(row.get(field, "")) for field in fieldnames})


def serialize_csv(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ";".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(jsonable(value), sort_keys=True, separators=(",", ":"))
    return str(value)


def upsert_csv_row(path: Path, key: str, row: dict[str, Any]) -> None:
    fields, rows = read_csv_rows(path)
    for field in row:
        if field not in fields:
            fields.append(field)
    serialized = {field: serialize_csv(row.get(field, "")) for field in fields}
    for index, existing in enumerate(rows):
        if existing.get(key) == str(row[key]):
            merged = dict(existing)
            merged.update(serialized)
            rows[index] = merged
            break
    else:
        rows.append(serialized)
    write_csv_rows(path, fields, rows)


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [jsonable(item) for item in value]
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def sha256(path: Path) -> str:
    return spec_writer.sha256(path)


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


def load_row_membership(path: Path) -> pd.DataFrame:
    manifest = load_yaml(path)
    csv_info = manifest["row_membership"]["full_csv"]
    csv_path = REPO_ROOT / csv_info["path"]
    if not csv_path.exists():
        raise FileNotFoundError(f"row membership CSV missing: {csv_info['path']}")
    observed = sha256(csv_path)
    if observed != csv_info["sha256"]:
        raise RuntimeError(f"row membership hash mismatch expected={csv_info['sha256']} observed={observed}")
    frame = pd.read_csv(csv_path)
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
        raise ValueError("no usable Wave02 cost/risk/holding feature columns")
    return columns


def build_model_target(labels: pd.DataFrame, train_mask: pd.Series) -> tuple[pd.Series, str, str, float | None]:
    raw = labels["target_binary_raw"].astype(float)
    train_raw = raw.loc[train_mask].dropna()
    if len(set(train_raw.astype(int).tolist())) >= 2:
        return raw, "classification", "target_binary_raw", None
    continuous = labels["target_continuous"].astype(float)
    threshold = float(continuous.loc[train_mask].quantile(0.60))
    return (continuous >= threshold).astype(float), "classification", "target_continuous_train_q60", threshold


def model_family(axis_values: dict[str, Any]) -> str:
    value = str(axis_values["model_variant"])
    family = MODEL_FAMILY_BY_VARIANT.get(value)
    if not family:
        raise ValueError(f"unsupported Wave02 cost/risk/holding model_variant: {value}")
    return family


def write_prediction_sample(path: Path, frame: pd.DataFrame, labels: pd.DataFrame, scores: pd.Series, target: pd.Series) -> None:
    sample = pd.DataFrame(
        {
            "model_row_key": frame["model_row_key"],
            "primary_split_role": frame["primary_split_role"],
            "close": frame["close"],
            "future_return": labels["future_return"],
            "future_abs_return_atr": labels["future_abs_return_atr"],
            "cost_return_proxy": labels["cost_return_proxy"],
            "target": target,
            "side_label": labels["side_label"],
            "score": scores,
        }
    )
    sample = sample.replace([np.inf, -np.inf], np.nan).dropna(subset=["score"]).head(200)
    path.parent.mkdir(parents=True, exist_ok=True)
    sample.to_csv(path, index=False, lineterminator="\n")


def artifact_ref(path: Path, *, availability: str = "present_hash_recorded") -> dict[str, Any]:
    return {
        "path": path.resolve().relative_to(REPO_ROOT.resolve()).as_posix(),
        "sha256": sha256(path),
        "size_bytes": path.stat().st_size,
        "availability": availability,
    }


def run_one(manifest_path: Path, frame: pd.DataFrame, command_argv: list[str]) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    run_id = str(manifest["run_id"])
    axis_values = manifest["axis_values"]
    root = manifest_path.parent
    artifacts = root / "artifacts"
    reports = root / "reports"

    features, feature_schema = build_wave02_cost_risk_holding_features(
        frame,
        manifest["recipes"]["feature_recipe_id"],
        str(axis_values["feature_variant"]),
    )
    labels, label_schema = build_wave02_cost_risk_holding_labels(
        frame,
        manifest["recipes"]["label_recipe_id"],
        str(axis_values["label_variant"]),
    )
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
            f"{run_id} insufficient rows train={int(train_mask.sum())} "
            f"validation={int(validation_mask.sum())} research={int(research_mask.sum())}"
        )

    columns = usable_feature_columns(features, train_mask)
    family = model_family(axis_values)
    x = features[columns]
    fit = fit_proxy_model(
        x,
        target,
        train_mask,
        model_family=family,
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
            decision_family=str(axis_values["decision_variant"]),
            score=scores["validation"],
            labels=labels.loc[validation_mask],
            fit=fit,
        ),
        "research_oos_a": decision_metrics(
            decision_family=str(axis_values["decision_variant"]),
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
    report_path = reports / "proxy_cost_risk_holding_report.json"
    metrics_path = root / "metrics.json"
    lineage_path = root / "artifact_lineage.json"
    receipt_path = root / "experiment_receipt.yaml"

    write_json(feature_schema_path, {**feature_schema.__dict__, "used_feature_columns": columns, "used_feature_count": len(columns)})
    write_json(label_schema_path, {**label_schema.__dict__, "target_name_used_for_model": target_name, "target_threshold": target_threshold})
    write_json(
        model_summary_path,
        {
            "run_id": run_id,
            "model_variant": axis_values["model_variant"],
            "proxy_model_family": family,
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

    model_validation = {
        "model_family": {"model_variant": axis_values["model_variant"], "proxy_model_family": family},
        "target_and_label": {
            "label_recipe_id": manifest["recipes"]["label_recipe_id"],
            "label_variant": axis_values["label_variant"],
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
        "threshold_knife_edge_check": "thresholds recorded_for_L4_follow_through_not_used_for_selection",
        "segment_or_regime_stability_check": "validation_and_research_oos_a_recorded_separately",
        "trade_concentration_check": "trade_count_and_density_recorded_no_economics_claim",
        "wfo_or_window_dispersion": "split_set_v0_primary_windows_only_WFO_missing_claim_lowered",
        "proxy_runtime_laundering_check": "proxy_only_L4_required_no_runtime_authority",
        "risk_stop_check": "runtime_stop_hold_execution_missing_until_L4",
        "comparison_baseline": ["no_trade_baseline_reference_only", "closed_wave02_momentum_ret_1_negative_memory_reference_only"],
        "anti_authority_laundering_judgment": "exploratory_proxy_observation_only",
        "validation_judgment": judgment,
    }
    report = {
        "version": "wave02_cost_risk_holding_proxy_report_v1",
        "run_id": run_id,
        "axis_values": axis_values,
        "model_metrics": model_metrics,
        "decision_metrics": decision,
        "judgment_reasons": reasons,
        "model_validation": model_validation,
        "result_judgment": judgment,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    write_json(report_path, report)

    outputs = [
        feature_schema_path,
        label_schema_path,
        model_summary_path,
        split_profile_path,
        validation_sample_path,
        research_sample_path,
        report_path,
    ]
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
        "missing_evidence": [
            "ONNX_export_not_materialized_for_L4_yet",
            "MT5_L4_split_runtime_probe_not_run_yet",
            "candidate_selection_forbidden_before_L4",
        ],
    }
    lineage = {
        "version": "artifact_lineage_v2",
        "run_id": run_id,
        "source_inputs": [
            artifact_ref(REPO_ROOT / ROW_MEMBERSHIP_MANIFEST),
            artifact_ref(manifest_path),
        ],
        "producer": {
            "type": "script",
            "identity": "foundation/pipelines/run_wave02_cost_risk_holding_proxy_batch.py",
            "command": " ".join(command_argv),
        },
        "artifact_paths": [artifact_ref(path, availability="local_generated_hash_recorded") for path in outputs],
        "availability": "present_hash_recorded",
        "lineage_judgment": "usable_proxy_observation_lineage_L4_missing",
        "claim_boundary": CLAIM_BOUNDARY,
    }
    receipt = {
        "version": "experiment_receipt_v2",
        "run_id": run_id,
        "status": RUN_STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
        "source_inputs": [ROW_MEMBERSHIP_MANIFEST.as_posix(), manifest_path.relative_to(REPO_ROOT).as_posix()],
        "producer": " ".join(command_argv),
        "consumer": NEXT_WORK_ITEM_ID,
        "artifact_paths": [path.relative_to(REPO_ROOT).as_posix() for path in [metrics_path, lineage_path, report_path]],
        "artifact_hashes": {},
        "model_validation": model_validation,
        "sample_scope": split_profile,
        "result_judgment": judgment,
        "missing_evidence": metrics["missing_evidence"],
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "environment_summary": {
            "python_executable": spec_writer.open_writer.redact_path(sys.executable),
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            **git_state(),
        },
    }
    manifest.update(
        {
            "status": RUN_STATUS,
            "executed_at_utc": utc_now(),
            "primary_family": "model_training",
            "primary_skill": "spacesonar-model-validation",
            "id_chain": {
                "goal_id": manifest.get("active_goal_id"),
                "wave_id": manifest.get("wave_id"),
                "campaign_id": manifest.get("campaign_id"),
                "idea_id": manifest.get("idea_id"),
                "hypothesis_id": manifest.get("hypothesis_id"),
                "surface_id": manifest.get("surface_id"),
                "sweep_id": manifest.get("sweep_id"),
                "run_id": run_id,
                "artifact_id": None,
                "bundle_id": None,
                "candidate_id": None,
            },
            "storage_contract": {
                "source_of_truth": manifest_path.relative_to(REPO_ROOT).as_posix(),
                "receipt": receipt_path.relative_to(REPO_ROOT).as_posix(),
                "lineage": lineage_path.relative_to(REPO_ROOT).as_posix(),
                "metrics": metrics_path.relative_to(REPO_ROOT).as_posix(),
                "campaign_run_refs": spec_writer.PATHS["run_refs"].as_posix(),
                "durable_identity_policy": "repo_relative_paths_only",
            },
            "result_judgment": judgment,
            "metrics_path": metrics_path.relative_to(REPO_ROOT).as_posix(),
            "lineage_path": lineage_path.relative_to(REPO_ROOT).as_posix(),
            "report_path": report_path.relative_to(REPO_ROOT).as_posix(),
            "model_validation": model_validation,
            "runtime_learning_probe_decision": {
                "required": True,
                "decision": "run_required_next",
                "target_level": "L4_split_runtime_probe",
                "lowered_claim_if_not_run": "proxy_observation_only_no_runtime_authority_no_economics_pass_no_candidate",
                "follow_up_work_item_id": NEXT_WORK_ITEM_ID,
            },
            "required_gate_coverage": {
                "passed": [
                    "run_manifest",
                    "experiment_receipt",
                    "storage_contract_check",
                    "runtime_learning_probe_decision",
                    "proxy_runtime_parity_decision",
                    "final_claim_guard",
                ],
                "missing": ["L4_split_runtime_probe_for_valid_proxy_run"],
                "not_applicable": ["locked_final_oos_b_access"],
            },
            "claim_boundary": CLAIM_BOUNDARY,
            "next_action": NEXT_WORK_ITEM_ID,
        }
    )
    write_json(manifest_path, manifest)
    lineage["source_inputs"] = [
        artifact_ref(REPO_ROOT / ROW_MEMBERSHIP_MANIFEST),
        artifact_ref(manifest_path),
    ]
    write_json(metrics_path, metrics)
    write_json(lineage_path, lineage)
    write_yaml(receipt_path, receipt)

    return {
        "run_id": run_id,
        "status": RUN_STATUS,
        "result_judgment": judgment,
        "run_manifest_path": manifest_path.relative_to(REPO_ROOT).as_posix(),
        "receipt_path": receipt_path.relative_to(REPO_ROOT).as_posix(),
        "lineage_path": lineage_path.relative_to(REPO_ROOT).as_posix(),
        "metrics_path": metrics_path.relative_to(REPO_ROOT).as_posix(),
        "report_path": report_path.relative_to(REPO_ROOT).as_posix(),
        "claim_boundary": CLAIM_BOUNDARY,
        "next_action": NEXT_WORK_ITEM_ID,
        "notes": ";".join(reasons),
    }


def summary_payload(results: list[dict[str, Any]], command_argv: list[str]) -> dict[str, Any]:
    counts = Counter(str(item["result_judgment"]) for item in results)
    return {
        "version": "wave02_cost_risk_holding_proxy_execution_summary_v1",
        "summary_id": "wave02_cost_risk_holding_proxy_execution_summary_v0",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "wave_id": WAVE_ID,
        "campaign_id": CAMPAIGN_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": utc_now(),
        "status": STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
        "primary_family": "model_training",
        "primary_skill": "spacesonar-model-validation",
        "support_skills": ["spacesonar-evidence-provenance"],
        "executed_proxy_run_count": len(results),
        "result_counts": dict(counts),
        "runtime_authority": "not_claimed",
        "economics_pass": "not_claimed",
        "live_readiness": "not_claimed",
        "counts": {
            "executed_proxy_run_count": len(results),
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "result_judgment_counts": dict(counts),
            "l4_required_count": len(results),
        },
        "result_rows": results,
        "next_action": NEXT_WORK_ITEM_ID,
        "missing_evidence": [
            "ONNX_exports_absent",
            "L4_split_runtime_probe_absent",
            "candidate_evidence_absent",
            "operational_validation_not_started",
        ],
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "provenance": {
            "source_inputs": [spec_writer.FIRST_BATCH_MANIFEST.as_posix(), spec_writer.PATHS["run_refs"].as_posix()],
            "producer": " ".join(command_argv),
            "consumer": NEXT_WORK_ITEM_ID,
            "environment_summary": {
                "python_executable": spec_writer.open_writer.redact_path(sys.executable),
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                **git_state(),
            },
        },
    }


def next_work_item() -> dict[str, Any]:
    return {
        "version": "work_item_lite_v1",
        "work_item_id": NEXT_WORK_ITEM_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "primary_family": "onnx_export_parity",
        "primary_skill": "spacesonar-runtime-evidence",
        "verification_profile": "onnx_bundle",
        "targets": [SUMMARY_PATH.as_posix(), INDEX_PATH.as_posix()],
        "acceptance_criteria": [
            "materialize ONNX/runtime-follow-through prep for executed cost/risk/holding proxy runs",
            "do not claim candidate, runtime authority, economics pass, live readiness, or Goal Achieve",
            "prepare L4 split runtime probe only for valid model-bearing proxy outputs",
        ],
        "status": NEXT_STATUS,
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "next_action": "prepare Wave02 cost/risk/holding L4 materialization and runtime attempts",
        "current_truth": {
            "proxy_execution_summary": SUMMARY_PATH.as_posix(),
            "proxy_execution_index": INDEX_PATH.as_posix(),
        },
        "unresolved_blockers": ["Wave02_cost_risk_holding_L4_materialization_not_prepared"],
        "missing_material_if_relevant": [
            "ONNX_exports_absent",
            "MT5_L4_split_runtime_probe_absent",
            "candidate_evidence_absent",
            "operational_validation_not_started",
        ],
    }


def update_run_refs(results: list[dict[str, Any]]) -> None:
    fields, rows = read_csv_rows(REPO_ROOT / spec_writer.PATHS["run_refs"])
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
    write_csv_rows(REPO_ROOT / spec_writer.PATHS["run_refs"], fields, rows)


def update_control_records(summary: dict[str, Any], results: list[dict[str, Any]]) -> None:
    write_yaml(REPO_ROOT / spec_writer.PATHS["next_work_item"], next_work_item())
    update_run_refs(results)

    campaign = load_yaml(REPO_ROOT / spec_writer.PATHS["campaign_manifest"])
    campaign["updated_at_utc"] = summary["created_at_utc"]
    campaign["status"] = STATUS
    campaign["proxy_execution_summary"] = SUMMARY_PATH.as_posix()
    campaign["next_action"] = NEXT_WORK_ITEM_ID
    write_yaml(REPO_ROOT / spec_writer.PATHS["campaign_manifest"], campaign)

    wave = load_yaml(REPO_ROOT / spec_writer.PATHS["wave_allocation"])
    wave["updated_at_utc"] = summary["created_at_utc"]
    wave["next_action"] = NEXT_WORK_ITEM_ID
    for allocation in wave.get("campaign_allocations", []):
        if allocation.get("campaign_id") == CAMPAIGN_ID:
            allocation["status"] = STATUS
            allocation["executed_proxy_run_count"] = len(results)
            allocation["next_action"] = NEXT_WORK_ITEM_ID
            allocation["notes"] = "Proxy batch executed; L4 materialization required next."
    write_yaml(REPO_ROOT / spec_writer.PATHS["wave_allocation"], wave)

    fields, refs = read_csv_rows(REPO_ROOT / spec_writer.PATHS["campaign_refs"])
    for ref in refs:
        if ref.get("campaign_id") == CAMPAIGN_ID:
            ref["status"] = STATUS
            ref["next_action"] = NEXT_WORK_ITEM_ID
            ref["notes"] = "Proxy batch executed; L4 materialization required next."
    write_csv_rows(REPO_ROOT / spec_writer.PATHS["campaign_refs"], fields, refs)

    resume = load_yaml(REPO_ROOT / spec_writer.PATHS["resume_cursor"])
    resume["updated_at_utc"] = summary["created_at_utc"]
    resume["cursor_state"] = NEXT_STATUS
    resume["active_phase"] = NEXT_STATUS
    resume["active_work_item_id"] = NEXT_WORK_ITEM_ID
    resume["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    resume["next_action"] = next_work_item()["next_action"]
    resume["unresolved_blockers"] = ["Wave02_cost_risk_holding_L4_materialization_not_prepared"]
    resume["latest_completed_work"] = {
        "work_item_id": WORK_ITEM_ID,
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_paths": [SUMMARY_PATH.as_posix(), WORK_CLOSEOUT.as_posix()],
    }
    resume["next_work_item"] = {"work_item_id": NEXT_WORK_ITEM_ID, "path": spec_writer.PATHS["next_work_item"].as_posix()}
    write_yaml(REPO_ROOT / spec_writer.PATHS["resume_cursor"], resume)

    goal = load_yaml(REPO_ROOT / spec_writer.PATHS["goal_manifest"])
    goal["updated_at_utc"] = summary["created_at_utc"]
    goal["active_phase"] = NEXT_STATUS
    campaign_state = goal.setdefault("wave02_cost_risk_holding_campaign", {})
    campaign_state["proxy_execution_summary"] = SUMMARY_PATH.as_posix()
    campaign_state["proxy_execution_counts"] = summary["counts"]
    campaign_state["next_work_item"] = NEXT_WORK_ITEM_ID
    write_yaml(REPO_ROOT / spec_writer.PATHS["goal_manifest"], goal)

    workspace = load_yaml(REPO_ROOT / spec_writer.PATHS["workspace_state"])
    workspace["updated_utc"] = summary["created_at_utc"]
    workspace["active_campaign"] = {
        "campaign_id": CAMPAIGN_ID,
        "status": STATUS,
        "manifest": spec_writer.PATHS["campaign_manifest"].as_posix(),
    }
    workspace["active_work_item"] = {"work_item_id": NEXT_WORK_ITEM_ID, "path": spec_writer.PATHS["next_work_item"].as_posix()}
    workspace["current_claim_boundary"] = NEXT_CLAIM_BOUNDARY
    workspace["next_action"] = next_work_item()["next_action"]
    workspace["unresolved_blockers"] = ["Wave02_cost_risk_holding_L4_materialization_not_prepared"]
    workspace.setdefault("summary_counts", {})["wave02_cost_risk_holding_proxy_execution"] = summary["counts"]
    write_yaml(REPO_ROOT / spec_writer.PATHS["workspace_state"], workspace)

    update_registries(summary, results)


def update_registries(summary: dict[str, Any], results: list[dict[str, Any]]) -> None:
    for path_key, registry_key in [
        ("campaign_registry", "campaign_id"),
        ("surface_registry", "surface_id"),
        ("sweep_registry", "sweep_id"),
    ]:
        path = REPO_ROOT / spec_writer.PATHS[path_key]
        fields, rows = read_csv_rows(path)
        for row in rows:
            if row.get(registry_key) in {CAMPAIGN_ID, SURFACE_ID, SWEEP_ID}:
                row["status"] = STATUS
                row["evidence_path"] = SUMMARY_PATH.as_posix()
                row["next_action"] = NEXT_WORK_ITEM_ID
                if "notes" in row:
                    row["notes"] = "Proxy batch executed; L4 materialization required next."
        write_csv_rows(path, fields, rows)

    upsert_csv_row(
        REPO_ROOT / spec_writer.PATHS["goal_registry"],
        "goal_id",
        {
            "goal_id": GOAL_ID,
            "status": "active_wave02_pre_operational_research",
            "active_phase": NEXT_STATUS,
            "next_work_item": NEXT_WORK_ITEM_ID,
            "claim_boundary": "active_goal_wave02_cost_risk_holding_l4_pending_not_goal_achieve",
        },
    )
    upsert_csv_row(
        REPO_ROOT / spec_writer.PATHS["wave_registry"],
        "wave_id",
        {
            "wave_id": WAVE_ID,
            "status": "wave02_campaign_002_proxy_executed_l4_required",
            "created_at_utc": "2026-06-27T12:15:00Z",
            "wave_path": spec_writer.PATHS["wave_allocation"].as_posix(),
            "allocation_goal": "Wave02 cost/risk/holding campaign proxy batch executed; L4 follow-through required.",
            "max_runs": "72",
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_path": SUMMARY_PATH.as_posix(),
            "next_action": NEXT_WORK_ITEM_ID,
            "notes": "No candidate, runtime authority, economics pass, live readiness, or Goal Achieve.",
        },
    )
    for result in results:
        upsert_csv_row(
            REPO_ROOT / Path("docs/registers/run_registry.csv"),
            "run_id",
            {
                "run_id": result["run_id"],
                "wave_id": WAVE_ID,
                "campaign_id": CAMPAIGN_ID,
                "idea_id": spec_writer.IDEA_ID,
                "hypothesis_id": spec_writer.HYPOTHESIS_ID,
                "surface_id": SURFACE_ID,
                "sweep_id": SWEEP_ID,
                "status": RUN_STATUS,
                "created_at_utc": summary["created_at_utc"],
                "primary_family": "model_training",
                "primary_skill": "spacesonar-model-validation",
                "manifest_path": result["run_manifest_path"],
                "receipt_path": result["receipt_path"],
                "lineage_path": result["lineage_path"],
                "metrics_path": result["metrics_path"],
                "claim_boundary": CLAIM_BOUNDARY,
                "result_judgment": result["result_judgment"],
                "required_gates": "run_manifest|experiment_receipt|storage_contract_check|runtime_learning_probe_decision|proxy_runtime_parity_decision|final_claim_guard",
                "evidence_path": result["report_path"],
                "next_action": NEXT_WORK_ITEM_ID,
                "notes": result["notes"],
            },
        )
    update_artifact_registry()


def update_artifact_registry() -> None:
    artifacts = {
        "artifact_wave02_cost_risk_holding_proxy_summary_v0": ("proxy_execution_summary", SUMMARY_PATH),
        "artifact_wave02_cost_risk_holding_proxy_index_v0": ("proxy_execution_index", INDEX_PATH),
        "artifact_wave02_cost_risk_holding_proxy_closeout_v0": ("work_closeout", WORK_CLOSEOUT),
    }
    for artifact_id, (artifact_type, path) in artifacts.items():
        full = REPO_ROOT / path
        upsert_csv_row(
            REPO_ROOT / spec_writer.PATHS["artifact_registry"],
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
                "producer_command": "python foundation/pipelines/run_wave02_cost_risk_holding_proxy_batch.py --write-control-records",
                "regeneration_command": "python foundation/pipelines/run_wave02_cost_risk_holding_proxy_batch.py --write-control-records",
                "source_of_truth": SUMMARY_PATH.as_posix(),
                "consumer": NEXT_WORK_ITEM_ID,
                "claim_boundary": CLAIM_BOUNDARY,
                "notes": f"Wave02 cost/risk/holding {artifact_type}",
            },
        )


def write_summary_records(summary: dict[str, Any], results: list[dict[str, Any]]) -> None:
    write_yaml(REPO_ROOT / SUMMARY_PATH, summary)
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
    write_yaml(
        REPO_ROOT / WORK_CLOSEOUT,
        {
            "version": "work_closeout_v1",
            "work_item_id": WORK_ITEM_ID,
            "parent_work_item_id": PARENT_WORK_ITEM_ID,
            "next_work_item_id": NEXT_WORK_ITEM_ID,
            "active_goal_id": GOAL_ID,
            "closed_at_utc": summary["created_at_utc"],
            "primary_family": "model_training",
            "primary_skill": "spacesonar-model-validation",
            "support_skills": ["spacesonar-evidence-provenance"],
            "status": STATUS,
            "claim_boundary": CLAIM_BOUNDARY,
            "counts": summary["counts"],
            "evidence_paths": [SUMMARY_PATH.as_posix(), INDEX_PATH.as_posix()],
            "next_action": NEXT_WORK_ITEM_ID,
            "missing_evidence": summary["missing_evidence"],
            "forbidden_claims": FORBIDDEN_CLAIMS,
        },
    )


def writer_scope_self_check(results: list[dict[str, Any]]) -> dict[str, Any]:
    failures: list[str] = []
    for path in [SUMMARY_PATH, INDEX_PATH, WORK_CLOSEOUT]:
        if not (REPO_ROOT / path).exists():
            failures.append(f"missing:{path.as_posix()}")
    if len(results) == 0:
        failures.append("no_results")
    for result in results:
        for key in ["run_manifest_path", "receipt_path", "metrics_path", "lineage_path", "report_path"]:
            if not (REPO_ROOT / result[key]).exists():
                failures.append(f"missing:{result[key]}")
    _, refs = read_csv_rows(REPO_ROOT / spec_writer.PATHS["run_refs"])
    executed = [row for row in refs if row.get("status") == RUN_STATUS]
    if len(executed) != len(results):
        failures.append("run_refs_executed_count_mismatch")
    workspace = load_yaml(REPO_ROOT / spec_writer.PATHS["workspace_state"])
    if (workspace.get("active_work_item") or {}).get("work_item_id") != NEXT_WORK_ITEM_ID:
        failures.append("workspace_next_work_mismatch")
    return {"status": "passed" if not failures else "failed", "failures": failures}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute Wave02 cost/risk/holding proxy batch.")
    parser.add_argument("--row-membership-manifest", default=ROW_MEMBERSHIP_MANIFEST.as_posix())
    parser.add_argument("--run-refs", default=spec_writer.PATHS["run_refs"].as_posix())
    parser.add_argument("--expected-branch", default="main")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--write-control-records", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    branch = git_value(["branch", "--show-current"])
    if branch != args.expected_branch:
        raise RuntimeError(f"branch mismatch before Wave02 proxy execution: current={branch!r} expected={args.expected_branch!r}")
    command_argv = ["python", "foundation/pipelines/run_wave02_cost_risk_holding_proxy_batch.py"]
    if args.write_control_records:
        command_argv.append("--write-control-records")
    if args.limit is not None:
        command_argv.extend(["--limit", str(args.limit)])
    fields, run_refs = read_csv_rows(REPO_ROOT / args.run_refs)
    selected = run_refs[: args.limit] if args.limit is not None else run_refs
    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "selected_run_count": len(selected),
                    "run_ids": [row["run_id"] for row in selected],
                    "claim_boundary": CLAIM_BOUNDARY,
                },
                indent=2,
            )
        )
        return 0
    frame = load_row_membership(REPO_ROOT / args.row_membership_manifest)
    results: list[dict[str, Any]] = []
    for row in selected:
        results.append(run_one(REPO_ROOT / row["run_manifest_path"], frame, command_argv))
    summary = summary_payload(results, command_argv)
    write_summary_records(summary, results)
    if args.write_control_records:
        update_control_records(summary, results)
    self_check = writer_scope_self_check(results)
    if self_check["status"] != "passed":
        print(json.dumps({"status": "writer_scope_self_check_failed", "self_check": self_check}, indent=2))
        return 1
    print(
        json.dumps(
            {
                "status": STATUS,
                "executed_proxy_run_count": len(results),
                "result_counts": dict(Counter(item["result_judgment"] for item in results)),
                "writer_scope_self_check": self_check["status"],
                "claim_boundary": CLAIM_BOUNDARY,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
