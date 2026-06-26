from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import subprocess
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

from foundation.features.wave0_scout_features import FeatureSchema, build_wave0_features
from foundation.labels.wave0_scout_labels import LabelSchema, build_wave0_labels
from foundation.training.wave0_proxy_models import (
    ProxyFit,
    build_model_target,
    decision_metrics,
    diagnostic_metrics,
    fit_proxy_model,
    judge_proxy_result,
    score_model,
)


UTC = timezone.utc
CLAIM_BOUNDARY = "first_batch_proxy_scout_l4_required_no_candidate_no_baseline_no_runtime_authority"
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
EXECUTION_REQUIRED_GATES = [
    "branch_worktree_fit",
    "time_axis_check",
    "feature_label_boundary_check",
    "split_boundary_check",
    "selection_bias_check",
    "run_manifest",
    "experiment_receipt",
    "storage_contract_check",
    "runtime_learning_probe_decision",
    "final_claim_guard",
    "onnx_export_or_runtime_materialization_required",
    "L4_split_runtime_probe_for_valid_proxy_run",
]


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def repo_relative(path: Path, repo_root: Path = REPO_ROOT) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return mask_local_path(str(path.resolve()))


def mask_local_path(value: str) -> str:
    home = Path.home()
    masked = str(value)
    for variant in (str(home), home.as_posix()):
        if masked.lower().startswith(variant.lower()):
            return "${USERPROFILE}" + masked[len(variant) :]
        masked = masked.replace(variant, "${USERPROFILE}")
    return masked


def durable_arg(value: str) -> str:
    try:
        path = Path(value)
        if path.is_absolute():
            return repo_relative(path)
    except OSError:
        pass
    return mask_local_path(str(value))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_ref(path: Path, *, availability: str = "present_hash_recorded") -> dict[str, Any]:
    return {
        "path": repo_relative(path),
        "sha256": file_sha256(path),
        "size_bytes": path.stat().st_size,
        "availability": availability,
    }


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a JSON object")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a YAML mapping")
    return payload


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


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
    packages = ["numpy", "pandas", "sklearn", "yaml"]
    versions: dict[str, str] = {
        "python": platform.python_version(),
        "platform": platform.platform(),
    }
    for package in packages:
        try:
            module = __import__(package)
            versions[package] = str(getattr(module, "__version__", "unknown"))
        except Exception as exc:  # noqa: BLE001 - recorded as environment evidence.
            versions[package] = f"unavailable:{exc}"
    return versions


def branch_worktree(expected_branch: str) -> dict[str, str]:
    current = git_value(["branch", "--show-current"])
    if current != expected_branch:
        raise RuntimeError(f"branch mismatch before Wave0 execution: current={current!r} expected={expected_branch!r}")
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
        "started_at_utc": started_at.isoformat().replace("+00:00", "Z"),
        "ended_at_utc": utc_now().isoformat().replace("+00:00", "Z"),
        "input_hashes": [artifact_ref(path) for path in input_paths if path.exists()],
        "output_hashes": [artifact_ref(path) for path in output_paths if path.exists()],
        "unknown_git_claim_effect": "planning_scaffold_only_no_reproducible_bundle_runtime_handoff_pass_readiness_or_goal_achieve",
        "dirty_worktree_claim_effect": "proxy_scout_only_no_reproducible_candidate_bundle_runtime_or_goal_achieve_claim",
    }


def load_row_membership(row_manifest: dict[str, Any]) -> pd.DataFrame:
    csv_info = row_manifest["row_membership"]["full_csv"]
    path = REPO_ROOT / csv_info["path"]
    if not path.exists():
        raise FileNotFoundError(f"row membership CSV missing: {csv_info['path']}")
    observed_hash = file_sha256(path)
    if observed_hash != csv_info["sha256"]:
        raise RuntimeError(f"row membership hash mismatch expected={csv_info['sha256']} observed={observed_hash}")
    frame = pd.read_csv(path)
    numeric_columns = [
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
    ]
    for column in numeric_columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def feature_label_frame(frame: pd.DataFrame, cell: dict[str, Any]) -> tuple[pd.DataFrame, FeatureSchema, pd.DataFrame, LabelSchema]:
    features, feature_schema = build_wave0_features(frame, str(cell["input_family"]))
    labels, label_schema = build_wave0_labels(frame, str(cell["target_family"]), int(cell["horizon_bars"]))
    return features, feature_schema, labels, label_schema


def split_masks(frame: pd.DataFrame, labels: pd.DataFrame) -> dict[str, pd.Series]:
    base = labels["same_role_horizon_ok"].astype(bool)
    roles = frame["primary_split_role"].astype(str)
    return {
        "train": base & roles.eq("train"),
        "validation": base & roles.eq("validation"),
        "research_oos_a_withheld": base & roles.eq("research_oos_a"),
        "locked_final_oos_b_withheld": base & roles.eq("locked_final_oos_b"),
    }


