from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]

GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WORK_ITEM_ID = "work_wave0_first_batch_l4_follow_through_v0"
SUBWORK_ID = "work_wave0_l4_mt5_attempt_preparation_v0"
CAMPAIGN_ID = "campaign_us100_task_surface_scout_v0"
SWEEP_ID = "sweep_wave0_broad_surface_scout_v0"
CLAIM_BOUNDARY = "l4_strategy_tester_attempt_preparation_only_no_runtime_authority_no_economics_pass_no_candidate"
NEXT_PHASE = "wave01_operating_proof_window_l4_terminal_execution_next"

MATERIALIZATION_SUMMARY = Path(
    "lab/campaigns/campaign_us100_task_surface_scout_v0/l4_follow_through/onnx_materialization_summary.yaml"
)
MATERIALIZATION_INDEX = Path(
    "lab/campaigns/campaign_us100_task_surface_scout_v0/l4_follow_through/onnx_materialization_index.csv"
)
OUTPUT_DIR = Path("lab/campaigns/campaign_us100_task_surface_scout_v0/l4_follow_through")
SUMMARY_PATH = OUTPUT_DIR / "l4_attempt_preparation_summary.yaml"
INDEX_PATH = OUTPUT_DIR / "l4_attempt_preparation_index.csv"
CLOSEOUT_PATH = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/work_wave0_l4_mt5_attempt_preparation_v0_closeout.yaml")
NEXT_WORK_ITEM = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml")
RESUME_CURSOR = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml")
GOAL_MANIFEST = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml")
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")
GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")

RUNTIME_CONTRACT = Path("foundation/config/mt5_runtime_probe_contract.yaml")
PERIOD_PROFILE = Path("configs/mt5/period_profiles/split_set_v0_runtime_periods.yaml")
EXECUTION_PROFILE = Path("configs/mt5/tester_execution_profile_v0.yaml")
EA_SOURCE = Path("foundation/mt5/experts/SpaceSonar_ONNX_L4_ScoreProbe.mq5")
EA_BINARY = Path("foundation/mt5/experts/SpaceSonar_ONNX_L4_ScoreProbe.ex5")
EA_EXPERT_CONFIG_PATH = "Project_SpaceSonar_X\\foundation\\mt5\\experts\\SpaceSonar_ONNX_L4_ScoreProbe.ex5"
COMMON_REL_ROOT = "SpaceSonar\\l4_score_probe"


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel(path: Path, repo_root: Path) -> str:
    if not path.is_absolute():
        return path.as_posix()
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def artifact_ref(path: Path, repo_root: Path, *, availability: str = "present_hash_recorded") -> dict[str, Any]:
    relative = Path(rel(path, repo_root))
    full = repo_root / relative
    return {
        "path": relative.as_posix(),
        "sha256": sha256(full),
        "size_bytes": full.stat().st_size,
        "availability": availability,
    }


def redact_path(value: str) -> str:
    text = str(value)
    home = str(Path.home())
    appdata = os.environ.get("APPDATA")
    program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
    if appdata and text.startswith(appdata):
        return "${APPDATA}" + text[len(appdata) :]
    if text.startswith(home):
        return "${USERPROFILE}" + text[len(home) :]
    if text.startswith(program_files):
        return "${PROGRAMFILES}" + text[len(program_files) :]
    return text


def common_files_root() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "MetaQuotes" / "Terminal" / "Common" / "Files"


def mt5_common_redacted(common_relative_path: str) -> str:
    return "${MT5_COMMONDATA}\\Files\\" + common_relative_path


