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

from foundation.mt5.runtime_completion import (
    RuntimeAttemptState,
    evaluate_runtime_attempt,
    reconstruct_runtime_attempt_from_records,
    runtime_status,
)
from foundation.mt5.tester_report_receipt import (
    build_tester_report_receipt,
    file_sha256,
    path_key,
    receipt_missing_requirements,
    tester_config_identity,
    tester_report_completed,
    timestamp_to_utc,
)
from spacesonar.control_plane.models import ExecutionContext
from spacesonar.control_plane.store import dump_yaml, filesystem_path, read_yaml, sha256_file
from spacesonar.control_plane.transaction import ControlPlaneTransaction


MIGRATION_ID = "materialize_runtime_report_receipts_v1"
WORK_ITEM_ID = "work_codex_control_plane_corrective_v3"
CLAIM_BOUNDARY = "corrective_wp03_runtime_graph_revalidation_no_runtime_authority_no_economics_pass"
REQUIRED_PERIOD_ROLES = ("validation", "research_oos")
ELIGIBLE_COMPLETION_SCOPES = ("full_period_deterministic", "full_period_sparse_decision_surface")


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def path_exists(path: Path) -> bool:
    return os.path.exists(filesystem_path(path))


def read_text(path: Path) -> str:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        return handle.read()


def target_attempt_paths(repo_root: Path) -> list[Path]:
    paths: list[Path] = []
    attempt_root = repo_root / "runtime" / "mt5_attempts"
    if not path_exists(attempt_root):
        return paths
    for dirpath, _dirnames, filenames in os.walk(filesystem_path(attempt_root)):
        if "attempt_manifest.yaml" not in filenames:
            continue
        rel_dir = Path(os.path.relpath(dirpath, filesystem_path(attempt_root)))
        path = attempt_root / rel_dir / "attempt_manifest.yaml"
        manifest = read_yaml(path)
        attempt_id = str(manifest.get("attempt_id") or path.parent.name)
        if (
            manifest.get("execution_state") is not None
            and "l4" in attempt_id
            and (attempt_id.startswith("attempt_wave0") or attempt_id.startswith("attempt_wave01"))
        ):
            paths.append(path)
    return paths


def telemetry_summary_path(attempt_root: Path) -> Path | None:
    for name in ("execution_telemetry_summary.yaml", "score_telemetry_summary.yaml"):
        path = attempt_root / name
        if path_exists(path):
            return path
    return None


def runtime_surface_kind(manifest: dict[str, Any], telemetry_path: Path | None) -> str:
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