def usable_feature_columns(features: pd.DataFrame, train_mask: pd.Series) -> list[str]:
    usable = [column for column in features.columns if features.loc[train_mask, column].notna().any()]
    if not usable:
        raise ValueError("all feature columns are empty in train scope")
    return usable


def write_prediction_sample(path: Path, frame: pd.DataFrame, labels: pd.DataFrame, score: pd.Series) -> None:
    sample = pd.DataFrame(
        {
            "row_seq": frame["row_seq"],
            "primary_split_role": frame["primary_split_role"],
            "us100_bar_close_time": frame["us100_bar_close_time_utc_rendered"],
            "future_return": labels["future_return"],
            "target_continuous": labels["target_continuous"],
            "score": score,
        }
    )
    sample.head(500).to_csv(path, index=False)


def run_one_cell(
    *,
    run_manifest_path: Path,
    row_frame: pd.DataFrame,
    row_manifest_path: Path,
    row_manifest: dict[str, Any],
    started_at: datetime,
    branch: dict[str, str],
    command_argv: list[str],
) -> dict[str, Any]:
    run_root = run_manifest_path.parent
    run_manifest = read_json(run_manifest_path)
    receipt_path = run_root / "experiment_receipt.yaml"
    metrics_path = run_root / "metrics.json"
    lineage_path = run_root / "artifact_lineage.json"
    receipt = read_yaml(receipt_path)

    cell = run_manifest["planned_cell"]
    run_id = str(run_manifest["run_id"])
    run_started = utc_now()
    artifacts_dir = run_root / "artifacts"
    reports_dir = run_root / "reports"

    output_paths: list[Path] = []
    input_paths = [
        row_manifest_path,
        REPO_ROOT / "lab/campaigns/campaign_us100_task_surface_scout_v0/first_batch_matrix.csv",
        REPO_ROOT / "configs/onnx_lab/feature_recipes/feature_wave0_us100_closedbar_price_session_regime_v0.yaml",
        REPO_ROOT / "configs/onnx_lab/label_recipes/label_wave0_surface_grid_v0.yaml",
        REPO_ROOT / "configs/onnx_lab/model_recipes/model_wave0_transparent_scout_v0.yaml",
        REPO_ROOT / "configs/onnx_lab/decision_recipes/decision_wave0_abstain_density_scout_v0.yaml",
        REPO_ROOT / "configs/onnx_lab/eval_recipes/eval_wave0_surface_scout_v0.yaml",
    ]

    try:
        features, feature_schema, labels, label_schema = feature_label_frame(row_frame, cell)
        masks = split_masks(row_frame, labels)
        train_mask = masks["train"]
        validation_mask = masks["validation"]
        if int(train_mask.sum()) < 1000 or int(validation_mask.sum()) < 1000:
            raise ValueError(f"insufficient split rows train={int(train_mask.sum())} validation={int(validation_mask.sum())}")

        target, task_kind, target_name, target_threshold = build_model_target(
            labels,
            train_mask,
            target_family=str(cell["target_family"]),
            model_family=str(cell["model_family"]),
        )
        target_notna = target.notna()
        train_mask = train_mask & target_notna
        validation_mask = validation_mask & target_notna
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
        train_scores = score_model(fit.model, x.loc[train_mask], fit.task_kind)
        validation_scores = score_model(fit.model, x.loc[validation_mask], fit.task_kind)
        train_metrics = diagnostic_metrics(target.loc[train_mask], train_scores, fit.task_kind)
        validation_metrics = diagnostic_metrics(target.loc[validation_mask], validation_scores, fit.task_kind)
        validation_decision = decision_metrics(
            decision_family=str(cell["decision_family"]),
            score=validation_scores,
            labels=labels.loc[validation_mask],
            fit=fit,
        )
        judgment, judgment_reasons = judge_proxy_result(validation_metrics, validation_decision, fit.task_kind)

        feature_schema_payload = {
            "version": "wave0_feature_schema_v1",
            **feature_schema.__dict__,
            "used_feature_columns": columns,
            "used_feature_count": len(columns),
            "all_nan_train_columns_dropped": [column for column in feature_schema.feature_columns if column not in columns],
            "claim_boundary": "feature_schema_for_proxy_scout_only_not_selected_feature_set",
        }
        label_schema_payload = {
            "version": "wave0_label_schema_v1",
            **label_schema.__dict__,
            "target_name_used_for_model": target_name,
            "target_threshold": target_threshold,
            "target_threshold_fit_scope": "train_only" if target_threshold is not None else "not_applicable",
            "claim_boundary": "label_schema_for_proxy_scout_only_not_default_target",
        }
        model_summary_payload = {
            "version": "wave0_proxy_model_summary_v1",
            "run_id": run_id,
            "cell_id": cell["cell_id"],
            "model_family": cell["model_family"],
            "task_kind": fit.task_kind,
            "model_summary": fit.model_summary,
            "train_score_summary": fit.train_score_summary,
            "claim_boundary": "proxy_model_summary_only_no_candidate_no_onnx_no_runtime",
        }
        split_profile_payload = {
            "version": "wave0_split_profile_v1",
            "run_id": run_id,
            "row_membership_manifest": repo_relative(row_manifest_path),
            "horizon_bars": int(cell["horizon_bars"]),
            "sample_counts": {
                "raw_rows": int(len(row_frame)),
                "train_label_eligible_rows": int(train_mask.sum()),
                "validation_label_eligible_rows": int(validation_mask.sum()),
                "research_oos_a_withheld_rows": int(masks["research_oos_a_withheld"].sum()),
                "locked_final_oos_b_withheld_rows": int(masks["locked_final_oos_b_withheld"].sum()),
            },
            "locked_final_oos_b_use": "withheld_not_used",
            "leakage_boundary": "label horizon same primary_split_role required; preprocessing and thresholds train-only",
        }

        feature_schema_path = artifacts_dir / "feature_schema.json"
        label_schema_path = artifacts_dir / "label_schema.json"
        model_summary_path = artifacts_dir / "model_summary.json"
        split_profile_path = artifacts_dir / "split_profile.json"
        prediction_sample_path = artifacts_dir / "prediction_sample.csv"
        proxy_report_path = reports_dir / "proxy_scout_report.json"
        write_json(feature_schema_path, feature_schema_payload)
        write_json(label_schema_path, label_schema_payload)
        write_json(model_summary_path, model_summary_payload)
        write_json(split_profile_path, split_profile_payload)
        validation_score_series = pd.Series(validation_scores, index=labels.loc[validation_mask].index)
        write_prediction_sample(prediction_sample_path, row_frame.loc[validation_mask], labels.loc[validation_mask], validation_score_series)

        report_payload = {
            "version": "wave0_proxy_scout_report_v1",
            "run_id": run_id,
            "cell": cell,
            "model_family": cell["model_family"],
            "target_and_label": {
                "target_family": cell["target_family"],
                "target_name": target_name,
                "horizon_bars": int(cell["horizon_bars"]),
                "target_threshold": target_threshold,
                "target_threshold_fit_scope": "train_only" if target_threshold is not None else "not_applicable",
            },
            "split_method": "split_set_v0_train_validation_only_oos_a_and_oos_b_withheld",
            "selection_metric": "none_selected_first_batch_proxy_scout",
            "secondary_metrics": ["validation_model_metrics", "validation_decision_proxy_metrics", "sample_counts"],
            "threshold_policy": fit.threshold_policy,
            "overfit_risk": "first_batch_multiple_surface_scout_no_selection_allowed",
            "calibration_risk": "scores_are_rank_or_model_scores_not_calibrated_probabilities",
            "comparison_baseline": "no_trade_or_random_baseline_not_materialized_in_this_first_proxy_execution",
            "train_metrics": train_metrics,
            "validation_metrics": validation_metrics,
            "validation_decision_metrics": validation_decision,
            "judgment_reasons": judgment_reasons,
            "validation_judgment": judgment,
            "claim_boundary": CLAIM_BOUNDARY,
        }
        write_json(proxy_report_path, report_payload)

        output_paths = [
            feature_schema_path,
            label_schema_path,
            model_summary_path,
            split_profile_path,
            prediction_sample_path,
            proxy_report_path,
        ]
        status = "executed_proxy_scout"
        missing_evidence = [
            "wfo_not_run_in_first_batch_proxy_scout",
            "onnx_export_or_runtime_materialization_required",
            "L4_split_runtime_probe_required_pending_for_all_valid_proxy_runs",
            "candidate_selection_not_allowed_from_first_batch",
        ]
        result_payload = {
            "status": status,
            "result_judgment": judgment,
            "judgment_reasons": judgment_reasons,
            "task_kind": fit.task_kind,
            "target_name": target_name,
            "target_threshold": target_threshold,
            "feature_count": len(columns),
            "train_metrics": train_metrics,
            "validation_metrics": validation_metrics,
            "validation_decision_metrics": validation_decision,
            "sample_counts": split_profile_payload["sample_counts"],
            "artifact_paths": output_paths,
            "missing_evidence": missing_evidence,
        }
    except Exception as exc:  # noqa: BLE001 - per-cell invalid setup evidence is useful.
        status = "invalid_setup"
        judgment = "invalid"
        missing_evidence = ["valid_proxy_execution_not_available"]
        result_payload = {
            "status": status,
            "result_judgment": judgment,
            "judgment_reasons": [f"execution_error:{type(exc).__name__}:{exc}"],
            "task_kind": None,
            "target_name": None,
            "target_threshold": None,
            "feature_count": None,
            "train_metrics": {},
            "validation_metrics": {},
            "validation_decision_metrics": {},
            "sample_counts": {},
            "artifact_paths": [],
            "missing_evidence": missing_evidence,
        }

    prov = provenance(command_argv, input_paths, output_paths, run_started)
    run_manifest.update(
        {
            "agent_consult_status": "not_requested_for_codex_only_first_batch_execution",
            "selected_agents": [],
            "branch_worktree": branch,
            "agent_allocation": {
                "phase": "wave0_first_batch_proxy_execution",
                "selected_agents": [],
                "role_modes": [],
                "selection_reason": "Codex-only execution of planned first-batch proxy specs; no material axis decision or protected claim made.",
                "why_not_smaller": "Codex alone is the smallest allocation.",
                "why_not_larger": "Axis rotation or narrowing is deferred to the next work item after result summary.",
                "max_threads_is_capacity_only": True,
                "claim_effect": "no_advisory_claim",
            },
            "status": status,
            "command": " ".join(durable_arg(arg) for arg in command_argv),
            "entrypoint": "foundation/pipelines/run_wave0_first_batch_proxy_scout.py",
            "environment_summary": dependency_summary(),
            "provenance": prov,
            "model_export": {
                "framework": "sklearn_proxy_model_no_onnx_export",
                "opset": None,
                "input_schema": {
                    "feature_schema_path": repo_relative(run_root / "artifacts" / "feature_schema.json"),
                    "feature_count": result_payload["feature_count"],
                },
                "output_schema": {
                    "score_semantics": "proxy_score_or_rank_not_calibrated_probability",
                },
                "onnx_sha256": None,
            },
            "required_gate_coverage": {
                "passed": [
                    gate
                    for gate in EXECUTION_REQUIRED_GATES
                    if gate not in {"onnx_export_or_runtime_materialization_required", "L4_split_runtime_probe_for_valid_proxy_run"}
                ],
                "not_applicable": ["locked_final_oos_access"],
                "missing": ["onnx_export_or_runtime_materialization_required", "L4_split_runtime_probe_for_valid_proxy_run"],
            },
            "result_judgment": judgment,
            "missing_evidence": missing_evidence,
            "claim_scope": CLAIM_BOUNDARY,
            "claim_boundary": CLAIM_BOUNDARY,
            "forbidden_claims": FORBIDDEN_CLAIMS,
            "next_action": "work_wave0_first_batch_axis_review_v0",
        }
    )
    receipt.update(
        {
            "branch_worktree": branch,
            "agent_allocation": run_manifest["agent_allocation"],
            "provenance": prov,
            "comparison_baseline": "no_trade_or_random_baseline_not_materialized_in_first_proxy_execution",
            "required_gate_coverage": run_manifest["required_gate_coverage"],
            "runtime_learning_probe_decision": run_manifest["runtime_learning_probe_decision"],
            "result_judgment": judgment,
            "missing_evidence": missing_evidence,
            "claim_boundary": CLAIM_BOUNDARY,
            "forbidden_claims": FORBIDDEN_CLAIMS,
            "next_action": "work_wave0_first_batch_axis_review_v0",
        }
    )
    receipt["sample_scope"] = {
        **receipt.get("sample_scope", {}),
        "row_membership_manifest": repo_relative(row_manifest_path),
        "locked_final_oos_b_use": "withheld_not_used",
    }

    metrics = {
        "version": "metrics_v2",
        "run_id": run_id,
        "status": status,
        "task_surface_id": run_manifest["id_chain"]["surface_id"],
        "planned_cell": cell,
        "sample_counts": result_payload["sample_counts"],
        "task_surface_metrics": {
            "target_name": result_payload["target_name"],
            "task_kind": result_payload["task_kind"],
            "target_threshold": result_payload["target_threshold"],
            "feature_count": result_payload["feature_count"],
        },
        "model_metrics": {
            "train": result_payload["train_metrics"],
            "validation": result_payload["validation_metrics"],
        },
        "trading_proxy_metrics": result_payload["validation_decision_metrics"],
        "runtime_metrics": {},
        "north_star_context": {
            "role": "final_objective_not_exploration_gate",
            "average_trades_per_active_day_min": 5,
            "profit_factor_preferred_range": [1.5, 3.0],
            "major_window_drawdown_pct_max": 10,
        },
        "measurement_scope": "first_batch_proxy_scout_train_validation_only_no_oos_b_l4_required_no_runtime_authority",
        "judgment_label": judgment,
        "result_judgment": judgment,
        "judgment_reasons": result_payload["judgment_reasons"],
        "claim_boundary": CLAIM_BOUNDARY,
        "missing_evidence": missing_evidence,
    }

    source_inputs = [artifact_ref(path) for path in input_paths if path.exists()]
    root_artifacts = [run_manifest_path, receipt_path, metrics_path]
    write_json(run_manifest_path, run_manifest)
    write_yaml(receipt_path, receipt)
    write_json(metrics_path, metrics)
    lineage_artifacts = [artifact_ref(path) for path in [*root_artifacts, *output_paths] if path.exists()]
    lineage = {
        "version": "artifact_lineage_v2",
        "run_id": run_id,
        "source_inputs": source_inputs,
        "producer": {
            "type": "python_pipeline",
            "identity": "foundation/pipelines/run_wave0_first_batch_proxy_scout.py",
            "command": " ".join(durable_arg(arg) for arg in command_argv),
            "environment_summary": dependency_summary(),
        },
        "consumer": ["work_wave0_first_batch_l4_follow_through_v0"],
        "source_of_truth_paths": [repo_relative(run_manifest_path)],
        "artifact_paths": lineage_artifacts,
        "artifact_hashes": [item["sha256"] for item in lineage_artifacts],
        "artifact_sizes": [item["size_bytes"] for item in lineage_artifacts],
        "regeneration_commands": [" ".join(durable_arg(arg) for arg in command_argv)],
        "registry_links": [
            "docs/registers/run_registry.csv",
            "lab/campaigns/campaign_us100_task_surface_scout_v0/sweeps/sweep_wave0_broad_surface_scout_v0/run_refs.csv",
        ],
        "availability": "run_local_evidence_with_heavy_artifacts_ignored_by_git_where_applicable",
        "heavy_artifact_policy": "track_by_path_hash_size_command_or_uri",
        "lineage_judgment": "usable_proxy_evidence_with_l4_follow_through_required" if judgment != "invalid" else "invalid_setup_recorded",
    }
    write_json(lineage_path, lineage)
    return {
        "run_id": run_id,
        "status": status,
        "result_judgment": judgment,
        "claim_boundary": CLAIM_BOUNDARY,
        "run_manifest_path": repo_relative(run_manifest_path),
        "receipt_path": repo_relative(receipt_path),
        "lineage_path": repo_relative(lineage_path),
        "metrics_path": repo_relative(metrics_path),
        "notes": ";".join(result_payload["judgment_reasons"]),
    }


