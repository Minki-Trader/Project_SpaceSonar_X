from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import ExecutionContext
from .store import dump_yaml, read_yaml, sha256_file
from .transaction import ControlPlaneTransaction


AGENT_EVENTS_PATH = Path("docs/workspace/agent_operating_events.yaml")
AGENT_METRICS_PATH = Path("docs/workspace/agent_operating_metrics.yaml")
PROGRESS_LEDGER_PATH = Path("docs/migrations/control_plane_corrective_v3_progress.yaml")
CONSULT_RECEIPT_VERSION = "agent_consult_receipt_v2"
EVENT_VERSION = "agent_operating_events_v2"
METRICS_VERSION = "agent_operating_metrics_v3"
KNOWN_AGENT_MODES = {"solo", "micro_specialist", "micro_adversarial", "formal_protected_review", "full_roster", "unknown"}
KNOWN_EVIDENCE_CLASSES = {"contemporaneous_work_receipt", "retrospective_attestation", "unknown"}


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _source_ref(repo_root: Path, rel_path: Path | str) -> dict[str, Any]:
    rel = Path(str(rel_path).replace("\\", "/"))
    path = repo_root / rel
    return {
        "path": rel.as_posix(),
        "sha256": sha256_file(path) if path.exists() else None,
        "size_bytes": path.stat().st_size if path.exists() else None,
    }


def _timestamp_in_boundary(value: str | None, start: str | None, end: str | None) -> bool:
    if not value:
        return False
    if start and value < start:
        return False
    if end and value > end:
        return False
    return True


def _load_consult_receipt(repo_root: Path, rel_path: str) -> dict[str, Any]:
    data = read_yaml(repo_root / rel_path)
    if data.get("version") != CONSULT_RECEIPT_VERSION:
        raise ValueError(f"{rel_path}: expected {CONSULT_RECEIPT_VERSION}")
    return data


def derive_advice_metrics(receipt: dict[str, Any]) -> dict[str, int]:
    opinions = receipt.get("opinions") or []
    duplicate_count = 0
    seen_summaries: set[str] = set()
    accepted = rejected = rewritten = unsupported = 0
    for item in opinions:
        classification = str(item.get("classification") or "")
        if classification == "accepted":
            accepted += 1
        elif classification == "rejected":
            rejected += 1
        elif classification == "rewritten":
            rewritten += 1
        if classification in {"accepted", "rewritten"} and not item.get("evidence_refs"):
            unsupported += 1
        summary = str(item.get("summary") or "").strip()
        if summary:
            duplicate_count += int(summary in seen_summaries)
            seen_summaries.add(summary)
    return {
        "total_advice_items": len(opinions),
        "duplicate_advice_items": duplicate_count,
        "unsupported_assertion_count": unsupported,
        "accepted_after_verification_count": accepted,
        "rejected_after_verification_count": rejected,
        "rewritten_after_verification_count": rewritten,
    }


def consult_metric_errors(receipt: dict[str, Any], *, label: str) -> list[str]:
    declared = receipt.get("metrics") or {}
    derived = derive_advice_metrics(receipt)
    aliases = {"unsupported_assertion_count": "unsupported_assertions"}
    errors: list[str] = []
    for key, value in derived.items():
        declared_key = aliases.get(key, key)
        if declared_key in declared and int(declared.get(declared_key) or 0) != value:
            errors.append(f"{label}: metrics.{declared_key} does not match item-level opinions")
    return errors


