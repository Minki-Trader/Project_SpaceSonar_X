from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation.evaluation.common import evaluation_time_utc, file_sha256, finalize_result, input_hash, load_yaml, write_yaml


EVALUATOR_ID = "research_cycle_closeout_evaluator_v1"
WAVE_ALLOCATION_PATH = "lab/waves/wave_us100_closedbar_surface_cartography_v0/wave_allocation.yaml"
CAMPAIGN_REFS_PATH = "lab/waves/wave_us100_closedbar_surface_cartography_v0/campaign_refs.csv"
NEGATIVE_MEMORY_ROOT = Path("lab/memory/negative")
CLUE_ROOT = Path("lab/memory/clues")


def _path_exists(repo_root: Path, rel_path: str | None) -> bool:
    return bool(rel_path) and (repo_root / str(rel_path)).is_file()


def _optional_input_hash(repo_root: Path, rel_path: str | None) -> dict[str, Any] | None:
    if not rel_path or not (repo_root / rel_path).is_file():
        return None
    return input_hash(repo_root, rel_path)


def _count_from_record(record: dict[str, Any], key: str) -> int:
    if key in record:
        return int(record.get(key) or 0)
    counts = record.get("counts") or {}
    return int(counts.get(key) or 0)


def _evidence_path_for_allocation(allocation: dict[str, Any]) -> str:
    for key in ("campaign_closeout", "decision_replay_judgment_summary"):
        value = allocation.get(key)
        if value:
            return str(value)
    campaign_id = str(allocation.get("campaign_id") or "")
    return f"lab/campaigns/{campaign_id}/campaign_closeout.yaml"


def evaluate_research_cycle_closeout(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    wave = load_yaml(repo_root / WAVE_ALLOCATION_PATH) or {}
    findings: list[dict[str, Any]] = []
    input_hashes: list[dict[str, Any]] = [input_hash(repo_root, WAVE_ALLOCATION_PATH)]
    campaign_refs_hash = _optional_input_hash(repo_root, CAMPAIGN_REFS_PATH)
    if campaign_refs_hash:
        input_hashes.append(campaign_refs_hash)

    campaign_results: list[dict[str, Any]] = []
    candidate_count = 0
    l5_candidate_count = 0
    negative_memory_ids: set[str] = set()
    clue_ids: set[str] = set()
    allocations = wave.get("campaign_allocations") or []
    if not allocations:
        findings.append({"id": "missing_campaign_allocations"})

    for allocation in allocations:
        campaign_id = str(allocation.get("campaign_id") or "")
        status = str(allocation.get("status") or "")
        evidence_rel = _evidence_path_for_allocation(allocation)
        if not _path_exists(repo_root, evidence_rel):
            findings.append({"id": "missing_campaign_closeout_evidence", "campaign_id": campaign_id, "path": evidence_rel})
            campaign_results.append({"campaign_id": campaign_id, "status": status, "evidence_status": "missing"})
            continue
        input_hashes.append(input_hash(repo_root, evidence_rel))
        record = load_yaml(repo_root / evidence_rel) or {}
        record_candidate_count = _count_from_record(record, "candidate_count")
        record_l5_count = _count_from_record(record, "l5_candidate_count")
        candidate_count += record_candidate_count
        l5_candidate_count += record_l5_count
        if record_candidate_count:
            findings.append({"id": "candidate_count_nonzero", "campaign_id": campaign_id, "count": record_candidate_count})
        if record_l5_count:
            findings.append({"id": "l5_candidate_count_nonzero", "campaign_id": campaign_id, "count": record_l5_count})
        if "closed" not in status and "judgment" not in status:
            findings.append({"id": "campaign_not_research_closed", "campaign_id": campaign_id, "status": status})

        if record.get("forbidden_claims_respected") is False:
            findings.append({"id": "forbidden_claims_not_respected", "campaign_id": campaign_id})

        for memory_id in record.get("negative_memory_ids") or []:
            negative_memory_ids.add(str(memory_id))
        memory = record.get("negative_memory") or {}
        if memory.get("memory_id"):
            negative_memory_ids.add(str(memory["memory_id"]))
        for clue_id in record.get("preserved_clue_ids") or []:
            clue_ids.add(str(clue_id))

        campaign_results.append(
            {
                "campaign_id": campaign_id,
                "status": status,
                "evidence_path": evidence_rel,
                "candidate_count": record_candidate_count,
                "l5_candidate_count": record_l5_count,
            }
        )

    for memory_id in sorted(negative_memory_ids):
        matches = sorted((repo_root / NEGATIVE_MEMORY_ROOT).glob(f"{memory_id}.yaml"))
        if not matches:
            findings.append({"id": "missing_negative_memory_record", "memory_id": memory_id})
        else:
            input_hashes.append(input_hash(repo_root, matches[0].relative_to(repo_root).as_posix()))
    for clue_id in sorted(clue_ids):
        matches = sorted((repo_root / CLUE_ROOT).glob(f"{clue_id}.yaml"))
        if not matches:
            findings.append({"id": "missing_preserved_clue_record", "clue_id": clue_id})
        else:
            input_hashes.append(input_hash(repo_root, matches[0].relative_to(repo_root).as_posix()))

    if wave.get("fixed_controls", {}).get("locked_final_oos") not in {"do_not_use", "locked_final_oos_b"}:
        findings.append({"id": "locked_final_oos_policy_missing"})
    if candidate_count or l5_candidate_count:
        findings.append({"id": "research_cycle_candidate_counts_nonzero", "candidate_count": candidate_count, "l5_candidate_count": l5_candidate_count})

    result = {
        "version": "evaluator_result_v1",
        "evaluator_id": EVALUATOR_ID,
        "executed_at_utc": evaluation_time_utc(),
        "input_hashes": sorted(input_hashes, key=lambda item: str(item.get("path") or "")),
        "status": "failed" if findings else "passed",
        "metrics": {
            "campaign_count": len(allocations),
            "candidate_count": candidate_count,
            "l5_candidate_count": l5_candidate_count,
            "negative_memory_count": len(negative_memory_ids),
            "preserved_clue_count": len(clue_ids),
            "locked_final_oos_used": False,
        },
        "campaign_results": sorted(campaign_results, key=lambda item: str(item.get("campaign_id") or "")),
        "findings": sorted(findings, key=lambda item: (str(item.get("id") or ""), str(item.get("campaign_id") or ""), str(item.get("memory_id") or ""), str(item.get("clue_id") or ""))),
        "claim_effect": "research_cycle_closeout_evaluated_no_candidate_no_runtime_authority_no_economics_pass",
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