def update_run_refs(path: Path, results: list[dict[str, Any]]) -> None:
    rows = []
    by_run = {item["run_id"]: item for item in results}
    for row in read_csv_rows(path):
        result = by_run.get(row["run_id"])
        if result:
            row["status"] = result["status"]
            row["claim_boundary"] = result["claim_boundary"]
            row["result_judgment"] = result["result_judgment"]
            row["notes"] = result["notes"]
        rows.append(row)
    write_csv(path, rows, ["run_id", "status", "created_at_utc", "run_manifest_path", "claim_boundary", "result_judgment", "notes"])


def update_run_registry(path: Path, results: list[dict[str, Any]]) -> None:
    fieldnames = [
        "run_id",
        "wave_id",
        "campaign_id",
        "idea_id",
        "hypothesis_id",
        "surface_id",
        "sweep_id",
        "status",
        "created_at_utc",
        "primary_family",
        "primary_skill",
        "manifest_path",
        "receipt_path",
        "lineage_path",
        "metrics_path",
        "claim_boundary",
        "result_judgment",
        "required_gates",
        "evidence_path",
        "next_action",
        "notes",
    ]
    existing = read_csv_rows(path) if path.exists() else []
    by_run = {row["run_id"]: row for row in existing}
    for result in results:
        manifest = read_json(REPO_ROOT / result["run_manifest_path"])
        routing = manifest["skill_routing"]
        by_run[result["run_id"]] = {
            "run_id": result["run_id"],
            "wave_id": manifest["id_chain"].get("wave_id", ""),
            "campaign_id": manifest["id_chain"].get("campaign_id", ""),
            "idea_id": manifest["id_chain"]["idea_id"],
            "hypothesis_id": manifest["id_chain"]["hypothesis_id"],
            "surface_id": manifest["id_chain"]["surface_id"],
            "sweep_id": manifest["id_chain"]["sweep_id"],
            "status": result["status"],
            "created_at_utc": manifest["created_at_utc"],
            "primary_family": routing["primary_family"],
            "primary_skill": routing["primary_skill"],
            "manifest_path": result["run_manifest_path"],
            "receipt_path": result["receipt_path"],
            "lineage_path": result["lineage_path"],
            "metrics_path": result["metrics_path"],
            "claim_boundary": result["claim_boundary"],
            "result_judgment": result["result_judgment"],
            "required_gates": "|".join(manifest["required_gate_coverage"]["passed"] + [f"not_applicable:{item}" for item in manifest["required_gate_coverage"]["not_applicable"]]),
            "evidence_path": str(Path(result["run_manifest_path"]).parent).replace("\\", "/"),
            "next_action": manifest["next_action"],
            "notes": "Wave0 first-batch proxy scout only; no candidate, baseline, ONNX, MT5, runtime, economics, or live claim",
        }
    ordered = list(existing)
    seen = {row["run_id"] for row in ordered}
    for run_id in sorted(by_run):
        if run_id not in seen:
            ordered.append(by_run[run_id])
    for index, row in enumerate(ordered):
        if row["run_id"] in by_run:
            ordered[index] = by_run[row["run_id"]]
    write_csv(path, ordered, fieldnames)


