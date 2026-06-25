from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]

WAVE_ID = "wave_us100_closedbar_surface_cartography_v0"
CAMPAIGN_ID = "campaign_us100_task_surface_scout_v0"
WAVE_CAMPAIGN_REFS = "lab/waves/wave_us100_closedbar_surface_cartography_v0/campaign_refs.csv"
WAVE0_RUN_REFS = (
    "lab/campaigns/campaign_us100_task_surface_scout_v0/"
    "sweeps/sweep_wave0_broad_surface_scout_v0/run_refs.csv"
)
VERTICAL_SLICE_CAMPAIGN_ID = "campaign_minimal_onnx_mt5_vertical_slice_v0"


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a YAML mapping")
    return payload


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8", newline="\n")


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader), list(reader.fieldnames or [])


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_front_fields(fieldnames: list[str], front_fields: list[str]) -> list[str]:
    out = [field for field in front_fields if field not in fieldnames]
    for field in fieldnames:
        if field not in out:
            out.append(field)
    for field in reversed(front_fields):
        if field in out:
            out.remove(field)
            out.insert(0, field)
    return out


def ordered_id_chain(id_chain: dict[str, Any], *, wave_id: str | None, campaign_id: str | None) -> dict[str, Any]:
    ordered: dict[str, Any] = {"wave_id": wave_id, "campaign_id": campaign_id}
    for key, value in id_chain.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def sync_run_id_chains() -> None:
    run_refs, _ = read_csv(REPO_ROOT / WAVE0_RUN_REFS)
    wave0_run_ids = {row["run_id"] for row in run_refs}
    for run_dir in sorted((REPO_ROOT / "lab" / "runs").iterdir()):
        if not run_dir.is_dir():
            continue
        run_id = run_dir.name
        if run_id in wave0_run_ids:
            wave_id: str | None = WAVE_ID
            campaign_id: str | None = CAMPAIGN_ID
        elif "minimal_onnx_mt5_plumbing" in run_id:
            wave_id = None
            campaign_id = VERTICAL_SLICE_CAMPAIGN_ID
        else:
            wave_id = None
            campaign_id = None
        manifest_path = run_dir / "run_manifest.json"
        if manifest_path.exists():
            manifest = read_json(manifest_path)
            manifest["id_chain"] = ordered_id_chain(manifest.get("id_chain") or {}, wave_id=wave_id, campaign_id=campaign_id)
            write_json(manifest_path, manifest)
        receipt_path = run_dir / "experiment_receipt.yaml"
        if receipt_path.exists():
            receipt = read_yaml(receipt_path)
            receipt["id_chain"] = ordered_id_chain(receipt.get("id_chain") or {}, wave_id=wave_id, campaign_id=campaign_id)
            write_yaml(receipt_path, receipt)


def sync_run_registry() -> None:
    path = REPO_ROOT / "docs" / "registers" / "run_registry.csv"
    rows, fields = read_csv(path)
    fields = ensure_front_fields(fields, ["run_id", "wave_id", "campaign_id"])
    for row in rows:
        run_id = row.get("run_id", "")
        manifest_path = row.get("manifest_path", "")
        if manifest_path and (REPO_ROOT / manifest_path).exists():
            id_chain = read_json(REPO_ROOT / manifest_path).get("id_chain") or {}
            row["wave_id"] = "" if id_chain.get("wave_id") is None else str(id_chain.get("wave_id"))
            row["campaign_id"] = "" if id_chain.get("campaign_id") is None else str(id_chain.get("campaign_id"))
        elif run_id.startswith("onnxlab_wave0_cell_"):
            row["wave_id"] = WAVE_ID
            row["campaign_id"] = CAMPAIGN_ID
        elif "minimal_onnx_mt5_plumbing" in run_id:
            row["wave_id"] = ""
            row["campaign_id"] = VERTICAL_SLICE_CAMPAIGN_ID
        else:
            row["wave_id"] = ""
            row["campaign_id"] = ""
    write_csv(path, rows, fields)


