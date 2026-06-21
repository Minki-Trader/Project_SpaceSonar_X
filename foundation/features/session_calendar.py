from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd


BROKER_CLOCK_TIMEZONE = "Europe/Athens"
SESSION_TIMEZONE = "America/New_York"
M5_SECONDS = 5 * 60


@dataclass(frozen=True)
class CalendarAuditSymbol:
    contract_symbol: str
    broker_symbol: str


DEFAULT_AUDIT_SYMBOLS: tuple[CalendarAuditSymbol, ...] = (
    CalendarAuditSymbol("US100", "US100"),
)


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def broker_clock_key_to_event_utc(
    timestamp_key: pd.Series,
    *,
    broker_timezone: str = BROKER_CLOCK_TIMEZONE,
) -> pd.Series:
    """Convert raw broker-clock timestamp keys into event UTC timestamps."""
    broker_clock = pd.to_datetime(timestamp_key, utc=True)
    broker_wall_clock = broker_clock.dt.tz_convert("UTC").dt.tz_localize(None)
    broker_local = broker_wall_clock.dt.tz_localize(
        broker_timezone,
        ambiguous="raise",
        nonexistent="raise",
    )
    return broker_local.dt.tz_convert("UTC")


def attach_event_time_columns(
    frame: pd.DataFrame,
    *,
    broker_clock_col: str = "timestamp",
    broker_timezone: str = BROKER_CLOCK_TIMEZONE,
    session_timezone: str = SESSION_TIMEZONE,
) -> pd.DataFrame:
    result = frame.copy()
    result["timestamp_broker_clock"] = result[broker_clock_col]
    result["timestamp_event_utc"] = broker_clock_key_to_event_utc(
        result[broker_clock_col],
        broker_timezone=broker_timezone,
    )
    result["timestamp_ny"] = result["timestamp_event_utc"].dt.tz_convert(session_timezone)
    result["broker_clock_timezone"] = broker_timezone
    return result


def compute_us_cash_session_features(
    frame: pd.DataFrame,
    *,
    event_time_col: str = "timestamp_event_utc",
    session_timezone: str = SESSION_TIMEZONE,
) -> dict[str, pd.Series]:
    if event_time_col not in frame.columns:
        raise ValueError(f"Missing required event timestamp column: {event_time_col}")

    timestamp_ny = frame[event_time_col].dt.tz_convert(session_timezone)
    ny_date = timestamp_ny.dt.date
    session_midnight = timestamp_ny.dt.normalize()
    is_us_cash_open = (
        ((timestamp_ny.dt.hour > 9) | ((timestamp_ny.dt.hour == 9) & (timestamp_ny.dt.minute >= 35)))
        & ((timestamp_ny.dt.hour < 16) | ((timestamp_ny.dt.hour == 16) & (timestamp_ny.dt.minute == 0)))
    ).astype(float)

    session_open_ts = session_midnight + pd.Timedelta(hours=9, minutes=30)
    minutes_from_cash_open = (timestamp_ny - session_open_ts).dt.total_seconds() / 60.0
    is_first_30m_after_open = ((minutes_from_cash_open > 0) & (minutes_from_cash_open <= 30)).astype(float)

    session_close_ts = session_midnight + pd.Timedelta(hours=16)
    minutes_to_cash_close = (session_close_ts - timestamp_ny).dt.total_seconds() / 60.0
    is_last_30m_before_cash_close = (
        (minutes_to_cash_close >= 0) & (minutes_to_cash_close <= 25)
    ).astype(float)

    cash_open_mask = (timestamp_ny.dt.hour == 9) & (timestamp_ny.dt.minute == 35)
    cash_close_mask = (timestamp_ny.dt.hour == 16) & (timestamp_ny.dt.minute == 0)

    cash_open_today = frame["open"].where(cash_open_mask).groupby(ny_date).transform("first")
    cash_close_by_date = frame.loc[cash_close_mask, ["close"]].copy()
    cash_close_by_date["ny_date"] = ny_date.loc[cash_close_mask].values
    cash_close_prev_lookup = cash_close_by_date.groupby("ny_date")["close"].last().shift(1)
    cash_close_prev_session = pd.Series(ny_date, index=frame.index).map(cash_close_prev_lookup)
    overnight_return = cash_open_today / cash_close_prev_session - 1.0
    overnight_return = overnight_return.groupby(ny_date).ffill()

    return {
        "timestamp_ny": timestamp_ny,
        "is_us_cash_open": is_us_cash_open,
        "minutes_from_cash_open": minutes_from_cash_open,
        "is_first_30m_after_open": is_first_30m_after_open,
        "is_last_30m_before_cash_close": is_last_30m_before_cash_close,
        "overnight_return": overnight_return,
    }


