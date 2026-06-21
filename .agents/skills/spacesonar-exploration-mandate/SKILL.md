---
name: spacesonar-exploration-mandate
description: Keep ONNX lab exploration open without legacy inheritance. Use for ideas, variants, sweeps, and negative memory.
---

# SpaceSonar Exploration Mandate

Use this skill when work is primarily exploration or when operating-claim discipline might block research too early.

## Reads

- `docs/policies/onnx_lab_operating_policy.md`
- `docs/registers/idea_registry.csv`
- `docs/registers/hypothesis_registry.csv`
- `docs/registers/negative_memory_registry.csv`

## Required Output

- `idea_id`
- `hypothesis_id`
- `hypothesis`
- `legacy_relation`: `none`, `concept_only`, `lesson_only`, or `prior_evidence_only`
- `axis_tags`
- `broad_sweep`
- `extreme_sweep`
- `micro_search_gate`
- `wfo_plan`
- `failure_memory`
- `evidence_boundary`

## Rules

- Start with broad sweep before micro search.
- Include extreme values when they can reveal cliffs, saturation, or failure boundaries.
- Use WFO as the default optimization frame for serious narrowing.
- Treat single-window optimization as scout evidence unless justified otherwise.
- Do not kill an idea only because WFO, parity, or runtime closure is absent.
- Record failed ideas as negative memory, not waste.
- Do not depend on deleted legacy archives; recreate lessons only from current lab evidence or user-restored material.
