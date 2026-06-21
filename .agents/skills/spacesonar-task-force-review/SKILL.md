---
name: spacesonar-task-force-review
description: Route Codex Task Force consultation; formal review only for protected high-claim surfaces.
---

# SpaceSonar Task Force Review

Use this skill when the user explicitly asks for agent consultation/review or when a protected claim requires formal Codex Task Force review.

## Required Reads

- `docs/agent_control/codex_task_force_registry.yaml`
- `.codex/agents/*.toml` only for selected agents
- current task context and claim boundary

## Modes

`micro_consult` is the default:

- usually 1 agent
- 2 agents when two remits are genuinely needed
- advisory only
- cannot produce reviewed/verified/pass

Formal review is only for:

- policy change
- runtime authority
- operating promotion
- cross-system handoff
- protected reviewed/verified/pass claim

## Escalation

- 3+ agents require `escalation_reason`
- 5+ agents require `why_not_smaller`
- all 8 agents require `full_roster_call_reason`

## Receipt Fields

- `consult_id`
- `trigger_source`
- `selected_agents`
- `selection_reason`
- `claim_surface`
- `question_or_context_digest`
- `spawned_agent_ids`
- `opinion_classification`
- `owner_response`
- `local_verification_required`
- `allowed_claim_effect=advisory_only_no_reviewed_pass`
- `forbidden_claims`

## Guardrails

- Agent consensus is not evidence.
- Self-review is not Task Force review.
- Stale agent output is not review evidence.
- Do not follow agent advice verbatim. Parent Codex must source-check advice against current repo files, selected skills, active workspace state, and user constraints before accepting it.
- If an agent did not read the relevant source-of-truth file or was spawned without full context, classify its output as advisory hypothesis only.
- If advice conflicts with project definitions, reject or rewrite it; do not bend project terms to match the advice.
- Legacy external reviews have no active or archive path in this workspace.
- Codex owns final direction after local verification.
