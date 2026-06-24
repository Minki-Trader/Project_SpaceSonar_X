from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import UTC, datetime, timedelta
from io import BytesIO
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
    build_source_snapshot_payload,
    git_identity,
    provenance_compaction_marker,
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
from spacesonar.control_plane.transaction import ControlPlaneTransaction, transaction_id


MIGRATION_ID = "compact_historical_execution_provenance_v1"
CORRECTION_ID = "wp06_execution_receipt_truth_correction_v2"
BATCH_ID = "batch_control_plane_corrective_v3_wp06_provenance_compaction"
BATCH_ROOT = Path("lab/executions") / BATCH_ID
BATCH_RECEIPT_PATH = BATCH_ROOT / "execution_batch_receipt.yaml"
SUPERSEDED_RECEIPT_PATH = BATCH_ROOT / "execution_batch_receipt_superseded.yaml"
SUPERSEDED_RECEIPT_V1_PATH = BATCH_ROOT / "execution_batch_receipt_superseded_v1.yaml"
START_RECEIPT_PATH = BATCH_ROOT / "batch_start_receipt.yaml"
FINALIZATION_RECEIPT_PATH = BATCH_ROOT / "batch_finalization_receipt.yaml"
TRANSACTION_RECEIPT_PATH = BATCH_ROOT / "transaction_receipt.yaml"
EFFECT_INVENTORY_PATH = BATCH_ROOT / "effect_inventory.yaml"
MIGRATION_INVENTORY_PATH = BATCH_ROOT / "migration_inventory.yaml"
PREIMAGE_MANIFEST_PATH = BATCH_ROOT / "preimages/preimage_manifest.yaml"
PREIMAGE_ARCHIVE_PATH = BATCH_ROOT / "preimages/preimages.zip"
SOURCE_SNAPSHOT_CORRECTION_NAMESPACE = "source_snapshot_correction_v2"
EVIDENCE_ROOT = BATCH_ROOT / "evidence"
PROGRESS_LEDGER_SNAPSHOT_PATH = EVIDENCE_ROOT / "progress_ledger_input.yaml"
AGENT_EVENTS_SNAPSHOT_PATH = EVIDENCE_ROOT / "agent_operating_events_output.yaml"
AGENT_METRICS_SNAPSHOT_PATH = EVIDENCE_ROOT / "agent_operating_metrics_output.yaml"
RUNTIME_EVALUATOR_SNAPSHOT_PATH = EVIDENCE_ROOT / "runtime_contract_evaluator_output.yaml"
ARTIFACT_REGISTRY_DELTA_PATH = EVIDENCE_ROOT / "artifact_registry_delta.yaml"
AGENT_WORK_RECEIPT_PATH = Path("docs/workspace/agent_work_receipts/WP06.yaml")
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


def _bytes_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _text_record(path: Path, text: str) -> dict[str, Any]:
    return {"path": path.as_posix(), "sha256": _text_sha256(text), "size_bytes": len(text.encode("utf-8"))}


def _bytes_record(path: Path, payload: bytes) -> dict[str, Any]:
    return {"path": path.as_posix(), "sha256": _bytes_sha256(payload), "size_bytes": len(payload)}


def _canonical_self_hash(payload: dict[str, Any], field_path: tuple[str, ...]) -> str:
    clone = json.loads(json.dumps(payload, sort_keys=True))
    cursor: dict[str, Any] = clone
    for key in field_path[:-1]:
        cursor = cursor.setdefault(key, {})
    cursor[field_path[-1]] = ""
    return _text_sha256(dump_yaml(clone))


def _with_self_hash(payload: dict[str, Any], field_path: tuple[str, ...] = ("receipt_sha256", "value")) -> dict[str, Any]:
    updated = json.loads(json.dumps(payload, sort_keys=True))
    cursor: dict[str, Any] = updated
    for key in field_path[:-1]:
        cursor = cursor.setdefault(key, {})
    cursor[field_path[-1]] = ""
    cursor[field_path[-1]] = _canonical_self_hash(updated, field_path)
    return updated


