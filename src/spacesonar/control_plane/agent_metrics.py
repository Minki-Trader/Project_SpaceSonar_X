from __future__ import annotations

import copy
import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import ExecutionContext
from .store import dump_yaml, filesystem_path, read_yaml, sha256_file
from .transaction import ControlPlaneTransaction


AGENT_EVENTS_PATH = Path("docs/workspace/agent_operating_events.yaml")
AGENT_METRICS_PATH = Path("docs/workspace/agent_operating_metrics.yaml")
AGENT_WINDOWS_PATH = Path("docs/workspace/agent_observation_windows.yaml")
AGENT_HISTORY_DIR = Path("docs/workspace/agent_operating_history")
AGENT_WORK_RECEIPTS_DIR = Path("docs/workspace/agent_work_receipts")
PROGRESS_LEDGER_PATH = Path("docs/migrations/control_plane_corrective_v3_progress.yaml")
WORK_FAMILY_REGISTRY_PATH = Path("docs/agent_control/work_family_registry.yaml")
CONSULT_RECEIPT_VERSION = "agent_consult_receipt_v2"
EVENT_VERSION = "agent_operating_events_v2"
METRICS_VERSION = "agent_operating_metrics_v3"
WINDOW_VERSION = "agent_observation_windows_v1"
START_RECEIPT_VERSION = "agent_work_start_receipt_v1"
FINAL_RECEIPT_VERSION = "agent_work_finalization_receipt_v1"
LEGACY_WORK_RECEIPT_VERSION = "agent_work_receipt_v1"
KNOWN_AGENT_MODES = {"solo", "micro_specialist", "micro_adversarial", "formal_protected_review", "full_roster", "unknown"}
KNOWN_EVIDENCE_CLASSES = {"contemporaneous_work_receipt", "retrospective_attestation", "unknown"}
VALID_RESULT_STATUSES = {"passed", "failed", "aborted"}


def utc_now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _exists(path: Path) -> bool:
    return os.path.exists(filesystem_path(path))


def _size(path: Path) -> int:
    return os.stat(filesystem_path(path)).st_size


def _source_ref(repo_root: Path, rel_path: Path | str) -> dict[str, Any]:
    rel = Path(str(rel_path).replace("\\", "/"))
    path = repo_root / rel
    return {
        "path": rel.as_posix(),
        "sha256": sha256_file(path) if _exists(path) else None,
        "size_bytes": _size(path) if _exists(path) else None,
    }


def _timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _timestamp_in_boundary(value: str | None, start: str | None, end: str | None) -> bool:
    observed = _timestamp(value)
    if observed is None:
        return False
    start_ts = _timestamp(start)
    end_ts = _timestamp(end)
    if start_ts and observed < start_ts:
        return False
    if end_ts and observed > end_ts:
        return False
    return True


def _known_work_families(repo_root: Path) -> set[str] | None:
    path = repo_root / WORK_FAMILY_REGISTRY_PATH
    if not _exists(path):
        return None
    registry = read_yaml(path)
    return set((registry.get("work_families") or {}).keys())


def _canonical_self_hash(payload: dict[str, Any]) -> str:
    clone = copy.deepcopy(payload)
    clone["receipt_sha256"] = {"algorithm": "sha256", "value": ""}
    return hashlib.sha256(dump_yaml(clone).encode("utf-8")).hexdigest()


