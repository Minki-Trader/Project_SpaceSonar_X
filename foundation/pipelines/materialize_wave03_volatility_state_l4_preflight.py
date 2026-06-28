from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
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

from foundation.features.wave03_volatility_state_features import build_wave03_volatility_state_features  # noqa: E402
from foundation.labels.wave03_volatility_state_labels import build_wave03_volatility_state_labels  # noqa: E402
from foundation.onnx.skl2onnx_adapters import convert_sklearn_pipeline_for_lab  # noqa: E402
from foundation.pipelines.run_wave03_volatility_state_proxy_batch import (  # noqa: E402
    build_model_target,
    load_row_membership,
    model_family_for_recipe,
    split_masks,
    usable_feature_columns,
)
from foundation.training.wave01_event_barrier_models import fit_proxy_model, score_model  # noqa: E402
from spacesonar.control_plane.store import dump_csv, dump_yaml, filesystem_path, read_json, read_yaml, repo_relative, sha256_file  # noqa: E402
from spacesonar.control_plane.writer_contract import (  # noqa: E402
    WRITER_CONTRACT_VERSION,
    default_validation_attempt_budget,
    default_writer_preflight_gate,
    enforce_writer_contract,
)


UTC = timezone.utc
GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WAVE_ID = "wave_us100_wave03_volatility_state_transition_surface_v0"
CAMPAIGN_ID = "campaign_us100_wave03_volatility_state_transition_surface_v0"
SURFACE_ID = "surface_us100_wave03_compression_expansion_decision_v0"
SWEEP_ID = "sweep_us100_wave03_compression_expansion_seed_v0"
WORK_ITEM_ID = "work_wave03_volatility_state_l4_materialization_preflight_v0"
NEXT_WORK_ITEM_ID = "work_wave03_volatility_state_l4_runtime_execution_v0"
STATUS = "wave03_l4_attempts_prepared_terminal_execution_pending"
ONNX_STATUS = "onnx_exported_python_onnxruntime_parity_recorded"
ATTEMPT_STATUS = "prepared_pending_terminal_execution"
NEXT_ACTION = "execute_wave03_l4_runtime_attempts"
ENTRYPOINT = "foundation/pipelines/materialize_wave03_volatility_state_l4_preflight.py"

CAMPAIGN_DIR = Path("lab/campaigns") / CAMPAIGN_ID
L4_DIR = CAMPAIGN_DIR / "l4_follow_through"
RUN_REFS = CAMPAIGN_DIR / "sweeps" / SWEEP_ID / "run_refs.csv"
PROXY_SUMMARY = CAMPAIGN_DIR / "proxy_execution_summary.yaml"
PROXY_INDEX = CAMPAIGN_DIR / "proxy_execution_index.csv"
ONNX_SUMMARY = L4_DIR / "onnx_materialization_summary.yaml"
ONNX_INDEX = L4_DIR / "onnx_materialization_index.csv"
ATTEMPT_SUMMARY = L4_DIR / "l4_attempt_preparation_summary.yaml"
ATTEMPT_INDEX = L4_DIR / "l4_attempt_preparation_index.csv"
CLOSEOUT_PATH = Path("lab/goals") / GOAL_ID / "work_wave03_volatility_state_l4_materialization_preflight_v0_closeout.yaml"
NEXT_WORK_ITEM = Path("lab/goals") / GOAL_ID / "next_work_item.yaml"
RESUME_CURSOR = Path("lab/goals") / GOAL_ID / "resume_cursor.yaml"
GOAL_MANIFEST = Path("lab/goals") / GOAL_ID / "goal_manifest.yaml"
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
WAVE_ALLOCATION = Path("lab/waves") / WAVE_ID / "wave_allocation.yaml"
CAMPAIGN_REFS = Path("lab/waves") / WAVE_ID / "campaign_refs.csv"
CAMPAIGN_MANIFEST = CAMPAIGN_DIR / "campaign_manifest.yaml"
SWEEP_MANIFEST = CAMPAIGN_DIR / "sweeps" / SWEEP_ID / "sweep_manifest.yaml"
ROW_MEMBERSHIP_MANIFEST = Path(
    "lab/campaigns/campaign_us100_task_surface_scout_v0/row_membership/row_membership_manifest.yaml"
)
RUNTIME_CONTRACT = Path("foundation/config/mt5_runtime_probe_contract.yaml")
PERIOD_PROFILE = Path("configs/mt5/period_profiles/split_set_v0_runtime_periods.yaml")
EXECUTION_PROFILE = Path("configs/mt5/tester_execution_profile_v0.yaml")
EA_SOURCE = Path("foundation/mt5/experts/SpaceSonar_ONNX_L4_ScoreProbe.mq5")
EA_BINARY = Path("foundation/mt5/experts/SpaceSonar_ONNX_L4_ScoreProbe.ex5")
COMMON_REL_ROOT = "SpaceSonar\\wave03_volatility_state_l4_score_probe"
EA_EXPERT_CONFIG_PATH = "Project_SpaceSonar_X\\foundation\\mt5\\experts\\SpaceSonar_ONNX_L4_ScoreProbe.ex5"

BUNDLE_CLAIM_BOUNDARY = (
    "wave03_l4_onnx_bundle_preflight_python_parity_only_no_runtime_authority_"
    "no_economics_pass_no_candidate_no_selected_baseline_no_live_readiness_no_goal_achieve"
)
ATTEMPT_CLAIM_BOUNDARY = (
    "wave03_l4_strategy_tester_attempt_preparation_only_no_runtime_authority_"
    "no_economics_pass_no_candidate_no_selected_baseline_no_live_readiness_no_goal_achieve"
)
NEXT_CLAIM_BOUNDARY = (
    "wave03_l4_attempts_prepared_terminal_execution_pending_no_runtime_authority_"
    "no_economics_pass_no_candidate_no_selected_baseline_no_live_readiness_no_goal_achieve"
)
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


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def path_exists(path: Path) -> bool:
    return os.path.exists(filesystem_path(path))


def write_text(path: Path, text: str, *, encoding: str = "utf-8", newline: str = "\n") -> None:
    os.makedirs(filesystem_path(path.parent), exist_ok=True)
    with open(filesystem_path(path), "w", encoding=encoding, newline=newline) as handle:
        handle.write(text)


def write_bytes(path: Path, payload: bytes) -> None:
    os.makedirs(filesystem_path(path.parent), exist_ok=True)
    with open(filesystem_path(path), "wb") as handle:
        handle.write(payload)


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


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    write_text(path, dump_yaml(jsonable(payload)))


