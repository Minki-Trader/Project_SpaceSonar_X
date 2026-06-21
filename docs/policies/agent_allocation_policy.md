# Agent Allocation Policy

Purpose: keep Task Force usage active and phase-driven without treating agent agreement as evidence.

## Capacity

`.codex/config.toml` `max_threads` is capacity only. It is not an instruction to fill all available threads, and it is not evidence.

## Default Allocation

- Codex alone: default for direct edits and local verification.
- One agent: narrow micro-consult for one specialized remit.
- Two agents: two-remit checks, such as routing plus evidence or data plus runtime.
- Three to four agents: policy, runtime, data, or architecture intersections where smaller routing would miss a material surface.
- Full roster: major direction change, protected claim preparation, or user-requested deep full-team review only.

## Role Modes

- `scout`: find experiment or design options without creating a claim.
- `design`: shape implementation, interfaces, or evidence before edits.
- `preflight`: check branch, scope, stale truth, and stop conditions before execution.
- `adversarial_check`: look for counterarguments, leakage, missing evidence, or claim laundering.
- `evidence_check`: specify receipts, manifests, hashes, and storage-contract requirements.
- `runtime_check`: check ONNX/EA/MT5 meaning boundaries and probe requirements.
- `closeout_check`: classify result boundary and forbidden claims after local evidence exists.

## Receipt Requirements

Agent receipts must record selected agents, role modes, selection reason, why the route was not smaller, why it was not larger, critical agents not selected, not-selected claim effect, and claim boundary.

Agent output is advisory only. Codex owns final direction after local verification.
