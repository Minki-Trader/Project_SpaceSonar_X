from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import importlib.util
import json
import platform
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN_ID = "campaign_us100_task_surface_scout_v0"
SWEEP_ID = "sweep_wave0_broad_surface_scout_v0"
GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WORK_ITEM_ID = "work_wave0_first_batch_l4_follow_through_v0"
PREFLIGHT_ID = "l4_materialization_preflight_wave0_first_batch_v0"
PREFLIGHT_WORK_ITEM_ID = "work_wave0_l4_materialization_preflight_v0"
CLAIM_BOUNDARY = "l4_materialization_preflight_only_no_runtime_authority_no_candidate_no_baseline"

RUN_REFS = Path(
    "lab/campaigns/campaign_us100_task_surface_scout_v0/"
    "sweeps/sweep_wave0_broad_surface_scout_v0/run_refs.csv"
)
AXIS_REVIEW = Path(
    "lab/campaigns/campaign_us100_task_surface_scout_v0/"
    "sweeps/sweep_wave0_broad_surface_scout_v0/axis_review_wave0_first_batch_v0.yaml"
)
OUTPUT_DIR = Path("lab/campaigns/campaign_us100_task_surface_scout_v0/l4_follow_through")
PREFLIGHT_YAML = OUTPUT_DIR / "l4_materialization_preflight.yaml"
PREFLIGHT_CSV = OUTPUT_DIR / "l4_materialization_preflight.csv"
CLOSEOUT_PATH = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/work_wave0_l4_materialization_preflight_v0_closeout.yaml")
NEXT_WORK_ITEM = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml")
RESUME_CURSOR = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml")
GOAL_MANIFEST = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml")
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")

RUNTIME_PERIOD_PROFILE = "period_profile_split_set_v0"
RUNTIME_PERIOD_SET = "split_base_anchor_v0_research_l4"
EXECUTION_PROFILE = "us100_m5_fpmarkets_tester_execution_v0"

STRATEGY_TESTER_ADAPTER_CANDIDATES = [
    Path("foundation/mt5/experts/SpaceSonar_ONNX_StrategyProbe.mq5"),
    Path("foundation/mt5/experts/SpaceSonar_ONNX_DecisionProbe.mq5"),
]
FIXED_FIXTURE_EA = Path("foundation/mt5/experts/SpaceSonar_ONNX_FixtureProbe.mq5")
SERIALIZED_MODEL_SUFFIXES = {".joblib", ".pkl", ".pickle", ".onnx"}


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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_ref(path: Path, repo_root: Path) -> dict[str, Any]:
    full = repo_root / path
    return {
        "path": path.as_posix(),
        "sha256": sha256(full),
        "size_bytes": full.stat().st_size,
        "availability": "present_hash_recorded",
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
        "unknown_git_claim_effect": "planning_or_preflight_only_no_reproducible_bundle_runtime_handoff_pass_readiness_or_goal_achieve"
        if changed
        else "clean_git_identity_recorded_for_preflight_only",
    }


def dependency_summary() -> dict[str, dict[str, str]]:
    package_names = {
        "numpy": "numpy",
        "pandas": "pandas",
        "sklearn": "scikit-learn",
        "onnx": "onnx",
        "onnxruntime": "onnxruntime",
        "skl2onnx": "skl2onnx",
        "yaml": "PyYAML",
    }
    summary: dict[str, dict[str, str]] = {
        "python": {"status": "available", "version": platform.python_version()}
    }
    for import_name, dist_name in package_names.items():
        available = importlib.util.find_spec(import_name) is not None
        version = "not_installed"
        if available:
            try:
                version = importlib.metadata.version(dist_name)
            except importlib.metadata.PackageNotFoundError:
                version = "unknown"
        summary[import_name] = {"status": "available" if available else "missing", "version": version}
    return summary


