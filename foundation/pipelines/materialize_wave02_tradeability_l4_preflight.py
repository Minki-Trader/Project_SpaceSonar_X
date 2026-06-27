from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
import pandas as pd
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
for item in (REPO_ROOT, SRC_ROOT):
    text = str(item)
    if text not in sys.path:
        sys.path.insert(0, text)

from foundation.features.wave02_tradeability_features import build_wave02_tradeability_features  # noqa: E402
from foundation.labels.wave02_tradeability_labels import build_wave02_tradeability_labels  # noqa: E402
from foundation.onnx.skl2onnx_adapters import convert_sklearn_pipeline_for_lab  # noqa: E402
from foundation.pipelines.run_wave02_tradeability_proxy_batch import (  # noqa: E402
    build_model_target,
    load_row_membership,
    model_family_for_recipe,
    split_masks,
    usable_feature_columns,
)
from foundation.training.wave01_event_barrier_models import fit_proxy_model, score_model  # noqa: E402
from spacesonar.control_plane.store import (  # noqa: E402
    dump_csv,
    dump_yaml,
    filesystem_path,
    read_csv_rows,
    read_json,
    read_yaml,
    repo_relative,
    sha256_file,
)


UTC = timezone.utc

GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WAVE_ID = "wave_us100_wave02_tradeability_decision_surface_v0"
CAMPAIGN_ID = "campaign_us100_wave02_tradeability_decision_surface_v0"
SWEEP_ID = "sweep_us100_wave02_tradeability_side_abstain_broad_v0"
SURFACE_ID = "surface_us100_wave02_tradeability_side_abstain_v0"
WORK_ITEM_ID = "work_wave02_tradeability_l4_materialization_preflight_v0"
NEXT_WORK_ITEM_ID = "work_wave02_tradeability_l4_runtime_execution_v0"

CAMPAIGN_DIR = Path("lab/campaigns") / CAMPAIGN_ID
RUN_REFS = CAMPAIGN_DIR / "sweeps" / SWEEP_ID / "run_refs.csv"
ROW_MEMBERSHIP_MANIFEST = Path(
    "lab/campaigns/campaign_us100_task_surface_scout_v0/row_membership/row_membership_manifest.yaml"
)
L4_DIR = CAMPAIGN_DIR / "l4_follow_through"
ONNX_SUMMARY = L4_DIR / "onnx_materialization_summary.yaml"
ONNX_INDEX = L4_DIR / "onnx_materialization_index.csv"
ATTEMPT_SUMMARY = L4_DIR / "l4_attempt_preparation_summary.yaml"
ATTEMPT_INDEX = L4_DIR / "l4_attempt_preparation_index.csv"
PRECHECK_SUMMARY = L4_DIR / "writer_contract_precheck.yaml"
CLOSEOUT_PATH = Path("lab/goals") / GOAL_ID / "work_wave02_tradeability_l4_materialization_preflight_v0_closeout.yaml"
NEXT_WORK_ITEM = Path("lab/goals") / GOAL_ID / "next_work_item.yaml"
RESUME_CURSOR = Path("lab/goals") / GOAL_ID / "resume_cursor.yaml"
GOAL_MANIFEST = Path("lab/goals") / GOAL_ID / "goal_manifest.yaml"
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")

RUNTIME_CONTRACT = Path("foundation/config/mt5_runtime_probe_contract.yaml")
PERIOD_PROFILE = Path("configs/mt5/period_profiles/split_set_v0_runtime_periods.yaml")
EXECUTION_PROFILE = Path("configs/mt5/tester_execution_profile_v0.yaml")
EA_SOURCE = Path("foundation/mt5/experts/SpaceSonar_ONNX_L4_ScoreProbe.mq5")
EA_BINARY = Path("foundation/mt5/experts/SpaceSonar_ONNX_L4_ScoreProbe.ex5")
COMMON_REL_ROOT = "SpaceSonar\\l4_score_probe"
EA_EXPERT_CONFIG_PATH = "Project_SpaceSonar_X\\foundation\\mt5\\experts\\SpaceSonar_ONNX_L4_ScoreProbe.ex5"

BUNDLE_CLAIM_BOUNDARY = (
    "wave02_l4_onnx_bundle_preflight_python_parity_only_no_runtime_authority_"
    "no_economics_pass_no_candidate_no_live_readiness_no_goal_achieve"
)
ATTEMPT_CLAIM_BOUNDARY = (
    "wave02_l4_strategy_tester_attempt_preparation_only_no_runtime_authority_"
    "no_economics_pass_no_candidate_no_live_readiness_no_goal_achieve"
)
NEXT_CLAIM_BOUNDARY = (
    "wave02_l4_attempts_prepared_terminal_execution_pending_no_runtime_authority_"
    "no_economics_pass_no_candidate_no_live_readiness_no_goal_achieve"
)
ONNX_STATUS = "onnx_exported_python_onnxruntime_parity_passed"
ATTEMPT_STATUS = "prepared_pending_terminal_execution"
CAMPAIGN_STATUS = "wave02_l4_attempts_prepared_terminal_execution_next"

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


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def path_exists(path: Path) -> bool:
    return os.path.exists(filesystem_path(path))


def write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    os.makedirs(filesystem_path(path.parent), exist_ok=True)
    with open(filesystem_path(path), "w", encoding=encoding, newline="\n") as handle:
        handle.write(text)


