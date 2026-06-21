# Collectors

Reusable source loaders, export readers, and raw normalization helpers.

Do not place one-off experiment notes here.

Current tools:

- `export_mt5_m5_bars.py`: exports active broker-native `M5` bars from MetaTrader 5. Start/end UTC windows are explicit inputs. Extra live-chart symbols can be exported with repeated `--symbol CONTRACT=BROKER` arguments only after local MT5 availability is proven and recorded with `--aux-evidence-id`.
- `raw_m5_inventory.py`: inspects active `US100` raw `M5` CSV files and row inventory.
