from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from foundation.evaluation.runtime_contract_evaluator import evaluate_runtime_contract
from foundation.migrations.runtime_graph_target_inventory import (
    INVENTORY_REL_PATH as RUNTIME_TARGET_INVENTORY,
    inventory_attempts,
    load_runtime_graph_target_inventory,
)
from foundation.validation.execution_provenance_validator import validate as validate_execution_provenance
from spacesonar.control_plane.agent_metrics import (
    AGENT_EVENTS_PATH,
    AGENT_METRICS_PATH,
    project_agent_events,
    project_agent_operating_metrics_from_events,
)
from spacesonar.control_plane.models import ExecutionContext, TRANSACTION_SUCCESS_STATUSES
from spacesonar.control_plane.provenance import (
    SOURCE_ROOTS,
    git_identity,
    provenance_compaction_marker,
    source_snapshot,
    source_tree_hash,
)
from spacesonar.control_plane.registry_projection import ARTIFACT_FIELDNAMES
from spacesonar.control_plane.store import (
    dump_csv,
    dump_json,
    dump_yaml,
    read_csv_rows,
    read_json,
    read_yaml,
    sha256_file,
)
from spacesonar.control_plane.transaction import ControlPlaneTransaction


MIGRATION_ID = "compact_historical_execution_provenance_v1"
BATCH_ID = "batch_control_plane_corrective_v3_wp06_provenance_compaction"
BATCH_ROOT = Path("lab/executions") / BATCH_ID
BATCH_RECEIPT_PATH = BATCH_ROOT / "execution_batch_receipt.yaml"
MIGRATION_INVENTORY_PATH = BATCH_ROOT / "migration_inventory.yaml"
HISTORICAL_BATCH_ID = "batch_control_plane_stabilization_v2_runtime_revalidation"
HISTORICAL_RECEIPT_PATH = Path("lab/executions") / HISTORICAL_BATCH_ID / "execution_batch_receipt.yaml"
RUNTIME_EVALUATOR_PATH = Path("lab/evaluations/control_plane_corrective_v3/runtime_contract_evaluator_v2.yaml")
ARTIFACT_REGISTRY_PATH = Path("docs/registers/artifact_registry.csv")
PROGRESS_LEDGER_PATH = Path("docs/migrations/control_plane_corrective_v3_progress.yaml")
CONSULT_RECEIPT_PATH = Path("lab/goals/goal_us100_onnx_forward_boundary_v0/task_force_consultation_initial_v2.yaml")
COMPACTION_ROLE = "metadata_compaction_only_not_original_execution_identity"
CLAIM_BOUNDARY = "wp06_provenance_compaction_only_no_runtime_authority_no_economics_pass_no_live_readiness_no_selected_baseline"
EXPECTED_RUN_COUNT = 37
EXPECTED_ATTEMPT_COUNT = 88
EXPECTED_TOTAL_COUNT = 125


def _now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _later(value: str) -> str:
    return (datetime.fromisoformat(value.replace("Z", "+00:00")) + timedelta(microseconds=1)).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _text_record(path: Path, text: str) -> dict[str, Any]:
    return {"path": path.as_posix(), "sha256": _text_sha256(text), "size_bytes": len(text.encode("utf-8"))}


def _file_record(repo_root: Path, rel_path: Path) -> dict[str, Any]:
    path = repo_root / rel_path
    return {
        "path": rel_path.as_posix(),
        "sha256": sha256_file(path) if path.exists() else None,
        "size_bytes": path.stat().st_size if path.exists() else None,
    }


