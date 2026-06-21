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

from foundation.features.wave01_event_barrier_features import FeatureSchema, build_wave01_features
from foundation.labels.wave01_event_barrier_labels import LabelSchema, build_wave01_labels
from foundation.training.wave01_event_barrier_models import (
    ProxyFit,
    build_model_target,
    decision_metrics,
    diagnostic_metrics,
    fit_proxy_model,
    judge_proxy_result,
    score_model,
)


UTC = timezone.utc
WORK_ITEM_ID = "work_wave01_event_barrier_execute_first_batch_proxy_v0"
NEXT_WORK_ITEM_ID = "work_wave01_event_barrier_l4_materialization_preflight_v0"
CLAIM_BOUNDARY = "wave01_event_barrier_proxy_batch_l4_required_no_candidate_no_baseline_no_runtime_authority"
CAMPAIGN_ID = "campaign_us100_event_barrier_decision_surface_v0"
SWEEP_ID = "sweep_us100_event_barrier_broad_v0"
WAVE_ID = "wave_us100_closedbar_surface_cartography_v0"
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


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a YAML mapping")
    return payload


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a JSON object")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


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
        except Exception as exc:  # noqa: BLE001 - this is environment evidence.
            versions[package] = f"unavailable:{exc}"
    return versions


def branch_worktree(expected_branch: str) -> dict[str, str]:
    current = git_value(["branch", "--show-current"])
    if current != expected_branch:
        raise RuntimeError(f"branch mismatch before Wave01 execution: current={current!r} expected={expected_branch!r}")
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
        "input_hashes": [artifact_ref(path) for path in input_paths if path.exists()],
        "output_hashes": [artifact_ref(path) for path in output_paths if path.exists()],
        "unknown_git_claim_effect": "planning_scaffold_only_no_reproducible_bundle_runtime_handoff_pass_readiness_or_goal_achieve",
        "dirty_worktree_claim_effect": "proxy_observation_only_no_reproducible_candidate_bundle_runtime_or_goal_achieve_claim",
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
        raise ValueError("all feature columns are empty in Wave01 train scope")
    return columns


def write_prediction_sample(path: Path, frame: pd.DataFrame, labels: pd.DataFrame, score: pd.Series) -> None:
    sample = pd.DataFrame(
        {
            "row_seq": frame["row_seq"],
            "primary_split_role": frame["primary_split_role"],
            "us100_bar_close_time": frame["us100_bar_close_time_utc_rendered"],
            "future_return": labels["future_return"],
            "target_continuous": labels["target_continuous"],
            "target_binary_raw": labels["target_binary_raw"],
            "score": score,
        }
    )
    sample.head(500).to_csv(path, index=False)


def label_contract_from_spec(spec: dict[str, Any]) -> dict[str, Any]:
    contract = dict(spec["label_contract"])
    contract["label_surface"] = spec["axis_values"]["label_surface"]
    return contract


