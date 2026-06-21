---
name: spacesonar-workflow-drift-guard
description: Prevent stale-path, stale-policy, wrong-artifact, and legacy-inheritance drift in ONNX lab workflows.
---

# SpaceSonar Workflow Drift Guard

Use when a path, artifact, routing record, register row, or policy meaning is inferred from memory or convention rather than verified current files.

## Required Output

- `assumption_checked`
- `truth_source`
- `path_verified`
- `legacy_boundary`
- `drift_risk`
- `claim_effect`

## Guardrails

- Verify repo-relative paths before acting on remembered names.
- Do not use adjacent guessing when artifact names vary.
- Do not revive legacy routing/review meanings from deleted archive paths.
- If a legacy file is absent, treat that evidence as unavailable unless the user explicitly restores it from backup.