def update_yaml_file(path: Path, updates: dict[str, Any]) -> None:
    data = read_yaml(path)
    data.update(updates)
    write_yaml(path, data)


def update_campaign_records(args: argparse.Namespace, results: list[dict[str, Any]]) -> None:
    campaign_dir = REPO_ROOT / args.campaign_dir
    result_counts = Counter(str(item["result_judgment"]) for item in results)
    first_batch_result = {
        "status": "executed_proxy_scout",
        "run_count": len(results),
        "result_counts": dict(sorted(result_counts.items())),
        "claim_boundary": CLAIM_BOUNDARY,
        "candidate_count": 0,
        "selected_baseline_count": 0,
        "runtime_claim": False,
        "next_action": "work_wave0_first_batch_axis_review_v0",
    }
    anti_path = campaign_dir / "anti_selection_ledger.yaml"
    anti = read_yaml(anti_path)
    anti.update(
        {
            "status": "results_viewed_no_selection_made",
            "result_viewed": True,
            "result_counts": first_batch_result["result_counts"],
            "candidate_count": 0,
            "selection_decision": "no_selection_first_batch_proxy_scout_only",
            "next_action": "work_wave0_first_batch_axis_review_v0",
        }
    )
    write_yaml(anti_path, anti)

    manifest_path = campaign_dir / "first_batch_run_specs_manifest.yaml"
    manifest = read_yaml(manifest_path)
    manifest.update(
        {
            "status": "executed_proxy_scout_no_candidate",
            "result_counts": first_batch_result["result_counts"],
            "candidate_count": 0,
            "next_action": "work_wave0_first_batch_axis_review_v0",
        }
    )
    write_yaml(manifest_path, manifest)

    for rel_path in [
        "lab/campaigns/campaign_us100_task_surface_scout_v0/campaign_manifest.yaml",
        "lab/campaigns/campaign_us100_task_surface_scout_v0/sweeps/sweep_wave0_broad_surface_scout_v0/sweep_manifest.yaml",
        "lab/waves/wave_us100_closedbar_surface_cartography_v0/wave_allocation.yaml",
        "lab/surfaces/surface_us100_task_input_decision_rotation_v0/surface_manifest.yaml",
    ]:
        path = REPO_ROOT / rel_path
        data = read_yaml(path)
        data["status"] = "first_batch_proxy_scout_executed_no_candidate"
        data["first_batch_result"] = first_batch_result
        data["next_action"] = "work_wave0_first_batch_axis_review_v0"
        write_yaml(path, data)


