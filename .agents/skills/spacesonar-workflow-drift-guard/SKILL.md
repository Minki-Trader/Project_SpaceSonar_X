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
- `writer_scope_contract_checked`
- `broad_validation_escalation_reason`
- `claim_effect`

## Guardrails

- Verify repo-relative paths before acting on remembered names.
- Verify the responsible source-of-truth path and writer contract before invoking broad validators.
- If the path or artifact gap is inside a repo-owned writer, fix or strengthen the writer-local contract before using pytest, full project validate, full evidence graph, broad hash resync, or global registry regeneration.
- Do not use adjacent guessing when artifact names vary.
- Do not treat repeated folder scans, whole-tree inventory, or CI success as proof that the operating rule is correct.
- If direct inspection is needed, inspect source-of-truth records and owner files with volatile excludes. A recursive listing that enters `.pytest_tmp`, `.spacesonar/transactions`, raw runtime reports, telemetry, or package artifacts is drift noise, not evidence.
- Direct inspection findings must be converted into owner writer, source-of-truth manifest, skill, policy, or scoped lint changes before they can count as operational repair.
- Do not let volatile local workspaces (`.pytest_tmp`, `.spacesonar/transactions`, raw runtime reports/telemetry, package artifacts) define current truth; follow the manifest, receipt, summary, registry projection, or workspace projection.
- Do not revive legacy routing/review meanings from deleted archive paths.
- If a legacy file is absent, treat that evidence as unavailable unless the user explicitly restores it from backup.
- Do not turn "not found", "unsupported", or "missing adapter/glue" into a final disposition from memory alone.
- If the missing path, parser, adapter, runner, or runtime glue is repo-controlled, first locate or create the smallest repair/fallback needed to test the hypothesis.
- Only record blocked, deferred, invalid, or discarded after the failing layer, repair/fallback attempt or narrow blocker, evidence path, remaining blocker, and reopen condition are captured.
