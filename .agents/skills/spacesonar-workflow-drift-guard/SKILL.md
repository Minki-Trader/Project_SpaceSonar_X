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
- `writer_preflight_gate_checked`
- `validation_attempt_budget_checked`
- `broad_validation_escalation_reason`
- `claim_effect`

## Guardrails

- Verify repo-relative paths before acting on remembered names.
- Verify the responsible source-of-truth path and writer contract before invoking broad validators.
- Verify `writer_preflight_gate` and `validation_attempt_budget` before allowing a changed writer or boundary record to count as operating proof.
- For strict writer-owned YAML surfaces, verify the write path uses `src/spacesonar/control_plane/writer_contract.py` or `ControlPlaneTransaction.stage_yaml`; post-hoc validation cannot make an unguarded record authoritative.
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

## Operational Stability Floor

- Default `validation_depth` is `writer_scope_smoke`; broad validation commands are not progress-loop defaults.
- If this skill mutates, closes, judges, or routes a record, follow `docs/agent_control/writer_scope_operating_contract.yaml` and record `writer_contract_version`, source-of-truth paths, writer-owned outputs, non-pytest smokes, skipped broad validations, escalation reason, self-check, claim boundary, forbidden claims, blocker or reopen condition, and next action.
- New or changed writer records must also record `writer_preflight_gate` and `validation_attempt_budget`; do not repeat writer-scope validation more than two passes without blocker or command-intent escalation.
- If a strict writer-owned record is produced without the shared write-time guard, treat it as construction drift and patch the writer before any broad validation.
- A discovered gap becomes an owner writer, manifest, policy, or scoped lint repair before pytest, project validate, full regression, evidence graph, broad hash resync, or global registry regeneration.
