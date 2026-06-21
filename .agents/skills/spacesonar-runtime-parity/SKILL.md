---
name: spacesonar-runtime-parity
description: Check Python/artifact/ONNX/EA/MT5 runtime meaning before runtime or handoff claims.
---

# SpaceSonar Runtime Parity

Use when work touches ONNX export, model bundles, EA modules, `.mq5/.mqh/.set` files, tester output, handoff files, live-like execution, or Python-vs-runtime behavior.

## Required Reads

- `foundation/config/mt5_runtime_probe_contract.yaml` for runtime claim requirements.
- `configs/mt5/period_profiles/split_set_v0_runtime_periods.yaml` for runtime date-window sets.
- `configs/mt5/tester_execution_profile_v0.yaml` for tester execution settings.

## Required Output

- `research_path`
- `runtime_path`
- `shared_contract`
- `known_differences`
- `proxy_runtime_parity`
- `interpretation_drift_risks`
- `minimum_reconciliation_attempt`
- `unit_semantics`
- `divergence_judgment`
- `prevention_memory`
- `parity_identity`
- `runtime_evidence_identity`
- `runtime_period_profile_id`
- `runtime_period_set_id`
- `runtime_learning_probe_decision`
- `runtime_claim_boundary`

## Guardrails

- Python success is not runtime authority.
- ONNX export smoke is not runtime authority.
- MetaEditor compile is not tester output.
- Python-vs-ONNX parity is not economics pass.
- Samples, previews, and diagnostic rows are runtime learning observations only.
- Runtime/materialization/handoff/economics claims require the narrow sufficient runtime probe or a lowered claim boundary.
- Do not skip a runtime learning probe only because proxy results are weak, trade count is low, long/short balance is poor, or cost is high.
- Do not treat proxy success or proxy failure as final until the campaign records how the proxy semantics map into MT5 runtime semantics.
- Preserve proxy-vs-runtime surprises as evidence: proxy-bad/runtime-good and proxy-good/runtime-bad are both investigation surfaces.
- Make at least one explicit reconciliation attempt when proxy and MT5 disagree, but do not force equality if units or execution semantics are genuinely different.
- Record unit semantics drift, such as point/pip/tick/digits/price-distance/ATR-stop conversion differences, as prevention memory.
- If ONNX, EA, parser, tester, or runtime glue is missing and is under repo/control, build and test the smallest adapter or fallback before calling the surface blocked, deferred, invalid, or discarded.
- "No adapter exists" is a repair trigger, not a final runtime blocker. Only user secrets, unavailable external state, destructive/unsafe action, or project-policy violation can block the attempt, and that blocker must be recorded.
- Do not embed date defaults in this skill. Runtime windows live in the period profile.
- If no actionable runtime surface exists, require at least one repair attempt before `blocked` or `inconclusive`.

## Standard MT5 Probe

Source of truth:

- contract: `foundation/config/mt5_runtime_probe_contract.yaml`
- period profile: `configs/mt5/period_profiles/split_set_v0_runtime_periods.yaml`
- execution profile: `configs/mt5/tester_execution_profile_v0.yaml`

`runtime_probe_completed` requires the contract's required period roles, period profile id, runtime period set id, execution profile id, surface contract, and completed reports.
