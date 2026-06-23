---
name: spacesonar-lane-classifier
description: "Classify ONNX lab lane: exploration, evidence, model, bundle, runtime, handoff, cleanup, or mixed intent."
---

# SpaceSonar Lane Classifier

Use this skill when a task mixes exploration, evidence, data, model, ONNX export, runtime, handoff, cleanup, or strong-claim language.

## Lane Types

- `exploration`: idea, hypothesis, broad/extreme sweep, scout surface
- `evidence`: run measurement, metrics, lineage, result judgment
- `data_feature`: data, timestamp, feature, label, split, leakage
- `model`: training, calibration, selection, validation risk
- `bundle`: ONNX export, schema, hash, package, parity preflight
- `runtime`: MT5/EA/tester/economics/runtime observation
- `handoff`: cross-system package or user-deliverable handoff
- `cleanup`: archive, delete, restore, or path boundary work
- `mixed`: more than one lane needs explicit routing

## Required Output

- `lane`
- `claim_surface`
- `primary_family_candidate`
- `hard_gate_applicable`
- `runtime_gate_applicable`
- `evidence_boundary`
- `claim_boundary`

## Guardrails

- Exploration lanes do not need operating gates.
- Runtime/economics/handoff claims need runtime evidence.
- Candidate status is not selected baseline.
- Bundle parity is not economics pass.
