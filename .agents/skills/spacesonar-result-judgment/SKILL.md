---
name: spacesonar-result-judgment
description: Classify ONNX lab results and claim boundary: positive, negative, inconclusive, invalid, blocked, candidate, runtime.
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
- `exploratory`
- `research_candidate`
- `probe_candidate`
- `runtime_probe`
- `runtime_authority`
- `not_applicable`

## Guardrails

- Negative is interpretable evidence.
- Invalid means the setup cannot be interpreted until repaired.
- Inconclusive is not success or failure.
- Research candidate is not selected baseline.
- Runtime probe is not runtime authority.
- Economics pass needs MT5 runtime evidence.

