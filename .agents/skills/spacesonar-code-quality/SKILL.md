---
name: spacesonar-code-quality
description: Review implementation quality for Python, MQL5, data, model, runtime, report, or test code.
---

# SpaceSonar Code Quality

Use for non-trivial Python, MQL5, data, feature, label, split, model, parity, runtime, report, or test edits.

Pair after `spacesonar-code-surface-guard` when code ownership is also in scope.

## Check

- `responsibility`: single clear owner
- `flow`: input -> processing -> output
- `contracts`: input/output/failure contract
- `assumptions`: trading/time/data assumptions visible
- `traceability`: ids, configs, paths, hashes, row counts when relevant
- `test_intent`: what behavior the test protects
- `quality_risk`: most likely misleading/hard-to-change failure mode

## Quant Checks

- data identity and expected columns
- timestamp/timezone/session meaning
- feature-label boundary
- train/validation/OOS boundary
- lookahead leakage risk
- financial/temporal meaning in tests, not execution-only tests

## Do Not

- tangle parsing, features, labels, training, and reporting in one large script
- hide constants, thresholds, or trading assumptions
- let passing tests replace explicit contracts
- mix feature and label logic without boundary/test intent
- rely on remembered timestamp meaning
