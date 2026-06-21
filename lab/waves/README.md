# Waves

`lab/waves/` stores allocation batches.

A wave is not a strategy class, feature family, model family, or result claim. A wave only records which campaigns, sweeps, and run budgets are funded in one execution batch.

Campaigns are not physically nested under waves. A wave owns allocation and budget by reference through:

- `wave_allocation.yaml`
- `campaign_refs.csv`

The campaign source of truth remains `lab/campaigns/<campaign_id>/campaign_manifest.yaml`. This lets a campaign continue across waves without moving or duplicating its evidence identity.

Evidence stays in `lab/runs/<run_id>/`. Runtime attempts stay in `runtime/mt5_attempts/<attempt_id>/`.
