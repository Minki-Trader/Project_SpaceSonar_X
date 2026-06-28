from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_BARS = Path(
    "data/raw/mt5_bars/m5/wave0_us100_closedbar_surface_cartography_v0/US100/bars_us100_m5_mt5api_raw.csv"
)
POINT = 0.01
FORMULA_VERSION = "trade_shape_reconstruction_v1"
CLAIM_BOUNDARY = (
    "trade_shape_reconstruction_observation_only_no_tester_deal_ledger_no_runtime_authority_"
    "no_economics_pass_no_selected_baseline"
)

TRADE_SHAPE_FIELDNAMES = [
    "attempt_id",
    "run_id",
    "campaign_id",
    "period_role",
    "symbol",
    "timeframe",
    "side",
    "entry_time",
    "entry_bar_index",
    "entry_price",
    "exit_time",
    "exit_bar_index",
    "exit_price",
    "exit_reason",
    "hold_bars",
    "mfe_points",
    "mae_points",
    "gross_points",
    "exit_efficiency",
    "trade_shape_bucket",
    "source_formula",
]


@dataclass(frozen=True)
class Bar:
    index: int
    open_time: str
    close_time: str
    open: float
    high: float
    low: float
    close: float


@dataclass
class PositionState:
    side: str
    entry_time: str
    entry_bar_index: int
    entry_price: float


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(fs_path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fs_path(path: Path) -> str:
    resolved = str(path.resolve())
    if os.name == "nt" and not resolved.startswith("\\\\?\\"):
        return "\\\\?\\" + resolved
    return resolved


def stat_size(path: Path) -> int:
    return os.stat(fs_path(path)).st_size


def repo_rel(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def load_yaml(path: Path) -> dict[str, Any]:
    with open(fs_path(path), "r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle) or {}


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    Path(fs_path(path.parent)).mkdir(parents=True, exist_ok=True)
    with open(fs_path(path), "w", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=False)


def render_unix_time(value: str) -> str:
    timestamp = int(float(value))
    return datetime.fromtimestamp(timestamp, tz=UTC).strftime("%Y.%m.%d %H:%M:%S")


def load_bars(raw_bars_path: Path) -> tuple[list[Bar], dict[str, Bar], dict[str, Bar]]:
    bars: list[Bar] = []
    by_open: dict[str, Bar] = {}
    by_close: dict[str, Bar] = {}
    with open(fs_path(raw_bars_path), "r", newline="", encoding="utf-8-sig") as handle:
        for index, row in enumerate(csv.DictReader(handle)):
            bar = Bar(
                index=index,
                open_time=render_unix_time(str(row["time_open_unix"])),
                close_time=render_unix_time(str(row["time_close_unix"])),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
            )
            bars.append(bar)
            by_open[bar.open_time] = bar
            by_close[bar.close_time] = bar
    return bars, by_open, by_close


def read_execution_rows(telemetry_path: Path) -> list[dict[str, str]]:
    with open(fs_path(telemetry_path), "r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def execution_bar(time_text: str, by_open: dict[str, Bar], by_close: dict[str, Bar]) -> Bar | None:
    return by_open.get(time_text) or by_close.get(time_text)


def signed_points(side: str, entry_price: float, exit_price: float) -> float:
    if side == "long":
        return (exit_price - entry_price) / POINT
    return (entry_price - exit_price) / POINT


def excursion_points(side: str, entry_price: float, path: list[Bar]) -> tuple[float, float]:
    if not path:
        return 0.0, 0.0
    if side == "long":
        mfe = max(bar.high - entry_price for bar in path) / POINT
        mae = max(entry_price - bar.low for bar in path) / POINT
    else:
        mfe = max(entry_price - bar.low for bar in path) / POINT
        mae = max(bar.high - entry_price for bar in path) / POINT
    return max(0.0, mfe), max(0.0, mae)


def shape_bucket(side: str, gross_points: float, hold_bars: int, mfe_points: float, mae_points: float) -> str:
    if hold_bars <= 1:
        hold_bucket = "hold_0_1"
    elif hold_bars <= 6:
        hold_bucket = "hold_2_6"
    elif hold_bars <= 12:
        hold_bucket = "hold_7_12"
    else:
        hold_bucket = "hold_gt12"

    if abs(gross_points) < 1e-9:
        outcome = "flat_exit"
    elif gross_points > 0:
        efficiency = gross_points / mfe_points if mfe_points > 0 else 0.0
        if efficiency >= 0.66:
            outcome = "efficient_win"
        elif efficiency >= 0.33:
            outcome = "partial_win"
        else:
            outcome = "low_efficiency_win"
    elif mae_points >= mfe_points:
        outcome = "adverse_loss"
    else:
        outcome = "failed_followthrough_loss"
    return f"{side}_{hold_bucket}_{outcome}"


def close_position(
    *,
    attempt_id: str,
    manifest: dict[str, Any],
    position: PositionState,
    exit_time: str,
    exit_bar: Bar,
    exit_reason: str,
    bars: list[Bar],
) -> dict[str, Any]:
    start = min(position.entry_bar_index, exit_bar.index)
    end = max(position.entry_bar_index, exit_bar.index)
    path = bars[start : end + 1]
    gross_points = signed_points(position.side, position.entry_price, exit_bar.open)
    mfe_points, mae_points = excursion_points(position.side, position.entry_price, path)
    hold_bars = max(0, exit_bar.index - position.entry_bar_index)
    exit_efficiency = gross_points / mfe_points if mfe_points > 0 else 0.0
    return {
        "attempt_id": attempt_id,
        "run_id": str(manifest.get("run_id", "")),
        "campaign_id": str(manifest.get("campaign_id", "")),
        "period_role": str((manifest.get("period_identity") or {}).get("period_role", "")),
        "symbol": str(((manifest.get("execution_identity") or {}).get("symbol")) or "US100"),
        "timeframe": str(((manifest.get("execution_identity") or {}).get("timeframe")) or "M5"),
        "side": position.side,
        "entry_time": position.entry_time,
        "entry_bar_index": position.entry_bar_index,
        "entry_price": f"{position.entry_price:.5f}",
        "exit_time": exit_time,
        "exit_bar_index": exit_bar.index,
        "exit_price": f"{exit_bar.open:.5f}",
        "exit_reason": exit_reason,
        "hold_bars": hold_bars,
        "mfe_points": f"{mfe_points:.5f}",
        "mae_points": f"{mae_points:.5f}",
        "gross_points": f"{gross_points:.5f}",
        "exit_efficiency": f"{exit_efficiency:.8f}",
        "trade_shape_bucket": shape_bucket(position.side, gross_points, hold_bars, mfe_points, mae_points),
        "source_formula": FORMULA_VERSION,
    }


def reconstruct_trade_shape_rows(
    *,
    repo_root: Path,
    attempt_id: str,
    bars: list[Bar],
    by_open: dict[str, Bar],
    by_close: dict[str, Bar],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    attempt_root = repo_root / "runtime" / "mt5_attempts" / attempt_id
    manifest = load_yaml(attempt_root / "attempt_manifest.yaml")
    telemetry_path = attempt_root / "telemetry" / "execution_telemetry.csv"
    rows = read_execution_rows(telemetry_path)
    trade_rows: list[dict[str, Any]] = []
    position: PositionState | None = None
    missing_bar_count = 0
    implicit_reversal_close_count = 0
    explicit_close_count = 0
    open_count = 0

    for row in rows:
        action = str(row.get("action") or "")
        time_text = str(row.get("bar_close_time") or "")
        bar = execution_bar(time_text, by_open, by_close)
        if bar is None:
            missing_bar_count += 1
            continue

        if action in {"open_long", "open_short"}:
            side = "long" if action == "open_long" else "short"
            if position is not None:
                trade_rows.append(
                    close_position(
                        attempt_id=attempt_id,
                        manifest=manifest,
                        position=position,
                        exit_time=time_text,
                        exit_bar=bar,
                        exit_reason="implicit_reversal",
                        bars=bars,
                    )
                )
                implicit_reversal_close_count += 1
            position = PositionState(side=side, entry_time=time_text, entry_bar_index=bar.index, entry_price=bar.open)
            open_count += 1
            continue

        if action in {"close_flat", "close_hold_elapsed"} and position is not None:
            trade_rows.append(
                close_position(
                    attempt_id=attempt_id,
                    manifest=manifest,
                    position=position,
                    exit_time=time_text,
                    exit_bar=bar,
                    exit_reason=action,
                    bars=bars,
                )
            )
            position = None
            explicit_close_count += 1

    diagnostic = {
        "source_execution_rows": len(rows),
        "open_count": open_count,
        "closed_trade_count": len(trade_rows),
        "explicit_close_count": explicit_close_count,
        "implicit_reversal_close_count": implicit_reversal_close_count,
        "unclosed_position_count": 1 if position is not None else 0,
        "missing_bar_count": missing_bar_count,
    }
    return trade_rows, diagnostic


def numeric(row: dict[str, Any], key: str) -> float:
    return float(str(row.get(key) or 0.0))


def summarize_group(rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    gross = sum(numeric(row, "gross_points") for row in rows)
    wins = sum(1 for row in rows if numeric(row, "gross_points") > 0)
    losses = sum(1 for row in rows if numeric(row, "gross_points") < 0)
    flats = count - wins - losses
    return {
        "trade_count": count,
        "gross_points_sum": round(gross, 5),
        "gross_points_avg": round(gross / count, 5) if count else 0.0,
        "win_count": wins,
        "loss_count": losses,
        "flat_count": flats,
        "win_rate": round(wins / count, 8) if count else 0.0,
        "avg_mfe_points": round(sum(numeric(row, "mfe_points") for row in rows) / count, 5) if count else 0.0,
        "avg_mae_points": round(sum(numeric(row, "mae_points") for row in rows) / count, 5) if count else 0.0,
        "avg_hold_bars": round(sum(numeric(row, "hold_bars") for row in rows) / count, 5) if count else 0.0,
        "avg_exit_efficiency": round(sum(numeric(row, "exit_efficiency") for row in rows) / count, 8) if count else 0.0,
    }


def summarize_trade_shapes(
    *,
    repo_root: Path,
    attempt_id: str,
    raw_bars_path: Path,
    trade_rows: list[dict[str, Any]],
    diagnostic: dict[str, Any],
) -> dict[str, Any]:
    attempt_root = repo_root / "runtime" / "mt5_attempts" / attempt_id
    manifest_path = attempt_root / "attempt_manifest.yaml"
    telemetry_path = attempt_root / "telemetry" / "execution_telemetry.csv"
    manifest = load_yaml(manifest_path)
    by_direction = {
        side: summarize_group([row for row in trade_rows if row["side"] == side])
        for side in ["long", "short"]
    }
    bucket_names = sorted({str(row["trade_shape_bucket"]) for row in trade_rows})
    by_bucket = {
        bucket: summarize_group([row for row in trade_rows if row["trade_shape_bucket"] == bucket])
        for bucket in bucket_names
    }
    return {
        "version": "mt5_trade_shape_reconstruction_summary_v1",
        "attempt_id": attempt_id,
        "run_id": str(manifest.get("run_id", "")),
        "campaign_id": str(manifest.get("campaign_id", "")),
        "period_role": str((manifest.get("period_identity") or {}).get("period_role", "")),
        "formula_version": FORMULA_VERSION,
        "method": "reconstructed_from_decision_replay_execution_telemetry_and_us100_m5_ohlc",
        "price_basis": "bar_open_at_recorded_bar_close_time_from_retained_ohlc_not_tester_deal_fill",
        "point": POINT,
        "stats": {
            **diagnostic,
            "direction_trade_counts": dict(Counter(str(row["side"]) for row in trade_rows)),
            "trade_shape_bucket_count": len(bucket_names),
        },
        "overall": summarize_group(trade_rows),
        "by_direction": by_direction,
        "by_trade_shape_bucket": by_bucket,
        "source_artifacts": {
            "attempt_manifest": {
                "path": repo_rel(manifest_path, repo_root),
                "sha256": sha256(manifest_path),
                "size_bytes": stat_size(manifest_path),
            },
            "execution_telemetry": {
                "path": repo_rel(telemetry_path, repo_root),
                "sha256": sha256(telemetry_path),
                "size_bytes": stat_size(telemetry_path),
            },
            "raw_bars": {
                "path": repo_rel(raw_bars_path, repo_root),
                "sha256": sha256(raw_bars_path),
                "size_bytes": stat_size(raw_bars_path),
            },
        },
        "claim_boundary": CLAIM_BOUNDARY,
    }


def write_trade_shape_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    Path(fs_path(path.parent)).mkdir(parents=True, exist_ok=True)
    with open(fs_path(path), "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRADE_SHAPE_FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in TRADE_SHAPE_FIELDNAMES})


def reconstruct_attempt(
    *,
    repo_root: Path,
    attempt_id: str,
    raw_bars_path: Path,
    bars_cache: tuple[list[Bar], dict[str, Bar], dict[str, Bar]] | None = None,
    write: bool = True,
) -> dict[str, Any]:
    bars, by_open, by_close = bars_cache or load_bars(raw_bars_path)
    trade_rows, diagnostic = reconstruct_trade_shape_rows(
        repo_root=repo_root,
        attempt_id=attempt_id,
        bars=bars,
        by_open=by_open,
        by_close=by_close,
    )
    summary = summarize_trade_shapes(
        repo_root=repo_root,
        attempt_id=attempt_id,
        raw_bars_path=raw_bars_path,
        trade_rows=trade_rows,
        diagnostic=diagnostic,
    )
    if write:
        attempt_root = repo_root / "runtime" / "mt5_attempts" / attempt_id
        csv_path = attempt_root / "telemetry" / "trade_shape_telemetry.csv"
        summary_path = attempt_root / "trade_shape_summary.yaml"
        write_trade_shape_csv(csv_path, trade_rows)
        summary["source_artifacts"]["trade_shape_telemetry"] = {
            "path": repo_rel(csv_path, repo_root),
            "sha256": sha256(csv_path),
            "size_bytes": stat_size(csv_path),
            "availability": "local_telemetry_hash_recorded",
        }
        write_yaml(summary_path, summary)
    return summary


def discover_decision_replay_attempts(repo_root: Path, campaign_id: str | None) -> list[str]:
    attempt_ids: list[str] = []
    for manifest_path in sorted((repo_root / "runtime" / "mt5_attempts").glob("*/attempt_manifest.yaml")):
        manifest = load_yaml(manifest_path)
        contract = manifest.get("runtime_surface_contract") or {}
        if contract.get("runtime_surface_kind") != "decision_replay":
            continue
        if campaign_id and manifest.get("campaign_id") != campaign_id:
            continue
        telemetry_path = manifest_path.parent / "telemetry" / "execution_telemetry.csv"
        if telemetry_path.exists():
            attempt_ids.append(str(manifest.get("attempt_id") or manifest_path.parent.name))
    return attempt_ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconstruct MT5 trade-shape KPI from decision replay telemetry.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--raw-bars", type=Path, default=None)
    parser.add_argument("--attempt-id", action="append", default=[])
    parser.add_argument("--campaign-id", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    raw_bars_path = args.raw_bars or repo_root / DEFAULT_RAW_BARS
    if not raw_bars_path.is_absolute():
        raw_bars_path = repo_root / raw_bars_path
    attempt_ids = list(args.attempt_id)
    for campaign_id in args.campaign_id:
        attempt_ids.extend(discover_decision_replay_attempts(repo_root, campaign_id))
    attempt_ids = sorted(set(attempt_ids))
    if not attempt_ids:
        attempt_ids = discover_decision_replay_attempts(repo_root, None)

    bars_cache = load_bars(raw_bars_path)
    summaries = []
    for attempt_id in attempt_ids:
        summaries.append(
            reconstruct_attempt(
                repo_root=repo_root,
                attempt_id=attempt_id,
                raw_bars_path=raw_bars_path,
                bars_cache=bars_cache,
                write=not args.dry_run,
            )
        )
    print(json.dumps({"attempt_count": len(summaries), "attempt_ids": attempt_ids}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
