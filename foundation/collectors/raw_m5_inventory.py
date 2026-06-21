from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


UTC = timezone.utc
M5_SECONDS = 5 * 60

REQUIRED_COLUMNS = (
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
)


@dataclass(frozen=True)
class SymbolExpectation:
    contract_symbol: str
    broker_symbol: str


DEFAULT_EXPECTED_SYMBOLS: tuple[SymbolExpectation, ...] = (
    SymbolExpectation("US100", "US100"),
)


@dataclass
class SymbolInventory:
    contract_symbol: str
    expected_broker_symbol: str
    symbol_dir: str
    status: str
    csv_status: str
    manifest_status: str
    csv_path: str | None = None
    manifest_path: str | None = None
    csv_sha256: str | None = None
    manifest_sha256: str | None = None
    csv_size_bytes: int | None = None
    row_count: int = 0
    first_open_unix: int | None = None
    last_open_unix: int | None = None
    first_open_utc: str | None = None
    last_open_utc: str | None = None
    contract_symbol_values: list[str] = field(default_factory=list)
    broker_symbol_values: list[str] = field(default_factory=list)
    timeframe_values: list[str] = field(default_factory=list)
    price_basis_values: list[str] = field(default_factory=list)
    timezone_status_values: list[str] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)
    unexpected_columns: list[str] = field(default_factory=list)
    open_alignment_error_count: int = 0
    close_span_error_count: int = 0
    duplicate_open_count: int = 0
    backwards_step_count: int = 0
    non_m5_forward_step_count: int = 0
    largest_forward_gap_seconds: int | None = None
    manifest_mismatches: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def unix_to_utc(value: int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=UTC).isoformat().replace("+00:00", "Z")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_manifest(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("manifest root is not a JSON object")
    return payload


def int_or_none(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def sorted_values(values: set[str]) -> list[str]:
    return sorted(value for value in values if value != "")


def inspect_csv(csv_path: Path, inventory: SymbolInventory, repo_root: Path) -> None:
    inventory.csv_path = repo_relative(csv_path, repo_root)
    inventory.csv_sha256 = file_sha256(csv_path)
    inventory.csv_size_bytes = csv_path.stat().st_size

    contract_values: set[str] = set()
    broker_values: set[str] = set()
    timeframe_values: set[str] = set()
    price_basis_values: set[str] = set()
    timezone_status_values: set[str] = set()
    seen_opens: set[int] = set()
    previous_open: int | None = None

    with csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = tuple(reader.fieldnames or ())
        inventory.missing_columns = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
        inventory.unexpected_columns = [column for column in fieldnames if column not in REQUIRED_COLUMNS]

        for row in reader:
            inventory.row_count += 1
            try:
                open_unix = int(row.get("time_open_unix") or "")
                close_unix = int(row.get("time_close_unix") or "")
            except ValueError:
                inventory.notes.append(f"row {inventory.row_count}: invalid open or close unix timestamp")
                continue

            if inventory.first_open_unix is None:
                inventory.first_open_unix = open_unix
            inventory.last_open_unix = open_unix

            if open_unix % M5_SECONDS != 0:
                inventory.open_alignment_error_count += 1
            if close_unix - open_unix != M5_SECONDS:
                inventory.close_span_error_count += 1
            if open_unix in seen_opens:
                inventory.duplicate_open_count += 1
            seen_opens.add(open_unix)

            if previous_open is not None:
                step = open_unix - previous_open
                if step <= 0:
                    inventory.backwards_step_count += 1
                elif step != M5_SECONDS:
                    inventory.non_m5_forward_step_count += 1
                    if inventory.largest_forward_gap_seconds is None or step > inventory.largest_forward_gap_seconds:
                        inventory.largest_forward_gap_seconds = step
            previous_open = open_unix

            contract_values.add(row.get("contract_symbol", ""))
            broker_values.add(row.get("broker_symbol", ""))
            timeframe_values.add(row.get("timeframe", ""))
            price_basis_values.add(row.get("price_basis", ""))
            timezone_status_values.add(row.get("timezone_status", ""))

    inventory.first_open_utc = unix_to_utc(inventory.first_open_unix)
    inventory.last_open_utc = unix_to_utc(inventory.last_open_unix)
    inventory.contract_symbol_values = sorted_values(contract_values)
    inventory.broker_symbol_values = sorted_values(broker_values)
    inventory.timeframe_values = sorted_values(timeframe_values)
    inventory.price_basis_values = sorted_values(price_basis_values)
    inventory.timezone_status_values = sorted_values(timezone_status_values)


def compare_manifest(manifest: dict[str, object], inventory: SymbolInventory) -> None:
    checks = (
        ("row_count", inventory.row_count),
        ("resolved_first_open_unix", inventory.first_open_unix),
        ("resolved_last_open_unix", inventory.last_open_unix),
        ("contract_symbol", inventory.contract_symbol),
        ("broker_symbol", inventory.expected_broker_symbol),
        ("timeframe", "M5"),
    )
    for key, expected in checks:
        observed = manifest.get(key)
        if observed != expected:
            inventory.manifest_mismatches.append(f"{key}: manifest={observed!r}, observed={expected!r}")


def finish_symbol_status(inventory: SymbolInventory) -> None:
    if inventory.csv_status != "ok":
        inventory.status = "missing_or_ambiguous_csv"
        return
    if inventory.missing_columns:
        inventory.status = "invalid_missing_columns"
        return
    if inventory.manifest_status == "mismatch":
        inventory.status = "manifest_mismatch"
        return
    if inventory.open_alignment_error_count or inventory.close_span_error_count or inventory.duplicate_open_count:
        inventory.status = "csv_timing_issue"
        return
    if inventory.contract_symbol_values != [inventory.contract_symbol]:
        inventory.status = "contract_symbol_mismatch"
        return
    if inventory.expected_broker_symbol not in inventory.broker_symbol_values:
        inventory.status = "broker_symbol_mismatch"
        return
    if inventory.timeframe_values != ["M5"]:
        inventory.status = "timeframe_mismatch"
        return
    inventory.status = "usable_raw_inventory"


def inspect_symbol(raw_root: Path, expected: SymbolExpectation, repo_root: Path) -> SymbolInventory:
    symbol_dir = raw_root / expected.contract_symbol
    inventory = SymbolInventory(
        contract_symbol=expected.contract_symbol,
        expected_broker_symbol=expected.broker_symbol,
        symbol_dir=repo_relative(symbol_dir, repo_root),
        status="unchecked",
        csv_status="unchecked",
        manifest_status="unchecked",
    )

    if not symbol_dir.exists():
        inventory.csv_status = "missing_symbol_dir"
        inventory.manifest_status = "missing_symbol_dir"
        finish_symbol_status(inventory)
        return inventory

    csv_files = sorted(symbol_dir.glob("*.csv"))
    manifest_files = sorted(symbol_dir.glob("*.manifest.json"))

    if len(csv_files) != 1:
        inventory.csv_status = "missing" if not csv_files else "multiple"
        inventory.notes.append(f"csv_file_count={len(csv_files)}")
    else:
        inventory.csv_status = "ok"
        inspect_csv(csv_files[0], inventory, repo_root)

    if len(manifest_files) != 1:
        inventory.manifest_status = "missing" if not manifest_files else "multiple"
        inventory.notes.append(f"manifest_file_count={len(manifest_files)}")
    else:
        inventory.manifest_path = repo_relative(manifest_files[0], repo_root)
        inventory.manifest_sha256 = file_sha256(manifest_files[0])
        try:
            manifest = read_manifest(manifest_files[0])
            compare_manifest(manifest, inventory)
            inventory.manifest_status = "mismatch" if inventory.manifest_mismatches else "ok"
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            inventory.manifest_status = "unreadable"
            inventory.notes.append(f"manifest_unreadable={exc}")

    finish_symbol_status(inventory)
    return inventory


def build_inventory(
    raw_root: Path,
    expected_symbols: Iterable[SymbolExpectation] = DEFAULT_EXPECTED_SYMBOLS,
    repo_root: Path | None = None,
) -> dict[str, object]:
    repo_root = repo_root or Path.cwd()
    raw_root = raw_root.resolve()
    expected = tuple(expected_symbols)
    symbols = [inspect_symbol(raw_root, symbol, repo_root) for symbol in expected]
    expected_names = {symbol.contract_symbol for symbol in expected}
    discovered_dirs = sorted(path.name for path in raw_root.iterdir() if path.is_dir()) if raw_root.exists() else []
    extra_symbol_dirs = [name for name in discovered_dirs if name not in expected_names]

    usable = [symbol for symbol in symbols if symbol.status == "usable_raw_inventory"]
    first_values = [symbol.first_open_unix for symbol in usable if symbol.first_open_unix is not None]
    last_values = [symbol.last_open_unix for symbol in usable if symbol.last_open_unix is not None]
    common_first = max(first_values) if first_values else None
    common_last = min(last_values) if last_values else None
    us100 = next((symbol for symbol in symbols if symbol.contract_symbol == "US100"), None)

    summary = {
        "inventory_version": "SPACESONAR_X_US100_RAW_M5_INVENTORY_V1",
        "generated_at_utc": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "raw_root": repo_relative(raw_root, repo_root),
        "expected_symbol_count": len(expected),
        "discovered_symbol_dirs": discovered_dirs,
        "extra_symbol_dirs": extra_symbol_dirs,
        "usable_symbol_count": len(usable),
        "non_usable_symbols": [symbol.contract_symbol for symbol in symbols if symbol.status != "usable_raw_inventory"],
        "symbols_with_manifest_mismatch": [
            symbol.contract_symbol for symbol in symbols if symbol.manifest_status == "mismatch"
        ],
        "symbols_with_timing_issue": [
            symbol.contract_symbol
            for symbol in symbols
            if symbol.open_alignment_error_count or symbol.close_span_error_count or symbol.duplicate_open_count
        ],
        "common_first_open_unix": common_first,
        "common_last_open_unix": common_last,
        "common_first_open_utc": unix_to_utc(common_first),
        "common_last_open_utc": unix_to_utc(common_last),
        "us100_first_open_utc": us100.first_open_utc if us100 else None,
        "us100_last_open_utc": us100.last_open_utc if us100 else None,
        "timezone_status_values": sorted(
            {value for symbol in symbols for value in symbol.timezone_status_values}
        ),
        "status": "complete" if len(usable) == len(expected) and not extra_symbol_dirs else "attention_needed",
        "boundary": (
            "Raw inventory only. This does not claim feature readiness, model readiness, "
            "runtime authority, or operating promotion."
        ),
    }
    return {
        "summary": summary,
        "symbols": [asdict(symbol) for symbol in symbols],
    }


def render_markdown(inventory: dict[str, object]) -> str:
    summary = inventory["summary"]
    symbols = inventory["symbols"]
    assert isinstance(summary, dict)
    assert isinstance(symbols, list)

    lines = [
        "# Raw M5 Inventory",
        "",
        "## Summary",
        "",
        f"- status: `{summary['status']}`",
        f"- raw_root: `{summary['raw_root']}`",
        f"- expected_symbol_count: `{summary['expected_symbol_count']}`",
        f"- usable_symbol_count: `{summary['usable_symbol_count']}`",
        f"- common_first_open_utc: `{summary['common_first_open_utc']}`",
        f"- common_last_open_utc: `{summary['common_last_open_utc']}`",
        f"- us100_first_open_utc: `{summary['us100_first_open_utc']}`",
        f"- us100_last_open_utc: `{summary['us100_last_open_utc']}`",
        "",
        "## Boundary",
        "",
        "This is a raw inventory only. It does not claim feature readiness, model readiness, runtime authority, or operating promotion.",
        "",
        "## Symbol Table",
        "",
        "| symbol | broker | status | rows | first open | last open | manifest | timing notes |",
        "|---|---|---:|---:|---|---|---|---|",
    ]
    for symbol in symbols:
        assert isinstance(symbol, dict)
        timing = []
        if symbol["open_alignment_error_count"]:
            timing.append(f"open_align={symbol['open_alignment_error_count']}")
        if symbol["close_span_error_count"]:
            timing.append(f"close_span={symbol['close_span_error_count']}")
        if symbol["duplicate_open_count"]:
            timing.append(f"dupe={symbol['duplicate_open_count']}")
        if symbol["non_m5_forward_step_count"]:
            timing.append(f"gaps={symbol['non_m5_forward_step_count']}")
        timing_text = ", ".join(timing) if timing else "ok"
        lines.append(
            "| "
            f"`{symbol['contract_symbol']}` | "
            f"`{symbol['expected_broker_symbol']}` | "
            f"`{symbol['status']}` | "
            f"{symbol['row_count']} | "
            f"`{symbol['first_open_utc']}` | "
            f"`{symbol['last_open_utc']}` | "
            f"`{symbol['manifest_status']}` | "
            f"{timing_text} |"
        )

    lines.extend(
        [
            "",
            "## Read Notes",
            "",
            "- `gaps` are forward gaps that may come from holidays, sessions, or symbol trading-hour differences.",
            "- `ok` means the file shape and manifest match observed values.",
            "- Timezone meaning may still inherit `UNRESOLVED_REQUIRES_MANUAL_BINDING` from the raw export.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(inventory: dict[str, object], output_dir: Path, raw_root: Path, repo_root: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "raw_m5_inventory.json").write_text(
        json.dumps(inventory, indent=2), encoding="utf-8"
    )
    (output_dir / "raw_m5_inventory.md").write_text(render_markdown(inventory), encoding="utf-8-sig")

    with (output_dir / "symbol_inventory.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "contract_symbol",
                "expected_broker_symbol",
                "status",
                "csv_status",
                "manifest_status",
                "row_count",
                "first_open_utc",
                "last_open_utc",
                "non_m5_forward_step_count",
                "largest_forward_gap_seconds",
                "csv_path",
                "manifest_path",
            ),
        )
        writer.writeheader()
        for symbol in inventory["symbols"]:
            writer.writerow({key: symbol.get(key) for key in writer.fieldnames})

    manifest = {
        "run_id": output_dir.name,
        "lane": "evidence",
        "work_scope": "raw_m5_inventory",
        "command": (
            "python foundation/collectors/raw_m5_inventory.py "
            f"--raw-root {repo_relative(raw_root, repo_root)} "
            f"--output-dir {output_dir.as_posix()}"
        ),
        "outputs": [
            (output_dir / "raw_m5_inventory.json").as_posix(),
            (output_dir / "raw_m5_inventory.md").as_posix(),
            (output_dir / "symbol_inventory.csv").as_posix(),
        ],
        "judgment_boundary": (
            "Evidence run only. No model readiness, runtime authority, or operating promotion."
        ),
    }
    (output_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a raw M5 inventory for active SpaceSonar US100 source files.")
    parser.add_argument("--raw-root", default="data/raw/mt5_bars/m5")
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path.cwd()
    raw_root = Path(args.raw_root)
    inventory = build_inventory(raw_root, repo_root=repo_root)
    write_outputs(inventory, Path(args.output_dir), raw_root, repo_root)
    print(json.dumps(inventory["summary"], indent=2))


if __name__ == "__main__":
    main()
