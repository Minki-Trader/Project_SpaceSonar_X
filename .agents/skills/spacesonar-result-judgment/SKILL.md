---
name: spacesonar-result-judgment
description: "Classify ONNX lab results and claim boundary: positive, negative, inconclusive, invalid, blocked, candidate, runtime."
---

# SpaceSonar Result Judgment

Use this skill when a run, model, bundle, package, backtest, PR, or user-facing outcome is interpreted or written into a register.

## Required Output

- `result_subject`
- `evidence_paths`
- `metric_identity`
- `comparison_baseline`
- `judgment_label`
- `claim_boundary`
- `missing_evidence`
- `next_action`

## Judgment Labels

- `positive`
- `negative`
- `invalid`
- `inconclusive`
- `blocked`
- `deferred`
- `discarded`
- `exploratory`
- `research_candidate`
- `probe_candidate`
- `runtime_probe`
- `runtime_authority`
- `not_applicable`

## Guardrails

- Negative is interpretable evidence.
- Invalid means the setup cannot be interpreted after a repair or reinterpretation attempt, or the attempt blocker is recorded.
- Inconclusive is not success or failure.
- Blocked, deferred, invalid, or discarded due to "cannot", "unsupported", "not available", or missing support require a failure disposition record: reproduction, exact failing layer, bounded repair/fallback attempt, evidence path, remaining blocker, and reopen condition.
- Missing converter, export, EA, parser, runtime, or environment support should trigger a minimal adapter/fallback attempt when feasible before disposition.
- Research candidate is not selected baseline.
- Runtime probe is not runtime authority.
- Economics pass needs MT5 runtime evidence.