def run_git(repo_root: Path, args: list[str]) -> str:
    result = subprocess.run(["git", *args], cwd=repo_root, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip()


def git_identity(repo_root: Path) -> dict[str, Any]:
    changed = [line for line in run_git(repo_root, ["status", "--short"]).splitlines() if line]
    return {
        "git_sha": run_git(repo_root, ["rev-parse", "HEAD"]),
        "branch": run_git(repo_root, ["branch", "--show-current"]),
        "dirty_flag": bool(changed),
        "changed_files": changed,
        "unknown_git_claim_effect": (
            "attempt_preparation_only_lower_reproducibility_claim"
            if changed
            else "clean_git_identity_recorded_for_attempt_preparation"
        ),
    }


def dependency_summary() -> dict[str, str]:
    packages: dict[str, str] = {
        "python": platform.python_version(),
        "yaml": yaml.__version__,
        "platform": platform.platform(),
    }
    return packages


def feature_order_hash(columns: list[str]) -> str:
    return hashlib.sha256("|".join(columns).encode("utf-8")).hexdigest()


def max_feature_window(columns: list[str]) -> int:
    max_window = 12
    for column in columns:
        suffix = column.rsplit("_", 1)[-1]
        if suffix.isdigit():
            max_window = max(max_window, int(suffix))
    return max(720, max_window + 24)


def required_l4_periods(period_profile: dict[str, Any], runtime_period_set_id: str) -> list[dict[str, str]]:
    for period_set in period_profile.get("runtime_period_sets", []):
        if period_set.get("runtime_period_set_id") == runtime_period_set_id:
            periods = period_set.get("periods") or {}
            required_roles = period_set.get("required_roles") or list(periods)
            return [
                {
                    "period_role": role,
                    "from_date": str(periods[role]["from_date"]),
                    "to_date": str(periods[role]["to_date"]),
                    "split_role": str(periods[role].get("split_role", role)),
                }
                for role in required_roles
            ]
    raise KeyError(f"runtime_period_set_id not found: {runtime_period_set_id}")


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
    feature_columns = bundle["feature_schema_contract"]["feature_columns"]
    low, high, has_low_high = score_thresholds(bundle)
    onnx_common_path = f"{COMMON_REL_ROOT}\\{bundle['bundle_id']}\\model.onnx"
    feature_columns_common_path = f"{COMMON_REL_ROOT}\\{bundle['bundle_id']}\\feature_columns.txt"
    telemetry_common_path = f"{COMMON_REL_ROOT}\\{attempt_id}\\score_telemetry.csv"
    report_name = f"Project_SpaceSonar_X\\runtime\\mt5_attempts\\{attempt_id}\\tester_report"
    lines = [
        "; SpaceSonar L4 full-period ONNX score probe.",
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
        f"InpFeatureColumns={';'.join(feature_columns)}",
        f"InpFeatureColumnsPath={feature_columns_common_path}",
        f"InpFeatureCount={len(feature_columns)}",
        f"InpInputFamily={bundle['feature_schema_contract']['input_family']}",
        f"InpDecisionFamily={bundle['decision_surface']['decision_family']}",
        f"InpScoreLow={low}",
        f"InpScoreHigh={high}",
        f"InpHasLowHigh={'true' if has_low_high else 'false'}",
        f"InpHistoryBars={max_feature_window(feature_columns)}",
        "InpMaxRows=0",
        "InpUseCommonFiles=true",
        f"InpFixedLot={sizing['default_lot']}",
        "",
    ]
    return "\n".join(lines)


def attempt_id_for(cell_id: str, period_role: str) -> str:
    return f"attempt_{cell_id}_l4_{period_role}_v0"


def attempt_manifest(
    *,
    repo_root: Path,
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
    feature_columns = bundle["feature_schema_contract"]["feature_columns"]
    low, high, has_low_high = score_thresholds(bundle)
    bundle_path = repo_root / bundle["source_of_truth"]
    onnx_path = repo_root / bundle["onnx_path"]
    ea_source = repo_root / EA_SOURCE
    ea_binary = repo_root / EA_BINARY
    report_path = f"runtime/mt5_attempts/{attempt_id}/tester_report.htm"
    telemetry_common = f"{COMMON_REL_ROOT}\\{attempt_id}\\score_telemetry.csv"
    return {
        "version": "mt5_attempt_manifest_v1",
        "attempt_id": attempt_id,
        "run_id": bundle["run_id"],
        "cell_id": (bundle.get("id_chain") or {}).get("cell_id") or bundle["bundle_id"].replace("bundle_", "").replace("_l4_onnx_export_v0", ""),
        "surface_id": bundle["task_surface_id"],
        "bundle_id": bundle["bundle_id"],
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": created_at_utc,
        "status": "prepared_pending_terminal_execution",
        "claim_boundary": CLAIM_BOUNDARY,
        "source_of_truth": f"runtime/mt5_attempts/{attempt_id}/attempt_manifest.yaml",
        "work_item_id": WORK_ITEM_ID,
        "subwork_item_id": SUBWORK_ID,
        "routing": {
            "primary_family": "runtime_probe",
            "primary_skill": "spacesonar-runtime-parity",
            "support_skills": [
                "spacesonar-artifact-lineage",
                "spacesonar-environment-reproducibility",
                "spacesonar-run-evidence-system",
                "spacesonar-result-judgment",
                "spacesonar-claim-discipline",
            ],
        },
        "runtime_learning_probe_decision": {
            "required": True,
            "decision": "run_required",
            "required_runtime_level": "L4_split_runtime_probe",
            "reason": "Every valid Wave01 first-batch proxy/model-bearing run requires L4 MT5 follow-through.",
            "forbidden_skip_reasons_checked": runtime_contract["runtime_learning_probe_decision"]["forbidden_standalone_skip_reasons"],
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
            "base_frame": bundle["data_source"]["base_frame"],
            "row_key": bundle["data_source"]["row_key"],
            "input_name": bundle["input_schema"]["input_name"],
            "input_dtype": bundle["input_schema"]["dtype"],
            "input_shape": [1, len(feature_columns)],
            "feature_count": len(feature_columns),
            "feature_order_hash": feature_order_hash(feature_columns),
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
            "known_differences": [
                "Python proxy row membership uses exported MT5 history; EA reconstructs features from Strategy Tester closed bars.",
                "Strategy Tester spread/tick availability can differ from exported proxy data.",
                "This score probe writes telemetry and does not place trades; economics report remains pending until a trading EA exists.",
            ],
            "interpretation_drift_risks": [
                "bar_close_timing",
                "CopyRates_history_window_availability",
                "spread_field_semantics",
                "score_threshold_translation",
                "non_trading_decision_observation_vs_trading_execution",
            ],
            "minimum_reconciliation_attempt": {
                "status": "prepared",
                "attempt": "single_score_output_ONNX_contract_plus_feature_order_hash_plus_EA_feature_reconstruction",
                "forced_equality_required": False,
            },
            "unit_semantics": {
                "features": "float32 closed-bar values in bundle feature order",
                "price_units": "MT5 price values from MqlRates",
                "spread": "MqlRates.spread raw points scaled only where feature contract says spread_scaled",
                "lot": "fixed_lot_profile_recorded_but_EA_non_trading",
                "point_tick_digits": "recorded in tester report when trading/runtime EA is introduced",
            },
            "comparison_class": "pending_L4_terminal_execution",
            "divergence_judgment": "pending_L4_terminal_execution",
            "prevention_memory": [
                "Use semicolon feature-column delimiter in tester config to avoid MT5 optimization pipe syntax ambiguity.",
                "Do not treat prepared tester configs as completed L4 evidence.",
                "If EA feature reconstruction diverges from Python proxy, preserve the difference as parity evidence before judging the proxy.",
            ],
            "follow_up_action": "run Strategy Tester for this attempt and compare telemetry scope before result judgment",
            "claim_boundary": "proxy_runtime_parity_tracking_only_no_runtime_authority",
        },
        "artifact_identity": {
            "ea_entrypoint": artifact_ref(ea_source, repo_root),
            "ea_binary": (
                artifact_ref(ea_binary, repo_root, availability="local_binary_hash_recorded_ignored_by_git")
                if ea_binary.exists()
                else {"path": EA_BINARY.as_posix(), "exists": False}
            ),
            "tester_config": {
                "path": rel(tester_config_path, repo_root),
                "status": "pending_write",
            },
            "bundle": artifact_ref(bundle_path, repo_root),
            "onnx_model": artifact_ref(onnx_path, repo_root, availability="local_artifact_hash_recorded"),
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
            },
        },
        "provenance": {
            "command_argv": command_argv,
            "cwd": ".",
            "python_executable": redact_path(sys.executable),
            "python_version": platform.python_version(),
            "key_package_versions": dependency_summary(),
            "started_at_utc": created_at_utc,
            "ended_at_utc": utc_now(),
            "input_hashes": [
                artifact_ref(repo_root / MATERIALIZATION_SUMMARY, repo_root),
                artifact_ref(repo_root / MATERIALIZATION_INDEX, repo_root),
                artifact_ref(repo_root / RUNTIME_CONTRACT, repo_root),
                artifact_ref(repo_root / PERIOD_PROFILE, repo_root),
                artifact_ref(repo_root / EXECUTION_PROFILE, repo_root),
                artifact_ref(bundle_path, repo_root),
            ],
            "output_hashes": [],
            **git_identity(repo_root),
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
                "ea_compile_smoke" if ea_binary.exists() else "ea_source_present",
                "final_claim_guard",
            ],
            "missing": [
                "Strategy_Tester_terminal_execution",
                "L4_period_role_completed_report",
                "score_telemetry_csv",
                "tester_report_hash",
                "result_judgment_from_L4",
            ],
            "not_applicable": [
                "locked_final_oos_b_access",
                "economics_pass",
                "runtime_authority",
            ],
        },
        "missing_evidence": [
            "Strategy_Tester_terminal_execution_not_run",
            "L4_validation_or_research_oos_report_pending",
            "score_telemetry_pending",
        ],
        "next_action": "execute this tester_config.ini with MT5 terminal, collect telemetry and tester report, then judge L4 result with proxy-runtime parity boundary",
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


def common_copy_record(repo_root: Path, bundle: dict[str, Any], *, copy_common_files: bool) -> dict[str, Any]:
    onnx_source = repo_root / bundle["onnx_path"]
    common_relative_path = f"{COMMON_REL_ROOT}\\{bundle['bundle_id']}\\model.onnx"
    feature_columns = bundle["feature_schema_contract"]["feature_columns"]
    feature_columns_text = ";".join(feature_columns)
    feature_columns_common_path = f"{COMMON_REL_ROOT}\\{bundle['bundle_id']}\\feature_columns.txt"
    record = {
        "model.onnx": {
            "common_relative_path": common_relative_path,
            "redacted_absolute_path": mt5_common_redacted(common_relative_path),
            "sha256": sha256(onnx_source),
            "size_bytes": onnx_source.stat().st_size,
            "durable_identity": "common_relative_path_plus_sha256",
            "path_boundary": "redacted_local_context_only",
            "copy_status": "not_copied_by_request",
        },
        "feature_columns.txt": {
            "common_relative_path": feature_columns_common_path,
            "redacted_absolute_path": mt5_common_redacted(feature_columns_common_path),
            "sha256": hashlib.sha256(feature_columns_text.encode("utf-8")).hexdigest(),
            "size_bytes": len(feature_columns_text.encode("utf-8")),
            "feature_count": len(feature_columns),
            "durable_identity": "common_relative_path_plus_sha256",
            "path_boundary": "redacted_local_context_only",
            "copy_status": "not_copied_by_request",
        }
    }
    if copy_common_files:
        root = common_files_root()
        if root is None:
            record["model.onnx"]["copy_status"] = "copy_skipped_APPDATA_unavailable"
            return record
        destination = root / common_relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(onnx_source, destination)
        record["model.onnx"]["copy_status"] = "copied_to_mt5_common_files"
        record["model.onnx"]["copied_sha256"] = sha256(destination)
        feature_destination = root / feature_columns_common_path
        feature_destination.parent.mkdir(parents=True, exist_ok=True)
        feature_destination.write_text(feature_columns_text, encoding="utf-8")
        record["feature_columns.txt"]["copy_status"] = "copied_to_mt5_common_files"
        record["feature_columns.txt"]["copied_sha256"] = sha256(feature_destination)
    return record


def build_attempt_rows_and_manifests(
    repo_root: Path,
    *,
    copy_common_files: bool,
    command_argv: list[str],
    created_at_utc: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, str]]:
    materialization = load_yaml(repo_root / MATERIALIZATION_SUMMARY)
    runtime_contract = load_yaml(repo_root / RUNTIME_CONTRACT)
    period_profile = load_yaml(repo_root / PERIOD_PROFILE)
    execution_profile = load_yaml(repo_root / EXECUTION_PROFILE)
    runtime_period_set_id = runtime_contract["period_authority"]["default_runtime_period_set_id"]
    periods = required_l4_periods(period_profile, runtime_period_set_id)
    exported = [row for row in materialization.get("exported_runs", []) if row.get("bundle_manifest_path")]
    manifests: dict[str, dict[str, Any]] = {}
    configs: dict[str, str] = {}
    rows: list[dict[str, Any]] = []

    for exported_row in exported:
        bundle_path = repo_root / exported_row["bundle_manifest_path"]
        bundle = load_json(bundle_path)
        cell_id = str(exported_row["cell_id"])
        common_copy = common_copy_record(repo_root, bundle, copy_common_files=copy_common_files)
        for period in periods:
            attempt_id = attempt_id_for(cell_id, period["period_role"])
            attempt_root = repo_root / "runtime" / "mt5_attempts" / attempt_id
            tester_config_path = attempt_root / "tester_config.ini"
            config_text = build_tester_config_text(
                attempt_id=attempt_id,
                bundle=bundle,
                period=period,
                execution_profile=execution_profile,
            )
            configs[attempt_id] = config_text
            manifest = attempt_manifest(
                repo_root=repo_root,
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
            manifests[attempt_id] = manifest
            rows.append(
                {
                    "attempt_id": attempt_id,
                    "run_id": bundle["run_id"],
                    "bundle_id": bundle["bundle_id"],
                    "cell_id": cell_id,
                    "period_role": period["period_role"],
                    "from_date": period["from_date"],
                    "to_date": period["to_date"],
                    "status": "prepared_pending_terminal_execution",
                    "attempt_manifest_path": f"runtime/mt5_attempts/{attempt_id}/attempt_manifest.yaml",
                    "tester_config_path": f"runtime/mt5_attempts/{attempt_id}/tester_config.ini",
                    "common_model_path": common_copy["model.onnx"]["common_relative_path"],
                    "common_model_copy_status": common_copy["model.onnx"]["copy_status"],
                    "telemetry_common_path": f"{COMMON_REL_ROOT}\\{attempt_id}\\score_telemetry.csv",
                    "feature_count": len(bundle["feature_schema_contract"]["feature_columns"]),
                    "decision_family": bundle["decision_surface"]["decision_family"],
                    "runtime_period_set_id": runtime_period_set_id,
                    "tester_execution_profile_id": execution_profile["profile_id"],
                    "claim_boundary": CLAIM_BOUNDARY,
                }
            )

    role_counts = Counter(row["period_role"] for row in rows)
    copy_counts = Counter(row["common_model_copy_status"] for row in rows)
    summary = {
        "version": "wave0_l4_mt5_attempt_preparation_summary_v1",
        "summary_id": "wave0_l4_mt5_attempt_preparation_summary_v0",
        "work_item_id": WORK_ITEM_ID,
        "subwork_item_id": SUBWORK_ID,
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": created_at_utc,
        "status": "prepared_attempts_pending_terminal_execution",
        "claim_boundary": CLAIM_BOUNDARY,
        "source_inputs": {
            "onnx_materialization_summary": MATERIALIZATION_SUMMARY.as_posix(),
            "onnx_materialization_index": MATERIALIZATION_INDEX.as_posix(),
            "runtime_contract": RUNTIME_CONTRACT.as_posix(),
            "period_profile": PERIOD_PROFILE.as_posix(),
            "tester_execution_profile": EXECUTION_PROFILE.as_posix(),
        },
        "input_hashes": [
            artifact_ref(repo_root / MATERIALIZATION_SUMMARY, repo_root),
            artifact_ref(repo_root / MATERIALIZATION_INDEX, repo_root),
            artifact_ref(repo_root / RUNTIME_CONTRACT, repo_root),
            artifact_ref(repo_root / PERIOD_PROFILE, repo_root),
            artifact_ref(repo_root / EXECUTION_PROFILE, repo_root),
            artifact_ref(repo_root / EA_SOURCE, repo_root),
        ],
        "counts": {
            "exported_bundle_count": len(exported),
            "required_period_role_count": len(periods),
            "prepared_attempt_count": len(rows),
            "period_role_counts": dict(sorted(role_counts.items())),
            "common_copy_status_counts": dict(sorted(copy_counts.items())),
        },
        "runtime_contract_binding": {
            "required_runtime_level": "L4_split_runtime_probe",
            "period_profile_id": period_profile["period_profile_id"],
            "runtime_period_set_id": runtime_period_set_id,
            "required_period_roles": [period["period_role"] for period in periods],
            "tester_execution_profile_id": execution_profile["profile_id"],
            "locked_final_oos_b": "excluded_forbidden_by_default",
            "l5_rule": runtime_contract["runtime_learning_probe_decision"]["l5_continuation_rule"],
        },
        "artifact_outputs": {
            "index_csv": INDEX_PATH.as_posix(),
            "attempt_manifest_paths": [row["attempt_manifest_path"] for row in rows],
            "tester_config_paths": [row["tester_config_path"] for row in rows],
            "ea_source": EA_SOURCE.as_posix(),
            "ea_binary": EA_BINARY.as_posix() if (repo_root / EA_BINARY).exists() else None,
        },
        "compile_smoke": {
            "ea_source": artifact_ref(repo_root / EA_SOURCE, repo_root),
            "ea_binary": (
                artifact_ref(repo_root / EA_BINARY, repo_root, availability="local_binary_hash_recorded_ignored_by_git")
                if (repo_root / EA_BINARY).exists()
                else {"path": EA_BINARY.as_posix(), "exists": False}
            ),
            "claim_boundary": "compile_smoke_only_not_strategy_tester_output",
        },
        "judgment": {
            "judgment_class": "runtime_attempt_preparation",
            "runtime_probe_completed": False,
            "runtime_authority": False,
            "economics_pass": False,
            "selected_baseline": False,
            "goal_achieve": False,
            "next_action": "Run the prepared L4 Strategy Tester attempts for validation and research_oos, then close each result with parity judgment.",
        },
        "prevention_memory": [
            "Feature-column strings use semicolon delimiter to avoid MT5 tester pipe syntax ambiguity.",
            "Single-score ONNX output is required before MT5 L4 score probe consumption.",
            "Prepared attempt manifests are not L4 completion evidence until terminal telemetry/report hashes are recorded.",
        ],
        "environment": {
            "command": " ".join(command_argv),
            "command_argv": command_argv,
            "cwd": ".",
            "python_executable": redact_path(sys.executable),
            "python_version": platform.python_version(),
            "dependency_summary": dependency_summary(),
            "started_at_utc": created_at_utc,
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
    return summary, rows, manifests, configs


def index_fieldnames() -> list[str]:
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


def build_closeout(summary: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    return {
        "version": "work_closeout_v1",
        "work_item_id": SUBWORK_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "created_at_utc": summary["created_at_utc"],
        "status": "completed_attempt_preparation_l4_terminal_execution_pending",
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
            artifact_ref(repo_root / SUMMARY_PATH, repo_root),
            artifact_ref(repo_root / INDEX_PATH, repo_root),
        ],
        "forbidden_claims": summary["forbidden_claims"],
    }


def ensure_list_item(values: list[Any], item: Any) -> None:
    if item not in values:
        values.append(item)


def upsert_artifact_registry(repo_root: Path, summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    registry_path = repo_root / ARTIFACT_REGISTRY
    registry_rows = read_csv_rows(registry_path)
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
    producer = "foundation/pipelines/prepare_wave0_l4_mt5_attempts.py --write-control-records --copy-common-files"
    regen = f"python {producer}"

    def put(row: dict[str, str]) -> None:
        path = repo_root / row["path_or_uri"]
        if path.exists():
            row["sha256"] = sha256(path)
            row["size_bytes"] = str(path.stat().st_size)
        by_id[row["artifact_id"]] = {key: row.get(key, "") for key in fieldnames}

    put(
        {
            "artifact_id": "artifact_wave0_l4_attempt_preparation_summary_v0",
            "run_id": "",
            "bundle_id": "",
            "attempt_id": "",
            "artifact_type": "l4_attempt_preparation_summary",
            "path_or_uri": SUMMARY_PATH.as_posix(),
            "availability": "present_hash_recorded",
            "producer_command": producer,
            "regeneration_command": regen,
            "source_of_truth": SUMMARY_PATH.as_posix(),
            "consumer": WORK_ITEM_ID,
            "claim_boundary": CLAIM_BOUNDARY,
            "notes": "attempt preparation only; Strategy Tester execution remains pending",
        }
    )
    put(
        {
            "artifact_id": "artifact_wave0_l4_attempt_preparation_index_v0",
            "run_id": "",
            "bundle_id": "",
            "attempt_id": "",
            "artifact_type": "l4_attempt_preparation_index",
            "path_or_uri": INDEX_PATH.as_posix(),
            "availability": "present_hash_recorded",
            "producer_command": producer,
            "regeneration_command": regen,
            "source_of_truth": SUMMARY_PATH.as_posix(),
            "consumer": WORK_ITEM_ID,
            "claim_boundary": CLAIM_BOUNDARY,
            "notes": "attempt index for 12 bundles x validation/research_oos roles",
        }
    )
    put(
        {
            "artifact_id": "artifact_wave0_l4_score_probe_ea_source_v0",
            "run_id": "",
            "bundle_id": "",
            "attempt_id": "",
            "artifact_type": "mt5_ea_source",
            "path_or_uri": EA_SOURCE.as_posix(),
            "availability": "present_hash_recorded",
            "producer_command": "manual codex EA adapter implementation",
            "regeneration_command": "compile with MetaEditor64 /portable /compile:<path>",
            "source_of_truth": EA_SOURCE.as_posix(),
            "consumer": WORK_ITEM_ID,
            "claim_boundary": CLAIM_BOUNDARY,
            "notes": "non-trading full-period score telemetry probe",
        }
    )
    if (repo_root / EA_BINARY).exists():
        put(
            {
                "artifact_id": "artifact_wave0_l4_score_probe_ea_binary_v0",
                "run_id": "",
                "bundle_id": "",
                "attempt_id": "",
                "artifact_type": "mt5_ea_binary",
                "path_or_uri": EA_BINARY.as_posix(),
                "availability": "local_binary_hash_recorded",
                "producer_command": "MetaEditor64 /portable /compile:foundation/mt5/experts/SpaceSonar_ONNX_L4_ScoreProbe.mq5",
                "regeneration_command": "compile with MetaEditor64 /portable /compile:<path>",
                "source_of_truth": EA_SOURCE.as_posix(),
                "consumer": WORK_ITEM_ID,
                "claim_boundary": "compile_smoke_only_not_strategy_tester_output",
                "notes": "compiled EA binary hash; not Strategy Tester evidence",
            }
        )
    for row in rows:
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
                "consumer": WORK_ITEM_ID,
                "claim_boundary": CLAIM_BOUNDARY,
                "notes": "prepared L4 MT5 attempt; terminal execution pending",
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
                "consumer": WORK_ITEM_ID,
                "claim_boundary": CLAIM_BOUNDARY,
                "notes": "MT5 Strategy Tester config for one period role",
            }
        )
    write_csv(registry_path, list(by_id.values()), fieldnames)


def update_control_records(repo_root: Path, summary: dict[str, Any], rows: list[dict[str, Any]], closeout: dict[str, Any]) -> None:
    next_work = load_yaml(repo_root / NEXT_WORK_ITEM)
    current_truth = next_work.setdefault("current_truth", {})
    current_truth["l4_attempt_preparation_summary"] = SUMMARY_PATH.as_posix()
    current_truth["l4_attempt_preparation_status"] = summary["status"]
    current_truth["l4_attempt_preparation_counts"] = summary["counts"]
    next_work["status"] = "planned_next_l4_strategy_tester_execution_after_attempt_preparation"
    next_work["missing_material_if_relevant"] = [
        "L4_strategy_tester_terminal_execution_absent_for_prepared_attempts",
        "L4_validation_and_research_oos_reports_absent",
        "score_telemetry_csv_absent_until_terminal_run",
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
    goal["active_phase"] = NEXT_PHASE
    wave_spec = goal.setdefault("program_budgets", {}).setdefault("current_wave0_spec", {})
    wave_spec["l4_attempt_preparation_summary"] = SUMMARY_PATH.as_posix()
    wave_spec["l4_attempt_preparation_status"] = summary["status"]
    wave_spec["l4_attempt_preparation_counts"] = summary["counts"]
    write_yaml(repo_root / GOAL_MANIFEST, goal)

    workspace = load_yaml(repo_root / WORKSPACE_STATE)
    workspace["updated_utc"] = summary["created_at_utc"]
    claims = workspace.setdefault("current_claims", {})
    claims["wave0_l4_attempt_preparation_summary"] = SUMMARY_PATH.as_posix()
    claims["wave0_l4_attempt_preparation_status"] = summary["status"]
    claims["wave0_l4_attempt_preparation_counts"] = summary["counts"]
    claims["active_goal_phase"] = NEXT_PHASE
    write_yaml(repo_root / WORKSPACE_STATE, workspace)

    goal_registry_path = repo_root / GOAL_REGISTRY
    if goal_registry_path.exists():
        goal_rows = read_csv_rows(goal_registry_path)
        for row in goal_rows:
            if row.get("goal_id") == GOAL_ID:
                row["active_phase"] = NEXT_PHASE
                row["next_work_item"] = WORK_ITEM_ID
        write_csv(goal_registry_path, goal_rows, list(goal_rows[0].keys()) if goal_rows else [])

    upsert_artifact_registry(repo_root, summary, rows)


def write_outputs(
    repo_root: Path,
    summary: dict[str, Any],
    rows: list[dict[str, Any]],
    manifests: dict[str, dict[str, Any]],
    configs: dict[str, str],
    *,
    write_control_records: bool,
) -> None:
    for attempt_id, manifest in manifests.items():
        tester_config_path = repo_root / "runtime" / "mt5_attempts" / attempt_id / "tester_config.ini"
        tester_config_path.parent.mkdir(parents=True, exist_ok=True)
        tester_config_path.write_text(configs[attempt_id], encoding="utf-8")
        attempt_path = repo_root / "runtime" / "mt5_attempts" / attempt_id / "attempt_manifest.yaml"
        manifest["artifact_identity"]["tester_config"] = artifact_ref(tester_config_path, repo_root)
        manifest["provenance"]["output_hashes"] = [
            artifact_ref(tester_config_path, repo_root),
            {
                "path": f"runtime/mt5_attempts/{attempt_id}/attempt_manifest.yaml",
                "sha256": "filled_after_write",
                "size_bytes": "filled_after_write",
                "availability": "present_hash_recorded_after_write",
            },
        ]
        write_yaml(attempt_path, manifest)
        manifest["provenance"]["output_hashes"][-1] = artifact_ref(attempt_path, repo_root)
        write_yaml(attempt_path, manifest)
    write_yaml(repo_root / SUMMARY_PATH, summary)
    write_csv(repo_root / INDEX_PATH, rows, index_fieldnames())
    closeout = build_closeout(summary, repo_root)
    write_yaml(repo_root / CLOSEOUT_PATH, closeout)
    if write_control_records:
        update_control_records(repo_root, summary, rows, closeout)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare Wave0/Wave01 L4 MT5 Strategy Tester attempts for ONNX bundles.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--write-control-records", action="store_true")
    parser.add_argument("--copy-common-files", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    started_at = utc_now()
    command_argv = ["python", "foundation/pipelines/prepare_wave0_l4_mt5_attempts.py"]
    if args.write_control_records:
        command_argv.append("--write-control-records")
    if args.copy_common_files:
        command_argv.append("--copy-common-files")
    summary, rows, manifests, _configs = build_attempt_rows_and_manifests(
        repo_root,
        copy_common_files=args.copy_common_files,
        command_argv=command_argv,
        created_at_utc=started_at,
    )
    write_outputs(repo_root, summary, rows, manifests, _configs, write_control_records=args.write_control_records)
    print(
        json.dumps(
            {
                "status": summary["status"],
                "summary": SUMMARY_PATH.as_posix(),
                "prepared_attempt_count": summary["counts"]["prepared_attempt_count"],
                "period_role_counts": summary["counts"]["period_role_counts"],
                "claim_boundary": CLAIM_BOUNDARY,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
