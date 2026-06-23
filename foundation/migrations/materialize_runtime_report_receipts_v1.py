from __future__ import annotations

import argparse
import copy
import hashlib
import os
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation.migrations.runtime_graph_target_inventory import (
    EXPECTED_ATTEMPT_COUNT,
    EXPECTED_PAIR_GROUP_COUNT,
    EXPECTED_SURFACE_KIND_COUNTS,
    INVENTORY_REL_PATH,
    generate_runtime_graph_target_inventory,
    inventory_attempts,
    target_attempt_paths,
    validate_runtime_graph_target_inventory,
)
from foundation.mt5.runtime_completion import (
    RuntimeAttemptState,
    evaluate_runtime_attempt,
    reconstruct_runtime_attempt_from_records,
    runtime_status,
)
from foundation.mt5.tester_report_receipt import (
    HISTORICAL_FRESHNESS_EVIDENCE_CLASS,
    HISTORICAL_FRESHNESS_REASON,
    HISTORICAL_RECEIPT_PROVENANCE_CLASS,
    build_tester_report_receipt,
    file_sha256,
    load_receipt,
    manifest_tester_report_path,
    parse_utc,
    receipt_missing_requirements,
    tester_config_identity,
    tester_report_completed,
    timestamp_to_utc,
    validate_tester_report_receipt_binding,
)
from spacesonar.control_plane.models import ExecutionContext, TRANSACTION_SUCCESS_STATUSES
from spacesonar.control_plane.store import dump_csv, dump_yaml, filesystem_path, read_csv_rows, read_yaml, sha256_file
from spacesonar.control_plane.transaction import ControlPlaneTransaction


MIGRATION_ID = "runtime_graph_revalidation_inventory_bound_v1"
PREVIOUS_MIGRATION_ID = "materialize_runtime_report_receipts_v1"
WORK_ITEM_ID = "work_codex_control_plane_corrective_v3"
CLAIM_BOUNDARY = "corrective_wp03_runtime_graph_revalidation_no_runtime_authority_no_economics_pass"
REQUIRED_PERIOD_ROLES = ("validation", "research_oos")
ELIGIBLE_COMPLETION_SCOPES = ("full_period_deterministic", "full_period_sparse_decision_surface")
HISTORICAL_REPORT_END_TOLERANCE_SECONDS = 120
ARTIFACT_REGISTRY_REL_PATH = Path("docs/registers/artifact_registry.csv")


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def path_exists(path: Path) -> bool:
    return os.path.exists(filesystem_path(path))


def path_size(path: Path) -> int:
    return os.stat(filesystem_path(path)).st_size


def read_text(path: Path) -> str:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        return handle.read()


def telemetry_summary_path(attempt_root: Path, runtime_surface_kind: str | None = None) -> Path | None:
    names = (
        ("execution_telemetry_summary.yaml",)
        if runtime_surface_kind == "decision_replay"
        else ("score_telemetry_summary.yaml",)
        if runtime_surface_kind == "score_probe"
        else ("execution_telemetry_summary.yaml", "score_telemetry_summary.yaml")
    )
    for name in names:
        path = attempt_root / name
        if path_exists(path):
            return path
    return None


def runtime_surface_kind(manifest: dict[str, Any], telemetry_path: Path | None = None) -> str:
    surface_contract = manifest.get("runtime_surface_contract") or {}
    if isinstance(surface_contract, dict):
        explicit_kind = surface_contract.get("runtime_surface_kind")
        if explicit_kind in {"score_probe", "decision_replay"}:
            return str(explicit_kind)
    attempt_id = str(manifest.get("attempt_id") or "")
    if telemetry_path and telemetry_path.name == "execution_telemetry_summary.yaml":
        return "decision_replay"
    if "decision_replay" in attempt_id or manifest.get("adapter_id"):
        return "decision_replay"
    return "score_probe"


def completion_scope_for_kind(kind: str) -> str:
    return "full_period_sparse_decision_surface" if kind == "decision_replay" else "full_period_deterministic"


def telemetry_kind_for_status(kind: str) -> str:
    return "decision_replay_execution_telemetry" if kind == "decision_replay" else "telemetry"


