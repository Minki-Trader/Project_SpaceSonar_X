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

## Operational Stability Floor

- Default `validation_depth` is `writer_scope_smoke`; broad validation commands are not progress-loop defaults.
- If this skill mutates, closes, judges, or routes a record, follow `docs/agent_control/writer_scope_operating_contract.yaml` and record `writer_contract_version`, source-of-truth paths, writer-owned outputs, non-pytest smokes, skipped broad validations, escalation reason, self-check, claim boundary, forbidden claims, blocker or reopen condition, and next action.
- A discovered gap becomes an owner writer, manifest, policy, or scoped lint repair before pytest, project validate, full regression, evidence graph, broad hash resync, or global registry regeneration.
