from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np
import onnx
import onnxruntime as ort
import pandas as pd
import yaml

from foundation.features.wave0_scout_features import FeatureSchema, build_wave0_features
from foundation.labels.wave0_scout_labels import LabelSchema, build_wave0_labels
from foundation.onnx.skl2onnx_adapters import convert_sklearn_pipeline_for_lab
from foundation.training.wave0_proxy_models import (
    ProxyFit,
    build_model_target,
    fit_proxy_model,
    score_model,
)


GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WORK_ITEM_ID = "work_wave0_first_batch_l4_follow_through_v0"
SUBWORK_ID = "work_wave0_l4_onnx_materialization_v0"
CAMPAIGN_ID = "campaign_us100_task_surface_scout_v0"
SWEEP_ID = "sweep_wave0_broad_surface_scout_v0"
SUMMARY_ID = "wave0_l4_onnx_materialization_summary_v0"
CLAIM_BOUNDARY = "onnx_bundle_preflight_python_parity_only_no_runtime_authority_no_candidate_no_baseline"
TARGET_OPSET = 13
PARITY_SAMPLE_ROWS = 512
PARITY_TOLERANCE = 1.0e-5

ROW_MEMBERSHIP_MANIFEST = Path("lab/campaigns/campaign_us100_task_surface_scout_v0/row_membership/row_membership_manifest.yaml")
RUN_REFS = Path("lab/campaigns/campaign_us100_task_surface_scout_v0/sweeps/sweep_wave0_broad_surface_scout_v0/run_refs.csv")
PREFLIGHT = Path("lab/campaigns/campaign_us100_task_surface_scout_v0/l4_follow_through/l4_materialization_preflight.yaml")
OUTPUT_DIR = Path("lab/campaigns/campaign_us100_task_surface_scout_v0/l4_follow_through")
SUMMARY_PATH = OUTPUT_DIR / "onnx_materialization_summary.yaml"
INDEX_PATH = OUTPUT_DIR / "onnx_materialization_index.csv"
CLOSEOUT_PATH = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/work_wave0_l4_onnx_materialization_v0_closeout.yaml")
NEXT_WORK_ITEM = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml")
RESUME_CURSOR = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml")
GOAL_MANIFEST = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml")
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")

EXPORTABLE_MODEL_FAMILIES = {
    "linear_or_ridge_rank_scout",
    "logistic_classification_scout",
    "onnx_realistic_tree_or_boosted_scout",
}


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle)


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.dump(payload, handle, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=False)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_ref(path: Path, repo_root: Path, *, availability: str = "present_hash_recorded") -> dict[str, Any]:
    if path.is_absolute():
        try:
            path = path.relative_to(repo_root)
        except ValueError as exc:
            raise ValueError(f"artifact path is outside repo root: {path}") from exc
    full = repo_root / path
    return {
        "path": path.as_posix(),
        "sha256": sha256(full),
        "size_bytes": full.stat().st_size,
        "availability": availability,
    }


