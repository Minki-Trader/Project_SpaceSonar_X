# Project SpaceSonar X - Codex Boot Kernel

Purpose: minimal cold-start rules for an ID-based ONNX development lab. Internal artifacts are for Codex, not for user reading.

## Mission

- Build, test, export, package, and probe ONNX-driven FPMarkets `US100` `M5` research systems.
- Operate as a developer lab with IDs, not numbered legacy pipelines.
- Primary instrument: `US100` `M5`.
- Final north star, not an exploration gate: 5+ trades/day, PF about 1.5-3.0, <=10% DD across major windows.
- Active split catalog: `configs/onnx_lab/split_recipes/split_set_v0.yaml`; research split set only, not baseline/pass/review.

## Non-Inheritance

- Blank slate: no default feature set/count, label, target, direction class, holding period, model family, IO shape, output head, threshold, or risk logic.
- Do not inherit legacy winners, selected baselines, promotion history, live readiness, runtime authority, economics pass, or Goal Achieve.
- Removed legacy material is unavailable as evidence. Do not recreate it unless the user explicitly restores backup material.

## Symbol Rules

- Live-chart auxiliary symbols are allowed only after local FPMarkets MT5 proves real-time bars/ticks for the exact symbol.
- Eligible examples only after proof: `BTCUSD`, gold symbols.
- Forbidden as inputs/features/runtime contracts when stale, delayed, unavailable, offline, or non-updating: `VIX`, single stocks such as `NVDA`, or any non-updating feed.

## Default Reads

Read this file first, then stop. Load more only when task-relevant:

- current lab truth: `docs/workspace/workspace_state.yaml`
- non-trivial routing: `docs/agent_control/work_family_registry.yaml`
- ONNX bundle/schema/export: `docs/contracts/onnx_lab_contract.yaml`
- split/eval: `configs/onnx_lab/split_recipes/split_set_v0.yaml`
- MT5/runtime: `foundation/config/mt5_runtime_probe_contract.yaml`
- MT5 runtime date windows: `configs/mt5/period_profiles/split_set_v0_runtime_periods.yaml`
- selected skill only after routing: `.agents/skills/<skill>/SKILL.md`

Do not read broad archives, legacy routing/review records, or generated run trees by default.

## ID Model

Canonical chain:

`goal_id -> wave_id -> campaign_id -> idea_id -> hypothesis_id -> surface_id -> sweep_id -> run_id -> artifact_id -> bundle_id -> candidate_id`

Every non-trivial work item chooses exactly one `primary_family` and one `primary_skill`; support skills only when they change execution, evidence, or closeout.

## Source Of Truth Paths

- wave: `lab/waves/<wave_id>/wave_allocation.yaml`
- wave campaign refs: `lab/waves/<wave_id>/campaign_refs.csv`
- campaign: `lab/campaigns/<campaign_id>/campaign_manifest.yaml`
- run manifest: `lab/runs/<run_id>/run_manifest.json`
- run receipt: `lab/runs/<run_id>/experiment_receipt.yaml`
- lineage: `lab/runs/<run_id>/artifact_lineage.json`
- metrics: `lab/runs/<run_id>/metrics.json`
- candidate: `lab/candidates/<candidate_id>/candidate_summary.yaml`
- bundle: `runtime/packages/<bundle_id>/experiment_bundle.json`
- MT5 attempt: `runtime/mt5_attempts/<attempt_id>/attempt_manifest.yaml`
- indexes only: `docs/registers/`

Wave owns allocation and refs only. Campaign folders stay central under `lab/campaigns/`; do not duplicate them under waves.
Wave/campaign scope must not become a long repair room for one candidate. Small repair attempts are bounded run/sweep work; if a repair does not reveal a reusable surface clue, close it as negative, invalid, inconclusive, or preserved clue and rotate.

## Code Layout

- reusable package: `src/spacesonar/`
- collectors: `foundation/collectors/`
- features: `foundation/features/`
- labels: `foundation/labels/`
- training: `foundation/training/`
- ONNX helpers: `foundation/onnx/`
- parity: `foundation/parity/`
- MT5/EA/set templates: `foundation/mt5/`
- orchestration: `foundation/pipelines/`

Do not put reusable feature, label, ONNX, parity, or MT5 logic only inside one-off run scripts.

