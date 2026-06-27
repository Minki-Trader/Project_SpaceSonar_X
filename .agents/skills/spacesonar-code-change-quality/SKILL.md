---
name: spacesonar-code-change-quality
description: Guard code ownership, contracts, implementation quality, tests, and artifact side effects.
---

# SpaceSonar Code Change Quality

Use before editing Python, MQL5, tests, pipelines, model builders, ONNX exporters, runtime helpers, report materializers, or reusable package code.

## Required Output

- `owner_surface`
- `caller`
- `input_contract`
- `output_contract`
- `artifact_effect`
- `responsibility`
- `flow`
- `assumptions`
- `traceability`
- `test_or_syntax_check`
- `no_pytest_reason`
- `migration_effect`
- `quality_risk`

## Placement Rules

- reusable package code: `src/spacesonar/`
- reusable feature logic: `foundation/features/`
- reusable label logic: `foundation/labels/`
- reusable training logic: `foundation/training/`
- ONNX export and schema logic: `foundation/onnx/`
- parity and MT5 reusable logic: `foundation/mt5/` or dedicated reusable modules
- orchestration entrypoints: `foundation/pipelines/`

## Guardrails

- Do not place reusable logic only inside one-off run scripts.
- Do not hide generated artifact effects.
- Do not let passing tests replace explicit input, output, and failure contracts.
- Do not default to pytest for ordinary code or policy edits. Prefer direct parse, compile, import, schema, lint, or command-level smoke for the touched surface; escalate to pytest only for boundary, shared-contract, protected-claim, or explicit user-requested validation.
- When skipping pytest, record the narrower smoke and why it covers the touched contract.
- Do not replace pytest with full project validation by habit. `python -m spacesonar.cli project validate` is also broad validation and follows the same boundary/drift/shared-contract/user-request escalation rule.
- If a bug repeats because validation finds it late, move the check into the writer, parser, adapter, or manifest contract so the next run fails before broad validation.
- For artifact writers, add an existence/hash guard at the write site before `artifact_ref` or registry projection. Missing optional raw artifacts should become explicit availability records; missing proof summaries/receipts should be written or fail with a writer-local error.
- Avoid unbounded recursive workspace reads for code understanding. Use `rg --files` and exclude volatile/generated trees before targeted reads.
- Exclude local volatile dirs from fallback scans and copy operations unless the task explicitly targets those dirs.
- Make trading, time, data, and runtime assumptions visible when relevant.