def model_export_assessment(model_family: str, dependencies: dict[str, dict[str, str]]) -> dict[str, Any]:
    skl2onnx_ready = dependencies.get("skl2onnx", {}).get("status") == "available"
    onnxruntime_ready = dependencies.get("onnxruntime", {}).get("status") == "available"
    if model_family in {"logistic_classification_scout", "linear_or_ridge_rank_scout"}:
        return {
            "export_adapter_status": "skl2onnx_converter_likely_available"
            if skl2onnx_ready
            else "missing_skl2onnx_requires_dependency_repair_attempt",
            "python_onnx_parity_possible": bool(skl2onnx_ready and onnxruntime_ready),
            "runtime_readiness_claim": "not_materialization_ready_until_retrained_exported_and_parity_checked",
        }
    if model_family == "onnx_realistic_tree_or_boosted_scout":
        return {
            "export_adapter_status": "requires_export_adapter_probe",
            "python_onnx_parity_possible": bool(skl2onnx_ready and onnxruntime_ready),
            "runtime_readiness_claim": "not_materialization_ready_tree_boosted_adapter_unproven_for_MT5_native_ONNX",
        }
    return {
        "export_adapter_status": "unknown_model_family_requires_manual_adapter_decision",
        "python_onnx_parity_possible": False,
        "runtime_readiness_claim": "not_materialization_ready_unknown_model_family",
    }


def serialized_model_artifacts(run_root: Path, repo_root: Path) -> list[str]:
    artifact_root = run_root / "artifacts"
    if not artifact_root.exists():
        return []
    found: list[str] = []
    for path in sorted(artifact_root.iterdir()):
        if path.suffix.lower() in SERIALIZED_MODEL_SUFFIXES and path.name != "model_summary.json":
            found.append(rel(path, repo_root))
    return found


def build_run_preflight(
    repo_root: Path,
    run_ref: dict[str, str],
    axis_by_run_id: dict[str, dict[str, Any]],
    dependencies: dict[str, dict[str, str]],
) -> dict[str, Any]:
    run_id = run_ref["run_id"]
    manifest_path = repo_root / run_ref["run_manifest_path"]
    manifest = load_json(manifest_path)
    run_root = manifest_path.parent
    feature_schema_path = repo_root / manifest["model_export"]["input_schema"]["feature_schema_path"]
    label_schema_path = run_root / "artifacts" / "label_schema.json"
    model_summary_path = run_root / "artifacts" / "model_summary.json"

    axis_record = axis_by_run_id.get(run_id, {})
    model_family = str((manifest.get("planned_cell") or {}).get("model_family") or axis_record.get("model_family") or "")
    decision_family = str((manifest.get("planned_cell") or {}).get("decision_family") or axis_record.get("decision_family") or "")
    task_kind = str(axis_record.get("task_kind") or "")
    export_assessment = model_export_assessment(model_family, dependencies)

    fitted_artifacts = serialized_model_artifacts(run_root, repo_root)
    onnx_artifact = bool((manifest.get("model_export") or {}).get("onnx_sha256")) or any(
        item.endswith(".onnx") for item in fitted_artifacts
    )
    strategy_adapter_exists = any((repo_root / candidate).exists() for candidate in STRATEGY_TESTER_ADAPTER_CANDIDATES)
    feature_schema = load_json(feature_schema_path) if feature_schema_path.exists() else {}
    label_schema = load_json(label_schema_path) if label_schema_path.exists() else {}

    blockers: list[str] = []
    if not fitted_artifacts:
        blockers.append("requires_retrain_for_materialization")
    if not onnx_artifact:
        blockers.append("requires_onnx_export_after_retrain")
    if export_assessment["export_adapter_status"] != "skl2onnx_converter_likely_available":
        blockers.append(export_assessment["export_adapter_status"])
    if not strategy_adapter_exists:
        blockers.append("requires_strategy_tester_ea_or_runtime_adapter")
    if decision_family == "diagnostic_rank_only":
        blockers.append("requires_declared_runtime_observation_mode_for_diagnostic_surface")

    direct_l4_ready = not blockers
    return {
        "run_id": run_id,
        "status": run_ref.get("status"),
        "result_judgment": run_ref.get("result_judgment"),
        "run_manifest_path": run_ref["run_manifest_path"],
        "target_family": axis_record.get("target_family"),
        "horizon_bars": str(axis_record.get("horizon_bars", "")),
        "input_family": axis_record.get("input_family"),
        "decision_family": decision_family,
        "model_family": model_family,
        "task_kind": task_kind,
        "feature_count": int(feature_schema.get("used_feature_count") or axis_record.get("feature_count") or 0),
        "feature_order_hash": feature_schema.get("feature_order_hash"),
        "label_schema_hash": label_schema.get("label_schema_hash"),
        "target_name_used_for_model": label_schema.get("target_name_used_for_model"),
        "fitted_model_artifacts": fitted_artifacts,
        "onnx_artifact_present": onnx_artifact,
        "export_adapter_status": export_assessment["export_adapter_status"],
        "python_onnx_parity_possible": export_assessment["python_onnx_parity_possible"],
        "strategy_tester_adapter_present": strategy_adapter_exists,
        "fixed_fixture_ea_present_not_sufficient_for_l4": (repo_root / FIXED_FIXTURE_EA).exists(),
        "direct_l4_ready": direct_l4_ready,
        "materialization_blockers": blockers,
        "required_next_action": "execute_L4_split_runtime_probe"
        if direct_l4_ready
        else "retrain_export_and_build_or_select_strategy_tester_adapter_before_L4",
        "claim_boundary": CLAIM_BOUNDARY,
    }


