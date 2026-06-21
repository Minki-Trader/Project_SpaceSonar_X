# KPI Measurement Standard

KPI records measure what a run actually tested. They do not create operating meaning by themselves.

## Scoreboards

- `structural_scout`: early structure or idea check
- `task_surface_scout`: whether an input/target/decision shape is worth further work
- `signal_quality`: hit rate, coverage, long/short mix, probability quality, calibration
- `trading_shape`: net profit, profit factor, expectancy, trade count, win rate, holding time
- `risk_shape`: max drawdown, recovery factor, time under water, exposure concentration
- `execution_shape`: fill rate, skip/reject count, spread/slippage, tester/runtime mismatch
- `runtime_probe`: Strategy Tester reports, EA inputs, bundle identity, runtime surface identity

## Rules

- Compare only lanes that tested the same surface, period, cost model, and claim boundary.
- Compare task shapes only when their target, horizon or holding logic, decision use, and sample scope are explicit.
- Scout KPI is not promotion KPI.
- Python/proxy KPI is not MT5 runtime evidence.
- A completed runtime report is not an economics pass unless the economics claim and required evidence were defined before the run.
- Missing or out-of-scope rows must not borrow profit, drawdown, trade count, or pass/fail status from another row.

## Input Boundary

Active KPI records must identify the `US100` closed-bar input surface used by the run.

If a live-chart auxiliary symbol is used, the KPI record must also name the exact broker symbol, availability evidence, merge policy, and claim boundary.

Do not add KPI dimensions for stale, delayed, offline, or non-updating symbols. Those surfaces are outside active SpaceSonar research and runtime scope.

## MT5 Runtime KPI

When MT5 or Strategy Tester is involved, include a runtime KPI layer:

- attempt id
- bundle id or EA input contract id
- tested period
- symbol and timeframe
- model mode
- deposit and leverage
- report path or missing-report reason
- claim boundary

If profit is discussed, risk and execution KPI must be present. Do not close a positive result on profit alone.
