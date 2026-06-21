---
name: spacesonar-reentry-read
description: Cold/warm ONNX lab re-entry. Read current truth narrowly and avoid legacy inheritance.
---

# SpaceSonar Reentry Read

Use only when the task needs repository re-entry, current truth, or stale-assumption control.

## Cold Start

Read only:

1. `AGENTS.md`
2. `docs/workspace/workspace_state.yaml` if current lab truth matters
3. `docs/agent_control/work_family_registry.yaml` if the task is non-trivial
4. `docs/contracts/onnx_lab_contract.yaml` if ONNX bundle/schema/export work is in scope
5. `foundation/config/mt5_runtime_probe_contract.yaml` if runtime/MT5 claims are in scope
6. touched skill `SKILL.md` only after selecting that skill

Do not recreate legacy archives, legacy routing records, old review records, or generated run trees by default.

## Current Workspace Assumptions

- This is an ID-based ONNX development lab.
- Legacy workspace material was deleted by user request and cannot create winners, baselines, live readiness, runtime authority, economics pass, or Goal Achieve.
- `data/`, `lab/runs/`, and `runtime/` may contain generated or ignored material; require manifests and hashes before strong claims.

## Output

- `reentry_mode`
- `truth_sources_read`
- `current_boundary`
- `missing_material_if_relevant`
- `next_route`
- `claim_limits`