def write_batch_closeout(args: argparse.Namespace, results: list[dict[str, Any]]) -> None:
    result_counts = Counter(str(item["result_judgment"]) for item in results)
    closeout = {
        "version": "work_closeout_v1",
        "work_item_id": "work_wave0_execute_first_batch_proxy_scout_v0",
        "active_goal_id": "goal_us100_onnx_forward_boundary_v0",
        "closed_at_utc": utc_now().isoformat().replace("+00:00", "Z"),
        "result_judgment": "preserved_clue" if result_counts.get("preserved_clue") else "inconclusive",
        "claim_boundary": CLAIM_BOUNDARY,
        "completed_scope": [
            "first 12 Wave0 planned scout cells executed or recorded",
            "run-local manifests, receipts, lineage, and metrics updated",
            "anti-selection ledger updated after result viewing with no selection",
            "global run registry updated for executed proxy scout runs",
        ],
        "result_counts": dict(sorted(result_counts.items())),
        "candidate_count": 0,
        "runtime_learning_probe_decision": {
            "required": True,
            "decision": "run_required",
            "reason": "First-batch proxy scout has no runtime authority claim, but every valid proxy/model-bearing run must reach L4_split_runtime_probe before proxy closeout.",
            "lowered_claim_if_not_run": "invalid_proxy_only_closeout_no_l4_runtime_evidence",
        },
        "evidence_paths": {
            "run_refs": "lab/campaigns/campaign_us100_task_surface_scout_v0/sweeps/sweep_wave0_broad_surface_scout_v0/run_refs.csv",
            "anti_selection_ledger": "lab/campaigns/campaign_us100_task_surface_scout_v0/anti_selection_ledger.yaml",
            "first_batch_manifest": "lab/campaigns/campaign_us100_task_surface_scout_v0/first_batch_run_specs_manifest.yaml",
            "run_registry": "docs/registers/run_registry.csv",
        },
        "run_results": results,
        "missing_evidence_before_candidate": [
            "independent axis review before narrowing or rotation",
            "WFO or repeated-surface evidence",
            "ONNX export or runtime materialization for valid proxy runs",
            "L4 MT5 split-runtime probe for valid proxy runs",
        ],
        "next_work_item": {
            "work_item_id": "work_wave0_first_batch_axis_review_v0",
            "path": "lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml",
        },
        "forbidden_claims": FORBIDDEN_CLAIMS,
    }
    write_yaml(REPO_ROOT / "lab/goals/goal_us100_onnx_forward_boundary_v0/work_wave0_execute_first_batch_proxy_scout_v0_closeout.yaml", closeout)