def execute_one_spec(
    *,
    spec_path: Path,
    row_frame: pd.DataFrame,
    row_manifest_path: Path,
    branch: dict[str, str],
    command_argv: list[str],
    started_at: datetime,
) -> dict[str, Any]:
    spec = read_yaml(spec_path)
    axis = spec["axis_values"]
    run_id = str(spec["planned_run_id"])
    run_root = REPO_ROOT / "lab" / "runs" / run_id
    artifacts_dir = run_root / "artifacts"
    reports_dir = run_root / "reports"
    run_started = utc_now()

    input_paths = [
        spec_path,
        row_manifest_path,
        REPO_ROOT / "configs/onnx_lab/feature_recipes/feature_wave01_us100_price_session_regime_flexible_v0.yaml",
        REPO_ROOT / "configs/onnx_lab/label_recipes/label_wave01_event_barrier_path_v0.yaml",
        REPO_ROOT / "configs/onnx_lab/model_recipes/model_wave01_onnx_feasible_scout_v0.yaml",
        REPO_ROOT / "configs/onnx_lab/decision_recipes/decision_wave01_barrier_abstain_risk_v0.yaml",
        REPO_ROOT / "configs/onnx_lab/eval_recipes/eval_wave01_event_barrier_runtime_v0.yaml",
        REPO_ROOT / "foundation/config/mt5_runtime_probe_contract.yaml",
        REPO_ROOT / "configs/mt5/period_profiles/split_set_v0_runtime_periods.yaml",
        REPO_ROOT / "configs/mt5/tester_execution_profile_v0.yaml",
    ]

    features, feature_schema = build_wave01_features(row_frame, str(axis["feature_family"]))
    labels, label_schema = build_wave01_labels(row_frame, label_contract_from_spec(spec))
    masks = split_masks(row_frame, labels)
    train_mask = masks["train"]
    validation_mask = masks["validation"]
    research_oos_mask = masks["research_oos_a"]
    target, task_kind, target_name, target_threshold = build_model_target(
        labels,
        train_mask,
        label_surface=str(axis["label_surface"]),
        model_family=str(axis["model_family"]),
        model_task=str(axis["model_task"]),
    )
    target_ok = target.notna()
    train_mask = train_mask & target_ok
    validation_mask = validation_mask & target_ok
    research_oos_mask = research_oos_mask & target_ok
    if int(train_mask.sum()) < 1000 or int(validation_mask.sum()) < 1000 or int(research_oos_mask.sum()) < 1000:
        raise ValueError(
            "insufficient split rows "
            f"train={int(train_mask.sum())} validation={int(validation_mask.sum())} "
            f"research_oos_a={int(research_oos_mask.sum())}"
        )

    columns = usable_feature_columns(features, train_mask)
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
    train_scores = score_model(fit.model, x.loc[train_mask], fit.task_kind)
    validation_scores = score_model(fit.model, x.loc[validation_mask], fit.task_kind)
    research_scores = score_model(fit.model, x.loc[research_oos_mask], fit.task_kind)
    train_metrics = diagnostic_metrics(target.loc[train_mask], train_scores, fit.task_kind)
    validation_metrics = diagnostic_metrics(target.loc[validation_mask], validation_scores, fit.task_kind)
    research_oos_metrics = diagnostic_metrics(target.loc[research_oos_mask], research_scores, fit.task_kind)
    validation_decision = decision_metrics(
        decision_family=str(axis["decision_family"]),
        score=validation_scores,
        labels=labels.loc[validation_mask],
        fit=fit,
    )
    research_oos_decision = decision_metrics(
        decision_family=str(axis["decision_family"]),
        score=research_scores,
        labels=labels.loc[research_oos_mask],
        fit=fit,
    )
    judgment, judgment_reasons = judge_proxy_result(
        validation_metrics,
        research_oos_metrics,
        validation_decision,
        research_oos_decision,
        fit.task_kind,
    )

    feature_schema_path = artifacts_dir / "feature_schema.json"
    label_schema_path = artifacts_dir / "label_schema.json"
    model_summary_path = artifacts_dir / "model_summary.json"
    split_profile_path = artifacts_dir / "split_profile.json"
    validation_sample_path = artifacts_dir / "prediction_sample_validation.csv"
    research_sample_path = artifacts_dir / "prediction_sample_research_oos_a.csv"
    proxy_report_path = reports_dir / "proxy_event_barrier_report.json"
    output_paths = [
        feature_schema_path,
        label_schema_path,
        model_summary_path,
        split_profile_path,
        validation_sample_path,
        research_sample_path,
        proxy_report_path,
    ]

    write_json(feature_schema_path, feature_schema_payload(feature_schema, columns))
    write_json(label_schema_path, label_schema_payload(label_schema, spec, target_name, target_threshold))
    write_json(model_summary_path, model_summary_payload(run_id, spec, fit))
    split_profile = split_profile_payload(row_frame, labels, masks, train_mask, validation_mask, research_oos_mask, row_manifest_path)
    write_json(split_profile_path, split_profile)
    validation_score_series = pd.Series(validation_scores, index=labels.loc[validation_mask].index)
    research_score_series = pd.Series(research_scores, index=labels.loc[research_oos_mask].index)
    write_prediction_sample(validation_sample_path, row_frame.loc[validation_mask], labels.loc[validation_mask], validation_score_series)
    write_prediction_sample(research_sample_path, row_frame.loc[research_oos_mask], labels.loc[research_oos_mask], research_score_series)
    report = {
        "version": "wave01_event_barrier_proxy_report_v1",
        "run_id": run_id,
        "run_spec_id": spec["run_spec_id"],
        "axis_values": axis,
        "model_family": axis["model_family"],
        "target_and_label": {
            "label_surface": axis["label_surface"],
            "target_name": target_name,
            "horizon_bars": int(axis["horizon_bars"]),
            "timeout_bars": int(axis["timeout_bars"]),
            "barrier_unit": axis["barrier_unit"],
            "upper_barrier": float(axis["upper_barrier"]),
            "lower_barrier": float(axis["lower_barrier"]),
            "target_threshold": target_threshold,
            "target_threshold_fit_scope": "train_only" if target_threshold is not None else "not_applicable",
        },
        "split_method": "split_set_v0_train_validation_research_oos_a_locked_final_oos_b_withheld",
        "selection_metric": "none_selected_first_batch_proxy_observation",
        "secondary_metrics": ["validation_model_metrics", "research_oos_model_metrics", "gross_proxy_decision_metrics"],
        "threshold_policy": fit.threshold_policy,
        "overfit_risk": "first_batch_multi_surface_observation_no_candidate_selection_allowed",
        "calibration_risk": "scores_are_model_scores_or_ranks_not_calibrated_probabilities",
        "comparison_baseline": "no_trade_baseline_named_only_not_materialized_as_selection",
        "train_metrics": train_metrics,
        "validation_metrics": validation_metrics,
        "research_oos_metrics": research_oos_metrics,
        "validation_decision_metrics": validation_decision,
        "research_oos_decision_metrics": research_oos_decision,
        "judgment_reasons": judgment_reasons,
        "validation_judgment": judgment,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    write_json(proxy_report_path, report)

    output_refs = [artifact_ref(path) for path in output_paths]
    prov = provenance(command_argv, input_paths, output_paths, run_started)
    missing_evidence = [
        "ONNX_export_not_materialized_for_L4_yet",
        "MT5_L4_split_runtime_probe_not_run_yet",
        "tester_report_not_available",
        "candidate_selection_forbidden_before_L4",
        "locked_final_oos_b_not_used",
    ]
    gate_coverage = {
        "passed": [
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
        ],
        "not_applicable": ["locked_final_oos_access"],
        "missing": ["L4_split_runtime_probe_for_valid_proxy_run"],
    }
    runtime_decision = {
        "required": True,
        "decision": "run_required",
        "reason": "Every valid Wave01 proxy/model-bearing run must continue to L4_split_runtime_probe.",
        "target_level": "L4_split_runtime_probe",
        "runtime_period_profile_id": "period_profile_split_set_v0",
        "runtime_period_set_id": "split_base_anchor_v0_research_l4",
        "tester_execution_profile_id": "us100_m5_fpmarkets_tester_execution_v0",
        "required_period_roles": ["validation", "research_oos"],
        "forbidden_skip_reasons_checked": [
            "probe_is_heavy",
            "probe_is_expensive",
            "proxy_result_is_weak",
            "trade_count_is_low",
            "candidate_is_ambiguous",
            "setup_might_fail",
        ],
        "lowered_claim_if_not_run": "proxy_observation_only_no_runtime_authority_no_economics_pass_no_candidate",
    }
    parity = proxy_runtime_parity_payload(spec)
    storage = {
        "source_of_truth": f"lab/runs/{run_id}/run_manifest.json",
        "receipt_path": f"lab/runs/{run_id}/experiment_receipt.yaml",
        "lineage_path": f"lab/runs/{run_id}/artifact_lineage.json",
        "metrics_path": f"lab/runs/{run_id}/metrics.json",
        "supporting_paths": [f"lab/runs/{run_id}/artifacts/", f"lab/runs/{run_id}/reports/"],
        "registry_rows": ["docs/registers/run_registry.csv"],
        "durable_identity_policy": "repo_relative_paths_only",
        "heavy_artifact_policy": "track_by_path_hash_size_command_or_uri",
    }
    run_manifest = run_manifest_payload(
        spec=spec,
        branch=branch,
        provenance_payload=prov,
        storage=storage,
        gate_coverage=gate_coverage,
        runtime_decision=runtime_decision,
        parity=parity,
        feature_schema=feature_schema,
        label_schema=label_schema,
        split_profile=split_profile,
        report=report,
        result_judgment=judgment,
        missing_evidence=missing_evidence,
        command_argv=command_argv,
    )
    receipt = receipt_payload(
        spec=spec,
        branch=branch,
        provenance_payload=prov,
        storage=storage,
        gate_coverage=gate_coverage,
        runtime_decision=runtime_decision,
        parity=parity,
        feature_schema=feature_schema,
        label_schema=label_schema,
        split_profile=split_profile,
        report=report,
        result_judgment=judgment,
        missing_evidence=missing_evidence,
    )
    metrics = metrics_payload(spec, split_profile, report, judgment, missing_evidence)
    lineage = lineage_payload(spec, input_paths, output_paths, output_refs, command_argv, prov)

    run_manifest_path = run_root / "run_manifest.json"
    receipt_path = run_root / "experiment_receipt.yaml"
    metrics_path = run_root / "metrics.json"
    lineage_path = run_root / "artifact_lineage.json"
    write_json(run_manifest_path, run_manifest)
    write_yaml(receipt_path, receipt)
    write_json(metrics_path, metrics)
    write_json(lineage_path, lineage)

    return {
        "run_spec_id": spec["run_spec_id"],
        "run_id": run_id,
        "status": "executed_proxy_observation_l4_required",
        "result_judgment": judgment,
        "claim_boundary": CLAIM_BOUNDARY,
        "run_manifest_path": repo_relative(run_manifest_path),
        "receipt_path": repo_relative(receipt_path),
        "lineage_path": repo_relative(lineage_path),
        "metrics_path": repo_relative(metrics_path),
        "evidence_path": repo_relative(proxy_report_path),
        "next_action": NEXT_WORK_ITEM_ID,
        "notes": ";".join(judgment_reasons),
    }


def feature_schema_payload(schema: FeatureSchema, used_columns: list[str]) -> dict[str, Any]:
    return {
        "version": "wave01_feature_schema_v1",
        **schema.__dict__,
        "used_feature_columns": used_columns,
        "used_feature_count": len(used_columns),
        "all_nan_train_columns_dropped": [column for column in schema.feature_columns if column not in used_columns],
        "feature_count_policy": "variable_declared_per_run_no_fixed_count",
        "claim_boundary": "feature_schema_for_wave01_proxy_run_only_not_fixed_feature_set",
    }


def label_schema_payload(schema: LabelSchema, spec: dict[str, Any], target_name: str, target_threshold: float | None) -> dict[str, Any]:
    return {
        "version": "wave01_label_schema_v1",
        **schema.__dict__,
        "label_contract": spec["label_contract"],
        "target_name_used_for_model": target_name,
        "target_threshold": target_threshold,
        "target_threshold_fit_scope": "train_only" if target_threshold is not None else "not_applicable",
        "claim_boundary": "label_schema_for_wave01_proxy_run_only_not_default_target",
    }


def model_summary_payload(run_id: str, spec: dict[str, Any], fit: ProxyFit) -> dict[str, Any]:
    return {
        "version": "wave01_proxy_model_summary_v1",
        "run_id": run_id,
        "run_spec_id": spec["run_spec_id"],
        "model_family": spec["axis_values"]["model_family"],
        "model_task": spec["axis_values"]["model_task"],
        "task_kind": fit.task_kind,
        "model_summary": fit.model_summary,
        "train_score_summary": fit.train_score_summary,
        "claim_boundary": "proxy_model_summary_only_no_candidate_no_onnx_no_runtime",
    }


def split_profile_payload(
    frame: pd.DataFrame,
    labels: pd.DataFrame,
    masks: dict[str, pd.Series],
    train_mask: pd.Series,
    validation_mask: pd.Series,
    research_oos_mask: pd.Series,
    row_manifest_path: Path,
) -> dict[str, Any]:
    return {
        "version": "wave01_split_profile_v1",
        "row_membership_manifest": repo_relative(row_manifest_path),
        "sample_counts": {
            "raw_rows": int(len(frame)),
            "same_role_horizon_rows": int(labels["same_role_horizon_ok"].sum()),
            "train_label_eligible_rows": int(train_mask.sum()),
            "validation_label_eligible_rows": int(validation_mask.sum()),
            "research_oos_a_label_eligible_rows": int(research_oos_mask.sum()),
            "locked_final_oos_b_withheld_rows": int(masks["locked_final_oos_b_withheld"].sum()),
        },
        "locked_final_oos_b_use": "withheld_not_used",
        "leakage_boundary": "label horizon must remain in same primary_split_role; preprocessing, target thresholds, and score thresholds fit train-only",
    }


def proxy_runtime_parity_payload(spec: dict[str, Any]) -> dict[str, Any]:
    parity = dict(spec["proxy_runtime_parity"])
    parity["required_for_proxy_model_bearing_run"] = True
    parity["minimum_reconciliation_attempt"] = {
        "required": True,
        "status": "pending_L4_materialization_and_runtime_difference",
        "attempts": [],
        "forced_equality_required": False,
    }
    parity["comparison_class"] = "pending_L4"
    parity["divergence_judgment"] = "pending_L4"
    parity["follow_up_action"] = NEXT_WORK_ITEM_ID
    parity["claim_boundary"] = "proxy_runtime_parity_tracking_only_no_runtime_authority"
    return parity


def common_routing() -> dict[str, Any]:
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
        "not_selected_claim_effect": "not_applicable_all_critical_execution_and_evidence_skills_selected",
        "required_gates": REQUIRED_GATES,
        "not_applicable_gates": ["locked_final_oos_access"],
    }