def project_agent_events(repo_root: Path) -> dict[str, Any]:
    progress = read_yaml(repo_root / PROGRESS_LEDGER_PATH)
    start = str(progress.get("initialized_at_utc") or "")
    end = str(progress.get("completed_at_utc") or "")
    work_events: list[dict[str, Any]] = []
    consult_events: list[dict[str, Any]] = []
    work_units = progress.get("work_units") or {}
    for work_item_id in sorted(work_units):
        unit = work_units[work_item_id] or {}
        execution = unit.get("agent_execution") or {}
        if not execution:
            continue
        mode = str(execution.get("mode") or "unknown")
        evidence_class = str(execution.get("evidence_class") or "unknown")
        started = execution.get("started_at_utc") or unit.get("completed_at_utc")
        ended = execution.get("ended_at_utc") or unit.get("completed_at_utc")
        in_boundary = _timestamp_in_boundary(str(started) if started else None, start, end or None)
        observed = evidence_class == "contemporaneous_work_receipt" and mode != "unknown" and in_boundary
        work_events.append(
            {
                "work_item_id": work_item_id,
                "agent_mode": mode,
                "evidence_class": evidence_class,
                "consult_ids": list(execution.get("consult_ids") or []),
                "source_refs": execution.get("source_refs") or [_source_ref(repo_root, PROGRESS_LEDGER_PATH)],
                "started_at_utc": started,
                "ended_at_utc": ended,
                "in_boundary": in_boundary,
                "observed_for_slo": observed,
            }
        )
    for work in work_events:
        for consult_id in work.get("consult_ids") or []:
            found_path: str | None = None
            for path in sorted(repo_root.glob("lab/**/task_force_consultation*_v2.yaml")):
                data = read_yaml(path)
                if data.get("consult_id") == consult_id:
                    found_path = path.relative_to(repo_root).as_posix()
                    break
            if not found_path:
                consult_events.append({"consult_id": consult_id, "work_item_id": work["work_item_id"], "status": "missing"})
                continue
            receipt = _load_consult_receipt(repo_root, found_path)
            created = str(receipt.get("created_at_utc") or "")
            in_boundary = _timestamp_in_boundary(created, start, end or None)
            consult_events.append(
                {
                    "consult_id": consult_id,
                    "work_item_id": work["work_item_id"],
                    "path": found_path,
                    "sha256": sha256_file(repo_root / found_path),
                    "selected_agent_count": len(receipt.get("selected_agent_ids") or []),
                    "created_at_utc": created,
                    "in_boundary": in_boundary,
                    "boundary_class": "in_boundary" if in_boundary else "historical_out_of_boundary",
                    "advice_metrics": derive_advice_metrics(receipt),
                }
            )
    return {
        "version": EVENT_VERSION,
        "updated_utc": progress.get("initialized_at_utc"),
        "measurement_boundary": {
            "start_utc": start,
            "end_utc": end or None,
            "boundary_id": "control_plane_corrective_v3",
        },
        "source_refs": [_source_ref(repo_root, PROGRESS_LEDGER_PATH)],
        "work_item_events": work_events,
        "consult_events": consult_events,
        "projection": {
            "generated_from": PROGRESS_LEDGER_PATH.as_posix(),
            "generator": "python -m spacesonar.cli agents events --write",
            "manual_edit_policy": "manual edits fail projection check",
        },
    }


def validate_agent_events_projection(repo_root: Path, events: dict[str, Any] | None = None) -> list[str]:
    events = events or read_yaml(repo_root / AGENT_EVENTS_PATH)
    errors: list[str] = []
    if events.get("version") != EVENT_VERSION:
        errors.append(f"{AGENT_EVENTS_PATH.as_posix()}: version mismatch")
    seen_work: set[str] = set()
    seen_consults: set[str] = set()
    for item in events.get("work_item_events") or []:
        work_item_id = str(item.get("work_item_id") or "")
        if not work_item_id:
            errors.append("agent event missing work_item_id")
        if work_item_id in seen_work:
            errors.append(f"duplicate work_item_id {work_item_id}")
        seen_work.add(work_item_id)
        if item.get("agent_mode") not in KNOWN_AGENT_MODES:
            errors.append(f"{work_item_id}: unknown agent mode {item.get('agent_mode')}")
        if item.get("evidence_class") not in KNOWN_EVIDENCE_CLASSES:
            errors.append(f"{work_item_id}: unknown evidence_class {item.get('evidence_class')}")
        for ref in item.get("source_refs") or []:
            path = repo_root / str(ref.get("path") or "")
            if not path.exists():
                errors.append(f"{work_item_id}: missing source {ref.get('path')}")
            elif ref.get("sha256") and ref.get("sha256") != sha256_file(path):
                errors.append(f"{work_item_id}: source hash mismatch {ref.get('path')}")
    work_ids = seen_work
    for item in events.get("consult_events") or []:
        consult_id = str(item.get("consult_id") or "")
        if not consult_id:
            errors.append("consult event missing consult_id")
        if consult_id in seen_consults:
            errors.append(f"duplicate consult_id {consult_id}")
        seen_consults.add(consult_id)
        if item.get("work_item_id") not in work_ids:
            errors.append(f"{consult_id}: consultation not linked to a work item")
        path = item.get("path")
        if path:
            receipt_path = repo_root / str(path)
            if not receipt_path.exists():
                errors.append(f"{consult_id}: missing consult receipt {path}")
            elif item.get("sha256") != sha256_file(receipt_path):
                errors.append(f"{consult_id}: source hash mismatch {path}")
    return errors


def agent_operating_events_diff(repo_root: Path) -> list[str]:
    expected = project_agent_events(repo_root)
    path = repo_root / AGENT_EVENTS_PATH
    if not path.exists():
        return [f"{AGENT_EVENTS_PATH.as_posix()}: missing generated agent event projection"]
    observed = read_yaml(path)
    errors = validate_agent_events_projection(repo_root, observed)
    if errors:
        return errors
    return [] if observed == expected else [f"{AGENT_EVENTS_PATH.as_posix()}: generated projection drift"]


