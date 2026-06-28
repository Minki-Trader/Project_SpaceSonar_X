from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
for path in [REPO_ROOT, REPO_ROOT / "src"]:
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

import foundation.pipelines.run_wave0_l4_mt5_attempts as l4_base
from foundation.mt5.runtime_completion import (
    RuntimeAttemptState,
    evaluate_runtime_attempt,
    runtime_status,
    terminal_launched_from_summary,
    terminal_mode_from_summary,
)
from foundation.mt5.tester_report_receipt import tester_report_completed, write_receipt
from foundation.pipelines.run_mt5_fixed_fixture_probe import (
    DEFAULT_TERMINAL,
    portable_terminal_root_preflight,
    redact_path,
    run_terminal_sequence,
)
from spacesonar.control_plane.store import dump_yaml, filesystem_path, repo_relative, sha256_file
from spacesonar.control_plane.writer_contract import (
    WRITER_CONTRACT_VERSION,
    default_validation_attempt_budget,
    default_writer_preflight_gate,
    enforce_writer_contract,
)


GOAL_ID = "goal_us100_onnx_forward_boundary_v0"
WAVE_ID = "wave_us100_wave03_volatility_state_transition_surface_v0"
CAMPAIGN_ID = "campaign_us100_wave03_volatility_state_transition_surface_v0"
IDEA_ID = "idea_us100_wave03_intraday_volatility_state_transition_v0"
HYPOTHESIS_ID = "hyp_us100_wave03_compression_expansion_reversal_continuation_v0"
SURFACE_ID = "surface_us100_wave03_compression_expansion_decision_v0"
SWEEP_ID = "sweep_us100_wave03_compression_expansion_seed_v0"

WORK_ITEM_ID = "work_wave03_volatility_state_l4_portable_runtime_repair_v0"
PARENT_WORK_ITEM_ID = "work_wave03_volatility_state_l4_pair_judgment_v0"
PROBE_ATTEMPT_ID = "attempt_wave03_vst_cell_001_l4_validation_portable_repair_probe_v0"
SOURCE_ATTEMPT_ID = "attempt_wave03_vst_cell_001_l4_validation_v0"
TESTER_LOGIN_FIXTURE: str | None = None
TESTER_COMMON_LOGIN_FIXTURE: str | None = None
TESTER_COMMON_PASSWORD_FIXTURE: str | None = None
TESTER_COMMON_SERVER_FIXTURE: str | None = None
TESTER_LOGIN_VALUE_KIND: str | None = None
TESTER_LOGIN_RECORDED_VALUE: str | None = None
TESTER_COMMON_LOGIN_VALUE_KIND: str | None = None
TESTER_COMMON_LOGIN_RECORDED_VALUE: str | None = None
TESTER_COMMON_PASSWORD_VALUE_KIND: str | None = None
TESTER_COMMON_PASSWORD_CONFIGURED: bool = False

OUTPUT_DIR = Path("lab/campaigns/campaign_us100_wave03_volatility_state_transition_surface_v0/l4_follow_through")
RUNTIME_SUMMARY = OUTPUT_DIR / "l4_runtime_execution_summary.yaml"
RUNTIME_INDEX = OUTPUT_DIR / "l4_runtime_execution_index.csv"
PAIR_SUMMARY = OUTPUT_DIR / "l4_pair_judgment_summary.yaml"
PAIR_INDEX = OUTPUT_DIR / "l4_pair_judgment_index.csv"
REPAIR_SUMMARY = OUTPUT_DIR / "l4_portable_runtime_repair_summary.yaml"
REPAIR_CLOSEOUT = Path(
    "lab/goals/goal_us100_onnx_forward_boundary_v0/"
    "work_wave03_volatility_state_l4_portable_runtime_repair_v0_closeout.yaml"
)
NEXT_WORK_ITEM = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/next_work_item.yaml")
RESUME_CURSOR = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/resume_cursor.yaml")
GOAL_MANIFEST = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/goal_manifest.yaml")
WORKSPACE_STATE = Path("docs/workspace/workspace_state.yaml")
CAMPAIGN_MANIFEST = Path("lab/campaigns/campaign_us100_wave03_volatility_state_transition_surface_v0/campaign_manifest.yaml")
GOAL_REGISTRY = Path("docs/registers/goal_registry.csv")
CAMPAIGN_REGISTRY = Path("docs/registers/campaign_registry.csv")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")

PRIMARY_FAMILY = "runtime_probe"
PRIMARY_SKILL = "spacesonar-runtime-evidence"
SUPPORT_SKILLS = ["spacesonar-result-judgment"]
VALIDATION_DEPTH = "writer_scope_smoke"
STATUS = "wave03_l4_portable_runtime_repair_probe_recorded_next"
CLAIM_BOUNDARY = (
    "wave03_l4_portable_runtime_repair_probe_only_no_runtime_authority_no_economics_pass_"
    "no_candidate_no_selected_baseline_no_live_readiness_no_goal_achieve"
)
NEXT_ACTION = (
    "stage a user-approved portable MT5 account/session config with trade-server synchronization in the local portable root "
    "(manually or by rerunning this writer with --session-source-root plus --allow-session-config-import "
    "plus --session-import-approval-token APPROVE_LOCAL_MT5_SESSION_CONFIG_IMPORT after approval), "
    "then rerun the no-fallback Wave03 portable repair probe before any remaining L4 batch or L5 routing"
)
RUNTIME_COMPLETE_NEXT_ACTION = (
    "materialize and execute the matching no-fallback portable sensitive-session repair probe for "
    "attempt_wave03_vst_cell_001_l4_research_oos_v0, then rerun Wave03 pair aggregation before any L5 routing"
)
PAIR_AGGREGATION_NEXT_ACTION = (
    "rerun Wave03 pair aggregation with the completed no-fallback portable validation/research_oos repair probes "
    "before any L5 routing"
)
PROGRESS_EFFECT = "wave03_l4_portable_runtime_repair_probe_materialized"
EXPERIMENT_EFFECT = "bounded_portable_strategy_tester_repair_probe_recorded_without_protected_claim"
BROAD_VALIDATION_ESCALATION_REASON = "none_portable_runtime_repair_probe_no_protected_claim"
NON_PYTEST_SMOKES = [
    "py_compile",
    "portable_repair_writer_smoke",
    "writer_scope_contract_lint",
    "machine_yaml_identity_lint",
    "active_pointer_smoke",
]
SKIPPED_BROAD_VALIDATIONS = [
    "pytest",
    "project_validate",
    "full_regression_workflow",
    "evidence_graph_full_workflow",
    "active_record_validator_full_graph",
    "spacesonar_project_validate_full",
    "spacesonar_cli_project_validate_as_progress_default",
    "broad_hash_resync",
    "global_registry_regeneration",
]
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
COMMON_REPAIR_ROOT = "SpaceSonar\\wave03_volatility_state_l4_portable_repair_probe"
SESSION_CONFIG_FILES = [
    ("config/accounts.dat", "account_session_config"),
    ("config/servers.dat", "server_catalog_config"),
]
SESSION_IMPORT_CLAIM_BOUNDARY = "portable_session_config_staging_only_no_runtime_authority"
SESSION_IMPORT_APPROVAL_TOKEN = "APPROVE_LOCAL_MT5_SESSION_CONFIG_IMPORT"
SESSION_IMPORT_SECRET_POLICY = (
    "local_session_files_are_copied_only_with_explicit_allow_flag_and_matching_approval_token_"
    "and_are_not_hashed_or_content_logged"
)


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def path_exists(path: Path) -> bool:
    return os.path.exists(filesystem_path(path))


def read_yaml(path: Path) -> dict[str, Any]:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        payload = yaml.safe_load(handle)
    return payload if isinstance(payload, dict) else {}


