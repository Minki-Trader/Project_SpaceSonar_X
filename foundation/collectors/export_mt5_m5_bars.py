from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import MetaTrader5 as mt5


UTC = timezone.utc
M5_SECONDS = 5 * 60


@dataclass(frozen=True)
class SymbolBinding:
    contract_symbol: str
    broker_symbol: str


DEFAULT_SYMBOL_BINDINGS: tuple[SymbolBinding, ...] = (
    SymbolBinding("US100", "US100"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export SpaceSonar raw M5 bars from the connected MetaTrader 5 terminal."
    )
    parser.add_argument(
        "--symbol",
        action="append",
        metavar="CONTRACT=BROKER",
        help=(
            "Symbol binding to export. Repeat for live-chart auxiliary research symbols. "
            "If omitted, exports US100=US100 only."
        ),
    )
    parser.add_argument(
        "--output-root",
        default="data/raw/mt5_bars/m5",
        help="Repo-relative output root for raw M5 bar exports.",
    )
    parser.add_argument(
        "--start-utc",
        required=True,
        help="Inclusive UTC start for M5 bar opens.",
    )
    parser.add_argument(
        "--end-utc",
        required=True,
        help="Inclusive UTC end for M5 bar opens.",
    )
    parser.add_argument(
        "--aux-evidence-id",
        default=None,
        help="Required when exporting non-US100 auxiliary symbols; records local MT5 live-chart availability evidence.",
    )
    parser.add_argument(
        "--price-basis",
        default="Bid",
        help="Price basis label to write into the CSV manifest fields.",
    )
    return parser.parse_args()


def parse_symbol_bindings(values: list[str] | None) -> tuple[SymbolBinding, ...]:
    if not values:
        return DEFAULT_SYMBOL_BINDINGS
    bindings: list[SymbolBinding] = []
    for value in values:
        if "=" in value:
            contract_symbol, broker_symbol = value.split("=", 1)
        else:
            contract_symbol = value
            broker_symbol = value
        contract_symbol = contract_symbol.strip()
        broker_symbol = broker_symbol.strip()
        if not contract_symbol or not broker_symbol:
            raise ValueError(f"Invalid symbol binding: {value!r}")
        bindings.append(SymbolBinding(contract_symbol, broker_symbol))
    return tuple(bindings)


def validate_symbol_scope(bindings: Iterable[SymbolBinding], aux_evidence_id: str | None) -> None:
    requires_aux_evidence = any(
        binding.contract_symbol.upper() != "US100" or binding.broker_symbol.upper() != "US100"
        for binding in bindings
    )
    if requires_aux_evidence and not aux_evidence_id:
        raise ValueError("--aux-evidence-id is required for non-US100 auxiliary symbol exports.")


def parse_utc_timestamp(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"UTC timestamp must be timezone-aware: {value}")
    return parsed.astimezone(UTC)


def normalize_file_token(value: str) -> str:
    return value.lower().replace(".", "_")


def ensure_symbol_selected(symbol: str) -> None:
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"Symbol not found in terminal: {symbol}")
    if not info.visible and not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"Failed to select symbol in Market Watch: {symbol}")


def write_csv(csv_path: Path, binding: SymbolBinding, rates, price_basis: str) -> None:
    fieldnames = [
        "time_open_unix",
        "time_close_unix",
        "contract_symbol",
        "broker_symbol",
        "timeframe",
        "price_basis",
        "open",
        "high",
        "low",
        "close",
        "tick_volume",
        "spread_points",
        "real_volume",
        "time_basis",
        "timezone_status",
    ]
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rates:
            time_open_unix = int(row["time"])
            writer.writerow(
                {
                    "time_open_unix": time_open_unix,
                    "time_close_unix": time_open_unix + M5_SECONDS,
                    "contract_symbol": binding.contract_symbol,
                    "broker_symbol": binding.broker_symbol,
                    "timeframe": "M5",
                    "price_basis": price_basis,
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "tick_volume": int(row["tick_volume"]),
                    "spread_points": int(row["spread"]),
                    "real_volume": int(row["real_volume"]),
                    "time_basis": "MT5_PY_API_UNIX_SECONDS",
                    "timezone_status": "UNRESOLVED_REQUIRES_MANUAL_BINDING",
                }
            )


