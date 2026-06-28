---
name: spacesonar-runtime-evidence
description: Check ONNX/EA/MT5 runtime meaning, Strategy Tester identity, reports, parity, and runtime claim boundaries.
---

# SpaceSonar Runtime Evidence

Use when work touches ONNX export, runtime bundles, EA modules, `.mq5/.mqh/.set` files, Strategy Tester output, tester reports, MT5 telemetry, handoff files, economics wording, or Python-to-runtime behavior.

## Required Reads

- `foundation/config/mt5_runtime_probe_contract.yaml`
- `configs/mt5/period_profiles/split_set_v0_runtime_periods.yaml` when period windows matter
- `configs/mt5/tester_execution_profile_v0.yaml` when tester identity matters

## Required Output

- `research_path`
- `runtime_path`
- `shared_contract`
- `tester_identity`
- `ea_identity`
- `report_identity`
- `trade_evidence`
- `cost_assumptions`
- `proxy_runtime_parity`
- `interpretation_drift_risks`
- `minimum_reconciliation_attempt`
- `runtime_evidence_identity`
- `validation_depth`
- `non_pytest_smokes`
- `broad_validation_escalation_reason`
- `runtime_claim_boundary`

## Guardrails

- Python success, ONNX export smoke, and MetaEditor compile are not runtime authority.
- Runtime completion requires the runtime probe contract, completed reports, telemetry rows, portable terminal mode, correct period/execution IDs, and eligible surface scope.
- Main-mode fallback is diagnostic only.
- When prepared MT5 attempts exist, the next meaningful action is runner/probe execution or runner repair, not another full validation pass.
- Runtime runners must write terminal summary, telemetry summary, tester-report receipt, missing evidence, next action, and claim boundary even when telemetry or tester report is missing.
- Runtime runners must fail writer-local when their own summaries, receipts, hashes, availability fields, or claim boundaries are missing; do not use pytest, project validate, or full active-record graph as the first way to discover those gaps.
- Do not let missing local tester reports crash manifest writing. Record missing availability and reopen condition, then keep the runtime claim below L4 completion.
- Do not convert proxy results, diagnostic samples, or telemetry-only observations into economics pass, live readiness, selected baseline, or runtime authority.
- Missing runner, parser, report, tester config, ONNX, EA, or runtime glue under repo control requires the smallest credible repair or fixture attempt before blocked or invalid disposition.

## Operational Stability Floor

- Default `validation_depth` is `writer_scope_smoke`; broad validation commands are not progress-loop defaults.
- If this skill mutates, closes, judges, or routes a record, follow `docs/agent_control/writer_scope_operating_contract.yaml` and record `writer_contract_version`, source-of-truth paths, writer-owned outputs, non-pytest smokes, skipped broad validations, escalation reason, self-check, claim boundary, forbidden claims, blocker or reopen condition, and next action.
- A discovered gap becomes an owner writer, manifest, policy, or scoped lint repair before pytest, project validate, full regression, evidence graph, broad hash resync, or global registry regeneration.
