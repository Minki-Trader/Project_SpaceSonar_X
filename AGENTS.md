# Project SpaceSonar X - ONNX Lab Boot Kernel

Purpose: keep cold-start context small while operating this workspace as an ID-based ONNX development lab.

## Core

- Workspace mission: build, test, export, package, and probe ONNX-driven FPMarkets `US100` `M5` research systems.
- Active operating shape: developer lab with run/campaign IDs, not numbered legacy pipelines.
- Preserve: broker-symbol contract, time-axis discipline, feature-label boundaries, ONNX/EA parity discipline, evidence discipline.
- Blank-slate concept: no default feature set, label, prediction target, direction class, holding period, model family, output head, decision surface, threshold, or risk logic exists.
- North star: no fixed TF/task; seek systems with 5+ trades/day, PF around 1.5-3.0, and <=10% DD across major windows. This is a final objective, not an exploration gate.
- Primary instrument: `US100` `M5`.
- Active research split catalog: `configs/onnx_lab/split_recipes/split_set_v0.yaml`. It is an adopted research split set, not a canonical baseline, pass, or reviewed claim.
- Broker-native live-chart auxiliary symbols may be used for research and development when the target FPMarkets MT5 terminal updates their charts in real time and can return current bars/ticks. Examples include `BTCUSD` or gold symbols only when the local terminal proves live chart availability.
- Do not use stale, unavailable, delayed, offline, or non-updating symbols as research inputs, feature sources, model inputs, runtime bundle inputs, or EA contract inputs. Examples include `VIX`, single-stock symbols such as `NVDA`, or any feed that does not update live in the target MT5 terminal.
- Do not inherit: any prior winners, selected baselines, promotion history, live readiness, runtime authority, economics pass, or Goal Achieve.
- No feature list, feature count, target definition, long/short direction framing, fixed holding-duration assumption, model input shape, or output head is inherited.
- Active roots: `src/`, `foundation/`, `configs/`, `data/`, `lab/`, `runtime/`, `docs/`, `.agents/`, `.codex/`, `tests/`.
- Removed legacy workspace material is not part of current operation. Do not recreate it unless the user explicitly restores an external backup.

## Lab Philosophy

- Exploration and experiment design are unrestricted. Gates protect claims, not curiosity.
- Start from zero: first discover and name the problem shape, input surface, target/label surface, decision use, holding logic, and evaluation method before optimizing anything.
- Hypothesis -> experiment -> validation -> judgment is the normal path for meaningful work.
- When runtime behavior, economics, handoff, or EA/ONNX meaning is the question, run the narrow sufficient MT5 runtime probe. Do not defer only because the probe is heavy or expensive.
- Failed, negative, invalid, and inconclusive results are assets when recorded with boundary, reason, salvage value, and reopen condition.

## Startup Budget

On a new session, read this file first and stop. Load more only when the current task requires it.

Default cold-start reads:

- `AGENTS.md`
- `docs/workspace/workspace_state.yaml` only for current lab truth
- `docs/agent_control/work_family_registry.yaml` only for non-trivial routing
- `docs/contracts/onnx_lab_contract.yaml` only for ONNX bundle/schema/export work
- `configs/onnx_lab/split_recipes/split_set_v0.yaml` only for split/evaluation work
- `foundation/config/mt5_runtime_probe_contract.yaml` only for MT5/runtime claims
- `configs/mt5/period_profiles/split_set_v0_runtime_periods.yaml` only for MT5 runtime date-window selection
- touched skill `SKILL.md` only after selecting that skill

Do not read or recreate broad archives, legacy routing records, legacy external-review records, or generated run trees by default. Bulk legacy routing, review, and archive trees are no longer present.

## Work Model

Use this ID hierarchy for current work:

`idea_id -> hypothesis_id -> surface_id -> sweep_id -> run_id -> artifact_id -> bundle_id -> candidate_id`

Primary active locations:

- `lab/hypotheses/`: idea and hypothesis notes when needed
- `lab/campaigns/`: bounded campaign charters
- `lab/runs/<run_id>/`: one folder per run; run-local manifests, receipts, metrics, logs, reports, MT5 evidence, and artifact references
- `lab/candidates/<candidate_id>/`: one folder per candidate; candidate summaries and claim boundary
- `lab/templates/`: manifest and receipt templates
- `runtime/packages/<bundle_id>/`: one folder per bundle; ONNX/EA handoff package references and manifests
- `runtime/mt5_attempts/<attempt_id>/`: one folder per Strategy Tester attempt
- `docs/registers/`: compact indexes only

Every non-trivial work item chooses exactly one `primary_family` and one `primary_skill` from `docs/agent_control/work_family_registry.yaml`. Add only support skills that change execution, evidence, or closeout.

## Storage Rules

- Durable identity uses repo-relative paths only.
- Absolute terminal paths are local context or logs only; never use them as durable artifact identity.
- Campaign source of truth: `lab/campaigns/<campaign_id>/campaign_manifest.yaml`.
- Run source of truth: `lab/runs/<run_id>/run_manifest.json`.
- Run receipt: `lab/runs/<run_id>/experiment_receipt.yaml`.
- Run lineage: `lab/runs/<run_id>/artifact_lineage.json`.
- Run metrics: `lab/runs/<run_id>/metrics.json`.
- Run supporting material stays under `lab/runs/<run_id>/logs/`, `reports/`, `artifacts/`, or `mt5/`.
- Candidate source of truth: `lab/candidates/<candidate_id>/candidate_summary.yaml`.
- Bundle source of truth: `runtime/packages/<bundle_id>/experiment_bundle.json`.
- MT5 attempt source of truth: `runtime/mt5_attempts/<attempt_id>/attempt_manifest.yaml`.
- Registry rows in `docs/registers/` are findability indexes, not proof by themselves.
- Heavy artifacts are not committed by default. Track path, sha256, size, producer command, regeneration command, or external URI.
- Do not duplicate a source-of-truth artifact across locations. If a copy is needed, record `source_of_truth` and `copy_reason`.

