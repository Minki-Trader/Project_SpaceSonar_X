# US100 Broker Symbol Note

This note records the current US100 broker-symbol facts found from the local FPMarkets MT5 terminal.

Status: observation note only. This is not runtime authority, economics pass, live readiness, or an operating contract.

## Probe Sources

- Symbol contract probe: `lab/runs/symbol_contract_probe_20260620T151302Z/symbol_contract_probe.json`
- Session bar probe: `lab/runs/us100_session_probe_20260620T151735Z/us100_session_bar_probe.json`
- Terminal/account context at probe time:
  - account server: `FPMarketsSC-Live`
  - account currency: `USD`
  - account leverage: `100`
  - timeframe checked: `M5`

## Exact Symbol

- broker symbol: `US100`
- description: `US Tech 100 Index Cash`
- MT5 path: `Indices\US100`
- trade mode: `full`

## Contract Fields

- digits: `2`
- point: `0.01`
- tick size: `0.01`
- tick value: `0.01`
- contract size: `1.0`
- spread at probe: `260` points
- spread type: floating
- price-distance meaning of probe spread: `260 * 0.01 = 2.60`
- min lot: `0.01`
- max lot: `200.0`
- lot step: `0.01`
- volume limit: `0.0`
- stops level: `0`
- freeze level: `0`
- swap long: `-3.94`
- swap short: `1.34`
- swap mode: `2`
- swap rollover 3 days: `5`

## Observed Bar Availability

Source: actual `US100` M5 bars observed over `2026-05-06T15:17:35Z` to `2026-06-20T15:17:35Z`.

UTC observed regular shape:

- normal weekdays: `01:00` to `23:55`
- normal full-day M5 bars: `276`
- observed internal large gaps: `0`

KST observed regular shape:

- normal weekdays: `10:00` to next day `08:55`

Observed shortened days in this sample:

- `2026-05-25`: `01:00` to `19:55` UTC, `228` bars
- `2026-06-19`: `01:00` to `19:55` UTC, `228` bars

These shortened days should be treated as holiday or early-close candidates until confirmed by broker/session evidence.

## Missing Or Limited Fields

- Commission was not exposed by the `MetaTrader5` Python `symbol_info` API.
- A separate broker cost observation exists in `BROKER_COST_NOTE.md`: reviewed `US100` report history showed `0.00` commission and `0.00` fee across the sample, with total observed swap `-0.75`.
- Official broker session table was not exposed by the `MetaTrader5` Python API.
- The session times above are empirical bar-availability observations, not an official broker session-table contract.

## Development Use

- Use `US100` as the exact broker symbol until contradicted by newer local MT5 evidence.
- Treat spread as floating; do not hard-code the probe value as a permanent cost.
- Use estimated swap from current MT5 symbol settings when no actual report `Swap` value exists: long `-3.94`, short `1.34`, rollover-3-days setting `5`.
- For Python research, keep M5 bar timestamps explicit as bar-open UTC unless another contract says otherwise.
- Before runtime or economics claims, re-check symbol fields and session behavior near the target test period.
