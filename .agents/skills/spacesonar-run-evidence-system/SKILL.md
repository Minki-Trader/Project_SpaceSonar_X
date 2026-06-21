---
name: spacesonar-run-evidence-system
description: Manage run identity, KPI records, ledgers, MT5 evidence, result summaries, and closeout evidence.
---

# SpaceSonar Run Evidence System

Use when a task creates, reviews, summarizes, registers, or closes run evidence.

## Pairing

Pair with `spacesonar-claim-discipline` when the task makes any result, selection, runtime, economics, or handoff claim.

## Reads

Read only the surfaces needed for the run:

- `docs/policies/kpi_measurement_standard.md`
- `docs/policies/result_judgment_policy.md`
- `docs/policies/exploration_mandate.md` when exploration boundaries matter
- `docs/policies/promotion_policy.md` when promotion-like wording appears
- `docs/policies/tiered_readiness_exploration.md` when Tier A/B/C readiness appears
- affected `lab/runs/**`, `runtime/**`, or `docs/registers/**` records

## Required Output

- `run_identity`: run id, command, input paths, output paths, and environment summary when available
- `artifact_identity`: artifact paths and hashes, or explicit missing/not-applicable reasons
- `measurement_scope`: KPI layer and scoreboard
- `judgment_class`: `positive`, `negative`, `inconclusive`, `invalid`, or `blocked`
- `claim_boundary`: idea, scout, candidate, probe, advisory, operating, runtime, or handoff boundary
- `storage_contract`: source-of-truth path, supporting paths, registry rows, and duplicate policy
- `required_gate_coverage`: gates passed, not applicable, missing, or lowering the claim
- `runtime_learning_probe_decision`: required, not applicable, blocked, or lowered claim with reason
- `registry_effect`: register row added/updated/not required
- `missing_evidence`: evidence gaps that lower the claim

## MT5 / EA Identity

For MT5, EA, `.set`, ONNX, or runtime package work, capture when applicable:

- `ea_entrypoint` path and sha256
- `.mqh` module paths and sha256 values
- `.set` file path and sha256
- ONNX/model/bundle path and sha256
- input parameter hash
- tester identity: symbol, timeframe, model, deposit, leverage, cost/spread settings
- tester output path or explicit missing reason

## Guardrails

- Do not call a run reviewed, selected, runtime-ready, economics-pass, or handoff-complete without matching durable evidence.
- Do not treat `runtime_probe` as `runtime_authority`.
- Do not treat proxy or diagnostic samples as runtime/economics proof.
- Keep large artifacts outside Git only when tracked by path, hash, and regeneration command or external URI.
- If evidence is missing, lower the claim instead of filling gaps with deleted legacy material.
- Do not let a registry row replace run-local, bundle-local, candidate-local, or attempt-local evidence.
