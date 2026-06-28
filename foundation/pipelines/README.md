# Pipelines

Reusable orchestration entry points for the ONNX lab.

Active pipeline style:

- manifest-centered
- run-id aware
- bundle-id aware when exporting ONNX or runtime packages
- ID-based ownership

No-pytest operating rule:

- Pipeline writers own their manifest, receipt, summary, hash, and claim-boundary output contracts.
- New or changed writers follow `docs/agent_control/writer_scope_operating_contract.yaml`.
- Each writer-owned summary/manifest/closeout must record `validation_depth`, `non_pytest_smokes`, `skipped_broad_validations`, `broad_validation_escalation_reason`, `writer_scope_self_check`, `source_of_truth_paths`, `claim_boundary`, and `next_action` or `reopen_condition`.
- A writer must not rely on pytest, full-regression, full active-record validation, evidence-graph validation, or broad registry regeneration to discover ordinary missing output files.
- Before projecting `artifact_identity` or registry rows, the writer must ensure proof-bearing summaries and receipts exist on the same filesystem path being hashed.
- Missing optional raw local artifacts, such as ignored telemetry CSVs or tester reports, are recorded as explicit availability/missing-evidence fields instead of crashing the writer.
- Runtime runners must write terminal summary, telemetry summary, tester-report receipt, missing evidence, next action, and claim boundary even when the Strategy Tester run is incomplete.
- Use scoped syntax/import/command smoke for touched entry points; boundary validation is reserved for campaign closeout, wave closeout, source-of-truth drift, shared-contract changes, protected claim changes, or explicit user request.
- Broad validation requires a recorded command-intent gate: allowed reason, owner surface, source-of-truth paths, why writer-scope is insufficient, expected claim effect, and smaller checks already attempted or not applicable.
