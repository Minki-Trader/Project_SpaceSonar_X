---
name: spacesonar-session-intake
description: Start ONNX lab work: identify intent, current truth need, work family, and routing need.
---

# SpaceSonar Session Intake

Use at the start of repository work when the user asks for status, implementation, verification, cleanup, handoff, policy, skill, model, ONNX, or runtime changes.

## Minimal Intake

1. Decide `reentry_mode`: `delta` for warm stable thread, `cold` only when needed.
2. Identify `user_intent`.
3. Decide if the task is trivial/information-only or non-trivial.
4. For non-trivial work, hand off to `spacesonar-work-item-router`.

## Non-Trivial Triggers

- file mutation
- command execution
- data, feature, label, model, ONNX, bundle, MT5, or runtime work
- policy, skill, agent, or control-plane change
- publish, handoff, archive, restore, or state sync
- strong `completed/reviewed/verified/pass` claim

## Reads

Default read: `AGENTS.md` only.

Additional reads are task-driven:

- current lab truth: `docs/workspace/workspace_state.yaml`
- routing: `docs/agent_control/work_family_registry.yaml`
- ONNX contract: `docs/contracts/onnx_lab_contract.yaml`
- runtime/MT5 claim: `foundation/config/mt5_runtime_probe_contract.yaml`
- selected skill: that skill's `SKILL.md`
- specific user-referenced file: that file only

Do not read archive folders, legacy routing records, old review records, or generated run trees unless the current task requires them.

## Output

Use compact internal fields:

- `reentry_mode`
- `user_intent`
- `triviality`
- `candidate_family`
- `required_reads`
- `stop_conditions`
- `claim_boundary`
- `final_answer_filter`
