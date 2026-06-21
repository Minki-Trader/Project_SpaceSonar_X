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
- Try-first disposition rule: a failure can be closed only after why it failed is identified, the failing layer is reproduced, the smallest credible repair/fallback under repo control is attempted, and the evidence is recorded.
- `blocked`, `deferred`, `invalid`, or `discarded` cannot be based only on "cannot", "unsupported", "not available", or missing adapter/glue.
- Before that disposition, record root cause, exact failing layer, repair/fallback attempt evidence, remaining blocker, and reopen condition.
- If converter/conversion adapter/export/EA/parser/runtime glue is missing and is under repo/control, build and test the smallest adapter or fallback before disposition. Only user secrets, unavailable external state, destructive/unsafe action, or policy violation can block the attempt.
- "Adapter does not exist yet" is an implementation task, not a final reason to defer or discard.
- `candidate` is not selected baseline, reviewed, verified, pass, runtime authority, or economics pass.