def write_manifest(
    manifest_path: Path,
    binding: SymbolBinding,
    csv_path: Path,
    rates,
    requested_from_utc: datetime,
    requested_to_utc: datetime,
    price_basis: str,
    aux_evidence_id: str | None,
) -> None:
    first_open_unix = int(rates[0]["time"])
    last_open_unix = int(rates[-1]["time"])
    last_close_unix = last_open_unix + M5_SECONDS
    terminal = mt5.terminal_info()
    payload = {
        "manifest_version": "SPACESONAR_X_RAW_BAR_EXPORT_V1",
        "export_status": "COMPLETE",
        "terminal_path": terminal.path if terminal else None,
        "terminal_data_path": terminal.data_path if terminal else None,
        "contract_symbol": binding.contract_symbol,
        "broker_symbol": binding.broker_symbol,
        "timeframe": "M5",
        "requested_from_utc": requested_from_utc.isoformat().replace("+00:00", "Z"),
        "requested_to_utc": requested_to_utc.isoformat().replace("+00:00", "Z"),
        "resolved_first_open_unix": first_open_unix,
        "resolved_last_open_unix": last_open_unix,
        "resolved_last_close_unix": last_close_unix,
        "row_count": len(rates),
        "csv_file": str(csv_path.resolve()),
        "time_basis": "MT5_PY_API_UNIX_SECONDS",
        "source_timezone": "OPEN",
        "calendar_id": "OPEN",
        "timezone_status": "UNRESOLVED_REQUIRES_MANUAL_BINDING",
        "bar_open_column": "time_open_unix",
        "bar_close_column": "time_close_unix",
        "price_basis": price_basis,
        "aux_evidence_id": aux_evidence_id,
        "source_scope_policy": "primary_us100_or_broker_native_live_chart_auxiliary_with_evidence",
        "generated_at_utc": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "note": (
            "Raw export produced directly from MetaTrader5.copy_rates_range for "
            "Project SpaceSonar X ONNX Lab. The default symbol is US100. "
            "Additional broker-native symbols are valid lab inputs only when "
            "the local MT5 terminal proves live chart and bar/tick availability."
        ),
    }
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_summary(
    summary_path: Path,
    rows: list[dict[str, object]],
    requested_from_utc: datetime,
    requested_to_utc: datetime,
    aux_evidence_id: str | None,
) -> None:
    payload = {
        "summary_version": "SPACESONAR_X_RAW_BAR_EXPORT_SUMMARY_V1",
        "requested_from_utc": requested_from_utc.isoformat().replace("+00:00", "Z"),
        "requested_to_utc": requested_to_utc.isoformat().replace("+00:00", "Z"),
        "aux_evidence_id": aux_evidence_id,
        "exported_symbols": rows,
        "generated_at_utc": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
    }
    summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def export_symbol(
    output_root: Path,
    binding: SymbolBinding,
    requested_from_utc: datetime,
    requested_to_utc: datetime,
    price_basis: str,
    aux_evidence_id: str | None,
) -> dict[str, object]:
    ensure_symbol_selected(binding.broker_symbol)
    rates = mt5.copy_rates_range(
        binding.broker_symbol,
        mt5.TIMEFRAME_M5,
        requested_from_utc,
        requested_to_utc,
    )
    if rates is None:
        raise RuntimeError(f"MT5 copy_rates_range failed for {binding.broker_symbol}: {mt5.last_error()}")
    if len(rates) == 0:
        raise RuntimeError(f"No M5 bars returned for {binding.broker_symbol} in the requested window.")

    symbol_root = output_root / binding.contract_symbol
    file_token = normalize_file_token(binding.broker_symbol)
    csv_path = symbol_root / f"bars_{file_token}_m5_mt5api_raw.csv"
    manifest_path = symbol_root / f"bars_{file_token}_m5_mt5api_raw.manifest.json"

    write_csv(csv_path, binding, rates, price_basis)
    write_manifest(
        manifest_path,
        binding,
        csv_path,
        rates,
        requested_from_utc,
        requested_to_utc,
        price_basis,
        aux_evidence_id,
    )

    first_open_unix = int(rates[0]["time"])
    last_open_unix = int(rates[-1]["time"])
    return {
        "contract_symbol": binding.contract_symbol,
        "broker_symbol": binding.broker_symbol,
        "row_count": len(rates),
        "csv_path": str(csv_path.resolve()),
        "manifest_path": str(manifest_path.resolve()),
        "first_open_unix": first_open_unix,
        "last_open_unix": last_open_unix,
        "aux_evidence_id": aux_evidence_id,
    }


def export_all(
    output_root: Path,
    symbol_bindings: Iterable[SymbolBinding],
    requested_from_utc: datetime,
    requested_to_utc: datetime,
    price_basis: str,
    aux_evidence_id: str | None,
) -> list[dict[str, object]]:
    exported: list[dict[str, object]] = []
    for binding in symbol_bindings:
        exported.append(
            export_symbol(
                output_root=output_root,
                binding=binding,
                requested_from_utc=requested_from_utc,
                requested_to_utc=requested_to_utc,
                price_basis=price_basis,
                aux_evidence_id=aux_evidence_id,
            )
        )
    return exported


def main() -> int:
    args = parse_args()
    output_root = Path(args.output_root)
    requested_from_utc = parse_utc_timestamp(args.start_utc)
    requested_to_utc = parse_utc_timestamp(args.end_utc)
    symbol_bindings = parse_symbol_bindings(args.symbol)
    validate_symbol_scope(symbol_bindings, args.aux_evidence_id)
    if requested_to_utc <= requested_from_utc:
        raise ValueError("end-utc must be later than start-utc")

    if not mt5.initialize():
        raise RuntimeError(f"Failed to initialize MetaTrader5: {mt5.last_error()}")

    try:
        exported = export_all(
            output_root=output_root,
            symbol_bindings=symbol_bindings,
            requested_from_utc=requested_from_utc,
            requested_to_utc=requested_to_utc,
            price_basis=args.price_basis,
            aux_evidence_id=args.aux_evidence_id,
        )
        summary_path = output_root / "raw_export_summary.json"
        write_summary(summary_path, exported, requested_from_utc, requested_to_utc, args.aux_evidence_id)
        print(json.dumps({"status": "ok", "exported_symbols": exported, "summary_path": str(summary_path.resolve())}, indent=2))
        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