def read_symbol_raw_frame(raw_root: Path, symbol: CalendarAuditSymbol) -> pd.DataFrame:
    symbol_dir = raw_root / symbol.contract_symbol
    csv_files = sorted(symbol_dir.glob("*.csv"))
    if len(csv_files) != 1:
        raise RuntimeError(f"Expected one raw CSV for {symbol.contract_symbol}, found {len(csv_files)}")
    frame = pd.read_csv(csv_files[0])
    required = {"time_open_unix", "time_close_unix", "open", "close"}
    missing = required.difference(frame.columns)
    if missing:
        raise RuntimeError(f"{csv_files[0]} missing required columns: {sorted(missing)}")
    frame["timestamp"] = pd.to_datetime(frame["time_close_unix"], unit="s", utc=True)
    return attach_event_time_columns(frame)


def summarize_symbol_calendar(frame: pd.DataFrame, symbol: CalendarAuditSymbol) -> dict[str, object]:
    session_features = compute_us_cash_session_features(frame)
    timestamp_ny = session_features["timestamp_ny"]
    is_cash = session_features["is_us_cash_open"].astype(bool)
    cash_frame = pd.DataFrame(
        {
            "ny_date": timestamp_ny.dt.date,
            "ny_clock": timestamp_ny.dt.strftime("%H:%M"),
            "is_cash": is_cash,
        }
    )
    cash_frame = cash_frame.loc[cash_frame["is_cash"]].copy()

    day_rows: dict[object, list[str]] = defaultdict(list)
    for row in cash_frame.itertuples(index=False):
        day_rows[row.ny_date].append(str(row.ny_clock))

    full_days = 0
    partial_days = 0
    first_clocks: Counter[str] = Counter()
    last_clocks: Counter[str] = Counter()
    row_counts: Counter[int] = Counter()
    for clocks in day_rows.values():
        ordered = sorted(clocks)
        first_clocks[ordered[0]] += 1
        last_clocks[ordered[-1]] += 1
        row_counts[len(ordered)] += 1
        if ordered[0] == "09:35" and ordered[-1] == "16:00" and len(ordered) == 78:
            full_days += 1
        else:
            partial_days += 1

    total_days = full_days + partial_days
    return {
        "contract_symbol": symbol.contract_symbol,
        "broker_symbol": symbol.broker_symbol,
        "raw_rows": int(len(frame)),
        "cash_session_rows": int(is_cash.sum()),
        "cash_session_days": total_days,
        "full_cash_session_days": full_days,
        "partial_cash_session_days": partial_days,
        "full_cash_session_ratio": round(full_days / total_days, 6) if total_days else 0.0,
        "first_cash_close_clock_distribution": dict(first_clocks.most_common()),
        "last_cash_close_clock_distribution": dict(last_clocks.most_common()),
        "cash_row_count_distribution": {str(key): value for key, value in row_counts.most_common()},
    }