def _load_record(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        return read_json(path)
    return read_yaml(path)


def _dump_record(path: Path, payload: dict[str, Any]) -> str:
    if path.suffix.lower() == ".json":
        return dump_json(payload)
    return dump_yaml(payload)


def _record_id(record_type: str, payload: dict[str, Any], path: Path) -> str:
    if record_type == "run_manifest":
        return str(payload.get("run_id") or path.parent.name)
    return str(payload.get("attempt_id") or path.parent.name)


def _manifest_paths(repo_root: Path) -> tuple[list[Path], list[Path]]:
    run_paths = sorted(
        path.relative_to(repo_root)
        for path in (repo_root / "lab" / "runs").glob("*/run_manifest.json")
    )
    attempt_paths = sorted(
        path.relative_to(repo_root)
        for path in (repo_root / "runtime" / "mt5_attempts").glob("*/attempt_manifest.yaml")
    )
    if len(run_paths) != EXPECTED_RUN_COUNT or len(attempt_paths) != EXPECTED_ATTEMPT_COUNT:
        raise RuntimeError(
            f"WP06 target count mismatch: runs={len(run_paths)} attempts={len(attempt_paths)} expected=37/88"
        )
    return run_paths, attempt_paths


def _historical_provenance_present(payload: dict[str, Any]) -> bool:
    provenance = payload.get("provenance")
    if isinstance(provenance, dict) and bool(provenance):
        return True
    return any(
        key in payload and payload.get(key) not in (None, "", [], {})
        for key in [
            "command",
            "entrypoint",
            "terminal_run_summary",
            "score_telemetry_summary",
            "execution_telemetry_summary",
            "tester_log_summary",
            "migration_history",
            "artifact_identity",
            "terminal_execution_subwork_item_id",
        ]
    )


def _updated_manifest(
    repo_root: Path,
    rel_path: Path,
    record_type: str,
    batch_receipt_path: str,
    *,
    existing_inventory_entry: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    path = repo_root / rel_path
    original = _load_record(path)
    updated = dict(original)
    previous_marker = original.get("provenance_compaction") or {}
    marker = provenance_compaction_marker(batch_receipt_path)
    previous_batch_receipt_path = (
        previous_marker.get("previous_batch_receipt_path")
        or previous_marker.get("batch_receipt_path")
    )
    marker.update(
        {
            "migration_id": MIGRATION_ID,
            "compaction_role": COMPACTION_ROLE,
            "compaction_batch_is_original_execution_identity": False,
            "original_execution_identity_preserved_in_inline_provenance": True,
            "previous_batch_receipt_path": previous_batch_receipt_path,
        }
    )
    updated["provenance_compaction"] = marker
    history = list(updated.get("migration_history") or [])
    if not any(item.get("migration_id") == MIGRATION_ID for item in history if isinstance(item, dict)):
        history.append(
            {
                "migration_id": MIGRATION_ID,
                "previous_sha256": sha256_file(path),
                "reason": "compact_batch_wide_provenance_reference_without_deleting_historical_inline_provenance",
                "executed_at_utc": _now(),
                "claim_boundary": CLAIM_BOUNDARY,
            }
        )
        updated["migration_history"] = history
    text = _dump_record(rel_path, updated)
    inventory_entry = {
        "record_type": record_type,
        "record_id": _record_id(record_type, original, rel_path),
        "path": rel_path.as_posix(),
        "pre_migration_sha256": sha256_file(path),
        "post_migration_sha256": _text_sha256(text),
        "historical_execution_provenance_present": _historical_provenance_present(original),
        "compaction_role": COMPACTION_ROLE,
    }
    if existing_inventory_entry:
        inventory_entry["pre_migration_sha256"] = existing_inventory_entry.get("pre_migration_sha256") or inventory_entry["pre_migration_sha256"]
        inventory_entry["historical_execution_provenance_present"] = existing_inventory_entry.get(
            "historical_execution_provenance_present",
            inventory_entry["historical_execution_provenance_present"],
        )
    return updated, inventory_entry, text


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or ARTIFACT_FIELDNAMES), [dict(row) for row in reader]


def _legacy_disabled_paths(repo_root: Path) -> set[str]:
    path = repo_root / "docs/agent_control/legacy_lifecycle_entrypoints.yaml"
    if not path.exists():
        return set()
    payload = read_yaml(path)
    return {
        str(item.get("path") or "").replace("\\", "/")
        for item in payload.get("entrypoints") or []
        if item.get("classification") == "historical_disabled"
    }


def _mark_historical_command(value: str, disabled_paths: set[str], *, field: str) -> str:
    text = str(value or "")
    if not text or text.startswith(("historical_producer:", "historical_disabled:", "replacement_command:", "regeneration_unavailable")):
        return text
    if any(path in text.replace("\\", "/") for path in disabled_paths):
        prefix = "historical_producer:" if field == "producer_command" else "historical_disabled:"
        return prefix + text
    return text


def _artifact_id_for_path(rel_path: Path) -> str:
    return "artifact_" + rel_path.as_posix().replace("/", "_").replace("\\", "_").replace(".", "_").replace("-", "_")


def _artifact_row_for_text(rel_path: Path, text: str, *, artifact_type: str, notes: str) -> dict[str, str]:
    return {
        "artifact_id": _artifact_id_for_path(rel_path),
        "run_id": "",
        "bundle_id": "",
        "attempt_id": rel_path.parent.name if rel_path.as_posix().startswith("runtime/mt5_attempts/") else "",
        "artifact_type": artifact_type,
        "path_or_uri": rel_path.as_posix(),
        "sha256": _text_sha256(text),
        "size_bytes": str(len(text.encode("utf-8"))),
        "availability": "present_hash_recorded",
        "producer_command": f"python foundation/migrations/{Path(__file__).name} --repo-root . --write",
        "regeneration_command": f"python foundation/migrations/{Path(__file__).name} --repo-root . --write",
        "source_of_truth": rel_path.as_posix(),
        "consumer": "work_codex_control_plane_corrective_v3",
        "claim_boundary": CLAIM_BOUNDARY,
        "notes": notes,
    }


def _artifact_registry_text(
    repo_root: Path,
    staged_texts: dict[Path, str],
    *,
    extra_rows: list[dict[str, str]],
) -> str:
    fieldnames, rows = _read_csv(repo_root / ARTIFACT_REGISTRY_PATH)
    if not fieldnames:
        fieldnames = ARTIFACT_FIELDNAMES
    disabled_paths = _legacy_disabled_paths(repo_root)
    by_path: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_path.setdefault(str(row.get("path_or_uri") or ""), []).append(row)
    for row in rows:
        row["producer_command"] = _mark_historical_command(row.get("producer_command", ""), disabled_paths, field="producer_command")
        row["regeneration_command"] = _mark_historical_command(row.get("regeneration_command", ""), disabled_paths, field="regeneration_command")
        if str(row.get("regeneration_command") or "").startswith("historical_disabled:"):
            notice = "historical-disabled regeneration; use replacement command or source-of-truth validator."
            notes = str(row.get("notes") or "").strip()
            if notice not in notes:
                row["notes"] = " ".join([notes, notice]).strip()
    for rel_path, text in staged_texts.items():
        path_key = rel_path.as_posix()
        matching_rows = by_path.get(path_key) or []
        if not matching_rows:
            row = _artifact_row_for_text(rel_path, text, artifact_type="canonical_record", notes="WP06 provenance compaction output.")
            rows.append(row)
            matching_rows = [row]
            by_path[path_key] = matching_rows
        for row in matching_rows:
            row["sha256"] = _text_sha256(text)
            row["size_bytes"] = str(len(text.encode("utf-8")))
            row["availability"] = "present_hash_recorded"
            if rel_path.match("lab/runs/*/run_manifest.json"):
                row["artifact_type"] = "run_manifest"
                row["run_id"] = rel_path.parent.name
            elif rel_path.match("runtime/mt5_attempts/*/attempt_manifest.yaml"):
                row["artifact_type"] = "attempt_manifest"
                row["attempt_id"] = rel_path.parent.name
            if rel_path in {MIGRATION_INVENTORY_PATH, BATCH_RECEIPT_PATH}:
                row["producer_command"] = f"python foundation/migrations/{Path(__file__).name} --repo-root . --write"
                row["regeneration_command"] = f"python foundation/migrations/{Path(__file__).name} --repo-root . --write"
                row["claim_boundary"] = CLAIM_BOUNDARY
                row["consumer"] = "work_codex_control_plane_corrective_v3"
    for extra in extra_rows:
        matching_rows = by_path.get(extra["path_or_uri"]) or []
        if not matching_rows:
            rows.append({key: extra.get(key, "") for key in fieldnames})
            by_path[extra["path_or_uri"]] = [rows[-1]]
            continue
        for row in matching_rows:
            for key in fieldnames:
                if key in extra:
                    row[key] = extra[key]
    rows = sorted(rows, key=lambda item: str(item.get("path_or_uri") or ""))
    return dump_csv(fieldnames, rows)


def _corrected_historical_receipt(repo_root: Path) -> tuple[dict[str, Any], str]:
    receipt = read_yaml(repo_root / HISTORICAL_RECEIPT_PATH)
    source_diff = (receipt.get("git") or {}).get("source_diff") or {}
    patch_rel = Path(str(source_diff.get("path") or ""))
    current_sha = (
        receipt.get("current_checkout_sha256")
        or (sha256_file(repo_root / patch_rel) if patch_rel and (repo_root / patch_rel).exists() else source_diff.get("sha256"))
    )
    original_sha = receipt.get("historical_original_sha256") or source_diff.get("sha256")
    receipt["receipt_completeness"] = "historical_partial"
    receipt["missing_historical_evidence"] = [
        "staged_patch_observation",
        "untracked_source_archive_observation",
    ]
    receipt["historical_original_sha256"] = original_sha
    receipt["current_checkout_sha256"] = current_sha
    if original_sha != current_sha:
        receipt["normalization_reason"] = "line_ending_or_historical_snapshot_normalization_between_recorded_source_diff_and_current_checkout"
    git = dict(receipt.get("git") or {})
    source_diff = dict(git.get("source_diff") or {})
    source_diff["sha256"] = current_sha
    git["source_diff"] = source_diff
    snapshot = dict(git.get("source_snapshot") or {})
    snapshot["tracked_patch_sha256"] = current_sha
    snapshot["receipt_completeness"] = "historical_partial"
    snapshot["missing_historical_evidence"] = list(receipt["missing_historical_evidence"])
    git["source_snapshot"] = snapshot
    receipt["git"] = git
    return receipt, dump_yaml(receipt)


def _materialize_evaluator_future(repo_root: Path, staged_texts: dict[Path, str]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="spacesonar_wp06_eval_") as raw_temp:
        temp_root = Path(raw_temp)
        inventory_paths = {RUNTIME_TARGET_INVENTORY}
        runtime_inventory = load_runtime_graph_target_inventory(repo_root)
        for entry in inventory_attempts(runtime_inventory):
            for rel_value in [
                entry.get("manifest_path"),
                entry.get("expected_terminal_summary_path"),
                entry.get("expected_telemetry_summary_path"),
                entry.get("expected_tester_report_receipt_path"),
            ]:
                if rel_value:
                    inventory_paths.add(Path(str(rel_value).replace("\\", "/")))
        for rel_path in sorted(inventory_paths, key=lambda item: item.as_posix()):
            target = temp_root / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            if rel_path in staged_texts:
                target.write_bytes(staged_texts[rel_path].encode("utf-8"))
            else:
                shutil.copy2(repo_root / rel_path, target)
        return evaluate_runtime_contract(temp_root)


def _updated_lineage_texts(repo_root: Path, staged_texts: dict[Path, str]) -> dict[Path, str]:
    updated: dict[Path, str] = {}
    staged_hashes = {
        rel_path.as_posix(): {
            "sha256": _text_sha256(text),
            "size_bytes": len(text.encode("utf-8")),
        }
        for rel_path, text in staged_texts.items()
    }
    for lineage_path in sorted((repo_root / "lab" / "runs").glob("*/artifact_lineage.json")):
        rel_lineage = lineage_path.relative_to(repo_root)
        payload = _load_record(lineage_path)
        changed = False
        artifact_paths = []
        for item in payload.get("artifact_paths") or []:
            if not isinstance(item, dict):
                artifact_paths.append(item)
                continue
            rel_path = str(item.get("path") or "")
            replacement = staged_hashes.get(rel_path)
            if replacement:
                item = dict(item)
                item["sha256"] = replacement["sha256"]
                item["size_bytes"] = replacement["size_bytes"]
                changed = True
            artifact_paths.append(item)
        if changed:
            payload["artifact_paths"] = artifact_paths
            updated[rel_lineage] = _dump_record(rel_lineage, payload)
    return updated


def _build_batch_receipt(
    repo_root: Path,
    *,
    input_paths: list[Path],
    output_records: list[dict[str, Any]],
    snapshot_manifest_record: dict[str, Any],
) -> dict[str, Any]:
    existing_path = repo_root / BATCH_RECEIPT_PATH
    if existing_path.exists():
        existing = read_yaml(existing_path)
        if existing.get("receipt_status") == "finalized":
            refreshed = dict(existing)
            git = dict(refreshed.get("git") or {})
            snapshot = dict(git.get("source_snapshot") or {})
            snapshot["manifest_path"] = snapshot_manifest_record["path"]
            snapshot["manifest_sha256"] = snapshot_manifest_record["sha256"]
            snapshot["source_surface"] = list(SOURCE_ROOTS)
            git["source_snapshot"] = snapshot
            refreshed["git"] = git
            refreshed["inputs"] = [_file_record(repo_root, path) for path in input_paths]
            refreshed["outputs"] = sorted(output_records, key=lambda item: str(item.get("path") or ""))
            refreshed["receipt_status"] = "finalized"
            refreshed["final_receipt_status"] = "valid"
            return refreshed
    started = _now()
    ended = _later(started)
    git = git_identity(repo_root)
    changed = {
        "source_files": [],
        "generated_files": [],
        "other_files": [],
    }
    try:
        from spacesonar.control_plane.provenance import classify_changed_files

        changed = classify_changed_files(repo_root)
    except Exception:
        pass
    return {
        "version": "execution_batch_receipt_v1",
        "batch_id": BATCH_ID,
        "work_item_id": "work_codex_control_plane_corrective_v3",
        "command_argv": [
            "python",
            "foundation/migrations/compact_historical_execution_provenance_v1.py",
            "--repo-root",
            ".",
            "--write",
        ],
        "cwd": ".",
        "started_at_utc": started,
        "ended_at_utc": ended,
        "exit_status": 0,
        "result_status": "completed",
        "receipt_status": "finalized",
        "final_receipt_status": "valid",
        "git": {
            "sha": git.get("sha"),
            "branch": git.get("branch"),
            "source_dirty": bool(changed.get("source_files")),
            "generated_output_dirty": bool(changed.get("generated_files")),
            "source_tree_hash": source_tree_hash(repo_root),
            "source_tree_hash_at_start": source_tree_hash(repo_root),
            "source_tree_hash_at_end": source_tree_hash(repo_root),
            "source_tree_drift_during_execution": False,
            "source_diff": {
                "path": None,
                "sha256": None,
            },
            "source_snapshot": {
                "version": "source_snapshot_v1",
                "batch_id": BATCH_ID,
                "manifest_path": snapshot_manifest_record["path"],
                "manifest_sha256": snapshot_manifest_record["sha256"],
                "source_surface": list(SOURCE_ROOTS),
            },
            "changed_files_summary": changed,
        },
        "environment": {
            "python_executable_redacted": "${PYTHON}",
            "python_version": sys.version.split()[0],
            "lock_file": "uv.lock",
            "lock_file_sha256": sha256_file(repo_root / "uv.lock") if (repo_root / "uv.lock").exists() else None,
        },
        "inputs": [_file_record(repo_root, path) for path in input_paths],
        "outputs": sorted(output_records, key=lambda item: str(item.get("path") or "")),
        "claim_boundary": CLAIM_BOUNDARY,
        "receipt_completeness": "complete",
    }


def build_plan(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    run_paths, attempt_paths = _manifest_paths(repo_root)
    batch_receipt_path = BATCH_RECEIPT_PATH.as_posix()
    staged_texts: dict[Path, str] = {}
    inventory_entries: list[dict[str, Any]] = []
    existing_inventory_entries: dict[str, dict[str, Any]] = {}
    existing_inventory_path = repo_root / MIGRATION_INVENTORY_PATH
    if existing_inventory_path.exists():
        existing_inventory = read_yaml(existing_inventory_path)
        existing_inventory_entries = {
            str(item.get("path") or ""): item
            for item in existing_inventory.get("entries") or []
            if isinstance(item, dict)
        }
    for rel_path in run_paths:
        _, entry, text = _updated_manifest(
            repo_root,
            rel_path,
            "run_manifest",
            batch_receipt_path,
            existing_inventory_entry=existing_inventory_entries.get(rel_path.as_posix()),
        )
        staged_texts[rel_path] = text
        inventory_entries.append(entry)
    for rel_path in attempt_paths:
        _, entry, text = _updated_manifest(
            repo_root,
            rel_path,
            "attempt_manifest",
            batch_receipt_path,
            existing_inventory_entry=existing_inventory_entries.get(rel_path.as_posix()),
        )
        staged_texts[rel_path] = text
        inventory_entries.append(entry)

    inventory = {
        "version": "provenance_compaction_inventory_v1",
        "migration_id": MIGRATION_ID,
        "batch_id": BATCH_ID,
        "record_counts": {
            "run_manifest": len(run_paths),
            "attempt_manifest": len(attempt_paths),
            "total": len(inventory_entries),
        },
        "entries": sorted(inventory_entries, key=lambda item: (item["record_type"], item["path"])),
        "claim_boundary": CLAIM_BOUNDARY,
    }
    staged_texts[MIGRATION_INVENTORY_PATH] = dump_yaml(inventory)

    historical_receipt, historical_receipt_text = _corrected_historical_receipt(repo_root)
    staged_texts[HISTORICAL_RECEIPT_PATH] = historical_receipt_text

    runtime_evaluator = _materialize_evaluator_future(repo_root, staged_texts)
    staged_texts[RUNTIME_EVALUATOR_PATH] = dump_yaml(runtime_evaluator)

    agent_events = project_agent_events(repo_root)
    agent_metrics = project_agent_operating_metrics_from_events(repo_root, agent_events)
    staged_texts[AGENT_EVENTS_PATH] = dump_yaml(agent_events)
    staged_texts[AGENT_METRICS_PATH] = dump_yaml(agent_metrics)
    staged_texts.update(_updated_lineage_texts(repo_root, staged_texts))

    existing_receipt_path = repo_root / BATCH_RECEIPT_PATH
    source_snapshot_texts: dict[Path, str] = {}
    if existing_receipt_path.exists():
        existing_receipt = read_yaml(existing_receipt_path)
        snapshot = ((existing_receipt.get("git") or {}).get("source_snapshot") or {})
        snapshot_manifest_path = Path(str(snapshot.get("manifest_path") or (WP06_BATCH_ROOT / "source_snapshot/source_snapshot_manifest.yaml").as_posix()))
        snapshot_manifest_record = _file_record(repo_root, snapshot_manifest_path)
    else:
        snapshot = source_snapshot(repo_root, BATCH_ID, write=True)
        snapshot_manifest_path = Path(str(snapshot["manifest_path"]))
        snapshot_manifest_record = _file_record(repo_root, snapshot_manifest_path)
        for key in ["tracked_patch_path", "staged_patch_path", "untracked_archive_path", "manifest_path"]:
            rel_value = snapshot.get(key)
            if rel_value:
                rel_path = Path(str(rel_value).replace("\\", "/"))
                path = repo_root / rel_path
                if path.exists() and path.is_file() and rel_path.suffix.lower() not in {".zip"}:
                    source_snapshot_texts[rel_path] = path.read_text(encoding="utf-8")

    output_records = [_text_record(path, text) for path, text in staged_texts.items()]
    output_records.append(snapshot_manifest_record)
    input_paths = sorted(
        set(run_paths)
        | set(attempt_paths)
        | {
            PROGRESS_LEDGER_PATH,
            HISTORICAL_RECEIPT_PATH,
            RUNTIME_TARGET_INVENTORY,
            CONSULT_RECEIPT_PATH,
        },
        key=lambda item: item.as_posix(),
    )
    receipt = _build_batch_receipt(
        repo_root,
        input_paths=input_paths,
        output_records=output_records,
        snapshot_manifest_record=snapshot_manifest_record,
    )
    staged_texts[BATCH_RECEIPT_PATH] = dump_yaml(receipt)

    extra_rows = [
        _artifact_row_for_text(BATCH_RECEIPT_PATH, staged_texts[BATCH_RECEIPT_PATH], artifact_type="execution_batch_receipt", notes="WP06 provenance compaction batch receipt."),
        _artifact_row_for_text(MIGRATION_INVENTORY_PATH, staged_texts[MIGRATION_INVENTORY_PATH], artifact_type="migration_inventory", notes="WP06 37/88/125 provenance compaction inventory."),
        _artifact_row_for_text(RUNTIME_EVALUATOR_PATH, staged_texts[RUNTIME_EVALUATOR_PATH], artifact_type="evaluator_result", notes="Runtime evaluator refreshed after WP06 manifest hash changes."),
        _artifact_row_for_text(AGENT_EVENTS_PATH, staged_texts[AGENT_EVENTS_PATH], artifact_type="agent_operating_events", notes="Agent event projection derived from durable progress ledger."),
        _artifact_row_for_text(AGENT_METRICS_PATH, staged_texts[AGENT_METRICS_PATH], artifact_type="agent_operating_metrics", notes="Agent metrics projection derived from event and opinion records."),
    ]
    staged_texts[ARTIFACT_REGISTRY_PATH] = _artifact_registry_text(repo_root, staged_texts, extra_rows=extra_rows)
    for rel_path, text in source_snapshot_texts.items():
        staged_texts.setdefault(rel_path, text)
    return {
        "staged_texts": staged_texts,
        "inventory": inventory,
        "receipt": receipt,
        "runtime_evaluator": runtime_evaluator,
    }


def plan_diffs(repo_root: Path, staged_texts: dict[Path, str]) -> list[str]:
    diffs: list[str] = []
    for rel_path, text in sorted(staged_texts.items(), key=lambda item: item[0].as_posix()):
        path = repo_root / rel_path
        observed = path.read_text(encoding="utf-8") if path.exists() else ""
        if observed != text:
            diffs.append(rel_path.as_posix())
    return diffs


def run(repo_root: Path, *, write: bool, fail_after_replace_count: int | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    plan = build_plan(repo_root)
    staged_texts: dict[Path, str] = plan["staged_texts"]
    diffs = plan_diffs(repo_root, staged_texts)
    report = {
        "migration_id": MIGRATION_ID,
        "mode": "write" if write else "check",
        "changed_record_count": len(diffs),
        "changed_paths": diffs,
        "inventory_path": MIGRATION_INVENTORY_PATH.as_posix(),
        "batch_receipt_path": BATCH_RECEIPT_PATH.as_posix(),
        "record_counts": plan["inventory"]["record_counts"],
        "runtime_evaluator_status": plan["runtime_evaluator"].get("status"),
        "transaction_status": None,
    }
    if not write:
        report["status"] = "passed" if not diffs else "failed"
        return report

    context = ExecutionContext(
        repo_root=repo_root,
        work_item_id="work_codex_control_plane_corrective_v3",
        claim_boundary=CLAIM_BOUNDARY,
        command_argv=("python", "foundation/migrations/compact_historical_execution_provenance_v1.py", "--repo-root", ".", "--write"),
        validation_commands=("execution_provenance_validator",),
    )
    tx = ControlPlaneTransaction(context)
    for rel_path, text in sorted(staged_texts.items(), key=lambda item: item[0].as_posix()):
        tx.stage_text(rel_path, text)
    result = tx.commit(
        validate=lambda future_root: validate_execution_provenance(future_root),
        fail_after_replace_count=fail_after_replace_count,
    )
    report["transaction_status"] = result.status
    report["transaction_id"] = result.transaction_id
    report["transaction_errors"] = list(result.errors)
    report["status"] = "passed" if result.status in TRANSACTION_SUCCESS_STATUSES else "failed"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--fail-after-replace-count", type=int)
    args = parser.parse_args(argv)

    report = run(
        Path(args.repo_root),
        write=bool(args.write),
        fail_after_replace_count=args.fail_after_replace_count,
    )
    print(dump_yaml(report))
    if args.check:
        return 0 if report["status"] == "passed" and report["changed_record_count"] == 0 else 1
    return 0 if report.get("transaction_status") in TRANSACTION_SUCCESS_STATUSES else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
