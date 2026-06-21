# Result Judgment Policy

## Judgment Classes

- `positive`: useful signal or setup worth extending inside the stated boundary.
- `negative`: valid result that weakens or closes a hypothesis.
- `inconclusive`: evidence is insufficient for the intended interpretation.
- `invalid`: setup, data, assumption, leakage, or runtime condition is broken.
- `blocked`: required environment, user input, or external state is unavailable after repair attempts.
- `preserved_clue`: reusable observation that should not yet become a candidate.
- `candidate`: compute/probe allocation, not selection.

## Rules

- A judgment must include claim boundary, evidence path, and missing evidence.
- `negative` is reusable evidence when the setup is valid.
- `invalid` is not interpreted until the broken condition is repaired.
- Missing required verification lowers the claim to `inconclusive`, `blocked`, or a narrower boundary.
- `candidate` is not selected baseline, reviewed, verified, pass, runtime authority, or economics pass.