def write_bytes(path: Path, payload: bytes) -> None:
    os.makedirs(filesystem_path(path.parent), exist_ok=True)
    with open(filesystem_path(path), "wb") as handle:
        handle.write(payload)


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    write_text(path, dump_yaml(jsonable(payload)))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    write_text(path, json.dumps(jsonable(payload), indent=2, ensure_ascii=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    write_text(path, dump_csv(fieldnames, rows))


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [jsonable(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, Path):
        return value.as_posix()
    return value


def stable_hash(payload: Any) -> str:
    encoded = json.dumps(jsonable(payload), sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def feature_order_hash(columns: list[str]) -> str:
    return hashlib.sha256("|".join(columns).encode("utf-8")).hexdigest()


def artifact_ref(path: Path, *, availability: str = "present_hash_recorded") -> dict[str, Any]:
    return {
        "path": repo_relative(REPO_ROOT, path),
        "sha256": sha256_file(path),
        "size_bytes": os.stat(filesystem_path(path)).st_size,
        "availability": availability,
    }


def optional_artifact_ref(path: Path, *, availability: str) -> dict[str, Any]:
    if path_exists(path):
        return artifact_ref(path, availability=availability)
    return {"path": path.as_posix(), "exists": False, "availability": "missing"}


def mask_local_path(value: str) -> str:
    text = str(value)
    home = str(Path.home())
    appdata = os.environ.get("APPDATA")
    if appdata and text.startswith(appdata):
        text = "${APPDATA}" + text[len(appdata) :]
    if text.startswith(home):
        text = "${USERPROFILE}" + text[len(home) :]
    return text


def durable_arg(value: str) -> str:
    try:
        path = Path(value)
        if path.is_absolute() and path.exists():
            return repo_relative(REPO_ROOT, path)
    except OSError:
        pass
    return mask_local_path(value)


def run_git(args: list[str]) -> str:
    result = subprocess.run(["git", *args], cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip() or "unknown"


def git_status_lines() -> list[str]:
    result = subprocess.run(["git", "status", "--short"], cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def branch_worktree(expected_branch: str) -> dict[str, Any]:
    current = run_git(["branch", "--show-current"])
    if current != expected_branch:
        raise RuntimeError(f"branch mismatch before Wave02 L4 preflight: current={current!r} expected={expected_branch!r}")
    status = git_status_lines()
    return {
        "current_branch": current,
        "requested_branch": expected_branch,
        "branch_worktree_fit": "fit",
        "branch_action": "keep_current_branch",
        "policy_reference": "docs/policies/branch_policy.md",
        "dirty_flag": bool(status),
        "changed_files": status,
        "mismatch_claim_effect": "not_applicable",
    }


def dependency_summary() -> dict[str, str]:
    result: dict[str, str] = {"python": platform.python_version(), "platform": platform.platform()}
    for package in ["numpy", "pandas", "sklearn", "onnx", "onnxruntime", "skl2onnx", "yaml"]:
        try:
            module = __import__(package)
            result[package] = str(getattr(module, "__version__", "unknown"))
        except Exception as exc:  # noqa: BLE001 - environment evidence.
            result[package] = f"unavailable:{exc}"
    return result


def common_files_root() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "MetaQuotes" / "Terminal" / "Common" / "Files"


def mt5_common_redacted(common_relative_path: str) -> str:
    return "${MT5_COMMONDATA}\\Files\\" + common_relative_path


def cell_id_from_run_id(run_id: str) -> str:
    match = re.search(r"(wave02_td_cell_\d{3})", run_id)
    if not match:
        raise ValueError(f"cannot derive Wave02 cell_id from run_id={run_id}")
    return match.group(1)


def required_l4_periods(period_profile: dict[str, Any], runtime_period_set_id: str) -> list[dict[str, str]]:
    for period_set in period_profile.get("runtime_period_sets", []):
        if period_set.get("runtime_period_set_id") == runtime_period_set_id:
            periods = period_set.get("periods") or {}
            roles = period_set.get("required_roles") or list(periods)
            return [
                {
                    "period_role": role,
                    "split_role": str(periods[role].get("split_role", role)),
                    "from_date": str(periods[role]["from_date"]),
                    "to_date": str(periods[role]["to_date"]),
                }
                for role in roles
            ]
    raise KeyError(f"runtime period set not found: {runtime_period_set_id}")


def max_feature_window(columns: list[str]) -> int:
    max_window = 12
    for column in columns:
        suffix = column.rsplit("_", 1)[-1]
        if suffix.isdigit():
            max_window = max(max_window, int(suffix))
    return max(720, max_window + 24)


def load_run_spec(path: Path) -> dict[str, Any]:
    payload = read_yaml(path)
    if not isinstance(payload, dict) or not payload.get("run_id"):
        raise ValueError(f"run spec is not a valid mapping: {repo_relative(REPO_ROOT, path)}")
    return payload


def run_refs() -> list[dict[str, str]]:
    rows = read_csv_rows(REPO_ROOT / RUN_REFS)
    if not rows:
        raise RuntimeError(f"run refs empty: {RUN_REFS.as_posix()}")
    return rows


def score_parity(
    *,
    fit_model: Any,
    task_kind: str,
    features: pd.DataFrame,
    validation_mask: pd.Series,
    onnx_path: Path,
    artifacts_dir: Path,
) -> dict[str, Any]:
    sample = features.loc[validation_mask].head(512).astype("float32")
    if sample.empty:
        raise ValueError("ONNX parity sample is empty")
    expected = score_model(fit_model, sample, task_kind).reshape(-1)
    session = ort.InferenceSession(filesystem_path(onnx_path), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    observed = session.run(["score"], {input_name: sample.to_numpy(dtype=np.float32)})[0].reshape(-1)
    abs_error = np.abs(expected - observed)

    fixture_input = artifacts_dir / "parity_fixture_input.csv"
    expected_score = artifacts_dir / "parity_expected_score.csv"
    observed_score = artifacts_dir / "parity_onnxruntime_score.csv"
    os.makedirs(filesystem_path(artifacts_dir), exist_ok=True)
    sample.to_csv(filesystem_path(fixture_input), index=False, lineterminator="\n")
    pd.DataFrame({"score": expected}).to_csv(filesystem_path(expected_score), index=False, lineterminator="\n")
    pd.DataFrame({"score": observed}).to_csv(filesystem_path(observed_score), index=False, lineterminator="\n")

    tolerance = 1e-5
    status = "passed" if float(np.max(abs_error)) <= tolerance else "failed"
    if status != "passed":
        raise RuntimeError(f"ONNXRuntime parity failed max_abs_error={float(np.max(abs_error))}")
    return {
        "status": status,
        "sample_scope": "first_validation_rows_after_train_only_fit",
        "sample_rows": int(len(sample)),
        "max_abs_error": float(np.max(abs_error)),
        "mean_abs_error": float(np.mean(abs_error)),
        "tolerance": tolerance,
        "fixture_input": artifact_ref(fixture_input, availability="local_artifact_hash_recorded"),
        "expected_score": artifact_ref(expected_score, availability="local_artifact_hash_recorded"),
        "observed_score": artifact_ref(observed_score, availability="local_artifact_hash_recorded"),
    }


def materialize_bundle(
    *,
    run_spec: dict[str, Any],
    frame: pd.DataFrame,
    command_argv: list[str],
    branch: dict[str, Any],
    runtime_contract: dict[str, Any],
    period_profile: dict[str, Any],
    execution_profile: dict[str, Any],
    started_at_utc: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    run_id = str(run_spec["run_id"])
    refs = run_spec["recipe_refs"]
    cell_id = cell_id_from_run_id(run_id)
    bundle_id = f"bundle_{cell_id}_l4_onnx_export_v0"
    bundle_dir = REPO_ROOT / "runtime" / "packages" / bundle_id
    artifacts_dir = bundle_dir / "artifacts"
    onnx_path = artifacts_dir / "model.onnx"
    feature_columns_path = artifacts_dir / "feature_columns.txt"

    features, feature_schema = build_wave02_tradeability_features(frame, refs["feature_recipe_id"])
    labels, label_schema = build_wave02_tradeability_labels(frame, refs["label_recipe_id"])
    masks = split_masks(frame, labels)
    train_mask = masks["train"]
    validation_mask = masks["validation"]
    research_mask = masks["research_oos_a"]
    target, task_kind, target_name, target_threshold = build_model_target(labels, train_mask)
    target_ok = target.notna()
    train_mask = train_mask & target_ok
    validation_mask = validation_mask & target_ok
    research_mask = research_mask & target_ok
    if int(train_mask.sum()) < 1000 or int(validation_mask.sum()) < 300 or int(research_mask.sum()) < 300:
        raise ValueError(
            f"{run_id}: insufficient split rows train={int(train_mask.sum())} "
            f"validation={int(validation_mask.sum())} research={int(research_mask.sum())}"
        )

    columns = usable_feature_columns(features, train_mask)
    x = features[columns]
    model_family = model_family_for_recipe(refs["model_recipe_id"])
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
    conversion = convert_sklearn_pipeline_for_lab(fit.model, feature_count=len(columns), task_kind=task_kind, target_opset=13)
    write_bytes(onnx_path, conversion.model.SerializeToString())
    write_text(feature_columns_path, ";".join(columns))

    feature_schema_contract = {
        "input_family": refs["feature_recipe_id"],
        "feature_count": len(columns),
        "feature_columns": columns,
        "feature_order_hash": feature_order_hash(columns),
        "all_nan_train_columns_dropped": [
            column for column in features.columns if column not in columns and not features.loc[train_mask, column].notna().any()
        ],
        "boundary": "right_aligned_US100_M5_closed_bar_wave02_tradeability_features",
        "feature_count_policy": "variable_declared_per_run_no_fixed_count",
    }
    label_schema_contract = {
        **getattr(label_schema, "__dict__", {}),
        "target_name_used_for_model": target_name,
        "target_threshold": target_threshold,
    }
    feature_schema_payload = {**getattr(feature_schema, "__dict__", {}), "used_feature_columns": columns}
    write_json(artifacts_dir / "feature_schema.json", feature_schema_payload)
    write_json(artifacts_dir / "label_schema.json", label_schema_contract)
    write_json(
        artifacts_dir / "model_summary.json",
        {
            "run_id": run_id,
            "model_recipe_id": refs["model_recipe_id"],
            "proxy_model_family": model_family,
            "task_kind": task_kind,
            "target_name": target_name,
            "target_threshold": target_threshold,
            "model_summary": fit.model_summary,
            "train_score_summary": fit.train_score_summary,
        },
    )
    split_profile = {
        "raw_rows": int(len(frame)),
        "train_rows_used_for_fit": int(train_mask.sum()),
        "validation_rows_available_for_L4": int(validation_mask.sum()),
        "research_oos_a_rows_available_for_L4": int(research_mask.sum()),
        "locked_final_oos_b_rows_withheld": int(masks["locked_final_oos_b_withheld"].sum()),
        "locked_final_oos_b_use": "withheld_forbidden_by_default",
    }
    write_json(artifacts_dir / "split_profile.json", split_profile)
    parity = score_parity(
        fit_model=fit.model,
        task_kind=task_kind,
        features=x,
        validation_mask=validation_mask,
        onnx_path=onnx_path,
        artifacts_dir=artifacts_dir,
    )

    row_manifest = read_yaml(REPO_ROOT / ROW_MEMBERSHIP_MANIFEST)
    csv_info = ((row_manifest.get("row_membership") or {}).get("full_csv") or {})
    id_chain = dict(run_spec.get("id_chain") or {})
    id_chain["bundle_id"] = bundle_id
    id_chain["candidate_id"] = None
    id_chain["cell_id"] = cell_id
    runtime_period_set_id = runtime_contract["period_authority"]["default_runtime_period_set_id"]
    required_roles = list(runtime_contract["completion"]["required_period_roles"])
    bundle = {
        "version": "experiment_bundle_v3",
        "bundle_id": bundle_id,
        "run_id": run_id,
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "source_of_truth": f"runtime/packages/{bundle_id}/experiment_bundle.json",
        "created_at_utc": started_at_utc,
        "status": ONNX_STATUS,
        "claim_boundary": BUNDLE_CLAIM_BOUNDARY,
        "id_chain": id_chain,
        "dataset_id": str(csv_info.get("dataset_id") or "dataset_raw_us100_m5_wave0_export_20260621T152827Z"),
        "data_source": {
            "base_frame": "US100_M5_closed_bar",
            "row_key": "us100_bar_close_time",
            "row_membership_manifest": ROW_MEMBERSHIP_MANIFEST.as_posix(),
            "row_membership_csv_sha256": csv_info.get("sha256"),
            "sample_scope": split_profile,
            "split_boundary": "train_only_fit_validation_and_research_oos_reserved_for_L4_runtime_observation",
            "locked_final_oos_b_use": "withheld_forbidden_by_default",
        },
        "feature_recipe_id": refs["feature_recipe_id"],
        "feature_schema_hash": stable_hash(feature_schema_payload),
        "feature_order_hash": feature_order_hash(columns),
        "feature_schema_contract": feature_schema_contract,
        "label_recipe_id": refs["label_recipe_id"],
        "label_id": refs["label_recipe_id"],
        "label_schema_hash": stable_hash(label_schema_contract),
        "target_and_label": {
            "label_surface": refs["label_recipe_id"],
            "target_name": target_name,
            "target_threshold": target_threshold,
            "target_threshold_fit_scope": "train_only" if target_threshold is not None else "not_applicable",
            "label_boundary": "same_split_role_horizon_ok_rows_only",
        },
        "split_id": "split_set_v0",
        "primary_split_id": "split_base_anchor_v0",
        "task_surface_id": SURFACE_ID,
        "task_surface": {
            "task_type": "tradeability_side_abstain_proxy",
            "target_or_label": refs["label_recipe_id"],
            "direction_mapping": "proxy_side_labels_not_runtime_authority",
            "output_head": "single_score_for_L4_non_trading_score_probe",
        },
        "decision_use": "wave02_score_telemetry_preflight_for_side_abstain_surface",
        "decision_recipe_id": refs["decision_recipe_id"],
        "decision_surface_id": f"{refs['decision_recipe_id']}_score_probe_runtime_preflight",
        "decision_surface": {
            "proxy_decision_recipe_id": refs["decision_recipe_id"],
            "decision_family": "abstain_capable_direction_agnostic_tradeability",
            "holding_policy": "not_executed_score_telemetry_only",
            "risk_policy": "fixed_lot_recorded_but_EA_non_trading",
            "threshold_policy": fit.threshold_policy,
            "score_low_threshold": fit.score_low_threshold,
            "score_high_threshold": fit.score_high_threshold,
            "runtime_translation_status": "score_probe_preflight_direction_and_trade_execution_pending",
        },
        "model_family": model_family,
        "model_task": "wave02_tradeability_classification",
        "model_framework": "sklearn_pipeline_skl2onnx",
        "onnx_conversion": {
            "target_opset": 13,
            "adapter_ids": conversion.adapter_ids,
            "try_first_policy": "missing_adapter_or_runtime_glue_triggers_smallest_repo_controlled_repair_before_disposition",
        },
        "model_opset": 13,
        "model_training": {
            "fit_scope": "train_only",
            "preprocessing_fit_scope": "train_only",
            "calibration": "none",
            "selection_metric": "none_selected_materialization_follows_existing_proxy_run",
            "overfit_risk": "broad_surface_multiple_testing_risk_no_selection_allowed",
            "calibration_risk": "scores_are_rank_or_classifier_outputs_not_calibrated_probabilities",
        },
        "input_schema": {
            "input_name": "features",
            "dtype": "float32",
            "shape": [None, len(columns)],
            "feature_order_hash": feature_order_hash(columns),
            "feature_columns": columns,
        },
        "output_schema": {
            "task_kind": task_kind,
            "score_semantics": "class_1_probability" if task_kind == "classification" else "regression_score",
            "onnx_outputs": ["score"],
            "score_extraction": "score.reshape(-1)",
            "probability_calibration_claim": False,
            "mt5_output_contract": "single_float_score_vector_shape_1_for_single_row_inference",
        },
        "onnx_path": repo_relative(REPO_ROOT, onnx_path),
        "onnx_sha256": sha256_file(onnx_path),
        "onnx_size_bytes": os.stat(filesystem_path(onnx_path)).st_size,
        "onnx_adapter_ids": conversion.adapter_ids,
        "parser_version": "spacesonar_wave02_tradeability_l4_preflight_v0",
        "runtime_contract_version": runtime_contract["version"],
        "runtime_period_profile_id": period_profile["period_profile_id"],
        "runtime_period_set_id": runtime_period_set_id,
        "tester_execution_profile_id": execution_profile["profile_id"],
        "python_onnxruntime_parity": parity,
        "runtime_learning_probe_decision": {
            "required": True,
            "decision": "run_required_next",
            "required_runtime_level": "L4_split_runtime_probe",
            "reason": "Valid Wave02 proxy/model-bearing run has ONNX bundle preflight; MT5 L4 terminal execution remains required.",
            "period_profile_id": period_profile["period_profile_id"],
            "runtime_period_set_id": runtime_period_set_id,
            "required_period_roles": required_roles,
            "l5_rule": runtime_contract["runtime_learning_probe_decision"]["l5_continuation_rule"],
            "lowered_claim_if_not_run": "bundle_preflight_only_no_runtime_authority_no_economics_pass_no_candidate",
        },
        "proxy_runtime_parity": {
            "status": "pending_L4_strategy_tester",
            "shared_contract": [
                "US100_M5_closed_bar_base_frame",
                "feature_order_hash",
                "single_score_output",
                "period_profile_split_set_v0",
                "us100_m5_fpmarkets_tester_execution_v0",
            ],
            "known_differences": [
                "Python proxy row membership uses exported MT5 history; EA reconstructs features from Strategy Tester closed bars.",
                "Wave02 proxy decision recipes may use side labels; this L4 score probe records non-trading score telemetry only.",
                "Strategy Tester spread/tick availability can differ from exported proxy data.",
                "Economics and live-like execution remain forbidden until a trading decision EA and terminal evidence exist.",
            ],
            "interpretation_drift_risks": [
                "bar_close_timing",
                "feature_reconstruction_in_EA",
                "spread_field_semantics",
                "score_threshold_translation",
                "side_label_not_available_to_score_only_EA",
                "non_trading_score_observation_vs_trade_execution",
            ],
            "minimum_reconciliation_attempt": {
                "status": "pending_MT5_L4",
                "attempt": "single_score_output_ONNX_contract_plus_feature_order_hash_plus_EA_feature_reconstruction",
                "forced_equality_required": False,
            },
            "unit_semantics": {
                "features": "float32 closed-bar values in bundle feature order",
                "score": "single model score from sklearn-to-ONNX adapter",
                "price_units": "MT5 price values from MqlRates",
                "spread": "MqlRates.spread raw points scaled only where feature contract says spread_scaled",
                "lot": "fixed_lot_profile_recorded_but_EA_non_trading",
            },
            "comparison_class": "pending_L4",
            "divergence_judgment": "pending_L4",
            "prevention_memory": [
                "Do not treat ONNXRuntime parity as MT5 runtime parity.",
                "Do not convert Wave02 side/abstain proxy metrics into economics claims from score telemetry.",
                "Missing runtime glue must trigger a bounded adapter attempt before blocked/deferred/invalid/discarded.",
            ],
            "follow_up_action": NEXT_WORK_ITEM_ID,
            "claim_boundary": "proxy_runtime_parity_tracking_only_no_runtime_authority",
        },
        "producer_command": " ".join(durable_arg(arg) for arg in command_argv),
        "environment_summary": dependency_summary(),
        "provenance": {
            "command_argv": [durable_arg(arg) for arg in command_argv],
            "cwd": ".",
            "python_executable": mask_local_path(sys.executable),
            "python_version": platform.python_version(),
            "started_at_utc": started_at_utc,
            "ended_at_utc": utc_now(),
            "git_sha": run_git(["rev-parse", "HEAD"]),
            "branch": run_git(["branch", "--show-current"]),
            "branch_worktree": branch,
            "input_hashes": [
                artifact_ref(REPO_ROOT / ROW_MEMBERSHIP_MANIFEST),
                artifact_ref(REPO_ROOT / RUN_REFS),
                artifact_ref(REPO_ROOT / CAMPAIGN_DIR / "run_specs" / f"{run_id}.yaml"),
            ],
            "output_hashes": [
                artifact_ref(onnx_path, availability="local_artifact_hash_recorded"),
                artifact_ref(feature_columns_path, availability="local_artifact_hash_recorded"),
                artifact_ref(artifacts_dir / "feature_schema.json", availability="local_artifact_hash_recorded"),
                artifact_ref(artifacts_dir / "label_schema.json", availability="local_artifact_hash_recorded"),
                artifact_ref(artifacts_dir / "model_summary.json", availability="local_artifact_hash_recorded"),
                artifact_ref(artifacts_dir / "split_profile.json", availability="local_artifact_hash_recorded"),
            ],
            "dirty_worktree_claim_effect": "bundle_preflight_only_no_reproducible_candidate_runtime_or_goal_achieve_claim",
        },
        "required_gate_coverage": {
            "passed": [
                "onnx_export_smoke",
                "python_onnx_parity",
                "feature_schema_contract",
                "bundle_integrity_hash",
                "proxy_runtime_parity_record",
                "operational_stability_writer_contract",
                "final_claim_guard",
            ],
            "missing": [
                "L4_split_runtime_probe_terminal_execution",
                "strategy_tester_report",
                "score_telemetry_rows",
                "candidate_runtime_evidence",
            ],
            "not_applicable": ["locked_final_oos_b_access"],
        },
        "missing_evidence": [
            "MT5_L4_split_runtime_probe_not_run",
            "Strategy_Tester_report_pending",
            "score_telemetry_pending_terminal_execution",
            "candidate_selection_forbidden_before_L4",
        ],
        "next_action": NEXT_WORK_ITEM_ID,
        "forbidden_claims": FORBIDDEN_CLAIMS,
    }
    bundle_path = bundle_dir / "experiment_bundle.json"
    write_json(bundle_path, bundle)
    bundle["bundle_manifest_ref"] = artifact_ref(bundle_path)
    row = {
        "run_id": run_id,
        "cell_id": cell_id,
        "bundle_id": bundle_id,
        "status": ONNX_STATUS,
        "bundle_manifest_path": repo_relative(REPO_ROOT, bundle_path),
        "onnx_path": repo_relative(REPO_ROOT, onnx_path),
        "onnx_sha256": sha256_file(onnx_path),
        "feature_count": len(columns),
        "feature_order_hash": feature_order_hash(columns),
        "model_family": model_family,
        "task_kind": task_kind,
        "parity_status": parity["status"],
        "parity_max_abs_error": parity["max_abs_error"],
        "claim_boundary": BUNDLE_CLAIM_BOUNDARY,
    }
    return bundle, row


def score_thresholds(bundle: dict[str, Any]) -> tuple[float, float, bool]:
    decision = bundle.get("decision_surface") or {}
    low = decision.get("score_low_threshold")
    high = decision.get("score_high_threshold")
    has_low_high = low is not None or high is not None
    return float(low or 0.0), float(high or 0.0), bool(has_low_high)


def build_tester_config_text(
    *,
    attempt_id: str,
    bundle: dict[str, Any],
    period: dict[str, str],
    execution_profile: dict[str, Any],
) -> str:
    tester_defaults = execution_profile["tester_defaults"]
    sizing = execution_profile["position_sizing_boundary"]
    columns = bundle["feature_schema_contract"]["feature_columns"]
    low, high, has_low_high = score_thresholds(bundle)
    onnx_common_path = f"{COMMON_REL_ROOT}\\{bundle['bundle_id']}\\model.onnx"
    columns_common_path = f"{COMMON_REL_ROOT}\\{bundle['bundle_id']}\\feature_columns.txt"
    telemetry_common_path = f"{COMMON_REL_ROOT}\\{attempt_id}\\score_telemetry.csv"
    report_name = f"Project_SpaceSonar_X\\runtime\\mt5_attempts\\{attempt_id}\\tester_report"
    lines = [
        "; SpaceSonar Wave02 L4 ONNX score probe.",
        "; Non-trading EA: reconstructs closed-bar features, runs ONNX, writes score telemetry.",
        "[Tester]",
        f"Expert={EA_EXPERT_CONFIG_PATH}",
        f"Symbol={execution_profile['scope']['symbol']}",
        f"Period={execution_profile['scope']['timeframe']}",
        "Optimization=0",
        f"Model={tester_defaults['model']['mt5_value']}",
        "Dates=1",
        f"FromDate={period['from_date']}",
        f"ToDate={period['to_date']}",
        "ForwardMode=0",
        f"Deposit={tester_defaults['initial_deposit']['value']}",
        f"Currency={tester_defaults['initial_deposit']['currency']}",
        "ProfitInPips=0",
        f"Leverage={str(tester_defaults['leverage']['value']).split(':')[-1]}",
        f"ExecutionMode={tester_defaults['execution_mode']['mt5_value']}",
        "OptimizationCriterion=0",
        "Visual=0",
        "ReplaceReport=1",
        f"Report={report_name}",
        "ShutdownTerminal=1",
        "",
        "[TesterInputs]",
        f"InpOnnxPath={onnx_common_path}",
        f"InpOutputPath={telemetry_common_path}",
        f"InpFeatureColumns={';'.join(columns)}",
        f"InpFeatureColumnsPath={columns_common_path}",
        f"InpFeatureCount={len(columns)}",
        f"InpInputFamily={bundle['feature_schema_contract']['input_family']}",
        f"InpDecisionFamily={bundle['decision_surface']['decision_family']}",
        f"InpScoreLow={low}",
        f"InpScoreHigh={high}",
        f"InpHasLowHigh={'true' if has_low_high else 'false'}",
        f"InpHistoryBars={max_feature_window(columns)}",
        "InpMaxRows=0",
        "InpUseCommonFiles=true",
        f"InpFixedLot={sizing['default_lot']}",
        "",
    ]
    return "\n".join(lines)


def copy_common_files(bundle: dict[str, Any], *, enabled: bool) -> dict[str, Any]:
    columns_path = REPO_ROOT / "runtime" / "packages" / bundle["bundle_id"] / "artifacts" / "feature_columns.txt"
    model_path = REPO_ROOT / bundle["onnx_path"]
    model_common = f"{COMMON_REL_ROOT}\\{bundle['bundle_id']}\\model.onnx"
    columns_common = f"{COMMON_REL_ROOT}\\{bundle['bundle_id']}\\feature_columns.txt"

    def skipped(path: Path, common_rel: str, reason: str) -> dict[str, Any]:
        return {
            "common_relative_path": common_rel,
            "redacted_absolute_path": mt5_common_redacted(common_rel),
            "sha256": sha256_file(path),
            "size_bytes": os.stat(filesystem_path(path)).st_size,
            "durable_identity": "common_relative_path_plus_sha256",
            "path_boundary": "redacted_local_context_only",
            "copy_status": reason,
        }

    if not enabled:
        return {
            "model.onnx": skipped(model_path, model_common, "not_copied_preflight_only"),
            "feature_columns.txt": {
                **skipped(columns_path, columns_common, "not_copied_preflight_only"),
                "feature_count": len(bundle["feature_schema_contract"]["feature_columns"]),
                "transport_reason": "avoid_MT5_tester_input_string_truncation_for_long_feature_lists",
            },
        }
    root = common_files_root()
    if root is None:
        return {
            "model.onnx": skipped(model_path, model_common, "copy_blocked_common_files_root_unavailable"),
            "feature_columns.txt": {
                **skipped(columns_path, columns_common, "copy_blocked_common_files_root_unavailable"),
                "feature_count": len(bundle["feature_schema_contract"]["feature_columns"]),
                "transport_reason": "avoid_MT5_tester_input_string_truncation_for_long_feature_lists",
            },
        }

    model_target = root / Path(model_common.replace("\\", os.sep))
    columns_target = root / Path(columns_common.replace("\\", os.sep))
    model_target.parent.mkdir(parents=True, exist_ok=True)
    columns_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(filesystem_path(model_path), filesystem_path(model_target))
    shutil.copy2(filesystem_path(columns_path), filesystem_path(columns_target))
    return {
        "model.onnx": {
            **skipped(model_path, model_common, "copied_to_mt5_common_files"),
            "copied_sha256": sha256_file(model_target),
        },
        "feature_columns.txt": {
            **skipped(columns_path, columns_common, "copied_to_mt5_common_files"),
            "feature_count": len(bundle["feature_schema_contract"]["feature_columns"]),
            "copied_sha256": sha256_file(columns_target),
            "transport_reason": "avoid_MT5_tester_input_string_truncation_for_long_feature_lists",
        },
    }


def attempt_id_for(cell_id: str, period_role: str) -> str:
    return f"attempt_{cell_id}_l4_{period_role}_v0"


def build_attempt_manifest(
    *,
    attempt_id: str,
    bundle: dict[str, Any],
    period: dict[str, str],
    runtime_contract: dict[str, Any],
    period_profile: dict[str, Any],
    execution_profile: dict[str, Any],
    tester_config_path: Path,
    common_copy: dict[str, Any],
    created_at_utc: str,
    command_argv: list[str],
) -> dict[str, Any]:
    columns = bundle["feature_schema_contract"]["feature_columns"]
    low, high, has_low_high = score_thresholds(bundle)
    bundle_path = REPO_ROOT / bundle["source_of_truth"]
    onnx_path = REPO_ROOT / bundle["onnx_path"]
    report_path = f"runtime/mt5_attempts/{attempt_id}/tester_report.htm"
    telemetry_common = f"{COMMON_REL_ROOT}\\{attempt_id}\\score_telemetry.csv"
    return {
        "version": "mt5_attempt_manifest_v2",
        "attempt_id": attempt_id,
        "run_id": bundle["run_id"],
        "cell_id": (bundle.get("id_chain") or {}).get("cell_id"),
        "surface_id": bundle["task_surface_id"],
        "bundle_id": bundle["bundle_id"],
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": created_at_utc,
        "status": ATTEMPT_STATUS,
        "claim_boundary": ATTEMPT_CLAIM_BOUNDARY,
        "source_of_truth": f"runtime/mt5_attempts/{attempt_id}/attempt_manifest.yaml",
        "work_item_id": NEXT_WORK_ITEM_ID,
        "preparation_work_item_id": WORK_ITEM_ID,
        "routing": {
            "primary_family": "runtime_probe",
            "primary_skill": "spacesonar-runtime-evidence",
            "support_skills": ["spacesonar-evidence-provenance"],
        },
        "runtime_learning_probe_decision": {
            "required": True,
            "decision": "run_required",
            "required_runtime_level": "L4_split_runtime_probe",
            "reason": "Every valid Wave02 proxy/model-bearing run requires L4 MT5 follow-through.",
            "forbidden_skip_reasons_checked": runtime_contract["runtime_learning_probe_decision"][
                "forbidden_standalone_skip_reasons"
            ],
            "lowered_claim_if_not_run": "attempt_preparation_only_no_L4_runtime_evidence",
        },
        "period_identity": {
            "period_profile_id": period_profile["period_profile_id"],
            "runtime_period_set_id": runtime_contract["period_authority"]["default_runtime_period_set_id"],
            "period_role": period["period_role"],
            "split_role": period["split_role"],
            "from_date": period["from_date"],
            "to_date": period["to_date"],
            "locked_final_oos_b": "excluded_forbidden_by_default",
        },
        "execution_identity": {
            "execution_profile_id": execution_profile["profile_id"],
            "broker_server": execution_profile["scope"]["broker_server"],
            "symbol": execution_profile["scope"]["symbol"],
            "timeframe": execution_profile["scope"]["timeframe"],
            "tester_model": execution_profile["tester_defaults"]["model"]["mt5_value"],
            "deposit": execution_profile["tester_defaults"]["initial_deposit"],
            "leverage": execution_profile["tester_defaults"]["leverage"]["value"],
            "spread": execution_profile["cost_defaults"]["spread"],
            "commission_policy": execution_profile["cost_defaults"]["commission"],
            "swap_policy": execution_profile["cost_defaults"]["swap"],
            "slippage_policy": execution_profile["cost_defaults"]["slippage"],
            "sizing_policy": execution_profile["position_sizing_boundary"],
            "non_trading_probe": True,
        },
        "runtime_surface_contract": {
            "completion_surface_scope": "full_period_deterministic",
            "runtime_surface_kind": "score_probe",
            "base_frame": bundle["data_source"]["base_frame"],
            "row_key": bundle["data_source"]["row_key"],
            "input_name": bundle["input_schema"]["input_name"],
            "input_dtype": bundle["input_schema"]["dtype"],
            "input_shape": [1, len(columns)],
            "feature_count": len(columns),
            "feature_order_hash": feature_order_hash(columns),
            "feature_columns_delimiter": "semicolon",
            "feature_columns_transport": "common_file_with_inline_fallback",
            "feature_columns_common_relative_path": f"{COMMON_REL_ROOT}\\{bundle['bundle_id']}\\feature_columns.txt",
            "output_name": "score",
            "output_contract": bundle["output_schema"]["mt5_output_contract"],
            "decision_family": bundle["decision_surface"]["decision_family"],
            "score_low_threshold": low,
            "score_high_threshold": high,
            "has_low_high_threshold": has_low_high,
            "decision_output": "telemetry_only_no_trades",
            "ea_feature_reconstruction": "closed_bar_CopyRates_shift_1_feature_columns_in_bundle_order",
        },
        "proxy_runtime_parity": {
            "status": "attempt_prepared_runtime_execution_pending",
            "shared_contract": [
                "US100_M5_closed_bar_base_frame",
                "feature_order_hash",
                "single_score_output",
                "period_profile_split_set_v0",
                "us100_m5_fpmarkets_tester_execution_v0",
            ],
            "known_differences": bundle["proxy_runtime_parity"]["known_differences"],
            "interpretation_drift_risks": bundle["proxy_runtime_parity"]["interpretation_drift_risks"],
            "minimum_reconciliation_attempt": {
                "status": "prepared",
                "attempt": "single_score_output_ONNX_contract_plus_feature_order_hash_plus_EA_feature_reconstruction",
                "forced_equality_required": False,
            },
            "unit_semantics": bundle["proxy_runtime_parity"]["unit_semantics"],
            "comparison_class": "pending_L4_terminal_execution",
            "divergence_judgment": "pending_L4_terminal_execution",
            "prevention_memory": [
                "Use common-file feature column transport for long Wave02 feature lists.",
                "Do not treat prepared tester configs as completed L4 evidence.",
                "Do not infer side/abstain economics from non-trading score telemetry.",
            ],
            "follow_up_action": "run Strategy Tester for this attempt and record telemetry/report hashes",
            "claim_boundary": "proxy_runtime_parity_tracking_only_no_runtime_authority",
        },
        "artifact_identity": {
            "ea_entrypoint": artifact_ref(REPO_ROOT / EA_SOURCE),
            "ea_binary": optional_artifact_ref(REPO_ROOT / EA_BINARY, availability="local_binary_hash_recorded_ignored_by_git"),
            "tester_config": {"path": repo_relative(REPO_ROOT, tester_config_path), "status": "pending_write"},
            "bundle": artifact_ref(bundle_path),
            "onnx_model": artifact_ref(onnx_path, availability="local_artifact_hash_recorded"),
            "common_files": common_copy,
            "tester_reports": [
                {
                    "path": report_path,
                    "status": "pending_terminal_execution",
                    "claim_boundary": "not_evidence_until_file_exists_and_hash_recorded",
                }
            ],
            "telemetry": {
                "common_relative_path": telemetry_common,
                "redacted_absolute_path": mt5_common_redacted(telemetry_common),
                "status": "pending_terminal_execution",
                "repo_copy": {
                    "path": f"runtime/mt5_attempts/{attempt_id}/telemetry/score_telemetry.csv",
                    "status": "pending_terminal_execution",
                },
            },
        },
        "provenance": {
            "command_argv": [durable_arg(arg) for arg in command_argv],
            "cwd": ".",
            "python_executable": mask_local_path(sys.executable),
            "python_version": platform.python_version(),
            "started_at_utc": created_at_utc,
            "ended_at_utc": utc_now(),
            "git_sha": run_git(["rev-parse", "HEAD"]),
            "branch": run_git(["branch", "--show-current"]),
            "input_hashes": [
                artifact_ref(bundle_path),
                artifact_ref(REPO_ROOT / RUNTIME_CONTRACT),
                artifact_ref(REPO_ROOT / PERIOD_PROFILE),
                artifact_ref(REPO_ROOT / EXECUTION_PROFILE),
                artifact_ref(REPO_ROOT / EA_SOURCE),
            ],
            "output_hashes": [],
        },
        "required_gate_coverage": {
            "passed": [
                "attempt_manifest",
                "period_profile_binding",
                "tester_execution_profile_binding",
                "feature_schema_contract",
                "bundle_integrity_hash",
                "runtime_surface_contract",
                "proxy_runtime_parity_record",
                "final_claim_guard",
            ],
            "missing": [
                "terminal_execution",
                "telemetry_rows",
                "tester_report",
                "L4_split_runtime_probe_completion",
            ],
            "not_applicable": ["locked_final_oos_b_access"],
        },
        "missing_evidence": [
            "Strategy_Tester_terminal_execution_pending",
            "score_telemetry_csv_pending",
            "tester_report_pending",
        ],
        "reopen_condition": "run prepared portable Strategy Tester attempt and record telemetry/report hashes",
        "next_action": NEXT_WORK_ITEM_ID,
        "forbidden_claims": FORBIDDEN_CLAIMS,
    }


def prepare_attempts(
    *,
    bundles: list[dict[str, Any]],
    runtime_contract: dict[str, Any],
    period_profile: dict[str, Any],
    execution_profile: dict[str, Any],
    command_argv: list[str],
    copy_to_common: bool,
    created_at_utc: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], Counter[str]]:
    runtime_period_set_id = runtime_contract["period_authority"]["default_runtime_period_set_id"]
    periods = required_l4_periods(period_profile, runtime_period_set_id)
    rows: list[dict[str, Any]] = []
    manifests: list[dict[str, Any]] = []
    copy_counts: Counter[str] = Counter()
    for bundle in bundles:
        common_copy = copy_common_files(bundle, enabled=copy_to_common)
        copy_counts.update(item["copy_status"] for item in common_copy.values())
        cell_id = (bundle.get("id_chain") or {}).get("cell_id")
        for period in periods:
            attempt_id = attempt_id_for(cell_id, period["period_role"])
            attempt_dir = REPO_ROOT / "runtime" / "mt5_attempts" / attempt_id
            tester_config_path = attempt_dir / "tester_config.ini"
            config_text = build_tester_config_text(
                attempt_id=attempt_id,
                bundle=bundle,
                period=period,
                execution_profile=execution_profile,
            )
            write_text(tester_config_path, config_text)
            manifest = build_attempt_manifest(
                attempt_id=attempt_id,
                bundle=bundle,
                period=period,
                runtime_contract=runtime_contract,
                period_profile=period_profile,
                execution_profile=execution_profile,
                tester_config_path=tester_config_path,
                common_copy=common_copy,
                created_at_utc=created_at_utc,
                command_argv=command_argv,
            )
            manifest["artifact_identity"]["tester_config"] = artifact_ref(tester_config_path)
            manifest["provenance"]["output_hashes"] = [artifact_ref(tester_config_path)]
            attempt_manifest_path = attempt_dir / "attempt_manifest.yaml"
            write_yaml(attempt_manifest_path, manifest)
            manifests.append(manifest)
            rows.append(
                {
                    "attempt_id": attempt_id,
                    "run_id": bundle["run_id"],
                    "bundle_id": bundle["bundle_id"],
                    "cell_id": cell_id,
                    "period_role": period["period_role"],
                    "from_date": period["from_date"],
                    "to_date": period["to_date"],
                    "status": ATTEMPT_STATUS,
                    "attempt_manifest_path": repo_relative(REPO_ROOT, attempt_manifest_path),
                    "tester_config_path": repo_relative(REPO_ROOT, tester_config_path),
                    "common_model_path": common_copy["model.onnx"]["common_relative_path"],
                    "common_model_copy_status": common_copy["model.onnx"]["copy_status"],
                    "telemetry_common_path": f"{COMMON_REL_ROOT}\\{attempt_id}\\score_telemetry.csv",
                    "feature_count": len(bundle["feature_schema_contract"]["feature_columns"]),
                    "decision_family": bundle["decision_surface"]["decision_family"],
                    "runtime_period_set_id": runtime_period_set_id,
                    "tester_execution_profile_id": execution_profile["profile_id"],
                    "claim_boundary": ATTEMPT_CLAIM_BOUNDARY,
                }
            )
    return rows, manifests, copy_counts


def onnx_index_fields() -> list[str]:
    return [
        "run_id",
        "cell_id",
        "bundle_id",
        "status",
        "bundle_manifest_path",
        "onnx_path",
        "onnx_sha256",
        "feature_count",
        "feature_order_hash",
        "model_family",
        "task_kind",
        "parity_status",
        "parity_max_abs_error",
        "claim_boundary",
    ]


def attempt_index_fields() -> list[str]:
    return [
        "attempt_id",
        "run_id",
        "bundle_id",
        "cell_id",
        "period_role",
        "from_date",
        "to_date",
        "status",
        "attempt_manifest_path",
        "tester_config_path",
        "common_model_path",
        "common_model_copy_status",
        "telemetry_common_path",
        "feature_count",
        "decision_family",
        "runtime_period_set_id",
        "tester_execution_profile_id",
        "claim_boundary",
    ]


def build_summaries(
    *,
    bundle_rows: list[dict[str, Any]],
    attempt_rows: list[dict[str, Any]],
    copy_counts: Counter[str],
    started_at_utc: str,
    command_argv: list[str],
    runtime_contract: dict[str, Any],
    period_profile: dict[str, Any],
    execution_profile: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    status_counts = Counter(row["status"] for row in bundle_rows)
    parity_counts = Counter(row["parity_status"] for row in bundle_rows)
    model_counts = Counter(row["model_family"] for row in bundle_rows)
    task_counts = Counter(row["task_kind"] for row in bundle_rows)
    role_counts = Counter(row["period_role"] for row in attempt_rows)
    runtime_period_set_id = runtime_contract["period_authority"]["default_runtime_period_set_id"]
    precheck = {
        "version": "writer_contract_precheck_v1",
        "work_item_id": WORK_ITEM_ID,
        "created_at_utc": started_at_utc,
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "primary_family": "onnx_export_parity",
        "primary_skill": "spacesonar-runtime-evidence",
        "source_of_truth_paths": [
            ONNX_SUMMARY.as_posix(),
            ONNX_INDEX.as_posix(),
            ATTEMPT_SUMMARY.as_posix(),
            ATTEMPT_INDEX.as_posix(),
        ],
        "hard_enforcement_points": {
            "writer_before_write": "applied",
            "writer_after_write": "applied",
            "boundary_before_main_push": "deferred_until_commit_scope_review",
        },
        "validation_depth": "writer_scope_smoke_plus_scoped_compile_parse",
        "skipped_broad_validations": ["pytest", "full_regression", "evidence_graph_full", "full_active_record_graph"],
        "next_action": NEXT_WORK_ITEM_ID,
    }
    onnx_summary = {
        "version": "wave02_l4_onnx_materialization_summary_v1",
        "summary_id": "wave02_l4_onnx_materialization_summary_v0",
        "work_item_id": WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": started_at_utc,
        "status": "completed_exportable_bundles_l4_terminal_execution_required",
        "claim_boundary": BUNDLE_CLAIM_BOUNDARY,
        "source_inputs": {
            "run_refs": RUN_REFS.as_posix(),
            "row_membership_manifest": ROW_MEMBERSHIP_MANIFEST.as_posix(),
            "runtime_contract": RUNTIME_CONTRACT.as_posix(),
            "period_profile": PERIOD_PROFILE.as_posix(),
            "tester_execution_profile": EXECUTION_PROFILE.as_posix(),
        },
        "input_hashes": [
            artifact_ref(REPO_ROOT / RUN_REFS),
            artifact_ref(REPO_ROOT / ROW_MEMBERSHIP_MANIFEST),
            artifact_ref(REPO_ROOT / RUNTIME_CONTRACT),
            artifact_ref(REPO_ROOT / PERIOD_PROFILE),
            artifact_ref(REPO_ROOT / EXECUTION_PROFILE),
            artifact_ref(REPO_ROOT / EA_SOURCE),
        ],
        "counts": {
            "valid_proxy_runs_requiring_l4": len(bundle_rows),
            "exportable_bundle_count": len(bundle_rows),
            "failed_materialization_count": 0,
            "status_counts": dict(sorted(status_counts.items())),
            "parity_status_counts": dict(sorted(parity_counts.items())),
            "model_family_counts": dict(sorted(model_counts.items())),
            "task_kind_counts": dict(sorted(task_counts.items())),
        },
        "artifact_outputs": {
            "index_csv": ONNX_INDEX.as_posix(),
            "bundle_manifest_paths": [row["bundle_manifest_path"] for row in bundle_rows],
            "onnx_paths": [row["onnx_path"] for row in bundle_rows],
        },
        "runtime_contract_binding": {
            "required_runtime_level": "L4_split_runtime_probe",
            "period_profile_id": period_profile["period_profile_id"],
            "runtime_period_set_id": runtime_period_set_id,
            "required_period_roles": runtime_contract["completion"]["required_period_roles"],
            "tester_execution_profile_id": execution_profile["profile_id"],
            "locked_final_oos_b": "excluded_forbidden_by_default",
        },
        "judgment": {
            "judgment_class": "onnx_bundle_preflight",
            "runtime_probe_completed": False,
            "runtime_authority": False,
            "economics_pass": False,
            "selected_baseline": False,
            "goal_achieve": False,
            "next_action": NEXT_WORK_ITEM_ID,
        },
        "environment": {
            "command": " ".join(durable_arg(arg) for arg in command_argv),
            "command_argv": [durable_arg(arg) for arg in command_argv],
            "cwd": ".",
            "python_executable": mask_local_path(sys.executable),
            "python_version": platform.python_version(),
            "dependency_summary": dependency_summary(),
            "started_at_utc": started_at_utc,
            "ended_at_utc": utc_now(),
            "git_sha": run_git(["rev-parse", "HEAD"]),
            "branch": run_git(["branch", "--show-current"]),
            "changed_files": git_status_lines(),
        },
        "forbidden_claims": FORBIDDEN_CLAIMS,
    }
    attempt_summary = {
        "version": "wave02_l4_attempt_preparation_summary_v1",
        "summary_id": "wave02_l4_attempt_preparation_summary_v0",
        "work_item_id": NEXT_WORK_ITEM_ID,
        "preparation_work_item_id": WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": started_at_utc,
        "status": "prepared_attempts_pending_terminal_execution",
        "claim_boundary": ATTEMPT_CLAIM_BOUNDARY,
        "source_inputs": {
            "onnx_materialization_summary": ONNX_SUMMARY.as_posix(),
            "onnx_materialization_index": ONNX_INDEX.as_posix(),
            "runtime_contract": RUNTIME_CONTRACT.as_posix(),
            "period_profile": PERIOD_PROFILE.as_posix(),
            "tester_execution_profile": EXECUTION_PROFILE.as_posix(),
        },
        "counts": {
            "exported_bundle_count": len(bundle_rows),
            "required_period_role_count": len(runtime_contract["completion"]["required_period_roles"]),
            "prepared_attempt_count": len(attempt_rows),
            "period_role_counts": dict(sorted(role_counts.items())),
            "common_copy_status_counts": dict(sorted(copy_counts.items())),
        },
        "runtime_contract_binding": {
            "required_runtime_level": "L4_split_runtime_probe",
            "period_profile_id": period_profile["period_profile_id"],
            "runtime_period_set_id": runtime_period_set_id,
            "required_period_roles": runtime_contract["completion"]["required_period_roles"],
            "tester_execution_profile_id": execution_profile["profile_id"],
            "locked_final_oos_b": "excluded_forbidden_by_default",
        },
        "artifact_outputs": {
            "index_csv": ATTEMPT_INDEX.as_posix(),
            "attempt_manifest_paths": [row["attempt_manifest_path"] for row in attempt_rows],
            "tester_config_paths": [row["tester_config_path"] for row in attempt_rows],
            "ea_source": EA_SOURCE.as_posix(),
            "ea_binary": EA_BINARY.as_posix() if path_exists(REPO_ROOT / EA_BINARY) else None,
        },
        "compile_smoke": {
            "ea_source": artifact_ref(REPO_ROOT / EA_SOURCE),
            "ea_binary": optional_artifact_ref(REPO_ROOT / EA_BINARY, availability="local_binary_hash_recorded_ignored_by_git"),
            "claim_boundary": "compile_smoke_only_not_strategy_tester_output",
        },
        "judgment": {
            "judgment_class": "runtime_attempt_preparation",
            "runtime_probe_completed": False,
            "runtime_authority": False,
            "economics_pass": False,
            "selected_baseline": False,
            "goal_achieve": False,
            "next_action": "Execute prepared portable Strategy Tester attempts for validation and research_oos, then record telemetry/report hashes.",
        },
        "prevention_memory": [
            "Feature-column strings use semicolon delimiter and common-file transport.",
            "Single-score ONNX output is required before MT5 L4 score probe consumption.",
            "Prepared attempt manifests are not L4 completion evidence until terminal telemetry/report hashes are recorded.",
            "Wave02 side/abstain proxy semantics require a later decision-execution adapter before economics can be discussed.",
        ],
        "environment": onnx_summary["environment"],
        "forbidden_claims": FORBIDDEN_CLAIMS,
    }
    return precheck, onnx_summary, attempt_summary


def build_closeout(onnx_summary: dict[str, Any], attempt_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "work_closeout_v1",
        "work_item_id": WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "created_at_utc": onnx_summary["created_at_utc"],
        "status": "completed_l4_preflight_terminal_execution_pending",
        "result_judgment": "inconclusive",
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "source_of_truth": ONNX_SUMMARY.as_posix(),
        "evidence_paths": [PRECHECK_SUMMARY.as_posix(), ONNX_SUMMARY.as_posix(), ONNX_INDEX.as_posix(), ATTEMPT_SUMMARY.as_posix(), ATTEMPT_INDEX.as_posix()],
        "summary_counts": {
            "onnx": onnx_summary["counts"],
            "attempts": attempt_summary["counts"],
        },
        "claim_effect": attempt_summary["judgment"],
        "next_work_item": {
            "work_item_id": NEXT_WORK_ITEM_ID,
            "path": NEXT_WORK_ITEM.as_posix(),
            "required_next_action": attempt_summary["judgment"]["next_action"],
        },
        "unresolved_blockers": ["L4_split_runtime_probe_terminal_execution_pending"],
        "reopen_conditions": ["run prepared portable Strategy Tester attempts and record telemetry/report hashes"],
        "forbidden_claims": FORBIDDEN_CLAIMS,
    }


def upsert_artifact_registry(bundle_rows: list[dict[str, Any]], attempt_rows: list[dict[str, Any]]) -> None:
    registry_path = REPO_ROOT / ARTIFACT_REGISTRY
    rows = read_csv_rows(registry_path) if path_exists(registry_path) else []
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
    by_id = {row.get("artifact_id", ""): row for row in rows}
    producer = "foundation/pipelines/materialize_wave02_tradeability_l4_preflight.py --write-control-records --copy-common-files"
    regen = f"python {producer}"

    def put(row: dict[str, str]) -> None:
        path = REPO_ROOT / row["path_or_uri"]
        if path_exists(path):
            row["sha256"] = sha256_file(path)
            row["size_bytes"] = str(os.stat(filesystem_path(path)).st_size)
        by_id[row["artifact_id"]] = {key: row.get(key, "") for key in fieldnames}

    for artifact_id, artifact_type, path, claim, notes in [
        ("artifact_wave02_l4_writer_precheck_v0", "writer_contract_precheck", PRECHECK_SUMMARY.as_posix(), NEXT_CLAIM_BOUNDARY, "writer contract guard record"),
        ("artifact_wave02_l4_onnx_materialization_summary_v0", "l4_onnx_materialization_summary", ONNX_SUMMARY.as_posix(), BUNDLE_CLAIM_BOUNDARY, "ONNX bundle preflight summary"),
        ("artifact_wave02_l4_onnx_materialization_index_v0", "l4_onnx_materialization_index", ONNX_INDEX.as_posix(), BUNDLE_CLAIM_BOUNDARY, "ONNX bundle preflight index"),
        ("artifact_wave02_l4_attempt_preparation_summary_v0", "l4_attempt_preparation_summary", ATTEMPT_SUMMARY.as_posix(), ATTEMPT_CLAIM_BOUNDARY, "prepared attempt summary; terminal execution pending"),
        ("artifact_wave02_l4_attempt_preparation_index_v0", "l4_attempt_preparation_index", ATTEMPT_INDEX.as_posix(), ATTEMPT_CLAIM_BOUNDARY, "prepared attempt index"),
        ("artifact_wave02_l4_score_probe_ea_source_v0", "mt5_ea_source", EA_SOURCE.as_posix(), ATTEMPT_CLAIM_BOUNDARY, "non-trading score telemetry EA source"),
    ]:
        put(
            {
                "artifact_id": artifact_id,
                "run_id": "",
                "bundle_id": "",
                "attempt_id": "",
                "artifact_type": artifact_type,
                "path_or_uri": path,
                "availability": "present_hash_recorded",
                "producer_command": producer,
                "regeneration_command": regen,
                "source_of_truth": path,
                "consumer": WORK_ITEM_ID,
                "claim_boundary": claim,
                "notes": notes,
            }
        )

    for row in bundle_rows:
        put(
            {
                "artifact_id": f"artifact_{row['bundle_id']}_manifest_v0",
                "run_id": row["run_id"],
                "bundle_id": row["bundle_id"],
                "attempt_id": "",
                "artifact_type": "experiment_bundle_manifest",
                "path_or_uri": row["bundle_manifest_path"],
                "availability": "present_hash_recorded",
                "producer_command": producer,
                "regeneration_command": regen,
                "source_of_truth": row["bundle_manifest_path"],
                "consumer": NEXT_WORK_ITEM_ID,
                "claim_boundary": BUNDLE_CLAIM_BOUNDARY,
                "notes": "ONNX bundle manifest; ONNX binary stored as ignored artifact with hash",
            }
        )
    for row in attempt_rows:
        put(
            {
                "artifact_id": f"artifact_{row['attempt_id']}_manifest_v0",
                "run_id": row["run_id"],
                "bundle_id": row["bundle_id"],
                "attempt_id": row["attempt_id"],
                "artifact_type": "attempt_manifest",
                "path_or_uri": row["attempt_manifest_path"],
                "availability": "present_hash_recorded",
                "producer_command": producer,
                "regeneration_command": regen,
                "source_of_truth": row["attempt_manifest_path"],
                "consumer": NEXT_WORK_ITEM_ID,
                "claim_boundary": ATTEMPT_CLAIM_BOUNDARY,
                "notes": "prepared L4 MT5 score probe attempt; terminal execution pending",
            }
        )
        put(
            {
                "artifact_id": f"artifact_{row['attempt_id']}_tester_config_v0",
                "run_id": row["run_id"],
                "bundle_id": row["bundle_id"],
                "attempt_id": row["attempt_id"],
                "artifact_type": "tester_config",
                "path_or_uri": row["tester_config_path"],
                "availability": "present_hash_recorded",
                "producer_command": producer,
                "regeneration_command": regen,
                "source_of_truth": row["attempt_manifest_path"],
                "consumer": NEXT_WORK_ITEM_ID,
                "claim_boundary": ATTEMPT_CLAIM_BOUNDARY,
                "notes": "Strategy Tester config for one period role",
            }
        )
    write_csv(registry_path, list(by_id.values()), fieldnames)


def ensure_list_item(values: list[Any], item: Any) -> None:
    if item not in values:
        values.append(item)


def update_control_records(onnx_summary: dict[str, Any], attempt_summary: dict[str, Any], closeout: dict[str, Any]) -> None:
    campaign_path = REPO_ROOT / CAMPAIGN_DIR / "campaign_manifest.yaml"
    campaign = read_yaml(campaign_path)
    campaign["updated_at_utc"] = onnx_summary["created_at_utc"]
    campaign["status"] = CAMPAIGN_STATUS
    campaign["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    campaign["next_action"] = NEXT_WORK_ITEM_ID
    campaign["l4_follow_through"] = {
        "onnx_materialization_summary": ONNX_SUMMARY.as_posix(),
        "onnx_materialization_status": onnx_summary["status"],
        "onnx_materialization_counts": onnx_summary["counts"],
        "attempt_preparation_summary": ATTEMPT_SUMMARY.as_posix(),
        "attempt_preparation_status": attempt_summary["status"],
        "attempt_preparation_counts": attempt_summary["counts"],
    }
    evidence_paths = campaign.setdefault("evidence_paths", [])
    for item in [ONNX_SUMMARY.as_posix(), ONNX_INDEX.as_posix(), ATTEMPT_SUMMARY.as_posix(), ATTEMPT_INDEX.as_posix()]:
        ensure_list_item(evidence_paths, item)
    campaign["missing_evidence"] = ["L4_split_runtime_probe_terminal_execution_pending"]
    write_yaml(campaign_path, campaign)

    next_work = {
        "version": "work_item_lite_v1",
        "work_item_id": NEXT_WORK_ITEM_ID,
        "primary_family": "runtime_probe",
        "primary_skill": "spacesonar-runtime-evidence",
        "verification_profile": "runtime_preflight_terminal_execution",
        "targets": [ATTEMPT_INDEX.as_posix(), ATTEMPT_SUMMARY.as_posix()],
        "acceptance_criteria": [
            "execute prepared validation and research_oos MT5 score-probe attempts",
            "record telemetry/report hashes before any L4 completion claim",
            "keep runtime_authority, economics_pass, candidate, live_readiness, and goal_achieve forbidden",
        ],
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "policy_binding": {
            "revision": "policy_contract_v2",
            "guards": [
                "GUARD_001_ATTEMPT_BEFORE_DISPOSITION",
                "GUARD_002_RUNTIME_COMPLETION_TRUTH",
                "GUARD_003_CLAIM_BOUNDARY",
                "GUARD_004_ARTIFACT_IDENTITY",
                "GUARD_007_OPERATIONAL_STABILITY",
            ],
        },
        "outputs": [
            "runtime/mt5_attempts/<attempt_id>/attempt_manifest.yaml",
            "runtime/mt5_attempts/<attempt_id>/telemetry/score_telemetry.csv",
            "runtime/mt5_attempts/<attempt_id>/reports/tester_report.htm",
        ],
        "next_action": "execute_prepared_wave02_l4_strategy_tester_attempts",
        "path": NEXT_WORK_ITEM.as_posix(),
        "summary": "Execute Wave02 prepared L4 Strategy Tester score-probe attempts.",
        "provenance": {
            "source": "wave02_l4_materialization_preflight",
            "campaign_id": CAMPAIGN_ID,
            "source_of_truth": ATTEMPT_SUMMARY.as_posix(),
        },
        "current_truth": {
            "onnx_materialization_summary": ONNX_SUMMARY.as_posix(),
            "attempt_preparation_summary": ATTEMPT_SUMMARY.as_posix(),
            "prepared_attempt_count": attempt_summary["counts"]["prepared_attempt_count"],
            "runtime_probe_completed": False,
            "candidate_count": 0,
            "l5_candidate_count": 0,
        },
        "unresolved_blockers": ["L4_split_runtime_probe_terminal_execution_pending"],
        "reopen_conditions": ["portable Strategy Tester execution records telemetry and completed report hashes"],
    }
    write_yaml(REPO_ROOT / NEXT_WORK_ITEM, next_work)

    resume = read_yaml(REPO_ROOT / RESUME_CURSOR)
    resume["updated_at_utc"] = onnx_summary["created_at_utc"]
    resume["cursor_state"] = "active_wave02_l4_attempts_prepared_terminal_execution_next"
    resume["active_phase"] = CAMPAIGN_STATUS
    resume["active_work_item_id"] = NEXT_WORK_ITEM_ID
    resume["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    resume["next_action"] = NEXT_WORK_ITEM_ID
    resume["unresolved_blockers"] = ["L4_split_runtime_probe_terminal_execution_pending"]
    truth_sources = resume.setdefault("current_truth_sources", [])
    for item in [ONNX_SUMMARY.as_posix(), ONNX_INDEX.as_posix(), ATTEMPT_SUMMARY.as_posix(), ATTEMPT_INDEX.as_posix(), CLOSEOUT_PATH.as_posix()]:
        ensure_list_item(truth_sources, item)
    resume["latest_completed_work"] = {
        "work_item_id": WORK_ITEM_ID,
        "result_judgment": "inconclusive",
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "evidence_paths": closeout["evidence_paths"],
    }
    write_yaml(REPO_ROOT / RESUME_CURSOR, resume)

    goal = read_yaml(REPO_ROOT / GOAL_MANIFEST)
    goal["updated_at_utc"] = onnx_summary["created_at_utc"]
    goal["active_phase"] = CAMPAIGN_STATUS
    goal["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    goal["next_work_item"] = {
        "work_item_id": NEXT_WORK_ITEM_ID,
        "path": NEXT_WORK_ITEM.as_posix(),
        "summary": "Execute prepared Wave02 L4 score-probe attempts.",
    }
    wave02 = goal.setdefault("wave02_tradeability_campaign", {})
    wave02.update(
        {
            "campaign_id": CAMPAIGN_ID,
            "status": CAMPAIGN_STATUS,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "l4_onnx_materialization_summary": ONNX_SUMMARY.as_posix(),
            "l4_onnx_materialization_status": onnx_summary["status"],
            "l4_onnx_materialization_counts": onnx_summary["counts"],
            "l4_attempt_preparation_summary": ATTEMPT_SUMMARY.as_posix(),
            "l4_attempt_preparation_status": attempt_summary["status"],
            "l4_attempt_preparation_counts": attempt_summary["counts"],
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "next_work_item": NEXT_WORK_ITEM_ID,
        }
    )
    write_yaml(REPO_ROOT / GOAL_MANIFEST, goal)

    workspace = read_yaml(REPO_ROOT / WORKSPACE_STATE)
    workspace["updated_utc"] = onnx_summary["created_at_utc"]
    workspace["current_claim_boundary"] = NEXT_CLAIM_BOUNDARY
    workspace["next_action"] = "Execute prepared Wave02 L4 score-probe attempts."
    workspace["unresolved_blockers"] = ["L4_split_runtime_probe_terminal_execution_pending"]
    workspace["active_work_item"] = {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()}
    workspace["wave02_tradeability_campaign"] = {
        "campaign_id": CAMPAIGN_ID,
        "status": CAMPAIGN_STATUS,
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "onnx_materialization_summary": ONNX_SUMMARY.as_posix(),
        "attempt_preparation_summary": ATTEMPT_SUMMARY.as_posix(),
        "prepared_attempt_count": attempt_summary["counts"]["prepared_attempt_count"],
        "candidate_count": 0,
        "l5_candidate_count": 0,
        "next_work_item": NEXT_WORK_ITEM_ID,
    }
    workspace.setdefault("summary_counts", {})["candidate_count"] = 0
    workspace.setdefault("summary_counts", {})["l5_candidate_count"] = 0
    write_yaml(REPO_ROOT / WORKSPACE_STATE, workspace)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize Wave02 tradeability ONNX bundles and prepared L4 MT5 attempts.")
    parser.add_argument("--run-refs", default=RUN_REFS.as_posix())
    parser.add_argument("--row-membership-manifest", default=ROW_MEMBERSHIP_MANIFEST.as_posix())
    parser.add_argument("--expected-branch", default="main")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--copy-common-files", action="store_true")
    parser.add_argument("--write-control-records", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    global RUN_REFS, ROW_MEMBERSHIP_MANIFEST
    RUN_REFS = Path(args.run_refs)
    ROW_MEMBERSHIP_MANIFEST = Path(args.row_membership_manifest)
    started_at_utc = utc_now()
    command_argv = sys.argv[:] if argv is None else ["foundation/pipelines/materialize_wave02_tradeability_l4_preflight.py", *argv]
    branch = branch_worktree(args.expected_branch)
    runtime_contract = read_yaml(REPO_ROOT / RUNTIME_CONTRACT)
    period_profile = read_yaml(REPO_ROOT / PERIOD_PROFILE)
    execution_profile = read_yaml(REPO_ROOT / EXECUTION_PROFILE)
    frame = load_row_membership(REPO_ROOT / ROW_MEMBERSHIP_MANIFEST)
    rows = run_refs()
    if args.limit is not None:
        rows = rows[: args.limit]

    bundles: list[dict[str, Any]] = []
    bundle_rows: list[dict[str, Any]] = []
    for row in rows:
        spec = load_run_spec(REPO_ROOT / row["run_spec_path"])
        bundle, bundle_row = materialize_bundle(
            run_spec=spec,
            frame=frame,
            command_argv=command_argv,
            branch=branch,
            runtime_contract=runtime_contract,
            period_profile=period_profile,
            execution_profile=execution_profile,
            started_at_utc=started_at_utc,
        )
        bundles.append(bundle)
        bundle_rows.append(bundle_row)

    attempt_rows, _attempt_manifests, copy_counts = prepare_attempts(
        bundles=bundles,
        runtime_contract=runtime_contract,
        period_profile=period_profile,
        execution_profile=execution_profile,
        command_argv=command_argv,
        copy_to_common=bool(args.copy_common_files),
        created_at_utc=started_at_utc,
    )
    precheck, onnx_summary, attempt_summary = build_summaries(
        bundle_rows=bundle_rows,
        attempt_rows=attempt_rows,
        copy_counts=copy_counts,
        started_at_utc=started_at_utc,
        command_argv=command_argv,
        runtime_contract=runtime_contract,
        period_profile=period_profile,
        execution_profile=execution_profile,
    )
    closeout = build_closeout(onnx_summary, attempt_summary)
    write_yaml(REPO_ROOT / PRECHECK_SUMMARY, precheck)
    write_yaml(REPO_ROOT / ONNX_SUMMARY, onnx_summary)
    write_csv(REPO_ROOT / ONNX_INDEX, bundle_rows, onnx_index_fields())
    write_yaml(REPO_ROOT / ATTEMPT_SUMMARY, attempt_summary)
    write_csv(REPO_ROOT / ATTEMPT_INDEX, attempt_rows, attempt_index_fields())
    write_yaml(REPO_ROOT / CLOSEOUT_PATH, closeout)
    upsert_artifact_registry(bundle_rows, attempt_rows)
    if args.write_control_records:
        update_control_records(onnx_summary, attempt_summary, closeout)

    print(
        json.dumps(
            {
                "status": CAMPAIGN_STATUS,
                "exported_bundle_count": len(bundle_rows),
                "prepared_attempt_count": len(attempt_rows),
                "claim_boundary": NEXT_CLAIM_BOUNDARY,
                "next_action": NEXT_WORK_ITEM_ID,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
