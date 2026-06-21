from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import MetaTrader5 as mt5


TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}

TRADE_MODE = {
    getattr(mt5, "SYMBOL_TRADE_MODE_DISABLED", -1): "disabled",
    getattr(mt5, "SYMBOL_TRADE_MODE_LONGONLY", -1): "long_only",
    getattr(mt5, "SYMBOL_TRADE_MODE_SHORTONLY", -1): "short_only",
    getattr(mt5, "SYMBOL_TRADE_MODE_CLOSEONLY", -1): "close_only",
    getattr(mt5, "SYMBOL_TRADE_MODE_FULL", -1): "full",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe broker-native MT5 symbol contract fields for SpaceSonar research."
    )
    parser.add_argument("--symbol", action="append", default=["US100"], help="Exact broker symbol to probe.")
    parser.add_argument(
        "--discover-term",
        action="append",
        default=["US100", "BTC", "XAU", "GOLD"],
        help="Case-insensitive symbol-name substring to include in discovery output.",
    )
    parser.add_argument("--timeframe", default="M5", choices=sorted(TIMEFRAME_MAP), help="Recent bar timeframe.")
    parser.add_argument("--recent-bars", type=int, default=5, help="Recent bars to request per symbol.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory. Defaults to lab/runs/symbol_contract_probe_<utc_timestamp>.",
    )
    return parser.parse_args()


def as_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if hasattr(value, "_asdict"):
        return dict(value._asdict())
    return dict(value)