def axis_records_by_run_id(axis_review: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row["run_id"]): row for row in axis_review.get("run_review", [])}


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    blockers = Counter(blocker for row in rows for blocker in row["materialization_blockers"])
    families = Counter(str(row["model_family"]) for row in rows)
    export_statuses = Counter(str(row["export_adapter_status"]) for row in rows)
    judgments = Counter(str(row["result_judgment"]) for row in rows)
    return {
        "valid_proxy_runs_requiring_l4": len(rows),
        "direct_l4_ready_runs": sum(1 for row in rows if row["direct_l4_ready"]),
        "runs_requiring_retrain": blockers["requires_retrain_for_materialization"],
        "runs_requiring_onnx_export": blockers["requires_onnx_export_after_retrain"],
        "runs_requiring_strategy_tester_adapter": blockers["requires_strategy_tester_ea_or_runtime_adapter"],
        "diagnostic_surfaces_requiring_runtime_observation_mode": blockers[
            "requires_declared_runtime_observation_mode_for_diagnostic_surface"
        ],
        "model_family_counts": dict(sorted(families.items())),
        "export_adapter_status_counts": dict(sorted(export_statuses.items())),
        "result_judgment_counts": dict(sorted(judgments.items())),
        "blocker_counts": dict(sorted(blockers.items())),
    }


