from __future__ import annotations

import argparse
import csv
import os
import sys
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
WP06_COMPACTION_ROLE = "metadata_compaction_only_not_original_execution_identity"
HISTORICAL_RECEIPT = Path("lab/executions/batch_control_plane_stabilization_v2_runtime_revalidation/execution_batch_receipt.yaml")
LEGACY_ENTRYPOINTS = Path("docs/agent_control/legacy_lifecycle_entrypoints.yaml")
ARTIFACT_REGISTRY = Path("docs/registers/artifact_registry.csv")


def _exists(path: Path) -> bool:
    return os.path.exists(filesystem_path(path))


def _stat_size(path: Path) -> int:
    return os.stat(filesystem_path(path)).st_size


def _record_for_path(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        return read_json(path)
    return read_yaml(path)


def _hash_record_errors(repo_root: Path, receipt: dict[str, Any], rel_path: Path) -> list[str]:
    errors: list[str] = []
    for label in ["inputs", "outputs"]:
        seen: dict[str, str] = {}
        for item in receipt.get(label) or []:
            path_value = str(item.get("path") or "")
            if not path_value:
                errors.append(f"{rel_path.as_posix()}: {label} item missing path")
                continue
            path = repo_root / path_value
            if not _exists(path):
                errors.append(f"{rel_path.as_posix()}: {label} path missing {path_value}")
                continue
            observed_hash = sha256_file(path)
            observed_size = _stat_size(path)
            if item.get("sha256") != observed_hash:
                errors.append(f"{rel_path.as_posix()}: {label} sha256 mismatch {path_value}")
            if int(item.get("size_bytes") or -1) != observed_size:
                errors.append(f"{rel_path.as_posix()}: {label} size mismatch {path_value}")
            if path_value in seen and seen[path_value] != item.get("sha256"):
                errors.append(f"{rel_path.as_posix()}: conflicting hashes for {path_value}")
            seen[path_value] = str(item.get("sha256") or "")
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
    if not path.exists():
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
