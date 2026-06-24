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
from spacesonar.control_plane.store import filesystem_path, read_json, read_yaml, sha256_file


WP06_BATCH_ID = "batch_control_plane_corrective_v3_wp06_provenance_compaction"
WP06_BATCH_ROOT = Path("lab/executions") / WP06_BATCH_ID
WP06_RECEIPT = WP06_BATCH_ROOT / "execution_batch_receipt.yaml"
WP06_INVENTORY = WP06_BATCH_ROOT / "migration_inventory.yaml"
WP06_PREIMAGE_MANIFEST = WP06_BATCH_ROOT / "preimages/preimage_manifest.yaml"
WP06_PREIMAGE_ARCHIVE = WP06_BATCH_ROOT / "preimages/preimages.zip"
WP06_ARTIFACT_DELTA = WP06_BATCH_ROOT / "evidence/artifact_registry_delta.yaml"
WP06_COMPACTION_ROLE = "metadata_compaction_only_not_original_execution_identity"
HISTORICAL_RECEIPT = Path("lab/executions/batch_control_plane_stabilization_v2_runtime_revalidation/execution_batch_receipt.yaml")
LEGACY_ENTRYPOINTS = Path("docs/agent_control/legacy_lifecycle_entrypoints.yaml")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")


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
                if item.get("normalization_verified") is not True:
                    errors.append(f"{WP06_PREIMAGE_MANIFEST.as_posix()}: normalization not verified {member}")
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
    else:
        errors.append(f"{WP06_ARTIFACT_DELTA.as_posix()}: missing artifact registry delta")
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


def validate(repo_root: Path) -> list[str]:
    repo_root = repo_root.resolve()
    return [
        *_validate_batch_receipts(repo_root),
        *_validate_execution_refs(repo_root),
        *_validate_wp06_inventory(repo_root),
        *_validate_wp06_preimages(repo_root),
        *_validate_historical_regeneration_lineage(repo_root),
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