def write_next_work_item(results: list[dict[str, Any]]) -> None:
    result_counts = Counter(str(item["result_judgment"]) for item in results)
    payload = {
        "version": "onnx_lab_work_item_v1",
        "work_item_id": "work_wave0_first_batch_axis_review_v0",
        "active_goal_id": "goal_us100_onnx_forward_boundary_v0",
        "created_at_utc": utc_now().isoformat().replace("+00:00", "Z"),
        "status": "planned_next",
        "user_request": "Review the executed Wave0 first-batch proxy scout results and decide the next axis: rotate, extend, preserve clues, or close negatives.",
        "current_truth": {
            "current_claim_boundary": CLAIM_BOUNDARY,
            "result_counts": dict(sorted(result_counts.items())),
            "candidate_count": 0,
        },
        "branch_worktree": {
            "current_branch": git_value(["branch", "--show-current"]),
            "requested_branch": "codex/active-goal-program-bootstrap",
            "branch_worktree_fit": "fit",
            "branch_action": "keep_current_branch",
            "policy_reference": "docs/policies/branch_policy.md",
            "mismatch_claim_effect": "block_axis_decision_until_resolved",
        },
        "work_classification": {
            "primary_family": "experiment_design",
            "detected_families": ["experiment_design", "model_training", "candidate_evaluation"],
            "mutation_intent": "axis_review_after_first_batch_proxy_scout",
            "execution_intent": "decide_next_wave0_axis_without_candidate_or_runtime_claim",
        },
        "acceptance_criteria": [
            "Review all 12 run metrics and judgments without selecting a baseline.",
            "Record preserved clues, negatives, invalids, and inconclusive surfaces with reopen conditions.",
            "Keep L4 follow-through required for every valid proxy/model-bearing run.",
            "If narrowing or axis rotation is material, use selected skills, source-of-truth records, and validators before opening the next sweep.",
            "Write exactly one next_work_item after the axis decision.",
        ],
        "skill_routing": {
            "primary_family": "experiment_design",
            "primary_skill": "spacesonar-experiment-design",
            "support_skills": [
                "spacesonar-model-validation",
                "spacesonar-data-integrity",
                "spacesonar-run-evidence-system",
                "spacesonar-claim-discipline",
            ],
            "skills_selected": [
                "spacesonar-experiment-design",
                "spacesonar-model-validation",
                "spacesonar-data-integrity",
                "spacesonar-run-evidence-system",
                "spacesonar-claim-discipline",
            ],
            "skills_not_used": ["spacesonar-runtime-parity"],
            "critical_skills_not_selected": [
                {
                    "skill": "spacesonar-runtime-parity",
                    "reason": "axis review has no ONNX/EA/MT5/runtime claim unless the next work item opens one",
                    "not_selected_claim_effect": "no_runtime_claim",
                }
            ],
            "not_selected_claim_effect": "no_runtime_claim_no_runtime_authority_no_economics_pass",
            "required_gates": ["design_contract_check", "selection_bias_check", "final_claim_guard"],
        },
        "agent_allocation": {
            "phase": "wave0_first_batch_axis_review",
            "selected_agents": [],
            "role_modes": [],
            "selection_reason": "Task Force/sub-agent spawning is disabled; Codex uses selected skills, validators, and source-of-truth records.",
            "why_not_smaller": "Codex solo is the only active allocation.",
            "why_not_larger": "No sub-agent allocation is active under docs/policies/agent_allocation_policy.md.",
            "max_threads_is_capacity_only": True,
            "claim_effect": "solo_execution_only_no_task_force_review_claim",
        },
        "runtime_learning_probe_decision": {
            "required": True,
            "decision": "run_required_after_axis_review",
            "reason": "Axis review itself is not runtime evidence, but any valid proxy/model-bearing run remains obligated to L4_split_runtime_probe.",
            "lowered_claim_if_not_run": "axis_review_only_no_proxy_closeout_until_l4",
        },
        "claim_boundary": "axis_review_planning_only_no_candidate_no_baseline_no_runtime",
        "forbidden_claims": FORBIDDEN_CLAIMS,
    }
    write_yaml(REPO_ROOT / "lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml", payload)


