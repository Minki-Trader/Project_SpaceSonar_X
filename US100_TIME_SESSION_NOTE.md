# US100 Time And Session Note

This note records how SpaceSonar should interpret US100 time axis and session context before experiments.

Status: observation note only. This is not runtime authority, economics pass, live readiness, or an official broker session-table contract.

## Sources

- US100 session bar probe: `lab/runs/us100_session_probe_20260620T151735Z/us100_session_bar_probe.json`
- US100 symbol note: `US100_BROKER_SYMBOL_NOTE.md`
- Probe range: `2026-05-06T15:17:35Z` to `2026-06-20T15:17:35Z`
- Probe row count: `8840` M5 bars

## Canonical Time Axis

- canonical storage time: `UTC`
- MT5 API time basis: Unix seconds from `MetaTrader5.copy_rates_*`
- bar timestamp meaning: bar open time
- bar close rule: `bar_open_time + timeframe`
- active timeframe observed here: `M5`
- closed-bar rule: use closed bars for features and labels
- partial bar allowed: `false`

Development effect:

- Store and join bars by UTC.
- Treat M5 `time` as the bar-open timestamp.
- A feature for a bar must use information available no later than that bar close unless the experiment explicitly declares another boundary.

## Timezone Views

### UTC

- role: canonical storage, merge, split, and artifact identity time
- reason: avoids mixing broker display time, New York market time, and Korean display time

### MT5 Server Time

- role: terminal display/runtime context
- status: not used as canonical storage until explicitly probed
- note: do not assume MT5 display time equals UTC only from UI appearance

### America/New_York

- role: US market session context
- timezone id: `America/New_York`
- DST rule: use timezone database conversion, not fixed UTC offsets

US cash session context:

- cash session: `09:30` to `16:00` New York time
- premarket: context-only until a specific experiment needs it
- after-hours: context-only until a specific experiment needs it

Development effect:

- `US cash session` is not the same as `US100 tradable/bar-available session`.
- Use New York time only to derive market-state features such as cash open, cash close, premarket, and after-hours.
- Do not hard-code cash session as a fixed UTC window because DST shifts it.

### Asia/Seoul

- role: user display only
- timezone id: `Asia/Seoul`
- note: do not use KST as model merge or split identity unless explicitly required.

## Observed US100 Bar Availability

This is empirical M5 bar availability from the local FPMarkets MT5 terminal, not an official broker session table.

Observed regular UTC shape:

- normal weekdays: `01:00` to `23:55`
- normal full-day M5 bars: `276`
- observed internal large gaps: `0`

Observed regular KST shape:

- normal weekdays: `10:00` to next day `08:55`

Observed early-close candidates:

- `2026-05-25`: `01:00` to `19:55` UTC, `228` bars
- `2026-06-19`: `01:00` to `19:55` UTC, `228` bars

Development effect:

- Treat early-close candidates as normal observed short sessions until confirmed.
- Do not fill missing late bars on these days without a session-calendar decision.
- Do not call them data defects unless a later source contradicts the observed session pattern.

## Holiday And Early Close Handling

Initial state:

- official holiday calendar: not yet bound
- official early-close calendar: not yet bound
- current evidence: empirical MT5 bar availability only

Required distinction:

- actual holiday or early close: normal market/session condition
- broker-specific early close: broker session condition
- data collection failure: data defect
- wrong session filter: implementation defect

Development rule:

- Keep `early_close_candidate` separate from `missing_data`.
- Confirm holidays or early closes with an official or verified market calendar before making calendar-based claims.
- If a run excludes holiday or early-close candidates, record the exclusion list and reason.

## Current Claim Boundary

- Usable for early data integrity checks and session-feature design.
- Usable to avoid accidental fixed-UTC cash-session coding.
- Not sufficient for official exchange holiday authority.
- Not sufficient for runtime/economics/live-readiness claims.