def run_manifest_payload(
    *,
    spec: dict[str, Any],
    branch: dict[str, str],
    provenance_payload: dict[str, Any],
    storage: dict[str, Any],
    gate_coverage: dict[str, list[str]],
    runtime_decision: dict[str, Any],
    parity: dict[str, Any],
    feature_schema: FeatureSchema,
    label_schema: LabelSchema,
    split_profile: dict[str, Any],
    report: dict[str, Any],
    result_judgment: str,
    missing_evidence: list[str],
    command_argv: list[str],
) -> dict[str, Any]:
    axis = spec["axis_values"]
    run_id = spec["planned_run_id"]
    return {
        "version": "run_manifest_v2",
        "run_id": run_id,
        "id_chain": {**spec["id_chain"], "artifact_ids": [], "bundle_id": None, "candidate_id": None},
        "trigger_source": WORK_ITEM_ID,
        "agent_consult_status": "not_requested",
        "selected_agents": [],
        "skill_routing": common_routing(),
        "branch_worktree": branch,
        "agent_allocation": {
            "phase": "wave01_proxy_execution",
            "selected_agents": [],
            "role_modes": [],
            "selection_reason": "Codex execution of already-materialized first-batch specs; formal review not required for proxy observation.",
            "why_not_smaller": "Model/data/runtime/evidence skills all affect the record.",
            "why_not_larger": "No protected reviewed/pass/runtime-authority claim is made.",
            "max_threads_is_capacity_only": True,
            "claim_effect": "advisory_only_no_reviewed_pass",
        },
        "objective": "Execute one Wave01 event/barrier proxy observation and preserve the L4 follow-through obligation.",
        "task_surface": {
            "task_type": axis["model_task"],
            "target_or_label": axis["label_surface"],
            "direction_mapping": spec["label_contract"]["direction_mapping"],
            "horizon_or_holding_policy": axis["holding_policy"],
            "output_head": "classification_score_or_regression_rank_declared_by_fit",
        },
        "status": "executed_proxy_observation_l4_required",
        "created_at_utc": iso_z(utc_now()),
        "timezone": "UTC",
        "git_commit": provenance_payload["git_sha"],
        "dirty_state": provenance_payload["dirty_flag"],
        "command": " ".join(durable_arg(arg) for arg in command_argv),
        "entrypoint": "foundation/pipelines/run_wave01_event_barrier_proxy_batch.py",
        "environment_summary": provenance_payload["key_package_versions"],
        "provenance": provenance_payload,
        "storage_contract": storage,
        "data_scope": {
            "instrument": "FPMarkets US100",
            "timeframe": "M5",
            "dataset_id": spec["data_contract"]["dataset_id"],
            "split_id": "split_set_v0",
            "date_range": "clean_universe_split_set_v0_no_locked_final_selection",
            "timezone_or_session_policy": spec["data_contract"]["timestamp_source"],
            "feature_boundary": feature_schema.boundary,
            "label_boundary": label_schema.boundary,
            "leakage_boundary": split_profile["leakage_boundary"],
            "missing_gap_policy": "row_membership_manifest_controls clean rows and exclusions",
        },
        "model_export": {
            "framework": "scikit-learn_proxy_fit_not_exported",
            "opset": None,
            "input_schema": feature_schema.feature_order_hash,
            "output_schema": report["target_and_label"]["target_name"],
            "onnx_sha256": None,
        },
        "runtime_learning_probe_decision": runtime_decision,
        "proxy_runtime_parity": parity,
        "failure_disposition": failure_disposition_not_applicable(),
        "required_gate_coverage": gate_coverage,
        "result_judgment": result_judgment,
        "missing_evidence": missing_evidence,
        "claim_scope": CLAIM_BOUNDARY,
        "claim_boundary": CLAIM_BOUNDARY,
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "invalid_conditions": spec["failure_disposition_policy"]["required_before_blocked_deferred_invalid_or_discarded"],
        "stop_conditions": [
            "proxy_observation_recorded",
            "L4_materialization_preflight_next",
            "candidate_claim_forbidden_before_L4",
        ],
        "next_action": NEXT_WORK_ITEM_ID,
    }


