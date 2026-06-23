from __future__ import annotations

import html
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import yaml


RECEIPT_VERSION = "tester_report_receipt_v1"
PARSED_STATUS = "parsed"
UNPARSEABLE_STATUS = "unparseable"
MISSING_STATUS = "missing"


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def file_sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_report_candidate(path: Path, origin: str) -> dict[str, Any]:
    if not path.exists():
        return {
            "path_key": path_key(path),
            "origin": origin,
            "existed": False,
            "sha256": None,
            "size_bytes": None,
            "mtime_ns": None,
        }
    stat = path.stat()
    return {
        "path_key": path_key(path),
        "origin": origin,
        "existed": True,
        "sha256": file_sha256(path),
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def path_key(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").lower()


def write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(receipt, handle, sort_keys=False, allow_unicode=False)


def load_receipt(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig") as handle:
        loaded = yaml.safe_load(handle)
    return loaded if isinstance(loaded, dict) else {}


def tester_report_completed(receipt: dict[str, Any]) -> bool:
    return all(
        [
            bool(receipt.get("report_fresh_for_launch")),
            receipt.get("parse_status") == PARSED_STATUS,
            bool(receipt.get("completion_marker_observed")),
            bool(receipt.get("tester_identity_match")),
            int(receipt.get("fatal_error_count") or 0) == 0,
        ]
    )


def tester_config_identity(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(";") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip().lower()] = value.strip()
    return {
        "symbol": values.get("symbol", ""),
        "timeframe": values.get("period", ""),
        "from_date": values.get("fromdate", ""),
        "to_date": values.get("todate", ""),
        "model": values.get("model", ""),
        "deposit": values.get("deposit", ""),
        "leverage": values.get("leverage", ""),
        "expert": values.get("expert", ""),
    }


def build_tester_report_receipt(
    *,
    attempt_id: str,
    report_path: Path | None,
    source_origin: str | None,
    launch_started_at_utc: str | None,
    report_observed_at_utc: str | None = None,
    prelaunch_candidates: Iterable[dict[str, Any]] = (),
    expected_identity: dict[str, Any] | None = None,
    claim_boundary: str = "tester_report_receipt_only_no_runtime_authority_no_economics_pass",
) -> dict[str, Any]:
    expected_identity = {key: value for key, value in (expected_identity or {}).items() if value not in (None, "")}
    observed_at = report_observed_at_utc or utc_now()
    receipt: dict[str, Any] = {
        "receipt_version": RECEIPT_VERSION,
        "attempt_id": attempt_id,
        "source_report_sha256": None,
        "source_report_size_bytes": None,
        "source_origin": source_origin,
        "source_report_extension": None,
        "launch_started_at_utc": launch_started_at_utc,
        "report_observed_at_utc": observed_at,
        "report_fresh_for_launch": False,
        "parse_status": MISSING_STATUS,
        "completion_marker_observed": False,
        "symbol": None,
        "timeframe": None,
        "from_date": None,
        "to_date": None,
        "model": None,
        "deposit": None,
        "leverage": None,
        "expert": None,
        "fatal_error_count": 0,
        "tester_identity_match": False,
        "claim_boundary": claim_boundary,
    }

    if report_path is None or not report_path.exists():
        receipt["missing_requirements"] = ["tester_report_observed"]
        receipt["tester_report_completed"] = False
        return receipt

    report = report_path.resolve()
    stat = report.stat()
    receipt.update(
        {
            "source_report_sha256": file_sha256(report),
            "source_report_size_bytes": stat.st_size,
            "source_report_extension": report.suffix.lower(),
            "report_fresh_for_launch": report_fresh_for_launch(report, prelaunch_candidates),
        }
    )

    parsed = parse_tester_report(report)
    receipt.update(parsed)
    receipt["tester_identity_match"] = tester_identity_match(parsed, expected_identity)
    receipt["tester_report_completed"] = tester_report_completed(receipt)
    receipt["missing_requirements"] = receipt_missing_requirements(receipt, expected_identity)
    return receipt


def report_fresh_for_launch(report_path: Path, prelaunch_candidates: Iterable[dict[str, Any]]) -> bool:
    snapshots = list(prelaunch_candidates)
    key = path_key(report_path)
    for snapshot in snapshots:
        if snapshot.get("path_key") != key:
            continue
        if not snapshot.get("existed"):
            return True
        return snapshot.get("sha256") != file_sha256(report_path)
    return False


def parse_tester_report(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError:
        return _unparseable()
    text = decode_report_bytes(raw)
    if text is None:
        return _unparseable()
    normalized = normalize_report_text(text)
    if not normalized.strip():
        return _unparseable()
    fields = {
        "parse_status": PARSED_STATUS,
        "completion_marker_observed": completion_marker_observed(normalized),
        "symbol": find_label_value(normalized, ["Symbol"]),
        "timeframe": find_label_value(normalized, ["Timeframe", "Period"]),
        "from_date": find_label_value(normalized, ["FromDate", "From date", "From"]),
        "to_date": find_label_value(normalized, ["ToDate", "To date", "To"]),
        "model": find_label_value(normalized, ["Model"]),
        "deposit": find_label_value(normalized, ["Deposit", "Initial deposit"]),
        "leverage": find_label_value(normalized, ["Leverage"]),
        "expert": find_label_value(normalized, ["Expert", "Expert Advisor"]),
        "fatal_error_count": fatal_error_count(normalized),
    }
    return fields


def decode_report_bytes(raw: bytes) -> str | None:
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def normalize_report_text(text: str) -> str:
    unescaped = html.unescape(text)
    without_tags = re.sub(r"<[^>]+>", "\n", unescaped)
    return without_tags.replace("\r\n", "\n").replace("\r", "\n")


def find_label_value(text: str, labels: list[str]) -> str | None:
    for label in labels:
        pattern = re.compile(rf"(?im)^\s*{re.escape(label)}\s*(?:[:=]|\t)\s*(.+?)\s*$")
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    lowered_labels = {label.lower() for label in labels}
    for index, line in enumerate(lines[:-1]):
        if line.lower() in lowered_labels:
            return lines[index + 1].strip()
    return None


def completion_marker_observed(text: str) -> bool:
    lower = text.lower()
    markers = (
        "total trades",
        "profit factor",
        "balance drawdown",
        "history quality",
        "bars in test",
        "report completed",
    )
    return any(marker in lower for marker in markers)


def fatal_error_count(text: str) -> int:
    explicit = re.search(r"(?im)^\s*fatal errors?\s*(?:[:=]|\t)\s*(\d+)\s*$", text)
    if explicit:
        return int(explicit.group(1))
    return len(re.findall(r"\bfatal error\b", text, flags=re.IGNORECASE))


def tester_identity_match(parsed: dict[str, Any], expected: dict[str, Any]) -> bool:
    if not expected:
        return False
    for field, expected_value in expected.items():
        observed = parsed.get(field)
        if observed in (None, ""):
            return False
        if normalize_identity_value(field, observed) != normalize_identity_value(field, expected_value):
            return False
    return True


def normalize_identity_value(field: str, value: Any) -> str:
    text = str(value).strip().replace("\\", "/")
    if field in {"symbol", "timeframe", "model"}:
        return text.upper()
    if field in {"from_date", "to_date"}:
        return text.replace("-", ".")
    if field == "deposit":
        try:
            return str(float(re.findall(r"-?\d+(?:\.\d+)?", text)[0]))
        except (IndexError, ValueError):
            return text
    if field == "leverage":
        cleaned = text.upper().replace(" ", "")
        if cleaned.startswith("1:"):
            return cleaned
        if cleaned.isdigit():
            return f"1:{cleaned}"
        return cleaned
    if field == "expert":
        return Path(text).stem.lower()
    return text


def receipt_missing_requirements(receipt: dict[str, Any], expected_identity: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not receipt.get("source_report_sha256"):
        missing.append("tester_report_observed")
    if not receipt.get("report_fresh_for_launch"):
        missing.append("tester_report_fresh_for_launch")
    if receipt.get("parse_status") != PARSED_STATUS:
        missing.append("tester_report_parsed")
    if not receipt.get("completion_marker_observed"):
        missing.append("tester_report_completion_marker")
    if expected_identity and not receipt.get("tester_identity_match"):
        missing.append("tester_identity_match")
    if int(receipt.get("fatal_error_count") or 0) != 0:
        missing.append("tester_report_fatal_errors_absent")
    return missing


def _unparseable() -> dict[str, Any]:
    return {
        "parse_status": UNPARSEABLE_STATUS,
        "completion_marker_observed": False,
        "symbol": None,
        "timeframe": None,
        "from_date": None,
        "to_date": None,
        "model": None,
        "deposit": None,
        "leverage": None,
        "expert": None,
        "fatal_error_count": 0,
    }
