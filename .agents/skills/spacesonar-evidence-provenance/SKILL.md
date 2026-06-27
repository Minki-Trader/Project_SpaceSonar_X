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
- Do not commit heavy artifacts just to close a gap.
- Do not call a run reviewed, selected, runtime-ready, economics-pass, or handoff-complete without matching durable evidence.
- Missing repo-controlled evidence glue is implementation work before a blocked, deferred, invalid, or discarded disposition.
