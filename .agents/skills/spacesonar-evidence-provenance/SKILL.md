---
name: spacesonar-evidence-provenance
description: Track run evidence, artifact identity, hashes, environment, and regeneration lineage.
---

# SpaceSonar Evidence Provenance

Use when work creates, consumes, moves, summarizes, registers, or closes evidence, artifacts, run outputs, runtime outputs, or reproducibility records.

## Required Output

- `source_inputs`
- `producer`
- `consumer`
- `artifact_paths`
- `artifact_hashes`
- `artifact_sizes`
- `source_of_truth_paths`
- `environment_summary`
- `regeneration_commands`
- `registry_links`
- `availability`
- `lineage_judgment`
- `writer_scope_self_check`
- `validation_depth`
- `non_pytest_smokes`
- `skipped_broad_validations`
- `broad_validation_escalation_reason`
- `claim_boundary`

## Guardrails

- Manifests and receipts are proof-bearing; registries are projections and indexes.
- Use repo-relative paths plus IDs and hashes for durable identity.
- For no-pytest operation, prefer writer-time manifest/receipt/hash checks over broad retrospective validation.
- Evidence writers must emit the writer-scope operating contract fields for the touched evidence surface; missing proof-bearing summaries, receipts, or hashes are writer-local failures, not pytest triggers.
- Compute hashes from the final written bytes after newline and encoding decisions are complete; do not use broad hash resync to mask a writer contract bug.
- A writer that records `artifact_identity` must first ensure the referenced summary/receipt exists on the same filesystem path it will hash. Optional raw local artifacts may be marked missing or local-only; proof-bearing summaries and receipts must not be missing after writer close.
- Machine YAML proof/control records must be dumped without aliases or anchors. Use the repo `NoAliasDumper` / `dump_yaml` helper, deep-copy reused nested objects before assigning them into multiple branches, and run touched YAML identity lint when manual or control-record rewrites are involved.
- For touched run evidence, run writer-scope smoke through `python -m spacesonar.cli project writer-smoke ...`; do not substitute full active-record validation as the default proof path.
- Do not substitute `python -m spacesonar.cli project validate` for writer-local evidence proof during ordinary progress work. If project validate is needed, record the boundary, drift, shared-contract, or explicit user-request reason.
- Do not run broad hash resync before checking the touched writer path and final bytes; use targeted artifact hash check/update only for the touched registered artifact.
- Treat telemetry/report/artifact directories as raw evidence locations, not traversal roots for routine operating truth; consume their paired manifests, summaries, receipts, and hashes.
- Do not commit heavy artifacts just to close a gap.
- Do not call a run reviewed, selected, runtime-ready, economics-pass, or handoff-complete without matching durable evidence.
- Missing repo-controlled evidence glue is implementation work before a blocked, deferred, invalid, or discarded disposition.