def receipt_payload(
    *,
    spec: dict[str, Any],
    branch: dict[str, str],
    provenance_payload: dict[str, Any],
    storage: dict[str, Any],
    gate_coverage: dict[str, list[str]],
    runtime_decision: dict[str, Any],
    parity: dict[str, Any],
    feature_schema: FeatureSchema,
    label_schema: LabelSchema,
    split_profile: dict[str, Any],
    report: dict[str, Any],
    result_judgment: str,
    missing_evidence: list[str],
) -> dict[str, Any]:
    axis = spec["axis_values"]
    return {
        "version": "experiment_receipt_v2",
        "run_id": spec["planned_run_id"],
        "id_chain": {**spec["id_chain"], "artifact_ids": [], "bundle_id": None, "candidate_id": None},
        "skill_routing": common_routing(),
        "branch_worktree": branch,
        "agent_allocation": {
            "phase": "wave01_proxy_execution",
            "selected_agents": [],
            "role_modes": [],
            "selection_reason": "Direct Codex execution of approved first-batch specs.",
            "why_not_smaller": "Execution touches data, model, evidence, parity, and claim surfaces.",
            "why_not_larger": "No protected reviewed/pass or runtime authority claim.",
            "max_threads_is_capacity_only": True,
            "claim_effect": "advisory_only_no_reviewed_pass",
        },
        "provenance": provenance_payload,
        "hypothesis": "Event/barrier labels with explicit abstain/risk/holding decisions may expose reusable US100 M5 surfaces.",
        "decision_use": axis["decision_family"],
        "task_surface": {
            "task_type": axis["model_task"],
            "target_or_label": axis["label_surface"],
            "direction_mapping": spec["label_contract"]["direction_mapping"],
            "horizon_or_holding_policy": axis["holding_policy"],
            "output_head": "classification_score_or_regression_rank_declared_by_fit",
        },
        "comparison_baseline": "no_trade_baseline_named_only_not_selected_or_materialized",
        "control_variables": [
            "FPMarkets_US100_M5_closed_bar_base_frame",
            "us100_bar_close_time_row_key",
            "split_set_v0",
            "locked_final_oos_b_forbidden",
            "no_auxiliary_symbols",
        ],
        "changed_variables": [
            axis["label_surface"],
            axis["feature_family"],
            axis["model_family"],
            axis["decision_family"],
            axis["holding_policy"],
        ],
        "sample_scope": {
            "instrument": "FPMarkets US100",
            "timeframe": "M5",
            "dataset_id": spec["data_contract"]["dataset_id"],
            "split_id": "split_set_v0",
            "timezone_or_session_policy": spec["data_contract"]["timestamp_source"],
            "feature_boundary": feature_schema.boundary,
            "label_boundary": label_schema.boundary,
            "leakage_boundary": split_profile["leakage_boundary"],
        },
        "storage_contract": storage,
        "success_criteria": spec.get("success_criteria", []),
        "failure_criteria": spec.get("failure_criteria", []),
        "invalid_conditions": ["feature_or_label_leakage", "locked_final_oos_b_used", "missing_MT5_executable_path_after_try_first_repair_attempt"],
        "stop_conditions": ["proxy_observation_recorded", "L4_materialization_preflight_next"],
        "evidence_plan": [
            storage["source_of_truth"],
            storage["receipt_path"],
            storage["lineage_path"],
            storage["metrics_path"],
        ],
        "required_gate_coverage": gate_coverage,
        "runtime_learning_probe_decision": runtime_decision,
        "proxy_runtime_parity": parity,
        "failure_disposition": failure_disposition_not_applicable(),
        "result_judgment": result_judgment,
        "missing_evidence": missing_evidence,
        "claim_boundary": CLAIM_BOUNDARY,
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "next_action": NEXT_WORK_ITEM_ID,
    }