def update_resume_cursor() -> None:
    cursor = {
        "version": "active_goal_resume_cursor_v1",
        "active_goal_id": "goal_us100_onnx_forward_boundary_v0",
        "updated_at_utc": utc_now().isoformat().replace("+00:00", "Z"),
        "cursor_state": "active",
        "active_phase": "wave0_first_batch_proxy_scout_executed_axis_review_next",
        "current_truth_sources": [
            "lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml",
            "lab/goals/goal_us100_onnx_forward_boundary_v0/work_wave0_execute_first_batch_proxy_scout_v0_closeout.yaml",
            "lab/campaigns/campaign_us100_task_surface_scout_v0/first_batch_run_specs_manifest.yaml",
            "lab/campaigns/campaign_us100_task_surface_scout_v0/anti_selection_ledger.yaml",
            "lab/campaigns/campaign_us100_task_surface_scout_v0/sweeps/sweep_wave0_broad_surface_scout_v0/run_refs.csv",
            "docs/registers/run_registry.csv",
        ],
        "active_ids": {
            "idea_id": "idea_us100_m5_blank_slate_surface_map_v0",
            "hypothesis_id": "hyp_surface_diversity_before_model_search_v0",
            "wave_id": "wave_us100_closedbar_surface_cartography_v0",
            "campaign_id": "campaign_us100_task_surface_scout_v0",
            "surface_id": "surface_us100_task_input_decision_rotation_v0",
            "sweep_id": "sweep_wave0_broad_surface_scout_v0",
        },
        "latest_completed_work": {
            "work_item_id": "work_wave0_execute_first_batch_proxy_scout_v0",
            "result_judgment": "proxy_scout_observation",
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_paths": [
                "lab/goals/goal_us100_onnx_forward_boundary_v0/work_wave0_execute_first_batch_proxy_scout_v0_closeout.yaml",
                "lab/campaigns/campaign_us100_task_surface_scout_v0/sweeps/sweep_wave0_broad_surface_scout_v0/run_refs.csv",
                "docs/registers/run_registry.csv",
            ],
        },
        "next_work_item": {
            "work_item_id": "work_wave0_first_batch_axis_review_v0",
            "path": "lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml",
        },
        "pause_policy": {
            "session_or_token_or_tool_limit": "pause_only_not_terminal",
            "before_pause_required": ["resume_cursor", "next_work_item"],
        },
    }
    write_yaml(REPO_ROOT / "lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml", cursor)


