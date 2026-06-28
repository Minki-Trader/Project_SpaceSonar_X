---
name: spacesonar-answer-clarity
description: "Final user-facing answer filter: concise Korean-friendly summaries with clear action/effect/claim boundary."
---

# SpaceSonar Answer Clarity

Use this only at the final user-facing response layer.

## Output Style

- Answer in Korean when the user writes Korean.
- Keep it short and practical.
- Say what changed or what was learned.
- Say why it matters.
- Say what is true now.
- Say what is not yet true when claim boundaries matter.
- Mention exact files only when they help the user act.

## Do Not

- Do not make internal records tutorial-like.
- Do not bury the result behind process detail.
- Do not over-explain obvious tool steps.
- Do not imply reviewed/verified/pass unless matching evidence exists.

## Operational Stability Floor

- Default `validation_depth` is `writer_scope_smoke`; broad validation commands are not progress-loop defaults.
- User-facing wording must keep the current claim boundary and must not turn writer-scope smoke into reviewed, verified, runtime authority, economics pass, live readiness, or Goal Achieve.
- If final wording exposes a changed status, keep it aligned with `docs/agent_control/writer_scope_operating_contract.yaml` fields already written by the owning writer.
- A discovered gap becomes an owner writer, manifest, policy, or scoped lint repair before pytest, project validate, full regression, evidence graph, broad hash resync, or global registry regeneration.
