from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import onnx
import onnxruntime as ort
import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import foundation.pipelines.materialize_wave01_event_barrier_l4_onnx_bundles as base
from foundation.features.wave01_session_transition_features import (
    FeatureSchema,
    build_wave01_session_transition_features,
)
from foundation.labels.wave01_session_transition_labels import (
    LabelSchema,
    build_wave01_session_transition_labels,
)
from foundation.training.wave01_event_barrier_models import (
    ProxyFit,
    build_model_target,
    fit_proxy_model,
    score_model,
)


GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WORK_ITEM_ID = "work_wave01_session_transition_l4_materialization_preflight_v0"
SUBWORK_ID = "work_wave01_session_transition_l4_onnx_materialization_v0"
CAMPAIGN_ID = "campaign_us100_session_transition_regime_surface_v0"
SWEEP_ID = "sweep_us100_session_transition_broad_v0"
SUMMARY_ID = "wave01_session_transition_l4_onnx_materialization_summary_v0"
CLAIM_BOUNDARY = (
    "wave01_session_transition_onnx_bundle_preflight_python_parity_only_"
    "no_runtime_authority_no_candidate_no_baseline"
)
TARGET_OPSET = 13
PARITY_SAMPLE_ROWS = 512
PARITY_TOLERANCE = 1.0e-5

ROW_MEMBERSHIP_MANIFEST = Path(
    "lab/campaigns/campaign_us100_task_surface_scout_v0/row_membership/row_membership_manifest.yaml"
)
MATRIX = Path("lab/campaigns/campaign_us100_session_transition_regime_surface_v0/first_batch_matrix.csv")
RUN_REFS = Path(
    "lab/campaigns/campaign_us100_session_transition_regime_surface_v0/"
    "sweeps/sweep_us100_session_transition_broad_v0/run_refs.csv"
)
OUTPUT_DIR = Path("lab/campaigns/campaign_us100_session_transition_regime_surface_v0/l4_follow_through")
SUMMARY_PATH = OUTPUT_DIR / "onnx_materialization_summary.yaml"
INDEX_PATH = OUTPUT_DIR / "onnx_materialization_index.csv"
CLOSEOUT_PATH = Path(
    "lab/goals/goal_us100_onnx_forward_boundary_v0/"
    "work_wave01_session_transition_l4_onnx_materialization_v0_closeout.yaml"
)
NEXT_WORK_ITEM = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml")
RESUME_CURSOR = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml")
GOAL_MANIFEST = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml")
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")
GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")

RUNTIME_PERIOD_PROFILE_ID = "period_profile_split_set_v0"
RUNTIME_PERIOD_SET_ID = "split_base_anchor_v0_research_l4"
TESTER_EXECUTION_PROFILE_ID = "us100_m5_fpmarkets_tester_execution_v0"