def locate_manifest_report(repo_root: Path, manifest: dict[str, Any]) -> tuple[Path | None, dict[str, Any]]:
    report_record = manifest.get("tester_report") if isinstance(manifest.get("tester_report"), dict) else {}
    if not report_record:
        reports = (manifest.get("artifact_identity") or {}).get("tester_reports") or []
        report_record = next((item for item in reports if isinstance(item, dict) and item.get("path")), {})
    rel_path = str(report_record.get("path") or "")
    if not rel_path:
        return None, report_record
    path = repo_root / rel_path
    return (path if path_exists(path) else None), report_record


def tester_config_path(repo_root: Path, attempt_root: Path, manifest: dict[str, Any]) -> Path:
    tester_config_ref = (manifest.get("artifact_identity") or {}).get("tester_config") or {}
    rel_path = str(tester_config_ref.get("path") or "")
    if rel_path and path_exists(repo_root / rel_path):
        return repo_root / rel_path
    return attempt_root / "tester_config.ini"


def tester_config_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path_exists(path):
        return values
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        for line in handle.read().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(";") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip().lower()] = value.strip()
    return values


def replace_report_enabled(path: Path) -> bool:
    value = tester_config_values(path).get("replacereport", "")
    return value.strip().lower() in {"1", "true", "yes"}


def report_hash_matches(report_path: Path | None, report_record: dict[str, Any]) -> bool | None:
    if report_path is None or not path_exists(report_path):
        return None
    expected = report_record.get("sha256")
    if not expected:
        return None
    return file_sha256(report_path) == str(expected)


def expected_report_size_matches(report_path: Path | None, report_record: dict[str, Any]) -> bool | None:
    if report_path is None or not path_exists(report_path):
        return None
    expected = report_record.get("size_bytes")
    if expected in (None, ""):
        return None
    try:
        return path_size(report_path) == int(expected)
    except (TypeError, ValueError):
        return False


def source_report_attempt_specific(source_report_path: str | None, attempt_id: str) -> bool:
    if not source_report_path:
        return False
    normalized = source_report_path.replace("\\", "/")
    return normalized.startswith(f"runtime/mt5_attempts/{attempt_id}/reports/")


def mtime_checks(
    *,
    report_path: Path | None,
    terminal_summary: dict[str, Any],
) -> tuple[bool, bool]:
    if report_path is None or not path_exists(report_path):
        return False, False
    source_mtime = datetime.fromtimestamp(os.stat(filesystem_path(report_path)).st_mtime, tz=UTC)
    launch_started = parse_utc(terminal_summary.get("started_at_utc"))
    launch_ended = parse_utc(terminal_summary.get("ended_at_utc"))
    after_start = bool(launch_started and source_mtime >= launch_started)
    before_end = bool(launch_ended and source_mtime <= launch_ended + _seconds(HISTORICAL_REPORT_END_TOLERANCE_SECONDS))
    return after_start, before_end


def _seconds(value: int):
    from datetime import timedelta

    return timedelta(seconds=value)


