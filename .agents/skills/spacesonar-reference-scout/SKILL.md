---
name: spacesonar-reference-scout
description: Use external/official refs for version-sensitive APIs, MT5/MQL5 behavior, libraries, or quant methods.
---

# SpaceSonar Reference Scout

Use only when external facts can change correctness: API syntax, MT5/MQL5/MetaEditor/Strategy Tester behavior, dependency behavior, ONNX/runtime details, or quant-method grounding.

## Source Order

1. Official/vendor docs.
2. Maintained repo, examples, release notes, issues.
3. Current readable examples.
4. Forums only as ideas/warnings, not evidence.

## Output

- `question`
- `sources_checked`
- `source_quality`
- `found_pattern`
- `project_fit`
- `do_not_copy`
- `recommended_use`
- `not_required_reason`

## MT5 Hard Trigger

For EA architecture or Strategy Tester behavior, check official MQL5 docs first.

Record:

- defined behavior vs inference
- `.mq5` entrypoint vs `.mqh` module placement
- parameter-only vs code-changing difference
- identity fields needed to trace tester output

## Do Not

- copy external code wholesale
- trust forum performance claims
- let external examples override project contracts
- present unbrowsed/unchecked statements as externally verified

## Operational Stability Floor

- Default `validation_depth` is `writer_scope_smoke`; broad validation commands are not progress-loop defaults.
- If this skill mutates, closes, judges, or routes a record, follow `docs/agent_control/writer_scope_operating_contract.yaml` and record `writer_contract_version`, source-of-truth paths, writer-owned outputs, non-pytest smokes, skipped broad validations, escalation reason, self-check, claim boundary, forbidden claims, blocker or reopen condition, and next action.
- A discovered gap becomes an owner writer, manifest, policy, or scoped lint repair before pytest, project validate, full regression, evidence graph, broad hash resync, or global registry regeneration.