def _receipt_input_record(
    *,
    path: Path,
    sha256: str,
    size_bytes: int,
    validation_class: str = "current_path_still_expected",
    preimage_ref: dict[str, Any] | None = None,
    immutable_evidence_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = {
        "path_at_execution": path.as_posix(),
        "sha256_at_start": sha256,
        "size_bytes_at_start": size_bytes,
        "hash_validation_class": validation_class,
    }
    if preimage_ref:
        record["preimage_ref"] = preimage_ref
    if immutable_evidence_ref:
        record["immutable_evidence_ref"] = immutable_evidence_ref
    return record


def _receipt_output_record(
    *,
    path: Path,
    sha256: str,
    size_bytes: int,
    validation_class: str = "current_path_still_expected",
    immutable_evidence_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = {
        "path_at_execution": path.as_posix(),
        "sha256_at_end": sha256,
        "size_bytes_at_end": size_bytes,
        "hash_validation_class": validation_class,
    }
    if immutable_evidence_ref:
        record["immutable_evidence_ref"] = immutable_evidence_ref
    return record


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


def _git_show_bytes(repo_root: Path, revision: str, rel_path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{revision}:{rel_path}"],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip() or f"git show failed for {rel_path}")
    return result.stdout


def _git_text(repo_root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo_root, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def _load_preimage_records(repo_root: Path) -> tuple[dict[str, Any] | None, bytes | None]:
    manifest_path = repo_root / PREIMAGE_MANIFEST_PATH
    archive_path = repo_root / PREIMAGE_ARCHIVE_PATH
    if manifest_path.exists() and archive_path.exists():
        return read_yaml(manifest_path), archive_path.read_bytes()
    return None, None


def _resolve_preimage_git_identity(repo_root: Path, rel_path: str, content_sha256: str) -> tuple[str, str]:
    commits = _git_text(repo_root, "rev-list", "--all", "--", rel_path).splitlines()
    for commit in commits:
        try:
            payload = _git_show_bytes(repo_root, commit, rel_path)
        except RuntimeError:
            continue
        raw_sha = _bytes_sha256(payload)
        crlf_sha = _bytes_sha256(payload.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        if content_sha256 in {raw_sha, crlf_sha}:
            return commit, _git_text(repo_root, "rev-parse", f"{commit}:{rel_path}")
    # Last-resort durable identity: keep the content hash and current HEAD commit,
    # but validators still reject symbolic refs and verify the archived bytes.
    return _git_text(repo_root, "rev-parse", "HEAD"), content_sha256


def _build_preimage_payload(repo_root: Path, inventory_entries: list[dict[str, Any]]) -> tuple[dict[str, Any], bytes, dict[Path, bytes]]:
    existing_manifest, existing_archive = _load_preimage_records(repo_root)
    if existing_manifest and existing_archive is not None:
        changed = False
        with zipfile.ZipFile(BytesIO(existing_archive)) as archive:
            for item in existing_manifest.get("entries") or []:
                if not isinstance(item, dict):
                    continue
                member = str(item.get("archive_member") or item.get("path") or "")
                payload = archive.read(member)
                content_sha = _bytes_sha256(payload)
                item["content_sha256"] = content_sha
                item["content_match_verified"] = True
                if item.get("normalization_applied") is None:
                    item["normalization_applied"] = bool(item.get("normalization_verified"))
                if item.get("normalization_applied") is False:
                    item["normalization_type"] = None
                if not item.get("git_commit_sha") or not item.get("git_blob_sha") or item.get("git_revision"):
                    commit_sha, blob_sha = _resolve_preimage_git_identity(repo_root, str(item.get("path") or member), content_sha)
                    item["git_commit_sha"] = commit_sha
                    item["git_blob_sha"] = blob_sha
                    item.pop("git_revision", None)
                    item.pop("normalization_verified", None)
                    changed = True
        existing_manifest["git_commit_sha"] = existing_manifest.get("git_commit_sha") or _git_text(repo_root, "rev-parse", "HEAD")
        existing_manifest.pop("git_revision", None)
        if changed:
            return existing_manifest, existing_archive, {PREIMAGE_MANIFEST_PATH: dump_yaml(existing_manifest).encode("utf-8")}
        return existing_manifest, existing_archive, {}
    revision = "HEAD~1"
    commit_sha = _git_text(repo_root, "rev-parse", revision)
    entries: list[dict[str, Any]] = []
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in sorted(inventory_entries, key=lambda entry: str(entry.get("path") or "")):
            rel_path = str(item["path"])
            raw_payload = _git_show_bytes(repo_root, commit_sha, rel_path)
            blob_sha = _git_text(repo_root, "rev-parse", f"{commit_sha}:{rel_path}")
            raw_sha = _bytes_sha256(raw_payload)
            crlf_payload = raw_payload.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            crlf_sha = _bytes_sha256(crlf_payload)
            if raw_sha == item["pre_migration_sha256"]:
                payload = raw_payload
                observed_sha = raw_sha
                normalization = {
                    "content_match_verified": True,
                    "normalization_applied": False,
                    "normalization_type": None,
                    "historical_original_sha256": raw_sha,
                    "current_checkout_sha256": raw_sha,
                }
            elif crlf_sha == item["pre_migration_sha256"]:
                payload = crlf_payload
                observed_sha = crlf_sha
                normalization = {
                    "content_match_verified": True,
                    "normalization_applied": True,
                    "normalization_type": "lf_to_crlf",
                    "historical_original_sha256": crlf_sha,
                    "current_checkout_sha256": raw_sha,
                }
            else:
                raise RuntimeError(
                    f"preimage hash mismatch for {rel_path}: expected={item['pre_migration_sha256']} raw={raw_sha} crlf={crlf_sha}"
                )
            mode = "100644"
            entries.append(
                {
                    "path": rel_path,
                    "archive_member": rel_path,
                    "sha256": observed_sha,
                    "content_sha256": observed_sha,
                    "size_bytes": len(payload),
                    "mode": mode,
                    "git_commit_sha": commit_sha,
                    "git_blob_sha": blob_sha,
                    **normalization,
                }
            )
            info = zipfile.ZipInfo(rel_path)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.external_attr = int(mode, 8) << 16
            archive.writestr(info, payload, compress_type=zipfile.ZIP_DEFLATED)
        manifest_bytes = json.dumps(
            {"version": "preimage_archive_member_manifest_v1", "files": entries},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        info = zipfile.ZipInfo("_preimage_manifest.json")
        info.date_time = (1980, 1, 1, 0, 0, 0)
        info.external_attr = 0o100644 << 16
        archive.writestr(info, manifest_bytes, compress_type=zipfile.ZIP_DEFLATED)
    archive_bytes = buffer.getvalue()
    manifest = {
        "version": "preimage_manifest_v1",
        "batch_id": BATCH_ID,
        "archive_path": PREIMAGE_ARCHIVE_PATH.as_posix(),
        "archive_sha256": _bytes_sha256(archive_bytes),
        "archive_size_bytes": len(archive_bytes),
        "source_class": "git_object",
        "git_commit_sha": commit_sha,
        "entries": entries,
    }
    return manifest, archive_bytes, {
        PREIMAGE_MANIFEST_PATH: dump_yaml(manifest).encode("utf-8"),
        PREIMAGE_ARCHIVE_PATH: archive_bytes,
    }


def _preimage_ref(preimage_manifest: dict[str, Any], rel_path: str) -> dict[str, Any]:
    entries = {
        str(item.get("path") or ""): item
        for item in preimage_manifest.get("entries") or []
        if isinstance(item, dict)
    }
    entry = entries[rel_path]
    return {
        "manifest_path": PREIMAGE_MANIFEST_PATH.as_posix(),
        "archive_path": PREIMAGE_ARCHIVE_PATH.as_posix(),
        "archive_sha256": preimage_manifest["archive_sha256"],
        "archive_member": entry["archive_member"],
        "sha256": entry["sha256"],
        "content_sha256": entry.get("content_sha256") or entry["sha256"],
        "size_bytes": entry["size_bytes"],
        "source_class": preimage_manifest.get("source_class", "git_object"),
        "git_commit_sha": entry.get("git_commit_sha") or preimage_manifest.get("git_commit_sha"),
        "git_blob_sha": entry.get("git_blob_sha"),
        "content_match_verified": entry.get("content_match_verified"),
        "normalization_applied": entry.get("normalization_applied"),
        "normalization_type": entry.get("normalization_type"),
    }


def _inventory_preimage_size(preimage_manifest: dict[str, Any], rel_path: str) -> int:
    for entry in preimage_manifest.get("entries") or []:
        if isinstance(entry, dict) and entry.get("path") == rel_path:
            return int(entry.get("size_bytes") or 0)
    raise KeyError(rel_path)


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


def _artifact_reference_row(rel_path: Path, *, artifact_type: str, notes: str) -> dict[str, str]:
    row = _artifact_row_for_text(rel_path, "", artifact_type=artifact_type, notes=notes)
    row["sha256"] = ""
    row["size_bytes"] = ""
    row["availability"] = "forward_stable_reference_hash_omitted_to_avoid_receipt_registry_cycle"
    return row


def _effect_record(repo_root: Path, rel_path: Path, payload: bytes, *, effect_type: str, validation_class: str) -> dict[str, Any]:
    current = repo_root / rel_path
    existed = current.exists()
    post_sha = "self_hash_cycle_omitted" if validation_class == "self_reference_excluded" else _bytes_sha256(payload)
    return {
        "path": rel_path.as_posix(),
        "effect_type": effect_type,
        "pre_sha256": sha256_file(current) if existed and current.is_file() else None,
        "post_sha256": post_sha,
        "evidence_ref": {
            "path": rel_path.as_posix(),
            "sha256": post_sha,
            "size_bytes": len(payload),
        },
        "validation_class": validation_class,
    }


def _build_effect_inventory(repo_root: Path, staged_texts: dict[Path, str], staged_bytes: dict[Path, bytes]) -> dict[str, Any]:
    effects: list[dict[str, Any]] = []
    for rel_path, text in sorted(staged_texts.items(), key=lambda item: item[0].as_posix()):
        if rel_path == EFFECT_INVENTORY_PATH:
            continue
        payload = text.encode("utf-8")
        effects.append(
            _effect_record(
                repo_root,
                rel_path,
                payload,
                effect_type="modified" if (repo_root / rel_path).exists() else "created",
                validation_class="self_reference_excluded" if rel_path in {BATCH_RECEIPT_PATH, FINALIZATION_RECEIPT_PATH} else "current_path_still_expected",
            )
        )
    for rel_path, payload in sorted(staged_bytes.items(), key=lambda item: item[0].as_posix()):
        if rel_path == EFFECT_INVENTORY_PATH:
            continue
        effects.append(
            _effect_record(
                repo_root,
                rel_path,
                payload,
                effect_type="modified" if (repo_root / rel_path).exists() else "created",
                validation_class="immutable_snapshot",
            )
        )
    inventory = {
        "version": "wp06_effect_inventory_v1",
        "batch_id": BATCH_ID,
        "migration_id": CORRECTION_ID,
        "self_reference_policy": "effect_inventory_self_hash_excluded; execution_batch_receipt_projection_hash_excluded",
        "effects": sorted(effects, key=lambda item: item["path"]),
    }
    inventory["effect_count"] = len(inventory["effects"])
    return inventory


def _build_start_receipt(
    *,
    started_at_utc: str,
    source_snapshot: dict[str, Any],
    input_records: list[dict[str, Any]],
    snapshot_manifest_record: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "version": "execution_batch_start_receipt_v1",
        "batch_id": BATCH_ID,
        "work_item_id": "work_codex_control_plane_corrective_v3",
        "correction_migration_id": CORRECTION_ID,
        "started_at_utc": started_at_utc,
        "source_snapshot_ref": snapshot_manifest_record,
        "source_tree_hash": source_snapshot.get("source_tree_hash"),
        "inputs": sorted(input_records, key=lambda item: str(item.get("path_at_execution") or "")),
        "claim_boundary": CLAIM_BOUNDARY,
        "receipt_sha256": {"algorithm": "sha256", "scope": "canonical_yaml_with_value_field_empty", "value": ""},
    }
    return _with_self_hash(payload)


def _build_durable_transaction_receipt(
    *,
    transaction_id: str,
    started_at_utc: str,
    committed_at_utc: str,
    staged_texts: dict[Path, str],
    staged_bytes: dict[Path, bytes],
) -> dict[str, Any]:
    output_hashes = []
    for rel_path, text in sorted(staged_texts.items(), key=lambda item: item[0].as_posix()):
        output_hashes.append({"path": rel_path.as_posix(), "sha256": _text_sha256(text), "size_bytes": len(text.encode("utf-8"))})
    for rel_path, payload in sorted(staged_bytes.items(), key=lambda item: item[0].as_posix()):
        output_hashes.append({"path": rel_path.as_posix(), "sha256": _bytes_sha256(payload), "size_bytes": len(payload)})
    return {
        "version": "durable_transaction_receipt_projection_v1",
        "transaction_id": transaction_id,
        "status": "committed",
        "started_at_utc": started_at_utc,
        "committed_at_utc": committed_at_utc,
        "input_hashes": [],
        "output_hashes": output_hashes,
        "applied_paths": sorted(item["path"] for item in output_hashes),
        "rollback_status": "not_required",
        "original_transaction_receipt_sha256": None,
        "original_transaction_receipt_availability": "ignored_workspace_receipt_not_required_for_clean_checkout",
    }


def _build_finalization_receipt(
    *,
    finalized_at_utc: str,
    batch_receipt_text: str,
    start_receipt_text: str,
    transaction_receipt_text: str,
    effect_inventory_text: str,
    snapshot_manifest_record: dict[str, Any],
    preimage_manifest_bytes: bytes,
) -> dict[str, Any]:
    payload = {
        "version": "execution_batch_finalization_receipt_v1",
        "batch_id": BATCH_ID,
        "correction_migration_id": CORRECTION_ID,
        "execution_batch_receipt_sha256": _text_sha256(batch_receipt_text),
        "batch_start_receipt_sha256": _text_sha256(start_receipt_text),
        "transaction_receipt_sha256": _text_sha256(transaction_receipt_text),
        "effect_inventory_sha256": _text_sha256(effect_inventory_text),
        "source_snapshot_manifest_sha256": snapshot_manifest_record["sha256"],
        "preimage_manifest_sha256": _bytes_sha256(preimage_manifest_bytes),
        "finalized_at_utc": finalized_at_utc,
        "receipt_sha256": {"algorithm": "sha256", "scope": "canonical_yaml_with_value_field_empty", "value": ""},
    }
    return _with_self_hash(payload)


def _build_agent_work_receipt(
    repo_root: Path,
    *,
    transaction_id_value: str,
    batch_receipt_text: str,
    transaction_receipt_text: str,
    ended_at_utc: str,
) -> dict[str, Any]:
    progress_bytes = (repo_root / PROGRESS_LEDGER_PATH).read_bytes()
    payload = {
        "version": "agent_work_receipt_v1",
        "work_item_id": "WP06",
        "agent_mode": "solo",
        "evidence_class": "contemporaneous_work_receipt",
        "started_at_utc": "2026-06-23T15:05:01Z",
        "ended_at_utc": ended_at_utc,
        "consult_ids": [],
        "source_refs": [
            {
                "path": PROGRESS_LEDGER_PATH.as_posix(),
                "sha256": _bytes_sha256(progress_bytes),
                "size_bytes": len(progress_bytes),
            }
        ],
        "wp06_batch_receipt_ref": {
            "batch_id": BATCH_ID,
            "path": BATCH_RECEIPT_PATH.as_posix(),
            "sha256": _text_sha256(batch_receipt_text),
            "size_bytes": len(batch_receipt_text.encode("utf-8")),
        },
        "transaction_receipt_ref": {
            "transaction_id": transaction_id_value,
            "path": TRANSACTION_RECEIPT_PATH.as_posix(),
            "sha256": _text_sha256(transaction_receipt_text),
            "size_bytes": len(transaction_receipt_text.encode("utf-8")),
        },
        "claim_boundary": CLAIM_BOUNDARY,
        "receipt_sha256": {"algorithm": "sha256", "scope": "canonical_yaml_with_value_field_empty", "value": ""},
    }
    return _with_self_hash(payload)


def _receipt_outputs_from_staged(staged_texts: dict[Path, str], staged_bytes: dict[Path, bytes]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for rel_path, text in sorted(staged_texts.items(), key=lambda item: item[0].as_posix()):
        if rel_path == BATCH_RECEIPT_PATH:
            continue
        records.append(
            _receipt_output_record(
                path=rel_path,
                sha256=_text_sha256(text),
                size_bytes=len(text.encode("utf-8")),
                validation_class="immutable_snapshot" if rel_path.as_posix().startswith(BATCH_ROOT.as_posix()) else "current_path_still_expected",
            )
        )
    for rel_path, payload in sorted(staged_bytes.items(), key=lambda item: item[0].as_posix()):
        records.append(
            _receipt_output_record(
                path=rel_path,
                sha256=_bytes_sha256(payload),
                size_bytes=len(payload),
                validation_class="immutable_snapshot",
            )
        )
    return records


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


def _row_sha256(row: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


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
    receipt.pop("normalization_reason", None)
    receipt.pop("normalization_verified", None)
    receipt.pop("normalization_type", None)
    receipt.pop("unresolved_historical_hash_mismatch", None)
    if original_sha != current_sha:
        patch_path = repo_root / patch_rel
        normalization_verified = False
        normalization_type = None
        if patch_path.exists():
            current_bytes = patch_path.read_bytes()
            lf_sha = _bytes_sha256(current_bytes.replace(b"\r\n", b"\n"))
            crlf_sha = _bytes_sha256(current_bytes.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
            if lf_sha == original_sha:
                normalization_verified = True
                normalization_type = "crlf_to_lf"
            elif crlf_sha == original_sha:
                normalization_verified = True
                normalization_type = "lf_to_crlf"
        receipt["normalization_verified"] = normalization_verified
        if normalization_verified:
            receipt["normalization_type"] = normalization_type
            receipt["normalization_reason"] = "verified_line_ending_normalization_between_recorded_source_diff_and_current_checkout"
        else:
            receipt["unresolved_historical_hash_mismatch"] = True
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


def _existing_or_built_source_snapshot(repo_root: Path) -> tuple[dict[str, Any], dict[Path, bytes]]:
    manifest_path = repo_root / BATCH_ROOT / SOURCE_SNAPSHOT_CORRECTION_NAMESPACE / "source_snapshot_manifest.yaml"
    if manifest_path.exists():
        manifest = read_yaml(manifest_path)
        manifest.setdefault("manifest_path", (BATCH_ROOT / SOURCE_SNAPSHOT_CORRECTION_NAMESPACE / "source_snapshot_manifest.yaml").as_posix())
        manifest["manifest_sha256"] = manifest.get("manifest_sha256") or sha256_file(manifest_path)
        if manifest.get("source_tree_hash") == source_tree_hash(repo_root):
            return manifest, {}
    payload = build_source_snapshot_payload(repo_root, BATCH_ID, namespace=SOURCE_SNAPSHOT_CORRECTION_NAMESPACE)
    return payload["manifest"], dict(payload.get("files") or {})


def _locked_receipt(repo_root: Path) -> dict[str, Any] | None:
    path = repo_root / BATCH_RECEIPT_PATH
    if not path.exists():
        return None
    receipt = read_yaml(path)
    if (
        receipt.get("receipt_status") == "finalized"
        and receipt.get("finalized_receipt_locked") is True
        and receipt.get("correction_migration_id") == CORRECTION_ID
    ):
        snapshot = ((receipt.get("git") or {}).get("source_snapshot") or {})
        if snapshot.get("source_tree_hash") != source_tree_hash(repo_root):
            return None
        return receipt
    return None


def _snapshot_manifest_record(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(snapshot.get("manifest_path") or ""),
        "sha256": str(snapshot.get("manifest_sha256") or ""),
        "size_bytes": None,
    }


def _immutable_snapshot_ref(path: Path, *, sha256: str, size_bytes: int) -> dict[str, Any]:
    return {
        "path": path.as_posix(),
        "sha256": sha256,
        "size_bytes": size_bytes,
        "evidence_class": "immutable_batch_evidence_snapshot",
    }


def _staged_or_existing_bytes(repo_root: Path, staged_bytes: dict[Path, bytes], rel_path: Path) -> bytes:
    if rel_path in staged_bytes:
        return staged_bytes[rel_path]
    return (repo_root / rel_path).read_bytes()


def _build_batch_receipt(
    repo_root: Path,
    *,
    input_records: list[dict[str, Any]],
    output_records: list[dict[str, Any]],
    snapshot_manifest_record: dict[str, Any],
    source_snapshot: dict[str, Any],
    superseded_receipt_record: dict[str, Any] | None,
) -> dict[str, Any]:
    existing_path = repo_root / BATCH_RECEIPT_PATH
    if existing_path.exists():
        existing = read_yaml(existing_path)
        if (
            existing.get("receipt_status") == "finalized"
            and existing.get("finalized_receipt_locked") is True
            and existing.get("correction_migration_id") == CORRECTION_ID
            and (repo_root / SUPERSEDED_RECEIPT_PATH).exists()
            and (repo_root / FINALIZATION_RECEIPT_PATH).exists()
            and ((existing.get("git") or {}).get("source_snapshot") or {}).get("source_tree_hash") == source_snapshot.get("source_tree_hash")
        ):
            return existing
    started = _now()
    ended = _now()
    if ended <= started:
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
    source_diff = {
        "path": source_snapshot.get("tracked_patch_path"),
        "sha256": source_snapshot.get("tracked_patch_sha256"),
    }
    if not source_diff["path"] and source_snapshot.get("staged_patch_path"):
        source_diff = {
            "path": source_snapshot.get("staged_patch_path"),
            "sha256": source_snapshot.get("staged_patch_sha256"),
        }
    tree_hash = str(source_snapshot.get("source_tree_hash") or source_tree_hash(repo_root))
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
        "finalized_receipt_locked": True,
        "correction_migration_id": CORRECTION_ID,
        "git": {
            "sha": git.get("sha"),
            "branch": git.get("branch"),
            "source_dirty": bool(changed.get("source_files")),
            "generated_output_dirty": bool(changed.get("generated_files")),
            "source_tree_hash": tree_hash,
            "source_tree_hash_at_start": tree_hash,
            "source_tree_hash_at_end": tree_hash,
            "source_tree_drift_during_execution": False,
            "source_diff": source_diff,
            "source_snapshot": {
                "version": "source_snapshot_v1",
                "batch_id": BATCH_ID,
                "manifest_path": snapshot_manifest_record["path"],
                "manifest_sha256": snapshot_manifest_record["sha256"],
                "source_tree_hash": tree_hash,
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
        "inputs": sorted(input_records, key=lambda item: str(item.get("path_at_execution") or "")),
        "outputs": sorted(output_records, key=lambda item: str(item.get("path_at_execution") or item.get("path") or "")),
        "claim_boundary": CLAIM_BOUNDARY,
        "receipt_completeness": "complete",
        "superseded_receipt": superseded_receipt_record,
    }


def build_plan(repo_root: Path, *, tx_id: str | None = None, started_at_utc: str | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    started_at_utc = started_at_utc or _now()
    tx_id = tx_id or (
        read_yaml(repo_root / TRANSACTION_RECEIPT_PATH).get("transaction_id")
        if (repo_root / TRANSACTION_RECEIPT_PATH).exists()
        else "tx_plan_preview"
    )
    locked_receipt = _locked_receipt(repo_root)
    run_paths, attempt_paths = _manifest_paths(repo_root)
    batch_receipt_path = BATCH_RECEIPT_PATH.as_posix()
    staged_texts: dict[Path, str] = {}
    staged_bytes: dict[Path, bytes] = {}
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

    preimage_manifest, _preimage_archive, preimage_stage = _build_preimage_payload(repo_root, inventory["entries"])
    staged_bytes.update(preimage_stage)

    source_snapshot_manifest, source_snapshot_stage = _existing_or_built_source_snapshot(repo_root)
    staged_bytes.update(source_snapshot_stage)
    snapshot_manifest_record = {
        "path": str(source_snapshot_manifest.get("manifest_path") or ""),
        "sha256": str(source_snapshot_manifest.get("manifest_sha256") or ""),
        "size_bytes": len((repo_root / str(source_snapshot_manifest.get("manifest_path") or "")).read_bytes())
        if (repo_root / str(source_snapshot_manifest.get("manifest_path") or "")).exists()
        else len(source_snapshot_stage.get(Path(str(source_snapshot_manifest.get("manifest_path") or "")), b"")),
    }

    if locked_receipt:
        evidence_snapshots = {
            rel_path: (repo_root / rel_path).read_text(encoding="utf-8")
            for rel_path in [
                PROGRESS_LEDGER_SNAPSHOT_PATH,
                AGENT_EVENTS_SNAPSHOT_PATH,
                AGENT_METRICS_SNAPSHOT_PATH,
                RUNTIME_EVALUATOR_SNAPSHOT_PATH,
            ]
            if (repo_root / rel_path).exists()
        }
    else:
        evidence_snapshots = {
            PROGRESS_LEDGER_SNAPSHOT_PATH: (repo_root / PROGRESS_LEDGER_PATH).read_text(encoding="utf-8"),
            AGENT_EVENTS_SNAPSHOT_PATH: staged_texts[AGENT_EVENTS_PATH],
            AGENT_METRICS_SNAPSHOT_PATH: staged_texts[AGENT_METRICS_PATH],
            RUNTIME_EVALUATOR_SNAPSHOT_PATH: staged_texts[RUNTIME_EVALUATOR_PATH],
        }
    staged_texts.update(evidence_snapshots)

    superseded_receipt_record = None
    existing_receipt_path = repo_root / BATCH_RECEIPT_PATH
    if existing_receipt_path.exists() and not (repo_root / SUPERSEDED_RECEIPT_PATH).exists():
        old_receipt_text = existing_receipt_path.read_text(encoding="utf-8")
        staged_texts[SUPERSEDED_RECEIPT_PATH] = old_receipt_text
        superseded_receipt_record = {
            **_text_record(SUPERSEDED_RECEIPT_PATH, old_receipt_text),
            "reason": "previous_finalized_receipt_recorded_post_state_hashes_as_inputs_and_was_refreshable",
        }
    if existing_receipt_path.exists() and not (repo_root / SUPERSEDED_RECEIPT_V1_PATH).exists():
        current_receipt = read_yaml(existing_receipt_path)
        if current_receipt.get("correction_migration_id") != CORRECTION_ID:
            old_receipt_text = existing_receipt_path.read_text(encoding="utf-8")
            staged_texts[SUPERSEDED_RECEIPT_V1_PATH] = old_receipt_text
            superseded_receipt_record = {
                **_text_record(SUPERSEDED_RECEIPT_V1_PATH, old_receipt_text),
                "reason": "previous_wp06_correction_v1_receipt_superseded_by_append_only_v2_start_and_finalization_receipts",
            }

    input_records: list[dict[str, Any]] = []
    inventory_by_path = {str(item["path"]): item for item in inventory["entries"]}
    for rel_path in sorted(set(run_paths) | set(attempt_paths), key=lambda item: item.as_posix()):
        entry = inventory_by_path[rel_path.as_posix()]
        input_records.append(
            _receipt_input_record(
                path=rel_path,
                sha256=str(entry["pre_migration_sha256"]),
                size_bytes=_inventory_preimage_size(preimage_manifest, rel_path.as_posix()),
                validation_class="immutable_snapshot",
                preimage_ref=_preimage_ref(preimage_manifest, rel_path.as_posix()),
            )
        )
    progress_snapshot_record = _text_record(PROGRESS_LEDGER_SNAPSHOT_PATH, evidence_snapshots[PROGRESS_LEDGER_SNAPSHOT_PATH])
    input_records.append(
        _receipt_input_record(
            path=PROGRESS_LEDGER_SNAPSHOT_PATH,
            sha256=progress_snapshot_record["sha256"],
            size_bytes=progress_snapshot_record["size_bytes"],
            validation_class="immutable_snapshot",
            immutable_evidence_ref=_immutable_snapshot_ref(
                PROGRESS_LEDGER_SNAPSHOT_PATH,
                sha256=progress_snapshot_record["sha256"],
                size_bytes=progress_snapshot_record["size_bytes"],
            ),
        )
    )
    for rel_path in [HISTORICAL_RECEIPT_PATH, RUNTIME_TARGET_INVENTORY, CONSULT_RECEIPT_PATH]:
        record = _file_record(repo_root, rel_path)
        input_records.append(
            _receipt_input_record(
                path=rel_path,
                sha256=str(record["sha256"]),
                size_bytes=int(record["size_bytes"] or 0),
                validation_class="current_path_still_expected",
            )
        )

    output_records: list[dict[str, Any]] = []
    for entry in inventory["entries"]:
        rel_path = Path(str(entry["path"]))
        output_records.append(
            _receipt_output_record(
                path=rel_path,
                sha256=str(entry["post_migration_sha256"]),
                size_bytes=len(staged_texts[rel_path].encode("utf-8")),
                validation_class="current_path_still_expected",
            )
        )
    for rel_path, text in sorted(evidence_snapshots.items(), key=lambda item: item[0].as_posix()):
        record = _text_record(rel_path, text)
        output_records.append(
            _receipt_output_record(
                path=rel_path,
                sha256=record["sha256"],
                size_bytes=record["size_bytes"],
                validation_class="immutable_snapshot",
                immutable_evidence_ref=_immutable_snapshot_ref(rel_path, sha256=record["sha256"], size_bytes=record["size_bytes"]),
            )
        )
    output_records.extend(
        [
            _receipt_output_record(
                path=PREIMAGE_MANIFEST_PATH,
                sha256=_bytes_sha256(_staged_or_existing_bytes(repo_root, staged_bytes, PREIMAGE_MANIFEST_PATH)),
                size_bytes=len(_staged_or_existing_bytes(repo_root, staged_bytes, PREIMAGE_MANIFEST_PATH)),
                validation_class="immutable_snapshot",
            ),
            _receipt_output_record(
                path=PREIMAGE_ARCHIVE_PATH,
                sha256=preimage_manifest["archive_sha256"],
                size_bytes=int(preimage_manifest["archive_size_bytes"]),
                validation_class="immutable_snapshot",
            ),
        ]
    )
    if snapshot_manifest_record["path"]:
        output_records.append(
            _receipt_output_record(
                path=Path(snapshot_manifest_record["path"]),
                sha256=str(snapshot_manifest_record["sha256"]),
                size_bytes=int(snapshot_manifest_record["size_bytes"] or 0),
                validation_class="immutable_snapshot",
            )
        )
    extra_rows = [
        _artifact_reference_row(BATCH_RECEIPT_PATH, artifact_type="execution_batch_receipt", notes="WP06 provenance compaction batch receipt; hash omitted to avoid receipt/registry self-reference cycle."),
        _artifact_reference_row(ARTIFACT_REGISTRY_DELTA_PATH, artifact_type="artifact_registry_delta", notes="Immutable WP06 artifact registry delta; receipt hashes this snapshot."),
        _artifact_row_for_text(MIGRATION_INVENTORY_PATH, staged_texts[MIGRATION_INVENTORY_PATH], artifact_type="migration_inventory", notes="WP06 37/88/125 provenance compaction inventory."),
        _artifact_row_for_text(RUNTIME_EVALUATOR_PATH, staged_texts[RUNTIME_EVALUATOR_PATH], artifact_type="evaluator_result", notes="Runtime evaluator refreshed after WP06 manifest hash changes."),
        _artifact_row_for_text(AGENT_EVENTS_PATH, staged_texts[AGENT_EVENTS_PATH], artifact_type="agent_operating_events", notes="Agent event projection derived from durable progress ledger."),
        _artifact_row_for_text(AGENT_METRICS_PATH, staged_texts[AGENT_METRICS_PATH], artifact_type="agent_operating_metrics", notes="Agent metrics projection derived from event and opinion records."),
    ]
    artifact_registry_text = _artifact_registry_text(repo_root, staged_texts, extra_rows=extra_rows)
    old_fieldnames, old_rows = _read_csv(repo_root / ARTIFACT_REGISTRY_PATH)
    new_rows = list(csv.DictReader(artifact_registry_text.splitlines()))
    old_by_id = {row.get("artifact_id", ""): row for row in old_rows}
    new_by_id = {row.get("artifact_id", ""): row for row in new_rows}
    affected_ids = sorted(row["artifact_id"] for row in extra_rows)
    row_deltas = []
    for artifact_id in affected_ids:
        old_row = old_by_id.get(artifact_id)
        new_row = new_by_id.get(artifact_id)
        row_deltas.append(
            {
                "artifact_id": artifact_id,
                "path_or_uri": (new_row or old_row or {}).get("path_or_uri"),
                "old_row_sha256": _row_sha256(old_row) if old_row else None,
                "new_row_sha256": _row_sha256(new_row) if new_row else None,
                "change_reason": "wp06_receipt_truth_correction_v2_projection_update",
                "new_row": new_row,
            }
        )
    existing_delta = read_yaml(repo_root / ARTIFACT_REGISTRY_DELTA_PATH) if (repo_root / ARTIFACT_REGISTRY_DELTA_PATH).exists() else {}
    if locked_receipt and (repo_root / ARTIFACT_REGISTRY_DELTA_PATH).exists():
        artifact_delta_text = (repo_root / ARTIFACT_REGISTRY_DELTA_PATH).read_text(encoding="utf-8")
    else:
        artifact_delta = {
            "version": "artifact_registry_delta_v1",
            "batch_id": BATCH_ID,
            "migration_id": CORRECTION_ID,
            "affected_artifact_ids": affected_ids,
            "row_deltas": row_deltas,
            "affected_row_count": len(row_deltas),
            "added_row_count": sum(1 for item in row_deltas if item["old_row_sha256"] is None and item["new_row_sha256"]),
            "modified_row_count": sum(1 for item in row_deltas if item["old_row_sha256"] and item["new_row_sha256"] and item["old_row_sha256"] != item["new_row_sha256"]),
            "removed_row_count": sum(1 for item in row_deltas if item["old_row_sha256"] and item["new_row_sha256"] is None),
            "old_registry_sha256": existing_delta.get("old_registry_sha256")
            or (sha256_file(repo_root / ARTIFACT_REGISTRY_PATH) if (repo_root / ARTIFACT_REGISTRY_PATH).exists() else None),
            "new_registry_sha256": _text_sha256(artifact_registry_text),
            "canonical_registry_hash_after_projection": _text_sha256(artifact_registry_text),
            "self_reference_policy": "receipt_and_delta_rows_are_forward_stable_references_without_embedded_hashes",
        }
        artifact_delta_text = dump_yaml(artifact_delta)
    staged_texts[ARTIFACT_REGISTRY_DELTA_PATH] = artifact_delta_text
    staged_texts[ARTIFACT_REGISTRY_PATH] = artifact_registry_text
    delta_record = _text_record(ARTIFACT_REGISTRY_DELTA_PATH, artifact_delta_text)
    output_records.append(
        _receipt_output_record(
            path=ARTIFACT_REGISTRY_DELTA_PATH,
            sha256=delta_record["sha256"],
            size_bytes=delta_record["size_bytes"],
            validation_class="immutable_snapshot",
            immutable_evidence_ref=_immutable_snapshot_ref(
                ARTIFACT_REGISTRY_DELTA_PATH,
                sha256=delta_record["sha256"],
                size_bytes=delta_record["size_bytes"],
            ),
        )
    )
    locked_append_only = locked_receipt and all((repo_root / path).exists() for path in [START_RECEIPT_PATH, TRANSACTION_RECEIPT_PATH, EFFECT_INVENTORY_PATH, FINALIZATION_RECEIPT_PATH, AGENT_WORK_RECEIPT_PATH])
    if locked_append_only:
        for rel_path in [START_RECEIPT_PATH, TRANSACTION_RECEIPT_PATH, EFFECT_INVENTORY_PATH, FINALIZATION_RECEIPT_PATH, AGENT_WORK_RECEIPT_PATH, BATCH_RECEIPT_PATH]:
            staged_texts[rel_path] = (repo_root / rel_path).read_text(encoding="utf-8")
        for rel_path in [AGENT_EVENTS_PATH, AGENT_METRICS_PATH, ARTIFACT_REGISTRY_PATH, ARTIFACT_REGISTRY_DELTA_PATH]:
            if (repo_root / rel_path).exists():
                staged_texts[rel_path] = (repo_root / rel_path).read_text(encoding="utf-8")
        receipt = read_yaml(repo_root / BATCH_RECEIPT_PATH)
    else:
        start_receipt = _build_start_receipt(
            started_at_utc=started_at_utc,
            source_snapshot=source_snapshot_manifest,
            input_records=input_records,
            snapshot_manifest_record=snapshot_manifest_record,
        )
        start_receipt_text = dump_yaml(start_receipt)
        staged_texts[START_RECEIPT_PATH] = start_receipt_text
        committed_at_utc = _later(started_at_utc)
        transaction_receipt = _build_durable_transaction_receipt(
            transaction_id=tx_id,
            started_at_utc=started_at_utc,
            committed_at_utc=committed_at_utc,
            staged_texts=staged_texts,
            staged_bytes=staged_bytes,
        )
        transaction_receipt_text = dump_yaml(transaction_receipt)
        staged_texts[TRANSACTION_RECEIPT_PATH] = transaction_receipt_text
        output_records = _receipt_outputs_from_staged(staged_texts, staged_bytes)
        receipt = _build_batch_receipt(
            repo_root,
            input_records=input_records,
            output_records=output_records,
            snapshot_manifest_record=snapshot_manifest_record,
            source_snapshot=source_snapshot_manifest,
            superseded_receipt_record=superseded_receipt_record,
        )
        staged_texts[BATCH_RECEIPT_PATH] = dump_yaml(receipt)
        effect_inventory = _build_effect_inventory(repo_root, staged_texts, staged_bytes)
        effect_inventory_text = dump_yaml(effect_inventory)
        staged_texts[EFFECT_INVENTORY_PATH] = effect_inventory_text
        finalization_receipt = _build_finalization_receipt(
            finalized_at_utc=_later(committed_at_utc),
            batch_receipt_text=staged_texts[BATCH_RECEIPT_PATH],
            start_receipt_text=start_receipt_text,
            transaction_receipt_text=transaction_receipt_text,
            effect_inventory_text=effect_inventory_text,
            snapshot_manifest_record=snapshot_manifest_record,
            preimage_manifest_bytes=_staged_or_existing_bytes(repo_root, staged_bytes, PREIMAGE_MANIFEST_PATH),
        )
        staged_texts[FINALIZATION_RECEIPT_PATH] = dump_yaml(finalization_receipt)
        agent_work_receipt = _build_agent_work_receipt(
            repo_root,
            transaction_id_value=tx_id,
            batch_receipt_text=staged_texts[BATCH_RECEIPT_PATH],
            transaction_receipt_text=transaction_receipt_text,
            ended_at_utc=_later(committed_at_utc),
        )
        staged_texts[AGENT_WORK_RECEIPT_PATH] = dump_yaml(agent_work_receipt)
        effect_inventory = _build_effect_inventory(repo_root, staged_texts, staged_bytes)
        effect_inventory_text = dump_yaml(effect_inventory)
        staged_texts[EFFECT_INVENTORY_PATH] = effect_inventory_text
        finalization_receipt = _build_finalization_receipt(
            finalized_at_utc=_later(committed_at_utc),
            batch_receipt_text=staged_texts[BATCH_RECEIPT_PATH],
            start_receipt_text=start_receipt_text,
            transaction_receipt_text=transaction_receipt_text,
            effect_inventory_text=effect_inventory_text,
            snapshot_manifest_record=snapshot_manifest_record,
            preimage_manifest_bytes=_staged_or_existing_bytes(repo_root, staged_bytes, PREIMAGE_MANIFEST_PATH),
        )
        staged_texts[FINALIZATION_RECEIPT_PATH] = dump_yaml(finalization_receipt)
    return {
        "staged_texts": staged_texts,
        "staged_bytes": staged_bytes,
        "inventory": inventory,
        "receipt": receipt,
        "runtime_evaluator": runtime_evaluator,
    }


def plan_diffs(repo_root: Path, staged_texts: dict[Path, str], staged_bytes: dict[Path, bytes] | None = None) -> list[str]:
    diffs: list[str] = []
    for rel_path, text in sorted(staged_texts.items(), key=lambda item: item[0].as_posix()):
        path = repo_root / rel_path
        expected = text.encode("utf-8")
        observed = path.read_bytes() if path.exists() else b""
        if observed != expected:
            diffs.append(rel_path.as_posix())
    for rel_path, payload in sorted((staged_bytes or {}).items(), key=lambda item: item[0].as_posix()):
        path = repo_root / rel_path
        observed = path.read_bytes() if path.exists() else b""
        if observed != payload:
            diffs.append(rel_path.as_posix())
    return sorted(set(diffs))


def run(repo_root: Path, *, write: bool, fail_after_replace_count: int | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    context = ExecutionContext(
        repo_root=repo_root,
        work_item_id="work_codex_control_plane_corrective_v3",
        claim_boundary=CLAIM_BOUNDARY,
        command_argv=("python", "foundation/migrations/compact_historical_execution_provenance_v1.py", "--repo-root", ".", "--write"),
        validation_commands=("execution_provenance_validator",),
    )
    tx_id = transaction_id("|".join([context.work_item_id, *context.command_argv])) if write else None
    started_at_utc = _now() if write else None
    try:
        plan = build_plan(repo_root, tx_id=tx_id, started_at_utc=started_at_utc)
    except TypeError as exc:
        if "unexpected keyword argument" not in str(exc):
            raise
        plan = build_plan(repo_root)
    staged_texts: dict[Path, str] = plan["staged_texts"]
    staged_bytes: dict[Path, bytes] = plan.get("staged_bytes", {})
    diffs = plan_diffs(repo_root, staged_texts, staged_bytes)
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

    tx = ControlPlaneTransaction(context, tx_id=tx_id)
    for rel_path, text in sorted(staged_texts.items(), key=lambda item: item[0].as_posix()):
        tx.stage_text(rel_path, text)
    for rel_path, payload in sorted(staged_bytes.items(), key=lambda item: item[0].as_posix()):
        tx.stage_bytes(rel_path, payload)
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
