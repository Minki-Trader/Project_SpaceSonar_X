from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import statistics
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation.pipelines.run_mt5_fixed_fixture_probe import (
    DEFAULT_METAEDITOR,
    DEFAULT_TERMINAL,
    parse_compile_log,
    redact_path,
    run_process,
    run_terminal_sequence,
)
from foundation.mt5.runtime_completion import (
    RuntimeAttemptState,
    evaluate_runtime_attempt,
    resolve_tester_report_candidates,
    runtime_status,
    terminal_launched_from_summary,
    terminal_mode_from_summary,
)
from foundation.mt5.tester_report_receipt import (
    build_tester_report_receipt,
    snapshot_report_candidate,
    tester_config_identity,
    tester_report_completed,
    write_receipt,
)
from spacesonar.control_plane.store import filesystem_path


GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WORK_ITEM_ID = "work_wave0_first_batch_l4_follow_through_v0"
SUBWORK_ID = "work_wave0_l4_mt5_runtime_execution_v0"
CAMPAIGN_ID = "campaign_us100_task_surface_scout_v0"
SWEEP_ID = "sweep_wave0_broad_surface_scout_v0"
OUTPUT_DIR = Path("lab/campaigns/campaign_us100_task_surface_scout_v0/l4_follow_through")
PREP_INDEX = OUTPUT_DIR / "l4_attempt_preparation_index.csv"
RUNTIME_SUMMARY = OUTPUT_DIR / "l4_runtime_execution_summary.yaml"
RUNTIME_INDEX = OUTPUT_DIR / "l4_runtime_execution_index.csv"
CLOSEOUT_PATH = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/work_wave0_l4_mt5_runtime_execution_v0_closeout.yaml")
NEXT_WORK_ITEM = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml")
RESUME_CURSOR = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml")
GOAL_MANIFEST = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml")
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")
GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")
EA_SOURCE = Path("foundation/mt5/experts/SpaceSonar_ONNX_L4_ScoreProbe.mq5")
EA_BINARY = Path("foundation/mt5/experts/SpaceSonar_ONNX_L4_ScoreProbe.ex5")
CLAIM_BOUNDARY = "l4_score_runtime_observation_only_no_runtime_authority_no_economics_pass_no_candidate"
PARTIAL_STATUS = "partial_l4_terminal_execution_started"
ALL_ATTEMPTS_STATUS = "l4_terminal_execution_attempted_for_all_prepared_attempts"
COMMON_REL_ROOT = "SpaceSonar\\l4_score_probe"
TESTER_REPORT_REL_ROOT = "reports\\spacesonar"
TESTER_REPORT_SUFFIXES = {".htm", ".html", ".xml"}


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(filesystem_path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repo_relative(path: Path, repo_root: Path = REPO_ROOT) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return redact_path(str(path))


def artifact_ref(path: Path, repo_root: Path = REPO_ROOT, *, availability: str = "present_hash_recorded") -> dict[str, Any]:
    full = path if path.is_absolute() else repo_root / path
    return {
        "path": repo_relative(full, repo_root),
        "sha256": sha256(full),
        "size_bytes": full.stat().st_size,
        "availability": availability,
    }


def ensure_tester_report_receipt_artifact_ref(
    receipt_path: Path,
    receipt: dict[str, Any],
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    full = receipt_path if receipt_path.is_absolute() else repo_root / receipt_path
    if not full.exists():
        try:
            write_receipt(full, receipt)
        except OSError as exc:
            receipt.setdefault("writer_warnings", []).append(
                {
                    "stage": "write_receipt",
                    "error_class": exc.__class__.__name__,
                    "claim_effect": "receipt_write_retry_required_before_artifact_ref",
                }
            )
    if not full.exists():
        os.makedirs(filesystem_path(full.parent), exist_ok=True)
        with open(filesystem_path(full), "w", encoding="utf-8") as handle:
            yaml.dump(receipt, handle, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=False)
    return artifact_ref(full, repo_root)


def is_tester_report_artifact(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in TESTER_REPORT_SUFFIXES


def load_yaml(path: Path) -> dict[str, Any]:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle)


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    os.makedirs(filesystem_path(path.parent), exist_ok=True)
    with open(filesystem_path(path), "w", encoding="utf-8") as handle:
        yaml.dump(payload, handle, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=False)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with open(filesystem_path(path), "r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    os.makedirs(filesystem_path(path.parent), exist_ok=True)
    with open(filesystem_path(path), "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def common_files_root() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA is unavailable; cannot locate MT5 Common\\Files")
    return Path(appdata) / "MetaQuotes" / "Terminal" / "Common" / "Files"


def common_relative_to_path(common_relative_path: str, *, root: Path | None = None) -> Path:
    root = root or common_files_root()
    parts = [part for part in common_relative_path.replace("\\", "/").split("/") if part]
    full = root.joinpath(*parts).resolve()
    root_resolved = root.resolve()
    if not full.is_relative_to(root_resolved):
        raise RuntimeError(f"common path escapes MT5 Common Files root: {common_relative_path}")
    return full


def load_json(path: Path) -> dict[str, Any]:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def current_git_identity(repo_root: Path) -> dict[str, Any]:
    def run_git(args: list[str]) -> str:
        result = subprocess.run(["git", *args], cwd=repo_root, text=True, capture_output=True, check=False)
        return result.stdout.strip() if result.returncode == 0 else "unknown"

    changed = [line for line in run_git(["status", "--short"]).splitlines() if line]
    return {
        "git_sha": run_git(["rev-parse", "HEAD"]),
        "branch": run_git(["branch", "--show-current"]),
        "dirty_flag": bool(changed),
        "changed_files": changed,
        "dirty_claim_effect": "runtime_execution_records_may_be_partial" if changed else "clean_before_runtime_execution",
    }


def dependency_summary() -> dict[str, str]:
    return {
        "python": sys.version.split()[0],
        "yaml": yaml.__version__,
        "platform": sys.platform,
    }


def selected_attempt_rows(
    rows: list[dict[str, str]],
    *,
    repo_root: Path,
    attempt_ids: set[str] | None,
    period_roles: set[str] | None,
    limit: int | None,
    include_completed: bool,
) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    for row in rows:
        if attempt_ids and row["attempt_id"] not in attempt_ids:
            continue
        if period_roles and row["period_role"] not in period_roles:
            continue
        manifest_path = repo_root / row["attempt_manifest_path"]
        manifest_status = row.get("status", "")
        manifest_complete = False
        if manifest_path.exists():
            manifest = load_yaml(manifest_path)
            manifest_status = str(manifest.get("status", manifest_status))
            manifest_complete = bool((manifest.get("execution_state") or {}).get("runtime_probe_complete"))
        if not include_completed and manifest_complete:
            continue
        item = dict(row)
        item["manifest_status"] = manifest_status
        selected.append(item)
        if limit is not None and len(selected) >= limit:
            break
    return selected


def execution_index_fieldnames() -> list[str]:
    return [
        "attempt_id",
        "run_id",
        "bundle_id",
        "cell_id",
        "period_role",
        "from_date",
        "to_date",
        "status",
        "result_judgment",
        "telemetry_observed",
        "telemetry_row_count",
        "tester_report_observed",
        "runtime_probe_complete",
        "terminal_mode",
        "terminal_exit_code",
        "terminal_timed_out",
        "terminal_run_summary_path",
        "score_telemetry_summary_path",
        "score_diagnostic_summary_path",
        "repo_telemetry_path",
        "tester_report_path",
        "claim_boundary",
        "next_action",
    ]


def bool_text(value: Any) -> bool:
    return str(value).lower() == "true"


def execution_row_from_manifest(
    repo_root: Path,
    prep_row: dict[str, str],
    existing_row: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    manifest_path = repo_root / prep_row["attempt_manifest_path"]
    if not manifest_path.exists():
        return existing_row
    manifest = load_yaml(manifest_path) or {}
    execution_state = manifest.get("execution_state") or {}
    if not execution_state:
        return existing_row

    attempt_id = prep_row["attempt_id"]
    attempt_root = repo_root / "runtime" / "mt5_attempts" / attempt_id
    terminal_path = attempt_root / "terminal_run_summary.yaml"
    telemetry_summary_path = attempt_root / "score_telemetry_summary.yaml"
    diagnostic_summary_path = attempt_root / "score_diagnostic_summary.yaml"
    terminal_summary = load_yaml(terminal_path) if terminal_path.exists() else {}
    telemetry_summary = load_yaml(telemetry_summary_path) if telemetry_summary_path.exists() else {}
    telemetry_artifact = telemetry_summary.get("telemetry") or {}
    telemetry_stats = telemetry_summary.get("stats") or {}
    tester_report = manifest.get("tester_report") or {}
    row = dict(existing_row or {})
    row.update(
        {
            "attempt_id": attempt_id,
            "run_id": prep_row.get("run_id") or manifest.get("run_id") or row.get("run_id", ""),
            "bundle_id": prep_row.get("bundle_id") or manifest.get("bundle_id") or row.get("bundle_id", ""),
            "cell_id": prep_row.get("cell_id") or manifest.get("cell_id") or row.get("cell_id", ""),
            "period_role": prep_row.get("period_role") or manifest.get("period_role") or row.get("period_role", ""),
            "from_date": prep_row.get("from_date") or manifest.get("from_date") or row.get("from_date", ""),
            "to_date": prep_row.get("to_date") or manifest.get("to_date") or row.get("to_date", ""),
            "status": manifest.get("status", row.get("status", "")),
            "result_judgment": manifest.get("result_judgment", row.get("result_judgment", "")),
            "telemetry_observed": bool(execution_state.get("telemetry_rows_observed")),
            "telemetry_row_count": telemetry_stats.get("row_count")
            or terminal_summary.get("telemetry_row_count")
            or row.get("telemetry_row_count", ""),
            "tester_report_observed": bool(execution_state.get("tester_report_observed")),
            "runtime_probe_complete": bool(execution_state.get("runtime_probe_complete")),
            "terminal_mode": execution_state.get("terminal_mode", row.get("terminal_mode", "")),
            "terminal_exit_code": terminal_summary.get("exit_code", row.get("terminal_exit_code", "")),
            "terminal_timed_out": terminal_summary.get("timed_out", row.get("terminal_timed_out", "")),
            "terminal_run_summary_path": repo_relative(terminal_path, repo_root),
            "score_telemetry_summary_path": repo_relative(telemetry_summary_path, repo_root),
            "score_diagnostic_summary_path": repo_relative(diagnostic_summary_path, repo_root)
            if diagnostic_summary_path.exists()
            else row.get("score_diagnostic_summary_path", ""),
            "repo_telemetry_path": telemetry_artifact.get("path") or row.get("repo_telemetry_path", ""),
            "tester_report_path": tester_report.get("path") or row.get("tester_report_path", ""),
            "claim_boundary": manifest.get("claim_boundary", row.get("claim_boundary", "")),
            "next_action": manifest.get("next_action", row.get("next_action", "")),
        }
    )
    return row


def ensure_ea_binary(
    *,
    repo_root: Path,
    metaeditor: Path,
    force_compile: bool,
    skip_compile_if_missing: bool,
    timeout_seconds: int,
    started_at_utc: str,
) -> dict[str, Any]:
    source = repo_root / EA_SOURCE
    binary = repo_root / EA_BINARY
    compile_summary_path = repo_root / OUTPUT_DIR / "l4_runtime_execution_compile_summary.yaml"
    should_compile = force_compile or (not binary.exists() and not skip_compile_if_missing)
    process: dict[str, Any] | None = None
    compile_log_ref: dict[str, Any] | None = None
    if should_compile:
        compile_log = repo_root / OUTPUT_DIR / "l4_runtime_execution_compile.log"
        argv = [
            str(metaeditor),
            "/portable",
            f"/compile:{source}",
            f"/log:{compile_log}",
        ]
        process = run_process(argv, cwd=repo_root, timeout_seconds=timeout_seconds)
        compile_log_ref = parse_compile_log(compile_log)

    binary_exists = binary.exists()
    summary: dict[str, Any] = {
        "version": "wave0_l4_runtime_execution_compile_summary_v1",
        "summary_path": repo_relative(compile_summary_path, repo_root),
        "created_at_utc": started_at_utc,
        "ea_source": artifact_ref(source, repo_root),
        "ea_binary": artifact_ref(binary, repo_root, availability="local_binary_hash_recorded_ignored_by_git")
        if binary_exists
        else {"path": EA_BINARY.as_posix(), "exists": False, "availability": "missing_local_binary"},
        "compile_attempted": should_compile,
        "compile_process": process,
        "compile_log": compile_log_ref,
        "status": "ea_binary_available" if binary_exists else "ea_binary_missing",
        "claim_boundary": "ea_compile_or_binary_preflight_only_not_strategy_tester_output",
    }
    if should_compile:
        errors = (compile_log_ref or {}).get("compile_errors")
        warnings = (compile_log_ref or {}).get("compile_warnings")
        summary["compile_success_derived_from_log_and_binary"] = bool(binary_exists and errors == 0 and warnings == 0)
        summary["status"] = "ea_compiled_for_runtime_execution" if summary["compile_success_derived_from_log_and_binary"] else "ea_compile_failed"
    elif not binary_exists and skip_compile_if_missing:
        summary["failure_disposition"] = {
            "reproduction": "EA binary missing before terminal execution",
            "exact_failing_layer": "mt5_ea_binary_preflight",
            "bounded_repair_or_fallback_attempt": "skipped_by_cli_flag_skip_compile_ea_if_missing",
            "evidence_path": repo_relative(compile_summary_path, repo_root),
            "remaining_blocker": "SpaceSonar_ONNX_L4_ScoreProbe.ex5 not available",
            "reopen_condition": "run without --skip-compile-ea-if-missing or provide compiled .ex5",
        }
    write_yaml(compile_summary_path, summary)
    return summary


def parse_tester_config_report_stem(path: Path) -> str | None:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        lines = handle.read().splitlines()
    for line in lines:
        if line.strip().lower().startswith("report="):
            return line.split("=", 1)[1].strip()
    return None


def parse_tester_config_expert(path: Path) -> str | None:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        lines = handle.read().splitlines()
    for line in lines:
        if line.strip().lower().startswith("expert="):
            return line.split("=", 1)[1].strip().strip('"')
    return None


def terminal_data_root(repo_root: Path) -> Path:
    for parent in [repo_root, *repo_root.parents]:
        if parent.name.lower() == "mql5":
            return parent.parent
    return repo_root


def upsert_ini_line(text: str, key: str, value: str, *, after_key: str | None = None) -> str:
    lines = text.splitlines()
    prefix = f"{key}="
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = f"{key}={value}"
            return "\n".join(lines) + "\n"
    insert_at = len(lines)
    if after_key:
        after_prefix = f"{after_key}="
        for index, line in enumerate(lines):
            if line.startswith(after_prefix):
                insert_at = index + 1
                break
    lines.insert(insert_at, f"{key}={value}")
    return "\n".join(lines) + "\n"


def tester_report_relative_stem(attempt_id: str) -> str:
    return f"{TESTER_REPORT_REL_ROOT}\\{attempt_id}\\tester_report"


def normalize_tester_report_config(tester_config: Path, attempt_id: str) -> dict[str, Any]:
    report_stem = tester_report_relative_stem(attempt_id)
    with open(filesystem_path(tester_config), "r", encoding="utf-8-sig") as handle:
        original = handle.read()
    updated = upsert_ini_line(original, "Report", report_stem, after_key="ReplaceReport")
    updated = upsert_ini_line(updated, "ReplaceReport", "1", after_key="Leverage")
    updated = upsert_ini_line(updated, "ShutdownTerminal", "1", after_key="Report")
    changed = updated != original
    if changed:
        with open(filesystem_path(tester_config), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(updated)
    return {
        "status": "tester_report_config_normalized",
        "changed": changed,
        "report_value": report_stem,
        "report_value_policy": "terminal_relative_stem_resolved_against_portable_root_main_data_root_and_attempt_archive",
    }


def ensure_portable_ea_stage(
    *,
    repo_root: Path,
    tester_config: Path,
    portable_terminal_root: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    expert_value = parse_tester_config_expert(tester_config)
    stage: dict[str, Any] = {
        "status": "not_configured",
        "tester_expert_value": expert_value,
        "claim_boundary": "portable_ea_stage_preflight_only_no_runtime_authority",
    }
    if not expert_value:
        manifest.setdefault("runtime_surface_contract", {})["portable_ea_stage_status"] = "not_configured"
        manifest.setdefault("artifact_identity", {}).setdefault("portable_runtime_root", {})["ea_binary"] = stage
        return manifest

    expert_relative = Path(expert_value.replace("\\", "/"))
    destination = portable_terminal_root / "MQL5" / "Experts" / expert_relative
    source_binary = repo_root / EA_BINARY
    source_mq5 = repo_root / EA_SOURCE
    try:
        os.makedirs(filesystem_path(destination.parent), exist_ok=True)
        copy_status = "already_current"
        if not destination.exists() or sha256(destination) != sha256(source_binary):
            shutil.copy2(source_binary, destination)
            copy_status = "copied_to_portable_mql5_experts"
        source_destination = destination.with_suffix(".mq5")
        if source_mq5.exists():
            if not source_destination.exists() or sha256(source_destination) != sha256(source_mq5):
                shutil.copy2(source_mq5, source_destination)
        stage = {
            "status": "staged",
            "copy_status": copy_status,
            "tester_expert_value": expert_value,
            "portable_terminal_root_redacted": redact_path(str(portable_terminal_root)),
            "portable_ex5_redacted": redact_path(str(destination)),
            "source": artifact_ref(source_binary, repo_root, availability="local_binary_hash_recorded_ignored_by_git"),
            "portable_sha256": sha256(destination),
            "portable_size_bytes": destination.stat().st_size,
            "durable_identity": "tester_config_expert_value_plus_source_binary_sha256",
            "claim_boundary": "portable_ea_stage_preflight_only_no_runtime_authority",
        }
    except OSError as exc:
        stage = {
            "status": "stage_failed",
            "tester_expert_value": expert_value,
            "portable_terminal_root_redacted": redact_path(str(portable_terminal_root)),
            "portable_ex5_redacted": redact_path(str(destination)),
            "error_class": exc.__class__.__name__,
            "error_message": str(exc),
            "remaining_blocker": "required_ex5_not_staged_under_portable_mql5_experts_path",
            "claim_boundary": "portable_ea_stage_failed_no_runtime_completion_claim",
        }

    manifest.setdefault("artifact_identity", {}).setdefault("portable_runtime_root", {})["ea_binary"] = stage
    manifest.setdefault("runtime_surface_contract", {})["portable_ea_stage_status"] = stage["status"]
    return manifest


def feature_columns_common_relative(bundle_id: str) -> str:
    return f"{COMMON_REL_ROOT}\\{bundle_id}\\feature_columns.txt"


def score_diagnostics_common_relative(attempt_id: str) -> str:
    return f"{COMMON_REL_ROOT}\\{attempt_id}\\score_diagnostics.csv"


def ensure_score_diagnostic_transport(
    *,
    manifest: dict[str, Any],
    tester_config: Path,
    attempt_id: str,
) -> dict[str, Any]:
    common_relative = score_diagnostics_common_relative(attempt_id)
    common_path = common_relative_to_path(common_relative)
    os.makedirs(filesystem_path(common_path.parent), exist_ok=True)

    with open(filesystem_path(tester_config), "r", encoding="utf-8-sig") as handle:
        config_text = handle.read()
    updated = upsert_ini_line(
        config_text,
        "InpDiagnosticPath",
        common_relative,
        after_key="InpOutputPath",
    )
    if updated != config_text:
        with open(filesystem_path(tester_config), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(updated)

    diagnostic_ref = {
        "common_relative_path": common_relative,
        "redacted_absolute_path": "${MT5_COMMONDATA}\\Files\\" + common_relative,
        "durable_identity": "common_relative_path_plus_attempt_id",
        "path_boundary": "redacted_local_context_only",
        "copy_status": "configured_for_mt5_common_files",
        "transport_reason": "capture EA-level score-probe path diagnostics without turning diagnostics into runtime proof",
    }
    manifest.setdefault("artifact_identity", {}).setdefault("diagnostics", {})["score_diagnostics.csv"] = diagnostic_ref
    runtime_contract = manifest.setdefault("runtime_surface_contract", {})
    runtime_contract["score_diagnostic_transport"] = "common_file_observation_only"
    runtime_contract["score_diagnostics_common_relative_path"] = common_relative
    return manifest


def ensure_feature_columns_transport(
    *,
    repo_root: Path,
    row: dict[str, str],
    manifest: dict[str, Any],
    tester_config: Path,
) -> dict[str, Any]:
    bundle_path = repo_root / "runtime" / "packages" / row["bundle_id"] / "experiment_bundle.json"
    bundle = load_json(bundle_path)
    columns = bundle["feature_schema_contract"]["feature_columns"]
    columns_text = ";".join(columns)
    common_relative = feature_columns_common_relative(row["bundle_id"])
    common_path = common_relative_to_path(common_relative)
    os.makedirs(filesystem_path(common_path.parent), exist_ok=True)
    with open(filesystem_path(common_path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(columns_text)

    with open(filesystem_path(tester_config), "r", encoding="utf-8-sig") as handle:
        config_text = handle.read()
    updated = upsert_ini_line(
        config_text,
        "InpFeatureColumnsPath",
        common_relative,
        after_key="InpFeatureColumns",
    )
    if updated != config_text:
        with open(filesystem_path(tester_config), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(updated)

    feature_ref = {
        "common_relative_path": common_relative,
        "redacted_absolute_path": "${MT5_COMMONDATA}\\Files\\" + common_relative,
        "sha256": sha256(common_path),
        "size_bytes": common_path.stat().st_size,
        "feature_count": len(columns),
        "durable_identity": "common_relative_path_plus_sha256",
        "path_boundary": "redacted_local_context_only",
        "copy_status": "copied_to_mt5_common_files",
        "transport_reason": "avoid_MT5_tester_input_string_truncation_for_long_feature_lists",
    }
    manifest.setdefault("artifact_identity", {}).setdefault("common_files", {})["feature_columns.txt"] = feature_ref
    runtime_contract = manifest.setdefault("runtime_surface_contract", {})
    runtime_contract["feature_columns_transport"] = "common_file_with_inline_fallback"
    runtime_contract["feature_columns_common_relative_path"] = common_relative
    runtime_contract["feature_count"] = len(columns)
    runtime_contract["feature_order_hash"] = hashlib.sha256("|".join(columns).encode("utf-8")).hexdigest()
    parity = manifest.setdefault("proxy_runtime_parity", {})
    prevention = parity.setdefault("prevention_memory", [])
    memory = "Use Common Files feature_columns.txt transport for long feature lists to avoid MT5 tester input truncation."
    if memory not in prevention:
        prevention.append(memory)
    known = parity.setdefault("known_differences", [])
    difference = "MT5 tester input strings can truncate long semicolon feature lists; runtime uses feature_columns.txt common-file transport."
    if difference not in known:
        known.append(difference)
    manifest["artifact_identity"]["tester_config"] = artifact_ref(tester_config, repo_root)
    manifest["artifact_identity"]["ea_entrypoint"] = artifact_ref(repo_root / EA_SOURCE, repo_root)
    binary = repo_root / EA_BINARY
    if binary.exists():
        manifest["artifact_identity"]["ea_binary"] = artifact_ref(binary, repo_root, availability="local_binary_hash_recorded_ignored_by_git")
    return manifest


def candidate_report_paths(
    repo_root: Path,
    attempt_root: Path,
    tester_config: Path,
    *,
    portable_terminal_root: Path | None = None,
    main_terminal_data_root: Path | None = None,
) -> list[tuple[Path, str]]:
    candidates: list[tuple[Path, str]] = []
    stem = parse_tester_config_report_stem(tester_config)
    if stem:
        for candidate in resolve_tester_report_candidates(
            report_value=stem,
            repo_root=repo_root,
            portable_terminal_root=portable_terminal_root,
            main_terminal_data_root=main_terminal_data_root,
            attempt_root=attempt_root,
        ):
            if is_tester_report_artifact(candidate.path):
                candidates.append((candidate.path, candidate.origin))
    candidates.extend(
        (path, "attempt_archive_path")
        for path in attempt_root.glob("tester_report*")
        if is_tester_report_artifact(path)
    )
    seen: set[Path] = set()
    unique: list[tuple[Path, str]] = []
    for path, origin in candidates:
        resolved = path.resolve()
        if resolved not in seen:
            unique.append((path, origin))
            seen.add(resolved)
    return unique


def prepare_tester_report_directories(
    *,
    repo_root: Path,
    attempt_root: Path,
    tester_config: Path,
    portable_terminal_root: Path | None,
    main_terminal_data_root: Path | None,
) -> dict[str, Any]:
    stem = parse_tester_config_report_stem(tester_config)
    if not stem:
        return {"status": "no_report_value_configured", "prepared": [], "skipped": []}
    prepared: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    prelaunch: list[dict[str, Any]] = []
    seen_prelaunch: set[str] = set()
    for candidate in resolve_tester_report_candidates(
        report_value=stem,
        repo_root=repo_root,
        portable_terminal_root=portable_terminal_root,
        main_terminal_data_root=main_terminal_data_root,
        attempt_root=attempt_root,
    ):
        snapshot = snapshot_report_candidate(candidate.path, candidate.origin)
        if snapshot["path_key"] not in seen_prelaunch:
            prelaunch.append(snapshot)
            seen_prelaunch.add(snapshot["path_key"])
        try:
            os.makedirs(filesystem_path(candidate.path.parent), exist_ok=True)
            prepared.append({"origin": candidate.origin, "redacted_parent": redact_path(str(candidate.path.parent))})
        except OSError as exc:
            skipped.append(
                {
                    "origin": candidate.origin,
                    "redacted_parent": redact_path(str(candidate.path.parent)),
                    "reason": f"{exc.__class__.__name__}: {exc}",
                }
            )
    for path in attempt_root.glob("tester_report*"):
        if not is_tester_report_artifact(path):
            continue
        snapshot = snapshot_report_candidate(path, "attempt_archive_path")
        if snapshot["path_key"] not in seen_prelaunch:
            prelaunch.append(snapshot)
            seen_prelaunch.add(snapshot["path_key"])
    status = "tester_report_directories_prepared"
    if skipped:
        status = "tester_report_directories_partially_prepared"
    if not prepared and skipped:
        status = "tester_report_directories_not_prepared"
    return {
        "status": status,
        "report_value": stem,
        "prepared": prepared,
        "skipped": skipped,
        "prelaunch_candidates": prelaunch,
    }


def public_report_resolution_summary(summary: dict[str, Any]) -> dict[str, Any]:
    public = dict(summary)
    public_candidates: list[dict[str, Any]] = []
    for candidate in summary.get("prelaunch_candidates", []):
        item = dict(candidate)
        path_key_value = item.pop("path_key", "")
        if path_key_value:
            item["path_key_sha256"] = hashlib.sha256(str(path_key_value).encode("utf-8")).hexdigest()
        public_candidates.append(item)
    public["prelaunch_candidates"] = public_candidates
    return public


def archive_tester_report(
    repo_root: Path,
    attempt_root: Path,
    tester_config: Path,
    *,
    portable_terminal_root: Path | None = None,
    main_terminal_data_root: Path | None = None,
) -> dict[str, Any]:
    candidates = candidate_report_paths(
        repo_root,
        attempt_root,
        tester_config,
        portable_terminal_root=portable_terminal_root,
        main_terminal_data_root=main_terminal_data_root,
    )
    if not candidates:
        return {
            "observed": False,
            "status": "tester_report_missing_after_terminal_execution",
            "path": None,
            "claim_boundary": "missing_report_no_economics_or_completion_claim",
        }
    report, origin = candidates[0]
    report = report.resolve()
    attempt_resolved = attempt_root.resolve()
    if not report.is_relative_to(attempt_resolved):
        reports_dir = attempt_root / "reports"
        os.makedirs(filesystem_path(reports_dir), exist_ok=True)
        archived = reports_dir / report.name
        shutil.copy2(report, archived)
        return {
            "observed": True,
            "status": "tester_report_archived_local_hash_recorded",
            "origin": origin,
            "source_redacted_path": redact_path(str(report)),
            **artifact_ref(archived, repo_root, availability="local_report_hash_recorded_ignored_by_git"),
            "claim_boundary": "tester_report_local_evidence_only_no_economics_pass",
        }
    reports_dir = attempt_root / "reports"
    os.makedirs(filesystem_path(reports_dir), exist_ok=True)
    archived = reports_dir / report.name
    if report.resolve() != archived.resolve():
        shutil.move(str(report), str(archived))
    return {
        "observed": True,
        "status": "tester_report_archived_local_hash_recorded",
        "origin": origin,
        **artifact_ref(archived, repo_root, availability="local_report_hash_recorded_ignored_by_git"),
        "claim_boundary": "tester_report_local_evidence_only_no_economics_pass",
    }


def build_tester_report_receipt_for_attempt(
    *,
    repo_root: Path,
    attempt_root: Path,
    attempt_id: str,
    tester_config: Path,
    portable_terminal_root: Path | None,
    main_terminal_data_root: Path | None,
    prelaunch_candidates: list[dict[str, Any]],
    launch_started_at_utc: str | None,
) -> dict[str, Any]:
    candidates = candidate_report_paths(
        repo_root,
        attempt_root,
        tester_config,
        portable_terminal_root=portable_terminal_root,
        main_terminal_data_root=main_terminal_data_root,
    )
    report_path: Path | None = None
    source_origin: str | None = None
    if candidates:
        report_path, source_origin = candidates[0]
    receipt = build_tester_report_receipt(
        attempt_id=attempt_id,
        report_path=report_path,
        source_origin=source_origin,
        launch_started_at_utc=launch_started_at_utc,
        prelaunch_candidates=prelaunch_candidates,
        expected_identity=tester_config_identity(tester_config),
    )
    write_receipt(attempt_root / "tester_report_receipt.yaml", receipt)
    return receipt


def runtime_contract_value(
    manifest: dict[str, Any],
    row: dict[str, str],
    key: str,
    *contract_keys: str,
) -> str | None:
    runtime_contract = manifest.get("runtime_surface_contract") or {}
    routing = manifest.get("runtime_probe_routing") or {}
    period_identity = manifest.get("period_identity") or {}
    execution_identity = manifest.get("execution_identity") or {}
    tester_identity = manifest.get("tester_identity") or {}
    for value in [
        period_identity.get(key),
        *(period_identity.get(item) for item in contract_keys),
        execution_identity.get(key),
        *(execution_identity.get(item) for item in contract_keys),
        tester_identity.get(key),
        *(tester_identity.get(item) for item in contract_keys),
        row.get(key),
        manifest.get(key),
        runtime_contract.get(key),
        *(runtime_contract.get(item) for item in contract_keys),
        routing.get(key),
        *(routing.get(item) for item in contract_keys),
    ]:
        if value not in (None, ""):
            return str(value)
    return None


def ensure_completion_surface_scope(manifest: dict[str, Any], completion_surface_scope: str) -> None:
    runtime_contract = manifest.setdefault("runtime_surface_contract", {})
    runtime_contract["completion_surface_scope"] = completion_surface_scope


def parse_score_telemetry(path: Path) -> dict[str, Any]:
    with open(filesystem_path(path), "r", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return {"row_count": 0, "status": "empty_telemetry"}
    scores: list[float] = []
    spreads: list[float] = []
    tick_volume_nonzero = 0
    decision_counts: Counter[str] = Counter()
    symbol_counts: Counter[str] = Counter()
    period_counts: Counter[str] = Counter()
    feature_counts: Counter[str] = Counter()
    for row in rows:
        decision_counts[str(row.get("decision", ""))] += 1
        symbol_counts[str(row.get("symbol", ""))] += 1
        period_counts[str(row.get("period", ""))] += 1
        feature_counts[str(row.get("feature_count", ""))] += 1
        try:
            score = float(row.get("score", "nan"))
            if math.isfinite(score):
                scores.append(score)
        except ValueError:
            pass
        try:
            spreads.append(float(row.get("spread_points", "nan")))
        except ValueError:
            pass
        try:
            tick_volume_nonzero += int(float(row.get("tick_volume", "0"))) > 0
        except ValueError:
            pass
    spread_values = [value for value in spreads if math.isfinite(value)]
    return {
        "status": "telemetry_observed",
        "row_count": len(rows),
        "first_bar_close_time": rows[0].get("bar_close_time"),
        "last_bar_close_time": rows[-1].get("bar_close_time"),
        "symbol_counts": dict(sorted(symbol_counts.items())),
        "period_counts": dict(sorted(period_counts.items())),
        "feature_count_values": dict(sorted(feature_counts.items())),
        "decision_counts": dict(sorted(decision_counts.items())),
        "score_stats": {
            "finite_count": len(scores),
            "min": min(scores) if scores else None,
            "max": max(scores) if scores else None,
            "mean": statistics.fmean(scores) if scores else None,
        },
        "spread_points_stats": {
            "finite_count": len(spread_values),
            "min": min(spread_values) if spread_values else None,
            "max": max(spread_values) if spread_values else None,
            "mean": statistics.fmean(spread_values) if spread_values else None,
        },
        "tick_volume_nonzero_count": tick_volume_nonzero,
    }


def parse_score_diagnostics(path: Path) -> dict[str, Any]:
    with open(filesystem_path(path), "r", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return {"status": "empty_diagnostic", "event_count": 0, "event_counts": {}}

    event_counts: Counter[str] = Counter()
    last_rows: list[dict[str, Any]] = []
    maxima = {
        "max_rows_written": 0,
        "max_ticks_seen": 0,
        "max_closed_bar_candidates": 0,
        "max_feature_failures": 0,
        "max_onnx_failures": 0,
    }
    counter_fields = {
        "rows_written": "max_rows_written",
        "ticks_seen": "max_ticks_seen",
        "closed_bar_candidates": "max_closed_bar_candidates",
        "feature_failures": "max_feature_failures",
        "onnx_failures": "max_onnx_failures",
    }
    for row in rows:
        event_counts[str(row.get("event", ""))] += 1
        for field, target in counter_fields.items():
            try:
                value = int(float(row.get(field, "0") or 0))
            except ValueError:
                value = 0
            maxima[target] = max(maxima[target], value)
        last_rows.append(
            {
                "event_time": row.get("event_time", ""),
                "event": row.get("event", ""),
                "bar_time": row.get("bar_time", ""),
                "detail": row.get("detail", ""),
                "last_error": row.get("last_error", ""),
                "rows_written": row.get("rows_written", ""),
                "ticks_seen": row.get("ticks_seen", ""),
                "closed_bar_candidates": row.get("closed_bar_candidates", ""),
                "feature_failures": row.get("feature_failures", ""),
                "onnx_failures": row.get("onnx_failures", ""),
            }
        )

    return {
        "status": "diagnostic_observed",
        "event_count": len(rows),
        "event_counts": dict(sorted(event_counts.items())),
        **maxima,
        "last_events": last_rows[-10:],
    }


def normalize_l4_terminal_summary(terminal_summary: dict[str, Any]) -> dict[str, Any]:
    summary = dict(terminal_summary)
    mode = summary.get("mode")
    if mode == "main_mode_config_fallback":
        summary["attempt_claim_boundary"] = "local_l4_main_mode_fallback_only_no_runtime_authority"
    for attempt in summary.get("terminal_attempts", []):
        if attempt.get("mode") == "main_mode_config_fallback":
            attempt["attempt_claim_boundary"] = "local_l4_main_mode_fallback_only_no_runtime_authority"
    policy = dict(summary.get("terminal_mode_policy") or {})
    if policy.get("main_mode_fallback_used"):
        policy["fallback_reason"] = "portable_attempt_did_not_produce_l4_score_telemetry"
        policy["claim_effect"] = "l4_local_main_mode_fallback_observation_only_no_standard_portable_completion_claim"
    elif policy:
        policy["claim_effect"] = "l4_standard_portable_attempt_observation"
    summary["terminal_mode_policy"] = policy
    return summary


def update_coverage(
    manifest: dict[str, Any],
    *,
    telemetry_observed: bool,
    report_observed: bool,
    report_completed: bool,
) -> None:
    coverage = manifest.setdefault("required_gate_coverage", {})
    passed = coverage.setdefault("passed", [])
    missing = coverage.setdefault("missing", [])

    def mark_passed(gate: str) -> None:
        if gate in missing:
            missing.remove(gate)
        if gate not in passed:
            passed.append(gate)

    def mark_missing(gate: str) -> None:
        if gate in passed:
            passed.remove(gate)
        if gate not in missing:
            missing.append(gate)

    if telemetry_observed:
        mark_passed("Strategy_Tester_terminal_execution")
        mark_passed("score_telemetry_csv")
        mark_passed("result_judgment_from_L4")
    else:
        mark_passed("Strategy_Tester_terminal_execution")
        mark_missing("score_telemetry_csv")
        mark_missing("result_judgment_from_L4")
    if report_completed:
        mark_passed("L4_period_role_completed_report")
    else:
        mark_missing("L4_period_role_completed_report")
    if report_observed:
        mark_passed("tester_report_hash")
    else:
        mark_missing("tester_report_hash")


def append_missing_evidence(manifest: dict[str, Any], values: list[str]) -> None:
    missing = manifest.setdefault("missing_evidence", [])
    for value in values:
        if value and value not in missing:
            missing.append(value)


def score_attempt_next_action(runtime_probe_complete: bool) -> str:
    if runtime_probe_complete:
        return "aggregate this period role with its paired L4 attempt before L5 decision"
    return "inspect terminal/EA/report evidence and rerun or repair this attempt before L4 completion claim"


def attempt_root(repo_root: Path, attempt_id: str) -> Path:
    return repo_root / "runtime" / "mt5_attempts" / attempt_id


def run_one_attempt(
    *,
    repo_root: Path,
    row: dict[str, str],
    terminal: Path,
    timeout_seconds: int,
    terminate_existing: bool,
    allow_main_mode_fallback: bool,
    started_at_utc: str,
) -> dict[str, Any]:
    attempt_id = row["attempt_id"]
    root = attempt_root(repo_root, attempt_id)
    manifest_path = repo_root / row["attempt_manifest_path"]
    tester_config = repo_root / row["tester_config_path"]
    manifest = load_yaml(manifest_path)
    manifest = ensure_feature_columns_transport(
        repo_root=repo_root,
        row=row,
        manifest=manifest,
        tester_config=tester_config,
    )
    manifest = ensure_score_diagnostic_transport(
        manifest=manifest,
        tester_config=tester_config,
        attempt_id=attempt_id,
    )
    ensure_completion_surface_scope(manifest, "full_period_deterministic")
    report_config_summary = normalize_tester_report_config(tester_config, attempt_id)
    portable_terminal_root = terminal.parent if terminal else DEFAULT_TERMINAL.parent
    manifest = ensure_portable_ea_stage(
        repo_root=repo_root,
        tester_config=tester_config,
        portable_terminal_root=portable_terminal_root,
        manifest=manifest,
    )
    manifest.setdefault("artifact_identity", {})["tester_config"] = artifact_ref(tester_config, repo_root)
    write_yaml(manifest_path, manifest)
    telemetry_rel = manifest["artifact_identity"]["telemetry"]["common_relative_path"]
    common_telemetry = common_relative_to_path(telemetry_rel)
    if common_telemetry.exists():
        common_telemetry.unlink()
    diagnostic_rel = manifest["artifact_identity"]["diagnostics"]["score_diagnostics.csv"]["common_relative_path"]
    common_diagnostic = common_relative_to_path(diagnostic_rel)
    if common_diagnostic.exists():
        common_diagnostic.unlink()
    main_data_root = terminal_data_root(repo_root)
    report_directory_summary = prepare_tester_report_directories(
        repo_root=repo_root,
        attempt_root=root,
        tester_config=tester_config,
        portable_terminal_root=portable_terminal_root,
        main_terminal_data_root=main_data_root,
    )

    terminal_summary = run_terminal_sequence(
        terminal=terminal,
        tester_config=tester_config,
        common_telemetry=common_telemetry,
        timeout_seconds=timeout_seconds,
        terminate_existing=terminate_existing,
        allow_main_mode_fallback=allow_main_mode_fallback,
    )
    terminal_summary = normalize_l4_terminal_summary(terminal_summary)
    terminal_summary = {
        **terminal_summary,
        "version": "wave0_l4_terminal_run_summary_v1",
        "summary_path": f"runtime/mt5_attempts/{attempt_id}/terminal_run_summary.yaml",
        "attempt_id": attempt_id,
        "run_id": row["run_id"],
        "bundle_id": row["bundle_id"],
        "tester_config": artifact_ref(tester_config, repo_root),
        "tester_report_config": report_config_summary,
        "tester_report_resolution_prelaunch": public_report_resolution_summary(report_directory_summary),
        "common_telemetry_redacted": redact_path(str(common_telemetry)),
        "common_diagnostic_redacted": redact_path(str(common_diagnostic)),
        "portable_ea_stage": (manifest.get("artifact_identity") or {}).get("portable_runtime_root", {}).get("ea_binary"),
        "claim_boundary": "terminal_execution_evidence_only_no_runtime_authority_no_economics_pass",
    }
    write_yaml(root / "terminal_run_summary.yaml", terminal_summary)

    telemetry_file_observed = common_telemetry.exists()
    telemetry_observed = False
    telemetry_artifact: dict[str, Any] | None = None
    telemetry_summary: dict[str, Any]
    if telemetry_file_observed:
        repo_telemetry = root / "telemetry" / "score_telemetry.csv"
        os.makedirs(filesystem_path(repo_telemetry.parent), exist_ok=True)
        shutil.copy2(common_telemetry, repo_telemetry)
        telemetry_stats = parse_score_telemetry(repo_telemetry)
        telemetry_observed = int(telemetry_stats.get("row_count") or 0) > 0
        telemetry_artifact = artifact_ref(repo_telemetry, repo_root, availability="local_telemetry_hash_recorded_ignored_by_git")
        telemetry_summary = {
            "version": "wave0_l4_score_telemetry_summary_v1",
            "summary_path": f"runtime/mt5_attempts/{attempt_id}/score_telemetry_summary.yaml",
            "attempt_id": attempt_id,
            "run_id": row["run_id"],
            "bundle_id": row["bundle_id"],
            "period_role": row["period_role"],
            "telemetry": telemetry_artifact,
            "common_telemetry_redacted": redact_path(str(common_telemetry)),
            "stats": telemetry_stats,
            "claim_boundary": CLAIM_BOUNDARY,
        }
        if not telemetry_observed:
            telemetry_summary["failure_disposition"] = {
                "reproduction": "MT5 terminal produced a score telemetry CSV with only headers or zero data rows",
                "exact_failing_layer": "mt5_strategy_tester_score_probe_row_generation",
                "bounded_repair_or_fallback_attempt": "thin-first single attempt captured terminal summary and empty CSV for diagnosis before expanding the batch",
                "evidence_path": f"runtime/mt5_attempts/{attempt_id}/score_telemetry_summary.yaml",
                "remaining_blocker": "score telemetry CSV exists but contains no score rows",
                "reopen_condition": "inspect EA journal/report availability, tester date/tick availability, and feature reconstruction before rerun",
            }
            telemetry_summary["claim_boundary"] = "terminal_attempt_empty_score_telemetry_no_l4_completion"
    else:
        telemetry_summary = {
            "version": "wave0_l4_score_telemetry_summary_v1",
            "summary_path": f"runtime/mt5_attempts/{attempt_id}/score_telemetry_summary.yaml",
            "attempt_id": attempt_id,
            "run_id": row["run_id"],
            "bundle_id": row["bundle_id"],
            "period_role": row["period_role"],
            "telemetry": {
                "path": None,
                "availability": "missing_after_terminal_execution",
            },
            "common_telemetry_redacted": redact_path(str(common_telemetry)),
            "stats": {"status": "telemetry_missing", "row_count": 0},
            "failure_disposition": {
                "reproduction": "MT5 terminal was launched with the attempt tester_config.ini",
                "exact_failing_layer": "mt5_strategy_tester_common_file_score_telemetry",
                "bounded_repair_or_fallback_attempt": "portable attempt plus configured main-mode fallback when enabled",
                "evidence_path": f"runtime/mt5_attempts/{attempt_id}/terminal_run_summary.yaml",
                "remaining_blocker": "score telemetry CSV not observed in MT5 Common Files",
                "reopen_condition": "rerun with terminal log inspection, EA journal capture, or explicit terminal cleanup if the terminal process was stale",
            },
            "claim_boundary": "terminal_attempt_no_score_telemetry_no_l4_completion",
        }
    write_yaml(root / "score_telemetry_summary.yaml", telemetry_summary)
    diagnostic_file_observed = common_diagnostic.exists()
    diagnostic_artifact: dict[str, Any] | None = None
    if diagnostic_file_observed:
        repo_diagnostic = root / "telemetry" / "score_diagnostics.csv"
        os.makedirs(filesystem_path(repo_diagnostic.parent), exist_ok=True)
        shutil.copy2(common_diagnostic, repo_diagnostic)
        diagnostic_stats = parse_score_diagnostics(repo_diagnostic)
        diagnostic_artifact = artifact_ref(
            repo_diagnostic,
            repo_root,
            availability="local_diagnostic_hash_recorded_ignored_by_git",
        )
        diagnostic_summary = {
            "version": "wave0_l4_score_diagnostic_summary_v1",
            "summary_path": f"runtime/mt5_attempts/{attempt_id}/score_diagnostic_summary.yaml",
            "attempt_id": attempt_id,
            "run_id": row["run_id"],
            "bundle_id": row["bundle_id"],
            "period_role": row["period_role"],
            "diagnostic": diagnostic_artifact,
            "common_diagnostic_redacted": redact_path(str(common_diagnostic)),
            "stats": diagnostic_stats,
            "claim_boundary": "ea_score_probe_diagnostic_observation_only_no_runtime_authority",
        }
    else:
        diagnostic_summary = {
            "version": "wave0_l4_score_diagnostic_summary_v1",
            "summary_path": f"runtime/mt5_attempts/{attempt_id}/score_diagnostic_summary.yaml",
            "attempt_id": attempt_id,
            "run_id": row["run_id"],
            "bundle_id": row["bundle_id"],
            "period_role": row["period_role"],
            "diagnostic": {
                "path": None,
                "availability": "missing_after_terminal_execution",
            },
            "common_diagnostic_redacted": redact_path(str(common_diagnostic)),
            "stats": {"status": "diagnostic_missing", "event_count": 0, "event_counts": {}},
            "failure_disposition": {
                "reproduction": "MT5 terminal was launched with InpDiagnosticPath configured in tester_config.ini",
                "exact_failing_layer": "mt5_strategy_tester_score_probe_diagnostic_file",
                "bounded_repair_or_fallback_attempt": "runner inserted diagnostic common-file path before terminal launch",
                "evidence_path": f"runtime/mt5_attempts/{attempt_id}/terminal_run_summary.yaml",
                "remaining_blocker": "EA diagnostic CSV was not observed after terminal execution",
                "reopen_condition": "inspect EA init/journal capture or terminal tester attachment before rerun",
            },
            "claim_boundary": "ea_score_probe_diagnostic_missing_no_runtime_authority",
        }
    write_yaml(root / "score_diagnostic_summary.yaml", diagnostic_summary)
    telemetry_summary["diagnostic_evidence"] = {
        "summary_path": diagnostic_summary["summary_path"],
        "status": (diagnostic_summary.get("stats") or {}).get("status"),
        "event_counts": (diagnostic_summary.get("stats") or {}).get("event_counts", {}),
        "claim_boundary": diagnostic_summary["claim_boundary"],
    }
    write_yaml(root / "score_telemetry_summary.yaml", telemetry_summary)
    row_count = ((telemetry_summary.get("stats") or {}).get("row_count")) or 0
    terminal_summary["telemetry_observed"] = telemetry_observed
    terminal_summary["telemetry_file_observed_after_attempt"] = telemetry_file_observed
    terminal_summary["telemetry_rows_observed_after_attempt"] = telemetry_observed
    terminal_summary["telemetry_row_count"] = row_count
    terminal_summary["score_diagnostic_file_observed_after_attempt"] = diagnostic_file_observed
    terminal_summary["score_diagnostic_event_count"] = (diagnostic_summary.get("stats") or {}).get("event_count", 0)
    if telemetry_file_observed and not telemetry_observed:
        terminal_summary["empty_telemetry_claim_effect"] = "csv_header_only_no_l4_score_observation"
    write_yaml(root / "terminal_run_summary.yaml", terminal_summary)

    receipt_path = root / "tester_report_receipt.yaml"
    report_receipt = build_tester_report_receipt_for_attempt(
        repo_root=repo_root,
        attempt_root=root,
        attempt_id=attempt_id,
        tester_config=tester_config,
        portable_terminal_root=portable_terminal_root,
        main_terminal_data_root=main_data_root,
        prelaunch_candidates=report_directory_summary.get("prelaunch_candidates", []),
        launch_started_at_utc=terminal_summary.get("started_at_utc"),
    )
    report = archive_tester_report(
        repo_root,
        root,
        tester_config,
        portable_terminal_root=portable_terminal_root,
        main_terminal_data_root=main_data_root,
    )
    report_observed = bool(report_receipt.get("source_report_sha256"))
    report_completed = tester_report_completed(report_receipt)

    result_judgment = "runtime_probe" if telemetry_observed else "inconclusive"
    terminal_mode_policy = terminal_summary.get("terminal_mode_policy") or {}
    terminal_launched = terminal_launched_from_summary(terminal_summary)
    terminal_mode_label = terminal_mode_from_summary(terminal_summary)
    completion = evaluate_runtime_attempt(
        RuntimeAttemptState(
            terminal_launched=terminal_launched,
            telemetry_file_observed=telemetry_file_observed,
            telemetry_rows_observed=telemetry_observed,
            tester_report_observed=report_observed,
            tester_report_completed=report_completed,
            terminal_mode=terminal_mode_label,
            period_role=row["period_role"],
            period_profile_id=runtime_contract_value(manifest, row, "period_profile_id", "runtime_period_profile_id"),
            runtime_period_set_id=runtime_contract_value(manifest, row, "runtime_period_set_id"),
            execution_profile_id=runtime_contract_value(
                manifest, row, "tester_execution_profile_id", "execution_profile_id"
            ),
            surface_scope=runtime_contract_value(manifest, row, "completion_surface_scope"),
            portable_attempted=terminal_mode_policy.get("portable_attempted"),
            main_mode_fallback_allowed=terminal_mode_policy.get("main_mode_fallback_allowed"),
            main_mode_fallback_used=terminal_mode_policy.get("main_mode_fallback_used"),
        ),
        required_period_roles=["validation", "research_oos"],
        completion_eligible_surface_scopes=["full_period_deterministic", "full_period_sparse_decision_surface"],
    )
    status = runtime_status(completion, telemetry_kind="telemetry")

    manifest["status"] = status
    manifest["claim_boundary"] = CLAIM_BOUNDARY if telemetry_observed else str(telemetry_summary["claim_boundary"])
    manifest["result_judgment"] = result_judgment
    manifest["execution_state"] = {
        "terminal_launched": terminal_launched,
        "telemetry_file_observed": telemetry_file_observed,
        "telemetry_rows_observed": telemetry_observed,
        "tester_report_observed": report_observed,
        "tester_report_completed": report_completed,
        "terminal_mode": terminal_mode_label,
        "portable_contract_satisfied": completion.portable_contract_satisfied,
        "report_contract_satisfied": completion.report_contract_satisfied,
        "period_contract_satisfied": completion.period_contract_satisfied,
        "surface_contract_satisfied": completion.surface_contract_satisfied,
        "runtime_probe_complete": completion.runtime_probe_complete,
        "missing_requirements": list(completion.missing_requirements),
        "completion_claim_boundary": completion.claim_boundary,
    }
    manifest["runtime_probe_routing"] = {
        "primary_family": "runtime_probe",
        "primary_skill": "spacesonar-runtime-parity",
        "support_skills": [
            "spacesonar-run-evidence-system",
            "spacesonar-artifact-lineage",
            "spacesonar-result-judgment",
            "spacesonar-claim-discipline",
        ],
        "routing_scope": "wave0_l4_split_runtime_score_probe_execution",
        "runtime_period_profile_id": "period_profile_split_set_v0",
        "runtime_period_set_id": "split_base_anchor_v0_research_l4",
        "period_role": row["period_role"],
        "claim_boundary": manifest["claim_boundary"],
    }
    manifest["terminal_run_summary"] = terminal_summary
    manifest["score_telemetry_summary"] = telemetry_summary
    manifest["score_diagnostic_summary"] = diagnostic_summary
    manifest["tester_report"] = report
    manifest["tester_report_receipt"] = {
        "path": f"runtime/mt5_attempts/{attempt_id}/tester_report_receipt.yaml",
        "receipt_version": report_receipt.get("receipt_version"),
        "tester_report_completed": report_receipt.get("tester_report_completed"),
        "missing_requirements": report_receipt.get("missing_requirements", []),
        "claim_boundary": report_receipt.get("claim_boundary"),
    }
    manifest.setdefault("artifact_identity", {})["terminal_run_summary"] = artifact_ref(root / "terminal_run_summary.yaml", repo_root)
    manifest["artifact_identity"]["score_telemetry_summary"] = artifact_ref(root / "score_telemetry_summary.yaml", repo_root)
    manifest["artifact_identity"]["score_diagnostic_summary"] = artifact_ref(root / "score_diagnostic_summary.yaml", repo_root)
    manifest["artifact_identity"]["tester_report_receipt"] = ensure_tester_report_receipt_artifact_ref(
        receipt_path,
        report_receipt,
        repo_root,
    )
    if telemetry_artifact:
        manifest["artifact_identity"]["telemetry"]["repo_copy"] = telemetry_artifact
    if diagnostic_artifact:
        manifest["artifact_identity"].setdefault("diagnostics", {})["repo_copy"] = diagnostic_artifact
    manifest["artifact_identity"]["tester_reports"] = [report]
    manifest["missing_evidence"] = []
    if not telemetry_observed:
        manifest["missing_evidence"].append(
            "score_telemetry_rows_missing_after_terminal_execution"
            if telemetry_file_observed
            else "score_telemetry_csv_missing_after_terminal_execution"
        )
    if not diagnostic_file_observed:
        manifest["missing_evidence"].append("score_diagnostic_csv_missing_after_terminal_execution")
    if not report_observed:
        manifest["missing_evidence"].append("tester_report_missing_or_not_archived")
    append_missing_evidence(manifest, list(report_receipt.get("missing_requirements") or []))
    manifest["next_action"] = score_attempt_next_action(completion.runtime_probe_complete)
    parity = manifest.setdefault("proxy_runtime_parity", {})
    parity["minimum_reconciliation_attempt"] = {
        "status": "terminal_score_probe_observed" if telemetry_observed else "terminal_attempted_score_probe_missing",
        "attempt": "MT5 Strategy Tester executed the prepared ONNX score EA against the declared period role",
        "forced_equality_required": False,
        "evidence_path": f"runtime/mt5_attempts/{attempt_id}/score_telemetry_summary.yaml",
    }
    parity["divergence_judgment"] = (
        "runtime_score_telemetry_observed_pending_proxy_row_comparison"
        if telemetry_observed
        else "blocked_runtime_score_telemetry_missing_after_terminal_attempt"
    )
    parity["comparison_class"] = "pending_pair_aggregation_after_L4_period_roles"
    parity["follow_up_action"] = manifest["next_action"]
    update_coverage(
        manifest,
        telemetry_observed=telemetry_observed,
        report_observed=report_observed,
        report_completed=report_completed,
    )
    write_yaml(manifest_path, manifest)

    execution_row = {
        "attempt_id": attempt_id,
        "run_id": row["run_id"],
        "bundle_id": row["bundle_id"],
        "cell_id": row["cell_id"],
        "period_role": row["period_role"],
        "from_date": row["from_date"],
        "to_date": row["to_date"],
        "status": status,
        "result_judgment": result_judgment,
        "telemetry_observed": telemetry_observed,
        "telemetry_row_count": row_count,
        "tester_report_observed": report_observed,
        "runtime_probe_complete": completion.runtime_probe_complete,
        "terminal_mode": terminal_mode_label,
        "terminal_exit_code": terminal_summary.get("exit_code"),
        "terminal_timed_out": terminal_summary.get("timed_out"),
        "terminal_run_summary_path": terminal_summary["summary_path"],
        "score_telemetry_summary_path": telemetry_summary["summary_path"],
        "score_diagnostic_summary_path": diagnostic_summary["summary_path"],
        "repo_telemetry_path": telemetry_artifact["path"] if telemetry_artifact else "",
        "tester_report_path": report.get("path") or "",
        "claim_boundary": manifest["claim_boundary"],
        "next_action": manifest["next_action"],
    }
    return execution_row


def build_summary(
    *,
    repo_root: Path,
    selected_rows: list[dict[str, str]],
    execution_rows: list[dict[str, Any]],
    compile_summary: dict[str, Any],
    started_at_utc: str,
    ended_at_utc: str,
    command_argv: list[str],
) -> dict[str, Any]:
    telemetry_count = sum(bool_text(row.get("telemetry_observed")) for row in execution_rows)
    report_count = sum(bool_text(row.get("tester_report_observed")) for row in execution_rows)
    runtime_complete_count = sum(bool_text(row.get("runtime_probe_complete")) for row in execution_rows)
    prepared_rows = read_csv_rows(repo_root / PREP_INDEX)
    executed_attempt_ids = {row["attempt_id"] for row in execution_rows}
    touched_manifest_count = 0
    missing_requirements_by_count: Counter[str] = Counter()
    for row in prepared_rows:
        manifest_path = repo_root / row["attempt_manifest_path"]
        if manifest_path.exists():
            manifest = load_yaml(manifest_path)
            if manifest.get("execution_state"):
                touched_manifest_count += 1
                for requirement in manifest.get("execution_state", {}).get("missing_requirements", []):
                    missing_requirements_by_count[str(requirement)] += 1
    all_attempts_touched = touched_manifest_count >= len(prepared_rows)
    all_attempts_runtime_complete = all_attempts_touched and runtime_complete_count == len(prepared_rows)
    return {
        "version": "wave0_l4_runtime_execution_summary_v1",
        "summary_id": "wave0_l4_runtime_execution_summary_v0",
        "work_item_id": WORK_ITEM_ID,
        "subwork_item_id": SUBWORK_ID,
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "sweep_id": SWEEP_ID,
        "created_at_utc": started_at_utc,
        "ended_at_utc": ended_at_utc,
        "status": ALL_ATTEMPTS_STATUS if all_attempts_touched else PARTIAL_STATUS,
        "claim_boundary": "l4_runtime_execution_progress_only_no_runtime_authority_no_economics_pass_no_candidate",
        "runtime_contract_binding": {
            "required_runtime_level": "L4_split_runtime_probe",
            "period_profile_id": "period_profile_split_set_v0",
            "runtime_period_set_id": "split_base_anchor_v0_research_l4",
            "required_period_roles": ["validation", "research_oos"],
            "tester_execution_profile_id": "us100_m5_fpmarkets_tester_execution_v0",
            "locked_final_oos_b": "excluded_forbidden_by_default",
        },
        "counts": {
            "prepared_attempt_count": len(prepared_rows),
            "selected_attempt_count": len(selected_rows),
            "indexed_execution_count": len(execution_rows),
            "executed_attempt_count": len(execution_rows),
            "completed_manifest_count": runtime_complete_count,
            "touched_manifest_count": touched_manifest_count,
            "telemetry_observed_count": telemetry_count,
            "telemetry_missing_count": len(execution_rows) - telemetry_count,
            "tester_report_observed_count": report_count,
            "tester_report_missing_count": len(execution_rows) - report_count,
            "terminal_execution_count": len(execution_rows),
            "telemetry_observation_count": telemetry_count,
            "tester_report_observation_count": report_count,
            "portable_contract_count": sum(str(row.get("terminal_mode")) == "portable_contract_attempt" for row in execution_rows),
            "runtime_probe_complete_count": runtime_complete_count,
            "runtime_probe_incomplete_count": len(execution_rows) - runtime_complete_count,
            "period_role_counts": dict(sorted(Counter(row["period_role"] for row in execution_rows).items())),
            "status_counts": dict(sorted(Counter(row["status"] for row in execution_rows).items())),
            "result_judgment_counts": dict(sorted(Counter(row["result_judgment"] for row in execution_rows).items())),
        },
        "runtime_completion": {
            "all_prepared_attempts_executed": all_attempts_touched,
            "all_prepared_attempts_runtime_complete": all_attempts_runtime_complete,
            "runtime_probe_complete": all_attempts_runtime_complete,
            "missing_requirements_by_count": dict(sorted(missing_requirements_by_count.items())),
        },
        "compile_summary": {
            "path": compile_summary["summary_path"],
            "status": compile_summary["status"],
            "compile_attempted": compile_summary["compile_attempted"],
            "ea_binary": compile_summary["ea_binary"],
        },
        "artifact_outputs": {
            "runtime_execution_summary": RUNTIME_SUMMARY.as_posix(),
            "runtime_execution_index": RUNTIME_INDEX.as_posix(),
            "attempt_terminal_summaries": [row["terminal_run_summary_path"] for row in execution_rows],
            "attempt_score_telemetry_summaries": [row["score_telemetry_summary_path"] for row in execution_rows],
        },
        "environment": {
            "command_argv": command_argv,
            "cwd": ".",
            "python_executable": redact_path(sys.executable),
            "python_version": sys.version.split()[0],
            "dependency_summary": dependency_summary(),
            "started_at_utc": started_at_utc,
            "ended_at_utc": ended_at_utc,
            **current_git_identity(repo_root),
        },
        "judgment": {
            "judgment_class": "runtime_probe_progress",
            "runtime_probe_completed_for_all_prepared_attempts": all_attempts_runtime_complete,
            "all_prepared_attempts_executed": all_attempts_touched,
            "runtime_authority": False,
            "economics_pass": False,
            "selected_baseline": False,
            "goal_achieve": False,
            "next_action": (
                "aggregate paired validation/research_oos L4 telemetry and decide L5 routing"
                if all_attempts_runtime_complete
                else "repair or rerun MT5 report-backed portable L4 contract before L5 routing"
                if all_attempts_touched
                else "continue running remaining prepared L4 Strategy Tester attempts"
            ),
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


def merge_execution_rows(repo_root: Path, new_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_attempt: dict[str, dict[str, Any]] = {}
    index_path = repo_root / RUNTIME_INDEX
    if index_path.exists():
        for row in read_csv_rows(index_path):
            if row.get("attempt_id"):
                by_attempt[row["attempt_id"]] = dict(row)
    for row in new_rows:
        by_attempt[str(row["attempt_id"])] = dict(row)
    prep_rows = read_csv_rows(repo_root / PREP_INDEX)
    ordered: list[dict[str, Any]] = []
    for prep in prep_rows:
        attempt_id = prep["attempt_id"]
        if attempt_id in by_attempt:
            projected = execution_row_from_manifest(repo_root, prep, by_attempt[attempt_id])
            ordered.append(projected or by_attempt[attempt_id])
        else:
            projected = execution_row_from_manifest(repo_root, prep)
            if projected:
                ordered.append(projected)
    extras = [row for attempt_id, row in sorted(by_attempt.items()) if attempt_id not in {prep["attempt_id"] for prep in prep_rows}]
    return [*ordered, *extras]


def build_closeout(summary: dict[str, Any]) -> dict[str, Any]:
    missing = ["remaining_prepared_L4_attempts"] if summary["status"] == PARTIAL_STATUS else []
    if not (summary.get("runtime_completion") or {}).get("runtime_probe_complete"):
        missing.append("standard_l4_runtime_completion_contract")
    if summary["counts"].get("tester_report_observed_count") == 0:
        missing.append("tester_report_hash_or_report_export_adapter_for_economics_claim")
    return {
        "version": "work_closeout_v1",
        "work_item_id": SUBWORK_ID,
        "parent_work_item_id": WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "closed_at_utc": summary["ended_at_utc"],
        "result_judgment": "runtime_probe" if summary["counts"]["telemetry_observed_count"] else "inconclusive",
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [
            RUNTIME_SUMMARY.as_posix(),
            RUNTIME_INDEX.as_posix(),
            summary["compile_summary"]["path"],
        ],
        "required_gate_coverage": {
            "passed": [
                "mt5_runtime_probe_contract_audit",
                "runtime_surface_contract",
                "terminal_execution_attempt_record",
                "result_judgment",
                "final_claim_guard",
            ],
            "missing": missing,
            "not_applicable": [
                "runtime_authority",
                "economics_pass",
                "selected_baseline",
                "goal_achieve",
            ],
        },
        "next_action": summary["judgment"]["next_action"],
        "forbidden_claims_respected": True,
    }


def upsert_artifact_registry(repo_root: Path, summary: dict[str, Any], execution_rows: list[dict[str, Any]]) -> None:
    registry_path = repo_root / ARTIFACT_REGISTRY
    rows = read_csv_rows(registry_path)
    fieldnames = list(rows[0].keys()) if rows else [
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
    producer = " ".join(summary["environment"]["command_argv"])
    regen = producer

    def put(row: dict[str, Any]) -> None:
        path_value = row.get("path_or_uri")
        full = repo_root / path_value if path_value else None
        if full and full.exists():
            row["sha256"] = sha256(full)
            row["size_bytes"] = str(full.stat().st_size)
        by_id[row["artifact_id"]] = {key: str(row.get(key, "")) for key in fieldnames}

    put(
        {
            "artifact_id": "artifact_wave0_l4_runtime_execution_summary_v0",
            "artifact_type": "l4_runtime_execution_summary",
            "path_or_uri": RUNTIME_SUMMARY.as_posix(),
            "availability": "present_hash_recorded",
            "producer_command": producer,
            "regeneration_command": regen,
            "source_of_truth": RUNTIME_SUMMARY.as_posix(),
            "consumer": WORK_ITEM_ID,
            "claim_boundary": summary["claim_boundary"],
            "notes": "runtime execution progress summary; no runtime authority or economics pass",
        }
    )
    put(
        {
            "artifact_id": "artifact_wave0_l4_runtime_execution_index_v0",
            "artifact_type": "l4_runtime_execution_index",
            "path_or_uri": RUNTIME_INDEX.as_posix(),
            "availability": "present_hash_recorded",
            "producer_command": producer,
            "regeneration_command": regen,
            "source_of_truth": RUNTIME_SUMMARY.as_posix(),
            "consumer": WORK_ITEM_ID,
            "claim_boundary": summary["claim_boundary"],
            "notes": "index of attempted L4 terminal executions",
        }
    )
    for item in [summary["compile_summary"]["path"]]:
        put(
            {
                "artifact_id": "artifact_wave0_l4_runtime_compile_summary_v0",
                "artifact_type": "l4_runtime_compile_summary",
                "path_or_uri": item,
                "availability": "present_hash_recorded",
                "producer_command": producer,
                "regeneration_command": regen,
                "source_of_truth": RUNTIME_SUMMARY.as_posix(),
                "consumer": WORK_ITEM_ID,
                "claim_boundary": "ea_compile_or_binary_preflight_only_not_strategy_tester_output",
                "notes": "EA binary availability check for runtime execution",
            }
        )
    put(
        {
            "artifact_id": "artifact_wave0_l4_score_probe_ea_source_v0",
            "artifact_type": "mt5_ea_source",
            "path_or_uri": EA_SOURCE.as_posix(),
            "availability": "present_hash_recorded",
            "producer_command": producer,
            "regeneration_command": regen,
            "source_of_truth": EA_SOURCE.as_posix(),
            "consumer": WORK_ITEM_ID,
            "claim_boundary": "ea_source_runtime_probe_adapter_only_no_runtime_authority",
            "notes": "non-trading L4 score telemetry probe source; hash refreshed after runtime adapter repair",
        }
    )
    if (repo_root / EA_BINARY).exists():
        put(
            {
                "artifact_id": "artifact_wave0_l4_score_probe_ea_binary_v0",
                "artifact_type": "mt5_ea_binary",
                "path_or_uri": EA_BINARY.as_posix(),
                "availability": "local_binary_hash_recorded_ignored_by_git",
                "producer_command": producer,
                "regeneration_command": "compile with MetaEditor64 /portable /compile:<path>",
                "source_of_truth": EA_SOURCE.as_posix(),
                "consumer": WORK_ITEM_ID,
                "claim_boundary": "ea_compile_or_binary_preflight_only_not_strategy_tester_output",
                "notes": "compiled EA binary hash; local ignored artifact",
            }
        )
    for row in execution_rows:
        put(
            {
                "artifact_id": f"artifact_{row['attempt_id']}_tester_config_v0",
                "run_id": row["run_id"],
                "bundle_id": row["bundle_id"],
                "attempt_id": row["attempt_id"],
                "artifact_type": "tester_config",
                "path_or_uri": f"runtime/mt5_attempts/{row['attempt_id']}/tester_config.ini",
                "availability": "present_hash_recorded",
                "producer_command": producer,
                "regeneration_command": regen,
                "source_of_truth": f"runtime/mt5_attempts/{row['attempt_id']}/attempt_manifest.yaml",
                "consumer": WORK_ITEM_ID,
                "claim_boundary": row["claim_boundary"],
                "notes": "tester config hash refreshed after runtime feature-column transport patch",
            }
        )
        put(
            {
                "artifact_id": f"artifact_{row['attempt_id']}_manifest_v0",
                "run_id": row["run_id"],
                "bundle_id": row["bundle_id"],
                "attempt_id": row["attempt_id"],
                "artifact_type": "attempt_manifest",
                "path_or_uri": f"runtime/mt5_attempts/{row['attempt_id']}/attempt_manifest.yaml",
                "availability": "present_hash_recorded",
                "producer_command": producer,
                "regeneration_command": regen,
                "source_of_truth": f"runtime/mt5_attempts/{row['attempt_id']}/attempt_manifest.yaml",
                "consumer": WORK_ITEM_ID,
                "claim_boundary": row["claim_boundary"],
                "notes": "attempt manifest updated with L4 runtime execution evidence",
            }
        )
        for suffix, artifact_type, path, availability, note in [
            ("terminal_summary", "terminal_run_summary", row["terminal_run_summary_path"], "present_hash_recorded", "terminal launch and mode evidence"),
            (
                "score_telemetry_summary",
                "score_telemetry_summary",
                row["score_telemetry_summary_path"],
                "present_hash_recorded",
                "summary of local score telemetry",
            ),
            (
                "score_diagnostic_summary",
                "score_diagnostic_summary",
                row.get("score_diagnostic_summary_path") or f"runtime/mt5_attempts/{row['attempt_id']}/score_diagnostic_summary.yaml",
                "present_hash_recorded",
                "EA score-probe diagnostic summary; observation only, not runtime authority",
            ),
        ]:
            artifact_claim_boundary = (
                "ea_score_probe_diagnostic_observation_only_no_runtime_authority"
                if suffix == "score_diagnostic_summary"
                else row["claim_boundary"]
            )
            put(
                {
                    "artifact_id": f"artifact_{row['attempt_id']}_{suffix}_v0",
                    "run_id": row["run_id"],
                    "bundle_id": row["bundle_id"],
                    "attempt_id": row["attempt_id"],
                    "artifact_type": artifact_type,
                    "path_or_uri": path,
                    "availability": availability,
                    "producer_command": producer,
                    "regeneration_command": regen,
                    "source_of_truth": f"runtime/mt5_attempts/{row['attempt_id']}/attempt_manifest.yaml",
                    "consumer": WORK_ITEM_ID,
                    "claim_boundary": artifact_claim_boundary,
                    "notes": note,
                }
            )
        if row.get("repo_telemetry_path"):
            put(
                {
                    "artifact_id": f"artifact_{row['attempt_id']}_score_telemetry_csv_v0",
                    "run_id": row["run_id"],
                    "bundle_id": row["bundle_id"],
                    "attempt_id": row["attempt_id"],
                    "artifact_type": "score_telemetry_csv",
                    "path_or_uri": row["repo_telemetry_path"],
                    "availability": "local_telemetry_hash_recorded_ignored_by_git",
                    "producer_command": producer,
                    "regeneration_command": regen,
                    "source_of_truth": f"runtime/mt5_attempts/{row['attempt_id']}/score_telemetry_summary.yaml",
                    "consumer": WORK_ITEM_ID,
                    "claim_boundary": row["claim_boundary"],
                    "notes": "raw telemetry is local/generated and ignored; summary is committed",
                }
            )
        else:
            by_id.pop(f"artifact_{row['attempt_id']}_score_telemetry_csv_v0", None)
        diagnostic_csv = f"runtime/mt5_attempts/{row['attempt_id']}/telemetry/score_diagnostics.csv"
        if (repo_root / diagnostic_csv).exists():
            put(
                {
                    "artifact_id": f"artifact_{row['attempt_id']}_score_diagnostics_csv_v0",
                    "run_id": row["run_id"],
                    "bundle_id": row["bundle_id"],
                    "attempt_id": row["attempt_id"],
                    "artifact_type": "score_diagnostics_csv",
                    "path_or_uri": diagnostic_csv,
                    "availability": "local_diagnostic_hash_recorded_ignored_by_git",
                    "producer_command": producer,
                    "regeneration_command": regen,
                    "source_of_truth": f"runtime/mt5_attempts/{row['attempt_id']}/score_diagnostic_summary.yaml",
                    "consumer": WORK_ITEM_ID,
                    "claim_boundary": "ea_score_probe_diagnostic_observation_only_no_runtime_authority",
                    "notes": "raw EA diagnostic events are local/generated and ignored; summary is committed",
                }
            )
        else:
            by_id.pop(f"artifact_{row['attempt_id']}_score_diagnostics_csv_v0", None)
        if row.get("tester_report_path"):
            put(
                {
                    "artifact_id": f"artifact_{row['attempt_id']}_tester_report_v0",
                    "run_id": row["run_id"],
                    "bundle_id": row["bundle_id"],
                    "attempt_id": row["attempt_id"],
                    "artifact_type": "tester_report",
                    "path_or_uri": row["tester_report_path"],
                    "availability": "local_report_hash_recorded_ignored_by_git",
                    "producer_command": producer,
                    "regeneration_command": regen,
                    "source_of_truth": f"runtime/mt5_attempts/{row['attempt_id']}/attempt_manifest.yaml",
                    "consumer": WORK_ITEM_ID,
                    "claim_boundary": "tester_report_local_evidence_only_no_economics_pass",
                    "notes": "raw tester report is generated/local; summary remains source for git",
                }
            )
        else:
            by_id.pop(f"artifact_{row['attempt_id']}_tester_report_v0", None)
    write_csv(registry_path, list(by_id.values()), fieldnames)


def update_control_records(repo_root: Path, summary: dict[str, Any]) -> None:
    next_work = load_yaml(repo_root / NEXT_WORK_ITEM)
    current_truth = next_work.setdefault("current_truth", {})
    current_truth["l4_runtime_execution_summary"] = RUNTIME_SUMMARY.as_posix()
    current_truth["l4_runtime_execution_status"] = summary["status"]
    current_truth["l4_runtime_execution_counts"] = summary["counts"]
    next_work["status"] = "l4_strategy_tester_execution_in_progress" if summary["status"] == PARTIAL_STATUS else "l4_strategy_tester_execution_completed_for_prepared_attempts"
    next_work["missing_material_if_relevant"] = (
        ["remaining_prepared_L4_attempts"] if summary["status"] == PARTIAL_STATUS else ["paired_L4_period_aggregation_pending"]
    )
    next_work["next_action"] = summary["judgment"]["next_action"]
    write_yaml(repo_root / NEXT_WORK_ITEM, next_work)

    resume = load_yaml(repo_root / RESUME_CURSOR)
    resume["updated_at_utc"] = summary["ended_at_utc"]
    sources = resume.setdefault("current_truth_sources", [])
    for source in [RUNTIME_SUMMARY.as_posix(), RUNTIME_INDEX.as_posix()]:
        if source not in sources:
            sources.append(source)
    resume["latest_completed_work"] = {
        "work_item_id": SUBWORK_ID,
        "result_judgment": "runtime_probe" if summary["counts"]["telemetry_observed_count"] else "inconclusive",
        "claim_boundary": summary["claim_boundary"],
        "evidence_paths": [RUNTIME_SUMMARY.as_posix(), CLOSEOUT_PATH.as_posix()],
    }
    resume["next_work_item"] = {"work_item_id": WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()}
    write_yaml(repo_root / RESUME_CURSOR, resume)

    goal = load_yaml(repo_root / GOAL_MANIFEST)
    goal["updated_at_utc"] = summary["ended_at_utc"]
    goal["active_phase"] = "wave01_operating_proof_window_l4_terminal_execution_in_progress"
    wave_spec = goal.setdefault("program_budgets", {}).setdefault("current_wave0_spec", {})
    wave_spec["l4_runtime_execution_summary"] = RUNTIME_SUMMARY.as_posix()
    wave_spec["l4_runtime_execution_status"] = summary["status"]
    wave_spec["l4_runtime_execution_counts"] = summary["counts"]
    write_yaml(repo_root / GOAL_MANIFEST, goal)

    workspace = load_yaml(repo_root / WORKSPACE_STATE)
    workspace["updated_utc"] = summary["ended_at_utc"]
    claims = workspace.setdefault("current_claims", {})
    claims["wave0_l4_runtime_execution_summary"] = RUNTIME_SUMMARY.as_posix()
    claims["wave0_l4_runtime_execution_status"] = summary["status"]
    claims["wave0_l4_runtime_execution_counts"] = summary["counts"]
    claims["active_goal_phase"] = "wave01_operating_proof_window_l4_terminal_execution_in_progress"
    write_yaml(repo_root / WORKSPACE_STATE, workspace)

    goal_registry = repo_root / GOAL_REGISTRY
    if goal_registry.exists():
        goal_rows = read_csv_rows(goal_registry)
        for row in goal_rows:
            if row.get("goal_id") == GOAL_ID:
                row["active_phase"] = "wave01_operating_proof_window_l4_terminal_execution_in_progress"
                row["next_work_item"] = WORK_ITEM_ID
        write_csv(goal_registry, goal_rows, list(goal_rows[0].keys()) if goal_rows else [])


def write_execution_records(
    *,
    repo_root: Path,
    summary: dict[str, Any],
    execution_rows: list[dict[str, Any]],
    write_control_records: bool,
) -> None:
    write_yaml(repo_root / RUNTIME_SUMMARY, summary)
    write_csv(repo_root / RUNTIME_INDEX, execution_rows, execution_index_fieldnames())
    write_yaml(repo_root / CLOSEOUT_PATH, build_closeout(summary))
    upsert_artifact_registry(repo_root, summary, execution_rows)
    if write_control_records:
        update_control_records(repo_root, summary)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run prepared Wave0/Wave01 L4 MT5 Strategy Tester attempts.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--attempt-id", action="append", default=[])
    parser.add_argument("--period-role", action="append", choices=["validation", "research_oos"], default=[])
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--include-completed", action="store_true")
    parser.add_argument("--terminal", default=str(DEFAULT_TERMINAL))
    parser.add_argument("--metaeditor", default=str(DEFAULT_METAEDITOR))
    parser.add_argument("--terminal-timeout-seconds", type=int, default=1200)
    parser.add_argument("--compile-timeout-seconds", type=int, default=120)
    parser.add_argument("--force-compile-ea", action="store_true")
    parser.add_argument("--skip-compile-ea-if-missing", action="store_true")
    parser.add_argument("--terminate-existing-terminal", action="store_true")
    parser.add_argument("--allow-main-mode-fallback", action="store_true")
    parser.add_argument("--no-main-mode-fallback", action="store_true")
    parser.add_argument("--write-control-records", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(*_args: object, **_kwargs: object) -> int:
    from foundation.pipelines.historical_lifecycle_guard import disabled_lifecycle_entrypoint

    return disabled_lifecycle_entrypoint(
        "a run-local/domain evidence command plus locked spacesonar lifecycle transaction for canonical state updates"
    )


if __name__ == "__main__":
    raise SystemExit(main())
