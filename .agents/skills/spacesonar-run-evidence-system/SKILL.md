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
- close a failed, unsupported, missing-adapter, or non-working path as blocked, deferred, invalid, or discarded without a `failure_disposition` record
- treat "adapter/glue does not exist" as evidence that a surface is impossible when the adapter/glue is repo-controlled

## Try-First Evidence

For blocked, deferred, invalid, or discarded outcomes caused by a tool, adapter, converter, parser, runtime, data path, or EA/ONNX support gap, record:

- failure reproduction or reproduction blocker
- exact failing layer
- smallest repo-controlled repair, adapter, translation layer, fixture, parser, runner, or fallback attempted
- evidence path for the attempt
- remaining blocker
- reopen condition

If no repair attempt is allowed, the blocker must be narrow: user secrets, unavailable external state, destructive or unsafe action, or project-policy violation.
