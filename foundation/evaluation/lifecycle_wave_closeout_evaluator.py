from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from spacesonar.control_plane.store import dump_yaml, sha256_file


EVALUATOR_ID = "lifecycle_wave_closeout_evaluator_v1"


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig") as handle:
        loaded = yaml.safe_load(handle) or {}
    return loaded if isinstance(loaded, dict) else {}


def _result_sha(payload: dict[str, Any]) -> str:
    copy = dict(payload)
    copy.pop("output_sha256", None)
    return hashlib.sha256(dump_yaml(copy).encode("utf-8")).hexdigest()


def evaluate_wave_closeout(repo_root: Path, wave_id: str) -> dict[str, Any]:
    wave_path = Path("lab/waves") / wave_id / "wave_allocation.yaml"
    wave = _read_yaml(repo_root / wave_path)
    findings: list[dict[str, Any]] = []
    input_hashes: list[dict[str, Any]] = []
    if not wave:
        findings.append({"id": "missing_wave_allocation", "status": "failed", "path": wave_path.as_posix()})
    else:
        input_hashes.append({"path": wave_path.as_posix(), "sha256": sha256_file(repo_root / wave_path)})

    campaign_count = 0
    closed_campaign_count = 0
    candidate_count = 0
    l5_candidate_count = 0
    clue_ids: list[str] = []
    negative_memory_ids: list[str] = []
    for allocation in wave.get("campaign_allocations") or []:
        campaign_count += 1
        campaign_id = str(allocation.get("campaign_id") or "")
        manifest_rel = Path(str(allocation.get("campaign_manifest") or f"lab/campaigns/{campaign_id}/campaign_manifest.yaml"))
        closeout_rel = Path(str(allocation.get("campaign_closeout") or f"lab/campaigns/{campaign_id}/campaign_closeout.yaml"))
        manifest = _read_yaml(repo_root / manifest_rel)
        closeout = _read_yaml(repo_root / closeout_rel)
        for rel, record in [(manifest_rel, manifest), (closeout_rel, closeout)]:
            if record and (repo_root / rel).exists():
                input_hashes.append({"path": rel.as_posix(), "sha256": sha256_file(repo_root / rel)})
        if not manifest:
            findings.append({"id": "missing_campaign_manifest", "status": "failed", "campaign_id": campaign_id})
            continue
        if manifest.get("status") != "closed":
            findings.append({"id": "campaign_not_closed", "status": "failed", "campaign_id": campaign_id})
            continue
        if not closeout or closeout.get("campaign_id") != campaign_id or closeout.get("status") != "closed":
            findings.append({"id": "invalid_campaign_closeout", "status": "failed", "campaign_id": campaign_id})
            continue
        closed_campaign_count += 1
        candidate_count += int(closeout.get("candidate_count") or 0)
        l5_candidate_count += int(closeout.get("l5_candidate_count") or 0)
        clue_ids.extend(str(item) for item in closeout.get("clue_ids") or [])
        negative_memory_ids.extend(str(item) for item in closeout.get("negative_memory_ids") or [])

    status = "passed" if not findings and campaign_count > 0 and closed_campaign_count == campaign_count else "failed"
    result = {
        "version": "evaluator_result_v1",
        "evaluator_id": EVALUATOR_ID,
        "executed_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "wave_id": wave_id,
        "input_hashes": sorted(input_hashes, key=lambda item: item["path"]),
        "status": status,
        "findings": sorted(findings, key=lambda item: (item["id"], item.get("campaign_id", ""))),
        "campaign_count": campaign_count,
        "closed_campaign_count": closed_campaign_count,
        "candidate_count": candidate_count,
        "l5_candidate_count": l5_candidate_count,
        "clue_ids": sorted(set(clue_ids)),
        "negative_memory_ids": sorted(set(negative_memory_ids)),
        "claim_effect": "wave_lifecycle_closeout_only_no_runtime_authority_no_economics_pass",
    }
    result["output_sha256"] = _result_sha(result)
    return result