def update_goal_manifest_and_workspace(results: list[dict[str, Any]]) -> None:
    result_counts = Counter(str(item["result_judgment"]) for item in results)
    goal_path = REPO_ROOT / "lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml"
    goal = read_yaml(goal_path)
    goal["updated_at_utc"] = utc_now().isoformat().replace("+00:00", "Z")
    goal["active_phase"] = "wave0_first_batch_proxy_scout_executed_axis_review_next"
    goal["next_work_item"] = {
        "path": "lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml",
        "work_item_id": "work_wave0_first_batch_axis_review_v0",
        "summary": "Review first-batch proxy scout observations and decide Wave0 axis rotation or extension without candidate/runtime claims.",
    }
    goal["program_budgets"]["current_wave0_spec"]["status"] = "first_batch_proxy_scout_executed_no_candidate"
    goal["program_budgets"]["current_wave0_spec"]["result_counts"] = dict(sorted(result_counts.items()))
    write_yaml(goal_path, goal)

    state_path = REPO_ROOT / "docs/workspace/workspace_state.yaml"
    state = read_yaml(state_path)
    claims = state["current_claims"]
    claims["active_goal_phase"] = "wave0_first_batch_proxy_scout_executed_axis_review_next"
    claims["next_work_item_id"] = "work_wave0_first_batch_axis_review_v0"
    claims["wave0_first_batch_status"] = "executed_proxy_scout_no_candidate"
    claims["wave0_first_batch_result_counts"] = dict(sorted(result_counts.items()))
    claims["wave0_first_batch_claim_boundary"] = CLAIM_BOUNDARY
    claims["runtime_authority"] = False
    state["updated_utc"] = utc_now().isoformat().replace("+00:00", "Z")
    write_yaml(state_path, state)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute Wave0 first-batch proxy scout cells.")
    parser.add_argument("--row-membership-manifest", default="lab/campaigns/campaign_us100_task_surface_scout_v0/row_membership/row_membership_manifest.yaml")
    parser.add_argument("--run-refs", default="lab/campaigns/campaign_us100_task_surface_scout_v0/sweeps/sweep_wave0_broad_surface_scout_v0/run_refs.csv")
    parser.add_argument("--campaign-dir", default="lab/campaigns/campaign_us100_task_surface_scout_v0")
    parser.add_argument("--expected-branch", default="codex/active-goal-program-bootstrap")
    return parser.parse_args()


def main(*_args: object, **_kwargs: object) -> int:
    from foundation.pipelines.historical_lifecycle_guard import disabled_lifecycle_entrypoint

    return disabled_lifecycle_entrypoint(
        "a run-local/domain evidence command plus locked spacesonar lifecycle transaction for canonical state updates"
    )


if __name__ == "__main__":
    raise SystemExit(main())
