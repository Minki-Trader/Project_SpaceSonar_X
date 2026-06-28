---
name: spacesonar-performance-attribution
description: Decompose KPI changes by time, sample, tier, feature, threshold, model, trade shape, drawdown, regime.
---

# SpaceSonar Performance Attribution

Use this skill when a KPI-bearing result is judged, a campaign/wave closeout is written, a result is better, worse, flat, surprising, unstable, or used to choose the next experiment.

## Required Output

- `kpi_scope`: proxy, MT5 runtime, proxy-vs-MT5 comparison, or mixed
- `tested_factor`: changed experimental item such as feature, target, threshold, model, decision rule, holding/risk rule, data scope, or runtime surface
- `observed_change`: KPI or behavior that changed
- `comparison_baseline`: what it changed against
- `directional_effect_hypothesis`: what effect the tested factor appears to have, stated as an exploratory hypothesis
- `likely_drivers`: threshold, model, feature, data scope, tier mix, trade frequency, risk shape, or market regime
- `segment_checks`: time period, tier, direction, volatility, session, drawdown cluster, or trade bucket checks performed or missing
- `trade_shape`: count, win rate, payoff ratio, average win/loss, drawdown, concentration, and exposure when available
- `candidate_effect_size_vs_noise`: whether the observed KPI movement is large enough to matter against sample noise and segment instability
- `alternative_explanations`: possible non-signal explanations
- `evidence_limits`: missing KPI fields, missing MT5 runtime evidence, small sample, noisy segment, or parser/runtime limits
- `failure_or_negative_salvage_value`: what the result still teaches if it is negative, flat, invalid, or inconclusive
- `attribution_confidence`: high, medium, low, inconclusive, or invalid
- `next_probe`: smallest follow-up that can confirm or reject the explanation, plus whether the next move is broaden, rotate, narrow, repair, follow through in runtime, synthesize, or stop

## Guardrails

- Do not stop at "what the KPI was"; always connect `tested_factor -> observed_change -> directional_effect_hypothesis -> next_probe`.
- Treat attribution as exploratory unless the comparison has matched scope, controls, enough samples, and matching proxy/runtime evidence.
- Keep proxy KPI interpretation and MT5 runtime KPI interpretation separate; compare them only for runs that actually reached MT5 runtime.
- Do not say a model improved just because one headline KPI improved.
- Do not hide a worse drawdown, trade concentration, or sample shrink behind profit.
- Do not over-explain noise; mark low-confidence attribution when evidence is thin.
- Negative, flat, invalid, and inconclusive results must still state whether they create a reusable clue, a boundary, or a stop condition.

## Operational Stability Floor

- Default `validation_depth` is `writer_scope_smoke`; broad validation commands are not progress-loop defaults.
- If this skill mutates, closes, judges, or routes a record, follow `docs/agent_control/writer_scope_operating_contract.yaml` and record `writer_contract_version`, source-of-truth paths, writer-owned outputs, non-pytest smokes, skipped broad validations, escalation reason, self-check, claim boundary, forbidden claims, blocker or reopen condition, and next action.
- A discovered gap becomes an owner writer, manifest, policy, or scoped lint repair before pytest, project validate, full regression, evidence graph, broad hash resync, or global registry regeneration.
