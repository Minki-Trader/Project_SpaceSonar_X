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
- `runtime_claim_boundary`

## Guardrails

- Python success, ONNX export smoke, and MetaEditor compile are not runtime authority.
- Runtime completion requires the runtime probe contract, completed reports, telemetry rows, portable terminal mode, correct period/execution IDs, and eligible surface scope.
- Main-mode fallback is diagnostic only.
- When prepared MT5 attempts exist, the next meaningful action is runner/probe execution or runner repair, not another full validation pass.
- Do not convert proxy results, diagnostic samples, or telemetry-only observations into economics pass, live readiness, selected baseline, or runtime authority.
- Missing runner, parser, report, tester config, ONNX, EA, or runtime glue under repo control requires the smallest credible repair or fixture attempt before blocked or invalid disposition.
