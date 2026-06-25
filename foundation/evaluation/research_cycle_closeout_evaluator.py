from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation.evaluation.common import evaluation_time_utc, finalize_result, implementation_hashes, input_hash, load_yaml, write_yaml
from spacesonar.control_plane.store import filesystem_path


EVALUATOR_ID = "research_cycle_closeout_evaluator_v1"
WAVE_ID = "wave_us100_closedbar_surface_cartography_v0"
WAVE_ALLOCATION_PATH = f"lab/waves/{WAVE_ID}/wave_allocation.yaml"
CAMPAIGN_REFS_PATH = f"lab/waves/{WAVE_ID}/campaign_refs.csv"
CANDIDATE_REGISTRY_PATH = "docs/registers/candidate_registry.csv"
CLUE_REGISTRY_PATH = "docs/registers/clue_registry.csv"
NEGATIVE_MEMORY_REGISTRY_PATH = "docs/registers/negative_memory_registry.csv"
NEGATIVE_MEMORY_ROOT = Path("lab/memory/negative")
CLUE_ROOT = Path("lab/memory/clues")
ACCEPTED_CLOSED_STATUSES = {
    "decision_replay_judgment_closed_no_candidate",
    "wave01_event_barrier_decision_replay_closed_no_candidate",
    "wave01_session_transition_closed_preserved_clues_no_candidate",
}
FORBIDDEN_CLAIMS = {
    "runtime_authority",
    "economics_pass",
    "live_readiness",
    "selected_baseline",
    "production_deployment",
}


def _read_csv(repo_root: Path, rel_path: str) -> list[dict[str, str]]:
    with open(filesystem_path(repo_root / rel_path), "r", newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _optional_hash(repo_root: Path, rel_path: str | None) -> dict[str, Any] | None:
    if not rel_path or not (repo_root / rel_path).is_file():
        return None
    return input_hash(repo_root, rel_path)


def _int_field(record: dict[str, Any], key: str, findings: list[dict[str, Any]], *, campaign_id: str) -> int | None:
    if key in record:
        value = record.get(key)
    else:
        counts = record.get("counts")
        if not isinstance(counts, dict) or key not in counts:
            findings.append({"id": "missing_campaign_count", "campaign_id": campaign_id, "field": key})
            return None
        value = counts.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        findings.append({"id": "invalid_campaign_count", "campaign_id": campaign_id, "field": key, "value": value})
        return None
    return value


def _evidence_path_for_allocation(allocation: dict[str, Any]) -> str:
    if allocation.get("campaign_closeout"):
        return str(allocation["campaign_closeout"])
    if allocation.get("decision_replay_judgment_summary"):
        return str(allocation["decision_replay_judgment_summary"])
    campaign_id = str(allocation.get("campaign_id") or "")
    return f"lab/campaigns/{campaign_id}/campaign_closeout.yaml"


def _memory_path(memory_id: str) -> str:
    return (NEGATIVE_MEMORY_ROOT / f"{memory_id}.yaml").as_posix()


def _clue_path(clue_id: str) -> str:
    return (CLUE_ROOT / f"{clue_id}.yaml").as_posix()


def _contains_locked_final_usage(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key).lower()
            if "locked_final_oos" in key_text and item in {True, "used", "consumed", "accessed"}:
                return True
            if _contains_locked_final_usage(item):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_locked_final_usage(item) for item in value)
    if isinstance(value, str):
        return _string_mentions_locked_final_usage(value)
    return False


def _string_mentions_locked_final_usage(value: str) -> bool:
    text = value.lower()
    if "locked_final_oos" not in text and "locked final oos" not in text:
        return False
    normalized = re.sub(r"[_\-]+", " ", text)
    if any(phrase in normalized for phrase in ("unused", "not used", "not consumed", "not accessed", "do not use")):
        return False
    tokens = set(re.findall(r"[a-z0-9]+", normalized))
    return bool(tokens & {"used", "consumed", "accessed"})


