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
REQUIRED_IDENTITY_FIELDS = (
    "symbol",
    "timeframe",
    "from_date",
    "to_date",
    "model",
    "deposit",
    "leverage",
    "expert",
)


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
            "mtime_utc": None,
        }
    stat = path.stat()
    return {
        "path_key": path_key(path),
        "origin": origin,
        "existed": True,
        "sha256": file_sha256(path),
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "mtime_utc": timestamp_to_utc(stat.st_mtime),
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
            receipt.get("receipt_version") == RECEIPT_VERSION,
            bool(receipt.get("attempt_id")),
            bool(receipt.get("source_report_sha256")),
            _valid_utc(receipt.get("launch_started_at_utc")),
            _valid_utc(receipt.get("report_observed_at_utc")),
            _source_mtime_not_before_launch(receipt),
            bool(receipt.get("report_fresh_for_launch")),
            receipt.get("parse_status") == PARSED_STATUS,
            bool(receipt.get("completion_marker_observed")),
            bool(receipt.get("tester_identity_match")),
            fatal_error_count_is_zero(receipt.get("fatal_error_count")),
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
    expected_identity = dict(expected_identity or {})
    expected_missing = expected_identity_missing_fields(expected_identity)
    observed_at = report_observed_at_utc or utc_now()
    receipt: dict[str, Any] = {
        "receipt_version": RECEIPT_VERSION,
        "attempt_id": attempt_id,
        "source_report_sha256": None,
        "source_report_size_bytes": None,
        "source_report_mtime_utc": None,
        "source_origin": source_origin,
        "source_report_extension": None,
        "launch_started_at_utc": launch_started_at_utc,
        "report_observed_at_utc": observed_at,
        "prelaunch_report_sha256": None,
        "postlaunch_report_sha256": None,
        "freshness_reason": "tester_report_missing",
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
        "expected_identity_missing_fields": expected_missing,
        "tester_identity_match": False,
        "claim_boundary": claim_boundary,
    }

    if report_path is None or not report_path.exists():
        receipt["missing_requirements"] = ["tester_report_observed"]
        receipt["tester_report_completed"] = False
        return receipt

    report = report_path.resolve()
    stat = report.stat()
    postlaunch_hash = file_sha256(report)
    freshness = report_freshness(
        report,
        prelaunch_candidates,
        launch_started_at_utc=launch_started_at_utc,
        postlaunch_hash=postlaunch_hash,
    )
    receipt.update(
        {
            "source_report_sha256": postlaunch_hash,
            "source_report_size_bytes": stat.st_size,
            "source_report_mtime_utc": timestamp_to_utc(stat.st_mtime),
            "source_report_extension": report.suffix.lower(),
            "prelaunch_report_sha256": freshness["prelaunch_report_sha256"],
            "postlaunch_report_sha256": postlaunch_hash,
            "freshness_reason": freshness["freshness_reason"],
            "report_fresh_for_launch": freshness["report_fresh_for_launch"],
        }
    )

    parsed = parse_tester_report(report)
    receipt.update(parsed)
    receipt["expected_identity_missing_fields"] = expected_missing
    receipt["tester_identity_match"] = tester_identity_match(parsed, expected_identity)
    receipt["tester_report_completed"] = tester_report_completed(receipt)
    receipt["missing_requirements"] = receipt_missing_requirements(receipt, expected_identity)
    return receipt


def report_fresh_for_launch(
    report_path: Path,
    prelaunch_candidates: Iterable[dict[str, Any]],
    *,
    launch_started_at_utc: str | None = None,
) -> bool:
    return report_freshness(
        report_path,
        prelaunch_candidates,
        launch_started_at_utc=launch_started_at_utc,
    )["report_fresh_for_launch"]


def report_freshness(
    report_path: Path,
    prelaunch_candidates: Iterable[dict[str, Any]],
    *,
    launch_started_at_utc: str | None,
    postlaunch_hash: str | None = None,
) -> dict[str, Any]:
    report_mtime = datetime.fromtimestamp(report_path.stat().st_mtime, tz=UTC)
    launch_started = parse_utc(launch_started_at_utc)
    if launch_started is None:
        return {
            "prelaunch_report_sha256": None,
            "report_fresh_for_launch": False,
            "freshness_reason": "invalid_launch_started_at_utc",
        }
    if report_mtime < launch_started:
        return {
            "prelaunch_report_sha256": None,
            "report_fresh_for_launch": False,
            "freshness_reason": "source_report_mtime_before_launch_start",
        }

    snapshots = list(prelaunch_candidates)
    key = path_key(report_path)
    current_hash = postlaunch_hash or file_sha256(report_path)
    for snapshot in snapshots:
        if snapshot.get("path_key") != key:
            continue
        if not snapshot.get("existed"):
            return {
                "prelaunch_report_sha256": None,
                "report_fresh_for_launch": True,
                "freshness_reason": "absent_prelaunch_created_after_launch",
            }
        prelaunch_hash = snapshot.get("sha256")
        changed = bool(prelaunch_hash and prelaunch_hash != current_hash)
        return {
            "prelaunch_report_sha256": prelaunch_hash,
            "report_fresh_for_launch": changed,
            "freshness_reason": "hash_changed_after_launch" if changed else "prelaunch_report_unchanged",
        }
    return {
        "prelaunch_report_sha256": None,
        "report_fresh_for_launch": False,
        "freshness_reason": "no_prelaunch_snapshot_for_report_path",
    }


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
    period_value = find_label_value(normalized, ["Period"])
    period_timeframe, period_from, period_to = parse_period_value(period_value)
    fields = {
        "parse_status": PARSED_STATUS,
        "completion_marker_observed": completion_marker_observed(normalized),
        "symbol": find_label_value(normalized, ["Symbol"]),
        "timeframe": find_label_value(normalized, ["Timeframe"]) or period_timeframe,
        "from_date": find_label_value(normalized, ["FromDate", "From date", "From"]) or period_from,
        "to_date": find_label_value(normalized, ["ToDate", "To date", "To"]) or period_to,
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
        if line.rstrip(":=").strip().lower() in lowered_labels:
            return lines[index + 1].strip()
    return None


def parse_period_value(value: str | None) -> tuple[str | None, str | None, str | None]:
    if not value:
        return None, None, None
    timeframe_match = re.search(r"\b(M\d+|H\d+|D1|W1|MN1)\b", value, flags=re.IGNORECASE)
    dates = re.findall(r"\b\d{4}[.-]\d{2}[.-]\d{2}\b", value)
    timeframe = timeframe_match.group(1).upper() if timeframe_match else None
    from_date = dates[0].replace("-", ".") if len(dates) >= 1 else None
    to_date = dates[1].replace("-", ".") if len(dates) >= 2 else None
    return timeframe, from_date, to_date


def completion_marker_observed(text: str) -> bool:
    lower = text.lower()
    markers = (
        "total trades",
        "profit factor",
        "total net profit",
        "balance drawdown",
        "bars in test",
        "report completed",
    )
    return any(marker in lower for marker in markers)


def fatal_error_count(text: str) -> int:
    explicit_any = re.search(r"(?im)^\s*fatal errors?\s*(?:[:=]|\t)\s*(.+?)\s*$", text)
    if explicit_any and not explicit_any.group(1).strip().isdigit():
        return "invalid"  # type: ignore[return-value]
    explicit = re.search(r"(?im)^\s*fatal errors?\s*(?:[:=]|\t)\s*(\d+)\s*$", text)
    if explicit:
        return int(explicit.group(1))
    return len(re.findall(r"\bfatal error\b", text, flags=re.IGNORECASE))


def tester_identity_match(parsed: dict[str, Any], expected: dict[str, Any]) -> bool:
    if expected_identity_missing_fields(expected):
        return False
    for field in REQUIRED_IDENTITY_FIELDS:
        expected_value = expected.get(field)
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
    if receipt.get("receipt_version") != RECEIPT_VERSION:
        missing.append("tester_report_receipt_version")
    if not receipt.get("attempt_id"):
        missing.append("attempt_id")
    if not receipt.get("source_report_sha256"):
        missing.append("tester_report_observed")
    if not _valid_utc(receipt.get("launch_started_at_utc")):
        missing.append("launch_started_at_utc")
    if not _valid_utc(receipt.get("report_observed_at_utc")):
        missing.append("report_observed_at_utc")
    if not _source_mtime_not_before_launch(receipt):
        missing.append("source_report_mtime_not_before_launch")
    if not receipt.get("report_fresh_for_launch"):
        missing.append("tester_report_fresh_for_launch")
    if receipt.get("parse_status") != PARSED_STATUS:
        missing.append("tester_report_parsed")
    if not receipt.get("completion_marker_observed"):
        missing.append("tester_report_completion_marker")
    for field in expected_identity_missing_fields(expected_identity):
        missing.append(f"expected_identity:{field}")
    if not receipt.get("tester_identity_match"):
        missing.append("tester_identity_match")
    if not fatal_error_count_is_zero(receipt.get("fatal_error_count")):
        missing.append("tester_report_fatal_errors_absent")
    return missing


def expected_identity_missing_fields(expected_identity: dict[str, Any]) -> list[str]:
    return [field for field in REQUIRED_IDENTITY_FIELDS if expected_identity.get(field) in (None, "")]


def timestamp_to_utc(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _valid_utc(value: Any) -> bool:
    return parse_utc(value) is not None


def _source_mtime_not_before_launch(receipt: dict[str, Any]) -> bool:
    source_mtime = parse_utc(receipt.get("source_report_mtime_utc"))
    launch_started = parse_utc(receipt.get("launch_started_at_utc"))
    if source_mtime is None or launch_started is None:
        return False
    return source_mtime >= launch_started


def fatal_error_count_is_zero(value: Any) -> bool:
    try:
        return int(value) == 0
    except (TypeError, ValueError):
        return False


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
