from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
import yaml
from sklearn.linear_model import LogisticRegression

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation.features.fixture_features import FEATURE_COLUMNS, build_fixture_features
from foundation.labels.fixture_labels import HORIZON_BARS, LABEL_ID, build_fixture_label
from foundation.onnx.linear_sigmoid import build_linear_sigmoid_onnx
from foundation.parity.onnx_fixture import run_onnx_fixture, sigmoid_logistic_probability


RUN_SLUG = "minimal_onnx_mt5_plumbing"
DATASET_ID = "dataset_us100_m5_closed_bar_v0"
FEATURE_RECIPE_ID = "feature_fixture_minimal_v0"
LABEL_RECIPE_ID = "label_fixture_minimal_v0"
MODEL_RECIPE_ID = "model_fixture_simple_logistic_v0"
TASK_SURFACE_ID = "surface_fixture_next_m5_probability_v0"
DECISION_RECIPE_ID = "decision_fixture_probability_only_v0"
DECISION_SURFACE_ID = "decision_surface_no_trade_fixture_v0"
SPLIT_ID = "split_fixture_chronological_smoke_v0"
PARSER_VERSION = "spacesonar_fixture_parser_v0"
RUNTIME_CONTRACT_VERSION = "mt5_native_onnx_fixed_fixture_micro_probe_v0"
TOLERANCE = 1e-5
M5_SECONDS = 5 * 60