def sync_run_lineage_hashes() -> None:
    for lineage_path in sorted((REPO_ROOT / "lab" / "runs").glob("*/artifact_lineage.json")):
        lineage = read_json(lineage_path)
        artifact_hashes: list[str] = []
        artifact_sizes: list[int] = []
        for item in lineage.get("artifact_paths", []):
            if not isinstance(item, dict) or not item.get("path"):
                continue
            full = REPO_ROOT / str(item["path"])
            if full.exists():
                item["sha256"] = sha256(full)
                item["size_bytes"] = full.stat().st_size
            if item.get("sha256"):
                artifact_hashes.append(str(item["sha256"]))
            if item.get("size_bytes") is not None:
                artifact_sizes.append(int(item["size_bytes"]))
        if artifact_hashes:
            lineage["artifact_hashes"] = artifact_hashes
        if artifact_sizes:
            lineage["artifact_sizes"] = artifact_sizes
        write_json(lineage_path, lineage)


def sync_campaign_and_goal_refs(timestamp: str) -> None:
    campaign_path = REPO_ROOT / "lab" / "campaigns" / CAMPAIGN_ID / "campaign_manifest.yaml"
    campaign = read_yaml(campaign_path)
    storage = campaign.setdefault("storage_contract", {})
    refs = storage.setdefault("wave_campaign_refs", [])
    if WAVE_CAMPAIGN_REFS not in refs:
        refs.append(WAVE_CAMPAIGN_REFS)
    storage["wave_link_policy"] = "central_campaign_folder_referenced_by_wave_allocation"
    write_yaml(campaign_path, campaign)

    workspace_path = REPO_ROOT / "docs" / "workspace" / "workspace_state.yaml"
    workspace = read_yaml(workspace_path)
    workspace["updated_utc"] = timestamp
    claims = workspace.setdefault("current_claims", {})
    claims["wave_campaign_storage_policy"] = "wave_allocates_central_campaigns_by_reference"
    claims["active_wave_campaign_refs"] = WAVE_CAMPAIGN_REFS
    write_yaml(workspace_path, workspace)

    next_work_path = REPO_ROOT / "lab" / "goals" / "goal_us100_onnx_forward_boundary_v0" / "next_work_item.yaml"
    if next_work_path.exists():
        next_work = read_yaml(next_work_path)
        current_truth = next_work.setdefault("current_truth", {})
        current_truth["wave_campaign_refs"] = WAVE_CAMPAIGN_REFS
        write_yaml(next_work_path, next_work)

    resume_path = REPO_ROOT / "lab" / "goals" / "goal_us100_onnx_forward_boundary_v0" / "resume_cursor.yaml"
    if resume_path.exists():
        resume = read_yaml(resume_path)
        sources = resume.setdefault("current_truth_sources", [])
        if WAVE_CAMPAIGN_REFS not in sources:
            sources.append(WAVE_CAMPAIGN_REFS)
        resume["updated_at_utc"] = timestamp
        write_yaml(resume_path, resume)


def sync_artifact_registry() -> None:
    path = REPO_ROOT / "docs" / "registers" / "artifact_registry.csv"
    rows, fields = read_csv(path)
    by_id = {row.get("artifact_id", ""): row for row in rows}
    if "artifact_wave0_campaign_refs_v0" not in by_id:
        rows.append(
            {
                "artifact_id": "artifact_wave0_campaign_refs_v0",
                "run_id": "",
                "bundle_id": "",
                "attempt_id": "",
                "artifact_type": "wave_campaign_refs",
                "path_or_uri": WAVE_CAMPAIGN_REFS,
                "sha256": "",
                "size_bytes": "",
                "availability": "present_hash_recorded",
                "producer_command": "foundation/pipelines/sync_wave_campaign_integration_contract.py",
                "regeneration_command": "python foundation/pipelines/sync_wave_campaign_integration_contract.py",
                "source_of_truth": WAVE_CAMPAIGN_REFS,
                "consumer": "wave_us100_closedbar_surface_cartography_v0",
                "claim_boundary": "wave_campaign_reference_index_only_no_candidate_no_runtime",
                "notes": "central campaign source-of-truth linked by wave refs",
            }
        )
    for row in rows:
        rel_path = row.get("path_or_uri", "")
        if not rel_path or "://" in rel_path:
            continue
        full = REPO_ROOT / rel_path
        if full.exists() and row.get("sha256") is not None:
            row["sha256"] = sha256(full)
            row["size_bytes"] = str(full.stat().st_size)
    write_csv(path, rows, fields)


def main() -> int:
    print(
        "historical lifecycle sync entrypoint disabled by WP04; use canonical projections and python -m spacesonar.cli project validate",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