def build_historical_receipt_for_attempt(
    *,
    repo_root: Path,
    attempt_path: Path,
    manifest: dict[str, Any],
    terminal_summary: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    attempt_root = attempt_path.parent
    attempt_id = str(manifest.get("attempt_id") or attempt_root.name)
    report_path, report_record = locate_manifest_report(repo_root, manifest)
    config_path = tester_config_path(repo_root, attempt_root, manifest)
    expected_identity = tester_config_identity(config_path)
    source_report_path = manifest_tester_report_path(manifest)
    observed_at = timestamp_to_utc(os.stat(filesystem_path(report_path)).st_mtime) if report_path else str(
        terminal_summary.get("ended_at_utc") or terminal_summary.get("started_at_utc") or utc_now()
    )
    receipt = build_tester_report_receipt(
        attempt_id=attempt_id,
        report_path=report_path,
        source_origin="attempt_archive_path" if report_path is not None else None,
        launch_started_at_utc=terminal_summary.get("started_at_utc"),
        report_observed_at_utc=observed_at,
        prelaunch_candidates=(),
        expected_identity=expected_identity,
        claim_boundary="tester_report_receipt_only_no_runtime_authority_no_economics_pass",
    )
    hash_match = report_hash_matches(report_path, report_record)
    size_match = expected_report_size_matches(report_path, report_record)
    after_start, before_end = mtime_checks(report_path=report_path, terminal_summary=terminal_summary)
    replace_enabled = replace_report_enabled(config_path)
    attempt_specific = source_report_attempt_specific(source_report_path, attempt_id)
    checks = {
        "raw_report_existed_at_materialization": bool(report_path),
        "stored_report_sha256_present": bool(report_record.get("sha256")),
        "stored_report_sha256_match": hash_match is True,
        "stored_report_size_present": report_record.get("size_bytes") not in (None, ""),
        "stored_report_size_match": size_match is True,
        "mtime_at_or_after_launch_start": after_start,
        "mtime_at_or_before_launch_end_plus_tolerance": before_end,
        "replace_report_enabled": replace_enabled,
        "source_report_attempt_specific": attempt_specific,
    }
    receipt.update(
        {
            "source_report_path": source_report_path,
            "stored_report_sha256": report_record.get("sha256"),
            "stored_report_sha256_match": hash_match,
            "stored_report_size_bytes": report_record.get("size_bytes"),
            "stored_report_size_match": size_match,
            "launch_ended_at_utc": terminal_summary.get("ended_at_utc"),
            "launch_end_tolerance_seconds": HISTORICAL_REPORT_END_TOLERANCE_SECONDS,
            "replace_report_enabled": replace_enabled,
            "prelaunch_observation_available": False,
            "historical_freshness_checks": checks,
            "freshness_evidence_class": HISTORICAL_FRESHNESS_EVIDENCE_CLASS,
            "freshness_reason": HISTORICAL_FRESHNESS_REASON,
            "report_fresh_for_launch": all(checks.values()),
            "source_report_attempt_specific": attempt_specific,
            "receipt_provenance_class": HISTORICAL_RECEIPT_PROVENANCE_CLASS,
            "migration_id": MIGRATION_ID,
        }
    )
    receipt["tester_report_completed"] = tester_report_completed(receipt)
    receipt["missing_requirements"] = receipt_missing_requirements(receipt, expected_identity)
    diagnostics = {
        "report_path": source_report_path,
        "report_hash_match": hash_match,
        "report_size_match": size_match,
        "replace_report_enabled": replace_enabled,
        "source_report_attempt_specific": attempt_specific,
        "expected_identity_missing_fields": receipt.get("expected_identity_missing_fields") or [],
        "receipt_completed": receipt.get("tester_report_completed"),
    }
    return receipt, diagnostics


def execution_state_payload(state: RuntimeAttemptState, result) -> dict[str, Any]:
    return {
        "terminal_launched": state.terminal_launched,
        "telemetry_file_observed": state.telemetry_file_observed,
        "telemetry_rows_observed": state.telemetry_rows_observed,
        "tester_report_observed": state.tester_report_observed,
        "tester_report_completed": state.tester_report_completed,
        "terminal_mode": state.terminal_mode,
        "portable_contract_satisfied": result.portable_contract_satisfied,
        "report_contract_satisfied": result.report_contract_satisfied,
        "period_contract_satisfied": result.period_contract_satisfied,
        "surface_contract_satisfied": result.surface_contract_satisfied,
        "runtime_probe_complete": result.runtime_probe_complete,
        "missing_requirements": list(result.missing_requirements),
        "completion_claim_boundary": result.claim_boundary,
    }


def receipt_ref(repo_root: Path, receipt_path: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    payload = dump_yaml(receipt).encode("utf-8")
    return {
        "path": receipt_path.relative_to(repo_root).as_posix(),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
        "availability": "present_hash_recorded",
        "migration_id": MIGRATION_ID,
    }


def has_migration(manifest: dict[str, Any]) -> bool:
    return any(item.get("migration_id") == MIGRATION_ID for item in manifest.get("migration_history", []) or [])


def load_receipt_or_materialize(
    *,
    repo_root: Path,
    entry: dict[str, Any],
    manifest: dict[str, Any],
    terminal_summary: dict[str, Any],
    rebuild_from_raw: bool,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    attempt_path = repo_root / str(entry["manifest_path"])
    receipt_path = repo_root / str(entry["expected_tester_report_receipt_path"])
    if path_exists(receipt_path) and not rebuild_from_raw:
        receipt = load_receipt(receipt_path)
        return receipt, {"receipt_completed": tester_report_completed(receipt), "used_committed_receipt": True}, False
    receipt, diagnostics = build_historical_receipt_for_attempt(
        repo_root=repo_root,
        attempt_path=attempt_path,
        manifest=manifest,
        terminal_summary=terminal_summary,
    )
    diagnostics["used_committed_receipt"] = False
    return receipt, diagnostics, bool(receipt.get("source_report_sha256"))


def migrated_manifest(
    *,
    repo_root: Path,
    entry: dict[str, Any],
    executed_at_utc: str,
    rebuild_from_raw: bool,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], bool]:
    attempt_path = repo_root / str(entry["manifest_path"])
    manifest = read_yaml(attempt_path)
    previous_sha = sha256_file(attempt_path)
    previous_status = str(manifest.get("status") or "")
    attempt_root = attempt_path.parent
    kind = str(entry["runtime_surface_kind"])
    terminal_path = repo_root / str(entry["expected_terminal_summary_path"])
    telemetry_path = repo_root / str(entry["expected_telemetry_summary_path"])
    terminal_summary = read_yaml(terminal_path) if path_exists(terminal_path) else {}
    telemetry_summary = read_yaml(telemetry_path) if path_exists(telemetry_path) else {}
    receipt, receipt_diagnostics, receipt_materialized = load_receipt_or_materialize(
        repo_root=repo_root,
        entry=entry,
        manifest=manifest,
        terminal_summary=terminal_summary,
        rebuild_from_raw=rebuild_from_raw,
    )
    updated = copy.deepcopy(manifest)
    surface_contract = updated.setdefault("runtime_surface_contract", {})
    surface_contract["completion_surface_scope"] = completion_scope_for_kind(kind)
    surface_contract["runtime_surface_kind"] = kind
    receipt_path = repo_root / str(entry["expected_tester_report_receipt_path"])
    if receipt:
        updated["tester_report_receipt"] = receipt_ref(repo_root, receipt_path, receipt)
    state = reconstruct_runtime_attempt_from_records(
        attempt_manifest=updated,
        terminal_summary=terminal_summary,
        telemetry_summary=telemetry_summary,
        report_receipt=receipt,
    )
    result = evaluate_runtime_attempt(
        state,
        required_period_roles=REQUIRED_PERIOD_ROLES,
        completion_eligible_surface_scopes=ELIGIBLE_COMPLETION_SCOPES,
    )
    updated["execution_state"] = execution_state_payload(state, result)
    updated["status"] = runtime_status(result, telemetry_kind=telemetry_kind_for_status(kind))
    missing_evidence = [
        item
        for item in list(updated.get("missing_evidence") or [])
        if not str(item).startswith(("runtime_completion_missing:", "tester_report_receipt_missing:"))
    ]
    for requirement in receipt.get("missing_requirements") or ["tester_report_receipt_missing"]:
        item = f"tester_report_receipt_missing:{requirement}"
        if item not in missing_evidence:
            missing_evidence.append(item)
    if not result.runtime_probe_complete:
        for requirement in result.missing_requirements:
            item = f"runtime_completion_missing:{requirement}"
            if item not in missing_evidence:
                missing_evidence.append(item)
    updated["missing_evidence"] = missing_evidence
    if not has_migration(updated):
        updated.setdefault("migration_history", []).append(
            {
                "migration_id": MIGRATION_ID,
                "previous_sha256": previous_sha,
                "previous_status": previous_status,
                "reason": "inventory_bound_runtime_graph_revalidation_with_historical_receipt_binding",
                "executed_at_utc": executed_at_utc,
                "preserves_previous_migration_id": PREVIOUS_MIGRATION_ID,
            }
        )
    binding_errors = (
        []
        if receipt_materialized
        else validate_tester_report_receipt_binding(updated, receipt, receipt_path)
        if receipt
        else ["tester_report_receipt_missing"]
    )
    diagnostics = {
        "attempt_id": str(updated.get("attempt_id") or attempt_root.name),
        "attempt_manifest": entry["manifest_path"],
        "receipt_path": entry["expected_tester_report_receipt_path"],
        "telemetry_summary": entry["expected_telemetry_summary_path"],
        "runtime_surface_kind": kind,
        "period_role": state.period_role,
        "runtime_probe_complete": result.runtime_probe_complete,
        "missing_requirements": list(result.missing_requirements),
        "receipt_binding_errors": binding_errors,
        **receipt_diagnostics,
    }
    return updated, receipt, diagnostics, receipt_materialized


def pair_key(manifest: dict[str, Any], diagnostics: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(manifest.get("campaign_id") or ""),
        str(manifest.get("cell_id") or ""),
        str(diagnostics.get("runtime_surface_kind") or ""),
    )


def pair_counts(records: list[tuple[dict[str, Any], dict[str, Any]]]) -> tuple[int, int]:
    grouped: dict[tuple[str, str, str], dict[str, bool]] = {}
    for manifest, diagnostics in records:
        key = pair_key(manifest, diagnostics)
        role = str(diagnostics.get("period_role") or "")
        complete = bool(diagnostics.get("runtime_probe_complete"))
        grouped.setdefault(key, {})[role] = grouped.setdefault(key, {}).get(role, False) or complete
    complete_count = 0
    incomplete_count = 0
    for roles in grouped.values():
        if all(roles.get(role) for role in REQUIRED_PERIOD_ROLES):
            complete_count += 1
        else:
            incomplete_count += 1
    return complete_count, incomplete_count


def payload_bytes(payload: dict[str, Any]) -> bytes:
    return dump_yaml(payload).encode("utf-8")


def desired_hash_and_size(repo_root: Path, rel_path: str, payloads: dict[str, dict[str, Any]]) -> tuple[str, int]:
    if rel_path in payloads:
        data = payload_bytes(payloads[rel_path])
        return hashlib.sha256(data).hexdigest(), len(data)
    path = repo_root / rel_path
    return sha256_file(path), path_size(path)


def receipt_artifact_row(
    *,
    repo_root: Path,
    manifest: dict[str, Any],
    entry: dict[str, Any],
    payloads: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    rel_path = str(entry["expected_tester_report_receipt_path"])
    sha, size = desired_hash_and_size(repo_root, rel_path, payloads)
    attempt_id = str(entry["attempt_id"])
    return {
        "artifact_id": f"artifact_{attempt_id}_tester_report_receipt_v0",
        "run_id": manifest.get("run_id", ""),
        "bundle_id": manifest.get("bundle_id", ""),
        "attempt_id": attempt_id,
        "artifact_type": "tester_report_receipt",
        "path_or_uri": rel_path,
        "sha256": sha,
        "size_bytes": size,
        "availability": "present_hash_recorded",
        "producer_command": "python foundation/migrations/materialize_runtime_report_receipts_v1.py --repo-root . --write --rebuild-from-raw",
        "regeneration_command": "python foundation/migrations/materialize_runtime_report_receipts_v1.py --repo-root . --write --rebuild-from-raw",
        "source_of_truth": entry["manifest_path"],
        "consumer": WORK_ITEM_ID,
        "claim_boundary": "tester_report_receipt_only_no_runtime_authority_no_economics_pass",
        "notes": "Corrective WP03 receipt; original MT5 execution provenance remains in attempt manifest and terminal/report records.",
    }


def updated_artifact_registry(
    repo_root: Path,
    inventory: dict[str, Any],
    manifest_payloads: dict[str, dict[str, Any]],
    receipt_payloads: dict[str, dict[str, Any]],
) -> tuple[str, int]:
    registry_path = repo_root / ARTIFACT_REGISTRY_REL_PATH
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
    attempts = inventory_attempts(inventory)
    manifest_paths = {str(item["manifest_path"]) for item in attempts}
    receipt_paths = {str(item["expected_tester_report_receipt_path"]) for item in attempts}
    payloads = {**manifest_payloads, **receipt_payloads}
    receipt_rows_by_manifest = {
        str(item["manifest_path"]): receipt_artifact_row(
            repo_root=repo_root,
            manifest=manifest_payloads[str(item["manifest_path"])],
            entry=item,
            payloads=payloads,
        )
        for item in attempts
    }
    output: list[dict[str, Any]] = []
    inserted_receipts: set[str] = set()
    for row in rows:
        rel_path = row.get("path_or_uri", "")
        if rel_path in receipt_paths:
            continue
        updated = dict(row)
        if rel_path in manifest_paths:
            sha, size = desired_hash_and_size(repo_root, rel_path, payloads)
            updated["sha256"] = sha
            updated["size_bytes"] = size
        output.append(updated)
        if rel_path in receipt_rows_by_manifest:
            receipt_row = receipt_rows_by_manifest[rel_path]
            if receipt_row["path_or_uri"] not in inserted_receipts:
                output.append(receipt_row)
                inserted_receipts.add(receipt_row["path_or_uri"])
    for manifest_path in sorted(set(receipt_rows_by_manifest) - {row.get("path_or_uri", "") for row in output}):
        receipt_row = receipt_rows_by_manifest[manifest_path]
        if receipt_row["path_or_uri"] not in inserted_receipts:
            output.append(receipt_row)
    receipt_row_count = sum(1 for row in output if row.get("path_or_uri") in receipt_paths)
    return dump_csv(fieldnames, output), receipt_row_count


def build_updates(
    repo_root: Path,
    executed_at_utc: str,
    *,
    rebuild_from_raw: bool,
) -> tuple[list[tuple[Path, dict[str, Any] | str]], dict[str, Any]]:
    inventory = generate_runtime_graph_target_inventory(repo_root)
    inventory_errors = validate_runtime_graph_target_inventory(repo_root, inventory)
    updates: list[tuple[Path, dict[str, Any] | str]] = [(INVENTORY_REL_PATH, inventory)]
    records: list[tuple[dict[str, Any], dict[str, Any]]] = []
    diagnostics: list[dict[str, Any]] = []
    receipt_count = 0
    binding_failures = 0
    manifest_payloads: dict[str, dict[str, Any]] = {}
    receipt_payloads: dict[str, dict[str, Any]] = {}
    for entry in inventory_attempts(inventory):
        manifest, receipt, attempt_diagnostics, receipt_materialized = migrated_manifest(
            repo_root=repo_root,
            entry=entry,
            executed_at_utc=executed_at_utc,
            rebuild_from_raw=rebuild_from_raw,
        )
        records.append((manifest, attempt_diagnostics))
        diagnostics.append(attempt_diagnostics)
        if receipt_materialized or receipt.get("source_report_sha256"):
            receipt_count += 1
        if attempt_diagnostics["receipt_binding_errors"]:
            binding_failures += 1
        manifest_rel = str(entry["manifest_path"])
        receipt_rel = str(entry["expected_tester_report_receipt_path"])
        manifest_payloads[manifest_rel] = manifest
        updates.append((Path(manifest_rel), manifest))
        if receipt:
            receipt_payloads[receipt_rel] = receipt
            updates.append((Path(receipt_rel), receipt))
    registry_csv, receipt_artifact_row_count = updated_artifact_registry(
        repo_root,
        inventory,
        manifest_payloads,
        receipt_payloads,
    )
    updates.append((ARTIFACT_REGISTRY_REL_PATH, registry_csv))
    complete_count = sum(1 for _, item in records if item.get("runtime_probe_complete"))
    incomplete_count = len(records) - complete_count
    pair_complete, pair_incomplete = pair_counts(records)
    surface_counts = Counter(str(item.get("runtime_surface_kind") or "") for _, item in records)
    summary = {
        "migration_id": MIGRATION_ID,
        "attempts_examined": len(records),
        "expected_attempt_count": EXPECTED_ATTEMPT_COUNT,
        "report_receipts_created": receipt_count,
        "report_receipts_missing": EXPECTED_ATTEMPT_COUNT - receipt_count,
        "attempts_complete": complete_count,
        "attempts_incomplete": incomplete_count,
        "pair_groups_complete": pair_complete,
        "pair_groups_incomplete": pair_incomplete,
        "expected_pair_group_count": EXPECTED_PAIR_GROUP_COUNT,
        "surface_kind_counts": dict(sorted(surface_counts.items())),
        "expected_surface_kind_counts": EXPECTED_SURFACE_KIND_COUNTS,
        "inventory_errors": inventory_errors,
        "receipt_binding_failure_count": binding_failures,
        "receipt_artifact_row_count": receipt_artifact_row_count,
        "diagnostics": diagnostics,
    }
    return updates, summary


def serialized_update(repo_root: Path, rel_path: Path, payload: dict[str, Any] | str) -> str:
    del repo_root, rel_path
    return payload if isinstance(payload, str) else dump_yaml(payload)


def existing_text(repo_root: Path, rel_path: Path) -> str | None:
    path = repo_root / rel_path
    if not path_exists(path):
        return None
    return read_text(path)


def validate_receipt_artifact_rows(repo_root: Path) -> list[str]:
    errors: list[str] = []
    inventory = generate_runtime_graph_target_inventory(repo_root)
    receipt_paths = {str(item["expected_tester_report_receipt_path"]) for item in inventory_attempts(inventory)}
    rows = read_csv_rows(repo_root / ARTIFACT_REGISTRY_REL_PATH)
    matched = [row for row in rows if row.get("path_or_uri") in receipt_paths]
    if len(matched) != EXPECTED_ATTEMPT_COUNT:
        errors.append(f"artifact_registry.csv: tester_report_receipt rows expected=86 observed={len(matched)}")
    for row in matched:
        path = repo_root / str(row.get("path_or_uri") or "")
        if not path_exists(path):
            errors.append(f"artifact_registry.csv {row.get('artifact_id')}: missing receipt path {row.get('path_or_uri')}")
            continue
        if row.get("sha256") != sha256_file(path):
            errors.append(f"artifact_registry.csv {row.get('artifact_id')}: receipt sha256 mismatch")
        if str(row.get("size_bytes")) != str(path_size(path)):
            errors.append(f"artifact_registry.csv {row.get('artifact_id')}: receipt size mismatch")
    return errors


def validate_runtime_graph_transaction(repo_root: Path) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_runtime_graph_target_inventory(repo_root))
    from foundation.validation.active_record_validator import validate_runtime_completion_truth

    errors.extend(validate_runtime_completion_truth(repo_root))
    errors.extend(validate_receipt_artifact_rows(repo_root))
    from foundation.evaluation.runtime_contract_evaluator import evaluate_runtime_contract

    evaluator_result = evaluate_runtime_contract(repo_root)
    if evaluator_result.get("status") != "passed":
        errors.append("runtime_contract_evaluator_v2 did not pass in transaction future tree")
    return errors


def run(
    repo_root: Path,
    *,
    write: bool,
    rebuild_from_raw: bool = False,
    fail_after_replace_count: int | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    executed_at = utc_now()
    updates, summary = build_updates(repo_root, executed_at, rebuild_from_raw=rebuild_from_raw)
    changed_updates = [
        (rel_path, payload)
        for rel_path, payload in updates
        if existing_text(repo_root, rel_path) != serialized_update(repo_root, rel_path, payload)
    ]
    summary["mode"] = "write" if write else "check"
    summary["rebuild_from_raw"] = rebuild_from_raw
    summary["changed_record_count"] = len(changed_updates)
    summary["transaction_status"] = "not_requested"
    summary["transaction_receipt_path"] = None
    summary["transaction_errors"] = []
    if write and changed_updates:
        context = ExecutionContext(
            repo_root=repo_root,
            work_item_id=WORK_ITEM_ID,
            claim_boundary=CLAIM_BOUNDARY,
            command_argv=("materialize_runtime_report_receipts_v1", "--write"),
            validation_commands=("validate_runtime_graph_transaction",),
        )
        tx = ControlPlaneTransaction(context)
        for rel_path, payload in changed_updates:
            if isinstance(payload, str):
                tx.stage_text(rel_path, payload)
            else:
                tx.stage_yaml(rel_path, payload)
        result = tx.commit(
            validate=lambda future_root: validate_runtime_graph_transaction(future_root),
            fail_after_replace_count=fail_after_replace_count,
        )
        summary["transaction_status"] = result.status
        summary["transaction_receipt_path"] = result.receipt_path.relative_to(repo_root).as_posix()
        summary["transaction_errors"] = list(result.errors)
    elif write:
        summary["transaction_status"] = "noop_already_applied"
    summary["claim_boundary"] = CLAIM_BOUNDARY
    return summary


def check_passed(result: dict[str, Any]) -> bool:
    return all(
        [
            result.get("changed_record_count") == 0,
            result.get("attempts_examined") == EXPECTED_ATTEMPT_COUNT,
            result.get("pair_groups_complete") == EXPECTED_PAIR_GROUP_COUNT,
            result.get("pair_groups_incomplete") == 0,
            result.get("attempts_incomplete") == 0,
            result.get("receipt_binding_failure_count") == 0,
            not result.get("inventory_errors"),
        ]
    )


def write_passed(result: dict[str, Any]) -> bool:
    return result.get("transaction_status") in TRANSACTION_SUCCESS_STATUSES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize runtime tester report receipts and revalidate attempts.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--rebuild-from-raw", action="store_true")
    parser.add_argument("--fail-after-replace-count", type=int)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--write", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run(
        Path(args.repo_root),
        write=args.write,
        rebuild_from_raw=args.rebuild_from_raw,
        fail_after_replace_count=args.fail_after_replace_count,
    )
    print(yaml.safe_dump(result, sort_keys=False, allow_unicode=False))
    return 0 if (write_passed(result) if args.write else check_passed(result)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
