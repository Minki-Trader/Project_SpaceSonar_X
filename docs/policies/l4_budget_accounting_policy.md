# L4 Budget Accounting Policy

L4 budget is counted by `validation_research_oos_pair`, not by raw MT5
Strategy Tester execution count.

One L4 pair means:

- one declared campaign/cell/runtime-surface target
- one `validation` Strategy Tester execution
- one `research_oos` Strategy Tester execution
- both executions belong to the same pair identity

The following are physical execution counts, not budget burn:

- `prepared_attempt_count`
- `executed_attempt_count`
- `runtime_probe_complete_count`
- `expected_attempt_count`

The following are L4 budget counts:

- `l4_pair_budget`
- `l4_pair_count`
- `l4_pair_complete_count`
- `expected_pair_group_count`
- `pair_group_count`
- `pair_groups_complete`

Decision replay may use the same validation/research_oos pair shape, but it
must stay in a declared decision-replay pair ledger unless a wave explicitly
budgets it with standard L4.

Historical numeric fields such as `formal_mt5_strategy_tester_runs` are
superseded by pair accounting when a wave has an active L4 budget amendment or
an `l4_budget_unit` field.
