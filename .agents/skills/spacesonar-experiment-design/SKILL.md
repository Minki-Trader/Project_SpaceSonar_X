---
name: spacesonar-experiment-design
description: "Design ONNX lab experiments: hypothesis, comparison, controls, criteria, evidence, and stop conditions."
---

# SpaceSonar Experiment Design

Use this skill when work creates, changes, compares, packages, or closes a lab experiment.

## Required Output

- `idea_id`
- `hypothesis_id`
- `surface_id`
- `sweep_id`
- `hypothesis`
- `decision_use`
- `comparison_baseline`
- `control_variables`
- `changed_variables`
- `kpi_interpretation_plan`
- `attribution_axes`
- `expected_effect_probe`
- `surface_rotation_rationale`
- `search_shape`: scout, broad, extreme, narrowing, repair, runtime follow-through, synthesis, or stop
- `next_surface_options`
- `axis_balance_check`
- `sample_scope`
- `success_criteria`
- `failure_criteria`
- `invalid_conditions`
- `stop_conditions`
- `reopen_or_stop_condition`
- `evidence_plan`
- `claim_boundary`
- `legacy_relation`
- `axis_tags`
- `broad_sweep`
- `extreme_sweep`
- `micro_search_gate`
- `failure_memory`

## Guardrails

- A completed command is not a meaningful experiment by itself.
- Do not compare results if baseline, data scope, or changed variable is unclear.
- Design each KPI-bearing run so later judgment can connect `changed_variables -> observed KPI -> likely effect hypothesis`; if that connection is impossible, lower the result to exploratory/inconclusive.
- Success/failure criteria must name which KPI fields matter and which experimental axis each KPI is meant to test.
- Every next-experiment recommendation must name why this axis is worth testing now, which axes are deliberately held still, and why other plausible axes are deferred.
- Do not let one weak candidate turn into a long repair track unless the repair teaches a reusable surface, divergence, parser, runtime, or negative-memory lesson.
- Do not let operating gates block exploration unless the claim is operating promotion, runtime authority, economics pass, or handoff complete.
- Fine search starts only after broad/extreme sweeps expose a repeated surface clue.
- WFO, threshold narrowing, and micro-search start only after a repeated clue exists across enough scope to justify spending budget.
- When closing a campaign or wave, state whether the next move is broaden, rotate, narrow, repair, follow through in runtime, synthesize, or stop.
- Every run intended for future reuse needs a manifest, metrics identity, and artifact lineage.
- Keep exploration open without inheriting deleted legacy winners, baselines, promotion history, live readiness, runtime authority, economics pass, or Goal Achieve.
- Record failed ideas as negative memory with salvage value instead of erasing them.
