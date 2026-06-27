---
name: spacesonar-session-bootstrap
description: Start or re-enter SpaceSonar lab work with narrow current-truth reads and routing handoff.
---

# SpaceSonar Session Bootstrap

Use when starting or resuming repository work that needs current truth, stale-assumption control, or work-family routing.

## Required Reads

- `AGENTS.md`
- `docs/agent_control/operational_stability_kernel.yaml` when validation cadence, no-pytest operation, stability, or heavy-check avoidance is in scope
- `docs/workspace/workspace_state.yaml` when current lab truth matters
- `docs/agent_control/work_family_registry.yaml` for non-trivial routing
- touched contracts or manifests only when the task requires them

## Required Output

- `reentry_mode`
- `user_intent`
- `current_truth_need`
- `primary_family_candidate`
- `required_reads`
- `stop_conditions`
- `claim_boundary`
- `final_answer_filter`

## Guardrails

- Start with the smallest repo-controlled read or action that answers the current request.
- If the user asks for progress, experiments, or why work is slow, identify the active work item's next executable writer/probe and move there before any validation-only loop.
- Default to writer-scope smoke, not pytest/full graph validation. Name `validation_depth` before running commands.
- When run evidence is touched, prefer `python -m spacesonar.cli project writer-smoke ...` as the first proof command.
- Do not use whole-tree inventory as proof of operational stability; identify the owned source-of-truth surface and the guard that should fail early.
- Do not inspect `.pytest_tmp`, `.spacesonar/transactions`, runtime telemetry/report trees, or package artifact trees as current truth; inspect their manifests, receipts, summaries, and hashes.
- Do not recreate deleted legacy archive meanings.
- Do not start broad validators or materializers unless the task is a boundary closeout, shared-contract change, source-of-truth drift repair, or protected claim surface.
- For non-trivial work, hand off to `spacesonar-work-item-router`.
