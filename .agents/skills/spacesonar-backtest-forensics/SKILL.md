---
name: spacesonar-backtest-forensics
description: Inspect MT5/Strategy Tester settings, reports, trades, costs, and evidence before trusting backtests.
---

# SpaceSonar Backtest Forensics

Use when work creates, reads, compares, packages, or reports MT5 Strategy Tester, broker terminal, or backtest outputs.

## Required Reads

- `foundation/config/mt5_runtime_probe_contract.yaml`
- `configs/mt5/period_profiles/split_set_v0_runtime_periods.yaml`
- `configs/mt5/tester_execution_profile_v0.yaml`

## Required Output

- `tester_identity`: terminal, broker, symbol, timeframe, deposit, leverage, model mode, spread, commission, date range, period profile id, runtime period set id.
- `ea_identity`: EA entrypoint, include module hashes, `.set` file, parameter hash, and model or bundle hash.
- `report_identity`: report path, snapshot path, terminal output path, and hash when available.
- `trade_evidence`: trade count, gross/net result, drawdown, profit factor, and trade list availability.
- `cost_assumptions`: spread, commission, slippage, swap, and missing costs.
- `forensic_checks`: settings drift, missing output, malformed report, wrong period, wrong symbol, wrong model, or missing evidence.
- `runtime_learning_probe_decision`: MT5 action, not-run reason, repair attempts, blocker, and claim effect.
- `backtest_judgment`: usable, usable_with_boundary, inconclusive, invalid, or blocked.

## Guardrails

- Do not trust a report if tester identity is unknown.
- Do not compare tester runs with different cost or modeling assumptions as equal.
- Do not call a backtest reviewed when output path or run identity is missing.
- Do not use tester profit alone as promotion evidence.
- Do not accept proxy_bad, candidate_gate_failed, low_trade_count_expected, long_short_imbalanced, or cost_expensive as an MT5 not-run reason when an actionable runtime surface exists.
- If no actionable runtime surface exists, require repair-attempt evidence before `blocked` or `inconclusive`.
- Missing report output is not runtime probe completion.
- Do not embed standard date windows in this skill. Use the period profile.
