from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sys
import zipfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from spacesonar.control_plane.provenance import validate_execution_batch_receipt
from spacesonar.control_plane.store import dump_yaml, filesystem_path, read_json, read_yaml, sha256_file


WP06_BATCH_ID = "batch_control_plane_corrective_v3_wp06_provenance_compaction"
WP06_BATCH_ROOT = Path("lab/executions") / WP06_BATCH_ID
WP06_RECEIPT = WP06_BATCH_ROOT / "execution_batch_receipt.yaml"
WP06_START_RECEIPT = WP06_BATCH_ROOT / "batch_start_receipt.yaml"
WP06_FINALIZATION_RECEIPT = WP06_BATCH_ROOT / "batch_finalization_receipt.yaml"
WP06_TRANSACTION_RECEIPT = WP06_BATCH_ROOT / "transaction_receipt.yaml"
WP06_EFFECT_INVENTORY = WP06_BATCH_ROOT / "effect_inventory.yaml"
WP06_INVENTORY = WP06_BATCH_ROOT / "migration_inventory.yaml"
WP06_PREIMAGE_MANIFEST = WP06_BATCH_ROOT / "preimages/preimage_manifest.yaml"
WP06_PREIMAGE_ARCHIVE = WP06_BATCH_ROOT / "preimages/preimages.zip"
WP06_ARTIFACT_DELTA = WP06_BATCH_ROOT / "evidence/artifact_registry_delta.yaml"
WP06_ARTIFACT_OLD_SNAPSHOT = WP06_BATCH_ROOT / "evidence/artifact_registry_before.csv"
WP06_COMPACTION_ROLE = "metadata_compaction_only_not_original_execution_identity"
HISTORICAL_RECEIPT = Path("lab/executions/batch_control_plane_stabilization_v2_runtime_revalidation/execution_batch_receipt.yaml")
LEGACY_ENTRYPOINTS = Path("docs/agent_control/legacy_lifecycle_entrypoints.yaml")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")
FORWARD_MUTABLE_OUTPUTS = {
    "lab/evaluations/control_plane_corrective_v3/runtime_contract_evaluator_v2.yaml",
    "docs/workspace/agent_operating_events.yaml",
    "docs/workspace/agent_operating_metrics.yaml",
    "docs/workspace/agent_work_receipts/WP06.yaml",
    "docs/registers/artifact_registry.csv",
}


def _exists(path: Path) -> bool:
    return os.path.exists(filesystem_path(path))


def _stat_size(path: Path) -> int:
    return os.stat(filesystem_path(path)).st_size


def _read_bytes(path: Path) -> bytes:
    with open(filesystem_path(path), "rb") as handle:
        return handle.read()


def _open_zip(path: Path) -> zipfile.ZipFile:
    return zipfile.ZipFile(filesystem_path(path))


