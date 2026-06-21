---
name: spacesonar-code-surface-guard
description: Guard code ownership, reusable logic placement, entrypoints, tests, and artifact side effects.
---

# SpaceSonar Code Surface Guard

Use this skill before editing Python, MQL5, tests, pipelines, model builders, ONNX exporters, runtime helpers, or report materializers.

## Required Output

- `owner_surface`
- `caller`
- `input_contract`
- `output_contract`
- `artifact_effect`
- `test_or_syntax_check`
- `migration_effect`

## Placement Rules

- reusable package code: `src/spacesonar/`
- reusable feature logic: `foundation/features/`
- reusable label logic: `foundation/labels/`
- reusable training logic: `foundation/training/`
- ONNX export and schema logic: `foundation/onnx/`
- parity logic: `foundation/parity/`
- MT5/EA reusable logic: `foundation/mt5/`
- orchestration entrypoints: `foundation/pipelines/`
- run-local evidence: `lab/runs/<run_id>/`
- runtime package evidence: `runtime/packages/<bundle_id>/`

## Guardrails

- Do not place reusable logic in one-off run scripts.
- Do not hide generated artifact effects.
- Do not change runtime behavior without naming parity and evidence impact.
- Do not describe legacy code as current architecture merely because it exists.

