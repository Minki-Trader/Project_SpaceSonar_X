# Project SpaceSonar X - Codex Boot Kernel

Purpose: minimal cold-start rules for an ID-based ONNX development lab. Internal artifacts are for Codex, not for user reading.

## Mission

- Build, test, export, package, and probe ONNX-driven FPMarkets `US100` `M5` research systems.
- Operate as a developer lab with IDs, not numbered legacy pipelines.
- Final north star, not an exploration gate: 5+ trades/day, PF about 1.5-3.0, <=10% DD across major windows.
- Active split catalog: `configs/onnx_lab/split_recipes/split_set_v0.yaml`; research split set only, not baseline/pass/review.
- Campaigns must explore meaningful surfaces, not become single-axis repair rooms.

## Non-Inheritance

- Blank slate: no default feature set, label, target, direction class, holding period, model family, IO shape, output head, threshold, or risk logic.
- Do not inherit legacy winners, selected baselines, promotion history, live readiness, runtime authority, economics pass, or Goal Achieve.
- Removed legacy material is unavailable as evidence unless the user explicitly restores it.

## Default Reads

Read this file first, then stop. Load more only when task-relevant:

- current lab truth: `docs/workspace/workspace_state.yaml`
- non-trivial routing: `docs/agent_control/work_family_registry.yaml`
- operational stability/no-pytest cadence: `docs/agent_control/operational_stability_kernel.yaml`
- writer-scope operating contract: `docs/agent_control/writer_scope_operating_contract.yaml`
- canonical policy: `docs/agent_control/policy_contract.yaml`
- ONNX bundle/schema/export: `docs/contracts/onnx_lab_contract.yaml`
- split/eval: `configs/onnx_lab/split_recipes/split_set_v0.yaml`
- MT5/runtime: `foundation/config/mt5_runtime_probe_contract.yaml`
- MT5 runtime windows: `configs/mt5/period_profiles/split_set_v0_runtime_periods.yaml`
- selected skill only after routing: `.agents/skills/<skill>/SKILL.md`

Do not read broad archives, legacy routing/review records, or generated run trees by default.
Direct inspection means source-of-truth and owned code/policy files. Do not use unbounded recursive workspace walks or volatile generated trees as operating proof.

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

Wave owns allocation and refs only. Campaign folders stay central under `lab/campaigns/`.

## Code Layout

- reusable package: `src/spacesonar/`
- collectors/features/labels/training/ONNX/parity/MT5 helpers: `foundation/`
- orchestration: `foundation/pipelines/`

Do not put reusable feature, label, ONNX, parity, or MT5 logic only inside one-off run scripts.

## Critical Guards

Policy meaning lives in `docs/agent_control/policy_contract.yaml`; manifests bind guard IDs instead of copying policy text.

- `GUARD_001_ATTEMPT_BEFORE_DISPOSITION`: diagnose, reproduce, attempt the smallest repo-controlled repair/fallback, then record disposition.
- `GUARD_002_RUNTIME_COMPLETION_TRUTH`: L4 completion requires portable terminal mode, telemetry rows, completed tester report, correct period/execution IDs, and eligible surface scope.
- `GUARD_003_CLAIM_BOUNDARY`: no selected baseline, runtime authority, economics pass, materialization-ready, handoff complete, live readiness, Goal Achieve, reviewed/verified/pass without matching evidence.
- `GUARD_004_ARTIFACT_IDENTITY`: durable identity uses repo-relative paths plus IDs/hashes; registries are indexes, not proof.
- `GUARD_005_LOCKED_OOS`: locked final OOS is excluded unless an explicit unlock contract exists.
- `GUARD_006_BRANCH_WORKTREE`: check branch/worktree fit before mutation; never revert user changes unless explicitly asked.
- `GUARD_007_OPERATIONAL_STABILITY`: default to writer-scope smoke and source-of-truth checks; routine pytest, full evidence graph, broad hash sync, global registry regeneration, or whole-tree scans are forbidden unless a boundary, drift, shared-contract change, protected claim, or explicit user request requires them.

No-pytest operation is writer-contract first: every new or changed writer must name
its `writer_contract_version`, owned source-of-truth paths, output records, validation depth, non-pytest
smokes, skipped broad validations, escalation reason, self-check, claim boundary,
and next action before broad validation can be considered.
Strong trigger rule: every new or changed writer must pass `writer_preflight_gate`
before mutation and carry `validation_attempt_budget`. Writer-scope validation is
limited to the initial smoke plus one owner repair/resmoke; a third pass requires
a blocker/reopen condition or command-intent escalation record.
Strict writer-owned YAML surfaces use the shared write-time guard
`src/spacesonar/control_plane/writer_contract.py`; transaction-backed writers get
the same fail-before-mutation check through `ControlPlaneTransaction.stage_yaml`.

## Runtime And Parity

- Every valid proxy/model-bearing experiment must be designed for ONNX/EA/MT5 follow-through.
- Proxy-only closure is not allowed for valid proxy/model-bearing runs.
- Required follow-through reaches `L4_split_runtime_probe`; if promising, continue to `L5_candidate_runtime_evidence`.
- Main-mode MT5 fallback is diagnostic only and cannot satisfy standard runtime completion.
- Samples/previews/diagnostic rows support learning only; they cannot create runtime authority, economics pass, handoff, or live readiness.

## Git

- Current user operating override: do not create or use routine `codex/` work branches.
- Work on `main` by default unless the user explicitly asks for a separate branch.
- Do not push every run. Push `origin/main` at campaign closeout or an explicit user-approved boundary/stabilization point.
- Current git root may be this project or a parent `MQL5` tree; avoid unrelated MetaTrader folders in status/commits.
- Never revert user changes unless explicitly requested.

## User-Facing Style

Answer in Korean when the user writes Korean. Report action/effect briefly, name the current claim boundary, and do not make the user read internal manifests.