def build_preflight(repo_root: Path, *, started_at_utc: str, command_argv: list[str]) -> dict[str, Any]:
    dependencies = dependency_summary()
    run_refs = read_csv_rows(repo_root / RUN_REFS)
    axis_review = load_yaml(repo_root / AXIS_REVIEW)
    rows = [
        build_run_preflight(repo_root, row, axis_records_by_run_id(axis_review), dependencies)
        for row in run_refs
        if row.get("status") == "executed_proxy_scout"
    ]
    summary = summarize(rows)
    git = git_identity(repo_root)
    ended_at_utc = utc_now()
    return {
        "version": "l4_materialization_preflight_v1",
        "preflight_id": PREFLIGHT_ID,
        "work_item_id": WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": ended_at_utc,
        "status": "completed_direct_l4_ready_0_materialization_required"
        if summary["direct_l4_ready_runs"] == 0
        else "completed_some_runs_direct_l4_ready",
        "claim_boundary": CLAIM_BOUNDARY,
        "source_inputs": {
            "run_refs": RUN_REFS.as_posix(),
            "axis_review": AXIS_REVIEW.as_posix(),
            "runtime_contract": "foundation/config/mt5_runtime_probe_contract.yaml",
            "runtime_period_profile": "configs/mt5/period_profiles/split_set_v0_runtime_periods.yaml",
            "tester_execution_profile": "configs/mt5/tester_execution_profile_v0.yaml",
        },
        "input_hashes": [
            artifact_ref(RUN_REFS, repo_root),
            artifact_ref(AXIS_REVIEW, repo_root),
        ],
        "runtime_contract_binding": {
            "required_runtime_level": "L4_split_runtime_probe",
            "period_profile_id": RUNTIME_PERIOD_PROFILE,
            "runtime_period_set_id": RUNTIME_PERIOD_SET,
            "required_period_roles": ["validation", "research_oos"],
            "tester_execution_profile_id": EXECUTION_PROFILE,
            "locked_final_oos_b": "forbidden_by_default",
            "l5_rule": "if_L4_remains_promising_continue_to_L5_candidate_runtime_evidence",
        },
        "adapter_inventory": {
            "strategy_tester_adapter_candidates": [
                {"path": path.as_posix(), "present": (repo_root / path).exists()}
                for path in STRATEGY_TESTER_ADAPTER_CANDIDATES
            ],
            "fixed_fixture_ea": {
                "path": FIXED_FIXTURE_EA.as_posix(),
                "present": (repo_root / FIXED_FIXTURE_EA).exists(),
                "claim_effect": "proves_native_ONNX_fixed_fixture_only_not_full_L4_strategy_tester_surface",
            },
        },
        "environment": {
            "command": " ".join(command_argv),
            "command_argv": command_argv,
            "cwd": ".",
            "python_executable": redact_home(sys.executable),
            "python_version": platform.python_version(),
            "dependency_summary": dependencies,
            "started_at_utc": started_at_utc,
            "ended_at_utc": ended_at_utc,
            **git,
        },
        "summary": summary,
        "run_preflight": rows,
        "judgment": {
            "judgment_class": "preflight_completed_l4_execution_pending",
            "materialization_ready": False,
            "runtime_authority": False,
            "economics_pass": False,
            "selected_baseline": False,
            "goal_achieve": False,
            "next_action": (
                "retrain/export model-bearing runs into bundles, add a full-period Strategy Tester "
                "decision adapter, then execute L4 validation and research_oos probes."
            ),
        },
        "prevention_memory": [
            "Do not call a proxy scout L4-ready unless fitted model, ONNX export/parity, bundle, and MT5 Strategy Tester adapter exist.",
            "Fixed-fixture native ONNX parity is useful plumbing evidence but not a substitute for split-period L4 Strategy Tester evidence.",
            "Diagnostic score surfaces need an explicit runtime observation or decision translation before MT5 follow-through.",
        ],
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


def csv_rows(preflight: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in preflight["run_preflight"]:
        rows.append(
            {
                "run_id": row["run_id"],
                "result_judgment": row["result_judgment"],
                "target_family": row["target_family"],
                "horizon_bars": row["horizon_bars"],
                "input_family": row["input_family"],
                "decision_family": row["decision_family"],
                "model_family": row["model_family"],
                "task_kind": row["task_kind"],
                "feature_count": row["feature_count"],
                "export_adapter_status": row["export_adapter_status"],
                "direct_l4_ready": str(row["direct_l4_ready"]).lower(),
                "materialization_blockers": "|".join(row["materialization_blockers"]),
                "required_next_action": row["required_next_action"],
                "claim_boundary": row["claim_boundary"],
            }
        )
    return rows


def build_closeout(preflight: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    return {
        "version": "work_closeout_v1",
        "work_item_id": PREFLIGHT_WORK_ITEM_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "created_at_utc": preflight["created_at_utc"],
        "status": "completed_preflight_l4_execution_pending",
        "result_judgment": "inconclusive",
        "claim_boundary": CLAIM_BOUNDARY,
        "source_of_truth": PREFLIGHT_YAML.as_posix(),
        "evidence_paths": [
            PREFLIGHT_YAML.as_posix(),
            PREFLIGHT_CSV.as_posix(),
        ],
        "summary": preflight["summary"],
        "claim_effect": {
            "materialization_ready": False,
            "runtime_authority": False,
            "economics_pass": False,
            "selected_baseline": False,
            "goal_achieve": False,
        },
        "next_work_item": {
            "work_item_id": WORK_ITEM_ID,
            "path": NEXT_WORK_ITEM.as_posix(),
            "required_next_action": preflight["judgment"]["next_action"],
        },
        "output_hashes": [
            artifact_ref(PREFLIGHT_YAML, repo_root),
            artifact_ref(PREFLIGHT_CSV, repo_root),
        ],
        "forbidden_claims": preflight["forbidden_claims"],
    }


def ensure_list_item(values: list[Any], item: Any) -> None:
    if item not in values:
        values.append(item)


def update_control_records(preflight: dict[str, Any], closeout: dict[str, Any], repo_root: Path) -> None:
    summary = preflight["summary"]

    next_work = load_yaml(repo_root / NEXT_WORK_ITEM)
    current_truth = next_work.setdefault("current_truth", {})
    current_truth["materialization_preflight"] = PREFLIGHT_YAML.as_posix()
    current_truth["materialization_preflight_status"] = preflight["status"]
    current_truth["materialization_preflight_summary"] = summary
    next_work["status"] = "planned_next_l4_materialization_after_preflight"
    next_work["missing_material_if_relevant"] = [
        "fitted_model_artifacts_absent_for_current_proxy_runs",
        "onnx_exports_absent_for_current_proxy_runs",
        "full_period_strategy_tester_adapter_absent_for_current_proxy_runs",
    ]
    next_work["next_action"] = preflight["judgment"]["next_action"]
    write_yaml(repo_root / NEXT_WORK_ITEM, next_work)

    resume = load_yaml(repo_root / RESUME_CURSOR)
    resume["updated_at_utc"] = preflight["created_at_utc"]
    truth_sources = resume.setdefault("current_truth_sources", [])
    ensure_list_item(truth_sources, PREFLIGHT_YAML.as_posix())
    ensure_list_item(truth_sources, PREFLIGHT_CSV.as_posix())
    resume["latest_completed_work"] = {
        "work_item_id": PREFLIGHT_WORK_ITEM_ID,
        "result_judgment": "inconclusive",
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_paths": [PREFLIGHT_YAML.as_posix(), CLOSEOUT_PATH.as_posix()],
    }
    resume["next_work_item"] = {"work_item_id": WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()}
    write_yaml(repo_root / RESUME_CURSOR, resume)

    goal = load_yaml(repo_root / GOAL_MANIFEST)
    goal["updated_at_utc"] = preflight["created_at_utc"]
    wave_spec = goal.setdefault("program_budgets", {}).setdefault("current_wave0_spec", {})
    wave_spec["l4_materialization_preflight"] = PREFLIGHT_YAML.as_posix()
    wave_spec["l4_materialization_preflight_status"] = preflight["status"]
    wave_spec["l4_materialization_preflight_summary"] = summary
    write_yaml(repo_root / GOAL_MANIFEST, goal)

    workspace = load_yaml(repo_root / WORKSPACE_STATE)
    workspace["updated_utc"] = preflight["created_at_utc"]
    claims = workspace.setdefault("current_claims", {})
    claims["wave0_l4_materialization_preflight"] = PREFLIGHT_YAML.as_posix()
    claims["wave0_l4_materialization_preflight_status"] = preflight["status"]
    claims["wave0_l4_materialization_preflight_summary"] = summary
    write_yaml(repo_root / WORKSPACE_STATE, workspace)

    upsert_artifact_registry(
        repo_root,
        [
            {
                "artifact_id": "artifact_wave0_l4_materialization_preflight_yaml_v0",
                "run_id": "",
                "bundle_id": "",
                "attempt_id": "",
                "artifact_type": "l4_materialization_preflight",
                "path_or_uri": PREFLIGHT_YAML.as_posix(),
                "availability": "present_hash_recorded",
                "producer_command": "foundation/pipelines/preflight_wave0_l4_materialization.py --write-control-records",
                "regeneration_command": "python foundation/pipelines/preflight_wave0_l4_materialization.py --write-control-records",
                "source_of_truth": PREFLIGHT_YAML.as_posix(),
                "consumer": WORK_ITEM_ID,
                "claim_boundary": CLAIM_BOUNDARY,
                "notes": "preflight only; L4 execution still pending",
            },
            {
                "artifact_id": "artifact_wave0_l4_materialization_preflight_csv_v0",
                "run_id": "",
                "bundle_id": "",
                "attempt_id": "",
                "artifact_type": "l4_materialization_preflight_csv",
                "path_or_uri": PREFLIGHT_CSV.as_posix(),
                "availability": "present_hash_recorded",
                "producer_command": "foundation/pipelines/preflight_wave0_l4_materialization.py --write-control-records",
                "regeneration_command": "python foundation/pipelines/preflight_wave0_l4_materialization.py --write-control-records",
                "source_of_truth": PREFLIGHT_YAML.as_posix(),
                "consumer": WORK_ITEM_ID,
                "claim_boundary": CLAIM_BOUNDARY,
                "notes": "run-level materialization blockers for first proxy batch",
            },
            {
                "artifact_id": "artifact_wave0_l4_materialization_preflight_closeout_v0",
                "run_id": "",
                "bundle_id": "",
                "attempt_id": "",
                "artifact_type": "work_closeout",
                "path_or_uri": CLOSEOUT_PATH.as_posix(),
                "availability": "present_hash_recorded",
                "producer_command": "foundation/pipelines/preflight_wave0_l4_materialization.py --write-control-records",
                "regeneration_command": "python foundation/pipelines/preflight_wave0_l4_materialization.py --write-control-records",
                "source_of_truth": CLOSEOUT_PATH.as_posix(),
                "consumer": WORK_ITEM_ID,
                "claim_boundary": CLAIM_BOUNDARY,
                "notes": "preflight closeout; parent L4 follow-through remains open",
            },
        ],
    )


def upsert_artifact_registry(repo_root: Path, new_rows: list[dict[str, str]]) -> None:
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
    for row in new_rows:
        path = repo_root / row["path_or_uri"]
        row["sha256"] = sha256(path)
        row["size_bytes"] = str(path.stat().st_size)
        by_id[row["artifact_id"]] = {key: row.get(key, "") for key in fieldnames}
    write_csv(registry_path, list(by_id.values()), fieldnames)


def write_outputs(preflight: dict[str, Any], repo_root: Path, *, write_control_records: bool) -> None:
    write_yaml(repo_root / PREFLIGHT_YAML, preflight)
    write_csv(
        repo_root / PREFLIGHT_CSV,
        csv_rows(preflight),
        [
            "run_id",
            "result_judgment",
            "target_family",
            "horizon_bars",
            "input_family",
            "decision_family",
            "model_family",
            "task_kind",
            "feature_count",
            "export_adapter_status",
            "direct_l4_ready",
            "materialization_blockers",
            "required_next_action",
            "claim_boundary",
        ],
    )
    closeout = build_closeout(preflight, repo_root)
    write_yaml(repo_root / CLOSEOUT_PATH, closeout)
    if write_control_records:
        update_control_records(preflight, closeout, repo_root)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--write-control-records", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    started_at = utc_now()
    command_argv = ["python", "foundation/pipelines/preflight_wave0_l4_materialization.py"]
    if args.write_control_records:
        command_argv.append("--write-control-records")
    preflight = build_preflight(repo_root, started_at_utc=started_at, command_argv=command_argv)
    write_outputs(preflight, repo_root, write_control_records=args.write_control_records)
    print(
        json.dumps(
            {
                "status": preflight["status"],
                "preflight": PREFLIGHT_YAML.as_posix(),
                "direct_l4_ready_runs": preflight["summary"]["direct_l4_ready_runs"],
                "valid_proxy_runs_requiring_l4": preflight["summary"]["valid_proxy_runs_requiring_l4"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