def with_receipt_self_hash(payload: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(payload)
    result["receipt_sha256"] = {"algorithm": "sha256", "value": ""}
    result["receipt_sha256"]["value"] = _canonical_self_hash(result)
    return result


def _self_hash_errors(payload: dict[str, Any], label: str) -> list[str]:
    stored = ((payload.get("receipt_sha256") or {}).get("value"))
    if not stored:
        return [f"{label}: self-hash missing"]
    expected = _canonical_self_hash(payload)
    if stored != expected:
        return [f"{label}: self-hash mismatch"]
    return []


def _work_receipt_path(work_item_id: str) -> Path:
    return AGENT_WORK_RECEIPTS_DIR / f"{work_item_id}.yaml"


def v2_start_receipt_path(work_item_id: str) -> Path:
    return AGENT_WORK_RECEIPTS_DIR / work_item_id / "start_receipt.yaml"


def v2_finalization_receipt_path(work_item_id: str) -> Path:
    return AGENT_WORK_RECEIPTS_DIR / work_item_id / "finalization_receipt.yaml"


def _load_work_receipt(repo_root: Path, work_item_id: str) -> dict[str, Any] | None:
    path = repo_root / _work_receipt_path(work_item_id)
    if not _exists(path):
        return None
    receipt = read_yaml(path)
    if receipt.get("work_item_id") != work_item_id:
        raise ValueError(f"{_work_receipt_path(work_item_id).as_posix()}: work_item_id mismatch")
    return receipt


def _load_consult_receipt(repo_root: Path, rel_path: str) -> dict[str, Any]:
    data = read_yaml(repo_root / rel_path)
    if data.get("version") != CONSULT_RECEIPT_VERSION:
        raise ValueError(f"{rel_path}: expected {CONSULT_RECEIPT_VERSION}")
    return data


def _load_windows(repo_root: Path) -> dict[str, Any] | None:
    path = repo_root / AGENT_WINDOWS_PATH
    if not _exists(path):
        return None
    data = read_yaml(path)
    if data.get("version") != WINDOW_VERSION:
        raise ValueError(f"{AGENT_WINDOWS_PATH.as_posix()}: expected {WINDOW_VERSION}")
    if not isinstance(data.get("windows"), dict):
        raise ValueError(f"{AGENT_WINDOWS_PATH.as_posix()}: windows must be a mapping")
    return data


def _prospective_windows(windows: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(window_id): window
        for window_id, window in (windows.get("windows") or {}).items()
        if (window or {}).get("role") == "prospective_proof"
    }


def _selected_observation_window(windows: dict[str, Any] | None) -> tuple[str | None, dict[str, Any] | None]:
    if not windows:
        return None, None
    active_id = windows.get("active_window_id")
    all_windows = windows.get("windows") or {}
    if active_id:
        return str(active_id), all_windows.get(active_id)
    prospective = _prospective_windows(windows)
    closed = [
        (window.get("end_utc") or window.get("start_utc") or "", window_id, window)
        for window_id, window in prospective.items()
        if window.get("status") == "closed"
    ]
    if not closed:
        return None, None
    _, window_id, window = sorted(closed)[-1]
    return window_id, window


def _window_history_payload(repo_root: Path, windows: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not windows:
        return []
    history = []
    for window_id, window in sorted((windows.get("windows") or {}).items()):
        if (window or {}).get("role") != "historical_preserved":
            continue
        history.append(
            {
                "window_id": window_id,
                "status": window.get("status"),
                "work_item_count": window.get("work_item_count"),
                "observed_work_item_count": window.get("observed_work_item_count"),
                "observation_coverage_ratio": window.get("observation_coverage_ratio"),
                "event_snapshot_ref": _source_ref(repo_root, window.get("event_snapshot_path", "")),
                "metric_snapshot_ref": _source_ref(repo_root, window.get("metric_snapshot_path", "")),
                "claim_effect": window.get("claim_effect"),
            }
        )
    return history


def _validate_ref(repo_root: Path, ref: dict[str, Any], label: str) -> list[str]:
    errors: list[str] = []
    rel_path = str(ref.get("path") or "")
    if not rel_path:
        return [f"{label}: ref path missing"]
    path = repo_root / rel_path
    if not _exists(path):
        return [f"{label}: ref missing {rel_path}"]
    if ref.get("sha256") != sha256_file(path):
        errors.append(f"{label}: ref hash mismatch {rel_path}; {label} hash mismatch {rel_path}")
    if int(ref.get("size_bytes") or -1) != _size(path):
        errors.append(f"{label}: ref size mismatch {rel_path}")
    return errors


def validate_agent_start_receipt(repo_root: Path, rel_path: Path) -> list[str]:
    path = repo_root / rel_path
    if not _exists(path):
        return [f"{rel_path.as_posix()}: missing start receipt"]
    receipt = read_yaml(path)
    label = rel_path.as_posix()
    errors: list[str] = []
    required = [
        "version",
        "receipt_status",
        "work_item_id",
        "observation_window_id",
        "primary_family",
        "agent_mode",
        "consult_ids",
        "started_at_utc",
        "branch",
        "start_commit_sha",
        "claim_boundary",
        "planned_commands",
        "input_refs",
        "receipt_sha256",
    ]
    for field in required:
        if receipt.get(field) in (None, "", {}):
            errors.append(f"{label}: missing {field}")
    if receipt.get("version") != START_RECEIPT_VERSION:
        errors.append(f"{label}: version mismatch")
    if receipt.get("receipt_status") != "started":
        errors.append(f"{label}: receipt_status must be started")
    if receipt.get("agent_mode") not in KNOWN_AGENT_MODES - {"unknown"}:
        errors.append(f"{label}: unknown agent mode {receipt.get('agent_mode')}")
    families = _known_work_families(repo_root)
    if families is not None and receipt.get("primary_family") not in families:
        errors.append(f"{label}: unknown primary_family {receipt.get('primary_family')}")
    if _timestamp(str(receipt.get("started_at_utc") or "")) is None:
        errors.append(f"{label}: invalid started_at_utc")
    windows = _load_windows(repo_root)
    window_id = str(receipt.get("observation_window_id") or "")
    if windows and window_id not in (windows.get("windows") or {}):
        errors.append(f"{label}: unknown observation_window_id {window_id}")
    elif windows:
        window = (windows.get("windows") or {}).get(window_id) or {}
        if not _timestamp_in_boundary(str(receipt.get("started_at_utc") or ""), window.get("start_utc"), window.get("end_utc")):
            errors.append(f"{label}: started_at_utc outside observation window")
    for ref in receipt.get("input_refs") or []:
        errors.extend(_validate_ref(repo_root, ref, f"{label}: input_refs"))
    errors.extend(_self_hash_errors(receipt, label))
    return errors


def validate_agent_finalization_receipt(repo_root: Path, rel_path: Path) -> list[str]:
    path = repo_root / rel_path
    if not _exists(path):
        return [f"{rel_path.as_posix()}: missing finalization receipt"]
    receipt = read_yaml(path)
    label = rel_path.as_posix()
    errors: list[str] = []
    required = [
        "version",
        "receipt_status",
        "work_item_id",
        "observation_window_id",
        "primary_family",
        "agent_mode",
        "consult_ids",
        "evidence_class",
        "start_receipt_ref",
        "ended_at_utc",
        "end_commit_sha",
        "result_status",
        "command_results",
        "evidence_refs",
        "validation_results",
        "claim_boundary",
        "receipt_sha256",
    ]
    for field in required:
        if receipt.get(field) in (None, "", {}):
            errors.append(f"{label}: missing {field}")
    if receipt.get("version") != FINAL_RECEIPT_VERSION:
        errors.append(f"{label}: version mismatch")
    if receipt.get("receipt_status") != "finalized":
        errors.append(f"{label}: receipt_status must be finalized")
    if receipt.get("evidence_class") != "contemporaneous_work_receipt":
        errors.append(f"{label}: evidence_class must be contemporaneous_work_receipt")
    if receipt.get("result_status") not in VALID_RESULT_STATUSES:
        errors.append(f"{label}: result_status must be passed, failed, or aborted")
    if receipt.get("agent_mode") not in KNOWN_AGENT_MODES - {"unknown"}:
        errors.append(f"{label}: unknown agent mode {receipt.get('agent_mode')}")
    families = _known_work_families(repo_root)
    if families is not None and receipt.get("primary_family") not in families:
        errors.append(f"{label}: unknown primary_family {receipt.get('primary_family')}")
    start_ref = receipt.get("start_receipt_ref") or {}
    errors.extend(_validate_ref(repo_root, start_ref, f"{label}: start_receipt_ref"))
    start_rel = Path(str(start_ref.get("path") or v2_start_receipt_path(str(receipt.get("work_item_id") or "")).as_posix()))
    start_path = repo_root / start_rel
    if _exists(start_path):
        start = read_yaml(start_path)
        if start.get("version") != START_RECEIPT_VERSION:
            errors.append(f"{label}: start receipt version mismatch")
        for key in ["work_item_id", "observation_window_id", "primary_family", "agent_mode", "claim_boundary"]:
            if start.get(key) != receipt.get(key):
                errors.append(f"{label}: start/final {key} mismatch")
        start_time = _timestamp(str(start.get("started_at_utc") or ""))
        end_time = _timestamp(str(receipt.get("ended_at_utc") or ""))
        if start_time is None or end_time is None or end_time <= start_time:
            errors.append(f"{label}: ended_at_utc must be later than started_at_utc")
    else:
        errors.append(f"{label}: start receipt missing")
    windows = _load_windows(repo_root)
    window_id = str(receipt.get("observation_window_id") or "")
    if windows and window_id not in (windows.get("windows") or {}):
        errors.append(f"{label}: unknown observation_window_id {window_id}")
    elif windows:
        window = (windows.get("windows") or {}).get(window_id) or {}
        if not _timestamp_in_boundary(str(receipt.get("ended_at_utc") or ""), window.get("start_utc"), window.get("end_utc")):
            errors.append(f"{label}: ended_at_utc outside observation window")
    for ref in receipt.get("evidence_refs") or []:
        errors.extend(_validate_ref(repo_root, ref, f"{label}: evidence_refs"))
    for result in receipt.get("command_results") or []:
        ref = result.get("result_ref")
        if ref:
            errors.extend(_validate_ref(repo_root, ref, f"{label}: command_results"))
    for result in receipt.get("validation_results") or []:
        ref = result.get("result_ref")
        if ref:
            errors.extend(_validate_ref(repo_root, ref, f"{label}: validation_results"))
    errors.extend(_self_hash_errors(receipt, label))
    return errors


def validate_agent_observation_windows(repo_root: Path, *, require_closed: bool = False) -> list[str]:
    path = repo_root / AGENT_WINDOWS_PATH
    if not _exists(path):
        return [f"{AGENT_WINDOWS_PATH.as_posix()}: missing observation window registry"]
    data = read_yaml(path)
    errors: list[str] = []
    if data.get("version") != WINDOW_VERSION:
        errors.append(f"{AGENT_WINDOWS_PATH.as_posix()}: version mismatch")
    windows = data.get("windows") or {}
    if not isinstance(windows, dict):
        return [f"{AGENT_WINDOWS_PATH.as_posix()}: windows must be a mapping"]
    active_id = data.get("active_window_id")
    if active_id and active_id not in windows:
        errors.append(f"{AGENT_WINDOWS_PATH.as_posix()}: active_window_id missing from windows")
    active_windows = [window_id for window_id, window in windows.items() if (window or {}).get("status") == "open"]
    if len(active_windows) > 1:
        errors.append(f"{AGENT_WINDOWS_PATH.as_posix()}: multiple active/open windows {active_windows}")
    if active_id and active_windows and active_id not in active_windows:
        errors.append(f"{AGENT_WINDOWS_PATH.as_posix()}: active_window_id does not point to an open window")
    seen_receipt_paths: set[str] = set()
    for window_id, window in sorted(windows.items()):
        if window.get("role") == "historical_preserved":
            for key in ["event_snapshot_path", "metric_snapshot_path"]:
                rel_path = str(window.get(key) or "")
                if not rel_path:
                    errors.append(f"{AGENT_WINDOWS_PATH.as_posix()}: {window_id} missing {key}")
                    continue
                snapshot = repo_root / rel_path
                if not _exists(snapshot):
                    errors.append(f"{AGENT_WINDOWS_PATH.as_posix()}: {window_id} missing snapshot {rel_path}")
                    continue
                sha_key = key.replace("_path", "_sha256")
                if window.get(sha_key) != sha256_file(snapshot):
                    errors.append(f"{AGENT_WINDOWS_PATH.as_posix()}: {window_id} {sha_key} mismatch")
            continue
        if window.get("role") != "prospective_proof":
            errors.append(f"{AGENT_WINDOWS_PATH.as_posix()}: {window_id} unknown role {window.get('role')}")
            continue
        status = window.get("status")
        if status not in {"open", "closed"}:
            errors.append(f"{AGENT_WINDOWS_PATH.as_posix()}: {window_id} invalid status {status}")
        if _timestamp(window.get("start_utc")) is None:
            errors.append(f"{AGENT_WINDOWS_PATH.as_posix()}: {window_id} invalid start_utc")
        if status == "closed" and _timestamp(window.get("end_utc")) is None:
            errors.append(f"{AGENT_WINDOWS_PATH.as_posix()}: {window_id} closed window missing end_utc")
        if require_closed and status != "closed":
            errors.append(f"{AGENT_WINDOWS_PATH.as_posix()}: {window_id} must be closed")
        work_items = window.get("work_items") or {}
        if not isinstance(work_items, dict):
            errors.append(f"{AGENT_WINDOWS_PATH.as_posix()}: {window_id} work_items must be a mapping")
            continue
        for work_item_id, item in sorted(work_items.items()):
            if item.get("observation_window_id") and item.get("observation_window_id") != window_id:
                errors.append(f"{AGENT_WINDOWS_PATH.as_posix()}: {work_item_id} receipt belongs to multiple windows")
            start_path = v2_start_receipt_path(work_item_id)
            final_path = v2_finalization_receipt_path(work_item_id)
            if start_path.as_posix() in seen_receipt_paths or final_path.as_posix() in seen_receipt_paths:
                errors.append(f"{AGENT_WINDOWS_PATH.as_posix()}: duplicate receipt path for {work_item_id}")
            seen_receipt_paths.update({start_path.as_posix(), final_path.as_posix()})
            if not _exists(repo_root / start_path):
                errors.append(f"{AGENT_WINDOWS_PATH.as_posix()}: {work_item_id} start receipt missing")
            else:
                errors.extend(validate_agent_start_receipt(repo_root, start_path))
            if item.get("status") == "finalized" or _exists(repo_root / final_path):
                if not _exists(repo_root / final_path):
                    errors.append(f"{AGENT_WINDOWS_PATH.as_posix()}: {work_item_id} finalization receipt missing")
                else:
                    errors.extend(validate_agent_finalization_receipt(repo_root, final_path))
    return errors


def validate_agent_window_close_ready(repo_root: Path, window_id: str) -> list[str]:
    errors = validate_agent_observation_windows(repo_root)
    if errors:
        return errors
    windows = read_yaml(repo_root / AGENT_WINDOWS_PATH)
    window = (windows.get("windows") or {}).get(window_id)
    if not window:
        return [f"{AGENT_WINDOWS_PATH.as_posix()}: unknown window {window_id}"]
    if window.get("status") != "closed":
        errors.append(f"{AGENT_WINDOWS_PATH.as_posix()}: {window_id} is not closed")
    work_items = window.get("work_items") or {}
    finalized = [item for item in work_items.values() if item.get("status") == "finalized"]
    failed = [work_id for work_id, item in work_items.items() if item.get("result_status") in {"failed", "aborted"}]
    if len(finalized) != len(work_items):
        errors.append(f"{AGENT_WINDOWS_PATH.as_posix()}: {window_id} has unfinalized work items")
    if failed:
        errors.append(f"{AGENT_WINDOWS_PATH.as_posix()}: {window_id} has failed or aborted drills {sorted(failed)}")
    observed_count = len(finalized)
    distinct_families = len({item.get("primary_family") for item in finalized if item.get("primary_family")})
    coverage = _ratio(observed_count, len(work_items))
    minimum_observed = int(window.get("minimum_observed_work_items") or 0)
    minimum_families = int(window.get("minimum_distinct_work_families") or 0)
    minimum_coverage = float(window.get("minimum_observation_coverage_ratio") or 0.80)
    if observed_count < minimum_observed:
        errors.append(f"{AGENT_WINDOWS_PATH.as_posix()}: {window_id} observed work item count below minimum")
    if distinct_families < minimum_families:
        errors.append(f"{AGENT_WINDOWS_PATH.as_posix()}: {window_id} distinct work family count below minimum")
    if coverage < minimum_coverage:
        errors.append(f"{AGENT_WINDOWS_PATH.as_posix()}: {window_id} observation coverage below minimum")
    return errors


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


def _project_legacy_agent_events(repo_root: Path) -> dict[str, Any]:
    progress = read_yaml(repo_root / PROGRESS_LEDGER_PATH)
    start = str(progress.get("initialized_at_utc") or "")
    end = str(progress.get("completed_at_utc") or "")
    work_events: list[dict[str, Any]] = []
    consult_events: list[dict[str, Any]] = []
    work_units = progress.get("work_units") or {}
    for work_item_id in sorted(work_units):
        unit = work_units[work_item_id] or {}
        execution = unit.get("agent_execution") or {}
        work_receipt = _load_work_receipt(repo_root, work_item_id)
        if work_receipt:
            execution = {
                "mode": work_receipt.get("agent_mode"),
                "evidence_class": work_receipt.get("evidence_class", "contemporaneous_work_receipt"),
                "consult_ids": work_receipt.get("consult_ids") or [],
                "source_refs": [_source_ref(repo_root, _work_receipt_path(work_item_id))],
                "started_at_utc": work_receipt.get("started_at_utc"),
                "ended_at_utc": work_receipt.get("ended_at_utc"),
            }
        if not execution:
            continue
        mode = str(execution.get("mode") or "unknown")
        evidence_class = str(execution.get("evidence_class") or "unknown")
        started = execution.get("started_at_utc") or unit.get("completed_at_utc")
        ended = execution.get("ended_at_utc") or unit.get("completed_at_utc")
        in_boundary = _timestamp_in_boundary(str(started) if started else None, start, end or None)
        observed = evidence_class == "contemporaneous_work_receipt" and mode != "unknown" and in_boundary
        event = {
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
        if work_receipt:
            event["work_receipt_ref"] = _source_ref(repo_root, _work_receipt_path(work_item_id))
        work_events.append(event)
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
    excluded_historical_consults = [
        {
            "consult_id": item.get("consult_id"),
            "boundary_class": item.get("boundary_class"),
            "original_work_context": "initial_goal_framing"
            if item.get("consult_id") == "tf_goal_us100_onnx_forward_boundary_initial_v2"
            else item.get("work_item_id"),
        }
        for item in consult_events
        if item.get("boundary_class") == "historical_out_of_boundary"
    ]
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
        "excluded_historical_consults": excluded_historical_consults,
        "projection": {
            "generated_from": PROGRESS_LEDGER_PATH.as_posix(),
            "generator": "python -m spacesonar.cli agents events --write",
            "manual_edit_policy": "manual edits fail projection check",
        },
    }


def _project_window_agent_events(repo_root: Path, windows: dict[str, Any], window_id: str, window: dict[str, Any]) -> dict[str, Any]:
    work_events: list[dict[str, Any]] = []
    consult_events: list[dict[str, Any]] = []
    for work_item_id, item in sorted((window.get("work_items") or {}).items()):
        start_path = v2_start_receipt_path(work_item_id)
        final_path = v2_finalization_receipt_path(work_item_id)
        start_errors = validate_agent_start_receipt(repo_root, start_path) if _exists(repo_root / start_path) else [f"{start_path.as_posix()}: missing start receipt"]
        final_errors = (
            validate_agent_finalization_receipt(repo_root, final_path)
            if _exists(repo_root / final_path)
            else [f"{final_path.as_posix()}: missing finalization receipt"]
        )
        start_receipt = read_yaml(repo_root / start_path) if _exists(repo_root / start_path) else {}
        final_receipt = read_yaml(repo_root / final_path) if _exists(repo_root / final_path) else {}
        started = start_receipt.get("started_at_utc") or item.get("started_at_utc")
        ended = final_receipt.get("ended_at_utc") or item.get("ended_at_utc")
        in_boundary = _timestamp_in_boundary(str(started) if started else None, window.get("start_utc"), window.get("end_utc")) and (
            not ended or _timestamp_in_boundary(str(ended), window.get("start_utc"), window.get("end_utc"))
        )
        receipt_errors = [*start_errors, *final_errors]
        observed = (
            not receipt_errors
            and final_receipt.get("evidence_class") == "contemporaneous_work_receipt"
            and final_receipt.get("agent_mode") in KNOWN_AGENT_MODES - {"unknown"}
            and in_boundary
        )
        source_refs = [_source_ref(repo_root, start_path)] if _exists(repo_root / start_path) else []
        if _exists(repo_root / final_path):
            source_refs.append(_source_ref(repo_root, final_path))
        event = {
            "work_item_id": work_item_id,
            "observation_window_id": window_id,
            "primary_family": item.get("primary_family") or start_receipt.get("primary_family") or final_receipt.get("primary_family"),
            "agent_mode": item.get("agent_mode") or final_receipt.get("agent_mode") or start_receipt.get("agent_mode"),
            "evidence_class": final_receipt.get("evidence_class", "contemporaneous_work_receipt" if final_receipt else "unknown"),
            "consult_ids": list(final_receipt.get("consult_ids") or start_receipt.get("consult_ids") or []),
            "source_refs": source_refs,
            "started_at_utc": started,
            "ended_at_utc": ended,
            "result_status": final_receipt.get("result_status") or item.get("result_status"),
            "in_boundary": in_boundary,
            "observed_for_slo": observed,
            "receipt_validation_errors": receipt_errors,
            "work_receipt_refs": {
                "start": _source_ref(repo_root, start_path),
                "finalization": _source_ref(repo_root, final_path),
            },
        }
        work_events.append(event)
    return {
        "version": EVENT_VERSION,
        "updated_utc": window.get("end_utc") or window.get("start_utc"),
        "measurement_boundary": {
            "start_utc": window.get("start_utc"),
            "end_utc": window.get("end_utc"),
            "boundary_id": window_id,
            "status": window.get("status"),
        },
        "source_refs": [_source_ref(repo_root, AGENT_WINDOWS_PATH)],
        "work_item_events": work_events,
        "consult_events": consult_events,
        "excluded_historical_consults": [],
        "historical_windows": _window_history_payload(repo_root, windows),
        "projection": {
            "generated_from": AGENT_WINDOWS_PATH.as_posix(),
            "generator": "python -m spacesonar.cli agents events --write",
            "manual_edit_policy": "manual edits fail projection check",
        },
    }


def project_agent_events(repo_root: Path) -> dict[str, Any]:
    windows = _load_windows(repo_root)
    window_id, window = _selected_observation_window(windows)
    if window_id and window:
        return _project_window_agent_events(repo_root, windows or {}, window_id, window)
    return _project_legacy_agent_events(repo_root)


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
            errors.extend(_validate_ref(repo_root, ref, f"{work_item_id}: source"))
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
            if not _exists(receipt_path):
                errors.append(f"{consult_id}: missing consult receipt {path}")
            elif item.get("sha256") != sha256_file(receipt_path):
                errors.append(f"{consult_id}: source hash mismatch {path}")
    return errors


def agent_operating_events_diff(repo_root: Path) -> list[str]:
    expected = project_agent_events(repo_root)
    path = repo_root / AGENT_EVENTS_PATH
    if not _exists(path):
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
    receipt_validation_failure_count = sum(len(item.get("receipt_validation_errors") or []) for item in work_items)
    failed_or_aborted_count = sum(1 for item in observed_work if item.get("result_status") in {"failed", "aborted"})

    work_item_count = len({item.get("work_item_id") for item in in_boundary_work})
    observed_work_item_count = len({item.get("work_item_id") for item in observed_work})
    solo_work_item_count = sum(1 for item in observed_work if item.get("agent_mode") == "solo")
    routine_work_item_count = sum(1 for item in observed_work if item.get("agent_mode") in {"solo", "micro_specialist"})
    distinct_families = len({item.get("primary_family") for item in observed_work if item.get("primary_family")})
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
    boundary = events.get("measurement_boundary") or {}
    metrics = {
        "observation_window_id": boundary.get("boundary_id"),
        "observation_window_status": boundary.get("status") or ("closed" if boundary.get("end_utc") else "open"),
        "work_item_count": work_item_count,
        "observed_work_item_count": observed_work_item_count,
        "observed_distinct_work_family_count": distinct_families,
        "solo_work_item_count": solo_work_item_count,
        "consult_count": len(consult_events),
        "one_agent_consult_count": one_agent_consult_count,
        "two_agent_consult_count": two_agent_consult_count,
        "three_plus_agent_consult_count": three_plus_agent_consult_count,
        "receipt_validation_failure_count": receipt_validation_failure_count,
        "failed_or_aborted_work_item_count": failed_or_aborted_count,
        **totals,
        "solo_work_share": _ratio(solo_work_item_count, observed_work_item_count),
        "observation_coverage_ratio": _ratio(observed_work_item_count, work_item_count),
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
        "historical_windows": events.get("historical_windows") or [],
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
        work_item_id="work_wp07_closeout_evidence_repair_v0",
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
    if not _exists(path):
        return [f"{AGENT_METRICS_PATH.as_posix()}: missing generated agent metrics projection"]
    observed = read_yaml(path)
    return [] if observed == expected else [f"{AGENT_METRICS_PATH.as_posix()}: generated projection drift"]


def _git_value(repo_root: Path, args: list[str]) -> str:
    import subprocess

    result = subprocess.run(["git", *args], cwd=repo_root, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _commit_agent_window_payload(repo_root: Path, payload: dict[str, Any], command_argv: tuple[str, ...]) -> None:
    context = ExecutionContext(
        repo_root=repo_root,
        work_item_id="work_wp07_closeout_evidence_repair_v0",
        claim_boundary="agent_observation_window_control_only_no_runtime_authority_no_economics_pass",
        command_argv=command_argv,
        validation_commands=("agent_observation_window_validation",),
    )
    tx = ControlPlaneTransaction(context)
    tx.stage_yaml(AGENT_WINDOWS_PATH, payload)
    result = tx.commit(validate=lambda future_root: validate_agent_observation_windows(future_root))
    if result.status not in {"committed", "noop_already_applied"}:
        raise RuntimeError(f"agent window transaction failed: {result.status}: {list(result.errors)}")


def open_agent_observation_window(
    repo_root: Path,
    *,
    window_id: str,
    minimum_observed_work_items: int,
    minimum_distinct_work_families: int,
    command_argv: tuple[str, ...],
) -> dict[str, Any]:
    windows = _load_windows(repo_root) or {"version": WINDOW_VERSION, "active_window_id": None, "windows": {}}
    if windows.get("active_window_id"):
        raise ValueError(f"active observation window already exists: {windows['active_window_id']}")
    if window_id in (windows.get("windows") or {}):
        raise ValueError(f"observation window already exists: {window_id}")
    payload = copy.deepcopy(windows)
    payload.setdefault("windows", {})[window_id] = {
        "status": "open",
        "role": "prospective_proof",
        "start_utc": utc_now(),
        "end_utc": None,
        "minimum_observed_work_items": int(minimum_observed_work_items),
        "minimum_distinct_work_families": int(minimum_distinct_work_families),
        "minimum_observation_coverage_ratio": 0.80,
        "work_items": {},
        "claim_effect": "prospective_contemporaneous_work_receipts_only_no_runtime_authority_no_economics_pass",
    }
    payload["active_window_id"] = window_id
    _commit_agent_window_payload(repo_root, payload, command_argv)
    return payload


def begin_agent_work(
    repo_root: Path,
    *,
    window_id: str,
    work_item_id: str,
    primary_family: str,
    agent_mode: str,
    claim_boundary: str,
    planned_commands: list[str] | None = None,
    input_refs: list[str] | None = None,
    command_argv: tuple[str, ...],
) -> dict[str, Any]:
    windows = _load_windows(repo_root)
    if not windows:
        raise ValueError("agent observation window registry is missing")
    window = (windows.get("windows") or {}).get(window_id)
    if not window or window.get("status") != "open" or windows.get("active_window_id") != window_id:
        raise ValueError(f"observation window is not open: {window_id}")
    if work_item_id in (window.get("work_items") or {}):
        raise ValueError(f"work item already has a receipt in this window: {work_item_id}")
    families = _known_work_families(repo_root)
    if families is not None and primary_family not in families:
        raise ValueError(f"unknown primary_family: {primary_family}")
    if agent_mode not in KNOWN_AGENT_MODES - {"unknown"}:
        raise ValueError(f"unknown agent mode: {agent_mode}")
    refs = [_source_ref(repo_root, path) for path in (input_refs or [])]
    receipt = with_receipt_self_hash(
        {
            "version": START_RECEIPT_VERSION,
            "receipt_status": "started",
            "work_item_id": work_item_id,
            "observation_window_id": window_id,
            "primary_family": primary_family,
            "agent_mode": agent_mode,
            "consult_ids": [],
            "started_at_utc": utc_now(),
            "branch": _git_value(repo_root, ["branch", "--show-current"]) or "non_git_fixture",
            "start_commit_sha": _git_value(repo_root, ["rev-parse", "HEAD"]) or "non_git_fixture",
            "claim_boundary": claim_boundary,
            "planned_commands": planned_commands or [],
            "input_refs": refs,
            "receipt_sha256": {"algorithm": "sha256", "value": ""},
        }
    )
    payload = copy.deepcopy(windows)
    payload["windows"][window_id].setdefault("work_items", {})[work_item_id] = {
        "status": "started",
        "observation_window_id": window_id,
        "primary_family": primary_family,
        "agent_mode": agent_mode,
        "started_at_utc": receipt["started_at_utc"],
        "start_receipt_ref": {"path": v2_start_receipt_path(work_item_id).as_posix()},
    }
    context = ExecutionContext(
        repo_root=repo_root,
        work_item_id="work_wp07_closeout_evidence_repair_v0",
        claim_boundary=claim_boundary,
        command_argv=command_argv,
        validation_commands=("agent_work_start_receipt_validation",),
    )
    tx = ControlPlaneTransaction(context)
    tx.stage_yaml(AGENT_WINDOWS_PATH, payload)
    tx.stage_yaml(v2_start_receipt_path(work_item_id), receipt)
    result = tx.commit(validate=lambda future_root: validate_agent_observation_windows(future_root))
    if result.status not in {"committed", "noop_already_applied"}:
        raise RuntimeError(f"agent work begin failed: {result.status}: {list(result.errors)}")
    return receipt


def finalize_agent_work(
    repo_root: Path,
    *,
    work_item_id: str,
    result_status: str,
    evidence_refs: list[str],
    command_argv: tuple[str, ...],
) -> dict[str, Any]:
    if result_status not in VALID_RESULT_STATUSES:
        raise ValueError(f"invalid result_status: {result_status}")
    windows = _load_windows(repo_root)
    if not windows:
        raise ValueError("agent observation window registry is missing")
    window_id = None
    window = None
    item = None
    for candidate_id, candidate in (windows.get("windows") or {}).items():
        work_items = candidate.get("work_items") or {}
        if work_item_id in work_items:
            if window_id is not None:
                raise ValueError(f"work item belongs to multiple windows: {work_item_id}")
            window_id = candidate_id
            window = candidate
            item = work_items[work_item_id]
    if not window_id or not window or not item:
        raise ValueError(f"work item has no start receipt: {work_item_id}")
    if window.get("status") != "open":
        raise ValueError(f"observation window is not open: {window_id}")
    start_path = v2_start_receipt_path(work_item_id)
    if not _exists(repo_root / start_path):
        raise ValueError(f"start receipt missing for {work_item_id}")
    start_receipt = read_yaml(repo_root / start_path)
    evidence = [_source_ref(repo_root, path) for path in evidence_refs]
    missing_evidence = [ref["path"] for ref in evidence if ref.get("sha256") is None]
    if missing_evidence:
        raise ValueError(f"evidence refs missing: {missing_evidence}")
    receipt = with_receipt_self_hash(
        {
            "version": FINAL_RECEIPT_VERSION,
            "receipt_status": "finalized",
            "work_item_id": work_item_id,
            "observation_window_id": window_id,
            "primary_family": start_receipt.get("primary_family"),
            "agent_mode": start_receipt.get("agent_mode"),
            "consult_ids": list(start_receipt.get("consult_ids") or []),
            "evidence_class": "contemporaneous_work_receipt",
            "start_receipt_ref": _source_ref(repo_root, start_path),
            "ended_at_utc": utc_now(),
            "end_commit_sha": _git_value(repo_root, ["rev-parse", "HEAD"]) or "non_git_fixture",
            "result_status": result_status,
            "command_results": [{"result_ref": ref} for ref in evidence],
            "evidence_refs": evidence,
            "validation_results": [{"result_ref": ref, "status": result_status} for ref in evidence],
            "claim_boundary": start_receipt.get("claim_boundary"),
            "receipt_sha256": {"algorithm": "sha256", "value": ""},
        }
    )
    payload = copy.deepcopy(windows)
    window_item = payload["windows"][window_id]["work_items"][work_item_id]
    window_item.update(
        {
            "status": "finalized",
            "result_status": result_status,
            "ended_at_utc": receipt["ended_at_utc"],
            "finalization_receipt_ref": {"path": v2_finalization_receipt_path(work_item_id).as_posix()},
        }
    )
    context = ExecutionContext(
        repo_root=repo_root,
        work_item_id="work_wp07_closeout_evidence_repair_v0",
        claim_boundary=str(start_receipt.get("claim_boundary") or "agent_work_receipt_only"),
        command_argv=command_argv,
        validation_commands=("agent_work_finalization_receipt_validation",),
    )
    tx = ControlPlaneTransaction(context)
    tx.stage_yaml(AGENT_WINDOWS_PATH, payload)
    tx.stage_yaml(v2_finalization_receipt_path(work_item_id), receipt)
    for ref in evidence:
        rel_path = Path(str(ref["path"]))
        tx.stage_bytes(rel_path, (repo_root / rel_path).read_bytes())
    result = tx.commit(validate=lambda future_root: validate_agent_observation_windows(future_root))
    if result.status not in {"committed", "noop_already_applied"}:
        raise RuntimeError(f"agent work finalize failed: {result.status}: {list(result.errors)}")
    return receipt


def close_agent_observation_window(repo_root: Path, *, window_id: str, command_argv: tuple[str, ...]) -> dict[str, Any]:
    windows = _load_windows(repo_root)
    if not windows:
        raise ValueError("agent observation window registry is missing")
    window = (windows.get("windows") or {}).get(window_id)
    if not window or window.get("status") != "open":
        raise ValueError(f"observation window is not open: {window_id}")
    payload = copy.deepcopy(windows)
    payload["windows"][window_id]["status"] = "closed"
    payload["windows"][window_id]["end_utc"] = utc_now()
    payload["active_window_id"] = None
    work_items = payload["windows"][window_id].get("work_items") or {}
    observed = [item for item in work_items.values() if item.get("status") == "finalized"]
    payload["windows"][window_id]["work_item_count"] = len(work_items)
    payload["windows"][window_id]["observed_work_item_count"] = len(observed)
    payload["windows"][window_id]["observed_distinct_work_family_count"] = len(
        {item.get("primary_family") for item in observed if item.get("primary_family")}
    )
    payload["windows"][window_id]["observation_coverage_ratio"] = _ratio(len(observed), len(work_items))
    context = ExecutionContext(
        repo_root=repo_root,
        work_item_id="work_wp07_closeout_evidence_repair_v0",
        claim_boundary="agent_observation_window_close_only_no_runtime_authority_no_economics_pass",
        command_argv=command_argv,
        validation_commands=("agent_window_close_ready_validation",),
    )
    tx = ControlPlaneTransaction(context)
    tx.stage_yaml(AGENT_WINDOWS_PATH, payload)

    def _validate(future_root: Path) -> list[str]:
        return validate_agent_window_close_ready(future_root, window_id)

    result = tx.commit(validate=_validate)
    if result.status not in {"committed", "noop_already_applied"}:
        raise RuntimeError(f"agent window close failed: {result.status}: {list(result.errors)}")
    return payload
