---
name: spacesonar-claim-discipline
description: Prevent overclaims in ONNX lab status, docs, reports, closure, readiness, handoff, or runtime claims.
---

# SpaceSonar Claim Discipline

Use this skill when writing, editing, or summarizing project state.

## Strict Tokens

If any relevant field contains one of these tokens, lower the claim unless matching evidence exists:

- `pending_*`
- `planning_*`
- `draft`
- `placeholder_*`
- `not_yet_evaluated`
- `not_applicable`

## Do Not Claim Without Evidence

- selected baseline
- operating reference
- operating promotion
- runtime authority
- economics pass
- materialization-ready
- handoff complete
- live readiness
- Goal Achieve
- reviewed/verified/pass

## Preferred Boundaries

- planning scaffold
- exploration-only
- scout surface
- proxy observation
- preserved clue
- negative memory
- invalid setup
- blocked retry condition
- bundle preflight
- runtime probe

## Guardrails

- A completed command is not a meaningful experiment by itself.
- "Cannot", "unsupported", "not available", or missing support is not enough to claim blocked, deferred, invalid, or discarded; name the reproduction, repair/fallback attempt, evidence path, remaining blocker, and reopen condition.
- ONNX export smoke is not runtime authority.
- MetaEditor compile is not Strategy Tester evidence.
- Python/ONNX parity is not economics pass.
- A candidate is not a selected baseline.
- Legacy archive material is prior evidence only.
- If closure is claimed, name the backing manifest, report, hash, or decision memo.