def _record_for_path(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        return read_json(path)
    return read_yaml(path)


def _phase_path(item: dict[str, Any]) -> str:
    return str(item.get("path_at_execution") or item.get("path") or "")


def _phase_sha(item: dict[str, Any], label: str) -> str:
    return str(item.get("sha256_at_start" if label == "inputs" else "sha256_at_end") or item.get("sha256") or "")


def _phase_size(item: dict[str, Any], label: str) -> int | None:
    value = item.get("size_bytes_at_start" if label == "inputs" else "size_bytes_at_end", item.get("size_bytes"))
    if value is None:
        return None
    return int(value)


def _hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _hash_record_errors(repo_root: Path, receipt: dict[str, Any], rel_path: Path) -> list[str]:
    errors: list[str] = []
    for label in ["inputs", "outputs"]:
        seen: dict[str, str] = {}
        for item in receipt.get(label) or []:
            path_value = _phase_path(item)
            if not path_value:
                errors.append(f"{rel_path.as_posix()}: {label} item missing path")
                continue
            expected_hash = _phase_sha(item, label)
            expected_size = _phase_size(item, label)
            validation_class = str(item.get("hash_validation_class") or "current_path_still_expected")
            if label == "outputs" and path_value in FORWARD_MUTABLE_OUTPUTS:
                seen[path_value] = expected_hash
                continue
            if label == "inputs" and validation_class in {"immutable_snapshot", "superseded_mutable_path", "git_object"}:
                preimage = item.get("preimage_ref") or {}
                immutable_ref = item.get("immutable_evidence_ref") or {}
                if preimage:
                    if preimage.get("sha256") != expected_hash:
                        errors.append(f"{rel_path.as_posix()}: immutable input preimage hash mismatch {path_value}")
                    elif int(preimage.get("size_bytes") or -1) != int(expected_size or -1):
                        errors.append(f"{rel_path.as_posix()}: immutable input preimage size mismatch {path_value}")
                elif immutable_ref:
                    if immutable_ref.get("sha256") != expected_hash:
                        errors.append(f"{rel_path.as_posix()}: immutable input evidence hash mismatch {path_value}")
                    elif int(immutable_ref.get("size_bytes") or -1) != int(expected_size or -1):
                        errors.append(f"{rel_path.as_posix()}: immutable input evidence size mismatch {path_value}")
                    evidence_path = repo_root / str(immutable_ref.get("path") or "")
                    if not _exists(evidence_path):
                        errors.append(f"{rel_path.as_posix()}: immutable input evidence path missing {path_value}")
                    else:
                        observed_hash = sha256_file(evidence_path)
                        observed_size = _stat_size(evidence_path)
                        if observed_hash != expected_hash:
                            errors.append(f"{rel_path.as_posix()}: immutable input evidence file hash mismatch {path_value}")
                        if observed_size != int(expected_size or -1):
                            errors.append(f"{rel_path.as_posix()}: immutable input evidence file size mismatch {path_value}")
                else:
                    errors.append(f"{rel_path.as_posix()}: immutable input missing preimage_ref or immutable_evidence_ref {path_value}")
            else:
                path = repo_root / path_value
                if not _exists(path):
                    errors.append(f"{rel_path.as_posix()}: {label} path missing {path_value}")
                    continue
                observed_hash = sha256_file(path)
                observed_size = _stat_size(path)
                if expected_hash != observed_hash:
                    errors.append(f"{rel_path.as_posix()}: {label} sha256 mismatch {path_value}")
                if int(expected_size or -1) != observed_size:
                    errors.append(f"{rel_path.as_posix()}: {label} size mismatch {path_value}")
            if path_value in seen and seen[path_value] != expected_hash:
                errors.append(f"{rel_path.as_posix()}: conflicting hashes for {path_value}")
            seen[path_value] = expected_hash
    return errors


def _validate_batch_receipts(repo_root: Path) -> list[str]:
    errors: list[str] = []
    for path in sorted((repo_root / "lab" / "executions").glob("*/execution_batch_receipt.yaml")):
        rel_path = path.relative_to(repo_root)
        receipt = read_yaml(path)
        historical_partial = receipt.get("receipt_completeness") == "historical_partial"
        if historical_partial and rel_path == HISTORICAL_RECEIPT:
            missing = set(receipt.get("missing_historical_evidence") or [])
            required = {"staged_patch_observation", "untracked_source_archive_observation"}
            if not required.issubset(missing):
                errors.append(f"{rel_path.as_posix()}: historical partial receipt missing evidence flags")
            snapshot = (receipt.get("git") or {}).get("source_snapshot") or {}
            source_diff = (receipt.get("git") or {}).get("source_diff") or {}
            canonical_sha = source_diff.get("sha256")
            if snapshot.get("tracked_patch_sha256") != canonical_sha:
                errors.append(f"{rel_path.as_posix()}: source.patch canonical hash conflict")
            patch_path = source_diff.get("path")
            if patch_path and _exists(repo_root / patch_path) and sha256_file(repo_root / patch_path) != canonical_sha:
                errors.append(f"{rel_path.as_posix()}: source.patch file hash mismatch")
            continue
        errors.extend(f"{rel_path.as_posix()}: {item}" for item in validate_execution_batch_receipt(receipt))
        errors.extend(_hash_record_errors(repo_root, receipt, rel_path))
        errors.extend(_validate_source_snapshot(repo_root, receipt, rel_path))
    return errors


def _validate_wp06_preimages(repo_root: Path) -> list[str]:
    errors: list[str] = []
    manifest_path = repo_root / WP06_PREIMAGE_MANIFEST
    archive_path = repo_root / WP06_PREIMAGE_ARCHIVE
    if not _exists(manifest_path) or not _exists(archive_path):
        return [f"{WP06_PREIMAGE_MANIFEST.as_posix()}: missing WP06 preimage archive"]
    manifest = read_yaml(manifest_path)
    archive_bytes = _read_bytes(archive_path)
    if manifest.get("batch_id") != WP06_BATCH_ID:
        errors.append(f"{WP06_PREIMAGE_MANIFEST.as_posix()}: batch_id mismatch")
    if manifest.get("archive_sha256") != _hash_bytes(archive_bytes):
        errors.append(f"{WP06_PREIMAGE_MANIFEST.as_posix()}: archive hash mismatch")
    if int(manifest.get("archive_size_bytes") or -1) != len(archive_bytes):
        errors.append(f"{WP06_PREIMAGE_MANIFEST.as_posix()}: archive size mismatch")
    entries = manifest.get("entries") or []
    try:
        with _open_zip(archive_path) as archive:
            names = set(archive.namelist())
            for item in entries:
                member = str(item.get("archive_member") or "")
                if member not in names:
                    errors.append(f"{WP06_PREIMAGE_ARCHIVE.as_posix()}: missing member {member}")
                    continue
                payload = archive.read(member)
                if item.get("sha256") != _hash_bytes(payload):
                    errors.append(f"{WP06_PREIMAGE_ARCHIVE.as_posix()}: member hash mismatch {member}")
                if int(item.get("size_bytes") or -1) != len(payload):
                    errors.append(f"{WP06_PREIMAGE_ARCHIVE.as_posix()}: member size mismatch {member}")
                symbolic = str(item.get("git_revision") or "")
                if symbolic in {"HEAD", "HEAD~1", "main"} or (symbolic and len(symbolic) != 40):
                    errors.append(f"{WP06_PREIMAGE_MANIFEST.as_posix()}: symbolic git revision is not allowed {member}")
                if len(str(item.get("git_commit_sha") or "")) != 40:
                    errors.append(f"{WP06_PREIMAGE_MANIFEST.as_posix()}: git_commit_sha missing or invalid {member}")
                if not str(item.get("git_blob_sha") or ""):
                    errors.append(f"{WP06_PREIMAGE_MANIFEST.as_posix()}: git_blob_sha missing {member}")
                if item.get("content_sha256") != item.get("sha256"):
                    errors.append(f"{WP06_PREIMAGE_MANIFEST.as_posix()}: content_sha256 mismatch {member}")
                if item.get("content_match_verified") is not True:
                    errors.append(f"{WP06_PREIMAGE_MANIFEST.as_posix()}: content match not verified {member}")
                if item.get("normalization_applied") is True and not item.get("normalization_type"):
                    errors.append(f"{WP06_PREIMAGE_MANIFEST.as_posix()}: normalization type missing {member}")
    except zipfile.BadZipFile as exc:
        errors.append(f"{WP06_PREIMAGE_ARCHIVE.as_posix()}: invalid zip {exc}")
    return errors


def _validate_source_snapshot(repo_root: Path, receipt: dict[str, Any], rel_path: Path) -> list[str]:
    errors: list[str] = []
    git = receipt.get("git") or {}
    snapshot = git.get("source_snapshot") or {}
    manifest_rel = str(snapshot.get("manifest_path") or "")
    if not manifest_rel:
        return [f"{rel_path.as_posix()}: source snapshot manifest missing"]
    manifest_path = repo_root / manifest_rel
    if not _exists(manifest_path):
        return [f"{rel_path.as_posix()}: source snapshot manifest path missing {manifest_rel}"]
    if snapshot.get("manifest_sha256") != sha256_file(manifest_path):
        errors.append(f"{rel_path.as_posix()}: source snapshot manifest sha256 mismatch")
    manifest = read_yaml(manifest_path)
    if manifest.get("batch_id") != receipt.get("batch_id"):
        errors.append(f"{rel_path.as_posix()}: source snapshot batch_id mismatch")
    if manifest.get("source_tree_hash") and len(str(manifest.get("source_tree_hash"))) != 64:
        errors.append(f"{rel_path.as_posix()}: source snapshot source_tree_hash format invalid")
    tree_hashes = [
        str(git.get("source_tree_hash_at_start") or ""),
        str((git.get("source_snapshot") or {}).get("source_tree_hash") or ""),
        str(manifest.get("source_tree_hash") or ""),
    ]
    if all(tree_hashes) and len(set(tree_hashes)) != 1:
        errors.append(f"{rel_path.as_posix()}: source tree hash mismatch between receipt and snapshot")
    source_dirty = bool(git.get("source_dirty"))
    dirty_mechanisms = [
        manifest.get("tracked_patch_path"),
        manifest.get("staged_patch_path"),
        manifest.get("untracked_archive_path"),
        manifest.get("deleted_paths"),
        manifest.get("renamed_paths"),
        manifest.get("binary_source_paths"),
    ]
    if source_dirty and not any(bool(item) for item in dirty_mechanisms):
        errors.append(f"{rel_path.as_posix()}: source_dirty true without recorded dirty-source mechanism")
    for path_key, hash_key in [
        ("tracked_patch_path", "tracked_patch_sha256"),
        ("staged_patch_path", "staged_patch_sha256"),
        ("untracked_archive_path", "untracked_archive_sha256"),
    ]:
        value = manifest.get(path_key)
        if not value:
            continue
        path = repo_root / str(value)
        if not _exists(path):
            errors.append(f"{rel_path.as_posix()}: source snapshot {path_key} missing {value}")
            continue
        if manifest.get(hash_key) != sha256_file(path):
            errors.append(f"{rel_path.as_posix()}: source snapshot {path_key} hash mismatch")
    archive_rel = manifest.get("untracked_archive_path")
    if archive_rel:
        archive_path = repo_root / str(archive_rel)
        try:
            with _open_zip(archive_path) as archive:
                names = set(archive.namelist())
                for item in manifest.get("untracked_archive_manifest") or []:
                    member = str(item.get("path") or "")
                    if member not in names:
                        errors.append(f"{rel_path.as_posix()}: untracked archive missing {member}")
                        continue
                    payload = archive.read(member)
                    if item.get("sha256") != _hash_bytes(payload):
                        errors.append(f"{rel_path.as_posix()}: untracked archive member hash mismatch {member}")
        except zipfile.BadZipFile as exc:
            errors.append(f"{rel_path.as_posix()}: invalid untracked archive {exc}")
    source_diff = git.get("source_diff") or {}
    if source_diff.get("path") and source_diff.get("path") != manifest.get("tracked_patch_path") and source_diff.get("path") != manifest.get("staged_patch_path"):
        errors.append(f"{rel_path.as_posix()}: source_diff path not present in source snapshot")
    if source_diff.get("path") and source_diff.get("sha256"):
        if source_diff.get("path") == manifest.get("tracked_patch_path") and source_diff.get("sha256") != manifest.get("tracked_patch_sha256"):
            errors.append(f"{rel_path.as_posix()}: source_diff tracked patch hash mismatch")
        if source_diff.get("path") == manifest.get("staged_patch_path") and source_diff.get("sha256") != manifest.get("staged_patch_sha256"):
            errors.append(f"{rel_path.as_posix()}: source_diff staged patch hash mismatch")
    return errors


def _validate_execution_refs(repo_root: Path) -> list[str]:
    errors: list[str] = []
    record_paths = [
        *sorted((repo_root / "lab" / "runs").glob("*/run_manifest.json")),
        *sorted((repo_root / "runtime" / "mt5_attempts").glob("*/attempt_manifest.yaml")),
    ]
    for path in record_paths:
        record = _record_for_path(path)
        ref = record.get("execution_batch_ref")
        if not ref:
            version = str(record.get("version") or "")
            if version in {"run_manifest_v3", "mt5_attempt_manifest_v2"}:
                errors.append(f"{path.relative_to(repo_root).as_posix()}: execution_batch_ref missing for {version}")
            elif not record.get("provenance_compaction"):
                errors.append(f"{path.relative_to(repo_root).as_posix()}: execution_batch_ref missing and no historical compaction marker")
            continue
        batch_id = str(ref.get("batch_id") or "")
        receipt_rel = str(ref.get("path") or "")
        receipt_path = repo_root / receipt_rel
        if not _exists(receipt_path):
            errors.append(f"{path.relative_to(repo_root).as_posix()}: execution_batch_ref receipt missing")
            continue
        receipt = read_yaml(receipt_path)
        if receipt.get("batch_id") != batch_id:
            errors.append(f"{path.relative_to(repo_root).as_posix()}: execution_batch_ref batch_id mismatch")
        if ref.get("sha256") != sha256_file(receipt_path):
            errors.append(f"{path.relative_to(repo_root).as_posix()}: execution_batch_ref sha256 mismatch")
        receipt_errors = validate_execution_batch_receipt(receipt)
        if receipt_errors:
            errors.append(f"{path.relative_to(repo_root).as_posix()}: execution_batch_ref receipt invalid")
    return errors


def _canonical_self_hash(payload: dict[str, Any]) -> str:
    import copy

    clone = copy.deepcopy(payload)
    (((clone.setdefault("receipt_sha256", {})))["value"]) = ""
    return hashlib.sha256(dump_yaml(clone).encode("utf-8")).hexdigest()


def validate_agent_work_receipt(repo_root: Path, rel_path: Path) -> list[str]:
    path = repo_root / rel_path
    if not _exists(path):
        return [f"{rel_path.as_posix()}: missing agent work receipt"]
    receipt = read_yaml(path)
    errors: list[str] = []
    for field in ["version", "work_item_id", "agent_mode", "evidence_class", "started_at_utc", "ended_at_utc", "claim_boundary"]:
        if receipt.get(field) in (None, "", [], {}):
            errors.append(f"{rel_path.as_posix()}: missing {field}")
    if receipt.get("version") != "agent_work_receipt_v1":
        errors.append(f"{rel_path.as_posix()}: version mismatch")
    try:
        from datetime import datetime

        start = datetime.fromisoformat(str(receipt.get("started_at_utc")).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(receipt.get("ended_at_utc")).replace("Z", "+00:00"))
        if end < start:
            errors.append(f"{rel_path.as_posix()}: ended_at_utc precedes started_at_utc")
    except Exception as exc:
        errors.append(f"{rel_path.as_posix()}: invalid timestamp {exc}")
    for ref in receipt.get("source_refs") or []:
        ref_path = repo_root / str(ref.get("path") or "")
        if not _exists(ref_path):
            errors.append(f"{rel_path.as_posix()}: source ref missing {ref.get('path')}")
            continue
        if ref.get("sha256") != sha256_file(ref_path):
            errors.append(f"{rel_path.as_posix()}: source ref hash mismatch {ref.get('path')}")
        if int(ref.get("size_bytes") or -1) != _stat_size(ref_path):
            errors.append(f"{rel_path.as_posix()}: source ref size mismatch {ref.get('path')}")
    for key in ["wp06_batch_receipt_ref", "transaction_receipt_ref", "finalization_receipt_ref"]:
        ref = receipt.get(key) or {}
        if not ref.get("path"):
            errors.append(f"{rel_path.as_posix()}: {key} missing")
            continue
        ref_path = repo_root / str(ref.get("path") or "")
        if not _exists(ref_path):
            errors.append(f"{rel_path.as_posix()}: {key} missing")
            continue
        if ref.get("sha256") != sha256_file(ref_path):
            errors.append(f"{rel_path.as_posix()}: {key} hash mismatch")
        if int(ref.get("size_bytes") or -1) != _stat_size(ref_path):
            errors.append(f"{rel_path.as_posix()}: {key} size mismatch")
    stored_hash = ((receipt.get("receipt_sha256") or {}).get("value"))
    if not stored_hash or stored_hash != _canonical_self_hash(receipt):
        errors.append(f"{rel_path.as_posix()}: self-hash mismatch")
    return errors


def _validate_agent_work_receipts(repo_root: Path) -> list[str]:
    root = repo_root / "docs" / "workspace" / "agent_work_receipts"
    if not _exists(root):
        return []
    errors: list[str] = []
    for path in sorted(root.glob("*.yaml")):
        errors.extend(validate_agent_work_receipt(repo_root, path.relative_to(repo_root)))
    return errors


def _validate_wp06_inventory(repo_root: Path) -> list[str]:
    inventory_path = repo_root / WP06_INVENTORY
    if not _exists(inventory_path):
        return [f"{WP06_INVENTORY.as_posix()}: missing WP06 provenance compaction inventory"]
    inventory = read_yaml(inventory_path)
    entries = inventory.get("entries") or []
    run_entries = [item for item in entries if item.get("record_type") == "run_manifest"]
    attempt_entries = [item for item in entries if item.get("record_type") == "attempt_manifest"]
    errors: list[str] = []
    if len(run_entries) != 37 or len(attempt_entries) != 88 or len(entries) != 125:
        errors.append(f"{WP06_INVENTORY.as_posix()}: expected 37/88/125 records")
    receipt_inputs: dict[str, dict[str, Any]] = {}
    receipt_outputs: dict[str, dict[str, Any]] = {}
    if _exists(repo_root / WP06_RECEIPT):
        receipt = read_yaml(repo_root / WP06_RECEIPT)
        receipt_inputs = {_phase_path(item): item for item in receipt.get("inputs") or []}
        receipt_outputs = {_phase_path(item): item for item in receipt.get("outputs") or []}
    seen_paths: set[str] = set()
    for item in entries:
        rel_path = str(item.get("path") or "")
        if rel_path in seen_paths:
            errors.append(f"{WP06_INVENTORY.as_posix()}: duplicate path {rel_path}")
        seen_paths.add(rel_path)
        path = repo_root / rel_path
        if not _exists(path):
            errors.append(f"{WP06_INVENTORY.as_posix()}: missing record {rel_path}")
            continue
        if item.get("post_migration_sha256") != sha256_file(path):
            errors.append(f"{WP06_INVENTORY.as_posix()}: post hash mismatch {rel_path}")
        record = _record_for_path(path)
        marker = record.get("provenance_compaction") or {}
        if marker.get("compaction_role") != WP06_COMPACTION_ROLE:
            errors.append(f"{rel_path}: compaction role is not historical metadata-only")
        if marker.get("historical_inline_provenance_retained") is not True:
            errors.append(f"{rel_path}: historical inline provenance retention not recorded")
        if not item.get("historical_execution_provenance_present"):
            errors.append(f"{rel_path}: inventory does not record historical provenance presence")
        input_record = receipt_inputs.get(rel_path)
        output_record = receipt_outputs.get(rel_path)
        if not input_record:
            errors.append(f"{WP06_RECEIPT.as_posix()}: missing input record for {rel_path}")
        elif _phase_sha(input_record, "inputs") != item.get("pre_migration_sha256"):
            errors.append(f"{WP06_RECEIPT.as_posix()}: input pre hash mismatch {rel_path}")
        if not output_record:
            errors.append(f"{WP06_RECEIPT.as_posix()}: missing output record for {rel_path}")
        elif _phase_sha(output_record, "outputs") != item.get("post_migration_sha256"):
            errors.append(f"{WP06_RECEIPT.as_posix()}: output post hash mismatch {rel_path}")
    if _exists(repo_root / WP06_ARTIFACT_DELTA):
        delta = read_yaml(repo_root / WP06_ARTIFACT_DELTA)
        if not delta.get("canonical_registry_hash_after_projection"):
            errors.append(f"{WP06_ARTIFACT_DELTA.as_posix()}: missing canonical registry hash")
        for item in delta.get("row_deltas") or []:
            artifact_id = str(item.get("artifact_id") or "")
            if not artifact_id or not item.get("path_or_uri") or not item.get("change_reason"):
                errors.append(f"{WP06_ARTIFACT_DELTA.as_posix()}: incomplete row delta")
                continue
            for key in ["old_row", "new_row"]:
                snapshot_row = item.get(key)
                declared_hash = item.get(f"{key}_sha256")
                if snapshot_row is None:
                    if declared_hash is not None:
                        errors.append(f"{WP06_ARTIFACT_DELTA.as_posix()}: {key} null hash mismatch {artifact_id}")
                    continue
                if not isinstance(snapshot_row, dict):
                    errors.append(f"{WP06_ARTIFACT_DELTA.as_posix()}: {key} snapshot invalid {artifact_id}")
                    continue
                observed = hashlib.sha256(
                    __import__("json").dumps(snapshot_row, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest()
                if declared_hash != observed:
                    errors.append(f"{WP06_ARTIFACT_DELTA.as_posix()}: {key} hash mismatch {artifact_id}")
        if int(delta.get("affected_row_count") or -1) != len(delta.get("row_deltas") or []):
            errors.append(f"{WP06_ARTIFACT_DELTA.as_posix()}: affected_row_count mismatch")
        if _exists(repo_root / WP06_ARTIFACT_OLD_SNAPSHOT):
            with open(filesystem_path(repo_root / WP06_ARTIFACT_OLD_SNAPSHOT), "r", newline="", encoding="utf-8-sig") as handle:
                fieldnames = list(csv.DictReader(handle).fieldnames or [])
            with open(filesystem_path(repo_root / WP06_ARTIFACT_OLD_SNAPSHOT), "r", newline="", encoding="utf-8-sig") as handle:
                old_rows = {row.get("artifact_id", ""): dict(row) for row in csv.DictReader(handle) if row.get("artifact_id")}
            reconstructed = dict(old_rows)
            for item in delta.get("row_deltas") or []:
                artifact_id = str(item.get("artifact_id") or "")
                if item.get("new_row") is None:
                    reconstructed.pop(artifact_id, None)
                else:
                    reconstructed[artifact_id] = item["new_row"]
            from io import StringIO

            handle = StringIO()
            writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            for row in sorted(reconstructed.values(), key=lambda value: str(value.get("path_or_uri") or "")):
                writer.writerow({key: "" if row.get(key) is None else row.get(key, "") for key in fieldnames})
            rebuilt = handle.getvalue()
            if hashlib.sha256(rebuilt.encode("utf-8")).hexdigest() != delta.get("new_registry_sha256"):
                errors.append(f"{WP06_ARTIFACT_DELTA.as_posix()}: row delta does not reconstruct new registry")
            if delta.get("old_registry_sha256") != sha256_file(repo_root / WP06_ARTIFACT_OLD_SNAPSHOT):
                errors.append(f"{WP06_ARTIFACT_DELTA.as_posix()}: old registry snapshot hash mismatch")
            if delta.get("old_registry_sha256") != delta.get("new_registry_sha256") and not delta.get("row_deltas"):
                errors.append(f"{WP06_ARTIFACT_DELTA.as_posix()}: registry hash changed without row deltas")
        else:
            errors.append(f"{WP06_ARTIFACT_OLD_SNAPSHOT.as_posix()}: missing old artifact registry snapshot")
    else:
        errors.append(f"{WP06_ARTIFACT_DELTA.as_posix()}: missing artifact registry delta")
    return errors


def _validate_wp06_append_only_receipts(repo_root: Path) -> list[str]:
    errors: list[str] = []
    required = [WP06_START_RECEIPT, WP06_FINALIZATION_RECEIPT, WP06_TRANSACTION_RECEIPT, WP06_EFFECT_INVENTORY]
    for rel_path in required:
        if not _exists(repo_root / rel_path):
            errors.append(f"{rel_path.as_posix()}: missing WP06 append-only receipt")
    if errors:
        return errors
    start = read_yaml(repo_root / WP06_START_RECEIPT)
    finalization = read_yaml(repo_root / WP06_FINALIZATION_RECEIPT)
    tx = read_yaml(repo_root / WP06_TRANSACTION_RECEIPT)
    effects = read_yaml(repo_root / WP06_EFFECT_INVENTORY)
    batch = read_yaml(repo_root / WP06_RECEIPT)
    if batch.get("started_at_utc") != start.get("started_at_utc"):
        errors.append(f"{WP06_RECEIPT.as_posix()}: started_at_utc does not match start receipt")
    if batch.get("ended_at_utc") != finalization.get("finalized_at_utc"):
        errors.append(f"{WP06_RECEIPT.as_posix()}: ended_at_utc does not match finalization receipt")
    if not tx.get("input_hashes"):
        errors.append(f"{WP06_TRANSACTION_RECEIPT.as_posix()}: input_hashes must be nonempty")
    if finalization.get("batch_start_receipt_sha256") != sha256_file(repo_root / WP06_START_RECEIPT):
        errors.append(f"{WP06_FINALIZATION_RECEIPT.as_posix()}: start receipt hash mismatch")
    if finalization.get("transaction_receipt_sha256") != sha256_file(repo_root / WP06_TRANSACTION_RECEIPT):
        errors.append(f"{WP06_FINALIZATION_RECEIPT.as_posix()}: transaction receipt hash mismatch")
    if finalization.get("effect_inventory_sha256") != sha256_file(repo_root / WP06_EFFECT_INVENTORY):
        errors.append(f"{WP06_FINALIZATION_RECEIPT.as_posix()}: effect inventory hash mismatch")
    if finalization.get("execution_batch_receipt_sha256") != sha256_file(repo_root / WP06_RECEIPT):
        errors.append(f"{WP06_FINALIZATION_RECEIPT.as_posix()}: batch receipt hash mismatch")
    snapshot_manifest = str((read_yaml(repo_root / WP06_RECEIPT).get("git") or {}).get("source_snapshot", {}).get("manifest_path") or "")
    if not snapshot_manifest or not _exists(repo_root / snapshot_manifest):
        errors.append(f"{WP06_FINALIZATION_RECEIPT.as_posix()}: source snapshot manifest missing")
    elif finalization.get("source_snapshot_manifest_sha256") != sha256_file(repo_root / snapshot_manifest):
        errors.append(f"{WP06_FINALIZATION_RECEIPT.as_posix()}: source snapshot manifest hash mismatch")
    if finalization.get("preimage_manifest_sha256") != sha256_file(repo_root / WP06_PREIMAGE_MANIFEST):
        errors.append(f"{WP06_FINALIZATION_RECEIPT.as_posix()}: preimage manifest hash mismatch")
    try:
        from datetime import datetime

        start_time = datetime.fromisoformat(str(start.get("started_at_utc")).replace("Z", "+00:00"))
        commit_time = datetime.fromisoformat(str(tx.get("committed_at_utc")).replace("Z", "+00:00"))
        final_time = datetime.fromisoformat(str(finalization.get("finalized_at_utc")).replace("Z", "+00:00"))
        if not (start_time < commit_time <= final_time):
            errors.append(f"{WP06_FINALIZATION_RECEIPT.as_posix()}: invalid start/commit/finalization ordering")
    except Exception as exc:
        errors.append(f"{WP06_FINALIZATION_RECEIPT.as_posix()}: invalid timing data {exc}")
    effect_paths = {str(item.get("path") or "") for item in effects.get("effects") or []}
    applied_paths = set(str(path) for path in tx.get("applied_paths") or [])
    if applied_paths != effect_paths:
        missing = sorted(applied_paths - effect_paths)
        extra = sorted(effect_paths - applied_paths)
        errors.append(f"{WP06_EFFECT_INVENTORY.as_posix()}: transaction applied paths differ from effect inventory missing={missing[:5]} extra={extra[:5]}")
    if sorted(effects.get("mutable_effect_paths") or []) != sorted(applied_paths):
        errors.append(f"{WP06_EFFECT_INVENTORY.as_posix()}: mutable_effect_paths mismatch")
    for item in effects.get("effects") or []:
        rel = str(item.get("path") or "")
        if item.get("validation_class") == "self_reference_excluded":
            continue
        if rel in FORWARD_MUTABLE_OUTPUTS:
            continue
        path = repo_root / rel
        if not _exists(path):
            errors.append(f"{WP06_EFFECT_INVENTORY.as_posix()}: effect path missing {rel}")
            continue
        expected = item.get("post_sha256")
        if expected and expected != "self_hash_cycle_omitted" and expected != sha256_file(path):
            errors.append(f"{WP06_EFFECT_INVENTORY.as_posix()}: effect hash mismatch {rel}")
    stored_hash = ((finalization.get("receipt_sha256") or {}).get("value"))
    if not stored_hash or stored_hash != _canonical_self_hash(finalization):
        errors.append(f"{WP06_FINALIZATION_RECEIPT.as_posix()}: self-hash mismatch")
    return errors


def _disabled_entrypoints(repo_root: Path) -> set[str]:
    path = repo_root / LEGACY_ENTRYPOINTS
    if not _exists(path):
        return set()
    data = read_yaml(path)
    return {
        str(item.get("path") or "").replace("\\", "/")
        for item in data.get("entrypoints") or []
        if item.get("classification") == "historical_disabled"
    }


def _validate_historical_regeneration_lineage(repo_root: Path) -> list[str]:
    path = repo_root / ARTIFACT_REGISTRY
    if not _exists(path):
        return []
    disabled = _disabled_entrypoints(repo_root)
    errors: list[str] = []
    with open(filesystem_path(path), "r", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    for idx, row in enumerate(rows, start=2):
        for field, allowed_prefix in [
            ("producer_command", "historical_producer:"),
            ("regeneration_command", "historical_disabled:"),
        ]:
            value = str(row.get(field) or "")
            normalized = value.replace("\\", "/")
            if value.startswith(allowed_prefix):
                continue
            if field == "regeneration_command" and value.startswith(("replacement_command:", "regeneration_unavailable")):
                continue
            if any(entrypoint in normalized for entrypoint in disabled):
                errors.append(
                    f"{ARTIFACT_REGISTRY.as_posix()}: row {idx} {field} uses historical-disabled entrypoint without lineage marker"
                )
    return errors


def _validate_future_writer_schema_versions(repo_root: Path) -> list[str]:
    errors: list[str] = []
    roots = [repo_root / "src", repo_root / "foundation", repo_root / "lab" / "templates"]
    forbidden = [
        '"version": "' + "run_manifest_v2" + '"',
        '"version": "' + "mt5_attempt_manifest_v1" + '"',
        "version: " + "mt5_attempt_manifest_v1",
    ]
    for root in roots:
        if not _exists(root):
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".py", ".json", ".yaml", ".yml"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for needle in forbidden:
                if needle in text:
                    errors.append(f"{path.relative_to(repo_root).as_posix()}: forbidden future writer schema literal {needle}")
    return errors


def validate(repo_root: Path) -> list[str]:
    repo_root = repo_root.resolve()
    return [
        *_validate_batch_receipts(repo_root),
        *_validate_execution_refs(repo_root),
        *_validate_wp06_inventory(repo_root),
        *_validate_wp06_preimages(repo_root),
        *_validate_wp06_append_only_receipts(repo_root),
        *_validate_agent_work_receipts(repo_root),
        *_validate_historical_regeneration_lineage(repo_root),
        *_validate_future_writer_schema_versions(repo_root),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args(argv)
    errors = validate(Path(args.repo_root))
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("execution provenance validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