def project_agent_operating_metrics_from_events(repo_root: Path, events: dict[str, Any]) -> dict[str, Any]:
    work_items = events.get("work_item_events") or []
    in_boundary_work = [item for item in work_items if item.get("in_boundary")]
    observed_work = [item for item in in_boundary_work if item.get("observed_for_slo")]
    consult_events = [item for item in events.get("consult_events") or [] if item.get("in_boundary")]

    work_item_count = len({item.get("work_item_id") for item in in_boundary_work})
    observed_work_item_count = len({item.get("work_item_id") for item in observed_work})
    solo_work_item_count = sum(1 for item in observed_work if item.get("agent_mode") == "solo")
    routine_work_item_count = sum(1 for item in observed_work if item.get("agent_mode") in {"solo", "micro_specialist"})
    one_agent_consult_count = sum(1 for item in consult_events if int(item.get("selected_agent_count") or 0) == 1)
    two_agent_consult_count = sum(1 for item in consult_events if int(item.get("selected_agent_count") or 0) == 2)
    three_plus_agent_consult_count = sum(1 for item in consult_events if int(item.get("selected_agent_count") or 0) >= 3)

    totals = {
        "total_advice_items": 0,
        "duplicate_advice_items": 0,
        "unsupported_assertion_count": 0,
        "accepted_after_verification_count": 0,
        "rejected_after_verification_count": 0,
        "rewritten_after_verification_count": 0,
    }
    for item in consult_events:
        for key, value in (item.get("advice_metrics") or {}).items():
            totals[key] = totals.get(key, 0) + int(value or 0)
    metrics = {
        "work_item_count": work_item_count,
        "observed_work_item_count": observed_work_item_count,
        "solo_work_item_count": solo_work_item_count,
        "consult_count": len(consult_events),
        "one_agent_consult_count": one_agent_consult_count,
        "two_agent_consult_count": two_agent_consult_count,
        "three_plus_agent_consult_count": three_plus_agent_consult_count,
        **totals,
        "solo_work_share": _ratio(solo_work_item_count, observed_work_item_count),
        "one_agent_consult_share": _ratio(one_agent_consult_count, len(consult_events)),
        "two_agent_consult_share": _ratio(two_agent_consult_count, len(consult_events)),
        "three_plus_agent_consult_share": _ratio(three_plus_agent_consult_count, len(consult_events)),
        "routine_solo_or_single_agent_share": _ratio(routine_work_item_count, observed_work_item_count),
        "duplicate_advice_ratio": _ratio(totals["duplicate_advice_items"], totals["total_advice_items"]),
        "accepted_after_verification_ratio": _ratio(totals["accepted_after_verification_count"], totals["total_advice_items"]),
    }
    return {
        "version": METRICS_VERSION,
        "updated_utc": events.get("updated_utc"),
        "source_refs": [_source_ref(repo_root, AGENT_EVENTS_PATH)],
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


def project_agent_operating_metrics(repo_root: Path) -> dict[str, Any]:
    return project_agent_operating_metrics_from_events(repo_root, read_yaml(repo_root / AGENT_EVENTS_PATH))


def _commit_projection(repo_root: Path, path: Path, payload: dict[str, Any], *, command_argv: tuple[str, ...]) -> None:
    context = ExecutionContext(
        repo_root=repo_root,
        work_item_id="work_codex_control_plane_corrective_v3",
        claim_boundary="agent_operating_telemetry_projection_only_no_reviewed_pass",
        command_argv=command_argv,
    )
    tx = ControlPlaneTransaction(context)
    tx.stage_yaml(path, payload)
    result = tx.commit()
    if result.status not in {"committed", "noop_already_applied"}:
        raise RuntimeError(f"projection transaction failed: {result.status}: {list(result.errors)}")


def write_agent_operating_events(repo_root: Path, *, command_argv: tuple[str, ...] = ("python", "-m", "spacesonar.cli", "agents", "events", "--write")) -> dict[str, Any]:
    projected = project_agent_events(repo_root)
    errors = validate_agent_events_projection(repo_root, projected)
    if errors:
        raise ValueError("; ".join(errors))
    _commit_projection(repo_root, AGENT_EVENTS_PATH, projected, command_argv=command_argv)
    return projected


def write_agent_operating_metrics(repo_root: Path, *, command_argv: tuple[str, ...] = ("python", "-m", "spacesonar.cli", "agents", "metrics", "--write")) -> dict[str, Any]:
    projected = project_agent_operating_metrics(repo_root)
    _commit_projection(repo_root, AGENT_METRICS_PATH, projected, command_argv=command_argv)
    return projected


def agent_operating_metrics_diff(repo_root: Path) -> list[str]:
    event_diffs = agent_operating_events_diff(repo_root)
    if event_diffs:
        return event_diffs
    expected = project_agent_operating_metrics(repo_root)
    path = repo_root / AGENT_METRICS_PATH
    if not path.exists():
        return [f"{AGENT_METRICS_PATH.as_posix()}: missing generated agent metrics projection"]
    observed = read_yaml(path)
    return [] if observed == expected else [f"{AGENT_METRICS_PATH.as_posix()}: generated projection drift"]
