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


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
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


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle)


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.dump(payload, handle, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=False)


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
    with path.open("r", encoding="utf-8-sig") as handle:
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
        if manifest_path.exists():
            manifest_status = str(load_yaml(manifest_path).get("status", manifest_status))
        if not include_completed and manifest_status.startswith("completed_"):
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
        "terminal_mode",
        "terminal_exit_code",
        "terminal_timed_out",
        "terminal_run_summary_path",
        "score_telemetry_summary_path",
        "repo_telemetry_path",
        "tester_report_path",
        "claim_boundary",
        "next_action",
    ]


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
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.strip().lower().startswith("report="):
            return line.split("=", 1)[1].strip()
    return None


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


def feature_columns_common_relative(bundle_id: str) -> str:
    return f"{COMMON_REL_ROOT}\\{bundle_id}\\feature_columns.txt"


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
    common_path.parent.mkdir(parents=True, exist_ok=True)
    common_path.write_text(columns_text, encoding="utf-8")

    config_text = tester_config.read_text(encoding="utf-8-sig")
    updated = upsert_ini_line(
        config_text,
        "InpFeatureColumnsPath",
        common_relative,
        after_key="InpFeatureColumns",
    )
    if updated != config_text:
        tester_config.write_text(updated, encoding="utf-8")

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


def candidate_report_paths(repo_root: Path, attempt_root: Path, tester_config: Path) -> list[Path]:
    candidates: list[Path] = []
    stem = parse_tester_config_report_stem(tester_config)
    if stem:
        normalized = stem.replace("\\", "/")
        stem_path = Path(normalized)
        parts = list(stem_path.parts)
        if parts and parts[0] == repo_root.name:
            base = repo_root.joinpath(*parts[1:])
        else:
            base = repo_root / stem_path
        candidates.extend([base.with_suffix(suffix) for suffix in [".htm", ".html", ".xml"]])
    candidates.extend(attempt_root.glob("tester_report*"))
    return list(dict.fromkeys(path for path in candidates if path.exists()))


def archive_tester_report(repo_root: Path, attempt_root: Path, tester_config: Path) -> dict[str, Any]:
    candidates = candidate_report_paths(repo_root, attempt_root, tester_config)
    if not candidates:
        return {
            "observed": False,
            "status": "tester_report_missing_after_terminal_execution",
            "path": None,
            "claim_boundary": "missing_report_no_economics_or_completion_claim",
        }
    report = candidates[0].resolve()
    attempt_resolved = attempt_root.resolve()
    if not report.is_relative_to(attempt_resolved):
        return {
            "observed": True,
            "status": "tester_report_observed_outside_attempt_root",
            "redacted_path": redact_path(str(report)),
            "claim_boundary": "local_context_only_report_not_archived",
        }
    reports_dir = attempt_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    archived = reports_dir / report.name
    if report.resolve() != archived.resolve():
        shutil.move(str(report), str(archived))
    return {
        "observed": True,
        "status": "tester_report_archived_local_hash_recorded",
        **artifact_ref(archived, repo_root, availability="local_report_hash_recorded_ignored_by_git"),
        "claim_boundary": "tester_report_local_evidence_only_no_economics_pass",
    }


def parse_score_telemetry(path: Path) -> dict[str, Any]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
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