def _forbidden_claims_proven(record: dict[str, Any], *, legacy: bool) -> bool:
    if record.get("forbidden_claims_respected") is True:
        return True
    if legacy:
        forbidden = set(record.get("forbidden_claims") or [])
        claim_boundary = str(record.get("claim_boundary") or "")
        return bool(forbidden & FORBIDDEN_CLAIMS) and "no_runtime_authority" in claim_boundary and "no_economics_pass" in claim_boundary
    return False


def _append_evidence_hash(input_hashes: list[dict[str, Any]], repo_root: Path, rel_path: str) -> None:
    record = _optional_hash(repo_root, rel_path)
    if record and not any(item.get("path") == record["path"] for item in input_hashes):
        input_hashes.append(record)


def evaluate_research_cycle_closeout(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    findings: list[dict[str, Any]] = []
    input_hashes: list[dict[str, Any]] = [
        input_hash(repo_root, WAVE_ALLOCATION_PATH),
        input_hash(repo_root, CAMPAIGN_REFS_PATH),
        input_hash(repo_root, CANDIDATE_REGISTRY_PATH),
        input_hash(repo_root, CLUE_REGISTRY_PATH),
        input_hash(repo_root, NEGATIVE_MEMORY_REGISTRY_PATH),
    ]
    wave = load_yaml(repo_root / WAVE_ALLOCATION_PATH) or {}
    if wave.get("wave_id") != WAVE_ID:
        findings.append({"id": "wave_id_mismatch", "expected": WAVE_ID, "observed": wave.get("wave_id")})
    if wave.get("fixed_controls", {}).get("locked_final_oos") != "do_not_use":
        findings.append({"id": "locked_final_oos_policy_missing"})

    ref_rows = _read_csv(repo_root, CAMPAIGN_REFS_PATH)
    ref_ids = [str(row.get("campaign_id") or "") for row in ref_rows if row.get("campaign_id")]
    duplicate_ref_ids = sorted({campaign_id for campaign_id in ref_ids if ref_ids.count(campaign_id) > 1})
    for campaign_id in duplicate_ref_ids:
        findings.append({"id": "duplicate_campaign_ref", "campaign_id": campaign_id})
    refs_by_campaign = {row.get("campaign_id"): row for row in ref_rows if row.get("campaign_id")}
    candidate_rows = _read_csv(repo_root, CANDIDATE_REGISTRY_PATH)
    clue_rows = {row.get("clue_id"): row for row in _read_csv(repo_root, CLUE_REGISTRY_PATH)}
    memory_rows = {row.get("memory_id"): row for row in _read_csv(repo_root, NEGATIVE_MEMORY_REGISTRY_PATH)}

    allocations = wave.get("campaign_allocations") or []
    if not allocations:
        findings.append({"id": "missing_campaign_allocations"})
    allocation_ids = [str(item.get("campaign_id") or "") for item in allocations if item.get("campaign_id")]
    duplicate_allocation_ids = sorted({campaign_id for campaign_id in allocation_ids if allocation_ids.count(campaign_id) > 1})
    for campaign_id in duplicate_allocation_ids:
        findings.append({"id": "duplicate_campaign_allocation", "campaign_id": campaign_id})
    allocation_id_set = set(allocation_ids)
    for campaign_id in sorted(set(ref_ids) - allocation_id_set):
        findings.append({"id": "unexpected_campaign_ref", "campaign_id": campaign_id})
    for campaign_id in sorted(allocation_id_set - set(ref_ids)):
        findings.append({"id": "allocation_missing_campaign_ref", "campaign_id": campaign_id})

    campaign_results: list[dict[str, Any]] = []
    candidate_count = 0
    l5_candidate_count = 0
    referenced_memory_ids: set[str] = set()
    referenced_clue_ids: set[str] = set()
    locked_final_oos_used = _contains_locked_final_usage(wave)

    for allocation in allocations:
        campaign_id = str(allocation.get("campaign_id") or "")
        allocation_status = str(allocation.get("status") or "")
        ref = refs_by_campaign.get(campaign_id)
        if ref is None:
            findings.append({"id": "campaign_ref_missing", "campaign_id": campaign_id})
            ref = {}
        if ref.get("wave_id") and ref.get("wave_id") != WAVE_ID:
            findings.append({"id": "campaign_ref_wave_id_mismatch", "campaign_id": campaign_id, "observed": ref.get("wave_id")})
        if ref.get("status") and ref.get("status") != allocation_status:
            findings.append({"id": "campaign_ref_status_mismatch", "campaign_id": campaign_id, "allocation_status": allocation_status, "ref_status": ref.get("status")})
        campaign_path = str(allocation.get("campaign_manifest") or ref.get("campaign_path") or f"lab/campaigns/{campaign_id}/campaign_manifest.yaml")
        if ref.get("campaign_path") and ref.get("campaign_path") != campaign_path:
            findings.append({"id": "campaign_refs_path_mismatch", "campaign_id": campaign_id})
        if not (repo_root / campaign_path).is_file():
            findings.append({"id": "campaign_manifest_missing", "campaign_id": campaign_id, "path": campaign_path})
            manifest = {}
        else:
            input_hashes.append(input_hash(repo_root, campaign_path))
            manifest = load_yaml(repo_root / campaign_path) or {}
            if manifest.get("campaign_id") != campaign_id:
                findings.append({"id": "campaign_manifest_id_mismatch", "campaign_id": campaign_id, "observed": manifest.get("campaign_id")})
            if WAVE_ID not in (manifest.get("wave_ids") or []):
                findings.append({"id": "campaign_manifest_wave_missing", "campaign_id": campaign_id})
            if manifest.get("status") != allocation_status:
                findings.append({"id": "campaign_manifest_status_mismatch", "campaign_id": campaign_id, "manifest_status": manifest.get("status"), "allocation_status": allocation_status})
            if manifest.get("status") not in ACCEPTED_CLOSED_STATUSES:
                findings.append({"id": "campaign_manifest_not_closed", "campaign_id": campaign_id, "status": manifest.get("status")})

        evidence_rel = _evidence_path_for_allocation(allocation)
        evidence_path = repo_root / evidence_rel
        if not evidence_path.is_file():
            findings.append({"id": "missing_campaign_closeout_evidence", "campaign_id": campaign_id, "path": evidence_rel})
            campaign_results.append({"campaign_id": campaign_id, "status": allocation_status, "evidence_status": "missing"})
            continue
        input_hashes.append(input_hash(repo_root, evidence_rel))
        record = load_yaml(evidence_path) or {}
        legacy = record.get("version") == "decision_replay_judgment_summary_v1"
        if record.get("version") not in {"campaign_closeout_v1", "decision_replay_judgment_summary_v1"}:
            findings.append({"id": "unrecognized_campaign_evidence_version", "campaign_id": campaign_id, "version": record.get("version")})
        if record.get("campaign_id") != campaign_id:
            findings.append({"id": "campaign_evidence_id_mismatch", "campaign_id": campaign_id, "observed": record.get("campaign_id")})
        if not legacy and record.get("status") != allocation_status:
            findings.append({"id": "campaign_closeout_status_mismatch", "campaign_id": campaign_id, "evidence_status": record.get("status"), "allocation_status": allocation_status})
        if not _forbidden_claims_proven(record, legacy=legacy):
            findings.append({"id": "forbidden_claims_not_explicitly_proven", "campaign_id": campaign_id})
        locked_final_oos_used = locked_final_oos_used or _contains_locked_final_usage(record)

        record_candidate_count = _int_field(record, "candidate_count", findings, campaign_id=campaign_id)
        record_l5_count = _int_field(record, "l5_candidate_count", findings, campaign_id=campaign_id)
        record_candidate_ids = [str(item) for item in (record.get("candidate_ids") or [])]
        record_l5_candidate_ids = [str(item) for item in (record.get("l5_candidate_ids") or [])]
        if record_candidate_count:
            if not record_candidate_ids:
                findings.append({"id": "candidate_count_without_candidate_ids", "campaign_id": campaign_id, "count": record_candidate_count})
            elif len(record_candidate_ids) != record_candidate_count:
                findings.append({"id": "candidate_count_id_mismatch", "campaign_id": campaign_id, "count": record_candidate_count, "candidate_id_count": len(record_candidate_ids)})
        if record_l5_count:
            if not record_l5_candidate_ids:
                findings.append({"id": "l5_candidate_count_without_l5_candidate_ids", "campaign_id": campaign_id, "count": record_l5_count})
            elif len(record_l5_candidate_ids) != record_l5_count:
                findings.append({"id": "l5_candidate_count_id_mismatch", "campaign_id": campaign_id, "count": record_l5_count, "candidate_id_count": len(record_l5_candidate_ids)})
        if record_candidate_count is not None:
            candidate_count += record_candidate_count
            if record_candidate_count:
                findings.append({"id": "candidate_count_nonzero", "campaign_id": campaign_id, "count": record_candidate_count})
        if record_l5_count is not None:
            l5_candidate_count += record_l5_count
            if record_l5_count:
                findings.append({"id": "l5_candidate_count_nonzero", "campaign_id": campaign_id, "count": record_l5_count})

        for rel_path in record.get("evidence_paths") or []:
            if not (repo_root / str(rel_path)).exists():
                findings.append({"id": "campaign_evidence_path_missing", "campaign_id": campaign_id, "path": str(rel_path)})
            else:
                _append_evidence_hash(input_hashes, repo_root, str(rel_path))
        for memory_id in record.get("negative_memory_ids") or []:
            referenced_memory_ids.add(str(memory_id))
        memory = record.get("negative_memory") or {}
        if memory.get("memory_id"):
            referenced_memory_ids.add(str(memory["memory_id"]))
        for clue_id in record.get("preserved_clue_ids") or []:
            referenced_clue_ids.add(str(clue_id))

        campaign_results.append(
            {
                "campaign_id": campaign_id,
                "status": allocation_status,
                "manifest_path": campaign_path,
                "evidence_path": evidence_rel,
                "evidence_class": "legacy_decision_replay_judgment" if legacy else "campaign_closeout",
                "candidate_count": record_candidate_count,
                "l5_candidate_count": record_l5_count,
                "candidate_ids": record_candidate_ids,
                "l5_candidate_ids": record_l5_candidate_ids,
                "forbidden_claims_respected": _forbidden_claims_proven(record, legacy=legacy),
            }
        )

    candidate_ids_seen: list[str] = []
    scoped_candidate_rows: list[dict[str, str]] = []
    scoped_l5_rows: list[dict[str, str]] = []
    for row in candidate_rows:
        candidate_id = str(row.get("candidate_id") or "")
        if not candidate_id:
            continue
        candidate_ids_seen.append(candidate_id)
        row_wave_id = str(row.get("wave_id") or "")
        row_campaign_id = str(row.get("campaign_id") or "")
        if not row_wave_id or not row_campaign_id:
            findings.append({"id": "unscoped_candidate_row", "candidate_id": candidate_id})
            continue
        if row_wave_id != WAVE_ID:
            continue
        if row_campaign_id not in allocation_id_set:
            findings.append({"id": "candidate_row_unallocated_campaign", "candidate_id": candidate_id, "campaign_id": row_campaign_id})
            continue
        scoped_candidate_rows.append(row)
        status = str(row.get("status") or "").lower()
        if status.startswith("l5") or "l5" in status:
            scoped_l5_rows.append(row)
    duplicate_candidate_ids = sorted({candidate_id for candidate_id in candidate_ids_seen if candidate_ids_seen.count(candidate_id) > 1})
    for candidate_id in duplicate_candidate_ids:
        findings.append({"id": "duplicate_candidate_id", "candidate_id": candidate_id})
    candidate_registry_count = len(scoped_candidate_rows)
    if candidate_registry_count != candidate_count:
        findings.append({"id": "candidate_registry_count_mismatch", "registry_count": candidate_registry_count, "evidence_count": candidate_count})
    l5_registry_count = len(scoped_l5_rows)
    if l5_registry_count != l5_candidate_count:
        findings.append({"id": "l5_candidate_registry_count_mismatch", "registry_count": l5_registry_count, "evidence_count": l5_candidate_count})
    expected_candidate_ids = sorted(
        candidate_id
        for result in campaign_results
        for candidate_id in (result.get("candidate_ids") or [])
    )
    scoped_candidate_ids = sorted(row.get("candidate_id") for row in scoped_candidate_rows if row.get("candidate_id"))
    if expected_candidate_ids and expected_candidate_ids != scoped_candidate_ids:
        findings.append({"id": "candidate_id_set_mismatch", "expected": expected_candidate_ids, "registry": scoped_candidate_ids})
    expected_l5_candidate_ids = sorted(
        candidate_id
        for result in campaign_results
        for candidate_id in (result.get("l5_candidate_ids") or [])
    )
    scoped_l5_candidate_ids = sorted(row.get("candidate_id") for row in scoped_l5_rows if row.get("candidate_id"))
    if expected_l5_candidate_ids and expected_l5_candidate_ids != scoped_l5_candidate_ids:
        findings.append({"id": "l5_candidate_id_set_mismatch", "expected": expected_l5_candidate_ids, "registry": scoped_l5_candidate_ids})
    if locked_final_oos_used:
        findings.append({"id": "locked_final_oos_used"})

    for memory_id in sorted(referenced_memory_ids):
        row = memory_rows.get(memory_id)
        rel_path = _memory_path(memory_id)
        if row is None:
            findings.append({"id": "negative_memory_registry_missing", "memory_id": memory_id})
        elif row.get("evidence_path") and not (repo_root / str(row["evidence_path"])).exists():
            findings.append({"id": "negative_memory_evidence_missing", "memory_id": memory_id, "path": row.get("evidence_path")})
        if not (repo_root / rel_path).is_file():
            findings.append({"id": "missing_negative_memory_record", "memory_id": memory_id})
        else:
            _append_evidence_hash(input_hashes, repo_root, rel_path)
            payload = load_yaml(repo_root / rel_path) or {}
            observed_id = payload.get("memory_id") or payload.get("negative_memory_id")
            if observed_id != memory_id:
                findings.append({"id": "negative_memory_id_mismatch", "memory_id": memory_id, "observed": observed_id})

    for clue_id in sorted(referenced_clue_ids):
        row = clue_rows.get(clue_id)
        rel_path = _clue_path(clue_id)
        if row is None:
            findings.append({"id": "clue_registry_missing", "clue_id": clue_id})
        elif row.get("evidence_path") and not (repo_root / str(row["evidence_path"])).exists():
            findings.append({"id": "clue_evidence_missing", "clue_id": clue_id, "path": row.get("evidence_path")})
        if not (repo_root / rel_path).is_file():
            findings.append({"id": "missing_preserved_clue_record", "clue_id": clue_id})
        else:
            _append_evidence_hash(input_hashes, repo_root, rel_path)
            payload = load_yaml(repo_root / rel_path) or {}
            if payload.get("clue_id") != clue_id:
                findings.append({"id": "clue_id_mismatch", "clue_id": clue_id, "observed": payload.get("clue_id")})

    result = {
        "version": "evaluator_result_v1",
        "evaluator_id": EVALUATOR_ID,
        "executed_at_utc": evaluation_time_utc(),
        "input_hashes": sorted(input_hashes, key=lambda item: str(item.get("path") or "")),
        "implementation_hashes": implementation_hashes(
            repo_root,
            (
                "foundation/evaluation/research_cycle_closeout_evaluator.py",
            ),
        ),
        "status": "failed" if findings else "passed",
        "metrics": {
            "campaign_count": len(allocations),
            "candidate_count": candidate_count,
            "l5_candidate_count": l5_candidate_count,
            "candidate_registry_count": candidate_registry_count,
            "negative_memory_count": len(referenced_memory_ids),
            "preserved_clue_count": len(referenced_clue_ids),
            "locked_final_oos_used": locked_final_oos_used,
        },
        "campaign_results": sorted(campaign_results, key=lambda item: str(item.get("campaign_id") or "")),
        "findings": sorted(
            findings,
            key=lambda item: (
                str(item.get("id") or ""),
                str(item.get("campaign_id") or ""),
                str(item.get("memory_id") or ""),
                str(item.get("clue_id") or ""),
                str(item.get("path") or ""),
            ),
        ),
        "claim_effect": "research_cycle_closeout_evaluated_no_runtime_authority_no_economics_pass",
    }
    return finalize_result(result)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = evaluate_research_cycle_closeout(Path(args.repo_root).resolve())
    if args.output:
        write_yaml(Path(args.output), result)
    else:
        print(result)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