def build_calendar_audit(
    raw_root: Path,
    *,
    symbols: Iterable[CalendarAuditSymbol] = DEFAULT_AUDIT_SYMBOLS,
    repo_root: Path | None = None,
) -> dict[str, object]:
    repo_root = repo_root or Path.cwd()
    symbol_summaries = []
    for symbol in symbols:
        frame = read_symbol_raw_frame(raw_root, symbol)
        symbol_summaries.append(summarize_symbol_calendar(frame, symbol))

    full_days = sum(int(symbol["full_cash_session_days"]) for symbol in symbol_summaries)
    total_days = sum(int(symbol["cash_session_days"]) for symbol in symbol_summaries)
    partial_days = sum(int(symbol["partial_cash_session_days"]) for symbol in symbol_summaries)
    summary = {
        "audit_version": "SPACESONAR_X_US100_SESSION_CALENDAR_AUDIT_V1",
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "raw_root": repo_relative(raw_root, repo_root),
        "broker_clock_timezone": BROKER_CLOCK_TIMEZONE,
        "session_timezone": SESSION_TIMEZONE,
        "symbols_checked": [symbol.contract_symbol for symbol in symbols],
        "cash_session_days": total_days,
        "full_cash_session_days": full_days,
        "partial_cash_session_days": partial_days,
        "full_cash_session_ratio": round(full_days / total_days, 6) if total_days else 0.0,
        "status": "mapper_observation_ready",
        "boundary": (
            "This verifies the broker-clock to event-time mapper for session features. "
            "It does not claim model readiness, runtime authority, or operating promotion."
        ),
    }
    return {
        "summary": summary,
        "symbols": symbol_summaries,
    }


def render_markdown(audit: dict[str, object]) -> str:
    summary = audit["summary"]
    symbols = audit["symbols"]
    assert isinstance(summary, dict)
    assert isinstance(symbols, list)

    lines = [
        "# Broker Session Calendar Mapper",
        "",
        "## Summary",
        "",
        f"- status: `{summary['status']}`",
        f"- broker_clock_timezone: `{summary['broker_clock_timezone']}`",
        f"- session_timezone: `{summary['session_timezone']}`",
        f"- cash_session_days: `{summary['cash_session_days']}`",
        f"- full_cash_session_days: `{summary['full_cash_session_days']}`",
        f"- partial_cash_session_days: `{summary['partial_cash_session_days']}`",
        f"- full_cash_session_ratio: `{summary['full_cash_session_ratio']}`",
        "",
        "This audit checks broker-clock to event-UTC and New York session mapping for raw M5 bars.",
        "Partial cash sessions are reported explicitly, not silently dropped.",
        "",
        "## Symbol Readout",
        "",
        "| symbol | raw rows | cash rows | full days | partial days | first clocks | row counts |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for symbol in symbols:
        assert isinstance(symbol, dict)
        lines.append(
            "| "
            f"`{symbol['contract_symbol']}` | "
            f"{symbol['raw_rows']} | "
            f"{symbol['cash_session_rows']} | "
            f"{symbol['full_cash_session_days']} | "
            f"{symbol['partial_cash_session_days']} | "
            f"`{symbol['first_cash_close_clock_distribution']}` | "
            f"`{symbol['cash_row_count_distribution']}` |"
        )

    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This is a time-mapper/session-feature audit only. It does not claim model readiness, runtime authority, or operating promotion.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(audit: dict[str, object], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "broker_session_calendar_audit.json").write_text(
        json.dumps(audit, indent=2),
        encoding="utf-8",
    )
    (output_dir / "broker_session_calendar_audit.md").write_text(
        render_markdown(audit),
        encoding="utf-8-sig",
    )
    manifest = {
        "run_id": output_dir.name,
        "lane": "evidence",
        "work_scope": "raw_m5_session_calendar_audit",
        "command": (
            "python foundation/features/session_calendar.py "
            "--raw-root data/raw/mt5_bars/m5 "
            f"--output-dir {output_dir.as_posix()}"
        ),
        "outputs": [
            (output_dir / "broker_session_calendar_audit.json").as_posix(),
            (output_dir / "broker_session_calendar_audit.md").as_posix(),
        ],
        "judgment_boundary": (
            "Evidence run only. This closes the broker-clock to session-time mapper, "
            "not model readiness or runtime authority."
        ),
    }
    (output_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit active SpaceSonar US100 broker-clock session calendar mapping.")
    parser.add_argument("--raw-root", default="data/raw/mt5_bars/m5")
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    audit = build_calendar_audit(Path(args.raw_root), repo_root=Path.cwd())
    write_outputs(audit, Path(args.output_dir))
    print(json.dumps(audit["summary"], indent=2))


if __name__ == "__main__":
    main()