def serializable(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def normalize_dict(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if data is None:
        return None
    return {key: serializable(value) for key, value in data.items()}


def discover_symbols(terms: list[str]) -> dict[str, list[str]]:
    symbols = mt5.symbols_get()
    if symbols is None:
        return {term: [] for term in terms}
    names = sorted(symbol.name for symbol in symbols)
    discovered: dict[str, list[str]] = {}
    for term in terms:
        needle = term.upper()
        discovered[term] = [name for name in names if needle in name.upper()]
    return discovered


def pick_contract_fields(info: dict[str, Any] | None) -> dict[str, Any] | None:
    if info is None:
        return None
    keys = [
        "name",
        "path",
        "description",
        "custom",
        "visible",
        "select",
        "currency_base",
        "currency_profit",
        "currency_margin",
        "digits",
        "point",
        "spread",
        "spread_float",
        "trade_mode",
        "trade_calc_mode",
        "trade_contract_size",
        "trade_tick_size",
        "trade_tick_value",
        "trade_tick_value_profit",
        "trade_tick_value_loss",
        "volume_min",
        "volume_max",
        "volume_step",
        "volume_limit",
        "trade_stops_level",
        "trade_freeze_level",
        "order_mode",
        "filling_mode",
        "expiration_mode",
        "swap_mode",
        "swap_long",
        "swap_short",
        "swap_rollover3days",
        "margin_initial",
        "margin_maintenance",
    ]
    contract = {key: info.get(key) for key in keys if key in info}
    if "trade_mode" in contract:
        contract["trade_mode_name"] = TRADE_MODE.get(contract["trade_mode"], "unknown")
    return contract


def recent_bars(symbol: str, timeframe: int, count: int) -> list[dict[str, Any]]:
    bars = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if bars is None:
        return []
    result: list[dict[str, Any]] = []
    for row in bars:
        item = {name: serializable(row[name]) for name in row.dtype.names}
        if "time" in item:
            item["time_utc"] = datetime.fromtimestamp(int(item["time"]), tz=UTC).isoformat().replace("+00:00", "Z")
        result.append(item)
    return result


def probe_symbol(symbol: str, timeframe: int, bar_count: int, now_utc: datetime) -> dict[str, Any]:
    before_info = normalize_dict(as_dict(mt5.symbol_info(symbol)))
    select_success = False
    if before_info is not None:
        select_success = bool(before_info.get("visible")) or bool(mt5.symbol_select(symbol, True))
    after_info = normalize_dict(as_dict(mt5.symbol_info(symbol)))
    tick = normalize_dict(as_dict(mt5.symbol_info_tick(symbol))) if after_info else None
    bars = recent_bars(symbol, timeframe, bar_count) if after_info else []

    tick_has_quote = bool(tick and tick.get("time") and (tick.get("bid") or tick.get("ask") or tick.get("last")))
    tick_age_seconds = None
    if tick_has_quote:
        tick_age_seconds = int(now_utc.timestamp()) - int(tick["time"])

    latest_bar_time = max((int(row["time"]) for row in bars), default=None)
    last_bar_age_seconds = None
    if latest_bar_time is not None:
        last_bar_age_seconds = int(now_utc.timestamp()) - latest_bar_time

    if after_info is None:
        contract_judgment = "symbol_not_found"
    elif not select_success:
        contract_judgment = "symbol_found_but_not_selectable"
    elif not tick_has_quote:
        contract_judgment = "contract_available_live_tick_not_proven"
    else:
        contract_judgment = "contract_available_tick_observed"

    return {
        "symbol": symbol,
        "found": after_info is not None,
        "select_success": select_success,
        "contract": pick_contract_fields(after_info),
        "tick": tick,
        "recent_bars": bars,
        "observability": {
            "tick_object_present": tick is not None,
            "tick_has_quote": tick_has_quote,
            "recent_bar_count": len(bars),
            "tick_age_seconds": tick_age_seconds,
            "last_bar_age_seconds": last_bar_age_seconds,
            "latest_bar_time_utc": (
                datetime.fromtimestamp(latest_bar_time, tz=UTC).isoformat().replace("+00:00", "Z")
                if latest_bar_time is not None
                else None
            ),
            "contract_judgment": contract_judgment,
            "live_chart_status": "requires_market_open_observation",
            "session_hours_status": "not_exposed_by_metatrader5_python_api",
            "commission_status": "not_exposed_by_symbol_info_python_api",
        },
    }


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Symbol Contract Probe",
        "",
        f"- generated_at_utc: `{payload['generated_at_utc']}`",
        f"- account_server: `{payload['environment'].get('account_server')}`",
        f"- account_currency: `{payload['environment'].get('account_currency')}`",
        f"- account_leverage: `{payload['environment'].get('account_leverage')}`",
        f"- timeframe: `{payload['timeframe']}`",
        "",
        "## Probed Symbols",
        "",
    ]
    for symbol in payload["symbols"]:
        contract = symbol.get("contract") or {}
        obs = symbol.get("observability") or {}
        lines.extend(
            [
                f"### {symbol['symbol']}",
                "",
                f"- found: `{symbol['found']}`",
                f"- select_success: `{symbol['select_success']}`",
                f"- description: `{contract.get('description')}`",
                f"- path: `{contract.get('path')}`",
                f"- digits / point: `{contract.get('digits')}` / `{contract.get('point')}`",
                f"- tick_size / tick_value: `{contract.get('trade_tick_size')}` / `{contract.get('trade_tick_value')}`",
                f"- contract_size: `{contract.get('trade_contract_size')}`",
                f"- spread / spread_float: `{contract.get('spread')}` / `{contract.get('spread_float')}`",
                f"- trade_mode: `{contract.get('trade_mode_name')}` (`{contract.get('trade_mode')}`)",
                f"- volume min/max/step/limit: `{contract.get('volume_min')}` / `{contract.get('volume_max')}` / `{contract.get('volume_step')}` / `{contract.get('volume_limit')}`",
                f"- stops/freeze level: `{contract.get('trade_stops_level')}` / `{contract.get('trade_freeze_level')}`",
                f"- swap long/short/mode: `{contract.get('swap_long')}` / `{contract.get('swap_short')}` / `{contract.get('swap_mode')}`",
                f"- tick_object_present: `{obs.get('tick_object_present')}`",
                f"- tick_has_quote: `{obs.get('tick_has_quote')}`",
                f"- recent_bar_count: `{obs.get('recent_bar_count')}`",
                f"- tick_age_seconds: `{obs.get('tick_age_seconds')}`",
                f"- last_bar_age_seconds: `{obs.get('last_bar_age_seconds')}`",
                f"- latest_bar_time_utc: `{obs.get('latest_bar_time_utc')}`",
                f"- contract_judgment: `{obs.get('contract_judgment')}`",
                f"- commission_status: `{obs.get('commission_status')}`",
                f"- session_hours_status: `{obs.get('session_hours_status')}`",
                "",
            ]
        )

    lines.extend(["## Discovery", ""])
    for term, names in payload["discovery"].items():
        shown = ", ".join(f"`{name}`" for name in names[:80])
        suffix = "" if len(names) <= 80 else f" ... ({len(names)} total)"
        lines.append(f"- {term}: {shown}{suffix}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    timeframe = TIMEFRAME_MAP[args.timeframe]
    generated_at = datetime.now(tz=UTC)
    output_dir = Path(args.output_dir or f"lab/runs/symbol_contract_probe_{generated_at.strftime('%Y%m%dT%H%M%SZ')}")
    output_dir.mkdir(parents=True, exist_ok=True)

    if not mt5.initialize():
        raise RuntimeError(f"Failed to initialize MetaTrader5: {mt5.last_error()}")

    try:
        terminal = normalize_dict(as_dict(mt5.terminal_info())) or {}
        account = normalize_dict(as_dict(mt5.account_info())) or {}
        payload = {
            "version": "spacesonar_symbol_contract_probe_v1",
            "generated_at_utc": generated_at.isoformat().replace("+00:00", "Z"),
            "timeframe": args.timeframe,
            "environment": {
                "terminal_name": terminal.get("name"),
                "terminal_company": terminal.get("company"),
                "terminal_connected": terminal.get("connected"),
                "terminal_trade_allowed": terminal.get("trade_allowed"),
                "account_server": account.get("server"),
                "account_currency": account.get("currency"),
                "account_leverage": account.get("leverage"),
                "account_trade_mode": account.get("trade_mode"),
            },
            "symbols": [probe_symbol(symbol, timeframe, args.recent_bars, generated_at) for symbol in args.symbol],
            "discovery": discover_symbols(args.discover_term),
            "claim_boundary": {
                "runtime_authority": False,
                "economics_pass": False,
                "live_readiness": False,
                "meaning": "Broker symbol contract and observability probe only.",
            },
        }
        json_path = output_dir / "symbol_contract_probe.json"
        markdown_path = output_dir / "symbol_contract_probe.md"
        json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        write_markdown(markdown_path, payload)
        print(json.dumps({"status": "ok", "json_path": str(json_path), "markdown_path": str(markdown_path)}, indent=2))
        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
