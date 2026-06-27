---
name: spacesonar-work-item-router
description: "Route non-trivial ONNX lab work: family, primary skill, support skills, gates, phases, and stop conditions."
---

# SpaceSonar Work Item Router

Use after session intake for non-trivial work.

## Reads

Read `docs/agent_control/work_family_registry.yaml`.

Read `docs/agent_control/operational_stability_kernel.yaml` when the task asks to operate without pytest/full graph validation, reduce heavy checks, change validation cadence, or harden Codex operating behavior.

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
- `execution_weight`
- `validation_depth`
- `non_pytest_smokes`
- `skipped_broad_validations`
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

## Execution Weight

- Default `execution_weight=thin_first_pass` unless the work is already at a campaign/wave boundary, protected runtime/economics/handoff claim, shared-contract mutation, or known source-of-truth drift repair.
- Default `validation_depth=writer_scope_smoke`; pytest, full active-record graph, full project validate, evidence-graph-full, broad hash sync, and global registry regeneration are not default run-loop actions.
- For touched run evidence, use `python -m spacesonar.cli project writer-smoke --run-refs <run_refs.csv> --campaign-id <campaign_id> --summary <summary.yaml> --pre-runtime` before considering broader validation.
- Do not route a first plumbing attempt as full-project reconciliation. Add broader validation only after the thin path is real or the claim requires it.
- For session start/resume, route the first executable step as one narrow fixture/run/probe/smoke path. Broad materializers, global sync, full validators, or full pytest require an explicit boundary/claim/drift reason.
- If the user asks why progress is slow or asks for experiments, route to the active work item's next executable writer, runner, probe, adapter, or materializer. Validation-only work is allowed only when the source-of-truth record itself is the task.
- If the user complains about pytest/full-regression/evidence-graph delay, route either to the active executable work item or to `policy_skill_governance` to harden the operating rule; do not answer by starting another broad validation pass.
- Broad hash resync or global registry regeneration is not a writer-scope repair. Prefer targeted hash/source-of-truth checks for the touched manifest, receipt, summary, or registry row; escalate only for boundary, drift, shared-contract, or explicit user-request reasons.
- YAML identity lint is a valid writer-scope smoke for touched control/evidence YAML. It catches PyYAML `&id...` / `*id...` anchors before they become machine-record drift.
- For direct repository inspection, use source-of-truth and touched-owner reads. Do not route unbounded recursive workspace walks as proof; volatile tree inventory is operational noise.
- `python -m spacesonar.cli project validate` is not a default progress-loop smoke. It is boundary, source-of-truth drift, shared validator/contract semantics, or explicit user-request scope.

## Do Not

- select broad automatic skill groups
- create numbered legacy routing rules
- treat advisory micro-consult as formal review
- make internal receipts tutorial-like
- use whole-tree scans, repeated folder passes, or CI success as proof of operating stability
- use recursive workspace listing without excluding volatile/generated trees
- scan volatile local trees such as `.pytest_tmp`, `.spacesonar/transactions`, runtime reports/telemetry, or package artifacts as a routine current-truth source
- claim completion/review/pass without required gate coverage
- route a non-trivial item without a storage contract
- skip a runtime learning probe decision when runtime behavior, economics, EA/ONNX meaning, or handoff is in scope
- route or close a repo-controlled support gap as blocked/deferred/invalid/discarded without a failure disposition record: reproduction, failing layer, repair/fallback attempt, evidence, remaining blocker, and reopen condition