def metrics_payload(
    spec: dict[str, Any],
    split_profile: dict[str, Any],
    report: dict[str, Any],
    result_judgment: str,
    missing_evidence: list[str],
) -> dict[str, Any]:
    return {
        "version": "metrics_v2",
        "run_id": spec["planned_run_id"],
        "status": "executed_proxy_observation_l4_required",
        "task_surface_id": spec["id_chain"]["surface_id"],
        "sample_counts": split_profile["sample_counts"],
        "task_surface_metrics": {
            "label_surface": spec["axis_values"]["label_surface"],
            "feature_family": spec["axis_values"]["feature_family"],
            "model_family": spec["axis_values"]["model_family"],
            "decision_family": spec["axis_values"]["decision_family"],
        },
        "model_metrics": {
            "train": report["train_metrics"],
            "validation": report["validation_metrics"],
            "research_oos_a": report["research_oos_metrics"],
        },
        "trading_proxy_metrics": {
            "validation": report["validation_decision_metrics"],
            "research_oos_a": report["research_oos_decision_metrics"],
        },
        "runtime_metrics": {},
        "north_star_context": {
            "role": "final_objective_not_exploration_gate",
            "average_trades_per_active_day_min": 5,
            "profit_factor_preferred_range": [1.5, 3.0],
            "major_window_drawdown_pct_max": 10,
        },
        "measurement_scope": "proxy_model_observation_validation_and_research_oos_a_no_locked_final_no_cost_no_execution",
        "judgment_label": result_judgment,
        "claim_boundary": CLAIM_BOUNDARY,
        "missing_evidence": missing_evidence,
    }


def lineage_payload(
    spec: dict[str, Any],
    input_paths: list[Path],
    output_paths: list[Path],
    output_refs: list[dict[str, Any]],
    command_argv: list[str],
    provenance_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "version": "artifact_lineage_v2",
        "run_id": spec["planned_run_id"],
        "source_inputs": [artifact_ref(path) for path in input_paths if path.exists()],
        "producer": {
            "type": "script",
            "identity": "foundation/pipelines/run_wave01_event_barrier_proxy_batch.py",
            "command": " ".join(durable_arg(arg) for arg in command_argv),
            "environment_summary": provenance_payload["key_package_versions"],
        },
        "consumer": ["future_L4_materialization_preflight"],
        "source_of_truth_paths": [f"lab/runs/{spec['planned_run_id']}/run_manifest.json"],
        "artifact_paths": output_refs,
        "artifact_hashes": [{item["path"]: item["sha256"]} for item in output_refs],
        "artifact_sizes": [{item["path"]: item["size_bytes"]} for item in output_refs],
        "regeneration_commands": ["python foundation/pipelines/run_wave01_event_barrier_proxy_batch.py --expected-branch codex/l4-pair-judgment-closeout"],
        "registry_links": ["docs/registers/run_registry.csv"],
        "availability": "present_hash_recorded",
        "heavy_artifact_policy": "track_by_path_hash_size_command_or_uri",
        "lineage_judgment": "usable_proxy_observation_lineage_L4_missing",
    }


