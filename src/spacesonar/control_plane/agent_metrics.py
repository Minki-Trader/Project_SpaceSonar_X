from __future__ import annotations

from pathlib import Path
from typing import Any

from .store import dump_yaml, read_yaml, sha256_file


AGENT_EVENTS_PATH = Path("docs/workspace/agent_operating_events.yaml")
AGENT_METRICS_PATH = Path("docs/workspace/agent_operating_metrics.yaml")
CONSULT_RECEIPT_VERSION = "agent_consult_receipt_v2"


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _load_consult_receipt(repo_root: Path, rel_path: str) -> dict[str, Any]:
    data = read_yaml(repo_root / rel_path)
    if data.get("version") != CONSULT_RECEIPT_VERSION:
        raise ValueError(f"{rel_path}: expected {CONSULT_RECEIPT_VERSION}")
    return data


def project_agent_operating_metrics(repo_root: Path) -> dict[str, Any]:
    events = read_yaml(repo_root / AGENT_EVENTS_PATH)
    work_items = events.get("work_item_events") or []
    consult_refs = events.get("consult_receipts") or []
    consult_receipts = [_load_consult_receipt(repo_root, str(item["path"])) for item in consult_refs]

    work_item_count = len(work_items)
    solo_work_item_count = sum(1 for item in work_items if item.get("agent_mode") == "solo")
    consult_count = len(consult_receipts)
    selected_counts = [len(item.get("selected_agent_ids") or []) for item in consult_receipts]
    one_agent_consult_count = sum(1 for count in selected_counts if count == 1)
    two_agent_consult_count = sum(1 for count in selected_counts if count == 2)
    three_plus_agent_consult_count = sum(1 for count in selected_counts if count >= 3)

    total_advice_items = sum(int((item.get("metrics") or {}).get("total_advice_items", 0)) for item in consult_receipts)
    duplicate_advice_items = sum(int((item.get("metrics") or {}).get("duplicate_advice_items", 0)) for item in consult_receipts)
    unsupported_assertion_count = sum(int((item.get("metrics") or {}).get("unsupported_assertions", 0)) for item in consult_receipts)
    accepted_after_verification_count = sum(int((item.get("metrics") or {}).get("accepted_after_verification", 0)) for item in consult_receipts)
    rejected_after_verification_count = sum(int((item.get("metrics") or {}).get("rejected_after_verification", 0)) for item in consult_receipts)
    rewritten_after_verification_count = sum(int((item.get("metrics") or {}).get("rewritten_after_verification", 0)) for item in consult_receipts)
    operating_event_count = work_item_count + consult_count

    source_refs = [
        {
            "path": AGENT_EVENTS_PATH.as_posix(),
            "sha256": sha256_file(repo_root / AGENT_EVENTS_PATH),
        },
        *[
            {
                "path": str(item["path"]),
                "sha256": sha256_file(repo_root / str(item["path"])),
            }
            for item in consult_refs
        ],
    ]
    metrics = {
        "work_item_count": work_item_count,
        "solo_work_item_count": solo_work_item_count,
        "consult_count": consult_count,
        "one_agent_consult_count": one_agent_consult_count,
        "two_agent_consult_count": two_agent_consult_count,
        "three_plus_agent_consult_count": three_plus_agent_consult_count,
        "total_advice_items": total_advice_items,
        "duplicate_advice_items": duplicate_advice_items,
        "unsupported_assertion_count": unsupported_assertion_count,
        "accepted_after_verification_count": accepted_after_verification_count,
        "rejected_after_verification_count": rejected_after_verification_count,
        "rewritten_after_verification_count": rewritten_after_verification_count,
        "operating_event_count": operating_event_count,
        "solo_work_share": _ratio(solo_work_item_count, operating_event_count),
        "one_agent_share": _ratio(one_agent_consult_count, operating_event_count),
        "two_agent_share": _ratio(two_agent_consult_count, operating_event_count),
        "three_plus_agent_share": _ratio(three_plus_agent_consult_count, operating_event_count),
        "routine_solo_or_single_agent_share": _ratio(solo_work_item_count + one_agent_consult_count, operating_event_count),
        "duplicate_advice_ratio": _ratio(duplicate_advice_items, total_advice_items),
        "accepted_after_verification_ratio": _ratio(accepted_after_verification_count, total_advice_items),
    }
    return {
        "version": "agent_operating_metrics_v2",
        "updated_utc": events.get("updated_utc"),
        "source_refs": source_refs,
        "measurement_boundary": events.get("measurement_boundary"),
        "agent_operating_metrics": metrics,
        "compact_work_default": {
            "agent_mode": "solo",
            "allocation_block_required": False,
            "claim_effect": "local_codex_execution_only_no_reviewed_pass",
        },
        "projection": {
            "generated_from": AGENT_EVENTS_PATH.as_posix(),
            "generator": "python -m spacesonar.cli agents metrics --write",
            "manual_edit_policy": "manual edits fail projection check",
        },
    }


def write_agent_operating_metrics(repo_root: Path) -> dict[str, Any]:
    projected = project_agent_operating_metrics(repo_root)
    path = repo_root / AGENT_METRICS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_yaml(projected), encoding="utf-8")
    return projected


def agent_operating_metrics_diff(repo_root: Path) -> list[str]:
    expected = project_agent_operating_metrics(repo_root)
    path = repo_root / AGENT_METRICS_PATH
    if not path.exists():
        return [f"{AGENT_METRICS_PATH.as_posix()}: missing generated agent metrics projection"]
    observed = read_yaml(path)
    return [] if observed == expected else [f"{AGENT_METRICS_PATH.as_posix()}: generated projection drift"]
