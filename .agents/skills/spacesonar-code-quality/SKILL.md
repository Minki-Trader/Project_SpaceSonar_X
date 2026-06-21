---
name: spacesonar-code-quality
description: Review implementation quality for Python, MQL5, data, model, runtime, report, or test code.
---

# SpaceSonar Code Quality

Use when implementation quality matters, especially for quant research code.

This is different from `spacesonar-code-surface-guard`. Code surface decides where code belongs. Code quality decides whether the implementation is clear, disciplined, and trustworthy.

## Automatic Bundle

Trigger automatically after `spacesonar-code-surface-guard` for non-trivial code edits in Python, MQL5, feature, label, split, model, dataset, parity, report, or test code.

Effect: check implementation responsibility, flow, contracts, and test intent so useful lab code does not collapse into large one-off scripts.

## Quality Standard

Code should read like a good expert answer:

- the responsibility is clear
- the reasoning flow is visible
- inputs, processing, and outputs are separated
- assumptions are near the code that depends on them
- names explain intent
- constants and thresholds are not hidden magic
- failures explain what broke
- outputs can be traced later
- tests protect the intended behavior, not only execution

## Quant-Specific Quality Points

For trading or research code, treat these as core quality issues:

- input data identity and expected columns
- timestamp meaning and timezone policy
- feature calculation boundary
- label calculation boundary
- train, validation, and OOS split boundary
- lookahead or future-data leakage risk
- dataset id, config, row count, hash, and artifact path traceability
- whether tests check financial or temporal meaning, not only that code runs

## Required Output Before Or During Implementation

- `responsibility`: what this code owns
- `flow`: how data moves from input to output
- `contracts`: input, output, and failure contracts
- `assumptions`: assumptions that must not be hidden
- `traceability`: ids, hashes, configs, row counts, or artifact paths to preserve
- `test_intent`: what the tests prove
- `quality_risk`: the most likely way this code could become misleading or hard to change

## Do Not

- Do not write a large script where parsing, feature work, labels, model training, and reporting are tangled together.
- Do not let a passing test replace a clear contract.
- Do not hide a business or trading assumption in a variable name like `threshold = 0.5`.
- Do not mix feature and label logic unless the boundary is explicit and tested.
- Do not rely on timestamp meaning by memory; use the project time-axis policy or name the unresolved assumption.
