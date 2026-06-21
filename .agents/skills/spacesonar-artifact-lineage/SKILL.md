---
name: spacesonar-artifact-lineage
description: Track artifact inputs, outputs, paths, hashes, manifests, availability, and handoff/evidence lineage.
---

# SpaceSonar Artifact Lineage

Use this skill when work creates, consumes, moves, ignores, packages, releases, or reports artifacts.

## Required Output

- `source_inputs`
- `producer`
- `consumer`
- `artifact_paths`
- `artifact_hashes`
- `artifact_sizes`
- `source_of_truth_paths`
- `regeneration_commands`
- `registry_links`
- `availability`
- `lineage_judgment`

## Preferred Registries

- `docs/registers/run_registry.csv`
- `docs/registers/artifact_registry.csv`
- `docs/registers/candidate_registry.csv`

## Guardrails

- Do not let a registry row point to missing evidence without a manifest, URI, or regeneration command.
- Do not commit heavy artifacts just to close an evidence gap.
- Do not treat a report as the same thing as a model, ONNX file, runtime bundle, or MT5 report.
