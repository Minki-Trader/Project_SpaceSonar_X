from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
for path in [REPO_ROOT, REPO_ROOT / "src"]:
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

from spacesonar.control_plane.store import filesystem_path, sha256_file


PROTECTED_CLAIMS = {
    "selected_baseline",
    "runtime_authority",
    "economics_pass",
    "live_readiness",
    "goal_achieve",
}
HASH_ONLY_AVAILABILITY = {
    "local_generated_hash_recorded_not_committed",
    "hash_record_only",
    "non_committed_hash_record",
}
LOCAL_PATH_RE = re.compile(r"C:\\Users\\", re.IGNORECASE)


def path_exists(path: Path) -> bool:
    return os.path.exists(filesystem_path(path))


def load_json(path: Path) -> dict[str, Any]:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def load_yaml(path: Path) -> dict[str, Any]:
    with open(filesystem_path(path), "r", encoding="utf-8-sig") as handle:
        payload = yaml.safe_load(handle)
    return payload if isinstance(payload, dict) else {}


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with open(filesystem_path(path), "r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def rel(path: Path, repo_root: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def is_repo_relative(value: str) -> bool:
    path = Path(value.replace("\\", "/"))
    return bool(value) and not path.is_absolute() and ".." not in path.parts


def local_path_errors(repo_root: Path, paths: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in paths:
        if not path_exists(path):
            continue
        text = Path(filesystem_path(path)).read_text(encoding="utf-8-sig", errors="replace")
        if LOCAL_PATH_RE.search(text):
            errors.append(f"{rel(path, repo_root)}: contains unmasked local C:\\Users path")
    return errors


def load_run_records(repo_root: Path, run_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    run_dir = repo_root / "lab" / "runs" / run_id
    paths = {
        "manifest": run_dir / "run_manifest.json",
        "receipt": run_dir / "experiment_receipt.yaml",
        "lineage": run_dir / "artifact_lineage.json",
        "metrics": run_dir / "metrics.json",
    }
    missing = [name for name, path in paths.items() if not path_exists(path)]
    if missing:
        raise FileNotFoundError(f"{run_id}: missing {', '.join(missing)}")
    return (
        load_json(paths["manifest"]),
        load_yaml(paths["receipt"]),
        load_json(paths["lineage"]),
        load_json(paths["metrics"]),
    )


def hash_ref_errors(repo_root: Path, owner: str, refs: list[dict[str, Any]]) -> tuple[list[str], int]:
    errors: list[str] = []
    hash_only_count = 0
    for item in refs:
        if not isinstance(item, dict):
            errors.append(f"{owner}: hash ref is not a mapping")
            continue
        path_value = str(item.get("path") or "")
        if not is_repo_relative(path_value):
            errors.append(f"{owner}: hash ref path must be repo-relative: {path_value!r}")
            continue
        expected_hash = str(item.get("sha256") or "")
        expected_size = item.get("size_bytes")
        availability = str(item.get("availability") or "present_hash_recorded")
        path = repo_root / path_value
        if not path_exists(path):
            if availability in HASH_ONLY_AVAILABILITY:
                hash_only_count += 1
                continue
            errors.append(f"{owner}: hash ref path missing: {path_value}")
            continue
        observed_hash = sha256_file(path)
        observed_size = os.stat(filesystem_path(path)).st_size
        if expected_hash and expected_hash != observed_hash:
            errors.append(f"{owner}: sha256 mismatch {path_value}")
        if expected_size not in (None, "") and int(expected_size) != observed_size:
            errors.append(f"{owner}: size mismatch {path_value}")
    return errors, hash_only_count


def validate_run(
    repo_root: Path,
    run_id: str,
    *,
    campaign_id: str | None,
    pre_runtime: bool,
    allow_bundle_id: bool = False,
) -> tuple[list[str], str]:
    errors: list[str] = []
    try:
        manifest, receipt, lineage, metrics = load_run_records(repo_root, run_id)
    except FileNotFoundError as exc:
        return [str(exc)], ""

    run_dir = repo_root / "lab" / "runs" / run_id
    record_paths = [
        run_dir / "run_manifest.json",
        run_dir / "experiment_receipt.yaml",
        run_dir / "artifact_lineage.json",
        run_dir / "metrics.json",
    ]
    errors.extend(local_path_errors(repo_root, record_paths))
    for label, payload in [
        ("manifest", manifest),
        ("receipt", receipt),
        ("lineage", lineage),
        ("metrics", metrics),
    ]:
        if payload.get("run_id") != run_id:
            errors.append(f"{run_id}: {label} run_id mismatch")

    id_chain = manifest.get("id_chain") or {}
    for field in ["goal_id", "wave_id", "campaign_id", "idea_id", "hypothesis_id", "surface_id", "sweep_id"]:
        if not id_chain.get(field):
            errors.append(f"{run_id}: id_chain.{field} missing")
    if campaign_id and id_chain.get("campaign_id") != campaign_id:
        errors.append(f"{run_id}: id_chain.campaign_id mismatch")
    if pre_runtime:
        if id_chain.get("bundle_id") and not allow_bundle_id:
            errors.append(f"{run_id}: bundle_id must be empty before L4/candidate evidence")
        if id_chain.get("candidate_id"):
            errors.append(f"{run_id}: candidate_id must be empty before candidate evidence")

    storage = manifest.get("storage_contract") or {}
    expected_storage = {
        "source_of_truth": f"lab/runs/{run_id}/run_manifest.json",
        "receipt": f"lab/runs/{run_id}/experiment_receipt.yaml",
        "lineage": f"lab/runs/{run_id}/artifact_lineage.json",
        "metrics": f"lab/runs/{run_id}/metrics.json",
    }
    for key, expected in expected_storage.items():
        observed = str(storage.get(key) or "")
        if observed != expected:
            errors.append(f"{run_id}: storage_contract.{key} expected {expected}, observed {observed}")
        if not path_exists(repo_root / expected):
            errors.append(f"{run_id}: storage_contract.{key} path missing {expected}")

    claim_boundary = str(manifest.get("claim_boundary") or "")
    forbidden = set(str(item) for item in manifest.get("forbidden_claims") or [])
    if not claim_boundary:
        errors.append(f"{run_id}: claim_boundary missing")
    for claim in PROTECTED_CLAIMS:
        if claim not in forbidden:
            errors.append(f"{run_id}: forbidden_claims missing {claim}")
    if pre_runtime:
        for token in ["no_runtime_authority", "no_economics_pass", "no_live_readiness", "no_goal_achieve"]:
            if token not in claim_boundary:
                errors.append(f"{run_id}: claim_boundary missing {token}")
        missing_gates = set((manifest.get("required_gate_coverage") or {}).get("missing") or [])
        if "L4_split_runtime_probe_for_valid_proxy_run" not in missing_gates:
            errors.append(f"{run_id}: L4 missing gate not explicit")

    result_judgment = str(manifest.get("result_judgment") or metrics.get("judgment_label") or "")
    if result_judgment in PROTECTED_CLAIMS:
        errors.append(f"{run_id}: protected result_judgment {result_judgment}")
    if metrics.get("judgment_label") and metrics.get("judgment_label") != result_judgment:
        errors.append(f"{run_id}: metrics judgment_label mismatch")

    for owner, refs in [
        (f"{run_id}: manifest provenance.inputs", (manifest.get("provenance") or {}).get("input_hashes") or []),
        (f"{run_id}: manifest provenance.outputs", (manifest.get("provenance") or {}).get("output_hashes") or []),
        (f"{run_id}: receipt provenance.inputs", (receipt.get("provenance") or {}).get("input_hashes") or []),
        (f"{run_id}: receipt provenance.outputs", (receipt.get("provenance") or {}).get("output_hashes") or []),
        (f"{run_id}: lineage source_inputs", lineage.get("source_inputs") or []),
        (f"{run_id}: lineage artifact_paths", lineage.get("artifact_paths") or []),
    ]:
        ref_errors, _hash_only_count = hash_ref_errors(repo_root, owner, refs)
        errors.extend(ref_errors)

    batch_ref = manifest.get("execution_batch_ref") or {}
    receipt_batch_ref = receipt.get("execution_batch_ref") or {}
    if batch_ref != receipt_batch_ref:
        errors.append(f"{run_id}: execution_batch_ref differs between manifest and receipt")
    batch_path_value = str(batch_ref.get("path") or "")
    if batch_path_value:
        if not is_repo_relative(batch_path_value):
            errors.append(f"{run_id}: execution_batch_ref path is not repo-relative")
        elif not path_exists(repo_root / batch_path_value):
            errors.append(f"{run_id}: execution_batch_ref path missing {batch_path_value}")
        elif batch_ref.get("sha256") != sha256_file(repo_root / batch_path_value):
            errors.append(f"{run_id}: execution_batch_ref sha256 mismatch")

    return errors, result_judgment


def run_ids_from_refs(repo_root: Path, run_refs: str | None) -> list[str]:
    if not run_refs:
        return []
    path = repo_root / run_refs
    return [row["run_id"] for row in read_csv_rows(path) if row.get("run_id")]


def validate(
    repo_root: Path,
    *,
    run_ids: list[str],
    run_refs: str | None = None,
    campaign_id: str | None = None,
    summary: str | None = None,
    pre_runtime: bool = False,
) -> list[str]:
    repo_root = repo_root.resolve()
    selected_run_ids = list(dict.fromkeys([*run_ids, *run_ids_from_refs(repo_root, run_refs)]))
    if not selected_run_ids:
        return ["writer-scope smoke requires --run-id or --run-refs"]
    errors: list[str] = []
    summary_payload: dict[str, Any] | None = None
    summary_allows_bundle_id = False
    if summary:
        summary_path = repo_root / summary
        if path_exists(summary_path):
            summary_payload = load_yaml(summary_path)
            version = str(summary_payload.get("version") or "")
            summary_allows_bundle_id = bool(
                summary_payload.get("bundle_count") is not None
                or summary_payload.get("attempt_count") is not None
                or "onnx_materialization" in version
                or "attempt_preparation" in version
            )
    result_counts: Counter[str] = Counter()
    for run_id in selected_run_ids:
        run_errors, judgment = validate_run(
            repo_root,
            run_id,
            campaign_id=campaign_id,
            pre_runtime=pre_runtime,
            allow_bundle_id=summary_allows_bundle_id,
        )
        errors.extend(run_errors)
        if judgment:
            result_counts[judgment] += 1
    if summary:
        summary_path = repo_root / summary
        if not path_exists(summary_path):
            errors.append(f"summary path missing {summary}")
        else:
            payload = summary_payload or load_yaml(summary_path)
            if campaign_id and payload.get("campaign_id") != campaign_id:
                errors.append(f"{summary}: campaign_id mismatch")
            if "executed_proxy_run_count" in payload:
                if int(payload.get("executed_proxy_run_count") or -1) != len(selected_run_ids):
                    errors.append(f"{summary}: executed_proxy_run_count mismatch")
            elif "bundle_count" in payload:
                if int(payload.get("bundle_count") or -1) != len(selected_run_ids):
                    errors.append(f"{summary}: bundle_count mismatch")
            elif "l4_pair_count" in payload:
                if int(payload.get("l4_pair_count") or -1) != len(selected_run_ids):
                    errors.append(f"{summary}: l4_pair_count mismatch")
            if "result_counts" in payload:
                summary_counts = {str(key): int(value) for key, value in (payload.get("result_counts") or {}).items()}
                if dict(sorted(result_counts.items())) != dict(sorted(summary_counts.items())):
                    errors.append(f"{summary}: result_counts mismatch")
            boundary = str(payload.get("claim_boundary") or "")
            for key, boundary_token in [
                ("runtime_authority", "no_runtime_authority"),
                ("economics_pass", "no_economics_pass"),
                ("live_readiness", "no_live_readiness"),
            ]:
                if key in payload and str(payload.get(key) or "") != "not_claimed":
                    errors.append(f"{summary}: {key} must be not_claimed")
                elif key not in payload and boundary_token not in boundary:
                    errors.append(f"{summary}: claim_boundary missing {boundary_token}")
    if errors:
        return errors
    print(
        "writer-scope evidence smoke passed: "
        f"runs={len(selected_run_ids)} result_counts={dict(sorted(result_counts.items()))}"
    )
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--run-id", action="append", default=[])
    parser.add_argument("--run-refs")
    parser.add_argument("--campaign-id")
    parser.add_argument("--summary")
    parser.add_argument("--pre-runtime", action="store_true")
    args = parser.parse_args(argv)
    errors = validate(
        Path(args.repo_root),
        run_ids=list(args.run_id or []),
        run_refs=args.run_refs,
        campaign_id=args.campaign_id,
        summary=args.summary,
        pre_runtime=bool(args.pre_runtime),
    )
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
