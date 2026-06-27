# Pipelines

Reusable orchestration entry points for the ONNX lab.

Active pipeline style:

- manifest-centered
- run-id aware
- bundle-id aware when exporting ONNX or runtime packages
- ID-based ownership

No-pytest operating rule:

- Pipeline writers own their manifest, receipt, summary, hash, and claim-boundary output contracts.
- A writer must not rely on pytest, full-regression, full active-record validation, evidence-graph validation, or broad registry regeneration to discover ordinary missing output files.
- Before projecting `artifact_identity` or registry rows, the writer must ensure proof-bearing summaries and receipts exist on the same filesystem path being hashed.
- Missing optional raw local artifacts, such as ignored telemetry CSVs or tester reports, are recorded as explicit availability/missing-evidence fields instead of crashing the writer.
- Runtime runners must write terminal summary, telemetry summary, tester-report receipt, missing evidence, next action, and claim boundary even when the Strategy Tester run is incomplete.
- Use scoped syntax/import/command smoke for touched entry points; boundary validation is reserved for campaign closeout, wave closeout, source-of-truth drift, shared-contract changes, protected claim changes, or explicit user request.
