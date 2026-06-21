# Registers

Compact indexes for the ONNX lab.

Rules:

- One row per durable identity.
- Detailed evidence stays inside `lab/runs/<run_id>/`, `lab/candidates/<candidate_id>/`, `runtime/packages/<bundle_id>/`, or `runtime/mt5_attempts/<attempt_id>/`.
- Wave, campaign, surface, sweep, recipe, and clue registries are indexes for allocation and findability.
- Ingredient card and synthesis campaign registries index previous-material-only mixing; they are not proof and do not select future wave direction.
- A registry row is findability metadata, not proof by itself.
- Rows should include ID, status, claim boundary, evidence path, hash when applicable, and next action.
- Missing evidence must be recorded as missing with reason rather than replaced by a registry note.
