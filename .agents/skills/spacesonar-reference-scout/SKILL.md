---
name: spacesonar-reference-scout
description: Use external/official refs for version-sensitive APIs, MT5/MQL5 behavior, libraries, or quant methods.
---

# SpaceSonar Reference Scout

Use when outside references can improve correctness, idea quality, or confidence in environment behavior.

This skill grounds decisions; it does not import external authority over project contracts.

## When To Use

- API, syntax, or library behavior is uncertain.
- MQL5, MT5, MetaEditor, Strategy Tester, file handoff, `.set`, `input/sinput`, `#include`, `OnInit`, `OnTick`, or `OnTester` behavior is involved.
- LightGBM, pandas, sklearn, numpy, ONNX, or another dependency may be version-sensitive.
- Maintained examples can inform implementation shape.
- Quant method choice, validation frame, backtest method, or runtime parity needs grounding.
- Exploration is stuck and outside examples may suggest new ideas.

## Pairing

For code-writing work, pair with `spacesonar-code-surface-guard` when external behavior affects the implementation.

If lookup is not needed, record `reference_scout: not_required` with the reason in the precheck or completion report.

## Source Priority

1. Official documentation or vendor docs.
2. Maintained source repository, examples, release notes, or issue discussions.
3. Well-scoped examples with readable code and recent maintenance.
4. Forum or community posts only as idea candidates or practical warnings.

## Required Output

- `question`
- `sources_checked`
- `source_quality`
- `found_pattern`
- `project_fit`
- `do_not_copy`
- `recommended_use`
- `not_required_reason`

## EA Hard Trigger

For MT5 EA architecture or Strategy Tester behavior, check official MQL5 documentation first.

Minimum questions:

- Is this behavior defined in official docs?
- Does it belong in the main `.mq5` entrypoint or a `.mqh` include module?
- Is the run difference parameter-only or code-changing?
- Which identity fields must be recorded so tester output can be traced?

## Guardrails

- Prefer official docs for API and syntax questions.
- Do not copy external code wholesale into this repo.
- Do not trust forum performance claims as evidence.
- Do not let external examples override project contracts for time axis, dataset identity, split policy, artifact identity, or runtime authority.
- If a source is old, version-specific, or unclear, say so.
- If browsing or source lookup was not performed, do not present the answer as externally verified.
