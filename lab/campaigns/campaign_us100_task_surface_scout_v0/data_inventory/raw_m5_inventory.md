# Raw M5 Inventory

## Summary

- status: `complete`
- raw_root: `data/raw/mt5_bars/m5/wave0_us100_closedbar_surface_cartography_v0`
- expected_symbol_count: `1`
- usable_symbol_count: `1`
- common_first_open_utc: `2022-02-09T01:00:00Z`
- common_last_open_utc: `2026-06-18T23:55:00Z`
- us100_first_open_utc: `2022-02-09T01:00:00Z`
- us100_last_open_utc: `2026-06-18T23:55:00Z`

## Boundary

This is a raw inventory only. It does not claim feature readiness, model readiness, runtime authority, or operating promotion.

## Symbol Table

| symbol | broker | status | rows | first open | last open | manifest | timing notes |
|---|---|---:|---:|---|---|---|---|
| `US100` | `US100` | `usable_raw_inventory` | 308002 | `2022-02-09T01:00:00Z` | `2026-06-18T23:55:00Z` | `ok` | gaps=1137 |

## Read Notes

- `gaps` are forward gaps that may come from holidays, sessions, or symbol trading-hour differences.
- `ok` means the file shape and manifest match observed values.
- Timezone meaning may still inherit `UNRESOLVED_REQUIRES_MANUAL_BINDING` from the raw export.
