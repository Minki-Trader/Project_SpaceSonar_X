---
name: spacesonar-architecture-guard
description: Guard ONNX lab architecture, policy, skills, agents, path identity, encoding, and ownership changes.
---

# SpaceSonar Architecture Guard

Use this skill when work can change ownership, source of truth, path identity, model identity, runtime identity, agent routing, or durable project semantics.

## Trigger Surface

- feature calculation
- label generation
- model training or export
- ONNX bundle construction
- runtime package or MT5 handoff
- artifact registry or claim surface
- reusable code placement
- repo-scoped skills or agent settings
- work-family routing
- archive behavior
- path identity or generated artifact policy

## Reads

Read only touched policy/skill/control files plus:

- `AGENTS.md`
- `docs/agent_control/work_family_registry.yaml` when routing changes
- `docs/agent_control/surface_registry.yaml` when path ownership changes
- `docs/workspace/workspace_state.yaml` when current truth changes

## Required Output

- `architecture_risk`
- `source_of_truth_effect`
- `ownership_boundary`
- `path_safety_check`
- `storage_contract_effect`
- `encoding_check`
- `line_ending_check`
- `code_surface_check`
- `skill_routing_check`
- `claim_boundary_effect`

## Guardrails

- Do not normalize legacy architecture debt as current style.
- Do not describe a model as materialized without a reproducible artifact or frozen spec bundle.
- Do not put reusable feature, label, ONNX, parity, or MT5 logic into one-off run scripts.
- Do not store absolute terminal paths as durable artifact identity.
- Use repo-relative paths plus hash, run id, bundle id, or registry id.
- Prefer manifests and hashes over committing heavy generated artifacts.
- Keep registry rows as indexes; source-of-truth manifests live in the run, bundle, candidate, campaign, or MT5 attempt folder.

## Validator

After editing skills, agents, or control-plane YAML, run a scoped syntax/metadata validation. If the historical validator is stale, record that and run direct YAML/TOML/frontmatter checks for the touched files.