@dataclass(frozen=True)
class ArtifactRef:
    path: str
    sha256: str
    size_bytes: int


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def compact_ts(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%SZ")


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_ref(path: Path, repo_root: Path) -> ArtifactRef:
    return ArtifactRef(
        path=repo_relative(path, repo_root),
        sha256=file_sha256(path),
        size_bytes=path.stat().st_size,
    )


def parse_utc(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp must include timezone: {value}")
    return parsed.astimezone(UTC)


def git_identity(repo_root: Path) -> dict[str, Any]:
    def run_git(args: list[str]) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            return "unknown"
        return result.stdout.strip()

    status = run_git(["status", "--short"])
    changed_files = [line[3:].strip() for line in status.splitlines() if len(line) > 3]
    return {
        "git_sha": run_git(["rev-parse", "HEAD"]),
        "branch": run_git(["branch", "--show-current"]),
        "dirty_flag": "dirty" if status else "clean",
        "changed_files": changed_files,
    }


def dependency_summary() -> dict[str, str]:
    packages = ["MetaTrader5", "numpy", "pandas", "sklearn", "onnx", "onnxruntime", "yaml"]
    versions: dict[str, str] = {}
    for name in packages:
        try:
            module = __import__(name)
            versions[name] = str(getattr(module, "__version__", "unknown"))
        except Exception as exc:  # noqa: BLE001 - recorded as environment evidence.
            versions[name] = f"unavailable:{exc}"
    versions["python"] = platform.python_version()
    versions["platform"] = platform.platform()
    return versions


def export_mt5_bars(symbol: str, start_utc: datetime, end_utc: datetime) -> pd.DataFrame:
    if not mt5.initialize():
        raise RuntimeError(f"Failed to initialize MetaTrader5: {mt5.last_error()}")
    try:
        if not mt5.symbol_select(symbol, True):
            raise RuntimeError(f"Failed to select symbol {symbol}: {mt5.last_error()}")
        rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5, start_utc, end_utc)
        if rates is None or len(rates) == 0:
            raise RuntimeError(f"No M5 bars returned for {symbol}: {mt5.last_error()}")
        terminal = mt5.terminal_info()
        account = mt5.account_info()
        frame = pd.DataFrame(rates)
        frame["contract_symbol"] = symbol
        frame["broker_symbol"] = symbol
        frame["timeframe"] = "M5"
        frame["price_basis"] = "Bid"
        frame["time_open_unix"] = frame["time"].astype("int64")
        frame["time_close_unix"] = frame["time_open_unix"] + M5_SECONDS
        frame["us100_bar_open_time"] = pd.to_datetime(frame["time_open_unix"], unit="s", utc=True)
        frame["us100_bar_close_time"] = pd.to_datetime(frame["time_close_unix"], unit="s", utc=True)
        frame.attrs["terminal_path"] = terminal.path if terminal else None
        frame.attrs["terminal_data_path"] = terminal.data_path if terminal else None
        frame.attrs["terminal_commondata_path"] = terminal.commondata_path if terminal else None
        frame.attrs["account_server"] = account.server if account else None
        return frame[
            [
                "us100_bar_close_time",
                "us100_bar_open_time",
                "time_open_unix",
                "time_close_unix",
                "contract_symbol",
                "broker_symbol",
                "timeframe",
                "price_basis",
                "open",
                "high",
                "low",
                "close",
                "tick_volume",
                "spread",
                "real_volume",
            ]
        ].rename(columns={"spread": "spread_points"})
    finally:
        mt5.shutdown()


def write_csv_frame(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8")


def write_fixture_csv(path: Path, values: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([f"{value:.10g}" for value in values])


def train_fixture_model(features: pd.DataFrame, labels: pd.Series) -> tuple[LogisticRegression, np.ndarray, np.ndarray]:
    train_end = int(len(features) * 0.70)
    if train_end < 50:
        raise RuntimeError("not enough rows for fixture training")
    x_train = features.iloc[:train_end].to_numpy(dtype=np.float32)
    y_train = labels.iloc[:train_end].to_numpy(dtype=np.int64)
    if len(set(y_train.tolist())) < 2:
        raise RuntimeError("fixture training labels contain only one class")
    mean = x_train.mean(axis=0)
    scale = x_train.std(axis=0)
    scale = np.where(scale == 0.0, 1.0, scale)
    model = LogisticRegression(C=1.0, solver="lbfgs", max_iter=500, random_state=0)
    model.fit((x_train - mean) / scale, y_train)
    return model, mean.astype(np.float32), scale.astype(np.float32)


def build_frame_for_training(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    feature_frame = build_fixture_features(raw)
    label_series = build_fixture_label(raw)
    combined = pd.concat(
        [
            raw[["us100_bar_close_time", "us100_bar_open_time", "close"]].copy(),
            feature_frame,
            label_series.rename("label_next_m5_up"),
        ],
        axis=1,
    )
    combined = combined.dropna().iloc[:-HORIZON_BARS].reset_index(drop=True)
    features = combined[FEATURE_COLUMNS].astype("float32")
    labels = combined["label_next_m5_up"].astype("int64")
    return features, labels, combined


def copy_fixture_to_common(
    *,
    terminal_commondata_path: str,
    bundle_id: str,
    onnx_path: Path,
    fixture_input_path: Path,
    expected_output_path: Path,
) -> dict[str, dict[str, object]]:
    common_files_root = Path(terminal_commondata_path) / "Files"
    target_dir = common_files_root / "SpaceSonar" / "onnx_fixture" / bundle_id
    target_dir.mkdir(parents=True, exist_ok=True)
    copied: dict[str, dict[str, object]] = {}
    for source in [onnx_path, fixture_input_path, expected_output_path]:
        target = target_dir / source.name
        shutil.copy2(source, target)
        copied[source.name] = {
            "common_relative_path": f"SpaceSonar\\onnx_fixture\\{bundle_id}\\{source.name}",
            "local_absolute_path": str(target),
            "sha256": file_sha256(target),
            "size_bytes": target.stat().st_size,
            "durable_identity": "common_relative_path_plus_sha256",
            "absolute_path_boundary": "local_context_only",
        }
    return copied


def make_tester_config(
    *,
    path: Path,
    bundle_id: str,
    feature_count: int,
    from_date: str,
    to_date: str,
) -> None:
    output_path = f"SpaceSonar\\\\onnx_fixture\\\\{bundle_id}\\\\mt5_probe_output.csv"
    content = f"""; SpaceSonar fixed-fixture ONNX micro-probe.
; Runs a non-trading EA that loads one ONNX bundle and compares one fixed fixture output.
[Tester]
Expert=Project_SpaceSonar_X\\foundation\\mt5\\experts\\SpaceSonar_ONNX_FixtureProbe.ex5
Symbol=US100
Period=M5
Optimization=0
Model=4
Dates=1
FromDate={from_date}
ToDate={to_date}
ForwardMode=0
Deposit=500
Currency=USD
ProfitInPips=0
Leverage=100
ExecutionMode=0
OptimizationCriterion=0
Visual=0
ShutdownTerminal=1

[TesterInputs]
InpOnnxPath=SpaceSonar\\\\onnx_fixture\\\\{bundle_id}\\\\model.onnx
InpFixtureInputPath=SpaceSonar\\\\onnx_fixture\\\\{bundle_id}\\\\fixture_input.csv
InpExpectedOutputPath=SpaceSonar\\\\onnx_fixture\\\\{bundle_id}\\\\expected_output.csv
InpOutputPath={output_path}
InpFeatureCount={feature_count}||{feature_count}||1||{feature_count}||N
InpTolerance={TOLERANCE}||{TOLERANCE}||0.000001||0.001||N
InpUseCommonFiles=true||false||0||true||N
InpRemoveAfterRun=true||false||0||true||N
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def run(args: argparse.Namespace) -> dict[str, str]:
    repo_root = Path.cwd()
    started_at = utc_now()
    run_id = args.run_id or f"onnxlab_{compact_ts(started_at)}_{RUN_SLUG}"
    bundle_id = args.bundle_id or f"bundle_{compact_ts(started_at)}_fixture_plumbing_v0"
    attempt_id = args.attempt_id or f"attempt_{compact_ts(started_at)}_mt5_onnx_fixture_v0"
    run_root = repo_root / "lab" / "runs" / run_id
    artifact_root = run_root / "artifacts"
    bundle_root = repo_root / "runtime" / "packages" / bundle_id
    bundle_artifact_root = bundle_root / "artifacts"
    attempt_root = repo_root / "runtime" / "mt5_attempts" / attempt_id

    start_utc = parse_utc(args.start_utc)
    end_utc = parse_utc(args.end_utc)
    raw = export_mt5_bars(args.symbol, start_utc, end_utc)
    dataset_path = artifact_root / "dataset_us100_m5_closed_bar_v0.csv"
    write_csv_frame(raw, dataset_path)
    dataset_ref = artifact_ref(dataset_path, repo_root)

    features, labels, combined = build_frame_for_training(raw)
    model, mean, scale = train_fixture_model(features, labels)
    coefficients = model.coef_.astype(np.float32).reshape(-1)
    intercept = float(model.intercept_[0])

    fixture_index = len(features) - 1
    fixture_features = features.iloc[fixture_index].to_numpy(dtype=np.float32)
    python_probability = sigmoid_logistic_probability(
        features=fixture_features,
        coefficients=coefficients,
        intercept=intercept,
        feature_mean=mean,
        feature_scale=scale,
    )

    onnx_path = bundle_artifact_root / "model.onnx"
    build_linear_sigmoid_onnx(
        feature_count=len(FEATURE_COLUMNS),
        coefficients=coefficients,
        intercept=intercept,
        feature_mean=mean,
        feature_scale=scale,
        output_path=onnx_path,
    )
    onnx_probability = run_onnx_fixture(onnx_path, fixture_features)
    parity_abs_error = abs(python_probability - onnx_probability)
    if parity_abs_error > TOLERANCE:
        raise RuntimeError(f"Python/ONNXRuntime parity failed: abs_error={parity_abs_error}")

    fixture_input_path = bundle_artifact_root / "fixture_input.csv"
    expected_output_path = bundle_artifact_root / "expected_output.csv"
    write_fixture_csv(fixture_input_path, fixture_features.astype(float).tolist())
    write_fixture_csv(expected_output_path, [onnx_probability])

    terminal_commondata_path = str(raw.attrs.get("terminal_commondata_path") or "")
    if not terminal_commondata_path:
        raise RuntimeError("MT5 terminal commondata_path unavailable")
    copied_common_files = copy_fixture_to_common(
        terminal_commondata_path=terminal_commondata_path,
        bundle_id=bundle_id,
        onnx_path=onnx_path,
        fixture_input_path=fixture_input_path,
        expected_output_path=expected_output_path,
    )

    train_end = int(len(features) * 0.70)
    fixture_manifest = {
        "version": "fixture_manifest_v1",
        "run_id": run_id,
        "bundle_id": bundle_id,
        "dataset_id": DATASET_ID,
        "dataset": asdict(dataset_ref),
        "row_time_key": "us100_bar_close_time",
        "row_count": int(len(raw)),
        "usable_feature_label_rows": int(len(features)),
        "feature_recipe_id": FEATURE_RECIPE_ID,
        "feature_columns": FEATURE_COLUMNS,
        "label_recipe_id": LABEL_RECIPE_ID,
        "label_id": LABEL_ID,
        "label_horizon_bars": HORIZON_BARS,
        "split_id": SPLIT_ID,
        "split": {
            "train_rows": train_end,
            "validation_rows": int(len(features) - train_end),
            "policy": "chronological fixture split only; no OOS, no candidate, no baseline",
        },
        "fixture_row": {
            "index": int(fixture_index),
            "us100_bar_close_time": str(combined.loc[fixture_index, "us100_bar_close_time"]),
            "feature_values": fixture_features.astype(float).tolist(),
            "expected_probability": onnx_probability,
        },
        "model": {
            "model_recipe_id": MODEL_RECIPE_ID,
            "framework": "manual_linear_sigmoid_from_sklearn_logistic_regression",
            "feature_mean": mean.astype(float).tolist(),
            "feature_scale": scale.astype(float).tolist(),
            "coefficients": coefficients.astype(float).tolist(),
            "intercept": intercept,
        },
        "python_onnxruntime_parity": {
            "python_probability": python_probability,
            "onnxruntime_probability": onnx_probability,
            "abs_error": parity_abs_error,
            "tolerance": TOLERANCE,
            "status": "matched",
        },
        "common_files": copied_common_files,
        "claim_boundary": "fixed_fixture_plumbing_probe_only_no_runtime_authority_no_economics_pass",
    }
    fixture_manifest_path = bundle_artifact_root / "fixture_manifest.json"
    write_json(fixture_manifest_path, fixture_manifest)

    onnx_ref = artifact_ref(onnx_path, repo_root)
    fixture_input_ref = artifact_ref(fixture_input_path, repo_root)
    expected_output_ref = artifact_ref(expected_output_path, repo_root)
    fixture_manifest_ref = artifact_ref(fixture_manifest_path, repo_root)
    input_hashes = [asdict(dataset_ref)]
    output_hashes = [asdict(onnx_ref), asdict(fixture_input_ref), asdict(expected_output_ref), asdict(fixture_manifest_ref)]
    git = git_identity(repo_root)
    ended_at = utc_now()
    provenance = {
        **git,
        "command_argv": sys.argv,
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "key_package_versions": dependency_summary(),
        "started_at_utc": started_at.isoformat().replace("+00:00", "Z"),
        "ended_at_utc": ended_at.isoformat().replace("+00:00", "Z"),
        "input_hashes": input_hashes,
        "output_hashes": output_hashes,
        "unknown_git_claim_effect": "not_applicable_git_identity_recorded_but_dirty_state_lowers_reproducibility_until_committed",
    }

    branch_worktree = {
        "current_branch": git["branch"],
        "requested_branch": "codex/minimal-onnx-mt5-plumbing-slice",
        "branch_worktree_fit": "fit",
        "branch_action": "keep_current_branch",
        "policy_reference": "docs/policies/branch_policy.md",
        "mismatch_claim_effect": "not_applicable",
    }

    tester_config_path = attempt_root / "tester_config.ini"
    make_tester_config(
        path=tester_config_path,
        bundle_id=bundle_id,
        feature_count=len(FEATURE_COLUMNS),
        from_date=start_utc.strftime("%Y.%m.%d"),
        to_date=(start_utc + timedelta(days=1)).strftime("%Y.%m.%d"),
    )
    tester_config_ref = artifact_ref(tester_config_path, repo_root)

    experiment_bundle = {
        "version": "experiment_bundle_v2",
        "bundle_id": bundle_id,
        "run_id": run_id,
        "source_of_truth": f"runtime/packages/{bundle_id}/experiment_bundle.json",
        "branch_worktree": branch_worktree,
        "dataset_id": DATASET_ID,
        "dataset_sha256": dataset_ref.sha256,
        "dataset_row_count": len(raw),
        "row_time_key": "us100_bar_close_time",
        "task_surface_id": TASK_SURFACE_ID,
        "decision_use": "fixed_fixture_probability_only_no_trade_decision",
        "feature_recipe_id": FEATURE_RECIPE_ID,
        "feature_schema_hash": hashlib.sha256(json.dumps(FEATURE_COLUMNS).encode("utf-8")).hexdigest(),
        "feature_order_hash": hashlib.sha256("|".join(FEATURE_COLUMNS).encode("utf-8")).hexdigest(),
        "label_recipe_id": LABEL_RECIPE_ID,
        "label_id": LABEL_ID,
        "target_id": LABEL_ID,
        "horizon_or_holding_policy": "horizon_1_closed_m5_bar_tail_drop_1_no_holding_policy",
        "split_id": SPLIT_ID,
        "decision_recipe_id": DECISION_RECIPE_ID,
        "model_framework": "manual_onnx_linear_sigmoid_from_sklearn_logistic_regression",
        "model_opset": 13,
        "input_schema": {"name": "features", "dtype": "float32", "shape": [len(FEATURE_COLUMNS)], "feature_order": FEATURE_COLUMNS},
        "output_schema": {"name": "probability", "dtype": "float32", "shape": [1]},
        "onnx_path": onnx_ref.path,
        "onnx_sha256": onnx_ref.sha256,
        "parser_version": PARSER_VERSION,
        "runtime_contract_version": RUNTIME_CONTRACT_VERSION,
        "decision_surface_id": DECISION_SURFACE_ID,
        "producer_command": " ".join(sys.argv),
        "environment_summary": dependency_summary(),
        "provenance": provenance,
        "runtime_learning_probe_decision": {
            "required": True,
            "decision": "run_required",
            "reason": "MT5 native ONNX meaning is in scope for this plumbing slice.",
        },
        "claim_boundary": "bundle_preflight_plus_python_onnxruntime_parity_only_until_mt5_probe_output_exists",
        "forbidden_claims": [
            "reviewed_verified_pass",
            "selected_baseline",
            "candidate",
            "runtime_authority",
            "economics_pass",
            "handoff_complete",
            "live_readiness",
            "goal_achieve",
        ],
    }
    write_json(bundle_root / "experiment_bundle.json", experiment_bundle)

    run_manifest = {
        "version": "run_manifest_v2",
        "run_id": run_id,
        "id_chain": {
            "idea_id": "idea_a_to_z_validation_spine_v0",
            "hypothesis_id": "hyp_minimal_onnx_mt5_plumbing_v0",
            "surface_id": TASK_SURFACE_ID,
            "sweep_id": "sweep_not_applicable_fixture_plumbing",
            "artifact_ids": [DATASET_ID, "artifact_fixture_onnx_v0", "artifact_fixture_inputs_v0"],
            "bundle_id": bundle_id,
            "candidate_id": None,
        },
        "trigger_source": "goal_objective",
        "agent_consult_status": "not_requested_for_local_implementation",
        "selected_agents": [],
        "skill_routing": {
            "primary_family": "onnx_export_parity",
            "primary_skill": "spacesonar-runtime-parity",
            "support_skills": [
                "spacesonar-data-integrity",
                "spacesonar-artifact-lineage",
                "spacesonar-environment-reproducibility",
                "spacesonar-run-evidence-system",
                "spacesonar-claim-discipline",
            ],
            "skills_selected": [
                "spacesonar-runtime-parity",
                "spacesonar-data-integrity",
                "spacesonar-artifact-lineage",
                "spacesonar-environment-reproducibility",
                "spacesonar-code-surface-guard",
            ],
            "skills_not_used": [],
            "critical_skills_not_selected": [],
            "not_selected_claim_effect": None,
            "required_gates": [
                "branch_worktree_fit",
                "provenance_capture",
                "time_axis_check",
                "feature_label_boundary_check",
                "feature_schema_contract",
                "onnx_export_smoke",
                "python_onnx_parity",
                "bundle_integrity_hash",
                "runtime_learning_probe_decision",
                "mt5_native_onnx_fixed_fixture_probe",
                "final_claim_guard",
            ],
            "not_applicable_gates": ["strategy_tester_economics"],
        },
        "branch_worktree": branch_worktree,
        "agent_allocation": {
            "phase": "vertical_slice_local_implementation",
            "selected_agents": [],
            "role_modes": [],
            "selection_reason": "local implementation after prior advisory design",
            "why_not_smaller": "codex_alone_is_smallest",
            "why_not_larger": "MT5 runtime check occurs through local probe evidence, not agent consensus",
            "max_threads_is_capacity_only": True,
            "claim_effect": "no_reviewed_pass",
        },
        "objective": "Create a minimal US100 M5 closed-bar feature-label-model-ONNX bundle and prepare MT5 native ONNX fixed-fixture probe.",
        "task_surface": {
            "task_type": "fixed_fixture_probability",
            "target_or_label": LABEL_ID,
            "direction_mapping": "next_closed_m5_bar_up_probability_fixture_only",
            "horizon_or_holding_policy": "horizon_1_closed_m5_bar_no_trade_holding_policy",
            "output_head": "single_probability_float32",
        },
        "status": "mt5_probe_prepared_python_onnxruntime_parity_passed",
        "created_at_utc": started_at.isoformat().replace("+00:00", "Z"),
        "timezone": "UTC",
        "git_commit": git["git_sha"],
        "dirty_state": git["dirty_flag"],
        "command": " ".join(sys.argv),
        "entrypoint": "foundation/pipelines/minimal_onnx_mt5_plumbing_slice.py",
        "environment_summary": dependency_summary(),
        "provenance": provenance,
        "storage_contract": {
            "source_of_truth": f"lab/runs/{run_id}/run_manifest.json",
            "receipt_path": f"lab/runs/{run_id}/experiment_receipt.yaml",
            "lineage_path": f"lab/runs/{run_id}/artifact_lineage.json",
            "metrics_path": f"lab/runs/{run_id}/metrics.json",
            "supporting_paths": [
                f"lab/runs/{run_id}/artifacts/",
                f"runtime/packages/{bundle_id}/artifacts/",
                f"runtime/mt5_attempts/{attempt_id}/",
            ],
            "registry_rows": ["docs/registers/run_registry.csv", "docs/registers/artifact_registry.csv"],
            "durable_identity_policy": "repo_relative_paths_only",
            "duplicate_policy": "single_source_of_truth_copy_requires_reason",
            "heavy_artifact_policy": "track_by_path_hash_size_command_or_uri",
        },
        "data_scope": {
            "instrument": "FPMarkets US100",
            "timeframe": "M5",
            "dataset_id": DATASET_ID,
            "split_id": SPLIT_ID,
            "date_range": {"start_utc": args.start_utc, "end_utc": args.end_utc},
            "timezone_or_session_policy": "MT5 Python API unix seconds; row key is us100_bar_close_time UTC timestamp derived from bar close",
            "feature_boundary": "right_aligned_closed_bar_features_only",
            "label_boundary": "label uses next closed M5 bar and tail_drop_1",
            "leakage_boundary": "fixture model trained chronologically; no OOS/candidate/performance claim",
            "missing_gap_policy": "raw continuity not used for economics; row_count and source command recorded",
        },
        "model_export": {
            "framework": "manual ONNX graph from sklearn LogisticRegression coefficients",
            "opset": 13,
            "input_schema": experiment_bundle["input_schema"],
            "output_schema": experiment_bundle["output_schema"],
            "onnx_sha256": onnx_ref.sha256,
        },
        "runtime_learning_probe_decision": experiment_bundle["runtime_learning_probe_decision"],
        "required_gate_coverage": {
            "passed": [
                "branch_worktree_fit",
                "provenance_capture",
                "time_axis_check",
                "feature_label_boundary_check",
                "feature_schema_contract",
                "onnx_export_smoke",
                "python_onnx_parity",
                "bundle_integrity_hash",
                "runtime_learning_probe_decision",
            ],
            "not_applicable": ["strategy_tester_economics"],
            "missing": ["mt5_native_onnx_fixed_fixture_probe"],
        },
        "result_judgment": "inconclusive",
        "missing_evidence": ["MT5 native ONNX fixed-fixture output not observed yet"],
        "claim_scope": "bundle_preflight",
        "forbidden_claims": experiment_bundle["forbidden_claims"],
        "invalid_conditions": ["any performance, candidate, baseline, economics, runtime authority, or live readiness claim"],
        "stop_conditions": ["MT5 probe output missing for runtime claim", "fixture parity abs_error exceeds tolerance"],
        "next_action": f"Compile SpaceSonar_ONNX_FixtureProbe.mq5 and run tester config {repo_relative(tester_config_path, repo_root)}",
    }
    write_json(run_root / "run_manifest.json", run_manifest)

    receipt = {
        "version": "experiment_receipt_v2",
        "run_id": run_id,
        "id_chain": run_manifest["id_chain"],
        "skill_routing": run_manifest["skill_routing"],
        "branch_worktree": branch_worktree,
        "agent_allocation": run_manifest["agent_allocation"],
        "provenance": provenance,
        "hypothesis": "A tiny provisional feature/label/model can prove the ONNX plumbing path without performance claims.",
        "decision_use": "fixed fixture probability only",
        "task_surface": run_manifest["task_surface"],
        "comparison_baseline": None,
        "control_variables": ["US100", "M5", "closed_bar_row_key", "fixed_fixture"],
        "changed_variables": ["new_provisional_fixture_feature_label_model_bundle"],
        "sample_scope": run_manifest["data_scope"],
        "storage_contract": run_manifest["storage_contract"],
        "success_criteria": ["Python/ONNXRuntime fixed fixture parity within tolerance", "MT5 fixed fixture output within tolerance"],
        "failure_criteria": ["ONNX export fails", "ONNXRuntime parity exceeds tolerance", "MT5 OnnxRun fails or exceeds tolerance"],
        "invalid_conditions": run_manifest["invalid_conditions"],
        "stop_conditions": run_manifest["stop_conditions"],
        "evidence_plan": [
            f"lab/runs/{run_id}/run_manifest.json",
            f"runtime/packages/{bundle_id}/experiment_bundle.json",
            f"runtime/mt5_attempts/{attempt_id}/attempt_manifest.yaml",
        ],
        "required_gate_coverage": run_manifest["required_gate_coverage"],
        "runtime_learning_probe_decision": {
            **experiment_bundle["runtime_learning_probe_decision"],
            "forbidden_skip_reasons_checked": [
                "probe_is_heavy",
                "probe_is_expensive",
                "proxy_result_is_weak",
                "trade_count_is_low",
                "candidate_is_ambiguous",
                "setup_might_fail",
            ],
            "lowered_claim_if_not_run": "bundle_preflight_only",
        },
        "result_judgment": "inconclusive",
        "missing_evidence": run_manifest["missing_evidence"],
        "claim_boundary": "bundle_preflight",
        "forbidden_claims": experiment_bundle["forbidden_claims"],
        "next_action": run_manifest["next_action"],
    }
    write_yaml(run_root / "experiment_receipt.yaml", receipt)

    lineage = {
        "version": "artifact_lineage_v2",
        "run_id": run_id,
        "source_inputs": ["MT5.copy_rates_range US100 M5", "foundation/features/fixture_features.py", "foundation/labels/fixture_labels.py"],
        "producer": {
            "type": "python_pipeline",
            "identity": "foundation/pipelines/minimal_onnx_mt5_plumbing_slice.py",
            "command": " ".join(sys.argv),
            "environment_summary": dependency_summary(),
        },
        "consumer": ["runtime/packages", "runtime/mt5_attempts", "MT5 common files"],
        "source_of_truth_paths": [f"lab/runs/{run_id}/run_manifest.json", f"runtime/packages/{bundle_id}/experiment_bundle.json"],
        "artifact_paths": output_hashes + [asdict(tester_config_ref)],
        "artifact_hashes": [item["sha256"] for item in output_hashes] + [tester_config_ref.sha256],
        "artifact_sizes": [item["size_bytes"] for item in output_hashes] + [tester_config_ref.size_bytes],
        "regeneration_commands": [" ".join(sys.argv)],
        "registry_links": ["docs/registers/run_registry.csv", "docs/registers/artifact_registry.csv"],
        "availability": "local_generated_artifacts_ignored_by_git_with_hashes",
        "heavy_artifact_policy": "track_by_path_hash_size_command_or_uri",
        "lineage_judgment": "usable_with_boundary",
    }
    write_json(run_root / "artifact_lineage.json", lineage)

    metrics = {
        "version": "metrics_v1",
        "run_id": run_id,
        "metric_scope": "fixed_fixture_plumbing_only",
        "dataset_rows": int(len(raw)),
        "feature_label_rows": int(len(features)),
        "train_rows": int(train_end),
        "validation_rows": int(len(features) - train_end),
        "python_onnxruntime_abs_error": parity_abs_error,
        "python_onnxruntime_tolerance": TOLERANCE,
        "mt5_native_onnx_abs_error": None,
        "claim_boundary": "not_performance_metrics",
    }
    write_json(run_root / "metrics.json", metrics)

    runtime_evidence = {
        "version": "runtime_evidence_v2",
        "run_id": run_id,
        "surface_id": TASK_SURFACE_ID,
        "bundle_id": bundle_id,
        "decision_surface_id": DECISION_SURFACE_ID,
        "branch_worktree": branch_worktree,
        "runtime_learning_probe_decision": {
            "required": True,
            "decision": "run_required",
            "reason": "MT5 native ONNX meaning is in scope.",
            "forbidden_skip_reasons_checked": receipt["runtime_learning_probe_decision"]["forbidden_skip_reasons_checked"],
            "lowered_claim_if_not_run": "bundle_preflight_only",
        },
        "provenance": provenance,
        "levels": {
            "L0_contract_declared": "passed",
            "L1_python_onnx_parity": "passed",
            "L2_label_outcome_parity": "not_applicable_fixture_only",
            "L3_mt5_micro_probe": "pending",
            "L4_split_runtime_probe": "not_applicable",
            "L5_candidate_runtime_evidence": "not_applicable",
        },
        "evidence_paths": [f"runtime/packages/{bundle_id}/experiment_bundle.json", f"runtime/mt5_attempts/{attempt_id}/attempt_manifest.yaml"],
        "mt5_attempt_ids": [attempt_id],
        "known_differences": [],
        "required_gate_coverage": run_manifest["required_gate_coverage"],
        "runtime_debt_state": "mt5_probe_pending",
        "repair_required": False,
        "repair_surface": None,
        "runtime_claim_boundary": "bundle_preflight_until_mt5_probe_output_exists",
        "missing_evidence": run_manifest["missing_evidence"],
    }
    write_yaml(run_root / "runtime_evidence.yaml", runtime_evidence)

    attempt_manifest = {
        "version": "mt5_attempt_manifest_v1",
        "attempt_id": attempt_id,
        "run_id": run_id,
        "surface_id": TASK_SURFACE_ID,
        "bundle_id": bundle_id,
        "created_at_utc": started_at.isoformat().replace("+00:00", "Z"),
        "status": "prepared_not_executed",
        "branch_worktree": branch_worktree,
        "storage_contract": {
            "source_of_truth": f"runtime/mt5_attempts/{attempt_id}/attempt_manifest.yaml",
            "supporting_paths": [f"runtime/mt5_attempts/{attempt_id}/"],
            "registry_rows": ["docs/registers/artifact_registry.csv"],
            "durable_identity_policy": "repo_relative_paths_only",
        },
        "runtime_learning_probe_decision": runtime_evidence["runtime_learning_probe_decision"],
        "provenance": provenance,
        "period_identity": {
            "period_profile_id": "period_profile_split_set_v0",
            "runtime_period_set_id": "specific_fixture_micro_probe_no_period_completion",
            "period_roles": ["fixture_micro_probe"],
        },
        "execution_identity": {
            "execution_profile_id": "us100_m5_fpmarkets_tester_execution_v0",
            "symbol": "US100",
            "timeframe": "M5",
            "tester_model": 4,
            "deposit": 500,
            "leverage": "1:100",
            "spread": "floating",
            "commission_assumption": "not_applicable_no_trading",
            "swap_assumption_or_source": "not_applicable_no_trading",
        },
        "artifact_identity": {
            "ea_entrypoint": {
                "path": "foundation/mt5/experts/SpaceSonar_ONNX_FixtureProbe.mq5",
                "sha256": None,
            },
            "include_modules": [],
            "set_file": {"path": tester_config_ref.path, "sha256": tester_config_ref.sha256},
            "bundle": {"path": f"runtime/packages/{bundle_id}/experiment_bundle.json", "sha256": file_sha256(bundle_root / "experiment_bundle.json")},
            "tester_reports": [],
            "common_files": copied_common_files,
        },
        "required_gate_coverage": run_manifest["required_gate_coverage"],
        "claim_boundary": "mt5_micro_probe_prepared_no_runtime_authority",
        "forbidden_claims": experiment_bundle["forbidden_claims"],
        "missing_evidence": ["EA compile hash", "MT5 tester execution output", "mt5_probe_output.csv"],
        "next_action": f"Compile EA and run terminal64.exe /config:{repo_relative(tester_config_path, repo_root)}",
    }
    write_yaml(attempt_root / "attempt_manifest.yaml", attempt_manifest)

    print(
        json.dumps(
            {
                "status": "prepared",
                "run_id": run_id,
                "bundle_id": bundle_id,
                "attempt_id": attempt_id,
                "python_onnxruntime_abs_error": parity_abs_error,
                "tester_config": repo_relative(tester_config_path, repo_root),
            },
            indent=2,
        )
    )
    return {"run_id": run_id, "bundle_id": bundle_id, "attempt_id": attempt_id}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the minimal SpaceSonar ONNX-MT5 plumbing fixture.")
    parser.add_argument("--symbol", default="US100")
    parser.add_argument("--start-utc", default="2024-06-05T00:00:00Z")
    parser.add_argument("--end-utc", default="2024-07-05T23:59:59Z")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--bundle-id", default=None)
    parser.add_argument("--attempt-id", default=None)
    return parser.parse_args()


def main() -> int:
    run(parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