EXPORTABLE_MODEL_FAMILIES = {
    "logistic_or_linear_rank_scout",
    "tree_or_boosted_onnx_feasible_scout",
    "small_mlp_secondary_only",
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


def read_matrix(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return {row["spec_id"]: row for row in csv.DictReader(handle)}


def axis_from_matrix_row(row: dict[str, str]) -> dict[str, Any]:
    axis: dict[str, Any] = dict(row)
    axis["horizon_bars"] = int(axis["horizon_bars"])
    return axis


def cell_id_for_axis(axis: dict[str, Any]) -> str:
    return str(axis["spec_id"])


def bundle_id_for_axis(axis: dict[str, Any]) -> str:
    return f"bundle_{cell_id_for_axis(axis)}_l4_onnx_export_v0"


def label_contract(axis: dict[str, Any]) -> dict[str, Any]:
    return {
        "label_surface": axis["label_surface"],
        "horizon_bars": int(axis["horizon_bars"]),
        "session_anchor": axis["session_anchor"],
        "transition_window_bars": axis["transition_window_bars"],
        "regime_label": axis["regime_label"],
    }


def label_cache_key(axis: dict[str, Any]) -> tuple[str, int, str, str, str]:
    return (
        str(axis["label_surface"]),
        int(axis["horizon_bars"]),
        str(axis["session_anchor"]),
        str(axis["transition_window_bars"]),
        str(axis["regime_label"]),
    )


def feature_label_for_axis(
    frame: pd.DataFrame,
    axis: dict[str, Any],
    feature_cache: dict[str, tuple[pd.DataFrame, FeatureSchema]],
    label_cache: dict[tuple[str, int, str, str, str], tuple[pd.DataFrame, LabelSchema]],
) -> tuple[pd.DataFrame, FeatureSchema, pd.DataFrame, LabelSchema]:
    feature_family = str(axis["feature_family"])
    key = label_cache_key(axis)
    if feature_family not in feature_cache:
        feature_cache[feature_family] = build_wave01_session_transition_features(frame, feature_family)
    if key not in label_cache:
        label_cache[key] = build_wave01_session_transition_labels(frame, label_contract(axis))
    features, feature_schema = feature_cache[feature_family]
    labels, label_schema = label_cache[key]
    return features, feature_schema, labels, label_schema


def convert_model_to_onnx(fit: ProxyFit, feature_count: int) -> tuple[bytes, list[str]]:
    result = base.convert_sklearn_pipeline_for_lab(
        fit.model,
        feature_count=feature_count,
        task_kind=fit.task_kind,
        target_opset=TARGET_OPSET,
    )
    return result.model.SerializeToString(), result.adapter_ids


def onnx_score(onnx_path: Path, features: np.ndarray) -> np.ndarray:
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    outputs = session.run(None, {"features": features.astype(np.float32)})
    return np.asarray(outputs[0]).reshape(-1).astype(float)


def write_float_matrix_csv(path: Path, columns: list[str], values: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(values, columns=columns).to_csv(path, index=False)


def write_score_csv(path: Path, values: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"score": values.astype(float)}).to_csv(path, index=False)


def materialize_one(
    *,
    repo_root: Path,
    row_frame: pd.DataFrame,
    matrix_rows: dict[str, dict[str, str]],
    run_ref: dict[str, str],
    row_manifest_path: Path,
    row_manifest: dict[str, Any],
    feature_cache: dict[str, tuple[pd.DataFrame, FeatureSchema]],
    label_cache: dict[tuple[str, int, str, str, str], tuple[pd.DataFrame, LabelSchema]],
    command_argv: list[str],
    started_at_utc: str,
) -> dict[str, Any]:
    run_id = run_ref["run_id"]
    run_manifest_path = repo_root / run_ref["run_manifest_path"]
    run_manifest = base.load_json(run_manifest_path)
    run_root = run_manifest_path.parent
    axis = axis_from_matrix_row(matrix_rows[run_ref["run_spec_id"]])
    cell_id = cell_id_for_axis(axis)
    bundle_id = bundle_id_for_axis(axis)
    bundle_root = repo_root / "runtime" / "packages" / bundle_id
    artifact_root = bundle_root / "artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)

    features, feature_schema, labels, label_schema = feature_label_for_axis(
        row_frame,
        axis,
        feature_cache,
        label_cache,
    )
    masks = base.split_masks(row_frame, labels)
    train_mask = masks["train"]
    target, task_kind, target_name, target_threshold = build_model_target(
        labels,
        train_mask,
        label_surface=str(axis["label_surface"]),
        model_family=str(axis["model_family"]),
        model_task=str(axis["model_task"]),
    )
    target_notna = target.notna()
    train_mask = train_mask & target_notna
    validation_mask = masks["validation"] & target_notna
    research_oos_mask = masks["research_oos_a"] & target_notna
    locked_mask = masks["locked_final_oos_b"] & target_notna

    columns = base.usable_feature_columns(features, train_mask)
    x = features[columns]
    fit = fit_proxy_model(
        x,
        target,
        train_mask,
        model_family=str(axis["model_family"]),
        task_kind=task_kind,
        target_name=target_name,
        threshold_policy=str(axis["threshold_policy"]),
        target_threshold=target_threshold,
    )

    onnx_bytes, onnx_adapter_ids = convert_model_to_onnx(fit, len(columns))
    onnx_path = artifact_root / "model.onnx"
    onnx_path.write_bytes(onnx_bytes)

    fixture_frame = x.loc[validation_mask].head(PARITY_SAMPLE_ROWS).astype("float32")
    if len(fixture_frame) == 0:
        raise RuntimeError(f"no validation rows available for parity fixture: {run_id}")
    python_scores = score_model(fit.model, fixture_frame, fit.task_kind)
    onnx_scores = onnx_score(onnx_path, fixture_frame.to_numpy(dtype=np.float32))
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

    source_refs = [
        base.artifact_ref(MATRIX, repo_root),
        base.artifact_ref(row_manifest_path, repo_root),
        base.artifact_ref(RUN_REFS, repo_root),
        base.artifact_ref(run_root / "artifacts" / "feature_schema.json", repo_root),
        base.artifact_ref(run_root / "artifacts" / "label_schema.json", repo_root),
        base.artifact_ref(run_root / "artifacts" / "model_summary.json", repo_root),
        base.artifact_ref(run_root / "artifacts" / "split_profile.json", repo_root),
    ]
    artifact_refs = [
        base.artifact_ref(onnx_path, repo_root, availability="local_artifact_hash_recorded"),
        base.artifact_ref(fixture_input_path, repo_root, availability="local_artifact_hash_recorded"),
        base.artifact_ref(expected_score_path, repo_root, availability="local_artifact_hash_recorded"),
        base.artifact_ref(observed_score_path, repo_root, availability="local_artifact_hash_recorded"),
    ]
    id_chain = dict(run_manifest.get("id_chain") or {})
    id_chain["cell_id"] = cell_id
    id_chain["bundle_id"] = bundle_id
    output_semantics = "class_1_probability" if task_kind == "classification" else "regression_score_or_rank"

    bundle_manifest = {
        "version": "experiment_bundle_v3",
        "bundle_id": bundle_id,
        "run_id": run_id,
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "source_of_truth": f"runtime/packages/{bundle_id}/experiment_bundle.json",
        "created_at_utc": base.utc_now(),
        "status": (
            "onnx_exported_python_onnxruntime_parity_passed"
            if parity_status == "passed"
            else "onnx_exported_python_onnxruntime_parity_failed"
        ),
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
            "input_family": axis["feature_family"],
            "feature_count": len(columns),
            "feature_columns": columns,
            "all_nan_train_columns_dropped": [
                column for column in feature_schema.feature_columns if column not in columns
            ],
            "boundary": feature_schema.boundary,
            "feature_count_policy": "variable_declared_per_run_no_fixed_count",
        },
        "label_recipe_id": label_schema.label_recipe_id,
        "label_id": f"{axis['label_surface']}_h{axis['horizon_bars']}_{target_name}",
        "label_schema_hash": label_schema.label_schema_hash,
        "target_and_label": {
            **label_contract(axis),
            "target_name": target_name,
            "target_threshold": target_threshold,
            "target_threshold_fit_scope": "train_only" if target_threshold is not None else "not_applicable",
            "label_boundary": label_schema.boundary,
        },
        "split_id": "split_set_v0",
        "primary_split_id": "split_base_anchor_v0",
        "task_surface_id": id_chain.get("surface_id", "surface_us100_session_transition_regime_surface_v0"),
        "task_surface": run_manifest.get("task_surface"),
        "decision_use": axis["decision_family"],
        "decision_recipe_id": "decision_wave01_session_transition_abstain_v0",
        "decision_surface_id": f"{axis['decision_family']}_{axis['threshold_policy']}",
        "decision_surface": {
            "decision_family": axis["decision_family"],
            "holding_policy": axis["holding_policy"],
            "risk_policy": axis["risk_policy"],
            "threshold_policy": fit.threshold_policy,
            "score_low_threshold": fit.score_low_threshold,
            "score_high_threshold": fit.score_high_threshold,
            "diagnostic_only": "diagnostic" in str(axis["decision_family"]) or "no_trade" in str(axis["decision_family"]),
            "claim_boundary": "score_thresholds_fit_on_train_only_no_runtime_execution_claim",
        },
        "model": {
            "framework": "sklearn",
            "family": axis["model_family"],
            "task_kind": task_kind,
            "target_name": fit.target_name,
            "model_task": axis["model_task"],
            "model_summary": fit.model_summary,
            "train_score_summary": fit.train_score_summary,
            "fit_scope": "train_split_only",
            "hyperparameter_tuning": "none",
            "selection": "none_first_batch_l4_follow_through",
        },
        "onnx": {
            "opset": TARGET_OPSET,
            "path": f"runtime/packages/{bundle_id}/artifacts/model.onnx",
            "sha256": base.sha256(onnx_path),
            "size_bytes": onnx_path.stat().st_size,
            "adapter_ids": onnx_adapter_ids,
            "ir_version": onnx.load(str(onnx_path)).ir_version,
        },
        "onnx_path": f"runtime/packages/{bundle_id}/artifacts/model.onnx",
        "input_schema": {
            "input_name": "features",
            "dtype": "float32",
            "shape": [1, len(columns)],
            "feature_order_hash": hashlib.sha256("|".join(columns).encode("utf-8")).hexdigest(),
        },
        "output_schema": {
            "output_name": "score",
            "shape": [1, 1],
            "semantics": output_semantics,
            "mt5_output_contract": "single_float_score",
        },
        "python_onnxruntime_parity": {
            "status": parity_status,
            "sample_rows": int(len(fixture_frame)),
            "max_abs_error": max_abs_error,
            "mean_abs_error": mean_abs_error,
            "tolerance": PARITY_TOLERANCE,
            "fixture_input": base.rel(fixture_input_path, repo_root),
            "expected_score": base.rel(expected_score_path, repo_root),
            "observed_score": base.rel(observed_score_path, repo_root),
            "claim_boundary": "python_onnxruntime_parity_only_not_MT5_runtime_authority",
        },
        "runtime_contract_binding": {
            "required_runtime_level": "L4_split_runtime_probe",
            "period_profile_id": RUNTIME_PERIOD_PROFILE_ID,
            "runtime_period_set_id": RUNTIME_PERIOD_SET_ID,
            "required_period_roles": ["validation", "research_oos"],
            "tester_execution_profile_id": TESTER_EXECUTION_PROFILE_ID,
            "locked_final_oos_b": "excluded_forbidden_by_default",
            "l5_rule": "if_L4_remains_promising_continue_to_L5_candidate_runtime_evidence",
        },
        "proxy_runtime_parity": {
            "status": "bundle_preflight_only_MT5_reconciliation_pending",
            "known_differences": [
                "Python proxy uses vectorized New_York session rendering from exported timestamps.",
                "MT5 score probe reconstructs feature values from Strategy Tester closed bars and server-time rates.",
                "This bundle does not prove trading execution or economics.",
            ],
            "minimum_reconciliation_attempt": "L4_score_probe_validation_and_research_oos_required_next",
            "unit_semantics": {
                "session_boundary": "America_New_York_rendered_from_exported_UTC_timestamp; MT5 runtime rendering pending",
                "price_distance": "not directly traded in this score probe; risk policy conversion remains pending for trading EA",
                "lot": "tester profile records 0.02 fixed lot but score probe is non-trading",
            },
            "comparison_class": "pending_L4",
            "divergence_judgment": "pending_L4",
            "prevention_memory": [
                "Do not force proxy and MT5 session semantics equal; record any boundary drift before judgment.",
            ],
        },
        "source_inputs": source_refs,
        "artifacts": artifact_refs,
        "producer": {
            "entrypoint": "foundation/pipelines/materialize_wave01_session_transition_l4_onnx_bundles.py",
            "command": " ".join(command_argv),
            "command_argv": command_argv,
            "started_at_utc": started_at_utc,
            "ended_at_utc": base.utc_now(),
            "python_executable": base.redact_home(sys.executable),
            "python_version": platform.python_version(),
            "dependency_summary": {
                **base.dependency_summary(),
                "onnx": onnx.__version__,
                "onnxruntime": ort.__version__,
                "yaml": yaml.__version__,
            },
            **base.git_identity(repo_root),
        },
        "missing_evidence": [
            "MT5_L4_validation_report_pending",
            "MT5_L4_research_oos_report_pending",
            "Strategy_Tester_report_pending",
            "L4_attempt_preparation_pending",
        ],
        "next_action": "prepare_L4_validation_and_research_oos_attempts",
        "forbidden_claims": FORBIDDEN_CLAIMS,
    }
    bundle_path = bundle_root / "experiment_bundle.json"
    base.write_json(bundle_path, bundle_manifest)
    return {
        "run_id": run_id,
        "run_spec_id": axis["spec_id"],
        "cell_id": cell_id,
        "bundle_id": bundle_id,
        "status": bundle_manifest["status"],
        "result_judgment": run_ref.get("result_judgment", ""),
        "model_family": axis["model_family"],
        "task_kind": fit.task_kind,
        "decision_family": axis["decision_family"],
        "session_anchor": axis["session_anchor"],
        "feature_count": len(columns),
        "bundle_manifest_path": base.rel(bundle_path, repo_root),
        "bundle_manifest_sha256": base.sha256(bundle_path),
        "onnx_path": base.rel(onnx_path, repo_root),
        "onnx_sha256": base.sha256(onnx_path),
        "onnx_size_bytes": onnx_path.stat().st_size,
        "onnx_adapter_ids": "|".join(onnx_adapter_ids),
        "parity_status": parity_status,
        "parity_max_abs_error": max_abs_error,
        "parity_mean_abs_error": mean_abs_error,
        "parity_sample_rows": int(len(fixture_frame)),
        "l4_status": "pending_strategy_tester_attempt_preparation",
        "claim_boundary": CLAIM_BOUNDARY,
    }


def materialize(
    repo_root: Path,
    *,
    command_argv: list[str],
    started_at_utc: str,
    limit: int | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    row_manifest_path = repo_root / ROW_MEMBERSHIP_MANIFEST
    row_manifest = base.load_yaml(row_manifest_path)
    matrix_rows = read_matrix(repo_root / MATRIX)
    run_refs = base.read_csv_rows(repo_root / RUN_REFS)
    if limit is not None:
        run_refs = run_refs[:limit]
    row_frame = base.load_row_membership(repo_root, row_manifest)
    feature_cache: dict[str, tuple[pd.DataFrame, FeatureSchema]] = {}
    label_cache: dict[tuple[str, int, str, str, str], tuple[pd.DataFrame, LabelSchema]] = {}
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for run_ref in run_refs:
        axis = axis_from_matrix_row(matrix_rows[run_ref["run_spec_id"]])
        if str(axis["model_family"]) not in EXPORTABLE_MODEL_FAMILIES:
            errors.append(
                {
                    "run_id": run_ref["run_id"],
                    "error_type": "unsupported_model_family_reproduction_required",
                    "error": str(axis["model_family"]),
                }
            )
            continue
        try:
            results.append(
                materialize_one(
                    repo_root=repo_root,
                    row_frame=row_frame,
                    matrix_rows=matrix_rows,
                    run_ref=run_ref,
                    row_manifest_path=row_manifest_path,
                    row_manifest=row_manifest,
                    feature_cache=feature_cache,
                    label_cache=label_cache,
                    command_argv=command_argv,
                    started_at_utc=started_at_utc,
                )
            )
        except Exception as exc:  # noqa: BLE001 - per-run failures are evidence.
            errors.append({"run_id": run_ref["run_id"], "error_type": type(exc).__name__, "error": str(exc)})

    counts = Counter(str(row["status"]) for row in results)
    parity_counts = Counter(str(row["parity_status"]) for row in results)
    model_counts = Counter(str(row["model_family"]) for row in results)
    task_counts = Counter(str(row["task_kind"]) for row in results)
    status = (
        "completed_exportable_bundles_l4_attempt_preparation_required"
        if not errors and len(results) == len(run_refs) and all(row["parity_status"] == "passed" for row in results)
        else "completed_with_materialization_errors_l4_still_required"
    )
    summary = {
        "version": "wave01_session_transition_l4_onnx_materialization_summary_v1",
        "summary_id": SUMMARY_ID,
        "work_item_id": WORK_ITEM_ID,
        "subwork_item_id": SUBWORK_ID,
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": base.utc_now(),
        "status": status,
        "attempt_depth": "thin_first_pass_limit" if limit is not None else "bounded_full_l4_materialization_batch",
        "verification_depth": "python_onnxruntime_parity_plus_bundle_hashes_not_MT5",
        "claim_boundary": CLAIM_BOUNDARY,
        "source_inputs": {
            "row_membership_manifest": ROW_MEMBERSHIP_MANIFEST.as_posix(),
            "first_batch_matrix": MATRIX.as_posix(),
            "run_refs": RUN_REFS.as_posix(),
        },
        "input_hashes": [
            base.artifact_ref(ROW_MEMBERSHIP_MANIFEST, repo_root),
            base.artifact_ref(MATRIX, repo_root),
            base.artifact_ref(RUN_REFS, repo_root),
        ],
        "counts": {
            "valid_proxy_runs_requiring_l4": len(run_refs),
            "exportable_bundle_count": len(results),
            "failed_materialization_count": len(errors),
            "status_counts": dict(sorted(counts.items())),
            "parity_status_counts": dict(sorted(parity_counts.items())),
            "model_family_counts": dict(sorted(model_counts.items())),
            "task_kind_counts": dict(sorted(task_counts.items())),
        },
        "runtime_contract_binding": {
            "required_runtime_level": "L4_split_runtime_probe",
            "period_profile_id": RUNTIME_PERIOD_PROFILE_ID,
            "runtime_period_set_id": RUNTIME_PERIOD_SET_ID,
            "required_period_roles": ["validation", "research_oos"],
            "tester_execution_profile_id": TESTER_EXECUTION_PROFILE_ID,
            "locked_final_oos_b": "excluded_forbidden_by_default",
            "l5_rule": "if_L4_remains_promising_continue_to_L5_candidate_runtime_evidence",
        },
        "artifact_outputs": {
            "index_csv": INDEX_PATH.as_posix(),
            "bundle_manifest_paths": [row["bundle_manifest_path"] for row in results],
            "onnx_artifact_paths": [row["onnx_path"] for row in results],
        },
        "errors": errors,
        "exported_runs": results,
        "judgment": {
            "judgment_class": "bundle_preflight",
            "materialization_ready": False,
            "runtime_probe_completed": False,
            "runtime_authority": False,
            "economics_pass": False,
            "selected_baseline": False,
            "goal_achieve": False,
            "next_action": "Prepare L4 MT5 validation and research_oos attempts for every exported session-transition bundle.",
        },
        "try_first_evidence": {
            "status": "adapter_probe_attempted",
            "reproduction": "session-transition model families retrained and converted through current skl2onnx adapter path",
            "blocked_or_deferred_runs": [],
            "claim_effect": "no_missing_adapter_blocker_for_session_transition_onnx_materialization",
        },
        "prevention_memory": [
            "Do not close session-transition proxy runs proxy-only; every valid model-bearing run remains L4-bound.",
            "Session boundary runtime semantics remain pending until MT5 L4 observation and reconciliation.",
            "Python ONNXRuntime parity is bundle preflight only, not runtime authority or economics evidence.",
        ],
        "environment": {
            "command": " ".join(command_argv),
            "command_argv": command_argv,
            "cwd": ".",
            "python_executable": base.redact_home(sys.executable),
            "python_version": platform.python_version(),
            "dependency_summary": base.dependency_summary(),
            "started_at_utc": started_at_utc,
            "ended_at_utc": base.utc_now(),
            **base.git_identity(repo_root),
        },
        "forbidden_claims": FORBIDDEN_CLAIMS,
    }
    return summary, results


def index_fieldnames() -> list[str]:
    return [
        "run_id",
        "run_spec_id",
        "cell_id",
        "bundle_id",
        "status",
        "result_judgment",
        "model_family",
        "task_kind",
        "decision_family",
        "session_anchor",
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
        "status": "completed_wave01_session_transition_onnx_bundle_preflight_l4_attempt_preparation_pending",
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
            base.artifact_ref(SUMMARY_PATH, repo_root),
            base.artifact_ref(INDEX_PATH, repo_root),
        ],
        "forbidden_claims": summary["forbidden_claims"],
    }


def ensure_list_item(values: list[Any], item: Any) -> None:
    if item not in values:
        values.append(item)


def upsert_artifact_registry(repo_root: Path, summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    registry_path = repo_root / ARTIFACT_REGISTRY
    registry_rows = base.read_csv_rows(registry_path)
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
    by_id = {row["artifact_id"]: row for row in registry_rows}
    producer = "foundation/pipelines/materialize_wave01_session_transition_l4_onnx_bundles.py --write-control-records"
    regen = f"python {producer}"

    def put(row: dict[str, str]) -> None:
        path = repo_root / row["path_or_uri"]
        if path.exists():
            row["sha256"] = base.sha256(path)
            row["size_bytes"] = str(path.stat().st_size)
        by_id[row["artifact_id"]] = {key: row.get(key, "") for key in fieldnames}

    put(
        {
            "artifact_id": "artifact_wave01_session_transition_l4_onnx_materialization_summary_v0",
            "artifact_type": "onnx_materialization_summary",
            "path_or_uri": SUMMARY_PATH.as_posix(),
            "availability": "present_hash_recorded",
            "producer_command": producer,
            "regeneration_command": regen,
            "source_of_truth": SUMMARY_PATH.as_posix(),
            "consumer": WORK_ITEM_ID,
            "claim_boundary": CLAIM_BOUNDARY,
            "notes": "session-transition bundle preflight only; MT5 L4 remains pending",
        }
    )
    put(
        {
            "artifact_id": "artifact_wave01_session_transition_l4_onnx_materialization_index_v0",
            "artifact_type": "onnx_materialization_index",
            "path_or_uri": INDEX_PATH.as_posix(),
            "availability": "present_hash_recorded",
            "producer_command": producer,
            "regeneration_command": regen,
            "source_of_truth": SUMMARY_PATH.as_posix(),
            "consumer": WORK_ITEM_ID,
            "claim_boundary": CLAIM_BOUNDARY,
            "notes": "session-transition run-to-bundle materialization index",
        }
    )
    put(
        {
            "artifact_id": "artifact_wave01_session_transition_l4_onnx_materialization_closeout_v0",
            "artifact_type": "work_closeout",
            "path_or_uri": CLOSEOUT_PATH.as_posix(),
            "availability": "present_hash_recorded",
            "producer_command": producer,
            "regeneration_command": regen,
            "source_of_truth": CLOSEOUT_PATH.as_posix(),
            "consumer": WORK_ITEM_ID,
            "claim_boundary": CLAIM_BOUNDARY,
            "notes": "subwork closeout; L4 attempt preparation remains next",
        }
    )
    for row in rows:
        put(
            {
                "artifact_id": f"artifact_{row['bundle_id']}_manifest_v0",
                "run_id": row["run_id"],
                "bundle_id": row["bundle_id"],
                "artifact_type": "experiment_bundle",
                "path_or_uri": row["bundle_manifest_path"],
                "availability": "present_hash_recorded",
                "producer_command": producer,
                "regeneration_command": regen,
                "source_of_truth": row["bundle_manifest_path"],
                "consumer": WORK_ITEM_ID,
                "claim_boundary": CLAIM_BOUNDARY,
                "notes": "session-transition ONNX bundle manifest with Python ONNXRuntime parity; MT5 L4 pending",
            }
        )
        put(
            {
                "artifact_id": f"artifact_{row['bundle_id']}_onnx_v0",
                "run_id": row["run_id"],
                "bundle_id": row["bundle_id"],
                "artifact_type": "onnx_model",
                "path_or_uri": row["onnx_path"],
                "availability": "local_artifact_hash_recorded",
                "producer_command": producer,
                "regeneration_command": regen,
                "source_of_truth": row["bundle_manifest_path"],
                "consumer": WORK_ITEM_ID,
                "claim_boundary": CLAIM_BOUNDARY,
                "notes": "local ONNX artifact tracked by hash; regenerate from session-transition materializer",
            }
        )
    base.write_csv(registry_path, list(by_id.values()), fieldnames)


def update_control_records(repo_root: Path, summary: dict[str, Any], closeout: dict[str, Any]) -> None:
    next_phase = "wave01_session_transition_l4_onnx_materialized_attempt_preparation_next"
    next_work = base.load_yaml(repo_root / NEXT_WORK_ITEM)
    current_truth = next_work.setdefault("current_truth", {})
    current_truth["wave01_session_transition_onnx_materialization_summary"] = SUMMARY_PATH.as_posix()
    current_truth["wave01_session_transition_onnx_materialization_status"] = summary["status"]
    current_truth["wave01_session_transition_onnx_materialization_counts"] = summary["counts"]
    next_work["status"] = "planned_next_l4_strategy_tester_attempt_preparation_after_onnx_materialization"
    next_work["missing_material_if_relevant"] = [
        "L4_strategy_tester_attempts_not_prepared_for_wave01_session_transition_bundles",
        "L4_validation_and_research_oos_reports_absent",
    ]
    next_work["next_action"] = summary["judgment"]["next_action"]
    base.write_yaml(repo_root / NEXT_WORK_ITEM, next_work)

    resume = base.load_yaml(repo_root / RESUME_CURSOR)
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
    base.write_yaml(repo_root / RESUME_CURSOR, resume)

    goal = base.load_yaml(repo_root / GOAL_MANIFEST)
    goal["updated_at_utc"] = summary["created_at_utc"]
    goal["active_phase"] = next_phase
    session_transition = goal.setdefault("session_transition_campaign", {})
    session_transition["l4_onnx_materialization_summary"] = SUMMARY_PATH.as_posix()
    session_transition["l4_onnx_materialization_status"] = summary["status"]
    session_transition["l4_onnx_materialization_counts"] = summary["counts"]
    session_transition["next_work_item"] = WORK_ITEM_ID
    base.write_yaml(repo_root / GOAL_MANIFEST, goal)

    workspace = base.load_yaml(repo_root / WORKSPACE_STATE)
    workspace["updated_utc"] = summary["created_at_utc"]
    claims = workspace.setdefault("current_claims", {})
    claims["active_goal_phase"] = next_phase
    claims["wave0_third_campaign_L4_status"] = "L4_onnx_materialized_attempt_preparation_required_next"
    claims["wave0_third_campaign_l4_onnx_materialization_summary"] = SUMMARY_PATH.as_posix()
    claims["wave0_third_campaign_l4_onnx_materialization_status"] = summary["status"]
    claims["wave0_third_campaign_l4_onnx_materialization_counts"] = summary["counts"]
    claims["wave0_third_campaign_next_work_item"] = WORK_ITEM_ID
    base.write_yaml(repo_root / WORKSPACE_STATE, workspace)

    goal_registry_path = repo_root / GOAL_REGISTRY
    if goal_registry_path.exists():
        goal_rows = base.read_csv_rows(goal_registry_path)
        for row in goal_rows:
            if row.get("goal_id") == GOAL_ID:
                row["active_phase"] = next_phase
                row["next_work_item"] = WORK_ITEM_ID
                row["claim_boundary"] = "active_goal_wave01_session_transition_l4_onnx_materialized_not_goal_achieve"
        if goal_rows:
            base.write_csv(goal_registry_path, goal_rows, list(goal_rows[0].keys()))

    upsert_artifact_registry(repo_root, summary, summary["exported_runs"])


def write_outputs(repo_root: Path, summary: dict[str, Any], rows: list[dict[str, Any]], *, write_control_records: bool) -> None:
    base.write_yaml(repo_root / SUMMARY_PATH, summary)
    base.write_csv(repo_root / INDEX_PATH, rows, index_fieldnames())
    closeout = build_closeout(summary, repo_root)
    base.write_yaml(repo_root / CLOSEOUT_PATH, closeout)
    if write_control_records:
        update_control_records(repo_root, summary, closeout)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize Wave01 session-transition ONNX bundles for L4 follow-through.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--write-control-records", action="store_true")
    return parser.parse_args(argv)


def main(*_args: object, **_kwargs: object) -> int:
    from foundation.pipelines.historical_lifecycle_guard import disabled_lifecycle_entrypoint

    return disabled_lifecycle_entrypoint(
        "a run-local/domain evidence command plus locked spacesonar lifecycle transaction for canonical state updates"
    )


if __name__ == "__main__":
    raise SystemExit(main())
