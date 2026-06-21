from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml


LOCAL_USER_PATH_RE = re.compile(r"C:\\Users\\[^\\\s,\"']+", re.IGNORECASE)
CLAIM_BLOCKING_WORDS = {
    "reviewed",
    "verified",
    "pass",
    "runtime_authority",
    "economics_pass",
    "handoff_complete",
    "live_readiness",
    "selected_baseline",
}
HASH_REQUIRED_AVAILABILITY = {"committed_manifest", "present_hash_recorded"}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def load_structured(path: Path) -> Any:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return load_json(path)
    if suffix in {".yaml", ".yml"}:
        return load_yaml(path)
    raise ValueError(f"unsupported structured file: {path}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel(path: Path, repo_root: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def as_set(values: Any) -> set[str]:
    if values is None:
        return set()
    if isinstance(values, str):
        return {item for item in values.split("|") if item}
    return {str(item) for item in values}


def walk_values(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    found = [(prefix, value)]
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            found.extend(walk_values(child, child_prefix))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_prefix = f"{prefix}[{index}]"
            found.extend(walk_values(child, child_prefix))
    return found


def validate_no_unmasked_local_paths(repo_root: Path, paths: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        text = read_text(path)
        if LOCAL_USER_PATH_RE.search(text):
            errors.append(f"{rel(path, repo_root)}: contains unmasked local C:\\Users path")
        if "local_absolute_path" in text:
            errors.append(f"{rel(path, repo_root)}: contains local_absolute_path durable field")
    return errors


def validate_gate_coverage(repo_root: Path, path: Path, data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    label = rel(path, repo_root)
    routing = data.get("skill_routing") or {}
    required = as_set(routing.get("required_gates") or data.get("required_gates"))
    coverage = data.get("required_gate_coverage") or {}
    covered = as_set(coverage.get("passed")) | as_set(coverage.get("missing")) | as_set(coverage.get("not_applicable"))
    missing_from_coverage = sorted(required - covered)
    if missing_from_coverage:
        errors.append(f"{label}: required_gate_coverage missing declared gates {missing_from_coverage}")
    if "final_claim_guard" in required and "final_claim_guard" not in covered:
        errors.append(f"{label}: final_claim_guard declared but not covered")
    passed = as_set(coverage.get("passed"))
    missing = as_set(coverage.get("missing"))
    overlap = sorted(passed & missing)
    if overlap:
        errors.append(f"{label}: gates both passed and missing {overlap}")
    return errors


def validate_skill_selection(repo_root: Path, path: Path, data: dict[str, Any]) -> list[str]:
    routing = data.get("skill_routing") or {}
    if not routing:
        return []
    errors: list[str] = []
    label = rel(path, repo_root)
    primary = routing.get("primary_skill")
    expected = set(routing.get("support_skills") or [])
    if primary:
        expected.add(str(primary))
    selected = set(routing.get("skills_selected") or [])
    missing = sorted(expected - selected)
    if missing:
        errors.append(f"{label}: skills_selected missing primary/support skills {missing}")
    extras = sorted(selected - expected)
    if extras and not routing.get("not_selected_claim_effect"):
        errors.append(f"{label}: skills_selected has extras without explicit claim effect {extras}")
    return errors


def validate_claim_boundary(repo_root: Path, path: Path, data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    label = rel(path, repo_root)
    boundary_text = " ".join(
        str(value)
        for key, value in walk_values(data)
        if key.endswith("claim_boundary") or key.endswith("claim_scope") or key.endswith("runtime_claim_boundary")
    ).lower()
    forbidden = as_set(data.get("forbidden_claims"))
    for word in CLAIM_BLOCKING_WORDS:
        if word in boundary_text and word not in forbidden and "no_" not in boundary_text:
            errors.append(f"{label}: claim boundary mentions protected word {word!r} without forbidden_claims guard")
    return errors


def validate_artifact_registry(repo_root: Path) -> list[str]:
    path = repo_root / "docs" / "registers" / "artifact_registry.csv"
    rows = read_csv_rows(path)
    errors: list[str] = []
    for row in rows:
        rel_path = row.get("path_or_uri", "")
        if not rel_path or "://" in rel_path:
            continue
        artifact_path = repo_root / rel_path
        availability = row.get("availability", "")
        must_exist = availability in HASH_REQUIRED_AVAILABILITY
        if not artifact_path.exists():
            if must_exist:
                errors.append(f"artifact_registry.csv {row.get('artifact_id')}: missing {rel_path}")
            continue
        observed_hash = sha256(artifact_path)
        observed_size = artifact_path.stat().st_size
        if row.get("sha256") and row["sha256"] != observed_hash:
            errors.append(
                f"artifact_registry.csv {row.get('artifact_id')}: sha256 mismatch "
                f"{rel_path} expected={row['sha256']} observed={observed_hash}"
            )
        if row.get("size_bytes") and int(row["size_bytes"]) != observed_size:
            errors.append(
                f"artifact_registry.csv {row.get('artifact_id')}: size mismatch "
                f"{rel_path} expected={row['size_bytes']} observed={observed_size}"
            )
        source = row.get("source_of_truth")
        if source and not (repo_root / source).exists():
            errors.append(f"artifact_registry.csv {row.get('artifact_id')}: missing source_of_truth {source}")
    return errors


def validate_run_registry(repo_root: Path) -> list[str]:
    rows = read_csv_rows(repo_root / "docs" / "registers" / "run_registry.csv")
    errors: list[str] = []
    for row in rows:
        manifest_path = repo_root / row["manifest_path"]
        receipt_path = repo_root / row["receipt_path"]
        lineage_path = repo_root / row["lineage_path"]
        metrics_path = repo_root / row["metrics_path"]
        for required_path in [manifest_path, receipt_path, lineage_path, metrics_path]:
            if not required_path.exists():
                errors.append(f"run_registry.csv {row['run_id']}: missing {rel(required_path, repo_root)}")
        if not manifest_path.exists():
            continue
        manifest = load_json(manifest_path)
        if manifest.get("run_id") != row["run_id"]:
            errors.append(f"run_registry.csv {row['run_id']}: run_manifest run_id mismatch")
        routing = manifest.get("skill_routing") or {}
        if routing.get("primary_family") != row.get("primary_family"):
            errors.append(f"run_registry.csv {row['run_id']}: primary_family mismatch")
        if routing.get("primary_skill") != row.get("primary_skill"):
            errors.append(f"run_registry.csv {row['run_id']}: primary_skill mismatch")
        if manifest.get("claim_scope") and row.get("claim_boundary") not in {manifest.get("claim_scope"), manifest.get("claim_boundary")}:
            errors.append(f"run_registry.csv {row['run_id']}: claim boundary does not match manifest")
    return errors


def validate_workspace_active_ids(repo_root: Path) -> list[str]:
    state = load_yaml(repo_root / "docs" / "workspace" / "workspace_state.yaml")
    claims = state.get("current_claims") or {}
    errors: list[str] = []
    ids = {
        "first_vertical_slice_run_id": ("lab/runs/{value}/run_manifest.json", "run"),
        "first_vertical_slice_bundle_id": ("runtime/packages/{value}/experiment_bundle.json", "bundle"),
        "first_vertical_slice_attempt_id": ("runtime/mt5_attempts/{value}/attempt_manifest.yaml", "attempt"),
    }
    for field, (pattern, label) in ids.items():
        value = claims.get(field)
        if not value:
            continue
        path = repo_root / pattern.format(value=value)
        if not path.exists():
            errors.append(f"workspace_state.yaml: active {label} id {value} missing {rel(path, repo_root)}")
    return errors


def validate_active_manifests(repo_root: Path) -> list[str]:
    paths = [
        *sorted((repo_root / "lab" / "runs").glob("*/run_manifest.json")),
        *sorted((repo_root / "lab" / "runs").glob("*/experiment_receipt.yaml")),
        *sorted((repo_root / "lab" / "runs").glob("*/runtime_evidence.yaml")),
        *sorted((repo_root / "runtime" / "packages").glob("*/experiment_bundle.json")),
        *sorted((repo_root / "runtime" / "mt5_attempts").glob("*/attempt_manifest.yaml")),
    ]
    errors: list[str] = []
    errors.extend(validate_no_unmasked_local_paths(repo_root, paths))
    for path in paths:
        data = load_structured(path)
        if isinstance(data, dict):
            errors.extend(validate_gate_coverage(repo_root, path, data))
            errors.extend(validate_skill_selection(repo_root, path, data))
            errors.extend(validate_claim_boundary(repo_root, path, data))
    return errors


def validate_bundle_attempt_relation(repo_root: Path) -> list[str]:
    errors: list[str] = []
    for attempt_path in sorted((repo_root / "runtime" / "mt5_attempts").glob("*/attempt_manifest.yaml")):
        attempt = load_yaml(attempt_path)
        bundle = ((attempt.get("artifact_identity") or {}).get("bundle") or {})
        bundle_path = bundle.get("path")
        expected_hash = bundle.get("sha256")
        if not bundle_path:
            continue
        full_bundle_path = repo_root / bundle_path
        if not full_bundle_path.exists():
            errors.append(f"{rel(attempt_path, repo_root)}: missing bundle path {bundle_path}")
            continue
        observed_hash = sha256(full_bundle_path)
        if expected_hash and expected_hash != observed_hash:
            errors.append(
                f"{rel(attempt_path, repo_root)}: bundle sha256 mismatch "
                f"expected={expected_hash} observed={observed_hash}"
            )
    return errors


def validate(repo_root: Path) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_workspace_active_ids(repo_root))
    errors.extend(validate_run_registry(repo_root))
    errors.extend(validate_artifact_registry(repo_root))
    errors.extend(validate_active_manifests(repo_root))
    errors.extend(validate_bundle_attempt_relation(repo_root))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    errors = validate(repo_root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("active-record validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