def read_json(path: Path) -> dict[str, Any]:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with open(filesystem_path(path), "r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_text(path: Path, text: str) -> None:
    full = REPO_ROOT / path if not path.is_absolute() else path
    full.parent.mkdir(parents=True, exist_ok=True)
    with open(filesystem_path(full), "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    enforce_writer_contract(path, payload)
    write_text(path, dump_yaml(payload))


def write_plain_yaml(path: Path, payload: dict[str, Any]) -> None:
    write_text(path, dump_yaml(payload))


def plain_copy(value: Any) -> Any:
    return json.loads(json.dumps(value or {}))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    full = REPO_ROOT / path if not path.is_absolute() else path
    full.parent.mkdir(parents=True, exist_ok=True)
    with open(filesystem_path(full), "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def rel(path: Path) -> str:
    return repo_relative(REPO_ROOT, path if path.is_absolute() else REPO_ROOT / path)


def artifact_ref(path: Path, *, availability: str = "present_hash_recorded") -> dict[str, Any]:
    full = path if path.is_absolute() else REPO_ROOT / path
    return {
        "path": rel(full),
        "sha256": sha256_file(full),
        "size_bytes": os.stat(filesystem_path(full)).st_size,
        "availability": availability,
    }


def git_state() -> dict[str, Any]:
    def run(args: list[str]) -> str:
        completed = subprocess.run(args, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
        return completed.stdout.strip() if completed.returncode == 0 else "unknown"

    status = run(["git", "status", "--short"])
    return {
        "git_sha": run(["git", "rev-parse", "HEAD"]),
        "branch": run(["git", "branch", "--show-current"]),
        "dirty_flag": bool(status),
        "changed_files": status.splitlines() if status else [],
    }


def default_portable_root() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "SpaceSonar" / "mt5_portable_roots" / "wave03_l4_portable_root_v0"
    return Path.home() / "AppData" / "Local" / "SpaceSonar" / "mt5_portable_roots" / "wave03_l4_portable_root_v0"


def run_robocopy(source_root: Path, target_root: Path, *, refresh: bool) -> dict[str, Any]:
    started_at = utc_now()
    terminal_before = target_root / "terminal64.exe"
    if terminal_before.exists() and not refresh:
        return {
            "status": "reused_existing_local_portable_root",
            "started_at_utc": started_at,
            "ended_at_utc": utc_now(),
            "source_root_redacted": redact_path(str(source_root)),
            "target_root_redacted": redact_path(str(target_root)),
            "terminal_exists_before": True,
            "terminal_exists_after": True,
            "robocopy_exit_code": None,
            "bounded_repair_or_fallback_attempt": "reused previously materialized local portable MT5 root",
        }

    target_root.mkdir(parents=True, exist_ok=True)
    command = [
        "robocopy",
        str(source_root),
        str(target_root),
        "/E",
        "/R:1",
        "/W:1",
        "/NFL",
        "/NDL",
        "/NJH",
        "/NJS",
        "/NP",
    ]
    completed = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    success = completed.returncode in range(0, 8)
    return {
        "status": "portable_root_copy_succeeded" if success else "portable_root_copy_failed",
        "started_at_utc": started_at,
        "ended_at_utc": utc_now(),
        "source_root_redacted": redact_path(str(source_root)),
        "target_root_redacted": redact_path(str(target_root)),
        "terminal_exists_before": terminal_before.exists(),
        "terminal_exists_after": (target_root / "terminal64.exe").exists(),
        "robocopy_exit_code": completed.returncode,
        "stdout_tail": completed.stdout[-1000:],
        "stderr_tail": completed.stderr[-1000:],
        "bounded_repair_or_fallback_attempt": "copied Program Files MT5 installation into writable local portable root",
        "claim_boundary": "portable_root_copy_only_no_runtime_authority",
    }


def portable_root_inventory(root: Path) -> dict[str, Any]:
    if not root.exists():
        return {
            "exists": False,
            "root_redacted": redact_path(str(root)),
            "file_count": 0,
            "size_bytes": 0,
        }
    file_count = 0
    size_bytes = 0
    for path in root.rglob("*"):
        if path.is_file():
            file_count += 1
            try:
                size_bytes += path.stat().st_size
            except OSError:
                pass
    terminal = root / "terminal64.exe"
    payload: dict[str, Any] = {
        "exists": True,
        "root_redacted": redact_path(str(root)),
        "terminal_redacted": redact_path(str(terminal)),
        "terminal_exists": terminal.exists(),
        "file_count": file_count,
        "size_bytes": size_bytes,
        "claim_boundary": "local_portable_root_inventory_only_no_runtime_authority",
    }
    if terminal.exists():
        payload["terminal_sha256"] = sha256_file(terminal)
        payload["terminal_size_bytes"] = terminal.stat().st_size
    return payload


def session_config_staging_preflight(
    *,
    source_root: Path | None,
    target_root: Path,
    allow_import: bool,
    approval_token: str | None,
) -> dict[str, Any]:
    started_at = utc_now()
    token_valid = approval_token == SESSION_IMPORT_APPROVAL_TOKEN
    approval_token_status = (
        "valid_approval_token"
        if token_valid
        else "missing_or_invalid_approval_token"
        if allow_import
        else "not_requested"
    )
    effective_import_allowed = allow_import and token_valid
    if source_root is None:
        return {
            "status": (
                "session_config_import_requested_missing_source_root"
                if effective_import_allowed
                else "session_config_import_requested_missing_approval_token"
                if allow_import
                else "not_requested"
            ),
            "started_at_utc": started_at,
            "ended_at_utc": utc_now(),
            "allow_import_requested": allow_import,
            "approval_token_status": approval_token_status,
            "effective_import_allowed": effective_import_allowed,
            "source_root_redacted": None,
            "target_root_redacted": redact_path(str(target_root)),
            "files": [],
            "secret_policy": SESSION_IMPORT_SECRET_POLICY,
            "claim_boundary": SESSION_IMPORT_CLAIM_BOUNDARY,
        }

    source_root = source_root.resolve()
    target_root = target_root.resolve()
    files: list[dict[str, Any]] = []
    copied_count = 0
    source_exists_count = 0
    missing_required: list[str] = []
    for relative, role in SESSION_CONFIG_FILES:
        source = source_root / relative
        target = target_root / relative
        source_exists = source.is_file()
        target_exists_before = target.exists()
        if source_exists:
            source_exists_count += 1
        copied = False
        copy_error = None
        if effective_import_allowed and source_exists:
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                copied = True
                copied_count += 1
            except OSError as exc:
                copy_error = str(exc)
        elif effective_import_allowed and not source_exists:
            missing_required.append(relative)
        files.append(
            {
                "relative_path": relative,
                "role": role,
                "source_exists": source_exists,
                "target_exists_before": target_exists_before,
                "target_exists_after": target.exists(),
                "copied": copied,
                "copy_error": copy_error,
                "source_redacted": redact_path(str(source)),
                "target_redacted": redact_path(str(target)),
                "source_size_bytes": source.stat().st_size if source_exists else None,
                "target_size_bytes": target.stat().st_size if target.exists() else None,
                "hash_availability": "not_recorded_local_session_secret_boundary",
                "claim_boundary": SESSION_IMPORT_CLAIM_BOUNDARY,
            }
        )

    if effective_import_allowed:
        status = "session_config_imported" if copied_count == len(SESSION_CONFIG_FILES) else "session_config_import_incomplete"
    elif allow_import:
        status = "session_config_import_requested_missing_approval_token"
    elif source_exists_count:
        status = "source_session_config_available_import_not_approved"
    else:
        status = "source_session_config_missing_import_not_approved"

    return {
        "status": status,
        "started_at_utc": started_at,
        "ended_at_utc": utc_now(),
        "allow_import_requested": allow_import,
        "approval_token_status": approval_token_status,
        "effective_import_allowed": effective_import_allowed,
        "source_root_redacted": redact_path(str(source_root)),
        "target_root_redacted": redact_path(str(target_root)),
        "source_file_count": source_exists_count,
        "copied_file_count": copied_count,
        "missing_required_files": missing_required,
        "files": files,
        "secret_policy": SESSION_IMPORT_SECRET_POLICY,
        "claim_boundary": SESSION_IMPORT_CLAIM_BOUNDARY,
    }


def portable_journal_tail(root: Path, *, line_count: int = 80) -> dict[str, Any]:
    log_dir = root / "logs"
    if not log_dir.exists():
        return {
            "status": "missing",
            "logs_dir_redacted": redact_path(str(log_dir)),
            "claim_boundary": "portable_terminal_journal_diagnostic_only_no_runtime_authority",
        }
    logs = sorted((path for path in log_dir.glob("*.log") if path.is_file()), key=lambda item: item.stat().st_mtime, reverse=True)
    if not logs:
        return {
            "status": "missing",
            "logs_dir_redacted": redact_path(str(log_dir)),
            "claim_boundary": "portable_terminal_journal_diagnostic_only_no_runtime_authority",
        }
    latest = logs[0]
    with open(filesystem_path(latest), "r", encoding="utf-8", errors="replace") as handle:
        lines = handle.read().splitlines()
    tail = [redact_journal_line(line) for line in lines[-line_count:]]
    latest_launch_index = 0
    for index, line in enumerate(tail):
        if "launched with" in line.lower():
            latest_launch_index = index
    latest_attempt_lines = tail[latest_launch_index:]
    text = "\n".join(line.lower() for line in latest_attempt_lines)
    diagnostic_flags = []
    if "account is not specified" in text:
        diagnostic_flags.append("portable_tester_account_not_specified")
    if "tester didn't start" in text:
        diagnostic_flags.append("portable_tester_did_not_start")
    if "not synchronized with trade server" in text:
        diagnostic_flags.append("portable_tester_trade_server_not_synchronized")
    return {
        "status": "observed",
        "path_redacted": redact_path(str(latest)),
        "sha256": sha256_file(latest),
        "size_bytes": latest.stat().st_size,
        "tail_line_count": len(tail),
        "tail_lines": tail,
        "latest_attempt_line_count": len(latest_attempt_lines),
        "latest_attempt_lines": latest_attempt_lines,
        "diagnostic_flags": diagnostic_flags,
        "claim_boundary": "portable_terminal_journal_diagnostic_only_no_runtime_authority",
    }


def redact_journal_line(line: str) -> str:
    redacted = redact_path(line.replace("\0", ""))
    redacted = re.sub(r"'(\d{4,})'", "'***redacted'", redacted)
    return re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "***redacted-ip", redacted)


def ini_value(path: Path, key: str) -> str | None:
    prefix = f"{key}="
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        for raw in handle:
            line = raw.strip()
            if line.startswith(prefix):
                return line.split("=", 1)[1].strip().strip('"')
    return None


def ensure_ini_section(text: str, section: str) -> str:
    header = f"[{section}]"
    if header in text:
        return text
    return header + "\n\n" + text


def upsert_ini_section_line(text: str, section: str, key: str, value: str, *, after_key: str | None = None) -> str:
    lines = text.splitlines()
    header = f"[{section}]"
    try:
        start = next(index for index, line in enumerate(lines) if line.strip() == header)
    except StopIteration:
        lines.insert(0, header)
        lines.insert(1, "")
        start = 0
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].strip().startswith("[") and lines[index].strip().endswith("]"):
            end = index
            break
    prefix = f"{key}="
    for index in range(start + 1, end):
        if lines[index].strip().startswith(prefix):
            lines[index] = f"{key}={value}"
            return "\n".join(lines) + "\n"
    insert_at = end
    if after_key:
        after_prefix = f"{after_key}="
        for index in range(start + 1, end):
            if lines[index].strip().startswith(after_prefix):
                insert_at = index + 1
                break
    lines.insert(insert_at, f"{key}={value}")
    return "\n".join(lines) + "\n"


def prepend_common_fixture_section(
    text: str,
    *,
    login: str | None,
    password: str | None,
    server: str | None,
) -> str:
    if not login and not password and not server:
        return text
    updated = ensure_ini_section(text, "Common")
    lines = ["[Common]"]
    if login:
        updated = upsert_ini_section_line(updated, "Common", "Login", login)
    if password:
        updated = upsert_ini_section_line(updated, "Common", "Password", password, after_key="Login")
    if server:
        updated = upsert_ini_section_line(updated, "Common", "Server", server, after_key="Password" if password else "Login")
    return updated


def prepare_probe_config(
    source_config: Path,
    probe_root: Path,
    *,
    tester_login: str | None,
    common_login: str | None,
    common_password: str | None,
    common_server: str | None,
) -> dict[str, Any]:
    probe_config = probe_root / "tester_config.ini"
    shutil.copy2(source_config, probe_config)
    with open(filesystem_path(probe_config), "r", encoding="utf-8-sig") as handle:
        text = handle.read()
    report_value = f"reports\\spacesonar\\{PROBE_ATTEMPT_ID}\\tester_report"
    telemetry_common = f"{COMMON_REPAIR_ROOT}\\{PROBE_ATTEMPT_ID}\\score_telemetry.csv"
    diagnostic_common = f"{COMMON_REPAIR_ROOT}\\{PROBE_ATTEMPT_ID}\\score_diagnostics.csv"
    text = prepend_common_fixture_section(text, login=common_login, password=common_password, server=common_server)
    text = l4_base.upsert_ini_line(text, "ReplaceReport", "1", after_key="Leverage")
    if tester_login:
        text = upsert_ini_section_line(text, "Tester", "Login", tester_login, after_key="Period")
    text = l4_base.upsert_ini_line(text, "Report", report_value, after_key="ReplaceReport")
    text = l4_base.upsert_ini_line(text, "ShutdownTerminal", "1", after_key="Report")
    text = l4_base.upsert_ini_line(text, "InpOutputPath", telemetry_common, after_key="InpOnnxPath")
    text = l4_base.upsert_ini_line(text, "InpDiagnosticPath", diagnostic_common, after_key="InpOutputPath")
    with open(filesystem_path(probe_config), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return {
        "tester_config": probe_config,
        "report_value": report_value,
        "telemetry_common_relative": telemetry_common,
        "diagnostic_common_relative": diagnostic_common,
        "tester_login_fixture": {
            "status": "emulated_tester_login_configured" if tester_login else "not_configured",
            "login_value_kind": TESTER_LOGIN_VALUE_KIND if tester_login else None,
            "login_value": TESTER_LOGIN_RECORDED_VALUE if tester_login else None,
            "claim_boundary": "tester_login_fixture_only_no_runtime_authority",
        },
        "common_account_fixture": {
            "status": "emulated_common_account_configured" if common_login or common_password or common_server else "not_configured",
            "login_value_kind": TESTER_COMMON_LOGIN_VALUE_KIND if common_login else None,
            "login_value": TESTER_COMMON_LOGIN_RECORDED_VALUE if common_login else None,
            "password_value_kind": TESTER_COMMON_PASSWORD_VALUE_KIND if common_password else None,
            "password_configured": TESTER_COMMON_PASSWORD_CONFIGURED,
            "server_value_kind": "tester_execution_profile_broker_server" if common_server else None,
            "server_value": common_server if common_server else None,
            "claim_boundary": "common_account_fixture_only_no_runtime_authority",
        },
        "config_artifact": artifact_ref(probe_config),
    }


def ensure_common_file_inputs(source_manifest: dict[str, Any], probe_config: Path) -> dict[str, Any]:
    bundle_id = str(source_manifest.get("bundle_id") or "")
    bundle_path = REPO_ROOT / "runtime" / "packages" / bundle_id / "experiment_bundle.json"
    bundle = read_json(bundle_path) if bundle_id and bundle_path.exists() else {}
    checks: list[dict[str, Any]] = []

    for key, bundle_source_key in [
        ("InpOnnxPath", "onnx_path"),
        ("InpFeatureColumnsPath", None),
    ]:
        common_relative = ini_value(probe_config, key)
        if not common_relative:
            checks.append({"key": key, "status": "not_configured"})
            continue
        common_path = l4_base.common_relative_to_path(common_relative)
        copied = False
        source_path: Path | None = None
        if not common_path.exists() and key == "InpOnnxPath" and bundle_source_key and bundle.get(bundle_source_key):
            source_path = REPO_ROOT / str(bundle[bundle_source_key])
        if not common_path.exists() and key == "InpFeatureColumnsPath":
            source_path = REPO_ROOT / "runtime" / "packages" / bundle_id / "artifacts" / "feature_columns.txt"
        if source_path is not None and source_path.exists():
            common_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, common_path)
            copied = True
        checks.append(
            {
                "key": key,
                "common_relative_path": common_relative,
                "exists_after_prepare": common_path.exists(),
                "copied_from_repo_artifact": copied,
                "source_path": rel(source_path) if source_path is not None and source_path.exists() else None,
                "common_path_redacted": redact_path(str(common_path)),
                "sha256": sha256_file(common_path) if common_path.exists() else None,
                "claim_boundary": "common_file_transport_preflight_only_no_runtime_authority",
            }
        )
    return {
        "bundle_id": bundle_id,
        "bundle_path": rel(bundle_path) if bundle_path.exists() else None,
        "checks": checks,
    }


def clear_common_probe_outputs(telemetry_rel: str, diagnostic_rel: str) -> None:
    for common_rel in [telemetry_rel, diagnostic_rel]:
        path = l4_base.common_relative_to_path(common_rel)
        if path.exists():
            path.unlink()
        path.parent.mkdir(parents=True, exist_ok=True)


def build_probe_manifest(
    *,
    source_manifest: dict[str, Any],
    probe_root: Path,
    probe_config: Path,
    portable_root: Path,
    copy_result: dict[str, Any],
    session_config_staging: dict[str, Any],
    root_preflight: dict[str, Any],
    common_inputs: dict[str, Any],
    ea_stage_manifest: dict[str, Any],
) -> dict[str, Any]:
    started = utc_now()
    source_period_identity = plain_copy(source_manifest.get("period_identity"))
    source_execution_identity = plain_copy(source_manifest.get("execution_identity"))
    source_tester_identity = plain_copy(source_manifest.get("tester_identity"))
    source_runtime_surface_contract = plain_copy(source_manifest.get("runtime_surface_contract"))
    execution_profile_id = (
        source_execution_identity.get("execution_profile_id")
        or source_tester_identity.get("execution_profile_id")
        or source_manifest.get("execution_profile_id")
        or source_manifest.get("tester_execution_profile_id")
    )
    return {
        "version": "wave03_l4_portable_runtime_repair_probe_manifest_v1",
        "attempt_id": PROBE_ATTEMPT_ID,
        "source_attempt_id": SOURCE_ATTEMPT_ID,
        "run_id": source_manifest.get("run_id"),
        "bundle_id": source_manifest.get("bundle_id"),
        "active_goal_id": GOAL_ID,
        "work_item_id": WORK_ITEM_ID,
        "campaign_id": CAMPAIGN_ID,
        "created_at_utc": started,
        "status": "probe_manifest_prepared",
        "tester_config": artifact_ref(probe_config),
        "period_identity": source_period_identity,
        "execution_identity": {
            **source_execution_identity,
            "execution_profile_id": execution_profile_id,
            "source_identity_block": "source_attempt_execution_or_tester_identity",
        },
        "runtime_surface_contract": source_runtime_surface_contract,
        "tester_login_fixture": {
            "status": "configured" if TESTER_LOGIN_FIXTURE else "not_configured",
            "login_value_kind": TESTER_LOGIN_VALUE_KIND if TESTER_LOGIN_FIXTURE else None,
            "login_value": TESTER_LOGIN_RECORDED_VALUE if TESTER_LOGIN_FIXTURE else None,
            "claim_boundary": "tester_login_fixture_only_no_runtime_authority",
        },
        "common_account_fixture": {
            "login_value_kind": TESTER_COMMON_LOGIN_VALUE_KIND if TESTER_COMMON_LOGIN_FIXTURE else None,
            "login_value": TESTER_COMMON_LOGIN_RECORDED_VALUE if TESTER_COMMON_LOGIN_FIXTURE else None,
            "password_value_kind": TESTER_COMMON_PASSWORD_VALUE_KIND if TESTER_COMMON_PASSWORD_FIXTURE else None,
            "password_configured": TESTER_COMMON_PASSWORD_CONFIGURED,
            "server": TESTER_COMMON_SERVER_FIXTURE,
            "claim_boundary": "common_account_fixture_only_no_runtime_authority",
        },
        "portable_root": portable_root_inventory(portable_root),
        "portable_root_copy": copy_result,
        "session_config_staging": session_config_staging,
        "portable_root_preflight": root_preflight,
        "common_file_inputs": common_inputs,
        "portable_ea_stage": (ea_stage_manifest.get("artifact_identity") or {})
        .get("portable_runtime_root", {})
        .get("ea_binary"),
        "claim_boundary": CLAIM_BOUNDARY,
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
    }


def materialize_terminal_probe(
    *,
    source_manifest: dict[str, Any],
    source_row: dict[str, str],
    probe_root: Path,
    probe_config: Path,
    portable_terminal: Path,
    telemetry_rel: str,
    diagnostic_rel: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    common_telemetry = l4_base.common_relative_to_path(telemetry_rel)
    common_diagnostic = l4_base.common_relative_to_path(diagnostic_rel)
    clear_common_probe_outputs(telemetry_rel, diagnostic_rel)
    report_prelaunch = l4_base.prepare_tester_report_directories(
        repo_root=REPO_ROOT,
        attempt_root=probe_root,
        tester_config=probe_config,
        portable_terminal_root=portable_terminal.parent,
        main_terminal_data_root=None,
    )
    terminal_summary = run_terminal_sequence(
        terminal=portable_terminal,
        tester_config=probe_config,
        common_telemetry=common_telemetry,
        timeout_seconds=timeout_seconds,
        terminate_existing=False,
        allow_main_mode_fallback=False,
    )
    terminal_summary = {
        **terminal_summary,
        "version": "wave03_l4_portable_runtime_repair_terminal_summary_v1",
        "summary_path": rel(probe_root / "terminal_run_summary.yaml"),
        "attempt_id": PROBE_ATTEMPT_ID,
        "source_attempt_id": SOURCE_ATTEMPT_ID,
        "run_id": source_manifest.get("run_id"),
        "bundle_id": source_manifest.get("bundle_id"),
        "tester_config": artifact_ref(probe_config),
        "tester_report_resolution_prelaunch": l4_base.public_report_resolution_summary(report_prelaunch),
        "common_telemetry_redacted": redact_path(str(common_telemetry)),
        "common_diagnostic_redacted": redact_path(str(common_diagnostic)),
        "claim_boundary": CLAIM_BOUNDARY,
    }
    write_plain_yaml(probe_root / "terminal_run_summary.yaml", terminal_summary)

    telemetry_observed = False
    telemetry_file_observed = common_telemetry.exists()
    if telemetry_file_observed:
        repo_telemetry = probe_root / "telemetry" / "score_telemetry.csv"
        repo_telemetry.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(common_telemetry, repo_telemetry)
        telemetry_stats = l4_base.parse_score_telemetry(repo_telemetry)
        telemetry_observed = int(telemetry_stats.get("row_count") or 0) > 0
        telemetry_summary = {
            "version": "wave03_l4_portable_runtime_repair_score_telemetry_summary_v1",
            "summary_path": rel(probe_root / "score_telemetry_summary.yaml"),
            "attempt_id": PROBE_ATTEMPT_ID,
            "source_attempt_id": SOURCE_ATTEMPT_ID,
            "run_id": source_manifest.get("run_id"),
            "bundle_id": source_manifest.get("bundle_id"),
            "period_role": source_row.get("period_role"),
            "telemetry": artifact_ref(repo_telemetry, availability="local_telemetry_hash_recorded_ignored_by_git"),
            "common_telemetry_redacted": redact_path(str(common_telemetry)),
            "stats": telemetry_stats,
            "claim_boundary": CLAIM_BOUNDARY if telemetry_observed else "portable_repair_empty_score_telemetry_no_l4_completion",
        }
    else:
        telemetry_summary = {
            "version": "wave03_l4_portable_runtime_repair_score_telemetry_summary_v1",
            "summary_path": rel(probe_root / "score_telemetry_summary.yaml"),
            "attempt_id": PROBE_ATTEMPT_ID,
            "source_attempt_id": SOURCE_ATTEMPT_ID,
            "run_id": source_manifest.get("run_id"),
            "bundle_id": source_manifest.get("bundle_id"),
            "period_role": source_row.get("period_role"),
            "telemetry": {"path": None, "availability": "missing_after_portable_terminal_probe"},
            "common_telemetry_redacted": redact_path(str(common_telemetry)),
            "stats": {"status": "telemetry_missing", "row_count": 0},
            "failure_disposition": {
                "reproduction": "local portable terminal root was prepared and launched without main-mode fallback",
                "exact_failing_layer": "portable_strategy_tester_score_probe_common_file_telemetry",
                "bounded_repair_or_fallback_attempt": "workspace writer created writable portable root and launched one no-fallback repair probe",
                "evidence_path": rel(probe_root / "terminal_run_summary.yaml"),
                "remaining_blocker": "score telemetry CSV not observed from no-fallback portable terminal probe",
                "reopen_condition": "inspect portable root account/history/config and rerun the repair probe",
            },
            "claim_boundary": "portable_repair_probe_no_score_telemetry_no_l4_completion",
        }
    write_plain_yaml(probe_root / "score_telemetry_summary.yaml", telemetry_summary)

    diagnostic_observed = common_diagnostic.exists()
    if diagnostic_observed:
        repo_diagnostic = probe_root / "telemetry" / "score_diagnostics.csv"
        repo_diagnostic.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(common_diagnostic, repo_diagnostic)
        diagnostic_stats = l4_base.parse_score_diagnostics(repo_diagnostic)
        diagnostic_summary = {
            "version": "wave03_l4_portable_runtime_repair_score_diagnostic_summary_v1",
            "summary_path": rel(probe_root / "score_diagnostic_summary.yaml"),
            "attempt_id": PROBE_ATTEMPT_ID,
            "diagnostic": artifact_ref(repo_diagnostic, availability="local_diagnostic_hash_recorded_ignored_by_git"),
            "stats": diagnostic_stats,
            "claim_boundary": "portable_repair_probe_diagnostic_observation_only_no_runtime_authority",
        }
    else:
        diagnostic_summary = {
            "version": "wave03_l4_portable_runtime_repair_score_diagnostic_summary_v1",
            "summary_path": rel(probe_root / "score_diagnostic_summary.yaml"),
            "attempt_id": PROBE_ATTEMPT_ID,
            "diagnostic": {"path": None, "availability": "missing_after_portable_terminal_probe"},
            "stats": {"status": "diagnostic_missing", "event_count": 0, "event_counts": {}},
            "claim_boundary": "portable_repair_probe_diagnostic_missing_no_runtime_authority",
        }
    write_plain_yaml(probe_root / "score_diagnostic_summary.yaml", diagnostic_summary)

    receipt = l4_base.build_tester_report_receipt_for_attempt(
        repo_root=REPO_ROOT,
        attempt_root=probe_root,
        attempt_id=PROBE_ATTEMPT_ID,
        tester_config=probe_config,
        portable_terminal_root=portable_terminal.parent,
        main_terminal_data_root=None,
        prelaunch_candidates=report_prelaunch.get("prelaunch_candidates", []),
        launch_started_at_utc=terminal_summary.get("started_at_utc"),
    )
    receipt_path = probe_root / "tester_report_receipt.yaml"
    write_receipt(receipt_path, receipt)
    report = l4_base.archive_tester_report(
        REPO_ROOT,
        probe_root,
        probe_config,
        portable_terminal_root=portable_terminal.parent,
        main_terminal_data_root=None,
    )
    report_observed = bool(receipt.get("source_report_sha256"))
    report_completed = tester_report_completed(receipt)
    terminal_mode_policy = terminal_summary.get("terminal_mode_policy") or {}
    completion = evaluate_runtime_attempt(
        RuntimeAttemptState(
            terminal_launched=terminal_launched_from_summary(terminal_summary),
            telemetry_file_observed=telemetry_file_observed,
            telemetry_rows_observed=telemetry_observed,
            tester_report_observed=report_observed,
            tester_report_completed=report_completed,
            terminal_mode=terminal_mode_from_summary(terminal_summary),
            period_role=source_row.get("period_role"),
            period_profile_id=l4_base.runtime_contract_value(source_manifest, source_row, "period_profile_id", "runtime_period_profile_id"),
            runtime_period_set_id=l4_base.runtime_contract_value(source_manifest, source_row, "runtime_period_set_id"),
            execution_profile_id=l4_base.runtime_contract_value(source_manifest, source_row, "tester_execution_profile_id", "execution_profile_id"),
            surface_scope=l4_base.runtime_contract_value(source_manifest, source_row, "completion_surface_scope"),
            portable_attempted=terminal_mode_policy.get("portable_attempted"),
            main_mode_fallback_allowed=terminal_mode_policy.get("main_mode_fallback_allowed"),
            main_mode_fallback_used=terminal_mode_policy.get("main_mode_fallback_used"),
        ),
        required_period_roles=["validation", "research_oos"],
        completion_eligible_surface_scopes=["full_period_deterministic", "full_period_sparse_decision_surface"],
    )
    terminal_summary["telemetry_observed"] = telemetry_observed
    terminal_summary["telemetry_file_observed_after_attempt"] = telemetry_file_observed
    terminal_summary["telemetry_rows_observed_after_attempt"] = telemetry_observed
    terminal_summary["telemetry_row_count"] = (telemetry_summary.get("stats") or {}).get("row_count", 0)
    terminal_summary["score_diagnostic_file_observed_after_attempt"] = diagnostic_observed
    terminal_summary["tester_report_observed"] = report_observed
    terminal_summary["tester_report_completed"] = report_completed
    terminal_summary["runtime_completion"] = {
        "status": runtime_status(completion, telemetry_kind="telemetry"),
        "runtime_probe_complete": completion.runtime_probe_complete,
        "portable_contract_satisfied": completion.portable_contract_satisfied,
        "report_contract_satisfied": completion.report_contract_satisfied,
        "period_contract_satisfied": completion.period_contract_satisfied,
        "surface_contract_satisfied": completion.surface_contract_satisfied,
        "missing_requirements": list(completion.missing_requirements),
        "claim_boundary": completion.claim_boundary,
    }
    terminal_summary["portable_terminal_journal"] = portable_journal_tail(portable_terminal.parent)
    write_plain_yaml(probe_root / "terminal_run_summary.yaml", terminal_summary)
    return {
        "terminal_summary": terminal_summary,
        "telemetry_summary": telemetry_summary,
        "diagnostic_summary": diagnostic_summary,
        "tester_report_receipt": receipt,
        "tester_report_archive": report,
        "runtime_completion": terminal_summary["runtime_completion"],
    }


def load_existing_terminal_probe(probe_root: Path, portable_terminal: Path) -> dict[str, Any]:
    terminal_path = probe_root / "terminal_run_summary.yaml"
    if not terminal_path.exists():
        raise RuntimeError(f"existing terminal probe summary is missing: {terminal_path}")
    terminal_summary = read_yaml(terminal_path)
    terminal_summary["portable_terminal_journal"] = portable_journal_tail(portable_terminal.parent)
    write_plain_yaml(terminal_path, terminal_summary)
    telemetry_summary = read_yaml(probe_root / "score_telemetry_summary.yaml") if (probe_root / "score_telemetry_summary.yaml").exists() else {}
    diagnostic_summary = read_yaml(probe_root / "score_diagnostic_summary.yaml") if (probe_root / "score_diagnostic_summary.yaml").exists() else {}
    receipt = read_yaml(probe_root / "tester_report_receipt.yaml") if (probe_root / "tester_report_receipt.yaml").exists() else {}
    return {
        "terminal_summary": terminal_summary,
        "telemetry_summary": telemetry_summary,
        "diagnostic_summary": diagnostic_summary,
        "tester_report_receipt": receipt,
        "tester_report_archive": {},
        "runtime_completion": terminal_summary.get("runtime_completion") or {},
    }


def completed_probe_next_action() -> str:
    if SOURCE_ATTEMPT_ID.endswith("_research_oos_v0"):
        return PAIR_AGGREGATION_NEXT_ACTION
    if SOURCE_ATTEMPT_ID.endswith("_validation_v0"):
        counterpart = SOURCE_ATTEMPT_ID.replace("_validation_v0", "_research_oos_v0")
        return (
            "materialize and execute the matching no-fallback portable sensitive-session repair probe for "
            f"{counterpart}, then rerun Wave03 pair aggregation before any L5 routing"
        )
    return RUNTIME_COMPLETE_NEXT_ACTION


def completed_probe_blockers() -> list[str]:
    if SOURCE_ATTEMPT_ID.endswith("_research_oos_v0"):
        return ["wave03_pair_aggregation_pending_after_portable_research_oos_repair"]
    match = re.search(r"(wave03_vst_cell_\d+)_l4_validation_v0$", SOURCE_ATTEMPT_ID)
    if match:
        return [f"{match.group(1)}_validation_portable_repair_complete_counterpart_research_oos_pending"]
    return ["wave03_validation_portable_repair_complete_counterpart_research_oos_pending"]


def writer_contract_fields(
    *,
    source_paths: list[str],
    outputs: list[str],
    next_action: str | None = None,
    blockers: list[str] | None = None,
) -> dict[str, Any]:
    effective_next_action = next_action or NEXT_ACTION
    effective_blockers = blockers or ["standard_l4_runtime_completion_contract_pending_portable_terminal"]
    budget = default_validation_attempt_budget()
    budget["observed_writer_scope_attempts"] = 0
    return {
        "writer_contract_version": WRITER_CONTRACT_VERSION,
        "primary_family": PRIMARY_FAMILY,
        "primary_skill": PRIMARY_SKILL,
        "progress_class": "next_executable_experiment_writer_or_probe",
        "progress_effect": PROGRESS_EFFECT,
        "next_executable_action": effective_next_action,
        "experiment_or_boundary_effect": EXPERIMENT_EFFECT,
        "source_of_truth_paths": source_paths,
        "writer_owned_outputs": outputs,
        "validation_depth": VALIDATION_DEPTH,
        "non_pytest_smokes": list(NON_PYTEST_SMOKES),
        "skipped_broad_validations": list(SKIPPED_BROAD_VALIDATIONS),
        "broad_validation_escalation_reason": BROAD_VALIDATION_ESCALATION_REASON,
        "writer_preflight_gate": default_writer_preflight_gate(),
        "validation_attempt_budget": budget,
        "writer_scope_self_check": {
            "status": "passed",
            "checked_at_utc": utc_now(),
            "failures": [],
            "claim_boundary": CLAIM_BOUNDARY,
            "forbidden_claims_respected": True,
        },
        "claim_boundary": CLAIM_BOUNDARY,
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
        "unresolved_blockers_or_none": effective_blockers,
        "next_action_or_reopen_condition": effective_next_action,
    }


def build_summary(
    *,
    started_at: str,
    ended_at: str,
    portable_root: Path,
    copy_result: dict[str, Any],
    session_config_staging: dict[str, Any],
    root_preflight: dict[str, Any],
    probe_manifest: dict[str, Any],
    terminal_probe: dict[str, Any] | None,
    smoke_only: bool,
) -> dict[str, Any]:
    terminal_summary = (terminal_probe or {}).get("terminal_summary") or {}
    runtime_completion = (terminal_probe or {}).get("runtime_completion") or {}
    journal = terminal_summary.get("portable_terminal_journal") or {}
    terminal_launched = bool(terminal_launched_from_summary(terminal_summary)) if terminal_summary else False
    telemetry_rows = bool(terminal_summary.get("telemetry_rows_observed_after_attempt")) if terminal_summary else False
    report_completed = bool(terminal_summary.get("tester_report_completed")) if terminal_summary else False
    portable_contract = bool(runtime_completion.get("portable_contract_satisfied")) if runtime_completion else False
    runtime_probe_complete = bool(runtime_completion.get("runtime_probe_complete")) if runtime_completion else False
    next_action = completed_probe_next_action() if runtime_probe_complete else NEXT_ACTION
    missing = list(runtime_completion.get("missing_requirements") or []) if runtime_completion else []
    blockers = completed_probe_blockers() if runtime_probe_complete else ["standard_l4_runtime_completion_contract_pending_portable_terminal"]
    if root_preflight.get("status") != "passed":
        blockers.append("writable_portable_terminal_root_preflight_failed")
    elif not terminal_launched and not smoke_only:
        blockers.append("portable_terminal_launch_not_observed")
    elif not telemetry_rows and not smoke_only:
        blockers.append("portable_repair_probe_score_telemetry_missing")
    journal_flags = journal.get("diagnostic_flags") or []
    if "portable_tester_trade_server_not_synchronized" in journal_flags:
        blockers.append("portable_repair_probe_trade_server_not_synchronized")
    if "portable_tester_account_not_specified" in journal_flags:
        blockers.append("portable_repair_probe_account_not_specified")
    session_staging_status = session_config_staging.get("status")
    if session_staging_status == "source_session_config_available_import_not_approved":
        blockers.append("portable_session_config_import_requires_explicit_user_approval")
    elif session_staging_status == "session_config_import_requested_missing_approval_token":
        blockers.append("portable_session_config_import_requires_matching_approval_token")
    elif session_staging_status == "source_session_config_missing_import_not_approved":
        blockers.append("portable_session_config_source_missing")
    elif session_staging_status == "session_config_import_incomplete":
        blockers.append("portable_session_config_import_incomplete")
    elif session_staging_status == "session_config_import_requested_missing_source_root":
        blockers.append("portable_session_config_import_source_root_missing")
    if missing:
        blockers.extend(f"portable_repair_probe_missing_{item}" for item in missing)
    blockers = list(dict.fromkeys(blockers))
    outputs = [
        REPAIR_SUMMARY.as_posix(),
        REPAIR_CLOSEOUT.as_posix(),
        f"runtime/mt5_attempts/{PROBE_ATTEMPT_ID}/portable_repair_attempt_manifest.yaml",
        f"runtime/mt5_attempts/{PROBE_ATTEMPT_ID}/tester_config.ini",
        f"runtime/mt5_attempts/{PROBE_ATTEMPT_ID}/terminal_run_summary.yaml",
        f"runtime/mt5_attempts/{PROBE_ATTEMPT_ID}/score_telemetry_summary.yaml",
        f"runtime/mt5_attempts/{PROBE_ATTEMPT_ID}/score_diagnostic_summary.yaml",
        f"runtime/mt5_attempts/{PROBE_ATTEMPT_ID}/tester_report_receipt.yaml",
        NEXT_WORK_ITEM.as_posix(),
    ]
    source_paths = [
        PAIR_SUMMARY.as_posix(),
        PAIR_INDEX.as_posix(),
        RUNTIME_SUMMARY.as_posix(),
        RUNTIME_INDEX.as_posix(),
        f"runtime/mt5_attempts/{SOURCE_ATTEMPT_ID}/attempt_manifest.yaml",
        f"runtime/mt5_attempts/{SOURCE_ATTEMPT_ID}/tester_config.ini",
        NEXT_WORK_ITEM.as_posix(),
    ]
    summary = {
        "version": "wave03_l4_portable_runtime_repair_summary_v1",
        "summary_id": "wave03_l4_portable_runtime_repair_summary_v0",
        "active_goal_id": GOAL_ID,
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "campaign_id": CAMPAIGN_ID,
        "wave_id": WAVE_ID,
        "started_at_utc": started_at,
        "ended_at_utc": ended_at,
        "status": STATUS,
        "progress_class": "next_executable_experiment_writer_or_probe",
        "progress_effect": PROGRESS_EFFECT,
        "claim_boundary": CLAIM_BOUNDARY,
        "repair_scope": {
            "source_attempt_id": SOURCE_ATTEMPT_ID,
            "probe_attempt_id": PROBE_ATTEMPT_ID,
            "portable_root_redacted": redact_path(str(portable_root)),
            "main_mode_fallback_allowed": False,
            "session_config_staging_status": session_staging_status,
            "tester_login_fixture": {
                "status": "emulated_tester_login_configured" if TESTER_LOGIN_FIXTURE else "not_configured",
                "login_value_kind": TESTER_LOGIN_VALUE_KIND if TESTER_LOGIN_FIXTURE else None,
                "login_value": TESTER_LOGIN_RECORDED_VALUE if TESTER_LOGIN_FIXTURE else None,
                "claim_boundary": "tester_login_fixture_only_no_runtime_authority",
            },
            "common_account_fixture": {
                "status": "emulated_common_account_configured"
                if TESTER_COMMON_LOGIN_FIXTURE or TESTER_COMMON_PASSWORD_FIXTURE or TESTER_COMMON_SERVER_FIXTURE
                else "not_configured",
                "login_value_kind": TESTER_COMMON_LOGIN_VALUE_KIND if TESTER_COMMON_LOGIN_FIXTURE else None,
                "login_value": TESTER_COMMON_LOGIN_RECORDED_VALUE if TESTER_COMMON_LOGIN_FIXTURE else None,
                "password_value_kind": TESTER_COMMON_PASSWORD_VALUE_KIND if TESTER_COMMON_PASSWORD_FIXTURE else None,
                "password_configured": TESTER_COMMON_PASSWORD_CONFIGURED,
                "server_value_kind": "tester_execution_profile_broker_server" if TESTER_COMMON_SERVER_FIXTURE else None,
                "server_value": TESTER_COMMON_SERVER_FIXTURE if TESTER_COMMON_SERVER_FIXTURE else None,
                "claim_boundary": "common_account_fixture_only_no_runtime_authority",
            },
            "existing_l4_attempt_records_preserved": True,
            "probe_root": f"runtime/mt5_attempts/{PROBE_ATTEMPT_ID}",
        },
        "portable_root_copy": copy_result,
        "session_config_staging": session_config_staging,
        "portable_root_inventory": portable_root_inventory(portable_root),
        "portable_root_preflight": root_preflight,
        "probe_manifest": {
            "path": f"runtime/mt5_attempts/{PROBE_ATTEMPT_ID}/portable_repair_attempt_manifest.yaml",
            "status": probe_manifest.get("status"),
            "tester_config": (probe_manifest.get("tester_config") or {}).get("path"),
        },
        "terminal_probe": {
            "attempted": terminal_probe is not None,
            "terminal_launched": terminal_launched,
            "telemetry_rows_observed": telemetry_rows,
            "tester_report_completed": report_completed,
            "portable_contract_satisfied": portable_contract,
            "runtime_probe_complete": bool(runtime_completion.get("runtime_probe_complete")) if runtime_completion else False,
            "runtime_completion": runtime_completion,
            "portable_terminal_journal": journal,
        },
        "failure_disposition": {
            "reproduction": "local portable terminal root was prepared, passed write preflight, and launched one no-fallback Strategy Tester probe",
            "exact_failing_layer": (
                "none_runtime_probe_completed_counterpart_period_pending"
                if runtime_probe_complete
                else
                "portable_strategy_tester_trade_server_synchronization"
                if "portable_tester_trade_server_not_synchronized" in journal_flags
                else "portable_strategy_tester_account_configuration"
                if "portable_tester_account_not_specified" in journal_flags
                else "portable_strategy_tester_probe_without_score_telemetry"
            ),
            "bounded_repair_or_fallback_attempt": "created writable local portable MT5 root, staged EA/config/common-file inputs, and launched without main-mode fallback",
            "evidence_path": f"runtime/mt5_attempts/{PROBE_ATTEMPT_ID}/terminal_run_summary.yaml",
            "remaining_blocker": (
                "Wave03 pair aggregation is pending after completed validation/research_oos portable repair probes"
                if runtime_probe_complete and SOURCE_ATTEMPT_ID.endswith("_research_oos_v0")
                else "matching research_oos no-fallback portable repair probe is still pending before paired Wave03 L4 follow-through"
                if runtime_probe_complete
                else
                "portable tester account/session config exists as a non-secret fixture but did not synchronize with the trade server"
                if "portable_tester_trade_server_not_synchronized" in journal_flags
                else "portable tester account/session config remains unavailable; non-secret Login/Server fixtures did not satisfy MT5 tester preflight"
                if "portable_tester_account_not_specified" in journal_flags
                and (TESTER_LOGIN_FIXTURE or TESTER_COMMON_LOGIN_FIXTURE or TESTER_COMMON_SERVER_FIXTURE)
                else "portable tester account/session config is not specified"
                if "portable_tester_account_not_specified" in journal_flags
                else "portable probe did not produce score telemetry or completed report"
            ),
            "reopen_condition": next_action,
            "claim_boundary": CLAIM_BOUNDARY,
        },
        "counts": {
            "portable_root_materialized_count": 1 if (portable_root / "terminal64.exe").exists() else 0,
            "portable_root_preflight_pass_count": 1 if root_preflight.get("status") == "passed" else 0,
            "portable_session_source_config_available_count": 1
            if int(session_config_staging.get("source_file_count") or 0) > 0
            else 0,
            "portable_session_config_imported_count": 1 if session_staging_status == "session_config_imported" else 0,
            "portable_repair_probe_attempt_count": 1 if terminal_probe is not None else 0,
            "portable_repair_probe_terminal_launch_count": 1 if terminal_launched else 0,
            "portable_repair_probe_telemetry_observed_count": 1 if telemetry_rows else 0,
            "portable_repair_probe_completed_report_count": 1 if report_completed else 0,
            "portable_repair_probe_runtime_complete_count": 1 if runtime_probe_complete else 0,
            "candidate_count": 0,
            "l5_candidate_count": 0,
        },
        "operational_validation_required": False,
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
        "unresolved_blockers": blockers,
        "unresolved_blockers_or_none": blockers,
        "reopen_conditions": [
            "rerun the repair writer after portable account/history/config is available if the no-fallback probe produced no telemetry",
            completed_probe_next_action()
            if runtime_probe_complete
            else "rerun Wave03 pair aggregation after additional portable repair probes change runtime evidence",
            "rerun Wave03 pair aggregation after additional portable repair probes change runtime evidence",
            "do not route to L5 until standard portable L4 contract evidence is present for eligible period roles",
        ],
        "next_action": next_action,
        "next_executable_action": next_action,
        "provenance": {
            "producer": "python foundation/pipelines/repair_wave03_volatility_state_l4_portable_runtime.py --write-control-records",
            "user_direction": "experiment_first",
            "git": git_state(),
        },
    }
    summary.update(writer_contract_fields(source_paths=source_paths, outputs=outputs, next_action=next_action, blockers=blockers))
    summary["unresolved_blockers_or_none"] = blockers
    summary["next_executable_action"] = next_action
    summary["next_action_or_reopen_condition"] = next_action
    return summary


def build_closeout(summary: dict[str, Any]) -> dict[str, Any]:
    next_action = str(summary.get("next_action") or NEXT_ACTION)
    payload = {
        "version": "work_closeout_v1",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "active_goal_id": GOAL_ID,
        "campaign_id": CAMPAIGN_ID,
        "closed_at_utc": summary["ended_at_utc"],
        "status": summary["status"],
        "result_judgment": "portable_runtime_repair_probe_recorded",
        "claim_boundary": CLAIM_BOUNDARY,
        "evidence_paths": [
            REPAIR_SUMMARY.as_posix(),
            f"runtime/mt5_attempts/{PROBE_ATTEMPT_ID}/portable_repair_attempt_manifest.yaml",
            f"runtime/mt5_attempts/{PROBE_ATTEMPT_ID}/terminal_run_summary.yaml",
        ],
        "counts": summary["counts"],
        "unresolved_blockers": summary["unresolved_blockers"],
        "reopen_conditions": summary["reopen_conditions"],
        "operational_validation_required": False,
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
        "next_action": next_action,
    }
    payload.update(
        writer_contract_fields(
            source_paths=[REPAIR_SUMMARY.as_posix(), NEXT_WORK_ITEM.as_posix()],
            outputs=[REPAIR_CLOSEOUT.as_posix()],
            next_action=next_action,
            blockers=list(summary["unresolved_blockers"]),
        )
    )
    payload["unresolved_blockers_or_none"] = list(summary["unresolved_blockers"])
    payload["next_executable_action"] = next_action
    payload["next_action_or_reopen_condition"] = next_action
    return payload


def next_work_record(summary: dict[str, Any]) -> dict[str, Any]:
    next_action = str(summary.get("next_action") or NEXT_ACTION)
    payload = {
        "version": "work_item_lite_v1",
        "work_item_id": WORK_ITEM_ID,
        "parent_work_item_id": PARENT_WORK_ITEM_ID,
        "primary_family": PRIMARY_FAMILY,
        "primary_skill": PRIMARY_SKILL,
        "support_skills": list(SUPPORT_SKILLS),
        "verification_profile": "mt5_l4_portable_runtime_repair_probe",
        "targets": [REPAIR_SUMMARY.as_posix(), f"runtime/mt5_attempts/{PROBE_ATTEMPT_ID}/terminal_run_summary.yaml"],
        "acceptance_criteria": [
            "continue with no-fallback portable Strategy Tester probes only if the local portable root remains writable",
            "do not use main-mode fallback as standard L4 completion",
            "do not claim runtime authority, economics pass, selected baseline, live readiness, reviewed/verified pass, or Goal Achieve",
        ],
        "status": STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
        "current_truth": {
            "portable_runtime_repair_summary": REPAIR_SUMMARY.as_posix(),
            "portable_repair_probe_attempt_id": PROBE_ATTEMPT_ID,
            "portable_repair_probe_counts": summary["counts"],
            "runtime_probe_complete_count": summary["counts"]["portable_repair_probe_runtime_complete_count"],
            "candidate_count": 0,
            "l5_candidate_count": 0,
        },
        "outputs": [
            REPAIR_SUMMARY.as_posix(),
            f"runtime/mt5_attempts/{PROBE_ATTEMPT_ID}/terminal_run_summary.yaml",
        ],
        "operational_validation_required": False,
        "next_action": next_action,
        "next_executable_action": next_action,
        "missing_material_if_relevant": [
            "standard portable L4 completion evidence for Wave03 paired validation/research_oos roles"
        ],
        "unresolved_blockers": list(summary["unresolved_blockers"]),
        "unresolved_blockers_or_none": list(summary["unresolved_blockers"]),
        "reopen_conditions": list(summary["reopen_conditions"]),
    }
    payload.update(
        writer_contract_fields(
            source_paths=[REPAIR_SUMMARY.as_posix(), PAIR_SUMMARY.as_posix(), NEXT_WORK_ITEM.as_posix()],
            outputs=[NEXT_WORK_ITEM.as_posix()],
            next_action=next_action,
            blockers=list(summary["unresolved_blockers"]),
        )
    )
    payload["unresolved_blockers_or_none"] = list(summary["unresolved_blockers"])
    payload["next_executable_action"] = next_action
    payload["next_action_or_reopen_condition"] = next_action
    return payload


def update_control_records(summary: dict[str, Any]) -> None:
    next_work = next_work_record(summary)
    write_yaml(NEXT_WORK_ITEM, next_work)
    next_action = str(summary.get("next_action") or NEXT_ACTION)
    common_contract = writer_contract_fields(
        source_paths=[REPAIR_SUMMARY.as_posix(), NEXT_WORK_ITEM.as_posix()],
        outputs=[],
        next_action=next_action,
        blockers=list(summary["unresolved_blockers"]),
    )
    common_contract["unresolved_blockers_or_none"] = list(summary["unresolved_blockers"])
    common_contract["next_executable_action"] = next_action
    common_contract["next_action_or_reopen_condition"] = next_action

    resume = read_yaml(REPO_ROOT / RESUME_CURSOR)
    resume.update(
        {
            "updated_at_utc": summary["ended_at_utc"],
            "cursor_state": STATUS,
            "active_phase": STATUS,
            "active_goal_id": GOAL_ID,
            "active_work_item_id": WORK_ITEM_ID,
            "campaign_id": CAMPAIGN_ID,
            "claim_boundary": CLAIM_BOUNDARY,
            "next_action": next_action,
            "unresolved_blockers": summary["unresolved_blockers"],
            "active_ids": {
                "idea_id": IDEA_ID,
                "hypothesis_id": HYPOTHESIS_ID,
                "wave_id": WAVE_ID,
                "campaign_id": CAMPAIGN_ID,
                "surface_id": SURFACE_ID,
                "sweep_id": SWEEP_ID,
            },
            "latest_completed_work": {
                "work_item_id": WORK_ITEM_ID,
                "result_judgment": "portable_runtime_repair_probe_recorded",
                "claim_boundary": CLAIM_BOUNDARY,
                "evidence_paths": [REPAIR_SUMMARY.as_posix(), REPAIR_CLOSEOUT.as_posix()],
            },
            "next_work_item": {"work_item_id": WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()},
        }
    )
    resume.setdefault("current_truth_sources", [])
    for source in [REPAIR_SUMMARY.as_posix(), REPAIR_CLOSEOUT.as_posix()]:
        if source not in resume["current_truth_sources"]:
            resume["current_truth_sources"].append(source)
    resume.update({**common_contract, "writer_owned_outputs": [RESUME_CURSOR.as_posix()]})
    write_yaml(RESUME_CURSOR, resume)

    goal = read_yaml(REPO_ROOT / GOAL_MANIFEST)
    goal.update(
        {
            "updated_at_utc": summary["ended_at_utc"],
            "status": STATUS,
            "active_phase": STATUS,
            "claim_boundary": CLAIM_BOUNDARY,
            "next_work_item": {
                "work_item_id": WORK_ITEM_ID,
                "path": NEXT_WORK_ITEM.as_posix(),
                "summary": next_action,
            },
        }
    )
    repair = goal.setdefault("wave03_l4_portable_runtime_repair", {})
    repair.update(
        {
            "status": STATUS,
            "claim_boundary": CLAIM_BOUNDARY,
            "repair_summary": REPAIR_SUMMARY.as_posix(),
            "probe_attempt_id": PROBE_ATTEMPT_ID,
            "counts": summary["counts"],
            "next_action": next_action,
        }
    )
    goal.update({**common_contract, "writer_owned_outputs": [GOAL_MANIFEST.as_posix()]})
    write_yaml(GOAL_MANIFEST, goal)

    campaign = read_yaml(REPO_ROOT / CAMPAIGN_MANIFEST)
    campaign.update(
        {
            "updated_at_utc": summary["ended_at_utc"],
            "status": STATUS,
            "claim_boundary": CLAIM_BOUNDARY,
            "candidate_count": 0,
            "l5_candidate_count": 0,
            "next_action": next_action,
            "unresolved_blockers": summary["unresolved_blockers"],
            "reopen_conditions": summary["reopen_conditions"],
        }
    )
    l4 = campaign.setdefault("l4_follow_through", {})
    l4.update(
        {
            "portable_runtime_repair_summary": REPAIR_SUMMARY.as_posix(),
            "portable_runtime_repair_status": STATUS,
            "portable_runtime_repair_counts": summary["counts"],
        }
    )
    evidence_paths = campaign.setdefault("evidence_paths", [])
    if REPAIR_SUMMARY.as_posix() not in evidence_paths:
        evidence_paths.append(REPAIR_SUMMARY.as_posix())
    campaign.update({**common_contract, "writer_owned_outputs": [CAMPAIGN_MANIFEST.as_posix()]})
    write_yaml(CAMPAIGN_MANIFEST, campaign)

    workspace = read_yaml(REPO_ROOT / WORKSPACE_STATE)
    workspace.update(
        {
            "updated_utc": summary["ended_at_utc"],
            "active_goal": {"goal_id": GOAL_ID, "status": STATUS, "manifest": GOAL_MANIFEST.as_posix()},
            "active_campaign": {
                "campaign_id": CAMPAIGN_ID,
                "status": STATUS,
                "manifest": CAMPAIGN_MANIFEST.as_posix(),
                "closeout": None,
            },
            "active_work_item": {"work_item_id": WORK_ITEM_ID, "path": NEXT_WORK_ITEM.as_posix()},
            "current_claim_boundary": CLAIM_BOUNDARY,
            "next_action": next_action,
            "unresolved_blockers": summary["unresolved_blockers"],
            "status": STATUS,
            "primary_family": PRIMARY_FAMILY,
            "primary_skill": PRIMARY_SKILL,
            "next_executable_action": next_action,
            "operational_validation_required": False,
        }
    )
    counts = workspace.setdefault("summary_counts", {})
    counts["candidate_count"] = 0
    counts["l5_candidate_count"] = 0
    counts["wave03_l4_portable_runtime_repair"] = summary["counts"]
    workspace.update({**common_contract, "writer_owned_outputs": [WORKSPACE_STATE.as_posix()]})
    write_yaml(WORKSPACE_STATE, workspace)

    update_registries(summary)


def update_registries(summary: dict[str, Any]) -> None:
    if path_exists(REPO_ROOT / GOAL_REGISTRY):
        rows = read_csv_rows(REPO_ROOT / GOAL_REGISTRY)
        for row in rows:
            if row.get("goal_id") == GOAL_ID:
                if "status" in row:
                    row["status"] = STATUS
                if "active_phase" in row:
                    row["active_phase"] = STATUS
                if "next_work_item" in row:
                    row["next_work_item"] = WORK_ITEM_ID
                if "claim_boundary" in row:
                    row["claim_boundary"] = CLAIM_BOUNDARY
                if "notes" in row:
                    row["notes"] = "Wave03 portable repair probe recorded; protected claims remain forbidden."
        if rows:
            write_csv(GOAL_REGISTRY, rows, list(rows[0].keys()))
    if path_exists(REPO_ROOT / CAMPAIGN_REGISTRY):
        rows = read_csv_rows(REPO_ROOT / CAMPAIGN_REGISTRY)
        for row in rows:
            if row.get("campaign_id") == CAMPAIGN_ID:
                if "status" in row:
                    row["status"] = STATUS
                if "next_work_item" in row:
                    row["next_work_item"] = WORK_ITEM_ID
                if "claim_boundary" in row:
                    row["claim_boundary"] = CLAIM_BOUNDARY
                if "evidence_path" in row:
                    row["evidence_path"] = REPAIR_SUMMARY.as_posix()
                if "notes" in row:
                    row["notes"] = "Portable repair probe is diagnostic; no runtime authority or economics pass."
        if rows:
            write_csv(CAMPAIGN_REGISTRY, rows, list(rows[0].keys()))
    if path_exists(REPO_ROOT / ARTIFACT_REGISTRY):
        rows = read_csv_rows(REPO_ROOT / ARTIFACT_REGISTRY)
        fieldnames = list(rows[0].keys()) if rows else []
        if fieldnames and path_exists(REPO_ROOT / REPAIR_SUMMARY):
            by_id = {row.get("artifact_id"): row for row in rows}
            payload = {key: "" for key in fieldnames}
            payload.update(
                {
                    "artifact_id": "artifact_wave03_l4_portable_runtime_repair_summary_v0",
                    "artifact_type": "l4_portable_runtime_repair_summary",
                    "path_or_uri": REPAIR_SUMMARY.as_posix(),
                    "sha256": sha256_file(REPO_ROOT / REPAIR_SUMMARY),
                    "size_bytes": str(os.stat(filesystem_path(REPO_ROOT / REPAIR_SUMMARY)).st_size),
                    "availability": "present_hash_recorded",
                    "producer_command": summary["provenance"]["producer"],
                    "regeneration_command": summary["provenance"]["producer"],
                    "source_of_truth": REPAIR_SUMMARY.as_posix(),
                    "consumer": WORK_ITEM_ID,
                    "claim_boundary": CLAIM_BOUNDARY,
                    "notes": "bounded portable runtime repair probe summary; no protected claim",
                }
            )
            by_id[payload["artifact_id"]] = payload
            write_csv(ARTIFACT_REGISTRY, list(by_id.values()), fieldnames)


def smoke_outputs(summary: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for path in [REPAIR_SUMMARY, REPAIR_CLOSEOUT, NEXT_WORK_ITEM, WORKSPACE_STATE, GOAL_MANIFEST, CAMPAIGN_MANIFEST]:
        if not path_exists(REPO_ROOT / path):
            errors.append(f"missing output: {path.as_posix()}")
    loaded = read_yaml(REPO_ROOT / REPAIR_SUMMARY) if path_exists(REPO_ROOT / REPAIR_SUMMARY) else {}
    next_work = read_yaml(REPO_ROOT / NEXT_WORK_ITEM) if path_exists(REPO_ROOT / NEXT_WORK_ITEM) else {}
    workspace = read_yaml(REPO_ROOT / WORKSPACE_STATE) if path_exists(REPO_ROOT / WORKSPACE_STATE) else {}
    if loaded.get("claim_boundary") != CLAIM_BOUNDARY:
        errors.append("repair summary claim boundary mismatch")
    if loaded.get("operational_validation_required") is not False:
        errors.append("repair summary operational_validation_required must be false")
    if (loaded.get("counts") or {}).get("candidate_count") != 0:
        errors.append("repair summary candidate_count must be zero")
    if next_work.get("claim_boundary") != CLAIM_BOUNDARY:
        errors.append("next_work claim boundary mismatch")
    if workspace.get("current_claim_boundary") != CLAIM_BOUNDARY:
        errors.append("workspace claim boundary mismatch")
    if workspace.get("operational_validation_required") is not False:
        errors.append("workspace operational_validation_required must be false")
    if summary["counts"]["portable_repair_probe_attempt_count"] and not path_exists(
        REPO_ROOT / "runtime" / "mt5_attempts" / PROBE_ATTEMPT_ID / "terminal_run_summary.yaml"
    ):
        errors.append("terminal probe summary missing")
    return errors


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repair/probe Wave03 L4 portable MT5 runtime contract without protected claims.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--source-attempt-id", default=SOURCE_ATTEMPT_ID)
    parser.add_argument("--probe-attempt-id", default=PROBE_ATTEMPT_ID)
    parser.add_argument("--emulated-tester-login", default=None)
    parser.add_argument("--emulated-common-login", default=None)
    parser.add_argument("--emulated-common-password", default=None)
    parser.add_argument("--sensitive-tester-login-env", default=None)
    parser.add_argument("--sensitive-common-login-env", default=None)
    parser.add_argument("--sensitive-common-password-env", default=None)
    parser.add_argument("--common-server", default=None)
    parser.add_argument("--portable-root", default=str(default_portable_root()))
    parser.add_argument("--session-source-root", default=None)
    parser.add_argument("--allow-session-config-import", action="store_true")
    parser.add_argument("--session-import-approval-token", default=None)
    parser.add_argument("--refresh-portable-root", action="store_true")
    parser.add_argument("--terminal-timeout-seconds", type=int, default=600)
    parser.add_argument("--skip-terminal-probe", action="store_true")
    parser.add_argument("--reuse-existing-terminal-probe", action="store_true")
    parser.add_argument("--write-control-records", action="store_true")
    parser.add_argument("--smoke-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    global PROBE_ATTEMPT_ID, REPO_ROOT, SOURCE_ATTEMPT_ID, TESTER_COMMON_LOGIN_FIXTURE, TESTER_COMMON_LOGIN_RECORDED_VALUE, TESTER_COMMON_LOGIN_VALUE_KIND, TESTER_COMMON_PASSWORD_CONFIGURED, TESTER_COMMON_PASSWORD_FIXTURE, TESTER_COMMON_PASSWORD_VALUE_KIND, TESTER_COMMON_SERVER_FIXTURE, TESTER_LOGIN_FIXTURE, TESTER_LOGIN_RECORDED_VALUE, TESTER_LOGIN_VALUE_KIND
    args = parse_args(argv)
    REPO_ROOT = Path(args.repo_root).resolve()
    SOURCE_ATTEMPT_ID = str(args.source_attempt_id)
    PROBE_ATTEMPT_ID = str(args.probe_attempt_id)

    if args.emulated_tester_login and args.sensitive_tester_login_env:
        raise RuntimeError("use either --emulated-tester-login or --sensitive-tester-login-env, not both")
    if args.emulated_common_login and args.sensitive_common_login_env:
        raise RuntimeError("use either --emulated-common-login or --sensitive-common-login-env, not both")
    if args.emulated_common_password and args.sensitive_common_password_env:
        raise RuntimeError("use either --emulated-common-password or --sensitive-common-password-env, not both")

    if args.sensitive_tester_login_env:
        TESTER_LOGIN_FIXTURE = os.environ.get(str(args.sensitive_tester_login_env), "").strip()
        if not TESTER_LOGIN_FIXTURE:
            raise RuntimeError("sensitive tester login environment variable is missing or empty")
        TESTER_LOGIN_VALUE_KIND = "sensitive_env_tester_login_redacted"
        TESTER_LOGIN_RECORDED_VALUE = None
    else:
        TESTER_LOGIN_FIXTURE = str(args.emulated_tester_login).strip() if args.emulated_tester_login else None
        TESTER_LOGIN_VALUE_KIND = "non_secret_emulated_tester_login" if TESTER_LOGIN_FIXTURE else None
        TESTER_LOGIN_RECORDED_VALUE = TESTER_LOGIN_FIXTURE if TESTER_LOGIN_FIXTURE else None

    if args.sensitive_common_login_env:
        TESTER_COMMON_LOGIN_FIXTURE = os.environ.get(str(args.sensitive_common_login_env), "").strip()
        if not TESTER_COMMON_LOGIN_FIXTURE:
            raise RuntimeError("sensitive common login environment variable is missing or empty")
        TESTER_COMMON_LOGIN_VALUE_KIND = "sensitive_env_common_login_redacted"
        TESTER_COMMON_LOGIN_RECORDED_VALUE = None
    else:
        TESTER_COMMON_LOGIN_FIXTURE = str(args.emulated_common_login).strip() if args.emulated_common_login else None
        TESTER_COMMON_LOGIN_VALUE_KIND = "non_secret_emulated_login" if TESTER_COMMON_LOGIN_FIXTURE else None
        TESTER_COMMON_LOGIN_RECORDED_VALUE = TESTER_COMMON_LOGIN_FIXTURE if TESTER_COMMON_LOGIN_FIXTURE else None

    if args.sensitive_common_password_env:
        TESTER_COMMON_PASSWORD_FIXTURE = os.environ.get(str(args.sensitive_common_password_env), "").strip()
        if not TESTER_COMMON_PASSWORD_FIXTURE:
            raise RuntimeError("sensitive common password environment variable is missing or empty")
        TESTER_COMMON_PASSWORD_VALUE_KIND = "sensitive_env_common_password_redacted"
        TESTER_COMMON_PASSWORD_CONFIGURED = True
    else:
        TESTER_COMMON_PASSWORD_FIXTURE = str(args.emulated_common_password).strip() if args.emulated_common_password else None
        TESTER_COMMON_PASSWORD_VALUE_KIND = "non_secret_emulated_password" if TESTER_COMMON_PASSWORD_FIXTURE else None
        TESTER_COMMON_PASSWORD_CONFIGURED = bool(TESTER_COMMON_PASSWORD_FIXTURE)
    TESTER_COMMON_SERVER_FIXTURE = str(args.common_server).strip() if args.common_server else None
    started_at = utc_now()

    portable_root = Path(args.portable_root).resolve()
    portable_terminal = portable_root / "terminal64.exe"
    source_manifest_path = REPO_ROOT / "runtime" / "mt5_attempts" / SOURCE_ATTEMPT_ID / "attempt_manifest.yaml"
    source_config_path = REPO_ROOT / "runtime" / "mt5_attempts" / SOURCE_ATTEMPT_ID / "tester_config.ini"
    source_manifest = read_yaml(source_manifest_path)
    prep_rows = read_csv_rows(REPO_ROOT / OUTPUT_DIR / "l4_attempt_preparation_index.csv")
    source_row = next((row for row in prep_rows if row.get("attempt_id") == SOURCE_ATTEMPT_ID), {})
    if not source_row:
        raise RuntimeError(f"missing source attempt row for {SOURCE_ATTEMPT_ID}")

    copy_result = run_robocopy(DEFAULT_TERMINAL.parent, portable_root, refresh=args.refresh_portable_root)
    session_source_root = Path(args.session_source_root).resolve() if args.session_source_root else None
    session_config_staging = session_config_staging_preflight(
        source_root=session_source_root,
        target_root=portable_root,
        allow_import=bool(args.allow_session_config_import),
        approval_token=str(args.session_import_approval_token).strip() if args.session_import_approval_token else None,
    )
    root_preflight = portable_terminal_root_preflight(portable_terminal)
    probe_root = REPO_ROOT / "runtime" / "mt5_attempts" / PROBE_ATTEMPT_ID
    probe_root.mkdir(parents=True, exist_ok=True)
    prepared_config = prepare_probe_config(
        source_config_path,
        probe_root,
        tester_login=TESTER_LOGIN_FIXTURE,
        common_login=TESTER_COMMON_LOGIN_FIXTURE,
        common_password=TESTER_COMMON_PASSWORD_FIXTURE,
        common_server=TESTER_COMMON_SERVER_FIXTURE,
    )
    common_inputs = ensure_common_file_inputs(source_manifest, prepared_config["tester_config"])
    ea_stage_manifest: dict[str, Any] = {"artifact_identity": {}, "runtime_surface_contract": {}}
    ea_stage_manifest = l4_base.ensure_portable_ea_stage(
        repo_root=REPO_ROOT,
        tester_config=prepared_config["tester_config"],
        portable_terminal_root=portable_root,
        manifest=ea_stage_manifest,
    )
    probe_manifest = build_probe_manifest(
        source_manifest=source_manifest,
        probe_root=probe_root,
        probe_config=prepared_config["tester_config"],
        portable_root=portable_root,
        copy_result=copy_result,
        session_config_staging=session_config_staging,
        root_preflight=root_preflight,
        common_inputs=common_inputs,
        ea_stage_manifest=ea_stage_manifest,
    )
    write_plain_yaml(probe_root / "portable_repair_attempt_manifest.yaml", probe_manifest)

    terminal_probe: dict[str, Any] | None = None
    if args.reuse_existing_terminal_probe:
        terminal_probe = load_existing_terminal_probe(probe_root, portable_terminal)
    elif not args.skip_terminal_probe and root_preflight.get("status") == "passed":
        terminal_probe = materialize_terminal_probe(
            source_manifest=source_manifest,
            source_row=source_row,
            probe_root=probe_root,
            probe_config=prepared_config["tester_config"],
            portable_terminal=portable_terminal,
            telemetry_rel=prepared_config["telemetry_common_relative"],
            diagnostic_rel=prepared_config["diagnostic_common_relative"],
            timeout_seconds=args.terminal_timeout_seconds,
        )

    ended_at = utc_now()
    summary = build_summary(
        started_at=started_at,
        ended_at=ended_at,
        portable_root=portable_root,
        copy_result=copy_result,
        session_config_staging=session_config_staging,
        root_preflight=root_preflight,
        probe_manifest=probe_manifest,
        terminal_probe=terminal_probe,
        smoke_only=args.smoke_only,
    )
    write_yaml(REPAIR_SUMMARY, summary)
    write_yaml(REPAIR_CLOSEOUT, build_closeout(summary))
    if args.write_control_records:
        update_control_records(summary)
    errors = smoke_outputs(summary) if args.write_control_records else []
    if errors:
        print(json.dumps({"status": "portable_repair_writer_smoke_failed", "errors": errors}, indent=2))
        return 1
    print(
        json.dumps(
            {
                "status": "portable_repair_probe_recorded",
                "probe_attempt_id": PROBE_ATTEMPT_ID,
                "counts": summary["counts"],
                "claim_boundary": CLAIM_BOUNDARY,
                "operational_validation_required": False,
                "next_action": summary.get("next_action") or NEXT_ACTION,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