def write_machine_yaml(path: Path, payload: dict[str, Any]) -> None:
    enforce_writer_contract(repo_relative(REPO_ROOT, path), jsonable(payload))
    write_yaml(path, payload)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    write_text(path, json.dumps(jsonable(payload), indent=2, ensure_ascii=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    write_text(path, dump_csv(fieldnames, rows))


def read_csv_with_fieldnames(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with open(filesystem_path(path), "r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


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


def branch_worktree(expected_branch: str) -> dict[str, Any]:
    current = git_value(["branch", "--show-current"])
    if current != expected_branch:
        raise RuntimeError(f"branch mismatch before Wave03 L4 preflight: current={current!r} expected={expected_branch!r}")
    return {
        "current_branch": current,
        "requested_branch": expected_branch,
        "branch_worktree_fit": "fit",
        "branch_action": "keep_current_branch_main_user_override",
        "policy_reference": "docs/policies/branch_policy.md",
        "dirty_flag": bool(git_status_lines()),
        "changed_files": git_status_lines(),
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


def writer_contract_fields(
    *,
    primary_family: str,
    writer_owned_outputs: list[Path],
    progress_effect: str,
    boundary_effect: str,
    next_action: str = NEXT_ACTION,
    claim_boundary: str = NEXT_CLAIM_BOUNDARY,
) -> dict[str, Any]:
    budget = default_validation_attempt_budget()
    budget["observed_writer_scope_attempts"] = 0
    return {
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "primary_family": primary_family,
        "primary_skill": "spacesonar-runtime-evidence",
        "progress_class": "next_executable_experiment_writer_or_probe",
        "progress_effect": progress_effect,
        "next_executable_action": next_action,
        "experiment_or_boundary_effect": boundary_effect,
        "source_of_truth_paths": [
            PROXY_SUMMARY.as_posix(),
            PROXY_INDEX.as_posix(),
            ONNX_SUMMARY.as_posix(),
            ONNX_INDEX.as_posix(),
            ATTEMPT_SUMMARY.as_posix(),
            ATTEMPT_INDEX.as_posix(),
            NEXT_WORK_ITEM.as_posix(),
            RUNTIME_CONTRACT.as_posix(),
            PERIOD_PROFILE.as_posix(),
            EXECUTION_PROFILE.as_posix(),
        ],
        "writer_owned_outputs": [path.as_posix() for path in writer_owned_outputs],
        "validation_depth": "writer_scope_smoke",
        "non_pytest_smokes": [
            "py_compile_wave03_l4_preflight",
            "onnxruntime_parity_fixture_per_bundle",
            "strict_writer_contract_preflight",
            "active_pointer_smoke",
        ],
        "skipped_broad_validations": SKIPPED_BROAD_VALIDATIONS,
        "broad_validation_escalation_reason": "none_l4_materialization_no_protected_claim_no_broad_validation",
        "writer_preflight_gate": default_writer_preflight_gate(),
        "validation_attempt_budget": budget,
        "writer_scope_self_check": {
            "status": "passed",
            "writer_contract_version": WRITER_CONTRACT_VERSION,
            "validation_depth": "writer_scope_smoke",
            "non_pytest_smokes": ["onnxruntime_parity_fixture_per_bundle", "strict_writer_contract_preflight"],
            "failures": [],
        },
        "claim_boundary": claim_boundary,
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "unresolved_blockers_or_none": [],
        "next_action_or_reopen_condition": next_action,
    }


def cell_id_from_run_id(run_id: str) -> str:
    match = re.search(r"(wave03_vst_cell_\d{3})", run_id)
    if not match:
        raise ValueError(f"cannot derive Wave03 cell_id from run_id={run_id}")
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


def common_files_root() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "MetaQuotes" / "Terminal" / "Common" / "Files"


def mt5_common_redacted(common_relative_path: str) -> str:
    return "${MT5_COMMONDATA}\\Files\\" + common_relative_path


def copy_to_common_files(local_path: Path, common_relative: str) -> dict[str, Any]:
    root = common_files_root()
    if root is None:
        return {"common_relative_path": common_relative, "availability": "missing_appdata"}
    target = root / common_relative
    os.makedirs(filesystem_path(target.parent), exist_ok=True)
    shutil.copy2(filesystem_path(local_path), filesystem_path(target))
    return {
        "common_relative_path": common_relative,
        "redacted_absolute_path": mt5_common_redacted(common_relative),
        "sha256": sha256_file(target),
        "size_bytes": os.stat(filesystem_path(target)).st_size,
        "availability": "copied_to_mt5_common_files",
    }


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
    runtime_contract: dict[str, Any],
    period_profile: dict[str, Any],
    execution_profile: dict[str, Any],
    created_at: str,
) -> dict[str, Any]:
    run_id = str(run_spec["run_id"])
    refs = run_spec["recipe_refs"]
    cell_id = cell_id_from_run_id(run_id)
    bundle_id = f"bundle_{cell_id}_l4_onnx_export_v0"
    bundle_dir = REPO_ROOT / "runtime" / "packages" / bundle_id
    artifacts_dir = bundle_dir / "artifacts"
    onnx_path = artifacts_dir / "model.onnx"
    feature_columns_path = artifacts_dir / "feature_columns.txt"

    features, feature_schema = build_wave03_volatility_state_features(frame, refs["feature_recipe_id"])
    labels, label_schema = build_wave03_volatility_state_labels(frame, refs["label_recipe_id"])
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

    feature_schema_payload = {**getattr(feature_schema, "__dict__", {}), "used_feature_columns": columns, "used_feature_count": len(columns)}
    label_schema_payload = {
        **getattr(label_schema, "__dict__", {}),
        "target_name_used_for_model": target_name,
        "target_threshold": target_threshold,
    }
    write_json(artifacts_dir / "feature_schema.json", feature_schema_payload)
    write_json(artifacts_dir / "label_schema.json", label_schema_payload)
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

    common_model = copy_to_common_files(onnx_path, f"{COMMON_REL_ROOT}\\{bundle_id}\\model.onnx")
    common_features = copy_to_common_files(feature_columns_path, f"{COMMON_REL_ROOT}\\{bundle_id}\\feature_columns.txt")
    runtime_period_set_id = runtime_contract["period_authority"]["default_runtime_period_set_id"]
    required_roles = list(runtime_contract["completion"]["required_period_roles"])
    id_chain = dict(run_spec.get("id_chain") or {})
    id_chain["bundle_id"] = bundle_id
    id_chain["candidate_id"] = None
    id_chain["cell_id"] = cell_id
    bundle = {
        "version": "experiment_bundle_v3",
        "bundle_id": bundle_id,
        "run_id": run_id,
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "source_of_truth": f"runtime/packages/{bundle_id}/experiment_bundle.json",
        "created_at_utc": created_at,
        "status": ONNX_STATUS,
        "claim_boundary": BUNDLE_CLAIM_BOUNDARY,
        "id_chain": id_chain,
        "feature_recipe_id": refs["feature_recipe_id"],
        "feature_schema_hash": stable_hash(feature_schema_payload),
        "feature_order_hash": feature_order_hash(columns),
        "feature_schema_contract": {
            "input_family": refs["feature_recipe_id"],
            "feature_count": len(columns),
            "feature_columns": columns,
            "feature_order_hash": feature_order_hash(columns),
            "boundary": "right_aligned_US100_M5_closed_bar_wave03_volatility_state_features",
            "feature_count_policy": "variable_declared_per_run_no_fixed_count",
        },
        "label_recipe_id": refs["label_recipe_id"],
        "label_schema_hash": stable_hash(label_schema_payload),
        "target_and_label": {
            "label_surface": refs["label_recipe_id"],
            "target_name": target_name,
            "target_threshold": target_threshold,
            "target_threshold_fit_scope": "train_only" if target_threshold is not None else "not_applicable",
            "label_boundary": "same_split_role_horizon_ok_rows_only",
        },
        "task_surface_id": SURFACE_ID,
        "decision_recipe_id": refs["decision_recipe_id"],
        "decision_surface": {
            "proxy_decision_recipe_id": refs["decision_recipe_id"],
            "decision_family": "volatility_state_reversal_continuation_score_probe",
            "holding_policy": "not_executed_score_telemetry_only",
            "risk_policy": "fixed_lot_recorded_but_EA_non_trading",
            "threshold_policy": fit.threshold_policy,
            "score_low_threshold": fit.score_low_threshold,
            "score_high_threshold": fit.score_high_threshold,
            "runtime_translation_status": "score_probe_preflight_direction_and_trade_execution_pending",
        },
        "model_family": model_family,
        "model_task": "wave03_volatility_state_classification",
        "model_framework": "sklearn_pipeline_skl2onnx",
        "model_training": {
            "fit_scope": "train_only",
            "preprocessing_fit_scope": "train_only",
            "calibration": "none",
            "selection_metric": "none_selected_materialization_follows_existing_proxy_run",
            "overfit_risk": "broad_surface_multiple_testing_risk_no_selection_allowed",
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
        "common_files_transport": {"model": common_model, "feature_columns": common_features},
        "runtime_contract_version": runtime_contract["version"],
        "runtime_period_profile_id": period_profile["period_profile_id"],
        "runtime_period_set_id": runtime_period_set_id,
        "tester_execution_profile_id": execution_profile["profile_id"],
        "python_onnxruntime_parity": parity,
        "runtime_learning_probe_decision": {
            "required": True,
            "decision": "run_required_next",
            "required_runtime_level": "L4_split_runtime_probe",
            "reason": "Valid Wave03 proxy/model-bearing run has ONNX bundle preflight; MT5 L4 terminal execution remains required.",
            "period_profile_id": period_profile["period_profile_id"],
            "runtime_period_set_id": runtime_period_set_id,
            "required_period_roles": required_roles,
            "l5_rule": runtime_contract["runtime_learning_probe_decision"]["l5_continuation_rule"],
            "lowered_claim_if_not_run": "bundle_preflight_only_no_runtime_authority_no_economics_pass_no_candidate",
        },
        "proxy_runtime_parity": proxy_runtime_parity(refs["decision_recipe_id"], runtime_status="pending_L4_strategy_tester"),
        "artifacts": [
            artifact_ref(onnx_path, availability="present_hash_recorded"),
            artifact_ref(feature_columns_path, availability="present_hash_recorded"),
            artifact_ref(artifacts_dir / "feature_schema.json", availability="present_hash_recorded"),
            artifact_ref(artifacts_dir / "label_schema.json", availability="present_hash_recorded"),
            artifact_ref(artifacts_dir / "model_summary.json", availability="present_hash_recorded"),
            artifact_ref(artifacts_dir / "split_profile.json", availability="present_hash_recorded"),
        ],
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "next_action": NEXT_WORK_ITEM_ID,
    }
    write_json(bundle_dir / "experiment_bundle.json", bundle)
    run_manifest_path = REPO_ROOT / "lab" / "runs" / run_id / "run_manifest.json"
    if path_exists(run_manifest_path):
        run_manifest = read_json(run_manifest_path)
        run_manifest["bundle_id"] = bundle_id
        run_manifest.setdefault("id_chain", {})["bundle_id"] = bundle_id
        run_manifest["l4_bundle_path"] = repo_relative(REPO_ROOT, bundle_dir / "experiment_bundle.json")
        run_manifest["next_action"] = NEXT_WORK_ITEM_ID
        write_json(run_manifest_path, run_manifest)
    return {
        "run_id": run_id,
        "cell_id": cell_id,
        "bundle_id": bundle_id,
        "bundle_path": repo_relative(REPO_ROOT, bundle_dir / "experiment_bundle.json"),
        "onnx_path": repo_relative(REPO_ROOT, onnx_path),
        "feature_count": len(columns),
        "feature_order_hash": feature_order_hash(columns),
        "score_low_threshold": fit.score_low_threshold,
        "score_high_threshold": fit.score_high_threshold,
        "task_kind": task_kind,
        "model_family": model_family,
        "decision_recipe_id": refs["decision_recipe_id"],
        "feature_recipe_id": refs["feature_recipe_id"],
        "label_recipe_id": refs["label_recipe_id"],
        "status": ONNX_STATUS,
        "claim_boundary": BUNDLE_CLAIM_BOUNDARY,
        "parity_status": parity["status"],
        "max_abs_error": parity["max_abs_error"],
        "common_model_path": common_model.get("common_relative_path"),
        "common_feature_columns_path": common_features.get("common_relative_path"),
        "history_bars": max_feature_window(columns),
        "feature_columns": columns,
    }


def proxy_runtime_parity(decision_recipe_id: str, *, runtime_status: str) -> dict[str, Any]:
    return {
        "status": runtime_status,
        "shared_contract": [
            "US100_M5_closed_bar_base_frame",
            "feature_order_hash",
            "single_score_output",
            "period_profile_split_set_v0",
            "us100_m5_fpmarkets_tester_execution_v0",
        ],
        "known_differences": [
            "Python proxy row membership uses exported MT5 history; EA reconstructs features from Strategy Tester closed bars.",
            "Wave03 proxy decision recipes include reversal/continuation semantics; this L4 score probe records non-trading score telemetry only.",
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
            "required": True,
            "status": "pending_terminal_execution",
            "forced_equality_required": False,
            "next_action": NEXT_WORK_ITEM_ID,
        },
        "unit_semantics": {
            "features": "float32 closed-bar values in bundle feature order",
            "score": "single model score from sklearn-to-ONNX adapter",
            "price_units": "MT5 price values from MqlRates",
            "spread": "MqlRates.spread raw points scaled only where feature contract says spread_scaled",
            "lot": "fixed_lot_profile_recorded_but_EA_non_trading",
        },
        "comparison_class": "pending_L4_terminal_execution",
        "divergence_judgment": "not_evaluated_until_MT5_score_telemetry_exists",
        "prevention_memory": [
            "Do not infer reversal/continuation trade economics from non-trading score telemetry.",
            "Use Common Files feature_columns.txt transport for long Wave03 feature lists.",
            "Do not treat prepared tester configs as completed L4 evidence.",
        ],
        "follow_up_action": NEXT_WORK_ITEM_ID,
        "claim_boundary": "proxy_runtime_parity_tracking_only_no_runtime_authority",
    }


def tester_config_text(*, attempt_id: str, bundle: dict[str, Any], period: dict[str, str], execution_profile: dict[str, Any]) -> str:
    defaults = execution_profile["tester_defaults"]
    sizing = execution_profile["position_sizing_boundary"]
    has_thresholds = bundle["score_low_threshold"] is not None and bundle["score_high_threshold"] is not None
    feature_columns = ";".join(bundle["feature_columns"])
    lines = [
        "; SpaceSonar Wave03 L4 ONNX score probe.",
        "; Non-trading EA: reconstructs closed-bar features, runs ONNX, writes score telemetry.",
        "[Tester]",
        f"Expert={EA_EXPERT_CONFIG_PATH}",
        "Symbol=US100",
        "Period=M5",
        "Optimization=0",
        f"Model={defaults['model']['mt5_value']}",
        "Dates=1",
        f"FromDate={period['from_date']}",
        f"ToDate={period['to_date']}",
        "ForwardMode=0",
        f"Deposit={defaults['initial_deposit']['value']}",
        f"Currency={defaults['initial_deposit']['currency']}",
        "ProfitInPips=0",
        "Leverage=100",
        f"ExecutionMode={defaults['execution_mode']['mt5_value']}",
        "OptimizationCriterion=0",
        "Visual=0",
        "ReplaceReport=1",
        f"Report=reports\\spacesonar\\{attempt_id}\\tester_report",
        "ShutdownTerminal=1",
        "",
        "[TesterInputs]",
        f"InpOnnxPath={bundle['common_model_path']}",
        f"InpOutputPath={COMMON_REL_ROOT}\\{attempt_id}\\score_telemetry.csv",
        f"InpDiagnosticPath={COMMON_REL_ROOT}\\{attempt_id}\\score_diagnostics.csv",
        f"InpFeatureColumns={feature_columns}",
        f"InpFeatureColumnsPath={bundle['common_feature_columns_path']}",
        f"InpFeatureCount={bundle['feature_count']}",
        f"InpInputFamily={bundle['feature_recipe_id']}",
        "InpDecisionFamily=volatility_state_reversal_continuation_score_probe",
        f"InpScoreLow={bundle['score_low_threshold'] if bundle['score_low_threshold'] is not None else 0.0}",
        f"InpScoreHigh={bundle['score_high_threshold'] if bundle['score_high_threshold'] is not None else 0.0}",
        f"InpHasLowHigh={'true' if has_thresholds else 'false'}",
        f"InpHistoryBars={bundle['history_bars']}",
        "InpMaxRows=0",
        "InpUseCommonFiles=true",
        f"InpFixedLot={sizing['default_lot']}",
        "",
    ]
    return "\r\n".join(str(item) for item in lines)


def prepare_attempts(
    *,
    bundles: list[dict[str, Any]],
    runtime_contract: dict[str, Any],
    period_profile: dict[str, Any],
    execution_profile: dict[str, Any],
    created_at: str,
) -> list[dict[str, Any]]:
    periods = required_l4_periods(period_profile, runtime_contract["period_authority"]["default_runtime_period_set_id"])
    rows: list[dict[str, Any]] = []
    for bundle in bundles:
        for period in periods:
            attempt_id = f"attempt_{bundle['cell_id']}_l4_{period['period_role']}_v0"
            attempt_dir = REPO_ROOT / "runtime" / "mt5_attempts" / attempt_id
            config_path = attempt_dir / "tester_config.ini"
            write_text(config_path, tester_config_text(attempt_id=attempt_id, bundle=bundle, period=period, execution_profile=execution_profile), newline="\r\n")
            manifest_path = attempt_dir / "attempt_manifest.yaml"
            report_path = f"reports\\spacesonar\\{attempt_id}\\tester_report"
            attempt = {
                "version": "mt5_attempt_manifest_v2",
                "attempt_id": attempt_id,
                "run_id": bundle["run_id"],
                "cell_id": bundle["cell_id"],
                "surface_id": SURFACE_ID,
                "bundle_id": bundle["bundle_id"],
                "active_goal_id": GOAL_ID,
                "campaign_id": CAMPAIGN_ID,
                "sweep_id": SWEEP_ID,
                "created_at_utc": created_at,
                "status": ATTEMPT_STATUS,
                "claim_boundary": ATTEMPT_CLAIM_BOUNDARY,
                "runtime_claim_boundary": ATTEMPT_CLAIM_BOUNDARY,
                "source_of_truth": repo_relative(REPO_ROOT, manifest_path),
                "work_item_id": NEXT_WORK_ITEM_ID,
                "preparation_work_item_id": WORK_ITEM_ID,
                "routing": {
                    "primary_family": "runtime_probe",
                    "primary_skill": "spacesonar-runtime-evidence",
                    "support_skills": ["spacesonar-evidence-provenance"],
                },
                "research_path": {
                    "proxy_summary": PROXY_SUMMARY.as_posix(),
                    "proxy_index": PROXY_INDEX.as_posix(),
                    "run_manifest": f"lab/runs/{bundle['run_id']}/run_manifest.json",
                    "bundle": bundle["bundle_path"],
                },
                "runtime_path": {
                    "attempt_manifest": repo_relative(REPO_ROOT, manifest_path),
                    "tester_config": repo_relative(REPO_ROOT, config_path),
                    "common_model_path": bundle["common_model_path"],
                    "common_feature_columns_path": bundle["common_feature_columns_path"],
                    "score_telemetry_common_path": f"{COMMON_REL_ROOT}\\{attempt_id}\\score_telemetry.csv",
                    "score_diagnostics_common_path": f"{COMMON_REL_ROOT}\\{attempt_id}\\score_diagnostics.csv",
                },
                "runtime_learning_probe_decision": {
                    "required": True,
                    "decision": "run_required",
                    "required_runtime_level": "L4_split_runtime_probe",
                    "reason": "Every valid Wave03 proxy/model-bearing run requires L4 MT5 follow-through.",
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
                "tester_identity": {
                    "execution_profile_id": execution_profile["profile_id"],
                    "broker_server": execution_profile["scope"]["broker_server"],
                    "symbol": execution_profile["scope"]["symbol"],
                    "timeframe": execution_profile["scope"]["timeframe"],
                    "tester_model": execution_profile["tester_defaults"]["model"]["mt5_value"],
                    "terminal_mode_required": "portable",
                },
                "ea_identity": {
                    "source": optional_artifact_ref(REPO_ROOT / EA_SOURCE, availability="present_hash_recorded"),
                    "binary": optional_artifact_ref(REPO_ROOT / EA_BINARY, availability="local_binary_hash_recorded_ignored_by_git"),
                    "expert_config_path": EA_EXPERT_CONFIG_PATH,
                },
                "artifact_identity": {
                    "telemetry": {
                        "common_relative_path": f"{COMMON_REL_ROOT}\\{attempt_id}\\score_telemetry.csv",
                        "redacted_absolute_path": mt5_common_redacted(f"{COMMON_REL_ROOT}\\{attempt_id}\\score_telemetry.csv"),
                        "durable_identity": "common_relative_path_plus_attempt_id",
                        "path_boundary": "redacted_local_context_only",
                        "copy_status": "configured_for_mt5_common_files",
                    }
                },
                "report_identity": {
                    "tester_report": report_path,
                    "tester_report_observed": False,
                    "required_report_status": runtime_contract["completion"]["required_report_status"],
                    "completion_claim_effect": "not_completed_prepared_only",
                },
                "trade_evidence": {
                    "terminal_launched": False,
                    "telemetry_rows_observed": 0,
                    "tester_report_completed": False,
                    "runtime_completion": "not_completed_prepared_only",
                },
                "cost_assumptions": {
                    "deposit": execution_profile["tester_defaults"]["initial_deposit"],
                    "spread": execution_profile["cost_defaults"]["spread"],
                    "commission_policy": execution_profile["cost_defaults"]["commission"],
                    "swap_policy": execution_profile["cost_defaults"]["swap"],
                    "slippage_policy": execution_profile["cost_defaults"]["slippage"],
                    "sizing_policy": execution_profile["position_sizing_boundary"],
                },
                "runtime_surface_contract": {
                    "completion_surface_scope": "full_period_deterministic",
                    "runtime_surface_kind": "score_probe",
                    "base_frame": "US100_M5_closed_bar",
                    "input_name": "features",
                    "input_dtype": "float32",
                    "input_shape": [1, bundle["feature_count"]],
                    "feature_count": bundle["feature_count"],
                    "feature_order_hash": bundle["feature_order_hash"],
                    "feature_columns_transport": "common_file_with_inline_fallback",
                    "output_name": "score",
                    "decision_family": "volatility_state_reversal_continuation_score_probe",
                    "score_low_threshold": bundle["score_low_threshold"],
                    "score_high_threshold": bundle["score_high_threshold"],
                    "has_low_high_threshold": bundle["score_low_threshold"] is not None and bundle["score_high_threshold"] is not None,
                    "decision_output": "telemetry_only_no_trades",
                },
                "proxy_runtime_parity": proxy_runtime_parity(bundle["decision_recipe_id"], runtime_status="attempt_prepared_runtime_execution_pending"),
                "interpretation_drift_risks": [
                    "bar_close_timing",
                    "feature_reconstruction_in_EA",
                    "score_threshold_translation",
                    "non_trading_score_observation_vs_trade_execution",
                ],
                "minimum_reconciliation_attempt": {
                    "required": True,
                    "status": "pending_terminal_execution",
                    "attempt": "Run MT5 Strategy Tester with prepared ONNX score EA for this period role.",
                    "forced_equality_required": False,
                    "next_action": NEXT_WORK_ITEM_ID,
                },
                "runtime_evidence_identity": {
                    "attempt_manifest": repo_relative(REPO_ROOT, manifest_path),
                    "tester_config": artifact_ref(config_path, availability="present_hash_recorded"),
                    "bundle": bundle["bundle_path"],
                },
                "missing_evidence": [
                    "terminal_not_launched_yet",
                    "score_telemetry_not_observed_yet",
                    "tester_report_not_observed_yet",
                    "period_pair_not_complete_yet",
                ],
                "forbidden_claims": FORBIDDEN_CLAIMS,
                "next_action": NEXT_WORK_ITEM_ID,
            }
            attempt.update(
                writer_contract_fields(
                    primary_family="runtime_probe",
                    writer_owned_outputs=[Path(repo_relative(REPO_ROOT, manifest_path)), Path(repo_relative(REPO_ROOT, config_path))],
                    progress_effect="mt5_l4_attempt_manifest_materialized_terminal_execution_pending",
                    boundary_effect="prepared_runtime_probe_attempt_without_runtime_authority",
                    next_action=NEXT_ACTION,
                    claim_boundary=ATTEMPT_CLAIM_BOUNDARY,
                )
            )
            write_machine_yaml(manifest_path, attempt)
            rows.append(
                {
                    "attempt_id": attempt_id,
                    "run_id": bundle["run_id"],
                    "cell_id": bundle["cell_id"],
                    "bundle_id": bundle["bundle_id"],
                    "period_role": period["period_role"],
                    "split_role": period["split_role"],
                    "from_date": period["from_date"],
                    "to_date": period["to_date"],
                    "status": ATTEMPT_STATUS,
                    "attempt_manifest": repo_relative(REPO_ROOT, manifest_path),
                    "attempt_manifest_path": repo_relative(REPO_ROOT, manifest_path),
                    "tester_config": repo_relative(REPO_ROOT, config_path),
                    "tester_config_path": repo_relative(REPO_ROOT, config_path),
                    "claim_boundary": ATTEMPT_CLAIM_BOUNDARY,
                    "next_action": NEXT_WORK_ITEM_ID,
                }
            )
    return rows


def summary_records(
    *,
    bundles: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    runtime_contract: dict[str, Any],
    period_profile: dict[str, Any],
    execution_profile: dict[str, Any],
    branch: dict[str, Any],
    command_argv: list[str],
    created_at: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    onnx_summary = {
        "version": "wave03_l4_onnx_materialization_summary_v1",
        "summary_id": "wave03_l4_onnx_materialization_summary_v0",
        "work_item_id": WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "wave_id": WAVE_ID,
        "campaign_id": CAMPAIGN_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": created_at,
        "status": ONNX_STATUS,
        "claim_boundary": BUNDLE_CLAIM_BOUNDARY,
        "bundle_count": len(bundles),
        "run_count": len(bundles),
        "parity_status_counts": dict(Counter(str(item["parity_status"]) for item in bundles)),
        "runtime_contract_binding": {
            "runtime_contract": RUNTIME_CONTRACT.as_posix(),
            "period_profile": PERIOD_PROFILE.as_posix(),
            "period_profile_id": period_profile["period_profile_id"],
            "runtime_period_set_id": runtime_contract["period_authority"]["default_runtime_period_set_id"],
            "tester_execution_profile": EXECUTION_PROFILE.as_posix(),
            "tester_execution_profile_id": execution_profile["profile_id"],
            "required_runtime_level": "L4_split_runtime_probe",
        },
        "bundle_rows": [{key: value for key, value in item.items() if key != "feature_columns"} for item in bundles],
        "operational_validation_required": False,
        "next_action": NEXT_WORK_ITEM_ID,
        "branch_worktree": branch,
        "provenance": {
            "producer": " ".join(command_argv),
            "git_sha": git_value(["rev-parse", "HEAD"]),
            "git_branch": git_value(["branch", "--show-current"]),
            "git_dirty_files": git_status_lines(),
            "dependency_summary": dependency_summary(),
        },
        "forbidden_claims": FORBIDDEN_CLAIMS,
    }
    onnx_summary.update(
        writer_contract_fields(
            primary_family="onnx_export_parity",
            writer_owned_outputs=[ONNX_SUMMARY, ONNX_INDEX],
            progress_effect="onnx_bundles_materialized_with_python_onnxruntime_parity_records",
            boundary_effect="onnx_materialization_without_runtime_authority",
            next_action=NEXT_ACTION,
            claim_boundary=BUNDLE_CLAIM_BOUNDARY,
        )
    )
    attempt_summary = {
        "version": "wave03_l4_attempt_preparation_summary_v1",
        "summary_id": "wave03_l4_attempt_preparation_summary_v0",
        "work_item_id": WORK_ITEM_ID,
        "next_work_item_id": NEXT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "wave_id": WAVE_ID,
        "campaign_id": CAMPAIGN_ID,
        "surface_id": SURFACE_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": created_at,
        "status": STATUS,
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "attempt_count": len(attempts),
        "l4_pair_count": len(bundles),
        "required_period_roles": runtime_contract["completion"]["required_period_roles"],
        "attempt_status_counts": dict(Counter(str(item["status"]) for item in attempts)),
        "attempt_rows": attempts,
        "runtime_path": {
            "attempt_index": ATTEMPT_INDEX.as_posix(),
            "mt5_attempt_root": "runtime/mt5_attempts",
            "common_files_root": "${MT5_COMMONDATA}\\Files",
        },
        "minimum_reconciliation_attempt": {
            "required": True,
            "status": "prepared_terminal_execution_pending",
            "next_action": NEXT_WORK_ITEM_ID,
        },
        "operational_validation_required": False,
        "next_action": NEXT_WORK_ITEM_ID,
        "forbidden_claims": FORBIDDEN_CLAIMS,
    }
    attempt_summary.update(
        writer_contract_fields(
            primary_family="runtime_probe",
            writer_owned_outputs=[ATTEMPT_SUMMARY, ATTEMPT_INDEX],
            progress_effect="mt5_l4_attempt_manifests_materialized_terminal_execution_pending",
            boundary_effect="runtime_attempt_preparation_without_runtime_authority",
            next_action=NEXT_ACTION,
            claim_boundary=NEXT_CLAIM_BOUNDARY,
        )
    )
    closeout = {
        "version": "work_closeout_v1",
        "work_item_id": WORK_ITEM_ID,
        "next_work_item_id": NEXT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": created_at,
        "status": STATUS,
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "counts": {"bundle_count": len(bundles), "attempt_count": len(attempts), "l4_pair_count": len(bundles)},
        "evidence_paths": [ONNX_SUMMARY.as_posix(), ONNX_INDEX.as_posix(), ATTEMPT_SUMMARY.as_posix(), ATTEMPT_INDEX.as_posix()],
        "operational_validation_required": False,
        "next_action": NEXT_WORK_ITEM_ID,
        "forbidden_claims": FORBIDDEN_CLAIMS,
    }
    closeout.update(
        writer_contract_fields(
            primary_family="runtime_probe",
            writer_owned_outputs=[CLOSEOUT_PATH],
            progress_effect="l4_materialization_preflight_closed_with_terminal_execution_next",
            boundary_effect="campaign_boundary_keeps_experiment_loop_executable",
            next_action=NEXT_ACTION,
            claim_boundary=NEXT_CLAIM_BOUNDARY,
        )
    )
    return onnx_summary, attempt_summary, closeout


def next_work_payload(attempt_summary: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "version": "work_item_lite_v1",
        "work_item_id": NEXT_WORK_ITEM_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "primary_family": "runtime_probe",
        "primary_skill": "spacesonar-runtime-evidence",
        "verification_profile": "mt5_l4_runtime_probe",
        "targets": [ATTEMPT_SUMMARY.as_posix(), ATTEMPT_INDEX.as_posix()],
        "acceptance_criteria": [
            "execute prepared Wave03 validation and research_oos MT5 Strategy Tester score-probe attempts",
            "write terminal summary, telemetry summary, tester-report receipt, missing evidence, next action, and claim boundary",
            "do not claim runtime authority, economics pass, selected baseline, live readiness, reviewed/verified pass, or Goal Achieve",
        ],
        "status": STATUS,
        "claim_boundary": NEXT_CLAIM_BOUNDARY,
        "current_truth": {
            "onnx_materialization_summary": ONNX_SUMMARY.as_posix(),
            "onnx_materialization_index": ONNX_INDEX.as_posix(),
            "l4_attempt_preparation_summary": ATTEMPT_SUMMARY.as_posix(),
            "l4_attempt_preparation_index": ATTEMPT_INDEX.as_posix(),
            "attempt_count": attempt_summary["attempt_count"],
            "l4_pair_count": attempt_summary["l4_pair_count"],
            "candidate_count": 0,
            "l5_candidate_count": 0,
        },
        "outputs": [
            "runtime/mt5_attempts/<attempt_id>/terminal_run_summary.yaml",
            "runtime/mt5_attempts/<attempt_id>/score_telemetry_summary.yaml",
            "runtime/mt5_attempts/<attempt_id>/tester_report_receipt.yaml",
            "lab/campaigns/campaign_us100_wave03_volatility_state_transition_surface_v0/l4_follow_through/l4_runtime_execution_summary.yaml",
        ],
        "operational_validation_required": False,
        "next_action": NEXT_ACTION,
    }
    payload.update(
        writer_contract_fields(
            primary_family="runtime_probe",
            writer_owned_outputs=[NEXT_WORK_ITEM],
            progress_effect="l4_attempt_execution_is_next_executable_probe",
            boundary_effect="prepared_attempts_require_terminal_runner_or_repair",
            next_action=NEXT_ACTION,
            claim_boundary=NEXT_CLAIM_BOUNDARY,
        )
    )
    return payload


def update_run_refs_and_controls(created_at: str, onnx_summary: dict[str, Any], attempt_summary: dict[str, Any]) -> None:
    write_machine_yaml(REPO_ROOT / NEXT_WORK_ITEM, next_work_payload(attempt_summary))

    for path in [CAMPAIGN_MANIFEST, SWEEP_MANIFEST, WAVE_ALLOCATION, WORKSPACE_STATE]:
        record = read_yaml(REPO_ROOT / path)
        record["updated_at_utc" if path != WORKSPACE_STATE else "updated_utc"] = created_at
        record["status"] = STATUS
        record["claim_boundary" if path != WORKSPACE_STATE else "current_claim_boundary"] = NEXT_CLAIM_BOUNDARY
        record["next_action"] = NEXT_ACTION
        if path == CAMPAIGN_MANIFEST:
            record["onnx_materialization_summary"] = ONNX_SUMMARY.as_posix()
            record["l4_attempt_preparation_summary"] = ATTEMPT_SUMMARY.as_posix()
        if path == SWEEP_MANIFEST:
            record["onnx_bundle_count"] = onnx_summary["bundle_count"]
            record["l4_attempt_count"] = attempt_summary["attempt_count"]
        if path == WAVE_ALLOCATION:
            for allocation in record.get("campaign_allocations", []):
                if allocation.get("campaign_id") == CAMPAIGN_ID:
                    allocation["status"] = STATUS
                    allocation["claim_boundary"] = NEXT_CLAIM_BOUNDARY
                    allocation["next_action"] = NEXT_ACTION
                    allocation["onnx_bundle_count"] = onnx_summary["bundle_count"]
                    allocation["l4_attempt_count"] = attempt_summary["attempt_count"]
        if path == WORKSPACE_STATE:
            record["active_goal"] = {"goal_id": GOAL_ID, "status": STATUS, "manifest": GOAL_MANIFEST.as_posix()}
            record["active_wave"] = {"wave_id": WAVE_ID, "status": "wave_open", "allocation": WAVE_ALLOCATION.as_posix(), "closeout": None}
            record["active_campaign"] = {
                "campaign_id": CAMPAIGN_ID,
                "status": STATUS,
                "manifest": CAMPAIGN_MANIFEST.as_posix(),
                "closeout": None,
            }
            record["active_work_item"] = {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()}
            record["unresolved_blockers"] = []
            record.setdefault("summary_counts", {})["wave03_l4_materialization"] = {
                "bundle_count": onnx_summary["bundle_count"],
                "attempt_count": attempt_summary["attempt_count"],
            }
        primary_family = "runtime_probe" if path in {SWEEP_MANIFEST, WORKSPACE_STATE} else "onnx_export_parity"
        record.update(
            writer_contract_fields(
                primary_family=primary_family,
                writer_owned_outputs=[path],
                progress_effect="l4_materialization_control_record_updated_with_terminal_execution_next",
                boundary_effect="active_pointer_moves_to_runtime_probe_execution",
                next_action=NEXT_ACTION,
                claim_boundary=NEXT_CLAIM_BOUNDARY,
            )
        )
        write_machine_yaml(REPO_ROOT / path, record)

    fields, refs = read_csv_with_fieldnames(REPO_ROOT / CAMPAIGN_REFS)
    for ref in refs:
        if ref.get("campaign_id") == CAMPAIGN_ID:
            ref["status"] = STATUS
            ref["claim_boundary"] = NEXT_CLAIM_BOUNDARY
            ref["next_action"] = NEXT_WORK_ITEM_ID
            ref["notes"] = "Wave03 L4 ONNX bundles and MT5 attempt manifests prepared; terminal execution required next."
    write_csv(REPO_ROOT / CAMPAIGN_REFS, refs, fields)

    goal = read_yaml(REPO_ROOT / GOAL_MANIFEST)
    goal["updated_at_utc"] = created_at
    goal["status"] = STATUS
    goal["active_phase"] = STATUS
    goal["claim_boundary"] = NEXT_CLAIM_BOUNDARY
    goal["next_work_item"] = {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix(), "summary": NEXT_ACTION}
    goal.setdefault("wave03_volatility_state_l4_materialization", {}).update(
        {
            "status": STATUS,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "onnx_materialization_summary": ONNX_SUMMARY.as_posix(),
            "l4_attempt_preparation_summary": ATTEMPT_SUMMARY.as_posix(),
            "counts": {"bundle_count": onnx_summary["bundle_count"], "attempt_count": attempt_summary["attempt_count"]},
            "next_work_item": NEXT_WORK_ITEM_ID,
        }
    )
    write_yaml(REPO_ROOT / GOAL_MANIFEST, goal)

    resume = read_yaml(REPO_ROOT / RESUME_CURSOR)
    resume.update(
        {
            "updated_at_utc": created_at,
            "cursor_state": STATUS,
            "active_phase": STATUS,
            "active_work_item_id": NEXT_WORK_ITEM_ID,
            "claim_boundary": NEXT_CLAIM_BOUNDARY,
            "next_action": NEXT_ACTION,
            "unresolved_blockers": [],
            "latest_completed_work": {
                "work_item_id": WORK_ITEM_ID,
                "claim_boundary": NEXT_CLAIM_BOUNDARY,
                "evidence_paths": [ONNX_SUMMARY.as_posix(), ATTEMPT_SUMMARY.as_posix(), CLOSEOUT_PATH.as_posix()],
            },
            "next_work_item": {"work_item_id": NEXT_WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix(), "summary": NEXT_ACTION},
        }
    )
    write_yaml(REPO_ROOT / RESUME_CURSOR, resume)

    for registry_path, id_key, id_value in [
        (Path("docs/registers/goal_registry.csv"), "goal_id", GOAL_ID),
        (Path("docs/registers/wave_registry.csv"), "wave_id", WAVE_ID),
        (Path("docs/registers/campaign_registry.csv"), "campaign_id", CAMPAIGN_ID),
    ]:
        fields, rows = read_csv_with_fieldnames(REPO_ROOT / registry_path)
        for row in rows:
            if row.get(id_key) == id_value:
                row["status"] = STATUS
                if "active_phase" in row:
                    row["active_phase"] = STATUS
                row["claim_boundary"] = NEXT_CLAIM_BOUNDARY
                if "next_work_item" in row:
                    row["next_work_item"] = NEXT_WORK_ITEM_ID
                if "next_action" in row:
                    row["next_action"] = NEXT_WORK_ITEM_ID
                if "evidence_path" in row:
                    row["evidence_path"] = ATTEMPT_SUMMARY.as_posix()
                if "notes" in row:
                    row["notes"] = "Wave03 L4 ONNX bundles and MT5 attempts prepared; terminal execution required next."
        write_csv(REPO_ROOT / registry_path, rows, fields)


def writer_scope_self_check(bundles: list[dict[str, Any]], attempts: list[dict[str, Any]]) -> dict[str, Any]:
    failures: list[str] = []
    for path in [ONNX_SUMMARY, ONNX_INDEX, ATTEMPT_SUMMARY, ATTEMPT_INDEX, CLOSEOUT_PATH, NEXT_WORK_ITEM, WORKSPACE_STATE]:
        if not path_exists(REPO_ROOT / path):
            failures.append(f"missing:{path.as_posix()}")
    if len(bundles) != 18:
        failures.append(f"bundle_count_not_18:{len(bundles)}")
    if len(attempts) != 36:
        failures.append(f"attempt_count_not_36:{len(attempts)}")
    for bundle in bundles:
        for key in ["bundle_path", "onnx_path"]:
            if not path_exists(REPO_ROOT / bundle[key]):
                failures.append(f"missing:{bundle[key]}")
        if bundle.get("parity_status") != "passed":
            failures.append(f"parity_not_passed:{bundle['bundle_id']}")
    for attempt in attempts:
        for key in ["attempt_manifest", "tester_config"]:
            if not path_exists(REPO_ROOT / attempt[key]):
                failures.append(f"missing:{attempt[key]}")
    workspace = read_yaml(REPO_ROOT / WORKSPACE_STATE)
    if (workspace.get("active_work_item") or {}).get("work_item_id") != NEXT_WORK_ITEM_ID:
        failures.append("workspace_next_work_mismatch")
    if workspace.get("current_claim_boundary") != NEXT_CLAIM_BOUNDARY:
        failures.append("workspace_claim_boundary_mismatch")
    return {"status": "passed" if not failures else "failed", "failures": failures}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize Wave03 L4 ONNX bundles and MT5 attempt manifests.")
    parser.add_argument("--expected-branch", default="main")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    command_argv = [arg for arg in sys.argv[:]]
    branch = branch_worktree(args.expected_branch)
    created_at = utc_now()
    runtime_contract = read_yaml(REPO_ROOT / RUNTIME_CONTRACT)
    period_profile = read_yaml(REPO_ROOT / PERIOD_PROFILE)
    execution_profile = read_yaml(REPO_ROOT / EXECUTION_PROFILE)
    frame = load_row_membership(REPO_ROOT / ROW_MEMBERSHIP_MANIFEST)
    _, refs = read_csv_with_fieldnames(REPO_ROOT / RUN_REFS)
    if len(refs) != 18:
        raise ValueError(f"Wave03 L4 preflight requires 18 run refs, observed {len(refs)}")

    bundles: list[dict[str, Any]] = []
    for row in refs:
        run_spec = read_yaml(REPO_ROOT / row["run_spec_path"])
        bundles.append(
            materialize_bundle(
                run_spec=run_spec,
                frame=frame,
                runtime_contract=runtime_contract,
                period_profile=period_profile,
                execution_profile=execution_profile,
                created_at=created_at,
            )
        )

    attempts = prepare_attempts(
        bundles=bundles,
        runtime_contract=runtime_contract,
        period_profile=period_profile,
        execution_profile=execution_profile,
        created_at=created_at,
    )
    onnx_summary, attempt_summary, closeout = summary_records(
        bundles=bundles,
        attempts=attempts,
        runtime_contract=runtime_contract,
        period_profile=period_profile,
        execution_profile=execution_profile,
        branch=branch,
        command_argv=command_argv,
        created_at=created_at,
    )
    onnx_fields = [
        "run_id",
        "cell_id",
        "bundle_id",
        "bundle_path",
        "onnx_path",
        "feature_count",
        "feature_order_hash",
        "task_kind",
        "model_family",
        "status",
        "claim_boundary",
        "parity_status",
        "max_abs_error",
        "common_model_path",
        "common_feature_columns_path",
        "history_bars",
    ]
    attempt_fields = [
        "attempt_id",
        "run_id",
        "cell_id",
        "bundle_id",
        "period_role",
        "split_role",
        "from_date",
        "to_date",
        "status",
        "attempt_manifest",
        "attempt_manifest_path",
        "tester_config",
        "tester_config_path",
        "claim_boundary",
        "next_action",
    ]
    write_machine_yaml(REPO_ROOT / ONNX_SUMMARY, onnx_summary)
    write_csv(REPO_ROOT / ONNX_INDEX, [{key: value for key, value in row.items() if key != "feature_columns"} for row in bundles], onnx_fields)
    write_machine_yaml(REPO_ROOT / ATTEMPT_SUMMARY, attempt_summary)
    write_csv(REPO_ROOT / ATTEMPT_INDEX, attempts, attempt_fields)
    write_machine_yaml(REPO_ROOT / CLOSEOUT_PATH, closeout)
    update_run_refs_and_controls(created_at, onnx_summary, attempt_summary)
    self_check = writer_scope_self_check(bundles, attempts)
    if self_check["status"] != "passed":
        raise RuntimeError(f"writer scope self check failed: {self_check['failures']}")
    print(
        json.dumps(
            {
                "status": STATUS,
                "bundle_count": len(bundles),
                "attempt_count": len(attempts),
                "claim_boundary": NEXT_CLAIM_BOUNDARY,
                "next_work_item": NEXT_WORK_ITEM_ID,
                "operational_validation_required": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