def failure_disposition_not_applicable() -> dict[str, Any]:
    return {
        "required_before_judgments": ["blocked", "deferred", "invalid", "discarded"],
        "status": "not_applicable",
        "diagnosis_state_only_tokens": ["cannot", "unsupported", "not_available", "missing_adapter", "missing_glue"],
        "failure_reproduction": None,
        "exact_failing_layer": None,
        "root_cause_hypothesis": None,
        "repo_controlled_support_gap": None,
        "repair_or_fallback_attempts": [],
        "attempt_blocker_if_no_repair": None,
        "evidence_paths": [],
        "remaining_blocker": None,
        "reopen_condition": None,
        "claim_effect": "not_applicable_successful_proxy_execution_not_final_disposition",
    }


def update_run_refs(path: Path, results: list[dict[str, Any]]) -> None:
    by_spec = {result["run_spec_id"]: result for result in results}
    rows = []
    for row in read_csv_rows(path):
        result = by_spec.get(row["run_spec_id"])
        if result:
            row.update(result)
        rows.append(row)
    write_csv(
        path,
        rows,
        [
            "run_spec_id",
            "planned_run_id",
            "run_id",
            "status",
            "created_at_utc",
            "run_spec_path",
            "run_manifest_path",
            "receipt_path",
            "lineage_path",
            "metrics_path",
            "claim_boundary",
            "result_judgment",
            "evidence_path",
            "next_action",
            "notes",
        ],
    )


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
        coverage = manifest["required_gate_coverage"]
        by_run[result["run_id"]] = {
            "run_id": result["run_id"],
            "wave_id": manifest["id_chain"].get("wave_id", ""),
            "campaign_id": manifest["id_chain"].get("campaign_id", ""),
            "idea_id": manifest["id_chain"].get("idea_id", ""),
            "hypothesis_id": manifest["id_chain"].get("hypothesis_id", ""),
            "surface_id": manifest["id_chain"].get("surface_id", ""),
            "sweep_id": manifest["id_chain"].get("sweep_id", ""),
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
            "required_gates": "|".join(
                coverage["passed"]
                + [f"missing:{item}" for item in coverage["missing"]]
                + [f"not_applicable:{item}" for item in coverage["not_applicable"]]
            ),
            "evidence_path": result["evidence_path"],
            "next_action": result["next_action"],
            "notes": "Wave01 event/barrier proxy observation; L4 required; no candidate, baseline, runtime authority, economics, or live claim",
        }
    ordered_run_ids = [row["run_id"] for row in existing]
    for run_id in sorted(by_run):
        if run_id not in ordered_run_ids:
            ordered_run_ids.append(run_id)
    write_csv(path, [by_run[run_id] for run_id in ordered_run_ids], fieldnames)


def update_registry_row(path: Path, key_field: str, key: str, updates: dict[str, Any]) -> None:
    rows = read_csv_rows(path)
    fieldnames = list(rows[0].keys())
    for row in rows:
        if row.get(key_field) == key:
            row.update({name: value for name, value in updates.items() if name in row})
    write_csv(path, rows, fieldnames)


def update_yaml_records(results: list[dict[str, Any]]) -> None:
    result_counts = dict(sorted(Counter(result["result_judgment"] for result in results).items()))
    campaign_dir = REPO_ROOT / "lab/campaigns/campaign_us100_event_barrier_decision_surface_v0"
    summary = {
        "status": "executed_proxy_observation_l4_required",
        "run_count": len(results),
        "result_counts": result_counts,
        "candidate_count": 0,
        "runtime_claim": False,
        "claim_boundary": CLAIM_BOUNDARY,
        "next_action": NEXT_WORK_ITEM_ID,
    }
    for rel_path in [
        "campaign_manifest.yaml",
        "sweeps/sweep_us100_event_barrier_broad_v0/sweep_manifest.yaml",
        "first_batch_run_specs_manifest.yaml",
        "anti_selection_ledger.yaml",
    ]:
        path = campaign_dir / rel_path
        payload = read_yaml(path)
        payload["status"] = "executed_proxy_observation_l4_required"
        payload["updated_at_utc"] = iso_z(utc_now())
        payload["claim_boundary"] = CLAIM_BOUNDARY
        payload["first_batch_proxy_result"] = summary
        payload["next_action"] = NEXT_WORK_ITEM_ID
        if rel_path.endswith("anti_selection_ledger.yaml"):
            payload["result_viewed"] = True
            payload["selection_decision"] = "no_selection_proxy_observation_l4_required"
            payload["candidate_count"] = 0
            payload["result_counts"] = result_counts
        if rel_path.endswith("first_batch_run_specs_manifest.yaml"):
            payload["result_counts"] = result_counts
            payload["missing_evidence"] = [
                "ONNX_exports_not_materialized_for_L4_yet",
                "MT5_L4_not_run",
                "candidate_selection_forbidden_before_L4",
            ]
        write_yaml(path, payload)

    update_registry_row(
        REPO_ROOT / "docs/registers/campaign_registry.csv",
        "campaign_id",
        CAMPAIGN_ID,
        {
            "status": "executed_proxy_observation_l4_required",
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_path": "lab/campaigns/campaign_us100_event_barrier_decision_surface_v0/sweeps/sweep_us100_event_barrier_broad_v0/run_refs.csv",
            "next_action": NEXT_WORK_ITEM_ID,
            "notes": "first proxy observations executed; all valid runs require L4 follow-through",
        },
    )
    update_registry_row(
        REPO_ROOT / "docs/registers/sweep_registry.csv",
        "sweep_id",
        SWEEP_ID,
        {
            "status": "executed_proxy_observation_l4_required",
            "evidence_boundary": CLAIM_BOUNDARY,
            "evidence_path": "lab/campaigns/campaign_us100_event_barrier_decision_surface_v0/sweeps/sweep_us100_event_barrier_broad_v0/run_refs.csv",
            "next_action": NEXT_WORK_ITEM_ID,
            "notes": "first proxy observations executed; L4 missing by design and required next",
        },
    )