## Evidence Rules

- Durable identity uses repo-relative paths plus IDs/hashes.
- Absolute terminal paths are local context/logs only.
- Registry rows are indexes, not proof.
- Heavy artifacts are not committed by default; record path/URI, sha256, size, producer command, regeneration command, or source of truth.
- Do not duplicate a source-of-truth artifact. If copied, record `source_of_truth` and `copy_reason`.

Non-trivial run records must include:

- `primary_family`, `primary_skill`, `required_gates`
- `claim_boundary`, `forbidden_claims`
- `runtime_learning_probe_decision`
- `proxy_runtime_parity`
- `missing_evidence`, `result_judgment`, `next_action`
- `branch_worktree_fit`, `branch_action`
- provenance: git state, command/runtime identity, timing, input/output hashes

Unknown git/env identity is planning scaffold only; it lowers reproducible-run, bundle, runtime, handoff, pass, readiness, and Goal Achieve claims.

## Runtime And Parity

- Every valid proxy/model-bearing experiment must be designed for ONNX/EA/MT5 follow-through.
- Proxy-only closure is not allowed for valid proxy/model-bearing runs.
- Required follow-through: reach `L4_split_runtime_probe` under active period/execution profiles.
- If L4 remains promising, continue to `L5_candidate_runtime_evidence`.
- If a surface cannot be made MT5-executable, repair it before treating proxy output as evidence.
- Do not stretch a wave or campaign around repeated tiny repairs for one candidate. One bounded repair can create prevention memory; repeated repair needs a new surface question, divergence campaign, or closeout.
- Campaigns must maintain `proxy_runtime_parity`: shared contract, known differences, MT5 risks, one reconciliation attempt, unit semantics, comparison class, divergence judgment, prevention memory, follow-up.
- Parity does not mean forced equality. Record genuine MT5 unit/execution differences as prevention memory.
- Samples/previews/diagnostic rows support learning only; they cannot create runtime authority, economics pass, materialization-ready, or handoff-complete claims.

ONNX bundle source of truth: `experiment_bundle.json`.
Minimum identity: dataset/hash, feature schema/order hash, label/split, task surface, framework/opset/input/output schema, ONNX hash, parser/runtime contract, decision surface, producer command/env.

## Claim Rules

Exploration has no gate. Operating meaning has gates.

Allowed without heavy proof: idea exploration, broad/extreme sweep design, proxy observation, negative memory, invalid setup, blocked retry, planning scaffold.

Forbidden without matching evidence:

- selected baseline
- operating reference or promotion
- runtime authority
- economics pass
- materialization-ready
- handoff complete
- live readiness
- Goal Achieve
- reviewed/verified/pass

## Task Force

- Codex owns final judgment.
- Micro-consult is advisory only.
- Never adopt sub-agent advice verbatim. Before using it, compare it against repo source-of-truth files, project rules, selected skills, current workspace state, and user constraints.
- If agent advice conflicts with source-of-truth files or active project definitions, reject or revise the advice and record the conflict boundary.
- When a delegated agent lacks forked context or did not read the relevant source files, treat its output as hypothesis/advice only, not project truth.
- Agent roles are proactive modes: `scout`, `design`, `preflight`, `adversarial_check`, `evidence_check`, `runtime_check`, `closeout_check`.
- `.codex/config.toml` `max_threads` is capacity only; actual agent count is phase-driven.
- Formal Task Force review only for policy change, runtime authority, operating promotion, cross-system handoff, or protected reviewed/verified/pass claims.
- If formal review is required but custom agents are unavailable, mark blocked for that review.
- No legacy external-review path exists.

## Git

- Use `codex/` branches unless user asks otherwise.
- Commit/main-push cadence: `campaign_open`, `campaign_close`, `wave_open`, `wave_close`.
- Do not push every run to `main` by default.
- Check branch/worktree fit before mutation.
- Current git root may be this project or a parent `MQL5` tree; avoid unrelated MetaTrader folders in status/commits.
- Never revert user changes unless explicitly requested.

## Internal Style

- Internal records: English-friendly, ID-oriented, compact, field-based, evidence-path explicit, claim-boundary explicit, stop-condition explicit.
- User-facing answers: Korean when user writes Korean; report action/effect briefly; do not make the user read files.
