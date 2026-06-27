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
- Verify the responsible source-of-truth path and writer contract before invoking broad validators.
- Do not use adjacent guessing when artifact names vary.
- Do not treat repeated folder scans, whole-tree inventory, or CI success as proof that the operating rule is correct.
- Do not let volatile local workspaces (`.pytest_tmp`, `.spacesonar/transactions`, raw runtime reports/telemetry, package artifacts) define current truth; follow the manifest, receipt, summary, registry projection, or workspace projection.
- Do not revive legacy routing/review meanings from deleted archive paths.
- If a legacy file is absent, treat that evidence as unavailable unless the user explicitly restores it from backup.
- Do not turn "not found", "unsupported", or "missing adapter/glue" into a final disposition from memory alone.
- If the missing path, parser, adapter, runner, or runtime glue is repo-controlled, first locate or create the smallest repair/fallback needed to test the hypothesis.
- Only record blocked, deferred, invalid, or discarded after the failing layer, repair/fallback attempt or narrow blocker, evidence path, remaining blocker, and reopen condition are captured.