def rel(path: Path, repo_root: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def redact_home(value: str) -> str:
    home = str(Path.home())
    return value.replace(home, "${USERPROFILE}").replace(home.replace("\\", "/"), "${USERPROFILE}")


def run_git(repo_root: Path, args: list[str]) -> str:
    result = subprocess.run(["git", *args], cwd=repo_root, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip()


def git_identity(repo_root: Path) -> dict[str, Any]:
    changed = [line for line in run_git(repo_root, ["status", "--short"]).splitlines() if line]
    return {
        "git_sha": run_git(repo_root, ["rev-parse", "HEAD"]),
        "branch": run_git(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"]),
        "dirty_flag": bool(changed),
        "changed_files": changed,
        "unknown_git_claim_effect": (
            "bundle_preflight_only_lower_reproducibility_claim"
            if changed
            else "clean_git_identity_recorded_for_bundle_preflight"
        ),
    }


def dependency_summary() -> dict[str, str]:
    packages = {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "sklearn": importlib.metadata.version("scikit-learn"),
        "onnx": onnx.__version__,
        "onnxruntime": ort.__version__,
        "skl2onnx": importlib.metadata.version("skl2onnx"),
        "yaml": yaml.__version__,
    }
    return packages


def load_row_membership(repo_root: Path, manifest: dict[str, Any]) -> pd.DataFrame:
    csv_info = manifest["row_membership"]["full_csv"]
    path = repo_root / csv_info["path"]
    if not path.exists():
        raise FileNotFoundError(f"row membership CSV missing: {csv_info['path']}")
    observed = sha256(path)
    if observed != csv_info["sha256"]:
        raise RuntimeError(f"row membership hash mismatch expected={csv_info['sha256']} observed={observed}")
    frame = pd.read_csv(path)
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
    base = labels["same_role_horizon_ok"].astype(bool)
    roles = frame["primary_split_role"].astype(str)
    return {
        "train": base & roles.eq("train"),
        "validation": base & roles.eq("validation"),
        "research_oos_a": base & roles.eq("research_oos_a"),
        "locked_final_oos_b": base & roles.eq("locked_final_oos_b"),
    }


def usable_feature_columns(features: pd.DataFrame, train_mask: pd.Series) -> list[str]:
    usable = [column for column in features.columns if features.loc[train_mask, column].notna().any()]
    if not usable:
        raise ValueError("all feature columns are empty in train scope")
    return usable


def bundle_id_for_run(run_manifest: dict[str, Any]) -> str:
    cell_id = str((run_manifest.get("planned_cell") or {}).get("cell_id") or run_manifest["run_id"])
    return f"bundle_{cell_id}_l4_onnx_export_v0"


def cell_from_manifest(run_manifest: dict[str, Any]) -> dict[str, Any]:
    cell = dict(run_manifest["planned_cell"])
    cell["horizon_bars"] = int(cell["horizon_bars"])
    return cell


def feature_label_for_cell(
    frame: pd.DataFrame,
    cell: dict[str, Any],
    feature_cache: dict[str, tuple[pd.DataFrame, FeatureSchema]],
    label_cache: dict[tuple[str, int], tuple[pd.DataFrame, LabelSchema]],
) -> tuple[pd.DataFrame, FeatureSchema, pd.DataFrame, LabelSchema]:
    input_family = str(cell["input_family"])
    label_key = (str(cell["target_family"]), int(cell["horizon_bars"]))
    if input_family not in feature_cache:
        feature_cache[input_family] = build_wave0_features(frame, input_family)
    if label_key not in label_cache:
        label_cache[label_key] = build_wave0_labels(frame, label_key[0], label_key[1])
    features, feature_schema = feature_cache[input_family]
    labels, label_schema = label_cache[label_key]
    return features, feature_schema, labels, label_schema


def convert_model_to_onnx(fit: ProxyFit, feature_count: int) -> tuple[bytes, list[str]]:
    result = convert_sklearn_pipeline_for_lab(
        fit.model,
        feature_count=feature_count,
        task_kind=fit.task_kind,
        target_opset=TARGET_OPSET,
    )
    return result.model.SerializeToString(), result.adapter_ids


def onnx_score(onnx_path: Path, features: np.ndarray, task_kind: str) -> np.ndarray:
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    outputs = session.run(None, {"features": features.astype(np.float32)})
    return np.asarray(outputs[0]).reshape(-1).astype(float)


def write_float_matrix_csv(path: Path, columns: list[str], values: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(values, columns=columns)
    frame.to_csv(path, index=False)


def write_score_csv(path: Path, values: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"score": values.astype(float)}).to_csv(path, index=False)


def exportable_from_preflight(preflight: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    exportable: list[str] = []
    blocked: dict[str, str] = {}
    for row in preflight.get("run_preflight", []):
        run_id = str(row["run_id"])
        model_family = str(row.get("model_family") or "")
        if model_family in EXPORTABLE_MODEL_FAMILIES:
            exportable.append(run_id)
        else:
            blocked[run_id] = "blocked_unknown_model_family_export_adapter_requires_attempted_probe"
    return exportable, blocked


def materialize_one(
    *,
    repo_root: Path,
    row_frame: pd.DataFrame,
    run_id: str,
    run_manifest_path: Path,
    row_manifest_path: Path,
    row_manifest: dict[str, Any],
    feature_cache: dict[str, tuple[pd.DataFrame, FeatureSchema]],
    label_cache: dict[tuple[str, int], tuple[pd.DataFrame, LabelSchema]],
    command_argv: list[str],
    started_at_utc: str,
) -> dict[str, Any]:
    run_manifest = load_json(run_manifest_path)
    run_root = run_manifest_path.parent
    cell = cell_from_manifest(run_manifest)
    bundle_id = bundle_id_for_run(run_manifest)
    bundle_root = repo_root / "runtime" / "packages" / bundle_id
    artifact_root = bundle_root / "artifacts"
    bundle_root.mkdir(parents=True, exist_ok=True)
    artifact_root.mkdir(parents=True, exist_ok=True)

    features, feature_schema, labels, label_schema = feature_label_for_cell(row_frame, cell, feature_cache, label_cache)
    masks = split_masks(row_frame, labels)
    train_mask = masks["train"]
    target, task_kind, target_name, target_threshold = build_model_target(
        labels,
        train_mask,
        target_family=str(cell["target_family"]),
        model_family=str(cell["model_family"]),
    )
    target_notna = target.notna()
    train_mask = train_mask & target_notna
    validation_mask = masks["validation"] & target_notna
    research_oos_mask = masks["research_oos_a"] & target_notna
    locked_mask = masks["locked_final_oos_b"] & target_notna

    columns = usable_feature_columns(features, train_mask)
    x = features[columns]
    fit = fit_proxy_model(
        x,
        target,
        train_mask,
        model_family=str(cell["model_family"]),
        target_name=target_name,
        threshold_policy=str(cell["threshold_policy"]),
        target_threshold=target_threshold,
    )

    onnx_bytes, onnx_adapter_ids = convert_model_to_onnx(fit, len(columns))
    onnx_path = artifact_root / "model.onnx"
    onnx_path.write_bytes(onnx_bytes)

    fixture_frame = x.loc[validation_mask].head(PARITY_SAMPLE_ROWS).astype("float32")
    if len(fixture_frame) == 0:
        raise RuntimeError(f"no validation rows available for parity fixture: {run_id}")
    python_scores = score_model(fit.model, fixture_frame, fit.task_kind)
    onnx_scores = onnx_score(onnx_path, fixture_frame.to_numpy(dtype=np.float32), fit.task_kind)
    abs_error = np.abs(python_scores.astype(float) - onnx_scores.astype(float))
    max_abs_error = float(np.nanmax(abs_error))
    mean_abs_error = float(np.nanmean(abs_error))
    parity_status = "passed" if max_abs_error <= PARITY_TOLERANCE else "failed"

    fixture_input_path = artifact_root / "parity_fixture_input.csv"
    expected_score_path = artifact_root / "parity_expected_score.csv"
    observed_score_path = artifact_root / "parity_onnxruntime_score.csv"
    write_float_matrix_csv(fixture_input_path, columns, fixture_frame.to_numpy(dtype=np.float32))
    write_score_csv(expected_score_path, python_scores)
    write_score_csv(observed_score_path, onnx_scores)

    feature_schema_path = repo_root / run_manifest["model_export"]["input_schema"]["feature_schema_path"]
    label_schema_path = run_root / "artifacts" / "label_schema.json"
    model_summary_path = run_root / "artifacts" / "model_summary.json"
    split_profile_path = run_root / "artifacts" / "split_profile.json"
    source_refs = [
        artifact_ref(row_manifest_path, repo_root),
        artifact_ref(RUN_REFS, repo_root),
        artifact_ref(PREFLIGHT, repo_root),
        artifact_ref(feature_schema_path.relative_to(repo_root), repo_root),
        artifact_ref(label_schema_path.relative_to(repo_root), repo_root),
        artifact_ref(model_summary_path.relative_to(repo_root), repo_root),
        artifact_ref(split_profile_path.relative_to(repo_root), repo_root),
    ]
    artifact_refs = [
        artifact_ref(onnx_path.relative_to(repo_root), repo_root, availability="local_artifact_hash_recorded"),
        artifact_ref(fixture_input_path.relative_to(repo_root), repo_root, availability="local_artifact_hash_recorded"),
        artifact_ref(expected_score_path.relative_to(repo_root), repo_root, availability="local_artifact_hash_recorded"),
        artifact_ref(observed_score_path.relative_to(repo_root), repo_root, availability="local_artifact_hash_recorded"),
    ]
    git = git_identity(repo_root)
    id_chain = dict(run_manifest.get("id_chain") or {})
    id_chain["bundle_id"] = bundle_id
    bundle_manifest = {
        "version": "experiment_bundle_v3",
        "bundle_id": bundle_id,
        "run_id": run_id,
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "source_of_truth": f"runtime/packages/{bundle_id}/experiment_bundle.json",
        "created_at_utc": utc_now(),
        "status": "onnx_exported_python_onnxruntime_parity_passed" if parity_status == "passed" else "onnx_exported_python_onnxruntime_parity_failed",
        "claim_boundary": CLAIM_BOUNDARY,
        "id_chain": id_chain,
        "dataset_id": row_manifest["dataset_id"],
        "data_source": {
            "base_frame": "US100_M5_closed_bar",
            "row_key": "us100_bar_close_time",
            "row_membership_manifest": ROW_MEMBERSHIP_MANIFEST.as_posix(),
            "row_membership_csv_sha256": row_manifest["row_membership"]["full_csv"]["sha256"],
            "time_axis": row_manifest["time_axis"],
            "sample_scope": {
                "train_rows_used_for_fit": int(train_mask.sum()),
                "validation_rows_available_for_L4": int(validation_mask.sum()),
                "research_oos_a_rows_available_for_L4": int(research_oos_mask.sum()),
                "locked_final_oos_b_rows_withheld": int(locked_mask.sum()),
            },
            "split_boundary": "train_only_fit_validation_and_research_oos_reserved_for_L4_runtime_observation",
            "locked_final_oos_b_use": "withheld_forbidden_by_default",
        },
        "feature_recipe_id": feature_schema.feature_recipe_id,
        "feature_schema_hash": feature_schema.feature_schema_hash,
        "feature_order_hash": hashlib.sha256("|".join(columns).encode("utf-8")).hexdigest(),
        "feature_schema_contract": {
            "input_family": cell["input_family"],
            "feature_count": len(columns),
            "feature_columns": columns,
            "all_nan_train_columns_dropped": [column for column in feature_schema.feature_columns if column not in columns],
            "boundary": feature_schema.boundary,
        },
        "label_recipe_id": label_schema.label_recipe_id,
        "label_id": f"{cell['target_family']}_h{cell['horizon_bars']}_{target_name}",
        "label_schema_hash": label_schema.label_schema_hash,
        "target_and_label": {
            "target_family": cell["target_family"],
            "target_name": target_name,
            "target_threshold": target_threshold,
            "target_threshold_fit_scope": "train_only" if target_threshold is not None else "not_applicable",
            "horizon_bars": int(cell["horizon_bars"]),
            "label_boundary": label_schema.boundary,
        },
        "split_id": run_manifest["data_scope"]["split_id"],
        "primary_split_id": run_manifest["data_scope"]["primary_split_id"],
        "task_surface_id": run_manifest["id_chain"]["surface_id"],
        "task_surface": run_manifest.get("task_surface"),
        "decision_use": cell["decision_family"],
        "decision_recipe_id": "decision_wave0_abstain_density_scout_v0",
        "decision_surface_id": f"{cell['decision_family']}_{cell['threshold_policy']}",
        "decision_surface": {
            "decision_family": cell["decision_family"],
            "threshold_policy": fit.threshold_policy,
            "score_low_threshold": fit.score_low_threshold,
            "score_high_threshold": fit.score_high_threshold,
            "diagnostic_only": cell["decision_family"] == "diagnostic_rank_only",
            "runtime_translation_status": "pending_strategy_tester_adapter",
        },
        "model_family": cell["model_family"],
        "model_framework": "sklearn_pipeline_skl2onnx",
        "onnx_conversion": {
            "target_opset": TARGET_OPSET,
            "adapter_ids": onnx_adapter_ids,
            "passive_block_policy": "unsupported_or_missing_adapter_requires_root_cause_probe_and_repair_attempt_before_blocked_or_discarded",
        },
        "model_opset": TARGET_OPSET,
        "model_training": {
            "fit_scope": "train_only",
            "preprocessing_fit_scope": "train_only",
            "calibration": "none",
            "selection_metric": "none_selected_materialization_follows_existing_proxy_run",
            "overfit_risk": "first_batch_multiple_surface_scout_no_selection_allowed",
            "calibration_risk": "scores_are_model_scores_not_calibrated_probabilities",
        },
        "input_schema": {
            "input_name": "features",
            "dtype": "float32",
            "shape": [None, len(columns)],
            "feature_order_hash": hashlib.sha256("|".join(columns).encode("utf-8")).hexdigest(),
            "feature_columns": columns,
        },
        "output_schema": {
            "task_kind": fit.task_kind,
            "score_semantics": "class_1_probability" if fit.task_kind == "classification" else "regression_rank_score",
            "onnx_outputs": ["score"],
            "score_extraction": "score.reshape(-1)",
            "probability_calibration_claim": False,
            "mt5_output_contract": "single_float_score_vector_shape_1_for_single_row_inference",
        },
        "onnx_path": rel(onnx_path, repo_root),
        "onnx_sha256": sha256(onnx_path),
        "onnx_size_bytes": onnx_path.stat().st_size,
        "onnx_adapter_ids": onnx_adapter_ids,
        "parser_version": "spacesonar_wave0_l4_materializer_v1",
        "runtime_contract_version": "mt5_runtime_probe_contract_v2",
        "runtime_period_profile_id": "period_profile_split_set_v0",
        "runtime_period_set_id": "split_base_anchor_v0_research_l4",
        "tester_execution_profile_id": "us100_m5_fpmarkets_tester_execution_v0",
        "python_onnxruntime_parity": {
            "status": parity_status,
            "sample_scope": "first_validation_rows_after_train_only_fit",
            "sample_rows": int(len(fixture_frame)),
            "max_abs_error": max_abs_error,
            "mean_abs_error": mean_abs_error,
            "tolerance": PARITY_TOLERANCE,
            "fixture_input": artifact_ref(fixture_input_path.relative_to(repo_root), repo_root, availability="local_artifact_hash_recorded"),
            "expected_score": artifact_ref(expected_score_path.relative_to(repo_root), repo_root, availability="local_artifact_hash_recorded"),
            "observed_score": artifact_ref(observed_score_path.relative_to(repo_root), repo_root, availability="local_artifact_hash_recorded"),
        },
        "runtime_learning_probe_decision": {
            "required": True,
            "decision": "run_required",
            "required_runtime_level": "L4_split_runtime_probe",
            "reason": "Valid proxy/model-bearing run now has ONNX bundle preflight; Strategy Tester L4 remains required.",
            "lowered_claim_if_not_run": "bundle_preflight_only_no_runtime_authority_no_economics_pass",
        },
        "proxy_runtime_parity": {
            "status": "pending_L4_strategy_tester",
            "shared_contract": [
                "US100_M5_closed_bar_base_frame",
                "us100_bar_close_time_row_key",
                "feature_order_hash",
                "train_only_fit_scope",
                "split_base_anchor_v0_research_l4",
            ],
            "known_differences": [
                "Python proxy and ONNXRuntime parity is not Strategy Tester execution",
                "MT5 EA decision timing, costs, spread, lot rounding, and no-trade semantics still pending",
            ],
            "interpretation_drift_risks": [
                "bar_close_timing",
                "feature_reconstruction_in_EA",
                "score_threshold_translation",
                "diagnostic_surface_runtime_observation_mode" if cell["decision_family"] == "diagnostic_rank_only" else "trade_decision_surface_translation",
            ],
            "minimum_reconciliation_attempt": {
                "status": "pending_MT5_L4",
                "forced_equality_required": False,
            },
            "unit_semantics": {
                "feature_input": "float32_feature_vector_in_declared_order",
                "price_units": "pending_EA_strategy_adapter",
                "point_tick_digits": "pending_EA_strategy_adapter",
                "lot_rounding": "pending_EA_strategy_adapter",
            },
            "comparison_class": "pending_L4",
            "divergence_judgment": "pending_L4",
            "prevention_memory": [
                "Do not treat ONNXRuntime parity as MT5 runtime parity.",
                "Record feature reconstruction and threshold interpretation before reusing this surface.",
                "Do not mark unsupported conversion as blocked until root cause, repair attempt, and fallback decision are recorded.",
            ],
            "follow_up_action": WORK_ITEM_ID,
            "claim_boundary": "proxy_runtime_parity_tracking_only_no_runtime_authority",
        },
        "producer_command": " ".join(command_argv),
        "environment_summary": dependency_summary(),
        "provenance": {
            "command_argv": command_argv,
            "cwd": ".",
            "python_executable": redact_home(sys.executable),
            "python_version": platform.python_version(),
            "started_at_utc": started_at_utc,
            "ended_at_utc": utc_now(),
            "input_hashes": source_refs,
            "output_hashes": artifact_refs,
            **git,
        },
        "required_gate_coverage": {
            "passed": [
                "onnx_export_smoke",
                "python_onnx_parity",
                "feature_schema_contract",
                "bundle_integrity_hash",
                "mt5_runtime_probe_contract_audit",
                "final_claim_guard",
            ]
            if parity_status == "passed"
            else ["onnx_export_smoke", "feature_schema_contract", "mt5_runtime_probe_contract_audit", "final_claim_guard"],
            "missing": ["L4_split_runtime_probe_for_valid_proxy_run", "full_period_strategy_tester_adapter"],
            "not_applicable": ["locked_final_oos_b_access"],
        },
        "missing_evidence": [
            "MT5_L4_split_runtime_probe_not_run",
            "full_period_strategy_tester_adapter_pending",
            "Strategy_Tester_report_pending",
        ],
        "next_action": "build_or_select_full_period_strategy_tester_adapter_then_execute_L4_validation_and_research_oos",
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
    bundle_path = bundle_root / "experiment_bundle.json"
    write_json(bundle_path, bundle_manifest)
    return {
        "run_id": run_id,
        "bundle_id": bundle_id,
        "cell_id": cell["cell_id"],
        "status": bundle_manifest["status"],
        "result_judgment": run_manifest.get("result_judgment"),
        "model_family": cell["model_family"],
        "task_kind": fit.task_kind,
        "decision_family": cell["decision_family"],
        "feature_count": len(columns),
        "bundle_manifest_path": rel(bundle_path, repo_root),
        "bundle_manifest_sha256": sha256(bundle_path),
        "onnx_path": rel(onnx_path, repo_root),
        "onnx_sha256": sha256(onnx_path),
        "onnx_size_bytes": onnx_path.stat().st_size,
        "onnx_adapter_ids": "|".join(onnx_adapter_ids),
        "parity_status": parity_status,
        "parity_max_abs_error": max_abs_error,
        "parity_mean_abs_error": mean_abs_error,
        "parity_sample_rows": int(len(fixture_frame)),
        "l4_status": "pending_strategy_tester_adapter",
        "claim_boundary": CLAIM_BOUNDARY,
    }


def build_blocked_rows(preflight: dict[str, Any], blocked: dict[str, str]) -> list[dict[str, Any]]:
    by_run = {str(row["run_id"]): row for row in preflight.get("run_preflight", [])}
    rows = []
    for run_id, reason in sorted(blocked.items()):
        source = by_run.get(run_id, {})
        rows.append(
            {
                "run_id": run_id,
                "bundle_id": "",
                "cell_id": run_id.replace("onnxlab_", "").replace("_surface_scout_v0", ""),
                "status": "blocked_export_adapter_required",
                "result_judgment": source.get("result_judgment"),
                "model_family": source.get("model_family"),
                "task_kind": source.get("task_kind"),
                "decision_family": source.get("decision_family"),
                "feature_count": source.get("feature_count"),
                "bundle_manifest_path": "",
                "bundle_manifest_sha256": "",
                "onnx_path": "",
                "onnx_sha256": "",
                "onnx_size_bytes": "",
                "onnx_adapter_ids": "",
                "parity_status": "not_run",
                "parity_max_abs_error": "",
                "parity_mean_abs_error": "",
                "parity_sample_rows": "",
                "l4_status": reason,
                "claim_boundary": CLAIM_BOUNDARY,
            }
        )
    return rows


def materialize(repo_root: Path, *, command_argv: list[str], started_at_utc: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    row_manifest = load_yaml(repo_root / ROW_MEMBERSHIP_MANIFEST)
    preflight = load_yaml(repo_root / PREFLIGHT)
    exportable_run_ids, blocked = exportable_from_preflight(preflight)
    run_refs = {row["run_id"]: row for row in read_csv_rows(repo_root / RUN_REFS)}
    row_frame = load_row_membership(repo_root, row_manifest)
    feature_cache: dict[str, tuple[pd.DataFrame, FeatureSchema]] = {}
    label_cache: dict[tuple[str, int], tuple[pd.DataFrame, LabelSchema]] = {}
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for run_id in exportable_run_ids:
        try:
            run_ref = run_refs[run_id]
            run_manifest_path = repo_root / run_ref["run_manifest_path"]
            results.append(
                materialize_one(
                    repo_root=repo_root,
                    row_frame=row_frame,
                    run_id=run_id,
                    run_manifest_path=run_manifest_path,
                    row_manifest_path=repo_root / ROW_MEMBERSHIP_MANIFEST,
                    row_manifest=row_manifest,
                    feature_cache=feature_cache,
                    label_cache=label_cache,
                    command_argv=command_argv,
                    started_at_utc=started_at_utc,
                )
            )
        except Exception as exc:  # noqa: BLE001 - per-run materialization failure is evidence.
            errors.append({"run_id": run_id, "error_type": type(exc).__name__, "error": str(exc)})

    blocked_rows = build_blocked_rows(preflight, blocked)
    all_rows = [*results, *blocked_rows]
    counts = Counter(str(row["status"]) for row in all_rows)
    parity_counts = Counter(str(row["parity_status"]) for row in all_rows)
    model_counts = Counter(str(row["model_family"]) for row in all_rows)
    summary = {
        "version": "wave0_l4_onnx_materialization_summary_v1",
        "summary_id": SUMMARY_ID,
        "work_item_id": WORK_ITEM_ID,
        "subwork_item_id": SUBWORK_ID,
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": utc_now(),
        "status": "completed_exportable_bundles_l4_still_pending",
        "claim_boundary": CLAIM_BOUNDARY,
        "source_inputs": {
            "row_membership_manifest": ROW_MEMBERSHIP_MANIFEST.as_posix(),
            "run_refs": RUN_REFS.as_posix(),
            "materialization_preflight": PREFLIGHT.as_posix(),
        },
        "input_hashes": [
            artifact_ref(ROW_MEMBERSHIP_MANIFEST, repo_root),
            artifact_ref(RUN_REFS, repo_root),
            artifact_ref(PREFLIGHT, repo_root),
        ],
        "counts": {
            "valid_proxy_runs_requiring_l4": len(preflight.get("run_preflight", [])),
            "exportable_bundle_count": len(results),
            "blocked_export_adapter_count": len(blocked_rows),
            "failed_materialization_count": len(errors),
            "status_counts": dict(sorted(counts.items())),
            "parity_status_counts": dict(sorted(parity_counts.items())),
            "model_family_counts": dict(sorted(model_counts.items())),
        },
        "runtime_contract_binding": {
            "required_runtime_level": "L4_split_runtime_probe",
            "period_profile_id": "period_profile_split_set_v0",
            "runtime_period_set_id": "split_base_anchor_v0_research_l4",
            "tester_execution_profile_id": "us100_m5_fpmarkets_tester_execution_v0",
            "locked_final_oos_b": "forbidden_by_default",
            "l5_rule": "if_L4_remains_promising_continue_to_L5_candidate_runtime_evidence",
        },
        "artifact_outputs": {
            "index_csv": INDEX_PATH.as_posix(),
            "bundle_manifest_paths": [row["bundle_manifest_path"] for row in results],
            "onnx_artifact_paths": [row["onnx_path"] for row in results],
        },
        "errors": errors,
        "blocked_runs": blocked_rows,
        "exported_runs": results,
        "judgment": {
            "judgment_class": "bundle_preflight",
            "materialization_ready": False,
            "runtime_authority": False,
            "economics_pass": False,
            "selected_baseline": False,
            "goal_achieve": False,
            "next_action": (
                "Build the full-period MT5 Strategy Tester adapter for exported ONNX bundles, "
                "then run L4 validation and research_oos."
            ),
        },
        "prevention_memory": [
            "Record ONNX bundle manifests separately from proxy reports before attempting L4.",
            "HistGradientBoosting export uses skl2onnx_hgb_numpy_scalar_cast_v0; keep converter adapter evidence before L4.",
            "Unsupported conversion paths require root-cause capture and at least one repair or fallback adapter attempt before blocked/discarded status.",
            "Do not count Python ONNXRuntime parity as MT5 L4 or economics evidence.",
        ],
        "environment": {
            "command": " ".join(command_argv),
            "command_argv": command_argv,
            "cwd": ".",
            "python_executable": redact_home(sys.executable),
            "python_version": platform.python_version(),
            "dependency_summary": dependency_summary(),
            "started_at_utc": started_at_utc,
            "ended_at_utc": utc_now(),
            **git_identity(repo_root),
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
    return summary, all_rows


def index_fieldnames() -> list[str]:
    return [
        "run_id",
        "bundle_id",
        "cell_id",
        "status",
        "result_judgment",
        "model_family",
        "task_kind",
        "decision_family",
        "feature_count",
        "bundle_manifest_path",
        "bundle_manifest_sha256",
        "onnx_path",
        "onnx_sha256",
        "onnx_size_bytes",
        "onnx_adapter_ids",
        "parity_status",
        "parity_max_abs_error",
        "parity_mean_abs_error",
        "parity_sample_rows",
        "l4_status",
        "claim_boundary",
    ]


def build_closeout(summary: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    return {
        "version": "work_closeout_v1",
        "work_item_id": SUBWORK_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "created_at_utc": summary["created_at_utc"],
        "status": "completed_exportable_onnx_bundle_preflight_l4_pending",
        "result_judgment": "inconclusive",
        "claim_boundary": CLAIM_BOUNDARY,
        "source_of_truth": SUMMARY_PATH.as_posix(),
        "evidence_paths": [SUMMARY_PATH.as_posix(), INDEX_PATH.as_posix()],
        "summary_counts": summary["counts"],
        "claim_effect": summary["judgment"],
        "next_work_item": {
            "work_item_id": WORK_ITEM_ID,
            "path": NEXT_WORK_ITEM.as_posix(),
            "required_next_action": summary["judgment"]["next_action"],
        },
        "output_hashes": [
            artifact_ref(SUMMARY_PATH, repo_root),
            artifact_ref(INDEX_PATH, repo_root),
        ],
        "forbidden_claims": summary["forbidden_claims"],
    }


def ensure_list_item(values: list[Any], item: Any) -> None:
    if item not in values:
        values.append(item)


def upsert_artifact_registry(repo_root: Path, summary: dict[str, Any], closeout: dict[str, Any]) -> None:
    registry_path = repo_root / ARTIFACT_REGISTRY
    rows = read_csv_rows(registry_path)
    fieldnames = [
        "artifact_id",
        "run_id",
        "bundle_id",
        "attempt_id",
        "artifact_type",
        "path_or_uri",
        "sha256",
        "size_bytes",
        "availability",
        "producer_command",
        "regeneration_command",
        "source_of_truth",
        "consumer",
        "claim_boundary",
        "notes",
    ]
    by_id = {row["artifact_id"]: row for row in rows}

    def put(row: dict[str, str]) -> None:
        path = repo_root / row["path_or_uri"]
        if path.exists():
            row["sha256"] = sha256(path)
            row["size_bytes"] = str(path.stat().st_size)
        by_id[row["artifact_id"]] = {key: row.get(key, "") for key in fieldnames}

    producer = "foundation/pipelines/materialize_wave0_l4_onnx_bundles.py --write-control-records"
    regen = f"python {producer}"
    put(
        {
            "artifact_id": "artifact_wave0_l4_onnx_materialization_summary_v0",
            "run_id": "",
            "bundle_id": "",
            "attempt_id": "",
            "artifact_type": "onnx_materialization_summary",
            "path_or_uri": SUMMARY_PATH.as_posix(),
            "availability": "present_hash_recorded",
            "producer_command": producer,
            "regeneration_command": regen,
            "source_of_truth": SUMMARY_PATH.as_posix(),
            "consumer": WORK_ITEM_ID,
            "claim_boundary": CLAIM_BOUNDARY,
            "notes": "bundle preflight only; L4 Strategy Tester execution remains pending",
        }
    )
    put(
        {
            "artifact_id": "artifact_wave0_l4_onnx_materialization_index_v0",
            "run_id": "",
            "bundle_id": "",
            "attempt_id": "",
            "artifact_type": "onnx_materialization_index",
            "path_or_uri": INDEX_PATH.as_posix(),
            "availability": "present_hash_recorded",
            "producer_command": producer,
            "regeneration_command": regen,
            "source_of_truth": SUMMARY_PATH.as_posix(),
            "consumer": WORK_ITEM_ID,
            "claim_boundary": CLAIM_BOUNDARY,
            "notes": "run to bundle materialization index",
        }
    )
    put(
        {
            "artifact_id": "artifact_wave0_l4_onnx_materialization_closeout_v0",
            "run_id": "",
            "bundle_id": "",
            "attempt_id": "",
            "artifact_type": "work_closeout",
            "path_or_uri": CLOSEOUT_PATH.as_posix(),
            "availability": "present_hash_recorded",
            "producer_command": producer,
            "regeneration_command": regen,
            "source_of_truth": CLOSEOUT_PATH.as_posix(),
            "consumer": WORK_ITEM_ID,
            "claim_boundary": CLAIM_BOUNDARY,
            "notes": "subwork closeout; parent L4 follow-through remains open",
        }
    )
    for row in summary["exported_runs"]:
        put(
            {
                "artifact_id": f"artifact_{row['bundle_id']}_manifest_v0",
                "run_id": row["run_id"],
                "bundle_id": row["bundle_id"],
                "attempt_id": "",
                "artifact_type": "experiment_bundle",
                "path_or_uri": row["bundle_manifest_path"],
                "availability": "present_hash_recorded",
                "producer_command": producer,
                "regeneration_command": regen,
                "source_of_truth": row["bundle_manifest_path"],
                "consumer": WORK_ITEM_ID,
                "claim_boundary": CLAIM_BOUNDARY,
                "notes": "ONNX bundle manifest with Python ONNXRuntime parity; MT5 L4 pending",
            }
        )
        put(
            {
                "artifact_id": f"artifact_{row['bundle_id']}_onnx_v0",
                "run_id": row["run_id"],
                "bundle_id": row["bundle_id"],
                "attempt_id": "",
                "artifact_type": "onnx_model",
                "path_or_uri": row["onnx_path"],
                "availability": "local_artifact_hash_recorded",
                "producer_command": producer,
                "regeneration_command": regen,
                "source_of_truth": row["bundle_manifest_path"],
                "consumer": WORK_ITEM_ID,
                "claim_boundary": CLAIM_BOUNDARY,
                "notes": "ignored ONNX artifact tracked by hash; regenerate from bundle materializer",
            }
        )
    write_csv(registry_path, list(by_id.values()), fieldnames)


def update_control_records(repo_root: Path, summary: dict[str, Any], closeout: dict[str, Any]) -> None:
    next_work = load_yaml(repo_root / NEXT_WORK_ITEM)
    current_truth = next_work.setdefault("current_truth", {})
    current_truth["onnx_materialization_summary"] = SUMMARY_PATH.as_posix()
    current_truth["onnx_materialization_status"] = summary["status"]
    current_truth["onnx_materialization_counts"] = summary["counts"]
    next_work["status"] = "planned_next_l4_strategy_tester_adapter_after_onnx_materialization"
    next_work["missing_material_if_relevant"] = [
        "full_period_strategy_tester_adapter_absent_for_current_proxy_runs",
        "L4_validation_and_research_oos_reports_absent",
    ]
    next_work["next_action"] = summary["judgment"]["next_action"]
    write_yaml(repo_root / NEXT_WORK_ITEM, next_work)

    resume = load_yaml(repo_root / RESUME_CURSOR)
    resume["updated_at_utc"] = summary["created_at_utc"]
    truth_sources = resume.setdefault("current_truth_sources", [])
    ensure_list_item(truth_sources, SUMMARY_PATH.as_posix())
    ensure_list_item(truth_sources, INDEX_PATH.as_posix())
    resume["latest_completed_work"] = {
        "work_item_id": SUBWORK_ID,
        "result_judgment": "inconclusive",
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_paths": [SUMMARY_PATH.as_posix(), CLOSEOUT_PATH.as_posix()],
    }
    resume["next_work_item"] = {"work_item_id": WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()}
    write_yaml(repo_root / RESUME_CURSOR, resume)

    goal = load_yaml(repo_root / GOAL_MANIFEST)
    goal["updated_at_utc"] = summary["created_at_utc"]
    wave_spec = goal.setdefault("program_budgets", {}).setdefault("current_wave0_spec", {})
    wave_spec["l4_onnx_materialization_summary"] = SUMMARY_PATH.as_posix()
    wave_spec["l4_onnx_materialization_status"] = summary["status"]
    wave_spec["l4_onnx_materialization_counts"] = summary["counts"]
    write_yaml(repo_root / GOAL_MANIFEST, goal)

    workspace = load_yaml(repo_root / WORKSPACE_STATE)
    workspace["updated_utc"] = summary["created_at_utc"]
    claims = workspace.setdefault("current_claims", {})
    claims["wave0_l4_onnx_materialization_summary"] = SUMMARY_PATH.as_posix()
    claims["wave0_l4_onnx_materialization_status"] = summary["status"]
    claims["wave0_l4_onnx_materialization_counts"] = summary["counts"]
    write_yaml(repo_root / WORKSPACE_STATE, workspace)

    upsert_artifact_registry(repo_root, summary, closeout)


def write_outputs(repo_root: Path, summary: dict[str, Any], rows: list[dict[str, Any]], *, write_control_records: bool) -> None:
    write_yaml(repo_root / SUMMARY_PATH, summary)
    write_csv(repo_root / INDEX_PATH, rows, index_fieldnames())
    closeout = build_closeout(summary, repo_root)
    write_yaml(repo_root / CLOSEOUT_PATH, closeout)
    if write_control_records:
        update_control_records(repo_root, summary, closeout)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--write-control-records", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    started_at = utc_now()
    command_argv = ["python", "foundation/pipelines/materialize_wave0_l4_onnx_bundles.py"]
    if args.write_control_records:
        command_argv.append("--write-control-records")
    summary, rows = materialize(repo_root, command_argv=command_argv, started_at_utc=started_at)
    write_outputs(repo_root, summary, rows, write_control_records=args.write_control_records)
    print(
        json.dumps(
            {
                "status": summary["status"],
                "summary": SUMMARY_PATH.as_posix(),
                "exportable_bundle_count": summary["counts"]["exportable_bundle_count"],
                "blocked_export_adapter_count": summary["counts"]["blocked_export_adapter_count"],
                "failed_materialization_count": summary["counts"]["failed_materialization_count"],
            },
            indent=2,
        )
    )
    return 0 if summary["counts"]["failed_materialization_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