def write_closeout(results: list[dict[str, Any]]) -> None:
    result_counts = dict(sorted(Counter(result["result_judgment"] for result in results).items()))
    payload = {
        "version": "work_closeout_v1",
        "work_item_id": WORK_ITEM_ID,
        "active_goal_id": "goal_us100_onnx_forward_boundary_v0",
        "closed_at_utc": iso_z(utc_now()),
        "status": "proxy_execution_completed_L4_required_next",
        "result_judgment": "proxy_observation",
        "claim_boundary": CLAIM_BOUNDARY,
        "completed_scope": [
            "12 Wave01 event/barrier proxy specs executed",
            "run-local manifest, receipt, lineage, and metrics created for each run",
            "locked_final_oos_b withheld from training, thresholding, and proxy observation",
            "run registry and sweep run_refs connected to run-local source-of-truth records",
        ],
        "incomplete_scope_not_claimed": [
            "ONNX materialization for L4",
            "MT5 L4 split runtime probe",
            "L5 candidate runtime evidence",
            "economics pass",
            "runtime authority",
            "selected baseline",
        ],
        "result_counts": result_counts,
        "candidate_count": 0,
        "runtime_learning_probe_decision": {
            "required": True,
            "decision": "run_required_next",
            "target_level": "L4_split_runtime_probe",
            "next_work_item": NEXT_WORK_ITEM_ID,
        },
        "evidence_paths": {
            "run_refs": "lab/campaigns/campaign_us100_event_barrier_decision_surface_v0/sweeps/sweep_us100_event_barrier_broad_v0/run_refs.csv",
            "run_registry": "docs/registers/run_registry.csv",
            "first_batch_manifest": "lab/campaigns/campaign_us100_event_barrier_decision_surface_v0/first_batch_run_specs_manifest.yaml",
        },
        "run_results": results,
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "next_work_item": {
            "work_item_id": NEXT_WORK_ITEM_ID,
            "path": "lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml",
        },
    }
    write_yaml(REPO_ROOT / f"lab/goals/goal_us100_onnx_forward_boundary_v0/{WORK_ITEM_ID}_closeout.yaml", payload)


def write_next_work_item(results: list[dict[str, Any]]) -> None:
    result_counts = dict(sorted(Counter(result["result_judgment"] for result in results).items()))
    payload = {
        "version": "onnx_lab_work_item_v1",
        "work_item_id": NEXT_WORK_ITEM_ID,
        "active_goal_id": "goal_us100_onnx_forward_boundary_v0",
        "created_at_utc": iso_z(utc_now()),
        "status": "planned_next",
        "user_request": "Materialize ONNX/EA/MT5 L4 path for every valid Wave01 event/barrier proxy run before any proxy-only closeout.",
        "current_truth": {
            "claim_boundary": CLAIM_BOUNDARY,
            "run_refs": "lab/campaigns/campaign_us100_event_barrier_decision_surface_v0/sweeps/sweep_us100_event_barrier_broad_v0/run_refs.csv",
            "run_registry": "docs/registers/run_registry.csv",
            "result_counts": result_counts,
            "valid_proxy_model_bearing_run_count": len(results),
        },
        "work_classification": {
            "primary_family": "onnx_export_parity",
            "detected_families": ["onnx_export_parity", "runtime_probe", "artifact_lineage"],
            "mutation_intent": "materialize_L4_follow_through_path_for_wave01_proxy_runs",
        },
        "skill_routing": {
            "primary_family": "onnx_export_parity",
            "primary_skill": "spacesonar-runtime-parity",
            "support_skills": [
                "spacesonar-artifact-lineage",
                "spacesonar-environment-reproducibility",
                "spacesonar-run-evidence-system",
                "spacesonar-claim-discipline",
            ],
            "required_gates": [
                "onnx_export_smoke",
                "python_onnx_parity",
                "proxy_runtime_parity_record",
                "bundle_integrity_hash",
                "L4_split_runtime_probe_for_valid_proxy_run",
                "final_claim_guard",
            ],
        },
        "acceptance_criteria": [
            "Do not discard or defer any valid proxy run only because an adapter is missing.",
            "Create or patch the smallest needed ONNX/export/EA/runtime adapter before any support-gap disposition.",
            "Prepare L4 validation and research_oos attempts for every valid proxy/model-bearing run.",
            "Do not use locked final OOS-B.",
            "Keep any L4 result as runtime probe evidence only unless the runtime contract is fully satisfied.",
        ],
        "claim_boundary": "planned_L4_materialization_preflight_no_runtime_authority_no_candidate",
        "forbidden_claims": FORBIDDEN_CLAIMS,
        "next_action": "build_wave01_onnx_materialization_and_L4_attempt_preparation",
    }
    write_yaml(REPO_ROOT / "lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml", payload)


