---
name: spacesonar-data-integrity
description: Check time axis, timezone, splits, leakage, duplicates, missing rows, and feature-label boundaries.
---

# SpaceSonar Data Integrity

Use this skill whenever work touches datasets, features, labels, splits, bars, timestamps, joins, resampling, training windows, runtime inputs, or KPI interpretation.

## Required Output

- `data_source`: source files, broker feed, runtime output, or generated artifact
- `time_axis`: timestamp meaning, timezone policy, bar close/open convention, and ordering
- `sample_scope`: symbol, timeframe, date range, tiers, rows, and exclusions
- `missing_or_duplicate_check`: whether gaps or duplicates matter here
- `feature_label_boundary`: how future data is prevented from entering features
- `split_boundary`: train, validation, test, WFO, or runtime split meaning
- `leakage_risk`: most likely lookahead or selection-bias path
- `data_hash_or_identity`: file hash, row count, artifact id, or reason unavailable
- `integrity_judgment`: usable, usable_with_boundary, inconclusive, invalid, or blocked

## Guardrails

- Do not trust a profitable result before the time axis and label boundary are named.
- Do not hide timezone assumptions in variable names.
- Do not mix feature and label logic without an explicit boundary and test intent.
- Do not call a result invalid when it is only incomplete; name the missing integrity check.

## Operational Stability Floor

- Default `validation_depth` is `writer_scope_smoke`; broad validation commands are not progress-loop defaults.
- If this skill mutates, closes, judges, or routes a record, follow `docs/agent_control/writer_scope_operating_contract.yaml` and record `writer_contract_version`, source-of-truth paths, writer-owned outputs, non-pytest smokes, skipped broad validations, escalation reason, self-check, claim boundary, forbidden claims, blocker or reopen condition, and next action.
- A discovered gap becomes an owner writer, manifest, policy, or scoped lint repair before pytest, project validate, full regression, evidence graph, broad hash resync, or global registry regeneration.
