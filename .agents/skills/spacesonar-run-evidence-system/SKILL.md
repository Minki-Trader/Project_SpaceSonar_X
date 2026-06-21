---
name: spacesonar-run-evidence-system
description: Manage run identity, KPI records, ledgers, MT5 evidence, result summaries, and closeout evidence.
---

# SpaceSonar Run Evidence System

Use when creating, updating, registering, summarizing, or closing run evidence.

Pair with `spacesonar-claim-discipline` for result, selection, runtime, economics, handoff, or readiness claims.

## Read

Only touched run/runtime/register records plus relevant policies:

- KPI/result/promotion policy only when those claims appear
- affected `lab/runs/**`, `runtime/**`, `docs/registers/**`

## Output

- `run_identity`: id, command, inputs, outputs, env
- `artifact_identity`: paths/hashes or missing/not-applicable reason
- `measurement_scope`
- `judgment_class`
- `claim_boundary`
- `storage_contract`
- `required_gate_coverage`
- `runtime_learning_probe_decision`
- `registry_effect`
- `missing_evidence`

## MT5 / EA Identity

Capture when applicable:

- EA entrypoint and `.mqh` hashes
- `.set`, ONNX/model/bundle hashes
- input parameter hash
- tester identity: symbol, timeframe, model, deposit, leverage, costs/spread
- tester output path or explicit missing reason

## Do Not

- call a run reviewed, selected, runtime-ready, economics-pass, or handoff-complete without durable evidence
- treat `runtime_probe` as `runtime_authority`
- treat proxy/diagnostic samples as runtime or economics proof
- let a registry row replace run-local, bundle-local, candidate-local, or attempt-local evidence
- fill missing evidence with deleted legacy material