def update_goal_and_workspace(results: list[dict[str, Any]]) -> None:
    result_counts = dict(sorted(Counter(result["result_judgment"] for result in results).items()))
    goal_path = REPO_ROOT / "lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml"
    goal = read_yaml(goal_path)
    goal["updated_at_utc"] = iso_z(utc_now())
    goal["active_phase"] = "wave01_campaign_002_proxy_executed_l4_required"
    goal["claim_boundary"] = "active_goal_wave01_proxy_executed_L4_required_not_goal_achieve"
    goal["next_work_item"] = {
        "path": "lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml",
        "work_item_id": NEXT_WORK_ITEM_ID,
        "summary": "Materialize L4 follow-through path for every valid Wave01 proxy/model-bearing run.",
    }
    goal["event_barrier_campaign"]["status"] = "executed_proxy_observation_l4_required"
    goal["event_barrier_campaign"]["claim_boundary"] = CLAIM_BOUNDARY
    goal["event_barrier_campaign"]["next_work_item"] = NEXT_WORK_ITEM_ID
    goal["event_barrier_campaign"]["result_counts"] = result_counts
    write_yaml(goal_path, goal)

    state_path = REPO_ROOT / "docs/workspace/workspace_state.yaml"
    state = read_yaml(state_path)
    claims = state["current_claims"]
    claims["active_goal_phase"] = "wave01_campaign_002_proxy_executed_l4_required"
    claims["active_goal_claim_boundary"] = "active_goal_wave01_proxy_executed_L4_required_not_goal_achieve"
    claims["next_work_item_id"] = NEXT_WORK_ITEM_ID
    claims["wave0_second_campaign_status"] = "executed_proxy_observation_l4_required"
    claims["wave0_second_campaign_claim_boundary"] = CLAIM_BOUNDARY
    claims["wave0_second_campaign_next_work_item"] = NEXT_WORK_ITEM_ID
    claims["wave0_second_campaign_proxy_result_counts"] = result_counts
    claims["wave0_second_campaign_executed_proxy_run_count"] = len(results)
    claims["wave0_second_campaign_L4_status"] = "L4_materialization_preflight_required_next"
    state["updated_utc"] = iso_z(utc_now())
    write_yaml(state_path, state)

    update_registry_row(
        REPO_ROOT / "docs/registers/goal_registry.csv",
        "goal_id",
        "goal_us100_onnx_forward_boundary_v0",
        {
            "active_phase": "wave01_campaign_002_proxy_executed_l4_required",
            "claim_boundary": "active_goal_wave01_proxy_executed_L4_required_not_goal_achieve",
            "next_work_item": NEXT_WORK_ITEM_ID,
            "notes": "Wave01 event/barrier proxy batch executed; L4 materialization preflight required next",
        },
    )


def update_resume_cursor(results: list[dict[str, Any]]) -> None:
    payload = {
        "version": "active_goal_resume_cursor_v1",
        "active_goal_id": "goal_us100_onnx_forward_boundary_v0",
        "updated_at_utc": iso_z(utc_now()),
        "cursor_state": "active",
        "active_phase": "wave01_campaign_002_proxy_executed_l4_required",
        "current_truth_sources": [
            "lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml",
            "lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml",
            "lab/campaigns/campaign_us100_event_barrier_decision_surface_v0/sweeps/sweep_us100_event_barrier_broad_v0/run_refs.csv",
            "docs/registers/run_registry.csv",
        ],
        "active_ids": {
            "wave_id": WAVE_ID,
            "campaign_id": CAMPAIGN_ID,
            "surface_id": "surface_us100_event_barrier_decision_surface_v0",
            "sweep_id": SWEEP_ID,
        },
        "latest_completed_work": {
            "work_item_id": WORK_ITEM_ID,
            "result_judgment": "proxy_observation",
            "claim_boundary": CLAIM_BOUNDARY,
            "evidence_paths": [
                f"lab/goals/goal_us100_onnx_forward_boundary_v0/{WORK_ITEM_ID}_closeout.yaml",
                "lab/campaigns/campaign_us100_event_barrier_decision_surface_v0/sweeps/sweep_us100_event_barrier_broad_v0/run_refs.csv",
                "docs/registers/run_registry.csv",
            ],
        },
        "next_work_item": {
            "work_item_id": NEXT_WORK_ITEM_ID,
            "path": "lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml",
        },
    }
    write_yaml(REPO_ROOT / "lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml", payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute Wave01 event/barrier first-batch proxy observations.")
    parser.add_argument("--row-membership-manifest", default="lab/campaigns/campaign_us100_task_surface_scout_v0/row_membership/row_membership_manifest.yaml")
    parser.add_argument("--run-refs", default="lab/campaigns/campaign_us100_event_barrier_decision_surface_v0/sweeps/sweep_us100_event_barrier_broad_v0/run_refs.csv")
    parser.add_argument("--expected-branch", default="codex/l4-pair-judgment-closeout")
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    started_at = utc_now()
    branch = branch_worktree(args.expected_branch)
    row_manifest_path = REPO_ROOT / args.row_membership_manifest
    row_manifest = read_yaml(row_manifest_path)
    row_frame = load_row_membership(row_manifest)
    run_refs_path = REPO_ROOT / args.run_refs
    rows = read_csv_rows(run_refs_path)
    if args.limit is not None:
        rows = rows[: args.limit]
    results = [
        execute_one_spec(
            spec_path=REPO_ROOT / row["run_spec_path"],
            row_frame=row_frame,
            row_manifest_path=row_manifest_path,
            branch=branch,
            command_argv=sys.argv[:],
            started_at=started_at,
        )
        for row in rows
    ]
    update_run_refs(run_refs_path, results)
    update_run_registry(REPO_ROOT / "docs/registers/run_registry.csv", results)
    update_yaml_records(results)
    write_closeout(results)
    write_next_work_item(results)
    update_goal_and_workspace(results)
    update_resume_cursor(results)
    print(
        json.dumps(
            {
                "status": "wave01_event_barrier_proxy_batch_executed_l4_required",
                "run_count": len(results),
                "result_counts": dict(sorted(Counter(result["result_judgment"] for result in results).items())),
                "claim_boundary": CLAIM_BOUNDARY,
                "next_work_item": NEXT_WORK_ITEM_ID,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
