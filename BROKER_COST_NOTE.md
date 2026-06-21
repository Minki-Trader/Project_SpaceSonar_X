# Broker Cost Note

This note records broker cost observations extracted from user-provided MT5 Tester `Groups` files.

Status: observation note only. This is not runtime authority, economics pass, live readiness, or a complete future commission schedule.

## Sources

Source folder:

`C:\Users\awdse\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Profiles\Tester\Groups`

Files reviewed:

- `ReportHistory-<account>.xlsx`
  - SHA256: `2ae962f32fb427eedfcb66c8df35c7a246d7f3237bc2cecf2ebd2ec69b63a626`
  - report timestamp: `2026.06.21 00:24`
  - account context in file: `USD`, `FPMarketsSC-Live`, `real`, `Hedge`
- `FPMarketsSC-Live_real.txt`
- `ZZ.txt`

Privacy handling: account number, account name, ticket ids, order ids, and deal ids are intentionally omitted from this note.

## US100 Cost Observation From Report History

The workbook contains `US100` trade history.

Position-level rows:

- symbol: `US100`
- row count: `92`
- open/close time span: `2026.01.12 18:10:37.089` to `2026.03.19 08:44:44.455`
- volume range: `0.01` to `0.36`
- total volume: `4.81`
- commission sum: `0.00`
- commission unique values: `0.00`
- swap sum: `-0.75`
- swap unique values: `0.00`, `-0.04`, `-0.71`
- profit sum before commission/swap identity adjustment: `-48.11`

Deal-level rows:

- symbol: `US100`
- row count: `185`
- commission sum: `0.00`
- fee sum: `0.00`
- swap sum: `-0.75`
- swap unique values: `0.00`, `-0.04`, `-0.71`
- profit sum: `-48.11`

Observed non-zero swap events:

- `2026.01.13 01:02:30.562`, out deal, volume `0.01`, swap `-0.04`
- `2026.02.02 22:47:25.835`, out deal, volume `0.06`, swap `-0.71`

## Tester Group Commission Files

The reviewed Tester `Groups` text files contain explicit commission rules for:

- `Equity CFD HK\*`
- `Equity CFD US\*`
- `Equity CFD EU\*`
- `Equity CFD UK\*`
- `ETF\*`

No explicit `US100` commission group rule was found in those text files.

## Interpretation

- For the reviewed `US100` report history sample, observed commission is `0.00`.
- For the reviewed `US100` report history sample, observed fee is `0.00`.
- Swap is an active cost field and appeared as non-zero on overnight or multi-day holds.
- The reviewed Tester group files do not show a separate explicit `US100` commission rule.
- Treat this as observed broker/account/tester evidence for the reviewed sample, not as a permanent universal fee schedule.

## US100 Estimated Swap Model

Use the current MT5 `symbol_info("US100")` swap settings as the development estimate when a report-level `Swap` value is not available.

- estimated long swap: `-3.94`
- estimated short swap: `1.34`
- swap mode: `2`
- 3-day rollover setting: `5`
- profit currency: `USD`

Priority:

1. Actual Strategy Tester or account-history `Swap` column when available.
2. Estimated swap from current MT5 symbol settings when no actual report value exists.
3. Explicit `swap_excluded` only when an experiment intentionally excludes overnight/multi-day holding.

## Current Development Use

- For early US100 Python research, commission can be initialized as observed `0.00` with a clear evidence note.
- Use estimated swap from current MT5 symbol settings when modeling positions that can cross rollover.
- For same-day intraday tests, swap may be zero in many rows, but this must not be assumed for positions held across rollover.
- Before economics claims, re-check costs against the specific Strategy Tester report or live/account statement for that run.
