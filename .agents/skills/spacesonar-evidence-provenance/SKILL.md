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
- `claim_boundary`

## Guardrails

- Manifests and receipts are proof-bearing; registries are projections and indexes.
- Use repo-relative paths plus IDs and hashes for durable identity.
- For no-pytest operation, prefer writer-time manifest/receipt/hash checks over broad retrospective validation.
- Compute hashes from the final written bytes after newline and encoding decisions are complete; do not use broad hash resync to mask a writer contract bug.
- A writer that records `artifact_identity` must first ensure the referenced summary/receipt exists on the same filesystem path it will hash. Optional raw local artifacts may be marked missing or local-only; proof-bearing summaries and receipts must not be missing after writer close.
- For touched run evidence, run writer-scope smoke through `python -m spacesonar.cli project writer-smoke ...`; do not substitute full active-record validation as the default proof path.
- Treat telemetry/report/artifact directories as raw evidence locations, not traversal roots for routine operating truth; consume their paired manifests, summaries, receipts, and hashes.
- Do not commit heavy artifacts just to close a gap.
- Do not call a run reviewed, selected, runtime-ready, economics-pass, or handoff-complete without matching durable evidence.
- Missing repo-controlled evidence glue is implementation work before a blocked, deferred, invalid, or discarded disposition.
