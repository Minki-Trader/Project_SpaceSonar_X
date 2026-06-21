---
name: spacesonar-work-item-router
description: Route non-trivial ONNX lab work: family, primary skill, support skills, gates, phases, and stop conditions.
---

# SpaceSonar Work Item Router

Use after session intake for non-trivial work.

## Reads

Read `docs/agent_control/work_family_registry.yaml`.

Read selected skill `SKILL.md` files only after selecting:

1. one `primary_family`
2. one `primary_skill`
3. only necessary `support_skills`

Do not read broad archives, legacy routing records, legacy review records, generated run trees, or all skills by default.

## Routing Receipt

Emit compact internal fields:

- `router_mode`
- `primary_family`
- `primary_skill`
- `support_skills`
- `skills_to_read`
- `verification_profile`
- `required_gates`
- `not_applicable_gates`
- `storage_contract`
- `runtime_learning_probe_decision`
- `failure_disposition_policy`
- `phase_plan`
- `stop_conditions`
- `claim_boundary`
- `final_answer_filter`

Internal receipts are not user reports.

## Defaults

- information-only: `router_mode=lite`, support skills usually `[]`
- policy/skill/agent/control changes: `policy_skill_governance`
- cleanup/delete/move: `cleanup_archive`
- data/feature/label/split work: `data_feature_build`
- model training and selection risk: `model_training`
- ONNX export or parity: `onnx_export_parity`
- bundle packaging: `bundle_materialization`
- MT5/economics/handoff/runtime claims: `runtime_probe`
- final user answer: apply `spacesonar-answer-clarity` and `spacesonar-claim-discipline`

## Do Not

- select broad automatic skill groups
- create numbered legacy routing rules
- treat advisory micro-consult as formal review
- make internal receipts tutorial-like
- claim completion/review/pass without required gate coverage
- route a non-trivial item without a storage contract
- skip a runtime learning probe decision when runtime behavior, economics, EA/ONNX meaning, or handoff is in scope
- route or close a repo-controlled support gap as blocked/deferred/invalid/discarded without a failure disposition record: reproduction, failing layer, repair/fallback attempt, evidence, remaining blocker, and reopen condition
