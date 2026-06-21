---
name: spacesonar-workspace-state-sync
description: Sync ONNX lab current truth, registers, candidates, handoff state, and archive boundaries.
---

# SpaceSonar Workspace State Sync

Use this skill when workspace truth, candidate state, register rows, handoff state, or archive boundaries change.

## Reads

Read only the surfaces needed for the sync:

- `docs/workspace/workspace_state.yaml`
- `docs/workspace/lab_profile.yaml`
- affected `docs/registers/*`
- affected `lab/**` or `runtime/**` manifest
- user-restored legacy backup material only when the task is explicitly archive recovery or archive boundary work

Do not read or recreate historical routing records, legacy external-review records, or generated run trees by default.

## Required Output

- `sync_scope`
- `truth_sources_read`
- `changed_surfaces`
- `register_effect`
- `claim_boundary_effect`
- `archive_boundary_effect`
- `not_applicable_gates`
- `next_required_action`

## Guardrails

- Do not create numbered legacy open/close semantics.
- Do not turn a candidate into selected baseline, operating reference, runtime authority, or economics pass.
- Do not let README carry mutable live state; point to `docs/workspace/workspace_state.yaml`.
- If evidence is missing, lower the claim rather than filling gaps with legacy archive material.