## Developer Layout

- `src/spacesonar/`: new Python package surface for reusable lab code
- `foundation/collectors/`: broker/source data collection
- `foundation/features/`: reusable feature logic
- `foundation/labels/`: reusable label logic
- `foundation/training/`: reusable training logic
- `foundation/onnx/`: export, schema, smoke, and bundle helpers
- `foundation/parity/`: Python-vs-ONNX-vs-MT5 parity checks and fixtures
- `foundation/mt5/`: EA sources, include modules, and `.set` templates
- `foundation/pipelines/`: reusable orchestration only; use ID-based entrypoints

## Evidence

Use index-first and run-local receipts.

Each meaningful run should prefer:

- `run_manifest.json`
- `experiment_receipt.yaml`
- `artifact_lineage.json`
- `metrics.json`
- optional logs, reports, and generated artifacts

Heavy artifacts are not committed just to close an evidence gap. Prefer hashes, manifests, external URI, or a regeneration command.

Run-local records must name `primary_family`, `primary_skill`, `required_gates`, `claim_boundary`, `forbidden_claims`, `runtime_learning_probe_decision`, `missing_evidence`, `result_judgment`, and `next_action` when applicable.
Run-local records for non-trivial work must also name `branch_worktree_fit`, `branch_action`, `critical_skills_not_selected`, `not_selected_claim_effect`, and provenance for git state, command/runtime identity, timing, and input/output hashes. Unknown git or environment identity is allowed for planning scaffold only and lowers reproducible-run, bundle, runtime, handoff, pass, readiness, and Goal Achieve claims.

## Claim Discipline

Exploration has no gate. Operating meaning has gates.

Allowed without heavy proof:

- idea exploration
- broad/extreme sweep design
- proxy observation
- negative memory
- invalid setup
- blocked retry condition
- planning scaffold

Forbidden without matching evidence:

- selected baseline
- operating reference
- operating promotion
- runtime authority
- economics pass
- materialization-ready
- handoff complete
- live readiness
- Goal Achieve
- reviewed/verified/pass

No legacy archive is available as current evidence. If an old artifact is found outside active roots, treat it as stale until revalidated or deleted.

## ONNX / Runtime

ONNX bundle source of truth: `experiment_bundle.json`.

Minimum bundle identity:

- dataset id/hash
- feature schema and `feature_order_hash`
- label and split id
- task or target surface id
- model framework/opset/input/output schema
- ONNX hash
- parser/runtime contract version
- decision surface
- producer command and environment summary

Runtime/MT5 verification is needed only for runtime behavior, Strategy Tester output, EA/ONNX handoff, `.mq5/.mqh/.set` behavior, economics, runtime authority, live readiness, or handoff-complete claims.

Standard MT5 probe source of truth: `foundation/config/mt5_runtime_probe_contract.yaml`.

Runtime date-window source of truth: `configs/mt5/period_profiles/split_set_v0_runtime_periods.yaml`.

Samples, previews, diagnostic rows, and proxy score samples can support learning observations only. They cannot create runtime authority, economics pass, materialization-ready, or handoff-complete claims.

Live-chart auxiliary symbol experiments are allowed for research and development only after MT5 availability evidence exists. Runtime bundles, feature schemas, model inputs, and EA contracts that use auxiliary symbols must record the symbol contract, merge policy, feature order, and runtime probe evidence. Non-updating symbols stay out of scope.

No model bundle, EA input contract, or runtime package may assume a fixed prediction target, direction mapping, holding period, or output head from legacy work. Each experiment must declare its own task surface and claim boundary.

## Task Force

Codex owns final judgment.

- Micro-consult is advisory only.
- Agent roles are proactive modes, not passive approval: `scout`, `design`, `preflight`, `adversarial_check`, `evidence_check`, `runtime_check`, and `closeout_check`.
- `.codex/config.toml` `max_threads` is capacity only. Actual agent use is phase-driven: Codex alone by default, 1 agent for narrow micro-consult, 2 agents for two-remit checks, 3-4 agents for policy/runtime/structure intersections, and full roster only for major direction changes or protected claims.
- Formal Task Force review is only for policy change, runtime authority, operating promotion, cross-system handoff, or protected reviewed/verified/pass claims.
- If formal review is required but callable custom agents are unavailable, mark blocked for that review.
- Legacy external review has no active or archive path in this workspace. Do not create outside-review calls, prompts, receipts, gates, or review paths.

## Internal Style

Internal Codex artifacts are machine-oriented:

- English-friendly
- id-oriented
- compact
- field-based
- claim-boundary explicit
- evidence-path explicit
- stop-condition explicit

User-facing answers are different: answer the user plainly, usually in Korean when the user writes Korean. Explain action and effect briefly. Keep uncertainty visible.

## Paths And Git

- Use repo-relative paths for durable identity.
- Absolute paths are local context only.
- Use `rg` / `rg --files` first for discovery.
- For Windows long paths, use targeted long-path handling rather than declaring evidence missing.
- Current git root may be the parent `MQL5` tree; avoid mixing unrelated MetaTrader folders into project status or commits.
- Never revert user changes unless explicitly requested.
