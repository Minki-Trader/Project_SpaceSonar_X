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
- `tested_factor`
- `kpi_interpretation`
- `directional_effect_hypothesis`
- `attribution_confidence`
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
- KPI-bearing judgments must include a performance-attribution pass: tested factor, observed KPI movement, likely effect hypothesis, confidence, and next probe.
- Do not close a KPI result with only the headline outcome; name what experimental item was changed and what effect it appears to have under the stated boundary.
- Effect language is exploratory unless controls, matched scope, sufficient samples, and proxy/runtime evidence support a stronger claim.
- Invalid means the setup cannot be interpreted after a repair or reinterpretation attempt, or the attempt blocker is recorded.
- Try-first disposition: before blocked, deferred, invalid, or discarded, identify why the attempt failed, reproduce the failing layer, try the smallest credible fix/fallback under repo control, and record evidence plus reopen condition.
- Explanation-only closeout is forbidden: diagnosis text, advisory notes, missing-helper observations, or agent consensus do not count as repair/fallback attempts.
- Inconclusive is not success or failure.
- Blocked, deferred, invalid, or discarded due to "cannot", "unsupported", "not available", or missing support require a failure disposition record: reproduction, exact failing layer, bounded repair/fallback attempt, evidence path, remaining blocker, and reopen condition.
- Missing converter, conversion adapter, export, EA, parser, or runtime glue under repo/control requires building and testing the smallest adapter/fallback before disposition; "adapter absent" alone is not a blocker.
- If the conversion adapter does not exist yet, create the smallest explicit translation layer needed to test the hypothesis unless a narrow attempt blocker applies.
- Attempt blockers are narrow: user secrets, unavailable external state, destructive/unsafe action, or project-policy violation. Record the blocker and reopen condition.
- Research candidate is not selected baseline.
- Runtime probe is not runtime authority.
- Economics pass needs MT5 runtime evidence.