def update_coverage(manifest: dict[str, Any], *, telemetry_observed: bool, report_observed: bool) -> None:
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
    if report_observed:
        mark_passed("L4_period_role_completed_report")
        mark_passed("tester_report_hash")
    else:
        mark_missing("L4_period_role_completed_report")
        mark_missing("tester_report_hash")


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
    write_yaml(manifest_path, manifest)
    telemetry_rel = manifest["artifact_identity"]["telemetry"]["common_relative_path"]
    common_telemetry = common_relative_to_path(telemetry_rel)
    if common_telemetry.exists():
        common_telemetry.unlink()

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
        "common_telemetry_redacted": redact_path(str(common_telemetry)),
        "claim_boundary": "terminal_execution_evidence_only_no_runtime_authority_no_economics_pass",
    }
    write_yaml(root / "terminal_run_summary.yaml", terminal_summary)

    telemetry_file_observed = common_telemetry.exists()
    telemetry_observed = False
    telemetry_artifact: dict[str, Any] | None = None
    telemetry_summary: dict[str, Any]
    if telemetry_file_observed:
        repo_telemetry = root / "telemetry" / "score_telemetry.csv"
        repo_telemetry.parent.mkdir(parents=True, exist_ok=True)
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
    row_count = ((telemetry_summary.get("stats") or {}).get("row_count")) or 0
    terminal_summary["telemetry_observed"] = telemetry_observed
    terminal_summary["telemetry_file_observed_after_attempt"] = telemetry_file_observed
    terminal_summary["telemetry_rows_observed_after_attempt"] = telemetry_observed
    terminal_summary["telemetry_row_count"] = row_count
    if telemetry_file_observed and not telemetry_observed:
        terminal_summary["empty_telemetry_claim_effect"] = "csv_header_only_no_l4_score_observation"
    write_yaml(root / "terminal_run_summary.yaml", terminal_summary)

    report = archive_tester_report(repo_root, root, tester_config)
    report_observed = bool(report.get("observed"))

    result_judgment = "runtime_probe" if telemetry_observed else "inconclusive"
    status = (
        "completed_l4_score_telemetry_observed"
        if telemetry_observed
        else ("terminal_executed_empty_score_telemetry" if telemetry_file_observed else "terminal_executed_telemetry_missing")
    )
    terminal_mode = (terminal_summary.get("terminal_mode_policy") or {}).get("main_mode_fallback_used")
    terminal_mode_label = "main_mode_config_fallback" if terminal_mode else "portable_contract_attempt"

    manifest["status"] = status
    manifest["claim_boundary"] = CLAIM_BOUNDARY if telemetry_observed else str(telemetry_summary["claim_boundary"])
    manifest["result_judgment"] = result_judgment
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
    manifest["tester_report"] = report
    manifest.setdefault("artifact_identity", {})["terminal_run_summary"] = artifact_ref(root / "terminal_run_summary.yaml", repo_root)
    manifest["artifact_identity"]["score_telemetry_summary"] = artifact_ref(root / "score_telemetry_summary.yaml", repo_root)
    if telemetry_artifact:
        manifest["artifact_identity"]["telemetry"]["repo_copy"] = telemetry_artifact
    manifest["artifact_identity"]["tester_reports"] = [report]
    manifest["missing_evidence"] = []
    if not telemetry_observed:
        manifest["missing_evidence"].append(
            "score_telemetry_rows_missing_after_terminal_execution"
            if telemetry_file_observed
            else "score_telemetry_csv_missing_after_terminal_execution"
        )
    if not report_observed:
        manifest["missing_evidence"].append("tester_report_missing_or_not_archived")
    manifest["next_action"] = (
        "aggregate this period role with its paired L4 attempt before L5 decision"
        if telemetry_observed
        else "inspect terminal/EA logs and rerun this attempt before L4 completion claim"
    )
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
    update_coverage(manifest, telemetry_observed=telemetry_observed, report_observed=report_observed)
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
        "terminal_mode": terminal_mode_label,
        "terminal_exit_code": terminal_summary.get("exit_code"),
        "terminal_timed_out": terminal_summary.get("timed_out"),
        "terminal_run_summary_path": terminal_summary["summary_path"],
        "score_telemetry_summary_path": telemetry_summary["summary_path"],
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
    telemetry_count = sum(str(row.get("telemetry_observed")).lower() == "true" for row in execution_rows)
    report_count = sum(str(row.get("tester_report_observed")).lower() == "true" for row in execution_rows)
    prepared_rows = read_csv_rows(repo_root / PREP_INDEX)
    executed_attempt_ids = {row["attempt_id"] for row in execution_rows}
    completed_manifest_count = 0
    for row in prepared_rows:
        manifest_path = repo_root / row["attempt_manifest_path"]
        if manifest_path.exists() and str(load_yaml(manifest_path).get("status", "")).startswith("completed_"):
            completed_manifest_count += 1
    all_attempts_touched = completed_manifest_count >= len(prepared_rows)
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
            "completed_manifest_count": completed_manifest_count,
            "telemetry_observed_count": telemetry_count,
            "telemetry_missing_count": len(execution_rows) - telemetry_count,
            "tester_report_observed_count": report_count,
            "tester_report_missing_count": len(execution_rows) - report_count,
            "period_role_counts": dict(sorted(Counter(row["period_role"] for row in execution_rows).items())),
            "status_counts": dict(sorted(Counter(row["status"] for row in execution_rows).items())),
            "result_judgment_counts": dict(sorted(Counter(row["result_judgment"] for row in execution_rows).items())),
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
            "runtime_probe_completed_for_all_prepared_attempts": all_attempts_touched,
            "runtime_authority": False,
            "economics_pass": False,
            "selected_baseline": False,
            "goal_achieve": False,
            "next_action": (
                "aggregate paired validation/research_oos L4 telemetry and decide L5 routing"
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
            ordered.append(by_attempt[attempt_id])
    extras = [row for attempt_id, row in sorted(by_attempt.items()) if attempt_id not in {prep["attempt_id"] for prep in prep_rows}]
    return [*ordered, *extras]


def build_closeout(summary: dict[str, Any]) -> dict[str, Any]:
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
            "missing": ["remaining_prepared_L4_attempts"] if summary["status"] == PARTIAL_STATUS else [],
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
        ]:
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
                    "claim_boundary": row["claim_boundary"],
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
    parser.add_argument("--no-main-mode-fallback", action="store_true")
    parser.add_argument("--write-control-records", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    started_at = utc_now()
    command_argv = ["python", "foundation/pipelines/run_wave0_l4_mt5_attempts.py"]
    for attempt_id in args.attempt_id:
        command_argv.extend(["--attempt-id", attempt_id])
    for period_role in args.period_role:
        command_argv.extend(["--period-role", period_role])
    command_argv.extend(["--limit", str(args.limit)])
    if args.include_completed:
        command_argv.append("--include-completed")
    if args.force_compile_ea:
        command_argv.append("--force-compile-ea")
    if args.skip_compile_ea_if_missing:
        command_argv.append("--skip-compile-ea-if-missing")
    if args.terminate_existing_terminal:
        command_argv.append("--terminate-existing-terminal")
    if args.no_main_mode_fallback:
        command_argv.append("--no-main-mode-fallback")
    if args.write_control_records:
        command_argv.append("--write-control-records")
    if args.dry_run:
        command_argv.append("--dry-run")

    rows = read_csv_rows(repo_root / PREP_INDEX)
    selected = selected_attempt_rows(
        rows,
        repo_root=repo_root,
        attempt_ids=set(args.attempt_id) if args.attempt_id else None,
        period_roles=set(args.period_role) if args.period_role else None,
        limit=args.limit if args.limit > 0 else None,
        include_completed=args.include_completed,
    )
    if args.dry_run:
        print(json.dumps({"status": "dry_run", "selected_attempt_ids": [row["attempt_id"] for row in selected]}, indent=2))
        return 0
    compile_summary = ensure_ea_binary(
        repo_root=repo_root,
        metaeditor=Path(args.metaeditor),
        force_compile=args.force_compile_ea,
        skip_compile_if_missing=args.skip_compile_ea_if_missing,
        timeout_seconds=args.compile_timeout_seconds,
        started_at_utc=started_at,
    )
    if not (repo_root / EA_BINARY).exists():
        ended_at = utc_now()
        summary = build_summary(
            repo_root=repo_root,
            selected_rows=selected,
            execution_rows=[],
            compile_summary=compile_summary,
            started_at_utc=started_at,
            ended_at_utc=ended_at,
            command_argv=command_argv,
        )
        summary["status"] = "blocked_ea_binary_missing_after_compile_preflight"
        summary["failure_disposition"] = compile_summary.get("failure_disposition")
        write_execution_records(repo_root=repo_root, summary=summary, execution_rows=[], write_control_records=args.write_control_records)
        print(json.dumps({"status": summary["status"], "summary": RUNTIME_SUMMARY.as_posix()}, indent=2))
        return 1

    execution_rows: list[dict[str, Any]] = []
    for row in selected:
        execution_rows.append(
            run_one_attempt(
                repo_root=repo_root,
                row=row,
                terminal=Path(args.terminal),
                timeout_seconds=args.terminal_timeout_seconds,
                terminate_existing=args.terminate_existing_terminal,
                allow_main_mode_fallback=not args.no_main_mode_fallback,
                started_at_utc=started_at,
            )
        )

    ended_at = utc_now()
    merged_rows = merge_execution_rows(repo_root, execution_rows)
    summary = build_summary(
        repo_root=repo_root,
        selected_rows=selected,
        execution_rows=merged_rows,
        compile_summary=compile_summary,
        started_at_utc=started_at,
        ended_at_utc=ended_at,
        command_argv=command_argv,
    )
    write_execution_records(
        repo_root=repo_root,
        summary=summary,
        execution_rows=merged_rows,
        write_control_records=args.write_control_records,
    )
    print(
        json.dumps(
            {
                "status": summary["status"],
                "summary": RUNTIME_SUMMARY.as_posix(),
                "current_batch_executed_attempt_count": len(execution_rows),
                "indexed_execution_count": len(merged_rows),
                "telemetry_observed_count": summary["counts"]["telemetry_observed_count"],
                "claim_boundary": summary["claim_boundary"],
            },
            indent=2,
        )
    )
    return 0 if all(row["telemetry_observed"] for row in execution_rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
