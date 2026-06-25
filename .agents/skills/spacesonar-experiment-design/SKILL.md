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
- `sample_scope`
- `success_criteria`
- `failure_criteria`
- `invalid_conditions`
- `stop_conditions`
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
- Do not let operating gates block exploration unless the claim is operating promotion, runtime authority, economics pass, or handoff complete.
- Fine search starts only after broad/extreme sweeps expose a repeated surface clue.
- Every run intended for future reuse needs a manifest, metrics identity, and artifact lineage.
- Keep exploration open without inheriting deleted legacy winners, baselines, promotion history, live readiness, runtime authority, economics pass, or Goal Achieve.
- Record failed ideas as negative memory instead of erasing them.