def locate_report(repo_root: Path, attempt_root: Path, manifest: dict[str, Any]) -> tuple[Path | None, dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    tester_report = manifest.get("tester_report")
    if isinstance(tester_report, dict):
        candidates.append(tester_report)
    for item in (manifest.get("artifact_identity") or {}).get("tester_reports") or []:
        if isinstance(item, dict):
            candidates.append(item)
    for candidate in candidates:
        rel_path = candidate.get("path")
        if not rel_path:
            continue
        path = repo_root / str(rel_path)
        if path_exists(path):
            return path, candidate
    for suffix in (".htm", ".html", ".xml"):
        fallback = attempt_root / "reports" / f"tester_report{suffix}"
        if path_exists(fallback):
            return fallback, {}
    return None, candidates[0] if candidates else {}


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
        return report_path.stat().st_size == int(expected)
    except (TypeError, ValueError):
        return False


def deterministic_observed_at(report_path: Path | None, terminal_summary: dict[str, Any]) -> str:
    if report_path is not None and path_exists(report_path):
        return timestamp_to_utc(report_path.stat().st_mtime)
    return str(terminal_summary.get("ended_at_utc") or terminal_summary.get("started_at_utc") or utc_now())


def historical_absent_prelaunch_snapshot(report_path: Path | None) -> list[dict[str, Any]]:
    if report_path is None:
        return []
    return [
        {
            "path_key": path_key(report_path),
            "origin": "attempt_archive_path",
            "existed": False,
            "sha256": None,
            "size_bytes": None,
            "mtime_ns": None,
            "mtime_utc": None,
            "migration_basis": "historical_attempt_archive_absence_before_report_materialization",
        }
    ]


def build_receipt_for_attempt(
    *,
    repo_root: Path,
    attempt_path: Path,
    manifest: dict[str, Any],
    terminal_summary: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    attempt_root = attempt_path.parent
    attempt_id = str(manifest.get("attempt_id") or attempt_root.name)
    report_path, report_record = locate_report(repo_root, attempt_root, manifest)
    tester_config_ref = (manifest.get("artifact_identity") or {}).get("tester_config") or {}
    tester_config_path = repo_root / str(tester_config_ref.get("path") or attempt_root / "tester_config.ini")
    if not path_exists(tester_config_path):
        tester_config_path = attempt_root / "tester_config.ini"
    expected_identity = tester_config_identity(tester_config_path)
    receipt = build_tester_report_receipt(
        attempt_id=attempt_id,
        report_path=report_path,
        source_origin="attempt_archive_path" if report_path is not None else None,
        launch_started_at_utc=terminal_summary.get("started_at_utc"),
        report_observed_at_utc=deterministic_observed_at(report_path, terminal_summary),
        prelaunch_candidates=historical_absent_prelaunch_snapshot(report_path),
        expected_identity=expected_identity,
        claim_boundary="tester_report_receipt_only_no_runtime_authority_no_economics_pass",
    )
    hash_match = report_hash_matches(report_path, report_record)
    size_match = expected_report_size_matches(report_path, report_record)
    receipt["source_report_path"] = (
        report_path.relative_to(repo_root).as_posix() if report_path is not None and report_path.is_relative_to(repo_root) else None
    )
    receipt["stored_report_sha256"] = report_record.get("sha256")
    receipt["stored_report_sha256_match"] = hash_match
    receipt["stored_report_size_bytes"] = report_record.get("size_bytes")
    receipt["stored_report_size_match"] = size_match
    receipt["migration_id"] = MIGRATION_ID
    receipt["migration_freshness_basis"] = "historical_attempt_archive_hash_verified_and_mtime_after_launch"
    if hash_match is False:
        receipt["tester_report_completed"] = False
        missing = list(receipt.get("missing_requirements") or [])
        if "stored_report_sha256_match" not in missing:
            missing.append("stored_report_sha256_match")
        receipt["missing_requirements"] = missing
    else:
        receipt["missing_requirements"] = receipt_missing_requirements(receipt, expected_identity)
        receipt["tester_report_completed"] = tester_report_completed(receipt)
    diagnostics = {
        "report_path": receipt.get("source_report_path"),
        "report_hash_match": hash_match,
        "report_size_match": size_match,
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


def migrated_manifest(
    *,
    repo_root: Path,
    attempt_path: Path,
    executed_at_utc: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest = read_yaml(attempt_path)
    previous_sha = sha256_file(attempt_path)
    previous_status = str(manifest.get("status") or "")
    attempt_root = attempt_path.parent
    terminal_path = attempt_root / "terminal_run_summary.yaml"
    telemetry_path = telemetry_summary_path(attempt_root)
    terminal_summary = read_yaml(terminal_path) if path_exists(terminal_path) else {}
    telemetry_summary = read_yaml(telemetry_path) if telemetry_path else {}
    receipt, receipt_diagnostics = build_receipt_for_attempt(
        repo_root=repo_root,
        attempt_path=attempt_path,
        manifest=manifest,
        terminal_summary=terminal_summary,
    )
    kind = runtime_surface_kind(manifest, telemetry_path)
    updated = copy.deepcopy(manifest)
    surface_contract = updated.setdefault("runtime_surface_contract", {})
    surface_contract["completion_surface_scope"] = completion_scope_for_kind(kind)
    surface_contract["runtime_surface_kind"] = kind
    receipt_path = attempt_root / "tester_report_receipt.yaml"
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
    missing_evidence = list(updated.get("missing_evidence") or [])
    missing_evidence = [item for item in missing_evidence if not str(item).startswith("runtime_completion_missing:")]
    missing_evidence = [item for item in missing_evidence if not str(item).startswith("tester_report_receipt_missing:")]
    for requirement in receipt.get("missing_requirements") or []:
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
                "reason": "materialize_report_receipt_and_reconstruct_runtime_completion_from_durable_evidence",
                "executed_at_utc": executed_at_utc,
            }
        )
    diagnostics = {
        "attempt_id": str(updated.get("attempt_id") or attempt_root.name),
        "attempt_manifest": attempt_path.relative_to(repo_root).as_posix(),
        "receipt_path": receipt_path.relative_to(repo_root).as_posix(),
        "telemetry_summary": telemetry_path.relative_to(repo_root).as_posix() if telemetry_path else None,
        "runtime_surface_kind": kind,
        "period_role": state.period_role,
        "runtime_probe_complete": result.runtime_probe_complete,
        "missing_requirements": list(result.missing_requirements),
        **receipt_diagnostics,
    }
    return updated, receipt, diagnostics


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


def build_updates(repo_root: Path, executed_at_utc: str) -> tuple[list[tuple[Path, dict[str, Any]]], dict[str, Any]]:
    updates: list[tuple[Path, dict[str, Any]]] = []
    records: list[tuple[dict[str, Any], dict[str, Any]]] = []
    diagnostics: list[dict[str, Any]] = []
    receipt_count = 0
    for attempt_path in target_attempt_paths(repo_root):
        manifest, receipt, attempt_diagnostics = migrated_manifest(
            repo_root=repo_root,
            attempt_path=attempt_path,
            executed_at_utc=executed_at_utc,
        )
        receipt_path = attempt_path.parent / "tester_report_receipt.yaml"
        records.append((manifest, attempt_diagnostics))
        diagnostics.append(attempt_diagnostics)
        if receipt.get("source_report_sha256"):
            receipt_count += 1
        updates.append((attempt_path.relative_to(repo_root), manifest))
        updates.append((receipt_path.relative_to(repo_root), receipt))
    complete_count = sum(1 for _, item in records if item.get("runtime_probe_complete"))
    incomplete_count = len(records) - complete_count
    pair_complete, pair_incomplete = pair_counts(records)
    summary = {
        "migration_id": MIGRATION_ID,
        "attempts_examined": len(records),
        "report_receipts_created": receipt_count,
        "attempts_complete": complete_count,
        "attempts_incomplete": incomplete_count,
        "pair_groups_complete": pair_complete,
        "pair_groups_incomplete": pair_incomplete,
        "diagnostics": diagnostics,
    }
    return updates, summary


def run(
    repo_root: Path,
    *,
    write: bool,
    fail_after_replace_count: int | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    executed_at = utc_now()
    updates, summary = build_updates(repo_root, executed_at)
    changed_updates = [
        (rel_path, payload)
        for rel_path, payload in updates
        if not path_exists(repo_root / rel_path)
        or read_text(repo_root / rel_path) != dump_yaml(payload)
    ]
    summary["mode"] = "write" if write else "check"
    summary["changed_record_count"] = len(changed_updates)
    summary["transaction_status"] = "not_requested"
    summary["transaction_receipt_path"] = None
    if write and changed_updates:
        from foundation.validation.active_record_validator import validate_runtime_completion_truth

        context = ExecutionContext(
            repo_root=repo_root,
            work_item_id=WORK_ITEM_ID,
            claim_boundary=CLAIM_BOUNDARY,
            command_argv=("materialize_runtime_report_receipts_v1", "--write"),
            validation_commands=("validate_runtime_completion_truth",),
        )
        tx = ControlPlaneTransaction(context)
        for rel_path, payload in changed_updates:
            tx.stage_yaml(rel_path, payload)
        result = tx.commit(
            validate=lambda future_root: validate_runtime_completion_truth(future_root),
            fail_after_replace_count=fail_after_replace_count,
        )
        summary["transaction_status"] = result.status
        summary["transaction_receipt_path"] = result.receipt_path.relative_to(repo_root).as_posix()
        summary["transaction_errors"] = list(result.errors)
    elif write:
        summary["transaction_status"] = "noop_already_applied"
    summary["claim_boundary"] = CLAIM_BOUNDARY
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize runtime tester report receipts and revalidate attempts.")
    parser.add_argument("--repo-root", default=".")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--write", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run(Path(args.repo_root), write=args.write)
    print(yaml.safe_dump(result, sort_keys=False, allow_unicode=False))
    return 0 if result.get("transaction_status") not in {"aborted_validation_failed", "rollback_failed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
